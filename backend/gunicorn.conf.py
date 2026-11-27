"""gunicorn en producción (spec 010b, T2; R2; deuda (b) de la spec 002).

Carga ``app.wsgi:application`` (web en ``/`` y API en ``/api``). Dos procesos con cuatro
hilos cada uno: el semáforo de Argon2 (spec 002, T10) es de 4 por proceso. Sin recarga
ni depurador. El puerto lo da la plataforma en ``$PORT``.

Registro de accesos a stdout con método, ruta **sin consulta**, estado, tamaño, duración
e ID de petición: ni cuerpos, ni cadenas de consulta, ni cabeceras con credenciales.
"""

import logging
import os
import sys
from typing import Any

wsgi_app = "app.wsgi:application"
bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = 2
worker_class = "gthread"
threads = 4
timeout = 30
graceful_timeout = 20
keepalive = 5
reload = False
# La app se crea en cada proceso, después del fork: el engine no se comparte.
preload_app = False
max_requests = 2000
max_requests_jitter = 200
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s "%(m)s %(U)s" %(s)s %(B)s %(M)sms %({x-request-id}o)s'
# Encabezados X-Forwarded-*: solo de la red interna de la plataforma. La IP del cliente
# la decide la app con TRUSTED_PROXY_HOPS (ProxyFix), no gunicorn.
forwarded_allow_ips = os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1")

# Spec 018 (R4): al apagarse un proceso se esperan los correos en curso, como mucho este
# plazo (menor que ``graceful_timeout``: después gunicorn mata el proceso de todos modos).
PLAZO_CORREO_AL_APAGAR = 15.0
_MODULO_WSGI = "app.wsgi"
_log = logging.getLogger("gunicorn.error")


def worker_exit(server: Any, worker: Any) -> None:
    """Espera los envíos de correo de este proceso; nunca falla ni bloquea más del plazo.

    gunicorn también la llama en el maestro, que no cargó la app (``preload_app = False``):
    si ``app.wsgi`` no está cargado no se importa. El registro no lleva destinos, tokens ni
    el mensaje de la excepción (puede traerlos): solo el tipo.
    """
    try:
        modulo = sys.modules.get(_MODULO_WSGI)
        obtener = getattr(modulo, "correo_del_proceso", None) if modulo is not None else None
        correo = obtener() if obtener is not None else None
        if correo is None:
            return
        if not correo.esperar(timeout=PLAZO_CORREO_AL_APAGAR):
            _log.warning(
                "Apagado: venció el plazo de %s s y se perdieron correos en curso.",
                PLAZO_CORREO_AL_APAGAR,
            )
    except Exception as exc:
        _log.warning(
            "Apagado: no se pudo esperar los correos en curso (tipo=%s).", type(exc).__name__
        )
