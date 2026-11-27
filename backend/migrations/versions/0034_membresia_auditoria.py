"""Registro de auditoría de los cambios de rol y activación de la empresa (spec usuarios).

Cada cambio que hace ``acceso.cambiar_membresia`` (0033) deja una fila en
``public.membresia_auditoria``, en la misma transacción que el cambio:

- ``rol_cambiado``: el rol pasó de ``rol_anterior`` a ``rol_nuevo``.
- ``usuario_desactivado`` / ``usuario_reactivado``: solo ``activa`` cambió (sin roles).

Solo guarda ids (empresa, quien cambia, persona afectada), la acción, los roles y la hora.
No guarda nombres, correos ni contraseñas: la auditoría no expone datos personales.

- ``membresia_auditoria``: RLS habilitada y forzada. La aplicación solo puede ``SELECT`` las
  filas de su empresa (``tenant_isolation``, patrón de 0002). ``auth_owner`` solo puede
  ``INSERT`` (por la función). Nadie tiene ``UPDATE`` ni ``DELETE``: la tabla es inmutable
  para la aplicación y para ``auth_owner``. Sin política ``PUBLIC`` ni ``FOR ALL``.
- ``acceso.cambiar_membresia``: se reemplaza (``CREATE OR REPLACE``) por el cuerpo de 0033 más
  los ``INSERT`` de auditoría, después del ``UPDATE`` y de la revocación de refresh. Todo lo
  demás queda igual (candados, GUC, errores, ``SET search_path``, ``lock_timeout``,
  ``SECURITY DEFINER``, dueña ``auth_owner``, ``EXECUTE`` solo para la aplicación).

``downgrade``: restaura el cuerpo de 0033, borra las políticas, los ``GRANT`` y la tabla. Al
borrar la tabla se pierde el historial de auditoría: el downgrade no conserva datos.

Revision ID: 0034_membresia_auditoria
Revises: 0033_usuarios_cambiar_membresia
Create Date: 2026-11-25
"""

import importlib.util
from collections.abc import Sequence
from pathlib import Path

from alembic import op
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0034_membresia_auditoria"
down_revision: str | Sequence[str] | None = "0033_usuarios_cambiar_membresia"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "membresia_auditoria"
# Columnas que escribe la función (id y creado_en las pone el DEFAULT).
INSERT_COLUMNS = (
    "tenant_id",
    "actor_usuario_id",
    "usuario_id",
    "accion",
    "rol_anterior",
    "rol_nuevo",
)
ACCIONES = ("rol_cambiado", "usuario_desactivado", "usuario_reactivado")
ROLES = ("admin", "contador")
# Política de la aplicación: el tenant de la GUC app.tenant_id (mismo texto que 0002).
APP_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"

# 0033 se carga por ruta: su nombre empieza por dígito y no es importable como módulo.
_MIGRATION_0033 = Path(__file__).with_name("0033_usuarios_cambiar_membresia.py")
_spec = importlib.util.spec_from_file_location("migration_0033_for_0034", _MIGRATION_0033)
if _spec is None or _spec.loader is None:
    raise RuntimeError("No se pudo cargar la migración 0033 (cambio de membresía).")
_m33 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_m33)

AUTH_OWNER = _m33.AUTH_OWNER
FUNCTION = _m33.FUNCTION
SUPABASE_ROLES = _m33.SUPABASE_ROLES
TENANT_GUC = _m33.TENANT_GUC
TENANT = _m33.TENANT


# Dos INSERT de auditoría tras la revocación: uno por cambio de rol y otro por activación.
# Solo constantes del módulo: no hay entrada de usuario en el SQL.
_AUDITORIA = f"""    IF v_rol <> p_rol THEN
        INSERT INTO public.{TABLE} ({", ".join(INSERT_COLUMNS)})
            VALUES (p_tenant, p_actor, p_usuario, 'rol_cambiado', v_rol, p_rol);
    END IF;
    IF v_activa <> p_activa THEN
        INSERT INTO public.{TABLE} ({", ".join(INSERT_COLUMNS)})
            VALUES (p_tenant, p_actor, p_usuario,
                    CASE WHEN p_activa THEN 'usuario_reactivado' ELSE 'usuario_desactivado' END,
                    NULL, NULL);
    END IF;
"""  # noqa: S608 - solo constantes del módulo

