"""Credenciales del desarrollador (spec 017, T1–T2; R2, R7–R9; plan.md §2.1, §2.4).

- **Política (R8):** de 14 a 128 caracteres y fuera de la lista corta de comunes de la
  spec 002 (``app.auth.credentials.COMMON_PASSWORDS``, con la misma normalización).
- **Hash:** Argon2id con los mismos parámetros de producción que la 002
  (``ARGON2_PARAMS``). Lo calcula el comando del operador; a la base solo llega el hash.
- **Token de acceso de plataforma (T2, R2):** JWT ``HS256`` con ``sub`` (desarrollador),
  ``fam`` (familia de refresh de la sesión), ``typ=plataforma``, ``iss``, ``iat`` y
  ``exp`` (10 min); **sin ``tenant``**. Clave derivada de ``SECRET_KEY`` con su propio
  contexto (``plataforma-acceso``): un token de tenant no valida aquí ni uno de
  plataforma en el tenant (clave, ``typ`` y claims obligatorios distintos). ``fam`` deja
  que cada petición compruebe que la familia no fue revocada (logout, reuso, restablecer
  o desactivar por CLI): el token vigente muere con ella (A20).
- **Refresh:** cookie opaca ``<desarrollador_id>.<secreto>`` con doble hash como en la
  002 (``token_storage_hash``); 8 h, rotación y familia revocable.

Nada de este módulo registra logs ni incluye la contraseña, el hash o tokens en sus
mensajes.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import argon2
import jwt

from app.auth.credentials import (
    ARGON2_PARAMS,
    JWT_ALGORITHM,
    JWT_ISSUER,
    PASSWORD_MAX_LENGTH,
    PasswordPolicyError,
    check_password_policy,
    derive_key,
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


# --- Token de acceso y refresh de plataforma (T2) --------------------------------------------

PLATAFORMA_JWT_CONTEXT = "plataforma-acceso"
PLATAFORMA_TOKEN_TYPE = "plataforma"  # noqa: S105 - valor del claim typ, no un secreto
PLATAFORMA_ACCESS_TTL = timedelta(minutes=10)
PLATAFORMA_REFRESH_TTL = timedelta(hours=8)
_REQUIRED_CLAIMS = ("exp", "iat", "iss", "sub", "fam", "typ")
# Holgado para el secreto de ``new_token`` (43 caracteres base64url).
_REFRESH_SECRET = re.compile(r"[A-Za-z0-9_-]{1,128}")


class InvalidPlatformTokenError(Exception):
    """El token de plataforma no es válido. No incluye el token ni la causa."""

    def __init__(self) -> None:
        super().__init__("El token de acceso no es válido.")


@dataclass(frozen=True)
class PlatformClaims:
    sub: uuid.UUID
    familia: uuid.UUID


def encode_platform_token(
    secret_key: str, *, sub: uuid.UUID, familia: uuid.UUID, now: datetime | None = None
) -> str:
    issued = now or datetime.now(UTC)
    claims = {
        "sub": str(sub),
        "fam": str(familia),
        "typ": PLATAFORMA_TOKEN_TYPE,
        "iss": JWT_ISSUER,
        "iat": int(issued.timestamp()),
        "exp": int((issued + PLATAFORMA_ACCESS_TTL).timestamp()),
    }
    return jwt.encode(
        claims, derive_key(secret_key, PLATAFORMA_JWT_CONTEXT), algorithm=JWT_ALGORITHM
    )


def decode_platform_token(secret_key: str, token: str) -> PlatformClaims:
    """Valida firma (solo ``HS256``), ``exp``, ``iss``, ``typ`` y que no traiga ``tenant``."""
    failed = False
    result: PlatformClaims | None = None
    try:
        claims = jwt.decode(
            token,
            derive_key(secret_key, PLATAFORMA_JWT_CONTEXT),
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            options={"require": list(_REQUIRED_CLAIMS)},
        )
        if claims["typ"] != PLATAFORMA_TOKEN_TYPE or "tenant" in claims:
            raise ValueError
        result = PlatformClaims(
            sub=_canonical_uuid(claims["sub"]), familia=_canonical_uuid(claims["fam"])
        )
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        failed = True
    if failed or result is None:
        # Fuera del except: sin causa ni contexto que arrastren el token.
        raise InvalidPlatformTokenError()
    return result


def _canonical_uuid(value: object) -> uuid.UUID:
    if not isinstance(value, str):
        raise TypeError
    parsed = uuid.UUID(value)
    if str(parsed) != value:
        raise ValueError
    return parsed


def parse_refresh_cookie(value: str | None) -> tuple[uuid.UUID, str] | None:
    """``(desarrollador_id, secreto)`` de ``<desarrollador_id>.<secreto>``, o ``None``.

    El id solo propone el desarrollador de la ``plataforma_session``: el secreto se busca
    bajo RLS de ese desarrollador.
    """
    if not value:
        return None
    dev_part, sep, secret = value.partition(".")
    if not sep or not _REFRESH_SECRET.fullmatch(secret):
        return None
    try:
        return _canonical_uuid(dev_part), secret
    except (ValueError, TypeError):
        return None
