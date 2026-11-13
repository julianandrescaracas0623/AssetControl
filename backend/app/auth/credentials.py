"""Credenciales y tokens (spec 002, T4; R12, R15; plan.md §2.2 y §6).

- **Contraseñas:** Argon2id (``argon2-cffi``, Q8). ``Passwords`` calcula al
  crearse un hash simulado con **los mismos parámetros** y lo verifica cuando la
  cuenta no existe, para que el tiempo del login no distinga cuentas (A10). Una
  contraseña sobre el máximo se rechaza sin hashear (A25).
- **Política (Q9):** de 10 a 128 caracteres y fuera de ``COMMON_PASSWORDS``.
- **Tokens opacos** (invitación y refresh): ``secrets.token_urlsafe``. La base
  recibe ``token_key(token) = sha256(token)`` en hex y guarda
  ``sha256(sha256(token))`` (``bytea``): el hash guardado no autentica (I1).
- **JWT de acceso:** ``HS256`` fijo, ``exp``, ``iss``, ``sub`` y ``tenant``
  obligatorios, clave derivada de ``SECRET_KEY`` con contexto propio (R15). El
  ``rol`` del claim es informativo: la autorización lo lee de ``membresia``.

Nada de este módulo registra logs ni incluye contraseñas, hashes o tokens en
los mensajes de error.
"""

import hashlib
import hmac
import secrets
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import argon2
import jwt
from argon2.exceptions import InvalidHashError, VerificationError
from flask import Flask, current_app

from app import config as config_module

# Argon2id. Perfil mínimo de OWASP (Password Storage Cheat Sheet; RFC 9106 §4 admite
# perfiles de menor memoria): m = 19 MiB, t = 2, p = 1. Hash de 32 bytes y sal de 16.
# Medido en T4 (ver tasks.md); lo revisa el security-reviewer antes del piloto.
ARGON2_PARAMS = argon2.Parameters(
    type=argon2.Type.ID,
    version=argon2.low_level.ARGON2_VERSION,
    salt_len=16,
    hash_len=32,
    time_cost=2,
    memory_cost=19 * 1024,
    parallelism=1,
)
# Solo con ENVIRONMENT=test (app.testing) y bajo pytest (M1 de T4): costo mínimo para
# que las pruebas no tarden.
ARGON2_TEST_PARAMS = argon2.Parameters(
    type=argon2.Type.ID,
    version=argon2.low_level.ARGON2_VERSION,
    salt_len=16,
    hash_len=32,
    time_cost=1,
    memory_cost=8,
    parallelism=1,
)

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128

# Lista corta de contraseñas comunes (Q9), en minúsculas y sin tildes normalizadas
# aparte: se compara con ``casefold`` y NFKC. Solo entradas de 10 o más caracteres; las
# más cortas ya las rechaza la longitud mínima.
COMMON_PASSWORDS: frozenset[str] = frozenset(
    {
        "0000000000",
        "0123456789",
        "1111111111",
        "1234567890",
        "12345678910",
        "123456789a",
        "1234567890a",
        "1q2w3e4r5t",
        "1qaz2wsx3edc",
        "abcdefghij",
        "abc1234567",
        "qwertyuiop",
        "qwerty1234",
        "qwerty12345",
        "asdfghjkl1",
        "asdfghjklñ",
        "zxcvbnm123",
        "password12",
        "password123",
        "password1234",
        "passw0rd123",
        "iloveyou12",
        "contraseña",
        "contrasena",
        "contraseña1",
        "contrasena1",
        "contraseña12",
        "contrasena12",
        "contraseña123",
        "contrasena123",
        "administrador",
        "administrador1",
        "administrador123",
        "admin12345",
        "admin123456",
        "bienvenido",
        "bienvenido1",
        "bienvenido123",
        "colombia123",
        "colombia2024",
        "colombia2025",
        "colombia2026",
        "teamo12345",
        "clinica123",
        "clinica1234",
        "odontologia",
        "odontologia1",
        "assetcontrol",
        "assetcontrol1",
        "inventario1",
        "inventario123",
    }
)


