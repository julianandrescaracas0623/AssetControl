"""Función del logo en el alta de la consola (spec 017, T7).

``plan.md`` §2.3 y §5 (la fila ``0022_plataforma_logo``). El nombre previsto en el plan,
``0022_plataforma_logo``, no se usa (0019–0022 quedan sin usar): la migración real es esta,
``0029_plataforma_logo``, y la cadena sigue tras ``0028``. ``spec.md`` R23, R24, R33, R36;
A4, A5, A19; CU-04. Mismo patrón que 0018, 0027 y 0028.

Función nueva (``plpgsql``, ``SECURITY DEFINER``, ``STRICT``, ``SET search_path =
pg_catalog, pg_temp``, todo calificado, SQL estático, dueña ``plataforma_owner``,
``EXECUTE`` solo para el rol de la aplicación). Vacía al empezar y al terminar **todas**
las GUC ``app.plat_*`` (las catorce de 0017, 0018, 0027 y 0028 y las dos de aquí), fija
solo las suyas con valores que ella recibe y nunca lee una GUC. Su primera comprobación
(A5, R36): ``p_desarrollador`` existe y está activo; si no, ``42501
desarrollador_no_autorizado`` sin escribir nada.

- ``acceso.plataforma_registrar_logo(p_desarrollador, p_tenant, p_logo, p_clave, p_bytes,
  p_ancho, p_alto)`` -> ``logo_id``, ``creado`` (R23). El archivo lo procesa Flask (reglas
  de la 013) y lo guarda **después** de que la función confirme ``creado``; si la
  transacción no se confirma, Flask lo borra. Aquí: si la empresa no tiene logo,
  ``INSERT empresa_logo`` (``subido_por`` = el admin de la empresa, ver abajo) y ``UPDATE
  empresa`` de ``logo_id`` y ``actualizada_en``, en la transacción de quien llama.
  Rechazos, en este orden y sin escribir: clave distinta de ``<tenant>/<logo>.png``
  -> ``22023 clave_invalida``; empresa inexistente -> ``P0002 empresa_no_encontrada``;
  tenant sin ficha ``empresa`` -> ``P0001 empresa_sin_datos`` (como la 013); la empresa
  ya tiene **este** logo -> ``creado = false`` (idempotente, sin escribir); ya tiene otro
  -> ``P0001 logo_existente``; sin ninguna membresía ``admin`` -> ``P0001
  empresa_sin_admin``; el ``id`` ya se usó en ``empresa_logo`` (de esta u otra empresa) ->
  ``23505 logo_id_en_uso`` (como la 013), salvo que sea el vigente tras esperar a otra
  subida igual (idempotente). Si otra transacción fijó un logo mientras tanto (p. ej. el
  admin desde su pantalla), el ``UPDATE`` no afecta filas -> ``P0001 logo_existente``.
  ``lock_timeout`` acotado (``LOCK_TIMEOUT``): la fila de ``empresa`` bloqueada por otra
  transacción más allá de ese tiempo -> ``55P03 empresa_ocupada`` (503 en la API).

  ``subido_por`` (plan §2.3: «la única membresía admin activa más antigua»): ni
  ``membresia`` ni ``usuario`` tienen fecha (ver T5), así que se elige la membresía
  ``admin`` del tenant con ``activa`` primero y, a igualdad, el menor ``usuario_id``. En
  el alta normal hay exactamente una: el primer admin creado con la empresa. Si hay
  varias, la elección es determinista pero no «la más antigua» (pregunta abierta en
  ``tasks.md``).

La auditoría (``empresa_logo_subido``) la escribe la aplicación en la misma transacción;
la política de 0018 ya admite esa acción con ``tenant_id``.

Políticas ``TO plataforma_owner`` (una por comando, nunca ``FOR ALL`` ni ``PUBLIC``; GUC
validadas por formato: vacía o con otro formato -> ``NULL`` -> cero filas), todas con el
desarrollador de ``app.plat_actor`` activo:

- ``tenant`` y ``membresia`` ``FOR SELECT`` del tenant de ``app.plat_logo_tenant``;
- ``empresa`` ``FOR SELECT`` de esa fila y ``FOR UPDATE`` solo si aún no tiene logo, con
  ``WITH CHECK`` que deja ``logo_id`` = ``app.plat_logo_id`` y ``actualizada_en = now()``;
- ``empresa_logo`` ``FOR INSERT`` con ``id`` = ``app.plat_logo_id``, ese tenant, la clave
  ``<tenant>/<logo>.png`` y ``subido_por`` de una membresía ``admin`` del tenant.

``GRANT`` por columna mínimos, sin ``DELETE`` ni ``SELECT`` nuevos: ``empresa`` ``UPDATE
(logo_id, actualizada_en)`` (el ``SELECT`` sigue siendo solo ``tenant_id`` y ``logo_id`` de
0018: el desarrollador no lee la ficha, A19) y ``empresa_logo`` ``INSERT (id, tenant_id,
clave, bytes, ancho, alto, subido_por)`` (ningún ``SELECT``: no lee logos).

Orden (C3/C5): políticas y ``GRANT`` -> ``CREATE FUNCTION`` -> ``REVOKE ALL`` de
``PUBLIC`` y de los roles de Supabase -> ``GRANT EXECUTE`` a la aplicación -> ``CREATE``
transitorio en ``acceso`` y membresía transitoria ``WITH INHERIT FALSE, SET TRUE`` ->
``OWNER TO plataforma_owner`` -> ``REVOKE CREATE`` y fin de la membresía; al terminar se
comprueba que no quede nada (C8).

``downgrade``: borra la función como ``plataforma_owner``, sus políticas y solo los
``GRANT`` de aquí. No borra datos: los logos subidos siguen en ``empresa_logo`` y en
``empresa.logo_id``.

Revision ID: 0029_plataforma_logo
Revises: 0028_plataforma_actividad
Create Date: 2026-11-21
"""

