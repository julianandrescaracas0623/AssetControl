"""API de sesiones de conteo (spec 006, T2; R1–R3, Q1; plan.md §3).

- Abrir: solo admin; nombre con la regla H-3 y fecha de corte; una abierta por tenant
  (``409 sesion_abierta_existente``), también en carrera (índice único).
- Listar, la abierta y el detalle: ambos roles, solo su tenant.
- Avance por ubicación vigente del activo: ``activo`` y ``en_reparacion`` cuentan, los
  dados de baja no; un activo verificado dos veces cuenta una.
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
def ses_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("sesiones_api")


@pytest.fixture(scope="module")
def ses_app(ses_db) -> Iterator[Flask]:
    flask_app = make_app(ses_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(ses_app):
    return ses_app.test_client(use_cookies=False)


@pytest.fixture(autouse=True)
def sin_sesiones(ses_db) -> Iterator[None]:
    yield
    with ses_db.migrator.begin() as conn:
        conn.execute(text("delete from activo_evento where sesion_id is not null"))
        conn.execute(text("delete from verificacion"))
        conn.execute(text("delete from sesion_conteo"))


def abrir(client, headers=ADMIN, **cambios):
    body = {"nombre": "Conteo nov 2026", "fecha_corte": "2026-11-30", **cambios}
    return client.post("/sesiones", json=body, headers=headers)


def code(response) -> str:
    return response.get_json()["error"]["code"]


def test_admin_opens_and_both_roles_see_it(client):
    response = abrir(client, nombre="  Conteo   nov 2026 ")
    assert response.status_code == 201, response.get_json()
    sesion = response.get_json()["sesion"]
    assert sesion["nombre"] == "Conteo   nov 2026"
    assert sesion["estado"] == "abierta"
    assert sesion["tipo"] == "conteo"
    assert sesion["fecha_corte"] == "2026-11-30"
    assert sesion["abierta_por"] == {"id": str(ADMIN_A.usuario_id), "nombre": "Ana"}
    assert sesion["cerrada_en"] is None

    for headers in (ADMIN, CONTADOR):
        abierta = client.get("/sesiones/abierta", headers=headers).get_json()["sesion"]
        assert abierta["id"] == sesion["id"]
        lista = client.get("/sesiones", headers=headers).get_json()["sesiones"]
        assert [s["id"] for s in lista] == [sesion["id"]]
    assert client.get("/sesiones/abierta", headers=ADMIN_OTRO).get_json() == {"sesion": None}
    assert client.get("/sesiones", headers=ADMIN_OTRO).get_json() == {"sesiones": []}


def test_only_one_open_session_per_tenant(client):
    assert abrir(client).status_code == 201
    segunda = abrir(client, nombre="Otra")
    assert segunda.status_code == 409
    assert code(segunda) == "sesion_abierta_existente"
    assert abrir(client, headers=ADMIN_OTRO).status_code == 201


def test_the_race_for_the_open_session_is_also_409(client, ses_app, monkeypatch):
    from app.conteo import service

    assert abrir(client).status_code == 201
    monkeypatch.setattr(service, "_abierta", lambda session: None)
    segunda = abrir(client, nombre="Carrera")
    assert segunda.status_code == 409
    assert code(segunda) == "sesion_abierta_existente"


@pytest.mark.parametrize(
    "body",
    [
        {"nombre": ""},
        {"nombre": "x" * 121},
        {"nombre": 3},
        {"fecha_corte": "30/11/2026"},
        {"fecha_corte": None},
        {"tipo": "importacion"},
    ],
)
def test_invalid_open_is_400(client, body):
    response = abrir(client, **body)
    assert response.status_code == 400
    assert code(response) == "solicitud_invalida"


def test_only_the_admin_opens(client):
    assert abrir(client, headers=CONTADOR).status_code == 403
    assert abrir(client, headers={}).status_code == 401


def test_list_puts_the_open_one_first(client, ses_db):
    with ses_db.migrator.begin() as conn:
        for nombre in ("Conteo may 2026", "Conteo nov 2025"):
            conn.execute(
                text(
                    "insert into sesion_conteo (tenant_id, nombre, fecha_corte, abierta_por, "
                    "estado, cerrada_por, cerrada_en, abierta_en, total_encontrado, "
                    "total_no_encontrado, total_registrado) values (:t, :n, current_date, "
                    ":p, 'cerrada', :p, now(), now() - interval '1 day', 0, 0, 0)"
                ),
                {"t": TENANT_A, "n": nombre, "p": ADMIN_A.usuario_id},
            )
    abierta = abrir(client).get_json()["sesion"]
    lista = client.get("/sesiones", headers=CONTADOR).get_json()["sesiones"]
    assert lista[0]["id"] == abierta["id"]
    assert {s["estado"] for s in lista[1:]} == {"cerrada"}
    assert all(s["cerrada_en"] for s in lista[1:])


def test_detail_is_tenant_scoped(client):
    sesion = abrir(client).get_json()["sesion"]
    assert client.get(f"/sesiones/{sesion['id']}", headers=CONTADOR).status_code == 200
    assert client.get(f"/sesiones/{sesion['id']}", headers=ADMIN_OTRO).status_code == 404
    assert client.get(f"/sesiones/{uuid.uuid4()}", headers=ADMIN).status_code == 404
    assert client.get(f"/sesiones/{sesion['id']}", headers={}).status_code == 401


# --- Avance (R3, CU-SES-02) --------------------------------------------------------------


@pytest.fixture
def inventario(client) -> dict:
    """Sede > sala (Consultorios) > box (Box 1) y otra sala (Bodega); cuatro activos."""

    def post(path, body):
        response = client.post(path, json=body, headers=ADMIN)
        assert response.status_code == 201, response.get_json()
        return response.get_json()

    sufijo = uuid.uuid4().hex[:4]
    sede = post("/ubicaciones", {"nombre": f"Sede {sufijo}", "tipo": "sede"})["ubicacion"]["id"]
    sala = post("/ubicaciones", {"nombre": "Consultorios", "tipo": "sala", "padre_id": sede})
    box = post(
        "/ubicaciones", {"nombre": "Box 1", "tipo": "box", "padre_id": sala["ubicacion"]["id"]}
    )
    bodega = post("/ubicaciones", {"nombre": "Bodega", "tipo": "sala", "padre_id": sede})
    cat = post("/categorias", {"nombre": f"Cat {sufijo}"})["categoria"]["id"]
    ids = {"box": box["ubicacion"]["id"], "bodega": bodega["ubicacion"]["id"], "cat": cat}

    def activo(nombre, ubicacion):
        body = {
            "id": str(uuid.uuid4()),
            "codigo": f"{nombre}-{sufijo}",
            "nombre": nombre,
            "precio_compra": "10.00",
            "categoria_id": cat,
            "ubicacion_id": ids[ubicacion],
        }
        return post("/activos", body)["activo"]

    ids["a1"] = activo("A1", "box")
    ids["a2"] = activo("A2", "box")
    ids["a3"] = activo("A3", "bodega")
    ids["baja"] = activo("BAJA", "bodega")
    return ids


def verificar_en_la_base(db: AccesoDb, sesion_id: str, activo: dict, ubicacion: str, cat: str):
    with db.migrator.begin() as conn:
        conn.execute(
            text(
                "insert into verificacion (id, tenant_id, sesion_id, activo_id, "
                "ubicacion_esperada_id, ubicacion_encontrada_id, estado_fisico, "
                "precio_al_contar, categoria_al_contar, verificado_por) "
                "values (gen_random_uuid(), :t, :s, :a, :u, :u, 'ok', 10, :c, :p)"
            ),
            {
                "t": TENANT_A,
                "s": sesion_id,
                "a": activo["id"],
                "u": ubicacion,
                "c": cat,
                "p": ADMIN_A.usuario_id,
            },
        )


def test_progress_by_current_location(client, ses_db, inventario):
    baja = inventario["baja"]
    client.post(
        f"/activos/{baja['id']}/baja",
        json={"motivo": "perdido"},
        headers={**ADMIN, "If-Match": "1"},
    )
    a2 = inventario["a2"]
    client.post(
        f"/activos/{a2['id']}/estado",
        json={"estado": "en_reparacion"},
        headers={**ADMIN, "If-Match": "1"},
    )
    sesion = abrir(client).get_json()["sesion"]
    for _ in range(2):  # dos verificaciones del mismo activo cuentan una
        verificar_en_la_base(
            ses_db, sesion["id"], inventario["a1"], inventario["box"], inventario["cat"]
        )

    for headers in (ADMIN, CONTADOR):
        cuerpo = client.get(f"/sesiones/{sesion['id']}", headers=headers).get_json()
        avance = cuerpo["avance"]
        filas = {f["ubicacion"]["ruta"]: f for f in avance["por_ubicacion"]}
        assert filas["Consultorios › Box 1"] == {
            "ubicacion": {"id": inventario["box"], "ruta": "Consultorios › Box 1"},
            "total": 2,
            "verificados": 1,
            "pendientes": 1,
        }
        assert filas["Bodega"]["total"] == 1
        assert filas["Bodega"]["pendientes"] == 1
        assert (avance["total"], avance["verificados"], avance["pendientes"]) == (3, 1, 2)
