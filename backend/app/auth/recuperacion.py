"""Recuperar y restablecer contraseña por correo (spec 014, T4; R1–R5, R8–R13, R16; plan §1, §5).

**Recuperar** (``solicitar``): token opaco nuevo en **toda** petición
(``secrets.token_urlsafe(32)``, ``new_token``), ``clave = sha256(token)`` en hex (la base
guarda ``sha256(clave)``, I1). Los contadores ``recuperar_ip`` y ``recuperar_cuenta`` y
``acceso.solicitar_recuperacion`` van en una sola transacción
(``limits.limit_recover_and_request``; M1 de la auditoría de T2). Solo tras el ``COMMIT``,
y solo si la función creó el enlace, se programa el correo con el correo normalizado y
el token recién generado (``Correo.enviar_recuperacion``: hilo aparte, nunca lanza), y se
hace al **cerrar la respuesta** (``response.call_on_close``, I1 de T4): ni el arranque
del hilo entra en la petición. El resultado nunca cambia la respuesta (R1): la ruta
responde siempre el mismo ``202``.

- Correo no normalizable, no ASCII o que no es una dirección simple: la función recibe
  ``""`` (mismas sentencias, cero filas: la GUC vacía no ve ninguna cuenta) y no se crea
  enlace. Un enlace que no se puede entregar solo invalidaría el pendiente de la persona.
- Sin correo configurado (``correo_activo`` falso) la ruta no llama aquí: mismo ``202``
  sin tocar la base (requisito 4 de T3).

**Restablecer** (``restablecer``): la política de contraseña ya la validó la ruta; Argon2
se calcula **siempre** (también con un token inválido o mal formado: mismo costo, R13),
con el semáforo de 002 (``503`` si está saturado), y **después** se llama a
``acceso.restablecer_contrasena`` en una transacción nueva y corta (``app.db``, B2).
Devuelve ``True`` solo si la función devolvió un ``usuario_id``.

Auditoría (M2 de T2): el cambio de contraseña se registra en el log de la app (``INFO``)
con ``usuario_id`` y ``request_id``; un enlace rechazado deja un ``WARNING`` solo con el
``request_id`` (T8). Nada de este módulo registra el correo, el token, la
clave, el enlace, la contraseña ni su hash.
"""

from flask import after_this_request, current_app
from flask.wrappers import Response

from app.auth import limits
from app.auth.credentials import get_passwords, new_token, token_key
from app.auth.service import normalize_email
from app.correo import get_correo
from app.correo.config import es_direccion_simple
from app.db import restablecer_contrasena
from app.errors import current_request_id

RECOVERY_MESSAGE = (
    "Si el correo está registrado, te enviamos un enlace para restablecer tu contraseña. "
    "Revisa tu bandeja de entrada."
)
INVALID_LINK_MESSAGE = "El enlace no es válido o ya venció. Pide uno nuevo."
INVALID_LINK = ("enlace_invalido", INVALID_LINK_MESSAGE)
# Lo que recibe la función cuando no hay un correo válido: con la GUC vacía las políticas
# del dueño no ven ninguna cuenta y la función ejecuta las mismas sentencias (R13).
SIN_DESTINO = ""


def destino_de(email: str) -> str | None:
    """Correo normalizado si es una dirección simple que se puede entregar; si no, ``None``."""
    normalized = normalize_email(email)
    if normalized is None or not es_direccion_simple(normalized):
        return None
    return normalized


def _clave(token: str) -> str:
    """``sha256(token)`` en hex; si no se puede codificar, la de un token nuevo (no existe)."""
    try:
        return token_key(token)
    except UnicodeEncodeError:
        pass
    return token_key(new_token())


def solicitar(email: str) -> None:
    """Cuenta, pide el enlace y, tras el ``COMMIT``, programa el correo (``429``/``503``)."""
    destino = destino_de(email)
    token = new_token()
    created = limits.limit_recover_and_request(email, destino or SIN_DESTINO, token_key(token))
    if not created or destino is None:
        return
    _programar_tras_responder(destino, token)


def _programar_tras_responder(destino: str, token: str) -> None:
    """Programa el correo para **después** de enviar la respuesta (I1 de T4, T8).

    ``response.call_on_close`` corre cuando el servidor WSGI ya escribió el cuerpo y
    cierra la respuesta: el arranque del hilo de envío (``hilo.start()``), que solo ocurre
    en la rama «se envía», no entra en la latencia que ve el cliente (R13). El contexto
    de la petición ya no existe entonces: la app, su logger y el ``request_id`` se
    capturan aquí. Solo se llega aquí tras el ``COMMIT`` (``limit_recover_and_request``).
    """
    correo = get_correo(current_app)
    logger = current_app.logger
    request_id = current_request_id()

    def enviar() -> None:
        failure: str | None = None
        try:
            correo.enviar_recuperacion(destino, token, request_id=request_id)
        except Exception as exc:  # noqa: BLE001 - el envío nunca cambia la respuesta (R1, R8)
            failure = type(exc).__name__
        if failure is not None:
            logger.warning(
                "Correo de recuperación no programado (request_id=%s, tipo=%s)",
                request_id,
                failure,
            )

    @after_this_request
    def _al_cerrar(response: Response) -> Response:
        response.call_on_close(enviar)
        return response


def restablecer(token: str, password: str) -> bool:
    """Argon2 siempre y luego ``acceso.restablecer_contrasena``; ``True`` si cambió.

    ``password`` ya cumple la política (la ruta la valida antes de contar).
    """
    password_hash = get_passwords().hash(password)
    usuario_id = restablecer_contrasena(_clave(token), password_hash)
    if usuario_id is None:
        # T8: solo el ``request_id``; nada del enlace, la cuenta ni el motivo.
        current_app.logger.warning(
            "Enlace de recuperación rechazado (request_id=%s)", current_request_id()
        )
        return False
    current_app.logger.info(
        "Contraseña restablecida por enlace de recuperación (request_id=%s, usuario_id=%s)",
        current_request_id(),
        usuario_id,
    )
    return True
