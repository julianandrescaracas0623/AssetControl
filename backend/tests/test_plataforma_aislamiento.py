"""Aislamiento entre la consola de plataforma y la app de las clínicas (spec 017, T2).

R5, R37; A2, A3, A6; CU-09. Sobre una base temporal migrada a ``head``:

- **Catálogo (A3):** todo endpoint de ``/plataforma`` es público por lista cerrada
  (login, refresh, logout) o declara exactamente el rol ``desarrollador``; ningún
  endpoint de tenant lo declara y ``ROLES`` del tenant no lo incluye.
- **Matriz (A2):** un token de ``admin`` y uno de ``contador`` reciben ``401`` en cada
  endpoint protegido de ``/plataforma`` (recorrido de ``url_map``); un token de
  plataforma recibe ``401`` en cada endpoint protegido de tenant.
- **Base (A6, R37):** con ``plataforma_session`` el rol de la aplicación no lee ninguna
  fila de tablas de negocio (y el ORM rechaza sus modelos); con ``tenant_session`` no lee
  ``desarrollador``, ``plataforma_refresh_token`` ni ``plataforma_auditoria``. Una sesión
  de plataforma no fija ``app.tenant_id`` y una de tenant no fija ``app.desarrollador_id``.
- ``select(Desarrollador)`` por el ORM no pide ``creado_en`` ni ``password_hash``
  (columnas sin ``GRANT`` para la aplicación): no da permiso denegado.
"""

import re
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
    temporary_acceso_db,
)
from flask import Flask
from plataforma_db import (
    Dev,
    error_code,
    filas,
    login,
    make_plat_app,
    nuevo_dev,
    plat_bearer,
    sembrar_dev,
)
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.pool import NullPool

from app.activos.models import Activo
from app.auth.decorators import ROLES, require_role
from app.auth.models import Membresia, Tenant, Usuario
from app.db import PlataformaScopeError, UnscopedStatementError, plataforma_session, tenant_session
from app.plataforma.decoradores import ROL_DESARROLLADOR
from app.plataforma.models import Desarrollador, PlataformaAuditoria, PlataformaRefreshToken

PLATFORM_TABLES = ("desarrollador", "plataforma_refresh_token", "plataforma_auditoria")
NOT_BUSINESS = {"alembic_version", "limite_tasa", *PLATFORM_TABLES}
PLATFORM_PUBLIC = frozenset(
    {"plataforma_auth.login", "plataforma_auth.refresh", "plataforma_auth.logout"}
)
INSUFFICIENT_PRIVILEGE = "42501"


@pytest.fixture(scope="module")
def iso_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("plat_iso")


