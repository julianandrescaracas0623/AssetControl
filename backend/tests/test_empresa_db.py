"""Tablas de la 0014 en la base (spec 013, T1; R1–R4; A2).

Con el **rol de la aplicación** sobre una base temporal con dos tenants:

- ``empresa``: una por tenant; NIT con formato; la de otro tenant no se ve ni se escribe.
- ``empresa_logo``: solo se inserta y se lee; nunca se cambia ni se borra.
- ``sesion_empresa`` y ``sesion_detalle``: solo para sesiones **cerradas**, solo
  ``INSERT``/``SELECT``; un activo una vez por sesión; encontrado ⇔ estado y ubicación.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from acceso_db import ADMIN_A, ADMIN_B, TENANT_A, TENANT_B, AccesoDb, temporary_acceso_db
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

INSUFFICIENT_PRIVILEGE = "42501"
UNIQUE_VIOLATION = "23505"
CHECK_VIOLATION = "23514"
FOREIGN_KEY_VIOLATION = "23503"
SESION_ABIERTA = "P0004"
RLS_VIOLATION = "42501"


@pytest.fixture(scope="module")
def db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("empresa")


@pytest.fixture(scope="module")
def base(db) -> dict[str, uuid.UUID]:
    ids = {n: uuid.uuid4() for n in ("sede", "sala", "cat", "act", "abierta", "cerrada")}
    with db.migrator.begin() as conn:
        conn.execute(
            text(
                "insert into ubicacion (id, tenant_id, nombre, nombre_clave, tipo, padre_id) "
                "values (:s, :t, 'Sede', 'sede', 'sede', null), "
                "(:a, :t, 'Sala', 'sala', 'sala', :s)"
            ),
            {"s": ids["sede"], "a": ids["sala"], "t": TENANT_A},
        )
        conn.execute(
            text(
                "insert into categoria (id, tenant_id, nombre, nombre_clave) "
                "values (:c, :t, 'Cat', 'cat')"
            ),
            {"c": ids["cat"], "t": TENANT_A},
        )
        conn.execute(
            text(
                "insert into activo (id, tenant_id, codigo, nombre, categoria_id, "
                "ubicacion_id, precio_compra, creado_por) "
                "values (:id, :t, 'AC-1', 'Autoclave', :c, :u, 100, :p)"
            ),
            {
                "id": ids["act"],
                "t": TENANT_A,
                "c": ids["cat"],
                "u": ids["sala"],
                "p": ADMIN_A.usuario_id,
            },
        )
        for clave in ("cerrada", "abierta"):  # una sola abierta por tenant: primero se cierra
            conn.execute(
                text(
                    "insert into sesion_conteo (id, tenant_id, nombre, fecha_corte, abierta_por) "
                    "values (:s, :t, :n, date '2026-11-30', :p)"
                ),
                {"s": ids[clave], "t": TENANT_A, "n": clave, "p": ADMIN_A.usuario_id},
            )
            if clave == "cerrada":
                conn.execute(
                    text(
                        "update sesion_conteo set estado = 'cerrada', cerrada_por = :p, "
                        "cerrada_en = now(), total_encontrado = 0, total_no_encontrado = 0, "
                        "total_registrado = 0 where id = :s"
                    ),
                    {"s": ids[clave], "p": ADMIN_A.usuario_id},
                )
    return ids


@contextmanager
def como_app(db: AccesoDb, tenant: uuid.UUID) -> Iterator[Connection]:
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


def falla(conn: Connection, sql: str, params: dict, esperado: str) -> None:
    with pytest.raises(DBAPIError) as raised:
        with conn.begin_nested():
            conn.execute(text(sql), params)
    assert getattr(raised.value.orig, "sqlstate", None) == esperado, raised.value


EMPRESA = (
    "insert into empresa (tenant_id, nombre, direccion, nit, telefono, correo, actualizada_por) "
    "values (:t, 'Clínica', 'Calle 1', :nit, null, null, :p)"
)
LOGO = (
    "insert into empresa_logo (id, tenant_id, clave, bytes, ancho, alto, subido_por) "
    "values (:id, :t, :k, 10, 60, 60, :p)"
)
DETALLE = (
    "insert into sesion_detalle (tenant_id, sesion_id, activo_id, codigo, nombre, categoria_id, "
    "categoria_nombre, ubicacion_id, ubicacion_ruta, encontrada_ruta, estado_fisico, "
    "encontrado, en_reparacion, precio) values (:t, :s, :a, 'AC-1', 'Autoclave', :c, 'Cat', "
    ":u, 'Sede › Sala', :er, :ef, :enc, false, 100)"
)
SESION_EMPRESA = (
    "insert into sesion_empresa (tenant_id, sesion_id, nombre, direccion) "
    "values (:t, :s, 'Clínica', 'Calle 1')"
)


def test_company_one_per_tenant_with_nit_format(db, base):
    with como_app(db, TENANT_A) as conn:
        p = {"t": TENANT_A, "p": ADMIN_A.usuario_id}
        for nit in ("1234567", "900.123.456-77", "900123456-7", "abc"):
            falla(conn, EMPRESA, {**p, "nit": nit}, CHECK_VIOLATION)
        conn.execute(text(EMPRESA), {**p, "nit": "900.123.456-7"})
        falla(conn, EMPRESA, {**p, "nit": None}, UNIQUE_VIOLATION)
        conn.execute(text("update empresa set nit = '900.123.456' where tenant_id = :t"), p)
        falla(conn, "delete from empresa", {}, INSUFFICIENT_PRIVILEGE)
        # Otro tenant: no ve la fila ni puede escribir con su tenant_id.
        falla(conn, EMPRESA, {"t": TENANT_B, "p": ADMIN_B.usuario_id, "nit": None}, RLS_VIOLATION)
    with como_app(db, TENANT_B) as conn:
        assert conn.scalar(text("select count(*) from empresa")) == 0


def test_logos_are_insert_only(db, base):
    with como_app(db, TENANT_A) as conn:
        logo = uuid.uuid4()
        conn.execute(
            text(LOGO),
            {"id": logo, "t": TENANT_A, "k": f"{TENANT_A}/{logo}.png", "p": ADMIN_A.usuario_id},
        )
        falla(conn, "update empresa_logo set bytes = 1", {}, INSUFFICIENT_PRIVILEGE)
        falla(conn, "delete from empresa_logo", {}, INSUFFICIENT_PRIVILEGE)
        p = {"t": TENANT_A, "p": ADMIN_A.usuario_id, "nit": None}
        conn.execute(text(EMPRESA), p)
        conn.execute(
            text("update empresa set logo_id = :l where tenant_id = :t"), {"l": logo, "t": TENANT_A}
        )
        falla(
            conn,
            "update empresa set logo_id = :l where tenant_id = :t",
            {"l": uuid.uuid4(), "t": TENANT_A},
            FOREIGN_KEY_VIOLATION,
        )


def test_frozen_tables_only_accept_closed_sessions(db, base):
    with como_app(db, TENANT_A) as conn:
        comun = {"t": TENANT_A, "a": base["act"], "c": base["cat"], "u": base["sala"]}
        encontrado = {"er": "Sede › Sala", "ef": "ok", "enc": True}
        falla(conn, DETALLE, {**comun, **encontrado, "s": base["abierta"]}, SESION_ABIERTA)
        falla(conn, SESION_EMPRESA, {"t": TENANT_A, "s": base["abierta"]}, SESION_ABIERTA)
        # encontrado ⇔ estado físico y ubicación encontrada.
        for incoherente in (
            {"er": None, "ef": "ok", "enc": True},
            {"er": "Sede › Sala", "ef": None, "enc": False},
        ):
            falla(conn, DETALLE, {**comun, **incoherente, "s": base["cerrada"]}, CHECK_VIOLATION)
        conn.execute(text(DETALLE), {**comun, **encontrado, "s": base["cerrada"]})
        falla(conn, DETALLE, {**comun, **encontrado, "s": base["cerrada"]}, UNIQUE_VIOLATION)
        conn.execute(text(SESION_EMPRESA), {"t": TENANT_A, "s": base["cerrada"]})
        falla(conn, SESION_EMPRESA, {"t": TENANT_A, "s": base["cerrada"]}, UNIQUE_VIOLATION)
        for sql in (
            "update sesion_detalle set nombre = 'x'",
            "delete from sesion_detalle",
            "update sesion_empresa set nombre = 'x'",
            "delete from sesion_empresa",
        ):
            falla(conn, sql, {}, INSUFFICIENT_PRIVILEGE)
    with como_app(db, TENANT_B) as conn:
        assert conn.scalar(text("select count(*) from sesion_detalle")) == 0
