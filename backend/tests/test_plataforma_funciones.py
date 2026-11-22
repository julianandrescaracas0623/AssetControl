"""Funciones de Empresas de la consola y ``tenant.activo`` en el login (spec 017, T3a).

Comportamiento en base de la migración ``0018_funciones_plataforma`` con el rol de la
aplicación (sin ``BYPASSRLS``) sobre la base temporal de ``acceso_db`` (tenants A y B):

- A5/R36: cada ``acceso.plataforma_*`` con un desarrollador inexistente, inactivo o con el
  id de un usuario de clínica falla sin devolver filas ni escribir.
- R21: la lista devuelve solo identidad y conteos.
- R16/R18/R20/A7/A8: alta atómica (tenant + usuario con ``debe_cambiar_password`` +
  membresía admin + ficha ``empresa`` sin logo, sin invitación); ``empresa_existente``,
  ``email_en_uso``, hash o ficha inválidos: cero filas nuevas.
- R22/A9 (SQL y login): desactivar y reactivar sin tocar otra fila; ``buscar_login`` no
  devuelve membresías de un tenant inactivo; el login de la 002 da ``401``.
- Privilegios nuevos de la aplicación: no lee ``tenant.desactivado_*``; solo audita sus
  acciones (nunca las del operador).
- Las funciones de ``app.db`` usan el desarrollador de la ``plataforma_session``.

Datos sintéticos (``@ejemplo.test``).
"""

import uuid
from collections.abc import Iterator

import argon2
import pytest
from acceso_db import ADMIN_A, PASSWORD, TENANT_A, TENANT_B, AccesoDb, temporary_acceso_db
from plataforma_db import HIGH_LIMITS, Dev, filas, nuevo_dev, sembrar_dev
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from app.auth.credentials import ARGON2_TEST_PARAMS
from app.db import (
    FichaEmpresa,
    PlataformaFuncionError,
    plataforma_cambiar_estado_tenant,
    plataforma_crear_tenant,
    plataforma_listar_tenants,
    plataforma_session,
    tenant_session,
)

HASHER = argon2.PasswordHasher.from_parameters(ARGON2_TEST_PARAMS)
ADMIN_PASSWORD = "Clave-Inicial-Sintetica-2026"
INSUFFICIENT_PRIVILEGE = "42501"
TABLES = (
    "tenant",
    "usuario",
    "membresia",
    "empresa",
    "empresa_logo",
    "invitacion",
    "refresh_token",
    "desarrollador",
    "plataforma_refresh_token",
    "plataforma_auditoria",
)
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
)
LISTAR = "select * from acceso.plataforma_listar_tenants(:d)"
CREAR = (
    "select * from acceso.plataforma_crear_tenant(:d, :t, :nombre, :direccion, :nit, "
    ":telefono, :correo, :email, :admin, :h)"
)
ESTADO = "select acceso.plataforma_cambiar_estado_tenant(:d, :t, :a)"


@pytest.fixture(scope="module")
def db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("plat_funciones")


@pytest.fixture(scope="module")
def app_engine(db) -> Iterator[Engine]:
    engine = create_engine(db.app_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def dev(db) -> Dev:
    return sembrar_dev(db, nuevo_dev())


@pytest.fixture(scope="module")
def flask_app(db):
    from acceso_db import dispose, make_app

    from app.plataforma.config import PlataformaConfig

    app = make_app(db, rate_limits=HIGH_LIMITS, plataforma=PlataformaConfig.desde_texto("true", ""))
    try:
        yield app
    finally:
        dispose(app)


def _email(prefijo: str = "admin") -> str:
    return f"{prefijo}.{uuid.uuid4().hex[:10]}@ejemplo.test"


def _params(dev_id, **changes) -> dict:
    params = {
        "d": str(dev_id),
        "t": str(uuid.uuid4()),
        "nombre": "Clínica Sintética Nueva",
        "direccion": "Calle 1 # 2-3, Cartago",
        "nit": "900.123.456-7",
        "telefono": "3001234567",
        "correo": "contacto@ejemplo.test",
        "email": _email(),
        "admin": "Admin Sintético",
        "h": HASHER.hash(ADMIN_PASSWORD),
    }
    params.update(changes)
    return params


def _counts(db: AccesoDb) -> dict[str, int]:
    with db.migrator.connect() as conn:
        return {t: conn.scalar(text(f"select count(*) from {t}")) for t in TABLES}  # noqa: S608


def _expect_error(conn: Connection, sql: str, params: dict, sqlstate: str) -> str:
    nested = conn.begin_nested()
    with pytest.raises(DBAPIError) as excinfo:
        conn.execute(text(sql), params)
    nested.rollback()
    assert getattr(excinfo.value.orig, "sqlstate", None) == sqlstate, str(excinfo.value.orig)
    return str(excinfo.value.orig)


def _call_app(app_engine: Engine, sql: str, params: dict):
    with app_engine.begin() as conn:
        return conn.execute(text(sql), params).all()


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


def _tenant(db: AccesoDb, tenant_id) -> dict:
    return filas(
        db,
        "select activo, desactivado_en, desactivado_por, nombre from tenant where id = :t",
        {"t": tenant_id},
    )[0]


def _nuevo_tenant(app_engine: Engine, dev: Dev, **changes) -> tuple[uuid.UUID, uuid.UUID, dict]:
    params = _params(dev.id, **changes)
    (row,) = _call_app(app_engine, CREAR, params)
    return row.tenant_id, row.usuario_id, params


# --- A5 / R36: quien llama debe ser un desarrollador activo ------------------------------------


def _calls(tenant_id: uuid.UUID) -> list[tuple[str, dict]]:
    return [
        (LISTAR, {}),
        (CREAR, {k: v for k, v in _params(uuid.uuid4()).items() if k != "d"}),
        (ESTADO, {"t": str(tenant_id), "a": False}),
    ]


@pytest.mark.parametrize("caso", ["inexistente", "inactivo", "usuario_de_clinica"])
def test_every_function_rejects_a_caller_that_is_not_an_active_developer(db, app_engine, caso):
    if caso == "inexistente":
        caller = uuid.uuid4()
    elif caso == "inactivo":
        caller = sembrar_dev(db, nuevo_dev("inactivo"), activo=False).id
    else:
        caller = ADMIN_A.usuario_id  # un admin de clínica no es desarrollador
    before = _counts(db)
    estado_antes = _tenant(db, TENANT_A)
    for sql, params in _calls(TENANT_A):
        message = _fail_app(app_engine, sql, {**params, "d": str(caller)}, INSUFFICIENT_PRIVILEGE)
        assert "desarrollador_no_autorizado" in message
        assert str(caller) not in message
    assert _counts(db) == before
    assert _tenant(db, TENANT_A) == estado_antes


def test_inside_a_tenant_session_an_admin_cannot_use_the_functions(db, app_engine, flask_app):
    # Con app.tenant_id fijado (sesión de un admin), el id del admin no sirve de desarrollador.
    before = _counts(db)
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(TENANT_A)})
            for sql, params in _calls(TENANT_A):
                _expect_error(
                    conn, sql, {**params, "d": str(ADMIN_A.usuario_id)}, INSUFFICIENT_PRIVILEGE
                )
        finally:
            tx.rollback()
    assert _counts(db) == before
    # Y las funciones de app.db exigen una sesión de plataforma.
    with flask_app.app_context(), tenant_session(TENANT_A) as session:
        with pytest.raises(Exception, match="desarrollador"):
            plataforma_listar_tenants(session)


