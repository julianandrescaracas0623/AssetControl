"""Configuración compartida de pytest.

Ninguna salida de pytest debe mostrar la contraseña de la base. Los frames de
SQLAlchemy y psycopg reciben la contraseña como argumento (``cparams``,
``conninfo``), así que un fallo de conexión dentro de una prueba la mostraría en
el traceback, en ``--showlocals`` o en la salida capturada. Estos hooks la
reemplazan por ``***`` en cada reporte antes de que se imprima.

Las pruebas con PostgreSQL usan dos URL (spec 001, R4c):

- ``TEST_DATABASE_URL``: rol de la aplicación (sin ``SUPERUSER`` ni
  ``BYPASSRLS``, no dueño). Es con la que se conecta la app en las pruebas.
- ``TEST_MIGRATION_DATABASE_URL``: rol migrador, dueño del esquema. Solo crea y
  elimina tablas de prueba, sus políticas y sus ``GRANT``.
"""

import os
from urllib.parse import unquote, urlsplit

import pytest
from sqlalchemy.engine import URL, make_url

_URL_VARS = (
    "TEST_DATABASE_URL",
    "TEST_MIGRATION_DATABASE_URL",
    "DATABASE_URL",
    "MIGRATION_DATABASE_URL",
)
_MASK = "***"

BLOCKED = (
    "bloqueado: faltan TEST_DATABASE_URL (rol de la aplicación) y "
    "TEST_MIGRATION_DATABASE_URL (rol migrador), o la base assetcontrol_test no responde"
)
SAME_ROLE = (
    "bloqueado: TEST_MIGRATION_DATABASE_URL usa el mismo rol que TEST_DATABASE_URL; "
    "debe usar el rol migrador (POSTGRES_USER), no el de la aplicación"
)


def _database_passwords() -> list[str]:
    """Contraseñas de las URL de base del entorno, tal cual y decodificadas."""
    found: set[str] = set()
    for name in _URL_VARS:
        raw = os.environ.get(name, "").strip()
        if not raw:
            continue
        try:
            password = urlsplit(raw).password
        except ValueError:
            continue
        if password:
            found.update({password, unquote(password)})
    # Primero las más largas: una contraseña no queda a medias tapada por otra.
    return sorted(found, key=len, reverse=True)


def _scrub(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        text = text.replace(secret, _MASK)
    return text


def _redact_report(report: pytest.CollectReport | pytest.TestReport) -> None:
    secrets = _database_passwords()
    if not secrets:
        return
    longrepr = report.longrepr
    if isinstance(longrepr, tuple):
        path, lineno, message = longrepr
        report.longrepr = (path, lineno, _scrub(message, secrets))
    elif longrepr is not None:
        text = str(longrepr)
        if any(secret in text for secret in secrets):
            report.longrepr = _scrub(text, secrets)
    report.sections = [(title, _scrub(body, secrets)) for title, body in report.sections]


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    _redact_report(report)
    return report


@pytest.hookimpl(wrapper=True)
def pytest_make_collect_report(collector):
    report = yield
    _redact_report(report)
    return report


def read_database_url(name: str) -> URL | None:
    """La variable ``name`` como ``URL``: su ``str`` y ``repr`` ocultan la contraseña.

    Así ningún frame de pytest (argumentos o variables locales) la muestra en texto plano.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    return make_url(raw)


@pytest.fixture
def app_database_url() -> URL:
    """URL del rol de la aplicación sobre la base de pruebas."""
    url = read_database_url("TEST_DATABASE_URL")
    if url is None:
        pytest.fail(BLOCKED, pytrace=False)
    return url


@pytest.fixture
def migration_database_url() -> URL:
    """URL del rol migrador sobre la base de pruebas."""
    url = read_database_url("TEST_MIGRATION_DATABASE_URL")
    if url is None:
        pytest.fail(BLOCKED, pytrace=False)
    app_url = read_database_url("TEST_DATABASE_URL")
    if app_url is not None and app_url.username == url.username:
        # Con el mismo rol no hay quién cree las tablas ni nada que probar sobre RLS.
        pytest.fail(SAME_ROLE, pytrace=False)
    return url
