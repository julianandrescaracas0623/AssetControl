"""Función del módulo Actividad de la consola (spec 017, T6).

``plan.md`` §2.3 y §5 (la fila ``0021_plataforma_actividad``). El nombre previsto en el
plan, ``0021_plataforma_actividad``, no se usa (0019–0022 quedan sin usar): la migración
real es esta, ``0028_plataforma_actividad``, y la cadena sigue tras ``0027``. ``spec.md``
R32, R34, R36; A4, A5, A6, A18. Mismo patrón que 0018 y 0027.

Función nueva (``plpgsql``, ``SECURITY DEFINER``, ``STRICT``, ``SET search_path =
pg_catalog, pg_temp``, todo calificado, SQL estático, dueña ``plataforma_owner``,
``EXECUTE`` solo para el rol de la aplicación). Vacía al empezar y al terminar **todas**
las GUC ``app.plat_*`` (las trece de 0017, 0018 y 0027 y la de aquí), fija solo las suyas
con valores que ella recibe y nunca lee una GUC. Su primera comprobación (A5, R36):
``p_desarrollador`` existe y está activo; si no, ``42501 desarrollador_no_autorizado`` sin
devolver filas.

- ``acceso.plataforma_listar_auditoria(p_desarrollador, p_tenant, p_accion, p_desde,
  p_hasta, p_limite, p_cursor_fecha, p_cursor_id)`` -> ``id``, ``creado_en``, ``accion``,
  ``resultado``, ``desarrollador_nombre``, ``tenant_id``, ``tenant_nombre``, ``objeto_id``
  (R32): la auditoría con ``LEFT JOIN`` a ``desarrollador`` y ``tenant`` solo para los
  nombres (se leen al consultar, R34: nunca se copian a la auditoría), de la más reciente
  a la más antigua por ``(creado_en, id)`` y estrictamente después del cursor
  ``(p_cursor_fecha, p_cursor_id)``. Solo lectura: no escribe nada (tampoco auditoría).
  Como la función es ``STRICT``, «sin filtro» viaja con valores centinela, nunca ``NULL``:
  ``p_tenant`` = UUID nulo (``00000000-…``; Flask rechaza ese id como filtro),
  ``p_accion`` = ``''`` (no está en la lista cerrada de R33), ``p_desde`` =
  ``-infinity``, ``p_hasta`` = ``infinity`` (el rango es ``[p_desde, p_hasta)``) y, en la
  primera página, el cursor ``(infinity, ffffffff-…)``. ``p_limite`` se acota aquí a
  ``[1, LIMITE_MAX]`` (``LIMITE_MAX`` = 100 por página más una fila para saber si hay otra
  página). Sin correos, IP, hashes ni texto libre: la tabla no los tiene.

Políticas ``TO plataforma_owner`` (una por comando, nunca ``FOR ALL`` ni ``PUBLIC``; la GUC
validada por formato: vacía o con otro formato -> ``NULL`` -> cero filas):

- ``plataforma_auditoria`` y ``tenant`` ``FOR SELECT`` con el desarrollador de
  ``app.plat_actividad`` activo (todas las filas: el desarrollador activo ve toda la
  auditoría y el nombre de cualquier empresa, como ya ve en Empresas).
- ``desarrollador`` ``FOR SELECT`` con ``app.plat_actividad`` no nula (todas las filas,
  solo para el nombre). No puede exigir «desarrollador activo» con un ``EXISTS`` sobre la
  propia tabla (recursión infinita de la política, como ``dueno_plat_desarrollador_actor``
  de 0018); la función ya lo comprobó antes de fijar la GUC y la vacía al salir.

``GRANT`` por columna mínimos, sin ``DELETE`` ni ``UPDATE``: ``plataforma_auditoria``
``SELECT`` de sus siete columnas (ninguna es un dato personal, R34) y ``desarrollador``
``SELECT (nombre)`` (además de lo de 0017; nunca ``password_hash`` fuera del login). De
``tenant`` basta lo de 0018 (``id``, ``nombre``). La aplicación no gana nada: su ``SELECT``
sobre ``plataforma_auditoria`` (0017, para un desarrollador activo en la
``plataforma_session``; lo necesita también el ``INSERT … RETURNING`` de la auditoría) no
cambia, y sin la función no lee nombres de otros desarrolladores ni de ninguna empresa.

Orden (C3/C5): políticas y ``GRANT`` -> ``CREATE FUNCTION`` -> ``REVOKE ALL`` de
``PUBLIC`` y de los roles de Supabase -> ``GRANT EXECUTE`` a la aplicación -> ``CREATE``
transitorio en ``acceso`` y membresía transitoria ``WITH INHERIT FALSE, SET TRUE`` ->
``OWNER TO plataforma_owner`` -> ``REVOKE CREATE`` y fin de la membresía; al terminar se
comprueba que no quede nada (C8). Los índices de la auditoría ya los creó 0017
(``(creado_en DESC, id DESC)``, ``(tenant_id, creado_en DESC)`` y ``(accion, creado_en
DESC)``); aquí no se crea ninguno.

``downgrade``: borra la función como ``plataforma_owner``, sus políticas y solo los
``GRANT`` de aquí. No borra datos.

El nombre previsto ``0021_plataforma_actividad`` no se usa; la revisión real es 0028.

Revision ID: 0028_plataforma_actividad
Revises: 0027_plataforma_usuarios
Create Date: 2026-11-20
"""

