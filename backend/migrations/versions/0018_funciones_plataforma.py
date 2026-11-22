"""Funciones de Empresas de la consola y ``tenant.activo`` en el login (spec 017, T3a).

``plan.md`` §2.3, §2.5 y §5; ``spec.md`` R16, R21, R22 (SQL), R36; A4, A5, A9 (login).
Mismo patrón que 0016/0017 (§2.1 de la spec 002).

Funciones nuevas (``plpgsql``, ``SECURITY DEFINER``, ``STRICT``, ``SET search_path =
pg_catalog, pg_temp``, todo calificado, SQL estático, dueña ``plataforma_owner``,
``EXECUTE`` solo para el rol de la aplicación). Cada una vacía al empezar y al terminar
**todas** las GUC ``app.plat_*`` (las cinco de 0017 y las cinco de aquí), fija solo las
suyas con valores que ella valida o calcula y nunca lee una GUC. Su primera comprobación
(A5, R36): ``p_desarrollador`` existe y está activo; si no, ``42501
desarrollador_no_autorizado`` sin devolver filas ni escribir.

- ``acceso.plataforma_listar_tenants(p_desarrollador)`` -> ``id``, ``nombre``, ``activo``,
  ``creado_en``, ``tiene_logo``, ``n_membresias_activas``, ``n_admins_activos`` (R21):
  solo identidad de la empresa y conteos; nada de negocio.
- ``acceso.plataforma_crear_tenant(p_desarrollador, p_tenant, p_nombre, p_direccion,
  p_nit, p_telefono, p_correo, p_admin_email, p_admin_nombre, p_password_hash)`` ->
  ``tenant_id``, ``usuario_id`` (R16, R18, R20). En la transacción de quien llama:
  ``tenant`` (``id`` del cliente; nombre = razón social), ``usuario`` activo con
  ``debe_cambiar_password = true`` (``id`` generado aquí), ``membresia`` ``admin`` activa
  y su ficha ``empresa`` sin logo (``actualizada_por`` = ese admin). Sin invitación. El
  hash Argon2id lo calcula Flask; la función valida su formato completo como 0016/0017
  (``22023 hash_invalido``) y nunca lo devuelve. Mismo ``id`` -> ``23505
  empresa_existente``; correo ya usado por cualquier ``usuario`` -> ``23505
  email_en_uso`` (H-2, sin decir de qué empresa); en los dos casos no queda nada. Como la
  función es ``STRICT``, los opcionales de la ficha (NIT, teléfono, correo) llegan como
  ``''`` cuando faltan y se guardan como ``NULL``. Las demás reglas de la ficha (013) y
  de la contraseña (002) las aplica Flask; los ``CHECK`` de 0002/0014 son la red.
- ``acceso.plataforma_cambiar_estado_tenant(p_desarrollador, p_tenant, p_activo)`` ->
  ``boolean`` (R22): fija ``tenant.activo`` con fecha y autor al desactivar y los deja
  en ``NULL`` al reactivar; no toca ninguna otra fila ni columna. Repetir no cambia nada.
  Empresa inexistente -> ``P0002 empresa_no_encontrada``.

La auditoría (``empresa_creada``, ``empresa_desactivada``, ``empresa_reactivada``) la
escribe la aplicación en la misma transacción (T3b, ``app.plataforma.auditoria``).

Políticas ``TO plataforma_owner`` (una por comando, nunca ``FOR ALL`` ni ``PUBLIC``; GUC
validadas por formato: vacía, nula o con otro formato -> ``NULL`` -> cero filas). Todas,
salvo la de lectura del propio desarrollador, exigen además que el desarrollador de
``app.plat_actor`` esté activo. Los ``INSERT`` de ``usuario``, ``membresia`` y
``empresa`` se acotan al tenant creado **en esta transacción** (``creado_en = now()``,
como Q21 de la 002). ``GRANT`` por columna mínimos, sin ``DELETE``: de ``empresa`` solo
lee ``tenant_id`` y ``logo_id`` (A19) y solo escribe la ficha inicial.

Cambios a lo existente:

- ``acceso.buscar_login`` (0004, dueña ``auth_owner``; plan §2.5): no devuelve
  membresías de un tenant inactivo (el login falla con el ``401`` genérico). Política
  ``dueno_tenant_login`` (``SELECT`` de ``tenant`` acotada a los tenants del usuario de
  ``app.auth_usuario``, la GUC que ya fija ``buscar_login``) y ``GRANT SELECT (activo)``
  a ``auth_owner``. Su cuerpo vacía ahora las once GUC ``app.auth_*`` (0004 y 0016).
- ``tenant``: la aplicación pasa de ``SELECT`` de tabla (0002) a ``SELECT (id, nombre,
  creado_en, activo)``; ya no lee ``desactivado_en`` ni ``desactivado_por`` (el id del
  desarrollador que desactivó). El modelo los difiere con ``raiseload``.
- ``plataforma_auditoria_insertar`` (0017): la aplicación solo inserta las acciones de
  sesión, empresas y usuarios de R33 (nunca las ``desarrollador_*`` del operador);
  ``login_ok`` sin tenant y con ``objeto_id`` = el propio desarrollador; las demás con
  tenant.

Orden (C3/C5): políticas y ``GRANT`` -> ``CREATE FUNCTION`` -> ``REVOKE ALL`` de
``PUBLIC`` y de los roles de Supabase -> ``GRANT EXECUTE`` a la aplicación -> ``CREATE``
transitorio en ``acceso`` y membresía transitoria ``WITH INHERIT FALSE, SET TRUE`` ->
``OWNER TO plataforma_owner`` -> ``REVOKE CREATE`` y fin de la membresía; lo mismo con
``auth_owner`` para reemplazar ``buscar_login`` (``SET LOCAL ROLE``: conserva dueño y
``EXECUTE``); al terminar se comprueba que no quede nada (C8).

``downgrade``: borra las tres funciones como ``plataforma_owner``, restaura el cuerpo de
``buscar_login`` de 0004, sus políticas, el ``SELECT`` de tabla de ``tenant`` y la
política de auditoría de 0017. No borra datos: las empresas creadas desde la consola
quedan como cualquier otra (la guarda de datos de 0017 sigue protegiendo la auditoría y
las empresas inactivas).

Revision ID: 0018_funciones_plataforma
Revises: 0017_plataforma
Create Date: 2026-11-20
"""