# Cuerpo de 0033 con la auditoría insertada antes del último ``_CLEAR``. El test de
# migraciones comprueba que quitar ``_AUDITORIA`` da exactamente el de 0033.
CREATE_FUNCTION = f"""
CREATE OR REPLACE FUNCTION acceso.cambiar_membresia(
    p_tenant uuid, p_actor uuid, p_usuario uuid, p_rol text, p_activa boolean)
RETURNS TABLE (rol_resultado text, activa_resultado boolean, cambiado boolean)
{_m33._HEADER}
SET lock_timeout = '{_m33.LOCK_TIMEOUT}'
AS $fn$
DECLARE
    v_membresia uuid;
    v_rol text;
    v_activa boolean;
    v_admins_otros bigint;
    v_pasada integer;
    v_revocados bigint;
BEGIN
    {_m33._CLEAR}
    PERFORM pg_catalog.set_config('{TENANT_GUC}', p_tenant::text, true);
    PERFORM pg_catalog.set_config('{_m33.USUARIO_GUC}', p_usuario::text, true);
    -- Mismo candado exclusivo por tenant que 0027 y 0031 (login y refresh lo toman compartido).
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended('plataforma_membresia:' || p_tenant::text, 0));
    PERFORM 1 FROM public.membresia AS m
        WHERE m.tenant_id = p_tenant AND m.usuario_id = p_actor
          AND m.rol = 'admin' AND m.activa;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = '42501', MESSAGE = 'no_autorizado';
    END IF;
    IF p_actor = p_usuario THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'cambio_propio_no_permitido';
    END IF;
    SELECT m.id, m.rol, m.activa INTO v_membresia, v_rol, v_activa
        FROM public.membresia AS m
        WHERE m.tenant_id = p_tenant AND m.usuario_id = p_usuario;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0002', MESSAGE = 'usuario_no_encontrado';
    END IF;
    IF v_rol = p_rol AND v_activa = p_activa THEN
        {_m33._CLEAR}
        RETURN QUERY SELECT v_rol, v_activa, false;
        RETURN;
    END IF;
    -- Quitar el rol admin o desactivar a un admin activo: debe quedar otro admin activo.
    -- Con la comprobación del actor (admin activo y distinto de quien cambia) esta guardia
    -- nunca se dispara hoy; se mantiene como defensa si esa regla cambia.
    IF v_rol = 'admin' AND v_activa AND NOT (p_rol = 'admin' AND p_activa) THEN
        SELECT pg_catalog.count(*) INTO v_admins_otros FROM public.membresia AS m
            WHERE m.tenant_id = p_tenant AND m.rol = 'admin' AND m.activa
              AND m.usuario_id <> p_usuario;
        IF v_admins_otros = 0 THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ultimo_admin';
        END IF;
    END IF;
    UPDATE public.membresia AS m SET rol = p_rol, activa = p_activa WHERE m.id = v_membresia;
    IF NOT p_activa OR p_rol <> v_rol THEN
        -- Se repite hasta que no afecte filas: cada pasada ve lo confirmado antes de
        -- empezar, así un sucesor insertado por una rotación que confirmó mientras se
        -- esperaba su candado se revoca en la pasada siguiente.
        FOR v_pasada IN 1..{_m33.REVOKE_MAX_PASSES} LOOP
            UPDATE public.refresh_token AS t SET revocado_en = pg_catalog.now()
                WHERE t.membresia_id = v_membresia AND t.revocado_en IS NULL;
            GET DIAGNOSTICS v_revocados = ROW_COUNT;
            EXIT WHEN v_revocados = 0;
        END LOOP;
        IF v_revocados <> 0 THEN
            -- Falla cerrado: no se cambia dejando una familia viva.
            RAISE EXCEPTION USING ERRCODE = '55P03', MESSAGE = 'membresia_ocupada';
        END IF;
    END IF;
{_AUDITORIA}    {_m33._CLEAR}
    RETURN QUERY SELECT p_rol, p_activa, true;
    RETURN;
EXCEPTION WHEN lock_not_available THEN
    RAISE EXCEPTION USING ERRCODE = '55P03', MESSAGE = 'membresia_ocupada';
END
$fn$
"""  # noqa: S608 - solo constantes del módulo

# Política de la aplicación: solo lectura de su empresa.
POLICY_APP = "tenant_isolation"
# Política del dueño de las funciones: solo INSERT, acotado a la GUC de la función.
POLICY_OWNER = "dueno_auditoria_insertar"

_ROLE_LEFTOVERS = (
    "Tras la migración 0034, el rol dueño de las funciones de acceso conserva CREATE "
    "en el esquema acceso o el rol migrador sigue siendo miembro de él: quítalo antes "
    "de migrar."
)


def _policies(app: str, owner: str) -> list[str]:
    return [
        f"CREATE POLICY {POLICY_APP} ON {TABLE} FOR SELECT TO {app} "  # noqa: S608
        f"USING (tenant_id = {APP_TENANT})",
        f"CREATE POLICY {POLICY_OWNER} ON {TABLE} FOR INSERT TO {owner} "  # noqa: S608
        f"WITH CHECK (tenant_id = {TENANT})",
    ]


