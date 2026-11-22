"""Discrepancias y pendientes de una sesión (spec 007, T2–T4; R1–R9, Q1–Q4; plan.md §3).

Una **discrepancia** es la verificación vigente de un activo en la sesión (mayor
``seq``, R3) cuya ubicación encontrada difiere de la esperada. No hay tabla propia: su
resolución es un evento del activo con el ``verificacion_id``:

- ``ubicacion_cambiada`` (aplicada: el activo se movió a donde se vio) o
- ``discrepancia_descartada`` (el activo no se mueve; Q2).

Un índice único de la 0010 garantiza una sola resolución por verificación (R4). Sin
resolución, el estado se deriva de la ubicación actual: ``pendiente`` si sigue en la
esperada, ``desfasada`` si ya está en otra. La verificación y la sesión no se tocan
(inmutables); por eso se resuelven también en sesiones cerradas (Q1) sin cambiar el
informe, que usa la ubicación esperada (P20).

Aplicar y descartar van en lote (Q3): cada verificación en su savepoint, con su
resultado. El activo se toma ``FOR UPDATE`` **antes** de mirar si ya está resuelta, así
dos admins a la vez dejan una aplicada y otra ``ya_resuelta``.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import and_, exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.activos.models import Activo, ActivoEvento
from app.activos.service import _ruta
from app.catalogo.models import Categoria, Ubicacion
from app.conteo.models import SesionConteo, Verificacion
from app.conteo.service import ESTADOS_QUE_CUENTAN, ErrorConteo, NoEncontrado, _autor

UNIQUE_VIOLATION = "23505"
RESOLUCIONES = ("ubicacion_cambiada", "discrepancia_descartada")
FILTROS = ("por_resolver", "resueltas", "todas")
MAX_LOTE = 100
POR_PAGINA = 50


def _sesion(session: Session, sesion_id: uuid.UUID) -> SesionConteo:
    sesion = session.get(SesionConteo, sesion_id)
    if sesion is None:
        raise NoEncontrado()
    return sesion


def _ubicacion(session: Session, ubicacion_id: uuid.UUID) -> dict[str, str]:
    ubicacion = session.get(Ubicacion, ubicacion_id)
    return {"id": str(ubicacion_id), "ruta": _ruta(session, ubicacion) if ubicacion else ""}


def _vigentes(sesion_id: uuid.UUID):
    """Subconsulta: la verificación de mayor ``seq`` de cada activo en la sesión (R3)."""
    orden = func.row_number().over(
        partition_by=Verificacion.activo_id, order_by=Verificacion.seq.desc()
    )
    return (
        select(Verificacion.id.label("id"), orden.label("orden"))
        .where(Verificacion.sesion_id == sesion_id)
        .subquery()
    )


def _resolucion(session: Session, verificacion_id: uuid.UUID) -> ActivoEvento | None:
    return session.scalars(
        select(ActivoEvento).where(
            ActivoEvento.verificacion_id == verificacion_id,
            ActivoEvento.tipo.in_(RESOLUCIONES),
        )
    ).one_or_none()


# --- Lista (T2; R1, CU-DIS-01) --------------------------------------------------------------


def listar(session: Session, sesion_id: uuid.UUID, filtro: object) -> list[dict[str, object]]:
    filtro = filtro if filtro is not None else "por_resolver"
    if filtro not in FILTROS:
        raise ErrorConteo()
    _sesion(session, sesion_id)
    vigentes = _vigentes(sesion_id)
    filas = session.execute(
        select(Verificacion, Activo)
        .join(vigentes, and_(vigentes.c.id == Verificacion.id, vigentes.c.orden == 1))
        .join(Activo, Activo.id == Verificacion.activo_id)
        .where(Verificacion.ubicacion_encontrada_id != Verificacion.ubicacion_esperada_id)
        .order_by(Verificacion.recibido_en.desc(), Verificacion.id)
    ).all()
    salida = []
    for verificacion, activo in filas:
        resolucion = _resolucion(session, verificacion.id)
        if resolucion is not None:
            estado = "aplicada" if resolucion.tipo == "ubicacion_cambiada" else "descartada"
        elif activo.ubicacion_id == verificacion.ubicacion_esperada_id:
            estado = "pendiente"
        else:
            estado = "desfasada"
        resuelta = estado in ("aplicada", "descartada")
        if (filtro == "por_resolver" and resuelta) or (filtro == "resueltas" and not resuelta):
            continue
        salida.append(
            {
                "verificacion_id": str(verificacion.id),
                "activo": {
                    "id": str(activo.id),
                    "codigo": activo.codigo,
                    "nombre": activo.nombre,
                    "estado": activo.estado,
                },
                "ubicacion_esperada": _ubicacion(session, verificacion.ubicacion_esperada_id),
                "ubicacion_encontrada": _ubicacion(session, verificacion.ubicacion_encontrada_id),
                "ubicacion_actual": _ubicacion(session, activo.ubicacion_id),
                "verificado_por": _autor(session, verificacion.verificado_por),
                "recibido_en": verificacion.recibido_en.isoformat(),
                "estado": estado,
                "resolucion": (
                    {
                        "tipo": estado,
                        "por": _autor(session, resolucion.usuario_id),
                        "en": resolucion.ocurrido_en.isoformat(),
                    }
                    if resolucion is not None
                    else None
                ),
            }
        )
    return salida


# --- Aplicar y descartar (T3; R2–R7, CU-DIS-02) --------------------------------------------


def datos_de_lote(body: dict[str, object], *, con_desfase: bool) -> tuple[list[uuid.UUID], bool]:
    permitidas = {"verificaciones", "confirmar_desfase"} if con_desfase else {"verificaciones"}
    if not set(body) <= permitidas:
        raise ErrorConteo()
    ids = body.get("verificaciones")
    if not isinstance(ids, list) or not 1 <= len(ids) <= MAX_LOTE:
        raise ErrorConteo("Elige entre 1 y 100 diferencias.")
    salida = []
    for valor in ids:
        if not isinstance(valor, str):
            raise ErrorConteo()
        try:
            salida.append(uuid.UUID(valor))
        except ValueError:
            raise ErrorConteo() from None
    if len(set(salida)) != len(salida):
        raise ErrorConteo()
    confirmar = body.get("confirmar_desfase", False)
    if not isinstance(confirmar, bool):
        raise ErrorConteo()
    return salida, confirmar


@dataclass(frozen=True)
class Resultado:
    verificacion_id: uuid.UUID
    resultado: str
    activo: Activo | None = None


def _es_vigente(session: Session, v: Verificacion) -> bool:
    ultima = session.scalar(
        select(Verificacion.id)
        .where(Verificacion.sesion_id == v.sesion_id, Verificacion.activo_id == v.activo_id)
        .order_by(Verificacion.seq.desc())
        .limit(1)
    )
    return ultima == v.id and v.ubicacion_encontrada_id != v.ubicacion_esperada_id


def _resolver_una(
    session: Session,
    sesion: SesionConteo,
    verificacion_id: uuid.UUID,
    *,
    aplicar: bool,
    confirmar_desfase: bool,
    usuario_id: uuid.UUID,
) -> Resultado:
    v = session.scalars(
        select(Verificacion).where(
            Verificacion.id == verificacion_id, Verificacion.sesion_id == sesion.id
        )
    ).one_or_none()
    if v is None:
        return Resultado(verificacion_id, "no_encontrada")
    activo = session.scalars(
        select(Activo)
        .where(Activo.id == v.activo_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    if _resolucion(session, v.id) is not None:
        return Resultado(verificacion_id, "ya_resuelta", activo)
    if not _es_vigente(session, v):
        return Resultado(verificacion_id, "ya_no_es_discrepancia", activo)
    esperada = _ubicacion(session, v.ubicacion_esperada_id)
    encontrada = _ubicacion(session, v.ubicacion_encontrada_id)

    if not aplicar:
        evento = ActivoEvento(
            activo_id=activo.id,
            tipo="discrepancia_descartada",
            usuario_id=usuario_id,
            sesion_id=sesion.id,
            verificacion_id=v.id,
            datos={"esperada": esperada, "encontrada": encontrada, "sesion": sesion.nombre},
        )
        session.add(evento)
        session.flush()
        return Resultado(verificacion_id, "descartada", activo)

    if activo.estado == "dado_de_baja":
        return Resultado(verificacion_id, "dado_de_baja", activo)
    if activo.ubicacion_id != v.ubicacion_esperada_id:
        if activo.ubicacion_id == v.ubicacion_encontrada_id:
            return Resultado(verificacion_id, "ya_en_la_encontrada", activo)
        if not confirmar_desfase:
            return Resultado(verificacion_id, "desfasada", activo)
    destino = session.scalars(
        select(Ubicacion)
        .where(Ubicacion.id == v.ubicacion_encontrada_id)
        .with_for_update(read=True)
    ).one_or_none()
    if destino is None or destino.tipo == "sede" or not destino.activa:
        return Resultado(verificacion_id, "ubicacion_invalida", activo)

    antes = _ubicacion(session, activo.ubicacion_id)
    activo.ubicacion_id = destino.id
    activo.row_version = activo.row_version + 1
    activo.actualizado_en = func.now()  # type: ignore[assignment]
    session.flush()
    session.add(
        ActivoEvento(
            activo_id=activo.id,
            tipo="ubicacion_cambiada",
            usuario_id=usuario_id,
            sesion_id=sesion.id,
            verificacion_id=v.id,
            datos={
                "antes": antes,
                "despues": encontrada,
                "origen": "discrepancia",
                "sesion": sesion.nombre,
            },
        )
    )
    session.flush()
    session.refresh(activo)
    return Resultado(verificacion_id, "aplicada", activo)


def resolver(
    session: Session,
    sesion_id: uuid.UUID,
    ids: list[uuid.UUID],
    *,
    aplicar: bool,
    confirmar_desfase: bool,
    usuario_id: uuid.UUID,
) -> list[Resultado]:
    sesion = _sesion(session, sesion_id)
    salida = []
    for verificacion_id in ids:
        try:
            with session.begin_nested():
                resultado = _resolver_una(
                    session,
                    sesion,
                    verificacion_id,
                    aplicar=aplicar,
                    confirmar_desfase=confirmar_desfase,
                    usuario_id=usuario_id,
                )
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) != UNIQUE_VIOLATION:
                raise
            resultado = Resultado(verificacion_id, "ya_resuelta")
        salida.append(resultado)
    return salida


def vista_resultado(session: Session, r: Resultado) -> dict[str, object]:
    datos: dict[str, object] = {"verificacion_id": str(r.verificacion_id), "resultado": r.resultado}
    if r.activo is not None:
        datos["activo"] = {
            "id": str(r.activo.id),
            "codigo": r.activo.codigo,
            "nombre": r.activo.nombre,
            "ubicacion": _ubicacion(session, r.activo.ubicacion_id),
        }
    return datos


# --- Pendientes (T4; R8, CU-VER-04) ---------------------------------------------------------


def pendientes(
    session: Session, sesion_id: uuid.UUID, *, ubicacion_id: object, pagina: object
) -> dict[str, object]:
    _sesion(session, sesion_id)
    try:
        numero = int(pagina) if pagina is not None else 1
    except (TypeError, ValueError):
        raise ErrorConteo() from None
    if not 1 <= numero <= 10_000:
        raise ErrorConteo()
    filtro = select(Activo).where(
        Activo.estado.in_(ESTADOS_QUE_CUENTAN),
        ~exists().where(
            and_(Verificacion.sesion_id == sesion_id, Verificacion.activo_id == Activo.id)
        ),
    )
    if ubicacion_id is not None:
        if not isinstance(ubicacion_id, str):
            raise ErrorConteo()
        try:
            filtro = filtro.where(Activo.ubicacion_id == uuid.UUID(ubicacion_id))
        except ValueError:
            raise ErrorConteo() from None
    total = session.scalar(select(func.count()).select_from(filtro.subquery()))
    categoria = aliased(Categoria)
    filas = session.execute(
        filtro.add_columns(categoria.nombre)
        .join(categoria, categoria.id == Activo.categoria_id)
        .order_by(Activo.ubicacion_id, Activo.codigo)
        .limit(POR_PAGINA)
        .offset((numero - 1) * POR_PAGINA)
    ).all()
    return {
        "activos": [
            {
                "id": str(a.id),
                "codigo": a.codigo,
                "nombre": a.nombre,
                "categoria": {"id": str(a.categoria_id), "nombre": nombre_categoria},
                "ubicacion": _ubicacion(session, a.ubicacion_id),
                "estado": a.estado,
            }
            for a, nombre_categoria in filas
        ],
        "total": int(total or 0),
        "pagina": numero,
        "por_pagina": POR_PAGINA,
    }
