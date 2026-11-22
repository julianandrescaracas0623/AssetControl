"""Sondas L1–L10 de la spec 019 (T1): ¿puede ``xlsxwriter==3.3.1`` reproducir la plantilla?

Cada sonda genera un ``.xlsx`` mínimo con xlsxwriter, lo lee con la utilidad de diseño
(ZIP + XML, no con la librería que lo escribió) y lo compara contra la huella versionada
(``tests/plantillas/*.json``), propiedad por propiedad. Los valores esperados salen de la
huella, nunca de números escritos aquí.

Resultado (detalle en ``specs/019-diseno-informes-excel/matriz.md``):

- L1: xlsxwriter NO escribe ``oneCellAnchor``; escribe ``twoCellAnchor editAs="oneCell"``
  con desplazamiento y tamaño EXACTOS en EMU → se usa el equivalente aprobado en Q13.
- L2–L7, L9: se reproducen.
- L8: el texto alternativo se reproduce; el nombre (``Picture N`` en vez de ``Image 1``) y
  el bloqueo de proporción son equivalentes ACEPTADOS por el humano (2026-11-22): se fijan.
- L10: metadatos del paquete que xlsxwriter no controla (aceptados por el humano
  2026-11-22); se fijan aquí para que ninguno se oculte.
- Fila 26: propiedades del documento (título del libro, ``creator`` = ``AssetControl``).
"""

from __future__ import annotations

import inspect
import io
from typing import Any

import pytest
import utils_xlsx_diseno as u
import xlsxwriter
import xlsxwriter.drawing
from PIL import Image
from xlsxwriter.color import Color

HUELLAS = {k: u.cargar_huella(k) for k in u.PLANTILLAS}
HOJA = "Sonda"


def _png(ancho: int, alto: int) -> io.BytesIO:
    b = io.BytesIO()
    Image.new("RGB", (ancho, alto), (29, 78, 216)).save(b, format="PNG")
    b.seek(0)
    return b


def _libro(construir) -> dict[str, Any]:
    salida = io.BytesIO()
    wb = xlsxwriter.Workbook(salida, {"in_memory": True})
    ws = wb.add_worksheet(HOJA)
    construir(wb, ws)
    wb.close()
    return {"bytes": salida.getvalue(), "huella": u.extraer(salida.getvalue())}


def _hojas() -> list[tuple[str, str, dict[str, Any]]]:
    return [(k, n, h) for k, hu in HUELLAS.items() for n, h in hu["hojas"].items()]


def _ids(casos):
    return [f"{k}/{n}" for k, n, _ in casos]


def _filas_y_columnas(ws, hoja: dict[str, Any]) -> None:
    for num, f in hoja["filas"].items():
        if f["alto"] is not None:
            ws.set_row_pixels(int(num) - 1, f["alto"] / 0.75)
    for c in hoja["columnas"]:
        ws.set_column_pixels(
            c["min"] - 1, c["max"] - 1, round(c["ancho"] * 7), None, {"hidden": c["oculta"]}
        )


# ---------------------------------------------------------------------------
# L1: ancla, desplazamiento y tamaño de la imagen
# ---------------------------------------------------------------------------


def test_l1_xlsxwriter_no_escribe_one_cell_anchor():
    """Decide el ancla (Q13): xlsxwriter 3.3.1 no tiene escritor de ``oneCellAnchor``."""
    assert xlsxwriter.__version__ == "3.3.1"
    fuente = inspect.getsource(xlsxwriter.drawing)
    assert "oneCellAnchor" not in fuente
    assert "twoCellAnchor" in fuente


