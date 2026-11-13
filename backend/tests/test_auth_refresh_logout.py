"""Refresh y logout (spec 002, T7; R8, Q2, Q7, Q14, Q15, A11, A23; plan.md §2.2).

Comportamiento real sobre una base temporal migrada a ``head`` con dos tenants
sintéticos (A y B), con ``COMMIT`` reales (la base se borra al terminar):

- ``POST /auth/refresh``: la cookie ``<tenant_id>.<secreto>`` fija el tenant y
  la rotación es un único ``UPDATE`` atómico (``usado_en`` solo si es nulo, no
  revocado, no vencido) que emite el siguiente refresh de la misma ``familia_id``.
  El nuevo acceso sale de ``membresia`` (rol y ``activa``) y ``usuario.activo``,
  releídos al rotar. Responde lo mismo que el login.
- Q15: reuso dentro de la ventana de gracia (~10 s) -> ``401`` sin revocar; fuera
  de ella revoca **solo** esa familia.
- ``POST /auth/logout``: revoca la familia de la cookie y la limpia; siempre ``204``.
- Q14: cabecera personalizada obligatoria y ``Sec-Fetch-Site``/``Origin`` del mismo
  sitio en ambas rutas (``403`` antes de mirar la cookie).
- ``401`` indistinguible (cuerpo y cabeceras) entre vencido, usado, revocado,
  inexistente, mal formado y de otro tenant; sin ``Set-Cookie``.
- Aislamiento: cookie ``<tenant_B>.<secreto de A>``, usuario con membresías en A
  y B, logout con cookie ajena.
- Secretos fuera de los logs, también con ``sqlalchemy.engine`` en ``DEBUG``.

El cliente de pruebas no guarda cookies: cada petición manda la suya en
``Cookie`` para que el estado sea explícito. Datos sintéticos (``@ejemplo.test``).
"""

import logging
import threading
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from http.cookies import SimpleCookie
from pathlib import Path

import argon2
import jwt
import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from conftest import BLOCKED, read_database_url, role_sees_all_rows
from flask import Flask
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

from app import create_app
from app.auth.credentials import (
    ARGON2_TEST_PARAMS,
    decode_access_token,
    new_token,
    token_key,
    token_storage_hash,
)
from app.auth.http import AUTH_MAX_BODY_BYTES, CSRF_HEADER, CSRF_HEADER_VALUE
from app.config import Config

BACKEND_DIR = Path(__file__).resolve().parent.parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"

SECRET_KEY = "clave-sintetica-de-prueba-t7-con-mas-de-32-bytes"
PASSWORD = "Clave-Sintetica-T7-ok"

TENANT_A = uuid.UUID("00000000-0000-4000-8000-00000000a007")
TENANT_B = uuid.UUID("00000000-0000-4000-8000-00000000b007")

SECURE_NAME = "__Secure-refresh"
DEV_NAME = "refresh"
CSRF = {CSRF_HEADER: CSRF_HEADER_VALUE}


@dataclass(frozen=True)
class Cuenta:
    usuario_id: uuid.UUID
    email: str
    nombre: str


ADMIN_A = Cuenta(uuid.UUID("00000000-0000-4000-8000-0000000a0071"), "admin.a7@ejemplo.test", "Ana")
CONTADOR_A = Cuenta(
    uuid.UUID("00000000-0000-4000-8000-0000000a0072"), "contador.a7@ejemplo.test", "Carlos"
)
BAJA_A = Cuenta(uuid.UUID("00000000-0000-4000-8000-0000000a0073"), "baja.a7@ejemplo.test", "Bruno")
DOBLE = Cuenta(uuid.UUID("00000000-0000-4000-8000-0000000a0074"), "doble.a7@ejemplo.test", "Diana")
ADMIN_B = Cuenta(uuid.UUID("00000000-0000-4000-8000-0000000b0071"), "admin.b7@ejemplo.test", "Beto")

# (cuenta, [(tenant, rol, activa)]); todas con usuario activo.
SEED = (
    (ADMIN_A, ((TENANT_A, "admin", True),)),
    (CONTADOR_A, ((TENANT_A, "contador", True),)),
    (BAJA_A, ((TENANT_A, "admin", True),)),
    # Membresía activa en A e inactiva en B: el login entra en A.
    (DOBLE, ((TENANT_A, "contador", True), (TENANT_B, "admin", False))),
    (ADMIN_B, ((TENANT_B, "admin", True),)),
)


@dataclass(frozen=True)
class RefreshDb:
    app_url: object
    migrator: Engine


def _fail(message: str) -> None:
    pytest.fail(message, pytrace=False)


