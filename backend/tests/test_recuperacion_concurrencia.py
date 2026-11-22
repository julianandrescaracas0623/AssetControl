"""Concurrencia y aislamiento de restablecer contraseña por HTTP (spec 014, T8; A3, A11; I2 de
las «Notas de cierre T4»).

- Dos canjes **simultáneos** del mismo token desde dos clientes: el migrador retiene la fila
  del enlace con ``FOR UPDATE`` hasta que las dos peticiones esperan ese candado en la base;
  al soltarlo, exactamente una responde ``204`` y la otra el mismo ``400 enlace_invalido``;
  queda vigente una sola contraseña (la de la ganadora) y el token no se puede reusar.
- Un token del tenant B usado desde una sesión del tenant A (``Authorization`` y cookie de A)
  solo cambia la contraseña y las sesiones de la cuenta de B: la ruta no mira la sesión.

La espera del candado se lee en ``pg_stat_activity`` con el migrador (superusuario local; la
misma dependencia que ``test_recuperacion_funciones.py::_wait_until_blocked``).
Datos sintéticos (``@ejemplo.test``).
"""

import threading
import time
from collections.abc import Iterator

import pytest
from acceso_db import PASSWORD, TENANT_A, TENANT_B, dispose, temporary_acceso_db
from flask import Flask
from sqlalchemy import text
from test_recuperacion_endpoints import (
    CSRF,
    INVALID_LINK,
    NUEVA,
    OTRA_NUEVA,
    RESTABLECER,
    Envios,
    build_app,
    crear_cuenta,
    enlace,
    error_of,
    login,
    password_hash_de,
    refrescar,
    refresh_cookie,
    restablecer,
    token_por_correo,
)

from app.auth.credentials import token_storage_hash
from app.correo import get_correo

TERCERA = "Tercera-Clave-Recuperada-14"


@pytest.fixture(scope="module")
def rec_db(database_residue_guard):
    yield from temporary_acceso_db("rec_conc")


@pytest.fixture(scope="module")
def rec_app(rec_db, tmp_path_factory) -> Iterator[Flask]:
    flask_app = build_app(rec_db, tmp_path_factory.mktemp("buzon"))
    yield flask_app
    get_correo(flask_app).esperar(5)
    dispose(flask_app)


@pytest.fixture
def client(rec_app):
    return rec_app.test_client(use_cookies=False)


@pytest.fixture
def envios(rec_app, rec_db, monkeypatch) -> Envios:
    correo = get_correo(rec_app)
    spy = Envios(rec_db, correo.enviar_recuperacion)
    monkeypatch.setattr(correo, "enviar_recuperacion", spy)
    return spy


@pytest.fixture(autouse=True)
def limpio(rec_db) -> None:
    with rec_db.migrator.begin() as conn:
        conn.execute(text("delete from limite_tasa"))


def _esperando_candado(db) -> int:
    with db.migrator.connect() as conn:
        return conn.scalar(
            text(
                "select count(*) from pg_stat_activity "
                "where datname = current_database() and wait_event_type = 'Lock' "
                "and pid <> pg_backend_pid()"
            )
        )


