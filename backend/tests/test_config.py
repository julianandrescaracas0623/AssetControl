import io
import re
import uuid
from pathlib import Path

import pytest
from flask import request
from sqlalchemy import create_engine, literal, select
from sqlalchemy.pool import NullPool

from app import create_app
from app.auth.http import AUTH_MAX_BODY_BYTES, refresh_cookie_options
from app.config import (
    REQUIRED_VARS,
    SECRET_KEY_MIN_BYTES,
    Config,
    MissingConfigError,
    WeakSecretKeyError,
    load_config,
)
from app.db import (
    POOL_RECYCLE_SECONDS,
    InsecureDatabaseRoleError,
    _get_database,
    ping_database,
    tenant_session,
    verify_connection_role,
)

VALID_ENV = {
    "DATABASE_URL": "postgresql+psycopg://user:valor-secreto-db@db.invalid:5432/assetcontrol",
    "SECRET_KEY": "valor-secreto-clave-123",
    "ENVIRONMENT": "test",
}


def test_required_vars_are_the_three_of_the_spec():
    assert set(REQUIRED_VARS) == {"DATABASE_URL", "SECRET_KEY", "ENVIRONMENT"}


def test_load_config_reads_all_variables():
    config = load_config(VALID_ENV)

    assert isinstance(config, Config)
    assert config.database_url == VALID_ENV["DATABASE_URL"]
    assert config.secret_key == VALID_ENV["SECRET_KEY"]
    assert config.environment == "test"


def test_load_config_reads_os_environ_by_default(monkeypatch):
    for name, value in VALID_ENV.items():
        monkeypatch.setenv(name, value)

    config = load_config()

    assert config.environment == "test"


@pytest.mark.parametrize("missing", ["DATABASE_URL", "SECRET_KEY", "ENVIRONMENT"])
def test_missing_variable_names_it_without_leaking_values(missing):
    env = {k: v for k, v in VALID_ENV.items() if k != missing}

    with pytest.raises(MissingConfigError) as excinfo:
        load_config(env)

    message = str(excinfo.value)
    assert missing in message
    for present_value in env.values():
        assert present_value not in message
    assert "valor-secreto" not in message


@pytest.mark.parametrize("missing", ["DATABASE_URL", "SECRET_KEY", "ENVIRONMENT"])
def test_empty_variable_counts_as_missing(missing):
    env = {**VALID_ENV, missing: "   "}

    with pytest.raises(MissingConfigError) as excinfo:
        load_config(env)

    assert missing in str(excinfo.value)


def test_all_missing_variables_are_named():
    with pytest.raises(MissingConfigError) as excinfo:
        load_config({})

    message = str(excinfo.value)
    for name in REQUIRED_VARS:
        assert name in message


def test_config_repr_does_not_leak_secrets():
    config = load_config(VALID_ENV)

    assert VALID_ENV["SECRET_KEY"] not in repr(config)
    assert VALID_ENV["DATABASE_URL"] not in repr(config)


# --- Spec 002, T4: SECRET_KEY, ENVIRONMENT, rol de la base, cabeceras y cuerpo --------

LONG_SECRET = "clave-sintetica-de-prueba-con-mas-de-32-bytes"
OFFLINE_DB = "postgresql+psycopg://user:valor-secreto-db@db.invalid:5432/assetcontrol"


def test_secret_key_minimum_is_32_bytes():
    assert SECRET_KEY_MIN_BYTES == 32


# "prod" y otros valores fuera de la lista cerrada fallan antes (test_environment.py, M1).
@pytest.mark.parametrize("environment", ["production", "development", "staging"])
def test_short_secret_key_fails_outside_tests_without_leaking_it(environment):
    weak = "valor-secreto-de-31-bytes-xxxxx"
    assert len(weak.encode()) == 31

    with pytest.raises(WeakSecretKeyError) as excinfo:
        load_config({**VALID_ENV, "SECRET_KEY": weak, "ENVIRONMENT": environment})

    assert "SECRET_KEY" in str(excinfo.value)
    assert "32" in str(excinfo.value)
    assert weak not in str(excinfo.value)
    assert "valor-secreto" not in str(excinfo.value)


def test_short_secret_key_also_fails_when_building_config_directly():
    with pytest.raises(WeakSecretKeyError):
        Config(database_url=OFFLINE_DB, secret_key="corta", environment="production")


def test_secret_key_length_is_measured_in_bytes():
    # 16 caracteres de 2 bytes = 32 bytes: válida.
    config = load_config({**VALID_ENV, "SECRET_KEY": "ñ" * 16, "ENVIRONMENT": "production"})
    assert len(config.secret_key.encode()) == 32


