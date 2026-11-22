"""Evolución entre conteos (spec 010, T3; R5; CU-DSH-04, P22, P24; ADR-003).

Solo lee lo congelado: ``sesion_conteo`` (total registrado) y ``sesion_desglose`` (las
unidades de la sesión son la suma de sus filas por categoría, igual que en
``cierre.informe``). No usa precios, categorías ni ubicaciones actuales. Hasta las
``MAX_SESIONES`` sesiones cerradas de ``tipo=conteo`` más recientes (P22), en orden
cronológico. Una categoría sin fila en una sesión no tiene punto ahí (ausente ≠ cero).
"""

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.conteo.models import SesionConteo, SesionDesglose
from app.inicio.indicadores import porcentaje

MAX_SESIONES = 12


def _dinero(valor: Decimal) -> str:
    return str(valor.quantize(Decimal("0.01")))


def evolucion(session: Session) -> dict[str, object]:
    recientes = list(
        session.scalars(
            select(SesionConteo)
            .where(SesionConteo.estado == "cerrada", SesionConteo.tipo == "conteo")
            .order_by(SesionConteo.cerrada_en.desc(), SesionConteo.id)
            .limit(MAX_SESIONES)
        )
    )
    sesiones = list(reversed(recientes))
    filas = (
        list(
            session.scalars(
                select(SesionDesglose).where(
                    SesionDesglose.dimension == "categoria",
                    SesionDesglose.sesion_id.in_([s.id for s in sesiones]),
                )
            )
        )
        if sesiones
        else []
    )
    orden = {s.id: i for i, s in enumerate(sesiones)}
    filas.sort(key=lambda f: orden[f.sesion_id])

    unidades: dict[uuid.UUID, tuple[int, int]] = {}
    categorias: dict[uuid.UUID | None, dict[str, object]] = {}
    for f in filas:
        reg, enc = unidades.get(f.sesion_id, (0, 0))
        unidades[f.sesion_id] = (reg + f.unidades_registrado, enc + f.unidades_encontrado)
        # El CHECK de la 0011 garantiza categoria_id en dimension='categoria'.
        categoria = categorias.setdefault(f.categoria_id, {"puntos": []})  # type: ignore[arg-type]
        categoria["etiqueta"] = f.etiqueta  # la de la sesión más reciente queda al final
        categoria["puntos"].append(  # type: ignore[union-attr]
            {
                "sesion_id": str(f.sesion_id),
                "total_registrado": _dinero(f.total_registrado),
                "unidades_registrado": f.unidades_registrado,
            }
        )

    puntos = []
    for s in sesiones:
        registradas, encontradas = unidades.get(s.id, (0, 0))
        puntos.append(
            {
                "sesion": {
                    "id": str(s.id),
                    "nombre": s.nombre,
                    "fecha_corte": s.fecha_corte.isoformat(),
                    "cerrada_en": s.cerrada_en.isoformat() if s.cerrada_en else None,
                },
                "total_registrado": _dinero(s.total_registrado or Decimal(0)),
                "unidades_registrado": registradas,
                "unidades_encontrado": encontradas,
                "porcentaje_encontrado": porcentaje(encontradas, registradas),
            }
        )
    por_categoria = sorted(
        (
            {"categoria_id": str(cid), "etiqueta": c["etiqueta"], "puntos": c["puntos"]}
            for cid, c in categorias.items()
        ),
        key=lambda c: str(c["etiqueta"]).casefold(),
    )
    return {"sesiones": puntos, "por_categoria": por_categoria}
