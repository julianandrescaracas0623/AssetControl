"""Login y usuario actual (spec 002, T6; R7, A10, A21; plan.md §2.2, §4).

Comportamiento real sobre una base temporal migrada a ``head`` con dos tenants
sintéticos (A y B), con ``COMMIT`` reales (la base se borra al terminar):

- ``POST /auth/login``: respuesta genérica (mismo código y cuerpo) para
  contraseña mala, cuenta inexistente, usuario inactivo, membresía inactiva,
  varias membresías activas (Q6, falla cerrado), contraseña sobre el máximo o
  con un sustituto suelto (el ``False`` rápido de ``verify``, deuda de T4).
- **Tiempo (A10):** no se mide el reloj (frágil en CI). Se espía el hasher de
  Argon2: con y sin cuenta se verifica exactamente una vez contra un hash de
  los mismos parámetros (el simulado cuando la cuenta no existe).
- JWT de acceso con ``sub`` y ``tenant``; refresh opaco en cookie
  ``<tenant_id>.<secreto>`` ``HttpOnly``/``Secure``/``SameSite=Lax``/``Path=/auth``
  con ``familia_id`` nueva; la base guarda solo ``sha256(sha256(secreto))``.
- ``rol`` y ``activa`` se leen de ``membresia`` bajo el tenant (nunca del claim ni
  de lo que devolvió ``buscar_login``).
- ``GET /auth/me``: token con el ``tenant`` de otro tenant, ``rol`` falsificado,
  membresía o usuario inactivos tras emitir el token -> sin acceso.
- A21: cookie ``Secure`` fuera de ``development``; sin ``Secure`` solo con
  ``development`` explícito.
- Por ruta (B5 de T4): ``no-store``, ``no-referrer`` y ``413`` en ``/auth/login``
  y ``/auth/me``.

Datos sintéticos (``@ejemplo.test``): nunca datos de la clínica.
"""

import base64
import json
import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie
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
from app.auth import service
from app.auth.credentials import (
    ARGON2_TEST_PARAMS,
    JWT_ALGORITHM,
    JWT_ISSUER,
    JWT_KEY_CONTEXT,
    PASSWORD_MAX_LENGTH,
    decode_access_token,
    derive_key,
    get_passwords,
    token_storage_hash,
)
from app.auth.http import AUTH_MAX_BODY_BYTES
from app.config import Config
from app.db import LoginRow

BACKEND_DIR = Path(__file__).resolve().parent.parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"

SECRET_KEY = "clave-sintetica-de-prueba-t6-con-mas-de-32-bytes"
PASSWORD = "Clave-Sintetica-T6-ok"
WRONG_PASSWORD = "Otra-Clave-Sintetica-T6"

TENANT_A = uuid.UUID("00000000-0000-4000-8000-00000000a006")
TENANT_B = uuid.UUID("00000000-0000-4000-8000-00000000b006")
NOMBRE_A = "Clínica sintética A6"
NOMBRE_B = "Clínica sintética B6"


@dataclass(frozen=True)
class Cuenta:
    usuario_id: uuid.UUID
    email: str
    nombre: str


ADMIN_A = Cuenta(uuid.UUID("00000000-0000-4000-8000-0000000a0061"), "admin.a6@ejemplo.test", "Ana")
CONTADOR_A = Cuenta(
    uuid.UUID("00000000-0000-4000-8000-0000000a0062"), "contador.a6@ejemplo.test", "Carlos"
)
INACTIVO_A = Cuenta(
    uuid.UUID("00000000-0000-4000-8000-0000000a0063"), "inactivo.a6@ejemplo.test", "Inés"
)
MEMBRESIA_INACTIVA_A = Cuenta(
    uuid.UUID("00000000-0000-4000-8000-0000000a0064"), "baja.a6@ejemplo.test", "Bruno"
)
DOS_MEMBRESIAS = Cuenta(
    uuid.UUID("00000000-0000-4000-8000-0000000a0065"), "doble.a6@ejemplo.test", "Diana"
)
UNA_ACTIVA_UNA_NO = Cuenta(
    uuid.UUID("00000000-0000-4000-8000-0000000a0066"), "mixta.a6@ejemplo.test", "Mario"
)
ADMIN_B = Cuenta(uuid.UUID("00000000-0000-4000-8000-0000000b0061"), "admin.b6@ejemplo.test", "Beto")
NO_EXISTE = "nadie.a6@ejemplo.test"

