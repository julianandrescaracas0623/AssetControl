"""Funciones ``SECURITY DEFINER`` del esquema ``acceso`` (spec 002, T3; plan.md §2.1).

Las cuatro funciones de acceso previo al tenant, con dueña ``auth_owner``:

- ``buscar_login(p_email)`` -> ``usuario_id``, ``password_hash``, ``activo``,
  ``tenant_id``, ``rol``. GUC: ``app.auth_email`` y ``app.auth_usuario``.
- ``validar_invitacion(p_clave)`` -> ``boolean``. GUC: ``app.auth_inv_validar``.
- ``aceptar_invitacion(p_clave, p_nombre, p_password_hash)`` -> ``usuario_id``,
  ``tenant_id``, ``rol``. GUC: ``app.auth_inv_aceptar`` y ``app.auth_usuario_nuevo``.
- ``crear_tenant(p_nombre, p_email, p_clave)`` -> ``tenant_id``. GUC:
  ``app.auth_tenant_nuevo``.

Cuerpo (R4c, C2, I6): ``plpgsql``, ``STRICT``, ``SET search_path = pg_catalog,
pg_temp``, todo calificado con esquema, SQL estático (sin ``EXECUTE`` ni
``format``). Cada función **vacía las seis GUC** ``app.auth_*`` al empezar,
fija solo las suyas con valores que ella calcula (el parámetro validado o el
``id`` que ella misma genera) y las vuelve a vaciar antes de devolver: nunca lee
una GUC (no hay ``current_setting``) ni depende de una que quien llama fijó de
antemano, y no deja contexto utilizable. Las GUC son locales a la transacción
(``set_config(..., true)``): no sobreviven a ``COMMIT``/``ROLLBACK`` y un
``ROLLBACK TO SAVEPOINT`` las devuelve a su valor anterior.

- ``buscar_login``: solo lectura del email exacto; una fila por membresía
  activa, o una fila con ``tenant_id``/``rol`` nulos si no tiene ninguna activa
  (el login responde genérico y falla cerrado con más de una, Q6).
- ``validar_invitacion``: solo ``true``/``false``; clave con otro formato que hex
  minúsculo de 64 caracteres -> ``false``. No consume.
- ``aceptar_invitacion`` (Q4=B, Q16): ``UPDATE`` condicional de la invitación
  (``usada_en = now()``) con ``RETURNING email, tenant_id, rol``; ``INSERT
  usuario`` con el email de la invitación y un ``id`` generado aquí, ``ON
  CONFLICT DO NOTHING`` (sin política ``SELECT``); si no insertó, excepción
  estática ``invitacion_invalida`` que revierte el consumo; luego fija
  ``app.auth_usuario_nuevo`` con ese ``id`` e inserta la ``membresia``. Clave
  inexistente, usada, vencida o mal formada -> cero filas, nada creado.
- ``crear_tenant`` (R6, Q3, Q21): ``INSERT tenant`` con un ``id`` generado aquí
  e ``INSERT invitacion`` ``admin``, ``creada_por`` NULL, 24 h; si la segunda
  falla, revierte todo. Clave mal formada -> excepción ``clave_invalida``.

Orden (C3): ``CREATE FUNCTION`` -> ``REVOKE ALL`` de ``PUBLIC`` y de ``anon``,
``authenticated`` y ``service_role`` (si existen) -> ``GRANT EXECUTE`` de las
tres de login/invitación al rol de la aplicación -> ``GRANT CREATE ON SCHEMA
acceso`` a ``auth_owner`` y membresía transitoria del migrador en
``auth_owner`` ``WITH INHERIT FALSE, SET TRUE`` -> ``ALTER FUNCTION ... OWNER TO
auth_owner`` -> ``GRANT EXECUTE`` de ``crear_tenant`` al migrador -> ``REVOKE
CREATE`` y fin de la membresía, de inmediato (C5). El ``GRANT EXECUTE`` de
``crear_tenant`` va **después** del cambio de dueño y como ``auth_owner`` (``SET
LOCAL ROLE``, gracias a la membresía ``SET``): antes, el migrador es el dueño y
``ALTER FUNCTION ... OWNER`` traspasa a ``auth_owner`` lo concedido al dueño
anterior, así que el migrador se quedaría sin ``EXECUTE``.

La migración falla con mensaje claro si ``auth_owner`` no existe o no es un rol
inerte (sin ``SUPERUSER``, ``BYPASSRLS``, ``LOGIN``, ``CREATEROLE``,
``CREATEDB`` ni ``REPLICATION``, y sin membresía en otro rol; un rol inexistente
cuenta como inseguro), si el rol de la aplicación es miembro (directo o
indirecto) de ``auth_owner`` (A6), si el servidor es
anterior a PostgreSQL 16 (sin ``WITH INHERIT FALSE, SET TRUE``) o si al
terminar ``auth_owner`` conserva ``CREATE`` en ``acceso`` o el migrador sigue
siendo miembro de ``auth_owner`` (p. ej. una membresía previa como la de
``createrole_self_grant`` en Supabase, C8). El ``downgrade`` borra las cuatro
funciones como ``auth_owner`` con la misma membresía transitoria; el esquema
``acceso`` lo borra 0002 (``DROP SCHEMA`` sin ``CASCADE``: falla si queda algo).

Revision ID: 0004_funciones_de_acceso
Revises: 0003_politicas_del_dueno
Create Date: 2026-11-12
"""

