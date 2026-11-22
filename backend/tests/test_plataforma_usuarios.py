"""Módulo Usuarios de la consola (spec 017, T5; R29–R31, R33–R36; A5, A17).

Sobre una base temporal migrada a ``head`` (tenants sintéticos A y B de ``acceso_db``) con
la consola habilitada. Cada prueba que cambia membresías usa una empresa propia sembrada
por el migrador (dos admins y un contador), así ninguna depende del orden de las demás.

- SQL (rol de la aplicación): las dos funciones de 0027 rechazan a quien no es un
  desarrollador activo (A5); la lista devuelve solo las columnas de R29; cambiar el estado
  toca solo ``membresia.activa`` de ese usuario y revoca solo sus familias de refresh;
  ``ultimo_admin``, ``empresa_inactiva`` y usuario de otra empresa no cambian nada; las
  GUC quedan vacías.
- HTTP: registro del módulo; ``GET`` con los campos exactos, ``no-store`` y ``404``;
  ``PATCH`` con ``{activa}`` exacto, auditoría en la misma transacción y sin auditar
  rechazos; el usuario desactivado recibe ``401`` en login, refresh y token vigente, y
  vuelve a entrar al reactivarlo; ``admin``/``contador`` reciben ``401`` con un cuerpo
  válido; un desarrollador desactivado recibe ``401``; tope ``plat_accion``; logs sin
  correos ni nombres.

Datos sintéticos (``@ejemplo.test``).
"""

import dataclasses
import logging
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
from app.auth.http import REFRESH_COOKIE_SECURE_NAME
from app.db import (
    CambioMembresia,
    PlataformaFuncionError,
    plataforma_cambiar_estado_membresia,
    plataforma_listar_usuarios,
    plataforma_session,
)

HASHER = argon2.PasswordHasher.from_parameters(ARGON2_TEST_PARAMS)
INSUFFICIENT_PRIVILEGE = "42501"
LISTAR = "select * from acceso.plataforma_listar_usuarios(:d, :t)"
# Devuelve una fila (estado, cambiado); ``scalar_one`` da el estado resultante.
ESTADO = "select * from acceso.plataforma_cambiar_estado_membresia(:d, :t, :u, :a)"
CLAVE_CANDADO = "plataforma_membresia:"
LOCK_TIMEOUT_SEGUNDOS = 5
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
)
CAMPOS = {"id", "nombre", "email", "rol", "activa", "debe_cambiar_password"}
TABLES = (
    "tenant",
    "usuario",
    "membresia",
    "empresa",
    "invitacion",
    "refresh_token",
    "plataforma_auditoria",
)


@pytest.fixture(scope="module")
def usr_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("plat_usuarios")


@pytest.fixture(scope="module")
def usr_app(usr_db) -> Iterator[Flask]:
    flask_app = make_plat_app(usr_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(usr_app):
    return usr_app.test_client(use_cookies=False)


@pytest.fixture(scope="module")
def app_engine(usr_db) -> Iterator[Engine]:
    engine = create_engine(usr_db.app_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def dev(usr_db) -> Dev:
    return sembrar_dev(usr_db, nuevo_dev("usuarios"))


@pytest.fixture(scope="module")
def headers(usr_app, dev) -> dict[str, str]:
    response = login(usr_app.test_client(use_cookies=False), dev.email)
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
            {"t": empresa.tenant_id, "n": f"Clínica Usuarios {uuid.uuid4().hex[:6]}"},
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


def _activa(db: AccesoDb, tenant_id, usuario_id) -> bool:
    (row,) = filas(
        db,
        "select activa from membresia where tenant_id = :t and usuario_id = :u",
        {"t": tenant_id, "u": usuario_id},
    )
    return row["activa"]


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


def _ruta(tenant_id, usuario_id=None) -> str:
    base = f"/plataforma/empresas/{tenant_id}/usuarios"
    return base if usuario_id is None else f"{base}/{usuario_id}"


def _patch(client, headers, tenant_id, usuario_id, activa):
    return client.patch(_ruta(tenant_id, usuario_id), json={"activa": activa}, headers=headers)


# --- SQL: utilidades -----------------------------------------------------------------------


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


# --- A5 / R36: quien llama debe ser un desarrollador activo ---------------------------------


@pytest.mark.parametrize("caso", ["inexistente", "inactivo", "usuario_de_clinica"])
def test_both_functions_reject_a_caller_that_is_not_an_active_developer(usr_db, app_engine, caso):
    if caso == "inexistente":
        caller = uuid.uuid4()
    elif caso == "inactivo":
        caller = sembrar_dev(usr_db, nuevo_dev("inactivo"), activo=False).id
    else:
        caller = ADMIN_A.usuario_id  # un admin de clínica no es desarrollador
    empresa = _empresa(usr_db)
    before = (_counts(usr_db), _membresias(usr_db))
    calls = (
        (LISTAR, {"t": str(empresa.tenant_id)}),
        (ESTADO, {"t": str(empresa.tenant_id), "u": str(empresa.contador.usuario_id), "a": False}),
    )
    for sql, params in calls:
        message = _fail_app(app_engine, sql, {**params, "d": str(caller)}, INSUFFICIENT_PRIVILEGE)
        assert "desarrollador_no_autorizado" in message
        assert str(caller) not in message
        assert empresa.contador.email not in message
    assert (_counts(usr_db), _membresias(usr_db)) == before


def test_inside_a_tenant_session_an_admin_cannot_use_the_functions(usr_db, app_engine):
    empresa = _empresa(usr_db)
    before = _membresias(usr_db)
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(TENANT_A)})
            for sql, params in (
                (LISTAR, {"t": str(TENANT_A)}),
                (ESTADO, {"t": str(TENANT_A), "u": str(CONTADOR_A.usuario_id), "a": False}),
            ):
                _expect_error(
                    conn, sql, {**params, "d": str(ADMIN_A.usuario_id)}, INSUFFICIENT_PRIVILEGE
                )
        finally:
            tx.rollback()
    assert _membresias(usr_db) == before
    assert _activa(usr_db, empresa.tenant_id, empresa.contador.usuario_id) is True


# --- SQL: lista (R29) ----------------------------------------------------------------------


def test_list_returns_only_the_r29_columns_of_that_tenant_and_clears_its_gucs(
    usr_db, app_engine, dev
):
    empresa = _empresa(usr_db)
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            result = conn.execute(text(LISTAR), {"d": str(dev.id), "t": str(empresa.tenant_id)})
            columns = list(result.keys())
            rows = result.all()
            assert _gucs_empty(conn)
        finally:
            tx.rollback()
    assert columns == ["usuario_id", "nombre", "email", "rol", "activa", "debe_cambiar_password"]
    personas = (empresa.admin, empresa.admin2, empresa.contador)
    assert sorted(tuple(r) for r in rows) == sorted(
        (p.usuario_id, p.nombre, p.email, p.rol, True, False) for p in personas
    )
    # Nada de otros tenants.
    assert {r.usuario_id for r in rows}.isdisjoint({ADMIN_A.usuario_id, ADMIN_B.usuario_id})


def test_list_of_an_unknown_company_fails_with_no_rows(app_engine, dev):
    message = _fail_app(app_engine, LISTAR, {"d": str(dev.id), "t": str(uuid.uuid4())}, "P0002")
    assert "empresa_no_encontrada" in message


def test_list_shows_the_pending_password_change_and_inactive_memberships(usr_db, app_engine, dev):
    empresa = _empresa(usr_db)
    ejecutar(
        usr_db,
        "update usuario set debe_cambiar_password = true where id = :u",
        {"u": empresa.admin.usuario_id},
    )
    ejecutar(
        usr_db,
        "update membresia set activa = false where usuario_id = :u",
        {"u": empresa.contador.usuario_id},
    )
    with app_engine.begin() as conn:
        rows = {
            r.usuario_id: r
            for r in conn.execute(text(LISTAR), {"d": str(dev.id), "t": str(empresa.tenant_id)})
        }
    assert rows[empresa.admin.usuario_id].debe_cambiar_password is True
    assert rows[empresa.contador.usuario_id].activa is False
    assert rows[empresa.admin2.usuario_id].activa is True


# --- SQL: estado (R30, R31) ----------------------------------------------------------------


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


