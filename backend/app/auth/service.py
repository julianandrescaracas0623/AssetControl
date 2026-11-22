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

**Cambio de contraseña (spec 017, T4; R27).** Ver ``cambiar_contrasena``: verifica la
actual con Argon2, guarda la nueva con ``acceso.cambiar_password_propio`` (marca en
``false`` y refresh revocados) y emite una familia nueva, todo en la ``tenant_session`` de
la petición. **M1 (0026):** la función pone también ``usuario.sesiones_validas_desde =
now()`` y ``load_current_user`` rechaza (``401``) todo JWT de acceso con ``iat`` anterior a
ese segundo; lo mismo tras restablecer por correo (014). Todo acceso (login, refresh y
sesión nueva del cambio) sale de ``emitir_acceso`` con un ``iat`` que nunca es anterior al
corte (``access_issued_at``). N4 sigue para el ``logout``.

**Desactivar desde la consola (spec 017, T5; 0027).** ``issue_session`` y ``refresh`` toman
el candado consultivo **compartido** del tenant (``bloquear_membresias``) antes de leer la
membresía; ``acceso.plataforma_cambiar_estado_membresia`` toma el mismo en exclusivo. Así
un login o una rotación a la vez que se desactiva o confirma antes (y la función revoca su
refresh nuevo) o espera y ya ve la membresía inactiva: no queda un refresh vivo de una
membresía desactivada. El cambio de contraseña (``cambiar_contrasena``) toma el mismo
candado antes de ``acceso.cambiar_password_propio``. La espera la acota
``LOCK_TIMEOUT_MEMBRESIAS`` (3 s, local a la transacción y restaurado tras tomarlo): si no
llega, ``503`` genérico con ``Retry-After``.

**Carrera login frente a cambio de contraseña (spec 017, T17; D48).** El login verifica con
Argon2 un hash leído en otra transacción. ``issue_session``, tras el candado compartido y en
la **misma** transacción y conexión donde inserta el refresh, relee ``acceso.buscar_login``
(``app.db.releer_login``) y no emite nada si no hay filas, si el ``usuario_id`` no es el
mismo o si el hash difiere del verificado: un cambio confirmado antes de esa relectura
(consola, cambio propio, 014 o cualquier otra vía, con corte o sin él) deja el login en el
``401`` genérico. Lo que confirma después no se ve; ver ``issue_session``.