import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0018_funciones_plataforma"
down_revision: str | Sequence[str] | None = "0017_plataforma"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE_VAR = "APP_DB_USER"
AUTH_OWNER = "auth_owner"
PLATAFORMA_OWNER = "plataforma_owner"
SUPABASE_ROLES = ("anon", "authenticated", "service_role")

LISTAR = "acceso.plataforma_listar_tenants(uuid)"
CREAR = "acceso.plataforma_crear_tenant(uuid, uuid, text, text, text, text, text, text, text, text)"
CAMBIAR_ESTADO = "acceso.plataforma_cambiar_estado_tenant(uuid, uuid, boolean)"
FUNCTIONS = (LISTAR, CREAR, CAMBIAR_ESTADO)
BUSCAR_LOGIN = "acceso.buscar_login(text)"

# Tablas existentes que tocan las políticas nuevas de plataforma_owner.
OWNER_TABLES = ("tenant", "usuario", "membresia", "empresa")

# Acciones de R33 que inserta la aplicación (nunca las desarrollador_* del operador).
ACCIONES_APP = (
    "login_ok",
    "empresa_creada",
    "empresa_desactivada",
    "empresa_reactivada",
    "empresa_logo_subido",
    "usuario_desactivado",
    "usuario_reactivado",
)

# Todas las GUC de las políticas de plataforma_owner (0017 y esta): cada función las vacía.
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
# Las once GUC de auth_owner (0004 y 0016): el nuevo cuerpo de buscar_login las vacía.
AUTH_GUCS_0004 = (
    "app.auth_email",
    "app.auth_usuario",
    "app.auth_inv_validar",
    "app.auth_inv_aceptar",
    "app.auth_usuario_nuevo",
    "app.auth_tenant_nuevo",
)
AUTH_GUCS = (
    *AUTH_GUCS_0004,
    "app.auth_rec_email",
    "app.auth_rec_usuario",
    "app.auth_rec_clave",
    "app.auth_reset_clave",
    "app.auth_reset_usuario",
)