import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0028_plataforma_actividad"
down_revision: str | Sequence[str] | None = "0027_plataforma_usuarios"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE_VAR = "APP_DB_USER"
AUTH_OWNER = "auth_owner"
PLATAFORMA_OWNER = "plataforma_owner"
SUPABASE_ROLES = ("anon", "authenticated", "service_role")

LISTAR = (
    "acceso.plataforma_listar_auditoria(uuid, uuid, text, timestamp with time zone, "
    "timestamp with time zone, integer, timestamp with time zone, uuid)"
)
FUNCTIONS = (LISTAR,)

# Todas las GUC de las políticas de plataforma_owner (0017, 0018, 0027 y esta).
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
    "app.plat_actividad",
)

# (tabla, política): lista cerrada (la fijan test_plataforma_catalogo.py y test_migrations.py).
POLICIES = (
    ("plataforma_auditoria", "dueno_plat_auditoria_actividad"),
    ("tenant", "dueno_plat_tenant_actividad"),
    ("desarrollador", "dueno_plat_desarrollador_actividad"),
)

# 100 por página (R32) más una fila para saber si hay otra página.
LIMITE_MAX = 101

_UUID = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def uuid_setting(guc: str) -> str:
    """UUID de ``guc``; ``NULL`` si falta o no es un UUID en minúsculas (como 0018)."""
    value = f"pg_catalog.current_setting('{guc}', true)"
    return f"(CASE WHEN {value} ~ '{_UUID}' THEN ({value})::uuid END)"


ACTIVIDAD = uuid_setting("app.plat_actividad")
ACTIVIDAD_ACTIVO = f"EXISTS (SELECT 1 FROM desarrollador d WHERE d.id = {ACTIVIDAD} AND d.activo)"  # noqa: S608

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

CREATE_LISTAR = f"""
CREATE FUNCTION acceso.plataforma_listar_auditoria(
    p_desarrollador uuid, p_tenant uuid, p_accion text, p_desde timestamptz,
    p_hasta timestamptz, p_limite integer, p_cursor_fecha timestamptz, p_cursor_id uuid)
RETURNS TABLE (id uuid, creado_en timestamptz, accion text, resultado text,
               desarrollador_nombre text, tenant_id uuid, tenant_nombre text, objeto_id uuid)
{_HEADER}
AS $fn$
DECLARE
    v_activo boolean;
BEGIN
    {_CLEAR}
    {_DESARROLLADOR_ACTIVO}
    PERFORM pg_catalog.set_config('app.plat_actividad', p_desarrollador::text, true);
    RETURN QUERY SELECT a.id, a.creado_en, a.accion, a.resultado, d.nombre, a.tenant_id,
            t.nombre, a.objeto_id
        FROM public.plataforma_auditoria AS a
        LEFT JOIN public.desarrollador AS d ON d.id = a.desarrollador_id
        LEFT JOIN public.tenant AS t ON t.id = a.tenant_id
        WHERE (p_tenant = '00000000-0000-0000-0000-000000000000'::uuid
               OR a.tenant_id = p_tenant)
          AND (p_accion = '' OR a.accion = p_accion)
          AND a.creado_en >= p_desde AND a.creado_en < p_hasta
          AND (a.creado_en, a.id) < (p_cursor_fecha, p_cursor_id)
        ORDER BY a.creado_en DESC, a.id DESC
        LIMIT LEAST(GREATEST(p_limite, 1), {LIMITE_MAX});
    {_CLEAR}
    RETURN;
END
$fn$
"""  # noqa: S608 - solo constantes del módulo