# (cuenta, usuario.activo, [(tenant, rol, activa)])
SEED: tuple[tuple[Cuenta, bool, tuple[tuple[uuid.UUID, str, bool], ...]], ...] = (
    (ADMIN_A, True, ((TENANT_A, "admin", True),)),
    (CONTADOR_A, True, ((TENANT_A, "contador", True),)),
    (INACTIVO_A, False, ((TENANT_A, "admin", True),)),
    (MEMBRESIA_INACTIVA_A, True, ((TENANT_A, "admin", False),)),
    (DOS_MEMBRESIAS, True, ((TENANT_A, "admin", True), (TENANT_B, "admin", True))),
    (UNA_ACTIVA_UNA_NO, True, ((TENANT_A, "contador", False), (TENANT_B, "contador", True))),
    (ADMIN_B, True, ((TENANT_B, "admin", True),)),
)


@dataclass(frozen=True)
class LoginDb:
    name: str
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
        for tenant, nombre in ((TENANT_A, NOMBRE_A), (TENANT_B, NOMBRE_B)):
            conn.execute(
                text("insert into tenant (id, nombre) values (:id, :n)"),
                {"id": tenant, "n": nombre},
            )
        for cuenta, activo, membresias in SEED:
            conn.execute(
                text(
                    "insert into usuario (id, email, nombre, password_hash, activo) "
                    "values (:id, :e, :n, :h, :a)"
                ),
                {
                    "id": cuenta.usuario_id,
                    "e": cuenta.email,
                    "n": cuenta.nombre,
                    "h": hasher.hash(PASSWORD),
                    "a": activo,
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


@pytest.fixture(scope="module")
def login_db(database_residue_guard) -> Iterator[LoginDb]:
    """Base temporal en ``head`` con datos sintéticos; se borra al terminar."""
    migrator_url = read_database_url("TEST_MIGRATION_DATABASE_URL")
    app_url = read_database_url("TEST_DATABASE_URL")
    if migrator_url is None or app_url is None or not app_url.username:
        _fail(BLOCKED)
    name = f"assetcontrol_login_{uuid.uuid4().hex[:12]}"

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
        yield LoginDb(name=name, app_url=app_url.set(database=name), migrator=migrator)
    finally:
        if migrator is not None:
            migrator.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def make_app(db: LoginDb, environment: str = "test") -> Flask:
    return create_app(
        Config(
            database_url=db.app_url.render_as_string(hide_password=False),
            secret_key=SECRET_KEY,
            environment=environment,
        )
    )


@pytest.fixture(scope="module")
def login_app(login_db) -> Iterator[Flask]:
    flask_app = make_app(login_db)
    yield flask_app
    flask_app.extensions["assetcontrol.db"].engine.dispose()


@pytest.fixture
def client(login_app):
    return login_app.test_client()


@pytest.fixture(autouse=True)
def fresh_rate_limits(login_db) -> Iterator[None]:
    """T10: cada prueba parte sin contadores de ``limite_tasa`` (los límites tienen sus
    propias pruebas en ``test_rate_limits.py``); la base del módulo es compartida."""
    with login_db.migrator.begin() as conn:
        conn.execute(text("delete from limite_tasa"))
    yield


# --- Utilidades -----------------------------------------------------------------


def login(client, email: str, password: object = PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def without_request_id(response) -> dict:
    body = response.get_json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id"}
    return {k: v for k, v in body["error"].items() if k != "request_id"}


def set_cookie_headers(response) -> list[str]:
    return response.headers.getlist("Set-Cookie")


def refresh_cookie(response) -> tuple[str, str, dict[str, str]]:
    """``(nombre, valor, atributos)`` de la única cookie que emite el login."""
    headers = set_cookie_headers(response)
    assert len(headers) == 1, headers
    parsed = SimpleCookie()
    parsed.load(headers[0])
    (name, morsel), *_ = parsed.items()
    lowered = headers[0].lower()
    flags = {
        "secure": "; secure" in lowered,
        "httponly": "; httponly" in lowered,
    }
    attrs = {
        "path": morsel["path"],
        "samesite": morsel["samesite"],
        "max-age": morsel["max-age"],
        **{k: str(v) for k, v in flags.items()},
    }
    return name, morsel.value, attrs


def refresh_rows(db: LoginDb, usuario_id: uuid.UUID) -> list[dict]:
    """Filas de ``refresh_token`` de ``usuario_id`` (el migrador ve todos los tenants)."""
    with db.migrator.connect() as conn:
        return [
            dict(row._mapping)
            for row in conn.execute(
                text(
                    "select r.*, r.expira_en - now() as restante from refresh_token r "
                    "join membresia m on m.tenant_id = r.tenant_id and m.id = r.membresia_id "
                    "where m.usuario_id = :u order by r.creado_en"
                ),
                {"u": usuario_id},
            )
        ]


def refresh_count(db: LoginDb) -> int:
    with db.migrator.connect() as conn:
        return conn.scalar(text("select count(*) from refresh_token"))


def membresia_id(db: LoginDb, cuenta: Cuenta, tenant: uuid.UUID) -> uuid.UUID:
    with db.migrator.connect() as conn:
        return conn.scalar(
            text("select id from membresia where tenant_id = :t and usuario_id = :u"),
            {"t": tenant, "u": cuenta.usuario_id},
        )


def forged_token(
    *,
    sub: uuid.UUID,
    tenant: uuid.UUID,
    rol: str | None = None,
    key: bytes | None = None,
    algorithm: str = JWT_ALGORITHM,
    **extra: object,
) -> str:
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "sub": str(sub),
        "tenant": str(tenant),
        "iss": JWT_ISSUER,
        "exp": int((now + timedelta(minutes=15)).timestamp()),
        **extra,
    }
    if rol is not None:
        claims["rol"] = rol
    return jwt.encode(claims, key or derive_key(SECRET_KEY, JWT_KEY_CONTEXT), algorithm=algorithm)


def me(client, token: str | None, scheme: str = "Bearer"):
    headers = {} if token is None else {"Authorization": f"{scheme} {token}"}
    return client.get("/auth/me", headers=headers)


@pytest.fixture
def toggle(login_db):
    """Cambia ``usuario.activo`` o ``membresia.activa`` y lo restaura al terminar."""
    restore: list[tuple[str, dict]] = []

    def apply(sql: str, undo: str, params: dict) -> None:
        with login_db.migrator.begin() as conn:
            conn.execute(text(sql), params)
        restore.append((undo, params))

    yield apply
    with login_db.migrator.begin() as conn:
        for undo, params in reversed(restore):
            conn.execute(text(undo), params)


class HasherSpy:
    """Envuelve el ``PasswordHasher`` de la app: registra contra qué hash se verifica."""

    def __init__(self, hasher: argon2.PasswordHasher) -> None:
        self._hasher = hasher
        self.targets: list[str] = []

    def verify(self, target: str, password: object) -> bool:
        self.targets.append(target)
        return self._hasher.verify(target, password)

    def __getattr__(self, name: str):
        return getattr(self._hasher, name)


@pytest.fixture
def hasher_spy(login_app, monkeypatch) -> HasherSpy:
    with login_app.app_context():
        passwords = get_passwords()
    spy = HasherSpy(passwords._hasher)
    monkeypatch.setattr(passwords, "_hasher", spy)
    return spy


# --- Login correcto ---------------------------------------------------------------


def test_login_issues_an_access_token_with_the_tenant_and_the_membership_role(client):
    response = login(client, ADMIN_A.email)

    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 15 * 60
    assert body["rol"] == "admin"
    assert body["usuario"] == {
        "id": str(ADMIN_A.usuario_id),
        "email": ADMIN_A.email,
        "nombre": ADMIN_A.nombre,
    }
    assert body["tenant"] == {"id": str(TENANT_A), "nombre": NOMBRE_A}
    claims = decode_access_token(SECRET_KEY, body["access_token"])
    assert claims.sub == ADMIN_A.usuario_id
    assert claims.tenant == TENANT_A


def test_login_reads_the_role_of_a_contador_from_membresia(client):
    body = login(client, CONTADOR_A.email).get_json()

    assert body["rol"] == "contador"
    raw = jwt.decode(
        body["access_token"],
        derive_key(SECRET_KEY, JWT_KEY_CONTEXT),
        algorithms=[JWT_ALGORITHM],
        issuer=JWT_ISSUER,
    )
    assert raw["rol"] == "contador"
    assert raw["tenant"] == str(TENANT_A)


def test_login_normalizes_the_email(client):
    response = login(client, "  Admin.A6@Ejemplo.TEST ")

    assert response.status_code == 200


def test_login_with_one_active_and_one_inactive_membership_enters_the_active_one(client):
    body = login(client, UNA_ACTIVA_UNA_NO.email).get_json()

    assert body["tenant"]["id"] == str(TENANT_B)
    assert body["rol"] == "contador"


def test_login_sets_the_refresh_cookie_with_tenant_and_secret(client, login_db):
    response = login(client, ADMIN_A.email)

    name, value, attrs = refresh_cookie(response)
    assert name == "__Secure-refresh"
    assert attrs["secure"] == "True"
    assert attrs["httponly"] == "True"
    assert attrs["samesite"] == "Lax"
    assert attrs["path"] == "/auth"
    assert attrs["max-age"] == str(7 * 24 * 3600)
    tenant, secret = value.split(".", 1)
    assert uuid.UUID(tenant) == TENANT_A
    assert len(secret) >= 43  # 32 bytes en base64url
    assert secret not in response.get_data(as_text=True)


def test_login_stores_only_the_double_hash_of_the_refresh_secret(client, login_db):
    response = login(client, CONTADOR_A.email)
    _, value, _ = refresh_cookie(response)
    secret = value.split(".", 1)[1]

    rows = refresh_rows(login_db, CONTADOR_A.usuario_id)
    row = rows[-1]
    assert bytes(row["token_hash"]) == token_storage_hash(secret)
    assert row["tenant_id"] == TENANT_A
    assert row["membresia_id"] == membresia_id(login_db, CONTADOR_A, TENANT_A)
    assert row["usado_en"] is None
    assert row["revocado_en"] is None
    assert timedelta(days=7) - timedelta(minutes=1) < row["restante"] <= timedelta(days=7)


def test_each_login_starts_a_new_refresh_family(client, login_db):
    login(client, ADMIN_B.email)
    login(client, ADMIN_B.email)

    rows = refresh_rows(login_db, ADMIN_B.usuario_id)
    assert len(rows) >= 2
    assert rows[-1]["familia_id"] != rows[-2]["familia_id"]
    assert rows[-1]["token_hash"] != rows[-2]["token_hash"]


def test_login_response_and_refresh_cookie_are_different_for_two_logins(client):
    first = login(client, ADMIN_A.email)
    second = login(client, ADMIN_A.email)

    assert refresh_cookie(first)[1] != refresh_cookie(second)[1]


# --- Respuesta genérica (A10) -------------------------------------------------------


GENERIC_CASES = {
    "contrasena_mala": (ADMIN_A.email, WRONG_PASSWORD),
    "cuenta_inexistente": (NO_EXISTE, PASSWORD),
    "usuario_inactivo": (INACTIVO_A.email, PASSWORD),
    "membresia_inactiva": (MEMBRESIA_INACTIVA_A.email, PASSWORD),
    "varias_membresias_activas": (DOS_MEMBRESIAS.email, PASSWORD),
    "contrasena_sobre_el_maximo": (ADMIN_A.email, "x" * (PASSWORD_MAX_LENGTH + 1)),
    "inexistente_sobre_el_maximo": (NO_EXISTE, "x" * (PASSWORD_MAX_LENGTH + 1)),
    "contrasena_con_sustituto": (ADMIN_A.email, "Clave-\ud800-Sintetica"),
    "inexistente_con_sustituto": (NO_EXISTE, "Clave-\ud800-Sintetica"),
    "contrasena_vacia": (ADMIN_A.email, ""),
    "email_con_sustituto": ("admin\ud800.a6@ejemplo.test", PASSWORD),
    "email_con_nul": ("admin\x00.a6@ejemplo.test", PASSWORD),
    "email_vacio": ("", PASSWORD),
    "email_comodin": ("%", PASSWORD),
    # N1/H3 (T9): mayúscula que solo PostgreSQL conoce; mismo genérico, nunca 500.
    "email_mayuscula_solo_postgres": ("admin\u1c89.a6@ejemplo.test", PASSWORD),
}

EXPECTED_GENERIC = {
    "code": "credenciales_invalidas",
    "message": "Correo o contraseña incorrectos.",
}


def _raw_login(client, email: str, password: str):
    # ensure_ascii: el sustituto suelto viaja como escape \ud800 (JSON válido).
    payload = json.dumps({"email": email, "password": password}, ensure_ascii=True)
    return client.post("/auth/login", data=payload, content_type="application/json")


@pytest.mark.parametrize("case", sorted(GENERIC_CASES))
def test_every_failed_login_gives_the_same_generic_response(client, login_db, case):
    email, password = GENERIC_CASES[case]
    before = refresh_count(login_db)

    response = _raw_login(client, email, password)

    assert response.status_code == 401
    assert without_request_id(response) == EXPECTED_GENERIC
    assert set_cookie_headers(response) == []
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert refresh_count(login_db) == before


def test_failed_logins_differ_only_in_request_id(client):
    bodies = {
        case: (response.status_code, without_request_id(response), sorted(response.headers.keys()))
        for case, (email, password) in GENERIC_CASES.items()
        for response in [_raw_login(client, email, password)]
    }

    assert len({json.dumps(value, sort_keys=True) for value in bodies.values()}) == 1


ARGON2_CASES = (
    "contrasena_mala",
    "cuenta_inexistente",
    "usuario_inactivo",
    "membresia_inactiva",
    "varias_membresias_activas",
)


@pytest.mark.parametrize("case", ARGON2_CASES)
def test_every_login_verifies_argon2_once_with_the_same_parameters(client, hasher_spy, case):
    """A10 sin reloj: con y sin cuenta, exactamente una verificación del mismo costo."""
    email, password = GENERIC_CASES[case]

    _raw_login(client, email, password)

    assert len(hasher_spy.targets) == 1
    assert argon2.extract_parameters(hasher_spy.targets[0]) == ARGON2_TEST_PARAMS


def test_a_missing_account_is_verified_against_the_dummy_hash(client, login_app, hasher_spy):
    login(client, NO_EXISTE)

    with login_app.app_context():
        dummy = get_passwords()._dummy_hash
    assert hasher_spy.targets == [dummy]


def test_a_correct_login_also_verifies_exactly_once(client, hasher_spy):
    assert login(client, ADMIN_A.email).status_code == 200
    assert len(hasher_spy.targets) == 1


@pytest.mark.parametrize(
    "case",
    [
        "contrasena_sobre_el_maximo",
        "inexistente_sobre_el_maximo",
        "contrasena_con_sustituto",
        "inexistente_con_sustituto",
    ],
)
def test_fast_false_of_verify_skips_argon2_with_and_without_account(client, hasher_spy, case):
    email, password = GENERIC_CASES[case]

    response = _raw_login(client, email, password)

    assert response.status_code == 401
    assert hasher_spy.targets == []


def test_multiple_active_memberships_fail_closed_and_log_without_the_email(client, caplog):
    with caplog.at_level(logging.WARNING):
        response = login(client, DOS_MEMBRESIAS.email)

    assert response.status_code == 401
    assert DOS_MEMBRESIAS.email not in caplog.text
    assert PASSWORD not in caplog.text
    assert "varias membresías activas" in caplog.text


# --- Rol y activa desde membresia (no de buscar_login) -------------------------------


def _stale_buscar_login(cuenta: Cuenta, tenant: uuid.UUID, rol: str):
    hasher = argon2.PasswordHasher.from_parameters(ARGON2_TEST_PARAMS)
    stored = hasher.hash(PASSWORD)

    def fake(email: str) -> list[LoginRow]:
        return [
            LoginRow(
                usuario_id=cuenta.usuario_id,
                password_hash=stored,
                activo=True,
                tenant_id=tenant,
                rol=rol,
            )
        ]

    return fake


def test_login_rereads_activa_from_membresia_under_the_tenant(client, login_db, monkeypatch):
    # buscar_login "desactualizado" (carrera): dice activa, la base dice inactiva.
    monkeypatch.setattr(
        service, "buscar_login", _stale_buscar_login(MEMBRESIA_INACTIVA_A, TENANT_A, "admin")
    )
    before = refresh_count(login_db)

    response = login(client, MEMBRESIA_INACTIVA_A.email)

    assert response.status_code == 401
    assert without_request_id(response) == EXPECTED_GENERIC
    assert refresh_count(login_db) == before


def test_login_rereads_usuario_activo_under_the_tenant(client, login_db, monkeypatch):
    monkeypatch.setattr(service, "buscar_login", _stale_buscar_login(INACTIVO_A, TENANT_A, "admin"))

    response = login(client, INACTIVO_A.email)

    assert response.status_code == 401
    assert without_request_id(response) == EXPECTED_GENERIC


def test_login_takes_the_role_from_membresia_not_from_buscar_login(client, monkeypatch):
    monkeypatch.setattr(service, "buscar_login", _stale_buscar_login(CONTADOR_A, TENANT_A, "admin"))

    body = login(client, CONTADOR_A.email).get_json()

    assert body["rol"] == "contador"


def test_login_with_a_tenant_where_there_is_no_membership_is_rejected(client, monkeypatch):
    # Una fila con el tenant B para un usuario solo de A: bajo RLS de B no hay membresía.
    monkeypatch.setattr(service, "buscar_login", _stale_buscar_login(ADMIN_A, TENANT_B, "admin"))

    response = login(client, ADMIN_A.email)

    assert response.status_code == 401


# --- Forma del cuerpo y política HTTP por ruta (B5 de T4) ---------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"data": "no es json", "content_type": "application/json"},
        {"data": "email=a&password=b", "content_type": "application/x-www-form-urlencoded"},
        {"json": ["lista"]},
        {"json": {"email": ADMIN_A.email}},
        {"json": {"password": PASSWORD}},
        {"json": {"email": 1, "password": PASSWORD}},
        {"json": {"email": ADMIN_A.email, "password": None}},
    ],
)
def test_malformed_login_body_is_a_400_without_touching_accounts(client, hasher_spy, kwargs):
    response = client.post("/auth/login", **kwargs)

    assert response.status_code == 400
    assert without_request_id(response)["code"] == "solicitud_invalida"
    assert hasher_spy.targets == []
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("path", ["/auth/login", "/auth/me"])
def test_auth_routes_reject_bodies_over_4_kb(client, path):
    big = {"email": ADMIN_A.email, "password": "x" * AUTH_MAX_BODY_BYTES}
    method = client.post if path == "/auth/login" else client.get

    response = method(path, json=big)

    assert response.status_code == 413
    assert without_request_id(response)["code"] == "cuerpo_demasiado_grande"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_login_success_carries_no_store_and_no_referrer(client):
    response = login(client, ADMIN_A.email)

    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"


