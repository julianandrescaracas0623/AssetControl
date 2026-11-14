"""Límites de tasa (spec 002, T10; R13, Q10, A13; plan.md §3.1; docs/03 cambio 6).

Sobre una base temporal migrada a ``head`` (con ``limite_tasa``, 0005) y dos tenants
sintéticos, con ``COMMIT`` reales: el contador vive en su propia transacción y debe
sobrevivir al fallo de la petición. Cada prueba empieza con la tabla vacía (la vacía
el migrador, que en local y CI ve todas las filas).

Condiciones de la auditoría de seguridad de T9 que se prueban aquí:

1. El contador sube **antes** de Argon2, en transacción propia confirmada (espía del
   hasher: 0 llamadas en una petición limitada; el contador sobrevive a un ``500``).
2. Incremento atómico: hilos en paralelo no superan el umbral.
3. Falla cerrado: si ``limite_tasa`` falla, ``503`` sin tocar la cuenta ni Argon2.
4. IP solo del proxy de confianza (``TRUSTED_PROXY_HOPS``); IPv6 agrupada por /64; un
   ``X-Forwarded-For`` falso no evade el límite.
5. Clave por cuenta = HMAC (``derive_key``) de ``normalize_email``; lo no
   normalizable va a un cubo fijo; la cuenta exista o no, cuenta igual.
6. ``429`` idéntico (cuerpo, cabeceras, costo) para cuentas existentes e inexistentes,
   con ``Retry-After`` constante.
7. Contadores separados por endpoint, IP y cuenta; la aplicación no puede ``DELETE``
   (ni ``TRUNCATE``) en ``limite_tasa`` y solo actualiza ``intentos``.
8. Login y refresh cuentan solo los fallos (se devuelve el intento si la petición
   tiene éxito); validar y aceptar cuentan todos (Q10).
9. Semáforo de Argon2 por proceso: ``503`` al saturarse.

Datos sintéticos (``@ejemplo.test``, IP de documentación 192.0.2.0/24, 198.51.100.0/24,
203.0.113.0/24 y 2001:db8::/32): nunca datos de la clínica.
"""

import hashlib
import hmac
import importlib.util
import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from acceso_db import (
    ADMIN_A,
    ADMIN_B,
    PASSWORD,
    SECRET_KEY,
    AccesoDb,
    dispose,
    temporary_acceso_db,
)
from flask import Flask
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.pool import NullPool

from app import cli, create_app
from app.auth import limits, service
from app.auth.credentials import derive_key, get_passwords
from app.auth.http import CSRF_HEADER, CSRF_HEADER_VALUE
from app.config import Config, RateLimits
from app.invitaciones import service as invitaciones_service

LIMITS = RateLimits(
    window_seconds=900, login_account=3, login_ip=4, refresh_ip=3, validate_ip=3, accept_ip=3
)
CSRF = {CSRF_HEADER: CSRF_HEADER_VALUE}
SECURE_NAME = "__Secure-refresh"
IP_A = "192.0.2.10"
IP_B = "198.51.100.20"
BAD_PASSWORD = "Clave-Incorrecta-123"
RATE_LIMITED = {
    "code": "demasiadas_solicitudes",
    "message": "Demasiados intentos. Espera unos minutos e intenta de nuevo.",
}


@pytest.fixture(scope="module")
def db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("limites")


def build_app(db: AccesoDb, **overrides) -> Flask:
    config = Config(
        database_url=db.app_url.render_as_string(hide_password=False),
        secret_key=SECRET_KEY,
        environment="test",
        rate_limits=LIMITS,
    )
    return create_app(replace(config, **overrides))


