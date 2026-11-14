"""Configuración de la aplicación leída del entorno.

Nunca incluye valores de las variables en mensajes de error ni en ``repr``.
"""

import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

if TYPE_CHECKING:
    from flask import Flask

REQUIRED_VARS: tuple[str, ...] = ("DATABASE_URL", "SECRET_KEY", "ENVIRONMENT")


class MissingConfigError(RuntimeError):
    """Falta una o más variables de entorno obligatorias."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = list(missing)
        names = ", ".join(self.missing)
        super().__init__(f"Faltan variables de entorno obligatorias: {names}")


SECRET_KEY_MIN_BYTES = 32
TEST_ENVIRONMENT = "test"
DEVELOPMENT_ENVIRONMENT = "development"
# Lista cerrada (M1 de T4): cualquier otro valor falla al arrancar.
ALLOWED_ENVIRONMENTS: frozenset[str] = frozenset(
    {DEVELOPMENT_ENVIRONMENT, TEST_ENVIRONMENT, "production", "staging"}
)


def is_test_context() -> bool:
    """``True`` solo si el proceso corre bajo pytest (M1 de T4).

    Las relajaciones de ``ENVIRONMENT=test`` (``SECRET_KEY`` corta, Argon2 barato,
    ``TESTING``) dependen de esto: en un servidor o CLI real ``test`` no arranca.
    No hay variable de entorno que lo active: quien puede fijar ``ENVIRONMENT``
    también podría fijar esa variable.
    """
    return "pytest" in sys.modules


class InvalidEnvironmentError(RuntimeError):
    """``ENVIRONMENT`` fuera de la lista cerrada. No repite el valor recibido."""

    def __init__(self) -> None:
        allowed = ", ".join(sorted(ALLOWED_ENVIRONMENTS))
        super().__init__(f"ENVIRONMENT no es válido; valores admitidos: {allowed}.")


class UnsafeTestEnvironmentError(RuntimeError):
    """``ENVIRONMENT=test`` fuera de pytest (M1 de T4). No muestra valores."""

    def __init__(self) -> None:
        super().__init__(
            "ENVIRONMENT=test solo se admite al ejecutar las pruebas (pytest): desactiva "
            "el mínimo de SECRET_KEY y abarata Argon2. Usa development, staging o production."
        )


class WeakSecretKeyError(RuntimeError):
    """``SECRET_KEY`` demasiado corta fuera de pruebas (R15, Q11). Nunca muestra su valor."""

    def __init__(self) -> None:
        super().__init__(
            f"SECRET_KEY debe tener al menos {SECRET_KEY_MIN_BYTES} bytes; genera una con "
            '`python -c "import secrets; print(secrets.token_urlsafe(48))"`.'
        )


class InvalidSettingError(RuntimeError):
    """Una variable numérica opcional no es un entero en su rango (T10). No repite el valor."""

    def __init__(self, name: str, low: int, high: int) -> None:
        self.name = name
        super().__init__(f"{name} no es válida: debe ser un entero entre {low} y {high}.")


@dataclass(frozen=True)
class RateLimits:
    """Umbrales de los límites de tasa (R13, Q10): ventana fija y máximos por ventana.

    Los valores por defecto son los de referencia de Q10 (ventana de 15 min; login 5
    fallidos por cuenta y 20 por IP; validar y aceptar 10 por IP; refresh 30 por IP);
    se ajustan con ``RATE_LIMIT_*``.
    """

    window_seconds: int = 900
    login_account: int = 5
    login_ip: int = 20
    refresh_ip: int = 30
    validate_ip: int = 10
    accept_ip: int = 10


# Variable de entorno -> (campo de RateLimits, mínimo, máximo). La ventana máxima es un día:
# la purga (``purgar-limite-tasa``) solo borra ventanas de más de un día.
RATE_LIMIT_VARS: dict[str, tuple[str, int, int]] = {
    "RATE_LIMIT_WINDOW_SECONDS": ("window_seconds", 60, 86400),
    "RATE_LIMIT_LOGIN_ACCOUNT": ("login_account", 1, 10000),
    "RATE_LIMIT_LOGIN_IP": ("login_ip", 1, 10000),
    "RATE_LIMIT_REFRESH_IP": ("refresh_ip", 1, 10000),
    "RATE_LIMIT_VALIDATE_IP": ("validate_ip", 1, 10000),
    "RATE_LIMIT_ACCEPT_IP": ("accept_ip", 1, 10000),
}
TRUSTED_PROXY_HOPS_VAR = "TRUSTED_PROXY_HOPS"
TRUSTED_PROXY_HOPS_RANGE = (0, 5)
ARGON2_MAX_CONCURRENCY_VAR = "ARGON2_MAX_CONCURRENCY"
ARGON2_MAX_CONCURRENCY_RANGE = (1, 64)
DEFAULT_ARGON2_MAX_CONCURRENCY = 4
_ASCII_INTEGER = re.compile(r"[0-9]{1,6}")


def _int_setting(source: Mapping[str, str], name: str, default: int, low: int, high: int) -> int:
    """Entero ASCII de ``name`` en ``[low, high]``; vacío o ausente -> ``default``."""
    raw = (source.get(name) or "").strip()
    if not raw:
        return default
    if not _ASCII_INTEGER.fullmatch(raw) or not low <= int(raw) <= high:
        raise InvalidSettingError(name, low, high)
    return int(raw)


def _check_range(name: str, value: object, low: int, high: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise InvalidSettingError(name, low, high)


@dataclass(frozen=True)
class Config:
    """Configuración validada al construirse (arranque, R15).

    ``environment`` debe estar en ``ALLOWED_ENVIRONMENTS``; distinto de
    ``development`` se trata como producción: cookies ``Secure``. Solo ``test``
    admite una ``SECRET_KEY`` corta, y ``test`` solo vale bajo pytest
    (``is_test_context``).
    """

    database_url: str = field(repr=False)
    secret_key: str = field(repr=False)
    environment: str
    # T10 (R13, Q10): umbrales del límite de tasa, saltos de proxy de confianza para la IP
    # del cliente (0 = sin ProxyFix: REMOTE_ADDR) y tope de hashes Argon2 simultáneos.
    rate_limits: RateLimits = field(default_factory=RateLimits)
    trusted_proxy_hops: int = 0
    argon2_max_concurrency: int = DEFAULT_ARGON2_MAX_CONCURRENCY

    def __post_init__(self) -> None:
        if self.environment not in ALLOWED_ENVIRONMENTS:
            raise InvalidEnvironmentError()
        _check_range(TRUSTED_PROXY_HOPS_VAR, self.trusted_proxy_hops, *TRUSTED_PROXY_HOPS_RANGE)
        _check_range(
            ARGON2_MAX_CONCURRENCY_VAR, self.argon2_max_concurrency, *ARGON2_MAX_CONCURRENCY_RANGE
        )
        for name, (attribute, low, high) in RATE_LIMIT_VARS.items():
            _check_range(name, getattr(self.rate_limits, attribute), low, high)
        if self.environment == TEST_ENVIRONMENT and not is_test_context():
            raise UnsafeTestEnvironmentError()
        if (
            self.environment != TEST_ENVIRONMENT
            and len(self.secret_key.encode()) < SECRET_KEY_MIN_BYTES
        ):
            raise WeakSecretKeyError()

    @property
    def is_test(self) -> bool:
        """``ENVIRONMENT=test`` y proceso bajo pytest; se reevalúa en cada uso."""
        return self.environment == TEST_ENVIRONMENT and is_test_context()

    @property
    def secure_cookies(self) -> bool:
        """``Secure`` salvo ``ENVIRONMENT=development`` exacto (B4 de T7 de la spec 001)."""
        return self.environment != DEVELOPMENT_ENVIRONMENT

    def to_flask(self) -> dict[str, object]:
        return {
            "DATABASE_URL": self.database_url,
            "SECRET_KEY": self.secret_key,
            "ENVIRONMENT": self.environment,
            "TESTING": self.is_test,
        }


CONFIG_EXTENSION_KEY = "assetcontrol.config"


def get_config(app: "Flask") -> Config:
    """``Config`` con la que se creó ``app`` (``create_app`` la guarda en ``extensions``)."""
    return app.extensions[CONFIG_EXTENSION_KEY]


MIGRATION_URL_VAR = "MIGRATION_DATABASE_URL"


class SameDatabaseRoleError(RuntimeError):
    """La URL del migrador usa el mismo rol que la de la aplicación (R4c)."""

    def __init__(self) -> None:
        super().__init__(
            f"{MIGRATION_URL_VAR} usa el mismo rol que DATABASE_URL; "
            "las migraciones deben correr con el rol migrador, no con el de la aplicación"
        )


class InvalidDatabaseUrlError(RuntimeError):
    """No se pudo leer el rol de una URL de base de datos; nunca muestra la URL."""

    def __init__(self) -> None:
        super().__init__(
            f"No se pudo interpretar {MIGRATION_URL_VAR} o DATABASE_URL para comparar sus roles"
        )


def _url_username(raw: str) -> str | None:
    """Usuario decodificado con el mismo parser que el engine (``make_url``)."""
    try:
        return make_url(raw).username
    except (ArgumentError, ValueError, TypeError):
        # ``from None``: la excepción original puede traer fragmentos de la URL.
        raise InvalidDatabaseUrlError() from None


def load_migration_url(environ: Mapping[str, str] | None = None) -> str:
    """URL del rol migrador; la usa solo Alembic (``migrations/env.py``).

    No es obligatoria para arrancar la API. Nunca se usa ``DATABASE_URL`` en su
    lugar: si falta, falla con el nombre de la variable y sin su valor.

    Si ``DATABASE_URL`` está definida, el rol del migrador debe ser distinto; si
    alguna de las dos no se puede interpretar, falla (no se omite en silencio).
    Sin ``DATABASE_URL`` (job de migración dedicado) el chequeo no aplica.
    """
    source = os.environ if environ is None else environ
    url = (source.get(MIGRATION_URL_VAR) or "").strip()
    if not url:
        raise MissingConfigError([MIGRATION_URL_VAR])
    app_url = (source.get("DATABASE_URL") or "").strip()
    if app_url and _url_username(app_url) == _url_username(url):
        raise SameDatabaseRoleError()
    return url


def load_config(environ: Mapping[str, str] | None = None) -> Config:
    """Construye la configuración desde ``environ`` (por defecto ``os.environ``)."""
    source = os.environ if environ is None else environ
    missing = [name for name in REQUIRED_VARS if not (source.get(name) or "").strip()]
    if missing:
        raise MissingConfigError(missing)
    defaults = RateLimits()
    rate_limits = RateLimits(
        **{
            attribute: _int_setting(source, name, getattr(defaults, attribute), low, high)
            for name, (attribute, low, high) in RATE_LIMIT_VARS.items()
        }
    )
    return Config(
        database_url=source["DATABASE_URL"],
        secret_key=source["SECRET_KEY"],
        environment=source["ENVIRONMENT"].strip(),
        rate_limits=rate_limits,
        trusted_proxy_hops=_int_setting(
            source, TRUSTED_PROXY_HOPS_VAR, 0, *TRUSTED_PROXY_HOPS_RANGE
        ),
        argon2_max_concurrency=_int_setting(
            source,
            ARGON2_MAX_CONCURRENCY_VAR,
            DEFAULT_ARGON2_MAX_CONCURRENCY,
            *ARGON2_MAX_CONCURRENCY_RANGE,
        ),
    )
