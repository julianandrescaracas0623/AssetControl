"""Estilo común de los Excel según las plantillas del humano (spec 019, T2).

Constantes y funciones de dibujo que comparten el Excel de activos (plantilla A,
``Activos_20261122_diseno.xlsx``) y el del informe de sesión (plantilla B,
``Informe_boseto_limpio.xlsx``): banda (fila 1), bloque de empresa con logo (filas 2–5),
cabecera de tabla, fila de datos, fila Total, formatos, anchos, alturas, pie, márgenes y
página. Todos los valores son los MEDIDOS en las plantillas (matriz de ``plan.md`` y
``specs/019-diseno-informes-excel/matriz.md``), nunca calculados; las pruebas
(``tests/test_exportar_estilo.py``) los comparan con la huella versionada.

Notas de reproducción con ``xlsxwriter`` (sondas de T1):

- Anchos: ``set_column_pixels(7 × ancho)`` guarda el ``width`` exacto de la plantilla.
- Alturas: ``set_row_pixels(alto / 0.75)`` guarda los decimales (44.1, 15.95…) exactos.
- Arial sin familia (``font_family: 0``), como la plantilla; formatos incorporados por su
  número (3 = ``#,##0``, 14 = fecha ``mm-dd-yy``); relleno sólido con fg = bg.
- Logo: ``twoCellAnchor editAs="oneCell"`` (Q13) con desplazamiento y tamaño en EMU
  exactos; ajustado dentro de la caja de la hoja conservando su proporción (Q10).

Dinero: ``Decimal`` hasta el borde de ``xlsxwriter`` (``write_number``); un ``float`` se
rechaza. Texto: siempre ``write_string`` (nunca fórmula).
"""

from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol

EMU_POR_PX = 9525
PX_POR_CARACTER = 7  # ancho guardado exacto con set_column_pixels (T1)
PT_POR_PX = 0.75
CIFRAS_SIGNIFICATIVAS = 16  # xlsxwriter escribe los números con «{:.16G}» (T5)

# --- Paleta (matriz filas 5–7, 23) -------------------------------------------------------
AZUL = "#1D4ED8"  # banda, pestaña, empresa, línea de la fila 5, rótulos de tarjeta
TINTA = "#111827"  # títulos, NIT, datos y totales
GRIS = "#6B7280"  # informe: fecha, contacto, dirección, notas
GRIS_ACTIVOS = "#4B5563"  # activos: fecha, «Correo», contacto, dirección (R7)
FONDO_CABECERA = "#1F2937"
BLANCO = "#FFFFFF"
DIVISOR = "#E5E7EB"  # línea fina bajo «Informe · …» (encabezado, 2026-11-24)
LINEA = "#9CA3AF"  # bordes finos de cabecera, datos y total
FONDO_TOTAL = "#DBEAFE"  # Total de «Por ubicación» y «Por categoría»
BARRA = "#BFDBFE"  # barras de datos (T5)
AMBAR_TEXTO = "#92400E"  # dxf «se encontró en otra ubicación» (T4)
AMBAR_FONDO = "#FDE68A"

# --- Formatos numéricos (matriz fila 9) ---------------------------------------------------
FORMATO_COP = '"$"\\ #,##0.00'
FORMATO_UNIDADES = 3  # incorporado: #,##0
FORMATO_PORCENTAJE = "0.0\\ %"
FORMATO_FECHA = 14  # incorporado: mm-dd-yy (se muestra según la configuración regional)

# --- Página (matriz filas 15–17) y documento (fila 26) -----------------------------------
PIE = "&L&8 Generado con AssetControl&R&8 Página &P de &N"
MARGENES = {"left": 0.4, "right": 0.4, "top": 0.6, "bottom": 0.6}
AUTOR = "AssetControl"  # creator = lastModifiedBy (xlsxwriter no permite omitir el segundo)
TEXTO_ALTERNATIVO_LOGO = "Picture"  # L8

