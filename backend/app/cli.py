"""Comandos del operador (spec 002, T5; R6; plan.md §2.3).

``flask create-tenant <nombre> <email>`` crea un ``tenant`` y la primera
invitación ``admin`` (24 h, ``creada_por`` NULL; Q3, Q17):

- Genera el token (``new_token``), calcula ``clave = sha256(token)`` en hex
  (``token_key``) y solo envía la clave a ``acceso.crear_tenant``, que en una
  transacción crea el tenant y la invitación y guarda ``sha256(clave)`` (I1). No
  hace ``INSERT`` directo ni fija el tenant: el migrador no tiene política bajo
  ``FORCE RLS``.
- Se conecta con el rol migrador de ``MIGRATION_DATABASE_URL`` (solo por entorno,
  Q5): el comando no acepta URL, contraseña ni rol por argumentos, y falla si esa
  URL usa el mismo rol que ``DATABASE_URL``. El servicio ``api`` no recibe esa
  variable (README), así que ahí no corre.
- Muestra el enlace ``/invitacion#<token>`` (Q13) una sola vez por la salida
  estándar, después de confirmar la transacción. No lo guarda ni lo registra en
  logs; un error de base se informa solo con su tipo y ``sqlstate`` (el mensaje de
  PostgreSQL podría traer valores de fila).
"""

import click
import psycopg
from flask import Flask
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from app.auth.credentials import new_token, token_key
from app.config import (
    InvalidDatabaseUrlError,
    MissingConfigError,
    SameDatabaseRoleError,
    load_migration_url,
)
from app.invitaciones.service import normalize_invitation_email

INVITATION_LINK_PREFIX = "/invitacion#"
CONNECT_TIMEOUT_SECONDS = 5
_CREAR_TENANT = text("select acceso.crear_tenant(:nombre, :email, :clave)")


def _database_error_summary(exc: BaseException) -> str:
    """Tipo y ``sqlstate``; nunca el mensaje, el SQL ni los parámetros."""
    orig = exc if isinstance(exc, psycopg.Error) else getattr(exc, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None) or "desconocido"
    return f"{type(exc).__name__}, sqlstate {sqlstate}"


@click.command("create-tenant")
@click.argument("nombre")
@click.argument("email")
def create_tenant_command(nombre: str, email: str) -> None:
    """Crea un tenant y la invitación de su primer admin (24 h).

    Usa el rol migrador de MIGRATION_DATABASE_URL (solo por entorno) y muestra el
    enlace de la invitación una sola vez.
    """
    nombre = nombre.strip()
    if not nombre:
        raise click.ClickException("El nombre del tenant no puede estar vacío.")
    # Mismo normalizador que la API (N1/H3 de T9): su salida cumple el CHECK de la base.
    normalized_email = normalize_invitation_email(email)
    if normalized_email is None:
        raise click.ClickException("El email del primer admin no es válido.")

    config_error: str | None = None
    try:
        url = load_migration_url()
    except (MissingConfigError, SameDatabaseRoleError, InvalidDatabaseUrlError) as exc:
        # Los mensajes nombran la variable, nunca su valor.
        config_error = str(exc)
    if config_error is not None:
        raise click.ClickException(config_error)

    token = new_token()
    engine = create_engine(
        url,
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
    )
    failure: str | None = None
    tenant_id = None
    try:
        with engine.begin() as conn:
            tenant_id = conn.scalar(
                _CREAR_TENANT,
                {"nombre": nombre, "email": normalized_email, "clave": token_key(token)},
            )
    except (SQLAlchemyError, psycopg.Error) as exc:
        failure = _database_error_summary(exc)
    finally:
        engine.dispose()
    if failure is not None:
        # Fuera del except: sin causa ni contexto que arrastren SQL o valores.
        raise click.ClickException(f"No se pudo crear el tenant ({failure}).")

    click.echo(f"Tenant creado: {tenant_id}")
    click.echo(
        "Enlace de invitación del primer admin (vence en 24 h). Se muestra una sola vez "
        "y no se guarda: antepón la dirección de la web y compártelo solo con esa persona."
    )
    click.echo(f"{INVITATION_LINK_PREFIX}{token}")


def register_cli(app: Flask) -> None:
    """Registra los comandos del operador en ``flask``."""
    app.cli.add_command(create_tenant_command)