def _alembic_config() -> AlembicConfig:
    config = AlembicConfig(str(ALEMBIC_INI))
    config.attributes["configure_logger"] = False
    return config


def _seed(migrator: Engine) -> None:
    hasher = argon2.PasswordHasher.from_parameters(ARGON2_TEST_PARAMS)
    with migrator.begin() as conn:
        for tenant, nombre in ((TENANT_A, "Clínica sintética A7"), (TENANT_B, "Clínica B7")):
            conn.execute(
                text("insert into tenant (id, nombre) values (:id, :n)"),
                {"id": tenant, "n": nombre},
            )
        for cuenta, membresias in SEED:
            conn.execute(
                text(
                    "insert into usuario (id, email, nombre, password_hash, activo) "
                    "values (:id, :e, :n, :h, true)"
                ),
                {
                    "id": cuenta.usuario_id,
                    "e": cuenta.email,
                    "n": cuenta.nombre,
                    "h": hasher.hash(PASSWORD),
                },
            )
            for tenant, rol, activa in membresias:
                conn.execute(
                    text(
                        "insert into membresia (tenant_id, usuario_id, rol, activa) "
                        "values (:t, :u, :r, :a)"
                    ),
                    {"t": tenant, "u": cuenta.usuario_id, "r": rol, "a": activa},
                )


@pytest.fixture(scope="module")
def refresh_db(database_residue_guard) -> Iterator[RefreshDb]:
    """Base temporal en ``head`` con datos sintéticos; se borra al terminar."""
    migrator_url = read_database_url("TEST_MIGRATION_DATABASE_URL")
    app_url = read_database_url("TEST_DATABASE_URL")
    if migrator_url is None or app_url is None or not app_url.username:
        _fail(BLOCKED)
    name = f"assetcontrol_refresh_{uuid.uuid4().hex[:12]}"

    admin = create_engine(migrator_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    failure = None
    try:
        with admin.connect() as conn:
            if not role_sees_all_rows(conn):
                failure = (
                    "bloqueado: el rol migrador debe ser superusuario o BYPASSRLS para "
                    "sembrar los datos sintéticos bajo FORCE RLS"
                )
            else:
                conn.execute(text(f'CREATE DATABASE "{name}"'))
    except SQLAlchemyError as exc:
        failure = f"bloqueado: el rol migrador no pudo preparar la base ({type(exc).__name__})"

    migrator: Engine | None = None
    try:
        if failure is not None:
            _fail(failure)
        migrator_db = migrator_url.set(database=name)
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("MIGRATION_DATABASE_URL", migrator_db.render_as_string(hide_password=False))
            mp.delenv("DATABASE_URL", raising=False)
            mp.setenv("APP_DB_USER", app_url.username)
            command.upgrade(_alembic_config(), "head")
        migrator = create_engine(migrator_db, poolclass=NullPool)
        _seed(migrator)
        yield RefreshDb(app_url=app_url.set(database=name), migrator=migrator)
    finally:
        if migrator is not None:
            migrator.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def make_app(db: RefreshDb, environment: str = "test") -> Flask:
    return create_app(
        Config(
            database_url=db.app_url.render_as_string(hide_password=False),
            secret_key=SECRET_KEY,
            environment=environment,
        )
    )


@pytest.fixture(scope="module")
def refresh_app(refresh_db) -> Iterator[Flask]:
    flask_app = make_app(refresh_db)
    yield flask_app
    flask_app.extensions["assetcontrol.db"].engine.dispose()


@pytest.fixture
def client(refresh_app):
    return refresh_app.test_client(use_cookies=False)


# --- Utilidades -----------------------------------------------------------------


def cookies_of(response) -> dict[str, tuple[str, str]]:
    """``{nombre: (valor, cabecera completa)}`` de los ``Set-Cookie`` de la respuesta."""
    result = {}
    for header in response.headers.getlist("Set-Cookie"):
        parsed = SimpleCookie()
        parsed.load(header)
        for name, morsel in parsed.items():
            result[name] = (morsel.value, header)
    return result


def login(client, cuenta: Cuenta) -> tuple[dict, str]:
    """``(cuerpo, valor de la cookie)`` de un login correcto."""
    response = client.post("/auth/login", json={"email": cuenta.email, "password": PASSWORD})
    assert response.status_code == 200, response.get_json()
    return response.get_json(), cookies_of(response)[SECURE_NAME][0]


def refresh(client, value: str | None, *, name: str = SECURE_NAME, headers=None):
    sent = dict(CSRF if headers is None else headers)
    if value is not None:
        sent["Cookie"] = f"{name}={value}"
    return client.post("/auth/refresh", headers=sent)


def logout(client, value: str | None, *, name: str = SECURE_NAME, headers=None):
    sent = dict(CSRF if headers is None else headers)
    if value is not None:
        sent["Cookie"] = f"{name}={value}"
    return client.post("/auth/logout", headers=sent)


def new_cookie(response) -> str:
    return cookies_of(response)[SECURE_NAME][0]


def secret_of(value: str) -> str:
    return value.split(".", 1)[1]


def row_of(db: RefreshDb, value: str) -> dict:
    """Fila de ``refresh_token`` del valor de cookie (el migrador ve todos los tenants)."""
    with db.migrator.connect() as conn:
        row = conn.execute(
            text("select * from refresh_token where token_hash = :h"),
            {"h": token_storage_hash(secret_of(value))},
        ).one()
    return dict(row._mapping)


def family_rows(db: RefreshDb, familia_id: uuid.UUID) -> list[dict]:
    with db.migrator.connect() as conn:
        return [
            dict(row._mapping)
            for row in conn.execute(
                text("select * from refresh_token where familia_id = :f order by creado_en"),
                {"f": familia_id},
            )
        ]


def age_use(db: RefreshDb, value: str, seconds: int = 60) -> None:
    """Retrasa ``usado_en`` del refresh para simular un reuso fuera de la ventana."""
    with db.migrator.begin() as conn:
        conn.execute(
            text(
                "update refresh_token set usado_en = usado_en - make_interval(secs => :s) "
                "where token_hash = :h"
            ),
            {"s": seconds, "h": token_storage_hash(secret_of(value))},
        )


def expire(db: RefreshDb, value: str) -> None:
    with db.migrator.begin() as conn:
        conn.execute(
            text(
                "update refresh_token set expira_en = now() - interval '1 second' "
                "where token_hash = :h"
            ),
            {"h": token_storage_hash(secret_of(value))},
        )


def revoke_directly(db: RefreshDb, value: str) -> None:
    with db.migrator.begin() as conn:
        conn.execute(
            text("update refresh_token set revocado_en = now() where token_hash = :h"),
            {"h": token_storage_hash(secret_of(value))},
        )


def live_families(db: RefreshDb) -> set[uuid.UUID]:
    """Familias con al menos un refresh sin revocar (de todos los tenants)."""
    with db.migrator.connect() as conn:
        return set(
            conn.scalars(
                text("select distinct familia_id from refresh_token where revocado_en is null")
            )
        )


def comparable_401(response) -> tuple:
    """Todo lo observable de un 401 salvo el ``request_id`` (cuerpo y cabecera)."""
    assert response.status_code == 401
    body = response.get_json()
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "request_id"}
    headers = sorted(
        (k.lower(), v) for k, v in response.headers.items() if k.lower() != "x-request-id"
    )
    return (
        response.status_code,
        {k: v for k, v in body["error"].items() if k != "request_id"},
        headers,
    )


