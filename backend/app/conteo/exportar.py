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
from collections.abc import Sequence
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
    id: str | None = None


@dataclass(frozen=True)
class NoEncontrado:
    codigo: str
    nombre: str
    categoria: str
    ubicacion: str
    precio: Decimal
    en_reparacion: bool


@dataclass(frozen=True)
class Empresa:
    """Datos de la empresa congelados al cierre (spec 013, R3) y los bytes de su logo."""

    nombre: str
    direccion: str | None = None
    nit: str | None = None
    telefono: str | None = None
    correo: str | None = None
    vigente: bool = False
    logo: bytes | None = None

    @property
    def contacto(self) -> str:
        """``NIT … · dirección · Tel. … · correo``, solo lo que exista."""
        partes = [
            f"NIT {self.nit}" if self.nit else None,
            self.direccion,
            f"Tel. {self.telefono}" if self.telefono else None,
            self.correo,
        ]
        return " · ".join(p for p in partes if p)


@dataclass(frozen=True)
class Detalle:
    """Un activo del detalle congelado al cierre (spec 013, R4)."""

    codigo: str
    nombre: str
    marca: str | None
    serial: str | None
    categoria_id: str
    categoria: str
    ubicacion: str
    encontrada: str | None
    estado_fisico: str | None
    encontrado: bool
    en_reparacion: bool
    precio: Decimal

    @property
    def estado(self) -> str:
        if self.estado_fisico == "danado":
            return "Dañado"
        if self.estado_fisico == "ok":
            return "Ok"
        return "En reparación" if self.en_reparacion else ""

    @property
    def resultado(self) -> str:
        return "Encontrado" if self.encontrado else "No encontrado"


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
    empresa: Empresa = Empresa(nombre="")
    detalle_disponible: bool = False
    detalle: tuple[Detalle, ...] = ()

    def categorias_con_detalle(self) -> list[tuple[Fila, tuple[Detalle, ...]]]:
        """Cada categoría del desglose con sus activos, en el orden del detalle."""
        filas = {f.id: f for f in self.por_categoria}
        grupos: dict[str, list[Detalle]] = {}
        for d in self.detalle:
            grupos.setdefault(d.categoria_id, []).append(d)
        return [(filas[cid], tuple(activos)) for cid, activos in grupos.items()]


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
        id=datos.get("id"),
        etiqueta=etiqueta,
        encontrado=_cifra(datos[f"{prefijo}encontrado"], datos["unidades_encontrado"]),
        no_encontrado=_cifra(datos[f"{prefijo}no_encontrado"], datos["unidades_no_encontrado"]),
        registrado=_cifra(datos[f"{prefijo}registrado"], datos["unidades_registrado"]),
        porcentaje=porcentaje(datos["unidades_encontrado"], datos["unidades_registrado"]),
    )


