"""Editar la ficha de una empresa desde la consola (spec 017, C1, T12; R41–R43, R45, R52;
A21, A21b, A23; CU-12).

Sobre una base temporal migrada a ``head`` (tenants sintéticos A y B de ``acceso_db``), con
la consola habilitada. Cada prueba crea su empresa con ``POST /plataforma/empresas``, así
ninguna depende del orden de las demás.

- ``GET /plataforma/empresas/{id}/ficha``: exactamente las seis claves de R41; ``404``;
  ``409 empresa_sin_datos``; no cuenta en ``plat_accion``.
- ``PUT /plataforma/empresas/{id}/ficha``: validaciones de la 013 (``422`` con ``campo``,
  sin cambios), cuerpo estricto (``400``), solo las cinco columnas y ``actualizada_en``
  (``actualizada_por`` y ``logo_id`` intactos), ``tenant.nombre`` si cambia el nombre (Q-E1;
  nada más de ``tenant``), ``empresa_editada`` sin valores y solo con un cambio real,
  ``404``, ``409``, ``503`` con la fila bloqueada, carrera con la edición del admin (013),
  informes cerrados intactos, el otro tenant intacto, ``plat_accion``, ``401`` a los tokens
  de tenant y a un desarrollador desactivado.
- SQL: las dos funciones rechazan a un desarrollador inactivo o inexistente sin leer ni
  escribir, y dejan las GUC vacías.
- Auditoría y logs sin los valores de la ficha.

Datos sintéticos (``@ejemplo.test``).
"""

import dataclasses
import logging
import threading
import time
import uuid
from collections.abc import Iterator

import pytest
from acceso_db import (
    ADMIN_A,
    TENANT_A,
    TENANT_B,
    AccesoDb,
    Cuenta,
    bearer,
    dispose,
    temporary_acceso_db,
)
from flask import Flask
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
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from app.db import UnscopedStatementError, tenant_session

ADMIN_PASSWORD = "Clave-Inicial-Sintetica-2026"
RUTA = "/plataforma/empresas"
LEER = "select * from acceso.plataforma_leer_empresa(:d, :t)"
ACTUALIZAR = "select acceso.plataforma_actualizar_empresa(:d, :t, :n, :di, :ni, :te, :co)"
INSUFFICIENT_PRIVILEGE = "42501"
LOCK_TIMEOUT_SEGUNDOS = 5
CLAVES_FICHA = {"nombre", "direccion", "nit", "telefono", "correo", "tiene_logo"}
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
    "app.plat_empresa_tenant",
)
# Una ficha nueva, con valores reconocibles para buscarlos en la auditoría y en los logs.
NUEVA = {
    "nombre": "Clínica Centinela Editada S.A.S.",
    "direccion": "Carrera 99 # 88-77, Centinela",
    "nit": "900.123.456-8",
    "telefono": "(602) 555 0199",
    "correo": "centinela.editada@ejemplo.test",
}


@pytest.fixture(scope="module")
def edicion_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("plat_edicion")


