"""Detalle por activo y empresa congelados al cerrar (spec 013, T3; R3, R4, R8 Q1 A; A2).

- El cierre guarda una fila de ``sesion_detalle`` por activo de U (la misma lista del
  desglose), con marca, serial, dónde se encontró y estado físico de la verificación
  vigente; sus sumas por categoría y por ubicación son **iguales** al desglose.
- Guarda también la empresa vigente (o el nombre del tenant) en ``sesion_empresa``.
- Nada de eso cambia si después cambian la empresa, el logo, nombres, precios o lugares.
- Sesiones cerradas antes de la 013 (sin copia): el informe da los datos vigentes,
  rotulados (``vigente: true``), y ``detalle_disponible: false`` (Q1 A).
"""

import io
import uuid
from collections import defaultdict
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from acceso_db import (
    ADMIN_A,
    CONTADOR_A,
    TENANT_A,
    AccesoDb,
    bearer,
    dispose,
    make_app,
    temporary_acceso_db,
)
from flask import Flask
from PIL import Image
from sqlalchemy import text

from app.conteo import cierre
from app.db import tenant_session
from app.fotos.almacen import EXTENSION_KEY, CarpetaLocal

ADMIN = bearer(ADMIN_A, TENANT_A)
CONTADOR = bearer(CONTADOR_A, TENANT_A, rol="contador")
EMPRESA = {
    "nombre": "Clínica Dental Ejemplo S.A.S.",
    "direccion": "Calle 10 # 5-20, Cartago",
    "nit": "890903938-8",
    "telefono": "(602) 210 0000",
    "correo": "contacto@clinica-ejemplo.co",
}
LIMPIAR = (
    "delete from sesion_detalle",
    "delete from sesion_empresa",
    "update empresa set logo_id = null",
    "delete from empresa",
    "delete from empresa_logo",
    "delete from sesion_no_encontrado",
    "delete from sesion_desglose",
    "delete from activo_evento",
    "delete from verificacion",
    "delete from sesion_conteo",
    "delete from activo",
    "delete from ubicacion",
    "delete from categoria",
)


@pytest.fixture(scope="module")
def det_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("cierre_detalle")


@pytest.fixture(scope="module")
def det_app(det_db, tmp_path_factory) -> Iterator[Flask]:
    flask_app = make_app(det_db)
    flask_app.extensions[EXTENSION_KEY] = CarpetaLocal(Path(tmp_path_factory.mktemp("almacen")))
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(det_app):
    return det_app.test_client(use_cookies=False)


@pytest.fixture(autouse=True)
def limpio(det_db) -> Iterator[None]:
    yield
    with det_db.migrator.begin() as conn:
        for sql in LIMPIAR:
            conn.execute(text(sql))


def _post(client, path, body, headers=ADMIN):
    response = client.post(path, json=body, headers=headers)
    assert response.status_code in (200, 201), response.get_json()
    return response.get_json()


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (90, 30), (14, 116, 144, 255)).save(buffer, "PNG")
    return buffer.getvalue()


def _logo(client) -> str:
    logo_id = str(uuid.uuid4())
    response = client.put(
        "/empresa/logo",
        data={"logo_id": logo_id, "archivo": (io.BytesIO(_png()), "l.png")},
        headers=ADMIN,
        content_type="multipart/form-data",
    )
    assert response.status_code == 201, response.get_json()
    return logo_id


class Caso:
    def __init__(self, client):
        self.client = client
        sede = _post(client, "/ubicaciones", {"nombre": "Sede", "tipo": "sede"})["ubicacion"]["id"]
        self.sala = _post(
            client, "/ubicaciones", {"nombre": "Consultorios", "tipo": "sala", "padre_id": sede}
        )["ubicacion"]["id"]
        self.box = _post(
            client, "/ubicaciones", {"nombre": "Box 1", "tipo": "box", "padre_id": self.sala}
        )["ubicacion"]["id"]
        self.bodega = _post(
            client, "/ubicaciones", {"nombre": "Bodega", "tipo": "sala", "padre_id": sede}
        )["ubicacion"]["id"]
        self.bio = _post(client, "/categorias", {"nombre": "Biomédicos"})["categoria"]["id"]
        self.mob = _post(client, "/categorias", {"nombre": "Mobiliario"})["categoria"]["id"]
        self.version: dict[str, int] = {}

    def activo(self, nombre, precio, categoria=None, ubicacion=None, **extra) -> str:
        body = {
            "id": str(uuid.uuid4()),
            "codigo": f"AC-{uuid.uuid4().hex[:6].upper()}",
            "nombre": nombre,
            "precio_compra": precio,
            "categoria_id": categoria or self.bio,
            "ubicacion_id": ubicacion or self.box,
            **extra,
        }
        activo = _post(self.client, "/activos", body)["activo"]
        self.version[activo["id"]] = activo["row_version"]
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

    def abrir(self) -> str:
        return _post(
            self.client, "/sesiones", {"nombre": "Inventario 2026", "fecha_corte": "2026-11-30"}
        )["sesion"]["id"]

    def verificar(self, sesion, activo_id, ubicacion=None, estado="ok"):
        body = {
            "id": str(uuid.uuid4()),
            "activo_id": activo_id,
            "ubicacion_encontrada_id": ubicacion or self.box,
            "estado_fisico": estado,
        }
        _post(self.client, f"/sesiones/{sesion}/verificaciones", body, CONTADOR)

    def cerrar(self, sesion) -> dict:
        response = self.client.post(f"/sesiones/{sesion}/cerrar", headers=ADMIN)
        assert response.status_code == 200, response.get_json()
        return self.client.get(f"/sesiones/{sesion}/informe", headers=ADMIN).get_json()


