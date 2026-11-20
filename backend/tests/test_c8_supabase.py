"""C8: la base preparada como en Supabase (spec 010b, T4; R5; spec 002, R4g).

Corre solo con ``C8_MIGRATION_DATABASE_URL`` (el migrador **no** superusuario, como
``postgres`` en Supabase) y ``C8_DATABASE_URL`` (el rol de la aplicación, con su
contraseña), contra una base ya preparada con ``flask preparar-roles`` y migrada con
``alembic upgrade head`` por ese migrador. La CI lo hace en el trabajo ``c8``.

Comprueba lo que la suite normal no puede (allí el migrador es superusuario): atributos
y membresías de los roles, que el migrador no hereda ``auth_owner`` ni el rol de la
aplicación, que la contraseña viajó como SCRAM y que el RLS aísla dos tenants de punta a
punta con el rol de la aplicación.
"""

import os
import uuid

import psycopg
import pytest
from sqlalchemy.engine import make_url

from app import create_app, roles
from app.auth.credentials import new_token, token_key
from app.config import Config

MIGRADOR = os.environ.get("C8_MIGRATION_DATABASE_URL", "").strip()
APLICACION = os.environ.get("C8_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not (MIGRADOR and APLICACION), reason="C8: sin base preparada como en Supabase"
)
APP_USER = os.environ.get("APP_DB_USER", "assetcontrol_app")
# Spec 017, T1: plataforma_owner se prepara igual que auth_owner.
ROLES = [APP_USER, roles.AUTH_OWNER, roles.PLATAFORMA_OWNER]


def libpq(url: str) -> str:
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


def consulta(url: str, sql: str, params: tuple = ()) -> list[tuple]:
    with psycopg.connect(libpq(url), connect_timeout=5) as conn:
        return conn.execute(sql, params).fetchall()


def test_the_migrator_is_not_superuser_like_supabase():
    ((superusuario,),) = consulta(
        MIGRADOR, "select rolsuper from pg_roles where rolname = current_user"
    )
    assert superusuario is False


def test_app_role_and_owners_have_no_dangerous_attributes():
    filas = consulta(
        MIGRADOR,
        "select rolname, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb, rolreplication, "
        "rolcanlogin from pg_roles where rolname = any(%s) order by rolname",
        (ROLES,),
    )
    assert filas == sorted(
        [
            (APP_USER, False, False, False, False, False, True),
            (roles.AUTH_OWNER, False, False, False, False, False, False),
            (roles.PLATAFORMA_OWNER, False, False, False, False, False, False),
        ]
    )


def test_only_the_creators_admin_membership_remains_and_gives_no_privileges():
    filas = consulta(
        MIGRADOR,
        "select g.rolname, m.rolname, a.admin_option, a.inherit_option, a.set_option "
        "from pg_auth_members a join pg_roles g on g.oid = a.roleid "
        "join pg_roles m on m.oid = a.member "
        "where g.rolname = any(%s) or m.rolname = any(%s)",
        (ROLES, ROLES),
    )
    ((migrador,),) = consulta(MIGRADOR, "select current_user")
    assert filas, "PostgreSQL 16+ da al creador ADMIN sobre los roles que crea"
    for concedido, miembro, admin, inherit, set_ in filas:
        assert (miembro, admin, inherit, set_) == (migrador, True, False, False), concedido
    for rol in ROLES:
        ((usa, cambia),) = consulta(
            MIGRADOR,
            "select pg_has_role(current_user, %s, 'USAGE'), pg_has_role(current_user, %s, 'SET')",
            (rol, rol),
        )
        assert (usa, cambia) == (False, False), rol


# Spec 017, T1 (0017): dueña plataforma_owner; solo plataforma_buscar_login es de la app.
PLATAFORMA = (
    "crear_desarrollador",
    "restablecer_desarrollador",
    "cambiar_estado_desarrollador",
    "plataforma_buscar_login",
)


