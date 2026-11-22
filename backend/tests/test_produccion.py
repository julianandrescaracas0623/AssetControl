"""Configuración de producción (spec 010b, T2; R2, R3).

- Fuera de desarrollo y pruebas, la conexión a la base exige TLS (``sslmode=require``)
  salvo que la URL ya pida algo igual o más estricto; nunca se relaja.
- Con ``ENVIRONMENT=production`` y ``TRUSTED_PROXY_HOPS=0`` la app avisa al arrancar
  (deuda (e) de la 002): detrás del proxy de la plataforma todas las IP serían la suya.
- gunicorn: trabajadores e hilos fijos, sin recarga, en ``$PORT``.
"""

import logging
import runpy
from pathlib import Path

import pytest

from app import create_app
from app import db as db_module
from app.config import Config

LONG_SECRET = "k" * 40
URL = "postgresql+psycopg://app:secreto@db.ejemplo.test:5432/assetcontrol"


def _connect_args(monkeypatch, config: Config) -> dict:
    captured: dict = {}
    real = db_module.create_engine

    def spy(*args, **kwargs):
        captured.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(db_module, "create_engine", spy)
    create_app(config)
    return captured["connect_args"]


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_tls_is_required_outside_development(monkeypatch, environment):
    args = _connect_args(
        monkeypatch, Config(database_url=URL, secret_key=LONG_SECRET, environment=environment)
    )
    assert args["sslmode"] == "require"


@pytest.mark.parametrize("modo", ["require", "verify-ca", "verify-full"])
def test_a_stricter_mode_in_the_url_is_kept(monkeypatch, modo):
    url = f"{URL}?sslmode={modo}"
    args = _connect_args(
        monkeypatch, Config(database_url=url, secret_key=LONG_SECRET, environment="production")
    )
    assert "sslmode" not in args  # lo decide la URL


@pytest.mark.parametrize("modo", ["disable", "allow", "prefer"])
def test_a_weaker_mode_in_the_url_is_refused(modo):
    url = f"{URL}?sslmode={modo}"
    with pytest.raises(RuntimeError, match="TLS"):
        create_app(Config(database_url=url, secret_key=LONG_SECRET, environment="production"))


def test_development_does_not_force_tls(monkeypatch):
    args = _connect_args(
        monkeypatch, Config(database_url=URL, secret_key=LONG_SECRET, environment="development")
    )
    assert "sslmode" not in args


def test_production_without_proxy_hops_warns(caplog):
    with caplog.at_level(logging.WARNING):
        create_app(Config(database_url=URL, secret_key=LONG_SECRET, environment="production"))
    assert any("TRUSTED_PROXY_HOPS" in r.getMessage() for r in caplog.records)
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        create_app(
            Config(
                database_url=URL,
                secret_key=LONG_SECRET,
                environment="production",
                trusted_proxy_hops=1,
            )
        )
    assert not any("TRUSTED_PROXY_HOPS" in r.getMessage() for r in caplog.records)


def test_gunicorn_configuration(monkeypatch):
    monkeypatch.setenv("PORT", "8123")
    conf = runpy.run_path(str(Path(__file__).resolve().parents[1] / "gunicorn.conf.py"))
    assert conf["bind"] == "0.0.0.0:8123"
    assert conf["wsgi_app"] == "app.wsgi:application"
    assert conf["workers"] == 2
    assert conf["threads"] == 4
    assert conf["worker_class"] == "gthread"
    assert conf["timeout"] == 30
    assert conf["reload"] is False
    assert conf["accesslog"] == "-"
    # Sin cuerpos ni consultas en el registro de accesos (pueden llevar datos).
    assert "%(q)s" not in conf["access_log_format"]
    assert "%(U)s" in conf["access_log_format"]
