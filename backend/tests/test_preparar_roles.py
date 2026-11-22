"""``flask preparar-roles`` (spec 010b, T4; R5, C8): la contraseña viaja como SCRAM.

Aquí el migrador local es superusuario; el caso de Supabase (migrador sin superusuario)
lo cubre ``test_c8_supabase.py`` en el trabajo ``c8`` de la CI.
"""

import re
import uuid

import psycopg
import pytest
from click.testing import CliRunner
from conftest import read_database_url

from app import roles
from app.cli import preparar_roles_command


def test_scram_verifier_has_postgres_format():
    v = roles.verificador_scram("Clave-de-prueba-larga-0123456789", sal=b"\x00" * 16)
    assert re.fullmatch(
        r"SCRAM-SHA-256\$4096:[A-Za-z0-9+/=]{24}\$[A-Za-z0-9+/=]{44}:[A-Za-z0-9+/=]{44}", v
    )
    assert v == roles.verificador_scram("Clave-de-prueba-larga-0123456789", sal=b"\x00" * 16)
    assert "Clave" not in v


@pytest.mark.parametrize(
    ("usuario", "contrasena", "texto"),
    [
        ("App-Rol", "x" * 30, "identificador"),
        ("migrador", "x" * 30, "migrador"),
        ("auth_owner", "x" * 30, "migrador"),
        ("plataforma_owner", "x" * 30, "plataforma_owner"),
        ("app", "corta", "24"),
        ("app", "ñ" * 30, "ASCII"),
        ("app", "con espacios " * 3, "ASCII"),
    ],
)
def test_invalid_names_and_passwords_are_refused(usuario, contrasena, texto):
    with pytest.raises(roles.ErrorRoles, match=texto):
        roles.validar(usuario, contrasena, "migrador")


def test_creates_a_role_that_logs_in_with_scram_and_is_idempotent():
    migrador = read_database_url("TEST_MIGRATION_DATABASE_URL")
    if migrador is None:
        pytest.skip("sin base de pruebas")
    conninfo = migrador.set(drivername="postgresql").render_as_string(hide_password=False)
    usuario = f"c8_prueba_{uuid.uuid4().hex[:8]}"
    contrasena = f"Clave-{uuid.uuid4().hex}"
    try:
        primero = roles.preparar(conninfo, usuario, contrasena)
        assert primero.creado is True
        segundo = roles.preparar(conninfo, usuario, contrasena + "x")
        assert segundo.creado is False
        app = migrador.set(drivername="postgresql", username=usuario, password=contrasena + "x")
        with psycopg.connect(app.render_as_string(hide_password=False), connect_timeout=5) as conn:
            assert conn.execute("select current_user").fetchone() == (usuario,)
            fila = conn.execute(
                "select rolsuper, rolbypassrls, rolcreaterole, rolcreatedb from pg_roles "
                "where rolname = current_user"
            ).fetchone()
            assert fila == (False, False, False, False)
    finally:
        with psycopg.connect(conninfo, autocommit=True) as conn:
            conn.execute(
                psycopg.sql.SQL("DROP OWNED BY {}").format(psycopg.sql.Identifier(usuario))
            )
            conn.execute(
                psycopg.sql.SQL("DROP ROLE IF EXISTS {}").format(psycopg.sql.Identifier(usuario))
            )


def test_cli_needs_user_and_password_from_the_environment(monkeypatch):
    monkeypatch.setenv("MIGRATION_DATABASE_URL", "postgresql+psycopg://m:x@localhost/db")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://a:x@localhost/db")
    monkeypatch.delenv("APP_DB_PASSWORD", raising=False)
    resultado = CliRunner().invoke(preparar_roles_command, [])
    assert resultado.exit_code != 0
    assert "APP_DB_USER o APP_DB_PASSWORD" in resultado.output