# Alturas del bloque común, en puntos (índice de fila de xlsxwriter, 0 = fila 1).
# Fila 4 (rótulos) y fila 5 (datos en dos líneas) del encabezado junto al logo (2026-11-24);
# el logo no cambia: su tamaño va en EMU (``CajaLogo``) y no depende del alto de las filas.
ALTOS_BLOQUE = {0: 6, 1: 44.1, 2: 18, 3: 16, 4: 30}
FILA_LOGO = 1  # el logo se ancla en la fila 2, columna A


def _arial(tamano: int, color: str, negrita: bool = False) -> dict[str, Any]:
    return {
        "font_name": "Arial",
        "font_family": 0,
        "font_size": tamano,
        "font_color": color,
        "bold": negrita,
    }


def _solido(color: str) -> dict[str, Any]:
    return {"pattern": 1, "fg_color": color, "bg_color": color}


_VC = {"valign": "vcenter"}
_CC = {"align": "center", "valign": "vcenter"}
_IZQ = {"align": "left", "valign": "vcenter"}
_BORDE = {"border": 1, "border_color": LINEA}
_LINEA_BLOQUE = {"bottom": 2, "bottom_color": AZUL}
_LINEA_TITULO = {"bottom": 1, "bottom_color": TINTA}
_DIVISOR = {"bottom": 1, "bottom_color": DIVISOR}
_AJUSTE = {"text_wrap": True}

# Catálogo: un formato por cada estilo medido en las plantillas (y ninguno más). «base» es
# el estilo por defecto (Calibri 11, color de tema 1) con la alineación de cada celda.
ESTILOS: dict[str, dict[str, Any]] = {
    # Celdas sin texto del bloque y de la plantilla (estilo por defecto + alineación).
    "base": {},
    "base_vcentro": _VC,
    "base_centro": {"align": "center"},
    # Bloque común (filas 1–5).
    "banda": _solido(AZUL),
    "linea_bloque": _LINEA_BLOQUE,
    "titulo": {**_arial(19, TINTA, True), **_VC},
    "titulo_resumen": {**_arial(19, TINTA, True), **_CC},
    # Encabezado junto al logo (2026-11-24): «Informe · …» con una línea fina debajo, rótulos
    # «Empresa», «Contacto» y «Dirección» y, bajo cada uno, sus datos en dos líneas.
    "subtitulo": {**_arial(10, GRIS_ACTIVOS), **_DIVISOR, **_VC},
    "divisor": {**_DIVISOR, **_VC},
    "rotulo_bloque": {**_arial(8, GRIS), "valign": "bottom"},
    "dato_bloque": {**_arial(9, TINTA), **_LINEA_BLOQUE, "valign": "top", **_AJUSTE},
    # Título y nota de las hojas de lista (T4).
    "titulo_lista": {**_arial(12, TINTA, True), **_LINEA_TITULO},
    "titulo_lista_vcentro": {**_arial(12, TINTA, True), **_LINEA_TITULO, **_VC},
    "titulo_lista_izquierda": {**_arial(12, TINTA, True), **_LINEA_TITULO, **_IZQ},
    "linea_titulo": _LINEA_TITULO,
    "linea_titulo_vcentro": {**_LINEA_TITULO, **_VC},
    "linea_titulo_izquierda": {**_LINEA_TITULO, **_IZQ},
    "nota": {**_arial(9, GRIS), **_VC, **_AJUSTE},
    # Cabecera de tabla.
    "cabecera": {**_arial(9, BLANCO, True), **_solido(FONDO_CABECERA), **_BORDE, **_CC, **_AJUSTE},
    "cabecera_activos": {
        **_arial(10, BLANCO, True),
        **_solido(FONDO_CABECERA),
        **_BORDE,
        **_CC,
        **_AJUSTE,
    },
    "cabecera_fuera": {**_arial(9, GRIS, True), "align": "left", **_AJUSTE},
    # Fila de datos.
    "datos": {**_arial(10, TINTA), **_BORDE, **_CC},
    "datos_cop": {**_arial(10, TINTA), **_BORDE, **_CC, "num_format": FORMATO_COP},
    "datos_unidades": {**_arial(10, TINTA), **_BORDE, **_CC, "num_format": FORMATO_UNIDADES},
    "datos_porcentaje": {**_arial(10, TINTA), **_BORDE, **_CC, "num_format": FORMATO_PORCENTAJE},
    "datos_fecha": {**_arial(10, TINTA), **_BORDE, **_CC, "num_format": FORMATO_FECHA},
    "datos_vacia": {**_BORDE, "align": "center"},  # informe: celda de datos sin valor
    # Fila Total.
    "total": {**_arial(10, TINTA, True), **_BORDE, **_CC},
    "total_izquierda": {**_arial(10, TINTA, True), **_BORDE, **_IZQ},
    "total_cop": {**_arial(10, TINTA, True), **_BORDE, **_CC, "num_format": FORMATO_COP},
    "total_cop_derecha": {
        **_arial(10, TINTA, True),
        **_BORDE,
        "align": "right",
        "valign": "vcenter",
        "num_format": FORMATO_COP,
    },
    "total_fondo": {**_arial(10, TINTA, True), **_solido(FONDO_TOTAL), **_BORDE, **_CC},
    "total_fondo_cop": {
        **_arial(10, TINTA, True),
        **_solido(FONDO_TOTAL),
        **_BORDE,
        **_CC,
        "num_format": FORMATO_COP,
    },
    "total_fondo_unidades": {
        **_arial(10, TINTA, True),
        **_solido(FONDO_TOTAL),
        **_BORDE,
        **_CC,
        "num_format": FORMATO_UNIDADES,
    },
    "total_fondo_porcentaje": {
        **_arial(10, TINTA, True),
        **_solido(FONDO_TOTAL),
        **_BORDE,
        **_CC,
        "num_format": FORMATO_PORCENTAJE,
    },
    "total_fuera": {**_arial(10, TINTA, True), **_IZQ},
    # Tarjetas del Resumen (T5).
    "tarjeta_rotulo": {**_arial(9, AZUL, True), **_CC},
    "tarjeta_subtexto": {**_arial(9, GRIS), **_CC},
    "tarjeta_valor_cop": {**_arial(18, TINTA, True), **_CC, "num_format": FORMATO_COP},
    "tarjeta_valor_porcentaje": {
        **_arial(18, TINTA, True),
        **_CC,
        "num_format": FORMATO_PORCENTAJE,
    },
}

