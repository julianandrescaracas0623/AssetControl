"""Activos en la base (spec 004, T1; R2, R3, R7, D1, Q1, Q2, A1; plan.md §2).

Con el **rol de la aplicación** sobre una base temporal con dos tenants (A y B):

- RLS: cada tenant ve y escribe solo lo suyo.
- ``codigo``: formato de Q1 (mayúsculas, 1–40, letras, números y ``- . / _``) y único por
  tenant; el mismo código en otro tenant sí se permite.
- ``precio_compra >= 0`` con dos decimales (Q2).
- D1: el disparador rechaza una sede o una ubicación inactiva.
- FK compuestas: categoría, ubicación y creador de otro tenant fallan.
- Sin ``UPDATE`` ni ``DELETE`` en ``activo`` (hasta la 005) ni en ``activo_evento``
  (inmutable); ``estado``, ``row_version`` y fechas por ``DEFAULT``.
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
UBICACION_INVALIDA = "P0002"


@pytest.fixture(scope="module")
def act_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("activos")


@pytest.fixture(scope="module")
def catalogo(act_db) -> dict[str, uuid.UUID]:
    """Sede, sala, box, sala inactiva y categoría en A; sala y categoría en B."""
    ids = {
        name: uuid.uuid4()
        for name in ("sede", "sala", "box", "inactiva", "cat", "sala_b", "sede_b", "cat_b")
    }
    with act_db.migrator.begin() as conn:
        insert = text(
            "insert into ubicacion (id, tenant_id, nombre, nombre_clave, tipo, padre_id, activa) "
            "values (:id, :t, :n, :n, :tipo, :p, :a)"
        )
        for nombre, tenant, tipo, padre, activa in (
            ("sede", TENANT_A, "sede", None, True),
            ("sala", TENANT_A, "sala", "sede", True),
            ("box", TENANT_A, "box", "sala", True),
            ("inactiva", TENANT_A, "sala", "sede", False),
            ("sede_b", TENANT_B, "sede", None, True),
            ("sala_b", TENANT_B, "sala", "sede_b", True),
        ):
            conn.execute(
                insert,
                {
                    "id": ids[nombre],
                    "t": tenant,
                    "n": nombre,
                    "tipo": tipo,
                    "p": ids[padre] if padre else None,
                    "a": activa,
                },
            )
        for nombre, tenant in (("cat", TENANT_A), ("cat_b", TENANT_B)):
            conn.execute(
                text(
                    "insert into categoria (id, tenant_id, nombre, nombre_clave) "
                    "values (:id, :t, :n, :n)"
                ),
                {"id": ids[nombre], "t": tenant, "n": nombre},
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


INSERT = (
    "insert into activo (id, tenant_id, codigo, nombre, categoria_id, ubicacion_id, "
    "precio_compra, creado_por) values (:id, :t, :codigo, :nombre, :cat, :ubi, :precio, :por)"
)


def params(catalogo, **cambios) -> dict:
    base = {
        "id": uuid.uuid4(),
        "t": TENANT_A,
        "codigo": f"AC-{uuid.uuid4().hex[:8].upper()}",
        "nombre": "Autoclave",
        "cat": catalogo["cat"],
        "ubi": catalogo["sala"],
        "precio": Decimal("1390000.00"),
        "por": ADMIN_A.usuario_id,
    }
    return {**base, **cambios}


def test_insert_with_defaults_and_isolation(act_db, catalogo):
    with como_app(act_db, TENANT_A) as conn:
        p = params(catalogo, ubi=catalogo["box"])
        conn.execute(text(INSERT), p)
        fila = conn.execute(
            text("select estado, row_version, atributos, precio_compra from activo where id = :id"),
            {"id": p["id"]},
        ).one()
        assert fila == ("activo", 1, {}, Decimal("1390000.00"))
        conn.execute(
            text(
                "insert into activo_evento (tenant_id, activo_id, tipo, datos, usuario_id) "
                "values (:t, :a, 'creado', '{}'::jsonb, :u)"
            ),
            {"t": TENANT_A, "a": p["id"], "u": ADMIN_A.usuario_id},
        )
        assert conn.scalar(text("select seq from activo_evento")) is not None

    with como_app(act_db, TENANT_B) as conn:
        assert conn.scalar(text("select count(*) from activo")) == 0
        # Con datos de A y el tenant B fijado lo detiene primero el disparador D1 (no ve la
        # ubicación de A por RLS); sin él lo detendría el WITH CHECK de la política.
        falla(conn, INSERT, params(catalogo), UBICACION_INVALIDA)


@pytest.mark.parametrize("codigo", ["", "abc-1", "A B", "Á1", "A" * 41, "A\n1", "A#1", "AC-1 "])
def test_code_format_is_checked(act_db, catalogo, codigo):
    with como_app(act_db, TENANT_A) as conn:
        falla(conn, INSERT, params(catalogo, codigo=codigo), CHECK_VIOLATION)


@pytest.mark.parametrize("codigo", ["0001", "AC-2026/001", "X.Y_Z-9", "A" * 40])
def test_valid_codes(act_db, catalogo, codigo):
    with como_app(act_db, TENANT_A) as conn:
        conn.execute(text(INSERT), params(catalogo, codigo=codigo))


def test_code_is_unique_per_tenant_only(act_db, catalogo):
    with como_app(act_db, TENANT_A) as conn:
        conn.execute(text(INSERT), params(catalogo, codigo="DUP-1"))
        falla(conn, INSERT, params(catalogo, codigo="DUP-1"), UNIQUE_VIOLATION)
    with como_app(act_db, TENANT_B) as conn:
        conn.execute(
            text(INSERT),
            params(
                catalogo,
                t=TENANT_B,
                codigo="DUP-1",
                cat=catalogo["cat_b"],
                ubi=catalogo["sala_b"],
                por=ADMIN_B.usuario_id,
            ),
        )


@pytest.mark.parametrize("precio", [Decimal("-0.01"), Decimal("1000000000000.00")])
def test_price_range_is_checked(act_db, catalogo, precio):
    esperado = CHECK_VIOLATION if precio < 0 else "22003"  # numeric_value_out_of_range
    with como_app(act_db, TENANT_A) as conn:
        falla(conn, INSERT, params(catalogo, precio=precio), esperado)


def test_price_zero_is_allowed_and_rounded_to_cents(act_db, catalogo):
    with como_app(act_db, TENANT_A) as conn:
        p = params(catalogo, precio=Decimal("0"))
        conn.execute(text(INSERT), p)
        assert (
            conn.scalar(
                text("select precio_compra::text from activo where id = :id"), {"id": p["id"]}
            )
            == "0.00"
        )


@pytest.mark.parametrize("ubicacion", ["sede", "inactiva"])
def test_d1_rejects_a_sede_or_an_inactive_location(act_db, catalogo, ubicacion):
    with como_app(act_db, TENANT_A) as conn:
        falla(conn, INSERT, params(catalogo, ubi=catalogo[ubicacion]), UBICACION_INVALIDA)


@pytest.mark.parametrize(
    "cambio",
    [
        {"ubi": "sala_b"},
        {"cat": "cat_b"},
        {"por": "admin_b"},
    ],
)
def test_references_of_another_tenant_fail(act_db, catalogo, cambio):
    valores = {**catalogo, "admin_b": ADMIN_B.usuario_id}
    reemplazo = {k: valores[v] for k, v in cambio.items()}
    with como_app(act_db, TENANT_A) as conn:
        esperado = UBICACION_INVALIDA if "ubi" in cambio else FOREIGN_KEY_VIOLATION
        falla(conn, INSERT, params(catalogo, **reemplazo), esperado)


@pytest.mark.parametrize(
    "sql",
    [
        "update activo set nombre = 'x'",
        "update activo set codigo = 'X'",
        "update activo set precio_compra = 0",
        "delete from activo",
        "truncate activo",
        "update activo_evento set datos = '{}'::jsonb",
        "delete from activo_evento",
        "insert into activo_evento (id, tenant_id, activo_id, tipo, datos, usuario_id) "
        "values (gen_random_uuid(), :t, gen_random_uuid(), 'creado', '{}', gen_random_uuid())",
        "insert into activo (id, tenant_id, codigo, nombre, categoria_id, ubicacion_id, "
        "precio_compra, creado_por, estado) values (gen_random_uuid(), :t, 'Z', 'x', "
        "gen_random_uuid(), gen_random_uuid(), 0, gen_random_uuid(), 'dado_de_baja')",
    ],
)
def test_app_cannot_update_delete_or_set_server_columns(act_db, catalogo, sql):
    with como_app(act_db, TENANT_A) as conn:
        falla(conn, sql, {"t": TENANT_A}, INSUFFICIENT_PRIVILEGE)


def test_trigger_function_is_invoker_with_fixed_search_path(act_db):
    with act_db.migrator.connect() as conn:
        fila = conn.execute(
            text(
                "select p.prosecdef, p.proconfig, "
                "has_function_privilege('public', p.oid, 'EXECUTE') "
                "from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                "where n.nspname = 'public' and p.proname = 'activo_ubicacion_valida'"
            )
        ).one()
    assert fila == (False, ["search_path=pg_catalog, pg_temp"], False)
