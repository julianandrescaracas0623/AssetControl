"""Correo de recuperación de contraseña (spec 014, T3; R6–R8, R16; plan §7).

Interfaz mínima para T4:

- ``correo_activo(app)``: ``False`` si falta ``CORREO_MODO`` (recuperación desactivada).
- ``get_correo(app).enviar_recuperacion(destino, token, request_id=None)``: se llama
  **después** del ``COMMIT`` (la ruta lo hace al cerrar la respuesta, sin contexto de
  petición, y pasa el ``request_id``); vuelve de inmediato y nunca lanza. Compone y
  entrega en un hilo ``daemon`` acotado por un ``BoundedSemaphore``; sin cupo, el envío
  se descarta, se cuenta en ``descartados`` y se registra con ese total.

Sin colas ni reintentos (ADR-002). Un fallo se registra solo con su tipo y el
``request_id``: nunca el destinatario, el host, el token, el enlace, el cuerpo ni el
mensaje de la excepción (que puede traer cualquiera de ellos).
"""

import logging
import threading
import time
from email.message import EmailMessage
from typing import TYPE_CHECKING, Protocol

from app.correo.buzon import Buzon
from app.correo.config import CorreoConfig
from app.correo.plantillas import componer_recuperacion
from app.correo.smtp import ServidorSmtp

if TYPE_CHECKING:
    from flask import Flask

__all__ = [
    "EXTENSION_KEY",
    "MAX_CONCURRENCIA",
    "Correo",
    "correo_activo",
    "crear",
    "get_correo",
]

EXTENSION_KEY = "assetcontrol.correo"
MAX_CONCURRENCIA = 4
SIN_PETICION = "-"

logger = logging.getLogger(__name__)


class Transporte(Protocol):
    def entregar(self, mensaje: EmailMessage) -> object: ...


def _request_id() -> str:
    """``request_id`` de la petición en curso (si la hay), leído antes de lanzar el hilo."""
    from flask import has_request_context

    if not has_request_context():
        return SIN_PETICION
    from app.errors import current_request_id

    return current_request_id()


class Correo:
    """Envío de correos de recuperación en segundo plano. Nunca propaga errores."""

    def __init__(
        self,
        config: CorreoConfig | None,
        transporte: Transporte | None = None,
        max_concurrencia: int = MAX_CONCURRENCIA,
    ) -> None:
        self._config = config
        if transporte is None and config is not None:
            transporte = Buzon(config.carpeta) if config.modo == "carpeta" else ServidorSmtp(config)
        self.transporte = transporte
        self._cupo = threading.BoundedSemaphore(max_concurrencia)
        self._hilos: set[threading.Thread] = set()
        self._hilos_lock = threading.Lock()
        self.descartados = 0

    def __repr__(self) -> str:
        modo = self._config.modo if self._config is not None else "desactivado"
        return f"Correo(modo={modo!r})"

    @property
    def activo(self) -> bool:
        return self._config is not None and self.transporte is not None

    def enviar_recuperacion(self, destino: str, token: str, request_id: str | None = None) -> None:
        """Programa el envío y vuelve sin esperar. Sin configuración no hace nada.

        ``request_id``: el de la petición que lo pidió; si falta, el de la petición en curso.
        """
        if not self.activo:
            return None
        if request_id is None:
            request_id = _request_id()
        if not self._cupo.acquire(blocking=False):
            with self._hilos_lock:
                self.descartados += 1
                descartados = self.descartados
            logger.warning(
                "Correo de recuperación descartado: sin cupo de envío (request_id=%s, "
                "descartados=%s)",
                request_id,
                descartados,
            )
            return None
        hilo = threading.Thread(
            target=self._enviar,
            args=(destino, token, request_id),
            name="correo-recuperacion",
            daemon=True,
        )
        with self._hilos_lock:
            self._hilos.add(hilo)
        try:
            hilo.start()
        except Exception as exc:  # p. ej. RuntimeError: el sistema no da más hilos
            with self._hilos_lock:
                self._hilos.discard(hilo)
            self._cupo.release()
            logger.warning(
                "Correo de recuperación no enviado (request_id=%s, tipo=%s)",
                request_id,
                type(exc).__name__,
            )
        return None

    def _enviar(self, destino: str, token: str, request_id: str) -> None:
        try:
            config = self._config
            if config is None or self.transporte is None:
                raise RuntimeError("correo desactivado")
            mensaje = componer_recuperacion(config.remitente, destino, config.url_publica, token)
            self.transporte.entregar(mensaje)
        except Exception as exc:
            # Solo el tipo: el mensaje de la excepción puede traer host, destinatario o
            # respuestas del servidor. Sin ``exc_info`` por la misma razón.
            logger.warning(
                "Correo de recuperación no enviado (request_id=%s, tipo=%s)",
                request_id,
                type(exc).__name__,
            )
        else:
            logger.info("Correo de recuperación entregado (request_id=%s)", request_id)
        finally:
            self._cupo.release()
            with self._hilos_lock:
                self._hilos.discard(threading.current_thread())

    def esperar(self, timeout: float | None = None) -> bool:
        """Espera a los envíos en curso (pruebas y apagado ordenado). ``True`` si acabaron."""
        limite = None if timeout is None else time.monotonic() + timeout
        while True:
            with self._hilos_lock:
                pendientes = list(self._hilos)
            if not pendientes:
                return True
            for hilo in pendientes:
                restante = None if limite is None else max(0.0, limite - time.monotonic())
                if hilo.ident is None:
                    # Registrado pero aún sin arrancar (otro hilo está en ``start``).
                    if restante == 0.0:
                        return False
                    time.sleep(0.01)
                    continue
                hilo.join(restante)
                if hilo.is_alive():
                    return False
                with self._hilos_lock:
                    self._hilos.discard(hilo)


def crear(config: CorreoConfig | None) -> Correo:
    """``Correo`` para la configuración; con ``None`` queda desactivado."""
    return Correo(config)


def get_correo(app: "Flask") -> Correo:
    return app.extensions[EXTENSION_KEY]


def correo_activo(app: "Flask") -> bool:
    return get_correo(app).activo