import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0004_funciones_de_acceso"
down_revision: str | Sequence[str] | None = "0003_politicas_del_dueno"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE_VAR = "APP_DB_USER"
AUTH_OWNER = "auth_owner"
SUPABASE_ROLES = ("anon", "authenticated", "service_role")

BUSCAR_LOGIN = "acceso.buscar_login(text)"
VALIDAR_INVITACION = "acceso.validar_invitacion(text)"
ACEPTAR_INVITACION = "acceso.aceptar_invitacion(text, text, text)"
CREAR_TENANT = "acceso.crear_tenant(text, text, text)"
APP_FUNCTIONS = (BUSCAR_LOGIN, VALIDAR_INVITACION, ACEPTAR_INVITACION)
FUNCTIONS = (*APP_FUNCTIONS, CREAR_TENANT)

# Todas las GUC de las políticas del dueño (0003): cada función las vacía.
OWNER_GUCS = (
    "app.auth_email",
    "app.auth_usuario",
    "app.auth_inv_validar",
    "app.auth_inv_aceptar",
    "app.auth_usuario_nuevo",
    "app.auth_tenant_nuevo",
)

_CLEAR = (
    "PERFORM pg_catalog.set_config(g, '', true) "
    "FROM pg_catalog.unnest(ARRAY['" + "', '".join(OWNER_GUCS) + "']::text[]) AS g;"
)
_KEY_FORMAT = "'^[0-9a-f]{64}$'"
_HEADER = "LANGUAGE plpgsql STRICT SECURITY DEFINER SET search_path = pg_catalog, pg_temp"

CREATE_BUSCAR_LOGIN = f"""
CREATE FUNCTION {BUSCAR_LOGIN.replace("(text)", "(p_email text)")}
RETURNS TABLE (usuario_id uuid, password_hash text, activo boolean, tenant_id uuid, rol text)
{_HEADER}
AS $fn$
DECLARE
    v_id uuid;
    v_hash text;
    v_activo boolean;
BEGIN
    {_CLEAR}
    PERFORM pg_catalog.set_config('app.auth_email', p_email, true);
    SELECT u.id, u.password_hash, u.activo INTO v_id, v_hash, v_activo
        FROM public.usuario AS u WHERE u.email = p_email;
    IF FOUND THEN
        PERFORM pg_catalog.set_config('app.auth_usuario', v_id::text, true);
        RETURN QUERY SELECT v_id, v_hash, v_activo, m.tenant_id, m.rol
            FROM public.membresia AS m WHERE m.usuario_id = v_id AND m.activa;
        IF NOT FOUND THEN
            RETURN QUERY SELECT v_id, v_hash, v_activo, NULL::uuid, NULL::text;
        END IF;
    END IF;
    {_CLEAR}
    RETURN;
END
$fn$
"""  # noqa: S608 - solo constantes del módulo

