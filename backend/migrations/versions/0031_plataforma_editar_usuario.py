"""Editar nombre y rol de un usuario desde la consola (spec 017, C1, T13).

``plan.md`` §10.1 y §10.2; ``spec.md`` R47–R52; A24, A25, A26. Mismo patrón que 0018, 0027
y 0030 (``plpgsql``, ``SECURITY DEFINER``, ``STRICT``, ``SET search_path = pg_catalog,
pg_temp``, todo calificado, SQL estático, dueña ``plataforma_owner``, ``EXECUTE`` solo para
el rol de la aplicación). La función vacía al empezar y al terminar **todas** las GUC
``app.plat_*`` conocidas (las diecisiete de 0017–0030 y la de aquí), fija solo las suyas con
valores que ella recibe y nunca lee una GUC; su primera comprobación (A5, R36) es que
``p_desarrollador`` exista y esté activo.

- ``acceso.plataforma_cambiar_usuario(p_desarrollador, p_tenant, p_usuario, p_nombre,
  p_rol)`` -> una fila ``(nombre, rol, cambiado, rol_cambiado)``. El nombre llega ya
  normalizado y el rol ya validado en Flask (R47; el ``CHECK membresia_rol_valido`` de 0002
  es el respaldo). Bajo el mismo candado consultivo exclusivo por tenant que
  ``plataforma_cambiar_estado_membresia`` (0027: ``hashtextextended('plataforma_membresia:'
  || tenant, 0)``, el que también toman el login y el refresh del tenant) y con el mismo
  orden de rechazos, sin cambiar nada (R48): empresa inexistente -> ``P0002
  empresa_no_encontrada``; el usuario no es de esa empresa -> ``P0002
  usuario_no_encontrado``; empresa desactivada -> ``P0001 empresa_inactiva`` (D9);
  degradar la última membresía ``admin`` **activa** -> ``P0001 ultimo_admin`` (P31; una
  membresía inactiva no cuenta, R51). Después cambia ``usuario.nombre`` solo si difiere y
  ``membresia.rol`` de esa membresía solo si difiere (``IS DISTINCT FROM``); idéntico no
  escribe (R50). Si cambió el rol, revoca las familias de refresh de esa membresía con el
  mismo bucle acotado y fallo cerrado de 0027 (R49); un cambio solo de nombre no revoca.
  Nunca toca ``email``, ``password_hash``, ``debe_cambiar_password``,
  ``sesiones_validas_desde``, ``activo`` ni ``membresia.activa``. ``lock_timeout``
  (``LOCK_TIMEOUT``): un candado que no llega a tiempo da ``55P03 membresia_ocupada``
  (``503`` en la API) sin cambiar nada.

La auditoría (``usuario_editado``, solo con un cambio real y sin valores) la escribe la
aplicación en la misma transacción; el ``CHECK`` y la política de inserción ya la admiten
desde 0030.

Políticas: la función reutiliza las GUC de 0027 (``app.plat_membresia_tenant`` y
``app.plat_membresia_usuario``) y sus políticas sobre ``tenant`` (leer el estado),
``membresia`` (leer las del tenant y cambiar la del usuario objetivo) y ``refresh_token``
(revocar las de esa membresía); nunca la GUC de estado del tenant de 0018. Sobre ``usuario``
añade dos políticas ``TO plataforma_owner`` (una por comando; GUC validada por formato), con
el desarrollador de ``app.plat_actor`` activo, acotadas al usuario de
``app.plat_usuario_edicion`` **y** a una membresía suya en el tenant de
``app.plat_membresia_tenant``: ``FOR SELECT`` y ``FOR UPDATE`` (``WITH CHECK``: el mismo
usuario).

``GRANT`` por columna mínimos, sin ``DELETE``: ``usuario`` ``UPDATE (nombre)`` y
``membresia`` ``UPDATE (rol)`` (el ``SELECT`` de ``usuario.id``/``nombre`` lo abre 0027 y el
de ``membresia`` 0018 y 0027). RC10: el privilegio por columna ensancha también la política
``UPDATE`` de 0027 sobre ``membresia`` (con sus GUC, la RLS dejaría cambiar ``rol``); lo
contiene la huella de los cuerpos y la aserción de catálogo de que solo esta función escribe
``usuario.nombre`` y ``membresia.rol``.

``downgrade``: borra la función (como ``plataforma_owner``), sus dos políticas y solo los
``GRANT`` de aquí. No borra datos: los nombres y roles editados se conservan.

Revision ID: 0031_plataforma_editar_usuario
Revises: 0030_plataforma_edicion_empresa
Create Date: 2026-11-21
"""