CREATE_STATEMENTS = (CREATE_LISTAR,)

_ROLE_EXISTS = text("select exists (select 1 from pg_roles where rolname = :name)")
_ROLE_SKIPS_RLS = text("select rolsuper or rolbypassrls from pg_roles where rolname = :name")
_ROLE_UNSAFE = text(
    "select coalesce((select r.rolsuper or r.rolbypassrls or r.rolcanlogin or r.rolcreaterole "
    "or r.rolcreatedb or r.rolreplication "
    "or exists (select 1 from pg_auth_members m where m.member = r.oid) "
    "from pg_roles r where r.rolname = :name), true)"
)
_IS_MEMBER = text("select pg_has_role(:member, :owner, 'MEMBER')")
# Igual que 0004/0018/0027 (C8): por rolname exacto; la membresía ADMIN del creador en
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
            "La migración 0028 exige PostgreSQL 16 o superior (membresía transitoria "
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
            "Tras la migración 0028, el rol dueño de las funciones de plataforma conserva "
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
                f"La migración 0028 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def _owner_policies(owner: str) -> list[str]:
    return [
        f"CREATE POLICY dueno_plat_auditoria_actividad ON plataforma_auditoria FOR SELECT "
        f"TO {owner} USING ({ACTIVIDAD_ACTIVO})",
        f"CREATE POLICY dueno_plat_tenant_actividad ON tenant FOR SELECT TO {owner} "
        f"USING ({ACTIVIDAD_ACTIVO})",
        # Sin EXISTS sobre desarrollador (recursión); la función ya comprobó el activo.
        f"CREATE POLICY dueno_plat_desarrollador_actividad ON desarrollador FOR SELECT "
        f"TO {owner} USING ({ACTIVIDAD} IS NOT NULL)",
    ]


_AUDITORIA_COLUMNS = "id, desarrollador_id, accion, resultado, tenant_id, objeto_id, creado_en"


def _owner_grants(owner: str) -> list[str]:
    # Mínimos y por columna; nunca DELETE, UPDATE, password_hash ni datos de negocio.
    return [
        f"GRANT SELECT ({_AUDITORIA_COLUMNS}) ON plataforma_auditoria TO {owner}",
        f"GRANT SELECT (nombre) ON desarrollador TO {owner}",
    ]


def _owner_revokes(owner: str) -> list[str]:
    # Exactamente lo de _owner_grants (lo de 0017 sobre las dos tablas se conserva).
    return [
        f"REVOKE SELECT ({_AUDITORIA_COLUMNS}) ON plataforma_auditoria FROM {owner}",  # noqa: S608
        f"REVOKE SELECT (nombre) ON desarrollador FROM {owner}",  # noqa: S608
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
    # Solo el dueño (plataforma_owner) puede borrar su función: SET LOCAL ROLE.
    statements = [*opening, f"SET LOCAL ROLE {owner}"]
    statements += [f"DROP FUNCTION {fn}" for fn in FUNCTIONS]
    statements += ["RESET ROLE", *closing]
    statements += [f"DROP POLICY {policy} ON {table}" for table, policy in POLICIES]
    statements += _owner_revokes(owner)
    execute_statements(conn, statements)
    require_no_leftover_privileges(conn)
