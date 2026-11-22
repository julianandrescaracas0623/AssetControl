"""Tabla ``foto`` en la base (spec 012, T3; R4, R6, R9; A2).

Con el **rol de la aplicación** sobre una base temporal con dos tenants:

- Inserta y lee solo en su tenant; la foto de otro tenant no se ve ni se puede ligar.
- Una sola principal vigente por activo (otra después de retirar la anterior sí) y una
  sola foto por verificación.
- Solo marca el retiro (quién y cuándo, juntos); no cambia otras columnas, no borra ni
  vacía la tabla, y una foto retirada ya no se toca (disparador).
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
FOTO_RETIRADA = "P0005"


@pytest.fixture(scope="module")
def db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("fotos")


@pytest.fixture(scope="module")
def base(db) -> dict[str, uuid.UUID]:
    ids = {
        n: uuid.uuid4()
        for n in ("sede", "sala", "cat", "act", "act2", "sede_b", "sala_b", "cat_b", "act_b")
    }
    ids["ses"] = uuid.uuid4()
    ids["ver"] = uuid.uuid4()
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
            activos = [("act", "AC-1")] + ([("act2", "AC-2")] if not sufijo else [])
            for nombre, codigo in activos:
                conn.execute(
                    text(
                        "insert into activo (id, tenant_id, codigo, nombre, categoria_id, "
                        "ubicacion_id, precio_compra, creado_por) "
                        "values (:id, :t, :cod, 'Autoclave', :c, :u, 100, :p)"
                    ),
                    {
                        "id": ids[f"{nombre}{sufijo}"],
                        "t": tenant,
                        "cod": codigo,
                        "c": ids[f"cat{sufijo}"],
                        "u": ids[f"sala{sufijo}"],
                        "p": admin.usuario_id,
                    },
                )
        conn.execute(
            text(
                "insert into sesion_conteo (id, tenant_id, nombre, fecha_corte, abierta_por) "
                "values (:s, :t, 'Conteo', date '2026-11-30', :p)"
            ),
            {"s": ids["ses"], "t": TENANT_A, "p": ADMIN_A.usuario_id},
        )
        conn.execute(
            text(
                "insert into verificacion (id, tenant_id, sesion_id, activo_id, "
                "ubicacion_esperada_id, ubicacion_encontrada_id, estado_fisico, "
                "precio_al_contar, categoria_al_contar, verificado_por) "
                "values (:v, :t, :s, :a, :u, :u, 'ok', 100, :c, :p)"
            ),
            {
                "v": ids["ver"],
                "t": TENANT_A,
                "s": ids["ses"],
                "a": ids["act"],
                "u": ids["sala"],
                "c": ids["cat"],
                "p": ADMIN_A.usuario_id,
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


INSERTAR = (
    "insert into foto (id, tenant_id, activo_id, verificacion_id, clave, bytes, ancho, alto, "
    "subida_por) values (:id, :t, :a, :v, :k, 1000, 1600, 1200, :p)"
)
RETIRAR = "update foto set retirada_en = now(), retirada_por = :p where id = :id"


def _foto(conn, base, activo="act", verificacion=None, tenant=TENANT_A, autor=ADMIN_A) -> uuid.UUID:
    foto_id = uuid.uuid4()
    conn.execute(
        text(INSERTAR),
        {
            "id": foto_id,
            "t": tenant,
            "a": base[activo],
            "v": verificacion,
            "k": f"{tenant}/{foto_id}.jpg",
            "p": autor.usuario_id,
        },
    )
    return foto_id


def test_app_inserts_and_reads_only_its_tenant(db, base):
    with como_app(db, TENANT_A) as conn:
        foto_id = _foto(conn, base)
        assert conn.scalar(text("select count(*) from foto")) == 1
        assert conn.scalar(
            text("select creada_en is not null from foto where id = :i"), {"i": foto_id}
        )
    with como_app(db, TENANT_B) as conn:
        assert conn.scalar(text("select count(*) from foto")) == 0


def test_foreign_tenant_rows_and_references_are_refused(db, base):
    with como_app(db, TENANT_A) as conn:
        foto_id = uuid.uuid4()
        params = {
            "id": foto_id,
            "a": base["act"],
            "v": None,
            "k": f"x/{foto_id}.jpg",
            "p": ADMIN_A.usuario_id,
        }
        # Otro tenant en la fila: la política lo rechaza.
        falla(conn, INSERTAR, {**params, "t": TENANT_B}, INSUFFICIENT_PRIVILEGE)
        # Activo de otro tenant: la FK compuesta lo rechaza.
        falla(conn, INSERTAR, {**params, "t": TENANT_A, "a": base["act_b"]}, FOREIGN_KEY_VIOLATION)


def test_one_current_main_photo_per_asset(db, base):
    with como_app(db, TENANT_A) as conn:
        primera = _foto(conn, base)
        with pytest.raises(DBAPIError) as raised:
            with conn.begin_nested():
                _foto(conn, base)
        assert raised.value.orig.sqlstate == UNIQUE_VIOLATION
        conn.execute(text(RETIRAR), {"id": primera, "p": ADMIN_A.usuario_id})
        _foto(conn, base)  # retirada la anterior, la nueva entra
        _foto(conn, base, activo="act2")  # otro activo, su propia principal


def test_one_photo_per_verification(db, base):
    with como_app(db, TENANT_A) as conn:
        _foto(conn, base, verificacion=base["ver"])
        _foto(conn, base)  # la principal no cuenta como foto de la verificación
        with pytest.raises(DBAPIError) as raised:
            with conn.begin_nested():
                _foto(conn, base, verificacion=base["ver"])
        assert raised.value.orig.sqlstate == UNIQUE_VIOLATION


def test_app_only_marks_retirement_and_cannot_delete(db, base):
    with como_app(db, TENANT_A) as conn:
        foto_id = _foto(conn, base)
        for columna, valor in (("clave", "'otra'"), ("activo_id", "activo_id"), ("bytes", "1")):
            falla(
                conn,
                f"update foto set {columna} = {valor} where id = :id",  # noqa: S608 - fijo
                {"id": foto_id},
                INSUFFICIENT_PRIVILEGE,
            )
        falla(conn, "delete from foto where id = :id", {"id": foto_id}, INSUFFICIENT_PRIVILEGE)
        falla(conn, "truncate foto", {}, INSUFFICIENT_PRIVILEGE)
        # Quién y cuándo van juntos.
        falla(
            conn,
            "update foto set retirada_en = now() where id = :id",
            {"id": foto_id},
            CHECK_VIOLATION,
        )


def test_a_retired_photo_cannot_be_touched_again(db, base):
    with como_app(db, TENANT_A) as conn:
        foto_id = _foto(conn, base)
        conn.execute(text(RETIRAR), {"id": foto_id, "p": ADMIN_A.usuario_id})
        falla(conn, RETIRAR, {"id": foto_id, "p": ADMIN_A.usuario_id}, FOTO_RETIRADA)
        falla(
            conn,
            "update foto set retirada_en = null, retirada_por = null where id = :id",
            {"id": foto_id},
            FOTO_RETIRADA,
        )
