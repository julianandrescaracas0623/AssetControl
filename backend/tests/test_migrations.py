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
import os
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
LIMITE_TASA = "0005_limite_tasa"
CATALOGO = "0006_ubicaciones_y_categorias"
ACTIVOS = "0007_activos"
CAMBIOS = "0008_activo_cambios"
CONTEO = "0009_sesiones_y_verificacion"
DISCREPANCIAS = "0010_discrepancias"
CIERRE = "0011_cierre_e_informe"
SUPABASE_FUNCIONES = "0012_funciones_sin_supabase"
FOTOS = "0013_fotos"
EMPRESA = "0014_empresa_y_detalle"
RECUPERACION = "0015_recuperacion_contrasena"
FUNCIONES_RECUPERACION = "0016_funciones_recuperacion"
PLATAFORMA = "0017_plataforma"
FUNCIONES_PLATAFORMA = "0018_funciones_plataforma"
# Spec 017, T3b: hallazgo de la revisión (0019-0022 los reserva el plan para T4-T7).
INVITACION_TENANT_ACTIVO = "0023_invitacion_tenant_activo"
# Spec 017, T4: cambio obligatorio de contraseña y ámbitos de plataforma en limite_tasa.
CAMBIO_PASSWORD = "0024_cambio_password"
LIMITE_TASA_PLATAFORMA = "0025_limite_tasa_plataforma"
# Spec 017, T4 (M1 de la revisión de seguridad): corte de los JWT al cambiar la contraseña.
SESIONES_VALIDAS_DESDE = "0026_sesiones_validas_desde"
# Spec 017, T5: funciones del módulo Usuarios de la consola.
PLATAFORMA_USUARIOS = "0027_plataforma_usuarios"
# Spec 017, T6: función del módulo Actividad de la consola.
PLATAFORMA_ACTIVIDAD = "0028_plataforma_actividad"
# Spec 017, T7: función del logo en el alta de la consola.
PLATAFORMA_LOGO = "0029_plataforma_logo"
# Spec 017, C1 (T12): editar la ficha y reemplazar el logo de una empresa.
PLATAFORMA_EDICION = "0030_plataforma_edicion_empresa"
# Spec 017, C1 (T13): editar nombre y rol de un usuario.
PLATAFORMA_EDITAR_USUARIO = "0031_plataforma_editar_usuario"
# Spec 017, C1b (T16): contraseña temporal de un usuario.
PLATAFORMA_PASSWORD_USUARIO = "0032_plataforma_password_usuario"
# Usuarios de la empresa (0033): el admin cambia rol y activación de una persona.
USUARIOS_CAMBIAR_MEMBRESIA = "0033_usuarios_cambiar_membresia"
HEAD = USUARIOS_CAMBIAR_MEMBRESIA
MIGRATION_0002 = BACKEND_DIR / "migrations" / "versions" / "0002_acceso_y_usuarios.py"
MIGRATION_0003 = BACKEND_DIR / "migrations" / "versions" / "0003_politicas_del_dueno.py"
MIGRATION_0004 = BACKEND_DIR / "migrations" / "versions" / "0004_funciones_de_acceso.py"
MIGRATION_0016 = BACKEND_DIR / "migrations" / "versions" / "0016_funciones_recuperacion.py"
MIGRATION_0017 = BACKEND_DIR / "migrations" / "versions" / "0017_plataforma.py"
APP_ROLE_VAR = "APP_DB_USER"
AUTH_TABLES = ["invitacion", "membresia", "refresh_token", "tenant", "usuario"]
CATALOG_TABLES = ["categoria", "ubicacion"]
ASSET_TABLES = ["activo", "activo_evento"]
COUNT_TABLES = ["sesion_conteo", "verificacion"]
CLOSE_TABLES = ["sesion_desglose", "sesion_no_encontrado"]
PHOTO_TABLES = ["foto"]
COMPANY_TABLES = ["empresa", "empresa_logo", "sesion_detalle", "sesion_empresa"]
RECOVERY_TABLES = ["recuperacion_contrasena"]
PLATFORM_TABLES = ["desarrollador", "plataforma_auditoria", "plataforma_refresh_token"]

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

    assert script.get_heads() == [HEAD]
    assert [r.revision for r in revisions] == [
        USUARIOS_CAMBIAR_MEMBRESIA,
        PLATAFORMA_PASSWORD_USUARIO,
        PLATAFORMA_EDITAR_USUARIO,
        PLATAFORMA_EDICION,
        PLATAFORMA_LOGO,
        PLATAFORMA_ACTIVIDAD,
        PLATAFORMA_USUARIOS,
        SESIONES_VALIDAS_DESDE,
        LIMITE_TASA_PLATAFORMA,
        CAMBIO_PASSWORD,
        INVITACION_TENANT_ACTIVO,
        FUNCIONES_PLATAFORMA,
        PLATAFORMA,
        FUNCIONES_RECUPERACION,
        RECUPERACION,
        EMPRESA,
        FOTOS,
        SUPABASE_FUNCIONES,
        CIERRE,
        DISCREPANCIAS,
        CONTEO,
        CAMBIOS,
        ACTIVOS,
        CATALOGO,
        LIMITE_TASA,
        FUNCIONES,
        POLITICAS,
        ACCESO,
        BASELINE,
    ]
    assert revisions[0].down_revision == PLATAFORMA_PASSWORD_USUARIO
    assert revisions[1].down_revision == PLATAFORMA_EDITAR_USUARIO
    assert revisions[2].down_revision == PLATAFORMA_EDICION
    assert revisions[3].down_revision == PLATAFORMA_LOGO
    assert revisions[4].down_revision == PLATAFORMA_ACTIVIDAD
    assert revisions[5].down_revision == PLATAFORMA_USUARIOS
    assert revisions[6].down_revision == SESIONES_VALIDAS_DESDE
    assert revisions[7].down_revision == LIMITE_TASA_PLATAFORMA
    assert revisions[8].down_revision == CAMBIO_PASSWORD
    assert revisions[9].down_revision == INVITACION_TENANT_ACTIVO
    assert revisions[10].down_revision == FUNCIONES_PLATAFORMA
    assert revisions[11].down_revision == PLATAFORMA
    assert revisions[12].down_revision == FUNCIONES_RECUPERACION
    assert revisions[13].down_revision == RECUPERACION
    assert revisions[14].down_revision == EMPRESA
    assert revisions[15].down_revision == FOTOS
    assert revisions[16].down_revision == SUPABASE_FUNCIONES
    assert revisions[17].down_revision == CIERRE
    assert revisions[18].down_revision == DISCREPANCIAS
    assert revisions[19].down_revision == CONTEO
    assert revisions[20].down_revision == CAMBIOS
    assert revisions[21].down_revision == ACTIVOS
    assert revisions[22].down_revision == CATALOGO
    assert revisions[23].down_revision == LIMITE_TASA
    assert revisions[24].down_revision == FUNCIONES
    assert revisions[25].down_revision == POLITICAS
    assert revisions[26].down_revision == ACCESO
    assert revisions[27].down_revision == BASELINE
    assert revisions[28].down_revision is None


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
    with_auth = sorted(
        [
            "alembic_version",
            "limite_tasa",
            *AUTH_TABLES,
            *CATALOG_TABLES,
            *ASSET_TABLES,
            *COUNT_TABLES,
            *CLOSE_TABLES,
            *PHOTO_TABLES,
            *COMPANY_TABLES,
            *RECOVERY_TABLES,
            *PLATFORM_TABLES,
        ]
    )

    assert _public_state(migrate_env) == ([], [])
    assert not _schema_exists(migrate_env, "acceso")

    command.upgrade(config, "head")
    assert _public_state(migrate_env) == (with_auth, [HEAD])
    assert _schema_exists(migrate_env, "acceso")

    command.downgrade(config, "base")
    # Solo queda la tabla de control de Alembic, vacía; el esquema acceso desaparece.
    assert _public_state(migrate_env) == (["alembic_version"], [])
    assert not _schema_exists(migrate_env, "acceso")

    command.upgrade(config, "head")
    assert _public_state(migrate_env) == (with_auth, [HEAD])
    assert _schema_exists(migrate_env, "acceso")


def test_downgrade_to_baseline_removes_only_0002(migrate_env):
    config = alembic_config()
    command.upgrade(config, "head")

    command.downgrade(config, BASELINE)

    assert _public_state(migrate_env) == (["alembic_version"], [BASELINE])
    assert not _schema_exists(migrate_env, "acceso")


def _policy_names(url: URL, table: str) -> list[str]:
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            return list(
                conn.scalars(
                    text(
                        "select policyname from pg_policies where schemaname = 'public' "
                        "and tablename = :t order by policyname"
                    ),
                    {"t": table},
                )
            )
    finally:
        engine.dispose()


def test_0005_up_down_up_touches_only_limite_tasa(migrate_env):
    # T10: 0005 crea solo limite_tasa (con sus políticas) y su downgrade solo la quita.
    config = alembic_config()
    with_auth = sorted(["alembic_version", *AUTH_TABLES])

    command.upgrade(config, FUNCIONES)
    assert _public_state(migrate_env) == (with_auth, [FUNCIONES])
    owner_before = _owner_state(migrate_env)

    command.upgrade(config, LIMITE_TASA)
    assert _public_state(migrate_env) == (sorted([*with_auth, "limite_tasa"]), [LIMITE_TASA])
    assert _policy_names(migrate_env, "limite_tasa") == [
        "limite_tasa_contar",
        "limite_tasa_leer",
        "limite_tasa_purga",
        "limite_tasa_purga_leer",
        "limite_tasa_sumar",
    ]
    assert _owner_state(migrate_env) == owner_before

    command.downgrade(config, FUNCIONES)
    assert _public_state(migrate_env) == (with_auth, [FUNCIONES])
    assert _policy_names(migrate_env, "limite_tasa") == []
    assert _owner_state(migrate_env) == owner_before

    command.upgrade(config, LIMITE_TASA)
    assert _public_state(migrate_env) == (sorted([*with_auth, "limite_tasa"]), [LIMITE_TASA])


def test_0006_up_down_up_touches_only_the_catalog_tables(migrate_env):
    # Spec 003, T1: 0006 crea solo ubicacion y categoria y su downgrade solo las quita.
    config = alembic_config()
    before = sorted(["alembic_version", "limite_tasa", *AUTH_TABLES])

    command.upgrade(config, LIMITE_TASA)
    owner_before = _owner_state(migrate_env)

    command.upgrade(config, CATALOGO)
    assert _public_state(migrate_env) == (sorted([*before, *CATALOG_TABLES]), [CATALOGO])
    for table in CATALOG_TABLES:
        assert _policy_names(migrate_env, table) == ["tenant_isolation"]
    assert _owner_state(migrate_env) == owner_before

    command.downgrade(config, LIMITE_TASA)
    assert _public_state(migrate_env) == (before, [LIMITE_TASA])

    command.upgrade(config, CATALOGO)
    assert _public_state(migrate_env) == (sorted([*before, *CATALOG_TABLES]), [CATALOGO])


def test_0007_up_down_up_touches_only_the_asset_tables_and_trigger(migrate_env):
    # Spec 004, T1: 0007 crea activo, activo_evento y la función del disparador D1.
    config = alembic_config()
    before = sorted(["alembic_version", "limite_tasa", *AUTH_TABLES, *CATALOG_TABLES])

    command.upgrade(config, CATALOGO)
    owner_before = _owner_state(migrate_env)

    command.upgrade(config, ACTIVOS)
    assert _public_state(migrate_env) == (sorted([*before, *ASSET_TABLES]), [ACTIVOS])
    for table in ASSET_TABLES:
        assert _policy_names(migrate_env, table) == ["tenant_isolation"]
    assert _public_functions(migrate_env) == ["activo_ubicacion_valida"]
    assert _owner_state(migrate_env) == owner_before

    command.downgrade(config, CATALOGO)
    assert _public_state(migrate_env) == (before, [CATALOGO])
    assert _public_functions(migrate_env) == []

    command.upgrade(config, ACTIVOS)
    assert _public_state(migrate_env) == (sorted([*before, *ASSET_TABLES]), [ACTIVOS])


def test_0008_up_down_up_changes_only_grants_and_event_types(migrate_env):
    # Spec 005, T1: 0008 da UPDATE por columna en activo y suma el tipo datos_cambiados;
    # no crea ni borra tablas ni funciones, y su downgrade deja todo como en 0007.
    config = alembic_config()
    tables = sorted(
        ["alembic_version", "limite_tasa", *AUTH_TABLES, *CATALOG_TABLES, *ASSET_TABLES]
    )

    command.upgrade(config, ACTIVOS)
    owner_before = _owner_state(migrate_env)
    grants_before = _activo_update_columns(migrate_env)
    assert grants_before == []
    assert "datos_cambiados" not in _event_type_check(migrate_env)

    command.upgrade(config, CAMBIOS)
    assert _public_state(migrate_env) == (tables, [CAMBIOS])
    assert _public_functions(migrate_env) == ["activo_ubicacion_valida"]
    assert "codigo" not in _activo_update_columns(migrate_env)
    assert "precio_compra" in _activo_update_columns(migrate_env)
    assert "datos_cambiados" in _event_type_check(migrate_env)
    assert _owner_state(migrate_env) == owner_before

    command.downgrade(config, ACTIVOS)
    assert _public_state(migrate_env) == (tables, [ACTIVOS])
    assert _activo_update_columns(migrate_env) == grants_before
    assert "datos_cambiados" not in _event_type_check(migrate_env)

    command.upgrade(config, CAMBIOS)
    assert _public_state(migrate_env) == (tables, [CAMBIOS])


def test_0009_up_down_up_touches_only_the_count_tables(migrate_env):
    # Spec 006, T1: 0009 crea sesion_conteo y verificacion y las FK de activo_evento.
    config = alembic_config()
    before = sorted(
        ["alembic_version", "limite_tasa", *AUTH_TABLES, *CATALOG_TABLES, *ASSET_TABLES]
    )

    command.upgrade(config, CAMBIOS)
    owner_before = _owner_state(migrate_env)

    command.upgrade(config, CONTEO)
    assert _public_state(migrate_env) == (sorted([*before, *COUNT_TABLES]), [CONTEO])
    for table in COUNT_TABLES:
        assert _policy_names(migrate_env, table) == ["tenant_isolation"]
    assert _owner_state(migrate_env) == owner_before

    command.downgrade(config, CAMBIOS)
    assert _public_state(migrate_env) == (before, [CAMBIOS])

    command.upgrade(config, CONTEO)
    assert _public_state(migrate_env) == (sorted([*before, *COUNT_TABLES]), [CONTEO])


def test_0010_up_down_up_changes_only_the_event_type_and_index(migrate_env):
    # Spec 007, T1: 0010 suma discrepancia_descartada y el índice de una resolución.
    config = alembic_config()
    tables = sorted(
        [
            "alembic_version",
            "limite_tasa",
            *AUTH_TABLES,
            *CATALOG_TABLES,
            *ASSET_TABLES,
            *COUNT_TABLES,
        ]
    )
    command.upgrade(config, CONTEO)
    owner_before = _owner_state(migrate_env)
    assert "discrepancia_descartada" not in _event_type_check(migrate_env)

    command.upgrade(config, DISCREPANCIAS)
    assert _public_state(migrate_env) == (tables, [DISCREPANCIAS])
    assert "discrepancia_descartada" in _event_type_check(migrate_env)
    assert _owner_state(migrate_env) == owner_before

    command.downgrade(config, CONTEO)
    assert _public_state(migrate_env) == (tables, [CONTEO])
    assert "discrepancia_descartada" not in _event_type_check(migrate_env)

    command.upgrade(config, DISCREPANCIAS)
    assert _public_state(migrate_env) == (tables, [DISCREPANCIAS])


def test_0011_up_down_up_touches_only_the_close_tables_and_functions(migrate_env):
    # Spec 008, T1: 0011 crea sesion_desglose, sesion_no_encontrado, los totales de la
    # sesión y las funciones de sus disparadores; el downgrade deja todo como en 0010.
    config = alembic_config()
    before = sorted(
        [
            "alembic_version",
            "limite_tasa",
            *AUTH_TABLES,
            *CATALOG_TABLES,
            *ASSET_TABLES,
            *COUNT_TABLES,
        ]
    )
    command.upgrade(config, DISCREPANCIAS)
    owner_before = _owner_state(migrate_env)

    command.upgrade(config, CIERRE)
    assert _public_state(migrate_env) == (sorted([*before, *CLOSE_TABLES]), [CIERRE])
    for table in CLOSE_TABLES:
        assert _policy_names(migrate_env, table) == ["tenant_isolation"]
    assert _public_functions(migrate_env) == [
        "activo_ubicacion_valida",
        "conteo_cerrado_requerido",
        "sesion_conteo_inmutable",
    ]
    assert _owner_state(migrate_env) == owner_before

    command.downgrade(config, DISCREPANCIAS)
    assert _public_state(migrate_env) == (before, [DISCREPANCIAS])
    assert _public_functions(migrate_env) == ["activo_ubicacion_valida"]

    command.upgrade(config, CIERRE)
    assert _public_state(migrate_env) == (sorted([*before, *CLOSE_TABLES]), [CIERRE])