CREATE_VALIDAR_INVITACION = f"""
CREATE FUNCTION {VALIDAR_INVITACION.replace("(text)", "(p_clave text)")}
RETURNS boolean
{_HEADER}
AS $fn$
DECLARE
    v_vigente boolean;
BEGIN
    {_CLEAR}
    IF p_clave !~ {_KEY_FORMAT} THEN
        RETURN false;
    END IF;
    PERFORM pg_catalog.set_config('app.auth_inv_validar', p_clave, true);
    v_vigente := EXISTS (
        SELECT 1 FROM public.invitacion AS i
        WHERE i.token_hash = pg_catalog.sha256(pg_catalog.decode(p_clave, 'hex'))
          AND i.usada_en IS NULL AND i.expira_en > pg_catalog.now()
    );
    {_CLEAR}
    RETURN v_vigente;
END
$fn$
"""  # noqa: S608 - solo constantes del módulo

CREATE_ACEPTAR_INVITACION = f"""
CREATE FUNCTION acceso.aceptar_invitacion(p_clave text, p_nombre text, p_password_hash text)
RETURNS TABLE (usuario_id uuid, tenant_id uuid, rol text)
{_HEADER}
AS $fn$
DECLARE
    v_email text;
    v_tenant uuid;
    v_rol text;
    v_usuario uuid;
    v_filas bigint;
BEGIN
    {_CLEAR}
    IF p_clave !~ {_KEY_FORMAT} THEN
        RETURN;
    END IF;
    PERFORM pg_catalog.set_config('app.auth_inv_aceptar', p_clave, true);
    UPDATE public.invitacion AS i SET usada_en = pg_catalog.now()
        WHERE i.token_hash = pg_catalog.sha256(pg_catalog.decode(p_clave, 'hex'))
          AND i.usada_en IS NULL AND i.expira_en > pg_catalog.now()
        RETURNING i.email, i.tenant_id, i.rol INTO v_email, v_tenant, v_rol;
    IF NOT FOUND THEN
        {_CLEAR}
        RETURN;
    END IF;
    v_usuario := pg_catalog.gen_random_uuid();
    INSERT INTO public.usuario (id, email, nombre, password_hash)
        VALUES (v_usuario, v_email, p_nombre, p_password_hash)
        ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_filas = ROW_COUNT;
    IF v_filas <> 1 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'invitacion_invalida';
    END IF;
    PERFORM pg_catalog.set_config('app.auth_usuario_nuevo', v_usuario::text, true);
    INSERT INTO public.membresia (tenant_id, usuario_id, rol) VALUES (v_tenant, v_usuario, v_rol);
    {_CLEAR}
    RETURN QUERY SELECT v_usuario, v_tenant, v_rol;
END
$fn$
"""  # noqa: S608 - solo constantes del módulo

CREATE_CREAR_TENANT = f"""
CREATE FUNCTION acceso.crear_tenant(p_nombre text, p_email text, p_clave text)
RETURNS uuid
{_HEADER}
AS $fn$
DECLARE
    v_tenant uuid;
BEGIN
    {_CLEAR}
    IF p_clave !~ {_KEY_FORMAT} THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'clave_invalida';
    END IF;
    v_tenant := pg_catalog.gen_random_uuid();
    PERFORM pg_catalog.set_config('app.auth_tenant_nuevo', v_tenant::text, true);
    INSERT INTO public.tenant (id, nombre) VALUES (v_tenant, p_nombre);
    INSERT INTO public.invitacion (tenant_id, email, rol, token_hash, expira_en)
        VALUES (v_tenant, p_email, 'admin',
                pg_catalog.sha256(pg_catalog.decode(p_clave, 'hex')),
                pg_catalog.now() + pg_catalog.make_interval(hours => 24));
    {_CLEAR}
    RETURN v_tenant;
END
$fn$
"""  # noqa: S608 - solo constantes del módulo

CREATE_STATEMENTS = (
    CREATE_BUSCAR_LOGIN,
    CREATE_VALIDAR_INVITACION,
    CREATE_ACEPTAR_INVITACION,
    CREATE_CREAR_TENANT,
)