# (tabla, política): lista cerrada (la fijan test_plataforma_catalogo.py y test_catalog_rls.py).
OWNER_POLICIES = (
    ("desarrollador", "dueno_plat_desarrollador_actor"),
    ("tenant", "dueno_plat_tenant_listar"),
    ("empresa", "dueno_plat_empresa_listar"),
    ("membresia", "dueno_plat_membresia_listar"),
    ("tenant", "dueno_plat_tenant_crear"),
    ("tenant", "dueno_plat_tenant_recien_creado"),
    ("usuario", "dueno_plat_usuario_crear"),
    ("membresia", "dueno_plat_membresia_crear"),
    ("empresa", "dueno_plat_empresa_crear"),
    ("tenant", "dueno_plat_tenant_estado_leer"),
    ("tenant", "dueno_plat_tenant_estado"),
)
AUTH_POLICIES = (("tenant", "dueno_tenant_login"),)
APP_TENANT_COLUMNS = ("id", "nombre", "creado_en", "activo")

DESARROLLADOR = "NULLIF(current_setting('app.desarrollador_id', true), '')::uuid"
_UUID = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def _setting(guc: str) -> str:
    return f"pg_catalog.current_setting('{guc}', true)"


def uuid_setting(guc: str) -> str:
    """UUID de ``guc``; ``NULL`` si falta o no es un UUID en minúsculas."""
    value = _setting(guc)
    return f"(CASE WHEN {value} ~ '{_UUID}' THEN ({value})::uuid END)"


ACTOR = uuid_setting("app.plat_actor")
LISTAR_GUC = uuid_setting("app.plat_listar")
TENANT_NUEVO = uuid_setting("app.plat_tenant_nuevo")
USUARIO_NUEVO = uuid_setting("app.plat_usuario_nuevo")
TENANT_ESTADO = uuid_setting("app.plat_tenant_estado")
AUTH_USUARIO = uuid_setting("app.auth_usuario")


def desarrollador_activo(guc: str) -> str:
    """El desarrollador del UUID ``guc`` existe y está activo (bajo la RLS del dueño)."""
    return f"EXISTS (SELECT 1 FROM desarrollador d WHERE d.id = {guc} AND d.activo)"  # noqa: S608


RECIEN_CREADO = (
    f"EXISTS (SELECT 1 FROM tenant t WHERE t.id = {TENANT_NUEVO} "  # noqa: S608
    "AND t.creado_en = now())"
)


def _clear(gucs: Sequence[str]) -> str:
    return (
        "PERFORM pg_catalog.set_config(g, '', true) "
        "FROM pg_catalog.unnest(ARRAY['" + "', '".join(gucs) + "']::text[]) AS g;"
    )


_CLEAR = _clear(OWNER_GUCS)
_HEADER = "LANGUAGE plpgsql STRICT SECURITY DEFINER SET search_path = pg_catalog, pg_temp"
# Formato completo del hash de argon2-cffi (como 0016 y 0017), sin barras invertidas (B1).
_HASH_FORMAT = (
    "'^[$]argon2id[$]v=19[$]m=[0-9]+,t=[0-9]+,p=[0-9]+[$][A-Za-z0-9+/]+[$][A-Za-z0-9+/]+$'"
)
_HASH_MAX_LENGTH = 255
_HASH_INVALIDO = (
    f"IF p_password_hash !~ {_HASH_FORMAT} "
    f"OR pg_catalog.length(p_password_hash) > {_HASH_MAX_LENGTH} THEN\n"
    "        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'hash_invalido';\n"
    "    END IF;"
)
# A5/R36: primera comprobación de cada función; excepción estática, sin datos.
_DESARROLLADOR_ACTIVO = (
    "PERFORM pg_catalog.set_config('app.plat_actor', p_desarrollador::text, true);\n"
    "    SELECT d.activo INTO v_activo FROM public.desarrollador AS d "
    "WHERE d.id = p_desarrollador;\n"
    "    IF NOT FOUND OR NOT v_activo THEN\n"
    "        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'desarrollador_no_autorizado';\n"
    "    END IF;"
)  # noqa: S608 - solo constantes del módulo

