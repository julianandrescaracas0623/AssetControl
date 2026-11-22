"""Aviso por correo al definir una contraseña temporal (spec 017, C1d; R61–R64; plan §12.1).

``programar(session, tenant_id, usuario_id)`` se llama desde la vista de C1b **después**
de que la contraseña quedó definida y auditada en la ``plataforma_session``:

1. Si el correo está apagado (``correo_activo`` falso), no hace nada.
2. Lee el correo de la persona con ``plataforma_listar_usuarios`` (R29) dentro de un
   ``SAVEPOINT``: un fallo de esa lectura revierte solo el punto, nunca la contraseña.
   Sin una dirección simple (``recuperacion.destino_de``), no hay aviso.
3. Registra un ``after_this_request``: corre cuando ``require_desarrollador`` ya hizo el
   ``COMMIT`` y solo actúa si la respuesta es ``204`` (si el ``COMMIT`` falla, la respuesta
   es ``5xx`` y no se pide nada). Pide un enlace de la 014 sin sus contadores
   (``pedir_enlace_recuperacion``); si la función no lo crea o falla, el aviso sale sin
   enlace. El envío se programa al **cerrar la respuesta** (``call_on_close``), en el hilo
   acotado de ``Correo``.

Nada cambia la respuesta (R64). Los logs llevan solo el tipo de un fallo y el
``request_id``: nunca el correo, el token, la clave, el enlace ni el mensaje de la
excepción. Ni el enlace ni el aviso se auditan aparte.
"""

import uuid

from flask import after_this_request, current_app
from flask.wrappers import Response
from sqlalchemy.orm import Session

from app.auth.credentials import new_token, token_key
from app.auth.recuperacion import destino_de
from app.correo import correo_activo, get_correo
from app.db import pedir_enlace_recuperacion, plataforma_listar_usuarios
from app.errors import current_request_id


def _correo_de(session: Session, tenant_id: uuid.UUID, usuario_id: uuid.UUID) -> str | None:
    for usuario in plataforma_listar_usuarios(session, tenant_id):
        if usuario.usuario_id == usuario_id:
            return usuario.email
    return None


def programar(session: Session, tenant_id: uuid.UUID, usuario_id: uuid.UUID) -> None:
    """Programa el aviso de R61 para después del ``COMMIT``. Nunca lanza."""
    app = current_app._get_current_object()  # type: ignore[attr-defined]
    if not correo_activo(app):
        return
    logger = app.logger
    request_id = current_request_id()
    email = None
    fallo: str | None = None
    try:
        with session.begin_nested():
            email = _correo_de(session, tenant_id, usuario_id)
    except Exception as exc:  # noqa: BLE001 - el aviso nunca cambia la respuesta (R64)
        fallo = type(exc).__name__
    if fallo is not None:
        logger.warning(
            "Aviso de contraseña temporal sin destino (request_id=%s, tipo=%s)", request_id, fallo
        )
        return
    destino = destino_de(email) if email is not None else None
    if destino is None:
        return

    @after_this_request
    def _tras_commit(response: Response) -> Response:
        if response.status_code != 204:
            return response
        token: str | None = new_token()
        error: str | None = None
        try:
            if not pedir_enlace_recuperacion(destino, token_key(token)):
                token = None
        except Exception as exc:  # noqa: BLE001 - sin enlace, el aviso sale igual (R61)
            token = None
            error = type(exc).__name__
        if error is not None:
            logger.warning(
                "Enlace del aviso de contraseña temporal no pedido (request_id=%s, tipo=%s)",
                request_id,
                error,
            )
        correo = get_correo(app)

        def enviar() -> None:
            failure: str | None = None
            try:
                correo.enviar_aviso_restablecimiento(destino, token, request_id=request_id)
            except Exception as exc:  # noqa: BLE001 - nunca cambia la respuesta (R64)
                failure = type(exc).__name__
            if failure is not None:
                logger.warning(
                    "Correo de aviso no programado (request_id=%s, tipo=%s)", request_id, failure
                )

        response.call_on_close(enviar)
        return response
