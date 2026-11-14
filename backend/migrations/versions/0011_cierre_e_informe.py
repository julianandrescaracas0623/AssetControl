"""Cierre de sesión e informe congelado (spec 008, T1; R2–R5, Q3; plan.md §2).

- ``sesion_conteo``: ``total_encontrado``, ``total_no_encontrado`` y
  ``total_registrado`` (``NUMERIC(14,2)``), obligatorios si y solo si la sesión está
  cerrada, ``>= 0`` y registrado = encontrado + no encontrado. ``GRANT UPDATE`` solo de
  las columnas del cierre. El disparador ``sesion_conteo_inmutable`` impide modificar
  una sesión que no esté abierta y solo deja pasar ``abierta → cerrada`` (R5).
- ``sesion_desglose`` (R9): una fila por categoría y una por ubicación con COP y
  unidades; ``etiqueta`` congela el nombre o la ruta al cierre (Q3).
- ``sesion_no_encontrado`` (R9a): una fila por activo no encontrado, con precio, nombres
  y la marca ``en_reparacion`` congelados.
- Las dos son inmutables (solo ``INSERT`` y ``SELECT``) y el disparador
  ``conteo_cerrado_requerido`` exige que la sesión ya esté cerrada al insertar.
- RLS forzada con ``tenant_isolation``, FK compuestas y funciones ``SECURITY INVOKER``
  con ``search_path`` fijo y sin ``EXECUTE`` para ``PUBLIC``.

El rol de la aplicación se lee de ``APP_DB_USER`` y nunca aparece en los mensajes.
``downgrade`` borra las tablas, las funciones y las columnas (y con ellas los informes).

Revision ID: 0011_cierre_e_informe
Revises: 0010_discrepancias
Create Date: 2026-11-14
"""

import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0011_cierre_e_informe"
down_revision: str | Sequence[str] | None = "0010_discrepancias"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("sesion_desglose", "sesion_no_encontrado")
SUPABASE_ROLES = ("anon", "authenticated", "service_role")
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
                f"La migración 0011 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


CIERRE = (
    "estado",
    "cerrada_por",
    "cerrada_en",
    "total_encontrado",
    "total_no_encontrado",
    "total_registrado",
)
DESGLOSE_INSERT = (
    "tenant_id",
    "sesion_id",
    "dimension",
    "categoria_id",
    "ubicacion_id",
    "etiqueta",
    "total_encontrado",
    "total_no_encontrado",
    "total_registrado",
    "unidades_encontrado",
    "unidades_no_encontrado",
    "unidades_registrado",
)
NO_ENCONTRADO_INSERT = (
    "tenant_id",
    "sesion_id",
    "activo_id",
    "codigo",
    "nombre",
    "categoria_id",
    "categoria_nombre",
    "ubicacion_id",
    "ubicacion_ruta",
    "precio",
    "en_reparacion",
)
DINERO = "numeric(14, 2) NOT NULL CHECK ({c} >= 0)"
UNIDADES = "integer NOT NULL CHECK ({c} >= 0)"
ETIQUETA = "text NOT NULL CHECK (char_length({c}) BETWEEN 1 AND 300)"


def _cifras() -> str:
    columnas = []
    for sufijo in ("encontrado", "no_encontrado", "registrado"):
        columnas.append(f"total_{sufijo} " + DINERO.format(c=f"total_{sufijo}"))
        columnas.append(f"unidades_{sufijo} " + UNIDADES.format(c=f"unidades_{sufijo}"))
    return ",\n            ".join(columnas)


