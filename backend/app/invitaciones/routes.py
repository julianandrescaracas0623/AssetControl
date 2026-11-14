"""Rutas ``/invitaciones`` (spec 002, T8–T9; R9, R10, R11, Q13, Q16; plan.md §4).

``POST /invitaciones`` (solo ``admin``): cuerpo ``{email, rol}``. Responde ``201``
``{invitacion: {id, email, rol, expira_en}, enlace: "/invitacion#<token>"}``; el
enlace sale solo en esta respuesta. Cualquier otro campo del cuerpo (``tenant_id``,
``creada_por``, ``expira_en``...) se ignora: el tenant y ``creada_por`` salen del
token validado contra ``membresia``. Cuerpo mal formado -> ``400``
``solicitud_invalida``; sin token ``401``; ``contador`` ``403`` ``prohibido``
(antes de mirar el cuerpo).

``POST /invitaciones/validar`` (T9, público): cuerpo ``{token}``; ``200
{"vigente": true|false}``. Vencida, usada, inexistente o con cualquier formato dan
el mismo ``{"vigente": false}``; no consume.

``POST /invitaciones/aceptar`` (T9, público): cuerpo ``{token, nombre, password}``,
sin email; cualquier otro campo (``email``, ``rol``, ``tenant_id``...) y las
credenciales de la petición (JWT, cookie) se ignoran. ``201`` con el mismo cuerpo
que el login y la cookie de refresh (sesión emitida tras el ``COMMIT``, R11).
Errores: ``400 solicitud_invalida`` (cuerpo, ``nombre`` vacío o con caracteres de
control), ``400 contrasena_*`` (Q9, antes de mirar el token), ``400
invitacion_invalida`` idéntico para vencida, usada, inexistente, mal formada o
email ya registrado (Q16), ``500`` genérico si la cuenta se creó pero la sesión no
(A22: entra con el login).

Las cabeceras ``no-store``/``no-referrer`` y el límite de 4 KB los pone
``app.auth.http`` para todo ``/invitaciones``. Límite de tasa (T10, R13): validar y
aceptar por IP, contados antes de la base y de Argon2 (aceptar, tras la política
Q9); ``429`` genérico o ``503``. Nada aquí registra el token ni la contraseña.
"""

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from app.auth import limits
from app.auth.credentials import PasswordPolicyError, check_password_policy
from app.auth.decorators import current_session, current_user, require_role
from app.auth.routes import session_response
from app.errors import error_response
from app.invitaciones import service

bp = Blueprint("invitaciones", __name__, url_prefix="/invitaciones")

BAD_REQUEST = ("solicitud_invalida", "La solicitud no es válida.")
INVALID_INVITATION = (
    "invitacion_invalida",
    "El enlace de invitación no es válido o ya no está vigente.",
)


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


# --- Validar y aceptar (T9): públicos, sin require_auth ni tenant_session ------------


def _text_fields(*names: str) -> tuple[str, ...] | None:
    """Los campos ``names`` del cuerpo JSON, o ``None`` si el cuerpo o alguno no es texto."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None
    values = tuple(body.get(name) for name in names)
    if not all(isinstance(value, str) for value in values):
        return None
    return values


@bp.post("/validar")
def validar() -> ResponseReturnValue:
    fields = _text_fields("token")
    if fields is None:
        return error_response(400, *BAD_REQUEST)
    (token,) = fields
    limits.limit_validate()
    return jsonify(vigente=service.is_valid_invitation(token))


@bp.post("/aceptar")
def aceptar() -> ResponseReturnValue:
    fields = _text_fields("token", "nombre", "password")
    if fields is None:
        return error_response(400, *BAD_REQUEST)
    token, nombre, password = fields
    nombre = service.normalize_nombre(nombre)
    if nombre is None:
        return error_response(400, *BAD_REQUEST)

    policy_error = None
    try:
        # Q9 antes de contar: no depende del token ni cuesta Argon2.
        check_password_policy(password)
        limits.limit_accept()
        result = service.accept_invitation(token, nombre, password)
    except PasswordPolicyError as exc:
        policy_error = (exc.code, str(exc))
    if policy_error is not None:
        return error_response(400, *policy_error)
    if result is None:
        return error_response(400, *INVALID_INVITATION)
    response = session_response(result)
    response.status_code = 201
    return response
