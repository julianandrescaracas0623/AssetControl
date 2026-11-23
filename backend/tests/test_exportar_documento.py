"""Documento intermedio de la exportación (spec 009, T1; R1–R3).

El Excel y el PDF salen de un mismo documento construido desde el dict de
``cierre.informe``: aquí no se suma nada. El formato COP y el porcentaje son los
mismos de la web (``web/src/lib/format.ts`` y ``porcentaje`` de ``lib/sesiones.ts``).
"""

import copy
import dataclasses
import html
import io
import re
import warnings
import zipfile
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
import utils_xlsx_diseno as u_diseno
from openpyxl import load_workbook
from PIL import Image
from pypdf import PdfReader

from app.conteo import exportar
from app.conteo import exportar_estilo as est


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
        "nit": "900.123.456-8",
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
        # Spec 019 (T5): sin caracteres de control (\x00–\x1f) en el nombre de hoja.
        (["Rayos\x00X\x07"], ["Rayos X"]),
        (["\x01\x1b\x1f"], ["Categoría"]),
        (["a\x0bb\x0cc\x1ed"], ["a b c d"]),
    ],
)
def test_sheet_names_are_valid_and_unique(categorias, hojas):
    nombres = exportar.nombres_de_hoja(categorias)
    assert nombres == hojas
    for nombre in nombres:
        assert len(nombre.encode("utf-16-le")) // 2 <= 31
        assert not set(nombre) & set("[]:*?/\\")
        assert not nombre.startswith("'") and not nombre.endswith("'")
        assert not any(ord(c) < 0x20 for c in nombre)


def test_sheet_names_with_control_characters_are_accepted_by_the_writer():
    """Una categoría con caracteres de control no llega al nombre de hoja (spec 019, T5)."""
    informe = copy.deepcopy(INFORME)
    informe["desglose"]["categorias"][0]["etiqueta"] = "Equipos\x00\x08Rayos"
    detalle = [_detalle(categoria_nombre="Equipos\x00\x08Rayos")]
    wb = load_workbook(io.BytesIO(exportar.a_excel(exportar.documento(informe, detalle))))
    assert "Equipos Rayos" in wb.sheetnames
    assert not any(ord(c) < 0x20 for nombre in wb.sheetnames for c in nombre)


def test_sheet_names_with_emoji_are_accepted_by_the_writer():
    """Las 16+ emoji de una categoría no tumban el libro (antes: ``InvalidWorksheetName``)."""
    informe = copy.deepcopy(INFORME)
    informe["desglose"]["categorias"][0]["etiqueta"] = "Equipos " + "😀" * 16
    detalle = [_detalle(categoria_id=informe["desglose"]["categorias"][0]["id"])]
    detalle[0].categoria_nombre = informe["desglose"]["categorias"][0]["etiqueta"]
    wb = load_workbook(io.BytesIO(exportar.a_excel(exportar.documento(informe, detalle))))
    assert "Equipos " + "😀" * 11 in wb.sheetnames


FORMULAS_PERMITIDAS = {
    html.escape('AND($F10<>"",$G10<>"",$F10<>$G10)', quote=False),
    html.escape('AND($E10<>"",$F10<>"",$E10<>$F10)', quote=False),
}
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
    """Todo texto es texto (``s``), sin fórmulas ni hipervínculos en el zip, y ninguna hoja
    con encabezado de impresión (spec 019, B5/Q7: el texto del usuario no llega a un código
    ``&`` de Excel)."""
    wb = load_workbook(io.BytesIO(contenido))
    for hoja in wb.worksheets:
        for fila in hoja.iter_rows():
            for celda in fila:
                if isinstance(celda.value, str):
                    assert celda.data_type == "s", (hoja.title, celda.coordinate)
        assert not hoja._hyperlinks, hoja.title
    # Spec 019 (T5): todas las hojas, Resumen incluido, llevan el bloque de la plantilla
    # (empresa en C3); el nombre de la sesión va como texto en las filas de contexto del
    # Resumen (Q7), que es la última hoja (Q6).
    for hoja in wb.worksheets:
        assert hoja["C3"].value == empresa and hoja["C3"].data_type == "s", hoja.title
    resumen = wb.worksheets[-1]
    assert resumen.title == "Resumen"
    sesion_ref = f"B{FILA_CONTEXTO + 1}"
    assert resumen[sesion_ref].value == sesion and resumen[sesion_ref].data_type == "s"
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        xml = "".join(z.read(n).decode() for n in z.namelist() if n.endswith((".xml", ".rels")))
        assert "<f>" not in xml and "<f " not in xml
        assert "<xm:f>" not in xml
        assert "<hyperlink" not in xml and "relationships/hyperlink" not in xml
        # Las únicas fórmulas son las fijas del formato condicional (B11), sin datos.
        assert set(re.findall(r"<formula>(.*?)</formula>", xml)) <= FORMULAS_PERMITIDAS
        hojas = sorted(
            (n for n in z.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)),
            key=lambda n: int(re.sub(r"\D", "", n)),
        )
        assert len(hojas) == len(wb.worksheets)
        for nombre in hojas:
            # Q6: el Resumen ya no es la primera hoja; ninguna hoja tiene encabezado (B5).
            assert re.findall(r"<oddHeader>(.*?)</oddHeader>", z.read(nombre).decode()) == []


def test_hostile_text_stays_text_in_every_sheet():
    informe = copy.deepcopy(INFORME)
    informe["empresa"]["nombre"] = EMPRESA_HOSTIL
    informe["empresa"]["nit"] = HOSTIL
    informe["empresa"]["telefono"] = EMPRESA_HOSTIL
    informe["empresa"]["correo"] = HOSTIL
    informe["empresa"]["direccion"] = EMPRESA_HOSTIL
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
        "Todos los activos",
        "Por ubicación",
        "No encontrados",
        '=HYPERLINK("http evil","x")',
        "Por categoría",
        "Resumen",
    ]
    for nombre in ("Todos los activos", '=HYPERLINK("http evil","x")', "No encontrados"):
        valores = [c.value for fila in wb[nombre].iter_rows() for c in fila]
        assert valores.count(HOSTIL) >= 4, nombre
    for nombre in ("Por ubicación", "Por categoría"):
        assert wb[nombre]["A8"].value == HOSTIL and wb[nombre]["A8"].data_type == "s", nombre
    # NIT, teléfono, correo y dirección de la empresa (bloque de cada hoja) salen como texto
    # literal; ``comprobar_libro_seguro`` ya exige que no haya ``<f>`` ni hipervínculos.
    contacto = {f"NIT {HOSTIL}", f"Tel. {EMPRESA_HOSTIL}", HOSTIL, EMPRESA_HOSTIL}
    for hoja in wb.worksheets:
        textos = {
            c.value
            for fila in hoja.iter_rows(min_row=1, max_row=5)
            for c in fila
            if isinstance(c.value, str) and c.data_type == "s"
        }
        assert contacto <= textos, hoja.title
    # El título del libro (fila 26) lleva el nombre hostil escapado, nunca como código.
    core = u_diseno.extraer(contenido)["libro"]["propiedades"]["core"]
    assert core["title"] == f"Informe · {SESION_HOSTIL}"


def test_document_keeps_the_real_cut_and_close_dates_for_the_spreadsheet():
    """Fechas reales (no texto) para las celdas de fecha del Resumen; cierre en hora de Colombia."""
    doc = exportar.documento(INFORME)
    assert doc.fecha_corte == date(2026, 11, 30)
    assert doc.momento_cierre == datetime(2026, 11, 14, 17, 58)
    assert doc.momento_cierre.tzinfo is None  # Excel no guarda zona horaria


def test_company_contact_line_has_only_what_exists():
    empresa = exportar.documento(INFORME).empresa
    assert empresa.contacto == "NIT 900.123.456-8 · Calle 10 # 5-20, Cartago"
    assert exportar.Empresa(nombre="X").contacto == ""


