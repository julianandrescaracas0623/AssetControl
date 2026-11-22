"""Corte de los JWT de acceso al cambiar o restablecer la contraseña (spec 017, T4; M1).

Hallazgo M1 de la revisión de seguridad de T4: el JWT de acceso de 15 minutos emitido con
la contraseña inicial (bloqueado por ``debe_cambiar_password``) recuperaba todos los
permisos al cambiarla, porque la marca pasaba a ``false`` y el token seguía vivo hasta su
``exp``. Quien creó la empresa conoce la contraseña inicial: en esa ventana, con rol admin,
podía crearse una invitación y conservar el acceso.

- **Columna ``usuario.sesiones_validas_desde timestamptz``** (``NULL`` = sin corte; ningún
  usuario existente cambia). ``GRANT SELECT (sesiones_validas_desde)`` a la aplicación (la
  lee ``load_current_user`` en cada petición, sin caché) y ``GRANT UPDATE
  (sesiones_validas_desde)`` solo a ``auth_owner``: la aplicación nunca la escribe.
- **``acceso.cambiar_password_propio``** (0024) y **``acceso.restablecer_contrasena``**
  (0024, antes 0016): el mismo cuerpo carácter a carácter salvo que el ``UPDATE`` de
  ``usuario`` que cambia el hash pone además ``sesiones_validas_desde =
  pg_catalog.now()`` (la misma sentencia: no hay hash nuevo sin corte). ``CREATE OR
  REPLACE`` como ``auth_owner``: conserva dueño, ``proacl``, firma, ``SECURITY DEFINER``,
  ``STRICT``, ``search_path`` y las GUC que vacía; las políticas de 0016 y 0024 ya dejan al
  dueño actualizar esa fila (ninguna política nueva).
- **Flask** (``app.auth.service.load_current_user``, punto único de cada petición del
  tenant) rechaza con el mismo ``401 no_autenticado`` un JWT cuyo ``iat`` (entero, en
  segundos) sea menor que ``floor(epoch(sesiones_validas_desde))``. Un token emitido en el
  mismo segundo del corte vale: así la sesión nueva que responde el cambio (su ``iat`` nunca
  es anterior al corte) sigue funcionando. Riesgo residual: un token emitido en el mismo
  segundo pero antes del corte también vale (ventana de menos de un segundo).
  ``pg_catalog.now()`` es el inicio de la transacción, así que el corte nunca es posterior
  al instante del cambio. El token de la consola de plataforma no cambia.

**N4 (Q7/A11 de la 002):** queda resuelto solo en estos dos casos (cambio de contraseña
propio y restablecer por correo de la 014). El JWT ya emitido sigue vivo tras ``logout``
hasta su ``exp`` (15 min): ese riesgo sigue aceptado.

Orden (C3/C5, como 0016 y 0024): columna y ``GRANT`` -> ``CREATE`` transitorio en
``acceso`` y membresía transitoria ``WITH INHERIT FALSE, SET TRUE`` -> ``CREATE OR
REPLACE`` de las dos funciones como ``auth_owner`` -> ``REVOKE CREATE`` y fin de la
membresía; al terminar se comprueba que no quede nada (C8).

``downgrade``: restaura los cuerpos exactos de 0024 (como ``auth_owner``), retira los dos
``GRANT`` y borra la columna (solo el corte de esta migración; ningún usuario, hash ni
marca cambia).

Revision ID: 0026_sesiones_validas_desde
Revises: 0025_limite_tasa_plataforma
Create Date: 2026-11-20
"""

import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0026_sesiones_validas_desde"
down_revision: str | Sequence[str] | None = "0025_limite_tasa_plataforma"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE_VAR = "APP_DB_USER"
AUTH_OWNER = "auth_owner"
COLUMN = "sesiones_validas_desde"
# Lo único que añaden las dos funciones: la misma asignación en el UPDATE del hash.
CORTE = ", sesiones_validas_desde = pg_catalog.now()"

# Las doce GUC que vacían las dos funciones desde 0024 (las once de 0004/0016 y la de 0024).
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
)
CAMBIO_GUC = "app.auth_cambio_usuario"

