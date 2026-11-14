"""Validar y aceptar invitación (spec 002, T9; R11, R12, R14, Q4, Q6, Q9, Q13, Q16; A8, A9, A14,
A20, A22, A25; plan.md §2.2, §4).

Sobre una base temporal migrada a ``head`` con dos tenants sintéticos (A y B):

- ``POST /invitaciones/validar`` ``{token}`` (público): ``200 {"vigente": bool}``; vencida,
  usada, inexistente o con formato inválido dan exactamente la misma respuesta, y validar
  no consume.
- ``POST /invitaciones/aceptar`` ``{token, nombre, password}`` (público, **sin email**):
  ``acceso.aceptar_invitacion`` crea usuario y membresía con el email, el tenant y el rol de
  la invitación (nunca del cuerpo, la URL, las cabeceras, el JWT ni la cookie). Tras el
  ``COMMIT`` se emite la sesión (R11, A22): ``201`` con el mismo cuerpo que el login y la
  cookie de refresh. Si la emisión falla, ``500`` genérico y la cuenta ya existe (el login
  funciona).
- Vencida, usada, inexistente, formato inválido y email ya existente (en el mismo tenant o en
  otro, Q6/Q16) dan el mismo ``400 invitacion_invalida`` (cuerpo y cabeceras salvo el
  ``request_id``); la invitación con email duplicado queda sin consumir (A20).
- La política de contraseña (Q9) y la forma del cuerpo se validan antes de mirar el token:
  no dependen de él. Argon2 se calcula exactamente una vez en todo intento que llega a la
  base (mismo costo para todo motivo de rechazo, A20).
- Ningún log lleva token, clave, hashes, contraseña ni la sesión emitida (R14, A14).

Datos sintéticos (``@ejemplo.test``).
"""

import logging
import uuid
from collections.abc import Iterator
from http.cookies import SimpleCookie

import argon2
import pytest
from acceso_db import (
    ADMIN_A,
    ADMIN_B,
    CONTADOR_A,
    CONTADOR_B,
    PASSWORD,
    TENANT_A,
    TENANT_B,
    AccesoDb,
    bearer,
    dispose,
    make_app,
    migrator_execute,
    temporary_acceso_db,
)
from flask import Flask
from sqlalchemy import text

from app.auth import service as auth_service
from app.auth.credentials import (
    ARGON2_TEST_PARAMS,
    PASSWORD_MAX_LENGTH,
    new_token,
    token_key,
    token_storage_hash,
)
from app.auth.http import AUTH_MAX_BODY_BYTES, REFRESH_COOKIE_SECURE_NAME
from app.config import RateLimits
from app.invitaciones import service as inv_service

VALIDAR = "/invitaciones/validar"
ACEPTAR = "/invitaciones/aceptar"
LINK_PREFIX = "/invitacion#"
NOMBRE = "Invitada Sintética"
NUEVA = "Clave-Nueva-T9-segura"
INVALID = {
    "code": "invitacion_invalida",
    "message": "El enlace de invitación no es válido o ya no está vigente.",
}


@pytest.fixture(scope="module")
def acc_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("aceptar")


@pytest.fixture(scope="module")
def acc_app(acc_db) -> Iterator[Flask]:
    # T10: los casos de indistinguibilidad mandan más de 10 validar/aceptar seguidos desde
    # la misma IP; aquí no se prueba el límite (test_rate_limits.py), se sube su umbral.
    flask_app = make_app(acc_db, RateLimits(validate_ip=1000, accept_ip=1000))
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(acc_app):
    return acc_app.test_client(use_cookies=False)


@pytest.fixture(autouse=True)
def fresh_rate_limits(acc_db) -> Iterator[None]:
    """T10: cada prueba parte sin contadores de ``limite_tasa`` (los límites tienen sus
    propias pruebas en ``test_rate_limits.py``); la base del módulo es compartida."""
    with acc_db.migrator.begin() as conn:
        conn.execute(text("delete from limite_tasa"))
    yield


def nuevo_email() -> str:
    return f"invitado.{uuid.uuid4().hex[:10]}@ejemplo.test"


