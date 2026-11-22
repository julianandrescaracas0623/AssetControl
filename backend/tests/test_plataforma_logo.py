"""Logo en el alta desde la consola (spec 017, T7; R23, R24, R33–R36; A4, A5, A19; CU-04).

Sobre una base temporal migrada a ``head`` (tenants sintéticos A y B de ``acceso_db``), con
la consola habilitada y el almacén en una carpeta temporal. Cada prueba crea su empresa
con ``POST /plataforma/empresas`` (sin logo), así ninguna depende del orden de las demás.

- HTTP: ``POST /plataforma/empresas/{id}/logo`` con las reglas de la 013 (PNG/JPEG/WebP
  ≤ 2 MB -> PNG ≤ 600 px, con transparencia, sin metadatos), clave del tenant, fila
  ``empresa_logo`` subida por el admin de la empresa, ``empresa.logo_id`` y
  ``empresa_logo_subido`` en la misma transacción; archivo inválido sin filas ni archivo
  huérfano; fallo de la transacción que borra el archivo; idempotencia con el mismo
  ``logo_id``; C1 (R44, A22): reemplazo del vigente (sin ``409 logo_existente``), el
  anterior se conserva y se audita ``empresa_logo_reemplazado``; ``409 logo_id_en_uso`` /
  ``empresa_sin_datos``;
  ``404``; ``503 logos_no_disponibles`` sin almacén; ``503`` genérico con la fila
  bloqueada; formulario estricto (``400``); tope del cuerpo; ``plat_accion``; ``401`` a
  los tokens de tenant.
- Admin de la empresa: ve el logo por ``GET /empresa`` y lo descarga; el de otra empresa no.
- SQL: la función rechaza a un desarrollador inactivo, una clave de otro tenant y deja las
  GUC vacías; el desarrollador no lee otras columnas de ``empresa`` (A19).
- Logs sin bytes, nombre del archivo ni clave.

Datos sintéticos (``@ejemplo.test``).
"""

import dataclasses
import io
import logging
import threading
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from acceso_db import (
    ADMIN_A,
    TENANT_A,
    AccesoDb,
    Cuenta,
    bearer,
    dispose,
    temporary_acceso_db,
)
from flask import Flask
from PIL import Image, PngImagePlugin
from plataforma_db import (
    HIGH_LIMITS,
    ejecutar,
    error_code,
    filas,
    login,
    make_plat_app,
    nuevo_dev,
    plat_bearer,
    sembrar_dev,
)
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool
from werkzeug.datastructures import FileStorage
from werkzeug.test import EnvironBuilder, encode_multipart

from app.fotos.almacen import EXTENSION_KEY, CarpetaLocal
from app.plataforma import LOGO_MAX_BODY_BYTES, MAX_BODY_BYTES, body_limit
from app.plataforma.modulos.empresas import service as empresas_service

ADMIN_PASSWORD = "Clave-Inicial-Sintetica-2026"
RUTA = "/plataforma/empresas"
REGISTRAR = "select * from acceso.plataforma_registrar_logo(:d, :t, :l, :c, :b, :w, :h)"
INSUFFICIENT_PRIVILEGE = "42501"
LOCK_TIMEOUT_SEGUNDOS = 5
MARCA_METADATOS = "centinela-metadato-logo"
NOMBRE_ARCHIVO = "logo-centinela-nombre.png"
OWNER_GUCS = (
    "app.plat_login_email",
    "app.plat_dev_crear",
    "app.plat_dev_restablecer",
    "app.plat_dev_estado",
    "app.plat_dev_objetivo",
    "app.plat_actor",
    "app.plat_listar",
    "app.plat_tenant_nuevo",
    "app.plat_usuario_nuevo",
    "app.plat_tenant_estado",
    "app.plat_usuarios",
    "app.plat_membresia_tenant",
    "app.plat_membresia_usuario",
    "app.plat_actividad",
    "app.plat_logo_tenant",
    "app.plat_logo_id",
    # C1 (0030): la empresa cuya ficha se lee o se edita.
    "app.plat_empresa_tenant",
)


@pytest.fixture(scope="module")
def logo_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("plat_logo")


