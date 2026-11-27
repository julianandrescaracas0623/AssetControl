"""Cabeceras de las páginas sensibles y del *fallback* de la SPA (spec 018, T1; R1–R3, A1).

- R1: ``/restablecer``, ``/invitacion``, ``/cambiar-contrasena``, ``/plataforma`` y
  ``/plataforma/**`` (existan o no como archivo) llevan ``Referrer-Policy: no-referrer`` y
  ``Cache-Control: no-store``.
- R2: todo ``index.html`` servido por el *fallback* lleva las mismas dos cabeceras; los
  ``/assets/*`` con huella conservan su caché y ``same-origin``.
- R3: CSP, ``X-Frame-Options``, ``Permissions-Policy`` y HSTS (producción) no cambian; la
  API tampoco.

Estas pruebas no necesitan base de datos: la API es una app Flask mínima.
"""

from pathlib import Path

import pytest
from flask import Flask, jsonify
from werkzeug.test import Client

from app.wsgi import CSP, crear_wsgi

INMUTABLE = "public, max-age=31536000, immutable"
HSTS = "max-age=31536000; includeSubDomains"

RUTAS_SENSIBLES = (
    "/restablecer",
    "/invitacion",
    "/cambiar-contrasena",
    "/plataforma",
    "/plataforma/entrar",
    "/plataforma/empresas/123/usuarios",
)
RUTAS_FALLBACK = (
    "/",
    "/index.html",
    "/login",
    "/app/activos",
    "/app/activos/AC.01",
    "/contar/nuevo",
    "/ruta/que/no/existe",
    "/restablecerx",
    "/plataformas",
    "/invitaciones/abc",
)


