"""Funciones ``acceso.*`` de recuperación de contraseña y políticas del dueño (spec 014, T2).

``plan.md`` §4; ``docs/03`` (``recuperacion_contrasena``); ``spec.md`` R2–R4, R9, R13,
R15; requisitos 1–11 del security-reviewer (``tasks.md``, «Notas de cierre T1»). Mismo
patrón que 0003/0004 de la spec 002 (§2.1).

Funciones (``plpgsql``, ``SECURITY DEFINER``, ``STRICT``, ``SET search_path =
pg_catalog, pg_temp``, todo calificado, SQL estático, dueña ``auth_owner``, ``EXECUTE``
solo para el rol de la aplicación). Cada una vacía al empezar y al terminar **todas**
las GUC ``app.auth_*`` (las seis de 0004 y las cinco de aquí), fija solo las suyas con
valores que ella misma valida o calcula y nunca lee una GUC:

- ``acceso.solicitar_recuperacion(p_email, p_clave)`` -> ``boolean``. GUC
  ``app.auth_rec_email``, ``app.auth_rec_usuario`` y ``app.auth_rec_clave``. Clave que
  no sea hex minúsculo de 64 -> excepción estática ``clave_invalida`` (no depende del
  correo). Toma un candado consultivo de transacción por correo (M2: dos solicitudes
  simultáneas del mismo usuario se serializan, sin ``23505``) y ejecuta **siempre** las
  mismas sentencias (R13): busca el usuario activo, cuenta sus membresías activas,
  invalida el pendiente anterior (sin filtrar por expiración, M1) e inserta el enlace
  (``expira_en = now() + 30 min``) con ``WHERE v_elegible``: 0 o 1 fila. Devuelve
  ``true`` solo si insertó; ``ON CONFLICT DO NOTHING`` como defensa adicional.
- ``acceso.restablecer_contrasena(p_clave, p_password_hash)`` -> ``uuid``. GUC
  ``app.auth_reset_clave`` y ``app.auth_reset_usuario``. Clave mal formada o hash sin el
  formato completo de argon2-cffi (``$argon2id$v=19$m=..,t=..,p=..$<sal>$<hash>``, base64
  sin relleno, 255 caracteres como máximo; vacío, ``argon2i``, ``bcrypt`` o recortado
  dejarían la cuenta sin poder entrar; regex sin barras invertidas, B1), comprobados
  juntos antes de tocar ninguna tabla y sin depender del usuario (R13), enlace
  vencido (reloj de la base), usado, invalidado o inexistente, usuario inactivo o sin
  exactamente una membresía activa (la del tenant del enlace) -> la misma excepción
  estática ``enlace_invalido`` (``P0001``, sin eco), que revierte también el consumo.
  Si todo cuadra: consume el enlace, guarda el hash Argon2id recibido (la función no
  hashea ni lee ``password_hash``), revoca los refresh vivos de **todas** las membresías
  del usuario (de cualquier tenant, solo de ese usuario) e invalida sus otros enlaces
  pendientes. Devuelve el ``usuario_id``. La revocación se repite hasta que no afecte
  filas (tope de 10 pasadas, H1): en READ COMMITTED cada sentencia de la función toma su
  propia instantánea, y una rotación de refresh en vuelo cuyo sucesor se confirma
  mientras se espera el candado del token viejo queda revocada en la pasada siguiente
  (mismo patrón que ``_revoke_family`` de la spec 002).

Políticas ``TO auth_owner`` (una por comando, nunca ``FOR ALL`` ni ``PUBLIC``; GUC
validadas por formato como en 0003: vacía, nula o con otro formato -> ``NULL`` -> cero
filas). El ``INSERT`` exige 30 minutos como máximo, sin marcas, la clave de la GUC y
exactamente una membresía activa, la del tenant del enlace. El cambio de contraseña y la
revocación de refresh exigen además un enlace del usuario **consumido en esta misma
transacción** con la clave de la GUC (``usada_en = now()``): fijar
``app.auth_reset_usuario`` no basta.

``GRANT`` por columna mínimos para ``auth_owner``, sin ``DELETE`` ni ``TRUNCATE``:
``UPDATE (password_hash)`` en ``usuario`` (ningún ``SELECT`` nuevo). ``auth_owner`` ya
tenía ``SELECT (password_hash)`` en ``usuario`` desde 0003 (lo usa ``buscar_login``), así
que el privilegio del rol no impide leerlo: la garantía de que estas funciones no leen ni
devuelven ``password_hash`` (requisito 9) es su cuerpo estático, fijado por la huella
``sha256`` del catálogo C6 (``test_catalog_rls.py``). ``SELECT (membresia_id,
revocado_en)`` y ``UPDATE (revocado_en)`` en
``refresh_token``; en ``recuperacion_contrasena`` ``INSERT (tenant_id, usuario_id,
token_hash, expira_en)``, ``UPDATE (usada_en, invalidada_en)`` y ``SELECT`` de lo que
leen el ``WHERE`` y el ``RETURNING``. La aplicación sigue sin ningún privilegio sobre la
tabla.

Orden (C3/C5, como 0004): políticas y ``GRANT`` -> ``CREATE FUNCTION`` -> ``REVOKE
ALL`` de ``PUBLIC`` y de los roles de Supabase -> ``GRANT EXECUTE`` a la aplicación ->
``CREATE`` transitorio en ``acceso`` y membresía transitoria ``WITH INHERIT FALSE, SET
TRUE`` -> ``OWNER TO auth_owner`` -> ``REVOKE CREATE`` y fin de la membresía, de
inmediato; al terminar se comprueba que no quede nada (C8).

``downgrade``: borra las dos funciones como ``auth_owner`` (misma membresía
transitoria), las 13 políticas y los ``GRANT`` de esta migración; no toca datos.

Revision ID: 0016_funciones_recuperacion
Revises: 0015_recuperacion_contrasena
Create Date: 2026-11-19
"""