def test_null_arguments_do_nothing_because_the_functions_are_strict(db, app_engine, dev):
    before = _counts(db)
    for sql, params in _calls(TENANT_A):
        nulls = {**params, "d": str(dev.id), "t": None} if "t" in params else {"d": None}
        rows = _call_app(app_engine, sql, nulls)
        assert rows in ([], [(None,)]), sql
    assert _counts(db) == before


# --- plataforma_listar_tenants (R21) -----------------------------------------------------------


def test_listar_returns_only_identity_and_counts(db, app_engine, dev):
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            result = conn.execute(text(LISTAR), {"d": str(dev.id)})
            rows = {row.id: row for row in result.all()}
            assert list(result.keys()) == [
                "id",
                "nombre",
                "activo",
                "creado_en",
                "tiene_logo",
                "n_membresias_activas",
                "n_admins_activos",
            ]
            assert _gucs_empty(conn)
            # Lo que la función vio no queda abierto para la aplicación.
            assert conn.scalar(text("select count(*) from tenant")) == 0
            assert conn.scalar(text("select count(*) from membresia")) == 0
            assert conn.scalar(text("select count(*) from empresa")) == 0
        finally:
            tx.rollback()
    a, b = rows[TENANT_A], rows[TENANT_B]
    assert (a.nombre, a.activo, a.tiene_logo) == ("Clínica sintética A8", True, False)
    assert (a.n_membresias_activas, a.n_admins_activos) == (3, 2)
    assert (b.n_membresias_activas, b.n_admins_activos) == (2, 1)


def test_listar_counts_only_active_memberships_and_reports_the_logo(db, app_engine, dev):
    tenant_id, usuario_id, _ = _nuevo_tenant(app_engine, dev)
    contador = uuid.uuid4()
    logo = uuid.uuid4()
    with db.migrator.begin() as conn:
        conn.execute(
            text(
                "insert into usuario (id, email, nombre, password_hash) "
                "values (:u, :e, 'Contador', 'h')"
            ),
            {"u": contador, "e": _email("contador")},
        )
        conn.execute(
            text(
                "insert into membresia (tenant_id, usuario_id, rol, activa) "
                "values (:t, :u, 'contador', false)"
            ),
            {"t": tenant_id, "u": contador},
        )
        conn.execute(
            text(
                "insert into empresa_logo (id, tenant_id, clave, bytes, ancho, alto, subido_por) "
                "values (:l, :t, :c, 10, 10, 10, :u)"
            ),
            {"l": logo, "t": tenant_id, "c": f"logos/{tenant_id}/{logo}.png", "u": usuario_id},
        )
        conn.execute(
            text("update empresa set logo_id = :l where tenant_id = :t"),
            {"l": logo, "t": tenant_id},
        )
    rows = {r.id: r for r in _call_app(app_engine, LISTAR, {"d": str(dev.id)})}
    nuevo = rows[tenant_id]
    assert (nuevo.tiene_logo, nuevo.n_membresias_activas, nuevo.n_admins_activos) == (True, 1, 1)


# --- plataforma_crear_tenant (R16, R18, R20; A7, A8) -------------------------------------------