# dxf del formato condicional «se encontró en otra ubicación» (T4): cursiva y fondo ámbar.
DXF_OTRA_UBICACION: dict[str, Any] = {
    "italic": True,
    "font_color": AMBAR_TEXTO,
    "pattern": 1,
    "bg_color": AMBAR_FONDO,
}


# --- Disposición de cada hoja de las plantillas ------------------------------------------


@dataclass(frozen=True)
class Columnas:
    """Rango de columnas (índices de xlsxwriter) con su ancho guardado en caracteres."""

    primera: int
    ultima: int
    ancho: float
    oculta: bool = False


@dataclass(frozen=True)
class CajaLogo:
    """Caja del logo en EMU: desplazamiento desde A2 y tamaño (matriz filas 13a/13b)."""

    col_off: int
    fila_off: int
    cx: int
    cy: int


@dataclass(frozen=True)
class Plantilla:
    titulo: str
    rotulo_fecha: str
    estilo_titulo: str
    ultima_columna_banda: int  # banda, línea de la fila 5 y área de impresión
    ultima_columna_bloque: int  # hasta dónde llevan estilo las filas 1 y 5
    caja_logo: CajaLogo
    columnas: tuple[Columnas, ...]
    margen_encabezado: float
    ajuste_alto: int  # 0 = alto automático (Q12)
    fila_repetida: int | None = None  # índice de fila a repetir al imprimir
    filas_congeladas: int = 0
    combinar_titulo: str | None = None
    altos: Mapping[int, float] = field(default_factory=dict)  # filas fijas bajo el bloque
    estilos_fila: Mapping[int, str] = field(default_factory=dict)  # estilo de fila propio
    fila_cabecera: int | None = None
    fila_datos: int | None = None
    fila_total: int | None = None  # None: justo después de la última fila de datos
    alto_datos: float | None = None
    alto_total: float | None = None
    estilos_cabecera: tuple[str, ...] = ()
    estilos_datos: tuple[str, ...] = ()
    estilos_total: tuple[str, ...] = ()
    estilo_vacia: str = "datos"  # celda de datos sin valor
    # Hojas de lista del informe (T4): fila 6 (título y su línea), fila 7 (nota combinada) y
    # regla de fila completa «se encontró en otra ubicación» (B11, matriz fila 23a).
    estilos_titulo_lista: tuple[str, ...] = ()
    combinar_nota: str | None = None
    formula_otra_ubicacion: str | None = None
    ultima_columna_datos: int | None = None  # rango del formato condicional


