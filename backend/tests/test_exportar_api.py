"""Exportar el informe congelado (spec 009, T2–T3; R1–R7; A1–A3).

Los archivos se leen con librerías distintas de las que los escriben (``openpyxl`` para
el Excel, ``pypdf`` para el PDF) y cada cifra se compara con el JSON de
``GET /sesiones/{id}/informe``: la igualdad no depende de quien escribió el archivo.
"""

import io
import logging
import re
import uuid
import warnings
import zipfile
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
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
from botocore.exceptions import ClientError, EndpointConnectionError
from flask import Flask
from openpyxl import load_workbook
from PIL import Image
from pypdf import PdfReader
from sqlalchemy import text
from test_cierre_api import Clinica
from test_exportar_documento import (
    EMPRESA_HOSTIL,
    FORMULAS_PERMITIDAS,
    HOSTIL,
    SESION_HOSTIL,
    comprobar_libro_seguro,
)

from app.conteo import exportar
from app.conteo import exportar_estilo as est
from app.fotos.almacen import EXTENSION_KEY, CarpetaLocal, ClaveInvalida

ADMIN = bearer(ADMIN_A, TENANT_A)
CONTADOR = bearer(CONTADOR_A, TENANT_A, rol="contador")
ADMIN_OTRO = bearer(ADMIN_B, TENANT_B)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CENTAVO = Decimal("0.01")


@pytest.fixture(scope="module")
def exp_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("exportar_api")


@pytest.fixture(scope="module")
def exp_app(exp_db, tmp_path_factory) -> Iterator[Flask]:
    flask_app = make_app(exp_db)
    flask_app.extensions[EXTENSION_KEY] = CarpetaLocal(tmp_path_factory.mktemp("almacen"))
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
            "update empresa set logo_id = null",
            "delete from empresa",
            "delete from empresa_logo",
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


LIBRO = [
    "Todos los activos",
    "Por ubicación",
    "No encontrados",
    "Biomédicos",
    "Mobiliario",
    "Por categoría",
    "Resumen",
]


def filas_desglose(hoja, titulo: str) -> list[list]:
    """Filas de la tabla «titulo» (después de su cabecera, hasta Total): spec 019 (Q6), la
    hoja «Por ubicación» o «Por categoría», cuyo título está en A6."""
    filas, dentro = [], False
    for fila in hoja.iter_rows(values_only=True):
        if fila[0] == titulo:
            dentro = None  # la siguiente es la cabecera
            continue
        if dentro is None:
            dentro = True
            continue
        if dentro:
            e, ue, n, un, r, ur, pct = fila[1:8]
            filas.append([fila[0], dinero(e), ue, dinero(n), un, dinero(r), ur, Decimal(str(pct))])
            if fila[0] == "Total":
                break
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
            exportar.fraccion_encontrada(f["unidades_encontrado"], f["unidades_registrado"]),
        ]

    filas = [fila(f["etiqueta"], f, "total_") for f in informe["desglose"][dimension]]
    return [*filas, fila("Total", informe["totales"], "")]


def tarjetas(hoja) -> dict[str, tuple]:
    """Tarjetas del tablero del Resumen: rótulo → (celda del valor, texto de debajo)."""
    rotulos = ("Encontrado", "No encontrado", "Total registrado", "% encontrado")
    for fila in hoja.iter_rows():
        valores = [c.value for c in fila]
        if all(r in valores for r in rotulos):
            resultado = {}
            for celda in fila:
                if celda.value in rotulos:
                    valor = hoja.cell(row=celda.row + 1, column=celda.column)
                    debajo = hoja.cell(row=celda.row + 2, column=celda.column).value
                    resultado[celda.value] = (valor, debajo)
            return resultado
    raise AssertionError("el Resumen no tiene las cuatro tarjetas")


def excel(client, sesion, headers=ADMIN):
    return client.get(f"/sesiones/{sesion}/informe/excel", headers=headers)


def libro(response):
    return load_workbook(io.BytesIO(response.data))


def activos_de_hoja(hoja) -> tuple[list[tuple], tuple]:
    """Filas de una hoja de lista (bajo la cabecera «Código») y su fila de total, que va
    fija encima de la cabecera (spec 015, T5)."""
    filas, total, dentro = [], None, False
    for fila in hoja.iter_rows(values_only=True):
        if not dentro and fila[0] == "Total":
            total = fila
        elif not dentro and fila[0] == "Código":
            dentro = True
        elif dentro and fila[0] is not None:
            filas.append(fila)
    assert total is not None, "la hoja no tiene fila de total"
    return filas, total


def fila_de(hoja, valor) -> int:
    """Número de fila (desde 1) de la primera celda con ese valor."""
    return next(c.row for fila in hoja.iter_rows() for c in fila if c.value == valor)


def detalle_congelado(exp_db, sesion) -> list[tuple]:
    """``sesion_detalle`` tal cual, en el orden de ``cierre.detalle``."""
    with exp_db.migrator.begin() as conn:
        return [
            tuple(f)
            for f in conn.execute(
                text(
                    "select codigo, nombre, categoria_nombre, marca, serial, ubicacion_ruta,"
                    " encontrada_ruta, estado_fisico, encontrado, en_reparacion, precio"
                    " from sesion_detalle where sesion_id = :s"
                    " order by lower(categoria_nombre), encontrado desc, codigo"
                ),
                {"s": sesion},
            )
        ]


def codigo(client, activo_id) -> str:
    return client.get(f"/activos/{activo_id}", headers=ADMIN).get_json()["activo"]["codigo"]


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (300, 100), (14, 116, 144, 255)).save(buffer, "PNG")
    return buffer.getvalue()


