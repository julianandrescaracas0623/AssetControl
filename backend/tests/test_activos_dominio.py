"""Reglas puras de activos (spec 004, T2; Q1, Q2; plan.md §3).

- ``normalizar_codigo``: recorta, pasa a mayúsculas y exige 1–40 caracteres ASCII entre
  letras, números y ``- . / _`` (Q1). Lo escaneado y lo escrito a mano coinciden.
- ``parsear_precio``: solo texto canónico ``"1390000"`` o ``"1390000.50"`` (la web
  convierte el formato colombiano); ``>= 0``, hasta dos decimales y el tope de
  ``NUMERIC(14,2)``; nunca ``float`` (Q2).
"""

from decimal import Decimal

import pytest

from app.activos.dominio import CODIGO_MAX, PRECIO_MAX, normalizar_codigo, parsear_precio


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("ac-0001", "AC-0001"),
        ("  000215 ", "000215"),
        ("x.y_z/9", "X.Y_Z/9"),
        ("a" * CODIGO_MAX, "A" * CODIGO_MAX),
    ],
)
def test_valid_codes_are_uppercased(entrada, esperado):
    assert normalizar_codigo(entrada) == esperado


@pytest.mark.parametrize(
    "entrada",
    ["", "   ", "A B", "AC#1", "árbol", "ß1", "ı1", "A" * (CODIGO_MAX + 1), "A\n1", "A​1", 5, None],
)
def test_invalid_codes(entrada):
    assert normalizar_codigo(entrada) is None


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("0", Decimal("0.00")),
        ("1390000", Decimal("1390000.00")),
        ("1390000.5", Decimal("1390000.50")),
        ("1390000.50", Decimal("1390000.50")),
        (" 25 ", Decimal("25.00")),
        ("999999999999.99", PRECIO_MAX),
    ],
)
def test_valid_prices(entrada, esperado):
    resultado = parsear_precio(entrada)
    assert resultado == esperado
    assert isinstance(resultado, Decimal)
    assert resultado.as_tuple().exponent == -2


@pytest.mark.parametrize(
    "entrada",
    [
        "",
        "-1",
        "1.390.000",
        "1390000,50",
        "1390000.505",
        "1e6",
        "NaN",
        "Infinity",
        "1000000000000",
        "$100",
        ".5",
        "5.",
        "+5",
        "٣",  # dígito arábigo: Decimal lo aceptaría
        1390000,
        1390000.5,
        True,
        None,
    ],
)
def test_invalid_prices(entrada):
    assert parsear_precio(entrada) is None
