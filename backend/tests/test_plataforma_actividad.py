"""Módulo Actividad de la consola (spec 017, T6; R32, R34, R36; A4, A5, A6, A18; CU-08).

Sobre una base temporal migrada a ``head`` (tenants sintéticos A y B de ``acceso_db``) con
la consola habilitada. Las filas de auditoría las siembra el migrador con fechas fijas
(años lejanos o una empresa propia por prueba), así ninguna prueba depende de las demás ni
de la auditoría que escriben los logins.

- SQL (rol de la aplicación): ``acceso.plataforma_listar_auditoria`` rechaza a quien no es
  un desarrollador activo (A5); devuelve solo las columnas de R32, con los nombres leídos
  de ``tenant`` y ``desarrollador`` al consultar; acota el límite dentro de la función;
  deja vacías todas las GUC ``app.plat_*``; con ``tenant_session`` (o sin desarrollador)
  la aplicación no lee la auditoría (A6), y fijar las GUC de la función no le abre nada.
- HTTP: registro del módulo; ``GET /plataforma/actividad`` con los campos exactos,
  ``no-store``, orden descendente por ``(fecha, id)``, páginas de 50 (máximo 100) con un
  cursor estable frente a inserciones, filtros por empresa, acción y fechas, validación
  estricta (``400 solicitud_invalida``), solo lectura (sin auditar la consulta, solo
  ``GET``), ``401`` para tokens de clínica y para un desarrollador desactivado, logs sin
  nombres ni correos.

Datos sintéticos (``@ejemplo.test``).
"""

import logging
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from acceso_db import (
    ADMIN_A,
    ADMIN_B,
    CONTADOR_A,
    TENANT_A,
    TENANT_B,
    AccesoDb,
    bearer,
    dispose,
    temporary_acceso_db,
)
from flask import Flask
from plataforma_db import (
    Dev,
    ejecutar,
    error_code,
    filas,
    login,
    make_plat_app,
    nuevo_dev,
    plat_bearer,
    sembrar_dev,
)
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from app.db import (
    FiltroAuditoria,
    PlataformaFuncionError,
    plataforma_listar_auditoria,
    plataforma_session,
)

INSUFFICIENT_PRIVILEGE = "42501"
RUTA = "/plataforma/actividad"
NIL = "00000000-0000-0000-0000-000000000000"
MAX_ID = "ffffffff-ffff-ffff-ffff-ffffffffffff"
LISTAR = (
    "select * from acceso.plataforma_listar_auditoria("
    ":d, cast(:t as uuid), :a, cast(:desde as timestamptz), cast(:hasta as timestamptz), "
    ":l, cast(:cf as timestamptz), cast(:ci as uuid))"
)
SIN_FILTRO = {
    "t": NIL,
    "a": "",
    "desde": "-infinity",
    "hasta": "infinity",
    "l": 50,
    "cf": "infinity",
    "ci": MAX_ID,
}
COLUMNAS = [
    "id",
    "creado_en",
    "accion",
    "resultado",
    "desarrollador_nombre",
    "tenant_id",
    "tenant_nombre",
    "objeto_id",
]
CAMPOS = {
    "id",
    "fecha",
    "accion",
    "resultado",
    "desarrollador_nombre",
    "empresa_id",
    "empresa_nombre",
    "objeto_id",
}
OWNER_GUCS = (
    "app.plat_login_email",
    "app.plat_dev_crear",
    "app.plat_dev_restablecer",
    "app.plat_dev_estado",
    "app.plat_dev_objetivo",
    "app.plat_actor",
    "app.plat_listar",
    "app.plat_tenant_nuevo",
    "app.plat_usuario_nuevo",
    "app.plat_tenant_estado",
    "app.plat_usuarios",
    "app.plat_membresia_tenant",
    "app.plat_membresia_usuario",
    "app.plat_actividad",
)
COT = timedelta(hours=-5)


@pytest.fixture(scope="module")
def act_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("plat_actividad")


