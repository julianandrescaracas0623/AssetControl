"""Prueba de catálogo de RLS, parte de tablas (spec 002, T1; A2, C6; plan.md §3 y §7.1).

Sobre una base temporal migrada a ``head`` con el rol migrador comprueba, leyendo
los catálogos de PostgreSQL:

- Toda tabla de ``public`` fuera de la lista cerrada de excepciones tiene
  ``tenant_id``, RLS habilitada y forzada y la política ``tenant_isolation``
  ``TO`` el rol de la aplicación (sin ``PUBLIC``).
- Ningún rol distinto del dueño tiene ``DELETE`` (ni ``TRUNCATE``) en ``public``.
- Las excepciones (``alembic_version``, ``tenant``, ``usuario`` y
  ``limite_tasa``) tienen su prueba propia; ``limite_tasa`` (T10, 0005) es de
  infraestructura: sin ``tenant_id``, sin ``DELETE`` para la aplicación, solo
  ``intentos`` actualizable y la purga solo para el migrador (docs/03, A13).
- Las políticas de ``public`` y las ``RESTRICTIVE`` forman listas cerradas. Desde
  T2 (0003) la lista incluye las políticas ``TO auth_owner``, con su texto exacto
  desde T3 (C6); su comportamiento lo prueban ``test_auth_tables_isolation.py`` y
  ``test_auth_functions.py``.
- ``auth_owner`` tiene exactamente sus ``GRANT`` por columna de 0003 (plan.md §2.1).
- Los ``GRANT`` del rol de la aplicación son exactamente los de plan.md §3, por
  columna: nunca ``usuario.password_hash`` ni ``invitacion.token_hash``.
- ``anon``, ``authenticated`` y ``service_role`` (roles de Supabase) no reciben
  nada aunque existan privilegios por defecto que se los den.
- El esquema ``acceso`` existe con ``USAGE`` solo para la aplicación y
  ``auth_owner`` y sin ``CREATE`` para nadie más que su dueño; ni ``auth_owner``
  conserva el ``CREATE`` transitorio ni el migrador su membresía (C5).
- Catálogo cerrado C6 (T3): las funciones de ``acceso`` son exactamente las
  cuatro de plan.md §2.1, con firma, resultado, ``SECURITY DEFINER``,
  ``STRICT``, ``plpgsql``, dueña ``auth_owner``, ``search_path`` fijo, ``proacl``
  exacto (solo la aplicación, o solo el migrador en ``crear_tenant``) y cuerpo
  exacto (huella ``sha256``), sin leer GUC ni SQL dinámico y todo calificado; las
  políticas ``TO auth_owner`` tienen su texto exacto.
- C7: ``anon``, ``authenticated`` y ``service_role`` no pueden ejecutar las
  funciones (ni con ``USAGE`` en ``acceso``); la aplicación no ejecuta
  ``crear_tenant``.

Los roles de Supabase no existen en local ni en la CI: la prueba los crea (solo
los que falten), les da privilegios por defecto en la base temporal (tablas de
``public`` y ``EXECUTE`` de toda función nueva), migra y los borra al terminar.
"""

import hashlib
import re
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from conftest import BLOCKED, read_database_url
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL, Connection
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.pool import NullPool

from app.auth import models

BACKEND_DIR = Path(__file__).resolve().parent.parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
AUTH_OWNER = "auth_owner"
SUPABASE_ROLES = ("anon", "authenticated", "service_role")

# Lista cerrada de tablas de public sin tenant_id; cada una tiene su prueba propia.
EXCEPTIONS = frozenset({"alembic_version", "tenant", "usuario", "limite_tasa"})
TENANT_TABLES = frozenset({"membresia", "invitacion", "refresh_token"})

TENANT_EXPR = "(NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid"
ISOLATION_EXPR = f"(tenant_id = {TENANT_EXPR})"

# Lista cerrada de políticas de public: (tabla, nombre) -> (permissive, cmd, roles, qual, check).
EXPECTED_POLICIES = {
    ("tenant", "tenant_isolation"): (
        "PERMISSIVE",
        "SELECT",
        "{app}",
        f"(id = {TENANT_EXPR})",
        None,
    ),
    ("usuario", "usuario_por_membresia"): (
        "PERMISSIVE",
        "SELECT",
        "{app}",
        # Texto esperado de pg_policies.qual, no una consulta.
        "(EXISTS ( SELECT 1\n   FROM membresia m\n  WHERE ((m.usuario_id = usuario.id) "  # noqa: S608
        f"AND (m.tenant_id = {TENANT_EXPR}))))",
        None,
    ),
    ("membresia", "tenant_isolation"): (
        "PERMISSIVE",
        "ALL",
        "{app}",
        ISOLATION_EXPR,
        ISOLATION_EXPR,
    ),
    ("invitacion", "tenant_isolation"): (
        "PERMISSIVE",
        "ALL",
        "{app}",
        ISOLATION_EXPR,
        ISOLATION_EXPR,
    ),
    ("invitacion", "invitacion_creada_por_no_nula"): (
        "RESTRICTIVE",
        "INSERT",
        "{app}",
        None,
        "(creada_por IS NOT NULL)",
    ),
    ("refresh_token", "tenant_isolation"): (
        "PERMISSIVE",
        "ALL",
        "{app}",
        ISOLATION_EXPR,
        ISOLATION_EXPR,
    ),
    # limite_tasa (T10, docs/03 cambio 6): una política por comando TO la aplicación, sin
    # filtro de tenant (no lo hay antes del login); su defensa es el privilegio mínimo y
    # el HMAC de la clave.
    ("limite_tasa", "limite_tasa_leer"): ("PERMISSIVE", "SELECT", "{app}", "true", None),
    ("limite_tasa", "limite_tasa_contar"): (
        "PERMISSIVE",
        "INSERT",
        "{app}",
        None,
        "(intentos = 1)",
    ),
    ("limite_tasa", "limite_tasa_sumar"): (
        "PERMISSIVE",
        "UPDATE",
        "{app}",
        "true",
        "(intentos >= 0)",
    ),
}
# Purga de limite_tasa (T10, R5, Q10): única política de otro rol, el migrador (dueño de la
# tabla, sujeto a FORCE RLS si no es superusuario); solo ventanas de más de un día.
PURGE_EXPR = "(ventana_inicio < (now() - '1 day'::interval))"
EXPECTED_PURGE_POLICIES = {
    ("limite_tasa", "limite_tasa_purga_leer"): ("PERMISSIVE", "SELECT", PURGE_EXPR, None),
    ("limite_tasa", "limite_tasa_purga"): ("PERMISSIVE", "DELETE", PURGE_EXPR, None),
}

