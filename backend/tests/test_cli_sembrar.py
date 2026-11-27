"""Pruebas de ``flask sembrar-demo``: activos sintéticos solo en local.

Sobre una base temporal con dos tenants (acceso_db): el comando usa el alta de
dominio (evento ``creado``, códigos ``DEMO-*``) y es idempotente. No usa el Excel
de la clínica. En production/staging no corre.
"""

from collections.abc import Iterator

import pytest
from acceso_db import (
    ADMIN_A,
    CONTADOR_A,
    SECRET_KEY,
    TENANT_A,
    TENANT_B,
    AccesoDb,
    dispose,
    make_app,
    temporary_acceso_db,
)
from flask import Flask
from sqlalchemy import text

from app import create_app
from app.config import Config
from app.sembrar import ACTIVOS_DEMO, CODIGO_PREFIJO


@pytest.fixture(scope="module")
def db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("cli_sembrar")


@pytest.fixture(scope="module")
def app(db: AccesoDb) -> Iterator[Flask]:
    flask_app = make_app(db)
    yield flask_app
    dispose(flask_app)


def contar(db: AccesoDb, tenant_id) -> int:
    with db.migrator.connect() as conn:
        return conn.scalar(
            text("select count(*) from activo where tenant_id = :t and codigo like :p"),
            {"t": tenant_id, "p": f"{CODIGO_PREFIJO}%"},
        )


def test_sembrar_demo_creates_synthetic_assets_and_is_idempotent(db, app):
    primero = app.test_cli_runner().invoke(args=["sembrar-demo", ADMIN_A.email])
    assert primero.exit_code == 0, primero.output
    assert f"{len(ACTIVOS_DEMO)} activos nuevos" in primero.output
    assert contar(db, TENANT_A) == len(ACTIVOS_DEMO)
    assert contar(db, TENANT_B) == 0
    with db.migrator.connect() as conn:
        tipos = (
            conn.execute(
                text("select tipo from activo_evento where tenant_id = :t"), {"t": TENANT_A}
            )
            .scalars()
            .all()
        )
    assert set(tipos) == {"creado"}
    assert len(tipos) == len(ACTIVOS_DEMO)
    assert "SEM-" not in primero.output

    segundo = app.test_cli_runner().invoke(args=["sembrar-demo", ADMIN_A.email])
    assert segundo.exit_code == 0, segundo.output
    assert "ya estaban" in segundo.output
    assert contar(db, TENANT_A) == len(ACTIVOS_DEMO)


def test_sembrar_demo_rejects_a_counter(app):
    result = app.test_cli_runner().invoke(args=["sembrar-demo", CONTADOR_A.email])
    assert result.exit_code != 0
    assert "administrador activo" in result.output


def test_sembrar_demo_rejects_an_unknown_email(app):
    result = app.test_cli_runner().invoke(args=["sembrar-demo", "nadie@ejemplo.test"])
    assert result.exit_code != 0
    assert "administrador activo" in result.output


def test_sembrar_demo_does_not_run_outside_local_environments(db):
    app = create_app(
        Config(
            database_url=db.app_url.render_as_string(hide_password=False),
            secret_key=SECRET_KEY,
            environment="staging",
        )
    )
    try:
        result = app.test_cli_runner().invoke(args=["sembrar-demo", ADMIN_A.email])
        assert result.exit_code != 0
        assert "solo se admite en development" in result.output
    finally:
        dispose(app)
