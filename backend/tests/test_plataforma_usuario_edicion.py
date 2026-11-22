"""Editar nombre y rol de un usuario desde la consola (spec 017, C1, T13; R47–R52; A24, A25,
A26; CU-13).

Sobre una base temporal migrada a ``head`` (tenants sintéticos A y B de ``acceso_db``) con
la consola habilitada. Cada prueba usa una empresa propia sembrada por el migrador (dos
admins y un contador), así ninguna depende del orden de las demás.

- SQL (rol de la aplicación): ``acceso.plataforma_cambiar_usuario`` rechaza a quien no es
  un desarrollador activo (A5); cambia solo ``usuario.nombre`` y ``membresia.rol`` de esa
  membresía; revoca las familias de refresh de esa membresía solo si cambia el rol;
  idéntico no escribe; rechazos en el orden de R48 (``404`` empresa, ``404`` usuario,
  ``empresa_inactiva``, ``ultimo_admin``) sin cambios; el candado por empresa de R30
  serializa dos degradaciones (visto en ``pg_locks``) y una desactivación con una edición;
  las GUC quedan vacías; ni la aplicación ni el dueño con las GUC pueden escribir otra cosa.
- HTTP: ``PUT /plataforma/empresas/{id}/usuarios/{usuario_id}`` con ``{nombre, rol}``
  exacto (``400`` con otra clave, ``422`` con ``campo``), respuesta ``{id, nombre, rol}``,
  ``usuario_editado`` sin valores y solo con un cambio real, rol efectivo inmediato con el
  acceso vigente (``403`` al admin degradado; el contador promovido entra a lo de admin),
  refresh revocado solo si cambia el rol, ``plat_accion``, ``503`` con el candado tomado,
  ``401`` a los tokens de tenant y a un desarrollador desactivado, logs sin nombres ni
  correos.

Datos sintéticos (``@ejemplo.test``).
"""

import dataclasses
import logging
import secrets
import threading
import time
import unicodedata
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import argon2
import pytest
from acceso_db import (
    ADMIN_A,
    ADMIN_B,
    CONTADOR_A,
    PASSWORD,
    TENANT_A,
    TENANT_B,
    AccesoDb,
    bearer,
    dispose,
    temporary_acceso_db,
)
from flask import Flask
from plataforma_db import (
    CSRF,
    HIGH_LIMITS,
    Dev,
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
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from app.auth.credentials import ARGON2_TEST_PARAMS
from app.auth.http import REFRESH_COOKIE_SECURE_NAME
from app.db import (
    PlataformaFuncionError,
    UsuarioEditado,
    plataforma_cambiar_usuario,
    plataforma_session,
)

HASHER = argon2.PasswordHasher.from_parameters(ARGON2_TEST_PARAMS)
INSUFFICIENT_PRIVILEGE = "42501"
EDITAR = "select * from acceso.plataforma_cambiar_usuario(:d, :t, :u, :n, :r)"
ESTADO = "select * from acceso.plataforma_cambiar_estado_membresia(:d, :t, :u, :a)"
CLAVE_CANDADO = "plataforma_membresia:"
LOCK_TIMEOUT_SEGUNDOS = 5
# Las diecisiete GUC de 0017–0030 y la de 0031.
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
    "app.plat_usuario_edicion",
)
TABLES = (
    "tenant",
    "usuario",
    "membresia",
    "empresa",
    "invitacion",
    "refresh_token",
    "plataforma_auditoria",
)
# Endpoint solo de admin y sin datos previos: un admin recibe 200 y un contador, 403.
SOLO_ADMIN = "/valor-actual"


@pytest.fixture(scope="module")
def ed_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("plat_usr_edicion")