_ROLE_EXISTS = text("select exists (select 1 from pg_roles where rolname = :name)")
_ROLE_SKIPS_RLS = text("select rolsuper or rolbypassrls from pg_roles where rolname = :name")
# Inseguro: se salta RLS, inicia sesión, crea roles o bases, replica o hereda de otro rol.
# Un rol inexistente cuenta como inseguro (falla cerrado): coalesce(..., true).
_ROLE_UNSAFE = text(
    "select coalesce((select r.rolsuper or r.rolbypassrls or r.rolcanlogin or r.rolcreaterole "
    "or r.rolcreatedb or r.rolreplication "
    "or exists (select 1 from pg_auth_members m where m.member = r.oid) "
    "from pg_roles r where r.rolname = :name), true)"
)
# Miembro directo o indirecto: la aplicación podría hacer SET ROLE al dueño (A6).
_APP_IS_OWNER_MEMBER = text("select pg_has_role(:app, :owner, 'MEMBER')")
_MIGRATOR_IS_MEMBER = text(
    "select exists (select 1 from pg_auth_members m "
    "where m.roleid = to_regrole(:owner) and m.member = to_regrole(current_user))"
)
_OWNER_CAN_CREATE = text(
    "select case when to_regnamespace('acceso') is null then false "
    "else has_schema_privilege(:owner, 'acceso', 'CREATE') end"
)


def require_auth_owner(conn: Connection, name: str | None = None) -> None:
    """Falla con un mensaje claro si no existe ``auth_owner`` (P0, plan.md §2.1)."""
    if not conn.scalar(_ROLE_EXISTS, {"name": name or AUTH_OWNER}):
        raise RuntimeError(
            f"Falta el rol {AUTH_OWNER}: créalo con docker/postgres/init/01-app-role.sh "
            "(spec 002, P0) antes de migrar."
        )


def require_owner_attributes(conn: Connection, name: str | None = None) -> None:
    """Falla si el dueño de las funciones de acceso no es un rol inerte (I3, R4a).

    El mensaje no lleva el nombre del rol: solo qué atributos se exigen.
    """
    if conn.scalar(_ROLE_UNSAFE, {"name": name or AUTH_OWNER}):
        raise RuntimeError(
            "El rol dueño de las funciones de acceso no es seguro: no puede ser "
            "SUPERUSER, tener BYPASSRLS, LOGIN, CREATEROLE, CREATEDB ni REPLICATION, "
            "ni tener membresía en otro rol. Corrígelo con docker/postgres/init/01-app-role.sh "
            "(spec 002, P0) antes de migrar."
        )


def require_postgres_16(conn: Connection) -> None:
    """``WITH INHERIT FALSE, SET TRUE`` en ``GRANT`` de roles exige PostgreSQL 16 o superior."""
    if int(conn.scalar(text("show server_version_num"))) < 160000:
        raise RuntimeError(
            "La migración 0004 exige PostgreSQL 16 o superior (membresía transitoria "
            "WITH INHERIT FALSE, SET TRUE; plan.md §2.1)."
        )


def _app_role(conn: Connection) -> str:
    """Rol de la aplicación desde ``APP_DB_USER``; nunca muestra su valor."""
    name = (os.environ.get(APP_ROLE_VAR) or "").strip()
    if not name:
        raise RuntimeError(
            f"Falta la variable de entorno {APP_ROLE_VAR} (rol de la aplicación) para migrar."
        )
    if name == AUTH_OWNER or name == conn.scalar(text("select current_user")):
        raise RuntimeError(
            f"{APP_ROLE_VAR} no puede ser {AUTH_OWNER} ni el rol migrador que ejecuta Alembic."
        )
    if not conn.scalar(_ROLE_EXISTS, {"name": name}):
        raise RuntimeError(
            f"El rol de la aplicación indicado en {APP_ROLE_VAR} no existe en la base: "
            "créalo con docker/postgres/init/01-app-role.sh antes de migrar."
        )
    if conn.scalar(_ROLE_SKIPS_RLS, {"name": name}):
        raise RuntimeError(
            f"El rol de la aplicación indicado en {APP_ROLE_VAR} es superusuario o tiene "
            "BYPASSRLS y se saltaría la RLS: déjalo NOSUPERUSER NOBYPASSRLS "
            "(docker/postgres/init/01-app-role.sh) antes de migrar."
        )
    if conn.scalar(_APP_IS_OWNER_MEMBER, {"app": name, "owner": AUTH_OWNER}):
        raise RuntimeError(
            f"El rol de la aplicación indicado en {APP_ROLE_VAR} es miembro del rol dueño de "
            "las funciones de acceso y podría actuar como él (A6): quita esa membresía antes "
            "de migrar."
        )
    return name


