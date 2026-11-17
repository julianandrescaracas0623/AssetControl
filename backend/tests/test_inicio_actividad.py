"""Inicio: actividad reciente (spec 010, T2; R3; CU-DSH-02, P13).

Eventos del tenant por ``seq`` descendente (20 por página, cursor ``antes_de``), con el
activo y el autor; al contador se le omiten los ``precio_cambiado`` y toda clave de
precio, con el mismo filtro del historial (005).
"""

import json
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
from test_exportar_api import ClinicaExp

ADMIN = bearer(ADMIN_A, TENANT_A)
CONTADOR = bearer(CONTADOR_A, TENANT_A, rol="contador")
ADMIN_OTRO = bearer(ADMIN_B, TENANT_B)


@pytest.fixture(scope="module")
def act_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("inicio_actividad")


@pytest.fixture(scope="module")
def act_app(act_db) -> Iterator[Flask]:
    flask_app = make_app(act_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(act_app):
    return act_app.test_client(use_cookies=False)


@pytest.fixture(autouse=True)
def tenant_limpio(act_db) -> Iterator[None]:
    yield
    with act_db.migrator.begin() as conn:
        for sql in (
            "delete from sesion_detalle",
            "delete from sesion_empresa",
            "delete from sesion_no_encontrado",
            "delete from sesion_desglose",
            "delete from activo_evento",
            "delete from verificacion",
            "delete from sesion_conteo",
            "delete from activo",
            "delete from ubicacion",
            "delete from categoria",
        ):
            conn.execute(text(sql))


def actividad(client, headers=ADMIN, **params):
    response = client.get("/inicio/actividad", headers=headers, query_string=params)
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def armar(client) -> tuple[ClinicaExp, str, str]:
    c = ClinicaExp(client)
    a = c.activo("Autoclave", "100.50")
    b = c.activo("Silla", "200.00", c.mob, c.bodega)
    c.precio(a, "150.00")
    c.mover(b, c.box)
    s = c.abrir()
    c._post(
        f"/sesiones/{s}/verificaciones",
        {
            "id": str(uuid.uuid4()),
            "activo_id": a,
            "ubicacion_encontrada_id": c.box,
            "estado_fisico": "ok",
        },
        CONTADOR,
    )
    return c, a, b


def test_admin_sees_the_tenant_events_newest_first_with_asset_and_author(client):
    _, a, b = armar(client)
    datos = actividad(client)
    tipos = [e["tipo"] for e in datos["eventos"]]
    assert tipos == ["verificado", "ubicacion_cambiada", "precio_cambiado", "creado", "creado"]
    seqs = [e["seq"] for e in datos["eventos"]]
    assert seqs == sorted(seqs, reverse=True)
    verificado = datos["eventos"][0]
    assert verificado["activo"]["id"] == a
    assert verificado["activo"]["nombre"] == "Autoclave"
    assert verificado["activo"]["codigo"].startswith("EXP-")
    assert verificado["autor"]["nombre"]
    assert datos["eventos"][1]["activo"]["id"] == b
    assert datos["siguiente"] is None


def test_counter_never_sees_prices(client):
    armar(client)
    datos = actividad(client, CONTADOR)
    assert [e["tipo"] for e in datos["eventos"]] == [
        "verificado",
        "ubicacion_cambiada",
        "creado",
        "creado",
    ]
    assert "precio" not in json.dumps(datos)


def test_pages_of_twenty_with_cursor(client):
    c = ClinicaExp(client)
    for i in range(23):
        c.activo(f"Activo {i}", "1.00")
    primera = actividad(client)
    assert len(primera["eventos"]) == 20
    segunda = actividad(client, antes_de=primera["siguiente"])
    assert len(segunda["eventos"]) == 3
    assert segunda["siguiente"] is None
    todos = [e["seq"] for e in primera["eventos"] + segunda["eventos"]]
    assert len(set(todos)) == 23


def test_bad_cursor_tenant_and_auth(client):
    armar(client)
    assert client.get("/inicio/actividad?antes_de=x", headers=ADMIN).status_code == 400
    assert actividad(client, ADMIN_OTRO)["eventos"] == []
    assert client.get("/inicio/actividad").status_code == 401
