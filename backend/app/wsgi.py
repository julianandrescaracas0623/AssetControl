"""App de producción en un solo origen (spec 010b, T1; R1, R2, R4; Q3).

gunicorn carga ``app.wsgi:application``: la web compilada (``web/dist``) en ``/`` y la
API Flask montada bajo ``/api`` con ``DispatcherMiddleware``. Así la web y la API
comparten origen: sin CORS, la cookie de refresh viaja con ``Path=/api/auth`` y la
comprobación de mismo sitio (Q14) vale tal cual. Toda respuesta, de la web o de la API,
pasa por ``ConCabeceras``.

En desarrollo nada de esto se usa: Vite sirve la web y su proxy reenvía ``/api``.
"""

import mimetypes
import os
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from flask import Flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.security import safe_join
from werkzeug.utils import send_file
from werkzeug.wrappers import Request, Response

WEB_DIST_VAR = "WEB_DIST_DIR"
INMUTABLE = "public, max-age=31536000, immutable"
CORTA = "public, max-age=3600"

# R4. connect-src 'self': la API está en el mismo origen. blob: para las descargas del
# informe (spec 009) y el video de la cámara; data: para el ícono vacío de index.html.
CSP = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "media-src 'self' blob:",
        "font-src 'self'",
        "connect-src 'self'",
        "worker-src 'self' blob:",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    )
)
CABECERAS: tuple[tuple[str, str], ...] = (
    ("Content-Security-Policy", CSP),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "same-origin"),
    ("Permissions-Policy", "camera=(self), microphone=(), geolocation=(), payment=()"),
    ("Cross-Origin-Opener-Policy", "same-origin"),
)
HSTS = ("Strict-Transport-Security", "max-age=31536000; includeSubDomains")

WsgiApp = Callable[[dict[str, Any], Callable[..., Any]], Iterable[bytes]]


# Spec 012 (R10): el manifest del atajo tipo app con su tipo, aunque el sistema no lo traiga.
mimetypes.add_type("application/manifest+json", ".webmanifest")


class Estaticos:
    """La web compilada: archivos con huella, archivos de la raíz e ``index.html``.

    - ``/assets/<archivo>``: caché larga e inmutable (Vite les pone huella); si no
      existe, ``404`` (nunca ``index.html``: un script que falta no debe recibir HTML).
    - Un archivo de la raíz que existe (``robots.txt``): caché corta. Uno con extensión
      de archivo estático que no existe: ``404``.
    - Cualquier otra ruta es de la SPA (también ``/admin/activos/AC.01``): ``index.html``
      sin caché, para que una versión nueva se vea al recargar.
    """

    EXTENSIONES_RAIZ = frozenset(
        {".ico", ".png", ".svg", ".txt", ".webmanifest", ".json", ".js", ".css", ".map", ".xml"}
    )

    def __init__(self, dist: Path) -> None:
        self.dist = dist.resolve()
        self.indice = self.dist / "index.html"
        if not self.indice.is_file():
            raise RuntimeError(f"No se encontró index.html de la web compilada en {self.dist}.")

    def _archivo(self, ruta: str) -> Path | None:
        unido = safe_join(str(self.dist), ruta)
        if unido is None:
            return None
        archivo = Path(unido)
        return archivo if archivo.is_file() else None

    def __call__(
        self, environ: dict[str, Any], start_response: Callable[..., Any]
    ) -> Iterable[bytes]:
        request = Request(environ)
        respuesta = self._responder(request)
        return respuesta(environ, start_response)

    def _responder(self, request: Request) -> Response:
        if request.method not in ("GET", "HEAD"):
            return Response("Método no permitido.", status=405, headers={"Allow": "GET, HEAD"})
        ruta = request.path.lstrip("/")
        if ruta.startswith("assets/"):
            archivo = self._archivo(ruta)
            if archivo is None:
                return Response("No encontrado.", status=404, mimetype="text/plain")
            return self._enviar(request, archivo, INMUTABLE)
        if ruta and "/" not in ruta:
            archivo = self._archivo(ruta)
            if archivo is not None and archivo != self.indice:
                return self._enviar(request, archivo, CORTA)
            if Path(ruta).suffix.lower() in self.EXTENSIONES_RAIZ:
                return Response("No encontrado.", status=404, mimetype="text/plain")
        return self._enviar(request, self.indice, "no-cache")

    @staticmethod
    def _enviar(request: Request, archivo: Path, cache: str) -> Response:
        respuesta = send_file(archivo, request.environ, conditional=True, max_age=None)
        respuesta.headers["Cache-Control"] = cache
        return respuesta


class ConCabeceras:
    """Agrega las cabeceras de seguridad (R4) a toda respuesta; HSTS solo en producción."""

    def __init__(self, app: WsgiApp, *, produccion: bool) -> None:
        self.app = app
        self.cabeceras = (*CABECERAS, HSTS) if produccion else CABECERAS

    def __call__(
        self, environ: dict[str, Any], start_response: Callable[..., Any]
    ) -> Iterable[bytes]:
        def con_cabeceras(status: str, headers: list[tuple[str, str]], exc_info: Any = None) -> Any:
            presentes = {nombre.lower() for nombre, _ in headers}
            extra = [(n, v) for n, v in self.cabeceras if n.lower() not in presentes]
            return start_response(status, [*headers, *extra], exc_info)

        return self.app(environ, con_cabeceras)


def crear_wsgi(api: Flask, dist: Path, *, produccion: bool) -> WsgiApp:
    """Web en ``/`` y API en ``/api``, con las cabeceras de seguridad."""
    return ConCabeceras(DispatcherMiddleware(Estaticos(dist), {"/api": api}), produccion=produccion)


def _desde_entorno() -> WsgiApp:  # pragma: no cover - lo carga gunicorn en el contenedor
    from app import create_app

    api = create_app()
    config = api.extensions["assetcontrol.config"]
    dist = Path(os.environ.get(WEB_DIST_VAR, Path(__file__).resolve().parents[2] / "web" / "dist"))
    return crear_wsgi(api, dist, produccion=config.environment == "production")


def __getattr__(nombre: str) -> WsgiApp:  # pragma: no cover
    # ``application`` se crea al pedirlo (gunicorn), no al importar el módulo en las pruebas.
    if nombre == "application":
        return _desde_entorno()
    raise AttributeError(nombre)
