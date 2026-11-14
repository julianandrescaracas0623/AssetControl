"""Verificar activos en una sesión de conteo (spec 006, T3; R4–R9, Q2–Q4; plan.md §3).

Un ``POST`` guarda una ``verificacion`` y su evento ``verificado`` en una transacción:

1. **Idempotencia primero (R2, Q3):** si el ``id`` ya existe con la misma sesión y el
   mismo activo, se devuelve la guardada (``200``), aunque la sesión ya esté cerrada:
   se guardó antes del cierre y cuenta. Con otro activo o sesión es ``400``.
2. Candado consultivo **compartido** de la sesión (``bloquear_sesion``) antes de leerla:
   el cierre (008) tomará el mismo candado **exclusivo**, así que cada verificación queda
   entera antes o después del cierre. Se usa un candado consultivo y no ``FOR SHARE``
   porque este exige ``UPDATE`` sobre la tabla y la aplicación no lo tiene hasta la 008.
   Cerrada → ``409 sesion_cerrada``.
3. Activo con ``FOR SHARE`` (una edición concurrente espera): dado de baja → ``409``
   (R5a). Se copian su precio, categoría y ubicación de ese momento (ADR-003).
4. Ubicación encontrada (Q4): sala o box activos, como D1 (``400 ubicacion_invalida``).
   Si difiere de la esperada es una **observación**: el activo no se mueve (R6).

El precio solo sale en las respuestas del admin (P13); el evento no lo guarda.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.activos.models import Activo, ActivoEvento
from app.activos.service import _ruta
from app.catalogo.models import Ubicacion
from app.conteo.models import SesionConteo, Verificacion
from app.conteo.service import ErrorConteo, NoEncontrado, _autor
from app.nombres import normalize_display_name

UNIQUE_VIOLATION = "23505"
ESTADOS_FISICOS = ("ok", "danado")
CAMPOS = {"id", "activo_id", "ubicacion_encontrada_id", "estado_fisico", "nota", "ocurrido_en"}


class SesionCerrada(ErrorConteo):
    status = 409
    code = "sesion_cerrada"
    message = "La sesión se cerró: esta verificación no se guardó."


class ActivoDadoDeBaja(ErrorConteo):
    status = 409
    code = "activo_dado_de_baja"
    message = "El activo está dado de baja: no se puede verificar."


class UbicacionInvalida(ErrorConteo):
    code = "ubicacion_invalida"
    message = "Elige una sala o un box activos."


ERRORES = (SesionCerrada, ActivoDadoDeBaja, UbicacionInvalida)


def _uuid(valor: object) -> uuid.UUID:
    if not isinstance(valor, str):
        raise ErrorConteo()
    try:
        return uuid.UUID(valor)
    except ValueError:
        raise ErrorConteo() from None


def _ubicacion_vista(session: Session, ubicacion_id: uuid.UUID) -> dict[str, str]:
    ubicacion = session.get(Ubicacion, ubicacion_id)
    return {"id": str(ubicacion_id), "ruta": _ruta(session, ubicacion) if ubicacion else ""}


def vista(session: Session, v: Verificacion, *, con_precio: bool) -> dict[str, object]:
    activo = session.get(Activo, v.activo_id)
    datos: dict[str, object] = {
        "id": str(v.id),
        "sesion_id": str(v.sesion_id),
        "activo": {
            "id": str(v.activo_id),
            "codigo": activo.codigo if activo else "",
            "nombre": activo.nombre if activo else "",
        },
        "ubicacion_esperada": _ubicacion_vista(session, v.ubicacion_esperada_id),
        "ubicacion_encontrada": _ubicacion_vista(session, v.ubicacion_encontrada_id),
        "estado_fisico": v.estado_fisico,
        "nota": v.nota,
        "verificado_por": _autor(session, v.verificado_por),
        "ocurrido_en": v.ocurrido_en.astimezone(UTC).isoformat() if v.ocurrido_en else None,
        "recibido_en": v.recibido_en.astimezone(UTC).isoformat(),
        "seq": v.seq,
    }
    if con_precio:
        datos["precio_al_contar"] = str(v.precio_al_contar)
    return datos


# --- Validación ----------------------------------------------------------------------------


def datos_de_verificacion(body: dict[str, object]) -> dict[str, object]:
    if not set(body) <= CAMPOS:
        raise ErrorConteo()
    estado = body.get("estado_fisico")
    if estado not in ESTADOS_FISICOS:
        raise ErrorConteo()
    valor = body.get("nota")
    nota = None
    if valor is not None and not (isinstance(valor, str) and not valor.strip()):
        nota = normalize_display_name(valor) if isinstance(valor, str) else None
        if nota is None:
            raise ErrorConteo("La nota admite hasta 120 caracteres.")
    ocurrido = body.get("ocurrido_en")
    ocurrido_en = None
    if ocurrido is not None:
        if not isinstance(ocurrido, str):
            raise ErrorConteo()
        try:
            ocurrido_en = datetime.fromisoformat(ocurrido)
        except ValueError:
            raise ErrorConteo() from None
        if ocurrido_en.tzinfo is None:
            raise ErrorConteo()
    return {
        "id": _uuid(body.get("id")),
        "activo_id": _uuid(body.get("activo_id")),
        "ubicacion_encontrada_id": _uuid(body.get("ubicacion_encontrada_id")),
        "estado_fisico": estado,
        "nota": nota,
        "ocurrido_en": ocurrido_en,
    }


# --- Verificar (R4–R8) ---------------------------------------------------------------------


def _previa(
    session: Session, verificacion_id: uuid.UUID, sesion_id: uuid.UUID, activo_id: uuid.UUID
) -> Verificacion | None:
    previa = session.get(Verificacion, verificacion_id)
    if previa is None:
        return None
    if previa.sesion_id != sesion_id or previa.activo_id != activo_id:
        raise ErrorConteo("Ese identificador ya se usó para otra verificación.")
    return previa


def bloquear_sesion(session: Session, sesion_id: uuid.UUID, *, exclusivo: bool = False) -> None:
    """Candado consultivo de la transacción para la sesión (compartido o exclusivo)."""
    clave = func.hashtextextended(f"sesion_conteo:{sesion_id}", 0)
    funcion = func.pg_advisory_xact_lock if exclusivo else func.pg_advisory_xact_lock_shared
    session.execute(select(funcion(clave)))


def verificar(
    session: Session, sesion_id: uuid.UUID, datos: dict[str, object], usuario_id: uuid.UUID
) -> tuple[Verificacion, bool]:
    """La verificación guardada y si es nueva (``201``) o un reintento (``200``)."""
    verificacion_id = _uuid(str(datos["id"]))
    activo_id = _uuid(str(datos["activo_id"]))
    previa = _previa(session, verificacion_id, sesion_id, activo_id)
    if previa is not None:
        return previa, False

    bloquear_sesion(session, sesion_id)
    sesion = session.scalars(
        select(SesionConteo)
        .where(SesionConteo.id == sesion_id)
        .execution_options(populate_existing=True)
    ).one_or_none()
    if sesion is None:
        raise NoEncontrado()
    if sesion.estado != "abierta":
        raise SesionCerrada()
    activo = session.scalars(
        select(Activo)
        .where(Activo.id == activo_id)
        .with_for_update(read=True)
        .execution_options(populate_existing=True)
    ).one_or_none()
    if activo is None:
        raise NoEncontrado()
    if activo.estado == "dado_de_baja":
        raise ActivoDadoDeBaja()
    encontrada = session.scalars(
        select(Ubicacion)
        .where(Ubicacion.id == datos["ubicacion_encontrada_id"])
        .with_for_update(read=True)
    ).one_or_none()
    if encontrada is None:
        raise NoEncontrado()
    if encontrada.tipo == "sede" or not encontrada.activa:
        raise UbicacionInvalida()

    verificacion = Verificacion(
        id=verificacion_id,
        sesion_id=sesion.id,
        activo_id=activo.id,
        ubicacion_esperada_id=activo.ubicacion_id,
        ubicacion_encontrada_id=encontrada.id,
        estado_fisico=datos["estado_fisico"],
        precio_al_contar=activo.precio_compra,
        categoria_al_contar=activo.categoria_id,
        nota=datos["nota"],
        verificado_por=usuario_id,
        ocurrido_en=datos["ocurrido_en"],
    )
    evento = ActivoEvento(
        activo_id=activo.id,
        tipo="verificado",
        usuario_id=usuario_id,
        sesion_id=sesion.id,
        verificacion_id=verificacion_id,
        datos={
            "estado_fisico": datos["estado_fisico"],
            **({"nota": datos["nota"]} if datos["nota"] else {}),
            "ubicacion_esperada": _ubicacion_vista(session, activo.ubicacion_id),
            "ubicacion_encontrada": _ubicacion_vista(session, encontrada.id),
            "sesion": sesion.nombre,
        },
    )
    try:
        with session.begin_nested():
            session.add(verificacion)
            session.flush()
            session.add(evento)
            session.flush()
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) != UNIQUE_VIOLATION:
            raise
        session.expunge_all()
        previa = _previa(session, verificacion_id, sesion_id, activo_id)
        if previa is not None:
            return previa, False
        # El id choca con una fila invisible (otro tenant): no se revela nada.
        raise ErrorConteo("Ese identificador ya se usó para otra verificación.") from None
    return verificacion, True


def ultima(session: Session, sesion_id: uuid.UUID, activo_id: object) -> Verificacion | None:
    """La verificación vigente (mayor ``seq``, R3) del activo en la sesión, o ``None``."""
    activo = _uuid(activo_id)
    if session.get(SesionConteo, sesion_id) is None:
        raise NoEncontrado()
    return session.scalars(
        select(Verificacion)
        .where(Verificacion.sesion_id == sesion_id, Verificacion.activo_id == activo)
        .order_by(Verificacion.seq.desc())
        .limit(1)
    ).one_or_none()
