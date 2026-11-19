"""Configuración del correo desde variables de entorno (spec 014, R7 y R18; plan §7).

Variables: ``CORREO_MODO`` (``carpeta`` | ``smtp``; ausente = recuperación
desactivada), ``CORREO_REMITENTE``, ``CORREO_CARPETA``, ``SMTP_HOST``, ``SMTP_PUERTO``,
``SMTP_USUARIO``, ``SMTP_CLAVE``, ``SMTP_CIFRADO`` (``starttls`` | ``ssl``) y
``URL_PUBLICA``.

Los mensajes de error nombran la variable y nunca repiten su valor. ``repr`` no
muestra el host, el usuario ni la clave SMTP.
"""

import ipaddress
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

MODOS = ("carpeta", "smtp")
CIFRADOS = ("starttls", "ssl")
PUERTO_POR_CIFRADO = {"starttls": 587, "ssl": 465}
SMTP_TIMEOUT_SEGUNDOS = 10
BUZON_POR_DEFECTO = Path(__file__).resolve().parents[2] / ".buzon"
REMITENTE_DESARROLLO = "AssetControl <no-responder@assetcontrol.invalid>"
# Entornos donde se admite el buzón en carpeta y una ``URL_PUBLICA`` con ``http``
# (``test`` solo existe bajo pytest, ver ``app.config.is_test_context``).
ENTORNOS_LOCALES: frozenset[str] = frozenset({"development", "test"})
URL_MAX = 2048

_ENTERO = re.compile(r"[0-9]{1,5}")
# Dirección simple ``local@dominio`` en ASCII imprimible, sin espacios ni separadores
# de lista o de nombre: lo que sí admite es una sola dirección, nunca varias.
_DIRECCION = r"[!#$%&'*+\-/=?^_`{|}~.0-9A-Za-z]+@[0-9A-Za-z](?:[0-9A-Za-z\-.]*[0-9A-Za-z])?"
_DIRECCION_SIMPLE = re.compile(_DIRECCION)
_REMITENTE = re.compile(rf"(?:[0-9A-Za-z][0-9A-Za-z .\-]{{0,62}} <{_DIRECCION}>|{_DIRECCION})")
_URL_PERMITIDA = re.compile(r"[\x21-\x7e]+")
# Host de ``URL_PUBLICA``: nombre con letras, dígitos, «.» y «-» (sin empezar ni terminar
# en «.» o «-») o una IPv6 literal entre corchetes; puerto opcional.
_HOST_NOMBRE = re.compile(r"[0-9A-Za-z](?:[0-9A-Za-z.\-]*[0-9A-Za-z])?(?::[0-9]{1,5})?")
_HOST_IPV6 = re.compile(r"\[([0-9A-Fa-f:.]+)\](?::[0-9]{1,5})?")
_URL_HOST_INVALIDO = (
    "URL_PUBLICA no es válida: el host solo admite letras, dígitos, «.» y «-», "
    "o una IPv6 entre corchetes."
)


class CorreoNoValido(RuntimeError):
    """La configuración del correo no es válida. El mensaje nunca repite valores."""


def es_direccion_simple(valor: object, maximo: int = 254) -> bool:
    """``True`` si ``valor`` es una sola dirección ``local@dominio`` ASCII sin CR/LF."""
    return (
        isinstance(valor, str)
        and 3 <= len(valor) <= maximo
        and _DIRECCION_SIMPLE.fullmatch(valor) is not None
    )


def _validar_url(url: object) -> None:
    if not isinstance(url, str) or not url or len(url) > URL_MAX:
        raise CorreoNoValido("URL_PUBLICA es obligatoria con CORREO_MODO (base del enlace).")
    if not _URL_PERMITIDA.fullmatch(url):
        raise CorreoNoValido("URL_PUBLICA no es válida: sin espacios ni caracteres de control.")
    try:
        partes = urlsplit(url)
    except ValueError:
        # p. ej. «https://[::1» (corchete sin cerrar) o IPv6 mal formada.
        raise CorreoNoValido(_URL_HOST_INVALIDO) from None
    if partes.scheme not in ("https", "http"):
        raise CorreoNoValido("URL_PUBLICA debe usar el esquema https.")
    if (
        not partes.hostname
        or partes.username is not None
        or partes.password is not None
        or partes.query
        or partes.fragment
        or "?" in url
        or "#" in url
    ):
        raise CorreoNoValido(
            "URL_PUBLICA no es válida: solo esquema, host, puerto y ruta opcional "
            "(sin usuario, consulta ni fragmento)."
        )
    _validar_host(partes.netloc)
    try:
        partes.port  # noqa: B018 - valida el puerto (lanza ValueError si no es numérico)
    except ValueError:
        raise CorreoNoValido("URL_PUBLICA no es válida: puerto incorrecto.") from None


def _validar_host(netloc: str) -> None:
    """``host[:puerto]`` sin usuario: nombre ``[A-Za-z0-9.-]`` o ``[IPv6]`` bien formada."""
    if _HOST_NOMBRE.fullmatch(netloc):
        return
    ipv6 = _HOST_IPV6.fullmatch(netloc)
    if ipv6 is not None:
        try:
            ipaddress.IPv6Address(ipv6.group(1))
        except ValueError:
            pass
        else:
            return
    raise CorreoNoValido(_URL_HOST_INVALIDO)