import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0029_plataforma_logo"
down_revision: str | Sequence[str] | None = "0028_plataforma_actividad"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE_VAR = "APP_DB_USER"
AUTH_OWNER = "auth_owner"
PLATAFORMA_OWNER = "plataforma_owner"
SUPABASE_ROLES = ("anon", "authenticated", "service_role")

REGISTRAR = "acceso.plataforma_registrar_logo(uuid, uuid, uuid, text, integer, integer, integer)"
FUNCTIONS = (REGISTRAR,)

# Todas las GUC de las políticas de plataforma_owner (0017, 0018, 0027, 0028 y esta).
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
    "app.plat_logo_tenant",
    "app.plat_logo_id",
)

# (tabla, política): lista cerrada (la fijan test_plataforma_catalogo.py y test_migrations.py).
POLICIES = (
    ("tenant", "dueno_plat_tenant_logo"),
    ("membresia", "dueno_plat_membresia_logo"),
    ("empresa", "dueno_plat_empresa_logo_leer"),
    ("empresa", "dueno_plat_empresa_logo"),
    ("empresa_logo", "dueno_plat_empresa_logo_crear"),
)

# Espera máxima de la fila de empresa (la puede tener el admin cambiando su logo): pasado
# este tiempo, ``55P03 empresa_ocupada`` (503 en la API), como 0027.
LOCK_TIMEOUT = "5s"

_UUID = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def uuid_setting(guc: str) -> str:
    """UUID de ``guc``; ``NULL`` si falta o no es un UUID en minúsculas (como 0018)."""
    value = f"pg_catalog.current_setting('{guc}', true)"
    return f"(CASE WHEN {value} ~ '{_UUID}' THEN ({value})::uuid END)"