_BV = "base_vcentro"


_COLUMNAS_INFORME = (
    Columnas(0, 0, 14),
    Columnas(1, 1, 26),
    Columnas(2, 3, 18),
    Columnas(4, 5, 22),
    Columnas(6, 6, 20),
    Columnas(7, 8, 16),
    Columnas(9, 9, 18),
)
_COLUMNAS_RESUMEN = (Columnas(0, 0, 24), *_COLUMNAS_INFORME[1:])
_COLUMNAS_NO_ENCONTRADOS = (
    *_COLUMNAS_INFORME[:5],
    Columnas(6, 6, 20, True),
    Columnas(7, 8, 16, True),
    Columnas(9, 9, 18, True),
    Columnas(10, 10, 13, True),
)

_TOTAL_DESGLOSE = (
    "total_fondo",
    "total_fondo_cop",
    "total_fondo_unidades",
    "total_fondo_cop",
    "total_fondo_unidades",
    "total_fondo_cop",
    "total_fondo_unidades",
    "total_fondo_porcentaje",
    "total_fuera",
    "total_fuera",
)
_DATOS_DESGLOSE = (
    "datos",
    "datos_cop",
    "datos_unidades",
    "datos_cop",
    "datos_unidades",
    "datos_cop",
    "datos_unidades",
    "datos_porcentaje",
)
_INFORME = {"titulo": "Informe de activos", "rotulo_fecha": "Corte", "margen_encabezado": 0.3}
# El formato condicional de las listas llega en la plantilla hasta la fila 499 (A10:J499,
# A10:I499); con más filas se extiende hasta la última escrita (req. 5).
FILA_FIN_FORMATO_CONDICIONAL = 498


def _desglose(caja: CajaLogo) -> Plantilla:
    """«Por ubicación» y «Por categoría»: cabecera en la fila 7, Total tras los datos."""
    return Plantilla(
        **_INFORME,
        estilo_titulo="titulo",
        ultima_columna_banda=7,
        ultima_columna_bloque=9,
        caja_logo=caja,
        columnas=_COLUMNAS_INFORME,
        ajuste_alto=1,  # hoja corta: 1 × 1 (Q12)
        altos={5: 26.1, 6: 27.95},
        fila_cabecera=6,
        fila_datos=7,
        alto_datos=21.95,
        alto_total=21.95,
        estilos_cabecera=("cabecera",) * 8 + ("cabecera_fuera",) * 2,
        estilos_datos=_DATOS_DESGLOSE,
        estilos_total=_TOTAL_DESGLOSE,
        # Fila 6 (T5): título con su línea en A–H; I6 y J6 con el estilo por defecto.
        estilos_titulo_lista=("titulo_lista",) + ("linea_titulo",) * 7 + ("base",) * 2,
    )


def _lista(**kw: Any) -> Plantilla:
    """Hojas de lista del informe: título f6, nota f7, Total f8, cabecera f9, datos f10."""
    return Plantilla(
        **_INFORME,
        estilo_titulo="titulo",
        ultima_columna_bloque=9,
        ajuste_alto=0,  # lista: 1 página de ancho × alto automático (Q12)
        fila_repetida=8,
        filas_congeladas=9,
        fila_cabecera=8,
        fila_total=7,
        alto_datos=21.95,
        alto_total=21.95,
        estilo_vacia="datos_vacia",
        **kw,
    )


