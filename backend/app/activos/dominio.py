"""Reglas puras de activos (spec 004, T2; Q1, Q2): sin Flask ni base de datos."""

import re
from decimal import Decimal

CODIGO_MAX = 40
_CODIGO = re.compile(rf"[A-Z0-9._/-]{{1,{CODIGO_MAX}}}")
# Solo dígitos ASCII (``\d`` aceptaría otros sistemas de numeración).
_PRECIO = re.compile(r"[0-9]{1,12}(?:\.[0-9]{1,2})?")
PRECIO_MAX = Decimal("999999999999.99")
_CENTAVOS = Decimal("0.01")


def normalizar_codigo(valor: object) -> str | None:
    """Código del sticker en mayúsculas, o ``None`` si no cumple Q1."""
    if not isinstance(valor, str):
        return None
    codigo = valor.strip()
    if not codigo.isascii():
        return None
    codigo = codigo.upper()
    return codigo if _CODIGO.fullmatch(codigo) else None


def parsear_precio(valor: object) -> Decimal | None:
    """Precio canónico (``"1390000.50"``) como ``Decimal`` con dos decimales, o ``None``.

    Solo texto: un número JSON con decimales llega como ``float`` y no se acepta.
    """
    if not isinstance(valor, str):
        return None
    texto = valor.strip()
    if not _PRECIO.fullmatch(texto):
        return None
    precio = Decimal(texto).quantize(_CENTAVOS)
    return precio if precio <= PRECIO_MAX else None