# GRANT del rol de la aplicación (plan.md §3): tabla -> privilegio -> columnas.
EXPECTED_APP_COLUMNS = {
    "tenant": {"SELECT": {"id", "nombre", "creado_en"}},
    "usuario": {"SELECT": {"id", "email", "nombre", "activo"}},
    "membresia": {"SELECT": {"id", "tenant_id", "usuario_id", "rol", "activa"}},
    "invitacion": {
        "SELECT": {"id", "tenant_id", "email", "rol", "expira_en", "usada_en", "creada_por"},
        "INSERT": {"id", "tenant_id", "rol", "email", "token_hash", "expira_en", "creada_por"},
    },
    "refresh_token": {
        # token_hash es legible: la rotación de T7 hace UPDATE ... WHERE token_hash = :h
        # (PostgreSQL exige SELECT en las columnas del WHERE). Lo guardado es sha256(clave):
        # no sirve como credencial (doble hash, I1).
        "SELECT": {
            "id",
            "tenant_id",
            "membresia_id",
            "familia_id",
            "token_hash",
            "expira_en",
            "usado_en",
            "revocado_en",
            "creado_en",
        },
        "INSERT": {
            "id",
            "tenant_id",
            "membresia_id",
            "familia_id",
            "token_hash",
            "expira_en",
            "usado_en",
            "revocado_en",
            "creado_en",
        },
        "UPDATE": {"usado_en", "revocado_en"},
    },
    # T10: el SELECT completo es necesario para ON CONFLICT (la inferencia del índice lee
    # clave_hash) y el RETURNING (docs/03 cambio 6, A13); solo se actualiza intentos.
    "limite_tasa": {
        "SELECT": {"ambito", "clave_hash", "ventana_inicio", "intentos"},
        "INSERT": {"ambito", "clave_hash", "ventana_inicio", "intentos"},
        "UPDATE": {"intentos"},
    },
}
# Privilegios a nivel de tabla del rol de la aplicación (sin columnas).
EXPECTED_APP_TABLE_PRIVILEGES = {
    "alembic_version": set(),
    "tenant": {"SELECT"},
    "usuario": set(),
    "membresia": {"SELECT"},
    "invitacion": set(),
    "refresh_token": {"SELECT", "INSERT"},
    "limite_tasa": {"SELECT", "INSERT"},
}


def _key_guc(guc: str) -> str:
    """Texto de pg_policies (espacios normalizados) de la clave hex de ``guc`` (0003)."""
    setting = f"current_setting('{guc}'::text, true)"
    return (
        f"CASE WHEN ({setting} ~ '^[0-9a-f]{{64}}$'::text) "
        f"THEN sha256(decode({setting}, 'hex'::text)) ELSE NULL::bytea END"
    )


def _uuid_guc(guc: str) -> str:
    """Texto de pg_policies (espacios normalizados) del UUID de ``guc`` (0003)."""
    setting = f"current_setting('{guc}'::text, true)"
    pattern = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    return f"CASE WHEN ({setting} ~ '{pattern}'::text) THEN ({setting})::uuid ELSE NULL::uuid END"


# Catálogo cerrado C6 (T3): políticas del dueño (0003) con su texto exacto, tal como lo
# devuelve pg_policies con los espacios normalizados.
# (tabla, nombre) -> (permissive, cmd, USING, WITH CHECK).
EXPECTED_OWNER_POLICIES = {
    ("invitacion", "dueno_invitacion_validar"): (
        "PERMISSIVE",
        "SELECT",
        f"(token_hash = {_key_guc('app.auth_inv_validar')})",
        None,
    ),
    ("invitacion", "dueno_invitacion_aceptar"): (
        "PERMISSIVE",
        "SELECT",
        f"(token_hash = {_key_guc('app.auth_inv_aceptar')})",
        None,
    ),
    ("invitacion", "dueno_invitacion_consumir"): (
        "PERMISSIVE",
        "UPDATE",
        f"((token_hash = {_key_guc('app.auth_inv_aceptar')}) AND (usada_en IS NULL) "
        "AND (expira_en > now()))",
        "(usada_en = now())",
    ),
    ("invitacion", "dueno_invitacion_crear_tenant"): (
        "PERMISSIVE",
        "INSERT",
        None,
        f"((tenant_id = {_uuid_guc('app.auth_tenant_nuevo')}) AND (rol = 'admin'::text) "  # noqa: S608
        "AND (creada_por IS NULL) AND (usada_en IS NULL) "
        "AND (expira_en <= (now() + '24:00:00'::interval)) "
        "AND (EXISTS ( SELECT 1 FROM tenant t "
        "WHERE ((t.id = invitacion.tenant_id) AND (t.creado_en = now())))))",
    ),
    ("usuario", "dueno_usuario_login"): (
        "PERMISSIVE",
        "SELECT",
        "(email = NULLIF(current_setting('app.auth_email'::text, true), ''::text))",
        None,
    ),
    ("usuario", "dueno_usuario_aceptar"): (
        "PERMISSIVE",
        "INSERT",
        None,
        "(EXISTS ( SELECT 1 FROM invitacion i "  # noqa: S608
        f"WHERE ((i.token_hash = {_key_guc('app.auth_inv_aceptar')}) "
        "AND (i.usada_en = now()) AND (i.email = usuario.email))))",
    ),
    ("membresia", "dueno_membresia_login"): (
        "PERMISSIVE",
        "SELECT",
        f"(usuario_id = {_uuid_guc('app.auth_usuario')})",
        None,
    ),
    ("membresia", "dueno_membresia_aceptar"): (
        "PERMISSIVE",
        "INSERT",
        None,
        f"((usuario_id = {_uuid_guc('app.auth_usuario_nuevo')}) "  # noqa: S608
        "AND (EXISTS ( SELECT 1 FROM invitacion i "
        "WHERE ((i.tenant_id = membresia.tenant_id) "
        f"AND (i.token_hash = {_key_guc('app.auth_inv_aceptar')}) "
        "AND (i.usada_en = now()) AND (i.rol = membresia.rol)))))",
    ),
    ("tenant", "dueno_tenant_crear"): (
        "PERMISSIVE",
        "INSERT",
        None,
        f"(id = {_uuid_guc('app.auth_tenant_nuevo')})",
    ),
    ("tenant", "dueno_tenant_recien_creado"): (
        "PERMISSIVE",
        "SELECT",
        f"((id = {_uuid_guc('app.auth_tenant_nuevo')}) AND (creado_en = now()))",
        None,
    ),
}

