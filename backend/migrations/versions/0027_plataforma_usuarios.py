"""Funciones del módulo Usuarios de la consola (spec 017, T5).

``plan.md`` §2.3 y §5 (la fila ``0020_plataforma_usuarios``; el número 0020 no se usa: la
cadena sigue tras ``0026``); ``spec.md`` R29–R31, R36; A4, A5, A17. Mismo patrón que 0018.

Funciones nuevas (``plpgsql``, ``SECURITY DEFINER``, ``STRICT``, ``SET search_path =
pg_catalog, pg_temp``, todo calificado, SQL estático, dueña ``plataforma_owner``,
``EXECUTE`` solo para el rol de la aplicación). Cada una vacía al empezar y al terminar
**todas** las GUC ``app.plat_*`` (las cinco de 0017, las cinco de 0018 y las tres de
aquí), fija solo las suyas con valores que ella recibe y nunca lee una GUC. Su primera
comprobación (A5, R36): ``p_desarrollador`` existe y está activo; si no, ``42501
desarrollador_no_autorizado`` sin devolver filas ni escribir.

- ``acceso.plataforma_listar_usuarios(p_desarrollador, p_tenant)`` -> ``usuario_id``,
  ``nombre``, ``email``, ``rol``, ``activa``, ``debe_cambiar_password`` (R29), una fila por
  membresía del tenant. Nunca hash, token ni dato de negocio. Empresa inexistente ->
  ``P0002 empresa_no_encontrada``. **Hueco:** R29 pide también la «fecha de alta», pero
  ni ``membresia`` ni ``usuario`` tienen fecha (0002) y el plan §3 dice «``membresia``: sin
  cambio de esquema»; no se inventa una columna: queda como pregunta para el humano.
- ``acceso.plataforma_cambiar_estado_membresia(p_desarrollador, p_tenant, p_usuario,
  p_activa)`` -> una fila ``(estado, cambiado)`` (R30, R31): cambia solo
  ``membresia.activa`` de ese usuario en ese tenant y, al desactivar, revoca las familias
  de refresh de esa membresía. ``estado`` es el estado resultante y ``cambiado`` dice si
  hubo cambio real (repetir el estado actual no cambia nada y da ``cambiado = false``; la
  aplicación solo audita los cambios reales). Bajo un candado consultivo exclusivo por
  tenant (``hashtextextended('plataforma_membresia:' || tenant, 0)``): dos
  desactivaciones a la vez no dejan la empresa sin admin, y el login y el refresh del
  tenant toman el mismo candado **compartido** antes de leer la membresía
  (``app.auth.service``), así una sesión emitida a la vez que se desactiva o confirma
  antes (y aquí se revoca) o ya ve la membresía inactiva. La revocación se repite hasta
  que no afecte filas (máximo ``REVOKE_MAX_PASSES``; si aún afecta, falla cerrado). La
  función fija ``lock_timeout`` (``LOCK_TIMEOUT``): un candado que no llega a tiempo da
  ``55P03 membresia_ocupada`` sin cambiar nada. Rechazos, en este orden y sin cambiar
  nada: empresa inexistente -> ``P0002 empresa_no_encontrada``; el usuario no es de esa
  empresa -> ``P0002 usuario_no_encontrado``; empresa desactivada -> ``P0001
  empresa_inactiva`` (D9, en los dos sentidos); desactivar la última membresía ``admin``
  activa -> ``P0001 ultimo_admin`` (P31).

La auditoría (``usuario_desactivado``, ``usuario_reactivado``) la escribe la aplicación en
la misma transacción (``app.plataforma.auditoria``); la política de 0018 ya admite esas
acciones con ``tenant_id``.

Políticas ``TO plataforma_owner`` (una por comando, nunca ``FOR ALL`` ni ``PUBLIC``; GUC
validadas por formato: vacía o con otro formato -> ``NULL`` -> cero filas), todas con el
desarrollador de ``app.plat_actor`` activo. ``GRANT`` por columna mínimos, sin ``DELETE``:
``membresia`` ``SELECT (id, usuario_id)`` (además de lo de 0018) y ``UPDATE (activa)``;
``usuario`` ``SELECT (id, email, nombre, debe_cambiar_password)`` (nunca ``password_hash``
ni ``sesiones_validas_desde``); ``refresh_token`` ``SELECT (tenant_id, membresia_id,
revocado_en)`` y ``UPDATE (revocado_en)`` (nunca ``token_hash``).

Orden (C3/C5): políticas y ``GRANT`` -> ``CREATE FUNCTION`` -> ``REVOKE ALL`` de
``PUBLIC`` y de los roles de Supabase -> ``GRANT EXECUTE`` a la aplicación -> ``CREATE``
transitorio en ``acceso`` y membresía transitoria ``WITH INHERIT FALSE, SET TRUE`` ->
``OWNER TO plataforma_owner`` -> ``REVOKE CREATE`` y fin de la membresía; al terminar se
comprueba que no quede nada (C8).

``downgrade``: borra las dos funciones como ``plataforma_owner``, sus políticas y solo los
``GRANT`` de aquí. No borra datos: las membresías desactivadas siguen desactivadas.

Revision ID: 0027_plataforma_usuarios
Revises: 0026_sesiones_validas_desde
Create Date: 2026-11-20
"""