@pytest.fixture(scope="module")
def iso_app(iso_db) -> Iterator[Flask]:
    flask_app = make_plat_app(iso_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(iso_app):
    return iso_app.test_client(use_cookies=False)


@pytest.fixture(scope="module")
def dev(iso_db) -> Dev:
    return sembrar_dev(iso_db, nuevo_dev("iso"))


@pytest.fixture(scope="module")
def otro_dev(iso_db) -> Dev:
    return sembrar_dev(iso_db, nuevo_dev("iso-otro"))


@pytest.fixture(scope="module")
def dev_token(iso_app, dev) -> str:
    response = login(iso_app.test_client(use_cookies=False), dev.email)
    assert response.status_code == 200
    return response.get_json()["access_token"]


@pytest.fixture(scope="module")
def negocio(iso_db) -> None:
    """Filas de negocio en los dos tenants para que «cero filas» signifique algo."""
    with iso_db.migrator.begin() as conn:
        for tenant in (TENANT_A, TENANT_B):
            conn.execute(
                text(
                    "insert into ubicacion (tenant_id, nombre, nombre_clave, tipo, padre_id) "
                    "values (:t, 'Sede', 'sede', 'sede', null)"
                ),
                {"t": tenant},
            )
            conn.execute(
                text(
                    "insert into categoria (tenant_id, nombre, nombre_clave) "
                    "values (:t, 'CPU', 'cpu')"
                ),
                {"t": tenant},
            )


def _sample(rule: str) -> str:
    return re.sub(r"<(?:[^:<>]+:)?[^<>]+>", str(uuid.uuid4()), rule)


def _routes(flask_app: Flask, *, platform: bool) -> list[tuple[str, str, str]]:
    found = []
    for rule in flask_app.url_map.iter_rules():
        if rule.rule.startswith("/plataforma") != platform:
            continue
        view = flask_app.view_functions[rule.endpoint]
        if getattr(view, "required_roles", None) is None:
            continue
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            found.append((rule.endpoint, method, _sample(rule.rule)))
    return found


# --- Catálogo (A3) ------------------------------------------------------------------------


def test_every_platform_endpoint_is_public_by_list_or_declares_desarrollador(iso_app):
    platform = {
        rule.endpoint
        for rule in iso_app.url_map.iter_rules()
        if rule.rule.startswith("/plataforma")
    }
    assert PLATFORM_PUBLIC <= platform
    for endpoint in platform:
        roles = getattr(iso_app.view_functions[endpoint], "required_roles", None)
        if endpoint in PLATFORM_PUBLIC:
            assert roles is None, endpoint
        else:
            assert roles == frozenset({ROL_DESARROLLADOR}), endpoint
    assert {"plataforma_auth.me", "plataforma_modulos.listar"} <= platform


def test_no_tenant_endpoint_accepts_the_desarrollador_role(iso_app):
    assert ROL_DESARROLLADOR not in ROLES
    with pytest.raises(ValueError):
        require_role(ROL_DESARROLLADOR)
    for rule in iso_app.url_map.iter_rules():
        if rule.rule.startswith("/plataforma"):
            continue
        roles = getattr(iso_app.view_functions[rule.endpoint], "required_roles", frozenset())
        assert ROL_DESARROLLADOR not in roles, rule.endpoint
        assert roles <= ROLES, rule.endpoint


# --- Matriz de tokens (A2, CU-09) ---------------------------------------------------------


def test_admin_and_contador_get_401_on_every_platform_endpoint(client, iso_app, dev_token):
    routes = _routes(iso_app, platform=True)
    assert routes
    for endpoint, method, path in routes:
        for name, headers in (
            ("anonimo", {}),
            ("admin", bearer(ADMIN_A, TENANT_A, rol="admin")),
            ("contador", bearer(CONTADOR_A, TENANT_A, rol="contador")),
        ):
            response = client.open(path, method=method, json={}, headers=headers)
            assert response.status_code == 401, (endpoint, method, name)
            assert error_code(response) == "no_autenticado"
        own = client.open(path, method=method, json={}, headers=plat_bearer(dev_token))
        assert own.status_code not in (401, 403), (endpoint, method)


def _alta_valida() -> dict:
    password = "Clave-Inicial-Aislamiento-2026"
    return {
        "id": str(uuid.uuid4()),
        "nombre": f"Clínica Aislamiento {uuid.uuid4().hex[:6]}",
        "direccion": "Calle 1 # 2-3, Cartago",
        "admin": {
            "nombre": "Admin Aislamiento",
            "email": f"iso.{uuid.uuid4().hex[:10]}@ejemplo.test",
            "password": password,
            "password_confirmacion": password,
        },
    }


def _conteos(db: AccesoDb) -> dict[str, int]:
    tablas = ("tenant", "usuario", "membresia", "empresa", "plataforma_auditoria")
    with db.migrator.connect() as conn:
        return {t: conn.scalar(text(f"select count(*) from {t}")) for t in tablas}  # noqa: S608


def test_tenant_tokens_get_401_on_empresas_writes_with_a_valid_body(client, iso_db):
    """Spec 017, T4 (revisión de T3b): con un cuerpo válido, el 401 lo da el token."""
    antes = _conteos(iso_db)
    escrituras = (
        ("POST", "/plataforma/empresas", _alta_valida()),
        ("PATCH", f"/plataforma/empresas/{TENANT_A}", {"activa": False}),
        ("PATCH", f"/plataforma/empresas/{TENANT_B}", {"activa": False}),
    )
    for method, path, body in escrituras:
        for name, headers in (
            ("anonimo", {}),
            ("admin", bearer(ADMIN_A, TENANT_A, rol="admin")),
            ("contador", bearer(CONTADOR_A, TENANT_A, rol="contador")),
            ("admin_b", bearer(ADMIN_B, TENANT_B, rol="admin")),
        ):
            response = client.open(path, method=method, json=body, headers=headers)
            assert response.status_code == 401, (method, path, name)
            assert error_code(response) == "no_autenticado"
    assert _conteos(iso_db) == antes
    activos = filas(
        iso_db, "select activo from tenant where id in (:a, :b)", {"a": TENANT_A, "b": TENANT_B}
    )
    assert activos == [{"activo": True}, {"activo": True}]


def test_tenant_tokens_do_not_refresh_the_platform_session(client):
    # El refresh de plataforma ignora el Authorization y la cookie de tenant.
    response = client.post(
        "/plataforma/auth/refresh",
        headers={
            "X-AssetControl-CSRF": "1",
            "Cookie": f"__Secure-refresh={TENANT_A}.{'A' * 43}",
            **bearer(ADMIN_A, TENANT_A, rol="admin"),
        },
    )
    assert response.status_code == 401
    assert error_code(response) == "no_autenticado"


def test_platform_token_gets_401_on_every_tenant_endpoint(client, iso_app, dev_token):
    routes = _routes(iso_app, platform=False)
    assert len(routes) > 30
    for endpoint, method, path in routes:
        response = client.open(path, method=method, json={}, headers=plat_bearer(dev_token))
        assert response.status_code == 401, (endpoint, method)
        assert error_code(response) == "no_autenticado"


def test_no_cors_on_platform_routes(client, dev_token):
    origin = "https://sitio-ajeno.example"
    for path in ("/plataforma/auth/login", "/plataforma/auth/refresh", "/plataforma/auth/me"):
        for response in (
            client.options(
                path,
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "x-assetcontrol-csrf, authorization",
                },
            ),
            client.get(path, headers={"Origin": origin, **plat_bearer(dev_token)}),
        ):
            assert not [
                h for h in response.headers.keys() if h.lower().startswith("access-control-")
            ]