# --- Spec 019, T4: hojas de lista del informe según la plantilla B ------------------------
#
# «Todos los activos», cada hoja por categoría y «No encontrados» se comparan, propiedad por
# propiedad, contra la huella ``tests/plantillas/informe.json`` (FT-1 a FT-3). Empresa y
# activos FICTICIOS (R8). «Por ubicación», «Por categoría», el Resumen y el libro completo
# (orden, hoja activa, propiedades y cobertura XML) son de T5 (más abajo).
#
# Celda vacía (pendiente del reviewer de T2, decidido aquí): la plantilla B SÍ determina un
# estilo propio para la celda de datos sin valor: la única que trae (Todos E10, categoría
# D10; serial vacío) es Calibri 11 con bordes, centro/abajo (``datos_vacia``), distinta de
# la de texto (A10: Arial 10). Las listas del informe no tienen columnas de fecha y el precio
# nunca es nulo (``precio_al_contar`` congelado): no hay fecha ni COP vacíos que decidir.
#
# «No encontrados» (decisión del humano 2026-11-22): la plantilla no trae fila de datos con
# estilo; sus filas llevan los estilos de datos de las otras listas (los de «Todos los
# activos»), sin filas alternas. La regla de fila completa de la spec compara «Ubicación
# esperada» con «Encontrado en», columna que esta hoja no tiene: sin formato condicional.

HUELLA_INFORME = u_diseno.cargar_huella("informe")
HOJA_HUELLA = {
    "Todos los activos": "Todos los activos",
    "Por ubicación": "Por ubicación",
    "No encontrados": "No encontrados",
    "Electrónica": u_diseno.MARCA_CATEGORIA,
    "Mobiliario": u_diseno.MARCA_CATEGORIA,
    "Por categoría": "Por categoría",
    "Resumen": "Resumen",
}
FILA_CONTEXTO = exportar.FILA_CONTEXTO_RESUMEN  # índice de xlsxwriter (0 = fila 1)
EMPRESA_DISENO = {
    "nombre": "Clínica Ficticia de Prueba S.A.S.",
    "direccion": "Calle Falsa 00 # 00-00, Ciudad Ficticia",
    "nit": "900.000.000-0",
    "telefono": "600 000 0000",
    "correo": "contacto@ejemplo.test",
    "logo": None,
    "vigente": False,
}
FORMULAS = {
    "Todos los activos": 'AND($F10<>"",$G10<>"",$F10<>$G10)',
    "categoria": 'AND($E10<>"",$F10<>"",$E10<>$F10)',
}


def _png_logo(ancho: int = 600, alto: int = 240) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (ancho, alto), (29, 78, 216)).save(buffer, "PNG")
    return buffer.getvalue()


def _detalle_diseno() -> list:
    """Encontrado en su sitio (sin serial: como la fila 10 de la plantilla), encontrado en
    otra ubicación (sin marca ni estado) y uno no encontrado en reparación."""
    mob = INFORME["desglose"]["categorias"][1]["id"]
    return [
        _detalle(codigo="000124", nombre="Autoclave", marca="Marca X"),
        _detalle(
            codigo="000126",
            nombre="Lámpara",
            serial="SN-1",
            ubicacion_ruta="Bodega",
            encontrada_ruta="Consultorio 1 › Box 2",
            estado_fisico=None,
            precio="2000000.00",
        ),
        _detalle(
            codigo="000123",
            nombre="Silla ergonómica",
            marca="Marca Y",
            categoria_id=mob,
            categoria_nombre="Mobiliario",
            encontrada_ruta=None,
            estado_fisico=None,
            encontrado=False,
            en_reparacion=True,
            precio="389900.00",
        ),
    ]


def _informe_diseno() -> dict:
    informe = copy.deepcopy(INFORME)
    informe["empresa"] = dict(EMPRESA_DISENO)
    return informe


SIN_LOGO = object()


def _generar_informe(informe=None, detalle=None, logo=SIN_LOGO) -> dict:
    informe = informe or _informe_diseno()
    detalle = _detalle_diseno() if detalle is None else detalle
    logo = _png_logo() if logo is SIN_LOGO else logo
    contenido = exportar.a_excel(exportar.documento(informe, detalle, logo))
    return {"contenido": contenido, **u_diseno.extraer(contenido)}


def _esperada_informe(nombre: str) -> dict:
    return copy.deepcopy(HUELLA_INFORME["hojas"][HOJA_HUELLA[nombre]])


def _num_fila(ref: str) -> int:
    return u_diseno.ref_a_rc(ref)[0]


def _textos_del_bloque() -> dict:
    e = EMPRESA_DISENO
    return {
        "{empresa.nombre}": e["nombre"],
        "Corte {fecha}": "Corte 30/11/2026",  # fecha de corte de la sesión (B17)
        "NIT {empresa.nit}": f"NIT {e['nit']}",
        "Tel. {empresa.telefono}": f"Tel. {e['telefono']}",
        "{empresa.correo}": e["correo"],
        "{empresa.direccion}": e["direccion"],
    }


def _estilos_de_datos(nombre: str) -> tuple[dict, dict, dict]:
    """(texto, COP, vacía) de la fila 10 de la plantilla. «No encontrados» no la trae: usa
    los de «Todos los activos» (decisión del humano 2026-11-22)."""
    hoja = "Todos los activos" if nombre == "No encontrados" else nombre
    celdas = _esperada_informe(hoja)["celdas"]
    if HOJA_HUELLA[hoja] == u_diseno.MARCA_CATEGORIA:
        return celdas["A10"]["estilo"], celdas["I10"]["estilo"], celdas["D10"]["estilo"]
    return celdas["A10"]["estilo"], celdas["J10"]["estilo"], celdas["E10"]["estilo"]


def comprobar_formato_hoja(hoja: dict, esp: dict) -> None:
    """``sheetFormatPr``: alto por defecto, filas ocultas y alto propio, iguales. El ancho por
    defecto y el ancho base son el equivalente no idéntico ``ancho_base`` (Q13): la plantilla
    declara ``defaultColWidth=9.140625`` y ``baseColWidth=10``; xlsxwriter no los escribe y el
    ancho por defecto efectivo es el mismo (8.43 caracteres = 64 px)."""
    for k in ("alto_fila_defecto", "filas_ocultas_defecto", "alto_propio_defecto"):
        assert hoja["formato_hoja"][k] == esp["formato_hoja"][k], k
    assert "ancho_base" in u_diseno.EQUIVALENTES_NO_IDENTICOS
    assert (esp["formato_hoja"]["ancho_col_defecto"], esp["formato_hoja"]["ancho_base"]) == (
        9.140625,
        10,
    )
    assert (hoja["formato_hoja"]["ancho_col_defecto"], hoja["formato_hoja"]["ancho_base"]) == (
        None,
        None,
    )


def comprobar_columnas(hoja: dict, esp: dict) -> None:
    """Anchos, ocultas y rangos de la plantilla; el estilo de columna de la plantilla resuelve
    al estilo por defecto (L7) y el generado no lo declara."""

    def sin_estilo(cols):
        return [{k: v for k, v in c.items() if k != "estilo"} for c in cols]

    assert u_diseno.comparar(sin_estilo(esp["columnas"]), sin_estilo(hoja["columnas"])) == []
    defecto = HUELLA_INFORME["libro"]["estilo_defecto"]
    assert all(c["estilo"] in (None, defecto) for c in esp["columnas"])
    assert all(c["estilo"] is None for c in hoja["columnas"])


def comprobar_imagen_de_hoja(hoja: dict, esp: dict) -> None:
    """Logo de la hoja (Q10, Q13, L8): ancla equivalente, desplazamiento exacto y tamaño
    dentro de la caja de la plantilla."""
    (img_esp,) = esp["imagenes"]
    (img,) = hoja["imagenes"]
    assert (img["ancla"], img["edit_as"]) == ("twoCellAnchor", "oneCell")
    assert u_diseno.comparar(img_esp["desde"], img["desde"], "desde") == []
    assert (img["xfrm"]["x"], img["xfrm"]["y"]) == (img_esp["xfrm"]["x"], img_esp["xfrm"]["y"])
    caja, cx, cy = img_esp["ext"], img["xfrm"]["cx"], img["xfrm"]["cy"]
    assert (cx == caja["cx"] and cy <= caja["cy"]) or (cy == caja["cy"] and cx <= caja["cx"])
    for k in ("descr", "titulo", "oculta", "decorativa", "estirar", "geometria"):
        assert img[k] == img_esp[k], k


