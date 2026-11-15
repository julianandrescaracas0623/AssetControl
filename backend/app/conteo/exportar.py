"""Exportar el informe congelado a Excel y PDF (spec 009; CU-INF-03).

Una sola entrada: el dict de ``cierre.informe`` (lo mismo que ve la pantalla). De él
sale un ``Documento`` intermedio y de ese documento los dos archivos. Aquí no se suma
ni se vuelve a leer ``activo``, ``verificacion`` o el universo U (R8): cada cifra es la
del cierre. El formato COP y el porcentaje son los de la web (``lib/format.ts``,
``porcentaje`` de ``lib/sesiones.ts``) para que el archivo diga lo mismo que la pantalla.
"""

import io
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

# Colombia no tiene horario de verano: UTC−5 fijo (evita depender de tzdata en Windows).
HORA_COLOMBIA = timezone(timedelta(hours=-5), "COT")
CENTAVO = Decimal("0.01")


@dataclass(frozen=True)
class Cifra:
    valor: Decimal
    unidades: int


@dataclass(frozen=True)
class Fila:
    """Una fila del desglose (o la de totales): tres cifras y el % de unidades encontradas."""

    etiqueta: str
    encontrado: Cifra
    no_encontrado: Cifra
    registrado: Cifra
    porcentaje: str


@dataclass(frozen=True)
class NoEncontrado:
    codigo: str
    nombre: str
    categoria: str
    ubicacion: str
    precio: Decimal
    en_reparacion: bool


@dataclass(frozen=True)
class Documento:
    sesion: str
    corte: str
    cerrada_en: str
    cerrada_por: str
    totales: Fila
    por_categoria: tuple[Fila, ...]
    por_ubicacion: tuple[Fila, ...]
    no_encontrados: tuple[NoEncontrado, ...]


# --- Formato (igual que la web) ---------------------------------------------------------


def formato_cop(valor: Decimal) -> str:
    """``Decimal("1234567.8")`` → ``"$ 1.234.567,80"``; sin pasar por ``float``."""
    if valor != valor.quantize(CENTAVO):
        raise ValueError(f"Valor de dinero con más de dos decimales: {valor}")
    signo = "-" if valor < 0 else ""
    entero, _, decimales = f"{abs(valor):.2f}".partition(".")
    return f"{signo}$ {formato_entero(int(entero))},{decimales}"


def formato_entero(n: int) -> str:
    """``1234567`` → ``"1.234.567"``."""
    return f"{n:,}".replace(",", ".")


def porcentaje(encontradas: int, registradas: int) -> str:
    """Proporción de unidades con un decimal, como ``porcentaje`` y ``toLocaleString('es-CO')``."""
    if registradas == 0:
        return "0 %"
    decimas = (Decimal(encontradas) * 1000 / Decimal(registradas)).quantize(
        Decimal(1), rounding=ROUND_HALF_UP
    )
    entero, decima = divmod(int(decimas), 10)
    return f"{formato_entero(entero)} %" if decima == 0 else f"{formato_entero(entero)},{decima} %"


def _cuantos_no_encontrados(n: int) -> str:
    return f"{formato_entero(n)} {'activo no encontrado' if n == 1 else 'activos no encontrados'}"


def _fecha(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


def _fecha_hora(iso: str) -> str:
    momento = datetime.fromisoformat(iso).astimezone(HORA_COLOMBIA)
    hora = momento.hour % 12 or 12
    sufijo = "a. m." if momento.hour < 12 else "p. m."
    return f"{momento:%d/%m/%Y}, {hora}:{momento:%M} {sufijo}"


def nombre_base(nombre_sesion: str, fecha_corte: str) -> str:
    """Nombre de archivo ASCII y seguro: ``informe-<sesión>-corte-<AAAA-MM-DD>``."""
    ascii_ = unicodedata.normalize("NFKD", nombre_sesion).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_.lower()).strip("-")[:60].strip("-")
    corte = date.fromisoformat(fecha_corte).isoformat()
    return f"informe-{slug}-corte-{corte}" if slug else f"informe-corte-{corte}"


# --- Documento ---------------------------------------------------------------------------


def _cifra(valor: str, unidades: int) -> Cifra:
    return Cifra(Decimal(valor), unidades)


