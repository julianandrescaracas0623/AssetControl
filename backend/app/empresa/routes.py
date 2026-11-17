"""Rutas ``/empresa`` (spec 013, T2; R1, R2, R9; plan.md §3). Solo el admin.

- ``GET /empresa`` y ``PUT /empresa`` (JSON ≤ 4 KB): los datos de la empresa.
- ``PUT /empresa/logo`` (multipart ``logo_id`` + ``archivo``, ≤ 2 MB) y
  ``DELETE /empresa/logo``: cambiar o quitar el logo vigente (el anterior no se borra).
- ``GET /empresa/logo/{id}``: el PNG de un logo del tenant (vigente o congelado).
"""

import uuid

from flask import Blueprint, Response, current_app, jsonify, request
from flask.typing import ResponseReturnValue

from app.auth.decorators import current_session, current_user, require_role
from app.empresa import service
from app.errors import current_request_id, error_response
from app.fotos import imagen
from app.fotos.almacen import EXTENSION_KEY, Almacen

bp = Blueprint("empresa", __name__, url_prefix="/empresa")

INVALIDA = (400, "solicitud_invalida", "Envía el logo como archivo con su identificador.")
ERRORES = (service.ErrorEmpresa, imagen.ErrorImagen)


def _almacen() -> Almacen | None:
    return current_app.extensions.get(EXTENSION_KEY)


def _error(exc: Exception) -> ResponseReturnValue:
    campo = getattr(exc, "campo", None)
    if campo is None:
        return error_response(exc.status, exc.code, exc.message)  # type: ignore[attr-defined]
    cuerpo = {
        "error": {
            "code": exc.code,  # type: ignore[attr-defined]
            "message": exc.message,  # type: ignore[attr-defined]
            "request_id": current_request_id(),
            "campo": campo,
        }
    }
    return jsonify(cuerpo), exc.status  # type: ignore[attr-defined]


def _vista() -> ResponseReturnValue:
    return jsonify(empresa=service.vista(current_session(), current_user().tenant_id))


@bp.get("")
@require_role("admin")
def ver() -> ResponseReturnValue:
    return _vista()


@bp.put("")
@require_role("admin")
def guardar() -> ResponseReturnValue:
    usuario = current_user()
    try:
        service.guardar(
            current_session(),
            request.get_json(silent=True),
            tenant_id=usuario.tenant_id,
            usuario_id=usuario.usuario_id,
        )
    except ERRORES as exc:
        return _error(exc)
    return _vista()


@bp.put("/logo")
@require_role("admin")
def subir_logo() -> ResponseReturnValue:
    archivo = request.files.get("archivo")
    try:
        logo_id = uuid.UUID(request.form.get("logo_id", ""))
    except ValueError:
        return error_response(*INVALIDA)
    if archivo is None:
        return error_response(*INVALIDA)
    usuario = current_user()
    try:
        subida = service.subir_logo(
            current_session(),
            _almacen(),
            tenant_id=usuario.tenant_id,
            logo_id=logo_id,
            datos=archivo.read(service.LOGO_MAX_BYTES + 1),
            usuario_id=usuario.usuario_id,
        )
    except ERRORES as exc:
        return _error(exc)
    logo = {"id": str(subida.logo.id), "ancho": subida.logo.ancho, "alto": subida.logo.alto}
    return jsonify(logo=logo), 201 if subida.creado else 200


@bp.delete("/logo")
@require_role("admin")
def quitar_logo() -> ResponseReturnValue:
    try:
        service.quitar_logo(current_session(), usuario_id=current_user().usuario_id)
    except ERRORES as exc:
        return _error(exc)
    return "", 204


@bp.get("/logo/<uuid:id>")
@require_role("admin")
def ver_logo(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002 - nombre del contrato
    try:
        datos = service.leer_logo(current_session(), _almacen(), id)
    except ERRORES as exc:
        return _error(exc)
    return Response(
        datos,
        mimetype=service.TIPO_LOGO,
        headers={
            # Un logo nunca cambia (cambiarlo crea otro con otro id).
            "Cache-Control": "private, max-age=86400",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )
