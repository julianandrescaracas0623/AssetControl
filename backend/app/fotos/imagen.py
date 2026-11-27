"""Procesar una imagen subida (spec 012, T2; R5; plan.md §3).

Nunca se guarda el archivo tal como llegó: se detecta el tipo por su contenido (JPEG, PNG
o WebP), se rechazan bombas de descompresión antes de decodificar, se aplica la
orientación EXIF, se pasa a RGB (fondo blanco si hay transparencia) y se vuelve a
codificar en JPEG **sin metadatos** (sin EXIF, GPS ni perfil de color), con lado mayor
≤ 1600 px, más una miniatura de 320 px.
"""

import io
import threading
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 10 * 1024 * 1024
# SEC-02: 25 MP (antes 40 MP). Decodificar a RGB cuesta ~3 bytes por píxel; con 40 MP una
# foto llegaba a ~350 MB por subida. 25 MP cubren cámaras de 20 a 24 MP sin problema.
MAX_PIXELES = 25_000_000
LADO_COMPLETA = 1600
LADO_MINI = 320
CALIDAD = 82
FORMATOS = frozenset({"JPEG", "PNG", "WEBP"})
# SEC-02: decodificaciones simultáneas por proceso y espera máxima antes de responder 503.
MAX_DECODIFICACIONES = 2
ESPERA_DECODIFICACION_SEGUNDOS = 5.0
_CUPO_DECODIFICACION = threading.BoundedSemaphore(MAX_DECODIFICACIONES)


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


class ImagenOcupada(ErrorImagen):
    status = 503
    code = "procesado_ocupado"
    message = "Hay varias fotos procesándose. Intenta de nuevo en unos segundos."


@contextmanager
def _cupo_de_decodificacion() -> Iterator[None]:
    """Limita cuántas imágenes se decodifican a la vez en este proceso (SEC-02)."""
    if not _CUPO_DECODIFICACION.acquire(timeout=ESPERA_DECODIFICACION_SEGUNDOS):
        raise ImagenOcupada()
    try:
        yield
    finally:
        _CUPO_DECODIFICACION.release()


@dataclass(frozen=True)
class Procesada:
    completa: bytes
    mini: bytes
    ancho: int
    alto: int


def _reducir(img: Image.Image, lado: int) -> Image.Image:
    """Imagen con lado mayor ≤ ``lado``. Si ya cabe, devuelve la misma (sin copiar)."""
    ancho, alto = img.size
    mayor = max(ancho, alto)
    if mayor <= lado:
        return img
    escala = lado / mayor
    nuevo = (max(1, round(ancho * escala)), max(1, round(alto * escala)))
    # resize crea solo la imagen pequeña: no se copia la decodificada completa.
    return img.resize(nuevo, Image.Resampling.LANCZOS)


def _codificar(img: Image.Image) -> bytes:
    buffer = io.BytesIO()
    # Sin ``exif`` ni ``icc_profile``: Pillow no escribe metadatos que no se le pasen.
    img.save(buffer, "JPEG", quality=CALIDAD, optimize=True, progressive=True)
    return buffer.getvalue()


def _rgb(img: Image.Image) -> Image.Image:
    if img.mode == "RGB":
        return img
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
            # in_place: sin una copia completa extra solo para girar (SEC-02).
            ImageOps.exif_transpose(original, in_place=True)
            return original
    except ErrorImagen:
        raise
    except UnidentifiedImageError:
        raise TipoNoAdmitido() from None
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError, Warning):
        raise ImagenInvalida() from None


def procesar(datos: bytes) -> Procesada:
    with _cupo_de_decodificacion():
        img = _rgb(_abrir(datos, MAX_BYTES))
        completa = _reducir(img, LADO_COMPLETA)
        # La miniatura sale de la completa (ya pequeña), no de la imagen decodificada.
        mini = _reducir(completa, LADO_MINI)
        return Procesada(
            completa=_codificar(completa),
            mini=_codificar(mini),
            ancho=completa.width,
            alto=completa.height,
        )


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
    with _cupo_de_decodificacion():
        try:
            img = _abrir(datos, LOGO_MAX_BYTES)
        except ImagenDemasiadoGrande:
            raise LogoDemasiadoGrande() from None
        img = _reducir(img.convert("RGBA"), LADO_LOGO)
        buffer = io.BytesIO()
        # Una imagen nueva sin ``info``: PNG no copia textos, EXIF ni perfil de color.
        limpia = Image.new("RGBA", img.size)
        limpia.paste(img)
        limpia.save(buffer, "PNG", optimize=True)
        return Logo(png=buffer.getvalue(), ancho=limpia.width, alto=limpia.height)