def invitar(client, *, email=None, rol="contador", cuenta=ADMIN_A, tenant=TENANT_A):
    """``(token, email)`` de una invitación nueva creada por la API (T8)."""
    email = email or nuevo_email()
    response = client.post(
        "/invitaciones", json={"email": email, "rol": rol}, headers=bearer(cuenta, tenant)
    )
    assert response.status_code == 201, response.get_json()
    return response.get_json()["enlace"].removeprefix(LINK_PREFIX), email


def aceptar(client, token, nombre=NOMBRE, password=NUEVA, extra=None, **kwargs):
    body = {"token": token, "nombre": nombre, "password": password, **(extra or {})}
    return client.post(ACEPTAR, json=body, **kwargs)


def validar(client, token, **kwargs):
    return client.post(VALIDAR, json={"token": token}, **kwargs)


def login(client, email, password=NUEVA):
    return client.post("/auth/login", json={"email": email, "password": password})


def inv_row(db: AccesoDb, token: str) -> dict:
    with db.migrator.connect() as conn:
        return dict(
            conn.execute(
                text("select * from invitacion where token_hash = :h"),
                {"h": token_storage_hash(token)},
            )
            .mappings()
            .one()
        )


def usuario_row(db: AccesoDb, email: str) -> dict | None:
    with db.migrator.connect() as conn:
        row = (
            conn.execute(text("select * from usuario where email = :e"), {"e": email})
            .mappings()
            .one_or_none()
        )
    return None if row is None else dict(row)


def membresias_de(db: AccesoDb, usuario_id: uuid.UUID) -> list[dict]:
    with db.migrator.connect() as conn:
        rows = conn.execute(
            text("select * from membresia where usuario_id = :u"), {"u": usuario_id}
        ).mappings()
        return [dict(r) for r in rows]


def membresias_del_tenant(db: AccesoDb, tenant: uuid.UUID) -> list[dict]:
    with db.migrator.connect() as conn:
        rows = conn.execute(
            text("select * from membresia where tenant_id = :t order by id"), {"t": tenant}
        ).mappings()
        return [dict(r) for r in rows]


def snapshot(db: AccesoDb) -> dict:
    """Todo lo que aceptar podría crear o consumir, en ambos tenants."""
    with db.migrator.connect() as conn:
        return {
            table: sorted(
                (tuple(map(str, r)) for r in conn.execute(text(f"select * from {table}"))),  # noqa: S608
            )
            for table in ("usuario", "membresia", "invitacion", "refresh_token")
        }


def expire(db: AccesoDb, token: str) -> None:
    migrator_execute(
        db,
        "update invitacion set expira_en = now() - interval '1 minute' where token_hash = :h",
        {"h": token_storage_hash(token)},
    )


def comparable(response) -> tuple:
    """Todo lo observable de una respuesta de error salvo el ``request_id``."""
    body = response.get_json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id"}
    headers = sorted(
        (k.lower(), v) for k, v in response.headers.items() if k.lower() != "x-request-id"
    )
    error = {k: v for k, v in body["error"].items() if k != "request_id"}
    return response.status_code, error, headers


def comparable_ok(response) -> tuple:
    headers = sorted(
        (k.lower(), v) for k, v in response.headers.items() if k.lower() != "x-request-id"
    )
    return response.status_code, response.get_json(), headers


def cookies_of(response) -> dict[str, tuple[str, str]]:
    result = {}
    for header in response.headers.getlist("Set-Cookie"):
        parsed = SimpleCookie()
        parsed.load(header)
        for name, morsel in parsed.items():
            result[name] = (morsel.value, header)
    return result


class HashSpy:
    """Cuenta los ``hash`` de Argon2 de ``Passwords`` (A20: mismo costo en todo motivo)."""

    def __init__(self, inner: argon2.PasswordHasher) -> None:
        self.inner = inner
        self.hashed = 0

    def hash(self, password, **kwargs):
        self.hashed += 1
        return self.inner.hash(password, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self.inner, name)


@pytest.fixture
def hash_spy(acc_app, monkeypatch) -> HashSpy:
    passwords = acc_app.extensions["assetcontrol.passwords"]
    spy = HashSpy(passwords._hasher)
    monkeypatch.setattr(passwords, "_hasher", spy)
    return spy