@pytest.fixture(scope="module")
def act_app(act_db) -> Iterator[Flask]:
    flask_app = make_plat_app(act_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(act_app):
    return act_app.test_client(use_cookies=False)


@pytest.fixture(scope="module")
def app_engine(act_db) -> Iterator[Engine]:
    engine = create_engine(act_db.app_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def dev(act_db) -> Dev:
    return sembrar_dev(act_db, nuevo_dev("actividad"))


@pytest.fixture(scope="module")
def headers(act_app, dev) -> dict[str, str]:
    response = login(act_app.test_client(use_cookies=False), dev.email)
    assert response.status_code == 200
    return plat_bearer(response.get_json()["access_token"])


# --- Siembra ---------------------------------------------------------------------------------


def _empresa(db: AccesoDb) -> tuple[uuid.UUID, str]:
    tenant_id = uuid.uuid4()
    nombre = f"Clínica Actividad {uuid.uuid4().hex[:6]}"
    ejecutar(db, "insert into tenant (id, nombre) values (:t, :n)", {"t": tenant_id, "n": nombre})
    return tenant_id, nombre


def _registro(
    db: AccesoDb,
    creado_en: datetime,
    *,
    accion: str = "empresa_desactivada",
    tenant_id: uuid.UUID | None = None,
    desarrollador_id: uuid.UUID | None = None,
    objeto_id: uuid.UUID | None = None,
    resultado: str = "ok",
    id: uuid.UUID | None = None,  # noqa: A002
) -> uuid.UUID:
    registro = id or uuid.uuid4()
    ejecutar(
        db,
        "insert into plataforma_auditoria "
        "(id, desarrollador_id, accion, resultado, tenant_id, objeto_id, creado_en) "
        "values (:i, :d, :a, :r, :t, :o, :c)",
        {
            "i": registro,
            "d": desarrollador_id,
            "a": accion,
            "r": resultado,
            "t": tenant_id,
            "o": objeto_id,
            "c": creado_en,
        },
    )
    return registro


def _serie(db: AccesoDb, tenant_id, n: int, inicio: datetime, dev_id=None) -> list[uuid.UUID]:
    """``n`` registros de ``tenant_id``, uno por segundo desde ``inicio``."""
    return [
        _registro(db, inicio + timedelta(seconds=i), tenant_id=tenant_id, desarrollador_id=dev_id)
        for i in range(n)
    ]


def _orden_esperado(db: AccesoDb, tenant_id) -> list[str]:
    return [
        str(r["id"])
        for r in filas(
            db,
            "select id from plataforma_auditoria where tenant_id = :t "
            "order by creado_en desc, id desc",
            {"t": tenant_id},
        )
    ]


def _auditoria_count(db: AccesoDb) -> int:
    (row,) = filas(db, "select count(*) as n from plataforma_auditoria")
    return row["n"]


def _get(client, headers, **params):
    return client.get(RUTA, query_string=params, headers=headers)


def _todas(client, headers, **params) -> list[dict]:
    """Recorre todas las páginas con el cursor."""
    resultado: list[dict] = []
    cursor = None
    for _ in range(500):
        extra = {} if cursor is None else {"cursor": cursor}
        response = _get(client, headers, **params, **extra)
        assert response.status_code == 200, response.get_json()
        body = response.get_json()
        resultado += body["actividad"]
        cursor = body["siguiente"]
        if cursor is None:
            return resultado
    raise AssertionError("el cursor no terminó")


# --- SQL: utilidades ------------------------------------------------------------------------


def _expect_error(conn: Connection, sql: str, params: dict, sqlstate: str) -> str:
    nested = conn.begin_nested()
    with pytest.raises(DBAPIError) as excinfo:
        conn.execute(text(sql), params)
    nested.rollback()
    assert getattr(excinfo.value.orig, "sqlstate", None) == sqlstate, str(excinfo.value.orig)
    return str(excinfo.value.orig)


def _gucs_empty(conn: Connection) -> bool:
    return all(
        conn.scalar(text("select current_setting(:g, true)"), {"g": guc}) in (None, "")
        for guc in OWNER_GUCS
    )


# --- A5 / R36: quien llama debe ser un desarrollador activo ---------------------------------


@pytest.mark.parametrize("caso", ["inexistente", "inactivo", "usuario_de_clinica"])
def test_the_function_rejects_a_caller_that_is_not_an_active_developer(act_db, app_engine, caso):
    if caso == "inexistente":
        caller = uuid.uuid4()
    elif caso == "inactivo":
        caller = sembrar_dev(act_db, nuevo_dev("inactivo"), activo=False).id
    else:
        caller = ADMIN_A.usuario_id  # un admin de clínica no es desarrollador
    tenant_id, nombre = _empresa(act_db)
    _registro(act_db, datetime.now(UTC), tenant_id=tenant_id)
    before = _auditoria_count(act_db)
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            message = _expect_error(
                conn, LISTAR, {**SIN_FILTRO, "d": str(caller)}, INSUFFICIENT_PRIVILEGE
            )
            assert "desarrollador_no_autorizado" in message
            assert str(caller) not in message
            assert nombre not in message
            assert _gucs_empty(conn)
        finally:
            tx.rollback()
    assert _auditoria_count(act_db) == before


def test_inside_a_tenant_session_the_app_reads_no_audit_and_cannot_use_the_function(
    act_db, app_engine, dev
):
    tenant_id, _ = _empresa(act_db)
    _registro(act_db, datetime.now(UTC), tenant_id=TENANT_A)
    _registro(act_db, datetime.now(UTC), tenant_id=tenant_id, desarrollador_id=dev.id)
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(TENANT_A)})
            assert conn.scalar(text("select count(*) from plataforma_auditoria")) == 0
            _expect_error(
                conn, LISTAR, {**SIN_FILTRO, "d": str(ADMIN_A.usuario_id)}, INSUFFICIENT_PRIVILEGE
            )
        finally:
            tx.rollback()


