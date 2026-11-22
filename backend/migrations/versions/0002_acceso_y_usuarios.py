"""Acceso y usuarios: esquema base, RLS y GRANT (spec 002, T1; plan.md §3 y §5).

Crea el esquema ``acceso`` (vacío: sus funciones llegan en 0004) y las tablas
``tenant``, ``usuario``, ``membresia``, ``invitacion`` y ``refresh_token`` de
``docs/03`` con:

- RLS habilitada y forzada en las cinco.
- ``tenant_isolation`` ``TO`` el rol de la aplicación (nunca ``PUBLIC``) en
  ``membresia``, ``invitacion`` y ``refresh_token``; en ``tenant``, solo lectura
  de la fila del tenant fijado; en ``usuario``, solo lectura de quien tiene
  membresía en el tenant fijado.
- Política ``RESTRICTIVE`` ``FOR INSERT`` ``invitacion_creada_por_no_nula``: la
  aplicación nunca inserta invitaciones del operador (``creada_por`` NULL).
- ``GRANT`` mínimos y por columna: la aplicación no lee ``usuario.password_hash``
  ni ``invitacion.token_hash`` y nadie recibe ``DELETE``.
- ``REVOKE`` a ``anon``, ``authenticated`` y ``service_role`` (Supabase) si existen.

El rol de la aplicación se lee de ``APP_DB_USER`` (migrations/README.md); su
valor no se escribe en el código ni aparece en los mensajes de error, y se
rechaza si es superusuario o tiene ``BYPASSRLS``. Las sentencias se ejecutan sin
interpretar parámetros (``execute_statements``). Los roles
no los crea la migración: ``auth_owner`` y el rol de la aplicación los crea
``docker/postgres/init/01-app-role.sh`` (P0).

Revision ID: 0002_acceso_y_usuarios
Revises: 0001_baseline
Create Date: 2026-11-12
"""

import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0002_acceso_y_usuarios"
down_revision: str | Sequence[str] | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE_VAR = "APP_DB_USER"
AUTH_OWNER = "auth_owner"
SUPABASE_ROLES = ("anon", "authenticated", "service_role")
TABLES = ("tenant", "usuario", "membresia", "invitacion", "refresh_token")

TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"

_ROLE_EXISTS = text("select exists (select 1 from pg_roles where rolname = :name)")
_ROLE_SKIPS_RLS = text("select rolsuper or rolbypassrls from pg_roles where rolname = :name")


def _role_exists(conn: Connection, name: str) -> bool:
    return bool(conn.scalar(_ROLE_EXISTS, {"name": name}))


