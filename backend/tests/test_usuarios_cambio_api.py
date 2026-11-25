"""API ``PUT /usuarios/{usuario_id}`` (0033): cambiar rol y activar o desactivar (solo admin).

- Cambia la membresía de la empresa de la sesión; no toca nombre, correo ni contraseña.
- Desactivar revoca los refresh de esa membresía y su acceso vigente deja de valer
  (``401``); cambiar el rol se aplica en la siguiente petición (``403`` para un admin
  degradado).
- Nunca se cambia el propio rol ni se desactiva uno mismo (``409``).
- Una persona de otra empresa da ``404`` y no cambia nada (RLS y la función).
- Cuerpo exacto ``{rol, activa}``; cualquier otra clave o valor da ``400``.
- Sin cambios responde ``200`` sin escribir ni revocar.
"""

from collections.abc import Iterator

import pytest
from acceso_db import (
    ADMIN_A,
    CAMBIANTE_A,
    CONTADOR_A,
    CONTADOR_B,
    TENANT_A,
    TENANT_B,
    AccesoDb,
    bearer,
    dispose,
    make_app,
    migrator_execute,
    temporary_acceso_db,
)
from flask import Flask
from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.pool import NullPool

ADMIN = bearer(ADMIN_A, TENANT_A)
CONTADOR = bearer(CONTADOR_A, TENANT_A, rol="contador")
CAMBIANTE = bearer(CAMBIANTE_A, TENANT_A, rol="admin")
CSRF = {"X-AssetControl-CSRF": "1"}


@pytest.fixture(scope="module")
def cambio_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("usuarios_cambio")


