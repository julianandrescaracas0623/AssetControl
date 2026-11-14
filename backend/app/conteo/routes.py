"""Rutas ``/sesiones`` (spec 006; R1–R9, Q1–Q4; plan.md §3).

Ambos roles ven la sesión abierta, la lista y el avance (sin precios) y verifican; solo
el admin abre (Q1) y solo él recibe ``precio_al_contar`` (P13). Una sesión de otro
tenant es ``404``. Cuerpos JSON de 4 KB como máximo (``app.auth.http``).
"""

import uuid

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from app.auth.decorators import current_session, current_user, require_auth, require_role
from app.conteo import discrepancias, service, verificaciones
from app.errors import error_response

bp = Blueprint("sesiones", __name__, url_prefix="/sesiones")


def _error(exc: service.ErrorConteo) -> ResponseReturnValue:
    return error_response(exc.status, exc.code, exc.message)


@bp.post("")
@require_role("admin")
def abrir() -> ResponseReturnValue:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error_response(400, "solicitud_invalida", "La solicitud no es válida.")
    session = current_session()
    try:
        nombre, fecha_corte = service.datos_de_apertura(body)
        sesion = service.abrir(session, nombre, fecha_corte, current_user().usuario_id)
    except service.ErrorConteo as exc:
        return _error(exc)
    return jsonify(sesion=service.vista(session, sesion)), 201


@bp.get("")
@require_auth
def listar() -> ResponseReturnValue:
    session = current_session()
    return jsonify(sesiones=[service.vista(session, s) for s in service.listar(session)])


@bp.get("/abierta")
@require_auth
def abierta() -> ResponseReturnValue:
    session = current_session()
    sesion = service.abierta(session)
    return jsonify(sesion=service.vista(session, sesion) if sesion else None)


@bp.get("/<uuid:id>")
@require_auth
def detalle(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002 - nombre del contrato
    session = current_session()
    try:
        sesion = service.obtener(session, id)
    except service.ErrorConteo as exc:
        return _error(exc)
    return jsonify(sesion=service.vista(session, sesion), avance=service.avance(session, sesion))


def _es_admin() -> bool:
    return current_user().rol == "admin"


@bp.post("/<uuid:id>/verificaciones")
@require_auth
def verificar(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002 - nombre del contrato
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error_response(400, "solicitud_invalida", "La solicitud no es válida.")
    session = current_session()
    try:
        datos = verificaciones.datos_de_verificacion(body)
        verificacion, nueva = verificaciones.verificar(
            session, id, datos, current_user().usuario_id
        )
    except service.ErrorConteo as exc:
        return _error(exc)
    vista = verificaciones.vista(session, verificacion, con_precio=_es_admin())
    return jsonify(verificacion=vista), 201 if nueva else 200


@bp.get("/<uuid:id>/verificaciones")
@require_auth
def ultima_verificacion(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002
    session = current_session()
    try:
        verificacion = verificaciones.ultima(session, id, request.args.get("activo_id"))
    except service.ErrorConteo as exc:
        return _error(exc)
    vista = (
        verificaciones.vista(session, verificacion, con_precio=_es_admin())
        if verificacion
        else None
    )
    return jsonify(verificacion=vista)


# --- Spec 007: discrepancias (solo admin) y pendientes (ambos) ----------------------------


@bp.get("/<uuid:id>/discrepancias")
@require_role("admin")
def listar_discrepancias(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002
    try:
        items = discrepancias.listar(current_session(), id, request.args.get("estado"))
    except service.ErrorConteo as exc:
        return _error(exc)
    return jsonify(discrepancias=items)


def _resolver(id: uuid.UUID, *, aplicar: bool) -> ResponseReturnValue:  # noqa: A002
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error_response(400, "solicitud_invalida", "La solicitud no es válida.")
    session = current_session()
    try:
        ids, confirmar = discrepancias.datos_de_lote(body, con_desfase=aplicar)
        salida = discrepancias.resolver(
            session,
            id,
            ids,
            aplicar=aplicar,
            confirmar_desfase=confirmar,
            usuario_id=current_user().usuario_id,
        )
    except service.ErrorConteo as exc:
        return _error(exc)
    return jsonify(resultados=[discrepancias.vista_resultado(session, r) for r in salida])


@bp.post("/<uuid:id>/discrepancias/aplicar")
@require_role("admin")
def aplicar_discrepancias(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002
    return _resolver(id, aplicar=True)


@bp.post("/<uuid:id>/discrepancias/descartar")
@require_role("admin")
def descartar_discrepancias(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002
    return _resolver(id, aplicar=False)


@bp.get("/<uuid:id>/pendientes")
@require_auth
def listar_pendientes(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002
    try:
        pagina = discrepancias.pendientes(
            current_session(),
            id,
            ubicacion_id=request.args.get("ubicacion_id"),
            pagina=request.args.get("pagina"),
        )
    except service.ErrorConteo as exc:
        return _error(exc)
    return jsonify(pagina)