def test_deactivating_touches_only_that_membership_and_revokes_only_its_families(
    usr_db, app_engine, dev
):
    empresa = _empresa(usr_db)
    otra = _empresa(usr_db)
    for persona in (empresa.contador, empresa.admin):
        _sembrar_refresh(usr_db, empresa.tenant_id, persona.usuario_id)
    _sembrar_refresh(usr_db, otra.tenant_id, otra.contador.usuario_id)
    before = _membresias(usr_db)
    usuarios_antes = filas(usr_db, "select * from usuario order by id")
    tenants_antes = filas(usr_db, "select * from tenant order by id")

    with app_engine.connect() as conn:
        tx = conn.begin()
        params = {
            "d": str(dev.id),
            "t": str(empresa.tenant_id),
            "u": str(empresa.contador.usuario_id),
            "a": False,
        }
        assert conn.execute(text(ESTADO), params).scalar_one() is False
        assert _gucs_empty(conn)
        tx.commit()

    after = _membresias(usr_db)
    changed = sorted(set(before) ^ set(after))
    tenant, contador = str(empresa.tenant_id), str(empresa.contador.usuario_id)
    assert changed == sorted(
        [(tenant, contador, "contador", True), (tenant, contador, "contador", False)]
    )
    assert filas(usr_db, "select * from usuario order by id") == usuarios_antes
    assert filas(usr_db, "select * from tenant order by id") == tenants_antes
    assert _refresh_tokens(usr_db, empresa.tenant_id) == {
        contador: True,
        str(empresa.admin.usuario_id): False,
    }
    assert _refresh_tokens(usr_db, otra.tenant_id) == {str(otra.contador.usuario_id): False}


def test_state_change_is_idempotent(usr_db, app_engine, dev):
    empresa = _empresa(usr_db)
    params = {
        "d": str(dev.id),
        "t": str(empresa.tenant_id),
        "u": str(empresa.contador.usuario_id),
    }
    for activa, cambiado in ((False, True), (False, False), (True, True), (True, False)):
        with app_engine.connect() as conn:
            tx = conn.begin()
            result = conn.execute(text(ESTADO), {**params, "a": activa})
            assert list(result.keys()) == ["estado", "cambiado"]
            assert tuple(result.one()) == (activa, cambiado)
            # También la rama idempotente deja vacías todas las GUC.
            assert _gucs_empty(conn)
            tx.commit()
        assert _activa(usr_db, empresa.tenant_id, empresa.contador.usuario_id) is activa


def test_a_rejection_leaves_every_guc_empty(usr_db, app_engine, dev):
    empresa = _empresa(usr_db)
    inactiva = _empresa(usr_db, activa=False)
    otra = _empresa(usr_db)
    base = {"d": str(dev.id), "a": False}
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(
                text(ESTADO),
                {**base, "t": str(empresa.tenant_id), "u": str(empresa.admin2.usuario_id)},
            )
            assert _gucs_empty(conn)
            for tenant, usuario, sqlstate, codigo in (
                (empresa.tenant_id, empresa.admin.usuario_id, "P0001", "ultimo_admin"),
                (inactiva.tenant_id, inactiva.contador.usuario_id, "P0001", "empresa_inactiva"),
                (empresa.tenant_id, otra.contador.usuario_id, "P0002", "usuario_no_encontrado"),
                (uuid.uuid4(), empresa.contador.usuario_id, "P0002", "empresa_no_encontrada"),
            ):
                params = {**base, "t": str(tenant), "u": str(usuario)}
                assert codigo in _expect_error(conn, ESTADO, params, sqlstate)
                assert _gucs_empty(conn), codigo
        finally:
            tx.rollback()


def test_the_last_active_admin_cannot_be_deactivated(usr_db, app_engine, dev):
    empresa = _empresa(usr_db)
    base = {"d": str(dev.id), "t": str(empresa.tenant_id)}
    with app_engine.begin() as conn:
        conn.execute(text(ESTADO), {**base, "u": str(empresa.admin2.usuario_id), "a": False})
    before = _membresias(usr_db)
    message = _fail_app(
        app_engine, ESTADO, {**base, "u": str(empresa.admin.usuario_id), "a": False}, "P0001"
    )
    assert "ultimo_admin" in message
    assert _membresias(usr_db) == before
    # Un contador sí se desactiva, y otro admin reactivado permite desactivar al primero.
    with app_engine.begin() as conn:
        conn.execute(text(ESTADO), {**base, "u": str(empresa.contador.usuario_id), "a": False})
        conn.execute(text(ESTADO), {**base, "u": str(empresa.admin2.usuario_id), "a": True})
        conn.execute(text(ESTADO), {**base, "u": str(empresa.admin.usuario_id), "a": False})
    assert _activa(usr_db, empresa.tenant_id, empresa.admin.usuario_id) is False


def test_two_overlapping_deactivations_of_the_two_admins_leave_one_active(usr_db, app_engine, dev):
    # P31 bajo concurrencia: la primera desactiva un admin y no confirma; la segunda (el otro
    # admin) espera el candado consultivo del tenant (visto en pg_locks); al confirmar la
    # primera, la segunda ve que es el último admin y da ultimo_admin sin cambiar nada.
    empresa = _empresa(usr_db)
    base = {"d": str(dev.id), "t": str(empresa.tenant_id), "a": False}
    resultado: dict[str, object] = {}

    def espera(pid: int) -> bool:
        (row,) = filas(
            usr_db,
            "select exists(select 1 from pg_locks where pid = :p and not granted) as e",
            {"p": pid},
        )
        return row["e"]

    with app_engine.connect() as segunda:
        pid = segunda.scalar(text("select pg_backend_pid()"))
        segunda.commit()

        def desactivar_segunda() -> None:
            try:
                with segunda.begin():
                    segunda.execute(text("set local lock_timeout = '30s'"))
                    resultado["ok"] = segunda.scalar(
                        text(ESTADO), {**base, "u": str(empresa.admin2.usuario_id)}
                    )
            except DBAPIError as exc:
                resultado["error"] = (exc.orig.sqlstate, exc.orig.diag.message_primary)

        with app_engine.connect() as primera:
            primera.begin()
            assert (
                primera.scalar(text(ESTADO), {**base, "u": str(empresa.admin.usuario_id)}) is False
            )
            hilo = threading.Thread(target=desactivar_segunda)
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
    assert _activa(usr_db, empresa.tenant_id, empresa.admin.usuario_id) is False
    assert _activa(usr_db, empresa.tenant_id, empresa.admin2.usuario_id) is True


def test_an_inactive_company_rejects_membership_changes_both_ways(usr_db, app_engine, dev):
    empresa = _empresa(usr_db, activa=False)
    ejecutar(
        usr_db,
        "update membresia set activa = false where usuario_id = :u",
        {"u": empresa.contador.usuario_id},
    )
    before = _membresias(usr_db)
    base = {"d": str(dev.id), "t": str(empresa.tenant_id)}
    for usuario, activa in ((empresa.admin2, False), (empresa.contador, True)):
        message = _fail_app(
            app_engine, ESTADO, {**base, "u": str(usuario.usuario_id), "a": activa}, "P0001"
        )
        assert "empresa_inactiva" in message
    assert _membresias(usr_db) == before


def test_a_user_of_another_company_is_not_found_and_nothing_changes(usr_db, app_engine, dev):
    empresa = _empresa(usr_db)
    otra = _empresa(usr_db)
    before = _membresias(usr_db)
    for tenant, usuario, codigo in (
        (empresa.tenant_id, otra.contador.usuario_id, "usuario_no_encontrado"),
        (empresa.tenant_id, uuid.uuid4(), "usuario_no_encontrado"),
        (TENANT_B, CONTADOR_A.usuario_id, "usuario_no_encontrado"),
        (uuid.uuid4(), empresa.contador.usuario_id, "empresa_no_encontrada"),
    ):
        params = {"d": str(dev.id), "t": str(tenant), "u": str(usuario), "a": False}
        assert codigo in _fail_app(app_engine, ESTADO, params, "P0002")
    assert _membresias(usr_db) == before


