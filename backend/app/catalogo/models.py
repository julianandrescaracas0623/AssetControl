"""Modelos ORM de ubicaciones y categorías (spec 003, T1; docs/03).

El esquema lo crea la migración ``0006_ubicaciones_y_categorias``; estos modelos solo
lo describen (nunca ``create_all``). Ambos son ``TenantScoped``: el filtro central de
``app.db`` y RLS los acotan al tenant de la sesión. ``id``, ``activa`` y
``creado_en`` los pone la base (la aplicación no tiene ``INSERT`` sobre ellos) y se
leen con ``RETURNING``.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, FetchedValue, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.models import Base
from app.db import TenantScoped


class Ubicacion(TenantScoped, Base):
    __tablename__ = "ubicacion"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=FetchedValue())
    nombre: Mapped[str] = mapped_column(Text)
    nombre_clave: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(Text)
    padre_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    activa: Mapped[bool] = mapped_column(server_default=FetchedValue())
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=FetchedValue()
    )


class Categoria(TenantScoped, Base):
    __tablename__ = "categoria"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=FetchedValue())
    nombre: Mapped[str] = mapped_column(Text)
    nombre_clave: Mapped[str] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=FetchedValue()
    )
