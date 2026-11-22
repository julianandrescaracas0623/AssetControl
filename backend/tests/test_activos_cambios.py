"""Cambios sobre activos existentes (spec 005; R1–R3, R7, R9, A2; plan.md §3–§4).

Sobre una base temporal con dos tenants (A y B) y un catálogo creado por la API:

- T2, editar (``PATCH /activos/{id}``): ``If-Match`` obligatorio (``428``), versión vieja
  ``412`` con el activo vigente y sin guardar nada; un evento por clase de cambio
  (``precio_cambiado``, ``categoria_cambiada``, ``datos_cambiados``) con antes/después
  y autor, en la misma transacción; ``row_version`` sube una vez; sin cambios no hay
  evento ni versión nueva; ``codigo`` nunca cambia; solo el admin; dado de baja ``409``.
- Spec 015, T1 (R4, A3): ``PATCH``, ``mover``, ``estado``, ``baja`` y el ``412`` devuelven
  la ficha con ``foto`` (misma forma que ``GET /activos/{id}``).
"""

import io
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
from PIL import Image
from sqlalchemy import text

from app.fotos.almacen import EXTENSION_KEY, CarpetaLocal

ADMIN = bearer(ADMIN_A, TENANT_A)
CONTADOR = bearer(CONTADOR_A, TENANT_A, rol="contador")
ADMIN_OTRO = bearer(ADMIN_B, TENANT_B)


@pytest.fixture(scope="module")
def cam_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("activos_cambios")


@pytest.fixture(scope="module")
def cam_app(cam_db, tmp_path_factory) -> Iterator[Flask]:
    flask_app = make_app(cam_db)
    # Almacén en carpeta temporal: la spec 015 (R4) prueba que las escrituras traen la foto.
    flask_app.extensions[EXTENSION_KEY] = CarpetaLocal(tmp_path_factory.mktemp("almacen"))
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(cam_app):
    return cam_app.test_client(use_cookies=False)


@pytest.fixture(scope="module")
def cat(cam_app) -> dict[str, str]:
    """Sede > sala > box, otra sala, dos categorías en A; sala y categoría en B."""
    client = cam_app.test_client(use_cookies=False)

    def post(path, body, headers=ADMIN):
        response = client.post(path, json=body, headers=headers)
        assert response.status_code == 201, response.get_json()
        return response.get_json()

    def ubicacion(nombre, tipo, padre=None, headers=ADMIN):
        body = {"nombre": nombre, "tipo": tipo, **({"padre_id": padre} if padre else {})}
        return post("/ubicaciones", body, headers)["ubicacion"]["id"]

    sede = ubicacion("Sede", "sede")
    sala = ubicacion("Consultorios", "sala", sede)
    ids = {
        "sede": sede,
        "sala": sala,
        "box": ubicacion("Box 2", "box", sala),
        "otra_sala": ubicacion("Bodega", "sala", sede),
        "sede_b": ubicacion("Sede B", "sede", headers=ADMIN_OTRO),
    }
    ids["sala_b"] = ubicacion("Sala B", "sala", ids["sede_b"], headers=ADMIN_OTRO)
    ids["cat"] = post("/categorias", {"nombre": "Biomédicos"})["categoria"]["id"]
    ids["cat2"] = post("/categorias", {"nombre": "Muebles"})["categoria"]["id"]
    ids["cat_b"] = post("/categorias", {"nombre": "Otra"}, ADMIN_OTRO)["categoria"]["id"]
    return ids


def nuevo(client, cat, **cambios) -> dict:
    body = {
        "id": str(uuid.uuid4()),
        "codigo": f"AC-{uuid.uuid4().hex[:8].upper()}",
        "nombre": "Autoclave clase B 18 L",
        "precio_compra": "14200000.00",
        "categoria_id": cat["cat"],
        "ubicacion_id": cat["box"],
        "marca": "Tuttnauer",
        **cambios,
    }
    response = client.post("/activos", json=body, headers=ADMIN)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["activo"]


def version(n: int) -> dict[str, str]:
    return {"If-Match": f'"{n}"'}


