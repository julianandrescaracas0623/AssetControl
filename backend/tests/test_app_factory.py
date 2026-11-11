import socket

import pytest
from flask import Flask

from app import create_app
from app.config import Config, MissingConfigError

UNREACHABLE_DB = "postgresql+psycopg://user:pw@db.invalid:5432/assetcontrol"


def make_config(**overrides) -> Config:
    values = {
        "database_url": UNREACHABLE_DB,
        "secret_key": "clave-de-prueba",
        "environment": "test",
    }
    values.update(overrides)
    return Config(**values)


@pytest.fixture
def no_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("create_app no debe abrir conexiones")

    monkeypatch.setattr(socket, "create_connection", fail)
    monkeypatch.setattr(socket.socket, "connect", fail)


def test_create_app_returns_flask_app_without_connecting(no_network):
    app = create_app(make_config())

    assert isinstance(app, Flask)
    assert app.config["SECRET_KEY"] == "clave-de-prueba"
    assert app.config["DATABASE_URL"] == UNREACHABLE_DB
    assert app.config["ENVIRONMENT"] == "test"


def test_each_call_creates_an_isolated_instance(no_network):
    first = create_app(make_config(environment="test"))
    second = create_app(make_config(environment="development"))

    assert first is not second
    assert first.config["ENVIRONMENT"] == "test"
    assert second.config["ENVIRONMENT"] == "development"


def test_testing_flag_follows_environment(no_network):
    assert create_app(make_config(environment="test")).testing is True
    assert create_app(make_config(environment="production")).testing is False


def test_create_app_without_config_reads_environment(monkeypatch, no_network):
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_DB)
    monkeypatch.setenv("SECRET_KEY", "clave-del-entorno")
    monkeypatch.setenv("ENVIRONMENT", "test")

    app = create_app()

    assert app.config["SECRET_KEY"] == "clave-del-entorno"


def test_create_app_without_config_fails_if_variable_missing(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", UNREACHABLE_DB)
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(MissingConfigError, match="SECRET_KEY"):
        create_app()
