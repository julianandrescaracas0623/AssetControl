"""API ``GET /usuarios`` (lista de usuarios de la empresa, solo admin).

- El admin ve a los usuarios de su empresa con rol, estado de la membresía y si debe
  cambiar la contraseña.
- Nunca aparece un usuario de otra empresa (RLS) ni un campo de contraseña.
- El contador recibe ``403`` y sin sesión ``401``.
"""

from collections.abc import Iterator

import pytest
from acceso_db import (
    ADMIN_A,
    ADMIN_B,
    CONTADOR_A,
    CONTADOR_B,
    TENANT_A,
    AccesoDb,
    bearer,
    dispose,
    make_app,
    migrator_execute,
    temporary_acceso_db,
)
from flask import Flask

ADMIN = bearer(ADMIN_A, TENANT_A)
CONTADOR = bearer(CONTADOR_A, TENANT_A, rol="contador")


@pytest.fixture(scope="module")
def usuarios_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("usuarios")


@pytest.fixture(scope="module")
def usuarios_app(usuarios_db) -> Iterator[Flask]:
    flask_app = make_app(usuarios_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(usuarios_app):
    return usuarios_app.test_client(use_cookies=False)


def test_admin_ve_solo_los_usuarios_de_su_empresa(client):
    respuesta = client.get("/usuarios", headers=ADMIN)
    assert respuesta.status_code == 200
    usuarios = respuesta.get_json()["usuarios"]
    ids = {u["id"] for u in usuarios}
    assert str(ADMIN_A.usuario_id) in ids
    assert str(CONTADOR_A.usuario_id) in ids
    assert str(ADMIN_B.usuario_id) not in ids
    assert str(CONTADOR_B.usuario_id) not in ids


def test_cada_fila_trae_rol_estado_y_ningun_secreto(client):
    usuarios = client.get("/usuarios", headers=ADMIN).get_json()["usuarios"]
    contador = next(u for u in usuarios if u["id"] == str(CONTADOR_A.usuario_id))
    assert set(contador) == {"id", "nombre", "email", "rol", "activa", "debe_cambiar_password"}
    assert contador["rol"] == "contador"
    assert contador["activa"] is True
    assert contador["email"] == CONTADOR_A.email
    assert all(clave not in {"password", "password_hash", "hash"} for u in usuarios for clave in u)


def test_membresia_desactivada_aparece_con_activa_falsa(usuarios_db, client):
    migrator_execute(
        usuarios_db,
        "UPDATE membresia SET activa = false WHERE usuario_id = :u",
        {"u": CONTADOR_A.usuario_id},
    )
    try:
        usuarios = client.get("/usuarios", headers=ADMIN).get_json()["usuarios"]
        contador = next(u for u in usuarios if u["id"] == str(CONTADOR_A.usuario_id))
        assert contador["activa"] is False
    finally:
        migrator_execute(
            usuarios_db,
            "UPDATE membresia SET activa = true WHERE usuario_id = :u",
            {"u": CONTADOR_A.usuario_id},
        )


def test_contador_recibe_403(client):
    assert client.get("/usuarios", headers=CONTADOR).status_code == 403


def test_sin_sesion_recibe_401(client):
    assert client.get("/usuarios").status_code == 401
