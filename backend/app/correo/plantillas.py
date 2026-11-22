"""Plantilla del correo de recuperación (spec 014, R5 y R6; plan §7 «Mensaje»).

En español, con asunto fijo y sin datos de la clínica ni de la persona. Va como
``multipart/alternative``: primero el texto plano (lo que leen los clientes sin HTML y
las pruebas) y después una versión HTML con la marca del producto («Grafito y
Cobalto», docs/08-diseno-visual.md): solo estilos en línea y tablas, sin imágenes,
fuentes ni recursos externos, para que nada se descargue al abrirlo. El
token va en el fragmento del enlace (``#``): no viaja al servidor ni a los logs de
acceso. El destinatario se valida como una sola dirección simple, sin CR/LF ni
separadores (defensa contra la inyección de cabeceras además de la que ya hace
``EmailMessage``). Los errores nunca repiten el destinatario ni el token.
"""

import html
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
# Colores del tema (docs/08-diseno-visual.md §2): base zinc, botón principal neutro
# oscuro (opción A) y el cobalto solo en el enlace de respaldo.
_HTML = """\
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="supported-color-schemes" content="light">
<title>{asunto}</title>
</head>
<body style="margin:0;padding:0;background-color:#F4F4F5;">
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">\
Elige una nueva contraseña. El enlace vence en 30 minutos.</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" \
style="background-color:#F4F4F5;">
<tr><td align="center" style="padding:32px 16px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" \
style="max-width:480px;">
<tr><td style="padding:0 4px 16px 4px;font-family:{fuente};font-size:16px;\
font-weight:600;color:#09090B;letter-spacing:-0.01em;">\
<span style="display:inline-block;width:10px;height:10px;background-color:#2B50E0;\
border-radius:2px;margin-right:8px;"></span>AssetControl</td></tr>
<tr><td style="background-color:#FFFFFF;border:1px solid #E4E4E7;border-radius:8px;\
padding:32px;font-family:{fuente};color:#09090B;">
<h1 style="margin:0 0 12px 0;font-size:20px;line-height:28px;font-weight:600;\
color:#09090B;">Restablece tu contraseña</h1>
<p style="margin:0 0 24px 0;font-size:14px;line-height:22px;color:#52525B;">\
Recibimos una solicitud para restablecer tu contraseña de AssetControl. \
Usa el botón para elegir una nueva.</p>
<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>\
<td style="border-radius:6px;background-color:#18181B;">\
<a href="{enlace}" style="display:inline-block;padding:12px 20px;font-family:{fuente};\
font-size:14px;font-weight:600;color:#FAFAFA;text-decoration:none;border-radius:6px;">\
Elegir nueva contraseña</a></td></tr></table>
<p style="margin:24px 0 0 0;font-size:13px;line-height:20px;color:#52525B;">\
Vence en 30 minutos y solo sirve una vez.</p>
<hr style="border:none;border-top:1px solid #E4E4E7;margin:24px 0;">
<p style="margin:0 0 8px 0;font-size:13px;line-height:20px;color:#52525B;">\
Si el botón no funciona, copia este enlace en tu navegador:</p>
<p style="margin:0;font-size:13px;line-height:20px;word-break:break-all;">\
<a href="{enlace}" style="color:#2B50E0;text-decoration:underline;">{enlace}</a></p>
</td></tr>
<tr><td style="padding:16px 4px 0 4px;font-family:{fuente};font-size:12px;\
line-height:18px;color:#52525B;">\
Si no lo pediste, ignora este mensaje; tu contraseña no cambia.</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""
_FUENTE = "-apple-system,BlinkMacSystemFont,&#39;Segoe UI&#39;,Roboto,Helvetica,Arial,sans-serif"


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
    """Mensaje ``multipart/alternative`` (texto plano y HTML, utf-8) listo para enviar."""
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
    mensaje.add_alternative(
        _HTML.format(
            asunto=html.escape(ASUNTO), enlace=html.escape(enlace, quote=True), fuente=_FUENTE
        ),
        subtype="html",
        charset="utf-8",
        cte="quoted-printable",
    )
    return mensaje
