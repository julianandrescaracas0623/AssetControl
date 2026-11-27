"""Cambiar rol y activar o desactivar a una persona desde la consola de la empresa.

Lo que la consola de plataforma ya hace (0027 y 0031) para un tenant, esta migración lo
hace para el admin de la propia empresa, dentro de su ``tenant_session``:

- ``acceso.cambiar_membresia(p_tenant, p_actor, p_usuario, p_rol, p_activa)`` -> una fila
  ``(rol_resultado, activa_resultado, cambiado)``. Mismo patrón que 0024 y 0026
  (``plpgsql``, ``SECURITY DEFINER``, ``STRICT``, ``SET search_path = pg_catalog,
  pg_temp``, ``SET lock_timeout``, todo calificado, SQL estático, dueña ``auth_owner``,
  ``EXECUTE`` solo para la aplicación).
  - Toma el candado **exclusivo** por tenant ``plataforma_membresia:<tenant>`` (el mismo
    de 0027 y 0031: login y refresh lo toman en compartido), así un cambio no adelanta el
    conteo de admins de otro en curso.
  - Quien llama debe ser admin **activo** del tenant (``42501 no_autorizado``) y no puede
    ser la persona que cambia (``P0001 cambio_propio_no_permitido``: no se cambia el propio
    rol ni se desactiva uno mismo, para no quedarse fuera por error).
  - ``P0002 usuario_no_encontrado`` si esa persona no tiene membresía en el tenant.
  - Quitar el rol admin o desactivar al **último** admin activo -> ``P0001 ultimo_admin``.
  - Idéntico no escribe (``cambiado = false``). Si cambia algo, escribe ``rol`` y
    ``activa`` solo si difieren.
  - Si se desactiva o cambia el rol, revoca los refresh de esa membresía con el mismo bucle
    acotado y fallo cerrado de 0027 (``55P03 membresia_ocupada`` sin cambiar nada).
  - Un cambio de rol o de activación no toca ``usuario`` (ni contraseña ni corte de JWT):
    ``load_current_user`` lee ``membresia.rol`` y ``membresia.activa`` en cada petición, así
    que el acceso de un JWT vigente cambia en la siguiente llamada.
  - ``lock_timeout`` ``5s``: un candado que no llega a tiempo da ``55P03`` (``503``).

- Políticas nuevas **solo para** ``auth_owner``, acotadas por las GUC de la función:
  ``membresia`` ``FOR SELECT`` (las del tenant de la GUC) y ``FOR UPDATE`` (la del usuario
  de la GUC dentro de ese tenant), y ``refresh_token`` ``FOR SELECT`` y ``FOR UPDATE`` (solo
  las de esa membresía). Ninguna política ``FOR ALL`` ni ``PUBLIC``.
- ``GRANT UPDATE (rol, activa) ON membresia TO auth_owner``: nada más. La aplicación no
  recibe ningún ``UPDATE`` ni ``INSERT`` nuevo sobre tablas.

Residual conocido: esta acción no deja registro de auditoría propio de la empresa (la
``plataforma_auditoria`` es solo de la consola).

``downgrade``: borra la función como ``auth_owner``, sus cuatro políticas y el ``GRANT``. No
borra datos: los roles y activaciones cambiados se conservan.

Revision ID: 0033_usuarios_cambiar_membresia
Revises: 0032_plataforma_password_usuario
Create Date: 2026-11-25
"""

import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0033_usuarios_cambiar_membresia"
down_revision: str | Sequence[str] | None = "0032_plataforma_password_usuario"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE_VAR = "APP_DB_USER"
AUTH_OWNER = "auth_owner"
SUPABASE_ROLES = ("anon", "authenticated", "service_role")
FUNCTION = "acceso.cambiar_membresia(uuid, uuid, uuid, text, boolean)"

# GUC propias de esta función: el tenant y la persona cuya membresía se cambia.
TENANT_GUC = "app.auth_membresia_tenant"
USUARIO_GUC = "app.auth_membresia_usuario"

# Las doce GUC de 0004–0026 más las dos de aquí: la función las vacía al empezar y al acabar.
AUTH_GUCS = (
    "app.auth_email",
    "app.auth_usuario",
    "app.auth_inv_validar",
    "app.auth_inv_aceptar",
    "app.auth_usuario_nuevo",
    "app.auth_tenant_nuevo",
    "app.auth_rec_email",
    "app.auth_rec_usuario",
    "app.auth_rec_clave",
    "app.auth_reset_clave",
    "app.auth_reset_usuario",
    "app.auth_cambio_usuario",
    TENANT_GUC,
    USUARIO_GUC,
)

