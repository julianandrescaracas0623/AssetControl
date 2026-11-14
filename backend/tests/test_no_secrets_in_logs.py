"""Secretos fuera de los logs en todo el flujo de acceso (spec 002, T10; R14, A14).

Recorre, con los loggers de la app y de SQLAlchemy en ``DEBUG`` (antes y después de
crear la app, y con ``echo="debug"``), el ciclo completo: crear invitación, validar,
aceptar, login correcto y fallido, refresh, logout, ``429`` por límite de tasa y el
``503`` de falla cerrada. Ni ``caplog`` ni la salida del proceso (``capfd``) pueden
contener contraseñas, tokens (invitación, acceso, refresh), claves ``sha256``, hashes
guardados (``token_hash``, Argon2), emails, IPs ni las claves HMAC de ``limite_tasa``.

Datos sintéticos (``@ejemplo.test``): nunca datos de la clínica.
"""

import logging
from collections.abc import Iterator
from http.cookies import SimpleCookie

import pytest
from acceso_db import (
    ADMIN_A,
    PASSWORD,
    SECRET_KEY,
    TENANT_A,
    AccesoDb,
    bearer,
    temporary_acceso_db,
)
from flask import Flask
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app import create_app
from app.auth import limits
from app.auth.credentials import token_key, token_storage_hash
from app.auth.http import CSRF_HEADER, CSRF_HEADER_VALUE
from app.config import Config, RateLimits

CSRF = {CSRF_HEADER: CSRF_HEADER_VALUE}
SECURE_NAME = "__Secure-refresh"
INVITED = "invitada.logs@ejemplo.test"
NEW_PASSWORD = "Clave-Nueva-Logs-2026"
WRONG_PASSWORD = "Clave-Mala-Logs-2026"
IP = "203.0.113.77"
IPV6 = "2001:db8:77:1::5"
SQLALCHEMY_LOGGERS = ("sqlalchemy.engine", "sqlalchemy.engine.Engine", "sqlalchemy.pool")
LIMITS = RateLimits(
    window_seconds=900, login_account=2, login_ip=50, refresh_ip=50, validate_ip=3, accept_ip=50
)


@pytest.fixture(scope="module")
def db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("logs")


@pytest.fixture
def sqlalchemy_debug():
    """SQLAlchemy en DEBUG antes de crear la app; restaura nivel, filtros y manejadores."""
    saved = {}
    for name in SQLALCHEMY_LOGGERS:
        logger = logging.getLogger(name)
        saved[name] = (logger.level, list(logger.filters), list(logger.handlers))
    for name in ("sqlalchemy.engine", "sqlalchemy.pool"):
        logging.getLogger(name).setLevel(logging.DEBUG)
    yield
    for name, (level, filters, handlers) in saved.items():
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.filters[:] = filters
        for handler in logger.handlers[:]:
            if handler not in handlers:
                logger.removeHandler(handler)


def build_app(db: AccesoDb) -> Flask:
    return create_app(
        Config(
            database_url=db.app_url.render_as_string(hide_password=False),
            secret_key=SECRET_KEY,
            environment="test",
            rate_limits=LIMITS,
        )
    )


def cookie_value(response) -> str:
    for header in response.headers.getlist("Set-Cookie"):
        parsed = SimpleCookie()
        parsed.load(header)
        if SECURE_NAME in parsed:
            return parsed[SECURE_NAME].value
    raise AssertionError("sin cookie de refresh")


