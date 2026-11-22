"""Autenticación de la consola de plataforma (spec 017, T2; R1–R6, R12–R13, R15, R35).

Sobre una base temporal migrada a ``head`` (``acceso_db``) con desarrolladores
sintéticos. Cubre:

- el flag ``PLATAFORMA_HABILITADA``: apagado, ninguna ruta ``/plataforma`` (``404``);
- login: token propio (``typ=plataforma``, sin ``tenant``, 10 min, clave con contexto
  propio), cookie propia (``__Secure-plat-refresh``, ``Path=/plataforma/auth``, 8 h),
  auditoría ``login_ok`` y el mismo ``401`` (con una sola verificación Argon2) para
  correo inexistente, contraseña errónea o desarrollador inactivo; límites de tasa;
- ``/auth/me`` y ``/modulos`` leen ``desarrollador.activo`` y la familia de refresh del
  token en cada petición: desactivar, restablecer o cerrar sesión cortan el token
  vigente (A20);
- refresh con rotación, reuso, CSRF y mismo sitio; logout que revoca la familia;
- cabeceras ``no-store``/``no-referrer``, restricción de red opcional y registro de
  módulos (un módulo de prueba aparece sin tocar el shell, R13);
- ningún log, respuesta ni ``repr`` contiene contraseña, hash, token ni correo.
"""

import dataclasses
import logging
import uuid
from collections.abc import Iterator

import jwt
import pytest
from acceso_db import (
    ADMIN_A,
    CONTADOR_A,
    PASSWORD,
    SECRET_KEY,
    TENANT_A,
    AccesoDb,
    bearer,
    dispose,
    temporary_acceso_db,
)
from flask import Blueprint, Flask, jsonify
from plataforma_db import (
    COOKIE,
    CSRF,
    DEV_PASSWORD,
    Dev,
    ejecutar,
    error_code,
    expired,
    filas,
    forged_platform,
    login,
    logout,
    make_plat_app,
    nuevo_dev,
    plat_bearer,
    plat_token,
    platform_claims,
    refresh,
    sembrar_dev,
)

from app import create_app
from app.auth.credentials import JWT_KEY_CONTEXT, Passwords, derive_key, token_storage_hash
from app.config import Config, RateLimits, load_config
from app.db import PlataformaLoginRow
from app.plataforma import modulos
from app.plataforma.config import PlataformaConfig, RedesNoValidasError
from app.plataforma.credenciales import (
    PLATAFORMA_JWT_CONTEXT,
    decode_platform_token,
)
from app.plataforma.decoradores import require_desarrollador

ENV = {
    "DATABASE_URL": "postgresql+psycopg://user:valor-secreto-db@db.invalid:5432/assetcontrol",
    "SECRET_KEY": "valor-secreto-clave-123",
    "ENVIRONMENT": "test",
}


# --- Flag y configuración (R1, A1) ------------------------------------------------------


def _rules(flask_app: Flask) -> list[str]:
    return [rule.rule for rule in flask_app.url_map.iter_rules()]


def test_without_the_flag_there_is_no_platform_route():
    flask_app = create_app(load_config(ENV))
    assert not [rule for rule in _rules(flask_app) if rule.startswith("/plataforma")]
    client = flask_app.test_client()
    for method, path in (
        ("post", "/plataforma/auth/login"),
        ("post", "/plataforma/auth/refresh"),
        ("get", "/plataforma/auth/me"),
        ("get", "/plataforma/modulos"),
    ):
        response = client.open(path, method=method, json={})
        assert response.status_code == 404, path
        assert error_code(response) == "no_encontrado"


@pytest.mark.parametrize("value", [None, "", "false", "1", "yes", "si", "verdadero", "truee"])
def test_only_true_enables_the_console(value):
    env = dict(ENV) if value is None else {**ENV, "PLATAFORMA_HABILITADA": value}
    assert load_config(env).plataforma.habilitada is False


@pytest.mark.parametrize("value", ["true", "TRUE", " true "])
def test_true_enables_the_console(value):
    config = load_config({**ENV, "PLATAFORMA_HABILITADA": value})
    assert config.plataforma.habilitada is True
    assert config.plataforma.redes_permitidas == ()
    flask_app = create_app(config)
    assert "/plataforma/auth/login" in _rules(flask_app)


def test_allowed_networks_are_parsed():
    config = load_config(
        {
            **ENV,
            "PLATAFORMA_HABILITADA": "true",
            "PLATAFORMA_REDES_PERMITIDAS": "10.0.0.0/8, 192.168.1.7 ,2001:db8::/32",
        }
    )
    assert [str(red) for red in config.plataforma.redes_permitidas] == [
        "10.0.0.0/8",
        "192.168.1.7/32",
        "2001:db8::/32",
    ]


@pytest.mark.parametrize("value", ["10.0.0.0/33", "no-es-una-red", "10.0.0.1/8", ",,"])
def test_invalid_networks_fail_without_echoing_the_value(value):
    with pytest.raises(RedesNoValidasError) as raised:
        load_config({**ENV, "PLATAFORMA_HABILITADA": "true", "PLATAFORMA_REDES_PERMITIDAS": value})
    assert value not in str(raised.value)
    assert "PLATAFORMA_REDES_PERMITIDAS" in str(raised.value)


