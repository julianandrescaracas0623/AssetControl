"""Redacción de errores de base en los logs (spec 002, T4; plan.md §2.2 "Logs", A14).

Un ``DBAPIError`` no controlado se registra solo con su tipo, el ``sqlstate`` y
el ``request_id``: ni la sentencia, ni los parámetros, ni el mensaje de
PostgreSQL (que puede traer valores de fila, p. ej. ``Key (email)=(...)``).
También cuando llega encadenado dentro de otra excepción. La respuesta sigue
siendo el ``500`` genérico de la spec 001.

Datos sintéticos.
"""

import logging

import psycopg
import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, InvalidRequestError, SQLAlchemyError, StatementError

from app import create_app
from app.config import Config
from app.db import _get_database

OFFLINE_DB = "postgresql+psycopg://user:valor-secreto-db@db.invalid:5432/assetcontrol"
SECRET_EMAIL = "secreto.log@ejemplo.test"
SECRET_VALUE = "valor-de-fila-secreto"
SECRET_STATEMENT = "INSERT INTO usuario (email) VALUES (%(email)s) -- sentencia-secreta"


class _FakeOrig(Exception):
    sqlstate = "23505"


def _orig() -> _FakeOrig:
    return _FakeOrig(
        f'duplicate key value violates unique constraint "x" '
        f"DETAIL: Key (email)=({SECRET_EMAIL}) already exists. {SECRET_VALUE}"
    )


def _integrity_error() -> IntegrityError:
    return IntegrityError(SECRET_STATEMENT, {"email": SECRET_EMAIL}, _orig())


def _app(database_url: str = OFFLINE_DB):
    flask_app = create_app(
        Config(database_url=database_url, secret_key="clave-de-prueba", environment="test")
    )

    def direct():
        raise _integrity_error()

    def chained():
        try:
            raise _integrity_error()
        except IntegrityError as exc:
            raise RuntimeError(f"envuelto: {exc}") from exc

    def implicit():
        try:
            raise _integrity_error()
        except IntegrityError:
            raise ValueError(SECRET_VALUE) from None

    def context_only():
        try:
            raise _integrity_error()
        except IntegrityError:
            raise KeyError(SECRET_VALUE)  # noqa: B904 - contexto implícito a propósito

    def real_database():
        with _get_database().engine.connect() as conn:
            conn.execute(text(f"select '{SECRET_VALUE}'::int"))  # noqa: S608 - literal de prueba
        return {}

    flask_app.add_url_rule("/_db/directo", "direct", direct)
    flask_app.add_url_rule("/_db/encadenado", "chained", chained)
    flask_app.add_url_rule("/_db/sin-causa", "implicit", implicit)
    flask_app.add_url_rule("/_db/contexto", "context_only", context_only)
    flask_app.add_url_rule("/_db/real", "real", real_database)
    return flask_app


def _secrets_in(text_: str) -> list[str]:
    return [s for s in (SECRET_EMAIL, SECRET_VALUE, "sentencia-secreta") if s in text_]


@pytest.mark.parametrize("path", ["/_db/directo", "/_db/encadenado", "/_db/contexto"])
def test_dbapi_error_is_logged_with_type_and_sqlstate_only(path, caplog):
    caplog.set_level(logging.DEBUG)

    response = _app().test_client().get(path)

    assert response.status_code == 500
    body = response.get_data(as_text=True)
    request_id = response.get_json()["error"]["request_id"]
    assert _secrets_in(body) == []
    assert _secrets_in(caplog.text) == []
    record = next(r for r in caplog.records if request_id in r.getMessage())
    assert "IntegrityError" in record.getMessage()
    assert "23505" in record.getMessage()
    assert record.exc_info is None
    assert record.levelno == logging.ERROR


def test_without_a_database_error_in_the_chain_the_traceback_is_kept(caplog):
    # "from None" suprime el contexto: no hay DBAPIError a la vista y se registra normal.
    caplog.set_level(logging.ERROR)

    response = _app().test_client().get("/_db/sin-causa")

    assert response.status_code == 500
    record = next(r for r in caplog.records if "request_id" in r.getMessage())
    assert record.exc_info is not None


def test_dbapi_error_log_keeps_the_code_location(caplog):
    caplog.set_level(logging.ERROR)

    _app().test_client().get("/_db/directo")

    # Ubicación (archivo y función) sí; mensaje de la base no.
    assert "test_log_redaction.py" in caplog.text
    assert "direct" in caplog.text


