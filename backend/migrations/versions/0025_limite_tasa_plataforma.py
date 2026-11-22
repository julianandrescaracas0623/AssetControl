"""Ámbitos propios de ``limite_tasa`` para la consola de plataforma (spec 017, T4; O1).

Hallazgo O1 de la revisión de seguridad de T3b: las acciones de Empresas no tenían tope por
desarrollador y el refresh de plataforma compartía ``refresh_ip`` con el del tenant. El
``CHECK`` de ``limite_tasa.ambito`` suma:

- ``plat_accion``: acciones de la consola (``POST`` y ``PATCH`` de ``/plataforma/empresas``)
  por desarrollador, contadas antes de Argon2 y de la base.
- ``plat_refresh_ip``: refresh de plataforma por IP, separado del refresh del tenant.

Solo cambia el ``CHECK`` (mismo nombre ``limite_tasa_ambito_check``, leído del catálogo como
en 0017); ni ``GRANT`` ni políticas. ``downgrade``: borra los contadores de esos dos ámbitos
y restaura el ``CHECK`` de 0017; si la RLS de la purga no deja borrarlos (sin
superusuario, solo alcanza ventanas de más de un día), falla con un mensaje claro y no deja
la tabla sin ``CHECK``.

Revision ID: 0025_limite_tasa_plataforma
Revises: 0024_cambio_password
Create Date: 2026-11-20
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0025_limite_tasa_plataforma"
down_revision: str | Sequence[str] | None = "0024_cambio_password"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCOPE_CHECK = "limite_tasa_ambito_check"
# Los de 0017 (en su orden) y los nuevos de esta migración.
OLD_SCOPES = (
    "login_ip",
    "login_cuenta",
    "refresh_ip",
    "validar_ip",
    "aceptar_ip",
    "recuperar_ip",
    "recuperar_cuenta",
    "restablecer_ip",
    "plat_login_ip",
    "plat_login_cuenta",
)
NEW_SCOPES = ("plat_accion", "plat_refresh_ip")

# CHECK de limite_tasa que solo mira la columna ambito (como 0015 y 0017).
_SCOPE_CHECKS = text(
    "select c.conname from pg_constraint c "
    "join pg_attribute a on a.attrelid = c.conrelid and a.attnum = any(c.conkey) "
    "where c.conrelid = 'public.limite_tasa'::regclass and c.contype = 'c' "
    "and a.attname = 'ambito' and array_length(c.conkey, 1) = 1"
)


def _scope_check_name(conn: Connection) -> str:
    """Nombre del único ``CHECK`` de ``ambito`` de ``limite_tasa``, leído del catálogo."""
    names = list(conn.scalars(_SCOPE_CHECKS))
    if len(names) != 1:
        raise RuntimeError(
            "La migración 0025 esperaba exactamente un CHECK sobre limite_tasa.ambito "
            f"y encontró {len(names)}: revisa el esquema antes de migrar."
        )
    return names[0]


def _scope_check(scopes: Sequence[str]) -> str:
    values = ", ".join(f"'{scope}'" for scope in scopes)
    return f"ALTER TABLE limite_tasa ADD CONSTRAINT {SCOPE_CHECK} CHECK (ambito IN ({values}))"


def execute_statements(conn: Connection, statements: Sequence[str]) -> None:
    """Ejecuta DDL tal cual, sin parámetros, y falla sin mostrar la sentencia."""
    for index, statement in enumerate(statements, start=1):
        failure = None
        try:
            conn.exec_driver_sql(statement, execution_options={"no_parameters": True})
        except SQLAlchemyError as exc:
            sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None) or "desconocido"
            failure = (
                f"La migración 0025 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def upgrade() -> None:
    conn = op.get_bind()
    current = conn.dialect.identifier_preparer.quote(_scope_check_name(conn))
    execute_statements(
        conn,
        [
            f"ALTER TABLE limite_tasa DROP CONSTRAINT {current}",
            _scope_check((*OLD_SCOPES, *NEW_SCOPES)),
        ],
    )


def downgrade() -> None:
    conn = op.get_bind()
    current = conn.dialect.identifier_preparer.quote(_scope_check_name(conn))
    new_scopes = ", ".join(f"'{scope}'" for scope in NEW_SCOPES)
    execute_statements(
        conn,
        [
            # Solo contadores de los ámbitos nuevos: el CHECK anterior no los admite.
            f"DELETE FROM limite_tasa WHERE ambito IN ({new_scopes})",  # noqa: S608
            f"ALTER TABLE limite_tasa DROP CONSTRAINT {current}",
        ],
    )
    failure = None
    try:
        conn.exec_driver_sql(_scope_check(OLD_SCOPES), execution_options={"no_parameters": True})
    except SQLAlchemyError as exc:
        sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None) or "desconocido"
        failure = (
            "La migración 0025 no puede revertirse: quedan en limite_tasa contadores de "
            "plat_accion o plat_refresh_ip que el migrador no pudo borrar (sin superusuario, "
            "la RLS de la purga solo alcanza ventanas de más de un día). Espera un día y "
            f"ejecuta flask purgar-limite-tasa ({type(exc).__name__}, SQLSTATE {sqlstate})."
        )
    if failure is not None:
        raise RuntimeError(failure) from None
