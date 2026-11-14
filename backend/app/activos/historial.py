"""Historial de un activo (spec 005, T4; R8, CU-HIS-01, P13; plan.md §4).

Línea de tiempo por ``seq`` descendente (no por reloj), 50 eventos por página con un
cursor ``antes_de``. El filtro por rol vive aquí, en el servidor:

- Al contador se le omiten los ``precio_cambiado`` **en la consulta** (así cada página
  tiene 50 eventos que sí puede ver) y se le quita toda clave de precio de los demás
  (``creado`` e ``importado`` guardan ``precio_compra``).
- El autor se resuelve con su membresía del tenant: solo nombres de este tenant.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.activos.models import ActivoEvento
from app.activos.service import ErrorActivo, obtener
from app.auth.models import Membresia, Usuario

POR_PAGINA = 50
MAX_SEQ = 2**63 - 1


@dataclass(frozen=True)
class Pagina:
    eventos: list[dict[str, object]]
    siguiente: int | None


def _cursor(valor: object) -> int | None:
    if valor is None:
        return None
    if not isinstance(valor, str) or not (valor.isascii() and valor.isdigit()):
        raise ErrorActivo()
    numero = int(valor)
    if numero < 1 or numero > MAX_SEQ:
        raise ErrorActivo()
    return numero


def _sin_precio(valor: object) -> object:
    """Copia de ``valor`` sin ninguna clave que hable de precio (P13, defensivo)."""
    if isinstance(valor, dict):
        return {k: _sin_precio(v) for k, v in valor.items() if "precio" not in k}
    if isinstance(valor, list):
        return [_sin_precio(v) for v in valor]
    return valor


def _autores(session: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    filas = session.execute(
        select(Usuario.id, Usuario.nombre)
        .join(Membresia, Membresia.usuario_id == Usuario.id)
        .where(Usuario.id.in_(ids))
    )
    return {fila.id: fila.nombre for fila in filas}


def leer(session: Session, activo_id: uuid.UUID, *, antes_de: object, con_precio: bool) -> Pagina:
    cursor = _cursor(antes_de)
    obtener(session, activo_id)  # 404 si no existe en este tenant
    consulta = select(ActivoEvento).where(ActivoEvento.activo_id == activo_id)
    if not con_precio:
        consulta = consulta.where(ActivoEvento.tipo != "precio_cambiado")
    if cursor is not None:
        consulta = consulta.where(ActivoEvento.seq < cursor)
    filas = list(session.scalars(consulta.order_by(ActivoEvento.seq.desc()).limit(POR_PAGINA + 1)))
    hay_mas = len(filas) > POR_PAGINA
    filas = filas[:POR_PAGINA]
    nombres = _autores(session, {f.usuario_id for f in filas})
    eventos = [
        {
            "seq": f.seq,
            "tipo": f.tipo,
            "ocurrido_en": f.ocurrido_en.isoformat(),
            "autor": {"id": str(f.usuario_id), "nombre": nombres.get(f.usuario_id, "")},
            "datos": f.datos if con_precio else _sin_precio(f.datos),
        }
        for f in filas
    ]
    return Pagina(eventos=eventos, siguiente=filas[-1].seq if hay_mas else None)