import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0031_plataforma_editar_usuario"
down_revision: str | Sequence[str] | None = "0030_plataforma_edicion_empresa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE_VAR = "APP_DB_USER"
AUTH_OWNER = "auth_owner"
PLATAFORMA_OWNER = "plataforma_owner"
SUPABASE_ROLES = ("anon", "authenticated", "service_role")

CAMBIAR = "acceso.plataforma_cambiar_usuario(uuid, uuid, uuid, text, text)"
FUNCTIONS = (CAMBIAR,)

# Las diecisiete GUC de 0017–0030, en su orden (las vacían las funciones de 0030).
OWNER_GUCS_0030 = (
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
)
# Y la de aquí: el usuario cuyo nombre se edita.
OWNER_GUCS = (*OWNER_GUCS_0030, "app.plat_usuario_edicion")

# (tabla, política): lista cerrada (la fijan test_plataforma_catalogo.py y test_migrations.py).
POLICIES = (
    ("usuario", "dueno_plat_usuario_edicion_leer"),
    ("usuario", "dueno_plat_usuario_edicion"),
)

# Espera máxima de cada candado (consultivo del tenant y filas): como 0027.
LOCK_TIMEOUT = "5s"
# Pasadas máximas de la revocación de refresh: como 0027.
REVOKE_MAX_PASSES = 10

_UUID = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def uuid_setting(guc: str) -> str:
    """UUID de ``guc``; ``NULL`` si falta o no es un UUID en minúsculas (como 0018)."""
    value = f"pg_catalog.current_setting('{guc}', true)"
    return f"(CASE WHEN {value} ~ '{_UUID}' THEN ({value})::uuid END)"


ACTOR = uuid_setting("app.plat_actor")
MEM_TENANT = uuid_setting("app.plat_membresia_tenant")
USUARIO_EDICION = uuid_setting("app.plat_usuario_edicion")
ACTOR_ACTIVO = f"EXISTS (SELECT 1 FROM desarrollador d WHERE d.id = {ACTOR} AND d.activo)"  # noqa: S608
# El usuario objetivo, y solo si tiene una membresía en el tenant de la edición.
_DEL_TENANT = (
    f"id = {USUARIO_EDICION} AND EXISTS (SELECT 1 FROM membresia m "  # noqa: S608
    f"WHERE m.usuario_id = usuario.id AND m.tenant_id = {MEM_TENANT})"
)

_CLEAR = (
    "PERFORM pg_catalog.set_config(g, '', true) "
    "FROM pg_catalog.unnest(ARRAY['" + "', '".join(OWNER_GUCS) + "']::text[]) AS g;"
)
_HEADER = "LANGUAGE plpgsql STRICT SECURITY DEFINER SET search_path = pg_catalog, pg_temp"
# A5/R36: primera comprobación de la función; excepción estática, sin datos (como 0018).
_DESARROLLADOR_ACTIVO = (
    "PERFORM pg_catalog.set_config('app.plat_actor', p_desarrollador::text, true);\n"
    "    SELECT d.activo INTO v_activo FROM public.desarrollador AS d "
    "WHERE d.id = p_desarrollador;\n"
    "    IF NOT FOUND OR NOT v_activo THEN\n"
    "        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'desarrollador_no_autorizado';\n"
    "    END IF;"
)  # noqa: S608 - solo constantes del módulo

