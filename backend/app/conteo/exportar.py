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

from app.conteo import exportar_estilo as est

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
    # Spec 015 (T5): fechas reales para las celdas de fecha del Excel (hora de Colombia,
    # sin zona: Excel no la guarda).
    fecha_corte: date | None = None
    momento_cierre: datetime | None = None

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


def _decimas_de_porcentaje(encontradas: int, registradas: int) -> int:
    """Décimas de punto porcentual (``1/3`` → ``333``), redondeo a la mitad hacia arriba."""
    if registradas == 0:
        return 0
    return int(
        (Decimal(encontradas) * 1000 / Decimal(registradas)).quantize(
            Decimal(1), rounding=ROUND_HALF_UP
        )
    )


def porcentaje(encontradas: int, registradas: int) -> str:
    """Proporción de unidades con un decimal, como ``porcentaje`` y ``toLocaleString('es-CO')``."""
    entero, decima = divmod(_decimas_de_porcentaje(encontradas, registradas), 10)
    return f"{formato_entero(entero)} %" if decima == 0 else f"{formato_entero(entero)},{decima} %"


def fraccion_encontrada(encontradas: int, registradas: int) -> Decimal:
    """La misma cifra que ``porcentaje`` como fracción exacta (``0.333``), para el formato
    de porcentaje del Excel (spec 015, T5). Sale de las unidades congeladas; no suma."""
    return Decimal(_decimas_de_porcentaje(encontradas, registradas)) / 1000


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
        fecha_corte=date.fromisoformat(sesion["fecha_corte"]),
        momento_cierre=(
            datetime.fromisoformat(sesion["cerrada_en"])
            .astimezone(HORA_COLOMBIA)
            .replace(tzinfo=None)
            if sesion.get("cerrada_en")
            else None
        ),
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


# --- Excel (009 T2 / 013 T4 / 015 T5: dinero como número COP, sin fórmulas) ---------------

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FORMATO_COP = '"$" #,##0.00'
FORMATO_PORCENTAJE = "0.0 %"
FORMATO_FECHA = "dd/mm/yyyy"
FORMATO_FECHA_HORA = "dd/mm/yyyy hh:mm"
NOTA = (
    "Cifras calculadas por el servidor una sola vez, al cerrar la sesión. Lo encontrado usa "
    "el precio, la categoría y la ubicación del momento de contar; lo no encontrado, los del "
    "cierre. Los cambios posteriores no alteran este informe."
)
# El PDF conserva su cabecera corta (no cambia en la 015); el Excel nombra cada columna.
ENCABEZADO_DESGLOSE = (
    "Encontrado",
    "u.",
    "No encontrado",
    "u.",
    "Total registrado",
    "u.",
    "% encontrado",
)
ENCABEZADO_DESGLOSE_EXCEL = (
    "Valor encontrado",
    "Unid. encontradas",
    "Valor no encontrado",
    "Unid. no encontradas",
    "Valor registrado",
    "Unid. registradas",
    "% encontrado",
)

# Colores de la marca «Grafito y Cobalto» (docs/08), sobrios; los de estado solo marcan.
GRAFITO = "#18181B"
COBALTO = "#2B50E0"
GRIS = "#71717A"
LINEA = "#E4E4E7"
FONDO = "#F4F4F5"
FONDO_TOTAL = "#EEF2FF"
BARRA = "#C7D2FE"  # cobalto claro: la cifra se sigue leyendo sobre la barra
VERDE = "#15803D"
ROJO = "#B91C1C"

HOJA_RESUMEN = "Resumen"
HOJA_TODOS = "Todos los activos"
HOJA_NO_ENCONTRADOS = "No encontrados"
HOJA_POR_UBICACION = "Por ubicación"  # spec 019 (Q6, B16): hojas de la plantilla B
HOJA_POR_CATEGORIA = "Por categoría"
TABLA_ACTIVOS = "Activos"
COLUMNAS_DETALLE = (
    "Código",
    "Activo",
    "Marca",
    "Serial",
    "Ubicación esperada",
    "Encontrado en",
    "Estado físico",
    "Resultado",
    "Precio (COP)",
)
COLUMNAS_PLANA = (
    "Código",
    "Activo",
    "Categoría",
    "Marca",
    "Serial",
    "Ubicación esperada",
    "Encontrado en",
    "Estado físico",
    "Resultado",
    "Precio (COP)",
)
COLUMNAS_NO_ENCONTRADOS = (
    "Código",
    "Activo",
    "Categoría",
    "Ubicación esperada",
    "Nota al cierre",
    "Precio (COP)",
)
SIN_DETALLE = (
    "Esta sesión se cerró antes de que AssetControl guardara el detalle por activo: el "
    "libro no trae la hoja «Todos los activos» ni una hoja por categoría."
)
EMPRESA_VIGENTE = (
    "Datos de la empresa vigentes: la sesión se cerró antes de guardarlos con el informe."
)
LEYENDA = "En cursiva y fondo ámbar: se encontró en otra ubicación."