def comprobar_lista(gen: dict, nombre: str, cuerpo: dict[str, str | None], filas: list) -> None:
    """Una hoja de lista contra la huella: hoja, filas 1–9 (bloque, título, nota, Total y
    cabecera) con sus textos ``cuerpo`` (ref → texto) y cada fila de datos."""
    hoja, esp = gen["hojas"][nombre], _esperada_informe(nombre)
    for k in ("pestana", "esquema", "combinadas", "validaciones", "hipervinculos", "proteccion"):
        assert u_diseno.comparar(esp[k], hoja[k], f"{nombre}.{k}") == [], k
    comprobar_formato_hoja(hoja, esp)
    comprobar_columnas(hoja, esp)
    # Q12: listas a 1 página de ancho × alto automático (la plantilla: 1 × 1).
    pagina = {**esp["pagina"], "ajuste_alto": 0}
    assert u_diseno.comparar(pagina, hoja["pagina"], f"{nombre}.pagina") == []
    assert hoja["pagina"]["encabezado_pie"] == {"oddFooter": est.PIE}  # sin encabezado (B5)
    assert hoja["pagina"]["papel"] is None  # L3
    # Vista: congelado bajo la cabecera, sin cuadrícula; Q11: sin la selección de edición
    # (la hoja activa del libro es de T5).
    vista_esp = {k: v for k, v in esp["vista"].items() if k not in ("seleccion",)}
    vista_esp["tab_seleccionada"] = hoja["vista"]["tab_seleccionada"]
    vista_gen = {k: v for k, v in hoja["vista"].items() if k != "seleccion"}
    assert u_diseno.comparar(vista_esp, vista_gen, f"{nombre}.vista") == []
    assert hoja["vista"]["seleccion"] == [
        {"panel": "bottomLeft", "celda_activa": None, "rango": None}
    ]

    ultima = 9 + len(filas)  # última fila escrita (1-based): cabecera 9, datos desde 10
    area = esp["impresion"]["area"].split("!")[1]
    assert hoja["impresion"]["area"].split("!")[1] == re.sub(r"\d+$", str(ultima), area)
    titulos = esp["impresion"]["titulos"].split("!")[1]
    assert hoja["impresion"]["titulos"].split("!")[1] == titulos

    # Alturas: filas 1–9 de la plantilla; cada fila de datos, la de la fila 10.
    filas_esp = {n: f for n, f in esp["filas"].items() if int(n) <= 9}
    filas_esp.update({str(n): esp["filas"]["10"] for n in range(10, ultima + 1)})
    assert u_diseno.comparar(filas_esp, hoja["filas"], f"{nombre}.filas") == []

    # Filas 1–9: las mismas celdas y estilos que la plantilla, con los textos esperados.
    textos = {**_textos_del_bloque(), **cuerpo}
    esp_celdas = {r: c for r, c in esp["celdas"].items() if _num_fila(r) <= 9}
    gen_celdas = {r: c for r, c in hoja["celdas"].items() if _num_fila(r) <= 9}
    assert sorted(gen_celdas) == sorted(esp_celdas), nombre
    for ref, celda in esp_celdas.items():
        g = gen_celdas[ref]
        assert u_diseno.comparar(celda["estilo"], g["estilo"], f"{nombre}!{ref}") == []
        if celda["tipo"] == "n":
            assert g["tipo"] == "n", ref
            continue
        valor = textos.get(ref, textos.get(celda["valor"], celda["valor"]))
        if valor is None:
            assert g["tipo"] == "vacia", (ref, g["valor"])
        else:
            assert (g["tipo"], g["valor"]) == ("s", valor), ref

    # Datos: sin filas alternas; texto, COP o vacía con el estilo de la fila 10.
    texto, cop, vacia = _estilos_de_datos(nombre)
    datos = {r: c for r, c in hoja["celdas"].items() if _num_fila(r) >= 10}
    columnas = len(filas[0]) if filas else 0
    assert sorted(datos) == sorted(
        f"{u_diseno.col_letra(c + 1)}{n}" for n in range(10, ultima + 1) for c in range(columnas)
    )
    for n, valores in enumerate(filas, start=10):
        for c, valor in enumerate(valores):
            ref = f"{u_diseno.col_letra(c + 1)}{n}"
            g = datos[ref]
            if valor is None:
                assert (g["tipo"], g["valor"]) == ("vacia", None), ref
                assert u_diseno.comparar(vacia, g["estilo"], ref) == []
            elif isinstance(valor, Decimal):
                assert g["tipo"] == "n" and Decimal(str(g["valor"])) == valor, ref
                assert u_diseno.comparar(cop, g["estilo"], ref) == []
            else:
                assert (g["tipo"], g["valor"]) == ("s", valor), ref
                assert u_diseno.comparar(texto, g["estilo"], ref) == []

    # Logo de la hoja (Q10, Q13, L8).
    comprobar_imagen_de_hoja(hoja, esp)


def _filas_todos(detalle) -> list[list]:
    return [
        [
            d.codigo,
            d.nombre,
            d.categoria_nombre,
            d.marca,
            d.serial,
            d.ubicacion_ruta,
            d.encontrada_ruta,
            {"ok": "Ok", "danado": "Dañado"}.get(d.estado_fisico)
            or ("En reparación" if d.en_reparacion else None),
            "Encontrado" if d.encontrado else "No encontrado",
            Decimal(d.precio),
        ]
        for d in detalle
    ]


def test_todos_los_activos_replica_la_huella():
    gen = _generar_informe()
    filas = _filas_todos(_detalle_diseno())
    nota = (
        "2 activos · encontrados 1 (50 %) por $ 1.390.000,50 · no encontrados 1 por "
        "$ 389.900,00 · tabla «Activos», lista para filtrar o hacer una tabla dinámica. "
        f"{exportar.LEYENDA}"
    )
    comprobar_lista(
        gen,
        "Todos los activos",
        {"A7": nota, "B8": "Todos los activos", "I8": "2 activos"},
        filas,
    )
    hoja = gen["hojas"]["Todos los activos"]
    assert Decimal(str(hoja["celdas"]["J8"]["valor"])) == Decimal(INFORME["totales"]["registrado"])
    # Q8: se conserva la tabla «Activos» (con su filtro), sin nombre de estilo: no altera
    # fuente, relleno ni bordes de la plantilla.
    (tabla,) = hoja["tablas"]
    assert tabla["nombre"] == exportar.TABLA_ACTIVOS
    assert tabla["rango"] == f"A9:J{9 + len(filas)}"
    assert tabla["autofiltro"] is True
    assert "name" not in tabla["estilo"]
    assert hoja["autofiltro"] is None
    # Formato condicional de fila completa (B11) con el dxf medido; rango de la plantilla.
    (regla_esp,) = _esperada_informe("Todos los activos")["formato_condicional"]
    assert u_diseno.comparar([regla_esp], hoja["formato_condicional"]) == []
    assert regla_esp["formulas"] == [FORMULAS["Todos los activos"]]


