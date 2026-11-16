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


def procesar(datos: bytes) -> Procesada:
    if len(datos) > MAX_BYTES:
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
            girada = ImageOps.exif_transpose(original)
            img = _rgb(girada)
    except ErrorImagen:
        raise
    except UnidentifiedImageError:
        raise TipoNoAdmitido() from None
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, Warning):
        raise ImagenInvalida() from None
    completa, reducida = _jpeg(img, LADO_COMPLETA)
    mini, _ = _jpeg(img, LADO_MINI)
    return Procesada(completa=completa, mini=mini, ancho=reducida.width, alto=reducida.height)
