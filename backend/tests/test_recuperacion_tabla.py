"""Tabla ``recuperacion_contrasena`` y ámbitos nuevos de ``limite_tasa`` (spec 014, T1).

Comportamiento real del esquema de la migración ``0015_recuperacion_contrasena``
sobre una base temporal migrada a ``head`` (``plan.md`` §3.1 y §3.2; ``spec.md``
R3, R4, R15, A4, A10, A11):

- columnas, ``CHECK``, ``UNIQUE``, FK compuesta a ``membresia`` e índice único parcial
  (un enlace vivo por usuario; otro se admite tras ``usada_en`` o ``invalidada_en``);
- ``expira_en`` como máximo 30 minutos después de ``creado_en``; ``usada_en`` e
  ``invalidada_en`` excluyentes;
- RLS habilitada y forzada con ``tenant_isolation`` ``TO`` el rol de la aplicación y
  **ningún privilegio** para la aplicación, ``auth_owner`` ni ``PUBLIC``: la aplicación
  recibe ``permission denied`` en ``SELECT``/``INSERT``/``UPDATE``/``DELETE``; si un
  ``GRANT`` llegara por error, la política sigue aislando por tenant;
- ``limite_tasa`` acepta ``recuperar_ip``, ``recuperar_cuenta`` y ``restablecer_ip`` y
  sigue rechazando un ámbito desconocido.

Las funciones ``acceso.*`` que operan la tabla son de T2. Datos sintéticos sembrados
por el rol migrador (superusuario en local y en la CI); toda prueba revierte lo suyo.
"""

import hashlib
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from conftest import BLOCKED, read_database_url, role_sees_all_rows
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.pool import NullPool

BACKEND_DIR = Path(__file__).resolve().parent.parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
TABLE = "recuperacion_contrasena"
AUTH_OWNER = "auth_owner"

UNIQUE_VIOLATION = "23505"
CHECK_VIOLATION = "23514"
FOREIGN_KEY_VIOLATION = "23503"
INSUFFICIENT_PRIVILEGE = "42501"

TENANT_A = uuid.UUID("00000000-0000-4000-8000-00000000a014")
TENANT_B = uuid.UUID("00000000-0000-4000-8000-00000000b014")
USER_A = uuid.UUID("00000000-0000-4000-8000-0000000a1401")
USER_A2 = uuid.UUID("00000000-0000-4000-8000-0000000a1402")
USER_B = uuid.UUID("00000000-0000-4000-8000-0000000b1401")

TENANT_EXPR = "(NULLIF(current_setting('app.tenant_id'::text, true), ''::text))::uuid"
ISOLATION_EXPR = f"(tenant_id = {TENANT_EXPR})"
NEW_SCOPES = ("recuperar_ip", "recuperar_cuenta", "restablecer_ip")
OLD_SCOPES = ("login_ip", "login_cuenta", "refresh_ip", "validar_ip", "aceptar_ip")
TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
COLUMN_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "REFERENCES")


@dataclass(frozen=True)
class RecDb:
    app_role: str
    migrator: Engine
    app: Engine


def _fail(message: str) -> None:
    pytest.fail(message, pytrace=False)


def _alembic_config() -> AlembicConfig:
    config = AlembicConfig(str(ALEMBIC_INI))
    config.attributes["configure_logger"] = False
    return config


def _seed(conn: Connection) -> None:
    """Dos tenants sintéticos: A con dos usuarios y B con uno, cada uno con membresía."""
    for tenant in (TENANT_A, TENANT_B):
        conn.execute(
            text("insert into tenant (id, nombre) values (:id, :n)"),
            {"id": tenant, "n": f"Clínica sintética {str(tenant)[-4:]}"},
        )
    for tenant, user in ((TENANT_A, USER_A), (TENANT_A, USER_A2), (TENANT_B, USER_B)):
        conn.execute(
            text(
                "insert into usuario (id, email, nombre, password_hash) "
                "values (:id, :e, 'Persona sintética', 'hash-sintetico-no-valido')"
            ),
            {"id": user, "e": f"rec.{str(user)[-6:]}@ejemplo.test"},
        )
        conn.execute(
            text("insert into membresia (tenant_id, usuario_id, rol) values (:t, :u, 'admin')"),
            {"t": tenant, "u": user},
        )


@pytest.fixture(scope="module")
def db(database_residue_guard) -> Iterator[RecDb]:
    """Base temporal en ``head`` con datos sintéticos; se borra al terminar."""
    migrator_url = read_database_url("TEST_MIGRATION_DATABASE_URL")
    app_url = read_database_url("TEST_DATABASE_URL")
    if migrator_url is None or app_url is None or not app_url.username:
        _fail(BLOCKED)
    name = f"assetcontrol_recuperacion_{uuid.uuid4().hex[:12]}"

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

    engines: list[Engine] = []
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
        app = create_engine(app_url.set(database=name), poolclass=NullPool)
        engines += [migrator, app]
        with migrator.begin() as conn:
            _seed(conn)
        yield RecDb(app_role=app_url.username, migrator=migrator, app=app)
    finally:
        for engine in engines:
            engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


# --- Utilidades -----------------------------------------------------------------


@contextmanager
def rolled_back(engine: Engine) -> Iterator[Connection]:
    """Transacción que siempre se revierte."""
    with engine.connect() as conn:
        tx = conn.begin()
        try:
            yield conn
        finally:
            tx.rollback()


def token_hash(seed: str | None = None) -> bytes:
    """``sha256(clave)`` de 32 bytes, como lo guardará ``acceso.solicitar_recuperacion``."""
    clave = hashlib.sha256((seed or uuid.uuid4().hex).encode()).digest()
    return hashlib.sha256(clave).digest()


INSERT = (
    f"insert into {TABLE} (tenant_id, usuario_id, token_hash, expira_en, usada_en, "  # noqa: S608
    "invalidada_en) values (:t, :u, :h, now() + cast(:vence as interval), "
    "now() + cast(:usada as interval), now() + cast(:invalidada as interval)) returning id"
)


def insert(
    conn: Connection,
    tenant: uuid.UUID = TENANT_A,
    user: uuid.UUID = USER_A,
    *,
    hash_: bytes | None = None,
    vence: str = "30 minutes",
    usada: str | None = None,
    invalidada: str | None = None,
) -> uuid.UUID:
    return conn.execute(
        text(INSERT),
        {
            "t": tenant,
            "u": user,
            "h": token_hash() if hash_ is None else hash_,
            "vence": vence,
            "usada": usada,
            "invalidada": invalidada,
        },
    ).scalar_one()


def fails(conn: Connection, sqlstate: str, statement: str, params: dict | None = None) -> str:
    """Ejecuta en un savepoint y exige el SQLSTATE; devuelve el mensaje."""
    savepoint = conn.begin_nested()
    with pytest.raises(DBAPIError) as excinfo:
        conn.execute(text(statement), params or {})
    savepoint.rollback()
    assert excinfo.value.orig.sqlstate == sqlstate, str(excinfo.value.orig)
    return str(excinfo.value.orig)


def insert_fails(conn: Connection, sqlstate: str, **kwargs) -> str:
    savepoint = conn.begin_nested()
    with pytest.raises(DBAPIError) as excinfo:
        insert(conn, **kwargs)
    savepoint.rollback()
    assert excinfo.value.orig.sqlstate == sqlstate, str(excinfo.value.orig)
    return str(excinfo.value.orig)


# --- Forma de la tabla ------------------------------------------------------------


def test_columns_types_and_nullability(db):
    with rolled_back(db.migrator) as conn:
        rows = conn.execute(
            text(
                "select column_name, data_type, is_nullable, column_default "
                "from information_schema.columns "
                "where table_schema = 'public' and table_name = :t"
            ),
            {"t": TABLE},
        ).all()
    columns = {r[0]: (r[1], r[2] == "NO") for r in rows}
    assert columns == {
        "id": ("uuid", True),
        "tenant_id": ("uuid", True),
        "usuario_id": ("uuid", True),
        "token_hash": ("bytea", True),
        "expira_en": ("timestamp with time zone", True),
        "usada_en": ("timestamp with time zone", False),
        "invalidada_en": ("timestamp with time zone", False),
        "creado_en": ("timestamp with time zone", True),
    }
    defaults = {r[0]: r[3] for r in rows if r[3] is not None}
    assert defaults == {"id": "gen_random_uuid()", "creado_en": "now()"}


def test_constraints_are_exactly_the_planned(db):
    with rolled_back(db.migrator) as conn:
        constraints = set(
            conn.scalars(
                text(
                    "select pg_get_constraintdef(oid) from pg_constraint "
                    "where conrelid = to_regclass(:t)"
                ),
                {"t": f"public.{TABLE}"},
            )
        )
    assert constraints == {
        "PRIMARY KEY (id)",
        "FOREIGN KEY (tenant_id) REFERENCES tenant(id)",
        "FOREIGN KEY (tenant_id, usuario_id) REFERENCES membresia(tenant_id, usuario_id)",
        "UNIQUE (token_hash)",
        "CHECK ((octet_length(token_hash) = 32))",
        "CHECK ((expira_en <= (creado_en + '00:30:00'::interval)))",
        "CHECK (((usada_en IS NULL) OR (invalidada_en IS NULL)))",
    }


def test_one_live_link_per_user_is_a_partial_unique_index(db):
    with rolled_back(db.migrator) as conn:
        indexes = set(
            conn.scalars(
                text(
                    "select pg_get_indexdef(i.indexrelid) from pg_index i "
                    "where i.indrelid = to_regclass(:t) and i.indisunique "
                    "and not i.indisprimary"
                ),
                {"t": f"public.{TABLE}"},
            )
        )
    partial = (
        f"CREATE UNIQUE INDEX recuperacion_contrasena_pendiente_key ON public.{TABLE} "
        "USING btree (usuario_id) WHERE ((usada_en IS NULL) AND (invalidada_en IS NULL))"
    )
    assert partial in indexes
    assert len(indexes) == 2  # el parcial y el UNIQUE (token_hash)


# --- Índice parcial: un enlace vivo por usuario (R4, A4) --------------------------


def test_second_pending_link_of_the_same_user_fails(db):
    with rolled_back(db.migrator) as conn:
        insert(conn)
        insert_fails(conn, UNIQUE_VIOLATION)


@pytest.mark.parametrize("closed", ["usada", "invalidada"])
def test_a_new_link_is_allowed_after_the_previous_is_used_or_invalidated(db, closed):
    with rolled_back(db.migrator) as conn:
        insert(conn, **{closed: "0 seconds"})
        insert(conn)
        insert_fails(conn, UNIQUE_VIOLATION)  # y el nuevo vuelve a ser el único vivo


def test_invalidating_the_pending_link_frees_the_slot(db):
    with rolled_back(db.migrator) as conn:
        first = insert(conn)
        conn.execute(
            text(f"update {TABLE} set invalidada_en = now() where id = :id"),  # noqa: S608
            {"id": first},
        )
        insert(conn)


def test_pending_links_of_different_users_coexist(db):
    with rolled_back(db.migrator) as conn:
        insert(conn, TENANT_A, USER_A)
        insert(conn, TENANT_A, USER_A2)
        insert(conn, TENANT_B, USER_B)


# --- CHECK, UNIQUE y FK -----------------------------------------------------------


def test_expiry_of_exactly_30_minutes_is_accepted(db):
    with rolled_back(db.migrator) as conn:
        insert(conn, vence="30 minutes")


@pytest.mark.parametrize("vence", ["30 minutes 1 second", "31 minutes", "1 day"])
def test_expiry_beyond_30_minutes_fails_the_check(db, vence):
    with rolled_back(db.migrator) as conn:
        insert_fails(conn, CHECK_VIOLATION, vence=vence)


def test_used_and_invalidated_are_mutually_exclusive(db):
    with rolled_back(db.migrator) as conn:
        insert_fails(conn, CHECK_VIOLATION, usada="0 seconds", invalidada="0 seconds")
        used = insert(conn, usada="0 seconds")
        fails(
            conn,
            CHECK_VIOLATION,
            f"update {TABLE} set invalidada_en = now() where id = :id",  # noqa: S608
            {"id": used},
        )


@pytest.mark.parametrize("size", [0, 31, 33, 64])
def test_token_hash_must_have_32_bytes(db, size):
    with rolled_back(db.migrator) as conn:
        insert_fails(conn, CHECK_VIOLATION, hash_=b"\x01" * size)


def test_token_hash_is_unique_across_users_and_tenants(db):
    same = token_hash("token-sintetico-repetido")
    with rolled_back(db.migrator) as conn:
        insert(conn, TENANT_A, USER_A, hash_=same)
        insert_fails(conn, UNIQUE_VIOLATION, tenant=TENANT_B, user=USER_B, hash_=same)


