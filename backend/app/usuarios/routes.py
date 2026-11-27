"""Rutas ``/usuarios`` (solo ``admin``): lista y cambio de rol y de activación.

``GET /usuarios``: lee las membresías de la sesión del tenant con su usuario. RLS limita la
consulta a la empresa; nunca se devuelven contraseñas ni hashes (la aplicación no tiene
``SELECT`` sobre ``usuario.password_hash``).

``PUT /usuarios/{usuario_id}`` (0033): cuerpo exacto ``{rol, activa}``. ``200
{id, rol, activa}``. ``400 solicitud_invalida`` con otra clave o valor; ``403`` si quien
llama no es admin activo; ``404 no_encontrado`` si esa persona no tiene membresía en la
empresa; ``409`` con ``cambio_propio_no_permitido`` o ``ultimo_admin`` (sin cambiar nada);
``503`` si el candado de membresías de la empresa sigue ocupado. La regla vive en
``acceso.cambiar_membresia`` (ver ``service``). Ningún cuerpo ni nombre se registra.
"""

import uuid

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue
from sqlalchemy import func, select

from app.auth.decorators import current_session, current_user, require_role
from app.auth.models import Membresia, Usuario
from app.errors import error_response
from app.invitaciones.service import INVITABLE_ROLES
from app.usuarios import service

bp = Blueprint("usuarios", __name__, url_prefix="/usuarios")

BAD_REQUEST = ("solicitud_invalida", "La solicitud no es válida.")
# Código de rechazo de la base -> (HTTP, código, mensaje). Sin datos de la persona.
RECHAZOS = {
    "usuario_no_encontrado": (404, "no_encontrado", "El recurso no existe."),
    "cambio_propio_no_permitido": (
        409,
        "cambio_propio_no_permitido",
        "No puedes cambiar tu propio rol ni desactivarte. Pídelo a otro administrador.",
    ),
    "ultimo_admin": (
        409,
        "ultimo_admin",
        "Debe quedar al menos un administrador activo en la empresa.",
    ),
    "no_autorizado": (403, "prohibido", "No tienes permiso para esta acción."),
}


@bp.get("")
@require_role("admin")
def listar() -> ResponseReturnValue:
    filas = (
        current_session()
        .execute(
            select(
                Membresia.usuario_id,
                Usuario.nombre,
                Usuario.email,
                Membresia.rol,
                Membresia.activa,
                Usuario.debe_cambiar_password,
            )
            .join(Usuario, Usuario.id == Membresia.usuario_id)
            .order_by(func.lower(Usuario.nombre), Usuario.email)
        )
        .all()
    )
    return jsonify(
        usuarios=[
            {
                "id": str(usuario_id),
                "nombre": nombre,
                "email": email,
                "rol": rol,
                "activa": activa,
                "debe_cambiar_password": debe_cambiar,
            }
            for usuario_id, nombre, email, rol, activa, debe_cambiar in filas
        ]
    )


@bp.put("/<uuid:usuario_id>")
@require_role("admin")
def cambiar(usuario_id: uuid.UUID) -> ResponseReturnValue:
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or set(body) != {"rol", "activa"}:
        return error_response(400, *BAD_REQUEST)
    rol, activa = body["rol"], body["activa"]
    if not isinstance(rol, str) or rol not in INVITABLE_ROLES or not isinstance(activa, bool):
        return error_response(400, *BAD_REQUEST)

    try:
        resultado = service.cambiar(
            current_session(),
            actor_id=current_user().usuario_id,
            usuario_id=usuario_id,
            rol=rol,
            activa=activa,
        )
    except service.CambioRechazado as exc:
        status, code, message = RECHAZOS[exc.codigo]
        return error_response(status, code, message)
    return jsonify(id=str(usuario_id), rol=resultado.rol, activa=resultado.activa)
