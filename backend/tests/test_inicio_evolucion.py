"""Inicio: evolución entre conteos (spec 010, T3; R5; CU-DSH-04, P22, P24).

Cada punto se lee de ``sesion_conteo`` y ``sesion_desglose`` y debe ser igual al informe
de su sesión; el % encontrado lo calcula el servidor, en unidades, con un decimal.
"""

import json
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
from sqlalchemy import text
from test_exportar_api import ClinicaExp

from app.inicio.indicadores import porcentaje

ADMIN = bearer(ADMIN_A, TENANT_A)
CONTADOR = bearer(CONTADOR_A, TENANT_A, rol="contador")
ADMIN_OTRO = bearer(ADMIN_B, TENANT_B)


@pytest.fixture(scope="module")
def evo_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("inicio_evolucion")


@pytest.fixture(scope="module")
def evo_app(evo_db) -> Iterator[Flask]:
    flask_app = make_app(evo_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(evo_app):
    return evo_app.test_client(use_cookies=False)


@pytest.fixture(autouse=True)
def tenant_limpio(evo_db) -> Iterator[None]:
    yield
    with evo_db.migrator.begin() as conn:
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


def evolucion(client, headers=ADMIN) -> dict:
    response = client.get("/inicio/evolucion", headers=headers)
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def verificar(c: ClinicaExp, sesion: str, activo: str) -> None:
    body = {
        "id": str(uuid.uuid4()),
        "activo_id": activo,
        "ubicacion_encontrada_id": c.box,
        "estado_fisico": "ok",
    }
    c._post(f"/sesiones/{sesion}/verificaciones", body, CONTADOR)


def abrir(c: ClinicaExp, nombre: str, corte: str) -> str:
    return c._post("/sesiones", {"nombre": nombre, "fecha_corte": corte})["sesion"]["id"]


def cerrar(client, sesion: str) -> dict:
    assert client.post(f"/sesiones/{sesion}/cerrar", headers=ADMIN).status_code == 200
    return client.get(f"/sesiones/{sesion}/informe", headers=ADMIN).get_json()


def test_without_closed_counts_it_is_empty(client):
    c = ClinicaExp(client)
    c.activo("Autoclave", "100.50")
    abrir(c, "Conteo nov 2026", "2026-11-30")  # abierta: no aparece
    assert evolucion(client) == {"sesiones": [], "por_categoria": []}


def test_each_point_equals_the_report_of_its_session(client):
    c = ClinicaExp(client)
    a = c.activo("Autoclave", "100.50")
    b = c.activo("Silla", "200.00", c.mob, c.bodega)
    c.activo("Lámpara", "300.00")
    s1 = abrir(c, "Conteo nov 2026", "2026-11-30")
    verificar(c, s1, a)
    informe1 = cerrar(client, s1)

    # Entre conteos: categoría nueva con un activo, una baja y un precio corregido.
    equipos = c._post("/categorias", {"nombre": "Equipos"})["categoria"]["id"]
    c.activo("Monitor", "50.25", equipos)
    c.baja(b)
    s2 = abrir(c, "Conteo dic 2026", "2026-12-31")
    verificar(c, s2, a)
    informe2 = cerrar(client, s2)
    abrir(c, "Conteo ene 2027", "2027-01-31")  # abierta: no aparece

    datos = evolucion(client)
    assert [p["sesion"]["id"] for p in datos["sesiones"]] == [s1, s2]  # cronológico
    for punto, informe in zip(datos["sesiones"], (informe1, informe2), strict=True):
        t = informe["totales"]
        assert punto["sesion"]["nombre"] == informe["sesion"]["nombre"]
        assert punto["sesion"]["fecha_corte"] == informe["sesion"]["fecha_corte"]
        assert punto["total_registrado"] == t["registrado"]
        assert punto["unidades_registrado"] == t["unidades_registrado"]
        assert punto["unidades_encontrado"] == t["unidades_encontrado"]
        assert punto["porcentaje_encontrado"] == porcentaje(
            t["unidades_encontrado"], t["unidades_registrado"]
        )
    assert datos["sesiones"][0]["porcentaje_encontrado"] == "33.3"

    por_categoria = {f["etiqueta"]: f for f in datos["por_categoria"]}
    assert set(por_categoria) == {"Biomédicos", "Mobiliario", "Equipos"}
    # Equipos no existía en el primer conteo: sin punto, no un cero inventado.
    assert [p["sesion_id"] for p in por_categoria["Equipos"]["puntos"]] == [s2]
    # Mobiliario (la silla) se dio de baja sin verificar: no tiene fila en el segundo.
    assert [p["sesion_id"] for p in por_categoria["Mobiliario"]["puntos"]] == [s1]
    for etiqueta, fila in por_categoria.items():
        for punto in fila["puntos"]:
            informe = informe1 if punto["sesion_id"] == s1 else informe2
            (esperada,) = [
                f for f in informe["desglose"]["categorias"] if f["etiqueta"] == etiqueta
            ]
            assert punto["total_registrado"] == esperada["total_registrado"]
            assert punto["unidades_registrado"] == esperada["unidades_registrado"]
    # Cada sesión: la suma de sus puntos por categoría es su total (lo del cierre).
    for punto in datos["sesiones"]:
        suma = sum(
            Decimal(p["total_registrado"])
            for f in datos["por_categoria"]
            for p in f["puntos"]
            if p["sesion_id"] == punto["sesion"]["id"]
        )
        assert suma == Decimal(punto["total_registrado"])


def test_shows_the_twelve_most_recent_counts_and_skips_imports(client, evo_db):
    with evo_db.migrator.begin() as conn:
        for i in range(14):
            conn.execute(
                text(
                    "insert into sesion_conteo (tenant_id, nombre, fecha_corte, abierta_por, "
                    "estado, cerrada_por, cerrada_en, abierta_en, total_encontrado, "
                    "total_no_encontrado, total_registrado) values (:t, :n, current_date, "
                    ":p, 'cerrada', :p, now() - make_interval(days => :d), "
                    "now() - make_interval(days => :d + 1), 0, 0, 0)"
                ),
                {
                    "t": TENANT_A,
                    "n": f"Conteo {i:02d}",
                    "p": ADMIN_A.usuario_id,
                    "d": 30 * (14 - i),
                },
            )
        conn.execute(
            text(
                "insert into sesion_conteo (tenant_id, nombre, fecha_corte, abierta_por, tipo, "
                "estado, cerrada_por, cerrada_en, abierta_en, total_encontrado, "
                "total_no_encontrado, total_registrado) values (:t, 'Importación', current_date, "
                ":p, 'importacion', 'cerrada', :p, now(), now() - interval '1 day', 0, 0, 0)"
            ),
            {"t": TENANT_A, "p": ADMIN_A.usuario_id},
        )
    nombres = [p["sesion"]["nombre"] for p in evolucion(client)["sesiones"]]
    assert nombres == [f"Conteo {i:02d}" for i in range(2, 14)]
    assert all(p["porcentaje_encontrado"] == "0.0" for p in evolucion(client)["sesiones"])


def test_only_admin_and_own_tenant(client):
    c = ClinicaExp(client)
    a = c.activo("Autoclave", "100.50")
    s = abrir(c, "Conteo nov 2026", "2026-11-30")
    verificar(c, s, a)
    cerrar(client, s)
    assert client.get("/inicio/evolucion", headers=CONTADOR).status_code == 403
    assert client.get("/inicio/evolucion").status_code == 401
    assert evolucion(client, ADMIN_OTRO) == {"sesiones": [], "por_categoria": []}
    assert "precio" not in json.dumps(evolucion(client))
