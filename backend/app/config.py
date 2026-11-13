"""Configuración de la aplicación leída del entorno.

Nunca incluye valores de las variables en mensajes de error ni en ``repr``.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

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


class WeakSecretKeyError(RuntimeError):
    """``SECRET_KEY`` demasiado corta fuera de pruebas (R15, Q11). Nunca muestra su valor."""

    def __init__(self) -> None:
        super().__init__(
            f"SECRET_KEY debe tener al menos {SECRET_KEY_MIN_BYTES} bytes; genera una con "
            '`python -c "import secrets; print(secrets.token_urlsafe(48))"`.'
        )


@dataclass(frozen=True)
class Config:
    """Configuración validada al construirse (arranque, R15).

    ``environment`` distinto de ``development`` se trata como producción: cookies
    ``Secure``. Solo ``test`` admite una ``SECRET_KEY`` corta.
    """

    database_url: str = field(repr=False)
    secret_key: str = field(repr=False)
    environment: str

    def __post_init__(self) -> None:
        if (
            self.environment != TEST_ENVIRONMENT
            and len(self.secret_key.encode()) < SECRET_KEY_MIN_BYTES
        ):
            raise WeakSecretKeyError()

    @property
    def secure_cookies(self) -> bool:
        """``Secure`` salvo ``ENVIRONMENT=development`` exacto (B4 de T7 de la spec 001)."""
        return self.environment != DEVELOPMENT_ENVIRONMENT

    def to_flask(self) -> dict[str, object]:
        return {
            "DATABASE_URL": self.database_url,
            "SECRET_KEY": self.secret_key,
            "ENVIRONMENT": self.environment,
            "TESTING": self.environment == TEST_ENVIRONMENT,
        }


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
    return Config(
        database_url=source["DATABASE_URL"],
        secret_key=source["SECRET_KEY"],
        environment=source["ENVIRONMENT"].strip(),
    )