# --- Aceptar: camino correcto (R11, A8, A9) ------------------------------------------


@pytest.mark.parametrize("rol", ["contador", "admin"])
def test_accept_creates_user_and_membership_from_the_invitation(client, acc_db, rol):
    token, email = invitar(client, rol=rol)

    response = aceptar(client, token, nombre=f"  {NOMBRE}  ")

    assert response.status_code == 201, response.get_json()
    body = response.get_json()
    assert set(body) == {"access_token", "token_type", "expires_in", "usuario", "tenant", "rol"}
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 900
    assert body["usuario"]["email"] == email
    assert body["usuario"]["nombre"] == NOMBRE
    assert body["tenant"]["id"] == str(TENANT_A)
    assert body["rol"] == rol

    usuario = usuario_row(acc_db, email)
    assert usuario is not None
    assert str(usuario["id"]) == body["usuario"]["id"]
    assert usuario["nombre"] == NOMBRE
    assert usuario["activo"] is True
    assert usuario["password_hash"].startswith("$argon2id$")
    assert NUEVA not in usuario["password_hash"]
    assert argon2.extract_parameters(usuario["password_hash"]) == ARGON2_TEST_PARAMS
    (membresia,) = membresias_de(acc_db, usuario["id"])
    assert membresia["tenant_id"] == TENANT_A
    assert membresia["rol"] == rol
    assert membresia["activa"] is True
    assert inv_row(acc_db, token)["usada_en"] is not None


def test_accept_issues_the_session_after_the_commit(client, acc_db):
    """R11/A22: cookie de refresh como la del login y acceso utilizable."""
    token, email = invitar(client)

    response = aceptar(client, token)

    value, header = cookies_of(response)[REFRESH_COOKIE_SECURE_NAME]
    lowered = header.lower()
    assert "httponly" in lowered and "secure" in lowered
    assert "samesite=lax" in lowered and "path=/auth" in lowered
    assert value.split(".", 1)[0] == str(TENANT_A)
    usuario = usuario_row(acc_db, email)
    (membresia,) = membresias_de(acc_db, usuario["id"])
    with acc_db.migrator.connect() as conn:
        stored = conn.execute(
            text("select membresia_id, tenant_id from refresh_token where token_hash = :h"),
            {"h": token_storage_hash(value.split(".", 1)[1])},
        ).one()
    assert stored.membresia_id == membresia["id"]
    assert stored.tenant_id == TENANT_A

    me = client.get(
        "/auth/me", headers={"Authorization": f"Bearer {response.get_json()['access_token']}"}
    )
    assert me.status_code == 200
    assert me.get_json()["usuario"]["email"] == email


def test_a8_invited_contador_accepts_logs_in_and_gets_403_on_admin_routes(client):
    token, email = invitar(client, rol="contador")
    access = aceptar(client, token).get_json()["access_token"]

    logged = login(client, email)
    assert logged.status_code == 200
    assert logged.get_json()["rol"] == "contador"
    for header in (access, logged.get_json()["access_token"]):
        response = client.post(
            "/invitaciones",
            json={"email": nuevo_email(), "rol": "contador"},
            headers={"Authorization": f"Bearer {header}"},
        )
        assert response.status_code == 403
        assert response.get_json()["error"]["code"] == "prohibido"


def test_invited_admin_can_invite(client):
    token, _ = invitar(client, rol="admin")
    access = aceptar(client, token).get_json()["access_token"]

    response = client.post(
        "/invitaciones",
        json={"email": nuevo_email(), "rol": "contador"},
        headers={"Authorization": f"Bearer {access}"},
    )

    assert response.status_code == 201


def test_invitation_of_b_creates_the_account_in_b(client, acc_db):
    token, email = invitar(client, cuenta=ADMIN_B, tenant=TENANT_B)

    response = aceptar(client, token)

    assert response.get_json()["tenant"]["id"] == str(TENANT_B)
    (membresia,) = membresias_de(acc_db, usuario_row(acc_db, email)["id"])
    assert membresia["tenant_id"] == TENANT_B


# --- Email, tenant y rol de la invitación, nunca de la petición (Q4, R9) -------------