def editar(client, activo_id, body, *, v=1, headers=ADMIN):
    return client.patch(f"/activos/{activo_id}", json=body, headers={**headers, **version(v)})


def code(response) -> str:
    return response.get_json()["error"]["code"]


def eventos(db: AccesoDb, activo_id: str) -> list[tuple[str, dict, uuid.UUID]]:
    with db.migrator.connect() as conn:
        filas = conn.execute(
            text(
                "select tipo, datos, usuario_id from activo_evento "
                "where activo_id = :a and tipo <> 'creado' order by seq"
            ),
            {"a": activo_id},
        )
        return [tuple(f) for f in filas]


def dar_de_baja_en_la_base(db: AccesoDb, activo_id: str) -> None:
    """Hasta T3 no hay endpoint de baja: se marca con el migrador."""
    with db.migrator.begin() as conn:
        conn.execute(
            text(
                "update activo set estado = 'dado_de_baja', row_version = row_version + 1 "
                "where id = :a"
            ),
            {"a": activo_id},
        )


# --- T2: editar ------------------------------------------------------------------------


def test_activo_response_carries_its_version_for_both_roles(client, cat):
    activo = nuevo(client, cat)
    assert activo["row_version"] == 1
    ficha = client.get(f"/activos/{activo['id']}", headers=CONTADOR).get_json()["activo"]
    assert ficha["row_version"] == 1
    assert "precio_compra" not in ficha


def test_admin_edits_and_each_kind_of_change_leaves_its_event(client, cat, cam_db):
    activo = nuevo(client, cat, serial="SN-1")
    response = editar(
        client,
        activo["id"],
        {
            "nombre": "Autoclave clase B 23 L",
            "precio_compra": "15000000.50",
            "categoria_id": cat["cat2"],
            "marca": None,
            "modelo": "Elara 11",
            "serial": "",
            "fecha_compra": "2024-03-01",
        },
    )

    assert response.status_code == 200, response.get_json()
    assert response.headers["ETag"] == '"2"'
    editado = response.get_json()["activo"]
    assert editado["row_version"] == 2
    assert editado["codigo"] == activo["codigo"]
    assert editado["nombre"] == "Autoclave clase B 23 L"
    assert editado["precio_compra"] == "15000000.50"
    assert editado["categoria"] == {"id": cat["cat2"], "nombre": "Muebles"}
    assert (editado["marca"], editado["modelo"], editado["serial"]) == (None, "Elara 11", None)
    assert editado["fecha_compra"] == "2024-03-01"

    assert eventos(cam_db, activo["id"]) == [
        (
            "precio_cambiado",
            {"antes": "14200000.00", "despues": "15000000.50"},
            ADMIN_A.usuario_id,
        ),
        (
            "categoria_cambiada",
            {
                "antes": {"id": cat["cat"], "nombre": "Biomédicos"},
                "despues": {"id": cat["cat2"], "nombre": "Muebles"},
            },
            ADMIN_A.usuario_id,
        ),
        (
            "datos_cambiados",
            {
                "campos": {
                    "nombre": {
                        "antes": "Autoclave clase B 18 L",
                        "despues": "Autoclave clase B 23 L",
                    },
                    "serial": {"antes": "SN-1", "despues": None},
                    "marca": {"antes": "Tuttnauer", "despues": None},
                    "modelo": {"antes": None, "despues": "Elara 11"},
                    "fecha_compra": {"antes": None, "despues": "2024-03-01"},
                }
            },
            ADMIN_A.usuario_id,
        ),
    ]


def test_saving_without_changes_touches_nothing(client, cat, cam_db):
    activo = nuevo(client, cat)
    response = editar(
        client,
        activo["id"],
        {"nombre": " Autoclave clase B 18 L ", "precio_compra": "14200000", "marca": "Tuttnauer"},
    )
    assert response.status_code == 200
    assert response.get_json()["activo"]["row_version"] == 1
    assert response.headers["ETag"] == '"1"'
    assert eventos(cam_db, activo["id"]) == []


