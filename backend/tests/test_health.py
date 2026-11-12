"""Pruebas de ``GET /health`` (spec 001, R5 / A5)."""

import dataclasses
import time
import tomllib
from pathlib import Path

import pytest

import app.db as db_module
import app.meta.routes as routes_module
from app import __version__, create_app
from app.config import Config
from app.db import CONNECT_TIMEOUT_SECONDS, ping_database

# Dominio reservado .invalid: falla de resolución inmediata.
DOWN_PASSWORD = "clave-que-no-debe-salir"
DOWN_DB = f"postgresql+psycopg://usuario:{DOWN_PASSWORD}@db.invalid:5432/assetcontrol"
# Puerto cerrado en loopback: en Windows libpq no detecta el rechazo y espera el timeout.
REFUSED_DB = "postgresql+psycopg://usuario:clave@127.0.0.1:1/assetcontrol"
# Un solo intento de conexión (una dirección): el timeout más un margen para crear la app.
MAX_HEALTH_SECONDS = CONNECT_TIMEOUT_SECONDS + 2
PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def make_app(database_url: str):
    return create_app(
        Config(database_url=database_url, secret_key="clave-de-prueba", environment="test")
    )


@pytest.fixture
def up_app(app_database_url):
    return make_app(app_database_url.render_as_string(hide_password=False))


def test_version_matches_pyproject():
    with PYPROJECT.open("rb") as handle:
        expected = tomllib.load(handle)["project"]["version"]

    assert __version__ == expected


def test_health_returns_200_when_database_responds(up_app):
    response = up_app.test_client().get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "db": "ok", "version": __version__}


def test_health_returns_503_when_database_is_down():
    response = make_app(DOWN_DB).test_client().get("/health")

    assert response.status_code == 503
    assert response.get_json() == {"status": "error", "db": "error", "version": __version__}


def test_engine_receives_connect_timeout(monkeypatch):
    captured: dict = {}
    real_create_engine = db_module.create_engine

    def spy(*args, **kwargs):
        captured.update(kwargs)
        return real_create_engine(*args, **kwargs)

    monkeypatch.setattr(db_module, "create_engine", spy)
    make_app(DOWN_DB)

    assert CONNECT_TIMEOUT_SECONDS == 5
    assert captured["connect_args"]["connect_timeout"] == CONNECT_TIMEOUT_SECONDS


def test_health_answers_503_within_connect_timeout():
    started = time.monotonic()
    response = make_app(REFUSED_DB).test_client().get("/health")
    elapsed = time.monotonic() - started

    assert response.status_code == 503
    assert elapsed < MAX_HEALTH_SECONDS


def test_health_503_does_not_expose_connection_details():
    response = make_app(DOWN_DB).test_client().get("/health")
    body = response.get_data(as_text=True)

    for secret in (DOWN_PASSWORD, "db.invalid", "usuario", "assetcontrol", "psycopg"):
        assert secret not in body


def test_ping_database_reports_state(up_app):
    with up_app.app_context():
        assert ping_database() is True

    with make_app(DOWN_DB).app_context():
        assert ping_database() is False


def forbid_tenant_session(monkeypatch, app, calls: list[str]) -> None:
    """Hace que cualquier vía hacia una sesión con tenant falle y quede registrada.

    Cubre ``tenant_session`` importado en ``app.meta.routes`` o usado como
    ``app.db.tenant_session``, la fábrica de sesiones de la app y la propia
    ``_TenantSession``. Si /health la usa, la ruta lanza y responde 500.
    """

    def forbidden(*args, **kwargs):
        calls.append("tenant_session")
        raise AssertionError("/health no debe abrir una sesión con tenant")

    def forbidden_init(self, *args, **kwargs):
        calls.append("_TenantSession")
        raise AssertionError("/health no debe construir una sesión con tenant")

    monkeypatch.setattr(routes_module, "tenant_session", forbidden, raising=False)
    monkeypatch.setattr(db_module, "tenant_session", forbidden)
    monkeypatch.setattr(db_module._TenantSession, "__init__", forbidden_init)
    database = app.extensions[db_module._EXTENSION_KEY]
    monkeypatch.setitem(
        app.extensions,
        db_module._EXTENSION_KEY,
        dataclasses.replace(database, session_factory=forbidden),
    )


def test_health_does_not_use_tenant_session_when_database_is_down(monkeypatch):
    app = make_app(DOWN_DB)
    calls: list[str] = []
    forbid_tenant_session(monkeypatch, app, calls)

    response = app.test_client().get("/health")

    assert calls == []
    assert response.status_code == 503


def test_health_does_not_use_tenant_session_when_database_responds(monkeypatch, up_app):
    calls: list[str] = []
    forbid_tenant_session(monkeypatch, up_app, calls)

    response = up_app.test_client().get("/health")

    assert calls == []
    assert response.status_code == 200


def test_health_only_accepts_get():
    response = make_app(DOWN_DB).test_client().post("/health")

    assert response.status_code == 405
    assert response.get_json()["error"]["code"] == "metodo_no_permitido"