@pytest.mark.parametrize("caso", ["sin_desarrollador", "desarrollador_inactivo"])
def test_without_an_active_developer_the_app_reads_no_audit_rows(act_db, app_engine, caso):
    _registro(act_db, datetime.now(UTC), tenant_id=TENANT_A)
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            if caso == "desarrollador_inactivo":
                inactivo = sembrar_dev(act_db, nuevo_dev("inactivo-rls"), activo=False)
                conn.execute(
                    text("select set_config('app.desarrollador_id', :d, true)"),
                    {"d": str(inactivo.id)},
                )
            assert conn.scalar(text("select count(*) from plataforma_auditoria")) == 0
        finally:
            tx.rollback()


def test_the_gucs_of_the_function_open_nothing_to_the_app(act_db, app_engine, dev):
    """Sin la función, fijar ``app.plat_actividad`` (y las demás) no abre nombres a la app."""
    otro = sembrar_dev(act_db, nuevo_dev("otro-nombre"))
    _empresa(act_db)
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            for guc in ("app.plat_actor", "app.plat_actividad", "app.plat_listar"):
                conn.execute(text("select set_config(:g, :v, true)"), {"g": guc, "v": str(dev.id)})
            for sql in (
                "select count(*) from tenant",
                "select count(*) from desarrollador",
                "select count(*) from plataforma_auditoria",
            ):
                nested = conn.begin_nested()
                try:
                    assert conn.execute(text(sql)).scalar_one() == 0, sql
                    nested.commit()
                except DBAPIError as exc:
                    nested.rollback()
                    assert exc.orig.sqlstate == INSUFFICIENT_PRIVILEGE, sql
            # Con su propio desarrollador, la app solo ve su fila de desarrollador.
            conn.execute(
                text("select set_config('app.desarrollador_id', :d, true)"), {"d": str(dev.id)}
            )
            ids = set(conn.scalars(text("select id from desarrollador")))
            assert ids == {dev.id}
            assert otro.id not in ids
        finally:
            tx.rollback()


