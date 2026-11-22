"""Cambio obligatorio de contraseña en el primer ingreso (spec 017, T4; R25–R28, A16, A12).

Sobre una base temporal migrada a ``head`` (tenants sintéticos A y B de ``acceso_db``) y con
la consola de plataforma habilitada:

- La marca ``usuario.debe_cambiar_password``: ``false`` en los usuarios existentes y en los
  invitados; ``true`` en el primer admin de una empresa creada desde la consola; el login y
  ``GET /auth/me`` la informan.
- Bloqueo central (A16): con la marca, **cada** endpoint de tenant con ``required_roles``
  (recorrido de ``url_map``) responde ``403 cambio_password_requerido``, para admin y
  contador, salvo ``GET /auth/me`` y ``POST /auth/cambiar-contrasena``; login, refresh y
  logout siguen sirviendo. La marca se lee de la base en cada petición (no del JWT).
- ``POST /auth/cambiar-contrasena``: actual errónea ``401``; nueva igual a la actual,
  confirmación distinta o fuera de la política ``422``; cuerpo mal formado ``400``; cambia el
  hash, quita la marca, revoca las demás familias de refresh y responde una sesión nueva;
  ``429`` por el límite de login antes de Argon2.
- M1 (0026): el JWT de acceso emitido antes del cambio (o del restablecer de la 014) da
  ``401 no_autenticado``; el de la sesión nueva y los emitidos en el mismo segundo del corte
  siguen sirviendo. Atomicidad, concurrencia, IDOR, ámbitos de ``limite_tasa`` separados de
  los de plataforma y la cuenta con dos membresías.
- ``acceso.cambiar_password_propio``: tenant ajeno, usuario inactivo o hash actual distinto
  -> ``cambio_invalido`` sin cambios; hash nuevo mal formado -> ``hash_invalido``. La
  aplicación no puede escribir la marca.
- La recuperación de la 014 deja la marca en ``false`` (R28).
- Ningún log contiene contraseñas, hashes ni tokens (A12).

Datos sintéticos (``@ejemplo.test``).
"""

import hashlib
import logging
import re
import threading
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import argon2
import jwt
import pytest
from acceso_db import (
    ADMIN_A,
    ADMIN_B,
    PASSWORD,
    SECRET_KEY,
    TENANT_A,
    TENANT_B,
    AccesoDb,
    dispose,
    temporary_acceso_db,
)
from flask import Flask
from plataforma_db import (
    CSRF,
    DEV_PASSWORD,
    Dev,
    cookie_value,
    error_code,
    filas,
    login,
    make_plat_app,
    nuevo_dev,
    refresh,
    sembrar_dev,
)
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from app.auth import service as auth_service
from app.auth.credentials import (
    ARGON2_TEST_PARAMS,
    JWT_ISSUER,
    JWT_KEY_CONTEXT,
    derive_key,
    encode_access_token,
)
from app.auth.decorators import PASSWORD_CHANGE_ENDPOINTS
from app.auth.http import REFRESH_COOKIE_SECURE_NAME
from app.config import RateLimits

NUEVA = "Clave-Nueva-Sintetica-2026"
INICIAL = "Clave-Inicial-Sintetica-2026"
RUTA = "/auth/cambiar-contrasena"
BLOQUEO = "cambio_password_requerido"


@pytest.fixture(scope="module")
def cp_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("cambio_pw")


@pytest.fixture(scope="module")
def cp_app(cp_db) -> Iterator[Flask]:
    flask_app = make_plat_app(cp_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(cp_app):
    return cp_app.test_client(use_cookies=False)


@pytest.fixture(scope="module")
def dev_headers(cp_db, cp_app) -> dict[str, str]:
    dev = sembrar_dev(cp_db, nuevo_dev("cambio"))
    response = login(cp_app.test_client(use_cookies=False), dev.email)
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['access_token']}"}


@pytest.fixture(autouse=True)
def fresh_rate_limits(cp_db) -> Iterator[None]:
    with cp_db.migrator.begin() as conn:
        conn.execute(text("delete from limite_tasa"))
    yield


def _hash(password: str) -> str:
    return argon2.PasswordHasher.from_parameters(ARGON2_TEST_PARAMS).hash(password)


def _cuenta(
    db: AccesoDb,
    *,
    rol: str = "admin",
    tenant: uuid.UUID = TENANT_A,
    marca: bool = True,
    password: str = INICIAL,
) -> tuple[uuid.UUID, str]:
    """Usuario nuevo con membresía activa en ``tenant`` (sembrado por el migrador)."""
    usuario = uuid.uuid4()
    email = f"cambio.{uuid.uuid4().hex[:10]}@ejemplo.test"
    with db.migrator.begin() as conn:
        conn.execute(
            text(
                "insert into usuario (id, email, nombre, password_hash, debe_cambiar_password) "
                "values (:id, :e, 'Persona Sintética', :h, :m)"
            ),
            {"id": usuario, "e": email, "h": _hash(password), "m": marca},
        )
        conn.execute(
            text("insert into membresia (tenant_id, usuario_id, rol) values (:t, :u, :r)"),
            {"t": tenant, "u": usuario, "r": rol},
        )
    return usuario, email


def _marca(db: AccesoDb, usuario: uuid.UUID) -> bool:
    (row,) = filas(db, "select debe_cambiar_password from usuario where id = :u", {"u": usuario})
    return row["debe_cambiar_password"]


def _password_hash(db: AccesoDb, usuario: uuid.UUID) -> str:
    (row,) = filas(db, "select password_hash from usuario where id = :u", {"u": usuario})
    return row["password_hash"]


def _login(client, email: str, password: str = INICIAL):
    return client.post("/auth/login", json={"email": email, "password": password})


def _bearer(response) -> dict[str, str]:
    return {"Authorization": f"Bearer {response.get_json()['access_token']}"}


def _cookie(response) -> str:
    for header in response.headers.getlist("Set-Cookie"):
        name, _, rest = header.partition("=")
        if name == REFRESH_COOKIE_SECURE_NAME:
            return rest.split(";", 1)[0]
    raise AssertionError("sin cookie de refresh")