def test_platform_rate_limits_default_and_are_tunable():
    assert RateLimits().plat_login_account == 5
    assert RateLimits().plat_login_ip == 10
    config = load_config(
        {**ENV, "RATE_LIMIT_PLAT_LOGIN_ACCOUNT": "3", "RATE_LIMIT_PLAT_LOGIN_IP": "7"}
    )
    assert (config.rate_limits.plat_login_account, config.rate_limits.plat_login_ip) == (3, 7)


PROD_URL = "postgresql+psycopg://app:valor-secreto-db@db.ejemplo.test:5432/assetcontrol"
REDES_AVISO = "198.51.100.0/24"


def _platform_network_warnings(caplog, **config) -> list[str]:
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        create_app(Config(database_url=PROD_URL, secret_key="k" * 40, **config))
    return [
        r.getMessage() for r in caplog.records if "PLATAFORMA_REDES_PERMITIDAS" in r.getMessage()
    ]


def test_production_with_networks_and_no_proxy_hops_warns_without_the_networks(caplog):
    redes = PlataformaConfig.desde_texto("true", REDES_AVISO)
    (aviso,) = _platform_network_warnings(caplog, environment="production", plataforma=redes)
    assert "TRUSTED_PROXY_HOPS" in aviso
    assert all(REDES_AVISO not in r.getMessage() for r in caplog.records)
    assert all("198.51.100" not in r.getMessage() for r in caplog.records)
    # Sin cualquiera de las tres condiciones, no hay aviso.
    assert not _platform_network_warnings(
        caplog, environment="production", plataforma=redes, trusted_proxy_hops=1
    )
    assert not _platform_network_warnings(
        caplog, environment="production", plataforma=PlataformaConfig.desde_texto("true", "")
    )
    assert not _platform_network_warnings(caplog, environment="test", plataforma=redes)


# --- Base y app ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def plat_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("plat_auth")


