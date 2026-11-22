"""Rutas ``/plataforma/auth`` (spec 017, T2; R2–R6; plan.md §4).

- ``POST /plataforma/auth/login`` (público, con límite): ``{email, password}``. Toda falla
  de credenciales responde el mismo ``401`` ``credenciales_invalidas``; un cuerpo mal
  formado, ``400``. Cuenta en ``plat_login_ip`` y ``plat_login_cuenta`` antes de Argon2
  (``429``/``503``); si entra, devuelve su intento.
- ``POST /plataforma/auth/refresh`` y ``/logout``: exigen ``X-AssetControl-CSRF: 1`` y el
  mismo sitio (``403`` antes de mirar la cookie), igual que el tenant. El refresh cuenta
  en su propio ``plat_refresh_ip`` (spec 017, T4; O1); cualquier rechazo
  es un ``401`` idéntico y sin ``Set-Cookie``. El logout responde siempre ``204`` y borra
  la cookie.
- ``GET /plataforma/auth/me`` (desarrollador): id, nombre y correo, leídos de la base.

La cookie de refresh es propia (``__Secure-plat-refresh``, o ``plat-refresh`` solo con
``ENVIRONMENT=development``), ``HttpOnly``, ``SameSite=Lax``, ``Path`` del prefijo de auth
de plataforma (con el ``SCRIPT_NAME`` que fije el despliegue). Las cabeceras ``no-store``
y ``no-referrer`` y el tope de 4 KB los pone ``app.plataforma`` para todo ``/plataforma``.
El valor de la cookie, la contraseña y el correo no se registran.
"""

from flask import Blueprint, abort, current_app, jsonify, request
from flask.typing import ResponseReturnValue
from flask.wrappers import Response

from app.auth import limits
from app.auth.http import is_same_site_request
from app.auth.routes import BAD_REQUEST, INVALID_CREDENTIALS
from app.config import get_config
from app.errors import error_response
from app.plataforma import servicio
from app.plataforma.credenciales import PLATAFORMA_ACCESS_TTL, PLATAFORMA_REFRESH_TTL
from app.plataforma.decoradores import (
    NOT_AUTHENTICATED,
    current_desarrollador,
    require_desarrollador,
)

bp = Blueprint("plataforma_auth", __name__, url_prefix="/plataforma/auth")

COOKIE_SECURE_NAME = "__Secure-plat-refresh"
COOKIE_DEVELOPMENT_NAME = "plat-refresh"


def cookie_options() -> dict[str, object]:
    """Atributos de la cookie de refresh de plataforma: ``Secure`` salvo ``development``."""
    secure = get_config(current_app).secure_cookies
    return {
        "key": COOKIE_SECURE_NAME if secure else COOKIE_DEVELOPMENT_NAME,
        "secure": secure,
        "httponly": True,
        "samesite": "Lax",
        "path": f"{request.script_root}{bp.url_prefix}",
    }


def _session_response(result: servicio.PlatformSession) -> Response:
    response = jsonify(
        access_token=result.access_token,
        token_type="Bearer",  # noqa: S106 - tipo de token (RFC 6750), no un secreto
        expires_in=int(PLATAFORMA_ACCESS_TTL.total_seconds()),
        **result.desarrollador.to_json(),
    )
    options = cookie_options()
    response.set_cookie(
        options.pop("key"),
        result.refresh_cookie_value,
        max_age=int(PLATAFORMA_REFRESH_TTL.total_seconds()),
        **options,
    )
    return response


def _cookie_value() -> str | None:
    return request.cookies.get(cookie_options()["key"])


@bp.post("/login")
def login() -> ResponseReturnValue:
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return error_response(400, *BAD_REQUEST)
    email, password = body.get("email"), body.get("password")
    if not isinstance(email, str) or not isinstance(password, str):
        return error_response(400, *BAD_REQUEST)
    # Antes de Argon2 y de buscar la cuenta (429/503 si no se puede seguir).
    attempts = limits.limit_platform_login(email)
    result = servicio.login(email, password)
    if result is None:
        return error_response(401, *INVALID_CREDENTIALS)
    limits.give_back(attempts)
    return _session_response(result)


@bp.post("/refresh")
def refresh() -> ResponseReturnValue:
    if not is_same_site_request():
        abort(403)
    attempts = limits.limit_platform_refresh()
    result = servicio.refresh(_cookie_value())
    if result is None:
        return error_response(401, *NOT_AUTHENTICATED)
    limits.give_back(attempts)
    return _session_response(result)


@bp.post("/logout")
def logout() -> ResponseReturnValue:
    if not is_same_site_request():
        abort(403)
    servicio.logout(_cookie_value())
    response = Response(status=204)
    options = cookie_options()
    response.delete_cookie(options.pop("key"), **options)
    return response


@bp.get("/me")
@require_desarrollador
def me() -> ResponseReturnValue:
    return jsonify(current_desarrollador().to_json())