def test_the_app_role_cannot_change_memberships_directly_even_with_the_gucs(
    usr_db, app_engine, dev
):
    """Sin la función, fijar las GUC de 0027 no abre nada a la aplicación."""
    empresa = _empresa(usr_db)
    _sembrar_refresh(usr_db, empresa.tenant_id, empresa.contador.usuario_id)
    before = (_membresias(usr_db), _refresh_tokens(usr_db, empresa.tenant_id))
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            for guc, value in (
                ("app.desarrollador_id", dev.id),
                ("app.plat_actor", dev.id),
                ("app.plat_usuarios", empresa.tenant_id),
                ("app.plat_membresia_tenant", empresa.tenant_id),
                ("app.plat_membresia_usuario", empresa.contador.usuario_id),
            ):
                conn.execute(text("select set_config(:g, :v, true)"), {"g": guc, "v": str(value)})
            for sql in (
                "update membresia set activa = false",
                "update refresh_token set revocado_en = now()",
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
    assert (_membresias(usr_db), _refresh_tokens(usr_db, empresa.tenant_id)) == before


def test_app_db_functions_use_the_developer_of_the_session(usr_app, usr_db, dev):
    empresa = _empresa(usr_db)
    with usr_app.app_context():
        with plataforma_session(dev.id) as session:
            usuarios = plataforma_listar_usuarios(session, empresa.tenant_id)
            assert {u.usuario_id for u in usuarios} == {
                empresa.admin.usuario_id,
                empresa.admin2.usuario_id,
                empresa.contador.usuario_id,
            }
            # El repr no lleva nombre ni correo.
            assert empresa.admin.email not in repr(usuarios)
            assert empresa.admin.nombre not in repr(usuarios)
            cambio = plataforma_cambiar_estado_membresia(
                session, empresa.tenant_id, empresa.contador.usuario_id, False
            )
            assert cambio == CambioMembresia(activa=False, cambiado=True)
            repetido = plataforma_cambiar_estado_membresia(
                session, empresa.tenant_id, empresa.contador.usuario_id, False
            )
            assert repetido == CambioMembresia(activa=False, cambiado=False)
        inactivo = sembrar_dev(usr_db, nuevo_dev("inactivo-db"), activo=False)
        with pytest.raises(PlataformaFuncionError) as excinfo:
            with plataforma_session(inactivo.id) as session:
                plataforma_listar_usuarios(session, empresa.tenant_id)
        assert excinfo.value.codigo == "desarrollador_no_autorizado"
    assert _activa(usr_db, empresa.tenant_id, empresa.contador.usuario_id) is False


# --- HTTP: registro y lista -----------------------------------------------------------------


def test_the_usuarios_module_is_registered(client, headers):
    response = client.get("/plataforma/modulos", headers=headers)
    assert response.status_code == 200
    modulos = response.get_json()["modulos"]
    (usuarios,) = [m for m in modulos if m["id"] == "usuarios"]
    assert usuarios["titulo"] == "Usuarios"
    assert [m["id"] for m in modulos].index("usuarios") > [m["id"] for m in modulos].index(
        "empresas"
    )


def test_list_returns_exactly_the_r29_fields(client, headers, usr_db):
    empresa = _empresa(usr_db)
    response = client.get(_ruta(empresa.tenant_id), headers=headers)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    usuarios = response.get_json()["usuarios"]
    assert all(set(u) == CAMPOS for u in usuarios)
    assert {u["id"]: (u["email"], u["rol"], u["activa"]) for u in usuarios} == {
        str(p.usuario_id): (p.email, p.rol, True)
        for p in (empresa.admin, empresa.admin2, empresa.contador)
    }
    assert "hash" not in response.get_data(as_text=True)
    assert "argon2" not in response.get_data(as_text=True)


def test_list_of_an_unknown_company_is_404(client, headers):
    response = client.get(_ruta(uuid.uuid4()), headers=headers)
    assert response.status_code == 404
    assert error_code(response) == "no_encontrado"


def test_list_requires_a_developer(client, usr_db):
    empresa = _empresa(usr_db)
    for extra in ({}, bearer(ADMIN_A, TENANT_A, rol="admin")):
        response = client.get(_ruta(empresa.tenant_id), headers=extra)
        assert response.status_code == 401
        assert error_code(response) == "no_autenticado"


# --- HTTP: estado (R30, R31; A17) -----------------------------------------------------------


def test_deactivating_cuts_login_refresh_and_the_live_token_and_reactivating_restores(
    client, headers, usr_db, dev
):
    empresa = _empresa(usr_db)
    persona = empresa.contador
    sesion = _tenant_login(client, persona.email)
    assert sesion.status_code == 200
    token = {"Authorization": f"Bearer {sesion.get_json()['access_token']}"}
    cookie = _cookie(sesion)
    otro = _tenant_login(client, empresa.admin.email)
    assert otro.status_code == 200
    otro_token = {"Authorization": f"Bearer {otro.get_json()['access_token']}"}
    assert client.get("/auth/me", headers=token).status_code == 200

    response = _patch(client, headers, empresa.tenant_id, persona.usuario_id, False)
    assert response.status_code == 200, response.get_json()
    assert response.get_json() == {"id": str(persona.usuario_id), "activa": False}
    assert response.headers["Cache-Control"] == "no-store"

    # Token vigente, refresh y login: 401 (el mismo que una cuenta inexistente).
    vigente = client.get("/auth/me", headers=token)
    assert vigente.status_code == 401
    assert error_code(vigente) == "no_autenticado"
    assert _refresh(client, cookie).status_code == 401
    fallido = _tenant_login(client, persona.email)
    assert fallido.status_code == 401
    assert error_code(fallido) == "credenciales_invalidas"
    # Las familias de esa membresía quedaron revocadas; el otro usuario sigue dentro.
    assert _refresh_tokens(usr_db, empresa.tenant_id)[str(persona.usuario_id)] is True
    assert _refresh_tokens(usr_db, empresa.tenant_id)[str(empresa.admin.usuario_id)] is False
    assert client.get("/auth/me", headers=otro_token).status_code == 200

    response = _patch(client, headers, empresa.tenant_id, persona.usuario_id, True)
    assert response.status_code == 200
    assert response.get_json() == {"id": str(persona.usuario_id), "activa": True}
    assert _tenant_login(client, persona.email).status_code == 200
    # La familia revocada no revive al reactivar.
    assert _refresh(client, cookie).status_code == 401

    assert _auditoria(usr_db, empresa.tenant_id) == [
        {
            "desarrollador_id": dev.id,
            "accion": accion,
            "resultado": "ok",
            "tenant_id": empresa.tenant_id,
            "objeto_id": persona.usuario_id,
        }
        for accion in ("usuario_desactivado", "usuario_reactivado")
    ]


def test_deactivating_does_not_touch_other_memberships_nor_tenants(client, headers, usr_db):
    empresa = _empresa(usr_db)
    before = _membresias(usr_db)
    tenants = filas(usr_db, "select * from tenant order by id")
    response = _patch(client, headers, empresa.tenant_id, empresa.admin2.usuario_id, False)
    assert response.status_code == 200
    changed = set(before) ^ set(_membresias(usr_db))
    assert {(t, u) for t, u, _, _ in changed} == {
        (str(empresa.tenant_id), str(empresa.admin2.usuario_id))
    }
    assert filas(usr_db, "select * from tenant order by id") == tenants
    # B sigue entrando.
    assert _tenant_login(client, ADMIN_B.email).status_code == 200


def test_last_admin_is_409_without_changes_nor_audit(client, headers, usr_db):
    empresa = _empresa(usr_db)
    segundo = _patch(client, headers, empresa.tenant_id, empresa.admin2.usuario_id, False)
    assert segundo.status_code == 200
    auditoria_antes = _auditoria(usr_db, empresa.tenant_id)
    before = _membresias(usr_db)
    response = _patch(client, headers, empresa.tenant_id, empresa.admin.usuario_id, False)
    assert response.status_code == 409
    assert error_code(response) == "ultimo_admin"
    assert response.get_json()["error"]["message"] == (
        "No se puede desactivar al último admin activo de la empresa."
    )
    assert _membresias(usr_db) == before
    assert _auditoria(usr_db, empresa.tenant_id) == auditoria_antes
    assert _tenant_login(client, empresa.admin.email).status_code == 200


def test_inactive_company_is_409_without_changes_nor_audit(client, headers, usr_db):
    empresa = _empresa(usr_db, activa=False)
    before = (_membresias(usr_db), _counts(usr_db))
    for activa in (False, True):
        response = _patch(client, headers, empresa.tenant_id, empresa.contador.usuario_id, activa)
        assert response.status_code == 409
        assert error_code(response) == "empresa_inactiva"
    assert (_membresias(usr_db), _counts(usr_db)) == before


def test_a_user_of_another_company_or_unknown_ids_are_a_generic_404(client, headers, usr_db):
    empresa = _empresa(usr_db)
    otra = _empresa(usr_db)
    before = (_membresias(usr_db), _counts(usr_db))
    for tenant, usuario in (
        (empresa.tenant_id, otra.contador.usuario_id),
        (TENANT_A, ADMIN_B.usuario_id),
        (empresa.tenant_id, uuid.uuid4()),
        (uuid.uuid4(), empresa.contador.usuario_id),
    ):
        response = _patch(client, headers, tenant, usuario, False)
        assert response.status_code == 404, (tenant, usuario)
        assert error_code(response) == "no_encontrado"
        assert otra.contador.email not in response.get_data(as_text=True)
    assert (_membresias(usr_db), _counts(usr_db)) == before


@pytest.mark.parametrize(
    "ruta",
    [
        "/plataforma/empresas/no-es-uuid/usuarios",
        "/plataforma/empresas/{t}/usuarios/no-es-uuid",
        "/plataforma/empresas/{t}/usuarios/{u}x",
    ],
)
def test_non_uuid_ids_never_reach_the_view(client, headers, usr_db, ruta):
    empresa = _empresa(usr_db)
    path = ruta.format(t=empresa.tenant_id, u=empresa.contador.usuario_id)
    response = client.patch(path, json={"activa": False}, headers=headers)
    assert response.status_code in (404, 405)
    assert _activa(usr_db, empresa.tenant_id, empresa.contador.usuario_id) is True


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        {"activa": "false"},
        {"activa": 0},
        {"activa": None},
        {"activa": False, "rol": "admin"},
        {"activa": False, "tenant_id": str(TENANT_B)},
        [False],
    ],
)
def test_the_body_is_exactly_activa_bool(client, headers, usr_db, body):
    empresa = _empresa(usr_db)
    before = (_membresias(usr_db), _counts(usr_db))
    ruta = _ruta(empresa.tenant_id, empresa.contador.usuario_id)
    if body is None:
        response = client.patch(ruta, data="no-json", headers=headers)
    else:
        response = client.patch(ruta, json=body, headers=headers)
    assert response.status_code == 400
    assert error_code(response) == "solicitud_invalida"
    assert (_membresias(usr_db), _counts(usr_db)) == before