PLANTILLAS: dict[str, Plantilla] = {
    "activos": Plantilla(
        titulo="Inventario de activos",
        rotulo_fecha="Exportado",
        estilo_titulo="titulo",
        ultima_columna_banda=11,
        ultima_columna_bloque=11,
        caja_logo=CajaLogo(76199, 47625, 2828926, 1104900),
        columnas=(
            Columnas(0, 0, 14),
            Columnas(1, 1, 30),
            Columnas(2, 2, 20),
            Columnas(3, 3, 22),
            Columnas(4, 4, 14),
            Columnas(5, 5, 18),
            Columnas(6, 8, 16),
            Columnas(9, 9, 18),
            Columnas(10, 11, 20),
        ),
        margen_encabezado=0.5,
        ajuste_alto=0,
        fila_repetida=6,
        filas_congeladas=7,
        altos={6: 30},
        fila_cabecera=6,
        fila_datos=7,
        alto_datos=20.1,
        estilos_cabecera=("cabecera_activos",) * 12,
        estilos_datos=("datos",) * 9 + ("datos_fecha", "datos_cop", "datos_fecha"),
    ),
    "todos": _lista(
        ultima_columna_banda=9,
        caja_logo=CajaLogo(80010, 102870, 2537460, 1108710),
        columnas=_COLUMNAS_INFORME,
        altos={5: 26.1, 6: 26.1, 7: 21.95, 8: 27.95},
        fila_datos=9,
        estilos_cabecera=("cabecera",) * 10,
        estilos_datos=("datos",) * 9 + ("datos_cop",),
        estilos_total=("total", "total") + ("total_izquierda",) * 7 + ("total_cop_derecha",),
        estilos_titulo_lista=("titulo_lista_izquierda", "linea_titulo_izquierda")
        + ("linea_titulo",) * 8,
        combinar_nota="A7:J7",
        formula_otra_ubicacion='AND($F10<>"",$G10<>"",$F10<>$G10)',
        ultima_columna_datos=9,
    ),
    "por_ubicacion": _desglose(CajaLogo(171450, 114300, 2388870, 1013460)),
    "no_encontrados": _lista(
        ultima_columna_banda=5,
        caja_logo=CajaLogo(112395, 91440, 2411730, 1083944),
        columnas=_COLUMNAS_NO_ENCONTRADOS,
        altos={5: 26.1, 6: 26.1, 7: 21.95, 8: 27.95},
        fila_datos=9,
        estilos_cabecera=("cabecera",) * 6 + ("cabecera_fuera",) * 4,
        # La plantilla no trae fila de datos con estilo. Decisión del humano 2026-11-22 (T4):
        # los estilos de datos de las otras listas (texto y COP de «Todos los activos»; la
        # celda vacía, ``datos_vacia``), sin filas alternas. Sin formato condicional: la
        # regla de fila completa compara con «Encontrado en», que esta hoja no tiene.
        estilos_datos=("datos",) * 5 + ("datos_cop",),
        estilos_total=("total",) * 5 + ("total_cop",) + ("total_fuera",) * 4,
        estilos_titulo_lista=("titulo_lista_vcentro",) + ("linea_titulo",) * 5 + ("base",) * 4,
        combinar_nota="A7:F7",
        ultima_columna_datos=5,
    ),
    "categoria": _lista(
        ultima_columna_banda=8,
        caja_logo=CajaLogo(152400, 62865, 2396490, 1082040),
        columnas=_COLUMNAS_INFORME,
        altos={5: 26.1, 6: 26.1, 7: 21.95, 8: 27.95},
        estilos_fila={5: _BV},
        fila_datos=9,
        estilos_cabecera=("cabecera",) * 9,
        estilos_datos=("datos",) * 8 + ("datos_cop",),
        estilos_total=("total",) * 8 + ("total_cop", "total_fuera"),
        estilos_titulo_lista=("titulo_lista_vcentro",)
        + ("linea_titulo_vcentro",) * 8
        + ("base_vcentro",),
        combinar_nota="A7:I7",
        formula_otra_ubicacion='AND($E10<>"",$F10<>"",$E10<>$F10)',
        ultima_columna_datos=8,
    ),
    "por_categoria": _desglose(CajaLogo(129540, 57150, 2343150, 1082040)),
    "resumen": Plantilla(
        **_INFORME,
        estilo_titulo="titulo_resumen",
        combinar_titulo="C2:D2",
        ultima_columna_banda=9,
        ultima_columna_bloque=9,
        caja_logo=CajaLogo(205740, 68580, 2606040, 1074420),
        columnas=_COLUMNAS_RESUMEN,
        ajuste_alto=1,  # hoja corta: 1 × 1 (Q12)
        altos={5: 15.95, 6: 30, 7: 15.95},  # tarjetas; f9–f13 omitidas (Q7)
    ),
}


