"""Plantillas del correo de recuperación (spec 014, R5 y R6; plan §7 «Mensaje») y del aviso
de contraseña temporal (spec 017, C1d; R62, R63), con el mismo marco HTML.

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
# Aviso de contraseña temporal (spec 017, C1d; R62, R63).
ASUNTO_AVISO = "Se restableció el acceso a tu cuenta de AssetControl"
_AVISO_INICIO = (
    "El equipo de AssetControl definió una contraseña temporal para tu cuenta "
    "y cerró tus sesiones abiertas."
)
_AVISO_ELEGIR = "Si prefieres elegir tu propia contraseña, usa este enlace."
_AVISO_TEMPORAL = (
    "Si te entregaron la contraseña temporal, también puedes entrar con ella; "
    "te pediremos cambiarla."
)
_AVISO_SIN_ENLACE_ENTRAR = (
    "Para entrar, pide la contraseña temporal a quien te la definió; "
    "te pediremos cambiarla al entrar."
)
_AVISO_CIERRE = "Si no esperabas este cambio, avísale al administrador de tu empresa."
_AVISO_CON_ENLACE = (
    "Hola:\n\n"
    f"{_AVISO_INICIO}\n\n"
    f"{_AVISO_ELEGIR}\n\n"
    "{enlace}\n\n"
    "Vence en 30 minutos y solo sirve una vez.\n\n"
    f"{_AVISO_TEMPORAL}\n\n"
    f"{_AVISO_CIERRE}\n\n"
    "AssetControl\n"
)
_AVISO_SIN_ENLACE = (
    f"Hola:\n\n{_AVISO_INICIO}\n\n{_AVISO_SIN_ENLACE_ENTRAR}\n\n{_AVISO_CIERRE}\n\nAssetControl\n"
)
# Colores del tema (docs/08-diseno-visual.md §2): base zinc, botón principal neutro
# oscuro (opción A) y el cobalto solo en el enlace de respaldo. El marco es común a los
# dos correos; cada uno pone su preencabezado, su contenido y su pie (ya escapados).
_MARCO = """\
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
{preencabezado}</div>
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
{contenido}</td></tr>
<tr><td style="padding:16px 4px 0 4px;font-family:{fuente};font-size:12px;\
line-height:18px;color:#52525B;">\
{pie}</td></tr>
</table>
</td></tr>
</table>
</body>
</html>
"""
_TITULO = """\
<h1 style="margin:0 0 12px 0;font-size:20px;line-height:28px;font-weight:600;\
color:#09090B;">{titulo}</h1>
"""
_PARRAFO = """\
<p style="margin:0 0 24px 0;font-size:14px;line-height:22px;color:#52525B;">\
{texto}</p>
"""
_PARRAFO_FINAL = """\
<p style="margin:24px 0 0 0;font-size:13px;line-height:20px;color:#52525B;">\
{texto}</p>
"""
_BOTON = """\
<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>\
<td style="border-radius:6px;background-color:#18181B;">\
<a href="{enlace}" style="display:inline-block;padding:12px 20px;font-family:{fuente};\
font-size:14px;font-weight:600;color:#FAFAFA;text-decoration:none;border-radius:6px;">\
{etiqueta}</a></td></tr></table>
<p style="margin:24px 0 0 0;font-size:13px;line-height:20px;color:#52525B;">\
Vence en 30 minutos y solo sirve una vez.</p>
<hr style="border:none;border-top:1px solid #E4E4E7;margin:24px 0;">
<p style="margin:0 0 8px 0;font-size:13px;line-height:20px;color:#52525B;">\
Si el botón no funciona, copia este enlace en tu navegador:</p>
<p style="margin:0;font-size:13px;line-height:20px;word-break:break-all;">\
<a href="{enlace}" style="color:#2B50E0;text-decoration:underline;">{enlace}</a></p>
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


