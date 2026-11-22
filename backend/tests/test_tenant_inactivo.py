"""Efecto de ``tenant.activo`` en la sesión del tenant (spec 017, T3b; R22, A9; plan.md §2.5).

Sobre una base temporal migrada a ``head`` (tenants sintéticos A y B de ``acceso_db``) y
con la consola de plataforma habilitada: un desarrollador desactiva la empresa A por
``PATCH /plataforma/empresas/{id}`` y desde ese momento sus usuarios no entran.

- Un token vigente de ``admin`` y de ``contador`` de A recibe ``401 no_autenticado`` en
  **cada** endpoint protegido de tenant (recorrido de ``url_map``), el mismo ``401`` que una
  membresía revocada (sin código propio). Reactivar restaura el acceso con el mismo token.
- ``POST /auth/refresh`` con una cookie vigente de A: ``401`` sin cookie nueva. Desactivar
  no revoca los refresh: tras reactivar, una cookie que no se presentó sigue sirviendo y la
  que se presentó durante la desactivación quedó usada (``401``).
- ``POST /auth/login`` de un usuario de A: ``401 credenciales_invalidas`` con el mismo
  cuerpo que una contraseña errónea.
- Una invitación pendiente de A no vale (0023): ``validar`` da ``false`` y aceptar da el
  ``400 invitacion_invalida`` de una vencida, sin consumirla ni crear cuenta; tras
  reactivar, la misma invitación se acepta y entra con sesión.
- B sigue entrando y desactivar o reactivar solo cambia ``tenant`` (su estado) y
  ``plataforma_auditoria``: el número de filas del resto de tablas no cambia.

Datos sintéticos (``@ejemplo.test``).
"""

import re
import uuid
from collections.abc import Iterator

import pytest
from acceso_db import (
    ADMIN_A,
    ADMIN_B,
    CONTADOR_A,
    PASSWORD,
    TENANT_A,
    TENANT_B,
    AccesoDb,
    dispose,
    temporary_acceso_db,
)
from flask import Flask
from plataforma_db import (
    CSRF,
    ejecutar,
    error_code,
    filas,
    login,
    make_plat_app,
    nuevo_dev,
    sembrar_dev,
)
from sqlalchemy import text

from app.auth.credentials import token_storage_hash
from app.auth.http import REFRESH_COOKIE_SECURE_NAME

NUEVA_PASSWORD = "Clave-Invitada-Sintetica-2026"


@pytest.fixture(scope="module")
def ina_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("tenant_inactivo")


@pytest.fixture(scope="module")
def ina_app(ina_db) -> Iterator[Flask]:
    flask_app = make_plat_app(ina_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(ina_app):
    return ina_app.test_client(use_cookies=False)


@pytest.fixture(scope="module")
def dev_headers(ina_db, ina_app) -> dict[str, str]:
    dev = sembrar_dev(ina_db, nuevo_dev("inactivo"))
    response = login(ina_app.test_client(use_cookies=False), dev.email)
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['access_token']}"}


