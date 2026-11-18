"""Documento intermedio de la exportación (spec 009, T1; R1–R3).

El Excel y el PDF salen de un mismo documento construido desde el dict de
``cierre.informe``: aquí no se suma nada. El formato COP y el porcentaje son los
mismos de la web (``web/src/lib/format.ts`` y ``porcentaje`` de ``lib/sesiones.ts``).
"""

import copy
import html
import io
import re
import warnings
import zipfile
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook
from pypdf import PdfReader

from app.conteo import exportar


@pytest.mark.parametrize(
    ("entrada", "salida"),
    [
        ("0", "$ 0,00"),
        ("0.5", "$ 0,50"),
        ("389900.00", "$ 389.900,00"),
        ("1234567.8", "$ 1.234.567,80"),
        ("276850300.00", "$ 276.850.300,00"),
        ("999999999999.99", "$ 999.999.999.999,99"),
        ("-1500", "-$ 1.500,00"),
    ],
)
def test_cop_format_matches_the_web(entrada, salida):
    assert exportar.formato_cop(Decimal(entrada)) == salida


def test_cop_format_rejects_more_than_two_decimals():
    with pytest.raises(ValueError):
        exportar.formato_cop(Decimal("1.005"))


@pytest.mark.parametrize(
    ("encontradas", "registradas", "salida"),
    [
        (0, 0, "0 %"),
        (1, 2, "50 %"),
        (1, 3, "33,3 %"),
        (2, 3, "66,7 %"),
        (3, 3, "100 %"),
        (1, 8, "12,5 %"),
    ],
)
def test_percentage_matches_the_web(encontradas, registradas, salida):
    assert exportar.porcentaje(encontradas, registradas) == salida


@pytest.mark.parametrize(
    ("encontradas", "registradas", "fraccion"),
    [
        (0, 0, "0"),
        (1, 2, "0.5"),
        (1, 3, "0.333"),
        (2, 3, "0.667"),
        (3, 3, "1"),
        (1, 8, "0.125"),
    ],
)
def test_found_fraction_is_the_same_rounding_as_the_percentage(encontradas, registradas, fraccion):
    """El % del Excel (spec 015, T5) es un número con formato ``0.0 %``: la misma cifra
    redondeada a la décima que el texto de la web, como ``Decimal`` exacto."""
    valor = exportar.fraccion_encontrada(encontradas, registradas)
    assert isinstance(valor, Decimal)
    assert valor == Decimal(fraccion)


INFORME = {
    "sesion": {
        "id": "00000000-0000-4000-8000-0000000000e1",
        "nombre": "Conteo nov 2026",
        "tipo": "conteo",
        "estado": "cerrada",
        "fecha_corte": "2026-11-30",
        "abierta_por": {"id": "00000000-0000-4000-8000-00000000000a", "nombre": "Ana Torres"},
        "abierta_en": "2026-11-14T13:00:00+00:00",
        "cerrada_por": {"id": "00000000-0000-4000-8000-00000000000a", "nombre": "Ana Torres"},
        "cerrada_en": "2026-11-14T22:58:00+00:00",
    },
    "empresa": {
        "nombre": "Clínica Dental Ejemplo S.A.S.",
        "direccion": "Calle 10 # 5-20, Cartago",
        "nit": "890.903.938-8",
        "telefono": None,
        "correo": None,
        "logo": None,
        "vigente": False,
    },
    "detalle_disponible": True,
    "totales": {
        "encontrado": "1390000.50",
        "no_encontrado": "389900.00",
        "registrado": "1779900.50",
        "unidades_encontrado": 1,
        "unidades_no_encontrado": 1,
        "unidades_registrado": 2,
    },
    "desglose": {
        "categorias": [
            {
                "id": "00000000-0000-4000-8000-0000000000c1",
                "etiqueta": "Electrónica",
                "total_encontrado": "1390000.50",
                "total_no_encontrado": "0.00",
                "total_registrado": "1390000.50",
                "unidades_encontrado": 1,
                "unidades_no_encontrado": 0,
                "unidades_registrado": 1,
            },
            {
                "id": "00000000-0000-4000-8000-0000000000c2",
                "etiqueta": "Mobiliario",
                "total_encontrado": "0.00",
                "total_no_encontrado": "389900.00",
                "total_registrado": "389900.00",
                "unidades_encontrado": 0,
                "unidades_no_encontrado": 1,
                "unidades_registrado": 1,
            },
        ],
        "ubicaciones": [
            {
                "id": "00000000-0000-4000-8000-0000000000a2",
                "etiqueta": "Consultorio 1 › Box 2",
                "total_encontrado": "1390000.50",
                "total_no_encontrado": "389900.00",
                "total_registrado": "1779900.50",
                "unidades_encontrado": 1,
                "unidades_no_encontrado": 1,
                "unidades_registrado": 2,
            }
        ],
    },
    "no_encontrados": [
        {
            "activo_id": "00000000-0000-4000-8000-0000000000d2",
            "codigo": "000123",
            "nombre": "Silla ergonómica",
            "categoria": {"id": "00000000-0000-4000-8000-0000000000c2", "nombre": "Mobiliario"},
            "ubicacion": {
                "id": "00000000-0000-4000-8000-0000000000a2",
                "ruta": "Consultorio 1 › Box 2",
            },
            "precio": "389900.00",
            "en_reparacion": True,
        }
    ],
}


