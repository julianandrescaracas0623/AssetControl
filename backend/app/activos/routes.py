"""Rutas ``/activos`` (spec 004; R1–R7; spec 005; plan.md §4).

Ambos roles leen y dan de alta (P11); el precio solo sale en las respuestas del admin
(R5, P13: la clave no existe para el contador). Un ``id`` de otro tenant es ``404``.
Cambiar un activo existente exige ``If-Match`` (spec 005, R2, R9); el contador solo edita
los campos descriptivos (spec 020, R7) y mover, estado y baja son solo del admin.
Cuerpos JSON de 4 KB como máximo (``app.auth.http``).
"""

import logging
import uuid
from datetime import datetime

from botocore.exceptions import BotoCoreError, ClientError
from flask import Blueprint, Response, current_app, jsonify, request
from flask.typing import ResponseReturnValue
from sqlalchemy.orm import Session

from app.activos import cambios, exportar, historial, service
from app.activos.models import Activo
from app.auth.decorators import current_session, current_user, require_auth, require_role
from app.conteo.exportar import Empresa
from app.empresa import service as empresa_service
from app.errors import current_request_id, error_response
from app.fotos import service as fotos_service
from app.fotos.almacen import EXTENSION_KEY

bp = Blueprint("activos", __name__, url_prefix="/activos")
logger = logging.getLogger(__name__)


def _es_admin() -> bool:
    return current_user().rol == "admin"


def _error(exc: service.ErrorActivo) -> ResponseReturnValue:
    if isinstance(exc, service.CodigoExistente | cambios.VersionDesactualizada):
        activo = exc.activo
        if isinstance(activo, Activo):
            # El vigente del ``412`` va con su foto, igual que la ficha (spec 015, R4), y con
            # precio solo para el admin: el contador también edita (spec 020, R7).
            # ``CodigoExistente`` ya trae un dict sin precio.
            activo = _ficha(activo, con_precio=_es_admin())
        cuerpo = {
            "error": {"code": exc.code, "message": exc.message, "request_id": current_request_id()},
            "activo": activo,
        }
        return jsonify(cuerpo), exc.status
    return error_response(exc.status, exc.code, exc.message)


def _ficha(activo: Activo, *, con_precio: bool) -> dict[str, object]:
    """Única forma de la ficha: el activo con su foto principal vigente (spec 012, R7) o
    ``null``. La usan las lecturas, las escrituras y el ``412`` (spec 015, R4)."""
    session = current_session()
    datos = service.vista(session, activo, con_precio=con_precio)
    foto = fotos_service.principal(session, activo.id)
    datos["foto"] = fotos_service.vista(foto) if foto else None
    return datos


def _con_foto(activo: Activo) -> dict[str, object]:
    """La ficha para quien lee: con precio solo si es admin (P13)."""
    return _ficha(activo, con_precio=_es_admin())


def _con_version(activo: Activo) -> ResponseReturnValue:
    """Respuesta de una escritura: la ficha con foto (precio solo para el admin) y su
    ``ETag``. El contador escribe con ``PATCH`` (spec 020, R7) y nunca recibe precio."""
    vista = _ficha(activo, con_precio=_es_admin())
    return jsonify(activo=vista), 200, {"ETag": f'"{activo.row_version}"'}


@bp.get("/por-codigo")
@require_auth
def por_codigo() -> ResponseReturnValue:
    session = current_session()
    try:
        activo = service.resolver(session, request.args.get("codigo"))
    except service.ErrorActivo as exc:
        return _error(exc)
    return jsonify(activo=_con_foto(activo))


@bp.get("/<uuid:id>")
@require_auth
def ficha(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002 - nombre del contrato
    session = current_session()
    try:
        activo = service.obtener(session, id)
    except service.ErrorActivo as exc:
        return _error(exc)
    return jsonify(activo=_con_foto(activo))


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
            ubicacion_id=request.args.get("ubicacion_id"),
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


def _empresa_vigente(session: Session) -> Empresa:
    """La empresa vigente del tenant para el Excel (spec 019, Q9): la misma lectura que
    ``GET /empresa`` (sin fila guardada, el nombre del tenant) bajo la sesión del tenant
    (RLS), y los bytes de su logo; sin logo o si no se puede leer (no existe, almacén
    sin configurar, disco o S3 con error), el archivo sale sin imagen (req. 8): el logo es
    decorativo y no tumba la exportación. Un fallo del almacén deja un WARNING con el tipo
    del error y, en S3, su código; sin clave, ruta, endpoint ni datos de la empresa."""
    datos = empresa_service.vista(session, current_user().tenant_id)
    logo: bytes | None = None
    if datos["logo"]:
        try:
            logo = empresa_service.leer_logo(
                session, current_app.extensions.get(EXTENSION_KEY), uuid.UUID(datos["logo"]["id"])
            )
        except empresa_service.ErrorEmpresa:
            logo = None
        except (OSError, ClientError, BotoCoreError) as exc:
            # Solo el tipo y, en S3, el código del error (un enum, sin datos); nunca la
            # clave, la ruta, el endpoint, el bucket ni datos de la empresa.
            detalle = type(exc).__name__
            if isinstance(exc, ClientError):
                detalle += f" {exc.response.get('Error', {}).get('Code', '')}".rstrip()
            logger.warning("Excel de activos sin logo: el almacén falló (%s).", detalle)
            logo = None
    return Empresa(
        nombre=datos["nombre"],
        direccion=datos["direccion"],
        nit=datos["nit"],
        telefono=datos["telefono"],
        correo=datos["correo"],
        vigente=True,
        logo=logo,
    )


@bp.get("/exportar")
@require_role("admin")
def exportar_lista() -> ResponseReturnValue:
    """La lista con los filtros vigentes, en Excel (spec 015, R1, R1a). Solo admin: el
    archivo lleva precios. Nombre fijo, sin caché y sin adivinar el tipo."""
    session = current_session()
    try:
        activos = service.buscar_todos(
            session,
            q=request.args.get("q"),
            estado=request.args.get("estado"),
            ubicacion_id=request.args.get("ubicacion_id"),
        )
    except service.ErrorActivo as exc:
        return _error(exc)
    hoy = datetime.now(exportar.HORA_COLOMBIA).date()
    nombre = exportar.nombre_archivo(hoy)
    contenido = exportar.a_excel(session, activos, _empresa_vigente(session), hoy)
    respuesta = Response(contenido, mimetype=exportar.XLSX)
    respuesta.headers["Content-Disposition"] = (
        f"attachment; filename=\"{nombre}\"; filename*=UTF-8''{nombre}"
    )
    respuesta.headers["Cache-Control"] = "no-store"
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    return respuesta


@bp.get("/<uuid:id>/historial")
@require_auth
def ver_historial(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002 - nombre del contrato
    try:
        pagina = historial.leer(
            current_session(), id, antes_de=request.args.get("antes_de"), con_precio=_es_admin()
        )
    except service.ErrorActivo as exc:
        return _error(exc)
    return jsonify(eventos=pagina.eventos, siguiente=pagina.siguiente)


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


# --- Spec 005: cambios (con If-Match) ------------------------------------------------------
# Editar es de ambos roles: el contador solo los campos descriptivos (spec 020, R7).
# Mover, estado y baja siguen siendo solo del admin.


@bp.patch("/<uuid:id>")
@require_role("admin", "contador")
def editar(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002 - nombre del contrato
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error_response(400, "solicitud_invalida", "La solicitud no es válida.")
    try:
        datos = cambios.edicion(body, current_user().rol)
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