def test_the_link_needs_a_membership_of_the_user_in_that_tenant(db):
    with rolled_back(db.migrator) as conn:
        insert_fails(conn, FOREIGN_KEY_VIOLATION, tenant=TENANT_A, user=USER_B)
        insert_fails(conn, FOREIGN_KEY_VIOLATION, tenant=uuid.uuid4(), user=USER_A)


# --- RLS y privilegios (R15, A10, A11) --------------------------------------------


def test_rls_is_enabled_and_forced_with_only_tenant_isolation(db):
    with rolled_back(db.migrator) as conn:
        flags = conn.execute(
            text(
                "select relrowsecurity, relforcerowsecurity from pg_class "
                "where oid = to_regclass(:t)"
            ),
            {"t": f"public.{TABLE}"},
        ).one()
        policies = conn.execute(
            text(
                "select policyname, permissive, cmd, roles::text, qual, with_check "
                "from pg_policies where schemaname = 'public' and tablename = :t"
            ),
            {"t": TABLE},
        ).all()
    assert tuple(flags) == (True, True)
    # Spec 014, T2 (0016): el resto son las políticas del dueño, por comando y nunca
    # FOR ALL; su texto exacto lo fija el catálogo (test_catalog_rls.py).
    app_policies = [tuple(p) for p in policies if p[3] != "{" + AUTH_OWNER + "}"]
    assert app_policies == [
        (
            "tenant_isolation",
            "PERMISSIVE",
            "ALL",
            "{" + db.app_role + "}",
            ISOLATION_EXPR,
            ISOLATION_EXPR,
        )
    ]
    assert {p[2] for p in policies if p[3] == "{" + AUTH_OWNER + "}"} == {
        "SELECT",
        "INSERT",
        "UPDATE",
    }


def test_nobody_but_the_owner_has_table_privileges_and_the_app_has_none(db):
    # Spec 014, T2 (0016): auth_owner recibe solo GRANT por columna (su lista exacta está
    # en test_catalog_rls.py); a nivel de tabla nadie más que el dueño, y la aplicación
    # nada, ni por columna.
    with rolled_back(db.migrator) as conn:
        acl = conn.execute(
            text(
                "select case when a.grantee = 0 then 'PUBLIC' else a.grantee::regrole::text end, "
                "a.privilege_type from pg_class c "
                "cross join lateral aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) a "
                "where c.oid = to_regclass(:t) and a.grantee <> c.relowner"
            ),
            {"t": f"public.{TABLE}"},
        ).all()
        column_grantees = set(
            conn.scalars(
                text(
                    "select distinct a.grantee::regrole::text from pg_attribute t "
                    "cross join lateral aclexplode(t.attacl) a "
                    "where t.attrelid = to_regclass(:t) and t.attacl is not null"
                ),
                {"t": f"public.{TABLE}"},
            )
        )
        privileges = set()
        for role in (db.app_role, AUTH_OWNER):
            for privilege in TABLE_PRIVILEGES:
                params = {"r": role, "t": f"public.{TABLE}", "p": privilege}
                if conn.scalar(text("select has_table_privilege(:r, :t, :p)"), params):
                    privileges.add((role, privilege))
            for privilege in COLUMN_PRIVILEGES:
                params = {"r": role, "t": f"public.{TABLE}", "p": privilege}
                if conn.scalar(text("select has_any_column_privilege(:r, :t, :p)"), params):
                    privileges.add((role, f"{privilege} (columna)"))
    assert acl == []
    assert column_grantees == {AUTH_OWNER}
    assert privileges == {
        (AUTH_OWNER, "SELECT (columna)"),
        (AUTH_OWNER, "INSERT (columna)"),
        (AUTH_OWNER, "UPDATE (columna)"),
    }