# --- SQL: lista (R32) ------------------------------------------------------------------------


def test_the_function_returns_only_the_r32_columns_with_names_read_at_query_time(
    act_db, app_engine, dev
):
    tenant_id, nombre = _empresa(act_db)
    autor = sembrar_dev(act_db, nuevo_dev("autor"))
    momento = datetime(2002, 5, 6, 7, 8, 9, 123456, tzinfo=UTC)
    del_dev = _registro(
        act_db, momento, tenant_id=tenant_id, desarrollador_id=autor.id, objeto_id=tenant_id
    )
    del_operador = _registro(
        act_db, momento - timedelta(seconds=1), accion="desarrollador_creado", objeto_id=autor.id
    )
    params = {
        **SIN_FILTRO,
        "d": str(dev.id),
        "desde": "2002-05-06T00:00:00Z",
        "hasta": "2002-05-07T00:00:00Z",
    }
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            result = conn.execute(text(LISTAR), params)
            columns = list(result.keys())
            rows = result.all()
            assert _gucs_empty(conn)
        finally:
            tx.rollback()
    assert columns == COLUMNAS
    assert [tuple(r) for r in rows] == [
        (del_dev, momento, "empresa_desactivada", "ok", autor.nombre, tenant_id, nombre, tenant_id),
        (
            del_operador,
            momento - timedelta(seconds=1),
            "desarrollador_creado",
            "ok",
            None,
            None,
            None,
            autor.id,
        ),
    ]
    # El nombre se lee al consultar: si cambia, la lista muestra el nuevo.
    ejecutar(
        act_db, "update tenant set nombre = :n where id = :t", {"n": "Renombrada", "t": tenant_id}
    )
    with app_engine.begin() as conn:
        (fila, _) = conn.execute(text(LISTAR), params).all()
    assert fila.tenant_nombre == "Renombrada"


def test_the_function_bounds_the_limit(act_db, app_engine, dev):
    tenant_id, _ = _empresa(act_db)
    _serie(act_db, tenant_id, 103, datetime(2003, 1, 1, tzinfo=UTC))
    base = {**SIN_FILTRO, "d": str(dev.id), "t": str(tenant_id)}
    with app_engine.begin() as conn:
        for limite, esperado in ((1000, 101), (2_147_483_647, 101), (0, 1), (-7, 1), (5, 5)):
            assert len(conn.execute(text(LISTAR), {**base, "l": limite}).all()) == esperado, limite


def test_the_function_filters_and_orders_by_date_and_id(act_db, app_engine, dev):
    tenant_id, _ = _empresa(act_db)
    otro, _ = _empresa(act_db)
    mismo = datetime(2004, 2, 3, 4, 5, 6, tzinfo=UTC)
    # Tres con la misma fecha: el desempate es el id, descendente.
    empates = [_registro(act_db, mismo, tenant_id=tenant_id) for _ in range(3)]
    viejo = _registro(
        act_db, mismo - timedelta(days=1), tenant_id=tenant_id, accion="usuario_reactivado"
    )
    _registro(act_db, mismo, tenant_id=otro)
    base = {**SIN_FILTRO, "d": str(dev.id), "t": str(tenant_id)}
    with app_engine.begin() as conn:
        ids = [r.id for r in conn.execute(text(LISTAR), base)]
        assert ids == [*sorted(empates, key=str, reverse=True), viejo]
        solo = [r.id for r in conn.execute(text(LISTAR), {**base, "a": "usuario_reactivado"})]
        assert solo == [viejo]
        # Cursor: estrictamente después de (fecha, id).
        cursor = sorted(empates, key=str, reverse=True)[0]
        despues = [
            r.id
            for r in conn.execute(
                text(LISTAR), {**base, "cf": mismo.isoformat(), "ci": str(cursor)}
            )
        ]
        assert despues == [*sorted(empates, key=str, reverse=True)[1:], viejo]