def _refresh(client, cookie: str):
    return client.post(
        "/auth/refresh", headers={**CSRF, "Cookie": f"{REFRESH_COOKIE_SECURE_NAME}={cookie}"}
    )


def _cambiar(client, headers, actual=INICIAL, nueva=NUEVA, confirmacion=None):
    body = {
        "actual": actual,
        "nueva": nueva,
        "confirmacion": nueva if confirmacion is None else confirmacion,
    }
    return client.post(RUTA, json=body, headers=headers)


def _tenant_routes(flask_app: Flask) -> list[tuple[str, str, str]]:
    found = []
    for rule in flask_app.url_map.iter_rules():
        if rule.rule.startswith("/plataforma"):
            continue
        view = flask_app.view_functions[rule.endpoint]
        if getattr(view, "required_roles", None) is None:
            continue
        path = re.sub(r"<(?:[^:<>]+:)?[^<>]+>", str(uuid.uuid4()), rule.rule)
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            found.append((rule.endpoint, method, path))
    return found


# --- R25: la marca ------------------------------------------------------------------------


def test_existing_and_invited_users_have_the_flag_off(client, cp_db):
    rows = filas(cp_db, "select debe_cambiar_password from usuario")
    assert rows and all(row["debe_cambiar_password"] is False for row in rows)
    response = _login(client, ADMIN_A.email, PASSWORD)
    assert response.status_code == 200
    assert response.get_json()["debe_cambiar_password"] is False
    me = client.get("/auth/me", headers=_bearer(response))
    assert me.get_json()["debe_cambiar_password"] is False

    creada = client.post(
        "/invitaciones",
        json={"email": f"inv.{uuid.uuid4().hex[:8]}@ejemplo.test", "rol": "contador"},
        headers=_bearer(response),
    )
    token = creada.get_json()["enlace"].split("#", 1)[1]
    aceptada = client.post(
        "/invitaciones/aceptar", json={"token": token, "nombre": "Invitada", "password": NUEVA}
    )
    assert aceptada.status_code == 201
    assert aceptada.get_json()["debe_cambiar_password"] is False
    assert _marca(cp_db, uuid.UUID(aceptada.get_json()["usuario"]["id"])) is False


def test_the_first_admin_of_a_console_company_must_change_it(client, cp_db, dev_headers):
    email = f"primer.{uuid.uuid4().hex[:10]}@ejemplo.test"
    alta = client.post(
        "/plataforma/empresas",
        json={
            "id": str(uuid.uuid4()),
            "nombre": f"Clínica Cambio {uuid.uuid4().hex[:6]}",
            "direccion": "Calle 1 # 2-3, Cartago",
            "admin": {
                "nombre": "Primer Admin",
                "email": email,
                "password": INICIAL,
                "password_confirmacion": INICIAL,
            },
        },
        headers=dev_headers,
    )
    assert alta.status_code == 201, alta.get_json()
    usuario = uuid.UUID(alta.get_json()["admin_id"])
    assert _marca(cp_db, usuario) is True

    entrada = _login(client, email)
    assert entrada.status_code == 200
    assert entrada.get_json()["debe_cambiar_password"] is True
    viejo = _bearer(entrada)
    assert client.get("/auth/me", headers=viejo).get_json()["debe_cambiar_password"] is True
    bloqueada = client.get("/ubicaciones", headers=viejo)
    assert bloqueada.status_code == 403
    assert error_code(bloqueada) == BLOQUEO

    # El cambio ocurre en un segundo posterior al iat del token de la contraseña inicial.
    time.sleep(1.05)
    cambio = _cambiar(client, viejo)
    assert cambio.status_code == 200, cambio.get_json()
    cuerpo = cambio.get_json()
    assert cuerpo["debe_cambiar_password"] is False
    assert cuerpo["rol"] == "admin"
    assert _marca(cp_db, usuario) is False
    assert client.get("/ubicaciones", headers=_bearer(cambio)).status_code == 200
    # M1 (0026): el JWT emitido con la contraseña inicial no recupera los permisos al
    # quitarse la marca; queda cortado (mismo 401 genérico), también para crear invitaciones.
    for respuesta in (
        client.get("/ubicaciones", headers=viejo),
        client.get("/auth/me", headers=viejo),
        client.post(
            "/invitaciones",
            json={"email": f"inv.{uuid.uuid4().hex[:8]}@ejemplo.test", "rol": "admin"},
            headers=viejo,
        ),
    ):
        assert respuesta.status_code == 401
        assert error_code(respuesta) == "no_autenticado"
    # La contraseña inicial ya no entra; la nueva sí.
    assert _login(client, email).status_code == 401
    assert _login(client, email, NUEVA).status_code == 200


# --- R26 / A16: bloqueo central -----------------------------------------------------------


def test_the_whitelist_is_closed():
    assert PASSWORD_CHANGE_ENDPOINTS == frozenset({"auth.me", "auth.cambiar_contrasena"})


@pytest.mark.parametrize("rol", ["admin", "contador"])
def test_a_flagged_user_gets_403_on_every_tenant_endpoint_except_the_whitelist(
    client, cp_app, cp_db, rol
):
    usuario, email = _cuenta(cp_db, rol=rol)
    entrada = _login(client, email)
    assert entrada.status_code == 200
    headers = _bearer(entrada)

    routes = _tenant_routes(cp_app)
    assert len(routes) > 30
    endpoints = {endpoint for endpoint, _, _ in routes}
    assert PASSWORD_CHANGE_ENDPOINTS <= endpoints
    for endpoint, method, path in routes:
        if endpoint in PASSWORD_CHANGE_ENDPOINTS:
            continue
        response = client.open(path, method=method, json={}, headers=headers)
        assert response.status_code == 403, (rol, endpoint, method)
        assert response.get_json()["error"] == {
            "code": BLOQUEO,
            "message": "Debes cambiar tu contraseña antes de continuar.",
            "request_id": response.get_json()["error"]["request_id"],
        }, (rol, endpoint, method)

    # La lista blanca: /auth/me responde; login, refresh y logout siguen sirviendo.
    assert client.get("/auth/me", headers=headers).status_code == 200
    renovada = _refresh(client, _cookie(entrada))
    assert renovada.status_code == 200
    assert renovada.get_json()["debe_cambiar_password"] is True
    salida = client.post(
        "/auth/logout",
        headers={**CSRF, "Cookie": f"{REFRESH_COOKIE_SECURE_NAME}={_cookie(renovada)}"},
    )
    assert salida.status_code == 204
    assert _marca(cp_db, usuario) is True