CREATE_LISTAR = f"""
CREATE FUNCTION acceso.plataforma_listar_tenants(p_desarrollador uuid)
RETURNS TABLE (id uuid, nombre text, activo boolean, creado_en timestamptz,
               tiene_logo boolean, n_membresias_activas bigint, n_admins_activos bigint)
{_HEADER}
AS $fn$
DECLARE
    v_activo boolean;
BEGIN
    {_CLEAR}
    {_DESARROLLADOR_ACTIVO}
    PERFORM pg_catalog.set_config('app.plat_listar', p_desarrollador::text, true);
    RETURN QUERY SELECT t.id, t.nombre, t.activo, t.creado_en,
            EXISTS (SELECT 1 FROM public.empresa AS e
                    WHERE e.tenant_id = t.id AND e.logo_id IS NOT NULL),
            (SELECT pg_catalog.count(*) FROM public.membresia AS m
                WHERE m.tenant_id = t.id AND m.activa),
            (SELECT pg_catalog.count(*) FROM public.membresia AS m
                WHERE m.tenant_id = t.id AND m.activa AND m.rol = 'admin')
        FROM public.tenant AS t
        ORDER BY t.creado_en DESC, t.id;
    {_CLEAR}
    RETURN;
END
$fn$
"""  # noqa: S608 - solo constantes del módulo

CREATE_CREAR = f"""
CREATE FUNCTION acceso.plataforma_crear_tenant(
    p_desarrollador uuid, p_tenant uuid, p_nombre text, p_direccion text, p_nit text,
    p_telefono text, p_correo text, p_admin_email text, p_admin_nombre text,
    p_password_hash text)
RETURNS TABLE (tenant_id uuid, usuario_id uuid)
{_HEADER}
AS $fn$
DECLARE
    v_activo boolean;
    v_usuario uuid;
    v_filas bigint;
BEGIN
    {_CLEAR}
    {_DESARROLLADOR_ACTIVO}
    {_HASH_INVALIDO}
    PERFORM pg_catalog.set_config('app.plat_tenant_nuevo', p_tenant::text, true);
    INSERT INTO public.tenant (id, nombre) VALUES (p_tenant, p_nombre)
        ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_filas = ROW_COUNT;
    IF v_filas <> 1 THEN
        RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'empresa_existente';
    END IF;
    v_usuario := pg_catalog.gen_random_uuid();
    PERFORM pg_catalog.set_config('app.plat_usuario_nuevo', v_usuario::text, true);
    INSERT INTO public.usuario (id, email, nombre, password_hash, debe_cambiar_password)
        VALUES (v_usuario, p_admin_email, p_admin_nombre, p_password_hash, true)
        ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_filas = ROW_COUNT;
    IF v_filas <> 1 THEN
        RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'email_en_uso';
    END IF;
    INSERT INTO public.membresia (tenant_id, usuario_id, rol)
        VALUES (p_tenant, v_usuario, 'admin');
    INSERT INTO public.empresa
        (tenant_id, nombre, direccion, nit, telefono, correo, actualizada_por)
        VALUES (p_tenant, p_nombre, p_direccion, NULLIF(p_nit, ''), NULLIF(p_telefono, ''),
                NULLIF(p_correo, ''), v_usuario);
    {_CLEAR}
    RETURN QUERY SELECT p_tenant, v_usuario;
END
$fn$
"""  # noqa: S608 - solo constantes del módulo

