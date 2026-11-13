"""Alembic y revisión inicial (spec 001, T6; plan.md §2 y §6).

- ``migrations/env.py`` se conecta solo con ``MIGRATION_DATABASE_URL`` (rol
  migrador), nunca con ``DATABASE_URL`` (rol de la aplicación), y falla con el
  nombre de la variable sin mostrar su valor.
- La revisión inicial es vacía y reversible: ``upgrade head`` y
  ``downgrade base`` funcionan sobre una base vacía y no crean tablas de negocio.

Las pruebas con base crean una base temporal propia con el rol migrador y la
borran al terminar: la base de pruebas compartida no recibe ``alembic_version``
(el guardián de residuos de T5 lo detectaría como cambio).
"""

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from app.config import (
    MIGRATION_URL_VAR,
    InvalidDatabaseUrlError,
    MissingConfigError,
    SameDatabaseRoleError,
    load_migration_url,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
BASELINE = "0001_baseline"

APP_URL = "postgresql+psycopg://assetcontrol_app:valor-secreto-app@db.invalid:5432/assetcontrol"
MIGRATOR_URL = "postgresql+psycopg://postgres:valor-secreto-migr@db.invalid:5432/assetcontrol"

_PUBLIC_TABLES = text(
    "select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace "
    "where n.nspname = 'public' and c.relkind in ('r', 'p', 'v', 'm', 'f') order by c.relname"
)


def alembic_config() -> AlembicConfig:
    config = AlembicConfig(str(ALEMBIC_INI))
    config.attributes["configure_logger"] = False
    return config


# --- Lectura de la URL del migrador ------------------------------------------


def test_migration_url_var_name():
    assert MIGRATION_URL_VAR == "MIGRATION_DATABASE_URL"


def test_load_migration_url_reads_the_variable():
    assert load_migration_url({MIGRATION_URL_VAR: MIGRATOR_URL}) == MIGRATOR_URL


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_migration_url_names_it_without_leaking_values(value):
    env = {"DATABASE_URL": APP_URL}
    if value is not None:
        env[MIGRATION_URL_VAR] = value

    with pytest.raises(MissingConfigError) as excinfo:
        load_migration_url(env)

    message = str(excinfo.value)
    assert MIGRATION_URL_VAR in message
    assert "valor-secreto" not in message


def test_migration_url_never_falls_back_to_database_url():
    with pytest.raises(MissingConfigError):
        load_migration_url({"DATABASE_URL": APP_URL})


def test_migration_url_with_the_app_role_is_rejected_without_leaking_values():
    same_role = APP_URL.replace("valor-secreto-app", "valor-secreto-otra")

    with pytest.raises(SameDatabaseRoleError) as excinfo:
        load_migration_url({MIGRATION_URL_VAR: same_role, "DATABASE_URL": APP_URL})

    message = str(excinfo.value)
    assert MIGRATION_URL_VAR in message
    assert "DATABASE_URL" in message
    assert "valor-secreto" not in message
    assert "assetcontrol_app" not in message


def test_migration_url_with_percent_encoded_app_role_is_rejected():
    # ``assetcontrol%5Fapp`` es ``assetcontrol_app``: el engine lo decodifica.
    encoded = APP_URL.replace("assetcontrol_app:valor-secreto-app", "assetcontrol%5Fapp:otra")

    with pytest.raises(SameDatabaseRoleError):
        load_migration_url({MIGRATION_URL_VAR: encoded, "DATABASE_URL": APP_URL})


def test_both_urls_without_username_are_rejected_as_same_role():
    env = {MIGRATION_URL_VAR: "postgresql+psycopg:///x", "DATABASE_URL": "postgresql+psycopg:///x"}
    with pytest.raises(SameDatabaseRoleError):
        load_migration_url(env)


SENTINEL = "centinela-no-debe-salir"


@pytest.mark.parametrize(
    ("database_url", "migration_url"),
    [
        (f"esto no es una url {SENTINEL}", MIGRATOR_URL),
        (f"postgresql+psycopg://assetcontrol_app:{SENTINEL}@db.invalid:puerto/x", MIGRATOR_URL),
        (APP_URL, f"esto no es una url {SENTINEL}"),
        (APP_URL, f"postgresql+psycopg://postgres:{SENTINEL}@db.invalid:puerto/x"),
    ],
)
def test_unparseable_url_fails_closed_without_leaking_values(database_url, migration_url):
    with pytest.raises(InvalidDatabaseUrlError) as excinfo:
        load_migration_url({MIGRATION_URL_VAR: migration_url, "DATABASE_URL": database_url})

    message = str(excinfo.value)
    assert MIGRATION_URL_VAR in message
    assert "DATABASE_URL" in message
    for leaked in (SENTINEL, "valor-secreto", "assetcontrol_app", "postgres", "db.invalid"):
        assert leaked not in message
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__


def test_role_check_is_skipped_without_database_url():
    assert load_migration_url({MIGRATION_URL_VAR: MIGRATOR_URL}) == MIGRATOR_URL


def test_migration_url_with_another_role_is_accepted():
    env = {MIGRATION_URL_VAR: MIGRATOR_URL, "DATABASE_URL": APP_URL}

    assert load_migration_url(env) == MIGRATOR_URL


# --- env.py y la cadena de revisiones ------------------------------------------


def test_env_py_requires_migration_database_url(monkeypatch):
    monkeypatch.delenv(MIGRATION_URL_VAR, raising=False)
    monkeypatch.setenv("DATABASE_URL", APP_URL)

    with pytest.raises(MissingConfigError) as excinfo:
        command.upgrade(alembic_config(), "head")

    message = str(excinfo.value)
    assert MIGRATION_URL_VAR in message
    assert "valor-secreto" not in message


def test_env_py_rejects_the_app_role(monkeypatch):
    monkeypatch.setenv(MIGRATION_URL_VAR, APP_URL)
    monkeypatch.setenv("DATABASE_URL", APP_URL)

    with pytest.raises(SameDatabaseRoleError) as excinfo:
        command.upgrade(alembic_config(), "head")

    assert "valor-secreto" not in str(excinfo.value)


def test_single_baseline_revision():
    script = ScriptDirectory.from_config(alembic_config())
    revisions = list(script.walk_revisions())

    assert script.get_heads() == [BASELINE]
    assert [r.revision for r in revisions] == [BASELINE]
    assert revisions[0].down_revision is None


def test_migrations_readme_documents_the_business_table_pattern():
    readme = (BACKEND_DIR / "migrations" / "README.md").read_text(encoding="utf-8")

    for fragment in (
        "ENABLE ROW LEVEL SECURITY",
        "FORCE ROW LEVEL SECURITY",
        "CREATE POLICY tenant_isolation",
        "USING",
        "WITH CHECK",
        "NULLIF(current_setting('app.tenant_id', true), '')::uuid",
        "GRANT SELECT, INSERT, UPDATE",
        "DROP POLICY tenant_isolation",
        "REVOKE",
        MIGRATION_URL_VAR,
    ):
        assert fragment in readme, fragment


# --- upgrade / downgrade sobre una base vacía ----------------------------------


@pytest.fixture
def empty_database(migration_database_url: URL) -> Iterator[URL]:
    """Base temporal vacía creada por el rol migrador; se borra al terminar."""
    name = f"assetcontrol_migr_{uuid.uuid4().hex[:12]}"
    admin = create_engine(migration_database_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    failure = None
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except SQLAlchemyError as exc:
        # Solo el nombre del error: el traceback de psycopg trae la contraseña.
        failure = (
            f"bloqueado: el rol migrador no pudo crear la base temporal ({type(exc).__name__})"
        )
    if failure is not None:
        admin.dispose()
        pytest.fail(failure, pytrace=False)
    try:
        yield migration_database_url.set(database=name)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _public_state(url: URL) -> tuple[list[str], list[str]]:
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            tables = list(conn.scalars(_PUBLIC_TABLES))
            versions = (
                list(conn.scalars(text("select version_num from alembic_version")))
                if "alembic_version" in tables
                else []
            )
    finally:
        engine.dispose()
    return tables, versions


def test_upgrade_downgrade_upgrade_on_an_empty_database(empty_database, monkeypatch):
    monkeypatch.setenv(MIGRATION_URL_VAR, empty_database.render_as_string(hide_password=False))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = alembic_config()

    assert _public_state(empty_database) == ([], [])

    command.upgrade(config, "head")
    assert _public_state(empty_database) == (["alembic_version"], [BASELINE])

    command.downgrade(config, "base")
    # Sin tablas de negocio: solo queda la tabla de control de Alembic, vacía.
    assert _public_state(empty_database) == (["alembic_version"], [])

    command.upgrade(config, "head")
    assert _public_state(empty_database) == (["alembic_version"], [BASELINE])
