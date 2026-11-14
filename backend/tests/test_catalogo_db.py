"""Ubicaciones y categorías en la base (spec 003, T1; R1–R3, A1; plan.md §2).

Comportamiento real con el **rol de la aplicación** sobre una base temporal migrada a
``head`` con dos tenants sintéticos (A y B), por SQL crudo con ``app.tenant_id``
fijado como lo hace ``tenant_session``:

- RLS: cada tenant ve y escribe solo lo suyo; un ``INSERT`` con otro ``tenant_id``
  falla.
- La FK compuesta impide un padre de otro tenant aunque se conozca su ``id``.
- ``CHECK``: solo la sede no tiene padre.
- Únicos por ``nombre_clave``: entre sedes del tenant, entre hermanas y en
  categorías; el mismo nombre en otro padre o en otro tenant sí se permite.
- Sin ``DELETE`` ni ``UPDATE`` de ``tenant_id``, ``tipo`` o ``padre_id``.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from acceso_db import TENANT_A, TENANT_B, AccesoDb, temporary_acceso_db
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

INSUFFICIENT_PRIVILEGE = "42501"
FOREIGN_KEY_VIOLATION = "23503"
UNIQUE_VIOLATION = "23505"
CHECK_VIOLATION = "23514"


@pytest.fixture(scope="module")
def cat_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("catalogo")


@contextmanager
def como_app(db: AccesoDb, tenant: uuid.UUID) -> Iterator[Connection]:
    """Transacción del rol de la aplicación con el tenant fijado (se revierte al salir)."""
    engine = create_engine(db.app_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            trans = conn.begin()
            conn.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
            try:
                yield conn
            finally:
                trans.rollback()
    finally:
        engine.dispose()


def sqlstate(exc: DBAPIError) -> str | None:
    return getattr(exc.orig, "sqlstate", None)


def falla(conn: Connection, sql: str, params: dict, esperado: str) -> None:
    with pytest.raises(DBAPIError) as raised:
        with conn.begin_nested():
            conn.execute(text(sql), params)
    assert sqlstate(raised.value) == esperado, raised.value


INSERT_UBI = (
    "insert into ubicacion (tenant_id, nombre, nombre_clave, tipo, padre_id) "
    "values (:t, :n, :k, :tipo, :p) returning id"
)


def crear(conn: Connection, tenant, nombre, tipo, padre=None) -> uuid.UUID:
    clave = nombre.lower()
    params = {"t": tenant, "n": nombre, "k": clave, "tipo": tipo, "p": padre}
    return conn.execute(text(INSERT_UBI), params).scalar_one()


def test_each_tenant_sees_and_writes_only_its_own(cat_db):
    with como_app(cat_db, TENANT_B) as conn:
        crear(conn, TENANT_B, "Sede B", "sede")
        conn.execute(
            text(
                "insert into categoria (tenant_id, nombre, nombre_clave) values (:t, 'CPU', 'cpu')"
            ),
            {"t": TENANT_B},
        )
        assert conn.scalar(text("select count(*) from ubicacion")) == 1

    with como_app(cat_db, TENANT_A) as conn:
        sede = crear(conn, TENANT_A, "Sede A", "sede")
        assert conn.execute(text("select id from ubicacion")).scalars().all() == [sede]
        assert conn.scalar(text("select count(*) from categoria")) == 0
        falla(
            conn,
            INSERT_UBI,
            {"t": TENANT_B, "n": "Intrusa", "k": "intrusa", "tipo": "sede", "p": None},
            INSUFFICIENT_PRIVILEGE,
        )


def test_parent_of_another_tenant_is_rejected_even_knowing_its_id(cat_db):
    with cat_db.migrator.begin() as conn:
        sede_b = conn.execute(
            text(INSERT_UBI),
            {"t": TENANT_B, "n": "Sede B2", "k": "sede b2", "tipo": "sede", "p": None},
        ).scalar_one()
    try:
        with como_app(cat_db, TENANT_A) as conn:
            falla(
                conn,
                INSERT_UBI,
                {"t": TENANT_A, "n": "Sala", "k": "sala", "tipo": "sala", "p": sede_b},
                FOREIGN_KEY_VIOLATION,
            )
    finally:
        with cat_db.migrator.begin() as conn:
            conn.execute(text("delete from ubicacion where id = :id"), {"id": sede_b})


@pytest.mark.parametrize(
    ("tipo", "con_padre"),
    [("sede", True), ("sala", False), ("box", False)],
)
def test_only_a_sede_has_no_parent(cat_db, tipo, con_padre):
    with como_app(cat_db, TENANT_A) as conn:
        sede = crear(conn, TENANT_A, "Sede", "sede")
        params = {"t": TENANT_A, "n": "X", "k": "x", "tipo": tipo, "p": sede if con_padre else None}
        falla(conn, INSERT_UBI, params, CHECK_VIOLATION)


def test_names_are_unique_among_siblings_by_key(cat_db):
    with como_app(cat_db, TENANT_A) as conn:
        norte = crear(conn, TENANT_A, "Norte", "sede")
        sur = crear(conn, TENANT_A, "Sur", "sede")
        falla(
            conn,
            INSERT_UBI,
            {"t": TENANT_A, "n": "NORTE", "k": "norte", "tipo": "sede", "p": None},
            UNIQUE_VIOLATION,
        )
        crear(conn, TENANT_A, "Recepción", "sala", norte)
        crear(conn, TENANT_A, "Recepción", "sala", sur)  # otro padre: permitido
        falla(
            conn,
            INSERT_UBI,
            {"t": TENANT_A, "n": "Recepción", "k": "recepción", "tipo": "sala", "p": norte},
            UNIQUE_VIOLATION,
        )

    with como_app(cat_db, TENANT_B) as conn:
        crear(conn, TENANT_B, "Norte", "sede")  # otro tenant: permitido


def test_category_keys_are_unique_per_tenant(cat_db):
    sql = "insert into categoria (tenant_id, nombre, nombre_clave) values (:t, :n, :k)"
    with como_app(cat_db, TENANT_A) as conn:
        conn.execute(text(sql), {"t": TENANT_A, "n": "Biomédicos", "k": "biomedicos"})
        falla(conn, sql, {"t": TENANT_A, "n": "BIOMEDICOS", "k": "biomedicos"}, UNIQUE_VIOLATION)
    with como_app(cat_db, TENANT_B) as conn:
        conn.execute(text(sql), {"t": TENANT_B, "n": "Biomédicos", "k": "biomedicos"})


@pytest.mark.parametrize(
    "sql",
    [
        "delete from ubicacion",
        "delete from categoria",
        "truncate ubicacion",
        "update ubicacion set tenant_id = tenant_id",
        "update ubicacion set tipo = tipo",
        "update ubicacion set padre_id = padre_id",
        "update categoria set tenant_id = tenant_id",
        "insert into ubicacion (id, tenant_id, nombre, nombre_clave, tipo) "
        "values (gen_random_uuid(), :t, 'X', 'x', 'sede')",
    ],
)
def test_app_cannot_delete_nor_change_identity_columns(cat_db, sql):
    with como_app(cat_db, TENANT_A) as conn:
        falla(conn, sql, {"t": TENANT_A}, INSUFFICIENT_PRIVILEGE)


def test_app_can_rename_and_deactivate(cat_db):
    with como_app(cat_db, TENANT_A) as conn:
        sede = crear(conn, TENANT_A, "Vieja", "sede")
        conn.execute(
            text(
                "update ubicacion set nombre = 'Nueva', nombre_clave = 'nueva', activa = false "
                "where id = :id"
            ),
            {"id": sede},
        )
        fila = conn.execute(
            text("select nombre, activa from ubicacion where id = :id"), {"id": sede}
        )
        assert fila.one() == ("Nueva", False)


@pytest.mark.parametrize("nombre", ["", "x" * 121])
def test_name_length_is_checked_by_the_database(cat_db, nombre):
    with como_app(cat_db, TENANT_A) as conn:
        params = {"t": TENANT_A, "n": nombre, "k": "k", "tipo": "sede", "p": None}
        falla(conn, INSERT_UBI, params, CHECK_VIOLATION)