class PasswordPolicyError(ValueError):
    """La contraseña no cumple la política (Q9). Nunca incluye la contraseña."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _normalized(password: str) -> str:
    return unicodedata.normalize("NFKC", password).casefold()


def _encodable(password: str) -> bool:
    """``False`` si no se puede codificar en UTF-8 (sustituto suelto, p. ej. U+D800).

    Argon2 codifica en UTF-8: sin esto, ``UnicodeEncodeError`` daría un ``500``.
    """
    try:
        password.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def check_password_policy(password: str) -> None:
    """Falla con ``PasswordPolicyError`` si la contraseña no cumple Q9."""
    if not isinstance(password, str) or not _encodable(password):
        # Fuera del except de _encodable: sin causa que arrastre el carácter (B1 de T4).
        raise PasswordPolicyError("contrasena_invalida", "La contraseña no es válida.")
    if len(password) < PASSWORD_MIN_LENGTH:
        raise PasswordPolicyError(
            "contrasena_corta",
            f"La contraseña debe tener al menos {PASSWORD_MIN_LENGTH} caracteres.",
        )
    if len(password) > PASSWORD_MAX_LENGTH:
        raise PasswordPolicyError(
            "contrasena_larga",
            f"La contraseña no puede tener más de {PASSWORD_MAX_LENGTH} caracteres.",
        )
    if _normalized(password) in COMMON_PASSWORDS:
        raise PasswordPolicyError(
            "contrasena_comun", "Esa contraseña es demasiado común; elige otra."
        )


class Passwords:
    """Hash y verificación Argon2id con hash simulado del mismo costo."""

    def __init__(self, params: argon2.Parameters) -> None:
        self.params = params
        self._hasher = argon2.PasswordHasher.from_parameters(params)
        # Secreto aleatorio que no se conserva: el hash simulado no verifica nada.
        self._dummy_hash = self._hasher.hash(secrets.token_urlsafe(32))

    def hash(self, password: str) -> str:
        """Hash de una contraseña nueva; aplica la política antes de hashear."""
        check_password_policy(password)
        return self._hasher.hash(password)

    def verify(self, stored_hash: str | None, password: object) -> bool:
        """``True`` solo si ``password`` corresponde a ``stored_hash``.

        Sin cuenta (``stored_hash`` ``None``) verifica contra el hash simulado y
        devuelve ``False``. Sin texto, sobre el máximo o no codificable en UTF-8
        (sustituto suelto), ``False`` sin hashear, igual con y sin cuenta.
        """
        if (
            not isinstance(password, str)
            or len(password) > PASSWORD_MAX_LENGTH
            or not _encodable(password)
        ):
            return False
        target = self._dummy_hash if stored_hash is None else stored_hash
        try:
            self._hasher.verify(target, password)
        except (VerificationError, InvalidHashError):
            return False
        return stored_hash is not None


_EXTENSION_KEY = "assetcontrol.passwords"


def init_credentials(app: Flask) -> None:
    """Crea ``Passwords`` al arrancar (calcula el hash simulado una vez)."""
    # Doble condición: TESTING puesto a mano fuera de pytest no abarata Argon2.
    cheap = app.testing and config_module.is_test_context()
    params = ARGON2_TEST_PARAMS if cheap else ARGON2_PARAMS
    app.extensions[_EXTENSION_KEY] = Passwords(params)


def get_passwords() -> Passwords:
    return current_app.extensions[_EXTENSION_KEY]


# --- Tokens opacos ---------------------------------------------------------------

TOKEN_BYTES = 32


def new_token() -> str:
    """Token opaco de invitación o refresh (32 bytes aleatorios en base64url)."""
    return secrets.token_urlsafe(TOKEN_BYTES)


def token_key(token: str) -> str:
    """``sha256(token)`` en hex minúsculo: la clave que reciben las funciones ``acceso.*``."""
    return hashlib.sha256(token.encode()).hexdigest()


def token_storage_hash(token: str) -> bytes:
    """``sha256(sha256(token))``: lo que guarda la base en ``token_hash`` (``bytea``)."""
    return hashlib.sha256(hashlib.sha256(token.encode()).digest()).digest()


# --- Claves derivadas y JWT ----------------------------------------------------------

_KEY_DERIVATION_PREFIX = b"assetcontrol/v1/"
JWT_KEY_CONTEXT = "jwt-acceso"
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "assetcontrol"
ACCESS_TOKEN_TTL = timedelta(minutes=15)
_REQUIRED_CLAIMS = ("exp", "iss", "sub", "tenant")


def derive_key(secret_key: str, context: str) -> bytes:
    """Clave de 32 bytes para un uso (``context``); nunca ``SECRET_KEY`` cruda."""
    message = _KEY_DERIVATION_PREFIX + context.encode()
    return hmac.new(secret_key.encode(), message, hashlib.sha256).digest()


class InvalidAccessTokenError(Exception):
    """El JWT de acceso no es válido. No incluye el token ni la causa."""

    def __init__(self) -> None:
        super().__init__("El token de acceso no es válido.")


@dataclass(frozen=True)
class AccessClaims:
    sub: uuid.UUID
    tenant: uuid.UUID


def encode_access_token(
    secret_key: str,
    *,
    sub: uuid.UUID,
    tenant: uuid.UUID,
    rol: str | None,
    now: datetime | None = None,
) -> str:
    issued = now or datetime.now(UTC)
    claims: dict[str, object] = {
        "sub": str(sub),
        "tenant": str(tenant),
        "iss": JWT_ISSUER,
        "iat": int(issued.timestamp()),
        "exp": int((issued + ACCESS_TOKEN_TTL).timestamp()),
    }
    if rol is not None:
        claims["rol"] = rol
    return jwt.encode(claims, derive_key(secret_key, JWT_KEY_CONTEXT), algorithm=JWT_ALGORITHM)


def decode_access_token(secret_key: str, token: str) -> AccessClaims:
    """Valida firma (solo ``HS256``), ``exp``, ``iss``, ``sub`` y ``tenant``."""
    failed = False
    claims: dict[str, object] = {}
    try:
        claims = jwt.decode(
            token,
            derive_key(secret_key, JWT_KEY_CONTEXT),
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            options={"require": list(_REQUIRED_CLAIMS)},
        )
        result = AccessClaims(
            sub=uuid.UUID(str(claims["sub"])), tenant=uuid.UUID(str(claims["tenant"]))
        )
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        failed = True
    if failed:
        # Fuera del except: sin causa ni contexto que arrastren el token.
        raise InvalidAccessTokenError()
    return result