def test_me_carries_no_store_and_no_referrer(client):
    token = login(client, ADMIN_A.email).get_json()["access_token"]

    for response in (me(client, token), me(client, None)):
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Referrer-Policy"] == "no-referrer"


def test_login_is_post_only(client):
    response = client.get("/auth/login")

    assert response.status_code == 405
    assert response.headers["Cache-Control"] == "no-store"


def test_me_is_get_only(client):
    assert client.post("/auth/me").status_code == 405


# --- GET /auth/me -------------------------------------------------------------------


def test_me_returns_the_user_tenant_and_role_from_membresia(client):
    token = login(client, CONTADOR_A.email).get_json()["access_token"]

    response = me(client, token)

    assert response.status_code == 200
    assert response.get_json() == {
        "usuario": {
            "id": str(CONTADOR_A.usuario_id),
            "email": CONTADOR_A.email,
            "nombre": CONTADOR_A.nombre,
        },
        "tenant": {"id": str(TENANT_A), "nombre": NOMBRE_A},
        "rol": "contador",
    }


EXPECTED_NO_AUTH = {"code": "no_autenticado", "message": "Debes iniciar sesión."}


def _none_token() -> str:
    def part(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    now = datetime.now(UTC)
    claims = {
        "sub": str(ADMIN_A.usuario_id),
        "tenant": str(TENANT_A),
        "iss": JWT_ISSUER,
        "exp": int((now + timedelta(minutes=5)).timestamp()),
    }
    return f"{part({'alg': 'none', 'typ': 'JWT'})}.{part(claims)}."


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "Bearer",
        "Bearer ",
        "Basic dXN1YXJpbzpjbGF2ZQ==",
        "Bearer no-es-un-jwt",
        "Bearer " + "x" * 50,
    ],
)
def test_me_without_a_valid_bearer_is_401(client, header):
    headers = {} if header is None else {"Authorization": header}

    response = client.get("/auth/me", headers=headers)

    assert response.status_code == 401
    assert without_request_id(response) == EXPECTED_NO_AUTH


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(lambda: _none_token(), id="alg-none"),
        pytest.param(
            lambda: forged_token(sub=ADMIN_A.usuario_id, tenant=TENANT_A, key=b"k" * 32),
            id="otra-clave",
        ),
        pytest.param(
            lambda: forged_token(
                sub=ADMIN_A.usuario_id,
                tenant=TENANT_A,
                exp=int((datetime.now(UTC) - timedelta(minutes=1)).timestamp()),
            ),
            id="vencido",
        ),
        pytest.param(
            lambda: forged_token(sub=ADMIN_A.usuario_id, tenant=TENANT_A, iss="otro"),
            id="iss-ajeno",
        ),
        pytest.param(
            lambda: forged_token(sub=ADMIN_A.usuario_id, tenant=uuid.uuid4()),
            id="tenant-inexistente",
        ),
        pytest.param(
            lambda: forged_token(sub=uuid.uuid4(), tenant=TENANT_A), id="usuario-inexistente"
        ),
    ],
)
def test_me_rejects_invalid_tokens(client, token):
    response = me(client, token())

    assert response.status_code == 401
    assert without_request_id(response) == EXPECTED_NO_AUTH