@pytest.fixture(scope="module")
def limits_app(db) -> Iterator[Flask]:
    flask_app = build_app(db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture(autouse=True)
def empty_counters(db) -> Iterator[None]:
    """Cada prueba parte sin contadores (y no deja ninguno)."""
    purge_all(db)
    yield
    purge_all(db)


@pytest.fixture
def client(limits_app):
    return limits_app.test_client(use_cookies=False)


def purge_all(db: AccesoDb) -> None:
    with db.migrator.begin() as conn:
        conn.execute(text("delete from limite_tasa"))


def counters(db: AccesoDb) -> list[dict]:
    with db.migrator.connect() as conn:
        rows = conn.execute(
            text("select ambito, clave_hash, ventana_inicio, intentos from limite_tasa")
        ).mappings()
        return [dict(row) for row in rows]


def total(db: AccesoDb, ambito: str) -> int:
    return sum(row["intentos"] for row in counters(db) if row["ambito"] == ambito)


class HasherSpy:
    """Envuelve el ``PasswordHasher`` de la app y cuenta las llamadas a Argon2."""

    def __init__(self, hasher) -> None:
        self._hasher = hasher
        self.calls = 0
        self._lock = threading.Lock()

    def _count(self) -> None:
        with self._lock:
            self.calls += 1

    def verify(self, target, password):
        self._count()
        return self._hasher.verify(target, password)

    def hash(self, password, **kwargs):
        self._count()
        return self._hasher.hash(password, **kwargs)

    def __getattr__(self, name):
        return getattr(self._hasher, name)


@pytest.fixture
def hasher_spy(limits_app, monkeypatch) -> HasherSpy:
    with limits_app.app_context():
        passwords = get_passwords()
    spy = HasherSpy(passwords._hasher)
    monkeypatch.setattr(passwords, "_hasher", spy)
    return spy


def env(ip: str) -> dict[str, str]:
    return {"REMOTE_ADDR": ip}


def nobody() -> str:
    return f"nadie.{uuid.uuid4().hex[:10]}@ejemplo.test"


# Un intento fallido (no exitoso) por endpoint; ``subject`` elige la cuenta del login.
def attempt(client, endpoint: str, ip: str, *, subject: str | None = None, headers=None):
    extra = dict(headers or {})
    if endpoint == "login":
        body = {"email": nobody() if subject is None else subject, "password": BAD_PASSWORD}
        return client.post("/auth/login", json=body, environ_base=env(ip), headers=extra)
    if endpoint == "refresh":
        cookie = f"{SECURE_NAME}={uuid.uuid4()}.{uuid.uuid4().hex}"
        sent = {**CSRF, "Cookie": cookie, **extra}
        return client.post("/auth/refresh", headers=sent, environ_base=env(ip))
    if endpoint == "validar":
        body = {"token": uuid.uuid4().hex}
        return client.post("/invitaciones/validar", json=body, environ_base=env(ip), headers=extra)
    if endpoint == "aceptar":
        body = {"token": uuid.uuid4().hex, "nombre": "Nadie", "password": "Clave-Nueva-Sintetica-9"}
        return client.post("/invitaciones/aceptar", json=body, environ_base=env(ip), headers=extra)
    raise AssertionError(endpoint)


IP_LIMITS = {
    "login": ("login_ip", LIMITS.login_ip),
    "refresh": ("refresh_ip", LIMITS.refresh_ip),
    "validar": ("validar_ip", LIMITS.validate_ip),
    "aceptar": ("aceptar_ip", LIMITS.accept_ip),
}
ENDPOINTS = sorted(IP_LIMITS)


def error_of(response) -> dict:
    body = response.get_json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id"}
    return {k: v for k, v in body["error"].items() if k != "request_id"}


def stable_headers(response) -> dict[str, str]:
    """Cabeceras sin las que cambian por petición (``X-Request-ID``)."""
    return {k: v for k, v in response.headers.items() if k != "X-Request-ID"}


def assert_rate_limited(response) -> None:
    assert response.status_code == 429, response.get_json()
    assert error_of(response) == RATE_LIMITED
    assert response.headers["Retry-After"] == str(LIMITS.window_seconds)
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "Set-Cookie" not in response.headers


def exhaust(client, endpoint: str, ip: str, **kwargs) -> None:
    _, limit = IP_LIMITS[endpoint]
    for _ in range(limit):
        response = attempt(client, endpoint, ip, **kwargs)
        assert response.status_code != 429, (endpoint, response.get_json())


# --- Configuración (Q10) ------------------------------------------------------------


def test_default_thresholds_are_those_of_q10():
    assert RateLimits() == RateLimits(
        window_seconds=900,
        login_account=5,
        login_ip=20,
        refresh_ip=30,
        validate_ip=10,
        accept_ip=10,
    )


# --- Por IP, por endpoint ------------------------------------------------------------


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_each_endpoint_blocks_an_ip_after_its_threshold(client, db, endpoint):
    ambito, limit = IP_LIMITS[endpoint]
    exhaust(client, endpoint, IP_A)
    assert total(db, ambito) == limit

    assert_rate_limited(attempt(client, endpoint, IP_A))


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_the_counter_of_one_ip_does_not_raise_another_ip(client, db, endpoint):
    exhaust(client, endpoint, IP_A)
    assert_rate_limited(attempt(client, endpoint, IP_A))

    response = attempt(client, endpoint, IP_B)
    assert response.status_code != 429


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_counters_are_separate_per_endpoint(client, endpoint):
    exhaust(client, endpoint, IP_A)
    assert_rate_limited(attempt(client, endpoint, IP_A))

    for other in ENDPOINTS:
        if other != endpoint:
            assert attempt(client, other, IP_A).status_code != 429, (endpoint, other)


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_a_limited_request_does_not_reach_argon2_nor_the_database(
    client, hasher_spy, monkeypatch, endpoint
):
    exhaust(client, endpoint, IP_A)
    called = []
    for name in ("login", "refresh"):
        monkeypatch.setattr(service, name, lambda *a, _n=name, **k: called.append(_n))
    for name in ("is_valid_invitation", "accept_invitation"):
        monkeypatch.setattr(invitaciones_service, name, lambda *a, _n=name, **k: called.append(_n))
    hasher_spy.calls = 0

    assert_rate_limited(attempt(client, endpoint, IP_A))

    assert hasher_spy.calls == 0
    assert called == []


# --- Por cuenta (login) ----------------------------------------------------------------


def test_login_blocks_an_account_from_any_ip(client, db):
    ips = [f"203.0.113.{n}" for n in range(1, LIMITS.login_account + 2)]
    for ip in ips[:-1]:
        assert attempt(client, "login", ip, subject=ADMIN_A.email).status_code == 401
    assert total(db, "login_cuenta") == LIMITS.login_account

    assert_rate_limited(attempt(client, "login", ips[-1], subject=ADMIN_A.email))
    # Otra cuenta desde la misma IP sigue intentando.
    assert attempt(client, "login", ips[-1], subject=ADMIN_B.email).status_code == 401


def test_the_blocked_account_gets_429_even_with_the_right_password(client):
    for n in range(LIMITS.login_account):
        attempt(client, "login", f"203.0.113.{n + 1}", subject=ADMIN_A.email)

    response = client.post(
        "/auth/login",
        json={"email": ADMIN_A.email, "password": PASSWORD},
        environ_base=env("203.0.113.99"),
    )

    assert_rate_limited(response)
    raw = response.get_data(as_text=True)
    # Nada de la cuenta bloqueada sale en la respuesta.
    assert ADMIN_A.email not in raw
    assert str(ADMIN_A.usuario_id) not in raw


def _account_429(client, email: str):
    for n in range(LIMITS.login_account):
        assert attempt(client, "login", f"203.0.113.{n + 1}", subject=email).status_code == 401
    return attempt(client, "login", "203.0.113.200", subject=email)


def test_429_is_identical_for_existing_and_missing_accounts(client, db, hasher_spy):
    existing_calls_before = hasher_spy.calls
    existing = _account_429(client, ADMIN_A.email)
    existing_calls = hasher_spy.calls - existing_calls_before
    purge_all(db)
    missing_calls_before = hasher_spy.calls
    missing = _account_429(client, nobody())
    missing_calls = hasher_spy.calls - missing_calls_before

    assert_rate_limited(existing)
    assert_rate_limited(missing)
    assert error_of(existing) == error_of(missing)
    assert stable_headers(existing) == stable_headers(missing)
    # Una verificación por intento fallido y ninguna en el 429, exista o no la cuenta.
    assert existing_calls == missing_calls == LIMITS.login_account


def test_missing_accounts_count_like_existing_ones(client, db):
    email = nobody()
    for n in range(LIMITS.login_account):
        attempt(client, "login", f"203.0.113.{n + 1}", subject=email)
    rows = [row for row in counters(db) if row["ambito"] == "login_cuenta"]
    assert [row["intentos"] for row in rows] == [LIMITS.login_account]


def test_account_key_uses_the_normalized_email(client, db):
    variants = [ADMIN_A.email, ADMIN_A.email.upper(), f"  {ADMIN_A.email}\t"]
    for n, email in enumerate(variants):
        attempt(client, "login", f"203.0.113.{n + 1}", subject=email)
    rows = [row for row in counters(db) if row["ambito"] == "login_cuenta"]
    assert [row["intentos"] for row in rows] == [len(variants)]


UNNORMALIZABLE = ["", "   ", "a\x00b@ejemplo.test", "\ud800@ejemplo.test", "Ᲊ@ejemplo.test"]


def test_unnormalizable_emails_share_one_fixed_bucket(client, db):
    for n, email in enumerate(UNNORMALIZABLE[: LIMITS.login_account]):
        assert attempt(client, "login", f"203.0.113.{n + 1}", subject=email).status_code == 401
    rows = [row for row in counters(db) if row["ambito"] == "login_cuenta"]
    assert len(rows) == 1

    blocked = attempt(client, "login", "203.0.113.100", subject=UNNORMALIZABLE[-1])
    assert_rate_limited(blocked)
    # Una cuenta real no comparte ese cubo.
    assert attempt(client, "login", "203.0.113.101", subject=ADMIN_A.email).status_code == 401


def test_keys_are_hmacs_never_ip_or_email_in_clear(limits_app):
    secret = SECRET_KEY
    ip_key = limits.ip_key(secret, IP_A)
    account_key = limits.account_key(secret, ADMIN_A.email)

    assert len(ip_key) == len(account_key) == 32
    assert ip_key != hashlib.sha256(IP_A.encode()).digest()
    assert account_key != hashlib.sha256(ADMIN_A.email.encode()).digest()
    # La clave depende de SECRET_KEY y de un contexto propio por tipo.
    assert ip_key != limits.ip_key(secret + "x", IP_A)
    assert account_key != limits.account_key(secret + "x", ADMIN_A.email)
    expected = hmac.new(
        derive_key(secret, limits.ACCOUNT_KEY_CONTEXT),
        b"\x00" + ADMIN_A.email.encode(),
        hashlib.sha256,
    ).digest()
    assert account_key == expected
    assert limits.IP_KEY_CONTEXT != limits.ACCOUNT_KEY_CONTEXT


def test_unnormalizable_account_keys_are_one_bucket_distinct_from_real_ones():
    keys = {limits.account_key(SECRET_KEY, email) for email in UNNORMALIZABLE}
    assert len(keys) == 1
    assert keys.isdisjoint({limits.account_key(SECRET_KEY, ADMIN_A.email)})


def test_the_table_stores_no_ip_nor_email_in_clear(client, db):
    attempt(client, "login", IP_A, subject=ADMIN_A.email)
    attempt(client, "validar", IP_A)
    with db.migrator.connect() as conn:
        dump = conn.scalar(text("select string_agg(t::text, '|') from limite_tasa t"))
    assert IP_A not in dump
    assert ADMIN_A.email not in dump
    assert ADMIN_A.email.encode().hex() not in dump
    assert IP_A.encode().hex() not in dump


# --- Solo los fallos de login y refresh ------------------------------------------------


def test_a_successful_login_gives_its_attempt_back(client, db):
    for _ in range(LIMITS.login_account + 2):
        response = client.post(
            "/auth/login",
            json={"email": ADMIN_A.email, "password": PASSWORD},
            environ_base=env(IP_A),
        )
        assert response.status_code == 200
    assert total(db, "login_cuenta") == 0
    assert total(db, "login_ip") == 0


def _cookie_of(response) -> str:
    for header in response.headers.getlist("Set-Cookie"):
        name, _, rest = header.partition("=")
        if name == SECURE_NAME:
            return rest.split(";", 1)[0]
    raise AssertionError("sin cookie de refresh")


def test_a_successful_refresh_gives_its_attempt_back(client, db):
    response = client.post(
        "/auth/login", json={"email": ADMIN_A.email, "password": PASSWORD}, environ_base=env(IP_A)
    )
    cookie = _cookie_of(response)
    for _ in range(LIMITS.refresh_ip + 2):
        response = client.post(
            "/auth/refresh",
            headers={**CSRF, "Cookie": f"{SECURE_NAME}={cookie}"},
            environ_base=env(IP_A),
        )
        assert response.status_code == 200
        cookie = _cookie_of(response)
    assert total(db, "refresh_ip") == 0

    # Los 401 sí cuentan.
    exhaust(client, "refresh", IP_A)
    assert_rate_limited(attempt(client, "refresh", IP_A))


def test_logout_is_not_rate_limited_nor_counted(client, db):
    for _ in range(LIMITS.refresh_ip + 2):
        response = client.post(
            "/auth/logout",
            headers={**CSRF, "Cookie": f"{SECURE_NAME}={uuid.uuid4()}.{uuid.uuid4().hex}"},
            environ_base=env(IP_A),
        )
        assert response.status_code == 204
    assert counters(db) == []


def test_validar_counts_every_request(client, db):
    for _ in range(LIMITS.validate_ip):
        response = attempt(client, "validar", IP_A)
        assert response.status_code == 200
    assert total(db, "validar_ip") == LIMITS.validate_ip


def test_aceptar_counts_before_argon2_but_not_password_policy_errors(client, db, hasher_spy):
    response = client.post(
        "/invitaciones/aceptar",
        json={"token": "x", "nombre": "Nadie", "password": "corta"},
        environ_base=env(IP_A),
    )
    assert response.status_code == 400
    assert total(db, "aceptar_ip") == 0
    assert hasher_spy.calls == 0

    attempt(client, "aceptar", IP_A)
    assert total(db, "aceptar_ip") == 1
    assert hasher_spy.calls == 1


def test_malformed_bodies_are_not_counted(client, db):
    for path in ("/auth/login", "/invitaciones/validar", "/invitaciones/aceptar"):
        response = client.post(path, data="no-json", environ_base=env(IP_A))
        assert response.status_code == 400
    assert counters(db) == []


# --- Transacción propia y atomicidad ------------------------------------------------------


def test_the_counter_survives_a_failed_request(client, db, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("fallo sintético después del contador")

    monkeypatch.setattr(service, "login", boom)
    monkeypatch.setattr(invitaciones_service, "accept_invitation", boom)

    assert attempt(client, "login", IP_A, subject=ADMIN_A.email).status_code == 500
    assert attempt(client, "aceptar", IP_A).status_code == 500

    assert total(db, "login_ip") == 1
    assert total(db, "login_cuenta") == 1
    assert total(db, "aceptar_ip") == 1


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_parallel_requests_never_exceed_the_threshold(limits_app, db, hasher_spy, endpoint):
    _, limit = IP_LIMITS[endpoint]
    workers = limit * 3
    barrier = threading.Barrier(workers)
    statuses: list[int] = []
    lock = threading.Lock()

    def worker() -> None:
        local_client = limits_app.test_client(use_cookies=False)
        barrier.wait()
        response = attempt(local_client, endpoint, IP_A, subject=ADMIN_A.email)
        with lock:
            statuses.append(response.status_code)

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads)

    allowed = limit if endpoint != "login" else min(limit, LIMITS.login_account)
    assert len(statuses) == workers
    assert statuses.count(429) == workers - allowed, statuses
    if endpoint in ("login", "aceptar"):
        assert hasher_spy.calls == allowed


def test_increment_is_a_single_atomic_upsert(limits_app):
    with limits_app.app_context():
        key = limits.ip_key(SECRET_KEY, "192.0.2.77")
        first = limits.increment_attempts([("validar_ip", key, 100)], 900)
        second = limits.increment_attempts([("validar_ip", key, 100)], 900)
    assert [c.intentos for c in first] == [1]
    assert [c.intentos for c in second] == [2]
    assert first[0].ventana_inicio == second[0].ventana_inicio
    assert first[0].ventana_inicio.timestamp() % 900 == 0


# --- Falla cerrado ------------------------------------------------------------------------


@pytest.mark.parametrize("error", ["operational", "programming", "unexpected"])
@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_the_limiter_fails_closed(client, hasher_spy, monkeypatch, endpoint, error):
    def broken(*args, **kwargs):
        if error == "operational":
            raise OperationalError("select", {}, Exception("sin base"))
        if error == "programming":
            raise DBAPIError("insert", {}, Exception("permiso denegado"))
        raise RuntimeError("inesperado")

    called = []
    monkeypatch.setattr(limits, "increment_attempts", broken)
    monkeypatch.setattr(service, "login", lambda *a, **k: called.append("login"))
    monkeypatch.setattr(service, "refresh", lambda *a, **k: called.append("refresh"))

    response = attempt(client, endpoint, IP_A, subject=ADMIN_A.email)

    assert response.status_code == 503
    assert error_of(response) == {
        "code": "servicio_no_disponible",
        "message": "El servicio no está disponible en este momento. Intenta de nuevo en unos "
        "segundos.",
    }
    assert response.headers["Retry-After"] == "10"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert hasher_spy.calls == 0
    assert called == []


def test_a_real_database_failure_fails_closed(db, hasher_spy):
    # Base sin la tabla: el rol de la aplicación no puede contar -> 503, sin Argon2.
    broken = build_app(db)
    try:
        with db.migrator.begin() as conn:
            conn.execute(text("alter table limite_tasa rename to limite_tasa_fuera"))
        try:
            response = attempt(broken.test_client(), "login", IP_A, subject=ADMIN_A.email)
        finally:
            with db.migrator.begin() as conn:
                conn.execute(text("alter table limite_tasa_fuera rename to limite_tasa"))
    finally:
        dispose(broken)
    assert response.status_code == 503
    assert error_of(response)["code"] == "servicio_no_disponible"


# --- IP del cliente y proxy de confianza ------------------------------------------------


def test_without_trusted_proxy_x_forwarded_for_is_ignored(client):
    for n in range(LIMITS.login_ip):
        headers = {"X-Forwarded-For": f"203.0.113.{n + 1}"}
        assert attempt(client, "login", IP_A, headers=headers).status_code == 401
    assert_rate_limited(attempt(client, "login", IP_A, headers={"X-Forwarded-For": "192.0.2.250"}))


@pytest.fixture
def proxied_app(db) -> Iterator[Flask]:
    flask_app = build_app(db, trusted_proxy_hops=1)
    yield flask_app
    dispose(flask_app)


PROXY = "10.0.0.2"


def test_with_one_trusted_hop_a_forged_x_forwarded_for_does_not_evade(proxied_app):
    client = proxied_app.test_client(use_cookies=False)
    for n in range(LIMITS.login_ip):
        # El cliente real (IP_A) antepone una IP falsa distinta cada vez; el proxy añade IP_A.
        headers = {"X-Forwarded-For": f"203.0.113.{n + 1}, {IP_A}"}
        assert attempt(client, "login", PROXY, headers=headers).status_code == 401
    forged = {"X-Forwarded-For": f"198.51.100.250, {IP_A}"}
    assert_rate_limited(attempt(client, "login", PROXY, headers=forged))
    # Otro cliente detrás del mismo proxy no está bloqueado.
    other = {"X-Forwarded-For": IP_B}
    assert attempt(client, "login", PROXY, headers=other).status_code == 401


def test_trusted_proxy_without_x_forwarded_for_uses_the_peer(proxied_app):
    client = proxied_app.test_client(use_cookies=False)
    for _ in range(LIMITS.login_ip):
        assert attempt(client, "login", PROXY).status_code == 401
    assert_rate_limited(attempt(client, "login", PROXY))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("192.0.2.10", "192.0.2.10"),
        (" 192.0.2.10 ", "192.0.2.10"),
        ("2001:db8:1:2:aaaa::1", "2001:db8:1:2::/64"),
        ("2001:db8:1:2:ffff:ffff:ffff:ffff", "2001:db8:1:2::/64"),
        ("2001:DB8:1:2::7", "2001:db8:1:2::/64"),
        ("fe80::1%eth0", "fe80::/64"),
        ("::ffff:192.0.2.10", "192.0.2.10"),
        (None, limits.UNKNOWN_ADDRESS),
        ("", limits.UNKNOWN_ADDRESS),
        ("no-es-una-ip", limits.UNKNOWN_ADDRESS),
        ("192.0.2.10, 198.51.100.1", limits.UNKNOWN_ADDRESS),
    ],
)
def test_client_address_groups_ipv6_by_64(raw, expected):
    assert limits.client_address(raw) == expected


