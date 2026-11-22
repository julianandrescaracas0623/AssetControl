"""Editar la ficha y reemplazar el logo de una empresa desde la consola (spec 017, C1, T12).

``plan.md`` §10.1 y §10.2; ``spec.md`` R41–R45, R52; A19, A21, A21b, A22, A23, A26.
Mismo patrón que 0018, 0027, 0028 y 0029 (``plpgsql``, ``SECURITY DEFINER``, ``STRICT``,
``SET search_path = pg_catalog, pg_temp``, todo calificado, SQL estático, dueña
``plataforma_owner``, ``EXECUTE`` solo para el rol de la aplicación). Cada función vacía
al empezar y al terminar **todas** las GUC ``app.plat_*`` conocidas (las dieciséis de
0017–0029 y la de aquí), fija solo las suyas con valores que ella recibe y nunca lee una
GUC; su primera comprobación (A5, R36) es que ``p_desarrollador`` exista y esté activo.

- ``acceso.plataforma_leer_empresa(p_desarrollador, p_tenant)`` -> ``nombre``,
  ``direccion``, ``nit``, ``telefono``, ``correo``, ``tiene_logo`` (R41; lista cerrada: ni
  ``actualizada_por`` ni el id del logo). Empresa inexistente -> ``P0002
  empresa_no_encontrada``; tenant sin ficha -> ``P0001 empresa_sin_datos``.
- ``acceso.plataforma_actualizar_empresa(p_desarrollador, p_tenant, p_nombre, p_direccion,
  p_nit, p_telefono, p_correo)`` -> ``boolean`` (``cambiado``; R42, R43). Los opcionales
  vacíos viajan como ``''`` (``STRICT``) y se guardan como ``NULL``; la validación es la
  de Flask (013 R1) y los ``CHECK`` de 0014 son el respaldo. Con la fila de ``empresa``
  bloqueada (``FOR UPDATE``; ``lock_timeout`` acotado, ``55P03 empresa_ocupada``),
  actualiza las cinco columnas y ``actualizada_en`` **solo si algún valor cambia**
  (``IS DISTINCT FROM``); ``actualizada_por`` no se toca (quien actúa no es un ``usuario``;
  la columna es ``NOT NULL`` y conserva el valor que ya tenía; el actor queda en la
  auditoría). **Q-E1 = (a):** si el nombre de la ficha cambia, también
  ``tenant.nombre`` (si difiere), en la misma transacción y bajo la misma fila bloqueada;
  nunca ``activo`` ni ``desactivado_*``.
- ``acceso.plataforma_registrar_logo`` **rehecha** (R44): misma firma de entrada, devuelve
  además ``reemplazado``. Ya no hay ``logo_existente``: bloquea la fila de ``empresa``
  (``FOR UPDATE``, así ``reemplazado`` es exacto aunque el admin cambie su logo a la vez) y,
  si la empresa tenía otro logo, lo reemplaza. Mismo ``logo_id`` vigente -> sin escribir
  (``creado = false``). El resto del orden de rechazos de 0029 no cambia. El logo anterior
  (fila y archivo) se conserva: los informes congelados lo usan (013 R2). Como cambia el
  tipo devuelto, ``DROP FUNCTION`` (como su dueño) y ``CREATE``.

La auditoría (``empresa_editada``, ``empresa_logo_reemplazado``, ``empresa_logo_subido``)
la escribe la aplicación en la misma transacción. Aquí se amplían con las tres acciones de
C1 (``empresa_editada``, ``empresa_logo_reemplazado`` y ``usuario_editado``; la última la
usa la T13) el ``CHECK plataforma_auditoria_accion_valida`` de 0017 y la política
``plataforma_auditoria_insertar`` de la aplicación (0018), una sola vez.

Políticas ``TO plataforma_owner`` nuevas (una por comando; GUC validada por formato), con
el desarrollador de ``app.plat_actor`` activo, sobre la empresa de
``app.plat_empresa_tenant``:

- ``empresa`` ``FOR SELECT`` y ``FOR UPDATE`` (``WITH CHECK``: mismo tenant y
  ``actualizada_en = now()``);
- ``tenant`` ``FOR SELECT`` y ``FOR UPDATE`` (``WITH CHECK``: mismo tenant y su nombre igual
  al de la ficha: ``tenant.nombre`` solo sigue a ``empresa.nombre``).

La política ``dueno_plat_empresa_logo`` de 0029 pierde ``logo_id IS NULL`` (reemplazo) y
mantiene su ``WITH CHECK`` (``logo_id = app.plat_logo_id``).

``GRANT`` por columna mínimos, sin ``DELETE``: ``empresa`` ``SELECT`` y ``UPDATE`` de
``nombre, direccion, nit, telefono, correo`` (A19 cambia: el desarrollador lee la ficha y
si hay logo, nunca ``actualizada_por`` ni ``actualizada_en``); ``tenant`` ``UPDATE
(nombre)``.

``downgrade``: borra las dos funciones nuevas y la rehecha (como ``plataforma_owner``),
recrea la de 0029 con su mismo cuerpo, restaura la política de logo, borra las políticas y
los ``GRANT`` de aquí y vuelve al ``CHECK`` y a la política de auditoría de 0018. No borra
datos: si ya hay auditoría con las acciones de C1, el ``CHECK`` de antes se añade ``NOT
VALID`` (rige para filas nuevas y conserva las existentes).

Revision ID: 0030_plataforma_edicion_empresa
Revises: 0029_plataforma_logo
Create Date: 2026-11-21
"""

