"""Modelos ORM de ``activo`` y ``activo_evento`` (spec 004, T1; docs/03).

El esquema lo crea ``0007_activos``. ``Activo.id`` lo manda el cliente (alta
idempotente); ``estado``, ``row_version`` y las fechas los pone la base y se leen con
``RETURNING``. ``ActivoEvento`` es inmutable (la aplicación solo inserta y lee).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, FetchedValue, Numeric, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.models import Base
from app.db import TenantScoped


class Activo(TenantScoped, Base):
    __tablename__ = "activo"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    codigo: Mapped[str] = mapped_column(Text)
    nombre: Mapped[str] = mapped_column(Text)
    categoria_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    ubicacion_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    serial: Mapped[str | None] = mapped_column(Text)
    marca: Mapped[str | None] = mapped_column(Text)
    modelo: Mapped[str | None] = mapped_column(Text)
    referencia: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str | None] = mapped_column(Text)
    subtipo: Mapped[str | None] = mapped_column(Text)
    atributos: Mapped[dict] = mapped_column(JSONB, default=dict)
    precio_compra: Mapped[Decimal] = mapped_column(Numeric(14, 2, asdecimal=True))
    fecha_compra: Mapped[date | None] = mapped_column(Date)
    estado: Mapped[str] = mapped_column(Text, server_default=FetchedValue())
    row_version: Mapped[int] = mapped_column(server_default=FetchedValue())
    creado_por: Mapped[uuid.UUID] = mapped_column(Uuid)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=FetchedValue()
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=FetchedValue()
    )


class ActivoEvento(TenantScoped, Base):
    __tablename__ = "activo_evento"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=FetchedValue())
    activo_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    tipo: Mapped[str] = mapped_column(Text)
    datos: Mapped[dict] = mapped_column(JSONB)
    usuario_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    sesion_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    verificacion_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    ocurrido_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=FetchedValue()
    )
    seq: Mapped[int] = mapped_column(BigInteger, server_default=FetchedValue())
