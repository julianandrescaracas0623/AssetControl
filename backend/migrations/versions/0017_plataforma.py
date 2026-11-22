"""Consola de plataforma: tablas, columnas y funciones del operador (spec 017, T1).

``plan.md`` §2.3, §2.4, §3 y §5; ``spec.md`` R7–R10, R25 (columna), R33–R34. Mismo
patrón que 0003/0004/0016 de la spec 002 (§2.1), con un dueño propio:
``plataforma_owner`` (``NOLOGIN``, inerte, distinto de ``auth_owner``; P35/D12).

Tablas nuevas (excepciones cerradas a «toda tabla de negocio lleva ``tenant_id``», con
prueba propia en ``test_plataforma_catalogo.py``), con RLS habilitada y forzada:

- ``desarrollador``: ``email`` único y normalizado, ``nombre`` de 1 a 120, ``password_hash``
  y ``activo``. La aplicación solo lee ``(id, email, nombre, activo)`` de la fila de
  ``app.desarrollador_id`` (nunca ``password_hash``); nadie más que las funciones del
  dueño inserta o actualiza.
- ``plataforma_refresh_token``: como ``refresh_token`` de la 002, por desarrollador. La
  aplicación lee, inserta y marca ``usado_en``/``revocado_en`` solo de la fila de
  ``app.desarrollador_id``; sin ``DELETE``.
- ``plataforma_auditoria``: solo ``INSERT``/``SELECT``; ``accion`` con la lista cerrada
  completa de R33, ``resultado`` ``ok``/``rechazado``, ``desarrollador_id`` nulo cuando
  la acción la hizo el operador por CLI, sin correos, nombres, IP ni texto libre (R34).
  La aplicación inserta solo con su ``app.desarrollador_id`` (activo) y lee si ese
  desarrollador está activo.

Columnas nuevas: ``tenant.activo`` (``true`` por defecto), ``tenant.desactivado_en`` y
``tenant.desactivado_por`` (FK a ``desarrollador``), coherentes por ``CHECK``;
``usuario.debe_cambiar_password`` (``false`` por defecto: la migración no cambia a nadie,
R25). ``limite_tasa``: el ``CHECK`` de ``ambito`` suma ``plat_login_ip`` y
``plat_login_cuenta``.

Funciones (``plpgsql``, ``SECURITY DEFINER``, ``STRICT``, ``SET search_path = pg_catalog,
pg_temp``, todo calificado, SQL estático, dueña ``plataforma_owner``). Cada una vacía al
empezar y al terminar **todas** las GUC ``app.plat_*`` de esta migración, fija solo las
suyas con valores que ella valida o calcula y nunca lee una GUC:

- ``acceso.crear_desarrollador(p_email, p_nombre, p_password_hash)`` -> ``uuid`` (solo
  el migrador). Hash con el formato completo de argon2id o ``22023 hash_invalido``;
  correo repetido -> ``23505 desarrollador_existente``. Audita ``desarrollador_creado``.
- ``acceso.restablecer_desarrollador(p_email, p_password_hash)`` (solo el migrador):
  cambia el hash, revoca todas las familias de refresh del desarrollador y audita
  ``desarrollador_restablecido``. Correo inexistente -> ``P0002`` genérico.
- ``acceso.cambiar_estado_desarrollador(p_email, p_activo)`` (solo el migrador): fija
  ``activo``, revoca las familias al desactivar y audita ``desarrollador_desactivado`` o
  ``desarrollador_reactivado``. Correo inexistente -> ``P0002`` genérico.
- ``acceso.plataforma_buscar_login(p_email)`` -> ``id``, ``password_hash``, ``activo``
  (solo la aplicación; lo usa el login de plataforma de T2).

Las tres del operador auditan con ``desarrollador_id`` nulo (CU-11). La revocación se
repite hasta que no afecte filas (tope de 10 pasadas), como en 0016.

Políticas ``TO plataforma_owner`` (una por comando, nunca ``FOR ALL`` ni ``PUBLIC``; GUC
validadas por formato: vacía, nula o con otro formato -> ``NULL`` -> cero filas).
``GRANT`` por columna mínimos para ``plataforma_owner``, sin ``DELETE``.

Orden (C3/C5): tablas, políticas y ``GRANT`` -> ``CREATE FUNCTION`` -> ``REVOKE ALL`` de
``PUBLIC`` y de los roles de Supabase -> ``GRANT EXECUTE`` de ``plataforma_buscar_login``
a la aplicación -> ``CREATE`` transitorio en ``acceso`` y membresía transitoria ``WITH
INHERIT FALSE, SET TRUE`` -> ``OWNER TO plataforma_owner`` -> ``GRANT EXECUTE`` de las tres
del operador al migrador (como ``plataforma_owner``) -> ``REVOKE CREATE`` y fin de la
membresía, de inmediato; al terminar se comprueba que no quede nada (C8).

La migración falla con mensaje claro si ``plataforma_owner`` no existe o no es inerte, si
el rol de la aplicación es miembro de él, o si el servidor es anterior a PostgreSQL 16.

``downgrade``: borra las cuatro funciones como ``plataforma_owner`` (misma membresía
transitoria), las columnas nuevas, las tres tablas (con sus datos: solo para desarrollo y
CI) y restaura el ``CHECK`` de ``limite_tasa`` tras borrar los contadores de los dos
ámbitos nuevos.

Revision ID: 0017_plataforma
Revises: 0016_funciones_recuperacion
Create Date: 2026-11-19
"""