@pytest.fixture
def toggle(refresh_db):
    """Ejecuta un cambio con el migrador y lo deshace al terminar."""
    restore: list[tuple[str, dict]] = []

    def apply(sql: str, undo: str, params: dict) -> None:
        with refresh_db.migrator.begin() as conn:
            conn.execute(text(sql), params)
        restore.append((undo, params))

    yield apply
    with refresh_db.migrator.begin() as conn:
        for undo, params in reversed(restore):
            conn.execute(text(undo), params)


# --- Rotación correcta -------------------------------------------------------------


def test_refresh_returns_the_same_contract_as_login_and_rotates_the_cookie(client, refresh_db):
    body, value = login(client, ADMIN_A)

    response = refresh(client, value)

    assert response.status_code == 200, response.get_json()
    data = response.get_json()
    assert (
        set(data)
        == set(body)
        == {
            "access_token",
            "token_type",
            "expires_in",
            "usuario",
            "tenant",
            "rol",
        }
    )
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] == 900
    assert data["usuario"] == body["usuario"]
    assert data["tenant"] == {"id": str(TENANT_A), "nombre": "Clínica sintética A7"}
    assert data["rol"] == "admin"
    claims = decode_access_token(SECRET_KEY, data["access_token"])
    assert claims.sub == ADMIN_A.usuario_id
    assert claims.tenant == TENANT_A

    rotated = new_cookie(response)
    assert rotated != value
    assert rotated.split(".", 1)[0] == str(TENANT_A)
    assert secret_of(rotated) not in response.get_data(as_text=True)


def test_rotated_cookie_keeps_the_login_attributes(client):
    _, value = login(client, ADMIN_A)

    header = cookies_of(refresh(client, value))[SECURE_NAME][1].lower()

    assert "; secure" in header
    assert "; httponly" in header
    assert "samesite=lax" in header
    assert "path=/auth" in header
    assert f"max-age={7 * 24 * 3600}" in header


