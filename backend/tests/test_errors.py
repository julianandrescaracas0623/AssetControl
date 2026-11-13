"""Pruebas del manejo uniforme de errores (spec 001, R6).

Un error no controlado responde JSON con código estable, mensaje genérico en
español e identificador de correlación (``request_id``), nunca la traza ni el
texto de la excepción (que en psycopg/SQLAlchemy puede incluir SQL, host o base).
"""

import uuid

import pytest
from sqlalchemy.exc import OperationalError

from app import create_app
from app.config import Config
from app.errors import INTERNAL_ERROR_CODE, INTERNAL_ERROR_MESSAGE

UNREACHABLE_DB = "postgresql+psycopg://user:pw@db.invalid:5432/assetcontrol"
LEAKY_SQL = "select * from activo where tenant_id = 'secreto'"
LEAKY_ORIG = 'connection to server at "10.0.0.9", port 5432 failed: password authentication'


def make_app(environment: str = "test"):
    app = create_app(
        Config(database_url=UNREACHABLE_DB, secret_key="clave-de-prueba", environment=environment)
    )

    @app.get("/_boom")
    def boom():
        raise RuntimeError("detalle interno: /srv/app/secreto.py")

    @app.get("/_db_boom")
    def db_boom():
        raise OperationalError(LEAKY_SQL, {"clave": "valor-secreto"}, Exception(LEAKY_ORIG))

    return app


def assert_uniform_internal_error(response):
    assert response.status_code == 500
    assert response.is_json
    payload = response.get_json()
    assert set(payload) == {"error"}
    error = payload["error"]
    assert set(error) == {"code", "message", "request_id"}
    assert error["code"] == INTERNAL_ERROR_CODE
    assert error["message"] == INTERNAL_ERROR_MESSAGE
    assert uuid.UUID(error["request_id"])
    assert response.headers["X-Request-ID"] == error["request_id"]


@pytest.mark.parametrize("environment", ["test", "development", "production"])
def test_unhandled_error_returns_uniform_json(environment):
    response = make_app(environment).test_client().get("/_boom")

    assert_uniform_internal_error(response)
    body = response.get_data(as_text=True)
    assert "Traceback" not in body
    assert "RuntimeError" not in body
    assert "secreto" not in body


def test_database_error_never_returns_driver_message():
    response = make_app().test_client().get("/_db_boom")

    assert_uniform_internal_error(response)
    body = response.get_data(as_text=True)
    for leak in ("select", "activo", "10.0.0.9", "5432", "valor-secreto", "OperationalError"):
        assert leak not in body


@pytest.mark.parametrize(
    ("path", "exc_text"),
    [("/_boom", "detalle interno: /srv/app/secreto.py"), ("/_db_boom", LEAKY_ORIG)],
)
def test_500_message_is_spanish_and_never_the_exception_text(path, exc_text):
    error = make_app().test_client().get(path).get_json()["error"]

    assert error["code"] == "error_interno"
    assert error["message"] == (
        "Ocurrió un error inesperado. Si persiste, comunica este identificador a soporte."
    )
    assert exc_text not in error["message"]


def test_request_id_is_unique_per_request():
    client = make_app().test_client()

    first = client.get("/_boom").get_json()["error"]["request_id"]
    second = client.get("/_boom").get_json()["error"]["request_id"]

    assert first != second


def test_client_request_id_header_is_ignored():
    sent = "inyectado-por-cliente"
    response = make_app().test_client().get("/_boom", headers={"X-Request-ID": sent})

    request_id = response.get_json()["error"]["request_id"]
    assert request_id != sent
    assert response.headers["X-Request-ID"] == request_id
    assert uuid.UUID(request_id)


def test_successful_responses_carry_request_id():
    app = make_app()

    @app.get("/_ok")
    def ok():
        return {"ok": True}

    response = app.test_client().get("/_ok")

    assert response.status_code == 200
    assert uuid.UUID(response.headers["X-Request-ID"])


def test_not_found_returns_uniform_json():
    response = make_app().test_client().get("/no-existe")

    assert response.status_code == 404
    error = response.get_json()["error"]
    assert error["code"] == "no_encontrado"
    assert error["message"]
    assert uuid.UUID(error["request_id"])


def test_unhandled_error_is_logged_with_request_id(caplog):
    with caplog.at_level("ERROR"):
        response = make_app().test_client().get("/_boom")

    request_id = response.get_json()["error"]["request_id"]
    assert any(request_id in record.getMessage() for record in caplog.records)
