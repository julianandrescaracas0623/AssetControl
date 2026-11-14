"""Sesiones de conteo y verificaciones (spec 006, T1; R1, R4–R7, Q1, Q2; plan.md §2).

- ``sesion_conteo``: ``tipo`` ``conteo`` o ``importacion`` y ``estado`` ``abierta`` o
  ``cerrada`` (cerrada exige ``cerrada_en``). **Q1:** una sola sesión ``conteo``
  abierta por tenant (índice único parcial). Sin ``UPDATE`` para la aplicación hasta el
  cierre (008); la aplicación solo inserta sesiones ``conteo`` ``abiertas`` (los
  ``DEFAULT``).
- ``verificacion``: inmutable (solo ``INSERT`` y ``SELECT``); ``id`` del cliente (R2);
  copia ``precio_al_contar``, ``categoria_al_contar`` y ``ubicacion_esperada_id``
  (ADR-003); ``estado_fisico`` ``ok`` o ``danado`` (Q2); ``seq`` por identidad (R3).
- FK compuestas: todo del mismo tenant. ``activo_evento`` gana las FK de ``sesion_id`` y
  ``verificacion_id`` (sin FK desde la 0007).
- RLS forzada con ``tenant_isolation`` y ``GRANT`` por columna.

El rol de la aplicación se lee de ``APP_DB_USER`` y nunca aparece en los mensajes.
``downgrade`` quita las FK de ``activo_evento`` y borra ambas tablas.

Revision ID: 0009_sesiones_y_verificacion
Revises: 0008_activo_cambios
Create Date: 2026-11-14
"""

import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0009_sesiones_y_verificacion"
down_revision: str | Sequence[str] | None = "0008_activo_cambios"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUPABASE_ROLES = ("anon", "authenticated", "service_role")
TABLES = ("sesion_conteo", "verificacion")
TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
APP_ROLE_VAR = "APP_DB_USER"
AUTH_OWNER = "auth_owner"

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
                f"La migración 0009 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


SESION_INSERT = ("tenant_id", "nombre", "fecha_corte", "abierta_por")
VERIFICACION_INSERT = (
    "id",
    "tenant_id",
    "sesion_id",
    "activo_id",
    "ubicacion_esperada_id",
    "ubicacion_encontrada_id",
    "estado_fisico",
    "precio_al_contar",
    "categoria_al_contar",
    "nota",
    "verificado_por",
    "ocurrido_en",
)


