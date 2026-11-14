"""Alta, resolución y ficha de activos (spec 004, T3; R1–R7, D1, Q1–Q3, Q5; plan.md §4).

Todo corre en la ``tenant_session`` de la vista: RLS y el filtro central acotan al
tenant, así que una categoría, ubicación o activo de otro tenant no existe (``404``).

- Alta idempotente (R4): el ``id`` lo manda el cliente; si ya existe con el mismo
  código se devuelve el guardado (``200``); un código de otro activo es ``409
  codigo_existente`` con ese activo, para abrirlo en vez de duplicar.
- La ubicación se toma con ``FOR SHARE``: desactivarla (``FOR UPDATE``, D2) espera a que
  termine el alta y entonces ve el activo nuevo.
- Precio (R5, P13): ``vista`` lo incluye solo para el admin; para el contador la clave
  no existe.
"""

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.activos.dominio import normalizar_codigo, parsear_precio
from app.activos.models import Activo, ActivoEvento
from app.catalogo.models import Categoria, Ubicacion
from app.nombres import normalize_display_name

OPCIONALES = ("serial", "marca", "modelo", "subtipo")
UNIQUE_VIOLATION = "23505"
UBICACION_INVALIDA_SQLSTATE = "P0002"


class ErrorActivo(Exception):
    status = 400
    code = "solicitud_invalida"
    message = "La solicitud no es válida."

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message)


class CodigoInvalido(ErrorActivo):
    code = "codigo_invalido"
    message = "El código no es válido: de 1 a 40 letras sin tilde, números o - . / _, sin espacios."


class PrecioInvalido(ErrorActivo):
    code = "precio_invalido"
    message = "El precio no es válido: un valor mayor o igual a 0 con hasta dos decimales."


class UbicacionInvalida(ErrorActivo):
    code = "ubicacion_invalida"
    message = "Elige una sala o un box activos."


class NoEncontrado(ErrorActivo):
    status = 404
    code = "no_encontrado"
    message = "El recurso no existe."


class CodigoExistente(ErrorActivo):
    status = 409
    code = "codigo_existente"
    message = "Ese código ya está registrado en otro activo."

    def __init__(self, activo: Activo) -> None:
        super().__init__()
        self.activo = {"id": str(activo.id), "codigo": activo.codigo, "nombre": activo.nombre}


ERRORES = (ErrorActivo, CodigoInvalido, PrecioInvalido, UbicacionInvalida, NoEncontrado)


@dataclass(frozen=True)
class Resultado:
    activo: dict[str, object]
    creado: bool


# --- Vista ------------------------------------------------------------------------------


def _ruta(session: Session, ubicacion: Ubicacion) -> str:
    if ubicacion.tipo == "box" and ubicacion.padre_id is not None:
        sala = session.get(Ubicacion, ubicacion.padre_id)
        if sala is not None:
            return f"{sala.nombre} › {ubicacion.nombre}"
    return ubicacion.nombre


def vista(session: Session, activo: Activo, *, con_precio: bool) -> dict[str, object]:
    """Respuesta de un activo; ``precio_compra`` solo si ``con_precio`` (admin)."""
    categoria = session.get(Categoria, activo.categoria_id)
    ubicacion = session.get(Ubicacion, activo.ubicacion_id)
    datos: dict[str, object] = {
        "id": str(activo.id),
        "codigo": activo.codigo,
        "nombre": activo.nombre,
        "categoria": {
            "id": str(activo.categoria_id),
            "nombre": categoria.nombre if categoria else "",
        },
        "ubicacion": {
            "id": str(activo.ubicacion_id),
            "nombre": ubicacion.nombre if ubicacion else "",
            "ruta": _ruta(session, ubicacion) if ubicacion else "",
        },
        **{campo: getattr(activo, campo) for campo in OPCIONALES},
        "fecha_compra": activo.fecha_compra.isoformat() if activo.fecha_compra else None,
        "estado": activo.estado,
        "row_version": activo.row_version,
        "creado_en": activo.creado_en.isoformat(),
    }
    if con_precio:
        datos["precio_compra"] = str(activo.precio_compra)
    return datos


# --- Lectura ----------------------------------------------------------------------------


def resolver(session: Session, codigo: object) -> Activo:
    normalizado = normalizar_codigo(codigo)
    if normalizado is None:
        raise CodigoInvalido()
    activo = session.scalars(select(Activo).where(Activo.codigo == normalizado)).one_or_none()
    if activo is None:
        raise NoEncontrado()
    return activo


def obtener(session: Session, activo_id: uuid.UUID) -> Activo:
    activo = session.get(Activo, activo_id)
    if activo is None:
        raise NoEncontrado()
    return activo


# --- Validación del cuerpo --------------------------------------------------------------


def _uuid(valor: object, *, faltante: type[ErrorActivo] = ErrorActivo) -> uuid.UUID:
    if not isinstance(valor, str):
        raise faltante()
    try:
        return uuid.UUID(valor)
    except ValueError:
        raise faltante() from None


