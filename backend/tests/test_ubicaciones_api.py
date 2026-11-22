"""API de ubicaciones (spec 003, T2; R1–R5, Q1–Q3, A2; plan.md §3).

Sobre una base temporal migrada a ``head`` con dos tenants sintéticos (A y B):

- Jerarquía estricta: sede sin padre, sala bajo sede, box bajo sala (``400
  jerarquia_invalida`` en cada combinación inválida); padre inexistente o de otro
  tenant ``404``; padre inactivo ``409``.
- Nombres: regla H-3 (``400``) y únicos entre hermanas sin mayúsculas ni tildes
  (``409 nombre_duplicado``), también al renombrar.
- Desactivar con hijas activas ``409 tiene_hijas_activas``; reactivar con el padre
  inactivo ``409 padre_inactivo``.
- El contador lista solo activas y no escribe (``403``); un ``id`` de otro tenant es
  ``404`` para leer y escribir.
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

from app.auth.http import AUTH_MAX_BODY_BYTES

ADMIN = bearer(ADMIN_A, TENANT_A)
CONTADOR = bearer(CONTADOR_A, TENANT_A, rol="contador")
ADMIN_OTRO = bearer(ADMIN_B, TENANT_B)


@pytest.fixture(scope="module")
def ubi_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("ubicaciones")


@pytest.fixture(scope="module")
def ubi_app(ubi_db) -> Iterator[Flask]:
    flask_app = make_app(ubi_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture(autouse=True)
def vaciar(ubi_db) -> Iterator[None]:
    yield
    with ubi_db.migrator.begin() as conn:
        conn.execute(text("delete from ubicacion where padre_id is not null and tipo = 'box'"))
        conn.execute(text("delete from ubicacion where padre_id is not null"))
        conn.execute(text("delete from ubicacion"))


@pytest.fixture
def client(ubi_app):
    return ubi_app.test_client(use_cookies=False)


def crear(client, nombre, tipo, padre=None, headers=ADMIN):
    body = {"nombre": nombre, "tipo": tipo}
    if padre is not None:
        body["padre_id"] = padre
    return client.post("/ubicaciones", json=body, headers=headers)


def creada(client, nombre, tipo, padre=None, headers=ADMIN) -> str:
    response = crear(client, nombre, tipo, padre, headers)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["ubicacion"]["id"]


def patch(client, ubicacion_id, body, headers=ADMIN):
    return client.patch(f"/ubicaciones/{ubicacion_id}", json=body, headers=headers)


def code(response) -> str:
    return response.get_json()["error"]["code"]


def listar(client, headers=ADMIN) -> list[dict]:
    response = client.get("/ubicaciones", headers=headers)
    assert response.status_code == 200
    return response.get_json()["ubicaciones"]


# --- Crear y jerarquía (R2, Q1) ----------------------------------------------------


def test_creates_a_full_hierarchy(client):
    response = crear(client, "  Sede Norte ", "sede")
    assert response.status_code == 201
    sede = response.get_json()["ubicacion"]
    assert set(sede) == {"id", "nombre", "tipo", "padre_id", "activa"}
    assert sede["nombre"] == "Sede Norte"
    assert sede["tipo"] == "sede" and sede["padre_id"] is None and sede["activa"] is True
    sala = creada(client, "Consultorios", "sala", sede["id"])
    box = creada(client, "Box 2", "box", sala)

    filas = listar(client)
    assert [(u["nombre"], u["tipo"], u["padre_id"]) for u in filas] == [
        ("Sede Norte", "sede", None),
        ("Consultorios", "sala", sede["id"]),
        ("Box 2", "box", sala),
    ]
    assert filas[2]["id"] == box


@pytest.mark.parametrize(
    ("tipo", "padre_tipo"),
    [
        ("sede", "sede"),
        ("sala", None),
        ("sala", "sala"),
        ("box", None),
        ("box", "sede"),
        ("box", "box"),
    ],
)
def test_invalid_hierarchy_is_400(client, tipo, padre_tipo):
    sede = creada(client, "Sede", "sede")
    sala = creada(client, "Sala", "sala", sede)
    box = creada(client, "Box", "box", sala)
    padre = {"sede": sede, "sala": sala, "box": box, None: None}[padre_tipo]

    response = crear(client, "Nueva", tipo, padre)

    assert response.status_code == 400
    assert code(response) == "jerarquia_invalida"


@pytest.mark.parametrize(
    "body",
    [
        {"nombre": "X", "tipo": "piso"},
        {"nombre": "X"},
        {"tipo": "sede"},
        {"nombre": 5, "tipo": "sede"},
        {"nombre": "X", "tipo": "sala", "padre_id": 7},
        {"nombre": "​", "tipo": "sede"},
        {"nombre": "x" * 121, "tipo": "sede"},
        {"nombre": "Ana ‮serroT", "tipo": "sede"},
    ],
)
def test_malformed_body_or_name_is_400(client, body):
    response = client.post("/ubicaciones", json=body, headers=ADMIN)
    assert response.status_code == 400
    assert code(response) == "solicitud_invalida"


def test_non_json_body_is_400(client):
    response = client.post("/ubicaciones", data="x", headers=ADMIN, content_type="text/plain")
    assert response.status_code == 400


def test_big_body_is_413(client):
    response = client.post(
        "/ubicaciones", json={"nombre": "x" * AUTH_MAX_BODY_BYTES, "tipo": "sede"}, headers=ADMIN
    )
    assert response.status_code == 413


@pytest.mark.parametrize("padre", [str(uuid.uuid4()), "no-es-uuid"])
def test_unknown_parent_is_404(client, padre):
    response = crear(client, "Sala", "sala", padre)
    assert response.status_code == 404
    assert code(response) == "no_encontrado"


def test_parent_of_another_tenant_is_404(client):
    sede_b = creada(client, "Sede B", "sede", headers=ADMIN_OTRO)
    response = crear(client, "Sala", "sala", sede_b)
    assert response.status_code == 404
    assert code(response) == "no_encontrado"


def test_inactive_parent_is_409(client):
    sede = creada(client, "Sede", "sede")
    assert patch(client, sede, {"activa": False}).status_code == 200
    response = crear(client, "Sala", "sala", sede)
    assert response.status_code == 409
    assert code(response) == "padre_inactivo"


# --- Nombres únicos (R3, Q3) ------------------------------------------------------------


@pytest.mark.parametrize("repetido", ["Consultorio Uno", "CONSULTORIO UNO", "Consultorío  Uno"])
def test_duplicate_sibling_names_are_409(client, repetido):
    sede = creada(client, "Sede", "sede")
    creada(client, "Consultorio Uno", "sala", sede)
    response = crear(client, repetido, "sala", sede)
    assert response.status_code == 409
    assert code(response) == "nombre_duplicado"


def test_same_name_is_allowed_under_another_parent_or_tenant(client):
    norte = creada(client, "Norte", "sede")
    sur = creada(client, "Sur", "sede")
    creada(client, "Recepción", "sala", norte)
    creada(client, "Recepción", "sala", sur)
    creada(client, "Norte", "sede", headers=ADMIN_OTRO)
    assert crear(client, "norte", "sede").status_code == 409


def test_rename_and_its_duplicate(client):
    sede = creada(client, "Sede", "sede")
    a = creada(client, "Sala A", "sala", sede)
    creada(client, "Sala B", "sala", sede)

    renombrada = patch(client, a, {"nombre": "  Sala Á "})
    assert renombrada.status_code == 200
    assert renombrada.get_json()["ubicacion"]["nombre"] == "Sala Á"
    assert patch(client, a, {"nombre": "sala a"}).status_code == 200  # misma clave: permitido

    duplicada = patch(client, a, {"nombre": "SALA B"})
    assert duplicada.status_code == 409
    assert code(duplicada) == "nombre_duplicado"


@pytest.mark.parametrize(
    "body",
    [{}, {"otro": 1}, {"activa": "no"}, {"activa": 1}, {"nombre": ""}, {"nombre": None, "x": 1}],
)
def test_patch_needs_a_valid_change(client, body):
    sede = creada(client, "Sede", "sede")
    response = patch(client, sede, body)
    assert response.status_code == 400
    assert code(response) == "solicitud_invalida"


# --- Desactivar y reactivar (R4, Q2) ---------------------------------------------------


def test_deactivate_with_active_children_is_409_and_in_order_works(client):
    sede = creada(client, "Sede", "sede")
    sala = creada(client, "Sala", "sala", sede)
    box = creada(client, "Box", "box", sala)

    for padre in (sede, sala):
        response = patch(client, padre, {"activa": False})
        assert response.status_code == 409
        assert code(response) == "tiene_hijas_activas"

    for ubicacion in (box, sala, sede):
        response = patch(client, ubicacion, {"activa": False})
        assert response.status_code == 200
        assert response.get_json()["ubicacion"]["activa"] is False


def test_reactivate_needs_an_active_parent(client):
    sede = creada(client, "Sede", "sede")
    sala = creada(client, "Sala", "sala", sede)
    patch(client, sala, {"activa": False})
    patch(client, sede, {"activa": False})

    response = patch(client, sala, {"activa": True})
    assert response.status_code == 409
    assert code(response) == "padre_inactivo"

    assert patch(client, sede, {"activa": True}).status_code == 200
    assert patch(client, sala, {"activa": True}).status_code == 200


# --- Roles y aislamiento (R1, R5) -----------------------------------------------------


def test_contador_lists_only_active_and_admin_lists_all(client):
    sede = creada(client, "Sede", "sede")
    activa = creada(client, "Activa", "sala", sede)
    inactiva = creada(client, "Inactiva", "sala", sede)
    patch(client, inactiva, {"activa": False})

    assert {u["id"] for u in listar(client)} == {sede, activa, inactiva}
    assert {u["id"] for u in listar(client, CONTADOR)} == {sede, activa}


def test_contador_cannot_write(client):
    sede = creada(client, "Sede", "sede")
    for response in (
        crear(client, "Otra", "sede", headers=CONTADOR),
        patch(client, sede, {"nombre": "X"}, headers=CONTADOR),
        patch(client, sede, {"activa": False}, headers=CONTADOR),
    ):
        assert response.status_code == 403
        assert code(response) == "prohibido"
    assert [u["nombre"] for u in listar(client)] == ["Sede"]


def test_other_tenant_rows_are_invisible_and_404(client):
    sede_b = creada(client, "Sede B", "sede", headers=ADMIN_OTRO)
    creada(client, "Sede A", "sede")

    assert [u["nombre"] for u in listar(client)] == ["Sede A"]
    for body in ({"nombre": "Robada"}, {"activa": False}):
        response = patch(client, sede_b, body)
        assert response.status_code == 404
        assert code(response) == "no_encontrado"
    assert [u["nombre"] for u in listar(client, ADMIN_OTRO)] == ["Sede B"]
    assert listar(client, ADMIN_OTRO)[0]["activa"] is True


def test_unknown_id_is_404(client):
    assert patch(client, uuid.uuid4(), {"nombre": "X"}).status_code == 404
    assert client.patch("/ubicaciones/no-es-uuid", json={}, headers=ADMIN).status_code == 404


def test_anonymous_is_401(client):
    for response in (
        client.get("/ubicaciones"),
        client.post("/ubicaciones", json={"nombre": "X", "tipo": "sede"}),
        client.patch(f"/ubicaciones/{uuid.uuid4()}", json={"nombre": "X"}),
    ):
        assert response.status_code == 401
        assert code(response) == "no_autenticado"
