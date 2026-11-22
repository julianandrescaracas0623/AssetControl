"""Procesar una imagen subida (spec 012, T2; R5; plan.md §3).

Nunca se guarda el archivo tal como llegó: se detecta el tipo por su contenido (JPEG, PNG
o WebP), se rechazan bombas de descompresión antes de decodificar, se aplica la
orientación EXIF, se pasa a RGB (fondo blanco si hay transparencia) y se vuelve a
codificar en JPEG **sin metadatos** (sin EXIF, GPS ni perfil de color), con lado mayor
≤ 1600 px, más una miniatura de 320 px.
"""

import io
import warnings
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELES = 40_000_000
LADO_COMPLETA = 1600
LADO_MINI = 320
CALIDAD = 82
FORMATOS = frozenset({"JPEG", "PNG", "WEBP"})


class ErrorImagen(ValueError):
    status = 422
    code = "imagen_invalida"
    message = "La imagen no se pudo leer. Toma la foto de nuevo."


class ImagenDemasiadoGrande(ErrorImagen):
    status = 413
    code = "imagen_demasiado_grande"
    message = "La foto pesa más de 10 MB."


class TipoNoAdmitido(ErrorImagen):
    status = 415
    code = "tipo_no_admitido"
    message = "Solo se admiten fotos JPEG, PNG o WebP."


class ImagenInvalida(ErrorImagen):
    pass


@dataclass(frozen=True)
class Procesada:
    completa: bytes
    mini: bytes
    ancho: int
    alto: int


def _jpeg(img: Image.Image, lado: int) -> tuple[bytes, Image.Image]:
    copia = img.copy()
    copia.thumbnail((lado, lado), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    # Sin ``exif`` ni ``icc_profile``: Pillow no escribe metadatos que no se le pasen.
    copia.save(buffer, "JPEG", quality=CALIDAD, optimize=True, progressive=True)
    return buffer.getvalue(), copia


def _rgb(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        con_alfa = img.convert("RGBA")
        fondo = Image.new("RGB", con_alfa.size, (255, 255, 255))
        fondo.paste(con_alfa, mask=con_alfa.getchannel("A"))
        return fondo
    return img.convert("RGB")


def _abrir(datos: bytes, max_bytes: int) -> Image.Image:
    """Decodifica con los mismos controles para fotos y logos; aplica la orientación."""
    if len(datos) > max_bytes:
        raise ImagenDemasiadoGrande()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            original = Image.open(io.BytesIO(datos))
            if original.format not in FORMATOS:
                raise TipoNoAdmitido()
            ancho, alto = original.size
            if ancho * alto > MAX_PIXELES:
                raise ImagenInvalida()
            original.load()
            return ImageOps.exif_transpose(original)
    except ErrorImagen:
        raise
    except UnidentifiedImageError:
        raise TipoNoAdmitido() from None
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, Warning):
        raise ImagenInvalida() from None


def procesar(datos: bytes) -> Procesada:
    img = _rgb(_abrir(datos, MAX_BYTES))
    completa, reducida = _jpeg(img, LADO_COMPLETA)
    mini, _ = _jpeg(img, LADO_MINI)
    return Procesada(completa=completa, mini=mini, ancho=reducida.width, alto=reducida.height)


# Spec 013 (R2): el logo de la empresa, en PNG con transparencia, ≤ 600 px y sin metadatos.
LOGO_MAX_BYTES = 2 * 1024 * 1024
LADO_LOGO = 600


class LogoDemasiadoGrande(ImagenDemasiadoGrande):
    message = "El logo pesa más de 2 MB."


@dataclass(frozen=True)
class Logo:
    png: bytes
    ancho: int
    alto: int


def procesar_logo(datos: bytes) -> Logo:
    try:
        img = _abrir(datos, LOGO_MAX_BYTES)
    except ImagenDemasiadoGrande:
        raise LogoDemasiadoGrande() from None
    img = img.convert("RGBA")
    img.thumbnail((LADO_LOGO, LADO_LOGO), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    # Una imagen nueva sin ``info``: PNG no copia textos, EXIF ni perfil de color.
    limpia = Image.new("RGBA", img.size)
    limpia.paste(img)
    limpia.save(buffer, "PNG", optimize=True)
    return Logo(png=buffer.getvalue(), ancho=limpia.width, alto=limpia.height)
