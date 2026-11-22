"""Rutas ``/auth`` (spec 002, T6–T7): login, usuario actual, refresh y logout.

Las cabeceras ``no-store``/``no-referrer`` y el límite de 4 KB los pone
``app.auth.http`` para todo ``/auth``. Toda falla de credenciales responde
``401`` ``credenciales_invalidas`` con el mismo mensaje; un cuerpo mal formado
(independiente de la cuenta) es ``400`` ``solicitud_invalida``.

``POST /auth/refresh`` y ``POST /auth/logout`` (T7) exigen la cabecera
personalizada y el mismo sitio (Q14, ``403`` antes de mirar la cookie). El
refresh responde lo mismo que el login y rota la cookie; cualquier rechazo es un
``401`` ``no_autenticado`` idéntico y sin ``Set-Cookie`` (borrarla haría que la
pestaña que pierde una carrera dentro de la ventana de gracia cerrara la sesión
de la que ganó). El logout siempre responde ``204`` y limpia la cookie, haya o
no una válida. El valor de la cookie no se registra.

Límites de tasa (T10, R13; ``app.auth.limits``): login por IP y cuenta y refresh por
IP, contados antes de Argon2 y de la base; ``429`` genérico o ``503`` si no se puede
contar. Si la petición termina bien se devuelve su intento (solo cuentan los fallos).
El logout no se limita.

Recuperar y restablecer contraseña (spec 014, T4; plan §5): públicos, sin sesión ni
cookies; exigen la cabecera personalizada y el mismo sitio (``403`` antes de mirar el
cuerpo, R14). ``POST /auth/recuperar`` ``{email}`` responde **siempre** el mismo ``202``
(R1; solo la forma da ``400``, y los límites ``429``/``503``); sin correo configurado,
el mismo ``202`` sin tocar la base. ``POST /auth/restablecer`` ``{token, password}``:
``400 contrasena_*`` antes de contar, ``restablecer_ip``, Argon2 siempre, ``204`` sin
sesión (R10) o ``400 enlace_invalido`` idéntico para todo enlace no canjeable.

Cambiar la contraseña (spec 017, T4; R26–R27, A16): ``POST /auth/cambiar-contrasena``
``{actual, nueva, confirmacion}`` con ``Authorization: Bearer`` (cualquier rol; está en la
lista blanca de ``require_auth`` aunque la cuenta tenga ``debe_cambiar_password``). Forma
mala -> ``400``; política de la 002, confirmación distinta o nueva igual a la actual ->
``422`` (antes de contar, sin depender de la cuenta); cuenta en ``login_ip`` y
``login_cuenta`` antes de Argon2 (``429``/``503``); actual errónea -> ``401
credenciales_invalidas`` (el intento queda contado). Si cambia, responde como el login
(sesión nueva, cookie de una familia nueva; las demás quedan revocadas) y devuelve el
intento. Ninguna contraseña se registra.
"""

from flask import Blueprint, abort, current_app, jsonify, request
from flask.typing import ResponseReturnValue
from flask.wrappers import Response

from app.auth import limits, recuperacion, service
from app.auth.credentials import (
    ACCESS_TOKEN_TTL,
    REFRESH_TOKEN_TTL,
    PasswordPolicyError,
    check_password_policy,
)
from app.auth.decorators import current_session, current_user, require_auth
from app.auth.http import is_same_site_request, refresh_cookie_options
from app.config import get_config
from app.correo import correo_activo
from app.errors import error_response

bp = Blueprint("auth", __name__, url_prefix="/auth")

INVALID_CREDENTIALS = ("credenciales_invalidas", "Correo o contraseña incorrectos.")
NOT_AUTHENTICATED = ("no_autenticado", "Debes iniciar sesión.")
BAD_REQUEST = ("solicitud_invalida", "La solicitud no es válida.")
PASSWORDS_DIFFER = ("contrasenas_distintas", "Las contraseñas no coinciden.")
PASSWORD_REPEATED = (
    "contrasena_repetida",
    "La contraseña nueva debe ser distinta de la actual.",
)


def session_response(result: service.LoginResult) -> Response:
    """Cuerpo común de login, refresh y aceptar invitación (T9), con la cookie de refresh nueva."""
    response = jsonify(
        access_token=result.access_token,
        token_type="Bearer",  # noqa: S106 - tipo de token (RFC 6750), no un secreto
        expires_in=int(ACCESS_TOKEN_TTL.total_seconds()),
        **result.user.to_json(),
    )
    options = refresh_cookie_options(get_config(current_app))
    response.set_cookie(
        options.pop("key"),
        result.refresh_cookie_value,
        max_age=int(REFRESH_TOKEN_TTL.total_seconds()),
        **options,
    )
    return response


