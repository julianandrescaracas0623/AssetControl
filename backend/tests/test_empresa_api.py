"""API de la empresa y su logo (spec 013, T2; R1, R2, R9; A1).

Sobre una base temporal con dos tenants y el almacenamiento en una carpeta temporal:

- ``GET /empresa`` sin datos: el nombre del tenant y ``completa: false``.
- ``PUT /empresa``: obligatorios, límites, NIT con dígito de verificación (DIAN) y
  normalizado, correo y teléfono; vacío = sin dato; campos desconocidos ``400``.
- Logo: PNG/JPEG/WebP ≤ 2 MB, se guarda en PNG ≤ 600 px con transparencia y sin
  metadatos; cambiarlo o quitarlo no borra el anterior (R2); requiere la empresa guardada.
- Solo el admin (contador ``403``); cada tenant ve lo suyo.
"""

import io
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

from app.empresa import service as empresa_service
from app.fotos.almacen import EXTENSION_KEY, CarpetaLocal

ADMIN = bearer(ADMIN_A, TENANT_A)
CONTADOR = bearer(CONTADOR_A, TENANT_A, rol="contador")
ADMIN_OTRO = bearer(ADMIN_B, TENANT_B)
DATOS = {
    "nombre": "Clínica Dental Ejemplo S.A.S.",
    "direccion": "Calle 10 # 5-20, Cartago",
    "nit": "900123456-8",
    "telefono": "(602) 210 0000",
    "correo": "contacto@clinica-ejemplo.co",
}


@pytest.fixture(scope="module")
def emp_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("empresa_api")


@pytest.fixture(scope="module")
def carpeta(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("almacen")


@pytest.fixture(scope="module")
def emp_app(emp_db, carpeta) -> Iterator[Flask]:
    flask_app = make_app(emp_db)
    flask_app.extensions[EXTENSION_KEY] = CarpetaLocal(carpeta)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(emp_app):
    return emp_app.test_client(use_cookies=False)


def _png(tamano=(1200, 400), modo="RGBA", color=(14, 116, 144, 255), **kw) -> bytes:
    buffer = io.BytesIO()
    Image.new(modo, tamano, color).save(buffer, "PNG", **kw)
    return buffer.getvalue()


def _subir(client, datos: bytes, logo_id=None, headers=ADMIN):
    form = {"logo_id": str(logo_id or uuid.uuid4()), "archivo": (io.BytesIO(datos), "logo.png")}
    return client.put(
        "/empresa/logo", data=form, headers=headers, content_type="multipart/form-data"
    )


def _guardar(client, datos=None, headers=ADMIN):
    return client.put("/empresa", json=datos or DATOS, headers=headers)


# --- datos


def test_without_data_the_tenant_name_is_used_and_it_is_incomplete(client):
    response = client.get("/empresa", headers=ADMIN_OTRO)
    assert response.status_code == 200
    assert response.get_json()["empresa"] == {
        "nombre": "Clínica B8",
        "direccion": None,
        "nit": None,
        "telefono": None,
        "correo": None,
        "logo": None,
        "completa": False,
    }


def test_logo_needs_the_company_saved_first(client):
    response = _subir(client, _png(), headers=ADMIN_OTRO)
    assert response.status_code == 409
    assert response.get_json()["error"]["code"] == "empresa_sin_datos"


def test_save_and_read_back_with_normalized_nit(client):
    response = _guardar(client)
    assert response.status_code == 200, response.get_json()
    empresa = response.get_json()["empresa"]
    assert empresa["nit"] == "900.123.456-8"
    assert empresa["completa"] is True
    assert client.get("/empresa", headers=ADMIN).get_json()["empresa"] == empresa


@pytest.mark.parametrize(
    ("entrada", "guardado"),
    [
        ("900123456-8", "900.123.456-8"),
        ("900.123.456-8", "900.123.456-8"),
        ("900 123 456 - 8", "900.123.456-8"),
        ("800197268-4", "800.197.268-4"),
        ("900123456", "900.123.456"),
        ("1094123456", "1.094.123.456"),
    ],
)
def test_nit_is_normalized(client, entrada, guardado):
    response = _guardar(client, {**DATOS, "nit": entrada})
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["empresa"]["nit"] == guardado


@pytest.mark.parametrize("nit", ["900123456-7", "9001234560-2", "12-3", "ABC", "900123456-88"])
def test_wrong_nit_is_refused(client, nit):
    response = _guardar(client, {**DATOS, "nit": nit})
    assert response.status_code == 400
    error = response.get_json()["error"]
    assert error["code"] == "solicitud_invalida"
    assert error.get("campo") == "nit"


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("nombre", ""),
        ("nombre", "x" * 121),
        ("nombre", "Clínica‮al revés"),
        ("direccion", "   "),
        ("direccion", "y" * 201),
        ("telefono", "123"),
        ("telefono", "llámame"),
        ("correo", "no-es-correo"),
        ("correo", "a@b"),
    ],
)
def test_invalid_fields_are_refused_naming_the_field(client, campo, valor):
    response = _guardar(client, {**DATOS, campo: valor})
    assert response.status_code == 400
    assert response.get_json()["error"].get("campo") == campo


