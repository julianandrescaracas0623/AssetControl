"""Políticas del dueño ``auth_owner`` y sus GRANT por columna (spec 002, T2; plan.md §2.1).

Las funciones ``SECURITY DEFINER`` de ``acceso`` (0004, T3) corren como
``auth_owner`` bajo ``FORCE ROW LEVEL SECURITY``: sin una política ``TO
auth_owner`` no ven ni escriben nada. Esta migración crea solo esas políticas,
una por comando (nunca ``FOR ALL``), todas ``TO auth_owner`` (nunca ``PUBLIC``),
cada una con la GUC propia de su función (I2, I3, I4):

=============  ========  ===========================  =================================
Tabla          Comando   GUC                          Para
=============  ========  ===========================  =================================
invitacion     SELECT    ``app.auth_inv_validar``     ``validar_invitacion``
invitacion     SELECT    ``app.auth_inv_aceptar``     ``aceptar_invitacion``
invitacion     UPDATE    ``app.auth_inv_aceptar``     consumir (``usada_en = now()``)
invitacion     INSERT    ``app.auth_tenant_nuevo``    ``crear_tenant`` (admin, ≤ 24 h,
                                                      tenant creado en esta transacción)
usuario        SELECT    ``app.auth_email``           ``buscar_login``
usuario        INSERT    ``app.auth_inv_aceptar``     email de la invitación recién usada
membresia      SELECT    ``app.auth_usuario``         ``buscar_login``
membresia      INSERT    ``app.auth_inv_aceptar`` y   tenant y rol de la invitación
                         ``app.auth_usuario_nuevo``   recién usada; usuario de la GUC
tenant         INSERT    ``app.auth_tenant_nuevo``    ``crear_tenant``
tenant         SELECT    ``app.auth_tenant_nuevo``    solo la fila creada en esta
                                                      transacción (``creado_en = now()``)
=============  ========  ===========================  =================================

- Las GUC se leen con ``current_setting(..., true)`` y se validan por formato
  antes de usarlas: clave hex minúscula de 64 caracteres o UUID en minúsculas.
  Vacía, nula, comodín (``%``, ``_``) o con otro formato -> ``NULL`` -> cero
  filas, nunca un error de conversión.
- La clave nunca se compara en claro: ``token_hash = sha256(decode(clave, 'hex'))``
  (doble hash, I1).
- "Recién consumida" es ``usada_en = now()``: ``now()`` es el inicio de la
  transacción, así que una invitación usada en otra transacción no sirve.
- La invitación de ``crear_tenant`` se liga a un tenant creado en la misma
  transacción (Q21, I2): ``auth_owner`` lee solo ``tenant (id, creado_en)`` y
  solo la fila con ``id`` de su GUC y ``creado_en = now()``; ``creado_en`` no
  está en su ``GRANT`` de ``INSERT`` (lo pone el ``DEFAULT now()``). Así, con el
  id de un tenant existente en la GUC no puede invitar un admin a ese tenant.
- ``GRANT`` por columna mínimos para ``auth_owner``; ninguno de ``DELETE`` ni
  ``TRUNCATE``; sin ``UPDATE`` en ``tenant`` y nada en ``refresh_token``.
  ``auth_owner`` no lee ``creada_por`` ni ``id`` de ``invitacion`` ni ``nombre``
  de ``usuario`` ni de ``tenant``, y no elige el ``id`` de ``membresia`` ni de
  ``invitacion`` (M3; lo pone el ``DEFAULT``).

Las políticas de la aplicación (0002) son ``TO`` el rol de la aplicación y no
afectan a ``auth_owner``; estas no afectan a la aplicación. Ninguna migración
crea roles: falla con mensaje claro si no existe ``auth_owner`` (P0), también
al bajar (M5), y si ``auth_owner`` es superusuario, tiene ``BYPASSRLS`` o
``LOGIN``, o es miembro de otro rol (I3).

Revision ID: 0003_politicas_del_dueno
Revises: 0002_acceso_y_usuarios
Create Date: 2026-11-12
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0003_politicas_del_dueno"
down_revision: str | Sequence[str] | None = "0002_acceso_y_usuarios"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AUTH_OWNER = "auth_owner"
OWNER_TABLES = ("tenant", "usuario", "membresia", "invitacion")

# (tabla, política): una lista cerrada (la fija T3 en el catálogo C6).
POLICIES = (
    ("invitacion", "dueno_invitacion_validar"),
    ("invitacion", "dueno_invitacion_aceptar"),
    ("invitacion", "dueno_invitacion_consumir"),
    ("invitacion", "dueno_invitacion_crear_tenant"),
    ("usuario", "dueno_usuario_login"),
    ("usuario", "dueno_usuario_aceptar"),
    ("membresia", "dueno_membresia_login"),
    ("membresia", "dueno_membresia_aceptar"),
    ("tenant", "dueno_tenant_crear"),
    ("tenant", "dueno_tenant_recien_creado"),
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


INV_VALIDAR = key_hash("app.auth_inv_validar")
INV_ACEPTAR = key_hash("app.auth_inv_aceptar")
EMAIL = text_setting("app.auth_email")
USUARIO = uuid_setting("app.auth_usuario")
USUARIO_NUEVO = uuid_setting("app.auth_usuario_nuevo")
TENANT_NUEVO = uuid_setting("app.auth_tenant_nuevo")

_ROLE_EXISTS = text("select exists (select 1 from pg_roles where rolname = :name)")
# Inseguro: se salta RLS, inicia sesión o hereda privilegios de otro rol.
_ROLE_UNSAFE = text(
    "select r.rolsuper or r.rolbypassrls or r.rolcanlogin "
    "or exists (select 1 from pg_auth_members m where m.member = r.oid) "
    "from pg_roles r where r.rolname = :name"
)


def require_auth_owner(conn: Connection, name: str | None = None) -> None:
    """Falla con un mensaje claro si no existe ``auth_owner`` (P0, plan.md §2.1)."""
    if not conn.scalar(_ROLE_EXISTS, {"name": name or AUTH_OWNER}):
        raise RuntimeError(
            f"Falta el rol {AUTH_OWNER}: créalo con docker/postgres/init/01-app-role.sh "
            "(spec 002, P0) antes de migrar."
        )


def require_owner_attributes(conn: Connection, name: str | None = None) -> None:
    """Falla si el dueño de las funciones de acceso no es un rol inerte (I3, R4a).

    El mensaje no lleva el nombre del rol: solo qué atributos se exigen.
    """
    if conn.scalar(_ROLE_UNSAFE, {"name": name or AUTH_OWNER}):
        raise RuntimeError(
            "El rol dueño de las funciones de acceso no es seguro: no puede ser "
            "SUPERUSER, tener BYPASSRLS ni LOGIN, ni tener membresía en otro rol. "
            "Corrígelo con docker/postgres/init/01-app-role.sh (spec 002, P0) antes de migrar."
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
                f"La migración 0003 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def upgrade() -> None:
    conn = op.get_bind()
    require_auth_owner(conn)
    require_owner_attributes(conn)
    owner = conn.dialect.identifier_preparer.quote(AUTH_OWNER)

    statements = [
        # --- invitacion ---
        f"CREATE POLICY dueno_invitacion_validar ON invitacion FOR SELECT TO {owner} "
        f"USING (token_hash = {INV_VALIDAR})",
        # aceptar_invitacion: lectura del UPDATE ... RETURNING y de las subconsultas
        # de las políticas de usuario y membresia.
        f"CREATE POLICY dueno_invitacion_aceptar ON invitacion FOR SELECT TO {owner} "
        f"USING (token_hash = {INV_ACEPTAR})",
        f"CREATE POLICY dueno_invitacion_consumir ON invitacion FOR UPDATE TO {owner} "
        f"USING (token_hash = {INV_ACEPTAR} AND usada_en IS NULL AND expira_en > now()) "
        "WITH CHECK (usada_en = now())",
        # Q21 (I2): solo para el tenant creado en esta misma transacción.
        f"CREATE POLICY dueno_invitacion_crear_tenant ON invitacion FOR INSERT TO {owner} "  # noqa: S608
        f"WITH CHECK (tenant_id = {TENANT_NUEVO} AND rol = 'admin' AND creada_por IS NULL "
        "AND usada_en IS NULL AND expira_en <= now() + interval '24 hours' "
        "AND EXISTS (SELECT 1 FROM tenant t "
        "WHERE t.id = invitacion.tenant_id AND t.creado_en = now()))",
        # --- usuario ---
        f"CREATE POLICY dueno_usuario_login ON usuario FOR SELECT TO {owner} "
        f"USING (email = {EMAIL})",
        # Solo constantes del módulo y el rol citado con identifier_preparer.quote.
        f"CREATE POLICY dueno_usuario_aceptar ON usuario FOR INSERT TO {owner} "  # noqa: S608
        "WITH CHECK (EXISTS (SELECT 1 FROM invitacion i "
        f"WHERE i.token_hash = {INV_ACEPTAR} AND i.usada_en = now() "
        "AND i.email = usuario.email))",
        # --- membresia ---
        f"CREATE POLICY dueno_membresia_login ON membresia FOR SELECT TO {owner} "
        f"USING (usuario_id = {USUARIO})",
        f"CREATE POLICY dueno_membresia_aceptar ON membresia FOR INSERT TO {owner} "  # noqa: S608
        f"WITH CHECK (usuario_id = {USUARIO_NUEVO} AND EXISTS (SELECT 1 FROM invitacion i "
        f"WHERE i.tenant_id = membresia.tenant_id AND i.token_hash = {INV_ACEPTAR} "
        "AND i.usada_en = now() AND i.rol = membresia.rol))",
        # --- tenant ---
        f"CREATE POLICY dueno_tenant_crear ON tenant FOR INSERT TO {owner} "
        f"WITH CHECK (id = {TENANT_NUEVO})",
        # Para el EXISTS de dueno_invitacion_crear_tenant: solo la fila recién creada.
        f"CREATE POLICY dueno_tenant_recien_creado ON tenant FOR SELECT TO {owner} "
        f"USING (id = {TENANT_NUEVO} AND creado_en = now())",
        # --- GRANT por columna mínimos; nunca DELETE ni TRUNCATE ---
        # creado_en nunca en INSERT: lo fija el DEFAULT now().
        f"GRANT INSERT (id, nombre) ON tenant TO {owner}",
        f"GRANT SELECT (id, creado_en) ON tenant TO {owner}",
        f"GRANT SELECT (id, email, password_hash, activo) ON usuario TO {owner}",
        f"GRANT INSERT (id, email, nombre, password_hash) ON usuario TO {owner}",
        f"GRANT SELECT (id, tenant_id, usuario_id, rol, activa) ON membresia TO {owner}",
        f"GRANT INSERT (tenant_id, usuario_id, rol) ON membresia TO {owner}",
        f"GRANT SELECT (tenant_id, email, rol, token_hash, expira_en, usada_en) "
        f"ON invitacion TO {owner}",
        f"GRANT UPDATE (usada_en) ON invitacion TO {owner}",
        f"GRANT INSERT (tenant_id, email, rol, token_hash, expira_en) ON invitacion TO {owner}",
    ]
    execute_statements(conn, statements)


def downgrade() -> None:
    conn = op.get_bind()
    require_auth_owner(conn)
    owner = conn.dialect.identifier_preparer.quote(AUTH_OWNER)
    statements = [f"DROP POLICY {policy} ON {table}" for table, policy in POLICIES]
    statements.append(f"REVOKE ALL ON {', '.join(OWNER_TABLES)} FROM {owner}")
    execute_statements(conn, statements)
