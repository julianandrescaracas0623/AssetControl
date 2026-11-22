"""Tablas ``activo`` y ``activo_evento`` (spec 004, T1; R2–R8, D1, Q1, Q2; plan.md §2).

- ``activo``: una fila por unidad (R8 de docs/03). ``id`` lo manda el cliente (alta
  idempotente, R2). ``codigo`` del sticker en mayúsculas con el formato de Q1, único por
  tenant e inmutable (la aplicación no tiene ``UPDATE`` todavía; llega con la 005).
  ``precio_compra`` ``NUMERIC(14,2) >= 0`` (Q2). FK compuestas a ``categoria``,
  ``ubicacion`` y ``membresia`` (quien lo creó): todo es del mismo tenant.
- **D1 en la base:** el disparador ``activo_ubicacion_valida`` rechaza una ubicación de
  tipo ``sede`` o inactiva al insertar o cambiar ``ubicacion_id``. ``SECURITY INVOKER``
  (lee ``ubicacion`` con la RLS de quien inserta) y ``search_path`` fijo.
- ``activo_evento``: línea de tiempo inmutable (solo ``SELECT`` e ``INSERT``); ``seq``
  por identidad para un orden estable. ``sesion_id`` y ``verificacion_id`` sin FK hasta
  la spec 006.
- RLS forzada con ``tenant_isolation`` (patrón de 0002) y ``GRANT`` por columna; sin
  ``DELETE`` ni ``TRUNCATE``. ``estado``, ``row_version`` y las fechas los pone la base.

El rol de la aplicación se lee de ``APP_DB_USER`` y nunca aparece en los mensajes.
``downgrade`` borra la función y ambas tablas.

Revision ID: 0007_activos
Revises: 0006_ubicaciones_y_categorias
Create Date: 2026-11-14
"""

