"""API de alta, resolución y ficha de activos (spec 004, T3; R1–R8, A2, A3; plan.md §4).

Sobre una base temporal con dos tenants (A y B) y un catálogo sintético:

- Alta de ambos roles (P11) con código en mayúsculas, precio en texto canónico y evento
  ``creado``; reintento con el mismo ``id`` devuelve el guardado (R4).
- Código repetido ``409 codigo_existente`` con el activo; formato ``400``.
- Precio: el admin lo ve, el contador **nunca** (la clave no existe).
- D1: una sede o una ubicación inactiva ``400 ubicacion_invalida``; referencias de otro
  tenant ``404``.
- D2: desactivar una ubicación con activos ``409 tiene_activos``; con solo dados de baja,
  se permite.
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

ADMIN = bearer(ADMIN_A, TENANT_A)
CONTADOR = bearer(CONTADOR_A, TENANT_A, rol="contador")
ADMIN_OTRO = bearer(ADMIN_B, TENANT_B)


@pytest.fixture(scope="module")
def act_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("activos_api")


@pytest.fixture(scope="module")
def act_app(act_db) -> Iterator[Flask]:
    flask_app = make_app(act_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(act_app):
    return act_app.test_client(use_cookies=False)


@pytest.fixture(scope="module")
def cat(act_app) -> dict[str, str]:
    """Catálogo creado por la API: sede > sala > box, otra sala y una categoría por tenant."""
    client = act_app.test_client(use_cookies=False)

    def ubicacion(nombre, tipo, padre=None, headers=ADMIN):
        body = {"nombre": nombre, "tipo": tipo, **({"padre_id": padre} if padre else {})}
        response = client.post("/ubicaciones", json=body, headers=headers)
        assert response.status_code == 201, response.get_json()
        return response.get_json()["ubicacion"]["id"]

    sede = ubicacion("Sede", "sede")
    sala = ubicacion("Consultorios", "sala", sede)
    ids = {
        "sede": sede,
        "sala": sala,
        "box": ubicacion("Box 2", "box", sala),
        "otra_sala": ubicacion("Bodega", "sala", sede),
        "sede_b": ubicacion("Sede B", "sede", headers=ADMIN_OTRO),
    }
    ids["sala_b"] = ubicacion("Sala B", "sala", ids["sede_b"], headers=ADMIN_OTRO)
    for clave, headers in (("cat", ADMIN), ("cat_b", ADMIN_OTRO)):
        response = client.post("/categorias", json={"nombre": "Biomédicos"}, headers=headers)
        ids[clave] = response.get_json()["categoria"]["id"]
    return ids


def body(cat, **cambios) -> dict:
    base = {
        "id": str(uuid.uuid4()),
        "codigo": f"ac-{uuid.uuid4().hex[:8]}",
        "nombre": "Autoclave clase B 18 L",
        "precio_compra": "14200000.00",
        "categoria_id": cat["cat"],
        "ubicacion_id": cat["box"],
    }
    return {**base, **cambios}


def alta(client, payload, headers=ADMIN):
    return client.post("/activos", json=payload, headers=headers)


def code(response) -> str:
    return response.get_json()["error"]["code"]


def tiene_precio(valor) -> bool:
    if isinstance(valor, dict):
        return any("precio" in k or tiene_precio(v) for k, v in valor.items())
    if isinstance(valor, list):
        return any(tiene_precio(v) for v in valor)
    return False


# --- Alta (R3, R4) ---------------------------------------------------------------------


def test_admin_creates_and_sees_the_price(client, cat, act_db):
    payload = body(cat, serial=" SN-1 ", marca="Tuttnauer", fecha_compra="2024-03-01")
    response = alta(client, payload)

    assert response.status_code == 201, response.get_json()
    activo = response.get_json()["activo"]
    assert activo["codigo"] == payload["codigo"].upper()
    assert activo["precio_compra"] == "14200000.00"
    assert activo["estado"] == "activo"
    assert activo["serial"] == "SN-1" and activo["marca"] == "Tuttnauer"
    assert activo["modelo"] is None and activo["subtipo"] is None
    assert activo["fecha_compra"] == "2024-03-01"
    assert activo["categoria"] == {"id": cat["cat"], "nombre": "Biomédicos"}
    assert activo["ubicacion"] == {
        "id": cat["box"],
        "nombre": "Box 2",
        "ruta": "Consultorios › Box 2",
    }

    with act_db.migrator.connect() as conn:
        evento = conn.execute(
            text("select tipo, usuario_id, datos from activo_evento where activo_id = :id"),
            {"id": payload["id"]},
        ).one()
    assert evento.tipo == "creado"
    assert evento.usuario_id == ADMIN_A.usuario_id
    assert evento.datos["precio_compra"] == "14200000.00"


def test_contador_creates_and_never_sees_the_price(client, cat):
    payload = body(cat)
    response = alta(client, payload, CONTADOR)
    assert response.status_code == 201
    assert not tiene_precio(response.get_json())

    for respuesta in (
        alta(client, payload, CONTADOR),  # reintento
        client.get(f"/activos/{payload['id']}", headers=CONTADOR),
        client.get(f"/activos/por-codigo?codigo={payload['codigo']}", headers=CONTADOR),
    ):
        assert respuesta.status_code == 200
        assert not tiene_precio(respuesta.get_json())

    admin = client.get(f"/activos/{payload['id']}", headers=ADMIN).get_json()["activo"]
    assert admin["precio_compra"] == "14200000.00"


def test_retry_with_the_same_id_returns_the_saved_one(client, cat, act_db):
    payload = body(cat)
    primera = alta(client, payload)
    segunda = alta(client, {**payload, "nombre": "Otro nombre"})

    assert primera.status_code == 201
    assert segunda.status_code == 200
    assert segunda.get_json()["activo"] == primera.get_json()["activo"]
    with act_db.migrator.connect() as conn:
        assert (
            conn.scalar(text("select count(*) from activo where id = :id"), {"id": payload["id"]})
            == 1
        )
        assert (
            conn.scalar(
                text("select count(*) from activo_evento where activo_id = :id"),
                {"id": payload["id"]},
            )
            == 1
        )


def test_same_id_with_another_code_is_400(client, cat):
    payload = body(cat)
    alta(client, payload)
    response = alta(client, {**payload, "codigo": "OTRO-1"})
    assert response.status_code == 400
    assert code(response) == "solicitud_invalida"


def test_duplicate_code_is_409_with_the_existing_asset(client, cat):
    original = body(cat, codigo="DUP-0001")
    alta(client, original)
    response = alta(client, body(cat, codigo=" dup-0001 "))

    assert response.status_code == 409
    cuerpo = response.get_json()
    assert cuerpo["error"]["code"] == "codigo_existente"
    assert cuerpo["activo"] == {
        "id": original["id"],
        "codigo": "DUP-0001",
        "nombre": original["nombre"],
    }


@pytest.mark.parametrize(
    ("cambio", "codigo_error"),
    [
        ({"codigo": "con espacio"}, "codigo_invalido"),
        ({"codigo": "ñ-1"}, "codigo_invalido"),
        ({"codigo": None}, "codigo_invalido"),
        ({"precio_compra": "-1"}, "precio_invalido"),
        ({"precio_compra": 1000}, "precio_invalido"),
        ({"precio_compra": 1000.5}, "precio_invalido"),
        ({"precio_compra": "1.390.000"}, "precio_invalido"),
        ({"precio_compra": None}, "precio_invalido"),
        ({"nombre": ""}, "solicitud_invalida"),
        ({"nombre": "​"}, "solicitud_invalida"),
        ({"id": "no-uuid"}, "solicitud_invalida"),
        ({"categoria_id": None}, "solicitud_invalida"),
        ({"serial": "‮"}, "solicitud_invalida"),
        ({"fecha_compra": "2024-13-01"}, "solicitud_invalida"),
        ({"fecha_compra": "2999-01-01"}, "solicitud_invalida"),
    ],
)
def test_invalid_bodies_are_400(client, cat, cambio, codigo_error):
    response = alta(client, body(cat, **cambio))
    assert response.status_code == 400
    assert code(response) == codigo_error


@pytest.mark.parametrize("ubicacion", ["sede", "otra_inactiva"])
def test_d1_a_sede_or_an_inactive_location_is_400(client, cat, ubicacion):
    if ubicacion == "otra_inactiva":
        sala = client.post(
            "/ubicaciones",
            json={
                "nombre": f"Cerrada {uuid.uuid4().hex[:4]}",
                "tipo": "sala",
                "padre_id": cat["sede"],
            },
            headers=ADMIN,
        ).get_json()["ubicacion"]["id"]
        client.patch(f"/ubicaciones/{sala}", json={"activa": False}, headers=ADMIN)
        destino = sala
    else:
        destino = cat["sede"]
    response = alta(client, body(cat, ubicacion_id=destino))
    assert response.status_code == 400
    assert code(response) == "ubicacion_invalida"


@pytest.mark.parametrize("campo", ["ubicacion_id", "categoria_id"])
def test_references_of_another_tenant_are_404(client, cat, campo):
    otro = {"ubicacion_id": cat["sala_b"], "categoria_id": cat["cat_b"]}[campo]
    response = alta(client, body(cat, **{campo: otro}))
    assert response.status_code == 404
    assert code(response) == "no_encontrado"


def test_same_code_in_another_tenant_is_allowed(client, cat):
    alta(client, body(cat, codigo="COMPARTIDO-1"))
    response = alta(
        client,
        body(cat, codigo="COMPARTIDO-1", categoria_id=cat["cat_b"], ubicacion_id=cat["sala_b"]),
        ADMIN_OTRO,
    )
    assert response.status_code == 201


# --- Resolver y ficha (R1) ---------------------------------------------------------------


def test_resolve_by_code_normalizes_and_isolates(client, cat):
    payload = body(cat, codigo="RES/0001")
    alta(client, payload)

    encontrado = client.get("/activos/por-codigo?codigo=res/0001", headers=ADMIN)
    assert encontrado.status_code == 200
    assert encontrado.get_json()["activo"]["id"] == payload["id"]

    assert client.get("/activos/por-codigo?codigo=NO-EXISTE", headers=ADMIN).status_code == 404
    assert client.get("/activos/por-codigo?codigo=RES/0001", headers=ADMIN_OTRO).status_code == 404
    invalido = client.get("/activos/por-codigo?codigo=con espacio", headers=ADMIN)
    assert invalido.status_code == 400 and code(invalido) == "codigo_invalido"
    assert client.get("/activos/por-codigo", headers=ADMIN).status_code == 400


def test_detail_of_another_tenant_is_404(client, cat):
    payload = body(cat)
    alta(client, payload)
    assert client.get(f"/activos/{payload['id']}", headers=ADMIN_OTRO).status_code == 404
    assert client.get(f"/activos/{uuid.uuid4()}", headers=ADMIN).status_code == 404


def test_anonymous_is_401(client, cat):
    for response in (
        client.get("/activos/por-codigo?codigo=X"),
        client.get(f"/activos/{uuid.uuid4()}"),
        client.post("/activos", json=body(cat)),
    ):
        assert response.status_code == 401


# --- D2: desactivar ubicación con activos ------------------------------------------------


def test_d2_deactivating_a_location_with_assets_is_409(client, cat, act_db):
    sala = client.post(
        "/ubicaciones",
        json={
            "nombre": f"Con activos {uuid.uuid4().hex[:4]}",
            "tipo": "sala",
            "padre_id": cat["sede"],
        },
        headers=ADMIN,
    ).get_json()["ubicacion"]["id"]
    primero = body(cat, ubicacion_id=sala)
    alta(client, primero)
    alta(client, body(cat, ubicacion_id=sala))

    response = client.patch(f"/ubicaciones/{sala}", json={"activa": False}, headers=ADMIN)
    assert response.status_code == 409
    assert code(response) == "tiene_activos"
    assert "2 activos" in response.get_json()["error"]["message"]

    # En reparación sigue bloqueando; dados de baja no (la 005 los cambia por la API).
    with act_db.migrator.begin() as conn:
        conn.execute(
            text("update activo set estado = 'en_reparacion' where ubicacion_id = :u"), {"u": sala}
        )
    assert (
        client.patch(f"/ubicaciones/{sala}", json={"activa": False}, headers=ADMIN).status_code
        == 409
    )
    with act_db.migrator.begin() as conn:
        conn.execute(
            text("update activo set estado = 'dado_de_baja' where ubicacion_id = :u"), {"u": sala}
        )
    assert (
        client.patch(f"/ubicaciones/{sala}", json={"activa": False}, headers=ADMIN).status_code
        == 200
    )


# --- Duplicar (R6, Q3; T4) ---------------------------------------------------------------


def original(client, cat) -> dict:
    payload = body(cat, marca="Tuttnauer", modelo="2540", subtipo="Autoclave", serial="SN-ORIG")
    response = alta(client, payload)
    assert response.status_code == 201
    return response.get_json()["activo"]


def duplicar(client, origen_id, headers=ADMIN, **extra):
    payload = {
        "id": str(uuid.uuid4()),
        "codigo": f"dup-{uuid.uuid4().hex[:8]}",
        "copiar_de": origen_id,
        **extra,
    }
    return client.post("/activos", json=payload, headers=headers), payload


def test_duplicate_copies_everything_but_code_serial_and_history(client, cat, act_db):
    origen = original(client, cat)
    response, payload = duplicar(client, origen["id"], serial="SN-NUEVO")

    assert response.status_code == 201, response.get_json()
    copia = response.get_json()["activo"]
    assert copia["id"] == payload["id"] and copia["id"] != origen["id"]
    assert copia["codigo"] == payload["codigo"].upper()
    for campo in (
        "nombre",
        "categoria",
        "ubicacion",
        "marca",
        "modelo",
        "subtipo",
        "precio_compra",
    ):
        assert copia[campo] == origen[campo], campo
    assert copia["serial"] == "SN-NUEVO"
    with act_db.migrator.connect() as conn:
        datos = conn.scalar(
            text("select datos from activo_evento where activo_id = :id"), {"id": payload["id"]}
        )
    assert datos["copiado_de"] == origen["id"]


def test_contador_duplicates_without_seeing_nor_changing_the_price(client, cat, act_db):
    origen = original(client, cat)
    response, payload = duplicar(client, origen["id"], headers=CONTADOR)
    assert response.status_code == 201
    assert not tiene_precio(response.get_json())
    with act_db.migrator.connect() as conn:
        precio = conn.scalar(
            text("select precio_compra::text from activo where id = :id"), {"id": payload["id"]}
        )
    assert precio == origen["precio_compra"]

    intento, _ = duplicar(client, origen["id"], headers=CONTADOR, precio_compra="1.00")
    assert intento.status_code == 400
    assert code(intento) == "solicitud_invalida"


def test_admin_can_change_the_price_and_the_location_when_duplicating(client, cat):
    origen = original(client, cat)
    response, _ = duplicar(
        client, origen["id"], precio_compra="99.50", ubicacion_id=cat["otra_sala"]
    )
    copia = response.get_json()["activo"]
    assert copia["precio_compra"] == "99.50"
    assert copia["ubicacion"]["id"] == cat["otra_sala"]


@pytest.mark.parametrize(
    ("extra", "status", "codigo_error"),
    [
        ({"copiar_de": "no-uuid"}, 400, "solicitud_invalida"),
        ({"precio_compra": "-5"}, 400, "precio_invalido"),
        ({"ubicacion_id": "sede"}, 400, "ubicacion_invalida"),
        ({"codigo": "con espacio"}, 400, "codigo_invalido"),
    ],
)
def test_invalid_duplicates(client, cat, extra, status, codigo_error):
    origen = original(client, cat)
    if extra.get("ubicacion_id") == "sede":
        extra = {**extra, "ubicacion_id": cat["sede"]}
    response, _ = duplicar(client, origen["id"], **extra)
    assert response.status_code == status
    assert code(response) == codigo_error


def test_duplicate_from_another_tenant_or_unknown_is_404(client, cat):
    de_b = alta(
        client, body(cat, categoria_id=cat["cat_b"], ubicacion_id=cat["sala_b"]), ADMIN_OTRO
    ).get_json()["activo"]
    for origen_id in (de_b["id"], str(uuid.uuid4())):
        response, _ = duplicar(client, origen_id)
        assert response.status_code == 404


def test_duplicate_with_an_existing_code_is_409(client, cat):
    origen = original(client, cat)
    response, _ = duplicar(client, origen["id"], codigo=origen["codigo"])
    assert response.status_code == 409
    assert response.get_json()["activo"]["id"] == origen["id"]
