"""Revisión inicial vacía (spec 001, T6).

No crea tablas de negocio: solo fija el punto de partida de la cadena de
revisiones. Las tablas de negocio llegan desde la spec 002 con el patrón
obligatorio de ``migrations/README.md``.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-11-12
"""

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