@pytest.fixture
def api() -> Flask:
    flask_app = Flask("api_de_prueba")

    @flask_app.get("/health")
    def health():
        return jsonify(status="ok")

    @flask_app.get("/con-cache")
    def con_cache():
        respuesta = jsonify(status="ok")
        respuesta.headers["Cache-Control"] = "private, max-age=60"
        return respuesta

    return flask_app


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>AssetControl</title>")
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)")
    (tmp_path / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
    return tmp_path


@pytest.fixture
def cliente(api, dist) -> Client:
    return Client(crear_wsgi(api, dist, produccion=False))


@pytest.fixture
def cliente_produccion(api, dist) -> Client:
    return Client(crear_wsgi(api, dist, produccion=True))


def _sin_referrer_ni_cache(headers) -> None:
    assert headers.getlist("Referrer-Policy") == ["no-referrer"]
    assert headers.getlist("Cache-Control") == ["no-store"]


@pytest.mark.parametrize("ruta", RUTAS_SENSIBLES)
def test_sensitive_routes_send_no_referrer_and_no_store_once(cliente, ruta):
    respuesta = cliente.get(ruta)
    assert respuesta.status_code == 200
    assert respuesta.mimetype == "text/html"
    _sin_referrer_ni_cache(respuesta.headers)


@pytest.mark.parametrize("ruta", RUTAS_SENSIBLES)
def test_sensitive_routes_win_even_if_a_file_exists_there(api, dist, ruta):
    # R1: «existan o no como archivo». Un archivo de la raíz llamado como la ruta se
    # serviría con caché corta; en estas rutas se fuerzan no-store y no-referrer.
    destino = dist / ruta.lstrip("/")
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text("archivo")
    respuesta = Client(crear_wsgi(api, dist, produccion=False)).get(ruta)
    _sin_referrer_ni_cache(respuesta.headers)


def test_sensitive_routes_keep_no_store_on_head(cliente):
    _sin_referrer_ni_cache(cliente.head("/restablecer").headers)


@pytest.mark.parametrize("ruta", RUTAS_FALLBACK)
def test_spa_fallback_sends_no_referrer_and_no_store_once(cliente, ruta):
    # R2: cualquier ruta que cae en index.html, incluidas las parecidas a las sensibles
    # (/restablecerx, /plataformas) y las inexistentes.
    respuesta = cliente.get(ruta)
    assert respuesta.status_code == 200
    assert b"AssetControl" in respuesta.data
    _sin_referrer_ni_cache(respuesta.headers)


def test_hashed_assets_keep_their_cache_and_same_origin(cliente):
    respuesta = cliente.get("/assets/index-abc123.js")
    assert respuesta.status_code == 200
    assert respuesta.headers.getlist("Cache-Control") == [INMUTABLE]
    assert respuesta.headers.getlist("Referrer-Policy") == ["same-origin"]


def test_missing_asset_is_404_and_not_the_fallback(cliente):
    respuesta = cliente.get("/assets/no-existe.js")
    assert respuesta.status_code == 404
    assert respuesta.headers.getlist("Referrer-Policy") == ["same-origin"]
    assert "no-store" not in respuesta.headers.getlist("Cache-Control")


def test_root_files_keep_their_short_cache_and_same_origin(cliente):
    respuesta = cliente.get("/robots.txt")
    assert respuesta.status_code == 200
    assert respuesta.headers.getlist("Cache-Control") == ["public, max-age=3600"]
    assert respuesta.headers.getlist("Referrer-Policy") == ["same-origin"]


def test_api_responses_do_not_change(cliente):
    respuesta = cliente.get("/api/health")
    assert respuesta.status_code == 200
    assert respuesta.headers.getlist("Referrer-Policy") == ["same-origin"]
    assert "Cache-Control" not in respuesta.headers
    propia = cliente.get("/api/con-cache")
    assert propia.headers.getlist("Cache-Control") == ["private, max-age=60"]
    assert propia.headers.getlist("Referrer-Policy") == ["same-origin"]


def test_api_paths_that_look_sensitive_do_not_change(api, dist):
    @api.get("/plataforma/auth/refresh")
    def refresh():
        return jsonify(status="ok")

    @api.get("/auth/cambiar-contrasena")
    def cambiar():
        return jsonify(status="ok")

    cliente = Client(crear_wsgi(api, dist, produccion=False))
    for ruta in ("/api/plataforma/auth/refresh", "/api/auth/cambiar-contrasena"):
        h = cliente.get(ruta).headers
        assert h.getlist("Referrer-Policy") == ["same-origin"], ruta
        assert "Cache-Control" not in h, ruta


@pytest.mark.parametrize(
    "ruta",
    (
        "/restablecer",
        "/plataforma/entrar",
        "/app/activos",
        "/assets/index-abc123.js",
        "/api/health",
    ),
)
def test_other_security_headers_stay_the_same(cliente, cliente_produccion, ruta):
    # R3: CSP, X-Frame-Options y Permissions-Policy siempre, una sola vez; HSTS en producción.
    for c, con_hsts in ((cliente, False), (cliente_produccion, True)):
        h = c.get(ruta).headers
        assert h.getlist("Content-Security-Policy") == [CSP], ruta
        assert h.getlist("X-Frame-Options") == ["DENY"], ruta
        assert h.getlist("X-Content-Type-Options") == ["nosniff"], ruta
        assert h.getlist("Permissions-Policy") == [
            "camera=(self), microphone=(), geolocation=(), payment=()"
        ], ruta
        assert h.getlist("Cross-Origin-Opener-Policy") == ["same-origin"], ruta
        assert h.getlist("Strict-Transport-Security") == ([HSTS] if con_hsts else []), ruta


@pytest.mark.parametrize(
    "ruta",
    (
        "//restablecer",
        "/RESTABLECER",
        "/restablecer/",
        "/restablecer;x",
        "/plataforma/entrar/",
    ),
)
def test_sensitive_route_variants_send_no_referrer_and_no_store_once(cliente, ruta):
    # Variantes de la ruta (barra doble, mayúsculas, barra final, parámetro de ruta) caen
    # en la regla sensible o en el fallback: las dos ponen no-referrer y no-store una vez.
    # PATH_INFO se fija a mano: werkzeug leería «//restablecer» como host y probaría «/».
    respuesta = cliente.get(ruta, environ_overrides={"PATH_INFO": ruta})
    assert respuesta.request.environ["PATH_INFO"] == ruta
    assert respuesta.status_code == 200
    assert respuesta.mimetype == "text/html"
    _sin_referrer_ni_cache(respuesta.headers)


@pytest.mark.parametrize("ruta", ("/restablecer", "/login"))
def test_not_modified_keeps_no_referrer_and_no_store(cliente, ruta):
    primera = cliente.get(ruta)
    etag = primera.headers.get("ETag")
    assert etag, ruta
    respuesta = cliente.get(ruta, headers={"If-None-Match": etag})
    assert respuesta.status_code == 304, ruta
    _sin_referrer_ni_cache(respuesta.headers)


def test_post_to_sensitive_route_is_405_and_keeps_no_referrer_and_no_store(cliente):
    respuesta = cliente.post("/restablecer")
    assert respuesta.status_code == 405
    _sin_referrer_ni_cache(respuesta.headers)
