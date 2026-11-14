"""Límites de tasa de login, refresh, validar y aceptar invitación (spec 002, T10).

R13, Q10 y A13; contadores en la tabla de infraestructura ``limite_tasa``
(``docs/03`` cambio 6, ``plan.md`` §3.1), sin Flask-Limiter ni Redis.

- **Antes del trabajo caro.** Cada ruta llama a su ``limit_*`` después de validar
  la forma del cuerpo y antes de Argon2 y de cualquier función ``acceso.*``. El
  intento se suma en una **transacción propia y confirmada**
  (``app.db.contar_intentos``): el fallo posterior de la petición no lo revierte.
- **Atómico.** Un ``INSERT ... ON CONFLICT DO UPDATE ... RETURNING intentos`` por
  contador; se permite la petición si, tras sumar, ``intentos <= umbral``. Con N
  peticiones simultáneas pasan exactamente las que caben.
- **Falla cerrado.** Si contar falla por cualquier motivo: ``503``
  (``ServiceUnavailableError``) sin tocar la cuenta ni Argon2. En el log solo el
  tipo del error y su ``sqlstate``.
- **Claves.** HMAC-SHA256 con una clave derivada de ``SECRET_KEY`` y contexto
  propio por tipo (``derive_key``): por IP sobre la dirección agrupada
  (``client_address``) y por cuenta sobre ``normalize_email``. Lo que no se puede
  normalizar (vacío, NUL, sustituto, letras inestables) va a un único cubo fijo,
  distinto de toda cuenta real. Se cuenta igual exista o no la cuenta.
- **IP del cliente.** ``request.remote_addr``: sin proxy de confianza es la del par
  TCP (se ignora ``X-Forwarded-For``); con ``TRUSTED_PROXY_HOPS = N`` la fija
  ``ProxyFix`` (``x_for=N``) con la dirección que añadió el último proxy de
  confianza, así que una IP falsa antepuesta por el cliente no cuenta. IPv6 se
  agrupa por /64 (un cliente suele tener el prefijo entero); IPv4 mapeada en IPv6
  cuenta como IPv4; lo que no es una IP va a un cubo fijo.
- **``429`` genérico** (``TooManyRequestsError``): mismo cuerpo y cabeceras para
  toda cuenta y endpoint; ``Retry-After`` es la duración de la ventana, constante.
- **Solo los fallos de login y refresh.** Si la petición termina bien se devuelve
  su intento (``give_back``); validar y aceptar cuentan todas (Q10). El logout no
  se limita.

Nada de este módulo registra IP, email, claves ni el mensaje de un error de base.
"""

import hashlib
import hmac
import ipaddress
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from flask import current_app, request

from app.auth.credentials import derive_key
from app.auth.service import normalize_email
from app.config import RateLimits, get_config
from app.db import contar_intentos, devolver_intentos
from app.errors import ServiceUnavailableError, TooManyRequestsError, current_request_id

IP_KEY_CONTEXT = "limite-tasa-ip"
ACCOUNT_KEY_CONTEXT = "limite-tasa-cuenta"
# Dirección que no es una IP (o falta): todas comparten un contador.
UNKNOWN_ADDRESS = "desconocida"
# Prefijos de un byte: la cuenta real y el cubo fijo nunca dan el mismo mensaje.
_ACCOUNT_PREFIX = b"\x00"
_UNNORMALIZABLE_ACCOUNT = b"\x01sin-normalizar"
_IPV6_GROUP_PREFIX = 64

LOGIN_IP = "login_ip"
LOGIN_ACCOUNT = "login_cuenta"
REFRESH_IP = "refresh_ip"
VALIDATE_IP = "validar_ip"
ACCEPT_IP = "aceptar_ip"


def client_address(raw: str | None) -> str:
    """Dirección del cliente para el contador: IPv4 tal cual, IPv6 como su /64."""
    if raw is None:
        return UNKNOWN_ADDRESS
    try:
        address = ipaddress.ip_address(raw.strip())
    except ValueError:
        return UNKNOWN_ADDRESS
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped is not None:
            return str(address.ipv4_mapped)
        # int() descarta el identificador de zona (``%eth0``).
        bits = 128 - _IPV6_GROUP_PREFIX
        network = ipaddress.IPv6Network((int(address) >> bits << bits, _IPV6_GROUP_PREFIX))
        return str(network)
    return str(address)


def ip_key(secret_key: str, address: str) -> bytes:
    """HMAC de la dirección ya agrupada (``client_address``); 32 bytes."""
    key = derive_key(secret_key, IP_KEY_CONTEXT)
    return hmac.new(key, address.encode(), hashlib.sha256).digest()