def _create_table() -> list[str]:
    acciones = ", ".join(f"'{a}'" for a in ACCIONES)
    roles = ", ".join(f"'{r}'" for r in ROLES)
    return [
        f"""
        CREATE TABLE {TABLE} (
            id uuid NOT NULL DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenant (id),
            actor_usuario_id uuid NOT NULL,
            usuario_id uuid NOT NULL,
            accion text NOT NULL,
            rol_anterior text,
            rol_nuevo text,
            creado_en timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT {TABLE}_pkey PRIMARY KEY (id),
            CONSTRAINT {TABLE}_accion_check CHECK (accion IN ({acciones})),
            CONSTRAINT {TABLE}_rol_anterior_check CHECK
                (rol_anterior IS NULL OR rol_anterior IN ({roles})),
            CONSTRAINT {TABLE}_rol_nuevo_check CHECK
                (rol_nuevo IS NULL OR rol_nuevo IN ({roles})),
            CONSTRAINT {TABLE}_rol_cambiado_check CHECK (
                accion <> 'rol_cambiado'
                OR (rol_anterior IS NOT NULL AND rol_nuevo IS NOT NULL
                    AND rol_anterior <> rol_nuevo)),
            CONSTRAINT {TABLE}_sin_rol_check CHECK (
                accion = 'rol_cambiado' OR (rol_anterior IS NULL AND rol_nuevo IS NULL)),
            CONSTRAINT {TABLE}_actor_distinto_check CHECK (actor_usuario_id <> usuario_id),
            CONSTRAINT {TABLE}_actor_fkey FOREIGN KEY (tenant_id, actor_usuario_id)
                REFERENCES membresia (tenant_id, usuario_id),
            CONSTRAINT {TABLE}_usuario_fkey FOREIGN KEY (tenant_id, usuario_id)
                REFERENCES membresia (tenant_id, usuario_id)
        )
        """,
        f"CREATE INDEX {TABLE}_tenant_creado_idx ON {TABLE} (tenant_id, creado_en DESC)",
    ]


def _require_no_leftovers(conn: Connection) -> None:
    """Al terminar, ``auth_owner`` sin ``CREATE`` en ``acceso`` y el migrador no es miembro."""
    if conn.scalar(_m33._OWNER_CAN_CREATE, {"owner": AUTH_OWNER}) or conn.scalar(
        _m33._MIGRATOR_IS_MEMBER, {"owner": AUTH_OWNER}
    ):
        raise RuntimeError(_ROLE_LEFTOVERS)


def _execute(conn: Connection, statements: Sequence[str]) -> None:
    """Ejecuta DDL tal cual, sin parámetros, y falla sin mostrar la sentencia."""
    for index, statement in enumerate(statements, start=1):
        failure = None
        try:
            conn.exec_driver_sql(statement, execution_options={"no_parameters": True})
        except SQLAlchemyError as exc:
            sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None) or "desconocido"
            failure = (
                f"La migración 0034 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def _roles(conn: Connection) -> tuple[str, str, str]:
    return _m33._roles(conn)


def upgrade() -> None:
    conn = op.get_bind()
    app, owner, migrator = _roles(conn)
    quote = conn.dialect.identifier_preparer.quote
    revoked = ["PUBLIC"] + [
        quote(role) for role in SUPABASE_ROLES if conn.scalar(_m33._ROLE_EXISTS, {"name": role})
    ]
    opening, closing = _m33._transient_membership(owner, migrator)
    statements = [
        *_create_table(),
        f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY",
        *_policies(app, owner),
        # Inmutable: sin UPDATE ni DELETE para nadie; la app solo lee, el dueño solo inserta.
        f"REVOKE ALL ON {TABLE} FROM {', '.join(revoked)}",
        f"GRANT SELECT ON {TABLE} TO {app}",
        f"GRANT INSERT ({', '.join(INSERT_COLUMNS)}) ON {TABLE} TO {owner}",
        # CREATE OR REPLACE necesita CREATE en el esquema; igual que 0024 (transitorio).
        f"GRANT CREATE ON SCHEMA acceso TO {owner}",
        *opening,
        f"SET LOCAL ROLE {owner}",
        CREATE_FUNCTION,
        "RESET ROLE",
        f"REVOKE CREATE ON SCHEMA acceso FROM {owner}",
        *closing,
    ]
    _execute(conn, statements)
    _require_no_leftovers(conn)


def downgrade() -> None:
    conn = op.get_bind()
    _app, owner, migrator = _roles(conn)
    opening, closing = _m33._transient_membership(owner, migrator)
    # Vuelve el cuerpo exacto de 0033 (sin INSERT de auditoría) como dueño.
    restored = _m33.CREATE_FUNCTION.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)
    statements = [
        f"GRANT CREATE ON SCHEMA acceso TO {owner}",
        *opening,
        f"SET LOCAL ROLE {owner}",
        restored,
        "RESET ROLE",
        f"REVOKE CREATE ON SCHEMA acceso FROM {owner}",
        *closing,
    ]
    statements += [f"DROP POLICY {POLICY_OWNER} ON {TABLE}", f"DROP POLICY {POLICY_APP} ON {TABLE}"]
    statements += [f"DROP TABLE {TABLE}"]
    _execute(conn, statements)
    _require_no_leftovers(conn)
