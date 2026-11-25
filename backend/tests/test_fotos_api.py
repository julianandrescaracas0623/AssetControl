"""API de la foto principal (spec 012, T4; R1, R2, R4, R5, R7, R8, Q1 B, Q2 B; A1).

Sobre una base temporal con dos tenants y el almacenamiento en una carpeta temporal:

- Subir (admin o contador): ``201``, la ficha la muestra, ``GET /fotos/{id}`` entrega un
  JPEG sin metadatos; reintentar con el mismo ``id`` → ``200`` sin otro evento.
- Cambiar y quitar (los dos roles, Q1 B): la anterior queda retirada, su imagen se borra
  del almacenamiento (Q2 B) y ya no se entrega; eventos ``foto_*`` en el historial.
- Errores: tipo, tamaño, bomba, formulario incompleto, activo de otro tenant o dado de
  baja, ``id`` usado en otro activo, fotos desactivadas; si la transacción falla, no
  quedan imágenes sin fila.
"""

import io
import threading
import uuid
from collections.abc import Iterator
from pathlib import Path

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
from PIL import Image
from sqlalchemy import text

from app.fotos import cupo as fotos_cupo
from app.fotos import imagen as fotos_imagen
from app.fotos import service as fotos_service
from app.fotos.almacen import EXTENSION_KEY, CarpetaLocal

ADMIN = bearer(ADMIN_A, TENANT_A)
CONTADOR = bearer(CONTADOR_A, TENANT_A, rol="contador")
ADMIN_OTRO = bearer(ADMIN_B, TENANT_B)


@pytest.fixture(scope="module")
def foto_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("fotos_api")