def test_crear_creates_tenant_admin_membership_and_ficha_in_one_call(db, app_engine, dev):
    before = _counts(db)
    with app_engine.connect() as conn:
        tx = conn.begin()
        params = _params(dev.id)
        result = conn.execute(text(CREAR), params)
        assert list(result.keys()) == ["tenant_id", "usuario_id"]
        (row,) = result.all()
        assert _gucs_empty(conn)
        tx.commit()
    tenant_id, usuario_id = row.tenant_id, row.usuario_id
    assert str(tenant_id) == params["t"]
    after = _counts(db)
    for table in ("tenant", "usuario", "membresia", "empresa"):
        assert after[table] == before[table] + 1, table
    for table in set(TABLES) - {"tenant", "usuario", "membresia", "empresa"}:
        assert after[table] == before[table], table  # sin invitación ni auditoría aquí
    assert _tenant(db, tenant_id) == {
        "activo": True,
        "desactivado_en": None,
        "desactivado_por": None,
        "nombre": params["nombre"],
    }
    (usuario,) = filas(
        db,
        "select email, nombre, password_hash, activo, debe_cambiar_password "
        "from usuario where id = :u",
        {"u": usuario_id},
    )
    assert usuario == {
        "email": params["email"],
        "nombre": params["admin"],
        "password_hash": params["h"],
        "activo": True,
        "debe_cambiar_password": True,
    }
    assert filas(
        db, "select tenant_id, rol, activa from membresia where usuario_id = :u", {"u": usuario_id}
    ) == [{"tenant_id": tenant_id, "rol": "admin", "activa": True}]
    (empresa,) = filas(
        db,
        "select nombre, direccion, nit, telefono, correo, logo_id, actualizada_por "
        "from empresa where tenant_id = :t",
        {"t": tenant_id},
    )
    assert empresa == {
        "nombre": params["nombre"],
        "direccion": params["direccion"],
        "nit": params["nit"],
        "telefono": params["telefono"],
        "correo": params["correo"],
        "logo_id": None,
        "actualizada_por": usuario_id,
    }


def test_crear_stores_missing_optional_fields_as_null(db, app_engine, dev):
    tenant_id, _, _ = _nuevo_tenant(app_engine, dev, nit="", telefono="", correo="")
    (empresa,) = filas(
        db, "select nit, telefono, correo from empresa where tenant_id = :t", {"t": tenant_id}
    )
    assert empresa == {"nit": None, "telefono": None, "correo": None}


def test_crear_allows_the_same_email_for_the_company_and_the_admin(db, app_engine, dev):
    email = _email("mismo")
    tenant_id, _, _ = _nuevo_tenant(app_engine, dev, email=email, correo=email)  # Q-A3
    assert filas(db, "select correo from empresa where tenant_id = :t", {"t": tenant_id}) == [
        {"correo": email}
    ]


def test_crear_with_the_same_id_is_empresa_existente_and_creates_nothing(db, app_engine, dev):
    tenant_id, _, params = _nuevo_tenant(app_engine, dev)
    before = _counts(db)
    for email in (params["email"], _email("otro")):  # doble clic, o mismo id con otro correo
        message = _fail_app(app_engine, CREAR, {**params, "email": email}, "23505")
        assert "empresa_existente" in message
    assert _counts(db) == before
    assert _tenant(db, tenant_id)["nombre"] == params["nombre"]


def test_crear_with_an_email_in_use_is_email_en_uso_and_creates_nothing(db, app_engine, dev):
    before = _counts(db)
    params = _params(dev.id, email=ADMIN_A.email)
    message = _fail_app(app_engine, CREAR, params, "23505")
    assert "email_en_uso" in message
    assert ADMIN_A.email not in message and str(TENANT_A) not in message  # H-2: no dice dónde
    assert _counts(db) == before
    assert filas(db, "select 1 from tenant where id = :t", {"t": params["t"]}) == []


@pytest.mark.parametrize(
    ("changes", "sqlstate"),
    [
        ({"h": "$argon2i$v=19$m=8,t=1,p=1$c2FsdHNhbHQ$aGFzaGhhc2g"}, "22023"),
        ({"h": ""}, "22023"),
        ({"h": "$argon2id$v=19$m=8,t=1,p=1$c2FsdHNhbHQ$" + "a" * 300}, "22023"),
        ({"direccion": ""}, "23514"),
        ({"nombre": "x" * 121}, "23514"),
        ({"nit": "123-45"}, "23514"),
        ({"telefono": "123"}, "23514"),
        ({"email": " Mayus@Ejemplo.test"}, "23514"),
    ],
)
def test_crear_with_invalid_data_creates_nothing(db, app_engine, dev, changes, sqlstate):
    before = _counts(db)
    params = _params(dev.id, **changes)
    _fail_app(app_engine, CREAR, params, sqlstate)
    assert _counts(db) == before


def test_crear_ignores_gucs_preset_by_the_caller(db, app_engine, dev):
    # Fijar las GUC del dueño antes de llamar no abre nada: la función las vacía y las
    # políticas son TO plataforma_owner.
    before = _counts(db)
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            for guc, value in (
                ("app.plat_tenant_nuevo", str(TENANT_A)),
                ("app.plat_listar", str(dev.id)),
                ("app.plat_actor", str(dev.id)),
                ("app.plat_tenant_estado", str(TENANT_A)),
            ):
                conn.execute(text("select set_config(:g, :v, true)"), {"g": guc, "v": value})
            assert conn.scalar(text("select count(*) from tenant")) == 0
            message = _expect_error(conn, CREAR, _params(dev.id, t=str(TENANT_A)), "23505")
            assert "empresa_existente" in message
        finally:
            tx.rollback()
    assert _counts(db) == before


