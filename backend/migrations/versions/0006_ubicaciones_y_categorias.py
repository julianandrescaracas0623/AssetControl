"""Tablas ``ubicacion`` y ``categoria`` (spec 003, T1; R1–R4, Q1–Q3; plan.md §2).

- ``ubicacion``: jerarquía estricta sede > sala > box (Q1). ``CHECK`` de que solo la
  sede no tiene padre; el tipo del padre lo exige la aplicación con el padre
  bloqueado. FK compuesta ``(tenant_id, padre_id) -> (tenant_id, id)``: el padre es
  siempre del mismo tenant. Únicos parciales por ``nombre_clave`` entre hermanas
  (los ``NULL`` no chocan en un ``UNIQUE``, así que las sedes tienen su propio índice).
- ``categoria``: ``UNIQUE (tenant_id, nombre_clave)`` (Q3) y ``UNIQUE (tenant_id, id)``
  para las FK compuestas de ``activo`` (spec 004).
- ``nombre`` de 1 a 120 caracteres (regla H-3 de la spec 002; la aplicación normaliza).
  ``nombre_clave`` la calcula la aplicación (sin tildes ni mayúsculas); la base solo
  hace cumplir su unicidad.
- RLS habilitada y forzada; ``tenant_isolation`` ``TO`` el rol de la aplicación con
  ``USING`` y ``WITH CHECK`` sobre ``app.tenant_id`` (patrón de 0002). ``GRANT``
  mínimos por columna: el ``tenant_id``, el ``tipo`` y el ``padre_id`` no se
  actualizan; **sin ``DELETE`` ni ``TRUNCATE``** (nada se borra físicamente).

El rol de la aplicación se lee de ``APP_DB_USER`` (como 0002–0005) y nunca aparece en
los mensajes. ``downgrade`` borra ambas tablas (y con ellas sus políticas y ``GRANT``).

Revision ID: 0006_ubicaciones_y_categorias
Revises: 0005_limite_tasa
Create Date: 2026-11-14
"""

import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0006_ubicaciones_y_categorias"
down_revision: str | Sequence[str] | None = "0005_limite_tasa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE_VAR = "APP_DB_USER"
AUTH_OWNER = "auth_owner"
SUPABASE_ROLES = ("anon", "authenticated", "service_role")
TABLES = ("ubicacion", "categoria")
TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
NOMBRE_CHECK = "CHECK (char_length(nombre) BETWEEN 1 AND 120)"

_ROLE_EXISTS = text("select exists (select 1 from pg_roles where rolname = :name)")
_ROLE_SKIPS_RLS = text("select rolsuper or rolbypassrls from pg_roles where rolname = :name")


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
                f"La migración 0006 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def upgrade() -> None:
    conn = op.get_bind()
    quote = conn.dialect.identifier_preparer.quote
    app = quote(_app_role(conn))

    statements = [
        f"""
        CREATE TABLE ubicacion (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenant (id),
            nombre text NOT NULL {NOMBRE_CHECK},
            nombre_clave text NOT NULL CHECK (char_length(nombre_clave) BETWEEN 1 AND 120),
            tipo text NOT NULL CHECK (tipo IN ('sede', 'sala', 'box')),
            padre_id uuid NULL,
            activa boolean NOT NULL DEFAULT true,
            creado_en timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ubicacion_tenant_id_key UNIQUE (tenant_id, id),
            CONSTRAINT ubicacion_padre_fkey FOREIGN KEY (tenant_id, padre_id)
                REFERENCES ubicacion (tenant_id, id) MATCH SIMPLE,
            CONSTRAINT ubicacion_solo_sede_sin_padre CHECK ((tipo = 'sede') = (padre_id IS NULL))
        )
        """,
        "CREATE UNIQUE INDEX ubicacion_sede_nombre_key ON ubicacion (tenant_id, nombre_clave) "
        "WHERE padre_id IS NULL",
        "CREATE UNIQUE INDEX ubicacion_hija_nombre_key ON ubicacion "
        "(tenant_id, padre_id, nombre_clave) WHERE padre_id IS NOT NULL",
        f"""
        CREATE TABLE categoria (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenant (id),
            nombre text NOT NULL {NOMBRE_CHECK},
            nombre_clave text NOT NULL CHECK (char_length(nombre_clave) BETWEEN 1 AND 120),
            creado_en timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT categoria_tenant_id_key UNIQUE (tenant_id, id),
            CONSTRAINT categoria_nombre_key UNIQUE (tenant_id, nombre_clave)
        )
        """,
    ]
    for table in TABLES:
        statements += [
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
            f"CREATE POLICY tenant_isolation ON {table} TO {app} "
            f"USING (tenant_id = {TENANT}) WITH CHECK (tenant_id = {TENANT})",
        ]

    # --- GRANT mínimos; nunca DELETE ni TRUNCATE para la aplicación ---
    statements += [
        f"REVOKE ALL ON {', '.join(TABLES)} FROM PUBLIC",
        f"GRANT SELECT ON ubicacion TO {app}",
        f"GRANT INSERT (tenant_id, nombre, nombre_clave, tipo, padre_id) ON ubicacion TO {app}",
        f"GRANT UPDATE (nombre, nombre_clave, activa) ON ubicacion TO {app}",
        f"GRANT SELECT ON categoria TO {app}",
        f"GRANT INSERT (tenant_id, nombre, nombre_clave) ON categoria TO {app}",
        f"GRANT UPDATE (nombre, nombre_clave) ON categoria TO {app}",
    ]
    for role in SUPABASE_ROLES:
        if conn.scalar(_ROLE_EXISTS, {"name": role}):
            statements.append(f"REVOKE ALL ON {', '.join(TABLES)} FROM {quote(role)}")
    execute_statements(conn, statements)


def downgrade() -> None:
    # DROP TABLE elimina también sus índices, políticas y GRANT.
    execute_statements(op.get_bind(), ["DROP TABLE categoria", "DROP TABLE ubicacion"])
