"""Rutas ``/sesiones`` (spec 006; R1–R9, Q1–Q4; plan.md §3).

Ambos roles ven la sesión abierta, la lista y el avance (sin precios) y verifican; solo
el admin abre (Q1) y solo él recibe ``precio_al_contar`` (P13). Una sesión de otro
tenant es ``404``. Cuerpos JSON de 4 KB como máximo (``app.auth.http``).
"""

import uuid
from urllib.parse import quote

from flask import Blueprint, Response, jsonify, request
from flask.typing import ResponseReturnValue

from app.auth.decorators import current_session, current_user, require_auth, require_role
from app.conteo import cierre, discrepancias, exportar, service, verificaciones
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


# --- Spec 008: cerrar e informe (solo admin) ----------------------------------------------


@bp.post("/<uuid:id>/cerrar")
@require_role("admin")
def cerrar(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002 - nombre del contrato
    session = current_session()
    try:
        sesion = cierre.cerrar(session, id, current_user().usuario_id)
        return jsonify(cierre.informe(session, sesion))
    except service.ErrorConteo as exc:
        return _error(exc)


@bp.get("/<uuid:id>/informe")
@require_role("admin")
def ver_informe(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002 - nombre del contrato
    session = current_session()
    try:
        return jsonify(cierre.informe(session, service.obtener(session, id)))
    except service.ErrorConteo as exc:
        return _error(exc)


# --- Spec 009: exportar el informe (solo admin) --------------------------------------------


def _archivo(contenido: bytes, mimetype: str, nombre: str) -> Response:
    """Descarga segura (R6): adjunto con nombre ASCII, sin caché y sin adivinar el tipo."""
    respuesta = Response(contenido, mimetype=mimetype)
    respuesta.headers["Content-Disposition"] = (
        f"attachment; filename=\"{nombre}\"; filename*=UTF-8''{quote(nombre)}"
    )
    respuesta.headers["Cache-Control"] = "no-store"
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    return respuesta


def _documento(session, id: uuid.UUID) -> tuple[exportar.Documento, str]:  # noqa: A002
    informe = cierre.informe(session, service.obtener(session, id))
    sesion = informe["sesion"]
    return exportar.documento(informe), exportar.nombre_base(
        sesion["nombre"], sesion["fecha_corte"]
    )


@bp.get("/<uuid:id>/informe/excel")
@require_role("admin")
def exportar_excel(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002 - nombre del contrato
    try:
        doc, nombre = _documento(current_session(), id)
    except service.ErrorConteo as exc:
        return _error(exc)
    return _archivo(exportar.a_excel(doc), exportar.XLSX, f"{nombre}.xlsx")


@bp.get("/<uuid:id>/informe/pdf")
@require_role("admin")
def exportar_pdf(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002 - nombre del contrato
    try:
        doc, nombre = _documento(current_session(), id)
    except service.ErrorConteo as exc:
        return _error(exc)
    return _archivo(exportar.a_pdf(doc), exportar.PDF, f"{nombre}.pdf")