CREATE_CAMBIAR = f"""
CREATE FUNCTION acceso.plataforma_cambiar_usuario(
    p_desarrollador uuid, p_tenant uuid, p_usuario uuid, p_nombre text, p_rol text)
RETURNS TABLE (nombre text, rol text, cambiado boolean, rol_cambiado boolean)
{_HEADER}
SET lock_timeout = '{LOCK_TIMEOUT}'
AS $fn$
DECLARE
    v_activo boolean;
    v_tenant_activo boolean;
    v_membresia uuid;
    v_rol text;
    v_activa boolean;
    v_nombre text;
    v_otros_admins bigint;
    v_filas bigint;
    v_pasada integer;
    v_revocados bigint;
    v_cambiado boolean := false;
    v_rol_cambiado boolean := false;
BEGIN
    {_CLEAR}
    {_DESARROLLADOR_ACTIVO}
    PERFORM pg_catalog.set_config('app.plat_membresia_tenant', p_tenant::text, true);
    PERFORM pg_catalog.set_config('app.plat_membresia_usuario', p_usuario::text, true);
    PERFORM pg_catalog.set_config('app.plat_usuario_edicion', p_usuario::text, true);
    -- El mismo candado que desactivar (0027): el conteo de admins no se adelanta.
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
    IF v_rol = 'admin' AND v_activa AND p_rol <> 'admin' THEN
        SELECT pg_catalog.count(*) INTO v_otros_admins FROM public.membresia AS m
            WHERE m.tenant_id = p_tenant AND m.rol = 'admin' AND m.activa
              AND m.usuario_id <> p_usuario;
        IF v_otros_admins = 0 THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ultimo_admin';
        END IF;
    END IF;
    SELECT u.nombre INTO v_nombre FROM public.usuario AS u WHERE u.id = p_usuario;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'usuario_no_encontrado';
    END IF;
    IF p_nombre IS DISTINCT FROM v_nombre THEN
        UPDATE public.usuario AS u SET nombre = p_nombre WHERE u.id = p_usuario;
        GET DIAGNOSTICS v_filas = ROW_COUNT;
        IF v_filas <> 1 THEN
            RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'usuario_no_encontrado';
        END IF;
        v_cambiado := true;
    END IF;
    IF p_rol IS DISTINCT FROM v_rol THEN
        UPDATE public.membresia AS m SET rol = p_rol
            WHERE m.tenant_id = p_tenant AND m.usuario_id = p_usuario;
        GET DIAGNOSTICS v_filas = ROW_COUNT;
        IF v_filas <> 1 THEN
            RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'usuario_no_encontrado';
        END IF;
        v_cambiado := true;
        v_rol_cambiado := true;
        -- Como al desactivar (0027): se repite hasta que no afecte filas, así un sucesor
        -- insertado por una rotación que confirmó mientras se esperaba su candado se
        -- revoca en la pasada siguiente.
        FOR v_pasada IN 1..{REVOKE_MAX_PASSES} LOOP
            UPDATE public.refresh_token AS t SET revocado_en = pg_catalog.now()
                WHERE t.tenant_id = p_tenant AND t.membresia_id = v_membresia
                  AND t.revocado_en IS NULL;
            GET DIAGNOSTICS v_revocados = ROW_COUNT;
            EXIT WHEN v_revocados = 0;
        END LOOP;
        IF v_revocados <> 0 THEN
            -- Falla cerrado: no se cambia el rol dejando una familia viva.
            RAISE EXCEPTION USING ERRCODE = '55P03', MESSAGE = 'membresia_ocupada';
        END IF;
    END IF;
    {_CLEAR}
    RETURN QUERY SELECT p_nombre, p_rol, v_cambiado, v_rol_cambiado;
    RETURN;
EXCEPTION WHEN lock_not_available THEN
    RAISE EXCEPTION USING ERRCODE = '55P03', MESSAGE = 'membresia_ocupada';
END
$fn$
"""  # noqa: S608 - solo constantes del módulo

CREATE_STATEMENTS = (CREATE_CAMBIAR,)