def _texto_opcional(valor: object) -> str | None:
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    texto = normalize_display_name(valor) if isinstance(valor, str) else None
    if texto is None:
        raise ErrorActivo()
    return texto


def _fecha(valor: object) -> date | None:
    if valor is None or valor == "":
        return None
    if not isinstance(valor, str):
        raise ErrorActivo()
    try:
        fecha = date.fromisoformat(valor)
    except ValueError:
        raise ErrorActivo() from None
    if fecha > date.today():
        raise ErrorActivo("La fecha de compra no puede ser futura.")
    return fecha


def _categoria(session: Session, valor: object) -> Categoria:
    categoria = session.get(Categoria, _uuid(valor))
    if categoria is None:
        raise NoEncontrado()
    return categoria


def _ubicacion(session: Session, valor: object) -> Ubicacion:
    ubicacion = session.scalars(
        select(Ubicacion).where(Ubicacion.id == _uuid(valor)).with_for_update(read=True)
    ).one_or_none()
    if ubicacion is None:
        raise NoEncontrado()
    if ubicacion.tipo == "sede" or not ubicacion.activa:
        raise UbicacionInvalida()
    return ubicacion


# --- Alta -------------------------------------------------------------------------------


def _existente(session: Session, activo_id: uuid.UUID, codigo: str) -> Activo | None:
    """El activo de este ``id`` si es un reintento (R4); error si el ``id`` es de otro."""
    previo = session.get(Activo, activo_id)
    if previo is None:
        return None
    if previo.codigo != codigo:
        raise ErrorActivo("Ese identificador ya se usó para otro activo.")
    return previo


def _por_codigo(session: Session, codigo: str) -> Activo | None:
    return session.scalars(select(Activo).where(Activo.codigo == codigo)).one_or_none()


@dataclass(frozen=True)
class DatosAlta:
    id: uuid.UUID
    codigo: str
    nombre: str
    precio: Decimal
    categoria_id: uuid.UUID
    ubicacion_id: uuid.UUID
    opcionales: dict[str, str | None]
    fecha_compra: date | None
    copiado_de: uuid.UUID | None = None


def guardar(
    session: Session, datos: DatosAlta, *, usuario_id: uuid.UUID, con_precio: bool
) -> Resultado:
    """Inserta el activo y su evento ``creado`` en un savepoint (carreras → 409/200)."""
    previo = _existente(session, datos.id, datos.codigo)
    if previo is not None:
        return Resultado(vista(session, previo, con_precio=con_precio), creado=False)
    otro = _por_codigo(session, datos.codigo)
    if otro is not None:
        raise CodigoExistente(otro)
    _categoria(session, str(datos.categoria_id))
    _ubicacion(session, str(datos.ubicacion_id))

    activo = Activo(
        id=datos.id,
        codigo=datos.codigo,
        nombre=datos.nombre,
        categoria_id=datos.categoria_id,
        ubicacion_id=datos.ubicacion_id,
        precio_compra=datos.precio,
        fecha_compra=datos.fecha_compra,
        creado_por=usuario_id,
        atributos={},
        **datos.opcionales,
    )
    evento = ActivoEvento(
        activo_id=datos.id,
        tipo="creado",
        usuario_id=usuario_id,
        datos={
            "codigo": datos.codigo,
            "nombre": datos.nombre,
            "categoria_id": str(datos.categoria_id),
            "ubicacion_id": str(datos.ubicacion_id),
            "precio_compra": str(datos.precio),
            "fecha_compra": datos.fecha_compra.isoformat() if datos.fecha_compra else None,
            **datos.opcionales,
            **({"copiado_de": str(datos.copiado_de)} if datos.copiado_de else {}),
        },
    )
    try:
        with session.begin_nested():
            session.add(activo)
            session.flush()
            session.add(evento)
            session.flush()
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) != UNIQUE_VIOLATION:
            raise
        session.expunge_all()
        previo = _existente(session, datos.id, datos.codigo)
        if previo is not None:
            return Resultado(vista(session, previo, con_precio=con_precio), creado=False)
        otro = _por_codigo(session, datos.codigo)
        if otro is not None:
            raise CodigoExistente(otro) from None
        # El id choca con una fila invisible (otro tenant): no se revela nada.
        raise ErrorActivo("Ese identificador ya se usó para otro activo.") from None
    return Resultado(vista(session, activo, con_precio=con_precio), creado=True)


def datos_de_alta(body: dict[str, object]) -> DatosAlta:
    """Valida el cuerpo de un alta nueva (R3)."""
    activo_id = _uuid(body.get("id"))
    codigo = normalizar_codigo(body.get("codigo"))
    if codigo is None:
        raise CodigoInvalido()
    nombre = body.get("nombre")
    nombre = normalize_display_name(nombre) if isinstance(nombre, str) else None
    if nombre is None:
        raise ErrorActivo()
    precio = parsear_precio(body.get("precio_compra"))
    if precio is None:
        raise PrecioInvalido()
    return DatosAlta(
        id=activo_id,
        codigo=codigo,
        nombre=nombre,
        precio=precio,
        categoria_id=_uuid(body.get("categoria_id")),
        ubicacion_id=_uuid(body.get("ubicacion_id")),
        opcionales={campo: _texto_opcional(body.get(campo)) for campo in OPCIONALES},
        fecha_compra=_fecha(body.get("fecha_compra")),
    )