def _detalle(det_app, sesion) -> list:
    with det_app.app_context(), tenant_session(TENANT_A) as session:
        sesion_db = session.get(cierre.SesionConteo, uuid.UUID(sesion))
        return [
            {
                "activo_id": str(f.activo_id),
                "codigo": f.codigo,
                "nombre": f.nombre,
                "marca": f.marca,
                "serial": f.serial,
                "categoria_id": str(f.categoria_id),
                "categoria": f.categoria_nombre,
                "ubicacion_id": str(f.ubicacion_id),
                "ubicacion": f.ubicacion_ruta,
                "encontrada": f.encontrada_ruta,
                "estado": f.estado_fisico,
                "encontrado": f.encontrado,
                "en_reparacion": f.en_reparacion,
                "precio": f.precio,
            }
            for f in cierre.detalle(session, sesion_db)
        ]


def _armar(client):
    c = Caso(client)
    ids = {
        "a": c.activo("Unidad odontológica", "1000.50", marca="Sirona", serial="SN-1"),
        "b": c.activo("Autoclave", "2000.00", ubicacion=c.sala),
        "d": c.activo("Silla", "300.00", categoria=c.mob, marca="Rimax"),
        "e": c.activo("Lámpara", "400.00"),
        "f": c.activo("Mesa", "500.00", categoria=c.mob, ubicacion=c.bodega),
        "g": c.activo("De baja", "600.00"),
    }
    c.cambiar(ids["e"], "/estado", {"estado": "en_reparacion"})
    c.cambiar(ids["g"], "/baja", {"motivo": "perdido"})
    sesion = c.abrir()
    c.verificar(sesion, ids["a"])
    c.verificar(sesion, ids["b"], c.bodega)  # encontrado en otro lugar
    c.verificar(sesion, ids["d"], estado="danado")
    return c, ids, sesion


def test_detail_has_one_row_per_asset_of_u_with_its_frozen_data(client, det_app):
    c, ids, sesion = _armar(client)
    c.cerrar(sesion)
    filas = {f["activo_id"]: f for f in _detalle(det_app, sesion)}
    assert set(filas) == {ids[k] for k in "abdef"}  # el dado de baja no está en U
    a, b, d, e, f = (filas[ids[k]] for k in "abdef")
    assert (a["marca"], a["serial"], a["estado"], a["encontrado"]) == ("Sirona", "SN-1", "ok", True)
    assert (a["ubicacion"], a["encontrada"]) == ("Consultorios › Box 1", "Consultorios › Box 1")
    assert (b["ubicacion"], b["encontrada"]) == ("Consultorios", "Bodega")
    assert d["estado"] == "danado" and d["categoria"] == "Mobiliario"
    assert (e["encontrado"], e["en_reparacion"], e["estado"], e["encontrada"]) == (
        False,
        True,
        None,
        None,
    )
    assert (f["encontrado"], f["ubicacion"]) == (False, "Bodega")
    assert a["precio"] == Decimal("1000.50")