import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0027_plataforma_usuarios"
down_revision: str | Sequence[str] | None = "0026_sesiones_validas_desde"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE_VAR = "APP_DB_USER"
AUTH_OWNER = "auth_owner"
PLATAFORMA_OWNER = "plataforma_owner"
SUPABASE_ROLES = ("anon", "authenticated", "service_role")

LISTAR = "acceso.plataforma_listar_usuarios(uuid, uuid)"
CAMBIAR_ESTADO = "acceso.plataforma_cambiar_estado_membresia(uuid, uuid, uuid, boolean)"
FUNCTIONS = (LISTAR, CAMBIAR_ESTADO)

# Todas las GUC de las políticas de plataforma_owner (0017, 0018 y esta).
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

# (tabla, política): lista cerrada (la fijan test_plataforma_catalogo.py y test_migrations.py).
POLICIES = (
    ("tenant", "dueno_plat_tenant_usuarios"),
    ("membresia", "dueno_plat_membresia_usuarios"),
    ("usuario", "dueno_plat_usuario_usuarios"),
    ("tenant", "dueno_plat_tenant_membresia"),
    ("membresia", "dueno_plat_membresia_estado_leer"),
    ("membresia", "dueno_plat_membresia_estado"),
    ("refresh_token", "dueno_plat_refresh_membresia_leer"),
    ("refresh_token", "dueno_plat_refresh_membresia_revocar"),
)

_UUID = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def uuid_setting(guc: str) -> str:
    """UUID de ``guc``; ``NULL`` si falta o no es un UUID en minúsculas (como 0018)."""
    value = f"pg_catalog.current_setting('{guc}', true)"
    return f"(CASE WHEN {value} ~ '{_UUID}' THEN ({value})::uuid END)"


ACTOR = uuid_setting("app.plat_actor")
USUARIOS = uuid_setting("app.plat_usuarios")
MEM_TENANT = uuid_setting("app.plat_membresia_tenant")
MEM_USUARIO = uuid_setting("app.plat_membresia_usuario")
ACTOR_ACTIVO = f"EXISTS (SELECT 1 FROM desarrollador d WHERE d.id = {ACTOR} AND d.activo)"  # noqa: S608
# Refresh de la membresía objetivo (la de MEM_USUARIO en MEM_TENANT).
_DE_LA_MEMBRESIA = (
    f"tenant_id = {MEM_TENANT} AND EXISTS (SELECT 1 FROM membresia m "  # noqa: S608
    "WHERE m.id = refresh_token.membresia_id AND m.tenant_id = refresh_token.tenant_id "
    f"AND m.usuario_id = {MEM_USUARIO})"
)