import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0016_funciones_recuperacion"
down_revision: str | Sequence[str] | None = "0015_recuperacion_contrasena"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE_VAR = "APP_DB_USER"
AUTH_OWNER = "auth_owner"
SUPABASE_ROLES = ("anon", "authenticated", "service_role")
TABLE = "recuperacion_contrasena"

SOLICITAR = "acceso.solicitar_recuperacion(text, text)"
RESTABLECER = "acceso.restablecer_contrasena(text, text)"
FUNCTIONS = (SOLICITAR, RESTABLECER)

# Todas las GUC de las políticas del dueño (0003 y esta): cada función las vacía.
OWNER_GUCS = (
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
)

# (tabla, política): lista cerrada (la fija el catálogo C6 en test_catalog_rls.py).
POLICIES = (
    ("usuario", "dueno_usuario_recuperar"),
    ("usuario", "dueno_usuario_restablecer"),
    ("usuario", "dueno_usuario_cambiar_clave"),
    ("membresia", "dueno_membresia_recuperar"),
    ("membresia", "dueno_membresia_restablecer"),
    (TABLE, "dueno_recuperacion_solicitar"),
    (TABLE, "dueno_recuperacion_crear"),
    (TABLE, "dueno_recuperacion_invalidar"),
    (TABLE, "dueno_recuperacion_restablecer"),
    (TABLE, "dueno_recuperacion_consumir"),
    (TABLE, "dueno_recuperacion_invalidar_otros"),
    ("refresh_token", "dueno_refresh_restablecer"),
    ("refresh_token", "dueno_refresh_revocar"),
)

_HEX_KEY = "^[0-9a-f]{64}$"
_UUID = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def _setting(guc: str) -> str:
    return f"pg_catalog.current_setting('{guc}', true)"


def key_hash(guc: str) -> str:
    """``sha256`` de la clave hex de ``guc``; ``NULL`` si falta o no tiene el formato."""
    value = _setting(guc)
    return (
        f"(CASE WHEN {value} ~ '{_HEX_KEY}' "
        f"THEN pg_catalog.sha256(pg_catalog.decode({value}, 'hex')) END)"
    )


def uuid_setting(guc: str) -> str:
    """UUID de ``guc``; ``NULL`` si falta o no es un UUID en minúsculas."""
    value = _setting(guc)
    return f"(CASE WHEN {value} ~ '{_UUID}' THEN ({value})::uuid END)"


