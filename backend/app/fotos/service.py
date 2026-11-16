"""Fotos de activos y de verificaciones (spec 012, T4–T5; R2, R4–R9, Q1 B, Q2 B; plan.md §5).

- Subir: valida el activo (o la verificación), procesa la imagen (``imagen.procesar``),
  guarda la completa y la miniatura en el almacenamiento y **después** escribe la fila.
  Reintentar con el mismo ``id`` devuelve la misma foto (idempotente).
- Cambiar o quitar la principal (los dos roles, Q1 B): la anterior queda retirada en la
  misma transacción y su imagen se **borra** del almacenamiento después del commit (Q2 B).
  Si la transacción se revierte, se borran las imágenes nuevas.
- Leer: solo fotos del tenant (RLS) y no retiradas.

Nunca se registran claves de almacenamiento ni nombres de archivo del usuario.
"""

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.activos import service as activos_service
from app.activos.cambios import ActivoDadoDeBaja
from app.activos.models import Activo, ActivoEvento
from app.conteo.models import SesionConteo, Verificacion
from app.fotos import imagen
from app.fotos.almacen import Almacen, ObjetoNoEncontrado
from app.fotos.models import Foto

logger = logging.getLogger(__name__)
TIPO = "image/jpeg"
TAMANOS = ("completa", "mini")


class ErrorFoto(Exception):
    status = 400
    code = "solicitud_invalida"
    message = "La solicitud no es válida."


class FotosNoDisponibles(ErrorFoto):
    status = 503
    code = "fotos_no_disponibles"
    message = "Las fotos no están disponibles en este momento."


class SinFoto(ErrorFoto):
    status = 404
    code = "sin_foto"
    message = "No hay foto."


class FotoIdEnUso(ErrorFoto):
    status = 409
    code = "foto_id_en_uso"
    message = "Ese identificador de foto ya se usó para otra cosa."


class FotoExistente(ErrorFoto):
    status = 409
    code = "foto_existente"
    message = "Esta verificación ya tiene foto."


class VerificacionNoEncontrada(ErrorFoto):
    status = 404
    code = "no_encontrado"
    message = "La verificación no existe."


class SesionCerrada(ErrorFoto):
    status = 409
    code = "sesion_cerrada"
    message = "La sesión ya se cerró: no se pueden agregar fotos a sus verificaciones."


class NoEsTuVerificacion(ErrorFoto):
    status = 403
    code = "prohibido"
    message = "Solo quien hizo la verificación o un admin puede agregarle una foto."


ERRORES = (FotosNoDisponibles, SinFoto, FotoIdEnUso, FotoExistente)


@dataclass(frozen=True)
class Subida:
    foto: Foto
    creada: bool


def clave(tenant_id: uuid.UUID, foto_id: uuid.UUID, tamano: str = "completa") -> str:
    sufijo = "_mini" if tamano == "mini" else ""
    return f"{tenant_id}/{foto_id}{sufijo}.jpg"


def vista(foto: Foto) -> dict[str, object]:
    return {
        "id": str(foto.id),
        "creada_en": foto.creada_en.isoformat(),
        "ancho": foto.ancho,
        "alto": foto.alto,
    }


def _requerir(almacen: Almacen | None) -> Almacen:
    if almacen is None:
        raise FotosNoDisponibles()
    return almacen


def _al_terminar(session: Session, al_confirmar: Callable[[], None] | None, al_revertir=None):
    if al_confirmar is not None:
        event.listen(session, "after_commit", lambda _s: al_confirmar(), once=True)
    if al_revertir is not None:
        event.listen(session, "after_rollback", lambda _s: al_revertir(), once=True)


def _borrar(almacen: Almacen, tenant_id: uuid.UUID, foto_id: uuid.UUID) -> None:
    for tamano in TAMANOS:
        try:
            almacen.borrar(clave(tenant_id, foto_id, tamano))
        except Exception:  # noqa: BLE001 - mejor esfuerzo: queda un objeto huérfano
            logger.warning("No se pudo borrar una imagen del almacenamiento (queda huérfana).")


def _guardar(
    session: Session, almacen: Almacen, tenant_id: uuid.UUID, foto_id: uuid.UUID, datos: bytes
) -> imagen.Procesada:
    procesada = imagen.procesar(datos)
    almacen.guardar(clave(tenant_id, foto_id), procesada.completa, TIPO)
    almacen.guardar(clave(tenant_id, foto_id, "mini"), procesada.mini, TIPO)
    # Si la transacción no se confirma, no deben quedar imágenes sin fila.
    _al_terminar(session, None, lambda: _borrar(almacen, tenant_id, foto_id))
    return procesada


def principal(session: Session, activo_id: uuid.UUID) -> Foto | None:
    return session.scalars(
        select(Foto).where(
            Foto.activo_id == activo_id,
            Foto.verificacion_id.is_(None),
            Foto.retirada_en.is_(None),
        )
    ).one_or_none()


