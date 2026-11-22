"""``ENVIRONMENT`` cerrado y relajaciones de ``test`` solo bajo pytest (spec 002, T4, M1).

``ENVIRONMENT`` admite solo ``development``, ``test``, ``production`` y
``staging``. ``test`` omite el mínimo de ``SECRET_KEY``, baja Argon2 y activa
``TESTING``; por eso solo vale cuando el proceso corre bajo pytest. En un
proceso real (servidor, CLI) ``ENVIRONMENT=test`` falla al arrancar, sin
mostrar valores de la configuración. Con ``test`` válido se registra un aviso
al arrancar.

Datos sintéticos.
"""

import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from flask import Flask

from app import config as config_module
from app import create_app
from app.auth.credentials import ARGON2_PARAMS, ARGON2_TEST_PARAMS, get_passwords, init_credentials
from app.config import (
    ALLOWED_ENVIRONMENTS,
    Config,
    InvalidEnvironmentError,
    UnsafeTestEnvironmentError,
    is_test_context,
    load_config,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
OFFLINE_DB = "postgresql+psycopg://user:valor-secreto-db@db.invalid:5432/assetcontrol"
SHORT_SECRET = "valor-secreto-corto"
LONG_SECRET = "clave-sintetica-de-prueba-con-mas-de-32-bytes"
ENV = {"DATABASE_URL": OFFLINE_DB, "SECRET_KEY": SHORT_SECRET, "ENVIRONMENT": "test"}


def _no_secrets(text: str) -> None:
    for secret in (SHORT_SECRET, LONG_SECRET, "valor-secreto-db", OFFLINE_DB):
        assert secret not in text


# --- Lista cerrada -----------------------------------------------------------------


def test_allowed_environments_are_the_closed_list():
    assert frozenset({"development", "test", "production", "staging"}) == ALLOWED_ENVIRONMENTS


@pytest.mark.parametrize("environment", sorted(ALLOWED_ENVIRONMENTS))
def test_each_allowed_environment_is_accepted(environment):
    assert Config(OFFLINE_DB, LONG_SECRET, environment).environment == environment


@pytest.mark.parametrize(
    "environment",
    ["prod", "Development", "TEST", "desarrollo", "produccion", "valor-secreto-entorno", "dev"],
)
def test_other_environment_values_fail_without_echoing_them(environment):
    with pytest.raises(InvalidEnvironmentError) as excinfo:
        load_config({**ENV, "SECRET_KEY": LONG_SECRET, "ENVIRONMENT": environment})

    message = str(excinfo.value)
    assert "ENVIRONMENT" in message
    for allowed in ALLOWED_ENVIRONMENTS:
        assert allowed in message
    assert "valor-secreto-entorno" not in message
    _no_secrets(message)


def test_invalid_environment_also_fails_when_building_config_directly():
    with pytest.raises(InvalidEnvironmentError):
        Config(OFFLINE_DB, LONG_SECRET, "prod")


# --- test solo bajo pytest -----------------------------------------------------------


def test_test_context_is_active_under_pytest():
    assert "pytest" in sys.modules
    assert is_test_context() is True


def test_environment_test_outside_pytest_fails_without_leaking_values(monkeypatch):
    monkeypatch.setattr(config_module, "is_test_context", lambda: False)

    with pytest.raises(UnsafeTestEnvironmentError) as excinfo:
        load_config(ENV)

    message = str(excinfo.value)
    assert "ENVIRONMENT=test" in message
    _no_secrets(message)
    # Ni siquiera con una SECRET_KEY larga: test fuera de pytest no arranca.
    with pytest.raises(UnsafeTestEnvironmentError):
        Config(OFFLINE_DB, LONG_SECRET, "test")


def test_other_environments_do_not_need_the_test_context(monkeypatch):
    monkeypatch.setattr(config_module, "is_test_context", lambda: False)

    for environment in ("development", "production", "staging"):
        assert Config(OFFLINE_DB, LONG_SECRET, environment).environment == environment


def _run_real_process(code: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    # Proceso real sin pytest importado; entorno mínimo (sin las variables del host).
    child_env = dict(env)
    for name in ("PATH", "SYSTEMROOT"):
        if name in os.environ:
            child_env[name] = os.environ[name]
    return subprocess.run(  # noqa: S603 - intérprete actual y código fijo de la prueba
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        env=child_env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.mark.parametrize("secret", [SHORT_SECRET, LONG_SECRET])
def test_a_real_process_with_environment_test_fails_at_startup(secret):
    result = _run_real_process(
        "import sys; from app import create_app; create_app(); print('pytest' in sys.modules)",
        {**ENV, "SECRET_KEY": secret},
    )

    assert result.returncode != 0
    assert "UnsafeTestEnvironmentError" in result.stderr
    assert "ENVIRONMENT=test" in result.stderr
    _no_secrets(result.stdout + result.stderr)


def test_a_real_process_with_a_valid_environment_starts():
    # Control: el mismo proceso con production y clave larga arranca (la prueba es válida).
    result = _run_real_process(
        "import sys; from app import create_app; app = create_app(); "
        "print(app.testing, 'pytest' in sys.modules)",
        {**ENV, "SECRET_KEY": LONG_SECRET, "ENVIRONMENT": "production"},
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False False"


# --- Relajaciones atadas al contexto de pruebas -----------------------------------------


def test_testing_flag_requires_the_test_context(monkeypatch):
    config = Config(OFFLINE_DB, SHORT_SECRET, "test")
    assert config.to_flask()["TESTING"] is True

    monkeypatch.setattr(config_module, "is_test_context", lambda: False)
    assert config.to_flask()["TESTING"] is False


def test_cheap_argon2_requires_the_test_context_even_if_testing_is_set(monkeypatch):
    # Aunque alguien ponga TESTING=True a mano, fuera de pytest se usa el costo real.
    monkeypatch.setattr(config_module, "is_test_context", lambda: False)
    flask_app = Flask(__name__)
    flask_app.config["TESTING"] = True

    init_credentials(flask_app)

    with flask_app.app_context():
        assert get_passwords().params == ARGON2_PARAMS


def test_cheap_argon2_is_used_in_the_test_context():
    flask_app = create_app(Config(OFFLINE_DB, SHORT_SECRET, "test"))
    with flask_app.app_context():
        assert get_passwords().params == ARGON2_TEST_PARAMS


# --- Aviso al arrancar --------------------------------------------------------------


def test_startup_warns_when_environment_is_test(caplog):
    caplog.set_level(logging.DEBUG)

    create_app(Config(OFFLINE_DB, SHORT_SECRET, "test"))

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("ENVIRONMENT=test" in r.getMessage() for r in warnings)
    _no_secrets(caplog.text)


@pytest.mark.parametrize("environment", ["development", "production", "staging"])
def test_startup_does_not_warn_outside_test(environment, caplog):
    caplog.set_level(logging.DEBUG)

    create_app(Config(OFFLINE_DB, LONG_SECRET, environment))

    assert "ENVIRONMENT=test" not in caplog.text


# --- Despliegue: ninguna imagen ni compose fija ENVIRONMENT=test --------------------------


_FIXES_TEST = re.compile(r"ENVIRONMENT\s*[:=]\s*[\"']?test\b", re.IGNORECASE)


def _deployment_files() -> list[Path]:
    files = [*REPO_DIR.glob("docker-compose*.yml"), *REPO_DIR.glob("docker-compose*.yaml")]
    files += [*REPO_DIR.glob("compose*.yml"), *REPO_DIR.glob("compose*.yaml")]
    files += [*BACKEND_DIR.glob("Dockerfile*"), *REPO_DIR.glob("Dockerfile*")]
    return files


def test_deployment_files_never_fix_environment_test():
    files = _deployment_files()
    assert any(f.name == "docker-compose.yml" for f in files)
    assert any(f.name == "Dockerfile" for f in files)

    offenders = [f.name for f in files if _FIXES_TEST.search(f.read_text("utf-8"))]
    assert offenders == []


@pytest.mark.parametrize(
    "line",
    ["ENVIRONMENT: test", "ENVIRONMENT=test", 'ENVIRONMENT: "test"', "ENV ENVIRONMENT=test"],
)
def test_deployment_check_detects_environment_test(line):
    assert _FIXES_TEST.search(line)


@pytest.mark.parametrize("line", ["ENVIRONMENT: development", "UV_PROJECT_ENVIRONMENT=/opt/venv"])
def test_deployment_check_ignores_other_values(line):
    assert not _FIXES_TEST.search(line)
