"""Pruebas de R4–R4d: aislamiento por tenant con RLS + filtro simple (spec 001, T3).

Las pruebas con base corren contra PostgreSQL real con dos roles:

- ``TEST_DATABASE_URL``: rol de la aplicación. La app se conecta con él y es lo
  que se prueba.
- ``TEST_MIGRATION_DATABASE_URL``: rol migrador. Solo crea y elimina las tablas de
  prueba con ``tenant_id``, ``ENABLE`` + ``FORCE ROW LEVEL SECURITY``, su política
  ``USING``/``WITH CHECK`` y ``GRANT SELECT, INSERT, UPDATE`` al rol de la app.

La barrera es RLS; varias pruebas atacan a propósito vías que el filtro de Python
no cubre y comprueban que la base las bloquea.
"""

import logging
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

import pytest
from conftest import BLOCKED
from sqlalchemy import (
    ForeignKey,
    Numeric,
    String,
    Uuid,
    create_engine,
    delete,
    exists,
    func,
    insert,
    literal,
    select,
    text,
    true,
    update,
)
from sqlalchemy import join as sa_join
from sqlalchemy.engine import URL, Engine
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    aliased,
    contains_eager,
    joinedload,
    make_transient_to_detached,
    mapped_column,
    relationship,
    selectinload,
)
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.pool import NullPool

from app import create_app
from app.config import Config
from app.db import (
    DatabaseNotInitializedError,
    MissingTenantError,
    TenantMismatchError,
    TenantScoped,
    UnscopedStatementError,
    _normalize_tenant,
    tenant_session,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
TENANT_A = uuid.UUID("00000000-0000-4000-8000-00000000000a")
TENANT_B = uuid.UUID("00000000-0000-4000-8000-00000000000b")
FAKE_PASSWORD = "clave-db-que-no-debe-salir"
REFUSED_DB = (
    f"postgresql+psycopg://usuario:{FAKE_PASSWORD}@127.0.0.1:1/assetcontrol?connect_timeout=2"
)
INSUFFICIENT_PRIVILEGE = "42501"
POLICY_EXPR = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"


class PruebaBase(DeclarativeBase):
    """Metadata propia de las pruebas: no contamina la de la aplicación."""


class PruebaCategoria(TenantScoped, PruebaBase):
    __tablename__ = "prueba_categoria_t3"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(50))
    activos: Mapped[list["PruebaActivo"]] = relationship(
        back_populates="categoria", order_by="PruebaActivo.nombre"
    )


class PruebaActivo(TenantScoped, PruebaBase):
    __tablename__ = "prueba_activo_t3"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(50))
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    categoria_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("prueba_categoria_t3.id"))
    categoria: Mapped[PruebaCategoria | None] = relationship(back_populates="activos")


ACTIVO = PruebaActivo.__table__


def make_app(database_url: str | URL):
    return create_app(
        Config(database_url=database_url, secret_key="clave-de-prueba", environment="test")
    )


def app_engine(app) -> Engine:
    return app.extensions["assetcontrol.db"].engine


def rls_ddl(table: str, role: str) -> list[str]:
    """Plantilla de toda tabla de negocio (plan.md §2), aplicada a una tabla de prueba."""
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING ({POLICY_EXPR}) WITH CHECK ({POLICY_EXPR})",
        f"GRANT SELECT, INSERT, UPDATE ON {table} TO {role}",
    ]


def create_test_tables(migrator: Engine, app_role: str) -> None:
    with migrator.begin() as conn:
        PruebaBase.metadata.drop_all(conn)
        PruebaBase.metadata.create_all(conn)
        preparer = conn.dialect.identifier_preparer
        role = preparer.quote(app_role)
        for table in PruebaBase.metadata.sorted_tables:
            for sql in rls_ddl(preparer.format_table(table), role):
                conn.execute(text(sql))


@pytest.fixture
def pg_app(app_database_url, migration_database_url):
    """App conectada con el rol de la aplicación; tablas de prueba creadas por el migrador."""
    migrator = create_engine(migration_database_url, poolclass=NullPool)
    failure = None
    try:
        create_test_tables(migrator, app_database_url.username)
    except OperationalError as exc:
        # Solo el nombre del error: el traceback de psycopg trae la contraseña en sus frames.
        failure = f"{BLOCKED} (rol migrador: {type(exc.orig).__name__})"
    if failure is not None:
        # Fuera del except: así pytest no encadena el OperationalError original.
        migrator.dispose()
        pytest.fail(failure, pytrace=False)

    app = make_app(app_database_url)
    try:
        with app_engine(app).connect():
            pass
    except OperationalError as exc:
        failure = f"{BLOCKED} (rol de la aplicación: {type(exc.orig).__name__})"
    try:
        if failure is not None:
            pytest.fail(failure, pytrace=False)
        with app.app_context():
            yield app
    finally:
        app_engine(app).dispose()
        with migrator.begin() as conn:
            PruebaBase.metadata.drop_all(conn)
        migrator.dispose()


