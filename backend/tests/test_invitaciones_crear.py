"""Crear invitación (spec 002, T8; R10, R14, Q7, Q13, Q17, A8, A12, A14, A25; plan.md §4).

``POST /invitaciones`` (solo ``admin``) sobre una base temporal migrada a ``head``
con dos tenants sintéticos (A y B):

- Cuerpo ``{email, rol}``; ``201`` con la invitación y el enlace
  ``/invitacion#<token>`` (Q13), que solo aparece en esta respuesta.
- El tenant es el del token; ``creada_por`` es el ``usuario_id`` del token (nunca
  del cuerpo); ``expira_en = now() + 72 h`` (Q7) fijado por la base.
- La base guarda solo ``token_hash = sha256(sha256(token))`` (I1): ni el token ni
  ``sha256(token)`` aparecen en la fila.
- ``tenant_id``, ``creada_por``, ``expira_en``, ``usada_en`` o ``token_hash`` del
  cuerpo, de la URL o de las cabeceras se ignoran.
- Cuerpo inválido -> ``400`` ``solicitud_invalida`` sin crear nada.
- Ningún log contiene el token, su clave ni el hash, también con
  ``sqlalchemy.engine`` en ``DEBUG``.

Datos sintéticos (``@ejemplo.test``).
"""

import logging
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from acceso_db import (
    ADMIN_A,
    ADMIN_B,
    CONTADOR_A,
    TENANT_A,
    TENANT_B,
    AccesoDb,
    access_token,
    all_invitaciones,
    bearer,
    dispose,
    invitaciones_de,
    make_app,
    temporary_acceso_db,
)
from flask import Flask
from sqlalchemy import text

from app.auth.credentials import token_key, token_storage_hash
from app.auth.http import AUTH_MAX_BODY_BYTES

INVITAR = "/invitaciones"
LINK_PREFIX = "/invitacion#"


@pytest.fixture(scope="module")
def inv_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("invitaciones")