@pytest.mark.parametrize(("clave", "nombre", "hoja"), _hojas(), ids=_ids(_hojas()))
def test_l1_imagen_mismo_desplazamiento_y_tamano(clave, nombre, hoja):
    (img,) = hoja["imagenes"]
    assert img["ancla"] == "oneCellAnchor"  # lo que trae la plantilla
    d, e = img["desde"], img["ext"]
    ancho, alto = img["imagen"]["ancho"], img["imagen"]["alto"]

    def construir(wb, ws):
        _filas_y_columnas(ws, hoja)
        ws.insert_image(
            d["fila"],
            d["col"],
            "logo.png",
            {
                "image_data": _png(ancho, alto),
                "x_offset": d["col_off"] / u.EMU_POR_PX,
                "y_offset": d["fila_off"] / u.EMU_POR_PX,
                "x_scale": e["cx"] / u.EMU_POR_PX / ancho,
                "y_scale": e["cy"] / u.EMU_POR_PX / alto,
                "object_position": 2,
                "description": img["descr"],
            },
        )

    (gen,) = _libro(construir)["huella"]["hojas"][HOJA]["imagenes"]
    # Equivalente aprobado (Q13): twoCellAnchor que se mueve pero no cambia de tamaño.
    assert (gen["ancla"], gen["edit_as"]) == ("twoCellAnchor", "oneCell")
    assert u.comparar(d, gen["desde"], f"{nombre}.desde") == []
    assert u.comparar(img["xfrm"], gen["xfrm"], f"{nombre}.xfrm") == []
    assert (gen["xfrm"]["cx"], gen["xfrm"]["cy"]) == (e["cx"], e["cy"])
    assert u.comparar(img["imagen"], gen["imagen"], f"{nombre}.imagen") == []
    assert gen["estirar"] == img["estirar"]
    assert gen["geometria"] == img["geometria"]


# ---------------------------------------------------------------------------
# L2: tema y fuente por defecto
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("clave", list(HUELLAS))
def test_l2_tema_y_fuente_por_defecto(clave):
    gen = _libro(lambda wb, ws: ws.write(0, 0, "x"))
    libro = HUELLAS[clave]["libro"]
    assert u.sha256_tema(gen["bytes"]) == libro["tema_sha256"]
    assert u.comparar(libro["tema"], gen["huella"]["libro"]["tema"]) == []
    assert u.comparar(libro["fuente_defecto"], gen["huella"]["libro"]["fuente_defecto"]) == []
    assert u.comparar(libro["estilo_defecto"], gen["huella"]["libro"]["estilo_defecto"]) == []


# ---------------------------------------------------------------------------
# L3: papel no declarado, orientación, ajuste, márgenes, pie, cuadrícula
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("clave", "nombre", "hoja"), _hojas(), ids=_ids(_hojas()))
def test_l3_pagina_sin_papel_declarado(clave, nombre, hoja):
    p = hoja["pagina"]
    m = p["margenes"]

    def construir(wb, ws):
        ws.set_landscape()
        ws.fit_to_pages(p["ajuste_ancho"], p["ajuste_alto"])
        ws.set_margins(m["left"], m["right"], m["top"], m["bottom"])
        ws.set_footer(p["encabezado_pie"]["oddFooter"], {"margin": m["footer"]})
        ws.set_header("", {"margin": m["header"]})
        ws.hide_gridlines(2)
        ws.write(0, 0, "x")

    gen = _libro(construir)["huella"]["hojas"][HOJA]
    assert p["papel"] is None and gen["pagina"]["papel"] is None
    assert u.comparar(p, gen["pagina"], f"{nombre}.pagina") == []
    assert gen["vista"]["cuadricula"] is hoja["vista"]["cuadricula"] is False
    assert gen["vista"]["zoom"] is hoja["vista"]["zoom"] is None


# ---------------------------------------------------------------------------
# L4: formato condicional por fórmula con su dxf
# ---------------------------------------------------------------------------

CASOS_L4 = [
    (k, n, h)
    for k, n, h in _hojas()
    if any(c["tipo"] == "expression" for c in h["formato_condicional"])
]


@pytest.mark.parametrize(("clave", "nombre", "hoja"), CASOS_L4, ids=_ids(CASOS_L4))
def test_l4_formato_condicional_formula_y_dxf(clave, nombre, hoja):
    reglas = hoja["formato_condicional"]

    def construir(wb, ws):
        for r in reglas:
            ws.conditional_format(
                r["rango"],
                {
                    "type": "formula",
                    "criteria": "=" + r["formulas"][0],
                    "format": wb.add_format(u.dxf_xlsxwriter(r["dxf"])),
                },
            )

    gen = _libro(construir)["huella"]["hojas"][HOJA]
    assert u.comparar(reglas, gen["formato_condicional"], f"{nombre}.cf") == []
    # Contenido del dxf medido en T1: cursiva, color 92400E, relleno sólido FDE68A.
    assert reglas[0]["dxf"]["fuente"]["cursiva"] is True


