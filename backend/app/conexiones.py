"""``flask revisar-conexiones`` (spec 010c, T2; R2): ¿funciona cada conexión del entorno?

Prueba cada URL de base que exista en el entorno y dice, sin mostrar nunca la URL, el
host ni la contraseña: si conecta, con qué rol, si es el rol esperado (la aplicación sin
superusuario ni ``BYPASSRLS``; el migrador distinto de la aplicación), si la conexión va
cifrada (TLS) y en qué revisión de migraciones está esa base frente a la del repo.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import psycopg
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

# (variable, tipo de rol esperado, variable del otro rol de la misma base)
VARIABLES: tuple[tuple[str, str, str], ...] = (
    ("DATABASE_URL", "aplicacion", "MIGRATION_DATABASE_URL"),
    ("MIGRATION_DATABASE_URL", "migrador", "DATABASE_URL"),
    ("TEST_DATABASE_URL", "aplicacion", "TEST_MIGRATION_DATABASE_URL"),
    ("TEST_MIGRATION_DATABASE_URL", "migrador", "TEST_DATABASE_URL"),
    ("SUPABASE_DATABASE_URL", "aplicacion", "SUPABASE_MIGRATION_DATABASE_URL"),
    ("SUPABASE_MIGRATION_DATABASE_URL", "migrador", "SUPABASE_DATABASE_URL"),
)


@dataclass(frozen=True)
class Fila:
    variable: str
    configurada: bool
    ok: bool
    rol: str = ""
    base: str = ""
    tls: bool | None = None
    revision: str = ""
    motivo: str = ""


def revision_del_repo() -> str:
    raiz = Path(__file__).resolve().parents[1]
    config = AlembicConfig(str(raiz / "alembic.ini"))
    config.set_main_option("script_location", str(raiz / "migrations"))
    return ScriptDirectory.from_config(config).get_current_head() or ""


def _usuario(url: str) -> str | None:
    try:
        return make_url(url).username
    except ArgumentError:
        return None


def _revisar_una(
    variable: str, tipo: str, otra: str, environ: Mapping[str, str], cabeza: str
) -> Fila:
    url = (environ.get(variable) or "").strip()
    if not url:
        return Fila(variable, configurada=False, ok=True, motivo="no configurada")
    try:
        libpq = make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)
    except ArgumentError:
        return Fila(
            variable, configurada=True, ok=False, motivo="la URL no tiene un formato válido"
        )
    try:
        with psycopg.connect(libpq, connect_timeout=5) as conn:
            rol, base, superusuario, bypass = conn.execute(
                "select current_user, current_database(), rolsuper, rolbypassrls "
                "from pg_roles where rolname = current_user"
            ).fetchone()  # type: ignore[misc]
            (tls,) = conn.execute(
                "select coalesce((select ssl from pg_stat_ssl where pid = pg_backend_pid()), false)"
            ).fetchone()  # type: ignore[misc]
            (existe, legible) = conn.execute(
                "select to_regclass('public.alembic_version') is not null, "
                "coalesce(has_table_privilege('public.alembic_version', 'SELECT'), false)"
            ).fetchone()  # type: ignore[misc]
            # El rol de la app no lee alembic_version (no le hace falta): la revisión la
            # informa la línea del migrador de la misma base.
            version = (
                conn.execute("select max(version_num) from alembic_version").fetchone()[0]  # type: ignore[index]
                if existe and legible
                else None
            )
    except psycopg.OperationalError as exc:
        texto = str(exc).lower()
        if "password" in texto or "authentication" in texto:
            motivo = "usuario o contraseña incorrectos"
        elif "does not exist" in texto:
            motivo = "la base o el rol no existen"
        elif "timeout" in texto or "timed out" in texto:
            motivo = "sin respuesta en 5 s (¿está encendida la base?)"
        else:
            motivo = "no se pudo conectar (¿Docker apagado, host o puerto mal?)"
        return Fila(variable, configurada=True, ok=False, motivo=motivo)
    except psycopg.Error as exc:
        estado = getattr(exc, "sqlstate", None) or "desconocido"
        return Fila(
            variable, configurada=True, ok=False, motivo=f"error de base (sqlstate {estado})"
        )

    problemas = []
    if tipo == "aplicacion" and (superusuario or bypass):
        problemas.append("el rol de la app no debe ser superusuario ni saltarse el RLS")
    if _usuario(environ.get(otra, "") or "") == rol:
        problemas.append(f"usa el mismo rol que {otra}")
    # La base de pruebas no se migra: cada prueba crea y migra su propia base temporal.
    if variable.startswith("TEST_"):
        pass
    elif version is None and (tipo == "migrador" or not existe):
        problemas.append("base sin migrar")
    elif version is not None and version != cabeza:
        problemas.append(f"migraciones atrasadas (repo: {cabeza})")
    if variable.startswith("SUPABASE") and not tls:
        problemas.append("Supabase sin TLS (agrega ?sslmode=require)")
    return Fila(
        variable,
        configurada=True,
        ok=not problemas,
        rol=rol,
        base=base,
        tls=bool(tls),
        revision=version or ("(la lee el migrador)" if existe else "—"),
        motivo="; ".join(problemas) or "bien",
    )


def revisar(environ: Mapping[str, str] | None = None) -> list[Fila]:
    fuente = os.environ if environ is None else environ
    cabeza = revision_del_repo()
    return [_revisar_una(v, t, o, fuente, cabeza) for v, t, o in VARIABLES]
