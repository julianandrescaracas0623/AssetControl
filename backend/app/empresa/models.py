"""Modelos ORM de ``empresa`` y ``empresa_logo`` (spec 013, T1; docs/03).

El esquema lo crea ``0014_empresa_y_detalle``. ``empresa`` es una fila por tenant (su
``tenant_id`` es la clave primaria). Los logos solo se insertan: nunca se borran porque
los informes congelados los siguen usando (R2).
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, FetchedValue, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.models import Base
from app.db import TenantScoped


class Empresa(TenantScoped, Base):
    __tablename__ = "empresa"
    __mapper_args__ = {"eager_defaults": True}

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    nombre: Mapped[str] = mapped_column(Text)
    direccion: Mapped[str] = mapped_column(Text)
    nit: Mapped[str | None] = mapped_column(Text)
    telefono: Mapped[str | None] = mapped_column(Text)
    correo: Mapped[str | None] = mapped_column(Text)
    logo_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    actualizada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=FetchedValue()
    )
    actualizada_por: Mapped[uuid.UUID] = mapped_column(Uuid)


class EmpresaLogo(TenantScoped, Base):
    __tablename__ = "empresa_logo"
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    clave: Mapped[str] = mapped_column(Text)
    bytes: Mapped[int] = mapped_column(Integer)
    ancho: Mapped[int] = mapped_column(Integer)
    alto: Mapped[int] = mapped_column(Integer)
    subido_por: Mapped[uuid.UUID] = mapped_column(Uuid)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=FetchedValue()
    )
