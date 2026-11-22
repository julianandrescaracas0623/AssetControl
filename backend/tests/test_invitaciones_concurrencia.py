"""Aceptación concurrente de invitaciones (spec 002, T9; R11, A9, A20, Q16).

- Varias aceptaciones del mismo token a la vez: el ``UPDATE`` condicional de
  ``acceso.aceptar_invitacion`` deja **un solo ganador**; los demás reciben el
  ``400 invitacion_invalida`` genérico y no se crea nada más.
- Dos invitaciones (de tenants distintos) para el mismo email aceptadas a la vez: el
  índice único de ``usuario.email`` con ``ON CONFLICT DO NOTHING`` deja un solo
  usuario; la perdedora revierte y su invitación queda **sin consumir** (A20).

El migrador retiene un candado para que todas las peticiones lleguen a la vez al
punto de conflicto. Datos sintéticos (``@ejemplo.test``).
"""

import threading
import time
import uuid
from collections.abc import Iterator

import pytest
from acceso_db import (
    ADMIN_A,
    ADMIN_B,
    TENANT_A,
    TENANT_B,
    AccesoDb,
    bearer,
    dispose,
    make_app,
    temporary_acceso_db,
)
from flask import Flask
from sqlalchemy import text

from app.auth.credentials import token_storage_hash

ACEPTAR = "/invitaciones/aceptar"
NUEVA = "Clave-Nueva-T9-segura"


@pytest.fixture(scope="module")
def conc_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("aceptar_conc")


@pytest.fixture(scope="module")
def conc_app(conc_db) -> Iterator[Flask]:
    flask_app = make_app(conc_db)
    yield flask_app
    dispose(flask_app)


def invitar(flask_app: Flask, email: str, cuenta=ADMIN_A, tenant=TENANT_A) -> str:
    response = flask_app.test_client(use_cookies=False).post(
        "/invitaciones", json={"email": email, "rol": "contador"}, headers=bearer(cuenta, tenant)
    )
    assert response.status_code == 201
    return response.get_json()["enlace"].removeprefix("/invitacion#")


def _waiting_on_locks(db: AccesoDb) -> int:
    with db.migrator.connect() as conn:
        return conn.scalar(
            text(
                "select count(*) from pg_stat_activity "
                "where datname = current_database() and wait_event_type = 'Lock'"
            )
        )


def _wait_for_lock_waiters(db: AccesoDb, expected: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _waiting_on_locks(db) >= expected:
            return
        time.sleep(0.05)
    pytest.fail(f"no llegaron {expected} transacciones a esperar el candado", pytrace=False)


def _run_parallel(flask_app: Flask, tokens: list[str]) -> tuple[list, list[threading.Thread]]:
    results: list[tuple[int, dict]] = []
    lock = threading.Lock()
    barrier = threading.Barrier(len(tokens))

    def worker(token: str, index: int) -> None:
        own = flask_app.test_client(use_cookies=False)
        barrier.wait()
        response = own.post(
            ACEPTAR, json={"token": token, "nombre": f"Paralela {index}", "password": NUEVA}
        )
        with lock:
            results.append((response.status_code, response.get_json()))

    threads = [
        threading.Thread(target=worker, args=(token, index)) for index, token in enumerate(tokens)
    ]
    for thread in threads:
        thread.start()
    return results, threads


def _join(threads: list[threading.Thread]) -> None:
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads)


def _usuarios(db: AccesoDb, email: str) -> list[dict]:
    with db.migrator.connect() as conn:
        return [
            dict(r)
            for r in conn.execute(
                text("select * from usuario where email = :e"), {"e": email}
            ).mappings()
        ]


def _membresias(db: AccesoDb, usuario_id: uuid.UUID) -> list[dict]:
    with db.migrator.connect() as conn:
        return [
            dict(r)
            for r in conn.execute(
                text("select * from membresia where usuario_id = :u"), {"u": usuario_id}
            ).mappings()
        ]


def _usada_en(db: AccesoDb, token: str):
    with db.migrator.connect() as conn:
        return conn.scalar(
            text("select usada_en from invitacion where token_hash = :h"),
            {"h": token_storage_hash(token)},
        )


def _assert_one_winner(results: list[tuple[int, dict]], workers: int) -> dict:
    statuses = sorted(status for status, _ in results)
    assert statuses == [201] + [400] * (workers - 1), results
    losers = [body for status, body in results if status == 400]
    assert all(body["error"]["code"] == "invitacion_invalida" for body in losers)
    return next(body for status, body in results if status == 201)


def test_same_token_accepted_in_parallel_has_a_single_winner(conc_app, conc_db):
    email = f"paralelo.{uuid.uuid4().hex[:8]}@ejemplo.test"
    token = invitar(conc_app, email)
    workers = 6

    # El migrador retiene la fila: todos llegan al UPDATE condicional a la vez.
    with conc_db.migrator.begin() as conn:
        conn.execute(
            text("select 1 from invitacion where token_hash = :h for update"),
            {"h": token_storage_hash(token)},
        )
        results, threads = _run_parallel(conc_app, [token] * workers)
        _wait_for_lock_waiters(conc_db, workers)
    _join(threads)

    winner = _assert_one_winner(results, workers)
    (usuario,) = _usuarios(conc_db, email)
    assert winner["usuario"]["id"] == str(usuario["id"])
    (membresia,) = _membresias(conc_db, usuario["id"])
    assert membresia["tenant_id"] == TENANT_A
    assert _usada_en(conc_db, token) is not None


def test_two_invitations_for_the_same_email_accepted_in_parallel_create_one_user(conc_app, conc_db):
    """Una en A y otra en B: un solo usuario; la perdedora queda sin consumir (A20)."""
    email = f"doble.{uuid.uuid4().hex[:8]}@ejemplo.test"
    token_a = invitar(conc_app, email, ADMIN_A, TENANT_A)
    token_b = invitar(conc_app, email, ADMIN_B, TENANT_B)

    # Un INSERT sin confirmar del mismo email obliga a ambas a esperar el índice único;
    # al revertirlo compiten entre ellas y la segunda espera a la primera.
    conn = conc_db.migrator.connect()
    try:
        tx = conn.begin()
        conn.execute(
            text(
                "insert into usuario (id, email, nombre, password_hash) "
                "values (:id, :e, 'Bloqueo', 'x')"
            ),
            {"id": uuid.uuid4(), "e": email},
        )
        results, threads = _run_parallel(conc_app, [token_a, token_b])
        _wait_for_lock_waiters(conc_db, 2)
        tx.rollback()
    finally:
        conn.close()
    _join(threads)

    winner = _assert_one_winner(results, 2)
    (usuario,) = _usuarios(conc_db, email)
    (membresia,) = _membresias(conc_db, usuario["id"])
    won_a = winner["tenant"]["id"] == str(TENANT_A)
    assert membresia["tenant_id"] == (TENANT_A if won_a else TENANT_B)
    winner_token, loser_token = (token_a, token_b) if won_a else (token_b, token_a)
    assert _usada_en(conc_db, winner_token) is not None
    assert _usada_en(conc_db, loser_token) is None