# --- Excel (spec 009 T2; spec 013 T4: libro v3) ---------------------------------------------


def test_excel_has_a_summary_one_sheet_per_category_and_the_missing(client):
    _, sesion, informe, _ = cerrada(client)
    response = excel(client, sesion)
    assert response.status_code == 200
    assert response.mimetype == XLSX
    wb = libro(response)
    # Spec 019 (Q6): el orden de la plantilla; el libro abre en la primera hoja (Q11).
    assert wb.sheetnames == LIBRO
    assert wb.active.title == "Todos los activos"

    resumen = wb["Resumen"]
    t = informe["totales"]
    cartas = tarjetas(resumen)
    for rotulo, clave in (
        ("Encontrado", "encontrado"),
        ("No encontrado", "no_encontrado"),
        ("Total registrado", "registrado"),
    ):
        valor, unidades = cartas[rotulo]
        assert dinero(valor.value) == Decimal(t[clave])
        assert "#,##0.00" in valor.number_format
        assert unidades.startswith(f"{t[f'unidades_{clave}']} unidad")
    # Spec 015 (T5): el % es un número con formato porcentaje, no texto.
    pct, debajo = cartas["% encontrado"]
    assert isinstance(pct.value, (int, float)) and Decimal(str(pct.value)) == Decimal("0.5")
    assert pct.number_format == est.FORMATO_PORCENTAJE
    assert debajo == "de las unidades registradas"
    # Criterio 8: las dos hojas de desglose dicen exactamente lo de ``cierre.informe``.
    por_categoria, por_ubicacion = wb["Por categoría"], wb["Por ubicación"]
    assert filas_desglose(por_categoria, "Por categoría") == esperado_desglose(
        informe, "categorias"
    )
    assert filas_desglose(por_ubicacion, "Por ubicación") == esperado_desglose(
        informe, "ubicaciones"
    )
    for hoja in (por_categoria, por_ubicacion):
        reglas = [r for rango in hoja.conditional_formatting for r in rango.rules]
        assert reglas and all(r.type == "dataBar" for r in reglas), hoja.title

    items, total = activos_de_hoja(wb["No encontrados"])
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
    assert total[1] == "2 activos no encontrados"


def test_summary_has_the_template_cards_and_the_closing_context(client):
    """Spec 019 (Q7): el Resumen de la plantilla (título, tarjetas) y, al final, la sesión,
    quién cerró y cuándo (hora de Colombia), la moneda, el estado y la nota de cifras
    congeladas; el corte, en el bloque. Impresión horizontal 1 × 1 (Q12), sin centrar."""
    _, sesion, informe, _ = cerrada(client)
    resumen = libro(excel(client, sesion))["Resumen"]
    assert resumen["C2"].value == "Informe de activos"
    assert resumen["C3"].value.endswith("· corte 30/11/2026")
    contexto = exportar.FILA_CONTEXTO_RESUMEN + 1
    filas = [
        [c for c in fila if c is not None]
        for fila in resumen.iter_rows(min_row=contexto, values_only=True)
    ]
    cerrada_en = datetime.fromisoformat(informe["sesion"]["cerrada_en"])
    hora = cerrada_en.astimezone(timezone(timedelta(hours=-5)))
    cuando = exportar._fecha_hora(informe["sesion"]["cerrada_en"])
    assert cuando.startswith(f"{hora:%d/%m/%Y}, ")
    assert filas == [
        ["Sesión", "Conteo nov 2026"],
        ["Cerró", ADMIN_A.nombre, "Cerrada", cuando],
        ["Moneda", "COP"],
        ["Estado", "Informe congelado"],
        [exportar.NOTA],
    ]
    assert resumen.page_setup.orientation == "landscape"
    assert resumen.sheet_properties.pageSetUpPr.fitToPage
    assert resumen.page_setup.fitToWidth in (None, 1) and resumen.page_setup.fitToHeight in (
        None,
        1,
    )
    assert not resumen.print_options.horizontalCentered
    assert resumen.freeze_panes is None


def test_flat_sheet_has_one_row_per_asset_of_the_frozen_universe(client, exp_db):
    """Spec 015 (T5): «Todos los activos» = ``sesion_detalle``, sin leer ``activo``."""
    _, sesion, _, _ = cerrada(client)
    hoja = libro(excel(client, sesion))["Todos los activos"]
    filas, _ = activos_de_hoja(hoja)
    assert [
        (f[0], f[1], f[2], f[3], f[4], f[5], f[6], f[7], f[8], dinero(f[9])) for f in filas
    ] == [
        (
            codigo_,
            nombre,
            categoria,
            marca,
            serial,
            ubicacion,
            encontrada,
            "Dañado"
            if estado == "danado"
            else "Ok"
            if estado == "ok"
            else "En reparación"
            if reparacion
            else None,
            "Encontrado" if encontrado else "No encontrado",
            Decimal(precio),
        )
        for (
            codigo_,
            nombre,
            categoria,
            marca,
            serial,
            ubicacion,
            encontrada,
            estado,
            encontrado,
            reparacion,
            precio,
        ) in detalle_congelado(exp_db, sesion)
    ]
    assert len(filas) == 4
    assert [c.value for c in hoja[fila_de(hoja, "Código")]][:10] == list(exportar.COLUMNAS_PLANA)


