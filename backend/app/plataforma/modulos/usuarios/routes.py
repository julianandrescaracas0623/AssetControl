"""Rutas ``/plataforma/empresas/{id}/usuarios`` (spec 017, T5; R29–R31; plan.md §4).

- ``GET /plataforma/empresas/{id}/usuarios``: por membresía, ``{id, nombre, email, rol,
  activa, debe_cambiar_password}`` (R29); ``404`` si la empresa no existe.
- ``PATCH /plataforma/empresas/{id}/usuarios/{usuario_id}``: exactamente ``{activa}`` ->
  ``200 {id, activa}``; ``404`` (empresa inexistente o usuario de otra empresa), ``409
  empresa_inactiva`` / ``ultimo_admin``.
- ``PUT /plataforma/empresas/{id}/usuarios/{usuario_id}`` (C1; R47–R51): exactamente
  ``{nombre, rol}`` -> ``200 {id, nombre, rol}``; ``400`` con otra clave, ``422`` con
  ``campo``, ``404``, ``409 empresa_inactiva`` / ``ultimo_admin``, ``503``.
- ``POST /plataforma/empresas/{id}/usuarios/{usuario_id}/contrasena`` (C1b; R53–R58):
  exactamente ``{password, password_confirmacion}`` -> ``204`` sin cuerpo; ``400``, ``422``
  con ``campo``, ``404``, ``409 empresa_inactiva``, ``503``. No idempotente.

El ``PATCH``, el ``PUT`` y el ``POST`` cuentan en ``plat_accion`` por desarrollador antes de
validar y de la base (``429``/``503``), como las acciones de Empresas. Todas con
``require_desarrollador`` (token de plataforma y ``desarrollador.activo`` en cada
petición); ``Authorization: Bearer``, sin cookies ni CSRF. ``no-store``, ``no-referrer``
y el tope de 4 KB los pone ``app.plataforma``. Los ids de la ruta pasan por el convertidor
``uuid`` (otra cosa da ``404`` sin llegar a la vista). El cuerpo no se registra.
"""

import uuid

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from app.auth import limits
from app.errors import current_request_id, error_response
from app.plataforma.decoradores import (
    current_desarrollador,
    current_plataforma_session,
    require_desarrollador,
)
from app.plataforma.modulos.usuarios import service

bp = Blueprint("plataforma_usuarios", __name__, url_prefix="/plataforma/empresas")


def _error(exc: service.ErrorUsuarios) -> ResponseReturnValue:
    if exc.campo is None:
        return error_response(exc.status, exc.code, exc.message)
    cuerpo = {
        "error": {
            "code": exc.code,
            "message": exc.message,
            "request_id": current_request_id(),
            "campo": exc.campo,
        }
    }
    return jsonify(cuerpo), exc.status


@bp.get("/<uuid:id>/usuarios")
@require_desarrollador
def listar(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002 - nombre del contrato
    try:
        usuarios = service.listar(current_plataforma_session(), id)
    except service.ErrorUsuarios as exc:
        return _error(exc)
    return jsonify(usuarios=usuarios)


@bp.patch("/<uuid:id>/usuarios/<uuid:usuario_id>")
@require_desarrollador
def cambiar_estado(id: uuid.UUID, usuario_id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002
    limits.limit_platform_action(current_desarrollador().id)
    try:
        activa = service.validar_estado(request.get_json(silent=True))
        resultado = service.cambiar_estado(current_plataforma_session(), id, usuario_id, activa)
    except service.ErrorUsuarios as exc:
        return _error(exc)
    return jsonify(id=str(usuario_id), activa=resultado)


@bp.put("/<uuid:id>/usuarios/<uuid:usuario_id>")
@require_desarrollador
def editar(id: uuid.UUID, usuario_id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002
    limits.limit_platform_action(current_desarrollador().id)
    try:
        nombre, rol = service.validar_edicion(request.get_json(silent=True))
        resultado = service.editar(current_plataforma_session(), id, usuario_id, nombre, rol)
    except service.ErrorUsuarios as exc:
        return _error(exc)
    return jsonify(resultado)


@bp.post("/<uuid:id>/usuarios/<uuid:usuario_id>/contrasena")
@require_desarrollador
def restablecer_contrasena(
    id: uuid.UUID,  # noqa: A002 - nombre del contrato
    usuario_id: uuid.UUID,
) -> ResponseReturnValue:
    limits.limit_platform_action(current_desarrollador().id)
    try:
        password = service.validar_contrasena(request.get_json(silent=True))
        service.restablecer_contrasena(current_plataforma_session(), id, usuario_id, password)
    except service.ErrorUsuarios as exc:
        return _error(exc)
    return "", 204
