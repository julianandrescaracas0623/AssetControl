"""Reglas de ubicaciones y categorías (spec 003; R1–R6, Q1–Q4; plan.md §2–§3).

Todo corre en la ``tenant_session`` de la vista protegida: RLS y el filtro central
acotan al tenant del token, así que un ``id`` de otro tenant no existe para estas
funciones (``NoEncontrado`` → ``404``).

- Jerarquía estricta (Q1): sede sin padre, sala bajo sede, box bajo sala. El padre se
  toma con ``FOR UPDATE``: crear una hija y desactivar el padre se serializan.
- Nombres (H-3 y Q3): ``normalize_display_name`` y una clave sin tildes ni mayúsculas
  (``nombre_clave``) cuya unicidad hace cumplir la base (``23505`` → ``409``).
- Desactivar con hijas activas se rechaza (Q2); reactivar exige el padre activo.
"""

import re
import unicodedata
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import case, exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.catalogo.models import Categoria, Ubicacion
from app.nombres import normalize_display_name

TIPOS = ("sede", "sala", "box")
# Tipo de padre que exige cada tipo (Q1).
PADRE_DE = {"sede": None, "sala": "sede", "box": "sala"}
UNIQUE_VIOLATION = "23505"


class ErrorCatalogo(Exception):
    """Error de regla con su estado HTTP y código estable (``app.errors``)."""

    status = 400
    code = "solicitud_invalida"
    message = "La solicitud no es válida."

    def __init__(self) -> None:
        super().__init__(self.message)


class NombreInvalido(ErrorCatalogo):
    pass


class NoEncontrado(ErrorCatalogo):
    status = 404
    code = "no_encontrado"
    message = "El recurso no existe."


class JerarquiaInvalida(ErrorCatalogo):
    code = "jerarquia_invalida"
    message = "Una sede no tiene padre, una sala va dentro de una sede y un box dentro de una sala."


class NombreDuplicado(ErrorCatalogo):
    status = 409
    code = "nombre_duplicado"
    message = "Ya existe uno con ese nombre en el mismo lugar."


class TieneHijasActivas(ErrorCatalogo):
    status = 409
    code = "tiene_hijas_activas"
    message = "Primero desactiva las salas o boxes que tiene dentro."


class PadreInactivo(ErrorCatalogo):
    status = 409
    code = "padre_inactivo"
    message = "La ubicación de arriba está inactiva: actívala primero."


ERRORES = (
    NombreInvalido,
    NoEncontrado,
    JerarquiaInvalida,
    NombreDuplicado,
    TieneHijasActivas,
    PadreInactivo,
)


def nombre_y_clave(nombre: object) -> tuple[str, str]:
    """Nombre visible normalizado (H-3) y su clave de comparación (Q3)."""
    if not isinstance(nombre, str):
        raise NombreInvalido()
    visible = normalize_display_name(nombre)
    if visible is None:
        raise NombreInvalido()
    sin_marcas = "".join(
        char for char in unicodedata.normalize("NFD", visible) if unicodedata.category(char) != "Mn"
    )
    clave = re.sub(r"\s+", " ", sin_marcas.casefold()).strip()
    return visible, clave


def _guardar[T](session: Session, escribir: Callable[[], T]) -> T:
    """Ejecuta ``escribir`` y su flush en un savepoint; un duplicado es ``409``."""
    try:
        with session.begin_nested():
            resultado = escribir()
            session.flush()
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == UNIQUE_VIOLATION:
            raise NombreDuplicado() from None
        raise
    return resultado


# --- Ubicaciones ----------------------------------------------------------------------


@dataclass(frozen=True)
class UbicacionVista:
    id: uuid.UUID
    nombre: str
    tipo: str
    padre_id: uuid.UUID | None
    activa: bool

    def to_json(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "nombre": self.nombre,
            "tipo": self.tipo,
            "padre_id": str(self.padre_id) if self.padre_id else None,
            "activa": self.activa,
        }


def _vista(ubicacion: Ubicacion) -> UbicacionVista:
    return UbicacionVista(
        id=ubicacion.id,
        nombre=ubicacion.nombre,
        tipo=ubicacion.tipo,
        padre_id=ubicacion.padre_id,
        activa=ubicacion.activa,
    )


def _bloquear(session: Session, ubicacion_id: uuid.UUID) -> Ubicacion:
    ubicacion = session.scalars(
        select(Ubicacion).where(Ubicacion.id == ubicacion_id).with_for_update()
    ).one_or_none()
    if ubicacion is None:
        raise NoEncontrado()
    return ubicacion


def listar_ubicaciones(session: Session, *, solo_activas: bool) -> list[UbicacionVista]:
    orden_tipo = case({tipo: posicion for posicion, tipo in enumerate(TIPOS)}, value=Ubicacion.tipo)
    consulta = select(Ubicacion).order_by(orden_tipo, Ubicacion.nombre_clave, Ubicacion.id)
    if solo_activas:
        consulta = consulta.where(Ubicacion.activa.is_(True))
    return [_vista(u) for u in session.scalars(consulta)]


def crear_ubicacion(
    session: Session, *, nombre: object, tipo: object, padre_id: uuid.UUID | None
) -> UbicacionVista:
    visible, clave = nombre_y_clave(nombre)
    if tipo not in TIPOS:
        raise ErrorCatalogo()
    tipo_padre = PADRE_DE[tipo]  # type: ignore[index]
    if (tipo_padre is None) != (padre_id is None):
        raise JerarquiaInvalida()
    if padre_id is not None:
        padre = _bloquear(session, padre_id)
        if padre.tipo != tipo_padre:
            raise JerarquiaInvalida()
        if not padre.activa:
            raise PadreInactivo()

    def escribir() -> Ubicacion:
        ubicacion = Ubicacion(nombre=visible, nombre_clave=clave, tipo=tipo, padre_id=padre_id)
        session.add(ubicacion)
        return ubicacion

    return _vista(_guardar(session, escribir))


def actualizar_ubicacion(
    session: Session, ubicacion_id: uuid.UUID, *, nombre: object = None, activa: object = None
) -> UbicacionVista:
    if nombre is None and activa is None:
        raise ErrorCatalogo()
    if activa is not None and not isinstance(activa, bool):
        raise ErrorCatalogo()
    cambio = nombre_y_clave(nombre) if nombre is not None else None

    ubicacion = _bloquear(session, ubicacion_id)
    if activa is False and ubicacion.activa:
        hijas_activas = session.scalar(
            select(exists().where(Ubicacion.padre_id == ubicacion.id, Ubicacion.activa.is_(True)))
        )
        if hijas_activas:
            raise TieneHijasActivas()
    if activa is True and not ubicacion.activa and ubicacion.padre_id is not None:
        if not _bloquear(session, ubicacion.padre_id).activa:
            raise PadreInactivo()

    def escribir() -> Ubicacion:
        if cambio is not None:
            ubicacion.nombre, ubicacion.nombre_clave = cambio
        if activa is not None:
            ubicacion.activa = activa
        return ubicacion

    return _vista(_guardar(session, escribir))


# --- Categorías (T3) ------------------------------------------------------------------


@dataclass(frozen=True)
class CategoriaVista:
    id: uuid.UUID
    nombre: str

    def to_json(self) -> dict[str, object]:
        return {"id": str(self.id), "nombre": self.nombre}


def _vista_categoria(categoria: Categoria) -> CategoriaVista:
    return CategoriaVista(id=categoria.id, nombre=categoria.nombre)