def test_tenant_tokens_get_401_with_a_valid_body(client, usr_db):
    empresa = _empresa(usr_db)
    before = (_membresias(usr_db), _counts(usr_db))
    objetivos = (
        (empresa.tenant_id, empresa.contador.usuario_id),
        (TENANT_A, CONTADOR_A.usuario_id),
        (TENANT_B, ADMIN_B.usuario_id),
    )
    for tenant, usuario in objetivos:
        for name, extra in (
            ("anonimo", {}),
            ("admin", bearer(ADMIN_A, TENANT_A, rol="admin")),
            ("contador", bearer(CONTADOR_A, TENANT_A, rol="contador")),
            ("admin_b", bearer(ADMIN_B, TENANT_B, rol="admin")),
        ):
            for response in (
                client.patch(_ruta(tenant, usuario), json={"activa": False}, headers=extra),
                client.get(_ruta(tenant), headers=extra),
            ):
                assert response.status_code == 401, (name, tenant)
                assert error_code(response) == "no_autenticado"
    assert (_membresias(usr_db), _counts(usr_db)) == before


def test_a_developer_deactivated_after_login_gets_401(usr_app, usr_db):
    client = usr_app.test_client(use_cookies=False)
    otro = sembrar_dev(usr_db, nuevo_dev("baja-usuarios"))
    response = login(client, otro.email)
    assert response.status_code == 200
    auth = plat_bearer(response.get_json()["access_token"])
    empresa = _empresa(usr_db)
    assert client.get(_ruta(empresa.tenant_id), headers=auth).status_code == 200
    ejecutar(usr_db, "update desarrollador set activo = false where id = :d", {"d": otro.id})
    before = (_membresias(usr_db), _counts(usr_db))
    for response in (
        client.get(_ruta(empresa.tenant_id), headers=auth),
        _patch(client, auth, empresa.tenant_id, empresa.contador.usuario_id, False),
    ):
        assert response.status_code == 401
        assert error_code(response) == "no_autenticado"
    assert (_membresias(usr_db), _counts(usr_db)) == before


def test_patch_counts_in_plat_accion_before_touching_the_database(usr_db):
    flask_app = make_plat_app(usr_db, rate_limits=dataclasses.replace(HIGH_LIMITS, plat_accion=2))
    try:
        client = flask_app.test_client(use_cookies=False)
        otro = sembrar_dev(usr_db, nuevo_dev("tope-usuarios"))
        auth = plat_bearer(login(client, otro.email).get_json()["access_token"])
        empresa = _empresa(usr_db)
        for activa in (False, True):
            response = _patch(client, auth, empresa.tenant_id, empresa.contador.usuario_id, activa)
            assert response.status_code == 200
        before = (_membresias(usr_db), _counts(usr_db))
        response = _patch(client, auth, empresa.tenant_id, empresa.contador.usuario_id, False)
        assert response.status_code == 429
        assert error_code(response) == "demasiadas_solicitudes"
        assert (_membresias(usr_db), _counts(usr_db)) == before
        # La lista no cuenta en el tope.
        assert client.get(_ruta(empresa.tenant_id), headers=auth).status_code == 200
    finally:
        dispose(flask_app)


def test_audit_failure_rolls_back_the_membership_change(client, headers, usr_db, monkeypatch):
    from app.plataforma import auditoria

    empresa = _empresa(usr_db)
    _sembrar_refresh(usr_db, empresa.tenant_id, empresa.contador.usuario_id)
    before = (_membresias(usr_db), _refresh_tokens(usr_db, empresa.tenant_id))

    def falla(*args, **kwargs):
        raise RuntimeError("auditoría caída (sintético)")

    monkeypatch.setattr(auditoria, "registrar", falla)
    response = _patch(client, headers, empresa.tenant_id, empresa.contador.usuario_id, False)
    assert response.status_code == 500
    assert (_membresias(usr_db), _refresh_tokens(usr_db, empresa.tenant_id)) == before


def test_logs_never_carry_emails_nor_names(client, headers, usr_db, caplog):
    empresa = _empresa(usr_db)
    caplog.set_level(logging.DEBUG)
    client.get(_ruta(empresa.tenant_id), headers=headers)
    _patch(client, headers, empresa.tenant_id, empresa.contador.usuario_id, False)
    _patch(client, headers, empresa.tenant_id, empresa.admin.usuario_id, False)
    _patch(client, headers, empresa.tenant_id, empresa.admin2.usuario_id, False)  # ultimo_admin
    texto = caplog.text
    for persona in (empresa.admin, empresa.admin2, empresa.contador):
        assert persona.email not in texto
        assert persona.nombre not in texto
    assert "argon2" not in texto


# --- Correcciones tras la revisión de T5 ----------------------------------------------------


def _esperando(db: AccesoDb) -> bool:
    """Hay en la base alguna petición esperando un candado (de fila o consultivo)."""
    (row,) = filas(
        db,
        "select exists(select 1 from pg_locks l join pg_stat_activity a on a.pid = l.pid "
        "where not l.granted and a.datname = current_database()) as e",
    )
    return row["e"]


def _sin_refresh_vivo(db: AccesoDb, tenant_id, usuario_id) -> bool:
    (row,) = filas(
        db,
        "select count(*) as n from refresh_token r join membresia m on m.id = r.membresia_id "
        "where r.tenant_id = :t and m.usuario_id = :u and r.revocado_en is null",
        {"t": tenant_id, "u": usuario_id},
    )
    return row["n"] == 0