def test_detail_sums_are_equal_to_the_frozen_breakdown(client, det_app):
    _, _, sesion = _armar(client)
    informe = Caso.cerrar(type("C", (), {"client": client})(), sesion)
    filas = _detalle(det_app, sesion)
    for dimension, clave in (("categorias", "categoria_id"), ("ubicaciones", "ubicacion_id")):
        sumas: dict[str, list] = defaultdict(lambda: [Decimal("0"), 0, Decimal("0"), 0])
        for f in filas:
            s = sumas[f[clave]]
            if f["encontrado"]:
                s[0] += f["precio"]
                s[1] += 1
            else:
                s[2] += f["precio"]
                s[3] += 1
        desglose = {r["id"]: r for r in informe["desglose"][dimension]}
        assert set(desglose) == set(sumas)
        for id_, (enc, uenc, noe, unoe) in sumas.items():
            r = desglose[id_]
            assert (Decimal(r["total_encontrado"]), r["unidades_encontrado"]) == (enc, uenc)
            assert (Decimal(r["total_no_encontrado"]), r["unidades_no_encontrado"]) == (noe, unoe)
    no_encontrados = {f["activo_id"] for f in informe["no_encontrados"]}
    assert no_encontrados == {f["activo_id"] for f in filas if not f["encontrado"]}


def test_company_is_frozen_at_close_and_later_changes_do_not_alter_anything(client, det_app):
    assert client.put("/empresa", json=EMPRESA, headers=ADMIN).status_code == 200
    logo = _logo(client)
    c, ids, sesion = _armar(client)
    informe = c.cerrar(sesion)
    assert informe["empresa"] == {
        "nombre": EMPRESA["nombre"],
        "direccion": EMPRESA["direccion"],
        "nit": "890.903.938-8",
        "telefono": EMPRESA["telefono"],
        "correo": EMPRESA["correo"],
        "logo": {"id": logo},
        "vigente": False,
    }
    assert informe["detalle_disponible"] is True
    antes = _detalle(det_app, sesion)

    # Cambios posteriores: empresa, logo, nombre, precio, categoría y lugar.
    client.put("/empresa", json={**EMPRESA, "nombre": "Otra S.A.S.", "nit": ""}, headers=ADMIN)
    _logo(client)
    c.cambiar(ids["a"], "", {"nombre": "Renombrada", "precio_compra": "9.99"}, "PATCH")
    c.cambiar(ids["f"], "/mover", {"ubicacion_id": c.box})
    c.cambiar(ids["f"], "", {"categoria_id": c.bio}, "PATCH")

    despues = client.get(f"/sesiones/{sesion}/informe", headers=ADMIN).get_json()
    assert despues == informe
    assert _detalle(det_app, sesion) == antes


def test_without_company_the_copy_uses_the_tenant_name(client):
    c = Caso(client)
    c.activo("Silla", "10.00")
    sesion = c.abrir()
    informe = c.cerrar(sesion)
    assert informe["empresa"] == {
        "nombre": "Clínica sintética A8",
        "direccion": None,
        "nit": None,
        "telefono": None,
        "correo": None,
        "logo": None,
        "vigente": False,
    }


def test_empty_session_still_freezes_the_company_and_no_rows(client, det_app):
    client.put("/empresa", json=EMPRESA, headers=ADMIN)
    sesion = Caso(client).abrir()
    informe = Caso.cerrar(type("C", (), {"client": client})(), sesion)
    assert informe["empresa"]["nombre"] == EMPRESA["nombre"]
    assert informe["detalle_disponible"] is True
    assert _detalle(det_app, sesion) == []


def test_session_closed_before_013_uses_current_company_labelled(client, det_db, det_app):
    c, _, sesion = _armar(client)
    c.cerrar(sesion)
    # Simula una sesión cerrada antes de la 013: sin copia de la empresa ni detalle.
    with det_db.migrator.begin() as conn:
        conn.execute(text("delete from sesion_detalle"))
        conn.execute(text("delete from sesion_empresa"))
    client.put("/empresa", json=EMPRESA, headers=ADMIN)
    informe = client.get(f"/sesiones/{sesion}/informe", headers=ADMIN).get_json()
    assert informe["empresa"]["nombre"] == EMPRESA["nombre"]
    assert informe["empresa"]["vigente"] is True
    assert informe["detalle_disponible"] is False
    assert _detalle(det_app, sesion) == []


def test_closing_twice_does_not_insert_again(client, det_db):
    c, _, sesion = _armar(client)
    c.cerrar(sesion)
    assert client.post(f"/sesiones/{sesion}/cerrar", headers=ADMIN).status_code == 200
    with det_db.migrator.connect() as conn:
        assert conn.scalar(text("select count(*) from sesion_detalle")) == 5
        assert conn.scalar(text("select count(*) from sesion_empresa")) == 1


def test_detail_is_ordered_by_category_result_and_code(client, det_app):
    c, _, sesion = _armar(client)
    c.cerrar(sesion)
    filas = _detalle(det_app, sesion)
    claves = [(f["categoria"].lower(), not f["encontrado"], f["codigo"]) for f in filas]
    assert claves == sorted(claves)