def test_document_reads_every_figure_from_the_report_without_summing():
    doc = exportar.documento(INFORME)
    assert doc.sesion == "Conteo nov 2026"
    assert doc.corte == "30/11/2026"
    assert doc.cerrada_por == "Ana Torres"
    # 22:58 UTC = 5:58 p. m. en Colombia (UTC−5, sin horario de verano).
    assert doc.cerrada_en == "14/11/2026, 5:58 p. m."
    assert doc.totales.encontrado == exportar.Cifra(Decimal("1390000.50"), 1)
    assert doc.totales.no_encontrado == exportar.Cifra(Decimal("389900.00"), 1)
    assert doc.totales.registrado == exportar.Cifra(Decimal("1779900.50"), 2)
    assert doc.totales.porcentaje == "50 %"
    assert [f.etiqueta for f in doc.por_categoria] == ["Electrónica", "Mobiliario"]
    assert doc.por_categoria[1].no_encontrado == exportar.Cifra(Decimal("389900.00"), 1)
    assert doc.por_categoria[1].porcentaje == "0 %"
    assert doc.por_ubicacion[0].etiqueta == "Consultorio 1 › Box 2"
    (silla,) = doc.no_encontrados
    assert (silla.codigo, silla.nombre, silla.categoria, silla.ubicacion) == (
        "000123",
        "Silla ergonómica",
        "Mobiliario",
        "Consultorio 1 › Box 2",
    )
    assert silla.precio == Decimal("389900.00")
    assert silla.en_reparacion is True
    assert all(
        isinstance(c.valor, Decimal) for c in (doc.totales.encontrado, doc.totales.no_encontrado)
    )


def test_document_of_an_empty_session_is_all_zeros():
    vacio = {
        **INFORME,
        "totales": {
            "encontrado": "0.00",
            "no_encontrado": "0.00",
            "registrado": "0.00",
            "unidades_encontrado": 0,
            "unidades_no_encontrado": 0,
            "unidades_registrado": 0,
        },
        "desglose": {"categorias": [], "ubicaciones": []},
        "no_encontrados": [],
    }
    doc = exportar.documento(vacio)
    assert doc.totales.registrado == exportar.Cifra(Decimal("0.00"), 0)
    assert doc.totales.porcentaje == "0 %"
    assert doc.por_categoria == doc.por_ubicacion == doc.no_encontrados == ()


@pytest.mark.parametrize(
    ("nombre", "corte", "archivo"),
    [
        ("Conteo nov 2026", "2026-11-30", "informe-conteo-nov-2026-corte-2026-11-30"),
        ("Conteo «Sede» / Año 2026", "2026-12-01", "informe-conteo-sede-ano-2026-corte-2026-12-01"),
        ("###", "2026-12-01", "informe-corte-2026-12-01"),
    ],
)
def test_file_name_is_ascii_and_safe(nombre, corte, archivo):
    assert exportar.nombre_base(nombre, corte) == archivo


def _lineas(contenido: bytes) -> list[str]:
    lector = PdfReader(io.BytesIO(contenido))
    return [li.strip() for pagina in lector.pages for li in pagina.extract_text().splitlines()]


def test_pdf_replaces_characters_the_standard_fonts_cannot_draw():
    informe = copy.deepcopy(INFORME)
    informe["no_encontrados"][0]["nombre"] = "Silla 日本 «ergonómica»"
    lineas = _lineas(exportar.a_pdf(exportar.documento(informe)))
    assert "Silla ?? «ergonómica»" in lineas