_CLEAR = (
    "PERFORM pg_catalog.set_config(g, '', true) "
    "FROM pg_catalog.unnest(ARRAY['" + "', '".join(OWNER_GUCS) + "']::text[]) AS g;"
)
_HEADER = "LANGUAGE plpgsql STRICT SECURITY DEFINER SET search_path = pg_catalog, pg_temp"
# A5/R36: primera comprobación de cada función; excepción estática, sin datos (como 0018).
_DESARROLLADOR_ACTIVO = (
    "PERFORM pg_catalog.set_config('app.plat_actor', p_desarrollador::text, true);\n"
    "    SELECT d.activo INTO v_activo FROM public.desarrollador AS d "
    "WHERE d.id = p_desarrollador;\n"
    "    IF NOT FOUND OR NOT v_activo THEN\n"
    "        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'desarrollador_no_autorizado';\n"
    "    END IF;"
)  # noqa: S608 - solo constantes del módulo

CREATE_LISTAR = f"""
CREATE FUNCTION acceso.plataforma_listar_usuarios(p_desarrollador uuid, p_tenant uuid)
RETURNS TABLE (usuario_id uuid, nombre text, email text, rol text, activa boolean,
               debe_cambiar_password boolean)
{_HEADER}
AS $fn$
DECLARE
    v_activo boolean;
BEGIN
    {_CLEAR}
    {_DESARROLLADOR_ACTIVO}
    PERFORM pg_catalog.set_config('app.plat_usuarios', p_tenant::text, true);
    PERFORM 1 FROM public.tenant AS t WHERE t.id = p_tenant;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'empresa_no_encontrada';
    END IF;
    RETURN QUERY SELECT u.id, u.nombre, u.email, m.rol, m.activa, u.debe_cambiar_password
        FROM public.membresia AS m JOIN public.usuario AS u ON u.id = m.usuario_id
        WHERE m.tenant_id = p_tenant
        ORDER BY u.nombre, u.id;
    {_CLEAR}
    RETURN;
END
$fn$
"""  # noqa: S608 - solo constantes del módulo

# Espera máxima de cada candado dentro de la función (consultivo del tenant y filas de
# membresia/refresh_token): pasado este tiempo, ``55P03 membresia_ocupada`` (503 en la API).
LOCK_TIMEOUT = "5s"
# Pasadas máximas de la revocación de refresh: cada pasada con filas solo se debe a una
# rotación o un cambio de contraseña que confirmó mientras se esperaba un candado.
REVOKE_MAX_PASSES = 10

CREATE_CAMBIAR_ESTADO = f"""
CREATE FUNCTION acceso.plataforma_cambiar_estado_membresia(
    p_desarrollador uuid, p_tenant uuid, p_usuario uuid, p_activa boolean)
RETURNS TABLE (estado boolean, cambiado boolean)
{_HEADER}
SET lock_timeout = '{LOCK_TIMEOUT}'
AS $fn$
DECLARE
    v_activo boolean;
    v_tenant_activo boolean;
    v_membresia uuid;
    v_rol text;
    v_activa boolean;
    v_otros_admins bigint;
    v_pasada integer;
    v_revocados bigint;
BEGIN
    {_CLEAR}
    {_DESARROLLADOR_ACTIVO}
    PERFORM pg_catalog.set_config('app.plat_membresia_tenant', p_tenant::text, true);
    PERFORM pg_catalog.set_config('app.plat_membresia_usuario', p_usuario::text, true);
    -- Un cambio de membresía por tenant a la vez: el conteo de admins no se adelanta.
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('plataforma_membresia:' || p_tenant::text, 0));
    SELECT t.activo INTO v_tenant_activo FROM public.tenant AS t WHERE t.id = p_tenant;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'empresa_no_encontrada';
    END IF;
    SELECT m.id, m.rol, m.activa INTO v_membresia, v_rol, v_activa
        FROM public.membresia AS m WHERE m.tenant_id = p_tenant AND m.usuario_id = p_usuario;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'usuario_no_encontrado';
    END IF;
    IF NOT v_tenant_activo THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'empresa_inactiva';
    END IF;
    IF v_activa = p_activa THEN
        {_CLEAR}
        RETURN QUERY SELECT p_activa, false;
        RETURN;
    END IF;
    IF NOT p_activa AND v_rol = 'admin' THEN
        SELECT pg_catalog.count(*) INTO v_otros_admins FROM public.membresia AS m
            WHERE m.tenant_id = p_tenant AND m.rol = 'admin' AND m.activa
              AND m.usuario_id <> p_usuario;
        IF v_otros_admins = 0 THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ultimo_admin';
        END IF;
    END IF;
    UPDATE public.membresia AS m SET activa = p_activa
        WHERE m.tenant_id = p_tenant AND m.usuario_id = p_usuario AND m.activa <> p_activa;
    IF NOT p_activa THEN
        -- Se repite hasta que no afecte filas: cada pasada ve lo confirmado antes de
        -- empezar, así un sucesor insertado por una rotación que confirmó mientras se
        -- esperaba su candado se revoca en la pasada siguiente.
        FOR v_pasada IN 1..{REVOKE_MAX_PASSES} LOOP
            UPDATE public.refresh_token AS t SET revocado_en = pg_catalog.now()
                WHERE t.tenant_id = p_tenant AND t.membresia_id = v_membresia
                  AND t.revocado_en IS NULL;
            GET DIAGNOSTICS v_revocados = ROW_COUNT;
            EXIT WHEN v_revocados = 0;
        END LOOP;
        IF v_revocados <> 0 THEN
            -- Falla cerrado: no se desactiva dejando una familia viva.
            RAISE EXCEPTION USING ERRCODE = '55P03', MESSAGE = 'membresia_ocupada';
        END IF;
    END IF;
    {_CLEAR}
    RETURN QUERY SELECT p_activa, true;
    RETURN;
EXCEPTION WHEN lock_not_available THEN
    RAISE EXCEPTION USING ERRCODE = '55P03', MESSAGE = 'membresia_ocupada';
END
$fn$
"""  # noqa: S608 - solo constantes del módulo