import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0030_plataforma_edicion_empresa"
down_revision: str | Sequence[str] | None = "0029_plataforma_logo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE_VAR = "APP_DB_USER"
AUTH_OWNER = "auth_owner"
PLATAFORMA_OWNER = "plataforma_owner"
SUPABASE_ROLES = ("anon", "authenticated", "service_role")

LEER = "acceso.plataforma_leer_empresa(uuid, uuid)"
ACTUALIZAR = "acceso.plataforma_actualizar_empresa(uuid, uuid, text, text, text, text, text)"
REGISTRAR = "acceso.plataforma_registrar_logo(uuid, uuid, uuid, text, integer, integer, integer)"
FUNCTIONS = (LEER, ACTUALIZAR, REGISTRAR)

# Las dieciséis GUC de 0017, 0018, 0027, 0028 y 0029, en su orden (las vacía la de 0029).
OWNER_GUCS_0029 = (
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
)
# Y la de aquí: la empresa cuya ficha se lee o se edita.
OWNER_GUCS = (*OWNER_GUCS_0029, "app.plat_empresa_tenant")

# Acciones de la aplicación en 0018 y las tres de C1 (la de usuario la usa la T13).
ACCIONES_APP_0018 = (
    "login_ok",
    "empresa_creada",
    "empresa_desactivada",
    "empresa_reactivada",
    "empresa_logo_subido",
    "usuario_desactivado",
    "usuario_reactivado",
)
ACCIONES_C1 = ("empresa_editada", "empresa_logo_reemplazado", "usuario_editado")
ACCIONES_APP = (*ACCIONES_APP_0018, *ACCIONES_C1)
# Lista del CHECK de 0017 (R33) y la ampliada (se añaden al final).
ACCIONES_0017 = (
    *ACCIONES_APP_0018,
    "desarrollador_creado",
    "desarrollador_restablecido",
    "desarrollador_desactivado",
    "desarrollador_reactivado",
)
ACCIONES = (*ACCIONES_0017, *ACCIONES_C1)
CHECK_ACCION = "plataforma_auditoria_accion_valida"

# (tabla, política): lista cerrada (la fijan test_plataforma_catalogo.py y test_migrations.py).
POLICIES = (
    ("empresa", "dueno_plat_empresa_ficha_leer"),
    ("empresa", "dueno_plat_empresa_ficha"),
    ("tenant", "dueno_plat_tenant_ficha_leer"),
    ("tenant", "dueno_plat_tenant_ficha"),
)
FICHA = ("nombre", "direccion", "nit", "telefono", "correo")

# Espera máxima de la fila de empresa (la puede tener el admin editando su ficha o su logo):
# pasado este tiempo, ``55P03 empresa_ocupada`` (503 en la API), como 0027 y 0029.
LOCK_TIMEOUT = "5s"

_UUID = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def uuid_setting(guc: str) -> str:
    """UUID de ``guc``; ``NULL`` si falta o no es un UUID en minúsculas (como 0018)."""
    value = f"pg_catalog.current_setting('{guc}', true)"
    return f"(CASE WHEN {value} ~ '{_UUID}' THEN ({value})::uuid END)"