CREATE_CAMBIAR_ESTADO = f"""
CREATE FUNCTION acceso.plataforma_cambiar_estado_tenant(
    p_desarrollador uuid, p_tenant uuid, p_activo boolean)
RETURNS boolean
{_HEADER}
AS $fn$
DECLARE
    v_activo boolean;
BEGIN
    {_CLEAR}
    {_DESARROLLADOR_ACTIVO}
    PERFORM pg_catalog.set_config('app.plat_tenant_estado', p_tenant::text, true);
    UPDATE public.tenant AS t
        SET activo = p_activo,
            desactivado_en = CASE WHEN p_activo THEN NULL ELSE pg_catalog.now() END,
            desactivado_por = CASE WHEN p_activo THEN NULL ELSE p_desarrollador END
        WHERE t.id = p_tenant AND t.activo <> p_activo;
    IF NOT FOUND THEN
        SELECT t.activo INTO v_activo FROM public.tenant AS t WHERE t.id = p_tenant;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'empresa_no_encontrada';
        END IF;
    END IF;
    {_CLEAR}
    RETURN p_activo;
END
$fn$
"""  # noqa: S608 - solo constantes del módulo

CREATE_STATEMENTS = (CREATE_LISTAR, CREATE_CREAR, CREATE_CAMBIAR_ESTADO)


def _buscar_login(gucs: Sequence[str], *, solo_activos: bool) -> str:
    """``acceso.buscar_login`` (0004); con ``solo_activos``, sin tenants inactivos (0018)."""
    clear = _clear(gucs)
    membresias = (
        "FROM public.membresia AS m JOIN public.tenant AS t ON t.id = m.tenant_id\n"
        "            WHERE m.usuario_id = v_id AND m.activa AND t.activo;"
        if solo_activos
        else "FROM public.membresia AS m WHERE m.usuario_id = v_id AND m.activa;"
    )
    return f"""
CREATE OR REPLACE FUNCTION acceso.buscar_login(p_email text)
RETURNS TABLE (usuario_id uuid, password_hash text, activo boolean, tenant_id uuid, rol text)
{_HEADER}
AS $fn$
DECLARE
    v_id uuid;
    v_hash text;
    v_activo boolean;
BEGIN
    {clear}
    PERFORM pg_catalog.set_config('app.auth_email', p_email, true);
    SELECT u.id, u.password_hash, u.activo INTO v_id, v_hash, v_activo
        FROM public.usuario AS u WHERE u.email = p_email;
    IF FOUND THEN
        PERFORM pg_catalog.set_config('app.auth_usuario', v_id::text, true);
        RETURN QUERY SELECT v_id, v_hash, v_activo, m.tenant_id, m.rol
            {membresias}
        IF NOT FOUND THEN
            RETURN QUERY SELECT v_id, v_hash, v_activo, NULL::uuid, NULL::text;
        END IF;
    END IF;
    {clear}
    RETURN;
END
$fn$
"""  # noqa: S608 - solo constantes del módulo


# Cuerpo nuevo (0018) y el de 0004, idéntico carácter a carácter (huella del catálogo C6).
REPLACE_BUSCAR_LOGIN = _buscar_login(AUTH_GUCS, solo_activos=True)
RESTORE_BUSCAR_LOGIN = _buscar_login(AUTH_GUCS_0004, solo_activos=False)

_ROLE_EXISTS = text("select exists (select 1 from pg_roles where rolname = :name)")
_ROLE_SKIPS_RLS = text("select rolsuper or rolbypassrls from pg_roles where rolname = :name")
_ROLE_UNSAFE = text(
    "select coalesce((select r.rolsuper or r.rolbypassrls or r.rolcanlogin or r.rolcreaterole "
    "or r.rolcreatedb or r.rolreplication "
    "or exists (select 1 from pg_auth_members m where m.member = r.oid) "
    "from pg_roles r where r.rolname = :name), true)"
)
_IS_MEMBER = text("select pg_has_role(:member, :owner, 'MEMBER')")
# Igual que 0004/0017 (C8): por rolname exacto; la membresía ADMIN del creador en Supabase,
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


def require_owners(conn: Connection) -> None:
    """Falla con un mensaje claro si falta ``auth_owner`` o ``plataforma_owner``."""
    for name in (AUTH_OWNER, PLATAFORMA_OWNER):
        if not conn.scalar(_ROLE_EXISTS, {"name": name}):
            raise RuntimeError(
                f"Falta el rol {name}: créalo con docker/postgres/init/01-app-role.sh "
                "(o flask preparar-roles en un PostgreSQL administrado; spec 017) antes de "
                "migrar."
            )