def test_secret_key_of_32_bytes_is_accepted_in_production():
    config = load_config({**VALID_ENV, "SECRET_KEY": "k" * 32, "ENVIRONMENT": "production"})
    assert config.environment == "production"


def test_short_secret_key_is_allowed_only_in_tests():
    assert load_config({**VALID_ENV, "SECRET_KEY": "corta"}).environment == "test"


@pytest.mark.parametrize(
    ("environment", "secure"),
    [
        ("development", False),
        ("production", True),
        ("test", True),
        ("staging", True),
        # "Development", "desarrollo" y otros valores ya no arrancan (lista cerrada, M1).
    ],
)
def test_cookies_are_secure_unless_development_is_explicit(environment, secure):
    config = Config(database_url=OFFLINE_DB, secret_key=LONG_SECRET, environment=environment)
    assert config.secure_cookies is secure


def test_refresh_cookie_uses_the_secure_prefix_outside_development():
    production = refresh_cookie_options(
        Config(database_url=OFFLINE_DB, secret_key=LONG_SECRET, environment="production")
    )
    development = refresh_cookie_options(
        Config(database_url=OFFLINE_DB, secret_key=LONG_SECRET, environment="development")
    )

    assert production == {
        "key": "__Secure-refresh",
        "secure": True,
        "httponly": True,
        "samesite": "Lax",
        "path": "/auth",
    }
    assert development == {**production, "key": "refresh", "secure": False}


def test_compose_fixes_environment_development_explicitly():
    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text("utf-8")
    api = compose.split("\n  api:", 1)[1]

    assert re.search(r"^\s+ENVIRONMENT: development\s*$", api, re.MULTILINE)
    assert ":-development" not in compose


# --- Rol de la base al conectar (M2 de T6 de la spec 001; R15, A6) ----------------------


def test_app_role_connection_is_accepted(app_database_url):
    flask_app = create_app(
        Config(
            database_url=app_database_url.render_as_string(hide_password=False),
            secret_key=LONG_SECRET,
            environment="test",
        )
    )
    with flask_app.app_context():
        assert ping_database() is True


def test_superuser_or_bypassrls_connection_is_refused(migration_database_url, caplog):
    # El migrador local y de la CI es superusuario: la aplicación no debe aceptarlo.
    url = migration_database_url.render_as_string(hide_password=False)
    flask_app = create_app(Config(database_url=url, secret_key=LONG_SECRET, environment="test"))
    with flask_app.app_context():
        assert ping_database() is False
        with pytest.raises(InsecureDatabaseRoleError) as excinfo:
            with tenant_session("00000000-0000-4000-8000-00000000a004") as session:
                session.scalar(select(literal(1)))

    message = str(excinfo.value)
    assert "SUPERUSER" in message and "BYPASSRLS" in message
    assert migration_database_url.username not in message
    assert migration_database_url.password not in caplog.text
    assert migration_database_url.password not in message


@pytest.mark.parametrize("attribute", ["SUPERUSER", "BYPASSRLS"])
def test_role_check_rejects_each_unsafe_attribute(migration_database_url, attribute):
    # El rol temporal se crea y se usa con SET LOCAL ROLE en una transacción que se revierte.
    engine = create_engine(migration_database_url, poolclass=NullPool)
    name = f"prueba_rol_t4_{uuid.uuid4().hex[:6]}"
    try:
        raw = engine.raw_connection()
        try:
            cursor = raw.cursor()
            cursor.execute(f'CREATE ROLE "{name}" NOLOGIN {attribute}')
            cursor.execute(f'SET LOCAL ROLE "{name}"')
            with pytest.raises(InsecureDatabaseRoleError):
                verify_connection_role(raw.driver_connection, rollback=False)
            cursor.execute("RESET ROLE")
            cursor.execute(f'CREATE ROLE "{name}_ok" NOLOGIN')
            cursor.execute(f'SET LOCAL ROLE "{name}_ok"')
            verify_connection_role(raw.driver_connection, rollback=False)
        finally:
            raw.rollback()
            raw.close()
    finally:
        engine.dispose()


def test_role_check_leaves_no_open_transaction(app_database_url):
    engine = create_engine(app_database_url, poolclass=NullPool)
    try:
        raw = engine.raw_connection()
        try:
            verify_connection_role(raw.driver_connection)
            assert raw.driver_connection.info.transaction_status.name == "IDLE"
        finally:
            raw.close()
    finally:
        engine.dispose()


# --- Cabeceras y límite de cuerpo en /auth e /invitaciones (A25, Q9) ---------------------