def text_setting(guc: str) -> str:
    """Texto de ``guc``; ``NULL`` si falta o está vacío (la comparación es por igualdad)."""
    return f"NULLIF({_setting(guc)}, '')"


REC_EMAIL = text_setting("app.auth_rec_email")
REC_USUARIO = uuid_setting("app.auth_rec_usuario")
REC_CLAVE = key_hash("app.auth_rec_clave")
RESET_CLAVE = key_hash("app.auth_reset_clave")
RESET_USUARIO = uuid_setting("app.auth_reset_usuario")
PENDIENTE = "usada_en IS NULL AND invalidada_en IS NULL"


def consumido(usuario: str) -> str:
    """Un enlace de ``usuario`` consumido en esta transacción con la clave de la GUC."""
    return (
        f"EXISTS (SELECT 1 FROM {TABLE} r WHERE r.usuario_id = {usuario} "  # noqa: S608
        f"AND r.token_hash = {RESET_CLAVE} AND r.usada_en = now())"
    )


_CLEAR = (
    "PERFORM pg_catalog.set_config(g, '', true) "
    "FROM pg_catalog.unnest(ARRAY['" + "', '".join(OWNER_GUCS) + "']::text[]) AS g;"
)
_KEY_FORMAT = "'^[0-9a-f]{64}$'"
# Formato completo del hash que genera la aplicación (argon2-cffi, argon2.Type.ID,
# versión 19, sal y hash en base64 sin relleno): con otro formato (vacío, argon2i,
# bcrypt, recortado...) la cuenta quedaría sin poder entrar (I1 de T2). Clases de
# carácter sin barra invertida (B1): no depende de standard_conforming_strings, una GUC
# de sesión que el rol de la aplicación puede cambiar.
_HASH_FORMAT = (
    "'^[$]argon2id[$]v=19[$]m=[0-9]+,t=[0-9]+,p=[0-9]+[$][A-Za-z0-9+/]+[$][A-Za-z0-9+/]+$'"
)
_HASH_MAX_LENGTH = 255
# H1 de la auditoría de T2: tope de pasadas de la revocación (como _revoke_family, 002).
_REVOKE_MAX_PASSES = 10
_HEADER = "LANGUAGE plpgsql STRICT SECURITY DEFINER SET search_path = pg_catalog, pg_temp"
_ENLACE_INVALIDO = "RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'enlace_invalido';"

CREATE_SOLICITAR = f"""
CREATE FUNCTION acceso.solicitar_recuperacion(p_email text, p_clave text)
RETURNS boolean
{_HEADER}
AS $fn$
DECLARE
    v_usuario uuid;
    v_tenant uuid;
    v_activas integer;
    v_elegible boolean;
    v_filas bigint;
BEGIN
    {_CLEAR}
    IF p_clave !~ {_KEY_FORMAT} THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'clave_invalida';
    END IF;
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('recuperacion_contrasena:' || p_email, 0));
    PERFORM pg_catalog.set_config('app.auth_rec_email', p_email, true);
    SELECT u.id INTO v_usuario FROM public.usuario AS u WHERE u.email = p_email AND u.activo;
    PERFORM pg_catalog.set_config('app.auth_rec_usuario', COALESCE(v_usuario::text, ''), true);
    SELECT pg_catalog.count(*)::integer, (pg_catalog.array_agg(m.tenant_id))[1]
        INTO v_activas, v_tenant
        FROM public.membresia AS m WHERE m.usuario_id = v_usuario AND m.activa;
    v_elegible := v_usuario IS NOT NULL AND v_activas = 1;
    PERFORM pg_catalog.set_config('app.auth_rec_clave', p_clave, true);
    UPDATE public.recuperacion_contrasena AS r SET invalidada_en = pg_catalog.now()
        WHERE v_elegible AND r.usuario_id = v_usuario
          AND r.usada_en IS NULL AND r.invalidada_en IS NULL;
    INSERT INTO public.recuperacion_contrasena (tenant_id, usuario_id, token_hash, expira_en)
        SELECT v_tenant, v_usuario, pg_catalog.sha256(pg_catalog.decode(p_clave, 'hex')),
               pg_catalog.now() + pg_catalog.make_interval(mins => 30)
        WHERE v_elegible
        ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_filas = ROW_COUNT;
    {_CLEAR}
    RETURN v_filas = 1;
END
$fn$
"""  # noqa: S608 - solo constantes del módulo

