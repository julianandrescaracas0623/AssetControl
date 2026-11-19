"""Plantilla del correo de recuperación (spec 014, R5 y R6; plan §7 «Mensaje»).

Texto plano en español, asunto fijo, sin datos de la clínica ni de la persona. El
token va en el fragmento del enlace (``#``): no viaja al servidor ni a los logs de
acceso. El destinatario se valida como una sola dirección simple, sin CR/LF ni
separadores (defensa contra la inyección de cabeceras además de la que ya hace
``EmailMessage``). Los errores nunca repiten el destinatario ni el token.
"""

import re
from email.message import EmailMessage
from email.utils import make_msgid

from app.correo.config import es_direccion_simple

ASUNTO = "Restablece tu contraseña de AssetControl"
RUTA_RESTABLECER = "/restablecer"
# ``secrets.token_urlsafe(32)`` da 43 caracteres base64url; se admite un margen.
_TOKEN = re.compile(r"[A-Za-z0-9_-]{32,128}")
_CUERPO = (
    "Hola:\n"
    "\n"
    "Recibimos una solicitud para restablecer tu contraseña de AssetControl.\n"
    "Abre este enlace para elegir una nueva:\n"
    "\n"
    "{enlace}\n"
    "\n"
    "Vence en 30 minutos y solo sirve una vez.\n"
    "\n"
    "Si no lo pediste, ignora este mensaje; tu contraseña no cambia.\n"
    "\n"
    "AssetControl\n"
)


class DestinoNoValido(ValueError):
    """El destinatario no es una sola dirección simple. No repite el valor."""

    def __init__(self) -> None:
        super().__init__("Destinatario del correo no válido.")


class TokenNoValido(ValueError):
    """El token no tiene la forma esperada. No repite el valor."""

    def __init__(self) -> None:
        super().__init__("Token de recuperación no válido.")


def enlace_recuperacion(url_publica: str, token: str) -> str:
    """``{URL_PUBLICA}/restablecer#<token>``; la base sale de la configuración (R5)."""
    if not isinstance(token, str) or not _TOKEN.fullmatch(token):
        raise TokenNoValido()
    return f"{url_publica.rstrip('/')}{RUTA_RESTABLECER}#{token}"


def componer_recuperacion(
    remitente: str, destino: str, url_publica: str, token: str
) -> EmailMessage:
    """Mensaje ``text/plain; charset=utf-8`` listo para el buzón o el SMTP."""
    if not es_direccion_simple(destino):
        raise DestinoNoValido()
    enlace = enlace_recuperacion(url_publica, token)
    mensaje = EmailMessage()
    mensaje["From"] = remitente
    mensaje["To"] = destino
    mensaje["Subject"] = ASUNTO
    # Dominio del remitente (ya validado): ``make_msgid`` sin dominio usaría el nombre
    # de la máquina, que no debe salir en el correo.
    mensaje["Message-ID"] = make_msgid(domain=remitente.rsplit("@", 1)[1].rstrip(">"))
    mensaje["Auto-Submitted"] = "auto-generated"
    mensaje.set_content(_CUERPO.format(enlace=enlace), charset="utf-8", cte="quoted-printable")
    return mensaje