@pytest.fixture(scope="module")
def cambio_app(cambio_db) -> Iterator[Flask]:
    flask_app = make_app(cambio_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(cambio_app):
    return cambio_app.test_client(use_cookies=False)


@pytest.fixture(autouse=True)
def membresias_originales(cambio_db):
    """Cada prueba parte de las membresías del seed y las deja así al terminar."""
    estado = _estado_membresias(cambio_db)
    _borrar_auditoria(cambio_db)
    yield
    for usuario_id, (rol, activa) in estado.items():
        migrator_execute(
            cambio_db,
            "UPDATE membresia SET rol = :r, activa = :a WHERE usuario_id = :u",
            {"r": rol, "a": activa, "u": usuario_id},
        )
    _borrar_refresh(cambio_db)
    _borrar_auditoria(cambio_db)


def _estado_membresias(db: AccesoDb) -> dict:
    with db.migrator.connect() as conn:
        filas = conn.execute(
            text("select usuario_id, rol, activa from membresia where tenant_id = :t"),
            {"t": TENANT_A},
        ).all()
    return {fila.usuario_id: (fila.rol, fila.activa) for fila in filas}


def _put(client, cuenta, cuerpo, headers=ADMIN):
    return client.put(f"/usuarios/{cuenta.usuario_id}", json=cuerpo, headers={**headers, **CSRF})


def _insertar_refresh(db: AccesoDb, cuenta) -> None:
    migrator_execute(
        db,
        "insert into refresh_token (tenant_id, membresia_id, familia_id, token_hash, expira_en) "
        "select m.tenant_id, m.id, gen_random_uuid(), "
        "decode(md5(random()::text) || md5(random()::text), 'hex'), now() + interval '1 day' "
        "from membresia m where m.usuario_id = :u",
        {"u": cuenta.usuario_id},
    )


def _refresh_vivos(db: AccesoDb, cuenta) -> int:
    with db.migrator.connect() as conn:
        return conn.execute(
            text(
                "select count(*) from refresh_token r join membresia m on m.id = r.membresia_id "
                "where m.usuario_id = :u and r.revocado_en is null"
            ),
            {"u": cuenta.usuario_id},
        ).scalar_one()


def _borrar_refresh(db: AccesoDb) -> None:
    migrator_execute(db, "delete from refresh_token")


def _membresia(db: AccesoDb, cuenta, tenant=TENANT_A) -> tuple[str, bool]:
    with db.migrator.connect() as conn:
        fila = conn.execute(
            text("select rol, activa from membresia where usuario_id = :u and tenant_id = :t"),
            {"u": cuenta.usuario_id, "t": tenant},
        ).one()
    return fila.rol, fila.activa


def test_admin_cambia_el_rol_y_responde_el_estado(cambio_db, client):
    respuesta = _put(client, CONTADOR_A, {"rol": "admin", "activa": True})
    assert respuesta.status_code == 200
    assert respuesta.get_json() == {
        "id": str(CONTADOR_A.usuario_id),
        "rol": "admin",
        "activa": True,
    }
    assert _membresia(cambio_db, CONTADOR_A) == ("admin", True)


def test_desactivar_revoca_refresh_y_el_acceso_vigente_cae(cambio_db, client):
    _insertar_refresh(cambio_db, CONTADOR_A)
    assert _refresh_vivos(cambio_db, CONTADOR_A) == 1

    respuesta = _put(client, CONTADOR_A, {"rol": "contador", "activa": False})
    assert respuesta.status_code == 200
    assert respuesta.get_json()["activa"] is False
    assert _refresh_vivos(cambio_db, CONTADOR_A) == 0

    # El JWT de la persona sigue sin caducar, pero la membresía inactiva corta la petición.
    assert client.get("/auth/me", headers=CONTADOR).status_code == 401


def test_reactivar_devuelve_el_acceso(cambio_db, client):
    _put(client, CONTADOR_A, {"rol": "contador", "activa": False})
    respuesta = _put(client, CONTADOR_A, {"rol": "contador", "activa": True})
    assert respuesta.status_code == 200
    assert client.get("/auth/me", headers=CONTADOR).status_code == 200


def test_cambio_de_rol_se_aplica_en_la_siguiente_peticion(cambio_db, client):
    # CAMBIANTE_A es admin en la base; su token dice admin, pero el rol sale de la base.
    assert client.get("/usuarios", headers=CAMBIANTE).status_code == 200
    _insertar_refresh(cambio_db, CAMBIANTE_A)

    respuesta = _put(client, CAMBIANTE_A, {"rol": "contador", "activa": True})
    assert respuesta.status_code == 200
    assert _refresh_vivos(cambio_db, CAMBIANTE_A) == 0
    assert client.get("/usuarios", headers=CAMBIANTE).status_code == 403


def test_no_se_cambia_el_propio_rol_ni_se_desactiva_uno_mismo(cambio_db, client):
    antes = _membresia(cambio_db, ADMIN_A)

    for cuerpo in ({"rol": "contador", "activa": True}, {"rol": "admin", "activa": False}):
        respuesta = _put(client, ADMIN_A, cuerpo)
        assert respuesta.status_code == 409
        assert respuesta.get_json()["error"]["code"] == "cambio_propio_no_permitido"
    assert _membresia(cambio_db, ADMIN_A) == antes


def test_contador_recibe_403_y_no_cambia_nada(cambio_db, client):
    antes = _membresia(cambio_db, CAMBIANTE_A)
    assert (
        _put(client, CAMBIANTE_A, {"rol": "contador", "activa": False}, CONTADOR).status_code == 403
    )
    assert _membresia(cambio_db, CAMBIANTE_A) == antes


def test_sin_sesion_recibe_401(cambio_db, client):
    respuesta = client.put(
        f"/usuarios/{CAMBIANTE_A.usuario_id}",
        json={"rol": "contador", "activa": False},
        headers=CSRF,
    )
    assert respuesta.status_code == 401


def test_persona_de_otra_empresa_da_404_sin_cambios(cambio_db, client):
    antes = _membresia(cambio_db, CONTADOR_B, TENANT_B)
    respuesta = client.put(
        f"/usuarios/{CONTADOR_B.usuario_id}",
        json={"rol": "admin", "activa": False},
        headers={**ADMIN, **CSRF},
    )
    assert respuesta.status_code == 404
    assert respuesta.get_json()["error"]["code"] == "no_encontrado"
    assert _membresia(cambio_db, CONTADOR_B, TENANT_B) == antes


@pytest.mark.parametrize(
    "cuerpo",
    [
        {},
        {"rol": "admin"},
        {"activa": True},
        {"rol": "admin", "activa": True, "nombre": "Otro"},
        {"rol": "superusuario", "activa": True},
        {"rol": "admin", "activa": "si"},
        {"rol": None, "activa": True},
    ],
)
def test_cuerpo_invalido_da_400(client, cuerpo):
    assert _put(client, CAMBIANTE_A, cuerpo).status_code == 400


def test_sin_cambios_responde_200_sin_revocar(cambio_db, client):
    _insertar_refresh(cambio_db, CONTADOR_A)
    respuesta = _put(client, CONTADOR_A, {"rol": "contador", "activa": True})
    assert respuesta.status_code == 200
    assert respuesta.get_json()["rol"] == "contador"
    assert _refresh_vivos(cambio_db, CONTADOR_A) == 1


# --- Auditoría de cambios (0034) ----------------------------------------------------------


def _borrar_auditoria(db: AccesoDb) -> None:
    # Solo el migrador (dueño de la tabla) puede borrar: es para limpiar entre pruebas.
    migrator_execute(db, "delete from membresia_auditoria")


def _auditoria(db: AccesoDb, tenant=TENANT_A) -> list[tuple]:
    """Filas de auditoría que ve la aplicación en ``tenant`` (lectura con RLS, no migrador)."""
    engine = create_engine(db.app_url, poolclass=NullPool)
    try:
        with engine.begin() as conn:
            conn.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})
            filas = conn.execute(
                text(
                    "select actor_usuario_id, usuario_id, accion, rol_anterior, rol_nuevo "
                    "from membresia_auditoria order by creado_en, accion"
                )
            ).all()
    finally:
        engine.dispose()
    return [tuple(fila) for fila in filas]


