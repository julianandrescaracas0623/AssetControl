"""Exportar la lista de activos a Excel (spec 015, T4; R1, R1a; Q2 = A, Q3 = A).

Una hoja «Activos» con las columnas de Q3, encabezado fijo y filtro; sin fila de total
(un total fuera del cierre se confundiría con un informe). Recibe los ``Activo`` ya
filtrados por ``service.buscar_todos`` (la misma consulta que la lista) y no lee nada
más que su categoría y su ubicación.

Reglas (R1a): todo texto va con ``write_string`` y el libro se abre con
``strings_to_formulas=False`` (un nombre como ``=1+1`` queda como texto); el precio va
con ``write_number`` desde el ``Decimal`` exacto, con formato COP; las fechas son fechas
de Excel. Nada se registra en los logs.
"""

import io
from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.activos.models import Activo
from app.activos.service import _ruta as _ruta_de_ubicacion
from app.catalogo.models import Categoria, Ubicacion
from app.conteo.exportar import FORMATO_COP, HORA_COLOMBIA, XLSX

__all__ = ["HORA_COLOMBIA", "XLSX", "a_excel", "nombre_archivo"]

HOJA = "Activos"
FORMATO_FECHA = "dd/mm/yyyy"
ESTADOS = {"activo": "Activo", "en_reparacion": "En reparación", "dado_de_baja": "Dado de baja"}
# (encabezado, ancho en caracteres)
COLUMNAS = (
    ("Código", 14),
    ("Nombre", 36),
    ("Categoría", 20),
    ("Ubicación", 30),
    ("Estado", 14),
    ("Serial", 18),
    ("Marca", 16),
    ("Modelo", 16),
    ("Subtipo", 16),
    ("Fecha de compra", 15),
    ("Precio de compra", 18),
    ("Registrado el", 14),
)


def nombre_archivo(hoy: date | None = None) -> str:
    """Nombre fijo y ASCII: ``activos-AAAAMMDD.xlsx`` (sin datos de la clínica)."""
    dia = hoy or datetime.now(HORA_COLOMBIA).date()
    return f"activos-{dia:%Y%m%d}.xlsx"


def _ruta(session: Session, activo: Activo) -> str:
    ubicacion = session.get(Ubicacion, activo.ubicacion_id)
    return _ruta_de_ubicacion(session, ubicacion) if ubicacion else ""


def a_excel(session: Session, activos: Sequence[Activo]) -> bytes:
    import xlsxwriter  # Import local: solo quien exporta carga la librería.

    salida = io.BytesIO()
    libro = xlsxwriter.Workbook(
        salida,
        {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False},
    )
    libro.set_properties({"title": "Activos"})

    def formato(**kw):
        return libro.add_format({"font_name": "Calibri", "font_size": 10, **kw})

    cabecera = formato(bold=True, bottom=1)
    texto = formato()
    codigo = formato(font_name="Consolas")
    cop = formato(num_format=FORMATO_COP)
    fecha = formato(num_format=FORMATO_FECHA)

    hoja = libro.add_worksheet(HOJA)
    for col, (titulo, ancho) in enumerate(COLUMNAS):
        hoja.set_column(col, col, ancho)
        hoja.write_string(0, col, titulo, cabecera)

    for fila, a in enumerate(activos, start=1):
        categoria = session.get(Categoria, a.categoria_id)
        hoja.write_string(fila, 0, a.codigo, codigo)
        hoja.write_string(fila, 1, a.nombre, texto)
        hoja.write_string(fila, 2, categoria.nombre if categoria else "", texto)
        hoja.write_string(fila, 3, _ruta(session, a), texto)
        hoja.write_string(fila, 4, ESTADOS[a.estado], texto)
        for col, valor in enumerate((a.serial, a.marca, a.modelo, a.subtipo), start=5):
            if valor:
                hoja.write_string(fila, col, valor, texto)
        if a.fecha_compra is not None:
            hoja.write_datetime(fila, 9, a.fecha_compra, fecha)
        hoja.write_number(fila, 10, a.precio_compra, cop)
        hoja.write_datetime(fila, 11, a.creado_en.astimezone(HORA_COLOMBIA).date(), fecha)

    hoja.freeze_panes(1, 0)
    hoja.autofilter(0, 0, len(activos), len(COLUMNAS) - 1)
    libro.close()
    return salida.getvalue()
