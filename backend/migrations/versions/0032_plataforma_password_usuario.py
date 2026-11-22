"""Contraseña temporal de un usuario desde la consola (spec 017, C1b, T16).

``plan.md`` §11.1; ``spec.md`` R53–R60; A27, A28, A29; RC7–RC9. Mismo patrón que 0018,
0027, 0030 y 0031 (``plpgsql``, ``SECURITY DEFINER``, ``STRICT``, ``SET search_path =
pg_catalog, pg_temp``, todo calificado, SQL estático, dueña ``plataforma_owner``,
``EXECUTE`` solo para el rol de la aplicación). La función vacía al empezar y al terminar
**todas** las GUC ``app.plat_*`` conocidas (las dieciocho de 0017–0031 y la de aquí), fija
solo las suyas con valores que ella recibe y nunca lee una GUC; su primera comprobación
(A5, R36) es que ``p_desarrollador`` exista y esté activo.

- ``acceso.plataforma_restablecer_password_usuario(p_desarrollador, p_tenant, p_usuario,
  p_password_hash)`` -> ``void`` (R53–R56). El hash Argon2id lo calcula Flask (la misma
  función y política que el alta, R19); aquí solo se valida su **formato** (como 0016,
  0018, 0024 y 0026: ``22023 hash_invalido``). Rechazos, en este orden y sin cambiar nada
  (R55): empresa inexistente -> ``P0002 empresa_no_encontrada``; el usuario no es de esa
  empresa -> ``P0002 usuario_no_encontrado`` (no se revela si existe en otra); empresa
  desactivada -> ``P0001 empresa_inactiva`` (D9). Aplica a cualquier usuario de la
  empresa (también al único admin, Q-P1), a una membresía desactivada y a usuarios con
  membresías en otras empresas (Q-P3), sin más condiciones.

  Candados: la contraseña es global (RC8), así que toma el candado consultivo exclusivo de
  0027 (``hashtextextended('plataforma_membresia:' || tenant, 0)``, el que toman también el
  login, el refresh, la invitación y el cambio de contraseña del tenant, compartido) de
  **cada** empresa donde el usuario tiene membresía, en orden ascendente de ``tenant_id``
  (orden fijo: dos definiciones del mismo usuario desde empresas distintas no se
  interbloquean). Ya bajo los candados vuelve a leer ese conjunto: si cambió (una
  membresía nueva entró mientras esperaba), falla cerrado con ``55P03 membresia_ocupada``
  (``503``). Las dos comprobaciones de existencia (404) van **antes** de los candados, así
  un usuario ajeno es ``404`` aunque otra empresa suya esté ocupada; bajo los candados se
  repiten con el estado ya serializado.

  En la misma transacción (R54): ``UPDATE`` de ``usuario`` con el hash nuevo,
  ``debe_cambiar_password = true`` y ``sesiones_validas_desde = now()`` (los access tokens
  vigentes dan ``401``), y revoca **todas** las familias de refresh del usuario, en todas
  sus membresías, con el bucle acotado y el fallo cerrado de 0027. ``lock_timeout``
  (``LOCK_TIMEOUT``): un candado que no llega a tiempo da ``55P03 membresia_ocupada``.
  Nunca lee ``password_hash`` (R56), ni toca ``email``, ``nombre``, ``activo``, la
  membresía ni el tenant.

La auditoría (``usuario_contrasena_restablecida``, sin valores) la escribe la aplicación en
la misma transacción. Aquí se amplían con esa acción el ``CHECK
plataforma_auditoria_accion_valida`` y la política ``plataforma_auditoria_insertar`` de la
aplicación (misma técnica que 0030).

GUC propia: ``app.plat_usuario_password`` (el usuario objetivo). Como 0031, reutiliza la GUC
de empresa de 0027 (``app.plat_membresia_tenant``) solo para leer el tenant y sus
membresías con las políticas de 0027 (``dueno_plat_tenant_membresia`` y
``dueno_plat_membresia_estado_leer``); **no** fija ``app.plat_membresia_usuario`` (así las
políticas de 0027 que cambian ``membresia.activa`` o revocan refresh quedan cerradas) ni
``app.plat_usuario_edicion`` de 0031. Políticas nuevas ``TO plataforma_owner`` (una por
comando; GUC validada por formato), todas con el desarrollador de ``app.plat_actor``
activo:

- ``membresia`` ``FOR SELECT``: las membresías del usuario objetivo (en cualquier empresa;
  sin ella no se conocen las empresas cuyos candados hay que tomar ni sus refresh);
- ``usuario`` ``FOR SELECT`` y ``FOR UPDATE``: el usuario objetivo y solo si tiene una
  membresía en el tenant de ``app.plat_membresia_tenant``; el ``WITH CHECK`` exige además
  ``debe_cambiar_password`` y ``sesiones_validas_desde = now()`` (no hay hash nuevo sin la
  marca ni sin el corte);
- ``refresh_token`` ``FOR SELECT`` y ``FOR UPDATE``: los de cualquier membresía del usuario
  objetivo; solo poner ``revocado_en = now()`` a los vivos.

``GRANT`` por columna mínimos, sin ``DELETE`` ni ``SELECT`` nuevo: ``usuario`` ``UPDATE
(password_hash, debe_cambiar_password, sesiones_validas_desde)``; **nunca** ``SELECT
(password_hash)`` (R56). ``membresia`` ``SELECT (id, tenant_id, usuario_id)`` y
``refresh_token`` ``SELECT``/``UPDATE (revocado_en)`` ya los abren 0018 y 0027. RC10: el
privilegio por columna ensancha también ``dueno_plat_usuario_edicion`` de 0031 (con sus GUC
la RLS dejaría escribir esas tres columnas), y el ``UPDATE (nombre)`` de 0031 ensancha la de
aquí (con su GUC la RLS deja cambiar el nombre solo junto con la marca y el corte); lo
contiene la huella de los cuerpos y la aserción de catálogo que fija qué columnas de
``usuario`` escribe cada función (``test_plataforma_catalogo.py``).

``downgrade``: borra la función (como ``plataforma_owner``), sus cinco políticas y solo el
``GRANT`` de aquí, y vuelve al ``CHECK`` y a la política de auditoría de 0030. No borra
datos: las contraseñas definidas y la marca se conservan; si ya hay auditoría con la acción
nueva, el ``CHECK`` de antes se añade ``NOT VALID`` (rige para filas nuevas y conserva las
existentes; como 0030).

Revision ID: 0032_plataforma_password_usuario
Revises: 0031_plataforma_editar_usuario
Create Date: 2026-11-21
"""

