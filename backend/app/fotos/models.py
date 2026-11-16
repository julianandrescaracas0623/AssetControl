"""Modelo ORM de ``foto`` (spec 012, T3; docs/03). El esquema lo crea ``0013_fotos``.

``id`` lo manda el cliente (subida idempotente); ``creada_en`` lo pone la base. La
aplicación solo inserta y, al cambiar o quitar, marca ``retirada_en``/``retirada_por``.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, FetchedValue, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.models import Base
from app.db import TenantScoped


class Foto(TenantScoped, Base):
    __tablename__ = "foto"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    activo_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    verificacion_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    clave: Mapped[str] = mapped_column(Text)
    bytes: Mapped[int] = mapped_column(Integer)
    ancho: Mapped[int] = mapped_column(Integer)
    alto: Mapped[int] = mapped_column(Integer)
    subida_por: Mapped[uuid.UUID] = mapped_column(Uuid)
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=FetchedValue()
    )
    retirada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retirada_por: Mapped[uuid.UUID | None] = mapped_column(Uuid)