def test_app_db_function_uses_the_developer_of_the_session(act_app, act_db, dev):
    tenant_id, nombre = _empresa(act_db)
    registro = _registro(act_db, datetime(2005, 1, 1, tzinfo=UTC), tenant_id=tenant_id)
    with act_app.app_context():
        with plataforma_session(dev.id) as session:
            filas_ = plataforma_listar_auditoria(session, FiltroAuditoria(tenant_id=tenant_id))
            assert [f.id for f in filas_] == [registro]
            # El repr no lleva nombres.
            assert nombre not in repr(filas_)
        inactivo = sembrar_dev(act_db, nuevo_dev("inactivo-db"), activo=False)
        with pytest.raises(PlataformaFuncionError) as excinfo:
            with plataforma_session(inactivo.id) as session:
                plataforma_listar_auditoria(session, FiltroAuditoria())
        assert excinfo.value.codigo == "desarrollador_no_autorizado"


# --- HTTP: registro y lista ------------------------------------------------------------------


def test_the_actividad_module_is_registered_after_usuarios(client, headers):
    response = client.get("/plataforma/modulos", headers=headers)
    assert response.status_code == 200
    modulos = response.get_json()["modulos"]
    assert [m["id"] for m in modulos] == ["empresas", "usuarios", "actividad"]
    (actividad,) = [m for m in modulos if m["id"] == "actividad"]
    assert actividad["titulo"] == "Actividad"


def test_list_returns_exactly_the_r32_fields(client, headers, act_db):
    tenant_id, nombre = _empresa(act_db)
    autor = sembrar_dev(act_db, nuevo_dev("autor-http"))
    usuario = uuid.uuid4()
    momento = datetime(2006, 7, 8, 9, 10, 11, 654321, tzinfo=UTC)
    registro = _registro(
        act_db,
        momento,
        accion="usuario_desactivado",
        tenant_id=tenant_id,
        desarrollador_id=autor.id,
        objeto_id=usuario,
    )
    response = _get(client, headers, empresa_id=str(tenant_id))
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    body = response.get_json()
    assert set(body) == {"actividad", "siguiente"}
    assert body == {
        "actividad": [
            {
                "id": str(registro),
                "fecha": momento.isoformat(),
                "accion": "usuario_desactivado",
                "resultado": "ok",
                "desarrollador_nombre": autor.nombre,
                "empresa_id": str(tenant_id),
                "empresa_nombre": nombre,
                "objeto_id": str(usuario),
            }
        ],
        "siguiente": None,
    }
    texto = response.get_data(as_text=True)
    assert autor.email not in texto
    assert str(autor.id) not in texto  # ni el id del desarrollador (no lo pide R32)


def test_operator_rows_show_operador_and_rows_without_company_have_null_company(
    client, headers, act_db
):
    momento = datetime(2007, 3, 3, 12, 0, tzinfo=UTC)
    objetivo = sembrar_dev(act_db, nuevo_dev("objetivo"))
    _registro(act_db, momento, accion="desarrollador_restablecido", objeto_id=objetivo.id)
    response = _get(
        client,
        headers,
        accion="desarrollador_restablecido",
        desde="2007-03-03",
        hasta="2007-03-03",
    )
    assert response.status_code == 200
    (fila,) = response.get_json()["actividad"]
    assert fila["desarrollador_nombre"] == "Operador"
    assert fila["empresa_id"] is None
    assert fila["empresa_nombre"] is None
    assert fila["objeto_id"] == str(objetivo.id)
    assert set(fila) == CAMPOS