def test_token_with_the_tenant_of_another_tenant_does_not_access(client):
    # Firmado con la clave real: usuario de A con el tenant de B.
    token = forged_token(sub=ADMIN_A.usuario_id, tenant=TENANT_B, rol="admin")

    response = me(client, token)

    assert response.status_code == 401
    assert without_request_id(response) == EXPECTED_NO_AUTH


def test_forged_role_in_the_claim_does_not_raise_privileges(client):
    token = forged_token(sub=CONTADOR_A.usuario_id, tenant=TENANT_A, rol="admin")

    response = me(client, token)

    assert response.status_code == 200
    assert response.get_json()["rol"] == "contador"


def test_inactive_membership_does_not_access_with_a_valid_jwt(client, toggle):
    token = login(client, ADMIN_A.email).get_json()["access_token"]
    assert me(client, token).status_code == 200

    toggle(
        "update membresia set activa = false where usuario_id = :u",
        "update membresia set activa = true where usuario_id = :u",
        {"u": ADMIN_A.usuario_id},
    )

    response = me(client, token)
    assert response.status_code == 401
    assert without_request_id(response) == EXPECTED_NO_AUTH


def test_inactive_user_does_not_access_with_a_valid_jwt(client, toggle):
    token = login(client, CONTADOR_A.email).get_json()["access_token"]

    toggle(
        "update usuario set activo = false where id = :u",
        "update usuario set activo = true where id = :u",
        {"u": CONTADOR_A.usuario_id},
    )

    assert me(client, token).status_code == 401


