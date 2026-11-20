"""Envío por SMTP con TLS obligatorio (spec 014, R7; plan §7).

- ``starttls``: ``smtplib.SMTP`` + ``starttls`` con el contexto por defecto (verifica
  certificado y nombre). Si el servidor no ofrece STARTTLS, ``smtplib`` lanza y el
  mensaje no sale: nunca hay texto plano.
- ``ssl``: ``smtplib.SMTP_SSL`` (TLS implícito) con el mismo contexto.

El EHLO se presenta con el dominio del remitente (``nombre_ehlo``), nunca con el nombre
de la máquina (``socket.getfqdn``): no lo filtra ni espera DNS. Tiempo límite de 10 s
por operación de socket y sin reintentos. Las credenciales salen solo de la
configuración. Las excepciones se propagan al hilo de envío, que registra solo su tipo.

Endurecimiento de T8 (deuda de T3):

- B-2: el contexto TLS exige TLS 1.2 como mínimo (``minimum_version`` explícito).
- M-1: plazo **total** de ``SMTP_PLAZO_TOTAL_SEGUNDOS`` por entrega. El cliente se crea
  sin conectar y un vigilante (``threading.Timer``) corta el socket (``shutdown``) al
  vencer el plazo, así un servidor que gotea respuestas sin agotar nunca el timeout por
  operación no retiene el hilo ni su cupo. La entrega vencida termina en
  ``TimeoutError``. Residual: la resolución DNS y el saludo TLS de ``ssl`` ocurren antes
  de que exista ``sock``; los acota el timeout por operación y, al terminar, se comprueba
  el plazo antes de seguir.
"""

import re
import smtplib
import socket
import ssl
import threading
from email.message import EmailMessage
from email.utils import parseaddr

from app.correo.config import SMTP_PLAZO_TOTAL_SEGUNDOS, SMTP_TIMEOUT_SEGUNDOS, CorreoConfig

NOMBRE_EHLO_POR_DEFECTO = "localhost"
_DOMINIO = re.compile(r"[0-9A-Za-z](?:[0-9A-Za-z\-.]*[0-9A-Za-z])?")


def nombre_ehlo(remitente: str) -> str:
    """Dominio de ``CORREO_REMITENTE`` para el EHLO; ``localhost`` si no hay uno válido."""
    direccion = parseaddr(remitente or "")[1]
    dominio = direccion.rpartition("@")[2] if "@" in direccion else ""
    if dominio and len(dominio) <= 253 and _DOMINIO.fullmatch(dominio):
        return dominio
    return NOMBRE_EHLO_POR_DEFECTO


# M-1: mensaje fijo, sin host ni destinatario (el hilo registra solo el tipo).
PLAZO_AGOTADO = "Plazo total del envío agotado."


class _Vigilante:
    """Corta el socket de ``conexion`` si la entrega supera ``plazo`` segundos.

    ``_cortar`` (hilo del temporizador) y ``__exit__`` (hilo de envío) comparten un candado:
    ``__exit__`` espera a que termine un corte en curso y marca ``terminado``; un
    ``_cortar`` tardío, cuyo temporizador ya disparó, no hace nada después de eso. Así el
    ``shutdown`` nunca cae en un descriptor ya cerrado y reutilizado por otra conexión.
    """

    def __init__(self, conexion: smtplib.SMTP, plazo: float) -> None:
        self._conexion = conexion
        self.vencido = False
        self._terminado = False
        self._candado = threading.Lock()
        self._timer = threading.Timer(plazo, self._cortar)
        self._timer.daemon = True

    def __enter__(self) -> "_Vigilante":
        self._timer.start()
        return self

    def __exit__(self, *args: object) -> None:
        self._timer.cancel()
        with self._candado:
            self._terminado = True

    def _cortar(self) -> None:
        with self._candado:
            if self._terminado:
                return
            self.vencido = True
            sock = getattr(self._conexion, "sock", None)
            if isinstance(sock, socket.socket):
                try:
                    # ``socket.socket.shutdown`` (no el de ``SSLSocket``): despierta la
                    # lectura bloqueada del otro hilo sin tocar el estado TLS; ``smtplib``
                    # cierra después.
                    socket.socket.shutdown(sock, socket.SHUT_RDWR)
                except OSError:
                    pass

    def comprobar(self) -> None:
        if self.vencido:
            raise TimeoutError(PLAZO_AGOTADO)


class ServidorSmtp:
    """Destino «smtp». Una conexión por mensaje; sin reintentos."""

    def __init__(
        self,
        config: CorreoConfig,
        timeout: float = SMTP_TIMEOUT_SEGUNDOS,
        plazo_total: float = SMTP_PLAZO_TOTAL_SEGUNDOS,
    ) -> None:
        if config.modo != "smtp" or config.smtp_cifrado not in ("starttls", "ssl"):
            raise ValueError("ServidorSmtp exige CORREO_MODO=smtp con TLS.")
        self._config = config
        self._timeout = timeout
        self._plazo_total = plazo_total

    def __repr__(self) -> str:
        return f"ServidorSmtp(cifrado={self._config.smtp_cifrado!r})"

    def entregar(self, mensaje: EmailMessage) -> None:
        config = self._config
        contexto = ssl.create_default_context()
        contexto.minimum_version = ssl.TLSVersion.TLSv1_2
        local = nombre_ehlo(config.remitente)
        # Sin host: se crea sin conectar para que el vigilante vea el socket desde el saludo.
        if config.smtp_cifrado == "ssl":
            conexion = smtplib.SMTP_SSL(
                local_hostname=local, timeout=self._timeout, context=contexto
            )
        else:
            conexion = smtplib.SMTP(local_hostname=local, timeout=self._timeout)
        # ``smtplib`` toma el nombre que verifica el certificado (``server_hostname`` de
        # ``SMTP_SSL`` y de ``starttls``) de ``_host``, que solo fija el constructor con host.
        # Sin esto la verificación del nombre fallaría cerrada; lo cubren las pruebas con
        # TLS real (certificado de otro nombre rechazado).
        # Deuda (T8): ``_host`` es un atributo privado de ``smtplib``. Si una versión de
        # Python lo renombra, el envío falla cerrado (no se verifica contra otro nombre ni
        # sale en claro) y las pruebas TLS reales de ``test_correo.py`` lo detectan.
        conexion._host = config.smtp_host
        vencido = False
        with _Vigilante(conexion, self._plazo_total) as vigilante:
            try:
                with conexion as servidor:
                    servidor.connect(config.smtp_host, config.smtp_puerto)
                    vigilante.comprobar()
                    if config.smtp_cifrado == "starttls":
                        servidor.ehlo()
                        servidor.starttls(context=contexto)
                        vigilante.comprobar()
                        servidor.ehlo()
                    if config.smtp_usuario and config.smtp_clave:
                        servidor.login(config.smtp_usuario, config.smtp_clave)
                    vigilante.comprobar()
                    servidor.send_message(mensaje)
            except Exception:
                if not vigilante.vencido:
                    raise
                vencido = True
        if vencido:
            # Fuera del except: sin causa ni contexto (pueden traer host o respuestas).
            raise TimeoutError(PLAZO_AGOTADO)