# --- Formatos ----------------------------------------------------------------------------


class Estilos:
    """Formatos del catálogo para un libro, creados una sola vez por nombre."""

    def __init__(self, libro: Any) -> None:
        self._libro = libro
        self._formatos: dict[str, Any] = {}

    def __call__(self, nombre: str) -> Any:
        if nombre not in self._formatos:
            self._formatos[nombre] = self._libro.add_format(dict(ESTILOS[nombre]))
        return self._formatos[nombre]


def propiedades(titulo: str) -> dict[str, str]:
    """Propiedades del documento (fila 26): título del libro y autor neutro."""
    return {"title": titulo, "author": AUTOR}


# --- Celdas y filas ----------------------------------------------------------------------


def escribir_celda(hoja: Any, fila: int, col: int, valor: Any, formato: Any) -> None:
    """Texto con ``write_string``, números desde ``Decimal``/``int``, fechas como fechas.

    ``None`` deja la celda vacía con su formato (bordes y alineación de la plantilla).
    Un ``float`` se rechaza: el dinero llega como ``Decimal`` exacto. Un ``Decimal`` de más
    de 16 cifras significativas también: ``xlsxwriter`` lo escribe con ``{:.16G}`` y lo
    redondearía en silencio (``NUMERIC(14,2)`` nunca llega a ese tope).
    """
    if valor is None:
        hoja.write_blank(fila, col, None, formato)
    elif isinstance(valor, str):
        hoja.write_string(fila, col, valor, formato)
    elif isinstance(valor, bool) or isinstance(valor, float):
        raise TypeError(f"Valor no admitido en el Excel: {type(valor).__name__}")
    elif isinstance(valor, Decimal) and len(valor.as_tuple().digits) > CIFRAS_SIGNIFICATIVAS:
        raise ValueError(
            f"Valor con más de {CIFRAS_SIGNIFICATIVAS} cifras significativas: el Excel lo "
            "redondearía"
        )
    elif isinstance(valor, Decimal | int):
        hoja.write_number(fila, col, valor, formato)
    elif isinstance(valor, date | datetime):
        hoja.write_datetime(fila, col, valor, formato)
    else:
        raise TypeError(f"Valor no admitido en el Excel: {type(valor).__name__}")


def alto_fila(hoja: Any, fila: int, alto_pt: float, formato: Any = None) -> None:
    """Altura exacta en puntos (``set_row`` redondearía a píxel entero)."""
    hoja.set_row_pixels(fila, alto_pt / PT_POR_PX, formato)


def escribir_fila(
    hoja: Any,
    estilos: Estilos,
    fila: int,
    celdas: Sequence[tuple[Any, str]],
    alto: float | None = None,
    col_inicio: int = 0,
) -> None:
    """Una fila de tabla: ``(valor, nombre de estilo)`` por columna desde ``col_inicio``."""
    if alto is not None:
        alto_fila(hoja, fila, alto)
    for i, (valor, nombre) in enumerate(celdas):
        escribir_celda(hoja, fila, col_inicio + i, valor, estilos(nombre))


# --- Hoja: columnas, alturas, vista y página ---------------------------------------------


