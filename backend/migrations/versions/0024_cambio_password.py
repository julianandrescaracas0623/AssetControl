"""Cambio obligatorio de contraseña en el primer ingreso (spec 017, T4; R25–R28, A16).

``plan.md`` §2.6. Mismo patrón que 0016 (§2.1 de la spec 002).

- **La aplicación lee la marca.** ``GRANT SELECT (debe_cambiar_password) ON usuario`` al rol
  de la aplicación (solo esa columna): ``load_current_user`` la lee en cada petición, sin
  caché, y el decorador común responde ``403 cambio_password_requerido`` mientras sea
  ``true``. La aplicación sigue sin poder escribirla.
- **``acceso.cambiar_password_propio(p_usuario, p_tenant, p_hash_actual, p_hash_nuevo)``**
  -> ``boolean`` (``plpgsql``, ``SECURITY DEFINER``, ``STRICT``, ``SET search_path =
  pg_catalog, pg_temp``, todo calificado, SQL estático, dueña ``auth_owner``, ``EXECUTE``
  solo para el rol de la aplicación). Vacía al empezar y al terminar **las doce** GUC
  ``app.auth_*`` (0004, 0016 y la nueva ``app.auth_cambio_usuario``), fija solo la suya y
  nunca lee una GUC. Hash nuevo sin el formato completo de argon2-cffi o de más de 255
  caracteres -> ``22023 hash_invalido``. Usuario inactivo o sin exactamente una membresía
  activa (la de ``p_tenant``), o ``password_hash`` distinto de ``p_hash_actual`` (lo que
  Flask verificó con Argon2; compara y cambia en el mismo ``UPDATE``, así que dos cambios
  simultáneos con la misma contraseña actual no prosperan los dos) -> ``P0001
  cambio_invalido`` sin cambiar nada. Si todo cuadra, en la transacción de quien llama:
  guarda el hash nuevo, pone ``debe_cambiar_password = false`` y revoca los refresh vivos de
  las membresías del usuario (repetido hasta que no afecte filas, tope de 10 pasadas, como
  ``restablecer_contrasena``). Flask emite después, en la misma transacción, la familia
  nueva de la sesión que cambió (las demás quedan revocadas, R27). La función no hashea ni
  devuelve ``password_hash``.
- **``acceso.restablecer_contrasena``** (0016, R28): el mismo cuerpo carácter a carácter
  salvo que vacía también ``app.auth_cambio_usuario`` y que su ``UPDATE`` de ``usuario``
  pone además ``debe_cambiar_password = false`` (la eligió la persona). ``CREATE OR
  REPLACE`` como ``auth_owner``: conserva dueño, ``proacl`` y firma.

Políticas ``TO auth_owner`` (una por comando, nunca ``FOR ALL`` ni ``PUBLIC``; GUC validada
por formato: vacía, nula o con otro formato -> ``NULL`` -> cero filas), todas acotadas al
usuario de ``app.auth_cambio_usuario``: ``SELECT`` y ``UPDATE`` de su fila de ``usuario``
(solo si está activo), ``SELECT`` de sus membresías y ``SELECT``/``UPDATE`` de los refresh
de sus membresías (el ``UPDATE`` solo marca ``revocado_en = now()``). ``GRANT`` por columna
mínimos para ``auth_owner``: ``UPDATE (debe_cambiar_password)`` en ``usuario``; el ``SELECT
(password_hash)`` (0003), el ``UPDATE (password_hash)`` (0016) y los de ``refresh_token``
(0016) ya existían.

**Riesgo residual (documentado):** el rol de la aplicación puede leer cualquier
``password_hash`` con ``acceso.buscar_login`` (0004) y, con él, llamar a esta función para
cualquier usuario activo con una sola membresía. La base no puede atar la llamada al JWT
(lo valida Flask); quien controle el rol de la aplicación ya controla el login de todos.
La función no amplía lo que se puede leer.

**N4 (Q7/A11 de la 002):** el JWT de acceso de 15 minutos ya emitido no se revoca al cambiar
la contraseña: sigue sirviendo hasta su ``exp`` (ahora sin la marca). Corregido en
``0026_sesiones_validas_desde`` (M1).

Orden (C3/C5, como 0016): políticas y ``GRANT`` -> ``CREATE FUNCTION`` -> ``REVOKE ALL`` de
``PUBLIC`` y de los roles de Supabase -> ``GRANT EXECUTE`` a la aplicación -> ``CREATE``
transitorio en ``acceso`` y membresía transitoria ``WITH INHERIT FALSE, SET TRUE`` ->
``OWNER TO auth_owner`` y ``CREATE OR REPLACE`` de ``restablecer_contrasena`` como
``auth_owner`` -> ``REVOKE CREATE`` y fin de la membresía; al terminar se comprueba que no
quede nada (C8).

``downgrade``: borra la función nueva y restaura el cuerpo de 0016 de
``restablecer_contrasena`` (como ``auth_owner``), borra las cinco políticas y los ``GRANT``
de esta migración. No toca datos (la marca de cada usuario queda como esté).

Revision ID: 0024_cambio_password
Revises: 0023_invitacion_tenant_activo
Create Date: 2026-11-20
"""

