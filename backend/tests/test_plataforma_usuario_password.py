"""Contraseña temporal de un usuario desde la consola (spec 017, C1b, T16; R53–R60; A27,
A28, A29; RC7–RC9; CU-14).

Sobre una base temporal migrada a ``head`` (tenants sintéticos A y B de ``acceso_db``) con
la consola habilitada. Cada prueba usa una empresa propia sembrada por el migrador (dos
admins y un contador), así ninguna depende del orden de las demás.

- SQL (rol de la aplicación): ``acceso.plataforma_restablecer_password_usuario`` rechaza a
  quien no es un desarrollador activo (A5) y dentro de una ``tenant_session`` (A6); valida
  el formato del hash; cambia solo ``password_hash``, ``debe_cambiar_password`` y
  ``sesiones_validas_desde`` de ese usuario y revoca **todas** sus familias de refresh, en
  todas sus empresas; rechazos en el orden de R55 sin cambios; toma el candado de cada
  empresa del usuario (dos definiciones, o una con una desactivación, se serializan); las
  GUC quedan vacías; ni la aplicación ni el dueño con las GUC pueden escribir otra cosa ni
  leer el hash.
- HTTP: ``POST /plataforma/empresas/{id}/usuarios/{usuario_id}/contrasena`` con
  ``{password, password_confirmacion}`` exacto (``400`` con otra clave, ``422`` con
  ``campo``), ``204`` sin cuerpo, efecto sobre la persona (login anterior ``401``, la
  temporal entra y queda bloqueada con ``403 cambio_password_requerido`` en todo el
  ``url_map`` salvo la lista de R26, token y refresh anteriores ``401``, tras cambiarla entra
  a lo de admin), la recuperación de la 014 sobre una temporal pendiente, el único admin,
  la membresía desactivada y el usuario de dos empresas, ``usuario_contrasena_restablecida``
  sin valores en cada llamada, ``plat_accion``, ``503`` con un candado tomado, ``401`` a los
  tokens de tenant y a un desarrollador desactivado; ni la contraseña, ni la confirmación,
  ni el hash en la respuesta, la auditoría o los logs.

Datos sintéticos (``@ejemplo.test``).
"""

import dataclasses
import hashlib
import logging
import re
import secrets
import threading
import time
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
from app.auth.decorators import PASSWORD_CHANGE_ENDPOINTS
from app.auth.http import REFRESH_COOKIE_SECURE_NAME
from app.db import (
    PlataformaFuncionError,
    plataforma_restablecer_password_usuario,
    plataforma_session,
)

HASHER = argon2.PasswordHasher.from_parameters(ARGON2_TEST_PARAMS)
INSUFFICIENT_PRIVILEGE = "42501"
RESTABLECER = "select acceso.plataforma_restablecer_password_usuario(:d, :t, :u, :h)"
ESTADO = "select * from acceso.plataforma_cambiar_estado_membresia(:d, :t, :u, :a)"
CLAVE_CANDADO = "plataforma_membresia:"
LOCK_TIMEOUT_SEGUNDOS = 5
TEMPORAL = "Temporal-Sintetica-2026"
OTRA_TEMPORAL = "Otra-Temporal-Sintetica-2026"
DEFINITIVA = "Definitiva-Sintetica-2026"
BLOQUEO = "cambio_password_requerido"
# Las dieciocho GUC de 0017–0031 y la de 0032.
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
    "app.plat_usuario_password",
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
def pw_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("plat_usr_password")


