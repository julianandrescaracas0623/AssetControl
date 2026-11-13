"""Login y usuario actual (spec 002, T6; R7, Q6, Q7; plan.md §2.2).

**Login.** ``acceso.buscar_login`` corre sin tenant y en su propia transacción
(``app.db.buscar_login``), nunca dentro de ``tenant_session``. La contraseña se
verifica **siempre exactamente una vez** con ``Passwords.verify``: contra el
hash de la cuenta o, si no existe, contra el hash simulado del mismo costo
(A10). Toda causa de rechazo (contraseña mala, cuenta inexistente, usuario o
membresía inactivos, varias membresías activas, el ``False`` rápido de
``verify`` por longitud o sustituto suelto) devuelve ``None`` y la ruta
responde lo mismo. Con más de una membresía activa falla cerrado (Q6).

Con una sola membresía, se abre ``tenant_session`` con ese tenant y bajo RLS se
vuelven a leer ``membresia`` (``rol``, ``activa``, ``id``) y ``usuario.activo``:
lo que devolvió ``buscar_login`` solo elige el tenant. En esa transacción se
guarda el refresh: ``familia_id`` nueva, ``token_hash = sha256(sha256(secreto))``
y ``expira_en = now() + 7 días`` (Q7). La cookie lleva ``<tenant_id>.<secreto>``.

**Usuario actual.** ``authenticate`` valida el JWT (``HS256``, ``exp``, ``iss``,
``sub``, ``tenant``), fija el tenant del claim y lee ``rol`` y ``activa`` de
``membresia`` y ``activo`` de ``usuario`` en cada petición; el ``rol`` del claim
no se usa. Lo generalizan ``require_auth``/``require_role`` en T8.

Nada de este módulo registra contraseñas, tokens, hashes ni el email.
"""

import uuid
from dataclasses import dataclass

from flask import current_app
from sqlalchemy import func, select

from app.auth.credentials import (
    REFRESH_TOKEN_TTL,
    InvalidAccessTokenError,
    decode_access_token,
    encode_access_token,
    get_passwords,
    new_token,
    token_storage_hash,
)
from app.auth.models import Membresia, RefreshToken, Tenant, Usuario
from app.db import buscar_login, tenant_session


@dataclass(frozen=True)
class CurrentUser:
    usuario_id: uuid.UUID
    email: str
    nombre: str
    tenant_id: uuid.UUID
    tenant_nombre: str
    rol: str

    def to_json(self) -> dict[str, object]:
        return {
            "usuario": {"id": str(self.usuario_id), "email": self.email, "nombre": self.nombre},
            "tenant": {"id": str(self.tenant_id), "nombre": self.tenant_nombre},
            "rol": self.rol,
        }


@dataclass(frozen=True)
class LoginResult:
    user: CurrentUser
    access_token: str
    refresh_cookie_value: str


def normalize_email(email: str) -> str | None:
    """``lower(btrim())`` como la base; ``None`` si no puede ser un email guardado.

    Un sustituto suelto (no codificable en UTF-8) o un NUL harían fallar la
    consulta con un ``500``: se tratan como cuenta inexistente.
    """
    value = email.strip().lower()
    if not value or "\x00" in value:
        return None
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return None
    return value


def _load_current_user(session, usuario_id: uuid.UUID, tenant_id: uuid.UUID):
    """``(membresia, CurrentUser)`` si la membresía y el usuario están activos en el tenant."""
    membresia = session.scalars(
        select(Membresia).where(Membresia.usuario_id == usuario_id)
    ).one_or_none()
    if membresia is None or not membresia.activa:
        return None
    usuario = session.get(Usuario, usuario_id)
    tenant = session.get(Tenant, tenant_id)
    if usuario is None or not usuario.activo or tenant is None:
        return None
    user = CurrentUser(
        usuario_id=usuario.id,
        email=usuario.email,
        nombre=usuario.nombre,
        tenant_id=tenant.id,
        tenant_nombre=tenant.nombre,
        rol=membresia.rol,
    )
    return membresia, user


def login(email: str, password: str) -> LoginResult | None:
    """Emite acceso y refresh, o ``None`` ante cualquier rechazo (respuesta genérica)."""
    normalized = normalize_email(email)
    rows = buscar_login(normalized) if normalized is not None else []
    stored_hash = rows[0].password_hash if rows else None
    # Siempre una verificación (hash simulado sin cuenta), antes de mirar nada más.
    if not get_passwords().verify(stored_hash, password):
        return None
    account = rows[0]
    if not account.activo:
        return None
    active = [row for row in rows if row.tenant_id is not None]
    if len(active) != 1:
        if len(active) > 1:
            current_app.logger.warning(
                "Login rechazado: varias membresías activas (usuario_id=%s); falla cerrado (Q6).",
                account.usuario_id,
            )
        return None
    tenant_id = active[0].tenant_id

    secret = new_token()
    with tenant_session(tenant_id) as session:
        loaded = _load_current_user(session, account.usuario_id, tenant_id)
        if loaded is None:
            return None
        membresia, user = loaded
        session.add(
            RefreshToken(
                membresia_id=membresia.id,
                familia_id=uuid.uuid4(),
                token_hash=token_storage_hash(secret),
                expira_en=func.now() + REFRESH_TOKEN_TTL,
            )
        )

    access_token = encode_access_token(
        current_app.config["SECRET_KEY"],
        sub=user.usuario_id,
        tenant=user.tenant_id,
        rol=user.rol,
    )
    return LoginResult(
        user=user,
        access_token=access_token,
        refresh_cookie_value=f"{user.tenant_id}.{secret}",
    )


_BEARER_PREFIX = "bearer "


def authenticate(authorization: str | None) -> CurrentUser | None:
    """Usuario del ``Authorization: Bearer <jwt>``, o ``None`` si no autentica."""
    if not authorization or not authorization[: len(_BEARER_PREFIX)].lower() == _BEARER_PREFIX:
        return None
    token = authorization[len(_BEARER_PREFIX) :].strip()
    if not token:
        return None
    try:
        claims = decode_access_token(current_app.config["SECRET_KEY"], token)
    except InvalidAccessTokenError:
        return None
    with tenant_session(claims.tenant) as session:
        loaded = _load_current_user(session, claims.sub, claims.tenant)
    return None if loaded is None else loaded[1]