def _carrera(usr_app, usr_db, headers, empresa, persona, accion_a, monkeypatch) -> dict:
    """Hilo A (``accion_a``: login o refresh del tenant) se detiene en su primera llamada a
    ``_load_current_user``, ya dentro de su transacción; hilo B desactiva a ``persona``;
    cuando B espera un candado, A sigue. Devuelve las dos respuestas."""
    from app.auth import service as auth_service

    original = auth_service._load_current_user
    dentro, seguir = threading.Event(), threading.Event()

    def pausada(*args, **kwargs):
        if not dentro.is_set():
            dentro.set()
            assert seguir.wait(30)
        return original(*args, **kwargs)

    monkeypatch.setattr(auth_service, "_load_current_user", pausada)
    resultado: dict = {}

    def hilo_a() -> None:
        resultado["a"] = accion_a(usr_app.test_client(use_cookies=False))

    def hilo_b() -> None:
        cliente = usr_app.test_client(use_cookies=False)
        resultado["b"] = _patch(cliente, headers, empresa.tenant_id, persona.usuario_id, False)

    a = threading.Thread(target=hilo_a)
    a.start()
    assert dentro.wait(20)
    b = threading.Thread(target=hilo_b)
    b.start()
    limite = time.monotonic() + 20
    while not _esperando(usr_db):
        assert b.is_alive() and time.monotonic() < limite, resultado
        time.sleep(0.05)
    seguir.set()
    a.join(timeout=30)
    b.join(timeout=30)
    assert not a.is_alive() and not b.is_alive()
    monkeypatch.undo()
    return resultado


def test_a_refresh_rotating_while_deactivating_leaves_no_live_refresh(
    usr_app, usr_db, headers, monkeypatch
):
    # Security medio 1: A rota el refresh (marca el viejo y va a insertar el sucesor) y B
    # desactiva a la vez. Al terminar, ninguna fila de esa membresía queda sin revocar.
    empresa = _empresa(usr_db)
    persona = empresa.contador
    sesion = _tenant_login(usr_app.test_client(use_cookies=False), persona.email)
    assert sesion.status_code == 200
    cookie = _cookie(sesion)
    resultado = _carrera(
        usr_app, usr_db, headers, empresa, persona, lambda c: _refresh(c, cookie), monkeypatch
    )

    assert resultado["b"].status_code == 200, resultado["b"].get_json()
    assert resultado["a"].status_code in (200, 401)
    assert _activa(usr_db, empresa.tenant_id, persona.usuario_id) is False
    assert _sin_refresh_vivo(usr_db, empresa.tenant_id, persona.usuario_id)
    # Ni el sucesor (si salió) ni la cookie vieja reviven al reactivar.
    client = usr_app.test_client(use_cookies=False)
    assert _patch(client, headers, empresa.tenant_id, persona.usuario_id, True).status_code == 200
    cookies = [cookie]
    if resultado["a"].status_code == 200:
        cookies.append(_cookie(resultado["a"]))
    for valor in cookies:
        assert _refresh(client, valor).status_code == 401


def test_a_login_while_deactivating_leaves_no_live_refresh(usr_app, usr_db, headers, monkeypatch):
    # Igual con el login (familia nueva): o entra antes y B la revoca, o no entra.
    empresa = _empresa(usr_db)
    persona = empresa.contador
    resultado = _carrera(
        usr_app,
        usr_db,
        headers,
        empresa,
        persona,
        lambda c: _tenant_login(c, persona.email),
        monkeypatch,
    )

    assert resultado["b"].status_code == 200, resultado["b"].get_json()
    assert resultado["a"].status_code in (200, 401)
    assert _sin_refresh_vivo(usr_db, empresa.tenant_id, persona.usuario_id)
    client = usr_app.test_client(use_cookies=False)
    assert _patch(client, headers, empresa.tenant_id, persona.usuario_id, True).status_code == 200
    if resultado["a"].status_code == 200:
        assert _refresh(client, _cookie(resultado["a"])).status_code == 401


def test_a_busy_membership_lock_waits_and_fails_with_503(client, headers, usr_db):
    # Security medio 2: con el candado del tenant tomado por otra transacción, la función
    # espera su lock_timeout (5 s) y falla con 503 servicio_no_disponible sin cambiar nada.
    empresa = _empresa(usr_db)
    _sembrar_refresh(usr_db, empresa.tenant_id, empresa.contador.usuario_id)
    before = (_membresias(usr_db), _counts(usr_db), _refresh_tokens(usr_db, empresa.tenant_id))
    with usr_db.migrator.connect() as conn:
        tx = conn.begin()
        conn.execute(
            text("select pg_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": f"{CLAVE_CANDADO}{empresa.tenant_id}"},
        )
        resultado: dict = {}

        def desactivar() -> None:
            inicio = time.monotonic()
            resultado["r"] = _patch(
                client, headers, empresa.tenant_id, empresa.contador.usuario_id, False
            )
            resultado["espera"] = time.monotonic() - inicio

        hilo = threading.Thread(target=desactivar)
        hilo.start()
        hilo.join(timeout=LOCK_TIMEOUT_SEGUNDOS + 10)
        vivo = hilo.is_alive()
        tx.rollback()  # suelta el candado: sin lock_timeout, el hilo terminaría aquí
        hilo.join(timeout=30)
    assert not vivo, "la función no aplicó su lock_timeout"
    response, espera = resultado["r"], resultado["espera"]
    assert response.status_code == 503, response.get_json()
    assert error_code(response) == "servicio_no_disponible"
    assert response.headers["Retry-After"].isdigit()
    assert LOCK_TIMEOUT_SEGUNDOS - 0.5 <= espera < LOCK_TIMEOUT_SEGUNDOS + 10
    assert (
        _membresias(usr_db),
        _counts(usr_db),
        _refresh_tokens(usr_db, empresa.tenant_id),
    ) == before


def test_audit_rows_carry_only_ids_and_an_idempotent_patch_writes_none(
    client, headers, usr_db, dev
):
    empresa = _empresa(usr_db)
    persona = empresa.contador
    for activa in (False, False, True, True):  # dos cambios reales y dos repetidos
        response = _patch(client, headers, empresa.tenant_id, persona.usuario_id, activa)
        assert response.status_code == 200
        assert response.get_json() == {"id": str(persona.usuario_id), "activa": activa}
    rows = filas(
        usr_db,
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
            "accion": accion,
            "resultado": "ok",
            "tenant_id": empresa.tenant_id,
            "objeto_id": persona.usuario_id,
        }
        for accion in ("usuario_desactivado", "usuario_reactivado")
    ]


def test_repeating_the_deactivation_of_an_inactive_admin_is_not_ultimo_admin(
    client, headers, usr_db
):
    # Con un solo admin activo, repetir la desactivación del otro (ya inactivo) es
    # idempotente: 200, sin ultimo_admin y sin auditoría nueva.
    empresa = _empresa(usr_db)
    primero = _patch(client, headers, empresa.tenant_id, empresa.admin2.usuario_id, False)
    assert primero.status_code == 200
    auditoria_antes = _auditoria(usr_db, empresa.tenant_id)
    before = _membresias(usr_db)
    response = _patch(client, headers, empresa.tenant_id, empresa.admin2.usuario_id, False)
    assert response.status_code == 200, response.get_json()
    assert response.get_json() == {"id": str(empresa.admin2.usuario_id), "activa": False}
    assert _membresias(usr_db) == before
    assert _auditoria(usr_db, empresa.tenant_id) == auditoria_antes


def test_in_an_inactive_company_reactivating_is_409_and_a_foreign_user_is_404(
    client, headers, usr_db
):
    empresa = _empresa(usr_db, activa=False)
    otra = _empresa(usr_db)
    ejecutar(
        usr_db,
        "update membresia set activa = false where usuario_id = :u",
        {"u": empresa.contador.usuario_id},
    )
    before = (_membresias(usr_db), _counts(usr_db))
    reactivar = _patch(client, headers, empresa.tenant_id, empresa.contador.usuario_id, True)
    assert reactivar.status_code == 409
    assert error_code(reactivar) == "empresa_inactiva"
    # 404 de usuario va antes que 409 empresa_inactiva (orden del contrato).
    for usuario in (otra.contador.usuario_id, uuid.uuid4()):
        for activa in (False, True):
            ajeno = _patch(client, headers, empresa.tenant_id, usuario, activa)
            assert ajeno.status_code == 404, usuario
            assert error_code(ajeno) == "no_encontrado"
    assert (_membresias(usr_db), _counts(usr_db)) == before


