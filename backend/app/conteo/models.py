"""Modelos ORM de ``sesion_conteo`` y ``verificacion`` (spec 006, T1; docs/03).

El esquema lo crea ``0009_sesiones_y_verificacion``. ``Verificacion.id`` lo manda el
cliente (idempotencia, R2) y la fila es inmutable; ``seq`` y ``recibido_en`` los pone la
base. ``SesionConteo`` la crea la aplicación siempre ``conteo`` y ``abierta`` (DEFAULT).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    FetchedValue,
    Integer,
    Numeric,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.models import Base
from app.db import TenantScoped


class SesionConteo(TenantScoped, Base):
    __tablename__ = "sesion_conteo"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=FetchedValue())
    nombre: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(Text, server_default=FetchedValue())
    estado: Mapped[str] = mapped_column(Text, server_default=FetchedValue())
    fecha_corte: Mapped[date] = mapped_column(Date)
    abierta_por: Mapped[uuid.UUID] = mapped_column(Uuid)
    abierta_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=FetchedValue()
    )
    # Las pone el cierre (008); al insertar no se envían (la aplicación no tiene INSERT).
    cerrada_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, server_default=FetchedValue())
    cerrada_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=FetchedValue()
    )
    total_encontrado: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2, asdecimal=True), server_default=FetchedValue()
    )
    total_no_encontrado: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2, asdecimal=True), server_default=FetchedValue()
    )
    total_registrado: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2, asdecimal=True), server_default=FetchedValue()
    )


class Verificacion(TenantScoped, Base):
    __tablename__ = "verificacion"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    sesion_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    activo_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    ubicacion_esperada_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    ubicacion_encontrada_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    estado_fisico: Mapped[str] = mapped_column(Text)
    precio_al_contar: Mapped[Decimal] = mapped_column(Numeric(14, 2, asdecimal=True))
    categoria_al_contar: Mapped[uuid.UUID] = mapped_column(Uuid)
    nota: Mapped[str | None] = mapped_column(Text)
    verificado_por: Mapped[uuid.UUID] = mapped_column(Uuid)
    ocurrido_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recibido_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=FetchedValue()
    )
    seq: Mapped[int] = mapped_column(BigInteger, server_default=FetchedValue())


class SesionDesglose(TenantScoped, Base):
    """Fila congelada del desglose de una sesión cerrada (spec 008, R9); solo INSERT."""

    __tablename__ = "sesion_desglose"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=FetchedValue())
    sesion_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    dimension: Mapped[str] = mapped_column(Text)
    categoria_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    ubicacion_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    etiqueta: Mapped[str] = mapped_column(Text)
    total_encontrado: Mapped[Decimal] = mapped_column(Numeric(14, 2, asdecimal=True))
    total_no_encontrado: Mapped[Decimal] = mapped_column(Numeric(14, 2, asdecimal=True))
    total_registrado: Mapped[Decimal] = mapped_column(Numeric(14, 2, asdecimal=True))
    unidades_encontrado: Mapped[int] = mapped_column(Integer)
    unidades_no_encontrado: Mapped[int] = mapped_column(Integer)
    unidades_registrado: Mapped[int] = mapped_column(Integer)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=FetchedValue()
    )


class SesionNoEncontrado(TenantScoped, Base):
    """Activo no encontrado congelado al cierre (spec 008, R9a); solo INSERT."""

    __tablename__ = "sesion_no_encontrado"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=FetchedValue())
    sesion_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    activo_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    codigo: Mapped[str] = mapped_column(Text)
    nombre: Mapped[str] = mapped_column(Text)
    categoria_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    categoria_nombre: Mapped[str] = mapped_column(Text)
    ubicacion_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    ubicacion_ruta: Mapped[str] = mapped_column(Text)
    precio: Mapped[Decimal] = mapped_column(Numeric(14, 2, asdecimal=True))
    en_reparacion: Mapped[bool] = mapped_column(Boolean)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=FetchedValue()
    )


class SesionEmpresa(TenantScoped, Base):
    """Datos de la empresa congelados al cierre (spec 013, R3); solo INSERT.

    ``vigente`` no se escribe al cerrar (siempre ``false``): la usa el informe para las
    sesiones cerradas antes de la 013, que no tienen copia (Q1 A).
    """

    __tablename__ = "sesion_empresa"
    __mapper_args__ = {"eager_defaults": True}

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    sesion_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    nombre: Mapped[str] = mapped_column(Text)
    direccion: Mapped[str | None] = mapped_column(Text)
    nit: Mapped[str | None] = mapped_column(Text)
    telefono: Mapped[str | None] = mapped_column(Text)
    correo: Mapped[str | None] = mapped_column(Text)
    logo_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    vigente: Mapped[bool] = mapped_column(Boolean, server_default=FetchedValue())
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=FetchedValue()
    )


class SesionDetalle(TenantScoped, Base):
    """Una fila por activo del universo U congelada al cierre (spec 013, R4); solo INSERT."""

    __tablename__ = "sesion_detalle"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=FetchedValue())
    sesion_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    activo_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    codigo: Mapped[str] = mapped_column(Text)
    nombre: Mapped[str] = mapped_column(Text)
    marca: Mapped[str | None] = mapped_column(Text)
    serial: Mapped[str | None] = mapped_column(Text)
    categoria_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    categoria_nombre: Mapped[str] = mapped_column(Text)
    ubicacion_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    ubicacion_ruta: Mapped[str] = mapped_column(Text)
    encontrada_ruta: Mapped[str | None] = mapped_column(Text)
    estado_fisico: Mapped[str | None] = mapped_column(Text)
    encontrado: Mapped[bool] = mapped_column(Boolean)
    en_reparacion: Mapped[bool] = mapped_column(Boolean)
    precio: Mapped[Decimal] = mapped_column(Numeric(14, 2, asdecimal=True))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=FetchedValue()
    )
