"""Tabla ``recuperacion_contrasena`` y ámbitos nuevos de ``limite_tasa`` (spec 014, T1).

``plan.md`` §3.1 y §3.2; ``docs/03`` (cambios 1–2); ``spec.md`` R3, R4, R12, R15:

- ``recuperacion_contrasena``: enlace de un solo uso para fijar una contraseña nueva.
  Guarda ``sha256(clave)`` (``bytea`` de 32 bytes, ``UNIQUE``), vence como máximo 30
  minutos después de creado y ``usada_en``/``invalidada_en`` son excluyentes. Lleva
  ``tenant_id`` (el de la única membresía activa del usuario) con FK compuesta
  ``(tenant_id, usuario_id)`` → ``membresia``. Un **índice único parcial** sobre
  ``usuario_id`` deja como máximo un enlace vivo por usuario (parcial porque los NULL
  no chocan en un ``UNIQUE`` normal); también sirve a la invalidación por usuario.
- RLS habilitada y forzada con ``tenant_isolation`` ``TO`` el rol de la aplicación (el
  mismo patrón R2 de 002: ``USING`` y ``WITH CHECK``, sin políticas ``PUBLIC`` ni
  ``FOR ALL`` auxiliares). **Ningún privilegio** para la aplicación (ni ``SELECT``): la
  política existe por catálogo y defensa en profundidad. ``REVOKE ALL`` a ``PUBLIC``, a
  la aplicación (por si un privilegio por defecto se lo diera) y a los roles de
  Supabase. Sin ``DELETE`` para nadie: los enlaces se conservan marcados.
- ``limite_tasa``: el ``CHECK`` de ``ambito`` se reemplaza (mismo nombre,
  ``limite_tasa_ambito_check``) añadiendo ``recuperar_ip``, ``recuperar_cuenta`` y
  ``restablecer_ip``. El nombre actual se lee del catálogo.

Las funciones ``acceso.*`` y las políticas de ``auth_owner`` son de ``0016`` (T2).

``downgrade``: borra la tabla y restaura el ``CHECK`` anterior. Antes borra los
contadores de los tres ámbitos nuevos (solo infraestructura: HMAC y contadores, sin
datos de negocio; recomendación de ``plan.md`` §3.2). Si el migrador no es
superusuario, la RLS de la purga solo le deja borrar ventanas de más de un día: si
quedan contadores recientes, el ``downgrade`` falla con un mensaje claro.

Revision ID: 0015_recuperacion_contrasena
Revises: 0014_empresa_y_detalle
Create Date: 2026-11-19
"""

import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0015_recuperacion_contrasena"
down_revision: str | Sequence[str] | None = "0014_empresa_y_detalle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUPABASE_ROLES = ("anon", "authenticated", "service_role")
TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
APP_ROLE_VAR = "APP_DB_USER"
AUTH_OWNER = "auth_owner"
TABLE = "recuperacion_contrasena"
SCOPE_CHECK = "limite_tasa_ambito_check"
OLD_SCOPES = ("login_ip", "login_cuenta", "refresh_ip", "validar_ip", "aceptar_ip")
NEW_SCOPES = ("recuperar_ip", "recuperar_cuenta", "restablecer_ip")