def _fila(etiqueta: str, datos: dict[str, Any], prefijo: str) -> Fila:
    return Fila(
        etiqueta=etiqueta,
        encontrado=_cifra(datos[f"{prefijo}encontrado"], datos["unidades_encontrado"]),
        no_encontrado=_cifra(datos[f"{prefijo}no_encontrado"], datos["unidades_no_encontrado"]),
        registrado=_cifra(datos[f"{prefijo}registrado"], datos["unidades_registrado"]),
        porcentaje=porcentaje(datos["unidades_encontrado"], datos["unidades_registrado"]),
    )


def documento(informe: dict[str, Any]) -> Documento:
    """Arma el documento a partir del informe congelado; no suma nada."""
    sesion = informe["sesion"]
    cerrada_por = sesion.get("cerrada_por") or {}
    return Documento(
        sesion=sesion["nombre"],
        corte=_fecha(sesion["fecha_corte"]),
        cerrada_en=_fecha_hora(sesion["cerrada_en"]) if sesion.get("cerrada_en") else "",
        cerrada_por=cerrada_por.get("nombre", ""),
        totales=_fila("Total", informe["totales"], ""),
        por_categoria=tuple(
            _fila(f["etiqueta"], f, "total_") for f in informe["desglose"]["categorias"]
        ),
        por_ubicacion=tuple(
            _fila(f["etiqueta"], f, "total_") for f in informe["desglose"]["ubicaciones"]
        ),
        no_encontrados=tuple(
            NoEncontrado(
                codigo=f["codigo"],
                nombre=f["nombre"],
                categoria=f["categoria"]["nombre"],
                ubicacion=f["ubicacion"]["ruta"],
                precio=Decimal(f["precio"]),
                en_reparacion=bool(f["en_reparacion"]),
            )
            for f in informe["no_encontrados"]
        ),
    )


# --- Excel (T2; Q2: dinero como número con formato COP, sin fórmulas) ----------------------

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FORMATO_COP = '"$" #,##0.00'
NOTA = (
    "Cifras calculadas por el servidor una sola vez, al cerrar la sesión. Lo encontrado usa "
    "el precio, la categoría y la ubicación del momento de contar; lo no encontrado, los del "
    "cierre. Los cambios posteriores no alteran este informe."
)
ENCABEZADO_DESGLOSE = (
    "Encontrado",
    "u.",
    "No encontrado",
    "u.",
    "Total registrado",
    "u.",
    "% encontrado",
)