# --- Base de datos (A6, R37) --------------------------------------------------------------


def _business_tables(iso_db: AccesoDb) -> list[str]:
    rows = filas(
        iso_db,
        "select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace "
        "where n.nspname = 'public' and c.relkind in ('r', 'p') order by 1",
    )
    return [row["relname"] for row in rows if row["relname"] not in NOT_BUSINESS]


def _app_engine(iso_db: AccesoDb):
    return create_engine(iso_db.app_url, poolclass=NullPool)


def _visible_rows(conn, table: str) -> int | None:
    """Filas visibles de ``table``; ``None`` si el rol ni siquiera puede leerla."""
    savepoint = conn.begin_nested()
    try:
        count = conn.scalar(text(f'select count(*) from "{table}"'))  # noqa: S608
    except DBAPIError as exc:
        savepoint.rollback()
        assert getattr(exc.orig, "sqlstate", None) == INSUFFICIENT_PRIVILEGE, table
        return None
    savepoint.commit()
    return count


def test_platform_guc_reads_no_business_row(iso_db, dev, negocio):
    tables = _business_tables(iso_db)
    assert {"tenant", "usuario", "membresia", "ubicacion", "categoria", "activo", "empresa"} <= set(
        tables
    )
    with iso_db.migrator.connect() as conn:
        assert conn.scalar(text("select count(*) from ubicacion")) >= 2
    engine = _app_engine(iso_db)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("select set_config('app.desarrollador_id', :d, true)"), {"d": str(dev.id)}
            )
            visible = {table: _visible_rows(conn, table) for table in tables}
    finally:
        engine.dispose()
    assert {table: count for table, count in visible.items() if count} == {}


_WRITES = {
    "ubicacion": (
        "insert into ubicacion (tenant_id, nombre, nombre_clave, tipo, padre_id) "
        "values (:a, 'Intrusa', 'intrusa', 'sede', null)",
        "update ubicacion set nombre = 'Intrusa'",
        "delete from ubicacion",
    ),
    "membresia": (
        "insert into membresia (tenant_id, usuario_id, rol, activa) "
        "values (:a, :usuario_b, 'admin', true)",
        "update membresia set activa = false",
        "delete from membresia",
    ),
    "tenant": (
        "insert into tenant (id, nombre) values (:nuevo, 'Clínica intrusa')",
        "update tenant set nombre = 'Clínica intrusa'",
        "delete from tenant",
    ),
}


def _snapshot(iso_db: AccesoDb) -> dict[str, list]:
    with iso_db.migrator.connect() as conn:
        return {
            table: sorted(
                tuple(str(value) for value in row)
                for row in conn.execute(text(f'select * from "{table}"'))  # noqa: S608
            )
            for table in _WRITES
        }


def test_platform_guc_cannot_write_business_rows(iso_db, dev, negocio):
    """Hallazgo 3b (T2): con solo ``app.desarrollador_id``, nada de negocio cambia."""
    before = _snapshot(iso_db)
    assert all(before.values())
    params = {"a": TENANT_A, "usuario_b": ADMIN_B.usuario_id, "nuevo": uuid.uuid4()}
    outcomes: dict[tuple[str, str], str] = {}
    engine = _app_engine(iso_db)
    try:
        with engine.begin() as conn:
            conn.execute(
                text("select set_config('app.desarrollador_id', :d, true)"), {"d": str(dev.id)}
            )
            for table, statements in _WRITES.items():
                for statement in statements:
                    savepoint = conn.begin_nested()
                    try:
                        result = conn.execute(text(statement), params)
                    except DBAPIError as exc:
                        savepoint.rollback()
                        sqlstate = getattr(exc.orig, "sqlstate", None)
                        assert sqlstate == INSUFFICIENT_PRIVILEGE, (table, statement, sqlstate)
                        outcomes[(table, statement.split()[0])] = "rechazada"
                        continue
                    savepoint.commit()
                    assert result.rowcount == 0, (table, statement)
                    outcomes[(table, statement.split()[0])] = "0 filas"
    finally:
        engine.dispose()
    assert len(outcomes) == 9
    # Un INSERT no puede afectar «0 filas»: debe fallar.
    assert all(
        outcome == "rechazada" for (_, verb), outcome in outcomes.items() if verb == "insert"
    )
    assert _snapshot(iso_db) == before