ACTOR = uuid_setting("app.plat_actor")
EMPRESA_TENANT = uuid_setting("app.plat_empresa_tenant")
LOGO_TENANT = uuid_setting("app.plat_logo_tenant")
LOGO_ID = uuid_setting("app.plat_logo_id")
ACTOR_ACTIVO = f"EXISTS (SELECT 1 FROM desarrollador d WHERE d.id = {ACTOR} AND d.activo)"  # noqa: S608
DESARROLLADOR = "NULLIF(current_setting('app.desarrollador_id', true), '')::uuid"
DESARROLLADOR_ACTIVO = (
    f"EXISTS (SELECT 1 FROM desarrollador d WHERE d.id = {DESARROLLADOR} AND d.activo)"  # noqa: S608
)
# tenant.nombre solo puede quedar igual al nombre de su ficha (Q-E1).
_NOMBRE_DE_LA_FICHA = (
    "EXISTS (SELECT 1 FROM empresa e WHERE e.tenant_id = tenant.id "  # noqa: S608
    "AND e.nombre = tenant.nombre)"
)


def _clear(gucs: Sequence[str]) -> str:
    return (
        "PERFORM pg_catalog.set_config(g, '', true) "
        "FROM pg_catalog.unnest(ARRAY['" + "', '".join(gucs) + "']::text[]) AS g;"
    )


_CLEAR = _clear(OWNER_GUCS)
_CLEAR_0029 = _clear(OWNER_GUCS_0029)
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
# Sin fila de empresa: 404 si el tenant no existe; si existe, no tiene ficha (como la 013).
_SIN_FICHA = (
    "IF NOT FOUND THEN\n"
    "        PERFORM 1 FROM public.tenant AS t WHERE t.id = p_tenant;\n"
    "        IF NOT FOUND THEN\n"
    "            RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'empresa_no_encontrada';\n"
    "        END IF;\n"
    "        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'empresa_sin_datos';\n"
    "    END IF;"
)  # noqa: S608 - solo constantes del módulo

CREATE_LEER = f"""
CREATE FUNCTION acceso.plataforma_leer_empresa(p_desarrollador uuid, p_tenant uuid)
RETURNS TABLE (nombre text, direccion text, nit text, telefono text, correo text,
               tiene_logo boolean)
{_HEADER}
AS $fn$
DECLARE
    v_activo boolean;
    v_nombre text;
    v_direccion text;
    v_nit text;
    v_telefono text;
    v_correo text;
    v_tiene_logo boolean;
BEGIN
    {_CLEAR}
    {_DESARROLLADOR_ACTIVO}
    PERFORM pg_catalog.set_config('app.plat_empresa_tenant', p_tenant::text, true);
    SELECT e.nombre, e.direccion, e.nit, e.telefono, e.correo, e.logo_id IS NOT NULL
        INTO v_nombre, v_direccion, v_nit, v_telefono, v_correo, v_tiene_logo
        FROM public.empresa AS e WHERE e.tenant_id = p_tenant;
    {_SIN_FICHA}
    {_CLEAR}
    RETURN QUERY SELECT v_nombre, v_direccion, v_nit, v_telefono, v_correo, v_tiene_logo;
    RETURN;
END
$fn$
"""  # noqa: S608 - solo constantes del módulo

CREATE_ACTUALIZAR = f"""
CREATE FUNCTION acceso.plataforma_actualizar_empresa(
    p_desarrollador uuid, p_tenant uuid, p_nombre text, p_direccion text, p_nit text,
    p_telefono text, p_correo text)
RETURNS boolean
{_HEADER}
SET lock_timeout = '{LOCK_TIMEOUT}'
AS $fn$
DECLARE
    v_activo boolean;
    v_nombre text;
    v_direccion text;
    v_nit text;
    v_telefono text;
    v_correo text;
    v_cambiado boolean := false;
    v_filas bigint;
BEGIN
    {_CLEAR}
    {_DESARROLLADOR_ACTIVO}
    PERFORM pg_catalog.set_config('app.plat_empresa_tenant', p_tenant::text, true);
    SELECT e.nombre, e.direccion, e.nit, e.telefono, e.correo
        INTO v_nombre, v_direccion, v_nit, v_telefono, v_correo
        FROM public.empresa AS e WHERE e.tenant_id = p_tenant
        FOR UPDATE;
    {_SIN_FICHA}
    IF p_nombre IS DISTINCT FROM v_nombre
        OR p_direccion IS DISTINCT FROM v_direccion
        OR NULLIF(p_nit, '') IS DISTINCT FROM v_nit
        OR NULLIF(p_telefono, '') IS DISTINCT FROM v_telefono
        OR NULLIF(p_correo, '') IS DISTINCT FROM v_correo THEN
        UPDATE public.empresa AS e
            SET nombre = p_nombre, direccion = p_direccion, nit = NULLIF(p_nit, ''),
                telefono = NULLIF(p_telefono, ''), correo = NULLIF(p_correo, ''),
                actualizada_en = pg_catalog.now()
            WHERE e.tenant_id = p_tenant;
        GET DIAGNOSTICS v_filas = ROW_COUNT;
        IF v_filas <> 1 THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'empresa_sin_datos';
        END IF;
        v_cambiado := true;
    END IF;
    IF p_nombre IS DISTINCT FROM v_nombre THEN
        UPDATE public.tenant AS t SET nombre = p_nombre
            WHERE t.id = p_tenant AND t.nombre <> p_nombre;
    END IF;
    {_CLEAR}
    RETURN v_cambiado;
EXCEPTION WHEN lock_not_available THEN
    RAISE EXCEPTION USING ERRCODE = '55P03', MESSAGE = 'empresa_ocupada';
END
$fn$
"""  # noqa: S608 - solo constantes del módulo