def test_rotation_marks_the_old_one_used_and_inserts_the_next_of_the_same_family(
    client, refresh_db
):
    _, value = login(client, ADMIN_A)
    old = row_of(refresh_db, value)

    rotated = new_cookie(refresh(client, value))

    used = row_of(refresh_db, value)
    nxt = row_of(refresh_db, rotated)
    assert used["usado_en"] is not None
    assert used["revocado_en"] is None
    assert nxt["familia_id"] == old["familia_id"]
    assert nxt["membresia_id"] == old["membresia_id"]
    assert nxt["tenant_id"] == TENANT_A
    assert nxt["usado_en"] is None and nxt["revocado_en"] is None
    assert bytes(nxt["token_hash"]) == token_storage_hash(secret_of(rotated))
    with refresh_db.migrator.connect() as conn:
        remaining = conn.scalar(
            text("select expira_en - now() from refresh_token where id = :i"), {"i": nxt["id"]}
        )
    assert remaining.total_seconds() > 7 * 24 * 3600 - 60


def test_a_chain_of_rotations_works_and_each_cookie_is_single_use(client):
    _, value = login(client, CONTADOR_A)
    for _ in range(3):
        response = refresh(client, value)
        assert response.status_code == 200
        value = new_cookie(response)


def test_the_new_access_token_takes_the_role_from_membresia(client, toggle):
    _, value = login(client, CONTADOR_A)
    toggle(
        "update membresia set rol = 'admin' where tenant_id = :t and usuario_id = :u",
        "update membresia set rol = 'contador' where tenant_id = :t and usuario_id = :u",
        {"t": TENANT_A, "u": CONTADOR_A.usuario_id},
    )

    response = refresh(client, value)

    assert response.status_code == 200
    assert response.get_json()["rol"] == "admin"
    token = response.get_json()["access_token"]
    assert jwt.decode(token, options={"verify_signature": False})["rol"] == "admin"


def test_refresh_ignores_an_authorization_header_with_another_role(client):
    body, value = login(client, CONTADOR_A)
    headers = {**CSRF, "Authorization": f"Bearer {body['access_token']}"}

    response = refresh(client, value, headers=headers)

    assert response.get_json()["rol"] == "contador"


@pytest.mark.parametrize(
    ("sql", "undo"),
    [
        (
            "update membresia set activa = false where tenant_id = :t and usuario_id = :u",
            "update membresia set activa = true where tenant_id = :t and usuario_id = :u",
        ),
        (
            "update usuario set activo = false where id = :u",
            "update usuario set activo = true where id = :u",
        ),
    ],
    ids=["membresia_inactiva", "usuario_inactivo"],
)
def test_refresh_of_a_deactivated_account_does_not_rotate(client, refresh_db, toggle, sql, undo):
    _, value = login(client, BAJA_A)
    toggle(sql, undo, {"t": TENANT_A, "u": BAJA_A.usuario_id})
    before = family_rows(refresh_db, row_of(refresh_db, value)["familia_id"])

    response = refresh(client, value)

    assert response.status_code == 401
    assert "Set-Cookie" not in response.headers
    after = family_rows(refresh_db, before[0]["familia_id"])
    assert len(after) == len(before)  # no se emitió otro refresh
    assert row_of(refresh_db, value)["usado_en"] is not None  # quedó consumido


# --- Ventana de gracia y reuso (Q15, A23) -----------------------------------------


def test_reuse_inside_the_grace_window_is_401_without_revoking(client, refresh_db):
    _, value = login(client, ADMIN_A)
    rotated = new_cookie(refresh(client, value))

    response = refresh(client, value)

    assert response.status_code == 401
    assert "Set-Cookie" not in response.headers
    familia = row_of(refresh_db, value)["familia_id"]
    assert all(r["revocado_en"] is None for r in family_rows(refresh_db, familia))
    assert refresh(client, rotated).status_code == 200


def test_reuse_outside_the_window_revokes_only_that_family(client, refresh_db):
    _, stolen = login(client, ADMIN_A)
    _, other_family_same_user = login(client, ADMIN_A)
    _, other_tenant = login(client, ADMIN_B)
    rotated = new_cookie(refresh(client, stolen))
    familia = row_of(refresh_db, stolen)["familia_id"]
    others = {
        row_of(refresh_db, other_family_same_user)["familia_id"],
        row_of(refresh_db, other_tenant)["familia_id"],
    }
    age_use(refresh_db, stolen)

    response = refresh(client, stolen)

    assert response.status_code == 401
    assert all(r["revocado_en"] is not None for r in family_rows(refresh_db, familia))
    live = live_families(refresh_db)
    assert familia not in live
    assert others <= live
    assert refresh(client, rotated).status_code == 401
    assert refresh(client, other_family_same_user).status_code == 200
    assert refresh(client, other_tenant).status_code == 200


