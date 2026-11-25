"""Rutas de fotos (spec 012, T4–T5; R2, R4–R8; plan.md §5).

- ``PUT /activos/{id}/foto`` y ``DELETE /activos/{id}/foto``: crear, cambiar o quitar la
  foto principal (admin y contador, Q1 B).
- ``PUT /sesiones/{sid}/verificaciones/{vid}/foto``: foto opcional de una verificación.
- ``GET /fotos/{id}?tamano=completa|mini``: la imagen (JPEG), privada y del tenant.

La subida es ``multipart/form-data`` con ``foto_id`` (UUID del cliente) y ``archivo``.
"""

import uuid

from flask import Blueprint, Response, current_app, jsonify, request
from flask.typing import ResponseReturnValue

from app.activos.service import ErrorActivo
from app.auth.decorators import current_session, current_user, require_auth
from app.errors import error_response
from app.fotos import cupo, imagen, service
from app.fotos.almacen import EXTENSION_KEY, Almacen

bp = Blueprint("fotos", __name__)

INVALIDA = (400, "solicitud_invalida", "Envía la foto como archivo con su identificador.")


def _almacen() -> Almacen | None:
    return current_app.extensions.get(EXTENSION_KEY)


def _subida() -> tuple[uuid.UUID, bytes] | None:
    archivo = request.files.get("archivo")
    try:
        foto_id = uuid.UUID(request.form.get("foto_id", ""))
    except ValueError:
        return None
    if archivo is None:
        return None
    return foto_id, archivo.read(imagen.MAX_BYTES + 1)


def _error(exc: Exception) -> ResponseReturnValue:
    return error_response(exc.status, exc.code, exc.message)  # type: ignore[attr-defined]


ERRORES = (service.ErrorFoto, imagen.ErrorImagen, ErrorActivo)


def _respuesta(subida: service.Subida) -> ResponseReturnValue:
    return jsonify(foto=service.vista(subida.foto)), 201 if subida.creada else 200


def _sin_cupo(usuario_id: uuid.UUID) -> ResponseReturnValue | None:
    """SEC-02: ``429`` si el usuario agotó sus subidas de la ventana; antes de leer el archivo."""
    try:
        cupo.registrar_subida(usuario_id)
    except cupo.SubidasExcedidas as exc:
        return _error(exc)
    return None


@bp.put("/activos/<uuid:id>/foto")
@require_auth
def subir_principal(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002 - nombre del contrato
    usuario = current_user()
    if (rechazo := _sin_cupo(usuario.usuario_id)) is not None:
        return rechazo
    datos = _subida()
    if datos is None:
        return error_response(*INVALIDA)
    try:
        subida = service.subir_principal(
            current_session(),
            _almacen(),
            tenant_id=usuario.tenant_id,
            activo_id=id,
            foto_id=datos[0],
            datos=datos[1],
            usuario_id=usuario.usuario_id,
        )
    except ERRORES as exc:
        return _error(exc)
    return _respuesta(subida)


@bp.delete("/activos/<uuid:id>/foto")
@require_auth
def quitar_principal(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002 - nombre del contrato
    usuario = current_user()
    try:
        service.quitar_principal(
            current_session(),
            _almacen(),
            tenant_id=usuario.tenant_id,
            activo_id=id,
            usuario_id=usuario.usuario_id,
        )
    except ERRORES as exc:
        return _error(exc)
    return "", 204


@bp.put("/sesiones/<uuid:sid>/verificaciones/<uuid:vid>/foto")
@require_auth
def subir_de_verificacion(sid: uuid.UUID, vid: uuid.UUID) -> ResponseReturnValue:
    usuario = current_user()
    if (rechazo := _sin_cupo(usuario.usuario_id)) is not None:
        return rechazo
    datos = _subida()
    if datos is None:
        return error_response(*INVALIDA)
    try:
        subida = service.subir_de_verificacion(
            current_session(),
            _almacen(),
            tenant_id=usuario.tenant_id,
            sesion_id=sid,
            verificacion_id=vid,
            foto_id=datos[0],
            datos=datos[1],
            usuario_id=usuario.usuario_id,
            es_admin=usuario.rol == "admin",
        )
    except ERRORES as exc:
        return _error(exc)
    return _respuesta(subida)


@bp.get("/fotos/<uuid:id>")
@require_auth
def ver(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002 - nombre del contrato
    tamano = request.args.get("tamano", "completa")
    if tamano not in service.TAMANOS:
        return error_response(400, "solicitud_invalida", "El tamaño debe ser completa o mini.")
    try:
        datos = service.leer(current_session(), _almacen(), id, tamano)
    except ERRORES as exc:
        return _error(exc)
    return Response(
        datos,
        mimetype=service.TIPO,
        headers={
            # La foto de un id nunca cambia (cambiarla crea otra): se puede guardar en caché
            # del navegador, solo para este usuario.
            "Cache-Control": "private, max-age=86400",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )
