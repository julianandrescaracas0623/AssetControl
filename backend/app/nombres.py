"""Nombres visibles: ``usuario.nombre`` y ``tenant.nombre`` (spec 002, cambio H-3).

Un solo normalizador para la API (aceptar invitación) y el script del operador
(``create-tenant``), porque la web muestra ambos nombres (menús, barra lateral):

- NFC y recorte de espacios en los extremos; el tope se mide después.
- Máximo ``NOMBRE_MAX_LENGTH`` caracteres.
- Sin control (``Cc``), sustitutos sueltos (``Cs``), formato (``Cf``: U+202E que
  invierte el texto, U+200B invisible, U+FEFF, etiquetas), separadores de línea y
  párrafo (``Zl``, ``Zp``), uso privado (``Co``) ni sin asignar (``Cn``, según la
  base Unicode de Python).
- Al menos una letra o un número: un nombre de solo signos no identifica a nadie.

``None`` si no cumple; quien llama responde ``400 solicitud_invalida`` (API) o un
error de uso (CLI). El valor nunca se registra.
"""

import unicodedata

NOMBRE_MAX_LENGTH = 120

_REJECTED_CATEGORIES = frozenset({"Cc", "Cs", "Cf", "Zl", "Zp", "Co", "Cn"})


def normalize_display_name(value: str) -> str | None:
    if not isinstance(value, str):
        return None
    if any(unicodedata.category(char) == "Cs" for char in value):
        # Antes de NFC: un sustituto suelto no se puede normalizar ni codificar en UTF-8.
        return None
    name = unicodedata.normalize("NFC", value).strip()
    if not name or len(name) > NOMBRE_MAX_LENGTH:
        return None
    if any(unicodedata.category(char) in _REJECTED_CATEGORIES for char in name):
        return None
    if not any(unicodedata.category(char)[0] in "LN" for char in name):
        return None
    return name