def test_reuse_of_an_old_link_of_the_chain_revokes_the_newest(client, refresh_db):
    _, first = login(client, CONTADOR_A)
    second = new_cookie(refresh(client, first))
    third = new_cookie(refresh(client, second))
    age_use(refresh_db, first)

    assert refresh(client, first).status_code == 401
    assert refresh(client, third).status_code == 401


def test_concurrent_rotation_has_a_single_winner_and_does_not_revoke(refresh_app, refresh_db):
    """Dos (o más) refresh con la misma cookie esperan el mismo candado: solo uno rota."""
    _, value = login(refresh_app.test_client(use_cookies=False), ADMIN_A)
    familia = row_of(refresh_db, value)["familia_id"]
    workers = 6
    results: list[int] = []
    lock = threading.Lock()
    barrier = threading.Barrier(workers)

    def worker() -> None:
        own = refresh_app.test_client(use_cookies=False)
        barrier.wait()
        status = refresh(own, value).status_code
        with lock:
            results.append(status)

    # El migrador retiene el candado de la fila: todos llegan al UPDATE a la vez.
    with refresh_db.migrator.begin() as conn:
        conn.execute(
            text("select 1 from refresh_token where token_hash = :h for update"),
            {"h": token_storage_hash(secret_of(value))},
        )
        threads = [threading.Thread(target=worker) for _ in range(workers)]
        for thread in threads:
            thread.start()
        time.sleep(1.0)
    for thread in threads:
        thread.join(timeout=30)

    assert sorted(results) == [200] + [401] * (workers - 1)
    rows = family_rows(refresh_db, familia)
    assert len(rows) == 2  # el original y un único sucesor
    assert all(r["revocado_en"] is None for r in rows)


# --- 401 indistinguible -------------------------------------------------------------


def test_every_rejected_refresh_is_indistinguishable(client, refresh_db):
    _, vencido = login(client, ADMIN_A)
    expire(refresh_db, vencido)
    _, usado = login(client, ADMIN_A)
    refresh(client, usado)
    _, usado_fuera = login(client, ADMIN_A)
    refresh(client, usado_fuera)
    age_use(refresh_db, usado_fuera)
    _, revocado = login(client, ADMIN_A)
    revoke_directly(refresh_db, revocado)
    _, de_a = login(client, ADMIN_A)

    cases = {
        "vencido": refresh(client, vencido),
        "usado_en_gracia": refresh(client, usado),
        "usado_fuera": refresh(client, usado_fuera),
        "revocado": refresh(client, revocado),
        "inexistente": refresh(client, f"{TENANT_A}.{'x' * 43}"),
        "otro_tenant": refresh(client, f"{TENANT_B}.{secret_of(de_a)}"),
        "tenant_inexistente": refresh(client, f"{uuid.uuid4()}.{secret_of(de_a)}"),
        "sin_punto": refresh(client, secret_of(de_a)),
        "tenant_no_uuid": refresh(client, f"no-es-uuid.{secret_of(de_a)}"),
        "secreto_vacio": refresh(client, f"{TENANT_A}."),
        "sin_cookie": refresh(client, None),
        "cookie_vacia": refresh(client, ""),
        "nombre_de_desarrollo": refresh(client, de_a, name=DEV_NAME),
    }

    observed = {case: comparable_401(response) for case, response in cases.items()}
    reference = observed["inexistente"]
    assert reference[1] == {"code": "no_autenticado", "message": "Debes iniciar sesión."}
    for case, value in observed.items():
        assert value == reference, case
        assert "Set-Cookie" not in cases[case].headers, case
    # Ninguno consumió la cookie válida de A.
    assert refresh(client, de_a).status_code == 200


# --- Aislamiento por tenant -----------------------------------------------------------


def test_cookie_with_another_tenant_does_not_rotate_nor_touch_the_row(client, refresh_db):
    _, de_a = login(client, ADMIN_A)
    before = row_of(refresh_db, de_a)

    response = refresh(client, f"{TENANT_B}.{secret_of(de_a)}")

    assert response.status_code == 401
    assert row_of(refresh_db, de_a) == before
    assert refresh(client, de_a).status_code == 200