def test_the_created_admin_is_found_by_the_tenant_login_lookup(db, app_engine, dev):
    tenant_id, usuario_id, params = _nuevo_tenant(app_engine, dev)
    rows = _call_app(
        app_engine,
        "select usuario_id, tenant_id, rol from acceso.buscar_login(:e)",
        {"e": params["email"]},
    )
    assert [tuple(r) for r in rows] == [(usuario_id, tenant_id, "admin")]


# --- plataforma_cambiar_estado_tenant (R22; A9) ------------------------------------------------


def test_desactivar_and_reactivar_touch_only_the_state_of_that_tenant(db, app_engine, dev):
    tenant_id, _, _ = _nuevo_tenant(app_engine, dev)
    otro = _tenant(db, TENANT_B)
    before = _counts(db)

    assert _call_app(app_engine, ESTADO, {"d": str(dev.id), "t": str(tenant_id), "a": False}) == [
        (False,)
    ]
    desactivado = _tenant(db, tenant_id)
    assert desactivado["activo"] is False
    assert desactivado["desactivado_en"] is not None
    assert desactivado["desactivado_por"] == dev.id

    # Repetir no falla ni cambia nada (ni la fecha).
    assert _call_app(app_engine, ESTADO, {"d": str(dev.id), "t": str(tenant_id), "a": False}) == [
        (False,)
    ]
    assert _tenant(db, tenant_id) == desactivado

    assert _call_app(app_engine, ESTADO, {"d": str(dev.id), "t": str(tenant_id), "a": True}) == [
        (True,)
    ]
    reactivado = _tenant(db, tenant_id)
    assert (reactivado["activo"], reactivado["desactivado_en"], reactivado["desactivado_por"]) == (
        True,
        None,
        None,
    )
    assert _call_app(app_engine, ESTADO, {"d": str(dev.id), "t": str(tenant_id), "a": True}) == [
        (True,)
    ]
    assert _counts(db) == before  # nada se crea ni se borra
    assert _tenant(db, TENANT_B) == otro


def test_cambiar_estado_of_an_unknown_tenant_is_empresa_no_encontrada(db, app_engine, dev):
    before = _counts(db)
    desconocido = uuid.uuid4()
    message = _fail_app(
        app_engine, ESTADO, {"d": str(dev.id), "t": str(desconocido), "a": False}, "P0002"
    )
    assert "empresa_no_encontrada" in message
    assert str(desconocido) not in message
    assert _counts(db) == before


def test_cambiar_estado_leaves_no_gucs_behind(app_engine, dev):
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(text(ESTADO), {"d": str(dev.id), "t": str(TENANT_B), "a": True})
            assert _gucs_empty(conn)
        finally:
            tx.rollback()


def test_login_lookup_skips_memberships_of_an_inactive_tenant(db, app_engine, dev, flask_app):
    tenant_id, usuario_id, params = _nuevo_tenant(app_engine, dev)
    lookup = "select usuario_id, tenant_id, rol from acceso.buscar_login(:e)"
    client = flask_app.test_client()
    credenciales = {"email": params["email"], "password": ADMIN_PASSWORD}
    assert client.post("/auth/login", json=credenciales).status_code == 200

    _call_app(app_engine, ESTADO, {"d": str(dev.id), "t": str(tenant_id), "a": False})
    rows = _call_app(app_engine, lookup, {"e": params["email"]})
    assert [tuple(r) for r in rows] == [(usuario_id, None, None)]
    response = client.post("/auth/login", json=credenciales)
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "credenciales_invalidas"
    # Otra empresa no se afecta.
    otra = client.post("/auth/login", json={"email": ADMIN_A.email, "password": PASSWORD})
    assert otra.status_code == 200

    _call_app(app_engine, ESTADO, {"d": str(dev.id), "t": str(tenant_id), "a": True})
    rows = _call_app(app_engine, lookup, {"e": params["email"]})
    assert [tuple(r) for r in rows] == [(usuario_id, tenant_id, "admin")]
    assert client.post("/auth/login", json=credenciales).status_code == 200


# --- Privilegios de la aplicación que cambian en 0018 ------------------------------------------


def test_app_reads_tenant_identity_but_not_who_deactivated_it(app_engine):
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(TENANT_A)})
            row = conn.execute(text("select id, nombre, creado_en, activo from tenant")).one()
            assert (row.id, row.activo) == (TENANT_A, True)
            for column in ("desactivado_en", "desactivado_por", "*"):
                sql = f"select {column} from tenant"  # noqa: S608 - columnas fijas
                _expect_error(conn, sql, {}, INSUFFICIENT_PRIVILEGE)
        finally:
            tx.rollback()


def test_the_orm_never_selects_the_deactivation_columns(flask_app):
    from sqlalchemy import select

    from app.auth.models import Tenant

    sql = str(select(Tenant))
    assert "desactivado_en" not in sql and "desactivado_por" not in sql
    with flask_app.app_context(), tenant_session(TENANT_A) as session:
        tenant = session.get(Tenant, TENANT_A)
        assert (tenant.nombre, tenant.activo) == ("Clínica sintética A8", True)


_AUDIT = (
    "insert into plataforma_auditoria (desarrollador_id, accion, resultado, tenant_id, objeto_id) "
    "values (:d, :a, 'ok', :t, :o)"
)