@pytest.fixture(scope="module")
def ed_app(ed_db) -> Iterator[Flask]:
    flask_app = make_plat_app(ed_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(ed_app):
    return ed_app.test_client(use_cookies=False)


@pytest.fixture(scope="module")
def app_engine(ed_db) -> Iterator[Engine]:
    engine = create_engine(ed_db.app_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def dev(ed_db) -> Dev:
    return sembrar_dev(ed_db, nuevo_dev("edicion-usuario"))


@pytest.fixture(scope="module")
def headers(ed_app, dev) -> dict[str, str]:
    response = login(ed_app.test_client(use_cookies=False), dev.email)
    assert response.status_code == 200
    return plat_bearer(response.get_json()["access_token"])


# --- Empresa propia de cada prueba ---------------------------------------------------------


@dataclass(frozen=True)
class Persona:
    usuario_id: uuid.UUID
    email: str
    nombre: str
    rol: str


@dataclass(frozen=True)
class Empresa:
    tenant_id: uuid.UUID
    admin: Persona
    admin2: Persona
    contador: Persona


def _persona(rol: str) -> Persona:
    sufijo = uuid.uuid4().hex[:10]
    return Persona(uuid.uuid4(), f"{rol}.{sufijo}@ejemplo.test", f"Persona {sufijo}", rol)


def _empresa(db: AccesoDb, *, activa: bool = True) -> Empresa:
    empresa = Empresa(uuid.uuid4(), _persona("admin"), _persona("admin"), _persona("contador"))
    with db.migrator.begin() as conn:
        conn.execute(
            text("insert into tenant (id, nombre) values (:t, :n)"),
            {"t": empresa.tenant_id, "n": f"Clínica Edición {uuid.uuid4().hex[:6]}"},
        )
        for persona in (empresa.admin, empresa.admin2, empresa.contador):
            conn.execute(
                text(
                    "insert into usuario (id, email, nombre, password_hash) values (:u, :e, :n, :h)"
                ),
                {
                    "u": persona.usuario_id,
                    "e": persona.email,
                    "n": persona.nombre,
                    "h": HASHER.hash(PASSWORD),
                },
            )
            conn.execute(
                text("insert into membresia (tenant_id, usuario_id, rol) values (:t, :u, :r)"),
                {"t": empresa.tenant_id, "u": persona.usuario_id, "r": persona.rol},
            )
        if not activa:
            conn.execute(
                text("update tenant set activo = false, desactivado_en = now() where id = :t"),
                {"t": empresa.tenant_id},
            )
    return empresa


def _membresias(db: AccesoDb) -> list[tuple]:
    return sorted(
        (str(r["tenant_id"]), str(r["usuario_id"]), r["rol"], r["activa"])
        for r in filas(db, "select tenant_id, usuario_id, rol, activa from membresia")
    )


def _rol(db: AccesoDb, tenant_id, usuario_id) -> str:
    (row,) = filas(
        db,
        "select rol from membresia where tenant_id = :t and usuario_id = :u",
        {"t": tenant_id, "u": usuario_id},
    )
    return row["rol"]


def _usuario(db: AccesoDb, usuario_id) -> dict:
    (row,) = filas(db, "select * from usuario where id = :u", {"u": usuario_id})
    return row


def _usuarios(db: AccesoDb) -> list[dict]:
    return filas(db, "select * from usuario order by id")


def _counts(db: AccesoDb) -> dict[str, int]:
    with db.migrator.connect() as conn:
        return {t: conn.scalar(text(f"select count(*) from {t}")) for t in TABLES}  # noqa: S608


def _auditoria(db: AccesoDb, tenant_id) -> list[dict]:
    return filas(
        db,
        "select desarrollador_id, accion, resultado, tenant_id, objeto_id "
        "from plataforma_auditoria where tenant_id = :t order by creado_en, id",
        {"t": tenant_id},
    )


def _estado(db: AccesoDb) -> tuple:
    """Todo lo que una edición rechazada no debe tocar."""
    return (
        _membresias(db),
        _usuarios(db),
        _counts(db),
        filas(db, "select id, revocado_en from refresh_token order by id"),
    )


def _sembrar_refresh(db: AccesoDb, tenant_id, usuario_id) -> None:
    with db.migrator.begin() as conn:
        membresia = conn.scalar(
            text("select id from membresia where tenant_id = :t and usuario_id = :u"),
            {"t": tenant_id, "u": usuario_id},
        )
        for _ in range(2):
            conn.execute(
                text(
                    "insert into refresh_token (tenant_id, membresia_id, familia_id, token_hash, "
                    "expira_en) values (:t, :m, :f, :h, :e)"
                ),
                {
                    "t": tenant_id,
                    "m": membresia,
                    "f": uuid.uuid4(),
                    "h": secrets.token_bytes(32),
                    "e": datetime.now(UTC) + timedelta(days=7),
                },
            )


def _refresh_tokens(db: AccesoDb, tenant_id) -> dict[str, bool]:
    """usuario_id -> si todas sus familias de refresh en ``tenant_id`` están revocadas."""
    rows = filas(
        db,
        "select m.usuario_id, bool_and(r.revocado_en is not null) as revocado "
        "from refresh_token r join membresia m on m.id = r.membresia_id "
        "where r.tenant_id = :t group by m.usuario_id",
        {"t": tenant_id},
    )
    return {str(row["usuario_id"]): row["revocado"] for row in rows}


def _sin_refresh_vivo(db: AccesoDb, tenant_id, usuario_id) -> bool:
    (row,) = filas(
        db,
        "select count(*) as n from refresh_token r join membresia m on m.id = r.membresia_id "
        "where r.tenant_id = :t and m.usuario_id = :u and r.revocado_en is null",
        {"t": tenant_id, "u": usuario_id},
    )
    return row["n"] == 0


def _tenant_login(client, email: str, password: str = PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def _cookie(response) -> str:
    for header in response.headers.getlist("Set-Cookie"):
        name, _, rest = header.partition("=")
        if name == REFRESH_COOKIE_SECURE_NAME:
            return rest.split(";", 1)[0]
    raise AssertionError("sin cookie de refresh")


def _refresh(client, cookie: str):
    return client.post(
        "/auth/refresh", headers={**CSRF, "Cookie": f"{REFRESH_COOKIE_SECURE_NAME}={cookie}"}
    )


def _ruta(tenant_id, usuario_id) -> str:
    return f"/plataforma/empresas/{tenant_id}/usuarios/{usuario_id}"


def _put(client, headers, tenant_id, usuario_id, nombre, rol):
    return client.put(
        _ruta(tenant_id, usuario_id), json={"nombre": nombre, "rol": rol}, headers=headers
    )


def _expect_error(conn: Connection, sql: str, params: dict, sqlstate: str) -> str:
    nested = conn.begin_nested()
    with pytest.raises(DBAPIError) as excinfo:
        conn.execute(text(sql), params)
    nested.rollback()
    assert getattr(excinfo.value.orig, "sqlstate", None) == sqlstate, str(excinfo.value.orig)
    return str(excinfo.value.orig)


def _fail_app(app_engine: Engine, sql: str, params: dict, sqlstate: str) -> str:
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            return _expect_error(conn, sql, params, sqlstate)
        finally:
            tx.rollback()


def _gucs_empty(conn: Connection) -> bool:
    return all(
        conn.scalar(text("select current_setting(:g, true)"), {"g": guc}) in (None, "")
        for guc in OWNER_GUCS
    )


def _params(dev: Dev, tenant_id, persona: Persona, nombre=None, rol=None) -> dict:
    return {
        "d": str(dev.id),
        "t": str(tenant_id),
        "u": str(persona.usuario_id),
        "n": persona.nombre if nombre is None else nombre,
        "r": persona.rol if rol is None else rol,
    }


# --- SQL: A5 / R36 ------------------------------------------------------------------------


@pytest.mark.parametrize("caso", ["inexistente", "inactivo", "usuario_de_clinica"])
def test_the_function_rejects_a_caller_that_is_not_an_active_developer(ed_db, app_engine, caso):
    if caso == "inexistente":
        caller = uuid.uuid4()
    elif caso == "inactivo":
        caller = sembrar_dev(ed_db, nuevo_dev("inactivo"), activo=False).id
    else:
        caller = ADMIN_A.usuario_id  # un admin de clínica no es desarrollador
    empresa = _empresa(ed_db)
    before = _estado(ed_db)
    params = {
        "d": str(caller),
        "t": str(empresa.tenant_id),
        "u": str(empresa.admin.usuario_id),
        "n": "Intruso",
        "r": "contador",
    }
    message = _fail_app(app_engine, EDITAR, params, INSUFFICIENT_PRIVILEGE)
    assert "desarrollador_no_autorizado" in message
    assert str(caller) not in message
    assert empresa.admin.email not in message
    assert _estado(ed_db) == before


def test_inside_a_tenant_session_an_admin_cannot_use_the_function(ed_db, app_engine):
    before = _estado(ed_db)
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(TENANT_A)})
            params = {
                "d": str(ADMIN_A.usuario_id),
                "t": str(TENANT_A),
                "u": str(CONTADOR_A.usuario_id),
                "n": "Intruso",
                "r": "admin",
            }
            _expect_error(conn, EDITAR, params, INSUFFICIENT_PRIVILEGE)
        finally:
            tx.rollback()
    assert _estado(ed_db) == before


# --- SQL: cambios (R47, R49, R50) ---------------------------------------------------------


def test_a_name_change_touches_only_usuario_nombre_and_revokes_nothing(ed_db, app_engine, dev):
    empresa = _empresa(ed_db)
    _sembrar_refresh(ed_db, empresa.tenant_id, empresa.contador.usuario_id)
    antes = _usuario(ed_db, empresa.contador.usuario_id)
    membresias = _membresias(ed_db)
    tenants = filas(ed_db, "select * from tenant order by id")
    with app_engine.connect() as conn:
        tx = conn.begin()
        result = conn.execute(
            text(EDITAR), _params(dev, empresa.tenant_id, empresa.contador, "Nuevo")
        )
        assert list(result.keys()) == ["nombre", "rol", "cambiado", "rol_cambiado"]
        assert tuple(result.one()) == ("Nuevo", "contador", True, False)
        assert _gucs_empty(conn)
        tx.commit()
    despues = _usuario(ed_db, empresa.contador.usuario_id)
    assert despues == {**antes, "nombre": "Nuevo"}
    assert _membresias(ed_db) == membresias
    assert filas(ed_db, "select * from tenant order by id") == tenants
    assert _refresh_tokens(ed_db, empresa.tenant_id) == {str(empresa.contador.usuario_id): False}


def test_a_role_change_touches_only_that_membership_and_revokes_only_its_families(
    ed_db, app_engine, dev
):
    empresa = _empresa(ed_db)
    otra = _empresa(ed_db)
    for persona in (empresa.contador, empresa.admin):
        _sembrar_refresh(ed_db, empresa.tenant_id, persona.usuario_id)
    _sembrar_refresh(ed_db, otra.tenant_id, otra.contador.usuario_id)
    before = _membresias(ed_db)
    usuarios = _usuarios(ed_db)
    with app_engine.connect() as conn:
        tx = conn.begin()
        row = conn.execute(
            text(EDITAR), _params(dev, empresa.tenant_id, empresa.contador, rol="admin")
        ).one()
        assert tuple(row) == (empresa.contador.nombre, "admin", True, True)
        assert _gucs_empty(conn)
        tx.commit()
    tenant, contador = str(empresa.tenant_id), str(empresa.contador.usuario_id)
    assert sorted(set(before) ^ set(_membresias(ed_db))) == sorted(
        [(tenant, contador, "contador", True), (tenant, contador, "admin", True)]
    )
    assert _usuarios(ed_db) == usuarios  # ni nombre, correo, hash ni marcas
    assert _refresh_tokens(ed_db, empresa.tenant_id) == {
        contador: True,
        str(empresa.admin.usuario_id): False,
    }
    assert _refresh_tokens(ed_db, otra.tenant_id) == {str(otra.contador.usuario_id): False}


def test_identical_values_write_nothing(ed_db, app_engine, dev):
    empresa = _empresa(ed_db)
    _sembrar_refresh(ed_db, empresa.tenant_id, empresa.admin.usuario_id)
    before = _estado(ed_db)
    xmin = filas(
        ed_db,
        "select (select xmin::text from usuario where id = :u) as u, "
        "(select xmin::text from membresia where usuario_id = :u) as m",
        {"u": empresa.admin.usuario_id},
    )
    with app_engine.connect() as conn:
        tx = conn.begin()
        row = conn.execute(text(EDITAR), _params(dev, empresa.tenant_id, empresa.admin)).one()
        assert tuple(row) == (empresa.admin.nombre, "admin", False, False)
        assert _gucs_empty(conn)
        tx.commit()
    assert _estado(ed_db) == before
    assert (
        filas(
            ed_db,
            "select (select xmin::text from usuario where id = :u) as u, "
            "(select xmin::text from membresia where usuario_id = :u) as m",
            {"u": empresa.admin.usuario_id},
        )
        == xmin
    )


def test_rejections_follow_the_r48_order_change_nothing_and_clear_the_gucs(ed_db, app_engine, dev):
    empresa = _empresa(ed_db)
    inactiva = _empresa(ed_db, activa=False)
    otra = _empresa(ed_db)
    # Un solo admin activo en «empresa»: degradarlo es ultimo_admin.
    ejecutar(
        ed_db,
        "update membresia set activa = false where usuario_id = :u",
        {"u": empresa.admin2.usuario_id},
    )
    ejecutar(
        ed_db,
        "update membresia set activa = false where usuario_id = :u",
        {"u": inactiva.admin2.usuario_id},
    )
    before = _estado(ed_db)
    casos = (
        # (tenant, persona, rol, sqlstate, código)
        (uuid.uuid4(), otra.contador, "admin", "P0002", "empresa_no_encontrada"),
        (empresa.tenant_id, otra.contador, "admin", "P0002", "usuario_no_encontrado"),
        (
            empresa.tenant_id,
            Persona(uuid.uuid4(), "", "X", "admin"),
            "admin",
            "P0002",
            "usuario_no_encontrado",
        ),
        (
            TENANT_B,
            Persona(CONTADOR_A.usuario_id, "", "X", "contador"),
            "contador",
            "P0002",
            "usuario_no_encontrado",
        ),
        # Empresa inactiva antes que usuario ajeno no: el usuario ajeno es 404 primero.
        (inactiva.tenant_id, otra.contador, "admin", "P0002", "usuario_no_encontrado"),
        # Empresa inactiva antes que ultimo_admin (y en los dos sentidos).
        (inactiva.tenant_id, inactiva.admin, "contador", "P0001", "empresa_inactiva"),
        (inactiva.tenant_id, inactiva.contador, "admin", "P0001", "empresa_inactiva"),
        (empresa.tenant_id, empresa.admin, "contador", "P0001", "ultimo_admin"),
    )
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            for tenant, persona, rol, sqlstate, codigo in casos:
                params = _params(dev, tenant, persona, nombre="Otro nombre", rol=rol)
                assert codigo in _expect_error(conn, EDITAR, params, sqlstate), codigo
                assert _gucs_empty(conn), codigo
        finally:
            tx.rollback()
    assert _estado(ed_db) == before


def test_ultimo_admin_counts_only_active_admins_of_that_company(ed_db, app_engine, dev):
    empresa = _empresa(ed_db)
    base = {"d": str(dev.id), "t": str(empresa.tenant_id)}

    def editar(persona: Persona, rol: str) -> tuple:
        with app_engine.begin() as conn:
            return tuple(
                conn.execute(
                    text(EDITAR),
                    {**base, "u": str(persona.usuario_id), "n": persona.nombre, "r": rol},
                ).one()
            )

    # Con otro admin activo se degrada; luego el que queda es el último.
    assert editar(empresa.admin2, "contador") == (empresa.admin2.nombre, "contador", True, True)
    before = _membresias(ed_db)
    message = _fail_app(
        app_engine, EDITAR, _params(dev, empresa.tenant_id, empresa.admin, rol="contador"), "P0001"
    )
    assert "ultimo_admin" in message
    assert _membresias(ed_db) == before
    # El último admin sí puede cambiar su nombre sin cambiar su rol.
    assert editar(Persona(empresa.admin.usuario_id, "", "Renombrado", "admin"), "admin") == (
        "Renombrado",
        "admin",
        True,
        False,
    )
    # Promover al contador permite degradar al primero.
    assert editar(empresa.contador, "admin")[3] is True
    assert editar(empresa.admin, "contador")[1] == "contador"
    assert _rol(ed_db, empresa.tenant_id, empresa.admin.usuario_id) == "contador"
    # Un admin de otra empresa no cuenta.
    solo = _empresa(ed_db)
    ejecutar(
        ed_db,
        "update membresia set activa = false where usuario_id = :u",
        {"u": solo.admin2.usuario_id},
    )
    assert "ultimo_admin" in _fail_app(
        app_engine, EDITAR, _params(dev, solo.tenant_id, solo.admin, rol="contador"), "P0001"
    )


def test_an_inactive_membership_is_editable_and_does_not_count_as_admin(ed_db, app_engine, dev):
    # R51: con la membresía desactivada se editan su nombre y su rol; degradar a un admin
    # inactivo no es ultimo_admin aunque el otro sea el único activo.
    empresa = _empresa(ed_db)
    ejecutar(
        ed_db,
        "update membresia set activa = false where usuario_id = :u",
        {"u": empresa.admin2.usuario_id},
    )
    _sembrar_refresh(ed_db, empresa.tenant_id, empresa.admin2.usuario_id)
    with app_engine.begin() as conn:
        row = conn.execute(
            text(EDITAR),
            _params(dev, empresa.tenant_id, empresa.admin2, nombre="Inactiva", rol="contador"),
        ).one()
    assert tuple(row) == ("Inactiva", "contador", True, True)
    (fila,) = filas(
        ed_db,
        "select rol, activa from membresia where usuario_id = :u",
        {"u": empresa.admin2.usuario_id},
    )
    assert (fila["rol"], fila["activa"]) == ("contador", False)
    assert _usuario(ed_db, empresa.admin2.usuario_id)["nombre"] == "Inactiva"
    assert _sin_refresh_vivo(ed_db, empresa.tenant_id, empresa.admin2.usuario_id)
    # Y vuelve a admin (sigue inactiva).
    with app_engine.begin() as conn:
        assert conn.execute(
            text(EDITAR), _params(dev, empresa.tenant_id, empresa.admin2, "Inactiva", "admin")
        ).one()[3]


def test_two_overlapping_demotions_of_the_two_admins_leave_one_admin(ed_db, app_engine, dev):
    # A25: la primera degrada un admin y no confirma; la segunda (el otro admin) espera el
    # candado consultivo de la empresa (visto en pg_locks); al confirmar la primera, la
    # segunda ve que es el último admin y da ultimo_admin sin cambiar nada.
    empresa = _empresa(ed_db)
    resultado: dict[str, object] = {}

    def espera(pid: int) -> bool:
        (row,) = filas(
            ed_db,
            "select exists(select 1 from pg_locks where pid = :p and not granted "
            "and locktype = 'advisory') as e",
            {"p": pid},
        )
        return row["e"]

    with app_engine.connect() as segunda:
        pid = segunda.scalar(text("select pg_backend_pid()"))
        segunda.commit()

        def degradar_segunda() -> None:
            try:
                with segunda.begin():
                    segunda.execute(text("set local lock_timeout = '30s'"))
                    resultado["ok"] = tuple(
                        segunda.execute(
                            text(EDITAR),
                            _params(dev, empresa.tenant_id, empresa.admin2, rol="contador"),
                        ).one()
                    )
            except DBAPIError as exc:
                resultado["error"] = (exc.orig.sqlstate, exc.orig.diag.message_primary)

        with app_engine.connect() as primera:
            primera.begin()
            primera.execute(
                text(EDITAR), _params(dev, empresa.tenant_id, empresa.admin, rol="contador")
            ).one()
            hilo = threading.Thread(target=degradar_segunda)
            hilo.start()
            limite = time.monotonic() + 20
            while not espera(pid):
                assert hilo.is_alive() and time.monotonic() < limite, resultado
                time.sleep(0.05)
            assert hilo.is_alive()
            primera.commit()
        hilo.join(timeout=30)
        assert not hilo.is_alive()

    assert resultado == {"error": ("P0001", "ultimo_admin")}
    assert _rol(ed_db, empresa.tenant_id, empresa.admin.usuario_id) == "contador"
    assert _rol(ed_db, empresa.tenant_id, empresa.admin2.usuario_id) == "admin"


def test_deactivating_and_changing_the_role_at_once_leave_no_live_family(ed_db, app_engine, dev):
    # A25: desactivar y editar a la vez se serializan con el mismo candado; al terminar,
    # la membresía inactiva no tiene ninguna familia viva.
    empresa = _empresa(ed_db)
    persona = empresa.contador
    _sembrar_refresh(ed_db, empresa.tenant_id, persona.usuario_id)
    resultado: dict[str, object] = {}

    with app_engine.connect() as segunda:
        pid = segunda.scalar(text("select pg_backend_pid()"))
        segunda.commit()

        def desactivar() -> None:
            with segunda.begin():
                segunda.execute(text("set local lock_timeout = '30s'"))
                resultado["estado"] = tuple(
                    segunda.execute(
                        text(ESTADO),
                        {
                            "d": str(dev.id),
                            "t": str(empresa.tenant_id),
                            "u": str(persona.usuario_id),
                            "a": False,
                        },
                    ).one()
                )

        with app_engine.connect() as primera:
            primera.begin()
            primera.execute(
                text(EDITAR), _params(dev, empresa.tenant_id, persona, rol="admin")
            ).one()
            hilo = threading.Thread(target=desactivar)
            hilo.start()
            limite = time.monotonic() + 20
            while not filas(
                ed_db,
                "select exists(select 1 from pg_locks where pid = :p and not granted) as e",
                {"p": pid},
            )[0]["e"]:
                assert hilo.is_alive() and time.monotonic() < limite
                time.sleep(0.05)
            # Mientras la edición no confirma, entra un refresh nuevo para esa membresía.
            _sembrar_refresh(ed_db, empresa.tenant_id, persona.usuario_id)
            primera.commit()
        hilo.join(timeout=30)
        assert not hilo.is_alive()

    assert resultado == {"estado": (False, True)}
    (fila,) = filas(
        ed_db, "select rol, activa from membresia where usuario_id = :u", {"u": persona.usuario_id}
    )
    assert (fila["rol"], fila["activa"]) == ("admin", False)
    assert _sin_refresh_vivo(ed_db, empresa.tenant_id, persona.usuario_id)


def test_the_app_role_cannot_edit_users_directly_even_with_the_gucs(ed_db, app_engine, dev):
    empresa = _empresa(ed_db)
    before = _estado(ed_db)
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            for guc, value in (
                ("app.desarrollador_id", dev.id),
                ("app.plat_actor", dev.id),
                ("app.plat_membresia_tenant", empresa.tenant_id),
                ("app.plat_membresia_usuario", empresa.admin.usuario_id),
                ("app.plat_usuario_edicion", empresa.admin.usuario_id),
            ):
                conn.execute(text("select set_config(:g, :v, true)"), {"g": guc, "v": str(value)})
            for sql in (
                "update usuario set nombre = 'X'",
                "update membresia set rol = 'contador'",
                "select count(*) from usuario",
                "select count(*) from membresia",
            ):
                nested = conn.begin_nested()
                try:
                    result = conn.execute(text(sql))
                except DBAPIError as exc:
                    nested.rollback()
                    assert exc.orig.sqlstate == INSUFFICIENT_PRIVILEGE, sql
                    continue
                if sql.startswith("select"):
                    assert result.scalar_one() == 0, sql
                else:
                    assert result.rowcount == 0, sql
                nested.commit()
        finally:
            tx.rollback()
    assert _estado(ed_db) == before


def _owner_update(conn: Connection, gucs: dict, sql: str, params: dict) -> int | str:
    """Como ``plataforma_owner`` con ``gucs``: filas cambiadas o el SQLSTATE del error."""
    nested = conn.begin_nested()
    try:
        for guc, value in gucs.items():
            conn.execute(text("select set_config(:g, :v, true)"), {"g": guc, "v": str(value)})
        try:
            return conn.execute(text(sql), params).rowcount
        except DBAPIError as exc:
            return exc.orig.sqlstate
    finally:
        nested.rollback()


def test_owner_policies_open_only_the_target_user_and_never_email_nor_hash(ed_db, dev):
    """Lo que la RLS y los privilegios por columna del dueño abren en 0031 (RC10: lo que
    no acota la RLS lo acota la huella de los cuerpos, test_plataforma_catalogo.py)."""
    empresa = _empresa(ed_db)
    otra = _empresa(ed_db)
    actor = {"app.plat_actor": dev.id}
    propia = {
        **actor,
        "app.plat_membresia_tenant": empresa.tenant_id,
        "app.plat_membresia_usuario": empresa.contador.usuario_id,
        "app.plat_usuario_edicion": empresa.contador.usuario_id,
    }
    renombrar = "update usuario set nombre = 'X' where id = :u"
    before = _estado(ed_db)
    with ed_db.migrator.connect() as conn:
        tx = conn.begin()
        try:
            conn.exec_driver_sql("SET LOCAL ROLE plataforma_owner")
            u = {"u": empresa.contador.usuario_id}
            # Con sus tres GUC, solo el usuario objetivo.
            assert _owner_update(conn, propia, renombrar, u) == 1
            # Sin la GUC de 0031 (solo las de 0027), o con la de otro usuario: cero filas.
            sin_edicion = {k: v for k, v in propia.items() if k != "app.plat_usuario_edicion"}
            assert _owner_update(conn, sin_edicion, renombrar, u) == 0
            assert (
                _owner_update(
                    conn,
                    {**propia, "app.plat_usuario_edicion": empresa.admin.usuario_id},
                    renombrar,
                    u,
                )
                == 0
            )
            # Un usuario de otra empresa con la GUC del usuario pero la empresa equivocada.
            ajeno = {**propia, "app.plat_usuario_edicion": otra.contador.usuario_id}
            assert _owner_update(conn, ajeno, renombrar, {"u": otra.contador.usuario_id}) == 0
            # Sin desarrollador activo: cero filas.
            inactivo = sembrar_dev(ed_db, nuevo_dev("dueno-inactivo"), activo=False)
            assert _owner_update(conn, {**propia, "app.plat_actor": inactivo.id}, renombrar, u) == 0
            # Nunca correo ni activo (el dueño no tiene esos privilegios).
            for columna in ("email = 'x@ejemplo.test'", "activo = false"):
                sql = f"update usuario set {columna} where id = :u"  # noqa: S608
                assert _owner_update(conn, propia, sql, u) == INSUFFICIENT_PRIVILEGE, columna
            # RC10 (C1b/T16, 0032): el dueño tiene ya UPDATE de password_hash,
            # debe_cambiar_password y sesiones_validas_desde (la contraseña temporal) y esa
            # concesión por columna ensancha también esta política: con las GUC de 0031 la
            # RLS no lo impide. Lo contiene la huella de los cuerpos y la aserción que fija
            # qué columnas de usuario escribe cada función (en test_plataforma_catalogo.py,
            # test_only_cambiar_usuario_renames_a_user_or_changes_a_role); sin las GUC de
            # 0031 (solo las de 0027), cero filas.
            for columna in (
                "password_hash = 'h'",
                "debe_cambiar_password = true",
                "sesiones_validas_desde = now()",
            ):
                sql = f"update usuario set {columna} where id = :u"  # noqa: S608
                assert _owner_update(conn, propia, sql, u) == 1, columna
                assert _owner_update(conn, sin_edicion, sql, u) == 0, columna
            # Y nunca leer el hash.
            assert (
                _owner_update(conn, propia, "select password_hash from usuario where id = :u", u)
                == INSUFFICIENT_PRIVILEGE
            )
            # membresia: solo rol y activa de la membresía objetivo; nunca tenant ni usuario.
            assert (
                _owner_update(
                    conn, propia, "update membresia set rol = 'admin' where usuario_id = :u", u
                )
                == 1
            )
            assert (
                _owner_update(
                    conn,
                    propia,
                    "update membresia set rol = 'admin' where usuario_id = :u",
                    {"u": empresa.admin2.usuario_id},
                )
                == 0
            )
            for columna in ("tenant_id = :t", "usuario_id = :t"):
                sql = f"update membresia set {columna} where usuario_id = :u"  # noqa: S608
                assert (
                    _owner_update(conn, propia, sql, {**u, "t": otra.tenant_id})
                    == INSUFFICIENT_PRIVILEGE
                ), columna
            for sql in (
                "delete from usuario where id = :u",
                "delete from membresia where usuario_id = :u",
            ):
                assert _owner_update(conn, propia, sql, u) == INSUFFICIENT_PRIVILEGE, sql
        finally:
            tx.rollback()
    assert _estado(ed_db)[:3] == before[:3]


def test_db_helper_uses_the_developer_of_the_session(ed_app, ed_db, dev):
    empresa = _empresa(ed_db)
    with ed_app.app_context():
        with plataforma_session(dev.id) as session:
            editado = plataforma_cambiar_usuario(
                session, empresa.tenant_id, empresa.contador.usuario_id, "Nombre Sesión", "admin"
            )
            assert editado == UsuarioEditado(
                nombre="Nombre Sesión", rol="admin", cambiado=True, rol_cambiado=True
            )
            assert "Nombre Sesión" not in repr(editado)
            repetido = plataforma_cambiar_usuario(
                session, empresa.tenant_id, empresa.contador.usuario_id, "Nombre Sesión", "admin"
            )
            assert (repetido.cambiado, repetido.rol_cambiado) == (False, False)
        inactivo = sembrar_dev(ed_db, nuevo_dev("inactivo-db"), activo=False)
        with pytest.raises(PlataformaFuncionError) as excinfo:
            with plataforma_session(inactivo.id) as session:
                plataforma_cambiar_usuario(
                    session, empresa.tenant_id, empresa.contador.usuario_id, "X", "contador"
                )
        assert excinfo.value.codigo == "desarrollador_no_autorizado"
    assert _rol(ed_db, empresa.tenant_id, empresa.contador.usuario_id) == "admin"


# --- HTTP (R47–R52; A24, A25) --------------------------------------------------------------


def test_a_name_change_answers_the_result_audits_and_keeps_the_sessions(
    client, headers, ed_db, dev
):
    empresa = _empresa(ed_db)
    persona = empresa.contador
    sesion = _tenant_login(client, persona.email)
    assert sesion.status_code == 200
    token = {"Authorization": f"Bearer {sesion.get_json()['access_token']}"}
    cookie = _cookie(sesion)
    antes = _usuario(ed_db, persona.usuario_id)

    response = _put(
        client, headers, empresa.tenant_id, persona.usuario_id, "Nombre Nuevo", "contador"
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json() == {
        "id": str(persona.usuario_id),
        "nombre": "Nombre Nuevo",
        "rol": "contador",
    }
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    # Solo el nombre: correo, hash y marcas intactos; la sesión sigue viva.
    assert _usuario(ed_db, persona.usuario_id) == {**antes, "nombre": "Nombre Nuevo"}
    assert client.get("/auth/me", headers=token).status_code == 200
    assert _refresh(client, cookie).status_code == 200
    assert _auditoria(ed_db, empresa.tenant_id) == [
        {
            "desarrollador_id": dev.id,
            "accion": "usuario_editado",
            "resultado": "ok",
            "tenant_id": empresa.tenant_id,
            "objeto_id": persona.usuario_id,
        }
    ]


def test_demoting_an_admin_revokes_its_refresh_and_its_live_token_gets_403(client, headers, ed_db):
    empresa = _empresa(ed_db)
    persona = empresa.admin2
    sesion = _tenant_login(client, persona.email)
    token = {"Authorization": f"Bearer {sesion.get_json()['access_token']}"}
    cookie = _cookie(sesion)
    otro = _tenant_login(client, empresa.admin.email)
    otro_cookie = _cookie(otro)
    assert client.get(SOLO_ADMIN, headers=token).status_code == 200
    hash_antes = _usuario(ed_db, persona.usuario_id)["password_hash"]

    response = _put(
        client, headers, empresa.tenant_id, persona.usuario_id, persona.nombre, "contador"
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["rol"] == "contador"
    # Rol efectivo inmediato con el acceso vigente; el refresh de esa membresía, revocado.
    negado = client.get(SOLO_ADMIN, headers=token)
    assert negado.status_code == 403
    assert _refresh(client, cookie).status_code == 401
    # El otro admin sigue dentro; la persona vuelve a entrar con el rol nuevo.
    assert _refresh(client, otro_cookie).status_code == 200
    nueva = _tenant_login(client, persona.email)
    assert nueva.status_code == 200
    nuevo_token = {"Authorization": f"Bearer {nueva.get_json()['access_token']}"}
    assert client.get(SOLO_ADMIN, headers=nuevo_token).status_code == 403
    # El cambio de rol no toca la contraseña ni el cambio pendiente.
    usuario = _usuario(ed_db, persona.usuario_id)
    assert usuario["password_hash"] == hash_antes
    assert usuario["debe_cambiar_password"] is False


def test_promoting_a_contador_gives_admin_access_with_the_live_token(client, headers, ed_db):
    empresa = _empresa(ed_db)
    persona = empresa.contador
    sesion = _tenant_login(client, persona.email)
    token = {"Authorization": f"Bearer {sesion.get_json()['access_token']}"}
    assert client.get(SOLO_ADMIN, headers=token).status_code == 403
    response = _put(client, headers, empresa.tenant_id, persona.usuario_id, persona.nombre, "admin")
    assert response.status_code == 200
    assert client.get(SOLO_ADMIN, headers=token).status_code == 200
    assert _rol(ed_db, empresa.tenant_id, persona.usuario_id) == "admin"


def test_identical_put_is_200_without_audit_nor_revocation(client, headers, ed_db):
    empresa = _empresa(ed_db)
    persona = empresa.admin
    sesion = _tenant_login(client, persona.email)
    cookie = _cookie(sesion)
    before = (_membresias(ed_db), _usuarios(ed_db))
    for _ in range(2):
        response = _put(
            client, headers, empresa.tenant_id, persona.usuario_id, persona.nombre, "admin"
        )
        assert response.status_code == 200
        assert response.get_json() == {
            "id": str(persona.usuario_id),
            "nombre": persona.nombre,
            "rol": "admin",
        }
    # El nombre se normaliza antes de comparar: con espacios es el mismo.
    response = _put(
        client, headers, empresa.tenant_id, persona.usuario_id, f"  {persona.nombre} ", "admin"
    )
    assert response.status_code == 200
    assert (_membresias(ed_db), _usuarios(ed_db)) == before
    assert _auditoria(ed_db, empresa.tenant_id) == []
    assert _refresh(client, cookie).status_code == 200


def test_the_name_is_normalized_like_usuario_nombre(client, headers, ed_db):
    empresa = _empresa(ed_db)
    descompuesto = unicodedata.normalize("NFD", "  José Peña  ")
    response = _put(
        client, headers, empresa.tenant_id, empresa.contador.usuario_id, descompuesto, "contador"
    )
    assert response.status_code == 200
    assert response.get_json()["nombre"] == "José Peña"
    assert _usuario(ed_db, empresa.contador.usuario_id)["nombre"] == "José Peña"


def test_last_admin_is_409_without_changes_nor_audit(client, headers, ed_db):
    empresa = _empresa(ed_db)
    assert (
        _put(client, headers, empresa.tenant_id, empresa.admin2.usuario_id, "Dos", "contador")
    ).status_code == 200
    auditoria_antes = _auditoria(ed_db, empresa.tenant_id)
    sesion = _tenant_login(client, empresa.admin.email)
    cookie = _cookie(sesion)
    before = (_membresias(ed_db), _usuarios(ed_db))
    response = _put(
        client, headers, empresa.tenant_id, empresa.admin.usuario_id, "Otro nombre", "contador"
    )
    assert response.status_code == 409
    assert error_code(response) == "ultimo_admin"
    assert response.get_json()["error"]["message"] == (
        "No se puede quitar el rol admin al último admin activo de la empresa."
    )
    # Ni el nombre (que también venía) ni el rol, ni auditoría, ni revocación.
    assert (_membresias(ed_db), _usuarios(ed_db)) == before
    assert _auditoria(ed_db, empresa.tenant_id) == auditoria_antes
    assert _refresh(client, cookie).status_code == 200


def test_inactive_company_is_409_without_changes(client, headers, ed_db):
    empresa = _empresa(ed_db, activa=False)
    before = _estado(ed_db)
    for persona, nombre, rol in (
        (empresa.contador, "Otro", "contador"),
        (empresa.contador, empresa.contador.nombre, "admin"),
        (empresa.admin, empresa.admin.nombre, "contador"),
    ):
        response = _put(client, headers, empresa.tenant_id, persona.usuario_id, nombre, rol)
        assert response.status_code == 409
        assert error_code(response) == "empresa_inactiva"
    assert _estado(ed_db) == before


def test_foreign_or_unknown_ids_are_a_generic_404(client, headers, ed_db):
    empresa = _empresa(ed_db)
    otra = _empresa(ed_db)
    inactiva = _empresa(ed_db, activa=False)
    before = _estado(ed_db)
    for tenant, usuario, mensaje in (
        (empresa.tenant_id, otra.contador.usuario_id, "Ese usuario no pertenece a esta empresa."),
        (TENANT_A, ADMIN_B.usuario_id, "Ese usuario no pertenece a esta empresa."),
        (empresa.tenant_id, uuid.uuid4(), "Ese usuario no pertenece a esta empresa."),
        # 404 de usuario antes que empresa_inactiva.
        (inactiva.tenant_id, otra.contador.usuario_id, "Ese usuario no pertenece a esta empresa."),
        (uuid.uuid4(), empresa.contador.usuario_id, "La empresa no existe."),
    ):
        response = _put(client, headers, tenant, usuario, "Intruso", "admin")
        assert response.status_code == 404, (tenant, usuario)
        assert error_code(response) == "no_encontrado"
        assert response.get_json()["error"]["message"] == mensaje
        assert otra.contador.email not in response.get_data(as_text=True)
    assert _estado(ed_db) == before


def test_a_user_with_another_membership_gets_a_global_name_and_a_local_role(client, headers, ed_db):
    # R51: el nombre es del usuario (global); el rol, solo de esta membresía.
    empresa = _empresa(ed_db)
    otra = _empresa(ed_db)
    persona = empresa.contador
    ejecutar(
        ed_db,
        "insert into membresia (tenant_id, usuario_id, rol, activa) "
        "values (:t, :u, 'contador', false)",
        {"t": otra.tenant_id, "u": persona.usuario_id},
    )
    response = _put(client, headers, empresa.tenant_id, persona.usuario_id, "Global", "admin")
    assert response.status_code == 200
    assert _usuario(ed_db, persona.usuario_id)["nombre"] == "Global"
    assert _rol(ed_db, empresa.tenant_id, persona.usuario_id) == "admin"
    assert _rol(ed_db, otra.tenant_id, persona.usuario_id) == "contador"
    # Desde la otra empresa también se edita (la membresía desactivada).
    response = _put(client, headers, otra.tenant_id, persona.usuario_id, "Global", "admin")
    assert response.status_code == 200
    assert _rol(ed_db, otra.tenant_id, persona.usuario_id) == "admin"


def test_tenant_b_is_untouched(client, headers, ed_db):
    empresa = _empresa(ed_db)
    tenant_b = (
        filas(ed_db, "select * from membresia where tenant_id = :t order by id", {"t": TENANT_B}),
        filas(ed_db, "select * from tenant where id = :t", {"t": TENANT_B}),
        _usuario(ed_db, ADMIN_B.usuario_id),
    )
    for rol in ("admin", "contador"):
        response = _put(client, headers, empresa.tenant_id, empresa.contador.usuario_id, "Uno", rol)
        assert response.status_code == 200
    assert (
        filas(ed_db, "select * from membresia where tenant_id = :t order by id", {"t": TENANT_B}),
        filas(ed_db, "select * from tenant where id = :t", {"t": TENANT_B}),
        _usuario(ed_db, ADMIN_B.usuario_id),
    ) == tenant_b
    assert _tenant_login(client, ADMIN_B.email).status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {},
        {"nombre": "Uno"},
        {"rol": "admin"},
        {"nombre": "Uno", "rol": "admin", "email": "otro@ejemplo.test"},
        {"nombre": "Uno", "rol": "admin", "password": "Clave-Nueva-Sintetica-2026"},
        {"nombre": "Uno", "rol": "admin", "activa": False},
        {"nombre": "Uno", "rol": "admin", "tenant_id": str(TENANT_B)},
        {"nombre": "Uno", "rol": "admin", "debe_cambiar_password": True},
    ],
)
def test_the_body_is_exactly_nombre_and_rol(client, headers, ed_db, body):
    empresa = _empresa(ed_db)
    before = _estado(ed_db)
    ruta = _ruta(empresa.tenant_id, empresa.contador.usuario_id)
    if body is None:
        response = client.put(ruta, data="no-json", headers=headers)
    else:
        response = client.put(ruta, json=body, headers=headers)
    assert response.status_code == 400
    assert error_code(response) == "solicitud_invalida"
    assert _estado(ed_db) == before


@pytest.mark.parametrize(
    ("nombre", "rol", "campo"),
    [
        ("", "admin", "nombre"),
        ("   ", "admin", "nombre"),
        ("x" * 121, "admin", "nombre"),
        ("Uno‮dos", "admin", "nombre"),
        ("---", "admin", "nombre"),
        (None, "admin", "nombre"),
        (7, "admin", "nombre"),
        ("Uno", "owner", "rol"),
        ("Uno", "Admin", "rol"),
        ("Uno", "desarrollador", "rol"),
        ("Uno", None, "rol"),
        ("Uno", 1, "rol"),
    ],
)
def test_invalid_values_are_422_with_campo_and_change_nothing(
    client, headers, ed_db, nombre, rol, campo
):
    empresa = _empresa(ed_db)
    before = _estado(ed_db)
    response = _put(client, headers, empresa.tenant_id, empresa.contador.usuario_id, nombre, rol)
    assert response.status_code == 422
    assert error_code(response) == "campo_invalido"
    assert response.get_json()["error"]["campo"] == campo
    assert _estado(ed_db) == before


def test_a_120_character_name_is_accepted(client, headers, ed_db):
    empresa = _empresa(ed_db)
    nombre = "n" * 120
    response = _put(
        client, headers, empresa.tenant_id, empresa.contador.usuario_id, nombre, "contador"
    )
    assert response.status_code == 200
    assert _usuario(ed_db, empresa.contador.usuario_id)["nombre"] == nombre


def test_tenant_tokens_get_401_with_a_valid_body(client, ed_db):
    empresa = _empresa(ed_db)
    before = _estado(ed_db)
    for tenant, usuario in (
        (empresa.tenant_id, empresa.contador.usuario_id),
        (TENANT_A, CONTADOR_A.usuario_id),
        (TENANT_B, ADMIN_B.usuario_id),
    ):
        for name, extra in (
            ("anonimo", {}),
            ("admin", bearer(ADMIN_A, TENANT_A, rol="admin")),
            ("contador", bearer(CONTADOR_A, TENANT_A, rol="contador")),
            ("admin_b", bearer(ADMIN_B, TENANT_B, rol="admin")),
        ):
            response = _put(client, extra, tenant, usuario, "Intruso", "admin")
            assert response.status_code == 401, (name, tenant)
            assert error_code(response) == "no_autenticado"
    assert _estado(ed_db) == before


def test_a_developer_deactivated_after_login_gets_401(ed_app, ed_db):
    client = ed_app.test_client(use_cookies=False)
    otro = sembrar_dev(ed_db, nuevo_dev("baja-edicion"))
    auth = plat_bearer(login(client, otro.email).get_json()["access_token"])
    empresa = _empresa(ed_db)
    ejecutar(ed_db, "update desarrollador set activo = false where id = :d", {"d": otro.id})
    before = _estado(ed_db)
    response = _put(client, auth, empresa.tenant_id, empresa.contador.usuario_id, "X", "admin")
    assert response.status_code == 401
    assert error_code(response) == "no_autenticado"
    assert _estado(ed_db) == before


def test_put_counts_in_plat_accion_before_touching_the_database(ed_db):
    flask_app = make_plat_app(ed_db, rate_limits=dataclasses.replace(HIGH_LIMITS, plat_accion=2))
    try:
        client = flask_app.test_client(use_cookies=False)
        otro = sembrar_dev(ed_db, nuevo_dev("tope-edicion"))
        auth = plat_bearer(login(client, otro.email).get_json()["access_token"])
        empresa = _empresa(ed_db)
        persona = empresa.contador
        # Un cuerpo inválido también cuenta (el tope va antes de validar).
        assert (
            client.put(
                _ruta(empresa.tenant_id, persona.usuario_id), json={}, headers=auth
            ).status_code
            == 400
        )
        assert (
            _put(client, auth, empresa.tenant_id, persona.usuario_id, "Uno", "contador").status_code
            == 200
        )
        before = _estado(ed_db)
        response = _put(client, auth, empresa.tenant_id, persona.usuario_id, "Dos", "admin")
        assert response.status_code == 429
        assert error_code(response) == "demasiadas_solicitudes"
        assert _estado(ed_db) == before
    finally:
        dispose(flask_app)


def test_a_busy_membership_lock_fails_with_503_without_changes(client, headers, ed_db):
    empresa = _empresa(ed_db)
    _sembrar_refresh(ed_db, empresa.tenant_id, empresa.admin2.usuario_id)
    before = _estado(ed_db)
    with ed_db.migrator.connect() as conn:
        tx = conn.begin()
        conn.execute(
            text("select pg_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": f"{CLAVE_CANDADO}{empresa.tenant_id}"},
        )
        resultado: dict = {}

        def editar() -> None:
            inicio = time.monotonic()
            resultado["r"] = _put(
                client, headers, empresa.tenant_id, empresa.admin2.usuario_id, "Ocupado", "contador"
            )
            resultado["espera"] = time.monotonic() - inicio

        hilo = threading.Thread(target=editar)
        hilo.start()
        hilo.join(timeout=LOCK_TIMEOUT_SEGUNDOS + 10)
        vivo = hilo.is_alive()
        tx.rollback()
        hilo.join(timeout=30)
    assert not vivo, "la función no aplicó su lock_timeout"
    response, espera = resultado["r"], resultado["espera"]
    assert response.status_code == 503, response.get_json()
    assert error_code(response) == "servicio_no_disponible"
    assert response.headers["Retry-After"].isdigit()
    assert LOCK_TIMEOUT_SEGUNDOS - 0.5 <= espera < LOCK_TIMEOUT_SEGUNDOS + 10
    assert _estado(ed_db) == before
    assert _auditoria(ed_db, empresa.tenant_id) == []


def _error_db(sqlstate: str) -> DBAPIError:
    from psycopg import errors as pg_errors

    clase = {"40P01": pg_errors.DeadlockDetected, "40001": pg_errors.SerializationFailure}
    return DBAPIError("select 1", {}, clase[sqlstate]("detalle-interno-de-la-base"))


@pytest.mark.parametrize("sqlstate", ["40P01", "40001"])
def test_a_deadlock_or_serialization_failure_is_503(client, headers, ed_db, monkeypatch, sqlstate):
    from app.plataforma.modulos.usuarios import service

    empresa = _empresa(ed_db)
    before = _estado(ed_db)

    def falla(*args, **kwargs):
        raise _error_db(sqlstate)

    monkeypatch.setattr(service, "plataforma_cambiar_usuario", falla)
    response = _put(client, headers, empresa.tenant_id, empresa.contador.usuario_id, "X", "admin")
    assert response.status_code == 503
    assert error_code(response) == "servicio_no_disponible"
    assert "detalle-interno" not in response.get_data(as_text=True)
    assert _estado(ed_db) == before


def test_audit_failure_rolls_back_the_edit(client, headers, ed_db, monkeypatch):
    from app.plataforma import auditoria

    empresa = _empresa(ed_db)
    _sembrar_refresh(ed_db, empresa.tenant_id, empresa.contador.usuario_id)
    before = _estado(ed_db)

    def falla(*args, **kwargs):
        raise RuntimeError("auditoría caída (sintético)")

    monkeypatch.setattr(auditoria, "registrar", falla)
    response = _put(client, headers, empresa.tenant_id, empresa.contador.usuario_id, "X", "admin")
    assert response.status_code == 500
    assert _estado(ed_db) == before


def test_audit_rows_carry_only_ids(client, headers, ed_db, dev):
    empresa = _empresa(ed_db)
    persona = empresa.contador
    for nombre, rol in (
        ("Uno", "contador"),
        ("Uno", "admin"),
        ("Uno", "admin"),
        ("Dos", "contador"),
    ):
        assert (
            _put(client, headers, empresa.tenant_id, persona.usuario_id, nombre, rol).status_code
            == 200
        )
    rows = filas(
        ed_db,
        "select * from plataforma_auditoria where tenant_id = :t order by creado_en, id",
        {"t": empresa.tenant_id},
    )
    assert {k for r in rows for k in r} == {
        "id",
        "creado_en",
        "desarrollador_id",
        "accion",
        "resultado",
        "tenant_id",
        "objeto_id",
    }
    # Tres cambios reales (nombre, rol, ambos) y uno repetido: tres filas iguales.
    assert [{k: v for k, v in r.items() if k not in ("id", "creado_en")} for r in rows] == [
        {
            "desarrollador_id": dev.id,
            "accion": "usuario_editado",
            "resultado": "ok",
            "tenant_id": empresa.tenant_id,
            "objeto_id": persona.usuario_id,
        }
    ] * 3


def test_logs_never_carry_names_nor_emails(client, headers, ed_db, caplog):
    empresa = _empresa(ed_db)
    caplog.set_level(logging.DEBUG)
    nuevo = f"Centinela {uuid.uuid4().hex[:8]}"
    _put(client, headers, empresa.tenant_id, empresa.contador.usuario_id, nuevo, "admin")
    _put(
        client,
        headers,
        empresa.tenant_id,
        empresa.admin.usuario_id,
        empresa.admin.nombre,
        "contador",
    )
    _put(client, headers, empresa.tenant_id, empresa.admin2.usuario_id, nuevo, "contador")
    # Degradar al último admin activo (el contador promovido): 409.
    _put(client, headers, empresa.tenant_id, empresa.contador.usuario_id, nuevo, "contador")
    _put(client, headers, empresa.tenant_id, empresa.contador.usuario_id, "", "contador")  # 422
    texto = caplog.text
    for persona in (empresa.admin, empresa.admin2, empresa.contador):
        assert persona.email not in texto
        assert persona.nombre not in texto
    assert nuevo not in texto
    assert "argon2" not in texto