def test_two_simultaneous_resets_with_the_same_token_exactly_one_wins(
    rec_app, rec_db, client, envios
):
    cuenta = crear_cuenta(rec_db)
    sesion = refresh_cookie(login(client, cuenta.email, PASSWORD))
    token = token_por_correo(client, envios, cuenta)
    respuestas: dict[str, object] = {}
    errores: list[BaseException] = []

    def canjear(password: str) -> None:
        try:
            respuestas[password] = restablecer(
                rec_app.test_client(use_cookies=False), token, password=password
            )
        except BaseException as exc:  # se reporta en el hilo principal
            errores.append(exc)

    hilos = [threading.Thread(target=canjear, args=(p,)) for p in (NUEVA, OTRA_NUEVA)]
    with rec_db.migrator.connect() as retenedor:
        transaccion = retenedor.begin()
        retenedor.execute(
            text("select 1 from recuperacion_contrasena where token_hash = :h for update"),
            {"h": token_storage_hash(token)},
        )
        for hilo in hilos:
            hilo.start()
        limite = time.monotonic() + 15
        while _esperando_candado(rec_db) < 2:
            if time.monotonic() > limite or errores:
                transaccion.rollback()
                pytest.fail("los dos canjes no llegaron a esperar el candado", pytrace=False)
            time.sleep(0.05)
        transaccion.rollback()
    for hilo in hilos:
        hilo.join(15)

    assert errores == []
    assert sorted(r.status_code for r in respuestas.values()) == [204, 400]
    [ganadora] = [p for p, r in respuestas.items() if r.status_code == 204]
    [perdedora] = [p for p, r in respuestas.items() if r.status_code == 400]
    assert error_of(respuestas[perdedora]) == INVALID_LINK
    # Una sola contraseña vigente: la de la ganadora.
    assert login(client, cuenta.email, ganadora).status_code == 200
    assert login(client, cuenta.email, perdedora).status_code == 401
    assert login(client, cuenta.email, PASSWORD).status_code == 401
    assert refrescar(client, sesion).status_code == 401
    assert enlace(rec_db, token)["usada_en"] is not None
    # Reuso tras el cambio: el mismo 400 y la contraseña no cambia.
    hash_vigente = password_hash_de(rec_db, cuenta)
    reuso = restablecer(client, token, password=TERCERA)
    assert reuso.status_code == 400
    assert error_of(reuso) == INVALID_LINK
    assert password_hash_de(rec_db, cuenta) == hash_vigente


def test_tenant_b_token_used_from_a_tenant_a_session_only_touches_b(client, rec_db, envios):
    cuenta_a = crear_cuenta(rec_db, membresias=((TENANT_A, "admin", True),))
    cuenta_b = crear_cuenta(rec_db, membresias=((TENANT_B, "admin", True),))
    entrada_a = login(client, cuenta_a.email, PASSWORD)
    acceso_a = entrada_a.get_json()["access_token"]
    cookie_a = refresh_cookie(entrada_a)
    cookie_b = refresh_cookie(login(client, cuenta_b.email, PASSWORD))
    token_a = token_por_correo(client, envios, cuenta_a)
    token_b = token_por_correo(client, envios, cuenta_b)
    hash_a = password_hash_de(rec_db, cuenta_a)

    response = client.post(
        RESTABLECER,
        json={"token": token_b, "password": NUEVA},
        headers={**CSRF, "Authorization": f"Bearer {acceso_a}", "Cookie": cookie_a},
    )

    assert response.status_code == 204
    assert "Set-Cookie" not in response.headers
    assert enlace(rec_db, token_b)["tenant_id"] == TENANT_B
    # A no cambia: misma contraseña, su sesión sigue viva y su acceso sigue en A.
    assert password_hash_de(rec_db, cuenta_a) == hash_a
    assert login(client, cuenta_a.email, PASSWORD).status_code == 200
    assert refrescar(client, cookie_a).status_code == 200
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {acceso_a}"})
    assert me.status_code == 200
    assert me.get_json()["tenant"]["id"] == str(TENANT_A)
    assert me.get_json()["usuario"]["id"] == str(cuenta_a.usuario_id)
    # El enlace pendiente de A sigue vigente: el canje de B no lo usa ni lo invalida.
    fila_a = enlace(rec_db, token_a)
    assert fila_a["tenant_id"] == TENANT_A
    assert fila_a["usada_en"] is None and fila_a["invalidada_en"] is None
    # B cambió y perdió sus sesiones.
    assert login(client, cuenta_b.email, PASSWORD).status_code == 401
    assert login(client, cuenta_b.email, NUEVA).status_code == 200
    assert refrescar(client, cookie_b).status_code == 401
    # Y el enlace de A todavía se puede canjear, solo para A.
    assert restablecer(client, token_a, password=TERCERA).status_code == 204
    assert login(client, cuenta_a.email, TERCERA).status_code == 200
    assert login(client, cuenta_b.email, NUEVA).status_code == 200