def test_role_change_after_issuing_the_token_is_seen_on_the_next_request(client, toggle):
    token = login(client, ADMIN_A.email).get_json()["access_token"]

    toggle(
        "update membresia set rol = 'contador' where usuario_id = :u",
        "update membresia set rol = 'admin' where usuario_id = :u",
        {"u": ADMIN_A.usuario_id},
    )

    assert me(client, token).get_json()["rol"] == "contador"


def test_token_of_a_user_with_inactive_membership_never_accesses(client):
    token = forged_token(sub=MEMBRESIA_INACTIVA_A.usuario_id, tenant=TENANT_A, rol="admin")

    assert me(client, token).status_code == 401


def test_token_of_a_user_with_two_memberships_only_reaches_the_claimed_tenant(client):
    token_b = forged_token(sub=DOS_MEMBRESIAS.usuario_id, tenant=TENANT_B)

    body = me(client, token_b).get_json()

    assert body["tenant"]["id"] == str(TENANT_B)


# --- A21: cookie Secure salvo development explícito ----------------------------------


@pytest.mark.parametrize(
    ("environment", "name", "secure"),
    [
        ("production", "__Secure-refresh", True),
        ("staging", "__Secure-refresh", True),
        ("test", "__Secure-refresh", True),
        ("development", "refresh", False),
    ],
)
def test_refresh_cookie_is_secure_unless_development_is_explicit(
    login_db, environment, name, secure
):
    flask_app = make_app(login_db, environment)
    try:
        response = login(flask_app.test_client(), ADMIN_A.email)
    finally:
        flask_app.extensions["assetcontrol.db"].engine.dispose()

    assert response.status_code == 200
    cookie_name, _, attrs = refresh_cookie(response)
    assert cookie_name == name
    assert attrs["secure"] == str(secure)
    assert attrs["httponly"] == "True"
    assert attrs["samesite"] == "Lax"
    assert attrs["path"] == "/auth"