def test_only_one_change_class_writes_only_its_event(client, cat, cam_db):
    activo = nuevo(client, cat)
    response = editar(client, activo["id"], {"precio_compra": "1.5"})
    assert response.get_json()["activo"]["precio_compra"] == "1.50"
    assert [e[0] for e in eventos(cam_db, activo["id"])] == ["precio_cambiado"]


@pytest.mark.parametrize("if_match", [None, "", "abc", 'W/"1"', '"1', "-1", '"１"', "9" * 12])
def test_missing_or_malformed_if_match_is_428(client, cat, cam_db, if_match):
    activo = nuevo(client, cat)
    headers = {**ADMIN, **({"If-Match": if_match} if if_match is not None else {})}
    response = client.patch(f"/activos/{activo['id']}", json={"nombre": "X"}, headers=headers)
    assert response.status_code == 428
    assert code(response) == "falta_version"
    assert eventos(cam_db, activo["id"]) == []


def test_if_match_without_quotes_is_accepted(client, cat):
    activo = nuevo(client, cat)
    headers = {**ADMIN, "If-Match": "1"}
    response = client.patch(f"/activos/{activo['id']}", json={"nombre": "Otro"}, headers=headers)
    assert response.status_code == 200


def test_stale_version_is_412_with_the_current_asset_and_saves_nothing(client, cat, cam_db):
    activo = nuevo(client, cat)
    primero = editar(client, activo["id"], {"nombre": "Primero"})
    assert primero.status_code == 200

    segundo = editar(client, activo["id"], {"nombre": "Segundo", "precio_compra": "1.00"})

    assert segundo.status_code == 412
    cuerpo = segundo.get_json()
    assert cuerpo["error"]["code"] == "version_desactualizada"
    assert cuerpo["activo"]["nombre"] == "Primero"
    assert cuerpo["activo"]["row_version"] == 2
    assert cuerpo["activo"]["precio_compra"] == "14200000.00"
    assert [e[0] for e in eventos(cam_db, activo["id"])] == ["datos_cambiados"]


def test_a_future_version_is_also_412(client, cat):
    activo = nuevo(client, cat)
    assert editar(client, activo["id"], {"nombre": "X"}, v=7).status_code == 412


@pytest.mark.parametrize(
    ("body", "esperado"),
    [
        ({"codigo": "OTRO-1"}, "codigo_inmutable"),
        ({"nombre": "X", "codigo": "AC-1"}, "codigo_inmutable"),
        ({"precio_compra": "-1"}, "precio_invalido"),
        ({"precio_compra": 10.5}, "precio_invalido"),
        ({"nombre": None}, "solicitud_invalida"),
        ({"nombre": "   "}, "solicitud_invalida"),
        ({"nombre": "x" * 121}, "solicitud_invalida"),
        ({"marca": 3}, "solicitud_invalida"),
        ({"fecha_compra": "2999-01-01"}, "solicitud_invalida"),
        ({"fecha_compra": "31/01/2024"}, "solicitud_invalida"),
        ({"categoria_id": "no-uuid"}, "solicitud_invalida"),
        ({"categoria_id": None}, "solicitud_invalida"),
        ({"ubicacion_id": "x"}, "solicitud_invalida"),
        ({"estado": "en_reparacion"}, "solicitud_invalida"),
        ({"referencia": "R"}, "solicitud_invalida"),
        ({"atributos": {}}, "solicitud_invalida"),
    ],
)
def test_invalid_edits_are_400_and_save_nothing(client, cat, cam_db, body, esperado):
    activo = nuevo(client, cat)
    response = editar(client, activo["id"], body)
    assert response.status_code == 400, response.get_json()
    assert code(response) == esperado
    assert eventos(cam_db, activo["id"]) == []


def test_non_object_body_is_400(client, cat):
    activo = nuevo(client, cat)
    response = client.patch(
        f"/activos/{activo['id']}", json=["nombre"], headers={**ADMIN, **version(1)}
    )
    assert response.status_code == 400


def test_category_or_asset_of_another_tenant_is_404(client, cat, cam_db):
    activo = nuevo(client, cat)
    assert editar(client, activo["id"], {"categoria_id": cat["cat_b"]}).status_code == 404
    assert editar(client, activo["id"], {"nombre": "X"}, headers=ADMIN_OTRO).status_code == 404
    assert editar(client, str(uuid.uuid4()), {"nombre": "X"}).status_code == 404
    assert eventos(cam_db, activo["id"]) == []