def test_the_flag_is_read_from_the_database_on_every_request(client, cp_db):
    usuario, email = _cuenta(cp_db, marca=False)
    headers = _bearer(_login(client, email))
    assert client.get("/ubicaciones", headers=headers).status_code == 200
    with cp_db.migrator.begin() as conn:
        conn.execute(
            text("update usuario set debe_cambiar_password = true where id = :u"), {"u": usuario}
        )
    # Mismo JWT: la marca no viaja en el token.
    assert client.get("/ubicaciones", headers=headers).status_code == 403
    with cp_db.migrator.begin() as conn:
        conn.execute(
            text("update usuario set debe_cambiar_password = false where id = :u"), {"u": usuario}
        )
    assert client.get("/ubicaciones", headers=headers).status_code == 200


def test_the_flag_goes_before_the_role(client, cp_db):
    _, email = _cuenta(cp_db, rol="contador")
    headers = _bearer(_login(client, email))
    # /invitaciones es solo de admin: sin la marca daría 403 prohibido.
    response = client.post(
        "/invitaciones", json={"email": "x@ejemplo.test", "rol": "contador"}, headers=headers
    )
    assert response.status_code == 403
    assert error_code(response) == BLOQUEO


# --- R27: el endpoint ---------------------------------------------------------------------


def test_a_wrong_current_password_is_401_and_changes_nothing(client, cp_db):
    usuario, email = _cuenta(cp_db)
    headers = _bearer(_login(client, email))
    antes = _password_hash(cp_db, usuario)
    response = _cambiar(client, headers, actual="Otra-Clave-Incorrecta-2026")
    assert response.status_code == 401
    assert error_code(response) == "credenciales_invalidas"
    assert "Set-Cookie" not in response.headers
    assert _password_hash(cp_db, usuario) == antes
    assert _marca(cp_db, usuario) is True


@pytest.mark.parametrize(
    ("cambios", "codigo"),
    [
        ({"nueva": INICIAL}, "contrasena_repetida"),
        ({"confirmacion": "Otra-Clave-Distinta-2026"}, "contrasenas_distintas"),
        ({"nueva": "corta"}, "contrasena_corta"),
        ({"nueva": "x" * 129}, "contrasena_larga"),
        ({"nueva": "bienvenido123"}, "contrasena_comun"),
    ],
)
def test_invalid_new_passwords_are_422_and_change_nothing(client, cp_db, cambios, codigo):
    usuario, email = _cuenta(cp_db)
    headers = _bearer(_login(client, email))
    antes = _password_hash(cp_db, usuario)
    nueva = cambios.get("nueva", NUEVA)
    response = _cambiar(client, headers, nueva=nueva, confirmacion=cambios.get("confirmacion"))
    assert response.status_code == 422
    assert error_code(response) == codigo
    assert _password_hash(cp_db, usuario) == antes
    assert _marca(cp_db, usuario) is True


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {},
        {"actual": INICIAL, "nueva": NUEVA},
        {"actual": INICIAL, "nueva": NUEVA, "confirmacion": 1},
        {"actual": None, "nueva": NUEVA, "confirmacion": NUEVA},
    ],
)
def test_malformed_bodies_are_400(client, cp_db, body):
    _, email = _cuenta(cp_db)
    headers = _bearer(_login(client, email))
    response = client.post(RUTA, json=body, headers=headers)
    assert response.status_code == 400
    assert error_code(response) == "solicitud_invalida"


def test_it_requires_a_session(client):
    response = client.post(RUTA, json={"actual": INICIAL, "nueva": NUEVA, "confirmacion": NUEVA})
    assert response.status_code == 401
    assert error_code(response) == "no_autenticado"


def test_changing_revokes_the_other_refresh_families(client, cp_db):
    usuario, email = _cuenta(cp_db)
    primera = _login(client, email)
    segunda = _login(client, email)
    cambio = _cambiar(client, _bearer(primera))
    assert cambio.status_code == 200
    for viejo in (primera, segunda):
        response = _refresh(client, _cookie(viejo))
        assert response.status_code == 401
        assert "Set-Cookie" not in response.headers
    nueva = _refresh(client, _cookie(cambio))
    assert nueva.status_code == 200
    assert nueva.get_json()["debe_cambiar_password"] is False
    vivas = filas(
        cp_db,
        "select count(distinct t.familia_id) as n from refresh_token t "
        "join membresia m on m.id = t.membresia_id "
        "where m.usuario_id = :u and t.revocado_en is null",
        {"u": usuario},
    )
    assert vivas == [{"n": 1}]


def test_a_voluntary_change_works_without_the_flag(client, cp_db):
    usuario, email = _cuenta(cp_db, rol="contador", marca=False)
    cambio = _cambiar(client, _bearer(_login(client, email)))
    assert cambio.status_code == 200
    assert cambio.get_json()["debe_cambiar_password"] is False
    assert _marca(cp_db, usuario) is False
    assert _login(client, email).status_code == 401
    assert _login(client, email, NUEVA).status_code == 200


def test_the_response_never_carries_a_password_or_hash(client, cp_db):
    usuario, email = _cuenta(cp_db)
    response = _cambiar(client, _bearer(_login(client, email)))
    raw = response.get_data(as_text=True)
    for secreto in (INICIAL, NUEVA, _password_hash(cp_db, usuario), "$argon2"):
        assert secreto not in raw
    assert set(response.get_json()) == {
        "access_token",
        "token_type",
        "expires_in",
        "usuario",
        "tenant",
        "rol",
        "debe_cambiar_password",
    }
    assert response.headers["Cache-Control"] == "no-store"


