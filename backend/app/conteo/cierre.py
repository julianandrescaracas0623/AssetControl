"""Cierre de una sesión de conteo e informe congelado (spec 008, T2–T3; R1–R7; plan.md §3).

**Una sola fuente (R8 de docs/03).** ``universo`` es la única función que calcula la
lista U del cierre y ``agregar`` la única que la suma; el cierre guarda lo que salen de
ahí y el informe solo **lee** lo guardado. Ningún otro código recalcula U ni los totales.

U = activos con verificación vigente (mayor ``seq``, R3) en la sesión, en cualquier
estado, ∪ activos ``activo`` o ``en_reparacion`` sin verificación (R4, P15):

- encontrado → ``precio_al_contar``, ``categoria_al_contar`` y ``ubicacion_esperada_id``
  de la verificación (foto al contar, ADR-003);
- no encontrado → precio, categoría y ubicación vigentes, y la marca "en reparación".

**Concurrencia (R4).** ``cerrar`` toma el candado consultivo **exclusivo** de la sesión
(la verificación toma el compartido: espera a las que están en curso y las siguientes
ven la sesión cerrada) y la fila con ``FOR UPDATE``; U sale de **una sola consulta**,
así cada escritura concurrente sobre activos (alta, precio, categoría, ubicación,
estado, baja) queda entera dentro o entera fuera de la vista del cierre.
"""

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import and_, case, exists, func, literal, select, union_all
from sqlalchemy.orm import Session, aliased

from app.activos.models import Activo
from app.auth.models import Tenant
from app.catalogo.models import Categoria, Ubicacion
from app.conteo import service
from app.conteo.models import (
    SesionConteo,
    SesionDesglose,
    SesionDetalle,
    SesionEmpresa,
    SesionNoEncontrado,
    Verificacion,
)
from app.conteo.verificaciones import bloquear_sesion
from app.empresa.models import Empresa

CERO = Decimal("0.00")
SEPARADOR_RUTA = " › "


class SesionAbierta(service.ErrorConteo):
    status = 409
    code = "sesion_abierta"
    message = "La sesión sigue abierta: el informe existe cuando se cierra."


ERRORES = (SesionAbierta,)


# --- Universo (la única fuente) -----------------------------------------------------------


@dataclass(frozen=True)
class FilaU:
    activo_id: uuid.UUID
    encontrado: bool
    precio: Decimal
    categoria_id: uuid.UUID
    categoria_nombre: str
    ubicacion_id: uuid.UUID
    ubicacion_ruta: str
    codigo: str
    nombre: str
    en_reparacion: bool
    # Spec 013 (R4): para el detalle congelado. De la verificación vigente si se encontró.
    marca: str | None = None
    serial: str | None = None
    encontrada_ruta: str | None = None
    estado_fisico: str | None = None


def _ruta(lugar, padre):
    return case(
        (
            and_(lugar.tipo == "box", padre.nombre.is_not(None)),
            padre.nombre + SEPARADOR_RUTA + lugar.nombre,
        ),
        else_=lugar.nombre,
    )


