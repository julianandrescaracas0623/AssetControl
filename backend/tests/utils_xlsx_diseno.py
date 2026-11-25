"""Huella de diseño de un ``.xlsx`` y comparación propiedad por propiedad (spec 019, T1).

Lee el paquete OOXML directamente (ZIP + XML) para no depender de lo que una librería
decida interpretar: libro, estilos, tema, hojas (vista, columnas, filas, celdas con su
estilo resuelto, combinaciones, formato condicional con su ``dxf``, barras de datos con su
``extLst``, validaciones, hipervínculos, protección, autofiltro, tablas, página,
impresión), dibujos e imágenes, y propiedades del documento.

Privacidad (R8): la huella que se versiona (``tests/plantillas/*.json``) NO guarda datos
reales. ``enmascarar`` deja literales solo los rótulos fijos de diseño (lista cerrada) y
sustituye lo demás por marcadores (``{empresa.nombre}``, ``{texto}``, ``{numero}``…).

Uso para regenerar la huella y la matriz (requiere las plantillas locales de ``informes/``,
que no se versionan)::

    cd backend && uv run python tests/utils_xlsx_diseno.py
"""

from __future__ import annotations

import io
import json
import posixpath
import re
import struct
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET  # noqa: S405 - solo archivos propios/generados

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_XDR = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_CP = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
NS_DC = "http://purl.org/dc/elements/1.1/"
NS_DCTERMS = "http://purl.org/dc/terms/"
NS_APP = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"

BACKEND = Path(__file__).resolve().parent.parent
RAIZ = BACKEND.parent
DIR_PLANTILLAS = RAIZ / "informes"
DIR_HUELLAS = Path(__file__).resolve().parent / "plantillas"
MATRIZ = RAIZ / "specs" / "019-diseno-informes-excel" / "matriz.md"

PLANTILLAS = {
    "activos": "Activos_20261122_diseno.xlsx",
    "informe": "Informe_boseto_limpio.xlsx",
}

EMU_POR_PX = 9525

# Formatos numéricos incorporados que aparecen (o pueden aparecer) en las plantillas.
FORMATOS_INCORPORADOS = {
    0: "General",
    1: "0",
    2: "0.00",
    3: "#,##0",
    4: "#,##0.00",
    9: "0%",
    10: "0.00%",
    14: "mm-dd-yy",
    22: "m/d/yy h:mm",
    49: "@",
}
FORMATOS_FECHA = {14, 15, 16, 17, 22}


# ---------------------------------------------------------------------------
# Lectura del paquete
# ---------------------------------------------------------------------------


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _hijo(el: ET.Element | None, nombre: str) -> ET.Element | None:
    if el is None:
        return None
    for h in el:
        if _local(h.tag) == nombre:
            return h
    return None


def _hijos(el: ET.Element | None, nombre: str) -> list[ET.Element]:
    if el is None:
        return []
    return [h for h in el if _local(h.tag) == nombre]


def _attr(el: ET.Element | None, nombre: str) -> str | None:
    if el is None:
        return None
    for k, v in el.attrib.items():
        if _local(k) == nombre:
            return v
    return None


def _num(v: str | None) -> float | int | None:
    if v is None:
        return None
    f = float(v)
    return int(f) if f.is_integer() else f


def _bool(v: str | None, defecto: bool = False) -> bool:
    if v is None:
        return defecto
    return v not in ("0", "false")


class Paquete:
    """Un ``.xlsx`` abierto: partes XML y relaciones resueltas."""

    def __init__(self, origen: bytes | str | Path) -> None:
        datos = origen if isinstance(origen, bytes) else Path(origen).read_bytes()
        self.zip = zipfile.ZipFile(io.BytesIO(datos))
        self.nombres = set(self.zip.namelist())

    def xml(self, parte: str) -> ET.Element | None:
        parte = parte.lstrip("/")
        if parte not in self.nombres:
            return None
        return ET.fromstring(self.zip.read(parte))  # noqa: S314 - paquete local

    def binario(self, parte: str) -> bytes:
        return self.zip.read(parte.lstrip("/"))

    def relaciones(self, parte: str) -> dict[str, tuple[str, str]]:
        """``{rId: (tipo, destino absoluto sin '/' inicial)}`` de una parte."""
        carpeta, archivo = posixpath.split(parte.lstrip("/"))
        rels = self.xml(posixpath.join(carpeta, "_rels", archivo + ".rels"))
        salida: dict[str, tuple[str, str]] = {}
        if rels is None:
            return salida
        for r in rels:
            destino = r.get("Target", "")
            if destino.startswith("/"):
                abs_ = destino.lstrip("/")
            else:
                abs_ = posixpath.normpath(posixpath.join(carpeta, destino))
            salida[r.get("Id", "")] = (r.get("Type", "").rsplit("/", 1)[-1], abs_)
        return salida


# ---------------------------------------------------------------------------
# Estilos
# ---------------------------------------------------------------------------


def _color(el: ET.Element | None) -> dict[str, Any] | None:
    if el is None:
        return None
    c: dict[str, Any] = {}
    for clave in ("rgb", "theme", "indexed", "tint", "auto"):
        v = el.get(clave)
        if v is not None:
            c[clave] = v.upper() if clave == "rgb" else _num(v)
    return c or None


def _fuente(el: ET.Element | None) -> dict[str, Any]:
    if el is None:
        return {}
    f: dict[str, Any] = {}
    for h in el:
        n = _local(h.tag)
        val = h.get("val")
        if n == "name":
            f["nombre"] = val
        elif n == "sz":
            f["tamano"] = _num(val)
        elif n == "b":
            f["negrita"] = _bool(val, True)
        elif n == "i":
            f["cursiva"] = _bool(val, True)
        elif n == "strike":
            f["tachado"] = _bool(val, True)
        elif n == "u":
            f["subrayado"] = val or "single"
        elif n == "color":
            f["color"] = _color(h)
        elif n == "family":
            f["familia"] = _num(val)
        elif n == "scheme":
            f["esquema"] = val
        elif n == "vertAlign":
            f["vert_align"] = val
        elif n in ("charset", "outline", "shadow", "condense", "extend"):
            f[n] = val
    for clave in ("negrita", "cursiva", "tachado"):
        f.setdefault(clave, False)
    return f


def _relleno(el: ET.Element | None, dxf: bool = False) -> dict[str, Any]:
    pf = _hijo(el, "patternFill")
    gf = _hijo(el, "gradientFill")
    if gf is not None:
        return {"degradado": ET.tostring(gf, encoding="unicode")}
    if pf is None:
        return {"patron": None}
    patron = pf.get("patternType")
    fg = _color(_hijo(pf, "fgColor"))
    bg = _color(_hijo(pf, "bgColor"))
    if dxf:
        # En un dxf, Excel pinta el relleno sólido con bgColor y un patternFill sin
        # patternType equivale a sólido (así lo escribe el propio Excel).
        if patron is None and (fg or bg):
            patron = "solid"
        return {"patron": patron, "color": bg or fg}
    return {"patron": patron or "none", "fg": fg, "bg": bg}


def _borde(el: ET.Element | None) -> dict[str, Any]:
    b: dict[str, Any] = {}
    for lado in ("left", "right", "top", "bottom", "diagonal"):
        h = _hijo(el, lado)
        estilo = h.get("style") if h is not None else None
        b[lado] = {"estilo": estilo, "color": _color(_hijo(h, "color"))} if estilo else None
    if el is not None:
        b["diagonal_arriba"] = _bool(el.get("diagonalUp"))
        b["diagonal_abajo"] = _bool(el.get("diagonalDown"))
    return b


def _alineacion(el: ET.Element | None) -> dict[str, Any]:
    return {
        "horizontal": el.get("horizontal", "general") if el is not None else "general",
        "vertical": el.get("vertical", "bottom") if el is not None else "bottom",
        "ajuste": _bool(_attr(el, "wrapText")),
        "sangria": _num(_attr(el, "indent")) or 0,
        "rotacion": _num(_attr(el, "textRotation")) or 0,
        "reducir": _bool(_attr(el, "shrinkToFit")),
    }


def _proteccion(el: ET.Element | None) -> dict[str, Any]:
    return {
        "bloqueada": _bool(_attr(el, "locked"), True),
        "oculta": _bool(_attr(el, "hidden")),
    }


class Estilos:
    def __init__(self, raiz: ET.Element | None) -> None:
        self.formatos = dict(FORMATOS_INCORPORADOS)
        for nf in _hijos(_hijo(raiz, "numFmts"), "numFmt"):
            self.formatos[int(nf.get("numFmtId", "0"))] = nf.get("formatCode", "")
        self.fuentes = [_fuente(f) for f in _hijos(_hijo(raiz, "fonts"), "font")]
        self.rellenos = [_relleno(f) for f in _hijos(_hijo(raiz, "fills"), "fill")]
        self.bordes = [_borde(b) for b in _hijos(_hijo(raiz, "borders"), "border")]
        self.xfs = _hijos(_hijo(raiz, "cellXfs"), "xf")
        self.dxfs = [self._dxf(d) for d in _hijos(_hijo(raiz, "dxfs"), "dxf")]
        ts = _hijo(raiz, "tableStyles")
        self.estilos_tabla = (
            {
                "defecto_tabla": ts.get("defaultTableStyle"),
                "defecto_dinamica": ts.get("defaultPivotStyle"),
                "propios": len(_hijos(ts, "tableStyle")),
            }
            if ts is not None
            else None
        )

    def formato(self, num_fmt_id: int) -> dict[str, Any]:
        codigo = self.formatos.get(num_fmt_id, f"<incorporado {num_fmt_id}>")
        salida: dict[str, Any] = {"codigo": codigo}
        if num_fmt_id in FORMATOS_INCORPORADOS or num_fmt_id < 164:
            salida["incorporado"] = num_fmt_id
        return salida

    def _dxf(self, el: ET.Element) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if (f := _hijo(el, "font")) is not None:
            d["fuente"] = _fuente(f)
        if (f := _hijo(el, "fill")) is not None:
            d["relleno"] = _relleno(f, dxf=True)
        if (b := _hijo(el, "border")) is not None:
            d["borde"] = _borde(b)
        if (n := _hijo(el, "numFmt")) is not None:
            d["formato"] = n.get("formatCode")
        if (a := _hijo(el, "alignment")) is not None:
            d["alineacion"] = _alineacion(a)
        return d

    def resolver(self, indice: int) -> dict[str, Any]:
        xf = self.xfs[indice] if indice < len(self.xfs) else self.xfs[0]
        return {
            "fuente": self.fuentes[int(xf.get("fontId", "0"))],
            "relleno": self.rellenos[int(xf.get("fillId", "0"))],
            "borde": self.bordes[int(xf.get("borderId", "0"))],
            "alineacion": _alineacion(_hijo(xf, "alignment")),
            "formato": self.formato(int(xf.get("numFmtId", "0"))),
            "proteccion": _proteccion(_hijo(xf, "protection")),
        }


