"""Rutas ``/activos`` (spec 004; R1–R7; plan.md §4).

Ambos roles leen y dan de alta (P11); el precio solo sale en las respuestas del admin
(R5, P13: la clave no existe para el contador). Un ``id`` de otro tenant es ``404``.
Cuerpos JSON de 4 KB como máximo (``app.auth.http``).
"""

import uuid

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from app.activos import service
from app.auth.decorators import current_session, current_user, require_auth
from app.errors import current_request_id, error_response

bp = Blueprint("activos", __name__, url_prefix="/activos")


def _es_admin() -> bool:
    return current_user().rol == "admin"


def _error(exc: service.ErrorActivo) -> ResponseReturnValue:
    if isinstance(exc, service.CodigoExistente):
        cuerpo = {
            "error": {"code": exc.code, "message": exc.message, "request_id": current_request_id()},
            "activo": exc.activo,
        }
        return jsonify(cuerpo), exc.status
    return error_response(exc.status, exc.code, exc.message)


@bp.get("/por-codigo")
@require_auth
def por_codigo() -> ResponseReturnValue:
    session = current_session()
    try:
        activo = service.resolver(session, request.args.get("codigo"))
    except service.ErrorActivo as exc:
        return _error(exc)
    return jsonify(activo=service.vista(session, activo, con_precio=_es_admin()))


@bp.get("/<uuid:id>")
@require_auth
def ficha(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002 - nombre del contrato
    session = current_session()
    try:
        activo = service.obtener(session, id)
    except service.ErrorActivo as exc:
        return _error(exc)
    return jsonify(activo=service.vista(session, activo, con_precio=_es_admin()))


@bp.post("")
@require_auth
def crear() -> ResponseReturnValue:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error_response(400, "solicitud_invalida", "La solicitud no es válida.")
    session = current_session()
    usuario = current_user()
    try:
        if "copiar_de" in body:
            datos = service.datos_de_duplicado(session, body, es_admin=usuario.rol == "admin")
        else:
            datos = service.datos_de_alta(body)
        resultado = service.guardar(
            session, datos, usuario_id=usuario.usuario_id, con_precio=usuario.rol == "admin"
        )
    except service.ErrorActivo as exc:
        return _error(exc)
    return jsonify(activo=resultado.activo), 201 if resultado.creado else 200
