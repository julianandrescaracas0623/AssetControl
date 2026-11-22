"""Una invitación de una empresa desactivada no vale (spec 017, T3b; R22, A9).

Hallazgo de la revisión de T3b: con ``tenant.activo`` falso, ``acceso.aceptar_invitacion``
consumía la invitación y creaba ``usuario`` y ``membresia`` en el tenant inactivo; la
sesión no salía y la ruta respondía ``500``, con la invitación gastada y el correo (único
global) ocupado. Ahora las dos funciones de invitación (0004, dueña ``auth_owner``) exigen
que el tenant de la invitación esté activo:

- ``acceso.validar_invitacion`` -> ``false``, igual que una invitación vencida.
- ``acceso.aceptar_invitacion`` -> cero filas sin consumir ni crear nada: la ruta responde
  el ``400 invitacion_invalida`` genérico de siempre (sin código nuevo ni oráculo) y, tras
  reactivar la empresa, la misma invitación sigue valiendo.

El resto del cuerpo es el de 0004 carácter a carácter (mismas seis GUC vaciadas, mismo
``STRICT``, ``SECURITY DEFINER`` y ``search_path``). ``CREATE OR REPLACE`` como
``auth_owner`` (``SET LOCAL ROLE`` con la membresía transitoria ``WITH INHERIT FALSE, SET
TRUE``): conserva dueño, ``proacl`` y firma.

``auth_owner`` ya lee ``tenant (id, creado_en, activo)`` (0003 y 0018); solo le falta ver
la fila: dos políticas ``SELECT`` de ``tenant`` ``TO auth_owner``, una por GUC de función
(``app.auth_inv_validar`` y ``app.auth_inv_aceptar``, las que ya fijan), acotadas al tenant
de la invitación de esa clave. Sin ``GRANT`` nuevo.

``downgrade``: restaura los dos cuerpos de 0004 y borra las dos políticas. No borra datos.

Revision ID: 0023_invitacion_tenant_activo
Revises: 0018_funciones_plataforma
Create Date: 2026-11-20
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0023_invitacion_tenant_activo"
down_revision: str | Sequence[str] | None = "0018_funciones_plataforma"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AUTH_OWNER = "auth_owner"

# Las seis GUC de 0004 (las que vacían los cuerpos de 0004; no cambian).
OWNER_GUCS = (
    "app.auth_email",
    "app.auth_usuario",
    "app.auth_inv_validar",
    "app.auth_inv_aceptar",
    "app.auth_usuario_nuevo",
    "app.auth_tenant_nuevo",
)

# (tabla, política): lista cerrada (la fijan test_catalog_rls.py y test_migrations.py).
POLICIES = (
    ("tenant", "dueno_tenant_inv_validar"),
    ("tenant", "dueno_tenant_inv_aceptar"),
)

_HEX_KEY = "^[0-9a-f]{64}$"
_KEY_FORMAT = "'^[0-9a-f]{64}$'"
_HEADER = "LANGUAGE plpgsql STRICT SECURITY DEFINER SET search_path = pg_catalog, pg_temp"
_CLEAR = (
    "PERFORM pg_catalog.set_config(g, '', true) "
    "FROM pg_catalog.unnest(ARRAY['" + "', '".join(OWNER_GUCS) + "']::text[]) AS g;"
)


def key_hash(guc: str) -> str:
    """``sha256`` de la clave hex de ``guc``; ``NULL`` si falta o no tiene el formato (0003)."""
    value = f"pg_catalog.current_setting('{guc}', true)"
    return (
        f"(CASE WHEN {value} ~ '{_HEX_KEY}' "
        f"THEN pg_catalog.sha256(pg_catalog.decode({value}, 'hex')) END)"
    )


def _tenant_policy(name: str, guc: str, owner: str) -> str:
    return (
        f"CREATE POLICY {name} ON tenant FOR SELECT TO {owner} "  # noqa: S608
        "USING (EXISTS (SELECT 1 FROM invitacion i "
        f"WHERE i.tenant_id = tenant.id AND i.token_hash = {key_hash(guc)}))"
    )


# Condición nueva: el tenant de la invitación está activo.
_TENANT_ACTIVO = (
    "\n          AND EXISTS (SELECT 1 FROM public.tenant AS t "
    "WHERE t.id = i.tenant_id AND t.activo)"
)


def _validar(*, tenant_activo: bool) -> str:
    """``acceso.validar_invitacion`` (0004); con ``tenant_activo``, solo de tenants activos."""
    extra = _TENANT_ACTIVO if tenant_activo else ""
    return f"""
CREATE OR REPLACE FUNCTION acceso.validar_invitacion(p_clave text)
RETURNS boolean
{_HEADER}
AS $fn$
DECLARE
    v_vigente boolean;
BEGIN
    {_CLEAR}
    IF p_clave !~ {_KEY_FORMAT} THEN
        RETURN false;
    END IF;
    PERFORM pg_catalog.set_config('app.auth_inv_validar', p_clave, true);
    v_vigente := EXISTS (
        SELECT 1 FROM public.invitacion AS i
        WHERE i.token_hash = pg_catalog.sha256(pg_catalog.decode(p_clave, 'hex'))
          AND i.usada_en IS NULL AND i.expira_en > pg_catalog.now(){extra}
    );
    {_CLEAR}
    RETURN v_vigente;
END
$fn$
"""  # noqa: S608 - solo constantes del módulo


def _aceptar(*, tenant_activo: bool) -> str:
    """``acceso.aceptar_invitacion`` (0004); con ``tenant_activo``, no consume si está inactivo."""
    extra = _TENANT_ACTIVO if tenant_activo else ""
    return f"""