def test_flat_sheet_squares_with_the_report_to_the_cent(client):
    """Cuadre (spec 015, T5): la hoja plana suma lo mismo que el informe, cero diferencias,
    en total, por resultado, por categoría y por ubicación esperada; y su fila de total es
    la del informe (no una suma del exportador)."""
    _, sesion, informe, _ = cerrada(client)
    wb = libro(excel(client, sesion))
    filas, total = activos_de_hoja(wb["Todos los activos"])
    t = informe["totales"]
    precio = {f[0]: dinero(f[9]) for f in filas}

    def suma(cond) -> tuple[Decimal, int]:
        sel = [precio[f[0]] for f in filas if cond(f)]
        return sum(sel, Decimal("0.00")), len(sel)

    assert suma(lambda f: True) == (Decimal(t["registrado"]), t["unidades_registrado"])
    assert suma(lambda f: f[8] == "Encontrado") == (
        Decimal(t["encontrado"]),
        t["unidades_encontrado"],
    )
    assert suma(lambda f: f[8] == "No encontrado") == (
        Decimal(t["no_encontrado"]),
        t["unidades_no_encontrado"],
    )
    for dimension, col in (("categorias", 2), ("ubicaciones", 5)):
        for d in informe["desglose"][dimension]:
            assert suma(lambda f, d=d, col=col: f[col] == d["etiqueta"]) == (
                Decimal(d["total_registrado"]),
                d["unidades_registrado"],
            ), d["etiqueta"]
    assert dinero(total[9]) == Decimal(t["registrado"])
    assert total[8] == "4 activos"
    assert total[1] == "Todos los activos"


def test_flat_sheet_is_a_table_with_header_filters_and_print_setup(client):
    _, sesion, _, _ = cerrada(client)
    response = excel(client, sesion)
    hoja = libro(response)["Todos los activos"]
    cabecera = fila_de(hoja, "Código")
    tabla = hoja.tables["Activos"]
    assert tabla.ref == f"A{cabecera}:J{cabecera + 4}"
    assert tabla.totalsRowCount in (None, 0)
    # Total encima de la cabecera; sin paneles inmovilizados (decisión del humano 2026-11-24:
    # la línea del corte no se puede ocultar). Al imprimir, la cabecera se repite.
    assert hoja.freeze_panes is None
    assert fila_de(hoja, "Total") < cabecera
    assert hoja.print_title_rows.replace("$", "") == f"{cabecera}:{cabecera}"
    assert hoja.page_setup.orientation == "landscape"
    # Una página de ancho (fitToWidth=1 es el valor por omisión) y las que haga falta de alto.
    assert hoja.sheet_properties.pageSetUpPr.fitToPage
    assert hoja.page_setup.fitToWidth in (None, 1) and hoja.page_setup.fitToHeight == 0
    # El nombre con forma de fórmula es texto; el precio, número COP.
    celda = next(c for fila in hoja.iter_rows() for c in fila if c.value == "=1+1")
    assert celda.data_type == "s"
    precio = hoja.cell(row=celda.row, column=10)
    assert isinstance(precio.value, (int, float)) and "#,##0.00" in precio.number_format


def test_list_sheets_keep_their_total_above_the_header(client):
    _, sesion, _, _ = cerrada(client)
    wb = libro(excel(client, sesion))
    for nombre in ("Todos los activos", "Biomédicos", "No encontrados"):
        hoja = wb[nombre]
        cabecera = fila_de(hoja, "Código")
        assert fila_de(hoja, "Total") == cabecera - 1, nombre
        assert hoja.freeze_panes is None, nombre  # sin paneles inmovilizados (2026-11-24)
        assert hoja.auto_filter.ref or hoja.tables, nombre
        # Nada después de la última fila de datos: el total ya no va al final.
        filas, _ = activos_de_hoja(hoja)
        assert hoja.max_row == cabecera + len(filas), nombre


def test_columns_have_the_template_widths_whatever_the_content(client):
    """Spec 019 (D-1, B15): anchos fijos de la plantilla, no calculados por contenido."""
    _, sesion, _, _ = cerrada(client)
    wb = libro(excel(client, sesion))
    for nombre, anchos in (
        ("Todos los activos", (14, 26, 18, 18, 22, 22, 20, 16, 16, 18)),
        ("Biomédicos", (14, 26, 18, 18, 22, 22, 20, 16, 16, 18)),
        ("No encontrados", (14, 26, 18, 18, 22, 22, 20, 16, 16, 18, 13)),
    ):
        hoja = wb[nombre]
        for col, ancho in enumerate(anchos, start=1):
            # XlsxWriter junta columnas seguidas del mismo ancho en un solo <col min max>.
            dim = next(d for d in hoja.column_dimensions.values() if d.min <= col <= d.max)
            assert dim.width == ancho, (nombre, col)
            assert bool(dim.hidden) is (nombre == "No encontrados" and col >= 7), (nombre, col)


def test_found_elsewhere_is_a_full_row_rule_and_rows_are_uniform(client):
    """Spec 019 (B11): sin filas alternas ni colores fijos por celda; lo encontrado en otra
    ubicación se marca con una regla de fila completa (cursiva y fondo ámbar)."""
    _, sesion, _, _ = cerrada(client)
    hoja = libro(excel(client, sesion))["Todos los activos"]
    (rango,) = list(hoja.conditional_formatting)
    (regla,) = rango.rules
    assert str(rango.sqref) == "A10:J499"
    assert regla.type == "expression"
    assert regla.formula == ['AND($F10<>"",$G10<>"",$F10<>$G10)']
    assert regla.dxf.font.i and regla.dxf.fill.bgColor.rgb.endswith("FDE68A")

    def fila(nombre: str):
        return [hoja.cell(row=fila_de(hoja, nombre), column=c) for c in range(1, 11)]

    # La lámpara se esperaba en la bodega y se encontró en el box: F ≠ G (la regla aplica).
    lampara = fila("Lámpara")
    assert (lampara[5].value, lampara[6].value) == ("Bodega", "Consultorios › Box 1")
    # El autoclave, donde se esperaba (F = G); la silla, no encontrada (G vacía).
    autoclave, silla = fila("Autoclave"), fila("Silla")
    assert autoclave[5].value == autoclave[6].value
    assert silla[6].value is None
    for celdas in (lampara, autoclave, silla):
        for c in celdas:
            assert not c.font.i and c.fill.fill_type in (None, "none"), c.coordinate
            if c.value is not None:  # sin verde/rojo/ámbar fijos: la tinta de la plantilla
                assert c.font.color.rgb == "FF111827", c.coordinate