@pytest.fixture
def raw_app_engine(pg_app, app_database_url) -> Iterator[Engine]:
    """Engine propio del rol de la aplicación, sin pasar por ``tenant_session``."""
    engine = create_engine(app_database_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def offline_app():
    """App con una base inalcanzable: sirve para validar sin conectar."""
    app = make_app(REFUSED_DB)
    with app.app_context():
        yield app


@contextmanager
def denied_by_database() -> Iterator[None]:
    """La base rechaza la operación por RLS (``WITH CHECK``) o por permisos."""
    with pytest.raises(DBAPIError) as excinfo:
        yield
    assert getattr(excinfo.value.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE


def seed(tenant_id, *nombres, valor: str = "0.00", categoria_id=None) -> list[uuid.UUID]:
    with tenant_session(tenant_id) as session:
        rows = [
            PruebaActivo(nombre=n, valor=Decimal(valor), categoria_id=categoria_id) for n in nombres
        ]
        session.add_all(rows)
        session.flush()
        return [r.id for r in rows]


def seed_categoria(tenant_id, nombre: str, *activos: str) -> tuple[uuid.UUID, list[uuid.UUID]]:
    with tenant_session(tenant_id) as session:
        categoria = PruebaCategoria(nombre=nombre)
        session.add(categoria)
        session.flush()
        categoria_id = categoria.id
    return categoria_id, seed(tenant_id, *activos, categoria_id=categoria_id)


def names_of(tenant_id) -> list[str]:
    with tenant_session(tenant_id) as session:
        return sorted(session.scalars(select(PruebaActivo.nombre)))


def set_tenant(conn, tenant_id) -> None:
    conn.execute(
        text("select set_config('app.tenant_id', :tenant_id, true)"), {"tenant_id": str(tenant_id)}
    )


# --- Sin tenant (sin base) -------------------------------------------------


@pytest.mark.parametrize("missing", [None, "", "   "])
def test_tenant_session_without_tenant_fails_explicitly(offline_app, missing):
    with pytest.raises(MissingTenantError, match="tenant"):
        with tenant_session(missing):
            pass


@pytest.mark.parametrize("invalid", ["no-es-un-uuid", "1234", 42])
def test_tenant_session_with_invalid_tenant_fails(offline_app, invalid):
    with pytest.raises(MissingTenantError):
        with tenant_session(invalid):
            pass


@pytest.mark.parametrize(
    "payload",
    [
        "'; select set_config('app.tenant_id','x',false); --",
        "' or '1'='1",
        f"{TENANT_A}'; select set_config('app.tenant_id','{TENANT_B}',false); --",
    ],
    ids=["set-config", "or-true", "uuid-prefix"],
)
def test_injection_payload_as_tenant_fails_before_connecting(offline_app, monkeypatch, payload):
    """Con la base inalcanzable, conectar daría ``OperationalError``: aquí no se llega."""

    def no_connect(*args, **kwargs):
        raise AssertionError("se intentó conectar con un tenant inválido")

    monkeypatch.setattr(app_engine(offline_app), "connect", no_connect)
    with pytest.raises(MissingTenantError):
        with tenant_session(payload):
            pass


class SneakyUUID(uuid.UUID):
    """Subclase con ``__str__`` hostil: lo que llegaría a ``set_config``."""

    def __str__(self) -> str:
        return f"{TENANT_B}' or '1'='1"


def test_normalized_tenant_is_an_exact_uuid():
    sneaky = SneakyUUID(str(TENANT_A))

    normalized = _normalize_tenant(sneaky)

    assert type(normalized) is uuid.UUID
    assert str(normalized) == str(TENANT_A)


def test_tenant_session_keeps_an_exact_uuid(offline_app):
    with tenant_session(SneakyUUID(str(TENANT_A))) as session:
        assert type(session.scoped_tenant) is uuid.UUID
        assert str(session.scoped_tenant) == str(TENANT_A)


def test_tenant_session_outside_app_fails_explicitly():
    with pytest.raises(DatabaseNotInitializedError):
        with tenant_session(TENANT_A):
            pass


# --- Higiene en Python (sin base) ------------------------------------------


def test_raw_sql_is_rejected_inside_tenant_session(offline_app):
    with pytest.raises(UnscopedStatementError):
        with tenant_session(TENANT_A) as session:
            session.execute(text("SELECT * FROM prueba_activo_t3"))


def test_session_connection_is_rejected(offline_app):
    with pytest.raises(UnscopedStatementError):
        with tenant_session(TENANT_A) as session:
            session.connection()


@pytest.mark.parametrize(
    "make_statement",
    [
        lambda: select(func.pg_backend_pid()),
        lambda: select(ACTIVO.c.nombre),
        lambda: select(PruebaActivo.nombre).select_from(
            sa_join(PruebaCategoria, PruebaActivo, true())
        ),
    ],
    ids=["core-func", "core-table", "explicit-join"],
)
def test_python_does_not_blacklist_statements(offline_app, make_statement):
    """Python ya no recorre el árbol: la sentencia llega a la base (RLS decide)."""
    with pytest.raises(OperationalError):
        with tenant_session(TENANT_A) as session:
            session.execute(make_statement())


# --- Atributos del rol y de la tabla (A4a) ---------------------------------


def test_app_role_cannot_bypass_rls(pg_app, app_database_url, migration_database_url):
    assert app_database_url.username != migration_database_url.username

    with app_engine(pg_app).connect() as conn:
        rolsuper, rolbypassrls = conn.execute(
            text("select rolsuper, rolbypassrls from pg_roles where rolname = current_user")
        ).one()
        tables = conn.execute(
            text(
                "select c.relname, c.relrowsecurity, c.relforcerowsecurity, "
                "pg_get_userbyid(c.relowner) = current_user "
                "from pg_class c where c.relname in ('prueba_activo_t3', 'prueba_categoria_t3') "
                "order by c.relname"
            )
        ).all()

        rolcreaterole, rolcreatedb = conn.execute(
            text("select rolcreaterole, rolcreatedb from pg_roles where rolname = current_user")
        ).one()
        # Ni dueño ni miembro del dueño: con USAGE sobre el dueño heredaría sus permisos.
        owner_usage = conn.execute(
            text(
                "select c.relname, pg_has_role(current_user, c.relowner, 'USAGE') "
                "from pg_class c where c.relname in ('prueba_activo_t3', 'prueba_categoria_t3') "
                "order by c.relname"
            )
        ).all()
        # Membresía directa o heredada en un rol que salte RLS (MEMBER = puede hacer SET ROLE).
        privileged_by_has_role = conn.execute(
            text(
                "select r.rolname from pg_roles r "
                "where (r.rolsuper or r.rolbypassrls) and r.rolname <> current_user "
                "and pg_has_role(current_user, r.oid, 'MEMBER')"
            )
        ).all()
        privileged_by_graph = conn.execute(
            text(
                "with recursive granted(roleid) as ("
                "  select m.roleid from pg_auth_members m "
                "  where m.member = (select oid from pg_roles where rolname = current_user)"
                "  union "
                "  select m.roleid from pg_auth_members m join granted g on m.member = g.roleid"
                ") "
                "select r.rolname from granted g join pg_roles r on r.oid = g.roleid "
                "where r.rolsuper or r.rolbypassrls"
            )
        ).all()

    assert rolsuper is False
    assert rolbypassrls is False
    assert rolcreaterole is False
    assert rolcreatedb is False
    assert [tuple(row) for row in tables] == [
        ("prueba_activo_t3", True, True, False),
        ("prueba_categoria_t3", True, True, False),
    ]
    assert [tuple(row) for row in owner_usage] == [
        ("prueba_activo_t3", False),
        ("prueba_categoria_t3", False),
    ]
    assert privileged_by_has_role == []
    assert privileged_by_graph == []


# --- Tenant en la transacción ----------------------------------------------


def test_tenant_session_sets_local_tenant(pg_app):
    with tenant_session(TENANT_A) as session:
        assert session.scalar(select(func.current_setting("app.tenant_id", True))) == str(TENANT_A)


def test_tenant_session_accepts_uuid_string(pg_app):
    seed(str(TENANT_A), "silla")
    seed(TENANT_B, "autoclave", "lampara")

    with tenant_session(str(TENANT_A)) as session:
        assert session.scalar(select(func.count()).select_from(PruebaActivo)) == 1
        assert session.scalars(select(PruebaActivo.nombre)).all() == ["silla"]


# --- Dos tenants ------------------------------------------------------------


def test_select_only_returns_rows_of_the_session_tenant(pg_app):
    seed(TENANT_A, "silla", "mesa")
    seed(TENANT_B, "autoclave")

    with tenant_session(TENANT_A) as session:
        nombres_a = sorted(session.scalars(select(PruebaActivo.nombre)))
        total_a = session.scalar(select(func.count(PruebaActivo.id)))

    assert nombres_a == ["mesa", "silla"]
    assert total_a == 2
    assert names_of(TENANT_B) == ["autoclave"]


def test_other_tenant_row_is_invisible_even_by_id(pg_app):
    [id_b] = seed(TENANT_B, "autoclave")

    with tenant_session(TENANT_A) as session:
        assert session.get(PruebaActivo, id_b) is None
        assert session.scalars(select(PruebaActivo).where(PruebaActivo.id == id_b)).all() == []
        explicit = select(PruebaActivo).where(PruebaActivo.tenant_id == TENANT_B)
        assert session.scalars(explicit).all() == []


def test_orm_update_statement_only_touches_the_session_tenant(pg_app):
    seed(TENANT_A, "silla")
    seed(TENANT_B, "autoclave", "lampara")

    with tenant_session(TENANT_A) as session:
        session.execute(update(PruebaActivo).values(nombre="cambiado"))

    assert names_of(TENANT_A) == ["cambiado"]
    assert names_of(TENANT_B) == ["autoclave", "lampara"]


# --- Escrituras -------------------------------------------------------------


def test_insert_without_tenant_receives_the_session_tenant(pg_app):
    with tenant_session(TENANT_A) as session:
        row = PruebaActivo(nombre="silla")
        session.add(row)
        session.flush()
        assert row.tenant_id == TENANT_A

    assert names_of(TENANT_B) == []


def test_insert_with_another_tenant_is_rejected_by_python(pg_app):
    with pytest.raises(TenantMismatchError):
        with tenant_session(TENANT_A) as session:
            session.add(PruebaActivo(nombre="intruso", tenant_id=TENANT_B))

    assert names_of(TENANT_A) == []
    assert names_of(TENANT_B) == []


def test_insert_with_another_tenant_is_rejected_by_rls(pg_app):
    """El INSERT del ORM no pasa por ``before_flush``: lo frena ``WITH CHECK``."""
    with denied_by_database():
        with tenant_session(TENANT_A) as session:
            session.execute(
                insert(PruebaActivo).values(id=uuid.uuid4(), nombre="intruso", tenant_id=TENANT_B)
            )

    assert names_of(TENANT_B) == []


def test_moving_a_row_to_another_tenant_is_rejected(pg_app):
    [id_a] = seed(TENANT_A, "silla")

    with pytest.raises(TenantMismatchError):
        with tenant_session(TENANT_A) as session:
            row = session.get(PruebaActivo, id_a)
            row.tenant_id = TENANT_B
    with denied_by_database():
        with tenant_session(TENANT_A) as session:
            session.execute(update(PruebaActivo).values(tenant_id=TENANT_B))

    assert names_of(TENANT_A) == ["silla"]
    assert names_of(TENANT_B) == []


def test_failed_block_rolls_back(pg_app):
    with pytest.raises(RuntimeError, match="falla a propósito"):
        with tenant_session(TENANT_A) as session:
            session.add(PruebaActivo(nombre="silla"))
            session.flush()
            raise RuntimeError("falla a propósito")

    assert names_of(TENANT_A) == []


def test_changing_session_info_tenant_has_no_effect(pg_app):
    seed(TENANT_A, "silla")
    seed(TENANT_B, "autoclave")

    with tenant_session(TENANT_A) as session:
        session.info["tenant_id"] = TENANT_B
        assert session.scalars(select(PruebaActivo.nombre)).all() == ["silla"]
        session.add(PruebaActivo(nombre="mesa"))

    assert names_of(TENANT_A) == ["mesa", "silla"]
    assert names_of(TENANT_B) == ["autoclave"]


# --- DELETE: sin permiso (nada se borra) ----------------------------------


def test_delete_is_denied_by_permissions(pg_app, raw_app_engine):
    [id_a] = seed(TENANT_A, "silla")

    with denied_by_database():
        with tenant_session(TENANT_A) as session:
            session.delete(session.get(PruebaActivo, id_a))
    with denied_by_database():
        with tenant_session(TENANT_A) as session:
            session.execute(delete(PruebaActivo))
    with denied_by_database():
        with raw_app_engine.begin() as conn:
            set_tenant(conn, TENANT_A)
            conn.execute(text("delete from prueba_activo_t3"))

    assert names_of(TENANT_A) == ["silla"]


# --- Sin tenant fijado: nada (R4b) -----------------------------------------


def test_pooled_connection_that_had_a_tenant_sees_nothing(pg_app):
    seed(TENANT_A, "silla")
    seed(TENANT_B, "autoclave")
    with tenant_session(TENANT_A) as session:
        pid = session.scalar(select(func.pg_backend_pid()))

    engine = app_engine(pg_app)
    with engine.connect() as conn:
        assert conn.scalar(select(func.pg_backend_pid())) == pid
        assert conn.scalar(select(func.current_setting("app.tenant_id", True))) in ("", None)
        assert conn.scalar(select(func.count()).select_from(ACTIVO)) == 0
    with denied_by_database():
        with engine.begin() as conn:
            conn.execute(insert(ACTIVO).values(id=uuid.uuid4(), tenant_id=TENANT_A, nombre="x"))

    assert names_of(TENANT_A) == ["silla"]


def fail_with_python_error(session) -> None:
    raise RuntimeError("falla a propósito")


def fail_with_database_error(session) -> None:
    session.execute(insert(PruebaActivo).values(id=uuid.uuid4(), nombre="x", tenant_id=TENANT_B))


@pytest.mark.parametrize(
    ("fail", "expected"),
    [(fail_with_python_error, RuntimeError), (fail_with_database_error, DBAPIError)],
    ids=["python-error", "database-error-42501"],
)
def test_pooled_connection_after_failed_session_sees_nothing(pg_app, fail, expected):
    seed(TENANT_A, "silla")
    pids: list[int] = []

    with pytest.raises(expected) as excinfo:
        with tenant_session(TENANT_A) as session:
            pids.append(session.scalar(select(func.pg_backend_pid())))
            fail(session)
    if expected is DBAPIError:
        assert getattr(excinfo.value.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE

    with app_engine(pg_app).connect() as conn:
        assert conn.scalar(select(func.pg_backend_pid())) == pids[0]
        assert conn.scalar(select(func.current_setting("app.tenant_id", True))) in ("", None)
        assert conn.scalar(select(func.count()).select_from(ACTIVO)) == 0

    assert names_of(TENANT_A) == ["silla"]
    assert names_of(TENANT_B) == []


def test_savepoint_rollback_keeps_the_session_tenant(pg_app):
    seed(TENANT_A, "silla")
    seed(TENANT_B, "autoclave")

    with tenant_session(TENANT_A) as session:
        nested = session.begin_nested()
        session.add(PruebaActivo(nombre="mesa"))
        session.flush()
        nested.rollback()
        assert session.scalar(select(func.current_setting("app.tenant_id", True))) == str(TENANT_A)

        with pytest.raises(DBAPIError) as excinfo:
            with session.begin_nested():
                session.execute(
                    insert(PruebaActivo).values(id=uuid.uuid4(), nombre="x", tenant_id=TENANT_B)
                )
        assert getattr(excinfo.value.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE

        assert session.scalar(select(func.current_setting("app.tenant_id", True))) == str(TENANT_A)
        assert session.scalars(select(PruebaActivo.nombre)).all() == ["silla"]
        session.add(PruebaActivo(nombre="lampara"))

    assert names_of(TENANT_A) == ["lampara", "silla"]
    assert names_of(TENANT_B) == ["autoclave"]


def test_fresh_connection_without_tenant_sees_nothing(pg_app, raw_app_engine):
    seed(TENANT_A, "silla")

    with raw_app_engine.connect() as conn:
        assert conn.execute(text("select nombre from prueba_activo_t3")).all() == []
    with denied_by_database():
        with raw_app_engine.begin() as conn:
            conn.execute(
                text(
                    "insert into prueba_activo_t3 (id, tenant_id, nombre, valor) "
                    "values (:id, :tenant, 'x', 0)"
                ),
                {"id": uuid.uuid4(), "tenant": TENANT_A},
            )

    assert names_of(TENANT_A) == ["silla"]


# --- Vías que el filtro de Python no cubre: las bloquea RLS ----------------


def test_rls_blocks_other_tenant_through_get_bind(pg_app):
    seed(TENANT_A, "silla")
    [id_b] = seed(TENANT_B, "autoclave")

    with tenant_session(TENANT_A) as session:
        with session.get_bind().connect() as conn:
            assert conn.execute(select(ACTIVO.c.nombre)).all() == []
            set_tenant(conn, TENANT_A)
            assert conn.execute(select(ACTIVO.c.nombre)).scalars().all() == ["silla"]
            stolen = select(ACTIVO.c.nombre).where(ACTIVO.c.id == id_b)
            assert conn.execute(stolen).all() == []


def test_rls_blocks_other_tenant_through_app_engine(pg_app):
    seed(TENANT_A, "silla")
    [id_b] = seed(TENANT_B, "autoclave")
    engine = app_engine(pg_app)

    with engine.begin() as conn:
        set_tenant(conn, TENANT_A)
        assert conn.execute(select(ACTIVO.c.nombre)).scalars().all() == ["silla"]
        result = conn.execute(update(ACTIVO).where(ACTIVO.c.id == id_b).values(nombre="cambiado"))
        assert result.rowcount == 0
    with denied_by_database():
        with engine.begin() as conn:
            set_tenant(conn, TENANT_A)
            conn.execute(insert(ACTIVO).values(id=uuid.uuid4(), tenant_id=TENANT_B, nombre="x"))

    assert names_of(TENANT_B) == ["autoclave"]


def test_rls_blocks_other_tenant_through_raw_sql(pg_app, raw_app_engine):
    seed(TENANT_A, "silla")
    seed(TENANT_B, "autoclave")

    with raw_app_engine.begin() as conn:
        set_tenant(conn, TENANT_A)
        assert conn.execute(text("select nombre from prueba_activo_t3")).scalars().all() == [
            "silla"
        ]
        by_tenant = text("select nombre from prueba_activo_t3 where tenant_id = :tenant")
        assert conn.execute(by_tenant, {"tenant": TENANT_B}).all() == []
        changed = conn.execute(
            text("update prueba_activo_t3 set nombre = 'cambiado' where tenant_id = :tenant"),
            {"tenant": TENANT_B},
        )
        assert changed.rowcount == 0
    with denied_by_database():
        with raw_app_engine.begin() as conn:
            set_tenant(conn, TENANT_A)
            conn.execute(
                text(
                    "insert into prueba_activo_t3 (id, tenant_id, nombre, valor) "
                    "values (:id, :tenant, 'x', 0)"
                ),
                {"id": uuid.uuid4(), "tenant": TENANT_B},
            )

    assert names_of(TENANT_B) == ["autoclave"]


def test_rls_blocks_legacy_bulk_insert(pg_app):
    with denied_by_database():
        with tenant_session(TENANT_A) as session:
            session.bulk_insert_mappings(
                PruebaActivo, [{"id": uuid.uuid4(), "nombre": "x", "tenant_id": TENANT_B}]
            )
    with denied_by_database():
        with tenant_session(TENANT_A) as session:
            session.bulk_save_objects([PruebaActivo(nombre="x", tenant_id=TENANT_B)])
    with denied_by_database():
        with tenant_session(TENANT_A) as session:
            session.execute(
                insert(PruebaActivo), [{"id": uuid.uuid4(), "nombre": "x", "tenant_id": TENANT_B}]
            )

    assert names_of(TENANT_B) == []


def test_rls_blocks_legacy_bulk_update(pg_app):
    [id_b] = seed(TENANT_B, "autoclave")

    def bulk_update_mappings():
        with tenant_session(TENANT_A) as session:
            session.bulk_update_mappings(PruebaActivo, [{"id": id_b, "nombre": "cambiado"}])

    def bulk_update_by_pk():
        with tenant_session(TENANT_A) as session:
            session.execute(update(PruebaActivo), [{"id": id_b, "nombre": "cambiado"}])

    # RLS esconde la fila de B: el UPDATE afecta 0 filas y el ORM lo detecta.
    with pytest.raises(StaleDataError):
        bulk_update_mappings()
    assert names_of(TENANT_B) == ["autoclave"]
    with pytest.raises(StaleDataError):
        bulk_update_by_pk()

    assert names_of(TENANT_B) == ["autoclave"]


def test_rls_blocks_explicit_join(pg_app):
    seed_categoria(TENANT_A, "cat-a", "silla")
    seed_categoria(TENANT_B, "cat-b", "autoclave", "lampara")
    joined = sa_join(PruebaCategoria, PruebaActivo, true())

    with tenant_session(TENANT_A) as session:
        nombres = session.scalars(select(PruebaActivo.nombre).select_from(joined)).all()
        total = session.scalar(select(func.count()).select_from(joined))

    assert nombres == ["silla"]
    assert total == 1


# El filtro de Python no se adapta a una subconsulta Core que finge ``tenant_id``:
# SQLAlchemy avisa y agrega la tabla real como producto cartesiano. RLS limita ambas a A.
@pytest.mark.filterwarnings("ignore:Did not locate an expression:sqlalchemy.exc.SAWarning")
@pytest.mark.filterwarnings("ignore:SELECT statement has a cartesian:sqlalchemy.exc.SAWarning")
def test_rls_blocks_aliased_core_subquery_with_fake_tenant(pg_app):
    seed(TENANT_A, "silla")
    seed(TENANT_B, "autoclave")
    fake = select(
        ACTIVO.c.id,
        ACTIVO.c.nombre,
        ACTIVO.c.valor,
        ACTIVO.c.categoria_id,
        literal(TENANT_A, Uuid).label("tenant_id"),
    ).subquery()
    disguised = aliased(PruebaActivo, fake)

    with tenant_session(TENANT_A) as session:
        assert session.scalars(select(disguised.nombre)).all() == ["silla"]

    assert names_of(TENANT_B) == ["autoclave"]


def fabricate_detached(row_id, tenant_id=TENANT_A, nombre="autoclave", **values) -> PruebaActivo:
    row = PruebaActivo(id=row_id, tenant_id=tenant_id, nombre=nombre, **values)
    make_transient_to_detached(row)
    return row


def test_detached_object_of_other_tenant_cannot_be_updated(pg_app):
    [id_b] = seed(TENANT_B, "autoclave")

    with pytest.raises(StaleDataError):
        with tenant_session(TENANT_A) as session:
            row = fabricate_detached(id_b, valor=Decimal("0.00"), categoria_id=None)
            session.add(row)
            row.nombre = "cambiado"
    with pytest.raises(TenantMismatchError):
        with tenant_session(TENANT_A) as session:
            row = fabricate_detached(id_b, tenant_id=TENANT_B)
            session.add(row)
            row.nombre = "cambiado"

    assert names_of(TENANT_B) == ["autoclave"]


def test_merge_load_false_other_tenant_is_blocked(pg_app):
    [id_b] = seed(TENANT_B, "autoclave")

    with pytest.raises(StaleDataError):
        with tenant_session(TENANT_A) as session:
            detached = fabricate_detached(id_b, valor=Decimal("0.00"), categoria_id=None)
            merged = session.merge(detached, load=False)
            merged.nombre = "cambiado"

    assert names_of(TENANT_B) == ["autoclave"]


def test_append_object_of_other_tenant_to_collection_is_blocked(pg_app):
    categoria_a, _ = seed_categoria(TENANT_A, "cat-a", "silla")
    categoria_b, [id_b] = seed_categoria(TENANT_B, "cat-b", "autoclave")

    def steal():
        with tenant_session(TENANT_A) as session:
            categoria = session.get(PruebaCategoria, categoria_a)
            intruso = fabricate_detached(id_b, valor=Decimal("0.00"), categoria_id=categoria_b)
            categoria.activos.append(intruso)

    # RLS esconde la fila de B: el UPDATE de ``categoria_id`` afecta 0 filas.
    with pytest.raises(StaleDataError):
        steal()

    with tenant_session(TENANT_B) as session:
        assert session.get(PruebaActivo, id_b).categoria_id == categoria_b


def test_detached_object_of_own_tenant_can_be_updated(pg_app):
    [id_a] = seed(TENANT_A, "silla")

    with tenant_session(TENANT_A) as session:
        row = fabricate_detached(id_a, nombre="silla", valor=Decimal("0.00"), categoria_id=None)
        session.add(row)
        row.nombre = "mesa"

    assert names_of(TENANT_A) == ["mesa"]


# --- Regresión: consultas legítimas del ORM --------------------------------


def test_relationship_joins_between_tenant_models(pg_app):
    seed_categoria(TENANT_A, "cat-a", "silla", "mesa")
    seed_categoria(TENANT_B, "cat-b", "autoclave")

    with tenant_session(TENANT_A) as session:
        pairs = session.execute(
            select(PruebaCategoria.nombre, PruebaActivo.nombre)
            .join(PruebaCategoria.activos)
            .order_by(PruebaActivo.nombre)
        ).all()
        with_any = session.scalars(
            select(PruebaCategoria.nombre).where(PruebaCategoria.activos.any())
        ).all()
        with_has = session.scalars(
            select(PruebaActivo.nombre)
            .where(PruebaActivo.categoria.has(PruebaCategoria.nombre == "cat-a"))
            .order_by(PruebaActivo.nombre)
        ).all()
        eager = (
            session.scalars(
                select(PruebaCategoria)
                .join(PruebaCategoria.activos)
                .options(contains_eager(PruebaCategoria.activos))
            )
            .unique()
            .all()
        )

    assert [tuple(p) for p in pairs] == [("cat-a", "mesa"), ("cat-a", "silla")]
    assert with_any == ["cat-a"]
    assert with_has == ["mesa", "silla"]
    assert [c.nombre for c in eager] == ["cat-a"]
    assert sorted(a.nombre for a in eager[0].activos) == ["mesa", "silla"]


def test_sum_of_numeric_is_decimal_of_own_tenant(pg_app):
    seed(TENANT_A, "silla", valor="10.10")
    seed(TENANT_A, "mesa", valor="20.25")
    seed(TENANT_B, "autoclave", valor="4787206.38")

    with tenant_session(TENANT_A) as session:
        total = session.scalar(select(func.sum(PruebaActivo.valor)))

    assert isinstance(total, Decimal)
    assert total == Decimal("30.35")


def test_limit_offset_with_order_by(pg_app):
    seed(TENANT_A, "d", "b", "a", "c")
    seed(TENANT_B, "aa", "ab", "ac")

    with tenant_session(TENANT_A) as session:
        page = session.scalars(
            select(PruebaActivo.nombre).order_by(PruebaActivo.nombre).limit(2).offset(1)
        ).all()

    assert page == ["b", "c"]


def test_subqueries_exists_and_cte_stay_filtered(pg_app):
    seed_categoria(TENANT_A, "silla", "silla")
    seed_categoria(TENANT_B, "autoclave", "autoclave")

    with tenant_session(TENANT_A) as session:
        correlated = exists().where(PruebaActivo.nombre == PruebaCategoria.nombre)
        assert session.scalars(select(PruebaCategoria.nombre).where(correlated)).all() == ["silla"]
        sub = select(PruebaActivo.id).subquery()
        assert session.scalar(select(func.count(sub.c.id)).select_from(sub)) == 1
        cte = select(PruebaActivo.nombre).cte()
        assert session.scalars(select(cte.c.nombre)).all() == ["silla"]
        alias = aliased(PruebaActivo)
        assert session.scalars(select(alias.nombre)).all() == ["silla"]
        union = select(PruebaActivo.nombre).union_all(select(PruebaActivo.nombre))
        assert session.scalars(union).all() == ["silla", "silla"]


@pytest.mark.parametrize("loader", ["lazy", "selectin", "joined"])
def test_relationship_loads_stay_filtered(pg_app, loader):
    seed_categoria(TENANT_A, "cat-a", "silla")
    seed_categoria(TENANT_B, "cat-b", "autoclave")

    options = {
        "lazy": [],
        "selectin": [selectinload(PruebaCategoria.activos)],
        "joined": [joinedload(PruebaCategoria.activos)],
    }[loader]
    with tenant_session(TENANT_A) as session:
        categorias = session.scalars(select(PruebaCategoria).options(*options)).unique().all()
        assert [c.nombre for c in categorias] == ["cat-a"]
        assert [a.nombre for a in categorias[0].activos] == ["silla"]


# --- Sin secretos en errores ni logs ---------------------------------------


def test_errors_and_logs_do_not_leak_database_url(offline_app, caplog):
    caplog.set_level(logging.DEBUG)
    errors: list[BaseException] = []

    for bad in (None, "", "no-es-un-uuid"):
        with pytest.raises(MissingTenantError) as excinfo:
            with tenant_session(bad):
                pass
        errors.append(excinfo.value)

    with pytest.raises(OperationalError) as excinfo:
        with tenant_session(TENANT_A) as session:
            session.scalars(select(PruebaActivo)).all()
    errors.append(excinfo.value)

    texts = [str(e) for e in errors] + [repr(e) for e in errors] + [caplog.text]
    for chunk in texts:
        assert FAKE_PASSWORD not in chunk
        assert REFUSED_DB not in chunk


# --- Sin secretos en la salida de pytest -----------------------------------

LEAK_PASSWORD = "CLAVE_FICTICIA_123"
LEAK_URL = f"postgresql+psycopg://u:{LEAK_PASSWORD}@127.0.0.1:1/x?connect_timeout=2"
LEAK_MIGRATION_PASSWORD = "CLAVE_MIGRADOR_456"
LEAK_MIGRATION_URL = (
    f"postgresql+psycopg://m:{LEAK_MIGRATION_PASSWORD}@127.0.0.1:1/x?connect_timeout=2"
)
URL_VARS = {
    "DATABASE_URL",
    "TEST_DATABASE_URL",
    "MIGRATION_DATABASE_URL",
    "TEST_MIGRATION_DATABASE_URL",
}

LEAK_PROBE = """
import os

from sqlalchemy import create_engine, text


def test_conexion_que_falla_dentro_de_la_prueba():
    url = os.environ["TEST_DATABASE_URL"]
    print("url en stdout:", url)
    engine = create_engine(url)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def test_conexion_del_migrador_que_falla():
    url = os.environ["TEST_MIGRATION_DATABASE_URL"]
    print("url del migrador en stdout:", url)
    engine = create_engine(url)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def test_asercion_que_muestra_la_url():
    url = os.environ["TEST_DATABASE_URL"]
    other = os.environ["MIGRATION_DATABASE_URL"]
    assert url == other
"""


def run_pytest(*args: str) -> str:
    env = {k: v for k, v in os.environ.items() if k not in URL_VARS}
    env["TEST_DATABASE_URL"] = LEAK_URL
    env["TEST_MIGRATION_DATABASE_URL"] = LEAK_MIGRATION_URL
    env["MIGRATION_DATABASE_URL"] = LEAK_MIGRATION_URL
    result = subprocess.run(  # noqa: S603 - comando fijo, sin entrada externa
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout + result.stderr


def test_database_url_fixtures_hide_password(monkeypatch, request):
    monkeypatch.setenv("TEST_DATABASE_URL", LEAK_URL)
    monkeypatch.setenv("TEST_MIGRATION_DATABASE_URL", LEAK_MIGRATION_URL)

    app_url = request.getfixturevalue("app_database_url")
    migration_url = request.getfixturevalue("migration_database_url")

    assert app_url.password == LEAK_PASSWORD
    assert migration_url.password == LEAK_MIGRATION_PASSWORD
    for url, password in ((app_url, LEAK_PASSWORD), (migration_url, LEAK_MIGRATION_PASSWORD)):
        assert password not in str(url)
        assert password not in repr(url)


def test_blocked_postgres_fixture_does_not_show_password():
    output = run_pytest(
        "tests/test_tenant_scope.py",
        "-k",
        "test_select_only_returns_rows_of_the_session_tenant",
        "--tb=long",
        "--showlocals",
    )

    assert "bloqueado: faltan TEST_DATABASE_URL" in output
    assert LEAK_PASSWORD not in output
    assert LEAK_MIGRATION_PASSWORD not in output
    assert "During handling of the above exception" not in output
    assert "site-packages" not in output


@pytest.mark.parametrize("tb", ["auto", "long", "short", "native"])
def test_failures_inside_tests_do_not_show_password(tmp_path, tb):
    probe = tmp_path / "test_fuga_probe.py"
    probe.write_text(LEAK_PROBE, encoding="utf-8")

    output = run_pytest(
        "-p", "tests.conftest", "--rootdir", str(tmp_path), f"--tb={tb}", "-l", "-rA", str(probe)
    )

    assert "3 failed" in output
    assert LEAK_PASSWORD not in output
    assert LEAK_MIGRATION_PASSWORD not in output


# --- Importar no conecta ----------------------------------------------------

IMPORT_PROBE = """
import socket

def fail(*args, **kwargs):
    raise SystemExit("conexion abierta al importar")

socket.create_connection = fail
socket.socket.connect = fail

import sqlalchemy
from sqlalchemy.engine import Engine

created = []
original = sqlalchemy.create_engine

def spy(*args, **kwargs):
    created.append(1)
    return original(*args, **kwargs)

sqlalchemy.create_engine = spy

import app
import app.db

assert not created, "create_engine llamado al importar"
for module in (app, app.db):
    for value in vars(module).values():
        assert not isinstance(value, Engine), "engine creado al importar"
print("ok")
"""


def test_importing_app_and_db_opens_no_connection_nor_engine():
    env = {k: v for k, v in os.environ.items() if k not in URL_VARS}
    result = subprocess.run(  # noqa: S603 - comando fijo, sin entrada externa
        [sys.executable, "-c", IMPORT_PROBE],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