_CLEAR = (
    "PERFORM pg_catalog.set_config(g, '', true) "
    "FROM pg_catalog.unnest(ARRAY['" + "', '".join(AUTH_GUCS) + "']::text[]) AS g;"
)
_KEY_FORMAT = "'^[0-9a-f]{64}$'"
# Formato completo del hash de argon2-cffi (como 0016/0018/0024), sin barras invertidas.
_HASH_FORMAT = (
    "'^[$]argon2id[$]v=19[$]m=[0-9]+,t=[0-9]+,p=[0-9]+[$][A-Za-z0-9+/]+[$][A-Za-z0-9+/]+$'"
)
_HASH_MAX_LENGTH = 255
_REVOKE_MAX_PASSES = 10
_HEADER = "LANGUAGE plpgsql STRICT SECURITY DEFINER SET search_path = pg_catalog, pg_temp"
_ENLACE_INVALIDO = "RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'enlace_invalido';"
_CAMBIO_INVALIDO = "RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'cambio_invalido';"


def _cambiar(*, corte: bool) -> str:
    """``acceso.cambiar_password_propio`` de 0024; con ``corte``, M1 (esta migración)."""
    extra = CORTE if corte else ""
    return f"""
CREATE OR REPLACE FUNCTION acceso.cambiar_password_propio(
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
        SET password_hash = p_hash_nuevo, debe_cambiar_password = false{extra}
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


def _restablecer(*, corte: bool) -> str:
    """``acceso.restablecer_contrasena`` de 0024; con ``corte``, M1 (esta migración)."""
    extra = CORTE if corte else ""
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
    UPDATE public.usuario AS u SET password_hash = p_password_hash, debe_cambiar_password = false{extra} WHERE u.id = v_usuario;
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
"""  # noqa: S608, E501 - solo constantes del módulo; la línea del UPDATE es la de 0024


# Cuerpos nuevos y los de 0024 (idénticos carácter a carácter entre $fn$; huella C6).
REPLACE_CAMBIAR = _cambiar(corte=True)
REPLACE_RESTABLECER = _restablecer(corte=True)
RESTORE_CAMBIAR = _cambiar(corte=False)
RESTORE_RESTABLECER = _restablecer(corte=False)

_ROLE_EXISTS = text("select exists (select 1 from pg_roles where rolname = :name)")
_ROLE_SKIPS_RLS = text("select rolsuper or rolbypassrls from pg_roles where rolname = :name")
_ROLE_UNSAFE = text(
    "select coalesce((select r.rolsuper or r.rolbypassrls or r.rolcanlogin or r.rolcreaterole "
    "or r.rolcreatedb or r.rolreplication "
    "or exists (select 1 from pg_auth_members m where m.member = r.oid) "
    "from pg_roles r where r.rolname = :name), true)"
)
_APP_IS_OWNER_MEMBER = text("select pg_has_role(:app, :owner, 'MEMBER')")
# Igual que 0004/0016/0024 (C8): por rolname exacto; la membresía ADMIN del creador en
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
            "La migración 0026 exige PostgreSQL 16 o superior (membresía transitoria "
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
            "Tras la migración 0026, el rol dueño de las funciones de acceso conserva CREATE "
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
                f"La migración 0026 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def _replace_as_owner(owner: str, migrator: str, bodies: Sequence[str]) -> list[str]:
    """``CREATE OR REPLACE`` de ``bodies`` como ``auth_owner`` con privilegios transitorios."""
    return [
        f"GRANT CREATE ON SCHEMA acceso TO {owner}",
        f"GRANT {owner} TO {migrator} WITH INHERIT FALSE, SET TRUE",
        f"SET LOCAL ROLE {owner}",
        *bodies,
        "RESET ROLE",
        f"REVOKE CREATE ON SCHEMA acceso FROM {owner}",
        f"REVOKE {owner} FROM {migrator}",
    ]


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
    statements = [
        f"ALTER TABLE usuario ADD COLUMN {COLUMN} timestamptz",
        f"GRANT SELECT ({COLUMN}) ON usuario TO {app}",
        f"GRANT UPDATE ({COLUMN}) ON usuario TO {owner}",
        *_replace_as_owner(owner, migrator, [REPLACE_CAMBIAR, REPLACE_RESTABLECER]),
    ]
    execute_statements(conn, statements)
    require_no_leftover_privileges(conn)


def downgrade() -> None:
    conn = op.get_bind()
    app, owner, migrator = _roles(conn)
    statements = [
        *_replace_as_owner(owner, migrator, [RESTORE_CAMBIAR, RESTORE_RESTABLECER]),
        f"REVOKE UPDATE ({COLUMN}) ON usuario FROM {owner}",
        f"REVOKE SELECT ({COLUMN}) ON usuario FROM {app}",  # noqa: S608
        f"ALTER TABLE usuario DROP COLUMN {COLUMN}",
    ]
    execute_statements(conn, statements)
    require_no_leftover_privileges(conn)