def nombres_de_hoja(categorias: Sequence[str]) -> list[str]:
    """Nombres de hoja válidos y únicos para cada categoría (spec 013, R5).

    Excel no admite ``[]:*?/\\``, más de 31 caracteres, comillas simples al principio o
    al final, ni dos hojas con el mismo nombre (sin distinguir mayúsculas). Tampoco se
    usan «Resumen», «Todos los activos», «No encontrados», «Por ubicación» ni «Por
    categoría», que son las otras hojas (spec 019, B16), ni «History», que Excel reserva.
    Los 31 caracteres se miden en unidades UTF-16, como Excel (un emoji ocupa dos), sin
    partir un par sustituto.
    """
    reservados = (
        HOJA_RESUMEN,
        HOJA_TODOS,
        HOJA_NO_ENCONTRADOS,
        HOJA_POR_UBICACION,
        HOJA_POR_CATEGORIA,
        "History",
    )
    usados = {h.casefold() for h in reservados}
    nombres = []
    for categoria in categorias:
        limpio = re.sub(r"[\[\]:*?/\\]", " ", categoria)
        limpio = " ".join(limpio.split()).strip("'").strip() or "Categoría"
        base = _recortar_utf16(limpio, 31).rstrip().rstrip("'").rstrip() or "Categoría"
        nombre, n = base, 2
        while nombre.casefold() in usados:
            sufijo = f" ({n})"
            nombre = _recortar_utf16(base, 31 - len(sufijo)).rstrip() + sufijo
            n += 1
        usados.add(nombre.casefold())
        nombres.append(nombre)
    return nombres


def _unidades_utf16(texto: str) -> int:
    return len(texto.encode("utf-16-le")) // 2


def _recortar_utf16(texto: str, tope: int) -> str:
    """Prefijo de ``texto`` de a lo sumo ``tope`` unidades UTF-16 (nunca medio emoji)."""
    largo = 0
    for i, caracter in enumerate(texto):
        largo += _unidades_utf16(caracter)
        if largo > tope:
            return texto[:i]
    return texto