def test_app_audits_only_its_own_actions(db, app_engine, dev):
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(
                text("select set_config('app.desarrollador_id', :d, true)"), {"d": str(dev.id)}
            )
            permitidas = [
                ("login_ok", None, dev.id),
                ("empresa_creada", TENANT_A, TENANT_A),
                ("empresa_desactivada", TENANT_A, TENANT_A),
                ("empresa_reactivada", TENANT_A, TENANT_A),
                ("empresa_logo_subido", TENANT_A, uuid.uuid4()),
                ("usuario_desactivado", TENANT_A, ADMIN_A.usuario_id),
                ("usuario_reactivado", TENANT_A, ADMIN_A.usuario_id),
                # Spec 017, C1 (0030): la ficha va sin objeto; el logo, con el suyo.
                ("empresa_editada", TENANT_A, None),
                ("empresa_logo_reemplazado", TENANT_A, uuid.uuid4()),
                ("usuario_editado", TENANT_A, ADMIN_A.usuario_id),
                # Spec 017, C1b (0032): contraseña temporal, con el usuario como objeto.
                ("usuario_contrasena_restablecida", TENANT_A, ADMIN_A.usuario_id),
            ]
            for accion, tenant, objeto in permitidas:
                conn.execute(text(_AUDIT), {"d": dev.id, "a": accion, "t": tenant, "o": objeto})
            rechazadas = [
                # Las del operador (CLI) nunca desde la aplicación.
                ("desarrollador_creado", None, dev.id),
                ("desarrollador_restablecido", None, uuid.uuid4()),
                ("desarrollador_desactivado", None, uuid.uuid4()),
                ("desarrollador_reactivado", TENANT_A, uuid.uuid4()),
                # login_ok: sin tenant y sobre el propio desarrollador.
                ("login_ok", TENANT_A, dev.id),
                ("login_ok", None, uuid.uuid4()),
                ("login_ok", None, None),
                # Las de empresas y usuarios llevan tenant.
                ("empresa_creada", None, TENANT_A),
                ("usuario_desactivado", None, ADMIN_A.usuario_id),
                ("empresa_editada", None, None),
                ("empresa_logo_reemplazado", None, uuid.uuid4()),
                ("usuario_contrasena_restablecida", None, ADMIN_A.usuario_id),
            ]
            for accion, tenant, objeto in rechazadas:
                _expect_error(
                    conn,
                    _AUDIT,
                    {"d": dev.id, "a": accion, "t": tenant, "o": objeto},
                    INSUFFICIENT_PRIVILEGE,
                )
        finally:
            tx.rollback()


# --- Funciones de app.db dentro de plataforma_session -----------------------------------------


def test_db_helpers_use_the_session_developer(db, flask_app, dev):
    tenant_id = uuid.uuid4()
    email = _email("helper")
    ficha = FichaEmpresa(nombre="Clínica Helper", direccion="Carrera 5 # 6-7")
    with flask_app.app_context():
        with plataforma_session(dev.id) as session:
            creado = plataforma_crear_tenant(
                session,
                tenant_id=tenant_id,
                ficha=ficha,
                admin_email=email,
                admin_nombre="Admin Helper",
                password_hash=HASHER.hash(ADMIN_PASSWORD),
            )
        assert creado.tenant_id == tenant_id
        with plataforma_session(dev.id) as session:
            resumen = {t.id: t for t in plataforma_listar_tenants(session)}
            assert plataforma_cambiar_estado_tenant(session, tenant_id, False) is False
        assert resumen[tenant_id].nombre == "Clínica Helper"
        assert (resumen[tenant_id].n_admins_activos, resumen[tenant_id].tiene_logo) == (1, False)
        with plataforma_session(dev.id) as session:
            assert plataforma_cambiar_estado_tenant(session, tenant_id, True) is True
    (empresa,) = filas(
        db, "select nit, telefono, correo from empresa where tenant_id = :t", {"t": tenant_id}
    )
    assert empresa == {"nit": None, "telefono": None, "correo": None}


@pytest.mark.parametrize("caso", ["empresa_existente", "email_en_uso", "hash_invalido"])
def test_db_helpers_map_the_static_errors_and_roll_back(db, flask_app, dev, caso):
    tenant_id = TENANT_A if caso == "empresa_existente" else uuid.uuid4()
    email = ADMIN_A.email if caso == "email_en_uso" else _email("error")
    password_hash = "no-es-argon2" if caso == "hash_invalido" else HASHER.hash(ADMIN_PASSWORD)
    before = _counts(db)
    with flask_app.app_context(), pytest.raises(PlataformaFuncionError) as excinfo:
        with plataforma_session(dev.id) as session:
            plataforma_crear_tenant(
                session,
                tenant_id=tenant_id,
                ficha=FichaEmpresa(nombre="Clínica Error", direccion="Calle 9"),
                admin_email=email,
                admin_nombre="Admin Error",
                password_hash=password_hash,
            )
    assert excinfo.value.codigo == caso
    assert str(excinfo.value) == caso
    assert excinfo.value.__cause__ is None and excinfo.value.__context__ is None
    assert _counts(db) == before


def test_db_helpers_reject_an_inactive_session_developer(db, flask_app):
    inactivo = sembrar_dev(db, nuevo_dev("helper_inactivo"), activo=False)
    with flask_app.app_context():
        for call in (
            lambda s: plataforma_listar_tenants(s),
            lambda s: plataforma_cambiar_estado_tenant(s, TENANT_A, False),
        ):
            with pytest.raises(PlataformaFuncionError) as excinfo:
                with plataforma_session(inactivo.id) as session:
                    call(session)
            assert excinfo.value.codigo == "desarrollador_no_autorizado"
        with pytest.raises(PlataformaFuncionError) as excinfo:
            with plataforma_session(uuid.uuid4()) as session:
                plataforma_cambiar_estado_tenant(session, uuid.uuid4(), True)
        assert excinfo.value.codigo == "desarrollador_no_autorizado"
    assert _tenant(db, TENANT_A)["activo"] is True