def test_0013_up_down_up_touches_only_the_photo_table_function_and_event_types(migrate_env):
    # Spec 012, T3: 0013 crea foto (RLS, privilegios mínimos), su disparador y los tipos de
    # evento de foto; el downgrade deja todo como en 0012.
    config = alembic_config()
    before = sorted(
        [
            "alembic_version",
            "limite_tasa",
            *AUTH_TABLES,
            *CATALOG_TABLES,
            *ASSET_TABLES,
            *COUNT_TABLES,
            *CLOSE_TABLES,
        ]
    )
    command.upgrade(config, SUPABASE_FUNCIONES)
    owner_before = _owner_state(migrate_env)
    check_before = _event_type_check(migrate_env)
    funciones_before = _public_functions(migrate_env)

    command.upgrade(config, FOTOS)
    assert _public_state(migrate_env) == (sorted([*before, *PHOTO_TABLES]), [FOTOS])
    assert _policy_names(migrate_env, "foto") == ["tenant_isolation"]
    assert _public_functions(migrate_env) == sorted([*funciones_before, "foto_retirada_es_final"])
    assert all(t in _event_type_check(migrate_env) for t in ("foto_agregada", "foto_cambiada"))
    assert "foto_retirada" in _event_type_check(migrate_env)
    assert _owner_state(migrate_env) == owner_before

    command.downgrade(config, SUPABASE_FUNCIONES)
    assert _public_state(migrate_env) == (before, [SUPABASE_FUNCIONES])
    assert _public_functions(migrate_env) == funciones_before
    assert _event_type_check(migrate_env) == check_before

    command.upgrade(config, FOTOS)
    assert _public_state(migrate_env) == (sorted([*before, *PHOTO_TABLES]), [FOTOS])


def test_0014_up_down_up_touches_only_the_company_and_detail_tables(migrate_env):
    # Spec 013, T1: 0014 crea empresa, empresa_logo, sesion_empresa y sesion_detalle;
    # el downgrade deja todo como en 0013 (sin funciones nuevas ni cambios del dueño).
    config = alembic_config()
    before = sorted(
        [
            "alembic_version",
            "limite_tasa",
            *AUTH_TABLES,
            *CATALOG_TABLES,
            *ASSET_TABLES,
            *COUNT_TABLES,
            *CLOSE_TABLES,
            *PHOTO_TABLES,
        ]
    )
    command.upgrade(config, FOTOS)
    owner_before = _owner_state(migrate_env)
    funciones_before = _public_functions(migrate_env)

    command.upgrade(config, EMPRESA)
    assert _public_state(migrate_env) == (sorted([*before, *COMPANY_TABLES]), [EMPRESA])
    for table in COMPANY_TABLES:
        assert _policy_names(migrate_env, table) == ["tenant_isolation"]
    assert _public_functions(migrate_env) == funciones_before
    assert _owner_state(migrate_env) == owner_before

    command.downgrade(config, FOTOS)
    assert _public_state(migrate_env) == (before, [FOTOS])

    command.upgrade(config, EMPRESA)
    assert _public_state(migrate_env) == (sorted([*before, *COMPANY_TABLES]), [EMPRESA])


RECOVERY_SCOPES = ("recuperar_ip", "recuperar_cuenta", "restablecer_ip")


def _limite_tasa_scope_check(url: URL) -> list[tuple[str, str]]:
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            return [
                tuple(row)
                for row in conn.execute(
                    text(
                        "select conname, pg_get_constraintdef(oid) from pg_constraint "
                        "where conrelid = 'public.limite_tasa'::regclass and contype = 'c' "
                        "and pg_get_constraintdef(oid) like '%ambito%'"
                    )
                )
            ]
    finally:
        engine.dispose()


def _limite_tasa_scopes(url: URL) -> list[str]:
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            return list(conn.scalars(text("select ambito from limite_tasa order by 1")))
    finally:
        engine.dispose()


def _count(url: URL, scopes: tuple[str, ...]) -> None:
    """Siembra un contador reciente por ámbito (el migrador local es superusuario)."""
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.begin() as conn:
            for scope in scopes:
                conn.execute(
                    text(
                        "insert into limite_tasa (ambito, clave_hash, ventana_inicio, intentos) "
                        "values (:a, :h, now(), 1)"
                    ),
                    {"a": scope, "h": uuid.uuid4().bytes * 2},
                )
    finally:
        engine.dispose()


def test_0015_up_down_up_touches_only_the_recovery_table_and_the_scope_check(migrate_env):
    # Spec 014, T1: 0015 crea recuperacion_contrasena y amplía el CHECK de ambito de
    # limite_tasa; el downgrade deja todo como en 0014 (sin funciones ni cambios del dueño).
    config = alembic_config()
    before = sorted(
        [
            "alembic_version",
            "limite_tasa",
            *AUTH_TABLES,
            *CATALOG_TABLES,
            *ASSET_TABLES,
            *COUNT_TABLES,
            *CLOSE_TABLES,
            *PHOTO_TABLES,
            *COMPANY_TABLES,
        ]
    )
    command.upgrade(config, EMPRESA)
    owner_before = _owner_state(migrate_env)
    funciones_before = _public_functions(migrate_env)
    acceso_before = _acceso_state(migrate_env)
    check_before = _limite_tasa_scope_check(migrate_env)
    assert len(check_before) == 1
    assert not any(scope in check_before[0][1] for scope in RECOVERY_SCOPES)

    command.upgrade(config, RECUPERACION)
    assert _public_state(migrate_env) == (sorted([*before, *RECOVERY_TABLES]), [RECUPERACION])
    assert _policy_names(migrate_env, "recuperacion_contrasena") == ["tenant_isolation"]
    assert _public_functions(migrate_env) == funciones_before
    assert _acceso_state(migrate_env) == acceso_before
    assert _owner_state(migrate_env) == owner_before
    check_after = _limite_tasa_scope_check(migrate_env)
    assert [name for name, _ in check_after] == [check_before[0][0]]
    assert all(scope in check_after[0][1] for scope in RECOVERY_SCOPES)

    command.downgrade(config, EMPRESA)
    assert _public_state(migrate_env) == (before, [EMPRESA])
    assert _limite_tasa_scope_check(migrate_env) == check_before
    assert _owner_state(migrate_env) == owner_before

    command.upgrade(config, RECUPERACION)
    assert _public_state(migrate_env) == (sorted([*before, *RECOVERY_TABLES]), [RECUPERACION])


def test_0015_downgrade_drops_only_the_counters_of_the_new_scopes(migrate_env):
    # plan.md §3.2: el CHECK anterior no admite los ámbitos nuevos; el downgrade borra
    # solo esos contadores (infraestructura, sin datos de negocio) y conserva los demás.
    config = alembic_config()
    command.upgrade(config, RECUPERACION)
    _count(migrate_env, ("login_ip", "aceptar_ip", *RECOVERY_SCOPES))

    command.downgrade(config, EMPRESA)
    assert _limite_tasa_scopes(migrate_env) == ["aceptar_ip", "login_ip"]

    command.upgrade(config, RECUPERACION)
    assert _limite_tasa_scopes(migrate_env) == ["aceptar_ip", "login_ip"]


RECOVERY_OWNER_POLICIES = [
    ("membresia", "dueno_membresia_recuperar"),
    ("membresia", "dueno_membresia_restablecer"),
    ("recuperacion_contrasena", "dueno_recuperacion_consumir"),
    ("recuperacion_contrasena", "dueno_recuperacion_crear"),
    ("recuperacion_contrasena", "dueno_recuperacion_invalidar"),
    ("recuperacion_contrasena", "dueno_recuperacion_invalidar_otros"),
    ("recuperacion_contrasena", "dueno_recuperacion_restablecer"),
    ("recuperacion_contrasena", "dueno_recuperacion_solicitar"),
    ("refresh_token", "dueno_refresh_restablecer"),
    ("refresh_token", "dueno_refresh_revocar"),
    ("usuario", "dueno_usuario_cambiar_clave"),
    ("usuario", "dueno_usuario_recuperar"),
    ("usuario", "dueno_usuario_restablecer"),
]


def test_0016_up_down_up_touches_only_the_recovery_functions_policies_and_grants(migrate_env):
    # Spec 014, T2: 0016 crea las dos funciones de acceso, las 13 políticas del dueño y sus
    # GRANT por columna; no crea tablas. El downgrade deja todo exactamente como en 0015.
    config = alembic_config()
    command.upgrade(config, RECUPERACION)
    tables_before = _public_state(migrate_env)[0]
    policies_before, grants_before = _owner_state(migrate_env)
    acceso_before = _acceso_state(migrate_env)
    funciones_before = _public_functions(migrate_env)
    assert acceso_before == (FUNCTION_NAMES, False, [])

    command.upgrade(config, FUNCIONES_RECUPERACION)
    assert _public_state(migrate_env) == (tables_before, [FUNCIONES_RECUPERACION])
    assert _acceso_state(migrate_env) == (RECOVERY_HEAD_FUNCTION_NAMES, False, [])
    policies, grants = _owner_state(migrate_env)
    assert sorted(set(policies) - set(policies_before)) == RECOVERY_OWNER_POLICIES
    assert set(policies_before) <= set(policies)
    assert grants > grants_before
    assert _public_functions(migrate_env) == funciones_before
    assert _policy_names(migrate_env, "recuperacion_contrasena") == sorted(
        [
            "tenant_isolation",
            *(p for t, p in RECOVERY_OWNER_POLICIES if t == "recuperacion_contrasena"),
        ]
    )

    command.downgrade(config, RECUPERACION)
    assert _public_state(migrate_env) == (tables_before, [RECUPERACION])
    assert _owner_state(migrate_env) == (policies_before, grants_before)
    assert _acceso_state(migrate_env) == acceso_before

    command.upgrade(config, FUNCIONES_RECUPERACION)
    assert _owner_state(migrate_env) == (policies, grants)
    assert _acceso_state(migrate_env) == (RECOVERY_HEAD_FUNCTION_NAMES, False, [])


def _load_migration_0016():
    spec = importlib.util.spec_from_file_location("migration_0016_under_test", MIGRATION_0016)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0016_failed_statement_does_not_leak_the_sql(migration_database_url):
    migration = _load_migration_0016()
    secret = f"centinela_{uuid.uuid4().hex[:8]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            with pytest.raises(RuntimeError) as excinfo:
                migration.execute_statements(conn, [f'GRANT SELECT ON no_existe TO "{secret}"'])
    finally:
        engine.dispose()

    message = str(excinfo.value)
    assert "0016" in message
    assert "centinela" not in message
    assert excinfo.value.__cause__ is None


@pytest.mark.parametrize("step", ["upgrade", "downgrade"])
def test_0016_without_auth_owner_fails_with_a_clear_message(
    migration_database_url, app_database_url, monkeypatch, step
):
    migration = _load_migration_0016()
    monkeypatch.setenv(APP_ROLE_VAR, app_database_url.username)
    missing = f"auth_owner_falta_{uuid.uuid4().hex[:6]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                monkeypatch.setattr(migration, "op", _FakeOp(conn))
                monkeypatch.setattr(migration, "AUTH_OWNER", missing)
                with pytest.raises(RuntimeError) as excinfo:
                    getattr(migration, step)()
            finally:
                tx.rollback()
    finally:
        engine.dispose()
    assert "01-app-role.sh" in str(excinfo.value)
    assert "0016" not in str(excinfo.value)  # no llegó a ejecutar ninguna sentencia


@pytest.mark.parametrize("attribute", ["LOGIN", "BYPASSRLS", "CREATEROLE"])
def test_0016_upgrade_checks_the_auth_owner_attributes(
    migration_database_url, app_database_url, temp_roles, monkeypatch, attribute
):
    name = temp_roles(attribute)
    migration = _load_migration_0016()
    monkeypatch.setenv(APP_ROLE_VAR, app_database_url.username)
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                monkeypatch.setattr(migration, "op", _FakeOp(conn))
                monkeypatch.setattr(migration, "AUTH_OWNER", name)
                with pytest.raises(RuntimeError) as excinfo:
                    migration.upgrade()
            finally:
                tx.rollback()
    finally:
        engine.dispose()
    assert name not in str(excinfo.value)
    assert attribute in str(excinfo.value)
    assert "0016" not in str(excinfo.value)


def _activo_update_columns(url: URL) -> list[str]:
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            return list(
                conn.scalars(
                    text(
                        "select column_name from information_schema.column_privileges "
                        "where table_schema = 'public' and table_name = 'activo' "
                        "and privilege_type = 'UPDATE' and grantee <> current_user "
                        "order by 1"
                    )
                )
            )
    finally:
        engine.dispose()


def _event_type_check(url: URL) -> str:
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            return conn.scalar(
                text(
                    "select pg_get_constraintdef(c.oid) from pg_constraint c "
                    "where c.conrelid = 'public.activo_evento'::regclass "
                    "and c.conname = 'activo_evento_tipo_check'"
                )
            )
    finally:
        engine.dispose()


def _public_functions(url: URL) -> list[str]:
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            return list(
                conn.scalars(
                    text(
                        "select p.proname from pg_proc p join pg_namespace n "
                        "on n.oid = p.pronamespace where n.nspname = 'public' order by 1"
                    )
                )
            )
    finally:
        engine.dispose()


def test_0005_rejects_the_migrator_as_app_role(migrate_env, monkeypatch):
    config = alembic_config()
    command.upgrade(config, FUNCIONES)
    monkeypatch.setenv(APP_ROLE_VAR, migrate_env.username)

    with pytest.raises(RuntimeError) as excinfo:
        command.upgrade(config, "head")

    assert APP_ROLE_VAR in str(excinfo.value)
    assert _public_state(migrate_env)[1] == [FUNCIONES]


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
        # T10 (0005): la purga de limite_tasa es la única política del migrador.
        # Spec 017 (0017): las del dueño de las funciones de plataforma.
        assert sorted(roles) == sorted(
            [name, "auth_owner", "plataforma_owner", migrate_env.username]
        )
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
    # 10 de 0003, 13 de 0016 (spec 014, T2), 1 de 0018 (spec 017, T3a), 2 de 0023 (T3b),
    # 5 de 0024 (T4) y 4 de 0033 (cambio de membresía de la empresa).
    assert len(policies) == 35
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
# Spec 014, T2 (0016): las dos de recuperación de contraseña.
RECOVERY_FUNCTION_NAMES = ["restablecer_contrasena", "solicitar_recuperacion"]
RECOVERY_HEAD_FUNCTION_NAMES = sorted([*FUNCTION_NAMES, *RECOVERY_FUNCTION_NAMES])
# Spec 017, T1 (0017): las del operador y el login de plataforma (dueña plataforma_owner).
PLATFORM_FUNCTION_NAMES = [
    "cambiar_estado_desarrollador",
    "crear_desarrollador",
    "plataforma_buscar_login",
    "restablecer_desarrollador",
]
PLATAFORMA_FUNCTION_NAMES = sorted([*RECOVERY_HEAD_FUNCTION_NAMES, *PLATFORM_FUNCTION_NAMES])
# Spec 017, T3a (0018): las de Empresas.
EMPRESAS_FUNCTION_NAMES = [
    "plataforma_cambiar_estado_tenant",
    "plataforma_crear_tenant",
    "plataforma_listar_tenants",
]
# Las que hay tras 0018 y 0023 (sin la de 0024).
EMPRESAS_HEAD_FUNCTION_NAMES = sorted([*PLATAFORMA_FUNCTION_NAMES, *EMPRESAS_FUNCTION_NAMES])
# Spec 017, T4 (0024): el cambio de contraseña propio (lo que hay tras 0024–0026).
CAMBIO_HEAD_FUNCTION_NAMES = sorted([*EMPRESAS_HEAD_FUNCTION_NAMES, "cambiar_password_propio"])
# Spec 017, T5 (0027): las de Usuarios.
USUARIOS_FUNCTION_NAMES = ["plataforma_cambiar_estado_membresia", "plataforma_listar_usuarios"]
USUARIOS_HEAD_FUNCTION_NAMES = sorted([*CAMBIO_HEAD_FUNCTION_NAMES, *USUARIOS_FUNCTION_NAMES])
# Spec 017, T6 (0028): la de Actividad.
ACTIVIDAD_HEAD_FUNCTION_NAMES = sorted(
    [*USUARIOS_HEAD_FUNCTION_NAMES, "plataforma_listar_auditoria"]
)
# Spec 017, T7 (0029): la del logo en el alta.
LOGO_HEAD_FUNCTION_NAMES = sorted([*ACTIVIDAD_HEAD_FUNCTION_NAMES, "plataforma_registrar_logo"])
# Spec 017, C1 (0030): las dos de la ficha (la del logo se rehace con el mismo nombre).
EDICION_HEAD_FUNCTION_NAMES = sorted(
    [*LOGO_HEAD_FUNCTION_NAMES, "plataforma_actualizar_empresa", "plataforma_leer_empresa"]
)
# Spec 017, C1/T13 (0031): la de editar nombre y rol.
EDITAR_USUARIO_HEAD_FUNCTION_NAMES = sorted(
    [*EDICION_HEAD_FUNCTION_NAMES, "plataforma_cambiar_usuario"]
)
# Spec 017, C1b/T16 (0032): la de la contraseña temporal.
PASSWORD_USUARIO_HEAD_FUNCTION_NAMES = sorted(
    [*EDITAR_USUARIO_HEAD_FUNCTION_NAMES, "plataforma_restablecer_password_usuario"]
)
# Usuarios de la empresa (0033): el admin cambia el rol y activa o desactiva a una persona.
HEAD_FUNCTION_NAMES = sorted([*PASSWORD_USUARIO_HEAD_FUNCTION_NAMES, "cambiar_membresia"])


