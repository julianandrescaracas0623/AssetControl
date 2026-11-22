"""Ayudas de las pruebas de la consola de plataforma (spec 017, T2).

Reutiliza la base temporal de ``acceso_db`` (tenants A y B con admin y contador) y
siembra desarrolladores sintéticos (``@ejemplo.test``) con el migrador, que ve todas
las filas bajo ``FORCE RLS``. La app se crea con la consola habilitada.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import argon2
import jwt
from acceso_db import SECRET_KEY, AccesoDb
from flask import Flask
from sqlalchemy import text

from app import create_app
from app.auth.credentials import ARGON2_TEST_PARAMS, JWT_ISSUER, derive_key
from app.auth.http import CSRF_HEADER, CSRF_HEADER_VALUE
from app.config import Config, RateLimits
from app.plataforma.config import PlataformaConfig
from app.plataforma.credenciales import (
    PLATAFORMA_ACCESS_TTL,
    PLATAFORMA_JWT_CONTEXT,
    encode_platform_token,
)

DEV_PASSWORD = "Clave-Sintetica-Plataforma-2026"
COOKIE = "__Secure-plat-refresh"
CSRF = {CSRF_HEADER: CSRF_HEADER_VALUE}
HIGH_LIMITS = RateLimits(
    login_account=1000,
    login_ip=1000,
    refresh_ip=1000,
    plat_login_account=1000,
    plat_login_ip=1000,
    plat_accion=1000,
    plat_refresh_ip=1000,
)


@dataclass(frozen=True)
class Dev:
    id: uuid.UUID
    email: str
    nombre: str


def nuevo_dev(prefijo: str = "dev") -> Dev:
    sufijo = uuid.uuid4().hex[:10]
    return Dev(uuid.uuid4(), f"{prefijo}.{sufijo}@ejemplo.test", f"Dev {sufijo}")


def sembrar_dev(db: AccesoDb, dev: Dev, password: str = DEV_PASSWORD, activo: bool = True) -> Dev:
    hasher = argon2.PasswordHasher.from_parameters(ARGON2_TEST_PARAMS)
    with db.migrator.begin() as conn:
        conn.execute(
            text(
                "insert into desarrollador (id, email, nombre, password_hash, activo) "
                "values (:id, :e, :n, :h, :a)"
            ),
            {
                "id": dev.id,
                "e": dev.email,
                "n": dev.nombre,
                "h": hasher.hash(password),
                "a": activo,
            },
        )
    return dev


def ejecutar(db: AccesoDb, sql: str, params: dict | None = None) -> None:
    """Escritura directa como migrador (ve y cambia todas las filas)."""
    with db.migrator.begin() as conn:
        conn.execute(text(sql), params or {})


def filas(db: AccesoDb, sql: str, params: dict | None = None) -> list[dict]:
    with db.migrator.connect() as conn:
        return [dict(row) for row in conn.execute(text(sql), params or {}).mappings()]


def make_plat_app(
    db: AccesoDb,
    *,
    rate_limits: RateLimits | None = None,
    redes: tuple[str, ...] = (),
    environment: str = "test",
    trusted_proxy_hops: int = 0,
    habilitada: bool = True,
) -> Flask:
    return create_app(
        Config(
            database_url=db.app_url.render_as_string(hide_password=False),
            secret_key=SECRET_KEY,
            environment=environment,
            rate_limits=rate_limits or HIGH_LIMITS,
            trusted_proxy_hops=trusted_proxy_hops,
            plataforma=PlataformaConfig.desde_texto(
                "true" if habilitada else "false", ",".join(redes)
            ),
        )
    )


def plat_token(dev: Dev, familia: uuid.UUID, now: datetime | None = None) -> str:
    return encode_platform_token(SECRET_KEY, sub=dev.id, familia=familia, now=now)


def plat_bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def forged_platform(claims: dict, key: bytes | None = None) -> str:
    return jwt.encode(
        claims, key or derive_key(SECRET_KEY, PLATAFORMA_JWT_CONTEXT), algorithm="HS256"
    )


def platform_claims(dev: Dev, familia: uuid.UUID, **changes) -> dict:
    now = datetime.now(UTC)
    claims = {
        "sub": str(dev.id),
        "fam": str(familia),
        "typ": "plataforma",
        "iss": JWT_ISSUER,
        "iat": int(now.timestamp()),
        "exp": int((now + PLATAFORMA_ACCESS_TTL).timestamp()),
    }
    claims.update(changes)
    return {k: v for k, v in claims.items() if v is not None}


def expired(dev: Dev, familia: uuid.UUID) -> str:
    return plat_token(dev, familia, now=datetime.now(UTC) - timedelta(hours=1))


def login(client, email: str, password: str = DEV_PASSWORD, **kwargs):
    return client.post(
        "/plataforma/auth/login", json={"email": email, "password": password}, **kwargs
    )


def cookie_value(response) -> str:
    for header in response.headers.getlist("Set-Cookie"):
        name, _, rest = header.partition("=")
        if name == COOKIE:
            return rest.split(";", 1)[0]
    raise AssertionError("sin cookie de refresh de plataforma")


def refresh(client, value: str | None, headers: dict | None = None):
    cookie = {} if value is None else {"Cookie": f"{COOKIE}={value}"}
    return client.post("/plataforma/auth/refresh", headers={**CSRF, **cookie, **(headers or {})})


def logout(client, value: str | None, headers: dict | None = None):
    cookie = {} if value is None else {"Cookie": f"{COOKIE}={value}"}
    return client.post("/plataforma/auth/logout", headers={**CSRF, **cookie, **(headers or {})})


def error_code(response) -> str:
    return response.get_json()["error"]["code"]