def test_long_pdf_numbers_pages_and_repeats_the_header():
    informe = copy.deepcopy(INFORME)
    fila = informe["no_encontrados"][0]
    informe["no_encontrados"] = [{**fila, "codigo": f"AC-{i:04d}"} for i in range(150)]
    lector = PdfReader(io.BytesIO(exportar.a_pdf(exportar.documento(informe))))
    paginas = len(lector.pages)
    assert paginas >= 3
    for numero, pagina in enumerate(lector.pages, start=1):
        texto = pagina.extract_text()
        assert f"AssetControl · Página {numero} de {paginas}" in texto
        if 1 < numero < paginas:
            assert "Código" in texto  # encabezado de la tabla repetido
        if numero > 1:
            # Encabezado reducido de la empresa y la sesión (spec 013, R6).
            assert "Informe de inventario · Conteo nov 2026 · corte 30/11/2026" in texto


@pytest.mark.parametrize(
    ("categorias", "hojas"),
    [
        (["Biomédicos", "CPU"], ["Biomédicos", "CPU"]),
        (["Equipos / Rayos X: [sala]*?"], ["Equipos Rayos X sala"]),
        (["x" * 40], ["x" * 31]),
        (["Resumen", "No encontrados"], ["Resumen (2)", "No encontrados (2)"]),
        (["Todos los activos"], ["Todos los activos (2)"]),
        (["Sillas", "SILLAS", "sillas"], ["Sillas", "SILLAS (2)", "sillas (3)"]),
        (["y" * 35, "y" * 33], ["y" * 31, "y" * 27 + " (2)"]),
        (["'Citada'", "///"], ["Citada", "Categoría"]),
        # Excel mide en unidades UTF-16: cada emoji ocupa dos (spec 015, T5, M2).
        (["Equipos " + "😀" * 16], ["Equipos " + "😀" * 11]),
        (["😀" * 20 + "x", "😀" * 20 + "y"], ["😀" * 15, "😀" * 13 + " (2)"]),
        (["a" * 30 + "😀"], ["a" * 30]),  # no parte el par sustituto
        (["a" * 29 + "😀"], ["a" * 29 + "😀"]),  # 31 unidades: cabe
        (["History", "history"], ["History (2)", "history (3)"]),
        (["a" * 30 + "'b"], ["a" * 30]),  # tras el corte tampoco termina en comilla
    ],
)
def test_sheet_names_are_valid_and_unique(categorias, hojas):
    nombres = exportar.nombres_de_hoja(categorias)
    assert nombres == hojas
    for nombre in nombres:
        assert len(nombre.encode("utf-16-le")) // 2 <= 31
        assert not set(nombre) & set("[]:*?/\\")
        assert not nombre.startswith("'") and not nombre.endswith("'")


def test_sheet_names_with_emoji_are_accepted_by_the_writer():
    """Las 16+ emoji de una categoría no tumban el libro (antes: ``InvalidWorksheetName``)."""
    informe = copy.deepcopy(INFORME)
    informe["desglose"]["categorias"][0]["etiqueta"] = "Equipos " + "😀" * 16
    detalle = [_detalle(categoria_id=informe["desglose"]["categorias"][0]["id"])]
    detalle[0].categoria_nombre = informe["desglose"]["categorias"][0]["etiqueta"]
    wb = load_workbook(io.BytesIO(exportar.a_excel(exportar.documento(informe, detalle))))
    assert "Equipos " + "😀" * 11 in wb.sheetnames


def test_print_header_text_is_cut_before_escaping_and_never_splits_a_double_ampersand():
    # 79 letras y un «&»: duplicado ocuparía 81; se corta antes del «&&», no en medio.
    assert exportar._cabecera_impresion("a" * 79 + "&b") == "a" * 79
    assert exportar._cabecera_impresion("a" * 78 + "&b") == "a" * 78 + "&&"
    assert exportar._cabecera_impresion("A&B") == "A&&B"
    # Imágenes (``&G``, ``&[Picture]``) y fuentes (``&"``) no llegan como código.
    assert exportar._cabecera_impresion('M&G &[Picture] &"Arial" &&G') == 'MG [Picture] "Arial" G'
    # El tope se mide en UTF-16 y no parte un emoji.
    assert exportar._cabecera_impresion("😀" * 50) == "😀" * 40
    assert exportar._cabecera_impresion("a" + "😀" * 50) == "a" + "😀" * 39


HOSTIL = '=HYPERLINK("http://evil","x")'
EMPRESA_HOSTIL = '&A&P&"Arial,Bold"&K FF0000&Z'
SESION_HOSTIL = "2026 &D inventario"