# (tabla, política): lista cerrada (la fijan los tests de catálogo y de migraciones).
POLICIES = (
    ("membresia", "dueno_membresia_cambiar_leer"),
    ("membresia", "dueno_membresia_cambiar"),
    ("refresh_token", "dueno_refresh_cambiar_leer"),
    ("refresh_token", "dueno_refresh_cambiar_revocar"),
)

# Espera máxima del candado exclusivo y del lock_timeout de la función: como 0027.
LOCK_TIMEOUT = "5s"
# Pasadas máximas de la revocación de refresh: como 0027.
REVOKE_MAX_PASSES = 10

_UUID = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def uuid_setting(guc: str) -> str:
    """UUID de ``guc``; ``NULL`` si falta o no es un UUID en minúsculas (como 0018 y 0031)."""
    value = f"pg_catalog.current_setting('{guc}', true)"
    return f"(CASE WHEN {value} ~ '{_UUID}' THEN ({value})::uuid END)"


TENANT = uuid_setting(TENANT_GUC)
USUARIO = uuid_setting(USUARIO_GUC)

_CLEAR = (
    "PERFORM pg_catalog.set_config(g, '', true) "
    "FROM pg_catalog.unnest(ARRAY['" + "', '".join(AUTH_GUCS) + "']::text[]) AS g;"
)
_HEADER = "LANGUAGE plpgsql STRICT SECURITY DEFINER SET search_path = pg_catalog, pg_temp"

CREATE_FUNCTION = f"""
CREATE FUNCTION acceso.cambiar_membresia(
    p_tenant uuid, p_actor uuid, p_usuario uuid, p_rol text, p_activa boolean)
RETURNS TABLE (rol_resultado text, activa_resultado boolean, cambiado boolean)
{_HEADER}
SET lock_timeout = '{LOCK_TIMEOUT}'
AS $fn$
DECLARE
    v_membresia uuid;
    v_rol text;
    v_activa boolean;
    v_admins_otros bigint;
    v_pasada integer;
    v_revocados bigint;
BEGIN
    {_CLEAR}
    PERFORM pg_catalog.set_config('{TENANT_GUC}', p_tenant::text, true);
    PERFORM pg_catalog.set_config('{USUARIO_GUC}', p_usuario::text, true);
    -- Mismo candado exclusivo por tenant que 0027 y 0031 (login y refresh lo toman compartido).
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('plataforma_membresia:' || p_tenant::text, 0));
    PERFORM 1 FROM public.membresia AS m
        WHERE m.tenant_id = p_tenant AND m.usuario_id = p_actor
          AND m.rol = 'admin' AND m.activa;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'no_autorizado';
    END IF;
    IF p_actor = p_usuario THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'cambio_propio_no_permitido';
    END IF;
    SELECT m.id, m.rol, m.activa INTO v_membresia, v_rol, v_activa
        FROM public.membresia AS m
        WHERE m.tenant_id = p_tenant AND m.usuario_id = p_usuario;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'usuario_no_encontrado';
    END IF;
    IF v_rol = p_rol AND v_activa = p_activa THEN
        {_CLEAR}
        RETURN QUERY SELECT v_rol, v_activa, false;
        RETURN;
    END IF;
    -- Quitar el rol admin o desactivar a un admin activo: debe quedar otro admin activo.
    -- Con la comprobación del actor (admin activo y distinto de quien cambia) esta guardia
    -- nunca se dispara hoy; se mantiene como defensa si esa regla cambia.
    IF v_rol = 'admin' AND v_activa AND NOT (p_rol = 'admin' AND p_activa) THEN
        SELECT pg_catalog.count(*) INTO v_admins_otros FROM public.membresia AS m
            WHERE m.tenant_id = p_tenant AND m.rol = 'admin' AND m.activa
              AND m.usuario_id <> p_usuario;
        IF v_admins_otros = 0 THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ultimo_admin';
        END IF;
    END IF;
    UPDATE public.membresia AS m SET rol = p_rol, activa = p_activa WHERE m.id = v_membresia;
    IF NOT p_activa OR p_rol <> v_rol THEN
        -- Se repite hasta que no afecte filas: cada pasada ve lo confirmado antes de
        -- empezar, así un sucesor insertado por una rotación que confirmó mientras se
        -- esperaba su candado se revoca en la pasada siguiente.
        FOR v_pasada IN 1..{REVOKE_MAX_PASSES} LOOP
            UPDATE public.refresh_token AS t SET revocado_en = pg_catalog.now()
                WHERE t.membresia_id = v_membresia AND t.revocado_en IS NULL;
            GET DIAGNOSTICS v_revocados = ROW_COUNT;
            EXIT WHEN v_revocados = 0;
        END LOOP;
        IF v_revocados <> 0 THEN
            -- Falla cerrado: no se cambia dejando una familia viva.
            RAISE EXCEPTION USING ERRCODE = '55P03', MESSAGE = 'membresia_ocupada';
        END IF;
    END IF;
    {_CLEAR}
    RETURN QUERY SELECT p_rol, p_activa, true;
    RETURN;
EXCEPTION WHEN lock_not_available THEN
    RAISE EXCEPTION USING ERRCODE = '55P03', MESSAGE = 'membresia_ocupada';
END
$fn$
"""  # noqa: S608 - solo constantes del módulo

