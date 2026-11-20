"""Modelos ORM de acceso y usuarios (spec 002, T1; docs/03).

El esquema lo crea la migración ``0002_acceso_y_usuarios``; estos modelos solo lo
describen (nunca se usa ``create_all``). ``membresia``, ``invitacion`` y
``refresh_token`` son ``TenantScoped``: el filtro central de ``app.db`` y RLS
los acotan al tenant de la sesión. ``tenant`` y ``usuario`` no tienen
``tenant_id`` (excepciones del catálogo); RLS los acota por ``id`` y por
membresía.

El rol de la aplicación no puede leer ``usuario.password_hash`` ni
``invitacion.token_hash`` (``GRANT`` por columna): se mapean diferidos con
``raiseload`` para que ningún ``SELECT`` del ORM los pida.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, FetchedValue, LargeBinary, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db import TenantScoped


class Base(DeclarativeBase):
    """Base declarativa de los modelos de acceso."""


class Tenant(Base):
    __tablename__ = "tenant"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    nombre: Mapped[str] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=FetchedValue()
    )
    # Spec 017, T1 (0017): estado de la empresa; solo lo cambia la consola de plataforma.
    activo: Mapped[bool] = mapped_column(server_default=FetchedValue())
    desactivado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=FetchedValue()
    )
    desactivado_por: Mapped[uuid.UUID | None] = mapped_column(Uuid, server_default=FetchedValue())


class Usuario(Base):
    __tablename__ = "usuario"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text)
    nombre: Mapped[str] = mapped_column(Text)
    password_hash: Mapped[str] = mapped_column(Text, deferred=True, deferred_raiseload=True)
    activo: Mapped[bool]
    # Spec 017, T1 (0017): la aplicación aún no tiene SELECT sobre la columna (lo da T4);
    # diferida con raiseload para que ningún SELECT del ORM la pida.
    debe_cambiar_password: Mapped[bool] = mapped_column(
        server_default=FetchedValue(), deferred=True, deferred_raiseload=True
    )


class Membresia(TenantScoped, Base):
    __tablename__ = "membresia"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    usuario_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    rol: Mapped[str] = mapped_column(Text)
    activa: Mapped[bool]


class Invitacion(TenantScoped, Base):
    __tablename__ = "invitacion"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(Text)
    rol: Mapped[str] = mapped_column(Text)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, deferred=True, deferred_raiseload=True)
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # FetchedValue: el ORM no la incluye en el INSERT (la aplicación no tiene
    # INSERT sobre usada_en; nace NULL en la base y solo la marca aceptar_invitacion).
    usada_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=FetchedValue()
    )
    creada_por: Mapped[uuid.UUID | None] = mapped_column(Uuid)


class RefreshToken(TenantScoped, Base):
    __tablename__ = "refresh_token"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    membresia_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    familia_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary)
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revocado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=FetchedValue()
    )


class RecuperacionContrasena(TenantScoped, Base):
    """Enlace de recuperación de contraseña (spec 014; migración ``0015``).

    Solo describe el esquema: la aplicación no tiene ningún privilegio sobre la tabla
    (R15) y la opera únicamente por las funciones ``acceso.*`` (T2). ``token_hash`` se
    mapea diferido con ``raiseload`` para que ningún ``SELECT`` del ORM lo pida.
    """

    __tablename__ = "recuperacion_contrasena"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, server_default=FetchedValue())
    usuario_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    token_hash: Mapped[bytes] = mapped_column(LargeBinary, deferred=True, deferred_raiseload=True)
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=FetchedValue()
    )
