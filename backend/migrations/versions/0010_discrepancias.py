"""Discrepancias (spec 007, T1; R2, R4, R5, Q2; plan.md §2).

- ``activo_evento.tipo`` suma ``discrepancia_descartada`` (Q2).
- Índice único parcial: una verificación se resuelve como mucho una vez, con
  ``ubicacion_cambiada`` (aplicada) o ``discrepancia_descartada`` (R4). Los movimientos
  sin verificación (``verificacion_id`` nulo) no quedan limitados.

No toca permisos. ``downgrade`` quita el índice y el tipo; falla (sin borrar nada) si ya
hay eventos ``discrepancia_descartada``.

Revision ID: 0010_discrepancias
Revises: 0009_sesiones_y_verificacion
Create Date: 2026-11-14
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

revision: str = "0010_discrepancias"
down_revision: str | Sequence[str] | None = "0009_sesiones_y_verificacion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EVENTOS_0009 = (
    "creado",
    "importado",
    "verificado",
    "ubicacion_cambiada",
    "precio_cambiado",
    "estado_cambiado",
    "categoria_cambiada",
    "dado_de_baja",
    "datos_cambiados",
)
EVENTOS = (*EVENTOS_0009, "discrepancia_descartada")
CHECK = "activo_evento_tipo_check"
INDICE = "activo_evento_una_resolucion"


def execute_statements(conn: Connection, statements: Sequence[str]) -> None:
    """Ejecuta DDL tal cual, sin parámetros, y falla sin mostrar la sentencia."""
    for index, statement in enumerate(statements, start=1):
        failure = None
        try:
            conn.exec_driver_sql(statement, execution_options={"no_parameters": True})
        except SQLAlchemyError as exc:
            sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None) or "desconocido"
            failure = (
                f"La migración 0010 falló en la sentencia {index} de {len(statements)} "
                f"({type(exc).__name__}, SQLSTATE {sqlstate})."
            )
        if failure is not None:
            raise RuntimeError(failure) from None


def _tipos(eventos: Sequence[str]) -> str:
    lista = ", ".join(f"'{e}'" for e in eventos)
    return f"ALTER TABLE activo_evento ADD CONSTRAINT {CHECK} CHECK (tipo IN ({lista}))"


def upgrade() -> None:
    execute_statements(
        op.get_bind(),
        [
            f"ALTER TABLE activo_evento DROP CONSTRAINT {CHECK}",
            _tipos(EVENTOS),
            f"CREATE UNIQUE INDEX {INDICE} ON activo_evento (tenant_id, verificacion_id) "
            "WHERE verificacion_id IS NOT NULL "
            "AND tipo IN ('ubicacion_cambiada', 'discrepancia_descartada')",
        ],
    )


def downgrade() -> None:
    execute_statements(
        op.get_bind(),
        [
            f"DROP INDEX {INDICE}",
            f"ALTER TABLE activo_evento DROP CONSTRAINT {CHECK}",
            _tipos(EVENTOS_0009),
        ],
    )