def test_0004_creates_the_functions_and_leaves_no_create_nor_membership(migrate_env):
    command.upgrade(alembic_config(), FUNCIONES)
    assert _acceso_state(migrate_env) == (FUNCTION_NAMES, False, [])
    command.upgrade(alembic_config(), "head")
    assert _acceso_state(migrate_env) == (HEAD_FUNCTION_NAMES, False, [])


def test_downgrade_0004_removes_only_the_functions(migrate_env):
    config = alembic_config()
    # Las políticas y GRANT del dueño de 0003 (0016 añade las suyas y las quita al bajar).
    command.upgrade(config, FUNCIONES)
    policies, grants = _owner_state(migrate_env)
    command.upgrade(config, "head")

    command.downgrade(config, POLITICAS)

    assert _acceso_state(migrate_env) == ([], False, [])
    assert _schema_exists(migrate_env, "acceso")
    assert _owner_state(migrate_env) == (policies, grants)
    with_auth = sorted(["alembic_version", *AUTH_TABLES])
    assert _public_state(migrate_env) == (with_auth, [POLITICAS])

    command.upgrade(config, "head")
    assert _acceso_state(migrate_env) == (HEAD_FUNCTION_NAMES, False, [])


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


@pytest.mark.parametrize("prefix", ["Migrador_Prueba_", "migrador-prueba-"])
def test_0004_detects_the_membership_of_a_migrator_with_a_quoted_name(
    migration_database_url, temp_roles, monkeypatch, prefix
):
    # H1 (auditoría de T3): to_regrole(current_user) da NULL con mayúsculas o guion y C5
    # no veía la membresía. El migrador de nombre citado se crea y se usa con SET LOCAL ROLE
    # dentro de la transacción; CREATE ROLE y GRANT se revierten con ella.
    owner = temp_roles()
    migration = _load_migration_0004()
    engine = create_engine(migration_database_url, poolclass=NullPool)
    migrator = f"{prefix}{uuid.uuid4().hex[:6]}"
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                quote = conn.dialect.identifier_preparer.quote
                conn.exec_driver_sql(f"CREATE ROLE {quote(migrator)} NOLOGIN")
                conn.exec_driver_sql(f"GRANT {quote(owner)} TO {quote(migrator)}")
                conn.exec_driver_sql(f"SET LOCAL ROLE {quote(migrator)}")
                assert conn.scalar(text("select current_user")) == migrator
                monkeypatch.setattr(migration, "AUTH_OWNER", owner)
                with pytest.raises(RuntimeError) as excinfo:
                    migration.require_no_leftover_privileges(conn)
            finally:
                tx.rollback()
    finally:
        engine.dispose()
    assert "C8" in str(excinfo.value)
    assert migrator not in str(excinfo.value)


# --- Spec 017, T1: 0017_plataforma ----------------------------------------------------

PLATFORM_SCOPES = ("plat_login_ip", "plat_login_cuenta")


def _platform_state(url: URL) -> dict[str, object]:
    """Lo que toca 0017 fuera de sus tablas: columnas, USAGE del dueño y sus políticas."""
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            columns = sorted(
                tuple(row)
                for row in conn.execute(
                    text(
                        "select table_name, column_name from information_schema.columns "
                        "where table_schema = 'public' and table_name in ('tenant', 'usuario')"
                    )
                )
            )
            usage = conn.scalar(
                text(
                    "select exists (select 1 from pg_namespace where nspname = 'acceso') "
                    "and has_schema_privilege('plataforma_owner', 'acceso', 'USAGE')"
                )
            )
            policies = conn.scalar(
                text(
                    "select count(*) from pg_policies "
                    "where schemaname = 'public' and 'plataforma_owner' = any(roles)"
                )
            )
            members = conn.scalar(
                text(
                    "select count(*) from pg_auth_members "
                    "where roleid = 'plataforma_owner'::regrole"
                )
            )
    finally:
        engine.dispose()
    return {"columns": columns, "usage": usage, "policies": policies, "members": members}


def test_0017_up_down_up_touches_only_the_platform_objects(migrate_env):
    config = alembic_config()
    command.upgrade(config, FUNCIONES_RECUPERACION)
    tables_before = _public_state(migrate_env)[0]
    owner_before = _owner_state(migrate_env)
    platform_before = _platform_state(migrate_env)
    check_before = _limite_tasa_scope_check(migrate_env)
    functions_before = _public_functions(migrate_env)
    assert platform_before["usage"] is False
    assert platform_before["policies"] == 0

    command.upgrade(config, PLATAFORMA)
    assert _public_state(migrate_env) == (
        sorted([*tables_before, *PLATFORM_TABLES]),
        [PLATAFORMA],
    )
    assert _acceso_state(migrate_env) == (PLATAFORMA_FUNCTION_NAMES, False, [])
    assert _owner_state(migrate_env) == owner_before  # auth_owner no cambia
    assert _public_functions(migrate_env) == functions_before
    platform = _platform_state(migrate_env)
    added = sorted(set(platform["columns"]) - set(platform_before["columns"]))
    assert added == [
        ("tenant", "activo"),
        ("tenant", "desactivado_en"),
        ("tenant", "desactivado_por"),
        ("usuario", "debe_cambiar_password"),
    ]
    assert (platform["usage"], platform["policies"], platform["members"]) == (True, 9, 0)
    check_after = _limite_tasa_scope_check(migrate_env)
    assert [name for name, _ in check_after] == [check_before[0][0]]
    assert all(scope in check_after[0][1] for scope in PLATFORM_SCOPES)

    command.downgrade(config, FUNCIONES_RECUPERACION)
    assert _public_state(migrate_env) == (tables_before, [FUNCIONES_RECUPERACION])
    assert _acceso_state(migrate_env) == (RECOVERY_HEAD_FUNCTION_NAMES, False, [])
    assert _owner_state(migrate_env) == owner_before
    assert _platform_state(migrate_env) == platform_before
    assert _limite_tasa_scope_check(migrate_env) == check_before

    command.upgrade(config, PLATAFORMA)
    assert _platform_state(migrate_env) == platform


def test_0017_does_not_change_existing_tenants_nor_users(migrate_env):
    # R25: la migración no cambia a ningún usuario; las empresas existentes siguen activas.
    config = alembic_config()
    command.upgrade(config, FUNCIONES_RECUPERACION)
    tenant_id, usuario_id = uuid.uuid4(), uuid.uuid4()
    engine = create_engine(migrate_env, poolclass=NullPool)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("insert into tenant (id, nombre) values (:t, 'Clínica sintética')"),
                {"t": tenant_id},
            )
            conn.execute(
                text(
                    "insert into usuario (id, email, nombre, password_hash) "
                    "values (:u, 'previo@ejemplo.test', 'Previo', 'h')"
                ),
                {"u": usuario_id},
            )
        command.upgrade(config, PLATAFORMA)
        with engine.connect() as conn:
            tenant = conn.execute(
                text("select activo, desactivado_en, desactivado_por from tenant where id = :t"),
                {"t": tenant_id},
            ).one()
            marca = conn.scalar(
                text("select debe_cambiar_password from usuario where id = :u"), {"u": usuario_id}
            )
    finally:
        engine.dispose()
    assert tuple(tenant) == (True, None, None)
    assert marca is False


def test_0017_downgrade_drops_only_the_counters_of_the_platform_scopes(migrate_env):
    config = alembic_config()
    command.upgrade(config, PLATAFORMA)
    _count(migrate_env, ("login_ip", "recuperar_ip", *PLATFORM_SCOPES))

    command.downgrade(config, FUNCIONES_RECUPERACION)
    assert _limite_tasa_scopes(migrate_env) == ["login_ip", "recuperar_ip"]


