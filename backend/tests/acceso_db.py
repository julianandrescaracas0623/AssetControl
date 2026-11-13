"""Base temporal de acceso para las pruebas de T8–T9 (spec 002).

La usan ``test_roles``, ``test_invitaciones_crear``, ``test_invitaciones_aceptar`` y
``test_invitaciones_concurrencia``.

Crea una base nueva migrada a ``head``, siembra dos tenants sintéticos (A y B) con
el rol migrador (que debe ver todas las filas bajo ``FORCE RLS``) y la borra al
terminar. La aplicación se conecta con el rol de aplicación de
``TEST_DATABASE_URL``. Datos sintéticos (``@ejemplo.test``): nunca de la clínica.
"""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import argon2
import jwt
import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from conftest import BLOCKED, read_database_url, role_sees_all_rows
from flask import Flask
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from app import create_app
from app.auth.credentials import (
    ACCESS_TOKEN_TTL,
    ARGON2_TEST_PARAMS,
    JWT_ISSUER,
    JWT_KEY_CONTEXT,
    derive_key,
    encode_access_token,
)
from app.config import Config

BACKEND_DIR = Path(__file__).resolve().parent.parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"

SECRET_KEY = "clave-sintetica-de-prueba-t8-con-mas-de-32-bytes"
PASSWORD = "Clave-Sintetica-T8-ok"

TENANT_A = uuid.UUID("00000000-0000-4000-8000-00000000a008")
TENANT_B = uuid.UUID("00000000-0000-4000-8000-00000000b008")


@dataclass(frozen=True)
class Cuenta:
    usuario_id: uuid.UUID
    email: str
    nombre: str


ADMIN_A = Cuenta(uuid.UUID("00000000-0000-4000-8000-0000000a0081"), "admin.a8@ejemplo.test", "Ana")
CONTADOR_A = Cuenta(
    uuid.UUID("00000000-0000-4000-8000-0000000a0082"), "contador.a8@ejemplo.test", "Carlos"
)
# Se modifica en las pruebas de A24 (rol y bajas tras emitir el token).
CAMBIANTE_A = Cuenta(
    uuid.UUID("00000000-0000-4000-8000-0000000a0083"), "cambiante.a8@ejemplo.test", "Celia"
)
ADMIN_B = Cuenta(uuid.UUID("00000000-0000-4000-8000-0000000b0081"), "admin.b8@ejemplo.test", "Beto")
CONTADOR_B = Cuenta(
    uuid.UUID("00000000-0000-4000-8000-0000000b0082"), "contador.b8@ejemplo.test", "Berta"
)

# (cuenta, [(tenant, rol, activa)]); todas con usuario activo.
SEED = (
    (ADMIN_A, ((TENANT_A, "admin", True),)),
    (CONTADOR_A, ((TENANT_A, "contador", True),)),
    (CAMBIANTE_A, ((TENANT_A, "admin", True),)),
    (ADMIN_B, ((TENANT_B, "admin", True),)),
    (CONTADOR_B, ((TENANT_B, "contador", True),)),
)


@dataclass(frozen=True)
class AccesoDb:
    app_url: object
    migrator: Engine


def _fail(message: str) -> None:
    pytest.fail(message, pytrace=False)


def _alembic_config() -> AlembicConfig:
    config = AlembicConfig(str(ALEMBIC_INI))
    config.attributes["configure_logger"] = False
    return config


def _seed(migrator: Engine) -> None:
    hasher = argon2.PasswordHasher.from_parameters(ARGON2_TEST_PARAMS)
    with migrator.begin() as conn:
        for tenant, nombre in ((TENANT_A, "Clínica sintética A8"), (TENANT_B, "Clínica B8")):
            conn.execute(
                text("insert into tenant (id, nombre) values (:id, :n)"),
                {"id": tenant, "n": nombre},
            )
        for cuenta, membresias in SEED:
            conn.execute(
                text(
                    "insert into usuario (id, email, nombre, password_hash, activo) "
                    "values (:id, :e, :n, :h, true)"
                ),
                {
                    "id": cuenta.usuario_id,
                    "e": cuenta.email,
                    "n": cuenta.nombre,
                    "h": hasher.hash(PASSWORD),
                },
            )
            for tenant, rol, activa in membresias:
                conn.execute(
                    text(
                        "insert into membresia (tenant_id, usuario_id, rol, activa) "
                        "values (:t, :u, :r, :a)"
                    ),
                    {"t": tenant, "u": cuenta.usuario_id, "r": rol, "a": activa},
                )