def test_user_with_memberships_in_a_and_b_cannot_rotate_a_under_b(client, refresh_db, toggle):
    _, de_a = login(client, DOBLE)
    assert de_a.split(".", 1)[0] == str(TENANT_A)
    toggle(
        "update membresia set activa = true where tenant_id = :t and usuario_id = :u",
        "update membresia set activa = false where tenant_id = :t and usuario_id = :u",
        {"t": TENANT_B, "u": DOBLE.usuario_id},
    )
    before = row_of(refresh_db, de_a)

    response = refresh(client, f"{TENANT_B}.{secret_of(de_a)}")

    assert response.status_code == 401
    assert row_of(refresh_db, de_a) == before
    rotated = refresh(client, de_a)
    assert rotated.status_code == 200
    assert rotated.get_json()["tenant"]["id"] == str(TENANT_A)


def test_reuse_of_a_cookie_under_another_tenant_revokes_nothing(client, refresh_db):
    _, de_a = login(client, ADMIN_A)
    rotated = new_cookie(refresh(client, de_a))
    age_use(refresh_db, de_a)
    live = live_families(refresh_db)

    response = refresh(client, f"{TENANT_B}.{secret_of(de_a)}")

    assert response.status_code == 401
    assert live_families(refresh_db) == live
    assert refresh(client, rotated).status_code == 200


# --- Logout (A11) ---------------------------------------------------------------------


def _assert_cleared(response, name: str = SECURE_NAME) -> None:
    value, header = cookies_of(response)[name]
    lowered = header.lower()
    assert value == ""
    assert "max-age=0" in lowered
    assert "path=/auth" in lowered
    assert "httponly" in lowered
    assert "samesite=lax" in lowered


def test_logout_revokes_the_family_and_clears_the_cookie(client, refresh_db):
    _, value = login(client, ADMIN_A)
    rotated = new_cookie(refresh(client, value))
    familia = row_of(refresh_db, value)["familia_id"]

    response = logout(client, rotated)

    assert response.status_code == 204
    assert response.get_data() == b""
    _assert_cleared(response)
    assert all(r["revocado_en"] is not None for r in family_rows(refresh_db, familia))
    assert refresh(client, rotated).status_code == 401  # A11


def test_logout_with_an_old_cookie_of_the_chain_revokes_the_live_successor(client, refresh_db):
    _, first = login(client, ADMIN_A)
    second = new_cookie(refresh(client, first))
    third = new_cookie(refresh(client, second))
    familia = row_of(refresh_db, first)["familia_id"]

    assert logout(client, first).status_code == 204

    assert all(r["revocado_en"] is not None for r in family_rows(refresh_db, familia))
    assert refresh(client, third).status_code == 401


def _live_in_family(db: RefreshDb, familia_id: uuid.UUID) -> int:
    with db.migrator.connect() as conn:
        return conn.scalar(
            text(
                "select count(*) from refresh_token where familia_id = :f and revocado_en is null"
            ),
            {"f": familia_id},
        )


def _race_with_inflight_rotation(db: RefreshDb, leaf: str, action) -> uuid.UUID:
    """Emula una rotación en vuelo de ``leaf`` y lanza ``action`` mientras no confirma.

    El migrador marca ``usado_en`` de ``leaf`` e inserta su sucesor en la misma
    familia sin confirmar; ``action`` (logout o reuso) corre en otro hilo, espera
    el candado de la fila de ``leaf`` y la transacción en vuelo se confirma después.
    Devuelve la familia.
    """
    row = row_of(db, leaf)
    errors: list[BaseException] = []

    def run() -> None:
        try:
            action()
        except BaseException as exc:  # noqa: BLE001 - se reporta en el hilo principal
            errors.append(exc)

    thread = threading.Thread(target=run)
    with db.migrator.begin() as conn:
        conn.execute(
            text("update refresh_token set usado_en = now() where id = :i"), {"i": row["id"]}
        )
        conn.execute(
            text(
                "insert into refresh_token "
                "(id, tenant_id, membresia_id, familia_id, token_hash, expira_en) "
                "values (:i, :t, :m, :f, :h, now() + interval '7 days')"
            ),
            {
                "i": uuid.uuid4(),
                "t": row["tenant_id"],
                "m": row["membresia_id"],
                "f": row["familia_id"],
                "h": token_storage_hash(new_token()),
            },
        )
        thread.start()
        time.sleep(1.0)
        assert thread.is_alive(), "la acción no esperó el candado de la rotación en vuelo"
    thread.join(timeout=30)
    assert not thread.is_alive()
    assert not errors, errors
    return row["familia_id"]


def test_logout_during_an_inflight_rotation_leaves_no_live_successor(refresh_app, refresh_db):
    """M1: el UPDATE que esperó el candado no ve el sucesor; hay que repetir la pasada."""
    _, value = login(refresh_app.test_client(use_cookies=False), ADMIN_A)
    statuses: list[int] = []

    def action() -> None:
        statuses.append(logout(refresh_app.test_client(use_cookies=False), value).status_code)

    familia = _race_with_inflight_rotation(refresh_db, value, action)

    assert statuses == [204]
    assert len(family_rows(refresh_db, familia)) == 2
    assert _live_in_family(refresh_db, familia) == 0