CREATE_STATEMENTS = (CREATE_LISTAR, CREATE_CAMBIAR_ESTADO)

_ROLE_EXISTS = text("select exists (select 1 from pg_roles where rolname = :name)")
_ROLE_SKIPS_RLS = text("select rolsuper or rolbypassrls from pg_roles where rolname = :name")
_ROLE_UNSAFE = text(
    "select coalesce((select r.rolsuper or r.rolbypassrls or r.rolcanlogin or r.rolcreaterole "
    "or r.rolcreatedb or r.rolreplication "
    "or exists (select 1 from pg_auth_members m where m.member = r.oid) "
    "from pg_roles r where r.rolname = :name), true)"
)
_IS_MEMBER = text("select pg_has_role(:member, :owner, 'MEMBER')")
# Igual que 0004/0018 (C8): por rolname exacto; la membresía ADMIN del creador en Supabase,
# sin INHERIT ni SET y concedida por otro, no cuenta.
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


def require_owner(conn: Connection) -> None:
    """Falla con un mensaje claro si falta ``plataforma_owner`` o no es un rol inerte."""
    if not conn.scalar(_ROLE_EXISTS, {"name": PLATAFORMA_OWNER}):
        raise RuntimeError(
            f"Falta el rol {PLATAFORMA_OWNER}: créalo con docker/postgres/init/01-app-role.sh "
            "(o flask preparar-roles en un PostgreSQL administrado; spec 017) antes de migrar."
        )
    if conn.scalar(_ROLE_UNSAFE, {"name": PLATAFORMA_OWNER}):
        raise RuntimeError(
            "El rol dueño de las funciones de plataforma no es seguro: no puede ser "
            "SUPERUSER, tener BYPASSRLS, LOGIN, CREATEROLE, CREATEDB ni REPLICATION, "
            "ni tener membresía en otro rol. Corrígelo con "
            "docker/postgres/init/01-app-role.sh (spec 017) antes de migrar."
        )


def require_postgres_16(conn: Connection) -> None:
    """``WITH INHERIT FALSE, SET TRUE`` exige PostgreSQL 16 o superior."""
    if int(conn.scalar(text("show server_version_num"))) < 160000:
        raise RuntimeError(
            "La migración 0027 exige PostgreSQL 16 o superior (membresía transitoria "
            "WITH INHERIT FALSE, SET TRUE; plan.md §2.1 de la spec 002)."
        )


