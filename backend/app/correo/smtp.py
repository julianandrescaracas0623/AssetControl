"""Envío por SMTP con TLS obligatorio (spec 014, R7; plan §7).

- ``starttls``: ``smtplib.SMTP`` + ``starttls`` con el contexto por defecto (verifica
  certificado y nombre). Si el servidor no ofrece STARTTLS, ``smtplib`` lanza y el
  mensaje no sale: nunca hay texto plano.
- ``ssl``: ``smtplib.SMTP_SSL`` (TLS implícito) con el mismo contexto.

El EHLO se presenta con el dominio del remitente (``nombre_ehlo``), nunca con el nombre
de la máquina (``socket.getfqdn``): no lo filtra ni espera DNS. Tiempo límite de 10 s
por operación de socket y sin reintentos. Las credenciales salen solo de la
configuración. Las excepciones se propagan al hilo de envío, que registra solo su tipo.
"""

import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import parseaddr

from app.correo.config import SMTP_TIMEOUT_SEGUNDOS, CorreoConfig

NOMBRE_EHLO_POR_DEFECTO = "localhost"
_DOMINIO = re.compile(r"[0-9A-Za-z](?:[0-9A-Za-z\-.]*[0-9A-Za-z])?")


def nombre_ehlo(remitente: str) -> str:
    """Dominio de ``CORREO_REMITENTE`` para el EHLO; ``localhost`` si no hay uno válido."""
    direccion = parseaddr(remitente or "")[1]
    dominio = direccion.rpartition("@")[2] if "@" in direccion else ""
    if dominio and len(dominio) <= 253 and _DOMINIO.fullmatch(dominio):
        return dominio
    return NOMBRE_EHLO_POR_DEFECTO


class ServidorSmtp:
    """Destino «smtp». Una conexión por mensaje; sin reintentos."""

    def __init__(self, config: CorreoConfig, timeout: float = SMTP_TIMEOUT_SEGUNDOS) -> None:
        if config.modo != "smtp" or config.smtp_cifrado not in ("starttls", "ssl"):
            raise ValueError("ServidorSmtp exige CORREO_MODO=smtp con TLS.")
        self._config = config
        self._timeout = timeout

    def __repr__(self) -> str:
        return f"ServidorSmtp(cifrado={self._config.smtp_cifrado!r})"

    def entregar(self, mensaje: EmailMessage) -> None:
        config = self._config
        contexto = ssl.create_default_context()
        local = nombre_ehlo(config.remitente)
        if config.smtp_cifrado == "ssl":
            conexion = smtplib.SMTP_SSL(
                config.smtp_host,
                config.smtp_puerto,
                local_hostname=local,
                timeout=self._timeout,
                context=contexto,
            )
        else:
            conexion = smtplib.SMTP(
                config.smtp_host, config.smtp_puerto, local_hostname=local, timeout=self._timeout
            )
        with conexion as servidor:
            if config.smtp_cifrado == "starttls":
                servidor.ehlo()
                servidor.starttls(context=contexto)
                servidor.ehlo()
            if config.smtp_usuario and config.smtp_clave:
                servidor.login(config.smtp_usuario, config.smtp_clave)
            servidor.send_message(mensaje)
