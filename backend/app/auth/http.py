"""Política HTTP de las rutas de acceso (spec 002, T4; plan.md §2.2, A25, Q9).

En ``/auth`` e ``/invitaciones`` (y todo lo que cuelga de ellas):

- ``Cache-Control: no-store`` y ``Referrer-Policy: no-referrer`` en toda
  respuesta, también en las de error.
- Cuerpo máximo de 4 KB: ``413`` (``cuerpo_demasiado_grande``) si
  ``Content-Length`` lo supera, y el flujo queda limitado para cuerpos sin
  ``Content-Length``.

Las pruebas por ruta se escriben en T6/T8/T9, cuando existan las rutas.
"""

import io

from flask import Flask, abort, request
from flask.wrappers import Response

from app.config import Config

AUTH_PATH_PREFIXES: tuple[str, ...] = ("/auth", "/invitaciones")
AUTH_MAX_BODY_BYTES = 4096
REFRESH_COOKIE_SECURE_NAME = "__Secure-refresh"
REFRESH_COOKIE_DEVELOPMENT_NAME = "refresh"


def is_auth_path(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix + "/") for prefix in AUTH_PATH_PREFIXES)


def refresh_cookie_options(config: Config) -> dict[str, object]:
    """Atributos de la cookie de refresh: ``Secure`` salvo ``development`` explícito."""
    secure = config.secure_cookies
    return {
        "key": REFRESH_COOKIE_SECURE_NAME if secure else REFRESH_COOKIE_DEVELOPMENT_NAME,
        "secure": secure,
        "httponly": True,
        "samesite": "Lax",
        "path": "/auth",
    }


def register_auth_http_policy(app: Flask) -> None:
    @app.before_request
    def _limit_auth_body() -> None:
        if not is_auth_path(request.path):
            return
        request.max_content_length = AUTH_MAX_BODY_BYTES
        if request.content_length is not None:
            if request.content_length > AUTH_MAX_BODY_BYTES:
                abort(413)
            return
        if request.environ.get("wsgi.input_terminated"):
            # Sin Content-Length (p. ej. chunked) Werkzeug truncaría en silencio al
            # límite: se lee hasta un byte más y se responde 413 si lo supera.
            body = request.environ["wsgi.input"].read(AUTH_MAX_BODY_BYTES + 1)
            if len(body) > AUTH_MAX_BODY_BYTES:
                abort(413)
            request.environ["wsgi.input"] = io.BytesIO(body)

    @app.after_request
    def _auth_headers(response: Response) -> Response:
        if is_auth_path(request.path):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
        return response