@pytest.fixture(scope="module")
def carpeta(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("almacen")


@pytest.fixture(scope="module")
def foto_app(foto_db, carpeta) -> Iterator[Flask]:
    flask_app = make_app(foto_db)
    flask_app.extensions[EXTENSION_KEY] = CarpetaLocal(carpeta)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(foto_app):
    return foto_app.test_client(use_cookies=False)


@pytest.fixture(scope="module")
def cat(foto_app) -> dict[str, str]:
    client = foto_app.test_client(use_cookies=False)

    def post(ruta, body, headers=ADMIN):
        response = client.post(ruta, json=body, headers=headers)
        assert response.status_code == 201, response.get_json()
        return response.get_json()

    ids = {}
    ids["sede"] = post("/ubicaciones", {"nombre": "Sede", "tipo": "sede"})["ubicacion"]["id"]
    ids["sala"] = post("/ubicaciones", {"nombre": "Sala", "tipo": "sala", "padre_id": ids["sede"]})[
        "ubicacion"
    ]["id"]
    ids["cat"] = post("/categorias", {"nombre": "Biomédicos"})["categoria"]["id"]
    sede_b = post("/ubicaciones", {"nombre": "Sede B", "tipo": "sede"}, ADMIN_OTRO)["ubicacion"]
    ids["sala_b"] = post(
        "/ubicaciones", {"nombre": "Sala B", "tipo": "sala", "padre_id": sede_b["id"]}, ADMIN_OTRO
    )["ubicacion"]["id"]
    ids["cat_b"] = post("/categorias", {"nombre": "Cat B"}, ADMIN_OTRO)["categoria"]["id"]
    return ids


def nuevo_activo(client, cat, headers=ADMIN, sufijo="") -> dict:
    body = {
        "id": str(uuid.uuid4()),
        "codigo": f"FT-{uuid.uuid4().hex[:6].upper()}",
        "nombre": "Autoclave",
        "categoria_id": cat[f"cat{sufijo}"],
        "ubicacion_id": cat[f"sala{sufijo}"],
        "precio_compra": "100.00",
    }
    response = client.post("/activos", json=body, headers=headers)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["activo"]


def jpeg(tamano=(800, 600), color=(10, 120, 200), gps=False) -> bytes:
    buffer = io.BytesIO()
    kw = {}
    if gps:
        exif = Image.Exif()
        exif.get_ifd(0x8825).update({1: "N", 2: (4.0, 44.0, 0.0)})
        kw["exif"] = exif.tobytes()
    Image.new("RGB", tamano, color).save(buffer, "JPEG", **kw)
    return buffer.getvalue()


def subir(client, activo_id, datos=None, foto_id=None, headers=ADMIN):
    foto_id = foto_id or str(uuid.uuid4())
    form = {"foto_id": foto_id, "archivo": (io.BytesIO(datos or jpeg()), "IMG_0001.jpg")}
    return client.put(
        f"/activos/{activo_id}/foto", data=form, headers=headers, content_type="multipart/form-data"
    )


def ficha(client, activo_id, headers=ADMIN) -> dict:
    return client.get(f"/activos/{activo_id}", headers=headers).get_json()["activo"]


def eventos(client, activo_id) -> list[dict]:
    return client.get(f"/activos/{activo_id}/historial", headers=ADMIN).get_json()["eventos"]


def archivos(carpeta: Path) -> set[str]:
    return {p.name for p in carpeta.rglob("*.jpg")}


def test_upload_shows_in_the_card_and_is_served_without_metadata(client, cat, carpeta):
    activo = nuevo_activo(client, cat)
    assert ficha(client, activo["id"])["foto"] is None
    respuesta = subir(client, activo["id"], jpeg((3000, 2000), gps=True))
    assert respuesta.status_code == 201, respuesta.get_json()
    foto = respuesta.get_json()["foto"]
    assert (foto["ancho"], foto["alto"]) == (1600, 1067)
    assert ficha(client, activo["id"])["foto"] == foto
    porcodigo = client.get(f"/activos/por-codigo?codigo={activo['codigo']}", headers=CONTADOR)
    assert porcodigo.get_json()["activo"]["foto"]["id"] == foto["id"]

    imagen = client.get(f"/fotos/{foto['id']}", headers=CONTADOR)
    assert imagen.status_code == 200
    assert imagen.mimetype == "image/jpeg"
    assert imagen.headers["Cache-Control"] == "private, max-age=86400"
    assert imagen.headers["X-Content-Type-Options"] == "nosniff"
    salida = Image.open(io.BytesIO(imagen.data))
    assert salida.size == (1600, 1067) and not salida.getexif()
    mini = client.get(f"/fotos/{foto['id']}?tamano=mini", headers=ADMIN)
    assert max(Image.open(io.BytesIO(mini.data)).size) == 320
    assert {f"{foto['id']}.jpg", f"{foto['id']}_mini.jpg"} <= archivos(carpeta)
    assert "IMG_0001" not in "".join(archivos(carpeta))
    assert [e["tipo"] for e in eventos(client, activo["id"])][:1] == ["foto_agregada"]


def test_retry_with_the_same_id_returns_the_same_photo(client, cat):
    activo = nuevo_activo(client, cat, headers=CONTADOR)
    foto_id = str(uuid.uuid4())
    primera = subir(client, activo["id"], foto_id=foto_id, headers=CONTADOR)
    otra = subir(client, activo["id"], foto_id=foto_id, headers=CONTADOR)
    assert (primera.status_code, otra.status_code) == (201, 200)
    assert otra.get_json() == primera.get_json()
    assert [e["tipo"] for e in eventos(client, activo["id"])].count("foto_agregada") == 1


def test_both_roles_change_and_remove_and_the_old_image_is_deleted(client, cat, carpeta):
    activo = nuevo_activo(client, cat)
    vieja = subir(client, activo["id"]).get_json()["foto"]
    nueva = subir(client, activo["id"], jpeg(color=(200, 0, 0)), headers=CONTADOR)
    assert nueva.status_code == 201
    nueva = nueva.get_json()["foto"]
    assert ficha(client, activo["id"])["foto"]["id"] == nueva["id"]
    assert client.get(f"/fotos/{vieja['id']}", headers=ADMIN).status_code == 404
    assert f"{vieja['id']}.jpg" not in archivos(carpeta)
    assert f"{vieja['id']}_mini.jpg" not in archivos(carpeta)
    cambio = eventos(client, activo["id"])[0]
    assert cambio["tipo"] == "foto_cambiada"
    assert cambio["datos"] == {"antes": vieja["id"], "despues": nueva["id"]}

    assert client.delete(f"/activos/{activo['id']}/foto", headers=CONTADOR).status_code == 204
    assert ficha(client, activo["id"])["foto"] is None
    assert client.get(f"/fotos/{nueva['id']}", headers=ADMIN).status_code == 404
    assert f"{nueva['id']}.jpg" not in archivos(carpeta)
    assert eventos(client, activo["id"])[0]["tipo"] == "foto_retirada"
    otra_vez = client.delete(f"/activos/{activo['id']}/foto", headers=ADMIN)
    assert (otra_vez.status_code, otra_vez.get_json()["error"]["code"]) == (404, "sin_foto")


def _codigo(respuesta) -> tuple[int, str]:
    return respuesta.status_code, respuesta.get_json()["error"]["code"]


def test_bad_uploads_are_refused(client, cat, carpeta):
    activo = nuevo_activo(client, cat)
    antes = archivos(carpeta)
    gif = io.BytesIO()
    Image.new("P", (10, 10)).save(gif, "GIF")
    assert _codigo(subir(client, activo["id"], gif.getvalue())) == (415, "tipo_no_admitido")
    bomba = io.BytesIO()
    Image.new("L", (10_000, 10_000)).save(bomba, "PNG")
    assert _codigo(subir(client, activo["id"], bomba.getvalue())) == (422, "imagen_invalida")
    grande = b"\xff\xd8" + b"0" * (10 * 1024 * 1024)
    assert _codigo(subir(client, activo["id"], grande)) == (413, "imagen_demasiado_grande")
    enorme = b"0" * (11 * 1024 * 1024)
    assert _codigo(subir(client, activo["id"], enorme)) == (413, "cuerpo_demasiado_grande")
    sin_id = client.put(
        f"/activos/{activo['id']}/foto",
        data={"archivo": (io.BytesIO(jpeg()), "x.jpg")},
        headers=ADMIN,
        content_type="multipart/form-data",
    )
    assert _codigo(sin_id) == (400, "solicitud_invalida")
    sin_archivo = client.put(
        f"/activos/{activo['id']}/foto",
        data={"foto_id": str(uuid.uuid4())},
        headers=ADMIN,
        content_type="multipart/form-data",
    )
    assert _codigo(sin_archivo) == (400, "solicitud_invalida")
    assert archivos(carpeta) == antes
    assert ficha(client, activo["id"])["foto"] is None


def test_other_tenant_and_misused_ids(client, cat, foto_db):
    activo = nuevo_activo(client, cat)
    foto = subir(client, activo["id"]).get_json()["foto"]
    ajeno = nuevo_activo(client, cat, headers=ADMIN_OTRO, sufijo="_b")
    assert _codigo(subir(client, ajeno["id"])) == (404, "no_encontrado")
    assert client.get(f"/fotos/{foto['id']}", headers=ADMIN_OTRO).status_code == 404
    assert client.delete(f"/activos/{activo['id']}/foto", headers=ADMIN_OTRO).status_code == 404
    otro = nuevo_activo(client, cat)
    assert _codigo(subir(client, otro["id"], foto_id=foto["id"])) == (409, "foto_id_en_uso")
    # El mismo id desde otro tenant (la RLS no lo deja ver): 409 y nada guardado.
    assert _codigo(subir(client, ajeno["id"], foto_id=foto["id"], headers=ADMIN_OTRO)) == (
        409,
        "foto_id_en_uso",
    )
    assert ficha(client, ajeno["id"], headers=ADMIN_OTRO)["foto"] is None
    with foto_db.migrator.begin() as conn:
        conn.execute(
            text("update activo set estado = 'dado_de_baja' where id = :i"), {"i": otro["id"]}
        )
    assert _codigo(subir(client, otro["id"])) == (409, "activo_dado_de_baja")
    assert client.get(f"/fotos/{uuid.uuid4()}", headers=ADMIN).status_code == 404
    assert _codigo(client.get(f"/fotos/{foto['id']}?tamano=gigante", headers=ADMIN)) == (
        400,
        "solicitud_invalida",
    )
    assert client.get(f"/fotos/{foto['id']}").status_code == 401


def test_photos_off_answer_503(client, cat, foto_app, monkeypatch):
    activo = nuevo_activo(client, cat)
    monkeypatch.setitem(foto_app.extensions, EXTENSION_KEY, None)
    assert _codigo(subir(client, activo["id"])) == (503, "fotos_no_disponibles")
    assert ficha(client, activo["id"])["foto"] is None


def test_a_failed_transaction_leaves_no_images(client, cat, carpeta, monkeypatch):
    activo = nuevo_activo(client, cat)
    antes = archivos(carpeta)

    def falla(*args, **kwargs):
        raise RuntimeError("falla sintética después de guardar la imagen")

    monkeypatch.setattr(fotos_service, "_evento", falla)
    assert subir(client, activo["id"]).status_code == 500
    assert archivos(carpeta) == antes
    assert ficha(client, activo["id"])["foto"] is None


def test_a_removed_photo_is_not_restored_by_a_retry(client, cat, carpeta):
    # SEC-04: reintentar con el id de una foto quitada no la devuelve a la ficha.
    activo = nuevo_activo(client, cat)
    foto_id = str(uuid.uuid4())
    assert subir(client, activo["id"], foto_id=foto_id).status_code == 201
    assert client.delete(f"/activos/{activo['id']}/foto", headers=ADMIN).status_code == 204
    antes = archivos(carpeta)
    reintento = subir(client, activo["id"], foto_id=foto_id)
    assert _codigo(reintento) == (409, "foto_retirada")
    assert ficha(client, activo["id"])["foto"] is None
    assert archivos(carpeta) == antes


def test_the_upload_limit_per_user_answers_429_before_reading_the_file(
    client, cat, carpeta, monkeypatch
):
    # SEC-02: con tope 2 por ventana, la tercera subida del usuario se rechaza sin guardar.
    monkeypatch.setattr(fotos_cupo, "SUBIDAS", fotos_cupo.VentanaDeSubidas(2, 600.0))
    activo = nuevo_activo(client, cat)
    assert subir(client, activo["id"]).status_code == 201
    assert subir(client, activo["id"], headers=ADMIN).status_code == 201  # reemplaza
    antes = archivos(carpeta)
    assert _codigo(subir(client, activo["id"])) == (429, "demasiadas_subidas")
    assert archivos(carpeta) == antes
    otro = subir(client, activo["id"], headers=CONTADOR)
    assert otro.status_code != 429  # el límite es por usuario, no global


def test_a_busy_decoder_answers_503_instead_of_queueing_forever(client, cat, carpeta, monkeypatch):
    # SEC-02: si todos los cupos de decodificación del proceso están ocupados, 503 tras la espera.
    ocupado = threading.BoundedSemaphore(1)
    ocupado.acquire()
    monkeypatch.setattr(fotos_imagen, "_CUPO_DECODIFICACION", ocupado)
    monkeypatch.setattr(fotos_imagen, "ESPERA_DECODIFICACION_SEGUNDOS", 0.05)
    activo = nuevo_activo(client, cat)
    antes = archivos(carpeta)
    assert _codigo(subir(client, activo["id"])) == (503, "procesado_ocupado")
    assert archivos(carpeta) == antes
    assert ficha(client, activo["id"])["foto"] is None
