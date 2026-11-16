"""Foto de una verificación (spec 012, T5; R6, R7; A1).

- Quien verificó (o un admin) agrega una foto mientras la sesión está abierta; otro
  contador ``403``; sesión cerrada ``409 sesion_cerrada``; una por verificación.
- La verificación y el historial del activo dicen qué foto tiene.
"""

import io
import uuid
from collections.abc import Iterator

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

from app.fotos.almacen import EXTENSION_KEY, CarpetaLocal

ADMIN = bearer(ADMIN_A, TENANT_A)
CONTADOR = bearer(CONTADOR_A, TENANT_A, rol="contador")


@pytest.fixture(scope="module")
def ver_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("fotos_ver")


@pytest.fixture(scope="module")
def ver_app(ver_db, tmp_path_factory) -> Iterator[Flask]:
    flask_app = make_app(ver_db)
    flask_app.extensions[EXTENSION_KEY] = CarpetaLocal(tmp_path_factory.mktemp("almacen"))
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(ver_app):
    return ver_app.test_client(use_cookies=False)


def _post(client, ruta, body, headers=ADMIN) -> dict:
    response = client.post(ruta, json=body, headers=headers)
    assert response.status_code in (200, 201), response.get_json()
    return response.get_json()


@pytest.fixture(scope="module")
def escenario(ver_app) -> dict[str, str]:
    client = ver_app.test_client(use_cookies=False)
    sede = _post(client, "/ubicaciones", {"nombre": "Sede", "tipo": "sede"})["ubicacion"]["id"]
    sala = _post(client, "/ubicaciones", {"nombre": "Sala", "tipo": "sala", "padre_id": sede})[
        "ubicacion"
    ]["id"]
    cat = _post(client, "/categorias", {"nombre": "Cat"})["categoria"]["id"]
    sesion = _post(client, "/sesiones", {"nombre": "Conteo", "fecha_corte": "2026-11-15"})
    return {"sala": sala, "cat": cat, "sid": sesion["sesion"]["id"]}


def _activo(client, e) -> str:
    return _post(
        client,
        "/activos",
        {
            "id": str(uuid.uuid4()),
            "codigo": f"FV-{uuid.uuid4().hex[:6].upper()}",
            "nombre": "Lámpara",
            "categoria_id": e["cat"],
            "ubicacion_id": e["sala"],
            "precio_compra": "10.00",
        },
    )["activo"]["id"]


def _verificar(client, e, activo_id, headers) -> str:
    vid = str(uuid.uuid4())
    _post(
        client,
        f"/sesiones/{e['sid']}/verificaciones",
        {
            "id": vid,
            "activo_id": activo_id,
            "ubicacion_encontrada_id": e["sala"],
            "estado_fisico": "danado",
        },
        headers,
    )
    return vid


def _subir(client, e, vid, headers, foto_id=None):
    buffer = io.BytesIO()
    Image.new("RGB", (60, 40), (90, 10, 10)).save(buffer, "JPEG")
    buffer.seek(0)
    form = {"foto_id": foto_id or str(uuid.uuid4()), "archivo": (buffer, "dano.jpg")}
    return client.put(
        f"/sesiones/{e['sid']}/verificaciones/{vid}/foto",
        data=form,
        headers=headers,
        content_type="multipart/form-data",
    )


def test_who_verified_adds_the_photo_and_it_shows_up(client, escenario):
    activo = _activo(client, escenario)
    vid = _verificar(client, escenario, activo, CONTADOR)
    subida = _subir(client, escenario, vid, CONTADOR)
    assert subida.status_code == 201, subida.get_json()
    foto_id = subida.get_json()["foto"]["id"]
    ultima = client.get(
        f"/sesiones/{escenario['sid']}/verificaciones?activo_id={activo}", headers=CONTADOR
    ).get_json()["verificacion"]
    assert ultima["foto_id"] == foto_id
    historial = client.get(f"/activos/{activo}/historial", headers=CONTADOR).get_json()["eventos"]
    verificado = next(e for e in historial if e["tipo"] == "verificado")
    assert verificado["foto_id"] == foto_id
    assert client.get(f"/fotos/{foto_id}", headers=CONTADOR).status_code == 200
    # La foto de la verificación no es la principal del activo.
    assert client.get(f"/activos/{activo}", headers=ADMIN).get_json()["activo"]["foto"] is None
    otra = _subir(client, escenario, vid, ADMIN)
    assert (otra.status_code, otra.get_json()["error"]["code"]) == (409, "foto_existente")


def test_only_who_verified_or_an_admin(client, escenario):
    activo = _activo(client, escenario)
    vid = _verificar(client, escenario, activo, ADMIN)
    ajena = _subir(client, escenario, vid, CONTADOR)
    assert (ajena.status_code, ajena.get_json()["error"]["code"]) == (403, "prohibido")
    assert _subir(client, escenario, vid, ADMIN).status_code == 201
    sin_foto = _verificar(client, escenario, _activo(client, escenario), ADMIN)
    ultima = client.get(
        f"/sesiones/{escenario['sid']}/verificaciones?activo_id={activo}", headers=ADMIN
    ).get_json()["verificacion"]
    assert ultima["foto_id"] is not None
    assert sin_foto


def test_closed_session_refuses_new_photos(client, escenario, ver_app):
    activo = _activo(client, escenario)
    vid = _verificar(client, escenario, activo, ADMIN)
    cierre = client.post(f"/sesiones/{escenario['sid']}/cerrar", headers=ADMIN)
    assert cierre.status_code == 200, cierre.get_json()
    cerrada = _subir(client, escenario, vid, ADMIN)
    assert (cerrada.status_code, cerrada.get_json()["error"]["code"]) == (409, "sesion_cerrada")
