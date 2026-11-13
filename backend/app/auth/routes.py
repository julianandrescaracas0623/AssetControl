"""Rutas ``/auth`` (spec 002, T6): ``POST /auth/login`` y ``GET /auth/me``.

Las cabeceras ``no-store``/``no-referrer`` y el límite de 4 KB los pone
``app.auth.http`` para todo ``/auth``. Toda falla de credenciales responde
``401`` ``credenciales_invalidas`` con el mismo mensaje; un cuerpo mal formado
(independiente de la cuenta) es ``400`` ``solicitud_invalida``.
"""

from flask import Blueprint, current_app, jsonify, request
from flask.typing import ResponseReturnValue

from app.auth import service
from app.auth.credentials import ACCESS_TOKEN_TTL, REFRESH_TOKEN_TTL
from app.auth.http import refresh_cookie_options
from app.config import get_config
from app.errors import error_response

bp = Blueprint("auth", __name__, url_prefix="/auth")

INVALID_CREDENTIALS = ("credenciales_invalidas", "Correo o contraseña incorrectos.")
NOT_AUTHENTICATED = ("no_autenticado", "Debes iniciar sesión.")
BAD_REQUEST = ("solicitud_invalida", "La solicitud no es válida.")


@bp.post("/login")
def login() -> ResponseReturnValue:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error_response(400, *BAD_REQUEST)
    email, password = body.get("email"), body.get("password")
    if not isinstance(email, str) or not isinstance(password, str):
        return error_response(400, *BAD_REQUEST)

    result = service.login(email, password)
    if result is None:
        return error_response(401, *INVALID_CREDENTIALS)

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


@bp.get("/me")
def me() -> ResponseReturnValue:
    user = service.authenticate(request.headers.get("Authorization"))
    if user is None:
        return error_response(401, *NOT_AUTHENTICATED)
    return jsonify(user.to_json())