def test_only_the_admin_edits(client, cat):
    activo = nuevo(client, cat)
    assert editar(client, activo["id"], {"nombre": "X"}, headers=CONTADOR).status_code == 403
    response = client.patch(f"/activos/{activo['id']}", json={"nombre": "X"}, headers=version(1))
    assert response.status_code == 401


def test_a_written_off_asset_cannot_be_edited(client, cat, cam_db):
    activo = nuevo(client, cat)
    dar_de_baja_en_la_base(cam_db, activo["id"])
    response = editar(client, activo["id"], {"nombre": "X"}, v=2)
    assert response.status_code == 409
    assert code(response) == "activo_dado_de_baja"
    assert eventos(cam_db, activo["id"]) == []


def test_the_code_never_changes_in_the_database(client, cat, cam_db):
    activo = nuevo(client, cat)
    editar(client, activo["id"], {"nombre": "Otro nombre"})
    with cam_db.migrator.connect() as conn:
        codigo = conn.scalar(text("select codigo from activo where id = :a"), {"a": activo["id"]})
    assert codigo == activo["codigo"]


# --- T3: mover, estado, baja y reactivar -------------------------------------------------


def accion(client, activo_id, nombre, body, *, v=1, headers=ADMIN):
    return client.post(
        f"/activos/{activo_id}/{nombre}", json=body, headers={**headers, **version(v)}
    )


def test_moving_leaves_the_old_and_new_route(client, cat, cam_db):
    activo = nuevo(client, cat)
    response = accion(client, activo["id"], "mover", {"ubicacion_id": cat["otra_sala"]})

    assert response.status_code == 200, response.get_json()
    assert response.headers["ETag"] == '"2"'
    movido = response.get_json()["activo"]
    assert movido["ubicacion"] == {"id": cat["otra_sala"], "nombre": "Bodega", "ruta": "Bodega"}
    assert eventos(cam_db, activo["id"]) == [
        (
            "ubicacion_cambiada",
            {
                "antes": {"id": cat["box"], "ruta": "Consultorios › Box 2"},
                "despues": {"id": cat["otra_sala"], "ruta": "Bodega"},
            },
            ADMIN_A.usuario_id,
        )
    ]


def test_moving_to_the_same_place_changes_nothing(client, cat, cam_db):
    activo = nuevo(client, cat)
    response = accion(client, activo["id"], "mover", {"ubicacion_id": cat["box"]})
    assert response.status_code == 200
    assert response.get_json()["activo"]["row_version"] == 1
    assert eventos(cam_db, activo["id"]) == []


def test_moving_follows_d1(client, cat, cam_db):
    activo = nuevo(client, cat)
    archivo = client.post(
        "/ubicaciones",
        json={"nombre": f"Archivo {uuid.uuid4().hex[:4]}", "tipo": "sala", "padre_id": cat["sede"]},
        headers=ADMIN,
    ).get_json()["ubicacion"]["id"]
    assert (
        client.patch(f"/ubicaciones/{archivo}", json={"activa": False}, headers=ADMIN).status_code
        == 200
    )
    for destino in (cat["sede"], archivo):
        response = accion(client, activo["id"], "mover", {"ubicacion_id": destino})
        assert response.status_code == 400
        assert code(response) == "ubicacion_invalida"
    assert accion(client, activo["id"], "mover", {"ubicacion_id": cat["sala_b"]}).status_code == 404
    for body in ({}, {"ubicacion_id": None}, {"ubicacion_id": cat["sala"], "otro": 1}):
        assert accion(client, activo["id"], "mover", body).status_code == 400
    assert eventos(cam_db, activo["id"]) == []