CREATE_REGISTRAR = f"""
CREATE FUNCTION acceso.plataforma_registrar_logo(
    p_desarrollador uuid, p_tenant uuid, p_logo uuid, p_clave text, p_bytes integer,
    p_ancho integer, p_alto integer)
RETURNS TABLE (logo_id uuid, creado boolean, reemplazado boolean)
{_HEADER}
SET lock_timeout = '{LOCK_TIMEOUT}'
AS $fn$
DECLARE
    v_activo boolean;
    v_vigente uuid;
    v_admin uuid;
    v_filas bigint;
BEGIN
    {_CLEAR}
    {_DESARROLLADOR_ACTIVO}
    IF p_clave <> (p_tenant::text || '/' || p_logo::text || '.png') THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'clave_invalida';
    END IF;
    PERFORM pg_catalog.set_config('app.plat_logo_tenant', p_tenant::text, true);
    PERFORM pg_catalog.set_config('app.plat_logo_id', p_logo::text, true);
    SELECT e.logo_id INTO v_vigente FROM public.empresa AS e WHERE e.tenant_id = p_tenant
        FOR UPDATE;
    {_SIN_FICHA}
    IF v_vigente IS NOT NULL AND v_vigente = p_logo THEN
        {_CLEAR}
        RETURN QUERY SELECT p_logo, false, false;
        RETURN;
    END IF;
    SELECT m.usuario_id INTO v_admin FROM public.membresia AS m
        WHERE m.tenant_id = p_tenant AND m.rol = 'admin'
        ORDER BY m.activa DESC, m.usuario_id
        LIMIT 1;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'empresa_sin_admin';
    END IF;
    INSERT INTO public.empresa_logo (id, tenant_id, clave, bytes, ancho, alto, subido_por)
        VALUES (p_logo, p_tenant, p_clave, p_bytes, p_ancho, p_alto, v_admin)
        ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_filas = ROW_COUNT;
    IF v_filas <> 1 THEN
        RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'logo_id_en_uso';
    END IF;
    UPDATE public.empresa AS e SET logo_id = p_logo, actualizada_en = pg_catalog.now()
        WHERE e.tenant_id = p_tenant;
    GET DIAGNOSTICS v_filas = ROW_COUNT;
    IF v_filas <> 1 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'empresa_sin_datos';
    END IF;
    {_CLEAR}
    RETURN QUERY SELECT p_logo, true, v_vigente IS NOT NULL;
    RETURN;
EXCEPTION WHEN lock_not_available THEN
    RAISE EXCEPTION USING ERRCODE = '55P03', MESSAGE = 'empresa_ocupada';
END
$fn$
"""  # noqa: S608 - solo constantes del módulo

CREATE_STATEMENTS = (CREATE_LEER, CREATE_ACTUALIZAR, CREATE_REGISTRAR)

# --- Lo de 0029, para el downgrade (idéntico a su CREATE_REGISTRAR; lo fija test_migrations) ---