def a_excel(doc: Documento) -> bytes:
    """Libro con portada, desglose por categoría y por ubicación y no encontrados.

    El texto se escribe siempre con ``write_string`` (nunca como fórmula, R6) y el dinero
    con ``write_number`` desde el ``Decimal`` exacto: en el XML queda ``1390000.50``.
    """
    import xlsxwriter  # Import local: solo quien exporta carga la librería.

    salida = io.BytesIO()
    libro = xlsxwriter.Workbook(
        salida,
        {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False},
    )
    libro.set_properties({"title": f"Informe · {doc.sesion}", "comments": "Informe congelado"})
    negrita = libro.add_format({"bold": True})
    titulo = libro.add_format({"bold": True, "font_size": 14})
    encabezado = libro.add_format({"bold": True, "bottom": 1, "bg_color": "#F4F4F5"})
    encabezado_num = libro.add_format(
        {"bold": True, "bottom": 1, "bg_color": "#F4F4F5", "align": "right"}
    )
    cop = libro.add_format({"num_format": FORMATO_COP})
    cop_total = libro.add_format({"num_format": FORMATO_COP, "bold": True, "top": 1})
    entero = libro.add_format({"num_format": "#,##0"})
    entero_total = libro.add_format({"num_format": "#,##0", "bold": True, "top": 1})
    texto_total = libro.add_format({"bold": True, "top": 1})
    derecha = libro.add_format({"align": "right"})
    derecha_total = libro.add_format({"align": "right", "bold": True, "top": 1})
    nota = libro.add_format({"italic": True, "font_color": "#52525B", "text_wrap": True})

    # Portada.
    hoja = libro.add_worksheet("Informe")
    hoja.set_column(0, 0, 28)
    hoja.set_column(1, 1, 22)
    hoja.set_column(2, 2, 12)
    hoja.write_string(0, 0, f"Informe · {doc.sesion}", titulo)
    fila = 2
    for rotulo, valor in (
        ("Sesión", doc.sesion),
        ("Fecha de corte", doc.corte),
        ("Cerrada", doc.cerrada_en),
        ("Por", doc.cerrada_por),
        ("Estado", "Informe congelado"),
        ("Moneda", "COP"),
    ):
        hoja.write_string(fila, 0, rotulo, negrita)
        hoja.write_string(fila, 1, valor)
        fila += 1
    fila += 1
    hoja.write_string(fila, 0, "Cifra", encabezado)
    hoja.write_string(fila, 1, "Valor", encabezado_num)
    hoja.write_string(fila, 2, "Unidades", encabezado_num)
    fila += 1
    t = doc.totales
    for rotulo, cifra in (
        ("Encontrado", t.encontrado),
        ("No encontrado", t.no_encontrado),
        ("Total registrado", t.registrado),
    ):
        hoja.write_string(fila, 0, rotulo, negrita)
        hoja.write_number(fila, 1, cifra.valor, cop)
        hoja.write_number(fila, 2, cifra.unidades, entero)
        fila += 1
    hoja.write_string(fila, 0, "% de unidades encontradas", negrita)
    hoja.write_string(fila, 1, t.porcentaje, derecha)
    fila += 2
    hoja.merge_range(fila, 0, fila + 2, 2, "", nota)
    hoja.write_string(fila, 0, NOTA, nota)

    # Desglose.
    for nombre, rotulo, filas in (
        ("Por categoría", "Categoría (al cierre)", doc.por_categoria),
        ("Por ubicación", "Ubicación (al cierre)", doc.por_ubicacion),
    ):
        hoja = libro.add_worksheet(nombre)
        hoja.set_column(0, 0, 34)
        hoja.set_column(1, 7, 16)
        hoja.freeze_panes(1, 1)
        hoja.write_string(0, 0, rotulo, encabezado)
        for col, texto in enumerate(ENCABEZADO_DESGLOSE, start=1):
            hoja.write_string(0, col, texto, encabezado_num)
        for i, f in enumerate((*filas, t), start=1):
            es_total = f is t
            hoja.write_string(i, 0, f.etiqueta, texto_total if es_total else None)
            for col, cifra in enumerate((f.encontrado, f.no_encontrado, f.registrado)):
                hoja.write_number(i, 1 + 2 * col, cifra.valor, cop_total if es_total else cop)
                hoja.write_number(
                    i, 2 + 2 * col, cifra.unidades, entero_total if es_total else entero
                )
            hoja.write_string(i, 7, f.porcentaje, derecha_total if es_total else derecha)

    # No encontrados.
    hoja = libro.add_worksheet("No encontrados")
    hoja.set_column(0, 0, 14)
    hoja.set_column(1, 1, 34)
    hoja.set_column(2, 3, 26)
    hoja.set_column(4, 4, 16)
    hoja.set_column(5, 5, 18)
    hoja.freeze_panes(1, 0)
    for col, texto in enumerate(
        ("Código", "Activo", "Categoría", "Ubicación esperada", "Nota al cierre")
    ):
        hoja.write_string(0, col, texto, encabezado)
    hoja.write_string(0, 5, "Precio", encabezado_num)
    for i, n in enumerate(doc.no_encontrados, start=1):
        hoja.write_string(i, 0, n.codigo)
        hoja.write_string(i, 1, n.nombre)
        hoja.write_string(i, 2, n.categoria)
        hoja.write_string(i, 3, n.ubicacion)
        if n.en_reparacion:
            hoja.write_string(i, 4, "En reparación")
        hoja.write_number(i, 5, n.precio, cop)
    i = len(doc.no_encontrados) + 1
    hoja.write_string(i, 0, _cuantos_no_encontrados(len(doc.no_encontrados)), texto_total)
    for col in range(1, 5):
        hoja.write_blank(i, col, None, texto_total)
    hoja.write_number(i, 5, t.no_encontrado.valor, cop_total)

    libro.close()
    return salida.getvalue()