@pytest.fixture(scope="module")
def edicion_app(edicion_db) -> Iterator[Flask]:
    flask_app = make_plat_app(edicion_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(edicion_app):
    return edicion_app.test_client(use_cookies=False)


@pytest.fixture(scope="module")
def dev(edicion_db):
    return sembrar_dev(edicion_db, nuevo_dev("edicion"))


@pytest.fixture(scope="module")
def headers(edicion_app, dev) -> dict[str, str]:
    response = login(edicion_app.test_client(use_cookies=False), dev.email)
    assert response.status_code == 200
    return plat_bearer(response.get_json()["access_token"])


@pytest.fixture(scope="module")
def app_engine(edicion_db) -> Iterator[Engine]:
    engine = create_engine(edicion_db.app_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


# --- Utilidades -------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Empresa:
    id: uuid.UUID
    nombre: str
    admin: Cuenta


def _empresa(client, headers, **ficha) -> Empresa:
    email = f"admin.{uuid.uuid4().hex[:10]}@ejemplo.test"
    nombre = f"Clínica Edición {uuid.uuid4().hex[:6]}"
    body = {
        "id": str(uuid.uuid4()),
        "nombre": nombre,
        "direccion": "Calle 1 # 2-3, Cartago",
        "nit": "800.200.300",
        "telefono": "3001234567",
        "correo": "contacto@ejemplo.test",
        **ficha,
        "admin": {
            "nombre": "Admin Edición",
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
        body["nombre"],
        Cuenta(uuid.UUID(creada["admin_id"]), email, "Admin Edición"),
    )


def _ficha_url(empresa_id) -> str:
    return f"{RUTA}/{empresa_id}/ficha"


def _put(client, headers, empresa_id, body):
    return client.put(_ficha_url(empresa_id), json=body, headers=headers)


def _fila(db: AccesoDb, tenant_id) -> dict:
    """Toda la fila de ``empresa`` (con lo que la edición no debe tocar)."""
    rows = filas(db, "select * from empresa where tenant_id = :t", {"t": tenant_id})
    return rows[0] if rows else {}


def _tenant(db: AccesoDb, tenant_id) -> dict:
    rows = filas(db, "select * from tenant where id = :t", {"t": tenant_id})
    return rows[0] if rows else {}


def _auditoria(db: AccesoDb, tenant_id) -> list[dict]:
    return filas(
        db,
        "select * from plataforma_auditoria where tenant_id = :t "
        "and accion = 'empresa_editada' order by creado_en, id",
        {"t": tenant_id},
    )


def _conteos(db: AccesoDb) -> dict[str, int]:
    tablas = (
        "tenant",
        "usuario",
        "membresia",
        "empresa",
        "empresa_logo",
        "sesion_conteo",
        "sesion_empresa",
        "refresh_token",
        "plataforma_auditoria",
    )
    with db.migrator.connect() as conn:
        return {t: conn.scalar(text(f"select count(*) from {t}")) for t in tablas}  # noqa: S608


def _estado(db: AccesoDb, tenant_id) -> dict:
    return {
        "empresa": _fila(db, tenant_id),
        "tenant": _tenant(db, tenant_id),
        "auditoria": _auditoria(db, tenant_id),
    }


def _admin_listo(db: AccesoDb, empresa: Empresa) -> dict[str, str]:
    """El admin creado por la consola, ya con su contraseña cambiada (R26)."""
    ejecutar(
        db,
        "update usuario set debe_cambiar_password = false where id = :u",
        {"u": empresa.admin.usuario_id},
    )
    return bearer(empresa.admin, empresa.id)


# --- GET …/ficha (R41) ------------------------------------------------------------------


def test_get_returns_exactly_the_six_keys_of_the_ficha(client, headers, edicion_db):
    empresa = _empresa(client, headers)
    response = client.get(_ficha_url(empresa.id), headers=headers)
    assert response.status_code == 200, response.get_json()
    assert response.headers["Cache-Control"] == "no-store"
    body = response.get_json()
    assert set(body) == CLAVES_FICHA
    assert body == {
        "nombre": empresa.nombre,
        "direccion": "Calle 1 # 2-3, Cartago",
        "nit": "800.200.300",
        "telefono": "3001234567",
        "correo": "contacto@ejemplo.test",
        "tiene_logo": False,
    }
    # Opcionales vacíos: null.
    sin_opcionales = _empresa(client, headers, nit=None, telefono=None, correo=None)
    body = client.get(_ficha_url(sin_opcionales.id), headers=headers).get_json()
    assert (body["nit"], body["telefono"], body["correo"]) == (None, None, None)


def test_get_says_whether_there_is_a_logo_but_not_which(client, headers, edicion_db):
    empresa = _empresa(client, headers)
    logo, admin = uuid.uuid4(), empresa.admin.usuario_id
    ejecutar(
        edicion_db,
        "insert into empresa_logo (id, tenant_id, clave, bytes, ancho, alto, subido_por) "
        "values (:l, :t, :c, 1, 1, 1, :u)",
        {"l": logo, "t": empresa.id, "c": f"{empresa.id}/{logo}.png", "u": admin},
    )
    ejecutar(
        edicion_db,
        "update empresa set logo_id = :l where tenant_id = :t",
        {"l": logo, "t": empresa.id},
    )
    response = client.get(_ficha_url(empresa.id), headers=headers)
    body = response.get_json()
    assert body["tiene_logo"] is True
    assert str(logo) not in response.get_data(as_text=True)
    assert str(admin) not in response.get_data(as_text=True)


def test_get_unknown_company_is_404_and_without_ficha_is_409(client, headers):
    response = client.get(_ficha_url(uuid.uuid4()), headers=headers)
    assert (response.status_code, error_code(response)) == (404, "no_encontrado")
    # El tenant A sembrado no tiene ficha empresa (lo crea la CLI, no la consola).
    response = client.get(_ficha_url(TENANT_A), headers=headers)
    assert (response.status_code, error_code(response)) == (409, "empresa_sin_datos")


def test_get_does_not_count_in_plat_accion(edicion_db):
    flask_app = make_plat_app(
        edicion_db, rate_limits=dataclasses.replace(HIGH_LIMITS, plat_accion=1)
    )
    try:
        client = flask_app.test_client(use_cookies=False)
        otro = sembrar_dev(edicion_db, nuevo_dev("tope-ficha-get"))
        auth = plat_bearer(login(client, otro.email).get_json()["access_token"])
        empresa = _empresa(client, auth)  # 1 (el tope)
        for _ in range(3):
            assert client.get(_ficha_url(empresa.id), headers=auth).status_code == 200
    finally:
        dispose(flask_app)


# --- PUT …/ficha (R42, R43, R45) --------------------------------------------------------


def test_put_changes_only_the_five_columns_and_the_tenant_name(client, headers, edicion_db, dev):
    empresa = _empresa(client, headers)
    otra = _empresa(client, headers)
    antes_empresa, antes_tenant = _fila(edicion_db, empresa.id), _tenant(edicion_db, empresa.id)
    otra_antes = _estado(edicion_db, otra.id)
    b_antes = _tenant(edicion_db, TENANT_B)
    conteos = _conteos(edicion_db)

    response = _put(client, headers, empresa.id, NUEVA)
    assert response.status_code == 200, response.get_json()
    assert response.headers["Cache-Control"] == "no-store"
    assert response.get_json() == {**NUEVA, "tiene_logo": False}

    despues = _fila(edicion_db, empresa.id)
    for columna in ("nombre", "direccion", "nit", "telefono", "correo"):
        assert despues[columna] == NUEVA[columna], columna
    assert despues["actualizada_en"] > antes_empresa["actualizada_en"]
    # El resto de la fila de empresa no cambia (actualizada_por sigue siendo el admin).
    resto = {"tenant_id", "logo_id", "actualizada_por"}
    assert {k: despues[k] for k in resto} == {k: antes_empresa[k] for k in resto}
    # Q-E1: tenant.nombre sigue a la ficha; nada más del tenant cambia.
    tenant = _tenant(edicion_db, empresa.id)
    assert tenant == {**antes_tenant, "nombre": NUEVA["nombre"]}
    # Una fila de auditoría del desarrollador, sin objeto (la empresa va en tenant_id).
    auditoria = _auditoria(edicion_db, empresa.id)
    assert [
        {k: fila[k] for k in ("desarrollador_id", "accion", "resultado", "tenant_id", "objeto_id")}
        for fila in auditoria
    ] == [
        {
            "desarrollador_id": dev.id,
            "accion": "empresa_editada",
            "resultado": "ok",
            "tenant_id": empresa.id,
            "objeto_id": None,
        }
    ]
    # Ninguna otra tabla cambia de tamaño salvo la auditoría; la otra empresa y el tenant B,
    # intactos.
    assert _conteos(edicion_db) == {
        **conteos,
        "plataforma_auditoria": conteos["plataforma_auditoria"] + 1,
    }
    assert _estado(edicion_db, otra.id) == otra_antes
    assert _tenant(edicion_db, TENANT_B) == b_antes


def test_the_new_name_shows_in_the_lists_of_the_console(client, headers, edicion_db):
    empresa = _empresa(client, headers)
    nombre = f"Clínica Renombrada {uuid.uuid4().hex[:6]}"
    assert _put(client, headers, empresa.id, {**NUEVA, "nombre": nombre}).status_code == 200
    lista = client.get(RUTA, headers=headers).get_json()["empresas"]
    assert [e["nombre"] for e in lista if e["id"] == str(empresa.id)] == [nombre]
    actividad = client.get(
        "/plataforma/actividad", query_string={"empresa_id": str(empresa.id)}, headers=headers
    ).get_json()["actividad"]
    assert actividad and {r["empresa_nombre"] for r in actividad} == {nombre}


def test_the_same_values_are_200_without_writing_nor_auditing(client, headers, edicion_db):
    empresa = _empresa(client, headers)
    assert _put(client, headers, empresa.id, NUEVA).status_code == 200
    estado = _estado(edicion_db, empresa.id)

    response = _put(client, headers, empresa.id, NUEVA)
    assert response.status_code == 200
    assert response.get_json() == {**NUEVA, "tiene_logo": False}
    assert _estado(edicion_db, empresa.id) == estado
    # Los mismos valores escritos de otra forma (la 013 normaliza): tampoco cambia nada.
    otra_forma = {
        **NUEVA,
        "nit": " 900123456 - 8 ",
        "direccion": "  Carrera 99 # 88-77,  Centinela",
    }
    assert _put(client, headers, empresa.id, otra_forma).status_code == 200
    assert _estado(edicion_db, empresa.id) == estado


def test_without_a_name_change_the_tenant_name_is_not_touched(client, headers, edicion_db):
    empresa = _empresa(client, headers)
    # El admin (013) ya podía hacer divergir tenant.nombre de empresa.nombre.
    ejecutar(
        edicion_db,
        "update tenant set nombre = 'Nombre del tenant distinto' where id = :t",
        {"t": empresa.id},
    )
    tenant = _tenant(edicion_db, empresa.id)
    body = {**NUEVA, "nombre": empresa.nombre}
    response = _put(client, headers, empresa.id, body)
    assert response.status_code == 200
    assert _fila(edicion_db, empresa.id)["direccion"] == NUEVA["direccion"]
    assert _tenant(edicion_db, empresa.id) == tenant
    assert len(_auditoria(edicion_db, empresa.id)) == 1


def test_clearing_the_optional_fields_stores_null(client, headers, edicion_db):
    empresa = _empresa(client, headers)
    body = {**NUEVA, "nit": None, "telefono": "", "correo": "   "}
    response = _put(client, headers, empresa.id, body)
    assert response.status_code == 200, response.get_json()
    fila = _fila(edicion_db, empresa.id)
    assert (fila["nit"], fila["telefono"], fila["correo"]) == (None, None, None)


@pytest.mark.parametrize(
    ("campo", "valor"),
    [
        ("nombre", ""),
        ("nombre", "   "),
        ("nombre", "x" * 121),
        ("nombre", 12),
        ("direccion", ""),
        ("direccion", None),
        ("direccion", "x" * 201),
        ("nit", "900123456-7"),
        ("nit", "abc"),
        ("telefono", "123"),
        ("telefono", "1" * 31),
        ("correo", "no-es-un-correo"),
    ],
    ids=[
        "nombre-vacio",
        "nombre-espacios",
        "nombre-largo",
        "nombre-numero",
        "direccion-vacia",
        "direccion-nula",
        "direccion-larga",
        "nit-dv-errado",
        "nit-letras",
        "telefono-corto",
        "telefono-largo",
        "correo-invalido",
    ],
)
def test_an_invalid_field_is_422_without_changes(client, headers, edicion_db, campo, valor):
    empresa = _empresa(client, headers)
    estado = _estado(edicion_db, empresa.id)
    response = _put(client, headers, empresa.id, {**NUEVA, campo: valor})
    assert (response.status_code, error_code(response)) == (422, "campo_invalido")
    assert response.get_json()["error"]["campo"] == campo
    assert _estado(edicion_db, empresa.id) == estado


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        "texto",
        {k: v for k, v in NUEVA.items() if k != "nit"},
        {k: v for k, v in NUEVA.items() if k != "nombre"},
        {**NUEVA, "logo_id": str(uuid.uuid4())},
        {**NUEVA, "actualizada_por": str(uuid.uuid4())},
        {**NUEVA, "activa": False},
    ],
    ids=[
        "nulo",
        "lista",
        "texto",
        "sin-nit",
        "sin-nombre",
        "logo-id",
        "actualizada-por",
        "activa",
    ],
)
def test_the_body_is_strict(client, headers, edicion_db, body):
    empresa = _empresa(client, headers)
    estado = _estado(edicion_db, empresa.id)
    response = _put(client, headers, empresa.id, body)
    assert (response.status_code, error_code(response)) == (400, "solicitud_invalida")
    assert _estado(edicion_db, empresa.id) == estado


def test_put_unknown_company_is_404_and_without_ficha_is_409(client, headers, edicion_db):
    tenant_a = _tenant(edicion_db, TENANT_A)
    conteos = _conteos(edicion_db)
    response = _put(client, headers, uuid.uuid4(), NUEVA)
    assert (response.status_code, error_code(response)) == (404, "no_encontrado")
    response = _put(client, headers, TENANT_A, NUEVA)
    assert (response.status_code, error_code(response)) == (409, "empresa_sin_datos")
    # No se crea la ficha ni se renombra el tenant.
    assert _tenant(edicion_db, TENANT_A) == tenant_a
    assert _conteos(edicion_db) == conteos


def test_a_deactivated_company_can_be_edited(client, headers, edicion_db):
    """Q-E3 (hereda D3): editar una empresa desactivada está permitido; sigue desactivada."""
    empresa = _empresa(client, headers)
    response = client.patch(f"{RUTA}/{empresa.id}", json={"activa": False}, headers=headers)
    assert response.status_code == 200
    assert _put(client, headers, empresa.id, NUEVA).status_code == 200
    tenant = _tenant(edicion_db, empresa.id)
    assert (tenant["nombre"], tenant["activo"]) == (NUEVA["nombre"], False)
    assert tenant["desactivado_en"] is not None


def test_a_locked_company_row_is_503_after_the_lock_timeout(client, headers, edicion_db):
    empresa = _empresa(client, headers)
    estado = _estado(edicion_db, empresa.id)
    tomado, soltar = threading.Event(), threading.Event()

    def bloquear() -> None:
        with edicion_db.migrator.connect() as conn:
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
        response = _put(client, headers, empresa.id, NUEVA)
        espera = time.monotonic() - inicio
    finally:
        soltar.set()
        hilo.join(30)
    assert (response.status_code, error_code(response)) == (503, "servicio_no_disponible")
    assert response.headers.get("Retry-After")
    assert LOCK_TIMEOUT_SEGUNDOS - 1 <= espera < LOCK_TIMEOUT_SEGUNDOS + 10
    assert _estado(edicion_db, empresa.id) == estado


def test_a_race_with_the_admin_edit_leaves_the_row_consistent(client, headers, edicion_db):
    """R43, A21b: la consola espera a que el admin (013) suelte la fila; la última escritura
    gana y ``tenant.nombre`` queda igual al nombre de la ficha."""
    empresa = _empresa(client, headers)
    tomado, soltar = threading.Event(), threading.Event()

    def admin_edita() -> None:
        # Como ``app.empresa.service.guardar``: bloquea la fila y cambia la ficha.
        with edicion_db.migrator.connect() as conn:
            tx = conn.begin()
            conn.execute(
                text("select 1 from empresa where tenant_id = :t for update"), {"t": empresa.id}
            )
            conn.execute(
                text(
                    "update empresa set nombre = 'Nombre del admin', telefono = '3110000000', "
                    "actualizada_en = now() where tenant_id = :t"
                ),
                {"t": empresa.id},
            )
            tomado.set()
            soltar.wait(30)
            tx.commit()

    hilo = threading.Thread(target=admin_edita)
    hilo.start()
    try:
        assert tomado.wait(10)
        threading.Timer(1.0, soltar.set).start()
        response = _put(client, headers, empresa.id, NUEVA)
    finally:
        soltar.set()
        hilo.join(30)
    assert response.status_code == 200, response.get_json()
    fila = _fila(edicion_db, empresa.id)
    assert (fila["nombre"], fila["telefono"]) == (NUEVA["nombre"], NUEVA["telefono"])
    assert _tenant(edicion_db, empresa.id)["nombre"] == fila["nombre"]
    assert len(_auditoria(edicion_db, empresa.id)) == 1


def test_a_closed_session_and_its_report_do_not_change(client, headers, edicion_db):
    """013 R3: cada sesión cerrada guarda su copia de la empresa."""
    empresa = _empresa(client, headers)
    admin = _admin_listo(edicion_db, empresa)
    response = client.post(
        "/sesiones",
        json={"nombre": "Inventario edición", "fecha_corte": "2026-11-30"},
        headers=admin,
    )
    assert response.status_code == 201, response.get_json()
    sesion = response.get_json()["sesion"]["id"]
    response = client.post(f"/sesiones/{sesion}/cerrar", headers=admin)
    assert response.status_code == 200, response.get_json()
    informe = client.get(f"/sesiones/{sesion}/informe", headers=admin).get_json()
    copia = filas(
        edicion_db, "select * from sesion_empresa where sesion_id = :s", {"s": uuid.UUID(sesion)}
    )
    assert informe["empresa"]["nombre"] == empresa.nombre

    assert _put(client, headers, empresa.id, NUEVA).status_code == 200
    assert client.get(f"/sesiones/{sesion}/informe", headers=admin).get_json() == informe
    assert (
        filas(
            edicion_db,
            "select * from sesion_empresa where sesion_id = :s",
            {"s": uuid.UUID(sesion)},
        )
        == copia
    )
    # Y el admin ve la ficha nueva en su pantalla Empresa.
    vista = client.get("/empresa", headers=admin).get_json()["empresa"]
    assert {k: vista[k] for k in NUEVA} == NUEVA


# --- Auditoría y logs sin valores (R45, A23) ----------------------------------------------


def test_audit_and_logs_carry_none_of_the_values(client, headers, edicion_db, caplog):
    empresa = _empresa(client, headers)
    caplog.set_level(logging.DEBUG)
    assert _put(client, headers, empresa.id, NUEVA).status_code == 200
    _put(client, headers, empresa.id, {**NUEVA, "correo": "malo"})  # 422
    client.get(_ficha_url(empresa.id), headers=headers)
    valores = [*NUEVA.values(), empresa.nombre, "900123456", "5550199"]
    for fila in _auditoria(edicion_db, empresa.id):
        texto = " ".join(str(v) for v in fila.values())
        for valor in valores:
            assert valor not in texto, valor
    for valor in (*valores, "malo"):
        assert valor not in caplog.text, valor


# --- Acceso (A2, A23, R52) ----------------------------------------------------------------


def test_tenant_tokens_get_401(client, headers, edicion_db):
    empresa = _empresa(client, headers)
    admin = _admin_listo(edicion_db, empresa)
    estado = _estado(edicion_db, empresa.id)
    for auth in (admin, bearer(ADMIN_A, TENANT_A), bearer(ADMIN_A, TENANT_A, rol="contador"), {}):
        for response in (
            client.get(_ficha_url(empresa.id), headers=auth),
            _put(client, auth, empresa.id, NUEVA),
        ):
            assert (response.status_code, error_code(response)) == (401, "no_autenticado")
    assert _estado(edicion_db, empresa.id) == estado


def test_a_deactivated_developer_gets_401(edicion_app, edicion_db):
    client = edicion_app.test_client(use_cookies=False)
    otro = sembrar_dev(edicion_db, nuevo_dev("edicion-baja"))
    auth = plat_bearer(login(client, otro.email).get_json()["access_token"])
    empresa = _empresa(client, auth)
    estado = _estado(edicion_db, empresa.id)
    ejecutar(edicion_db, "update desarrollador set activo = false where id = :d", {"d": otro.id})
    for response in (
        client.get(_ficha_url(empresa.id), headers=auth),
        _put(client, auth, empresa.id, NUEVA),
    ):
        assert (response.status_code, error_code(response)) == (401, "no_autenticado")
    assert _estado(edicion_db, empresa.id) == estado


def test_put_counts_in_plat_accion_before_touching_anything(edicion_db):
    flask_app = make_plat_app(
        edicion_db, rate_limits=dataclasses.replace(HIGH_LIMITS, plat_accion=2)
    )
    try:
        client = flask_app.test_client(use_cookies=False)
        otro = sembrar_dev(edicion_db, nuevo_dev("tope-ficha"))
        auth = plat_bearer(login(client, otro.email).get_json()["access_token"])
        empresa = _empresa(client, auth)  # 1
        assert _put(client, auth, empresa.id, {"x": 1}).status_code == 400  # 2
        estado = _estado(edicion_db, empresa.id)
        response = _put(client, auth, empresa.id, NUEVA)
        assert (response.status_code, error_code(response)) == (429, "demasiadas_solicitudes")
        assert _estado(edicion_db, empresa.id) == estado
    finally:
        dispose(flask_app)


# --- SQL (A4, A5, A23) --------------------------------------------------------------------


def _llamar(engine: Engine, sql: str, params: dict):
    with engine.connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(
                text("select set_config('app.desarrollador_id', :d, true)"), {"d": params["d"]}
            )
            error = None
            try:
                with conn.begin_nested():
                    fila = conn.execute(text(sql), params).one()
            except DBAPIError as exc:
                error, fila = exc, None
            gucs = {
                guc: conn.scalar(text("select current_setting(:g, true)"), {"g": guc})
                for guc in OWNER_GUCS
            }
        finally:
            tx.rollback()
    return fila, error, gucs


def _params(desarrollador, tenant) -> dict:
    return {
        "d": str(desarrollador),
        "t": str(tenant),
        "n": NUEVA["nombre"],
        "di": NUEVA["direccion"],
        "ni": "",
        "te": "",
        "co": "",
    }


def test_functions_reject_an_inactive_or_unknown_developer(client, headers, edicion_db, app_engine):
    empresa = _empresa(client, headers)
    estado = _estado(edicion_db, empresa.id)
    inactivo = sembrar_dev(edicion_db, nuevo_dev("edicion-inactivo"), activo=False)
    for desarrollador in (inactivo.id, uuid.uuid4()):
        for sql in (LEER, ACTUALIZAR):
            fila, error, _ = _llamar(app_engine, sql, _params(desarrollador, empresa.id))
            assert fila is None
            assert error.orig.sqlstate == INSUFFICIENT_PRIVILEGE
            assert "desarrollador_no_autorizado" in str(error.orig)
    assert _estado(edicion_db, empresa.id) == estado


def test_functions_clear_their_gucs(client, headers, edicion_db, app_engine, dev):
    empresa = _empresa(client, headers)
    fila, error, gucs = _llamar(app_engine, LEER, _params(dev.id, empresa.id))
    assert error is None and fila.nombre == empresa.nombre
    assert all(valor in ("", None) for valor in gucs.values()), gucs
    fila, error, gucs = _llamar(app_engine, ACTUALIZAR, _params(dev.id, empresa.id))
    assert error is None and tuple(fila) == (True,)
    assert all(valor in ("", None) for valor in gucs.values()), gucs
    # La prueba revirtió: nada cambió.
    assert _fila(edicion_db, empresa.id)["nombre"] == empresa.nombre


def test_the_app_cannot_update_the_ficha_directly(client, headers, edicion_db, app_engine, dev):
    """Con la GUC de la empresa fijada a mano, el rol de la aplicación no lee ni escribe."""
    empresa = _empresa(client, headers)
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            for guc, valor in (
                ("app.desarrollador_id", str(dev.id)),
                ("app.plat_actor", str(dev.id)),
                ("app.plat_empresa_tenant", str(empresa.id)),
            ):
                conn.execute(text("select set_config(:g, :v, true)"), {"g": guc, "v": valor})
            assert conn.scalar(text("select count(*) from empresa")) == 0
            assert conn.scalar(text("select count(*) from tenant")) == 0
            for sql in ("update tenant set nombre = 'x'", "update empresa set nombre = 'x'"):
                try:
                    with conn.begin_nested():
                        cambiadas = conn.execute(text(sql)).rowcount
                except DBAPIError as exc:
                    assert exc.orig.sqlstate == INSUFFICIENT_PRIVILEGE, sql
                else:
                    assert cambiadas == 0, sql
        finally:
            tx.rollback()
    assert _tenant(edicion_db, empresa.id)["nombre"] == empresa.nombre


def test_a_tenant_session_cannot_call_the_functions(edicion_app, dev):
    with edicion_app.app_context(), tenant_session(TENANT_A) as session:
        with pytest.raises(UnscopedStatementError):
            session.execute(text(LEER), {"d": str(dev.id), "t": str(TENANT_A)})