def require_no_leftover_privileges(conn: Connection) -> None:
    """C5: al terminar, ``auth_owner`` sin ``CREATE`` en ``acceso`` y el migrador no es miembro."""
    if conn.scalar(_OWNER_CAN_CREATE, {"owner": AUTH_OWNER}) or conn.scalar(
        _MIGRATOR_IS_MEMBER, {"owner": AUTH_OWNER}
    ):
        raise RuntimeError(
            "Tras la migración 0004, el rol dueño de las funciones de acceso conserva CREATE "
            "en el esquema acceso o el rol migrador sigue siendo miembro de él (p. ej. una "
            "membresía previa de createrole_self_grant en Supabase, C8): quítala antes de migrar."
        )


def execute_statements(conn: Connection, statements: Sequence[str]) -> None:
    """Ejecuta DDL tal cual, sin parámetros, y falla sin mostrar la sentencia."""
    for index, statement in enumerate(statements, start=1):
        failure = None
        try:
            conn.exec_driver_sql(statement, execution_options={"no_parameters": True})
        except SQLAlchemyError as exc:
            sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None) or "desconocido"
            failure = (
                f"La migración 0004 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def _transient_membership(owner: str, migrator: str) -> tuple[list[str], list[str]]:
    """Sentencias para abrir y cerrar la membresía transitoria (plan.md §2.1)."""
    opening = [f"GRANT {owner} TO {migrator} WITH INHERIT FALSE, SET TRUE"]
    closing = [f"REVOKE {owner} FROM {migrator}"]
    return opening, closing


def upgrade() -> None:
    conn = op.get_bind()
    require_auth_owner(conn)
    require_owner_attributes(conn)
    require_postgres_16(conn)
    quote = conn.dialect.identifier_preparer.quote
    app = quote(_app_role(conn))
    owner = quote(AUTH_OWNER)
    migrator = quote(conn.scalar(text("select current_user")))
    revoked = ["PUBLIC"] + [
        quote(role) for role in SUPABASE_ROLES if conn.scalar(_ROLE_EXISTS, {"name": role})
    ]
    opening, closing = _transient_membership(owner, migrator)

    statements = [*CREATE_STATEMENTS]
    statements += [f"REVOKE ALL ON FUNCTION {fn} FROM {', '.join(revoked)}" for fn in FUNCTIONS]
    statements += [f"GRANT EXECUTE ON FUNCTION {fn} TO {app}" for fn in APP_FUNCTIONS]
    statements += [f"GRANT CREATE ON SCHEMA acceso TO {owner}", *opening]
    statements += [f"ALTER FUNCTION {fn} OWNER TO {owner}" for fn in FUNCTIONS]
    statements += [
        # Como auth_owner (ya dueña): el EXECUTE del migrador no se traspasa al cambiar
        # de dueño. Ver el docstring.
        f"SET LOCAL ROLE {owner}",
        f"GRANT EXECUTE ON FUNCTION {CREAR_TENANT} TO {migrator}",
        "RESET ROLE",
        f"REVOKE CREATE ON SCHEMA acceso FROM {owner}",
        *closing,
    ]
    execute_statements(conn, statements)
    require_no_leftover_privileges(conn)


def downgrade() -> None:
    conn = op.get_bind()
    require_auth_owner(conn)
    require_postgres_16(conn)
    quote = conn.dialect.identifier_preparer.quote
    owner = quote(AUTH_OWNER)
    migrator = quote(conn.scalar(text("select current_user")))
    opening, closing = _transient_membership(owner, migrator)
    # Solo el dueño (auth_owner) puede borrarlas: SET LOCAL ROLE con la membresía SET.
    statements = [*opening, f"SET LOCAL ROLE {owner}"]
    statements += [f"DROP FUNCTION {fn}" for fn in FUNCTIONS]
    statements += ["RESET ROLE", *closing]
    execute_statements(conn, statements)
    require_no_leftover_privileges(conn)
