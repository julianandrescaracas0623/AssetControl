"""Catálogo y comportamiento en base de la migración ``0017_plataforma`` (spec 017, T1).

Cubre A4 (parte: funciones de 0017), A10 (auditoría de solo inserción), A13 (parte: el
rol de la aplicación no ejecuta las funciones del operador), A15 (parte: tablas nuevas,
``tenant.activo`` y ``usuario.debe_cambiar_password`` en el catálogo de RLS) y R33–R34
(lista cerrada de acciones, sin datos personales).

Sobre una base temporal migrada a ``head`` (con los roles de Supabase y sus privilegios
por defecto, como ``test_catalog_rls.py``) comprueba leyendo los catálogos:

- Las tres tablas nuevas (excepciones cerradas a «toda tabla lleva ``tenant_id``»): columnas,
  claves, ``CHECK``, índices, RLS habilitada y forzada.
- Políticas: lista cerrada con texto exacto, las de la aplicación sobre las tablas nuevas y
  todas las ``TO plataforma_owner`` (una por comando, nunca ``FOR ALL``).
- ``GRANT`` exactos de la aplicación (nunca ``password_hash``) y de ``plataforma_owner``
  (por columna, sin ``DELETE``, nada en otras tablas); nada para los roles de Supabase.
- ``plataforma_owner`` inerte, sin membresías, con ``USAGE`` y sin ``CREATE`` en ``acceso``.
- Las cuatro funciones de 0017: firma, resultado, ``SECURITY DEFINER``, ``STRICT``,
  ``plpgsql``, dueña ``plataforma_owner``, ``search_path`` fijo, ``proacl`` exacto (la
  aplicación solo ``plataforma_buscar_login``; el migrador las tres del operador) y cuerpo
  exacto (huella ``sha256``), estático, calificado y sin leer GUC.

Y su comportamiento con el rol de la aplicación y el migrador: aislamiento por
``app.desarrollador_id``, auditoría sin ``UPDATE``/``DELETE``, funciones del operador
(crear, restablecer y cambiar estado, con revocación y auditoría con ``desarrollador_id``
nulo) y el login de plataforma. Datos sintéticos (``@ejemplo.test``).
"""

import hashlib
import re
import secrets
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
from sqlalchemy.engine import URL, Connection, Engine
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.pool import NullPool

from app.auth.credentials import ARGON2_TEST_PARAMS

BACKEND_DIR = Path(__file__).resolve().parent.parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
OWNER = "plataforma_owner"
AUTH_OWNER = "auth_owner"
SUPABASE_ROLES = ("anon", "authenticated", "service_role")
PLATFORM_TABLES = ("desarrollador", "plataforma_refresh_token", "plataforma_auditoria")
INSUFFICIENT_PRIVILEGE = "42501"

ACCIONES = [
    "login_ok",
    "empresa_creada",
    "empresa_desactivada",
    "empresa_reactivada",
    "empresa_logo_subido",
    "usuario_desactivado",
    "usuario_reactivado",
    "desarrollador_creado",
    "desarrollador_restablecido",
    "desarrollador_desactivado",
    "desarrollador_reactivado",
]


# --- Texto esperado de pg_policies (espacios normalizados) ---------------------------


def _uuid_guc(guc: str) -> str:
    setting = f"current_setting('{guc}'::text, true)"
    pattern = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    return f"CASE WHEN ({setting} ~ '{pattern}'::text) THEN ({setting})::uuid ELSE NULL::uuid END"


def _text_guc(guc: str) -> str:
    return f"NULLIF(current_setting('{guc}'::text, true), ''::text)"


_DEV = "(NULLIF(current_setting('app.desarrollador_id'::text, true), ''::text))::uuid"
_ACTIVO = (
    "(EXISTS ( SELECT 1 FROM desarrollador d "  # noqa: S608
    f"WHERE ((d.id = {_DEV}) AND d.activo)))"
)
_OBJETIVO = _uuid_guc("app.plat_dev_objetivo")
_RESTABLECER = f"(email = {_text_guc('app.plat_dev_restablecer')})"
_ESTADO = f"(email = {_text_guc('app.plat_dev_estado')})"

# (tabla, nombre) -> (permissive, cmd, roles, USING, WITH CHECK); "app" = rol de la aplicación.
EXPECTED_POLICIES = {
    ("desarrollador", "desarrollador_propio"): (
        "PERMISSIVE",
        "SELECT",
        "app",
        f"(id = {_DEV})",
        None,
    ),
    ("plataforma_refresh_token", "plataforma_refresh_leer"): (
        "PERMISSIVE",
        "SELECT",
        "app",
        f"(desarrollador_id = {_DEV})",
        None,
    ),
    ("plataforma_refresh_token", "plataforma_refresh_crear"): (
        "PERMISSIVE",
        "INSERT",
        "app",
        None,
        f"(desarrollador_id = {_DEV})",
    ),
    ("plataforma_refresh_token", "plataforma_refresh_marcar"): (
        "PERMISSIVE",
        "UPDATE",
        "app",
        f"(desarrollador_id = {_DEV})",
        f"(desarrollador_id = {_DEV})",
    ),
    ("plataforma_auditoria", "plataforma_auditoria_insertar"): (
        "PERMISSIVE",
        "INSERT",
        "app",
        None,
        f"((desarrollador_id = {_DEV}) AND {_ACTIVO})",
    ),
    ("plataforma_auditoria", "plataforma_auditoria_leer"): (
        "PERMISSIVE",
        "SELECT",
        "app",
        _ACTIVO,
        None,
    ),
    # --- plataforma_owner: una GUC por función, cero filas con la GUC vacía ---
    ("desarrollador", "dueno_plat_desarrollador_login"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        f"(email = {_text_guc('app.plat_login_email')})",
        None,
    ),
    ("desarrollador", "dueno_plat_desarrollador_crear"): (
        "PERMISSIVE",
        "INSERT",
        OWNER,
        None,
        f"((id = {_uuid_guc('app.plat_dev_crear')}) AND activo)",
    ),
    ("desarrollador", "dueno_plat_desarrollador_restablecer_leer"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        _RESTABLECER,
        None,
    ),
    ("desarrollador", "dueno_plat_desarrollador_restablecer"): (
        "PERMISSIVE",
        "UPDATE",
        OWNER,
        _RESTABLECER,
        _RESTABLECER,
    ),
    ("desarrollador", "dueno_plat_desarrollador_estado_leer"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        _ESTADO,
        None,
    ),
    ("desarrollador", "dueno_plat_desarrollador_estado"): (
        "PERMISSIVE",
        "UPDATE",
        OWNER,
        _ESTADO,
        _ESTADO,
    ),
    ("plataforma_refresh_token", "dueno_plat_refresh_leer"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        f"(desarrollador_id = {_OBJETIVO})",
        None,
    ),
    ("plataforma_refresh_token", "dueno_plat_refresh_revocar"): (
        "PERMISSIVE",
        "UPDATE",
        OWNER,
        f"((desarrollador_id = {_OBJETIVO}) AND (revocado_en IS NULL))",
        f"((desarrollador_id = {_OBJETIVO}) AND (revocado_en = now()))",
    ),
    ("plataforma_auditoria", "dueno_plat_auditoria_operador"): (
        "PERMISSIVE",
        "INSERT",
        OWNER,
        None,
        "((desarrollador_id IS NULL) AND (tenant_id IS NULL) AND (resultado = 'ok'::text) "
        "AND (accion = ANY (ARRAY['desarrollador_creado'::text, "
        "'desarrollador_restablecido'::text, 'desarrollador_desactivado'::text, "
        f"'desarrollador_reactivado'::text])) AND (objeto_id = {_OBJETIVO}))",
    ),
}

