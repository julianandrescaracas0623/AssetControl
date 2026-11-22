"""API de categorías (spec 003, T3; R1, R3, R5, R6, Q3–Q4, A2; plan.md §3).

- Crear y renombrar con la regla H-3 y nombres únicos en el tenant sin mayúsculas ni
  tildes (``409 nombre_duplicado``).
- "Cargar las sugeridas" crea solo las que faltan de la lista de P8 y repetirlo no
  cambia nada.
- Ambos roles listan; solo el admin escribe (``403``); otro tenant es invisible y su
  ``id`` es ``404``.
"""

import uuid
from collections.abc import Iterator

import pytest
from acceso_db import (
    ADMIN_A,
    ADMIN_B,
    CONTADOR_A,
    TENANT_A,
    TENANT_B,
    AccesoDb,
    bearer,
    dispose,
    make_app,
    temporary_acceso_db,
)
from flask import Flask
from sqlalchemy import text

from app.catalogo.service import CATEGORIAS_SUGERIDAS

ADMIN = bearer(ADMIN_A, TENANT_A)
CONTADOR = bearer(CONTADOR_A, TENANT_A, rol="contador")
ADMIN_OTRO = bearer(ADMIN_B, TENANT_B)


@pytest.fixture(scope="module")
def cat_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("categorias")


@pytest.fixture(scope="module")
def cat_app(cat_db) -> Iterator[Flask]:
    flask_app = make_app(cat_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture(autouse=True)
def vaciar(cat_db) -> Iterator[None]:
    yield
    with cat_db.migrator.begin() as conn:
        conn.execute(text("delete from categoria"))


@pytest.fixture
def client(cat_app):
    return cat_app.test_client(use_cookies=False)


def crear(client, nombre, headers=ADMIN):
    return client.post("/categorias", json={"nombre": nombre}, headers=headers)


def creada(client, nombre, headers=ADMIN) -> str:
    response = crear(client, nombre, headers)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["categoria"]["id"]


def nombres(client, headers=ADMIN) -> list[str]:
    response = client.get("/categorias", headers=headers)
    assert response.status_code == 200
    return [c["nombre"] for c in response.get_json()["categorias"]]


def code(response) -> str:
    return response.get_json()["error"]["code"]


def test_create_list_and_rename(client):
    response = crear(client, "  Equipo médico ")
    assert response.status_code == 201
    categoria = response.get_json()["categoria"]
    assert set(categoria) == {"id", "nombre"}
    assert categoria["nombre"] == "Equipo médico"
    creada(client, "Aseo")

    assert nombres(client) == ["Aseo", "Equipo médico"]
    assert nombres(client, CONTADOR) == ["Aseo", "Equipo médico"]

    renombrada = client.patch(
        f"/categorias/{categoria['id']}", json={"nombre": "Biomédicos"}, headers=ADMIN
    )
    assert renombrada.status_code == 200
    assert renombrada.get_json()["categoria"] == {"id": categoria["id"], "nombre": "Biomédicos"}


@pytest.mark.parametrize("repetido", ["Mobiliario", "MOBILIARIO", "Mobiliário", " mobiliario "])
def test_duplicates_are_409(client, repetido):
    creada(client, "Mobiliario")
    response = crear(client, repetido)
    assert response.status_code == 409
    assert code(response) == "nombre_duplicado"


def test_rename_to_an_existing_name_is_409(client):
    creada(client, "CPU")
    otra = creada(client, "Periféricos")
    response = client.patch(f"/categorias/{otra}", json={"nombre": "cpu"}, headers=ADMIN)
    assert response.status_code == 409
    assert code(response) == "nombre_duplicado"


@pytest.mark.parametrize("nombre", ["", "​", "x" * 121, 5, None, "..."])
def test_invalid_names_are_400(client, nombre):
    response = crear(client, nombre)
    assert response.status_code == 400
    assert code(response) == "solicitud_invalida"


def test_suggested_are_created_once(client):
    creada(client, "biomedicos")  # ya existe con otra forma: no se duplica

    primera = client.post("/categorias/sugeridas", headers=ADMIN)
    assert primera.status_code == 200
    body = primera.get_json()
    assert body["creadas"] == len(CATEGORIAS_SUGERIDAS) - 1
    assert len(body["categorias"]) == len(CATEGORIAS_SUGERIDAS)
    assert "biomedicos" in [c["nombre"] for c in body["categorias"]]

    segunda = client.post("/categorias/sugeridas", headers=ADMIN)
    assert segunda.get_json()["creadas"] == 0
    assert segunda.get_json()["categorias"] == body["categorias"]


def test_suggested_list_is_p8():
    assert CATEGORIAS_SUGERIDAS == (
        "Mobiliario",
        "Electrónica",
        "CPU",
        "Periféricos",
        "Electrodomésticos",
        "Biomédicos",
    )


def test_contador_cannot_write(client):
    categoria = creada(client, "Aseo")
    for response in (
        crear(client, "Otra", headers=CONTADOR),
        client.patch(f"/categorias/{categoria}", json={"nombre": "X"}, headers=CONTADOR),
        client.post("/categorias/sugeridas", headers=CONTADOR),
    ):
        assert response.status_code == 403
        assert code(response) == "prohibido"
    assert nombres(client) == ["Aseo"]


def test_other_tenant_is_invisible_and_404(client):
    de_b = creada(client, "Solo B", headers=ADMIN_OTRO)
    creada(client, "Solo A")
    client.post("/categorias/sugeridas", headers=ADMIN_OTRO)

    assert nombres(client) == ["Solo A"]
    response = client.patch(f"/categorias/{de_b}", json={"nombre": "Robada"}, headers=ADMIN)
    assert response.status_code == 404
    assert code(response) == "no_encontrado"
    assert "Solo B" in nombres(client, ADMIN_OTRO)


def test_unknown_id_is_404_and_anonymous_is_401(client):
    response = client.patch(f"/categorias/{uuid.uuid4()}", json={"nombre": "X"}, headers=ADMIN)
    assert response.status_code == 404
    for response in (
        client.get("/categorias"),
        client.post("/categorias", json={"nombre": "X"}),
        client.post("/categorias/sugeridas"),
    ):
        assert response.status_code == 401
