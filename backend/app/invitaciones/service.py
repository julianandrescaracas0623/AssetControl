"""Crear invitación (spec 002, T8; R10, Q7, Q13, Q17; plan.md §2.2).

- El token es opaco y de alta entropía (``new_token``); la base guarda solo
  ``sha256(sha256(token))`` (``token_storage_hash``, I1), igual que el script del
  operador (T5). El token en claro sale una sola vez, en el enlace
  ``/invitacion#<token>`` de la respuesta de creación (Q13); no se guarda ni se
  registra.
- El tenant es el de la ``tenant_session`` de la petición (el del token, ya
  validado contra ``membresia``); ``creada_por`` es el ``usuario_id`` del admin
  autenticado (la política ``RESTRICTIVE`` de la base exige que no sea nulo).
- ``expira_en = now() + 72 h`` (Q7) lo calcula la base.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.credentials import new_token, token_storage_hash
from app.auth.models import Invitacion
from app.auth.service import normalize_email

INVITATION_TTL = timedelta(hours=72)
INVITATION_LINK_PREFIX = "/invitacion#"
INVITABLE_ROLES = frozenset({"admin", "contador"})


@dataclass(frozen=True)
class CreatedInvitation:
    id: uuid.UUID
    email: str
    rol: str
    expira_en: datetime
    # Fuera del repr: que un log accidental del objeto no lleve el token.
    token: str = field(repr=False)

    @property
    def enlace(self) -> str:
        return f"{INVITATION_LINK_PREFIX}{self.token}"


def normalize_invitation_email(email: str) -> str | None:
    """Email normalizado como lo exige el CHECK de ``invitacion``, o ``None`` si no vale.

    Misma forma mínima que el script del operador: una sola ``@`` con parte local
    y dominio, sin espacios, sin NUL ni sustitutos sueltos.
    """
    value = normalize_email(email)
    if value is None:
        return None
    local, at, domain = value.partition("@")
    if not at or not local or not domain or "@" in domain or any(c.isspace() for c in value):
        return None
    return value


def create_invitation(
    session: Session, *, creada_por: uuid.UUID, email: str, rol: str
) -> CreatedInvitation:
    """Inserta la invitación en el tenant de ``session``; ``email`` ya normalizado."""
    token = new_token()
    invitacion = Invitacion(
        email=email,
        rol=rol,
        token_hash=token_storage_hash(token),
        expira_en=func.now() + INVITATION_TTL,
        creada_por=creada_por,
    )
    session.add(invitacion)
    session.flush()
    return CreatedInvitation(
        id=invitacion.id,
        email=invitacion.email,
        rol=invitacion.rol,
        expira_en=invitacion.expira_en,
        token=token,
    )