def test_email_tenant_and_role_from_body_query_headers_jwt_and_cookie_are_ignored(client, acc_db):
    """Invitación de A aceptada con JWT, cookie y campos de B: no activa nada en B."""
    token, email = invitar(client, rol="contador")
    otro = nuevo_email()
    before_b = membresias_del_tenant(acc_db, TENANT_B)
    cookie = f"{REFRESH_COOKIE_SECURE_NAME}={TENANT_B}.{new_token()}"

    response = aceptar(
        client,
        token,
        extra={
            "email": otro,
            "rol": "admin",
            "tenant_id": str(TENANT_B),
            "tenant": str(TENANT_B),
            "usuario_id": str(ADMIN_B.usuario_id),
            "activa": False,
        },
        headers={
            **bearer(ADMIN_B, TENANT_B, rol="admin"),
            "Cookie": cookie,
            "X-Tenant-ID": str(TENANT_B),
            "X-Rol": "admin",
        },
        query_string={"tenant_id": str(TENANT_B), "rol": "admin", "email": otro},
    )

    assert response.status_code == 201
    body = response.get_json()
    assert body["usuario"]["email"] == email
    assert body["tenant"]["id"] == str(TENANT_A)
    assert body["rol"] == "contador"
    assert usuario_row(acc_db, otro) is None
    (membresia,) = membresias_de(acc_db, usuario_row(acc_db, email)["id"])
    assert (membresia["tenant_id"], membresia["rol"]) == (TENANT_A, "contador")
    assert membresias_del_tenant(acc_db, TENANT_B) == before_b
    assert membresias_de(acc_db, ADMIN_B.usuario_id)[0]["rol"] == "admin"


# --- Rechazos indistinguibles (A9, A20, Q6, Q16) -------------------------------------


def _rejection_cases(client, acc_db) -> dict[str, str]:
    """Tokens que no deben crear nada; todos con una invitación real detrás si aplica."""
    vencida, _ = invitar(client)
    expire(acc_db, vencida)
    usada, _ = invitar(client)
    assert aceptar(client, usada).status_code == 201
    vigente, _ = invitar(client)
    duplicado_a, _ = invitar(client, email=CONTADOR_A.email)
    duplicado_b, _ = invitar(client, email=ADMIN_B.email)
    return {
        "vencida": vencida,
        "usada": usada,
        "inexistente": new_token(),
        "vacio": "",
        "corto": "x",
        "con_espacios": f" {vigente} ",
        "clave_en_vez_de_token": token_key(vigente),
        "hash_guardado_hex": token_storage_hash(vigente).hex(),
        "nul": "\x00",
        "sustituto": "\ud800",
        "unicode": "ñandú-token",
        "email_existente_en_a": duplicado_a,
        "email_existente_en_otro_tenant": duplicado_b,
    }


def test_every_rejected_acceptance_is_indistinguishable_and_creates_nothing(client, acc_db):
    cases = _rejection_cases(client, acc_db)
    vigente = cases["con_espacios"].strip()
    before = snapshot(acc_db)

    observed = {case: aceptar(client, token) for case, token in cases.items()}

    reference = comparable(observed["inexistente"])
    assert reference[0] == 400
    assert reference[1] == INVALID
    for case, response in observed.items():
        assert comparable(response) == reference, case
        assert "Set-Cookie" not in response.headers, case
        assert "access_token" not in response.get_data(as_text=True), case
    assert snapshot(acc_db) == before
    # El duplicado revierte el consumo (A20) y la vigente sigue sin usar.
    for case in ("email_existente_en_a", "email_existente_en_otro_tenant"):
        assert inv_row(acc_db, cases[case])["usada_en"] is None, case
    assert inv_row(acc_db, vigente)["usada_en"] is None
    assert aceptar(client, vigente).status_code == 201


def test_existing_users_keep_their_single_membership_after_a_duplicate_invitation(client, acc_db):
    """Q6: un usuario de B invitado en A no gana una segunda membresía (falla cerrado)."""
    token, _ = invitar(client, email=CONTADOR_B.email, rol="admin")

    response = aceptar(client, token, password=PASSWORD)

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invitacion_invalida"
    (membresia,) = membresias_de(acc_db, CONTADOR_B.usuario_id)
    assert (membresia["tenant_id"], membresia["rol"]) == (TENANT_B, "contador")
    logged = login(client, CONTADOR_B.email, PASSWORD)
    assert logged.status_code == 200
    assert logged.get_json()["tenant"]["id"] == str(TENANT_B)