def test_each_category_sheet_lists_its_assets_and_its_frozen_total(client):
    c, sesion, informe, ids = cerrada(client)
    wb = libro(excel(client, sesion))
    desglose = {f["etiqueta"]: f for f in informe["desglose"]["categorias"]}
    esperado = {
        "Biomédicos": {ids["autoclave"]: "Encontrado", ids["formula"]: "No encontrado"},
        "Mobiliario": {ids["lampara"]: "Encontrado", ids["silla"]: "No encontrado"},
    }
    for categoria, activos in esperado.items():
        filas, total = activos_de_hoja(wb[categoria])
        assert {f[0]: f[7] for f in filas} == {codigo(client, i): r for i, r in activos.items()}
        # Encontrados primero; el total y las unidades son los del desglose congelado.
        assert [f[7] for f in filas] == ["Encontrado", "No encontrado"]
        assert sum(dinero(f[8]) for f in filas) == Decimal(desglose[categoria]["total_registrado"])
        assert dinero(total[8]) == Decimal(desglose[categoria]["total_registrado"])
        assert total[1] == categoria and total[7] == "2 activos"
    filas, _ = activos_de_hoja(wb["Mobiliario"])
    lampara = next(f for f in filas if f[1] == "Lámpara")
    # Esperada en la bodega y encontrada en el box: las dos rutas y su estado.
    assert (lampara[4], lampara[5], lampara[6]) == ("Bodega", "Consultorios › Box 1", "Ok")
    silla = next(f for f in filas if f[1] == "Silla")
    assert (silla[5], silla[6], silla[7]) == (None, "En reparación", "No encontrado")


def test_excel_money_is_a_number_with_cop_format_and_no_formulas(client):
    _, sesion, _, _ = cerrada(client)
    response = excel(client, sesion)
    filas, _ = activos_de_hoja(libro(response)["Biomédicos"])
    hoja = libro(response)["Biomédicos"]
    celda = next(c for fila in hoja.iter_rows() for c in fila if c.value == filas[0][0])
    precio = hoja.cell(row=celda.row, column=9)
    assert isinstance(precio.value, (int, float))
    assert "#,##0.00" in precio.number_format
    with zipfile.ZipFile(io.BytesIO(response.data)) as z:
        hojas = "".join(z.read(n).decode() for n in z.namelist() if n.startswith("xl/worksheets/"))
        assert "<f>" not in hojas
        # Solo la fórmula fija del formato condicional de fila completa (spec 019, B11).
        formulas = set(re.findall(r"<formula>(.*?)</formula>", hojas))
        assert formulas and formulas <= FORMULAS_PERMITIDAS
        # El número se escribe desde el Decimal exacto, no desde un float redondeado.
        assert "<v>1390000.50</v>" in hojas


def test_excel_text_that_looks_like_a_formula_stays_text(client):
    _, sesion, _, _ = cerrada(client)
    wb = libro(excel(client, sesion))
    for nombre in ("Biomédicos", "No encontrados"):
        celda = next(c for fila in wb[nombre].iter_rows() for c in fila if c.value == "=1+1")
        assert celda.data_type == "s", nombre


def test_every_sheet_carries_the_frozen_company_and_its_logo(client):
    datos = {
        "nombre": "Clínica & Ejemplo S.A.S.",
        "direccion": "Calle 10 # 5-20, Cartago",
        "nit": "900123456-8",
    }
    respuesta = client.put("/empresa", json=datos, headers=ADMIN)
    assert respuesta.status_code == 200, respuesta.get_json()
    subida = client.put(
        "/empresa/logo",
        data={"logo_id": str(uuid.uuid4()), "archivo": (io.BytesIO(_png()), "l.png")},
        headers=ADMIN,
        content_type="multipart/form-data",
    )
    assert subida.status_code == 201, subida.get_json()
    _, sesion, _, _ = cerrada(client)
    wb = libro(excel(client, sesion))
    assert wb.sheetnames == LIBRO
    # Spec 019 (T5): todas las hojas, Resumen incluido, llevan el bloque de la plantilla con
    # la empresa congelada y el pie «Página &P de &N»; ninguna, encabezado de impresión.
    for hoja in wb.worksheets:
        assert hoja["C2"].value == "Informe de activos", hoja.title
        assert hoja["C3"].value == "Informe · Clínica & Ejemplo S.A.S. · corte 30/11/2026", (
            hoja.title
        )
        # Empresa (C), Contacto (E) y Dirección (G o F) bajo sus rótulos (2026-11-24).
        assert hoja["C4"].value == "Empresa", hoja.title
        assert hoja["C5"].value == "Clínica & Ejemplo S.A.S.\nNIT 900.123.456-8", hoja.title
        direccion = "F5" if hoja.title == "No encontrados" else "G5"
        assert hoja[direccion].value == "Calle 10 # 5-20, Cartago", hoja.title
        assert hoja.HeaderFooter.oddFooter.left.text.strip() == "Generado con AssetControl"
        assert hoja.HeaderFooter.oddFooter.right.text.strip() == "Página &P de &N", hoja.title
        assert not hoja.HeaderFooter.oddHeader.left.text, hoja.title
        assert not hoja.HeaderFooter.oddHeader.right.text, hoja.title
        assert len(hoja._images) == 1, hoja.title
        assert hoja.page_setup.orientation == "landscape"


