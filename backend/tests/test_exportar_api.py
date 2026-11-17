"""Exportar el informe congelado (spec 009, T2–T3; R1–R7; A1–A3).

Los archivos se leen con librerías distintas de las que los escriben (``openpyxl`` para
el Excel, ``pypdf`` para el PDF) y cada cifra se compara con el JSON de
``GET /sesiones/{id}/informe``: la igualdad no depende de quien escribió el archivo.
"""

import io
import logging
import re
import uuid
import zipfile
from collections.abc import Iterator
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
from pypdf import PdfReader
from sqlalchemy import text
from test_cierre_api import Clinica

from app.conteo import exportar

ADMIN = bearer(ADMIN_A, TENANT_A)
CONTADOR = bearer(CONTADOR_A, TENANT_A, rol="contador")
ADMIN_OTRO = bearer(ADMIN_B, TENANT_B)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CENTAVO = Decimal("0.01")


@pytest.fixture(scope="module")
def exp_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("exportar_api")


@pytest.fixture(scope="module")
def exp_app(exp_db) -> Iterator[Flask]:
    flask_app = make_app(exp_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(exp_app):
    return exp_app.test_client(use_cookies=False)


@pytest.fixture(autouse=True)
def tenant_limpio(exp_db) -> Iterator[None]:
    yield
    with exp_db.migrator.begin() as conn:
        for sql in (
            "delete from sesion_detalle",
            "delete from sesion_empresa",
            "delete from sesion_no_encontrado",
            "delete from sesion_desglose",
            "delete from activo_evento",
            "delete from verificacion",
            "delete from sesion_conteo",
            "delete from activo",
            "delete from ubicacion",
            "delete from categoria",
        ):
            conn.execute(text(sql))


class ClinicaExp(Clinica):
    """Como la de la 008, pero el código no sale del nombre (aquí hay nombres con tilde y ``=``)."""

    def activo(self, nombre, precio, categoria=None, ubicacion=None) -> str:
        body = {
            "id": str(uuid.uuid4()),
            "codigo": f"EXP-{uuid.uuid4().hex[:6]}".upper(),
            "nombre": nombre,
            "precio_compra": precio,
            "categoria_id": categoria or self.bio,
            "ubicacion_id": ubicacion or self.box,
        }
        activo = self._post("/activos", body)["activo"]
        self.version[activo["id"]] = 1
        return activo["id"]


def cerrada(client) -> tuple[ClinicaExp, str, dict, dict[str, str]]:
    """Encontrados, no encontrados (uno en reparación, uno con nombre de fórmula), dos
    categorías y tres ubicaciones; devuelve la clínica, la sesión, su informe y activos."""
    c = ClinicaExp(client)
    ids = {
        "autoclave": c.activo("Autoclave", "1390000.50"),
        "silla": c.activo("Silla", "389900.00", c.mob, c.bodega),
        "formula": c.activo("=1+1", "100.00"),
        "lampara": c.activo("Lámpara", "2000000.00", c.mob, c.bodega),
    }
    c.reparacion(ids["silla"])
    sesion = c.abrir()
    c.verificar(sesion, ids["autoclave"])
    c.verificar(sesion, ids["lampara"], c.box)
    assert client.post(f"/sesiones/{sesion}/cerrar", headers=ADMIN).status_code == 200
    informe = client.get(f"/sesiones/{sesion}/informe", headers=ADMIN).get_json()
    return c, sesion, informe, ids


def dinero(valor) -> Decimal:
    return Decimal(str(valor)).quantize(CENTAVO)


def filas_desglose(hoja) -> list[list]:
    """Filas de datos de una hoja de desglose, con el dinero como Decimal."""
    filas = []
    for fila in hoja.iter_rows(min_row=2, values_only=True):
        if fila[0] is None:
            continue
        e, ue, n, un, r, ur, pct = fila[1:8]
        filas.append([fila[0], dinero(e), ue, dinero(n), un, dinero(r), ur, pct])
    return filas


def esperado_desglose(informe: dict, dimension: str) -> list[list]:
    def fila(etiqueta, f, prefijo):
        return [
            etiqueta,
            Decimal(f[f"{prefijo}encontrado"]),
            f["unidades_encontrado"],
            Decimal(f[f"{prefijo}no_encontrado"]),
            f["unidades_no_encontrado"],
            Decimal(f[f"{prefijo}registrado"]),
            f["unidades_registrado"],
            exportar.porcentaje(f["unidades_encontrado"], f["unidades_registrado"]),
        ]

    filas = [fila(f["etiqueta"], f, "total_") for f in informe["desglose"][dimension]]
    return [*filas, fila("Total", informe["totales"], "")]


def excel(client, sesion, headers=ADMIN):
    return client.get(f"/sesiones/{sesion}/informe/excel", headers=headers)


def libro(response):
    return load_workbook(io.BytesIO(response.data))


# --- Excel (T2) ----------------------------------------------------------------------------


def test_excel_has_exactly_the_figures_of_the_report(client):
    _, sesion, informe, _ = cerrada(client)
    response = excel(client, sesion)
    assert response.status_code == 200
    assert response.mimetype == XLSX
    wb = libro(response)
    assert wb.sheetnames == ["Informe", "Por categoría", "Por ubicación", "No encontrados"]

    portada = {fila[0]: fila[1:] for fila in wb["Informe"].iter_rows(values_only=True) if fila[0]}
    assert portada["Sesión"][0] == "Conteo nov 2026"
    assert portada["Fecha de corte"][0] == "30/11/2026"
    assert portada["Estado"][0] == "Informe congelado"
    t = informe["totales"]
    for rotulo, clave in (
        ("Encontrado", "encontrado"),
        ("No encontrado", "no_encontrado"),
        ("Total registrado", "registrado"),
    ):
        valor, unidades = portada[rotulo][:2]
        assert dinero(valor) == Decimal(t[clave]), rotulo
        assert unidades == t[f"unidades_{clave}"], rotulo
    assert portada["% de unidades encontradas"][0] == "50 %"

    assert filas_desglose(wb["Por categoría"]) == esperado_desglose(informe, "categorias")
    assert filas_desglose(wb["Por ubicación"]) == esperado_desglose(informe, "ubicaciones")

    lista = [f for f in wb["No encontrados"].iter_rows(min_row=2, values_only=True) if f[0]]
    *items, total = lista
    assert [(f[0], f[1], f[2], f[3], f[4], dinero(f[5])) for f in items] == [
        (
            n["codigo"],
            n["nombre"],
            n["categoria"]["nombre"],
            n["ubicacion"]["ruta"],
            "En reparación" if n["en_reparacion"] else None,
            Decimal(n["precio"]),
        )
        for n in informe["no_encontrados"]
    ]
    assert dinero(total[5]) == Decimal(t["no_encontrado"])
    assert total[0] == "2 activos no encontrados"


def test_excel_money_is_a_number_with_cop_format_and_no_formulas(client):
    _, sesion, _, _ = cerrada(client)
    response = excel(client, sesion)
    hoja = libro(response)["Por categoría"]
    celda = hoja.cell(row=2, column=2)
    assert isinstance(celda.value, (int, float))
    assert "#,##0.00" in celda.number_format
    with zipfile.ZipFile(io.BytesIO(response.data)) as z:
        for nombre in z.namelist():
            if nombre.startswith("xl/worksheets/"):
                assert "<f>" not in z.read(nombre).decode(), nombre
        # El número se escribe desde el Decimal exacto, no desde un float redondeado.
        hojas = "".join(z.read(n).decode() for n in z.namelist() if n.startswith("xl/worksheets/"))
        assert "<v>1390000.50</v>" in hojas


def test_excel_text_that_looks_like_a_formula_stays_text(client):
    _, sesion, _, _ = cerrada(client)
    hoja = libro(excel(client, sesion))["No encontrados"]
    celda = next(c for fila in hoja.iter_rows(min_row=2) for c in fila if c.value == "=1+1")
    assert celda.data_type == "s"


def test_excel_download_headers(client):
    _, sesion, _, _ = cerrada(client)
    response = excel(client, sesion)
    disposicion = response.headers["Content-Disposition"]
    assert disposicion.startswith("attachment;")
    assert 'filename="informe-conteo-nov-2026-corte-2026-11-30.xlsx"' in disposicion
    assert "filename*=UTF-8''informe-conteo-nov-2026-corte-2026-11-30.xlsx" in disposicion
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_excel_of_an_empty_session_has_zeros(client):
    c = ClinicaExp(client)
    sesion = c.abrir()
    assert client.post(f"/sesiones/{sesion}/cerrar", headers=ADMIN).status_code == 200
    wb = libro(excel(client, sesion))
    portada = {f[0]: f[1:] for f in wb["Informe"].iter_rows(values_only=True) if f[0]}
    assert dinero(portada["Total registrado"][0]) == Decimal("0.00")
    assert portada["Total registrado"][1] == 0
    assert filas_desglose(wb["Por categoría"]) == [
        ["Total", Decimal("0.00"), 0, Decimal("0.00"), 0, Decimal("0.00"), 0, "0 %"]
    ]


def test_excel_reads_the_frozen_report_after_later_changes(client):
    c, sesion, _, ids = cerrada(client)
    antes = [list(h.iter_rows(values_only=True)) for h in libro(excel(client, sesion)).worksheets]
    c.precio(ids["autoclave"], "1.00")
    c.mover(ids["silla"], c.box)
    client.patch(f"/categorias/{c.bio}", json={"nombre": "Equipos"}, headers=ADMIN)
    despues = [list(h.iter_rows(values_only=True)) for h in libro(excel(client, sesion)).worksheets]
    assert despues == antes


def test_excel_errors_roles_and_tenant(client):
    c = ClinicaExp(client)
    abierta = c.abrir()
    respuesta = excel(client, abierta)
    assert respuesta.status_code == 409
    assert respuesta.get_json()["error"]["code"] == "sesion_abierta"
    assert excel(client, str(uuid.uuid4())).status_code == 404
    assert client.post(f"/sesiones/{abierta}/cerrar", headers=ADMIN).status_code == 200
    assert excel(client, abierta, CONTADOR).status_code == 403
    assert excel(client, abierta, {}).status_code == 401
    assert excel(client, abierta, ADMIN_OTRO).status_code == 404


def test_export_does_not_log_figures_or_names(client, caplog):
    _, sesion, _, _ = cerrada(client)
    with caplog.at_level(logging.DEBUG):
        assert excel(client, sesion).status_code == 200
        assert client.get(f"/sesiones/{sesion}/informe/pdf", headers=ADMIN).status_code == 200
    registros = " ".join(r.getMessage() for r in caplog.records)
    assert not re.search(r"1390000|Autoclave|Conteo nov", registros)


# --- PDF (T3) ------------------------------------------------------------------------------


def pdf(client, sesion, headers=ADMIN):
    return client.get(f"/sesiones/{sesion}/informe/pdf", headers=headers)


def lineas_pdf(response) -> list[str]:
    lector = PdfReader(io.BytesIO(response.data))
    return [
        linea.strip() for pagina in lector.pages for linea in pagina.extract_text().splitlines()
    ]


def contiene_seguidas(lineas: list[str], esperadas: list[str]) -> bool:
    n = len(esperadas)
    return any(lineas[i : i + n] == esperadas for i in range(len(lineas) - n + 1))


def test_pdf_has_exactly_the_figures_of_the_report(client):
    _, sesion, informe, _ = cerrada(client)
    response = pdf(client, sesion)
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    lector = PdfReader(io.BytesIO(response.data))
    alto, ancho = float(lector.pages[0].mediabox.height), float(lector.pages[0].mediabox.width)
    assert (round(ancho), round(alto)) == (792, 612)  # Carta horizontal (Q3).
    lineas = lineas_pdf(response)
    assert "Informe · Conteo nov 2026" in lineas
    assert any("Fecha de corte 30/11/2026" in li and "Informe congelado" in li for li in lineas)
    t = informe["totales"]
    cop = exportar.formato_cop
    assert contiene_seguidas(
        lineas, [cop(Decimal(t[k])) for k in ("encontrado", "no_encontrado", "registrado")]
    )
    assert "50 % de las unidades encontradas." in lineas
    for dimension in ("categorias", "ubicaciones"):
        for fila in esperado_desglose(informe, dimension):
            etiqueta, e, ue, n, un, r, ur, pct = fila
            esperadas = [etiqueta, cop(e), str(ue), cop(n), str(un), cop(r), str(ur), pct]
            assert contiene_seguidas(lineas, esperadas), esperadas
    for n in informe["no_encontrados"]:
        esperadas = [n["codigo"], n["nombre"], n["categoria"]["nombre"], n["ubicacion"]["ruta"]]
        if n["en_reparacion"]:
            esperadas.append("En reparación")
        esperadas.append(cop(Decimal(n["precio"])))
        assert contiene_seguidas(lineas, esperadas), esperadas
    assert contiene_seguidas(lineas, ["2 activos no encontrados", cop(Decimal(t["no_encontrado"]))])
    assert lineas[-1] == "Página 1 de 1"


def test_pdf_download_headers(client):
    _, sesion, _, _ = cerrada(client)
    response = pdf(client, sesion)
    disposicion = response.headers["Content-Disposition"]
    assert disposicion.startswith("attachment;")
    assert 'filename="informe-conteo-nov-2026-corte-2026-11-30.pdf"' in disposicion
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_pdf_of_an_empty_session_has_zeros(client):
    c = Clinica(client)
    sesion = c.abrir()
    assert client.post(f"/sesiones/{sesion}/cerrar", headers=ADMIN).status_code == 200
    lineas = lineas_pdf(pdf(client, sesion))
    assert contiene_seguidas(lineas, ["$ 0,00", "$ 0,00", "$ 0,00"])
    assert contiene_seguidas(lineas, ["0 activos no encontrados", "$ 0,00"])


def test_pdf_reads_the_frozen_report_after_later_changes(client):
    c, sesion, _, ids = cerrada(client)
    antes = lineas_pdf(pdf(client, sesion))
    c.precio(ids["autoclave"], "1.00")
    c.mover(ids["silla"], c.box)
    client.patch(f"/categorias/{c.bio}", json={"nombre": "Equipos"}, headers=ADMIN)
    assert lineas_pdf(pdf(client, sesion)) == antes


def test_pdf_errors_roles_and_tenant(client):
    c = Clinica(client)
    abierta = c.abrir()
    assert pdf(client, abierta).get_json()["error"]["code"] == "sesion_abierta"
    assert pdf(client, str(uuid.uuid4())).status_code == 404
    assert client.post(f"/sesiones/{abierta}/cerrar", headers=ADMIN).status_code == 200
    assert pdf(client, abierta, CONTADOR).status_code == 403
    assert pdf(client, abierta, {}).status_code == 401
    assert pdf(client, abierta, ADMIN_OTRO).status_code == 404
