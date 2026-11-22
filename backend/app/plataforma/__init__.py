"""Consola de plataforma (spec 017; plan.md §2.1).

``register_plataforma(app)`` (T2) lee ``Config.plataforma``. Si la consola no está
habilitada (``PLATAFORMA_HABILITADA`` distinto de ``true``) no registra nada: toda ruta
``/plataforma`` responde ``404`` como una inexistente y no se crea ningún dato al
arrancar (R1). Si está habilitada registra:

- el blueprint de auth (``/plataforma/auth``), el de ``/plataforma/modulos`` y el de cada
  módulo de ``modulos.MODULOS``;
- la restricción de red opcional (``PLATAFORMA_REDES_PERMITIDAS``; fuera de la lista,
  ``404`` antes de cualquier otra cosa; compara ``request.remote_addr``, ya ajustada por
  ``ProxyFix`` si hay saltos de confianza);
- un tope de 4 KB para los cuerpos de ``/plataforma`` (``413``), como ``/auth``, salvo
  la subida del logo en el alta (``/plataforma/empresas/<id>/logo``, T7), que admite el
  logo de 2 MB y su formulario como ``/empresa/logo`` de la 013; un cuerpo chunked de
  esa ruta no se pre-lee: se limita al parsearlo, ya autenticado;
- ``Cache-Control: no-store`` y ``Referrer-Policy: no-referrer`` en toda respuesta de
  ``/plataforma``, también en las de error (R15), salvo en el ``404`` de una red no
  permitida: ese se marca con ``g.plataforma_oculta`` y sale con el mismo cuerpo y las
  mismas cabeceras que el ``404`` con la consola apagada, para no delatar que existe.

Los imports van dentro de la función: ``app.config`` importa ``app.plataforma.config`` y
este paquete no debe arrastrar las rutas al importarse.
"""

import io
import re

from flask import Flask, abort, g, request
from flask.wrappers import Response

PREFIX = "/plataforma"
MAX_BODY_BYTES = 4096
# Spec 017, T7: el logo del alta (2 MB) y su formulario, el mismo tope que la 013. El UUID
# en formato canónico (8-4-4-4-12 hex), el mismo que acepta el convertidor ``uuid`` de Flask.
_HEX = "[0-9a-fA-F]"
LOGO_PATH = re.compile(
    rf"/plataforma/empresas/{_HEX}{{8}}-{_HEX}{{4}}-{_HEX}{{4}}-{_HEX}{{4}}-{_HEX}{{12}}/logo"
)
LOGO_MAX_BODY_BYTES = 2 * 1024 * 1024 + 64 * 1024


def is_platform_path(path: str) -> bool:
    return path == PREFIX or path.startswith(PREFIX + "/")


def body_limit(path: str) -> int:
    return LOGO_MAX_BODY_BYTES if LOGO_PATH.fullmatch(path) else MAX_BODY_BYTES


def register_plataforma(app: Flask) -> None:
    from app.config import get_config
    from app.plataforma import modulos
    from app.plataforma.auth_routes import bp as auth_bp

    config = get_config(app).plataforma
    if not config.habilitada:
        return

    @app.before_request
    def _restrict_platform_network() -> None:
        if is_platform_path(request.path) and not config.permite(request.remote_addr):
            # El 404 debe ser idéntico al de la consola apagada: sin cabeceras propias.
            g.plataforma_oculta = True
            abort(404)

    @app.before_request
    def _limit_platform_body() -> None:
        if not is_platform_path(request.path):
            return
        limit = body_limit(request.path)
        request.max_content_length = limit
        if request.content_length is not None:
            if request.content_length > limit:
                abort(413)
            return
        if limit == LOGO_MAX_BODY_BYTES:
            # O1 de T7: el cuerpo chunked del logo no se pre-lee antes de autenticar. Lo
            # limita Werkzeug al parsear el formulario, después de ``require_desarrollador``
            # (``max_content_length`` con ``wsgi.input_terminated`` -> ``413``).
            return
        if request.environ.get("wsgi.input_terminated"):
            # Sin Content-Length (p. ej. chunked): se lee hasta un byte más.
            body = request.environ["wsgi.input"].read(limit + 1)
            if len(body) > limit:
                abort(413)
            request.environ["wsgi.input"] = io.BytesIO(body)

    @app.after_request
    def _platform_headers(response: Response) -> Response:
        if is_platform_path(request.path) and not g.get("plataforma_oculta", False):
            response.headers["Cache-Control"] = "no-store"
            response.headers["Referrer-Policy"] = "no-referrer"
        return response

    app.register_blueprint(auth_bp)
    app.register_blueprint(modulos.bp)
    for modulo in modulos.habilitados():
        app.register_blueprint(modulo.blueprint)
