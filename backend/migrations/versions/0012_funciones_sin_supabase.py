"""Funciones de disparador sin ``EXECUTE`` para los roles de Supabase (spec 010b, T6; C8).

Supabase concede por defecto (``ALTER DEFAULT PRIVILEGES``) todo lo que el rol
``postgres`` crea en ``public`` a ``anon``, ``authenticated`` y ``service_role``. Las
migraciones ya revocan esos roles de cada tabla y de las funciones de ``acceso``, pero
las tres funciones de disparador de ``public`` solo se revocaban de ``PUBLIC``. Una
función ``RETURNS trigger`` no se puede llamar directamente, así que el riesgo es
nulo; esto cierra el hueco por defensa en profundidad y deja la regla de C8 sin
excepciones: los roles de Supabase no reciben nada.

En una base sin esos roles (local, CI) no hace nada. ``downgrade`` tampoco: no se
devuelven privilegios a los roles de Supabase.

Revision ID: 0012_funciones_sin_supabase
Revises: 0011_cierre_e_informe
Create Date: 2026-11-15
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "0012_funciones_sin_supabase"
down_revision: str | Sequence[str] | None = "0011_cierre_e_informe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SUPABASE_ROLES = ("anon", "authenticated", "service_role")
FUNCIONES = (
    "public.activo_ubicacion_valida()",
    "public.sesion_conteo_inmutable()",
    "public.conteo_cerrado_requerido()",
)
_ROLE_EXISTS = text("select exists (select 1 from pg_roles where rolname = :name)")


def upgrade() -> None:
    conn = op.get_bind()
    quote = conn.dialect.identifier_preparer.quote
    roles = [quote(r) for r in SUPABASE_ROLES if conn.scalar(_ROLE_EXISTS, {"name": r})]
    if not roles:
        return
    for funcion in FUNCIONES:
        conn.exec_driver_sql(
            f"REVOKE ALL ON FUNCTION {funcion} FROM {', '.join(roles)}",
            execution_options={"no_parameters": True},
        )


def downgrade() -> None:
    """Sin cambios: no se devuelven privilegios a los roles de Supabase."""
