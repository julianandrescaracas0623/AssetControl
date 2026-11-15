"""App de producción en un solo origen (spec 010b, T1; R1, R4).

gunicorn sirve la web compilada en ``/`` y la API bajo ``/api``: la cookie de refresh
viaja con ``Path=/api/auth`` y toda respuesta lleva las cabeceras de seguridad.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest
from acceso_db import ADMIN_A, PASSWORD, AccesoDb, dispose, make_app, temporary_acceso_db
from flask import Flask
from werkzeug.test import Client

from app.auth.http import CSRF_HEADER, CSRF_HEADER_VALUE
from app.wsgi import crear_wsgi


@pytest.fixture(scope="module")
def wsgi_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("wsgi")


@pytest.fixture(scope="module")
def api(wsgi_db) -> Iterator[Flask]:
    flask_app = make_app(wsgi_db)
    yield flask_app
    dispose(flask_app)


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


def test_spa_routes_get_index_html_without_cache(cliente):
    for ruta in ("/", "/admin", "/admin/activos/AC.01", "/contar/activo/000123/historial"):
        respuesta = cliente.get(ruta)
        assert respuesta.status_code == 200, ruta
        assert respuesta.mimetype == "text/html", ruta
        assert b"AssetControl" in respuesta.data
        assert respuesta.headers["Cache-Control"] == "no-cache"


def test_hashed_assets_are_immutable_and_missing_ones_are_404(cliente):
    respuesta = cliente.get("/assets/index-abc123.js")
    assert respuesta.status_code == 200
    assert respuesta.headers["Cache-Control"] == "public, max-age=31536000, immutable"
    assert cliente.get("/assets/no-existe.js").status_code == 404
    assert cliente.get("/assets/..%2f..%2fpyproject.toml").status_code == 404  # fuera de dist
    assert cliente.get("/favicon.ico").status_code == 404  # archivo raíz que no existe
    assert cliente.get("/robots.txt").status_code == 200


def test_only_get_and_head_reach_the_static_files(cliente):
    assert cliente.post("/admin").status_code == 405
    assert cliente.head("/").status_code == 200


def test_the_api_lives_under_api(cliente):
    respuesta = cliente.get("/api/health")
    assert respuesta.status_code == 200
    assert respuesta.get_json()["status"] == "ok"
    noexiste = cliente.get("/api/no-existe")
    assert noexiste.status_code == 404
    assert noexiste.mimetype == "application/json"


def test_refresh_cookie_path_is_under_api(cliente):
    respuesta = cliente.post(
        "/api/auth/login",
        json={"email": ADMIN_A.email, "password": PASSWORD},
        headers={CSRF_HEADER: CSRF_HEADER_VALUE},
    )
    assert respuesta.status_code == 200, respuesta.get_json()
    cookie = respuesta.headers["Set-Cookie"]
    assert "Path=/api/auth" in cookie
    assert "HttpOnly" in cookie


def test_security_headers_on_web_and_api(cliente):
    for ruta in ("/", "/assets/index-abc123.js", "/api/health"):
        h = cliente.get(ruta).headers
        csp = h["Content-Security-Policy"]
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp
        assert "script-src 'self'" in csp
        assert "'unsafe-eval'" not in csp
        assert h["X-Content-Type-Options"] == "nosniff"
        assert h["X-Frame-Options"] == "DENY"
        assert h["Referrer-Policy"] in ("same-origin", "no-referrer")
        assert "camera=(self)" in h["Permissions-Policy"]
        assert "Strict-Transport-Security" not in h  # solo en producción


def test_hsts_only_in_production(api, dist):
    h = Client(crear_wsgi(api, dist, produccion=True)).get("/").headers
    assert h["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"


def test_missing_build_fails_clearly(api, tmp_path):
    with pytest.raises(RuntimeError, match="index.html"):
        crear_wsgi(api, tmp_path / "no-hay", produccion=False)
