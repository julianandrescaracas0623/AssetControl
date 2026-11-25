"""Comprobaciones comunes del logo con borde (decisiones del humano 2026-11-24 y 2026-11-25).

El logo va en una sola imagen compuesta: la imagen con esquinas redondeadas y, a
``MARGEN_MARCO_PX``, el borde gris medio con radio ``RADIO_MARCO_PX``. El logo conserva el
tamaño que le da su caja (Q10) y queda centrado en altura entre la banda y la línea azul.
"""

from typing import Any

from app.conteo import exportar_estilo as est

EMU = est.EMU_POR_PX


def comprobar_logo_con_borde(
    imagen: dict[str, Any], caja: est.CajaLogo, logo: bytes, ancho: int, alto: int, dpi: float = 96
) -> None:
    """``imagen``: la extraída por ``utils_xlsx_diseno``; ``ancho``/``alto``/``dpi``: los del
    logo subido."""
    assert (imagen["ancla"], imagen["edit_as"]) == ("twoCellAnchor", "oneCell")  # Q13
    assert (imagen["desde"]["col"], imagen["desde"]["fila"]) == (0, est.FILA_LOGO)
    ajuste = est.ajustar_logo(ancho, alto, dpi, dpi, caja)
    m = est.MARGEN_MARCO_PX * EMU
    # El logo, del tamaño de su caja (una dimensión exacta, la otra cabe) más el margen.
    cx, cy = imagen["xfrm"]["cx"], imagen["xfrm"]["cy"]
    assert abs(cx - (ajuste.cx + 2 * m)) <= 2 and abs(cy - (ajuste.cy + 2 * m)) <= 2, (cx, cy)
    assert ajuste.cx <= caja.cx and ajuste.cy <= caja.cy
    assert ajuste.cx == caja.cx or ajuste.cy == caja.cy
    # Horizontal: la caja de siempre, corrida el margen; vertical: centrado en el bloque.
    assert abs(imagen["desde"]["col_off"] - (caja.col_off - m)) <= 1
    arriba = imagen["desde"]["fila_off"] / EMU
    abajo = est.alto_bloque_px() - arriba - cy / EMU
    assert abs(arriba - abajo) <= 1.5, (arriba, abajo)
    # El borde no pasa a la columna C (el título).
    hasta = imagen["hasta"]
    assert hasta["col"] < 2 or (hasta["col"], hasta["col_off"]) == (2, 0), hasta
    # La imagen es la compuesta (una sola por libro) y sin pHYs, como la plantilla.
    compuesto = est.componer_logo(logo)
    assert compuesto is not None
    assert (imagen["imagen"]["ancho"], imagen["imagen"]["alto"]) == compuesto[1:]
    assert imagen["imagen"]["phys"] is None
    assert imagen["descr"] == est.TEXTO_ALTERNATIVO_LOGO
