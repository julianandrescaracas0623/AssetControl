"""Login, desarrollador actual, refresh y logout de la consola (spec 017, T2; R2–R6).

Paralelo a ``app.auth.service`` de la spec 002 y sin mezclarse con él:

**Login.** ``acceso.plataforma_buscar_login`` corre sin tenant ni desarrollador, en su
propia transacción (``app.db.plataforma_buscar_login``). La contraseña se verifica
**siempre exactamente una vez** con ``Passwords.verify``: contra el hash del
desarrollador o, si no existe (o el correo no se puede normalizar), contra el hash
simulado del mismo costo. Correo inexistente, contraseña errónea y desarrollador
inactivo devuelven ``None`` y la ruta responde el mismo ``401``. El hash solo vive en
esta función: nunca se devuelve, registra ni audita. Si pasa, bajo
``plataforma_session`` se relee ``desarrollador.activo`` y en esa transacción se guardan
el refresh (familia nueva, 8 h) y la auditoría ``login_ok``.

**Petición autenticada.** ``platform_claims`` valida el JWT de plataforma y
``load_current_desarrollador`` lee, bajo la ``plataforma_session`` del ``sub``, que el
desarrollador sigue activo **y** que la familia de refresh del token (``fam``) tiene
alguna fila sin revocar. Desactivar o restablecer por CLI, el logout y el reuso de un
refresh revocan la familia: el token vigente da ``401`` en su siguiente petición (A20).

**Refresh y logout.** Como en la 002: rotación atómica con familia, ventana de gracia de
reuso (10 s) y revocación de la familia, todo bajo la ``plataforma_session`` del
desarrollador de la cookie (RLS acota la búsqueda del secreto).

Nada de este módulo registra contraseñas, tokens, hashes ni el correo.
"""

import uuid
from dataclasses import dataclass
from datetime import timedelta

from flask import current_app
from sqlalchemy import exists, func, select, update
from sqlalchemy.orm import Session

from app.auth.credentials import get_passwords, new_token, token_storage_hash
from app.auth.service import normalize_email
from app.db import plataforma_buscar_login, plataforma_session
from app.plataforma import auditoria
from app.plataforma.credenciales import (
    PLATAFORMA_REFRESH_TTL,
    InvalidPlatformTokenError,
    PlatformClaims,
    decode_platform_token,
    encode_platform_token,
    parse_refresh_cookie,
)
from app.plataforma.models import Desarrollador, PlataformaRefreshToken

# Q15 de la 002: un refresh ya usado hace menos de esto responde 401 sin revocar.
REFRESH_REUSE_GRACE = timedelta(seconds=10)
_REVOKE_FAMILY_MAX_PASSES = 10
_BEARER_PREFIX = "bearer "


@dataclass(frozen=True)
class CurrentDesarrollador:
    id: uuid.UUID
    email: str
    nombre: str

    def to_json(self) -> dict[str, object]:
        return {"desarrollador": {"id": str(self.id), "email": self.email, "nombre": self.nombre}}


@dataclass(frozen=True)
class PlatformSession:
    desarrollador: CurrentDesarrollador
    access_token: str
    refresh_cookie_value: str


def _active(session: Session, desarrollador_id: uuid.UUID) -> CurrentDesarrollador | None:
    row = session.execute(
        select(
            Desarrollador.id, Desarrollador.email, Desarrollador.nombre, Desarrollador.activo
        ).where(Desarrollador.id == desarrollador_id)
    ).one_or_none()
    if row is None or not row.activo:
        return None
    return CurrentDesarrollador(id=row.id, email=row.email, nombre=row.nombre)


def _issue(desarrollador: CurrentDesarrollador, familia: uuid.UUID, secret: str) -> PlatformSession:
    token = encode_platform_token(
        current_app.config["SECRET_KEY"], sub=desarrollador.id, familia=familia
    )
    return PlatformSession(
        desarrollador=desarrollador,
        access_token=token,
        refresh_cookie_value=f"{desarrollador.id}.{secret}",
    )


def login(email: str, password: str) -> PlatformSession | None:
    """Emite acceso y refresh, o ``None`` ante cualquier rechazo (``401`` genérico)."""
    normalized = normalize_email(email)
    account = plataforma_buscar_login(normalized) if normalized is not None else None
    stored_hash = account.password_hash if account is not None else None
    # Siempre una verificación (hash simulado sin cuenta), antes de mirar nada más.
    if not get_passwords().verify(stored_hash, password):
        return None
    if account is None or not account.activo:
        return None

    secret = new_token()
    familia = uuid.uuid4()
    with plataforma_session(account.id) as session:
        desarrollador = _active(session, account.id)
        if desarrollador is None:
            return None
        session.add(
            PlataformaRefreshToken(
                desarrollador_id=desarrollador.id,
                familia_id=familia,
                token_hash=token_storage_hash(secret),
                expira_en=func.now() + PLATAFORMA_REFRESH_TTL,
            )
        )
        auditoria.registrar(session, "login_ok", objeto_id=desarrollador.id)
    return _issue(desarrollador, familia, secret)