def test_default_page_is_50_and_the_cursor_walks_every_row_once_in_order(client, headers, act_db):
    tenant_id, _ = _empresa(act_db)
    _serie(act_db, tenant_id, 120, datetime(2008, 1, 1, tzinfo=UTC))
    # Empates de fecha justo en el borde de la página.
    borde = datetime(2008, 1, 1, tzinfo=UTC) + timedelta(seconds=70)
    for _ in range(4):
        _registro(act_db, borde, tenant_id=tenant_id)
    primera = _get(client, headers, empresa_id=str(tenant_id))
    body = primera.get_json()
    assert len(body["actividad"]) == 50
    assert isinstance(body["siguiente"], str)
    todas = _todas(client, headers, empresa_id=str(tenant_id))
    assert [f["id"] for f in todas] == _orden_esperado(act_db, tenant_id)
    assert len(todas) == 124


@pytest.mark.parametrize("limite", [1, 100])
def test_the_page_size_can_go_from_1_to_100(client, headers, act_db, limite):
    tenant_id, _ = _empresa(act_db)
    _serie(act_db, tenant_id, 105, datetime(2009, 1, 1, tzinfo=UTC))
    body = _get(client, headers, empresa_id=str(tenant_id), limite=str(limite)).get_json()
    assert len(body["actividad"]) == limite
    assert body["siguiente"] is not None
    todas = _todas(client, headers, empresa_id=str(tenant_id), limite=str(limite))
    assert [f["id"] for f in todas] == _orden_esperado(act_db, tenant_id)


def test_an_exact_last_page_has_no_next_cursor(client, headers, act_db):
    tenant_id, _ = _empresa(act_db)
    _serie(act_db, tenant_id, 50, datetime(2010, 1, 1, tzinfo=UTC))
    body = _get(client, headers, empresa_id=str(tenant_id)).get_json()
    assert len(body["actividad"]) == 50
    assert body["siguiente"] is None


def test_the_cursor_is_stable_while_rows_are_inserted(client, headers, act_db, dev):
    tenant_id, _ = _empresa(act_db)
    inicio = datetime(2011, 1, 1, tzinfo=UTC)
    _serie(act_db, tenant_id, 60, inicio)
    antes = _orden_esperado(act_db, tenant_id)
    primera = _get(client, headers, empresa_id=str(tenant_id), limite="20").get_json()
    assert [f["id"] for f in primera["actividad"]] == antes[:20]
    # Llegan registros nuevos (más recientes) y uno con la misma fecha que el último visto
    # pero con un id mayor: ninguno se cuela en las páginas siguientes ni las desplaza.
    _serie(act_db, tenant_id, 5, datetime.now(UTC))
    ultimo = primera["actividad"][-1]
    _registro(
        act_db,
        datetime.fromisoformat(ultimo["fecha"]),
        tenant_id=tenant_id,
        id=uuid.UUID(MAX_ID[:-1] + "e"),
    )
    resto: list[dict] = []
    cursor = primera["siguiente"]
    while cursor is not None:
        body = _get(client, headers, empresa_id=str(tenant_id), limite="20", cursor=cursor)
        assert body.status_code == 200
        resto += body.get_json()["actividad"]
        cursor = body.get_json()["siguiente"]
    assert [f["id"] for f in resto] == antes[20:]


