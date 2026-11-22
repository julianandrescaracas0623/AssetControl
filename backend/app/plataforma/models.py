"""Modelos ORM de la consola de plataforma (spec 017, T1; plan.md §3).

El esquema lo crea la migración ``0017_plataforma``; estos modelos solo lo describen.
Ninguno es ``TenantScoped``: son excepciones cerradas del catálogo (no se filtran por el
tenant de la sesión, sino por el desarrollador de la sesión en RLS). ``plataforma_auditoria``
tiene un ``tenant_id`` informativo (nulo si la acción no es de una empresa).

La aplicación no puede leer ``desarrollador.password_hash`` ni ``creado_en`` (``GRANT``
por columna): se mapean diferidos con ``raiseload`` para que ningún ``SELECT`` del ORM los
pida.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, FetchedValue, LargeBinary, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.models import Base


class Desarrollador(Base):
    __tablename__ = "desarrollador"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=FetchedValue())
    email: Mapped[str] = mapped_column(Text)
    nombre: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text, deferred=True, deferred_raiseload=True)
    activo: Mapped[bool] = mapped_column(server_default=FetchedValue())
    # T2 (hallazgo c de T1): la aplicación tampoco tiene SELECT sobre ``creado_en``; diferida
    # con raiseload para que ``select(Desarrollador)`` no la pida (permiso denegado).
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=FetchedValue(),
        deferred=True,
        deferred_raiseload=True,
    )


class PlataformaRefreshToken(Base):
    __tablename__ = "plataforma_refresh_token"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    desarrollador_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    familia_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary)
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=FetchedValue()
    )


class PlataformaAuditoria(Base):
    """Auditoría de solo inserción (R33–R34): sin texto libre ni datos personales."""

    __tablename__ = "plataforma_auditoria"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=FetchedValue())
    desarrollador_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    accion: Mapped[str] = mapped_column(Text)
    resultado: Mapped[str] = mapped_column(Text)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    objeto_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=FetchedValue()
    )
