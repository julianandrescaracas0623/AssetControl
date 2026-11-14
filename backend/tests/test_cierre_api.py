"""Cerrar una sesión y leer su informe (spec 008, T2–T3; R1–R9, Q1, Q3; A2).

- Cada regla de R4 en un caso armado a mano, con las cifras exactas.
- Cuadre con cero diferencias (R3) en un conjunto al azar con semilla fija, contra un
  cálculo independiente hecho en SQL en la prueba.
- El informe no cambia después del cierre aunque cambien precios, nombres, ubicaciones o
  estados (ADR-003, Q3); cerrar otra vez lo devuelve sin reinsertar (Q1).
- Concurrencia: el cierre espera a una verificación en curso y la incluye; una edición
  de un activo sin confirmar queda entera fuera.
- Solo admin; la sesión abierta no tiene informe (``409 sesion_abierta``).
"""

import random
import threading
import uuid
from collections import Counter
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

ADMIN = bearer(ADMIN_A, TENANT_A)
CONTADOR = bearer(CONTADOR_A, TENANT_A, rol="contador")
ADMIN_OTRO = bearer(ADMIN_B, TENANT_B)


@pytest.fixture(scope="module")
def cie_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("cierre_api")


@pytest.fixture(scope="module")
def cie_app(cie_db) -> Iterator[Flask]:
    flask_app = make_app(cie_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(cie_app):
    return cie_app.test_client(use_cookies=False)


@pytest.fixture(autouse=True)
def tenant_limpio(cie_db) -> Iterator[None]:
    """Cada prueba cierra en un tenant con activos propios: se borra lo de la anterior."""
    yield
    with cie_db.migrator.begin() as conn:
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


class Clinica:
    """Catálogo armado por la API y atajos para el caso de prueba."""

    def __init__(self, client):
        self.client = client
        sufijo = uuid.uuid4().hex[:4]
        self.sede = self._post("/ubicaciones", {"nombre": f"Sede {sufijo}", "tipo": "sede"})[
            "ubicacion"
        ]["id"]
        sala = self._post(
            "/ubicaciones", {"nombre": "Consultorios", "tipo": "sala", "padre_id": self.sede}
        )
        self.sala = sala["ubicacion"]["id"]
        self.box = self._post(
            "/ubicaciones", {"nombre": "Box 1", "tipo": "box", "padre_id": self.sala}
        )["ubicacion"]["id"]
        self.bodega = self._post(
            "/ubicaciones", {"nombre": "Bodega", "tipo": "sala", "padre_id": self.sede}
        )["ubicacion"]["id"]
        self.bio = self._post("/categorias", {"nombre": "Biomédicos"})["categoria"]["id"]
        self.mob = self._post("/categorias", {"nombre": "Mobiliario"})["categoria"]["id"]
        self.version: dict[str, int] = {}

    def _post(self, path, body, headers=ADMIN):
        response = self.client.post(path, json=body, headers=headers)
        assert response.status_code in (200, 201), response.get_json()
        return response.get_json()

    def activo(self, nombre, precio, categoria=None, ubicacion=None) -> str:
        body = {
            "id": str(uuid.uuid4()),
            "codigo": f"{nombre}-{uuid.uuid4().hex[:6]}".upper(),
            "nombre": nombre,
            "precio_compra": precio,
            "categoria_id": categoria or self.bio,
            "ubicacion_id": ubicacion or self.box,
        }
        activo = self._post("/activos", body)["activo"]
        self.version[activo["id"]] = 1
        return activo["id"]

    def cambiar(self, activo_id, ruta, body, metodo="POST"):
        response = self.client.open(
            f"/activos/{activo_id}{ruta}",
            method=metodo,
            json=body,
            headers={**ADMIN, "If-Match": str(self.version[activo_id])},
        )
        assert response.status_code == 200, response.get_json()
        self.version[activo_id] = response.get_json()["activo"]["row_version"]

    def precio(self, activo_id, precio):
        self.cambiar(activo_id, "", {"precio_compra": precio}, "PATCH")

    def categoria(self, activo_id, categoria):
        self.cambiar(activo_id, "", {"categoria_id": categoria}, "PATCH")

    def mover(self, activo_id, ubicacion):
        self.cambiar(activo_id, "/mover", {"ubicacion_id": ubicacion})

    def reparacion(self, activo_id, estado="en_reparacion"):
        self.cambiar(activo_id, "/estado", {"estado": estado})

    def baja(self, activo_id):
        self.cambiar(activo_id, "/baja", {"motivo": "perdido"})

    def abrir(self) -> str:
        return self._post("/sesiones", {"nombre": "Conteo nov 2026", "fecha_corte": "2026-11-30"})[
            "sesion"
        ]["id"]

    def verificar(self, sesion, activo_id, ubicacion=None, headers=CONTADOR):
        body = {
            "id": str(uuid.uuid4()),
            "activo_id": activo_id,
            "ubicacion_encontrada_id": ubicacion or self.box,
            "estado_fisico": "ok",
        }
        return self._post(f"/sesiones/{sesion}/verificaciones", body, headers)


def cerrar(client, sesion, headers=ADMIN):
    return client.post(f"/sesiones/{sesion}/cerrar", headers=headers)


def code(response) -> str:
    return response.get_json()["error"]["code"]


def assert_cuadra(informe: dict) -> None:
    """R3: por dimensión, filas = cifras; lista = no encontrado (cero diferencias)."""
    totales = informe["totales"]
    for dimension in ("categorias", "ubicaciones"):
        filas = informe["desglose"][dimension]
        for campo in ("encontrado", "no_encontrado", "registrado"):
            suma = sum(Decimal(f[f"total_{campo}"]) for f in filas)
            assert suma == Decimal(totales[campo]), (dimension, campo)
            unidades = sum(f[f"unidades_{campo}"] for f in filas)
            assert unidades == totales[f"unidades_{campo}"], (dimension, campo)
        for f in filas:
            assert Decimal(f["total_registrado"]) == Decimal(f["total_encontrado"]) + Decimal(
                f["total_no_encontrado"]
            )
    lista = informe["no_encontrados"]
    assert sum(Decimal(f["precio"]) for f in lista) == Decimal(totales["no_encontrado"])
    assert len(lista) == totales["unidades_no_encontrado"]
    assert Decimal(totales["registrado"]) == Decimal(totales["encontrado"]) + Decimal(
        totales["no_encontrado"]
    )
    for dimension, clave, nombre in (
        ("categorias", "categoria", "id"),
        ("ubicaciones", "ubicacion", "id"),
    ):
        por_fila = Counter()
        suma_fila: dict[str, Decimal] = {}
        for f in lista:
            k = f[clave][nombre]
            por_fila[k] += 1
            suma_fila[k] = suma_fila.get(k, Decimal("0")) + Decimal(f["precio"])
        for fila in informe["desglose"][dimension]:
            assert fila["unidades_no_encontrado"] == por_fila.get(fila["id"], 0)
            assert Decimal(fila["total_no_encontrado"]) == suma_fila.get(fila["id"], Decimal("0"))


# --- R4 regla por regla --------------------------------------------------------------------


def test_every_rule_of_r4_with_exact_figures(client):
    c = Clinica(client)
    a = c.activo("A", "100.10")  # encontrado tal cual
    b = c.activo("B", "200.00")  # verificado dos veces: cuenta la última foto
    d = c.activo("C", "300.00", ubicacion=c.sala)  # verificado y luego cambiado: no se mueve
    e = c.activo("D", "400.00")  # verificado y luego dado de baja: sigue encontrado
    f = c.activo("E", "500.00", categoria=c.mob)  # en reparación sin verificar: no encontrado
    c.activo("F", "600.00", ubicacion=c.bodega)  # sin verificar: no encontrado
    h = c.activo("G", "700.00")  # dado de baja sin verificar: fuera
    i = c.activo("H", "800.00", categoria=c.mob)  # en reparación y verificado: encontrado
    c.reparacion(f)
    c.reparacion(i)
    c.baja(h)
    sesion = c.abrir()
    c.verificar(sesion, a)
    c.verificar(sesion, b)
    c.precio(b, "250.00")
    c.verificar(sesion, b, c.bodega)
    c.verificar(sesion, d, c.sala)
    c.precio(d, "999.00")
    c.categoria(d, c.mob)
    c.mover(d, c.bodega)
    c.verificar(sesion, e)
    c.baja(e)
    c.verificar(sesion, i)

    response = cerrar(client, sesion)
    assert response.status_code == 200, response.get_json()
    informe = response.get_json()
    assert informe["sesion"]["estado"] == "cerrada"
    assert informe["sesion"]["cerrada_por"]["nombre"] == "Ana"
    assert informe["totales"] == {
        # 100.10 + 250 + 300 + 400 + 800 (de B cuenta la última foto: 250, en Box 1)
        "encontrado": "1850.10",
        "no_encontrado": "1100.00",  # 500 + 600
        "registrado": "2950.10",
        "unidades_encontrado": 5,
        "unidades_no_encontrado": 2,
        "unidades_registrado": 7,
    }
    assert_cuadra(informe)
    cats = {r["etiqueta"]: r for r in informe["desglose"]["categorias"]}
    # C cuenta en Biomédicos (su categoría al contar), no en Mobiliario.
    assert cats["Biomédicos"]["total_encontrado"] == "1050.10"
    assert cats["Mobiliario"]["total_encontrado"] == "800.00"
    assert cats["Mobiliario"]["total_no_encontrado"] == "500.00"
    ubic = {r["etiqueta"]: r for r in informe["desglose"]["ubicaciones"]}
    # C en Consultorios (su ubicación esperada al contar), no en Bodega donde está ahora;
    # B en Box 1 (su esperada), aunque se vio en Bodega.
    assert ubic["Consultorios"]["total_encontrado"] == "300.00"
    assert ubic["Consultorios › Box 1"]["unidades_encontrado"] == 4
    assert ubic["Bodega"] == {
        "id": c.bodega,
        "etiqueta": "Bodega",
        "total_encontrado": "0.00",
        "total_no_encontrado": "600.00",
        "total_registrado": "600.00",
        "unidades_encontrado": 0,
        "unidades_no_encontrado": 1,
        "unidades_registrado": 1,
    }
    faltan = {x["nombre"]: x for x in informe["no_encontrados"]}
    assert set(faltan) == {"E", "F"}
    assert faltan["E"]["en_reparacion"] is True
    assert faltan["F"]["en_reparacion"] is False
    assert faltan["E"]["categoria"] == {"id": c.mob, "nombre": "Mobiliario"}
    assert faltan["F"]["ubicacion"] == {"id": c.bodega, "ruta": "Bodega"}
    assert faltan["F"]["precio"] == "600.00"


def test_empty_session_closes_with_zeros(client):
    c = Clinica(client)
    sesion = c.abrir()
    informe = cerrar(client, sesion).get_json()
    assert informe["totales"]["registrado"] == "0.00"
    assert informe["desglose"] == {"categorias": [], "ubicaciones": []}
    assert informe["no_encontrados"] == []


# --- Cuadre al azar (R3) -------------------------------------------------------------------


def test_random_inventory_reconciles_with_zero_differences(client, cie_db):
    rnd = random.Random(20261114)  # noqa: S311 - datos de prueba, no criptografía
    c = Clinica(client)
    lugares = [c.box, c.sala, c.bodega]
    ids = []
    for n in range(60):
        precio = f"{rnd.randint(0, 9_999_999)}.{rnd.randint(0, 99):02d}"
        ids.append(c.activo(f"R{n}", precio, rnd.choice([c.bio, c.mob]), rnd.choice(lugares)))
    for activo_id in ids:
        if rnd.random() < 0.15:
            c.reparacion(activo_id)
    sesion = c.abrir()
    for activo_id in ids:
        for _ in range(rnd.choice([0, 0, 1, 1, 2])):
            c.verificar(sesion, activo_id, rnd.choice(lugares))
            if rnd.random() < 0.3:
                c.precio(activo_id, f"{rnd.randint(1, 5_000_000)}.{rnd.randint(0, 99):02d}")
            if rnd.random() < 0.2:
                c.mover(activo_id, rnd.choice([x for x in lugares if x]))
    for activo_id in ids:
        if rnd.random() < 0.1:
            c.baja(activo_id)
    informe = cerrar(client, sesion).get_json()
    assert_cuadra(informe)

    # Cálculo independiente en SQL (DISTINCT ON) de las tres cifras.
    with cie_db.migrator.connect() as conn:
        encontrado, unidades_e = conn.execute(
            text(
                "select coalesce(sum(precio_al_contar), 0), count(*) from ("
                " select distinct on (activo_id) precio_al_contar from verificacion"
                " where sesion_id = :s order by activo_id, seq desc) v"
            ),
            {"s": sesion},
        ).one()
        no_encontrado, unidades_n = conn.execute(
            text(
                "select coalesce(sum(precio_compra), 0), count(*) from activo a"
                " where a.estado in ('activo', 'en_reparacion') and not exists"
                " (select 1 from verificacion v where v.sesion_id = :s and v.activo_id = a.id)"
            ),
            {"s": sesion},
        ).one()
    totales = informe["totales"]
    assert Decimal(totales["encontrado"]) == encontrado
    assert Decimal(totales["no_encontrado"]) == no_encontrado
    assert (totales["unidades_encontrado"], totales["unidades_no_encontrado"]) == (
        unidades_e,
        unidades_n,
    )


# --- Después del cierre (ADR-003, Q1, Q3) ----------------------------------------------------


def test_the_report_never_changes_after_closing(client, cie_db):
    c = Clinica(client)
    a = c.activo("A", "100.00")
    b = c.activo("B", "200.00", ubicacion=c.bodega)
    sesion = c.abrir()
    c.verificar(sesion, a)
    antes = cerrar(client, sesion).get_json()

    c.precio(b, "9999.00")
    c.precio(a, "1.00")
    c.mover(b, c.sala)
    c.baja(a)
    client.patch(f"/categorias/{c.bio}", json={"nombre": "Equipos"}, headers=ADMIN)
    client.patch(f"/ubicaciones/{c.bodega}", json={"nombre": "Almacén"}, headers=ADMIN)

    despues = client.get(f"/sesiones/{sesion}/informe", headers=ADMIN)
    assert despues.status_code == 200
    assert despues.get_json() == antes
    # Q1: cerrar otra vez devuelve lo mismo y no reinserta nada.
    otra = cerrar(client, sesion)
    assert otra.status_code == 200
    assert otra.get_json() == antes
    with cie_db.migrator.connect() as conn:
        assert (
            conn.scalar(
                text("select count(*) from sesion_no_encontrado where sesion_id = :s"),
                {"s": sesion},
            )
            == 1
        )
        assert (
            conn.scalar(
                text("select count(*) from sesion_desglose where sesion_id = :s"), {"s": sesion}
            )
            == 3  # una categoría y dos ubicaciones
        )


def test_after_closing_verifications_are_rejected_and_a_new_session_can_open(client):
    c = Clinica(client)
    a = c.activo("A", "10.00")
    sesion = c.abrir()
    cerrar(client, sesion)
    body = {
        "id": str(uuid.uuid4()),
        "activo_id": a,
        "ubicacion_encontrada_id": c.box,
        "estado_fisico": "ok",
    }
    response = client.post(f"/sesiones/{sesion}/verificaciones", json=body, headers=CONTADOR)
    assert response.status_code == 409
    assert code(response) == "sesion_cerrada"
    assert client.get("/sesiones/abierta", headers=CONTADOR).get_json() == {"sesion": None}
    assert c.abrir() != sesion


# --- Concurrencia (R4) -----------------------------------------------------------------------


def test_close_waits_for_a_verification_in_progress_and_includes_it(client, cie_db):
    c = Clinica(client)
    a = c.activo("A", "123.45")
    sesion = c.abrir()
    resultado = {}
    with cie_db.migrator.connect() as conn:
        trans = conn.begin()
        # Una verificación en curso: tiene el candado compartido y su fila sin confirmar.
        conn.execute(
            text("select pg_advisory_xact_lock_shared(hashtextextended(:k, 0))"),
            {"k": f"sesion_conteo:{sesion}"},
        )
        conn.execute(
            text(
                "insert into verificacion (id, tenant_id, sesion_id, activo_id, "
                "ubicacion_esperada_id, ubicacion_encontrada_id, estado_fisico, "
                "precio_al_contar, categoria_al_contar, verificado_por) "
                "values (gen_random_uuid(), :t, :s, :a, :u, :u, 'ok', 123.45, :c, :p)"
            ),
            {
                "t": TENANT_A,
                "s": sesion,
                "a": a,
                "u": c.box,
                "c": c.bio,
                "p": CONTADOR_A.usuario_id,
            },
        )
        hilo = threading.Thread(target=lambda: resultado.update(r=cerrar(client, sesion)))
        hilo.start()
        hilo.join(timeout=0.5)
        assert hilo.is_alive(), "el cierre no esperó a la verificación en curso"
        trans.commit()
    hilo.join(timeout=10)
    informe = resultado["r"].get_json()
    assert informe["totales"]["encontrado"] == "123.45"
    assert informe["totales"]["unidades_no_encontrado"] == 0


def test_an_uncommitted_asset_edit_stays_entirely_out(client, cie_db):
    c = Clinica(client)
    a = c.activo("A", "50.00")
    sesion = c.abrir()
    with cie_db.migrator.connect() as conn:
        trans = conn.begin()
        conn.execute(text("update activo set precio_compra = 9999 where id = :a"), {"a": a})
        response = cerrar(client, sesion)  # no espera: lee la versión confirmada
        trans.commit()
    assert response.status_code == 200
    assert response.get_json()["totales"]["no_encontrado"] == "50.00"


# --- Roles y estados ---------------------------------------------------------------------------


def test_only_the_admin_closes_and_reads_and_open_sessions_have_no_report(client):
    c = Clinica(client)
    sesion = c.abrir()
    abierta = client.get(f"/sesiones/{sesion}/informe", headers=ADMIN)
    assert abierta.status_code == 409
    assert code(abierta) == "sesion_abierta"
    assert cerrar(client, sesion, CONTADOR).status_code == 403
    assert client.get(f"/sesiones/{sesion}/informe", headers=CONTADOR).status_code == 403
    assert cerrar(client, sesion, ADMIN_OTRO).status_code == 404
    assert cerrar(client, str(uuid.uuid4())).status_code == 404
    assert cerrar(client, sesion, {}).status_code == 401
    assert client.get(f"/sesiones/{sesion}/informe", headers=ADMIN_OTRO).status_code == 404