def test_l4_rango_se_extiende_con_mas_filas():
    """Req. 5: el rango literal (…499) puede crecer hasta la última fila escrita."""
    (regla,) = HUELLAS["informe"]["hojas"]["Todos los activos"]["formato_condicional"]

    def construir(wb, ws):
        ws.conditional_format(
            "A10:J2000",
            {
                "type": "formula",
                "criteria": "=" + regla["formulas"][0],
                "format": wb.add_format(u.dxf_xlsxwriter(regla["dxf"])),
            },
        )

    (gen,) = _libro(construir)["huella"]["hojas"][HOJA]["formato_condicional"]
    assert gen["rango"] == "A10:J2000"
    assert gen["formulas"] == regla["formulas"]


# ---------------------------------------------------------------------------
# L5: barras de datos sin extensión 2010
# ---------------------------------------------------------------------------

CASOS_L5 = [
    (k, n, h)
    for k, n, h in _hojas()
    if any(c["tipo"] == "dataBar" for c in h["formato_condicional"])
]


def _sin_val_min_max(reglas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Excel ignora ``val`` en cfvo min/max (equivalente aceptado ``cfvo_val_min_max``)."""
    salida = []
    for r in reglas:
        r = dict(r)
        if "barra" in r:
            barra = dict(r["barra"])
            barra["cfvo"] = [
                {"tipo": c["tipo"], "valor": None if c["tipo"] in ("min", "max") else c["valor"]}
                for c in barra["cfvo"]
            ]
            r["barra"] = barra
        salida.append(r)
    return salida


@pytest.mark.parametrize(("clave", "nombre", "hoja"), CASOS_L5, ids=_ids(CASOS_L5))
def test_l5_barras_de_datos(clave, nombre, hoja):
    reglas = hoja["formato_condicional"]
    assert {r["tipo"] for r in reglas} == {"dataBar"}

    def construir(wb, ws):
        for r in reglas:
            ws.conditional_format(
                r["rango"],
                {
                    "type": "data_bar",
                    "bar_color": "#" + r["barra"]["color"]["rgb"][-6:],
                    "data_bar_2010": False,
                },
            )

    gen = _libro(construir)["huella"]["hojas"][HOJA]
    assert all(r["barra"]["ext"] == [] for r in gen["formato_condicional"])
    assert gen["formato_condicional_ext"] == hoja["formato_condicional_ext"] == []
    assert (
        u.comparar(
            _sin_val_min_max(reglas),
            _sin_val_min_max(gen["formato_condicional"]),
            f"{nombre}.barras",
        )
        == []
    )
    # Diferencia fijada (no oculta): xlsxwriter escribe val="0" en min/max.
    assert [c["valor"] for c in gen["formato_condicional"][0]["barra"]["cfvo"]] == ["0", "0"]
    assert [c["valor"] for c in reglas[0]["barra"]["cfvo"]] == [None, None]


# ---------------------------------------------------------------------------
# L6 (y filas 5–9 de la matriz): cada estilo de celda medido es reproducible
# ---------------------------------------------------------------------------


def _estilos_distintos() -> list[tuple[str, dict[str, Any]]]:
    vistos: dict[str, tuple[str, dict[str, Any]]] = {}
    for k, n, h in _hojas():
        for ref, c in h["celdas"].items():
            clave = repr(c["estilo"])
            vistos.setdefault(clave, (f"{k}/{n}!{ref}", c["estilo"]))
    return list(vistos.values())


ESTILOS = _estilos_distintos()


def test_l6_hay_fuentes_con_color_de_tema():
    con_tema = [
        (ref, e["fuente"]["nombre"])
        for ref, e in ESTILOS
        if "theme" in (e["fuente"].get("color") or {})
    ]
    assert any(nombre == "Arial" for _, nombre in con_tema)
    assert any(nombre == "Calibri" for _, nombre in con_tema)


@pytest.mark.parametrize(("ref", "estilo"), ESTILOS, ids=[r for r, _ in ESTILOS])
def test_l6_estilo_de_celda_reproducible(ref, estilo):
    gen = _libro(
        lambda wb, ws: ws.write_blank(0, 0, None, wb.add_format(u.formato_xlsxwriter(estilo)))
    )
    obtenido = gen["huella"]["hojas"][HOJA]["celdas"]["A1"]["estilo"]
    assert u.comparar(estilo, obtenido, ref) == []


def test_l6_color_de_tema_con_arial():
    gen = _libro(
        lambda wb, ws: ws.write(
            0,
            0,
            "Correo",
            wb.add_format({"font_name": "Arial", "font_size": 11, "font_color": Color.theme(1, 0)}),
        )
    )
    fuente = gen["huella"]["hojas"][HOJA]["celdas"]["A1"]["estilo"]["fuente"]
    assert fuente["color"] == {"theme": 1}
    assert fuente["nombre"] == "Arial"


# ---------------------------------------------------------------------------
# L7: columnas (ancho guardado exacto, ocultas, estilo de columna) y alturas de fila
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("clave", "nombre", "hoja"), _hojas(), ids=_ids(_hojas()))
def test_l7_columnas_y_filas(clave, nombre, hoja):
    gen = _libro(lambda wb, ws: _filas_y_columnas(ws, hoja))["huella"]["hojas"][HOJA]

    def sin_estilo(cols):
        return [{k: v for k, v in c.items() if k != "estilo"} for c in cols]

    assert (
        u.comparar(sin_estilo(hoja["columnas"]), sin_estilo(gen["columnas"]), f"{nombre}.columnas")
        == []
    )
    # El estilo de columna de la plantilla (style=18 en el informe) resuelve al estilo por
    # defecto; sin estilo de columna el resultado es el mismo.
    defecto = HUELLAS[clave]["libro"]["estilo_defecto"]
    for c in hoja["columnas"]:
        assert c["estilo"] in (None, defecto)
    altos = {n: (f["alto"], f["alto_propio"]) for n, f in hoja["filas"].items()}
    altos_gen = {n: (f["alto"], f["alto_propio"]) for n, f in gen["filas"].items()}
    assert u.comparar(altos, altos_gen, f"{nombre}.filas") == []
    assert gen["formato_hoja"]["alto_fila_defecto"] == hoja["formato_hoja"]["alto_fila_defecto"]


def test_l7_estilo_de_fila_con_custom_format():
    """La única fila con ``customFormat`` (categoría f6) se reproduce con ``set_row``."""
    hoja = HUELLAS["informe"]["hojas"][u.MARCA_CATEGORIA]
    fila = hoja["filas"]["6"]
    assert fila["estilo"] is not None

    def construir(wb, ws):
        ws.set_row_pixels(
            5, fila["alto"] / 0.75, wb.add_format(u.formato_xlsxwriter(fila["estilo"]))
        )

    gen = _libro(construir)["huella"]["hojas"][HOJA]["filas"]["6"]
    assert u.comparar(fila, gen, "f6") == []


def test_l7_set_row_redondea_y_set_row_pixels_no():
    """Hallazgo: ``set_row(44.1)`` guarda 44.25 (píxel entero); se usa ``set_row_pixels``."""

    def construir(wb, ws):
        ws.set_row(0, 44.1)
        ws.set_row_pixels(1, 44.1 / 0.75)

    filas = _libro(construir)["huella"]["hojas"][HOJA]["filas"]
    assert filas["1"]["alto"] == 44.25
    assert filas["2"]["alto"] == 44.1


# ---------------------------------------------------------------------------
# L8: texto alternativo, nombre y bloqueos de la imagen
# ---------------------------------------------------------------------------


def _imagen_sonda(img: dict[str, Any]) -> dict[str, Any]:
    def construir(wb, ws):
        ws.insert_image(
            1,
            0,
            "logo.png",
            {"image_data": _png(600, 240), "description": img["descr"], "object_position": 2},
        )

    (gen,) = _libro(construir)["huella"]["hojas"][HOJA]["imagenes"]
    return gen


@pytest.mark.parametrize(("clave", "nombre", "hoja"), _hojas(), ids=_ids(_hojas()))
def test_l8_texto_alternativo(clave, nombre, hoja):
    (img,) = hoja["imagenes"]
    gen = _imagen_sonda(img)
    assert img["descr"] == "Picture"
    assert gen["descr"] == img["descr"]
    assert gen["titulo"] == img["titulo"]
    assert gen["oculta"] is img["oculta"] is False
    assert gen["decorativa"] is img["decorativa"] is False


@pytest.mark.parametrize(("clave", "nombre", "hoja"), _hojas(), ids=_ids(_hojas()))
def test_l8_nombre_de_imagen_equivalente_aceptado(clave, nombre, hoja):
    """Equivalente aceptado (humano 2026-11-22, ``l8_nombre_imagen``).

    La plantilla llama a la imagen ``Image 1``; xlsxwriter escribe ``Picture N`` sin opción
    para cambiarlo. Se fija la diferencia exacta: si xlsxwriter cambia, se revisa la decisión.
    """
    (img,) = hoja["imagenes"]
    assert img["nombre"] == "Image 1"
    assert _imagen_sonda(img)["nombre"] == "Picture 1"
    assert "l8_nombre_imagen" in u.EQUIVALENTES_ACEPTADOS


@pytest.mark.parametrize(("clave", "nombre", "hoja"), _hojas(), ids=_ids(_hojas()))
def test_l8_bloqueo_de_proporcion_equivalente_aceptado(clave, nombre, hoja):
    """Equivalente aceptado (humano 2026-11-22, ``l8_bloqueo_proporcion``).

    La plantilla no bloquea la proporción; xlsxwriter siempre escribe
    ``picLocks noChangeAspect="1"``. El tamaño y la posición siguen exactos (L1).
    """
    (img,) = hoja["imagenes"]
    assert img["bloqueos"] == {}
    assert _imagen_sonda(img)["bloqueos"] == {"noChangeAspect": "1"}
    assert "l8_bloqueo_proporcion" in u.EQUIVALENTES_ACEPTADOS


# ---------------------------------------------------------------------------
# L9: hoja activa, celda activa y celda superior izquierda
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("clave", "nombre", "hoja"), _hojas(), ids=_ids(_hojas()))
def test_l9_vista_reproducible(clave, nombre, hoja):
    v = hoja["vista"]

    def construir(wb, ws):
        if v["panel"]:
            fila = int(v["panel"]["y_split"] or 0)
            ws.freeze_panes(fila, int(v["panel"]["x_split"] or 0))
        if v["celda_superior_izquierda"]:
            ws.set_top_left_cell(v["celda_superior_izquierda"])
        sel = v["seleccion"][0]
        ws.set_selection(sel["rango"])
        ws.hide_gridlines(2)
        if v["tab_seleccionada"]:
            ws.activate()
        else:
            wb.add_worksheet("Otra").activate()

    gen = _libro(construir)["huella"]["hojas"][HOJA]["vista"]
    assert u.comparar(v, gen, f"{nombre}.vista") == []


def test_l9_q11_primera_hoja_a1_sin_desplazamiento():
    """Lo que se usará (Q11): primera hoja activa, A1, sin ``topLeftCell``."""
    gen = _libro(lambda wb, ws: ws.write(0, 0, "x"))["huella"]
    assert gen["libro"]["hoja_activa"] == 0
    vista = gen["hojas"][HOJA]["vista"]
    assert vista["tab_seleccionada"] is True
    assert vista["celda_superior_izquierda"] is None
    assert vista["seleccion"] == []  # sin selección = A1


# ---------------------------------------------------------------------------
# L10: metadatos del paquete que xlsxwriter no controla (se fijan, no se ocultan)
# ---------------------------------------------------------------------------


def test_l10_metadatos_no_controlables():
    def construir(wb, ws):
        ws.insert_image(1, 0, "a.png", {"image_data": _png(600, 240)})
        otra = wb.add_worksheet("Otra")
        otra.insert_image(1, 0, "a.png", {"image_data": _png(600, 240)})

    gen = _libro(construir)
    libro = gen["huella"]["libro"]
    # calcId fijo de xlsxwriter (la plantilla trae 0) y fullCalcOnLoad siempre (Q13).
    assert libro["calculo"] == {"calcId": "124519", "fullCalcOnLoad": "1"}
    assert HUELLAS["activos"]["libro"]["calculo"] == {"calcId": "0"}
    assert HUELLAS["informe"]["libro"]["calculo"] == {"calcId": "0", "fullCalcOnLoad": "1"}
    # Medios: la plantilla del informe trae 6 copias; xlsxwriter deduplica (Q13).
    assert len(HUELLAS["informe"]["libro"]["medios"]) == 6
    assert len(libro["medios"]) == 1
    # Ancho base: la plantilla declara baseColWidth=10 y defaultColWidth=9.140625; xlsxwriter
    # no los escribe y el ancho por defecto efectivo es el mismo (8.43 caracteres = 64 px).
    hoja = gen["huella"]["hojas"][HOJA]
    assert hoja["formato_hoja"]["ancho_base"] is None
    assert hoja["formato_hoja"]["ancho_col_defecto"] is None
    for h in HUELLAS.values():
        for hj in h["hojas"].values():
            assert hj["formato_hoja"]["ancho_col_defecto"] == 9.140625
    # Inventario XML: lo que solo existe en la plantilla queda clasificado (no se pierde).
    inv = u.inventario_xml(gen["bytes"])
    assert "wsDr/twoCellAnchor@editAs" in inv["drawing"]
    assert "wsDr/oneCellAnchor" not in inv["drawing"]
    assert "worksheet/sheetData/row@dyDescent" not in inv["sheet"]
    assert "worksheet/sheetData/row@dyDescent" in HUELLAS["activos"]["inventario_xml"]["sheet"]


def test_l10_alfa_del_borde_no_controlable():
    """xlsxwriter escribe ``FF`` como alfa; el informe guarda ``00`` (Q13)."""
    bordes_informe = {
        lado["color"]["rgb"][:2]
        for _, _, h in _hojas()
        for c in h["celdas"].values()
        for lado in c["estilo"]["borde"].values()
        if isinstance(lado, dict) and lado.get("color", {}).get("rgb", "").endswith("9CA3AF")
    }
    assert bordes_informe == {"00", "FF"}
    gen = _libro(
        lambda wb, ws: ws.write_blank(
            0, 0, None, wb.add_format({"left": 1, "left_color": "#9CA3AF"})
        )
    )
    lado = gen["huella"]["hojas"][HOJA]["celdas"]["A1"]["estilo"]["borde"]["left"]
    assert lado["color"]["rgb"] == "FF9CA3AF"


# ---------------------------------------------------------------------------
# Fila 26: propiedades del documento (decisión del humano 2026-11-22)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("titulo", ["Activos", "Informe · Sesión de prueba"])
def test_fila_26_propiedades_del_documento(titulo):
    """Título del libro y ``creator`` neutro; nada del equipo ni de una persona."""
    gen = _libro(lambda wb, ws: wb.set_properties({"title": titulo, "author": "AssetControl"}))
    props = gen["huella"]["libro"]["propiedades"]
    core = props["core"]
    assert core["title"] == titulo
    assert core["creator"] == "AssetControl"
    # xlsxwriter 3.3.1 no permite omitir lastModifiedBy: lo escribe con el valor de author
    # (neutro). PENDIENTE de confirmación humana (ver ``PROPIEDADES_DOCUMENTO``).
    assert core["lastModifiedBy"] == "AssetControl"
    assert set(core) == {"title", "creator", "lastModifiedBy", "created", "modified"}
    # Company vacío (xlsxwriter escribe el elemento sin texto si no se da `company`).
    assert props["app"] == {
        "Application": "Microsoft Excel",
        "AppVersion": "12.0000",
        "Company": None,
    }
    # La plantilla trae el autor de la librería que la guardó: no se copia.
    for h in HUELLAS.values():
        assert h["libro"]["propiedades"]["core"].get("creator") == "openpyxl"


# ---------------------------------------------------------------------------
# Complemento: combinadas, área de impresión, filas a repetir, autofiltro y congelado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("clave", "nombre", "hoja"), _hojas(), ids=_ids(_hojas()))
def test_combinadas_impresion_filtro_reproducibles(clave, nombre, hoja):
    imp = hoja["impresion"]

    def rango(valor: str) -> str:
        return valor.split("!", 1)[1].replace("$", "")

    def construir(wb, ws):
        for m in hoja["combinadas"]:
            ws.merge_range(m, None)
        if imp["area"]:
            ws.print_area(rango(imp["area"]))
        if imp["titulos"]:
            fila = int(rango(imp["titulos"]).split(":")[0]) - 1
            ws.repeat_rows(fila)
        if hoja["autofiltro"]:
            ws.autofilter(hoja["autofiltro"])

    gen = _libro(construir)["huella"]
    g = gen["hojas"][HOJA]
    assert g["combinadas"] == hoja["combinadas"]
    assert g["autofiltro"] == hoja["autofiltro"]

    def sin_hoja(valor):
        return rango(valor) if valor else None

    for clave_imp in ("area", "titulos", "filtro"):
        assert sin_hoja(g["impresion"][clave_imp]) == sin_hoja(imp[clave_imp]), clave_imp
    filtro = [
        d for d in gen["libro"]["nombres_definidos"] if d["nombre"] == "_xlnm._FilterDatabase"
    ]
    esperado = [
        d
        for d in HUELLAS[clave]["libro"]["nombres_definidos"]
        if d["nombre"] == "_xlnm._FilterDatabase" and d["hoja"] == hoja["indice"]
    ]
    assert [d["oculto"] for d in filtro] == [d["oculto"] for d in esperado]