def test_access_functions_belong_to_their_owner_and_only_the_app_runs_them():
    filas = consulta(
        MIGRADOR,
        "select p.proname, pg_get_userbyid(p.proowner), p.proacl::text from pg_proc p "
        "join pg_namespace n on n.oid = p.pronamespace where n.nspname = 'acceso' order by 1",
    )
    ((migrador,),) = consulta(MIGRADOR, "select current_user")
    assert {f[0] for f in filas} == {
        "aceptar_invitacion",
        "buscar_login",
        "crear_tenant",
        "validar_invitacion",
        # Spec 014, T2 (0016).
        "solicitar_recuperacion",
        "restablecer_contrasena",
        *PLATAFORMA,
    }
    del_migrador = {"crear_tenant", *(f for f in PLATAFORMA if f != "plataforma_buscar_login")}
    for nombre, dueno, acl in filas:
        esperado = roles.PLATAFORMA_OWNER if nombre in PLATAFORMA else roles.AUTH_OWNER
        assert dueno == esperado, nombre
        concedidos = {e.split("=")[0] for e in acl.strip("{}").split(",")} - {esperado}
        assert concedidos == ({migrador} if nombre in del_migrador else {APP_USER}), nombre


def test_supabase_roles_receive_nothing_despite_default_privileges():
    # Supabase concede por defecto todo lo nuevo de public a anon, authenticated y
    # service_role (ALTER DEFAULT PRIVILEGES); service_role además tiene BYPASSRLS. Las
    # migraciones lo revocan tabla por tabla y función por función.
    tablas = consulta(
        MIGRADOR,
        "select grantee, table_name, privilege_type from information_schema.role_table_grants "
        "where table_schema in ('public', 'acceso') and grantee = any(%s)",
        (["anon", "authenticated", "service_role"],),
    )
    assert tablas == []
    funciones = consulta(
        MIGRADOR,
        "select r.rolname, p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
        "cross join pg_roles r where n.nspname in ('public', 'acceso') "
        "and r.rolname = any(%s) and has_function_privilege(r.oid, p.oid, 'EXECUTE')",
        (["anon", "authenticated", "service_role"],),
    )
    assert funciones == []


def test_the_app_role_logs_in_with_its_password_and_cannot_skip_rls():
    ((usuario, bypass),) = consulta(
        APLICACION,
        "select current_user, (select rolbypassrls from pg_roles where rolname = current_user)",
    )
    assert (usuario, bypass) == (APP_USER, False)
    # Sin tenant fijado, el RLS no deja ver ni una fila (y no lanza: la política lo filtra).
    assert consulta(APLICACION, "select count(*) from activo") == [(0,)]


def test_prepare_roles_again_changes_nothing_but_the_password():
    contrasena = make_url(APLICACION).password
    resultado = roles.preparar(libpq(MIGRADOR), APP_USER, contrasena)
    assert (resultado.creado, resultado.revocadas, resultado.conservadas) == (False, 0, 3)


def test_two_tenants_are_isolated_end_to_end_with_the_app_role():
    tokens = []
    for nombre in ("Clínica A", "Clínica B"):
        token = new_token()
        sufijo = uuid.uuid4().hex[:8]
        consulta(
            MIGRADOR,
            "select acceso.crear_tenant(%s, %s, %s)",
            (f"{nombre} {sufijo}", f"admin.{sufijo}@c8.ejemplo.test", token_key(token)),
        )
        tokens.append(token)
    app = create_app(
        Config(
            database_url=APLICACION,
            secret_key="c8-clave-efimera-de-mas-de-32-bytes",
            environment="test",
        )
    )
    cliente = app.test_client(use_cookies=False)
    sesiones = []
    for token in tokens:
        r = cliente.post(
            "/invitaciones/aceptar",
            json={"token": token, "nombre": "Admin C8", "password": "Clave-C8-Efimera-2026"},
        )
        assert r.status_code == 201, r.status_code
        sesiones.append({"Authorization": f"Bearer {r.get_json()['access_token']}"})
    a, b = sesiones
    creada = cliente.post("/ubicaciones", json={"nombre": "Sede C8", "tipo": "sede"}, headers=a)
    assert creada.status_code == 201, creada.get_json()
    ubicacion = creada.get_json()["ubicacion"]["id"]
    assert ubicacion in {
        u["id"] for u in cliente.get("/ubicaciones", headers=a).get_json()["ubicaciones"]
    }
    assert cliente.get("/ubicaciones", headers=b).get_json()["ubicaciones"] == []
    app.extensions["assetcontrol.db"].engine.dispose()