@pytest.mark.parametrize("nombre", ["Electrónica", "Mobiliario"])
def test_hoja_por_categoria_replica_la_huella(nombre):
    gen = _generar_informe()
    detalle = [d for d in _detalle_diseno() if d.categoria_nombre == nombre]
    filas = [f[:2] + f[3:] for f in _filas_todos(detalle)]
    cifras = next(c for c in INFORME["desglose"]["categorias"] if c["etiqueta"] == nombre)
    pct = exportar.porcentaje(cifras["unidades_encontrado"], cifras["unidades_registrado"])
    nota = (
        f"{exportar._activos(cifras['unidades_registrado'])} · encontrados "
        f"{cifras['unidades_encontrado']} ({pct}) por "
        f"{exportar.formato_cop(Decimal(cifras['total_encontrado']))} · no encontrados "
        f"{cifras['unidades_no_encontrado']} por "
        f"{exportar.formato_cop(Decimal(cifras['total_no_encontrado']))} · {exportar.LEYENDA}"
    )
    comprobar_lista(
        gen,
        nombre,
        {
            "A6": f"Categoría: {nombre}",
            "A7": nota,
            "B8": nombre,
            "H8": exportar._activos(cifras["unidades_registrado"]),
        },
        filas,
    )
    hoja = gen["hojas"][nombre]
    assert Decimal(str(hoja["celdas"]["I8"]["valor"])) == Decimal(cifras["total_registrado"])
    assert hoja["autofiltro"] == f"A9:I{9 + len(filas)}"  # Q8: filtros conservados
    assert hoja["tablas"] == []
    (regla_esp,) = _esperada_informe(nombre)["formato_condicional"]
    assert u_diseno.comparar([regla_esp], hoja["formato_condicional"]) == []
    assert regla_esp["formulas"] == [FORMULAS["categoria"]]


def test_no_encontrados_replica_la_huella_con_los_estilos_de_datos_de_las_listas():
    gen = _generar_informe()
    (n,) = INFORME["no_encontrados"]
    filas = [
        [
            n["codigo"],
            n["nombre"],
            n["categoria"]["nombre"],
            n["ubicacion"]["ruta"],
            "En reparación",
            Decimal(n["precio"]),
        ]
    ]
    comprobar_lista(
        gen,
        "No encontrados",
        {"A7": "1 activo no encontrado por $ 389.900,00.", "B8": "1 activo no encontrado"},
        filas,
    )
    hoja = gen["hojas"]["No encontrados"]
    total = Decimal(INFORME["totales"]["no_encontrado"])
    assert Decimal(str(hoja["celdas"]["F8"]["valor"])) == total
    assert hoja["autofiltro"] == "A9:F10"  # Q8: filtros conservados
    # Sin «Encontrado en», la regla de fila completa de la spec no aplica (y la plantilla
    # tampoco la trae): sin formato condicional (decisión del humano 2026-11-22).
    assert _esperada_informe("No encontrados")["formato_condicional"] == []
    assert hoja["formato_condicional"] == []


def test_no_encontrados_oculta_las_columnas_g_a_k_como_la_plantilla():
    hoja = _generar_informe()["hojas"]["No encontrados"]
    ocultas = [(c["min"], c["max"], c["ancho"]) for c in hoja["columnas"] if c["oculta"]]
    assert ocultas == [(7, 7, 20), (8, 9, 16), (10, 10, 18), (11, 11, 13)]  # G, H–I, J, K
    esp = [
        (c["min"], c["max"], c["ancho"])
        for c in _esperada_informe("No encontrados")["columnas"]
        if c["oculta"]
    ]
    assert ocultas == esp
    visibles = [c for c in hoja["columnas"] if not c["oculta"]]
    assert max(c["max"] for c in visibles) == 6  # A–F visibles


def test_no_encontrados_vacio_tiene_total_y_cabecera_sin_filtro():
    informe = _informe_diseno()
    informe["no_encontrados"] = []
    gen = _generar_informe(informe, detalle=[])
    comprobar_lista(
        gen,
        "No encontrados",
        {"A7": "0 activos no encontrados por $ 389.900,00.", "B8": "1 activo no encontrado"},
        [],
    )
    assert gen["hojas"]["No encontrados"]["autofiltro"] is None


def test_celdas_vacias_de_cada_columna_llevan_el_estilo_vacia_de_la_plantilla():
    """Marca, serial, «Encontrado en» y «Estado físico» nulos: celda vacía con bordes y el
    estilo de E10 de la plantilla (``datos_vacia``); igual «Nota al cierre» vacía."""
    detalle = [
        _detalle(
            marca=None, serial=None, encontrada_ruta=None, estado_fisico=None, encontrado=False
        )
    ]
    informe = _informe_diseno()
    informe["no_encontrados"][0]["en_reparacion"] = False
    gen = _generar_informe(informe, detalle)
    _, _, vacia = _estilos_de_datos("Todos los activos")
    todos = gen["hojas"]["Todos los activos"]["celdas"]
    for col in "DEGH":  # Marca, Serial, Encontrado en, Estado físico
        celda = todos[f"{col}10"]
        assert (celda["tipo"], celda["valor"]) == ("vacia", None), col
        assert u_diseno.comparar(vacia, celda["estilo"], col) == []
    categoria = gen["hojas"]["Electrónica"]["celdas"]
    for col in "CDFG":
        assert categoria[f"{col}10"]["tipo"] == "vacia", col
        assert u_diseno.comparar(vacia, categoria[f"{col}10"]["estilo"], col) == []
    nota = gen["hojas"]["No encontrados"]["celdas"]["E10"]
    assert nota["tipo"] == "vacia"
    assert u_diseno.comparar(vacia, nota["estilo"]) == []
    # La plantilla distingue la vacía (Calibri 11, abajo) del texto (Arial 10, centro).
    texto, _, _ = _estilos_de_datos("Todos los activos")
    assert u_diseno.comparar(texto, vacia) != []


def test_con_mas_filas_el_formato_condicional_y_el_area_se_extienden():
    """Req. 5: el rango literal de la plantilla (…499) crece hasta la última fila."""
    base = _detalle(encontrada_ruta="Otra")
    detalle = [SimpleNamespace(**{**vars(base), "codigo": f"AC-{i:04d}"}) for i in range(600)]
    gen = _generar_informe(detalle=detalle)
    hoja = gen["hojas"]["Todos los activos"]
    (regla,) = hoja["formato_condicional"]
    assert regla["rango"] == "A10:J609"
    assert regla["formulas"] == [FORMULAS["Todos los activos"]]
    assert hoja["impresion"]["area"].endswith("$A$1:$J$609")
    assert hoja["tablas"][0]["rango"] == "A9:J609"
    (regla,) = gen["hojas"]["Electrónica"]["formato_condicional"]
    assert regla["rango"] == "A10:I609"


def test_las_listas_no_recalculan_el_total_y_escriben_el_decimal_exacto():
    """El Total es el congelado del informe (no la suma de las filas) y el dinero sale del
    ``Decimal`` exacto, sin pasar por ``float``."""
    informe = _informe_diseno()
    informe["totales"]["registrado"] = "167226590.70"  # no es la suma del detalle
    informe["desglose"]["categorias"][0]["total_registrado"] = "12345678901.23"
    gen = _generar_informe(informe)
    assert gen["hojas"]["Todos los activos"]["celdas"]["J8"]["valor"] == 167226590.7
    with zipfile.ZipFile(io.BytesIO(gen["contenido"])) as z:
        xml = "".join(z.read(n).decode() for n in z.namelist() if n.startswith("xl/worksheets/"))
    assert "<v>167226590.70</v>" in xml
    assert "<v>12345678901.23</v>" in xml
    assert "<v>2000000.00</v>" in xml


def test_el_precio_float_se_rechaza_en_las_listas():
    doc = exportar.documento(_informe_diseno(), _detalle_diseno())
    primero, *resto = doc.detalle
    mal = dataclasses.replace(primero, precio=1390000.5)
    with pytest.raises(TypeError):
        exportar.a_excel(dataclasses.replace(doc, detalle=(mal, *resto)))


def test_sin_logo_las_listas_salen_sin_imagen():
    gen = _generar_informe(logo=None)
    for nombre in ("Todos los activos", "Electrónica", "No encontrados"):
        assert gen["hojas"][nombre]["imagenes"] == [], nombre


@pytest.mark.parametrize(
    ("categorias", "hojas"),
    [
        (["Por ubicación", "por categoría"], ["Por ubicación (2)", "por categoría (2)"]),
        (["POR UBICACIÓN"], ["POR UBICACIÓN (2)"]),
    ],
)
def test_los_dos_nombres_de_hoja_nuevos_estan_reservados(categorias, hojas):
    assert exportar.nombres_de_hoja(categorias) == hojas


