"""Configuración de límites de tasa, proxy de confianza y semáforo de Argon2 (spec 002, T10).

- Umbrales de Q10 por defecto y ajustables por entorno (``RATE_LIMIT_*``).
- ``TRUSTED_PROXY_HOPS``: sin definir, 0 (sin ``ProxyFix``: se usa ``REMOTE_ADDR`` y se
  ignora ``X-Forwarded-For``); con N, ``ProxyFix`` solo con ``x_for=N`` (no toca
  ``Host``, esquema ni puerto, que usa la comprobación de mismo sitio de T7).
- ``ARGON2_MAX_CONCURRENCY``: tope de hashes simultáneos por proceso.
- Valores no numéricos o fuera de rango fallan al arrancar, nombrando la variable y
  sin repetir el valor.
"""

import re
import threading
from pathlib import Path

import pytest
from werkzeug.middleware.proxy_fix import ProxyFix

from app import create_app
from app.auth.credentials import ARGON2_TEST_PARAMS, Passwords, get_passwords
from app.config import (
    InvalidSettingError,
    RateLimits,
    load_config,
)
from app.errors import ServiceUnavailableError

BASE_ENV = {
    "DATABASE_URL": "postgresql+psycopg://user:valor-secreto-db@db.invalid:5432/assetcontrol",
    "SECRET_KEY": "valor-secreto-clave-123",
    "ENVIRONMENT": "test",
}
SETTINGS = {
    "RATE_LIMIT_WINDOW_SECONDS": ("window_seconds", 60, 86400),
    "RATE_LIMIT_LOGIN_ACCOUNT": ("login_account", 1, 10000),
    "RATE_LIMIT_LOGIN_IP": ("login_ip", 1, 10000),
    "RATE_LIMIT_REFRESH_IP": ("refresh_ip", 1, 10000),
    "RATE_LIMIT_VALIDATE_IP": ("validate_ip", 1, 10000),
    "RATE_LIMIT_ACCEPT_IP": ("accept_ip", 1, 10000),
}


def test_defaults_without_variables():
    config = load_config(BASE_ENV)
    assert config.rate_limits == RateLimits()
    assert config.trusted_proxy_hops == 0
    assert config.argon2_max_concurrency == 4


@pytest.mark.parametrize("name", sorted(SETTINGS))
def test_thresholds_are_adjustable_by_environment(name):
    field, low, high = SETTINGS[name]
    for value in (low, high):
        config = load_config({**BASE_ENV, name: f" {value} "})
        assert getattr(config.rate_limits, field) == value


def test_proxy_hops_and_argon2_concurrency_are_read():
    config = load_config({**BASE_ENV, "TRUSTED_PROXY_HOPS": "2", "ARGON2_MAX_CONCURRENCY": "8"})
    assert config.trusted_proxy_hops == 2
    assert config.argon2_max_concurrency == 8


INVALID = ["abc", "-1", "1.5", "0x10", "١٢", "99999999999"]
RANGES = {
    **{name: (low, high) for name, (_, low, high) in SETTINGS.items()},
    "TRUSTED_PROXY_HOPS": (0, 5),
    "ARGON2_MAX_CONCURRENCY": (1, 64),
}


@pytest.mark.parametrize("name", sorted(RANGES))
@pytest.mark.parametrize("value", INVALID)
def test_invalid_values_fail_naming_the_variable_without_the_value(name, value):
    with pytest.raises(InvalidSettingError) as excinfo:
        load_config({**BASE_ENV, name: value})
    message = str(excinfo.value)
    assert name in message
    assert value not in message


@pytest.mark.parametrize("name", sorted(RANGES))
def test_out_of_range_values_fail(name):
    low, high = RANGES[name]
    for value in (low - 1, high + 1):
        if value < 0:
            continue
        with pytest.raises(InvalidSettingError):
            load_config({**BASE_ENV, name: str(value)})


def test_empty_values_use_the_default():
    config = load_config({**BASE_ENV, "TRUSTED_PROXY_HOPS": "  ", "RATE_LIMIT_LOGIN_IP": ""})
    assert config.trusted_proxy_hops == 0
    assert config.rate_limits.login_ip == RateLimits().login_ip


TUNABLE_VARS = (*SETTINGS, "TRUSTED_PROXY_HOPS", "ARGON2_MAX_CONCURRENCY")