TS = "timestamp with time zone"
EXPECTED_COLUMNS = {
    "desarrollador": {
        "id": ("uuid", True),
        "email": ("text", True),
        "nombre": ("text", True),
        "password_hash": ("text", True),
        "activo": ("boolean", True),
        "creado_en": (TS, True),
    },
    "plataforma_refresh_token": {
        "id": ("uuid", True),
        "desarrollador_id": ("uuid", True),
        "familia_id": ("uuid", True),
        "token_hash": ("bytea", True),
        "expira_en": (TS, True),
        "usado_en": (TS, False),
        "revocado_en": (TS, False),
        "creado_en": (TS, True),
    },
    "plataforma_auditoria": {
        "id": ("uuid", True),
        "desarrollador_id": ("uuid", False),
        "accion": ("text", True),
        "resultado": ("text", True),
        "tenant_id": ("uuid", False),
        "objeto_id": ("uuid", False),
        "creado_en": (TS, True),
    },
}
_ACCIONES_CHECK = ", ".join(f"'{a}'::text" for a in ACCIONES)
EXPECTED_CONSTRAINTS = {
    "desarrollador": {
        "PRIMARY KEY (id)",
        "UNIQUE (email)",
        "CHECK ((email = lower(btrim(email))))",
        "CHECK (((char_length(nombre) >= 1) AND (char_length(nombre) <= 120)))",
    },
    "plataforma_refresh_token": {
        "PRIMARY KEY (id)",
        "FOREIGN KEY (desarrollador_id) REFERENCES desarrollador(id)",
        "UNIQUE (token_hash)",
        "CHECK ((octet_length(token_hash) = 32))",
    },
    "plataforma_auditoria": {
        "PRIMARY KEY (id)",
        "FOREIGN KEY (desarrollador_id) REFERENCES desarrollador(id)",
        "FOREIGN KEY (tenant_id) REFERENCES tenant(id)",
        f"CHECK ((accion = ANY (ARRAY[{_ACCIONES_CHECK}])))",
        "CHECK ((resultado = ANY (ARRAY['ok'::text, 'rechazado'::text])))",
    },
}

EXPECTED_APP_COLUMNS = {
    "desarrollador": {"SELECT": {"id", "email", "nombre", "activo"}},
    "plataforma_refresh_token": {
        "SELECT": set(EXPECTED_COLUMNS["plataforma_refresh_token"]),
        "INSERT": set(EXPECTED_COLUMNS["plataforma_refresh_token"]),
        "UPDATE": {"usado_en", "revocado_en"},
    },
    "plataforma_auditoria": {
        "SELECT": set(EXPECTED_COLUMNS["plataforma_auditoria"]),
        "INSERT": {"desarrollador_id", "accion", "resultado", "tenant_id", "objeto_id"},
    },
}
EXPECTED_APP_TABLE_PRIVILEGES = {
    "desarrollador": set(),
    "plataforma_refresh_token": {"SELECT", "INSERT"},
    "plataforma_auditoria": {"SELECT"},
}
# plataforma_owner: tabla -> privilegio -> columnas; nada fuera de estas tablas.
EXPECTED_OWNER_COLUMNS = {
    "desarrollador": {
        "SELECT": {"id", "email", "password_hash", "activo"},
        "INSERT": {"id", "email", "nombre", "password_hash"},
        "UPDATE": {"password_hash", "activo"},
    },
    "plataforma_refresh_token": {
        "SELECT": {"desarrollador_id", "revocado_en"},
        "UPDATE": {"revocado_en"},
    },
    "plataforma_auditoria": {"INSERT": {"accion", "resultado", "objeto_id"}},
}

SEARCH_PATH = ["search_path=pg_catalog, pg_temp"]
# nombre -> (argumentos, resultado, GUC que fija, huella sha256 de prosrc, rol con EXECUTE).
EXPECTED_FUNCTIONS = {
    "crear_desarrollador": (
        "p_email text, p_nombre text, p_password_hash text",
        "uuid",
        {"app.plat_dev_crear", "app.plat_dev_objetivo"},
        "c5980fa2693fb58f7b42daf556848f75870f0bb7ca2eab7ac80f51c72cbd915b",
        "migrator",
    ),
    "restablecer_desarrollador": (
        "p_email text, p_password_hash text",
        "void",
        {"app.plat_dev_restablecer", "app.plat_dev_objetivo"},
        "eb2b6ac721d6fc19df3804b01cb1cdc0c7db6e7ba01efa8d6bdc596576ea484d",
        "migrator",
    ),
    "cambiar_estado_desarrollador": (
        "p_email text, p_activo boolean",
        "void",
        {"app.plat_dev_estado", "app.plat_dev_objetivo"},
        "335bfd19dbf3cceb2fd3b618291572cab597483bdb11a96260a96a546db6e2f0",
        "migrator",
    ),
    # Lectura para el login de plataforma (T2): el hash solo para verificar Argon2id en
    # Flask (plan.md §2.3); ninguna otra función de plataforma devuelve un hash.
    "plataforma_buscar_login": (
        "p_email text",
        "TABLE(id uuid, password_hash text, activo boolean)",
        {"app.plat_login_email"},
        "8dd5760702aff6b8b536b0c7b70ad1e609e7d294b5e45d71c51d99ce18124156",
        "app",
    ),
}
OWNER_GUCS = (
    "app.plat_login_email",
    "app.plat_dev_crear",
    "app.plat_dev_restablecer",
    "app.plat_dev_estado",
    "app.plat_dev_objetivo",
)
FUNCTION_CALLS = {
    "crear_desarrollador": "select acceso.crear_desarrollador('x@ejemplo.test', 'X', 'h')",
    "restablecer_desarrollador": "select acceso.restablecer_desarrollador('x@ejemplo.test', 'h')",
    "cambiar_estado_desarrollador": (
        "select acceso.cambiar_estado_desarrollador('x@ejemplo.test', false)"
    ),
    "plataforma_buscar_login": "select * from acceso.plataforma_buscar_login('x@ejemplo.test')",
}
TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
COLUMN_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "REFERENCES")