def test_filters_by_company_action_and_dates_in_colombia_time(client, headers, act_db):
    tenant_id, _ = _empresa(act_db)
    otro, _ = _empresa(act_db)

    def utc(*args) -> datetime:
        return datetime(*args, tzinfo=UTC)

    # Días de Colombia (UTC−5): el 10 de marzo empieza a las 05:00 UTC.
    fuera_antes = _registro(act_db, utc(2012, 3, 10, 4, 59, 59, 999999), tenant_id=tenant_id)
    dentro_inicio = _registro(act_db, utc(2012, 3, 10, 5, 0), tenant_id=tenant_id)
    dentro_accion = _registro(
        act_db, utc(2012, 3, 11, 12, 0), tenant_id=tenant_id, accion="empresa_reactivada"
    )
    dentro_fin = _registro(act_db, utc(2012, 3, 13, 4, 59, 59, 999999), tenant_id=tenant_id)
    fuera_despues = _registro(act_db, utc(2012, 3, 13, 5, 0), tenant_id=tenant_id)
    de_otra = _registro(act_db, utc(2012, 3, 11, 12, 0), tenant_id=otro)

    def ids(**params) -> list[str]:
        return [f["id"] for f in _todas(client, headers, **params)]

    rango = {"desde": "2012-03-10", "hasta": "2012-03-12"}
    assert ids(empresa_id=str(tenant_id), **rango) == [
        str(dentro_fin),
        str(dentro_accion),
        str(dentro_inicio),
    ]
    assert ids(empresa_id=str(tenant_id)) == [
        str(i) for i in (fuera_despues, dentro_fin, dentro_accion, dentro_inicio, fuera_antes)
    ]
    assert ids(empresa_id=str(tenant_id), accion="empresa_reactivada") == [str(dentro_accion)]
    assert ids(accion="empresa_reactivada", **rango) == [str(dentro_accion)]
    # Sin filtro de empresa, el rango trae también la de la otra.
    assert set(ids(**rango)) >= {str(de_otra), str(dentro_accion)}
    assert ids(empresa_id=str(tenant_id), desde="2012-03-13") == [str(fuera_despues)]
    assert ids(empresa_id=str(tenant_id), hasta="2012-03-09") == [str(fuera_antes)]
    # Un mismo día en los dos extremos.
    assert ids(empresa_id=str(tenant_id), desde="2012-03-11", hasta="2012-03-11") == [
        str(dentro_accion)
    ]
    # Una empresa sin registros (o inexistente) da una lista vacía, no 404.
    assert ids(empresa_id=str(uuid.uuid4())) == []


@pytest.mark.parametrize(
    "params",
    [
        {"empresa_id": "no-es-uuid"},
        {"empresa_id": str(TENANT_A).upper()},
        {"empresa_id": str(TENANT_A).replace("-", "")},
        {"empresa_id": NIL},
        {"empresa_id": ""},
        {"accion": "borrar_todo"},
        {"accion": ""},
        {"accion": "LOGIN_OK"},
        {"desde": "2012-3-1"},
        {"desde": "2012-02-30"},
        {"desde": "01/03/2012"},
        {"hasta": "2012-03-01T00:00:00"},
        {"hasta": "9999-12-31"},  # el día siguiente no existe en Python
        {"desde": "2012-03-02", "hasta": "2012-03-01"},
        {"limite": "0"},
        {"limite": "101"},
        {"limite": "-1"},
        {"limite": "50.0"},
        {"limite": "abc"},
        {"limite": ""},
        {"cursor": "x"},
        {"cursor": ""},
        {"cursor": f"1_{NIL}x"},
        {"cursor": f"-1_{uuid.uuid4()}"},
        {"cursor": f"99999999999999999999_{uuid.uuid4()}"},
        {"cursor": f"1000_{str(uuid.uuid4()).upper()}"},
        {"tenant_id": str(TENANT_A)},
        {"orden": "asc"},
    ],
)
def test_invalid_parameters_are_400_solicitud_invalida(client, headers, act_db, params):
    before = _auditoria_count(act_db)
    response = _get(client, headers, **params)
    assert response.status_code == 400, params
    assert error_code(response) == "solicitud_invalida"
    assert response.headers["Cache-Control"] == "no-store"
    assert _auditoria_count(act_db) == before


@pytest.mark.parametrize("desde", ["0001-01-01", "9999-12-31"])
def test_extreme_desde_dates_are_valid(client, headers, desde):
    response = _get(client, headers, desde=desde)
    assert response.status_code == 200, response.get_json()