_ROLE_EXISTS = text("select exists (select 1 from pg_roles where rolname = :name)")
_ROLE_SKIPS_RLS = text("select rolsuper or rolbypassrls from pg_roles where rolname = :name")
_ROLE_UNSAFE = text(
    "select coalesce((select r.rolsuper or r.rolbypassrls or r.rolcanlogin or r.rolcreaterole "
    "or r.rolcreatedb or r.rolreplication "
    "or exists (select 1 from pg_auth_members m where m.member = r.oid) "
    "from pg_roles r where r.rolname = :name), true)"
)
_APP_IS_OWNER_MEMBER = text("select pg_has_role(:app, :owner, 'MEMBER')")
# Igual que 0004/0016/0024/0026 (C8): por rolname exacto.
_MIGRATOR_IS_MEMBER = text(
    "select exists (select 1 from pg_auth_members m "
    "where m.roleid = (select oid from pg_roles where rolname = :owner) "
    "and m.member = (select oid from pg_roles where rolname = current_user) "
    "and (m.inherit_option or m.set_option or m.grantor = m.member "
    "or m.grantor = (select oid from pg_roles where rolname = current_user)))"
)
_OWNER_CAN_CREATE = text(
    "select case when to_regnamespace('acceso') is null then false "
    "else has_schema_privilege(:owner, 'acceso', 'CREATE') end"
)


def _de_la_membresia(tabla: str) -> str:
    """Un refresh de ``tabla`` de la membresía de la GUC de usuario dentro de la GUC de tenant."""
    return (
        f"EXISTS (SELECT 1 FROM membresia m WHERE m.id = {tabla}.membresia_id "  # noqa: S608
        f"AND m.tenant_id = {tabla}.tenant_id AND m.tenant_id = {TENANT} "
        f"AND m.usuario_id = {USUARIO})"
    )


def _policies(owner: str) -> list[str]:
    return [
        f"CREATE POLICY dueno_membresia_cambiar_leer ON membresia FOR SELECT TO {owner} "  # noqa: S608
        f"USING (tenant_id = {TENANT})",
        f"CREATE POLICY dueno_membresia_cambiar ON membresia FOR UPDATE TO {owner} "  # noqa: S608
        f"USING (tenant_id = {TENANT} AND usuario_id = {USUARIO}) "
        f"WITH CHECK (tenant_id = {TENANT} AND usuario_id = {USUARIO})",
        f"CREATE POLICY dueno_refresh_cambiar_leer ON refresh_token FOR SELECT TO {owner} "  # noqa: S608
        f"USING ({_de_la_membresia('refresh_token')})",
        f"CREATE POLICY dueno_refresh_cambiar_revocar ON refresh_token FOR UPDATE TO {owner} "  # noqa: S608
        f"USING (revocado_en IS NULL AND {_de_la_membresia('refresh_token')}) "
        "WITH CHECK (revocado_en = now())",
    ]


