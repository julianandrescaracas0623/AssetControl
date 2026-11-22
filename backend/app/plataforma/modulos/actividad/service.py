"""Actividad de la consola: lectura paginada de la auditoría (spec 017, T6).

``spec.md`` R32, R34; A18; CU-08. Todo corre en la ``plataforma_session`` de
``require_desarrollador`` y pasa por ``acceso.plataforma_listar_auditoria`` (0028), que
une los nombres de ``desarrollador`` y ``tenant`` al consultar. Solo lectura: no escribe
nada, tampoco auditoría.

Consulta (todo opcional; cualquier otro parámetro, uno repetido o un valor fuera de
formato -> ``400 solicitud_invalida``):

- ``empresa_id``: UUID canónico (minúsculas con guiones), distinto del UUID nulo.
- ``accion``: una de la lista cerrada de R33 (``app.plataforma.auditoria.ACCIONES``).
- ``desde`` / ``hasta``: fechas ``AAAA-MM-DD``, las dos inclusive, en la hora de Colombia
  (UTC−5 fijo, como los informes: ``app.conteo.exportar``); ``desde`` > ``hasta`` es
  ``400``.
- ``limite``: de 1 a ``PAGINA_MAX`` (100); por defecto ``PAGINA`` (50).
- ``cursor``: el ``siguiente`` opaco de la página anterior.

Respuesta: ``{actividad: [...], siguiente}``; cada registro lleva exactamente ``id``,
``fecha`` (ISO 8601 en UTC), ``accion``, ``resultado``, ``desarrollador_nombre``
(«Operador» si lo hizo el operador por CLI), ``empresa_id`` y ``empresa_nombre`` (nulos
si la acción no es de una empresa) y ``objeto_id``. Nunca correos, IP, hashes ni el id del
desarrollador. ``siguiente`` es nulo en la última página: se pide una fila de más para
saberlo. El cursor es ``<microsegundos desde 1970 en UTC>_<id>`` del último registro de la
página: estable frente a inserciones (lo nuevo es más reciente y queda antes del cursor).
"""

import re
import uuid
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db import (
    FiltroAuditoria,
    PlataformaFuncionError,
    RegistroAuditoria,
    plataforma_listar_auditoria,
)
from app.plataforma.auditoria import ACCIONES

PAGINA = 50
PAGINA_MAX = 100
PARAMETROS = frozenset({"empresa_id", "accion", "desde", "hasta", "cursor", "limite"})
OPERADOR = "Operador"
# Colombia no tiene horario de verano: UTC−5 fijo (igual que app.conteo.exportar).
HORA_COLOMBIA = timezone(timedelta(hours=-5), "COT")

_EPOCA = datetime(1970, 1, 1, tzinfo=UTC)
_MICROSEGUNDO = timedelta(microseconds=1)
_UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_FECHA = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_LIMITE = re.compile(r"[1-9][0-9]{0,2}")
_CURSOR = re.compile(rf"([0-9]{{1,17}})_({_UUID})")
_UUID_NULO = uuid.UUID(int=0)


class ErrorActividad(Exception):
    status = 400
    code = "solicitud_invalida"
    message = "La consulta no es válida."

    def __init__(self) -> None:
        super().__init__(self.code)


class DesarrolladorNoAutorizado(ErrorActividad):
    """El desarrollador dejó de estar activo durante la petición: el mismo ``401``."""

    status = 401
    code = "no_autenticado"
    message = "Debes iniciar sesión."


# Códigos propios del módulo.
ERRORES = (ErrorActividad,)


# --- Consulta ------------------------------------------------------------------------------


def _empresa(valor: str) -> uuid.UUID:
    try:
        parsed = uuid.UUID(valor)
    except ValueError:
        raise ErrorActividad() from None
    if str(parsed) != valor or parsed == _UUID_NULO:
        raise ErrorActividad()
    return parsed


def _fecha(valor: str) -> date:
    if not _FECHA.fullmatch(valor):
        raise ErrorActividad()
    try:
        return date.fromisoformat(valor)
    except ValueError:
        raise ErrorActividad() from None


