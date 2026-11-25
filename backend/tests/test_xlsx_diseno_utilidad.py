"""Utilidad de huella de diseño, huella versionada y cobertura XML (spec 019, T1).

- La huella versionada (``tests/plantillas/*.json``) no contiene datos reales: todo texto de
  celda es un rótulo fijo de la lista cerrada o un marcador (R8, D-3).
- ``comparar`` informa «ruta: esperado …, obtenido …» y no compara el canal alfa (Q13).
- Cobertura (``test_cobertura_matriz``): cada elemento/atributo XML de las plantillas tiene
  fila en la matriz o está declarado equivalente/decidido.
- ``matriz.md`` está sincronizada con la huella.
- Deriva: si las plantillas locales existen (``informes/``), la huella coincide con ellas.
"""

from __future__ import annotations

import io
import json
import re

import pytest
import utils_xlsx_diseno as u
import xlsxwriter

HUELLAS = {k: u.cargar_huella(k) for k in u.PLANTILLAS}
MARCADOR = re.compile(r"^\{[A-Za-z_.]+\}$")
PERMITIDOS_BLOQUE = {
    "NIT {empresa.nit}",
    "Tel. {empresa.telefono}",
    "Corte {fecha}",
    "Exportado {fecha}",
    "Categoría: {categoria}",
    # Línea junto al logo (decisión del humano 2026-11-24).
    "Informe · {empresa.nombre} · exportado {fecha}",
    "Informe · {empresa.nombre} · corte {fecha}",
    "Empresa",
    "Contacto",
    "Dirección",
    "{empresa.nombre}\nNIT {empresa.nit}",
    "{empresa.correo}\nTel. {empresa.telefono}",
    # Panel «Sesión» del Resumen (opción C, 2026-11-24); sus valores van como {texto}.
    "Sesión",
    "Nombre",
    "Cerró",
    "Cerrada",
    "Moneda",
    "COP",
    "Estado",
    "Informe congelado",
}


def _xlsx(construir) -> bytes:
    salida = io.BytesIO()
    wb = xlsxwriter.Workbook(salida, {"in_memory": True})
    construir(wb, wb.add_worksheet("Hoja"))
    wb.close()
    return salida.getvalue()


# ---------------------------------------------------------------------------
# Huella versionada
# ---------------------------------------------------------------------------


def test_huellas_tienen_las_hojas_de_las_plantillas():
    assert HUELLAS["activos"]["libro"]["hojas"] == ["Activos"]
    assert HUELLAS["informe"]["libro"]["hojas"] == [
        "Todos los activos",
        "Por ubicación",
        "No encontrados",
        u.MARCA_CATEGORIA,
        "Por categoría",
        "Resumen",
    ]
    for h in HUELLAS.values():
        assert list(h["hojas"]) == h["libro"]["hojas"]


