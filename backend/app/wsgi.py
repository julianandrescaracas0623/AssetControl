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
from typing import TYPE_CHECKING, Any

from flask import Flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.security import safe_join
from werkzeug.utils import send_file
from werkzeug.wrappers import Request, Response

if TYPE_CHECKING:
    from app.correo import Correo

WEB_DIST_VAR = "WEB_DIST_DIR"
INMUTABLE = "public, max-age=31536000, immutable"
CORTA = "public, max-age=3600"
# Spec 018 (R1, R2): ni el navegador ni un proxy guardan el HTML de la SPA ni el de las
# páginas sensibles, y no se envía la URL como referrer.
SIN_CACHE = "no-store"
SIN_REFERRER = "no-referrer"

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
    - Cualquier otra ruta es de la SPA (también ``/app/activos/AC.01``): ``index.html``
      con ``no-store`` y ``no-referrer`` (spec 018, R2), para que una versión nueva se vea
      al recargar y la URL de la SPA no salga como referrer.
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
        respuesta = self._enviar(request, self.indice, SIN_CACHE)
        respuesta.headers["Referrer-Policy"] = SIN_REFERRER
        return respuesta

    @staticmethod
    def _enviar(request: Request, archivo: Path, cache: str) -> Response:
        respuesta = send_file(archivo, request.environ, conditional=True, max_age=None)
        respuesta.headers["Cache-Control"] = cache
        return respuesta


# SEC-05 y spec 018 (R1): en estas rutas el enlace de un solo uso (restablecer, invitar),
# el cambio de contraseña o la consola viajan en la URL; ninguna petición de salida debe
# llevarla como referrer y la página no se guarda en caché, exista o no como archivo.
RUTAS_SENSIBLES: tuple[str, ...] = (
    "/restablecer",
    "/invitacion",
    "/cambiar-contrasena",
    "/plataforma",
)
FORZADAS_SENSIBLES: tuple[tuple[str, str], ...] = (
    ("Referrer-Policy", SIN_REFERRER),
    ("Cache-Control", SIN_CACHE),
)
_NOMBRES_FORZADOS = frozenset(nombre.lower() for nombre, _ in FORZADAS_SENSIBLES)


def _ruta_sensible(ruta: str) -> bool:
    return any(ruta == base or ruta.startswith(base + "/") for base in RUTAS_SENSIBLES)


class ConCabeceras:
    """Agrega las cabeceras de seguridad (R4) a toda respuesta; HSTS solo en producción.

    No pisa las que la respuesta ya trae, salvo en las rutas sensibles (spec 018, R1), donde
    ``Referrer-Policy`` y ``Cache-Control`` se reemplazan por ``no-referrer`` y ``no-store``.
    """

    def __init__(self, app: WsgiApp, *, produccion: bool) -> None:
        self.app = app
        self.cabeceras = (*CABECERAS, HSTS) if produccion else CABECERAS

    def __call__(
        self, environ: dict[str, Any], start_response: Callable[..., Any]
    ) -> Iterable[bytes]:
        sensible = _ruta_sensible(environ.get("PATH_INFO", ""))

        def con_cabeceras(status: str, headers: list[tuple[str, str]], exc_info: Any = None) -> Any:
            if sensible:
                headers = [
                    *((n, v) for n, v in headers if n.lower() not in _NOMBRES_FORZADOS),
                    *FORZADAS_SENSIBLES,
                ]
            presentes = {nombre.lower() for nombre, _ in headers}
            extra = [(n, v) for n, v in self.cabeceras if n.lower() not in presentes]
            return start_response(status, [*headers, *extra], exc_info)

        return self.app(environ, con_cabeceras)


def crear_wsgi(api: Flask, dist: Path, *, produccion: bool) -> WsgiApp:
    """Web en ``/`` y API en ``/api``, con las cabeceras de seguridad."""
    return ConCabeceras(DispatcherMiddleware(Estaticos(dist), {"/api": api}), produccion=produccion)


# Spec 018 (R4): la API Flask creada en ESTE proceso (``preload_app = False``: cada proceso
# de gunicorn crea la suya). Solo la lee ``worker_exit`` para esperar los correos en curso.
_api: Flask | None = None


def correo_del_proceso() -> "Correo | None":
    """El ``Correo`` de la app creada en este proceso, o ``None`` si aún no se creó."""
    api = _api
    if api is None:
        return None
    from app.correo import EXTENSION_KEY

    return api.extensions.get(EXTENSION_KEY)


def _desde_entorno() -> WsgiApp:  # pragma: no cover - lo carga gunicorn en el contenedor
    global _api
    from app import create_app

    api = create_app()
    _api = api
    config = api.extensions["assetcontrol.config"]
    dist = Path(os.environ.get(WEB_DIST_VAR, Path(__file__).resolve().parents[2] / "web" / "dist"))
    return crear_wsgi(api, dist, produccion=config.environment == "production")


def __getattr__(nombre: str) -> WsgiApp:  # pragma: no cover
    # ``application`` se crea al pedirlo (gunicorn), no al importar el módulo en las pruebas.
    if nombre == "application":
        return _desde_entorno()
    raise AttributeError(nombre)
