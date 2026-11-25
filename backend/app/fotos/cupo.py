"""Límite de subidas de foto por usuario y ventana (SEC-02).

Ventana deslizante en memoria del proceso: cada usuario puede subir ``MAX_SUBIDAS`` fotos
(principales o de verificación) en ``VENTANA_SEGUNDOS``. Pasado el tope, ``429`` sin tocar
la imagen. Es por proceso: con varios trabajadores de gunicorn el tope real es el de cada
uno (ver docs/09-despliegue.md). Un contador en la base exigiría un ámbito nuevo en
``limite_tasa`` (CHECK de la migración 0025), fuera de este cambio.
"""

import threading
import time
import uuid
from collections import deque
from collections.abc import Callable

MAX_SUBIDAS = 60
VENTANA_SEGUNDOS = 600.0


class SubidasExcedidas(Exception):
    status = 429
    code = "demasiadas_subidas"
    message = "Has subido muchas fotos en poco tiempo. Espera unos minutos y vuelve a intentarlo."


class VentanaDeSubidas:
    def __init__(
        self,
        maximo: int,
        ventana: float,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        self._maximo = maximo
        self._ventana = ventana
        self._reloj = reloj
        self._lock = threading.Lock()
        self._instantes: dict[uuid.UUID, deque[float]] = {}

    def registrar(self, usuario_id: uuid.UUID) -> None:
        """Suma una subida del usuario; ``SubidasExcedidas`` si ya llegó al tope."""
        ahora = self._reloj()
        with self._lock:
            cola = self._instantes.setdefault(usuario_id, deque())
            while cola and ahora - cola[0] >= self._ventana:
                cola.popleft()
            if len(cola) >= self._maximo:
                raise SubidasExcedidas()
            cola.append(ahora)


SUBIDAS = VentanaDeSubidas(MAX_SUBIDAS, VENTANA_SEGUNDOS)


def registrar_subida(usuario_id: uuid.UUID) -> None:
    SUBIDAS.registrar(usuario_id)