def test_every_attempt_that_reaches_the_database_hashes_once(client, acc_db, hash_spy):
    """A20: mismo costo (un Argon2) con token vigente, vencido, usado, inexistente o duplicado."""
    cases = _rejection_cases(client, acc_db)
    vigente = cases["con_espacios"].strip()
    cases["vigente"] = vigente
    hash_spy.hashed = 0

    for case, token in cases.items():
        before = hash_spy.hashed
        aceptar(client, token)
        assert hash_spy.hashed == before + 1, case


# --- Cuerpo y contraseña, antes de mirar el token (R12, Q9) --------------------------


INVALID_BODIES = {
    "lista": ["t", "n", "p"],
    "texto": "token",
    "nulo": None,
    "sin_token": {"nombre": NOMBRE, "password": NUEVA},
    "sin_nombre": {"token": "t", "password": NUEVA},
    "sin_password": {"token": "t", "nombre": NOMBRE},
    "token_numero": {"token": 5, "nombre": NOMBRE, "password": NUEVA},
    "token_lista": {"token": ["t"], "nombre": NOMBRE, "password": NUEVA},
    "nombre_numero": {"token": "t", "nombre": 5, "password": NUEVA},
    "password_numero": {"token": "t", "nombre": NOMBRE, "password": 1234567890},
    "nombre_vacio": {"token": "t", "nombre": "   ", "password": NUEVA},
    "nombre_con_nul": {"token": "t", "nombre": "Ana\x00", "password": NUEVA},
    "nombre_con_salto": {"token": "t", "nombre": "Ana\nBeto", "password": NUEVA},
    "nombre_sustituto": {"token": "t", "nombre": "Ana\ud800", "password": NUEVA},
}


@pytest.mark.parametrize("case", sorted(INVALID_BODIES))
@pytest.mark.parametrize("with_real_token", [False, True], ids=["token_falso", "token_real"])
def test_malformed_bodies_are_400_without_hashing_nor_consuming(
    client, acc_db, hash_spy, case, with_real_token
):
    body = INVALID_BODIES[case]
    token = None
    if with_real_token and isinstance(body, dict) and isinstance(body.get("token"), str):
        token, _ = invitar(client)
        body = {**body, "token": token}
    hash_spy.hashed = 0

    response = client.post(ACEPTAR, json=body)

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "solicitud_invalida"
    assert hash_spy.hashed == 0
    if token is not None:
        assert inv_row(acc_db, token)["usada_en"] is None


@pytest.mark.parametrize(
    ("data", "content_type"),
    [("{no es json", "application/json"), ("token=x", "text/plain"), ("", None)],
    ids=["json_invalido", "texto_plano", "sin_cuerpo"],
)
@pytest.mark.parametrize("path", [VALIDAR, ACEPTAR])
def test_non_json_bodies_are_400(client, path, data, content_type):
    headers = {} if content_type is None else {"Content-Type": content_type}

    response = client.post(path, data=data, headers=headers)

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "solicitud_invalida"


PASSWORD_CASES = {
    "corta": ("Corta-1", "contrasena_corta"),
    "larga": ("x" * (PASSWORD_MAX_LENGTH + 1), "contrasena_larga"),
    "comun": ("Contraseña123", "contrasena_comun"),
    "sustituto": ("Clave-larga-\ud800", "contrasena_invalida"),
}


@pytest.mark.parametrize("case", sorted(PASSWORD_CASES))
def test_password_policy_is_checked_before_hashing_and_does_not_depend_on_the_token(
    client, acc_db, hash_spy, case
):
    password, code = PASSWORD_CASES[case]
    token, _ = invitar(client)
    hash_spy.hashed = 0

    with_real = aceptar(client, token, password=password)
    with_fake = aceptar(client, new_token(), password=password)

    assert with_real.status_code == 400
    assert with_real.get_json()["error"]["code"] == code
    assert comparable(with_real) == comparable(with_fake)
    assert hash_spy.hashed == 0
    assert inv_row(acc_db, token)["usada_en"] is None
    assert aceptar(client, token).status_code == 201