def require_auth_owner(conn: Connection) -> None:
    """Falla con un mensaje claro si falta ``auth_owner`` o no es un rol inerte."""
    if not conn.scalar(_ROLE_EXISTS, {"name": AUTH_OWNER}):
        raise RuntimeError(
            f"Falta el rol {AUTH_OWNER}: créalo con docker/postgres/init/01-app-role.sh "
            "(o flask preparar-roles en un PostgreSQL administrado) antes de migrar."
        )
    if conn.scalar(_ROLE_UNSAFE, {"name": AUTH_OWNER}):
        raise RuntimeError(
            "El rol dueño de las funciones de acceso no es seguro: no puede ser "
            "SUPERUSER, tener BYPASSRLS, LOGIN, CREATEROLE, CREATEDB ni REPLICATION, "
            "ni tener membresía en otro rol. Corrígelo con "
            "docker/postgres/init/01-app-role.sh antes de migrar."
        )


def require_postgres_16(conn: Connection) -> None:
    """``WITH INHERIT FALSE, SET TRUE`` exige PostgreSQL 16 o superior."""
    if int(conn.scalar(text("show server_version_num"))) < 160000:
        raise RuntimeError(
            "La migración 0033 exige PostgreSQL 16 o superior (membresía transitoria "
            "WITH INHERIT FALSE, SET TRUE; plan.md §2.1 de la spec 002)."
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
            "las funciones de acceso y podría actuar como él: quita esa membresía antes "
            "de migrar."
        )
    return name


def require_no_leftover_privileges(conn: Connection) -> None:
    """C5: al terminar, ``auth_owner`` sin ``CREATE`` en ``acceso`` y el migrador no es miembro."""
    if conn.scalar(_OWNER_CAN_CREATE, {"owner": AUTH_OWNER}) or conn.scalar(
        _MIGRATOR_IS_MEMBER, {"owner": AUTH_OWNER}
    ):
        raise RuntimeError(
            "Tras la migración 0033, el rol dueño de las funciones de acceso conserva CREATE "
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
                f"La migración 0033 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def _transient_membership(owner: str, migrator: str) -> tuple[list[str], list[str]]:
    opening = [f"GRANT {owner} TO {migrator} WITH INHERIT FALSE, SET TRUE"]
    closing = [f"REVOKE {owner} FROM {migrator}"]
    return opening, closing


def _roles(conn: Connection) -> tuple[str, str, str]:
    require_auth_owner(conn)
    require_postgres_16(conn)
    quote = conn.dialect.identifier_preparer.quote
    app = quote(_app_role(conn))
    owner = quote(AUTH_OWNER)
    migrator = quote(conn.scalar(text("select current_user")))
    return app, owner, migrator


def upgrade() -> None:
    conn = op.get_bind()
    app, owner, migrator = _roles(conn)
    quote = conn.dialect.identifier_preparer.quote
    revoked = ["PUBLIC"] + [
        quote(role) for role in SUPABASE_ROLES if conn.scalar(_ROLE_EXISTS, {"name": role})
    ]
    opening, closing = _transient_membership(owner, migrator)
    statements = [
        *_policies(owner),
        f"GRANT UPDATE (rol, activa) ON membresia TO {owner}",
        CREATE_FUNCTION,
        f"REVOKE ALL ON FUNCTION {FUNCTION} FROM {', '.join(revoked)}",
        f"GRANT EXECUTE ON FUNCTION {FUNCTION} TO {app}",
        f"GRANT CREATE ON SCHEMA acceso TO {owner}",
        *opening,
        f"ALTER FUNCTION {FUNCTION} OWNER TO {owner}",
        f"REVOKE CREATE ON SCHEMA acceso FROM {owner}",
        *closing,
    ]
    execute_statements(conn, statements)
    require_no_leftover_privileges(conn)


def downgrade() -> None:
    conn = op.get_bind()
    app, owner, migrator = _roles(conn)
    opening, closing = _transient_membership(owner, migrator)
    # Solo el dueño (auth_owner) borra sus funciones: SET LOCAL ROLE, como en 0024.
    statements = [
        f"GRANT CREATE ON SCHEMA acceso TO {owner}",
        *opening,
        f"SET LOCAL ROLE {owner}",
        f"DROP FUNCTION {FUNCTION}",
        "RESET ROLE",
        f"REVOKE CREATE ON SCHEMA acceso FROM {owner}",
        *closing,
    ]
    statements += [f"DROP POLICY {policy} ON {table}" for table, policy in POLICIES]
    statements += [f"REVOKE UPDATE (rol, activa) ON membresia FROM {owner}"]
    execute_statements(conn, statements)
    require_no_leftover_privileges(conn)
