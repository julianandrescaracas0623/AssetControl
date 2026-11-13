"""Pruebas del arnés de pruebas (spec 001, R7 / A7, T5).

- Fixtures ``app``, ``client`` y ``db_connection`` (``conftest.py``): la app usa el
  rol de la aplicación y todo lo que escribe queda dentro de una transacción
  externa que se revierte al terminar cada prueba.
- Riesgo de ``SET LOCAL`` con *savepoints* (plan.md §4): el tenant que fija
  ``tenant_session`` no sobrevive a su bloque dentro de la transacción externa.
- ``pytest`` dos veces seguidas sin residuos: lo que escribe una prueba no lo ve
  la siguiente, y el guardián de residuos falla si queda una tabla de prueba.
- Spec 002, T2: el guardián cuenta filas bajo FORCE RLS (o falla cerrado si no
  puede), detecta roles ``prueba_*`` sin borrar y falla si un rol ``prueba_*``
  es miembro de ``auth_owner`` (también un huérfano previo).
"""

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import String, create_engine, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import NullPool

from app.db import TenantScoped, tenant_session
from tests.conftest import (
    BLOCKED,
    _schema_snapshot,
    create_rls_tables,
    read_database_url,
    residue_problems,
    role_sees_all_rows,
)

BACKEND_DIR = Path(__file__).resolve().parent.parent
TENANT_A = uuid.UUID("00000000-0000-4000-8000-0000000000a5")
TENANT_B = uuid.UUID("00000000-0000-4000-8000-0000000000b5")
TABLE = "prueba_harness_t5"
RESIDUE_TABLE = "prueba_residuo_t5"


class HarnessBase(DeclarativeBase):
    """Metadata propia: no contamina la de la aplicación ni la de T3."""


class HarnessActivo(TenantScoped, HarnessBase):
    __tablename__ = TABLE

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(50))


def module_rls_table(metadata):
    """Fixture de módulo: crea las tablas de ``metadata`` con RLS forzada y las borra al final.

    Dura más que una prueba a propósito: así se comprueba que las filas de una
    prueba no llegan a la siguiente por el rollback, no porque la tabla se recree.
    """

    @pytest.fixture(scope="module")
    def _table(database_residue_guard) -> Iterator[None]:
        migration_url = read_database_url("TEST_MIGRATION_DATABASE_URL")
        app_url = read_database_url("TEST_DATABASE_URL")
        if migration_url is None or app_url is None:
            pytest.fail(BLOCKED, pytrace=False)
        migrator = create_engine(migration_url, poolclass=NullPool)
        failure = None
        try:
            with migrator.begin() as conn:
                create_rls_tables(conn, metadata, app_url.username)
        except OperationalError as exc:
            failure = f"{BLOCKED} (rol migrador: {type(exc.orig).__name__})"
        if failure is not None:
            migrator.dispose()
            pytest.fail(failure, pytrace=False)
        try:
            yield
        finally:
            with migrator.begin() as conn:
                metadata.drop_all(conn)
            migrator.dispose()

    return _table


harness_table = module_rls_table(HarnessBase.metadata)


@pytest.fixture
def table_app(harness_table, app):
    return app