def _insert_bypassing_rls(url: URL, table: str, statement: str, params: dict) -> None:
    """Inserta como dueño (migrador) quitando FORCE RLS solo dentro de la transacción."""
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            conn.execute(text(statement), params)
            conn.exec_driver_sql(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    finally:
        engine.dispose()


def _seed_tenant(url: URL, *, activo: bool) -> None:
    _insert_bypassing_rls(
        url,
        "tenant",
        "insert into tenant (id, nombre, activo, desactivado_en) values "
        "(:id, 'Clínica sintética', :activo, case when :activo then null else now() end)",
        {"id": uuid.uuid4(), "activo": activo},
    )


@pytest.mark.parametrize(
    ("seed", "expected"),
    [
        ("auditoria", "plataforma_auditoria"),
        ("tenant_inactivo", "inactiva"),
    ],
)
def test_0017_downgrade_aborts_if_it_would_lose_platform_data(migrate_env, seed, expected):
    # Hallazgo de seguridad de T1: el downgrade no borra auditoría ni el estado de una
    # empresa desactivada; aborta con un mensaje claro y no toca nada.
    config = alembic_config()
    command.upgrade(config, PLATAFORMA)
    _seed_tenant(migrate_env, activo=True)
    if seed == "auditoria":
        _insert_bypassing_rls(
            migrate_env,
            "plataforma_auditoria",
            "insert into plataforma_auditoria (accion, resultado, objeto_id) "
            "values ('desarrollador_creado', 'ok', :objeto)",
            {"objeto": uuid.uuid4()},
        )
    else:
        _seed_tenant(migrate_env, activo=False)
    tables_before = _public_state(migrate_env)
    platform_before = _platform_state(migrate_env)
    check_before = _limite_tasa_scope_check(migrate_env)

    with pytest.raises(RuntimeError) as excinfo:
        command.downgrade(config, FUNCIONES_RECUPERACION)

    message = str(excinfo.value)
    assert "0017" in message
    assert "no puede revertirse" in message
    assert expected in message
    assert _public_state(migrate_env) == tables_before
    assert _platform_state(migrate_env) == platform_before
    assert _limite_tasa_scope_check(migrate_env) == check_before
    engine = create_engine(migrate_env, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            forced = dict(
                conn.execute(
                    text(
                        "select relname, relforcerowsecurity from pg_class "
                        "where relname in ('tenant', 'plataforma_auditoria') "
                        "and relnamespace = 'public'::regnamespace"
                    )
                ).all()
            )
    finally:
        engine.dispose()
    assert forced == {"tenant": True, "plataforma_auditoria": True}


def test_0017_downgrade_works_with_only_active_tenants(migrate_env):
    config = alembic_config()
    command.upgrade(config, PLATAFORMA)
    _seed_tenant(migrate_env, activo=True)

    command.downgrade(config, FUNCIONES_RECUPERACION)
    assert _public_state(migrate_env)[1] == [FUNCIONES_RECUPERACION]
    engine = create_engine(migrate_env, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            forced = conn.scalar(
                text(
                    "select relforcerowsecurity from pg_class "
                    "where relname = 'tenant' and relnamespace = 'public'::regnamespace"
                )
            )
    finally:
        engine.dispose()
    assert forced is True


def _load_migration_0017():
    spec = importlib.util.spec_from_file_location("migration_0017_under_test", MIGRATION_0017)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0017_failed_statement_does_not_leak_the_sql(migration_database_url):
    migration = _load_migration_0017()
    secret = f"centinela_{uuid.uuid4().hex[:8]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            with pytest.raises(RuntimeError) as excinfo:
                migration.execute_statements(conn, [f'GRANT SELECT ON no_existe TO "{secret}"'])
    finally:
        engine.dispose()

    message = str(excinfo.value)
    assert "0017" in message
    assert "centinela" not in message
    assert excinfo.value.__cause__ is None


@pytest.mark.parametrize("step", ["upgrade", "downgrade"])
def test_0017_without_plataforma_owner_fails_with_a_clear_message(
    migration_database_url, app_database_url, monkeypatch, step
):
    migration = _load_migration_0017()
    monkeypatch.setenv(APP_ROLE_VAR, app_database_url.username)
    missing = f"plataforma_owner_falta_{uuid.uuid4().hex[:6]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                monkeypatch.setattr(migration, "op", _FakeOp(conn))
                monkeypatch.setattr(migration, "PLATAFORMA_OWNER", missing)
                with pytest.raises(RuntimeError) as excinfo:
                    getattr(migration, step)()
            finally:
                tx.rollback()
    finally:
        engine.dispose()
    assert "01-app-role.sh" in str(excinfo.value)
    assert "preparar-roles" in str(excinfo.value)
    assert "0017" not in str(excinfo.value)  # no llegó a ejecutar ninguna sentencia


@pytest.mark.parametrize("attribute", ["LOGIN", "BYPASSRLS", "CREATEROLE", "SUPERUSER"])
def test_0017_upgrade_checks_the_plataforma_owner_attributes(
    migration_database_url, app_database_url, temp_roles, monkeypatch, attribute
):
    name = temp_roles(attribute)
    migration = _load_migration_0017()
    monkeypatch.setenv(APP_ROLE_VAR, app_database_url.username)
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                monkeypatch.setattr(migration, "op", _FakeOp(conn))
                monkeypatch.setattr(migration, "PLATAFORMA_OWNER", name)
                with pytest.raises(RuntimeError) as excinfo:
                    migration.upgrade()
            finally:
                tx.rollback()
    finally:
        engine.dispose()
    assert name not in str(excinfo.value)
    assert attribute in str(excinfo.value)
    assert "0017" not in str(excinfo.value)


def test_0017_rejects_an_app_role_that_is_member_of_plataforma_owner(
    migration_database_url, temp_roles, monkeypatch
):
    owner, app_role = temp_roles(), temp_roles()
    temp_roles.grant(owner, app_role)
    migration = _load_migration_0017()
    monkeypatch.setenv(APP_ROLE_VAR, app_role)
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                monkeypatch.setattr(migration, "op", _FakeOp(conn))
                monkeypatch.setattr(migration, "PLATAFORMA_OWNER", owner)
                with pytest.raises(RuntimeError) as excinfo:
                    migration.upgrade()
            finally:
                tx.rollback()
    finally:
        engine.dispose()
    message = str(excinfo.value)
    assert "miembro" in message
    assert app_role not in message and owner not in message


@pytest.mark.parametrize("name", ["auth_owner", "plataforma_owner"])
def test_0017_rejects_an_owner_as_app_role(migration_database_url, monkeypatch, name):
    migration = _load_migration_0017()
    monkeypatch.setenv(APP_ROLE_VAR, name)
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            with pytest.raises(RuntimeError) as excinfo:
                migration._app_role(conn)
    finally:
        engine.dispose()
    assert APP_ROLE_VAR in str(excinfo.value)


# --- Spec 017, T3a: 0018_funciones_plataforma ----------------------------------------------

MIGRATION_0018 = BACKEND_DIR / "migrations" / "versions" / "0018_funciones_plataforma.py"
# Huella de buscar_login de 0004 (la que el downgrade de 0018 debe restaurar).
BUSCAR_LOGIN_0004_SHA = "e2d65ea58fe28d0906cd6ecdc87126b3fe75f61105f6203bb15c93f4f8f1ae1c"


def _empresas_state(url: URL) -> dict[str, object]:
    """Lo que toca 0018: cuerpos, ACL de tenant, políticas y privilegios de los dueños."""
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            bodies = dict(
                conn.execute(
                    text(
                        "select p.proname, encode(sha256(convert_to(p.prosrc, 'UTF8')), 'hex') "
                        "from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                        "where n.nspname = 'acceso'"
                    )
                ).all()
            )
            acls = dict(
                conn.execute(
                    text(
                        "select p.proname, p.proacl::text from pg_proc p "
                        "join pg_namespace n on n.oid = p.pronamespace "
                        "where n.nspname = 'acceso'"
                    )
                ).all()
            )
            tenant_acl = conn.scalar(
                text("select relacl::text from pg_class where oid = 'tenant'::regclass")
            )
            tenant_columns = sorted(
                tuple(row)
                for row in conn.execute(
                    text(
                        "select grantee, column_name, privilege_type "
                        "from information_schema.column_privileges "
                        "where table_schema = 'public' and table_name = 'tenant'"
                    )
                )
            )
            policies = sorted(
                tuple(row)
                for row in conn.execute(
                    text(
                        "select tablename, policyname, roles::text, qual, with_check "
                        "from pg_policies where schemaname = 'public'"
                    )
                )
            )
            owner_columns = sorted(
                tuple(row)
                for row in conn.execute(
                    text(
                        "select grantee, table_name, column_name, privilege_type "
                        "from information_schema.column_privileges where table_schema = 'public' "
                        "and grantee in ('auth_owner', 'plataforma_owner')"
                    )
                )
            )
            leftovers = conn.execute(
                text(
                    "select has_schema_privilege('auth_owner', 'acceso', 'CREATE'), "
                    "has_schema_privilege('plataforma_owner', 'acceso', 'CREATE'), "
                    "(select count(*) from pg_auth_members where roleid in "
                    "('auth_owner'::regrole, 'plataforma_owner'::regrole))"
                )
            ).one()
    finally:
        engine.dispose()
    return {
        "bodies": bodies,
        "acls": acls,
        "tenant_acl": tenant_acl,
        "tenant_columns": tenant_columns,
        "policies": policies,
        "owner_columns": owner_columns,
        "leftovers": tuple(leftovers),
    }


def test_0018_up_down_up_touches_only_its_objects(migrate_env):
    config = alembic_config()
    command.upgrade(config, PLATAFORMA)
    tables_before = _public_state(migrate_env)[0]
    before = _empresas_state(migrate_env)
    assert before["bodies"]["buscar_login"] == BUSCAR_LOGIN_0004_SHA

    command.upgrade(config, FUNCIONES_PLATAFORMA)
    after = _empresas_state(migrate_env)
    assert _public_state(migrate_env) == (tables_before, [FUNCIONES_PLATAFORMA])
    assert sorted(after["bodies"]) == EMPRESAS_HEAD_FUNCTION_NAMES
    assert after["bodies"]["buscar_login"] != BUSCAR_LOGIN_0004_SHA
    # CREATE OR REPLACE como auth_owner: mismo EXECUTE de buscar_login.
    assert after["acls"]["buscar_login"] == before["acls"]["buscar_login"]
    for name in set(before["bodies"]) - {"buscar_login"}:
        assert after["bodies"][name] == before["bodies"][name], name
    added = sorted(set(after["policies"]) - set(before["policies"]))
    removed = sorted(set(before["policies"]) - set(after["policies"]))
    assert [p[1] for p in removed] == ["plataforma_auditoria_insertar"]
    assert sorted(p[1] for p in added) == sorted(
        [
            "dueno_plat_desarrollador_actor",
            "dueno_plat_empresa_crear",
            "dueno_plat_empresa_listar",
            "dueno_plat_membresia_crear",
            "dueno_plat_membresia_listar",
            "dueno_plat_tenant_crear",
            "dueno_plat_tenant_estado",
            "dueno_plat_tenant_estado_leer",
            "dueno_plat_tenant_listar",
            "dueno_plat_tenant_recien_creado",
            "dueno_plat_usuario_crear",
            "dueno_tenant_login",
            "plataforma_auditoria_insertar",
        ]
    )
    assert after["tenant_acl"] != before["tenant_acl"]
    assert after["leftovers"] == (False, False, 0)

    command.downgrade(config, PLATAFORMA)
    assert _public_state(migrate_env) == (tables_before, [PLATAFORMA])
    assert _empresas_state(migrate_env) == before

    command.upgrade(config, FUNCIONES_PLATAFORMA)
    assert _empresas_state(migrate_env) == after


def test_0018_downgrade_keeps_the_companies_created_from_the_console(migrate_env):
    # El downgrade no borra datos: la empresa creada desde la consola queda como cualquier otra.
    config = alembic_config()
    command.upgrade(config, FUNCIONES_PLATAFORMA)
    dev, tenant = uuid.uuid4(), uuid.uuid4()
    _insert_bypassing_rls(
        migrate_env,
        "desarrollador",
        "insert into desarrollador (id, email, nombre, password_hash) "
        "values (:d, 'dev.0018@ejemplo.test', 'Dev', 'h')",
        {"d": dev},
    )
    engine = create_engine(migrate_env, poolclass=NullPool)
    password_hash = "$argon2id$v=19$m=8,t=1,p=1$c2FsdHNhbHQ$aGFzaGhhc2g"
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "select * from acceso.plataforma_crear_tenant(:d, :t, 'Clínica 0018', "
                    "'Calle 1', '', '', '', 'admin.0018@ejemplo.test', 'Admin', :h)"
                ),
                {"d": dev, "t": tenant, "h": password_hash},
            )
        command.downgrade(config, PLATAFORMA)
        with engine.connect() as conn:
            for table in ("tenant", "empresa"):
                conn.exec_driver_sql(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            counts = conn.execute(
                text(
                    "select (select count(*) from tenant where id = :t), "
                    "(select count(*) from empresa where tenant_id = :t)"
                ),
                {"t": tenant},
            ).one()
            conn.rollback()
    finally:
        engine.dispose()
    assert tuple(counts) == (1, 1)


def _load_migration(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_migration_0018():
    return _load_migration(MIGRATION_0018, "migration_0018_under_test")


def test_0018_restores_exactly_the_0004_login_body():
    migration = _load_migration_0018()
    migration_0004 = _load_migration(MIGRATION_0004, "migration_0004_login_body")

    def body(statement: str) -> str:
        return statement.split("$fn$")[1]

    assert body(migration.RESTORE_BUSCAR_LOGIN) == body(migration_0004.CREATE_BUSCAR_LOGIN)


def test_0018_failed_statement_does_not_leak_the_sql(migration_database_url):
    migration = _load_migration_0018()
    secret = f"centinela_{uuid.uuid4().hex[:8]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            with pytest.raises(RuntimeError) as excinfo:
                migration.execute_statements(conn, [f'GRANT SELECT ON no_existe TO "{secret}"'])
    finally:
        engine.dispose()
    message = str(excinfo.value)
    assert "0018" in message
    assert "centinela" not in message
    assert excinfo.value.__cause__ is None


@pytest.mark.parametrize("owner", ["AUTH_OWNER", "PLATAFORMA_OWNER"])
@pytest.mark.parametrize("step", ["upgrade", "downgrade"])
def test_0018_without_an_owner_fails_with_a_clear_message(
    migration_database_url, app_database_url, monkeypatch, step, owner
):
    migration = _load_migration_0018()
    monkeypatch.setenv(APP_ROLE_VAR, app_database_url.username)
    missing = f"dueno_falta_{uuid.uuid4().hex[:6]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                monkeypatch.setattr(migration, "op", _FakeOp(conn))
                monkeypatch.setattr(migration, owner, missing)
                with pytest.raises(RuntimeError) as excinfo:
                    getattr(migration, step)()
            finally:
                tx.rollback()
    finally:
        engine.dispose()
    assert "01-app-role.sh" in str(excinfo.value)
    assert "0018" not in str(excinfo.value)  # no llegó a ejecutar ninguna sentencia


@pytest.mark.parametrize("name", ["auth_owner", "plataforma_owner"])
def test_0018_rejects_an_owner_as_app_role(migration_database_url, monkeypatch, name):
    migration = _load_migration_0018()
    monkeypatch.setenv(APP_ROLE_VAR, name)
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            with pytest.raises(RuntimeError) as excinfo:
                migration._app_role(conn)
    finally:
        engine.dispose()
    assert APP_ROLE_VAR in str(excinfo.value)


# --- Spec 017, T3b: 0023_invitacion_tenant_activo -----------------------------------------

MIGRATION_0023 = BACKEND_DIR / "migrations" / "versions" / "0023_invitacion_tenant_activo.py"
# Huellas de validar_invitacion y aceptar_invitacion de 0004 (las que restaura el downgrade).
VALIDAR_INVITACION_0004_SHA = "c51ab1560e578613b40021f4eec9e2b0134f9ec19256524bc49636cc748ef19d"
ACEPTAR_INVITACION_0004_SHA = "04aebfbb9e1aa4c96ddb0ffd18b70756f71e1db506b97e33f3e272a7daa95407"
INVITATION_FUNCTIONS = ("aceptar_invitacion", "validar_invitacion")


def _load_migration_0023():
    return _load_migration(MIGRATION_0023, "migration_0023_under_test")


def test_0023_up_down_up_touches_only_its_objects(migrate_env):
    config = alembic_config()
    command.upgrade(config, FUNCIONES_PLATAFORMA)
    tables_before = _public_state(migrate_env)[0]
    before = _empresas_state(migrate_env)
    assert before["bodies"]["validar_invitacion"] == VALIDAR_INVITACION_0004_SHA
    assert before["bodies"]["aceptar_invitacion"] == ACEPTAR_INVITACION_0004_SHA

    command.upgrade(config, INVITACION_TENANT_ACTIVO)
    after = _empresas_state(migrate_env)
    assert _public_state(migrate_env) == (tables_before, [INVITACION_TENANT_ACTIVO])
    assert sorted(after["bodies"]) == EMPRESAS_HEAD_FUNCTION_NAMES
    for name in INVITATION_FUNCTIONS:
        assert after["bodies"][name] != before["bodies"][name], name
        # CREATE OR REPLACE como auth_owner: mismo dueño y mismo EXECUTE.
        assert after["acls"][name] == before["acls"][name], name
    for name in set(before["bodies"]) - set(INVITATION_FUNCTIONS):
        assert after["bodies"][name] == before["bodies"][name], name
    added = sorted(set(after["policies"]) - set(before["policies"]))
    assert set(before["policies"]) <= set(after["policies"])
    assert [(p[0], p[1], p[2]) for p in added] == [
        ("tenant", "dueno_tenant_inv_aceptar", "{auth_owner}"),
        ("tenant", "dueno_tenant_inv_validar", "{auth_owner}"),
    ]
    # Sin GRANT nuevo: auth_owner ya leía tenant (id, creado_en, activo).
    for key in ("tenant_acl", "tenant_columns", "owner_columns"):
        assert after[key] == before[key], key
    assert after["leftovers"] == (False, False, 0)

    command.downgrade(config, FUNCIONES_PLATAFORMA)
    assert _public_state(migrate_env) == (tables_before, [FUNCIONES_PLATAFORMA])
    assert _empresas_state(migrate_env) == before

    command.upgrade(config, INVITACION_TENANT_ACTIVO)
    assert _empresas_state(migrate_env) == after


def test_0023_downgrade_keeps_the_invitations_and_accounts(migrate_env):
    # El downgrade no borra datos: la invitación aceptada y su cuenta quedan.
    config = alembic_config()
    command.upgrade(config, INVITACION_TENANT_ACTIVO)
    engine = create_engine(migrate_env, poolclass=NullPool)
    clave = uuid.uuid4().hex * 2
    try:
        with engine.begin() as conn:
            tenant = conn.scalar(
                text("select acceso.crear_tenant('Clínica 0023', 'admin.0023@ejemplo.test', :c)"),
                {"c": clave},
            )
        command.downgrade(config, FUNCIONES_PLATAFORMA)
        with engine.connect() as conn:
            for table in ("tenant", "invitacion"):
                conn.exec_driver_sql(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            counts = conn.execute(
                text(
                    "select (select count(*) from tenant where id = :t), "
                    "(select count(*) from invitacion where tenant_id = :t)"
                ),
                {"t": tenant},
            ).one()
            conn.rollback()
    finally:
        engine.dispose()
    assert tuple(counts) == (1, 1)


def test_0023_restores_exactly_the_0004_invitation_bodies():
    migration = _load_migration_0023()
    migration_0004 = _load_migration(MIGRATION_0004, "migration_0004_invitation_bodies")

    def body(statement: str) -> str:
        return statement.split("$fn$")[1]

    assert body(migration.RESTORE_VALIDAR) == body(migration_0004.CREATE_VALIDAR_INVITACION)
    assert body(migration.RESTORE_ACEPTAR) == body(migration_0004.CREATE_ACEPTAR_INVITACION)
    # El cuerpo nuevo solo añade la condición del tenant activo.
    for new, old in (
        (migration.REPLACE_VALIDAR, migration_0004.CREATE_VALIDAR_INVITACION),
        (migration.REPLACE_ACEPTAR, migration_0004.CREATE_ACEPTAR_INVITACION),
    ):
        assert body(new).replace(migration._TENANT_ACTIVO, "") == body(old)
        assert body(new).count(migration._TENANT_ACTIVO) == 1


def test_0023_failed_statement_does_not_leak_the_sql(migration_database_url):
    migration = _load_migration_0023()
    secret = f"centinela_{uuid.uuid4().hex[:8]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            with pytest.raises(RuntimeError) as excinfo:
                migration.execute_statements(conn, [f'GRANT SELECT ON no_existe TO "{secret}"'])
    finally:
        engine.dispose()
    message = str(excinfo.value)
    assert "0023" in message
    assert "centinela" not in message
    assert excinfo.value.__cause__ is None


@pytest.mark.parametrize("step", ["upgrade", "downgrade"])
def test_0023_without_auth_owner_fails_with_a_clear_message(
    migration_database_url, monkeypatch, step
):
    migration = _load_migration_0023()
    missing = f"dueno_falta_{uuid.uuid4().hex[:6]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                monkeypatch.setattr(migration, "op", _FakeOp(conn))
                monkeypatch.setattr(migration, "AUTH_OWNER", missing)
                with pytest.raises(RuntimeError) as excinfo:
                    getattr(migration, step)()
            finally:
                tx.rollback()
    finally:
        engine.dispose()
    assert "01-app-role.sh" in str(excinfo.value)
    assert "0023" not in str(excinfo.value)  # no llegó a ejecutar ninguna sentencia


# --- Spec 017, T4: 0024_cambio_password y 0025_limite_tasa_plataforma ----------------------

MIGRATION_0024 = BACKEND_DIR / "migrations" / "versions" / "0024_cambio_password.py"
MIGRATION_0025 = BACKEND_DIR / "migrations" / "versions" / "0025_limite_tasa_plataforma.py"
# Huella del cuerpo de 0016 de restablecer_contrasena (la que restaura el downgrade).
RESTABLECER_0016_SHA = "5c610ef358b4b823cafc24f1a5aaa7e183d404b91518995d52308b172a065b68"
CAMBIO_POLICIES = [
    ("membresia", "dueno_membresia_cambio", "{auth_owner}"),
    ("refresh_token", "dueno_refresh_cambio", "{auth_owner}"),
    ("refresh_token", "dueno_refresh_cambio_revocar", "{auth_owner}"),
    ("usuario", "dueno_usuario_cambio_leer", "{auth_owner}"),
    ("usuario", "dueno_usuario_cambio_propio", "{auth_owner}"),
]


def _usuario_columns(url: URL) -> list[tuple[str, str, str]]:
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            return sorted(
                tuple(row)
                for row in conn.execute(
                    text(
                        "select grantee, column_name, privilege_type "
                        "from information_schema.column_privileges "
                        "where table_schema = 'public' and table_name = 'usuario'"
                    )
                )
            )
    finally:
        engine.dispose()


def test_0024_up_down_up_touches_only_its_objects(migrate_env):
    config = alembic_config()
    command.upgrade(config, INVITACION_TENANT_ACTIVO)
    tables_before = _public_state(migrate_env)[0]
    before = _empresas_state(migrate_env)
    columns_before = _usuario_columns(migrate_env)
    assert before["bodies"]["restablecer_contrasena"] == RESTABLECER_0016_SHA

    command.upgrade(config, CAMBIO_PASSWORD)
    after = _empresas_state(migrate_env)
    assert _public_state(migrate_env) == (tables_before, [CAMBIO_PASSWORD])
    assert sorted(after["bodies"]) == CAMBIO_HEAD_FUNCTION_NAMES
    assert after["bodies"]["restablecer_contrasena"] != RESTABLECER_0016_SHA
    # CREATE OR REPLACE como auth_owner: mismo dueño y mismo EXECUTE.
    assert after["acls"]["restablecer_contrasena"] == before["acls"]["restablecer_contrasena"]
    assert after["acls"]["cambiar_password_propio"] == after["acls"]["restablecer_contrasena"]
    for name in set(before["bodies"]) - {"restablecer_contrasena"}:
        assert after["bodies"][name] == before["bodies"][name], name
    added = sorted(set(after["policies"]) - set(before["policies"]))
    assert set(before["policies"]) <= set(after["policies"])
    assert [(p[0], p[1], p[2]) for p in added] == CAMBIO_POLICIES
    new_owner = sorted(set(after["owner_columns"]) - set(before["owner_columns"]))
    assert new_owner == [("auth_owner", "usuario", "debe_cambiar_password", "UPDATE")]
    # La aplicación solo gana el SELECT de la marca; auth_owner, su UPDATE.
    app_added = sorted(set(_usuario_columns(migrate_env)) - set(columns_before))
    assert sorted((c, p) for _, c, p in app_added) == [
        ("debe_cambiar_password", "SELECT"),
        ("debe_cambiar_password", "UPDATE"),
    ]
    assert after["leftovers"] == (False, False, 0)

    command.downgrade(config, INVITACION_TENANT_ACTIVO)
    assert _public_state(migrate_env) == (tables_before, [INVITACION_TENANT_ACTIVO])
    assert _empresas_state(migrate_env) == before
    assert _usuario_columns(migrate_env) == columns_before

    command.upgrade(config, CAMBIO_PASSWORD)
    assert _empresas_state(migrate_env) == after


def test_0024_does_not_change_any_flag(migrate_env):
    # R25: la migración no cambia a ningún usuario.
    config = alembic_config()
    command.upgrade(config, INVITACION_TENANT_ACTIVO)
    usuario = uuid.uuid4()
    engine = create_engine(migrate_env, poolclass=NullPool)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "insert into usuario (id, email, nombre, password_hash, debe_cambiar_password) "
                    "values (:u, 'marcado.0024@ejemplo.test', 'Marcado', 'h', true)"
                ),
                {"u": usuario},
            )
        command.upgrade(config, CAMBIO_PASSWORD)
        command.downgrade(config, INVITACION_TENANT_ACTIVO)
        command.upgrade(config, CAMBIO_PASSWORD)
        with engine.connect() as conn:
            conn.exec_driver_sql("ALTER TABLE usuario NO FORCE ROW LEVEL SECURITY")
            marcas = conn.execute(
                text("select debe_cambiar_password from usuario where id = :u"), {"u": usuario}
            ).all()
            conn.rollback()
    finally:
        engine.dispose()
    assert [tuple(row) for row in marcas] == [(True,)]


def test_0024_restores_exactly_the_0016_reset_body():
    migration = _load_migration(MIGRATION_0024, "migration_0024_under_test")
    migration_0016 = _load_migration(MIGRATION_0016, "migration_0016_reset_body")

    def body(statement: str) -> str:
        return statement.split("$fn$")[1]

    assert body(migration.RESTORE_RESTABLECER) == body(migration_0016.CREATE_RESTABLECER)
    # El cuerpo nuevo solo quita la marca y vacía también la GUC nueva.
    nuevo = body(migration.REPLACE_RESTABLECER)
    assert nuevo.count(", debe_cambiar_password = false") == 1
    sin_cambios = nuevo.replace(", debe_cambiar_password = false", "").replace(
        ", 'app.auth_cambio_usuario'", ""
    )
    assert sin_cambios == body(migration_0016.CREATE_RESTABLECER)


def test_0024_failed_statement_does_not_leak_the_sql(migration_database_url):
    migration = _load_migration(MIGRATION_0024, "migration_0024_leak")
    secret = f"centinela_{uuid.uuid4().hex[:8]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            with pytest.raises(RuntimeError) as excinfo:
                migration.execute_statements(conn, [f'GRANT SELECT ON no_existe TO "{secret}"'])
    finally:
        engine.dispose()
    message = str(excinfo.value)
    assert "0024" in message
    assert "centinela" not in message
    assert excinfo.value.__cause__ is None


@pytest.mark.parametrize("step", ["upgrade", "downgrade"])
def test_0024_without_auth_owner_fails_with_a_clear_message(
    migration_database_url, monkeypatch, step
):
    migration = _load_migration(MIGRATION_0024, "migration_0024_owner")
    missing = f"dueno_falta_{uuid.uuid4().hex[:6]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                monkeypatch.setattr(migration, "op", _FakeOp(conn))
                monkeypatch.setattr(migration, "AUTH_OWNER", missing)
                with pytest.raises(RuntimeError) as excinfo:
                    getattr(migration, step)()
            finally:
                tx.rollback()
    finally:
        engine.dispose()
    assert "01-app-role.sh" in str(excinfo.value)
    assert "0024" not in str(excinfo.value)  # no llegó a ejecutar ninguna sentencia


NEW_PLATFORM_SCOPES = ("plat_accion", "plat_refresh_ip")


def test_0025_up_down_up_changes_only_the_scope_check(migrate_env):
    config = alembic_config()
    command.upgrade(config, CAMBIO_PASSWORD)
    tables_before = _public_state(migrate_env)[0]
    check_before = _limite_tasa_scope_check(migrate_env)
    state_before = _empresas_state(migrate_env)
    assert not any(scope in check_before[0][1] for scope in NEW_PLATFORM_SCOPES)

    command.upgrade(config, LIMITE_TASA_PLATAFORMA)
    check_after = _limite_tasa_scope_check(migrate_env)
    assert _public_state(migrate_env) == (tables_before, [LIMITE_TASA_PLATAFORMA])
    assert [name for name, _ in check_after] == [check_before[0][0]]
    assert all(scope in check_after[0][1] for scope in (*PLATFORM_SCOPES, *NEW_PLATFORM_SCOPES))
    assert _empresas_state(migrate_env) == state_before

    _count(migrate_env, ("login_ip", "plat_login_ip", *NEW_PLATFORM_SCOPES))
    command.downgrade(config, CAMBIO_PASSWORD)
    assert _limite_tasa_scope_check(migrate_env) == check_before
    assert _limite_tasa_scopes(migrate_env) == ["login_ip", "plat_login_ip"]

    command.upgrade(config, LIMITE_TASA_PLATAFORMA)
    assert _limite_tasa_scope_check(migrate_env) == check_after


def test_0025_failed_statement_does_not_leak_the_sql(migration_database_url):
    migration = _load_migration(MIGRATION_0025, "migration_0025_leak")
    secret = f"centinela_{uuid.uuid4().hex[:8]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            with pytest.raises(RuntimeError) as excinfo:
                migration.execute_statements(conn, [f'GRANT SELECT ON no_existe TO "{secret}"'])
    finally:
        engine.dispose()
    message = str(excinfo.value)
    assert "0025" in message
    assert "centinela" not in message
    assert excinfo.value.__cause__ is None


# --- Spec 017, T4 (M1): 0026_sesiones_validas_desde -----------------------------------------

MIGRATION_0026 = BACKEND_DIR / "migrations" / "versions" / "0026_sesiones_validas_desde.py"
CORTE = ", sesiones_validas_desde = pg_catalog.now()"


def _body(statement: str) -> str:
    return statement.split("$fn$")[1]


def test_0026_restores_exactly_the_0024_bodies_and_only_adds_the_cut():
    migration = _load_migration(MIGRATION_0026, "migration_0026_bodies")
    migration_0024 = _load_migration(MIGRATION_0024, "migration_0024_for_0026")

    assert migration.CORTE == CORTE
    assert _body(migration.RESTORE_CAMBIAR) == _body(migration_0024.CREATE_CAMBIAR)
    assert _body(migration.RESTORE_RESTABLECER) == _body(migration_0024.REPLACE_RESTABLECER)
    for nuevo, viejo in (
        (migration.REPLACE_CAMBIAR, migration.RESTORE_CAMBIAR),
        (migration.REPLACE_RESTABLECER, migration.RESTORE_RESTABLECER),
    ):
        cuerpo = _body(nuevo)
        assert cuerpo.count(CORTE) == 1
        assert cuerpo.replace(CORTE, "") == _body(viejo)
        # La misma sentencia que cambia el hash pone el corte (sin UPDATE aparte).
        (sentencia,) = [s for s in cuerpo.split(";") if CORTE in s]
        assert "SET password_hash = " in sentencia
        assert sentencia.count("UPDATE public.usuario") == 1
    # Mismo encabezado (STRICT, SECURITY DEFINER, search_path) que 0024.
    assert migration._HEADER == migration_0024._HEADER
    assert set(migration.AUTH_GUCS) == set(migration_0024.AUTH_GUCS)


def test_0026_up_down_up_touches_only_its_objects(migrate_env):
    config = alembic_config()
    command.upgrade(config, LIMITE_TASA_PLATAFORMA)
    tables_before = _public_state(migrate_env)[0]
    before = _empresas_state(migrate_env)
    columns_before = _usuario_columns(migrate_env)

    command.upgrade(config, SESIONES_VALIDAS_DESDE)
    after = _empresas_state(migrate_env)
    assert _public_state(migrate_env) == (tables_before, [SESIONES_VALIDAS_DESDE])
    assert sorted(after["bodies"]) == CAMBIO_HEAD_FUNCTION_NAMES
    cambiadas = {"cambiar_password_propio", "restablecer_contrasena"}
    for name in cambiadas:
        assert after["bodies"][name] != before["bodies"][name], name
        # CREATE OR REPLACE como auth_owner: mismo dueño y mismo EXECUTE.
        assert after["acls"][name] == before["acls"][name], name
    for name in set(before["bodies"]) - cambiadas:
        assert after["bodies"][name] == before["bodies"][name], name
    assert after["policies"] == before["policies"]
    new_owner = sorted(set(after["owner_columns"]) - set(before["owner_columns"]))
    assert new_owner == [("auth_owner", "usuario", "sesiones_validas_desde", "UPDATE")]
    # La aplicación solo gana el SELECT de la columna y auth_owner su UPDATE (el migrador,
    # dueño de la tabla, figura con todos sus privilegios sobre la columna nueva).
    added = sorted(set(_usuario_columns(migrate_env)) - set(columns_before))
    assert sorted(
        (g, c, p) for g, c, p in added if g in (os.environ[APP_ROLE_VAR], "auth_owner")
    ) == sorted(
        [
            (os.environ[APP_ROLE_VAR], "sesiones_validas_desde", "SELECT"),
            ("auth_owner", "sesiones_validas_desde", "UPDATE"),
        ]
    )
    assert after["leftovers"] == (False, False, 0)

    command.downgrade(config, LIMITE_TASA_PLATAFORMA)
    assert _public_state(migrate_env) == (tables_before, [LIMITE_TASA_PLATAFORMA])
    # Cuerpos (huella SHA de prosrc), ACL, políticas y privilegios: exactamente los de 0025.
    assert _empresas_state(migrate_env) == before
    assert _usuario_columns(migrate_env) == columns_before

    command.upgrade(config, SESIONES_VALIDAS_DESDE)
    assert _empresas_state(migrate_env) == after


def test_0026_keeps_users_and_their_data(migrate_env):
    # Ningún usuario cambia al subir (corte NULL) ni al bajar (hash y marca intactos).
    config = alembic_config()
    command.upgrade(config, LIMITE_TASA_PLATAFORMA)
    usuario = uuid.uuid4()
    engine = create_engine(migrate_env, poolclass=NullPool)
    consulta = "select password_hash, debe_cambiar_password, activo from usuario where id = :u"

    def leer(sql: str) -> list[tuple]:
        with engine.connect() as conn:
            conn.exec_driver_sql("ALTER TABLE usuario NO FORCE ROW LEVEL SECURITY")
            rows = [tuple(row) for row in conn.execute(text(sql), {"u": usuario})]
            conn.rollback()
        return rows

    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "insert into usuario (id, email, nombre, password_hash, debe_cambiar_password) "
                    "values (:u, 'corte.0026@ejemplo.test', 'Corte', 'h', true)"
                ),
                {"u": usuario},
            )
        antes = leer(consulta)
        command.upgrade(config, SESIONES_VALIDAS_DESDE)
        assert leer("select sesiones_validas_desde from usuario where id = :u") == [(None,)]
        assert leer(consulta) == antes
        command.downgrade(config, LIMITE_TASA_PLATAFORMA)
        assert leer(consulta) == antes
    finally:
        engine.dispose()
    assert antes == [("h", True, True)]