def test_the_login_limit_applies_before_argon2(cp_db, monkeypatch):
    flask_app = make_plat_app(cp_db, rate_limits=RateLimits(login_account=3, login_ip=1000))
    try:
        client = flask_app.test_client(use_cookies=False)
        usuario, email = _cuenta(cp_db)
        headers = _bearer(_login(client, email))  # 1 (devuelto: entró)
        for _ in range(3):
            assert _cambiar(client, headers, actual="Otra-Clave-Mala-2026").status_code == 401
        llamadas = []
        real = auth_service.get_passwords

        def contar():
            llamadas.append(1)
            return real()

        monkeypatch.setattr(auth_service, "get_passwords", contar)
        limitada = _cambiar(client, headers)
        assert limitada.status_code == 429
        assert error_code(limitada) == "demasiadas_solicitudes"
        assert llamadas == []
        assert _marca(cp_db, usuario) is True
    finally:
        dispose(flask_app)


def test_a_success_gives_back_its_attempt(cp_db):
    flask_app = make_plat_app(cp_db, rate_limits=RateLimits(login_account=2, login_ip=1000))
    try:
        client = flask_app.test_client(use_cookies=False)
        _, email = _cuenta(cp_db)
        headers = _bearer(_login(client, email))
        assert _cambiar(client, headers).status_code == 200
        # Login y cambio devolvieron su intento: quedan los dos del umbral.
        assert _login(client, email, "Otra-Clave-Mala-2026").status_code == 401
        assert _login(client, email, NUEVA).status_code == 200
    finally:
        dispose(flask_app)


# --- La función SQL -----------------------------------------------------------------------


@pytest.fixture(scope="module")
def app_engine(cp_db):
    engine = create_engine(cp_db.app_url, poolclass=NullPool)
    yield engine
    engine.dispose()


CAMBIAR = "select acceso.cambiar_password_propio(:u, :t, :a, :n)"


def _sqlstate_message(exc: DBAPIError) -> tuple[str, str]:
    return exc.orig.sqlstate, exc.orig.diag.message_primary


def test_the_function_rejects_another_tenant_or_a_stale_hash(app_engine, cp_db):
    usuario, _ = _cuenta(cp_db)
    actual = _password_hash(cp_db, usuario)
    nuevo = _hash(NUEVA)
    for tenant, hash_actual in ((TENANT_B, actual), (TENANT_A, _hash(INICIAL))):
        with pytest.raises(DBAPIError) as raised, app_engine.begin() as conn:
            conn.execute(text(CAMBIAR), {"u": usuario, "t": tenant, "a": hash_actual, "n": nuevo})
        assert _sqlstate_message(raised.value) == ("P0001", "cambio_invalido")
    assert _password_hash(cp_db, usuario) == actual
    assert _marca(cp_db, usuario) is True


def test_the_function_rejects_an_inactive_user_and_a_bad_hash(app_engine, cp_db):
    usuario, _ = _cuenta(cp_db)
    actual = _password_hash(cp_db, usuario)
    with pytest.raises(DBAPIError) as raised, app_engine.begin() as conn:
        conn.execute(text(CAMBIAR), {"u": usuario, "t": TENANT_A, "a": actual, "n": "texto"})
    assert _sqlstate_message(raised.value) == ("22023", "hash_invalido")

    with cp_db.migrator.begin() as conn:
        conn.execute(text("update usuario set activo = false where id = :u"), {"u": usuario})
    with pytest.raises(DBAPIError) as raised, app_engine.begin() as conn:
        conn.execute(text(CAMBIAR), {"u": usuario, "t": TENANT_A, "a": actual, "n": _hash(NUEVA)})
    assert _sqlstate_message(raised.value) == ("P0001", "cambio_invalido")
    assert _password_hash(cp_db, usuario) == actual


def test_the_function_does_not_touch_other_users(app_engine, cp_db):
    usuario, _ = _cuenta(cp_db)
    otro, _ = _cuenta(cp_db)
    antes = filas(
        cp_db,
        "select id, password_hash, debe_cambiar_password from usuario where id <> :u order by id",
        {"u": usuario},
    )
    with app_engine.begin() as conn:
        resultado = conn.scalar(
            text(CAMBIAR),
            {"u": usuario, "t": TENANT_A, "a": _password_hash(cp_db, usuario), "n": _hash(NUEVA)},
        )
    assert resultado is True
    assert _marca(cp_db, usuario) is False
    assert _marca(cp_db, otro) is True
    despues = filas(
        cp_db,
        "select id, password_hash, debe_cambiar_password from usuario where id <> :u order by id",
        {"u": usuario},
    )
    assert despues == antes


def test_the_app_can_read_the_flag_but_never_write_it(app_engine, cp_db):
    with app_engine.connect() as conn:
        privilegios = {
            privilegio: conn.scalar(
                text(
                    "select has_column_privilege(current_user, 'public.usuario', "
                    "'debe_cambiar_password', :p)"
                ),
                {"p": privilegio},
            )
            for privilegio in ("SELECT", "INSERT", "UPDATE")
        }
    assert privilegios == {"SELECT": True, "INSERT": False, "UPDATE": False}


# --- R28: la recuperación de la 014 deja la marca en false ---------------------------------


def test_recovery_clears_the_flag(app_engine, cp_db):
    usuario, email = _cuenta(cp_db)
    clave = hashlib.sha256(uuid.uuid4().hex.encode()).hexdigest()
    with app_engine.begin() as conn:
        assert conn.scalar(
            text("select acceso.solicitar_recuperacion(:e, :c)"), {"e": email, "c": clave}
        )
    with app_engine.begin() as conn:
        restablecido = conn.scalar(
            text("select acceso.restablecer_contrasena(:c, :h)"), {"c": clave, "h": _hash(NUEVA)}
        )
    assert restablecido == usuario
    assert _marca(cp_db, usuario) is False