class ClinicaOtra(ClinicaExp):
    """La misma clínica de prueba, en el tenant B."""

    def _post(self, path, body, headers=ADMIN_OTRO):
        return super()._post(path, body, headers)


def hostil(client) -> str:
    """Sesión cerrada con empresa, sesión, categoría, ubicación y activos de texto hostil
    (el código no: la API solo acepta ``A-Z0-9._/-``; se prueba en el documento)."""
    datos = {"nombre": EMPRESA_HOSTIL, "direccion": "Calle 10 # 5-20, Cartago"}
    assert client.put("/empresa", json=datos, headers=ADMIN).status_code == 200
    c = ClinicaExp(client)
    categoria = c._post("/categorias", {"nombre": HOSTIL})["categoria"]["id"]
    lugar = c._post("/ubicaciones", {"nombre": HOSTIL, "tipo": "sala", "padre_id": c.sede})
    lugar = lugar["ubicacion"]["id"]
    ids = []
    for _ in range(2):
        cuerpo = {
            "id": str(uuid.uuid4()),
            "codigo": f"EXP-{uuid.uuid4().hex[:6]}".upper(),
            "nombre": HOSTIL,
            "marca": HOSTIL,
            "serial": HOSTIL,
            "precio_compra": "100.00",
            "categoria_id": categoria,
            "ubicacion_id": lugar,
        }
        ids.append(c._post("/activos", cuerpo)["activo"]["id"])
    sesion = c._post("/sesiones", {"nombre": SESION_HOSTIL, "fecha_corte": "2026-11-30"})
    sesion = sesion["sesion"]["id"]
    c.verificar(sesion, ids[0], lugar)
    assert client.post(f"/sesiones/{sesion}/cerrar", headers=ADMIN).status_code == 200
    return sesion


def test_hostile_text_from_the_api_stays_text_end_to_end(client):
    sesion = hostil(client)
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)  # XlsxWriter avisaría con el texto
        response = excel(client, sesion)
    assert response.status_code == 200
    comprobar_libro_seguro(response.data, EMPRESA_HOSTIL, SESION_HOSTIL)
    wb = libro(response)
    assert '=HYPERLINK("http evil","x")' in wb.sheetnames
    for nombre in ("Todos los activos", '=HYPERLINK("http evil","x")', "No encontrados"):
        valores = [c.value for fila in wb[nombre].iter_rows() for c in fila]
        assert HOSTIL in valores, nombre


def test_hostile_session_of_one_tenant_never_reaches_another(client):
    sesion = hostil(client)
    assert excel(client, sesion, ADMIN_OTRO).status_code == 404
    assert pdf(client, sesion, ADMIN_OTRO).status_code == 404
    otra = ClinicaOtra(client)
    otra.activo("Silla", "10.00")
    propia = otra.abrir()
    assert client.post(f"/sesiones/{propia}/cerrar", headers=ADMIN_OTRO).status_code == 200
    response = excel(client, propia, ADMIN_OTRO)
    assert response.status_code == 200
    wb = libro(response)
    textos = [c for h in wb.worksheets for f in h.iter_rows(values_only=True) for c in f if c]
    assert not {HOSTIL, EMPRESA_HOSTIL} & set(textos)
    assert not any(isinstance(t, str) and SESION_HOSTIL in t for t in textos)
    assert '=HYPERLINK("http evil","x")' not in wb.sheetnames


def test_a_category_named_like_the_flat_sheet_gets_its_own_sheet(client):
    c = ClinicaExp(client)
    todos = c._post("/categorias", {"nombre": "Todos los activos"})["categoria"]["id"]
    uno = c.activo("Autoclave", "1390000.50")
    dos = c.activo("Archivador", "50.00", todos)
    sesion = c.abrir()
    c.verificar(sesion, uno)
    c.verificar(sesion, dos)
    assert client.post(f"/sesiones/{sesion}/cerrar", headers=ADMIN).status_code == 200
    wb = libro(excel(client, sesion))
    assert wb.sheetnames == [
        "Todos los activos",
        "Por ubicación",
        "No encontrados",
        "Biomédicos",
        "Todos los activos (2)",
        "Por categoría",
        "Resumen",
    ]
    plana = wb["Todos los activos"]
    cabecera = fila_de(plana, "Código")
    assert plana.tables["Activos"].ref == f"A{cabecera}:J{cabecera + 2}"
    filas, total = activos_de_hoja(plana)
    assert {f[1] for f in filas} == {"Autoclave", "Archivador"}
    assert total[1] == "Todos los activos" and total[8] == "2 activos"
    filas, total = activos_de_hoja(wb["Todos los activos (2)"])
    assert [f[1] for f in filas] == ["Archivador"]
    assert total[1] == "Todos los activos" and total[7] == "1 activo"
    assert dinero(total[8]) == Decimal("50.00")


