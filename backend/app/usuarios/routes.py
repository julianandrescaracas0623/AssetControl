"""Ruta ``GET /usuarios`` (solo ``admin``): la lista de usuarios de la empresa.

Lee las membresías de la sesión del tenant con su usuario. RLS limita la consulta a la
empresa; nunca se devuelven contraseñas ni hashes (la aplicación no tiene ``SELECT`` sobre
``usuario.password_hash``). Ningún cuerpo ni nombre se registra.
"""

from flask import Blueprint, jsonify
from flask.typing import ResponseReturnValue
from sqlalchemy import func, select

from app.auth.decorators import current_session, require_role
from app.auth.models import Membresia, Usuario

bp = Blueprint("usuarios", __name__, url_prefix="/usuarios")


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