CREATE OR REPLACE FUNCTION acceso.aceptar_invitacion(
    p_clave text, p_nombre text, p_password_hash text)
RETURNS TABLE (usuario_id uuid, tenant_id uuid, rol text)
{_HEADER}
AS $fn$
DECLARE
    v_email text;
    v_tenant uuid;
    v_rol text;
    v_usuario uuid;
    v_filas bigint;
BEGIN
    {_CLEAR}
    IF p_clave !~ {_KEY_FORMAT} THEN
        RETURN;
    END IF;
    PERFORM pg_catalog.set_config('app.auth_inv_aceptar', p_clave, true);
    UPDATE public.invitacion AS i SET usada_en = pg_catalog.now()
        WHERE i.token_hash = pg_catalog.sha256(pg_catalog.decode(p_clave, 'hex'))
          AND i.usada_en IS NULL AND i.expira_en > pg_catalog.now(){extra}
        RETURNING i.email, i.tenant_id, i.rol INTO v_email, v_tenant, v_rol;
    IF NOT FOUND THEN
        {_CLEAR}
        RETURN;
    END IF;
    v_usuario := pg_catalog.gen_random_uuid();
    INSERT INTO public.usuario (id, email, nombre, password_hash)
        VALUES (v_usuario, v_email, p_nombre, p_password_hash)
        ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_filas = ROW_COUNT;
    IF v_filas <> 1 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'invitacion_invalida';
    END IF;
    PERFORM pg_catalog.set_config('app.auth_usuario_nuevo', v_usuario::text, true);
    INSERT INTO public.membresia (tenant_id, usuario_id, rol) VALUES (v_tenant, v_usuario, v_rol);
    {_CLEAR}
    RETURN QUERY SELECT v_usuario, v_tenant, v_rol;
END
$fn$
"""  # noqa: S608 - solo constantes del módulo


# Cuerpos nuevos y los de 0004, idénticos carácter a carácter entre $fn$ (huella C6).
REPLACE_VALIDAR = _validar(tenant_activo=True)
REPLACE_ACEPTAR = _aceptar(tenant_activo=True)
RESTORE_VALIDAR = _validar(tenant_activo=False)
RESTORE_ACEPTAR = _aceptar(tenant_activo=False)

_ROLE_EXISTS = text("select exists (select 1 from pg_roles where rolname = :name)")
_ROLE_UNSAFE = text(
    "select coalesce((select r.rolsuper or r.rolbypassrls or r.rolcanlogin or r.rolcreaterole "
    "or r.rolcreatedb or r.rolreplication "
    "or exists (select 1 from pg_auth_members m where m.member = r.oid) "
    "from pg_roles r where r.rolname = :name), true)"
)
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
            "La migración 0023 exige PostgreSQL 16 o superior (membresía transitoria "
            "WITH INHERIT FALSE, SET TRUE; plan.md §2.1 de la spec 002)."
        )


def require_no_leftover_privileges(conn: Connection) -> None:
    """C5: al terminar, ``auth_owner`` sin ``CREATE`` en ``acceso`` y el migrador no es miembro."""
    if conn.scalar(_OWNER_CAN_CREATE, {"owner": AUTH_OWNER}) or conn.scalar(
        _MIGRATOR_IS_MEMBER, {"owner": AUTH_OWNER}
    ):
        raise RuntimeError(
            "Tras la migración 0023, el rol dueño de las funciones de acceso conserva CREATE "
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
                f"La migración 0023 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def _replace_as_owner(auth: str, migrator: str, bodies: Sequence[str]) -> list[str]:
    """``CREATE OR REPLACE`` como ``auth_owner``: conserva dueño, ``proacl`` y firma."""
    return [
        f"GRANT CREATE ON SCHEMA acceso TO {auth}",
        f"GRANT {auth} TO {migrator} WITH INHERIT FALSE, SET TRUE",
        f"SET LOCAL ROLE {auth}",
        *bodies,
        "RESET ROLE",
        f"REVOKE CREATE ON SCHEMA acceso FROM {auth}",
        f"REVOKE {auth} FROM {migrator}",
    ]


def upgrade() -> None:
    conn = op.get_bind()
    require_auth_owner(conn)
    require_postgres_16(conn)
    quote = conn.dialect.identifier_preparer.quote
    auth = quote(AUTH_OWNER)
    migrator = quote(conn.scalar(text("select current_user")))
    statements = [
        _tenant_policy("dueno_tenant_inv_validar", "app.auth_inv_validar", auth),
        _tenant_policy("dueno_tenant_inv_aceptar", "app.auth_inv_aceptar", auth),
    ]
    statements += _replace_as_owner(auth, migrator, (REPLACE_VALIDAR, REPLACE_ACEPTAR))
    execute_statements(conn, statements)
    require_no_leftover_privileges(conn)


def downgrade() -> None:
    conn = op.get_bind()
    require_auth_owner(conn)
    require_postgres_16(conn)
    quote = conn.dialect.identifier_preparer.quote
    auth = quote(AUTH_OWNER)
    migrator = quote(conn.scalar(text("select current_user")))
    statements = _replace_as_owner(auth, migrator, (RESTORE_VALIDAR, RESTORE_ACEPTAR))
    statements += [f"DROP POLICY {policy} ON {table}" for table, policy in POLICIES]
    execute_statements(conn, statements)
    require_no_leftover_privileges(conn)