def test_moving_everything_out_lets_the_location_be_deactivated(client, cat):
    sala = client.post(
        "/ubicaciones",
        json={"nombre": f"Rayos X {uuid.uuid4().hex[:4]}", "tipo": "sala", "padre_id": cat["sede"]},
        headers=ADMIN,
    ).get_json()["ubicacion"]["id"]
    activo = nuevo(client, cat, ubicacion_id=sala)
    desactivar = {"activa": False}
    assert client.patch(f"/ubicaciones/{sala}", json=desactivar, headers=ADMIN).status_code == 409
    assert accion(client, activo["id"], "mover", {"ubicacion_id": cat["box"]}).status_code == 200
    assert client.patch(f"/ubicaciones/{sala}", json=desactivar, headers=ADMIN).status_code == 200


def test_repair_round_trip_leaves_two_events(client, cat, cam_db):
    activo = nuevo(client, cat)
    ida = accion(client, activo["id"], "estado", {"estado": "en_reparacion"})
    assert ida.status_code == 200
    assert ida.get_json()["activo"]["estado"] == "en_reparacion"
    vuelta = accion(client, activo["id"], "estado", {"estado": "activo"}, v=2)
    assert vuelta.get_json()["activo"]["row_version"] == 3
    assert [(t, d) for t, d, _ in eventos(cam_db, activo["id"])] == [
        ("estado_cambiado", {"antes": "activo", "despues": "en_reparacion"}),
        ("estado_cambiado", {"antes": "en_reparacion", "despues": "activo"}),
    ]


def test_same_state_changes_nothing(client, cat, cam_db):
    activo = nuevo(client, cat)
    response = accion(client, activo["id"], "estado", {"estado": "activo"})
    assert response.status_code == 200
    assert response.get_json()["activo"]["row_version"] == 1
    assert eventos(cam_db, activo["id"]) == []


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"estado": "dado_de_baja"},
        {"estado": "perdido"},
        {"estado": "en_reparacion", "motivo": "encontrado"},
        {"estado": "en_reparacion", "nota": "x"},
    ],
)
def test_invalid_state_changes_are_400(client, cat, cam_db, body):
    activo = nuevo(client, cat)
    assert accion(client, activo["id"], "estado", body).status_code == 400
    assert eventos(cam_db, activo["id"]) == []


@pytest.mark.parametrize(
    ("body", "datos"),
    [
        ({"motivo": "perdido"}, {"motivo": "perdido"}),
        (
            {"motivo": "danado_sin_reparacion", "nota": " Tarjeta quemada "},
            {"motivo": "danado_sin_reparacion", "nota": "Tarjeta quemada"},
        ),
        (
            {"motivo": "otro", "nota": "Robo reportado"},
            {"motivo": "otro", "nota": "Robo reportado"},
        ),
        ({"motivo": "obsoleto", "nota": ""}, {"motivo": "obsoleto"}),
    ],
)
def test_write_off_needs_a_reason_and_leaves_it(client, cat, cam_db, body, datos):
    activo = nuevo(client, cat)
    response = accion(client, activo["id"], "baja", body)
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["activo"]["estado"] == "dado_de_baja"
    assert eventos(cam_db, activo["id"]) == [("dado_de_baja", datos, ADMIN_A.usuario_id)]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"motivo": "robado"},
        {"motivo": "otro"},
        {"motivo": "otro", "nota": "   "},
        {"motivo": "perdido", "nota": "x" * 121},
        {"motivo": "perdido", "nota": 3},
        {"motivo": "perdido", "extra": 1},
    ],
)
def test_invalid_write_off_is_400(client, cat, cam_db, body):
    activo = nuevo(client, cat)
    response = accion(client, activo["id"], "baja", body)
    assert response.status_code == 400
    assert code(response) in {"motivo_invalido", "solicitud_invalida"}
    assert eventos(cam_db, activo["id"]) == []


def test_a_written_off_asset_is_read_only(client, cat, cam_db):
    activo = nuevo(client, cat)
    assert accion(client, activo["id"], "baja", {"motivo": "perdido"}).status_code == 200
    for nombre, body in (
        ("mover", {"ubicacion_id": cat["otra_sala"]}),
        ("estado", {"estado": "en_reparacion"}),
        ("baja", {"motivo": "obsoleto"}),
    ):
        response = accion(client, activo["id"], nombre, body, v=2)
        assert response.status_code == 409, nombre
        assert code(response) == "activo_dado_de_baja"
    assert editar(client, activo["id"], {"nombre": "X"}, v=2).status_code == 409
    assert [e[0] for e in eventos(cam_db, activo["id"])] == ["dado_de_baja"]


