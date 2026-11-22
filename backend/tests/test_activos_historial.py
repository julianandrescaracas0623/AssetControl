"""Historial de un activo y filtro por ubicación (spec 005, T4; R8, R10, A2; plan.md §4).

- ``GET /activos/{id}/historial``: ambos roles; ``seq`` descendente, 50 por página con
  ``siguiente``; autor con su nombre. Al contador el servidor le omite los
  ``precio_cambiado`` y le quita todo precio de los demás eventos (P13); la paginación
  se calcula sobre lo que ve cada rol.
- ``GET /activos?ubicacion_id=``: solo los activos de esa ubicación (R10, D2).
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


@pytest.fixture(scope="module")
def his_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("activos_historial")


@pytest.fixture(scope="module")
def his_app(his_db) -> Iterator[Flask]:
    flask_app = make_app(his_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(his_app):
    return his_app.test_client(use_cookies=False)


@pytest.fixture(scope="module")
def cat(his_app) -> dict[str, str]:
    client = his_app.test_client(use_cookies=False)

    def post(path, body, headers=ADMIN):
        response = client.post(path, json=body, headers=headers)
        assert response.status_code == 201, response.get_json()
        return response.get_json()

    sede = post("/ubicaciones", {"nombre": "Sede", "tipo": "sede"})["ubicacion"]["id"]
    sala = post("/ubicaciones", {"nombre": "Consultorios", "tipo": "sala", "padre_id": sede})
    otra = post("/ubicaciones", {"nombre": "Bodega", "tipo": "sala", "padre_id": sede})
    sede_b = post("/ubicaciones", {"nombre": "Sede B", "tipo": "sede"}, ADMIN_OTRO)
    return {
        "sede": sede,
        "sala": sala["ubicacion"]["id"],
        "otra": otra["ubicacion"]["id"],
        "sede_b": sede_b["ubicacion"]["id"],
        "cat": post("/categorias", {"nombre": "Biomédicos"})["categoria"]["id"],
        "cat2": post("/categorias", {"nombre": "Muebles"})["categoria"]["id"],
    }


def nuevo(client, cat, headers=CONTADOR, **cambios) -> dict:
    body = {
        "id": str(uuid.uuid4()),
        "codigo": f"H-{uuid.uuid4().hex[:8].upper()}",
        "nombre": "Silla ergonómica",
        "precio_compra": "389900.00",
        "categoria_id": cat["cat"],
        "ubicacion_id": cat["sala"],
        **cambios,
    }
    response = client.post("/activos", json=body, headers=headers)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["activo"]


def cambio(client, metodo, ruta, body, v):
    response = client.open(ruta, method=metodo, json=body, headers={**ADMIN, "If-Match": str(v)})
    assert response.status_code == 200, response.get_json()


def historial(client, activo_id, headers=ADMIN, **params):
    return client.get(f"/activos/{activo_id}/historial", query_string=params, headers=headers)


def tiene_precio(valor) -> bool:
    if isinstance(valor, dict):
        return any("precio" in k or tiene_precio(v) for k, v in valor.items())
    if isinstance(valor, list):
        return any(tiene_precio(v) for v in valor)
    if isinstance(valor, str):
        return "389900" in valor or "500000" in valor
    return False


@pytest.fixture(scope="module")
def con_vida(his_app, cat) -> dict:
    """Un activo con un evento de cada tipo de la 005 (alta del contador)."""
    client = his_app.test_client(use_cookies=False)
    activo = nuevo(client, cat)
    ruta = f"/activos/{activo['id']}"
    cambio(client, "PATCH", ruta, {"precio_compra": "500000.00"}, 1)
    cambio(client, "PATCH", ruta, {"categoria_id": cat["cat2"], "marca": "Rimax"}, 2)
    cambio(client, "POST", f"{ruta}/mover", {"ubicacion_id": cat["otra"]}, 3)
    cambio(client, "POST", f"{ruta}/estado", {"estado": "en_reparacion"}, 4)
    cambio(client, "POST", f"{ruta}/baja", {"motivo": "perdido"}, 5)
    cambio(client, "POST", f"{ruta}/estado", {"estado": "activo", "motivo": "encontrado"}, 6)
    return activo


def test_admin_sees_the_whole_timeline_newest_first(client, con_vida):
    response = historial(client, con_vida["id"])
    assert response.status_code == 200
    cuerpo = response.get_json()
    tipos = [e["tipo"] for e in cuerpo["eventos"]]
    assert tipos == [
        "estado_cambiado",
        "dado_de_baja",
        "estado_cambiado",
        "ubicacion_cambiada",
        "datos_cambiados",
        "categoria_cambiada",
        "precio_cambiado",
        "creado",
    ]
    assert cuerpo["siguiente"] is None
    seqs = [e["seq"] for e in cuerpo["eventos"]]
    assert seqs == sorted(seqs, reverse=True)
    precio = cuerpo["eventos"][6]
    assert precio["datos"] == {"antes": "389900.00", "despues": "500000.00"}
    assert precio["autor"] == {"id": str(ADMIN_A.usuario_id), "nombre": "Ana"}
    creado = cuerpo["eventos"][-1]
    assert creado["autor"] == {"id": str(CONTADOR_A.usuario_id), "nombre": "Carlos"}
    assert creado["datos"]["precio_compra"] == "389900.00"
    assert "ocurrido_en" in creado


def test_counter_never_sees_prices_in_the_timeline(client, con_vida):
    response = historial(client, con_vida["id"], headers=CONTADOR)
    assert response.status_code == 200
    cuerpo = response.get_json()
    tipos = [e["tipo"] for e in cuerpo["eventos"]]
    assert "precio_cambiado" not in tipos
    assert tipos[-1] == "creado"
    assert len(tipos) == 7
    assert not tiene_precio(cuerpo)


def test_pages_of_fifty_with_a_cursor(client, cat):
    activo = nuevo(client, cat, headers=ADMIN)
    ruta = f"/activos/{activo['id']}"
    for v in range(1, 55):
        cambio(client, "PATCH", ruta, {"nombre": f"Nombre {v}"}, v)
    for v in range(55, 58):
        cambio(client, "PATCH", ruta, {"precio_compra": f"{v}.00"}, v)

    primera = historial(client, activo["id"]).get_json()
    assert len(primera["eventos"]) == 50
    segunda = historial(client, activo["id"], antes_de=primera["siguiente"]).get_json()
    assert len(segunda["eventos"]) == 8
    assert segunda["siguiente"] is None
    vistos = [e["seq"] for e in primera["eventos"] + segunda["eventos"]]
    assert len(set(vistos)) == 58
    assert vistos == sorted(vistos, reverse=True)

    # El contador pagina sobre lo que ve: 54 cambios de nombre y el alta.
    c1 = historial(client, activo["id"], headers=CONTADOR).get_json()
    c2 = historial(client, activo["id"], headers=CONTADOR, antes_de=c1["siguiente"]).get_json()
    assert len(c1["eventos"]) == 50
    assert len(c2["eventos"]) == 5
    assert not tiene_precio(c1) and not tiene_precio(c2)


@pytest.mark.parametrize("antes_de", ["x", "0", "-3", "1.5", "9" * 20])
def test_bad_cursor_is_400(client, con_vida, antes_de):
    assert historial(client, con_vida["id"], antes_de=antes_de).status_code == 400


def test_history_is_tenant_scoped_and_needs_a_session(client, con_vida):
    assert historial(client, con_vida["id"], headers=ADMIN_OTRO).status_code == 404
    assert historial(client, str(uuid.uuid4())).status_code == 404
    assert historial(client, con_vida["id"], headers={}).status_code == 401


# --- Filtro por ubicación (R10) ---------------------------------------------------------


def test_search_filters_by_location(client, cat):
    rayos = client.post(
        "/ubicaciones",
        json={"nombre": f"Rayos {uuid.uuid4().hex[:4]}", "tipo": "sala", "padre_id": cat["sede"]},
        headers=ADMIN,
    ).get_json()["ubicacion"]["id"]
    uno = nuevo(client, cat, ubicacion_id=rayos)
    dos = nuevo(client, cat, ubicacion_id=rayos)
    nuevo(client, cat)

    for headers in (ADMIN, CONTADOR):
        cuerpo = client.get(
            "/activos", query_string={"ubicacion_id": rayos}, headers=headers
        ).get_json()
        assert cuerpo["total"] == 2
        assert {a["id"] for a in cuerpo["activos"]} == {uno["id"], dos["id"]}

    vacia = client.get("/activos", query_string={"ubicacion_id": cat["sede_b"]}, headers=ADMIN)
    assert vacia.get_json()["total"] == 0
    malo = client.get("/activos", query_string={"ubicacion_id": "x"}, headers=ADMIN)
    assert malo.status_code == 400
