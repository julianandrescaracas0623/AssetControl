"""Configuración de la aplicación leída del entorno.

Nunca incluye valores de las variables en mensajes de error ni en ``repr``.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

REQUIRED_VARS: tuple[str, ...] = ("DATABASE_URL", "SECRET_KEY", "ENVIRONMENT")


class MissingConfigError(RuntimeError):
    """Falta una o más variables de entorno obligatorias."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = list(missing)
        names = ", ".join(self.missing)
        super().__init__(f"Faltan variables de entorno obligatorias: {names}")


@dataclass(frozen=True)
class Config:
    database_url: str = field(repr=False)
    secret_key: str = field(repr=False)
    environment: str

    def to_flask(self) -> dict[str, object]:
        return {
            "DATABASE_URL": self.database_url,
            "SECRET_KEY": self.secret_key,
            "ENVIRONMENT": self.environment,
            "TESTING": self.environment == "test",
        }


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
