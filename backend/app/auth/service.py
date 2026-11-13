"""Login, usuario actual, refresh y logout (spec 002, T6–T7; R7, R8, Q6, Q7, Q15; plan.md §2.2).

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

**Usuario actual (T8).** ``access_claims`` valida el JWT (``HS256``, ``exp``,
``iss``, ``sub``, ``tenant``) y ``load_current_user`` lee, bajo la
``tenant_session`` del tenant del claim, ``rol`` y ``activa`` de ``membresia`` y
``activo`` de ``usuario`` en cada petición; el ``rol`` del claim no se usa. Los
combinan ``require_auth``/``require_role`` (``app.auth.decorators``).

**Refresh y logout (T7).** Ver ``refresh`` y ``logout``: rotación atómica con
familia, ventana de gracia de reuso (Q15) y revocación de la familia de la
cookie; todo bajo ``tenant_session`` con el tenant de la cookie.

Nada de este módulo registra contraseñas, tokens, hashes ni el email.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import timedelta

from flask import current_app
from sqlalchemy import func, select, update

from app.auth.credentials import (
    REFRESH_TOKEN_TTL,
    AccessClaims,
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


# --- Refresh y logout (T7; R8, Q2, Q15) --------------------------------------------

# Q15: un refresh ya usado hace menos de esto responde 401 sin revocar (dos pestañas
# que rotan a la vez); pasado este tiempo, su reuso revoca la familia.
REFRESH_REUSE_GRACE = timedelta(seconds=10)
# Holgado para el secreto de ``new_token`` (43 caracteres base64url).
_REFRESH_SECRET = re.compile(r"[A-Za-z0-9_-]{1,128}")


def parse_refresh_cookie(value: str | None) -> tuple[uuid.UUID, str] | None:
    """``(tenant_id, secreto)`` de ``<tenant_id>.<secreto>``, o ``None`` si no tiene la forma.

    El ``tenant_id`` debe ser un UUID en forma canónica; solo propone el tenant:
    el secreto se busca bajo RLS de ese tenant.
    """
    if not value:
        return None
    tenant_part, sep, secret = value.partition(".")
    if not sep or not _REFRESH_SECRET.fullmatch(secret):
        return None
    try:
        tenant_id = uuid.UUID(tenant_part)
    except ValueError:
        return None
    if str(tenant_id) != tenant_part:
        return None
    return tenant_id, secret


def refresh(cookie_value: str | None) -> LoginResult | None:
    """Rota el refresh de la cookie y emite un acceso nuevo, o ``None`` (``401`` genérico).

    1. ``tenant_session`` con el tenant de la cookie; RLS acota todo a ese tenant.
    2. Un único ``UPDATE`` atómico marca ``usado_en`` solo si es nulo, no está
       revocado y no venció. Con dos peticiones a la vez, la segunda espera el
       candado de la fila, reevalúa el ``WHERE`` y no rota.
    3. Si rota: se releen ``membresia`` (``rol``, ``activa``) y ``usuario.activo``
       por la ``membresia_id`` del refresh; si siguen activos se inserta el
       siguiente de la misma ``familia_id`` (7 días) y el acceso sale de
       ``membresia``. Si no, el refresh queda usado y no se emite nada.
    4. Si no rota y el hash existe ya usado fuera de la ventana de gracia
       (Q15), se revoca toda su familia (solo esa) y se responde lo mismo.
    """
    parsed = parse_refresh_cookie(cookie_value)
    if parsed is None:
        return None
    tenant_id, secret = parsed
    stored = token_storage_hash(secret)
    new_secret = new_token()

    with tenant_session(tenant_id) as session:
        rotated = session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == stored,
                RefreshToken.usado_en.is_(None),
                RefreshToken.revocado_en.is_(None),
                RefreshToken.expira_en > func.now(),
            )
            .values(usado_en=func.now())
            .returning(RefreshToken.membresia_id, RefreshToken.familia_id),
            execution_options={"synchronize_session": False},
        ).one_or_none()

        if rotated is None:
            _revoke_family_on_reuse(session, stored)
            return None

        membresia = session.get(Membresia, rotated.membresia_id)
        if membresia is None:
            return None
        loaded = _load_current_user(session, membresia.usuario_id, tenant_id)
        if loaded is None or loaded[0].id != membresia.id:
            return None
        membresia, user = loaded
        session.add(
            RefreshToken(
                membresia_id=membresia.id,
                familia_id=rotated.familia_id,
                token_hash=token_storage_hash(new_secret),
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
        refresh_cookie_value=f"{user.tenant_id}.{new_secret}",
    )


def _revoke_family_on_reuse(session, stored: bytes) -> None:
    """Q15: si ``stored`` ya se usó fuera de la ventana de gracia, revoca su familia."""
    reused = session.execute(
        select(RefreshToken.familia_id).where(
            RefreshToken.token_hash == stored,
            RefreshToken.usado_en.is_not(None),
            RefreshToken.revocado_en.is_(None),
            RefreshToken.usado_en <= func.now() - REFRESH_REUSE_GRACE,
        )
    ).one_or_none()
    if reused is None:
        return
    _revoke_family(session, reused.familia_id)


_REVOKE_FAMILY_MAX_PASSES = 10


def _revoke_family(session, familia_id: uuid.UUID) -> None:
    """Revoca toda la familia, también el sucesor de una rotación en vuelo (M1, A11).

    En READ COMMITTED cada ``UPDATE`` toma su propia instantánea: si otra
    transacción rotó la familia y aún no confirmó, el ``UPDATE`` espera el candado
    de la fila vieja, la revoca al confirmarse la otra y **no** ve el sucesor que
    esta insertó. Por eso se repite la pasada hasta que no afecte filas: la
    siguiente ya ve el sucesor confirmado, y una rotación posterior sobre una fila
    ya revocada no prospera (su ``WHERE`` exige ``revocado_en IS NULL``). Cada
    pasada con filas solo puede deberse a una rotación que confirmó mientras se
    esperaba un candado; el tope evita un bucle sin fin.
    """
    for _ in range(_REVOKE_FAMILY_MAX_PASSES):
        result = session.execute(
            update(RefreshToken)
            .where(RefreshToken.familia_id == familia_id, RefreshToken.revocado_en.is_(None))
            .values(revocado_en=func.now()),
            execution_options={"synchronize_session": False},
        )
        if result.rowcount == 0:
            return


def logout(cookie_value: str | None) -> None:
    """Revoca la familia del refresh de la cookie (A11); sin cookie válida no hace nada.

    No depende del token de acceso. **N4 (Q7/A11):** el JWT de acceso ya emitido
    no se revoca: sigue sirviendo hasta su ``exp`` (15 min). Un login nuevo
    tampoco revoca familias anteriores (N6: la spec no lo pide; varios
    dispositivos).
    """
    parsed = parse_refresh_cookie(cookie_value)
    if parsed is None:
        return
    tenant_id, secret = parsed
    stored = token_storage_hash(secret)
    with tenant_session(tenant_id) as session:
        found = session.execute(
            select(RefreshToken.familia_id).where(RefreshToken.token_hash == stored)
        ).one_or_none()
        if found is not None:
            _revoke_family(session, found.familia_id)


_BEARER_PREFIX = "bearer "


def access_claims(authorization: str | None) -> AccessClaims | None:
    """Claims del ``Authorization: Bearer <jwt>`` válido, o ``None`` (``401``).

    Solo proponen ``sub`` y ``tenant``: el rol y la vigencia se leen de la base
    con ``load_current_user`` (``app.auth.decorators``).
    """
    if not authorization or not authorization[: len(_BEARER_PREFIX)].lower() == _BEARER_PREFIX:
        return None
    token = authorization[len(_BEARER_PREFIX) :].strip()
    if not token:
        return None
    try:
        return decode_access_token(current_app.config["SECRET_KEY"], token)
    except InvalidAccessTokenError:
        return None


def load_current_user(session, usuario_id: uuid.UUID, tenant_id: uuid.UUID) -> CurrentUser | None:
    """Usuario con membresía y cuenta activas en el tenant de ``session``, o ``None``.

    ``session`` es la ``tenant_session`` de ``tenant_id``: RLS acota la lectura.
    """
    loaded = _load_current_user(session, usuario_id, tenant_id)
    return None if loaded is None else loaded[1]