import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0024_cambio_password"
down_revision: str | Sequence[str] | None = "0023_invitacion_tenant_activo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE_VAR = "APP_DB_USER"
AUTH_OWNER = "auth_owner"
SUPABASE_ROLES = ("anon", "authenticated", "service_role")

CAMBIAR = "acceso.cambiar_password_propio(uuid, uuid, text, text)"
FUNCTIONS = (CAMBIAR,)

# Las once GUC de 0004 y 0016 (las que vacía el cuerpo de 0016 de restablecer_contrasena).
AUTH_GUCS_0016 = (
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
CAMBIO_GUC = "app.auth_cambio_usuario"
AUTH_GUCS = (*AUTH_GUCS_0016, CAMBIO_GUC)

# (tabla, política): lista cerrada (la fijan test_catalog_rls.py y test_migrations.py).
POLICIES = (
    ("usuario", "dueno_usuario_cambio_leer"),
    ("usuario", "dueno_usuario_cambio_propio"),
    ("membresia", "dueno_membresia_cambio"),
    ("refresh_token", "dueno_refresh_cambio"),
    ("refresh_token", "dueno_refresh_cambio_revocar"),
)

_UUID = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def uuid_setting(guc: str) -> str:
    """UUID de ``guc``; ``NULL`` si falta o no es un UUID en minúsculas."""
    value = f"pg_catalog.current_setting('{guc}', true)"
    return f"(CASE WHEN {value} ~ '{_UUID}' THEN ({value})::uuid END)"


CAMBIO_USUARIO = uuid_setting(CAMBIO_GUC)


def _clear(gucs: Sequence[str]) -> str:
    return (
        "PERFORM pg_catalog.set_config(g, '', true) "
        "FROM pg_catalog.unnest(ARRAY['" + "', '".join(gucs) + "']::text[]) AS g;"
    )


_CLEAR = _clear(AUTH_GUCS)
_KEY_FORMAT = "'^[0-9a-f]{64}$'"
# Formato completo del hash de argon2-cffi (como 0016/0018), sin barras invertidas (B1).
_HASH_FORMAT = (
    "'^[$]argon2id[$]v=19[$]m=[0-9]+,t=[0-9]+,p=[0-9]+[$][A-Za-z0-9+/]+[$][A-Za-z0-9+/]+$'"
)
_HASH_MAX_LENGTH = 255
_REVOKE_MAX_PASSES = 10
_HEADER = "LANGUAGE plpgsql STRICT SECURITY DEFINER SET search_path = pg_catalog, pg_temp"
_ENLACE_INVALIDO = "RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'enlace_invalido';"
_CAMBIO_INVALIDO = "RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'cambio_invalido';"

CREATE_CAMBIAR = f"""
CREATE FUNCTION acceso.cambiar_password_propio(
    p_usuario uuid, p_tenant uuid, p_hash_actual text, p_hash_nuevo text)
RETURNS boolean
{_HEADER}
AS $fn$
DECLARE
    v_activas integer;
    v_tenant_activo uuid;
    v_filas bigint;
BEGIN
    {_CLEAR}
    IF p_hash_nuevo !~ {_HASH_FORMAT}
       OR pg_catalog.length(p_hash_nuevo) > {_HASH_MAX_LENGTH} THEN
        RAISE EXCEPTION USING ERRCODE = '22023', MESSAGE = 'hash_invalido';
    END IF;
    PERFORM pg_catalog.set_config('{CAMBIO_GUC}', p_usuario::text, true);
    SELECT pg_catalog.count(*)::integer, (pg_catalog.array_agg(m.tenant_id))[1]
        INTO v_activas, v_tenant_activo
        FROM public.membresia AS m WHERE m.usuario_id = p_usuario AND m.activa;
    IF v_activas <> 1 OR v_tenant_activo <> p_tenant THEN
        {_CAMBIO_INVALIDO}
    END IF;
    UPDATE public.usuario AS u
        SET password_hash = p_hash_nuevo, debe_cambiar_password = false
        WHERE u.id = p_usuario AND u.activo AND u.password_hash = p_hash_actual;
    GET DIAGNOSTICS v_filas = ROW_COUNT;
    IF v_filas <> 1 THEN
        {_CAMBIO_INVALIDO}
    END IF;
    FOR v_pasada IN 1..{_REVOKE_MAX_PASSES} LOOP
        UPDATE public.refresh_token AS t SET revocado_en = pg_catalog.now()
            WHERE t.revocado_en IS NULL AND t.membresia_id IN (
                SELECT m.id FROM public.membresia AS m WHERE m.usuario_id = p_usuario);
        EXIT WHEN NOT FOUND;
    END LOOP;
    {_CLEAR}
    RETURN true;
END
$fn$
"""  # noqa: S608 - solo constantes del módulo


def _restablecer(gucs: Sequence[str], *, quita_marca: bool) -> str:
    """``acceso.restablecer_contrasena`` (0016); con ``quita_marca``, R28 de la 017."""
    clear = _clear(gucs)
    marca = ", debe_cambiar_password = false" if quita_marca else ""
    return f"""
CREATE OR REPLACE FUNCTION acceso.restablecer_contrasena(p_clave text, p_password_hash text)
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
    {clear}
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
    UPDATE public.usuario AS u SET password_hash = p_password_hash{marca} WHERE u.id = v_usuario;
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
    {clear}
    RETURN v_usuario;
END
$fn$
"""  # noqa: S608 - solo constantes del módulo


# Cuerpo nuevo y el de 0016 (idéntico carácter a carácter entre $fn$; huella C6).
REPLACE_RESTABLECER = _restablecer(AUTH_GUCS, quita_marca=True)
RESTORE_RESTABLECER = _restablecer(AUTH_GUCS_0016, quita_marca=False)

_ROLE_EXISTS = text("select exists (select 1 from pg_roles where rolname = :name)")
_ROLE_SKIPS_RLS = text("select rolsuper or rolbypassrls from pg_roles where rolname = :name")
_ROLE_UNSAFE = text(
    "select coalesce((select r.rolsuper or r.rolbypassrls or r.rolcanlogin or r.rolcreaterole "
    "or r.rolcreatedb or r.rolreplication "
    "or exists (select 1 from pg_auth_members m where m.member = r.oid) "
    "from pg_roles r where r.rolname = :name), true)"
)
_APP_IS_OWNER_MEMBER = text("select pg_has_role(:app, :owner, 'MEMBER')")
# Igual que 0004/0016 (C8): por rolname exacto; la membresía ADMIN del creador en Supabase,
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
            "La migración 0024 exige PostgreSQL 16 o superior (membresía transitoria "
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
            "Tras la migración 0024, el rol dueño de las funciones de acceso conserva CREATE "
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
                f"La migración 0024 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def _transient_membership(owner: str, migrator: str) -> tuple[list[str], list[str]]:
    opening = [f"GRANT {owner} TO {migrator} WITH INHERIT FALSE, SET TRUE"]
    closing = [f"REVOKE {owner} FROM {migrator}"]
    return opening, closing


def _de_sus_membresias(tabla: str) -> str:
    """Un refresh de ``tabla`` de una membresía del usuario de ``app.auth_cambio_usuario``."""
    return (
        f"EXISTS (SELECT 1 FROM membresia m WHERE m.id = {tabla}.membresia_id "  # noqa: S608
        f"AND m.tenant_id = {tabla}.tenant_id AND m.usuario_id = {CAMBIO_USUARIO})"
    )


def _policies(owner: str) -> list[str]:
    return [
        f"CREATE POLICY dueno_usuario_cambio_leer ON usuario FOR SELECT TO {owner} "
        f"USING (id = {CAMBIO_USUARIO})",
        f"CREATE POLICY dueno_usuario_cambio_propio ON usuario FOR UPDATE TO {owner} "
        f"USING (id = {CAMBIO_USUARIO} AND activo) "
        f"WITH CHECK (id = {CAMBIO_USUARIO} AND activo)",
        f"CREATE POLICY dueno_membresia_cambio ON membresia FOR SELECT TO {owner} "
        f"USING (usuario_id = {CAMBIO_USUARIO})",
        f"CREATE POLICY dueno_refresh_cambio ON refresh_token FOR SELECT TO {owner} "
        f"USING ({_de_sus_membresias('refresh_token')})",
        f"CREATE POLICY dueno_refresh_cambio_revocar ON refresh_token FOR UPDATE TO {owner} "
        f"USING (revocado_en IS NULL AND {_de_sus_membresias('refresh_token')}) "
        "WITH CHECK (revocado_en = now())",
    ]


def upgrade() -> None:
    conn = op.get_bind()
    require_auth_owner(conn)
    require_postgres_16(conn)
    quote = conn.dialect.identifier_preparer.quote
    app = quote(_app_role(conn))
    owner = quote(AUTH_OWNER)
    migrator = quote(conn.scalar(text("select current_user")))
    revoked = ["PUBLIC"] + [
        quote(role) for role in SUPABASE_ROLES if conn.scalar(_ROLE_EXISTS, {"name": role})
    ]
    opening, closing = _transient_membership(owner, migrator)

    statements = [
        *_policies(owner),
        f"GRANT UPDATE (debe_cambiar_password) ON usuario TO {owner}",
        f"GRANT SELECT (debe_cambiar_password) ON usuario TO {app}",
        CREATE_CAMBIAR,
    ]
    statements += [f"REVOKE ALL ON FUNCTION {fn} FROM {', '.join(revoked)}" for fn in FUNCTIONS]
    statements += [f"GRANT EXECUTE ON FUNCTION {fn} TO {app}" for fn in FUNCTIONS]
    statements += [f"GRANT CREATE ON SCHEMA acceso TO {owner}", *opening]
    statements += [f"ALTER FUNCTION {fn} OWNER TO {owner}" for fn in FUNCTIONS]
    statements += [f"SET LOCAL ROLE {owner}", REPLACE_RESTABLECER, "RESET ROLE"]
    statements += [f"REVOKE CREATE ON SCHEMA acceso FROM {owner}", *closing]
    execute_statements(conn, statements)
    require_no_leftover_privileges(conn)


def downgrade() -> None:
    conn = op.get_bind()
    require_auth_owner(conn)
    require_postgres_16(conn)
    quote = conn.dialect.identifier_preparer.quote
    app = quote(_app_role(conn))
    owner = quote(AUTH_OWNER)
    migrator = quote(conn.scalar(text("select current_user")))
    opening, closing = _transient_membership(owner, migrator)
    # Solo el dueño (auth_owner) puede borrar y reemplazar sus funciones: SET LOCAL ROLE.
    statements = [f"GRANT CREATE ON SCHEMA acceso TO {owner}", *opening, f"SET LOCAL ROLE {owner}"]
    statements += [f"DROP FUNCTION {fn}" for fn in FUNCTIONS]
    statements += [RESTORE_RESTABLECER, "RESET ROLE"]
    statements += [f"REVOKE CREATE ON SCHEMA acceso FROM {owner}", *closing]
    statements += [f"DROP POLICY {policy} ON {table}" for table, policy in POLICIES]
    statements += [
        f"REVOKE UPDATE (debe_cambiar_password) ON usuario FROM {owner}",
        f"REVOKE SELECT (debe_cambiar_password) ON usuario FROM {app}",  # noqa: S608
    ]
    execute_statements(conn, statements)
    require_no_leftover_privileges(conn)