# --- Sesión tras el COMMIT (A22) -----------------------------------------------------


@pytest.mark.parametrize("failure", ["excepcion", "sin_sesion"])
def test_if_issuing_the_session_fails_the_account_exists_and_login_works(
    client, acc_db, monkeypatch, failure
):
    token, email = invitar(client)

    def broken(usuario_id, tenant_id):
        if failure == "excepcion":
            raise RuntimeError("fallo sintético al emitir la sesión")
        return None

    monkeypatch.setattr(inv_service, "issue_session", broken)
    response = aceptar(client, token)
    monkeypatch.undo()

    assert response.status_code == 500
    assert response.get_json()["error"]["code"] == "error_interno"
    assert "Set-Cookie" not in response.headers
    assert "access_token" not in response.get_data(as_text=True)
    assert inv_row(acc_db, token)["usada_en"] is not None
    assert usuario_row(acc_db, email) is not None
    logged = login(client, email)
    assert logged.status_code == 200
    assert logged.get_json()["tenant"]["id"] == str(TENANT_A)
    assert aceptar(client, token).get_json()["error"]["code"] == "invitacion_invalida"


def test_the_acceso_call_runs_without_tenant_and_the_session_opens_after_it(client, monkeypatch):
    """La función ``acceso`` corre fuera de ``tenant_session``; la sesión se abre después."""
    events: list[str] = []
    original_call = inv_service.aceptar_invitacion
    original_session = auth_service.tenant_session

    def spy_call(*args):
        events.append("aceptar_invitacion")
        return original_call(*args)

    def spy_session(tenant_id):
        events.append(f"tenant_session:{tenant_id}")
        return original_session(tenant_id)

    monkeypatch.setattr(inv_service, "aceptar_invitacion", spy_call)
    monkeypatch.setattr(auth_service, "tenant_session", spy_session)
    token, _ = invitar(client)
    events.clear()

    assert aceptar(client, token).status_code == 201

    assert events == ["aceptar_invitacion", f"tenant_session:{TENANT_A}"]


def test_rejected_acceptance_and_validation_open_no_tenant_session(client, monkeypatch):
    opened: list[object] = []
    original = auth_service.tenant_session

    def spy(tenant_id):
        opened.append(tenant_id)
        return original(tenant_id)

    monkeypatch.setattr(auth_service, "tenant_session", spy)
    token, _ = invitar(client)

    assert validar(client, token).get_json() == {"vigente": True}
    assert aceptar(client, new_token()).status_code == 400

    assert opened == []


# --- Validar (R11, A9) ---------------------------------------------------------------


def test_validate_says_only_whether_it_is_valid_and_does_not_consume(client, acc_db):
    token, _ = invitar(client)

    for _ in range(3):
        response = validar(client, token)
        assert response.status_code == 200
        assert response.get_json() == {"vigente": True}
    assert inv_row(acc_db, token)["usada_en"] is None
    assert aceptar(client, token).status_code == 201
    assert validar(client, token).get_json() == {"vigente": False}


def test_every_non_valid_token_validates_identically(client, acc_db):
    cases = _rejection_cases(client, acc_db)
    vigente = cases.pop("con_espacios").strip()
    # validar no mira el email: con email duplicado la invitación sigue vigente.
    cases.pop("email_existente_en_a")
    cases.pop("email_existente_en_otro_tenant")
    before = snapshot(acc_db)

    observed = {case: validar(client, token) for case, token in cases.items()}

    reference = comparable_ok(observed["inexistente"])
    assert reference[:2] == (200, {"vigente": False})
    for case, response in observed.items():
        assert comparable_ok(response) == reference, case
    assert snapshot(acc_db) == before
    assert validar(client, vigente).get_json() == {"vigente": True}


@pytest.mark.parametrize(
    "body",
    [None, [], "token", {}, {"token": 5}, {"token": None}, {"token": ["x"]}],
    ids=["nulo", "lista", "texto", "vacio", "numero", "token_nulo", "token_lista"],
)
def test_validate_with_a_malformed_body_is_400(client, body):
    response = client.post(VALIDAR, json=body)

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "solicitud_invalida"