@pytest.fixture(scope="module")
def inv_app(inv_db) -> Iterator[Flask]:
    flask_app = make_app(inv_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(inv_app):
    return inv_app.test_client(use_cookies=False)


def nuevo_email() -> str:
    return f"invitado.{uuid.uuid4().hex[:10]}@ejemplo.test"


def invitar(client, body, cuenta=ADMIN_A, tenant=TENANT_A, **kwargs):
    headers = {**bearer(cuenta, tenant), **kwargs.pop("headers", {})}
    return client.post(INVITAR, json=body, headers=headers, **kwargs)


def token_of(response) -> str:
    enlace = response.get_json()["enlace"]
    assert enlace.startswith(LINK_PREFIX)
    return enlace.removeprefix(LINK_PREFIX)


def row_by_id(db: AccesoDb, invitacion_id: str) -> dict:
    with db.migrator.connect() as conn:
        return dict(
            conn.execute(text("select * from invitacion where id = :id"), {"id": invitacion_id})
            .mappings()
            .one()
        )


def db_now(db: AccesoDb) -> datetime:
    with db.migrator.connect() as conn:
        return conn.scalar(text("select now()"))


# --- Creación correcta ---------------------------------------------------------------


@pytest.mark.parametrize("rol", ["contador", "admin"])
def test_admin_creates_an_invitation_with_the_contract(client, inv_db, rol):
    email = nuevo_email()

    response = invitar(client, {"email": email, "rol": rol})

    assert response.status_code == 201, response.get_json()
    body = response.get_json()
    assert set(body) == {"invitacion", "enlace"}
    assert set(body["invitacion"]) == {"id", "email", "rol", "expira_en"}
    assert body["invitacion"]["email"] == email
    assert body["invitacion"]["rol"] == rol
    token = token_of(response)
    assert len(token) >= 43
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"

    row = row_by_id(inv_db, body["invitacion"]["id"])
    assert row["tenant_id"] == TENANT_A
    assert row["email"] == email
    assert row["rol"] == rol
    assert row["creada_por"] == ADMIN_A.usuario_id
    assert row["usada_en"] is None
    assert datetime.fromisoformat(body["invitacion"]["expira_en"]) == row["expira_en"]


def test_expiration_is_72_hours_set_by_the_database(client, inv_db):
    before = db_now(inv_db)
    response = invitar(client, {"email": nuevo_email(), "rol": "contador"})
    after = db_now(inv_db)

    row = row_by_id(inv_db, response.get_json()["invitacion"]["id"])
    assert before + timedelta(hours=72) <= row["expira_en"] <= after + timedelta(hours=72)


def test_only_the_double_hash_is_stored(client, inv_db):
    response = invitar(client, {"email": nuevo_email(), "rol": "contador"})
    token = token_of(response)

    row = row_by_id(inv_db, response.get_json()["invitacion"]["id"])
    assert bytes(row["token_hash"]) == token_storage_hash(token)
    dumped = repr(row)
    for secret in (token, token_key(token)):
        assert secret not in dumped
    assert bytes(row["token_hash"]) != bytes.fromhex(token_key(token))


def test_each_invitation_has_its_own_token(client):
    tokens = {
        token_of(invitar(client, {"email": nuevo_email(), "rol": "contador"})) for _ in range(5)
    }
    assert len(tokens) == 5


def test_the_link_appears_only_in_the_link_field(client):
    response = invitar(client, {"email": nuevo_email(), "rol": "contador"})
    token = token_of(response)
    body = response.get_json()

    assert token not in str(body["invitacion"])
    assert all(token not in value for _, value in response.headers.items())


def test_email_is_normalized(client, inv_db):
    email = nuevo_email()

    response = invitar(client, {"email": f"  {email.upper()}  ", "rol": "contador"})

    assert response.status_code == 201
    assert response.get_json()["invitacion"]["email"] == email
    assert row_by_id(inv_db, response.get_json()["invitacion"]["id"])["email"] == email


def test_admin_of_b_creates_in_b(client, inv_db):
    response = invitar(client, {"email": nuevo_email(), "rol": "contador"}, ADMIN_B, TENANT_B)

    row = row_by_id(inv_db, response.get_json()["invitacion"]["id"])
    assert row["tenant_id"] == TENANT_B
    assert row["creada_por"] == ADMIN_B.usuario_id


# --- Tenant y creada_por del token, nunca de la petición (R10, A12) -----------------


def test_tenant_and_server_fields_from_the_body_are_ignored(client, inv_db):
    before_b = invitaciones_de(inv_db, TENANT_B)
    body = {
        "email": nuevo_email(),
        "rol": "contador",
        "tenant_id": str(TENANT_B),
        "tenant": str(TENANT_B),
        "creada_por": str(ADMIN_B.usuario_id),
        "expira_en": "2999-01-01T00:00:00+00:00",
        "usada_en": "2000-01-01T00:00:00+00:00",
        "token_hash": "00" * 32,
        "id": str(uuid.uuid4()),
    }

    response = invitar(client, body)

    assert response.status_code == 201
    created = response.get_json()["invitacion"]
    assert created["id"] != body["id"]
    row = row_by_id(inv_db, created["id"])
    assert row["tenant_id"] == TENANT_A
    assert row["creada_por"] == ADMIN_A.usuario_id
    assert row["usada_en"] is None
    assert row["expira_en"].year < 2999
    assert bytes(row["token_hash"]) == token_storage_hash(token_of(response))
    assert invitaciones_de(inv_db, TENANT_B) == before_b


def test_tenant_from_query_and_headers_is_ignored(client, inv_db):
    before_b = invitaciones_de(inv_db, TENANT_B)

    response = invitar(
        client,
        {"email": nuevo_email(), "rol": "contador"},
        headers={"X-Tenant-ID": str(TENANT_B), "X-Tenant": str(TENANT_B)},
        query_string={"tenant_id": str(TENANT_B), "creada_por": str(ADMIN_B.usuario_id)},
    )

    assert response.status_code == 201
    row = row_by_id(inv_db, response.get_json()["invitacion"]["id"])
    assert row["tenant_id"] == TENANT_A
    assert row["creada_por"] == ADMIN_A.usuario_id
    assert invitaciones_de(inv_db, TENANT_B) == before_b


def test_admin_of_a_cannot_invite_in_b_with_a_forged_tenant(client, inv_db):
    """Token de ``ADMIN_A`` con ``tenant`` B (bien firmado): no hay membresía en B."""
    before = all_invitaciones(inv_db)

    response = client.post(
        INVITAR,
        json={"email": nuevo_email(), "rol": "admin", "tenant_id": str(TENANT_B)},
        headers={"Authorization": f"Bearer {access_token(ADMIN_A, TENANT_B, 'admin')}"},
    )

    assert response.status_code == 401
    assert all_invitaciones(inv_db) == before


def test_contador_cannot_create_even_with_a_valid_body(client, inv_db):
    before = all_invitaciones(inv_db)

    response = invitar(client, {"email": nuevo_email(), "rol": "contador"}, CONTADOR_A)

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "prohibido"
    assert "enlace" not in response.get_json()
    assert all_invitaciones(inv_db) == before


# --- Cuerpo inválido (400) -----------------------------------------------------------


INVALID_BODIES = {
    "lista": ["a@ejemplo.test", "contador"],
    "texto": "a@ejemplo.test",
    "nulo": None,
    "sin_email": {"rol": "contador"},
    "sin_rol": {"email": "sinrol@ejemplo.test"},
    "email_numero": {"email": 5, "rol": "contador"},
    "email_lista": {"email": ["a@ejemplo.test"], "rol": "contador"},
    "email_vacio": {"email": "   ", "rol": "contador"},
    "email_sin_arroba": {"email": "ejemplo.test", "rol": "contador"},
    "email_sin_local": {"email": "@ejemplo.test", "rol": "contador"},
    "email_sin_dominio": {"email": "a@", "rol": "contador"},
    "email_dos_arrobas": {"email": "a@b@ejemplo.test", "rol": "contador"},
    "email_con_espacio": {"email": "a b@ejemplo.test", "rol": "contador"},
    "email_con_nul": {"email": "a\x00@ejemplo.test", "rol": "contador"},
    "email_sustituto": {"email": "a\ud800@ejemplo.test", "rol": "contador"},
    "rol_desconocido": {"email": "x@ejemplo.test", "rol": "superadmin"},
    "rol_mayusculas": {"email": "x@ejemplo.test", "rol": "Admin"},
    "rol_vacio": {"email": "x@ejemplo.test", "rol": ""},
    "rol_numero": {"email": "x@ejemplo.test", "rol": 1},
}


@pytest.mark.parametrize("case", sorted(INVALID_BODIES))
def test_invalid_bodies_are_400_and_create_nothing(client, inv_db, case):
    before = all_invitaciones(inv_db)

    response = invitar(client, INVALID_BODIES[case])

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "solicitud_invalida"
    assert all_invitaciones(inv_db) == before


@pytest.mark.parametrize(
    ("data", "content_type"),
    [("{no es json", "application/json"), ("email=a@ejemplo.test", "text/plain"), ("", None)],
    ids=["json_invalido", "texto_plano", "sin_cuerpo"],
)
def test_non_json_bodies_are_400(client, inv_db, data, content_type):
    before = all_invitaciones(inv_db)
    headers = bearer(ADMIN_A, TENANT_A)
    if content_type is not None:
        headers["Content-Type"] = content_type

    response = client.post(INVITAR, data=data, headers=headers)

    assert response.status_code == 400
    assert all_invitaciones(inv_db) == before


def test_bodies_over_4_kb_are_413(client, inv_db):
    before = all_invitaciones(inv_db)
    body = {"email": nuevo_email(), "rol": "contador", "relleno": "x" * AUTH_MAX_BODY_BYTES}

    response = invitar(client, body)

    assert response.status_code == 413
    assert response.get_json()["error"]["code"] == "cuerpo_demasiado_grande"
    assert all_invitaciones(inv_db) == before


def test_only_post(client):
    for method in (client.get, client.put, client.patch, client.delete):
        assert method(INVITAR, headers=bearer(ADMIN_A, TENANT_A)).status_code == 405


@pytest.mark.parametrize("status_case", ["400", "401", "403"])
def test_error_responses_carry_no_store_and_no_referrer(client, status_case):
    if status_case == "400":
        response = invitar(client, {"email": "malo", "rol": "contador"})
    elif status_case == "401":
        response = client.post(INVITAR, json={"email": nuevo_email(), "rol": "contador"})
    else:
        response = invitar(client, {"email": nuevo_email(), "rol": "contador"}, CONTADOR_A)

    assert response.status_code == int(status_case)
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"


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


def test_invitation_tokens_never_reach_the_logs(inv_db, sqlalchemy_debug, caplog, capfd):
    flask_app = make_app(inv_db)
    try:
        client = flask_app.test_client(use_cookies=False)
        with caplog.at_level(logging.DEBUG):
            created = [
                invitar(client, {"email": nuevo_email(), "rol": rol})
                for rol in ("admin", "contador")
            ]
            invitar(client, {"email": nuevo_email(), "rol": "contador"}, CONTADOR_A)
            invitar(client, {"email": "malo", "rol": "contador"})
    finally:
        dispose(flask_app)

    assert [r.status_code for r in created] == [201, 201]
    secrets = []
    for response in created:
        token = token_of(response)
        stored = token_storage_hash(token)
        secrets += [token, token_key(token), stored.hex(), repr(stored)]
    out, err = capfd.readouterr()
    joined = "\n".join((caplog.text, out, err))
    assert [value for value in secrets if value in joined] == []
    assert "Row " not in joined