@pytest.mark.parametrize(
    "statement",
    [
        f"select count(*) from {TABLE}",  # noqa: S608
        f"select id from {TABLE} where tenant_id = :a",  # noqa: S608
        f"insert into {TABLE} (tenant_id, usuario_id, token_hash, expira_en) "  # noqa: S608
        "values (:a, :u, :h, now() + interval '5 minutes')",
        f"update {TABLE} set invalidada_en = now() where tenant_id = :a",  # noqa: S608
        f"delete from {TABLE} where tenant_id = :a",  # noqa: S608
    ],
)
@pytest.mark.parametrize("tenant", [None, TENANT_A, TENANT_B])
def test_the_app_is_denied_every_command_even_with_a_tenant(db, statement, tenant):
    params = {"a": TENANT_A, "u": USER_A, "h": token_hash()}
    with rolled_back(db.app) as conn:
        if tenant is not None:
            conn.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
        message = fails(conn, INSUFFICIENT_PRIVILEGE, statement, params)
    assert "permission denied" in message


def test_auth_owner_without_its_gucs_sees_nothing_and_cannot_delete(db):
    # Spec 014, T2 (0016): auth_owner tiene sus políticas por comando, pero sin las GUC
    # de las funciones acceso.* no ve ninguna fila; DELETE nunca.
    with rolled_back(db.migrator) as conn:
        insert(conn)
        conn.exec_driver_sql(f'SET LOCAL ROLE "{AUTH_OWNER}"')
        assert conn.scalar(text(f"select count(usuario_id) from {TABLE}")) == 0  # noqa: S608
        fails(conn, INSUFFICIENT_PRIVILEGE, f"delete from {TABLE}")  # noqa: S608


def test_tenant_isolation_still_isolates_if_a_grant_slipped_in(db):
    # Defensa en profundidad: con un GRANT accidental (dentro de una transacción que se
    # revierte) la política sigue acotando al tenant fijado y, sin tenant, a nada.
    quoted = '"' + db.app_role.replace('"', '""') + '"'
    with rolled_back(db.migrator) as conn:
        own = insert(conn, TENANT_A, USER_A)
        other = insert(conn, TENANT_B, USER_B)
        conn.exec_driver_sql(f"GRANT SELECT, INSERT, UPDATE ON {TABLE} TO {quoted}")
        conn.exec_driver_sql(f"SET LOCAL ROLE {quoted}")

        count = text(f"select count(*) from {TABLE}")  # noqa: S608
        assert conn.scalar(count) == 0  # sin tenant fijado: cero filas
        conn.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(TENANT_A)})
        ids = set(conn.scalars(text(f"select id from {TABLE}")))  # noqa: S608
        assert ids == {own}
        touched = conn.execute(
            text(f"update {TABLE} set invalidada_en = now() where id = :id"),  # noqa: S608
            {"id": other},
        )
        assert touched.rowcount == 0
        message = insert_fails(conn, INSUFFICIENT_PRIVILEGE, tenant=TENANT_B, user=USER_B)
        assert "row-level security" in message


# --- limite_tasa: ámbitos nuevos (plan.md §3.2) -----------------------------------


@pytest.mark.parametrize("scope", NEW_SCOPES + OLD_SCOPES)
def test_limite_tasa_accepts_the_known_scopes(db, scope):
    with rolled_back(db.app) as conn:
        counted = conn.execute(
            text(
                "insert into limite_tasa (ambito, clave_hash, ventana_inicio, intentos) "
                "values (:a, :h, now(), 1) returning intentos"
            ),
            {"a": scope, "h": token_hash()},
        ).scalar_one()
    assert counted == 1


@pytest.mark.parametrize("scope", ["recuperar", "restablecer_cuenta", "RECUPERAR_IP", ""])
def test_limite_tasa_rejects_an_unknown_scope(db, scope):
    with rolled_back(db.app) as conn:
        fails(
            conn,
            CHECK_VIOLATION,
            "insert into limite_tasa (ambito, clave_hash, ventana_inicio, intentos) "
            "values (:a, :h, now(), 1)",
            {"a": scope, "h": token_hash()},
        )


def test_limite_tasa_scope_check_is_a_single_named_constraint(db):
    with rolled_back(db.migrator) as conn:
        checks = conn.execute(
            text(
                "select conname, pg_get_constraintdef(oid) from pg_constraint "
                "where conrelid = 'public.limite_tasa'::regclass and contype = 'c' "
                "and pg_get_constraintdef(oid) like '%ambito%'"
            )
        ).all()
    scopes = ", ".join(f"'{s}'::text" for s in OLD_SCOPES + NEW_SCOPES)
    assert [tuple(c) for c in checks] == [
        ("limite_tasa_ambito_check", f"CHECK ((ambito = ANY (ARRAY[{scopes}])))")
    ]
