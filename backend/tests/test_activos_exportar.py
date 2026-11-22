"""Exportar la lista de activos a Excel (spec 015, T4; R1, R1a; A1; Q1–Q4).

- ``GET /activos/exportar`` es solo del admin (``403`` al contador, ``401`` sin sesión)
  y respeta ``q``, ``estado`` y ``ubicacion_id`` con el mismo resultado y el mismo orden
  que ``GET /activos`` (una sola consulta, sin paginar).
- Columnas de Q3 (A), sin fila de total; el dinero es un número desde el ``Decimal``
  exacto con formato COP; ningún texto se vuelve fórmula; cero filas → solo encabezado.
- Tope técnico de Q4 (B): más filas que ``MAX_FILAS_EXPORTACION`` → ``413``.
- Nombre de archivo fijo (sin datos de la clínica), ``no-store`` y ``nosniff``; nada de
  los datos en los registros. Otro tenant no aparece.

El archivo se lee con ``openpyxl`` (otra librería que la que lo escribe).
"""

import io
import logging
import re
import uuid
import zipfile
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal

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
    make_app,
    temporary_acceso_db,
)
from flask import Flask
from openpyxl import load_workbook
from sqlalchemy import text

from app.activos import exportar, service

ADMIN = bearer(ADMIN_A, TENANT_A)
CONTADOR = bearer(CONTADOR_A, TENANT_A, rol="contador")
ADMIN_OTRO = bearer(ADMIN_B, TENANT_B)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CENTAVO = Decimal("0.01")
ENCABEZADO = [
    "Código",
    "Nombre",
    "Categoría",
    "Ubicación",
    "Estado",
    "Serial",
    "Marca",
    "Modelo",
    "Subtipo",
    "Fecha de compra",
    "Precio de compra",
    "Registrado el",
]


@pytest.fixture(scope="module")
def exa_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("activos_exportar")