def test_excel_download_headers(client):
    _, sesion, _, _ = cerrada(client)
    response = excel(client, sesion)
    disposicion = response.headers["Content-Disposition"]
    assert disposicion.startswith("attachment;")
    assert 'filename="informe-conteo-nov-2026-corte-2026-11-30.xlsx"' in disposicion
    assert "filename*=UTF-8''informe-conteo-nov-2026-corte-2026-11-30.xlsx" in disposicion
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_excel_of_an_empty_session_has_zeros_and_no_category_sheets(client):
    c = ClinicaExp(client)
    sesion = c.abrir()
    assert client.post(f"/sesiones/{sesion}/cerrar", headers=ADMIN).status_code == 200
    wb = libro(excel(client, sesion))
    assert wb.sheetnames == ["Por ubicación", "No encontrados", "Por categoría", "Resumen"]
    for nombre in ("Por ubicación", "Por categoría"):
        assert filas_desglose(wb[nombre], nombre) == [
            ["Total", Decimal("0.00"), 0, Decimal("0.00"), 0, Decimal("0.00"), 0, Decimal("0")]
        ]
    assert all(h._images == [] for h in wb.worksheets)


def test_session_closed_before_013_has_no_category_sheets_and_says_so(client, exp_db):
    _, sesion, _, _ = cerrada(client)
    with exp_db.migrator.begin() as conn:
        conn.execute(text("delete from sesion_detalle"))
        conn.execute(text("delete from sesion_empresa"))
    wb = libro(excel(client, sesion))
    assert wb.sheetnames == ["Por ubicación", "No encontrados", "Por categoría", "Resumen"]
    textos = [c for fila in wb["Resumen"].iter_rows(values_only=True) for c in fila if c]
    # Spec 019 (Q7): los dos avisos, al final del Resumen.
    assert textos[-2:] == [exportar.SIN_DETALLE, exportar.EMPRESA_VIGENTE]


def test_excel_reads_the_frozen_report_after_later_changes(client):
    c, sesion, _, ids = cerrada(client)

    def contenido():
        return [
            list(h.iter_rows(values_only=True)) for h in libro(excel(client, sesion)).worksheets
        ]

    antes = contenido()
    c.precio(ids["autoclave"], "1.00")
    c.mover(ids["silla"], c.box)
    client.patch(f"/categorias/{c.bio}", json={"nombre": "Equipos"}, headers=ADMIN)
    client.put(
        "/empresa", json={"nombre": "Nombre nuevo", "direccion": "Otra dirección"}, headers=ADMIN
    )
    assert contenido() == antes


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


# --- Spec 019 (T4): un fallo del almacén al leer el logo congelado degrada a «sin logo» ------


class AlmacenQueFalla:
    """Almacén falso: ``leer`` lanza el error dado (S3 caído, sin permiso, disco roto)."""

    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.lecturas = 0

    def guardar(self, *_args) -> None:
        raise AssertionError("no se escribe en el almacén al exportar")

    def leer(self, _clave: str) -> bytes:
        self.lecturas += 1
        raise self.error

    def borrar(self, *_args) -> None:
        raise AssertionError("no se borra del almacén al exportar")


ERRORES_DEL_ALMACEN = [
    pytest.param(OSError("disco no disponible"), id="oserror"),
    pytest.param(
        ClientError({"Error": {"Code": "AccessDenied", "Message": "denegado"}}, "GetObject"),
        id="clienterror",
    ),
    pytest.param(EndpointConnectionError(endpoint_url="https://almacen.invalido"), id="botocore"),
]
EMPRESA_CON_LOGO = {
    "nombre": "Clínica Ficticia de Prueba S.A.S.",
    "direccion": "Calle Falsa 00 # 00-00",
    "nit": "900123456-8",
    "telefono": "600 000 0000",
    "correo": "contacto@ejemplo.test",
}


def cerrada_con_logo(client) -> tuple[str, dict, str, ClinicaExp]:
    """Sesión cerrada con la empresa y su logo congelados; devuelve sesión, informe, logo y
    la clínica de prueba."""
    assert client.put("/empresa", json=EMPRESA_CON_LOGO, headers=ADMIN).status_code == 200
    logo_id = str(uuid.uuid4())
    subida = client.put(
        "/empresa/logo",
        data={"logo_id": logo_id, "archivo": (io.BytesIO(_png()), "l.png")},
        headers=ADMIN,
        content_type="multipart/form-data",
    )
    assert subida.status_code == 201, subida.get_json()
    c, sesion, informe, _ = cerrada(client)
    return sesion, informe, logo_id, c


@pytest.mark.parametrize("error", ERRORES_DEL_ALMACEN)
def test_if_the_store_fails_the_excel_is_complete_without_logo(
    client, exp_app, monkeypatch, caplog, error
):
    """Req. 8: el logo es decorativo; un fallo del almacén no tumba el informe (ni ``500``):
    el Excel sale completo y con las cifras congeladas, sin imagen."""
    sesion, informe, logo_id, _ = cerrada_con_logo(client)
    con_logo = libro(excel(client, sesion))
    almacen = AlmacenQueFalla(error)
    monkeypatch.setitem(exp_app.extensions, EXTENSION_KEY, almacen)
    with caplog.at_level(logging.DEBUG):
        response = excel(client, sesion)
    assert response.status_code == 200
    assert response.mimetype == XLSX
    assert almacen.lecturas == 1
    wb = libro(response)
    assert wb.sheetnames == con_logo.sheetnames
    for hoja in wb.worksheets:
        assert hoja._images == [], hoja.title
        filas = list(hoja.iter_rows(values_only=True))
        assert filas == list(con_logo[hoja.title].iter_rows(values_only=True)), hoja.title
    items, total = activos_de_hoja(wb["Todos los activos"])
    assert len(items) == informe["totales"]["unidades_registrado"]
    assert dinero(total[9]) == Decimal(informe["totales"]["registrado"])
    registros = " ".join(r.getMessage() for r in caplog.records)
    for dato in [logo_id, str(TENANT_A), "almacen.invalido", *EMPRESA_CON_LOGO.values()]:
        assert dato not in registros, dato


