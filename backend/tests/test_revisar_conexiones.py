"""``flask revisar-conexiones`` (spec 010c, T2; R2): cada conexión, sin mostrar valores."""

from click.testing import CliRunner
from conftest import read_database_url

from app import conexiones
from app.cli import revisar_conexiones_command


def _url(nombre: str) -> str:
    url = read_database_url(nombre)
    assert url is not None
    return url.render_as_string(hide_password=False)


def test_good_app_and_migrator_connections():
    app, migrador = _url("TEST_DATABASE_URL"), _url("TEST_MIGRATION_DATABASE_URL")
    filas = {
        f.variable: f
        for f in conexiones.revisar({"DATABASE_URL": app, "MIGRATION_DATABASE_URL": migrador})
    }
    assert filas["DATABASE_URL"].configurada and filas["DATABASE_URL"].rol
    assert "rol de la app" not in filas["DATABASE_URL"].motivo
    assert filas["MIGRATION_DATABASE_URL"].rol != filas["DATABASE_URL"].rol
    assert filas["SUPABASE_DATABASE_URL"].configurada is False


def test_app_url_with_a_superuser_is_flagged():
    migrador = _url("TEST_MIGRATION_DATABASE_URL")
    (fila,) = [
        f for f in conexiones.revisar({"DATABASE_URL": migrador}) if f.variable == "DATABASE_URL"
    ]
    assert fila.ok is False
    assert "superusuario" in fila.motivo


def test_wrong_password_says_so_without_showing_it():
    url = read_database_url("TEST_DATABASE_URL").set(password="no-es-la-clave-1234")
    texto = url.render_as_string(hide_password=False)
    (fila,) = [
        f for f in conexiones.revisar({"DATABASE_URL": texto}) if f.variable == "DATABASE_URL"
    ]
    assert fila.ok is False
    assert fila.motivo == "usuario o contraseña incorrectos"


def test_cli_never_prints_urls_or_passwords(monkeypatch):
    nombres = ("TEST_DATABASE_URL", "TEST_MIGRATION_DATABASE_URL")
    app, migrador = (_url(n) for n in nombres)
    claves = [read_database_url(n).password for n in nombres]
    for nombre, _, _ in conexiones.VARIABLES:
        monkeypatch.delenv(nombre, raising=False)
    monkeypatch.setenv("DATABASE_URL", app)
    monkeypatch.setenv("MIGRATION_DATABASE_URL", migrador)
    salida = CliRunner().invoke(revisar_conexiones_command, []).output
    assert "DATABASE_URL" in salida
    assert "Migraciones del repo" in salida
    for secreto in (*claves, "localhost", "127.0.0.1"):
        assert secreto not in salida


def test_test_database_without_alembic_table_is_ok():
    # La base de pruebas nunca se migra (cada prueba crea la suya): no tiene
    # alembic_version y la revisión no debe fallar por eso (sqlstate 42P01).
    sin_migrar = {
        n: read_database_url(n).set(database="postgres").render_as_string(hide_password=False)
        for n in ("TEST_DATABASE_URL", "TEST_MIGRATION_DATABASE_URL")
    }
    filas = {f.variable: f for f in conexiones.revisar(sin_migrar)}
    for nombre in sin_migrar:
        assert filas[nombre].ok, filas[nombre].motivo
        assert filas[nombre].revision == "—"


def test_unmigrated_database_is_reported_not_crashing():
    url = read_database_url("TEST_MIGRATION_DATABASE_URL").set(database="postgres")
    texto = url.render_as_string(hide_password=False)
    (fila,) = [
        f
        for f in conexiones.revisar({"MIGRATION_DATABASE_URL": texto})
        if f.variable == "MIGRATION_DATABASE_URL"
    ]
    assert fila.ok is False
    assert fila.motivo == "base sin migrar"