def universo(session: Session, sesion_id: uuid.UUID) -> list[FilaU]:
    """La lista U del cierre, en **una** consulta (vista consistente)."""
    orden = func.row_number().over(
        partition_by=Verificacion.activo_id, order_by=Verificacion.seq.desc()
    )
    vigentes = (
        select(
            Verificacion.activo_id,
            Verificacion.precio_al_contar,
            Verificacion.categoria_al_contar,
            Verificacion.ubicacion_esperada_id,
            Verificacion.ubicacion_encontrada_id,
            Verificacion.estado_fisico,
            orden.label("orden"),
        )
        .where(Verificacion.sesion_id == sesion_id)
        .subquery()
    )
    encontrados = select(
        vigentes.c.activo_id.label("activo_id"),
        literal(True).label("encontrado"),
        vigentes.c.precio_al_contar.label("precio"),
        vigentes.c.categoria_al_contar.label("categoria_id"),
        vigentes.c.ubicacion_esperada_id.label("ubicacion_id"),
        vigentes.c.ubicacion_encontrada_id.label("encontrada_id"),
        vigentes.c.estado_fisico.label("estado_fisico"),
    ).where(vigentes.c.orden == 1)
    no_encontrados = select(
        Activo.id.label("activo_id"),
        literal(False).label("encontrado"),
        Activo.precio_compra.label("precio"),
        Activo.categoria_id.label("categoria_id"),
        Activo.ubicacion_id.label("ubicacion_id"),
        literal(None, type_=Verificacion.ubicacion_encontrada_id.type).label("encontrada_id"),
        literal(None, type_=Verificacion.estado_fisico.type).label("estado_fisico"),
    ).where(
        Activo.estado.in_(service.ESTADOS_QUE_CUENTAN),
        ~exists().where(
            and_(Verificacion.sesion_id == sesion_id, Verificacion.activo_id == Activo.id)
        ),
    )
    u = union_all(encontrados, no_encontrados).subquery()
    lugar = aliased(Ubicacion)
    padre = aliased(Ubicacion)
    hallado = aliased(Ubicacion)
    hallado_padre = aliased(Ubicacion)
    filas = session.execute(
        select(
            u.c.activo_id,
            u.c.encontrado,
            u.c.precio,
            u.c.categoria_id,
            Categoria.nombre,
            u.c.ubicacion_id,
            _ruta(lugar, padre),
            Activo.codigo,
            Activo.nombre,
            Activo.estado,
            Activo.marca,
            Activo.serial,
            case((hallado.id.is_not(None), _ruta(hallado, hallado_padre)), else_=None),
            u.c.estado_fisico,
        )
        .join(Activo, Activo.id == u.c.activo_id)
        .join(Categoria, Categoria.id == u.c.categoria_id)
        .join(lugar, lugar.id == u.c.ubicacion_id)
        .outerjoin(padre, padre.id == lugar.padre_id)
        .outerjoin(hallado, hallado.id == u.c.encontrada_id)
        .outerjoin(hallado_padre, hallado_padre.id == hallado.padre_id)
        .order_by(u.c.activo_id)
    ).all()
    return [
        FilaU(
            activo_id=f[0],
            encontrado=bool(f[1]),
            precio=Decimal(f[2]),
            categoria_id=f[3],
            categoria_nombre=f[4],
            ubicacion_id=f[5],
            ubicacion_ruta=f[6],
            codigo=f[7],
            nombre=f[8],
            en_reparacion=(not f[1]) and f[9] == "en_reparacion",
            marca=f[10],
            serial=f[11],
            encontrada_ruta=f[12],
            estado_fisico=f[13],
        )
        for f in filas
    ]


@dataclass
class Cifras:
    etiqueta: str = ""
    encontrado: Decimal = CERO
    no_encontrado: Decimal = CERO
    unidades_encontrado: int = 0
    unidades_no_encontrado: int = 0

    def sumar(self, fila: FilaU) -> None:
        if fila.encontrado:
            self.encontrado += fila.precio
            self.unidades_encontrado += 1
        else:
            self.no_encontrado += fila.precio
            self.unidades_no_encontrado += 1

    @property
    def registrado(self) -> Decimal:
        return self.encontrado + self.no_encontrado

    @property
    def unidades_registrado(self) -> int:
        return self.unidades_encontrado + self.unidades_no_encontrado


@dataclass
class Agregado:
    filas: list[FilaU] = field(default_factory=list)
    total: Cifras = field(default_factory=Cifras)
    por_categoria: dict[uuid.UUID, Cifras] = field(default_factory=dict)
    por_ubicacion: dict[uuid.UUID, Cifras] = field(default_factory=dict)
    no_encontrados: list[FilaU] = field(default_factory=list)


def agregar(filas: list[FilaU]) -> Agregado:
    """Las tres cifras, el desglose y la lista, todo de la misma lista U (``Decimal``)."""
    agregado = Agregado(filas=list(filas))
    for fila in filas:
        agregado.total.sumar(fila)
        agregado.por_categoria.setdefault(fila.categoria_id, Cifras(fila.categoria_nombre)).sumar(
            fila
        )
        agregado.por_ubicacion.setdefault(fila.ubicacion_id, Cifras(fila.ubicacion_ruta)).sumar(
            fila
        )
        if not fila.encontrado:
            agregado.no_encontrados.append(fila)
    return agregado


# --- Cerrar (R2, R4–R6) -------------------------------------------------------------------


