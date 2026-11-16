"""Comandos del operador (spec 002, T5; R6; plan.md §2.3).

``flask purgar-limite-tasa`` (T10, Q10) borra las ventanas de ``limite_tasa`` de
más de un día, con el mismo rol migrador y las mismas reglas de entorno y errores.

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

``flask preparar-roles`` (spec 010b, T4; C8) crea o reafirma el rol de la aplicación y
``auth_owner`` en un PostgreSQL administrado donde el migrador no es superusuario
(Supabase), con el usuario y la contraseña solo por entorno (``APP_DB_USER``,
``APP_DB_PASSWORD``) y la contraseña enviada como verificador SCRAM (``app.roles``).
"""

import os

import click
import psycopg
from flask import Flask
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from app import conexiones, roles
from app.auth.credentials import new_token, token_key
from app.config import (
    InvalidDatabaseUrlError,
    MissingConfigError,
    SameDatabaseRoleError,
    load_migration_url,
)
from app.invitaciones.service import normalize_invitation_email
from app.nombres import NOMBRE_MAX_LENGTH, normalize_display_name

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
    # Cambio H-3: mismo normalizador que el nombre de usuario (la web muestra ambos).
    normalized_nombre = normalize_display_name(nombre)
    if normalized_nombre is None:
        raise click.ClickException(
            f"El nombre del tenant no es válido: de 1 a {NOMBRE_MAX_LENGTH} caracteres, con "
            "letras o números y sin caracteres invisibles o de control."
        )
    nombre = normalized_nombre
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


# Misma condición que las políticas de purga de 0005: nunca una ventana vigente.
_PURGAR_LIMITE_TASA = text(
    "delete from limite_tasa where ventana_inicio < now() - interval '1 day'"
)


@click.command("purgar-limite-tasa")
def purge_rate_limit_command() -> None:
    """Borra las ventanas de límite de tasa de más de un día (T10, Q10, R5).

    Lo ejecuta el operador con el rol migrador de MIGRATION_DATABASE_URL (solo por
    entorno): es el único rol con DELETE en limite_tasa. No acepta argumentos.
    """
    config_error: str | None = None
    try:
        url = load_migration_url()
    except (MissingConfigError, SameDatabaseRoleError, InvalidDatabaseUrlError) as exc:
        config_error = str(exc)
    if config_error is not None:
        raise click.ClickException(config_error)

    engine = create_engine(
        url,
        poolclass=NullPool,
        hide_parameters=True,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
    )
    failure: str | None = None
    deleted = 0
    try:
        with engine.begin() as conn:
            deleted = conn.execute(_PURGAR_LIMITE_TASA).rowcount
    except (SQLAlchemyError, psycopg.Error) as exc:
        failure = _database_error_summary(exc)
    finally:
        engine.dispose()
    if failure is not None:
        raise click.ClickException(f"No se pudo purgar limite_tasa ({failure}).")
    click.echo(f"Ventanas de límite de tasa purgadas (más de un día): {deleted}")


@click.command("preparar-roles")
def preparar_roles_command() -> None:
    """Crea o reafirma el rol de la aplicación y auth_owner (Supabase u otro administrado).

    Usa el rol migrador de MIGRATION_DATABASE_URL y lee APP_DB_USER y APP_DB_PASSWORD
    solo del entorno. La contraseña viaja como verificador SCRAM, nunca en claro.
    """
    config_error: str | None = None
    try:
        url = load_migration_url()
    except (MissingConfigError, SameDatabaseRoleError, InvalidDatabaseUrlError) as exc:
        config_error = str(exc)
    if config_error is not None:
        raise click.ClickException(config_error)
    app_user = (os.environ.get("APP_DB_USER") or "").strip()
    contrasena = os.environ.get("APP_DB_PASSWORD") or ""
    if not app_user or not contrasena:
        raise click.ClickException("Faltan APP_DB_USER o APP_DB_PASSWORD en el entorno.")
    conninfo = make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)
    failure: str | None = None
    try:
        resultado = roles.preparar(conninfo, app_user, contrasena)
    except roles.ErrorRoles as exc:
        failure = str(exc)
    except psycopg.Error as exc:
        failure = f"error de base ({_database_error_summary(exc)})"
    if failure is not None:
        raise click.ClickException(f"No se pudieron preparar los roles: {failure}")
    estado = "creado" if resultado.creado else "actualizado"
    click.echo(
        f"Rol de la aplicación {estado} y auth_owner listo; "
        f"membresías revocadas: {resultado.revocadas}; conservadas (solo ADMIN del creador): "
        f"{resultado.conservadas}."
    )


@click.command("revisar-conexiones")
def revisar_conexiones_command() -> None:
    """Prueba cada conexión de base del entorno y dice si está bien (sin mostrar valores)."""
    filas = conexiones.revisar()
    click.echo(f"Migraciones del repo: {conexiones.revision_del_repo()}")
    for f in filas:
        if not f.configurada:
            click.echo(f"  ·  {f.variable}: no configurada")
            continue
        marca = "OK " if f.ok else "MAL"
        detalle = (
            f"rol {f.rol}, base {f.base}, TLS {'sí' if f.tls else 'no'}, migración {f.revision}"
            if f.rol
            else ""
        )
        click.echo(f"  {marca} {f.variable}: {f.motivo}" + (f" ({detalle})" if detalle else ""))
    if any(f.configurada and not f.ok for f in filas):
        raise SystemExit(1)


def register_cli(app: Flask) -> None:
    """Registra los comandos del operador en ``flask``."""
    app.cli.add_command(create_tenant_command)
    app.cli.add_command(purge_rate_limit_command)
    app.cli.add_command(preparar_roles_command)
    app.cli.add_command(revisar_conexiones_command)