def require_owner_attributes(conn: Connection) -> None:
    """Falla si un dueño no es un rol inerte; el mensaje no lleva el nombre del rol."""
    for name in (AUTH_OWNER, PLATAFORMA_OWNER):
        if conn.scalar(_ROLE_UNSAFE, {"name": name}):
            raise RuntimeError(
                "Un rol dueño de las funciones de acceso no es seguro: no puede ser "
                "SUPERUSER, tener BYPASSRLS, LOGIN, CREATEROLE, CREATEDB ni REPLICATION, "
                "ni tener membresía en otro rol. Corrígelo con "
                "docker/postgres/init/01-app-role.sh (spec 017) antes de migrar."
            )


def require_postgres_16(conn: Connection) -> None:
    """``WITH INHERIT FALSE, SET TRUE`` exige PostgreSQL 16 o superior."""
    if int(conn.scalar(text("show server_version_num"))) < 160000:
        raise RuntimeError(
            "La migración 0018 exige PostgreSQL 16 o superior (membresía transitoria "
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
    for owner in (AUTH_OWNER, PLATAFORMA_OWNER):
        if conn.scalar(_IS_MEMBER, {"member": name, "owner": owner}):
            raise RuntimeError(
                f"El rol de la aplicación indicado en {APP_ROLE_VAR} es miembro de un rol "
                "dueño de las funciones de acceso y podría actuar como él: quita esa "
                "membresía antes de migrar."
            )
    return name


def require_no_leftover_privileges(conn: Connection) -> None:
    """C5: al terminar, los dueños sin ``CREATE`` en ``acceso`` y el migrador no es miembro."""
    for owner in (AUTH_OWNER, PLATAFORMA_OWNER):
        if conn.scalar(_OWNER_CAN_CREATE, {"owner": owner}) or conn.scalar(
            _MIGRATOR_IS_MEMBER, {"owner": owner}
        ):
            raise RuntimeError(
                "Tras la migración 0018, un rol dueño de las funciones de acceso conserva "
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
                f"La migración 0018 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def _transient_membership(owner: str, migrator: str) -> tuple[list[str], list[str]]:
    opening = [f"GRANT {owner} TO {migrator} WITH INHERIT FALSE, SET TRUE"]
    closing = [f"REVOKE {owner} FROM {migrator}"]
    return opening, closing


def _audit_policy(app: str, acciones: Sequence[str] | None) -> str:
    """Política ``INSERT`` de la aplicación en la auditoría (0017; acotada en 0018)."""
    activo = desarrollador_activo(DESARROLLADOR)
    check = f"desarrollador_id = {DESARROLLADOR} AND {activo}"
    if acciones is not None:
        lista = ", ".join(f"'{accion}'" for accion in acciones)
        check += (
            f" AND accion IN ({lista}) "
            f"AND ((accion = 'login_ok' AND tenant_id IS NULL AND objeto_id = {DESARROLLADOR}) "
            "OR (accion <> 'login_ok' AND tenant_id IS NOT NULL))"
        )
    return (
        f"CREATE POLICY plataforma_auditoria_insertar ON plataforma_auditoria FOR INSERT "
        f"TO {app} WITH CHECK ({check})"
    )


def _owner_policies(owner: str) -> list[str]:
    actor = desarrollador_activo(ACTOR)
    listar = desarrollador_activo(LISTAR_GUC)
    return [
        # --- quien llama: solo su propia fila (A5) ---
        f"CREATE POLICY dueno_plat_desarrollador_actor ON desarrollador FOR SELECT "
        f"TO {owner} USING (id = {ACTOR})",
        # --- listar (R21): identidad, logo sí/no y conteos ---
        f"CREATE POLICY dueno_plat_tenant_listar ON tenant FOR SELECT TO {owner} USING ({listar})",
        f"CREATE POLICY dueno_plat_empresa_listar ON empresa FOR SELECT TO {owner} "
        f"USING ({listar})",
        f"CREATE POLICY dueno_plat_membresia_listar ON membresia FOR SELECT TO {owner} "
        f"USING ({listar})",
        # --- crear (R16): todo ligado al tenant creado en esta transacción ---
        f"CREATE POLICY dueno_plat_tenant_crear ON tenant FOR INSERT TO {owner} "
        f"WITH CHECK (id = {TENANT_NUEVO} AND activo AND desactivado_en IS NULL "
        f"AND desactivado_por IS NULL AND {actor})",
        f"CREATE POLICY dueno_plat_tenant_recien_creado ON tenant FOR SELECT TO {owner} "
        f"USING (id = {TENANT_NUEVO} AND creado_en = now())",
        f"CREATE POLICY dueno_plat_usuario_crear ON usuario FOR INSERT TO {owner} "
        f"WITH CHECK (id = {USUARIO_NUEVO} AND activo AND debe_cambiar_password "
        f"AND {RECIEN_CREADO} AND {actor})",
        f"CREATE POLICY dueno_plat_membresia_crear ON membresia FOR INSERT TO {owner} "
        f"WITH CHECK (tenant_id = {TENANT_NUEVO} AND usuario_id = {USUARIO_NUEVO} "
        f"AND rol = 'admin' AND activa AND {RECIEN_CREADO} AND {actor})",
        f"CREATE POLICY dueno_plat_empresa_crear ON empresa FOR INSERT TO {owner} "
        f"WITH CHECK (tenant_id = {TENANT_NUEVO} AND actualizada_por = {USUARIO_NUEVO} "
        f"AND logo_id IS NULL AND {RECIEN_CREADO} AND {actor})",
        # --- cambiar estado (R22): solo activo, fecha y autor del tenant objetivo ---
        f"CREATE POLICY dueno_plat_tenant_estado_leer ON tenant FOR SELECT TO {owner} "
        f"USING (id = {TENANT_ESTADO} AND {actor})",
        f"CREATE POLICY dueno_plat_tenant_estado ON tenant FOR UPDATE TO {owner} "
        f"USING (id = {TENANT_ESTADO} AND {actor}) "
        f"WITH CHECK (id = {TENANT_ESTADO} AND ((activo AND desactivado_en IS NULL "
        "AND desactivado_por IS NULL) OR (NOT activo AND desactivado_en = now() "
        f"AND desactivado_por = {ACTOR})))",
    ]


def _owner_grants(owner: str) -> list[str]:
    # Mínimos y por columna; nunca DELETE ni TRUNCATE. creado_en nunca en INSERT.
    return [
        f"GRANT SELECT (id, nombre, activo, creado_en) ON tenant TO {owner}",
        f"GRANT INSERT (id, nombre) ON tenant TO {owner}",
        f"GRANT UPDATE (activo, desactivado_en, desactivado_por) ON tenant TO {owner}",
        f"GRANT INSERT (id, email, nombre, password_hash, debe_cambiar_password) "
        f"ON usuario TO {owner}",
        f"GRANT SELECT (tenant_id, rol, activa) ON membresia TO {owner}",
        f"GRANT INSERT (tenant_id, usuario_id, rol) ON membresia TO {owner}",
        f"GRANT SELECT (tenant_id, logo_id) ON empresa TO {owner}",
        f"GRANT INSERT (tenant_id, nombre, direccion, nit, telefono, correo, actualizada_por) "
        f"ON empresa TO {owner}",
    ]


def _auth_policy(owner: str) -> str:
    return (
        f"CREATE POLICY dueno_tenant_login ON tenant FOR SELECT TO {owner} "  # noqa: S608
        "USING (EXISTS (SELECT 1 FROM membresia m "
        f"WHERE m.tenant_id = tenant.id AND m.usuario_id = {AUTH_USUARIO}))"
    )


def _replace_buscar_login(auth: str, migrator: str, body: str) -> list[str]:
    """``CREATE OR REPLACE`` como ``auth_owner``: conserva dueño, ``proacl`` y firma."""
    opening, closing = _transient_membership(auth, migrator)
    return [
        f"GRANT CREATE ON SCHEMA acceso TO {auth}",
        *opening,
        f"SET LOCAL ROLE {auth}",
        body,
        "RESET ROLE",
        f"REVOKE CREATE ON SCHEMA acceso FROM {auth}",
        *closing,
    ]


def upgrade() -> None:
    conn = op.get_bind()
    require_owners(conn)
    require_owner_attributes(conn)
    require_postgres_16(conn)
    quote = conn.dialect.identifier_preparer.quote
    app = quote(_app_role(conn))
    owner = quote(PLATAFORMA_OWNER)
    auth = quote(AUTH_OWNER)
    migrator = quote(conn.scalar(text("select current_user")))
    supabase = [quote(role) for role in SUPABASE_ROLES if conn.scalar(_ROLE_EXISTS, {"name": role})]
    opening, closing = _transient_membership(owner, migrator)

    statements = [*_owner_policies(owner), *_owner_grants(owner)]
    # tenant.activo en el login del tenant (plan §2.5).
    statements += [_auth_policy(auth), f"GRANT SELECT (activo) ON tenant TO {auth}"]
    # La aplicación ya no lee desactivado_en ni desactivado_por.
    statements += [
        f"REVOKE SELECT ON tenant FROM {app}",  # noqa: S608 - rol citado
        f"GRANT SELECT ({', '.join(APP_TENANT_COLUMNS)}) ON tenant TO {app}",  # noqa: S608
    ]
    # La aplicación solo audita sus acciones (nunca las del operador).
    statements += [
        "DROP POLICY plataforma_auditoria_insertar ON plataforma_auditoria",
        _audit_policy(app, ACCIONES_APP),
    ]
    statements += [*CREATE_STATEMENTS]
    revoked = ", ".join(["PUBLIC", *supabase])
    statements += [f"REVOKE ALL ON FUNCTION {fn} FROM {revoked}" for fn in FUNCTIONS]
    statements += [f"GRANT EXECUTE ON FUNCTION {fn} TO {app}" for fn in FUNCTIONS]
    statements += [f"GRANT CREATE ON SCHEMA acceso TO {owner}", *opening]
    statements += [f"ALTER FUNCTION {fn} OWNER TO {owner}" for fn in FUNCTIONS]
    statements += [f"REVOKE CREATE ON SCHEMA acceso FROM {owner}", *closing]
    statements += _replace_buscar_login(auth, migrator, REPLACE_BUSCAR_LOGIN)
    execute_statements(conn, statements)
    require_no_leftover_privileges(conn)


def downgrade() -> None:
    conn = op.get_bind()
    require_owners(conn)
    require_postgres_16(conn)
    quote = conn.dialect.identifier_preparer.quote
    app = quote(_app_role(conn))
    owner = quote(PLATAFORMA_OWNER)
    auth = quote(AUTH_OWNER)
    migrator = quote(conn.scalar(text("select current_user")))
    opening, closing = _transient_membership(owner, migrator)
    # Solo el dueño (plataforma_owner) puede borrar sus funciones: SET LOCAL ROLE.
    statements = [*opening, f"SET LOCAL ROLE {owner}"]
    statements += [f"DROP FUNCTION {fn}" for fn in FUNCTIONS]
    statements += ["RESET ROLE", *closing]
    statements += _replace_buscar_login(auth, migrator, RESTORE_BUSCAR_LOGIN)
    statements += [
        f"DROP POLICY {policy} ON {table}" for table, policy in (*OWNER_POLICIES, *AUTH_POLICIES)
    ]
    # Antes de 0018 plataforma_owner no tenía nada en estas tablas.
    statements += [f"REVOKE ALL ON {', '.join(OWNER_TABLES)} FROM {owner}"]
    statements += [f"REVOKE SELECT (activo) ON tenant FROM {auth}"]  # noqa: S608
    statements += [
        f"REVOKE SELECT ON tenant FROM {app}",  # noqa: S608 - rol citado, sin datos
        f"GRANT SELECT ON tenant TO {app}",  # noqa: S608
    ]
    statements += [
        "DROP POLICY plataforma_auditoria_insertar ON plataforma_auditoria",
        _audit_policy(app, None),
    ]
    execute_statements(conn, statements)
    require_no_leftover_privileges(conn)