@pytest.fixture(scope="module")
def pw_app(pw_db) -> Iterator[Flask]:
    flask_app = make_plat_app(pw_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(pw_app):
    return pw_app.test_client(use_cookies=False)


@pytest.fixture(scope="module")
def app_engine(pw_db) -> Iterator[Engine]:
    engine = create_engine(pw_db.app_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def dev(pw_db) -> Dev:
    return sembrar_dev(pw_db, nuevo_dev("password-usuario"))


@pytest.fixture(scope="module")
def headers(pw_app, dev) -> dict[str, str]:
    response = login(pw_app.test_client(use_cookies=False), dev.email)
    assert response.status_code == 200
    return plat_bearer(response.get_json()["access_token"])


@pytest.fixture(autouse=True)
def fresh_rate_limits(pw_db) -> Iterator[None]:
    with pw_db.migrator.begin() as conn:
        conn.execute(text("delete from limite_tasa"))
    yield


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
            {"t": empresa.tenant_id, "n": f"Clínica Contraseña {uuid.uuid4().hex[:6]}"},
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


def _otra_membresia(db: AccesoDb, tenant_id, persona: Persona, *, activa: bool) -> None:
    ejecutar(
        db,
        "insert into membresia (tenant_id, usuario_id, rol, activa) "
        "values (:t, :u, 'contador', :a)",
        {"t": tenant_id, "u": persona.usuario_id, "a": activa},
    )


def _membresias(db: AccesoDb) -> list[tuple]:
    return sorted(
        (str(r["tenant_id"]), str(r["usuario_id"]), r["rol"], r["activa"])
        for r in filas(db, "select tenant_id, usuario_id, rol, activa from membresia")
    )


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
    """Todo lo que una definición rechazada no debe tocar."""
    return (
        _membresias(db),
        _usuarios(db),
        _counts(db),
        filas(db, "select id, revocado_en from refresh_token order by id"),
        filas(db, "select * from tenant order by id"),
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


def _vivos(db: AccesoDb, usuario_id) -> int:
    """Refresh sin revocar del usuario, en todas sus empresas."""
    (row,) = filas(
        db,
        "select count(*) as n from refresh_token r join membresia m on m.id = r.membresia_id "
        "where m.usuario_id = :u and r.revocado_en is null",
        {"u": usuario_id},
    )
    return row["n"]


def _tenant_login(client, email: str, password: str = PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def _bearer(response) -> dict[str, str]:
    return {"Authorization": f"Bearer {response.get_json()['access_token']}"}


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
    return f"/plataforma/empresas/{tenant_id}/usuarios/{usuario_id}/contrasena"


def _post(client, headers, tenant_id, usuario_id, password=TEMPORAL, confirmacion=None):
    body = {
        "password": password,
        "password_confirmacion": password if confirmacion is None else confirmacion,
    }
    return client.post(_ruta(tenant_id, usuario_id), json=body, headers=headers)


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


def _params(dev: Dev, tenant_id, persona: Persona, password_hash: str | None = None) -> dict:
    return {
        "d": str(dev.id),
        "t": str(tenant_id),
        "u": str(persona.usuario_id),
        "h": HASHER.hash(TEMPORAL) if password_hash is None else password_hash,
    }


def _verifica(password_hash: str, password: str) -> bool:
    try:
        return HASHER.verify(password_hash, password)
    except argon2.exceptions.VerifyMismatchError:
        return False


# --- SQL: A5 / A6 / R36 -------------------------------------------------------------------


@pytest.mark.parametrize("caso", ["inexistente", "inactivo", "usuario_de_clinica"])
def test_the_function_rejects_a_caller_that_is_not_an_active_developer(pw_db, app_engine, caso):
    if caso == "inexistente":
        caller = uuid.uuid4()
    elif caso == "inactivo":
        caller = sembrar_dev(pw_db, nuevo_dev("inactivo"), activo=False).id
    else:
        caller = ADMIN_A.usuario_id  # un admin de clínica no es desarrollador
    empresa = _empresa(pw_db)
    before = _estado(pw_db)
    params = {**_params(Dev(caller, "", ""), empresa.tenant_id, empresa.admin)}
    message = _fail_app(app_engine, RESTABLECER, params, INSUFFICIENT_PRIVILEGE)
    assert "desarrollador_no_autorizado" in message
    assert str(caller) not in message
    assert params["h"] not in message
    assert _estado(pw_db) == before


def test_inside_a_tenant_session_an_admin_cannot_use_the_function(pw_db, app_engine):
    before = _estado(pw_db)
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(TENANT_A)})
            params = {
                "d": str(ADMIN_A.usuario_id),
                "t": str(TENANT_A),
                "u": str(CONTADOR_A.usuario_id),
                "h": HASHER.hash(TEMPORAL),
            }
            _expect_error(conn, RESTABLECER, params, INSUFFICIENT_PRIVILEGE)
        finally:
            tx.rollback()
    assert _estado(pw_db) == before


# --- SQL: efecto (R54, R56) ---------------------------------------------------------------


def test_it_sets_hash_flag_and_cut_and_revokes_every_family_of_the_user(pw_db, app_engine, dev):
    empresa = _empresa(pw_db)
    otra = _empresa(pw_db)
    persona = empresa.contador
    # Una membresía desactivada en otra empresa (RC8, Q-P3): sus familias también caen.
    _otra_membresia(pw_db, otra.tenant_id, persona, activa=False)
    for tenant in (empresa.tenant_id, otra.tenant_id):
        _sembrar_refresh(pw_db, tenant, persona.usuario_id)
    _sembrar_refresh(pw_db, empresa.tenant_id, empresa.admin.usuario_id)
    _sembrar_refresh(pw_db, otra.tenant_id, otra.contador.usuario_id)
    antes = _usuario(pw_db, persona.usuario_id)
    otros = [u for u in _usuarios(pw_db) if u["id"] != persona.usuario_id]
    membresias = _membresias(pw_db)
    tenants = filas(pw_db, "select * from tenant order by id")
    nuevo = HASHER.hash(TEMPORAL)
    with app_engine.connect() as conn:
        tx = conn.begin()
        result = conn.execute(text(RESTABLECER), _params(dev, empresa.tenant_id, persona, nuevo))
        assert list(result.keys()) == ["plataforma_restablecer_password_usuario"]
        assert result.scalar_one() in (None, "")  # void: nada vuelve (psycopg lo da como '')
        assert _gucs_empty(conn)
        ahora = conn.scalar(text("select now()"))
        tx.commit()
    despues = _usuario(pw_db, persona.usuario_id)
    assert despues == {
        **antes,
        "password_hash": nuevo,
        "debe_cambiar_password": True,
        "sesiones_validas_desde": ahora,
    }
    assert [u for u in _usuarios(pw_db) if u["id"] != persona.usuario_id] == otros
    assert _membresias(pw_db) == membresias
    assert filas(pw_db, "select * from tenant order by id") == tenants
    assert _vivos(pw_db, persona.usuario_id) == 0
    assert _vivos(pw_db, empresa.admin.usuario_id) == 2
    assert _vivos(pw_db, otra.contador.usuario_id) == 2


def test_rejections_follow_the_r55_order_change_nothing_and_clear_the_gucs(pw_db, app_engine, dev):
    empresa = _empresa(pw_db)
    inactiva = _empresa(pw_db, activa=False)
    otra = _empresa(pw_db)
    before = _estado(pw_db)
    casos = (
        # (tenant, persona, sqlstate, código)
        (uuid.uuid4(), otra.contador, "P0002", "empresa_no_encontrada"),
        (empresa.tenant_id, otra.contador, "P0002", "usuario_no_encontrado"),
        (
            empresa.tenant_id,
            Persona(uuid.uuid4(), "", "X", "admin"),
            "P0002",
            "usuario_no_encontrado",
        ),
        (
            TENANT_B,
            Persona(CONTADOR_A.usuario_id, "", "X", "contador"),
            "P0002",
            "usuario_no_encontrado",
        ),
        # El usuario ajeno es 404 antes que empresa_inactiva.
        (inactiva.tenant_id, otra.contador, "P0002", "usuario_no_encontrado"),
        (inactiva.tenant_id, inactiva.admin, "P0001", "empresa_inactiva"),
        (inactiva.tenant_id, inactiva.contador, "P0001", "empresa_inactiva"),
    )
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            for tenant, persona, sqlstate, codigo in casos:
                params = _params(dev, tenant, persona)
                message = _expect_error(conn, RESTABLECER, params, sqlstate)
                assert codigo in message, codigo
                assert params["h"] not in message
                assert _gucs_empty(conn), codigo
        finally:
            tx.rollback()
    assert _estado(pw_db) == before


@pytest.mark.parametrize(
    "password_hash",
    [
        "",
        "x",
        "$argon2i$v=19$m=8,t=1,p=1$c2FsdHNhbHQ$aGFzaGhhc2g",
        "$2b$12$abcdefghijklmnopqrstuuabcdefghijklmnopqrstuvwxyzabcde",
        "$argon2id$v=19$m=8,t=1,p=1$c2FsdHNhbHQ$" + "a" * 300,
        TEMPORAL,  # la contraseña en claro nunca vale como hash
    ],
)
def test_a_malformed_hash_fails_before_writing(pw_db, app_engine, dev, password_hash):
    empresa = _empresa(pw_db)
    before = _estado(pw_db)
    message = _fail_app(
        app_engine,
        RESTABLECER,
        _params(dev, empresa.tenant_id, empresa.contador, password_hash),
        "22023",
    )
    assert "hash_invalido" in message
    assert _estado(pw_db) == before


def _espera_candado(db: AccesoDb, pid: int) -> bool:
    (row,) = filas(
        db,
        "select exists(select 1 from pg_locks where pid = :p and not granted "
        "and locktype = 'advisory') as e",
        {"p": pid},
    )
    return row["e"]


def test_two_overlapping_definitions_serialize_and_leave_no_live_family(pw_db, app_engine, dev):
    # A28: la segunda espera el candado consultivo de la empresa (visto en pg_locks); un
    # refresh emitido mientras la primera no confirma lo revoca la segunda; el hash final es
    # entero (el de la segunda), nunca a medias.
    empresa = _empresa(pw_db)
    persona = empresa.contador
    _sembrar_refresh(pw_db, empresa.tenant_id, persona.usuario_id)
    segundo_hash = HASHER.hash(OTRA_TEMPORAL)
    resultado: dict[str, object] = {}

    with app_engine.connect() as segunda:
        pid = segunda.scalar(text("select pg_backend_pid()"))
        segunda.commit()

        def definir_segunda() -> None:
            try:
                with segunda.begin():
                    segunda.execute(text("set local lock_timeout = '30s'"))
                    segunda.execute(
                        text(RESTABLECER), _params(dev, empresa.tenant_id, persona, segundo_hash)
                    )
                    resultado["ok"] = True
            except DBAPIError as exc:
                resultado["error"] = (exc.orig.sqlstate, exc.orig.diag.message_primary)

        with app_engine.connect() as primera:
            primera.begin()
            primera.execute(text(RESTABLECER), _params(dev, empresa.tenant_id, persona))
            hilo = threading.Thread(target=definir_segunda)
            hilo.start()
            limite = time.monotonic() + 20
            while not _espera_candado(pw_db, pid):
                assert hilo.is_alive() and time.monotonic() < limite, resultado
                time.sleep(0.05)
            _sembrar_refresh(pw_db, empresa.tenant_id, persona.usuario_id)
            primera.commit()
        hilo.join(timeout=30)
        assert not hilo.is_alive()

    assert resultado == {"ok": True}
    usuario = _usuario(pw_db, persona.usuario_id)
    assert usuario["password_hash"] == segundo_hash
    assert _verifica(usuario["password_hash"], OTRA_TEMPORAL)
    assert usuario["debe_cambiar_password"] is True
    assert _vivos(pw_db, persona.usuario_id) == 0


def test_defining_and_deactivating_at_once_leave_no_live_family(pw_db, app_engine, dev):
    # A28: desactivar la membresía y definir la contraseña se serializan con el mismo
    # candado; al terminar no queda ninguna familia viva y la contraseña quedó definida.
    empresa = _empresa(pw_db)
    persona = empresa.contador
    _sembrar_refresh(pw_db, empresa.tenant_id, persona.usuario_id)
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
            primera.execute(text(RESTABLECER), _params(dev, empresa.tenant_id, persona))
            hilo = threading.Thread(target=desactivar)
            hilo.start()
            limite = time.monotonic() + 20
            while not _espera_candado(pw_db, pid):
                assert hilo.is_alive() and time.monotonic() < limite
                time.sleep(0.05)
            _sembrar_refresh(pw_db, empresa.tenant_id, persona.usuario_id)
            primera.commit()
        hilo.join(timeout=30)
        assert not hilo.is_alive()

    assert resultado == {"estado": (False, True)}
    assert _usuario(pw_db, persona.usuario_id)["debe_cambiar_password"] is True
    assert _vivos(pw_db, persona.usuario_id) == 0


def test_a_membership_that_appears_while_waiting_fails_closed(pw_db, app_engine, dev):
    # Bajo los candados se relee el conjunto de empresas del usuario: si cambió (una
    # membresía nueva entró mientras se esperaba), 55P03 sin cambiar nada.
    empresa = _empresa(pw_db)
    nueva = _empresa(pw_db)
    persona = empresa.contador
    resultado: dict[str, object] = {}
    with app_engine.connect() as definir:
        pid = definir.scalar(text("select pg_backend_pid()"))
        definir.commit()

        def correr() -> None:
            try:
                with definir.begin():
                    definir.execute(text("set local lock_timeout = '30s'"))
                    definir.execute(text(RESTABLECER), _params(dev, empresa.tenant_id, persona))
                    resultado["ok"] = True
            except DBAPIError as exc:
                resultado["error"] = (exc.orig.sqlstate, exc.orig.diag.message_primary)

        with pw_db.migrator.connect() as candado:
            tx = candado.begin()
            candado.execute(
                text("select pg_advisory_xact_lock(hashtextextended(:k, 0))"),
                {"k": f"{CLAVE_CANDADO}{empresa.tenant_id}"},
            )
            hilo = threading.Thread(target=correr)
            hilo.start()
            limite = time.monotonic() + 20
            while not _espera_candado(pw_db, pid):
                assert hilo.is_alive() and time.monotonic() < limite
                time.sleep(0.05)
            before = _usuario(pw_db, persona.usuario_id)
            _otra_membresia(pw_db, nueva.tenant_id, persona, activa=False)
            tx.rollback()
        hilo.join(timeout=30)
        assert not hilo.is_alive()
    assert resultado == {"error": ("55P03", "membresia_ocupada")}
    assert _usuario(pw_db, persona.usuario_id) == before


def test_the_app_role_cannot_write_nor_read_the_hash_even_with_the_gucs(pw_db, app_engine, dev):
    empresa = _empresa(pw_db)
    before = _estado(pw_db)
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            for guc, value in (
                ("app.desarrollador_id", dev.id),
                ("app.plat_actor", dev.id),
                ("app.plat_membresia_tenant", empresa.tenant_id),
                ("app.plat_usuario_password", empresa.admin.usuario_id),
            ):
                conn.execute(text("select set_config(:g, :v, true)"), {"g": guc, "v": str(value)})
            for sql in (
                "update usuario set password_hash = 'h'",
                "update usuario set debe_cambiar_password = true",
                "update refresh_token set revocado_en = now()",
                "select password_hash from usuario",
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
                if sql.startswith("select count"):
                    assert result.scalar_one() == 0, sql
                else:
                    assert result.rowcount == 0, sql
                nested.commit()
        finally:
            tx.rollback()
    assert _estado(pw_db) == before


def _owner_run(conn: Connection, gucs: dict, sql: str, params: dict) -> int | str:
    """Como ``plataforma_owner`` con ``gucs``: filas afectadas o el SQLSTATE del error."""
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


def test_owner_policies_open_only_the_three_columns_of_the_target_user(pw_db, dev):
    """Lo que la RLS y los privilegios por columna del dueño abren en 0032 (RC9, RC10)."""
    empresa = _empresa(pw_db)
    otra = _empresa(pw_db)
    persona = empresa.contador
    _otra_membresia(pw_db, otra.tenant_id, persona, activa=False)
    for tenant in (empresa.tenant_id, otra.tenant_id):
        _sembrar_refresh(pw_db, tenant, persona.usuario_id)
    _sembrar_refresh(pw_db, empresa.tenant_id, empresa.admin.usuario_id)
    propia = {
        "app.plat_actor": dev.id,
        "app.plat_membresia_tenant": empresa.tenant_id,
        "app.plat_usuario_password": persona.usuario_id,
    }
    definir = (
        "update usuario set password_hash = :h, debe_cambiar_password = true, "
        "sesiones_validas_desde = now() where id = :u"
    )
    u = {"u": persona.usuario_id, "h": HASHER.hash(TEMPORAL)}
    revocar = "update refresh_token set revocado_en = now() where revocado_en is null"
    before = _estado(pw_db)
    with pw_db.migrator.connect() as conn:
        tx = conn.begin()
        try:
            conn.exec_driver_sql("SET LOCAL ROLE plataforma_owner")
            # Con sus GUC: el usuario objetivo, con la marca y el corte.
            assert _owner_run(conn, propia, definir, u) == 1
            # Sin la marca o sin el corte, el WITH CHECK lo rechaza.
            for sql in (
                "update usuario set password_hash = :h where id = :u",
                "update usuario set password_hash = :h, debe_cambiar_password = false, "
                "sesiones_validas_desde = now() where id = :u",
                "update usuario set nombre = 'X' where id = :u",
            ):
                assert _owner_run(conn, propia, sql, u) == INSUFFICIENT_PRIVILEGE, sql
            # Sin la GUC de 0032, con la de otro usuario o la empresa equivocada: cero filas.
            sin_password = {k: v for k, v in propia.items() if k != "app.plat_usuario_password"}
            assert _owner_run(conn, sin_password, definir, u) == 0
            ajeno = {**propia, "app.plat_usuario_password": empresa.admin.usuario_id}
            assert _owner_run(conn, ajeno, definir, u) == 0
            fuera = {**propia, "app.plat_membresia_tenant": TENANT_B}
            assert _owner_run(conn, fuera, definir, u) == 0
            inactivo = sembrar_dev(pw_db, nuevo_dev("dueno-inactivo"), activo=False)
            assert _owner_run(conn, {**propia, "app.plat_actor": inactivo.id}, definir, u) == 0
            # Nunca leer el hash, ni correo ni activo; nunca DELETE.
            for sql in (
                "select password_hash from usuario where id = :u",
                "update usuario set email = 'x@ejemplo.test' where id = :u",
                "update usuario set activo = false where id = :u",
                "delete from usuario where id = :u",
                "delete from refresh_token",
            ):
                assert _owner_run(conn, propia, sql, u) == INSUFFICIENT_PRIVILEGE, sql
            # Refresh: los de cualquier membresía del usuario (las dos empresas), nada más.
            assert _owner_run(conn, propia, revocar, {}) == 4
            assert _owner_run(conn, ajeno, revocar, {}) == 2
            assert _owner_run(conn, sin_password, revocar, {}) == 0
        finally:
            tx.rollback()
    assert _estado(pw_db) == before


def test_db_helper_uses_the_developer_of_the_session(pw_app, pw_db, dev):
    empresa = _empresa(pw_db)
    nuevo = HASHER.hash(TEMPORAL)
    with pw_app.app_context():
        with plataforma_session(dev.id) as session:
            assert (
                plataforma_restablecer_password_usuario(
                    session, empresa.tenant_id, empresa.contador.usuario_id, nuevo
                )
                is None
            )
        inactivo = sembrar_dev(pw_db, nuevo_dev("inactivo-db"), activo=False)
        with pytest.raises(PlataformaFuncionError) as excinfo:
            with plataforma_session(inactivo.id) as session:
                plataforma_restablecer_password_usuario(
                    session, empresa.tenant_id, empresa.admin.usuario_id, nuevo
                )
        assert excinfo.value.codigo == "desarrollador_no_autorizado"
        with pytest.raises(PlataformaFuncionError) as excinfo:
            with plataforma_session(dev.id) as session:
                plataforma_restablecer_password_usuario(
                    session, empresa.tenant_id, empresa.admin.usuario_id, "no-es-un-hash"
                )
        assert excinfo.value.codigo == "hash_invalido"
    assert _usuario(pw_db, empresa.contador.usuario_id)["password_hash"] == nuevo
    assert _usuario(pw_db, empresa.admin.usuario_id)["debe_cambiar_password"] is False


# --- HTTP (R53–R58; A27, A28) --------------------------------------------------------------


def test_a_valid_definition_is_204_and_cuts_every_session_of_the_person(
    client, headers, pw_db, dev
):
    empresa = _empresa(pw_db)
    persona = empresa.admin2
    sesion = _tenant_login(client, persona.email)
    assert sesion.status_code == 200
    token, cookie = _bearer(sesion), _cookie(sesion)
    assert client.get(SOLO_ADMIN, headers=token).status_code == 200
    antes = _usuario(pw_db, persona.usuario_id)
    membresias = _membresias(pw_db)
    time.sleep(1.05)  # el corte cae en un segundo posterior al iat del token vigente

    response = _post(client, headers, empresa.tenant_id, persona.usuario_id)
    assert response.status_code == 204
    assert response.get_data() == b""
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    despues = _usuario(pw_db, persona.usuario_id)
    # Solo el hash (Argon2id de la temporal), la marca y el corte; nombre, correo, activo,
    # rol y membresía intactos.
    assert despues["password_hash"] != antes["password_hash"]
    assert despues["password_hash"].startswith("$argon2id$")
    assert _verifica(despues["password_hash"], TEMPORAL)
    assert despues["debe_cambiar_password"] is True
    assert despues["sesiones_validas_desde"] is not None
    sin_cambio = {"password_hash", "debe_cambiar_password", "sesiones_validas_desde"}
    assert {k: v for k, v in despues.items() if k not in sin_cambio} == {
        k: v for k, v in antes.items() if k not in sin_cambio
    }
    assert _membresias(pw_db) == membresias
    # A28: el acceso vigente y el refresh anteriores ya no sirven; la contraseña anterior,
    # tampoco.
    vigente = client.get(SOLO_ADMIN, headers=token)
    assert vigente.status_code == 401
    assert error_code(vigente) == "no_autenticado"
    assert _refresh(client, cookie).status_code == 401
    assert _tenant_login(client, persona.email).status_code == 401
    assert _auditoria(pw_db, empresa.tenant_id) == [
        {
            "desarrollador_id": dev.id,
            "accion": "usuario_contrasena_restablecida",
            "resultado": "ok",
            "tenant_id": empresa.tenant_id,
            "objeto_id": persona.usuario_id,
        }
    ]


def test_the_temporary_password_enters_blocked_until_it_is_changed(client, headers, pw_db):
    empresa = _empresa(pw_db)
    persona = empresa.admin
    assert _post(client, headers, empresa.tenant_id, persona.usuario_id).status_code == 204
    entrada = _tenant_login(client, persona.email, TEMPORAL)
    assert entrada.status_code == 200
    assert entrada.get_json()["debe_cambiar_password"] is True
    temporal = _bearer(entrada)
    bloqueada = client.get(SOLO_ADMIN, headers=temporal)
    assert bloqueada.status_code == 403
    assert error_code(bloqueada) == BLOQUEO

    time.sleep(1.05)
    cambio = client.post(
        "/auth/cambiar-contrasena",
        json={"actual": TEMPORAL, "nueva": DEFINITIVA, "confirmacion": DEFINITIVA},
        headers=temporal,
    )
    assert cambio.status_code == 200, cambio.get_json()
    assert cambio.get_json()["debe_cambiar_password"] is False
    assert _usuario(pw_db, persona.usuario_id)["debe_cambiar_password"] is False
    assert client.get(SOLO_ADMIN, headers=_bearer(cambio)).status_code == 200
    assert _tenant_login(client, persona.email, TEMPORAL).status_code == 401
    assert _tenant_login(client, persona.email, DEFINITIVA).status_code == 200


def _tenant_routes(flask_app: Flask) -> list[tuple[str, str, str]]:
    found = []
    for rule in flask_app.url_map.iter_rules():
        if rule.rule.startswith("/plataforma"):
            continue
        view = flask_app.view_functions[rule.endpoint]
        if getattr(view, "required_roles", None) is None:
            continue
        path = re.sub(r"<(?:[^:<>]+:)?[^<>]+>", str(uuid.uuid4()), rule.rule)
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            found.append((rule.endpoint, method, path))
    return found


@pytest.mark.parametrize("rol", ["admin", "contador"])
def test_with_the_temporary_password_every_tenant_endpoint_but_r26_is_403(
    client, pw_app, headers, pw_db, rol
):
    # A28 (recorrido de url_map, como A16): la lista blanca es la de R26.
    empresa = _empresa(pw_db)
    persona = empresa.admin if rol == "admin" else empresa.contador
    assert _post(client, headers, empresa.tenant_id, persona.usuario_id).status_code == 204
    entrada = _tenant_login(client, persona.email, TEMPORAL)
    assert entrada.status_code == 200
    temporal = _bearer(entrada)
    routes = _tenant_routes(pw_app)
    assert len(routes) > 30
    for endpoint, method, path in routes:
        if endpoint in PASSWORD_CHANGE_ENDPOINTS:
            continue
        response = client.open(path, method=method, json={}, headers=temporal)
        assert response.status_code == 403, (rol, endpoint, method)
        assert error_code(response) == BLOQUEO, (rol, endpoint, method)
    assert client.get("/auth/me", headers=temporal).status_code == 200


def test_recovery_by_email_over_a_pending_temporary_clears_the_flag(
    client, headers, pw_db, app_engine
):
    # R59 / R28: la recuperación de la 014 deja la marca en false aunque la temporal siga
    # pendiente.
    empresa = _empresa(pw_db)
    persona = empresa.contador
    assert _post(client, headers, empresa.tenant_id, persona.usuario_id).status_code == 204
    assert _usuario(pw_db, persona.usuario_id)["debe_cambiar_password"] is True
    clave = hashlib.sha256(uuid.uuid4().hex.encode()).hexdigest()
    with app_engine.begin() as conn:
        assert conn.scalar(
            text("select acceso.solicitar_recuperacion(:e, :c)"),
            {"e": persona.email, "c": clave},
        )
    with app_engine.begin() as conn:
        restablecido = conn.scalar(
            text("select acceso.restablecer_contrasena(:c, :h)"),
            {"c": clave, "h": HASHER.hash(DEFINITIVA)},
        )
    assert restablecido == persona.usuario_id
    assert _usuario(pw_db, persona.usuario_id)["debe_cambiar_password"] is False
    assert _tenant_login(client, persona.email, DEFINITIVA).status_code == 200


def test_a_second_definition_revokes_and_audits_again(client, headers, pw_db, dev):
    # No idempotente: cada llamada válida cambia la contraseña, revoca y audita.
    empresa = _empresa(pw_db)
    persona = empresa.contador
    assert _post(client, headers, empresa.tenant_id, persona.usuario_id).status_code == 204
    entrada = _tenant_login(client, persona.email, TEMPORAL)
    cookie = _cookie(entrada)
    assert (
        _post(client, headers, empresa.tenant_id, persona.usuario_id, OTRA_TEMPORAL).status_code
        == 204
    )
    assert _refresh(client, cookie).status_code == 401
    assert _tenant_login(client, persona.email, TEMPORAL).status_code == 401
    assert _tenant_login(client, persona.email, OTRA_TEMPORAL).status_code == 200
    filas_auditoria = _auditoria(pw_db, empresa.tenant_id)
    assert [r["accion"] for r in filas_auditoria] == ["usuario_contrasena_restablecida"] * 2
    assert all(r["objeto_id"] == persona.usuario_id for r in filas_auditoria)


def test_the_only_admin_can_get_a_temporary_password(client, headers, pw_db):
    # Q-P1: cualquier usuario, también el único admin activo (sin ultimo_admin).
    empresa = _empresa(pw_db)
    ejecutar(
        pw_db,
        "update membresia set activa = false where usuario_id = :u",
        {"u": empresa.admin2.usuario_id},
    )
    membresias = _membresias(pw_db)
    response = _post(client, headers, empresa.tenant_id, empresa.admin.usuario_id)
    assert response.status_code == 204
    assert _membresias(pw_db) == membresias  # sigue siendo admin activo
    assert _tenant_login(client, empresa.admin.email, TEMPORAL).status_code == 200


def test_an_inactive_membership_and_a_user_of_two_companies_lose_every_session(
    client, headers, pw_db
):
    # Q-P3 / RC8: membresía desactivada aquí y activa en otra empresa; se permite desde las
    # dos y se revocan todas sus sesiones.
    empresa = _empresa(pw_db)
    otra = _empresa(pw_db)
    persona = empresa.contador
    ejecutar(
        pw_db,
        "update membresia set activa = false where usuario_id = :u and tenant_id = :t",
        {"u": persona.usuario_id, "t": empresa.tenant_id},
    )
    _otra_membresia(pw_db, otra.tenant_id, persona, activa=True)
    sesion = _tenant_login(client, persona.email)  # entra a la otra (su única activa)
    assert sesion.status_code == 200
    _sembrar_refresh(pw_db, empresa.tenant_id, persona.usuario_id)
    cookie = _cookie(sesion)
    membresias = _membresias(pw_db)

    response = _post(client, headers, empresa.tenant_id, persona.usuario_id)
    assert response.status_code == 204
    assert _membresias(pw_db) == membresias
    assert _vivos(pw_db, persona.usuario_id) == 0
    assert _refresh(client, cookie).status_code == 401
    assert _tenant_login(client, persona.email, TEMPORAL).status_code == 200
    # Y desde la otra empresa también.
    assert (
        _post(client, headers, otra.tenant_id, persona.usuario_id, OTRA_TEMPORAL).status_code == 204
    )
    assert _vivos(pw_db, persona.usuario_id) == 0
    assert _auditoria(pw_db, otra.tenant_id)[-1]["accion"] == "usuario_contrasena_restablecida"


def test_inactive_company_is_409_without_changes_nor_audit(client, headers, pw_db):
    empresa = _empresa(pw_db, activa=False)
    before = _estado(pw_db)
    for persona in (empresa.admin, empresa.contador):
        response = _post(client, headers, empresa.tenant_id, persona.usuario_id)
        assert response.status_code == 409
        assert error_code(response) == "empresa_inactiva"
    assert _estado(pw_db) == before
    assert _auditoria(pw_db, empresa.tenant_id) == []


def test_foreign_or_unknown_ids_are_a_generic_404(client, headers, pw_db):
    empresa = _empresa(pw_db)
    otra = _empresa(pw_db)
    inactiva = _empresa(pw_db, activa=False)
    before = _estado(pw_db)
    for tenant, usuario, mensaje in (
        (empresa.tenant_id, otra.contador.usuario_id, "Ese usuario no pertenece a esta empresa."),
        (TENANT_A, ADMIN_B.usuario_id, "Ese usuario no pertenece a esta empresa."),
        (empresa.tenant_id, uuid.uuid4(), "Ese usuario no pertenece a esta empresa."),
        (inactiva.tenant_id, otra.contador.usuario_id, "Ese usuario no pertenece a esta empresa."),
        (uuid.uuid4(), empresa.contador.usuario_id, "La empresa no existe."),
    ):
        response = _post(client, headers, tenant, usuario)
        assert response.status_code == 404, (tenant, usuario)
        assert error_code(response) == "no_encontrado"
        assert response.get_json()["error"]["message"] == mensaje
        assert otra.contador.email not in response.get_data(as_text=True)
    assert _estado(pw_db) == before


def test_tenant_b_is_untouched(client, headers, pw_db):
    empresa = _empresa(pw_db)
    tenant_b = (
        filas(pw_db, "select * from membresia where tenant_id = :t order by id", {"t": TENANT_B}),
        filas(pw_db, "select * from tenant where id = :t", {"t": TENANT_B}),
        _usuario(pw_db, ADMIN_B.usuario_id),
    )
    assert _post(client, headers, empresa.tenant_id, empresa.contador.usuario_id).status_code == 204
    assert (
        filas(pw_db, "select * from membresia where tenant_id = :t order by id", {"t": TENANT_B}),
        filas(pw_db, "select * from tenant where id = :t", {"t": TENANT_B}),
        _usuario(pw_db, ADMIN_B.usuario_id),
    ) == tenant_b
    assert _tenant_login(client, ADMIN_B.email).status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {},
        {"password": TEMPORAL},
        {"password_confirmacion": TEMPORAL},
        {"password": TEMPORAL, "password_confirmacion": TEMPORAL, "nombre": "X"},
        {"password": TEMPORAL, "password_confirmacion": TEMPORAL, "email": "x@ejemplo.test"},
        {"password": TEMPORAL, "password_confirmacion": TEMPORAL, "rol": "admin"},
        {"password": TEMPORAL, "password_confirmacion": TEMPORAL, "debe_cambiar_password": False},
        {"password": TEMPORAL, "password_confirmacion": TEMPORAL, "password_hash": "h"},
        {"password": None, "password_confirmacion": None},
        {"password": 1234567890, "password_confirmacion": 1234567890},
        {"password": TEMPORAL, "password_confirmacion": None},
    ],
)
def test_the_body_is_exactly_password_and_its_confirmation(client, headers, pw_db, body):
    empresa = _empresa(pw_db)
    before = _estado(pw_db)
    ruta = _ruta(empresa.tenant_id, empresa.contador.usuario_id)
    if body is None:
        response = client.post(ruta, data="no-json", headers=headers)
    else:
        response = client.post(ruta, json=body, headers=headers)
    assert response.status_code == 400
    assert error_code(response) == "solicitud_invalida"
    assert TEMPORAL not in response.get_data(as_text=True)
    assert _estado(pw_db) == before


@pytest.mark.parametrize(
    ("password", "confirmacion", "codigo", "campo"),
    [
        ("corta-9ch", None, "contrasena_corta", "password"),
        ("x" * 129, None, "contrasena_larga", "password"),
        ("inventario123", None, "contrasena_comun", "password"),
        ("\ud800" * 12, None, "contrasena_invalida", "password"),
        (TEMPORAL, OTRA_TEMPORAL, "contrasenas_distintas", "password_confirmacion"),
        (TEMPORAL, TEMPORAL.lower(), "contrasenas_distintas", "password_confirmacion"),
    ],
)
def test_invalid_passwords_are_422_with_campo_and_change_nothing(
    client, headers, pw_db, password, confirmacion, codigo, campo
):
    empresa = _empresa(pw_db)
    before = _estado(pw_db)
    response = _post(
        client, headers, empresa.tenant_id, empresa.contador.usuario_id, password, confirmacion
    )
    assert response.status_code == 422
    assert error_code(response) == codigo
    assert response.get_json()["error"]["campo"] == campo
    texto = response.get_data(as_text=True)
    assert TEMPORAL not in texto and OTRA_TEMPORAL not in texto
    assert _estado(pw_db) == before


def test_10_and_128_characters_are_accepted(client, headers, pw_db):
    empresa = _empresa(pw_db)
    for password in ("Diez-chr10", "y" * 127 + "Z"):
        assert len(password) in (10, 128)
        response = _post(client, headers, empresa.tenant_id, empresa.contador.usuario_id, password)
        assert response.status_code == 204
        assert _tenant_login(client, empresa.contador.email, password).status_code == 200


def test_tenant_tokens_get_401_with_a_valid_body(client, pw_db):
    empresa = _empresa(pw_db)
    before = _estado(pw_db)
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
            response = _post(client, extra, tenant, usuario)
            assert response.status_code == 401, (name, tenant)
            assert error_code(response) == "no_autenticado"
    assert _estado(pw_db) == before


def test_a_developer_deactivated_after_login_gets_401(pw_app, pw_db):
    client = pw_app.test_client(use_cookies=False)
    otro = sembrar_dev(pw_db, nuevo_dev("baja-password"))
    auth = plat_bearer(login(client, otro.email).get_json()["access_token"])
    empresa = _empresa(pw_db)
    ejecutar(pw_db, "update desarrollador set activo = false where id = :d", {"d": otro.id})
    before = _estado(pw_db)
    response = _post(client, auth, empresa.tenant_id, empresa.contador.usuario_id)
    assert response.status_code == 401
    assert error_code(response) == "no_autenticado"
    assert _estado(pw_db) == before


def test_post_counts_in_plat_accion_before_touching_the_database(pw_db):
    flask_app = make_plat_app(pw_db, rate_limits=dataclasses.replace(HIGH_LIMITS, plat_accion=2))
    try:
        client = flask_app.test_client(use_cookies=False)
        otro = sembrar_dev(pw_db, nuevo_dev("tope-password"))
        auth = plat_bearer(login(client, otro.email).get_json()["access_token"])
        empresa = _empresa(pw_db)
        persona = empresa.contador
        # Un cuerpo inválido también cuenta (el tope va antes de validar y de Argon2).
        assert (
            client.post(
                _ruta(empresa.tenant_id, persona.usuario_id), json={}, headers=auth
            ).status_code
            == 400
        )
        assert _post(client, auth, empresa.tenant_id, persona.usuario_id).status_code == 204
        before = _estado(pw_db)
        response = _post(client, auth, empresa.tenant_id, persona.usuario_id, OTRA_TEMPORAL)
        assert response.status_code == 429
        assert error_code(response) == "demasiadas_solicitudes"
        assert _estado(pw_db) == before
    finally:
        dispose(flask_app)


@pytest.mark.parametrize("cual", ["objetivo", "otra_del_usuario"])
def test_a_busy_company_lock_fails_with_503_without_changes(client, headers, pw_db, cual):
    # El candado de la empresa pedida y el de otra empresa del usuario (la contraseña es
    # global: se toman todos).
    empresa = _empresa(pw_db)
    otra = _empresa(pw_db)
    persona = empresa.contador
    _otra_membresia(pw_db, otra.tenant_id, persona, activa=False)
    _sembrar_refresh(pw_db, empresa.tenant_id, persona.usuario_id)
    ocupada = empresa.tenant_id if cual == "objetivo" else otra.tenant_id
    before = _estado(pw_db)
    with pw_db.migrator.connect() as conn:
        tx = conn.begin()
        conn.execute(
            text("select pg_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": f"{CLAVE_CANDADO}{ocupada}"},
        )
        resultado: dict = {}

        def definir() -> None:
            inicio = time.monotonic()
            resultado["r"] = _post(client, headers, empresa.tenant_id, persona.usuario_id)
            resultado["espera"] = time.monotonic() - inicio

        hilo = threading.Thread(target=definir)
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
    assert _estado(pw_db) == before
    assert _auditoria(pw_db, empresa.tenant_id) == []


def test_a_foreign_user_is_404_even_if_another_company_of_it_is_busy(client, headers, pw_db):
    # Los 404 van antes de los candados: no se espera a otra empresa para responderlos.
    empresa = _empresa(pw_db)
    otra = _empresa(pw_db)
    with pw_db.migrator.connect() as conn:
        tx = conn.begin()
        conn.execute(
            text("select pg_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": f"{CLAVE_CANDADO}{otra.tenant_id}"},
        )
        try:
            inicio = time.monotonic()
            response = _post(client, headers, empresa.tenant_id, otra.contador.usuario_id)
            espera = time.monotonic() - inicio
        finally:
            tx.rollback()
    assert response.status_code == 404
    assert espera < LOCK_TIMEOUT_SEGUNDOS - 1


def _error_db(sqlstate: str) -> DBAPIError:
    from psycopg import errors as pg_errors

    clase = {"40P01": pg_errors.DeadlockDetected, "40001": pg_errors.SerializationFailure}
    return DBAPIError("select 1", {}, clase[sqlstate]("detalle-interno-de-la-base"))


@pytest.mark.parametrize("sqlstate", ["40P01", "40001"])
def test_a_deadlock_or_serialization_failure_is_503(client, headers, pw_db, monkeypatch, sqlstate):
    from app.plataforma.modulos.usuarios import service

    empresa = _empresa(pw_db)
    before = _estado(pw_db)

    def falla(*args, **kwargs):
        raise _error_db(sqlstate)

    monkeypatch.setattr(service, "plataforma_restablecer_password_usuario", falla)
    response = _post(client, headers, empresa.tenant_id, empresa.contador.usuario_id)
    assert response.status_code == 503
    assert error_code(response) == "servicio_no_disponible"
    assert "detalle-interno" not in response.get_data(as_text=True)
    assert _estado(pw_db) == before


def test_audit_failure_rolls_back_the_definition(client, headers, pw_db, monkeypatch):
    from app.plataforma import auditoria

    empresa = _empresa(pw_db)
    _sembrar_refresh(pw_db, empresa.tenant_id, empresa.contador.usuario_id)
    before = _estado(pw_db)

    def falla(*args, **kwargs):
        raise RuntimeError("auditoría caída (sintético)")

    monkeypatch.setattr(auditoria, "registrar", falla)
    response = _post(client, headers, empresa.tenant_id, empresa.contador.usuario_id)
    assert response.status_code == 500
    assert _estado(pw_db) == before


def test_neither_response_audit_nor_logs_carry_the_password_or_the_hash(
    client, headers, pw_db, dev, caplog
):
    # A27 / R57: se buscan los valores enviados y el hash guardado en todas las columnas de
    # la auditoría, en los logs y en cada respuesta.
    caplog.set_level(logging.DEBUG)
    empresa = _empresa(pw_db)
    persona = empresa.contador
    centinela = f"Centinela-{uuid.uuid4().hex[:12]}"
    distinta = f"Distinta-{uuid.uuid4().hex[:12]}"
    respuestas = [
        _post(client, headers, empresa.tenant_id, persona.usuario_id, centinela),
        _post(client, headers, empresa.tenant_id, persona.usuario_id, centinela, distinta),
        _post(client, headers, empresa.tenant_id, persona.usuario_id, "corta"),
        _post(client, headers, uuid.uuid4(), persona.usuario_id, centinela),
    ]
    assert [r.status_code for r in respuestas] == [204, 422, 422, 404]
    guardado = _usuario(pw_db, persona.usuario_id)["password_hash"]
    assert _verifica(guardado, centinela)
    sal_y_hash = guardado.rsplit("$", 2)[1:]
    rows = filas(
        pw_db,
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
    assert [{k: v for k, v in r.items() if k not in ("id", "creado_en")} for r in rows] == [
        {
            "desarrollador_id": dev.id,
            "accion": "usuario_contrasena_restablecida",
            "resultado": "ok",
            "tenant_id": empresa.tenant_id,
            "objeto_id": persona.usuario_id,
        }
    ]
    textos = [caplog.text, repr(rows), *(r.get_data(as_text=True) for r in respuestas)]
    for texto in textos:
        for secreto in (centinela, distinta, guardado, *sal_y_hash, persona.email, persona.nombre):
            assert secreto not in texto
        assert "argon2" not in texto
