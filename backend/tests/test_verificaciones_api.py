"""Verificar activos en una sesión (spec 006, T3–T4; R4–R9, Q2–Q4; plan.md §3).

- Alta de una verificación (``201``) con copia de precio, categoría y ubicación del
  activo en ese momento (ADR-003) y evento ``verificado`` en la misma transacción.
- Reintento con el mismo ``id``: ``200`` con la guardada, también con la sesión ya
  cerrada (Q3); un ``id`` de otro activo o sesión ``400``.
- ``409 sesion_cerrada``, ``409 activo_dado_de_baja``, ``400 ubicacion_invalida``;
  sesión, activo o ubicación de otro tenant ``404``.
- Verificar dos veces: se conservan las dos; la última (mayor ``seq``) es la vigente.
- Precio: el admin ve ``precio_al_contar``; el contador nunca (T4).
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
def ver_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("verificaciones_api")


@pytest.fixture(scope="module")
def ver_app(ver_db) -> Iterator[Flask]:
    flask_app = make_app(ver_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(ver_app):
    return ver_app.test_client(use_cookies=False)


@pytest.fixture(scope="module")
def cat(ver_app) -> dict[str, str]:
    client = ver_app.test_client(use_cookies=False)

    def post(path, body, headers=ADMIN):
        response = client.post(path, json=body, headers=headers)
        assert response.status_code == 201, response.get_json()
        return response.get_json()

    sede = post("/ubicaciones", {"nombre": "Sede", "tipo": "sede"})["ubicacion"]["id"]
    sala = post("/ubicaciones", {"nombre": "Consultorios", "tipo": "sala", "padre_id": sede})
    sala_id = sala["ubicacion"]["id"]
    box = post("/ubicaciones", {"nombre": "Box 1", "tipo": "box", "padre_id": sala_id})
    bodega = post("/ubicaciones", {"nombre": "Bodega", "tipo": "sala", "padre_id": sede})
    sede_b = post("/ubicaciones", {"nombre": "Sede B", "tipo": "sede"}, ADMIN_OTRO)
    sala_b = post(
        "/ubicaciones",
        {"nombre": "Sala B", "tipo": "sala", "padre_id": sede_b["ubicacion"]["id"]},
        ADMIN_OTRO,
    )
    return {
        "sede": sede,
        "sala": sala_id,
        "box": box["ubicacion"]["id"],
        "bodega": bodega["ubicacion"]["id"],
        "sala_b": sala_b["ubicacion"]["id"],
        "cat": post("/categorias", {"nombre": "Biomédicos"})["categoria"]["id"],
        "cat2": post("/categorias", {"nombre": "Muebles"})["categoria"]["id"],
        "cat_b": post("/categorias", {"nombre": "Otra"}, ADMIN_OTRO)["categoria"]["id"],
    }


@pytest.fixture
def sesion(client, ver_db) -> Iterator[str]:
    response = client.post(
        "/sesiones", json={"nombre": "Conteo nov 2026", "fecha_corte": "2026-11-30"}, headers=ADMIN
    )
    assert response.status_code == 201, response.get_json()
    sesion_id = response.get_json()["sesion"]["id"]
    yield sesion_id
    cerrar(ver_db, sesion_id)


def cerrar(db: AccesoDb, sesion_id: str) -> None:
    """El cierre llega con la 008: aquí lo hace el migrador."""
    with db.migrator.begin() as conn:
        conn.execute(
            text(
                "update sesion_conteo set estado = 'cerrada', cerrada_en = now(), "
                "total_encontrado = 0, total_no_encontrado = 0, total_registrado = 0, "
                "cerrada_por = abierta_por where id = :s and estado = 'abierta'"
            ),
            {"s": sesion_id},
        )


def nuevo(client, cat, **cambios) -> dict:
    body = {
        "id": str(uuid.uuid4()),
        "codigo": f"V-{uuid.uuid4().hex[:8].upper()}",
        "nombre": "Autoclave clase B 18 L",
        "precio_compra": "14200000.00",
        "categoria_id": cat["cat"],
        "ubicacion_id": cat["box"],
        **cambios,
    }
    response = client.post("/activos", json=body, headers=ADMIN)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["activo"]


def verificar(client, sesion_id, activo, ubicacion, headers=CONTADOR, **cambios):
    body = {
        "id": str(uuid.uuid4()),
        "activo_id": activo,
        "ubicacion_encontrada_id": ubicacion,
        "estado_fisico": "ok",
        **cambios,
    }
    response = client.post(f"/sesiones/{sesion_id}/verificaciones", json=body, headers=headers)
    return response, body


def code(response) -> str:
    return response.get_json()["error"]["code"]


def filas(db: AccesoDb, activo_id: str) -> list[tuple]:
    with db.migrator.connect() as conn:
        return list(
            conn.execute(
                text(
                    "select id, estado_fisico, precio_al_contar::text, categoria_al_contar, "
                    "ubicacion_esperada_id, ubicacion_encontrada_id, nota, verificado_por "
                    "from verificacion where activo_id = :a order by seq"
                ),
                {"a": activo_id},
            )
        )


def eventos(db: AccesoDb, activo_id: str) -> list[tuple]:
    with db.migrator.connect() as conn:
        return list(
            conn.execute(
                text(
                    "select tipo, datos, usuario_id, sesion_id, verificacion_id "
                    "from activo_evento where activo_id = :a and tipo = 'verificado' order by seq"
                ),
                {"a": activo_id},
            )
        )


def tiene_precio(valor) -> bool:
    if isinstance(valor, dict):
        return any("precio" in k or tiene_precio(v) for k, v in valor.items())
    if isinstance(valor, list):
        return any(tiene_precio(v) for v in valor)
    if isinstance(valor, str):
        return "14200000" in valor
    return False


# --- T3: verificar -----------------------------------------------------------------------


def test_counter_verifies_with_a_snapshot_and_an_event(client, cat, ver_db, sesion):
    activo = nuevo(client, cat)
    response, body = verificar(
        client,
        sesion,
        activo["id"],
        cat["bodega"],
        estado_fisico="danado",
        nota="  Tapa rayada ",
        ocurrido_en="2026-11-14T10:32:00-05:00",
    )

    assert response.status_code == 201, response.get_json()
    v = response.get_json()["verificacion"]
    assert v["id"] == body["id"]
    assert v["sesion_id"] == sesion
    assert v["activo"] == {
        "id": activo["id"],
        "codigo": activo["codigo"],
        "nombre": activo["nombre"],
    }
    assert v["ubicacion_esperada"] == {"id": cat["box"], "ruta": "Consultorios › Box 1"}
    assert v["ubicacion_encontrada"] == {"id": cat["bodega"], "ruta": "Bodega"}
    assert v["estado_fisico"] == "danado"
    assert v["nota"] == "Tapa rayada"
    assert v["verificado_por"] == {"id": str(CONTADOR_A.usuario_id), "nombre": "Carlos"}
    assert v["ocurrido_en"].startswith("2026-11-14T15:32:00")
    assert "precio_al_contar" not in v

    assert filas(ver_db, activo["id"]) == [
        (
            uuid.UUID(body["id"]),
            "danado",
            "14200000.00",
            uuid.UUID(cat["cat"]),
            uuid.UUID(cat["box"]),
            uuid.UUID(cat["bodega"]),
            "Tapa rayada",
            CONTADOR_A.usuario_id,
        )
    ]
    [(tipo, datos, autor, sesion_id, verificacion_id)] = eventos(ver_db, activo["id"])
    assert (tipo, autor, str(sesion_id), str(verificacion_id)) == (
        "verificado",
        CONTADOR_A.usuario_id,
        sesion,
        body["id"],
    )
    assert datos == {
        "estado_fisico": "danado",
        "nota": "Tapa rayada",
        "ubicacion_esperada": {"id": cat["box"], "ruta": "Consultorios › Box 1"},
        "ubicacion_encontrada": {"id": cat["bodega"], "ruta": "Bodega"},
        "sesion": "Conteo nov 2026",
    }


def test_snapshot_does_not_follow_later_changes(client, cat, ver_db, sesion):
    activo = nuevo(client, cat)
    verificar(client, sesion, activo["id"], cat["box"])
    client.patch(
        f"/activos/{activo['id']}",
        json={"precio_compra": "1.00", "categoria_id": cat["cat2"]},
        headers={**ADMIN, "If-Match": "1"},
    )
    client.post(
        f"/activos/{activo['id']}/mover",
        json={"ubicacion_id": cat["bodega"]},
        headers={**ADMIN, "If-Match": "2"},
    )
    [fila] = filas(ver_db, activo["id"])
    assert (fila[2], fila[3], fila[4]) == (
        "14200000.00",
        uuid.UUID(cat["cat"]),
        uuid.UUID(cat["box"]),
    )


def test_retry_with_the_same_id_returns_the_saved_one(client, cat, ver_db, sesion):
    activo = nuevo(client, cat)
    primera, body = verificar(client, sesion, activo["id"], cat["box"])
    assert primera.status_code == 201
    segunda = client.post(f"/sesiones/{sesion}/verificaciones", json=body, headers=CONTADOR)
    assert segunda.status_code == 200
    assert segunda.get_json()["verificacion"] == primera.get_json()["verificacion"]
    assert len(filas(ver_db, activo["id"])) == 1
    assert len(eventos(ver_db, activo["id"])) == 1

    # Q3: guardada antes del cierre, el reintento tardío la devuelve.
    cerrar(ver_db, sesion)
    tardia = client.post(f"/sesiones/{sesion}/verificaciones", json=body, headers=CONTADOR)
    assert tardia.status_code == 200
    assert tardia.get_json()["verificacion"]["id"] == body["id"]


def test_an_id_reused_for_another_asset_or_session_is_400(client, cat, ver_db, sesion):
    a1, a2 = nuevo(client, cat), nuevo(client, cat)
    _, body = verificar(client, sesion, a1["id"], cat["box"])
    otro = client.post(
        f"/sesiones/{sesion}/verificaciones", json={**body, "activo_id": a2["id"]}, headers=CONTADOR
    )
    assert otro.status_code == 400
    assert filas(ver_db, a2["id"]) == []


def test_closed_session_rejects_new_verifications(client, cat, ver_db, sesion):
    activo = nuevo(client, cat)
    cerrar(ver_db, sesion)
    response, _ = verificar(client, sesion, activo["id"], cat["box"])
    assert response.status_code == 409
    assert code(response) == "sesion_cerrada"
    assert filas(ver_db, activo["id"]) == []


def test_written_off_asset_is_rejected(client, cat, ver_db, sesion):
    activo = nuevo(client, cat)
    client.post(
        f"/activos/{activo['id']}/baja",
        json={"motivo": "perdido"},
        headers={**ADMIN, "If-Match": "1"},
    )
    response, _ = verificar(client, sesion, activo["id"], cat["box"])
    assert response.status_code == 409
    assert code(response) == "activo_dado_de_baja"
    assert filas(ver_db, activo["id"]) == []


def test_in_repair_can_be_verified(client, cat, sesion):
    activo = nuevo(client, cat)
    client.post(
        f"/activos/{activo['id']}/estado",
        json={"estado": "en_reparacion"},
        headers={**ADMIN, "If-Match": "1"},
    )
    response, _ = verificar(client, sesion, activo["id"], cat["box"])
    assert response.status_code == 201


@pytest.mark.parametrize("donde", ["sede", "inactiva"])
def test_found_location_must_be_an_active_room_or_box(client, cat, ver_db, sesion, donde):
    activo = nuevo(client, cat)
    ubicacion = cat["sede"]
    if donde == "inactiva":
        ubicacion = client.post(
            "/ubicaciones",
            json={
                "nombre": f"Vieja {uuid.uuid4().hex[:4]}",
                "tipo": "sala",
                "padre_id": cat["sede"],
            },
            headers=ADMIN,
        ).get_json()["ubicacion"]["id"]
        client.patch(f"/ubicaciones/{ubicacion}", json={"activa": False}, headers=ADMIN)
    response, _ = verificar(client, sesion, activo["id"], ubicacion)
    assert response.status_code == 400
    assert code(response) == "ubicacion_invalida"
    assert filas(ver_db, activo["id"]) == []


@pytest.mark.parametrize(
    "cambios",
    [
        {"estado_fisico": "regular"},
        {"estado_fisico": None},
        {"nota": "x" * 121},
        {"nota": 3},
        {"ocurrido_en": "ayer"},
        {"ocurrido_en": "2026-11-14T10:32:00"},
        {"id": "no-uuid"},
        {"activo_id": None},
        {"ubicacion_encontrada_id": None},
        {"precio_al_contar": "1.00"},
    ],
)
def test_invalid_bodies_are_400(client, cat, ver_db, sesion, cambios):
    activo = nuevo(client, cat)
    response, _ = verificar(client, sesion, activo["id"], cat["box"], **cambios)
    assert response.status_code == 400, response.get_json()
    assert code(response) == "solicitud_invalida"
    assert filas(ver_db, activo["id"]) == []


def test_other_tenant_references_are_404(client, cat, sesion):
    activo = nuevo(client, cat)
    assert verificar(client, sesion, activo["id"], cat["sala_b"])[0].status_code == 404
    assert verificar(client, sesion, str(uuid.uuid4()), cat["box"])[0].status_code == 404
    assert verificar(client, str(uuid.uuid4()), activo["id"], cat["box"])[0].status_code == 404
    otro = verificar(client, sesion, activo["id"], cat["box"], headers=ADMIN_OTRO)[0]
    assert otro.status_code == 404
    assert verificar(client, sesion, activo["id"], cat["box"], headers={})[0].status_code == 401


def test_verifying_again_keeps_both_and_the_last_one_rules(client, cat, ver_db, sesion):
    activo = nuevo(client, cat)
    ruta = f"/sesiones/{sesion}/verificaciones"
    vacia = client.get(ruta, query_string={"activo_id": activo["id"]}, headers=CONTADOR)
    assert vacia.get_json() == {"verificacion": None}

    def verificados_en_box() -> int:
        avance = client.get(f"/sesiones/{sesion}", headers=CONTADOR).get_json()["avance"]
        return next(f for f in avance["por_ubicacion"] if f["ubicacion"]["id"] == cat["box"])[
            "verificados"
        ]

    antes = verificados_en_box()
    verificar(client, sesion, activo["id"], cat["box"])
    _, segunda = verificar(client, sesion, activo["id"], cat["bodega"], headers=ADMIN)
    assert verificados_en_box() == antes + 1  # dos verificaciones, un activo
    assert len(filas(ver_db, activo["id"])) == 2
    ultima = client.get(ruta, query_string={"activo_id": activo["id"]}, headers=CONTADOR).get_json()
    assert ultima["verificacion"]["id"] == segunda["id"]
    assert ultima["verificacion"]["verificado_por"]["nombre"] == "Ana"

    for params in ({}, {"activo_id": "x"}):
        assert client.get(ruta, query_string=params, headers=CONTADOR).status_code == 400
    otra_sesion = client.get(
        f"/sesiones/{uuid.uuid4()}/verificaciones",
        query_string={"activo_id": activo["id"]},
        headers=CONTADOR,
    )
    assert otra_sesion.status_code == 404


# --- T4: precio por rol --------------------------------------------------------------------


def test_admin_sees_the_reference_price(client, cat, sesion):
    activo = nuevo(client, cat)
    response, _ = verificar(client, sesion, activo["id"], cat["box"], headers=ADMIN)
    assert response.get_json()["verificacion"]["precio_al_contar"] == "14200000.00"
    ultima = client.get(
        f"/sesiones/{sesion}/verificaciones",
        query_string={"activo_id": activo["id"]},
        headers=ADMIN,
    )
    assert ultima.get_json()["verificacion"]["precio_al_contar"] == "14200000.00"


def test_no_response_to_the_counter_carries_a_price(client, cat, sesion):
    activo = nuevo(client, cat)
    respuestas = []
    nueva, body = verificar(client, sesion, activo["id"], cat["box"])
    respuestas.append(nueva)
    respuestas.append(
        client.post(f"/sesiones/{sesion}/verificaciones", json=body, headers=CONTADOR)
    )
    respuestas.append(
        client.get(
            f"/sesiones/{sesion}/verificaciones",
            query_string={"activo_id": activo["id"]},
            headers=CONTADOR,
        )
    )
    respuestas.append(client.get(f"/sesiones/{sesion}", headers=CONTADOR))
    respuestas.append(client.get("/sesiones", headers=CONTADOR))
    respuestas.append(client.get("/sesiones/abierta", headers=CONTADOR))
    respuestas.append(client.get(f"/activos/{activo['id']}/historial", headers=CONTADOR))
    for response in respuestas:
        assert response.status_code in {200, 201}, response.get_json()
        assert not tiene_precio(response.get_json()), response.get_json()


def test_a_verification_waits_for_a_close_in_progress(client, cat, ver_db, sesion):
    """El cierre (008) tomará el candado exclusivo: la verificación espera y ve el cierre."""
    import threading

    activo = nuevo(client, cat)
    resultado: dict[str, object] = {}
    with ver_db.migrator.connect() as conn:
        trans = conn.begin()
        conn.execute(
            text("select pg_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": f"sesion_conteo:{sesion}"},
        )

        def intentar():
            resultado["respuesta"] = verificar(client, sesion, activo["id"], cat["box"])[0]

        hilo = threading.Thread(target=intentar)
        hilo.start()
        hilo.join(timeout=0.5)
        assert hilo.is_alive(), "la verificación no esperó al cierre"
        conn.execute(
            text(
                "update sesion_conteo set estado = 'cerrada', cerrada_en = now(), "
                "total_encontrado = 0, total_no_encontrado = 0, total_registrado = 0, "
                "cerrada_por = abierta_por where id = :s"
            ),
            {"s": sesion},
        )
        trans.commit()
    hilo.join(timeout=10)
    respuesta = resultado["respuesta"]
    assert respuesta.status_code == 409  # type: ignore[union-attr]
    assert code(respuesta) == "sesion_cerrada"
    assert filas(ver_db, activo["id"]) == []