# --- A12: nada sensible en los logs -------------------------------------------------------


def test_no_log_has_passwords_hashes_or_tokens(client, cp_db, caplog):
    caplog.set_level(logging.DEBUG)
    usuario, email = _cuenta(cp_db)
    entrada = _login(client, email)
    headers = _bearer(entrada)
    _cambiar(client, headers, actual="Otra-Clave-Incorrecta-2026")
    _cambiar(client, headers, nueva=INICIAL)
    _cambiar(client, headers, confirmacion="Otra-Confirmacion-2026")
    cambio = _cambiar(client, headers)
    assert cambio.status_code == 200
    secretos = (
        INICIAL,
        NUEVA,
        "Otra-Clave-Incorrecta-2026",
        "Otra-Confirmacion-2026",
        _password_hash(cp_db, usuario),
        "$argon2",
        entrada.get_json()["access_token"],
        cambio.get_json()["access_token"],
        _cookie(cambio).split(".", 1)[1],
        email,
    )
    texto = "\n".join(record.getMessage() for record in caplog.records)
    for secreto in secretos:
        assert secreto not in texto


def test_a_token_for_a_flagged_user_of_another_tenant_is_401(client, cp_db):
    usuario, _ = _cuenta(cp_db)
    token = encode_access_token(SECRET_KEY, sub=usuario, tenant=TENANT_B, rol="admin")
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert (
        client.get("/auth/me", headers=_bearer(_login(client, ADMIN_B.email, PASSWORD))).get_json()[
            "debe_cambiar_password"
        ]
        is False
    )


# --- M1 (0026): corte de los JWT de acceso al cambiar o restablecer ------------------------


def _token(usuario: uuid.UUID, issued: datetime, tenant: uuid.UUID = TENANT_A) -> dict[str, str]:
    token = encode_access_token(SECRET_KEY, sub=usuario, tenant=tenant, rol="admin", now=issued)
    return {"Authorization": f"Bearer {token}"}


def _corte(db: AccesoDb, usuario: uuid.UUID) -> datetime | None:
    (row,) = filas(db, "select sesiones_validas_desde from usuario where id = :u", {"u": usuario})
    return row["sesiones_validas_desde"]


def _familias_vivas(db: AccesoDb, usuario: uuid.UUID) -> list[uuid.UUID]:
    return [
        row["familia_id"]
        for row in filas(
            db,
            "select distinct t.familia_id from refresh_token t "
            "join membresia m on m.id = t.membresia_id "
            "where m.usuario_id = :u and t.revocado_en is null order by t.familia_id",
            {"u": usuario},
        )
    ]


def test_a_token_issued_before_the_change_is_401_and_the_new_session_works(client, cp_db):
    usuario, email = _cuenta(cp_db)
    assert _corte(cp_db, usuario) is None  # sin corte hasta el primer cambio
    anterior = _token(usuario, datetime.now(UTC) - timedelta(seconds=5))
    cambio = _cambiar(client, _bearer(_login(client, email)))
    assert cambio.status_code == 200
    assert _corte(cp_db, usuario) is not None

    response = client.get("/auth/me", headers=anterior)
    assert response.status_code == 401
    assert error_code(response) == "no_autenticado"
    # La sesión nueva que respondió el cambio, su refresh y un login nuevo siguen sirviendo.
    assert client.get("/ubicaciones", headers=_bearer(cambio)).status_code == 200
    renovada = _refresh(client, _cookie(cambio))
    assert renovada.status_code == 200
    assert client.get("/ubicaciones", headers=_bearer(renovada)).status_code == 200
    nueva = _login(client, email, NUEVA)
    assert client.get("/ubicaciones", headers=_bearer(nueva)).status_code == 200


def test_the_cut_compares_whole_seconds(client, cp_db):
    # iat es entero y el corte tiene microsegundos: vale todo token del segundo del corte.
    usuario, email = _cuenta(cp_db, marca=False)
    assert _cambiar(client, _bearer(_login(client, email))).status_code == 200
    segundo = _corte(cp_db, usuario).replace(microsecond=0)
    for issued in (segundo, segundo + timedelta(seconds=1)):
        assert client.get("/ubicaciones", headers=_token(usuario, issued)).status_code == 200
    antes = client.get("/ubicaciones", headers=_token(usuario, segundo - timedelta(seconds=1)))
    assert antes.status_code == 401
    assert error_code(antes) == "no_autenticado"


# M-1/M-3: el reloj de Flask va ATRASADO respecto al de la base (el corte es now() de
# PostgreSQL). Sin el max(ahora, floor(corte)) de access_issued_at, todo acceso emitido en
# esos segundos tendría iat < corte y load_current_user lo rechazaría (login 200 y 401 en la
# primera llamada). El atraso queda dentro de la holgura de iat futuro (O-2, 60 s).
ATRASO_FLASK = timedelta(seconds=30)