def _estado(client, dev_headers, tenant: uuid.UUID, activa: bool) -> None:
    response = client.patch(
        f"/plataforma/empresas/{tenant}", json={"activa": activa}, headers=dev_headers
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json() == {"id": str(tenant), "activa": activa}


@pytest.fixture
def a_inactiva(client, dev_headers) -> Iterator[None]:
    """Desactiva la empresa A durante la prueba; al terminar la reactiva."""
    yield None
    _estado(client, dev_headers, TENANT_A, True)


def _tenant_login(client, email: str, password: str = PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def _cookie(response) -> str:
    for header in response.headers.getlist("Set-Cookie"):
        name, _, rest = header.partition("=")
        if name == REFRESH_COOKIE_SECURE_NAME:
            return rest.split(";", 1)[0]
    raise AssertionError("sin cookie de refresh")


def _bearer(response) -> dict[str, str]:
    return {"Authorization": f"Bearer {response.get_json()['access_token']}"}


def _refresh(client, cookie: str):
    return client.post(
        "/auth/refresh", headers={**CSRF, "Cookie": f"{REFRESH_COOKIE_SECURE_NAME}={cookie}"}
    )


def _sin_request_id(body: dict) -> dict:
    error = {k: v for k, v in body["error"].items() if k != "request_id"}
    return {"error": error}


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


def _counts(db: AccesoDb) -> dict[str, int]:
    tables = [
        row["tablename"]
        for row in filas(db, "select tablename from pg_tables where schemaname = 'public'")
    ]
    with db.migrator.connect() as conn:
        return {t: conn.scalar(text(f'select count(*) from "{t}"')) for t in tables}  # noqa: S608


# --- (1) token vigente --------------------------------------------------------------------


def test_a_live_token_of_an_inactive_company_gets_401_everywhere(
    client, ina_app, dev_headers, a_inactiva
):
    admin = _bearer(_tenant_login(client, ADMIN_A.email))
    contador = _bearer(_tenant_login(client, CONTADOR_A.email))
    for headers in (admin, contador):
        assert client.get("/auth/me", headers=headers).status_code == 200

    _estado(client, dev_headers, TENANT_A, False)
    routes = _tenant_routes(ina_app)
    assert len(routes) > 30
    for name, headers in (("admin", admin), ("contador", contador)):
        for endpoint, method, path in routes:
            response = client.open(path, method=method, json={}, headers=headers)
            assert response.status_code == 401, (name, endpoint, method)
            assert response.get_json()["error"] == {
                "code": "no_autenticado",
                "message": "Debes iniciar sesión.",
                "request_id": response.get_json()["error"]["request_id"],
            }

    _estado(client, dev_headers, TENANT_A, True)
    for headers in (admin, contador):
        assert client.get("/auth/me", headers=headers).status_code == 200
        assert client.get("/ubicaciones", headers=headers).status_code == 200


def test_an_inactive_company_gives_the_same_401_as_a_revoked_membership(
    client, ina_db, dev_headers, a_inactiva
):
    admin = _bearer(_tenant_login(client, ADMIN_A.email))
    _estado(client, dev_headers, TENANT_A, False)
    inactiva = client.get("/auth/me", headers=admin)
    _estado(client, dev_headers, TENANT_A, True)

    ajeno = _bearer(_tenant_login(client, ADMIN_B.email))
    with ina_db.migrator.begin() as conn:
        conn.execute(
            text("update membresia set activa = false where usuario_id = :u"),
            {"u": ADMIN_B.usuario_id},
        )
    try:
        revocada = client.get("/auth/me", headers=ajeno)
    finally:
        with ina_db.migrator.begin() as conn:
            conn.execute(
                text("update membresia set activa = true where usuario_id = :u"),
                {"u": ADMIN_B.usuario_id},
            )
    assert (inactiva.status_code, revocada.status_code) == (401, 401)
    assert _sin_request_id(inactiva.get_json()) == _sin_request_id(revocada.get_json())
    assert dict(inactiva.headers).keys() == dict(revocada.headers).keys()


# --- (2) refresh --------------------------------------------------------------------------


def test_refresh_of_an_inactive_company_fails_without_a_new_cookie(client, dev_headers, a_inactiva):
    presentada = _cookie(_tenant_login(client, ADMIN_A.email))
    guardada = _cookie(_tenant_login(client, ADMIN_A.email))
    _estado(client, dev_headers, TENANT_A, False)

    response = _refresh(client, presentada)
    assert response.status_code == 401
    assert error_code(response) == "no_autenticado"
    assert "Set-Cookie" not in response.headers
    assert "access_token" not in response.get_data(as_text=True)

    # Desactivar no revocó los refresh: tras reactivar, el que no se presentó sirve; el
    # presentado durante la desactivación quedó usado y no vuelve a servir.
    _estado(client, dev_headers, TENANT_A, True)
    muerta = _refresh(client, presentada)
    assert muerta.status_code == 401
    assert error_code(muerta) == "no_autenticado"
    assert "Set-Cookie" not in muerta.headers
    renovada = _refresh(client, guardada)
    assert renovada.status_code == 200
    assert _cookie(renovada)


# --- (3) login ----------------------------------------------------------------------------


def test_login_of_an_inactive_company_is_the_generic_invalid_credentials(
    client, dev_headers, a_inactiva
):
    _estado(client, dev_headers, TENANT_A, False)
    for email in (ADMIN_A.email, CONTADOR_A.email):
        inactiva = _tenant_login(client, email)
        erronea = _tenant_login(client, email, "Otra-Clave-Incorrecta-2026")
        assert (inactiva.status_code, erronea.status_code) == (401, 401)
        assert error_code(inactiva) == "credenciales_invalidas"
        assert _sin_request_id(inactiva.get_json()) == _sin_request_id(erronea.get_json())
        assert "Set-Cookie" not in inactiva.headers
        assert "empresa_desactivada" not in inactiva.get_data(as_text=True)

    _estado(client, dev_headers, TENANT_A, True)
    assert _tenant_login(client, ADMIN_A.email).status_code == 200


# --- (4) invitación -----------------------------------------------------------------------


def _invitar(client, admin: dict[str, str]) -> tuple[str, str]:
    email = f"invitado.{uuid.uuid4().hex[:10]}@ejemplo.test"
    creada = client.post("/invitaciones", json={"email": email, "rol": "contador"}, headers=admin)
    assert creada.status_code == 201
    return creada.get_json()["enlace"].split("#", 1)[1], email


def _aceptar(client, token: str):
    return client.post(
        "/invitaciones/aceptar",
        json={"token": token, "nombre": "Invitada", "password": NUEVA_PASSWORD},
    )


def _validar(client, token: str) -> bool:
    response = client.post("/invitaciones/validar", json={"token": token})
    assert response.status_code == 200
    return response.get_json()["vigente"]


def _observable(response) -> tuple:
    """Estado, cuerpo sin ``request_id`` y cabeceras salvo ``X-Request-Id``."""
    headers = sorted(
        (k.lower(), v) for k, v in response.headers.items() if k.lower() != "x-request-id"
    )
    return response.status_code, _sin_request_id(response.get_json()), headers


def _invitacion(db: AccesoDb, token: str) -> dict:
    (row,) = filas(
        db,
        "select usada_en from invitacion where token_hash = :h",
        {"h": token_storage_hash(token)},
    )
    return row


def _cuenta(db: AccesoDb, email: str) -> tuple[int, int]:
    (row,) = filas(
        db,
        "select (select count(*) from usuario where email = :e) as usuarios, "
        "(select count(*) from membresia m join usuario u on u.id = m.usuario_id "
        "where u.email = :e) as membresias",
        {"e": email},
    )
    return row["usuarios"], row["membresias"]


def test_accepting_an_invitation_of_an_inactive_company_is_the_generic_invalid_invitation(
    client, ina_db, dev_headers, a_inactiva
):
    admin = _bearer(_tenant_login(client, ADMIN_A.email))
    token, email = _invitar(client, admin)
    vencida, _ = _invitar(client, admin)
    ejecutar(
        ina_db,
        "update invitacion set expira_en = now() - interval '1 minute' where token_hash = :h",
        {"h": token_storage_hash(vencida)},
    )
    _estado(client, dev_headers, TENANT_A, False)

    assert _validar(client, token) is False
    assert _validar(client, token) == _validar(client, vencida)
    response = _aceptar(client, token)
    referencia = _aceptar(client, vencida)
    assert response.status_code == 400
    assert error_code(response) == "invitacion_invalida"
    assert _observable(response) == _observable(referencia)
    assert "Set-Cookie" not in response.headers
    assert "access_token" not in response.get_data(as_text=True)
    # No se consume ni crea nada: el correo sigue libre y la invitación pendiente.
    assert _invitacion(ina_db, token) == {"usada_en": None}
    assert _cuenta(ina_db, email) == (0, 0)
    assert _tenant_login(client, email, NUEVA_PASSWORD).status_code == 401

    # Tras reactivar, la misma invitación vale y entra con sesión.
    _estado(client, dev_headers, TENANT_A, True)
    assert _validar(client, token) is True
    aceptada = _aceptar(client, token)
    assert aceptada.status_code == 201, aceptada.get_json()
    assert _cookie(aceptada)
    assert client.get("/auth/me", headers=_bearer(aceptada)).status_code == 200
    assert _invitacion(ina_db, token)["usada_en"] is not None
    assert _cuenta(ina_db, email) == (1, 1)


# --- (5) otro tenant y conteos ------------------------------------------------------------


def test_deactivating_changes_only_the_tenant_state_and_the_audit(
    client, ina_db, dev_headers, a_inactiva
):
    otra = _bearer(_tenant_login(client, ADMIN_B.email))
    before = _counts(ina_db)
    tenant_b = filas(ina_db, "select * from tenant where id = :t", {"t": TENANT_B})

    _estado(client, dev_headers, TENANT_A, False)
    after = _counts(ina_db)
    assert {t for t in before if before[t] != after[t]} == {"plataforma_auditoria"}
    assert after["plataforma_auditoria"] == before["plataforma_auditoria"] + 1
    (estado,) = filas(ina_db, "select activo from tenant where id = :t", {"t": TENANT_A})
    assert estado == {"activo": False}
    assert filas(ina_db, "select * from tenant where id = :t", {"t": TENANT_B}) == tenant_b

    # La otra empresa sigue entrando, con su token y por el login.
    assert client.get("/auth/me", headers=otra).status_code == 200
    assert _tenant_login(client, ADMIN_B.email).status_code == 200

    middle = _counts(ina_db)
    _estado(client, dev_headers, TENANT_A, True)
    final = _counts(ina_db)
    assert {t for t in middle if middle[t] != final[t]} == {"plataforma_auditoria"}
    (estado,) = filas(
        ina_db,
        "select activo, desactivado_en, desactivado_por from tenant where id = :t",
        {"t": TENANT_A},
    )
    assert estado == {"activo": True, "desactivado_en": None, "desactivado_por": None}
