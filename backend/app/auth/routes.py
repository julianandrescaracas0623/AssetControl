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
"""

from flask import Blueprint, abort, current_app, jsonify, request
from flask.typing import ResponseReturnValue
from flask.wrappers import Response

from app.auth import limits, service
from app.auth.credentials import ACCESS_TOKEN_TTL, REFRESH_TOKEN_TTL
from app.auth.decorators import current_user, require_auth
from app.auth.http import is_same_site_request, refresh_cookie_options
from app.config import get_config
from app.errors import error_response

bp = Blueprint("auth", __name__, url_prefix="/auth")

INVALID_CREDENTIALS = ("credenciales_invalidas", "Correo o contraseña incorrectos.")
NOT_AUTHENTICATED = ("no_autenticado", "Debes iniciar sesión.")
BAD_REQUEST = ("solicitud_invalida", "La solicitud no es válida.")


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
