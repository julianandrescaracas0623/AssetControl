"""Rutas ``/ubicaciones`` y ``/categorias`` (spec 003, T2–T3; R1–R6; plan.md §3).

Todas exigen sesión (``require_role``): ambos roles leen y solo el admin escribe
(``403 prohibido`` al contador antes de mirar el cuerpo). El contador recibe solo
ubicaciones activas. Un ``id`` de otro tenant o inexistente es ``404``. Cuerpos JSON
de 4 KB como máximo (``app.auth.http``); los campos desconocidos se ignoran.
"""

import uuid

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from app.auth.decorators import current_session, current_user, require_auth, require_role
from app.catalogo import service
from app.errors import error_response

ubicaciones_bp = Blueprint("ubicaciones", __name__, url_prefix="/ubicaciones")

BAD_REQUEST = ("solicitud_invalida", "La solicitud no es válida.")


def _cuerpo() -> dict | None:
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else None


def _error(exc: service.ErrorCatalogo) -> ResponseReturnValue:
    return error_response(exc.status, exc.code, exc.message)


def _uuid_o_none(valor: object) -> uuid.UUID | None:
    if valor is None:
        return None
    if not isinstance(valor, str):
        raise service.ErrorCatalogo()
    try:
        return uuid.UUID(valor)
    except ValueError:
        raise service.NoEncontrado() from None


@ubicaciones_bp.get("")
@require_auth
def listar() -> ResponseReturnValue:
    solo_activas = current_user().rol != "admin"
    ubicaciones = service.listar_ubicaciones(current_session(), solo_activas=solo_activas)
    return jsonify(ubicaciones=[u.to_json() for u in ubicaciones])


@ubicaciones_bp.post("")
@require_role("admin")
def crear() -> ResponseReturnValue:
    body = _cuerpo()
    if body is None:
        return error_response(400, *BAD_REQUEST)
    try:
        creada = service.crear_ubicacion(
            current_session(),
            nombre=body.get("nombre"),
            tipo=body.get("tipo"),
            padre_id=_uuid_o_none(body.get("padre_id")),
        )
    except service.ErrorCatalogo as exc:
        return _error(exc)
    return jsonify(ubicacion=creada.to_json()), 201


@ubicaciones_bp.patch("/<uuid:id>")
@require_role("admin")
def actualizar(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002 - nombre del contrato
    body = _cuerpo()
    if body is None:
        return error_response(400, *BAD_REQUEST)
    try:
        actualizada = service.actualizar_ubicacion(
            current_session(), id, nombre=body.get("nombre"), activa=body.get("activa")
        )
    except service.ErrorCatalogo as exc:
        return _error(exc)
    return jsonify(ubicacion=actualizada.to_json())