def test_0026_failed_statement_does_not_leak_the_sql(migration_database_url):
    migration = _load_migration(MIGRATION_0026, "migration_0026_leak")
    secret = f"centinela_{uuid.uuid4().hex[:8]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            with pytest.raises(RuntimeError) as excinfo:
                migration.execute_statements(conn, [f'GRANT SELECT ON no_existe TO "{secret}"'])
    finally:
        engine.dispose()
    message = str(excinfo.value)
    assert "0026" in message
    assert "centinela" not in message
    assert excinfo.value.__cause__ is None


@pytest.mark.parametrize("step", ["upgrade", "downgrade"])
def test_0026_without_auth_owner_fails_with_a_clear_message(
    migration_database_url, monkeypatch, step
):
    migration = _load_migration(MIGRATION_0026, "migration_0026_owner")
    missing = f"dueno_falta_{uuid.uuid4().hex[:6]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                monkeypatch.setattr(migration, "op", _FakeOp(conn))
                monkeypatch.setattr(migration, "AUTH_OWNER", missing)
                with pytest.raises(RuntimeError) as excinfo:
                    getattr(migration, step)()
            finally:
                tx.rollback()
    finally:
        engine.dispose()
    assert "01-app-role.sh" in str(excinfo.value)
    assert "0026" not in str(excinfo.value)  # no llegó a ejecutar ninguna sentencia


# --- Spec 017, T5: 0027_plataforma_usuarios ------------------------------------------------

MIGRATION_0027 = BACKEND_DIR / "migrations" / "versions" / "0027_plataforma_usuarios.py"


def _refresh_owner_columns(url: URL) -> list[tuple[str, str, str, str]]:
    """Privilegios por columna de ``plataforma_owner`` en ``refresh_token`` (0027)."""
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            return sorted(
                tuple(row)
                for row in conn.execute(
                    text(
                        "select grantee, table_name, column_name, privilege_type "
                        "from information_schema.column_privileges "
                        "where table_schema = 'public' and table_name = 'refresh_token' "
                        "and grantee = 'plataforma_owner'"
                    )
                )
            )
    finally:
        engine.dispose()