def _inicio_del_dia(dia: date) -> datetime:
    """00:00 de ``dia`` en Colombia (como instante con zona)."""
    return datetime(dia.year, dia.month, dia.day, tzinfo=HORA_COLOMBIA)


def _cursor(valor: str) -> tuple[datetime, uuid.UUID]:
    match = _CURSOR.fullmatch(valor)
    if match is None:
        raise ErrorActividad()
    try:
        fecha = _EPOCA + timedelta(microseconds=int(match.group(1)))
    except OverflowError:
        raise ErrorActividad() from None
    return fecha, uuid.UUID(match.group(2))


def codificar_cursor(registro: RegistroAuditoria) -> str:
    microsegundos = (registro.creado_en - _EPOCA) // _MICROSEGUNDO
    return f"{microsegundos}_{registro.id}"


def consulta(args: Any) -> FiltroAuditoria:
    """Valida la consulta (``request.args``) y devuelve el filtro de la función."""
    claves = set(args.keys())
    if not claves <= PARAMETROS or any(len(args.getlist(clave)) != 1 for clave in claves):
        raise ErrorActividad()
    tenant_id = _empresa(args["empresa_id"]) if "empresa_id" in claves else None
    accion = args.get("accion")
    if accion is not None and accion not in ACCIONES:
        raise ErrorActividad()
    desde = _fecha(args["desde"]) if "desde" in claves else None
    hasta = _fecha(args["hasta"]) if "hasta" in claves else None
    if desde is not None and hasta is not None and desde > hasta:
        raise ErrorActividad()
    # Inclusive: hasta el inicio del día siguiente (exclusivo en la función). 9999-12-31 no
    # tiene día siguiente en Python: es 400, no 500.
    try:
        hasta_siguiente = None if hasta is None else hasta + timedelta(days=1)
    except OverflowError:
        raise ErrorActividad() from None
    limite = PAGINA
    if "limite" in claves:
        if not _LIMITE.fullmatch(args["limite"]):
            raise ErrorActividad()
        limite = int(args["limite"])
        if limite > PAGINA_MAX:
            raise ErrorActividad()
    cursor = _cursor(args["cursor"]) if "cursor" in claves else None
    return FiltroAuditoria(
        tenant_id=tenant_id,
        accion=accion,
        desde=None if desde is None else _inicio_del_dia(desde),
        hasta=None if hasta_siguiente is None else _inicio_del_dia(hasta_siguiente),
        cursor=cursor,
        limite=limite,
    )


# --- Lista (R32) ---------------------------------------------------------------------------


def _registro_json(registro: RegistroAuditoria) -> dict[str, object]:
    return {
        "id": str(registro.id),
        "fecha": registro.creado_en.astimezone(UTC).isoformat(),
        "accion": registro.accion,
        "resultado": registro.resultado,
        "desarrollador_nombre": registro.desarrollador_nombre or OPERADOR,
        "empresa_id": None if registro.tenant_id is None else str(registro.tenant_id),
        "empresa_nombre": registro.tenant_nombre,
        "objeto_id": None if registro.objeto_id is None else str(registro.objeto_id),
    }


def listar(session: Session, filtro: FiltroAuditoria) -> dict[str, object]:
    """Una página de la auditoría y el cursor de la siguiente (nulo si no hay más)."""
    pedido = FiltroAuditoria(
        tenant_id=filtro.tenant_id,
        accion=filtro.accion,
        desde=filtro.desde,
        hasta=filtro.hasta,
        cursor=filtro.cursor,
        limite=filtro.limite + 1,  # una de más para saber si hay otra página
    )
    rechazo = None
    try:
        registros = plataforma_listar_auditoria(session, pedido)
    except PlataformaFuncionError as exc:
        if exc.codigo != "desarrollador_no_autorizado":
            raise
        rechazo = DesarrolladorNoAutorizado
    if rechazo is not None:
        # Fuera del except: sin causa ni contexto de la base.
        raise rechazo()
    pagina = registros[: filtro.limite]
    hay_mas = len(registros) > filtro.limite
    return {
        "actividad": [_registro_json(r) for r in pagina],
        "siguiente": codificar_cursor(pagina[-1]) if hay_mas else None,
    }