@pytest.fixture
def committed_reader(app_database_url) -> Iterator[Engine]:
    """Engine propio del rol de la aplicación: solo ve lo confirmado."""
    engine = create_engine(app_database_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


def count_as(conn, tenant_id) -> int:
    conn.execute(
        text("select set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )
    return conn.scalar(text(f"select count(*) from {TABLE}"))  # noqa: S608 - nombre fijo


def count_in_session(tenant_id) -> int:
    with tenant_session(tenant_id) as session:
        return session.scalar(select(func.count()).select_from(HarnessActivo))


def tenant_setting(conn) -> str | None:
    return conn.scalar(text("select current_setting('app.tenant_id', true)"))


# --- Fixtures de app y cliente HTTP ----------------------------------------


def test_app_fixture_connects_with_the_app_role(app, db_connection, app_database_url):
    current_user, is_super = db_connection.execute(
        text("select current_user, rolsuper from pg_roles where rolname = current_user")
    ).one()

    assert app.testing is True
    assert current_user == app_database_url.username
    assert is_super is False


def test_db_connection_is_inside_an_open_transaction(db_connection):
    assert db_connection.in_transaction() is True
    assert db_connection.scalar(text("select now() = statement_timestamp()")) is False


def test_client_fixture_serves_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.get_json()["db"] == "ok"


# --- Transacción con rollback por prueba -----------------------------------


def test_tenant_session_writes_stay_inside_the_test_transaction(table_app, committed_reader):
    with tenant_session(TENANT_A) as session:
        session.add(HarnessActivo(nombre="silla"))

    assert count_in_session(TENANT_A) == 1
    with committed_reader.begin() as conn:
        assert count_as(conn, TENANT_A) == 0


def test_tenant_session_failure_rolls_back_only_its_block(table_app):
    with tenant_session(TENANT_A) as session:
        session.add(HarnessActivo(nombre="silla"))

    with pytest.raises(RuntimeError, match="falla a propósito"):
        with tenant_session(TENANT_A) as session:
            session.add(HarnessActivo(nombre="mesa"))
            session.flush()
            raise RuntimeError("falla a propósito")

    assert count_in_session(TENANT_A) == 1


def test_rls_still_isolates_tenants_inside_the_test_transaction(table_app):
    with tenant_session(TENANT_A) as session:
        session.add(HarnessActivo(nombre="silla"))
    with tenant_session(TENANT_B) as session:
        session.add_all([HarnessActivo(nombre="autoclave"), HarnessActivo(nombre="lampara")])

    assert count_in_session(TENANT_A) == 1
    assert count_in_session(TENANT_B) == 2


# --- SET LOCAL y savepoints (plan.md §4) -----------------------------------


def test_tenant_does_not_survive_tenant_session_in_the_test_transaction(table_app, db_connection):
    """Sin el arnés, el ``RELEASE SAVEPOINT`` dejaría el tenant A en la transacción externa."""
    with tenant_session(TENANT_A) as session:
        session.add(HarnessActivo(nombre="silla"))

    assert tenant_setting(db_connection) in ("", None)
    assert db_connection.scalar(text(f"select count(*) from {TABLE}")) == 0  # noqa: S608


def test_tenant_does_not_survive_a_failed_tenant_session(table_app, db_connection):
    with tenant_session(TENANT_A) as session:
        session.add(HarnessActivo(nombre="silla"))
    with pytest.raises(RuntimeError):
        with tenant_session(TENANT_A):
            raise RuntimeError("falla a propósito")

    assert tenant_setting(db_connection) in ("", None)
    assert db_connection.scalar(text(f"select count(*) from {TABLE}")) == 0  # noqa: S608


def test_next_tenant_session_sees_only_its_tenant(table_app):
    with tenant_session(TENANT_A) as session:
        session.add(HarnessActivo(nombre="silla"))

    with tenant_session(TENANT_B) as session:
        assert session.scalar(select(func.current_setting("app.tenant_id", True))) == str(TENANT_B)
        assert session.scalars(select(HarnessActivo.nombre)).all() == []


# --- Dos corridas sin residuos ---------------------------------------------

ACROSS_TESTS_PROBE = """
import uuid

import pytest
from sqlalchemy import String, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db import TenantScoped, tenant_session
from tests.test_harness import module_rls_table

TENANT = uuid.UUID("00000000-0000-4000-8000-0000000000c5")


class ProbeBase(DeclarativeBase):
    pass


class ProbeActivo(TenantScoped, ProbeBase):
    __tablename__ = "prueba_probe_t5"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(String(50))


probe_table = module_rls_table(ProbeBase.metadata)


@pytest.fixture
def probe_app(probe_table, app):
    return app


def contar():
    with tenant_session(TENANT) as session:
        return session.scalar(select(func.count()).select_from(ProbeActivo))


def test_1_escribe(probe_app):
    assert contar() == 0
    with tenant_session(TENANT) as session:
        session.add(ProbeActivo(nombre="silla"))
    assert contar() == 1


def test_2_no_ve_lo_de_la_anterior(probe_app):
    assert contar() == 0
"""

RESIDUE_PROBE = f"""
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool


def test_deja_una_tabla(database_residue_guard, migration_database_url):
    engine = create_engine(migration_database_url, poolclass=NullPool)
    with engine.begin() as conn:
        conn.execute(text("create table {RESIDUE_TABLE} (id int)"))
    engine.dispose()
"""


def run_probe(tmp_path: Path, source: str) -> str:
    probe = tmp_path / "test_arnes_probe.py"
    probe.write_text(source, encoding="utf-8")
    result = subprocess.run(  # noqa: S603 - comando fijo, sin entrada externa
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-p",
            "tests.conftest",
            "--rootdir",
            str(tmp_path),
            "-q",
            str(probe),
        ],
        cwd=BACKEND_DIR,
        env=dict(os.environ),
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout + result.stderr


def test_writes_of_one_test_do_not_reach_the_next_twice_in_a_row(tmp_path):
    first = run_probe(tmp_path, ACROSS_TESTS_PROBE)
    second = run_probe(tmp_path, ACROSS_TESTS_PROBE)

    for output in (first, second):
        assert "2 passed" in output, output
        assert "error" not in output.lower(), output


def test_residue_guard_fails_when_a_test_table_is_left_behind(tmp_path, migration_database_url):
    migrator = create_engine(migration_database_url, poolclass=NullPool)
    try:
        output = run_probe(tmp_path, RESIDUE_PROBE)
    finally:
        with migrator.begin() as conn:
            conn.execute(text(f"drop table if exists {RESIDUE_TABLE}"))
        migrator.dispose()

    assert "1 passed, 1 error" in output, output
    assert "residuos" in output
    assert RESIDUE_TABLE in output


# --- Guardián de residuos bajo FORCE RLS (spec 002, T2; plan.md §7.6) -------

GUARD_TABLE = "prueba_guardian_t2"


class GuardBase(DeclarativeBase):
    """Metadata propia de la prueba del guardián."""


class GuardActivo(TenantScoped, GuardBase):
    __tablename__ = GUARD_TABLE

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


def _snapshot(**overrides):
    base = {"tables": [], "policies": [], "rows": {}, "roles": [], "rows_complete": True}
    base.update(overrides)
    return base


def test_residue_guard_counts_rows_of_every_tenant_under_force_rls(
    migration_database_url, app_database_url
):
    migrator = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with migrator.begin() as conn:
            create_rls_tables(conn, GuardBase.metadata, app_database_url.username)
            for tenant in (TENANT_A, TENANT_B):
                conn.execute(
                    text(f"insert into {GUARD_TABLE} (id, tenant_id) values (:id, :t)"),  # noqa: S608
                    {"id": uuid.uuid4(), "t": tenant},
                )
        snapshot = _schema_snapshot(migration_database_url)
    finally:
        with migrator.begin() as conn:
            GuardBase.metadata.drop_all(conn)
        migrator.dispose()

    assert snapshot is not None
    assert snapshot["rows_complete"] is True
    # Sin app.tenant_id: con FORCE RLS y un rol que no se la salta, daría 0.
    assert snapshot["rows"][GUARD_TABLE] == 2


def test_role_sees_all_rows_is_false_for_a_role_under_rls(migration_database_url, app_database_url):
    migrator = create_engine(migration_database_url, poolclass=NullPool)
    preparer = migrator.dialect.identifier_preparer
    try:
        with migrator.begin() as conn:
            assert role_sees_all_rows(conn) is True
            conn.exec_driver_sql(f"SET LOCAL ROLE {preparer.quote(app_database_url.username)}")
            assert role_sees_all_rows(conn) is False
    finally:
        migrator.dispose()


def test_residue_guard_fails_closed_when_it_cannot_count_rows():
    problems = residue_problems(_snapshot(rows_complete=False), _snapshot(rows_complete=False))
    assert any("FORCE RLS" in problem for problem in problems)


def test_residue_guard_detects_rows_left_in_a_business_table():
    before = _snapshot(tables=[("membresia", "r")], rows={"membresia": 0})
    after = _snapshot(tables=[("membresia", "r")], rows={"membresia": 1})
    assert residue_problems(before, after) != []


def test_residue_guard_detects_a_test_role_left_behind():
    before = _snapshot(roles=["prueba_de_otro_proceso"])
    after = _snapshot(roles=["prueba_de_otro_proceso", "prueba_dueno_abc"])
    assert residue_problems(before, after) == ["rol de prueba sin borrar: prueba_dueno_abc"]


def test_residue_guard_detects_a_new_auth_owner_membership():
    # Las membresías son de todo el clúster: borrar la base temporal no las quita.
    before = _snapshot(memberships=[])
    after = _snapshot(memberships=[("auth_owner", "assetcontrol_app")])
    problems = residue_problems(before, after)
    assert len(problems) == 1
    assert "auth_owner" in problems[0]


def test_residue_snapshot_lists_no_auth_owner_membership(migration_database_url):
    snapshot = _schema_snapshot(migration_database_url)
    assert snapshot is not None
    assert snapshot["memberships"] == []


def test_residue_guard_fails_on_an_orphan_test_member_of_auth_owner():
    # Huérfano de una corrida anterior: está antes y después; igual falla (I1).
    orphan = [("auth_owner", "prueba_dueno_huerfano")]
    problems = residue_problems(_snapshot(memberships=orphan), _snapshot(memberships=orphan))
    assert problems == ["rol de prueba miembro de auth_owner: prueba_dueno_huerfano"]


def _role_exists(conn, name: str) -> bool:
    return bool(conn.scalar(text("select count(*) from pg_roles where rolname = :n"), {"n": name}))


def test_residue_snapshot_detects_a_real_test_member_of_auth_owner(migration_database_url):
    name = f"prueba_miembro_{uuid.uuid4().hex[:10]}"
    admin = create_engine(migration_database_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    quoted = admin.dialect.identifier_preparer.quote(name)
    try:
        with admin.connect() as conn:
            conn.exec_driver_sql(f"CREATE ROLE {quoted} NOLOGIN")
            conn.exec_driver_sql(f"GRANT auth_owner TO {quoted}")
        snapshot = _schema_snapshot(migration_database_url)
    finally:
        with admin.connect() as conn:
            conn.exec_driver_sql(f"DROP ROLE IF EXISTS {quoted}")
            left = _role_exists(conn, name)
        admin.dispose()

    assert left is False
    assert snapshot is not None
    assert ("auth_owner", name) in snapshot["memberships"]
    problems = residue_problems(_snapshot(), snapshot)
    assert f"rol de prueba miembro de auth_owner: {name}" in problems