_ROLE_EXISTS = text("select exists (select 1 from pg_roles where rolname = :name)")
_ROLE_SKIPS_RLS = text("select rolsuper or rolbypassrls from pg_roles where rolname = :name")
_ROLE_UNSAFE = text(
    "select coalesce((select r.rolsuper or r.rolbypassrls or r.rolcanlogin or r.rolcreaterole "
    "or r.rolcreatedb or r.rolreplication "
    "or exists (select 1 from pg_auth_members m where m.member = r.oid) "
    "from pg_roles r where r.rolname = :name), true)"
)
_IS_MEMBER = text("select pg_has_role(:member, :owner, 'MEMBER')")
# Igual que 0004/0018/0027–0030 (C8): por rolname exacto; la membresía ADMIN del creador en
# Supabase, sin INHERIT ni SET y concedida por otro, no cuenta.
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
            "La migración 0031 exige PostgreSQL 16 o superior (membresía transitoria "
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
            "Tras la migración 0031, el rol dueño de las funciones de plataforma conserva "
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
                f"La migración 0031 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def _owner_policies(owner: str) -> list[str]:
    return [
        f"CREATE POLICY dueno_plat_usuario_edicion_leer ON usuario FOR SELECT TO {owner} "
        f"USING ({_DEL_TENANT} AND {ACTOR_ACTIVO})",
        f"CREATE POLICY dueno_plat_usuario_edicion ON usuario FOR UPDATE TO {owner} "
        f"USING ({_DEL_TENANT} AND {ACTOR_ACTIVO}) "
        f"WITH CHECK (id = {USUARIO_EDICION})",
    ]


def _owner_grants(owner: str) -> list[str]:
    # Mínimos y por columna; nunca DELETE, email, password_hash ni las marcas del usuario.
    return [
        f"GRANT UPDATE (nombre) ON usuario TO {owner}",
        f"GRANT UPDATE (rol) ON membresia TO {owner}",
    ]


def _owner_revokes(owner: str) -> list[str]:
    # Exactamente lo de _owner_grants (lo de 0018 y 0027 se conserva).
    return [
        f"REVOKE UPDATE (nombre) ON usuario FROM {owner}",
        f"REVOKE UPDATE (rol) ON membresia FROM {owner}",
    ]


def _transient_membership(owner: str, migrator: str) -> tuple[list[str], list[str]]:
    return (
        [f"GRANT {owner} TO {migrator} WITH INHERIT FALSE, SET TRUE"],
        [f"REVOKE {owner} FROM {migrator}"],
    )


def _context(conn: Connection) -> tuple[str, str, str, list[str]]:
    quote = conn.dialect.identifier_preparer.quote
    app = quote(_app_role(conn))
    owner = quote(PLATAFORMA_OWNER)
    migrator = quote(conn.scalar(text("select current_user")))
    supabase = [quote(role) for role in SUPABASE_ROLES if conn.scalar(_ROLE_EXISTS, {"name": role})]
    return app, owner, migrator, supabase


def upgrade() -> None:
    conn = op.get_bind()
    require_owner(conn)
    require_postgres_16(conn)
    app, owner, migrator, supabase = _context(conn)
    opening, closing = _transient_membership(owner, migrator)

    # Orden C3/C5: políticas y GRANT -> CREATE -> REVOKE de PUBLIC y de Supabase -> GRANT
    # EXECUTE a la aplicación -> CREATE transitorio y membresía transitoria -> OWNER -> fin.
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
    # Solo el dueño (plataforma_owner) puede borrar su función: SET LOCAL ROLE.
    statements = [*opening, f"SET LOCAL ROLE {owner}"]
    statements += [f"DROP FUNCTION {fn}" for fn in FUNCTIONS]
    statements += ["RESET ROLE", *closing]
    statements += [f"DROP POLICY {policy} ON {table}" for table, policy in POLICIES]
    statements += _owner_revokes(owner)
    execute_statements(conn, statements)
    require_no_leftover_privileges(conn)
