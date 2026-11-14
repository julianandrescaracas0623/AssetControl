"""Modelos ORM de ``sesion_conteo`` y ``verificacion`` (spec 006, T1; docs/03).

El esquema lo crea ``0009_sesiones_y_verificacion``. ``Verificacion.id`` lo manda el
cliente (idempotencia, R2) y la fila es inmutable; ``seq`` y ``recibido_en`` los pone la
base. ``SesionConteo`` la crea la aplicación siempre ``conteo`` y ``abierta`` (DEFAULT).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, FetchedValue, Numeric, Text, Uuid
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