@dataclass(frozen=True)
class CorreoConfig:
    """Destino del correo de recuperación. Validada al construirse (arranque)."""

    modo: str
    remitente: str
    url_publica: str
    carpeta: Path | None = None
    smtp_host: str | None = field(default=None, repr=False)
    smtp_puerto: int | None = None
    smtp_usuario: str | None = field(default=None, repr=False)
    smtp_clave: str | None = field(default=None, repr=False)
    smtp_cifrado: str | None = None

    def __post_init__(self) -> None:
        if self.modo not in MODOS:
            raise CorreoNoValido("CORREO_MODO debe ser «carpeta» o «smtp».")
        if not isinstance(self.remitente, str) or not _REMITENTE.fullmatch(self.remitente):
            raise CorreoNoValido(
                "CORREO_REMITENTE no es válido: usa «Nombre <correo@dominio>» o «correo@dominio»."
            )
        _validar_url(self.url_publica)
        if self.url_publica.endswith("/"):
            raise CorreoNoValido("URL_PUBLICA no debe terminar en «/».")
        if self.modo == "carpeta":
            if self.carpeta is None:
                raise CorreoNoValido("CORREO_CARPETA es obligatoria con CORREO_MODO=carpeta.")
            return
        if not self.smtp_host or not isinstance(self.smtp_host, str):
            raise CorreoNoValido("SMTP_HOST es obligatoria con CORREO_MODO=smtp.")
        if self.smtp_cifrado not in CIFRADOS:
            raise CorreoNoValido(
                "SMTP_CIFRADO debe ser «starttls» o «ssl»: el correo nunca sale sin TLS."
            )
        puerto = self.smtp_puerto
        if isinstance(puerto, bool) or not isinstance(puerto, int) or not 1 <= puerto <= 65535:
            raise CorreoNoValido("SMTP_PUERTO no es válida: debe ser un entero entre 1 y 65535.")
        if bool(self.smtp_usuario) != bool(self.smtp_clave):
            falta = "SMTP_CLAVE" if self.smtp_usuario else "SMTP_USUARIO"
            raise CorreoNoValido(
                f"{falta} es obligatoria: SMTP_USUARIO y SMTP_CLAVE van juntas o ninguna."
            )


def validar_entorno(config: "CorreoConfig | None", entorno: str) -> None:
    """Reglas que dependen de ``ENVIRONMENT`` (R7, R18): carpeta y ``http`` solo locales."""
    if config is None or entorno in ENTORNOS_LOCALES:
        return
    if config.modo == "carpeta":
        raise CorreoNoValido(
            "CORREO_MODO=carpeta solo se admite en development; en producción usa "
            "CORREO_MODO=smtp con TLS."
        )
    if urlsplit(config.url_publica).scheme != "https":
        raise CorreoNoValido("URL_PUBLICA debe usar el esquema https fuera de development.")


def _texto(source: Mapping[str, str], nombre: str) -> str:
    return (source.get(nombre) or "").strip()


def load_correo(source: Mapping[str, str], entorno: str) -> CorreoConfig | None:
    """``CorreoConfig`` desde el entorno o ``None`` si ``CORREO_MODO`` está vacío.

    - ``carpeta``: solo en development; ``CORREO_CARPETA`` o ``backend/.buzon``.
    - ``smtp``: ``SMTP_HOST`` obligatoria; ``SMTP_CIFRADO`` obligatoria fuera de
      development (allí por defecto ``starttls``; nunca texto plano); ``SMTP_PUERTO``
      por defecto 587 (``starttls``) o 465 (``ssl``).
    - ``URL_PUBLICA`` obligatoria; ``https`` fuera de development. Se quita la ``/`` final.
    """
    modo = _texto(source, "CORREO_MODO").lower()
    if not modo:
        return None
    if modo not in MODOS:
        raise CorreoNoValido("CORREO_MODO debe ser «carpeta» o «smtp».")
    url = _texto(source, "URL_PUBLICA")
    if not url:
        raise CorreoNoValido("URL_PUBLICA es obligatoria con CORREO_MODO (base del enlace).")
    _validar_url(url)
    url = url.rstrip("/")
    remitente = _texto(source, "CORREO_REMITENTE")
    if modo == "carpeta":
        carpeta = _texto(source, "CORREO_CARPETA")
        config = CorreoConfig(
            modo="carpeta",
            remitente=remitente or REMITENTE_DESARROLLO,
            url_publica=url,
            carpeta=Path(carpeta) if carpeta else BUZON_POR_DEFECTO,
        )
        validar_entorno(config, entorno)
        return config
    if not remitente:
        raise CorreoNoValido("CORREO_REMITENTE es obligatoria con CORREO_MODO=smtp.")
    cifrado = _texto(source, "SMTP_CIFRADO").lower()
    if not cifrado:
        if entorno not in ENTORNOS_LOCALES:
            raise CorreoNoValido(
                "SMTP_CIFRADO es obligatoria fuera de development («starttls» o «ssl»)."
            )
        cifrado = "starttls"
    if cifrado not in CIFRADOS:
        raise CorreoNoValido(
            "SMTP_CIFRADO debe ser «starttls» o «ssl»: el correo nunca sale sin TLS."
        )
    puerto_texto = _texto(source, "SMTP_PUERTO")
    if not puerto_texto:
        puerto = PUERTO_POR_CIFRADO[cifrado]
    elif _ENTERO.fullmatch(puerto_texto):
        puerto = int(puerto_texto)
    else:
        raise CorreoNoValido("SMTP_PUERTO no es válida: debe ser un entero entre 1 y 65535.")
    # La clave no se recorta: un espacio puede ser parte de ella.
    clave = source.get("SMTP_CLAVE") or ""
    config = CorreoConfig(
        modo="smtp",
        remitente=remitente,
        url_publica=url,
        smtp_host=_texto(source, "SMTP_HOST") or None,
        smtp_puerto=puerto,
        smtp_usuario=_texto(source, "SMTP_USUARIO") or None,
        smtp_clave=clave if clave.strip() else None,
        smtp_cifrado=cifrado,
    )
    validar_entorno(config, entorno)
    return config
