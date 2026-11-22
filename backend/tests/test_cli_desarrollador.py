"""Comandos del operador para cuentas de desarrollador (spec 017, T1; R7–R10; A13, A20).

``flask crear-desarrollador``, ``flask restablecer-desarrollador`` y ``flask
desactivar-desarrollador [--reactivar]`` llaman a ``acceso.crear_desarrollador``,
``acceso.restablecer_desarrollador`` y ``acceso.cambiar_estado_desarrollador`` con el rol
migrador. Como ``test_cli_tenant.py``, corren sobre una base temporal en ``head`` con un
**migrador de prueba sin superusuario ni ``BYPASSRLS``** (``LOGIN``, ``USAGE`` en
``acceso`` y ``EXECUTE`` en las tres funciones), nunca con ``POSTGRES_USER``.
Comprueban que:

- los tres comandos funcionan con ese rol y auditan con ``desarrollador_id`` nulo;
- la contraseña llega solo por el prompt sin eco (con confirmación) o por
  ``--password-stdin``; ningún argumento ni variable de entorno la acepta;
- se aplica la política (14–128 y lista de comunes) y se guarda Argon2id;
- ni la salida ni los logs muestran la contraseña, el hash ni el correo;
- restablecer revoca todas las familias de refresh; desactivar también, y reactivar
  devuelve el acceso; un correo inexistente da un mensaje genérico;
- ese rol no puede escribir ``desarrollador`` directo (``FORCE RLS``) y el rol de la
  aplicación no ejecuta las funciones.

El ``401`` de un token vigente tras desactivar (A20) se prueba en T2 con los endpoints.
Datos sintéticos (``@ejemplo.test``).
"""

import logging
import os
import re
import secrets
import subprocess
import sys
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import argon2
import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from conftest import BLOCKED, read_database_url, role_sees_all_rows
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.pool import NullPool

