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

import importlib.util
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from conftest import BLOCKED, read_database_url
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
ACCESO = "0002_acceso_y_usuarios"
POLITICAS = "0003_politicas_del_dueno"
FUNCIONES = "0004_funciones_de_acceso"
MIGRATION_0002 = BACKEND_DIR / "migrations" / "versions" / "0002_acceso_y_usuarios.py"
MIGRATION_0003 = BACKEND_DIR / "migrations" / "versions" / "0003_politicas_del_dueno.py"
MIGRATION_0004 = BACKEND_DIR / "migrations" / "versions" / "0004_funciones_de_acceso.py"
APP_ROLE_VAR = "APP_DB_USER"
AUTH_TABLES = ["invitacion", "membresia", "refresh_token", "tenant", "usuario"]

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


def test_revision_chain():
    script = ScriptDirectory.from_config(alembic_config())
    revisions = list(script.walk_revisions())

    assert script.get_heads() == [FUNCIONES]
    assert [r.revision for r in revisions] == [FUNCIONES, POLITICAS, ACCESO, BASELINE]
    assert revisions[0].down_revision == POLITICAS
    assert revisions[1].down_revision == ACCESO
    assert revisions[2].down_revision == BASELINE
    assert revisions[3].down_revision is None


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


def test_migrations_readme_warns_that_downgrading_0002_destroys_data():
    readme = (BACKEND_DIR / "migrations" / "README.md").read_text(encoding="utf-8")

    for fragment in (
        "downgrade` de `0002_acceso_y_usuarios` destruye",
        "tenants",
        "usuarios",
        "refresh tokens",
        "solo para desarrollo y CI",
        "nunca sobre datos reales",
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


def _schema_exists(url: URL, name: str) -> bool:
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            return bool(
                conn.scalar(
                    text("select exists (select 1 from pg_namespace where nspname = :n)"),
                    {"n": name},
                )
            )
    finally:
        engine.dispose()


@pytest.fixture
def app_role() -> str:
    """Nombre del rol de la aplicación (usuario de ``TEST_DATABASE_URL``)."""
    url = read_database_url("TEST_DATABASE_URL")
    if url is None or not url.username:
        pytest.fail(BLOCKED, pytrace=False)
    return url.username


@pytest.fixture
def migrate_env(empty_database, app_role, monkeypatch) -> URL:
    """Entorno de Alembic apuntando a la base temporal, con el rol de la aplicación."""
    monkeypatch.setenv(MIGRATION_URL_VAR, empty_database.render_as_string(hide_password=False))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv(APP_ROLE_VAR, app_role)
    return empty_database


def test_upgrade_downgrade_upgrade_on_an_empty_database(migrate_env):
    config = alembic_config()
    with_auth = sorted(["alembic_version", *AUTH_TABLES])

    assert _public_state(migrate_env) == ([], [])
    assert not _schema_exists(migrate_env, "acceso")

    command.upgrade(config, "head")
    assert _public_state(migrate_env) == (with_auth, [FUNCIONES])
    assert _schema_exists(migrate_env, "acceso")

    command.downgrade(config, "base")
    # Solo queda la tabla de control de Alembic, vacía; el esquema acceso desaparece.
    assert _public_state(migrate_env) == (["alembic_version"], [])
    assert not _schema_exists(migrate_env, "acceso")

    command.upgrade(config, "head")
    assert _public_state(migrate_env) == (with_auth, [FUNCIONES])
    assert _schema_exists(migrate_env, "acceso")


def test_downgrade_to_baseline_removes_only_0002(migrate_env):
    config = alembic_config()
    command.upgrade(config, "head")

    command.downgrade(config, BASELINE)

    assert _public_state(migrate_env) == (["alembic_version"], [BASELINE])
    assert not _schema_exists(migrate_env, "acceso")


@pytest.mark.parametrize("value", [None, "", "   "])
def test_upgrade_requires_app_db_user_and_leaves_nothing(migrate_env, monkeypatch, value):
    if value is None:
        monkeypatch.delenv(APP_ROLE_VAR, raising=False)
    else:
        monkeypatch.setenv(APP_ROLE_VAR, value)

    with pytest.raises(RuntimeError) as excinfo:
        command.upgrade(alembic_config(), "head")

    assert APP_ROLE_VAR in str(excinfo.value)
    # DDL transaccional: el fallo revierte todo, también alembic_version.
    assert _public_state(migrate_env) == ([], [])
    assert not _schema_exists(migrate_env, "acceso")


def test_upgrade_fails_when_the_app_role_does_not_exist(migrate_env, monkeypatch):
    missing = f"rol_inexistente_{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv(APP_ROLE_VAR, missing)

    with pytest.raises(RuntimeError) as excinfo:
        command.upgrade(alembic_config(), "head")

    message = str(excinfo.value)
    assert APP_ROLE_VAR in message
    assert missing not in message
    assert _public_state(migrate_env) == ([], [])


def test_upgrade_rejects_the_migrator_as_app_role(migrate_env, monkeypatch):
    monkeypatch.setenv(APP_ROLE_VAR, migrate_env.username)

    with pytest.raises(RuntimeError) as excinfo:
        command.upgrade(alembic_config(), "head")

    assert APP_ROLE_VAR in str(excinfo.value)
    assert _public_state(migrate_env) == ([], [])


def test_upgrade_rejects_auth_owner_as_app_role(migrate_env, monkeypatch):
    monkeypatch.setenv(APP_ROLE_VAR, "auth_owner")

    with pytest.raises(RuntimeError) as excinfo:
        command.upgrade(alembic_config(), "head")

    assert APP_ROLE_VAR in str(excinfo.value)
    assert _public_state(migrate_env) == ([], [])


@pytest.fixture
def temp_role(migration_database_url, migrate_env) -> Iterator:
    """Crea roles NOLOGIN temporales de clúster y los borra al terminar.

    Antes del ``DROP ROLE`` quita, con ``DROP OWNED BY``, los GRANT y las políticas
    que la migración les haya dado en la base temporal (si no, el borrado falla).
    """
    admin = create_engine(migration_database_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    temp_db = create_engine(migrate_env, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    created: list[str] = []

    def make(name: str, attributes: str = "") -> str:
        quoted = admin.dialect.identifier_preparer.quote(name)
        failure = None
        try:
            with admin.connect() as conn:
                conn.exec_driver_sql(f"CREATE ROLE {quoted} NOLOGIN {attributes}")
        except SQLAlchemyError as exc:
            failure = (
                f"bloqueado: el rol migrador no pudo crear un rol temporal ({type(exc).__name__})"
            )
        if failure is not None:
            pytest.fail(failure, pytrace=False)
        created.append(quoted)
        return name

    try:
        yield make
    finally:
        try:
            with temp_db.connect() as conn:
                for quoted in created:
                    conn.exec_driver_sql(f"DROP OWNED BY {quoted}")
            with admin.connect() as conn:
                for quoted in created:
                    conn.exec_driver_sql(f"DROP ROLE IF EXISTS {quoted}")
        finally:
            temp_db.dispose()
            admin.dispose()


@pytest.mark.parametrize("attribute", ["BYPASSRLS", "SUPERUSER"])
def test_upgrade_rejects_an_app_role_that_skips_rls(migrate_env, monkeypatch, temp_role, attribute):
    name = temp_role(f"ac_tmp_{attribute.lower()}_{uuid.uuid4().hex[:8]}", attribute)
    monkeypatch.setenv(APP_ROLE_VAR, name)

    with pytest.raises(RuntimeError) as excinfo:
        command.upgrade(alembic_config(), "head")

    message = str(excinfo.value)
    assert APP_ROLE_VAR in message
    assert "BYPASSRLS" in message
    assert name not in message
    assert _public_state(migrate_env) == ([], [])
    assert not _schema_exists(migrate_env, "acceso")


def test_upgrade_accepts_an_app_role_with_a_colon_in_its_name(migrate_env, monkeypatch, temp_role):
    # Con op.execute(texto), ":palabra" (tras un carácter que no es de palabra) se
    # tomaría como parámetro y el error de SQLAlchemy mostraría la sentencia con el
    # nombre del rol.
    name = temp_role(f"ac_tmp_{uuid.uuid4().hex[:8]} :palabra")
    monkeypatch.setenv(APP_ROLE_VAR, name)
    config = alembic_config()

    command.upgrade(config, "head")
    try:
        engine = create_engine(migrate_env, poolclass=NullPool)
        try:
            with engine.connect() as conn:
                roles = conn.scalars(
                    text(
                        "select distinct unnest(roles)::text from pg_policies "
                        "where schemaname = 'public'"
                    )
                ).all()
        finally:
            engine.dispose()
        assert sorted(roles) == sorted([name, "auth_owner"])
    finally:
        # Quita los GRANT y políticas del rol para poder borrarlo en el teardown.
        command.downgrade(config, "base")


def test_failed_statement_does_not_leak_the_sql(migration_database_url):
    migration = _load_migration_0002()
    secret = f"centinela_{uuid.uuid4().hex[:8]}:palabra"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            with pytest.raises(RuntimeError) as excinfo:
                migration.execute_statements(conn, [f'GRANT SELECT ON no_existe TO "{secret}"'])
    finally:
        engine.dispose()

    message = str(excinfo.value)
    assert "0002" in message
    assert secret not in message
    assert "centinela" not in message
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__suppress_context__


def _load_migration_0002():
    spec = importlib.util.spec_from_file_location("migration_0002_under_test", MIGRATION_0002)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_auth_owner_fails_with_a_clear_message(migration_database_url):
    # auth_owner es de todo el clúster: no se borra en una prueba. Se comprueba el
    # mismo chequeo que usa upgrade() con un nombre de rol que no existe.
    migration = _load_migration_0002()
    assert migration.AUTH_OWNER == "auth_owner"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            migration.require_auth_owner(conn)  # existe (P0): no falla
            with pytest.raises(RuntimeError) as excinfo:
                migration.require_auth_owner(conn, name=f"auth_owner_falta_{uuid.uuid4().hex[:6]}")
    finally:
        engine.dispose()

    message = str(excinfo.value)
    assert "auth_owner" in message
    assert "01-app-role.sh" in message


# --- 0003_politicas_del_dueno (spec 002, T2) -------------------------------------


def _owner_state(url: URL) -> tuple[list[tuple[str, str]], int]:
    """Políticas TO auth_owner y número de privilegios de columna de auth_owner."""
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            policies = [
                tuple(row)
                for row in conn.execute(
                    text(
                        "select tablename, policyname from pg_policies "
                        "where schemaname = 'public' and 'auth_owner' = any(roles) "
                        "order by tablename, policyname"
                    )
                )
            ]
            grants = conn.scalar(
                text(
                    "select count(*) from information_schema.column_privileges "
                    "where table_schema = 'public' and grantee = 'auth_owner'"
                )
            )
    finally:
        engine.dispose()
    return policies, grants


def test_downgrade_0003_removes_only_the_owner_policies_and_grants(migrate_env):
    config = alembic_config()
    command.upgrade(config, "head")
    policies, grants = _owner_state(migrate_env)
    assert len(policies) == 10
    assert grants > 0

    command.downgrade(config, ACCESO)

    assert _owner_state(migrate_env) == ([], 0)
    with_auth = sorted(["alembic_version", *AUTH_TABLES])
    assert _public_state(migrate_env) == (with_auth, [ACCESO])

    command.upgrade(config, "head")
    assert _owner_state(migrate_env) == (policies, grants)


def _load_migration_0003():
    spec = importlib.util.spec_from_file_location("migration_0003_under_test", MIGRATION_0003)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0003_missing_auth_owner_fails_with_a_clear_message(migration_database_url):
    migration = _load_migration_0003()
    assert migration.AUTH_OWNER == "auth_owner"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            migration.require_auth_owner(conn)
            with pytest.raises(RuntimeError) as excinfo:
                migration.require_auth_owner(conn, name=f"auth_owner_falta_{uuid.uuid4().hex[:6]}")
    finally:
        engine.dispose()

    message = str(excinfo.value)
    assert "auth_owner" in message
    assert "01-app-role.sh" in message


def test_0003_failed_statement_does_not_leak_the_sql(migration_database_url):
    migration = _load_migration_0003()
    secret = f"centinela_{uuid.uuid4().hex[:8]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            with pytest.raises(RuntimeError) as excinfo:
                migration.execute_statements(conn, [f'GRANT SELECT ON no_existe TO "{secret}"'])
    finally:
        engine.dispose()

    message = str(excinfo.value)
    assert "0003" in message
    assert "centinela" not in message
    assert excinfo.value.__cause__ is None


# --- 0003: atributos de auth_owner (I3) y downgrade sin auth_owner (M5) ------------


@pytest.fixture
def temp_roles(migration_database_url) -> Iterator:
    """Crea roles ``prueba_atrib_*`` en el clúster; los borra y verifica que no quedan."""
    admin = create_engine(migration_database_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    quote = admin.dialect.identifier_preparer.quote
    created: list[str] = []

    def create(unsafe: str | None = None) -> str:
        # Inerte (como auth_owner) salvo, si se pide, un atributo inseguro.
        safe = {
            "SUPERUSER": "NOSUPERUSER",
            "BYPASSRLS": "NOBYPASSRLS",
            "LOGIN": "NOLOGIN",
            "CREATEROLE": "NOCREATEROLE",
            "CREATEDB": "NOCREATEDB",
            "REPLICATION": "NOREPLICATION",
        }
        options = " ".join(unsafe if key == unsafe else value for key, value in safe.items())
        name = f"prueba_atrib_{uuid.uuid4().hex[:10]}"
        with admin.connect() as conn:
            conn.exec_driver_sql(f"CREATE ROLE {quote(name)} {options}")
        created.append(name)
        return name

    def grant(role: str, member: str) -> None:
        with admin.connect() as conn:
            conn.exec_driver_sql(f"GRANT {quote(role)} TO {quote(member)}")

    create.grant = grant  # type: ignore[attr-defined]
    try:
        yield create
    finally:
        with admin.connect() as conn:
            for name in reversed(created):
                conn.exec_driver_sql(f"DROP ROLE IF EXISTS {quote(name)}")
            left = conn.scalar(
                text("select count(*) from pg_roles where rolname = any(:n)"), {"n": created}
            )
        admin.dispose()
        assert left == 0, "quedaron roles temporales de prueba"


def _check_attributes(migration_database_url, name: str | None = None) -> None:
    migration = _load_migration_0003()
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            migration.require_owner_attributes(conn, name=name)
    finally:
        engine.dispose()


def test_0003_accepts_the_real_auth_owner(migration_database_url):
    _check_attributes(migration_database_url)


def test_0003_accepts_a_role_with_safe_attributes(migration_database_url, temp_roles):
    _check_attributes(migration_database_url, temp_roles())


def _assert_unsafe_message(excinfo, name: str) -> None:
    message = str(excinfo.value)
    assert "SUPERUSER" in message and "BYPASSRLS" in message and "LOGIN" in message
    assert "membresía" in message
    assert name not in message
    assert "auth_owner" not in message


@pytest.mark.parametrize("attribute", ["SUPERUSER", "BYPASSRLS", "LOGIN"])
def test_0003_rejects_auth_owner_with_an_unsafe_attribute(
    migration_database_url, temp_roles, attribute
):
    name = temp_roles(attribute)
    with pytest.raises(RuntimeError) as excinfo:
        _check_attributes(migration_database_url, name)
    _assert_unsafe_message(excinfo, name)


def test_0003_rejects_auth_owner_that_is_member_of_another_role(migration_database_url, temp_roles):
    name, group = temp_roles(), temp_roles()
    temp_roles.grant(group, name)
    with pytest.raises(RuntimeError) as excinfo:
        _check_attributes(migration_database_url, name)
    _assert_unsafe_message(excinfo, name)


def test_0003_auth_owner_being_granted_to_another_role_is_not_unsafe(
    migration_database_url, temp_roles
):
    # Al revés (otro rol miembro de auth_owner, como el creador en Supabase, C8) no es
    # lo que mide esta comprobación: la membresía prohibida es la de auth_owner en otro.
    name, member = temp_roles(), temp_roles()
    temp_roles.grant(name, member)
    _check_attributes(migration_database_url, name)


class _FakeOp:
    def __init__(self, conn) -> None:
        self._conn = conn

    def get_bind(self):
        return self._conn


def _run_with_owner(migration_database_url, monkeypatch, step: str, owner: str) -> RuntimeError:
    """Ejecuta ``upgrade``/``downgrade`` de 0003 con otro nombre de dueño; se revierte."""
    migration = _load_migration_0003()
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                monkeypatch.setattr(migration, "op", _FakeOp(conn))
                monkeypatch.setattr(migration, "AUTH_OWNER", owner)
                with pytest.raises(RuntimeError) as excinfo:
                    getattr(migration, step)()
            finally:
                tx.rollback()
    finally:
        engine.dispose()
    return excinfo.value


def test_0003_upgrade_checks_the_auth_owner_attributes(
    migration_database_url, temp_roles, monkeypatch
):
    name = temp_roles("LOGIN")
    error = _run_with_owner(migration_database_url, monkeypatch, "upgrade", name)
    assert name not in str(error)
    assert "BYPASSRLS" in str(error)


def test_0003_downgrade_without_auth_owner_fails_with_a_clear_message(
    migration_database_url, monkeypatch
):
    missing = f"auth_owner_falta_{uuid.uuid4().hex[:6]}"
    error = _run_with_owner(migration_database_url, monkeypatch, "downgrade", missing)
    assert "01-app-role.sh" in str(error)
    assert "0003" not in str(error)  # no llegó a ejecutar ninguna sentencia


# --- 0004_funciones_de_acceso (spec 002, T3) -------------------------------------


def _load_migration_0004():
    spec = importlib.util.spec_from_file_location("migration_0004_under_test", MIGRATION_0004)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _acceso_state(url: URL) -> tuple[list[str], bool, list[str]]:
    """Funciones de acceso, CREATE de auth_owner en acceso y miembros de auth_owner."""
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            functions = list(
                conn.scalars(
                    text(
                        "select p.proname from pg_proc p join pg_namespace n "
                        "on n.oid = p.pronamespace where n.nspname = 'acceso' order by 1"
                    )
                )
            )
            can_create = bool(
                conn.scalar(
                    text(
                        "select exists (select 1 from pg_namespace where nspname = 'acceso') "
                        "and has_schema_privilege('auth_owner', 'acceso', 'CREATE')"
                    )
                )
            )
            members = list(
                conn.scalars(
                    text(
                        "select member::regrole::text from pg_auth_members "
                        "where roleid = 'auth_owner'::regrole order by 1"
                    )
                )
            )
    finally:
        engine.dispose()
    return functions, can_create, members


FUNCTION_NAMES = ["aceptar_invitacion", "buscar_login", "crear_tenant", "validar_invitacion"]


def test_0004_creates_the_functions_and_leaves_no_create_nor_membership(migrate_env):
    command.upgrade(alembic_config(), "head")
    assert _acceso_state(migrate_env) == (FUNCTION_NAMES, False, [])


def test_downgrade_0004_removes_only_the_functions(migrate_env):
    config = alembic_config()
    command.upgrade(config, "head")
    policies, grants = _owner_state(migrate_env)

    command.downgrade(config, POLITICAS)

    assert _acceso_state(migrate_env) == ([], False, [])
    assert _schema_exists(migrate_env, "acceso")
    assert _owner_state(migrate_env) == (policies, grants)
    with_auth = sorted(["alembic_version", *AUTH_TABLES])
    assert _public_state(migrate_env) == (with_auth, [POLITICAS])

    command.upgrade(config, "head")
    assert _acceso_state(migrate_env) == (FUNCTION_NAMES, False, [])


def test_0004_missing_auth_owner_fails_with_a_clear_message(migration_database_url):
    migration = _load_migration_0004()
    assert migration.AUTH_OWNER == "auth_owner"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            migration.require_auth_owner(conn)
            with pytest.raises(RuntimeError) as excinfo:
                migration.require_auth_owner(conn, name=f"auth_owner_falta_{uuid.uuid4().hex[:6]}")
    finally:
        engine.dispose()

    message = str(excinfo.value)
    assert "auth_owner" in message
    assert "01-app-role.sh" in message


def test_0004_failed_statement_does_not_leak_the_sql(migration_database_url):
    migration = _load_migration_0004()
    secret = f"centinela_{uuid.uuid4().hex[:8]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            with pytest.raises(RuntimeError) as excinfo:
                migration.execute_statements(conn, [f'GRANT SELECT ON no_existe TO "{secret}"'])
    finally:
        engine.dispose()

    message = str(excinfo.value)
    assert "0004" in message
    assert "centinela" not in message
    assert excinfo.value.__cause__ is None


def _check_attributes_0004(migration_database_url, name: str | None = None) -> None:
    migration = _load_migration_0004()
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            migration.require_owner_attributes(conn, name=name)
    finally:
        engine.dispose()


UNSAFE_ATTRIBUTES = ["SUPERUSER", "BYPASSRLS", "LOGIN", "CREATEROLE", "CREATEDB", "REPLICATION"]


def test_0004_accepts_the_real_auth_owner_and_a_safe_role(migration_database_url, temp_roles):
    _check_attributes_0004(migration_database_url)
    _check_attributes_0004(migration_database_url, temp_roles())


@pytest.mark.parametrize("attribute", UNSAFE_ATTRIBUTES)
def test_0004_rejects_auth_owner_with_an_unsafe_attribute(
    migration_database_url, temp_roles, attribute
):
    name = temp_roles(attribute)
    with pytest.raises(RuntimeError) as excinfo:
        _check_attributes_0004(migration_database_url, name)
    message = str(excinfo.value)
    for word in UNSAFE_ATTRIBUTES:
        assert word in message, word
    assert "membresía" in message
    assert name not in message
    assert "auth_owner" not in message


def test_0004_rejects_auth_owner_that_is_member_of_another_role(migration_database_url, temp_roles):
    name, group = temp_roles(), temp_roles()
    temp_roles.grant(group, name)
    with pytest.raises(RuntimeError) as excinfo:
        _check_attributes_0004(migration_database_url, name)
    assert name not in str(excinfo.value)


def test_0004_attribute_check_treats_a_missing_role_as_unsafe(migration_database_url):
    # Falla cerrado: un rol inexistente no se da por inerte (revisión de seguridad de T2).
    missing = f"auth_owner_falta_{uuid.uuid4().hex[:6]}"
    with pytest.raises(RuntimeError) as excinfo:
        _check_attributes_0004(migration_database_url, missing)
    assert missing not in str(excinfo.value)
    assert "01-app-role.sh" in str(excinfo.value)


def test_0004_upgrade_fails_if_the_app_role_is_member_of_auth_owner(
    migration_database_url, app_database_url, temp_roles, monkeypatch
):
    # La aplicación nunca puede hacer SET ROLE al dueño (A6): 0004 no concede EXECUTE
    # si el rol de la aplicación es miembro de él. El GRANT se revierte con la transacción.
    owner = temp_roles()
    migration = _load_migration_0004()
    monkeypatch.setenv("APP_DB_USER", app_database_url.username)
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                quote = conn.dialect.identifier_preparer.quote
                conn.exec_driver_sql(f"GRANT {quote(owner)} TO {quote(app_database_url.username)}")
                monkeypatch.setattr(migration, "op", _FakeOp(conn))
                monkeypatch.setattr(migration, "AUTH_OWNER", owner)
                with pytest.raises(RuntimeError) as excinfo:
                    migration.upgrade()
            finally:
                tx.rollback()
    finally:
        engine.dispose()
    message = str(excinfo.value)
    assert "APP_DB_USER" in message
    assert "miembro" in message
    assert owner not in message
    assert app_database_url.username not in message
    assert "0004" not in message  # no llegó a ejecutar ninguna sentencia


def _run_0004_with_owner(migration_database_url, monkeypatch, step: str, owner: str):
    """Ejecuta ``upgrade``/``downgrade`` de 0004 con otro nombre de dueño; se revierte."""
    migration = _load_migration_0004()
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                monkeypatch.setattr(migration, "op", _FakeOp(conn))
                monkeypatch.setattr(migration, "AUTH_OWNER", owner)
                with pytest.raises(RuntimeError) as excinfo:
                    getattr(migration, step)()
            finally:
                tx.rollback()
    finally:
        engine.dispose()
    return excinfo.value


@pytest.mark.parametrize("attribute", ["CREATEROLE", "CREATEDB", "REPLICATION"])
def test_0004_upgrade_checks_the_auth_owner_attributes(
    migration_database_url, temp_roles, monkeypatch, attribute
):
    name = temp_roles(attribute)
    error = _run_0004_with_owner(migration_database_url, monkeypatch, "upgrade", name)
    assert name not in str(error)
    assert attribute in str(error)
    assert "0004" not in str(error)  # no llegó a ejecutar ninguna sentencia


@pytest.mark.parametrize("step", ["upgrade", "downgrade"])
def test_0004_without_auth_owner_fails_with_a_clear_message(
    migration_database_url, monkeypatch, step
):
    missing = f"auth_owner_falta_{uuid.uuid4().hex[:6]}"
    error = _run_0004_with_owner(migration_database_url, monkeypatch, step, missing)
    assert "01-app-role.sh" in str(error)
    assert "0004" not in str(error)


def test_0004_fails_if_the_migrator_stays_member_of_auth_owner(
    migration_database_url, temp_roles, monkeypatch
):
    # Una membresía previa del migrador en el dueño (como createrole_self_grant en
    # Supabase, C8) no se da por buena: la comprobación final de 0004 falla. Todo se
    # revierte (también el GRANT del rol temporal, que es transaccional).
    owner = temp_roles()
    migration = _load_migration_0004()
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                quote = conn.dialect.identifier_preparer.quote
                migrator = conn.scalar(text("select current_user"))
                conn.exec_driver_sql(f"GRANT {quote(owner)} TO {quote(migrator)}")
                monkeypatch.setattr(migration, "AUTH_OWNER", owner)
                with pytest.raises(RuntimeError) as excinfo:
                    migration.require_no_leftover_privileges(conn)
            finally:
                tx.rollback()
    finally:
        engine.dispose()
    assert "C8" in str(excinfo.value)
    assert owner not in str(excinfo.value)