def temporary_acceso_db(prefix: str) -> Iterator[AccesoDb]:
    """Generador para un fixture de módulo: base temporal sembrada; se borra al terminar."""
    migrator_url = read_database_url("TEST_MIGRATION_DATABASE_URL")
    app_url = read_database_url("TEST_DATABASE_URL")
    if migrator_url is None or app_url is None or not app_url.username:
        _fail(BLOCKED)
    name = f"assetcontrol_{prefix}_{uuid.uuid4().hex[:12]}"

    admin = create_engine(migrator_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    failure = None
    try:
        with admin.connect() as conn:
            if not role_sees_all_rows(conn):
                failure = (
                    "bloqueado: el rol migrador debe ser superusuario o BYPASSRLS para "
                    "sembrar los datos sintéticos bajo FORCE RLS"
                )
            else:
                conn.execute(text(f'CREATE DATABASE "{name}"'))
    except SQLAlchemyError as exc:
        failure = f"bloqueado: el rol migrador no pudo preparar la base ({type(exc).__name__})"

    migrator: Engine | None = None
    try:
        if failure is not None:
            _fail(failure)
        migrator_db = migrator_url.set(database=name)
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("MIGRATION_DATABASE_URL", migrator_db.render_as_string(hide_password=False))
            mp.delenv("DATABASE_URL", raising=False)
            mp.setenv("APP_DB_USER", app_url.username)
            command.upgrade(_alembic_config(), "head")
        migrator = create_engine(migrator_db, poolclass=NullPool)
        _seed(migrator)
        yield AccesoDb(app_url=app_url.set(database=name), migrator=migrator)
    finally:
        if migrator is not None:
            migrator.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def make_app(db: AccesoDb) -> Flask:
    return create_app(
        Config(
            database_url=db.app_url.render_as_string(hide_password=False),
            secret_key=SECRET_KEY,
            environment="test",
        )
    )


def dispose(flask_app: Flask) -> None:
    flask_app.extensions["assetcontrol.db"].engine.dispose()


def access_token(cuenta: Cuenta, tenant: uuid.UUID, rol: str | None = None) -> str:
    """JWT de acceso válido (firmado con la clave de la app) para ``cuenta`` en ``tenant``."""
    return encode_access_token(SECRET_KEY, sub=cuenta.usuario_id, tenant=tenant, rol=rol)


def bearer(cuenta: Cuenta, tenant: uuid.UUID, rol: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token(cuenta, tenant, rol)}"}


_REAL_KEY = object()


def forged_token(claims: dict, *, key: object = _REAL_KEY, algorithm="HS256", headers=None):
    """JWT con ``claims`` arbitrarios (por defecto firmado con la clave real de la app).

    ``alg: none`` exige ``key=None``.
    """
    if key is _REAL_KEY:
        key = derive_key(SECRET_KEY, JWT_KEY_CONTEXT)
    return jwt.encode(claims, key, algorithm=algorithm, headers=headers)


def base_claims(cuenta: Cuenta, tenant: uuid.UUID) -> dict:
    now = datetime.now(UTC)
    return {
        "sub": str(cuenta.usuario_id),
        "tenant": str(tenant),
        "iss": JWT_ISSUER,
        "iat": int(now.timestamp()),
        "exp": int((now + ACCESS_TOKEN_TTL).timestamp()),
    }


def migrator_execute(db: AccesoDb, sql: str, params: dict | None = None) -> None:
    with db.migrator.begin() as conn:
        conn.execute(text(sql), params or {})


def invitaciones_de(db: AccesoDb, tenant: uuid.UUID) -> list[dict]:
    """Filas de ``invitacion`` del tenant (el migrador ve todos los tenants)."""
    with db.migrator.connect() as conn:
        rows = conn.execute(
            text("select * from invitacion where tenant_id = :t order by expira_en"),
            {"t": tenant},
        ).mappings()
        return [dict(row) for row in rows]


def all_invitaciones(db: AccesoDb) -> list[dict]:
    with db.migrator.connect() as conn:
        return [dict(r) for r in conn.execute(text("select * from invitacion")).mappings()]