@pytest.mark.parametrize("clave", list(HUELLAS))
def test_huella_sin_datos_reales(clave):
    h = HUELLAS[clave]
    for nombre, hoja in h["hojas"].items():
        for ref, celda in hoja["celdas"].items():
            v = celda["valor"]
            if v is None:
                continue
            assert (
                v in u.ROTULOS_FIJOS
                or v in u.FRASES_CON_MARCADORES
                or v in PERMITIDOS_BLOQUE
                or MARCADOR.match(v)
            ), f"{nombre}!{ref}: texto no permitido en la huella"
    core = h["libro"]["propiedades"]["core"]
    assert core.get("creator") in (None, "openpyxl")
    assert all(MARCADOR.match(v) for k, v in core.items() if k != "creator" and v)
    # El hash del tema (hex) no es un dato; se quita para que no confunda la búsqueda.
    sin_hash = {**h, "libro": {k: v for k, v in h["libro"].items() if k != "tema_sha256"}}
    assert re.fullmatch(r"[0-9a-f]{64}", h["libro"]["tema_sha256"])
    texto = json.dumps(sin_hash, ensure_ascii=False)
    assert not re.search(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", texto), "correo en la huella"
    assert not re.search(r"\d{3}[ .-]?\d{3}[ .-]?\d{4}", texto), "teléfono en la huella"
    assert not re.search(r"NIT \d", texto), "NIT en la huella"
    # La ruta local que trae AlternateContent/absPath (solo el nombre del elemento entra en
    # el inventario XML, nunca su valor).
    assert "Downloads" not in texto and "Users" not in texto and ":\\\\" not in texto


def test_negrita_confirmada_y_fila_5_con_el_ancho_de_la_banda():
    """Hallazgos de T1: ``N`` es negrita y la fila 5 tiene borde donde está la banda."""
    for h in HUELLAS.values():
        for nombre, hoja in h["hojas"].items():
            assert hoja["celdas"]["C2"]["estilo"]["fuente"]["negrita"] is True, nombre
            banda = {
                ref[:-1]
                for ref, c in hoja["celdas"].items()
                if ref.endswith("1")
                and len(ref) == 2
                and c["estilo"]["relleno"]["patron"] == "solid"
            }
            fila5 = {
                ref[:-1]
                for ref, c in hoja["celdas"].items()
                if ref.endswith("5")
                and len(ref) == 2
                and (c["estilo"]["borde"]["bottom"] or {}).get("estilo") == "medium"
            }
            assert banda == fila5, nombre


def test_dxf_y_barras_medidos():
    informe = HUELLAS["informe"]
    for dxf in informe["libro"]["dxfs"]:
        assert dxf["fuente"]["cursiva"] is True
        assert dxf["fuente"]["color"] == {"rgb": "FF92400E"}
        assert dxf["relleno"] == {"patron": "solid", "color": {"rgb": "FFFDE68A"}}
    for nombre in ("Por ubicación", "Por categoría"):
        for cf in informe["hojas"][nombre]["formato_condicional"]:
            assert cf["barra"]["ext"] == []
            assert cf["barra"]["color"] == {"rgb": "FFBFDBFE"}
            assert [c["tipo"] for c in cf["barra"]["cfvo"]] == ["min", "max"]
    for h in HUELLAS.values():
        for hoja in h["hojas"].values():
            assert hoja["pagina"]["cuadricula_impresa"] is False
            (img,) = hoja["imagenes"]
            assert img["descr"] == "Picture"


# ---------------------------------------------------------------------------
# Enmascarado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "fila", "col", "esperado"),
    [
        ("Empresa Ejemplo S.A.S.", 3, 3, "{empresa.nombre}"),
        ("NIT 900.123.456-7", 4, 3, "NIT {empresa.nit}"),
        ("Tel. 300 000 0000", 4, 5, "Tel. {empresa.telefono}"),
        ("contacto@ejemplo.test", 4, 6, "{empresa.correo}"),
        ("Calle Falsa 123", 5, 3, "{empresa.direccion}"),
        ("Corte 01/02/2030", 3, 5, "Corte {fecha}"),
        ("Exportado 01/02/2030", 3, 5, "Exportado {fecha}"),
        ("Correo", 3, 6, "Correo"),
        ("Otro dato", 4, 9, "{texto}"),
        ("Precio (COP)", 9, 10, "Precio (COP)"),
        ("Categoría: Mobiliario", 6, 1, "Categoría: {categoria}"),
        ("3 activos no encontrados por $ 1.234,50.", 7, 1, "{n} activos no encontrados por {cop}."),
        ("Texto libre que no es rótulo", 7, 1, "{texto}"),
    ],
)
def test_marcar_texto(texto, fila, col, esperado):
    assert u.marcar_texto(texto, "Todos los activos", fila, col) == esperado


def test_filas_de_datos_siempre_con_marcador():
    # Aunque el texto coincida con un rótulo, en una fila de datos es un dato.
    assert u.marcar_texto("Encontrado", "Todos los activos", 10, 9) == "{texto}"


# ---------------------------------------------------------------------------
# Comparación
# ---------------------------------------------------------------------------


def test_comparar_igual_no_da_diferencias():
    h = HUELLAS["activos"]
    assert u.comparar(h, json.loads(json.dumps(h))) == []


def test_comparar_informa_ruta_esperado_y_obtenido():
    difs = u.comparar({"a": {"b": 1, "c": [1, 2]}}, {"a": {"b": 2, "c": [1], "d": 0}})
    assert "a.b: esperado 1, obtenido 2" in difs
    assert any(d.startswith("a.c: esperado 2 elementos") for d in difs)
    assert "a.d: esperado <ausente>, obtenido 0" in difs


def test_comparar_ignora_solo_el_canal_alfa():
    assert u.comparar({"color": {"rgb": "009CA3AF"}}, {"color": {"rgb": "FF9CA3AF"}}) == []
    assert u.comparar({"color": {"rgb": "009CA3AF"}}, {"color": {"rgb": "FF9CA3AE"}}) != []
    assert u.comparar({"color": {"theme": 1}}, {"color": {"rgb": "FF000000"}}) != []