@pytest.mark.parametrize("error", ERRORES_DEL_ALMACEN)
def test_if_the_store_fails_the_pdf_is_complete_without_logo(client, exp_app, monkeypatch, error):
    """La misma lectura del logo sirve al PDF: también degrada a «sin logo»."""
    sesion, informe, _, _ = cerrada_con_logo(client)
    monkeypatch.setitem(exp_app.extensions, EXTENSION_KEY, AlmacenQueFalla(error))
    response = pdf(client, sesion)
    assert response.status_code == 200
    assert response.mimetype == exportar.PDF
    lineas = lineas_pdf(response)
    assert exportar.formato_cop(Decimal(informe["totales"]["registrado"])) in " ".join(lineas)


def test_store_failure_is_a_warning_with_the_s3_code_and_no_data(
    client, exp_app, monkeypatch, caplog
):
    """Un WARNING con el tipo del error y, en S3, su código (un enum, sin datos); nunca la
    clave, el tenant, el endpoint, el bucket ni datos de la empresa o del informe."""
    sesion, _, logo_id, _ = cerrada_con_logo(client)
    error = ClientError({"Error": {"Code": "AccessDenied", "Message": "denegado"}}, "GetObject")
    monkeypatch.setitem(exp_app.extensions, EXTENSION_KEY, AlmacenQueFalla(error))
    with caplog.at_level(logging.DEBUG, logger="app.conteo.routes"):
        assert excel(client, sesion).status_code == 200
    avisos = [r for r in caplog.records if r.name == "app.conteo.routes"]
    assert len(avisos) == 1
    assert avisos[0].levelno == logging.WARNING
    mensaje = avisos[0].getMessage()
    assert "ClientError" in mensaje and "AccessDenied" in mensaje
    registros = " ".join(r.getMessage() for r in caplog.records)
    for dato in [logo_id, str(TENANT_A), sesion, "denegado", "GetObject", "Conteo nov"]:
        assert dato not in registros, dato
    for dato in EMPRESA_CON_LOGO.values():
        assert dato not in registros, dato


def test_oserror_warning_has_only_the_error_type(client, exp_app, monkeypatch, caplog):
    sesion, _, _, _ = cerrada_con_logo(client)
    error = OSError(2, "No such file", "/ruta/secreta/tenant/logo.png")
    monkeypatch.setitem(exp_app.extensions, EXTENSION_KEY, AlmacenQueFalla(error))
    with caplog.at_level(logging.DEBUG, logger="app.conteo.routes"):
        assert excel(client, sesion).status_code == 200
    (aviso,) = [r for r in caplog.records if r.name == "app.conteo.routes"]
    # errno 2 hace de ``OSError`` un ``FileNotFoundError``: solo el nombre del tipo.
    assert aviso.getMessage() == "Informe sin logo: el almacén falló (FileNotFoundError)."
    assert "/ruta/secreta" not in aviso.getMessage() and "No such file" not in aviso.getMessage()


def test_informe_logo_con_clave_invalida_no_se_traga_el_error(client, exp_app, monkeypatch):
    """Decisión documentada (security-reviewer, T4): solo los fallos del almacén degradan a
    «sin logo». ``ClaveInvalida`` es un error de integridad de la clave congelada y NO se
    traga en ``_logo``: se propaga al manejador central y sale como ``500 error_interno``
    (no un Excel «sin logo»)."""
    sesion, _, _, _ = cerrada_con_logo(client)
    almacen = AlmacenQueFalla(ClaveInvalida())
    monkeypatch.setitem(exp_app.extensions, EXTENSION_KEY, almacen)
    response = excel(client, sesion)
    assert response.status_code == 500
    assert response.mimetype == "application/json"
    assert response.get_json()["error"]["code"] == "error_interno"
    assert almacen.lecturas == 1


def test_contador_and_previous_errors_do_not_touch_the_store(client, exp_app, monkeypatch):
    """El ``403`` del contador, el ``404`` y el ``409`` salen antes de leer el logo."""
    sesion, _, _, clinica = cerrada_con_logo(client)
    abierta = clinica.abrir()
    almacen = AlmacenQueFalla(AssertionError("no se debe leer el logo"))
    monkeypatch.setitem(exp_app.extensions, EXTENSION_KEY, almacen)
    prohibido = excel(client, sesion, CONTADOR)
    assert prohibido.status_code == 403
    assert prohibido.get_json()["error"]["code"] == "prohibido"
    assert pdf(client, sesion, CONTADOR).status_code == 403
    assert excel(client, str(uuid.uuid4())).status_code == 404
    assert excel(client, sesion, ADMIN_OTRO).status_code == 404
    respuesta = excel(client, abierta)
    assert respuesta.status_code == 409
    assert respuesta.get_json()["error"]["code"] == "sesion_abierta"
    assert almacen.lecturas == 0


def test_contador_gets_403_without_figures_nor_company_data(client):
    """Spec 019 (req. 4): el libro con «Por ubicación» y «Por categoría» lleva precios; el
    contador sigue con ``403`` y la respuesta no trae cifras, nombres ni datos de la empresa."""
    sesion, informe, _, _ = cerrada_con_logo(client)
    prohibido = excel(client, sesion, CONTADOR)
    assert prohibido.status_code == 403
    assert prohibido.mimetype == "application/json"
    assert prohibido.get_json()["error"]["code"] == "prohibido"
    cuerpo = prohibido.get_data(as_text=True)
    for dato in [
        *EMPRESA_CON_LOGO.values(),
        "1390000",
        "389900",
        "Conteo nov",
        *(f["etiqueta"] for f in informe["desglose"]["ubicaciones"]),
    ]:
        assert dato not in cuerpo, dato