def _detalle(**cambios):
    fila = {
        "codigo": "000124",
        "nombre": "Autoclave",
        "marca": None,
        "serial": None,
        "categoria_id": INFORME["desglose"]["categorias"][0]["id"],
        "categoria_nombre": "Electrónica",
        "ubicacion_ruta": "Consultorio 1 › Box 2",
        "encontrada_ruta": "Consultorio 1 › Box 2",
        "estado_fisico": "ok",
        "encontrado": True,
        "en_reparacion": False,
        "precio": "1390000.50",
    }
    return SimpleNamespace(**{**fila, **cambios})


def comprobar_libro_seguro(contenido: bytes, empresa: str, sesion: str) -> None:
    """Todo texto es texto (``s``), sin fórmulas ni hipervínculos en el zip, y el
    encabezado de impresión con cada ``&`` del usuario neutralizado y el tamaño aparte."""
    wb = load_workbook(io.BytesIO(contenido))
    for hoja in wb.worksheets:
        for fila in hoja.iter_rows():
            for celda in fila:
                if isinstance(celda.value, str):
                    assert celda.data_type == "s", (hoja.title, celda.coordinate)
        assert not hoja._hyperlinks, hoja.title
    resumen = wb["Resumen"]
    for ref in ("B1", "B2", "B3"):
        assert resumen[ref].data_type == "s", ref
    assert resumen["B1"].value == empresa
    assert f"«{sesion}»" in resumen["B3"].value
    esperado = (
        f"&L&8 {exportar._cabecera_impresion(empresa)}&R&8 {exportar._cabecera_impresion(sesion)}"
    )
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        xml = "".join(z.read(n).decode() for n in z.namelist() if n.endswith((".xml", ".rels")))
        assert "<f>" not in xml and "<f " not in xml
        assert "<xm:f>" not in xml
        assert "<hyperlink" not in xml and "relationships/hyperlink" not in xml
        hojas = [n for n in z.namelist() if n.startswith("xl/worksheets/sheet")]
        for nombre in hojas:
            cabeceras = re.findall(r"<oddHeader>(.*?)</oddHeader>", z.read(nombre).decode())
            assert [html.unescape(c) for c in cabeceras] == [esperado], nombre
    assert not re.search(r"&8\d", esperado)


def test_hostile_text_stays_text_in_every_sheet_and_in_the_print_header():
    informe = copy.deepcopy(INFORME)
    informe["empresa"]["nombre"] = EMPRESA_HOSTIL
    informe["sesion"]["nombre"] = SESION_HOSTIL
    categoria = informe["desglose"]["categorias"][0]
    categoria["etiqueta"] = HOSTIL
    informe["desglose"]["ubicaciones"][0]["etiqueta"] = HOSTIL
    informe["no_encontrados"][0].update(
        codigo=HOSTIL,
        nombre=HOSTIL,
        categoria={"id": categoria["id"], "nombre": HOSTIL},
        ubicacion={"id": "x", "ruta": HOSTIL},
    )
    detalle = [
        _detalle(
            codigo=HOSTIL,
            nombre=HOSTIL,
            marca=HOSTIL,
            serial=HOSTIL,
            categoria_nombre=HOSTIL,
            ubicacion_ruta=HOSTIL,
            encontrada_ruta="Otra",
        )
    ]
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # XlsxWriter avisa (con el texto) si descarta algo
        contenido = exportar.a_excel(exportar.documento(informe, detalle))
    comprobar_libro_seguro(contenido, EMPRESA_HOSTIL, SESION_HOSTIL)
    wb = load_workbook(io.BytesIO(contenido))
    assert wb.sheetnames == [
        "Resumen",
        "Todos los activos",
        '=HYPERLINK("http evil","x")',
        "No encontrados",
    ]
    for nombre in ("Todos los activos", '=HYPERLINK("http evil","x")', "No encontrados"):
        valores = [c.value for fila in wb[nombre].iter_rows() for c in fila]
        assert valores.count(HOSTIL) >= 4, nombre


def test_document_keeps_the_real_cut_and_close_dates_for_the_spreadsheet():
    """Fechas reales (no texto) para las celdas de fecha del Resumen; cierre en hora de Colombia."""
    doc = exportar.documento(INFORME)
    assert doc.fecha_corte == date(2026, 11, 30)
    assert doc.momento_cierre == datetime(2026, 11, 14, 17, 58)
    assert doc.momento_cierre.tzinfo is None  # Excel no guarda zona horaria


def test_company_contact_line_has_only_what_exists():
    empresa = exportar.documento(INFORME).empresa
    assert empresa.contacto == "NIT 890.903.938-8 · Calle 10 # 5-20, Cartago"
    assert exportar.Empresa(nombre="X").contacto == ""