def test_tenant_guc_reads_no_platform_row(iso_db, dev, client):
    login(client, dev.email)  # deja refresh y auditoría del desarrollador
    engine = _app_engine(iso_db)
    try:
        with engine.begin() as conn:
            conn.execute(text("select set_config('app.tenant_id', :t, true)"), {"t": str(TENANT_A)})
            assert conn.scalar(text("select count(*) from membresia")) > 0  # control
            visible = {table: _visible_rows(conn, table) for table in PLATFORM_TABLES}
    finally:
        engine.dispose()
    assert {table: count for table, count in visible.items() if count} == {}
    with iso_db.migrator.connect() as conn:
        assert conn.scalar(text("select count(*) from plataforma_auditoria")) > 0


@pytest.mark.parametrize("model", [Activo, Usuario, Tenant, Membresia])
def test_plataforma_session_rejects_business_models(iso_app, dev, model):
    with iso_app.app_context():
        with pytest.raises(PlataformaScopeError):
            with plataforma_session(dev.id) as session:
                session.scalars(select(model)).all()


def test_plataforma_session_rejects_raw_sql_and_connection(iso_app, dev):
    with iso_app.app_context():
        with pytest.raises(UnscopedStatementError):
            with plataforma_session(dev.id) as session:
                session.execute(text("select 1"))
        with pytest.raises(UnscopedStatementError):
            with plataforma_session(dev.id) as session:
                session.connection()


def test_plataforma_session_rejects_writing_business_models(iso_app, dev):
    with iso_app.app_context():
        with pytest.raises(PlataformaScopeError):
            with plataforma_session(dev.id) as session:
                session.add(Tenant(nombre="No debe existir"))
                session.flush()


def test_plataforma_session_reads_only_its_own_developer(iso_app, dev, otro_dev):
    with iso_app.app_context():
        with plataforma_session(dev.id) as session:
            rows = session.scalars(select(Desarrollador)).all()
            assert [(row.id, row.email, row.nombre, row.activo) for row in rows] == [
                (dev.id, dev.email, dev.nombre, True)
            ]
            assert session.scalar(select(func.current_setting("app.tenant_id", True))) in (None, "")
            assert session.scalar(
                select(func.current_setting("app.desarrollador_id", True))
            ) == str(dev.id)


def test_tenant_session_reads_no_platform_row_through_the_orm(iso_app, iso_db, dev, client):
    login(client, dev.email)
    with iso_app.app_context():
        with tenant_session(TENANT_A) as session:
            assert session.scalars(select(Desarrollador)).all() == []
            assert session.scalars(select(PlataformaRefreshToken)).all() == []
            assert session.scalars(select(PlataformaAuditoria)).all() == []
            assert session.scalar(select(func.current_setting("app.desarrollador_id", True))) in (
                None,
                "",
            )


def test_desarrollador_select_does_not_ask_for_ungranted_columns(iso_app, dev):
    """Hallazgo (c) de T1: ``creado_en`` y ``password_hash`` no se piden por defecto."""
    statement = str(select(Desarrollador).compile())
    assert "creado_en" not in statement
    assert "password_hash" not in statement
    with iso_app.app_context(), plataforma_session(dev.id) as session:
        assert session.get(Desarrollador, dev.id).email == dev.email


def test_plataforma_session_requires_a_valid_developer_id(iso_app):
    from app.db import MissingDesarrolladorError

    with iso_app.app_context():
        for value in (None, "", "no-es-uuid"):
            with pytest.raises(MissingDesarrolladorError):
                with plataforma_session(value):
                    pass


def test_platform_writes_cannot_impersonate_another_developer(iso_app, dev, otro_dev):
    with iso_app.app_context():
        with pytest.raises(DBAPIError):
            with plataforma_session(dev.id) as session:
                session.add(
                    PlataformaAuditoria(
                        desarrollador_id=otro_dev.id, accion="login_ok", resultado="ok"
                    )
                )
                session.flush()