def test_cambio_de_rol_queda_en_la_auditoria(cambio_db, client):
    rol_antes, _ = _membresia(cambio_db, CONTADOR_A)
    assert rol_antes == "contador"

    assert _put(client, CONTADOR_A, {"rol": "admin", "activa": True}).status_code == 200

    assert _auditoria(cambio_db) == [
        (ADMIN_A.usuario_id, CONTADOR_A.usuario_id, "rol_cambiado", "contador", "admin")
    ]


def test_desactivar_queda_en_la_auditoria_sin_roles(cambio_db, client):
    assert _put(client, CONTADOR_A, {"rol": "contador", "activa": False}).status_code == 200

    assert _auditoria(cambio_db) == [
        (ADMIN_A.usuario_id, CONTADOR_A.usuario_id, "usuario_desactivado", None, None)
    ]


def test_reactivar_queda_en_la_auditoria(cambio_db, client):
    _put(client, CONTADOR_A, {"rol": "contador", "activa": False})
    assert _put(client, CONTADOR_A, {"rol": "contador", "activa": True}).status_code == 200

    assert _auditoria(cambio_db) == [
        (ADMIN_A.usuario_id, CONTADOR_A.usuario_id, "usuario_desactivado", None, None),
        (ADMIN_A.usuario_id, CONTADOR_A.usuario_id, "usuario_reactivado", None, None),
    ]


def test_rol_y_activacion_en_una_peticion_dan_dos_filas(cambio_db, client):
    assert _put(client, CONTADOR_A, {"rol": "admin", "activa": False}).status_code == 200

    assert sorted(_auditoria(cambio_db)) == sorted(
        [
            (ADMIN_A.usuario_id, CONTADOR_A.usuario_id, "rol_cambiado", "contador", "admin"),
            (ADMIN_A.usuario_id, CONTADOR_A.usuario_id, "usuario_desactivado", None, None),
        ]
    )


def test_cambio_que_no_hace_nada_no_escribe_auditoria(cambio_db, client):
    assert _put(client, CONTADOR_A, {"rol": "contador", "activa": True}).status_code == 200
    assert _auditoria(cambio_db) == []


@pytest.mark.parametrize(
    "cuerpo, cuenta, headers",
    [
        ({"rol": "contador", "activa": True}, ADMIN_A, ADMIN),  # propio: 409
        ({"rol": "admin", "activa": False}, ADMIN_A, ADMIN),  # propio: 409
        ({"rol": "admin", "activa": True, "nombre": "x"}, CONTADOR_A, ADMIN),  # cuerpo: 400
        ({"rol": "admin", "activa": True}, CONTADOR_A, CONTADOR),  # sin permiso: 403
    ],
)
def test_intento_rechazado_no_deja_filas(cambio_db, client, cuerpo, cuenta, headers):
    respuesta = _put(client, cuenta, cuerpo, headers=headers)
    assert respuesta.status_code in (400, 403, 409)
    assert _auditoria(cambio_db) == []


def test_persona_de_otra_empresa_no_deja_filas(cambio_db, client):
    respuesta = client.put(
        f"/usuarios/{CONTADOR_B.usuario_id}",
        json={"rol": "admin", "activa": False},
        headers={**ADMIN, **CSRF},
    )
    assert respuesta.status_code == 404
    assert _auditoria(cambio_db, TENANT_B) == []
    assert _auditoria(cambio_db, TENANT_A) == []


def test_auditoria_de_una_empresa_no_aparece_en_otra(cambio_db, client):
    assert _put(client, CONTADOR_A, {"rol": "admin", "activa": False}).status_code == 200

    assert len(_auditoria(cambio_db, TENANT_A)) == 2
    assert _auditoria(cambio_db, TENANT_B) == []


def test_la_app_no_puede_modificar_ni_borrar_la_auditoria(cambio_db, client):
    assert _put(client, CONTADOR_A, {"rol": "contador", "activa": False}).status_code == 200
    engine = create_engine(cambio_db.app_url, poolclass=NullPool)
    try:
        for sql in (
            "update membresia_auditoria set accion = 'usuario_reactivado'",
            "delete from membresia_auditoria",
            "insert into membresia_auditoria (tenant_id, actor_usuario_id, usuario_id, accion) "
            "values (current_setting('app.tenant_id')::uuid, gen_random_uuid(), "
            "gen_random_uuid(), 'usuario_desactivado')",
        ):
            with engine.begin() as conn:
                conn.execute(
                    text("select set_config('app.tenant_id', :t, true)"),
                    {"t": str(TENANT_A)},
                )
                with pytest.raises(ProgrammingError) as excinfo:
                    conn.execute(text(sql))
                assert excinfo.value.orig.sqlstate == "42501", sql
    finally:
        engine.dispose()
    # Ninguna de las tres sentencias cambió ni borró la fila de la auditoría.
    assert [fila[2] for fila in _auditoria(cambio_db)] == ["usuario_desactivado"]
