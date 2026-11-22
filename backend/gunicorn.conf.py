"""gunicorn en producción (spec 010b, T2; R2; deuda (b) de la spec 002).

Carga ``app.wsgi:application`` (web en ``/`` y API en ``/api``). Dos procesos con cuatro
hilos cada uno: el semáforo de Argon2 (spec 002, T10) es de 4 por proceso. Sin recarga
ni depurador. El puerto lo da la plataforma en ``$PORT``.

Registro de accesos a stdout con método, ruta **sin consulta**, estado, tamaño, duración
e ID de petición: ni cuerpos, ni cadenas de consulta, ni cabeceras con credenciales.
"""

import os

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