def test_comparar_flotantes():
    assert u.comparar({"alto": 20.1}, {"alto": 20.100000000000001}) == []
    assert u.comparar({"alto": 20.1}, {"alto": 20.25}) != []


# ---------------------------------------------------------------------------
# Extracción sobre un archivo generado
# ---------------------------------------------------------------------------


def test_extraer_archivo_generado():
    def construir(wb, ws):
        ws.set_tab_color("#1D4ED8")
        ws.hide_gridlines(2)
        ws.set_row_pixels(1, 44.1 / 0.75)
        ws.set_column_pixels(1, 1, 7 * 26)
        ws.write(
            1,
            2,
            "Informe de activos",
            wb.add_format(
                {
                    "font_name": "Arial",
                    "font_size": 19,
                    "bold": True,
                    "font_color": "#111827",
                    "font_family": 0,
                    "valign": "vcenter",
                }
            ),
        )
        ws.write_number(2, 0, 45000, wb.add_format({"num_format": '"$"\\ #,##0.00'}))
        ws.merge_range("A7:J7", "nota")
        ws.freeze_panes(9, 0)

    h = u.extraer(_xlsx(construir))
    hoja = h["hojas"]["Hoja"]
    assert hoja["pestana"] == {"rgb": "FF1D4ED8"}
    assert hoja["vista"]["cuadricula"] is False
    assert hoja["filas"]["2"]["alto"] == 44.1
    assert hoja["columnas"][0]["ancho"] == 26
    assert (
        u.comparar(
            HUELLAS["informe"]["hojas"]["Todos los activos"]["celdas"]["C2"]["estilo"],
            hoja["celdas"]["C2"]["estilo"],
        )
        == []
    )
    assert hoja["celdas"]["A3"]["estilo"]["formato"]["codigo"] == '"$"\\ #,##0.00'
    assert hoja["combinadas"] == ["A7:J7"]
    assert hoja["vista"]["panel"]["y_split"] == 9


# ---------------------------------------------------------------------------
# Cobertura XML (fila 27 de la matriz)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("clave", list(HUELLAS))
def test_cobertura_matriz(clave):
    sin_fila = [
        f"{tipo}:{ruta}"
        for tipo, rutas in HUELLAS[clave]["inventario_xml"].items()
        for ruta in rutas
        if u.destino_cobertura(f"{tipo}:{ruta}") is None
    ]
    assert sin_fila == []


def test_cobertura_tambien_clasifica_lo_que_genera_xlsxwriter():
    def construir(wb, ws):
        ws.write(0, 0, "x", wb.add_format({"bold": True}))

    sin_fila = [
        f"{tipo}:{ruta}"
        for tipo, rutas in u.inventario_xml(_xlsx(construir)).items()
        for ruta in rutas
        if u.destino_cobertura(f"{tipo}:{ruta}") is None
    ]
    assert sin_fila == []


def test_matriz_sincronizada_con_la_huella():
    assert u.MATRIZ.read_text(encoding="utf-8") == u.generar_matriz(HUELLAS)


def test_matriz_registra_las_decisiones_de_t4():
    """«No encontrados» con los estilos de datos de las listas (humano 2026-11-22), sin
    marcarlo como omitido; celda vacía y columnas ocultas G–K."""
    texto = u.MATRIZ.read_text(encoding="utf-8")
    seccion = texto.split("## Hojas de lista del informe (T4)", 1)[1]
    for clave in ("no_encontrados_datos", "celda_vacia_informe", "columnas_ocultas_no_encontrados"):
        assert f"`{clave}`" in seccion, clave
    assert "Decisión del humano 2026-11-22" in seccion
    assert "NO REPRODUCIDO" not in seccion


def test_matriz_sin_datos_reales():
    texto = u.MATRIZ.read_text(encoding="utf-8")
    assert not re.search(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", texto)
    assert not re.search(r"\d{3}[ .-]?\d{3}[ .-]?\d{4}", texto)
    assert not re.search(r"NIT \d", texto)


# ---------------------------------------------------------------------------
# Deriva respecto de las plantillas locales (se omite si no están: CI)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("clave", "archivo"), list(u.PLANTILLAS.items()))
def test_huella_coincide_con_la_plantilla_local(clave, archivo):
    ruta = u.DIR_PLANTILLAS / archivo
    if not ruta.exists():
        pytest.skip("plantilla local no disponible (informes/ no se versiona)")
    fresca = json.loads(json.dumps(u.huella_de_plantilla(ruta), ensure_ascii=False))
    assert u.comparar(fresca, HUELLAS[clave]) == []
