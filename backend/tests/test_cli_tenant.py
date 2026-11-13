"""Pruebas del comando del operador ``flask create-tenant`` (spec 002, T5; R6; plan.md §2.3).

El comando crea un ``tenant`` y la primera invitación ``admin`` llamando a
``acceso.crear_tenant`` con el rol migrador. Estas pruebas corren sobre una base
temporal migrada a ``head`` y con un **migrador de prueba sin superusuario ni
``BYPASSRLS``** creado aquí (``LOGIN`` y solo ``USAGE`` en ``acceso`` y ``EXECUTE``
en ``crear_tenant``), nunca con ``POSTGRES_USER`` (I11, Q5): así la prueba no pasa
por ser superusuario. Comprueban que:

- (a) el comando funciona con ese rol: tenant e invitación ``admin``, ``creada_por``
  NULL, sin usar, 24 h, email normalizado, en una transacción;
- la base guarda solo ``sha256(sha256(token))`` (I1): ni el token ni la clave
  quedan en ninguna columna, y el enlace se muestra una sola vez por la salida
  estándar, nunca en stderr ni en los logs;
- (b) ese rol no puede hacer ``INSERT`` directo en ``tenant``/``invitacion``, ni
  siquiera con ``GRANT INSERT`` (``FORCE RLS`` sin política para él);
- (c) el rol de la aplicación no puede ejecutar ``crear_tenant`` (tampoco a través
  del comando);
- las credenciales del migrador llegan solo por ``MIGRATION_DATABASE_URL``: el
  comando no acepta URL, contraseña ni rol por argumentos;
- un error de base se informa solo con su tipo y ``sqlstate``, sin enlace.

El rol de prueba y la base temporal se borran al terminar (el guardián de
residuos de ``conftest.py`` falla si queda un rol ``prueba_*``). Datos
sintéticos (``@ejemplo.test``); nunca datos de la clínica.
"""

import hashlib
import logging
import os
import re
import secrets
import subprocess
import sys
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from conftest import BLOCKED, read_database_url, role_sees_all_rows
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.pool import NullPool

from app import create_app
from app.auth.credentials import token_key, token_storage_hash
from app.config import Config

BACKEND_DIR = Path(__file__).resolve().parent.parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"

INSUFFICIENT_PRIVILEGE = "42501"
INVALID_PARAMETER = "22023"
LINK_PREFIX = "/invitacion#"
LINK_RE = re.compile(r"/invitacion#([A-Za-z0-9_-]+)")
TENANT_RE = re.compile(r"Tenant creado: ([0-9a-f-]{36})")


@dataclass(frozen=True)
class OperadorDb:
    """Base temporal en ``head`` y sus roles."""

    name: str
    superuser: Engine  # solo para contar y verificar (ve todas las filas bajo FORCE RLS)
    app: Engine
    app_url: URL
    operator: Engine
    operator_url: URL
    operator_role: str


def _fail(message: str) -> None:
    pytest.fail(message, pytrace=False)