HASHER = argon2.PasswordHasher.from_parameters(ARGON2_TEST_PARAMS)


@dataclass(frozen=True)
class PlataformaDb:
    url: URL
    app_role: str
    migrator: str
    superuser: Engine  # migrador superusuario: ve todas las filas bajo FORCE RLS
    app: Engine


def _fail(message: str) -> None:
    pytest.fail(message, pytrace=False)


def _alembic_config() -> AlembicConfig:
    config = AlembicConfig(str(ALEMBIC_INI))
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="module")
def db(database_residue_guard) -> Iterator[PlataformaDb]:
    """Base temporal en ``head`` con los roles de Supabase; se borra al terminar."""
    migrator_url = read_database_url("TEST_MIGRATION_DATABASE_URL")
    app_url = read_database_url("TEST_DATABASE_URL")
    if migrator_url is None or app_url is None or not app_url.username:
        _fail(BLOCKED)
    name = f"assetcontrol_plataforma_{uuid.uuid4().hex[:12]}"
    admin = create_engine(migrator_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    created_roles: list[str] = []
    failure = None
    try:
        with admin.connect() as conn:
            if not role_sees_all_rows(conn):
                failure = "bloqueado: el rol migrador debe ser superusuario para verificar"
            else:
                conn.execute(text(f'CREATE DATABASE "{name}"'))
                for role in SUPABASE_ROLES:
                    exists = conn.scalar(
                        text("select exists (select 1 from pg_roles where rolname = :r)"),
                        {"r": role},
                    )
                    if not exists:
                        conn.execute(text(f'CREATE ROLE "{role}" NOLOGIN'))
                        created_roles.append(role)
    except SQLAlchemyError as exc:
        failure = f"bloqueado: el rol migrador no pudo preparar la base ({type(exc).__name__})"
    if failure is not None:
        admin.dispose()
        _fail(failure)

    url = migrator_url.set(database=name)
    engines: list[Engine] = []
    try:
        setup = create_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
        try:
            with setup.connect() as conn:
                for role in SUPABASE_ROLES:
                    conn.execute(
                        text(
                            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                            f'GRANT ALL ON TABLES TO "{role}"'
                        )
                    )
                    conn.execute(
                        text(f'ALTER DEFAULT PRIVILEGES GRANT EXECUTE ON FUNCTIONS TO "{role}"')
                    )
        finally:
            setup.dispose()
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("MIGRATION_DATABASE_URL", url.render_as_string(hide_password=False))
            mp.delenv("DATABASE_URL", raising=False)
            mp.setenv("APP_DB_USER", app_url.username)
            command.upgrade(_alembic_config(), "head")
        superuser = create_engine(url, poolclass=NullPool)
        app = create_engine(app_url.set(database=name), poolclass=NullPool)
        engines += [superuser, app]
        yield PlataformaDb(
            url=url,
            app_role=app_url.username,
            migrator=migrator_url.username,
            superuser=superuser,
            app=app,
        )
    finally:
        for engine in engines:
            engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            for role in created_roles:
                conn.execute(text(f'DROP ROLE IF EXISTS "{role}"'))
        admin.dispose()


@pytest.fixture
def conn(db) -> Iterator[Connection]:
    with db.superuser.connect() as connection:
        yield connection


# --- Utilidades de catálogo --------------------------------------------------------


def _normalize(expression: str | None) -> str | None:
    return None if expression is None else " ".join(expression.split())


def _policies(conn: Connection) -> dict[tuple[str, str], tuple]:
    rows = conn.execute(
        text(
            "select tablename, policyname, permissive, cmd, roles::text, qual, with_check "
            "from pg_policies where schemaname = 'public' "
            "and (tablename = any(:t) or roles::text = :owner)"
        ),
        {"t": list(PLATFORM_TABLES), "owner": "{" + OWNER + "}"},
    )
    return {
        (r[0], r[1]): (r[2], r[3], r[4].strip("{}"), _normalize(r[5]), _normalize(r[6]))
        for r in rows
    }


def _columns(conn: Connection, table: str) -> dict[str, tuple[str, bool]]:
    rows = conn.execute(
        text(
            "select column_name, data_type, is_nullable from information_schema.columns "
            "where table_schema = 'public' and table_name = :t"
        ),
        {"t": table},
    )
    return {r[0]: (r[1], r[2] == "NO") for r in rows}


def _public_tables(conn: Connection) -> set[str]:
    return set(
        conn.scalars(
            text(
                "select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace "
                "where n.nspname = 'public' and c.relkind in ('r', 'p')"
            )
        )
    )


def _acl_table_privileges(conn: Connection, role: str, table: str) -> set[str]:
    return set(
        conn.scalars(
            text(
                "select a.privilege_type from pg_class c "
                "join pg_namespace n on n.oid = c.relnamespace "
                "cross join lateral aclexplode(c.relacl) a "
                "where n.nspname = 'public' and c.relname = :t "
                "and a.grantee = (select oid from pg_roles where rolname = :r)"
            ),
            {"t": table, "r": role},
        )
    )


def _column_privileges(conn: Connection, role: str, table: str) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for privilege in COLUMN_PRIVILEGES:
        cols = {
            column
            for column in _columns(conn, table)
            if conn.scalar(
                text("select has_column_privilege(:r, :t, :c, :p)"),
                {"r": role, "t": f"public.{table}", "c": column, "p": privilege},
            )
        }
        if cols:
            result[privilege] = cols
    return result


def _functions(conn: Connection) -> dict[str, dict[str, object]]:
    rows = conn.execute(
        text(
            "select p.proname, pg_get_function_identity_arguments(p.oid), "
            "pg_get_function_result(p.oid), p.prosecdef, p.proisstrict, l.lanname, "
            "p.provolatile, pg_get_userbyid(p.proowner), p.proconfig, p.prosrc, p.prokind "
            "from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
            "join pg_language l on l.oid = p.prolang "
            "where n.nspname = 'acceso' and pg_get_userbyid(p.proowner) <> :auth"
        ),
        {"auth": AUTH_OWNER},
    ).all()
    keys = ("args", "result", "secdef", "strict", "lang", "volatile", "owner", "config", "src")
    return {row[0]: dict(zip(keys + ("kind",), row[1:], strict=True)) for row in rows}


def _function_acl(conn: Connection, name: str) -> set[tuple[str, str, str, bool]]:
    rows = conn.execute(
        text(
            "select case when a.grantee = 0 then 'PUBLIC' else pg_get_userbyid(a.grantee) end, "
            "pg_get_userbyid(a.grantor), a.privilege_type, a.is_grantable "
            "from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
            "cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a "
            "where n.nspname = 'acceso' and p.proname = :n"
        ),
        {"n": name},
    ).all()
    return {tuple(row) for row in rows}


def _expect_error(connection: Connection, sql: str, params: dict, sqlstate: str) -> str:
    nested = connection.begin_nested()
    with pytest.raises(DBAPIError) as excinfo:
        connection.execute(text(sql), params)
    nested.rollback()
    assert getattr(excinfo.value.orig, "sqlstate", None) == sqlstate, str(excinfo.value.orig)
    return str(excinfo.value.orig)


def _as_developer(connection: Connection, desarrollador_id: uuid.UUID | str) -> None:
    connection.execute(
        text("select set_config('app.desarrollador_id', :d, true)"), {"d": str(desarrollador_id)}
    )


def _email(prefix: str = "dev") -> str:
    return f"{prefix}.{uuid.uuid4().hex[:10]}@ejemplo.test"


def _new_developer(db: PlataformaDb, *, activo: bool = True) -> tuple[uuid.UUID, str]:
    """Desarrollador sembrado por el superusuario (sin pasar por las funciones)."""
    desarrollador_id, email = uuid.uuid4(), _email()
    with db.superuser.begin() as connection:
        connection.execute(
            text(
                "insert into desarrollador (id, email, nombre, password_hash, activo) "
                "values (:id, :e, 'Dev sintético', :h, :a)"
            ),
            {"id": desarrollador_id, "e": email, "h": HASHER.hash("x" * 16), "a": activo},
        )
    return desarrollador_id, email


def _new_refresh(db: PlataformaDb, desarrollador_id: uuid.UUID) -> uuid.UUID:
    token_id = uuid.uuid4()
    with db.superuser.begin() as connection:
        connection.execute(
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


def _audit_rows(db: PlataformaDb, objeto_id: uuid.UUID) -> list[dict]:
    with db.superuser.connect() as connection:
        return [
            dict(r)
            for r in connection.execute(
                text(
                    "select desarrollador_id, accion, resultado, tenant_id, objeto_id "
                    "from plataforma_auditoria where objeto_id = :o order by creado_en, accion"
                ),
                {"o": objeto_id},
            ).mappings()
        ]


def _counts(db: PlataformaDb) -> dict[str, int]:
    with db.superuser.connect() as connection:
        return {
            table: connection.scalar(text(f"select count(*) from {table}"))  # noqa: S608
            for table in PLATFORM_TABLES
        }


def _revoked(db: PlataformaDb, token_id: uuid.UUID) -> bool:
    with db.superuser.connect() as connection:
        return (
            connection.scalar(
                text("select revocado_en from plataforma_refresh_token where id = :i"),
                {"i": token_id},
            )
            is not None
        )


# --- Tablas, columnas y claves --------------------------------------------------------


@pytest.mark.parametrize("table", PLATFORM_TABLES)
def test_platform_tables_columns_and_constraints(conn, table):
    assert _columns(conn, table) == EXPECTED_COLUMNS[table]
    constraints = set(
        conn.scalars(
            text(
                "select pg_get_constraintdef(oid) from pg_constraint "
                "where conrelid = to_regclass(:t) and contype in ('c', 'u', 'f', 'p')"
            ),
            {"t": f"public.{table}"},
        )
    )
    assert constraints == EXPECTED_CONSTRAINTS[table]


@pytest.mark.parametrize("table", PLATFORM_TABLES)
def test_platform_tables_have_rls_enabled_and_forced(conn, table):
    flags = conn.execute(
        text(
            "select c.relrowsecurity, c.relforcerowsecurity from pg_class c "
            "where c.oid = to_regclass(:t)"
        ),
        {"t": f"public.{table}"},
    ).one()
    assert tuple(flags) == (True, True)


def test_platform_tables_are_owned_by_the_migrator(conn, db):
    for table in PLATFORM_TABLES:
        owner = conn.scalar(
            text("select pg_get_userbyid(relowner) from pg_class where oid = to_regclass(:t)"),
            {"t": f"public.{table}"},
        )
        assert owner == db.migrator, table


def test_auditoria_actions_are_the_closed_list_of_r33(conn):
    check = conn.scalar(
        text(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conname = 'plataforma_auditoria_accion_valida'"
        )
    )
    assert re.findall(r"'(\w+)'::text", check) == ACCIONES


def test_auditoria_has_no_personal_data_columns(conn):
    # R34: sin correos, nombres, IP, texto libre ni hashes.
    assert set(_columns(conn, "plataforma_auditoria")) == {
        "id",
        "desarrollador_id",
        "accion",
        "resultado",
        "tenant_id",
        "objeto_id",
        "creado_en",
    }


def test_auditoria_and_refresh_indexes(conn):
    def indexes(table: str) -> set[str]:
        return {
            re.sub(r"^.* USING btree ", "", definition)
            for definition in conn.scalars(
                text(
                    "select indexdef from pg_indexes where schemaname = 'public' and tablename = :t"
                ),
                {"t": table},
            )
        }

    assert indexes("plataforma_auditoria") == {
        "(id)",
        "(creado_en DESC, id DESC)",
        "(tenant_id, creado_en DESC)",
        "(accion, creado_en DESC)",
    }
    assert indexes("plataforma_refresh_token") == {
        "(id)",
        "(token_hash)",
        "(familia_id)",
        "(desarrollador_id)",
    }


def test_tenant_activo_columns_and_checks(conn):
    columns = _columns(conn, "tenant")
    assert {k: columns[k] for k in ("activo", "desactivado_en", "desactivado_por")} == {
        "activo": ("boolean", True),
        "desactivado_en": (TS, False),
        "desactivado_por": ("uuid", False),
    }
    default = conn.scalar(
        text(
            "select column_default from information_schema.columns "
            "where table_name = 'tenant' and column_name = 'activo'"
        )
    )
    assert default == "true"
    constraints = set(
        conn.scalars(
            text(
                "select pg_get_constraintdef(oid) from pg_constraint "
                "where conrelid = 'tenant'::regclass"
            )
        )
    )
    assert constraints == {
        "PRIMARY KEY (id)",
        "CHECK ((activo = (desactivado_en IS NULL)))",
        "CHECK (((NOT activo) OR (desactivado_por IS NULL)))",
        "FOREIGN KEY (desactivado_por) REFERENCES desarrollador(id)",
    }


def test_tenant_activo_check_keeps_state_and_date_together(db):
    with db.superuser.connect() as connection:
        tx = connection.begin()
        try:
            tenant_id = uuid.uuid4()
            connection.execute(
                text("insert into tenant (id, nombre) values (:i, 'Clínica sintética')"),
                {"i": tenant_id},
            )
            assert (
                connection.scalar(text("select activo from tenant where id = :i"), {"i": tenant_id})
                is True
            )
            for sql in (
                "update tenant set activo = false where id = :i",
                "update tenant set desactivado_en = now() where id = :i",
            ):
                _expect_error(connection, sql, {"i": tenant_id}, "23514")
            connection.execute(
                text("update tenant set activo = false, desactivado_en = now() where id = :i"),
                {"i": tenant_id},
            )
        finally:
            tx.rollback()


def test_usuario_debe_cambiar_password_defaults_to_false(conn):
    assert _columns(conn, "usuario")["debe_cambiar_password"] == ("boolean", True)
    default = conn.scalar(
        text(
            "select column_default from information_schema.columns "
            "where table_name = 'usuario' and column_name = 'debe_cambiar_password'"
        )
    )
    assert default == "false"


def test_limite_tasa_accepts_the_platform_login_scopes(conn):
    check = conn.scalar(
        text(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conname = 'limite_tasa_ambito_check'"
        )
    )
    scopes = re.findall(r"'(\w+)'::text", check)
    assert scopes[-2:] == ["plat_login_ip", "plat_login_cuenta"]
    assert len(scopes) == 10


# --- Políticas ------------------------------------------------------------------------


def test_platform_policies_are_a_closed_list_with_exact_text(conn, db):
    expected = {
        key: (permissive, cmd, db.app_role if roles == "app" else roles, qual, check)
        for key, (permissive, cmd, roles, qual, check) in EXPECTED_POLICIES.items()
    }
    assert _policies(conn) == expected


def test_owner_policies_are_never_for_all_nor_public(conn):
    for key, (_, cmd, roles, _, _) in _policies(conn).items():
        assert cmd != "ALL", key
        assert roles != "public", key


def test_platform_owner_policies_only_touch_platform_tables(conn):
    tables = {table for (table, _), value in _policies(conn).items() if value[2] == OWNER}
    assert tables == set(PLATFORM_TABLES)


# --- GRANT --------------------------------------------------------------------------


@pytest.mark.parametrize("table", PLATFORM_TABLES)
def test_app_privileges_on_platform_tables_are_exact(conn, db, table):
    assert _column_privileges(conn, db.app_role, table) == EXPECTED_APP_COLUMNS[table]
    assert _acl_table_privileges(conn, db.app_role, table) == EXPECTED_APP_TABLE_PRIVILEGES[table]


def test_app_never_reads_the_developer_password_hash(conn, db):
    assert not conn.scalar(
        text("select has_column_privilege(:r, 'public.desarrollador', 'password_hash', 'SELECT')"),
        {"r": db.app_role},
    )


def test_platform_owner_privileges_are_exactly_its_column_grants(conn):
    for table in _public_tables(conn):
        assert _acl_table_privileges(conn, OWNER, table) == set(), table
        expected = EXPECTED_OWNER_COLUMNS.get(table, {})
        assert _column_privileges(conn, OWNER, table) == expected, table


def test_nobody_but_the_owner_can_delete_platform_rows(conn, db):
    for role in (db.app_role, OWNER, AUTH_OWNER, *SUPABASE_ROLES):
        for table in PLATFORM_TABLES:
            for privilege in ("DELETE", "TRUNCATE"):
                assert not conn.scalar(
                    text("select has_table_privilege(:r, :t, :p)"),
                    {"r": role, "t": f"public.{table}", "p": privilege},
                ), (role, table, privilege)


def test_supabase_roles_receive_nothing_on_platform_tables(conn):
    for role in SUPABASE_ROLES:
        for table in PLATFORM_TABLES:
            assert _acl_table_privileges(conn, role, table) == set(), (role, table)
            assert _column_privileges(conn, role, table) == {}, (role, table)


# --- plataforma_owner ------------------------------------------------------------------


def test_platform_owner_is_inert_and_has_no_memberships(conn, db):
    row = conn.execute(
        text(
            "select rolsuper, rolbypassrls, rolcanlogin, rolcreaterole, rolcreatedb, "
            "rolreplication from pg_roles where rolname = :r"
        ),
        {"r": OWNER},
    ).one()
    assert tuple(row) == (False, False, False, False, False, False)
    members = conn.scalar(
        text(
            "select count(*) from pg_auth_members m "
            "join pg_roles r on r.oid in (m.roleid, m.member) "
            "where r.rolname = :r"
        ),
        {"r": OWNER},
    )
    assert members == 0
    for member, role in ((db.app_role, OWNER), (OWNER, db.app_role), (OWNER, AUTH_OWNER)):
        assert not conn.scalar(
            text("select pg_has_role(:m, :r, 'MEMBER')"), {"m": member, "r": role}
        ), (member, role)


def test_platform_owner_has_usage_but_no_create_on_acceso(conn):
    assert conn.scalar(text("select has_schema_privilege(:r, 'acceso', 'USAGE')"), {"r": OWNER})
    assert not conn.scalar(
        text("select has_schema_privilege(:r, 'acceso', 'CREATE')"), {"r": OWNER}
    )
    assert not conn.scalar(
        text("select has_schema_privilege(:r, 'public', 'CREATE')"), {"r": OWNER}
    )
    assert not conn.scalar(
        text("select has_database_privilege(:r, current_database(), 'CREATE')"), {"r": OWNER}
    )


# --- Funciones (A4) ----------------------------------------------------------------------


def test_platform_functions_are_a_closed_list(conn):
    assert set(_functions(conn)) == set(EXPECTED_FUNCTIONS)


@pytest.mark.parametrize("name", sorted(EXPECTED_FUNCTIONS))
def test_platform_function_signature_and_attributes(conn, name):
    function = _functions(conn)[name]
    args, result, _, _, _ = EXPECTED_FUNCTIONS[name]
    assert (function["args"], function["result"]) == (args, result)
    assert function["kind"] == "f"
    assert function["secdef"] is True
    assert function["strict"] is True
    assert function["lang"] == "plpgsql"
    assert function["volatile"] == "v"
    assert function["owner"] == OWNER
    assert function["config"] == SEARCH_PATH


@pytest.mark.parametrize("name", sorted(EXPECTED_FUNCTIONS))
def test_platform_function_acl_is_exact(conn, db, name):
    grantee = {"app": db.app_role, "migrator": db.migrator}[EXPECTED_FUNCTIONS[name][4]]
    assert _function_acl(conn, name) == {
        (OWNER, OWNER, "EXECUTE", False),
        (grantee, OWNER, "EXECUTE", False),
    }


@pytest.mark.parametrize("name", sorted(EXPECTED_FUNCTIONS))
def test_platform_function_body_is_exactly_the_reviewed_one(conn, name):
    source = _functions(conn)[name]["src"]
    assert hashlib.sha256(source.encode()).hexdigest() == EXPECTED_FUNCTIONS[name][3]


_RELATION_REFERENCE = re.compile(r"\b(?:FROM|JOIN|UPDATE|INTO)\s+([A-Za-z_][\w]*)(\.)?", re.I)


@pytest.mark.parametrize("name", sorted(EXPECTED_FUNCTIONS))
def test_platform_function_body_is_static_qualified_and_reads_no_guc(conn, name):
    source = _functions(conn)[name]["src"]
    lowered = source.lower()
    assert "current_setting" not in lowered
    assert re.search(r"\bexecute\b", lowered) is None
    assert "format(" not in lowered
    for match in _RELATION_REFERENCE.finditer(source):
        word, qualified = match.group(1), match.group(2)
        if qualified:
            assert word in ("public", "pg_catalog"), match.group(0)
        else:
            assert word.startswith("v_"), match.group(0)
    for guc in EXPECTED_FUNCTIONS[name][2]:
        assert f"pg_catalog.set_config('{guc}'," in source, guc
    assert source.count("pg_catalog.set_config(g, '', true)") >= 2
    for guc in OWNER_GUCS:
        assert f"'{guc}'" in source, guc  # la lista que vacía es la completa


def test_only_the_login_function_returns_a_hash(conn):
    for name, function in _functions(conn).items():
        result = str(function["result"])
        if name == "plataforma_buscar_login":
            assert "password_hash" in result
        else:
            assert "hash" not in result, name


def test_app_executes_only_the_login_function(conn, db):
    for name, (args, *_rest) in EXPECTED_FUNCTIONS.items():
        signature = f"acceso.{name}({', '.join(a.split()[-1] for a in args.split(', '))})"
        allowed = conn.scalar(
            text("select has_function_privilege(:r, :f, 'EXECUTE')"),
            {"r": db.app_role, "f": signature},
        )
        assert allowed is (name == "plataforma_buscar_login"), name


@pytest.mark.parametrize("role", SUPABASE_ROLES)
@pytest.mark.parametrize("name", sorted(EXPECTED_FUNCTIONS))
def test_supabase_roles_cannot_execute_platform_functions(db, role, name):
    with db.superuser.connect() as connection:
        for with_usage in (False, True):
            tx = connection.begin()
            try:
                if with_usage:
                    connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA acceso TO "{role}"')
                connection.exec_driver_sql(f'SET LOCAL ROLE "{role}"')
                with pytest.raises(DBAPIError) as excinfo:
                    connection.execute(text(FUNCTION_CALLS[name]))
            finally:
                tx.rollback()
            assert excinfo.value.orig.sqlstate == INSUFFICIENT_PRIVILEGE


# --- Rol de la aplicación sobre las tablas nuevas (A6, A10) ------------------------------


def test_without_developer_the_app_sees_no_platform_rows(db):
    desarrollador_id, _ = _new_developer(db)
    _new_refresh(db, desarrollador_id)
    with db.app.connect() as connection:
        tx = connection.begin()
        try:
            # Sin GUC y con un tenant fijado (tenant_session): cero filas (R37).
            for tenant in (None, str(uuid.uuid4())):
                if tenant is not None:
                    connection.execute(
                        text("select set_config('app.tenant_id', :t, true)"), {"t": tenant}
                    )
                assert connection.scalar(text("select count(id) from desarrollador")) == 0
                assert connection.scalar(text("select count(*) from plataforma_refresh_token")) == 0
                assert connection.scalar(text("select count(*) from plataforma_auditoria")) == 0
        finally:
            tx.rollback()


def test_with_a_developer_the_app_sees_only_its_own_rows(db):
    propio, _ = _new_developer(db)
    ajeno, _ = _new_developer(db)
    _new_refresh(db, propio)
    _new_refresh(db, ajeno)
    with db.app.connect() as connection:
        tx = connection.begin()
        try:
            _as_developer(connection, propio)
            ids = connection.scalars(text("select id from desarrollador")).all()
            assert ids == [propio]
            owners = set(
                connection.scalars(text("select desarrollador_id from plataforma_refresh_token"))
            )
            assert owners == {propio}
            _expect_error(
                connection,
                "select password_hash from desarrollador",
                {},
                INSUFFICIENT_PRIVILEGE,
            )
        finally:
            tx.rollback()


def test_with_a_developer_the_app_reads_no_business_rows(db):
    desarrollador_id, _ = _new_developer(db)
    with db.superuser.begin() as connection:
        connection.execute(
            text("insert into tenant (id, nombre) values (:i, 'Clínica sintética P')"),
            {"i": uuid.uuid4()},
        )
    with db.app.connect() as connection:
        tx = connection.begin()
        try:
            _as_developer(connection, desarrollador_id)
            for table in ("tenant", "membresia", "activo", "ubicacion", "categoria", "empresa"):
                count = connection.scalar(text(f"select count(*) from {table}"))  # noqa: S608
                assert count == 0, table
        finally:
            tx.rollback()


def test_app_cannot_write_developers_directly(db):
    desarrollador_id, _ = _new_developer(db)
    with db.app.connect() as connection:
        tx = connection.begin()
        try:
            _as_developer(connection, desarrollador_id)
            for sql in (
                "insert into desarrollador (email, nombre, password_hash) "
                "values ('x@ejemplo.test', 'X', 'h')",
                "update desarrollador set activo = true",
                "update desarrollador set password_hash = 'h'",
                "delete from desarrollador",
            ):
                _expect_error(connection, sql, {}, INSUFFICIENT_PRIVILEGE)
        finally:
            tx.rollback()


def test_app_refresh_tokens_are_bound_to_its_developer(db):
    propio, _ = _new_developer(db)
    ajeno, _ = _new_developer(db)
    params = {
        "f": uuid.uuid4(),
        "h": secrets.token_bytes(32),
        "e": datetime.now(UTC) + timedelta(hours=8),
    }
    sql = (
        "insert into plataforma_refresh_token "
        "(desarrollador_id, familia_id, token_hash, expira_en) "
        "values (:d, :f, :h, :e)"
    )
    with db.app.connect() as connection:
        tx = connection.begin()
        try:
            _as_developer(connection, propio)
            connection.execute(text(sql), {**params, "d": propio})
            _expect_error(
                connection, sql, {**params, "d": ajeno, "h": secrets.token_bytes(32)}, "42501"
            )
            _expect_error(connection, "delete from plataforma_refresh_token", {}, "42501")
        finally:
            tx.rollback()


def test_audit_is_insert_and_select_only_for_an_active_developer(db):
    activo, _ = _new_developer(db)
    inactivo, _ = _new_developer(db, activo=False)
    sql = (
        "insert into plataforma_auditoria (desarrollador_id, accion, resultado) "
        "values (:d, 'login_ok', 'ok')"
    )
    with db.app.connect() as connection:
        tx = connection.begin()
        try:
            _as_developer(connection, activo)
            connection.execute(text(sql), {"d": activo})
            assert connection.scalar(text("select count(*) from plataforma_auditoria")) >= 1
            # Otro desarrollador ni nulo (operador): RLS lo rechaza.
            _expect_error(connection, sql, {"d": inactivo}, "42501")
            _expect_error(connection, sql, {"d": None}, "42501")
            # A10: sin UPDATE ni DELETE para la aplicación.
            _expect_error(
                connection, "update plataforma_auditoria set resultado = 'rechazado'", {}, "42501"
            )
            _expect_error(connection, "delete from plataforma_auditoria", {}, "42501")
            # Un desarrollador inactivo no inserta ni lee.
            _as_developer(connection, inactivo)
            assert connection.scalar(text("select count(*) from plataforma_auditoria")) == 0
            _expect_error(connection, sql, {"d": inactivo}, "42501")
        finally:
            tx.rollback()


def test_tenant_session_reads_no_platform_rows(db):
    desarrollador_id, _ = _new_developer(db)
    with db.app.connect() as connection:
        tx = connection.begin()
        try:
            connection.execute(
                text("select set_config('app.tenant_id', :t, true)"), {"t": str(uuid.uuid4())}
            )
            assert (
                connection.scalar(
                    text("select count(*) from desarrollador where id = :i"),
                    {"i": desarrollador_id},
                )
                == 0
            )
        finally:
            tx.rollback()


# --- plataforma_buscar_login --------------------------------------------------------------


def test_login_lookup_returns_only_the_listed_columns_and_clears_its_gucs(db):
    desarrollador_id, email = _new_developer(db)
    with db.app.connect() as connection:
        tx = connection.begin()
        try:
            result = connection.execute(
                text("select * from acceso.plataforma_buscar_login(:e)"), {"e": email}
            )
            rows = result.all()
            assert list(result.keys()) == ["id", "password_hash", "activo"]
            assert len(rows) == 1
            assert rows[0].id == desarrollador_id and rows[0].activo is True
            assert rows[0].password_hash.startswith("$argon2id$")
            for guc in OWNER_GUCS:
                value = connection.scalar(text("select current_setting(:g, true)"), {"g": guc})
                assert value in (None, ""), guc
            missing = connection.execute(
                text("select * from acceso.plataforma_buscar_login(:e)"), {"e": _email("nadie")}
            ).all()
            assert missing == []
        finally:
            tx.rollback()


def test_login_lookup_returns_inactive_developers_with_their_flag(db):
    desarrollador_id, email = _new_developer(db, activo=False)
    with db.app.connect() as connection:
        rows = connection.execute(
            text("select id, activo from acceso.plataforma_buscar_login(:e)"), {"e": email}
        ).all()
    assert [tuple(r) for r in rows] == [(desarrollador_id, False)]


def test_app_cannot_execute_the_operator_functions(db):
    with db.app.connect() as connection:
        tx = connection.begin()
        try:
            for name in ("crear_desarrollador", "restablecer_desarrollador"):
                message = _expect_error(
                    connection, FUNCTION_CALLS[name], {}, INSUFFICIENT_PRIVILEGE
                )
                assert "permission denied for function" in message
            _expect_error(
                connection,
                FUNCTION_CALLS["cambiar_estado_desarrollador"],
                {},
                INSUFFICIENT_PRIVILEGE,
            )
        finally:
            tx.rollback()


# --- Funciones del operador (con el migrador) ------------------------------------------------


def _call(db: PlataformaDb, sql: str, params: dict):
    with db.superuser.begin() as connection:
        return connection.scalar(text(sql), params)


def test_crear_desarrollador_inserts_and_audits_as_operator(db):
    email, password_hash = _email(), HASHER.hash("clave-sintetica-larga")
    before = _counts(db)

    desarrollador_id = _call(
        db,
        "select acceso.crear_desarrollador(:e, :n, :h)",
        {"e": email, "n": "Dev Sintético", "h": password_hash},
    )

    with db.superuser.connect() as connection:
        row = connection.execute(
            text("select email, nombre, password_hash, activo from desarrollador where id = :i"),
            {"i": desarrollador_id},
        ).one()
    assert tuple(row) == (email, "Dev Sintético", password_hash, True)
    assert _audit_rows(db, desarrollador_id) == [
        {
            "desarrollador_id": None,
            "accion": "desarrollador_creado",
            "resultado": "ok",
            "tenant_id": None,
            "objeto_id": desarrollador_id,
        }
    ]
    after = _counts(db)
    assert after["desarrollador"] == before["desarrollador"] + 1
    assert after["plataforma_auditoria"] == before["plataforma_auditoria"] + 1


def test_crear_desarrollador_with_a_repeated_email_creates_nothing(db):
    _, email = _new_developer(db)
    before = _counts(db)
    with db.superuser.connect() as connection:
        tx = connection.begin()
        try:
            message = _expect_error(
                connection,
                "select acceso.crear_desarrollador(:e, 'Otro', :h)",
                {"e": email, "h": HASHER.hash("x" * 16)},
                "23505",
            )
        finally:
            tx.rollback()
    assert "desarrollador_existente" in message
    assert email not in message
    assert _counts(db) == before


@pytest.mark.parametrize(
    "password_hash",
    [
        "",
        "x",
        "$argon2i$v=19$m=8,t=1,p=1$c2FsdHNhbHQ$aGFzaGhhc2g",
        "$2b$12$abcdefghijklmnopqrstuuabcdefghijklmnopqrstuvwxyzabcde",
        "$argon2id$v=19$m=8,t=1,p=1$c2FsdHNhbHQ$" + "a" * 300,
    ],
)
def test_crear_desarrollador_rejects_hashes_that_are_not_argon2id(db, password_hash):
    before = _counts(db)
    with db.superuser.connect() as connection:
        tx = connection.begin()
        try:
            _expect_error(
                connection,
                "select acceso.crear_desarrollador(:e, 'X', :h)",
                {"e": _email(), "h": password_hash},
                "22023",
            )
        finally:
            tx.rollback()
    assert _counts(db) == before


def test_crear_desarrollador_rejects_an_unnormalized_email(db):
    before = _counts(db)
    with db.superuser.connect() as connection:
        tx = connection.begin()
        try:
            _expect_error(
                connection,
                "select acceso.crear_desarrollador(:e, 'X', :h)",
                {"e": " Mayus@Ejemplo.test", "h": HASHER.hash("x" * 16)},
                "23514",
            )
        finally:
            tx.rollback()
    assert _counts(db) == before


def test_restablecer_desarrollador_changes_the_hash_and_revokes_every_family(db):
    desarrollador_id, email = _new_developer(db)
    otro, _ = _new_developer(db)
    tokens = [_new_refresh(db, desarrollador_id) for _ in range(3)]
    ajeno = _new_refresh(db, otro)
    nuevo = HASHER.hash("otra-clave-sintetica")

    _call(db, "select acceso.restablecer_desarrollador(:e, :h)", {"e": email, "h": nuevo})

    with db.superuser.connect() as connection:
        stored = connection.scalar(
            text("select password_hash from desarrollador where id = :i"), {"i": desarrollador_id}
        )
    assert stored == nuevo
    assert all(_revoked(db, token) for token in tokens)
    assert not _revoked(db, ajeno)
    assert [r["accion"] for r in _audit_rows(db, desarrollador_id)] == [
        "desarrollador_restablecido"
    ]
    assert _audit_rows(db, desarrollador_id)[0]["desarrollador_id"] is None


def test_restablecer_desarrollador_with_an_unknown_email_fails_generically(db):
    before = _counts(db)
    email = _email("nadie")
    with db.superuser.connect() as connection:
        tx = connection.begin()
        try:
            message = _expect_error(
                connection,
                "select acceso.restablecer_desarrollador(:e, :h)",
                {"e": email, "h": HASHER.hash("x" * 16)},
                "P0002",
            )
        finally:
            tx.rollback()
    assert email not in message
    assert _counts(db) == before


def test_cambiar_estado_desarrollador_deactivates_revokes_and_reactivates(db):
    desarrollador_id, email = _new_developer(db)
    token = _new_refresh(db, desarrollador_id)
    sql = "select acceso.cambiar_estado_desarrollador(:e, :a)"

    _call(db, sql, {"e": email, "a": False})
    with db.superuser.connect() as connection:
        activo = connection.scalar(
            text("select activo from desarrollador where id = :i"), {"i": desarrollador_id}
        )
    assert activo is False
    assert _revoked(db, token)

    posterior = _new_refresh(db, desarrollador_id)
    _call(db, sql, {"e": email, "a": True})
    with db.superuser.connect() as connection:
        activo = connection.scalar(
            text("select activo from desarrollador where id = :i"), {"i": desarrollador_id}
        )
    assert activo is True
    assert not _revoked(db, posterior)  # reactivar no revoca
    rows = _audit_rows(db, desarrollador_id)
    assert {r["accion"] for r in rows} == {"desarrollador_desactivado", "desarrollador_reactivado"}
    assert all(r["desarrollador_id"] is None and r["tenant_id"] is None for r in rows)


def test_cambiar_estado_with_an_unknown_email_fails_generically(db):
    before = _counts(db)
    with db.superuser.connect() as connection:
        tx = connection.begin()
        try:
            _expect_error(
                connection,
                "select acceso.cambiar_estado_desarrollador(:e, false)",
                {"e": _email("nadie")},
                "P0002",
            )
        finally:
            tx.rollback()
    assert _counts(db) == before


def test_operator_functions_leave_no_gucs_behind(db):
    _, email = _new_developer(db)
    with db.superuser.connect() as connection:
        tx = connection.begin()
        try:
            connection.execute(
                text("select acceso.cambiar_estado_desarrollador(:e, true)"), {"e": email}
            )
            for guc in OWNER_GUCS:
                value = connection.scalar(text("select current_setting(:g, true)"), {"g": guc})
                assert value in (None, ""), guc
        finally:
            tx.rollback()
