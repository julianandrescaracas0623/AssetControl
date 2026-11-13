"""Rutas ``/invitaciones`` (spec 002, T8; R9, R10, Q13; plan.md §4).

``POST /invitaciones`` (solo ``admin``): cuerpo ``{email, rol}``. Responde ``201``
``{invitacion: {id, email, rol, expira_en}, enlace: "/invitacion#<token>"}``; el
enlace sale solo en esta respuesta. Cualquier otro campo del cuerpo (``tenant_id``,
``creada_por``, ``expira_en``...) se ignora: el tenant y ``creada_por`` salen del
token validado contra ``membresia``. Cuerpo mal formado -> ``400``
``solicitud_invalida``; sin token ``401``; ``contador`` ``403`` ``prohibido``
(antes de mirar el cuerpo).

Las cabeceras ``no-store``/``no-referrer`` y el límite de 4 KB los pone
``app.auth.http`` para todo ``/invitaciones``. Nada aquí registra el token.
"""

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from app.auth.decorators import current_session, current_user, require_role
from app.errors import error_response
from app.invitaciones import service

bp = Blueprint("invitaciones", __name__, url_prefix="/invitaciones")

BAD_REQUEST = ("solicitud_invalida", "La solicitud no es válida.")


@bp.post("")
@require_role("admin")
def crear() -> ResponseReturnValue:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error_response(400, *BAD_REQUEST)
    email, rol = body.get("email"), body.get("rol")
    if not isinstance(email, str) or not isinstance(rol, str):
        return error_response(400, *BAD_REQUEST)
    normalized = service.normalize_invitation_email(email)
    if normalized is None or rol not in service.INVITABLE_ROLES:
        return error_response(400, *BAD_REQUEST)

    created = service.create_invitation(
        current_session(),
        creada_por=current_user().usuario_id,
        email=normalized,
        rol=rol,
    )
    payload = {
        "invitacion": {
            "id": str(created.id),
            "email": created.email,
            "rol": created.rol,
            "expira_en": created.expira_en.isoformat(),
        },
        "enlace": created.enlace,
    }
    return jsonify(payload), 201
