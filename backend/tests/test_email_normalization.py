"""Un único normalizador de email que coincide con el ``CHECK`` de la base (spec 002, T9; N1/H3).

``normalize_email`` (``app.auth.service``) es el único normalizador: lo usan el login (T6),
la creación de invitaciones (T8), el script del operador (T5) y lo usará la clave por cuenta
de ``limite_tasa`` (T10). Devuelve ``None`` cuando no puede garantizar que su salida
cumple ``email = lower(btrim(email))`` en PostgreSQL:

- La base de Unicode de Python (15.0 en 3.12) no conoce algunos caracteres que PostgreSQL 17
  sí pasa a minúsculas (U+1C89, U+A7CB/CC/DA/DC, U+10D50…U+10D65): antes daban un ``500`` por
  el ``CHECK``. Se rechaza todo carácter sin asignar en Python (``Cn``) y toda mayúscula o
  titular que quede tras ``lower()``.
- La prueba exhaustiva recorre todos los code points contra la base real: todo lo que el
  normalizador acepta cumple el ``CHECK``.
"""

import sys
import unicodedata

import pytest
from sqlalchemy import text

from app.auth.service import normalize_email
from app.invitaciones.service import normalize_invitation_email

# Mayúsculas que PostgreSQL 17 pasa a minúsculas y la base de Unicode de Python 3.12 no conoce
# (hallazgo H3 de T8). En una versión de Python con Unicode 16 ``lower()`` ya las convierte.
POSTGRES_ONLY_UPPERCASE = (
    0x1C89,
    0xA7CB,
    0xA7CC,
    0xA7DA,
    0xA7DC,
    *range(0x10D50, 0x10D66),
)


def _all_code_points() -> list[str]:
    return [chr(c) for c in range(1, sys.maxunicode + 1) if not 0xD800 <= c <= 0xDFFF]


@pytest.mark.parametrize("code_point", POSTGRES_ONLY_UPPERCASE, ids=lambda c: f"U+{c:04X}")
def test_characters_that_postgres_would_lowercase_are_rejected(code_point):
    if unicodedata.category(chr(code_point)) != "Cn":
        pytest.skip("esta versión de Python ya conoce el carácter y lo pasa a minúsculas")
    email = f"a{chr(code_point)}@ejemplo.test"

    assert normalize_email(email) is None
    assert normalize_invitation_email(email) is None


def test_uppercase_left_after_lower_is_rejected():
    """U+03D2 (GREEK UPSILON WITH HOOK SYMBOL) es ``Lu`` sin minúscula en Python."""
    value = "\u03d2@ejemplo.test"
    assert unicodedata.category(value.lower()[0]) == "Lu"
    assert normalize_email(value) is None


def test_ordinary_emails_are_still_normalized():
    assert normalize_email("  Ana.Pérez@Ejemplo.TEST\u00a0") == "ana.pérez@ejemplo.test"
    assert normalize_email("ÑANDÚ@EJEMPLO.TEST") == "ñandú@ejemplo.test"


def test_everything_the_normalizer_accepts_satisfies_the_database_check(db_connection):
    """Exhaustiva: cada code point solo, y entre letras, contra ``lower(btrim())`` real."""
    accepted = []
    for char in _all_code_points():
        for candidate in (char, f"a{char}b"):
            value = normalize_email(candidate)
            if value is not None:
                accepted.append(value)
    assert len(accepted) > 100_000

    mismatched = db_connection.execute(
        text("select v from unnest(cast(:values as text[])) as v where lower(btrim(v)) <> v"),
        {"values": accepted},
    ).scalars()

    assert [" ".join(f"U+{ord(c):04X}" for c in v) for v in mismatched] == []


def test_the_rejected_set_is_only_what_python_cannot_guarantee():
    """Sin falsos rechazos: todo lo rechazado es ``Cn`` o ``Lu``/``Lt`` tras ``lower()``."""
    for char in _all_code_points():
        if normalize_email(f"a{char}b") is not None:
            continue
        lowered = f"a{char}b".lower()
        reasons = {unicodedata.category(c) for c in lowered} & {"Cn", "Lu", "Lt"}
        assert reasons or char == "\x00", f"U+{ord(char):04X}"
