"""Cambios sobre activos existentes (spec 005, T1; R1–R7, Q1–Q3; plan.md §2).

- ``GRANT UPDATE`` por columna en ``activo`` al rol de la aplicación: solo lo editable
  (nombre, categoría, ubicación, serial, marca, modelo, subtipo, precio y fecha de
  compra), más ``estado``, ``row_version`` y ``actualizado_en``, que el servidor sube en
  cada cambio. Nunca ``codigo`` (inmutable, R8 de docs/03), ``id``, ``tenant_id``,
  ``creado_por``, ``creado_en``, ``atributos``, ``referencia`` ni ``color`` (no los
  expone la API). La RLS forzada de 0007 ya limita el ``UPDATE`` al tenant; el
  disparador D1 (``UPDATE OF ubicacion_id``) ya cubre mover.
- El ``CHECK`` de ``activo_evento.tipo`` suma ``datos_cambiados`` (Q3). El historial
  sigue inmutable: solo ``SELECT`` e ``INSERT``.

El rol de la aplicación se lee de ``APP_DB_USER`` y nunca aparece en los mensajes.
``downgrade`` quita el permiso y el tipo nuevo; falla (sin borrar nada) si ya hay
eventos ``datos_cambiados``.

Revision ID: 0008_activo_cambios
Revises: 0007_activos
Create Date: 2026-11-14
"""

import os
from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0008_activo_cambios"
down_revision: str | Sequence[str] | None = "0007_activos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

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
                f"La migración 0008 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


EDITABLES = (
    "nombre",
    "categoria_id",
    "ubicacion_id",
    "serial",
    "marca",
    "modelo",
    "subtipo",
    "precio_compra",
    "fecha_compra",
    "estado",
    "row_version",
    "actualizado_en",
)
EVENTOS_0007 = (
    "creado",
    "importado",
    "verificado",
    "ubicacion_cambiada",
    "precio_cambiado",
    "estado_cambiado",
    "categoria_cambiada",
    "dado_de_baja",
)
EVENTOS = (*EVENTOS_0007, "datos_cambiados")
CHECK = "activo_evento_tipo_check"


def _tipos(eventos: Sequence[str]) -> str:
    lista = ", ".join(f"'{e}'" for e in eventos)
    return f"ALTER TABLE activo_evento ADD CONSTRAINT {CHECK} CHECK (tipo IN ({lista}))"


def upgrade() -> None:
    conn = op.get_bind()
    app = conn.dialect.identifier_preparer.quote(_app_role(conn))
    execute_statements(
        conn,
        [
            f"GRANT UPDATE ({', '.join(EDITABLES)}) ON activo TO {app}",
            f"ALTER TABLE activo_evento DROP CONSTRAINT {CHECK}",
            _tipos(EVENTOS),
        ],
    )


def downgrade() -> None:
    conn = op.get_bind()
    app = conn.dialect.identifier_preparer.quote(_app_role(conn))
    execute_statements(
        conn,
        [
            f"REVOKE UPDATE ({', '.join(EDITABLES)}) ON activo FROM {app}",
            f"ALTER TABLE activo_evento DROP CONSTRAINT {CHECK}",
            _tipos(EVENTOS_0007),
        ],
    )