def test_optional_fields_can_be_cleared(client):
    response = _guardar(client, {**DATOS, "nit": "", "telefono": None, "correo": "  "})
    assert response.status_code == 200
    empresa = response.get_json()["empresa"]
    assert (empresa["nit"], empresa["telefono"], empresa["correo"]) == (None, None, None)
    assert empresa["completa"] is True


@pytest.mark.parametrize(
    "cuerpo",
    [
        {k: v for k, v in DATOS.items() if k != "direccion"},
        {**DATOS, "logo_id": str(uuid.uuid4())},
        {**DATOS, "tenant_id": str(TENANT_B)},
        ["no", "objeto"],
    ],
)
def test_missing_or_unknown_fields_are_refused(client, cuerpo):
    assert client.put("/empresa", json=cuerpo, headers=ADMIN).status_code == 400


def test_counter_cannot_read_or_change_the_company(client):
    assert client.get("/empresa", headers=CONTADOR).status_code == 403
    assert _guardar(client, headers=CONTADOR).status_code == 403
    assert _subir(client, _png(), headers=CONTADOR).status_code == 403
    assert client.delete("/empresa/logo", headers=CONTADOR).status_code == 403


def test_each_tenant_sees_its_own_company(client):
    _guardar(client)
    _guardar(client, {**DATOS, "nombre": "Otra empresa B", "nit": ""}, headers=ADMIN_OTRO)
    assert client.get("/empresa", headers=ADMIN).get_json()["empresa"]["nombre"] == DATOS["nombre"]
    otra = client.get("/empresa", headers=ADMIN_OTRO).get_json()["empresa"]
    assert otra["nombre"] == "Otra empresa B"


# --- logo


def test_logo_is_saved_as_png_without_metadata_keeping_transparency(client, carpeta):
    _guardar(client)
    logo_id = uuid.uuid4()
    entrada = io.BytesIO()
    Image.new("RGBA", (1800, 600), (0, 0, 0, 0)).save(
        entrada, "PNG", pnginfo=_texto("Autor", "teléfono de alguien")
    )
    response = _subir(client, entrada.getvalue(), logo_id)
    assert response.status_code == 201, response.get_json()
    assert response.get_json()["logo"] == {"id": str(logo_id), "ancho": 600, "alto": 200}
    assert client.get("/empresa", headers=ADMIN).get_json()["empresa"]["logo"] == {
        "id": str(logo_id)
    }

    imagen = client.get(f"/empresa/logo/{logo_id}", headers=ADMIN)
    assert imagen.status_code == 200
    assert imagen.mimetype == "image/png"
    assert imagen.headers["X-Content-Type-Options"] == "nosniff"
    assert "private" in imagen.headers["Cache-Control"]
    salida = Image.open(io.BytesIO(imagen.data))
    assert salida.format == "PNG" and salida.size == (600, 200)
    assert salida.mode == "RGBA" and salida.getpixel((10, 10))[3] == 0
    assert "Autor" not in salida.info and "teléfono".encode() not in imagen.data
    assert (carpeta / f"{TENANT_A}" / f"{logo_id}.png").exists()


def _texto(clave, valor):
    from PIL.PngImagePlugin import PngInfo

    info = PngInfo()
    info.add_itxt(clave, valor)
    return info


def test_same_logo_id_again_is_idempotent(client):
    _guardar(client)
    logo_id = uuid.uuid4()
    assert _subir(client, _png(), logo_id).status_code == 201
    assert _subir(client, _png(), logo_id).status_code == 200


