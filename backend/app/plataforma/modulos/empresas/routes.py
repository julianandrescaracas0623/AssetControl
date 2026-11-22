"""Rutas ``/plataforma/empresas`` (spec 017, T3b; R16–R22; plan.md §4). Solo desarrolladores.

- ``GET /plataforma/empresas?q=&estado=activas|desactivadas|todas``: identidad, logo sí/no
  y conteos de cada empresa (R21). ``q`` filtra por nombre (sin distinguir mayúsculas).
- ``POST /plataforma/empresas``: ``{id, nombre, direccion, nit?, telefono?, correo?,
  admin: {nombre, email, password, password_confirmacion}}`` -> ``201 {empresa_id,
  admin_id}``; ``400``, ``422`` (con ``campo``), ``409 empresa_existente`` /
  ``email_en_uso``, ``503`` si Argon2 está saturado.
- ``PATCH /plataforma/empresas/{id}``: ``{activa}`` -> ``200 {id, activa}``; ``404``.
- ``POST /plataforma/empresas/{id}/logo`` (T7; R23; C1: R44): ``multipart/form-data`` con
  exactamente ``logo_id`` (UUID canónico) y ``archivo`` -> ``201 {logo: {id}}`` (logo nuevo o
  reemplazo del vigente; ``200`` si ese logo ya es el vigente); ``400``,
  ``413``/``415``/``422`` (reglas de la 013), ``404``, ``409 logo_id_en_uso`` /
  ``empresa_sin_datos`` / ``empresa_sin_admin``, ``503 logos_no_disponibles`` sin almacén. El
  tope de su cuerpo es el del logo de la 013.
- ``GET /plataforma/empresas/{id}/ficha`` (C1; R41): ``{nombre, direccion, nit, telefono,
  correo, tiene_logo}``; ``404``, ``409 empresa_sin_datos``.
- ``PUT /plataforma/empresas/{id}/ficha`` (C1; R42, R43): los cinco campos de la ficha ->
  ``200`` con la ficha resultante; ``400``, ``422`` (con ``campo``), ``404``, ``409
  empresa_sin_datos``, ``503`` (fila bloqueada más de 5 s).

``POST``, ``PATCH`` y ``PUT`` cuentan en ``plat_accion`` por desarrollador (spec 017, T4; O1;
C1: R52) antes de validar, de Argon2 y de la base: ``429``/``503``. Los ``GET`` no cuentan.

Todas con ``require_desarrollador`` (token de plataforma y ``desarrollador.activo`` en cada
petición); usan ``Authorization: Bearer``, no cookies, así que no llevan CSRF (plan §2.7).
``no-store``, ``no-referrer`` y el tope de 4 KB los pone ``app.plataforma``. El cuerpo no
se registra.
"""

import uuid

from flask import Blueprint, current_app, jsonify, request
from flask.typing import ResponseReturnValue

from app.auth import limits
from app.errors import current_request_id, error_response
from app.fotos.almacen import EXTENSION_KEY, Almacen
from app.plataforma.decoradores import (
    current_desarrollador,
    current_plataforma_session,
    require_desarrollador,
)
from app.plataforma.modulos.empresas import service

bp = Blueprint("plataforma_empresas", __name__, url_prefix="/plataforma/empresas")


def _error(exc: service.ErrorEmpresas) -> ResponseReturnValue:
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


@bp.get("")
@require_desarrollador
def listar() -> ResponseReturnValue:
    try:
        q, estado = service.filtros(request.args)
        empresas = service.listar(current_plataforma_session(), q, estado)
    except service.ErrorEmpresas as exc:
        return _error(exc)
    return jsonify(empresas=empresas)


@bp.post("")
@require_desarrollador
def crear() -> ResponseReturnValue:
    limits.limit_platform_action(current_desarrollador().id)
    try:
        alta = service.validar_alta(request.get_json(silent=True))
        creada = service.crear(current_plataforma_session(), alta)
    except service.ErrorEmpresas as exc:
        return _error(exc)
    return jsonify(creada.to_json()), 201


@bp.patch("/<uuid:id>")
@require_desarrollador
def cambiar_estado(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002 - nombre del contrato
    limits.limit_platform_action(current_desarrollador().id)
    try:
        activa = service.validar_estado(request.get_json(silent=True))
        activo = service.cambiar_estado(current_plataforma_session(), id, activa)
    except service.ErrorEmpresas as exc:
        return _error(exc)
    return jsonify(id=str(id), activa=activo)


@bp.get("/<uuid:id>/ficha")
@require_desarrollador
def leer_ficha(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002 - nombre del contrato
    try:
        ficha = service.leer_ficha(current_plataforma_session(), id)
    except service.ErrorEmpresas as exc:
        return _error(exc)
    return jsonify(ficha)


@bp.put("/<uuid:id>/ficha")
@require_desarrollador
def actualizar_ficha(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002 - nombre del contrato
    limits.limit_platform_action(current_desarrollador().id)
    try:
        ficha = service.validar_ficha(request.get_json(silent=True))
        resultado = service.actualizar_ficha(current_plataforma_session(), id, ficha)
    except service.ErrorEmpresas as exc:
        return _error(exc)
    return jsonify(resultado)


FORMULARIO_LOGO = frozenset({"logo_id"})
ARCHIVOS_LOGO = frozenset({"archivo"})


def _almacen() -> Almacen | None:
    return current_app.extensions.get(EXTENSION_KEY)


def _formulario_logo() -> tuple[uuid.UUID, bytes]:
    """Exactamente ``logo_id`` (UUID canónico) y ``archivo``, una vez cada uno; si no, ``400``."""
    form, files = request.form, request.files
    if set(form) != FORMULARIO_LOGO or set(files) != ARCHIVOS_LOGO:
        raise service.ErrorEmpresas()
    if len(form.getlist("logo_id")) != 1 or len(files.getlist("archivo")) != 1:
        raise service.ErrorEmpresas()
    logo_id = service.parse_uuid(form["logo_id"])
    return logo_id, files["archivo"].read(service.LOGO_MAX_BYTES + 1)


@bp.post("/<uuid:id>/logo")
@require_desarrollador
def subir_logo(id: uuid.UUID) -> ResponseReturnValue:  # noqa: A002 - nombre del contrato
    limits.limit_platform_action(current_desarrollador().id)
    try:
        logo_id, datos = _formulario_logo()
        registrado = service.subir_logo(
            current_plataforma_session(), _almacen(), tenant_id=id, logo_id=logo_id, datos=datos
        )
    except service.ErrorEmpresas as exc:
        return _error(exc)
    return jsonify(logo={"id": str(registrado.logo_id)}), 201 if registrado.creado else 200