CREATE_RESTABLECER = f"""
CREATE FUNCTION acceso.restablecer_contrasena(p_clave text, p_password_hash text)
RETURNS uuid
{_HEADER}
AS $fn$
DECLARE
    v_usuario uuid;
    v_tenant uuid;
    v_activo boolean;
    v_activas integer;
    v_tenant_activo uuid;
    v_filas bigint;
BEGIN
    {_CLEAR}
    IF p_clave !~ {_KEY_FORMAT} OR p_password_hash !~ {_HASH_FORMAT}
       OR pg_catalog.length(p_password_hash) > {_HASH_MAX_LENGTH} THEN
        {_ENLACE_INVALIDO}
    END IF;
    PERFORM pg_catalog.set_config('app.auth_reset_clave', p_clave, true);
    UPDATE public.recuperacion_contrasena AS r SET usada_en = pg_catalog.now()
        WHERE r.token_hash = pg_catalog.sha256(pg_catalog.decode(p_clave, 'hex'))
          AND r.usada_en IS NULL AND r.invalidada_en IS NULL
          AND r.expira_en > pg_catalog.now()
        RETURNING r.usuario_id, r.tenant_id INTO v_usuario, v_tenant;
    IF NOT FOUND THEN
        {_ENLACE_INVALIDO}
    END IF;
    PERFORM pg_catalog.set_config('app.auth_reset_usuario', v_usuario::text, true);
    SELECT u.activo INTO v_activo FROM public.usuario AS u WHERE u.id = v_usuario;
    SELECT pg_catalog.count(*)::integer, (pg_catalog.array_agg(m.tenant_id))[1]
        INTO v_activas, v_tenant_activo
        FROM public.membresia AS m WHERE m.usuario_id = v_usuario AND m.activa;
    IF v_activo IS NOT TRUE OR v_activas <> 1 OR v_tenant_activo IS DISTINCT FROM v_tenant THEN
        {_ENLACE_INVALIDO}
    END IF;
    UPDATE public.usuario AS u SET password_hash = p_password_hash WHERE u.id = v_usuario;
    GET DIAGNOSTICS v_filas = ROW_COUNT;
    IF v_filas <> 1 THEN
        {_ENLACE_INVALIDO}
    END IF;
    FOR v_pasada IN 1..{_REVOKE_MAX_PASSES} LOOP
        UPDATE public.refresh_token AS t SET revocado_en = pg_catalog.now()
            WHERE t.revocado_en IS NULL AND t.membresia_id IN (
                SELECT m.id FROM public.membresia AS m WHERE m.usuario_id = v_usuario);
        EXIT WHEN NOT FOUND;
    END LOOP;
    UPDATE public.recuperacion_contrasena AS r SET invalidada_en = pg_catalog.now()
        WHERE r.usuario_id = v_usuario AND r.usada_en IS NULL AND r.invalidada_en IS NULL;
    {_CLEAR}
    RETURN v_usuario;
END
$fn$
"""  # noqa: S608 - solo constantes del módulo

CREATE_STATEMENTS = (CREATE_SOLICITAR, CREATE_RESTABLECER)

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
_APP_IS_OWNER_MEMBER = text("select pg_has_role(:app, :owner, 'MEMBER')")
# Igual que 0004 (C8, H1 de T3): por rolname exacto; la membresía ADMIN del creador en
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


def require_auth_owner(conn: Connection, name: str | None = None) -> None:
    """Falla con un mensaje claro si no existe ``auth_owner`` (P0 de 002)."""
    if not conn.scalar(_ROLE_EXISTS, {"name": name or AUTH_OWNER}):
        raise RuntimeError(
            f"Falta el rol {AUTH_OWNER}: créalo con docker/postgres/init/01-app-role.sh "
            "(spec 002, P0) antes de migrar."
        )


