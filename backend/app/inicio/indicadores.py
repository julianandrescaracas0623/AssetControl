"""Indicadores del Inicio (spec 010, T1; R1, R2, R6; CU-DSH-01, P13, P26).

Cada cifra sale de la función que ya la calcula en su módulo (avance, valor actual,
discrepancias, informe), sin recalcular nada aquí:

- Ambos roles: activos hoy (``activo`` + ``en_reparacion``, R7) y la sesión abierta con
  su avance (porcentaje en texto con un decimal).
- Solo admin (las claves no existen para el contador, P13): valor actual (vivo, R7),
  discrepancias por resolver y «dañados o en reparación» de la **sesión de referencia**
  (la abierta o, sin ella, la última cerrada; P26) y las tres cifras del último informe
  cerrado de ``tipo=conteo`` (congeladas, ADR-003).
"""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.activos.models import Activo
from app.activos.valor import valor_actual
from app.conteo import cierre, discrepancias, service
from app.conteo.models import SesionConteo, Verificacion
from app.conteo.service import ESTADOS_QUE_CUENTAN


def porcentaje(parte: int, total: int) -> str:
    """``1, 3`` → ``"33.3"``: un decimal, redondeo half-up, con ``Decimal`` (P24)."""
    if total == 0:
        return "0.0"
    return str((Decimal(parte) * 100 / Decimal(total)).quantize(Decimal("0.1"), ROUND_HALF_UP))


def _ultima_cerrada(session: Session) -> SesionConteo | None:
    return session.scalars(
        select(SesionConteo)
        .where(SesionConteo.estado == "cerrada", SesionConteo.tipo == "conteo")
        .order_by(SesionConteo.cerrada_en.desc(), SesionConteo.id)
        .limit(1)
    ).one_or_none()


def _ref(sesion: SesionConteo) -> dict[str, str]:
    return {"id": str(sesion.id), "nombre": sesion.nombre}


def _activos_hoy(session: Session) -> dict[str, int]:
    unidades, en_reparacion = session.execute(
        select(func.count(), func.count().filter(Activo.estado == "en_reparacion")).where(
            Activo.estado.in_(ESTADOS_QUE_CUENTAN)
        )
    ).one()
    return {"unidades": unidades, "en_reparacion": en_reparacion}


def _sesion_abierta(session: Session, sesion: SesionConteo | None) -> dict[str, object] | None:
    if sesion is None:
        return None
    avance = service.avance(session, sesion)
    total, verificados = int(avance["total"]), int(avance["verificados"])  # type: ignore[call-overload]
    return {
        **_ref(sesion),
        "fecha_corte": sesion.fecha_corte.isoformat(),
        "avance": {
            "total": total,
            "verificados": verificados,
            "pendientes": total - verificados,
            "porcentaje": porcentaje(verificados, total),
        },
    }


def _danados(session: Session, referencia: SesionConteo | None) -> dict[str, object]:
    """En reparación (estado vigente) ∪ dañados en su verificación vigente de la sesión
    de referencia; solo activos que cuentan hoy (los dados de baja no)."""
    en_reparacion = {
        fila for fila in session.scalars(select(Activo.id).where(Activo.estado == "en_reparacion"))
    }
    danados: set = set()
    if referencia is not None:
        vigentes = discrepancias._vigentes(referencia.id)
        danados = set(
            session.scalars(
                select(Verificacion.activo_id)
                .join(vigentes, and_(vigentes.c.id == Verificacion.id, vigentes.c.orden == 1))
                .join(Activo, Activo.id == Verificacion.activo_id)
                .where(
                    Verificacion.estado_fisico == "danado",
                    Activo.estado.in_(ESTADOS_QUE_CUENTAN),
                )
            )
        )
    return {
        "total": len(en_reparacion | danados),
        "en_reparacion": len(en_reparacion),
        "danados": len(danados),
        "sesion": _ref(referencia) if referencia is not None else None,
    }


def indicadores(session: Session, rol: str) -> dict[str, object]:
    abierta = service.abierta(session)
    datos: dict[str, object] = {
        "activos_hoy": _activos_hoy(session),
        "sesion_abierta": _sesion_abierta(session, abierta),
    }
    if rol != "admin":
        return datos

    ultima = _ultima_cerrada(session)
    referencia = abierta or ultima
    valor = valor_actual(session)
    datos["valor_actual"] = {
        "total": valor["total"],
        "unidades": valor["unidades"],
        "calculado_en": valor["calculado_en"],
    }
    datos["discrepancias"] = (
        {
            "por_resolver": len(discrepancias.listar(session, referencia.id, "por_resolver")),
            "sesion": _ref(referencia),
        }
        if referencia is not None
        else None
    )
    datos["danados"] = _danados(session, referencia)
    if ultima is None:
        datos["ultimo_informe"] = None
    else:
        informe = cierre.informe(session, ultima)
        datos["ultimo_informe"] = {"sesion": informe["sesion"], "totales": informe["totales"]}
    return datos
