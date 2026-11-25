"""Cambio de rol y de activación de una persona de la empresa (solo admin; 0033).

Toda la regla vive en ``acceso.cambiar_membresia``: quién puede cambiar, la guardia de
último admin, la revocación de sesiones y el candado. Este módulo solo traduce el rechazo
de la base a un código de la aplicación. Un candado ocupado se eleva como
``ServiceUnavailableError`` (``503``) sin cambiar nada.
"""

import uuid

from app import db
from app.errors import ServiceUnavailableError


class CambioRechazado(Exception):
    """Rechazo de negocio; ``codigo`` es estable y no lleva datos de la base."""

    def __init__(self, codigo: str) -> None:
        self.codigo = codigo
        super().__init__(codigo)


def cambiar(
    session,
    *,
    actor_id: uuid.UUID,
    usuario_id: uuid.UUID,
    rol: str,
    activa: bool,
) -> db.ResultadoCambioMembresia:
    try:
        return db.cambiar_membresia(session, usuario_id, actor_id=actor_id, rol=rol, activa=activa)
    except db.MembresiaRechazada as exc:
        if exc.codigo == "membresia_ocupada":
            raise ServiceUnavailableError() from None
        raise CambioRechazado(exc.codigo) from None