def test_reuse_during_an_inflight_rotation_leaves_no_live_successor(refresh_app, refresh_db):
    """M1 en la revocación por reuso fuera de ventana (Q15)."""
    own = refresh_app.test_client(use_cookies=False)
    _, stolen = login(own, ADMIN_A)
    leaf = new_cookie(refresh(own, stolen))
    age_use(refresh_db, stolen)
    statuses: list[int] = []

    def action() -> None:
        statuses.append(refresh(refresh_app.test_client(use_cookies=False), stolen).status_code)

    familia = _race_with_inflight_rotation(refresh_db, leaf, action)

    assert statuses == [401]
    assert len(family_rows(refresh_db, familia)) == 3
    assert _live_in_family(refresh_db, familia) == 0


def test_logout_revokes_only_its_family(client, refresh_db):
    _, mine = login(client, ADMIN_A)
    _, same_user = login(client, ADMIN_A)
    _, other_tenant = login(client, ADMIN_B)
    live = live_families(refresh_db)

    logout(client, mine)

    assert live - live_families(refresh_db) == {row_of(refresh_db, mine)["familia_id"]}
    assert refresh(client, same_user).status_code == 200
    assert refresh(client, other_tenant).status_code == 200


def test_logout_with_a_foreign_cookie_revokes_nothing(client, refresh_db):
    _, de_a = login(client, ADMIN_A)
    live = live_families(refresh_db)

    for foreign in (
        f"{TENANT_B}.{secret_of(de_a)}",
        f"{uuid.uuid4()}.{secret_of(de_a)}",
        f"{TENANT_A}.{'x' * 43}",
    ):
        response = logout(client, foreign)
        assert response.status_code == 204
        _assert_cleared(response)

    assert live_families(refresh_db) == live
    assert refresh(client, de_a).status_code == 200


@pytest.mark.parametrize("value", [None, "", "sin-punto", "no-es-uuid.abc"])
def test_logout_without_a_valid_cookie_is_still_204(client, value):
    response = logout(client, value)

    assert response.status_code == 204
    _assert_cleared(response)


def test_logout_does_not_need_an_access_token_and_access_lives_until_it_expires(client):
    """N4 (Q7/A11): el JWT de acceso no se revoca con el logout; vive hasta 15 min."""
    body, value = login(client, ADMIN_A)

    assert logout(client, value).status_code == 204

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200


def test_a_new_login_does_not_revoke_previous_families(client, refresh_db):
    """N6: la spec no pide revocar familias al iniciar sesión (varios dispositivos)."""
    _, first = login(client, CONTADOR_A)
    login(client, CONTADOR_A)

    assert refresh(client, first).status_code == 200


# --- Q14: cabecera personalizada y mismo sitio -------------------------------------------


CSRF_REJECTED = {
    "sin_cabecera": {},
    "cabecera_con_otro_valor": {CSRF_HEADER: "0"},
    "sec_fetch_cross_site": {**CSRF, "Sec-Fetch-Site": "cross-site"},
    "sec_fetch_none": {**CSRF, "Sec-Fetch-Site": "none"},
    "origin_ajeno": {**CSRF, "Origin": "https://atacante.ejemplo.test"},
    "origin_null": {**CSRF, "Origin": "null"},
    "sec_fetch_ajeno_con_origin_propio": {
        **CSRF,
        "Sec-Fetch-Site": "cross-site",
        "Origin": "http://localhost",
    },
}

CSRF_ACCEPTED = {
    "sin_metadatos": dict(CSRF),
    "same_origin": {**CSRF, "Sec-Fetch-Site": "same-origin"},
    "same_site": {**CSRF, "Sec-Fetch-Site": "same-site"},
    "origin_propio": {**CSRF, "Origin": "http://localhost"},
    "origin_propio_otro_puerto": {**CSRF, "Origin": "http://localhost:5173"},
}


@pytest.mark.parametrize("case", sorted(CSRF_REJECTED))
@pytest.mark.parametrize("route", [refresh, logout], ids=["refresh", "logout"])
def test_cross_site_requests_are_403_before_touching_the_cookie(client, refresh_db, route, case):
    _, value = login(client, ADMIN_A)
    before = row_of(refresh_db, value)

    response = route(client, value, headers=CSRF_REJECTED[case])

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "prohibido"
    assert "Set-Cookie" not in response.headers
    assert row_of(refresh_db, value) == before
    assert refresh(client, value).status_code == 200