import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0007_activos"
down_revision: str | Sequence[str] | None = "0006_ubicaciones_y_categorias"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE_VAR = "APP_DB_USER"
AUTH_OWNER = "auth_owner"
SUPABASE_ROLES = ("anon", "authenticated", "service_role")
TABLES = ("activo", "activo_evento")
TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
NOMBRE_CHECK = "CHECK (char_length(nombre) BETWEEN 1 AND 120)"
OPCIONALES = ("serial", "marca", "modelo", "referencia", "color", "subtipo")
EVENTOS = (
    "creado",
    "importado",
    "verificado",
    "ubicacion_cambiada",
    "precio_cambiado",
    "estado_cambiado",
    "categoria_cambiada",
    "dado_de_baja",
)

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
                f"La migración 0007 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def upgrade() -> None:
    conn = op.get_bind()
    quote = conn.dialect.identifier_preparer.quote
    app = quote(_app_role(conn))
    opcionales = ",\n".join(
        f"            {c} text NULL CHECK (char_length({c}) BETWEEN 1 AND 120)" for c in OPCIONALES
    )
    eventos = ", ".join(f"'{e}'" for e in EVENTOS)

    statements = [
        f"""
        CREATE TABLE activo (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenant (id),
            codigo text NOT NULL CHECK (codigo ~ '^[A-Z0-9._/-]{{1,40}}$'),
            nombre text NOT NULL {NOMBRE_CHECK},
            categoria_id uuid NOT NULL,
            ubicacion_id uuid NOT NULL,
{opcionales},
            atributos jsonb NOT NULL DEFAULT '{{}}'::jsonb
                CHECK (jsonb_typeof(atributos) = 'object'),
            precio_compra numeric(14, 2) NOT NULL CHECK (precio_compra >= 0),
            fecha_compra date NULL,
            estado text NOT NULL DEFAULT 'activo'
                CHECK (estado IN ('activo', 'en_reparacion', 'dado_de_baja')),
            row_version integer NOT NULL DEFAULT 1 CHECK (row_version >= 1),
            creado_por uuid NOT NULL,
            creado_en timestamptz NOT NULL DEFAULT now(),
            actualizado_en timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT activo_tenant_id_key UNIQUE (tenant_id, id),
            CONSTRAINT activo_codigo_key UNIQUE (tenant_id, codigo),
            CONSTRAINT activo_categoria_fkey FOREIGN KEY (tenant_id, categoria_id)
                REFERENCES categoria (tenant_id, id),
            CONSTRAINT activo_ubicacion_fkey FOREIGN KEY (tenant_id, ubicacion_id)
                REFERENCES ubicacion (tenant_id, id),
            CONSTRAINT activo_creado_por_fkey FOREIGN KEY (tenant_id, creado_por)
                REFERENCES membresia (tenant_id, usuario_id)
        )
        """,
        "CREATE INDEX activo_serial_idx ON activo (tenant_id, serial) WHERE serial IS NOT NULL",
        "CREATE INDEX activo_ubicacion_estado_idx ON activo (tenant_id, ubicacion_id, estado)",
        "CREATE INDEX activo_creado_idx ON activo (tenant_id, creado_en DESC, id)",
        # D1: solo sala o box activos. Sin SQL dinámico; todo calificado.
        """
        CREATE FUNCTION public.activo_ubicacion_valida() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
        DECLARE
            v_tipo text;
            v_activa boolean;
        BEGIN
            SELECT u.tipo, u.activa INTO v_tipo, v_activa
            FROM public.ubicacion u
            WHERE u.tenant_id = NEW.tenant_id AND u.id = NEW.ubicacion_id;
            IF v_tipo IS NULL OR v_tipo = 'sede' OR NOT v_activa THEN
                RAISE EXCEPTION 'ubicacion_invalida' USING ERRCODE = 'P0002';
            END IF;
            RETURN NEW;
        END;
        $$
        """,
        "REVOKE ALL ON FUNCTION public.activo_ubicacion_valida() FROM PUBLIC",
        "CREATE TRIGGER activo_ubicacion_valida BEFORE INSERT OR UPDATE OF ubicacion_id "
        "ON activo FOR EACH ROW EXECUTE FUNCTION public.activo_ubicacion_valida()",
        f"""
        CREATE TABLE activo_evento (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenant (id),
            activo_id uuid NOT NULL,
            tipo text NOT NULL CHECK (tipo IN ({eventos})),
            datos jsonb NOT NULL CHECK (jsonb_typeof(datos) = 'object'),
            usuario_id uuid NOT NULL,
            sesion_id uuid NULL,
            verificacion_id uuid NULL,
            ocurrido_en timestamptz NOT NULL DEFAULT now(),
            seq bigint GENERATED ALWAYS AS IDENTITY,
            CONSTRAINT activo_evento_activo_fkey FOREIGN KEY (tenant_id, activo_id)
                REFERENCES activo (tenant_id, id),
            CONSTRAINT activo_evento_usuario_fkey FOREIGN KEY (tenant_id, usuario_id)
                REFERENCES membresia (tenant_id, usuario_id)
        )
        """,
        "CREATE INDEX activo_evento_activo_idx ON activo_evento (tenant_id, activo_id, seq)",
    ]
    for table in TABLES:
        statements += [
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
            f"CREATE POLICY tenant_isolation ON {table} TO {app} "
            f"USING (tenant_id = {TENANT}) WITH CHECK (tenant_id = {TENANT})",
        ]

    insert_activo = ", ".join(
        [
            "id",
            "tenant_id",
            "codigo",
            "nombre",
            "categoria_id",
            "ubicacion_id",
            *OPCIONALES,
            "atributos",
            "precio_compra",
            "fecha_compra",
            "creado_por",
        ]
    )
    statements += [
        f"REVOKE ALL ON {', '.join(TABLES)} FROM PUBLIC",
        f"GRANT SELECT ON activo TO {app}",
        f"GRANT INSERT ({insert_activo}) ON activo TO {app}",
        f"GRANT SELECT ON activo_evento TO {app}",
        "GRANT INSERT (tenant_id, activo_id, tipo, datos, usuario_id, sesion_id, "
        f"verificacion_id) ON activo_evento TO {app}",
    ]
    for role in SUPABASE_ROLES:
        if conn.scalar(_ROLE_EXISTS, {"name": role}):
            statements.append(f"REVOKE ALL ON {', '.join(TABLES)} FROM {quote(role)}")
    execute_statements(conn, statements)


def downgrade() -> None:
    execute_statements(
        op.get_bind(),
        [
            "DROP TABLE activo_evento",
            "DROP TABLE activo",
            "DROP FUNCTION public.activo_ubicacion_valida()",
        ],
    )