def test_validate_ignores_credentials_and_issues_nothing(client):
    token, _ = invitar(client)

    response = validar(
        client,
        token,
        headers={
            **bearer(ADMIN_B, TENANT_B),
            "Cookie": f"{REFRESH_COOKIE_SECURE_NAME}={TENANT_B}.{new_token()}",
        },
    )

    assert response.get_json() == {"vigente": True}
    assert "Set-Cookie" not in response.headers


# --- Cabeceras, tamaño y métodos (R14, A25) ------------------------------------------


@pytest.mark.parametrize("path", [VALIDAR, ACEPTAR])
def test_responses_carry_no_store_and_no_referrer(client, path):
    token, _ = invitar(client)
    ok = validar(client, token) if path == VALIDAR else aceptar(client, token)
    bad = client.post(path, json=[])

    for response in (ok, bad):
        assert response.status_code in (200, 201, 400)
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Referrer-Policy"] == "no-referrer"


@pytest.mark.parametrize("path", [VALIDAR, ACEPTAR])
def test_bodies_over_4_kb_are_413_and_consume_nothing(client, acc_db, path):
    token, _ = invitar(client)
    body = {"token": token, "nombre": NOMBRE, "password": NUEVA, "x": "x" * AUTH_MAX_BODY_BYTES}

    response = client.post(path, json=body)

    assert response.status_code == 413
    assert response.get_json()["error"]["code"] == "cuerpo_demasiado_grande"
    assert inv_row(acc_db, token)["usada_en"] is None


@pytest.mark.parametrize("path", [VALIDAR, ACEPTAR])
def test_only_post(client, path):
    for method in (client.get, client.put, client.patch, client.delete):
        assert method(path).status_code == 405


# --- Secretos fuera de los logs (R14, A14, M1) ---------------------------------------


@pytest.fixture
def sqlalchemy_debug():
    """``sqlalchemy.engine``/``pool`` en DEBUG antes de crear la app; restaura al final."""
    names = ("sqlalchemy.engine", "sqlalchemy.engine.Engine", "sqlalchemy.pool")
    saved = {}
    for name in names:
        logger = logging.getLogger(name)
        saved[name] = (logger.level, list(logger.filters), list(logger.handlers))
    for name in ("sqlalchemy.engine", "sqlalchemy.pool"):
        logging.getLogger(name).setLevel(logging.DEBUG)
    yield
    for name, (level, filters, handlers) in saved.items():
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.filters[:] = filters
        for handler in logger.handlers[:]:
            if handler not in handlers:
                logger.removeHandler(handler)


def _broken_session(usuario_id, tenant_id):
    raise RuntimeError("fallo sintético al emitir la sesión")


def test_validate_and_accept_never_log_tokens_passwords_or_hashes(
    acc_db, sqlalchemy_debug, caplog, capfd, monkeypatch
):
    flask_app = make_app(acc_db)
    try:
        client = flask_app.test_client(use_cookies=False)
        token, email = invitar(client)
        duplicado, _ = invitar(client, email=CONTADOR_A.email)
        fallida, fallida_email = invitar(client)
        with caplog.at_level(logging.DEBUG):
            validar(client, token)
            ok = aceptar(client, token)
            aceptar(client, token)  # usada
            aceptar(client, duplicado)
            aceptar(client, new_token())
            aceptar(client, token, password="Corta-1")
            with monkeypatch.context() as mp:
                mp.setattr(inv_service, "issue_session", _broken_session)
                assert aceptar(client, fallida).status_code == 500
    finally:
        dispose(flask_app)

    assert ok.status_code == 201
    cookie = cookies_of(ok)[REFRESH_COOKIE_SECURE_NAME][0]
    secrets = [NUEVA, ok.get_json()["access_token"], cookie, cookie.split(".", 1)[1]]
    for value in (token, duplicado, fallida):
        stored = token_storage_hash(value)
        secrets += [value, token_key(value), stored.hex(), repr(stored)]
    for value in (email, fallida_email):
        secrets.append(usuario_row(acc_db, value)["password_hash"])
    out, err = capfd.readouterr()
    joined = "\n".join((caplog.text, out, err))
    assert [value for value in secrets if value in joined] == []
    assert "Row " not in joined