def _http_app():
    flask_app = create_app(
        Config(database_url=OFFLINE_DB, secret_key=LONG_SECRET, environment="test")
    )

    def echo():
        return {"bytes": len(request.get_data())}

    def boom():
        raise RuntimeError("fallo sintético")

    for prefix in ("/auth", "/invitaciones", "/otra", "/authx"):
        flask_app.add_url_rule(f"{prefix}/_prueba", f"echo{prefix}", echo, methods=["GET", "POST"])
    flask_app.add_url_rule("/auth/_boom", "boom", boom)
    flask_app.add_url_rule("/auth/_sin_leer", "sin_leer", lambda: {}, methods=["POST"])
    return flask_app


@pytest.mark.parametrize(
    "path",
    ["/auth/_prueba", "/invitaciones/_prueba", "/auth/no-existe", "/auth/_boom", "/auth"],
)
def test_auth_paths_get_no_store_and_no_referrer(path):
    response = _http_app().test_client().get(path)

    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"


@pytest.mark.parametrize("path", ["/otra/_prueba", "/authx/_prueba", "/health-no-existe"])
def test_other_paths_do_not_get_the_auth_headers(path):
    response = _http_app().test_client().get(path)

    assert "no-store" not in response.headers.get("Cache-Control", "")
    assert "Referrer-Policy" not in response.headers


def test_auth_body_limit_is_4_kb():
    assert AUTH_MAX_BODY_BYTES == 4096


@pytest.mark.parametrize("path", ["/auth/_prueba", "/invitaciones/_prueba"])
def test_auth_body_at_the_limit_is_accepted(path):
    response = _http_app().test_client().post(path, data=b"x" * AUTH_MAX_BODY_BYTES)

    assert response.status_code == 200
    assert response.get_json() == {"bytes": AUTH_MAX_BODY_BYTES}


@pytest.mark.parametrize("path", ["/auth/_prueba", "/invitaciones/_prueba"])
def test_auth_body_over_the_limit_is_413_with_the_uniform_error(path):
    response = _http_app().test_client().post(path, data=b"x" * (AUTH_MAX_BODY_BYTES + 1))

    assert response.status_code == 413
    error = response.get_json()["error"]
    assert error["code"] == "cuerpo_demasiado_grande"
    assert uuid.UUID(error["request_id"])
    assert response.headers["Cache-Control"] == "no-store"


def test_auth_body_over_the_limit_without_content_length_is_413():
    # Cuerpo por chunks, sin Content-Length (el servidor WSGI marca wsgi.input_terminated,
    # como gunicorn): el límite se aplica al leer el flujo.
    response = (
        _http_app()
        .test_client()
        .post(
            "/auth/_prueba",
            input_stream=io.BytesIO(b"x" * (AUTH_MAX_BODY_BYTES + 1)),
            headers={"Transfer-Encoding": "chunked"},
            environ_overrides={"wsgi.input_terminated": True},
        )
    )

    assert response.status_code == 413
    assert response.get_json()["error"]["code"] == "cuerpo_demasiado_grande"


def test_auth_body_over_the_limit_is_413_even_if_the_view_does_not_read_it():
    client = _http_app().test_client()

    over = client.post("/auth/_sin_leer", data=b"x" * (AUTH_MAX_BODY_BYTES + 1))
    at_limit = client.post("/auth/_sin_leer", data=b"x" * AUTH_MAX_BODY_BYTES)

    assert over.status_code == 413
    assert at_limit.status_code == 200


def test_auth_body_at_the_limit_without_content_length_is_read_whole():
    response = (
        _http_app()
        .test_client()
        .post(
            "/auth/_prueba",
            input_stream=io.BytesIO(b"x" * AUTH_MAX_BODY_BYTES),
            headers={"Transfer-Encoding": "chunked"},
            environ_overrides={"wsgi.input_terminated": True},
        )
    )

    assert response.status_code == 200
    assert response.get_json() == {"bytes": AUTH_MAX_BODY_BYTES}


def test_other_paths_are_not_limited_to_4_kb():
    response = _http_app().test_client().post("/otra/_prueba", data=b"x" * 10_000)

    assert response.status_code == 200


# --- B6 de T4: reciclar conexiones del pool ------------------------------------------------


def test_engine_recycles_pooled_connections_every_30_minutes():
    # Acota la ventana en que una conexión vieja sigue viva tras un ALTER ROLE ... BYPASSRLS:
    # cada conexión nueva vuelve a pasar verify_connection_role.
    assert POOL_RECYCLE_SECONDS == 30 * 60
    flask_app = create_app(
        Config(database_url=OFFLINE_DB, secret_key=LONG_SECRET, environment="production")
    )
    with flask_app.app_context():
        engine = _get_database().engine
        assert engine.pool._recycle == POOL_RECYCLE_SECONDS
        assert engine.pool._pre_ping is True