# --- Secretos fuera de los logs ------------------------------------------------------


def test_login_and_me_do_not_log_passwords_tokens_or_hashes(client, caplog):
    with caplog.at_level(logging.DEBUG):
        ok = login(client, ADMIN_A.email)
        login(client, ADMIN_A.email, WRONG_PASSWORD)
        login(client, NO_EXISTE)
        token = ok.get_json()["access_token"]
        me(client, token)

    secret = refresh_cookie(ok)[1].split(".", 1)[1]
    for value in (PASSWORD, WRONG_PASSWORD, token, secret, token_storage_hash(secret).hex()):
        assert value not in caplog.text


# --- M1 de T6-endurecimiento: filas de SQLAlchemy fuera de los logs -------------------

SQLALCHEMY_LOGGERS = ("sqlalchemy.engine", "sqlalchemy.engine.Engine", "sqlalchemy.pool")


@pytest.fixture
def sqlalchemy_debug():
    """Pone los loggers de SQLAlchemy en DEBUG **antes** de crear la app y los restaura.

    Simula a quien activa el log del engine para depurar (``logging.basicConfig`` o
    ``dictConfig`` con ``sqlalchemy.engine: DEBUG``). Restaura nivel, filtros y
    manejadores (``echo=True`` agrega uno propio a ``sqlalchemy.engine.Engine``).
    """
    saved = {}
    for name in SQLALCHEMY_LOGGERS:
        logger = logging.getLogger(name)
        saved[name] = (logger.level, list(logger.filters), list(logger.handlers))
    for name in ("sqlalchemy.engine", "sqlalchemy.pool"):
        logging.getLogger(name).setLevel(logging.DEBUG)
    yield
    for name, (level, filters, handlers) in saved.items():
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.filters[:] = filters
        for handler in logger.handlers[:]:
            if handler not in handlers:
                logger.removeHandler(handler)


