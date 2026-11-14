"""Valor actual del inventario (spec 008, T3; R7 de docs/03, P15/E2; CU-INF-02).

Consulta **en vivo** de ``activo``: cuentan ``activo`` y ``en_reparacion`` (también en
el universo del cierre); los ``dado_de_baja`` no. No es un informe: nunca lee el desglose
congelado de una sesión ni se mezcla con él. Solo admin (P13). Dinero en ``Decimal``.
"""

from datetime import UTC, datetime
from decimal import Decimal

from flask import Blueprint, jsonify
from flask.typing import ResponseReturnValue
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, aliased

from app.activos.models import Activo
from app.auth.decorators import current_session, require_role
from app.catalogo.models import Categoria, Ubicacion

bp = Blueprint("valor", __name__)

ESTADOS_QUE_CUENTAN = ("activo", "en_reparacion")
CERO = Decimal("0.00")


def _dinero(valor: Decimal | None) -> str:
    return str((valor or CERO).quantize(Decimal("0.01")))


def valor_actual(session: Session) -> dict[str, object]:
    vigentes = Activo.estado.in_(ESTADOS_QUE_CUENTAN)
    en_reparacion = Activo.estado == "en_reparacion"
    total, unidades, valor_rep, unidades_rep = session.execute(
        select(
            func.coalesce(func.sum(Activo.precio_compra), 0),
            func.count(),
            func.coalesce(func.sum(case((en_reparacion, Activo.precio_compra), else_=0)), 0),
            func.count().filter(en_reparacion),
        ).where(vigentes)
    ).one()
    por_categoria = session.execute(
        select(Categoria.id, Categoria.nombre, func.sum(Activo.precio_compra), func.count())
        .join(Categoria, Categoria.id == Activo.categoria_id)
        .where(vigentes)
        .group_by(Categoria.id, Categoria.nombre)
        .order_by(func.lower(Categoria.nombre))
    ).all()
    lugar, padre = aliased(Ubicacion), aliased(Ubicacion)
    ruta = case(
        ((lugar.tipo == "box") & padre.nombre.is_not(None), padre.nombre + " › " + lugar.nombre),
        else_=lugar.nombre,
    )
    por_ubicacion = session.execute(
        select(lugar.id, ruta, func.sum(Activo.precio_compra), func.count())
        .join(lugar, lugar.id == Activo.ubicacion_id)
        .outerjoin(padre, padre.id == lugar.padre_id)
        .where(vigentes)
        .group_by(lugar.id, ruta)
        .order_by(func.lower(ruta))
    ).all()

    def filas(datos) -> list[dict[str, object]]:
        return [
            {"id": str(i), "etiqueta": etiqueta, "valor": _dinero(v), "unidades": n}
            for i, etiqueta, v, n in datos
        ]

    return {
        "total": _dinero(total),
        "unidades": unidades,
        "en_reparacion": {"valor": _dinero(valor_rep), "unidades": unidades_rep},
        "por_categoria": filas(por_categoria),
        "por_ubicacion": filas(por_ubicacion),
        "calculado_en": datetime.now(UTC).isoformat(),
    }


@bp.get("/valor-actual")
@require_role("admin")
def ver_valor_actual() -> ResponseReturnValue:
    return jsonify(valor_actual(current_session()))