def test_a_user_with_two_memberships(client, headers, usr_db):
    # Límite conocido (H-2/Q6): reactivar en X con la membresía de Y activa queda permitido;
    # el login falla cerrado con dos membresías activas. La lista de X no muestra nada de Y.
    x = _empresa(usr_db)
    y = _empresa(usr_db)
    persona = _persona("contador")
    with usr_db.migrator.begin() as conn:
        conn.execute(
            text("insert into usuario (id, email, nombre, password_hash) values (:u, :e, :n, :h)"),
            {
                "u": persona.usuario_id,
                "e": persona.email,
                "n": persona.nombre,
                "h": HASHER.hash(PASSWORD),
            },
        )
        for tenant, rol in ((x.tenant_id, "contador"), (y.tenant_id, "admin")):
            conn.execute(
                text("insert into membresia (tenant_id, usuario_id, rol) values (:t, :u, :r)"),
                {"t": tenant, "u": persona.usuario_id, "r": rol},
            )
    fallido = _tenant_login(client, persona.email)
    assert fallido.status_code == 401
    assert error_code(fallido) == "credenciales_invalidas"

    assert _patch(client, headers, x.tenant_id, persona.usuario_id, False).status_code == 200
    assert _activa(usr_db, y.tenant_id, persona.usuario_id) is True
    assert _tenant_login(client, persona.email).status_code == 200  # solo Y activa

    reactivar = _patch(client, headers, x.tenant_id, persona.usuario_id, True)
    assert reactivar.status_code == 200, reactivar.get_json()
    fallido = _tenant_login(client, persona.email)
    assert fallido.status_code == 401
    assert error_code(fallido) == "credenciales_invalidas"

    lista = client.get(_ruta(x.tenant_id), headers=headers)
    assert lista.status_code == 200
    usuarios = lista.get_json()["usuarios"]
    assert [u for u in usuarios if u["id"] == str(persona.usuario_id)] == [
        {
            "id": str(persona.usuario_id),
            "nombre": persona.nombre,
            "email": persona.email,
            "rol": "contador",
            "activa": True,
            "debe_cambiar_password": False,
        }
    ]
    texto = lista.get_data(as_text=True)
    assert str(y.tenant_id) not in texto
    for ajeno in (y.admin, y.admin2, y.contador):
        assert str(ajeno.usuario_id) not in texto
        assert ajeno.email not in texto
    # El cambio en X no tocó la membresía de Y.
    (fila_y,) = filas(
        usr_db,
        "select rol, activa from membresia where tenant_id = :t and usuario_id = :u",
        {"t": y.tenant_id, "u": persona.usuario_id},
    )
    assert fila_y == {"rol": "admin", "activa": True}


def _sembrar_conteo(db: AccesoDb, empresa: Empresa) -> uuid.UUID:
    """Una sesión de conteo abierta por admin2 y una verificación del contador."""
    ids = {n: uuid.uuid4() for n in ("sede", "sala", "cat", "act", "sesion")}
    params = {**ids, "t": empresa.tenant_id}
    with db.migrator.begin() as conn:
        conn.execute(
            text(
                "insert into ubicacion (id, tenant_id, nombre, nombre_clave, tipo, padre_id) "
                "values (:sede, :t, 'Sede', 'sede', 'sede', null), "
                "(:sala, :t, 'Sala', 'sala', 'sala', :sede)"
            ),
            params,
        )
        conn.execute(
            text(
                "insert into categoria (id, tenant_id, nombre, nombre_clave) "
                "values (:cat, :t, 'Cat', 'cat')"
            ),
            params,
        )
        conn.execute(
            text(
                "insert into activo (id, tenant_id, codigo, nombre, categoria_id, ubicacion_id, "
                "precio_compra, creado_por) values (:act, :t, 'AC-1', 'Autoclave', :cat, :sala, "
                "100, :p)"
            ),
            {**params, "p": empresa.admin.usuario_id},
        )
        conn.execute(
            text(
                "insert into sesion_conteo (id, tenant_id, nombre, fecha_corte, abierta_por) "
                "values (:sesion, :t, 'Conteo', date '2026-11-30', :p)"
            ),
            {**params, "p": empresa.admin2.usuario_id},
        )
        conn.execute(
            text(
                "insert into verificacion (id, tenant_id, sesion_id, activo_id, "
                "ubicacion_esperada_id, ubicacion_encontrada_id, estado_fisico, "
                "precio_al_contar, categoria_al_contar, verificado_por) "
                "values (gen_random_uuid(), :t, :sesion, :act, :sala, :sala, 'ok', 100, :cat, :p)"
            ),
            {**params, "p": empresa.contador.usuario_id},
        )
    return ids["sesion"]


def test_deactivating_keeps_counts_sessions_and_author_names(client, headers, usr_app, usr_db):
    from app.conteo.service import _autor
    from app.db import tenant_session

    empresa = _empresa(usr_db)
    sesion_id = _sembrar_conteo(usr_db, empresa)

    def conteo() -> dict[str, list[dict]]:
        return {
            "verificacion": filas(
                usr_db,
                "select * from verificacion where tenant_id = :t order by id",
                {"t": empresa.tenant_id},
            ),
            "sesion_conteo": filas(
                usr_db,
                "select * from sesion_conteo where tenant_id = :t order by id",
                {"t": empresa.tenant_id},
            ),
        }

    antes = conteo()
    assert [len(antes["verificacion"]), len(antes["sesion_conteo"])] == [1, 1]
    assert antes["sesion_conteo"][0]["id"] == sesion_id
    for persona in (empresa.contador, empresa.admin2):
        response = _patch(client, headers, empresa.tenant_id, persona.usuario_id, False)
        assert response.status_code == 200
    assert conteo() == antes
    with usr_app.app_context():
        with tenant_session(empresa.tenant_id) as session:
            for persona in (empresa.contador, empresa.admin2):
                assert _autor(session, persona.usuario_id) == {
                    "id": str(persona.usuario_id),
                    "nombre": persona.nombre,
                }


# --- Segunda ronda de correcciones de T5 (security-reviewer) --------------------------------
#
# El candado compartido de login, refresh, invitación y cambio de contraseña
# (``bloquear_membresias``) lleva su propio ``lock_timeout`` corto: contra un candado
# exclusivo retenido responde ``503`` acotado en vez de colgar; el valor previo de
# ``lock_timeout`` se restaura en la transacción. El cambio de contraseña toma el candado y,
# si la cuenta dejó de estar activa, revierte todo con ``401``. Interbloqueos y fallos de
# serialización del ``PATCH`` y del cambio son ``503`` genéricos.

LOCK_TIMEOUT_TENANT_SEGUNDOS = 3
NUEVA = "Clave-Nueva-Sintetica-2026"
CAMBIAR = "/auth/cambiar-contrasena"
SECRETO_BASE = "detalle-interno-de-la-base"


class _CandadoExclusivo:
    """Retiene en exclusivo el candado consultivo de membresías de ``tenant_id``."""

    def __init__(self, db: AccesoDb, tenant_id) -> None:
        self._db, self._tenant_id = db, tenant_id

    def __enter__(self) -> "_CandadoExclusivo":
        self._conn = self._db.migrator.connect()
        self._tx = self._conn.begin()
        self._conn.execute(
            text("select pg_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": f"{CLAVE_CANDADO}{self._tenant_id}"},
        )
        return self

    def __exit__(self, *exc) -> None:
        self._tx.rollback()
        self._conn.close()


def _en_hilo(funcion, espera: float) -> tuple[threading.Thread, dict]:
    resultado: dict = {}

    def correr() -> None:
        inicio = time.monotonic()
        resultado["r"] = funcion()
        resultado["espera"] = time.monotonic() - inicio

    hilo = threading.Thread(target=correr)
    hilo.start()
    hilo.join(timeout=espera)
    return hilo, resultado


def _assert_503(response) -> None:
    assert response.status_code == 503, response.get_json()
    assert error_code(response) == "servicio_no_disponible"
    assert response.headers["Retry-After"].isdigit()
    assert SECRETO_BASE not in response.get_data(as_text=True)


def _cuenta(db: AccesoDb, usuario_id) -> dict:
    (row,) = filas(
        db,
        "select password_hash, debe_cambiar_password, sesiones_validas_desde "
        "from usuario where id = :u",
        {"u": usuario_id},
    )
    return row


def _refresh_de(db: AccesoDb, usuario_id) -> list[dict]:
    return filas(
        db,
        "select r.id, r.usado_en, r.revocado_en from refresh_token r "
        "join membresia m on m.id = r.membresia_id where m.usuario_id = :u order by r.id",
        {"u": usuario_id},
    )


def _cambiar(client, access_token: str, actual: str = PASSWORD):
    return client.post(
        CAMBIAR,
        json={"actual": actual, "nueva": NUEVA, "confirmacion": NUEVA},
        headers={"Authorization": f"Bearer {access_token}"},
    )