# ---------------------------------------------------------------------------
# Tema
# ---------------------------------------------------------------------------


def _tema(raiz: ET.Element | None) -> dict[str, Any] | None:
    if raiz is None:
        return None
    elems = _hijo(raiz, "themeElements")
    colores: dict[str, str | None] = {}
    esquema = _hijo(elems, "clrScheme")
    for c in esquema if esquema is not None else []:
        v = _hijo(c, "srgbClr")
        s = _hijo(c, "sysClr")
        colores[_local(c.tag)] = (
            v.get("val") if v is not None else (s.get("lastClr") if s is not None else None)
        )
    fuentes = _hijo(elems, "fontScheme")
    mayor = _hijo(_hijo(fuentes, "majorFont"), "latin")
    menor = _hijo(_hijo(fuentes, "minorFont"), "latin")
    return {
        "nombre": raiz.get("name"),
        "colores": colores,
        "fuente_mayor": mayor.get("typeface") if mayor is not None else None,
        "fuente_menor": menor.get("typeface") if menor is not None else None,
        "esquema_fuentes": fuentes.get("name") if fuentes is not None else None,
    }


def tema_normalizado(origen: bytes | str | Path) -> str:
    """El ``theme1.xml`` completo sin la declaración XML (para comparar byte a byte)."""
    p = Paquete(origen)
    t = p.binario("xl/theme/theme1.xml").decode("utf-8")
    return re.sub(r"^<\?xml[^>]*\?>\s*", "", t).strip()