def platform_claims(authorization: str | None) -> PlatformClaims | None:
    """Claims del ``Authorization: Bearer <jwt>`` de plataforma válido, o ``None``."""
    if not authorization or authorization[: len(_BEARER_PREFIX)].lower() != _BEARER_PREFIX:
        return None
    token = authorization[len(_BEARER_PREFIX) :].strip()
    if not token:
        return None
    try:
        return decode_platform_token(current_app.config["SECRET_KEY"], token)
    except InvalidPlatformTokenError:
        return None


def _family_alive(session: Session, familia: uuid.UUID) -> bool:
    return bool(
        session.scalar(
            select(
                exists().where(
                    PlataformaRefreshToken.familia_id == familia,
                    PlataformaRefreshToken.revocado_en.is_(None),
                )
            )
        )
    )


def load_current_desarrollador(
    session: Session, claims: PlatformClaims
) -> CurrentDesarrollador | None:
    """Desarrollador activo con la familia del token viva, o ``None`` (``401``).

    ``session`` es la ``plataforma_session`` de ``claims.sub``: RLS acota la lectura.
    """
    desarrollador = _active(session, claims.sub)
    if desarrollador is None or not _family_alive(session, claims.familia):
        return None
    return desarrollador


def refresh(cookie_value: str | None) -> PlatformSession | None:
    """Rota el refresh de la cookie y emite un acceso nuevo, o ``None`` (``401``)."""
    parsed = parse_refresh_cookie(cookie_value)
    if parsed is None:
        return None
    desarrollador_id, secret = parsed
    stored = token_storage_hash(secret)
    new_secret = new_token()

    with plataforma_session(desarrollador_id) as session:
        rotated = session.execute(
            update(PlataformaRefreshToken)
            .where(
                PlataformaRefreshToken.token_hash == stored,
                PlataformaRefreshToken.usado_en.is_(None),
                PlataformaRefreshToken.revocado_en.is_(None),
                PlataformaRefreshToken.expira_en > func.now(),
            )
            .values(usado_en=func.now())
            .returning(PlataformaRefreshToken.desarrollador_id, PlataformaRefreshToken.familia_id),
            execution_options={"synchronize_session": False},
        ).one_or_none()
        if rotated is None:
            _revoke_family_on_reuse(session, stored)
            return None
        desarrollador = _active(session, rotated.desarrollador_id)
        if desarrollador is None:
            return None
        session.add(
            PlataformaRefreshToken(
                desarrollador_id=desarrollador.id,
                familia_id=rotated.familia_id,
                token_hash=token_storage_hash(new_secret),
                expira_en=func.now() + PLATAFORMA_REFRESH_TTL,
            )
        )
    return _issue(desarrollador, rotated.familia_id, new_secret)


def _revoke_family_on_reuse(session: Session, stored: bytes) -> None:
    """Si ``stored`` ya se usó fuera de la ventana de gracia, revoca su familia."""
    reused = session.execute(
        select(PlataformaRefreshToken.familia_id).where(
            PlataformaRefreshToken.token_hash == stored,
            PlataformaRefreshToken.usado_en.is_not(None),
            PlataformaRefreshToken.revocado_en.is_(None),
            PlataformaRefreshToken.usado_en <= func.now() - REFRESH_REUSE_GRACE,
        )
    ).one_or_none()
    if reused is not None:
        _revoke_family(session, reused.familia_id)


def _revoke_family(session: Session, familia_id: uuid.UUID) -> None:
    """Revoca toda la familia, también un sucesor de una rotación en vuelo (M1 de la 002)."""
    for _ in range(_REVOKE_FAMILY_MAX_PASSES):
        result = session.execute(
            update(PlataformaRefreshToken)
            .where(
                PlataformaRefreshToken.familia_id == familia_id,
                PlataformaRefreshToken.revocado_en.is_(None),
            )
            .values(revocado_en=func.now()),
            execution_options={"synchronize_session": False},
        )
        if result.rowcount == 0:
            return


def logout(cookie_value: str | None) -> None:
    """Revoca la familia del refresh de la cookie; sin cookie válida no hace nada.

    Al revocar la familia, el token de acceso de esa sesión también deja de servir
    (``load_current_desarrollador`` comprueba la familia en cada petición).
    """
    parsed = parse_refresh_cookie(cookie_value)
    if parsed is None:
        return
    desarrollador_id, secret = parsed
    stored = token_storage_hash(secret)
    with plataforma_session(desarrollador_id) as session:
        found = session.execute(
            select(PlataformaRefreshToken.familia_id).where(
                PlataformaRefreshToken.token_hash == stored
            )
        ).one_or_none()
        if found is not None:
            _revoke_family(session, found.familia_id)