# --- Spec 019, T5: «Por ubicación», «Por categoría», Resumen y el libro completo -------------
#
# Las dos hojas de desglose escriben las cifras congeladas de ``cierre.informe`` (criterio 8):
# una fila por etiqueta y la fila Total con los ``totales`` del cierre, sin sumar. El Resumen
# replica las filas 1–8 de la plantilla (bloque y cuatro tarjetas) y, desde la fila 10, las
# filas de contexto de Q7 con el estilo de la nota de lista (plan, fila 25g); la lista
# «Todos los activos» duplicada de la plantilla (filas 9–13, A10:J10, regla A13:J13) no se
# genera (Q7). Orden del libro (Q6), primera hoja activa en A1 (Q11), propiedades (fila 26) y
# cobertura XML del libro completo (fila 27).

LIBRO_HOJAS = [
    "Todos los activos",
    "Por ubicación",
    "No encontrados",
    "Electrónica",
    "Mobiliario",
    "Por categoría",
    "Resumen",
]


def _cifras(etiqueta: str, f: dict, prefijo: str) -> list:
    """Fila del desglose tal como está en ``cierre.informe`` (Decimal y unidades)."""
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


def _desglose_esperado(informe: dict, dimension: str) -> tuple[list[list], list]:
    filas = [_cifras(f["etiqueta"], f, "total_") for f in informe["desglose"][dimension]]
    return filas, _cifras("Total", informe["totales"], "")


def _valor_numerico(celda: dict) -> Decimal:
    assert celda["tipo"] == "n", celda
    return Decimal(str(celda["valor"]))


def comprobar_hoja_corta(hoja: dict, esp: dict, nombre: str, combinadas: list[str]) -> None:
    """Lo común de «Por ubicación», «Por categoría» y Resumen: pestaña, columnas, página
    1 × 1 (Q12: igual que la plantilla), pie sin encabezado, sin congelar, sin tabla ni
    filtro, vista sin la selección de edición de la plantilla (Q11)."""
    for k in ("pestana", "esquema", "validaciones", "hipervinculos", "proteccion"):
        assert u_diseno.comparar(esp[k], hoja[k], f"{nombre}.{k}") == [], k
    assert hoja["combinadas"] == combinadas
    assert hoja["formato_condicional_ext"] == esp["formato_condicional_ext"] == []
    comprobar_formato_hoja(hoja, esp)
    comprobar_columnas(hoja, esp)
    assert u_diseno.comparar(esp["pagina"], hoja["pagina"], f"{nombre}.pagina") == []
    assert (hoja["pagina"]["ajuste_ancho"], hoja["pagina"]["ajuste_alto"]) == (1, 1)  # Q12
    assert hoja["pagina"]["encabezado_pie"] == {"oddFooter": est.PIE}
    assert hoja["pagina"]["papel"] is None  # L3
    assert hoja["tablas"] == esp["tablas"] == []
    assert hoja["autofiltro"] is esp["autofiltro"] is None
    assert hoja["impresion"]["titulos"] is esp["impresion"]["titulos"] is None
    vista_esp = {k: v for k, v in esp["vista"].items() if k not in ("seleccion",)}
    vista_esp["tab_seleccionada"] = hoja["vista"]["tab_seleccionada"]  # Q11: libro
    vista_esp["celda_superior_izquierda"] = None  # Q11: sin el desplazamiento (Resumen A7)
    vista_gen = {k: v for k, v in hoja["vista"].items() if k != "seleccion"}
    assert u_diseno.comparar(vista_esp, vista_gen, f"{nombre}.vista") == []
    assert hoja["vista"]["panel"] is None
    assert hoja["vista"]["seleccion"] == []  # Q11: A1


def comprobar_desglose(gen: dict, nombre: str, filas: list[list], total: list) -> None:
    """Una hoja de desglose contra la huella: filas 1–7 (bloque, título y cabecera) iguales
    a la plantilla, cada fila de datos con el estilo de su columna en la fila 8 y la fila
    Total con el de la fila 9 (fondo ``DBEAFE``); barras de datos en F y H hasta la última
    fila; cada cifra, la de ``cierre.informe`` exacta."""
    hoja, esp = gen["hojas"][nombre], _esperada_informe(nombre)
    comprobar_hoja_corta(hoja, esp, nombre, [])
    n = len(filas)
    fila_total = 8 + n  # 1-based: cabecera 7, datos desde 8
    area = esp["impresion"]["area"].split("!")[1]
    assert hoja["impresion"]["area"].split("!")[1] == re.sub(r"\d+$", str(fila_total), area)

    filas_esp = {k: f for k, f in esp["filas"].items() if int(k) <= 7}
    filas_esp.update({str(k): esp["filas"]["8"] for k in range(8, fila_total)})
    filas_esp[str(fila_total)] = esp["filas"]["9"]
    assert u_diseno.comparar(filas_esp, hoja["filas"], f"{nombre}.filas") == []

    textos = _textos_del_bloque()
    esp_fijas = {r: c for r, c in esp["celdas"].items() if _num_fila(r) <= 7}
    gen_fijas = {r: c for r, c in hoja["celdas"].items() if _num_fila(r) <= 7}
    assert sorted(gen_fijas) == sorted(esp_fijas), nombre
    for ref, celda in esp_fijas.items():
        g = gen_fijas[ref]
        assert u_diseno.comparar(celda["estilo"], g["estilo"], f"{nombre}!{ref}") == []
        valor = textos.get(celda["valor"], celda["valor"])
        if valor is None:
            assert g["tipo"] == "vacia", (ref, g["valor"])
        else:
            assert (g["tipo"], g["valor"]) == ("s", valor), ref

    columnas = "ABCDEFGH"
    esperadas = {f"{c}{k}" for c in columnas for k in range(8, fila_total)}
    esperadas |= {f"{c}{fila_total}" for c in "ABCDEFGHIJ"}
    assert sorted(r for r in hoja["celdas"] if _num_fila(r) >= 8) == sorted(esperadas)
    for k, valores in enumerate([*filas, total], start=8):
        plantilla = "9" if k == fila_total else "8"
        for c, valor in zip(columnas, valores, strict=True):
            g = hoja["celdas"][f"{c}{k}"]
            molde = esp["celdas"][f"{c}{plantilla}"]
            assert u_diseno.comparar(molde["estilo"], g["estilo"], f"{nombre}!{c}{k}") == []
            if c == "A":
                assert (g["tipo"], g["valor"]) == ("s", valor), f"{c}{k}"
            else:
                assert _valor_numerico(g) == valor, f"{c}{k}"
        for c in "IJ" if k == fila_total else "":
            g = hoja["celdas"][f"{c}{k}"]
            assert g["tipo"] == "vacia", f"{c}{k}"
            assert u_diseno.comparar(esp["celdas"][f"{c}9"]["estilo"], g["estilo"]) == []

    # Barras de datos (L5): F y H de las filas de datos, BFDBFE, sin extensión 2010; el
    # ``val="0"`` de min/max es el equivalente aceptado ``cfvo_val_min_max``.
    reglas = hoja["formato_condicional"]
    if not filas:
        assert reglas == []
    else:
        ultima = 7 + n
        esperadas_cf = []
        for regla in esp["formato_condicional"]:
            col = regla["rango"][0]
            rango = f"{col}8" if n == 1 else f"{col}8:{col}{ultima}"
            cfvo = [{**v, "valor": "0"} for v in regla["barra"]["cfvo"]]
            barra = {**regla["barra"], "cfvo": cfvo}
            esperadas_cf.append({**regla, "rango": rango, "barra": barra})
        assert u_diseno.comparar(esperadas_cf, reglas, f"{nombre}.barras") == []
        assert [r["rango"][0] for r in reglas] == ["F", "H"]
    comprobar_imagen_de_hoja(hoja, esp)


@pytest.mark.parametrize(
    ("nombre", "dimension"), [("Por ubicación", "ubicaciones"), ("Por categoría", "categorias")]
)
def test_hoja_de_desglose_replica_la_huella_con_las_cifras_del_cierre(nombre, dimension):
    gen = _generar_informe()
    informe = _informe_diseno()
    filas, total = _desglose_esperado(informe, dimension)
    comprobar_desglose(gen, nombre, filas, total)