def upgrade() -> None:
    conn = op.get_bind()
    quote = conn.dialect.identifier_preparer.quote
    app = quote(_app_role(conn))
    statements = [
        "ALTER TABLE sesion_conteo "
        "ADD COLUMN total_encontrado numeric(14, 2) NULL, "
        "ADD COLUMN total_no_encontrado numeric(14, 2) NULL, "
        "ADD COLUMN total_registrado numeric(14, 2) NULL",
        "ALTER TABLE sesion_conteo ADD CONSTRAINT sesion_conteo_totales_check CHECK ("
        "(estado = 'cerrada') = (total_encontrado IS NOT NULL) "
        "AND (estado = 'cerrada') = (total_no_encontrado IS NOT NULL) "
        "AND (estado = 'cerrada') = (total_registrado IS NOT NULL) "
        "AND total_encontrado >= 0 AND total_no_encontrado >= 0 "
        "AND total_registrado = total_encontrado + total_no_encontrado)",
        # R5: una sesión cerrada no cambia; la única transición es abierta → cerrada.
        """
        CREATE FUNCTION public.sesion_conteo_inmutable() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
        BEGIN
            IF OLD.estado <> 'abierta' OR NEW.estado <> 'cerrada' THEN
                RAISE EXCEPTION 'sesion_cerrada' USING ERRCODE = 'P0003';
            END IF;
            RETURN NEW;
        END;
        $$
        """,
        "REVOKE ALL ON FUNCTION public.sesion_conteo_inmutable() FROM PUBLIC",
        "CREATE TRIGGER sesion_conteo_inmutable BEFORE UPDATE ON sesion_conteo "
        "FOR EACH ROW EXECUTE FUNCTION public.sesion_conteo_inmutable()",
        f"""
        CREATE TABLE sesion_desglose (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenant (id),
            sesion_id uuid NOT NULL,
            dimension text NOT NULL CHECK (dimension IN ('categoria', 'ubicacion')),
            categoria_id uuid NULL,
            ubicacion_id uuid NULL,
            etiqueta {ETIQUETA.format(c="etiqueta")},
            {_cifras()},
            creado_en timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT sesion_desglose_dimension_ids_check CHECK (
                (dimension = 'categoria' AND categoria_id IS NOT NULL AND ubicacion_id IS NULL)
                OR (dimension = 'ubicacion' AND ubicacion_id IS NOT NULL AND categoria_id IS NULL)
            ),
            CONSTRAINT sesion_desglose_suma_check CHECK (
                total_registrado = total_encontrado + total_no_encontrado
                AND unidades_registrado = unidades_encontrado + unidades_no_encontrado
            ),
            CONSTRAINT sesion_desglose_sesion_fkey FOREIGN KEY (tenant_id, sesion_id)
                REFERENCES sesion_conteo (tenant_id, id),
            CONSTRAINT sesion_desglose_categoria_fkey FOREIGN KEY (tenant_id, categoria_id)
                REFERENCES categoria (tenant_id, id),
            CONSTRAINT sesion_desglose_ubicacion_fkey FOREIGN KEY (tenant_id, ubicacion_id)
                REFERENCES ubicacion (tenant_id, id)
        )
        """,
        "CREATE UNIQUE INDEX sesion_desglose_categoria_key ON sesion_desglose "
        "(tenant_id, sesion_id, categoria_id) WHERE dimension = 'categoria'",
        "CREATE UNIQUE INDEX sesion_desglose_ubicacion_key ON sesion_desglose "
        "(tenant_id, sesion_id, ubicacion_id) WHERE dimension = 'ubicacion'",
        f"""
        CREATE TABLE sesion_no_encontrado (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenant (id),
            sesion_id uuid NOT NULL,
            activo_id uuid NOT NULL,
            codigo text NOT NULL CHECK (codigo ~ '^[A-Z0-9._/-]{{1,40}}$'),
            nombre {ETIQUETA.format(c="nombre")},
            categoria_id uuid NOT NULL,
            categoria_nombre {ETIQUETA.format(c="categoria_nombre")},
            ubicacion_id uuid NOT NULL,
            ubicacion_ruta {ETIQUETA.format(c="ubicacion_ruta")},
            precio {DINERO.format(c="precio")},
            en_reparacion boolean NOT NULL,
            creado_en timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT sesion_no_encontrado_activo_key UNIQUE (tenant_id, sesion_id, activo_id),
            CONSTRAINT sesion_no_encontrado_sesion_fkey FOREIGN KEY (tenant_id, sesion_id)
                REFERENCES sesion_conteo (tenant_id, id),
            CONSTRAINT sesion_no_encontrado_activo_fkey FOREIGN KEY (tenant_id, activo_id)
                REFERENCES activo (tenant_id, id),
            CONSTRAINT sesion_no_encontrado_categoria_fkey FOREIGN KEY (tenant_id, categoria_id)
                REFERENCES categoria (tenant_id, id),
            CONSTRAINT sesion_no_encontrado_ubicacion_fkey FOREIGN KEY (tenant_id, ubicacion_id)
                REFERENCES ubicacion (tenant_id, id)
        )
        """,
        # Desglose y lista solo para sesiones ya cerradas (el cierre cierra y luego inserta).
        """
        CREATE FUNCTION public.conteo_cerrado_requerido() RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
        DECLARE
            v_estado text;
        BEGIN
            SELECT s.estado INTO v_estado
            FROM public.sesion_conteo s
            WHERE s.tenant_id = NEW.tenant_id AND s.id = NEW.sesion_id;
            IF v_estado IS DISTINCT FROM 'cerrada' THEN
                RAISE EXCEPTION 'sesion_abierta' USING ERRCODE = 'P0004';
            END IF;
            RETURN NEW;
        END;
        $$
        """,
        "REVOKE ALL ON FUNCTION public.conteo_cerrado_requerido() FROM PUBLIC",
    ]
    for table in TABLES:
        statements += [
            f"CREATE TRIGGER {table}_cerrada BEFORE INSERT ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION public.conteo_cerrado_requerido()",
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
            f"CREATE POLICY tenant_isolation ON {table} TO {app} "
            f"USING (tenant_id = {TENANT}) WITH CHECK (tenant_id = {TENANT})",
        ]
    statements += [
        f"REVOKE ALL ON {', '.join(TABLES)} FROM PUBLIC",
        f"GRANT UPDATE ({', '.join(CIERRE)}) ON sesion_conteo TO {app}",
        f"GRANT SELECT ON {', '.join(TABLES)} TO {app}",
        f"GRANT INSERT ({', '.join(DESGLOSE_INSERT)}) ON sesion_desglose TO {app}",
        f"GRANT INSERT ({', '.join(NO_ENCONTRADO_INSERT)}) ON sesion_no_encontrado TO {app}",
    ]
    for role in SUPABASE_ROLES:
        if conn.scalar(_ROLE_EXISTS, {"name": role}):
            statements.append(f"REVOKE ALL ON {', '.join(TABLES)} FROM {quote(role)}")
    execute_statements(conn, statements)


def downgrade() -> None:
    conn = op.get_bind()
    app = conn.dialect.identifier_preparer.quote(_app_role(conn))
    execute_statements(
        conn,
        [
            "DROP TABLE sesion_no_encontrado",
            "DROP TABLE sesion_desglose",
            "DROP FUNCTION public.conteo_cerrado_requerido()",
            f"REVOKE UPDATE ({', '.join(CIERRE)}) ON sesion_conteo FROM {app}",
            "DROP TRIGGER sesion_conteo_inmutable ON sesion_conteo",
            "DROP FUNCTION public.sesion_conteo_inmutable()",
            "ALTER TABLE sesion_conteo DROP CONSTRAINT sesion_conteo_totales_check",
            "ALTER TABLE sesion_conteo DROP COLUMN total_registrado, "
            "DROP COLUMN total_no_encontrado, DROP COLUMN total_encontrado",
        ],
    )
