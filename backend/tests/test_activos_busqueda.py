"""Búsqueda, sugerencias y precio por rol (spec 004, T5; R5, R10, A2; plan.md §4).

- ``GET /activos``: por código, nombre o serial (sin distinguir mayúsculas), filtro por
  estado, 25 por página, lo más reciente primero; otro tenant invisible.
- ``GET /activos/sugerencias``: valores ya registrados de nombre, marca, modelo o
  subtipo, los más usados primero, hasta 8; nunca precio.
- **Ninguna respuesta al contador trae precio** (recorre todos los endpoints de
  activos con el contador).
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

ADMIN = bearer(ADMIN_A, TENANT_A)
CONTADOR = bearer(CONTADOR_A, TENANT_A, rol="contador")
ADMIN_OTRO = bearer(ADMIN_B, TENANT_B)

NOMBRES = ["Silla ergonómica"] * 3 + ["Silla de espera"] * 2 + ["Monitor 24"] + ["Autoclave 18 L"]


@pytest.fixture(scope="module")
def bus_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("activos_busqueda")


@pytest.fixture(scope="module")
def bus_app(bus_db) -> Iterator[Flask]:
    flask_app = make_app(bus_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(bus_app):
    return bus_app.test_client(use_cookies=False)


def _catalogo(client, headers) -> tuple[str, str]:
    sede = client.post("/ubicaciones", json={"nombre": "Sede", "tipo": "sede"}, headers=headers)
    sala = client.post(
        "/ubicaciones",
        json={"nombre": "Sala", "tipo": "sala", "padre_id": sede.get_json()["ubicacion"]["id"]},
        headers=headers,
    )
    cat = client.post("/categorias", json={"nombre": "Mobiliario"}, headers=headers)
    return sala.get_json()["ubicacion"]["id"], cat.get_json()["categoria"]["id"]


@pytest.fixture(scope="module")
def datos(bus_app) -> dict:
    client = bus_app.test_client(use_cookies=False)
    sala, cat = _catalogo(client, ADMIN)
    creados = []
    for indice, nombre in enumerate(NOMBRES):
        payload = {
            "id": str(uuid.uuid4()),
            "codigo": f"BUS-{indice:04d}",
            "nombre": nombre,
            "precio_compra": f"{1000 + indice}.00",
            "categoria_id": cat,
            "ubicacion_id": sala,
            "marca": "Rimax" if nombre.startswith("Silla") else None,
            "serial": f"SER_{indice}%" if indice == 6 else None,
        }
        response = client.post("/activos", json=payload, headers=ADMIN)
        assert response.status_code == 201, response.get_json()
        creados.append(payload)
    for indice in range(30):
        client.post(
            "/activos",
            json={
                "id": str(uuid.uuid4()),
                "codigo": f"LOTE-{indice:04d}",
                "nombre": "Archivador",
                "precio_compra": "10.00",
                "categoria_id": cat,
                "ubicacion_id": sala,
            },
            headers=ADMIN,
        )
    sala_b, cat_b = _catalogo(client, ADMIN_OTRO)
    client.post(
        "/activos",
        json={
            "id": str(uuid.uuid4()),
            "codigo": "BUS-B",
            "nombre": "Silla ergonómica",
            "precio_compra": "1.00",
            "categoria_id": cat_b,
            "ubicacion_id": sala_b,
        },
        headers=ADMIN_OTRO,
    )
    return {"creados": creados, "sala": sala, "cat": cat}


def buscar(client, headers=ADMIN, **params):
    response = client.get("/activos", query_string=params, headers=headers)
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def tiene_precio(valor) -> bool:
    if isinstance(valor, dict):
        return any("precio" in k or tiene_precio(v) for k, v in valor.items())
    if isinstance(valor, list):
        return any(tiene_precio(v) for v in valor)
    return False


def test_search_by_code_name_or_serial(client, datos):
    assert [a["codigo"] for a in buscar(client, q="bus-0006")["activos"]] == ["BUS-0006"]
    assert {a["codigo"] for a in buscar(client, q="SILLA")["activos"]} == {
        f"BUS-000{i}" for i in range(5)
    }
    # % y _ se buscan literalmente (no son comodines).
    assert [a["codigo"] for a in buscar(client, q="ser_6%")["activos"]] == ["BUS-0006"]
    assert buscar(client, q="ser%")["total"] == 0


def test_pagination_and_order(client, datos):
    primera = buscar(client)
    assert primera["total"] == len(NOMBRES) + 30
    assert primera["por_pagina"] == 25 and primera["pagina"] == 1
    assert len(primera["activos"]) == 25
    assert primera["activos"][0]["codigo"] == "LOTE-0029"  # lo más reciente primero
    segunda = buscar(client, pagina=2)
    assert len(segunda["activos"]) == len(NOMBRES) + 30 - 25
    assert not {a["id"] for a in primera["activos"]} & {a["id"] for a in segunda["activos"]}


def test_state_filter(client, datos):
    assert buscar(client, estado="activo")["total"] == len(NOMBRES) + 30
    assert buscar(client, estado="dado_de_baja")["total"] == 0


@pytest.mark.parametrize(
    "params",
    [{"estado": "otro"}, {"pagina": "0"}, {"pagina": "x"}, {"q": "x" * 121}],
)
def test_invalid_search_params_are_400(client, datos, params):
    response = client.get("/activos", query_string=params, headers=ADMIN)
    assert response.status_code == 400


def test_other_tenant_is_invisible(client, datos):
    assert "BUS-B" not in {a["codigo"] for a in buscar(client, q="silla")["activos"]}
    assert buscar(client, ADMIN_OTRO, q="silla")["total"] == 1


def test_suggestions_most_used_first(client, datos):
    response = client.get("/activos/sugerencias?campo=nombre&q=sil", headers=CONTADOR)
    assert response.status_code == 200
    assert response.get_json() == {"valores": ["Silla ergonómica", "Silla de espera"]}
    marcas = client.get("/activos/sugerencias?campo=marca", headers=ADMIN).get_json()["valores"]
    assert marcas == ["Rimax"]


@pytest.mark.parametrize("campo", ["precio_compra", "codigo", "", None])
def test_suggestions_only_for_allowed_fields(client, datos, campo):
    params = {"q": "a"} | ({"campo": campo} if campo is not None else {})
    response = client.get("/activos/sugerencias", query_string=params, headers=ADMIN)
    assert response.status_code == 400


def test_admin_sees_prices_in_the_list(client, datos):
    activo = buscar(client, q="BUS-0000")["activos"][0]
    assert activo["precio_compra"] == "1000.00"


def test_no_response_to_the_contador_has_a_price(client, datos):
    """A2/R5: recorre todas las lecturas y escrituras de activos con el contador."""
    origen = datos["creados"][0]
    nuevo = {
        "id": str(uuid.uuid4()),
        "codigo": f"CNT-{uuid.uuid4().hex[:6]}",
        "nombre": "Alta del contador",
        "precio_compra": "5.00",
        "categoria_id": datos["cat"],
        "ubicacion_id": datos["sala"],
    }
    respuestas = [
        client.get("/activos", headers=CONTADOR),
        client.get("/activos", query_string={"q": "silla", "pagina": 1}, headers=CONTADOR),
        client.get(f"/activos/{origen['id']}", headers=CONTADOR),
        client.get(
            "/activos/por-codigo", query_string={"codigo": origen["codigo"]}, headers=CONTADOR
        ),
        client.post("/activos", json=nuevo, headers=CONTADOR),
        client.post("/activos", json=nuevo, headers=CONTADOR),
        client.post(
            "/activos",
            json={
                "id": str(uuid.uuid4()),
                "codigo": f"CPY-{uuid.uuid4().hex[:6]}",
                "copiar_de": origen["id"],
            },
            headers=CONTADOR,
        ),
        client.post("/activos", json={**nuevo, "id": str(uuid.uuid4())}, headers=CONTADOR),  # 409
    ]
    respuestas += [
        client.get("/activos/sugerencias", query_string={"campo": c, "q": ""}, headers=CONTADOR)
        for c in ("nombre", "marca", "modelo", "subtipo")
    ]
    for response in respuestas:
        assert response.status_code < 500
        assert not tiene_precio(response.get_json()), response.get_json()
        assert "1000.00" not in response.get_data(as_text=True)