import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0017_plataforma"
down_revision: str | Sequence[str] | None = "0016_funciones_recuperacion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE_VAR = "APP_DB_USER"
AUTH_OWNER = "auth_owner"
PLATAFORMA_OWNER = "plataforma_owner"
SUPABASE_ROLES = ("anon", "authenticated", "service_role")
TABLES = ("desarrollador", "plataforma_refresh_token", "plataforma_auditoria")

CREAR = "acceso.crear_desarrollador(text, text, text)"
RESTABLECER = "acceso.restablecer_desarrollador(text, text)"
CAMBIAR_ESTADO = "acceso.cambiar_estado_desarrollador(text, boolean)"
BUSCAR_LOGIN = "acceso.plataforma_buscar_login(text)"
MIGRATOR_FUNCTIONS = (CREAR, RESTABLECER, CAMBIAR_ESTADO)
APP_FUNCTIONS = (BUSCAR_LOGIN,)
FUNCTIONS = (*MIGRATOR_FUNCTIONS, *APP_FUNCTIONS)

# Lista cerrada de acciones auditables (R33).
ACCIONES = (
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
)
ACCIONES_OPERADOR = (
    "desarrollador_creado",
    "desarrollador_restablecido",
    "desarrollador_desactivado",
    "desarrollador_reactivado",
)

SCOPE_CHECK = "limite_tasa_ambito_check"
OLD_SCOPES = (
    "login_ip",
    "login_cuenta",
    "refresh_ip",
    "validar_ip",
    "aceptar_ip",
    "recuperar_ip",
    "recuperar_cuenta",
    "restablecer_ip",
)
NEW_SCOPES = ("plat_login_ip", "plat_login_cuenta")

# Todas las GUC de las políticas de plataforma_owner: cada función las vacía.
OWNER_GUCS = (
    "app.plat_login_email",
    "app.plat_dev_crear",
    "app.plat_dev_restablecer",
    "app.plat_dev_estado",
    "app.plat_dev_objetivo",
)

# (tabla, política): lista cerrada (la fija test_plataforma_catalogo.py).
APP_POLICIES = (
    ("desarrollador", "desarrollador_propio"),
    ("plataforma_refresh_token", "plataforma_refresh_leer"),
    ("plataforma_refresh_token", "plataforma_refresh_crear"),
    ("plataforma_refresh_token", "plataforma_refresh_marcar"),
    ("plataforma_auditoria", "plataforma_auditoria_insertar"),
    ("plataforma_auditoria", "plataforma_auditoria_leer"),
)
OWNER_POLICIES = (
    ("desarrollador", "dueno_plat_desarrollador_login"),
    ("desarrollador", "dueno_plat_desarrollador_crear"),
    ("desarrollador", "dueno_plat_desarrollador_restablecer_leer"),
    ("desarrollador", "dueno_plat_desarrollador_restablecer"),
    ("desarrollador", "dueno_plat_desarrollador_estado_leer"),
    ("desarrollador", "dueno_plat_desarrollador_estado"),
    ("plataforma_refresh_token", "dueno_plat_refresh_leer"),
    ("plataforma_refresh_token", "dueno_plat_refresh_revocar"),
    ("plataforma_auditoria", "dueno_plat_auditoria_operador"),
)

DESARROLLADOR = "NULLIF(current_setting('app.desarrollador_id', true), '')::uuid"
_UUID = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def _setting(guc: str) -> str:
    return f"pg_catalog.current_setting('{guc}', true)"


def uuid_setting(guc: str) -> str:
    """UUID de ``guc``; ``NULL`` si falta o no es un UUID en minúsculas."""
    value = _setting(guc)
    return f"(CASE WHEN {value} ~ '{_UUID}' THEN ({value})::uuid END)"


def text_setting(guc: str) -> str:
    """Texto de ``guc``; ``NULL`` si falta o está vacío (la comparación es por igualdad)."""
    return f"NULLIF({_setting(guc)}, '')"


LOGIN_EMAIL = text_setting("app.plat_login_email")
DEV_CREAR = uuid_setting("app.plat_dev_crear")
DEV_RESTABLECER = text_setting("app.plat_dev_restablecer")
DEV_ESTADO = text_setting("app.plat_dev_estado")
DEV_OBJETIVO = uuid_setting("app.plat_dev_objetivo")

_CLEAR = (
    "PERFORM pg_catalog.set_config(g, '', true) "
    "FROM pg_catalog.unnest(ARRAY['" + "', '".join(OWNER_GUCS) + "']::text[]) AS g;"
)
# Formato completo del hash de argon2-cffi (como 0016): con otro formato la cuenta
# quedaría sin poder entrar. Sin barras invertidas (B1 de la 014).
_HASH_FORMAT = (
    "'^[$]argon2id[$]v=19[$]m=[0-9]+,t=[0-9]+,p=[0-9]+[$][A-Za-z0-9+/]+[$][A-Za-z0-9+/]+$'"
)
_HASH_MAX_LENGTH = 255
_REVOKE_MAX_PASSES = 10
_HEADER = "LANGUAGE plpgsql STRICT SECURITY DEFINER SET search_path = pg_catalog, pg_temp"
_HASH_INVALIDO = (
    f"IF p_password_hash !~ {_HASH_FORMAT} "
    f"OR pg_catalog.length(p_password_hash) > {_HASH_MAX_LENGTH} THEN\n"
    "        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'hash_invalido';\n"
    "    END IF;"
)
_NO_ENCONTRADO = "RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'desarrollador_no_encontrado';"
_REVOCAR = f"""FOR v_pasada IN 1..{_REVOKE_MAX_PASSES} LOOP
        UPDATE public.plataforma_refresh_token AS t SET revocado_en = pg_catalog.now()
            WHERE t.desarrollador_id = v_id AND t.revocado_en IS NULL;
        EXIT WHEN NOT FOUND;
    END LOOP;"""  # noqa: S608 - solo constantes del módulo

CREATE_CREAR = f"""
CREATE FUNCTION acceso.crear_desarrollador(p_email text, p_nombre text, p_password_hash text)
RETURNS uuid
{_HEADER}
AS $fn$
DECLARE
    v_id uuid;
    v_filas bigint;
BEGIN
    {_CLEAR}
    {_HASH_INVALIDO}
    v_id := pg_catalog.gen_random_uuid();
    PERFORM pg_catalog.set_config('app.plat_dev_crear', v_id::text, true);
    INSERT INTO public.desarrollador (id, email, nombre, password_hash)
        VALUES (v_id, p_email, p_nombre, p_password_hash)
        ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_filas = ROW_COUNT;
    IF v_filas <> 1 THEN
        RAISE EXCEPTION USING ERRCODE = '23505', MESSAGE = 'desarrollador_existente';
    END IF;
    PERFORM pg_catalog.set_config('app.plat_dev_objetivo', v_id::text, true);
    INSERT INTO public.plataforma_auditoria (accion, resultado, objeto_id)
        VALUES ('desarrollador_creado', 'ok', v_id);
    {_CLEAR}
    RETURN v_id;
END
$fn$
"""  # noqa: S608 - solo constantes del módulo

CREATE_RESTABLECER = f"""
CREATE FUNCTION acceso.restablecer_desarrollador(p_email text, p_password_hash text)
RETURNS void
{_HEADER}
AS $fn$
DECLARE
    v_id uuid;
BEGIN
    {_CLEAR}
    {_HASH_INVALIDO}
    PERFORM pg_catalog.set_config('app.plat_dev_restablecer', p_email, true);
    UPDATE public.desarrollador AS d SET password_hash = p_password_hash
        WHERE d.email = p_email
        RETURNING d.id INTO v_id;
    IF NOT FOUND THEN
        {_NO_ENCONTRADO}
    END IF;
    PERFORM pg_catalog.set_config('app.plat_dev_objetivo', v_id::text, true);
    {_REVOCAR}
    INSERT INTO public.plataforma_auditoria (accion, resultado, objeto_id)
        VALUES ('desarrollador_restablecido', 'ok', v_id);
    {_CLEAR}
    RETURN;
END
$fn$
"""  # noqa: S608 - solo constantes del módulo

CREATE_CAMBIAR_ESTADO = f"""
CREATE FUNCTION acceso.cambiar_estado_desarrollador(p_email text, p_activo boolean)
RETURNS void
{_HEADER}
AS $fn$
DECLARE
    v_id uuid;
BEGIN
    {_CLEAR}
    PERFORM pg_catalog.set_config('app.plat_dev_estado', p_email, true);
    UPDATE public.desarrollador AS d SET activo = p_activo
        WHERE d.email = p_email
        RETURNING d.id INTO v_id;
    IF NOT FOUND THEN
        {_NO_ENCONTRADO}
    END IF;
    PERFORM pg_catalog.set_config('app.plat_dev_objetivo', v_id::text, true);
    IF NOT p_activo THEN
        {_REVOCAR}
    END IF;
    INSERT INTO public.plataforma_auditoria (accion, resultado, objeto_id)
        VALUES (CASE WHEN p_activo THEN 'desarrollador_reactivado'
                     ELSE 'desarrollador_desactivado' END, 'ok', v_id);
    {_CLEAR}
    RETURN;
END
$fn$
"""  # noqa: S608 - solo constantes del módulo

CREATE_BUSCAR_LOGIN = f"""
CREATE FUNCTION acceso.plataforma_buscar_login(p_email text)
RETURNS TABLE (id uuid, password_hash text, activo boolean)
{_HEADER}
AS $fn$
BEGIN
    {_CLEAR}
    PERFORM pg_catalog.set_config('app.plat_login_email', p_email, true);
    RETURN QUERY SELECT d.id, d.password_hash, d.activo
        FROM public.desarrollador AS d WHERE d.email = p_email;
    {_CLEAR}
    RETURN;
END
$fn$
"""  # noqa: S608 - solo constantes del módulo

CREATE_STATEMENTS = (CREATE_CREAR, CREATE_RESTABLECER, CREATE_CAMBIAR_ESTADO, CREATE_BUSCAR_LOGIN)

_ROLE_EXISTS = text("select exists (select 1 from pg_roles where rolname = :name)")
_ROLE_SKIPS_RLS = text("select rolsuper or rolbypassrls from pg_roles where rolname = :name")
# Inseguro: se salta RLS, inicia sesión, crea roles o bases, replica o hereda de otro rol.
# Un rol inexistente cuenta como inseguro (falla cerrado), como en 0004.
_ROLE_UNSAFE = text(
    "select coalesce((select r.rolsuper or r.rolbypassrls or r.rolcanlogin or r.rolcreaterole "
    "or r.rolcreatedb or r.rolreplication "
    "or exists (select 1 from pg_auth_members m where m.member = r.oid) "
    "from pg_roles r where r.rolname = :name), true)"
)
_IS_MEMBER = text("select pg_has_role(:member, :owner, 'MEMBER')")
# Igual que 0004 (C8): por rolname exacto; la membresía ADMIN del creador en Supabase,
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
# CHECK de limite_tasa que solo mira la columna ambito (como 0015).
_SCOPE_CHECKS = text(
    "select c.conname from pg_constraint c "
    "join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any(c.conkey) "
    "where c.conrelid = 'public.limite_tasa'::regclass and c.contype = 'c' "
    "and a.attname = 'ambito' and array_length(c.conkey, 1) = 1"
)


def require_plataforma_owner(conn: Connection, name: str | None = None) -> None:
    """Falla con un mensaje claro si no existe ``plataforma_owner`` (plan.md §3)."""
    if not conn.scalar(_ROLE_EXISTS, {"name": name or PLATAFORMA_OWNER}):
        raise RuntimeError(
            f"Falta el rol {PLATAFORMA_OWNER}: créalo con docker/postgres/init/01-app-role.sh "
            "(o flask preparar-roles en un PostgreSQL administrado; spec 017) antes de migrar."
        )


def require_owner_attributes(conn: Connection, name: str | None = None) -> None:
    """Falla si el dueño no es un rol inerte; el mensaje no lleva el nombre del rol."""
    if conn.scalar(_ROLE_UNSAFE, {"name": name or PLATAFORMA_OWNER}):
        raise RuntimeError(
            "El rol dueño de las funciones de plataforma no es seguro: no puede ser "
            "SUPERUSER, tener BYPASSRLS, LOGIN, CREATEROLE, CREATEDB ni REPLICATION, "
            "ni tener membresía en otro rol. Corrígelo con docker/postgres/init/01-app-role.sh "
            "(spec 017) antes de migrar."
        )