RESTORE_REGISTRAR_0029 = f"""
CREATE FUNCTION acceso.plataforma_registrar_logo(
    p_desarrollador uuid, p_tenant uuid, p_logo uuid, p_clave text, p_bytes integer,
    p_ancho integer, p_alto integer)
RETURNS TABLE (logo_id uuid, creado boolean)
{_HEADER}
SET lock_timeout = '{LOCK_TIMEOUT}'
AS $fn$
DECLARE
    v_activo boolean;
    v_vigente uuid;
    v_admin uuid;
    v_filas bigint;
BEGIN
    {_CLEAR_0029}
    {_DESARROLLADOR_ACTIVO}
    IF p_clave <> (p_tenant::text || '/' || p_logo::text || '.png') THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'clave_invalida';
    END IF;
    PERFORM pg_catalog.set_config('app.plat_logo_tenant', p_tenant::text, true);
    PERFORM pg_catalog.set_config('app.plat_logo_id', p_logo::text, true);
    SELECT e.logo_id INTO v_vigente FROM public.empresa AS e WHERE e.tenant_id = p_tenant;
    IF NOT FOUND THEN
        PERFORM 1 FROM public.tenant AS t WHERE t.id = p_tenant;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'empresa_no_encontrada';
        END IF;
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'empresa_sin_datos';
    END IF;
    IF v_vigente IS NOT NULL THEN
        IF v_vigente = p_logo THEN
            {_CLEAR_0029}
            RETURN QUERY SELECT p_logo, false;
            RETURN;
        END IF;
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'logo_existente';
    END IF;
    SELECT m.usuario_id INTO v_admin FROM public.membresia AS m
        WHERE m.tenant_id = p_tenant AND m.rol = 'admin'
        ORDER BY m.activa DESC, m.usuario_id
        LIMIT 1;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'empresa_sin_admin';
    END IF;
    INSERT INTO public.empresa_logo (id, tenant_id, clave, bytes, ancho, alto, subido_por)
        VALUES (p_logo, p_tenant, p_clave, p_bytes, p_ancho, p_alto, v_admin)
        ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_filas = ROW_COUNT;
    IF v_filas <> 1 THEN
        SELECT e.logo_id INTO v_vigente FROM public.empresa AS e WHERE e.tenant_id = p_tenant;
        IF v_vigente = p_logo THEN
            {_CLEAR_0029}
            RETURN QUERY SELECT p_logo, false;
            RETURN;
        END IF;
        RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'logo_id_en_uso';
    END IF;
    UPDATE public.empresa AS e SET logo_id = p_logo, actualizada_en = pg_catalog.now()
        WHERE e.tenant_id = p_tenant AND e.logo_id IS NULL;
    GET DIAGNOSTICS v_filas = ROW_COUNT;
    IF v_filas <> 1 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'logo_existente';
    END IF;
    {_CLEAR_0029}
    RETURN QUERY SELECT p_logo, true;
    RETURN;
EXCEPTION WHEN lock_not_available THEN
    RAISE EXCEPTION USING ERRCODE = '55P03', MESSAGE = 'empresa_ocupada';
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
_IS_MEMBER = text("select pg_has_role(:member, :owner, 'MEMBER')")
# Igual que 0004/0018/0027/0028/0029 (C8): por rolname exacto; la membresía ADMIN del
# creador en Supabase, sin INHERIT ni SET y concedida por otro, no cuenta.
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
            "La migración 0030 exige PostgreSQL 16 o superior (membresía transitoria "
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
            "Tras la migración 0030, el rol dueño de las funciones de plataforma conserva "
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
                f"La migración 0030 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def _owner_policies(owner: str) -> list[str]:
    return [
        f"CREATE POLICY dueno_plat_empresa_ficha_leer ON empresa FOR SELECT TO {owner} "
        f"USING (tenant_id = {EMPRESA_TENANT} AND {ACTOR_ACTIVO})",
        f"CREATE POLICY dueno_plat_empresa_ficha ON empresa FOR UPDATE TO {owner} "
        f"USING (tenant_id = {EMPRESA_TENANT} AND {ACTOR_ACTIVO}) "
        f"WITH CHECK (tenant_id = {EMPRESA_TENANT} AND actualizada_en = now())",
        f"CREATE POLICY dueno_plat_tenant_ficha_leer ON tenant FOR SELECT TO {owner} "
        f"USING (id = {EMPRESA_TENANT} AND {ACTOR_ACTIVO})",
        f"CREATE POLICY dueno_plat_tenant_ficha ON tenant FOR UPDATE TO {owner} "
        f"USING (id = {EMPRESA_TENANT} AND {ACTOR_ACTIVO}) "
        f"WITH CHECK (id = {EMPRESA_TENANT} AND {_NOMBRE_DE_LA_FICHA})",
    ]


def _logo_policy_using(con_logo_nulo: bool) -> str:
    """``USING`` de ``dueno_plat_empresa_logo``: 0029 exigía ``logo_id IS NULL``."""
    nulo = " AND logo_id IS NULL" if con_logo_nulo else ""
    return (
        f"ALTER POLICY dueno_plat_empresa_logo ON empresa "
        f"USING (tenant_id = {LOGO_TENANT}{nulo} AND {ACTOR_ACTIVO})"
    )


def _owner_grants(owner: str) -> list[str]:
    # Mínimos y por columna; nunca DELETE ni actualizada_por (A19).
    columnas = ", ".join(FICHA)
    return [
        f"GRANT SELECT ({columnas}) ON empresa TO {owner}",
        f"GRANT UPDATE ({columnas}) ON empresa TO {owner}",
        f"GRANT UPDATE (nombre) ON tenant TO {owner}",
    ]


def _owner_revokes(owner: str) -> list[str]:
    # Exactamente lo de _owner_grants (lo de 0018 y 0029 se conserva).
    columnas = ", ".join(FICHA)
    return [
        f"REVOKE SELECT ({columnas}) ON empresa FROM {owner}",  # noqa: S608 - constantes
        f"REVOKE UPDATE ({columnas}) ON empresa FROM {owner}",
        f"REVOKE UPDATE (nombre) ON tenant FROM {owner}",
    ]


def _audit_policy(app: str, acciones: Sequence[str]) -> str:
    """La política de inserción de la aplicación, con el mismo texto que la de 0018."""
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


def _drop_as_owner(owner: str, migrator: str, functions: Sequence[str]) -> list[str]:
    # Solo el dueño (plataforma_owner) puede borrar sus funciones: SET LOCAL ROLE.
    opening, closing = _transient_membership(owner, migrator)
    statements = [*opening, f"SET LOCAL ROLE {owner}"]
    statements += [f"DROP FUNCTION {fn}" for fn in functions]
    return [*statements, "RESET ROLE", *closing]


def _ownership(
    owner: str, migrator: str, app: str, supabase: Sequence[str], functions: Sequence[str]
) -> list[str]:
    # Orden C3/C5 (tras el CREATE): REVOKE de PUBLIC y de Supabase -> GRANT EXECUTE a la
    # aplicación -> CREATE transitorio y membresía transitoria -> OWNER -> fin de ambos.
    opening, closing = _transient_membership(owner, migrator)
    revoked = ", ".join(["PUBLIC", *supabase])
    statements = [f"REVOKE ALL ON FUNCTION {fn} FROM {revoked}" for fn in functions]
    statements += [f"GRANT EXECUTE ON FUNCTION {fn} TO {app}" for fn in functions]
    statements += [f"GRANT CREATE ON SCHEMA acceso TO {owner}", *opening]
    statements += [f"ALTER FUNCTION {fn} OWNER TO {owner}" for fn in functions]
    return [*statements, f"REVOKE CREATE ON SCHEMA acceso FROM {owner}", *closing]


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

    statements = [*_audit_check(ACCIONES)]
    statements += [
        "DROP POLICY plataforma_auditoria_insertar ON plataforma_auditoria",
        _audit_policy(app, ACCIONES_APP),
    ]
    statements += [*_owner_policies(owner), _logo_policy_using(False), *_owner_grants(owner)]
    statements += _drop_as_owner(owner, migrator, (REGISTRAR,))
    statements += [*CREATE_STATEMENTS]
    statements += _ownership(owner, migrator, app, supabase, FUNCTIONS)
    execute_statements(conn, statements)
    require_no_leftover_privileges(conn)


def downgrade() -> None:
    conn = op.get_bind()
    require_owner(conn)
    require_postgres_16(conn)
    app, owner, migrator, supabase = _context(conn)
    # No se borra auditoría: si ya hay filas con las acciones de C1, el CHECK de antes
    # rige solo para filas nuevas (NOT VALID).
    in_use = bool(conn.scalar(_NEW_ACTIONS_IN_USE, {"acciones": list(ACCIONES_C1)}))

    statements = _drop_as_owner(owner, migrator, FUNCTIONS)
    statements += [RESTORE_REGISTRAR_0029]
    statements += _ownership(owner, migrator, app, supabase, (REGISTRAR,))
    statements += [_logo_policy_using(True)]
    statements += [f"DROP POLICY {policy} ON {table}" for table, policy in POLICIES]
    statements += _owner_revokes(owner)
    statements += [
        "DROP POLICY plataforma_auditoria_insertar ON plataforma_auditoria",
        _audit_policy(app, ACCIONES_APP_0018),
    ]
    statements += _audit_check(ACCIONES_0017, not_valid=in_use)
    execute_statements(conn, statements)
    require_no_leftover_privileges(conn)