def a_excel(doc: Documento) -> bytes:
    """Libro v4 (spec 015, T5): «Resumen» tipo tablero, «Todos los activos» (tabla plana),
    una hoja por categoría y «No encontrados».

    Spec 019 (T4): las tres familias de hojas de lista replican la plantilla B con el estilo
    común (``exportar_estilo``): bloque de la empresa congelada, título y nota, Total sobre
    la cabecera, datos sin filas alternas, formato condicional de fila completa, columnas
    ocultas en «No encontrados», congelado, impresión de 1 página de ancho (Q12) y la tabla
    «Activos» y los filtros (Q8). El Resumen y el orden del libro son de T5.

    El texto va siempre con ``write_string`` (nunca fórmula) y el dinero con
    ``write_number`` desde el ``Decimal`` exacto (un ``float`` se rechaza). Las cifras y
    totales son los del informe congelado (``totales``, desglose y lista): aquí no se suma
    ni se recalcula nada.
    """
    import xlsxwriter  # Import local: solo quien exporta carga la librería.

    salida = io.BytesIO()
    libro = xlsxwriter.Workbook(
        salida,
        {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False},
    )
    libro.set_properties({"title": f"Informe · {doc.sesion}", "comments": "Informe congelado"})
    formatos: dict[tuple, Any] = {}

    def fmt(**kw):
        """Formato con la base común; uno por combinación (XlsxWriter no los deduplica)."""
        clave = tuple(sorted(kw.items()))
        if clave not in formatos:
            formatos[clave] = libro.add_format(
                {"font_name": "Calibri", "font_size": 10, "valign": "vcenter", **kw}
            )
        return formatos[clave]

    celda = {"bottom": 1, "bottom_color": LINEA}
    banda = {
        "bold": True,
        "bg_color": FONDO_TOTAL,
        "top": 2,
        "top_color": COBALTO,
        "bottom": 2,
        "bottom_color": COBALTO,
    }
    f = {
        "empresa": fmt(bold=True, font_size=15, font_color=GRAFITO),
        "gris": fmt(font_color=GRIS),
        "rotulo": fmt(font_color=GRIS, font_size=9),
        "antetitulo": fmt(bold=True, font_size=9, font_color=COBALTO),
        "sesion": fmt(bold=True, font_size=18, font_color=GRAFITO),
        "titulo": fmt(bold=True, font_size=12, font_color=COBALTO),
        "dato": fmt(bold=True, font_color=GRAFITO),
        "fecha": fmt(bold=True, font_color=GRAFITO, num_format=FORMATO_FECHA, align="left"),
        "fecha_hora": fmt(
            bold=True, font_color=GRAFITO, num_format=FORMATO_FECHA_HORA, align="left"
        ),
        "cabecera": fmt(
            bold=True,
            font_color="#FFFFFF",
            bg_color=GRAFITO,
            text_wrap=True,
            border=1,
            border_color=GRAFITO,
        ),
        "cabecera_num": fmt(
            bold=True,
            font_color="#FFFFFF",
            bg_color=GRAFITO,
            text_wrap=True,
            border=1,
            border_color=GRAFITO,
            align="right",
        ),
        # Columna numérica con filtro: la sangría deja ver el texto junto al botón.
        "cabecera_filtro_num": fmt(
            bold=True,
            font_color="#FFFFFF",
            bg_color=GRAFITO,
            text_wrap=True,
            border=1,
            border_color=GRAFITO,
            align="right",
            indent=2,
        ),
        "nota": fmt(italic=True, font_color=GRIS, text_wrap=True, valign="top"),
        "total": fmt(**banda),
        "total_cop": fmt(**banda, num_format=FORMATO_COP),
        "total_entero": fmt(**banda, num_format="#,##0"),
        "total_pct": fmt(**banda, num_format=FORMATO_PORCENTAJE),
        "total_derecha": fmt(**banda, align="right"),
    }

    def cuerpo(alterna: bool = False, **kw):
        """Celda de tabla: línea inferior suave y, si ``alterna``, fondo gris claro."""
        return fmt(**celda, **({"bg_color": FONDO} if alterna else {}), **kw)

    e = doc.empresa
    sesion = (
        f"Informe de inventario «{doc.sesion}» · corte {doc.corte} · "
        f"cerrada {doc.cerrada_en} por {doc.cerrada_por}"
    )
    estado = "Informe congelado al cierre · valores en COP"
    if e.vigente:
        estado += f" · {EMPRESA_VIGENTE}"

    def encabezado(hoja, filas_repetidas: int | None) -> None:
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
        if filas_repetidas is not None:
            hoja.repeat_rows(filas_repetidas, filas_repetidas)
        hoja.set_margins(left=0.4, right=0.4, top=0.6, bottom=0.6)
        # El espacio separa el tamaño (``&8``) del texto: «2026 …» no se lee como ``&82026``.
        hoja.set_header(
            f"&L&8 {_cabecera_impresion(e.nombre)}&R&8 {_cabecera_impresion(doc.sesion)}"
        )
        hoja.set_footer("&L&8Generado con AssetControl&RPágina &P de &N")

    def texto(hoja, fila: int, col: int, valor: str | None, formato_) -> None:
        """Texto siempre como texto (nunca fórmula); vacío como celda en blanco."""
        if valor:
            hoja.write_string(fila, col, valor, formato_)
        else:
            hoja.write_blank(fila, col, None, formato_)

    def cabecera(
        hoja, fila: int, columnas: Sequence[str], numericas: int, filtro: bool = False
    ) -> None:
        numerica = "cabecera_filtro_num" if filtro else "cabecera_num"
        for col, nombre in enumerate(columnas):
            hoja.write_string(fila, col, nombre, f[numerica if col >= numericas else "cabecera"])
        hoja.set_row(fila, 30)

    def tabla_desglose(hoja, fila: int, titulo: str, rotulo: str, filas: tuple[Fila, ...]) -> int:
        hoja.write_string(fila, 0, titulo, f["titulo"])
        cabecera(hoja, fila + 1, (rotulo, *ENCABEZADO_DESGLOSE_EXCEL), 1)
        fila += 2
        primera = fila
        for i, d in enumerate(filas):
            alterna = i % 2 == 1
            hoja.write_string(fila, 0, d.etiqueta, cuerpo(alterna))
            for j, cifra in enumerate((d.encontrado, d.no_encontrado, d.registrado)):
                hoja.write_number(
                    fila, 1 + 2 * j, cifra.valor, cuerpo(alterna, num_format=FORMATO_COP)
                )
                hoja.write_number(
                    fila, 2 + 2 * j, cifra.unidades, cuerpo(alterna, num_format="#,##0")
                )
            hoja.write_number(
                fila,
                7,
                fraccion_encontrada(d.encontrado.unidades, d.registrado.unidades),
                cuerpo(alterna, num_format=FORMATO_PORCENTAJE),
            )
            fila += 1
        if filas:
            # Barras de datos: solo visuales, sin fórmulas (mínimo y máximo automáticos).
            for col in (5, 7):
                hoja.conditional_format(
                    primera,
                    col,
                    fila - 1,
                    col,
                    {"type": "data_bar", "bar_color": BARRA, "bar_solid": True},
                )
        t = doc.totales
        hoja.write_string(fila, 0, t.etiqueta, f["total"])
        for j, cifra in enumerate((t.encontrado, t.no_encontrado, t.registrado)):
            hoja.write_number(fila, 1 + 2 * j, cifra.valor, f["total_cop"])
            hoja.write_number(fila, 2 + 2 * j, cifra.unidades, f["total_entero"])
        hoja.write_number(
            fila,
            7,
            fraccion_encontrada(t.encontrado.unidades, t.registrado.unidades),
            f["total_pct"],
        )
        return fila + 2

    t = doc.totales

    # --- Resumen (tablero)
    hoja = libro.add_worksheet(HOJA_RESUMEN)
    encabezado(hoja, None)
    hoja.center_horizontally()
    hoja.set_column(0, 0, 34)
    hoja.set_column(1, 6, 18)
    hoja.set_column(7, 7, 26)  # la tarjeta del % va sola en su columna
    hoja.write_string(5, 0, "INFORME DE INVENTARIO DE ACTIVOS", f["antetitulo"])
    hoja.write_string(6, 0, doc.sesion, f["sesion"])
    hoja.set_row(6, 28)
    for col, rotulo in enumerate(("Fecha de corte", "Cerrada", "Moneda", "Estado", "Cerró")):
        hoja.write_string(8, col, rotulo, f["rotulo"])
    if doc.fecha_corte is not None:
        hoja.write_datetime(
            9, 0, datetime.combine(doc.fecha_corte, datetime.min.time()), f["fecha"]
        )
    if doc.momento_cierre is not None:
        hoja.write_datetime(9, 1, doc.momento_cierre, f["fecha_hora"])
    hoja.write_string(9, 2, "COP", f["dato"])
    hoja.write_string(9, 3, "Informe congelado", f["dato"])
    hoja.merge_range(9, 4, 9, 7, "", f["dato"])
    texto(hoja, 9, 4, doc.cerrada_por, f["dato"])

    tarjeta = 11
    for col, ultima, rotulo, color, valor, num, debajo in (
        (1, 2, "Encontrado", VERDE, t.encontrado.valor, FORMATO_COP, t.encontrado.unidades),
        (3, 4, "No encontrado", ROJO, t.no_encontrado.valor, FORMATO_COP, t.no_encontrado.unidades),
        (5, 6, "Total registrado", COBALTO, t.registrado.valor, FORMATO_COP, t.registrado.unidades),
        (
            7,
            7,
            "% encontrado",
            GRAFITO,
            fraccion_encontrada(t.encontrado.unidades, t.registrado.unidades),
            FORMATO_PORCENTAJE,
            None,
        ),
    ):
        fondo = {
            "bg_color": FONDO,
            "left": 1,
            "left_color": LINEA,
            "right": 1,
            "right_color": LINEA,
        }
        f_rotulo = fmt(**fondo, bold=True, font_color=color, top=5, top_color=color)
        f_valor = fmt(**fondo, bold=True, font_size=16, font_color=GRAFITO, num_format=num)
        f_debajo = fmt(**fondo, font_color=GRIS, bottom=1, bottom_color=LINEA)
        unidades = "de las unidades registradas" if debajo is None else _unidades(debajo)
        if ultima > col:
            hoja.merge_range(tarjeta, col, tarjeta, ultima, "", f_rotulo)
            hoja.merge_range(tarjeta + 1, col, tarjeta + 1, ultima, "", f_valor)
            hoja.merge_range(tarjeta + 2, col, tarjeta + 2, ultima, "", f_debajo)
        hoja.write_string(tarjeta, col, rotulo, f_rotulo)
        hoja.write_number(tarjeta + 1, col, valor, f_valor)
        hoja.write_string(tarjeta + 2, col, unidades, f_debajo)
    hoja.write_string(tarjeta, 0, "Cifras del cierre", f["titulo"])
    hoja.set_row(tarjeta, 20)
    hoja.set_row(tarjeta + 1, 30)

    fila = tabla_desglose(
        hoja, tarjeta + 4, "Por categoría", "Categoría (al cierre)", doc.por_categoria
    )
    fila = tabla_desglose(hoja, fila, "Por ubicación", "Ubicación (al cierre)", doc.por_ubicacion)
    hoja.merge_range(fila, 0, fila + 1, 7, "", f["nota"])
    hoja.write_string(fila, 0, NOTA, f["nota"])
    if not doc.detalle_disponible:
        hoja.merge_range(fila + 2, 0, fila + 3, 7, "", f["nota"])
        hoja.write_string(fila + 2, 0, SIN_DETALLE, f["nota"])

    # --- Hojas de lista (spec 019, T4): plantilla B, desde el estilo común
    estilos = est.Estilos(libro)

    # Todos los activos (tabla plana del universo U congelado)
    if doc.detalle:
        hoja = _hoja_de_lista(
            libro,
            estilos,
            HOJA_TODOS,
            est.PLANTILLAS["todos"],
            doc,
            titulo="Todos los activos del cierre",
            nota=f"{_resumen_de_lista(t)} · tabla «{TABLA_ACTIVOS}», lista para filtrar o "
            f"hacer una tabla dinámica. {LEYENDA}",
            total=(
                "Total",
                HOJA_TODOS,
                *(None,) * 6,
                _activos(t.registrado.unidades),
                t.registrado.valor,
            ),
            cabecera=COLUMNAS_PLANA,
            filas=[_valores_de_activo(a, con_categoria=True) for a in doc.detalle],
        )
        # Q8: se conserva la tabla «Activos» (y su filtro), sin nombre de estilo para no
        # alterar la fuente, el relleno ni los bordes de la plantilla.
        hoja.add_table(
            est.PLANTILLAS["todos"].fila_cabecera,
            0,
            est.PLANTILLAS["todos"].fila_cabecera + len(doc.detalle),
            len(COLUMNAS_PLANA) - 1,
            {
                "name": TABLA_ACTIVOS,
                "style": None,
                "columns": [
                    {"header": c, "header_format": estilos("cabecera")} for c in COLUMNAS_PLANA
                ],
            },
        )

    # Una hoja por categoría (R5)
    grupos = doc.categorias_con_detalle()
    plantilla = est.PLANTILLAS["categoria"]
    for nombre, (cifras, activos) in zip(
        nombres_de_hoja([g[0].etiqueta for g in grupos]), grupos, strict=True
    ):
        hoja = _hoja_de_lista(
            libro,
            estilos,
            nombre,
            plantilla,
            doc,
            titulo=f"Categoría: {cifras.etiqueta}",
            nota=f"{_resumen_de_lista(cifras)} · {LEYENDA}",
            total=(
                "Total",
                cifras.etiqueta,
                *(None,) * 5,
                _activos(cifras.registrado.unidades),
                cifras.registrado.valor,
                None,
            ),
            cabecera=COLUMNAS_DETALLE,
            filas=[_valores_de_activo(a, con_categoria=False) for a in activos],
        )
        hoja.autofilter(
            plantilla.fila_cabecera,
            0,
            plantilla.fila_cabecera + len(activos),
            len(COLUMNAS_DETALLE) - 1,
        )

    # No encontrados
    plantilla = est.PLANTILLAS["no_encontrados"]
    hoja = _hoja_de_lista(
        libro,
        estilos,
        HOJA_NO_ENCONTRADOS,
        plantilla,
        doc,
        titulo="No encontrados (lista congelada al cierre)",
        nota=f"{_cuantos_no_encontrados(len(doc.no_encontrados))} por "
        f"{formato_cop(t.no_encontrado.valor)}.",
        total=(
            "Total",
            _cuantos_no_encontrados(t.no_encontrado.unidades),
            None,
            None,
            None,
            t.no_encontrado.valor,
            *(None,) * 4,
        ),
        cabecera=(*COLUMNAS_NO_ENCONTRADOS, *(None,) * 4),
        filas=[
            (
                n.codigo,
                n.nombre,
                n.categoria,
                n.ubicacion,
                "En reparación" if n.en_reparacion else None,
                n.precio,
            )
            for n in doc.no_encontrados
        ],
    )
    if doc.no_encontrados:
        hoja.autofilter(
            plantilla.fila_cabecera,
            0,
            plantilla.fila_cabecera + len(doc.no_encontrados),
            len(COLUMNAS_NO_ENCONTRADOS) - 1,
        )

    libro.close()
    return salida.getvalue()