def test_all_tunable_variables_empty_give_the_defaults():
    # Es lo que recibe la API del compose cuando .env no las define (``${VAR:-}``).
    config = load_config({**BASE_ENV, **dict.fromkeys(TUNABLE_VARS, "")})
    assert config.rate_limits == RateLimits()
    assert config.trusted_proxy_hops == 0
    assert config.argon2_max_concurrency == 4


@pytest.mark.parametrize("name", TUNABLE_VARS)
def test_compose_passes_each_tunable_variable_to_the_api(name):
    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text("utf-8")
    api = compose.split("\n  api:", 1)[1].split("\n    volumes:", 1)[0]
    environment = api.split("\n    environment:", 1)[1]

    # Opcional y sin valor literal: vacío en .env -> valor por defecto de config.py.
    assert re.search(rf"^      {name}: \$\{{{name}:-\}}\s*$", environment, re.MULTILINE)


def test_without_hops_there_is_no_proxy_fix():
    flask_app = create_app(load_config(BASE_ENV))
    assert not isinstance(flask_app.wsgi_app, ProxyFix)


def test_with_hops_proxy_fix_trusts_only_x_forwarded_for():
    flask_app = create_app(load_config({**BASE_ENV, "TRUSTED_PROXY_HOPS": "2"}))
    proxy = flask_app.wsgi_app
    assert isinstance(proxy, ProxyFix)
    assert (proxy.x_for, proxy.x_proto, proxy.x_host, proxy.x_port, proxy.x_prefix) == (
        2,
        0,
        0,
        0,
        0,
    )


def test_app_passwords_use_the_configured_concurrency():
    flask_app = create_app(load_config({**BASE_ENV, "ARGON2_MAX_CONCURRENCY": "3"}))
    with flask_app.app_context():
        passwords = get_passwords()
    assert passwords.max_concurrency == 3


# --- Semáforo de Argon2 -------------------------------------------------------------


def test_semaphore_caps_concurrent_hashes_and_raises_503_error():
    passwords = Passwords(ARGON2_TEST_PARAMS, max_concurrency=2, wait_seconds=0)
    stored = passwords.hash("Clave-Sintetica-Semaforo-1")
    assert passwords._slots.acquire(blocking=False)
    assert passwords._slots.acquire(blocking=False)
    try:
        with pytest.raises(ServiceUnavailableError):
            passwords.verify(stored, "Clave-Sintetica-Semaforo-1")
        with pytest.raises(ServiceUnavailableError):
            passwords.verify(None, "Clave-Sintetica-Semaforo-1")
        with pytest.raises(ServiceUnavailableError):
            passwords.hash("Clave-Sintetica-Semaforo-2")
    finally:
        passwords._slots.release()
        passwords._slots.release()
    assert passwords.verify(stored, "Clave-Sintetica-Semaforo-1") is True


def test_semaphore_is_released_after_errors():
    passwords = Passwords(ARGON2_TEST_PARAMS, max_concurrency=1, wait_seconds=0)
    for _ in range(3):
        assert passwords.verify("$argon2id$corrupto", "Clave-Sintetica-Semaforo-1") is False
    assert passwords._slots.acquire(blocking=False)
    passwords._slots.release()


def test_fast_rejections_do_not_take_a_slot():
    passwords = Passwords(ARGON2_TEST_PARAMS, max_concurrency=1, wait_seconds=0)
    assert passwords._slots.acquire(blocking=False)
    try:
        # Sobre el máximo o no codificable: False sin Argon2 y sin esperar cupo.
        assert passwords.verify(None, "x" * 500) is False
        assert passwords.verify(None, "\ud800") is False
    finally:
        passwords._slots.release()


def test_waiting_for_a_slot_succeeds_when_it_frees_in_time():
    passwords = Passwords(ARGON2_TEST_PARAMS, max_concurrency=1, wait_seconds=5)
    stored = passwords.hash("Clave-Sintetica-Semaforo-1")
    assert passwords._slots.acquire(blocking=False)
    timer = threading.Timer(0.2, passwords._slots.release)
    timer.start()
    try:
        assert passwords.verify(stored, "Clave-Sintetica-Semaforo-1") is True
    finally:
        timer.join()


def test_service_unavailable_error_does_not_echo_anything():
    assert "Clave" not in str(ServiceUnavailableError())
