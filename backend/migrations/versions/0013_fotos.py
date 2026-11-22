"""Fotos de activos y de verificaciones (spec 012, T3; R4, R6, R9, Q1, Q2; plan.md §4).

- ``foto``: ``id`` del cliente (subida idempotente), activo, verificación opcional,
  ``clave`` del almacenamiento (la arma el servidor), tamaño en bytes y en píxeles, quién
  la subió y, si se cambió o se quitó, quién y cuándo (``retirada_*``; Q2 B: el archivo
  se borra del almacenamiento, la fila queda).
- Una sola principal vigente por activo y una sola foto por verificación (índices
  únicos parciales).
- RLS forzada con ``tenant_isolation``; el rol de la app solo ``SELECT``, ``INSERT`` y
  ``UPDATE (retirada_en, retirada_por)``; un disparador impide tocar una foto ya retirada.
  Sin ``DELETE``.
- ``activo_evento.tipo`` suma ``foto_agregada``, ``foto_cambiada`` y ``foto_retirada``.

``downgrade`` borra la tabla y la función y devuelve los tipos de evento; falla (sin
borrar nada) si ya hay eventos de foto.

Revision ID: 0013_fotos
Revises: 0012_funciones_sin_supabase
Create Date: 2026-11-15
"""

import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0013_fotos"
down_revision: str | Sequence[str] | None = "0012_funciones_sin_supabase"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUPABASE_ROLES = ("anon", "authenticated", "service_role")
TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
APP_ROLE_VAR = "APP_DB_USER"
AUTH_OWNER = "auth_owner"
FUNCION = "public.foto_retirada_es_final()"

EVENTOS_0010 = (
    "creado",
    "importado",
    "verificado",
    "ubicacion_cambiada",
    "precio_cambiado",
    "estado_cambiado",
    "categoria_cambiada",
    "dado_de_baja",
    "datos_cambiados",
    "discrepancia_descartada",
)
EVENTOS = (*EVENTOS_0010, "foto_agregada", "foto_cambiada", "foto_retirada")
CHECK = "activo_evento_tipo_check"
FOTO_INSERT = (
    "id",
    "tenant_id",
    "activo_id",
    "verificacion_id",
    "clave",
    "bytes",
    "ancho",
    "alto",
    "subida_por",
)
FOTO_RETIRO = ("retirada_en", "retirada_por")

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
                f"La migración 0013 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def _tipos(eventos: Sequence[str]) -> str:
    lista = ", ".join(f"'{e}'" for e in eventos)
    return f"ALTER TABLE activo_evento ADD CONSTRAINT {CHECK} CHECK (tipo IN ({lista}))"


def upgrade() -> None:
    conn = op.get_bind()
    quote = conn.dialect.identifier_preparer.quote
    app = quote(_app_role(conn))
    statements = [
        f"ALTER TABLE activo_evento DROP CONSTRAINT {CHECK}",
        _tipos(EVENTOS),
        """
        CREATE TABLE foto (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL REFERENCES tenant (id),
            activo_id uuid NOT NULL,
            verificacion_id uuid NULL,
            clave text NOT NULL CHECK (char_length(clave) BETWEEN 1 AND 200),
            bytes integer NOT NULL CHECK (bytes > 0),
            ancho integer NOT NULL CHECK (ancho > 0),
            alto integer NOT NULL CHECK (alto > 0),
            subida_por uuid NOT NULL,
            creada_en timestamptz NOT NULL DEFAULT now(),
            retirada_en timestamptz NULL,
            retirada_por uuid NULL,
            CONSTRAINT foto_retiro_check CHECK ((retirada_en IS NULL) = (retirada_por IS NULL)),
            CONSTRAINT foto_tenant_id_key UNIQUE (tenant_id, id),
            CONSTRAINT foto_clave_key UNIQUE (clave),
            CONSTRAINT foto_activo_fkey FOREIGN KEY (tenant_id, activo_id)
                REFERENCES activo (tenant_id, id),
            CONSTRAINT foto_verificacion_fkey FOREIGN KEY (tenant_id, verificacion_id)
                REFERENCES verificacion (tenant_id, id),
            CONSTRAINT foto_subida_por_fkey FOREIGN KEY (tenant_id, subida_por)
                REFERENCES membresia (tenant_id, usuario_id),
            CONSTRAINT foto_retirada_por_fkey FOREIGN KEY (tenant_id, retirada_por)
                REFERENCES membresia (tenant_id, usuario_id)
        )
        """,
        # R4: una sola principal vigente por activo; R6: una por verificación.
        "CREATE UNIQUE INDEX foto_principal_vigente ON foto (tenant_id, activo_id) "
        "WHERE verificacion_id IS NULL AND retirada_en IS NULL",
        "CREATE UNIQUE INDEX foto_una_por_verificacion ON foto (tenant_id, verificacion_id) "
        "WHERE verificacion_id IS NOT NULL",
        "CREATE INDEX foto_activo_idx ON foto (tenant_id, activo_id, creada_en)",
        f"""
        CREATE FUNCTION {FUNCION} RETURNS trigger
        LANGUAGE plpgsql SECURITY INVOKER SET search_path = pg_catalog, pg_temp AS $$
        BEGIN
            IF OLD.retirada_en IS NOT NULL THEN
                RAISE EXCEPTION 'foto_retirada' USING ERRCODE = 'P0005';
            END IF;
            RETURN NEW;
        END;
        $$
        """,
        f"REVOKE ALL ON FUNCTION {FUNCION} FROM PUBLIC",
        f"CREATE TRIGGER foto_retirada_es_final BEFORE UPDATE ON foto "
        f"FOR EACH ROW EXECUTE FUNCTION {FUNCION}",
        "ALTER TABLE foto ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE foto FORCE ROW LEVEL SECURITY",
        f"CREATE POLICY tenant_isolation ON foto TO {app} "
        f"USING (tenant_id = {TENANT}) WITH CHECK (tenant_id = {TENANT})",
        "REVOKE ALL ON foto FROM PUBLIC",
        f"GRANT SELECT ON foto TO {app}",
        f"GRANT INSERT ({', '.join(FOTO_INSERT)}) ON foto TO {app}",
        f"GRANT UPDATE ({', '.join(FOTO_RETIRO)}) ON foto TO {app}",
    ]
    for role in SUPABASE_ROLES:
        if conn.scalar(_ROLE_EXISTS, {"name": role}):
            statements += [
                f"REVOKE ALL ON foto FROM {quote(role)}",
                f"REVOKE ALL ON FUNCTION {FUNCION} FROM {quote(role)}",
            ]
    execute_statements(conn, statements)


def downgrade() -> None:
    execute_statements(
        op.get_bind(),
        [
            "DROP TABLE foto",
            f"DROP FUNCTION {FUNCION}",
            f"ALTER TABLE activo_evento DROP CONSTRAINT {CHECK}",
            _tipos(EVENTOS_0010),
        ],
    )