def _resumen_de_lista(cifras: Fila) -> str:
    """``N activos · encontrados n (pct) por $ … · no encontrados n por $ …`` (congeladas)."""
    return (
        f"{_activos(cifras.registrado.unidades)} · encontrados "
        f"{formato_entero(cifras.encontrado.unidades)} ({cifras.porcentaje}) por "
        f"{formato_cop(cifras.encontrado.valor)} · no encontrados "
        f"{formato_entero(cifras.no_encontrado.unidades)} por "
        f"{formato_cop(cifras.no_encontrado.valor)}"
    )


def _o_vacia(texto: str | None) -> str | None:
    """Un texto vacío es una celda vacía (con el estilo «vacía» de la plantilla)."""
    return texto if texto else None


def _valores_de_activo(a: Detalle, con_categoria: bool) -> tuple:
    """Una fila del detalle congelado, en el orden de las columnas (sin cambios)."""
    return (
        a.codigo,
        a.nombre,
        *((a.categoria,) if con_categoria else ()),
        _o_vacia(a.marca),
        _o_vacia(a.serial),
        _o_vacia(a.ubicacion),
        _o_vacia(a.encontrada),
        _o_vacia(a.estado),
        a.resultado,
        a.precio,
    )


def _fecha_de_corte(doc: Documento) -> date:
    if doc.fecha_corte is not None:
        return doc.fecha_corte
    return datetime.strptime(doc.corte, "%d/%m/%Y").date()