# Lo que se copia al duplicar (R6, CU-CAT-03); nunca código, serial ni historial.
COPIADOS = ("marca", "modelo", "subtipo")


def datos_de_duplicado(session: Session, body: dict[str, object], *, es_admin: bool) -> DatosAlta:
    """Valida un duplicado (``copiar_de``): el servidor copia del original (R6, Q3).

    El contador no puede mandar precio (lo hereda sin verlo); el admin puede cambiarlo.
    La ubicación puede cambiar (la unidad nueva puede estar en otro cuarto).
    """
    activo_id = _uuid(body.get("id"))
    codigo = normalizar_codigo(body.get("codigo"))
    if codigo is None:
        raise CodigoInvalido()
    origen = session.get(Activo, _uuid(body.get("copiar_de")))
    if origen is None:
        raise NoEncontrado()
    precio = origen.precio_compra
    if body.get("precio_compra") is not None:
        if not es_admin:
            raise ErrorActivo("Al duplicar, el precio se copia del original.")
        precio = parsear_precio(body.get("precio_compra"))
        if precio is None:
            raise PrecioInvalido()
    ubicacion = body.get("ubicacion_id")
    return DatosAlta(
        id=activo_id,
        codigo=codigo,
        nombre=origen.nombre,
        precio=precio,
        categoria_id=origen.categoria_id,
        ubicacion_id=_uuid(ubicacion) if ubicacion is not None else origen.ubicacion_id,
        opcionales={
            **{campo: getattr(origen, campo) for campo in COPIADOS},
            "serial": _texto_opcional(body.get("serial")),
        },
        fecha_compra=None,
        copiado_de=origen.id,
    )


# --- Búsqueda y sugerencias (T5; R10, CU-CAT-04) -------------------------------------------

POR_PAGINA = 25
ESTADOS = ("activo", "en_reparacion", "dado_de_baja")
CAMPOS_SUGERIDOS = ("nombre", "marca", "modelo", "subtipo")
MAX_SUGERENCIAS = 8


def _patron(texto: str) -> str:
    """``%texto%`` para ``ILIKE`` con ``%``, ``_`` y ``\\`` escapados."""
    escapado = texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escapado}%"


def _consulta_texto(valor: object) -> str | None:
    if valor is None:
        return None
    if not isinstance(valor, str) or len(valor) > 120:
        raise ErrorActivo()
    texto = " ".join(valor.split())
    return texto or None


@dataclass(frozen=True)
class Pagina:
    activos: list[dict[str, object]]
    total: int
    pagina: int
    por_pagina: int


def buscar(
    session: Session, *, q: object, estado: object, pagina: object, con_precio: bool
) -> Pagina:
    texto = _consulta_texto(q)
    if estado is not None and estado not in ESTADOS:
        raise ErrorActivo()
    try:
        numero = int(pagina) if pagina is not None else 1
    except (TypeError, ValueError):
        raise ErrorActivo() from None
    if numero < 1 or numero > 10_000:
        raise ErrorActivo()

    filtro = select(Activo)
    if texto:
        patron = _patron(texto)
        filtro = filtro.where(
            or_(
                Activo.codigo.ilike(_patron(texto.upper()), escape="\\"),
                Activo.nombre.ilike(patron, escape="\\"),
                Activo.serial.ilike(patron, escape="\\"),
            )
        )
    if estado is not None:
        filtro = filtro.where(Activo.estado == estado)
    total = session.scalar(select(func.count()).select_from(filtro.subquery()))
    filas = session.scalars(
        filtro.order_by(Activo.creado_en.desc(), Activo.id)
        .limit(POR_PAGINA)
        .offset((numero - 1) * POR_PAGINA)
    )
    return Pagina(
        activos=[vista(session, a, con_precio=con_precio) for a in filas],
        total=int(total or 0),
        pagina=numero,
        por_pagina=POR_PAGINA,
    )


def sugerencias(session: Session, *, campo: object, q: object) -> list[str]:
    """Valores ya registrados de ``campo`` que contienen ``q``, los más usados primero."""
    if campo not in CAMPOS_SUGERIDOS:
        raise ErrorActivo()
    texto = _consulta_texto(q)
    columna = getattr(Activo, campo)  # type: ignore[arg-type]
    consulta = select(columna, func.count().label("usos")).where(columna.is_not(None))
    if texto:
        consulta = consulta.where(columna.ilike(_patron(texto), escape="\\"))
    consulta = (
        consulta.group_by(columna).order_by(func.count().desc(), columna).limit(MAX_SUGERENCIAS)
    )
    return [fila[0] for fila in session.execute(consulta)]
