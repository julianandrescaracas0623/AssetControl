"""Manejo uniforme de errores (spec 001, R6).

Toda respuesta de error tiene la forma::

    {"error": {"code": "<código estable>", "message": "<texto en español>",
               "request_id": "<uuid>"}}

Cada petición recibe un ``request_id`` generado en el servidor (se ignora el que
mande el cliente) y se devuelve también en la cabecera ``X-Request-ID``.

Un error no controlado responde siempre ``500`` con un mensaje genérico: nunca
la traza ni ``str(exc)``, que en psycopg/SQLAlchemy puede incluir SQL, host o
nombre de la base. El detalle queda solo en el log del servidor, junto al
``request_id`` para correlacionarlo.

Un error de base de datos (``SQLAlchemyError``, incluidos ``DBAPIError`` y
``StatementError``, o un ``psycopg.Error`` sin envolver; también encadenado en
otra excepción) se registra solo con su tipo, el ``sqlstate`` y la ubicación en
el código, sin traza con mensaje: el texto de PostgreSQL o de SQLAlchemy puede
traer SQL, parámetros o valores de fila (spec 002, T4; B2).
"""

import traceback
import uuid
from pathlib import Path

import psycopg
from flask import Flask, current_app, g, jsonify
from flask.typing import ResponseReturnValue
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException

REQUEST_ID_HEADER = "X-Request-ID"
INTERNAL_ERROR_CODE = "error_interno"
INTERNAL_ERROR_MESSAGE = (
    "Ocurrió un error inesperado. Si persiste, comunica este identificador a soporte."
)

_HTTP_ERRORS: dict[int, tuple[str, str]] = {
    400: ("solicitud_invalida", "La solicitud no es válida."),
    401: ("no_autenticado", "Debes iniciar sesión."),
    403: ("sin_permiso", "No tienes permiso para esta acción."),
    404: ("no_encontrado", "El recurso no existe."),
    405: ("metodo_no_permitido", "Método no permitido para este recurso."),
    # Código de la spec 002 (plan.md §2.2, Errores).
    413: ("cuerpo_demasiado_grande", "El contenido enviado es demasiado grande."),
    415: ("tipo_no_soportado", "El tipo de contenido no es compatible."),
}


def current_request_id() -> str:
    """``request_id`` de la petición en curso; lo crea si aún no existe."""
    request_id = g.get("request_id")
    if request_id is None:
        request_id = str(uuid.uuid4())
        g.request_id = request_id
    return request_id


def error_response(status: int, code: str, message: str) -> ResponseReturnValue:
    payload = {"error": {"code": code, "message": message, "request_id": current_request_id()}}
    return jsonify(payload), status


def _handle_http_exception(exc: HTTPException) -> ResponseReturnValue:
    status = exc.code or 500
    if status >= 500:
        return error_response(status, INTERNAL_ERROR_CODE, INTERNAL_ERROR_MESSAGE)
    code, message = _HTTP_ERRORS.get(status, ("error_http", "No se pudo procesar la solicitud."))
    return error_response(status, code, message)


_DATABASE_ERRORS = (SQLAlchemyError, psycopg.Error)


def _database_error_in_chain(exc: BaseException) -> BaseException | None:
    """Primer error de base de la cadena (``__cause__`` o ``__context__`` visible).

    ``SQLAlchemyError`` (``DBAPIError``, ``StatementError`` y el resto) o
    ``psycopg.Error`` sin envolver (p. ej. desde ``driver_connection``).
    """
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        if isinstance(current, _DATABASE_ERRORS):
            return current
        seen.add(id(current))
        if current.__cause__ is not None:
            current = current.__cause__
        elif current.__suppress_context__:
            current = None
        else:
            current = current.__context__
    return None


def _log_database_error(exc: BaseException, database_error: BaseException) -> None:
    """Solo tipo, ``sqlstate`` y ubicación en el código: nunca SQL, parámetros ni mensaje.

    El mensaje de PostgreSQL puede traer valores de fila (``Key (email)=(...)``).
    En un ``psycopg.Error`` sin envolver el origen es el propio error.
    """
    if isinstance(database_error, psycopg.Error):
        orig: object = database_error
    else:
        orig = getattr(database_error, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None) or "desconocido"
    frames = traceback.extract_tb(exc.__traceback__)
    location = " <- ".join(f"{Path(f.filename).name}:{f.lineno} {f.name}" for f in frames[::-1])
    current_app.logger.error(
        "Error de base de datos no controlado (request_id=%s, tipo=%s, origen=%s, "
        "sqlstate=%s, en=%s)",
        current_request_id(),
        type(database_error).__name__,
        type(orig).__name__ if orig is not None else "desconocido",
        sqlstate,
        location or "desconocido",
    )


def _handle_unexpected(exc: Exception) -> ResponseReturnValue:
    database_error = _database_error_in_chain(exc)
    if database_error is not None:
        _log_database_error(exc, database_error)
        return error_response(500, INTERNAL_ERROR_CODE, INTERNAL_ERROR_MESSAGE)
    current_app.logger.error(
        "Error no controlado (request_id=%s, tipo=%s)",
        current_request_id(),
        type(exc).__name__,
        exc_info=exc,
    )
    return error_response(500, INTERNAL_ERROR_CODE, INTERNAL_ERROR_MESSAGE)


def register_error_handlers(app: Flask) -> None:
    """Registra el ``request_id`` por petición y los manejadores de error."""

    @app.before_request
    def _assign_request_id() -> None:
        g.request_id = str(uuid.uuid4())

    @app.after_request
    def _expose_request_id(response):
        response.headers[REQUEST_ID_HEADER] = current_request_id()
        return response

    app.register_error_handler(HTTPException, _handle_http_exception)
    app.register_error_handler(Exception, _handle_unexpected)