def test_changing_or_removing_the_logo_keeps_the_previous_file(client, carpeta):
    _guardar(client)
    primero, segundo = uuid.uuid4(), uuid.uuid4()
    assert _subir(client, _png(), primero).status_code == 201
    assert _subir(client, _png(color=(200, 0, 0, 255)), segundo).status_code == 201
    assert client.get("/empresa", headers=ADMIN).get_json()["empresa"]["logo"]["id"] == str(segundo)
    # R2: el anterior sigue disponible para los informes congelados.
    assert client.get(f"/empresa/logo/{primero}", headers=ADMIN).status_code == 200

    assert client.delete("/empresa/logo", headers=ADMIN).status_code == 204
    assert client.get("/empresa", headers=ADMIN).get_json()["empresa"]["logo"] is None
    assert client.get(f"/empresa/logo/{segundo}", headers=ADMIN).status_code == 200
    assert (carpeta / f"{TENANT_A}" / f"{segundo}.png").exists()
    assert client.delete("/empresa/logo", headers=ADMIN).status_code == 404


def test_saving_the_data_keeps_the_logo(client):
    _guardar(client)
    logo_id = uuid.uuid4()
    _subir(client, _png(), logo_id)
    _guardar(client, {**DATOS, "nombre": "Nombre nuevo"})
    assert client.get("/empresa", headers=ADMIN).get_json()["empresa"]["logo"] == {
        "id": str(logo_id)
    }


@pytest.mark.parametrize(
    ("datos", "status", "code"),
    [
        (b"GIF89a cualquier cosa", 415, "tipo_no_admitido"),
        (b"%PDF-1.7", 415, "tipo_no_admitido"),
        (b"\x89PNG\r\n\x1a\n" + b"0" * (2 * 1024 * 1024), 413, "imagen_demasiado_grande"),
    ],
)
def test_bad_logos_are_refused(client, datos, status, code):
    _guardar(client)
    response = _subir(client, datos)
    assert response.status_code == status
    assert response.get_json()["error"]["code"] == code


def test_logo_form_must_be_complete(client):
    _guardar(client)
    sin_id = client.put(
        "/empresa/logo",
        data={"archivo": (io.BytesIO(_png()), "x.png")},
        headers=ADMIN,
        content_type="multipart/form-data",
    )
    assert sin_id.status_code == 400
    sin_archivo = client.put(
        "/empresa/logo",
        data={"logo_id": str(uuid.uuid4())},
        headers=ADMIN,
        content_type="multipart/form-data",
    )
    assert sin_archivo.status_code == 400


def test_logo_of_another_tenant_is_not_found(client):
    _guardar(client, {**DATOS, "nit": ""}, headers=ADMIN_OTRO)
    logo_b = uuid.uuid4()
    assert _subir(client, _png(), logo_b, headers=ADMIN_OTRO).status_code == 201
    assert client.get(f"/empresa/logo/{logo_b}", headers=ADMIN).status_code == 404
    # Su id no se puede reusar en el tenant A ni revela nada.
    _guardar(client)
    reuso = _subir(client, _png(), logo_b)
    assert reuso.status_code == 409
    assert reuso.get_json()["error"]["code"] == "logo_id_en_uso"


def test_logo_without_storage_is_503(emp_app, client):
    _guardar(client)
    guardado = emp_app.extensions[EXTENSION_KEY]
    emp_app.extensions[EXTENSION_KEY] = None
    try:
        assert _subir(client, _png()).status_code == 503
    finally:
        emp_app.extensions[EXTENSION_KEY] = guardado


def test_body_limit_for_the_logo_is_about_2_mb(client):
    assert empresa_service.LOGO_MAX_BYTES == 2 * 1024 * 1024
    response = client.put(
        "/empresa/logo",
        data=b"x" * (3 * 1024 * 1024),
        headers={**ADMIN, "Content-Type": "multipart/form-data; boundary=x"},
    )
    assert response.status_code == 413


def test_company_json_body_is_limited_to_4_kb(client):
    response = client.put(
        "/empresa",
        data=b'{"nombre": "' + b"x" * 5000 + b'"}',
        headers={**ADMIN, "Content-Type": "application/json"},
    )
    assert response.status_code == 413
