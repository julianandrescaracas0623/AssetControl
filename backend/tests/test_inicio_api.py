"""Inicio: indicadores (spec 010, T1; R1, R2, R6; CU-DSH-01, P13, P26).

Cifras exactas en un caso armado, sin sesión y sin cierres, aislamiento por tenant y
la respuesta al contador sin ningún dinero (ocultarlo en la UI no cuenta, P13).
"""

import json
import re
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
DINERO = re.compile(r"precio|valor|total_|registrado|\d+\.\d{2}\b", re.IGNORECASE)


@pytest.fixture(scope="module")
def ini_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("inicio_api")


@pytest.fixture(scope="module")
def ini_app(ini_db) -> Iterator[Flask]:
    flask_app = make_app(ini_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(ini_app):
    return ini_app.test_client(use_cookies=False)


@pytest.fixture(autouse=True)
def tenant_limpio(ini_db) -> Iterator[None]:
    yield
    with ini_db.migrator.begin() as conn:
        for sql in (
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


def inicio(client, headers=ADMIN) -> dict:
    response = client.get("/inicio", headers=headers)
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def verificar(c: ClinicaExp, sesion: str, activo: str, ubicacion: str, estado="ok") -> None:
    body = {
        "id": str(uuid.uuid4()),
        "activo_id": activo,
        "ubicacion_encontrada_id": ubicacion,
        "estado_fisico": estado,
    }
    c._post(f"/sesiones/{sesion}/verificaciones", body, CONTADOR)


def test_empty_tenant_has_no_session_and_no_report(client):
    datos = inicio(client)
    assert datos["activos_hoy"] == {"unidades": 0, "en_reparacion": 0}
    assert datos["sesion_abierta"] is None
    assert datos["valor_actual"]["total"] == "0.00"
    assert datos["valor_actual"]["unidades"] == 0
    assert datos["discrepancias"] is None
    assert datos["danados"] == {"total": 0, "en_reparacion": 0, "danados": 0, "sesion": None}
    assert datos["ultimo_informe"] is None


def test_indicators_follow_the_open_session_or_the_last_closed_one(client):
    c = ClinicaExp(client)
    a = c.activo("Autoclave", "100.50")
    b = c.activo("Silla", "200.00", c.mob, c.bodega)
    d = c.activo("Lámpara", "300.00")
    baja = c.activo("Vieja", "400.00")
    c.reparacion(b)
    c.baja(baja)

    s1 = c.abrir()
    verificar(c, s1, a, c.bodega)  # en otra ubicación: discrepancia
    verificar(c, s1, d, c.box, "danado")
    assert client.post(f"/sesiones/{s1}/cerrar", headers=ADMIN).status_code == 200
    informe = client.get(f"/sesiones/{s1}/informe", headers=ADMIN).get_json()

    sin_abierta = inicio(client)
    assert sin_abierta["sesion_abierta"] is None
    assert sin_abierta["activos_hoy"] == {"unidades": 3, "en_reparacion": 1}
    assert sin_abierta["valor_actual"]["total"] == "600.50"
    assert sin_abierta["valor_actual"]["unidades"] == 3
    # Sin sesión abierta, la referencia es la última cerrada (P26) y se nombra.
    assert sin_abierta["danados"] == {
        "total": 2,
        "en_reparacion": 1,
        "danados": 1,
        "sesion": {"id": s1, "nombre": "Conteo nov 2026"},
    }
    assert sin_abierta["discrepancias"] == {
        "por_resolver": 1,
        "sesion": {"id": s1, "nombre": "Conteo nov 2026"},
    }
    # El último informe es el del cierre, tal cual (lo congelado se lee).
    assert sin_abierta["ultimo_informe"] == {
        "sesion": informe["sesion"],
        "totales": informe["totales"],
    }

    s2 = c._post("/sesiones", {"nombre": "Conteo dic 2026", "fecha_corte": "2026-12-31"})["sesion"][
        "id"
    ]
    verificar(c, s2, d, c.box)  # ya no está dañada en la sesión abierta
    con_abierta = inicio(client)
    assert con_abierta["sesion_abierta"] == {
        "id": s2,
        "nombre": "Conteo dic 2026",
        "fecha_corte": "2026-12-31",
        "avance": {"total": 3, "verificados": 1, "pendientes": 2, "porcentaje": "33.3"},
    }
    assert con_abierta["danados"]["sesion"] == {"id": s2, "nombre": "Conteo dic 2026"}
    assert con_abierta["danados"]["danados"] == 0
    assert con_abierta["danados"]["total"] == 1
    assert con_abierta["discrepancias"] == {
        "por_resolver": 0,
        "sesion": {"id": s2, "nombre": "Conteo dic 2026"},
    }
    assert con_abierta["ultimo_informe"]["sesion"]["id"] == s1


def test_counter_gets_units_and_progress_without_any_money(client):
    c = ClinicaExp(client)
    a = c.activo("Autoclave", "100.50")
    s = c.abrir()
    verificar(c, s, a, c.bodega, "danado")
    response = client.get("/inicio", headers=CONTADOR)
    assert response.status_code == 200
    datos = response.get_json()
    assert set(datos) == {"activos_hoy", "sesion_abierta"}
    assert datos["sesion_abierta"]["avance"]["verificados"] == 1
    assert not DINERO.search(json.dumps(datos)), datos


def test_inicio_is_per_tenant_and_needs_a_session(client):
    c = ClinicaExp(client)
    c.activo("Autoclave", "100.50")
    c.abrir()
    otro = inicio(client, ADMIN_OTRO)
    assert otro["activos_hoy"]["unidades"] == 0
    assert otro["sesion_abierta"] is None
    assert client.get("/inicio").status_code == 401