@pytest.fixture(scope="module")
def exa_app(exa_db) -> Iterator[Flask]:
    flask_app = make_app(exa_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(exa_app):
    return exa_app.test_client(use_cookies=False)


@pytest.fixture(autouse=True)
def tenant_limpio(exa_db) -> Iterator[None]:
    yield
    with exa_db.migrator.begin() as conn:
        for sql in (
            "delete from activo_evento",
            "delete from activo",
            "delete from ubicacion",
            "delete from categoria",
        ):
            conn.execute(text(sql))


class Catalogo:
    """Sede › Consultorios › Box 1 y Bodega; Biomédicos y Mobiliario (por la API)."""

    def __init__(self, client, headers=ADMIN):
        self.client, self.headers = client, headers
        sede = self._post("/ubicaciones", {"nombre": "Sede", "tipo": "sede"})["ubicacion"]["id"]
        self.sala = self._post(
            "/ubicaciones", {"nombre": "Consultorios", "tipo": "sala", "padre_id": sede}
        )["ubicacion"]["id"]
        self.box = self._post(
            "/ubicaciones", {"nombre": "Box 1", "tipo": "box", "padre_id": self.sala}
        )["ubicacion"]["id"]
        self.bodega = self._post(
            "/ubicaciones", {"nombre": "Bodega", "tipo": "sala", "padre_id": sede}
        )["ubicacion"]["id"]
        self.bio = self._post("/categorias", {"nombre": "Biomédicos"})["categoria"]["id"]
        self.mob = self._post("/categorias", {"nombre": "Mobiliario"})["categoria"]["id"]

    def _post(self, path, body):
        response = self.client.post(path, json=body, headers=self.headers)
        assert response.status_code in (200, 201), response.get_json()
        return response.get_json()

    def activo(self, nombre, precio="10.00", categoria=None, ubicacion=None, **extra) -> dict:
        body = {
            "id": str(uuid.uuid4()),
            "codigo": f"EXA-{uuid.uuid4().hex[:8]}".upper(),
            "nombre": nombre,
            "precio_compra": precio,
            "categoria_id": categoria or self.bio,
            "ubicacion_id": ubicacion or self.box,
            **extra,
        }
        return self._post("/activos", body)["activo"]

    def accion(self, activo, ruta, body):
        response = self.client.post(
            f"/activos/{activo['id']}/{ruta}",
            json=body,
            headers={**self.headers, "If-Match": f'"{activo["row_version"]}"'},
        )
        assert response.status_code == 200, response.get_json()
        return response.get_json()["activo"]


def exportar_(client, headers=ADMIN, **params):
    return client.get("/activos/exportar", query_string=params, headers=headers)


def filas(response) -> list[tuple]:
    """Filas de datos (sin el encabezado) de la única hoja."""
    assert response.status_code == 200, response.get_json()
    hoja = load_workbook(io.BytesIO(response.data)).worksheets[0]
    todas = list(hoja.iter_rows(values_only=True))
    assert list(todas[0]) == ENCABEZADO
    return todas[1:]


def lista_completa(client, **params) -> list[str]:
    """Códigos de ``GET /activos`` recorriendo todas las páginas, en su orden."""
    codigos, pagina = [], 1
    while True:
        response = client.get("/activos", query_string={**params, "pagina": pagina}, headers=ADMIN)
        assert response.status_code == 200, response.get_json()
        cuerpo = response.get_json()
        codigos += [a["codigo"] for a in cuerpo["activos"]]
        if pagina * cuerpo["por_pagina"] >= cuerpo["total"]:
            return codigos
        pagina += 1


def test_export_has_the_same_rows_and_order_as_the_list_with_each_filter(client):
    c = Catalogo(client)
    reparada = c.activo("Silla en reparación", categoria=c.mob)
    c.accion(reparada, "estado", {"estado": "en_reparacion"})
    baja = c.activo("Silla dada de baja", ubicacion=c.bodega)
    c.accion(baja, "baja", {"motivo": "perdido"})
    for i in range(28):  # más de una página de la lista (25)
        c.activo(f"Archivador {i}", ubicacion=c.bodega if i % 2 else c.box)
    for params in (
        {},
        {"q": "silla"},
        {"q": reparada["codigo"].lower()},
        {"estado": "en_reparacion"},
        {"estado": "dado_de_baja"},
        {"estado": "activo"},
        {"ubicacion_id": c.bodega},
        {"ubicacion_id": c.bodega, "estado": "activo", "q": "archivador"},
    ):
        esperados = lista_completa(client, **params)
        assert [f[0] for f in filas(exportar_(client, **params))] == esperados, params
    # «Todos» incluye los dados de baja, igual que la lista (Q3 A).
    assert baja["codigo"] in [f[0] for f in filas(exportar_(client))]


def test_each_column_has_the_decided_value(client):
    c = Catalogo(client)
    activo = c.activo(
        "Autoclave",
        precio="1390000.50",
        serial="SN-1",
        marca="Tuttnauer",
        modelo="2540",
        subtipo="Clase B",
        fecha_compra="2024-01-31",
    )
    c.accion(activo, "estado", {"estado": "en_reparacion"})
    sin_opcionales = c.activo("Silla", precio="389900.00", categoria=c.mob, ubicacion=c.bodega)
    por_codigo = {f[0]: f for f in filas(exportar_(client))}

    fila = por_codigo[activo["codigo"]]
    assert fila[:9] == (
        activo["codigo"],
        "Autoclave",
        "Biomédicos",
        "Consultorios › Box 1",
        "En reparación",
        "SN-1",
        "Tuttnauer",
        "2540",
        "Clase B",
    )
    assert fila[9] == datetime(2024, 1, 31)
    assert Decimal(str(fila[10])).quantize(CENTAVO) == Decimal("1390000.50")
    registrado = datetime.fromisoformat(activo["creado_en"]).astimezone(exportar.HORA_COLOMBIA)
    assert fila[11] == datetime.combine(registrado.date(), datetime.min.time())

    otra = por_codigo[sin_opcionales["codigo"]]
    assert otra[2:5] == ("Mobiliario", "Bodega", "Activo")
    assert otra[5:10] == (None, None, None, None, None)
    assert Decimal(str(otra[10])).quantize(CENTAVO) == Decimal("389900.00")
    # Sin fila de total (Q3 A): solo los dos activos.
    assert len(por_codigo) == 2


def test_money_is_an_exact_number_with_cop_format_and_there_are_no_formulas(client):
    c = Catalogo(client)
    c.activo("Autoclave", precio="1390000.50")
    response = exportar_(client)
    hoja = load_workbook(io.BytesIO(response.data)).worksheets[0]
    precio = hoja.cell(row=2, column=11)
    assert isinstance(precio.value, (int, float))
    assert "#,##0.00" in precio.number_format
    assert "dd/mm/yyyy" in hoja.cell(row=2, column=12).number_format
    with zipfile.ZipFile(io.BytesIO(response.data)) as z:
        hojas = "".join(z.read(n).decode() for n in z.namelist() if n.startswith("xl/worksheets/"))
    assert "<f>" not in hojas
    # Escrito desde el Decimal exacto, no desde un float redondeado.
    assert "<v>1390000.50</v>" in hojas


@pytest.mark.parametrize("peligroso", ["=1+1", "+57 300", "-2+3", "@SUMA(A1)"])
def test_text_that_looks_like_a_formula_stays_text(client, peligroso):
    c = Catalogo(client)
    c.activo(peligroso, serial=peligroso, marca=peligroso, modelo=peligroso, subtipo=peligroso)
    response = exportar_(client)
    hoja = load_workbook(io.BytesIO(response.data)).worksheets[0]
    for col in (2, 6, 7, 8, 9):
        celda = hoja.cell(row=2, column=col)
        assert celda.value == peligroso
        assert celda.data_type == "s", (col, celda.data_type)


def test_with_no_results_the_file_has_only_the_header(client):
    Catalogo(client)
    assert filas(exportar_(client)) == []
    assert filas(exportar_(client, q="no-existe")) == []


def test_sheet_has_a_filter_and_a_frozen_header(client):
    c = Catalogo(client)
    c.activo("Autoclave")
    c.activo("Silla")
    hoja = load_workbook(io.BytesIO(exportar_(client).data)).worksheets[0]
    assert hoja.title == "Activos"
    assert hoja.freeze_panes == "A2"
    assert hoja.auto_filter.ref == "A1:L3"


def test_download_headers_and_a_fixed_file_name(client):
    c = Catalogo(client)
    c.activo("Clínica & Ejemplo")
    response = exportar_(client, q="clínica")
    assert response.status_code == 200
    assert response.mimetype == XLSX
    disposicion = response.headers["Content-Disposition"]
    hoy = datetime.now(exportar.HORA_COLOMBIA).date()
    nombre = f"activos-{hoy:%Y%m%d}.xlsx"
    assert disposicion == f"attachment; filename=\"{nombre}\"; filename*=UTF-8''{nombre}"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_only_the_admin_exports_and_the_contador_gets_no_price(client):
    c = Catalogo(client)
    c.activo("Autoclave", precio="1390000.50")
    prohibido = exportar_(client, CONTADOR)
    assert prohibido.status_code == 403
    assert prohibido.mimetype == "application/json"
    assert "1390000" not in prohibido.get_data(as_text=True)
    assert prohibido.get_json()["error"]["code"] == "prohibido"
    assert exportar_(client, {}).status_code == 401


def test_other_tenant_is_not_exported(client):
    propio = Catalogo(client).activo("Autoclave")
    ajeno = Catalogo(client, ADMIN_OTRO).activo("Autoclave del otro")
    assert [f[0] for f in filas(exportar_(client))] == [propio["codigo"]]
    assert [f[0] for f in filas(exportar_(client, ADMIN_OTRO))] == [ajeno["codigo"]]
    # Filtrar por una ubicación del otro tenant no la revela: no hay filas.
    assert filas(exportar_(client, ubicacion_id=ajeno["ubicacion"]["id"])) == []


@pytest.mark.parametrize(
    "params",
    [{"estado": "otro"}, {"q": "x" * 121}, {"ubicacion_id": "no-es-uuid"}],
)
def test_invalid_filters_are_400(client, params):
    response = exportar_(client, **params)
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "solicitud_invalida"


def test_more_rows_than_the_cap_is_413_with_a_clear_message(client, monkeypatch):
    assert service.MAX_FILAS_EXPORTACION == 5_000  # Q4 (B), decidido por el humano.
    c = Catalogo(client)
    for i in range(3):
        c.activo(f"Archivador {i}")
    monkeypatch.setattr(service, "MAX_FILAS_EXPORTACION", 3)
    assert len(filas(exportar_(client))) == 3  # justo en el tope: se exporta
    c.activo("Uno más")
    response = exportar_(client)
    assert response.status_code == 413
    error = response.get_json()["error"]
    assert error["code"] == "exportacion_demasiado_grande"
    assert error["message"] == (
        "Hay más de 3 activos para exportar. Filtra por búsqueda, estado o ubicación."
    )
    # Con un filtro que deja menos filas, vuelve a funcionar.
    assert len(filas(exportar_(client, q="uno más"))) == 1


def test_export_does_not_log_names_codes_or_prices(client, caplog):
    c = Catalogo(client)
    activo = c.activo("Autoclave secreto", precio="1390000.50", serial="SN-SECRETO")
    with caplog.at_level(logging.DEBUG):
        assert exportar_(client, q="autoclave").status_code == 200
    registros = " ".join(r.getMessage() for r in caplog.records)
    assert not re.search(rf"1390000|Autoclave|SN-SECRETO|{activo['codigo']}", registros)


def test_registered_date_is_a_real_date(client):
    c = Catalogo(client)
    c.activo("Autoclave")
    (fila,) = filas(exportar_(client))
    assert isinstance(fila[11], datetime)
    assert fila[11].date() == datetime.now(exportar.HORA_COLOMBIA).date()


@pytest.mark.parametrize("tope", [1, 2])
def test_exactly_the_cap_is_200_and_one_more_is_413(client, monkeypatch, tope):
    c = Catalogo(client)
    for i in range(tope):
        c.activo(f"Archivador {i}")
    monkeypatch.setattr(service, "MAX_FILAS_EXPORTACION", tope)
    assert len(filas(exportar_(client))) == tope
    c.activo("Archivador extra")
    response = exportar_(client)
    assert response.status_code == 413
    assert response.get_json()["error"]["code"] == "exportacion_demasiado_grande"


def test_413_body_has_no_data_of_the_activos(client, monkeypatch):
    c = Catalogo(client)
    activos = [
        c.activo("Autoclave secreto", precio="1390000.50", serial="SN-SECRETO", marca="Tuttnauer"),
        c.activo("Silla secreta", precio="389900.00", categoria=c.mob, ubicacion=c.bodega),
    ]
    monkeypatch.setattr(service, "MAX_FILAS_EXPORTACION", 1)
    response = exportar_(client)
    assert response.status_code == 413
    assert response.mimetype == "application/json"
    cuerpo = response.get_data(as_text=True)
    assert set(response.get_json()) == {"error"}
    prohibidos = ["1390000", "389900", "Autoclave", "Silla", "SN-SECRETO", "Tuttnauer"]
    prohibidos += ["Biomédicos", "Mobiliario", "Bodega", "Box 1", "Consultorios"]
    for a in activos:
        prohibidos += [a["codigo"], a["id"], a["ubicacion"]["id"]]
    for dato in prohibidos:
        assert dato not in cuerpo, dato


CON_BARRA = "Ruta c\\d"


@pytest.mark.parametrize(
    ("q", "esperado"),
    [
        ("%", "Algodón 100% puro"),
        ("_", "Tubo a_b"),
        ("\\", CON_BARRA),
        ("0%", "Algodón 100% puro"),
    ],
)
def test_like_wildcards_in_q_are_literal_and_match_the_list(client, q, esperado):
    c = Catalogo(client)
    for nombre in ("Algodón 100% puro", "Tubo a_b", CON_BARRA, "Otro activo", "Silla"):
        c.activo(nombre)
    exportados = filas(exportar_(client, q=q))
    assert [f[0] for f in exportados] == lista_completa(client, q=q)
    assert [f[1] for f in exportados] == [esperado]


def test_percent_alone_does_not_export_everything(client):
    c = Catalogo(client)
    for nombre in ("Autoclave", "Silla", "Mesa"):
        c.activo(nombre)
    assert filas(exportar_(client, q="%")) == []
    assert filas(exportar_(client, q="_")) == []
    assert len(filas(exportar_(client))) == 3


PELIGROSOS_CATALOGO = [
    "=cmd|' /C calc'!A0",
    "+57 Sede",
    "-2 Bodega",
    "@Sala 1",
    "\tTabulada",
    "Con\nsalto",
]


@pytest.mark.parametrize("peligroso", PELIGROSOS_CATALOGO)
def test_category_and_location_names_that_look_like_formulas_stay_text(client, exa_db, peligroso):
    c = Catalogo(client)
    activo = c.activo("Autoclave")
    # La API no deja crear tabuladores ni saltos (nombres.py): se escriben directo en la
    # base para cubrir datos ya existentes o importados.
    with exa_db.migrator.begin() as conn:
        conn.execute(
            text("update categoria set nombre = :n where id = :id"),
            {"n": peligroso, "id": c.bio},
        )
        conn.execute(
            text("update ubicacion set nombre = :n where id = :id"),
            {"n": peligroso, "id": c.box},
        )
    response = exportar_(client)
    assert response.status_code == 200
    hoja = load_workbook(io.BytesIO(response.data)).worksheets[0]
    assert hoja.cell(row=2, column=1).value == activo["codigo"]
    categoria, ubicacion = hoja.cell(row=2, column=3), hoja.cell(row=2, column=4)
    assert categoria.value == peligroso
    assert ubicacion.value == f"Consultorios › {peligroso}"
    assert categoria.data_type == "s"
    assert ubicacion.data_type == "s"
    with zipfile.ZipFile(io.BytesIO(response.data)) as z:
        hojas = "".join(z.read(n).decode() for n in z.namelist() if n.startswith("xl/worksheets/"))
    assert "<f>" not in hojas