_ROLE_EXISTS = text("select exists (select 1 from pg_roles where rolname = :name)")
_ROLE_SKIPS_RLS = text("select rolsuper or rolbypassrls from pg_roles where rolname = :name")
# CHECK de limite_tasa que solo mira la columna ambito (creado en línea por 0005).
_SCOPE_CHECKS = text(
    "select c.conname from pg_constraint c "
    "join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any(c.conkey) "
    "where c.conrelid = 'public.limite_tasa'::regclass and c.contype = 'c' "
    "and a.attname = 'ambito' and array_length(c.conkey, 1) = 1"
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
    return name


def execute_statements(conn: Connection, statements: Sequence[str]) -> None:
    """Ejecuta DDL tal cual, sin parámetros, y falla sin mostrar la sentencia."""
    for index, statement in enumerate(statements, start=1):
        failure = None
        try:
            conn.exec_driver_sql(statement, execution_options={"no_parameters": True})
        except SQLAlchemyError as exc:
            sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None) or "desconocido"
            failure = (
                f"La migración 0015 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def _scope_check_name(conn: Connection) -> str:
    """Nombre del único ``CHECK`` de ``ambito`` de ``limite_tasa``, leído del catálogo."""
    names = list(conn.scalars(_SCOPE_CHECKS))
    if len(names) != 1:
        raise RuntimeError(
            "La migración 0015 esperaba exactamente un CHECK sobre limite_tasa.ambito "
            f"y encontró {len(names)}: revisa el esquema antes de migrar."
        )
    return names[0]


def _scope_check(scopes: Sequence[str]) -> str:
    values = ", ".join(f"'{scope}'" for scope in scopes)
    return f"ALTER TABLE limite_tasa ADD CONSTRAINT {SCOPE_CHECK} CHECK (ambito IN ({values}))"


def upgrade() -> None:
    conn = op.get_bind()
    quote = conn.dialect.identifier_preparer.quote
    app = quote(_app_role(conn))
    current_check = quote(_scope_check_name(conn))
    statements = [
        f"""
        CREATE TABLE {TABLE} (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenant (id),
            usuario_id uuid NOT NULL,
            token_hash bytea NOT NULL,
            expira_en timestamptz NOT NULL,
            usada_en timestamptz NULL,
            invalidada_en timestamptz NULL,
            creado_en timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT {TABLE}_token_hash_32 CHECK (octet_length(token_hash) = 32),
            CONSTRAINT {TABLE}_token_hash_key UNIQUE (token_hash),
            CONSTRAINT {TABLE}_vence_en_30_min
                CHECK (expira_en <= creado_en + interval '30 minutes'),
            CONSTRAINT {TABLE}_usada_o_invalidada
                CHECK (usada_en IS NULL OR invalidada_en IS NULL),
            CONSTRAINT {TABLE}_membresia_fkey FOREIGN KEY (tenant_id, usuario_id)
                REFERENCES membresia (tenant_id, usuario_id)
        )
        """,
        # Un enlace vivo por usuario; también sirve a la invalidación por usuario_id.
        f"CREATE UNIQUE INDEX {TABLE}_pendiente_key ON {TABLE} (usuario_id) "
        "WHERE usada_en IS NULL AND invalidada_en IS NULL",
        f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY",
        f"CREATE POLICY tenant_isolation ON {TABLE} TO {app} "
        f"USING (tenant_id = {TENANT}) WITH CHECK (tenant_id = {TENANT})",
        # Ningún GRANT: ni la aplicación ni nadie más que el dueño (R15).
        f"REVOKE ALL ON {TABLE} FROM PUBLIC",
        f"REVOKE ALL ON {TABLE} FROM {app}",
        # limite_tasa: mismo CHECK con los tres ámbitos nuevos (plan.md §3.2).
        f"ALTER TABLE limite_tasa DROP CONSTRAINT {current_check}",
        _scope_check((*OLD_SCOPES, *NEW_SCOPES)),
    ]
    for role in SUPABASE_ROLES:
        if conn.scalar(_ROLE_EXISTS, {"name": role}):
            statements.append(f"REVOKE ALL ON {TABLE} FROM {quote(role)}")
    execute_statements(conn, statements)


def downgrade() -> None:
    conn = op.get_bind()
    current_check = conn.dialect.identifier_preparer.quote(_scope_check_name(conn))
    new_scopes = ", ".join(f"'{scope}'" for scope in NEW_SCOPES)
    execute_statements(
        conn,
        [
            f"DROP TABLE {TABLE}",
            # Solo contadores de los ámbitos nuevos: el CHECK anterior no los admite.
            # Constantes del módulo, no datos externos.
            f"DELETE FROM limite_tasa WHERE ambito IN ({new_scopes})",  # noqa: S608
            f"ALTER TABLE limite_tasa DROP CONSTRAINT {current_check}",
        ],
    )
    failure = None
    try:
        conn.exec_driver_sql(_scope_check(OLD_SCOPES), execution_options={"no_parameters": True})
    except SQLAlchemyError as exc:
        sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None) or "desconocido"
        failure = (
            "La migración 0015 no puede revertirse: quedan en limite_tasa contadores de "
            "recuperar_ip, recuperar_cuenta o restablecer_ip que el migrador no pudo borrar "
            "(sin superusuario, la RLS de la purga solo alcanza ventanas de más de un día). "
            f"Espera un día y ejecuta flask purgar-limite-tasa ({type(exc).__name__}, "
            f"SQLSTATE {sqlstate})."
        )
    if failure is not None:
        raise RuntimeError(failure) from None
