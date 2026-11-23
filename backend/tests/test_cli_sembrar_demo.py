"""``flask sembrar-demo``: datos de demostración por la API con la cuenta de un admin.

Sobre una base temporal migrada a ``head`` (tenants sintéticos A y B de ``acceso_db``):
crea salas, categorías y activos ``SEM-…`` por las rutas de la app y una sesión de conteo
cerrada; repetir no duplica activos; ``--sin-sesion`` no abre sesión; una contraseña mala,
un contador o ``ENVIRONMENT=production`` no siembran nada; la otra empresa queda intacta
y la contraseña nunca sale por la salida.

Datos sintéticos (``@ejemplo.test``).
"""

import re
from collections.abc import Iterator
from decimal import Decimal
from types import SimpleNamespace

import pytest
from acceso_db import (
    ADMIN_A,
    CONTADOR_A,
    PASSWORD,
    TENANT_A,
    TENANT_B,
    AccesoDb,
    dispose,
    make_app,
    temporary_acceso_db,
)
from flask import Flask
from sqlalchemy import text

from app import cli as app_cli
from app.config import RateLimits

HIGH = RateLimits(login_account=1000, login_ip=1000, refresh_ip=1000)


@pytest.fixture(scope="module")
def demo_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("sembrar_demo")


@pytest.fixture(scope="module")
def demo_app(demo_db) -> Iterator[Flask]:
    flask_app = make_app(demo_db, rate_limits=HIGH)
    yield flask_app
    dispose(flask_app)


def _sembrar(app: Flask, *args: str, email: str = ADMIN_A.email, password: str = PASSWORD):
    return app.test_cli_runner().invoke(
        args=["sembrar-demo", email, "--password-stdin", *args], input=f"{password}\n"
    )


def _uno(db: AccesoDb, sql: str, params: dict | None = None):
    with db.migrator.connect() as conn:
        return conn.scalar(text(sql), params or {})


def _activos_demo(db: AccesoDb, tenant) -> int:
    return _uno(
        db,
        "select count(*) from activo where tenant_id = :t and codigo like 'SEM-%'",
        {"t": tenant},
    )


def _sesiones(db: AccesoDb, tenant) -> list[dict]:
    with db.migrator.connect() as conn:
        rows = conn.execute(
            text("select * from sesion_conteo where tenant_id = :t order by abierta_en"),
            {"t": tenant},
        ).mappings()
        return [dict(r) for r in rows]


def test_seeds_assets_and_a_closed_session_through_the_api(demo_app, demo_db):
    antes_b = _uno(demo_db, "select count(*) from activo where tenant_id = :t", {"t": TENANT_B})

    resultado = _sembrar(demo_app, "--activos", "12")

    assert resultado.exit_code == 0, resultado.output
    assert "Activos: 12 nuevos, 0 ya existían" in resultado.output
    assert _activos_demo(demo_db, TENANT_A) == 12
    # Por la API: cada activo tiene su evento de alta.
    eventos = _uno(
        demo_db,
        "select count(*) from activo_evento e join activo a on a.id = e.activo_id "
        "where a.tenant_id = :t and a.codigo like 'SEM-%'",
        {"t": TENANT_A},
    )
    assert eventos >= 12
    (sesion,) = [s for s in _sesiones(demo_db, TENANT_A) if s["nombre"].startswith("Conteo de")]
    assert sesion["cerrada_en"] is not None
    assert "Sesión cerrada" in resultado.output
    assert PASSWORD not in resultado.output
    # La otra empresa no cambia.
    assert _uno(demo_db, "select count(*) from activo where tenant_id = :t", {"t": TENANT_B}) == (
        antes_b
    )


def test_running_again_does_not_duplicate_assets(demo_app, demo_db):
    assert _sembrar(demo_app, "--activos", "12", "--sin-sesion").exit_code == 0
    antes = len(_sesiones(demo_db, TENANT_A))

    resultado = _sembrar(demo_app, "--activos", "12", "--sin-sesion")

    assert resultado.exit_code == 0, resultado.output
    assert "Activos: 0 nuevos, 12 ya existían" in resultado.output
    assert "Ubicaciones creadas: ninguna" in resultado.output
    assert "Categorías creadas: ninguna" in resultado.output
    assert _activos_demo(demo_db, TENANT_A) == 12
    assert len(_sesiones(demo_db, TENANT_A)) == antes


def test_closed_session_totals_add_up(demo_app, demo_db):
    resultado = _sembrar(demo_app, "--activos", "20")

    assert resultado.exit_code == 0, resultado.output
    linea = next(x for x in resultado.output.splitlines() if x.startswith("Sesión cerrada"))
    cifras = dict(re.findall(r"(registrado|no encontrado|encontrado) ([0-9.]+)", linea))
    assert Decimal(cifras["encontrado"]) + Decimal(cifras["no encontrado"]) == Decimal(
        cifras["registrado"]
    )
    assert Decimal(cifras["no encontrado"]) > 0


@pytest.mark.parametrize(
    ("email", "password", "mensaje"),
    [
        (ADMIN_A.email, "Clave-Incorrecta-123", "correo o contraseña incorrectos"),
        (CONTADOR_A.email, PASSWORD, "debe ser admin"),
    ],
)
def test_wrong_password_or_non_admin_seeds_nothing(demo_db, email, password, mensaje):
    db_app = make_app(demo_db, rate_limits=HIGH)
    try:
        antes = _uno(demo_db, "select count(*) from activo")
        antes_ubic = _uno(demo_db, "select count(*) from ubicacion")

        resultado = _sembrar(db_app, email=email, password=password)

        assert resultado.exit_code != 0
        assert mensaje in resultado.output
        assert password not in resultado.output
        assert _uno(demo_db, "select count(*) from activo") == antes
        assert _uno(demo_db, "select count(*) from ubicacion") == antes_ubic
    finally:
        dispose(db_app)


def test_refuses_to_run_in_production(demo_app, demo_db, monkeypatch):
    monkeypatch.setattr(
        app_cli, "get_config", lambda _app: SimpleNamespace(environment="production")
    )
    antes = _uno(demo_db, "select count(*) from activo")

    resultado = _sembrar(demo_app)

    assert resultado.exit_code != 0
    assert "ENVIRONMENT=production" in resultado.output
    assert _uno(demo_db, "select count(*) from activo") == antes


def test_amount_out_of_range_is_rejected(demo_app):
    resultado = _sembrar(demo_app, "--activos", "0")

    assert resultado.exit_code != 0
    assert "va de 1 a 500" in resultado.output