def test_0027_up_down_up_touches_only_its_objects(migrate_env):
    config = alembic_config()
    command.upgrade(config, SESIONES_VALIDAS_DESDE)
    tables_before = _public_state(migrate_env)[0]
    before = _empresas_state(migrate_env)
    refresh_before = _refresh_owner_columns(migrate_env)
    assert refresh_before == []

    command.upgrade(config, PLATAFORMA_USUARIOS)
    after = _empresas_state(migrate_env)
    assert _public_state(migrate_env) == (tables_before, [PLATAFORMA_USUARIOS])
    assert sorted(after["bodies"]) == USUARIOS_HEAD_FUNCTION_NAMES
    for name in before["bodies"]:
        assert after["bodies"][name] == before["bodies"][name], name
        assert after["acls"][name] == before["acls"][name], name
    added = sorted(set(after["policies"]) - set(before["policies"]))
    assert set(before["policies"]) <= set(after["policies"])
    assert sorted(p[1] for p in added) == sorted(
        [
            "dueno_plat_membresia_estado",
            "dueno_plat_membresia_estado_leer",
            "dueno_plat_membresia_usuarios",
            "dueno_plat_refresh_membresia_leer",
            "dueno_plat_refresh_membresia_revocar",
            "dueno_plat_tenant_membresia",
            "dueno_plat_tenant_usuarios",
            "dueno_plat_usuario_usuarios",
        ]
    )
    assert all(p[2] == "{plataforma_owner}" for p in added)
    assert after["tenant_acl"] == before["tenant_acl"]
    assert after["tenant_columns"] == before["tenant_columns"]
    new_owner = sorted(set(after["owner_columns"]) - set(before["owner_columns"]))
    assert new_owner == sorted(
        [
            ("plataforma_owner", "membresia", "activa", "UPDATE"),
            ("plataforma_owner", "membresia", "id", "SELECT"),
            ("plataforma_owner", "membresia", "usuario_id", "SELECT"),
            ("plataforma_owner", "usuario", "debe_cambiar_password", "SELECT"),
            ("plataforma_owner", "usuario", "email", "SELECT"),
            ("plataforma_owner", "usuario", "id", "SELECT"),
            ("plataforma_owner", "usuario", "nombre", "SELECT"),
            ("plataforma_owner", "refresh_token", "membresia_id", "SELECT"),
            ("plataforma_owner", "refresh_token", "revocado_en", "SELECT"),
            ("plataforma_owner", "refresh_token", "revocado_en", "UPDATE"),
            ("plataforma_owner", "refresh_token", "tenant_id", "SELECT"),
        ]
    )
    assert set(before["owner_columns"]) <= set(after["owner_columns"])
    assert after["leftovers"] == (False, False, 0)

    command.downgrade(config, SESIONES_VALIDAS_DESDE)
    assert _public_state(migrate_env) == (tables_before, [SESIONES_VALIDAS_DESDE])
    assert _empresas_state(migrate_env) == before
    assert _refresh_owner_columns(migrate_env) == refresh_before

    command.upgrade(config, PLATAFORMA_USUARIOS)
    assert _empresas_state(migrate_env) == after


def test_0027_downgrade_keeps_the_deactivated_memberships(migrate_env):
    # El downgrade no borra datos: una membresía desactivada sigue desactivada.
    config = alembic_config()
    command.upgrade(config, PLATAFORMA_USUARIOS)
    tenant, admin, contador = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    engine = create_engine(migrate_env, poolclass=NullPool)
    try:
        with engine.begin() as conn:
            for table in ("tenant", "usuario", "membresia"):
                conn.exec_driver_sql(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            conn.execute(
                text("insert into tenant (id, nombre) values (:t, 'Clínica 0027')"), {"t": tenant}
            )
            for usuario, rol in ((admin, "admin"), (contador, "contador")):
                conn.execute(
                    text(
                        "insert into usuario (id, email, nombre, password_hash) "
                        "values (:u, :e, 'Persona 0027', 'h')"
                    ),
                    {"u": usuario, "e": f"{rol}.0027@ejemplo.test"},
                )
                conn.execute(
                    text(
                        "insert into membresia (tenant_id, usuario_id, rol, activa) "
                        "values (:t, :u, :r, :a)"
                    ),
                    {"t": tenant, "u": usuario, "r": rol, "a": rol == "admin"},
                )
            for table in ("tenant", "usuario", "membresia"):
                conn.exec_driver_sql(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        command.downgrade(config, SESIONES_VALIDAS_DESDE)
        with engine.connect() as conn:
            conn.exec_driver_sql("ALTER TABLE membresia NO FORCE ROW LEVEL SECURITY")
            rows = sorted(
                tuple(row)
                for row in conn.execute(
                    text("select rol, activa from membresia where tenant_id = :t"), {"t": tenant}
                )
            )
            conn.rollback()
    finally:
        engine.dispose()
    assert rows == [("admin", True), ("contador", False)]


def test_0027_failed_statement_does_not_leak_the_sql(migration_database_url):
    migration = _load_migration(MIGRATION_0027, "migration_0027_leak")
    secret = f"centinela_{uuid.uuid4().hex[:8]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            with pytest.raises(RuntimeError) as excinfo:
                migration.execute_statements(conn, [f'GRANT SELECT ON no_existe TO "{secret}"'])
    finally:
        engine.dispose()
    message = str(excinfo.value)
    assert "0027" in message
    assert "centinela" not in message
    assert excinfo.value.__cause__ is None


@pytest.mark.parametrize("step", ["upgrade", "downgrade"])
def test_0027_without_plataforma_owner_fails_with_a_clear_message(
    migration_database_url, app_database_url, monkeypatch, step
):
    migration = _load_migration(MIGRATION_0027, "migration_0027_owner")
    monkeypatch.setenv(APP_ROLE_VAR, app_database_url.username)
    missing = f"dueno_falta_{uuid.uuid4().hex[:6]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                monkeypatch.setattr(migration, "op", _FakeOp(conn))
                monkeypatch.setattr(migration, "PLATAFORMA_OWNER", missing)
                with pytest.raises(RuntimeError) as excinfo:
                    getattr(migration, step)()
            finally:
                tx.rollback()
    finally:
        engine.dispose()
    assert "01-app-role.sh" in str(excinfo.value)
    assert "0027" not in str(excinfo.value)  # no llegó a ejecutar ninguna sentencia


def test_0027_bodies_clear_every_platform_guc_and_reuse_the_0018_check():
    migration = _load_migration(MIGRATION_0027, "migration_0027_bodies")
    migration_0018 = _load_migration_0018()
    # Las diez GUC de 0017 y 0018 más las tres de aquí, en el mismo orden.
    assert migration.OWNER_GUCS[: len(migration_0018.OWNER_GUCS)] == migration_0018.OWNER_GUCS
    assert len(migration.OWNER_GUCS) == len(migration_0018.OWNER_GUCS) + 3
    assert migration._HEADER == migration_0018._HEADER
    assert migration._DESARROLLADOR_ACTIVO == migration_0018._DESARROLLADOR_ACTIVO
    for statement in migration.CREATE_STATEMENTS:
        cuerpo = statement.split("$fn$")[1]
        assert cuerpo.count(migration._CLEAR) >= 2
        assert cuerpo.index(migration._DESARROLLADOR_ACTIVO) < cuerpo.index("public.tenant")


# --- Spec 017, T6: 0028_plataforma_actividad -----------------------------------------------

MIGRATION_0028 = BACKEND_DIR / "migrations" / "versions" / "0028_plataforma_actividad.py"


def test_0028_up_down_up_touches_only_its_objects(migrate_env):
    config = alembic_config()
    command.upgrade(config, PLATAFORMA_USUARIOS)
    tables_before = _public_state(migrate_env)[0]
    before = _empresas_state(migrate_env)

    command.upgrade(config, PLATAFORMA_ACTIVIDAD)
    after = _empresas_state(migrate_env)
    assert _public_state(migrate_env) == (tables_before, [PLATAFORMA_ACTIVIDAD])
    assert sorted(after["bodies"]) == ACTIVIDAD_HEAD_FUNCTION_NAMES
    for name in before["bodies"]:
        assert after["bodies"][name] == before["bodies"][name], name
        assert after["acls"][name] == before["acls"][name], name
    added = sorted(set(after["policies"]) - set(before["policies"]))
    assert set(before["policies"]) <= set(after["policies"])
    assert sorted((p[0], p[1]) for p in added) == [
        ("desarrollador", "dueno_plat_desarrollador_actividad"),
        ("plataforma_auditoria", "dueno_plat_auditoria_actividad"),
        ("tenant", "dueno_plat_tenant_actividad"),
    ]
    assert all(p[2] == "{plataforma_owner}" for p in added)
    assert after["tenant_acl"] == before["tenant_acl"]
    assert after["tenant_columns"] == before["tenant_columns"]
    new_owner = sorted(set(after["owner_columns"]) - set(before["owner_columns"]))
    auditoria = (
        "id",
        "desarrollador_id",
        "accion",
        "resultado",
        "tenant_id",
        "objeto_id",
        "creado_en",
    )
    assert new_owner == sorted(
        [
            ("plataforma_owner", "desarrollador", "nombre", "SELECT"),
            *(("plataforma_owner", "plataforma_auditoria", c, "SELECT") for c in auditoria),
        ]
    )
    assert set(before["owner_columns"]) <= set(after["owner_columns"])
    assert after["leftovers"] == (False, False, 0)

    command.downgrade(config, PLATAFORMA_USUARIOS)
    assert _public_state(migrate_env) == (tables_before, [PLATAFORMA_USUARIOS])
    assert _empresas_state(migrate_env) == before

    command.upgrade(config, PLATAFORMA_ACTIVIDAD)
    assert _empresas_state(migrate_env) == after


def test_0028_downgrade_keeps_the_audit_rows(migrate_env):
    # El downgrade no borra datos: la auditoría sigue entera.
    config = alembic_config()
    command.upgrade(config, PLATAFORMA_ACTIVIDAD)
    engine = create_engine(migrate_env, poolclass=NullPool)
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "insert into plataforma_auditoria (accion, resultado) "
                    "values ('desarrollador_creado', 'ok')"
                )
            )
        command.downgrade(config, PLATAFORMA_USUARIOS)
        with engine.connect() as conn:
            count = conn.scalar(text("select count(*) from plataforma_auditoria"))
    finally:
        engine.dispose()
    assert count == 1


def test_0028_failed_statement_does_not_leak_the_sql(migration_database_url):
    migration = _load_migration(MIGRATION_0028, "migration_0028_leak")
    secret = f"centinela_{uuid.uuid4().hex[:8]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            with pytest.raises(RuntimeError) as excinfo:
                migration.execute_statements(conn, [f'GRANT SELECT ON no_existe TO "{secret}"'])
    finally:
        engine.dispose()
    message = str(excinfo.value)
    assert "0028" in message
    assert "centinela" not in message
    assert excinfo.value.__cause__ is None


@pytest.mark.parametrize("step", ["upgrade", "downgrade"])
def test_0028_without_plataforma_owner_fails_with_a_clear_message(
    migration_database_url, app_database_url, monkeypatch, step
):
    migration = _load_migration(MIGRATION_0028, "migration_0028_owner")
    monkeypatch.setenv(APP_ROLE_VAR, app_database_url.username)
    missing = f"dueno_falta_{uuid.uuid4().hex[:6]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                monkeypatch.setattr(migration, "op", _FakeOp(conn))
                monkeypatch.setattr(migration, "PLATAFORMA_OWNER", missing)
                with pytest.raises(RuntimeError) as excinfo:
                    getattr(migration, step)()
            finally:
                tx.rollback()
    finally:
        engine.dispose()
    assert "01-app-role.sh" in str(excinfo.value)
    assert "0028" not in str(excinfo.value)  # no llegó a ejecutar ninguna sentencia


def test_0028_body_clears_every_platform_guc_and_reuses_the_0018_check():
    migration = _load_migration(MIGRATION_0028, "migration_0028_bodies")
    migration_0027 = _load_migration(MIGRATION_0027, "migration_0027_for_0028")
    migration_0018 = _load_migration_0018()
    # Las trece GUC de 0017, 0018 y 0027 más la de aquí, en el mismo orden.
    assert migration.OWNER_GUCS[: len(migration_0027.OWNER_GUCS)] == migration_0027.OWNER_GUCS
    assert migration.OWNER_GUCS[len(migration_0027.OWNER_GUCS) :] == ("app.plat_actividad",)
    assert migration._HEADER == migration_0018._HEADER
    assert migration._DESARROLLADOR_ACTIVO == migration_0018._DESARROLLADOR_ACTIVO
    for statement in migration.CREATE_STATEMENTS:
        cuerpo = statement.split("$fn$")[1]
        assert cuerpo.count(migration._CLEAR) >= 2
        check = cuerpo.index(migration._DESARROLLADOR_ACTIVO)
        assert check < cuerpo.index("public.tenant")
        assert check < cuerpo.index("public.plataforma_auditoria")
        # Solo lectura.
        for palabra in ("INSERT", "UPDATE", "DELETE"):
            assert palabra not in cuerpo, palabra


# --- Spec 017, T7: 0029_plataforma_logo ----------------------------------------------------

MIGRATION_0029 = BACKEND_DIR / "migrations" / "versions" / "0029_plataforma_logo.py"


def test_0029_up_down_up_touches_only_its_objects(migrate_env):
    config = alembic_config()
    command.upgrade(config, PLATAFORMA_ACTIVIDAD)
    tables_before = _public_state(migrate_env)[0]
    before = _empresas_state(migrate_env)

    command.upgrade(config, PLATAFORMA_LOGO)
    after = _empresas_state(migrate_env)
    assert _public_state(migrate_env) == (tables_before, [PLATAFORMA_LOGO])
    assert sorted(after["bodies"]) == LOGO_HEAD_FUNCTION_NAMES
    for name in before["bodies"]:
        assert after["bodies"][name] == before["bodies"][name], name
        assert after["acls"][name] == before["acls"][name], name
    added = sorted(set(after["policies"]) - set(before["policies"]))
    assert set(before["policies"]) <= set(after["policies"])
    assert sorted((p[0], p[1]) for p in added) == [
        ("empresa", "dueno_plat_empresa_logo"),
        ("empresa", "dueno_plat_empresa_logo_leer"),
        ("empresa_logo", "dueno_plat_empresa_logo_crear"),
        ("membresia", "dueno_plat_membresia_logo"),
        ("tenant", "dueno_plat_tenant_logo"),
    ]
    assert all(p[2] == "{plataforma_owner}" for p in added)
    assert after["tenant_acl"] == before["tenant_acl"]
    assert after["tenant_columns"] == before["tenant_columns"]
    new_owner = sorted(set(after["owner_columns"]) - set(before["owner_columns"]))
    logo = ("id", "tenant_id", "clave", "bytes", "ancho", "alto", "subido_por")
    assert new_owner == sorted(
        [
            ("plataforma_owner", "empresa", "actualizada_en", "UPDATE"),
            ("plataforma_owner", "empresa", "logo_id", "UPDATE"),
            *(("plataforma_owner", "empresa_logo", c, "INSERT") for c in logo),
        ]
    )
    assert set(before["owner_columns"]) <= set(after["owner_columns"])
    assert after["leftovers"] == (False, False, 0)

    command.downgrade(config, PLATAFORMA_ACTIVIDAD)
    assert _public_state(migrate_env) == (tables_before, [PLATAFORMA_ACTIVIDAD])
    assert _empresas_state(migrate_env) == before

    command.upgrade(config, PLATAFORMA_LOGO)
    assert _empresas_state(migrate_env) == after