class _RelojFlaskAtrasado(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime.now(tz) - ATRASO_FLASK


def _atrasar_flask(monkeypatch) -> None:
    monkeypatch.setattr(auth_service, "datetime", _RelojFlaskAtrasado)


def _iat(response) -> int:
    token = response.get_json()["access_token"]
    return jwt.decode(token, options={"verify_signature": False})["iat"]


def _segundo_corte(db: AccesoDb, usuario: uuid.UUID) -> int:
    return int(_corte(db, usuario).replace(microsecond=0).timestamp())


def _funciona(client, response) -> bool:
    return client.get("/ubicaciones", headers=_bearer(response)).status_code == 200


def test_the_new_session_token_is_never_before_the_cut(client, cp_db, monkeypatch):
    # Aunque el reloj de Flask vaya detrás del de la base, la sesión nueva sale con un iat no
    # anterior al corte: el cambio no cierra la sesión que acaba de crear.
    usuario, email = _cuenta(cp_db)
    headers = _bearer(_login(client, email))
    _atrasar_flask(monkeypatch)
    cambio = _cambiar(client, headers)
    assert cambio.status_code == 200
    assert _iat(cambio) >= _segundo_corte(cp_db, usuario)
    assert _funciona(client, cambio)


def test_a_login_right_after_the_change_works_with_flask_behind(client, cp_db, monkeypatch):
    usuario, email = _cuenta(cp_db)
    assert _cambiar(client, _bearer(_login(client, email))).status_code == 200
    _atrasar_flask(monkeypatch)
    entrada = _login(client, email, NUEVA)
    assert entrada.status_code == 200
    assert _iat(entrada) >= _segundo_corte(cp_db, usuario)
    assert _funciona(client, entrada)


def test_a_refresh_right_after_the_change_works_with_flask_behind(client, cp_db, monkeypatch):
    usuario, email = _cuenta(cp_db)
    cambio = _cambiar(client, _bearer(_login(client, email)))
    assert cambio.status_code == 200
    _atrasar_flask(monkeypatch)
    renovada = _refresh(client, _cookie(cambio))
    assert renovada.status_code == 200
    assert _iat(renovada) >= _segundo_corte(cp_db, usuario)
    assert _funciona(client, renovada)


def test_a_login_right_after_recovery_works_with_flask_behind(
    client, app_engine, cp_db, monkeypatch
):
    usuario, email = _cuenta(cp_db, marca=False)
    clave = hashlib.sha256(uuid.uuid4().hex.encode()).hexdigest()
    with app_engine.begin() as conn:
        assert conn.scalar(
            text("select acceso.solicitar_recuperacion(:e, :c)"), {"e": email, "c": clave}
        )
    with app_engine.begin() as conn:
        restablecido = conn.scalar(
            text("select acceso.restablecer_contrasena(:c, :h)"), {"c": clave, "h": _hash(NUEVA)}
        )
    assert restablecido == usuario
    _atrasar_flask(monkeypatch)
    entrada = _login(client, email, NUEVA)
    assert entrada.status_code == 200
    assert _iat(entrada) >= _segundo_corte(cp_db, usuario)
    assert _funciona(client, entrada)


def test_without_a_cut_the_token_uses_the_flask_clock(client, cp_db, monkeypatch):
    # Sin corte (nunca cambió la contraseña) no hay max(): el iat es el reloj de Flask.
    usuario, email = _cuenta(cp_db, marca=False)
    assert _corte(cp_db, usuario) is None
    _atrasar_flask(monkeypatch)
    entrada = _login(client, email)
    assert entrada.status_code == 200
    atrasado = int((datetime.now(UTC) - ATRASO_FLASK).timestamp())
    assert abs(_iat(entrada) - atrasado) <= 2
    assert _funciona(client, entrada)


@pytest.mark.parametrize("segundos", [120, float("inf")], ids=["mas-120s", "infinito"])
def test_an_access_token_with_a_far_future_or_infinite_iat_is_401(client, cp_db, segundos):
    # O-2: el decodificador rechaza a mano un iat > ahora + 60 s o no finito (mismo 401).
    usuario, _ = _cuenta(cp_db, marca=False)
    ahora = datetime.now(UTC)
    claims = {
        "sub": str(usuario),
        "tenant": str(TENANT_A),
        "iss": JWT_ISSUER,
        "iat": ahora.timestamp() + segundos,
        "exp": int((ahora + timedelta(minutes=5)).timestamp()),
    }
    token = jwt.encode(claims, derive_key(SECRET_KEY, JWT_KEY_CONTEXT), algorithm="HS256")
    response = client.get("/ubicaciones", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert error_code(response) == "no_autenticado"


def test_recovery_by_email_cuts_the_tokens_issued_before(client, app_engine, cp_db):
    usuario, email = _cuenta(cp_db, marca=False)
    anterior = _token(usuario, datetime.now(UTC) - timedelta(seconds=5))
    assert client.get("/ubicaciones", headers=anterior).status_code == 200
    clave = hashlib.sha256(uuid.uuid4().hex.encode()).hexdigest()
    with app_engine.begin() as conn:
        assert conn.scalar(
            text("select acceso.solicitar_recuperacion(:e, :c)"), {"e": email, "c": clave}
        )
    with app_engine.begin() as conn:
        restablecido = conn.scalar(
            text("select acceso.restablecer_contrasena(:c, :h)"), {"c": clave, "h": _hash(NUEVA)}
        )
    assert restablecido == usuario
    assert _corte(cp_db, usuario) is not None
    response = client.get("/ubicaciones", headers=anterior)
    assert response.status_code == 401
    assert error_code(response) == "no_autenticado"
    nueva = _login(client, email, NUEVA)
    assert nueva.status_code == 200
    assert client.get("/ubicaciones", headers=_bearer(nueva)).status_code == 200


def test_the_cut_only_affects_that_user(client, cp_db):
    _, email = _cuenta(cp_db, marca=False)
    otro, _ = _cuenta(cp_db, marca=False)
    anterior_otro = _token(otro, datetime.now(UTC) - timedelta(seconds=5))
    assert _cambiar(client, _bearer(_login(client, email))).status_code == 200
    assert _corte(cp_db, otro) is None
    assert client.get("/ubicaciones", headers=anterior_otro).status_code == 200


def test_the_cut_does_not_affect_a_user_of_another_tenant(client, cp_db):
    _, email = _cuenta(cp_db, marca=False)
    ajeno, ajeno_email = _cuenta(cp_db, tenant=TENANT_B, marca=False)
    anterior_ajeno = _token(ajeno, datetime.now(UTC) - timedelta(seconds=5), tenant=TENANT_B)
    sesion_ajena = _login(client, ajeno_email)
    assert _cambiar(client, _bearer(_login(client, email))).status_code == 200
    assert _corte(cp_db, ajeno) is None
    assert client.get("/ubicaciones", headers=anterior_ajeno).status_code == 200
    assert _funciona(client, sesion_ajena)
    assert _refresh(client, _cookie(sesion_ajena)).status_code == 200


def test_the_app_can_read_the_cut_but_never_write_it(app_engine):
    consulta = text(
        "select has_column_privilege(cast(:rol as text), 'public.usuario', "
        "'sesiones_validas_desde', :p)"
    )
    with app_engine.connect() as conn:
        app_role = conn.scalar(text("select current_user"))
        privilegios = {
            (rol, p): conn.scalar(consulta, {"rol": nombre, "p": p})
            for rol, nombre in (("app", app_role), ("dueno", "auth_owner"))
            for p in ("SELECT", "INSERT", "UPDATE")
        }
    assert privilegios == {
        ("app", "SELECT"): True,
        ("app", "INSERT"): False,
        ("app", "UPDATE"): False,
        ("dueno", "SELECT"): False,
        ("dueno", "INSERT"): False,
        ("dueno", "UPDATE"): True,
    }


def test_a_rejected_change_does_not_set_the_cut(app_engine, cp_db):
    usuario, _ = _cuenta(cp_db)
    with pytest.raises(DBAPIError), app_engine.begin() as conn:
        conn.execute(
            text(CAMBIAR), {"u": usuario, "t": TENANT_A, "a": _hash(INICIAL), "n": _hash(NUEVA)}
        )
    assert _corte(cp_db, usuario) is None


# --- Pruebas pendientes del security-reviewer de T4 ---------------------------------------


class _FalloProvocado(Exception):
    pass


def test_a_failure_after_the_function_rolls_everything_back(client, cp_db, monkeypatch):
    # (1) Atomicidad: si falla la familia nueva, ni el hash, ni la marca, ni el corte, ni la
    # revocación de las familias previas quedan escritos.
    usuario, email = _cuenta(cp_db)
    entrada = _login(client, email)
    otra = _login(client, email)
    hash_antes = _password_hash(cp_db, usuario)
    familias_antes = _familias_vivas(cp_db, usuario)
    assert len(familias_antes) == 2

    def falla():
        raise _FalloProvocado

    monkeypatch.setattr(auth_service, "new_token", falla)
    try:
        response = _cambiar(client, _bearer(entrada))
    except _FalloProvocado:
        response = None
    monkeypatch.undo()
    assert response is None or response.status_code == 500

    assert _password_hash(cp_db, usuario) == hash_antes
    assert _marca(cp_db, usuario) is True
    assert _corte(cp_db, usuario) is None
    assert _familias_vivas(cp_db, usuario) == familias_antes
    assert _refresh(client, _cookie(otra)).status_code == 200
    assert _login(client, email).status_code == 200


def test_two_concurrent_changes_only_one_wins(cp_app, cp_db):
    # (2) Concurrencia real: misma actual, nuevas distintas; exactamente uno 200 y el otro 401.
    usuario, email = _cuenta(cp_db)
    headers = _bearer(_login(cp_app.test_client(use_cookies=False), email))
    nuevas = ("Clave-Hilo-Uno-Sintetica-2026", "Clave-Hilo-Dos-Sintetica-2026")
    barrera = threading.Barrier(len(nuevas))
    resultados: dict[str, int] = {}

    def cambiar(nueva: str) -> None:
        cliente = cp_app.test_client(use_cookies=False)
        barrera.wait()
        resultados[nueva] = _cambiar(cliente, headers, nueva=nueva).status_code

    hilos = [threading.Thread(target=cambiar, args=(nueva,)) for nueva in nuevas]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join(timeout=60)
    assert sorted(resultados.values()) == [200, 401]
    (ganadora,) = [nueva for nueva, status in resultados.items() if status == 200]
    (perdedora,) = [nueva for nueva in nuevas if nueva != ganadora]
    final = _password_hash(cp_db, usuario)
    hasher = argon2.PasswordHasher.from_parameters(ARGON2_TEST_PARAMS)
    assert hasher.verify(final, ganadora)
    with pytest.raises(argon2.exceptions.VerifyMismatchError):
        hasher.verify(final, perdedora)
    assert _marca(cp_db, usuario) is False
    assert len(_familias_vivas(cp_db, usuario)) == 1


def _espera_un_candado(db: AccesoDb, pid: int) -> bool:
    (row,) = filas(
        db, "select exists(select 1 from pg_locks where pid = :p and not granted) as e", {"p": pid}
    )
    return row["e"]


def test_two_overlapping_changes_the_second_waits_and_loses(app_engine, cp_db):
    # (2, M-2) Solape garantizado: la primera transacción cambia la fila y no confirma; la
    # segunda queda esperando el candado de esa fila (se comprueba en pg_locks); al confirmar
    # la primera, la segunda reevalúa el WHERE (hash actual distinto) y da cambio_invalido.
    usuario, _ = _cuenta(cp_db)
    actual = _password_hash(cp_db, usuario)
    hash_uno = _hash("Clave-Primera-Sintetica-2026")
    hash_dos = _hash("Clave-Segunda-Sintetica-2026")
    params = {"u": usuario, "t": TENANT_A, "a": actual}
    resultado: dict[str, object] = {}

    with app_engine.connect() as segunda:
        pid = segunda.scalar(text("select pg_backend_pid()"))
        segunda.commit()

        def cambiar_segunda() -> None:
            try:
                with segunda.begin():
                    segunda.execute(text("set local lock_timeout = '30s'"))
                    resultado["ok"] = segunda.scalar(text(CAMBIAR), {**params, "n": hash_dos})
            except DBAPIError as exc:
                resultado["error"] = _sqlstate_message(exc)

        with app_engine.connect() as primera:
            primera.begin()
            assert primera.scalar(text(CAMBIAR), {**params, "n": hash_uno}) is True
            hilo = threading.Thread(target=cambiar_segunda)
            hilo.start()
            limite = time.monotonic() + 20
            while not _espera_un_candado(cp_db, pid):
                assert hilo.is_alive() and time.monotonic() < limite, resultado
                time.sleep(0.05)
            assert hilo.is_alive()  # sigue bloqueada mientras la primera no confirme
            primera.commit()
        hilo.join(timeout=30)
        assert not hilo.is_alive()

    assert resultado == {"error": ("P0001", "cambio_invalido")}
    assert _password_hash(cp_db, usuario) == hash_uno
    assert _marca(cp_db, usuario) is False


def test_the_body_cannot_choose_another_account(client, cp_db):
    # (3) IDOR: usuario, tenant o email en el cuerpo se ignoran; solo cambia la del token.
    usuario, email = _cuenta(cp_db)
    otro, otro_email = _cuenta(cp_db)
    ajeno, ajeno_email = _cuenta(cp_db, tenant=TENANT_B)
    antes = {cuenta: _password_hash(cp_db, cuenta) for cuenta in (otro, ajeno)}
    body = {
        "actual": INICIAL,
        "nueva": NUEVA,
        "confirmacion": NUEVA,
        "usuario": str(otro),
        "usuario_id": str(ajeno),
        "tenant": str(TENANT_B),
        "tenant_id": str(TENANT_B),
        "email": otro_email,
    }
    response = client.post(RUTA, json=body, headers=_bearer(_login(client, email)))
    assert response.status_code == 200
    assert response.get_json()["usuario"]["id"] == str(usuario)
    assert response.get_json()["tenant"]["id"] == str(TENANT_A)
    assert {cuenta: _password_hash(cp_db, cuenta) for cuenta in (otro, ajeno)} == antes
    assert _marca(cp_db, otro) is True and _marca(cp_db, ajeno) is True
    assert _corte(cp_db, otro) is None and _corte(cp_db, ajeno) is None
    assert _login(client, email, NUEVA).status_code == 200
    assert _login(client, otro_email).status_code == 200
    assert _login(client, ajeno_email).status_code == 200


def _app_con_limites(db: AccesoDb, **cambios: int) -> Flask:
    base = {
        "login_account": 1000,
        "login_ip": 1000,
        "refresh_ip": 1000,
        "plat_login_account": 1000,
        "plat_login_ip": 1000,
        "plat_accion": 1000,
        "plat_refresh_ip": 1000,
    }
    return make_plat_app(db, rate_limits=RateLimits(**{**base, **cambios}))


def test_tenant_and_platform_login_limits_are_separate_scopes(cp_db):
    # (4) Agotar login_cuenta del tenant no consume plat_login_cuenta del mismo correo, y
    # viceversa.
    flask_app = _app_con_limites(cp_db, login_account=2, plat_login_account=2)
    try:
        client = flask_app.test_client(use_cookies=False)
        _, email = _cuenta(cp_db, marca=False)
        sembrar_dev(cp_db, Dev(uuid.uuid4(), email, "Dev Mismo Correo"))
        for _ in range(2):
            assert _login(client, email, "Otra-Clave-Mala-2026").status_code == 401
        assert _login(client, email).status_code == 429
        assert login(client, email).status_code == 200

        _, otro_email = _cuenta(cp_db, marca=False)
        sembrar_dev(cp_db, Dev(uuid.uuid4(), otro_email, "Dev Otro Correo"))
        for _ in range(2):
            assert login(client, otro_email, "Otra-Clave-Mala-2026").status_code == 401
        assert login(client, otro_email).status_code == 429
        assert _login(client, otro_email).status_code == 200
    finally:
        dispose(flask_app)


def test_tenant_and_platform_refresh_limits_are_separate_scopes(cp_db):
    # (4) Agotar refresh_ip no consume plat_refresh_ip, y viceversa.
    flask_app = _app_con_limites(cp_db, refresh_ip=2, plat_refresh_ip=2)
    try:
        client = flask_app.test_client(use_cookies=False)
        _, email = _cuenta(cp_db, marca=False)
        dev = sembrar_dev(cp_db, nuevo_dev("refresh"))
        tenant_cookie = _cookie(_login(client, email))
        plat_cookie = cookie_value(login(client, dev.email, DEV_PASSWORD))

        for _ in range(2):
            assert _refresh(client, f"{TENANT_A}.no-vale").status_code == 401
        assert _refresh(client, tenant_cookie).status_code == 429
        plat = refresh(client, plat_cookie)
        assert plat.status_code == 200

        with cp_db.migrator.begin() as conn:
            conn.execute(text("delete from limite_tasa"))
        tenant_cookie = _cookie(_login(client, email))
        for _ in range(2):
            assert refresh(client, "no-vale").status_code == 401
        assert refresh(client, cookie_value(plat)).status_code == 429
        assert _refresh(client, tenant_cookie).status_code == 200
    finally:
        dispose(flask_app)


def test_a_flagged_account_with_two_memberships_cannot_change_and_stays_consistent(client, cp_db):
    # (5) Con la marca y dos membresías activas el cambio da 401 sin tocar nada; con una
    # sola membresía entra y cambia normalmente.
    usuario, email = _cuenta(cp_db)
    with cp_db.migrator.begin() as conn:
        conn.execute(
            text("insert into membresia (tenant_id, usuario_id, rol) values (:t, :u, 'contador')"),
            {"t": TENANT_B, "u": usuario},
        )
    assert _login(client, email).status_code == 401  # Q6: varias membresías, falla cerrado
    headers = _token(usuario, datetime.now(UTC))
    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.get_json()["debe_cambiar_password"] is True
    hash_antes = _password_hash(cp_db, usuario)

    response = _cambiar(client, headers)
    assert response.status_code == 401
    assert error_code(response) == "credenciales_invalidas"
    assert "Set-Cookie" not in response.headers
    assert _password_hash(cp_db, usuario) == hash_antes
    assert _marca(cp_db, usuario) is True
    assert _corte(cp_db, usuario) is None
    # Sigue bloqueada por la marca, no a medias: el resto da 403 y /auth/me, 200.
    assert error_code(client.get("/ubicaciones", headers=headers)) == BLOQUEO
    assert client.get("/auth/me", headers=headers).status_code == 200

    with cp_db.migrator.begin() as conn:
        conn.execute(
            text("update membresia set activa = false where usuario_id = :u and tenant_id = :t"),
            {"u": usuario, "t": TENANT_B},
        )
    entrada = _login(client, email)
    assert entrada.status_code == 200
    assert _cambiar(client, _bearer(entrada)).status_code == 200
    assert _marca(cp_db, usuario) is False