def test_desglose_sin_filas_tiene_titulo_cabecera_y_total_sin_barras():
    informe = _informe_diseno()
    informe["desglose"] = {"categorias": [], "ubicaciones": []}
    gen = _generar_informe(informe, detalle=[])
    for nombre in ("Por ubicación", "Por categoría"):
        comprobar_desglose(gen, nombre, [], _cifras("Total", informe["totales"], ""))


def test_desglose_con_muchas_filas_extiende_barras_y_area():
    """Req. 5: las barras de datos y el área de impresión llegan hasta la última fila."""
    informe = _informe_diseno()
    base = informe["desglose"]["ubicaciones"][0]
    informe["desglose"]["ubicaciones"] = [
        {**base, "id": f"u{i}", "etiqueta": f"Sala {i:03d}"} for i in range(40)
    ]
    gen = _generar_informe(informe)
    filas, total = _desglose_esperado(informe, "ubicaciones")
    comprobar_desglose(gen, "Por ubicación", filas, total)
    hoja = gen["hojas"]["Por ubicación"]
    assert [r["rango"] for r in hoja["formato_condicional"]] == ["F8:F47", "H8:H47"]
    assert hoja["impresion"]["area"].endswith("$A$1:$H$48")


def test_desglose_escribe_el_decimal_congelado_sin_sumar_ni_pasar_por_float():
    """Criterio 8: las cifras de «Por ubicación» y «Por categoría» son las de
    ``cierre.informe`` exactas. Centavos que ``float`` no representa (0,10; 0,07…) y un Total
    que NO es la suma de las filas: el libro escribe lo congelado, dígito a dígito."""
    informe = _informe_diseno()
    informe["totales"].update(encontrado="0.10", no_encontrado="0.20", registrado="999999999999.99")
    cat = informe["desglose"]["categorias"][0]
    cat.update(total_encontrado="1234567.07", total_no_encontrado="0.30", total_registrado="0.70")
    ubi = informe["desglose"]["ubicaciones"][0]
    ubi.update(total_encontrado="12345678901.23", total_registrado="12345678901.10")
    gen = _generar_informe(informe)
    for nombre, dimension in (("Por ubicación", "ubicaciones"), ("Por categoría", "categorias")):
        filas, total = _desglose_esperado(informe, dimension)
        comprobar_desglose(gen, nombre, filas, total)
    assert Decimal("0.1") != Decimal(0.1) and Decimal("0.07") != Decimal(0.07)
    with zipfile.ZipFile(io.BytesIO(gen["contenido"])) as z:
        nombres = re.findall(r'<sheet name="([^"]+)"', z.read("xl/workbook.xml").decode())
        xml = {
            html.unescape(n): z.read(f"xl/worksheets/sheet{i}.xml").decode()
            for i, n in enumerate(nombres, start=1)
        }
    # El texto del número es el del Decimal (con su cero final), no el de un float.
    for texto in ("0.10", "0.20", "999999999999.99"):
        assert f"<v>{texto}</v>" in xml["Por ubicación"], texto
        assert f"<v>{texto}</v>" in xml["Por categoría"], texto
    for texto in ("1234567.07", "0.30", "0.70"):
        assert f"<v>{texto}</v>" in xml["Por categoría"], texto
    for texto in ("12345678901.23", "12345678901.10"):
        assert f"<v>{texto}</v>" in xml["Por ubicación"], texto


def test_un_decimal_de_mas_de_16_cifras_se_rechaza_en_vez_de_redondearse():
    """``xlsxwriter`` escribe los números con ``{:.16G}``: 17 cifras se redondearían en
    silencio. El generador lo rechaza (``NUMERIC(14,2)`` nunca llega ahí)."""
    assert format(Decimal("12345678901234567.89"), ".16G") == "1.234567890123457E+16"
    informe = _informe_diseno()
    informe["desglose"]["ubicaciones"][0]["total_registrado"] = "12345678901234567.89"
    with pytest.raises(ValueError, match="16 cifras significativas"):
        exportar.a_excel(exportar.documento(informe, _detalle_diseno()))
    # 16 cifras sí caben exactas.
    informe["desglose"]["ubicaciones"][0]["total_registrado"] = "12345678901234.56"
    gen = _generar_informe(informe)
    celda = gen["hojas"]["Por ubicación"]["celdas"]["F8"]
    assert _valor_numerico(celda) == Decimal("12345678901234.56")


def _textos_contexto(doc_informe: dict, detalle: bool = True, vigente: bool = False) -> list:
    doc = exportar.documento(doc_informe)
    filas = [
        ["Sesión", doc.sesion],
        ["Cerró", doc.cerrada_por, "Cerrada", doc.cerrada_en],
        ["Moneda", "COP"],
        ["Estado", "Informe congelado"],
        [exportar.NOTA],
    ]
    if not detalle:
        filas.append([exportar.SIN_DETALLE])
    if vigente:
        filas.append([exportar.EMPRESA_VIGENTE])
    return filas


def comprobar_resumen(gen: dict, informe: dict, contexto: list[list]) -> None:
    """El Resumen contra la huella: filas 1–8 (bloque y tarjetas) iguales a la plantilla con
    las cifras de ``totales``; nada en la fila 9; desde la 10, las filas de contexto (Q7) con
    el estilo de la nota de lista; sin la lista duplicada ni su regla (Q7)."""
    hoja, esp = gen["hojas"]["Resumen"], _esperada_informe("Resumen")
    # Q7: A10:J10 es de la lista omitida; queda el título combinado C2:D2.
    assert esp["combinadas"] == ["A10:J10", "C2:D2"]
    comprobar_hoja_corta(hoja, esp, "Resumen", ["C2:D2"])
    ultima = FILA_CONTEXTO + len(contexto)  # 1-based
    area = esp["impresion"]["area"].split("!")[1]
    assert hoja["impresion"]["area"].split("!")[1] == re.sub(r"\d+$", str(ultima), area)
    # Q7: sin la regla de la lista duplicada (A13:J13).
    assert [r["rango"] for r in esp["formato_condicional"]] == ["A13:J13"]
    assert hoja["formato_condicional"] == []

    # Alturas: filas 1–8 de la plantilla; las de contexto, la altura por defecto (plan 11b).
    filas_esp = {k: f for k, f in esp["filas"].items() if int(k) <= 8}
    defecto = {"alto": None, "alto_propio": False, "oculta": False, "nivel": 0}
    filas_esp.update(
        {
            str(k): {**defecto, "contraida": False, "estilo": None}
            for k in range(FILA_CONTEXTO + 1, ultima + 1)
        }
    )
    assert u_diseno.comparar(filas_esp, hoja["filas"], "Resumen.filas") == []

    t = informe["totales"]
    tarjetas = {
        "A7": Decimal(t["encontrado"]),
        "C7": Decimal(t["no_encontrado"]),
        "E7": Decimal(t["registrado"]),
        "G7": exportar.fraccion_encontrada(t["unidades_encontrado"], t["unidades_registrado"]),
    }
    textos = {
        **_textos_del_bloque(),
        "A8": exportar._unidades(t["unidades_encontrado"]),
        "C8": exportar._unidades(t["unidades_no_encontrado"]),
        "E8": exportar._unidades(t["unidades_registrado"]),
    }
    esp_fijas = {r: c for r, c in esp["celdas"].items() if _num_fila(r) <= 8}
    gen_fijas = {r: c for r, c in hoja["celdas"].items() if _num_fila(r) <= 8}
    assert sorted(gen_fijas) == sorted(esp_fijas)
    for ref, celda in esp_fijas.items():
        g = gen_fijas[ref]
        assert u_diseno.comparar(celda["estilo"], g["estilo"], f"Resumen!{ref}") == []
        if ref in tarjetas:
            assert _valor_numerico(g) == tarjetas[ref], ref
            continue
        valor = textos.get(ref, textos.get(celda["valor"], celda["valor"]))
        if valor is None:
            assert g["tipo"] == "vacia", (ref, g["valor"])
        else:
            assert (g["tipo"], g["valor"]) == ("s", valor), ref

    # Filas de contexto (Q7): texto siempre como texto, con el estilo de la nota de lista.
    nota = _esperada_informe("Todos los activos")["celdas"]["A7"]["estilo"]
    resto = {r: c for r, c in hoja["celdas"].items() if _num_fila(r) > 8}
    esperadas = {
        f"{u_diseno.col_letra(c + 1)}{FILA_CONTEXTO + 1 + i}": v
        for i, fila in enumerate(contexto)
        for c, v in enumerate(fila)
    }
    assert sorted(resto) == sorted(esperadas)
    for ref, valor in esperadas.items():
        assert (resto[ref]["tipo"], resto[ref]["valor"]) == ("s", valor), ref
        assert u_diseno.comparar(nota, resto[ref]["estilo"], ref) == []
    comprobar_imagen_de_hoja(hoja, esp)