def test_db_helpers_report_an_unknown_tenant(flask_app, dev):
    with flask_app.app_context(), pytest.raises(PlataformaFuncionError) as excinfo:
        with plataforma_session(dev.id) as session:
            plataforma_cambiar_estado_tenant(session, uuid.uuid4(), False)
    assert excinfo.value.codigo == "empresa_no_encontrada"


# --- Revisión de T3a (fijadas en T3b) ----------------------------------------------------------


def test_a_developer_deactivated_later_is_rejected_by_every_function_and_the_audit(db, app_engine):
    tarde = sembrar_dev(db, nuevo_dev("tarde"))
    tenant_id, _, _ = _nuevo_tenant(app_engine, tarde)  # activo: funciona
    assert _call_app(app_engine, LISTAR, {"d": str(tarde.id)})
    with db.migrator.begin() as conn:
        conn.execute(
            text("select acceso.cambiar_estado_desarrollador(:e, false)"), {"e": tarde.email}
        )
    before = _counts(db)
    estado_antes = _tenant(db, tenant_id)
    for sql, params in _calls(tenant_id):
        message = _fail_app(app_engine, sql, {**params, "d": str(tarde.id)}, INSUFFICIENT_PRIVILEGE)
        assert "desarrollador_no_autorizado" in message
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            conn.execute(
                text("select set_config('app.desarrollador_id', :d, true)"), {"d": str(tarde.id)}
            )
            for accion in ("empresa_creada", "empresa_desactivada", "empresa_reactivada"):
                _expect_error(
                    conn,
                    _AUDIT,
                    {"d": tarde.id, "a": accion, "t": tenant_id, "o": tenant_id},
                    INSUFFICIENT_PRIVILEGE,
                )
        finally:
            tx.rollback()
    assert _counts(db) == before
    assert _tenant(db, tenant_id) == estado_antes