@pytest.mark.parametrize("case", sorted(CSRF_ACCEPTED))
def test_same_site_requests_are_accepted(client, case):
    _, value = login(client, ADMIN_A)

    assert refresh(client, value, headers=CSRF_ACCEPTED[case]).status_code == 200


# --- HTTP: método, cabeceras, tamaño, entorno ------------------------------------------


@pytest.mark.parametrize("path", ["/auth/refresh", "/auth/logout"])
def test_refresh_and_logout_are_post_only(client, path):
    for method in (client.get, client.put, client.delete):
        response = method(path, headers=CSRF)
        assert response.status_code == 405
        assert response.headers["Cache-Control"] == "no-store"


def test_refresh_and_logout_carry_no_store_and_no_referrer(client):
    _, value = login(client, ADMIN_A)
    responses = [
        refresh(client, value),
        refresh(client, value),  # 401
        refresh(client, value, headers={}),  # 403
        logout(client, value),
    ]
    for response in responses:
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["Referrer-Policy"] == "no-referrer"


@pytest.mark.parametrize("route", [refresh, logout], ids=["refresh", "logout"])
def test_refresh_and_logout_reject_bodies_over_4_kb(client, route):
    path = "/auth/refresh" if route is refresh else "/auth/logout"
    response = client.post(path, data="x" * (AUTH_MAX_BODY_BYTES + 1), headers=CSRF)

    assert response.status_code == 413


def test_development_uses_the_cookie_without_prefix(refresh_db):
    flask_app = make_app(refresh_db, environment="development")
    try:
        dev = flask_app.test_client(use_cookies=False)
        response = dev.post("/auth/login", json={"email": ADMIN_A.email, "password": PASSWORD})
        value, header = cookies_of(response)[DEV_NAME]
        assert "; secure" not in header.lower()

        rotated = refresh(dev, value, name=DEV_NAME)
        assert rotated.status_code == 200
        new_value, new_header = cookies_of(rotated)[DEV_NAME]
        assert "; secure" not in new_header.lower()
        assert refresh(dev, new_value, name=SECURE_NAME).status_code == 401

        out = logout(dev, new_value, name=DEV_NAME)
        assert out.status_code == 204
        _assert_cleared(out, DEV_NAME)
        assert refresh(dev, new_value, name=DEV_NAME).status_code == 401
    finally:
        flask_app.extensions["assetcontrol.db"].engine.dispose()


# --- Secretos fuera de los logs (A14, M1) ----------------------------------------------


@pytest.fixture
def sqlalchemy_debug():
    """``sqlalchemy.engine``/``pool`` en DEBUG antes de crear la app; restaura al final."""
    names = ("sqlalchemy.engine", "sqlalchemy.engine.Engine", "sqlalchemy.pool")
    saved = {}
    for name in names:
        logger = logging.getLogger(name)
        saved[name] = (logger.level, list(logger.filters), list(logger.handlers))
    for name in ("sqlalchemy.engine", "sqlalchemy.pool"):
        logging.getLogger(name).setLevel(logging.DEBUG)
    yield
    for name, (level, filters, handlers) in saved.items():
        logger = logging.getLogger(name)
        logger.setLevel(level)
        logger.filters[:] = filters
        for handler in logger.handlers[:]:
            if handler not in handlers:
                logger.removeHandler(handler)


def _secrets_of(*values: str) -> list[str]:
    found = []
    for value in values:
        secret = secret_of(value)
        stored = token_storage_hash(secret)
        found += [value, secret, token_key(secret), stored.hex(), repr(stored)]
    return found


def _exercise(flask_app, db: RefreshDb) -> tuple[list[str], list[str]]:
    client = flask_app.test_client(use_cookies=False)
    body, value = login(client, ADMIN_A)
    ok = refresh(client, value)
    rotated = new_cookie(ok)
    refresh(client, value)  # reuso en gracia
    age_use(db, value)
    refresh(client, value)  # reuso fuera: revoca
    _, other = login(client, ADMIN_A)
    refresh(client, f"{TENANT_B}.{secret_of(other)}")
    logout(client, other)
    tokens = [body["access_token"], ok.get_json()["access_token"]]
    return _secrets_of(value, rotated, other), tokens


def test_refresh_and_logout_do_not_log_cookies_tokens_or_hashes(
    refresh_db, sqlalchemy_debug, caplog, capfd
):
    flask_app = make_app(refresh_db)
    try:
        with caplog.at_level(logging.DEBUG):
            secrets, tokens = _exercise(flask_app, refresh_db)
    finally:
        flask_app.extensions["assetcontrol.db"].engine.dispose()

    out, err = capfd.readouterr()
    joined = "\n".join((caplog.text, out, err))
    assert [value for value in secrets + tokens if value in joined] == []
    assert "Row " not in joined
