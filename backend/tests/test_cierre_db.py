"""Cierre e informe congelado en la base (spec 008, T1; R2, R5, Q3; A1).

Con el **rol de la aplicación** sobre una base temporal con dos tenants:

- ``sesion_conteo``: cerrada ⇔ totales; registrado = encontrado + no encontrado; solo
  ``abierta → cerrada`` (disparador): una sesión cerrada no se modifica ni se reabre.
- ``sesion_desglose`` y ``sesion_no_encontrado``: solo con la sesión ya cerrada, solo
  ``INSERT`` (inmutables), dimensión coherente, sumas, únicos y referencias del tenant.
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
FOREIGN_KEY_VIOLATION = "23503"
UNIQUE_VIOLATION = "23505"
CHECK_VIOLATION = "23514"
SESION_CERRADA = "P0003"
SESION_ABIERTA = "P0004"


@pytest.fixture(scope="module")
def db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("cierre")


@pytest.fixture(scope="module")
def base(db) -> dict[str, uuid.UUID]:
    ids = {
        n: uuid.uuid4()
        for n in ("sede", "sala", "cat", "act", "sede_b", "sala_b", "cat_b", "act_b")
    }
    with db.migrator.begin() as conn:
        for sufijo, tenant, admin in (("", TENANT_A, ADMIN_A), ("_b", TENANT_B, ADMIN_B)):
            conn.execute(
                text(
                    "insert into ubicacion (id, tenant_id, nombre, nombre_clave, tipo, padre_id) "
                    "values (:s, :t, 'Sede', 'sede', 'sede', null), "
                    "(:a, :t, 'Sala', 'sala', 'sala', :s)"
                ),
                {"s": ids[f"sede{sufijo}"], "a": ids[f"sala{sufijo}"], "t": tenant},
            )
            conn.execute(
                text(
                    "insert into categoria (id, tenant_id, nombre, nombre_clave) "
                    "values (:c, :t, 'Cat', 'cat')"
                ),
                {"c": ids[f"cat{sufijo}"], "t": tenant},
            )
            conn.execute(
                text(
                    "insert into activo (id, tenant_id, codigo, nombre, categoria_id, "
                    "ubicacion_id, precio_compra, creado_por) "
                    "values (:id, :t, 'AC-1', 'Autoclave', :c, :u, 100, :p)"
                ),
                {
                    "id": ids[f"act{sufijo}"],
                    "t": tenant,
                    "c": ids[f"cat{sufijo}"],
                    "u": ids[f"sala{sufijo}"],
                    "p": admin.usuario_id,
                },
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


def abrir(conn: Connection) -> uuid.UUID:
    return conn.scalar(
        text(
            "insert into sesion_conteo (tenant_id, nombre, fecha_corte, abierta_por) "
            "values (:t, 'Conteo', date '2026-11-30', :p) returning id"
        ),
        {"t": TENANT_A, "p": ADMIN_A.usuario_id},
    )


CERRAR = (
    "update sesion_conteo set estado = 'cerrada', cerrada_en = now(), cerrada_por = :p, "
    "total_encontrado = :e, total_no_encontrado = :n, total_registrado = :r where id = :s"
)
DESGLOSE = (
    "insert into sesion_desglose (tenant_id, sesion_id, dimension, categoria_id, ubicacion_id, "
    "etiqueta, total_encontrado, total_no_encontrado, total_registrado, unidades_encontrado, "
    "unidades_no_encontrado, unidades_registrado) values (:t, :s, :d, :c, :u, :etiqueta, "
    ":te, :tn, :tr, :ue, :un, :ur)"
)
NO_ENCONTRADO = (
    "insert into sesion_no_encontrado (tenant_id, sesion_id, activo_id, codigo, nombre, "
    "categoria_id, categoria_nombre, ubicacion_id, ubicacion_ruta, precio, en_reparacion) "
    "values (:t, :s, :a, 'AC-1', 'Autoclave', :c, 'Cat', :u, 'Sala', :precio, :rep)"
)


def cierre(sesion, **c) -> dict:
    return {"s": sesion, "p": ADMIN_A.usuario_id, "e": 60, "n": 40, "r": 100, **c}


def fila(base, sesion, **c) -> dict:
    return {
        "t": TENANT_A,
        "s": sesion,
        "d": "categoria",
        "c": base["cat"],
        "u": None,
        "etiqueta": "Cat",
        "te": 60,
        "tn": 40,
        "tr": 100,
        "ue": 1,
        "un": 1,
        "ur": 2,
        **c,
    }


def falta(base, sesion, **c) -> dict:
    return {
        "t": TENANT_A,
        "s": sesion,
        "a": base["act"],
        "c": base["cat"],
        "u": base["sala"],
        "precio": 40,
        "rep": False,
        **c,
    }


def test_close_sets_totals_and_then_nothing_changes(db, base):
    with como_app(db, TENANT_A) as conn:
        sesion = abrir(conn)
        conn.execute(text(CERRAR), cierre(sesion))
        for sql in (
            "update sesion_conteo set total_encontrado = 0, total_registrado = 40 where id = :s",
            "update sesion_conteo set estado = 'abierta', cerrada_en = null, cerrada_por = null, "
            "total_encontrado = null, total_no_encontrado = null, total_registrado = null "
            "where id = :s",
            "update sesion_conteo set cerrada_en = now() where id = :s",
        ):
            falla(conn, sql, {"s": sesion}, SESION_CERRADA)


@pytest.mark.parametrize(
    "cambio",
    [{"e": None}, {"r": 99}, {"e": -1, "r": 39}, {"n": None, "r": 60}],
)
def test_totals_are_checked(db, base, cambio):
    with como_app(db, TENANT_A) as conn:
        sesion = abrir(conn)
        falla(conn, CERRAR, cierre(sesion, **cambio), CHECK_VIOLATION)


def test_an_open_session_cannot_get_totals_or_be_touched_otherwise(db, base):
    with como_app(db, TENANT_A) as conn:
        sesion = abrir(conn)
        falla(
            conn,
            "update sesion_conteo set total_encontrado = 1 where id = :s",
            {"s": sesion},
            SESION_CERRADA,
        )
        falla(
            conn,
            "update sesion_conteo set nombre = 'x' where id = :s",
            {"s": sesion},
            INSUFFICIENT_PRIVILEGE,
        )


def test_breakdown_and_list_only_for_closed_sessions(db, base):
    with como_app(db, TENANT_A) as conn:
        sesion = abrir(conn)
        falla(conn, DESGLOSE, fila(base, sesion), SESION_ABIERTA)
        falla(conn, NO_ENCONTRADO, falta(base, sesion), SESION_ABIERTA)
        conn.execute(text(CERRAR), cierre(sesion))
        conn.execute(text(DESGLOSE), fila(base, sesion))
        conn.execute(
            text(DESGLOSE),
            fila(base, sesion, d="ubicacion", c=None, u=base["sala"], etiqueta="Sala"),
        )
        conn.execute(text(NO_ENCONTRADO), falta(base, sesion, rep=True))
        # Una vez: únicos por categoría, ubicación y activo.
        falla(conn, DESGLOSE, fila(base, sesion), UNIQUE_VIOLATION)
        falla(
            conn,
            DESGLOSE,
            fila(base, sesion, d="ubicacion", c=None, u=base["sala"]),
            UNIQUE_VIOLATION,
        )
        falla(conn, NO_ENCONTRADO, falta(base, sesion), UNIQUE_VIOLATION)


@pytest.mark.parametrize(
    "cambio",
    [
        {"d": "categoria", "u": "sala"},
        {"d": "ubicacion"},
        {"d": "otra"},
        {"tr": 99},
        {"ur": 3},
        {"te": -1, "tr": 39},
        {"etiqueta": ""},
    ],
)
def test_breakdown_rows_are_checked(db, base, cambio):
    valores = {k: (base[v] if k == "u" else v) for k, v in cambio.items()}
    with como_app(db, TENANT_A) as conn:
        sesion = abrir(conn)
        conn.execute(text(CERRAR), cierre(sesion))
        falla(conn, DESGLOSE, fila(base, sesion, **valores), CHECK_VIOLATION)


@pytest.mark.parametrize("campo", ["a", "c", "u"])
def test_references_of_another_tenant_fail(db, base, campo):
    otros = {"a": base["act_b"], "c": base["cat_b"], "u": base["sala_b"]}
    with como_app(db, TENANT_A) as conn:
        sesion = abrir(conn)
        conn.execute(text(CERRAR), cierre(sesion))
        falla(
            conn, NO_ENCONTRADO, falta(base, sesion, **{campo: otros[campo]}), FOREIGN_KEY_VIOLATION
        )


@pytest.mark.parametrize(
    "sql",
    [
        "update sesion_desglose set total_encontrado = 0",
        "delete from sesion_desglose",
        "truncate sesion_desglose",
        "update sesion_no_encontrado set precio = 0",
        "delete from sesion_no_encontrado",
        "truncate sesion_no_encontrado",
        "delete from sesion_conteo",
    ],
)
def test_frozen_rows_are_immutable_for_the_app(db, base, sql):
    with como_app(db, TENANT_A) as conn:
        falla(conn, sql, {}, INSUFFICIENT_PRIVILEGE)


@pytest.mark.parametrize("funcion", ["sesion_conteo_inmutable", "conteo_cerrado_requerido"])
def test_trigger_functions_are_invoker_with_fixed_search_path(db, funcion):
    with db.migrator.connect() as conn:
        fila_ = conn.execute(
            text(
                "select p.prosecdef, p.proconfig, "
                "has_function_privilege('public', p.oid, 'EXECUTE') "
                "from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                "where n.nspname = 'public' and p.proname = :f"
            ),
            {"f": funcion},
        ).one()
    assert fila_ == (False, ["search_path=pg_catalog, pg_temp"], False)
