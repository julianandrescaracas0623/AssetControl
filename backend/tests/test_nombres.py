"""Nombres visibles (spec 002, cambio H-3 del 2026-11-14).

``normalize_display_name`` es el único normalizador de ``usuario.nombre`` (aceptar
invitación) y ``tenant.nombre`` (``create-tenant``): NFC, recorte, máximo 120
caracteres, sin control, sustitutos, formato, separadores de línea/párrafo, uso
privado ni sin asignar, y al menos una letra o un número.
"""

import unicodedata

import pytest

from app.nombres import NOMBRE_MAX_LENGTH, normalize_display_name


def test_max_length_is_the_decided_one():
    assert NOMBRE_MAX_LENGTH == 120


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("Ana Torres", "Ana Torres"),
        ("  Ana Torres  ", "Ana Torres"),
        ("María José Ñúñez-O'Brien", "María José Ñúñez-O'Brien"),
        ("Clínica Biotecnología Dental 2", "Clínica Biotecnología Dental 2"),
        ("李小龙", "李小龙"),
        ("R2", "R2"),
        ("x" * 120, "x" * 120),
        # NFD (e + acento combinante) se guarda en NFC: se ve y compara igual.
        ("José", "José"),
        # El recorte se mide después de NFC: 119 letras + "é" en NFD caben.
        ("a" * 119 + "é", "a" * 119 + "é"),
    ],
)
def test_valid_names_are_normalized(valor, esperado):
    resultado = normalize_display_name(valor)
    assert resultado == esperado
    assert resultado is not None
    assert unicodedata.is_normalized("NFC", resultado)


@pytest.mark.parametrize(
    "valor",
    [
        "",
        "   ",
        "x" * 121,
        "​",  # espacio de ancho cero solo: nombre invisible
        "Ana​Torres",  # Cf dentro
        "Ana ‮serroT",  # U+202E invierte el texto (Cf)
        "﻿Ana",  # BOM (Cf)
        "Ana Torres",  # separador de línea (Zl)
        "Ana Torres",  # separador de párrafo (Zp)
        "Ana\U000e0041",  # etiqueta Unicode (Cf)
        "Ana",  # uso privado (Co)
        "Ana\U000e01f0x",  # sin asignar (Cn)
        "Ana\x00",  # control (Cc)
        "Ana\nTorres",
        "Ana\tTorres",
        "Ana\ud800",  # sustituto suelto (Cs)
        "...",  # sin letra ni número
        "-- __ !!",
        "́",  # solo un acento combinante
    ],
)
def test_invalid_names_are_rejected(valor):
    assert normalize_display_name(valor) is None


def test_non_string_is_rejected():
    assert normalize_display_name(None) is None  # type: ignore[arg-type]
    assert normalize_display_name(5) is None  # type: ignore[arg-type]