def test_reactivating_needs_a_reason_and_returns_to_active(client, cat, cam_db):
    activo = nuevo(client, cat)
    accion(client, activo["id"], "baja", {"motivo": "perdido"})
    for body in (
        {"estado": "activo"},
        {"estado": "activo", "motivo": "perdido"},
        {"estado": "activo", "motivo": "otro"},
    ):
        response = accion(client, activo["id"], "estado", body, v=2)
        assert response.status_code == 400, body
        assert code(response) == "motivo_invalido"

    response = accion(
        client, activo["id"], "estado", {"estado": "activo", "motivo": "encontrado"}, v=2
    )
    assert response.status_code == 200
    assert response.get_json()["activo"]["estado"] == "activo"
    assert eventos(cam_db, activo["id"])[-1] == (
        "estado_cambiado",
        {"antes": "dado_de_baja", "despues": "activo", "motivo": "encontrado"},
        ADMIN_A.usuario_id,
    )
    # De nuevo editable.
    assert editar(client, activo["id"], {"nombre": "Reaparecido"}, v=3).status_code == 200


@pytest.mark.parametrize(
    ("nombre", "body"),
    [
        ("mover", {"ubicacion_id": "x"}),
        ("estado", {"estado": "en_reparacion"}),
        ("baja", {"motivo": "perdido"}),
    ],
)
def test_lifecycle_actions_are_admin_only_and_versioned(client, cat, cam_db, nombre, body):
    activo = nuevo(client, cat)
    assert accion(client, activo["id"], nombre, body, headers=CONTADOR).status_code == 403
    sin_version = client.post(f"/activos/{activo['id']}/{nombre}", json=body, headers=ADMIN)
    assert sin_version.status_code == 428
    assert accion(client, activo["id"], nombre, body, v=5).status_code in {400, 412}
    assert accion(client, str(uuid.uuid4()), nombre, body).status_code in {400, 404}
    assert eventos(cam_db, activo["id"]) == []


def test_stale_version_on_actions_is_412(client, cat):
    activo = nuevo(client, cat)
    editar(client, activo["id"], {"nombre": "Ya cambió"})
    for nombre, body in (
        ("mover", {"ubicacion_id": cat["otra_sala"]}),
        ("estado", {"estado": "en_reparacion"}),
        ("baja", {"motivo": "perdido"}),
    ):
        response = accion(client, activo["id"], nombre, body)
        assert response.status_code == 412, nombre
        assert response.get_json()["activo"]["row_version"] == 2


# --- Spec 015, T1: las escrituras traen la foto (R4, A3) -----------------------------------


def con_foto(client, cat) -> tuple[dict, dict]:
    """Un activo con foto principal; devuelve el activo vigente y su foto."""
    activo = nuevo(client, cat)
    buffer = io.BytesIO()
    Image.new("RGB", (64, 48), (10, 120, 200)).save(buffer, "JPEG")
    subida = client.put(
        f"/activos/{activo['id']}/foto",
        data={"foto_id": str(uuid.uuid4()), "archivo": (io.BytesIO(buffer.getvalue()), "a.jpg")},
        headers=ADMIN,
        content_type="multipart/form-data",
    )
    assert subida.status_code == 201, subida.get_json()
    ficha = client.get(f"/activos/{activo['id']}", headers=ADMIN).get_json()["activo"]
    assert ficha["foto"] is not None
    return ficha, ficha["foto"]