def sha256_tema(origen: bytes | str | Path) -> str:
    import hashlib

    return hashlib.sha256(tema_normalizado(origen).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Hojas
# ---------------------------------------------------------------------------


def col_letra(n: int) -> str:
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def ref_a_rc(ref: str) -> tuple[int, int]:
    m = re.fullmatch(r"\$?([A-Z]+)\$?(\d+)", ref)
    if not m:
        raise ValueError(ref)
    col = 0
    for ch in m.group(1):
        col = col * 26 + ord(ch) - 64
    return int(m.group(2)), col


def _texto_celda(c: ET.Element, compartidas: list[str]) -> tuple[str, Any]:
    t = c.get("t", "n")
    v = _hijo(c, "v")
    if t == "inlineStr":
        is_ = _hijo(c, "is")
        partes = (
            [x.text or "" for x in is_.iter() if _local(x.tag) == "t"] if is_ is not None else []
        )
        return "s", "".join(partes)
    if t == "s":
        return "s", compartidas[int(v.text or "0")] if v is not None else ""
    if t in ("str", "e", "b"):
        return t, v.text if v is not None else None
    if v is None or v.text is None:
        return "vacia", None
    return "n", _num(v.text)


def _hoja(p: Paquete, parte: str, estilos: Estilos, compartidas: list[str]) -> dict[str, Any]:
    raiz = p.xml(parte)
    assert raiz is not None, parte
    rels = p.relaciones(parte)
    h: dict[str, Any] = {}

    sp = _hijo(raiz, "sheetPr")
    tab = _hijo(sp, "tabColor")
    h["pestana"] = _color(tab)
    op = _hijo(sp, "outlinePr")
    h["esquema"] = {
        "resumen_abajo": _bool(_attr(op, "summaryBelow"), True),
        "resumen_derecha": _bool(_attr(op, "summaryRight"), True),
    }
    psp = _hijo(sp, "pageSetUpPr")
    ajuste_pagina = _bool(_attr(psp, "fitToPage"))

    sv = _hijo(_hijo(raiz, "sheetViews"), "sheetView")
    pane = _hijo(sv, "pane")
    sel = _hijos(sv, "selection")
    h["vista"] = {
        "cuadricula": _bool(_attr(sv, "showGridLines"), True),
        "encabezados": _bool(_attr(sv, "showRowColHeaders"), True),
        "ceros": _bool(_attr(sv, "showZeros"), True),
        "derecha_a_izquierda": _bool(_attr(sv, "rightToLeft")),
        "zoom": _num(_attr(sv, "zoomScale")),
        "tipo": _attr(sv, "view"),
        "tab_seleccionada": _bool(_attr(sv, "tabSelected")),
        "celda_superior_izquierda": _attr(sv, "topLeftCell"),
        "panel": (
            {
                "x_split": _num(pane.get("xSplit")),
                "y_split": _num(pane.get("ySplit")),
                "celda_superior_izquierda": pane.get("topLeftCell"),
                "panel_activo": pane.get("activePane"),
                "estado": pane.get("state"),
            }
            if pane is not None
            else None
        ),
        "seleccion": [
            {"panel": s.get("pane"), "celda_activa": s.get("activeCell"), "rango": s.get("sqref")}
            for s in sel
        ],
    }

    sfp = _hijo(raiz, "sheetFormatPr")
    base = _num(_attr(sfp, "baseColWidth"))
    h["formato_hoja"] = {
        "alto_fila_defecto": _num(_attr(sfp, "defaultRowHeight")),
        "ancho_col_defecto": _num(_attr(sfp, "defaultColWidth")),
        "ancho_base": base,
        "filas_ocultas_defecto": _bool(_attr(sfp, "zeroHeight")),
        "alto_propio_defecto": _bool(_attr(sfp, "customHeight")),
    }

    h["columnas"] = [
        {
            "min": int(c.get("min", "0")),
            "max": int(c.get("max", "0")),
            "ancho": _num(c.get("width")),
            "ancho_propio": _bool(c.get("customWidth")),
            "oculta": _bool(c.get("hidden")),
            "nivel": int(c.get("outlineLevel", "0")),
            "contraida": _bool(c.get("collapsed")),
            "estilo": estilos.resolver(int(c.get("style"))) if c.get("style") else None,
        }
        for c in _hijos(_hijo(raiz, "cols"), "col")
    ]

    filas: dict[str, Any] = {}
    celdas: dict[str, Any] = {}
    for r in _hijos(_hijo(raiz, "sheetData"), "row"):
        num = r.get("r", "")
        formato_propio = _bool(r.get("customFormat"))
        filas[num] = {
            "alto": _num(r.get("ht")),
            "alto_propio": _bool(r.get("customHeight")),
            "oculta": _bool(r.get("hidden")),
            "nivel": int(r.get("outlineLevel", "0")),
            "contraida": _bool(r.get("collapsed")),
            # Sin customFormat="1" Excel ignora el atributo s de la fila.
            "estilo": estilos.resolver(int(r.get("s", "0"))) if formato_propio else None,
        }
        for c in _hijos(r, "c"):
            tipo, valor = _texto_celda(c, compartidas)
            s = int(c.get("s", "0"))
            estilo = estilos.resolver(s)
            if tipo == "n" and estilo["formato"].get("incorporado") in FORMATOS_FECHA:
                tipo = "fecha"
            celdas[c.get("r", "")] = {"tipo": tipo, "valor": valor, "estilo": estilo}
    h["filas"] = filas
    h["celdas"] = celdas
    h["combinadas"] = sorted(
        m.get("ref", "") for m in _hijos(_hijo(raiz, "mergeCells"), "mergeCell")
    )

    cfs = []
    for cf in _hijos(raiz, "conditionalFormatting"):
        for regla in _hijos(cf, "cfRule"):
            item: dict[str, Any] = {
                "rango": cf.get("sqref"),
                "tipo": regla.get("type"),
                "prioridad": _num(regla.get("priority")),
                "detener": _bool(regla.get("stopIfTrue")),
                "operador": regla.get("operator"),
                "formulas": [f.text for f in _hijos(regla, "formula")],
                "dxf": (
                    estilos.dxfs[int(regla.get("dxfId", "0"))]
                    if regla.get("dxfId") is not None
                    else None
                ),
            }
            db = _hijo(regla, "dataBar")
            if db is not None:
                item["barra"] = {
                    "cfvo": [
                        {"tipo": v.get("type"), "valor": v.get("val")} for v in _hijos(db, "cfvo")
                    ],
                    "color": _color(_hijo(db, "color")),
                    "mostrar_valor": _bool(db.get("showValue"), True),
                    "largo_min": _num(db.get("minLength")),
                    "largo_max": _num(db.get("maxLength")),
                    "ext": [e.get("uri") for e in _hijos(_hijo(regla, "extLst"), "ext")],
                }
            cfs.append(item)
    h["formato_condicional"] = cfs
    h["formato_condicional_ext"] = [e.get("uri") for e in _hijos(_hijo(raiz, "extLst"), "ext")]

    h["validaciones"] = [
        {"rango": d.get("sqref"), "tipo": d.get("type")}
        for d in _hijos(_hijo(raiz, "dataValidations"), "dataValidation")
    ]
    h["hipervinculos"] = [
        {"ref": x.get("ref")} for x in _hijos(_hijo(raiz, "hyperlinks"), "hyperlink")
    ]
    prot = _hijo(raiz, "sheetProtection")
    h["proteccion"] = dict(prot.attrib) if prot is not None else None
    af = _hijo(raiz, "autoFilter")
    h["autofiltro"] = af.get("ref") if af is not None else None
    tablas = []
    for tp in _hijos(_hijo(raiz, "tableParts"), "tablePart"):
        rid = _attr(tp, "id") or ""
        t = p.xml(rels[rid][1])
        if t is not None:
            info = _hijo(t, "tableStyleInfo")
            tablas.append(
                {
                    "nombre": t.get("displayName"),
                    "rango": t.get("ref"),
                    "estilo": dict(info.attrib) if info is not None else None,
                    "autofiltro": _hijo(t, "autoFilter") is not None,
                }
            )
    h["tablas"] = tablas

    pm = _hijo(raiz, "pageMargins")
    ps = _hijo(raiz, "pageSetup")
    po = _hijo(raiz, "printOptions")
    hf = _hijo(raiz, "headerFooter")
    h["pagina"] = {
        "margenes": {
            k: _num(pm.get(k)) for k in ("left", "right", "top", "bottom", "header", "footer")
        }
        if pm is not None
        else None,
        "orientacion": _attr(ps, "orientation"),
        "papel": _num(_attr(ps, "paperSize")),
        "escala": _num(_attr(ps, "scale")),
        "ajustar_a_pagina": ajuste_pagina,
        "ajuste_ancho": _num(_attr(ps, "fitToWidth")) if _attr(ps, "fitToWidth") else 1,
        "ajuste_alto": _num(_attr(ps, "fitToHeight")) if _attr(ps, "fitToHeight") else 1,
        "primera_pagina": _num(_attr(ps, "firstPageNumber")),
        "orden": _attr(ps, "pageOrder"),
        "blanco_y_negro": _bool(_attr(ps, "blackAndWhite")),
        "cuadricula_impresa": _bool(_attr(po, "gridLines")),
        "encabezados_impresos": _bool(_attr(po, "headings")),
        "centrado_horizontal": _bool(_attr(po, "horizontalCentered")),
        "centrado_vertical": _bool(_attr(po, "verticalCentered")),
        "encabezado_pie": {_local(x.tag): x.text for x in (hf if hf is not None else []) if x.text},
        "encabezado_pie_distinto_primera": _bool(_attr(hf, "differentFirst")),
        "encabezado_pie_pares_impares": _bool(_attr(hf, "differentOddEven")),
        "saltos_fila": len(_hijos(_hijo(raiz, "rowBreaks"), "brk")),
        "saltos_columna": len(_hijos(_hijo(raiz, "colBreaks"), "brk")),
    }

    objetos = []
    dibujo = _hijo(raiz, "drawing")
    if dibujo is not None:
        dparte = rels[_attr(dibujo, "id") or ""][1]
        objetos = _dibujo(p, dparte)
    # Imágenes (el logo) y formas (su marco, 2026-11-24) por separado.
    h["imagenes"] = [o for o in objetos if o.get("objeto") != "forma"]
    h["formas"] = [o for o in objetos if o.get("objeto") == "forma"]
    return h


def _png(datos: bytes) -> dict[str, Any]:
    if datos[:8] != b"\x89PNG\r\n\x1a\n":
        return {"formato": "otro"}
    i = 8
    info: dict[str, Any] = {"formato": "png", "phys": None}
    while i < len(datos):
        largo = struct.unpack(">I", datos[i : i + 4])[0]
        tipo = datos[i + 4 : i + 8]
        cuerpo = datos[i + 8 : i + 8 + largo]
        if tipo == b"IHDR":
            info["ancho"], info["alto"] = struct.unpack(">II", cuerpo[:8])
        elif tipo == b"pHYs":
            x, y, u = struct.unpack(">IIB", cuerpo[:9])
            info["phys"] = {"x": x, "y": y, "unidad": u}
        i += 12 + largo
    return info


def _forma(ancla: ET.Element, pos: Any) -> dict[str, Any]:
    """Una forma (``xdr:sp``) del dibujo: el marco del logo (decisión 2026-11-24)."""
    sp = _hijo(ancla, "sp")
    sppr = _hijo(sp, "spPr")
    xfrm = _hijo(sppr, "xfrm")
    off, ext = _hijo(xfrm, "off"), _hijo(xfrm, "ext")
    ln = _hijo(sppr, "ln")
    color = _hijo(_hijo(ln, "solidFill"), "srgbClr")
    nv = _hijo(_hijo(sp, "nvSpPr"), "cNvPr")
    return {
        "edit_as": ancla.get("editAs"),
        "desde": pos(_hijo(ancla, "from")),
        "hasta": pos(_hijo(ancla, "to")),
        "xfrm": {
            "x": int(off.get("x", 0)) if off is not None else None,
            "y": int(off.get("y", 0)) if off is not None else None,
            "cx": int(ext.get("cx", 0)) if ext is not None else None,
            "cy": int(ext.get("cy", 0)) if ext is not None else None,
        },
        "geometria": _attr(_hijo(sppr, "prstGeom"), "prst"),
        "sin_relleno": _hijo(sppr, "noFill") is not None,
        "linea": {
            "ancho": int(ln.get("w", 0)) if ln is not None else None,
            "color": _attr(color, "val"),
        },
        "texto": "".join(t.text or "" for t in sp.iter() if _local(t.tag) == "t")
        if sp is not None
        else "",
        "decorativa": nv is not None and b"decorative" in ET.tostring(nv),
    }


def _dibujo(p: Paquete, parte: str) -> list[dict[str, Any]]:
    raiz = p.xml(parte)
    rels = p.relaciones(parte)
    salida = []
    for ancla in raiz if raiz is not None else []:
        tipo = _local(ancla.tag)
        if tipo not in ("oneCellAnchor", "twoCellAnchor", "absoluteAnchor"):
            continue

        def pos(el: ET.Element | None) -> dict[str, int] | None:
            if el is None:
                return None
            return {
                "col": int(_hijo(el, "col").text or 0),  # type: ignore[union-attr]
                "col_off": int(_hijo(el, "colOff").text or 0),  # type: ignore[union-attr]
                "fila": int(_hijo(el, "row").text or 0),  # type: ignore[union-attr]
                "fila_off": int(_hijo(el, "rowOff").text or 0),  # type: ignore[union-attr]
            }

        pic = _hijo(ancla, "pic")
        if pic is None:
            salida.append({"ancla": tipo, "objeto": "forma", **_forma(ancla, pos)})
            continue

        ext = _hijo(ancla, "ext")
        nv = _hijo(_hijo(pic, "nvPicPr"), "cNvPr")
        cpic = _hijo(_hijo(pic, "nvPicPr"), "cNvPicPr")
        locks = _hijo(cpic, "picLocks")
        blip_fill = _hijo(pic, "blipFill")
        blip = _hijo(blip_fill, "blip")
        sppr = _hijo(pic, "spPr")
        xfrm = _hijo(sppr, "xfrm")
        off = _hijo(xfrm, "off")
        xext = _hijo(xfrm, "ext")
        ln = _hijo(sppr, "ln")
        rid = _attr(blip, "embed") or ""
        media = rels.get(rid, ("", ""))[1]
        salida.append(
            {
                "ancla": tipo,
                "edit_as": ancla.get("editAs"),
                "desde": pos(_hijo(ancla, "from")),
                "hasta": pos(_hijo(ancla, "to")),
                "ext": {"cx": int(ext.get("cx", 0)), "cy": int(ext.get("cy", 0))}
                if ext is not None
                else None,
                "xfrm": {
                    "x": int(off.get("x", 0)) if off is not None else None,
                    "y": int(off.get("y", 0)) if off is not None else None,
                    "cx": int(xext.get("cx", 0)) if xext is not None else None,
                    "cy": int(xext.get("cy", 0)) if xext is not None else None,
                },
                "nombre": _attr(nv, "name"),
                "descr": _attr(nv, "descr"),
                "titulo": _attr(nv, "title"),
                "oculta": _bool(_attr(nv, "hidden")),
                "decorativa": nv is not None and b"decorative" in ET.tostring(nv),
                "bloqueos": dict(locks.attrib) if locks is not None else {},
                "cstate": _attr(blip, "cstate"),
                "estirar": _hijo(blip_fill, "stretch") is not None,
                "geometria": _attr(_hijo(sppr, "prstGeom"), "prst"),
                "linea": ([_local(x.tag) for x in ln] if ln is not None else None),
                "medio": media,
                "imagen": _png(p.binario(media)) if media else None,
            }
        )
    return salida


# ---------------------------------------------------------------------------
# Libro completo
# ---------------------------------------------------------------------------


def extraer(origen: bytes | str | Path) -> dict[str, Any]:
    """Huella cruda (con los valores reales de las celdas) de un ``.xlsx``."""
    p = Paquete(origen)
    wb = p.xml("xl/workbook.xml")
    assert wb is not None
    wrels = p.relaciones("xl/workbook.xml")
    estilos_parte = next((d for t, d in wrels.values() if t == "styles"), "xl/styles.xml")
    estilos = Estilos(p.xml(estilos_parte))
    tema_parte = next((d for t, d in wrels.values() if t == "theme"), "xl/theme/theme1.xml")
    compartidas: list[str] = []
    ss_parte = next((d for t, d in wrels.values() if t == "sharedStrings"), None)
    if ss_parte:
        ss = p.xml(ss_parte)
        for si in ss if ss is not None else []:
            compartidas.append("".join(x.text or "" for x in si.iter() if _local(x.tag) == "t"))

    bv = _hijo(_hijo(wb, "bookViews"), "workbookView")
    hojas_xml = _hijos(_hijo(wb, "sheets"), "sheet")
    nombres = [s.get("name", "") for s in hojas_xml]
    calc = _hijo(wb, "calcPr")
    libro: dict[str, Any] = {
        "hojas": nombres,
        "estados": [s.get("state", "visible") for s in hojas_xml],
        "hoja_activa": int(_attr(bv, "activeTab") or 0),
        "primera_hoja_visible": int(_attr(bv, "firstSheet") or 0),
        "pestanas_visibles": _bool(_attr(bv, "showSheetTabs"), True),
        "nombres_definidos": [
            {
                "nombre": d.get("name"),
                "hoja": int(d.get("localSheetId")) if d.get("localSheetId") else None,
                "oculto": _bool(d.get("hidden")),
                "valor": d.text,
            }
            for d in _hijos(_hijo(wb, "definedNames"), "definedName")
        ],
        "calculo": dict(calc.attrib) if calc is not None else None,
        "proteccion": dict(p_.attrib)
        if (p_ := _hijo(wb, "workbookProtection")) is not None
        else None,
        "fecha_1904": _bool(_attr(_hijo(wb, "workbookPr"), "date1904")),
        "tema": _tema(p.xml(tema_parte)),
        "fuente_defecto": estilos.fuentes[0] if estilos.fuentes else None,
        "estilo_defecto": estilos.resolver(0) if estilos.xfs else None,
        "estilos_tabla": estilos.estilos_tabla,
        "dxfs": estilos.dxfs,
        "medios": sorted(n for n in p.nombres if n.startswith("xl/media/")),
    }
    core = p.xml("docProps/core.xml")
    app = p.xml("docProps/app.xml")
    libro["propiedades"] = {
        "core": {_local(x.tag): x.text for x in core} if core is not None else {},
        "app": {
            _local(x.tag): x.text
            for x in (app if app is not None else [])
            if _local(x.tag) in ("Application", "Company", "Manager", "AppVersion")
        },
    }

    hojas: dict[str, Any] = {}
    for i, s in enumerate(hojas_xml):
        rid = _attr(s, "id") or ""
        hoja = _hoja(p, wrels[rid][1], estilos, compartidas)
        hoja["indice"] = i
        hoja["estado"] = s.get("state", "visible")
        locales = [d for d in libro["nombres_definidos"] if d["hoja"] == i]
        hoja["impresion"] = {
            "area": next((d["valor"] for d in locales if d["nombre"] == "_xlnm.Print_Area"), None),
            "titulos": next(
                (d["valor"] for d in locales if d["nombre"] == "_xlnm.Print_Titles"), None
            ),
            "filtro": next(
                (d["valor"] for d in locales if d["nombre"] == "_xlnm._FilterDatabase"), None
            ),
        }
        hojas[s.get("name", "")] = hoja
    return {"libro": libro, "hojas": hojas}


def inventario_xml(origen: bytes | str | Path) -> dict[str, list[str]]:
    """Rutas de elementos y atributos (sin espacio de nombres) por tipo de parte."""
    p = Paquete(origen)
    tipos = {
        "workbook": re.compile(r"xl/workbook\.xml$"),
        "styles": re.compile(r"xl/styles\.xml$"),
        "sheet": re.compile(r"xl/worksheets/sheet\d+\.xml$"),
        "drawing": re.compile(r"xl/drawings/drawing\d+\.xml$"),
        "table": re.compile(r"xl/tables/table\d+\.xml$"),
    }
    salida: dict[str, set[str]] = {k: set() for k in tipos}

    def recorrer(el: ET.Element, ruta: str, destino: set[str]) -> None:
        r = f"{ruta}/{_local(el.tag)}" if ruta else _local(el.tag)
        destino.add(r)
        for k in el.attrib:
            destino.add(f"{r}@{_local(k)}")
        for h in el:
            recorrer(h, r, destino)

    for nombre in sorted(p.nombres):
        for tipo, patron in tipos.items():
            if patron.search(nombre):
                raiz = p.xml(nombre)
                if raiz is not None:
                    recorrer(raiz, "", salida[tipo])
    return {k: sorted(v) for k, v in salida.items() if v}


# ---------------------------------------------------------------------------
# Enmascarado (sin datos reales)
# ---------------------------------------------------------------------------

# Rótulos fijos de diseño que sí se versionan (lista cerrada). Cualquier otro texto se
# sustituye por un marcador.
ROTULOS_FIJOS = frozenset(
    {
        "Inventario de activos",
        "Informe de activos",
        "Correo",
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
        "Todos los activos del cierre",
        "Todos los activos",
        "Total",
        "Activo",
        "Ubicación esperada",
        "Encontrado en",
        "Estado físico",
        "Resultado",
        "Precio (COP)",
        "Nota al cierre",
        "Por ubicación",
        "Por categoría",
        "No encontrados (lista congelada al cierre)",
        "Ubicación (al cierre)",
        "Categoría (al cierre)",
        "Valor encontrado",
        "Unid. encontradas",
        "Valor no encontrado",
        "Unid. no encontradas",
        "Valor registrado",
        "Unid. registradas",
        "% encontrado",
        "Encontrado",
        "No encontrado",
        "Total registrado",
        "de las unidades registradas",
    }
)

# Frases fijas con cifras: se versionan con las cifras ya sustituidas por marcadores.
FRASES_CON_MARCADORES = frozenset(
    {
        # Nota de las listas (opción C, 2026-11-24): la segunda línea solo si hay
        # discrepancias (``exportar._nota_de_lista``).
        "{n} activos · {n} encontrados ({pct}) por {cop} · {n} no encontrados por {cop}\n"
        "{n} discrepancias en amarillo: activos encontrados en una ubicación distinta de la "
        "registrada.",
        "{n} activos no encontrados por {cop}.",
        "{n} activo",
        "{n} activos no encontrados",
        "{n} unidad",
        "{n} unidades",
    }
)

HOJAS_FIJAS = frozenset(
    {"Activos", "Todos los activos", "Por ubicación", "No encontrados", "Por categoría", "Resumen"}
)
MARCA_CATEGORIA = "{categoria}"

# Filas de datos de ejemplo por hoja (siempre con marcadores, aunque el texto parezca fijo).
FILAS_DATOS = {
    "Activos": {8},
    "Todos los activos": {10},
    "Por ubicación": {8},
    "No encontrados": set(),
    MARCA_CATEGORIA: {10},
    "Por categoría": {8},
    "Resumen": {13},
}


def _sustituir_cifras(texto: str) -> str:
    t = re.sub(r"\$ ?[\d.]+,\d{2}", "{cop}", texto)
    t = re.sub(r"\d+(?:,\d+)? ?%", "{pct}", t)
    return re.sub(r"\b\d+\b", "{n}", t)


def marcar_texto(texto: str, hoja: str, fila: int, col: int) -> str:
    """Rótulo fijo literal o marcador; nunca devuelve un dato real."""
    if fila in (3, 4, 5):
        if texto == "Correo":
            return texto
        if texto.startswith("NIT "):
            return "NIT {empresa.nit}"
        if texto.startswith("Tel. "):
            return "Tel. {empresa.telefono}"
        if texto.startswith("Corte "):
            return "Corte {fecha}"
        if texto.startswith("Exportado "):
            return "Exportado {fecha}"
        if "@" in texto:
            return "{empresa.correo}"
        if fila == 3 and col == 3:
            return "{empresa.nombre}"
        if fila == 5 and col == 3:
            return "{empresa.direccion}"
        return "{texto}"
    if fila in FILAS_DATOS.get(hoja, set()):
        return "{texto}"
    if texto in ROTULOS_FIJOS:
        return texto
    if texto.startswith("Categoría: "):
        return "Categoría: {categoria}"
    cifras = _sustituir_cifras(texto)
    if cifras in FRASES_CON_MARCADORES:
        return cifras
    return "{texto}"


def enmascarar(huella: dict[str, Any]) -> dict[str, Any]:
    """Copia de la huella sin datos reales (marcadores en lugar de valores)."""
    h = json.loads(json.dumps(huella, default=str))
    libro = h["libro"]
    mapa = {n: (n if n in HOJAS_FIJAS else MARCA_CATEGORIA) for n in libro["hojas"]}
    libro["hojas"] = [mapa[n] for n in libro["hojas"]]
    for d in libro["nombres_definidos"]:
        for real, marca in mapa.items():
            if real != marca and d["valor"]:
                d["valor"] = d["valor"].replace(real, marca)
    core = libro["propiedades"]["core"]
    for k in list(core):
        if core[k] and k not in ("creator",):
            core[k] = "{" + k + "}"
    hojas = {}
    for real, hoja in h["hojas"].items():
        nombre = mapa[real]
        for ref, celda in hoja["celdas"].items():
            fila, col = ref_a_rc(ref)
            if celda["tipo"] == "s":
                celda["valor"] = marcar_texto(celda["valor"] or "", nombre, fila, col)
            elif celda["tipo"] == "n":
                celda["valor"] = "{numero}"
            elif celda["tipo"] == "fecha":
                celda["valor"] = "{fecha}"
            elif celda["tipo"] != "vacia":
                celda["valor"] = "{valor}"
        for clave in ("area", "titulos", "filtro"):
            v = hoja["impresion"][clave]
            if v and real != nombre:
                hoja["impresion"][clave] = v.replace(real, nombre)
        hojas[nombre] = hoja
    h["hojas"] = hojas
    return h


# ---------------------------------------------------------------------------
# Comparación
# ---------------------------------------------------------------------------

# Propiedades sin efecto visible ni funcional que no se comparan (Q13, humano 2026-11-22).
EQUIVALENTES_NO_IDENTICOS = {
    "alfa_color": "Canal alfa del color ARGB (`00`/`FF`): Excel no lo usa en celdas (Q13).",
    "calcPr": "`calcId` y `fullCalcOnLoad` de `calcPr` (Q13: calcId).",
    "ancho_base": "`baseColWidth`/`defaultColWidth` del paquete; se compara el ancho por "
    "defecto efectivo (Q13: baseColWidth).",
    "medios": "Un medio por imagen vs. un medio deduplicado (Q13: medios duplicados).",
    "encabezado_vacio": "Elementos de encabezado/pie vacíos (Q13).",
    "ancla": '`oneCellAnchor` vs. `twoCellAnchor editAs="oneCell"` con las mismas '
    "dimensiones visibles (Q13; L1 confirma que xlsxwriter no escribe oneCellAnchor).",
}


# Diferencias de paquete halladas en T1 que NO están en la lista de Q13 y que xlsxwriter no
# controla. ACEPTADAS como equivalentes por decisión del humano 2026-11-22 (revisadas grupo
# por grupo). Ninguna se oculta: las sondas de ``test_xlsx_sondas.py`` las fijan una por una
# (si xlsxwriter cambia lo que escribe, la prueba falla y la decisión se revisa).
EQUIVALENTES_ACEPTADOS = {
    "l8_nombre_imagen": 'L8: la imagen se llama `Picture N` (xlsxwriter fija `name="Picture '
    'N"` sin opción); la plantilla dice `Image 1`. Mismo tamaño y posición exactos.',
    "l8_bloqueo_proporcion": "L8: xlsxwriter siempre escribe `<a:picLocks "
    'noChangeAspect="1"/>` (casilla «Bloquear relación de aspecto» marcada); la plantilla no '
    "la trae. Mismo tamaño y posición exactos.",
    "cfvo_val_min_max": 'xlsxwriter escribe `val="0"` en los `cfvo` min/max de las barras '
    "de datos (la plantilla no lo trae); para min/max Excel ignora `val` (L5).",
    "dxf_patternType": "xlsxwriter escribe el relleno del dxf sin `patternType` y solo con "
    "`bgColor`; la plantilla trae `solid` con fg = bg. Excel escribe el dxf igual que "
    "xlsxwriter y lo pinta sólido con `bgColor` (L4).",
    "fila_s_sin_customFormat": 'La plantilla del informe pone `s="18"` en cada fila sin '
    "`customFormat`; Excel ignora ese atributo (L10).",
    "pistas_fila": "`spans` y `thickBot` de fila; `x14ac:dyDescent` ya entra en Q13 (L10).",
    "cstate_y_ln": '`cstate="print"` del blip y `<a:ln><a:prstDash/></a:ln>` sin relleno '
    "(no dibuja línea) en las imágenes (L10).",
    "cadenas": "`inlineStr` (informe) / `sharedStrings` (activos) vs. `sharedStrings` "
    "(xlsxwriter): mismo texto (L10).",
    "fullCalcOnLoad_activos": "Activos no trae `fullCalcOnLoad`; xlsxwriter siempre lo "
    "escribe en modo automático (solo `set_calc_mode('manual')` lo quita, y agrega "
    "`calcMode=manual`). Es parte de `calcPr` (Q13 nombra `calcId`) (L10).",
    "ventana_y_aplicacion": "Geometría de `workbookView`, `fileVersion`, `AlternateContent` "
    "(ruta local del equipo que guardó), `revisionPtr`, `extLst` del libro y de estilos, "
    "`colors` indexados por defecto, banderas `apply*`/`pivotButton`/`quotePrefix`, índices "
    "de estilo y de `numFmt` (L10).",
}

# Fila 26 (propiedades del documento), decisión del humano 2026-11-22: no se copian las de
# la plantilla (`creator` = `openpyxl`, `lastModifiedBy` y fechas del equipo que guardó).
PROPIEDADES_DOCUMENTO = {
    "title": "Según el libro: «Activos» en el Excel de activos; en el informe, el título "
    "que ya escribe el generador («Informe · {sesion}»).",
    "creator": "Neutro: `AssetControl`.",
    "lastModifiedBy": "Sin dato de equipo ni personal. xlsxwriter 3.3.1 SIEMPRE escribe "
    "`<cp:lastModifiedBy>` con el mismo valor que `author` (o vacío si no hay autor): no se "
    "puede omitir el elemento ni darle otro valor que el de `creator`. Decisión del "
    "coordinator 2026-11-22: `creator` = `lastModifiedBy` = `AssetControl` (única opción "
    "coherente), CONFIRMADA salvo que el humano pida ambos vacíos.",
    "otros": "Sin asunto, palabras clave ni administrador; `Company` vacío (xlsxwriter "
    "escribe el elemento sin texto); `created`/`modified` "
    "con la hora de generación (xlsxwriter siempre los escribe); `Application` = "
    "`Microsoft Excel` (fijo en xlsxwriter, no es dato del equipo).",
}


# Decisiones de T4 (hojas de lista del informe): qué se reproduce y con qué criterio donde la
# plantilla no basta. Cada una tiene su prueba en ``test_exportar_documento.py`` o
# ``test_exportar_api.py``.
DECISIONES_T4 = {
    "no_encontrados_datos": "Decisión del humano 2026-11-22: la plantilla no trae fila de "
    "datos con estilo en «No encontrados» (filas 10–11 solo con alto 21.95). Sus filas de "
    "datos llevan los mismos estilos de datos que las otras hojas de lista: texto `datos` "
    "(Todos A10), COP `datos_cop` (Todos J10) y celda vacía `datos_vacia` (Todos E10), sin "
    "filas alternas, alto 21.95. Formato condicional de fila completa: la regla de la spec "
    "(B11, fila 23a) compara «Ubicación esperada» con «Encontrado en»; esta hoja no tiene "
    "«Encontrado en» (todo lo listado no se encontró) y la plantilla no trae regla: sin "
    "formato condicional. Prueba: "
    "`test_no_encontrados_replica_la_huella_con_los_estilos_de_datos_de_las_listas`.",
    "celda_vacia_informe": "Celda de datos sin valor en las listas del informe (marca, "
    "serial, «Encontrado en», «Estado físico», «Nota al cierre»): `datos_vacia`, el estilo "
    "que la plantilla da a su única celda de datos vacía (Todos E10, categoría D10: Calibri "
    "11, bordes finos, centro/abajo), distinto del de texto (A10). Las listas del informe no "
    "tienen columnas de fecha y el precio nunca es nulo (`precio_al_contar` congelado): no "
    "hay fecha ni COP vacíos. Prueba: "
    "`test_celdas_vacias_de_cada_columna_llevan_el_estilo_vacia_de_la_plantilla`.",
    "columnas_ocultas_no_encontrados": "«No encontrados»: G–K ocultas con los anchos de la "
    "plantilla (20, 16, 16, 18, 13; L7). Prueba: "
    "`test_no_encontrados_oculta_las_columnas_g_a_k_como_la_plantilla`.",
    "formato_condicional_listas": "Todos `A10:J499` y cada categoría `A10:I499` con la "
    "fórmula y el dxf medidos; con más filas, hasta la última escrita (req. 5). Prueba: "
    "`test_con_mas_filas_el_formato_condicional_y_el_area_se_extienden`.",
    "dxf_deduplicado": "Decisión del humano 2026-11-22: ACEPTADO como equivalente. "
    "xlsxwriter deduplica los `dxf` idénticos: el libro guarda uno solo "
    "para las reglas de Todos y de cada categoría (la plantilla guarda uno por regla, los "
    "tres iguales). Se compara el `dxf` resuelto de cada regla, como el estilo resuelto de "
    "cada celda (índices de estilo: `ventana_y_aplicacion`); cada regla resuelve al mismo "
    "estilo.",
    "estados_sin_relleno": "Decisión del humano 2026-11-22: «En reparación» y «Dañado» "
    "(«Estado físico» en las listas y «Nota al cierre» en «No encontrados») van sin relleno "
    "ámbar fijo, como la plantilla: llevan el estilo de datos de su columna y no se agrega "
    "regla de formato condicional extra. El único ámbar es el de la regla de discrepancia "
    "(fila 23a).",
    "tabla_y_filtros": "Q8: «Todos los activos» lleva la tabla «Activos» (A9:J…) sin nombre "
    "de estilo (`tableStyleInfo` sin `name`: no altera fuente, relleno ni bordes); la hoja "
    "por categoría y «No encontrados» (si tiene filas), autofiltro desde la fila 9. Sobrantes "
    "aceptados por Q8: `tableParts`, la parte `table`, `autoFilter`.",
    "encabezado_impresion_listas": "Vacío, como la plantilla (B5, Q7); pie de la plantilla.",
    "bloque_informe": "Empresa CONGELADA al cierre (`cierre.informe`) y «Corte dd/mm/aaaa» "
    "con la fecha de corte de la sesión (B17).",
    "logo_informe": "Logo congelado ilegible o almacén con error (`OSError`, `ClientError`, "
    "`BotoCoreError`): sin imagen y `200` (req. 8), con un WARNING con el tipo del error y, en "
    "S3, su código; sin clave, ruta, endpoint, bucket ni datos. Vale también para el PDF. "
    "`ClaveInvalida` (clave del logo congelado inválida) NO se degrada: es un error de "
    "integridad y se propaga. Prueba: "
    "`test_informe_logo_con_clave_invalida_no_se_traga_el_error`.",
}


# Decisiones de T5 (desglose, Resumen y libro completo del informe). Cada una tiene su prueba
# en ``test_exportar_documento.py`` o ``test_exportar_api.py``.
DECISIONES_T5 = {
    "orden_libro": "Q6 (humano 2026-11-22): Todos los activos, Por ubicación, No encontrados, "
    "una hoja por categoría, Por categoría, Resumen. Sin detalle (sesión anterior a la 013): "
    "Por ubicación, No encontrados, Por categoría, Resumen. Prueba: "
    "`test_el_libro_sigue_el_orden_de_la_plantilla_y_abre_en_la_primera_hoja`.",
    "hoja_activa": "Q11 (humano 2026-11-22): el libro abre en la primera hoja (`activeTab` "
    "ausente = 0; solo ella con `tabSelected`), en A1 y sin `topLeftCell`; la hoja activa "
    "(«No encontrados»), las celdas activas y el desplazamiento del Resumen (A7) de la "
    "plantilla son residuo de edición y no se generan.",
    "desglose_cifras": "Criterio 8: «Por ubicación» y «Por categoría» escriben una fila por "
    "etiqueta del desglose congelado de `cierre.informe` y la fila Total con sus `totales` "
    "(nunca la suma de las filas), desde el `Decimal` exacto (`precio_al_contar`). Prueba: "
    "`test_desglose_escribe_el_decimal_congelado_sin_sumar_ni_pasar_por_float`.",
    "desglose_disposicion": "Título en A6 (I6 y J6 con el estilo por defecto), cabecera en la "
    "fila 7 (I7 y J7 vacías con su estilo), datos desde la 8 con el estilo de la fila 8 de la "
    "plantilla y Total justo debajo con el de la fila 9 (fondo `DBEAFE`, I y J vacías con su "
    "estilo). Barras de datos `BFDBFE` en F y H de las filas de datos, sin extensión 2010, "
    "extendidas hasta la última fila (req. 5); sin filas, sin barras.",
    "resumen_tarjetas": "Filas 6–8 de la plantilla: rótulos en A6, C6, E6 (Arial 9 N "
    "`1D4ED8`) y G6 (Arial 9 `6B7280`, sin negrita, como la plantilla); valores congelados "
    "en A7, C7, E7 (COP) y G7 (`0.0 %`); unidades y «de las unidades registradas» en la fila "
    "8; las demás celdas de A–J con el estilo por defecto centrado de la plantilla.",
    "resumen_contexto": "Q7 (humano 2026-11-22) y plan, fila 25g: desde la fila 10, «Sesión» "
    "y su nombre; «Cerró» y quién, «Cerrada» y cuándo; «Moneda» COP; «Estado» «Informe "
    "congelado»; la `NOTA`; `SIN_DETALLE` y `EMPRESA_VIGENTE` solo si aplican. Rótulo en A y "
    "valor en B (D para «Cerrada»). Estilo: el de la nota de lista de la plantilla (Arial 9 "
    "`6B7280`, centro vertical, ajuste de texto), sin combinar y con la altura por defecto "
    "(plan, filas 11b y 12). «Cerrada» va como texto (hora de Colombia, igual que el PDF): "
    "la plantilla no tiene un formato de fecha y hora. Prueba: "
    "`test_resumen_replica_la_huella_con_tarjetas_y_filas_de_contexto`. Decisión del humano "
    "2026-11-22: ACEPTADAS (estilo `nota`, sin combinar, altura por defecto; «Cerrada» y "
    "«Corte» como texto con hora de Colombia); se revisan visualmente en Excel real en T6.",
    "contexto_solo_resumen": "Decisión del humano 2026-11-22: Sesión, Cerró, Cerrada, Moneda, "
    "Estado y los avisos `EMPRESA_VIGENTE` van solo en el Resumen; no se repiten en cada "
    "hoja (las demás hojas llevan solo el bloque de la plantilla).",
    "resumen_lista_omitida": "Q7 (humano 2026-11-22): la lista «Todos los activos» duplicada "
    "del Resumen (filas 9–13, combinada A10:J10 y regla A13:J13) no se genera; la fila 9 queda "
    "vacía.",
    "impresion_hojas_cortas": "Q12 (humano 2026-11-22): Por ubicación, Por categoría y "
    "Resumen a 1 × 1 página (como la plantilla); área de impresión hasta la última fila.",
    "encabezado_impresion_resumen": "El Resumen pierde el encabezado de impresión con la "
    "empresa y la sesión (B5, Q7): ninguna hoja del libro tiene encabezado; el pie es el de "
    "la plantilla.",
    "propiedades_informe": "Fila 26: título «Informe · {sesion}» y `creator` = "
    "`lastModifiedBy` = `AssetControl`; se quita el comentario «Informe congelado» que "
    "escribía el generador (sin asunto, palabras clave ni comentarios).",
    "corte_congelado": "«Corte dd/mm/aaaa» (E3) en todas las hojas, Resumen incluido: la "
    "fecha de corte de la sesión de `cierre.informe` (B17), no la de hoy ni la del cierre. "
    "Prueba: `test_corte_es_la_fecha_de_corte_congelada_no_la_de_hoy`.",
    "decimal_16_cifras": "xlsxwriter escribe los números con `{:.16G}`: un `Decimal` de más "
    "de 16 cifras significativas se rechaza (`ValueError`) en vez de redondearse en "
    "silencio; `NUMERIC(14,2)` nunca llega a ese tope. Prueba: "
    "`test_un_decimal_de_mas_de_16_cifras_se_rechaza_en_vez_de_redondearse`.",
    "ancho_base_comparado": "`defaultColWidth`/`baseColWidth` se comparan como el equivalente "
    "`ancho_base` (Q13) en todas las hojas: la plantilla declara 9.140625 y 10; el generado no "
    "los escribe (mismo ancho por defecto efectivo).",
    "valores_por_omision": "Cobertura en las dos direcciones (fila 27): la plantilla escribe "
    'atributos con su valor por omisión que xlsxwriter no escribe: `<b val="1"/>` y '
    '`<i val="1"/>` (xlsxwriter: `<b/>` y `<i/>`; `val` vale `true` por omisión en '
    'ECMA-376), `fitToWidth="1"`, `sheet@state="visible"`, `outlinePr` por defecto y '
    "`col@style` que resuelve al estilo por defecto. La propiedad se compara resuelta "
    "(negrita, cursiva del dxf, ajuste de ancho, visibilidad, agrupación, estilo de columna) "
    "y coincide. Decisión del humano 2026-11-22: ACEPTADOS como equivalentes.",
    "regla_discrepancia_vacia": "Cambio semántico menor (T4, documentado en T5): la regla de "
    'fila completa sigue la fórmula de la plantilla `AND($F10<>"",$G10<>"",$F10<>$G10)`; con '
    "«Ubicación esperada» vacía la fila ya no se marca (antes el generador marcaba la celda "
    "«Encontrado en» si difería). La ubicación esperada sale del cierre y no suele faltar.",
}


def normalizar_color(c: Any) -> Any:
    """Quita el canal alfa de un color ARGB (equivalente no idéntico, Q13)."""
    if isinstance(c, dict) and isinstance(c.get("rgb"), str) and len(c["rgb"]) == 8:
        c = dict(c)
        c["rgb"] = c["rgb"][2:]
    return c


def _normalizar(v: Any) -> Any:
    if isinstance(v, dict):
        if "rgb" in v and set(v) <= {"rgb", "theme", "indexed", "tint", "auto"}:
            return normalizar_color(v)
        return {k: _normalizar(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_normalizar(x) for x in v]
    return v


def comparar(esperado: Any, obtenido: Any, ruta: str = "") -> list[str]:
    """Diferencias «ruta: esperado …, obtenido …» entre dos huellas (o fragmentos).

    Los colores se comparan sin canal alfa (Q13). Las claves que solo están en
    ``obtenido`` también se informan, para no aceptar propiedades de más.
    """
    e, o = _normalizar(esperado), _normalizar(obtenido)
    difs: list[str] = []
    _comparar(e, o, ruta, difs)
    return difs


def _comparar(e: Any, o: Any, ruta: str, difs: list[str]) -> None:
    if isinstance(e, dict) and isinstance(o, dict):
        for k in sorted(set(e) | set(o), key=str):
            sub = f"{ruta}.{k}" if ruta else str(k)
            if k not in o:
                difs.append(f"{sub}: esperado {e[k]!r}, obtenido <ausente>")
            elif k not in e:
                difs.append(f"{sub}: esperado <ausente>, obtenido {o[k]!r}")
            else:
                _comparar(e[k], o[k], sub, difs)
        return
    if isinstance(e, list) and isinstance(o, list):
        if len(e) != len(o):
            difs.append(f"{ruta}: esperado {len(e)} elementos {e!r}, obtenido {len(o)} {o!r}")
            return
        for i, (a, b) in enumerate(zip(e, o, strict=True)):
            _comparar(a, b, f"{ruta}[{i}]", difs)
        return
    if isinstance(e, float) or isinstance(o, float):
        if isinstance(e, int | float) and isinstance(o, int | float) and abs(e - o) < 1e-9:
            return
    if e != o:
        difs.append(f"{ruta}: esperado {e!r}, obtenido {o!r}")


ESTILOS_BORDE = {
    "thin": 1,
    "medium": 2,
    "dashed": 3,
    "dotted": 4,
    "thick": 5,
    "double": 6,
    "hair": 7,
}
ALINEACION_H = {
    "general": None,
    "left": "left",
    "center": "center",
    "right": "right",
    "fill": "fill",
    "justify": "justify",
    "centerContinuous": "center_across",
    "distributed": "distributed",
}
ALINEACION_V = {
    "bottom": None,
    "top": "top",
    "center": "vcenter",
    "justify": "vjustify",
    "distributed": "vdistributed",
}


def _color_xlsxwriter(c: dict[str, Any] | None) -> Any:
    from xlsxwriter.color import Color

    if not c:
        return None
    if "theme" in c:
        return Color.theme(int(c["theme"]), 0)
    return "#" + c["rgb"][-6:]


def formato_xlsxwriter(estilo: dict[str, Any]) -> dict[str, Any]:
    """Propiedades de ``Workbook.add_format`` que reproducen un estilo resuelto.

    Solo para las sondas de T1: demuestra que cada estilo medido es reproducible. El
    módulo de estilo de la aplicación (T2) define sus propias constantes.
    """
    f = estilo["fuente"]
    props: dict[str, Any] = {
        "font_name": f.get("nombre"),
        "font_size": f.get("tamano"),
        "bold": f.get("negrita", False),
        "italic": f.get("cursiva", False),
        "font_strikeout": f.get("tachado", False),
        "font_family": f.get("familia", 0),
    }
    if f.get("esquema"):
        props["font_scheme"] = f["esquema"]
    if f.get("color"):
        props["font_color"] = _color_xlsxwriter(f["color"])
    r = estilo["relleno"]
    if r.get("patron") == "solid":
        props["pattern"] = 1
        if r.get("fg"):
            props["fg_color"] = _color_xlsxwriter(r["fg"])
        if r.get("bg"):
            props["bg_color"] = _color_xlsxwriter(r["bg"])
    elif r.get("patron") not in (None, "none"):
        raise ValueError(f"patrón sin traducir: {r}")
    for lado in ("left", "right", "top", "bottom"):
        b = estilo["borde"].get(lado)
        if b:
            props[lado] = ESTILOS_BORDE[b["estilo"]]
            if b.get("color"):
                props[f"{lado}_color"] = _color_xlsxwriter(b["color"])
    a = estilo["alineacion"]
    if ALINEACION_H[a["horizontal"]]:
        props["align"] = ALINEACION_H[a["horizontal"]]
    if ALINEACION_V[a["vertical"]]:
        props["valign"] = ALINEACION_V[a["vertical"]]
    if a["ajuste"]:
        props["text_wrap"] = True
    if a["sangria"]:
        props["indent"] = a["sangria"]
    if a["rotacion"]:
        props["rotation"] = a["rotacion"]
    if a["reducir"]:
        props["shrink"] = True
    fmt = estilo["formato"]
    if "incorporado" in fmt:
        if fmt["incorporado"]:
            props["num_format"] = fmt["incorporado"]
    else:
        props["num_format"] = fmt["codigo"]
    if not estilo["proteccion"]["bloqueada"]:
        props["locked"] = False
    if estilo["proteccion"]["oculta"]:
        props["hidden"] = True
    return props


def dxf_xlsxwriter(dxf: dict[str, Any]) -> dict[str, Any]:
    """Propiedades de formato para un ``dxf`` (formato condicional)."""
    props: dict[str, Any] = {}
    f = dxf.get("fuente", {})
    if f.get("cursiva"):
        props["italic"] = True
    if f.get("negrita"):
        props["bold"] = True
    if f.get("color"):
        props["font_color"] = _color_xlsxwriter(f["color"])
    r = dxf.get("relleno")
    if r and r.get("patron") == "solid":
        props["pattern"] = 1
        props["bg_color"] = _color_xlsxwriter(r["color"])
    return props


def cargar_huella(nombre: str) -> dict[str, Any]:
    return json.loads((DIR_HUELLAS / f"{nombre}.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Cobertura: cada elemento/atributo XML de la plantilla → fila de la matriz o decisión
# ---------------------------------------------------------------------------

# (expresión regular sobre «parte:ruta», destino). Se evalúan en orden; la primera gana.
COBERTURA: list[tuple[str, str]] = [
    (r"\w+:\w+@Ignorable$", "EQ L10: espacios de nombres ignorables (mc:Ignorable)"),
    # --- workbook.xml
    (r"workbook:workbook$", "estructura"),
    (r"workbook:workbook/sheets(/sheet)?$", "1 nombres y orden de hojas"),
    (r"workbook:workbook/sheets/sheet@(name|sheetId|id)$", "1 nombres y orden de hojas"),
    (r"workbook:workbook/sheets/sheet@state$", "3 visibilidad"),
    (r"workbook:workbook/bookViews/workbookView@activeTab$", "3 hoja activa (Q11)"),
    (
        r"workbook:workbook/bookViews/workbookView@(firstSheet|showSheetTabs|visibility"
        r"|minimized|showHorizontalScroll|showVerticalScroll|autoFilterDateGrouping)$",
        "3 visibilidad (valores por defecto)",
    ),
    (
        r"workbook:workbook/bookViews/workbookView@(xWindow|yWindow|windowWidth|windowHeight"
        r"|tabRatio|uid)$",
        "EQ L10: geometría de ventana del equipo que guardó (Q11/Q13)",
    ),
    (r"workbook:workbook/bookViews(/workbookView)?$", "3 visibilidad"),
    (r"workbook:workbook/definedNames.*", "18 área de impresión y filas a repetir; 24 filtro"),
    (r"workbook:workbook/calcPr.*", "EQ Q13: calcPr (calcId, fullCalcOnLoad)"),
    (r"workbook:workbook/workbookPr.*", "EQ L10: workbookPr sin atributos de efecto"),
    (
        r"workbook:workbook/(fileVersion|AlternateContent|revisionPtr|extLst).*",
        "EQ L10: metadatos de la aplicación que guardó (Q13)",
    ),
    # --- styles.xml
    (r"styles:styleSheet$", "estructura"),
    (r"styles:styleSheet/numFmts.*", "9 formatos numéricos"),
    (r"styles:styleSheet/fonts@knownFonts$", "EQ L10: x14ac:knownFonts (Q13)"),
    (r"styles:styleSheet/fonts.*", "5 fuentes"),
    (r"styles:styleSheet/fills.*", "6 rellenos"),
    (r"styles:styleSheet/borders.*", "7 bordes"),
    (r"styles:styleSheet/cellStyleXfs.*", "4 fuente y estilo por defecto"),
    (r"styles:styleSheet/cellXfs/xf/alignment.*", "8 alineación"),
    (r"styles:styleSheet/cellXfs/xf/protection.*", "24 protección"),
    (
        r"styles:styleSheet/cellXfs/xf@(pivotButton|quotePrefix|applyAlignment|applyFont"
        r"|applyFill|applyBorder|applyNumberFormat|applyProtection|xfId)$",
        "EQ L10: banderas apply*/pivotButton/quotePrefix por defecto; el estilo se compara "
        "resuelto (Q13)",
    ),
    (r"styles:styleSheet/cellXfs.*", "5-9 estilo de celda (resuelto)"),
    (r"styles:styleSheet/cellStyles.*", "4 fuente y estilo por defecto"),
    (r"styles:styleSheet/dxfs.*", "23a formato condicional (dxf)"),
    (r"styles:styleSheet/tableStyles.*", "24 tablas (Q8)"),
    (
        r"styles:styleSheet/colors.*",
        "EQ L10: paleta indexada por defecto (no se usa en ningún color de la plantilla)",
    ),
    (
        r"styles:styleSheet/extLst.*",
        "EQ L10: estilos de segmentación/escala de tiempo por defecto (Q13)",
    ),
    # --- worksheets
    (r"sheet:worksheet$", "estructura"),
    (r"sheet:worksheet@uid$", "EQ Q13: uid"),
    (r"sheet:worksheet/sheetPr$", "estructura"),
    (r"sheet:worksheet/sheetPr/tabColor.*", "2 color de pestaña"),
    (r"sheet:worksheet/sheetPr/outlinePr.*", "21 agrupación (valores por defecto)"),
    (r"sheet:worksheet/sheetPr/pageSetUpPr.*", "15 ajuste a página"),
    (r"sheet:worksheet/dimension.*", "EQ L10: dimension (la calcula el escritor)"),
    (r"sheet:worksheet/sheetViews(/sheetView)?$", "estructura"),
    (r"sheet:worksheet/sheetViews/sheetView@showGridLines$", "20 cuadrícula"),
    (
        r"sheet:worksheet/sheetViews/sheetView@(tabSelected|topLeftCell)$",
        "3 hoja activa y desplazamiento (Q11)",
    ),
    (r"sheet:worksheet/sheetViews/sheetView@workbookViewId$", "estructura"),
    (r"sheet:worksheet/sheetViews/sheetView/pane.*", "14 congelados"),
    (r"sheet:worksheet/sheetViews/sheetView/selection.*", "3 selección (Q11)"),
    (r"sheet:worksheet/sheetFormatPr@defaultRowHeight$", "11 alturas (por defecto)"),
    (
        r"sheet:worksheet/sheetFormatPr@(baseColWidth|defaultColWidth)$",
        "EQ Q13: baseColWidth (10 alturas/anchos por defecto efectivos)",
    ),
    (r"sheet:worksheet/sheetFormatPr@dyDescent$", "EQ Q13: dyDescent"),
    (r"sheet:worksheet/sheetFormatPr$", "estructura"),
    (r"sheet:worksheet/cols(/col)?$", "10 anchos"),
    (r"sheet:worksheet/cols/col@(min|max|width|customWidth)$", "10 anchos"),
    (r"sheet:worksheet/cols/col@hidden$", "21 ocultas"),
    (r"sheet:worksheet/cols/col@style$", "L7 estilo de columna (resuelto)"),
    (r"sheet:worksheet/sheetData$", "estructura"),
    (r"sheet:worksheet/sheetData/row@(r|ht|customHeight)$", "11 alturas"),
    (
        r"sheet:worksheet/sheetData/row@(s|customFormat)$",
        "11 estilo de fila (solo cuenta con customFormat=1)",
    ),
    (
        r"sheet:worksheet/sheetData/row@(spans|dyDescent|thickBot)$",
        "EQ L10: pistas de renderizado de fila (Q13)",
    ),
    (r"sheet:worksheet/sheetData/row$", "11 alturas"),
    (r"sheet:worksheet/sheetData/row/c@r$", "detalle por celda (matriz.md)"),
    (r"sheet:worksheet/sheetData/row/c@s$", "5-9 estilo de celda (resuelto)"),
    (
        r"sheet:worksheet/sheetData/row/c@t$",
        "25 textos (tipo); inlineStr vs. sharedStrings = EQ L10",
    ),
    (r"sheet:worksheet/sheetData/row/c(/v|/is(/t)?)?$", "25 textos y valores"),
    (r"sheet:worksheet/mergeCells.*", "12 combinadas"),
    (r"sheet:worksheet/conditionalFormatting.*", "23 formato condicional"),
    (r"sheet:worksheet/dataValidations.*", "22 validaciones"),
    (r"sheet:worksheet/hyperlinks.*", "24 hipervínculos"),
    (r"sheet:worksheet/sheetProtection.*", "24 protección"),
    (r"sheet:worksheet/autoFilter@uid$", "EQ Q13: uid"),
    (r"sheet:worksheet/autoFilter.*", "24 autofiltro"),
    (r"sheet:worksheet/tableParts.*", "24 tablas (Q8)"),
    (r"sheet:worksheet/pageMargins.*", "16 márgenes"),
    (r"sheet:worksheet/printOptions.*", "20 cuadrícula al imprimir; 15 centrado"),
    (r"sheet:worksheet/pageSetup.*", "15 orientación, papel y ajuste"),
    (
        r"sheet:worksheet/headerFooter/(oddHeader|evenHeader|evenFooter|firstHeader"
        r"|firstFooter)$",
        "17 encabezado/pie (vacíos: EQ Q13)",
    ),
    (r"sheet:worksheet/headerFooter.*", "17 encabezado y pie"),
    (r"sheet:worksheet/(rowBreaks|colBreaks).*", "15 saltos de página"),
    (r"sheet:worksheet/drawing.*", "13 imágenes"),
    # --- drawings
    (r"drawing:wsDr$", "estructura"),
    (r"drawing:wsDr/(oneCellAnchor|twoCellAnchor)$", "13 imágenes (ancla, Q13/L1)"),
    (r"drawing:wsDr/(oneCellAnchor|twoCellAnchor)@editAs$", "13 imágenes (ancla, Q13/L1)"),
    (r"drawing:wsDr/\w+/(from|to)(/\w+)?$", "13 imágenes (posición)"),
    (r"drawing:wsDr/\w+/ext.*", "13 imágenes (tamaño)"),
    (
        r"drawing:wsDr/\w+/pic/nvPicPr/cNvPr@(name|descr|id)$",
        "13 imágenes; L8 texto alternativo; nombre `Picture N` = EQ aceptado (humano)",
    ),
    (r"drawing:wsDr/\w+/pic/nvPicPr/cNvPr/extLst.*", "EQ Q13: creationId (uid)"),
    (r"drawing:wsDr/\w+/pic/nvPicPr.*", "13 imágenes; L8 bloqueos (noChangeAspect = EQ aceptado)"),
    (
        r"drawing:wsDr/\w+/pic/blipFill/blip@cstate$",
        "EQ L10: cstate (estado de compresión, sin efecto)",
    ),
    (r"drawing:wsDr/\w+/pic/blipFill.*", "13 imágenes (medio, estirado)"),
    (r"drawing:wsDr/\w+/pic/spPr/ln.*", "EQ L10: a:ln sin relleno ni estilo (no dibuja línea)"),
    (r"drawing:wsDr/\w+/pic/spPr.*", "13 imágenes (posición absoluta, geometría)"),
    (r"drawing:wsDr/\w+/pic$", "13 imágenes"),
    (r"drawing:wsDr/\w+/clientData$", "13 imágenes (por defecto)"),
]


def destino_cobertura(ruta: str) -> str | None:
    for patron, destino in COBERTURA:
        if re.fullmatch(patron, ruta):
            return destino
    return None


# ---------------------------------------------------------------------------
# Generación de la huella versionada y de matriz.md
# ---------------------------------------------------------------------------


def huella_de_plantilla(ruta: Path) -> dict[str, Any]:
    h = enmascarar(extraer(ruta))
    h["plantilla"] = ruta.name
    h["libro"]["tema_sha256"] = sha256_tema(ruta)
    h["inventario_xml"] = inventario_xml(ruta)
    return h


def _resumen_estilo(e: dict[str, Any]) -> str:
    f = e["fuente"]
    color = (f.get("color") or {}).get("rgb") or (
        f"tema {f['color']['theme']}" if f.get("color") and "theme" in f["color"] else "-"
    )
    partes = [
        f"{f.get('nombre')} {f.get('tamano')}{' N' if f.get('negrita') else ''}"
        f"{' K' if f.get('cursiva') else ''} {color}"
    ]
    r = e["relleno"]
    if r.get("patron") not in (None, "none"):
        partes.append(f"relleno {r['patron']} {(r.get('fg') or {}).get('rgb')}")
    lados = [
        f"{lado[0].upper()}:{b['estilo']} {(b.get('color') or {}).get('rgb')}"
        for lado, b in e["borde"].items()
        if isinstance(b, dict)
    ]
    if lados:
        partes.append("borde " + ", ".join(lados))
    a = e["alineacion"]
    partes.append(f"alin {a['horizontal']}/{a['vertical']}{' ajuste' if a['ajuste'] else ''}")
    if e["formato"]["codigo"] != "General":
        partes.append(f"formato `{e['formato']['codigo']}`")
    return "; ".join(partes).replace("|", "\\|")


DECISIONES_ENCABEZADO = {
    "encabezado_junto_al_logo": "Decisión del humano 2026-11-24: el bloque de las dos "
    "exportaciones (activos e informe) pone el título junto al logo y debajo la línea "
    "«Informe · empresa · exportado|corte fecha» (C3) con una línea fina gris. En la fila 4, "
    "los rótulos «Empresa», «Contacto» y «Dirección»; en la fila 5, bajo cada uno, sus datos "
    "(nombre y NIT; correo y teléfono; dirección) en celdas combinadas con ajuste de texto, "
    "hasta el fin de la banda. Un dato ausente se omite y un grupo sin datos va sin rótulo. "
    "Se quitan los rótulos «Exportado» y «Correo» de la plantilla. Alturas: fila 4 = 16 y "
    "fila 5 = 30. El logo conserva el tamaño de su caja (`CajaLogo`, Q10) y, desde el "
    "2026-11-25, va centrado en altura entre la banda y la línea azul, con un borde gris "
    "medio (`9CA3AF`, 1 pt) de esquinas redondeadas (radio 30 px) a 3 px de la imagen, que "
    "también lleva las esquinas redondeadas. Logo y borde van en una sola imagen PNG, "
    "compuesta una vez con la caja de «Activos» y escalada a la caja de cada hoja (el libro "
    "guarda una sola imagen); si Pillow no puede procesar el logo, va el original sin borde. "
    "Lo cubren `utils_logo.comprobar_logo_con_borde` y sus pruebas. Ninguna hoja "
    "inmoviliza paneles: Excel dibuja una línea en el corte que no se puede ocultar (al "
    "imprimir, la cabecera se sigue repitiendo). Las huellas "
    "`activos.json` e `informe.json` llevan las filas 1–5 de este diseño, con sus marcadores.",
    "nota_de_lista": "Decisión del humano 2026-11-24 (opción C): la nota de «Todos los "
    "activos» y de cada categoría da las cifras en la primera línea («N activos · n "
    "encontrados (pct) por $ … · n no encontrados por $ …», con singular y plural) y, solo si "
    "la hoja tiene discrepancias, una segunda con cuántas son: «N discrepancias en amarillo: "
    "activos encontrados en una ubicación distinta de la registrada». Discrepancia = "
    "ubicación esperada y «Encontrado en» llenas y distintas, la misma regla que pinta la fila "
    "de ámbar. Se quita la frase de la tabla dinámica.",
    "resumen_opcion_c": "Decisión del humano 2026-11-24 (opción C): el Resumen deja la "
    "plantilla. Título junto al logo, sin combinar. Tarjetas 2 × 2 con fondo `F3F4F6` en "
    "A:B y C:D (filas 7–12, 24 pt): Encontrado, No encontrado, Total registrado y % "
    "encontrado, con rótulo, cifra (número COP o %) y unidades; bajo el %, una barra de "
    "datos clásica de 0 a 1 en C12 (solo la barra, azul claro de los desgloses; la de Excel "
    "2010 escribe fórmulas `xm:f`). Bordes blancos gruesos separan las tarjetas. Panel "
    "«Sesión» en F7:J12 con borde fino: Nombre, Cerró, Cerrada, Moneda y Estado. La nota y "
    "los avisos van a todo el ancho desde la fila 14, en un recuadro gris. Anchos propios "
    "del Resumen para que las cifras quepan (A 24, B 26, C:D 25, E 3, F 22, G 18, H:I 12, "
    "J 14).",
}


def generar_matriz(huellas: dict[str, dict[str, Any]]) -> str:
    """``matriz.md``: detalle por celda y cobertura XML, solo con marcadores."""
    lineas = [
        "# Matriz de detalle 019 — generada desde la huella (T1)",
        "",
        "> Generada por `backend/tests/utils_xlsx_diseno.py` desde `backend/tests/plantillas/"
        "*.json`. Solo marcadores: sin datos reales de la clínica. No editar a mano: "
        "regenerar. La matriz resumida (filas 1–27) está en `plan.md`; aquí está el detalle "
        "por celda, columna, fila e imagen, y la cobertura XML.",
        "",
        'Leyenda: `N` = negrita (confirmado en T1: `<b val="1"/>` / `<b/>`), `K` = cursiva. '
        "Colores en ARGB tal como los guarda la plantilla (el canal alfa no se compara, Q13).",
        "",
        "## Hallazgos de T1 (lo que la medición previa no leyó)",
        "",
        "- Contenido de los `dxf` del informe (3, idénticos): fuente cursiva color "
        "`FF92400E`; relleno sólido `FFFDE68A` (fg = bg). Activos: 0 `dxf`.",
        "- Barras de datos (Por ubicación y Por categoría, F8 y H8): sin `extLst` (sin "
        "extensión 2010), `cfvo` min y max sin `val`, color `FFBFDBFE`, prioridades 1 y 2.",
        "- Cuadrícula al imprimir: no hay `printOptions` en ninguna hoja → no se imprime.",
        '- Texto alternativo de las 7 imágenes: `descr="Picture"`; nombre `Image 1`.',
        "- Propiedades del documento: `creator` = `openpyxl` en ambas; `lastModifiedBy`, "
        "`created` y `modified` con valores del equipo que guardó (marcadores); sin "
        "título, asunto ni palabras clave. No se copian: ver «Propiedades del documento "
        "(fila 26)».",
        "- Fila 5 (borde inferior medio `FF1D4ED8`): Activos A5:L5; Todos A5:J5; Por "
        "ubicación A5:H5; No encontrados A5:F5; categoría A5:I5; Por categoría A5:H5; "
        "Resumen A5:J5 (= el ancho de la banda de la fila 1).",
        '- `N` es negrita: confirmado (`<b val="1"/>` en el informe, `<b/>` en activos).',
        "- Anchos: el valor guardado (`width`) de la plantilla es el que se compara; con "
        "xlsxwriter se obtiene exacto con `set_column_pixels(7 × ancho)`.",
        "- Alturas con decimales (44.1, 15.95, 26.1, 21.95, 27.95, 20.1): `set_row` las "
        "redondea a píxel; `set_row_pixels(alto / 0.75)` las escribe exactas.",
        "",
    ]
    for clave, h in huellas.items():
        lineas += [f"## Plantilla `{clave}` (`{h['plantilla']}`)", ""]
        libro = h["libro"]
        lineas += [
            f"- Hojas (orden): {', '.join(libro['hojas'])}",
            f"- Hoja activa: {libro['hoja_activa']} (Q11: no se reproduce; primera hoja, A1)",
            "- Nombres definidos: "
            + "; ".join(
                f"`{d['nombre']}`[{d['hoja']}] = `{d['valor']}`" for d in libro["nombres_definidos"]
            ),
            f"- `calcPr`: `{libro['calculo']}` (EQ Q13)",
            f"- Tema: {libro['tema']['nombre']}; mayor {libro['tema']['fuente_mayor']}, "
            f"menor {libro['tema']['fuente_menor']}",
            f"- Fuente por defecto: `{libro['fuente_defecto']}`",
            f"- dxfs: `{libro['dxfs']}`",
            f"- Propiedades: `{libro['propiedades']}`",
            "",
        ]
        for nombre, hoja in h["hojas"].items():
            q7 = nombre == "Resumen"
            lineas += [f"### Hoja `{nombre}`", ""]
            v = hoja["vista"]
            lineas += [
                f"- Pestaña `{(hoja['pestana'] or {}).get('rgb')}`; cuadrícula en pantalla "
                f"{'visible' if v['cuadricula'] else 'oculta'}; zoom {v['zoom'] or 100}; "
                f"congelado `{v['panel']}`",
                f"- Selección `{v['seleccion']}`, tabSelected {v['tab_seleccionada']}, "
                f"topLeftCell `{v['celda_superior_izquierda']}` (Q11: no se reproduce)",
                f"- Formato de hoja `{hoja['formato_hoja']}`",
                f"- Combinadas: {hoja['combinadas'] or 'ninguna'}"
                + (" (A10:J10 es de la lista omitida por Q7)" if q7 else ""),
                f"- Autofiltro `{hoja['autofiltro']}`; tablas `{hoja['tablas']}`; validaciones "
                f"{hoja['validaciones'] or 'ninguna'}; hipervínculos "
                f"{hoja['hipervinculos'] or 'ninguno'}; protección {hoja['proteccion']}",
                f"- Impresión `{hoja['impresion']}`",
                f"- Página `{hoja['pagina']}`",
                "",
                "| Columnas | Ancho guardado | Oculta | Estilo de columna |",
                "|---|---|---|---|",
            ]
            for c in hoja["columnas"]:
                rango = col_letra(c["min"]) + (
                    f"–{col_letra(c['max'])}" if c["max"] != c["min"] else ""
                )
                estilo = _resumen_estilo(c["estilo"]) if c["estilo"] else "-"
                lineas.append(f"| {rango} | {c['ancho']} | {c['oculta']} | {estilo} |")
            lineas += ["", "| Fila | Alto (pt) | Propio | Estilo de fila |", "|---|---|---|---|"]
            for num, f in hoja["filas"].items():
                estilo = _resumen_estilo(f["estilo"]) if f["estilo"] else "-"
                lineas.append(f"| {num} | {f['alto']} | {f['alto_propio']} | {estilo} |")
            lineas += [
                "",
                "| Celda | Valor | Estilo resuelto | Fila de matriz / decisión |",
                "|---|---|---|---|",
            ]
            for ref, c in hoja["celdas"].items():
                fila, _ = ref_a_rc(ref)
                decision = "5–9, 25"
                if q7 and fila >= 9:
                    decision = "NO REPRODUCIDO (Q7: lista duplicada del Resumen)"
                valor = "" if c["valor"] is None else str(c["valor"]).replace("|", "\\|")
                lineas.append(f"| {ref} | {valor} | {_resumen_estilo(c['estilo'])} | {decision} |")
            lineas += ["", "| Formato condicional | Detalle |", "|---|---|"]
            for cf in hoja["formato_condicional"]:
                nota = " (Q7: no se reproduce)" if q7 else ""
                lineas.append(f"| {cf['rango']}{nota} | `{cf}` |".replace("|`", "| `"))
            lineas += ["", "| Imagen | Detalle |", "|---|---|"]
            for i, img in enumerate(hoja["imagenes"]):
                lineas.append(f"| {i + 1} | `{img}` |")
            lineas.append("")
        lineas += [
            f"### Cobertura XML `{clave}`",
            "",
            "| Parte:ruta | Fila de matriz / decisión |",
            "|---|---|",
        ]
        for tipo, rutas in h["inventario_xml"].items():
            for r in rutas:
                lineas.append(f"| `{tipo}:{r}` | {destino_cobertura(f'{tipo}:{r}')} |")
        lineas.append("")
    lineas += [
        "## Equivalentes no idénticos (Q13, humano 2026-11-22)",
        "",
        *[f"- `{k}`: {v}" for k, v in EQUIVALENTES_NO_IDENTICOS.items()],
        "",
        "## Equivalentes aceptados fuera de Q13 (decisión del humano 2026-11-22)",
        "",
        *[f"- `{k}`: {v}" for k, v in EQUIVALENTES_ACEPTADOS.items()],
        "",
        "## Propiedades del documento (fila 26, decisión del humano 2026-11-22)",
        "",
        *[f"- `{k}`: {v}" for k, v in PROPIEDADES_DOCUMENTO.items()],
        "",
        "## Hojas de lista del informe (T4)",
        "",
        *[f"- `{k}`: {v}" for k, v in DECISIONES_T4.items()],
        "",
        "## Libro del informe (T5)",
        "",
        *[f"- `{k}`: {v}" for k, v in DECISIONES_T5.items()],
        "",
        "## Encabezado junto al logo (decisión del humano 2026-11-24)",
        "",
        *[f"- `{k}`: {v}" for k, v in DECISIONES_ENCABEZADO.items()],
        "",
    ]
    return "\n".join(lineas)


def generar(directorio: Path = DIR_PLANTILLAS) -> dict[str, dict[str, Any]]:
    DIR_HUELLAS.mkdir(parents=True, exist_ok=True)
    huellas = {}
    for clave, archivo in PLANTILLAS.items():
        h = huella_de_plantilla(directorio / archivo)
        (DIR_HUELLAS / f"{clave}.json").write_text(
            json.dumps(h, ensure_ascii=False, indent=1, sort_keys=False) + "\n",
            encoding="utf-8",
        )
        huellas[clave] = h
    MATRIZ.write_text(generar_matriz(huellas), encoding="utf-8")
    return huellas


if __name__ == "__main__":
    generar()
    print("Huellas y matriz regeneradas.")  # noqa: T201