def _hoja_de_lista(
    libro: Any,
    estilos: Any,
    nombre: str,
    plantilla: Any,
    doc: Documento,
    *,
    titulo: str,
    nota: str,
    total: Sequence[Any],
    cabecera: Sequence[str | None],
    filas: Sequence[Sequence[Any]],
) -> Any:
    """Hoja de lista de la plantilla B (spec 019, T4): bloque de la empresa congelada
    (filas 1–5), título (6), nota combinada (7), Total congelado sobre la cabecera (8),
    cabecera (9) y datos desde la fila 10 con el estilo de la fila de datos de la plantilla
    (sin filas alternas; la celda sin valor, con el estilo «vacía»); formato condicional de
    fila completa cuando la plantilla lo trae, extendido hasta la última fila (req. 5)."""
    hoja = libro.add_worksheet(nombre)
    cab = plantilla.fila_cabecera
    ultima = cab + len(filas)
    est.preparar_hoja(hoja, plantilla, ultima)
    est.dibujar_bloque(hoja, estilos, plantilla, doc.empresa, _fecha_de_corte(doc))
    primero, *resto = plantilla.estilos_titulo_lista
    est.escribir_fila(hoja, estilos, cab - 3, [(titulo, primero), *((None, s) for s in resto)])
    hoja.merge_range(plantilla.combinar_nota, None)  # sin formato: solo A7 lleva estilo
    hoja.write_string(cab - 2, 0, nota, estilos("nota"))
    est.escribir_fila(
        hoja,
        estilos,
        plantilla.fila_total,
        list(zip(total, plantilla.estilos_total, strict=True)),
        plantilla.alto_total,
    )
    est.escribir_fila(
        hoja, estilos, cab, list(zip(cabecera, plantilla.estilos_cabecera, strict=True))
    )
    for fila, valores in enumerate(filas, start=plantilla.fila_datos):
        est.escribir_fila(
            hoja,
            estilos,
            fila,
            [
                (v, plantilla.estilo_vacia if v is None else s)
                for v, s in zip(valores, plantilla.estilos_datos, strict=True)
            ],
            plantilla.alto_datos,
        )
    if plantilla.formula_otra_ubicacion:
        hoja.conditional_format(
            plantilla.fila_datos,
            0,
            max(est.FILA_FIN_FORMATO_CONDICIONAL, ultima),
            plantilla.ultima_columna_datos,
            {
                "type": "formula",
                "criteria": "=" + plantilla.formula_otra_ubicacion,
                "format": libro.add_format(dict(est.DXF_OTRA_UBICACION)),
            },
        )
    return hoja