def require_auth_owner(conn: Connection, name: str = AUTH_OWNER) -> None:
    """Falla con un mensaje claro si no existe ``auth_owner`` (P0, plan.md §2.1)."""
    if not _role_exists(conn, name):
        raise RuntimeError(
            f"Falta el rol {AUTH_OWNER}: créalo con docker/postgres/init/01-app-role.sh "
            "(spec 002, P0) antes de migrar."
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
    if not _role_exists(conn, name):
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
    """Ejecuta DDL tal cual, sin parámetros, y falla sin mostrar la sentencia.

    ``op.execute`` envuelve el texto en ``text()``: un ``:palabra`` dentro del nombre
    citado del rol se tomaría como parámetro. Aquí no se interpretan ``:`` ni ``%``,
    y el error, si lo hay, no lleva el SQL (que incluye el nombre del rol).
    """
    for index, statement in enumerate(statements, start=1):
        failure = None
        try:
            conn.exec_driver_sql(statement, execution_options={"no_parameters": True})
        except SQLAlchemyError as exc:
            sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None) or "desconocido"
            failure = (
                f"La migración 0002 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def upgrade() -> None:
    conn = op.get_bind()
    require_auth_owner(conn)
    quote = conn.dialect.identifier_preparer.quote
    app = quote(_app_role(conn))
    owner = quote(AUTH_OWNER)

    statements = [
        # Esquema de las funciones SECURITY DEFINER (0004); propiedad del migrador.
        "CREATE SCHEMA acceso",
        "REVOKE ALL ON SCHEMA acceso FROM PUBLIC",
        f"GRANT USAGE ON SCHEMA acceso TO {app}, {owner}",
        # --- Tablas (docs/03) ---
        """
        CREATE TABLE tenant (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            nombre text NOT NULL,
            creado_en timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE usuario (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            email text NOT NULL,
            nombre text NOT NULL,
            password_hash text NOT NULL,
            activo boolean NOT NULL DEFAULT true,
            CONSTRAINT usuario_email_normalizado CHECK (email = lower(btrim(email)))
        )
        """,
        "CREATE UNIQUE INDEX usuario_email_key ON usuario (email)",
        """
        CREATE TABLE membresia (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenant (id),
            usuario_id uuid NOT NULL REFERENCES usuario (id),
            rol text NOT NULL,
            activa boolean NOT NULL DEFAULT true,
            CONSTRAINT membresia_rol_valido CHECK (rol IN ('admin', 'contador')),
            CONSTRAINT membresia_tenant_usuario_key UNIQUE (tenant_id, usuario_id),
            CONSTRAINT membresia_tenant_id_key UNIQUE (tenant_id, id)
        )
        """,
        """
        CREATE TABLE invitacion (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenant (id),
            email text NOT NULL,
            rol text NOT NULL,
            token_hash bytea NOT NULL,
            expira_en timestamptz NOT NULL,
            usada_en timestamptz,
            creada_por uuid,
            CONSTRAINT invitacion_email_normalizado CHECK (email = lower(btrim(email))),
            CONSTRAINT invitacion_rol_valido CHECK (rol IN ('admin', 'contador')),
            CONSTRAINT invitacion_token_hash_32 CHECK (octet_length(token_hash) = 32),
            CONSTRAINT invitacion_token_hash_key UNIQUE (token_hash),
            -- MATCH SIMPLE: creada_por NULL = creada por el operador (crear_tenant).
            CONSTRAINT invitacion_creada_por_fkey FOREIGN KEY (tenant_id, creada_por)
                REFERENCES membresia (tenant_id, usuario_id) MATCH SIMPLE
        )
        """,
        "CREATE INDEX invitacion_tenant_id_idx ON invitacion (tenant_id)",
        """
        CREATE TABLE refresh_token (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL,
            membresia_id uuid NOT NULL,
            familia_id uuid NOT NULL,
            token_hash bytea NOT NULL,
            expira_en timestamptz NOT NULL,
            usado_en timestamptz,
            revocado_en timestamptz,
            creado_en timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT refresh_token_token_hash_32 CHECK (octet_length(token_hash) = 32),
            CONSTRAINT refresh_token_token_hash_key UNIQUE (token_hash),
            CONSTRAINT refresh_token_membresia_fkey FOREIGN KEY (tenant_id, membresia_id)
                REFERENCES membresia (tenant_id, id)
        )
        """,
        "CREATE INDEX refresh_token_tenant_id_idx ON refresh_token (tenant_id)",
        "CREATE INDEX refresh_token_familia_id_idx ON refresh_token (familia_id)",
    ]

    # --- RLS habilitada y forzada en las cinco ---
    for table in TABLES:
        statements += [
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY",
        ]

    statements += [
        # tenant: solo la fila del tenant fijado; sin INSERT/UPDATE de la aplicación.
        f"CREATE POLICY tenant_isolation ON tenant FOR SELECT TO {app} USING (id = {TENANT})",
        # usuario: solo quien tiene membresía en el tenant fijado (membresia también
        # está bajo RLS para la aplicación).
        # Solo constantes del módulo y el rol citado con identifier_preparer.quote.
        f"CREATE POLICY usuario_por_membresia ON usuario FOR SELECT TO {app} "  # noqa: S608
        "USING (EXISTS (SELECT 1 FROM membresia m "
        f"WHERE m.usuario_id = usuario.id AND m.tenant_id = {TENANT}))",
    ]
    for table in ("membresia", "invitacion", "refresh_token"):
        statements.append(
            f"CREATE POLICY tenant_isolation ON {table} TO {app} "
            f"USING (tenant_id = {TENANT}) WITH CHECK (tenant_id = {TENANT})"
        )
    statements += [
        # RESTRICTIVE: se combina con AND; una permisiva futura no la anula.
        f"CREATE POLICY invitacion_creada_por_no_nula ON invitacion AS RESTRICTIVE "
        f"FOR INSERT TO {app} WITH CHECK (creada_por IS NOT NULL)",
    ]

    # --- GRANT mínimos (plan.md §3); nunca DELETE ---
    statements.append(f"REVOKE ALL ON {', '.join(TABLES)} FROM PUBLIC")
    statements += [
        f"GRANT SELECT ON tenant TO {app}",
        f"GRANT SELECT (id, email, nombre, activo) ON usuario TO {app}",
        f"GRANT SELECT ON membresia TO {app}",
        f"GRANT SELECT (id, tenant_id, email, rol, expira_en, usada_en, creada_por) "
        f"ON invitacion TO {app}",
        f"GRANT INSERT (id, tenant_id, rol, email, token_hash, expira_en, creada_por) "
        f"ON invitacion TO {app}",
        f"GRANT SELECT, INSERT ON refresh_token TO {app}",
        f"GRANT UPDATE (usado_en, revocado_en) ON refresh_token TO {app}",
    ]

    # --- Roles de la Data API de Supabase: nada en estas tablas ni en acceso ---
    # alembic_version también: los privilegios por defecto de Supabase se los dan al
    # crearla y quedaría expuesta (incluido DELETE) por la Data API.
    for role in SUPABASE_ROLES:
        if _role_exists(conn, role):
            quoted = quote(role)
            statements += [
                f"REVOKE ALL ON alembic_version, {', '.join(TABLES)} FROM {quoted}",
                f"REVOKE ALL ON SCHEMA acceso FROM {quoted}",
            ]

    execute_statements(conn, statements)


def downgrade() -> None:
    # La política de usuario depende de membresia: se quita antes de borrar tablas.
    op.execute("DROP POLICY usuario_por_membresia ON usuario")
    for table in reversed(TABLES):
        # DROP TABLE elimina también sus políticas, índices y GRANT.
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP SCHEMA acceso")
