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
    # Spec 019 (T4): las hojas de lista llevan el bloque de la plantilla (empresa en C3) y su
    # encabezado de impresión queda vacío (B5, Q7); el Resumen conserva el suyo hasta T5.
    for hoja in wb.worksheets[1:]:
        assert hoja["C3"].value == empresa and hoja["C3"].data_type == "s", hoja.title
    esperado = (
        f"&L&8 {exportar._cabecera_impresion(empresa)}&R&8 {exportar._cabecera_impresion(sesion)}"
    )
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
        for i, nombre in enumerate(hojas):
            cabeceras = re.findall(r"<oddHeader>(.*?)</oddHeader>", z.read(nombre).decode())
            assert [html.unescape(c) for c in cabeceras] == ([esperado] if i == 0 else []), nombre
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
    assert empresa.contacto == "NIT 900.123.456-8 · Calle 10 # 5-20, Cartago"
    assert exportar.Empresa(nombre="X").contacto == ""


# --- Spec 019, T4: hojas de lista del informe según la plantilla B ------------------------
#
# «Todos los activos», cada hoja por categoría y «No encontrados» se comparan, propiedad por
# propiedad, contra la huella ``tests/plantillas/informe.json`` (FT-1 a FT-3). Empresa y
# activos FICTICIOS (R8). El Resumen y el orden del libro son de T5.
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
    "No encontrados": "No encontrados",
    "Electrónica": u_diseno.MARCA_CATEGORIA,
    "Mobiliario": u_diseno.MARCA_CATEGORIA,
}
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


def comprobar_lista(gen: dict, nombre: str, cuerpo: dict[str, str | None], filas: list) -> None:
    """Una hoja de lista contra la huella: hoja, filas 1–9 (bloque, título, nota, Total y
    cabecera) con sus textos ``cuerpo`` (ref → texto) y cada fila de datos."""
    hoja, esp = gen["hojas"][nombre], _esperada_informe(nombre)
    for k in ("pestana", "esquema", "combinadas", "validaciones", "hipervinculos", "proteccion"):
        assert u_diseno.comparar(esp[k], hoja[k], f"{nombre}.{k}") == [], k
    for k in ("alto_fila_defecto", "filas_ocultas_defecto", "alto_propio_defecto"):
        assert hoja["formato_hoja"][k] == esp["formato_hoja"][k], k

    def sin_estilo(cols):
        return [{k: v for k, v in c.items() if k != "estilo"} for c in cols]

    assert u_diseno.comparar(sin_estilo(esp["columnas"]), sin_estilo(hoja["columnas"])) == []
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
    (img_esp,) = esp["imagenes"]
    (img,) = hoja["imagenes"]
    assert (img["ancla"], img["edit_as"]) == ("twoCellAnchor", "oneCell")
    assert u_diseno.comparar(img_esp["desde"], img["desde"], "desde") == []
    assert (img["xfrm"]["x"], img["xfrm"]["y"]) == (img_esp["xfrm"]["x"], img_esp["xfrm"]["y"])
    caja, cx, cy = img_esp["ext"], img["xfrm"]["cx"], img["xfrm"]["cy"]
    assert (cx == caja["cx"] and cy <= caja["cy"]) or (cy == caja["cy"] and cx <= caja["cx"])
    for k in ("descr", "titulo", "oculta", "decorativa", "estirar", "geometria"):
        assert img[k] == img_esp[k], k


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


# Lo que las hojas de lista escriben y la plantilla no, y por qué.
SOBRANTES_LISTAS = (
    (r"worksheet/tableParts.*", "Q8: tabla «Activos» conservada"),
    (r"worksheet/autoFilter.*", "Q8: filtros conservados"),
    (r"wsDr/twoCellAnchor.*", "Q13: ancla twoCellAnchor editAs=oneCell (y picLocks, L8)"),
    (r"worksheet/sheetData/row@spans", "pistas_fila (equivalente aceptado, L10)"),
)


def _rutas(xml: bytes) -> set[str]:
    from xml.etree import ElementTree as ET  # noqa: S405 - archivo generado por la prueba

    rutas: set[str] = set()

    def recorrer(el, ruta: str) -> None:
        r = f"{ruta}/{u_diseno._local(el.tag)}" if ruta else u_diseno._local(el.tag)
        rutas.add(r)
        rutas.update(f"{r}@{u_diseno._local(k)}" for k in el.attrib)
        for h in el:
            recorrer(h, r)

    recorrer(ET.fromstring(xml), "")  # noqa: S314
    return rutas


def test_las_hojas_de_lista_no_escriben_nada_fuera_de_la_plantilla():
    """Cobertura XML (fila 27) de las hojas de lista y sus dibujos: todo lo que escriben
    está en la plantilla o es una decisión (Q8, Q13). El libro completo (Resumen y estilos)
    se cubre en T5, cuando el Resumen pase a la plantilla."""
    contenido = _generar_informe()["contenido"]
    plantilla = HUELLA_INFORME["inventario_xml"]
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        nombres = re.findall(r'<sheet name="([^"]+)"', z.read("xl/workbook.xml").decode())
        dibujos = set()
        for i, nombre in enumerate(nombres, start=1):
            if html.unescape(nombre) == "Resumen":
                continue
            parte = f"xl/worksheets/sheet{i}.xml"
            sobran = _rutas(z.read(parte)) - set(plantilla["sheet"])
            for ruta in sorted(sobran):
                assert any(re.fullmatch(p, ruta) for p, _ in SOBRANTES_LISTAS), (nombre, ruta)
            rels = z.read(f"xl/worksheets/_rels/sheet{i}.xml.rels").decode()
            dibujos |= {f"xl/drawings/{d}" for d in re.findall(r"drawings/(drawing\d+\.xml)", rels)}
        assert len(dibujos) == len(nombres) - 1
        for parte in sorted(dibujos):
            sobran = _rutas(z.read(parte)) - set(plantilla["drawing"])
            for ruta in sorted(sobran):
                assert any(re.fullmatch(p, ruta) for p, _ in SOBRANTES_LISTAS), (parte, ruta)