import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0032_plataforma_password_usuario"
down_revision: str | Sequence[str] | None = "0031_plataforma_editar_usuario"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE_VAR = "APP_DB_USER"
AUTH_OWNER = "auth_owner"
PLATAFORMA_OWNER = "plataforma_owner"
SUPABASE_ROLES = ("anon", "authenticated", "service_role")

RESTABLECER = "acceso.plataforma_restablecer_password_usuario(uuid, uuid, uuid, text)"
FUNCTIONS = (RESTABLECER,)

# Las dieciocho GUC de 0017–0031, en su orden (las vacía la función de 0031).
OWNER_GUCS_0031 = (
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
# Y la de aquí: el usuario cuya contraseña se define.
OWNER_GUCS = (*OWNER_GUCS_0031, "app.plat_usuario_password")

# Acciones de la aplicación en 0030 y la de C1b (al final, como en 0030).
ACCIONES_APP_0030 = (
    "login_ok",
    "empresa_creada",
    "empresa_desactivada",
    "empresa_reactivada",
    "empresa_logo_subido",
    "usuario_desactivado",
    "usuario_reactivado",
    "empresa_editada",
    "empresa_logo_reemplazado",
    "usuario_editado",
)
ACCIONES_C1B = ("usuario_contrasena_restablecida",)
ACCIONES_APP = (*ACCIONES_APP_0030, *ACCIONES_C1B)
# Lista del CHECK tras 0030 (R33) y la ampliada (se añade al final).
ACCIONES_0030 = (
    "login_ok",
    "empresa_creada",
    "empresa_desactivada",
    "empresa_reactivada",
    "empresa_logo_subido",
    "usuario_desactivado",
    "usuario_reactivado",
    "desarrollador_creado",
    "desarrollador_restablecido",
    "desarrollador_desactivado",
    "desarrollador_reactivado",
    "empresa_editada",
    "empresa_logo_reemplazado",
    "usuario_editado",
)
ACCIONES = (*ACCIONES_0030, *ACCIONES_C1B)
CHECK_ACCION = "plataforma_auditoria_accion_valida"

# (tabla, política): lista cerrada (la fijan test_plataforma_catalogo.py y test_migrations.py).
POLICIES = (
    ("membresia", "dueno_plat_membresia_password"),
    ("usuario", "dueno_plat_usuario_password_leer"),
    ("usuario", "dueno_plat_usuario_password"),
    ("refresh_token", "dueno_plat_refresh_password_leer"),
    ("refresh_token", "dueno_plat_refresh_password_revocar"),
)
# Las únicas columnas de usuario que escribe la función (R56).
COLUMNAS = ("password_hash", "debe_cambiar_password", "sesiones_validas_desde")

# Espera máxima de cada candado (consultivo de cada empresa y filas): como 0027.
LOCK_TIMEOUT = "5s"
# Pasadas máximas de la revocación de refresh: como 0027.
REVOKE_MAX_PASSES = 10
# Formato completo del hash de argon2-cffi (como 0016/0018/0024/0026), sin barras invertidas.
_HASH_FORMAT = (
    "'^[$]argon2id[$]v=19[$]m=[0-9]+,t=[0-9]+,p=[0-9]+[$][A-Za-z0-9+/]+[$][A-Za-z0-9+/]+$'"
)
_HASH_MAX_LENGTH = 255

_UUID = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def uuid_setting(guc: str) -> str:
    """UUID de ``guc``; ``NULL`` si falta o no es un UUID en minúsculas (como 0018)."""
    value = f"pg_catalog.current_setting('{guc}', true)"
    return f"(CASE WHEN {value} ~ '{_UUID}' THEN ({value})::uuid END)"


ACTOR = uuid_setting("app.plat_actor")
MEM_TENANT = uuid_setting("app.plat_membresia_tenant")
USUARIO_PASSWORD = uuid_setting("app.plat_usuario_password")
ACTOR_ACTIVO = f"EXISTS (SELECT 1 FROM desarrollador d WHERE d.id = {ACTOR} AND d.activo)"  # noqa: S608
DESARROLLADOR = "NULLIF(current_setting('app.desarrollador_id', true), '')::uuid"
DESARROLLADOR_ACTIVO = (
    f"EXISTS (SELECT 1 FROM desarrollador d WHERE d.id = {DESARROLLADOR} AND d.activo)"  # noqa: S608
)
# El usuario objetivo, y solo si tiene una membresía en el tenant de la petición.
_DEL_TENANT = (
    f"id = {USUARIO_PASSWORD} AND EXISTS (SELECT 1 FROM membresia m "  # noqa: S608
    f"WHERE m.usuario_id = usuario.id AND m.tenant_id = {MEM_TENANT})"
)
# Refresh de cualquier membresía del usuario objetivo (la contraseña es global, RC8).
_DEL_USUARIO = (
    "EXISTS (SELECT 1 FROM membresia m "  # noqa: S608
    "WHERE m.id = refresh_token.membresia_id AND m.tenant_id = refresh_token.tenant_id "
    f"AND m.usuario_id = {USUARIO_PASSWORD})"
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
_EMPRESAS_DEL_USUARIO = (
    "SELECT pg_catalog.array_agg(m.tenant_id ORDER BY m.tenant_id) INTO {destino}\n"
    "        FROM public.membresia AS m WHERE m.usuario_id = p_usuario;"
)  # noqa: S608 - solo constantes del módulo

CREATE_RESTABLECER = f"""
CREATE FUNCTION acceso.plataforma_restablecer_password_usuario(
    p_desarrollador uuid, p_tenant uuid, p_usuario uuid, p_password_hash text)
RETURNS void
{_HEADER}
SET lock_timeout = '{LOCK_TIMEOUT}'
AS $fn$
DECLARE
    v_activo boolean;
    v_tenant_activo boolean;
    v_empresas uuid[];
    v_empresas_ahora uuid[];
    v_empresa uuid;
    v_filas bigint;
    v_pasada integer;
    v_revocados bigint;
BEGIN
    {_CLEAR}
    {_DESARROLLADOR_ACTIVO}
    IF p_password_hash !~ {_HASH_FORMAT}
       OR pg_catalog.length(p_password_hash) > {_HASH_MAX_LENGTH} THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'hash_invalido';
    END IF;
    PERFORM pg_catalog.set_config('app.plat_membresia_tenant', p_tenant::text, true);
    PERFORM pg_catalog.set_config('app.plat_usuario_password', p_usuario::text, true);
    -- 404 antes de esperar: un usuario ajeno no depende de los candados de otras empresas.
    PERFORM 1 FROM public.tenant AS t WHERE t.id = p_tenant;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'empresa_no_encontrada';
    END IF;
    PERFORM 1 FROM public.membresia AS m WHERE m.tenant_id = p_tenant AND m.usuario_id = p_usuario;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'usuario_no_encontrado';
    END IF;
    -- El candado de 0027 de cada empresa del usuario, en orden fijo (la contraseña es global).
    {_EMPRESAS_DEL_USUARIO.format(destino="v_empresas")}
    FOREACH v_empresa IN ARRAY v_empresas LOOP
        PERFORM pg_catalog.pg_advisory_xact_lock(
            pg_catalog.hashtextextended('plataforma_membresia:' || v_empresa::text, 0));
    END LOOP;
    {_EMPRESAS_DEL_USUARIO.format(destino="v_empresas_ahora")}
    IF v_empresas_ahora IS DISTINCT FROM v_empresas THEN
        -- Falla cerrado: una membresía nueva entró mientras se esperaba un candado.
        RAISE EXCEPTION USING ERRCODE = '55P03', MESSAGE = 'membresia_ocupada';
    END IF;
    -- Ya serializado: los mismos rechazos, en el mismo orden.
    SELECT t.activo INTO v_tenant_activo FROM public.tenant AS t WHERE t.id = p_tenant;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'empresa_no_encontrada';
    END IF;
    IF NOT (p_tenant = ANY (v_empresas_ahora)) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'usuario_no_encontrado';
    END IF;
    IF NOT v_tenant_activo THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'empresa_inactiva';
    END IF;
    UPDATE public.usuario AS u
        SET password_hash = p_password_hash, debe_cambiar_password = true,
            sesiones_validas_desde = pg_catalog.now()
        WHERE u.id = p_usuario;
    GET DIAGNOSTICS v_filas = ROW_COUNT;
    IF v_filas <> 1 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'usuario_no_encontrado';
    END IF;
    -- Como al desactivar (0027), pero de todas las membresías del usuario: se repite hasta
    -- que no afecte filas, así un sucesor insertado por una rotación que confirmó mientras
    -- se esperaba un candado se revoca en la pasada siguiente.
    FOR v_pasada IN 1..{REVOKE_MAX_PASSES} LOOP
        UPDATE public.refresh_token AS t SET revocado_en = pg_catalog.now()
            WHERE t.revocado_en IS NULL AND t.membresia_id IN (
                SELECT m.id FROM public.membresia AS m WHERE m.usuario_id = p_usuario);
        GET DIAGNOSTICS v_revocados = ROW_COUNT;
        EXIT WHEN v_revocados = 0;
    END LOOP;
    IF v_revocados <> 0 THEN
        -- Falla cerrado: no se define la contraseña dejando una familia viva.
        RAISE EXCEPTION USING ERRCODE = '55P03', MESSAGE = 'membresia_ocupada';
    END IF;
    {_CLEAR}
    RETURN;
EXCEPTION WHEN lock_not_available THEN
    RAISE EXCEPTION USING ERRCODE = '55P03', MESSAGE = 'membresia_ocupada';
END
$fn$
"""  # noqa: S608 - solo constantes del módulo

CREATE_STATEMENTS = (CREATE_RESTABLECER,)

_ROLE_EXISTS = text("select exists (select 1 from pg_roles where rolname = :name)")
_ROLE_SKIPS_RLS = text("select rolsuper or rolbypassrls from pg_roles where rolname = :name")
_ROLE_UNSAFE = text(
    "select coalesce((select r.rolsuper or r.rolbypassrls or r.rolcanlogin or r.rolcreaterole "
    "or r.rolcreatedb or r.rolreplication "
    "or exists (select 1 from pg_auth_members m where m.member = r.oid) "
    "from pg_roles r where r.rolname = :name), true)"
)
_IS_MEMBER = text("select pg_has_role(:member, :owner, 'MEMBER')")
# Igual que 0004/0018/0027–0031 (C8): por rolname exacto; la membresía ADMIN del creador en
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
_NEW_ACTIONS_IN_USE = text(
    "select exists (select 1 from plataforma_auditoria where accion = any(:acciones))"
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
            "La migración 0032 exige PostgreSQL 16 o superior (membresía transitoria "
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
            "Tras la migración 0032, el rol dueño de las funciones de plataforma conserva "
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
                f"La migración 0032 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def _owner_policies(owner: str) -> list[str]:
    return [
        f"CREATE POLICY dueno_plat_membresia_password ON membresia FOR SELECT TO {owner} "
        f"USING (usuario_id = {USUARIO_PASSWORD} AND {ACTOR_ACTIVO})",
        f"CREATE POLICY dueno_plat_usuario_password_leer ON usuario FOR SELECT TO {owner} "
        f"USING ({_DEL_TENANT} AND {ACTOR_ACTIVO})",
        f"CREATE POLICY dueno_plat_usuario_password ON usuario FOR UPDATE TO {owner} "
        f"USING ({_DEL_TENANT} AND {ACTOR_ACTIVO}) "
        f"WITH CHECK (id = {USUARIO_PASSWORD} AND debe_cambiar_password "
        "AND sesiones_validas_desde = now())",
        f"CREATE POLICY dueno_plat_refresh_password_leer ON refresh_token FOR SELECT "
        f"TO {owner} USING ({_DEL_USUARIO} AND {ACTOR_ACTIVO})",
        f"CREATE POLICY dueno_plat_refresh_password_revocar ON refresh_token FOR UPDATE "
        f"TO {owner} USING ({_DEL_USUARIO} AND revocado_en IS NULL AND {ACTOR_ACTIVO}) "
        f"WITH CHECK ({_DEL_USUARIO} AND revocado_en = now())",
    ]


def _owner_grants(owner: str) -> list[str]:
    # Mínimo y por columna; nunca SELECT (password_hash), DELETE, email, nombre ni activo.
    return [f"GRANT UPDATE ({', '.join(COLUMNAS)}) ON usuario TO {owner}"]


def _owner_revokes(owner: str) -> list[str]:
    # Exactamente lo de _owner_grants (lo de 0018, 0027 y 0031 se conserva).
    return [f"REVOKE UPDATE ({', '.join(COLUMNAS)}) ON usuario FROM {owner}"]


def _audit_policy(app: str, acciones: Sequence[str]) -> str:
    """La política de inserción de la aplicación, con el mismo texto que la de 0018/0030."""
    lista = ", ".join(f"'{accion}'" for accion in acciones)
    check = (
        f"desarrollador_id = {DESARROLLADOR} AND {DESARROLLADOR_ACTIVO}"
        f" AND accion IN ({lista}) "
        f"AND ((accion = 'login_ok' AND tenant_id IS NULL AND objeto_id = {DESARROLLADOR}) "
        "OR (accion <> 'login_ok' AND tenant_id IS NOT NULL))"
    )
    return (
        f"CREATE POLICY plataforma_auditoria_insertar ON plataforma_auditoria FOR INSERT "
        f"TO {app} WITH CHECK ({check})"
    )


def _audit_check(acciones: Sequence[str], *, not_valid: bool = False) -> list[str]:
    lista = ", ".join(f"'{accion}'" for accion in acciones)
    sufijo = " NOT VALID" if not_valid else ""
    return [
        f"ALTER TABLE plataforma_auditoria DROP CONSTRAINT {CHECK_ACCION}",
        f"ALTER TABLE plataforma_auditoria ADD CONSTRAINT {CHECK_ACCION} "
        f"CHECK (accion IN ({lista})){sufijo}",
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

    statements = [*_audit_check(ACCIONES)]
    statements += [
        "DROP POLICY plataforma_auditoria_insertar ON plataforma_auditoria",
        _audit_policy(app, ACCIONES_APP),
    ]
    # Orden C3/C5: políticas y GRANT -> CREATE -> REVOKE de PUBLIC y de Supabase -> GRANT
    # EXECUTE a la aplicación -> CREATE transitorio y membresía transitoria -> OWNER -> fin.
    statements += [*_owner_policies(owner), *_owner_grants(owner), *CREATE_STATEMENTS]
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
    app, owner, migrator, _ = _context(conn)
    opening, closing = _transient_membership(owner, migrator)
    # No se borra auditoría: si ya hay filas con la acción de C1b, el CHECK de antes rige
    # solo para filas nuevas (NOT VALID), como 0030.
    in_use = bool(conn.scalar(_NEW_ACTIONS_IN_USE, {"acciones": list(ACCIONES_C1B)}))
    # Solo el dueño (plataforma_owner) puede borrar su función: SET LOCAL ROLE.
    statements = [*opening, f"SET LOCAL ROLE {owner}"]
    statements += [f"DROP FUNCTION {fn}" for fn in FUNCTIONS]
    statements += ["RESET ROLE", *closing]
    statements += [f"DROP POLICY {policy} ON {table}" for table, policy in POLICIES]
    statements += _owner_revokes(owner)
    statements += [
        "DROP POLICY plataforma_auditoria_insertar ON plataforma_auditoria",
        _audit_policy(app, ACCIONES_APP_0030),
    ]
    statements += _audit_check(ACCIONES_0030, not_valid=in_use)
    execute_statements(conn, statements)
    require_no_leftover_privileges(conn)
