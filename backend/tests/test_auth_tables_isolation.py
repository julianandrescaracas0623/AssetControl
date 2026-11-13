"""Pruebas de aislamiento de las tablas de acceso (spec 002, T2; plan.md §7.2, A26).

Comportamiento real, no catálogo: sobre una base temporal migrada a ``head`` con
dos tenants sintéticos (A y B) se ejecuta SQL con

- el **rol de la aplicación** (``TEST_DATABASE_URL``), por ORM con
  ``tenant_session``, por ``get_bind()`` y por SQL crudo con ``app.tenant_id``;
- **``auth_owner`` real**: cada transacción del migrador hace ``SET LOCAL ROLE
  auth_owner``. ``current_user`` pasa a ser ``auth_owner`` (sin ``SUPERUSER``
  ni ``BYPASSRLS``), así que RLS se evalúa para ``auth_owner`` y no para el
  superusuario. No se crea ningún rol de pruebas ni se concede membresía en
  ``auth_owner`` (I1 de la revisión de seguridad de T2).

Cubre las pruebas 1–7 de plan.md §7.2, la 8 en su parte sin funciones
(``SET ROLE auth_owner`` falla para la aplicación) y, de la 9, solo el nivel
SQL: las GUC ``app.auth_*`` fijadas con ``set_config(..., true)`` no sobreviven
a ``COMMIT``/``ROLLBACK``/``ROLLBACK TO SAVEPOINT`` y con GUC vacía las
políticas devuelven cero filas. La prueba 9 completa y la 10 son de T3.

Los datos se siembran con el rol migrador, que en local y en la CI es
superusuario (se salta RLS); si no lo es, el módulo queda bloqueado. Datos
sintéticos: nunca datos de la clínica.
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
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import URL, Connection, Engine
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.pool import NullPool, QueuePool

from app import create_app
from app.auth.models import Invitacion, Membresia, RefreshToken, Tenant, Usuario
from app.config import Config
from app.db import _EXTENSION_KEY, tenant_session

BACKEND_DIR = Path(__file__).resolve().parent.parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
AUTH_OWNER = "auth_owner"

INSUFFICIENT_PRIVILEGE = "42501"
FOREIGN_KEY_VIOLATION = "23503"
RLS_VIOLATION = "row-level security"
PERMISSION_DENIED = "permission denied"

TABLES = ("tenant", "usuario", "membresia", "invitacion", "refresh_token")
TENANT_TABLES = ("membresia", "invitacion", "refresh_token")

TENANT_A = uuid.UUID("00000000-0000-4000-8000-00000000a002")
TENANT_B = uuid.UUID("00000000-0000-4000-8000-00000000b002")
USER_A = uuid.UUID("00000000-0000-4000-8000-0000000a0001")
USER_B = uuid.UUID("00000000-0000-4000-8000-0000000b0001")
MEM_A = uuid.UUID("00000000-0000-4000-8000-0000000a0002")
MEM_B = uuid.UUID("00000000-0000-4000-8000-0000000b0002")
REFRESH_A = uuid.UUID("00000000-0000-4000-8000-0000000a0003")
REFRESH_B = uuid.UUID("00000000-0000-4000-8000-0000000b0003")
EMAIL_A = "admin.a@ejemplo.test"
EMAIL_B = "admin.b@ejemplo.test"
EMAIL_NUEVA_A = "nueva.a@ejemplo.test"


def clave(token: str) -> str:
    """Lo que envía la aplicación: ``sha256(token)`` en hex minúsculo (I1)."""
    return hashlib.sha256(token.encode()).hexdigest()


def stored_hash(clave_hex: str) -> bytes:
    """Lo que guarda la base: ``sha256(clave)`` en bytes (doble hash, I1)."""
    return hashlib.sha256(bytes.fromhex(clave_hex)).digest()


CLAVE_A = clave("token-sintetico-invitacion-a")
CLAVE_B = clave("token-sintetico-invitacion-b")
CLAVE_USADA = clave("token-sintetico-invitacion-usada")
CLAVE_VENCIDA = clave("token-sintetico-invitacion-vencida")
CLAVE_REFRESH_A = clave("token-sintetico-refresh-a")
CLAVE_REFRESH_B = clave("token-sintetico-refresh-b")

# Invitaciones sembradas: clave -> (tenant, email, rol, creada_por, expira, usada).
INVITACIONES = {
    CLAVE_A: (TENANT_A, EMAIL_NUEVA_A, "contador", USER_A, "now() + interval '3 days'", "NULL"),
    CLAVE_B: (
        TENANT_B,
        "nueva.b@ejemplo.test",
        "contador",
        USER_B,
        "now() + interval '3 days'",
        "NULL",
    ),
    CLAVE_USADA: (
        TENANT_A,
        "usada.a@ejemplo.test",
        "contador",
        USER_A,
        "now() + interval '3 days'",
        "now() - interval '1 hour'",
    ),
    CLAVE_VENCIDA: (
        TENANT_A,
        "vencida.a@ejemplo.test",
        "contador",
        USER_A,
        "now() - interval '1 hour'",
        "NULL",
    ),
}

OWNER_GUCS = (
    "app.auth_email",
    "app.auth_usuario",
    "app.auth_inv_validar",
    "app.auth_inv_aceptar",
    "app.auth_usuario_nuevo",
    "app.auth_tenant_nuevo",
)


@dataclass(frozen=True)
class AccesoDb:
    app_url: URL
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
    """Dos tenants sintéticos con un admin, invitaciones y un refresh cada uno."""
    for tenant, user, mem, email, refresh, refresh_clave in (
        (TENANT_A, USER_A, MEM_A, EMAIL_A, REFRESH_A, CLAVE_REFRESH_A),
        (TENANT_B, USER_B, MEM_B, EMAIL_B, REFRESH_B, CLAVE_REFRESH_B),
    ):
        conn.execute(
            text("insert into tenant (id, nombre) values (:id, :n)"),
            {"id": tenant, "n": f"Clínica sintética {str(tenant)[-4:]}"},
        )
        conn.execute(
            text(
                "insert into usuario (id, email, nombre, password_hash) "
                "values (:id, :e, 'Admin sintético', 'hash-sintetico-no-valido')"
            ),
            {"id": user, "e": email},
        )
        conn.execute(
            text(
                "insert into membresia (id, tenant_id, usuario_id, rol) "
                "values (:id, :t, :u, 'admin')"
            ),
            {"id": mem, "t": tenant, "u": user},
        )
        conn.execute(
            text(
                "insert into refresh_token (id, tenant_id, membresia_id, familia_id, "
                "token_hash, expira_en) values (:id, :t, :m, :f, :h, now() + interval '7 days')"
            ),
            {
                "id": refresh,
                "t": tenant,
                "m": mem,
                "f": uuid.uuid4(),
                "h": stored_hash(refresh_clave),
            },
        )
    for key, (tenant, email, rol, creador, expira, usada) in INVITACIONES.items():
        conn.execute(
            text(
                "insert into invitacion (tenant_id, email, rol, token_hash, creada_por, "  # noqa: S608
                f"expira_en, usada_en) values (:t, :e, :r, :h, :c, {expira}, {usada})"
            ),
            {"t": tenant, "e": email, "r": rol, "h": stored_hash(key), "c": creador},
        )


@pytest.fixture(scope="module")
def acceso(database_residue_guard) -> Iterator[AccesoDb]:
    """Base temporal en ``head`` con datos sintéticos."""
    migrator_url = read_database_url("TEST_MIGRATION_DATABASE_URL")
    app_url = read_database_url("TEST_DATABASE_URL")
    if migrator_url is None or app_url is None or not app_url.username:
        _fail(BLOCKED)
    name = f"assetcontrol_aislamiento_{uuid.uuid4().hex[:12]}"

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
        app_db = app_url.set(database=name)
        app = create_engine(app_db, poolclass=NullPool)
        engines += [migrator, app]
        with migrator.begin() as conn:
            _seed(conn)
        yield AccesoDb(
            app_url=app_db,
            app_role=app_url.username,
            migrator=migrator,
            app=app,
        )
    finally:
        for engine in engines:
            engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


# --- Utilidades -----------------------------------------------------------------


def _set_tenant(conn: Connection, tenant: object) -> None:
    conn.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})


@contextmanager
def app_tx(db: AccesoDb, tenant: object | None = None) -> Iterator[Connection]:
    """Transacción del rol de la aplicación, con ``app.tenant_id`` opcional; se revierte."""
    with db.app.connect() as conn:
        tx = conn.begin()
        try:
            if tenant is not None:
                _set_tenant(conn, tenant)
            yield conn
        finally:
            tx.rollback()


def _set_owner(conn: Connection, gucs: dict[str, str]) -> None:
    conn.exec_driver_sql(f"SET LOCAL ROLE {AUTH_OWNER}")
    for name, value in gucs.items():
        conn.execute(text("select set_config(:n, :v, true)"), {"n": name, "v": value})


@contextmanager
def owner_tx(db: AccesoDb, **gucs: str) -> Iterator[Connection]:
    """Transacción del migrador como ``auth_owner`` real (``SET LOCAL ROLE``); se revierte.

    Las GUC van como ``app_auth_email=...`` -> ``app.auth_email``.
    """
    with db.migrator.connect() as conn:
        tx = conn.begin()
        try:
            _set_owner(conn, {name.replace("app_", "app.", 1): v for name, v in gucs.items()})
            yield conn
        finally:
            tx.rollback()


def _sqlstate(exc: DBAPIError) -> str | None:
    return getattr(exc.orig, "sqlstate", None)


def assert_fails(conn: Connection, sql: str, params=None, *, code: str, fragment: str) -> None:
    """Falla con ``code`` y ``fragment``; revierte solo su savepoint."""
    nested = conn.begin_nested()
    with pytest.raises(DBAPIError) as excinfo:
        conn.execute(text(sql), params or {})
    nested.rollback()
    assert _sqlstate(excinfo.value) == code, str(excinfo.value.orig)
    assert fragment in str(excinfo.value.orig), str(excinfo.value.orig)


def assert_denied(conn: Connection, sql: str, params=None) -> None:
    assert_fails(conn, sql, params, code=INSUFFICIENT_PRIVILEGE, fragment=PERMISSION_DENIED)


def assert_rls_rejects(conn: Connection, sql: str, params=None) -> None:
    assert_fails(conn, sql, params, code=INSUFFICIENT_PRIVILEGE, fragment=RLS_VIOLATION)


def _count(conn: Connection, table: str, where: str = "true", params=None) -> int:
    # ``count(id)``: la aplicación solo tiene SELECT por columna en usuario e invitacion.
    return conn.scalar(text(f"select count(id) from {table} where {where}"), params or {})  # noqa: S608


def _new_invitacion(tenant: uuid.UUID, creada_por: uuid.UUID | None) -> dict[str, object]:
    return {
        "id": uuid.uuid4(),
        "t": tenant,
        "e": f"x{uuid.uuid4().hex[:8]}@ejemplo.test",
        "h": stored_hash(clave(uuid.uuid4().hex)),
        "c": creada_por,
    }


INSERT_INVITACION = (
    "insert into invitacion (id, tenant_id, email, rol, token_hash, expira_en, creada_por) "
    "values (:id, :t, :e, 'contador', :h, now() + interval '3 days', :c)"
)
INSERT_REFRESH = (
    "insert into refresh_token (id, tenant_id, membresia_id, familia_id, token_hash, expira_en) "
    "values (:id, :t, :m, :f, :h, now() + interval '7 days')"
)


def _new_refresh(tenant: uuid.UUID, membresia: uuid.UUID) -> dict[str, object]:
    return {
        "id": uuid.uuid4(),
        "t": tenant,
        "m": membresia,
        "f": uuid.uuid4(),
        "h": stored_hash(clave(uuid.uuid4().hex)),
    }


# --- 1. Sin tenant fijado (conexión nueva y reutilizada) -------------------------


@pytest.mark.parametrize("tenant", [None, ""])
@pytest.mark.parametrize("table", TABLES)
def test_app_without_tenant_reads_nothing_on_a_new_connection(acceso, table, tenant):
    with app_tx(acceso, tenant) as conn:
        assert _count(conn, table) == 0


def test_app_without_tenant_reads_nothing_on_a_reused_connection(acceso):
    engine = create_engine(acceso.app_url, poolclass=QueuePool, pool_size=1, max_overflow=0)
    try:
        for end in ("commit", "rollback"):
            with engine.connect() as conn:
                tx = conn.begin()
                pid = conn.scalar(text("select pg_backend_pid()"))
                _set_tenant(conn, TENANT_A)
                assert all(_count(conn, table) > 0 for table in TABLES)
                getattr(tx, end)()
            with engine.connect() as conn:
                with conn.begin():
                    # Misma conexión física del pool, sin tenant: cero filas.
                    assert conn.scalar(text("select pg_backend_pid()")) == pid
                    assert conn.scalar(text("select current_setting('app.tenant_id', true)")) in (
                        "",
                        None,
                    )
                    for table in TABLES:
                        assert _count(conn, table) == 0, (end, table)
    finally:
        engine.dispose()


@pytest.mark.parametrize("tenant", [None, ""])
def test_app_without_tenant_cannot_insert(acceso, tenant):
    with app_tx(acceso, tenant) as conn:
        # Con GRANT de INSERT: lo frena la política (WITH CHECK con tenant nulo).
        assert_rls_rejects(conn, INSERT_INVITACION, _new_invitacion(TENANT_A, USER_A))
        assert_rls_rejects(conn, INSERT_REFRESH, _new_refresh(TENANT_A, MEM_A))
        # Sin GRANT de INSERT.
        assert_denied(conn, "insert into tenant (id, nombre) values (gen_random_uuid(), 'x')")
        assert_denied(
            conn,
            "insert into usuario (email, nombre, password_hash) "
            "values ('y@ejemplo.test', 'y', 'h')",
        )
        assert_denied(
            conn,
            "insert into membresia (tenant_id, usuario_id, rol) values (:t, :u, 'admin')",
            {"t": TENANT_A, "u": USER_A},
        )


@pytest.mark.parametrize("tenant", [None, ""])
def test_app_without_tenant_updates_nothing(acceso, tenant):
    with app_tx(acceso, tenant) as conn:
        result = conn.execute(text("update refresh_token set revocado_en = now()"))
        assert result.rowcount == 0
        assert_denied(conn, "update invitacion set usada_en = now()")
        assert_denied(conn, "update membresia set activa = false")
        assert_denied(conn, "update tenant set nombre = 'x'")
        assert_denied(conn, "update usuario set nombre = 'x'")


# --- 2. Con tenant A: cero filas de B (ORM, get_bind, SQL crudo, join) ------------


@pytest.fixture
def acceso_app(acceso):
    app = create_app(
        Config(database_url=acceso.app_url, secret_key="clave-de-prueba", environment="test")
    )
    try:
        with app.app_context():
            yield app
    finally:
        app.extensions[_EXTENSION_KEY].engine.dispose()


def test_orm_with_tenant_a_sees_only_tenant_a(acceso_app):
    with tenant_session(TENANT_A) as session:
        assert set(session.scalars(select(Tenant.id))) == {TENANT_A}
        assert set(session.scalars(select(Usuario.id))) == {USER_A}
        for model in (Membresia, Invitacion, RefreshToken):
            assert set(session.scalars(select(model.tenant_id))) == {TENANT_A}, model
            explicit = select(func.count()).select_from(model).where(model.tenant_id == TENANT_B)
            assert session.scalar(explicit) == 0, model
        assert session.get(Tenant, TENANT_B) is None
        assert session.get(Usuario, USER_B) is None
        assert session.get(Membresia, MEM_B) is None
        assert session.get(RefreshToken, REFRESH_B) is None


def test_orm_join_with_tenant_a_sees_only_tenant_a(acceso_app):
    with tenant_session(TENANT_A) as session:
        rows = session.execute(
            select(RefreshToken.id, Membresia.tenant_id, Usuario.email, Tenant.id)
            .join(Membresia, RefreshToken.membresia_id == Membresia.id)
            .join(Usuario, Membresia.usuario_id == Usuario.id)
            .join(Tenant, Membresia.tenant_id == Tenant.id)
        ).all()
    assert rows == [(REFRESH_A, TENANT_A, EMAIL_A, TENANT_A)]


def test_pool_connection_reused_after_tenant_session_has_no_tenant(acceso_app):
    with tenant_session(TENANT_A) as session:
        pid = session.scalar(select(func.pg_backend_pid()))
        assert session.scalar(select(func.count()).select_from(Membresia)) == 1
    engine = acceso_app.extensions[_EXTENSION_KEY].engine
    with engine.connect() as conn:
        # La misma conexión física que usó tenant_session vuelve al pool sin tenant.
        assert conn.scalar(text("select pg_backend_pid()")) == pid
        assert _guc(conn, "app.tenant_id") in ("", None)
        for table in TABLES:
            assert _count(conn, table) == 0, table


def test_get_bind_inside_tenant_session_has_no_tenant(acceso_app):
    with tenant_session(TENANT_A) as session:
        # get_bind() devuelve el engine: otra conexión, sin app.tenant_id; RLS da cero.
        with session.get_bind().connect() as conn:
            for table in TABLES:
                assert _count(conn, table) == 0, table


@pytest.mark.parametrize("table", TENANT_TABLES)
def test_raw_sql_with_tenant_a_sees_no_row_of_b(acceso, table):
    with app_tx(acceso, TENANT_A) as conn:
        tenants = set(conn.scalars(text(f"select tenant_id from {table}")))  # noqa: S608
        assert tenants == {TENANT_A}
        assert _count(conn, table, "tenant_id = :b", {"b": TENANT_B}) == 0


def test_raw_sql_tenant_and_usuario_with_tenant_a(acceso):
    with app_tx(acceso, TENANT_A) as conn:
        assert set(conn.scalars(text("select id from tenant"))) == {TENANT_A}
        assert set(conn.scalars(text("select id from usuario"))) == {USER_A}
        assert _count(conn, "usuario", "email = :e", {"e": EMAIL_B}) == 0


def test_raw_sql_join_with_tenant_a_sees_no_row_of_b(acceso):
    with app_tx(acceso, TENANT_A) as conn:
        rows = conn.execute(
            text(
                "select r.id, m.tenant_id, u.email, t.id, i.tenant_id from refresh_token r "
                "join membresia m on m.tenant_id = r.tenant_id and m.id = r.membresia_id "
                "join usuario u on u.id = m.usuario_id "
                "join tenant t on t.id = m.tenant_id "
                "left join invitacion i on i.tenant_id = m.tenant_id "
                "and i.creada_por = m.usuario_id"
            )
        ).all()
        assert {row[0] for row in rows} == {REFRESH_A}
        assert {(row[1], row[2], row[3]) for row in rows} == {(TENANT_A, EMAIL_A, TENANT_A)}
        assert {row[4] for row in rows} == {TENANT_A}


@pytest.mark.parametrize("table", TABLES)
def test_app_cannot_delete_or_truncate(acceso, table):
    with app_tx(acceso, TENANT_A) as conn:
        assert_denied(conn, f"delete from {table}")  # noqa: S608
        assert_denied(conn, f"truncate {table}")


# --- 3. WITH CHECK, UPDATE de tenant_id y FK compuestas ----------------------------


def test_insert_with_own_tenant_succeeds(acceso):
    # Control positivo: las pruebas negativas fallan por la razón que dicen.
    with app_tx(acceso, TENANT_A) as conn:
        conn.execute(text(INSERT_INVITACION), _new_invitacion(TENANT_A, USER_A))
        conn.execute(text(INSERT_REFRESH), _new_refresh(TENANT_A, MEM_A))


def test_insert_with_a_foreign_tenant_fails(acceso):
    with app_tx(acceso, TENANT_A) as conn:
        assert_rls_rejects(conn, INSERT_INVITACION, _new_invitacion(TENANT_B, USER_B))
        assert_rls_rejects(conn, INSERT_REFRESH, _new_refresh(TENANT_B, MEM_B))


@pytest.mark.parametrize("table", TABLES)
def test_update_set_tenant_id_fails(acceso, table):
    column = "tenant_id" if table in TENANT_TABLES else "id"
    with app_tx(acceso, TENANT_A) as conn:
        assert_denied(conn, f"update {table} set {column} = :b", {"b": TENANT_B})  # noqa: S608


def test_update_cannot_reach_rows_of_b(acceso):
    with app_tx(acceso, TENANT_A) as conn:
        result = conn.execute(
            text("update refresh_token set revocado_en = now() where id = :id"), {"id": REFRESH_B}
        )
        assert result.rowcount == 0
        result = conn.execute(
            text("update refresh_token set revocado_en = now() where id = :id"), {"id": REFRESH_A}
        )
        assert result.rowcount == 1


def test_composite_fk_rejects_creada_por_of_another_tenant(acceso):
    with app_tx(acceso, TENANT_A) as conn:
        assert_fails(
            conn,
            INSERT_INVITACION,
            _new_invitacion(TENANT_A, USER_B),
            code=FOREIGN_KEY_VIOLATION,
            fragment="invitacion_creada_por_fkey",
        )


def test_composite_fk_rejects_membresia_of_another_tenant(acceso):
    with app_tx(acceso, TENANT_A) as conn:
        assert_fails(
            conn,
            INSERT_REFRESH,
            _new_refresh(TENANT_A, MEM_B),
            code=FOREIGN_KEY_VIOLATION,
            fragment="refresh_token_membresia_fkey",
        )


# --- 6 (aplicación). RESTRICTIVE creada_por IS NOT NULL ----------------------------


def test_app_cannot_insert_invitacion_without_creada_por(acceso):
    with app_tx(acceso, TENANT_A) as conn:
        assert_rls_rejects(conn, INSERT_INVITACION, _new_invitacion(TENANT_A, None))


def test_restrictive_policy_wins_over_an_extra_permissive_policy(acceso):
    # Política permisiva de prueba, solo dentro de esta transacción del migrador, que
    # luego actúa como el rol de la aplicación con SET LOCAL ROLE.
    quote = acceso.migrator.dialect.identifier_preparer.quote
    with acceso.migrator.connect() as conn:
        tx = conn.begin()
        try:
            conn.exec_driver_sql(
                "CREATE POLICY prueba_permisiva ON invitacion AS PERMISSIVE FOR INSERT "
                f"TO {quote(acceso.app_role)} WITH CHECK (true)"
            )
            conn.exec_driver_sql(f"SET LOCAL ROLE {quote(acceso.app_role)}")
            assert conn.scalar(text("select current_user")) == acceso.app_role
            _set_tenant(conn, TENANT_A)
            # La permisiva se suma por OR: deja pasar hasta un tenant ajeno...
            conn.execute(text(INSERT_INVITACION), _new_invitacion(TENANT_B, USER_B))
            # ...pero la RESTRICTIVE va con AND: creada_por NULL sigue rechazado.
            assert_rls_rejects(conn, INSERT_INVITACION, _new_invitacion(TENANT_A, None))
            assert_rls_rejects(conn, INSERT_INVITACION, _new_invitacion(TENANT_B, None))
        finally:
            tx.rollback()


# --- 7. Columnas de hash ----------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "select password_hash from usuario",
        "select * from usuario",
        "select token_hash from invitacion",
        "select * from invitacion",
        "select count(*) from invitacion where token_hash is not null",
    ],
)
def test_app_cannot_read_password_or_invitation_hashes(acceso, sql):
    with app_tx(acceso, TENANT_A) as conn:
        assert_denied(conn, sql)


def test_app_reads_refresh_token_hash_only_of_its_tenant(acceso):
    with app_tx(acceso, TENANT_A) as conn:
        hashes = set(conn.scalars(text("select token_hash from refresh_token")))
        assert hashes == {stored_hash(CLAVE_REFRESH_A)}
        hit = conn.scalar(
            text("select count(*) from refresh_token where token_hash = :h"),
            {"h": stored_hash(CLAVE_REFRESH_B)},
        )
        assert hit == 0


def test_stored_refresh_hash_is_not_the_client_secret(acceso):
    # Doble hash (I1): lo que la aplicación puede leer no es la clave que envía el cliente.
    with app_tx(acceso, TENANT_A) as conn:
        stored = conn.scalar(text("select token_hash from refresh_token"))
    assert stored != bytes.fromhex(CLAVE_REFRESH_A)
    assert stored == hashlib.sha256(bytes.fromhex(CLAVE_REFRESH_A)).digest()


# --- 8 (sin funciones). La aplicación no asume auth_owner --------------------------


def test_app_cannot_set_role_auth_owner(acceso):
    with app_tx(acceso) as conn:
        assert_fails(
            conn,
            f"SET ROLE {AUTH_OWNER}",
            code=INSUFFICIENT_PRIVILEGE,
            fragment="permission denied to set role",
        )


# --- auth_owner real: sesión de prueba --------------------------------------------


def test_owner_session_is_auth_owner_without_super_or_bypassrls(acceso):
    with owner_tx(acceso) as conn:
        row = conn.execute(
            text(
                "select current_user, r.rolsuper, r.rolbypassrls "
                "from pg_roles r where r.rolname = current_user"
            )
        ).one()
    assert row == (AUTH_OWNER, False, False)
    assert acceso.app_role != AUTH_OWNER


def test_owner_session_needs_no_member_of_auth_owner(acceso):
    # I1: ni rol de pruebas con LOGIN ni membresía en auth_owner.
    with acceso.migrator.connect() as conn:
        members = conn.scalar(
            text(
                "select count(*) from pg_auth_members a join pg_roles g on g.oid = a.roleid "
                "where g.rolname = :o"
            ),
            {"o": AUTH_OWNER},
        )
    assert members == 0


# --- 6 (dueño). Lectura: nada sin su GUC, ni comodines ----------------------------


def test_owner_cannot_read_refresh_token_or_other_tenant_columns(acceso):
    with owner_tx(acceso, app_auth_tenant_nuevo=str(TENANT_A)) as conn:
        assert_denied(conn, "select nombre from tenant")
        assert_denied(conn, "select * from tenant")
        assert_denied(conn, "select id from refresh_token")


@pytest.mark.parametrize("guc", [None, "", "%", "_"])
def test_owner_reads_no_tenant_without_its_guc(acceso, guc):
    gucs = {} if guc is None else {"app_auth_tenant_nuevo": guc}
    with owner_tx(acceso, **gucs) as conn:
        assert conn.scalar(text("select count(id) from tenant")) == 0


@pytest.mark.parametrize("tenant", [TENANT_A, TENANT_B], ids=["A", "B"])
def test_owner_cannot_read_a_tenant_created_in_another_transaction(acceso, tenant):
    # I2: el tenant se sembró en otra transacción; su id en la GUC no lo abre.
    with owner_tx(acceso, app_auth_tenant_nuevo=str(tenant)) as conn:
        assert conn.scalar(text("select count(id) from tenant")) == 0
        hit = conn.scalar(text("select count(id) from tenant where id = :t"), {"t": tenant})
        assert hit == 0


OWNER_READS = {
    "app.auth_inv_validar": ("invitacion", "select count(email) from invitacion", CLAVE_A),
    "app.auth_inv_aceptar": ("invitacion", "select count(email) from invitacion", CLAVE_A),
    "app.auth_email": ("usuario", "select count(email) from usuario", EMAIL_A),
    "app.auth_usuario": ("membresia", "select count(id) from membresia", str(USER_A)),
}


@pytest.mark.parametrize("guc", sorted(OWNER_READS))
def test_owner_reads_exactly_one_row_with_its_guc(acceso, guc):
    _, sql, value = OWNER_READS[guc]
    with acceso.migrator.connect() as conn:
        with conn.begin():
            _set_owner(conn, {guc: value})
            assert conn.scalar(text(sql)) == 1


@pytest.mark.parametrize("value", [None, "", "%", "_", " ", "*", "null"])
@pytest.mark.parametrize("guc", sorted(OWNER_READS))
def test_owner_reads_nothing_with_empty_null_or_wildcard_guc(acceso, guc, value):
    _, sql, _ = OWNER_READS[guc]
    with acceso.migrator.connect() as conn:
        with conn.begin():
            _set_owner(conn, {} if value is None else {guc: value})
            assert conn.scalar(text(sql)) == 0


@pytest.mark.parametrize("guc", sorted(OWNER_READS))
def test_owner_guc_of_one_table_does_not_open_another(acceso, guc):
    table, _, value = OWNER_READS[guc]
    with acceso.migrator.connect() as conn:
        with conn.begin():
            _set_owner(conn, {guc: value})
            for other, other_sql, _ in OWNER_READS.values():
                if other != table:
                    assert conn.scalar(text(other_sql)) == 0, (guc, other)
            assert conn.scalar(text("select count(id) from tenant")) == 0, guc


def test_owner_empty_email_guc_does_not_match_an_empty_email(acceso):
    # El CHECK de usuario admite email ''; con GUC vacía no debe coincidir con esa cuenta.
    with acceso.migrator.connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(text(INSERT_USUARIO), {"id": uuid.uuid4(), "e": ""})
            _set_owner(conn, {"app.auth_email": ""})
            assert conn.scalar(text("select current_user")) == AUTH_OWNER
            assert conn.scalar(text("select count(email) from usuario")) == 0
        finally:
            tx.rollback()


def test_owner_reads_with_the_hash_of_the_key_not_the_stored_hash(acceso):
    # La GUC lleva la clave; pasar el hash guardado (doble) no encuentra la fila.
    with owner_tx(acceso, app_auth_inv_validar=stored_hash(CLAVE_A).hex()) as conn:
        assert conn.scalar(text("select count(email) from invitacion")) == 0


# --- Dueño: consumir invitación (UPDATE) -------------------------------------------

CONSUME = "update invitacion set usada_en = now() where token_hash = :h"


@pytest.mark.parametrize(
    ("key", "expected"),
    [(CLAVE_A, 1), (CLAVE_USADA, 0), (CLAVE_VENCIDA, 0)],
    ids=["vigente", "usada", "vencida"],
)
def test_owner_consumes_only_a_valid_unused_invitation(acceso, key, expected):
    with owner_tx(acceso, app_auth_inv_aceptar=key) as conn:
        assert conn.execute(text(CONSUME), {"h": stored_hash(key)}).rowcount == expected


def test_owner_cannot_consume_without_or_with_another_guc(acceso):
    with owner_tx(acceso) as conn:
        assert conn.execute(text(CONSUME), {"h": stored_hash(CLAVE_A)}).rowcount == 0
    with owner_tx(acceso, app_auth_inv_validar=CLAVE_A) as conn:
        assert conn.execute(text(CONSUME), {"h": stored_hash(CLAVE_A)}).rowcount == 0
    with owner_tx(acceso, app_auth_inv_aceptar=CLAVE_B) as conn:
        # La GUC acota a la invitación de esa clave: no consume otra.
        assert conn.execute(text(CONSUME), {"h": stored_hash(CLAVE_A)}).rowcount == 0


@pytest.mark.parametrize("value", ["NULL", "now() - interval '1 hour'"])
def test_owner_update_must_mark_the_invitation_as_used_now(acceso, value):
    with owner_tx(acceso, app_auth_inv_aceptar=CLAVE_A) as conn:
        assert_rls_rejects(
            conn,
            f"update invitacion set usada_en = {value} where token_hash = :h",  # noqa: S608
            {"h": stored_hash(CLAVE_A)},
        )


@pytest.mark.parametrize("column", ["rol", "email", "tenant_id", "expira_en", "creada_por"])
def test_owner_cannot_update_other_invitation_columns(acceso, column):
    with owner_tx(acceso, app_auth_inv_aceptar=CLAVE_A) as conn:
        assert_denied(conn, f"update invitacion set {column} = {column}")  # noqa: S608


# --- 5. Dueño: INSERT usuario ligado a la invitación recién consumida ----------------

INSERT_USUARIO = (
    "insert into usuario (id, email, nombre, password_hash) "
    "values (:id, :e, 'Nuevo sintético', 'hash-sintetico-no-valido')"
)


def _consume(conn: Connection, key: str) -> None:
    assert conn.execute(text(CONSUME), {"h": stored_hash(key)}).rowcount == 1


def test_owner_inserts_usuario_with_the_email_of_the_consumed_invitation(acceso):
    with owner_tx(acceso, app_auth_inv_aceptar=CLAVE_A) as conn:
        _consume(conn, CLAVE_A)
        conn.execute(text(INSERT_USUARIO), {"id": uuid.uuid4(), "e": EMAIL_NUEVA_A})


def test_owner_cannot_insert_usuario_with_another_email(acceso):
    with owner_tx(acceso, app_auth_inv_aceptar=CLAVE_A) as conn:
        _consume(conn, CLAVE_A)
        assert_rls_rejects(conn, INSERT_USUARIO, {"id": uuid.uuid4(), "e": "otro@ejemplo.test"})


def test_owner_cannot_insert_usuario_without_consuming_the_invitation(acceso):
    with owner_tx(acceso, app_auth_inv_aceptar=CLAVE_A) as conn:
        assert_rls_rejects(conn, INSERT_USUARIO, {"id": uuid.uuid4(), "e": EMAIL_NUEVA_A})


def test_owner_cannot_insert_usuario_from_an_invitation_used_earlier(acceso):
    with owner_tx(acceso, app_auth_inv_aceptar=CLAVE_USADA) as conn:
        assert_rls_rejects(conn, INSERT_USUARIO, {"id": uuid.uuid4(), "e": "usada.a@ejemplo.test"})


def test_owner_cannot_insert_usuario_without_guc(acceso):
    with owner_tx(acceso) as conn:
        assert_rls_rejects(conn, INSERT_USUARIO, {"id": uuid.uuid4(), "e": EMAIL_NUEVA_A})


# --- 4. Dueño: INSERT membresia ligada a la invitación, rol y usuario ----------------

# Sin id (M3): auth_owner no tiene INSERT en membresia.id; lo pone el DEFAULT.
INSERT_MEMBRESIA = "insert into membresia (tenant_id, usuario_id, rol) values (:t, :u, :r)"


def _accept_until_membresia(conn: Connection, user: uuid.UUID) -> None:
    _consume(conn, CLAVE_A)
    conn.execute(text(INSERT_USUARIO), {"id": user, "e": EMAIL_NUEVA_A})
    conn.execute(text("select set_config('app.auth_usuario_nuevo', :u, true)"), {"u": str(user)})


def test_owner_inserts_membresia_bound_to_the_consumed_invitation(acceso):
    user = uuid.uuid4()
    with owner_tx(acceso, app_auth_inv_aceptar=CLAVE_A) as conn:
        _accept_until_membresia(conn, user)
        conn.execute(text(INSERT_MEMBRESIA), {"t": TENANT_A, "u": user, "r": "contador"})


@pytest.mark.parametrize(
    ("tenant", "rol", "other_user"),
    [
        (TENANT_A, "admin", False),  # otro rol que el de la invitación
        (TENANT_B, "contador", False),  # otro tenant
        (TENANT_A, "contador", True),  # otro usuario que el de la GUC
    ],
)
def test_owner_membresia_must_match_tenant_rol_and_usuario(acceso, tenant, rol, other_user):
    user = uuid.uuid4()
    with owner_tx(acceso, app_auth_inv_aceptar=CLAVE_A) as conn:
        _accept_until_membresia(conn, user)
        assert_rls_rejects(
            conn,
            INSERT_MEMBRESIA,
            {"t": tenant, "u": USER_A if other_user else user, "r": rol},
        )


def test_owner_cannot_insert_membresia_without_usuario_guc(acceso):
    user = uuid.uuid4()
    with owner_tx(acceso, app_auth_inv_aceptar=CLAVE_A) as conn:
        _consume(conn, CLAVE_A)
        conn.execute(text(INSERT_USUARIO), {"id": user, "e": EMAIL_NUEVA_A})
        assert_rls_rejects(conn, INSERT_MEMBRESIA, {"t": TENANT_A, "u": user, "r": "contador"})


def test_owner_cannot_insert_membresia_without_consuming_the_invitation(acceso):
    with owner_tx(acceso, app_auth_inv_aceptar=CLAVE_A, app_auth_usuario_nuevo=str(USER_A)) as conn:
        assert_rls_rejects(
            conn,
            INSERT_MEMBRESIA,
            {"t": TENANT_A, "u": USER_A, "r": "contador"},
        )


def test_owner_cannot_insert_membresia_from_an_invitation_used_earlier(acceso):
    with owner_tx(
        acceso, app_auth_inv_aceptar=CLAVE_USADA, app_auth_usuario_nuevo=str(USER_A)
    ) as conn:
        assert_rls_rejects(
            conn,
            INSERT_MEMBRESIA,
            {"t": TENANT_A, "u": USER_A, "r": "contador"},
        )


# --- 6 (dueño). INSERT tenant e invitacion solo para crear_tenant --------------------

INSERT_TENANT = "insert into tenant (id, nombre) values (:id, 'Clínica sintética nueva')"
# Sin id (M3): auth_owner no tiene INSERT en invitacion.id; lo pone el DEFAULT.
INSERT_INV_ADMIN = (
    "insert into invitacion (tenant_id, email, rol, token_hash, expira_en) "
    "values (:t, 'primer.admin@ejemplo.test', :r, :h, {expira})"
)
IN_24H = "now() + interval '24 hours'"


def _admin_invitacion(tenant: uuid.UUID) -> dict[str, object]:
    return {"t": tenant, "r": "admin", "h": stored_hash(clave(uuid.uuid4().hex))}


def test_owner_inserts_tenant_and_admin_invitation_with_its_guc(acceso):
    new = uuid.uuid4()
    with owner_tx(acceso, app_auth_tenant_nuevo=str(new)) as conn:
        conn.execute(text(INSERT_TENANT), {"id": new})
        conn.execute(text(INSERT_INV_ADMIN.format(expira=IN_24H)), _admin_invitacion(new))


def test_owner_reads_only_the_tenant_created_in_its_transaction(acceso):
    new = uuid.uuid4()
    with owner_tx(acceso, app_auth_tenant_nuevo=str(new)) as conn:
        assert conn.scalar(text("select count(id) from tenant")) == 0
        conn.execute(text(INSERT_TENANT), {"id": new})
        assert list(conn.scalars(text("select id from tenant"))) == [new]


@pytest.mark.parametrize("tenant", [TENANT_A, TENANT_B], ids=["A", "B"])
def test_owner_cannot_invite_an_admin_to_a_tenant_created_in_another_transaction(acceso, tenant):
    # I2: con el id de un tenant ya existente en la GUC, la invitación admin no pasa.
    with owner_tx(acceso, app_auth_tenant_nuevo=str(tenant)) as conn:
        assert_rls_rejects(conn, INSERT_INV_ADMIN.format(expira=IN_24H), _admin_invitacion(tenant))


def test_owner_cannot_set_tenant_creado_en(acceso):
    # creado_en no está en el GRANT de INSERT: no se puede fingir "creado ahora".
    new = uuid.uuid4()
    with owner_tx(acceso, app_auth_tenant_nuevo=str(new)) as conn:
        assert_denied(
            conn,
            "insert into tenant (id, nombre, creado_en) values (:id, 'x', now())",
            {"id": new},
        )


@pytest.mark.parametrize(
    "sql",
    [
        "insert into membresia (id, tenant_id, usuario_id, rol) "
        "values (gen_random_uuid(), :t, :u, 'contador')",
        "insert into invitacion (id, tenant_id, email, rol, token_hash, expira_en) "
        "values (gen_random_uuid(), :t, 'x@ejemplo.test', 'admin', :h, now())",
    ],
    ids=["membresia", "invitacion"],
)
def test_owner_cannot_choose_the_id_of_membresia_or_invitacion(acceso, sql):
    # M3: sin INSERT en membresia.id ni invitacion.id.
    with owner_tx(acceso, app_auth_tenant_nuevo=str(TENANT_A)) as conn:
        assert_denied(conn, sql, {"t": TENANT_A, "u": USER_A, "h": stored_hash(clave("m3"))})


@pytest.mark.parametrize("guc", [None, "", "%", "otro"])
def test_owner_cannot_insert_tenant_without_its_guc(acceso, guc):
    new = uuid.uuid4()
    gucs = (
        {}
        if guc is None
        else {"app_auth_tenant_nuevo": str(uuid.uuid4()) if guc == "otro" else guc}
    )
    with owner_tx(acceso, **gucs) as conn:
        assert_rls_rejects(conn, INSERT_TENANT, {"id": new})


@pytest.mark.parametrize(
    ("tenant", "rol", "expira"),
    [
        ("nuevo", "contador", IN_24H),  # rol distinto de admin
        ("nuevo", "admin", "now() + interval '24 hours 1 second'"),  # más de 24 h
        ("A", "admin", IN_24H),  # tenant distinto del de la GUC
    ],
)
def test_owner_admin_invitation_must_match_crear_tenant(acceso, tenant, rol, expira):
    new = uuid.uuid4()
    with owner_tx(acceso, app_auth_tenant_nuevo=str(new)) as conn:
        conn.execute(text(INSERT_TENANT), {"id": new})
        params = {**_admin_invitacion(new if tenant == "nuevo" else TENANT_A), "r": rol}
        assert_rls_rejects(conn, INSERT_INV_ADMIN.format(expira=expira), params)


def test_owner_cannot_insert_invitation_without_guc_or_with_creada_por(acceso):
    with owner_tx(acceso) as conn:
        assert_rls_rejects(
            conn, INSERT_INV_ADMIN.format(expira=IN_24H), _admin_invitacion(TENANT_A)
        )
    new = uuid.uuid4()
    with owner_tx(acceso, app_auth_tenant_nuevo=str(new)) as conn:
        conn.execute(text(INSERT_TENANT), {"id": new})
        # creada_por y usada_en no están en su GRANT de INSERT.
        for column, value in (("creada_por", ":u"), ("usada_en", "now()")):
            assert_denied(
                conn,
                "insert into invitacion (tenant_id, email, rol, token_hash, expira_en, "  # noqa: S608
                f"{column}) values (:t, 'primer.admin@ejemplo.test', 'admin', :h, now(), {value})",
                {"t": new, "h": stored_hash(clave(uuid.uuid4().hex)), "u": USER_A},
            )


@pytest.mark.parametrize("table", TABLES)
def test_owner_cannot_delete_or_truncate(acceso, table):
    with owner_tx(acceso, app_auth_inv_aceptar=CLAVE_A) as conn:
        assert_denied(conn, f"delete from {table}")  # noqa: S608
        assert_denied(conn, f"truncate {table}")


def test_owner_cannot_update_usuario_membresia_or_tenant(acceso):
    with owner_tx(acceso, app_auth_email=EMAIL_A, app_auth_usuario=str(USER_A)) as conn:
        assert_denied(conn, "update usuario set nombre = 'x'")
        assert_denied(conn, "update membresia set activa = false")
        assert_denied(conn, "update tenant set nombre = 'x'")


# --- 9 (nivel SQL). Las GUC no sobreviven a la transacción ni al savepoint -----------


def _guc(conn: Connection, name: str) -> str | None:
    return conn.scalar(text("select current_setting(:n, true)"), {"n": name})


@pytest.mark.parametrize("end", ["commit", "rollback"])
def test_owner_gucs_do_not_survive_the_transaction(acceso, end):
    with acceso.migrator.connect() as conn:
        tx = conn.begin()
        _set_owner(conn, dict.fromkeys(OWNER_GUCS, CLAVE_A))
        assert conn.scalar(text("select count(email) from invitacion")) == 1
        getattr(tx, end)()
        with conn.begin():
            for name in OWNER_GUCS:
                assert _guc(conn, name) in ("", None), name
            conn.exec_driver_sql(f"SET LOCAL ROLE {AUTH_OWNER}")
            assert conn.scalar(text("select count(email) from invitacion")) == 0


def test_owner_gucs_do_not_survive_rollback_to_savepoint(acceso):
    with acceso.migrator.connect() as conn:
        with conn.begin():
            conn.exec_driver_sql(f"SET LOCAL ROLE {AUTH_OWNER}")
            savepoint = conn.begin_nested()
            for name in OWNER_GUCS:
                conn.execute(text("select set_config(:n, :v, true)"), {"n": name, "v": CLAVE_A})
            assert conn.scalar(text("select count(email) from invitacion")) == 1
            savepoint.rollback()
            for name in OWNER_GUCS:
                assert _guc(conn, name) in ("", None), name
            assert conn.scalar(text("select count(email) from invitacion")) == 0


def test_app_tenant_does_not_survive_rollback_to_savepoint(acceso):
    with app_tx(acceso) as conn:
        savepoint = conn.begin_nested()
        _set_tenant(conn, TENANT_A)
        assert _count(conn, "membresia") == 1
        savepoint.rollback()
        assert _guc(conn, "app.tenant_id") in ("", None)
        for table in TABLES:
            assert _count(conn, table) == 0, table
