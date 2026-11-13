"""Prueba de catálogo de RLS, parte de tablas (spec 002, T1; A2, C6; plan.md §3 y §7.1).

Sobre una base temporal migrada a ``head`` con el rol migrador comprueba, leyendo
los catálogos de PostgreSQL:

- Toda tabla de ``public`` fuera de la lista cerrada de excepciones tiene
  ``tenant_id``, RLS habilitada y forzada y la política ``tenant_isolation``
  ``TO`` el rol de la aplicación (sin ``PUBLIC``).
- Ningún rol distinto del dueño tiene ``DELETE`` (ni ``TRUNCATE``) en ``public``.
- Las excepciones (``alembic_version``, ``tenant``, ``usuario`` y
  ``limite_tasa``) tienen su prueba propia; ``limite_tasa`` se crea en T10 y la
  excepción es por nombre.
- Las políticas de ``public`` y las ``RESTRICTIVE`` forman listas cerradas.
- Los ``GRANT`` del rol de la aplicación son exactamente los de plan.md §3, por
  columna: nunca ``usuario.password_hash`` ni ``invitacion.token_hash``.
- ``anon``, ``authenticated`` y ``service_role`` (roles de Supabase) no reciben
  nada aunque existan privilegios por defecto que se los den.
- El esquema ``acceso`` existe, vacío, con ``USAGE`` solo para la aplicación y
  ``auth_owner`` y sin ``CREATE`` para nadie más que su dueño.

Los roles de Supabase no existen en local ni en la CI: la prueba los crea (solo
los que falten), les da privilegios por defecto en la base temporal, migra y los
borra al terminar.
"""

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
from sqlalchemy.exc import SQLAlchemyError
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
}
# Privilegios a nivel de tabla del rol de la aplicación (sin columnas).
EXPECTED_APP_TABLE_PRIVILEGES = {
    "alembic_version": set(),
    "tenant": {"SELECT"},
    "usuario": set(),
    "membresia": {"SELECT"},
    "invitacion": set(),
    "refresh_token": {"SELECT", "INSERT"},
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
    # limite_tasa llega en T10: hasta entonces su excepción no exige que exista.
    assert _public_tables(conn) == {"alembic_version", "tenant", "usuario"} | TENANT_TABLES


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
    assert _policies(conn) == _expected_policies(catalog.app_role)


def test_restrictive_policies_are_a_closed_list(conn, catalog):
    restrictive = {key for key, value in _policies(conn).items() if value[0] == "RESTRICTIVE"}
    assert restrictive == {("invitacion", "invitacion_creada_por_no_nula")}


def test_no_policy_targets_public_or_auth_owner_yet(conn):
    # Las políticas TO auth_owner llegan en T2 (0003) y amplían esta lista cerrada.
    for (table, name), (_, _, roles, _, _) in _policies(conn).items():
        assert "public" not in roles, (table, name)
        assert AUTH_OWNER not in roles, (table, name)


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
    # Ojo: en T10, limite_tasa.clave_hash será otra excepción; antes hay que enmendar
    # plan.md §7.1/§3.1 con decisión humana y solo entonces ampliar esta lista.
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
    assert readable == {("refresh_token", "token_hash")}


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
    tenant_policies = {k: v for k, v in _policies(conn).items() if k[0] == "tenant"}
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
    usuario_policies = {k: v for k, v in _policies(conn).items() if k[0] == "usuario"}
    # Solo lectura acotada a la membresía del tenant fijado; sin INSERT/UPDATE.
    assert set(usuario_policies) == {("usuario", "usuario_por_membresia")}
    assert usuario_policies[("usuario", "usuario_por_membresia")][1] == "SELECT"
    assert _table_privileges(conn, catalog.app_role, "usuario") == set()


def test_exception_limite_tasa_does_not_exist_until_t10(conn):
    assert "limite_tasa" in EXCEPTIONS
    assert "limite_tasa" not in _public_tables(conn)


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


def test_auth_owner_has_no_table_privileges_yet(conn):
    # Sus GRANT por columna llegan en T2 (0003).
    for table in _public_tables(conn):
        assert _table_privileges(conn, AUTH_OWNER, table) == set(), table
        assert _column_privileges(conn, AUTH_OWNER, table) == {}, table


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


def test_acceso_schema_is_empty_until_t3(conn):
    objects = conn.scalar(
        text(
            "select (select count(*) from pg_class c join pg_namespace n "
            "on n.oid = c.relnamespace where n.nspname = 'acceso') + "
            "(select count(*) from pg_proc p join pg_namespace n "
            "on n.oid = p.pronamespace where n.nspname = 'acceso')"
        )
    )
    assert objects == 0


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