# Catálogo cerrado C6 (T3): funciones de acceso (0004).
# nombre -> (argumentos, resultado, GUC que fija, huella sha256 de prosrc, rol con EXECUTE).
# La huella obliga a que todo cambio del cuerpo se revise también aquí.
SEARCH_PATH = ["search_path=pg_catalog, pg_temp"]
EXPECTED_FUNCTIONS = {
    "buscar_login": (
        "p_email text",
        "TABLE(usuario_id uuid, password_hash text, activo boolean, tenant_id uuid, rol text)",
        {"app.auth_email", "app.auth_usuario"},
        "e2d65ea58fe28d0906cd6ecdc87126b3fe75f61105f6203bb15c93f4f8f1ae1c",
        "app",
    ),
    "validar_invitacion": (
        "p_clave text",
        "boolean",
        {"app.auth_inv_validar"},
        "c51ab1560e578613b40021f4eec9e2b0134f9ec19256524bc49636cc748ef19d",
        "app",
    ),
    "aceptar_invitacion": (
        "p_clave text, p_nombre text, p_password_hash text",
        "TABLE(usuario_id uuid, tenant_id uuid, rol text)",
        {"app.auth_inv_aceptar", "app.auth_usuario_nuevo"},
        "04aebfbb9e1aa4c96ddb0ffd18b70756f71e1db506b97e33f3e272a7daa95407",
        "app",
    ),
    "crear_tenant": (
        "p_nombre text, p_email text, p_clave text",
        "uuid",
        {"app.auth_tenant_nuevo"},
        "d2f0e9fef94935d417a6b7a54ef5048951ace8df125fdcb2628ddc90fcfca589",
        "migrator",
    ),
}
FUNCTION_CALLS = {
    "buscar_login": "select * from acceso.buscar_login('x@ejemplo.test')",
    "validar_invitacion": "select acceso.validar_invitacion('" + "0" * 64 + "')",
    "aceptar_invitacion": "select * from acceso.aceptar_invitacion('" + "0" * 64 + "', 'x', 'h')",
    "crear_tenant": "select acceso.crear_tenant('x', 'x@ejemplo.test', '" + "0" * 64 + "')",
}
# GRANT de auth_owner (0003): tabla -> privilegio -> columnas; nada a nivel de tabla.
EXPECTED_OWNER_COLUMNS = {
    "alembic_version": {},
    # SELECT solo de id y creado_en, y solo de la fila creada en su transacción (I2);
    # creado_en nunca en INSERT.
    "tenant": {"INSERT": {"id", "nombre"}, "SELECT": {"id", "creado_en"}},
    "usuario": {
        "SELECT": {"id", "email", "password_hash", "activo"},
        "INSERT": {"id", "email", "nombre", "password_hash"},
    },
    # Sin INSERT de id en membresia ni invitacion (M3): lo pone el DEFAULT.
    "membresia": {
        "SELECT": {"id", "tenant_id", "usuario_id", "rol", "activa"},
        "INSERT": {"tenant_id", "usuario_id", "rol"},
    },
    "invitacion": {
        "SELECT": {"tenant_id", "email", "rol", "token_hash", "expira_en", "usada_en"},
        "UPDATE": {"usada_en"},
        "INSERT": {"tenant_id", "email", "rol", "token_hash", "expira_en"},
    },
    "refresh_token": {},
    "limite_tasa": {},
}
TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
COLUMN_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "REFERENCES")


@dataclass(frozen=True)
class Catalog:
    url: URL
    app_role: str
    migrator: str


def _alembic_config() -> AlembicConfig:
    config = AlembicConfig(str(ALEMBIC_INI))
    config.attributes["configure_logger"] = False
    return config


def _fail(message: str) -> None:
    pytest.fail(message, pytrace=False)