def cerrar(session: Session, sesion_id: uuid.UUID, usuario_id: uuid.UUID) -> SesionConteo:
    bloquear_sesion(session, sesion_id, exclusivo=True)
    sesion = session.scalars(
        select(SesionConteo)
        .where(SesionConteo.id == sesion_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one_or_none()
    if sesion is None:
        raise service.NoEncontrado()
    if sesion.estado != "abierta":
        return sesion  # Q1: ya cerrada; el informe se lee, nada se reinserta.

    agregado = agregar(universo(session, sesion.id))
    sesion.estado = "cerrada"
    sesion.cerrada_por = usuario_id
    sesion.cerrada_en = func.now()  # type: ignore[assignment]
    sesion.total_encontrado = agregado.total.encontrado
    sesion.total_no_encontrado = agregado.total.no_encontrado
    sesion.total_registrado = agregado.total.registrado
    session.flush()  # primero se cierra; los disparadores exigen la sesión cerrada

    for dimension, grupo in (
        ("categoria", agregado.por_categoria),
        ("ubicacion", agregado.por_ubicacion),
    ):
        for clave, cifras in grupo.items():
            session.add(
                SesionDesglose(
                    sesion_id=sesion.id,
                    dimension=dimension,
                    categoria_id=clave if dimension == "categoria" else None,
                    ubicacion_id=clave if dimension == "ubicacion" else None,
                    etiqueta=cifras.etiqueta,
                    total_encontrado=cifras.encontrado,
                    total_no_encontrado=cifras.no_encontrado,
                    total_registrado=cifras.registrado,
                    unidades_encontrado=cifras.unidades_encontrado,
                    unidades_no_encontrado=cifras.unidades_no_encontrado,
                    unidades_registrado=cifras.unidades_registrado,
                )
            )
    for fila in agregado.no_encontrados:
        session.add(
            SesionNoEncontrado(
                sesion_id=sesion.id,
                activo_id=fila.activo_id,
                codigo=fila.codigo,
                nombre=fila.nombre,
                categoria_id=fila.categoria_id,
                categoria_nombre=fila.categoria_nombre,
                ubicacion_id=fila.ubicacion_id,
                ubicacion_ruta=fila.ubicacion_ruta,
                precio=fila.precio,
                en_reparacion=fila.en_reparacion,
            )
        )
    # Spec 013 (R4): una fila por activo de U, de la misma lista que el desglose.
    for fila in agregado.filas:
        session.add(
            SesionDetalle(
                sesion_id=sesion.id,
                activo_id=fila.activo_id,
                codigo=fila.codigo,
                nombre=fila.nombre,
                marca=fila.marca,
                serial=fila.serial,
                categoria_id=fila.categoria_id,
                categoria_nombre=fila.categoria_nombre,
                ubicacion_id=fila.ubicacion_id,
                ubicacion_ruta=fila.ubicacion_ruta,
                encontrada_ruta=fila.encontrada_ruta,
                estado_fisico=fila.estado_fisico,
                encontrado=fila.encontrado,
                en_reparacion=fila.en_reparacion,
                precio=fila.precio,
            )
        )
    session.add(_copia_empresa(session, sesion))
    session.flush()
    session.refresh(sesion)
    return sesion


CAMPOS_EMPRESA = ("nombre", "direccion", "nit", "telefono", "correo", "logo_id")


def _copia_empresa(session: Session, sesion: SesionConteo) -> SesionEmpresa:
    """R3: la empresa vigente al cerrar; sin datos guardados, el nombre del tenant."""
    empresa = session.scalars(select(Empresa)).one_or_none()
    if empresa is None:
        nombre = session.scalar(select(Tenant.nombre).where(Tenant.id == sesion.tenant_id))
        return SesionEmpresa(sesion_id=sesion.id, nombre=nombre)
    return SesionEmpresa(
        sesion_id=sesion.id, **{campo: getattr(empresa, campo) for campo in CAMPOS_EMPRESA}
    )


# --- Informe (solo lectura; R7) -----------------------------------------------------------


def _dinero(valor: Decimal | None) -> str:
    return str((valor or CERO).quantize(Decimal("0.01")))


def informe(session: Session, sesion: SesionConteo) -> dict[str, object]:
    """Lee lo congelado al cierre; no recalcula nada con datos actuales."""
    if sesion.estado != "cerrada":
        raise SesionAbierta()
    filas = session.scalars(
        select(SesionDesglose)
        .where(SesionDesglose.sesion_id == sesion.id)
        .order_by(SesionDesglose.dimension, func.lower(SesionDesglose.etiqueta), SesionDesglose.id)
    ).all()

    def vista_fila(f: SesionDesglose) -> dict[str, object]:
        return {
            "id": str(f.categoria_id or f.ubicacion_id),
            "etiqueta": f.etiqueta,
            "total_encontrado": _dinero(f.total_encontrado),
            "total_no_encontrado": _dinero(f.total_no_encontrado),
            "total_registrado": _dinero(f.total_registrado),
            "unidades_encontrado": f.unidades_encontrado,
            "unidades_no_encontrado": f.unidades_no_encontrado,
            "unidades_registrado": f.unidades_registrado,
        }

    categorias = [f for f in filas if f.dimension == "categoria"]
    ubicaciones = [f for f in filas if f.dimension == "ubicacion"]
    faltantes = session.scalars(
        select(SesionNoEncontrado)
        .where(SesionNoEncontrado.sesion_id == sesion.id)
        .order_by(func.lower(SesionNoEncontrado.ubicacion_ruta), SesionNoEncontrado.codigo)
    ).all()
    return {
        "sesion": service.vista(session, sesion),
        "empresa": empresa_del_informe(session, sesion),
        "detalle_disponible": _tiene_detalle(session, sesion),
        "totales": {
            "encontrado": _dinero(sesion.total_encontrado),
            "no_encontrado": _dinero(sesion.total_no_encontrado),
            "registrado": _dinero(sesion.total_registrado),
            # Las unidades de la sesión son la suma de una dimensión del desglose (R9).
            "unidades_encontrado": sum(f.unidades_encontrado for f in categorias),
            "unidades_no_encontrado": sum(f.unidades_no_encontrado for f in categorias),
            "unidades_registrado": sum(f.unidades_registrado for f in categorias),
        },
        "desglose": {
            "categorias": [vista_fila(f) for f in categorias],
            "ubicaciones": [vista_fila(f) for f in ubicaciones],
        },
        "no_encontrados": [
            {
                "activo_id": str(f.activo_id),
                "codigo": f.codigo,
                "nombre": f.nombre,
                "categoria": {"id": str(f.categoria_id), "nombre": f.categoria_nombre},
                "ubicacion": {"id": str(f.ubicacion_id), "ruta": f.ubicacion_ruta},
                "precio": _dinero(f.precio),
                "en_reparacion": f.en_reparacion,
            }
            for f in faltantes
        ],
    }


def empresa_del_informe(session: Session, sesion: SesionConteo) -> dict[str, object]:
    """La copia del cierre (R3) o, si la sesión se cerró antes de la 013, la vigente
    rotulada con ``vigente: true`` (Q1 A)."""
    copia = session.get(SesionEmpresa, (sesion.tenant_id, sesion.id))
    fuente: SesionEmpresa | Empresa | None = copia
    if fuente is None:
        fuente = session.scalars(select(Empresa)).one_or_none()
    if fuente is None:
        nombre = session.scalar(select(Tenant.nombre).where(Tenant.id == sesion.tenant_id))
        datos = dict.fromkeys(CAMPOS_EMPRESA)
        datos["nombre"] = nombre
    else:
        datos = {campo: getattr(fuente, campo) for campo in CAMPOS_EMPRESA}
    logo_id = datos.pop("logo_id")
    return {
        **datos,
        "logo": {"id": str(logo_id)} if logo_id else None,
        "vigente": copia is None,
    }


def _tiene_detalle(session: Session, sesion: SesionConteo) -> bool:
    """Las sesiones cerradas desde la 013 tienen la copia de la empresa y su detalle."""
    return session.get(SesionEmpresa, (sesion.tenant_id, sesion.id)) is not None


def detalle(session: Session, sesion: SesionConteo) -> list[SesionDetalle]:
    """El detalle congelado (R4), por categoría, encontrados primero y código."""
    if sesion.estado != "cerrada":
        raise SesionAbierta()
    return list(
        session.scalars(
            select(SesionDetalle)
            .where(SesionDetalle.sesion_id == sesion.id)
            .order_by(
                func.lower(SesionDetalle.categoria_nombre),
                SesionDetalle.encontrado.desc(),
                SesionDetalle.codigo,
            )
        ).all()
    )