def preparar_hoja(hoja: Any, plantilla: Plantilla, ultima_fila: int) -> None:
    """Anchos, alturas fijas, pestaña, cuadrícula, congelado e impresión de la plantilla.

    ``ultima_fila`` (índice de xlsxwriter) cierra el área de impresión: el rango de la
    plantilla se extiende hasta la última fila escrita (req. 5).
    """
    for c in plantilla.columnas:
        hoja.set_column_pixels(
            c.primera,
            c.ultima,
            round(c.ancho * PX_POR_CARACTER),
            None,
            {"hidden": True} if c.oculta else None,
        )
    for fila, alto in {**ALTOS_BLOQUE, **plantilla.altos}.items():
        alto_fila(hoja, fila, alto)
    hoja.set_tab_color(AZUL)
    hoja.hide_gridlines(2)
    if plantilla.filas_congeladas:
        hoja.freeze_panes(plantilla.filas_congeladas, 0)
    hoja.set_landscape()
    hoja.fit_to_pages(1, plantilla.ajuste_alto)
    hoja.set_margins(**MARGENES)
    hoja.set_header("", {"margin": plantilla.margen_encabezado})
    hoja.set_footer(PIE, {"margin": plantilla.margen_encabezado})
    hoja.print_area(0, 0, ultima_fila, plantilla.ultima_columna_banda)
    if plantilla.fila_repetida is not None:
        hoja.repeat_rows(plantilla.fila_repetida)


# --- Bloque de encabezado ----------------------------------------------------------------


class DatosEmpresa(Protocol):
    """Lo que el bloque lee de la empresa (vigente en activos, congelada en el informe)."""

    nombre: str | None
    nit: str | None
    telefono: str | None
    correo: str | None
    direccion: str | None
    logo: bytes | None


def _textos(empresa: DatosEmpresa, plantilla: Plantilla, fecha: date) -> dict[str, str | None]:
    """Texto de cada dato del bloque; un dato ausente se omite (Q9) y un grupo sin datos
    queda en ``None`` (sin rótulo)."""

    def limpio(v: str | None) -> str | None:
        return v if v and v.strip() else None

    def lineas(*partes: str | None) -> str | None:
        return "\n".join(p for p in partes if p) or None

    nit, telefono = limpio(empresa.nit), limpio(empresa.telefono)
    nombre = limpio(empresa.nombre)
    fecha_txt = f"{plantilla.rotulo_fecha.lower()} {fecha:%d/%m/%Y}"
    return {
        "subtitulo": " · ".join(p for p in ("Informe", nombre, fecha_txt) if p),
        "empresa": lineas(nombre, f"NIT {nit}" if nit else None),
        "contacto": lineas(limpio(empresa.correo), f"Tel. {telefono}" if telefono else None),
        "direccion": limpio(empresa.direccion),
    }


@dataclass(frozen=True)
class GrupoBloque:
    """Rótulo de la fila 4 y dato de la fila 5, de la columna ``primera`` a ``ultima``."""

    rotulo: str
    clave: str
    primera: int
    ultima: int


def grupos_bloque(banda: int) -> tuple[GrupoBloque, ...]:
    """Empresa, Contacto y Dirección a la derecha del logo (desde C), hasta el fin de la
    banda. «No encontrados» (banda hasta F, G–K ocultas) les da una columna a los dos últimos."""
    if banda <= 5:
        contacto, direccion = (4, 4), (5, banda)
    else:
        contacto, direccion = (4, 5), (6, banda)
    return (
        GrupoBloque("Empresa", "empresa", 2, 3),
        GrupoBloque("Contacto", "contacto", *contacto),
        GrupoBloque("Dirección", "direccion", *direccion),
    )