def require_owner_attributes(conn: Connection, name: str | None = None) -> None:
    """Falla si el dueño no es un rol inerte; el mensaje no lleva el nombre del rol."""
    if conn.scalar(_ROLE_UNSAFE, {"name": name or AUTH_OWNER}):
        raise RuntimeError(
            "El rol dueño de las funciones de acceso no es seguro: no puede ser "
            "SUPERUSER, tener BYPASSRLS, LOGIN, CREATEROLE, CREATEDB ni REPLICATION, "
            "ni tener membresía en otro rol. Corrígelo con docker/postgres/init/01-app-role.sh "
            "(spec 002, P0) antes de migrar."
        )


def require_postgres_16(conn: Connection) -> None:
    """``WITH INHERIT FALSE, SET TRUE`` exige PostgreSQL 16 o superior."""
    if int(conn.scalar(text("show server_version_num"))) < 160000:
        raise RuntimeError(
            "La migración 0016 exige PostgreSQL 16 o superior (membresía transitoria "
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
            "Tras la migración 0016, el rol dueño de las funciones de acceso conserva CREATE "
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
                f"La migración 0016 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def _transient_membership(owner: str, migrator: str) -> tuple[list[str], list[str]]:
    opening = [f"GRANT {owner} TO {migrator} WITH INHERIT FALSE, SET TRUE"]
    closing = [f"REVOKE {owner} FROM {migrator}"]
    return opening, closing


def _policies(owner: str) -> list[str]:
    return [
        # --- usuario ---
        f"CREATE POLICY dueno_usuario_recuperar ON usuario FOR SELECT TO {owner} "
        f"USING (email = {REC_EMAIL} AND activo)",
        f"CREATE POLICY dueno_usuario_restablecer ON usuario FOR SELECT TO {owner} "
        f"USING (id = {RESET_USUARIO})",
        f"CREATE POLICY dueno_usuario_cambiar_clave ON usuario FOR UPDATE TO {owner} "
        f"USING (id = {RESET_USUARIO} AND activo AND {consumido('usuario.id')}) "
        f"WITH CHECK (id = {RESET_USUARIO} AND activo)",
        # --- membresia ---
        f"CREATE POLICY dueno_membresia_recuperar ON membresia FOR SELECT TO {owner} "
        f"USING (usuario_id = {REC_USUARIO})",
        f"CREATE POLICY dueno_membresia_restablecer ON membresia FOR SELECT TO {owner} "
        f"USING (usuario_id = {RESET_USUARIO})",
        # --- recuperacion_contrasena: solicitar ---
        f"CREATE POLICY dueno_recuperacion_solicitar ON {TABLE} FOR SELECT TO {owner} "
        f"USING (usuario_id = {REC_USUARIO})",
        # Exactamente una membresía activa: la del tenant del enlace (R2, requisito 5).
        f"CREATE POLICY dueno_recuperacion_crear ON {TABLE} FOR INSERT TO {owner} "  # noqa: S608
        f"WITH CHECK (usuario_id = {REC_USUARIO} AND token_hash = {REC_CLAVE} "
        f"AND {PENDIENTE} AND expira_en > now() "
        "AND expira_en <= now() + interval '30 minutes' "
        "AND EXISTS (SELECT 1 FROM membresia m "
        f"WHERE m.tenant_id = {TABLE}.tenant_id AND m.usuario_id = {TABLE}.usuario_id "
        "AND m.activa) "
        "AND NOT EXISTS (SELECT 1 FROM membresia m "
        f"WHERE m.usuario_id = {TABLE}.usuario_id AND m.tenant_id <> {TABLE}.tenant_id "
        "AND m.activa))",
        # M1: sin filtro de expiración, para que un vencido sin usar no bloquee otro.
        f"CREATE POLICY dueno_recuperacion_invalidar ON {TABLE} FOR UPDATE TO {owner} "
        f"USING (usuario_id = {REC_USUARIO} AND {PENDIENTE}) "
        "WITH CHECK (invalidada_en = now() AND usada_en IS NULL)",
        # --- recuperacion_contrasena: restablecer ---
        # B3 de la auditoría (deuda): la rama por usuario no puede limitarse a pendientes,
        # porque la fila nueva del UPDATE de invalidar_otros (su WHERE lee columnas) debe
        # pasar también esta política SELECT y ya no es pendiente (42501).
        f"CREATE POLICY dueno_recuperacion_restablecer ON {TABLE} FOR SELECT TO {owner} "
        f"USING (token_hash = {RESET_CLAVE} OR usuario_id = {RESET_USUARIO})",
        f"CREATE POLICY dueno_recuperacion_consumir ON {TABLE} FOR UPDATE TO {owner} "
        f"USING (token_hash = {RESET_CLAVE} AND {PENDIENTE} AND expira_en > now()) "
        "WITH CHECK (usada_en = now() AND invalidada_en IS NULL)",
        f"CREATE POLICY dueno_recuperacion_invalidar_otros ON {TABLE} FOR UPDATE TO {owner} "
        f"USING (usuario_id = {RESET_USUARIO} AND {PENDIENTE}) "
        "WITH CHECK (invalidada_en = now() AND usada_en IS NULL)",
        # --- refresh_token: solo las membresías del usuario que restablece ---
        f"CREATE POLICY dueno_refresh_restablecer ON refresh_token FOR SELECT TO {owner} "  # noqa: S608
        "USING (EXISTS (SELECT 1 FROM membresia m WHERE m.id = refresh_token.membresia_id "
        f"AND m.tenant_id = refresh_token.tenant_id AND m.usuario_id = {RESET_USUARIO}))",
        f"CREATE POLICY dueno_refresh_revocar ON refresh_token FOR UPDATE TO {owner} "  # noqa: S608
        "USING (revocado_en IS NULL AND EXISTS (SELECT 1 FROM membresia m "
        "WHERE m.id = refresh_token.membresia_id AND m.tenant_id = refresh_token.tenant_id "
        f"AND m.usuario_id = {RESET_USUARIO} AND {consumido('m.usuario_id')})) "
        "WITH CHECK (revocado_en = now())",
    ]


def _grants(owner: str) -> list[str]:
    # Mínimos y por columna; nunca DELETE ni TRUNCATE.
    return [
        f"GRANT UPDATE (password_hash) ON usuario TO {owner}",
        f"GRANT SELECT (membresia_id, revocado_en) ON refresh_token TO {owner}",
        f"GRANT UPDATE (revocado_en) ON refresh_token TO {owner}",
        f"GRANT SELECT (tenant_id, usuario_id, token_hash, expira_en, usada_en, invalidada_en) "
        f"ON {TABLE} TO {owner}",
        f"GRANT INSERT (tenant_id, usuario_id, token_hash, expira_en) ON {TABLE} TO {owner}",
        f"GRANT UPDATE (usada_en, invalidada_en) ON {TABLE} TO {owner}",
    ]


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

    statements = [*_policies(owner), *_grants(owner), *CREATE_STATEMENTS]
    statements += [f"REVOKE ALL ON FUNCTION {fn} FROM {', '.join(revoked)}" for fn in FUNCTIONS]
    statements += [f"GRANT EXECUTE ON FUNCTION {fn} TO {app}" for fn in FUNCTIONS]
    statements += [f"GRANT CREATE ON SCHEMA acceso TO {owner}", *opening]
    statements += [f"ALTER FUNCTION {fn} OWNER TO {owner}" for fn in FUNCTIONS]
    statements += [f"REVOKE CREATE ON SCHEMA acceso FROM {owner}", *closing]
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
    statements += [f"DROP POLICY {policy} ON {table}" for table, policy in POLICIES]
    statements += [
        f"REVOKE UPDATE (password_hash) ON usuario FROM {owner}",
        f"REVOKE SELECT (membresia_id, revocado_en), UPDATE (revocado_en) "  # noqa: S608
        f"ON refresh_token FROM {owner}",
        f"REVOKE ALL ON {TABLE} FROM {owner}",
    ]
    execute_statements(conn, statements)
    require_no_leftover_privileges(conn)
