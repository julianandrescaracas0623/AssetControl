"""Procesar la imagen subida (spec 012, T2; R5; plan.md §3).

La imagen guardada nunca es la que llegó: se decodifica, se gira según su EXIF, se pasa a
RGB y se vuelve a codificar en JPEG sin metadatos (sin GPS), con lado ≤ 1600 px, más una
miniatura de 320 px. Se rechazan tipos no admitidos por su contenido, archivos grandes,
imágenes rotas y bombas de descompresión.
"""

import io

import pytest
from PIL import Image

from app.fotos import imagen
from app.fotos.imagen import ImagenDemasiadoGrande, ImagenInvalida, TipoNoAdmitido

GPS_IFD = 0x8825
ORIENTACION = 0x0112


def _imagen(formato="JPEG", tamano=(400, 200), modo="RGB", color=(200, 30, 30), **kw) -> bytes:
    buffer = io.BytesIO()
    Image.new(modo, tamano, color).save(buffer, formato, **kw)
    return buffer.getvalue()


def _con_gps_y_orientacion(tamano=(400, 200)) -> bytes:
    exif = Image.Exif()
    exif[ORIENTACION] = 6  # girada 90°: se muestra de pie
    exif[0x010F] = "Fabricante del teléfono"
    exif[0x0110] = "Modelo del teléfono"
    exif.get_ifd(GPS_IFD).update({1: "N", 2: (4.0, 44.0, 0.0), 3: "W", 4: (75.0, 54.0, 0.0)})
    return _imagen(tamano=tamano, exif=exif.tobytes())


def _abrir(datos: bytes) -> Image.Image:
    salida = Image.open(io.BytesIO(datos))
    salida.load()
    return salida


def test_output_is_jpeg_with_a_thumbnail():
    resultado = imagen.procesar(_imagen("PNG", (800, 600)))
    completa, mini = _abrir(resultado.completa), _abrir(resultado.mini)
    assert completa.format == mini.format == "JPEG"
    assert completa.size == (800, 600) == (resultado.ancho, resultado.alto)
    assert max(mini.size) == 320


def test_large_photos_are_reduced_to_1600_on_the_long_side():
    resultado = imagen.procesar(_imagen(tamano=(4000, 3000)))
    assert _abrir(resultado.completa).size == (1600, 1200)
    assert (resultado.ancho, resultado.alto) == (1600, 1200)


def test_small_photos_are_not_enlarged():
    resultado = imagen.procesar(_imagen(tamano=(120, 90)))
    assert _abrir(resultado.completa).size == (120, 90)
    assert _abrir(resultado.mini).size == (120, 90)


def test_metadata_is_removed_gps_included_and_orientation_is_applied():
    entrada = _con_gps_y_orientacion()
    assert _abrir(entrada).getexif().get_ifd(GPS_IFD)  # la entrada sí trae GPS
    resultado = imagen.procesar(entrada)
    for datos in (resultado.completa, resultado.mini):
        salida = _abrir(datos)
        assert not salida.getexif(), "no debe quedar EXIF"
        assert "exif" not in salida.info and "icc_profile" not in salida.info
        assert b"Exif" not in datos[:4096] and "teléfono".encode() not in datos
    # Girada según la orientación 6: de 400x200 pasa a 200x400.
    assert _abrir(resultado.completa).size == (200, 400)


def test_transparent_png_gets_a_white_background():
    resultado = imagen.procesar(_imagen("PNG", (50, 50), "RGBA", (0, 0, 0, 0)))
    salida = _abrir(resultado.completa)
    assert salida.mode == "RGB"
    assert all(c > 245 for c in salida.getpixel((25, 25)))


@pytest.mark.parametrize("formato", ["JPEG", "PNG", "WEBP"])
def test_jpeg_png_and_webp_are_accepted(formato):
    assert imagen.procesar(_imagen(formato)).completa


@pytest.mark.parametrize(
    "datos",
    [
        _imagen("GIF", modo="P", color=1),
        _imagen("BMP"),
        _imagen("TIFF"),
        b"%PDF-1.7 no soy una foto",
        b"<svg xmlns='http://www.w3.org/2000/svg'/>",
        b"texto cualquiera que dice ser jpeg",
    ],
)
def test_other_types_are_refused_by_content(datos):
    with pytest.raises(TipoNoAdmitido):
        imagen.procesar(datos)


def test_empty_file_is_refused():
    with pytest.raises(TipoNoAdmitido):
        imagen.procesar(b"")


def test_truncated_image_is_invalid():
    datos = _imagen(tamano=(600, 600))
    with pytest.raises(ImagenInvalida):
        imagen.procesar(datos[: len(datos) // 3])


def test_size_limit_is_10_mb():
    assert imagen.MAX_BYTES == 10 * 1024 * 1024
    with pytest.raises(ImagenDemasiadoGrande):
        imagen.procesar(b"\xff\xd8" + b"0" * imagen.MAX_BYTES)


def test_decompression_bomb_is_refused_before_decoding():
    # 10.000 x 10.000 = 100 MP en un PNG de pocos KB.
    bomba = _imagen("PNG", (10_000, 10_000), "L", 0)
    assert len(bomba) < imagen.MAX_BYTES
    with pytest.raises(ImagenInvalida):
        imagen.procesar(bomba)