def account_key(secret_key: str, email: str) -> bytes:
    """HMAC del email normalizado; lo no normalizable comparte un cubo fijo. 32 bytes."""
    normalized = normalize_email(email)
    message = (
        _UNNORMALIZABLE_ACCOUNT if normalized is None else _ACCOUNT_PREFIX + normalized.encode()
    )
    key = derive_key(secret_key, ACCOUNT_KEY_CONTEXT)
    return hmac.new(key, message, hashlib.sha256).digest()


@dataclass(frozen=True)
class Counter:
    """Un contador tras sumar el intento de esta petición."""

    ambito: str
    clave_hash: bytes
    ventana_inicio: datetime
    intentos: int
    limit: int

    @property
    def exceeded(self) -> bool:
        return self.intentos > self.limit


def increment_attempts(
    items: Sequence[tuple[str, bytes, int]], window_seconds: int
) -> list[Counter]:
    """Suma un intento a cada ``(ambito, clave_hash, umbral)``; transacción propia confirmada."""
    rows = contar_intentos([(ambito, clave) for ambito, clave, _ in items], window_seconds)
    return [
        Counter(
            ambito=ambito,
            clave_hash=clave,
            ventana_inicio=row.ventana_inicio,
            intentos=row.intentos,
            limit=limit,
        )
        for (ambito, clave, limit), row in zip(items, rows, strict=True)
    ]


def _error_summary(exc: BaseException) -> tuple[str, str]:
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None) or getattr(exc, "sqlstate", None)
    return type(exc).__name__, sqlstate if isinstance(sqlstate, str) else "desconocido"


def _enforce(items: Sequence[tuple[str, bytes, int]], limits: RateLimits) -> list[Counter]:
    failure: tuple[str, str] | None = None
    counters: list[Counter] = []
    try:
        counters = increment_attempts(items, limits.window_seconds)
    except Exception as exc:  # noqa: BLE001 - falla cerrado ante cualquier error
        failure = _error_summary(exc)
    if failure is not None:
        # Fuera del except: sin causa ni contexto que arrastren SQL, parámetros o valores.
        current_app.logger.error(
            "Límite de tasa no disponible; se responde 503 (request_id=%s, tipo=%s, sqlstate=%s)",
            current_request_id(),
            *failure,
        )
        raise ServiceUnavailableError()
    exceeded = sorted({counter.ambito for counter in counters if counter.exceeded})
    if exceeded:
        current_app.logger.warning(
            "Límite de tasa superado (request_id=%s, ambito=%s)",
            current_request_id(),
            ",".join(exceeded),
        )
        raise TooManyRequestsError(limits.window_seconds)
    return counters


def _settings() -> tuple[str, RateLimits]:
    return current_app.config["SECRET_KEY"], get_config(current_app).rate_limits


def _ip() -> str:
    return client_address(request.remote_addr)


def limit_login(email: str) -> list[Counter]:
    """Login: por IP y por cuenta (exista o no). ``429``/``503`` antes de Argon2."""
    secret, limits = _settings()
    return _enforce(
        [
            (LOGIN_IP, ip_key(secret, _ip()), limits.login_ip),
            (LOGIN_ACCOUNT, account_key(secret, email), limits.login_account),
        ],
        limits,
    )


def limit_refresh() -> list[Counter]:
    secret, limits = _settings()
    return _enforce([(REFRESH_IP, ip_key(secret, _ip()), limits.refresh_ip)], limits)


def limit_validate() -> list[Counter]:
    secret, limits = _settings()
    return _enforce([(VALIDATE_IP, ip_key(secret, _ip()), limits.validate_ip)], limits)


def limit_accept() -> list[Counter]:
    secret, limits = _settings()
    return _enforce([(ACCEPT_IP, ip_key(secret, _ip()), limits.accept_ip)], limits)


def give_back(counters: Sequence[Counter]) -> None:
    """Devuelve el intento de una petición que terminó bien (login y refresh).

    Si la base falla aquí la petición ya tuvo éxito: se registra el tipo y el intento
    queda contado (el error solo puede endurecer el límite, nunca relajarlo).
    """
    failure: tuple[str, str] | None = None
    try:
        devolver_intentos([(c.ambito, c.clave_hash, c.ventana_inicio) for c in counters])
    except Exception as exc:  # noqa: BLE001 - la petición ya terminó bien
        failure = _error_summary(exc)
    if failure is not None:
        current_app.logger.warning(
            "No se pudo devolver el intento al límite de tasa (request_id=%s, tipo=%s, "
            "sqlstate=%s)",
            current_request_id(),
            *failure,
        )