def _refresh_cookie_value() -> str | None:
    name = refresh_cookie_options(get_config(current_app))["key"]
    return request.cookies.get(name)


@bp.post("/login")
def login() -> ResponseReturnValue:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error_response(400, *BAD_REQUEST)
    email, password = body.get("email"), body.get("password")
    if not isinstance(email, str) or not isinstance(password, str):
        return error_response(400, *BAD_REQUEST)

    # T10: antes de Argon2 y de buscar la cuenta (429/503 si no se puede seguir).
    attempts = limits.limit_login(email)
    result = service.login(email, password)
    if result is None:
        return error_response(401, *INVALID_CREDENTIALS)
    limits.give_back(attempts)
    return session_response(result)


@bp.post("/refresh")
def refresh() -> ResponseReturnValue:
    if not is_same_site_request():
        abort(403)
    attempts = limits.limit_refresh()
    result = service.refresh(_refresh_cookie_value())
    if result is None:
        return error_response(401, *NOT_AUTHENTICATED)
    limits.give_back(attempts)
    return session_response(result)


@bp.post("/logout")
def logout() -> ResponseReturnValue:
    if not is_same_site_request():
        abort(403)
    service.logout(_refresh_cookie_value())
    response = Response(status=204)
    options = refresh_cookie_options(get_config(current_app))
    response.delete_cookie(options.pop("key"), **options)
    return response


@bp.get("/me")
@require_auth
def me() -> ResponseReturnValue:
    return jsonify(current_user().to_json())


# --- Recuperar y restablecer contraseña (spec 014, T4) -----------------------------------


def _text_fields(*names: str) -> tuple[str, ...] | None:
    """Los campos ``names`` del cuerpo JSON, o ``None`` si el cuerpo o alguno no es texto."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None
    values = tuple(body.get(name) for name in names)
    if not all(isinstance(value, str) for value in values):
        return None
    return values


@bp.post("/recuperar")
def recuperar() -> ResponseReturnValue:
    if not is_same_site_request():
        abort(403)
    fields = _text_fields("email")
    if fields is None:
        return error_response(400, *BAD_REQUEST)
    (email,) = fields
    # Requisito 4 de T3: sin correo configurado no se cuenta, no se crea ni se invalida
    # ningún enlace; la respuesta es la misma para todos.
    if correo_activo(current_app):
        recuperacion.solicitar(email)
    return jsonify(mensaje=recuperacion.RECOVERY_MESSAGE), 202


@bp.post("/restablecer")
def restablecer() -> ResponseReturnValue:
    if not is_same_site_request():
        abort(403)
    fields = _text_fields("token", "password")
    if fields is None:
        return error_response(400, *BAD_REQUEST)
    token, password = fields
    policy_error = None
    try:
        # R11: antes de contar y de Argon2; no depende del token.
        check_password_policy(password)
    except PasswordPolicyError as exc:
        policy_error = (exc.code, str(exc))
    if policy_error is not None:
        return error_response(400, *policy_error)
    limits.limit_reset()
    if not recuperacion.restablecer(token, password):
        return error_response(400, *recuperacion.INVALID_LINK)
    return Response(status=204)


# --- Cambiar la contraseña (spec 017, T4) ------------------------------------------------


@bp.post("/cambiar-contrasena")
@require_auth
def cambiar_contrasena() -> ResponseReturnValue:
    fields = _text_fields("actual", "nueva", "confirmacion")
    if fields is None:
        return error_response(400, *BAD_REQUEST)
    actual, nueva, confirmacion = fields
    policy_error = None
    try:
        # Antes de contar y de Argon2; no depende de la cuenta.
        check_password_policy(nueva)
    except PasswordPolicyError as exc:
        policy_error = (exc.code, str(exc))
    if policy_error is not None:
        return error_response(422, *policy_error)
    if confirmacion != nueva:
        return error_response(422, *PASSWORDS_DIFFER)
    if nueva == actual:
        return error_response(422, *PASSWORD_REPEATED)

    user = current_user()
    attempts = limits.limit_login(user.email)
    result = service.cambiar_contrasena(current_session(), user, actual, nueva)
    if result is None:
        return error_response(401, *INVALID_CREDENTIALS)
    limits.give_back(attempts)
    return session_response(result)