def _login_secrets(ok) -> list[str]:
    secret = refresh_cookie(ok)[1].split(".", 1)[1]
    stored = token_storage_hash(secret)
    return [
        "$argon2",
        ADMIN_A.email,
        PASSWORD,
        secret,
        stored.hex(),
        repr(stored),
        ok.get_json()["access_token"],
    ]


def _leaks(secrets: list[str], *texts: str) -> list[str]:
    joined = "\n".join(texts)
    return [value for value in secrets if value in joined]


def _login_and_me(flask_app) -> object:
    client = flask_app.test_client()
    ok = login(client, ADMIN_A.email)
    assert ok.status_code == 200, ok.get_json()
    login(client, NO_EXISTE)
    me(client, ok.get_json()["access_token"])
    return ok


def test_sqlalchemy_debug_before_create_app_does_not_log_rows(
    login_db, sqlalchemy_debug, caplog, capfd
):
    flask_app = make_app(login_db)
    try:
        with caplog.at_level(logging.DEBUG):
            ok = _login_and_me(flask_app)
    finally:
        flask_app.extensions["assetcontrol.db"].engine.dispose()

    out, err = capfd.readouterr()
    assert _leaks(_login_secrets(ok), caplog.text, out, err) == []
    assert "Row " not in caplog.text
    engine = flask_app.extensions["assetcontrol.db"].engine
    assert engine.echo is False
    assert engine.pool.echo is False
    for name in ("sqlalchemy.engine", "sqlalchemy.pool"):
        assert logging.getLogger(name).level == logging.WARNING, name


def test_sqlalchemy_debug_after_create_app_still_drops_rows(
    login_db, sqlalchemy_debug, caplog, capfd
):
    # Alguien vuelve a subir el nivel (o activa echo="debug") con la app ya creada.
    flask_app = make_app(login_db)
    engine = flask_app.extensions["assetcontrol.db"].engine
    for name in ("sqlalchemy.engine", "sqlalchemy.pool"):
        logging.getLogger(name).setLevel(logging.DEBUG)
    try:
        with caplog.at_level(logging.DEBUG):
            ok = _login_and_me(flask_app)
            engine.echo = "debug"
            ok_echo = _login_and_me(flask_app)
    finally:
        engine.dispose()

    out, err = capfd.readouterr()
    secrets = _login_secrets(ok) + _login_secrets(ok_echo)
    assert _leaks(secrets, caplog.text, out, err) == []
    assert "Row " not in caplog.text + out + err
