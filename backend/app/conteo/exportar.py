"""Exportar el informe congelado a Excel y PDF (spec 009; CU-INF-03).

Una sola entrada: el dict de ``cierre.informe`` (lo mismo que ve la pantalla). De él
sale un ``Documento`` intermedio y de ese documento los dos archivos. Aquí no se suma
ni se vuelve a leer ``activo``, ``verificacion`` o el universo U (R8): cada cifra es la
del cierre. El formato COP y el porcentaje son los de la web (``lib/format.ts``,
``porcentaje`` de ``lib/sesiones.ts``) para que el archivo diga lo mismo que la pantalla.
"""

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