@pytest.mark.parametrize("accion", ["login", "refresh"])
def test_login_and_refresh_against_a_held_membership_lock_fail_fast_with_503(
    usr_app, usr_db, accion
):
    # (a) Con el candado exclusivo retenido (la consola a medias), login y refresh esperan
    # como mucho su lock_timeout corto y responden 503 genérico; no cuelgan.
    empresa = _empresa(usr_db)
    persona = empresa.contador
    sesion = _tenant_login(usr_app.test_client(use_cookies=False), persona.email)
    assert sesion.status_code == 200
    cookie = _cookie(sesion)
    before = _refresh_de(usr_db, persona.usuario_id)
    client = usr_app.test_client(use_cookies=False)

    def pedir():
        if accion == "login":
            return _tenant_login(client, persona.email)
        return _refresh(client, cookie)

    with _CandadoExclusivo(usr_db, empresa.tenant_id):
        hilo, resultado = _en_hilo(pedir, LOCK_TIMEOUT_TENANT_SEGUNDOS + 10)
        vivo = hilo.is_alive()
    hilo.join(timeout=30)
    assert not vivo, "el candado compartido no aplicó su lock_timeout"
    _assert_503(resultado["r"])
    assert (
        LOCK_TIMEOUT_TENANT_SEGUNDOS - 0.5 <= resultado["espera"] < LOCK_TIMEOUT_TENANT_SEGUNDOS + 5
    )
    # Nada cambió: ni refresh nuevo ni el viejo marcado; la cookie sigue sirviendo.
    assert _refresh_de(usr_db, persona.usuario_id) == before
    assert _refresh(client, cookie).status_code == 200


def test_accepting_an_invitation_against_a_held_membership_lock_is_503(usr_app, usr_db):
    # (a) La invitación emite la sesión con el mismo candado (issue_session): 503, no 500.
    client = usr_app.test_client(use_cookies=False)
    email = f"invitado.{uuid.uuid4().hex[:10]}@ejemplo.test"
    creada = client.post(
        "/invitaciones",
        json={"email": email, "rol": "contador"},
        headers=bearer(ADMIN_A, TENANT_A),
    )
    assert creada.status_code == 201, creada.get_json()
    token = creada.get_json()["enlace"].removeprefix("/invitacion#")
    body = {"token": token, "nombre": "Invitada Sintética", "password": NUEVA}
    with _CandadoExclusivo(usr_db, TENANT_A):
        hilo, resultado = _en_hilo(
            lambda: client.post("/invitaciones/aceptar", json=body),
            LOCK_TIMEOUT_TENANT_SEGUNDOS + 10,
        )
        vivo = hilo.is_alive()
    hilo.join(timeout=30)
    assert not vivo
    _assert_503(resultado["r"])
    # La cuenta quedó creada (commit previo): entra con el login.
    assert _tenant_login(client, email, NUEVA).status_code == 200


def _pool_sano(usr_app, valor_por_defecto: str) -> None:
    """Todas las conexiones devueltas al pool de la app: GUC vacías y lock_timeout intacto."""
    from app.db import _get_database

    with usr_app.app_context():
        engine = _get_database().engine
        conexiones = [engine.connect() for _ in range(max(engine.pool.checkedin(), 1))]
        try:
            for conn in conexiones:
                assert conn.scalar(text("show lock_timeout")) == valor_por_defecto
                for guc in ("app.tenant_id", *OWNER_GUCS):
                    valor = conn.scalar(text("select current_setting(:g, true)"), {"g": guc})
                    assert valor in (None, ""), guc
        finally:
            for conn in conexiones:
                conn.close()


def test_gucs_and_lock_timeout_are_clean_after_the_55p03(usr_app, usr_db, app_engine):
    # (g) Tras el 503 por 55P03, la conexión vuelve al pool sin tenant ni lock_timeout.
    with app_engine.connect() as conn:
        por_defecto = conn.scalar(text("show lock_timeout"))
    empresa = _empresa(usr_db)
    client = usr_app.test_client(use_cookies=False)
    with _CandadoExclusivo(usr_db, empresa.tenant_id):
        hilo, resultado = _en_hilo(
            lambda: _tenant_login(client, empresa.contador.email),
            LOCK_TIMEOUT_TENANT_SEGUNDOS + 10,
        )
    hilo.join(timeout=30)
    _assert_503(resultado["r"])
    _pool_sano(usr_app, por_defecto)


def test_the_shared_lock_restores_the_previous_lock_timeout(usr_app, usr_db, app_engine):
    # (c) SET LOCAL no se filtra: dentro de la transacción vuelve el valor previo (también
    # uno fijado antes por quien llama) y fuera de ella el de la sesión.
    from sqlalchemy import func, select

    from app.auth.service import bloquear_membresias
    from app.db import tenant_session

    with app_engine.connect() as conn:
        por_defecto = conn.scalar(text("show lock_timeout"))
    empresa = _empresa(usr_db)
    with usr_app.app_context():
        with tenant_session(empresa.tenant_id) as session:
            antes = session.scalar(select(func.current_setting("lock_timeout")))
            bloquear_membresias(session, empresa.tenant_id)
            assert session.scalar(select(func.current_setting("lock_timeout"))) == antes
            session.execute(select(func.set_config("lock_timeout", "7s", True)))
            bloquear_membresias(session, empresa.tenant_id)
            assert session.scalar(select(func.current_setting("lock_timeout"))) == "7s"
    assert antes == por_defecto
    _pool_sano(usr_app, por_defecto)


def test_changing_the_password_while_deactivating_is_401_and_leaves_no_live_refresh(
    usr_app, usr_db, app_engine, dev
):
    # (b) La consola desactiva (candado exclusivo, sin confirmar) y el usuario cambia su
    # contraseña a la vez: el cambio espera el candado, ve la membresía inactiva y responde
    # 401 sin cambiar nada; ninguna fila de refresh de esa membresía queda viva.
    empresa = _empresa(usr_db)
    persona = empresa.contador
    sesion = _tenant_login(usr_app.test_client(use_cookies=False), persona.email)
    assert sesion.status_code == 200
    access = sesion.get_json()["access_token"]
    cuenta = _cuenta(usr_db, persona.usuario_id)
    client = usr_app.test_client(use_cookies=False)
    resultado: dict = {}

    def cambiar() -> None:
        resultado["r"] = _cambiar(client, access)

    with app_engine.connect() as conn:
        tx = conn.begin()
        params = {"d": dev.id, "t": empresa.tenant_id, "u": persona.usuario_id, "a": False}
        assert tuple(conn.execute(text(ESTADO), params).one()) == (False, True)
        hilo = threading.Thread(target=cambiar)
        hilo.start()
        limite = time.monotonic() + 20
        while not _esperando(usr_db):
            assert hilo.is_alive() and time.monotonic() < limite, resultado
            time.sleep(0.05)
        tx.commit()
    hilo.join(timeout=30)
    assert not hilo.is_alive()

    response = resultado["r"]
    assert response.status_code == 401, response.get_json()
    assert _activa(usr_db, empresa.tenant_id, persona.usuario_id) is False
    assert _sin_refresh_vivo(usr_db, empresa.tenant_id, persona.usuario_id)
    assert _cuenta(usr_db, persona.usuario_id) == cuenta


def test_an_account_that_stops_being_active_during_the_change_rolls_back_with_401(
    usr_app, usr_db, monkeypatch
):
    # (b) Si tras la función la cuenta ya no se puede cargar (p. ej. la empresa se desactivó
    # entretanto), se revierte todo con 401, no un 500.
    from app.auth import service as auth_service

    empresa = _empresa(usr_db)
    persona = empresa.contador
    sesion = _tenant_login(usr_app.test_client(use_cookies=False), persona.email)
    access = sesion.get_json()["access_token"]
    cuenta = _cuenta(usr_db, persona.usuario_id)
    refresh_antes = _refresh_de(usr_db, persona.usuario_id)
    original = auth_service._load_current_user
    llamadas = {"n": 0}

    def segunda_none(*args, **kwargs):
        llamadas["n"] += 1
        return None if llamadas["n"] >= 2 else original(*args, **kwargs)

    monkeypatch.setattr(auth_service, "_load_current_user", segunda_none)
    response = _cambiar(usr_app.test_client(use_cookies=False), access)
    monkeypatch.undo()
    assert llamadas["n"] >= 2
    assert response.status_code == 401, response.get_json()
    assert _cuenta(usr_db, persona.usuario_id) == cuenta
    assert _refresh_de(usr_db, persona.usuario_id) == refresh_antes


