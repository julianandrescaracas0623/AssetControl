"""Datos sintéticos para desarrollo y pruebas (``flask sembrar-demo`` / ``sembrar-contador``).

Solo corre en ``development`` y ``test``. Los activos usan el alta de dominio
(evento ``creado``, UUID de cliente estable) y el catálogo del tenant. Códigos
``DEMO-*``. El contador se crea por invitación de dominio (no un ``INSERT``
directo). Nunca el Excel de la clínica ni datos reales.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.activos.service import CodigoExistente, DatosAlta, ErrorActivo, guardar
from app.auth.credentials import get_passwords
from app.auth.service import normalize_email
from app.catalogo.service import (
    NombreDuplicado,
    cargar_sugeridas,
    crear_ubicacion,
    listar_categorias,
    listar_ubicaciones,
)
from app.db import LoginRow, aceptar_invitacion, buscar_login, tenant_session
from app.invitaciones.service import (
    create_invitation,
    invitation_key,
    normalize_invitation_email,
    normalize_nombre,
)

CODIGO_PREFIJO = "DEMO-"
_NS = uuid.UUID("a11ce7d0-0000-4000-8000-00000000de30")
_ADMIN_GENERICO = "No hay un administrador activo con ese correo en una sola clínica."
_CONTADOR_GENERICO = "No se pudo crear el usuario de prueba."

# Cuenta sintética local. El comando no corre fuera de development/test.
CONTADOR_DEMO_EMAIL = "contador@ejemplo.com"
CONTADOR_DEMO_NOMBRE = "Contador de prueba"
CONTADOR_CLAVE_LOCAL = "ContadorLocal-26"

_SEDE = "Sede de prueba"
_CONSULTORIO = "Consultorio 1"
_BOX = "Box 1"
_BODEGA = "Bodega"


@dataclass(frozen=True)
class ActivoDemo:
    codigo: str
    nombre: str
    categoria: str
    sitio: str
    precio: str
    fecha: str
    marca: str | None = None
    modelo: str | None = None
    serial: str | None = None
    subtipo: str | None = None


ACTIVOS_DEMO: tuple[ActivoDemo, ...] = (
    ActivoDemo(
        "DEMO-001",
        "Silla de espera",
        "Mobiliario",
        _CONSULTORIO,
        "185000.00",
        "2024-02-10",
        "Genérico",
        "SE-100",
    ),
    ActivoDemo(
        "DEMO-002",
        "Escritorio de consulta",
        "Mobiliario",
        _CONSULTORIO,
        "420000.00",
        "2024-03-01",
        "Genérico",
        "EC-200",
    ),
    ActivoDemo(
        "DEMO-003",
        "Monitor 24 pulgadas",
        "Electrónica",
        _BOX,
        "890000.00",
        "2024-04-12",
        "Vista",
        "M24",
        "SN-MON-001",
    ),
    ActivoDemo(
        "DEMO-004",
        "CPU de escritorio",
        "CPU",
        _BOX,
        "2100000.00",
        "2024-04-12",
        "Núcleo",
        "T3",
        "SN-CPU-001",
    ),
    ActivoDemo(
        "DEMO-005",
        "Teclado",
        "Periféricos",
        _BOX,
        "95000.00",
        "2024-05-20",
        "Pulse",
        "K1",
        "SN-TEC-001",
    ),
    ActivoDemo(
        "DEMO-006",
        "Impresora láser",
        "Periféricos",
        _BODEGA,
        "780000.00",
        "2023-11-08",
        "Hoja",
        "L2",
        "SN-IMP-001",
    ),
    ActivoDemo(
        "DEMO-007",
        "Nevera pequeña",
        "Electrodomésticos",
        _BODEGA,
        "1250000.00",
        "2023-09-15",
        "Frío",
        "N90",
    ),
    ActivoDemo(
        "DEMO-008",
        "Lámpara LED",
        "Biomédicos",
        _BOX,
        "640000.00",
        "2024-06-03",
        "Luz",
        "LED-7",
        "SN-LAM-001",
        "techo",
    ),
    ActivoDemo(
        "DEMO-009",
        "Autoclave de prueba",
        "Biomédicos",
        _BODEGA,
        "4500000.00",
        "2022-08-22",
        "Vapor",
        "AC-1",
        "SN-AUT-001",
    ),
    ActivoDemo(
        "DEMO-010",
        "Enrutador Wi-Fi",
        "Electrónica",
        _CONSULTORIO,
        "310000.00",
        "2024-01-18",
        "Red",
        "R6",
        "SN-RED-001",
    ),
    ActivoDemo(
        "DEMO-011",
        "Sillón reclinable",
        "Mobiliario",
        _BOX,
        "980000.00",
        "2023-12-04",
        "Asiento",
        "SR-4",
    ),
    ActivoDemo(
        "DEMO-012",
        "Escáner de mesa",
        "Periféricos",
        _BODEGA,
        "540000.00",
        "2024-07-09",
        "Lector",
        "ES-2",
        "SN-ESC-001",
    ),
)


@dataclass(frozen=True)
class ResultadoSembrar:
    nuevos: int
    existentes: int


@dataclass(frozen=True)
class ResultadoContador:
    creado: bool
    email: str


class SembrarError(Exception):
    """Fallo del operador: el mensaje es seguro para la salida (sin filas ni correos)."""


def id_demo(tenant_id: uuid.UUID, codigo: str) -> uuid.UUID:
    return uuid.uuid5(_NS, f"{tenant_id}:{codigo}")


def _admin_unico(email: str) -> LoginRow:
    normalizado = normalize_email(email)
    if normalizado is None:
        raise SembrarError("El correo no es válido.")
    filas = [
        fila
        for fila in buscar_login(normalizado)
        if fila.activo and fila.rol == "admin" and fila.tenant_id is not None
    ]
    if len(filas) != 1:
        raise SembrarError(_ADMIN_GENERICO)
    return filas[0]


def _asegurar_ubicacion(
    session: Session, *, nombre: str, tipo: str, padre_id: uuid.UUID | None
) -> uuid.UUID:
    for u in listar_ubicaciones(session, solo_activas=True):
        if u.nombre == nombre and u.tipo == tipo and u.padre_id == padre_id:
            return u.id
    try:
        return crear_ubicacion(session, nombre=nombre, tipo=tipo, padre_id=padre_id).id
    except NombreDuplicado:
        for u in listar_ubicaciones(session, solo_activas=True):
            if u.nombre == nombre and u.tipo == tipo and u.padre_id == padre_id:
                return u.id
        raise SembrarError("No se pudo preparar una ubicación de prueba.") from None


def _mapa_categorias(session: Session) -> dict[str, uuid.UUID]:
    return {c.nombre: c.id for c in listar_categorias(session)}


def _sembrar_en_sesion(
    session: Session, *, tenant_id: uuid.UUID, usuario_id: uuid.UUID
) -> ResultadoSembrar:
    cargar_sugeridas(session, tenant_id)
    categorias = _mapa_categorias(session)
    sede = _asegurar_ubicacion(session, nombre=_SEDE, tipo="sede", padre_id=None)
    consultorio = _asegurar_ubicacion(session, nombre=_CONSULTORIO, tipo="sala", padre_id=sede)
    box = _asegurar_ubicacion(session, nombre=_BOX, tipo="box", padre_id=consultorio)
    bodega = _asegurar_ubicacion(session, nombre=_BODEGA, tipo="sala", padre_id=sede)
    sitios = {_CONSULTORIO: consultorio, _BOX: box, _BODEGA: bodega}

    nuevos = 0
    existentes = 0
    for item in ACTIVOS_DEMO:
        categoria_id = categorias.get(item.categoria)
        ubicacion_id = sitios.get(item.sitio)
        if categoria_id is None or ubicacion_id is None:
            raise SembrarError("El catálogo de prueba no quedó completo.")
        datos = DatosAlta(
            id=id_demo(tenant_id, item.codigo),
            codigo=item.codigo,
            nombre=item.nombre,
            precio=Decimal(item.precio),
            categoria_id=categoria_id,
            ubicacion_id=ubicacion_id,
            opcionales={
                "serial": item.serial,
                "marca": item.marca,
                "modelo": item.modelo,
                "subtipo": item.subtipo,
            },
            fecha_compra=date.fromisoformat(item.fecha),
        )
        try:
            resultado = guardar(session, datos, usuario_id=usuario_id, con_precio=True)
        except CodigoExistente:
            existentes += 1
            continue
        except ErrorActivo as exc:
            raise SembrarError("No se pudo crear un activo de prueba.") from exc
        if resultado.creado:
            nuevos += 1
        else:
            existentes += 1
    return ResultadoSembrar(nuevos=nuevos, existentes=existentes)


def sembrar_demo(email: str) -> ResultadoSembrar:
    """Siembra el catálogo y los ``DEMO-*`` del tenant del admin indicado."""
    cuenta = _admin_unico(email)
    tenant_id = cuenta.tenant_id
    if tenant_id is None:
        raise SembrarError(_ADMIN_GENERICO)
    with tenant_session(tenant_id) as session:
        return _sembrar_en_sesion(session, tenant_id=tenant_id, usuario_id=cuenta.usuario_id)


def _contador_demo_en_tenant(tenant_id: uuid.UUID) -> bool:
    return any(
        fila.activo and fila.rol == "contador" and fila.tenant_id == tenant_id
        for fila in buscar_login(CONTADOR_DEMO_EMAIL)
    )


def sembrar_contador(email: str) -> ResultadoContador:
    """Crea el contador sintético del tenant del admin, por invitación de dominio."""
    cuenta = _admin_unico(email)
    tenant_id = cuenta.tenant_id
    if tenant_id is None:
        raise SembrarError(_ADMIN_GENERICO)
    if _contador_demo_en_tenant(tenant_id):
        return ResultadoContador(creado=False, email=CONTADOR_DEMO_EMAIL)
    destino = normalize_invitation_email(CONTADOR_DEMO_EMAIL)
    nombre = normalize_nombre(CONTADOR_DEMO_NOMBRE)
    if destino is None or nombre is None:
        raise SembrarError(_CONTADOR_GENERICO)
    if destino == normalize_email(email):
        raise SembrarError(_CONTADOR_GENERICO)
    try:
        with tenant_session(tenant_id) as session:
            invitacion = create_invitation(
                session, creada_por=cuenta.usuario_id, email=destino, rol="contador"
            )
            token = invitacion.token
    except IntegrityError as exc:
        raise SembrarError(_CONTADOR_GENERICO) from exc
    aceptada = aceptar_invitacion(
        invitation_key(token), nombre, get_passwords().hash(CONTADOR_CLAVE_LOCAL)
    )
    if aceptada is None or aceptada.tenant_id != tenant_id or aceptada.rol != "contador":
        raise SembrarError(_CONTADOR_GENERICO)
    return ResultadoContador(creado=True, email=CONTADOR_DEMO_EMAIL)