def test_resumen_replica_la_huella_con_tarjetas_y_filas_de_contexto():
    informe = _informe_diseno()
    gen = _generar_informe(informe)
    comprobar_resumen(gen, informe, _textos_contexto(informe))
    # «Cerrada» es la hora del cierre en Colombia, como en el PDF (no «hoy»).
    assert gen["hojas"]["Resumen"]["celdas"]["D11"]["valor"] == "14/11/2026, 5:58 p. m."


def test_resumen_de_sesion_antigua_avisa_sin_detalle_y_empresa_vigente():
    """Sesión cerrada antes de la 013: sin detalle ni empresa congelada. El libro sigue
    siendo válido: «Por ubicación», «No encontrados», «Por categoría» y Resumen, con los
    avisos ``SIN_DETALLE`` y ``EMPRESA_VIGENTE`` al final del Resumen."""
    informe = _informe_diseno()
    informe["detalle_disponible"] = False
    informe["empresa"]["vigente"] = True
    gen = _generar_informe(informe, detalle=[])
    assert gen["libro"]["hojas"] == ["Por ubicación", "No encontrados", "Por categoría", "Resumen"]
    comprobar_resumen(gen, informe, _textos_contexto(informe, detalle=False, vigente=True))
    for nombre, dimension in (("Por ubicación", "ubicaciones"), ("Por categoría", "categorias")):
        filas, total = _desglose_esperado(informe, dimension)
        comprobar_desglose(gen, nombre, filas, total)
    wb = load_workbook(io.BytesIO(gen["contenido"]))  # el libro abre sin errores
    assert wb.active.title == "Por ubicación"


def test_resumen_sin_avisos_cuando_no_aplican():
    gen = _generar_informe()
    textos = [c["valor"] for c in gen["hojas"]["Resumen"]["celdas"].values()]
    assert exportar.NOTA in textos
    assert exportar.SIN_DETALLE not in textos and exportar.EMPRESA_VIGENTE not in textos


def test_corte_es_la_fecha_de_corte_congelada_no_la_de_hoy():
    """«Corte dd/mm/aaaa» (E3) en todas las hojas: la fecha de corte de la sesión tal como
    está en ``cierre.informe`` (B17); ni la de hoy ni la del momento del cierre."""
    informe = _informe_diseno()
    informe["sesion"]["fecha_corte"] = "2025-01-31"
    gen = _generar_informe(informe)
    hoy = date.today().strftime("%d/%m/%Y")
    for nombre, hoja in gen["hojas"].items():
        assert hoja["celdas"]["E3"]["valor"] == "Corte 31/01/2025", nombre
        assert hoy not in hoja["celdas"]["E3"]["valor"], nombre
        assert "14/11/2026" not in hoja["celdas"]["E3"]["valor"], nombre


def test_el_libro_sigue_el_orden_de_la_plantilla_y_abre_en_la_primera_hoja():
    """Q6: orden de la plantilla; Q11: primera hoja activa, A1, sin desplazamiento."""
    gen = _generar_informe()
    libro, esp = gen["libro"], HUELLA_INFORME["libro"]
    assert libro["hojas"] == LIBRO_HOJAS
    assert [HOJA_HUELLA[n] for n in libro["hojas"] if n != "Mobiliario"] == esp["hojas"]
    assert esp["hoja_activa"] == 2  # residuo de edición de la plantilla (Q11)
    assert libro["hoja_activa"] == 0
    assert libro["primera_hoja_visible"] == esp["primera_hoja_visible"] == 0
    assert libro["pestanas_visibles"] is esp["pestanas_visibles"] is True
    assert set(libro["estados"]) == set(esp["estados"]) == {"visible"}
    for i, nombre in enumerate(libro["hojas"]):
        vista = gen["hojas"][nombre]["vista"]
        assert vista["tab_seleccionada"] is (i == 0), nombre
        assert vista["celda_superior_izquierda"] is None, nombre
        for sel in vista["seleccion"]:  # sin celda activa ni rango: Excel abre en A1
            assert (sel["celda_activa"], sel["rango"]) == (None, None), nombre
    wb = load_workbook(io.BytesIO(gen["contenido"]))
    assert wb.active.title == "Todos los activos"


def test_el_libro_replica_tema_estilos_por_defecto_nombres_y_propiedades():
    """Libro (FT-1): tema, fuente y estilo por defecto, estilos de tabla y ``dxf`` (uno,
    deduplicado: decisión del humano T4); nombres definidos con los rangos extendidos y los
    filtros de Q8; propiedades del documento (fila 26) y un solo medio (Q13)."""
    gen = _generar_informe()
    libro, esp = gen["libro"], HUELLA_INFORME["libro"]
    for k in ("proteccion", "fecha_1904", "tema", "fuente_defecto", "estilo_defecto"):
        assert u_diseno.comparar(esp[k], libro[k], k) == [], k
    assert u_diseno.comparar(esp["estilos_tabla"], libro["estilos_tabla"]) == []
    assert u_diseno.sha256_tema(gen["contenido"]) == esp["tema_sha256"]
    # dxfs@count: la plantilla guarda 3 iguales; xlsxwriter, 1 (``dxf_deduplicado``).
    assert len(esp["dxfs"]) == 3 and all(d == esp["dxfs"][0] for d in esp["dxfs"])
    assert len(libro["dxfs"]) == 1
    assert u_diseno.comparar(esp["dxfs"][0], libro["dxfs"][0]) == []
    with zipfile.ZipFile(io.BytesIO(gen["contenido"])) as z:
        estilos_xml = z.read("xl/styles.xml").decode()
    assert re.search(r'<dxfs count="1">', estilos_xml)
    for nombre in ("Todos los activos", "Electrónica", "Mobiliario"):
        for regla in gen["hojas"][nombre]["formato_condicional"]:
            assert u_diseno.comparar(esp["dxfs"][0], regla["dxf"], nombre) == []

    # Nombres definidos: área de cada hoja hasta su última fila, filas a repetir de las
    # listas y, por Q8, el filtro oculto de las hojas con autofiltro.
    def hoja_(nombre: str) -> str:
        return f"'{nombre}'" if " " in nombre else nombre

    ultimas = {
        "Todos los activos": ("J", 12),
        "Por ubicación": ("H", 9),
        "No encontrados": ("F", 10),
        "Electrónica": ("I", 11),
        "Mobiliario": ("I", 10),
        "Por categoría": ("H", 10),
        "Resumen": ("J", 14),
    }
    esperados = []
    for i, nombre in enumerate(LIBRO_HOJAS):
        col, fila = ultimas[nombre]
        esperados.append(
            {
                "nombre": "_xlnm.Print_Area",
                "hoja": i,
                "oculto": False,
                "valor": f"{hoja_(nombre)}!$A$1:${col}${fila}",
            }
        )
        if nombre in ("Todos los activos", "No encontrados", "Electrónica", "Mobiliario"):
            esperados.append(
                {
                    "nombre": "_xlnm.Print_Titles",
                    "hoja": i,
                    "oculto": False,
                    "valor": f"{hoja_(nombre)}!$9:$9",
                }
            )
        if nombre in ("No encontrados", "Electrónica", "Mobiliario"):
            esperados.append(
                {
                    "nombre": "_xlnm._FilterDatabase",
                    "hoja": i,
                    "oculto": True,
                    "valor": f"{hoja_(nombre)}!$A$9:${col}${fila}",
                }
            )
    # La plantilla: un área por hoja y filas a repetir en las tres listas (sin filtros).
    assert {d["nombre"] for d in esp["nombres_definidos"]} == {
        "_xlnm.Print_Area",
        "_xlnm.Print_Titles",
    }

    def orden(lista):
        return sorted(lista, key=lambda d: (d["hoja"], d["nombre"]))

    assert u_diseno.comparar(orden(esperados), orden(libro["nombres_definidos"])) == []

    # Fila 26 (decisión del humano): título del libro, autor neutro, nada del equipo.
    core = libro["propiedades"]["core"]
    assert core["title"] == "Informe · Conteo nov 2026"
    assert core["creator"] == core["lastModifiedBy"] == est.AUTOR == "AssetControl"
    assert set(core) == {"title", "creator", "lastModifiedBy", "created", "modified"}
    assert libro["propiedades"]["app"] == {
        "Application": "Microsoft Excel",
        "AppVersion": "12.0000",
        "Company": None,
    }
    assert libro["medios"] == ["xl/media/image1.png"]  # Q13: un medio para las 7 hojas