def upgrade() -> None:
    conn = op.get_bind()
    quote = conn.dialect.identifier_preparer.quote
    app = quote(_app_role(conn))
    statements = [
        """
        CREATE TABLE sesion_conteo (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenant (id),
            nombre text NOT NULL CHECK (char_length(nombre) BETWEEN 1 AND 120),
            tipo text NOT NULL DEFAULT 'conteo' CHECK (tipo IN ('conteo', 'importacion')),
            estado text NOT NULL DEFAULT 'abierta' CHECK (estado IN ('abierta', 'cerrada')),
            fecha_corte date NOT NULL,
            abierta_por uuid NOT NULL,
            abierta_en timestamptz NOT NULL DEFAULT now(),
            cerrada_por uuid NULL,
            cerrada_en timestamptz NULL,
            CONSTRAINT sesion_conteo_cierre_check
                CHECK ((estado = 'cerrada') = (cerrada_en IS NOT NULL)),
            CONSTRAINT sesion_conteo_tenant_id_key UNIQUE (tenant_id, id),
            CONSTRAINT sesion_conteo_abierta_por_fkey FOREIGN KEY (tenant_id, abierta_por)
                REFERENCES membresia (tenant_id, usuario_id),
            CONSTRAINT sesion_conteo_cerrada_por_fkey FOREIGN KEY (tenant_id, cerrada_por)
                REFERENCES membresia (tenant_id, usuario_id)
        )
        """,
        # Q1: una sola sesión de conteo abierta por tenant.
        "CREATE UNIQUE INDEX sesion_conteo_una_abierta ON sesion_conteo (tenant_id) "
        "WHERE estado = 'abierta' AND tipo = 'conteo'",
        "CREATE INDEX sesion_conteo_abierta_en_idx ON sesion_conteo (tenant_id, abierta_en DESC)",
        """
        CREATE TABLE verificacion (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenant (id),
            sesion_id uuid NOT NULL,
            activo_id uuid NOT NULL,
            ubicacion_esperada_id uuid NOT NULL,
            ubicacion_encontrada_id uuid NOT NULL,
            estado_fisico text NOT NULL CHECK (estado_fisico IN ('ok', 'danado')),
            precio_al_contar numeric(14, 2) NOT NULL CHECK (precio_al_contar >= 0),
            categoria_al_contar uuid NOT NULL,
            nota text NULL CHECK (char_length(nota) BETWEEN 1 AND 120),
            verificado_por uuid NOT NULL,
            ocurrido_en timestamptz NULL,
            recibido_en timestamptz NOT NULL DEFAULT now(),
            seq bigint GENERATED ALWAYS AS IDENTITY,
            CONSTRAINT verificacion_tenant_id_key UNIQUE (tenant_id, id),
            CONSTRAINT verificacion_sesion_fkey FOREIGN KEY (tenant_id, sesion_id)
                REFERENCES sesion_conteo (tenant_id, id),
            CONSTRAINT verificacion_activo_fkey FOREIGN KEY (tenant_id, activo_id)
                REFERENCES activo (tenant_id, id),
            CONSTRAINT verificacion_esperada_fkey FOREIGN KEY (tenant_id, ubicacion_esperada_id)
                REFERENCES ubicacion (tenant_id, id),
            CONSTRAINT verificacion_encontrada_fkey
                FOREIGN KEY (tenant_id, ubicacion_encontrada_id)
                REFERENCES ubicacion (tenant_id, id),
            CONSTRAINT verificacion_categoria_fkey FOREIGN KEY (tenant_id, categoria_al_contar)
                REFERENCES categoria (tenant_id, id),
            CONSTRAINT verificacion_autor_fkey FOREIGN KEY (tenant_id, verificado_por)
                REFERENCES membresia (tenant_id, usuario_id)
        )
        """,
        "CREATE INDEX verificacion_sesion_activo_idx "
        "ON verificacion (tenant_id, sesion_id, activo_id, seq)",
        "ALTER TABLE activo_evento ADD CONSTRAINT activo_evento_sesion_fkey "
        "FOREIGN KEY (tenant_id, sesion_id) REFERENCES sesion_conteo (tenant_id, id)",
        "ALTER TABLE activo_evento ADD CONSTRAINT activo_evento_verificacion_fkey "
        "FOREIGN KEY (tenant_id, verificacion_id) REFERENCES verificacion (tenant_id, id)",
    ]
    for table in TABLES:
        statements += [
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
            f"CREATE POLICY tenant_isolation ON {table} TO {app} "
            f"USING (tenant_id = {TENANT}) WITH CHECK (tenant_id = {TENANT})",
        ]
    statements += [
        f"REVOKE ALL ON {', '.join(TABLES)} FROM PUBLIC",
        f"GRANT SELECT ON sesion_conteo, verificacion TO {app}",
        f"GRANT INSERT ({', '.join(SESION_INSERT)}) ON sesion_conteo TO {app}",
        f"GRANT INSERT ({', '.join(VERIFICACION_INSERT)}) ON verificacion TO {app}",
    ]
    for role in SUPABASE_ROLES:
        if conn.scalar(_ROLE_EXISTS, {"name": role}):
            statements.append(f"REVOKE ALL ON {', '.join(TABLES)} FROM {quote(role)}")
    execute_statements(conn, statements)


def downgrade() -> None:
    execute_statements(
        op.get_bind(),
        [
            "ALTER TABLE activo_evento DROP CONSTRAINT activo_evento_verificacion_fkey",
            "ALTER TABLE activo_evento DROP CONSTRAINT activo_evento_sesion_fkey",
            "DROP TABLE verificacion",
            "DROP TABLE sesion_conteo",
        ],
    )