def _alembic_config() -> AlembicConfig:
    config = AlembicConfig(str(ALEMBIC_INI))
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="module")
def operador(database_residue_guard) -> Iterator[OperadorDb]:
    """Base temporal migrada y un migrador de prueba sin superusuario ni ``BYPASSRLS``."""
    migrator_url = read_database_url("TEST_MIGRATION_DATABASE_URL")
    app_url = read_database_url("TEST_DATABASE_URL")
    if migrator_url is None or app_url is None or not app_url.username:
        _fail(BLOCKED)
    suffix = uuid.uuid4().hex[:12]
    name = f"assetcontrol_operador_{suffix}"
    role = f"prueba_migrador_{suffix}"
    # Contraseña aleatoria de un rol efímero; nunca se imprime.
    password = secrets.token_hex(24)

    admin = create_engine(migrator_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    failure = None
    created_role = False
    try:
        with admin.connect() as conn:
            if not role_sees_all_rows(conn):
                failure = (
                    "bloqueado: el rol de TEST_MIGRATION_DATABASE_URL debe ser superusuario "
                    "para crear el migrador de prueba y verificar bajo FORCE RLS"
                )
            else:
                conn.execute(text(f'CREATE DATABASE "{name}"'))
                conn.execute(
                    text(
                        f'CREATE ROLE "{role}" LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB '
                        f"NOCREATEROLE NOREPLICATION NOINHERIT PASSWORD '{password}'"
                    )
                )
                created_role = True
    except SQLAlchemyError as exc:
        failure = f"bloqueado: el rol migrador no pudo preparar la base ({type(exc).__name__})"

    engines: list[Engine] = []
    try:
        if failure is not None:
            _fail(failure)
        superuser_db = migrator_url.set(database=name)
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("MIGRATION_DATABASE_URL", superuser_db.render_as_string(hide_password=False))
            mp.delenv("DATABASE_URL", raising=False)
            mp.setenv("APP_DB_USER", app_url.username)
            command.upgrade(_alembic_config(), "head")

        superuser = create_engine(superuser_db, poolclass=NullPool)
        engines.append(superuser)
        with superuser.begin() as conn:
            # Lo mínimo de la spec (plan.md §2.3): USAGE en acceso y EXECUTE en crear_tenant.
            conn.execute(text(f'GRANT USAGE ON SCHEMA acceso TO "{role}"'))
            conn.execute(
                text(f'GRANT EXECUTE ON FUNCTION acceso.crear_tenant(text, text, text) TO "{role}"')
            )

        operator_url = migrator_url.set(database=name, username=role, password=password)
        app_db_url = app_url.set(database=name)
        operator = create_engine(operator_url, poolclass=NullPool)
        app = create_engine(app_db_url, poolclass=NullPool)
        engines += [operator, app]
        yield OperadorDb(
            name=name,
            superuser=superuser,
            app=app,
            app_url=app_db_url,
            operator=operator,
            operator_url=operator_url,
            operator_role=role,
        )
    finally:
        for engine in engines:
            engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            if created_role:
                conn.execute(text(f'DROP ROLE IF EXISTS "{role}"'))
        admin.dispose()


# --- Utilidades -----------------------------------------------------------------


def nuevo_email(prefix: str = "admin") -> str:
    return f"{prefix}.{uuid.uuid4().hex[:10]}@ejemplo.test"


def nuevo_nombre() -> str:
    return f"Clínica sintética {uuid.uuid4().hex[:8]}"


def raw(url: URL) -> str:
    return url.render_as_string(hide_password=False)


def run_cli(db: OperadorDb, *args: str, migration_url: URL | None = None, env=None):
    """Invoca el comando en proceso con ``MIGRATION_DATABASE_URL`` solo en el entorno."""
    app = create_app(
        Config(database_url=raw(db.app_url), secret_key="clave-de-prueba", environment="test")
    )
    environ = {
        "MIGRATION_DATABASE_URL": raw(migration_url or db.operator_url),
        "DATABASE_URL": raw(db.app_url),
    }
    environ.update(env or {})
    return app.test_cli_runner().invoke(args=list(args), env=environ)


def link_token(output: str) -> str:
    tokens = LINK_RE.findall(output)
    assert len(tokens) == 1, "el enlace debe mostrarse exactamente una vez"
    return tokens[0]


def counts(db: OperadorDb) -> dict[str, int]:
    """Filas de ``tenant`` e ``invitacion`` vistas por el superusuario (todos los tenants)."""
    with db.superuser.connect() as conn:
        return {
            table: conn.scalar(text(f"select count(*) from {table}"))  # noqa: S608
            for table in ("tenant", "invitacion", "usuario", "membresia")
        }


def tenant_rows(db: OperadorDb, tenant_id: str) -> tuple[dict, list[dict]]:
    with db.superuser.connect() as conn:
        tenant = (
            conn.execute(text("select * from tenant where id = :id"), {"id": tenant_id})
            .mappings()
            .one()
        )
        invitaciones = (
            conn.execute(text("select * from invitacion where tenant_id = :id"), {"id": tenant_id})
            .mappings()
            .all()
        )
    return dict(tenant), [dict(row) for row in invitaciones]


def assert_denied(conn, sql: str, params: dict, fragment: str = "permission denied") -> None:
    nested = conn.begin_nested()
    with pytest.raises(DBAPIError) as excinfo:
        conn.execute(text(sql), params)
    nested.rollback()
    message = str(excinfo.value.orig)
    assert getattr(excinfo.value.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE, message
    assert fragment in message, message


# --- Precondición: el rol de la prueba no se salta RLS ------------------------------


def test_operator_role_is_not_superuser_nor_bypassrls(operador):
    with operador.operator.connect() as conn:
        row = conn.execute(
            text(
                "select current_user, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb "
                "from pg_roles where rolname = current_user"
            )
        ).one()
        assert not role_sees_all_rows(conn)
    assert tuple(row) == (operador.operator_role, False, False, False, False)


# --- (a) El comando funciona con el migrador sin superusuario -------------------------


def test_create_tenant_creates_the_tenant_and_a_24h_admin_invitation(operador):
    nombre, email = nuevo_nombre(), nuevo_email()
    before = counts(operador)

    result = run_cli(operador, "create-tenant", nombre, email)

    assert result.exit_code == 0, result.output
    tenant_id = TENANT_RE.search(result.stdout).group(1)
    token = link_token(result.stdout)
    tenant, invitaciones = tenant_rows(operador, tenant_id)
    assert tenant["nombre"] == nombre
    assert len(invitaciones) == 1
    inv = invitaciones[0]
    assert (inv["email"], inv["rol"], inv["creada_por"], inv["usada_en"]) == (
        email,
        "admin",
        None,
        None,
    )
    # Misma transacción: now() de crear_tenant es el creado_en del tenant (Q3: 24 h).
    with operador.superuser.connect() as conn:
        exact_24h = conn.scalar(
            text(
                "select i.expira_en = t.creado_en + interval '24 hours' "
                "from invitacion i join tenant t on t.id = i.tenant_id where t.id = :id"
            ),
            {"id": tenant_id},
        )
    assert exact_24h is True
    after = counts(operador)
    assert after == {
        **before,
        "tenant": before["tenant"] + 1,
        "invitacion": before["invitacion"] + 1,
    }
    assert bytes(inv["token_hash"]) == token_storage_hash(token)


def test_the_invitation_stores_only_the_double_hash_of_the_token(operador):
    result = run_cli(operador, "create-tenant", nuevo_nombre(), nuevo_email())

    assert result.exit_code == 0, result.output
    token = link_token(result.stdout)
    key = token_key(token)
    tenant_id = TENANT_RE.search(result.stdout).group(1)
    tenant, (inv,) = tenant_rows(operador, tenant_id)
    stored = bytes(inv["token_hash"])

    assert stored == hashlib.sha256(bytes.fromhex(key)).digest()
    assert stored != hashlib.sha256(token.encode()).digest()  # no es sha256(token)
    assert stored != bytes.fromhex(key)
    for row in (tenant, inv):
        for value in row.values():
            if isinstance(value, memoryview):
                value = bytes(value)
            rendered = value.hex() if isinstance(value, bytes) else str(value)
            assert token not in rendered
            assert key not in rendered
    # El enlace sirve: la aplicación lo valida con la clave derivada del token.
    with operador.app.begin() as conn:
        assert conn.scalar(text("select acceso.validar_invitacion(:c)"), {"c": key}) is True


def test_the_link_goes_only_to_stdout_once_and_never_to_logs(operador, caplog):
    caplog.set_level(logging.DEBUG)

    result = run_cli(operador, "create-tenant", nuevo_nombre(), nuevo_email())

    assert result.exit_code == 0, result.output
    token = link_token(result.stdout)
    assert result.stdout.count(token) == 1
    assert LINK_PREFIX + token in result.stdout
    assert token not in result.stderr
    key = token_key(token)
    for record in caplog.records:
        message = record.getMessage()
        assert token not in message and key not in message
        assert token not in str(record.args) and key not in str(record.args)
    assert token not in caplog.text and key not in caplog.text


def test_create_tenant_normalizes_the_email(operador):
    local = f"Admin.Mayus.{uuid.uuid4().hex[:6]}"

    result = run_cli(operador, "create-tenant", nuevo_nombre(), f"  {local}@Ejemplo.TEST ")

    assert result.exit_code == 0, result.output
    tenant_id = TENANT_RE.search(result.stdout).group(1)
    _, (inv,) = tenant_rows(operador, tenant_id)
    assert inv["email"] == f"{local.lower()}@ejemplo.test"


# --- (b) El migrador de prueba no inserta directo ------------------------------------


def test_operator_role_cannot_insert_directly(operador):
    with operador.operator.connect() as conn:
        tx = conn.begin()
        try:
            assert_denied(
                conn,
                "insert into tenant (id, nombre) values (:id, 'Directo')",
                {"id": uuid.uuid4()},
            )
            assert_denied(
                conn,
                "insert into invitacion (tenant_id, email, rol, token_hash, expira_en) "
                "values (:t, 'directo@ejemplo.test', 'admin', :h, now() + interval '1 hour')",
                {"t": uuid.uuid4(), "h": secrets.token_bytes(32)},
            )
        finally:
            tx.rollback()


def test_operator_role_cannot_insert_even_with_grant_insert_under_force_rls(operador):
    """Con ``GRANT INSERT`` y sin ``BYPASSRLS``, ``FORCE RLS`` sin política lo rechaza."""
    with operador.superuser.connect() as conn:
        tx = conn.begin()
        try:
            role = conn.dialect.identifier_preparer.quote(operador.operator_role)
            conn.execute(text(f"GRANT INSERT (id, nombre) ON tenant TO {role}"))
            conn.execute(text(f"SET LOCAL ROLE {role}"))
            assert conn.scalar(text("select current_user")) == operador.operator_role
            assert_denied(
                conn,
                "insert into tenant (id, nombre) values (:id, 'Directo')",
                {"id": uuid.uuid4()},
                fragment="row-level security",
            )
        finally:
            tx.rollback()


# --- (c) La aplicación no ejecuta crear_tenant ---------------------------------------


def test_app_role_cannot_execute_crear_tenant(operador):
    with operador.app.connect() as conn:
        tx = conn.begin()
        try:
            assert_denied(
                conn,
                "select acceso.crear_tenant(:n, :e, :c)",
                {"n": nuevo_nombre(), "e": nuevo_email(), "c": token_key("x")},
            )
        finally:
            tx.rollback()


def test_command_with_the_app_role_fails_and_creates_nothing(operador):
    before = counts(operador)

    result = run_cli(
        operador,
        "create-tenant",
        nuevo_nombre(),
        nuevo_email(),
        migration_url=operador.app_url,
        env={"DATABASE_URL": None},
    )

    assert result.exit_code == 1
    assert INSUFFICIENT_PRIVILEGE in result.stderr
    assert LINK_PREFIX not in result.output
    assert operador.app_url.password not in result.output
    assert counts(operador) == before


# --- Credenciales solo por entorno ---------------------------------------------------


def test_command_takes_only_nombre_and_email_as_arguments():
    app = create_app(
        Config(database_url="postgresql+psycopg://x@h/db", secret_key="k", environment="test")
    )
    params = app.cli.commands["create-tenant"].params

    assert [param.name for param in params] == ["nombre", "email"]
    assert all(param.param_type_name == "argument" for param in params)


@pytest.mark.parametrize(
    "extra",
    [
        ["--database-url", "postgresql+psycopg://otro@h/db"],
        ["--password", "x"],
        ["--rol", "contador"],
    ],
)
def test_command_rejects_credentials_or_role_in_argv(operador, extra):
    before = counts(operador)

    result = run_cli(operador, "create-tenant", nuevo_nombre(), nuevo_email(), *extra)

    assert result.exit_code == 2
    assert "No such option" in result.stderr  # el comando existe; la opción no
    assert LINK_PREFIX not in result.output
    assert counts(operador) == before


def test_command_requires_the_migration_url_from_the_environment(operador):
    before = counts(operador)

    result = run_cli(
        operador,
        "create-tenant",
        nuevo_nombre(),
        nuevo_email(),
        env={"MIGRATION_DATABASE_URL": None},
    )

    assert result.exit_code == 1
    assert "MIGRATION_DATABASE_URL" in result.stderr
    assert LINK_PREFIX not in result.output
    assert counts(operador) == before


def test_command_rejects_the_app_role_as_migrator(operador):
    before = counts(operador)

    result = run_cli(
        operador, "create-tenant", nuevo_nombre(), nuevo_email(), migration_url=operador.app_url
    )

    assert result.exit_code == 1
    assert "mismo rol" in result.stderr
    assert operador.app_url.password not in result.output
    assert counts(operador) == before


# --- Entradas y errores --------------------------------------------------------------


@pytest.mark.parametrize(
    ("nombre", "email"),
    [
        ("   ", "admin@ejemplo.test"),
        ("Clínica sintética", "sin-arroba.ejemplo.test"),
        ("Clínica sintética", "dos@@ejemplo.test"),
        ("Clínica sintética", "con espacio@ejemplo.test"),
        ("Clínica sintética", "@ejemplo.test"),
        ("Clínica sintética", "admin@"),
        ("Clínica sintética", "   "),
        # N1/H3 (T9): mismo normalizador que la API; antes, error de CHECK.
        ("Clínica sintética", "admin\u1c89@ejemplo.test"),
        ("Clínica sintética", "admin\x00@ejemplo.test"),
    ],
)
def test_invalid_input_creates_nothing(operador, nombre, email):
    before = counts(operador)

    result = run_cli(operador, "create-tenant", nombre, email)

    assert result.exit_code == 1
    assert "no es válido" in result.stderr or "vacío" in result.stderr
    assert LINK_PREFIX not in result.output
    assert counts(operador) == before


def test_database_error_is_reported_only_with_type_and_sqlstate(operador, monkeypatch):
    bad_key = "Z" * 64  # formato inválido: crear_tenant falla con clave_invalida (22023)
    monkeypatch.setattr("app.cli.token_key", lambda token: bad_key)
    before = counts(operador)

    result = run_cli(operador, "create-tenant", nuevo_nombre(), nuevo_email())

    assert result.exit_code == 1
    assert INVALID_PARAMETER in result.stderr
    assert bad_key not in result.output
    assert "crear_tenant" not in result.output  # sin SQL
    assert "clave_invalida" not in result.output  # sin el mensaje de PostgreSQL
    assert LINK_PREFIX not in result.output
    assert counts(operador) == before


# --- De punta a punta: ``flask create-tenant`` en un proceso real ----------------------


def test_flask_create_tenant_in_a_real_process(operador):
    """Proceso real (no pytest): ``ENVIRONMENT=development`` y credenciales solo por entorno."""
    nombre, email = nuevo_nombre(), nuevo_email()
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.endswith("DATABASE_URL") and key not in ("ENVIRONMENT", "SECRET_KEY")
    }
    env.update(
        {
            "DATABASE_URL": raw(operador.app_url),
            "MIGRATION_DATABASE_URL": raw(operador.operator_url),
            "SECRET_KEY": secrets.token_urlsafe(48),
            "ENVIRONMENT": "development",
        }
    )
    args = [sys.executable, "-m", "flask", "--app", "app", "create-tenant", nombre, email]
    assert all(operador.operator_url.password not in arg for arg in args)

    completed = subprocess.run(  # noqa: S603 - argumentos fijos de la prueba
        args, cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=120, check=False
    )

    assert completed.returncode == 0, completed.stderr[-2000:]
    token = link_token(completed.stdout)
    assert token not in completed.stderr
    assert operador.operator_url.password not in completed.stdout + completed.stderr
    tenant_id = TENANT_RE.search(completed.stdout).group(1)
    tenant, (inv,) = tenant_rows(operador, tenant_id)
    assert tenant["nombre"] == nombre
    assert bytes(inv["token_hash"]) == token_storage_hash(token)