def dibujar_bloque(
    hoja: Any, estilos: Estilos, plantilla: Plantilla, empresa: DatosEmpresa, fecha: date
) -> None:
    """Filas 1–5: banda, logo, título y «Informe · empresa · fecha» junto al logo y, debajo,
    Empresa (nombre y NIT), Contacto (correo y teléfono) y Dirección (decisión 2026-11-24).

    Un dato ausente se omite y un grupo sin datos queda sin rótulo; las celdas conservan su
    estilo (la línea azul de la fila 5 sigue entera). El logo conserva su caja.
    """
    textos = _textos(empresa, plantilla, fecha)
    banda, bloque = plantilla.ultima_columna_banda, plantilla.ultima_columna_bloque
    for col in range(bloque + 1):
        hoja.write_blank(0, col, None, estilos("banda" if col <= banda else "base"))
    if plantilla.combinar_titulo:
        hoja.merge_range(plantilla.combinar_titulo, None)  # sin formato: no escribe D2
    hoja.write_string(1, 2, plantilla.titulo, estilos(plantilla.estilo_titulo))
    # Fila 3: «Informe · …» y la línea fina hasta el fin de la banda.
    escribir_celda(hoja, 2, 2, textos["subtitulo"], estilos("subtitulo"))
    for col in range(3, bloque + 1):
        hoja.write_blank(2, col, None, estilos("divisor" if col <= banda else _BV))
    # Filas 4 y 5: rótulo y datos de cada grupo; la fila 5 lleva la línea azul.
    for col in range(2):
        hoja.write_blank(4, col, None, estilos("linea_bloque"))
    for g in grupos_bloque(banda):
        valor = textos[g.clave]
        rotulo, dato = estilos("rotulo_bloque"), estilos("dato_bloque")
        escribir_celda(hoja, 3, g.primera, g.rotulo if valor else None, rotulo)
        for col in range(g.primera + 1, g.ultima + 1):
            hoja.write_blank(3, col, None, rotulo)
        if g.ultima > g.primera:
            hoja.merge_range(4, g.primera, 4, g.ultima, None, dato)
        escribir_celda(hoja, 4, g.primera, valor, dato)  # texto literal (nunca fórmula)
    for col in range(banda + 1, bloque + 1):
        hoja.write_blank(3, col, None, estilos(_BV))
        hoja.write_blank(4, col, None, estilos("base"))
    for fila, nombre in plantilla.estilos_fila.items():
        alto_fila(hoja, fila, plantilla.altos[fila], estilos(nombre))
    insertar_logo(hoja, empresa.logo, plantilla.caja_logo)


def _rc(ref: str) -> tuple[int, int]:
    letras = ref.rstrip("0123456789")
    col = 0
    for ch in letras:
        col = col * 26 + ord(ch) - 64
    return int(ref[len(letras) :]) - 1, col - 1


# --- Logo (Q10) --------------------------------------------------------------------------


@dataclass(frozen=True)
class AjusteLogo:
    x_scale: float
    y_scale: float
    cx: int  # EMU finales
    cy: int


def ajustar_logo(
    ancho: float, alto: float, x_dpi: float, y_dpi: float, caja: CajaLogo
) -> AjusteLogo:
    """Escala única que hace caber el logo en la caja conservando su proporción (Q10).

    La dimensión que manda queda con los EMU exactos de la caja y la otra se redondea a
    EMU entero. Tiene en cuenta el escalado por 96/dpi que aplica ``xlsxwriter``.
    """
    natural_cx = ancho * 96.0 / x_dpi * EMU_POR_PX
    natural_cy = alto * 96.0 / y_dpi * EMU_POR_PX
    if caja.cx * natural_cy <= caja.cy * natural_cx:  # manda el ancho
        cx = caja.cx
        cy = min(caja.cy, round(natural_cy * caja.cx / natural_cx))
    else:
        cy = caja.cy
        cx = min(caja.cx, round(natural_cx * caja.cy / natural_cy))
    return AjusteLogo(cx / natural_cx, cy / natural_cy, cx, cy)


def insertar_logo(hoja: Any, logo: bytes | None, caja: CajaLogo) -> bool:
    """Inserta el logo ajustado a la caja; sin logo o ilegible, no inserta nada (req. 8)."""
    if not logo:
        return False
    from xlsxwriter.image import Image

    try:
        imagen = Image(io.BytesIO(logo))
    except Exception:  # un logo dañado o de formato no admitido no impide el archivo (req. 8)
        return False
    if not imagen.width or not imagen.height:
        return False
    ajuste = ajustar_logo(imagen.width, imagen.height, imagen.x_dpi, imagen.y_dpi, caja)
    hoja.insert_image(
        FILA_LOGO,
        0,
        "logo.png",
        {
            "image_data": io.BytesIO(logo),
            "x_offset": caja.col_off / EMU_POR_PX,
            "y_offset": caja.fila_off / EMU_POR_PX,
            "x_scale": ajuste.x_scale,
            "y_scale": ajuste.y_scale,
            "object_position": 2,
            "description": TEXTO_ALTERNATIVO_LOGO,
        },
    )
    return True