def run_flow(flask_app: Flask, monkeypatch) -> list[str]:
    """El ciclo completo; devuelve los secretos que no deben aparecer."""
    client = flask_app.test_client(use_cookies=False)
    environ = {"REMOTE_ADDR": IP}

    created = client.post(
        "/invitaciones",
        json={"email": INVITED, "rol": "contador"},
        headers=bearer(ADMIN_A, TENANT_A),
        environ_base=environ,
    )
    assert created.status_code == 201, created.get_json()
    token = created.get_json()["enlace"].split("#", 1)[1]

    assert client.post(
        "/invitaciones/validar", json={"token": token}, environ_base=environ
    ).get_json() == {"vigente": True}
    accepted = client.post(
        "/invitaciones/aceptar",
        json={"token": token, "nombre": "Invitada", "password": NEW_PASSWORD},
        environ_base=environ,
    )
    assert accepted.status_code == 201, accepted.get_json()
    accept_cookie = cookie_value(accepted)

    ok = client.post(
        "/auth/login", json={"email": ADMIN_A.email, "password": PASSWORD}, environ_base=environ
    )
    assert ok.status_code == 200
    login_cookie = cookie_value(ok)
    access = ok.get_json()["access_token"]
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {access}"}).status_code == 200

    rotated = client.post(
        "/auth/refresh",
        headers={**CSRF, "Cookie": f"{SECURE_NAME}={login_cookie}"},
        environ_base=environ,
    )
    assert rotated.status_code == 200
    rotated_cookie = cookie_value(rotated)
    assert (
        client.post(
            "/auth/logout",
            headers={**CSRF, "Cookie": f"{SECURE_NAME}={rotated_cookie}"},
            environ_base=environ,
        ).status_code
        == 204
    )

    # Fallos hasta el 429 por cuenta (login) y por IP (validar), también desde IPv6.
    statuses = [
        client.post(
            "/auth/login",
            json={"email": INVITED, "password": WRONG_PASSWORD},
            environ_base={"REMOTE_ADDR": IPV6},
        ).status_code
        for _ in range(LIMITS.login_account + 1)
    ]
    assert statuses[-1] == 429
    statuses = [
        client.post(
            "/invitaciones/validar", json={"token": token}, environ_base={"REMOTE_ADDR": IPV6}
        ).status_code
        for _ in range(LIMITS.validate_ip + 1)
    ]
    assert statuses[-1] == 429

    # Falla cerrada: el error de base se registra sin detalles.
    def broken(*args, **kwargs):
        raise OperationalError(
            f"insert -- {INVITED} {IP}", {"clave": b"x"}, Exception(f"sin base {INVITED}")
        )

    with monkeypatch.context() as patched:
        patched.setattr(limits, "increment_attempts", broken)
        failed = client.post(
            "/auth/login", json={"email": INVITED, "password": NEW_PASSWORD}, environ_base=environ
        )
    assert failed.status_code == 503

    secrets = []
    for value in (
        token,
        *(c.split(".", 1)[1] for c in (accept_cookie, login_cookie, rotated_cookie)),
    ):
        secrets += [value, token_key(value), token_storage_hash(value).hex()]
    secrets += [
        "$argon2",
        PASSWORD,
        NEW_PASSWORD,
        WRONG_PASSWORD,
        access,
        accepted.get_json()["access_token"],
        ADMIN_A.email,
        INVITED,
        IP,
        IPV6,
        "2001:db8:77:1::/64",
        SECRET_KEY,
    ]
    for address in (IP, "2001:db8:77:1::/64"):
        secrets.append(limits.ip_key(SECRET_KEY, address).hex())
    for email in (ADMIN_A.email, INVITED):
        secrets.append(limits.account_key(SECRET_KEY, email).hex())
    return secrets


@pytest.fixture(autouse=True)
def clean_state(db) -> Iterator[None]:
    """Deja la base como estaba: sin contadores ni la cuenta invitada."""
    yield
    with db.migrator.begin() as conn:
        conn.execute(text("delete from limite_tasa"))
        conn.execute(
            text(
                "delete from refresh_token where membresia_id in (select m.id from membresia m "
                "join usuario u on u.id = m.usuario_id where u.email = :e)"
            ),
            {"e": INVITED},
        )
        conn.execute(
            text(
                "delete from membresia where usuario_id in "
                "(select id from usuario where email = :e)"
            ),
            {"e": INVITED},
        )
        conn.execute(text("delete from usuario where email = :e"), {"e": INVITED})
        conn.execute(text("delete from invitacion where email = :e"), {"e": INVITED})


def _leaks(secrets: list[str], *texts: str) -> list[str]:
    joined = "\n".join(texts)
    return [value for value in secrets if value in joined]


def test_the_whole_flow_logs_no_secrets_with_debug_before_create_app(
    db, sqlalchemy_debug, caplog, capfd, monkeypatch
):
    flask_app = build_app(db)
    try:
        with caplog.at_level(logging.DEBUG):
            secrets = run_flow(flask_app, monkeypatch)
    finally:
        flask_app.extensions["assetcontrol.db"].engine.dispose()

    out, err = capfd.readouterr()
    assert _leaks(secrets, caplog.text, out, err) == []
    assert "Row " not in caplog.text
    # La falla cerrada sí deja rastro (solo el tipo) y el 429 nombra el ámbito.
    assert "OperationalError" in caplog.text
    assert "login_cuenta" in caplog.text
    assert "validar_ip" in caplog.text


def test_the_whole_flow_logs_no_secrets_with_debug_and_echo_after_create_app(
    db, sqlalchemy_debug, caplog, capfd, monkeypatch
):
    flask_app = build_app(db)
    engine = flask_app.extensions["assetcontrol.db"].engine
    for name in ("sqlalchemy.engine", "sqlalchemy.pool"):
        logging.getLogger(name).setLevel(logging.DEBUG)
    engine.echo = "debug"
    try:
        with caplog.at_level(logging.DEBUG):
            secrets = run_flow(flask_app, monkeypatch)
    finally:
        engine.dispose()

    out, err = capfd.readouterr()
    assert _leaks(secrets, caplog.text, out, err) == []
    assert "Row " not in caplog.text + out + err