@pytest.mark.parametrize(
    ("nombre", "body"),
    [
        ("editar", lambda cat: {"nombre": "Autoclave renombrada"}),
        ("mover", lambda cat: {"ubicacion_id": cat["otra_sala"]}),
        ("estado", lambda cat: {"estado": "en_reparacion"}),
        ("baja", lambda cat: {"motivo": "perdido"}),
    ],
)
def test_every_write_returns_the_card_with_its_photo(client, cat, nombre, body):
    activo, foto = con_foto(client, cat)
    v = activo["row_version"]
    if nombre == "editar":
        response = editar(client, activo["id"], body(cat), v=v)
    else:
        response = accion(client, activo["id"], nombre, body(cat), v=v)

    assert response.status_code == 200, response.get_json()
    escrito = response.get_json()["activo"]
    assert escrito["foto"] == foto
    assert escrito["precio_compra"] == "14200000.00"
    ficha = client.get(f"/activos/{activo['id']}", headers=ADMIN).get_json()["activo"]
    assert escrito == ficha
    assert response.headers["ETag"] == f'"{ficha["row_version"]}"'


def test_a_write_without_photo_returns_foto_null(client, cat):
    activo = nuevo(client, cat)
    response = editar(client, activo["id"], {"nombre": "Sin foto"})
    assert response.status_code == 200
    assert response.get_json()["activo"]["foto"] is None


def test_stale_version_412_also_carries_the_photo(client, cat):
    activo, foto = con_foto(client, cat)
    v = activo["row_version"]
    assert editar(client, activo["id"], {"nombre": "Ya cambió"}, v=v).status_code == 200

    respuestas = [editar(client, activo["id"], {"nombre": "Tarde"}, v=v)]
    respuestas += [
        accion(client, activo["id"], nombre, body, v=v)
        for nombre, body in (
            ("mover", {"ubicacion_id": cat["otra_sala"]}),
            ("estado", {"estado": "en_reparacion"}),
            ("baja", {"motivo": "perdido"}),
        )
    ]
    for response in respuestas:
        assert response.status_code == 412
        vigente = response.get_json()["activo"]
        assert vigente["foto"] == foto
        assert vigente["row_version"] == v + 1
        assert vigente["precio_compra"] == "14200000.00"


def escrituras(client, activo_id, cat, *, v, headers):
    """PATCH, mover, estado y baja con la misma versión y el mismo rol."""
    respuestas = {"editar": editar(client, activo_id, {"nombre": "Ajeno"}, v=v, headers=headers)}
    for nombre, body in (
        ("mover", {"ubicacion_id": cat["otra_sala"]}),
        ("estado", {"estado": "en_reparacion"}),
        ("baja", {"motivo": "perdido"}),
    ):
        respuestas[nombre] = accion(client, activo_id, nombre, body, v=v, headers=headers)
    return respuestas


def test_another_tenant_never_sees_the_card_nor_its_photo(client, cat):
    activo, foto = con_foto(client, cat)
    v = activo["row_version"]
    assert editar(client, activo["id"], {"nombre": "Ya cambió"}, v=v).status_code == 200

    for version_enviada in (v + 1, v):  # la real y una vieja
        respuestas = escrituras(client, activo["id"], cat, v=version_enviada, headers=ADMIN_OTRO)
        for nombre, response in respuestas.items():
            assert response.status_code == 404, (nombre, version_enviada)
            cuerpo = response.get_json()
            assert "activo" not in cuerpo, nombre
            assert "foto" not in cuerpo, nombre

    ficha = client.get(f"/activos/{activo['id']}", headers=ADMIN).get_json()["activo"]
    assert ficha["foto"] == foto
    assert ficha["row_version"] == v + 1
    assert ficha["nombre"] == "Ya cambió"


def test_a_counter_with_a_stale_version_gets_403_without_the_card(client, cat):
    activo, _ = con_foto(client, cat)
    v = activo["row_version"]
    assert editar(client, activo["id"], {"nombre": "Ya cambió"}, v=v).status_code == 200

    for nombre, response in escrituras(client, activo["id"], cat, v=v, headers=CONTADOR).items():
        assert response.status_code == 403, nombre
        assert "activo" not in response.get_json(), nombre


def test_the_counter_reads_the_photo_but_never_the_price(client, cat):
    activo, foto = con_foto(client, cat)
    response = client.get(f"/activos/{activo['id']}", headers=CONTADOR)
    assert response.status_code == 200
    ficha = response.get_json()["activo"]
    assert ficha["foto"] == foto
    assert "precio_compra" not in ficha
