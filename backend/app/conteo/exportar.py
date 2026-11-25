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
# Resumen, opción C (decisión del humano 2026-11-24), en índices de xlsxwriter (0 = fila 1):
# tarjetas 2 × 2 en A:B y C:D y el panel de la sesión en F:J (filas 7–12); la nota y los
# avisos, a todo el ancho desde la fila 14.
FILA_TARJETAS = 6
FILA_NOTA_RESUMEN = 13
COLUMNA_PANEL = 5  # F
ULTIMA_COLUMNA_RESUMEN = 9  # J
CARACTERES_POR_LINEA_NOTA = 230  # Arial 9 en A:J (≈ 1 250 px)


def nombres_de_hoja(categorias: Sequence[str]) -> list[str]:
    """Nombres de hoja válidos y únicos para cada categoría (spec 013, R5).

    Excel no admite ``[]:*?/\\``, más de 31 caracteres, comillas simples al principio o
    al final, ni dos hojas con el mismo nombre (sin distinguir mayúsculas). Tampoco se
    usan «Resumen», «Todos los activos», «No encontrados», «Por ubicación» ni «Por
    categoría», que son las otras hojas (spec 019, B16), ni «History», que Excel reserva.
    Los caracteres de control se eliminan (se cambian por espacio, como los prohibidos).
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
        # Tampoco caracteres de control (\x00–\x1f): romperían el XML del libro (spec 019, T5).
        limpio = re.sub(r"[\[\]:*?/\\\x00-\x1f]", " ", categoria)
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
    """Libro del informe congelado con el diseño de la plantilla B (spec 019).

    Orden de la plantilla (Q6): «Todos los activos», «Por ubicación», «No encontrados», una
    hoja por categoría, «Por categoría» y «Resumen»; sin detalle (sesión anterior a la 013)
    no hay «Todos los activos» ni hojas por categoría. Todas las hojas llevan el bloque de la
    empresa congelada (filas 1–5) y el estilo común (``exportar_estilo``). El libro abre en
    la primera hoja, celda A1, sin desplazamiento (Q11).

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
    # Fila 26: título del libro y autor neutro («AssetControl»), nada del equipo.
    libro.set_properties(est.propiedades(f"Informe · {doc.sesion}"))
    estilos = est.Estilos(libro)
    t = doc.totales

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

    # Por ubicación (desglose congelado del cierre)
    _hoja_de_desglose(
        libro,
        estilos,
        HOJA_POR_UBICACION,
        est.PLANTILLAS["por_ubicacion"],
        doc,
        rotulo="Ubicación (al cierre)",
        filas=doc.por_ubicacion,
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

    # Por categoría (desglose congelado del cierre)
    _hoja_de_desglose(
        libro,
        estilos,
        HOJA_POR_CATEGORIA,
        est.PLANTILLAS["por_categoria"],
        doc,
        rotulo="Categoría (al cierre)",
        filas=doc.por_categoria,
    )

    # Resumen: tarjetas de la plantilla y filas de contexto (Q7)
    _hoja_resumen(libro, estilos, doc)

    libro.close()
    return salida.getvalue()


def _cifras_de_desglose(f: Fila) -> tuple:
    """Etiqueta, las tres cifras congeladas con sus unidades y la fracción encontrada."""
    return (
        f.etiqueta,
        f.encontrado.valor,
        f.encontrado.unidades,
        f.no_encontrado.valor,
        f.no_encontrado.unidades,
        f.registrado.valor,
        f.registrado.unidades,
        fraccion_encontrada(f.encontrado.unidades, f.registrado.unidades),
    )


def _hoja_de_desglose(
    libro: Any,
    estilos: Any,
    nombre: str,
    plantilla: Any,
    doc: Documento,
    *,
    rotulo: str,
    filas: Sequence[Fila],
) -> Any:
    """«Por ubicación» o «Por categoría» (spec 019, T5; Q6): bloque de la empresa congelada
    (filas 1–5), título (6), cabecera (7), una fila por etiqueta del desglose congelado desde
    la 8 y la fila Total (los ``totales`` del cierre, con fondo ``DBEAFE``) justo debajo.
    Barras de datos en «Valor registrado» y «% encontrado», sin extensión 2010, extendidas
    hasta la última fila (req. 5). Las cifras son las de ``cierre.informe``: no se suma."""
    hoja = libro.add_worksheet(nombre)
    total = plantilla.fila_datos + len(filas)
    est.preparar_hoja(hoja, plantilla, total)
    est.dibujar_bloque(hoja, estilos, plantilla, doc.empresa, _fecha_de_corte(doc))
    primero, *resto = plantilla.estilos_titulo_lista
    est.escribir_fila(
        hoja,
        estilos,
        plantilla.fila_cabecera - 1,
        [(nombre, primero), *((None, s) for s in resto)],
    )
    est.escribir_fila(
        hoja,
        estilos,
        plantilla.fila_cabecera,
        list(
            zip(
                (rotulo, *ENCABEZADO_DESGLOSE_EXCEL, None, None),
                plantilla.estilos_cabecera,
                strict=True,
            )
        ),
    )
    for fila, cifras in enumerate(filas, start=plantilla.fila_datos):
        est.escribir_fila(
            hoja,
            estilos,
            fila,
            list(zip(_cifras_de_desglose(cifras), plantilla.estilos_datos, strict=True)),
            plantilla.alto_datos,
        )
    est.escribir_fila(
        hoja,
        estilos,
        total,
        list(
            zip(
                (*_cifras_de_desglose(doc.totales), None, None),
                plantilla.estilos_total,
                strict=True,
            )
        ),
        plantilla.alto_total,
    )
    if filas:
        # Barras de datos solo visuales (sin fórmulas): mínimo y máximo automáticos.
        for col in (5, 7):
            hoja.conditional_format(
                plantilla.fila_datos,
                col,
                total - 1,
                col,
                {"type": "data_bar", "bar_color": est.BARRA, "data_bar_2010": False},
            )
    return hoja


def _datos_sesion(doc: Documento) -> list[tuple[str, str | None]]:
    """Panel «Sesión» del Resumen: rótulo y valor (vacío si falta)."""
    return [
        ("Nombre", doc.sesion or None),
        ("Cerró", doc.cerrada_por or None),
        ("Cerrada", doc.cerrada_en or None),
        ("Moneda", "COP"),
        ("Estado", "Informe congelado"),
    ]


def _notas_resumen(doc: Documento) -> list[str]:
    """La nota de cifras congeladas y los avisos que apliquen, a todo el ancho."""
    notas = [NOTA]
    if not doc.detalle_disponible:
        notas.append(SIN_DETALLE)
    if doc.empresa.vigente:
        notas.append(EMPRESA_VIGENTE)
    return notas


def _alto_nota(texto: str) -> float:
    """Alto de una nota combinada en A:J: 12 pt por línea estimada más aire."""
    lineas = max(1, -(-len(texto) // CARACTERES_POR_LINEA_NOTA))
    return 12.0 * lineas + 10


def _hoja_resumen(libro: Any, estilos: Any, doc: Documento) -> Any:
    """Resumen, opción C (decisión del humano 2026-11-24): bloque (filas 1–5), tarjetas
    2 × 2 con fondo gris a la izquierda (Encontrado, No encontrado, Total registrado y
    % encontrado con su barra), el panel de la sesión a la derecha y, debajo, la nota de
    cifras congeladas y los avisos a todo el ancho. Todo texto va como texto; las cifras,
    como números (COP y porcentaje)."""
    plantilla = est.PLANTILLAS["resumen"]
    hoja = libro.add_worksheet(HOJA_RESUMEN)
    notas = _notas_resumen(doc)
    est.preparar_hoja(hoja, plantilla, FILA_NOTA_RESUMEN + len(notas) - 1)
    est.dibujar_bloque(hoja, estilos, plantilla, doc.empresa, _fecha_de_corte(doc))
    t = doc.totales
    pct = fraccion_encontrada(t.encontrado.unidades, t.registrado.unidades)
    # (fila, columna, valor, estilo): cada celda combinada en dos columnas.
    tarjetas: list[tuple[int, int, Any, str]] = [
        (0, 0, "Encontrado", "tarjeta_rotulo"),
        (1, 0, t.encontrado.valor, "tarjeta_valor_cop"),
        (2, 0, _unidades(t.encontrado.unidades), "tarjeta_subtexto"),
        (0, 2, "No encontrado", "tarjeta_rotulo_izq"),
        (1, 2, t.no_encontrado.valor, "tarjeta_valor_cop_izq"),
        (2, 2, _unidades(t.no_encontrado.unidades), "tarjeta_subtexto_izq"),
        (3, 0, "Total registrado", "tarjeta_rotulo_arriba"),
        (4, 0, t.registrado.valor, "tarjeta_valor_cop"),
        (5, 0, _unidades(t.registrado.unidades), "tarjeta_subtexto"),
        (3, 2, "% encontrado", "tarjeta_rotulo_izq_arriba"),
        (4, 2, pct, "tarjeta_valor_porcentaje_izq"),
    ]
    for fila, col, valor, estilo in tarjetas:
        formato = estilos(estilo)
        hoja.merge_range(FILA_TARJETAS + fila, col, FILA_TARJETAS + fila, col + 1, None, formato)
        est.escribir_celda(hoja, FILA_TARJETAS + fila, col, valor, formato)
    # Barra del % (C12, sin combinar: mide lo mismo en Excel y en LibreOffice); D12 es fondo.
    fila_barra = FILA_TARJETAS + 5
    est.escribir_celda(hoja, fila_barra, 2, pct, estilos("tarjeta_barra_izq"))
    hoja.write_blank(fila_barra, 3, None, estilos("tarjeta_subtexto"))
    hoja.conditional_format(
        fila_barra,
        2,
        fila_barra,
        2,
        {
            "type": "data_bar",
            "bar_color": est.BARRA,  # el azul claro de las barras de los desgloses
            "bar_only": True,
            "min_type": "num",
            "min_value": 0,
            "max_type": "num",
            "max_value": 1,
            # Barra clásica, como la de los desgloses: la de Excel 2010 escribe sus límites
            # como fórmulas (``xm:f``) y el libro no lleva ninguna.
            "data_bar_2010": False,
        },
    )
    # Panel «Sesión» (F:J): título y, en cada fila, rótulo en F y valor en G:J.
    panel, ultima = COLUMNA_PANEL, ULTIMA_COLUMNA_RESUMEN
    titulo = estilos("panel_titulo")
    hoja.merge_range(FILA_TARJETAS, panel, FILA_TARJETAS, ultima, None, titulo)
    hoja.write_string(FILA_TARJETAS, panel, "Sesión", titulo)
    datos = _datos_sesion(doc)
    for i, (rotulo, valor) in enumerate(datos):
        fila = FILA_TARJETAS + 1 + i
        fin = "_fin" if i == len(datos) - 1 else ""
        est.escribir_celda(hoja, fila, panel, rotulo, estilos(f"panel_rotulo{fin}"))
        formato = estilos(f"panel_valor{fin}")
        hoja.merge_range(fila, panel + 1, fila, ultima, None, formato)
        est.escribir_celda(hoja, fila, panel + 1, valor, formato)
    # Nota y avisos: recuadro gris a todo el ancho (A:J).
    nota = estilos("nota_resumen")
    for i, texto in enumerate(notas):
        fila = FILA_NOTA_RESUMEN + i
        est.alto_fila(hoja, fila, _alto_nota(texto))
        hoja.merge_range(fila, 0, fila, ultima, None, nota)
        hoja.write_string(fila, 0, texto, nota)
    return hoja


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
