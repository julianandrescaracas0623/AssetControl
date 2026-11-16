"""Datos de la empresa y detalle congelado del cierre (spec 013, T1; R1–R4; plan.md §2).

- ``empresa``: una fila por tenant (nombre, dirección, NIT, teléfono, correo y el logo
  vigente). La app la lee, la crea y la actualiza (solo el admin, en la aplicación).
- ``empresa_logo``: cada logo subido (``id`` del cliente, ``clave`` del almacenamiento,
  tamaño). Solo ``INSERT``/``SELECT``: nunca se borra, porque los informes congelados
  siguen usándolo (R2).
- ``sesion_empresa``: copia de los datos de la empresa al cerrar una sesión (R3).
- ``sesion_detalle``: una fila por activo del universo U del cierre (R4), con los mismos
  criterios del desglose (encontrado: datos de su verificación vigente; no encontrado:
  los del cierre).
- Las dos tablas del cierre solo aceptan filas de sesiones cerradas (disparador
  ``conteo_cerrado_requerido`` de la 0011) y solo ``INSERT``/``SELECT``.
- RLS forzada con ``tenant_isolation`` y nada para los roles de Supabase (C8).

``downgrade`` borra las cuatro tablas.

Revision ID: 0014_empresa_y_detalle
Revises: 0013_fotos
Create Date: 2026-11-16
"""

import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0014_empresa_y_detalle"
down_revision: str | Sequence[str] | None = "0013_fotos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUPABASE_ROLES = ("anon", "authenticated", "service_role")
TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
APP_ROLE_VAR = "APP_DB_USER"
AUTH_OWNER = "auth_owner"
TABLES = ("empresa_logo", "empresa", "sesion_empresa", "sesion_detalle")
CERRADAS = ("sesion_empresa", "sesion_detalle")