# Cobertura XML del libro completo (fila 27), en las dos direcciones. Lo que el generado
# escribe y la plantilla no, y por qué:
SOBRANTES_LIBRO = {
    "workbook": (
        (r"workbook/definedNames/definedName@hidden", "Q8: _FilterDatabase oculto (filtros)"),
        (r"workbook/fileVersion(@\w+)?", "ventana_y_aplicacion (equivalente aceptado)"),
        (r"workbook/workbookPr@defaultThemeVersion", "EQ L10: workbookPr sin efecto"),
    ),
    "styles": (
        (
            r"styleSheet/cellXfs/xf@apply(Alignment|Border|Fill|Font|NumberFormat|Protection)",
            "ventana_y_aplicacion: banderas apply* (equivalente aceptado)",
        ),
    ),
    "sheet": (
        (r"worksheet/tableParts.*", "Q8: tabla «Activos» conservada"),
        (r"worksheet/autoFilter.*", "Q8: filtros conservados"),
        (r"worksheet/sheetData/row@spans", "pistas_fila (equivalente aceptado)"),
        (
            r"worksheet/conditionalFormatting/cfRule/dataBar/cfvo@val",
            "cfvo_val_min_max (equivalente aceptado, L5)",
        ),
    ),
    "drawing": ((r"wsDr/twoCellAnchor.*", "Q13: ancla twoCellAnchor editAs=oneCell (L8)"),),
    "table": ((r"table.*", "Q8: la parte de la tabla «Activos»"),),
}
# Lo que la plantilla trae y el generado no escribe, y por qué (además de lo que la matriz
# ya clasifica como EQ, Q11 o «valores por defecto»):
FALTANTES_LIBRO = {
    "workbook": (
        (r"workbook/sheets/sheet@state", 'state="visible" por omisión (estados comparados)'),
    ),
    "styles": (
        (
            r"styleSheet/dxfs/dxf/fill/patternFill(/fgColor(@rgb)?|@patternType)",
            "dxf_patternType (equivalente aceptado, L4)",
        ),
        # ``<b val="1"/>``/``<i val="1"/>`` frente a ``<b/>``/``<i/>``: ``val`` vale ``true``
        # por omisión (ECMA-376); negrita y cursiva se comparan resueltas y coinciden.
        (r"styleSheet/fonts/font/b@val", "val por omisión de <b> (negrita resuelta igual)"),
        (r"styleSheet/dxfs/dxf/font/i@val", "val por omisión de <i> (cursiva resuelta igual)"),
    ),
    "sheet": (
        (r"worksheet/cols/col@style", "L7: el estilo de columna resuelve al por defecto"),
        (r"worksheet/pageSetup@fitToWidth", "fitToWidth=1 por omisión (ajuste comparado)"),
        (r"worksheet/sheetData/row/c/is(/t)?", "cadenas: inlineStr vs sharedStrings"),
    ),
}


# Sesión antigua (sin detalle): no hay hojas de lista con la regla de fila completa, así que
# tampoco su fórmula ni su dxf; el resto del libro se cubre igual.
FALTANTES_SIN_DETALLE = {
    "sheet": (
        (r"worksheet/conditionalFormatting/cfRule(/formula|@dxfId)", "sin listas"),
        (r"worksheet/sheetData/row@(customFormat|s)", "sin hoja por categoría (estilo de f6)"),
    ),
    "styles": ((r"styleSheet/dxfs/.+", "sin listas: sin dxf"),),
}


def _aceptada_faltante(parte: str, ruta: str, generado: set[str], detalle: bool = True) -> bool:
    if not detalle and any(re.fullmatch(p, ruta) for p, _ in FALTANTES_SIN_DETALLE.get(parte, ())):
        return True
    destino = u_diseno.destino_cobertura(f"{parte}:{ruta}") or ""
    # «EQ …» = equivalente no idéntico (Q13) o aceptado (humano); Q11 = residuo de edición.
    if re.search(r"\bEQ\b", destino) or "(Q11)" in destino or "(valores por defecto)" in destino:
        return True
    if parte == "drawing" and ruta.startswith("wsDr/oneCellAnchor"):
        # Q13: el mismo elemento bajo twoCellAnchor; el «ext» del ancla va en xfrm y «to».
        gemela = ruta.replace("oneCellAnchor", "twoCellAnchor")
        return gemela in generado or ruta.startswith("wsDr/oneCellAnchor/ext")
    return any(re.fullmatch(p, ruta) for p, _ in FALTANTES_LIBRO.get(parte, ()))


@pytest.mark.parametrize("detalle", [True, False], ids=["con_detalle", "sesion_antigua"])
def test_cobertura_xml_del_libro_completo_en_las_dos_direcciones(detalle):
    """Fila 27: cada elemento y atributo del libro (workbook, styles, todas las hojas, sus
    dibujos y la tabla) está en la plantilla o es una decisión registrada; y cada uno de la
    plantilla está en el generado o tiene su equivalente/decisión. Sin sobrantes ni
    faltantes sin clasificar."""
    informe = _informe_diseno()
    if not detalle:
        informe["detalle_disponible"] = False
    gen = _generar_informe(informe, detalle=None if detalle else [])
    generado = u_diseno.inventario_xml(gen["contenido"])
    plantilla = HUELLA_INFORME["inventario_xml"]
    partes = {"workbook", "styles", "sheet", "drawing"}
    assert set(plantilla) == partes
    assert set(generado) == partes | ({"table"} if detalle else set())
    for parte in sorted(generado):
        sobran = set(generado[parte]) - set(plantilla.get(parte, ()))
        for ruta in sorted(sobran):
            assert any(re.fullmatch(p, ruta) for p, _ in SOBRANTES_LIBRO.get(parte, ())), (
                f"sobra en el generado: {parte}:{ruta}"
            )
    for parte in sorted(plantilla):
        faltan = set(plantilla[parte]) - set(generado[parte])
        for ruta in sorted(faltan):
            assert _aceptada_faltante(parte, ruta, set(generado[parte]), detalle), (
                f"falta en el generado: {parte}:{ruta} "
                f"({u_diseno.destino_cobertura(f'{parte}:{ruta}')})"
            )
    # Cada dibujo pertenece a una hoja; las 7 hojas llevan logo (un medio, Q13).
    assert len(gen["libro"]["hojas"]) == sum(1 for h in gen["hojas"].values() if h["imagenes"])


def test_las_decisiones_de_t5_estan_en_la_matriz():
    texto = u_diseno.MATRIZ.read_text(encoding="utf-8")
    seccion = texto.split("## Libro del informe (T5)", 1)[1]
    for clave in u_diseno.DECISIONES_T5:
        assert f"`{clave}`" in seccion, clave
