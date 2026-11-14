"""Sesiones de conteo y verificaciones en la base (spec 006, T1; R1, R4–R7, Q1, Q2; A1).

Con el **rol de la aplicación** sobre una base temporal con dos tenants (A y B):

- ``sesion_conteo``: una sola sesión ``conteo`` abierta por tenant (Q1); cerrada exige
  ``cerrada_en``; ``UPDATE`` solo de las columnas del cierre (spec 008, 0011).
- ``verificacion``: inmutable (solo ``INSERT`` y ``SELECT``); ``estado_fisico`` de Q2;
  precio ``>= 0``; nota de 1 a 120; ``seq`` y ``recibido_en`` los pone la base.
- FK compuestas: sesión, activo, ubicaciones, categoría y autor del mismo tenant.
- ``activo_evento.sesion_id`` y ``verificacion_id`` ya tienen FK.
- Spec 007, T1 (0010): ``discrepancia_descartada`` y una sola resolución
  (``ubicacion_cambiada`` o ``discrepancia_descartada``) por verificación.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal

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


@pytest.fixture(scope="module")
def con_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("conteo")


@pytest.fixture(scope="module")
def base(con_db) -> dict[str, uuid.UUID]:
    """Por tenant: sede > sala, categoría y un activo en la sala."""
    ids = {
        n: uuid.uuid4()
        for n in ("sede", "sala", "cat", "act", "sede_b", "sala_b", "cat_b", "act_b")
    }
    with con_db.migrator.begin() as conn:
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


ABRIR = (
    "insert into sesion_conteo (tenant_id, nombre, fecha_corte, abierta_por) "
    "values (:t, :n, date '2026-11-30', :p) returning id"
)
VERIFICAR = (
    "insert into verificacion (id, tenant_id, sesion_id, activo_id, ubicacion_esperada_id, "
    "ubicacion_encontrada_id, estado_fisico, precio_al_contar, categoria_al_contar, nota, "
    "verificado_por) values (:id, :t, :s, :a, :ue, :uf, :ef, :precio, :c, :nota, :p)"
)


def abrir(conn: Connection, tenant=TENANT_A, admin=ADMIN_A) -> uuid.UUID:
    return conn.scalar(text(ABRIR), {"t": tenant, "n": "Conteo", "p": admin.usuario_id})


def verificacion(base, sesion, **cambios) -> dict:
    p = {
        "id": uuid.uuid4(),
        "t": TENANT_A,
        "s": sesion,
        "a": base["act"],
        "ue": base["sala"],
        "uf": base["sala"],
        "ef": "ok",
        "precio": Decimal("100.00"),
        "c": base["cat"],
        "nota": None,
        "p": ADMIN_A.usuario_id,
    }
    return {**p, **cambios}


def test_open_session_defaults_and_one_open_per_tenant(con_db, base):
    with como_app(con_db, TENANT_A) as conn:
        sesion = abrir(conn)
        fila = conn.execute(
            text("select tipo, estado, cerrada_en from sesion_conteo where id = :s"), {"s": sesion}
        ).one()
        assert fila == ("conteo", "abierta", None)
        falla(conn, ABRIR, {"t": TENANT_A, "n": "Otra", "p": ADMIN_A.usuario_id}, UNIQUE_VIOLATION)
    with como_app(con_db, TENANT_B) as conn_b:
        abrir(conn_b, TENANT_B, ADMIN_B)


def test_closed_requires_closed_at(con_db, base):
    with con_db.migrator.begin() as conn:
        with pytest.raises(DBAPIError) as raised:
            conn.execute(
                text(
                    "insert into sesion_conteo (tenant_id, nombre, fecha_corte, abierta_por, "
                    "estado, total_encontrado, total_no_encontrado, total_registrado) "
                    "values (:t, 'x', date '2026-11-30', :p, 'cerrada', 0, 0, 0)"
                ),
                {"t": TENANT_A, "p": ADMIN_A.usuario_id},
            )
        assert getattr(raised.value.orig, "sqlstate", None) == CHECK_VIOLATION


def test_verification_defaults_and_checks(con_db, base):
    with como_app(con_db, TENANT_A) as conn:
        sesion = abrir(conn)
        p = verificacion(base, sesion, nota="Rayón en la tapa")
        conn.execute(text(VERIFICAR), p)
        fila = conn.execute(
            text("select seq is not null, recibido_en is not null from verificacion where id = :i"),
            {"i": p["id"]},
        ).one()
        assert fila == (True, True)
        for cambio in (
            {"ef": "regular"},
            {"precio": Decimal("-1")},
            {"nota": ""},
            {"nota": "x" * 121},
        ):
            falla(conn, VERIFICAR, verificacion(base, sesion, **cambio), CHECK_VIOLATION)
        falla(conn, VERIFICAR, verificacion(base, sesion, id=p["id"]), UNIQUE_VIOLATION)


@pytest.mark.parametrize("campo", ["a", "ue", "uf", "c", "p", "s"])
def test_references_of_another_tenant_fail(con_db, base, campo):
    otros = {
        "a": base["act_b"],
        "ue": base["sala_b"],
        "uf": base["sala_b"],
        "c": base["cat_b"],
        "p": ADMIN_B.usuario_id,
    }
    with con_db.migrator.begin() as conn:
        sesion_b = conn.scalar(
            text(ABRIR.replace("returning id", "returning id")),
            {"t": TENANT_B, "n": f"B {uuid.uuid4().hex[:4]}", "p": ADMIN_B.usuario_id},
        )
    try:
        otros["s"] = sesion_b
        with como_app(con_db, TENANT_A) as conn:
            sesion = abrir(conn)
            falla(
                conn,
                VERIFICAR,
                verificacion(base, sesion, **{campo: otros[campo]}),
                FOREIGN_KEY_VIOLATION,
            )
    finally:
        with con_db.migrator.begin() as conn:
            conn.execute(text("delete from sesion_conteo where id = :s"), {"s": sesion_b})


@pytest.mark.parametrize(
    "sql",
    [
        "update verificacion set estado_fisico = 'danado'",
        "update verificacion set precio_al_contar = 0",
        "delete from verificacion",
        "truncate verificacion",
        "update sesion_conteo set nombre = 'x'",
        "update sesion_conteo set fecha_corte = current_date",
        "delete from sesion_conteo",
        "insert into sesion_conteo (tenant_id, nombre, fecha_corte, abierta_por, estado) "
        "values (:t, 'x', date '2026-11-30', gen_random_uuid(), 'cerrada')",
        "insert into sesion_conteo (tenant_id, nombre, fecha_corte, abierta_por, tipo) "
        "values (:t, 'x', date '2026-11-30', gen_random_uuid(), 'importacion')",
    ],
)
def test_app_cannot_change_closed_or_immutable_data(con_db, base, sql):
    with como_app(con_db, TENANT_A) as conn:
        falla(conn, sql, {"t": TENANT_A}, INSUFFICIENT_PRIVILEGE)


def test_event_links_to_session_and_verification(con_db, base):
    with como_app(con_db, TENANT_A) as conn:
        sesion = abrir(conn)
        p = verificacion(base, sesion)
        conn.execute(text(VERIFICAR), p)
        evento = (
            "insert into activo_evento (tenant_id, activo_id, tipo, datos, usuario_id, "
            "sesion_id, verificacion_id) values (:t, :a, 'verificado', '{}', :u, :s, :v)"
        )
        conn.execute(
            text(evento),
            {"t": TENANT_A, "a": base["act"], "u": ADMIN_A.usuario_id, "s": sesion, "v": p["id"]},
        )
        falla(
            conn,
            evento,
            {
                "t": TENANT_A,
                "a": base["act"],
                "u": ADMIN_A.usuario_id,
                "s": uuid.uuid4(),
                "v": None,
            },
            FOREIGN_KEY_VIOLATION,
        )
        falla(
            conn,
            evento,
            {
                "t": TENANT_A,
                "a": base["act"],
                "u": ADMIN_A.usuario_id,
                "s": None,
                "v": uuid.uuid4(),
            },
            FOREIGN_KEY_VIOLATION,
        )


def test_rls_hides_other_tenant_rows(con_db, base):
    with con_db.migrator.begin() as conn:
        sesion_b = conn.scalar(
            text(ABRIR),
            {"t": TENANT_B, "n": f"Ajena {uuid.uuid4().hex[:4]}", "p": ADMIN_B.usuario_id},
        )
    try:
        with como_app(con_db, TENANT_A) as conn:
            assert (
                conn.scalar(
                    text("select count(*) from sesion_conteo where id = :s"), {"s": sesion_b}
                )
                == 0
            )
    finally:
        with con_db.migrator.begin() as conn:
            conn.execute(text("delete from sesion_conteo where id = :s"), {"s": sesion_b})


# --- Spec 007, T1 (0010): una sola resolución por verificación ----------------------------

EVENTO = (
    "insert into activo_evento (tenant_id, activo_id, tipo, datos, usuario_id, sesion_id, "
    "verificacion_id) values (:t, :a, :tipo, '{}', :u, :s, :v)"
)


@pytest.mark.parametrize(
    ("primera", "segunda"),
    [
        ("ubicacion_cambiada", "ubicacion_cambiada"),
        ("ubicacion_cambiada", "discrepancia_descartada"),
        ("discrepancia_descartada", "discrepancia_descartada"),
        ("discrepancia_descartada", "ubicacion_cambiada"),
    ],
)
def test_a_verification_is_resolved_at_most_once(con_db, base, primera, segunda):
    with como_app(con_db, TENANT_A) as conn:
        sesion = abrir(conn)
        p = verificacion(base, sesion)
        conn.execute(text(VERIFICAR), p)
        datos = {
            "t": TENANT_A,
            "a": base["act"],
            "u": ADMIN_A.usuario_id,
            "s": sesion,
            "v": p["id"],
        }
        conn.execute(text(EVENTO), {**datos, "tipo": "verificado"})
        conn.execute(text(EVENTO), {**datos, "tipo": primera})
        falla(conn, EVENTO, {**datos, "tipo": segunda}, UNIQUE_VIOLATION)


def test_moves_without_verification_are_not_limited(con_db, base):
    with como_app(con_db, TENANT_A) as conn:
        datos = {"t": TENANT_A, "a": base["act"], "u": ADMIN_A.usuario_id, "s": None, "v": None}
        for _ in range(2):
            conn.execute(text(EVENTO), {**datos, "tipo": "ubicacion_cambiada"})