@pytest.fixture(scope="module")
def carpeta(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("almacen_logo")


@pytest.fixture(scope="module")
def logo_app(logo_db, carpeta) -> Iterator[Flask]:
    flask_app = make_plat_app(logo_db)
    flask_app.extensions[EXTENSION_KEY] = CarpetaLocal(carpeta)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(logo_app):
    return logo_app.test_client(use_cookies=False)


@pytest.fixture(scope="module")
def dev(logo_db):
    return sembrar_dev(logo_db, nuevo_dev("logo"))


@pytest.fixture(scope="module")
def headers(logo_app, dev) -> dict[str, str]:
    response = login(logo_app.test_client(use_cookies=False), dev.email)
    assert response.status_code == 200
    return plat_bearer(response.get_json()["access_token"])


@pytest.fixture(scope="module")
def app_engine(logo_db) -> Iterator[Engine]:
    engine = create_engine(logo_db.app_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


# --- Utilidades -------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Empresa:
    id: uuid.UUID
    admin: Cuenta


def _png(tamano=(1200, 400), modo="RGBA", color=(14, 116, 144, 128), formato="PNG") -> bytes:
    buffer = io.BytesIO()
    img = Image.new(modo, tamano, color)
    if formato == "PNG":
        info = PngImagePlugin.PngInfo()
        info.add_text("Comment", MARCA_METADATOS)
        img.save(buffer, "PNG", pnginfo=info)
    else:
        img.save(buffer, formato)
    return buffer.getvalue()


def _empresa(client, headers) -> Empresa:
    email = f"admin.{uuid.uuid4().hex[:10]}@ejemplo.test"
    body = {
        "id": str(uuid.uuid4()),
        "nombre": f"Clínica Logo {uuid.uuid4().hex[:6]}",
        "direccion": "Calle 1 # 2-3, Cartago",
        "admin": {
            "nombre": "Admin Logo",
            "email": email,
            "password": ADMIN_PASSWORD,
            "password_confirmacion": ADMIN_PASSWORD,
        },
    }
    response = client.post(RUTA, json=body, headers=headers)
    assert response.status_code == 201, response.get_json()
    creada = response.get_json()
    return Empresa(
        uuid.UUID(creada["empresa_id"]),
        Cuenta(uuid.UUID(creada["admin_id"]), email, "Admin Logo"),
    )


def _subir(client, headers, empresa_id, datos: bytes, logo_id=None, nombre=NOMBRE_ARCHIVO):
    form = {"logo_id": str(logo_id or uuid.uuid4()), "archivo": (io.BytesIO(datos), nombre)}
    return client.post(
        f"{RUTA}/{empresa_id}/logo",
        data=form,
        headers=headers,
        content_type="multipart/form-data",
    )


def _archivos(carpeta: Path, tenant_id=None) -> set[str]:
    raiz = carpeta if tenant_id is None else carpeta / str(tenant_id)
    if not raiz.exists():
        return set()
    return {p.relative_to(carpeta).as_posix() for p in raiz.rglob("*") if p.is_file()}


def _estado(db: AccesoDb, tenant_id) -> dict:
    """Lo que la subida puede cambiar en una empresa: logo vigente, logos y auditoría."""
    return {
        "logo_id": filas(db, "select logo_id from empresa where tenant_id = :t", {"t": tenant_id}),
        "logos": filas(
            db,
            "select id, clave, bytes, ancho, alto, subido_por from empresa_logo "
            "where tenant_id = :t order by id",
            {"t": tenant_id},
        ),
        "auditoria": filas(
            db,
            "select accion, objeto_id from plataforma_auditoria "
            "where tenant_id = :t "
            "and accion in ('empresa_logo_subido', 'empresa_logo_reemplazado') "
            "order by creado_en, id",
            {"t": tenant_id},
        ),
    }


def _sin_logo(db: AccesoDb, tenant_id) -> dict:
    return {"logo_id": [{"logo_id": None}], "logos": [], "auditoria": []}


def _admin_listo(db: AccesoDb, empresa: Empresa) -> dict[str, str]:
    """El admin creado por la consola, ya con su contraseña cambiada (R26)."""
    ejecutar(
        db,
        "update usuario set debe_cambiar_password = false where id = :u",
        {"u": empresa.admin.usuario_id},
    )
    return bearer(empresa.admin, empresa.id)


# --- Subida (R23) -----------------------------------------------------------------------


def test_upload_sets_the_logo_with_the_013_rules_and_audits(client, headers, logo_db, carpeta, dev):
    empresa = _empresa(client, headers)
    logo_id = uuid.uuid4()
    response = _subir(client, headers, empresa.id, _png(), logo_id)
    assert response.status_code == 201, response.get_json()
    assert response.get_json() == {"logo": {"id": str(logo_id)}}
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"

    clave = f"{empresa.id}/{logo_id}.png"
    assert _archivos(carpeta, empresa.id) == {clave}
    guardado = (carpeta / clave).read_bytes()
    estado = _estado(logo_db, empresa.id)
    assert estado["logo_id"] == [{"logo_id": logo_id}]
    assert estado["logos"] == [
        {
            "id": logo_id,
            "clave": clave,
            "bytes": len(guardado),
            "ancho": 600,
            "alto": 200,
            "subido_por": empresa.admin.usuario_id,
        }
    ]
    # Una sola fila de auditoría, del desarrollador, con el tenant y el id del logo.
    auditoria = filas(
        logo_db,
        "select desarrollador_id, accion, resultado, tenant_id, objeto_id "
        "from plataforma_auditoria where tenant_id = :t and accion = 'empresa_logo_subido'",
        {"t": empresa.id},
    )
    assert auditoria == [
        {
            "desarrollador_id": dev.id,
            "accion": "empresa_logo_subido",
            "resultado": "ok",
            "tenant_id": empresa.id,
            "objeto_id": logo_id,
        }
    ]
    # PNG ≤ 600 px, con transparencia y sin metadatos (013).
    with Image.open(io.BytesIO(guardado)) as img:
        assert (img.format, img.mode, img.size) == ("PNG", "RGBA", (600, 200))
        assert img.getpixel((0, 0))[3] == 128
        assert "Comment" not in img.info and not getattr(img, "text", {})
    assert MARCA_METADATOS.encode() not in guardado
    # La lista de Empresas ya lo marca.
    lista = client.get(RUTA, headers=headers).get_json()["empresas"]
    assert [e["tiene_logo"] for e in lista if e["id"] == str(empresa.id)] == [True]


@pytest.mark.parametrize("formato", ["JPEG", "WEBP"])
def test_jpeg_and_webp_are_stored_as_png(client, headers, logo_db, carpeta, formato):
    empresa = _empresa(client, headers)
    logo_id = uuid.uuid4()
    datos = _png((300, 300), "RGB", (200, 10, 10), formato=formato)
    response = _subir(client, headers, empresa.id, datos, logo_id)
    assert response.status_code == 201, response.get_json()
    with Image.open(carpeta / f"{empresa.id}/{logo_id}.png") as img:
        assert (img.format, img.size) == ("PNG", (300, 300))


def _gif() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buffer, "GIF")
    return buffer.getvalue()


def _grande() -> bytes:
    # Ruido sin comprimir: más de 2 MB dentro del tope del cuerpo.
    return b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * (8 * 1024 + 8)


@pytest.mark.parametrize(
    ("datos", "status", "code"),
    [
        (b"esto no es una imagen", 415, "tipo_no_admitido"),
        (_gif(), 415, "tipo_no_admitido"),
        (_png()[:200], 422, "imagen_invalida"),
        (_grande(), 413, "imagen_demasiado_grande"),
    ],
    ids=["texto", "gif", "png-truncado", "mas-de-2-mb"],
)
def test_an_invalid_file_leaves_no_rows_nor_orphan_file(
    client, headers, logo_db, carpeta, datos, status, code
):
    empresa = _empresa(client, headers)
    response = _subir(client, headers, empresa.id, datos)
    assert (response.status_code, error_code(response)) == (status, code)
    assert _estado(logo_db, empresa.id) == _sin_logo(logo_db, empresa.id)
    assert _archivos(carpeta, empresa.id) == set()


def test_the_same_logo_id_is_idempotent_and_keeps_the_stored_file(
    client, headers, logo_db, carpeta
):
    empresa = _empresa(client, headers)
    logo_id = uuid.uuid4()
    assert _subir(client, headers, empresa.id, _png(), logo_id).status_code == 201
    clave = carpeta / f"{empresa.id}/{logo_id}.png"
    guardado = clave.read_bytes()
    estado = _estado(logo_db, empresa.id)

    # Un reintento (aun con otro archivo) no reescribe el archivo, ni filas, ni audita.
    otro = _png((100, 100), color=(1, 2, 3, 255))
    response = _subir(client, headers, empresa.id, otro, logo_id)
    assert response.status_code == 200
    assert response.get_json() == {"logo": {"id": str(logo_id)}}
    assert clave.read_bytes() == guardado
    assert _estado(logo_db, empresa.id) == estado
    assert _archivos(carpeta, empresa.id) == {f"{empresa.id}/{logo_id}.png"}


def _fila_empresa(db: AccesoDb, tenant_id) -> dict:
    return filas(
        db,
        "select nombre, direccion, nit, telefono, correo, logo_id, actualizada_por "
        "from empresa where tenant_id = :t",
        {"t": tenant_id},
    )[0]


def test_a_second_logo_replaces_the_current_one_and_keeps_the_old(
    client, headers, logo_db, carpeta, dev
):
    """C1 (R44, A22): ya no hay ``409 logo_existente``; el anterior se conserva (013 R2)."""
    empresa = _empresa(client, headers)
    primero, segundo = uuid.uuid4(), uuid.uuid4()
    assert _subir(client, headers, empresa.id, _png(), primero).status_code == 201
    archivo_primero = (carpeta / f"{empresa.id}/{primero}.png").read_bytes()
    antes = _fila_empresa(logo_db, empresa.id)

    response = _subir(client, headers, empresa.id, _png((300, 100)), segundo)
    assert response.status_code == 201, response.get_json()
    assert response.get_json() == {"logo": {"id": str(segundo)}}
    estado = _estado(logo_db, empresa.id)
    assert estado["logo_id"] == [{"logo_id": segundo}]
    # Las dos filas y los dos archivos siguen; el primero, intacto.
    assert [logo["id"] for logo in estado["logos"]] == sorted([primero, segundo])
    assert _archivos(carpeta, empresa.id) == {
        f"{empresa.id}/{primero}.png",
        f"{empresa.id}/{segundo}.png",
    }
    assert (carpeta / f"{empresa.id}/{primero}.png").read_bytes() == archivo_primero
    # Auditoría: subido y luego reemplazado, cada uno con el id de su logo.
    assert estado["auditoria"] == [
        {"accion": "empresa_logo_subido", "objeto_id": primero},
        {"accion": "empresa_logo_reemplazado", "objeto_id": segundo},
    ]
    reemplazo = filas(
        logo_db,
        "select desarrollador_id, resultado from plataforma_auditoria "
        "where tenant_id = :t and accion = 'empresa_logo_reemplazado'",
        {"t": empresa.id},
    )
    assert reemplazo == [{"desarrollador_id": dev.id, "resultado": "ok"}]
    # Solo cambió el logo vigente: la ficha y actualizada_por siguen igual.
    despues = _fila_empresa(logo_db, empresa.id)
    assert {**despues, "logo_id": primero} == antes

    # Repetir el reemplazo con el mismo logo_id es idempotente (200, sin escribir).
    response = _subir(client, headers, empresa.id, _png(), segundo)
    assert response.status_code == 200
    assert _estado(logo_db, empresa.id) == estado

    # El admin ve el nuevo y aún descarga el anterior (los informes congelados lo usan).
    admin = _admin_listo(logo_db, empresa)
    assert client.get("/empresa", headers=admin).get_json()["empresa"]["logo"] == {
        "id": str(segundo)
    }
    anterior = client.get(f"/empresa/logo/{primero}", headers=admin)
    assert (anterior.status_code, anterior.data) == (200, archivo_primero)


def test_a_logo_set_by_the_admin_is_replaced_and_kept(client, headers, logo_db, carpeta):
    """C1: la consola reemplaza también el logo que subió el admin (013); no lo borra."""
    empresa = _empresa(client, headers)
    admin = _admin_listo(logo_db, empresa)
    del_admin = uuid.uuid4()
    form = {"logo_id": str(del_admin), "archivo": (io.BytesIO(_png()), "a.png")}
    response = client.put(
        "/empresa/logo", data=form, headers=admin, content_type="multipart/form-data"
    )
    assert response.status_code == 201, response.get_json()
    estado = _estado(logo_db, empresa.id)

    # La subida idempotente con el id del admin no audita ni reescribe nada.
    response = _subir(client, headers, empresa.id, _png(), del_admin)
    assert response.status_code == 200
    assert _estado(logo_db, empresa.id) == estado

    nuevo = uuid.uuid4()
    response = _subir(client, headers, empresa.id, _png(), nuevo)
    assert response.status_code == 201, response.get_json()
    despues = _estado(logo_db, empresa.id)
    assert despues["logo_id"] == [{"logo_id": nuevo}]
    assert [logo["id"] for logo in despues["logos"]] == sorted([del_admin, nuevo])
    assert despues["auditoria"] == [{"accion": "empresa_logo_reemplazado", "objeto_id": nuevo}]
    assert f"{empresa.id}/{del_admin}.png" in _archivos(carpeta, empresa.id)


def test_after_the_admin_removes_the_logo_the_upload_is_audited_as_subido(
    client, headers, logo_db
):
    empresa = _empresa(client, headers)
    primero = uuid.uuid4()
    assert _subir(client, headers, empresa.id, _png(), primero).status_code == 201
    admin = _admin_listo(logo_db, empresa)
    assert client.delete("/empresa/logo", headers=admin).status_code == 204

    otro = uuid.uuid4()
    assert _subir(client, headers, empresa.id, _png(), otro).status_code == 201
    assert _estado(logo_db, empresa.id)["auditoria"] == [
        {"accion": "empresa_logo_subido", "objeto_id": primero},
        {"accion": "empresa_logo_subido", "objeto_id": otro},
    ]
    # Volver a un logo ya usado por la empresa es logo_id_en_uso (como la 013).
    response = _subir(client, headers, empresa.id, _png(), primero)
    assert (response.status_code, error_code(response)) == (409, "logo_id_en_uso")


def test_an_invalid_replacement_keeps_the_current_logo(client, headers, logo_db, carpeta):
    empresa = _empresa(client, headers)
    primero = uuid.uuid4()
    assert _subir(client, headers, empresa.id, _png(), primero).status_code == 201
    estado = _estado(logo_db, empresa.id)
    for datos, status in ((b"no es imagen", 415), (_png()[:200], 422), (_grande(), 413)):
        response = _subir(client, headers, empresa.id, datos)
        assert response.status_code == status
        assert _estado(logo_db, empresa.id) == estado
        assert _archivos(carpeta, empresa.id) == {f"{empresa.id}/{primero}.png"}


def test_a_failed_replacement_deletes_only_the_new_file(
    client, headers, logo_db, carpeta, monkeypatch
):
    empresa = _empresa(client, headers)
    primero = uuid.uuid4()
    assert _subir(client, headers, empresa.id, _png(), primero).status_code == 201
    estado = _estado(logo_db, empresa.id)

    def falla(*args, **kwargs):
        raise RuntimeError("auditoría caída (sintético)")

    monkeypatch.setattr(empresas_service.auditoria, "registrar", falla)
    response = _subir(client, headers, empresa.id, _png())
    assert response.status_code == 500
    # Sin fila nueva ni archivo huérfano; el vigente y su archivo, intactos.
    assert _estado(logo_db, empresa.id) == estado
    assert _archivos(carpeta, empresa.id) == {f"{empresa.id}/{primero}.png"}


def _cerrar_sesion(client, admin) -> str:
    response = client.post(
        "/sesiones", json={"nombre": "Inventario logo", "fecha_corte": "2026-11-30"}, headers=admin
    )
    assert response.status_code == 201, response.get_json()
    sesion = response.get_json()["sesion"]["id"]
    response = client.post(f"/sesiones/{sesion}/cerrar", headers=admin)
    assert response.status_code == 200, response.get_json()
    return sesion


def test_a_frozen_report_keeps_serving_the_previous_logo(client, headers, logo_db, carpeta):
    """A22: el informe congelado que usa el logo anterior lo sigue sirviendo."""
    empresa = _empresa(client, headers)
    primero = uuid.uuid4()
    assert _subir(client, headers, empresa.id, _png(), primero).status_code == 201
    admin = _admin_listo(logo_db, empresa)
    sesion = _cerrar_sesion(client, admin)
    informe = client.get(f"/sesiones/{sesion}/informe", headers=admin).get_json()
    assert informe["empresa"]["logo"] == {"id": str(primero)}

    assert _subir(client, headers, empresa.id, _png(), uuid.uuid4()).status_code == 201
    despues = client.get(f"/sesiones/{sesion}/informe", headers=admin).get_json()
    assert despues["empresa"] == informe["empresa"]
    png = client.get(f"/empresa/logo/{primero}", headers=admin)
    assert png.status_code == 200
    assert png.data == (carpeta / f"{empresa.id}/{primero}.png").read_bytes()


def test_a_replacement_waits_for_the_admin_and_reports_it_exactly(client, headers, logo_db):
    """La fila bloqueada serializa contra el admin: si él fija un logo mientras tanto, el
    de la consola lo reemplaza y se audita como reemplazo (no como subida)."""
    empresa = _empresa(client, headers)
    _admin_listo(logo_db, empresa)
    del_admin = uuid.uuid4()
    tomado, soltar = threading.Event(), threading.Event()

    def admin_sube() -> None:
        # Como el admin en la 013: bloquea la fila, registra su logo y lo fija.
        with logo_db.migrator.connect() as conn:
            tx = conn.begin()
            conn.execute(
                text("select 1 from empresa where tenant_id = :t for update"), {"t": empresa.id}
            )
            conn.execute(
                text(
                    "insert into empresa_logo (id, tenant_id, clave, bytes, ancho, alto, "
                    "subido_por) values (:l, :t, :c, 1, 1, 1, :u)"
                ),
                {
                    "l": del_admin,
                    "t": empresa.id,
                    "c": f"{empresa.id}/{del_admin}.png",
                    "u": empresa.admin.usuario_id,
                },
            )
            conn.execute(
                text("update empresa set logo_id = :l where tenant_id = :t"),
                {"l": del_admin, "t": empresa.id},
            )
            tomado.set()
            soltar.wait(30)
            tx.commit()

    hilo = threading.Thread(target=admin_sube)
    hilo.start()
    try:
        assert tomado.wait(10)
        threading.Timer(1.0, soltar.set).start()
        nuevo = uuid.uuid4()
        response = _subir(client, headers, empresa.id, _png(), nuevo)
    finally:
        soltar.set()
        hilo.join(30)
    assert response.status_code == 201, response.get_json()
    estado = _estado(logo_db, empresa.id)
    assert estado["logo_id"] == [{"logo_id": nuevo}]
    assert estado["auditoria"] == [{"accion": "empresa_logo_reemplazado", "objeto_id": nuevo}]


def test_a_logo_id_used_by_another_company_is_refused(client, headers, logo_db, carpeta):
    una, otra = _empresa(client, headers), _empresa(client, headers)
    logo_id = uuid.uuid4()
    assert _subir(client, headers, una.id, _png(), logo_id).status_code == 201
    guardado = (carpeta / f"{una.id}/{logo_id}.png").read_bytes()
    estado_una = _estado(logo_db, una.id)

    response = _subir(client, headers, otra.id, _png((50, 50)), logo_id)
    assert (response.status_code, error_code(response)) == (409, "logo_id_en_uso")
    # El logo de una no se asocia a otra, y su archivo sigue intacto.
    assert _estado(logo_db, otra.id) == _sin_logo(logo_db, otra.id)
    assert _estado(logo_db, una.id) == estado_una
    assert _archivos(carpeta, otra.id) == set()
    assert (carpeta / f"{una.id}/{logo_id}.png").read_bytes() == guardado


def test_unknown_company_is_404_and_stores_nothing(client, headers, carpeta):
    tenant = uuid.uuid4()
    response = _subir(client, headers, tenant, _png())
    assert (response.status_code, error_code(response)) == (404, "no_encontrado")
    assert _archivos(carpeta, tenant) == set()


def test_a_tenant_without_company_data_is_409_like_013(client, headers, logo_db, carpeta):
    # El tenant A sembrado no tiene ficha empresa (lo crea la CLI, no la consola).
    assert filas(logo_db, "select 1 from empresa where tenant_id = :t", {"t": TENANT_A}) == []
    response = _subir(client, headers, TENANT_A, _png())
    assert (response.status_code, error_code(response)) == (409, "empresa_sin_datos")
    assert filas(logo_db, "select id from empresa_logo where tenant_id = :t", {"t": TENANT_A}) == []
    assert _archivos(carpeta, TENANT_A) == set()


def test_without_storage_it_is_503_logos_no_disponibles(
    client, headers, logo_app, logo_db, carpeta, monkeypatch
):
    empresa = _empresa(client, headers)
    monkeypatch.setitem(logo_app.extensions, EXTENSION_KEY, None)
    response = _subir(client, headers, empresa.id, _png())
    assert (response.status_code, error_code(response)) == (503, "logos_no_disponibles")
    assert _estado(logo_db, empresa.id) == _sin_logo(logo_db, empresa.id)
    assert _archivos(carpeta, empresa.id) == set()


def test_a_failed_transaction_deletes_the_stored_file(
    client, headers, logo_db, carpeta, monkeypatch
):
    empresa = _empresa(client, headers)
    guardados = []
    real = CarpetaLocal.guardar

    def espia(self, clave, datos, tipo):
        real(self, clave, datos, tipo)
        guardados.append(clave)

    def falla(*args, **kwargs):
        raise RuntimeError("auditoría caída (sintético)")

    monkeypatch.setattr(CarpetaLocal, "guardar", espia)
    monkeypatch.setattr(empresas_service.auditoria, "registrar", falla)
    logo_id = uuid.uuid4()
    response = _subir(client, headers, empresa.id, _png(), logo_id)
    assert response.status_code == 500
    # Se llegó a guardar y, al revertir, se borró: sin filas ni archivo huérfano.
    assert guardados == [f"{empresa.id}/{logo_id}.png"]
    assert _archivos(carpeta, empresa.id) == set()
    assert _estado(logo_db, empresa.id) == _sin_logo(logo_db, empresa.id)


def test_a_transient_flush_error_is_503_and_deletes_the_file(
    client, headers, logo_db, carpeta, monkeypatch
):
    empresa = _empresa(client, headers)
    real = empresas_service.auditoria.registrar

    class Serializacion(Exception):
        sqlstate = "40001"

    def falla(*args, **kwargs):
        raise DBAPIError("detalle-de-la-base-sintetico", {}, Serializacion())

    def registrar(session, *args, **kwargs):
        # La auditoría se añade y su flush falla como un fallo de serialización.
        real(session, *args, **kwargs)
        event.listen(session, "before_flush", falla, once=True)

    monkeypatch.setattr(empresas_service.auditoria, "registrar", registrar)
    response = _subir(client, headers, empresa.id, _png())
    assert (response.status_code, error_code(response)) == (503, "servicio_no_disponible")
    assert "detalle-de-la-base" not in response.get_data(as_text=True)
    assert _archivos(carpeta, empresa.id) == set()
    assert _estado(logo_db, empresa.id) == _sin_logo(logo_db, empresa.id)


def test_a_transient_function_error_is_503_without_storing(
    client, headers, logo_db, carpeta, monkeypatch
):
    empresa = _empresa(client, headers)

    class Interbloqueo(Exception):
        sqlstate = "40P01"

    def falla(session, **kwargs):
        raise DBAPIError("detalle-de-la-base-sintetico", {}, Interbloqueo())

    monkeypatch.setattr(empresas_service, "plataforma_registrar_logo", falla)
    response = _subir(client, headers, empresa.id, _png())
    assert (response.status_code, error_code(response)) == (503, "servicio_no_disponible")
    assert "detalle-de-la-base" not in response.get_data(as_text=True)
    assert _archivos(carpeta, empresa.id) == set()
    assert _estado(logo_db, empresa.id) == _sin_logo(logo_db, empresa.id)


def test_a_locked_company_row_is_503_after_the_lock_timeout(client, headers, logo_db, carpeta):
    empresa = _empresa(client, headers)
    tomado, soltar = threading.Event(), threading.Event()

    def bloquear() -> None:
        with logo_db.migrator.connect() as conn:
            tx = conn.begin()
            conn.execute(
                text("select 1 from empresa where tenant_id = :t for update"), {"t": empresa.id}
            )
            tomado.set()
            soltar.wait(30)
            tx.rollback()

    hilo = threading.Thread(target=bloquear)
    hilo.start()
    try:
        assert tomado.wait(10)
        inicio = time.monotonic()
        response = _subir(client, headers, empresa.id, _png())
        espera = time.monotonic() - inicio
    finally:
        soltar.set()
        hilo.join(30)
    assert (response.status_code, error_code(response)) == (503, "servicio_no_disponible")
    assert response.headers.get("Retry-After")
    assert LOCK_TIMEOUT_SEGUNDOS - 1 <= espera < LOCK_TIMEOUT_SEGUNDOS + 10
    assert _estado(logo_db, empresa.id) == _sin_logo(logo_db, empresa.id)
    assert _archivos(carpeta, empresa.id) == set()


# --- Formulario y cuerpo ----------------------------------------------------------------


@pytest.mark.parametrize(
    "form",
    [
        {"archivo": "png"},
        {"logo_id": "id"},
        {"logo_id": "no-es-un-uuid", "archivo": "png"},
        {"logo_id": "ID-MAYUSCULAS", "archivo": "png"},
        {"logo_id": "id", "archivo": "png", "extra": "x"},
        {"logo_id": "id", "archivo": "png", "otro_archivo": "png"},
    ],
    ids=["sin-id", "sin-archivo", "id-invalido", "id-no-canonico", "campo-extra", "dos-archivos"],
)
def test_the_form_is_strict(client, headers, logo_db, carpeta, form):
    empresa = _empresa(client, headers)
    logo_id = uuid.uuid4()
    data = {}
    for campo, valor in form.items():
        if valor == "png":
            data[campo] = (io.BytesIO(_png()), "logo.png")
        elif valor == "id":
            data[campo] = str(logo_id)
        elif valor == "ID-MAYUSCULAS":
            data[campo] = str(logo_id).upper()
        else:
            data[campo] = valor
    response = client.post(
        f"{RUTA}/{empresa.id}/logo", data=data, headers=headers, content_type="multipart/form-data"
    )
    assert (response.status_code, error_code(response)) == (400, "solicitud_invalida")
    assert _estado(logo_db, empresa.id) == _sin_logo(logo_db, empresa.id)
    assert _archivos(carpeta, empresa.id) == set()


def test_a_json_body_is_400(client, headers):
    empresa = _empresa(client, headers)
    response = client.post(
        f"{RUTA}/{empresa.id}/logo", json={"logo_id": str(uuid.uuid4())}, headers=headers
    )
    assert (response.status_code, error_code(response)) == (400, "solicitud_invalida")


def test_body_limit_is_the_013_logo_one_only_for_this_route(client, headers):
    empresa = _empresa(client, headers)
    response = client.post(
        f"{RUTA}/{empresa.id}/logo",
        data=b"x" * (LOGO_MAX_BODY_BYTES + 1),
        headers={**headers, "Content-Type": "multipart/form-data; boundary=x"},
    )
    assert response.status_code == 413
    # El resto de /plataforma sigue con el tope de 4 KB.
    response = client.post(RUTA, data=b"{" + b" " * 5000 + b"}", headers=headers)
    assert response.status_code == 413
    assert LOGO_MAX_BODY_BYTES == 2 * 1024 * 1024 + 64 * 1024


NO_CANONICO = "0123456789abcdef-0123456789abcdef-ab"  # 36 caracteres hex y guiones


@pytest.mark.parametrize(
    ("segmento", "tope"),
    [
        ("00000000-0000-4000-8000-0000000000ab", LOGO_MAX_BODY_BYTES),
        ("00000000-0000-4000-8000-0000000000AB", LOGO_MAX_BODY_BYTES),
        (NO_CANONICO, MAX_BODY_BYTES),
        ("------------------------------------", MAX_BODY_BYTES),
    ],
    ids=["canonico", "mayusculas", "no-canonico", "solo-guiones"],
)
def test_the_logo_limit_follows_the_canonical_uuid_like_the_route(segmento, tope):
    # El patrón del tope coincide con el convertidor ``uuid`` de Flask (8-4-4-4-12 hex).
    assert len(segmento) == 36
    assert body_limit(f"{RUTA}/{segmento}/logo") == tope


def test_a_non_canonical_36_char_segment_gets_the_4_kb_limit(client, headers):
    response = client.post(
        f"{RUTA}/{NO_CANONICO}/logo",
        data=b"x" * (MAX_BODY_BYTES + 1),
        headers={**headers, "Content-Type": "multipart/form-data; boundary=x"},
    )
    assert response.status_code == 413
    # Con el UUID canónico en mayúsculas el mismo cuerpo pasa el tope (Flask lo acepta).
    empresa = _empresa(client, headers)
    response = client.post(
        f"{RUTA}/{str(empresa.id).upper()}/logo",
        data=b"x" * (MAX_BODY_BYTES + 1),
        headers={**headers, "Content-Type": "multipart/form-data; boundary=x"},
    )
    assert response.status_code == 400


class _FlujoContado(io.BytesIO):
    """``wsgi.input`` que cuenta los bytes que alguien le lee (spec 017, O1 de T7)."""

    def __init__(self, datos: bytes) -> None:
        super().__init__(datos)
        self.leidos = 0

    def read(self, size: int | None = -1) -> bytes:
        trozo = super().read(size)
        self.leidos += len(trozo)
        return trozo

    def readline(self, size: int | None = -1) -> bytes:
        trozo = super().readline(size)
        self.leidos += len(trozo)
        return trozo

    def readinto(self, buffer) -> int:  # el LimitedStream de Werkzeug lee con readinto
        n = super().readinto(buffer)
        self.leidos += n
        return n


def _subir_chunked(client, headers, empresa_id, datos: bytes, logo_id=None) -> tuple:
    """Subida sin ``Content-Length`` (chunked; el servidor WSGI marca ``input_terminated``)."""
    archivo = FileStorage(io.BytesIO(datos), NOMBRE_ARCHIVO, content_type="image/png")
    campos = {"logo_id": str(logo_id or uuid.uuid4()), "archivo": archivo}
    boundary, cuerpo = encode_multipart(campos)
    flujo = _FlujoContado(cuerpo)
    response = client.post(
        f"{RUTA}/{empresa_id}/logo",
        input_stream=flujo,
        headers={
            **headers,
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Transfer-Encoding": "chunked",
        },
        environ_overrides={"wsgi.input_terminated": True},
    )
    return response, flujo, len(cuerpo)


def test_a_chunked_logo_without_token_is_401_without_reading_the_body(client, headers):
    # O1 de T7: sin autenticar no se pre-lee el cuerpo chunked (hasta 2 MB + 64 KB).
    empresa = _empresa(client, headers)
    response, flujo, total = _subir_chunked(client, {}, empresa.id, b"x" * (512 * 1024))
    assert 4096 < total < LOGO_MAX_BODY_BYTES
    assert (response.status_code, error_code(response)) == (401, "no_autenticado")
    assert flujo.leidos == 0


def test_a_chunked_logo_with_token_is_parsed_after_authenticating(client, headers, logo_db):
    empresa = _empresa(client, headers)
    response, flujo, total = _subir_chunked(client, headers, empresa.id, _png())
    assert response.status_code == 201, response.get_json()
    assert flujo.leidos == total


def test_a_chunked_logo_over_the_limit_is_413_after_authenticating(client, headers, logo_db):
    empresa = _empresa(client, headers)
    response, flujo, _ = _subir_chunked(
        client, headers, empresa.id, b"x" * (LOGO_MAX_BODY_BYTES + 1)
    )
    assert response.status_code == 413
    assert flujo.leidos <= LOGO_MAX_BODY_BYTES + 64 * 1024
    assert _estado(logo_db, empresa.id) == _sin_logo(logo_db, empresa.id)


def _post_crudo(client, path: str, auth: dict, flujo: _FlujoContado, extra: dict, environ=None):
    """POST con el ``wsgi.input`` contador y las cabeceras de cuerpo que pide la prueba.

    Con ``input_stream`` el cliente de pruebas pone ``CONTENT_LENGTH`` = largo del flujo e
    ignora la cabecera ``Content-Length``: un largo declarado distinto va en ``environ``.
    Werkzeug mira si ``wsgi.input_terminated`` *existe* (no su valor); el cliente de
    pruebas no la pone: sin ``environ`` la clave no está, como en un servidor que no la marca.
    """
    return client.post(
        path,
        input_stream=flujo,
        headers={**auth, "Content-Type": "multipart/form-data; boundary=x", **extra},
        environ_overrides=environ or {},
    )


def test_the_test_client_does_not_set_input_terminated():
    environ = EnvironBuilder(path="/", method="POST", input_stream=io.BytesIO(b"x")).get_environ()
    assert "wsgi.input_terminated" not in environ


def test_a_declared_length_over_the_logo_limit_is_413_before_401_without_reading(client, headers):
    # El tope va antes que la autenticación, igual que en /auth: un Content-Length declarado
    # mayor que 2 MB + 64 KB recibe 413 aun sin token, y sin leer un solo byte del cuerpo.
    empresa = _empresa(client, headers)
    flujo = _FlujoContado(b"x" * 1024)
    response = _post_crudo(
        client,
        f"{RUTA}/{empresa.id}/logo",
        {},
        flujo,
        {},
        environ={"CONTENT_LENGTH": str(LOGO_MAX_BODY_BYTES + 1)},
    )
    assert response.status_code == 413
    assert flujo.leidos == 0


def test_an_empty_body_without_token_is_401_without_reading(client, headers):
    empresa = _empresa(client, headers)
    flujo = _FlujoContado(b"x" * 1024)
    response = _post_crudo(
        client, f"{RUTA}/{empresa.id}/logo", {}, flujo, {}, environ={"CONTENT_LENGTH": "0"}
    )
    assert (response.status_code, error_code(response)) == (401, "no_autenticado")
    assert flujo.leidos == 0


@pytest.mark.parametrize(
    ("environ", "status", "leidos"),
    [
        # Servidor que marca el fin del cuerpo (gunicorn): la ruta con barra final no es la
        # del logo, así que rige la pre-lectura de 4 KB del resto de /plataforma: se leen a
        # lo sumo 4 KB + 1 byte antes de autenticar y responde 413 (no se lee el resto).
        ({"wsgi.input_terminated": True}, 413, MAX_BODY_BYTES + 1),
        # Sin la marca no se lee nada: la ruta no existe (sin redirección 308).
        ({}, 404, 0),
    ],
    ids=["input-terminated", "sin-marca"],
)
def test_a_chunked_body_with_a_trailing_slash_is_not_the_logo_route(
    client, headers, environ, status, leidos
):
    empresa = _empresa(client, headers)
    flujo = _FlujoContado(b"x" * (5 * 1024))
    response = _post_crudo(
        client,
        f"{RUTA}/{empresa.id}/logo/",
        {},
        flujo,
        {"Transfer-Encoding": "chunked"},
        environ=environ,
    )
    assert response.status_code == status
    assert "Location" not in response.headers
    assert flujo.leidos == leidos


def test_without_input_terminated_nor_length_it_is_400_without_reading(client, headers, logo_db):
    # Falla cerrado: sin Content-Length y sin ``wsgi.input_terminated`` Werkzeug no lee el
    # cuerpo (no sabe dónde acaba); el formulario llega vacío y la ruta responde 400.
    empresa = _empresa(client, headers)
    flujo = _FlujoContado(b"x" * (5 * 1024))
    response = _post_crudo(
        client, f"{RUTA}/{empresa.id}/logo", headers, flujo, {"Transfer-Encoding": "chunked"}
    )
    assert (response.status_code, error_code(response)) == (400, "solicitud_invalida")
    assert flujo.leidos == 0
    assert _estado(logo_db, empresa.id) == _sin_logo(logo_db, empresa.id)


def test_tenant_tokens_get_401(client, headers, logo_db, carpeta):
    empresa = _empresa(client, headers)
    admin = _admin_listo(logo_db, empresa)
    for auth in (admin, bearer(ADMIN_A, TENANT_A), {}):
        response = _subir(client, auth, empresa.id, _png())
        assert (response.status_code, error_code(response)) == (401, "no_autenticado")
    assert _estado(logo_db, empresa.id) == _sin_logo(logo_db, empresa.id)
    assert _archivos(carpeta, empresa.id) == set()


def test_a_deactivated_developer_gets_401(logo_app, logo_db, carpeta):
    client = logo_app.test_client(use_cookies=False)
    otro = sembrar_dev(logo_db, nuevo_dev("logo-baja"))
    auth = plat_bearer(login(client, otro.email).get_json()["access_token"])
    empresa = _empresa(client, auth)
    ejecutar(logo_db, "update desarrollador set activo = false where id = :d", {"d": otro.id})
    response = _subir(client, auth, empresa.id, _png())
    assert (response.status_code, error_code(response)) == (401, "no_autenticado")
    assert _estado(logo_db, empresa.id) == _sin_logo(logo_db, empresa.id)
    assert _archivos(carpeta, empresa.id) == set()


def test_upload_counts_in_plat_accion_before_touching_anything(logo_db, carpeta):
    flask_app = make_plat_app(logo_db, rate_limits=dataclasses.replace(HIGH_LIMITS, plat_accion=2))
    flask_app.extensions[EXTENSION_KEY] = CarpetaLocal(carpeta)
    try:
        client = flask_app.test_client(use_cookies=False)
        otro = sembrar_dev(logo_db, nuevo_dev("tope-logo"))
        auth = plat_bearer(login(client, otro.email).get_json()["access_token"])
        empresa = _empresa(client, auth)  # 1
        assert _subir(client, auth, empresa.id, b"no").status_code == 415  # 2
        response = _subir(client, auth, empresa.id, _png())
        assert (response.status_code, error_code(response)) == (429, "demasiadas_solicitudes")
        assert _estado(logo_db, empresa.id) == _sin_logo(logo_db, empresa.id)
        assert _archivos(carpeta, empresa.id) == set()
    finally:
        dispose(flask_app)


# --- El admin de la empresa (A19) -------------------------------------------------------


def test_the_admin_sees_the_logo_in_his_company_screen(client, headers, logo_db, carpeta):
    empresa = _empresa(client, headers)
    logo_id = uuid.uuid4()
    assert _subir(client, headers, empresa.id, _png(), logo_id).status_code == 201
    admin = _admin_listo(logo_db, empresa)

    vista = client.get("/empresa", headers=admin)
    assert vista.status_code == 200, vista.get_json()
    assert vista.get_json()["empresa"]["logo"] == {"id": str(logo_id)}
    png = client.get(f"/empresa/logo/{logo_id}", headers=admin)
    assert png.status_code == 200
    assert png.mimetype == "image/png"
    assert png.data == (carpeta / f"{empresa.id}/{logo_id}.png").read_bytes()


def test_the_logo_of_one_company_is_not_visible_to_another(client, headers, logo_db):
    una, otra = _empresa(client, headers), _empresa(client, headers)
    logo_id = uuid.uuid4()
    assert _subir(client, headers, una.id, _png(), logo_id).status_code == 201
    admin_otra = _admin_listo(logo_db, otra)
    assert client.get("/empresa", headers=admin_otra).get_json()["empresa"]["logo"] is None
    response = client.get(f"/empresa/logo/{logo_id}", headers=admin_otra)
    assert response.status_code == 404


def test_skipping_the_logo_leaves_the_company_operational_without_logo(client, headers, logo_db):
    """R24: el paso 2 es opcional; sin subir nada la empresa queda sin logo."""
    empresa = _empresa(client, headers)
    assert _estado(logo_db, empresa.id) == _sin_logo(logo_db, empresa.id)
    admin = _admin_listo(logo_db, empresa)
    vista = client.get("/empresa", headers=admin).get_json()["empresa"]
    assert (vista["logo"], vista["completa"]) == (None, True)


# --- SQL (A4, A5, A19) --------------------------------------------------------------------


def _llamar(engine: Engine, desarrollador, tenant, logo, clave=None, **cambios):
    params = {
        "d": str(desarrollador),
        "t": str(tenant),
        "l": str(logo),
        "c": clave or f"{tenant}/{logo}.png",
        "b": 10,
        "w": 10,
        "h": 10,
    }
    params.update(cambios)
    with engine.connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(
                text("select set_config('app.desarrollador_id', :d, true)"), {"d": params["d"]}
            )
            error = None
            try:
                with conn.begin_nested():
                    fila = conn.execute(text(REGISTRAR), params).one()
            except DBAPIError as exc:
                error, fila = exc, None
            gucs = {
                guc: conn.scalar(text("select current_setting(:g, true)"), {"g": guc})
                for guc in OWNER_GUCS
            }
        finally:
            tx.rollback()
    return fila, error, gucs


def test_function_rejects_an_inactive_or_unknown_developer(client, headers, logo_db, app_engine):
    empresa = _empresa(client, headers)
    inactivo = sembrar_dev(logo_db, nuevo_dev("logo-inactivo"), activo=False)
    for desarrollador in (inactivo.id, uuid.uuid4()):
        fila, error, gucs = _llamar(app_engine, desarrollador, empresa.id, uuid.uuid4())
        assert fila is None
        assert error.orig.sqlstate == INSUFFICIENT_PRIVILEGE
        assert "desarrollador_no_autorizado" in str(error.orig)
    assert _estado(logo_db, empresa.id) == _sin_logo(logo_db, empresa.id)


def test_function_rejects_a_key_of_another_tenant_and_clears_its_gucs(
    client, headers, logo_db, app_engine, dev
):
    una, otra = _empresa(client, headers), _empresa(client, headers)
    logo = uuid.uuid4()
    fila, error, gucs = _llamar(app_engine, dev.id, una.id, logo, clave=f"{otra.id}/{logo}.png")
    assert fila is None and error.orig.sqlstate == "22023"
    assert "clave_invalida" in str(error.orig)
    # Con éxito (y revertido por la prueba) las GUC también quedan vacías.
    fila, error, gucs = _llamar(app_engine, dev.id, una.id, logo)
    assert error is None and tuple(fila) == (logo, True, False)
    assert all(valor in ("", None) for valor in gucs.values()), gucs
    assert _estado(logo_db, una.id) == _sin_logo(logo_db, una.id)


def test_function_reports_a_replacement_and_clears_its_gucs(
    client, headers, logo_db, app_engine, dev
):
    empresa = _empresa(client, headers)
    vigente = uuid.uuid4()
    assert _subir(client, headers, empresa.id, _png(), vigente).status_code == 201
    fila, error, gucs = _llamar(app_engine, dev.id, empresa.id, vigente)
    assert error is None and tuple(fila) == (vigente, False, False)
    nuevo = uuid.uuid4()
    fila, error, gucs = _llamar(app_engine, dev.id, empresa.id, nuevo)
    assert error is None and tuple(fila) == (nuevo, True, True)
    assert all(valor in ("", None) for valor in gucs.values()), gucs
    # La prueba revirtió: el vigente sigue siendo el primero.
    assert _estado(logo_db, empresa.id)["logo_id"] == [{"logo_id": vigente}]


def test_the_developer_reads_no_other_company_columns(logo_db, app_engine, client, headers, dev):
    """A19 (C1): de empresa, plataforma_owner lee tenant_id, logo_id y las cinco columnas de
    la ficha (nunca actualizada_por ni actualizada_en); la app, nada."""
    columnas = {
        row["column_name"]
        for row in filas(
            logo_db,
            "select column_name from information_schema.columns "
            "where table_schema = 'public' and table_name = 'empresa'",
        )
    }
    legibles = {
        columna
        for columna in columnas
        if filas(
            logo_db,
            "select has_column_privilege('plataforma_owner', 'public.empresa', :c, 'SELECT') as s",
            {"c": columna},
        )[0]["s"]
    }
    assert legibles == {"tenant_id", "logo_id", "nombre", "direccion", "nit", "telefono", "correo"}
    for tabla in ("empresa_logo",):
        for columna in ("id", "clave", "tenant_id", "subido_por"):
            permiso = filas(
                logo_db,
                f"select has_column_privilege('plataforma_owner', 'public.{tabla}', :c, "  # noqa: S608
                "'SELECT') as s",
                {"c": columna},
            )[0]["s"]
            assert permiso is False, columna
    # En una plataforma_session la aplicación no ve ninguna fila de empresa ni de logos.
    empresa = _empresa(client, headers)
    assert _subir(client, headers, empresa.id, _png()).status_code == 201
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(
                text("select set_config('app.desarrollador_id', :d, true)"), {"d": str(dev.id)}
            )
            assert conn.scalar(text("select count(*) from empresa")) == 0
            assert conn.scalar(text("select count(*) from empresa_logo")) == 0
        finally:
            tx.rollback()


# --- Logs -------------------------------------------------------------------------------


def test_logs_never_carry_the_file_its_name_nor_the_key(client, headers, logo_db, caplog):
    empresa = _empresa(client, headers)
    logo_id = uuid.uuid4()
    caplog.set_level(logging.DEBUG)
    assert _subir(client, headers, empresa.id, _png(), logo_id).status_code == 201
    _subir(client, headers, empresa.id, b"no es imagen", nombre=NOMBRE_ARCHIVO)
    _subir(client, headers, empresa.id, _png())  # reemplazo (C1)
    texto = caplog.text
    # El texto incrustado en el PNG (MARCA_METADATOS) representa el contenido del archivo.
    for secreto in (NOMBRE_ARCHIVO, MARCA_METADATOS, f"{empresa.id}/{logo_id}.png"):
        assert secreto not in texto, secreto