Nada de este módulo registra contraseñas, tokens, hashes ni el email.
"""

import hmac
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from flask import current_app
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError

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
from app.db import (
    buscar_login,
    cambiar_password_propio,
    candado_compartido_acotado,
    releer_login,
    tenant_session,
)
from app.errors import ServiceUnavailableError


@dataclass(frozen=True)
class CurrentUser:
    usuario_id: uuid.UUID
    email: str
    nombre: str
    tenant_id: uuid.UUID
    tenant_nombre: str
    rol: str
    # Spec 017 (R26): leída de la base en cada petición; el JWT no la lleva.
    debe_cambiar_password: bool = False
    # Spec 017, T4 (M1, 0026): corte de los JWT de acceso; no se serializa.
    sesiones_validas_desde: datetime | None = None

    def to_json(self) -> dict[str, object]:
        return {
            "usuario": {"id": str(self.usuario_id), "email": self.email, "nombre": self.nombre},
            "tenant": {"id": str(self.tenant_id), "nombre": self.tenant_nombre},
            "rol": self.rol,
            "debe_cambiar_password": self.debe_cambiar_password,
        }


@dataclass(frozen=True)
class LoginResult:
    user: CurrentUser
    access_token: str
    refresh_cookie_value: str


# N1/H3 (T9): categorías que impiden garantizar que la salida cumple el CHECK
# ``email = lower(btrim(email))`` de la base. ``Cn``: sin asignar en la base de
# Unicode de Python (15.0 en 3.12), pero PostgreSQL 17 puede conocerlo y pasarlo a
# minúsculas (U+1C89, U+A7CB, U+10D50...). ``Lu``/``Lt``: mayúscula o titular que
# ``lower()`` deja igual y otra tabla de Unicode podría convertir.
_UNSTABLE_CASE_CATEGORIES = frozenset({"Cn", "Lu", "Lt"})


def normalize_email(email: str) -> str | None:
    """Único normalizador de email (login, invitaciones, script del operador y T10).

    ``strip().lower()`` y ``None`` si no se puede garantizar que el resultado cumple
    ``email = lower(btrim(email))`` de la base (``test_email_normalization`` lo
    comprueba con todos los code points contra PostgreSQL), o si haría fallar la
    consulta: vacío, NUL o sustituto suelto (no codificable en UTF-8). El login lo
    trata como cuenta inexistente; las altas responden ``400``.
    """
    value = email.strip().lower()
    if not value or "\x00" in value:
        return None
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return None
    if any(unicodedata.category(char) in _UNSTABLE_CASE_CATEGORIES for char in value):
        return None
    return value


def _load_current_user(session, usuario_id: uuid.UUID, tenant_id: uuid.UUID):
    """``(membresia, CurrentUser)`` si la membresía, el usuario y el tenant están activos.

    Punto único de ``load_current_user`` (cada petición), ``refresh`` e ``issue_session``
    (login y aceptación de invitación). Spec 017 (R22, A9; plan §2.5): una empresa
    desactivada desde la consola (``tenant.activo`` falso, leído en cada llamada, sin
    caché) da ``None``, el mismo ``401`` genérico que una membresía revocada.
    """
    membresia = session.scalars(
        select(Membresia).where(Membresia.usuario_id == usuario_id)
    ).one_or_none()
    if membresia is None or not membresia.activa:
        return None
    usuario = session.get(Usuario, usuario_id)
    tenant = session.get(Tenant, tenant_id)
    if usuario is None or not usuario.activo or tenant is None or not tenant.activo:
        return None
    user = CurrentUser(
        usuario_id=usuario.id,
        email=usuario.email,
        nombre=usuario.nombre,
        tenant_id=tenant.id,
        tenant_nombre=tenant.nombre,
        rol=membresia.rol,
        debe_cambiar_password=usuario.debe_cambiar_password,
        sesiones_validas_desde=usuario.sesiones_validas_desde,
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
    return issue_session(
        account.usuario_id,
        active[0].tenant_id,
        verificado_hash=account.password_hash,
        email=normalized,
    )


# Misma clave que el candado exclusivo de acceso.plataforma_cambiar_estado_membresia (0027).
CANDADO_MEMBRESIAS = "plataforma_membresia:"


# Espera máxima del candado compartido (login, refresh, invitación, cambio de contraseña):
# pasado este tiempo, ``503`` genérico con ``Retry-After`` en vez de colgar la petición.
LOCK_TIMEOUT_MEMBRESIAS = "3s"
# Candado no obtenido, interbloqueo y fallo de serialización: transitorios del cambio de
# contraseña, ``503`` sin eco de la base.
SQLSTATE_TRANSITORIOS = frozenset({"55P03", "40P01", "40001"})


def sqlstate(exc: DBAPIError) -> str | None:
    """SQLSTATE del error del driver, sin leer su mensaje."""
    return getattr(exc.orig, "sqlstate", None)


def bloquear_membresias(session, tenant_id: uuid.UUID) -> None:
    """Candado consultivo compartido del tenant mientras se emite o rota un refresh.

    Entre logins y refresh no se estorban (compartido); espera solo a un cambio de
    membresía de la consola en curso (exclusivo, unos milisegundos, acotado por su
    ``lock_timeout``). Va antes de cualquier otro candado de la transacción.

    La espera la acota ``LOCK_TIMEOUT_MEMBRESIAS`` (``app.db.candado_compartido_acotado``:
    local a la transacción y restaurado al valor previo tras tomarlo): si no llega,
    ``ServiceUnavailableError`` (``503`` con ``Retry-After``) y quien llama revierte su
    transacción.
    """
    clave = f"{CANDADO_MEMBRESIAS}{uuid.UUID(str(tenant_id))}"
    if not candado_compartido_acotado(session, clave, LOCK_TIMEOUT_MEMBRESIAS):
        raise ServiceUnavailableError()


def _mismo_hash(verificado: str, releido: str) -> bool:
    return hmac.compare_digest(verificado.encode("utf-8"), releido.encode("utf-8"))


def issue_session(
    usuario_id: uuid.UUID,
    tenant_id: uuid.UUID,
    *,
    verificado_hash: str | None = None,
    email: str | None = None,
) -> LoginResult | None:
    """Acceso y refresh nuevos (familia nueva) para la membresía activa en ``tenant_id``.

    Lo usan el login y la aceptación de invitación (T9, después del ``COMMIT`` de
    ``aceptar_invitacion``, R11/A22). Bajo ``tenant_session`` relee ``membresia`` y
    ``usuario.activo``; ``None`` si ya no están activos.

    Spec 017, T17 (D48): el login pasa ``verificado_hash`` (el hash que verificó con Argon2)
    y ``email`` (normalizado). Tras el candado compartido y ``_load_current_user``, en la
    **misma** transacción y conexión donde se inserta el refresh, se relee
    ``acceso.buscar_login(email)``: sin filas, con otro ``usuario_id`` o con un hash distinto
    (``hmac.compare_digest``), ``None``, la ruta responde el mismo ``401
    credenciales_invalidas`` y no se crea familia ni JWT. Así no emite sesión un login que
    verificó una contraseña ya cambiada por un cambio **confirmado** antes de la relectura
    (consola, cambio propio, 014 o cualquier vía, con o sin corte), sin depender de relojes.
    La invitación no lo pasa: la cuenta se acaba de crear con esa contraseña.

    Residual (``docs/02``): un cambio que aún no confirmó no se ve. En la consola el candado
    exclusivo por empresa lo ordena (o espera a este login y luego revoca su refresh, o este
    espera y ve el hash nuevo). En el cambio propio y la 014 no hay candado común: si el
    ``INSERT`` del refresh confirma después de la sentencia de revocación del cambio y antes
    de su ``COMMIT`` (milisegundos), esa familia sobrevive; el ``refresh`` no compara el
    corte (solo ``load_current_user`` lo hace con el JWT) y el JWT emitido vale hasta 15 min
    (clase N4).
    """
    if (verificado_hash is None) != (email is None):
        raise ValueError("verificado_hash y email van juntos.")
    secret = new_token()
    with tenant_session(tenant_id) as session:
        bloquear_membresias(session, tenant_id)
        loaded = _load_current_user(session, usuario_id, tenant_id)
        if loaded is None:
            return None
        membresia, user = loaded
        if verificado_hash is not None and email is not None:
            rows = releer_login(session, email)
            if (
                not rows
                or rows[0].usuario_id != usuario_id
                or not _mismo_hash(verificado_hash, rows[0].password_hash)
            ):
                current_app.logger.info(
                    "Login rechazado: la contraseña cambió durante la verificación "
                    "(usuario_id=%s; D48).",
                    usuario_id,
                )
                return None
        session.add(
            RefreshToken(
                membresia_id=membresia.id,
                familia_id=uuid.uuid4(),
                token_hash=token_storage_hash(secret),
                expira_en=func.now() + REFRESH_TOKEN_TTL,
            )
        )

    return LoginResult(
        user=user,
        access_token=emitir_acceso(user),
        refresh_cookie_value=f"{user.tenant_id}.{secret}",
    )


def access_issued_at(user: CurrentUser) -> datetime:
    """``iat`` del acceso nuevo de ``user``: ``max(ahora de Flask, floor(corte))`` (M1).

    El corte (``usuario.sesiones_validas_desde``) es ``now()`` de PostgreSQL. Si el reloj de
    Flask va detrás del de la base, un acceso emitido justo después del cambio o del
    restablecer tendría ``iat`` anterior al corte y ``load_current_user`` lo rechazaría (login
    ``200`` y ``401`` en la primera llamada). Usa el corte ya cargado en ``user`` (sin otra
    consulta). Sin corte, el reloj de Flask. La holgura de ``iat`` futuro del decodificador
    (``ACCESS_TOKEN_MAX_FUTURE_IAT``, O-2) exige NTP entre Flask y PostgreSQL.
    """
    issued = datetime.now(UTC)
    cut = user.sesiones_validas_desde
    if cut is None:
        return issued
    return max(issued, cut.replace(microsecond=0))


def emitir_acceso(user: CurrentUser) -> str:
    """JWT de acceso de ``user``; punto único del login, el refresh y el cambio (M1)."""
    return encode_access_token(
        current_app.config["SECRET_KEY"],
        sub=user.usuario_id,
        tenant=user.tenant_id,
        rol=user.rol,
        now=access_issued_at(user),
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
        # Antes de rotar: el candado de la fila del refresh viene después (mismo orden que
        # la función de la consola, sin interbloqueo).
        bloquear_membresias(session, tenant_id)
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

    return LoginResult(
        user=user,
        access_token=emitir_acceso(user),
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


def issued_before_cut(issued_at: int, cut: datetime | None) -> bool:
    """``True`` si un JWT con ``iat`` = ``issued_at`` es anterior al corte ``cut`` (M1).

    ``iat`` es entero en segundos y ``cut`` (``now()`` de PostgreSQL) tiene microsegundos:
    se compara con el segundo entero del corte (``floor``), así que un token emitido en el
    mismo segundo del corte vale (la sesión nueva del cambio nunca queda fuera).
    """
    if cut is None:
        return False
    return issued_at < int(cut.replace(microsecond=0).timestamp())


def load_current_user(
    session, usuario_id: uuid.UUID, tenant_id: uuid.UUID, *, issued_at: int
) -> CurrentUser | None:
    """Usuario con membresía y cuenta activas en el tenant de ``session``, o ``None``.

    ``session`` es la ``tenant_session`` de ``tenant_id``: RLS acota la lectura. Spec 017,
    T4 (M1, 0026): ``None`` también si el JWT (``issued_at``, su ``iat``) es anterior a
    ``usuario.sesiones_validas_desde`` (cambio o restablecer de la contraseña), el mismo
    ``401`` genérico. Solo el acceso del tenant; el de plataforma no pasa por aquí.
    """
    loaded = _load_current_user(session, usuario_id, tenant_id)
    if loaded is None:
        return None
    user = loaded[1]
    if issued_before_cut(issued_at, user.sesiones_validas_desde):
        return None
    return user


# --- Cambio de contraseña (spec 017, T4; R27; plan.md §2.6) -------------------------------


class _CuentaNoVigenteError(Exception):
    """La cuenta dejó de estar activa en medio del cambio: se revierte todo (``401``)."""


def _new_session(session, usuario_id: uuid.UUID, tenant_id: uuid.UUID) -> LoginResult:
    """Familia nueva de refresh y acceso nuevo en la transacción de ``session``."""
    loaded = _load_current_user(session, usuario_id, tenant_id)
    if loaded is None:
        raise _CuentaNoVigenteError()
    membresia, user = loaded
    secret = new_token()
    session.add(
        RefreshToken(
            membresia_id=membresia.id,
            familia_id=uuid.uuid4(),
            token_hash=token_storage_hash(secret),
            expira_en=func.now() + REFRESH_TOKEN_TTL,
        )
    )
    session.flush()
    # M1: el iat de la sesión nueva nunca es anterior al corte, aunque el reloj de Flask vaya
    # detrás del de la base.
    return LoginResult(
        user=user,
        access_token=emitir_acceso(user),
        refresh_cookie_value=f"{user.tenant_id}.{secret}",
    )


def cambiar_contrasena(session, user: CurrentUser, actual: str, nueva: str) -> LoginResult | None:
    """Cambia la contraseña de ``user`` y devuelve su sesión nueva, o ``None`` (``401``).

    ``session`` es la ``tenant_session`` de la petición (la de ``require_auth``) y ``nueva``
    ya cumple la política, coincide con su confirmación y difiere de ``actual`` (lo
    comprueba la ruta). Pasos:

    1. Hash guardado con ``acceso.buscar_login`` (transacción propia, como el login) y
       **una** verificación Argon2 de ``actual`` (hash simulado si no aparece la cuenta).
    2. Hash Argon2id de ``nueva`` (``503`` si Argon2 está saturado).
    3. ``acceso.cambiar_password_propio``: compara el hash guardado y lo reemplaza, pone
       ``debe_cambiar_password = false`` y ``sesiones_validas_desde = now()`` (M1) y
       revoca los refresh del usuario. Si la cuenta ya
       no es elegible o la contraseña cambió entretanto, ``None`` sin cambiar nada.
    4. Familia nueva para esta sesión (las demás quedaron revocadas) y acceso nuevo.

    Spec 017, T5: antes del paso 3 toma ``bloquear_membresias`` (compartido; el mismo orden
    que login y refresh: el candado consultivo antes que cualquier fila), así no cruza una
    desactivación de la consola: o confirma antes (y la consola revoca su familia nueva) o
    espera y la función ve la membresía inactiva (``None``, ``401``). Los pasos 3 y 4 van en
    un ``SAVEPOINT``: si la cuenta ya no se puede cargar en el 4, se revierte todo y ``None``
    (``401``, no ``500``). Candado no obtenido a tiempo, interbloqueo (``40P01``) o fallo de
    serialización (``40001``): ``ServiceUnavailableError`` (``503`` genérico, sin el mensaje
    de la base) y la ``tenant_session`` revierte.
    """
    rows = buscar_login(user.email)
    stored = rows[0].password_hash if rows and rows[0].usuario_id == user.usuario_id else None
    passwords = get_passwords()
    if not passwords.verify(stored, actual) or stored is None:
        return None
    nuevo_hash = passwords.hash(nueva)
    bloquear_membresias(session, user.tenant_id)
    resultado = None
    transitorio = False
    try:
        with session.begin_nested():
            if cambiar_password_propio(session, user.usuario_id, stored, nuevo_hash):
                # La función cambió la fila fuera del ORM: se relee la marca de la base.
                session.expire_all()
                resultado = _new_session(session, user.usuario_id, user.tenant_id)
    except _CuentaNoVigenteError:
        return None
    except DBAPIError as exc:
        if sqlstate(exc) not in SQLSTATE_TRANSITORIOS:
            raise
        transitorio = True
    if transitorio:
        # Fuera del except: sin causa ni contexto con el mensaje de la base.
        raise ServiceUnavailableError()
    return resultado