DATOS_EMPRESA = ("nombre", "direccion", "nit", "telefono", "correo", "logo_id")
EMPRESA_INSERT = ("tenant_id", *DATOS_EMPRESA, "actualizada_por")
EMPRESA_UPDATE = (*DATOS_EMPRESA, "actualizada_en", "actualizada_por")
LOGO_INSERT = ("id", "tenant_id", "clave", "bytes", "ancho", "alto", "subido_por")
SESION_EMPRESA_INSERT = ("tenant_id", "sesion_id", *DATOS_EMPRESA, "vigente")
DETALLE_INSERT = (
    "tenant_id",
    "sesion_id",
    "activo_id",
    "codigo",
    "nombre",
    "marca",
    "serial",
    "categoria_id",
    "categoria_nombre",
    "ubicacion_id",
    "ubicacion_ruta",
    "encontrada_ruta",
    "estado_fisico",
    "encontrado",
    "en_reparacion",
    "precio",
)
ETIQUETA = "text NOT NULL CHECK (char_length({c}) BETWEEN 1 AND 300)"
OPCIONAL = "text NULL CHECK (char_length({c}) BETWEEN 1 AND 300)"
NIT = r"text NULL CHECK (nit ~ '^[0-9]{{1,3}}(\.[0-9]{{3}}){{1,4}}(-[0-9])?$')"
# Mismos límites para la empresa y su copia congelada.
COLUMNAS_EMPRESA = f"""
            nombre text NOT NULL CHECK (char_length(nombre) BETWEEN 1 AND 120),
            direccion text NULL CHECK (char_length(direccion) BETWEEN 1 AND 200),
            nit {NIT.format()},
            telefono text NULL CHECK (char_length(telefono) BETWEEN 7 AND 30),
            correo text NULL CHECK (char_length(correo) BETWEEN 3 AND 254),
            logo_id uuid NULL"""


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
                f"La migración 0014 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def upgrade() -> None:
    conn = op.get_bind()
    quote = conn.dialect.identifier_preparer.quote
    app = quote(_app_role(conn))
    statements = [
        """
        CREATE TABLE empresa_logo (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenant (id),
            clave text NOT NULL CHECK (char_length(clave) BETWEEN 1 AND 200),
            bytes integer NOT NULL CHECK (bytes > 0),
            ancho integer NOT NULL CHECK (ancho > 0),
            alto integer NOT NULL CHECK (alto > 0),
            subido_por uuid NOT NULL,
            creado_en timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT empresa_logo_tenant_id_key UNIQUE (tenant_id, id),
            CONSTRAINT empresa_logo_clave_key UNIQUE (clave),
            CONSTRAINT empresa_logo_subido_por_fkey FOREIGN KEY (tenant_id, subido_por)
                REFERENCES membresia (tenant_id, usuario_id)
        )
        """,
        f"""
        CREATE TABLE empresa (
            tenant_id uuid PRIMARY KEY REFERENCES tenant (id),{COLUMNAS_EMPRESA},
            actualizada_en timestamptz NOT NULL DEFAULT now(),
            actualizada_por uuid NOT NULL,
            CONSTRAINT empresa_direccion_requerida CHECK (direccion IS NOT NULL),
            CONSTRAINT empresa_logo_fkey FOREIGN KEY (tenant_id, logo_id)
                REFERENCES empresa_logo (tenant_id, id),
            CONSTRAINT empresa_actualizada_por_fkey FOREIGN KEY (tenant_id, actualizada_por)
                REFERENCES membresia (tenant_id, usuario_id)
        )
        """,
        f"""
        CREATE TABLE sesion_empresa (
            tenant_id uuid NOT NULL REFERENCES tenant (id),
            sesion_id uuid NOT NULL,{COLUMNAS_EMPRESA},
            vigente boolean NOT NULL DEFAULT false,
            creado_en timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT sesion_empresa_pkey PRIMARY KEY (tenant_id, sesion_id),
            CONSTRAINT sesion_empresa_sesion_fkey FOREIGN KEY (tenant_id, sesion_id)
                REFERENCES sesion_conteo (tenant_id, id),
            CONSTRAINT sesion_empresa_logo_fkey FOREIGN KEY (tenant_id, logo_id)
                REFERENCES empresa_logo (tenant_id, id)
        )
        """,
        f"""
        CREATE TABLE sesion_detalle (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenant (id),
            sesion_id uuid NOT NULL,
            activo_id uuid NOT NULL,
            codigo text NOT NULL CHECK (codigo ~ '^[A-Z0-9._/-]{{1,40}}$'),
            nombre {ETIQUETA.format(c="nombre")},
            marca {OPCIONAL.format(c="marca")},
            serial {OPCIONAL.format(c="serial")},
            categoria_id uuid NOT NULL,
            categoria_nombre {ETIQUETA.format(c="categoria_nombre")},
            ubicacion_id uuid NOT NULL,
            ubicacion_ruta {ETIQUETA.format(c="ubicacion_ruta")},
            encontrada_ruta {OPCIONAL.format(c="encontrada_ruta")},
            estado_fisico text NULL CHECK (estado_fisico IN ('ok', 'danado')),
            encontrado boolean NOT NULL,
            en_reparacion boolean NOT NULL,
            precio numeric(14, 2) NOT NULL CHECK (precio >= 0),
            creado_en timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT sesion_detalle_encontrado_check CHECK (
                encontrado = (estado_fisico IS NOT NULL)
                AND encontrado = (encontrada_ruta IS NOT NULL)
            ),
            CONSTRAINT sesion_detalle_activo_key UNIQUE (tenant_id, sesion_id, activo_id),
            CONSTRAINT sesion_detalle_sesion_fkey FOREIGN KEY (tenant_id, sesion_id)
                REFERENCES sesion_conteo (tenant_id, id),
            CONSTRAINT sesion_detalle_activo_fkey FOREIGN KEY (tenant_id, activo_id)
                REFERENCES activo (tenant_id, id),
            CONSTRAINT sesion_detalle_categoria_fkey FOREIGN KEY (tenant_id, categoria_id)
                REFERENCES categoria (tenant_id, id),
            CONSTRAINT sesion_detalle_ubicacion_fkey FOREIGN KEY (tenant_id, ubicacion_id)
                REFERENCES ubicacion (tenant_id, id)
        )
        """,
    ]
    for table in CERRADAS:
        statements.append(
            f"CREATE TRIGGER {table}_cerrada BEFORE INSERT ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION public.conteo_cerrado_requerido()"
        )
    for table in TABLES:
        statements += [
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
            f"CREATE POLICY tenant_isolation ON {table} TO {app} "
            f"USING (tenant_id = {TENANT}) WITH CHECK (tenant_id = {TENANT})",
        ]
    statements += [
        f"REVOKE ALL ON {', '.join(TABLES)} FROM PUBLIC",
        f"GRANT SELECT ON {', '.join(TABLES)} TO {app}",
        f"GRANT INSERT ({', '.join(LOGO_INSERT)}) ON empresa_logo TO {app}",
        f"GRANT INSERT ({', '.join(EMPRESA_INSERT)}) ON empresa TO {app}",
        f"GRANT UPDATE ({', '.join(EMPRESA_UPDATE)}) ON empresa TO {app}",
        f"GRANT INSERT ({', '.join(SESION_EMPRESA_INSERT)}) ON sesion_empresa TO {app}",
        f"GRANT INSERT ({', '.join(DETALLE_INSERT)}) ON sesion_detalle TO {app}",
    ]
    for role in SUPABASE_ROLES:
        if conn.scalar(_ROLE_EXISTS, {"name": role}):
            statements.append(f"REVOKE ALL ON {', '.join(TABLES)} FROM {quote(role)}")
    execute_statements(conn, statements)


def downgrade() -> None:
    execute_statements(
        op.get_bind(),
        [
            "DROP TABLE sesion_detalle",
            "DROP TABLE sesion_empresa",
            "DROP TABLE empresa",
            "DROP TABLE empresa_logo",
        ],
    )