def _app_role(conn: Connection) -> str:
    """Rol de la aplicación desde ``APP_DB_USER``; nunca muestra su valor."""
    name = (os.environ.get(APP_ROLE_VAR) or "").strip()
    if not name:
        raise RuntimeError(
            f"Falta la variable de entorno {APP_ROLE_VAR} (rol de la aplicación) para migrar."
        )
    if name in (AUTH_OWNER, PLATAFORMA_OWNER) or name == conn.scalar(text("select current_user")):
        raise RuntimeError(
            f"{APP_ROLE_VAR} no puede ser {AUTH_OWNER}, {PLATAFORMA_OWNER} ni el rol migrador "
            "que ejecuta Alembic."
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
    if conn.scalar(_IS_MEMBER, {"member": name, "owner": PLATAFORMA_OWNER}):
        raise RuntimeError(
            f"El rol de la aplicación indicado en {APP_ROLE_VAR} es miembro del rol dueño "
            "de las funciones de plataforma y podría actuar como él: quita esa membresía "
            "antes de migrar."
        )
    return name


def require_no_leftover_privileges(conn: Connection) -> None:
    """C5: al terminar, el dueño sin ``CREATE`` en ``acceso`` y el migrador no es miembro."""
    if conn.scalar(_OWNER_CAN_CREATE, {"owner": PLATAFORMA_OWNER}) or conn.scalar(
        _MIGRATOR_IS_MEMBER, {"owner": PLATAFORMA_OWNER}
    ):
        raise RuntimeError(
            "Tras la migración 0027, el rol dueño de las funciones de plataforma conserva "
            "CREATE en el esquema acceso o el rol migrador sigue siendo miembro de él "
            "(p. ej. una membresía previa de createrole_self_grant en Supabase, C8): "
            "quítala antes de migrar."
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
                f"La migración 0027 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def _owner_policies(owner: str) -> list[str]:
    return [
        # --- listar (R29): el tenant pedido, sus membresías y sus usuarios ---
        f"CREATE POLICY dueno_plat_tenant_usuarios ON tenant FOR SELECT TO {owner} "
        f"USING (id = {USUARIOS} AND {ACTOR_ACTIVO})",
        f"CREATE POLICY dueno_plat_membresia_usuarios ON membresia FOR SELECT TO {owner} "
        f"USING (tenant_id = {USUARIOS} AND {ACTOR_ACTIVO})",
        f"CREATE POLICY dueno_plat_usuario_usuarios ON usuario FOR SELECT TO {owner} "  # noqa: S608
        "USING (EXISTS (SELECT 1 FROM membresia m WHERE m.usuario_id = usuario.id "
        f"AND m.tenant_id = {USUARIOS}) AND {ACTOR_ACTIVO})",
        # --- cambiar estado (R30, R31): solo activa de la membresía objetivo ---
        f"CREATE POLICY dueno_plat_tenant_membresia ON tenant FOR SELECT TO {owner} "
        f"USING (id = {MEM_TENANT} AND {ACTOR_ACTIVO})",
        f"CREATE POLICY dueno_plat_membresia_estado_leer ON membresia FOR SELECT TO {owner} "
        f"USING (tenant_id = {MEM_TENANT} AND {ACTOR_ACTIVO})",
        f"CREATE POLICY dueno_plat_membresia_estado ON membresia FOR UPDATE TO {owner} "
        f"USING (tenant_id = {MEM_TENANT} AND usuario_id = {MEM_USUARIO} AND {ACTOR_ACTIVO}) "
        f"WITH CHECK (tenant_id = {MEM_TENANT} AND usuario_id = {MEM_USUARIO})",
        # --- revocar (R30): solo las familias de esa membresía, y solo poner la fecha ---
        f"CREATE POLICY dueno_plat_refresh_membresia_leer ON refresh_token FOR SELECT "
        f"TO {owner} USING ({_DE_LA_MEMBRESIA} AND {ACTOR_ACTIVO})",
        f"CREATE POLICY dueno_plat_refresh_membresia_revocar ON refresh_token FOR UPDATE "
        f"TO {owner} USING ({_DE_LA_MEMBRESIA} AND revocado_en IS NULL AND {ACTOR_ACTIVO}) "
        f"WITH CHECK ({_DE_LA_MEMBRESIA} AND revocado_en = now())",
    ]


def _owner_grants(owner: str) -> list[str]:
    # Mínimos y por columna; nunca DELETE, password_hash, token_hash ni datos de negocio.
    return [
        f"GRANT SELECT (id, usuario_id) ON membresia TO {owner}",
        f"GRANT UPDATE (activa) ON membresia TO {owner}",
        f"GRANT SELECT (id, email, nombre, debe_cambiar_password) ON usuario TO {owner}",
        f"GRANT SELECT (tenant_id, membresia_id, revocado_en) ON refresh_token TO {owner}",
        f"GRANT UPDATE (revocado_en) ON refresh_token TO {owner}",
    ]


def _owner_revokes(owner: str) -> list[str]:
    # Exactamente lo de _owner_grants (lo de 0018 sobre membresia se conserva). Solo
    # constantes del módulo y el rol citado con identifier_preparer.quote.
    return [
        f"REVOKE SELECT (id, usuario_id) ON membresia FROM {owner}",  # noqa: S608
        f"REVOKE UPDATE (activa) ON membresia FROM {owner}",
        f"REVOKE SELECT (id, email, nombre, debe_cambiar_password) ON usuario FROM {owner}",  # noqa: S608
        f"REVOKE SELECT (tenant_id, membresia_id, revocado_en) ON refresh_token FROM {owner}",  # noqa: S608
        f"REVOKE UPDATE (revocado_en) ON refresh_token FROM {owner}",
    ]


def _transient_membership(owner: str, migrator: str) -> tuple[list[str], list[str]]:
    return (
        [f"GRANT {owner} TO {migrator} WITH INHERIT FALSE, SET TRUE"],
        [f"REVOKE {owner} FROM {migrator}"],
    )


def upgrade() -> None:
    conn = op.get_bind()
    require_owner(conn)
    require_postgres_16(conn)
    quote = conn.dialect.identifier_preparer.quote
    app = quote(_app_role(conn))
    owner = quote(PLATAFORMA_OWNER)
    migrator = quote(conn.scalar(text("select current_user")))
    supabase = [quote(role) for role in SUPABASE_ROLES if conn.scalar(_ROLE_EXISTS, {"name": role})]
    opening, closing = _transient_membership(owner, migrator)

    statements = [*_owner_policies(owner), *_owner_grants(owner), *CREATE_STATEMENTS]
    revoked = ", ".join(["PUBLIC", *supabase])
    statements += [f"REVOKE ALL ON FUNCTION {fn} FROM {revoked}" for fn in FUNCTIONS]
    statements += [f"GRANT EXECUTE ON FUNCTION {fn} TO {app}" for fn in FUNCTIONS]
    statements += [f"GRANT CREATE ON SCHEMA acceso TO {owner}", *opening]
    statements += [f"ALTER FUNCTION {fn} OWNER TO {owner}" for fn in FUNCTIONS]
    statements += [f"REVOKE CREATE ON SCHEMA acceso FROM {owner}", *closing]
    execute_statements(conn, statements)
    require_no_leftover_privileges(conn)


def downgrade() -> None:
    conn = op.get_bind()
    require_owner(conn)
    require_postgres_16(conn)
    quote = conn.dialect.identifier_preparer.quote
    owner = quote(PLATAFORMA_OWNER)
    migrator = quote(conn.scalar(text("select current_user")))
    opening, closing = _transient_membership(owner, migrator)
    # Solo el dueño (plataforma_owner) puede borrar sus funciones: SET LOCAL ROLE.
    statements = [*opening, f"SET LOCAL ROLE {owner}"]
    statements += [f"DROP FUNCTION {fn}" for fn in FUNCTIONS]
    statements += ["RESET ROLE", *closing]
    statements += [f"DROP POLICY {policy} ON {table}" for table, policy in POLICIES]
    statements += _owner_revokes(owner)
    execute_statements(conn, statements)
    require_no_leftover_privileges(conn)