def _owner_tx_error(conn: Connection, gucs: dict, sql: str, params: dict) -> str:
    nested = conn.begin_nested()
    try:
        for guc, value in gucs.items():
            conn.execute(text("select set_config(:g, :v, true)"), {"g": guc, "v": str(value)})
        with pytest.raises(DBAPIError) as excinfo:
            conn.execute(text(sql), params)
    finally:
        nested.rollback()
    assert getattr(excinfo.value.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE, str(
        excinfo.value.orig
    )
    return str(excinfo.value.orig)


def test_owner_policies_do_not_write_into_a_preexisting_tenant(db, dev):
    nuevo = uuid.uuid4()
    base = {"app.plat_actor": dev.id, "app.plat_tenant_nuevo": TENANT_A}
    inserts = [
        (
            {**base, "app.plat_usuario_nuevo": nuevo},
            "insert into usuario (id, email, nombre, password_hash, debe_cambiar_password) "
            "values (:u, :e, 'Intruso', :h, true)",
            {"u": nuevo, "e": _email("intruso"), "h": HASHER.hash(ADMIN_PASSWORD)},
        ),
        (
            {**base, "app.plat_usuario_nuevo": nuevo},
            "insert into membresia (tenant_id, usuario_id, rol) values (:t, :u, 'admin')",
            {"t": TENANT_A, "u": nuevo},
        ),
        (
            {**base, "app.plat_usuario_nuevo": ADMIN_A.usuario_id},
            "insert into membresia (tenant_id, usuario_id, rol) values (:t, :u, 'admin')",
            {"t": TENANT_A, "u": ADMIN_A.usuario_id},
        ),
        (
            {**base, "app.plat_usuario_nuevo": ADMIN_A.usuario_id},
            "insert into empresa (tenant_id, nombre, direccion, actualizada_por) "
            "values (:t, 'Intrusa', 'Calle 0', :u)",
            {"t": TENANT_A, "u": ADMIN_A.usuario_id},
        ),
    ]
    # Spec 017, C1 (0030): plataforma_owner ya tiene UPDATE (nombre) en tenant (Q-E1), así
    # que renombrar ya no da «permission denied»; lo acota la RLS (ver
    # test_owner_cannot_rename_a_tenant_outside_its_ficha_guc).
    denied = [
        ({**base, "app.plat_tenant_estado": TENANT_A}, "delete from tenant where id = :t"),
        (
            {**base, "app.plat_tenant_estado": TENANT_A},
            "delete from membresia where tenant_id = :t",
        ),
    ]
    before = _counts(db)
    with db.migrator.connect() as conn:
        tx = conn.begin()
        try:
            conn.exec_driver_sql("SET LOCAL ROLE plataforma_owner")
            for gucs, sql, params in inserts:
                message = _owner_tx_error(conn, gucs, sql, params)
                assert "row-level security" in message, sql
            for gucs, sql in denied:
                message = _owner_tx_error(conn, gucs, sql, {"t": TENANT_A})
                assert "permission denied" in message, sql
        finally:
            tx.rollback()
    assert _counts(db) == before


def test_owner_cannot_rename_a_tenant_outside_its_ficha_guc(db, dev):
    """Spec 017, C1 (0030): con UPDATE (nombre) en tenant, la RLS del dueño solo deja
    renombrar el tenant de ``app.plat_empresa_tenant`` y al nombre de su ficha.

    Límite conocido: el privilegio es por columna y no por política, así que con
    ``app.plat_tenant_estado`` (0018) la RLS también dejaría cambiar el nombre; ninguna
    función lo hace (cuerpos estáticos con huella en test_plataforma_catalogo.py).
    """
    nombre = filas(db, "select nombre from tenant where id = :t", {"t": TENANT_A})[0]["nombre"]
    casos = [
        # Sin GUC de la ficha, o con la de otro tenant: cero filas.
        {"app.plat_actor": dev.id},
        {"app.plat_actor": dev.id, "app.plat_empresa_tenant": TENANT_B},
        {"app.plat_actor": dev.id, "app.plat_listar": dev.id},
        {"app.plat_actor": dev.id, "app.plat_tenant_nuevo": TENANT_A},
    ]
    with db.migrator.connect() as conn:
        tx = conn.begin()
        try:
            conn.exec_driver_sql("SET LOCAL ROLE plataforma_owner")
            for gucs in casos:
                nested = conn.begin_nested()
                try:
                    for guc, value in gucs.items():
                        conn.execute(
                            text("select set_config(:g, :v, true)"), {"g": guc, "v": str(value)}
                        )
                    cambiadas = conn.execute(
                        text("update tenant set nombre = 'X' where id = :t"), {"t": TENANT_A}
                    ).rowcount
                finally:
                    nested.rollback()
                assert cambiadas == 0, gucs
            # Con su GUC pero a un nombre distinto del de su ficha (el tenant A no tiene
            # ficha): la RLS lo rechaza.
            message = _owner_tx_error(
                conn,
                {"app.plat_actor": dev.id, "app.plat_empresa_tenant": TENANT_A},
                "update tenant set nombre = 'X' where id = :t",
                {"t": TENANT_A},
            )
            assert "row-level security" in message
        finally:
            tx.rollback()
    assert filas(db, "select nombre from tenant where id = :t", {"t": TENANT_A}) == [
        {"nombre": nombre}
    ]


_NEW_GUCS = (
    "app.plat_actor",
    "app.plat_listar",
    "app.plat_tenant_nuevo",
    "app.plat_usuario_nuevo",
    "app.plat_tenant_estado",
)


def _preset(conn: Connection, otro: Dev) -> None:
    values = {
        "app.plat_actor": otro.id,
        "app.plat_listar": otro.id,
        "app.plat_tenant_nuevo": TENANT_A,
        "app.plat_usuario_nuevo": ADMIN_A.usuario_id,
        "app.plat_tenant_estado": TENANT_A,
    }
    for guc in _NEW_GUCS:
        conn.execute(text("select set_config(:g, :v, true)"), {"g": guc, "v": str(values[guc])})


def test_new_gucs_preset_by_the_app_do_not_alter_plataforma_buscar_login(app_engine, dev, db):
    otro = sembrar_dev(db, nuevo_dev("guc-login"))
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            _preset(conn, otro)
            buscar = text("select id, activo from acceso.plataforma_buscar_login(:e)")
            assert [tuple(r) for r in conn.execute(buscar, {"e": dev.email})] == [(dev.id, True)]
            assert conn.execute(buscar, {"e": _email("nadie")}).all() == []
            # Ni la búsqueda ni las GUC abren tablas a la aplicación.
            for table in ("tenant", "membresia", "usuario", "empresa"):
                assert conn.scalar(text(f"select count(*) from {table}")) == 0  # noqa: S608
        finally:
            tx.rollback()


def test_new_gucs_preset_do_not_alter_the_operator_functions(db, dev):
    otro = sembrar_dev(db, nuevo_dev("guc-operador"))
    leer = text("select id, password_hash, activo from desarrollador where id in (:a, :b)")
    with db.migrator.connect() as conn:
        tx = conn.begin()
        try:
            antes = {r.id: r for r in conn.execute(leer, {"a": dev.id, "b": otro.id})}
            _preset(conn, otro)
            nuevo_hash = HASHER.hash("Otra-Clave-Sintetica-Operador")
            conn.execute(
                text("select acceso.restablecer_desarrollador(:e, :h)"),
                {"e": dev.email, "h": nuevo_hash},
            )
            _preset(conn, otro)
            conn.execute(
                text("select acceso.cambiar_estado_desarrollador(:e, false)"), {"e": dev.email}
            )
            despues = {r.id: r for r in conn.execute(leer, {"a": dev.id, "b": otro.id})}
            assert despues[dev.id].password_hash == nuevo_hash
            assert despues[dev.id].activo is False
            assert tuple(despues[otro.id]) == tuple(antes[otro.id])  # el de las GUC, intacto
            # Un correo inexistente no cae sobre el desarrollador de las GUC.
            _preset(conn, otro)
            for sql, params in (
                (
                    "select acceso.restablecer_desarrollador(:e, :h)",
                    {"e": _email("nadie"), "h": nuevo_hash},
                ),
                ("select acceso.cambiar_estado_desarrollador(:e, false)", {"e": _email("nadie")}),
            ):
                _expect_error(conn, sql, params, "P0002")
            final = {r.id: r for r in conn.execute(leer, {"a": dev.id, "b": otro.id})}
            assert tuple(final[otro.id]) == tuple(antes[otro.id])
        finally:
            tx.rollback()


# --- Spec 017, C1 (T12): GUC de 0029 y 0030 preestablecidas -----------------------------------

REGISTRAR = "select * from acceso.plataforma_registrar_logo(:d, :t, :l, :c, :b, :w, :h)"


def _preset_c1(conn: Connection, otro: Dev, ajeno: uuid.UUID, logo_ajeno: uuid.UUID) -> None:
    """Las de 0018 (``_preset``) y las de 0029/0030 apuntando a otro tenant y otro logo."""
    _preset(conn, otro)
    values = {
        "app.plat_tenant_estado": ajeno,
        "app.plat_logo_tenant": ajeno,
        "app.plat_logo_id": logo_ajeno,
        "app.plat_empresa_tenant": ajeno,
    }
    for guc, value in values.items():
        conn.execute(text("select set_config(:g, :v, true)"), {"g": guc, "v": str(value)})


def _huella_tenant(db: AccesoDb, tenant_id) -> dict:
    (tenant,) = filas(
        db,
        "select t.nombre, t.activo, t.desactivado_en, t.desactivado_por, e.nombre as ficha, "
        "e.direccion, e.logo_id, e.actualizada_en, "
        "(select count(*) from empresa_logo l where l.tenant_id = t.id) as logos "
        "from tenant t left join empresa e on e.tenant_id = t.id where t.id = :t",
        {"t": tenant_id},
    )
    return tenant


def test_c1_gucs_preset_do_not_alter_estado_listar_or_registrar_logo(db, app_engine, dev):
    objetivo, _, _ = _nuevo_tenant(app_engine, dev)
    ajeno, _, _ = _nuevo_tenant(app_engine, dev)
    otro = sembrar_dev(db, nuevo_dev("guc-c1"))
    logo, logo_ajeno = uuid.uuid4(), uuid.uuid4()
    ajeno_antes = _huella_tenant(db, ajeno)
    a_antes = _huella_tenant(db, TENANT_A)
    registrar = {
        "d": str(dev.id),
        "t": str(objetivo),
        "l": str(logo),
        "c": f"{objetivo}/{logo}.png",
        "b": 10,
        "w": 10,
        "h": 10,
    }
    with app_engine.connect() as conn:
        tx = conn.begin()
        try:
            listado = sorted(tuple(r) for r in conn.execute(text(LISTAR), {"d": str(dev.id)}))
            _preset_c1(conn, otro, ajeno, logo_ajeno)
            assert sorted(tuple(r) for r in conn.execute(text(LISTAR), {"d": str(dev.id)})) == (
                listado
            )
            assert _gucs_empty(conn)

            _preset_c1(conn, otro, ajeno, logo_ajeno)
            estado = {"d": str(dev.id), "t": str(objetivo), "a": False}
            assert conn.execute(text(ESTADO), estado).all() == [(False,)]
            _preset_c1(conn, otro, ajeno, logo_ajeno)
            assert conn.execute(text(ESTADO), {**estado, "a": True}).all() == [(True,)]

            _preset_c1(conn, otro, ajeno, logo_ajeno)
            assert [tuple(r) for r in conn.execute(text(REGISTRAR), registrar)] == [
                (logo, True, False)
            ]
            _preset_c1(conn, otro, ajeno, logo_ajeno)  # repetir: idempotente, mismo resultado
            assert [tuple(r) for r in conn.execute(text(REGISTRAR), registrar)] == [
                (logo, False, False)
            ]
            tx.commit()
        except BaseException:
            tx.rollback()
            raise
    # Cero filas ajenas: el tenant de las GUC y el tenant A siguen idénticos.
    assert _huella_tenant(db, ajeno) == ajeno_antes
    assert _huella_tenant(db, TENANT_A) == a_antes
    assert filas(db, "select count(*) as n from empresa_logo where id = :l", {"l": logo_ajeno}) == [
        {"n": 0}
    ]
    final = _huella_tenant(db, objetivo)
    assert (final["activo"], final["desactivado_en"], final["desactivado_por"]) == (
        True,
        None,
        None,
    )
    assert (final["logo_id"], final["logos"]) == (logo, 1)
    assert filas(db, "select tenant_id from empresa_logo where id = :l", {"l": logo}) == [
        {"tenant_id": objetivo}
    ]


def test_known_limit_rc10_owner_under_tenant_estado_guc_can_rename_the_tenant(db, dev):
    """Límite conocido y aceptado (RC10): el UPDATE (nombre) de ``plataforma_owner`` en
    ``tenant`` es por columna y la política ``dueno_plat_tenant_estado`` (0018) no mira
    columnas; con ``app.plat_tenant_estado`` el dueño puede renombrar ese tenant. Lo contiene
    que ninguna función lo haga salvo ``plataforma_actualizar_empresa`` (cuerpos estáticos
    con huella; ``test_only_actualizar_empresa_renames_a_tenant`` en
    test_plataforma_catalogo.py). Si esta prueba falla, el límite se cerró: actualizarla."""
    nombre = _tenant(db, TENANT_A)["nombre"]
    with db.migrator.connect() as conn:
        tx = conn.begin()
        try:
            conn.exec_driver_sql("SET LOCAL ROLE plataforma_owner")
            for guc, value in {
                "app.plat_actor": dev.id,
                "app.plat_tenant_estado": TENANT_A,
            }.items():
                conn.execute(text("select set_config(:g, :v, true)"), {"g": guc, "v": str(value)})
            cambiadas = conn.execute(
                text("update tenant set nombre = 'Renombrada por el dueño' where id = :t"),
                {"t": TENANT_A},
            ).rowcount
            assert cambiadas == 1
        finally:
            tx.rollback()
    assert _tenant(db, TENANT_A)["nombre"] == nombre