def test_real_postgres_error_is_redacted(app_database_url, caplog):
    caplog.set_level(logging.DEBUG)
    flask_app = _app(app_database_url.render_as_string(hide_password=False))

    response = flask_app.test_client().get("/_db/real")

    assert response.status_code == 500
    assert _secrets_in(caplog.text) == []
    assert app_database_url.password not in caplog.text
    assert "DataError" in caplog.text or "InvalidTextRepresentation" in caplog.text
    assert "22P02" in caplog.text  # invalid_text_representation


# --- B2 de T4: SQLAlchemyError (también StatementError) y psycopg.Error sin envolver -----


class _SecretError(Exception):
    """Excepción con texto secreto que no debe llegar al log."""


def _b2_app(database_url: str = OFFLINE_DB):
    flask_app = _app(database_url)

    def statement_error():
        raise StatementError(
            f"fallo {SECRET_VALUE}", SECRET_STATEMENT, {"e": SECRET_EMAIL}, _orig()
        )

    def sqlalchemy_error():
        raise SQLAlchemyError(f"Key (email)=({SECRET_EMAIL}) {SECRET_VALUE}")

    def invalid_request():
        raise InvalidRequestError(f"estado inválido {SECRET_VALUE}")

    def psycopg_error():
        raise psycopg.errors.UniqueViolation(f"Key (email)=({SECRET_EMAIL}) already exists")

    def psycopg_chained():
        try:
            raise psycopg.errors.UniqueViolation(f"Key (email)=({SECRET_EMAIL}) {SECRET_VALUE}")
        except psycopg.Error as exc:
            raise _SecretError(f"envuelto: {exc}") from exc

    def psycopg_base():
        raise psycopg.OperationalError(f"conexión fallida {SECRET_VALUE}")

    def real_psycopg():
        raw = _get_database().engine.raw_connection()
        try:
            raw.driver_connection.execute(f"select '{SECRET_VALUE}'::int")  # noqa: S608
        finally:
            raw.close()
        return {}

    routes = {
        "/_b2/statement": statement_error,
        "/_b2/sqlalchemy": sqlalchemy_error,
        "/_b2/invalid-request": invalid_request,
        "/_b2/psycopg": psycopg_error,
        "/_b2/psycopg-encadenado": psycopg_chained,
        "/_b2/psycopg-base": psycopg_base,
        "/_b2/psycopg-real": real_psycopg,
    }
    for path, view in routes.items():
        flask_app.add_url_rule(path, path, view)
    return flask_app


@pytest.mark.parametrize(
    ("path", "kind", "sqlstate"),
    [
        ("/_b2/statement", "StatementError", "23505"),
        ("/_b2/sqlalchemy", "SQLAlchemyError", "desconocido"),
        ("/_b2/invalid-request", "InvalidRequestError", "desconocido"),
        ("/_b2/psycopg", "UniqueViolation", "23505"),
        ("/_b2/psycopg-encadenado", "UniqueViolation", "23505"),
        ("/_b2/psycopg-base", "OperationalError", "desconocido"),
    ],
)
def test_sqlalchemy_and_psycopg_errors_are_redacted(path, kind, sqlstate, caplog):
    caplog.set_level(logging.DEBUG)

    response = _b2_app().test_client().get(path)

    assert response.status_code == 500
    request_id = response.get_json()["error"]["request_id"]
    assert _secrets_in(response.get_data(as_text=True)) == []
    assert _secrets_in(caplog.text) == []
    record = next(r for r in caplog.records if request_id in r.getMessage())
    message = record.getMessage()
    assert record.exc_info is None
    assert record.levelno == logging.ERROR
    assert f"tipo={kind}" in message
    assert f"sqlstate={sqlstate}" in message
    assert "test_log_redaction.py" in message  # archivo:línea:función sí


def test_real_unwrapped_psycopg_error_is_redacted(app_database_url, caplog):
    caplog.set_level(logging.DEBUG)
    flask_app = _b2_app(app_database_url.render_as_string(hide_password=False))

    response = flask_app.test_client().get("/_b2/psycopg-real")

    assert response.status_code == 500
    assert _secrets_in(caplog.text) == []
    assert app_database_url.password not in caplog.text
    assert "InvalidTextRepresentation" in caplog.text
    assert "22P02" in caplog.text