def test_two_developers_with_the_same_name_keep_their_own_rows(client, headers, act_db):
    tenant_id, _ = _empresa(act_db)
    nombre = f"Dev repetido {uuid.uuid4().hex[:6]}"
    uno = sembrar_dev(act_db, Dev(uuid.uuid4(), f"uno.{uuid.uuid4().hex[:8]}@ejemplo.test", nombre))
    dos = sembrar_dev(act_db, Dev(uuid.uuid4(), f"dos.{uuid.uuid4().hex[:8]}@ejemplo.test", nombre))
    momento = datetime(2013, 5, 5, 12, 0, tzinfo=UTC)
    del_uno = _registro(act_db, momento, tenant_id=tenant_id, desarrollador_id=uno.id)
    del_dos = _registro(
        act_db, momento + timedelta(seconds=1), tenant_id=tenant_id, desarrollador_id=dos.id
    )
    filas_http = _todas(client, headers, empresa_id=str(tenant_id))
    # Una fila por registro (la unión es por id, no por nombre): ni duplicadas ni mezcladas.
    assert [f["id"] for f in filas_http] == [str(del_dos), str(del_uno)]
    assert all(f["desarrollador_nombre"] == nombre for f in filas_http)


def test_a_repeated_parameter_is_400(client, headers):
    response = client.get(f"{RUTA}?accion=login_ok&accion=empresa_creada", headers=headers)
    assert response.status_code == 400
    assert error_code(response) == "solicitud_invalida"


def test_reading_writes_no_audit(client, headers, act_db):
    before = _auditoria_count(act_db)
    for _ in range(3):
        assert _get(client, headers).status_code == 200
    assert _auditoria_count(act_db) == before


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_only_get(client, headers, act_db, method):
    before = _auditoria_count(act_db)
    response = client.open(RUTA, method=method, json={}, headers=headers)
    assert response.status_code == 405
    assert _auditoria_count(act_db) == before


def test_tenant_tokens_and_anonymous_get_401(client):
    for name, extra in (
        ("anonimo", {}),
        ("admin", bearer(ADMIN_A, TENANT_A, rol="admin")),
        ("contador", bearer(CONTADOR_A, TENANT_A, rol="contador")),
        ("admin_b", bearer(ADMIN_B, TENANT_B, rol="admin")),
    ):
        response = client.get(RUTA, headers=extra)
        assert response.status_code == 401, name
        assert error_code(response) == "no_autenticado"
        assert "actividad" not in response.get_json()


def test_a_developer_deactivated_after_login_gets_401(act_app, act_db):
    client = act_app.test_client(use_cookies=False)
    otro = sembrar_dev(act_db, nuevo_dev("baja-actividad"))
    response = login(client, otro.email)
    assert response.status_code == 200
    auth = plat_bearer(response.get_json()["access_token"])
    assert client.get(RUTA, headers=auth).status_code == 200
    ejecutar(act_db, "update desarrollador set activo = false where id = :d", {"d": otro.id})
    response = client.get(RUTA, headers=auth)
    assert response.status_code == 401
    assert error_code(response) == "no_autenticado"


def test_logs_never_carry_names_nor_emails(client, headers, act_db, caplog):
    tenant_id, nombre = _empresa(act_db)
    autor = sembrar_dev(act_db, nuevo_dev("autor-log"))
    _registro(
        act_db, datetime(2013, 1, 1, tzinfo=UTC), tenant_id=tenant_id, desarrollador_id=autor.id
    )
    caplog.set_level(logging.DEBUG)
    assert _get(client, headers, empresa_id=str(tenant_id)).status_code == 200
    assert _get(client, headers, empresa_id="no-es-uuid").status_code == 400
    texto = caplog.text
    for secreto in (nombre, autor.nombre, autor.email):
        assert secreto not in texto


def test_the_date_of_each_row_is_iso_with_offset_and_parses_back(client, headers, act_db):
    tenant_id, _ = _empresa(act_db)
    momento = datetime(2014, 6, 1, 3, 0, 0, 1, tzinfo=UTC)
    _registro(act_db, momento, tenant_id=tenant_id)
    (fila,) = _get(client, headers, empresa_id=str(tenant_id)).get_json()["actividad"]
    assert datetime.fromisoformat(fila["fecha"]) == momento
    # Colombia: la misma fecha local que muestra la web (UTC−5).
    assert (datetime.fromisoformat(fila["fecha"]) + COT).date().isoformat() == "2014-05-31"
