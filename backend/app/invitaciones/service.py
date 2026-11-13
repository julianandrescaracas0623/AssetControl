"""Crear, validar y aceptar invitación (spec 002, T8–T9; R10, R11, Q7, Q13, Q16, Q17; plan.md §2.2).

**Crear (T8).**

- El token es opaco y de alta entropía (``new_token``); la base guarda solo
  ``sha256(sha256(token))`` (``token_storage_hash``, I1), igual que el script del
  operador (T5). El token en claro sale una sola vez, en el enlace
  ``/invitacion#<token>`` de la respuesta de creación (Q13); no se guarda ni se
  registra.
- El tenant es el de la ``tenant_session`` de la petición (el del token, ya
  validado contra ``membresia``); ``creada_por`` es el ``usuario_id`` del admin
  autenticado (la política ``RESTRICTIVE`` de la base exige que no sea nulo).
- ``expira_en = now() + 72 h`` (Q7) lo calcula la base.

**Validar y aceptar (T9).** Públicos y sin ``tenant_session``: llaman a
``acceso.validar_invitacion`` / ``acceso.aceptar_invitacion`` con la clave
``token_key(token)`` en su propia transacción (``app.db``).

- Aceptar recibe ``{token, nombre, password}``: el email, el tenant y el rol salen
  de la invitación dentro de la función de la base; nada de la petición los propone.
- La política de contraseña (Q9) se aplica **antes** de mirar el token y el hash
  Argon2 se calcula siempre, una vez, para todo intento que llega a la base: el
  costo no distingue un token vigente, vencido, usado, inexistente, mal formado o
  con email ya registrado (A20).
- Vencida, usada, inexistente, mal formada o email existente -> ``None``: la ruta
  responde el mismo ``invitacion_invalida`` (Q16).
- La sesión (acceso + refresh) se emite **después** del ``COMMIT`` con
  ``issue_session`` (R11, A22); si falla, la cuenta ya existe y se lanza
  ``SessionNotIssuedError`` (``500`` genérico): el invitado entra con el login.

H1 de T8 (decisión humana 2026-11-13, opción A): una invitación vigente sobrevive
hasta su vencimiento (72 h) a la baja o degradación de quien la creó; riesgo
aceptado para el piloto.

Nada de este módulo registra el token, su clave, la contraseña ni su hash.
"""

import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.credentials import get_passwords, new_token, token_key, token_storage_hash
from app.auth.models import Invitacion
from app.auth.service import LoginResult, issue_session, normalize_email
from app.db import aceptar_invitacion, validar_invitacion

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

    La usan esta API y el script del operador (T5; N1/H3 de T9): ``normalize_email``
    más una forma mínima, una sola ``@`` con parte local y dominio y sin espacios.
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


# --- Validar y aceptar (T9) ---------------------------------------------------------


class SessionNotIssuedError(RuntimeError):
    """La cuenta se creó (``COMMIT`` hecho) pero no se pudo emitir la sesión (A22)."""

    def __init__(self) -> None:
        super().__init__("Invitación aceptada sin sesión emitida; el invitado debe iniciar sesión.")


def invitation_key(token: str) -> str:
    """``token_key(token)``; si el token no se puede codificar, una clave que no existe.

    Un sustituto suelto daría ``UnicodeEncodeError`` (``500``). Se usa la clave de un
    token aleatorio nuevo: la consulta corre igual que con un token inexistente.
    """
    try:
        return token_key(token)
    except UnicodeEncodeError:
        pass
    return token_key(new_token())


def normalize_nombre(nombre: str) -> str | None:
    """Nombre sin espacios en los extremos; ``None`` si queda vacío, lleva caracteres de
    control (NUL, saltos de línea...) o un sustituto suelto (no codificable en UTF-8)."""
    value = nombre.strip()
    if not value or any(unicodedata.category(char) in ("Cc", "Cs") for char in value):
        return None
    return value


def is_valid_invitation(token: str) -> bool:
    """Vigente o no; no consume (``acceso.validar_invitacion``)."""
    return validar_invitacion(invitation_key(token))


def accept_invitation(token: str, nombre: str, password: str) -> LoginResult | None:
    """Acepta la invitación y emite la sesión, o ``None`` (``invitacion_invalida``).

    ``nombre`` ya normalizado. Lanza ``PasswordPolicyError`` antes de mirar el token
    si la contraseña no cumple Q9, y ``SessionNotIssuedError`` si la cuenta se creó
    pero la sesión no pudo emitirse.
    """
    password_hash = get_passwords().hash(password)
    accepted = aceptar_invitacion(invitation_key(token), nombre, password_hash)
    if accepted is None:
        return None
    result = issue_session(accepted.usuario_id, accepted.tenant_id)
    if result is None:
        raise SessionNotIssuedError()
    return result