@pytest.fixture(scope="module")
def plat_app(plat_db) -> Iterator[Flask]:
    flask_app = make_plat_app(plat_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(plat_app):
    return plat_app.test_client(use_cookies=False)


@pytest.fixture(autouse=True)
def fresh_rate_limits(plat_db) -> Iterator[None]:
    ejecutar(plat_db, "delete from limite_tasa")
    yield


@pytest.fixture
def dev(plat_db) -> Dev:
    return sembrar_dev(plat_db, nuevo_dev())


def _login_ok(client, dev: Dev) -> tuple[dict, str]:
    response = login(client, dev.email)
    assert response.status_code == 200, response.get_json()
    return response.get_json(), _cookie(response)


def _cookie(response) -> str:
    for header in response.headers.getlist("Set-Cookie"):
        name, _, rest = header.partition("=")
        if name == COOKIE:
            return rest.split(";", 1)[0]
    raise AssertionError("sin cookie")


def _set_cookie_header(response) -> str:
    (header,) = [h for h in response.headers.getlist("Set-Cookie") if h.startswith(COOKIE + "=")]
    return header


def _familia(plat_db, value: str) -> uuid.UUID:
    secret = value.split(".", 1)[1]
    (row,) = filas(
        plat_db,
        "select familia_id from plataforma_refresh_token where token_hash = :h",
        {"h": token_storage_hash(secret)},
    )
    return row["familia_id"]


def _comparable_401(response) -> tuple:
    assert response.status_code == 401
    body = response.get_json()
    headers = sorted(
        (k.lower(), v) for k, v in response.headers.items() if k.lower() != "x-request-id"
    )
    return {k: v for k, v in body["error"].items() if k != "request_id"}, headers


# --- Login (R2, R3, A13) -----------------------------------------------------------------


def test_login_issues_a_platform_token_and_its_own_cookie(client, plat_db, dev):
    response = login(client, dev.email)
    assert response.status_code == 200
    body = response.get_json()
    assert set(body) == {"access_token", "token_type", "expires_in", "desarrollador"}
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 600
    assert body["desarrollador"] == {"id": str(dev.id), "email": dev.email, "nombre": dev.nombre}

    claims = jwt.decode(
        body["access_token"],
        derive_key(SECRET_KEY, PLATAFORMA_JWT_CONTEXT),
        algorithms=["HS256"],
        issuer="assetcontrol",
    )
    assert claims["typ"] == "plataforma"
    assert claims["sub"] == str(dev.id)
    assert "tenant" not in claims and "rol" not in claims
    assert claims["exp"] - claims["iat"] == 600

    header = _set_cookie_header(response)
    attributes = [part.strip().lower() for part in header.split(";")]
    assert "httponly" in attributes and "secure" in attributes
    assert "samesite=lax" in attributes
    assert "path=/plataforma/auth" in attributes
    assert "max-age=28800" in attributes
    value = _cookie(response)
    assert value.split(".", 1)[0] == str(dev.id)

    (fila,) = filas(
        plat_db,
        "select desarrollador_id, familia_id, expira_en - creado_en as ttl "
        "from plataforma_refresh_token where token_hash = :h",
        {"h": token_storage_hash(value.split(".", 1)[1])},
    )
    assert fila["desarrollador_id"] == dev.id
    assert fila["ttl"].total_seconds() == pytest.approx(8 * 3600, abs=5)
    assert claims["fam"] == str(fila["familia_id"])


def test_login_audits_login_ok_in_the_same_transaction(client, plat_db, dev):
    _login_ok(client, dev)
    rows = filas(
        plat_db,
        "select accion, resultado, desarrollador_id, tenant_id, objeto_id "
        "from plataforma_auditoria where desarrollador_id = :d",
        {"d": dev.id},
    )
    assert rows == [
        {
            "accion": "login_ok",
            "resultado": "ok",
            "desarrollador_id": dev.id,
            "tenant_id": None,
            "objeto_id": dev.id,
        }
    ]


def test_login_normalizes_the_email(client, dev):
    response = login(client, f"  {dev.email.upper()} ")
    assert response.status_code == 200


def test_every_failed_login_is_the_same_401_with_one_verification(
    client, plat_db, dev, monkeypatch
):
    inactivo = sembrar_dev(plat_db, nuevo_dev("inactivo"), activo=False)
    calls: list[str | None] = []
    original = Passwords.verify

    def spy(self, stored_hash, password):
        calls.append("simulado" if stored_hash is None else "real")
        return original(self, stored_hash, password)

    monkeypatch.setattr(Passwords, "verify", spy)
    cases = {
        "inexistente": (login(client, "nadie.registrado@ejemplo.test"), ["simulado"]),
        "contrasena": (login(client, dev.email, "Otra-Clave-Incorrecta-123"), ["real"]),
        "inactivo": (login(client, inactivo.email), ["real"]),
        "no_normalizable": (login(client, "\x00"), ["simulado"]),
    }
    seen = set()
    offset = 0
    for name, (response, expected) in cases.items():
        assert error_code(response) == "credenciales_invalidas", name
        assert not response.headers.getlist("Set-Cookie"), name
        seen.add(repr(_comparable_401(response)))
        assert calls[offset : offset + len(expected)] == expected, name
        offset += len(expected)
    assert len(seen) == 1
    assert (
        filas(
            plat_db,
            "select 1 from plataforma_auditoria where desarrollador_id in (:a, :b)",
            {"a": dev.id, "b": inactivo.id},
        )
        == []
    )


def test_tenant_credentials_do_not_open_the_console(client):
    for cuenta in (ADMIN_A, CONTADOR_A):
        response = login(client, cuenta.email, PASSWORD)
        assert response.status_code == 401
        assert error_code(response) == "credenciales_invalidas"


@pytest.mark.parametrize(
    "body", [None, {}, {"email": 1, "password": "x"}, {"email": "a@b.c"}, ["x"]]
)
def test_malformed_login_body_is_400(client, body):
    response = client.post("/plataforma/auth/login", json=body)
    assert response.status_code == 400
    assert error_code(response) == "solicitud_invalida"


def test_login_body_over_4kb_is_413(client):
    response = client.post(
        "/plataforma/auth/login", data="x" * 5000, content_type="application/json"
    )
    assert response.status_code == 413


def test_sixth_failed_login_of_an_account_is_429(plat_db):
    flask_app = make_plat_app(plat_db, rate_limits=RateLimits())
    try:
        own = flask_app.test_client(use_cookies=False)
        dev = sembrar_dev(plat_db, nuevo_dev("limite"))
        statuses = [login(own, dev.email, "Clave-Erronea-Numero-1").status_code for _ in range(6)]
        assert statuses == [401] * 5 + [429]
        # Superado el límite, ni la contraseña correcta entra.
        assert login(own, dev.email).status_code == 429
        assert error_code(login(own, dev.email)) == "demasiadas_solicitudes"
    finally:
        dispose(flask_app)


def test_eleventh_failed_login_of_an_ip_is_429(plat_db):
    flask_app = make_plat_app(plat_db, rate_limits=RateLimits())
    try:
        own = flask_app.test_client(use_cookies=False)
        statuses = [
            login(own, f"ip{i}.{uuid.uuid4().hex[:6]}@ejemplo.test").status_code for i in range(11)
        ]
        assert statuses == [401] * 10 + [429]
    finally:
        dispose(flask_app)


def test_successful_logins_give_back_their_attempt(plat_db):
    flask_app = make_plat_app(plat_db, rate_limits=RateLimits())
    try:
        own = flask_app.test_client(use_cookies=False)
        dev = sembrar_dev(plat_db, nuevo_dev("devuelve"))
        assert [login(own, dev.email).status_code for _ in range(7)] == [200] * 7
    finally:
        dispose(flask_app)


def test_platform_counters_use_their_own_scopes(client, plat_db, dev):
    login(client, dev.email, "Clave-Erronea-Numero-1")
    ambitos = {row["ambito"] for row in filas(plat_db, "select ambito from limite_tasa")}
    assert ambitos == {"plat_login_ip", "plat_login_cuenta"}


def test_platform_refresh_counts_in_its_own_scope(client, plat_db, dev):
    """Spec 017, T4 (O1): el refresh de plataforma ya no comparte ``refresh_ip``."""
    from plataforma_db import refresh as plat_refresh

    plat_refresh(client, None)
    ambitos = {row["ambito"] for row in filas(plat_db, "select ambito from limite_tasa")}
    assert ambitos == {"plat_refresh_ip"}


def test_the_n_plus_first_platform_refresh_of_an_ip_is_429(plat_db):
    from plataforma_db import HIGH_LIMITS, cookie_value
    from plataforma_db import refresh as plat_refresh

    limites = dataclasses.replace(HIGH_LIMITS, plat_refresh_ip=3, refresh_ip=1000)
    flask_app = make_plat_app(plat_db, rate_limits=limites)
    try:
        own = flask_app.test_client(use_cookies=False)
        dev = sembrar_dev(plat_db, nuevo_dev("refresh-limite"))
        statuses = [plat_refresh(own, "x.y").status_code for _ in range(3)]
        assert statuses == [401] * 3
        valida = cookie_value(login(own, dev.email))
        bloqueada = plat_refresh(own, valida)
        assert bloqueada.status_code == 429
        assert error_code(bloqueada) == "demasiadas_solicitudes"
        assert "Set-Cookie" not in bloqueada.headers
        # El refresh del tenant tiene su propio contador: sigue respondiendo 401, no 429.
        tenant = own.post("/auth/refresh", headers=CSRF)
        assert tenant.status_code == 401
    finally:
        dispose(flask_app)


def test_platform_action_and_refresh_limits_default_and_are_tunable():
    assert (RateLimits().plat_accion, RateLimits().plat_refresh_ip) == (60, 30)
    config = load_config({**ENV, "RATE_LIMIT_PLAT_ACCION": "4", "RATE_LIMIT_PLAT_REFRESH_IP": "9"})
    assert (config.rate_limits.plat_accion, config.rate_limits.plat_refresh_ip) == (4, 9)


# --- Petición autenticada (R4, R5, A20) --------------------------------------------------


def test_me_returns_the_developer(client, dev):
    body, _ = _login_ok(client, dev)
    response = client.get("/plataforma/auth/me", headers=plat_bearer(body["access_token"]))
    assert response.status_code == 200
    assert response.get_json() == {
        "desarrollador": {"id": str(dev.id), "email": dev.email, "nombre": dev.nombre}
    }


def _invalid_tokens(dev: Dev, familia: uuid.UUID) -> dict[str, dict]:
    tenant_key = derive_key(SECRET_KEY, JWT_KEY_CONTEXT)
    return {
        "sin_token": {},
        "basura": plat_bearer("no-es-un-jwt"),
        "vencido": plat_bearer(expired(dev, familia)),
        "admin": bearer(ADMIN_A, TENANT_A, rol="admin"),
        "contador": bearer(CONTADOR_A, TENANT_A, rol="contador"),
        "clave_de_tenant": plat_bearer(forged_platform(platform_claims(dev, familia), tenant_key)),
        "otro_typ": plat_bearer(forged_platform(platform_claims(dev, familia, typ="acceso"))),
        "sin_typ": plat_bearer(forged_platform(platform_claims(dev, familia, typ=None))),
        "con_tenant": plat_bearer(
            forged_platform(platform_claims(dev, familia, tenant=str(TENANT_A)))
        ),
        "sin_fam": plat_bearer(forged_platform(platform_claims(dev, familia, fam=None))),
        "otro_iss": plat_bearer(forged_platform(platform_claims(dev, familia, iss="otro"))),
        "familia_ajena": plat_bearer(plat_token(dev, uuid.uuid4())),
        "dev_inexistente": plat_bearer(plat_token(nuevo_dev(), familia)),
        "alg_none": plat_bearer(jwt.encode(platform_claims(dev, familia), None, algorithm="none")),
    }


def test_invalid_tokens_are_401(client, plat_db, dev):
    _, value = _login_ok(client, dev)
    familia = _familia(plat_db, value)
    # Control: el token bien formado de esa familia sí entra.
    assert (
        client.get("/plataforma/auth/me", headers=plat_bearer(plat_token(dev, familia))).status_code
        == 200
    )
    for name, headers in _invalid_tokens(dev, familia).items():
        for path in ("/plataforma/auth/me", "/plataforma/modulos"):
            response = client.get(path, headers=headers)
            assert response.status_code == 401, (name, path)
            assert error_code(response) == "no_autenticado"


def test_deactivated_developer_with_a_live_token_is_401(client, plat_db, dev):
    body, _ = _login_ok(client, dev)
    headers = plat_bearer(body["access_token"])
    ejecutar(plat_db, "update desarrollador set activo = false where id = :d", {"d": dev.id})
    try:
        assert client.get("/plataforma/auth/me", headers=headers).status_code == 401
        assert client.get("/plataforma/modulos", headers=headers).status_code == 401
    finally:
        ejecutar(plat_db, "update desarrollador set activo = true where id = :d", {"d": dev.id})
    # Sin revocar la familia, reactivar devuelve el acceso al mismo token.
    assert client.get("/plataforma/auth/me", headers=headers).status_code == 200


def test_cli_deactivation_cuts_token_and_refresh_and_reactivation_allows_login(
    client, plat_db, dev
):
    body, value = _login_ok(client, dev)
    headers = plat_bearer(body["access_token"])
    ejecutar(plat_db, "select acceso.cambiar_estado_desarrollador(:e, false)", {"e": dev.email})
    assert client.get("/plataforma/auth/me", headers=headers).status_code == 401
    assert refresh(client, value).status_code == 401
    assert login(client, dev.email).status_code == 401

    ejecutar(plat_db, "select acceso.cambiar_estado_desarrollador(:e, true)", {"e": dev.email})
    # La familia quedó revocada: el token viejo no vuelve; un login nuevo sí entra.
    assert client.get("/plataforma/auth/me", headers=headers).status_code == 401
    new_body, _ = _login_ok(client, dev)
    me = client.get("/plataforma/auth/me", headers=plat_bearer(new_body["access_token"]))
    assert me.status_code == 200


def test_cli_reset_revokes_the_live_token_and_refresh(client, plat_db, dev):
    import argon2

    from app.auth.credentials import ARGON2_TEST_PARAMS

    body, value = _login_ok(client, dev)
    nueva = "Clave-Restablecida-Plataforma-1"
    hashed = argon2.PasswordHasher.from_parameters(ARGON2_TEST_PARAMS).hash(nueva)
    ejecutar(
        plat_db,
        "select acceso.restablecer_desarrollador(:e, :h)",
        {"e": dev.email, "h": hashed},
    )
    assert (
        client.get("/plataforma/auth/me", headers=plat_bearer(body["access_token"])).status_code
        == 401
    )
    assert refresh(client, value).status_code == 401
    assert login(client, dev.email).status_code == 401
    assert login(client, dev.email, nueva).status_code == 200


# --- Refresh y logout (R2, R6) ------------------------------------------------------------


def test_refresh_rotates_the_cookie_and_issues_a_new_token(client, plat_db, dev):
    _, value = _login_ok(client, dev)
    response = refresh(client, value)
    assert response.status_code == 200
    body = response.get_json()
    assert set(body) == {"access_token", "token_type", "expires_in", "desarrollador"}
    nuevo = _cookie(response)
    assert nuevo != value
    assert _familia(plat_db, nuevo) == _familia(plat_db, value)
    claims = decode_platform_token(SECRET_KEY, body["access_token"])
    assert claims.sub == dev.id and claims.familia == _familia(plat_db, value)
    assert "path=/plataforma/auth" in _set_cookie_header(response).lower()
    # La cookie vieja ya se usó (dentro de la ventana de gracia: 401 sin revocar).
    assert refresh(client, value).status_code == 401
    assert refresh(client, nuevo).status_code == 200


def test_reuse_outside_the_grace_window_revokes_the_family(client, plat_db, dev):
    body, value = _login_ok(client, dev)
    nuevo = _cookie(refresh(client, value))
    ejecutar(
        plat_db,
        "update plataforma_refresh_token set usado_en = usado_en - interval '1 minute' "
        "where token_hash = :h",
        {"h": token_storage_hash(value.split(".", 1)[1])},
    )
    assert refresh(client, value).status_code == 401
    assert refresh(client, nuevo).status_code == 401
    me = client.get("/plataforma/auth/me", headers=plat_bearer(body["access_token"]))
    assert me.status_code == 401


def test_rejected_refreshes_are_indistinguishable(client, plat_db, dev):
    _, value = _login_ok(client, dev)
    expirado = _cookie(login(client, dev.email))
    ejecutar(
        plat_db,
        "update plataforma_refresh_token set expira_en = now() - interval '1 second' "
        "where token_hash = :h",
        {"h": token_storage_hash(expirado.split(".", 1)[1])},
    )
    otro = sembrar_dev(plat_db, nuevo_dev("otro"))
    cases = {
        "sin_cookie": refresh(client, None),
        "basura": refresh(client, "basura"),
        "secreto_falso": refresh(client, f"{dev.id}.{'A' * 43}"),
        "otro_dev": refresh(client, f"{otro.id}.{value.split('.', 1)[1]}"),
        "tenant": refresh(client, f"{TENANT_A}.{value.split('.', 1)[1]}"),
        "vencida": refresh(client, expirado),
    }
    seen = set()
    for name, response in cases.items():
        assert error_code(response) == "no_autenticado", name
        assert not response.headers.getlist("Set-Cookie"), name
        seen.add(repr(_comparable_401(response)))
    assert len(seen) == 1
    # Probar con el dev ajeno no quemó la cookie buena.
    assert refresh(client, value).status_code == 200


def _familia_revocada(plat_db, familia: uuid.UUID) -> bool:
    rows = filas(
        plat_db,
        "select revocado_en from plataforma_refresh_token where familia_id = :f",
        {"f": familia},
    )
    assert rows
    return any(row["revocado_en"] is not None for row in rows)


def test_cross_developer_cookie_neither_refreshes_nor_revokes(client, plat_db, dev):
    """Hallazgo 3c (T2): ``<id_dev_B>.<secreto_de_A>`` no sirve ni quema la familia de A."""
    body, value = _login_ok(client, dev)
    familia = _familia(plat_db, value)
    otro = sembrar_dev(plat_db, nuevo_dev("cruzado"))
    _login_ok(client, otro)
    cruzada = f"{otro.id}.{value.split('.', 1)[1]}"

    rechazado = refresh(client, cruzada)
    assert rechazado.status_code == 401
    assert error_code(rechazado) == "no_autenticado"
    assert not rechazado.headers.getlist("Set-Cookie")
    assert not _familia_revocada(plat_db, familia)

    # El logout responde siempre 204 y borra la cookie (contrato de T2): no hay 401 que dar,
    # pero no debe revocar la familia de A.
    assert logout(client, cruzada).status_code == 204
    assert not _familia_revocada(plat_db, familia)

    me = client.get("/plataforma/auth/me", headers=plat_bearer(body["access_token"]))
    assert me.status_code == 200
    assert refresh(client, value).status_code == 200


def test_refresh_creates_a_new_row_that_expires_in_8_hours(client, plat_db, dev):
    """Hallazgo 3d (T2): la rotación inserta una fila nueva con su propio TTL de 8 h."""
    _, value = _login_ok(client, dev)
    response = refresh(client, value)
    assert response.status_code == 200
    nuevo = _cookie(response)
    hashes = {
        "viejo": token_storage_hash(value.split(".", 1)[1]),
        "nuevo": token_storage_hash(nuevo.split(".", 1)[1]),
    }
    rows = {
        name: filas(
            plat_db,
            "select id, familia_id, desarrollador_id, usado_en, "
            "extract(epoch from expira_en - creado_en) as ttl, "
            "extract(epoch from expira_en - now()) as restante "
            "from plataforma_refresh_token where token_hash = :h",
            {"h": token_hash},
        )
        for name, token_hash in hashes.items()
    }
    (viejo,) = rows["viejo"]
    (fila,) = rows["nuevo"]
    assert fila["id"] != viejo["id"]
    assert fila["familia_id"] == viejo["familia_id"]
    assert fila["desarrollador_id"] == dev.id
    assert fila["usado_en"] is None and viejo["usado_en"] is not None
    assert float(fila["ttl"]) == pytest.approx(8 * 3600, abs=5)
    assert float(fila["restante"]) == pytest.approx(8 * 3600, abs=60)


def test_refresh_of_a_deactivated_developer_is_401(client, plat_db, dev):
    _, value = _login_ok(client, dev)
    ejecutar(plat_db, "update desarrollador set activo = false where id = :d", {"d": dev.id})
    try:
        assert refresh(client, value).status_code == 401
    finally:
        ejecutar(plat_db, "update desarrollador set activo = true where id = :d", {"d": dev.id})


def test_refresh_of_a_revoked_family_is_401(client, plat_db, dev):
    _, value = _login_ok(client, dev)
    ejecutar(
        plat_db,
        "update plataforma_refresh_token set revocado_en = now() where familia_id = :f",
        {"f": _familia(plat_db, value)},
    )
    assert refresh(client, value).status_code == 401


@pytest.mark.parametrize(
    "headers",
    [
        {"X-AssetControl-CSRF": "0"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Origin": "https://sitio-ajeno.example"},
        {"Origin": "null"},
    ],
    ids=["csrf_0", "cross_site", "origin_ajeno", "origin_null"],
)
def test_refresh_and_logout_require_csrf_and_same_site(client, dev, headers):
    _, value = _login_ok(client, dev)
    cookie = {"Cookie": f"{COOKIE}={value}"}
    for path in ("/plataforma/auth/refresh", "/plataforma/auth/logout"):
        response = client.post(path, headers={**CSRF, **cookie, **headers})
        assert response.status_code == 403, path
        assert error_code(response) == "prohibido"
    sin_csrf = client.post("/plataforma/auth/refresh", headers=cookie)
    assert sin_csrf.status_code == 403
    # Nada se consumió: la cookie sigue sirviendo.
    assert refresh(client, value).status_code == 200


def test_logout_revokes_the_family_cuts_the_token_and_clears_the_cookie(client, plat_db, dev):
    body, value = _login_ok(client, dev)
    response = logout(client, value)
    assert response.status_code == 204
    header = _set_cookie_header(response).lower()
    assert "max-age=0" in header or "expires=thu, 01 jan 1970" in header
    assert "path=/plataforma/auth" in header
    assert refresh(client, value).status_code == 401
    me = client.get("/plataforma/auth/me", headers=plat_bearer(body["access_token"]))
    assert me.status_code == 401
    rows = filas(
        plat_db,
        "select revocado_en from plataforma_refresh_token where familia_id = :f",
        {"f": _familia(plat_db, value)},
    )
    assert rows and all(row["revocado_en"] is not None for row in rows)


def test_logout_without_a_valid_cookie_is_204(client):
    assert logout(client, None).status_code == 204
    assert logout(client, "basura").status_code == 204


def test_development_cookie_has_no_secure_prefix(plat_db):
    flask_app = make_plat_app(plat_db, environment="development")
    try:
        own = flask_app.test_client(use_cookies=False)
        dev = sembrar_dev(plat_db, nuevo_dev("desarrollo"))
        response = login(own, dev.email)
        (header,) = [
            h for h in response.headers.getlist("Set-Cookie") if h.startswith("plat-refresh=")
        ]
        attributes = [part.strip().lower() for part in header.split(";")]
        assert "secure" not in attributes
        assert "path=/plataforma/auth" in attributes
    finally:
        dispose(flask_app)


# --- Módulos (R12, R13) ------------------------------------------------------------------


def test_modules_endpoint_lists_the_server_registry(client, dev):
    body, _ = _login_ok(client, dev)
    response = client.get("/plataforma/modulos", headers=plat_bearer(body["access_token"]))
    assert response.status_code == 200
    assert response.get_json() == {
        "modulos": [
            {"id": modulo.id, "titulo": modulo.titulo, "orden": modulo.orden}
            for modulo in sorted(modulos.MODULOS, key=lambda m: m.orden)
        ]
    }


def test_a_test_module_registers_without_touching_the_shell(plat_db, monkeypatch):
    bp = Blueprint("plataforma_prueba", __name__, url_prefix="/plataforma/prueba")

    @bp.get("")
    @require_desarrollador
    def ver():
        return jsonify(ok=True)

    prueba = modulos.Modulo(id="prueba", titulo="Prueba", orden=99, blueprint=bp)
    monkeypatch.setattr(modulos, "MODULOS", (*modulos.MODULOS, prueba))
    flask_app = make_plat_app(plat_db)
    try:
        own = flask_app.test_client(use_cookies=False)
        dev = sembrar_dev(plat_db, nuevo_dev("modulo"))
        token = login(own, dev.email).get_json()["access_token"]
        listed = own.get("/plataforma/modulos", headers=plat_bearer(token)).get_json()["modulos"]
        assert {"id": "prueba", "titulo": "Prueba", "orden": 99} in listed
        assert own.get("/plataforma/prueba", headers=plat_bearer(token)).get_json() == {"ok": True}
        assert own.get("/plataforma/prueba").status_code == 401
    finally:
        dispose(flask_app)


# --- Cabeceras y red (R15, R1) -----------------------------------------------------------


def test_every_platform_response_is_no_store_and_no_referrer(client, dev):
    body, value = _login_ok(client, dev)
    token = plat_bearer(body["access_token"])
    responses = [
        login(client, dev.email),
        login(client, dev.email, "Clave-Erronea-Numero-1"),
        client.post("/plataforma/auth/login", json={}),
        client.get("/plataforma/auth/me", headers=token),
        client.get("/plataforma/auth/me"),
        client.get("/plataforma/modulos", headers=token),
        refresh(client, value),
        client.post("/plataforma/auth/refresh"),
        logout(client, None),
        client.get("/plataforma/no-existe"),
        client.get("/plataforma/auth/login"),
    ]
    for response in responses:
        assert response.headers["Cache-Control"] == "no-store", response.status_code
        assert response.headers["Referrer-Policy"] == "no-referrer", response.status_code


def test_allowed_networks_hide_the_console_from_other_addresses(plat_db):
    flask_app = make_plat_app(plat_db, redes=("10.0.0.0/8",))
    try:
        own = flask_app.test_client(use_cookies=False)
        dev = sembrar_dev(plat_db, nuevo_dev("red"))
        fuera = login(own, dev.email, environ_base={"REMOTE_ADDR": "203.0.113.5"})
        assert fuera.status_code == 404
        assert error_code(fuera) == "no_encontrado"
        assert (
            own.get("/plataforma/modulos", environ_base={"REMOTE_ADDR": "203.0.113.5"}).status_code
            == 404
        )
        dentro = login(own, dev.email, environ_base={"REMOTE_ADDR": "10.2.3.4"})
        assert dentro.status_code == 200
        # El resto de la API no se ve afectado por la lista de redes.
        assert own.get("/health", environ_base={"REMOTE_ADDR": "203.0.113.5"}).status_code in (
            200,
            503,
        )
    finally:
        dispose(flask_app)


def _comparable_404(response) -> tuple:
    assert response.status_code == 404
    body = response.get_json()
    headers = sorted(
        (k.lower(), v) for k, v in response.headers.items() if k.lower() != "x-request-id"
    )
    return {k: v for k, v in body["error"].items() if k != "request_id"}, headers


def test_blocked_network_404_is_identical_to_the_flag_off_404(plat_db):
    """Hallazgo 1 (T2): fuera de la red, el 404 no delata que la consola existe."""
    blocked = make_plat_app(plat_db, redes=("10.0.0.0/8",))
    off = make_plat_app(plat_db, habilitada=False)
    try:
        fuera = {"environ_base": {"REMOTE_ADDR": "203.0.113.5"}}
        for method, path in (
            ("post", "/plataforma/auth/login"),
            ("post", "/plataforma/auth/refresh"),
            ("post", "/plataforma/auth/logout"),
            ("get", "/plataforma/auth/me"),
            ("get", "/plataforma/modulos"),
            ("get", "/plataforma"),
            ("get", "/plataforma/no-existe"),
        ):
            hidden = blocked.test_client(use_cookies=False).open(
                path, method=method, json={}, **fuera
            )
            missing = off.test_client(use_cookies=False).open(path, method=method, json={}, **fuera)
            assert _comparable_404(hidden) == _comparable_404(missing), path
            assert "Cache-Control" not in hidden.headers, path
            assert "Referrer-Policy" not in hidden.headers, path
    finally:
        dispose(blocked)
        dispose(off)


def test_forged_forwarded_for_does_not_open_the_console(plat_db):
    """Hallazgo 3a (T2): solo cuenta el salto que añade el proxy de confianza."""
    dev = sembrar_dev(plat_db, nuevo_dev("xff"))
    behind_proxy = make_plat_app(plat_db, redes=("10.0.0.0/8",), trusted_proxy_hops=1)
    direct = make_plat_app(plat_db, redes=("10.0.0.0/8",))
    try:
        own = behind_proxy.test_client(use_cookies=False)
        # El cliente antepone una IP permitida; el proxy añade la real al final.
        forged = login(
            own,
            dev.email,
            headers={"X-Forwarded-For": "10.1.1.1, 203.0.113.5"},
            environ_base={"REMOTE_ADDR": "10.0.0.2"},
        )
        assert forged.status_code == 404
        allowed = login(
            own,
            dev.email,
            headers={"X-Forwarded-For": "203.0.113.5, 10.1.1.1"},
            environ_base={"REMOTE_ADDR": "10.0.0.2"},
        )
        assert allowed.status_code == 200

        own = direct.test_client(use_cookies=False)
        # Sin saltos de confianza, X-Forwarded-For se ignora en los dos sentidos.
        assert (
            login(
                own,
                dev.email,
                headers={"X-Forwarded-For": "10.1.1.1"},
                environ_base={"REMOTE_ADDR": "203.0.113.5"},
            ).status_code
            == 404
        )
        assert (
            login(
                own,
                dev.email,
                headers={"X-Forwarded-For": "203.0.113.5"},
                environ_base={"REMOTE_ADDR": "10.2.3.4"},
            ).status_code
            == 200
        )
    finally:
        dispose(behind_proxy)
        dispose(direct)


# --- Secretos (R35, A11, A12) -------------------------------------------------------------


def test_no_log_or_response_contains_secrets(client, plat_db, caplog):
    dev = sembrar_dev(plat_db, nuevo_dev("secretos"))
    (stored,) = filas(
        plat_db, "select password_hash from desarrollador where id = :d", {"d": dev.id}
    )
    caplog.set_level(logging.DEBUG)
    ok = login(client, dev.email)
    value = _cookie(ok)
    token = ok.get_json()["access_token"]
    responses = [
        ok,
        login(client, dev.email, "Clave-Erronea-Secreta-77"),
        login(client, "no.existe.secreto@ejemplo.test", "Clave-Erronea-Secreta-77"),
        client.get("/plataforma/auth/me", headers=plat_bearer(token)),
        refresh(client, value),
        logout(client, value),
    ]
    logs = caplog.text + "".join(repr(record.args) for record in caplog.records)
    secrets = [
        DEV_PASSWORD,
        "Clave-Erronea-Secreta-77",
        stored["password_hash"],
        token,
        value,
        value.split(".", 1)[1],
        dev.email,
        "no.existe.secreto@ejemplo.test",
    ]
    for secret in secrets:
        assert secret not in logs
    bodies = "".join(response.get_data(as_text=True) for response in responses[1:])
    for secret in (DEV_PASSWORD, stored["password_hash"], "argon2"):
        assert secret not in bodies
        assert secret not in ok.get_data(as_text=True)


def test_login_row_repr_hides_the_hash():
    row = PlataformaLoginRow(id=uuid.uuid4(), password_hash="$argon2id$secreto", activo=True)
    assert "argon2" not in repr(row)
    assert "secreto" not in str(row)


def test_audit_never_stores_secrets(client, plat_db, dev):
    _login_ok(client, dev)
    (row,) = filas(
        plat_db,
        "select to_jsonb(a)::text as fila from plataforma_auditoria a where desarrollador_id = :d",
        {"d": dev.id},
    )
    for secret in (dev.email, dev.nombre, DEV_PASSWORD, "argon2", "127.0.0.1"):
        assert secret not in row["fila"]


def test_platform_config_is_off_by_default():
    config = Config(database_url="postgresql://x@y/z", secret_key="k", environment="test")
    assert config.plataforma == PlataformaConfig()
    assert config.plataforma.habilitada is False


def test_password_policy_is_not_applied_on_login(client, plat_db):
    """El login no revela la política: una contraseña corta es el mismo 401."""
    dev = sembrar_dev(plat_db, nuevo_dev("politica"))
    assert error_code(login(client, dev.email, "corta")) == "credenciales_invalidas"
    assert error_code(login(client, dev.email, "x" * 200)) == "credenciales_invalidas"
