"""Rutas ``/activos`` (spec 004; R1–R7; spec 005; plan.md §4).

Ambos roles leen y dan de alta (P11); el precio solo sale en las respuestas del admin
(R5, P13: la clave no existe para el contador). Un ``id`` de otro tenant es ``404``.
Cambiar un activo existente es solo del admin y exige ``If-Match`` (spec 005, R2, R9).
Cuerpos JSON de 4 KB como máximo (``app.auth.http``).
"""

import uuid

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from app.activos import cambios, service
from app.activos.models import Activo
from app.auth.decorators import current_session, current_user, require_auth, require_role
from app.errors import current_request_id, error_response

bp = Blueprint("activos", __name__, url_prefix="/activos")


def _es_admin() -> bool:
    return current_user().rol == "admin"


def _error(exc: service.ErrorActivo) -> ResponseReturnValue:
    if isinstance(exc, service.CodigoExistente | cambios.VersionDesactualizada):
        activo = exc.activo
        if isinstance(activo, Activo):
            # Solo el admin escribe sobre activos existentes: el vigente va con precio.
            activo = service.vista(current_session(), activo, con_precio=True)
        cuerpo = {
            "error": {"code": exc.code, "message": exc.message, "request_id": current_request_id()},
            "activo": activo,
        }
        return jsonify(cuerpo), exc.status
    return error_response(exc.status, exc.code, exc.message)


def _con_version(activo: Activo) -> ResponseReturnValue:
    """Respuesta de una escritura del admin: el activo con precio y su ``ETag``."""
    vista = service.vista(current_session(), activo, con_precio=True)
    return jsonify(activo=vista), 200, {"ETag": f'"{activo.row_version}"'}


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


@bp.get("")
@require_auth
def buscar() -> ResponseReturnValue:
    session = current_session()
    try:
        pagina = service.buscar(
            session,
            q=request.args.get("q"),
            estado=request.args.get("estado"),
            pagina=request.args.get("pagina"),
            con_precio=_es_admin(),
        )
    except service.ErrorActivo as exc:
        return _error(exc)
    return jsonify(
        activos=pagina.activos,
        total=pagina.total,
        pagina=pagina.pagina,
        por_pagina=pagina.por_pagina,
    )


@bp.get("/sugerencias")
@require_auth
def sugerencias() -> ResponseReturnValue:
    try:
        valores = service.sugerencias(
            current_session(), campo=request.args.get("campo"), q=request.args.get("q")
        )
    except service.ErrorActivo as exc:
        return _error(exc)
    return jsonify(valores=valores)


# --- Spec 005: cambios (solo admin, con If-Match) ----------------------------------------


@bp.patch("/<uuid:id>")
@require_role("admin")
def editar(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002 - nombre del contrato
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error_response(400, "solicitud_invalida", "La solicitud no es válida.")
    try:
        datos = cambios.edicion(body)
        version = cambios.leer_version(request.headers.get("If-Match"))
        activo = cambios.editar(current_session(), id, version, datos, current_user().usuario_id)
    except service.ErrorActivo as exc:
        return _error(exc)
    return _con_version(activo)


def _accion(id: uuid.UUID, accion: cambios.Accion) -> ResponseReturnValue:  # noqa: A002
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error_response(400, "solicitud_invalida", "La solicitud no es válida.")
    try:
        version = cambios.leer_version(request.headers.get("If-Match"))
        activo = accion(current_session(), id, version, body, current_user().usuario_id)
    except service.ErrorActivo as exc:
        return _error(exc)
    return _con_version(activo)


@bp.post("/<uuid:id>/mover")
@require_role("admin")
def mover(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002 - nombre del contrato
    return _accion(id, cambios.mover)


@bp.post("/<uuid:id>/estado")
@require_role("admin")
def cambiar_estado(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002 - nombre del contrato
    return _accion(id, cambios.cambiar_estado)


@bp.post("/<uuid:id>/baja")
@require_role("admin")
def dar_de_baja(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002 - nombre del contrato
    return _accion(id, cambios.dar_de_baja)