from app import create_app
from app.config import Config
from app.plataforma.credenciales import (
    DEVELOPER_PASSWORD_MIN_LENGTH,
    check_developer_password_policy,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
INSUFFICIENT_PRIVILEGE = "42501"
CREATED_RE = re.compile(r"Desarrollador creado: ([0-9a-f-]{36})")
PASSWORD = "Clave-Sintetica-Dev-2026"
COMMANDS = ("crear-desarrollador", "restablecer-desarrollador", "desactivar-desarrollador")
FUNCTIONS = (
    "acceso.crear_desarrollador(text, text, text)",
    "acceso.restablecer_desarrollador(text, text)",
    "acceso.cambiar_estado_desarrollador(text, boolean)",
)


@dataclass(frozen=True)
class OperadorDb:
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
    name = f"assetcontrol_operador_dev_{suffix}"
    role = f"prueba_migrador_dev_{suffix}"
    password = secrets.token_hex(24)  # rol efímero; nunca se imprime

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
            # Lo mínimo (plan.md §2.4): USAGE en acceso y EXECUTE en las tres funciones.
            conn.execute(text(f'GRANT USAGE ON SCHEMA acceso TO "{role}"'))
            for function in FUNCTIONS:
                conn.execute(text(f'GRANT EXECUTE ON FUNCTION {function} TO "{role}"'))

        operator_url = migrator_url.set(database=name, username=role, password=password)
        app_db_url = app_url.set(database=name)
        operator = create_engine(operator_url, poolclass=NullPool)
        app = create_engine(app_db_url, poolclass=NullPool)
        engines += [operator, app]
        yield OperadorDb(
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


# --- Utilidades -----------------------------------------------------------------------


def nuevo_email() -> str:
    return f"dev.{uuid.uuid4().hex[:10]}@ejemplo.test"


def raw(url: URL) -> str:
    return url.render_as_string(hide_password=False)


def run_cli(db: OperadorDb, *args: str, input: str | None = None, migration_url=None, env=None):
    """Invoca el comando en proceso con ``MIGRATION_DATABASE_URL`` solo en el entorno."""
    app = create_app(
        Config(database_url=raw(db.app_url), secret_key="clave-de-prueba", environment="test")
    )
    environ = {
        "MIGRATION_DATABASE_URL": raw(migration_url or db.operator_url),
        "DATABASE_URL": raw(db.app_url),
    }
    environ.update(env or {})
    return app.test_cli_runner().invoke(args=list(args), env=environ, input=input)


def crear(db: OperadorDb, email: str, password: str = PASSWORD, nombre: str = "Dev Sintético"):
    """Crear por el prompt sin eco y con confirmación."""
    return run_cli(db, "crear-desarrollador", email, input=f"{nombre}\n{password}\n{password}\n")


def developer(db: OperadorDb, email: str) -> dict | None:
    with db.superuser.connect() as conn:
        row = (
            conn.execute(
                text(
                    "select id, email, nombre, password_hash, activo from desarrollador "
                    "where email = :e"
                ),
                {"e": email},
            )
            .mappings()
            .one_or_none()
        )
    return dict(row) if row is not None else None


def audit(db: OperadorDb, desarrollador_id: uuid.UUID) -> list[tuple]:
    with db.superuser.connect() as conn:
        return [
            tuple(row)
            for row in conn.execute(
                text(
                    "select accion, resultado, desarrollador_id, tenant_id from "
                    "plataforma_auditoria where objeto_id = :o order by creado_en, id"
                ),
                {"o": desarrollador_id},
            )
        ]


def counts(db: OperadorDb) -> dict[str, int]:
    with db.superuser.connect() as conn:
        return {
            table: conn.scalar(text(f"select count(*) from {table}"))  # noqa: S608
            for table in ("desarrollador", "plataforma_refresh_token", "plataforma_auditoria")
        }


def new_refresh(db: OperadorDb, desarrollador_id: uuid.UUID) -> uuid.UUID:
    token_id = uuid.uuid4()
    with db.superuser.begin() as conn:
        conn.execute(
            text(
                "insert into plataforma_refresh_token "
                "(id, desarrollador_id, familia_id, token_hash, expira_en) "
                "values (:id, :d, :f, :h, :e)"
            ),
            {
                "id": token_id,
                "d": desarrollador_id,
                "f": uuid.uuid4(),
                "h": secrets.token_bytes(32),
                "e": datetime.now(UTC) + timedelta(hours=8),
            },
        )
    return token_id


def revoked(db: OperadorDb, token_id: uuid.UUID) -> bool:
    with db.superuser.connect() as conn:
        value = conn.scalar(
            text("select revocado_en from plataforma_refresh_token where id = :i"),
            {"i": token_id},
        )
    return value is not None


def assert_no_secrets(result, *secrets_: str) -> None:
    for secret in secrets_:
        assert secret not in result.output, "un secreto apareció en la salida"
        assert secret not in (result.stderr or ""), "un secreto apareció en stderr"


def assert_denied(conn, sql: str, params: dict, fragment: str = "permission denied") -> None:
    nested = conn.begin_nested()
    with pytest.raises(DBAPIError) as excinfo:
        conn.execute(text(sql), params)
    nested.rollback()
    message = str(excinfo.value.orig)
    assert getattr(excinfo.value.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE, message
    assert fragment in message, message


# --- Política de contraseña (R8) --------------------------------------------------------


def test_developer_policy_is_14_to_128_and_rejects_common_passwords():
    from app.auth.credentials import PasswordPolicyError

    assert DEVELOPER_PASSWORD_MIN_LENGTH == 14
    check_developer_password_policy("a" * 13 + "Z")
    check_developer_password_policy("b" * 128)
    for invalid in ("a" * 13, "a" * 129, "administrador123", "ADMINISTRADOR123", "\ud800" * 20):
        with pytest.raises(PasswordPolicyError) as excinfo:
            check_developer_password_policy(invalid)
        assert invalid not in str(excinfo.value)
    with pytest.raises(PasswordPolicyError, match="entre 14 y 128"):
        check_developer_password_policy("corta-123")


# --- Precondición: el rol de la prueba no se salta RLS -------------------------------------


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


# --- crear-desarrollador ----------------------------------------------------------------


def test_crear_creates_the_developer_with_argon2id_and_audits_as_operator(operador):
    email = nuevo_email()
    before = counts(operador)

    result = crear(operador, email)

    assert result.exit_code == 0, result.output
    desarrollador_id = uuid.UUID(CREATED_RE.search(result.stdout).group(1))
    row = developer(operador, email)
    assert row["id"] == desarrollador_id
    assert (row["nombre"], row["activo"]) == ("Dev Sintético", True)
    assert row["password_hash"].startswith("$argon2id$v=19$m=19456,t=2,p=1$")
    assert argon2.PasswordHasher().verify(row["password_hash"], PASSWORD)
    assert audit(operador, desarrollador_id) == [("desarrollador_creado", "ok", None, None)]
    after = counts(operador)
    assert after == {
        **before,
        "desarrollador": before["desarrollador"] + 1,
        "plataforma_auditoria": before["plataforma_auditoria"] + 1,
    }
    assert_no_secrets(result, PASSWORD, row["password_hash"], email)


def test_crear_with_password_stdin_reads_the_line_after_the_name(operador):
    email = nuevo_email()

    result = run_cli(
        operador,
        "crear-desarrollador",
        email,
        "--password-stdin",
        input=f"Dev Stdin\n{PASSWORD}\r\n",
    )

    assert result.exit_code == 0, result.output
    row = developer(operador, email)
    assert row["nombre"] == "Dev Stdin"
    assert argon2.PasswordHasher().verify(row["password_hash"], PASSWORD)
    assert_no_secrets(result, PASSWORD, row["password_hash"])


def test_crear_normalizes_the_email_and_the_name(operador):
    local = f"Dev.Mayus.{uuid.uuid4().hex[:6]}"

    result = run_cli(
        operador,
        "crear-desarrollador",
        f"  {local}@Ejemplo.TEST ",
        input=f"  José Sintético  \n{PASSWORD}\n{PASSWORD}\n",
    )

    assert result.exit_code == 0, result.output
    row = developer(operador, f"{local.lower()}@ejemplo.test")
    assert row["nombre"] == "José Sintético"


def test_crear_with_mismatched_confirmation_creates_nothing(operador):
    before = counts(operador)

    result = run_cli(
        operador,
        "crear-desarrollador",
        nuevo_email(),
        input=f"Dev\n{PASSWORD}\n{PASSWORD}x\n",
    )

    assert result.exit_code != 0
    assert counts(operador) == before
    assert_no_secrets(result, PASSWORD)


@pytest.mark.parametrize(
    "password",
    ["corta-123", "a" * 13, "x" * 129, "administrador123"],
)
def test_crear_rejects_passwords_outside_the_policy(operador, password):
    before = counts(operador)

    result = run_cli(
        operador,
        "crear-desarrollador",
        nuevo_email(),
        "--password-stdin",
        input=f"Dev\n{password}\n",
    )

    assert result.exit_code == 1
    assert "contraseña" in result.stderr.lower()
    assert counts(operador) == before
    assert_no_secrets(result, password)


def test_crear_with_empty_stdin_creates_nothing(operador):
    before = counts(operador)

    result = run_cli(
        operador, "crear-desarrollador", nuevo_email(), "--password-stdin", input="Dev\n"
    )

    assert result.exit_code == 1
    assert "--password-stdin" in result.stderr
    assert counts(operador) == before


@pytest.mark.parametrize("email", ["sin-arroba.ejemplo.test", "dos@@ejemplo.test", "   "])
def test_crear_rejects_an_invalid_email(operador, email):
    before = counts(operador)

    result = run_cli(
        operador, "crear-desarrollador", email, "--password-stdin", input=f"Dev\n{PASSWORD}\n"
    )

    assert result.exit_code == 1
    assert "correo" in result.stderr
    assert counts(operador) == before


@pytest.mark.parametrize("nombre", ["   ", "​", "x" * 121])
def test_crear_rejects_an_invalid_name(operador, nombre):
    before = counts(operador)

    result = run_cli(
        operador,
        "crear-desarrollador",
        nuevo_email(),
        "--password-stdin",
        input=f"{nombre}\n{PASSWORD}\n",
    )

    assert result.exit_code != 0
    assert counts(operador) == before


def test_crear_with_a_repeated_email_fails_and_creates_nothing(operador):
    email = nuevo_email()
    assert crear(operador, email).exit_code == 0
    before = counts(operador)

    result = crear(operador, email)

    assert result.exit_code == 1
    assert "Ya existe un desarrollador con ese correo." in result.stderr
    assert counts(operador) == before
    assert_no_secrets(result, PASSWORD, email)


# --- restablecer-desarrollador ------------------------------------------------------------


def test_restablecer_changes_the_hash_revokes_every_family_and_audits(operador):
    email = nuevo_email()
    assert crear(operador, email).exit_code == 0
    row = developer(operador, email)
    tokens = [new_refresh(operador, row["id"]) for _ in range(2)]
    nueva = "Otra-Clave-Sintetica-2026"

    result = run_cli(operador, "restablecer-desarrollador", email, input=f"{nueva}\n{nueva}\n")

    assert result.exit_code == 0, result.output
    stored = developer(operador, email)["password_hash"]
    assert stored != row["password_hash"]
    assert argon2.PasswordHasher().verify(stored, nueva)
    assert all(revoked(operador, token) for token in tokens)
    assert [a[0] for a in audit(operador, row["id"])] == [
        "desarrollador_creado",
        "desarrollador_restablecido",
    ]
    assert all(a[2] is None for a in audit(operador, row["id"]))
    assert_no_secrets(result, nueva, stored, email)


def test_restablecer_with_password_stdin(operador):
    email = nuevo_email()
    assert crear(operador, email).exit_code == 0
    nueva = "Clave-Por-Stdin-Sintetica"

    result = run_cli(
        operador, "restablecer-desarrollador", email, "--password-stdin", input=f"{nueva}\n"
    )

    assert result.exit_code == 0, result.output
    assert argon2.PasswordHasher().verify(developer(operador, email)["password_hash"], nueva)


def test_restablecer_with_an_unknown_email_fails_generically(operador):
    before = counts(operador)
    email = nuevo_email()

    result = run_cli(
        operador, "restablecer-desarrollador", email, "--password-stdin", input=f"{PASSWORD}\n"
    )

    assert result.exit_code == 1
    assert "revisa el correo del desarrollador" in result.stderr
    assert "P0002" not in result.output
    assert counts(operador) == before
    assert_no_secrets(result, PASSWORD, email)


def test_restablecer_applies_the_policy(operador):
    email = nuevo_email()
    assert crear(operador, email).exit_code == 0
    before = developer(operador, email)["password_hash"]

    result = run_cli(
        operador, "restablecer-desarrollador", email, "--password-stdin", input="corta\n"
    )

    assert result.exit_code == 1
    assert developer(operador, email)["password_hash"] == before


# --- desactivar-desarrollador ---------------------------------------------------------------


def test_desactivar_revokes_every_family_and_reactivar_restores(operador):
    email = nuevo_email()
    assert crear(operador, email).exit_code == 0
    row = developer(operador, email)
    token = new_refresh(operador, row["id"])

    result = run_cli(operador, "desactivar-desarrollador", email)

    assert result.exit_code == 0, result.output
    assert developer(operador, email)["activo"] is False
    assert revoked(operador, token)

    result = run_cli(operador, "desactivar-desarrollador", email, "--reactivar")

    assert result.exit_code == 0, result.output
    assert developer(operador, email)["activo"] is True
    assert [a[0] for a in audit(operador, row["id"])] == [
        "desarrollador_creado",
        "desarrollador_desactivado",
        "desarrollador_reactivado",
    ]
    assert all(a[1:] == ("ok", None, None) for a in audit(operador, row["id"]))
    assert_no_secrets(result, email)


def test_desactivar_does_not_read_a_password(operador):
    email = nuevo_email()
    assert crear(operador, email).exit_code == 0

    result = run_cli(operador, "desactivar-desarrollador", email, input="")

    assert result.exit_code == 0, result.output
    assert "Contraseña" not in result.output


def test_desactivar_with_an_unknown_email_fails_generically(operador):
    before = counts(operador)

    result = run_cli(operador, "desactivar-desarrollador", nuevo_email())

    assert result.exit_code == 1
    assert "revisa el correo del desarrollador" in result.stderr
    assert counts(operador) == before


# --- Credenciales: nunca por argumento ni por entorno ---------------------------------------


@pytest.mark.parametrize("name", COMMANDS)
def test_commands_take_only_the_email_and_flags(name):
    app = create_app(
        Config(database_url="postgresql+psycopg://x@h/db", secret_key="k", environment="test")
    )
    params = app.cli.commands[name].params
    arguments = [p.name for p in params if p.param_type_name == "argument"]
    options = [p for p in params if p.param_type_name == "option"]

    assert arguments == ["email"]
    # Solo banderas: ninguna opción recibe un valor (ni contraseña, ni URL, ni rol).
    assert all(option.is_flag for option in options), name
    assert all(option.envvar is None for option in params), name


@pytest.mark.parametrize(
    "extra",
    [["--password", PASSWORD], ["--database-url", "postgresql+psycopg://otro@h/db"]],
)
def test_crear_rejects_a_password_or_url_in_argv(operador, extra):
    before = counts(operador)

    result = run_cli(operador, "crear-desarrollador", nuevo_email(), *extra, input="")

    assert result.exit_code == 2
    assert "No such option" in result.stderr
    assert counts(operador) == before


def test_a_password_in_the_environment_is_ignored(operador):
    """Con la contraseña en variables de entorno, el comando igual la pide (y falla sin ella)."""
    before = counts(operador)
    env = {
        "FLASK_CREAR_DESARROLLADOR_PASSWORD": PASSWORD,
        "FLASK_CREAR_DESARROLLADOR_PASSWORD_STDIN": PASSWORD,
        "PASSWORD": PASSWORD,
        "DESARROLLADOR_PASSWORD": PASSWORD,
    }

    result = run_cli(operador, "crear-desarrollador", nuevo_email(), input="Dev\n", env=env)

    assert result.exit_code != 0
    assert counts(operador) == before


def test_commands_require_the_migration_url_from_the_environment(operador):
    before = counts(operador)

    result = run_cli(
        operador,
        "crear-desarrollador",
        nuevo_email(),
        "--password-stdin",
        input=f"Dev\n{PASSWORD}\n",
        env={"MIGRATION_DATABASE_URL": None},
    )

    assert result.exit_code == 1
    assert "MIGRATION_DATABASE_URL" in result.stderr
    assert counts(operador) == before


def test_commands_reject_the_app_role_as_migrator(operador):
    before = counts(operador)

    result = run_cli(
        operador,
        "desactivar-desarrollador",
        nuevo_email(),
        migration_url=operador.app_url,
    )

    assert result.exit_code == 1
    assert "mismo rol" in result.stderr
    assert operador.app_url.password not in result.output
    assert counts(operador) == before


def test_command_with_the_app_role_fails_and_creates_nothing(operador):
    before = counts(operador)

    result = run_cli(
        operador,
        "crear-desarrollador",
        nuevo_email(),
        "--password-stdin",
        input=f"Dev\n{PASSWORD}\n",
        migration_url=operador.app_url,
        env={"DATABASE_URL": None},
    )

    assert result.exit_code == 1
    assert INSUFFICIENT_PRIVILEGE in result.stderr
    assert "crear_desarrollador" not in result.output
    assert counts(operador) == before
    assert_no_secrets(result, PASSWORD, operador.app_url.password)


# --- El migrador de prueba no escribe directo (A13) ------------------------------------------


def test_operator_role_cannot_write_developers_directly(operador):
    with operador.operator.connect() as conn:
        tx = conn.begin()
        try:
            assert_denied(
                conn,
                "insert into desarrollador (email, nombre, password_hash) "
                "values ('directo@ejemplo.test', 'Directo', 'h')",
                {},
            )
            assert_denied(conn, "update desarrollador set activo = false", {})
        finally:
            tx.rollback()


def test_operator_role_cannot_write_even_with_grants_under_force_rls(operador):
    with operador.superuser.connect() as conn:
        tx = conn.begin()
        try:
            role = conn.dialect.identifier_preparer.quote(operador.operator_role)
            conn.execute(
                text(
                    f"GRANT INSERT, SELECT, UPDATE ON desarrollador, plataforma_auditoria TO {role}"
                )
            )
            conn.execute(text(f"SET LOCAL ROLE {role}"))
            assert_denied(
                conn,
                "insert into desarrollador (email, nombre, password_hash) "
                "values ('directo@ejemplo.test', 'Directo', 'h')",
                {},
                fragment="row-level security",
            )
            assert_denied(
                conn,
                "insert into plataforma_auditoria (accion, resultado) "
                "values ('desarrollador_creado', 'ok')",
                {},
                fragment="row-level security",
            )
            # Bajo FORCE RLS sin política, el UPDATE no ve ninguna fila.
            assert conn.execute(text("update desarrollador set activo = false")).rowcount == 0
        finally:
            tx.rollback()


def test_app_role_cannot_execute_the_operator_functions(operador):
    with operador.app.connect() as conn:
        tx = conn.begin()
        try:
            assert_denied(
                conn,
                "select acceso.crear_desarrollador(:e, 'X', 'h')",
                {"e": nuevo_email()},
            )
            assert_denied(
                conn, "select acceso.restablecer_desarrollador(:e, 'h')", {"e": nuevo_email()}
            )
            assert_denied(
                conn,
                "select acceso.cambiar_estado_desarrollador(:e, false)",
                {"e": nuevo_email()},
            )
        finally:
            tx.rollback()


# --- Sin secretos en logs ni errores ---------------------------------------------------------


def test_nothing_secret_reaches_the_logs(operador, caplog):
    caplog.set_level(logging.DEBUG)
    email = nuevo_email()

    assert crear(operador, email).exit_code == 0
    stored = developer(operador, email)["password_hash"]
    nueva = "Clave-Nueva-Para-Logs-2026"
    assert (
        run_cli(
            operador, "restablecer-desarrollador", email, "--password-stdin", input=f"{nueva}\n"
        ).exit_code
        == 0
    )
    stored_new = developer(operador, email)["password_hash"]
    assert crear(operador, email).exit_code == 1  # error de base (duplicado)

    for secret in (PASSWORD, nueva, stored, stored_new, email):
        assert secret not in caplog.text
        for record in caplog.records:
            assert secret not in record.getMessage()
            assert secret not in str(record.args)


def test_a_database_error_is_reported_only_with_type_and_sqlstate(operador, monkeypatch):
    # Un hash con otro formato: la función falla con hash_invalido (22023).
    monkeypatch.setattr("app.cli.hash_developer_password", lambda password: "no-es-argon2")
    before = counts(operador)

    result = run_cli(
        operador,
        "crear-desarrollador",
        nuevo_email(),
        "--password-stdin",
        input=f"Dev\n{PASSWORD}\n",
    )

    assert result.exit_code == 1
    assert "22023" in result.stderr
    assert "hash_invalido" not in result.output  # sin el mensaje de PostgreSQL
    assert "crear_desarrollador" not in result.output  # sin SQL
    assert "no-es-argon2" not in result.output
    assert counts(operador) == before


# --- De punta a punta: ``flask crear-desarrollador`` en un proceso real -----------------------


def test_flask_crear_desarrollador_in_a_real_process(operador):
    """Proceso real con la contraseña por stdin y credenciales de base solo por entorno."""
    email = nuevo_email()
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
    args = [sys.executable, "-m", "flask", "--app", "app", "crear-desarrollador", email]
    args.append("--password-stdin")
    assert all(PASSWORD not in arg for arg in args)

    completed = subprocess.run(  # noqa: S603 - argumentos fijos de la prueba
        args,
        cwd=BACKEND_DIR,
        env=env,
        input=f"Dev Proceso\n{PASSWORD}\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr[-2000:]
    assert CREATED_RE.search(completed.stdout)
    row = developer(operador, email)
    assert argon2.PasswordHasher().verify(row["password_hash"], PASSWORD)
    output = completed.stdout + completed.stderr
    for secret in (PASSWORD, row["password_hash"], email, operador.operator_url.password):
        assert secret not in output
