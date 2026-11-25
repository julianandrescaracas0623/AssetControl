"""Exportar la lista de activos a Excel (spec 015, T4; R1, R1a; Q2 = A, Q3 = A).

Una hoja «Activos» con las columnas de Q3, encabezado fijo y filtro; sin fila de total
(un total fuera del cierre se confundiría con un informe). Recibe los ``Activo`` ya
filtrados por ``service.buscar_todos`` (la misma consulta que la lista) y no lee nada
más que su categoría y su ubicación.

Diseño (spec 019, T3): replica la plantilla A (``Activos_20261122_diseno.xlsx``) con el
estilo común de ``app.conteo.exportar_estilo``: banda y bloque de la empresa VIGENTE del
tenant en las filas 1–5 (logo, nombre, «Exportado dd/mm/aaaa», NIT, teléfono, correo y
dirección; los campos ausentes se omiten, Q9; logo ajustado a la caja con su proporción,
Q10), cabecera en la fila 7, datos desde la 8, congelado bajo la cabecera, filtro, impresión
horizontal de 1 página de ancho, anchos, alturas y formatos medidos. Datos, orden de filas y
columnas, sin cambios.

Celda vacía (decisión de T3): lleva el estilo de su columna en la fila de datos de la
plantilla (req. 5); la plantilla A no tiene un estilo «vacía» propio (F8 e I8, vacías,
tienen el estilo de las celdas de texto). Así cada celda conserva su borde.

Reglas (R1a): todo texto va con ``write_string`` y el libro se abre con
``strings_to_formulas=False`` (un nombre como ``=1+1`` queda como texto); el precio va
con ``write_number`` desde el ``Decimal`` exacto (un ``float`` se rechaza), con formato
COP; las fechas son fechas de Excel. Nada se registra en los logs.
"""

import io
from collections.abc import Sequence
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.activos.models import Activo
from app.activos.service import _ruta as _ruta_de_ubicacion
from app.catalogo.models import Categoria, Ubicacion
from app.conteo import exportar_estilo as est
from app.conteo.exportar import HORA_COLOMBIA, XLSX

__all__ = ["HORA_COLOMBIA", "XLSX", "a_excel", "nombre_archivo"]

HOJA = "Activos"
PLANTILLA = est.PLANTILLAS["activos"]
ESTADOS = {"activo": "Activo", "en_reparacion": "En reparación", "dado_de_baja": "Dado de baja"}
COLUMNAS = (
    "Código",
    "Nombre",
    "Categoría",
    "Ubicación",
    "Estado",
    "Serial",
    "Marca",
    "Modelo",
    "Subtipo",
    "Fecha de compra",
    "Precio de compra",
    "Registrado el",
)


def nombre_archivo(hoy: date | None = None) -> str:
    """Nombre fijo y ASCII: ``activos-AAAAMMDD.xlsx`` (sin datos de la clínica)."""
    dia = hoy or datetime.now(HORA_COLOMBIA).date()
    return f"activos-{dia:%Y%m%d}.xlsx"


def _ruta(session: Session, activo: Activo) -> str:
    ubicacion = session.get(Ubicacion, activo.ubicacion_id)
    return _ruta_de_ubicacion(session, ubicacion) if ubicacion else ""


def _texto(valor: str | None) -> str | None:
    """Un texto vacío o solo de espacios es una celda vacía (con su borde)."""
    return valor if valor and valor.strip() else None


def _valores(session: Session, a: Activo) -> tuple:
    categoria = session.get(Categoria, a.categoria_id)
    return (
        a.codigo,
        a.nombre,
        _texto(categoria.nombre if categoria else None),
        _texto(_ruta(session, a)),
        ESTADOS[a.estado],
        _texto(a.serial),
        _texto(a.marca),
        _texto(a.modelo),
        _texto(a.subtipo),
        a.fecha_compra,
        a.precio_compra,
        a.creado_en.astimezone(HORA_COLOMBIA).date(),
    )


def a_excel(
    session: Session,
    activos: Sequence[Activo],
    empresa: est.DatosEmpresa,
    hoy: date,
) -> bytes:
    """El libro de la lista; ``empresa`` es la vigente del tenant y ``hoy``, la fecha de
    exportación en Colombia (la misma del nombre del archivo)."""
    import xlsxwriter  # Import local: solo quien exporta carga la librería.

    salida = io.BytesIO()
    libro = xlsxwriter.Workbook(
        salida,
        {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False},
    )
    libro.set_properties(est.propiedades(HOJA))
    estilos = est.Estilos(libro)
    hoja = libro.add_worksheet(HOJA)

    cabecera = PLANTILLA.fila_cabecera
    ultima_fila = cabecera + len(activos)
    est.preparar_hoja(hoja, PLANTILLA, ultima_fila)
    est.dibujar_bloque(hoja, estilos, PLANTILLA, empresa, hoy)
    est.escribir_fila(
        hoja, estilos, cabecera, list(zip(COLUMNAS, PLANTILLA.estilos_cabecera, strict=True))
    )
    for fila, a in enumerate(activos, start=PLANTILLA.fila_datos):
        est.escribir_fila(
            hoja,
            estilos,
            fila,
            list(zip(_valores(session, a), PLANTILLA.estilos_datos, strict=True)),
            PLANTILLA.alto_datos,
        )
    hoja.autofilter(cabecera, 0, ultima_fila, len(COLUMNAS) - 1)
    libro.close()
    return salida.getvalue()