def documento(
    informe: dict[str, Any], detalle: Sequence[Any] = (), logo: bytes | None = None
) -> Documento:
    """Arma el documento a partir del informe congelado y su detalle; no suma nada.

    ``detalle`` son las filas de ``cierre.detalle`` (spec 013) y ``logo``, los bytes del
    logo congelado (o nada si no hay o no se pudo leer).
    """
    sesion = informe["sesion"]
    cerrada_por = sesion.get("cerrada_por") or {}
    empresa = informe["empresa"]
    return Documento(
        empresa=Empresa(
            nombre=empresa["nombre"],
            direccion=empresa["direccion"],
            nit=empresa["nit"],
            telefono=empresa["telefono"],
            correo=empresa["correo"],
            vigente=bool(empresa["vigente"]),
            logo=logo,
        ),
        detalle_disponible=bool(informe["detalle_disponible"]),
        detalle=tuple(
            Detalle(
                codigo=d.codigo,
                nombre=d.nombre,
                marca=d.marca,
                serial=d.serial,
                categoria_id=str(d.categoria_id),
                categoria=d.categoria_nombre,
                ubicacion=d.ubicacion_ruta,
                encontrada=d.encontrada_ruta,
                estado_fisico=d.estado_fisico,
                encontrado=d.encontrado,
                en_reparacion=d.en_reparacion,
                precio=Decimal(d.precio),
            )
            for d in detalle
        ),
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


def nombres_de_hoja(categorias: Sequence[str]) -> list[str]:
    """Nombres de hoja válidos y únicos para cada categoría (spec 013, R5).

    Excel no admite ``[]:*?/\\``, más de 31 caracteres, comillas simples al principio o
    al final, ni dos hojas con el mismo nombre (sin distinguir mayúsculas). Tampoco se
    usan «Resumen» ni «No encontrados», que son las otras hojas del libro.
    """
    usados = {HOJA_RESUMEN.casefold(), HOJA_NO_ENCONTRADOS.casefold()}
    nombres = []
    for categoria in categorias:
        limpio = re.sub(r"[\[\]:*?/\\]", " ", categoria)
        limpio = " ".join(limpio.split()).strip("'").strip() or "Categoría"
        base = limpio[:31].rstrip()
        nombre, n = base, 2
        while nombre.casefold() in usados:
            sufijo = f" ({n})"
            nombre = base[: 31 - len(sufijo)].rstrip() + sufijo
            n += 1
        usados.add(nombre.casefold())
        nombres.append(nombre)
    return nombres


HOJA_RESUMEN = "Resumen"
HOJA_NO_ENCONTRADOS = "No encontrados"
COLUMNAS_DETALLE = (
    ("Código", 13),
    ("Activo", 32),
    ("Marca", 16),
    ("Serial", 16),
    ("Ubicación esperada", 30),
    ("Encontrado en", 30),
    ("Estado físico", 14),
    ("Resultado", 15),
    ("Precio (COP)", 18),
)
SIN_DETALLE = (
    "Esta sesión se cerró antes de que AssetControl guardara el detalle por activo: el "
    "libro no trae una hoja por categoría."
)
EMPRESA_VIGENTE = (
    "Datos de la empresa vigentes: la sesión se cerró antes de guardarlos con el informe."
)
FILA_TABLA = 6  # primera fila después del encabezado común (filas 0–4)


def a_excel(doc: Documento) -> bytes:
    """Libro v3 (spec 013, R5): «Resumen», una hoja por categoría y «No encontrados».

    Cada hoja lleva el encabezado de la empresa congelada (logo, datos y sesión). El texto
    va siempre con ``write_string`` (nunca fórmula) y el dinero con ``write_number`` desde
    el ``Decimal`` exacto. Los totales salen del desglose congelado: aquí no se suma.
    """
    import xlsxwriter  # Import local: solo quien exporta carga la librería.

    salida = io.BytesIO()
    libro = xlsxwriter.Workbook(
        salida,
        {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False},
    )
    libro.set_properties({"title": f"Informe · {doc.sesion}", "comments": "Informe congelado"})
    acento, gris, linea = "#0E7490", "#71717A", "#E4E4E7"

    def formato(**kw):
        return libro.add_format(
            {"font_name": "Calibri", "font_size": 10, "valign": "vcenter", **kw}
        )

    f = {
        "empresa": formato(bold=True, font_size=15),
        "gris": formato(font_color=gris),
        "rotulo": formato(font_color=gris, font_size=9),
        "titulo": formato(bold=True, font_size=12, font_color=acento),
        "cifra": formato(bold=True, font_size=16, num_format=FORMATO_COP),
        "cabecera": formato(
            bold=True,
            font_color="#FFFFFF",
            bg_color=acento,
            text_wrap=True,
            border=1,
            border_color=acento,
        ),
        "cabecera_num": formato(
            bold=True,
            font_color="#FFFFFF",
            bg_color=acento,
            text_wrap=True,
            border=1,
            border_color=acento,
            align="right",
        ),
        "texto": formato(bottom=1, bottom_color=linea),
        "codigo": formato(font_name="Consolas", bottom=1, bottom_color=linea),
        "cop": formato(num_format=FORMATO_COP, bottom=1, bottom_color=linea),
        "entero": formato(num_format="#,##0", bottom=1, bottom_color=linea),
        "derecha": formato(align="right", bottom=1, bottom_color=linea),
        "encontrado": formato(font_color="#15803D", bottom=1, bottom_color=linea),
        "no_encontrado": formato(font_color="#B91C1C", bold=True, bottom=1, bottom_color=linea),
        "danado": formato(font_color="#B45309", bottom=1, bottom_color=linea),
        "movido": formato(font_color="#B45309", italic=True, bottom=1, bottom_color=linea),
        "total": formato(bold=True, top=2, bottom=2),
        "total_cop": formato(bold=True, top=2, bottom=2, num_format=FORMATO_COP),
        "total_entero": formato(bold=True, top=2, bottom=2, num_format="#,##0"),
        "total_derecha": formato(bold=True, top=2, bottom=2, align="right"),
        "nota": formato(italic=True, font_color=gris, text_wrap=True, valign="top"),
    }
    e = doc.empresa
    sesion = (
        f"Informe de inventario «{doc.sesion}» · corte {doc.corte} · "
        f"cerrada {doc.cerrada_en} por {doc.cerrada_por}"
    )
    estado = "Informe congelado al cierre · valores en COP"
    if e.vigente:
        estado += f" · {EMPRESA_VIGENTE}"

    def encabezado(hoja, filas_repetidas: int) -> None:
        hoja.hide_gridlines(2)
        hoja.set_row(0, 34)
        if e.logo:
            ancho, alto = _tamano_png(e.logo)
            escala = min(40 / alto, 110 / ancho) if ancho and alto else 1
            hoja.insert_image(
                0,
                0,
                "logo.png",
                {
                    "image_data": io.BytesIO(e.logo),
                    "x_scale": escala,
                    "y_scale": escala,
                    "x_offset": 4,
                    "y_offset": 4,
                    "object_position": 3,
                },
            )
        hoja.write_string(0, 1, e.nombre, f["empresa"])
        if e.contacto:
            hoja.write_string(1, 1, e.contacto, f["gris"])
        hoja.write_string(2, 1, sesion, f["gris"])
        hoja.write_string(3, 1, estado, f["rotulo"])
        hoja.set_landscape()
        hoja.set_paper(1)  # Carta
        hoja.fit_to_pages(1, 0)
        hoja.repeat_rows(filas_repetidas, filas_repetidas)
        hoja.set_margins(left=0.4, right=0.4, top=0.6, bottom=0.6)
        hoja.set_header(f"&L&8{_cabecera_impresion(e.nombre)}&R&8{_cabecera_impresion(doc.sesion)}")
        hoja.set_footer("&L&8Generado con AssetControl&RPágina &P de &N")

    def texto(hoja, fila: int, col: int, valor: str | None, fmt) -> None:
        """Texto siempre como texto (nunca fórmula); vacío como celda en blanco."""
        if valor:
            hoja.write_string(fila, col, valor, fmt)
        else:
            hoja.write_blank(fila, col, None, fmt)

    def cabecera(hoja, fila: int, columnas: Sequence[str], numericas: int) -> None:
        for col, texto in enumerate(columnas):
            hoja.write_string(
                fila, col, texto, f["cabecera_num" if col >= numericas else "cabecera"]
            )
        hoja.set_row(fila, 22)

    def tabla_desglose(hoja, fila: int, titulo: str, rotulo: str, filas: tuple[Fila, ...]) -> int:
        hoja.write_string(fila, 0, titulo, f["titulo"])
        cabecera(hoja, fila + 1, (rotulo, *ENCABEZADO_DESGLOSE), 1)
        fila += 2
        for d in (*filas, doc.totales):
            total = d is doc.totales
            hoja.write_string(fila, 0, d.etiqueta, f["total" if total else "texto"])
            for i, cifra in enumerate((d.encontrado, d.no_encontrado, d.registrado)):
                hoja.write_number(fila, 1 + 2 * i, cifra.valor, f["total_cop" if total else "cop"])
                hoja.write_number(
                    fila, 2 + 2 * i, cifra.unidades, f["total_entero" if total else "entero"]
                )
            hoja.write_string(fila, 7, d.porcentaje, f["total_derecha" if total else "derecha"])
            fila += 1
        return fila + 1

    # --- Resumen
    hoja = libro.add_worksheet(HOJA_RESUMEN)
    encabezado(hoja, 0)
    hoja.set_column(0, 0, 34)
    hoja.set_column(1, 7, 17)
    t = doc.totales
    for i, (rotulo, cifra) in enumerate(
        (
            ("Encontrado", t.encontrado),
            ("No encontrado", t.no_encontrado),
            ("Total registrado", t.registrado),
        )
    ):
        # Cada cifra ocupa dos columnas (la del valor y la de sus unidades) para que quepa.
        col = 1 + 2 * i
        hoja.merge_range(FILA_TABLA - 1, col, FILA_TABLA - 1, col + 1, rotulo, f["rotulo"])
        hoja.merge_range(FILA_TABLA, col, FILA_TABLA, col + 1, "", f["cifra"])
        hoja.write_number(FILA_TABLA, col, cifra.valor, f["cifra"])
        hoja.merge_range(
            FILA_TABLA + 1, col, FILA_TABLA + 1, col + 1, _unidades(cifra.unidades), f["gris"]
        )
    hoja.set_row(FILA_TABLA, 24)
    hoja.write_string(FILA_TABLA + 2, 1, f"{t.porcentaje} de las unidades encontradas.", f["gris"])
    fila = tabla_desglose(
        hoja, FILA_TABLA + 4, "Por categoría", "Categoría (al cierre)", doc.por_categoria
    )
    fila = tabla_desglose(hoja, fila, "Por ubicación", "Ubicación (al cierre)", doc.por_ubicacion)
    hoja.merge_range(fila, 0, fila + 1, 7, "", f["nota"])
    hoja.write_string(fila, 0, NOTA, f["nota"])
    if not doc.detalle_disponible:
        hoja.merge_range(fila + 2, 0, fila + 3, 7, "", f["nota"])
        hoja.write_string(fila + 2, 0, SIN_DETALLE, f["nota"])

    # --- Una hoja por categoría (R5)
    grupos = doc.categorias_con_detalle()
    for nombre, (cifras, activos) in zip(
        nombres_de_hoja([g[0].etiqueta for g in grupos]), grupos, strict=True
    ):
        hoja = libro.add_worksheet(nombre)
        primera = FILA_TABLA + 2
        encabezado(hoja, primera - 1)
        for col, (_, ancho) in enumerate(COLUMNAS_DETALLE):
            hoja.set_column(col, col, ancho)
        hoja.write_string(FILA_TABLA - 1, 1, f"Categoría: {cifras.etiqueta}", f["titulo"])
        hoja.write_string(
            FILA_TABLA,
            1,
            f"{_activos(cifras.registrado.unidades)} · encontrados "
            f"{formato_entero(cifras.encontrado.unidades)} ({cifras.porcentaje}) por "
            f"{formato_cop(cifras.encontrado.valor)} · no encontrados "
            f"{formato_entero(cifras.no_encontrado.unidades)} por "
            f"{formato_cop(cifras.no_encontrado.valor)}",
            f["gris"],
        )
        cabecera(hoja, primera - 1, [c for c, _ in COLUMNAS_DETALLE], 8)
        fila = primera
        for a in activos:
            movido = a.encontrada is not None and a.encontrada != a.ubicacion
            hoja.write_string(fila, 0, a.codigo, f["codigo"])
            hoja.write_string(fila, 1, a.nombre, f["texto"])
            texto(hoja, fila, 2, a.marca, f["texto"])
            texto(hoja, fila, 3, a.serial, f["texto"])
            hoja.write_string(fila, 4, a.ubicacion, f["texto"])
            texto(hoja, fila, 5, a.encontrada, f["movido" if movido else "texto"])
            texto(hoja, fila, 6, a.estado, f["danado" if a.estado == "Dañado" else "texto"])
            hoja.write_string(
                fila, 7, a.resultado, f["encontrado" if a.encontrado else "no_encontrado"]
            )
            hoja.write_number(fila, 8, a.precio, f["cop"])
            fila += 1
        hoja.autofilter(primera - 1, 0, fila - 1, 8)
        hoja.freeze_panes(primera, 2)
        hoja.write_string(fila, 1, f"Total {cifras.etiqueta}", f["total"])
        for col in (0, 2, 3, 4, 5, 6):
            hoja.write_blank(fila, col, None, f["total"])
        hoja.write_string(fila, 7, _activos(cifras.registrado.unidades), f["total"])
        hoja.write_number(fila, 8, cifras.registrado.valor, f["total_cop"])
        hoja.write_string(
            fila + 2,
            1,
            "En cursiva: se encontró en otra ubicación. Usa los filtros del encabezado para "
            "ver solo lo no encontrado o una ubicación.",
            f["rotulo"],
        )

    # --- No encontrados
    hoja = libro.add_worksheet(HOJA_NO_ENCONTRADOS)
    encabezado(hoja, FILA_TABLA - 1)
    for col, ancho in enumerate((13, 34, 22, 32, 16, 18)):
        hoja.set_column(col, col, ancho)
    cabecera(
        hoja,
        FILA_TABLA - 1,
        ("Código", "Activo", "Categoría", "Ubicación esperada", "Nota al cierre", "Precio (COP)"),
        5,
    )
    fila = FILA_TABLA
    for n in doc.no_encontrados:
        hoja.write_string(fila, 0, n.codigo, f["codigo"])
        hoja.write_string(fila, 1, n.nombre, f["texto"])
        hoja.write_string(fila, 2, n.categoria, f["texto"])
        hoja.write_string(fila, 3, n.ubicacion, f["texto"])
        texto(hoja, fila, 4, "En reparación" if n.en_reparacion else None, f["texto"])
        hoja.write_number(fila, 5, n.precio, f["cop"])
        fila += 1
    if doc.no_encontrados:
        hoja.autofilter(FILA_TABLA - 1, 0, fila - 1, 5)
    hoja.freeze_panes(FILA_TABLA, 0)
    hoja.write_string(fila, 0, _cuantos_no_encontrados(len(doc.no_encontrados)), f["total"])
    for col in range(1, 5):
        hoja.write_blank(fila, col, None, f["total"])
    hoja.write_number(fila, 5, t.no_encontrado.valor, f["total_cop"])

    libro.close()
    return salida.getvalue()


def _cabecera_impresion(texto: str) -> str:
    """Texto seguro para el encabezado de impresión de Excel (``&`` es un código)."""
    return texto.replace("&", "&&")[:80]


def _tamano_png(datos: bytes) -> tuple[int, int]:
    """Ancho y alto de un PNG (los logos se guardan siempre en PNG, spec 013)."""
    if datos[:8] == b"\x89PNG\r\n\x1a\n" and len(datos) >= 24:
        return int.from_bytes(datos[16:20], "big"), int.from_bytes(datos[20:24], "big")
    return 0, 0


def _activos(n: int) -> str:
    return f"{formato_entero(n)} {'activo' if n == 1 else 'activos'}"


# --- PDF (T3; Q3: Carta horizontal) --------------------------------------------------------

PDF = "application/pdf"


def _latin(texto: str) -> str:
    """Las fuentes estándar del PDF (Helvetica, WinAnsi) no dibujan otros alfabetos: «?»."""
    return "".join(c if _cabe_en_winansi(c) else "?" for c in texto)


def _cabe_en_winansi(caracter: str) -> bool:
    try:
        caracter.encode("cp1252")
    except UnicodeEncodeError:
        return False
    return True


def a_pdf(doc: Documento) -> bytes:
    """Informe en Carta horizontal: metadatos, tres cifras, desglose y no encontrados."""
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import (
        KeepTogether,
        LongTable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    tinta, gris, linea, fondo = (
        colors.HexColor("#18181B"),
        colors.HexColor("#52525B"),
        colors.HexColor("#D4D4D8"),
        colors.HexColor("#F4F4F5"),
    )
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9, leading=11, textColor=tinta)
    estilos = {
        "titulo": ParagraphStyle(
            "titulo", parent=base, fontName="Helvetica-Bold", fontSize=16, leading=20
        ),
        "meta": ParagraphStyle("meta", parent=base, textColor=gris),
        "seccion": ParagraphStyle(
            "seccion",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "celda": base,
        "nota": ParagraphStyle("nota", parent=base, fontSize=8, leading=10, textColor=gris),
    }

    def p(texto: str, estilo: str = "celda") -> Paragraph:
        return Paragraph(escape(_latin(texto)), estilos[estilo])

    def tabla(filas: list[list], anchos: list[float], numericas: range, total: bool) -> LongTable:
        t = LongTable(filas, colWidths=anchos, repeatRows=1, hAlign="LEFT")
        estilo = [
            ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
            ("BACKGROUND", (0, 0), (-1, 0), fondo),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, linea),
            ("LINEBELOW", (0, 1), (-1, -1), 0.3, linea),
            ("ALIGN", (numericas.start, 0), (numericas.stop - 1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        if total:
            estilo += [
                ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 8.5),
                ("BACKGROUND", (0, -1), (-1, -1), fondo),
                ("LINEABOVE", (0, -1), (-1, -1), 0.8, tinta),
            ]
        t.setStyle(TableStyle(estilo))
        return t

    def desglose(filas: tuple[Fila, ...], rotulo: str) -> LongTable:
        cuerpo: list[list] = [[rotulo, *ENCABEZADO_DESGLOSE]]
        for f in (*filas, doc.totales):
            cuerpo.append(
                [
                    _latin(f.etiqueta) if f is doc.totales else p(f.etiqueta),
                    formato_cop(f.encontrado.valor),
                    formato_entero(f.encontrado.unidades),
                    formato_cop(f.no_encontrado.valor),
                    formato_entero(f.no_encontrado.unidades),
                    formato_cop(f.registrado.valor),
                    formato_entero(f.registrado.unidades),
                    f.porcentaje,
                ]
            )
        return tabla(
            cuerpo,
            [62 * mm, 32 * mm, 12 * mm, 32 * mm, 12 * mm, 34 * mm, 12 * mm, 22 * mm],
            range(1, 8),
            True,
        )

    t = doc.totales
    cifras = Table(
        [
            ["Encontrado", "No encontrado", "Total registrado"],
            [formato_cop(c.valor) for c in (t.encontrado, t.no_encontrado, t.registrado)],
            [_unidades(c.unidades) for c in (t.encontrado, t.no_encontrado, t.registrado)],
        ],
        colWidths=[72 * mm] * 3,
        hAlign="LEFT",
    )
    cifras.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                ("TEXTCOLOR", (0, 0), (0, 0), colors.HexColor("#15803D")),
                ("TEXTCOLOR", (1, 0), (1, 0), colors.HexColor("#B91C1C")),
                ("TEXTCOLOR", (2, 0), (2, 0), gris),
                ("FONT", (0, 1), (-1, 1), "Helvetica-Bold", 15),
                ("FONT", (0, 2), (-1, 2), "Helvetica", 8.5),
                ("TEXTCOLOR", (0, 2), (-1, 2), gris),
                ("BOX", (0, 0), (-1, -1), 0.6, linea),
                ("LINEBEFORE", (1, 0), (-1, -1), 0.6, linea),
                ("BACKGROUND", (0, 0), (-1, -1), fondo),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )

    lista: list[list] = [
        ["Código", "Activo", "Categoría", "Ubicación esperada", "Nota al cierre", "Precio"]
    ]
    for n in doc.no_encontrados:
        lista.append(
            [
                p(n.codigo),
                p(n.nombre),
                p(n.categoria),
                p(n.ubicacion),
                "En reparación" if n.en_reparacion else "",
                formato_cop(n.precio),
            ]
        )
    lista.append(
        [
            _cuantos_no_encontrados(len(doc.no_encontrados)),
            "",
            "",
            "",
            "",
            formato_cop(t.no_encontrado.valor),
        ]
    )
    tabla_lista = tabla(
        lista, [30 * mm, 66 * mm, 40 * mm, 56 * mm, 24 * mm, 32 * mm], range(5, 6), True
    )
    tabla_lista.setStyle(TableStyle([("SPAN", (0, -1), (4, -1))]))

    meta = (
        f"Fecha de corte <b>{escape(doc.corte)}</b> · Cerrada <b>{escape(doc.cerrada_en)}</b> · "
        f"Por <b>{escape(_latin(doc.cerrada_por))}</b> · Valores en COP · <b>Informe congelado</b>"
    )
    historia = [
        p(f"Informe · {doc.sesion}", "titulo"),
        Spacer(0, 2 * mm),
        Paragraph(meta, estilos["meta"]),
        Spacer(0, 5 * mm),
        cifras,
        Spacer(0, 2 * mm),
        p(f"{t.porcentaje} de las unidades encontradas.", "meta"),
        KeepTogether(
            [p("Por categoría (al cierre)", "seccion"), desglose(doc.por_categoria, "Categoría")]
        ),
        KeepTogether(
            [p("Por ubicación (al cierre)", "seccion"), desglose(doc.por_ubicacion, "Ubicación")]
        ),
        p("No encontrados (lista congelada al cierre)", "seccion"),
        tabla_lista,
        Spacer(0, 4 * mm),
        p(NOTA, "nota"),
    ]

    pie = _latin(f"Informe congelado al cierre · {doc.sesion}")

    class ConPaginas(rl_canvas.Canvas):
        """Pie con «página N de M»: guarda las páginas y las numera al final."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._paginas: list[dict] = []

        def showPage(self):  # noqa: N802 - API de reportlab
            self._paginas.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._paginas)
            for estado in self._paginas:
                self.__dict__.update(estado)
                self.setFont("Helvetica", 7.5)
                self.setFillColor(gris)
                self.drawString(15 * mm, 9 * mm, pie)
                self.drawRightString(
                    self._pagesize[0] - 15 * mm, 9 * mm, f"Página {self._pageNumber} de {total}"
                )
                super().showPage()
            super().save()

    salida = io.BytesIO()
    plantilla = SimpleDocTemplate(
        salida,
        pagesize=landscape(letter),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=16 * mm,
        title=_latin(f"Informe · {doc.sesion}"),
        author="AssetControl",
        subject="Informe congelado",
    )
    plantilla.build(historia, canvasmaker=ConPaginas)
    return salida.getvalue()


def _unidades(n: int) -> str:
    return f"{formato_entero(n)} {'unidad' if n == 1 else 'unidades'}"