def test_0029_downgrade_keeps_the_uploaded_logos(migrate_env):
    # El downgrade no borra datos: el logo subido sigue en empresa_logo y en empresa.
    config = alembic_config()
    command.upgrade(config, PLATAFORMA_LOGO)
    tenant, admin, logo = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    tables = ("tenant", "usuario", "membresia", "empresa", "empresa_logo")
    engine = create_engine(migrate_env, poolclass=NullPool)
    try:
        with engine.begin() as conn:
            for table in tables:
                conn.exec_driver_sql(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            conn.execute(
                text("insert into tenant (id, nombre) values (:t, 'Clínica 0029')"), {"t": tenant}
            )
            conn.execute(
                text(
                    "insert into usuario (id, email, nombre, password_hash) "
                    "values (:u, 'admin.0029@ejemplo.test', 'Persona 0029', 'h')"
                ),
                {"u": admin},
            )
            conn.execute(
                text("insert into membresia (tenant_id, usuario_id, rol) values (:t, :u, 'admin')"),
                {"t": tenant, "u": admin},
            )
            conn.execute(
                text(
                    "insert into empresa_logo (id, tenant_id, clave, bytes, ancho, alto, "
                    "subido_por) values (:l, :t, :c, 1, 1, 1, :u)"
                ),
                {"l": logo, "t": tenant, "c": f"{tenant}/{logo}.png", "u": admin},
            )
            conn.execute(
                text(
                    "insert into empresa (tenant_id, nombre, direccion, logo_id, actualizada_por) "
                    "values (:t, 'Clínica 0029', 'Calle 1', :l, :u)"
                ),
                {"t": tenant, "l": logo, "u": admin},
            )
            for table in tables:
                conn.exec_driver_sql(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        command.downgrade(config, PLATAFORMA_ACTIVIDAD)
        with engine.connect() as conn:
            conn.exec_driver_sql("ALTER TABLE empresa NO FORCE ROW LEVEL SECURITY")
            conn.exec_driver_sql("ALTER TABLE empresa_logo NO FORCE ROW LEVEL SECURITY")
            vigente = conn.scalar(
                text("select logo_id from empresa where tenant_id = :t"), {"t": tenant}
            )
            logos = conn.scalar(
                text("select count(*) from empresa_logo where tenant_id = :t"), {"t": tenant}
            )
            conn.rollback()
    finally:
        engine.dispose()
    assert (vigente, logos) == (logo, 1)


def test_0029_failed_statement_does_not_leak_the_sql(migration_database_url):
    migration = _load_migration(MIGRATION_0029, "migration_0029_leak")
    secret = f"centinela_{uuid.uuid4().hex[:8]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            with pytest.raises(RuntimeError) as excinfo:
                migration.execute_statements(conn, [f'GRANT SELECT ON no_existe TO "{secret}"'])
    finally:
        engine.dispose()
    message = str(excinfo.value)
    assert "0029" in message
    assert "centinela" not in message
    assert excinfo.value.__cause__ is None


@pytest.mark.parametrize("step", ["upgrade", "downgrade"])
def test_0029_without_plataforma_owner_fails_with_a_clear_message(
    migration_database_url, app_database_url, monkeypatch, step
):
    migration = _load_migration(MIGRATION_0029, "migration_0029_owner")
    monkeypatch.setenv(APP_ROLE_VAR, app_database_url.username)
    missing = f"dueno_falta_{uuid.uuid4().hex[:6]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                monkeypatch.setattr(migration, "op", _FakeOp(conn))
                monkeypatch.setattr(migration, "PLATAFORMA_OWNER", missing)
                with pytest.raises(RuntimeError) as excinfo:
                    getattr(migration, step)()
            finally:
                tx.rollback()
    finally:
        engine.dispose()
    assert "01-app-role.sh" in str(excinfo.value)
    assert "0029" not in str(excinfo.value)  # no llegó a ejecutar ninguna sentencia


def test_0029_body_clears_every_platform_guc_and_reuses_the_0018_check():
    migration = _load_migration(MIGRATION_0029, "migration_0029_bodies")
    migration_0028 = _load_migration(MIGRATION_0028, "migration_0028_for_0029")
    migration_0018 = _load_migration_0018()
    # Las catorce GUC de 0017, 0018, 0027 y 0028 más las dos de aquí, en el mismo orden.
    assert migration.OWNER_GUCS[: len(migration_0028.OWNER_GUCS)] == migration_0028.OWNER_GUCS
    assert migration.OWNER_GUCS[len(migration_0028.OWNER_GUCS) :] == (
        "app.plat_logo_tenant",
        "app.plat_logo_id",
    )
    assert migration._HEADER == migration_0018._HEADER
    assert migration._DESARROLLADOR_ACTIVO == migration_0018._DESARROLLADOR_ACTIVO
    for statement in migration.CREATE_STATEMENTS:
        cuerpo = statement.split("$fn$")[1]
        # Al entrar, al salir y en las dos salidas idempotentes.
        assert cuerpo.count(migration._CLEAR) >= 4
        check = cuerpo.index(migration._DESARROLLADOR_ACTIVO)
        for palabra in ("public.empresa", "public.tenant", "public.membresia", "INSERT", "UPDATE"):
            assert check < cuerpo.index(palabra), palabra
        # Nunca borra ni lee la ficha de la empresa.
        assert "DELETE" not in cuerpo
        for columna in ("e.nombre", "e.direccion", "e.nit", "e.telefono", "e.correo"):
            assert columna not in cuerpo, columna


# --- Spec 017, C1 (T12): 0030_plataforma_edicion_empresa -----------------------------------

MIGRATION_0030 = BACKEND_DIR / "migrations" / "versions" / "0030_plataforma_edicion_empresa.py"
_CHECK_ACCION = (
    "select pg_get_constraintdef(oid), convalidated from pg_constraint "
    "where conname = 'plataforma_auditoria_accion_valida'"
)
_ACCIONES_C1 = ("empresa_editada", "empresa_logo_reemplazado", "usuario_editado")


def _audit_check(url: URL) -> tuple[str, bool]:
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            return tuple(conn.execute(text(_CHECK_ACCION)).one())
    finally:
        engine.dispose()


def test_0030_up_down_up_touches_only_its_objects(migrate_env):
    config = alembic_config()
    command.upgrade(config, PLATAFORMA_LOGO)
    tables_before = _public_state(migrate_env)[0]
    before = _empresas_state(migrate_env)
    check_before = _audit_check(migrate_env)

    command.upgrade(config, PLATAFORMA_EDICION)
    after = _empresas_state(migrate_env)
    assert _public_state(migrate_env) == (tables_before, [PLATAFORMA_EDICION])
    assert sorted(after["bodies"]) == EDICION_HEAD_FUNCTION_NAMES
    # Solo cambia el cuerpo de la del logo (rehecha); las demás, intactas.
    logo_fn = "plataforma_registrar_logo"
    for name in set(before["bodies"]) - {logo_fn}:
        assert after["bodies"][name] == before["bodies"][name], name
        assert after["acls"][name] == before["acls"][name], name
    assert after["bodies"][logo_fn] != before["bodies"][logo_fn]
    assert after["acls"][logo_fn] == before["acls"][logo_fn]
    added = sorted(set(after["policies"]) - set(before["policies"]))
    removed = sorted(set(before["policies"]) - set(after["policies"]))
    # Cambian la de logo (sin logo_id IS NULL) y la de inserción de auditoría (tres acciones).
    assert sorted((p[0], p[1]) for p in removed) == [
        ("empresa", "dueno_plat_empresa_logo"),
        ("plataforma_auditoria", "plataforma_auditoria_insertar"),
    ]
    assert sorted((p[0], p[1]) for p in added) == [
        ("empresa", "dueno_plat_empresa_ficha"),
        ("empresa", "dueno_plat_empresa_ficha_leer"),
        ("empresa", "dueno_plat_empresa_logo"),
        ("plataforma_auditoria", "plataforma_auditoria_insertar"),
        ("tenant", "dueno_plat_tenant_ficha"),
        ("tenant", "dueno_plat_tenant_ficha_leer"),
    ]
    logo = next(p for p in added if p[1] == "dueno_plat_empresa_logo")
    assert "logo_id IS NULL" not in logo[3]
    insertar = next(p for p in added if p[1] == "plataforma_auditoria_insertar")
    for accion in _ACCIONES_C1:
        assert f"'{accion}'" in insertar[4], accion
    assert all(
        p[2] == "{plataforma_owner}" for p in added if p[1] != "plataforma_auditoria_insertar"
    )
    assert after["tenant_acl"] == before["tenant_acl"]
    new_owner = sorted(set(after["owner_columns"]) - set(before["owner_columns"]))
    ficha = ("nombre", "direccion", "nit", "telefono", "correo")
    assert new_owner == sorted(
        [
            *(("plataforma_owner", "empresa", c, "SELECT") for c in ficha),
            *(("plataforma_owner", "empresa", c, "UPDATE") for c in ficha),
            ("plataforma_owner", "tenant", "nombre", "UPDATE"),
        ]
    )
    assert set(before["owner_columns"]) <= set(after["owner_columns"])
    assert sorted(set(after["tenant_columns"]) - set(before["tenant_columns"])) == [
        ("plataforma_owner", "nombre", "UPDATE")
    ]
    assert after["leftovers"] == (False, False, 0)
    check_after = _audit_check(migrate_env)
    assert check_after[1] is True
    assert check_after[0] != check_before[0]
    for accion in _ACCIONES_C1:
        assert f"'{accion}'" in check_after[0], accion

    command.downgrade(config, PLATAFORMA_LOGO)
    assert _public_state(migrate_env) == (tables_before, [PLATAFORMA_LOGO])
    assert _empresas_state(migrate_env) == before
    assert _audit_check(migrate_env) == check_before

    command.upgrade(config, PLATAFORMA_EDICION)
    assert _empresas_state(migrate_env) == after
    assert _audit_check(migrate_env) == check_after


def test_0030_downgrade_keeps_the_c1_audit_rows(migrate_env):
    # El downgrade no borra datos: la auditoría de C1 se conserva (el CHECK de antes vuelve
    # NOT VALID: rige para filas nuevas) y se puede volver a subir.
    config = alembic_config()
    command.upgrade(config, PLATAFORMA_EDICION)
    tenant = uuid.uuid4()
    _insert_bypassing_rls(
        migrate_env,
        "tenant",
        "insert into tenant (id, nombre) values (:t, 'Clínica 0030')",
        {"t": tenant},
    )
    _insert_bypassing_rls(
        migrate_env,
        "plataforma_auditoria",
        "insert into plataforma_auditoria (accion, resultado, tenant_id) "
        "values ('empresa_editada', 'ok', :t)",
        {"t": tenant},
    )
    command.downgrade(config, PLATAFORMA_LOGO)
    engine = create_engine(migrate_env, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("ALTER TABLE plataforma_auditoria NO FORCE ROW LEVEL SECURITY")
            filas_c1 = conn.scalar(
                text("select count(*) from plataforma_auditoria where tenant_id = :t"),
                {"t": tenant},
            )
            conn.rollback()
    finally:
        engine.dispose()
    assert filas_c1 == 1
    definicion, validada = _audit_check(migrate_env)
    assert validada is False
    assert "'empresa_editada'" not in definicion
    command.upgrade(config, PLATAFORMA_EDICION)
    assert _audit_check(migrate_env)[1] is True


def test_0030_failed_statement_does_not_leak_the_sql(migration_database_url):
    migration = _load_migration(MIGRATION_0030, "migration_0030_leak")
    secret = f"centinela_{uuid.uuid4().hex[:8]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            with pytest.raises(RuntimeError) as excinfo:
                migration.execute_statements(conn, [f'GRANT SELECT ON no_existe TO "{secret}"'])
    finally:
        engine.dispose()
    message = str(excinfo.value)
    assert "0030" in message
    assert "centinela" not in message
    assert excinfo.value.__cause__ is None


@pytest.mark.parametrize("step", ["upgrade", "downgrade"])
def test_0030_without_plataforma_owner_fails_with_a_clear_message(
    migration_database_url, app_database_url, monkeypatch, step
):
    migration = _load_migration(MIGRATION_0030, "migration_0030_owner")
    monkeypatch.setenv(APP_ROLE_VAR, app_database_url.username)
    missing = f"dueno_falta_{uuid.uuid4().hex[:6]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                monkeypatch.setattr(migration, "op", _FakeOp(conn))
                monkeypatch.setattr(migration, "PLATAFORMA_OWNER", missing)
                with pytest.raises(RuntimeError) as excinfo:
                    getattr(migration, step)()
            finally:
                tx.rollback()
    finally:
        engine.dispose()
    assert "01-app-role.sh" in str(excinfo.value)
    assert "0030" not in str(excinfo.value)  # no llegó a ejecutar ninguna sentencia


def test_0030_bodies_clear_every_platform_guc_and_restore_0029_and_0018_exactly():
    migration = _load_migration(MIGRATION_0030, "migration_0030_bodies")
    migration_0029 = _load_migration(MIGRATION_0029, "migration_0029_for_0030")
    migration_0018 = _load_migration_0018()
    # Las dieciséis GUC de 0017–0029 más la de aquí, en el mismo orden.
    assert migration.OWNER_GUCS_0029 == migration_0029.OWNER_GUCS
    assert migration.OWNER_GUCS == (*migration_0029.OWNER_GUCS, "app.plat_empresa_tenant")
    assert migration._HEADER == migration_0018._HEADER
    assert migration._DESARROLLADOR_ACTIVO == migration_0018._DESARROLLADOR_ACTIVO
    # El downgrade recrea la función de 0029 con su mismo cuerpo, y la política de
    # auditoría y la lista de acciones de 0018 con el mismo texto.
    assert migration.RESTORE_REGISTRAR_0029 == migration_0029.CREATE_REGISTRAR
    assert migration.ACCIONES_APP_0018 == migration_0018.ACCIONES_APP
    assert migration._audit_policy('"app"', migration.ACCIONES_APP_0018) == (
        migration_0018._audit_policy('"app"', migration_0018.ACCIONES_APP)
    )
    for statement in migration.CREATE_STATEMENTS:
        cuerpo = statement.split("$fn$")[1]
        assert cuerpo.count(migration._CLEAR) >= 2
        check = cuerpo.index(migration._DESARROLLADOR_ACTIVO)
        for palabra in ("public.empresa", "public.tenant", "UPDATE", "RETURN QUERY", "RETURN v_"):
            if palabra in cuerpo:
                assert check < cuerpo.index(palabra), palabra
        # Nunca borra, nunca lee ni escribe actualizada_por, ni toca activo/desactivado_*.
        for prohibido in ("DELETE", "actualizada_por", "activo =", "desactivado_"):
            assert prohibido not in cuerpo, prohibido


# --- Spec 017, C1 (T13): 0031_plataforma_editar_usuario -----------------------------------

MIGRATION_0031 = BACKEND_DIR / "migrations" / "versions" / "0031_plataforma_editar_usuario.py"


def test_0031_up_down_up_touches_only_its_objects(migrate_env):
    config = alembic_config()
    command.upgrade(config, PLATAFORMA_EDICION)
    tables_before = _public_state(migrate_env)[0]
    before = _empresas_state(migrate_env)
    check_before = _audit_check(migrate_env)

    command.upgrade(config, PLATAFORMA_EDITAR_USUARIO)
    after = _empresas_state(migrate_env)
    assert _public_state(migrate_env) == (tables_before, [PLATAFORMA_EDITAR_USUARIO])
    assert sorted(after["bodies"]) == EDITAR_USUARIO_HEAD_FUNCTION_NAMES
    for name in before["bodies"]:
        assert after["bodies"][name] == before["bodies"][name], name
        assert after["acls"][name] == before["acls"][name], name
    assert set(before["policies"]) <= set(after["policies"])
    added = sorted(set(after["policies"]) - set(before["policies"]))
    assert sorted((p[0], p[1]) for p in added) == [
        ("usuario", "dueno_plat_usuario_edicion"),
        ("usuario", "dueno_plat_usuario_edicion_leer"),
    ]
    assert all(p[2] == "{plataforma_owner}" for p in added)
    # Ni la ACL ni las columnas de tenant cambian; la auditoría ya admitía usuario_editado.
    assert after["tenant_acl"] == before["tenant_acl"]
    assert after["tenant_columns"] == before["tenant_columns"]
    assert _audit_check(migrate_env) == check_before
    new_owner = sorted(set(after["owner_columns"]) - set(before["owner_columns"]))
    assert new_owner == [
        ("plataforma_owner", "membresia", "rol", "UPDATE"),
        ("plataforma_owner", "usuario", "nombre", "UPDATE"),
    ]
    assert set(before["owner_columns"]) <= set(after["owner_columns"])
    assert after["leftovers"] == (False, False, 0)

    command.downgrade(config, PLATAFORMA_EDICION)
    assert _public_state(migrate_env) == (tables_before, [PLATAFORMA_EDICION])
    assert _empresas_state(migrate_env) == before

    command.upgrade(config, PLATAFORMA_EDITAR_USUARIO)
    assert _empresas_state(migrate_env) == after


def test_0031_downgrade_keeps_the_edited_names_and_roles(migrate_env):
    # El downgrade no borra datos: el nombre y el rol editados se conservan.
    config = alembic_config()
    command.upgrade(config, PLATAFORMA_EDITAR_USUARIO)
    tenant, usuario = uuid.uuid4(), uuid.uuid4()
    engine = create_engine(migrate_env, poolclass=NullPool)
    tables = ("tenant", "usuario", "membresia")
    try:
        with engine.begin() as conn:
            for table in tables:
                conn.exec_driver_sql(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            conn.execute(
                text("insert into tenant (id, nombre) values (:t, 'Clínica 0031')"), {"t": tenant}
            )
            conn.execute(
                text(
                    "insert into usuario (id, email, nombre, password_hash) "
                    "values (:u, 'persona.0031@ejemplo.test', 'Editada 0031', 'h')"
                ),
                {"u": usuario},
            )
            conn.execute(
                text("insert into membresia (tenant_id, usuario_id, rol) values (:t, :u, 'admin')"),
                {"t": tenant, "u": usuario},
            )
            for table in tables:
                conn.exec_driver_sql(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        command.downgrade(config, PLATAFORMA_EDICION)
        with engine.connect() as conn:
            for table in ("usuario", "membresia"):
                conn.exec_driver_sql(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            fila = conn.execute(
                text(
                    "select u.nombre, m.rol from usuario u join membresia m on m.usuario_id = u.id "
                    "where u.id = :u"
                ),
                {"u": usuario},
            ).one()
            conn.rollback()
    finally:
        engine.dispose()
    assert tuple(fila) == ("Editada 0031", "admin")


def test_0031_failed_statement_does_not_leak_the_sql(migration_database_url):
    migration = _load_migration(MIGRATION_0031, "migration_0031_leak")
    secret = f"centinela_{uuid.uuid4().hex[:8]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            with pytest.raises(RuntimeError) as excinfo:
                migration.execute_statements(conn, [f'GRANT SELECT ON no_existe TO "{secret}"'])
    finally:
        engine.dispose()
    message = str(excinfo.value)
    assert "0031" in message
    assert "centinela" not in message
    assert excinfo.value.__cause__ is None


@pytest.mark.parametrize("step", ["upgrade", "downgrade"])
def test_0031_without_plataforma_owner_fails_with_a_clear_message(
    migration_database_url, app_database_url, monkeypatch, step
):
    migration = _load_migration(MIGRATION_0031, "migration_0031_owner")
    monkeypatch.setenv(APP_ROLE_VAR, app_database_url.username)
    missing = f"dueno_falta_{uuid.uuid4().hex[:6]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                monkeypatch.setattr(migration, "op", _FakeOp(conn))
                monkeypatch.setattr(migration, "PLATAFORMA_OWNER", missing)
                with pytest.raises(RuntimeError) as excinfo:
                    getattr(migration, step)()
            finally:
                tx.rollback()
    finally:
        engine.dispose()
    assert "01-app-role.sh" in str(excinfo.value)
    assert "0031" not in str(excinfo.value)  # no llegó a ejecutar ninguna sentencia


def test_0031_body_clears_every_platform_guc_and_reuses_the_0027_lock_and_checks():
    migration = _load_migration(MIGRATION_0031, "migration_0031_bodies")
    migration_0030 = _load_migration(MIGRATION_0030, "migration_0030_for_0031")
    migration_0027 = _load_migration(MIGRATION_0027, "migration_0027_for_0031")
    migration_0018 = _load_migration_0018()
    # Las diecisiete GUC de 0017–0030 más la de aquí, en el mismo orden.
    assert migration.OWNER_GUCS_0030 == migration_0030.OWNER_GUCS
    assert migration.OWNER_GUCS == (*migration_0030.OWNER_GUCS, "app.plat_usuario_edicion")
    assert migration._HEADER == migration_0018._HEADER
    assert migration._DESARROLLADOR_ACTIVO == migration_0018._DESARROLLADOR_ACTIVO
    assert migration.LOCK_TIMEOUT == migration_0027.LOCK_TIMEOUT
    assert migration.REVOKE_MAX_PASSES == migration_0027.REVOKE_MAX_PASSES
    (statement,) = migration.CREATE_STATEMENTS
    cuerpo = statement.split("$fn$")[1]
    estado = migration_0027.CREATE_CAMBIAR_ESTADO.split("$fn$")[1]
    assert cuerpo.count(migration._CLEAR) >= 2
    check = cuerpo.index(migration._DESARROLLADOR_ACTIVO)
    for palabra in ("public.tenant", "public.membresia", "public.usuario", "UPDATE"):
        assert check < cuerpo.index(palabra), palabra
    # El mismo candado, los mismos rechazos y la misma revocación que desactivar (0027).
    for fragmento in (
        "pg_catalog.hashtextextended('plataforma_membresia:' || p_tenant::text, 0)",
        "MESSAGE = 'empresa_no_encontrada'",
        "MESSAGE = 'usuario_no_encontrado'",
        "MESSAGE = 'empresa_inactiva'",
        "MESSAGE = 'ultimo_admin'",
        "MESSAGE = 'membresia_ocupada'",
        "UPDATE public.refresh_token AS t SET revocado_en = pg_catalog.now()",
    ):
        assert fragmento in cuerpo and fragmento in estado, fragmento
    orden = [
        cuerpo.index(f"MESSAGE = '{c}'")
        for c in (
            "empresa_no_encontrada",
            "usuario_no_encontrado",
            "empresa_inactiva",
            "ultimo_admin",
        )
    ]
    assert orden == sorted(orden)
    # Nunca borra ni toca correo, contraseña, marcas, estado ni el tenant.
    for prohibido in (
        "DELETE",
        "INSERT",
        "u.email",
        "password_hash",
        "debe_cambiar_password",
        "sesiones_validas_desde",
        "SET activa",
        "UPDATE public.tenant",
        "set_config('app.plat_tenant_estado'",
        "set_config('app.plat_empresa_tenant'",
    ):
        assert prohibido not in cuerpo, prohibido


# --- Spec 017, C1b (T16): 0032_plataforma_password_usuario ---------------------------------

MIGRATION_0032 = BACKEND_DIR / "migrations" / "versions" / "0032_plataforma_password_usuario.py"
MIGRATION_0031_FOR_0032 = MIGRATION_0031
_ACCION_C1B = "usuario_contrasena_restablecida"


def test_0032_up_down_up_touches_only_its_objects(migrate_env):
    config = alembic_config()
    command.upgrade(config, PLATAFORMA_EDITAR_USUARIO)
    tables_before = _public_state(migrate_env)[0]
    before = _empresas_state(migrate_env)
    check_before = _audit_check(migrate_env)

    command.upgrade(config, PLATAFORMA_PASSWORD_USUARIO)
    after = _empresas_state(migrate_env)
    assert _public_state(migrate_env) == (tables_before, [PLATAFORMA_PASSWORD_USUARIO])
    assert sorted(after["bodies"]) == PASSWORD_USUARIO_HEAD_FUNCTION_NAMES
    for name in before["bodies"]:
        assert after["bodies"][name] == before["bodies"][name], name
        assert after["acls"][name] == before["acls"][name], name
    added = sorted(set(after["policies"]) - set(before["policies"]))
    removed = sorted(set(before["policies"]) - set(after["policies"]))
    # Solo cambia la de inserción de auditoría (una acción más); cinco del dueño nuevas.
    assert [(p[0], p[1]) for p in removed] == [
        ("plataforma_auditoria", "plataforma_auditoria_insertar")
    ]
    assert sorted((p[0], p[1]) for p in added) == [
        ("membresia", "dueno_plat_membresia_password"),
        ("plataforma_auditoria", "plataforma_auditoria_insertar"),
        ("refresh_token", "dueno_plat_refresh_password_leer"),
        ("refresh_token", "dueno_plat_refresh_password_revocar"),
        ("usuario", "dueno_plat_usuario_password"),
        ("usuario", "dueno_plat_usuario_password_leer"),
    ]
    insertar = next(p for p in added if p[1] == "plataforma_auditoria_insertar")
    assert f"'{_ACCION_C1B}'" in insertar[4]
    assert all(
        p[2] == "{plataforma_owner}" for p in added if p[1] != "plataforma_auditoria_insertar"
    )
    assert after["tenant_acl"] == before["tenant_acl"]
    assert after["tenant_columns"] == before["tenant_columns"]
    new_owner = sorted(set(after["owner_columns"]) - set(before["owner_columns"]))
    # Solo UPDATE de las tres columnas de la contraseña temporal; nunca SELECT del hash.
    assert new_owner == sorted(
        ("plataforma_owner", "usuario", column, "UPDATE")
        for column in ("password_hash", "debe_cambiar_password", "sesiones_validas_desde")
    )
    assert set(before["owner_columns"]) <= set(after["owner_columns"])
    assert ("plataforma_owner", "usuario", "password_hash", "SELECT") not in after["owner_columns"]
    assert after["leftovers"] == (False, False, 0)
    check_after = _audit_check(migrate_env)
    assert check_after[1] is True
    assert f"'{_ACCION_C1B}'" in check_after[0]
    assert f"'{_ACCION_C1B}'" not in check_before[0]

    command.downgrade(config, PLATAFORMA_EDITAR_USUARIO)
    assert _public_state(migrate_env) == (tables_before, [PLATAFORMA_EDITAR_USUARIO])
    assert _empresas_state(migrate_env) == before
    assert _audit_check(migrate_env) == check_before

    command.upgrade(config, PLATAFORMA_PASSWORD_USUARIO)
    assert _empresas_state(migrate_env) == after
    assert _audit_check(migrate_env) == check_after


def test_0032_downgrade_keeps_the_passwords_the_flag_and_the_audit(migrate_env):
    # El downgrade no borra datos: la contraseña definida, la marca, el corte y la auditoría
    # de C1b se conservan (el CHECK de antes vuelve NOT VALID: rige para filas nuevas).
    config = alembic_config()
    command.upgrade(config, PLATAFORMA_PASSWORD_USUARIO)
    tenant, usuario = uuid.uuid4(), uuid.uuid4()
    engine = create_engine(migrate_env, poolclass=NullPool)
    tables = ("tenant", "usuario", "membresia")
    try:
        with engine.begin() as conn:
            for table in tables:
                conn.exec_driver_sql(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            conn.execute(
                text("insert into tenant (id, nombre) values (:t, 'Clínica 0032')"), {"t": tenant}
            )
            conn.execute(
                text(
                    "insert into usuario (id, email, nombre, password_hash, "
                    "debe_cambiar_password, sesiones_validas_desde) "
                    "values (:u, 'persona.0032@ejemplo.test', 'Persona 0032', 'h-0032', true, "
                    "now())"
                ),
                {"u": usuario},
            )
            conn.execute(
                text("insert into membresia (tenant_id, usuario_id, rol) values (:t, :u, 'admin')"),
                {"t": tenant, "u": usuario},
            )
            for table in tables:
                conn.exec_driver_sql(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        _insert_bypassing_rls(
            migrate_env,
            "plataforma_auditoria",
            "insert into plataforma_auditoria (accion, resultado, tenant_id, objeto_id) "
            "values ('usuario_contrasena_restablecida', 'ok', :t, :u)",
            {"t": tenant, "u": usuario},
        )
        command.downgrade(config, PLATAFORMA_EDITAR_USUARIO)
        with engine.connect() as conn:
            for table in ("usuario", "plataforma_auditoria"):
                conn.exec_driver_sql(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
            fila = conn.execute(
                text(
                    "select password_hash, debe_cambiar_password, "
                    "sesiones_validas_desde is not null from usuario where id = :u"
                ),
                {"u": usuario},
            ).one()
            filas_c1b = conn.scalar(
                text("select count(*) from plataforma_auditoria where tenant_id = :t"),
                {"t": tenant},
            )
            conn.rollback()
    finally:
        engine.dispose()
    assert tuple(fila) == ("h-0032", True, True)
    assert filas_c1b == 1
    definicion, validada = _audit_check(migrate_env)
    assert validada is False
    assert f"'{_ACCION_C1B}'" not in definicion
    command.upgrade(config, PLATAFORMA_PASSWORD_USUARIO)
    assert _audit_check(migrate_env)[1] is True


def test_0032_failed_statement_does_not_leak_the_sql(migration_database_url):
    migration = _load_migration(MIGRATION_0032, "migration_0032_leak")
    secret = f"centinela_{uuid.uuid4().hex[:8]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            with pytest.raises(RuntimeError) as excinfo:
                migration.execute_statements(conn, [f'GRANT SELECT ON no_existe TO "{secret}"'])
    finally:
        engine.dispose()
    message = str(excinfo.value)
    assert "0032" in message
    assert "centinela" not in message
    assert excinfo.value.__cause__ is None


@pytest.mark.parametrize("step", ["upgrade", "downgrade"])
def test_0032_without_plataforma_owner_fails_with_a_clear_message(
    migration_database_url, app_database_url, monkeypatch, step
):
    migration = _load_migration(MIGRATION_0032, "migration_0032_owner")
    monkeypatch.setenv(APP_ROLE_VAR, app_database_url.username)
    missing = f"dueno_falta_{uuid.uuid4().hex[:6]}"
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                monkeypatch.setattr(migration, "op", _FakeOp(conn))
                monkeypatch.setattr(migration, "PLATAFORMA_OWNER", missing)
                with pytest.raises(RuntimeError) as excinfo:
                    getattr(migration, step)()
            finally:
                tx.rollback()
    finally:
        engine.dispose()
    assert "01-app-role.sh" in str(excinfo.value)
    assert "0032" not in str(excinfo.value)  # no llegó a ejecutar ninguna sentencia


def test_0032_body_clears_every_platform_guc_and_reuses_the_0027_lock_and_checks():
    migration = _load_migration(MIGRATION_0032, "migration_0032_bodies")
    migration_0031 = _load_migration(MIGRATION_0031_FOR_0032, "migration_0031_for_0032")
    migration_0030 = _load_migration(MIGRATION_0030, "migration_0030_for_0032")
    migration_0027 = _load_migration(MIGRATION_0027, "migration_0027_for_0032")
    migration_0026 = _load_migration(
        BACKEND_DIR / "migrations" / "versions" / "0026_sesiones_validas_desde.py",
        "migration_0026_for_0032",
    )
    migration_0018 = _load_migration_0018()
    # Las dieciocho GUC de 0017–0031 más la de aquí (propia: ni la de 0031 ni otra), en orden.
    assert migration.OWNER_GUCS_0031 == migration_0031.OWNER_GUCS
    assert migration.OWNER_GUCS == (*migration_0031.OWNER_GUCS, "app.plat_usuario_password")
    assert migration._HEADER == migration_0018._HEADER
    assert migration._DESARROLLADOR_ACTIVO == migration_0018._DESARROLLADOR_ACTIVO
    assert migration.LOCK_TIMEOUT == migration_0027.LOCK_TIMEOUT
    assert migration.REVOKE_MAX_PASSES == migration_0027.REVOKE_MAX_PASSES
    assert migration._HASH_FORMAT == migration_0026._HASH_FORMAT
    # El downgrade vuelve a la política y a la lista de acciones de 0030 con el mismo texto.
    assert migration.ACCIONES_APP_0030 == migration_0030.ACCIONES_APP
    assert migration.ACCIONES_0030 == migration_0030.ACCIONES
    assert migration._audit_policy('"app"', migration.ACCIONES_APP_0030) == (
        migration_0030._audit_policy('"app"', migration_0030.ACCIONES_APP)
    )
    (statement,) = migration.CREATE_STATEMENTS
    cuerpo = statement.split("$fn$")[1]
    estado = migration_0027.CREATE_CAMBIAR_ESTADO.split("$fn$")[1]
    assert "RETURNS void" in statement
    assert cuerpo.count(migration._CLEAR) >= 2
    check = cuerpo.index(migration._DESARROLLADOR_ACTIVO)
    palabras = ("public.tenant", "public.membresia", "public.usuario", "UPDATE", "hash_invalido")
    for palabra in palabras:
        assert check < cuerpo.index(palabra), palabra
    # El formato del hash se valida antes de tocar ninguna tabla de negocio.
    assert cuerpo.index("hash_invalido") < cuerpo.index("public.tenant")
    # El mismo candado (de cada empresa del usuario), los mismos rechazos y la misma
    # revocación acotada que desactivar (0027).
    assert "pg_catalog.hashtextextended('plataforma_membresia:' || v_empresa::text, 0)" in cuerpo
    assert "ORDER BY m.tenant_id" in cuerpo
    for fragmento in (
        "MESSAGE = 'empresa_no_encontrada'",
        "MESSAGE = 'usuario_no_encontrado'",
        "MESSAGE = 'empresa_inactiva'",
        "MESSAGE = 'membresia_ocupada'",
        "UPDATE public.refresh_token AS t SET revocado_en = pg_catalog.now()",
        "EXCEPTION WHEN lock_not_available THEN",
    ):
        assert fragmento in cuerpo and fragmento in estado, fragmento
    orden = [
        cuerpo.index(f"MESSAGE = '{c}'")
        for c in ("empresa_no_encontrada", "usuario_no_encontrado", "empresa_inactiva")
    ]
    assert orden == sorted(orden)
    # Nunca borra, inserta ni toca el correo, el nombre, el estado, el rol ni el tenant;
    # nunca la GUC de edición de 0031, la de membresía-usuario de 0027 ni la de estado.
    for prohibido in (
        "DELETE",
        "INSERT",
        "u.email",
        "email =",
        "nombre",
        "SET activa",
        "u.activo",
        "SET rol",
        "UPDATE public.tenant",
        "UPDATE public.membresia",
        "set_config('app.plat_usuario_edicion'",
        "set_config('app.plat_membresia_usuario'",
        "set_config('app.plat_tenant_estado'",
        "set_config('app.plat_empresa_tenant'",
        "u.password_hash",
    ):
        assert prohibido not in cuerpo, prohibido