def _mensaje(remitente: str, destino: str, asunto: str) -> EmailMessage:
    """Cabeceras comunes; el destinatario ya validado como dirección simple."""
    if not es_direccion_simple(destino):
        raise DestinoNoValido()
    mensaje = EmailMessage()
    mensaje["From"] = remitente
    mensaje["To"] = destino
    mensaje["Subject"] = asunto
    # Dominio del remitente (ya validado): ``make_msgid`` sin dominio usaría el nombre
    # de la máquina, que no debe salir en el correo.
    mensaje["Message-ID"] = make_msgid(domain=remitente.rsplit("@", 1)[1].rstrip(">"))
    mensaje["Auto-Submitted"] = "auto-generated"
    return mensaje


def _con_html(
    mensaje: EmailMessage, asunto: str, preencabezado: str, contenido: str, pie: str
) -> None:
    """Añade la alternativa HTML con el marco común. ``contenido`` ya viene escapado."""
    mensaje.add_alternative(
        _MARCO.format(
            asunto=html.escape(asunto),
            preencabezado=html.escape(preencabezado),
            contenido=contenido,
            pie=html.escape(pie),
            fuente=_FUENTE,
        ),
        subtype="html",
        charset="utf-8",
        cte="quoted-printable",
    )


def componer_recuperacion(
    remitente: str, destino: str, url_publica: str, token: str
) -> EmailMessage:
    """Mensaje ``multipart/alternative`` (texto plano y HTML, utf-8) listo para enviar."""
    mensaje = _mensaje(remitente, destino, ASUNTO)
    enlace = enlace_recuperacion(url_publica, token)
    mensaje.set_content(_CUERPO.format(enlace=enlace), charset="utf-8", cte="quoted-printable")
    enlace_html = html.escape(enlace, quote=True)
    contenido = (
        _TITULO.format(titulo="Restablece tu contraseña")
        + _PARRAFO.format(
            texto="Recibimos una solicitud para restablecer tu contraseña de AssetControl. "
            "Usa el botón para elegir una nueva."
        )
        + _BOTON.format(enlace=enlace_html, etiqueta="Elegir nueva contraseña", fuente=_FUENTE)
    )
    _con_html(
        mensaje,
        ASUNTO,
        "Elige una nueva contraseña. El enlace vence en 30 minutos.",
        contenido,
        "Si no lo pediste, ignora este mensaje; tu contraseña no cambia.",
    )
    return mensaje


def componer_aviso_restablecimiento(
    remitente: str, destino: str, url_publica: str, token: str | None
) -> EmailMessage:
    """Aviso de contraseña temporal (spec 017, C1d; R62, R63). Con ``token``, lleva el
    enlace de la 014 para que la persona elija su contraseña; con ``None``, sale sin
    enlace. Nunca lleva la contraseña temporal, ni el nombre de la empresa ni el de quien
    la definió."""
    mensaje = _mensaje(remitente, destino, ASUNTO_AVISO)
    if token is None:
        texto = _AVISO_SIN_ENLACE
        contenido = _TITULO.format(titulo="Se restableció tu acceso") + "".join(
            _PARRAFO.format(texto=html.escape(linea))
            for linea in (_AVISO_INICIO, _AVISO_SIN_ENLACE_ENTRAR)
        )
        preencabezado = "Se definió una contraseña temporal para tu cuenta."
    else:
        enlace = enlace_recuperacion(url_publica, token)
        texto = _AVISO_CON_ENLACE.format(enlace=enlace)
        contenido = (
            _TITULO.format(titulo="Se restableció tu acceso")
            + _PARRAFO.format(texto=html.escape(f"{_AVISO_INICIO} {_AVISO_ELEGIR}"))
            + _BOTON.format(
                enlace=html.escape(enlace, quote=True),
                etiqueta="Elegir mi contraseña",
                fuente=_FUENTE,
            )
            + _PARRAFO_FINAL.format(texto=html.escape(_AVISO_TEMPORAL))
        )
        preencabezado = "Elige tu propia contraseña. El enlace vence en 30 minutos."
    mensaje.set_content(texto, charset="utf-8", cte="quoted-printable")
    _con_html(mensaje, ASUNTO_AVISO, preencabezado, contenido, _AVISO_CIERRE)
    return mensaje