@pytest.fixture(scope="module")
def catalog(database_residue_guard) -> Iterator[Catalog]:
    """Base temporal migrada a ``head``; se borra al terminar, junto con los roles creados."""
    migrator_url = read_database_url("TEST_MIGRATION_DATABASE_URL")
    app_url = read_database_url("TEST_DATABASE_URL")
    if migrator_url is None or app_url is None or not app_url.username:
        _fail(BLOCKED)
    name = f"assetcontrol_catalogo_{uuid.uuid4().hex[:12]}"
    admin = create_engine(migrator_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    created_roles: list[str] = []
    failure = None
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{name}"'))
            for role in SUPABASE_ROLES:
                exists = conn.scalar(
                    text("select exists (select 1 from pg_roles where rolname = :r)"), {"r": role}
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
    try:
        engine = create_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
        try:
            with engine.connect() as conn:
                # Como en Supabase: lo nuevo de public se concede por defecto a sus roles.
                for role in SUPABASE_ROLES:
                    conn.execute(
                        text(
                            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                            f'GRANT ALL ON TABLES TO "{role}"'
                        )
                    )
                    # Y EXECUTE de toda función nueva, en cualquier esquema (C7).
                    conn.execute(
                        text(f'ALTER DEFAULT PRIVILEGES GRANT EXECUTE ON FUNCTIONS TO "{role}"')
                    )
        finally:
            engine.dispose()

        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("MIGRATION_DATABASE_URL", url.render_as_string(hide_password=False))
            mp.delenv("DATABASE_URL", raising=False)
            mp.setenv("APP_DB_USER", app_url.username)
            command.upgrade(_alembic_config(), "head")

        yield Catalog(url=url, app_role=app_url.username, migrator=migrator_url.username)
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            for role in created_roles:
                conn.execute(text(f'DROP ROLE IF EXISTS "{role}"'))
        admin.dispose()


@pytest.fixture
def conn(catalog) -> Iterator[Connection]:
    engine = create_engine(catalog.url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            yield connection
    finally:
        engine.dispose()


def _public_tables(conn: Connection) -> set[str]:
    return set(
        conn.scalars(
            text(
                "select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace "
                "where n.nspname = 'public' and c.relkind in ('r', 'p', 'v', 'm', 'f')"
            )
        )
    )


def _rls_flags(conn: Connection, table: str) -> tuple[bool, bool]:
    row = conn.execute(
        text(
            "select c.relrowsecurity, c.relforcerowsecurity from pg_class c "
            "join pg_namespace n on n.oid = c.relnamespace "
            "where n.nspname = 'public' and c.relname = :t"
        ),
        {"t": table},
    ).one()
    return bool(row[0]), bool(row[1])


def _policies(conn: Connection) -> dict[tuple[str, str], tuple]:
    rows = conn.execute(
        text(
            "select tablename, policyname, permissive, cmd, roles::text, qual, with_check "
            "from pg_policies where schemaname = 'public'"
        )
    )
    return {(r[0], r[1]): (r[2], r[3], r[4], r[5], r[6]) for r in rows}


OWNER_ROLES = "{" + AUTH_OWNER + "}"


def _app_policies(conn: Connection) -> dict[tuple[str, str], tuple]:
    """Políticas que no son de ``auth_owner`` ni de la purga del migrador."""
    return {
        k: v
        for k, v in _policies(conn).items()
        if v[2] != OWNER_ROLES and k not in EXPECTED_PURGE_POLICIES
    }


def _purge_policies(conn: Connection) -> dict[tuple[str, str], tuple]:
    return {
        k: (v[0], v[1], _normalize(v[3]), _normalize(v[4]))
        for k, v in _policies(conn).items()
        if k in EXPECTED_PURGE_POLICIES
    }


def _normalize(expression: str | None) -> str | None:
    return None if expression is None else " ".join(expression.split())


def _owner_policies(conn: Connection) -> dict[tuple[str, str], tuple]:
    return {
        k: (v[0], v[1], _normalize(v[3]), _normalize(v[4]))
        for k, v in _policies(conn).items()
        if v[2] == OWNER_ROLES
    }


def _expected_policies(app_role: str) -> dict[tuple[str, str], tuple]:
    return {
        key: (permissive, cmd, roles.replace("app", app_role), qual, check)
        for key, (permissive, cmd, roles, qual, check) in EXPECTED_POLICIES.items()
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


def _table_privileges(conn: Connection, role: str, table: str) -> set[str]:
    return {
        privilege
        for privilege in TABLE_PRIVILEGES
        if conn.scalar(
            text("select has_table_privilege(:r, :t, :p)"),
            {"r": role, "t": f"public.{table}", "p": privilege},
        )
    }


def _acl_table_privileges(conn: Connection, role: str, table: str) -> set[str]:
    """Privilegios de tabla concedidos explícitamente a ``role`` (sin los de columna)."""
    rows = conn.scalars(
        text(
            "select a.privilege_type from pg_class c "
            "join pg_namespace n on n.oid = c.relnamespace "
            "cross join lateral aclexplode(c.relacl) a "
            "where n.nspname = 'public' and c.relname = :t and a.grantee = to_regrole(:r)"
        ),
        {"t": table, "r": role},
    )
    return set(rows)


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


def _existing_roles(conn: Connection, names: tuple[str, ...]) -> list[str]:
    return list(
        conn.scalars(
            text("select rolname from pg_roles where rolname = any(:n) order by rolname"),
            {"n": list(names)},
        )
    )


# --- Lista cerrada de tablas y regla general -----------------------------------


def test_exception_list_is_closed():
    assert EXCEPTIONS == {"alembic_version", "tenant", "usuario", "limite_tasa"}


def test_public_tables_are_exactly_the_expected(conn):
    assert _public_tables(conn) == EXCEPTIONS | TENANT_TABLES


def test_every_non_exception_table_is_tenant_isolated(conn, catalog):
    problems = []
    tables = _public_tables(conn) - EXCEPTIONS
    assert tables == TENANT_TABLES
    policies = _policies(conn)
    for table in sorted(tables):
        columns = _columns(conn, table)
        if columns.get("tenant_id") != ("uuid", True):
            problems.append(f"{table}: falta tenant_id uuid NOT NULL")
        if _rls_flags(conn, table) != (True, True):
            problems.append(f"{table}: RLS no habilitada y forzada")
        policy = policies.get((table, "tenant_isolation"))
        expected = ("PERMISSIVE", "ALL", f"{{{catalog.app_role}}}", ISOLATION_EXPR, ISOLATION_EXPR)
        if policy != expected:
            problems.append(f"{table}: tenant_isolation distinta: {policy}")
    assert problems == []


def test_no_role_but_the_owner_can_delete_or_truncate(conn, catalog):
    rows = conn.execute(
        text(
            "select c.relname, a.grantee::regrole::text, a.privilege_type "
            "from pg_class c join pg_namespace n on n.oid = c.relnamespace "
            "cross join lateral aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) a "
            "where n.nspname = 'public' and c.relkind in ('r', 'p') "
            "and a.privilege_type in ('DELETE', 'TRUNCATE') and a.grantee <> c.relowner"
        )
    ).all()
    assert rows == []
    for role in (catalog.app_role, AUTH_OWNER, *SUPABASE_ROLES):
        for table in _public_tables(conn):
            granted = _table_privileges(conn, role, table) & {"DELETE", "TRUNCATE"}
            assert granted == set(), (role, table)


def test_tables_are_owned_by_the_migrator(conn, catalog):
    owners = dict(
        conn.execute(
            text(
                "select c.relname, c.relowner::regrole::text from pg_class c "
                "join pg_namespace n on n.oid = c.relnamespace "
                "where n.nspname = 'public' and c.relkind = 'r'"
            )
        ).all()
    )
    assert set(owners.values()) == {catalog.migrator}


# --- Políticas: listas cerradas -----------------------------------------------


def test_public_policies_are_a_closed_list(conn, catalog):
    assert _app_policies(conn) == _expected_policies(catalog.app_role)
    assert _owner_policies(conn) == EXPECTED_OWNER_POLICIES
    assert _purge_policies(conn) == EXPECTED_PURGE_POLICIES
    assert len(_policies(conn)) == (
        len(EXPECTED_POLICIES) + len(EXPECTED_OWNER_POLICIES) + len(EXPECTED_PURGE_POLICIES)
    )


def test_restrictive_policies_are_a_closed_list(conn, catalog):
    restrictive = {key for key, value in _policies(conn).items() if value[0] == "RESTRICTIVE"}
    assert restrictive == {("invitacion", "invitacion_creada_por_no_nula")}


def test_no_policy_targets_public_and_each_targets_a_single_role(conn, catalog):
    # Cada política es de un solo rol: la aplicación o auth_owner, nunca los dos ni PUBLIC;
    # la única excepción es la purga de limite_tasa, solo del migrador (T10).
    for (table, name), (_, _, roles, _, _) in _policies(conn).items():
        assert "public" not in roles, (table, name)
        if (table, name) in EXPECTED_PURGE_POLICIES:
            assert roles == "{" + catalog.migrator + "}", (table, name)
            continue
        assert roles in ("{" + catalog.app_role + "}", OWNER_ROLES), (table, name)


def test_owner_policies_are_never_for_all(conn):
    for key, (_, cmd, _, _) in _owner_policies(conn).items():
        assert cmd != "ALL", key


def _compact(expression: str | None) -> str:
    return "".join((expression or "").split())


def test_bootstrap_invitation_is_bound_to_a_tenant_created_now(conn):
    # I2: la invitación de crear_tenant exige un tenant creado en la misma transacción,
    # y auth_owner solo lee esa fila. El texto completo lo fija el catálogo C6 de T3.
    policies = _policies(conn)
    check = _compact(policies[("invitacion", "dueno_invitacion_crear_tenant")][4])
    assert "EXISTS(SELECT1FROMtenanttWHERE((t.id=invitacion.tenant_id)AND" in check, check
    assert "(t.creado_en=now())" in check, check
    using = _compact(policies[("tenant", "dueno_tenant_recien_creado")][3])
    assert "(creado_en=now())" in using, using
    assert "app.auth_tenant_nuevo" in using, using


# --- GRANT por columna del rol de la aplicación --------------------------------


@pytest.mark.parametrize("table", sorted(EXPECTED_APP_COLUMNS))
def test_app_column_privileges_are_exact(conn, catalog, table):
    assert _column_privileges(conn, catalog.app_role, table) == EXPECTED_APP_COLUMNS[table]


@pytest.mark.parametrize("table", sorted(EXPECTED_APP_TABLE_PRIVILEGES))
def test_app_table_privileges_are_exact(conn, catalog, table):
    assert (
        _acl_table_privileges(conn, catalog.app_role, table)
        == (EXPECTED_APP_TABLE_PRIVILEGES[table])
    )


def test_app_cannot_read_password_or_invitation_hashes(conn, catalog):
    for table, column in (("usuario", "password_hash"), ("invitacion", "token_hash")):
        readable = conn.scalar(
            text("select has_column_privilege(:r, :t, :c, 'SELECT')"),
            {"r": catalog.app_role, "t": f"public.{table}", "c": column},
        )
        assert readable is False, (table, column)


def test_app_can_read_only_the_allowed_hash_columns(conn, catalog):
    # Regla general de §7.1 enmendada (Q20): ninguna columna con "hash" en el nombre es
    # legible por la aplicación salvo la lista cerrada. refresh_token.token_hash es la
    # única excepción (lo guardado es sha256 de la clave, I1).
    # T10: limite_tasa.clave_hash es la segunda, por docs/03 (cambio 6, aplicado por el
    # humano) y A13: GRANT SELECT de la tabla completa, porque ON CONFLICT exige SELECT
    # sobre las columnas del índice inferido (sin él, "permission denied"). Es un HMAC de
    # la IP o del email con clave derivada de SECRET_KEY: no autentica ni revela nada.
    # plan.md §7.1 aún dice "única excepción": pendiente de enmienda (decisión humana).
    rows = conn.execute(
        text(
            "select table_name, column_name from information_schema.columns "
            "where table_schema = 'public' and column_name like '%hash%'"
        )
    ).all()
    assert rows, "no se encontró ninguna columna hash: la prueba no comprueba nada"
    readable = {
        (table, column)
        for table, column in rows
        if conn.scalar(
            text("select has_column_privilege(:r, :t, :c, 'SELECT')"),
            {"r": catalog.app_role, "t": f"public.{table}", "c": column},
        )
    }
    assert readable == {("refresh_token", "token_hash"), ("limite_tasa", "clave_hash")}


def test_app_has_no_insert_or_update_on_tenant_usuario_membresia(conn, catalog):
    for table in ("tenant", "usuario", "membresia"):
        privileges = _column_privileges(conn, catalog.app_role, table)
        assert set(privileges) == {"SELECT"}, table


# --- Excepciones con prueba propia ----------------------------------------------


def test_exception_alembic_version_is_closed_to_the_app(conn, catalog):
    assert _table_privileges(conn, catalog.app_role, "alembic_version") == set()
    assert _column_privileges(conn, catalog.app_role, "alembic_version") == {}


def test_exception_tenant(conn, catalog):
    assert "tenant_id" not in _columns(conn, "tenant")
    assert _rls_flags(conn, "tenant") == (True, True)
    tenant_policies = {k: v for k, v in _app_policies(conn).items() if k[0] == "tenant"}
    owner_tenant = {k for k in _owner_policies(conn) if k[0] == "tenant"}
    assert owner_tenant == {
        ("tenant", "dueno_tenant_crear"),
        ("tenant", "dueno_tenant_recien_creado"),
    }
    assert tenant_policies == {
        ("tenant", "tenant_isolation"): _expected_policies(catalog.app_role)[
            ("tenant", "tenant_isolation")
        ]
    }
    assert _table_privileges(conn, catalog.app_role, "tenant") == {"SELECT"}


def test_exception_usuario(conn, catalog):
    columns = _columns(conn, "usuario")
    assert "tenant_id" not in columns
    assert set(columns) == {"id", "email", "nombre", "password_hash", "activo"}
    assert _rls_flags(conn, "usuario") == (True, True)
    usuario_policies = {k: v for k, v in _app_policies(conn).items() if k[0] == "usuario"}
    # Solo lectura acotada a la membresía del tenant fijado; sin INSERT/UPDATE.
    assert set(usuario_policies) == {("usuario", "usuario_por_membresia")}
    assert usuario_policies[("usuario", "usuario_por_membresia")][1] == "SELECT"
    assert _table_privileges(conn, catalog.app_role, "usuario") == set()


def test_exception_limite_tasa(conn, catalog):
    # Tabla de infraestructura (docs/03 cambio 6, plan.md §3.1, A13): sin tenant_id, solo
    # hashes y contadores, RLS forzada, una política por comando TO la aplicación, sin
    # DELETE para nadie salvo la purga del migrador (dueño).
    assert _columns(conn, "limite_tasa") == {
        "ambito": ("text", True),
        "clave_hash": ("bytea", True),
        "ventana_inicio": ("timestamp with time zone", True),
        "intentos": ("integer", True),
    }
    assert _rls_flags(conn, "limite_tasa") == (True, True)
    app_policies = {k: v for k, v in _app_policies(conn).items() if k[0] == "limite_tasa"}
    assert {v[1] for v in app_policies.values()} == {"SELECT", "INSERT", "UPDATE"}
    assert len(app_policies) == 3
    assert {k for k in _owner_policies(conn) if k[0] == "limite_tasa"} == set()
    assert _table_privileges(conn, catalog.app_role, "limite_tasa") == {"SELECT", "INSERT"}
    assert _column_privileges(conn, catalog.app_role, "limite_tasa")["UPDATE"] == {"intentos"}
    for role in (catalog.app_role, AUTH_OWNER, *SUPABASE_ROLES):
        assert not _table_privileges(conn, role, "limite_tasa") & {"DELETE", "TRUNCATE"}, role
    assert _purge_policies(conn) == EXPECTED_PURGE_POLICIES


# --- Roles de Supabase y auth_owner ---------------------------------------------


def test_supabase_roles_receive_nothing(conn):
    roles = _existing_roles(conn, SUPABASE_ROLES)
    assert roles == sorted(SUPABASE_ROLES)
    for role in roles:
        for table in _public_tables(conn):
            assert _acl_table_privileges(conn, role, table) == set(), (role, table)
            assert _column_privileges(conn, role, table) == {}, (role, table)
        assert not conn.scalar(
            text("select has_schema_privilege(:r, 'acceso', 'USAGE')"), {"r": role}
        ), role


def test_auth_owner_privileges_are_exactly_its_column_grants(conn):
    # GRANT por columna de 0003 (T2); ninguno a nivel de tabla.
    assert set(_public_tables(conn)) == set(EXPECTED_OWNER_COLUMNS)
    for table in _public_tables(conn):
        assert _acl_table_privileges(conn, AUTH_OWNER, table) == set(), table
        expected = EXPECTED_OWNER_COLUMNS[table]
        assert _column_privileges(conn, AUTH_OWNER, table) == expected, table


# --- Esquema acceso -------------------------------------------------------------


def test_acceso_schema_is_owned_by_the_migrator_with_minimal_usage(conn, catalog):
    owner = conn.scalar(
        text("select nspowner::regrole::text from pg_namespace where nspname = 'acceso'")
    )
    assert owner == catalog.migrator
    acl = conn.execute(
        text(
            "select a.grantee::regrole::text, a.privilege_type from pg_namespace n "
            "cross join lateral aclexplode(n.nspacl) a "
            "where n.nspname = 'acceso' and a.grantee <> n.nspowner"
        )
    ).all()
    assert sorted(acl) == sorted([(catalog.app_role, "USAGE"), (AUTH_OWNER, "USAGE")])
    for role in (catalog.app_role, AUTH_OWNER):
        assert not conn.scalar(
            text("select has_schema_privilege(:r, 'acceso', 'CREATE')"), {"r": role}
        ), role


def test_acceso_schema_has_no_relations_or_types(conn):
    # Solo las funciones de C6: ni tablas, ni vistas, ni secuencias, ni tipos propios.
    objects = conn.scalar(
        text(
            "select (select count(*) from pg_class c join pg_namespace n "
            "on n.oid = c.relnamespace where n.nspname = 'acceso') + "
            "(select count(*) from pg_type t join pg_namespace n "
            "on n.oid = t.typnamespace where n.nspname = 'acceso')"
        )
    )
    assert objects == 0


def test_create_on_acceso_is_not_left_open_and_the_migrator_is_not_a_member(conn, catalog):
    # C5: el CREATE y la membresía transitorios de 0004 se cierran en la misma migración.
    assert not conn.scalar(text("select has_schema_privilege('auth_owner', 'acceso', 'CREATE')"))
    members = conn.scalars(
        text(
            "select m.member::regrole::text from pg_auth_members m "
            "where m.roleid = 'auth_owner'::regrole"
        )
    ).all()
    assert catalog.migrator not in members
    assert members == []


# --- Catálogo cerrado C6: funciones de acceso (T3) -------------------------------


def _functions(conn: Connection) -> dict[str, dict[str, object]]:
    rows = conn.execute(
        text(
            "select p.proname, pg_get_function_identity_arguments(p.oid), "
            "pg_get_function_result(p.oid), p.prosecdef, p.proisstrict, l.lanname, "
            "p.provolatile, p.proowner::regrole::text, p.proconfig, p.prosrc, p.prokind "
            "from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
            "join pg_language l on l.oid = p.prolang where n.nspname = 'acceso'"
        )
    ).all()
    keys = ("args", "result", "secdef", "strict", "lang", "volatile", "owner", "config", "src")
    return {row[0]: dict(zip(keys + ("kind",), row[1:], strict=True)) for row in rows}


def _function_acl(conn: Connection, name: str) -> set[tuple[str, str, str, bool]]:
    rows = conn.execute(
        text(
            # grantee 0 = PUBLIC. Sin proacl (NULL) valdría el defecto: EXECUTE a PUBLIC.
            "select case when a.grantee = 0 then 'PUBLIC' else a.grantee::regrole::text end, "
            "a.grantor::regrole::text, a.privilege_type, a.is_grantable "
            "from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
            "cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a "
            "where n.nspname = 'acceso' and p.proname = :n"
        ),
        {"n": name},
    ).all()
    return {tuple(row) for row in rows}


def test_acceso_functions_are_a_closed_list(conn):
    assert set(_functions(conn)) == set(EXPECTED_FUNCTIONS)


@pytest.mark.parametrize("name", sorted(EXPECTED_FUNCTIONS))
def test_acceso_function_signature_and_attributes(conn, name):
    function = _functions(conn)[name]
    args, result, _, _, _ = EXPECTED_FUNCTIONS[name]
    assert (function["args"], function["result"]) == (args, result)
    assert function["kind"] == "f"
    assert function["secdef"] is True
    assert function["strict"] is True
    assert function["lang"] == "plpgsql"
    assert function["volatile"] == "v"
    assert function["owner"] == AUTH_OWNER
    assert function["config"] == SEARCH_PATH


@pytest.mark.parametrize("name", sorted(EXPECTED_FUNCTIONS))
def test_acceso_function_acl_is_exact(conn, catalog, name):
    # Solo auth_owner (dueña) y la aplicación, o el migrador en crear_tenant; nunca PUBLIC
    # ni los roles de Supabase, aunque sus privilegios por defecto se lo dieran.
    grantee = {"app": catalog.app_role, "migrator": catalog.migrator}[EXPECTED_FUNCTIONS[name][4]]
    assert _function_acl(conn, name) == {
        (AUTH_OWNER, AUTH_OWNER, "EXECUTE", False),
        (grantee, AUTH_OWNER, "EXECUTE", False),
    }


@pytest.mark.parametrize("name", sorted(EXPECTED_FUNCTIONS))
def test_acceso_function_body_is_exactly_the_reviewed_one(conn, name):
    source = _functions(conn)[name]["src"]
    assert hashlib.sha256(source.encode()).hexdigest() == EXPECTED_FUNCTIONS[name][3]


_RELATION_REFERENCE = re.compile(r"\b(?:FROM|JOIN|UPDATE|INTO)\s+([A-Za-z_][\w]*)(\.)?", re.I)


@pytest.mark.parametrize("name", sorted(EXPECTED_FUNCTIONS))
def test_acceso_function_body_is_static_qualified_and_reads_no_guc(conn, name):
    source = _functions(conn)[name]["src"]
    lowered = source.lower()
    # Nunca lee una GUC: no depende de una que quien llama fijó antes (revisión de T3).
    assert "current_setting" not in lowered
    # SQL estático.
    assert re.search(r"\bexecute\b", lowered) is None
    assert "format(" not in lowered
    # Toda relación calificada: public.<tabla> o pg_catalog.<función>; INTO de plpgsql
    # solo a variables v_*.
    for match in _RELATION_REFERENCE.finditer(source):
        word, qualified = match.group(1), match.group(2)
        if qualified:
            assert word in ("public", "pg_catalog"), match.group(0)
        else:
            assert word.startswith("v_"), match.group(0)
    # Fija sus GUC y vacía las seis al empezar y al terminar.
    for guc in EXPECTED_FUNCTIONS[name][2]:
        assert f"pg_catalog.set_config('{guc}'," in source, guc
    assert source.count("pg_catalog.set_config(g, '', true)") >= 2


def test_functions_are_not_executable_by_public(conn):
    for name in EXPECTED_FUNCTIONS:
        assert not any(entry[0] == "PUBLIC" for entry in _function_acl(conn, name)), name


def test_app_executes_only_the_login_and_invitation_functions(conn, catalog):
    for name, (args, *_rest) in EXPECTED_FUNCTIONS.items():
        signature = f"acceso.{name}({', '.join(a.split()[-1] for a in args.split(', '))})"
        allowed = conn.scalar(
            text("select has_function_privilege(:r, :f, 'EXECUTE')"),
            {"r": catalog.app_role, "f": signature},
        )
        assert allowed is (name != "crear_tenant"), name


# --- C7: los roles de Supabase no ejecutan nada de acceso --------------------------


@pytest.mark.parametrize("role", SUPABASE_ROLES)
@pytest.mark.parametrize("name", sorted(EXPECTED_FUNCTIONS))
def test_supabase_roles_cannot_execute_acceso_functions(catalog, role, name):
    engine = create_engine(catalog.url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            for with_usage in (False, True):
                tx = connection.begin()
                try:
                    if with_usage:
                        # Aun con USAGE en el esquema, el REVOKE de la función lo frena.
                        connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA acceso TO "{role}"')
                    connection.exec_driver_sql(f'SET LOCAL ROLE "{role}"')
                    with pytest.raises(DBAPIError) as excinfo:
                        connection.execute(text(FUNCTION_CALLS[name]))
                finally:
                    tx.rollback()
                message = str(excinfo.value.orig)
                assert excinfo.value.orig.sqlstate == "42501", message
                expected = "permission denied for " + ("function" if with_usage else "schema")
                assert expected in message, message
    finally:
        engine.dispose()


def test_no_own_functions_in_public(conn):
    functions = conn.scalars(
        text(
            "select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
            "where n.nspname = 'public'"
        )
    ).all()
    assert functions == []


# --- Claves, CHECK e índices ----------------------------------------------------


def _constraints(conn: Connection, table: str) -> set[str]:
    return set(
        conn.scalars(
            text(
                "select pg_get_constraintdef(oid) from pg_constraint "
                "where conrelid = to_regclass(:t) and contype in ('c', 'u', 'f', 'p')"
            ),
            {"t": f"public.{table}"},
        )
    )


def _unique_indexes(conn: Connection, table: str) -> set[str]:
    return set(
        conn.scalars(
            text(
                "select pg_get_indexdef(i.indexrelid) from pg_index i "
                "where i.indrelid = to_regclass(:t) and i.indisunique"
            ),
            {"t": f"public.{table}"},
        )
    )


def test_keys_and_checks(conn):
    normalized = "CHECK ((email = lower(btrim(email))))"
    rol = "CHECK ((rol = ANY (ARRAY['admin'::text, 'contador'::text])))"
    hash32 = "CHECK ((octet_length(token_hash) = 32))"

    assert _constraints(conn, "tenant") == {"PRIMARY KEY (id)"}
    assert _constraints(conn, "usuario") == {"PRIMARY KEY (id)", normalized}
    assert any("(email)" in idx for idx in _unique_indexes(conn, "usuario"))
    assert _constraints(conn, "membresia") == {
        "PRIMARY KEY (id)",
        "FOREIGN KEY (tenant_id) REFERENCES tenant(id)",
        "FOREIGN KEY (usuario_id) REFERENCES usuario(id)",
        "UNIQUE (tenant_id, usuario_id)",
        "UNIQUE (tenant_id, id)",
        rol,
    }
    assert _constraints(conn, "invitacion") == {
        "PRIMARY KEY (id)",
        "FOREIGN KEY (tenant_id) REFERENCES tenant(id)",
        # MATCH SIMPLE (por defecto): creada_por NULL = creada por el operador.
        "FOREIGN KEY (tenant_id, creada_por) REFERENCES membresia(tenant_id, usuario_id)",
        "UNIQUE (token_hash)",
        normalized,
        rol,
        hash32,
    }
    assert _constraints(conn, "refresh_token") == {
        "PRIMARY KEY (id)",
        "FOREIGN KEY (tenant_id, membresia_id) REFERENCES membresia(tenant_id, id)",
        "UNIQUE (token_hash)",
        hash32,
    }
    assert _constraints(conn, "limite_tasa") == {
        "PRIMARY KEY (ambito, clave_hash, ventana_inicio)",
        "CHECK ((ambito = ANY (ARRAY['login_ip'::text, 'login_cuenta'::text, "
        "'refresh_ip'::text, 'validar_ip'::text, 'aceptar_ip'::text])))",
        "CHECK ((octet_length(clave_hash) = 32))",
        "CHECK ((intentos >= 0))",
    }


def test_column_types_and_nullability(conn):
    assert _columns(conn, "invitacion") == {
        "id": ("uuid", True),
        "tenant_id": ("uuid", True),
        "email": ("text", True),
        "rol": ("text", True),
        "token_hash": ("bytea", True),
        "expira_en": ("timestamp with time zone", True),
        "usada_en": ("timestamp with time zone", False),
        "creada_por": ("uuid", False),
    }
    assert _columns(conn, "refresh_token") == {
        "id": ("uuid", True),
        "tenant_id": ("uuid", True),
        "membresia_id": ("uuid", True),
        "familia_id": ("uuid", True),
        "token_hash": ("bytea", True),
        "expira_en": ("timestamp with time zone", True),
        "usado_en": ("timestamp with time zone", False),
        "revocado_en": ("timestamp with time zone", False),
        "creado_en": ("timestamp with time zone", True),
    }
    assert _columns(conn, "membresia") == {
        "id": ("uuid", True),
        "tenant_id": ("uuid", True),
        "usuario_id": ("uuid", True),
        "rol": ("text", True),
        "activa": ("boolean", True),
    }
    assert _columns(conn, "usuario") == {
        "id": ("uuid", True),
        "email": ("text", True),
        "nombre": ("text", True),
        "password_hash": ("text", True),
        "activo": ("boolean", True),
    }
    assert _columns(conn, "tenant") == {
        "id": ("uuid", True),
        "nombre": ("text", True),
        "creado_en": ("timestamp with time zone", True),
    }


def test_refresh_token_familia_is_indexed(conn):
    indexes = set(
        conn.scalars(
            text(
                "select pg_get_indexdef(indexrelid) from pg_index where indrelid = to_regclass(:t)"
            ),
            {"t": "public.refresh_token"},
        )
    )
    assert any("(familia_id)" in idx for idx in indexes)


# --- Modelos ORM ----------------------------------------------------------------


def test_models_match_the_migrated_schema(conn):
    tables = {table.name: table for table in models.Base.metadata.sorted_tables}
    assert set(tables) == {"tenant", "usuario"} | TENANT_TABLES
    for name, table in tables.items():
        assert {c.name for c in table.columns} == set(_columns(conn, name)), name


def test_models_never_select_the_hash_columns_by_default():
    usuario_sql = str(select(models.Usuario))
    invitacion_sql = str(select(models.Invitacion))
    assert "password_hash" not in usuario_sql
    assert "token_hash" not in invitacion_sql
