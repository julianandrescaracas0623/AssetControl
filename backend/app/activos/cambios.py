"""Cambios sobre activos existentes (spec 005; R1–R7, Q1–Q3; plan.md §3).

Toda escritura sigue el mismo camino:

1. ``leer_version``: el ``If-Match`` es obligatorio (``428 falta_version``).
2. ``bloquear``: ``SELECT ... FOR UPDATE`` del activo y comparación con su
   ``row_version`` bajo el bloqueo (``412 version_desactualizada`` con el vigente). Así
   dos admins que editan a la vez no se pisan: el segundo ve la versión nueva.
3. Se calcula la diferencia; sin diferencias no se toca nada (ni versión ni eventos).
4. ``_registrar``: un solo ``UPDATE`` que sube ``row_version`` una vez y los eventos con
   ``{antes, despues}`` y autor, en la misma transacción de la vista.

Un activo ``dado_de_baja`` es de solo lectura (``409 activo_dado_de_baja``, Q1).
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.activos.dominio import parsear_precio
from app.activos.models import Activo, ActivoEvento
from app.activos.service import (
    ErrorActivo,
    NoEncontrado,
    PrecioInvalido,
    _categoria,
    _fecha,
    _texto_opcional,
    _uuid,
)
from app.catalogo.models import Categoria
from app.nombres import normalize_display_name

# Campos que el admin edita (R1): los mismos del alta; nunca el código.
TEXTOS = ("serial", "marca", "modelo", "subtipo")
EDITABLES = ("nombre", "categoria_id", "precio_compra", *TEXTOS, "fecha_compra")
# Orden de los campos dentro de ``datos_cambiados``.
DATOS = ("nombre", *TEXTOS, "fecha_compra")
MAX_VERSION_DIGITOS = 9


class FaltaVersion(ErrorActivo):
    status = 428
    code = "falta_version"
    message = "Falta la versión del activo. Recarga la ficha y vuelve a intentarlo."


class VersionDesactualizada(ErrorActivo):
    status = 412
    code = "version_desactualizada"
    message = "Alguien cambió este activo. Revisa los datos actuales y vuelve a guardar."

    def __init__(self, activo: Activo) -> None:
        super().__init__()
        self.activo = activo


class CodigoInmutable(ErrorActivo):
    code = "codigo_inmutable"
    message = "El código del sticker no se puede cambiar."


class ActivoDadoDeBaja(ErrorActivo):
    status = 409
    code = "activo_dado_de_baja"
    message = "El activo está dado de baja: solo se puede reactivar."


ERRORES = (FaltaVersion, VersionDesactualizada, CodigoInmutable, ActivoDadoDeBaja)


# --- Versión y bloqueo ------------------------------------------------------------------


def leer_version(cabecera: str | None) -> int:
    """``If-Match: "3"`` o ``3``; cualquier otra forma (débil, lista, vacía) es ``428``."""
    if cabecera is None:
        raise FaltaVersion()
    valor = cabecera.strip()
    if len(valor) >= 2 and valor[0] == valor[-1] == '"':
        valor = valor[1:-1]
    if not (valor.isascii() and valor.isdigit()) or len(valor) > MAX_VERSION_DIGITOS:
        raise FaltaVersion()
    return int(valor)


def bloquear(session: Session, activo_id: uuid.UUID, version: int) -> Activo:
    activo = session.scalars(
        select(Activo)
        .where(Activo.id == activo_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    if activo is None:
        raise NoEncontrado()
    if activo.row_version != version:
        raise VersionDesactualizada(activo)
    return activo


def _registrar(
    session: Session,
    activo: Activo,
    eventos: list[tuple[str, dict[str, object]]],
    usuario_id: uuid.UUID,
) -> None:
    activo.row_version = activo.row_version + 1
    activo.actualizado_en = func.now()  # type: ignore[assignment]
    session.flush()
    for tipo, datos in eventos:
        session.add(
            ActivoEvento(activo_id=activo.id, tipo=tipo, datos=datos, usuario_id=usuario_id)
        )
    session.flush()
    session.refresh(activo)


# --- Editar (T2; R1, R3, CU-CAT-05) -----------------------------------------------------


def edicion(body: dict[str, object]) -> dict[str, object]:
    """Valida el cuerpo de ``PATCH``: solo campos de R1, ya normalizados como en el alta."""
    if "codigo" in body:
        raise CodigoInmutable()
    if not set(body) <= set(EDITABLES):
        raise ErrorActivo()
    cambios: dict[str, object] = {}
    for campo, valor in body.items():
        if campo == "nombre":
            nombre = normalize_display_name(valor) if isinstance(valor, str) else None
            if nombre is None:
                raise ErrorActivo("El nombre es obligatorio: de 1 a 120 caracteres.")
            cambios[campo] = nombre
        elif campo == "precio_compra":
            precio = parsear_precio(valor)
            if precio is None:
                raise PrecioInvalido()
            cambios[campo] = precio
        elif campo == "categoria_id":
            cambios[campo] = _uuid(valor)
        elif campo == "fecha_compra":
            cambios[campo] = _fecha(valor)
        else:
            cambios[campo] = _texto_opcional(valor)
    return cambios


def _json(valor: object) -> object:
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    return valor


def editar(
    session: Session,
    activo_id: uuid.UUID,
    version: int,
    cambios: dict[str, object],
    usuario_id: uuid.UUID,
) -> Activo:
    activo = bloquear(session, activo_id, version)
    if activo.estado == "dado_de_baja":
        raise ActivoDadoDeBaja()

    eventos: list[tuple[str, dict[str, object]]] = []
    precio = cambios.get("precio_compra")
    if precio is not None and precio != activo.precio_compra:
        eventos.append(
            ("precio_cambiado", {"antes": str(activo.precio_compra), "despues": str(precio)})
        )
    categoria_id = cambios.get("categoria_id")
    if categoria_id is not None and categoria_id != activo.categoria_id:
        nueva = _categoria(session, str(categoria_id))
        antes = session.get(Categoria, activo.categoria_id)
        nombre_antes = antes.nombre if antes else ""
        eventos.append(
            (
                "categoria_cambiada",
                {
                    "antes": {"id": str(activo.categoria_id), "nombre": nombre_antes},
                    "despues": {"id": str(nueva.id), "nombre": nueva.nombre},
                },
            )
        )
    campos = {
        campo: {"antes": _json(getattr(activo, campo)), "despues": _json(cambios[campo])}
        for campo in DATOS
        if campo in cambios and cambios[campo] != getattr(activo, campo)
    }
    if campos:
        eventos.append(("datos_cambiados", {"campos": campos}))
    if not eventos:
        return activo

    for campo, valor in cambios.items():
        setattr(activo, campo, valor)
    _registrar(session, activo, eventos, usuario_id)
    return activo