def _bloquear_activo(session: Session, activo_id: uuid.UUID) -> Activo:
    activo = session.scalars(
        select(Activo)
        .where(Activo.id == activo_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    if activo is None:
        raise activos_service.NoEncontrado()
    return activo


def _retirar(session: Session, foto: Foto, usuario_id: uuid.UUID) -> None:
    foto.retirada_en = func.now()  # type: ignore[assignment]
    foto.retirada_por = usuario_id
    session.flush()


def _insertar(session: Session, foto: Foto) -> None:
    """Inserta la fila; un ``id`` que ya existe en otro tenant (la RLS no lo deja ver)
    choca con la clave primaria: ``409 foto_id_en_uso``, sin revelar nada más."""
    try:
        with session.begin_nested():
            session.add(foto)
            session.flush()
    except IntegrityError:
        raise FotoIdEnUso() from None


def _evento(session: Session, activo: Activo, tipo: str, datos: dict, usuario_id: uuid.UUID):
    session.add(ActivoEvento(activo_id=activo.id, tipo=tipo, datos=datos, usuario_id=usuario_id))
    session.flush()


def subir_principal(
    session: Session,
    almacen: Almacen | None,
    *,
    tenant_id: uuid.UUID,
    activo_id: uuid.UUID,
    foto_id: uuid.UUID,
    datos: bytes,
    usuario_id: uuid.UUID,
) -> Subida:
    """Crea o cambia la foto principal (R1, R2, R4; Q1 B, Q2 B)."""
    almacen = _requerir(almacen)
    activo = _bloquear_activo(session, activo_id)
    previa = session.get(Foto, foto_id)
    if previa is not None:
        if previa.activo_id == activo_id and previa.verificacion_id is None:
            return Subida(previa, creada=False)
        raise FotoIdEnUso()
    if activo.estado == "dado_de_baja":
        raise ActivoDadoDeBaja()
    procesada = _guardar(session, almacen, tenant_id, foto_id, datos)
    anterior = principal(session, activo_id)
    if anterior is not None:
        _retirar(session, anterior, usuario_id)
        anterior_id = anterior.id
        _al_terminar(session, lambda: _borrar(almacen, tenant_id, anterior_id))
    foto = Foto(
        id=foto_id,
        activo_id=activo_id,
        verificacion_id=None,
        clave=clave(tenant_id, foto_id),
        bytes=len(procesada.completa),
        ancho=procesada.ancho,
        alto=procesada.alto,
        subida_por=usuario_id,
    )
    _insertar(session, foto)
    if anterior is None:
        _evento(session, activo, "foto_agregada", {"foto_id": str(foto_id)}, usuario_id)
    else:
        datos_evento = {"antes": str(anterior.id), "despues": str(foto_id)}
        _evento(session, activo, "foto_cambiada", datos_evento, usuario_id)
    return Subida(foto, creada=True)


def quitar_principal(
    session: Session,
    almacen: Almacen | None,
    *,
    tenant_id: uuid.UUID,
    activo_id: uuid.UUID,
    usuario_id: uuid.UUID,
) -> None:
    """Quita la foto principal: la fila queda retirada y la imagen se borra (Q2 B)."""
    almacen = _requerir(almacen)
    activo = _bloquear_activo(session, activo_id)
    anterior = principal(session, activo_id)
    if anterior is None:
        raise SinFoto()
    _retirar(session, anterior, usuario_id)
    anterior_id = anterior.id
    _evento(session, activo, "foto_retirada", {"foto_id": str(anterior_id)}, usuario_id)
    _al_terminar(session, lambda: _borrar(almacen, tenant_id, anterior_id))


def subir_de_verificacion(
    session: Session,
    almacen: Almacen | None,
    *,
    tenant_id: uuid.UUID,
    sesion_id: uuid.UUID,
    verificacion_id: uuid.UUID,
    foto_id: uuid.UUID,
    datos: bytes,
    usuario_id: uuid.UUID,
    es_admin: bool,
) -> Subida:
    """Foto opcional de una verificación (R6): sesión abierta, quien verificó o un admin."""
    almacen = _requerir(almacen)
    verificacion = session.get(Verificacion, verificacion_id)
    if verificacion is None or verificacion.sesion_id != sesion_id:
        raise VerificacionNoEncontrada()
    previa = session.get(Foto, foto_id)
    if previa is not None:
        if previa.verificacion_id == verificacion_id:
            return Subida(previa, creada=False)
        raise FotoIdEnUso()
    if not es_admin and verificacion.verificado_por != usuario_id:
        raise NoEsTuVerificacion()
    sesion = session.scalars(
        select(SesionConteo).where(SesionConteo.id == sesion_id).with_for_update(read=True)
    ).one()
    if sesion.estado != "abierta":
        raise SesionCerrada()
    existente = session.scalars(
        select(Foto).where(Foto.verificacion_id == verificacion_id)
    ).one_or_none()
    if existente is not None:
        raise FotoExistente()
    procesada = _guardar(session, almacen, tenant_id, foto_id, datos)
    foto = Foto(
        id=foto_id,
        activo_id=verificacion.activo_id,
        verificacion_id=verificacion_id,
        clave=clave(tenant_id, foto_id),
        bytes=len(procesada.completa),
        ancho=procesada.ancho,
        alto=procesada.alto,
        subida_por=usuario_id,
    )
    _insertar(session, foto)
    return Subida(foto, creada=True)


def leer(session: Session, almacen: Almacen | None, foto_id: uuid.UUID, tamano: str) -> bytes:
    """Bytes JPEG de una foto vigente del tenant (R8); retirada o ajena → ``404``."""
    almacen = _requerir(almacen)
    foto = session.get(Foto, foto_id)
    if foto is None or foto.retirada_en is not None:
        raise SinFoto()
    try:
        return almacen.leer(clave(foto.tenant_id, foto.id, tamano))
    except ObjetoNoEncontrado:
        raise SinFoto() from None
