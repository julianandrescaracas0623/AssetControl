"""Tabla de infraestructura ``limite_tasa`` (spec 002, T10; Q10, R13, R5, A13).

Contadores de los límites de tasa de login, refresh, validar y aceptar
invitación (``docs/03``, cambio 6; ``plan.md`` §3.1):

- **Sin ``tenant_id``**: se limita antes de conocer el tenant y la tabla no guarda
  datos de negocio ni de la clínica, solo HMAC de 32 bytes y contadores. Es una
  excepción cerrada del catálogo con prueba propia (``test_catalog_rls.py``).
- PK ``(ambito, clave_hash, ventana_inicio)``; ``ambito`` en lista cerrada,
  ``clave_hash`` de 32 bytes e ``intentos >= 0``.
- RLS habilitada y forzada; una política por comando ``TO`` el rol de la
  aplicación (``SELECT``, ``INSERT``, ``UPDATE``), sin ``PUBLIC`` ni ``FOR ALL``.
  No filtran por tenant (no lo hay): la defensa es el privilegio mínimo y el HMAC.
  El ``INSERT`` solo crea contadores con ``intentos = 1`` (no se pueden sembrar
  ventanas ya agotadas ni con cero) y el ``UPDATE`` no deja valores negativos.
- ``GRANT SELECT, INSERT, UPDATE (intentos)`` a la aplicación: el ``SELECT`` es
  necesario para el ``ON CONFLICT`` (inferencia del índice) y el ``RETURNING``
  (A13). **Sin ``DELETE`` ni ``TRUNCATE``** para la aplicación, ``auth_owner`` ni
  los roles de Supabase.
- **Purga** (R5, Q10): solo el migrador (``current_user`` al migrar, dueño de la
  tabla) borra, con el comando ``flask purgar-limite-tasa``. Bajo ``FORCE RLS`` un
  migrador que no es superusuario necesita política: ``limite_tasa_purga``
  (``DELETE``) y ``limite_tasa_purga_leer`` (``SELECT``, la exige el ``WHERE``),
  ambas ``TO`` el migrador y solo para ventanas de más de un día (el máximo de la
  ventana configurable es un día: nunca borra un contador vigente).

El rol de la aplicación se lee de ``APP_DB_USER`` (como 0002–0004) y nunca aparece en
los mensajes. ``downgrade`` borra la tabla (y con ella sus políticas y ``GRANT``).

Revision ID: 0005_limite_tasa
Revises: 0004_funciones_de_acceso
Create Date: 2026-11-13
"""

import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0005_limite_tasa"
down_revision: str | Sequence[str] | None = "0004_funciones_de_acceso"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE_VAR = "APP_DB_USER"
AUTH_OWNER = "auth_owner"
SUPABASE_ROLES = ("anon", "authenticated", "service_role")
SCOPES = ("login_ip", "login_cuenta", "refresh_ip", "validar_ip", "aceptar_ip")
# Ventanas que la purga puede borrar: más viejas que la ventana máxima configurable.
PURGE_CONDITION = "ventana_inicio < now() - interval '1 day'"

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
                f"La migración 0005 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def upgrade() -> None:
    conn = op.get_bind()
    quote = conn.dialect.identifier_preparer.quote
    app = quote(_app_role(conn))
    migrator = quote(conn.scalar(text("select current_user")))
    scopes = ", ".join(f"'{scope}'" for scope in SCOPES)

    statements = [
        f"""
        CREATE TABLE limite_tasa (
            ambito text NOT NULL CHECK (ambito IN ({scopes})),
            clave_hash bytea NOT NULL CHECK (octet_length(clave_hash) = 32),
            ventana_inicio timestamptz NOT NULL,
            intentos integer NOT NULL DEFAULT 0 CHECK (intentos >= 0),
            PRIMARY KEY (ambito, clave_hash, ventana_inicio)
        )
        """,
        "ALTER TABLE limite_tasa ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE limite_tasa FORCE ROW LEVEL SECURITY",
        # --- Aplicación: una política por comando, sin filtro de tenant ---
        f"CREATE POLICY limite_tasa_leer ON limite_tasa FOR SELECT TO {app} USING (true)",
        f"CREATE POLICY limite_tasa_contar ON limite_tasa FOR INSERT TO {app} "
        "WITH CHECK (intentos = 1)",
        f"CREATE POLICY limite_tasa_sumar ON limite_tasa FOR UPDATE TO {app} "
        "USING (true) WITH CHECK (intentos >= 0)",
        # --- Purga: solo el migrador (dueño) y solo ventanas de más de un día ---
        f"CREATE POLICY limite_tasa_purga_leer ON limite_tasa FOR SELECT TO {migrator} "
        f"USING ({PURGE_CONDITION})",
        f"CREATE POLICY limite_tasa_purga ON limite_tasa FOR DELETE TO {migrator} "
        f"USING ({PURGE_CONDITION})",
        # --- GRANT mínimos; nunca DELETE ni TRUNCATE para la aplicación ---
        "REVOKE ALL ON limite_tasa FROM PUBLIC",
        f"GRANT SELECT, INSERT ON limite_tasa TO {app}",
        f"GRANT UPDATE (intentos) ON limite_tasa TO {app}",
    ]
    for role in SUPABASE_ROLES:
        if conn.scalar(_ROLE_EXISTS, {"name": role}):
            statements.append(f"REVOKE ALL ON limite_tasa FROM {quote(role)}")
    execute_statements(conn, statements)


def downgrade() -> None:
    # DROP TABLE elimina también sus políticas y GRANT.
    execute_statements(op.get_bind(), ["DROP TABLE limite_tasa"])