ACTOR = uuid_setting("app.plat_actor")
LOGO_TENANT = uuid_setting("app.plat_logo_tenant")
LOGO_ID = uuid_setting("app.plat_logo_id")
ACTOR_ACTIVO = f"EXISTS (SELECT 1 FROM desarrollador d WHERE d.id = {ACTOR} AND d.activo)"  # noqa: S608
# subido_por: una membresía admin del tenant (la FK de 0014 solo exige una membresía).
_SUBIDO_POR_ADMIN = (
    "EXISTS (SELECT 1 FROM membresia m WHERE m.tenant_id = empresa_logo.tenant_id "  # noqa: S608
    "AND m.usuario_id = empresa_logo.subido_por AND m.rol = 'admin')"
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

CREATE_REGISTRAR = f"""
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
    {_CLEAR}
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
            {_CLEAR}
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
            {_CLEAR}
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
    {_CLEAR}
    RETURN QUERY SELECT p_logo, true;
    RETURN;
EXCEPTION WHEN lock_not_available THEN
    RAISE EXCEPTION USING ERRCODE = '55P03', MESSAGE = 'empresa_ocupada';
END
$fn$
"""  # noqa: S608 - solo constantes del módulo

CREATE_STATEMENTS = (CREATE_REGISTRAR,)

_ROLE_EXISTS = text("select exists (select 1 from pg_roles where rolname = :name)")
_ROLE_SKIPS_RLS = text("select rolsuper or rolbypassrls from pg_roles where rolname = :name")
_ROLE_UNSAFE = text(
    "select coalesce((select r.rolsuper or r.rolbypassrls or r.rolcanlogin or r.rolcreaterole "
    "or r.rolcreatedb or r.rolreplication "
    "or exists (select 1 from pg_auth_members m where m.member = r.oid) "
    "from pg_roles r where r.rolname = :name), true)"
)
_IS_MEMBER = text("select pg_has_role(:member, :owner, 'MEMBER')")
# Igual que 0004/0018/0027/0028 (C8): por rolname exacto; la membresía ADMIN del creador en
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
            "La migración 0029 exige PostgreSQL 16 o superior (membresía transitoria "
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
            "Tras la migración 0029, el rol dueño de las funciones de plataforma conserva "
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
                f"La migración 0029 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def _owner_policies(owner: str) -> list[str]:
    clave = "clave = (tenant_id::text || '/' || id::text || '.png')"
    return [
        f"CREATE POLICY dueno_plat_tenant_logo ON tenant FOR SELECT TO {owner} "
        f"USING (id = {LOGO_TENANT} AND {ACTOR_ACTIVO})",
        f"CREATE POLICY dueno_plat_membresia_logo ON membresia FOR SELECT TO {owner} "
        f"USING (tenant_id = {LOGO_TENANT} AND {ACTOR_ACTIVO})",
        f"CREATE POLICY dueno_plat_empresa_logo_leer ON empresa FOR SELECT TO {owner} "
        f"USING (tenant_id = {LOGO_TENANT} AND {ACTOR_ACTIVO})",
        # Solo una empresa sin logo, y solo para dejarle el de esta subida.
        f"CREATE POLICY dueno_plat_empresa_logo ON empresa FOR UPDATE TO {owner} "
        f"USING (tenant_id = {LOGO_TENANT} AND logo_id IS NULL AND {ACTOR_ACTIVO}) "
        f"WITH CHECK (tenant_id = {LOGO_TENANT} AND logo_id = {LOGO_ID} "
        "AND actualizada_en = now())",
        f"CREATE POLICY dueno_plat_empresa_logo_crear ON empresa_logo FOR INSERT TO {owner} "
        f"WITH CHECK (id = {LOGO_ID} AND tenant_id = {LOGO_TENANT} AND {clave} "
        f"AND {_SUBIDO_POR_ADMIN} AND {ACTOR_ACTIVO})",
    ]


_LOGO_INSERT = "id, tenant_id, clave, bytes, ancho, alto, subido_por"


def _owner_grants(owner: str) -> list[str]:
    # Mínimos y por columna; nunca DELETE ni SELECT de la ficha o de los logos (A19).
    return [
        f"GRANT UPDATE (logo_id, actualizada_en) ON empresa TO {owner}",
        f"GRANT INSERT ({_LOGO_INSERT}) ON empresa_logo TO {owner}",
    ]


def _owner_revokes(owner: str) -> list[str]:
    # Exactamente lo de _owner_grants (lo de 0018 sobre empresa se conserva).
    return [
        f"REVOKE UPDATE (logo_id, actualizada_en) ON empresa FROM {owner}",
        f"REVOKE INSERT ({_LOGO_INSERT}) ON empresa_logo FROM {owner}",
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