def require_postgres_16(conn: Connection) -> None:
    """``WITH INHERIT FALSE, SET TRUE`` exige PostgreSQL 16 o superior."""
    if int(conn.scalar(text("show server_version_num"))) < 160000:
        raise RuntimeError(
            "La migración 0017 exige PostgreSQL 16 o superior (membresía transitoria "
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
            f"El rol de la aplicación indicado en {APP_ROLE_VAR} es miembro del rol dueño de "
            "las funciones de plataforma y podría actuar como él: quita esa membresía antes "
            "de migrar."
        )
    return name


def require_no_leftover_privileges(conn: Connection) -> None:
    """C5: al terminar, el dueño sin ``CREATE`` en ``acceso`` y el migrador no es miembro."""
    if conn.scalar(_OWNER_CAN_CREATE, {"owner": PLATAFORMA_OWNER}) or conn.scalar(
        _MIGRATOR_IS_MEMBER, {"owner": PLATAFORMA_OWNER}
    ):
        raise RuntimeError(
            "Tras la migración 0017, el rol dueño de las funciones de plataforma conserva "
            "CREATE en el esquema acceso o el rol migrador sigue siendo miembro de él (p. ej. "
            "una membresía previa de createrole_self_grant en Supabase, C8): quítala antes de "
            "migrar."
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
                f"La migración 0017 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def _transient_membership(owner: str, migrator: str) -> tuple[list[str], list[str]]:
    opening = [f"GRANT {owner} TO {migrator} WITH INHERIT FALSE, SET TRUE"]
    closing = [f"REVOKE {owner} FROM {migrator}"]
    return opening, closing


def _scope_check_name(conn: Connection) -> str:
    """Nombre del único ``CHECK`` de ``ambito`` de ``limite_tasa``, leído del catálogo."""
    names = list(conn.scalars(_SCOPE_CHECKS))
    if len(names) != 1:
        raise RuntimeError(
            "La migración 0017 esperaba exactamente un CHECK sobre limite_tasa.ambito "
            f"y encontró {len(names)}: revisa el esquema antes de migrar."
        )
    return names[0]


def _scope_check(scopes: Sequence[str]) -> str:
    values = ", ".join(f"'{scope}'" for scope in scopes)
    return f"ALTER TABLE limite_tasa ADD CONSTRAINT {SCOPE_CHECK} CHECK (ambito IN ({values}))"


def _tables() -> list[str]:
    acciones = ", ".join(f"'{accion}'" for accion in ACCIONES)
    return [
        """
        CREATE TABLE desarrollador (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            email text NOT NULL,
            nombre text NOT NULL,
            password_hash text NOT NULL,
            activo boolean NOT NULL DEFAULT true,
            creado_en timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT desarrollador_email_key UNIQUE (email),
            CONSTRAINT desarrollador_email_normalizado CHECK (email = lower(btrim(email))),
            CONSTRAINT desarrollador_nombre_longitud
                CHECK (char_length(nombre) BETWEEN 1 AND 120)
        )
        """,
        """
        CREATE TABLE plataforma_refresh_token (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            desarrollador_id uuid NOT NULL REFERENCES desarrollador (id),
            familia_id uuid NOT NULL,
            token_hash bytea NOT NULL,
            expira_en timestamptz NOT NULL,
            usado_en timestamptz NULL,
            revocado_en timestamptz NULL,
            creado_en timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT plataforma_refresh_token_token_hash_32
                CHECK (octet_length(token_hash) = 32),
            CONSTRAINT plataforma_refresh_token_token_hash_key UNIQUE (token_hash)
        )
        """,
        "CREATE INDEX plataforma_refresh_token_familia_idx "
        "ON plataforma_refresh_token (familia_id)",
        "CREATE INDEX plataforma_refresh_token_desarrollador_idx "
        "ON plataforma_refresh_token (desarrollador_id)",
        f"""
        CREATE TABLE plataforma_auditoria (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            desarrollador_id uuid NULL REFERENCES desarrollador (id),
            accion text NOT NULL,
            resultado text NOT NULL,
            tenant_id uuid NULL REFERENCES tenant (id),
            objeto_id uuid NULL,
            creado_en timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT plataforma_auditoria_accion_valida CHECK (accion IN ({acciones})),
            CONSTRAINT plataforma_auditoria_resultado_valido
                CHECK (resultado IN ('ok', 'rechazado'))
        )
        """,
        "CREATE INDEX plataforma_auditoria_creado_idx "
        "ON plataforma_auditoria (creado_en DESC, id DESC)",
        "CREATE INDEX plataforma_auditoria_tenant_idx "
        "ON plataforma_auditoria (tenant_id, creado_en DESC)",
        "CREATE INDEX plataforma_auditoria_accion_idx "
        "ON plataforma_auditoria (accion, creado_en DESC)",
        # --- Columnas nuevas de tablas existentes ---
        "ALTER TABLE tenant ADD COLUMN activo boolean NOT NULL DEFAULT true",
        "ALTER TABLE tenant ADD COLUMN desactivado_en timestamptz NULL",
        "ALTER TABLE tenant ADD COLUMN desactivado_por uuid NULL "
        "CONSTRAINT tenant_desactivado_por_fkey REFERENCES desarrollador (id)",
        "ALTER TABLE tenant ADD CONSTRAINT tenant_activo_coherente "
        "CHECK (activo = (desactivado_en IS NULL))",
        "ALTER TABLE tenant ADD CONSTRAINT tenant_desactivado_por_coherente "
        "CHECK (NOT activo OR desactivado_por IS NULL)",
        "ALTER TABLE usuario ADD COLUMN debe_cambiar_password boolean NOT NULL DEFAULT false",
    ]


def _app_policies(app: str) -> list[str]:
    activo = (
        "EXISTS (SELECT 1 FROM desarrollador d "  # noqa: S608
        f"WHERE d.id = {DESARROLLADOR} AND d.activo)"
    )
    return [
        f"CREATE POLICY desarrollador_propio ON desarrollador FOR SELECT TO {app} "
        f"USING (id = {DESARROLLADOR})",
        f"CREATE POLICY plataforma_refresh_leer ON plataforma_refresh_token FOR SELECT TO {app} "
        f"USING (desarrollador_id = {DESARROLLADOR})",
        f"CREATE POLICY plataforma_refresh_crear ON plataforma_refresh_token FOR INSERT TO {app} "
        f"WITH CHECK (desarrollador_id = {DESARROLLADOR})",
        f"CREATE POLICY plataforma_refresh_marcar ON plataforma_refresh_token FOR UPDATE "
        f"TO {app} USING (desarrollador_id = {DESARROLLADOR}) "
        f"WITH CHECK (desarrollador_id = {DESARROLLADOR})",
        f"CREATE POLICY plataforma_auditoria_insertar ON plataforma_auditoria FOR INSERT "
        f"TO {app} WITH CHECK (desarrollador_id = {DESARROLLADOR} AND {activo})",
        f"CREATE POLICY plataforma_auditoria_leer ON plataforma_auditoria FOR SELECT "
        f"TO {app} USING ({activo})",
    ]


def _owner_policies(owner: str) -> list[str]:
    operador = ", ".join(f"'{accion}'" for accion in ACCIONES_OPERADOR)
    return [
        # --- desarrollador ---
        f"CREATE POLICY dueno_plat_desarrollador_login ON desarrollador FOR SELECT "
        f"TO {owner} USING (email = {LOGIN_EMAIL})",
        f"CREATE POLICY dueno_plat_desarrollador_crear ON desarrollador FOR INSERT "
        f"TO {owner} WITH CHECK (id = {DEV_CREAR} AND activo)",
        f"CREATE POLICY dueno_plat_desarrollador_restablecer_leer ON desarrollador "
        f"FOR SELECT TO {owner} USING (email = {DEV_RESTABLECER})",
        f"CREATE POLICY dueno_plat_desarrollador_restablecer ON desarrollador FOR UPDATE "
        f"TO {owner} USING (email = {DEV_RESTABLECER}) WITH CHECK (email = {DEV_RESTABLECER})",
        f"CREATE POLICY dueno_plat_desarrollador_estado_leer ON desarrollador "
        f"FOR SELECT TO {owner} USING (email = {DEV_ESTADO})",
        f"CREATE POLICY dueno_plat_desarrollador_estado ON desarrollador FOR UPDATE "
        f"TO {owner} USING (email = {DEV_ESTADO}) WITH CHECK (email = {DEV_ESTADO})",
        # --- plataforma_refresh_token: solo las familias del desarrollador objetivo ---
        f"CREATE POLICY dueno_plat_refresh_leer ON plataforma_refresh_token FOR SELECT "
        f"TO {owner} USING (desarrollador_id = {DEV_OBJETIVO})",
        f"CREATE POLICY dueno_plat_refresh_revocar ON plataforma_refresh_token FOR UPDATE "
        f"TO {owner} USING (desarrollador_id = {DEV_OBJETIVO} AND revocado_en IS NULL) "
        f"WITH CHECK (desarrollador_id = {DEV_OBJETIVO} AND revocado_en = now())",
        # --- plataforma_auditoria: solo acciones del operador, sin desarrollador ni tenant ---
        f"CREATE POLICY dueno_plat_auditoria_operador ON plataforma_auditoria FOR INSERT "
        f"TO {owner} WITH CHECK (desarrollador_id IS NULL AND tenant_id IS NULL "
        f"AND resultado = 'ok' AND accion IN ({operador}) AND objeto_id = {DEV_OBJETIVO})",
    ]


def _grants(app: str, owner: str, revoked: Sequence[str]) -> list[str]:
    statements = [f"REVOKE ALL ON {table} FROM {', '.join(revoked)}" for table in TABLES]
    statements += [
        # Aplicación: nunca password_hash; sin DELETE.
        f"GRANT SELECT (id, email, nombre, activo) ON desarrollador TO {app}",
        f"GRANT SELECT, INSERT ON plataforma_refresh_token TO {app}",
        f"GRANT UPDATE (usado_en, revocado_en) ON plataforma_refresh_token TO {app}",
        f"GRANT SELECT ON plataforma_auditoria TO {app}",
        f"GRANT INSERT (desarrollador_id, accion, resultado, tenant_id, objeto_id) "
        f"ON plataforma_auditoria TO {app}",
        # plataforma_owner: mínimos y por columna; nunca DELETE ni TRUNCATE.
        f"GRANT SELECT (id, email, password_hash, activo) ON desarrollador TO {owner}",
        f"GRANT INSERT (id, email, nombre, password_hash) ON desarrollador TO {owner}",
        f"GRANT UPDATE (password_hash, activo) ON desarrollador TO {owner}",
        f"GRANT SELECT (desarrollador_id, revocado_en) ON plataforma_refresh_token TO {owner}",
        f"GRANT UPDATE (revocado_en) ON plataforma_refresh_token TO {owner}",
        f"GRANT INSERT (accion, resultado, objeto_id) ON plataforma_auditoria TO {owner}",
    ]
    return statements


def upgrade() -> None:
    conn = op.get_bind()
    require_plataforma_owner(conn)
    require_owner_attributes(conn)
    require_postgres_16(conn)
    quote = conn.dialect.identifier_preparer.quote
    app = quote(_app_role(conn))
    owner = quote(PLATAFORMA_OWNER)
    migrator = quote(conn.scalar(text("select current_user")))
    current_check = quote(_scope_check_name(conn))
    supabase = [quote(role) for role in SUPABASE_ROLES if conn.scalar(_ROLE_EXISTS, {"name": role})]
    opening, closing = _transient_membership(owner, migrator)

    statements = [*_tables()]
    for table in TABLES:
        statements += [
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        ]
    statements += [*_app_policies(app), *_owner_policies(owner)]
    statements += _grants(app, owner, ["PUBLIC", app, *supabase])
    statements += [
        f"ALTER TABLE limite_tasa DROP CONSTRAINT {current_check}",
        _scope_check((*OLD_SCOPES, *NEW_SCOPES)),
    ]
    statements += [*CREATE_STATEMENTS]
    revoked = ", ".join(["PUBLIC", *supabase])
    statements += [f"REVOKE ALL ON FUNCTION {fn} FROM {revoked}" for fn in FUNCTIONS]
    statements += [f"GRANT EXECUTE ON FUNCTION {fn} TO {app}" for fn in APP_FUNCTIONS]
    # USAGE permanente, como auth_owner en 0002: el dueño resuelve sus funciones por
    # nombre (GRANT y DROP); sin CREATE, que solo se da y se quita aquí.
    statements += [f"GRANT USAGE ON SCHEMA acceso TO {owner}"]
    statements += [f"GRANT CREATE ON SCHEMA acceso TO {owner}", *opening]
    statements += [f"ALTER FUNCTION {fn} OWNER TO {owner}" for fn in FUNCTIONS]
    # Como plataforma_owner (ya dueña): el EXECUTE del migrador no se traspasa al cambiar
    # de dueño (mismo motivo que crear_tenant en 0004).
    statements.append(f"SET LOCAL ROLE {owner}")
    statements += [f"GRANT EXECUTE ON FUNCTION {fn} TO {migrator}" for fn in MIGRATOR_FUNCTIONS]
    statements += ["RESET ROLE", f"REVOKE CREATE ON SCHEMA acceso FROM {owner}", *closing]
    execute_statements(conn, statements)
    require_no_leftover_privileges(conn)


def require_nothing_to_lose(conn: Connection) -> None:
    """Aborta el downgrade si borraría auditoría o el estado de una empresa desactivada.

    Bajo ``FORCE ROW LEVEL SECURITY`` el migrador (dueño) no ve filas sin política: se
    quita ``FORCE`` solo para contar, dentro de la transacción, y se restablece antes de
    decidir. Si el migrador no es el dueño, el ``ALTER`` falla y el downgrade no sigue.
    """
    guarded = ("plataforma_auditoria", "tenant")
    execute_statements(conn, [f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY" for t in guarded])
    audit = conn.scalar(text("select exists (select 1 from plataforma_auditoria)"))
    inactive = conn.scalar(text("select exists (select 1 from tenant where not activo)"))
    execute_statements(conn, [f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY" for t in guarded])
    reasons = []
    if audit:
        reasons.append("plataforma_auditoria tiene registros")
    if inactive:
        reasons.append("hay al menos una empresa inactiva (tenant.activo = false)")
    if reasons:
        raise RuntimeError(
            "La migración 0017 no puede revertirse: " + " y ".join(reasons) + ". El downgrade "
            "borraría la auditoría de plataforma o el estado de desactivación de las empresas; "
            "no se tocó nada. Solo se revierte sobre una base sin esos datos."
        )


def downgrade() -> None:
    conn = op.get_bind()
    require_plataforma_owner(conn)
    require_postgres_16(conn)
    require_nothing_to_lose(conn)
    quote = conn.dialect.identifier_preparer.quote
    owner = quote(PLATAFORMA_OWNER)
    migrator = quote(conn.scalar(text("select current_user")))
    current_check = quote(_scope_check_name(conn))
    opening, closing = _transient_membership(owner, migrator)
    new_scopes = ", ".join(f"'{scope}'" for scope in NEW_SCOPES)
    # Solo el dueño (plataforma_owner) puede borrar sus funciones: SET LOCAL ROLE.
    statements = [*opening, f"SET LOCAL ROLE {owner}"]
    statements += [f"DROP FUNCTION {fn}" for fn in FUNCTIONS]
    statements += ["RESET ROLE", *closing, f"REVOKE USAGE ON SCHEMA acceso FROM {owner}"]
    statements += [
        "ALTER TABLE usuario DROP COLUMN debe_cambiar_password",
        "ALTER TABLE tenant DROP CONSTRAINT tenant_desactivado_por_coherente",
        "ALTER TABLE tenant DROP CONSTRAINT tenant_activo_coherente",
        "ALTER TABLE tenant DROP COLUMN desactivado_por",
        "ALTER TABLE tenant DROP COLUMN desactivado_en",
        "ALTER TABLE tenant DROP COLUMN activo",
        # DROP TABLE elimina también sus políticas, índices y GRANT.
        *(f"DROP TABLE {table}" for table in reversed(TABLES)),
        # Solo contadores de los ámbitos nuevos: el CHECK anterior no los admite.
        f"DELETE FROM limite_tasa WHERE ambito IN ({new_scopes})",  # noqa: S608
        f"ALTER TABLE limite_tasa DROP CONSTRAINT {current_check}",
    ]
    execute_statements(conn, statements)
    failure = None
    try:
        conn.exec_driver_sql(_scope_check(OLD_SCOPES), execution_options={"no_parameters": True})
    except SQLAlchemyError as exc:
        sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None) or "desconocido"
        failure = (
            "La migración 0017 no puede revertirse: quedan en limite_tasa contadores de "
            "plat_login_ip o plat_login_cuenta que el migrador no pudo borrar (sin "
            "superusuario, la RLS de la purga solo alcanza ventanas de más de un día). "
            f"Espera un día y ejecuta flask purgar-limite-tasa ({type(exc).__name__}, "
            f"SQLSTATE {sqlstate})."
        )
    if failure is not None:
        raise RuntimeError(failure) from None
    require_no_leftover_privileges(conn)