def test_ipv6_addresses_of_one_64_share_the_counter(client):
    for n in range(LIMITS.login_ip):
        assert attempt(client, "login", f"2001:db8:5:6::{n + 1:x}").status_code == 401
    assert_rate_limited(attempt(client, "login", "2001:db8:5:6:ffff::1"))
    assert attempt(client, "login", "2001:db8:5:7::1").status_code == 401


# --- Privilegios de la aplicación sobre limite_tasa ----------------------------------------


@pytest.fixture
def app_conn(db):
    engine = create_engine(db.app_url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            yield connection
    finally:
        engine.dispose()


def _seed_counter(app_conn) -> None:
    key = limits.ip_key(SECRET_KEY, "192.0.2.55")
    app_conn.execute(
        text(
            "insert into limite_tasa (ambito, clave_hash, ventana_inicio, intentos) "
            "values ('validar_ip', :k, now(), 1)"
        ),
        {"k": key},
    )
    app_conn.commit()


@pytest.mark.parametrize(
    "sql",
    [
        "delete from limite_tasa",
        "truncate limite_tasa",
        "update limite_tasa set ambito = 'login_ip'",
        "update limite_tasa set clave_hash = clave_hash",
        "update limite_tasa set ventana_inicio = now()",
    ],
)
def test_the_app_cannot_delete_truncate_or_rewrite_counters(app_conn, db, sql):
    _seed_counter(app_conn)
    with pytest.raises(DBAPIError) as excinfo:
        app_conn.execute(text(sql))
    app_conn.rollback()
    assert excinfo.value.orig.sqlstate == "42501"
    assert len(counters(db)) == 1


@pytest.mark.parametrize(
    "sql",
    [
        "insert into limite_tasa values ('validar_ip', :k, now(), 0)",
        "insert into limite_tasa values ('validar_ip', :k, now(), 50)",
        "update limite_tasa set intentos = -1",
    ],
)
def test_the_app_cannot_forge_counters(app_conn, db, sql):
    _seed_counter(app_conn)
    with pytest.raises(DBAPIError) as excinfo:
        app_conn.execute(text(sql), {"k": limits.ip_key(SECRET_KEY, "192.0.2.56")})
    app_conn.rollback()
    # Política WITH CHECK (42501) o CHECK de la tabla (23514).
    assert excinfo.value.orig.sqlstate in ("42501", "23514")
    assert [row["intentos"] for row in counters(db)] == [1]


def test_the_app_reads_only_hashes_and_counters(app_conn):
    # docs/03 (cambio 6) y A13: SELECT de la tabla, necesario para ON CONFLICT y RETURNING.
    _seed_counter(app_conn)
    columns = list(app_conn.execute(text("select * from limite_tasa")).keys())
    assert columns == ["ambito", "clave_hash", "ventana_inicio", "intentos"]


def test_an_unknown_scope_is_rejected_by_the_table(app_conn):
    with pytest.raises(DBAPIError) as excinfo:
        app_conn.execute(
            text("insert into limite_tasa values ('otro', :k, now(), 1)"),
            {"k": limits.ip_key(SECRET_KEY, "192.0.2.57")},
        )
    app_conn.rollback()
    assert excinfo.value.orig.sqlstate == "23514"


# --- Semáforo de Argon2 ----------------------------------------------------------------


@pytest.mark.parametrize("endpoint", ["login", "aceptar"])
def test_saturated_argon2_answers_503(db, endpoint):
    busy = build_app(db, argon2_max_concurrency=1)
    try:
        with busy.app_context():
            passwords = get_passwords()
        passwords._wait_seconds = 0
        assert passwords._slots.acquire(blocking=False)
        try:
            response = attempt(busy.test_client(), endpoint, IP_A, subject=ADMIN_A.email)
        finally:
            passwords._slots.release()
        assert response.status_code == 503
        assert error_of(response)["code"] == "servicio_no_disponible"
        assert response.headers["Retry-After"] == "10"
        assert response.headers["Cache-Control"] == "no-store"

        # Con el cupo libre vuelve a responder normal.
        after = attempt(busy.test_client(), endpoint, IP_B, subject=ADMIN_A.email)
        assert after.status_code in (400, 401)
    finally:
        dispose(busy)


# --- Purga: comando del operador con el rol migrador (Q10, R5) ----------------------------


def _insert_window(db: AccesoDb, address: str, age: str) -> None:
    with db.migrator.begin() as conn:
        conn.execute(
            text(
                "insert into limite_tasa (ambito, clave_hash, ventana_inicio, intentos) "
                "values ('validar_ip', :k, now() - cast(:age as interval), 3)"
            ),
            {"k": limits.ip_key(SECRET_KEY, address), "age": age},
        )


def _purge(limits_app, monkeypatch, migration_url, database_url=None):
    monkeypatch.setenv(
        "MIGRATION_DATABASE_URL", migration_url.render_as_string(hide_password=False)
    )
    if database_url is None:
        monkeypatch.delenv("DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("DATABASE_URL", database_url.render_as_string(hide_password=False))
    return limits_app.test_cli_runner().invoke(args=["purgar-limite-tasa"])


def test_purge_deletes_only_windows_older_than_a_day(limits_app, db, monkeypatch):
    _insert_window(db, "192.0.2.1", "2 days")
    _insert_window(db, "192.0.2.2", "25 hours")
    _insert_window(db, "192.0.2.3", "23 hours")
    _insert_window(db, "192.0.2.4", "0 seconds")

    result = _purge(limits_app, monkeypatch, db.migrator.url, db.app_url)

    assert result.exit_code == 0, result.output
    assert "2" in result.output
    remaining = {row["clave_hash"] for row in counters(db)}
    assert remaining == {
        limits.ip_key(SECRET_KEY, "192.0.2.3"),
        limits.ip_key(SECRET_KEY, "192.0.2.4"),
    }


def test_purge_refuses_the_app_role_as_migrator(limits_app, db, monkeypatch):
    _insert_window(db, "192.0.2.1", "2 days")

    result = _purge(limits_app, monkeypatch, db.app_url, db.app_url)

    assert result.exit_code != 0
    assert "MIGRATION_DATABASE_URL" in result.output
    assert len(counters(db)) == 1


def test_purge_with_the_app_role_cannot_delete(limits_app, db, monkeypatch):
    # Aunque nadie compare roles (sin DATABASE_URL), la base niega el DELETE a la app.
    _insert_window(db, "192.0.2.1", "2 days")

    result = _purge(limits_app, monkeypatch, db.app_url)

    assert result.exit_code != 0
    assert "42501" in result.output
    assert db.app_url.password not in result.output
    assert len(counters(db)) == 1


def test_purge_requires_the_migration_url(limits_app, db, monkeypatch):
    monkeypatch.delenv("MIGRATION_DATABASE_URL", raising=False)
    result = limits_app.test_cli_runner().invoke(args=["purgar-limite-tasa"])
    assert result.exit_code != 0
    assert "MIGRATION_DATABASE_URL" in result.output


def test_purge_takes_no_credentials_in_argv(limits_app):
    result = limits_app.test_cli_runner().invoke(
        args=["purgar-limite-tasa", "--url", "postgresql://x"]
    )
    assert result.exit_code != 0


# --- Purga bajo FORCE RLS con un migrador sin superusuario (Q5, Q10) ----------------------
#
# En local y CI el migrador es superusuario y se salta la RLS: las pruebas de arriba no
# ejercen las políticas ``limite_tasa_purga`` y ``limite_tasa_purga_leer``. En producción
# el migrador es el ``current_user`` que ejecuta 0005 y por eso el **dueño** de la tabla
# (las políticas van ``TO`` él). Aquí se reproduce eso: un rol temporal NOSUPERUSER
# NOBYPASSRLS ejecuta el ``upgrade`` real de 0005 en un esquema propio (``SET LOCAL ROLE``
# desde el migrador de la fixture) y queda como dueño bajo FORCE RLS. Rol y esquema viven
# en una transacción que siempre se revierte: no quedan residuos (guardián de la sesión).

MIGRATION_0005 = (
    Path(__file__).resolve().parents[1] / "migrations" / "versions" / "0005_limite_tasa.py"
)
OLD_WINDOWS = {"192.0.2.1": "2 days", "192.0.2.2": "25 hours"}
YOUNG_WINDOWS = {"192.0.2.3": "23 hours", "192.0.2.4": "0 seconds"}


def _load_migration_0005():
    spec = importlib.util.spec_from_file_location("migration_0005_under_test", MIGRATION_0005)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@dataclass(frozen=True)
class PurgeRoles:
    conn: Connection
    migrator: str  # citado; dueño de la tabla, sin superusuario ni BYPASSRLS
    app: str  # citado; rol de la aplicación


@pytest.fixture
def owner_migrator(db, monkeypatch) -> Iterator[PurgeRoles]:
    suffix = uuid.uuid4().hex[:12]
    with db.migrator.connect() as conn:
        tx = conn.begin()
        try:
            if not conn.scalar(text("select rolsuper from pg_roles where rolname = current_user")):
                pytest.fail(
                    "bloqueado: el rol de TEST_MIGRATION_DATABASE_URL debe ser superusuario "
                    "para crear el migrador de prueba",
                    pytrace=False,
                )
            quote = conn.dialect.identifier_preparer.quote
            role, schema = f"prueba_migrador_{suffix}", f"prueba_purga_{suffix}"
            migrator, app = quote(role), quote(db.app_url.username)
            conn.exec_driver_sql(
                f"CREATE ROLE {migrator} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB "
                "NOCREATEROLE NOREPLICATION NOINHERIT"
            )
            conn.exec_driver_sql(f"CREATE SCHEMA {quote(schema)} AUTHORIZATION {migrator}")
            conn.exec_driver_sql(f"SET LOCAL search_path TO {quote(schema)}")
            conn.exec_driver_sql(f"SET LOCAL ROLE {migrator}")

            migration = _load_migration_0005()
            monkeypatch.setenv("APP_DB_USER", db.app_url.username)
            monkeypatch.setattr(migration, "op", SimpleNamespace(get_bind=lambda: conn))
            migration.upgrade()
            conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA {quote(schema)} TO {app}")

            facts = conn.execute(
                text(
                    "select pg_get_userbyid(c.relowner), c.relforcerowsecurity, "
                    "r.rolsuper or r.rolbypassrls from pg_class c "
                    "join pg_roles r on r.oid = c.relowner "
                    "where c.oid = 'limite_tasa'::regclass"
                )
            ).one()
            assert tuple(facts) == (role, True, False)

            conn.exec_driver_sql("RESET ROLE")
            for address, age in {**OLD_WINDOWS, **YOUNG_WINDOWS}.items():
                conn.execute(
                    text(
                        "insert into limite_tasa (ambito, clave_hash, ventana_inicio, intentos) "
                        "values ('validar_ip', :k, now() - cast(:age as interval), 3)"
                    ),
                    {"k": limits.ip_key(SECRET_KEY, address), "age": age},
                )
            yield PurgeRoles(conn=conn, migrator=migrator, app=app)
        finally:
            tx.rollback()


def _keys(addresses) -> set[bytes]:
    return {limits.ip_key(SECRET_KEY, address) for address in addresses}


def _remaining(roles: PurgeRoles) -> set[bytes]:
    # El migrador de la fixture (superusuario) ve todas las filas.
    roles.conn.exec_driver_sql("RESET ROLE")
    return set(roles.conn.scalars(text("select clave_hash from limite_tasa")))


def _as(roles: PurgeRoles, role: str) -> None:
    roles.conn.exec_driver_sql(f"SET LOCAL ROLE {role}")


def test_owner_migrator_only_sees_windows_older_than_a_day(owner_migrator):
    _as(owner_migrator, owner_migrator.migrator)
    visible = set(owner_migrator.conn.scalars(text("select clave_hash from limite_tasa")))
    assert visible == _keys(OLD_WINDOWS)


def test_policy_never_lets_the_owner_migrator_delete_a_young_window(owner_migrator):
    # Sin WHERE: lo único que frena el borrado de una ventana vigente es la política.
    _as(owner_migrator, owner_migrator.migrator)
    deleted = owner_migrator.conn.execute(text("delete from limite_tasa")).rowcount
    assert deleted == len(OLD_WINDOWS)
    assert _remaining(owner_migrator) == _keys(YOUNG_WINDOWS)


def test_purge_statement_of_the_cli_deletes_old_windows_under_force_rls(owner_migrator):
    _as(owner_migrator, owner_migrator.migrator)
    deleted = owner_migrator.conn.execute(cli._PURGAR_LIMITE_TASA).rowcount
    assert deleted == len(OLD_WINDOWS)
    assert _remaining(owner_migrator) == _keys(YOUNG_WINDOWS)


@pytest.mark.parametrize("policy", ["limite_tasa_purga_leer", "limite_tasa_purga"])
def test_without_either_purge_policy_the_owner_migrator_deletes_nothing(owner_migrator, policy):
    # El DELETE del CLI lleva WHERE: necesita también la política de SELECT (Q5).
    owner_migrator.conn.exec_driver_sql(f"DROP POLICY {policy} ON limite_tasa")
    _as(owner_migrator, owner_migrator.migrator)
    assert owner_migrator.conn.execute(cli._PURGAR_LIMITE_TASA).rowcount == 0
    assert _remaining(owner_migrator) == _keys({**OLD_WINDOWS, **YOUNG_WINDOWS})


@pytest.mark.parametrize(
    "statement",
    [cli._PURGAR_LIMITE_TASA, text("delete from limite_tasa"), text("truncate limite_tasa")],
)
def test_app_role_cannot_purge_under_the_purge_policies(owner_migrator, statement):
    nested = owner_migrator.conn.begin_nested()
    _as(owner_migrator, owner_migrator.app)
    with pytest.raises(DBAPIError) as excinfo:
        owner_migrator.conn.execute(statement)
    nested.rollback()
    assert excinfo.value.orig.sqlstate == "42501"
    assert _remaining(owner_migrator) == _keys({**OLD_WINDOWS, **YOUNG_WINDOWS})
