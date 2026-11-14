"""Sesiones de conteo (spec 006, T2; R1–R3, Q1; plan.md §3).

Todo corre en la ``tenant_session`` de la vista (RLS y filtro central): una sesión de
otro tenant no existe (``404``).

- Abrir (Q1): una sola sesión ``conteo`` abierta por tenant. Se comprueba antes y,
  además, el índice único parcial de la base resuelve la carrera (``409``).
- Avance (CU-SES-02): por ubicación vigente del activo, los ``activo`` y
  ``en_reparacion`` y cuántos tienen al menos una verificación en la sesión. Es
  información de trabajo, sin precios; no es el informe (008).
"""

import uuid
from datetime import date

from sqlalchemy import and_, case, exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.activos.models import Activo
from app.activos.service import _ruta
from app.auth.models import Usuario
from app.catalogo.models import Ubicacion
from app.conteo.models import SesionConteo, Verificacion
from app.nombres import normalize_display_name

UNIQUE_VIOLATION = "23505"
ESTADOS_QUE_CUENTAN = ("activo", "en_reparacion")


class ErrorConteo(Exception):
    status = 400
    code = "solicitud_invalida"
    message = "La solicitud no es válida."

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message)


class NoEncontrado(ErrorConteo):
    status = 404
    code = "no_encontrado"
    message = "El recurso no existe."


class SesionAbiertaExistente(ErrorConteo):
    status = 409
    code = "sesion_abierta_existente"
    message = "Ya hay una sesión de conteo abierta. Ciérrala antes de abrir otra."


ERRORES = (ErrorConteo, NoEncontrado, SesionAbiertaExistente)


def _autor(session: Session, usuario_id: uuid.UUID | None) -> dict[str, str] | None:
    if usuario_id is None:
        return None
    nombre = session.scalar(select(Usuario.nombre).where(Usuario.id == usuario_id))
    return {"id": str(usuario_id), "nombre": nombre or ""}


def vista(session: Session, sesion: SesionConteo) -> dict[str, object]:
    return {
        "id": str(sesion.id),
        "nombre": sesion.nombre,
        "tipo": sesion.tipo,
        "estado": sesion.estado,
        "fecha_corte": sesion.fecha_corte.isoformat(),
        "abierta_por": _autor(session, sesion.abierta_por),
        "abierta_en": sesion.abierta_en.isoformat(),
        "cerrada_por": _autor(session, sesion.cerrada_por),
        "cerrada_en": sesion.cerrada_en.isoformat() if sesion.cerrada_en else None,
    }


# --- Lectura ----------------------------------------------------------------------------


def _abierta(session: Session) -> SesionConteo | None:
    return session.scalars(
        select(SesionConteo).where(SesionConteo.estado == "abierta", SesionConteo.tipo == "conteo")
    ).one_or_none()


def abierta(session: Session) -> SesionConteo | None:
    return _abierta(session)


def listar(session: Session) -> list[SesionConteo]:
    return list(
        session.scalars(
            select(SesionConteo).order_by(
                case((SesionConteo.estado == "abierta", 0), else_=1),
                SesionConteo.abierta_en.desc(),
                SesionConteo.id,
            )
        )
    )


def obtener(session: Session, sesion_id: uuid.UUID) -> SesionConteo:
    sesion = session.get(SesionConteo, sesion_id)
    if sesion is None:
        raise NoEncontrado()
    return sesion


# --- Abrir (R1, Q1) ---------------------------------------------------------------------


def datos_de_apertura(body: dict[str, object]) -> tuple[str, date]:
    if not set(body) <= {"nombre", "fecha_corte"}:
        raise ErrorConteo()
    nombre = body.get("nombre")
    nombre = normalize_display_name(nombre) if isinstance(nombre, str) else None
    if nombre is None:
        raise ErrorConteo("El nombre es obligatorio: de 1 a 120 caracteres.")
    valor = body.get("fecha_corte")
    if not isinstance(valor, str):
        raise ErrorConteo("La fecha de corte es obligatoria.")
    try:
        fecha = date.fromisoformat(valor)
    except ValueError:
        raise ErrorConteo("La fecha de corte no es válida.") from None
    return nombre, fecha


def abrir(session: Session, nombre: str, fecha_corte: date, usuario_id: uuid.UUID) -> SesionConteo:
    if _abierta(session) is not None:
        raise SesionAbiertaExistente()
    sesion = SesionConteo(nombre=nombre, fecha_corte=fecha_corte, abierta_por=usuario_id)
    try:
        with session.begin_nested():
            session.add(sesion)
            session.flush()
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) != UNIQUE_VIOLATION:
            raise
        raise SesionAbiertaExistente() from None
    return sesion


# --- Avance (R3, CU-SES-02) -------------------------------------------------------------


def avance(session: Session, sesion: SesionConteo) -> dict[str, object]:
    verificado = exists().where(
        and_(Verificacion.sesion_id == sesion.id, Verificacion.activo_id == Activo.id)
    )
    filas = session.execute(
        select(
            Activo.ubicacion_id,
            func.count().label("total"),
            func.count().filter(verificado).label("verificados"),
        )
        .where(Activo.estado.in_(ESTADOS_QUE_CUENTAN))
        .group_by(Activo.ubicacion_id)
    ).all()
    por_ubicacion = []
    for fila in filas:
        ubicacion = session.get(Ubicacion, fila.ubicacion_id)
        por_ubicacion.append(
            {
                "ubicacion": {
                    "id": str(fila.ubicacion_id),
                    "ruta": _ruta(session, ubicacion) if ubicacion else "",
                },
                "total": fila.total,
                "verificados": fila.verificados,
                "pendientes": fila.total - fila.verificados,
            }
        )
    por_ubicacion.sort(key=lambda f: str(f["ubicacion"]["ruta"]).casefold())  # type: ignore[index]
    total = sum(int(f["total"]) for f in por_ubicacion)  # type: ignore[arg-type]
    verificados = sum(int(f["verificados"]) for f in por_ubicacion)  # type: ignore[arg-type]
    return {
        "total": total,
        "verificados": verificados,
        "pendientes": total - verificados,
        "por_ubicacion": por_ubicacion,
    }