def test_revocation_that_never_settles_fails_closed_with_503(client, headers, usr_db):
    # (d) Si tras 10 pasadas la revocación aún afecta filas, la función falla cerrado: 503
    # sin desactivar ni auditar. Un disparador de prueba repone un refresh vivo por cada uno
    # revocado, así ninguna pasada queda en cero.
    empresa = _empresa(usr_db)
    persona = empresa.contador
    _sembrar_refresh(usr_db, empresa.tenant_id, persona.usuario_id)
    (membresia,) = filas(
        usr_db,
        "select id from membresia where tenant_id = :t and usuario_id = :u",
        {"t": empresa.tenant_id, "u": persona.usuario_id},
    )
    membresia_id = uuid.UUID(str(membresia["id"]))
    nombre = f"t5_reponer_{membresia_id.hex[:12]}"
    ejecutar(
        usr_db,
        f"create function public.{nombre}() returns trigger language plpgsql "  # noqa: S608
        "security definer set search_path = pg_catalog, public as $$ begin "
        "insert into public.refresh_token (tenant_id, membresia_id, familia_id, token_hash, "
        "expira_en) values (new.tenant_id, new.membresia_id, new.familia_id, "
        "sha256(convert_to(gen_random_uuid()::text, 'UTF8')), now() + interval '7 days'); "
        "return null; end $$",
    )
    ejecutar(
        usr_db,
        f"create trigger {nombre} after update of revocado_en on public.refresh_token "
        "for each row when (old.revocado_en is null and new.revocado_en is not null "
        f"and new.membresia_id = '{membresia_id}'::uuid) execute function public.{nombre}()",
    )
    try:
        before = (_membresias(usr_db), _counts(usr_db), _refresh_tokens(usr_db, empresa.tenant_id))
        response = _patch(client, headers, empresa.tenant_id, persona.usuario_id, False)
        _assert_503(response)
        assert _activa(usr_db, empresa.tenant_id, persona.usuario_id) is True
        assert _auditoria(usr_db, empresa.tenant_id) == []
        assert (
            _membresias(usr_db),
            _counts(usr_db),
            _refresh_tokens(usr_db, empresa.tenant_id),
        ) == before
    finally:
        ejecutar(usr_db, f"drop trigger {nombre} on public.refresh_token")
        ejecutar(usr_db, f"drop function public.{nombre}()")


def _error_db(sqlstate: str) -> DBAPIError:
    from psycopg import errors as pg_errors

    clase = {"40P01": pg_errors.DeadlockDetected, "40001": pg_errors.SerializationFailure}
    return DBAPIError("select 1", {}, clase[sqlstate](SECRETO_BASE))


@pytest.mark.parametrize("sqlstate", ["40P01", "40001"])
def test_a_deadlock_or_serialization_failure_in_the_patch_is_503(
    client, headers, usr_db, monkeypatch, sqlstate
):
    # (e) Interbloqueo o fallo de serialización (unitaria: no se provoca un 40P01 de forma
    # determinista): 503 genérico sin el mensaje de la base, sin cambios ni auditoría.
    from app.plataforma.modulos.usuarios import service as usuarios_service

    empresa = _empresa(usr_db)

    def falla(*args, **kwargs):
        raise _error_db(sqlstate)

    monkeypatch.setattr(usuarios_service, "plataforma_cambiar_estado_membresia", falla)
    before = (_membresias(usr_db), _counts(usr_db))
    response = _patch(client, headers, empresa.tenant_id, empresa.contador.usuario_id, False)
    _assert_503(response)
    assert (_membresias(usr_db), _counts(usr_db)) == before
    assert _auditoria(usr_db, empresa.tenant_id) == []


@pytest.mark.parametrize("sqlstate", ["40P01", "40001"])
def test_a_deadlock_or_serialization_failure_in_the_password_change_is_503(
    usr_app, usr_db, monkeypatch, sqlstate
):
    from app.auth import service as auth_service

    empresa = _empresa(usr_db)
    persona = empresa.contador
    sesion = _tenant_login(usr_app.test_client(use_cookies=False), persona.email)
    access = sesion.get_json()["access_token"]
    cuenta = _cuenta(usr_db, persona.usuario_id)
    refresh_antes = _refresh_de(usr_db, persona.usuario_id)

    def falla(*args, **kwargs):
        raise _error_db(sqlstate)

    monkeypatch.setattr(auth_service, "cambiar_password_propio", falla)
    response = _cambiar(usr_app.test_client(use_cookies=False), access)
    _assert_503(response)
    assert _cuenta(usr_db, persona.usuario_id) == cuenta
    assert _refresh_de(usr_db, persona.usuario_id) == refresh_antes


def test_tenant_b_logins_and_refreshes_are_not_blocked_while_tenant_a_is_locked(usr_app, usr_db):
    # (f) El candado es por tenant: mientras la consola retiene el de A, B entra y rota.
    empresa_a, empresa_b = _empresa(usr_db), _empresa(usr_db)
    client = usr_app.test_client(use_cookies=False)
    sesion = _tenant_login(client, empresa_b.contador.email)
    assert sesion.status_code == 200
    cookie = _cookie(sesion)
    with _CandadoExclusivo(usr_db, empresa_a.tenant_id):
        hilo, resultado = _en_hilo(
            lambda: (
                _tenant_login(client, empresa_b.admin.email),
                _refresh(client, cookie),
            ),
            LOCK_TIMEOUT_TENANT_SEGUNDOS * 2 + 10,
        )
        vivo = hilo.is_alive()
    hilo.join(timeout=30)
    assert not vivo
    entrada, rotacion = resultado["r"]
    assert entrada.status_code == 200, entrada.get_json()
    assert rotacion.status_code == 200, rotacion.get_json()
    assert resultado["espera"] < LOCK_TIMEOUT_TENANT_SEGUNDOS - 0.5


def test_a_password_change_committing_while_deactivating_leaves_no_live_refresh(
    usr_app, usr_db, headers, monkeypatch
):
    # (b) Orden inverso: el cambio ya insertó su familia nueva (sin confirmar) y la consola
    # desactiva a la vez. Con el candado compartido la consola espera al cambio y su
    # revocación ve la familia nueva; sin él, la revocación esperaría solo las filas viejas y
    # la familia nueva quedaría viva en una membresía inactiva.
    from app.auth import service as auth_service

    empresa = _empresa(usr_db)
    persona = empresa.contador
    sesion = _tenant_login(usr_app.test_client(use_cookies=False), persona.email)
    assert sesion.status_code == 200
    access = sesion.get_json()["access_token"]
    original = auth_service.emitir_acceso
    dentro, seguir = threading.Event(), threading.Event()

    def pausada(*args, **kwargs):
        if not dentro.is_set():
            dentro.set()
            assert seguir.wait(30)
        return original(*args, **kwargs)

    monkeypatch.setattr(auth_service, "emitir_acceso", pausada)
    resultado: dict = {}

    def hilo_a() -> None:
        resultado["a"] = _cambiar(usr_app.test_client(use_cookies=False), access)

    def hilo_b() -> None:
        cliente = usr_app.test_client(use_cookies=False)
        resultado["b"] = _patch(cliente, headers, empresa.tenant_id, persona.usuario_id, False)

    a = threading.Thread(target=hilo_a)
    a.start()
    assert dentro.wait(20)
    b = threading.Thread(target=hilo_b)
    b.start()
    limite = time.monotonic() + 20
    while not _esperando(usr_db):
        assert b.is_alive() and time.monotonic() < limite, resultado
        time.sleep(0.05)
    seguir.set()
    a.join(timeout=30)
    b.join(timeout=30)
    assert not a.is_alive() and not b.is_alive()
    monkeypatch.undo()

    assert resultado["a"].status_code == 200, resultado["a"].get_json()
    assert resultado["b"].status_code == 200, resultado["b"].get_json()
    assert _activa(usr_db, empresa.tenant_id, persona.usuario_id) is False
    assert _sin_refresh_vivo(usr_db, empresa.tenant_id, persona.usuario_id)
    client = usr_app.test_client(use_cookies=False)
    assert _patch(client, headers, empresa.tenant_id, persona.usuario_id, True).status_code == 200
    assert _refresh(client, _cookie(resultado["a"])).status_code == 401
