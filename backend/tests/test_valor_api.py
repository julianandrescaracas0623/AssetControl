"""Valor actual del inventario (spec 008, T3; R8 de la spec, R7 de docs/03, P15/E2).

Consulta en vivo de ``activo``: cuentan ``activo`` y ``en_reparacion``; los dados de baja
no. Sigue los cambios al instante (a diferencia del informe congelado) y nunca lee el
desglose de una sesión. Solo admin. También cierra la prueba de A3 de la spec 005.
"""

import uuid
from collections.abc import Iterator
from decimal import Decimal

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


@pytest.fixture(scope="module")
def val_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("valor_api")


@pytest.fixture(scope="module")
def val_app(val_db) -> Iterator[Flask]:
    flask_app = make_app(val_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(val_app):
    return val_app.test_client(use_cookies=False)


def post(client, path, body, headers=ADMIN, version=None):
    extra = {"If-Match": str(version)} if version else {}
    response = client.post(path, json=body, headers={**headers, **extra})
    assert response.status_code in (200, 201), response.get_json()
    return response.get_json()


def test_real_time_value_follows_r7(client):
    sede = post(client, "/ubicaciones", {"nombre": "Sede", "tipo": "sede"})["ubicacion"]["id"]
    sala = post(
        client, "/ubicaciones", {"nombre": "Consultorios", "tipo": "sala", "padre_id": sede}
    )["ubicacion"]["id"]
    box = post(client, "/ubicaciones", {"nombre": "Box 1", "tipo": "box", "padre_id": sala})[
        "ubicacion"
    ]["id"]
    bio = post(client, "/categorias", {"nombre": "Biomédicos"})["categoria"]["id"]
    mob = post(client, "/categorias", {"nombre": "Mobiliario"})["categoria"]["id"]

    def activo(precio, categoria, ubicacion):
        body = {
            "id": str(uuid.uuid4()),
            "codigo": f"V-{uuid.uuid4().hex[:6]}".upper(),
            "nombre": "Activo",
            "precio_compra": precio,
            "categoria_id": categoria,
            "ubicacion_id": ubicacion,
        }
        return post(client, "/activos", body)["activo"]["id"]

    a = activo("100.50", bio, box)
    b = activo("200.00", mob, sala)
    c = activo("300.00", bio, sala)
    d = activo("400.00", mob, box)
    post(client, f"/activos/{b}/estado", {"estado": "en_reparacion"}, version=1)
    post(client, f"/activos/{d}/baja", {"motivo": "perdido"}, version=1)

    response = client.get("/valor-actual", headers=ADMIN)
    assert response.status_code == 200
    valor = response.get_json()
    assert valor["total"] == "600.50"  # a + b + c; d dado de baja no cuenta
    assert valor["unidades"] == 3
    assert valor["en_reparacion"] == {"valor": "200.00", "unidades": 1}
    cats = {f["etiqueta"]: f for f in valor["por_categoria"]}
    assert cats["Biomédicos"] == {
        "id": bio,
        "etiqueta": "Biomédicos",
        "valor": "400.50",
        "unidades": 2,
    }
    assert cats["Mobiliario"]["valor"] == "200.00"
    ubic = {f["etiqueta"]: f for f in valor["por_ubicacion"]}
    assert ubic["Consultorios › Box 1"]["valor"] == "100.50"
    assert ubic["Consultorios"]["unidades"] == 2
    for dimension in ("por_categoria", "por_ubicacion"):
        assert sum(Decimal(f["valor"]) for f in valor[dimension]) == Decimal(valor["total"])
    assert "calculado_en" in valor

    # Sigue los cambios al instante (no está congelado).
    post(client, f"/activos/{c}/estado", {"estado": "en_reparacion"}, version=1)
    client.patch(
        f"/activos/{a}", json={"precio_compra": "1.00"}, headers={**ADMIN, "If-Match": "1"}
    )
    despues = client.get("/valor-actual", headers=ADMIN).get_json()
    assert despues["total"] == "501.00"
    assert despues["en_reparacion"] == {"valor": "500.00", "unidades": 2}


def test_only_admin_and_own_tenant(client):
    assert client.get("/valor-actual", headers=CONTADOR).status_code == 403
    assert client.get("/valor-actual", headers={}).status_code == 401
    otro = client.get("/valor-actual", headers=ADMIN_OTRO).get_json()
    assert otro["total"] == "0.00"
    assert otro["por_categoria"] == []