CABECERA_MAXIMA = 80  # unidades UTF-16 ya escapadas, por lado (Excel admite 255 en total)


def _cabecera_impresion(texto: str) -> str:
    """Texto seguro para el encabezado de impresión de Excel (``&`` es un código).

    Se quita el ``&`` de ``&G`` y ``&[`` (imagen: XlsxWriter descarta el encabezado y avisa
    con el texto) y de ``&"`` (fuente); los demás ``&`` se duplican. El tope se aplica al
    escapar, carácter a carácter, para no partir un ``&&`` ni un emoji.
    """
    previo = None
    while previo != texto:
        previo, texto = texto, re.sub(r'&(?=[G"\[])', "", texto)
    salida, largo = [], 0
    for caracter in texto:
        escapado = "&&" if caracter == "&" else caracter
        largo += _unidades_utf16(escapado)
        if largo > CABECERA_MAXIMA:
            break
        salida.append(escapado)
    return "".join(salida)


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
    """Informe en Carta horizontal, estilo A «Corporativo» (spec 013, R6; sin firmas, G1).

    Encabezado con el logo y los datos de la empresa congelados, fila de corte y cierre,
    tarjetas de las tres cifras, desglose por categoría y por ubicación, no encontrados y
    la nota de cómo se calculó. Pie con empresa, sesión y «Página X de Y»; desde la página
    2, un encabezado reducido.
    """
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import (
        Image,
        KeepTogether,
        LongTable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    tinta, gris, linea, fondo, acento = (
        colors.HexColor("#18181B"),
        colors.HexColor("#52525B"),
        colors.HexColor("#E4E4E7"),
        colors.HexColor("#F4F4F5"),
        colors.HexColor("#0E7490"),
    )
    verde, rojo = colors.HexColor("#15803D"), colors.HexColor("#B91C1C")
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9, leading=11, textColor=tinta)
    estilos = {
        "empresa": ParagraphStyle(
            "empresa", parent=base, fontName="Helvetica-Bold", fontSize=13, leading=16
        ),
        "contacto": ParagraphStyle(
            "contacto", parent=base, fontSize=8.5, leading=11.5, textColor=gris
        ),
        "antetitulo": ParagraphStyle(
            "antetitulo", parent=base, fontSize=8, leading=10, textColor=gris, alignment=2
        ),
        "titulo": ParagraphStyle(
            "titulo", parent=base, fontName="Helvetica-Bold", fontSize=15, leading=18, alignment=2
        ),
        "rotulo": ParagraphStyle("rotulo", parent=base, fontSize=8, leading=10, textColor=gris),
        "dato": ParagraphStyle("dato", parent=base, fontName="Helvetica-Bold"),
        "meta": ParagraphStyle("meta", parent=base, textColor=gris),
        "seccion": ParagraphStyle(
            "seccion",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            spaceBefore=10,
            spaceAfter=5,
        ),
        "celda": base,
        "nota": ParagraphStyle("nota", parent=base, fontSize=8, leading=10, textColor=gris),
        "aviso": ParagraphStyle("aviso", parent=base, fontSize=8.5, leading=11, textColor=rojo),
    }

    def p(texto: str, estilo: str = "celda") -> Paragraph:
        return Paragraph(escape(_latin(texto)), estilos[estilo])

    def tabla(filas: list[list], anchos: list[float], numericas: range, total: bool) -> LongTable:
        t = LongTable(filas, colWidths=anchos, repeatRows=1, hAlign="LEFT")
        estilo = [
            ("FONT", (0, 0), (-1, -1), "Helvetica", 8.5),
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
            ("TEXTCOLOR", (0, 0), (-1, 0), gris),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, acento),
            ("LINEBELOW", (0, 1), (-1, -1), 0.4, linea),
            ("ALIGN", (numericas.start, 0), (numericas.stop - 1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        ultima = len(filas) - (1 if total else 0)
        for i in range(2, ultima, 2):
            estilo.append(("BACKGROUND", (0, i), (-1, i), fondo))
        if total:
            estilo += [
                ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 8.5),
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
            [66 * mm, 32 * mm, 12 * mm, 32 * mm, 12 * mm, 34 * mm, 12 * mm, 24 * mm],
            range(1, 8),
            True,
        )

    e = doc.empresa
    t = doc.totales

    # Encabezado: logo, empresa y título.
    datos_empresa = [p(e.nombre, "empresa")]
    if e.contacto:
        datos_empresa.append(p(e.contacto, "contacto"))
    titulo = [p("INFORME DE INVENTARIO DE ACTIVOS", "antetitulo"), p(doc.sesion, "titulo")]
    celdas: list = [datos_empresa, titulo]
    anchos = [140 * mm, 110 * mm]
    if e.logo:
        lector = ImageReader(io.BytesIO(e.logo))
        ancho_px, alto_px = lector.getSize()
        alto = 18 * mm
        ancho = min(40 * mm, alto * ancho_px / alto_px)
        alto = ancho * alto_px / ancho_px
        celdas.insert(0, Image(io.BytesIO(e.logo), width=ancho, height=alto))
        anchos = [ancho + 5 * mm, 140 * mm - ancho - 5 * mm, 110 * mm]
    cabecera = Table([celdas], colWidths=anchos, hAlign="LEFT")
    cabecera.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LINEBELOW", (0, 0), (-1, -1), 2, acento),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )

    meta = Table(
        [
            [p(r, "rotulo") for r in ("Fecha de corte", "Cerrada", "Cerró", "Moneda", "Estado")],
            [
                p(doc.corte, "dato"),
                p(doc.cerrada_en, "dato"),
                p(doc.cerrada_por, "dato"),
                p("COP", "dato"),
                p("Informe congelado", "dato"),
            ],
        ],
        colWidths=[40 * mm, 52 * mm, 62 * mm, 30 * mm, 46 * mm],
        hAlign="LEFT",
    )
    meta.setStyle(
        TableStyle([("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)])
    )

    def tarjeta(rotulo: str, cifra: Cifra, detalle: str, color) -> Table:
        tarjeta = Table(
            [
                [Paragraph(f"<b>{rotulo}</b>", ParagraphStyle("t", parent=base, textColor=color))],
                [
                    Paragraph(
                        f"<b>{formato_cop(cifra.valor)}</b>",
                        ParagraphStyle("v", parent=base, fontSize=16, leading=20),
                    )
                ],
                [p(detalle, "nota")],
            ],
            colWidths=[79 * mm],
        )
        tarjeta.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.6, linea),
                    ("LINEABOVE", (0, 0), (-1, 0), 3, color),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (0, 0), 6),
                    ("BOTTOMPADDING", (0, -1), (-1, -1), 6),
                ]
            )
        )
        return tarjeta

    tarjetas = Table(
        [
            [
                tarjeta("Encontrado", t.encontrado, _unidades(t.encontrado.unidades), verde),
                tarjeta(
                    "No encontrado", t.no_encontrado, _unidades(t.no_encontrado.unidades), rojo
                ),
                tarjeta(
                    "Total registrado",
                    t.registrado,
                    f"{_unidades(t.registrado.unidades)} · {t.porcentaje} encontradas",
                    acento,
                ),
            ]
        ],
        colWidths=[83 * mm] * 3,
        hAlign="LEFT",
    )
    tarjetas.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0)]))

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
        lista, [30 * mm, 70 * mm, 40 * mm, 60 * mm, 24 * mm, 32 * mm], range(5, 6), True
    )
    tabla_lista.setStyle(TableStyle([("SPAN", (0, -1), (4, -1))]))

    historia: list = [cabecera, Spacer(0, 3 * mm), meta]
    if e.vigente:
        historia += [Spacer(0, 2 * mm), p(EMPRESA_VIGENTE, "aviso")]
    historia += [
        Spacer(0, 4 * mm),
        tarjetas,
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

    pie = _latin(f"{e.nombre} · {doc.sesion} · Informe congelado al cierre ({doc.cerrada_en})")
    reducido_izquierda = _latin(e.nombre)
    reducido_derecha = _latin(f"Informe de inventario · {doc.sesion} · corte {doc.corte}")

    class ConPaginas(rl_canvas.Canvas):
        """Pie con «Página N de M» y encabezado reducido desde la página 2."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._paginas: list[dict] = []

        def showPage(self):  # noqa: N802 - API de reportlab
            self._paginas.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._paginas)
            ancho, alto = self._pagesize
            for estado in self._paginas:
                self.__dict__.update(estado)
                self.setStrokeColor(linea)
                self.line(15 * mm, 12 * mm, ancho - 15 * mm, 12 * mm)
                self.setFont("Helvetica", 7.5)
                self.setFillColor(gris)
                self.drawString(15 * mm, 8 * mm, pie)
                self.drawRightString(
                    ancho - 15 * mm, 8 * mm, f"AssetControl · Página {self._pageNumber} de {total}"
                )
                if self._pageNumber > 1:
                    self.setFont("Helvetica-Bold", 8)
                    self.setFillColor(tinta)
                    self.drawString(15 * mm, alto - 10 * mm, reducido_izquierda)
                    self.setFont("Helvetica", 8)
                    self.setFillColor(gris)
                    self.drawRightString(ancho - 15 * mm, alto - 10 * mm, reducido_derecha)
                super().showPage()
            super().save()

    salida = io.BytesIO()
    plantilla = SimpleDocTemplate(
        salida,
        pagesize=landscape(letter),
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=15 * mm,
        bottomMargin=17 * mm,
        title=_latin(f"Informe · {doc.sesion}"),
        author=_latin(e.nombre) or "AssetControl",
        subject="Informe congelado",
    )
    plantilla.build(historia, canvasmaker=ConPaginas)
    return salida.getvalue()


def _unidades(n: int) -> str:
    return f"{formato_entero(n)} {'unidad' if n == 1 else 'unidades'}"
