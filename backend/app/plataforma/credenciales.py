"""Credenciales del desarrollador (spec 017, T1; R7–R9; plan.md §2.4).

- **Política (R8):** de 14 a 128 caracteres y fuera de la lista corta de comunes de la
  spec 002 (``app.auth.credentials.COMMON_PASSWORDS``, con la misma normalización).
- **Hash:** Argon2id con los mismos parámetros de producción que la 002
  (``ARGON2_PARAMS``). Lo calcula el comando del operador; a la base solo llega el hash.

Nada de este módulo registra logs ni incluye la contraseña o el hash en sus mensajes.
"""

import argon2

from app.auth.credentials import (
    ARGON2_PARAMS,
    PASSWORD_MAX_LENGTH,
    PasswordPolicyError,
    check_password_policy,
)

DEVELOPER_PASSWORD_MIN_LENGTH = 14


def check_developer_password_policy(password: str) -> None:
    """Falla con ``PasswordPolicyError`` si la contraseña no cumple R8."""
    # El mínimo propio va primero: el de la 002 (10) daría un mensaje equivocado.
    if isinstance(password, str) and len(password) < DEVELOPER_PASSWORD_MIN_LENGTH:
        raise PasswordPolicyError(
            "contrasena_corta",
            f"La contraseña debe tener entre {DEVELOPER_PASSWORD_MIN_LENGTH} y "
            f"{PASSWORD_MAX_LENGTH} caracteres.",
        )
    # Luego la política común de la 002: tipo, UTF-8, máximo y lista de comunes.
    check_password_policy(password)


def hash_developer_password(password: str) -> str:
    """Hash Argon2id de una contraseña de desarrollador; aplica R8 antes de hashear."""
    check_developer_password_policy(password)
    return argon2.PasswordHasher.from_parameters(ARGON2_PARAMS).hash(password)