def test_list_sheets_carry_the_frozen_block_not_the_current_company(client):
    """El bloque de las hojas de lista es el de la empresa congelada al cierre: cambiar la
    empresa después no cambia el archivo; tampoco aparece la de otro tenant."""
    sesion, _, _, _ = cerrada_con_logo(client)
    otra = {**EMPRESA_CON_LOGO, "nombre": "Empresa Ajena de Prueba Ltda.", "nit": "800197268"}
    assert client.put("/empresa", json=otra, headers=ADMIN_OTRO).status_code == 200
    nueva = {"nombre": "Nombre nuevo", "direccion": "Otra dirección"}
    assert client.put("/empresa", json=nueva, headers=ADMIN).status_code == 200
    wb = libro(excel(client, sesion))
    assert len(wb.worksheets) == len(LIBRO)
    for hoja in wb.worksheets:
        linea = f"Informe · {EMPRESA_CON_LOGO['nombre']} · corte 30/11/2026"
        assert hoja["C3"].value == linea, hoja.title
    with zipfile.ZipFile(io.BytesIO(excel(client, sesion).data)) as z:
        xml = "".join(z.read(n).decode() for n in z.namelist() if n.endswith(".xml"))
    assert "Empresa Ajena" not in xml and "800.197.268" not in xml and "Nombre nuevo" not in xml


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
    assert contiene_seguidas(lineas, ["INFORME DE INVENTARIO DE ACTIVOS", "Conteo nov 2026"])
    assert contiene_seguidas(lineas, ["Fecha de corte", "Cerrada", "Cerró", "Moneda", "Estado"])
    i = lineas.index("Estado")
    assert lineas[i + 1] == "30/11/2026"
    assert lineas[i + 3 : i + 6] == [ADMIN_A.nombre, "COP", "Informe congelado"]
    t = informe["totales"]
    cop = exportar.formato_cop
    for rotulo, clave in (
        ("Encontrado", "encontrado"),
        ("No encontrado", "no_encontrado"),
        ("Total registrado", "registrado"),
    ):
        assert contiene_seguidas(lineas, [rotulo, cop(Decimal(t[clave]))]), rotulo
    assert "50 % de las unidades encontradas." in lineas
    for dimension in ("categorias", "ubicaciones"):
        for fila in esperado_desglose(informe, dimension):
            etiqueta, e, ue, n, un, r, ur, _ = fila
            pct = exportar.porcentaje(ue, ur)  # el PDF no cambia: el % sigue como texto
            esperadas = [etiqueta, cop(e), str(ue), cop(n), str(un), cop(r), str(ur), pct]
            assert contiene_seguidas(lineas, esperadas), esperadas
    for n in informe["no_encontrados"]:
        esperadas = [n["codigo"], n["nombre"], n["categoria"]["nombre"], n["ubicacion"]["ruta"]]
        if n["en_reparacion"]:
            esperadas.append("En reparación")
        esperadas.append(cop(Decimal(n["precio"])))
        assert contiene_seguidas(lineas, esperadas), esperadas
    assert contiene_seguidas(lineas, ["2 activos no encontrados", cop(Decimal(t["no_encontrado"]))])
    assert any(li.endswith("Página 1 de 1") for li in lineas)
    assert not {"Elaboró", "Revisó", "Aprobó"} & set(lineas)  # sin firmas (G1)


def test_pdf_carries_the_frozen_company_logo_and_footer(client):
    datos = {
        "nombre": "Clínica Ejemplo S.A.S.",
        "direccion": "Calle 10 # 5-20",
        "nit": "900123456-8",
    }
    assert client.put("/empresa", json=datos, headers=ADMIN).status_code == 200
    subida = client.put(
        "/empresa/logo",
        data={"logo_id": str(uuid.uuid4()), "archivo": (io.BytesIO(_png()), "l.png")},
        headers=ADMIN,
        content_type="multipart/form-data",
    )
    assert subida.status_code == 201
    _, sesion, _, _ = cerrada(client)
    response = pdf(client, sesion)
    lineas = lineas_pdf(response)
    assert lineas[0] == "Clínica Ejemplo S.A.S."
    assert "NIT 900.123.456-8 · Calle 10 # 5-20" in lineas
    pie = "Clínica Ejemplo S.A.S. · Conteo nov 2026 · Informe congelado al cierre"
    assert any(li.startswith(pie) for li in lineas)
    pagina = PdfReader(io.BytesIO(response.data)).pages[0]
    assert len(pagina.images) == 1
    # Después del cierre la empresa cambia: el PDF sigue con lo congelado.
    client.put("/empresa", json={**datos, "nombre": "Otra S.A.S."}, headers=ADMIN)
    assert lineas_pdf(pdf(client, sesion)) == lineas


def test_pdf_of_a_session_closed_before_013_labels_the_current_company(client, exp_db):
    _, sesion, _, _ = cerrada(client)
    with exp_db.migrator.begin() as conn:
        conn.execute(text("delete from sesion_detalle"))
        conn.execute(text("delete from sesion_empresa"))
    lineas = lineas_pdf(pdf(client, sesion))
    texto = " ".join(lineas)
    assert exportar.EMPRESA_VIGENTE in texto


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
    for rotulo in ("Encontrado", "No encontrado", "Total registrado"):
        assert contiene_seguidas(lineas, [rotulo, "$ 0,00"]), rotulo
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
