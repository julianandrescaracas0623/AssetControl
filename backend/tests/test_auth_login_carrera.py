"""Carrera login frente a restablecimiento de contraseña (spec 017, T17; D48; R26–R28, A28).

Un login lee el hash con ``acceso.buscar_login`` y lo verifica con Argon2 fuera de toda
transacción; si en ese intervalo otra petición cambia la contraseña y confirma, el login
verificó la contraseña **anterior** y no debe emitir sesión. Las tres vías que cambian la
contraseña ponen ``usuario.sesiones_validas_desde = now()`` (0026, 0032): la consola (T16,
``POST /plataforma/empresas/{id}/usuarios/{usuario_id}/contrasena``), el cambio propio (T4,
``POST /auth/cambiar-contrasena``) y la recuperación por correo (014, ``POST
/auth/restablecer``).

La carrera es **determinista** (sin dormir): se envuelve ``get_passwords`` del servicio para
que, justo después de la primera verificación Argon2 del login (que ya leyó el hash
anterior) y antes de ``issue_session``, se ejecute el cambio completo por su ruta real. En
cada vía: ``401 credenciales_invalidas`` idéntico al de una contraseña errónea, sin cookie,
sin JWT y sin familia de refresh nueva; el intento cuenta para el límite de tasa como uno
fallido. Un login que empieza **después** del corte no se rechaza.

La barrera (revisión del security-reviewer): ``issue_session``, ya bajo el candado
compartido y en la **misma** transacción y conexión donde inserta el refresh, relee
``acceso.buscar_login`` y exige el mismo ``usuario_id`` y el mismo hash que verificó. No
depende del reloj: cubre también un cambio cuya transacción empezó **antes** de la lectura
del login (su ``now()``, el corte, es anterior a esa lectura) y un cambio de hash sin corte.

Datos sintéticos (``@ejemplo.test``).
"""

import logging
import secrets
import threading
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta

import argon2
import pytest
from acceso_db import PASSWORD, AccesoDb, dispose, temporary_acceso_db
from flask import Flask
from plataforma_db import (
    CSRF,
    Dev,
    filas,
    login,
    make_plat_app,
    nuevo_dev,
    plat_bearer,
    sembrar_dev,
)
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app import db as app_db
from app.auth import credentials, service
from app.auth.credentials import ARGON2_TEST_PARAMS, token_key
from app.auth.http import REFRESH_COOKIE_SECURE_NAME

HASHER = argon2.PasswordHasher.from_parameters(ARGON2_TEST_PARAMS)
NUEVA = "Nueva-Sintetica-Carrera-2026"
ERRONEA = "Erronea-Sintetica-Carrera-2026"
VIAS = ("consola", "cambio_propio", "recuperacion")
LOGIN_AMBITOS = ("login_cuenta", "login_ip")


@pytest.fixture(scope="module")
def carrera_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("login_carrera")


@pytest.fixture(scope="module")
def carrera_app(carrera_db) -> Iterator[Flask]:
    flask_app = make_plat_app(carrera_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(carrera_app):
    return carrera_app.test_client(use_cookies=False)


@pytest.fixture(scope="module")
def app_engine(carrera_db) -> Iterator[Engine]:
    engine = create_engine(carrera_db.app_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def plat_dev(carrera_db) -> Dev:
    return sembrar_dev(carrera_db, nuevo_dev("carrera"))


@pytest.fixture(scope="module")
def dev_headers(plat_dev, carrera_app) -> dict[str, str]:
    response = login(carrera_app.test_client(use_cookies=False), plat_dev.email)
    assert response.status_code == 200
    return plat_bearer(response.get_json()["access_token"])


@pytest.fixture(autouse=True)
def fresh_rate_limits(carrera_db) -> Iterator[None]:
    with carrera_db.migrator.begin() as conn:
        conn.execute(text("delete from limite_tasa"))
    yield


# --- Datos ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class Persona:
    usuario_id: uuid.UUID
    tenant_id: uuid.UUID
    email: str


def _persona(db: AccesoDb) -> Persona:
    """Empresa propia con un admin activo (contraseña ``PASSWORD``), sembrada por el migrador."""
    sufijo = uuid.uuid4().hex[:10]
    persona = Persona(uuid.uuid4(), uuid.uuid4(), f"carrera.{sufijo}@ejemplo.test")
    with db.migrator.begin() as conn:
        conn.execute(
            text("insert into tenant (id, nombre) values (:t, :n)"),
            {"t": persona.tenant_id, "n": f"Clínica Carrera {sufijo}"},
        )
        conn.execute(
            text("insert into usuario (id, email, nombre, password_hash) values (:u, :e, :n, :h)"),
            {
                "u": persona.usuario_id,
                "e": persona.email,
                "n": f"Persona {sufijo}",
                "h": HASHER.hash(PASSWORD),
            },
        )
        conn.execute(
            text("insert into membresia (tenant_id, usuario_id, rol) values (:t, :u, 'admin')"),
            {"t": persona.tenant_id, "u": persona.usuario_id},
        )
    return persona


def _familias(db: AccesoDb, persona: Persona) -> int:
    (row,) = filas(
        db,
        "select count(distinct r.familia_id) as n from refresh_token r "
        "join membresia m on m.id = r.membresia_id where m.usuario_id = :u",
        {"u": persona.usuario_id},
    )
    return row["n"]


def _vivos(db: AccesoDb, persona: Persona) -> int:
    (row,) = filas(
        db,
        "select count(*) as n from refresh_token r join membresia m on m.id = r.membresia_id "
        "where m.usuario_id = :u and r.revocado_en is null",
        {"u": persona.usuario_id},
    )
    return row["n"]


def _corte(db: AccesoDb, persona: Persona) -> datetime | None:
    (row,) = filas(
        db, "select sesiones_validas_desde from usuario where id = :u", {"u": persona.usuario_id}
    )
    return row["sesiones_validas_desde"]


def _intentos(db: AccesoDb) -> dict[str, int]:
    rows = filas(
        db,
        "select ambito, sum(intentos)::int as n from limite_tasa "
        "where ambito in ('login_cuenta', 'login_ip') group by ambito",
    )
    return {row["ambito"]: row["n"] for row in rows}


def _limpiar_intentos(db: AccesoDb) -> None:
    with db.migrator.begin() as conn:
        conn.execute(text("delete from limite_tasa"))


def _tenant_login(client, email: str, password: str = PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def _bearer(response) -> dict[str, str]:
    return {"Authorization": f"Bearer {response.get_json()['access_token']}"}


def _cookie(response) -> str | None:
    for header in response.headers.getlist("Set-Cookie"):
        name, _, rest = header.partition("=")
        if name == REFRESH_COOKIE_SECURE_NAME:
            return rest.split(";", 1)[0]
    return None


def _sin_request_id(response) -> dict:
    body = response.get_json()
    assert set(body) == {"error"}
    return {k: v for k, v in body["error"].items() if k != "request_id"}


# --- Las tres vías del cambio, por su ruta real ----------------------------------------------


def _preparar(via: str, client, app_engine: Engine, persona: Persona, dev_headers) -> Callable:
    """Lo que hay que tener antes de la carrera y la acción que cambia la contraseña."""
    if via == "consola":
        ruta = f"/plataforma/empresas/{persona.tenant_id}/usuarios/{persona.usuario_id}/contrasena"

        def accion():
            response = client.post(
                ruta, json={"password": NUEVA, "password_confirmacion": NUEVA}, headers=dev_headers
            )
            assert response.status_code == 204

        return accion

    if via == "cambio_propio":
        # La persona legítima ya tiene su sesión abierta y cambia su contraseña.
        propia = _tenant_login(client, persona.email)
        assert propia.status_code == 200
        headers = _bearer(propia)

        def accion():
            response = client.post(
                "/auth/cambiar-contrasena",
                json={"actual": PASSWORD, "nueva": NUEVA, "confirmacion": NUEVA},
                headers=headers,
            )
            assert response.status_code == 200

        return accion

    assert via == "recuperacion"
    token = secrets.token_urlsafe(32)
    with app_engine.begin() as conn:
        assert conn.scalar(
            text("select acceso.solicitar_recuperacion(:e, :c)"),
            {"e": persona.email, "c": token_key(token)},
        )

    def accion():
        response = client.post(
            "/auth/restablecer", json={"token": token, "password": NUEVA}, headers=CSRF
        )
        assert response.status_code == 204

    return accion


class _VerificaYLuego:
    """``Passwords`` cuya primera ``verify`` ejecuta ``accion`` después de verificar.

    Así el cambio de contraseña cae, determinista, entre la verificación Argon2 del login
    (que ya leyó el hash anterior) y ``issue_session``. Las demás llamadas (la verificación
    de la contraseña actual en el cambio propio, por ejemplo) pasan sin tocar.
    """

    def __init__(self, original: Callable, accion: Callable) -> None:
        self._original = original
        self._accion = accion
        self.disparado = False

    def verify(self, stored, password):
        resultado = self._original().verify(stored, password)
        if not self.disparado:
            self.disparado = True
            self._accion()
        return resultado

    def __getattr__(self, name):
        return getattr(self._original(), name)


def _intercalar(monkeypatch, accion: Callable) -> _VerificaYLuego:
    envoltura = _VerificaYLuego(service.get_passwords, accion)
    monkeypatch.setattr(service, "get_passwords", lambda: envoltura)
    return envoltura


def _reloj_de_flask(monkeypatch, desfase: timedelta) -> None:
    """Desplaza el reloj de Flask (emisión y validación del JWT); el de la base no cambia."""

    class Reloj(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(tz) + desfase

    monkeypatch.setattr(service, "datetime", Reloj)
    monkeypatch.setattr(credentials, "datetime", Reloj)


# --- La carrera, en las tres vías ------------------------------------------------------------

# Familias vivas tras la carrera: el cambio propio deja la sesión nueva de quien cambió.
VIVAS_TRAS_EL_CAMBIO = {"consola": 0, "cambio_propio": 1, "recuperacion": 0}


@pytest.mark.parametrize("via", VIAS)
def test_a_login_verified_before_the_cut_emits_no_session(
    client, carrera_db, app_engine, dev_headers, monkeypatch, caplog, via
):
    persona = _persona(carrera_db)
    erronea = _tenant_login(client, persona.email, ERRONEA)
    assert erronea.status_code == 401
    intentos_erronea = _intentos(carrera_db)
    _limpiar_intentos(carrera_db)
    accion = _preparar(via, client, app_engine, persona, dev_headers)
    familias_antes = _familias(carrera_db, persona)
    envoltura = _intercalar(monkeypatch, accion)
    caplog.set_level(logging.DEBUG)

    # La contraseña anterior es correcta cuando se lee el hash y se verifica.
    response = _tenant_login(client, persona.email, PASSWORD)

    assert envoltura.disparado
    assert _corte(carrera_db, persona) is not None
    assert response.status_code == 401
    assert _sin_request_id(response) == _sin_request_id(erronea)
    assert response.get_json() is not None and "access_token" not in response.get_json()
    assert response.headers.getlist("Set-Cookie") == []
    assert _cookie(response) is None
    # Ninguna familia nueva del login (el cambio propio crea la de quien cambió).
    nuevas_del_cambio = 1 if via == "cambio_propio" else 0
    assert _familias(carrera_db, persona) == familias_antes + nuevas_del_cambio
    assert _vivos(carrera_db, persona) == VIVAS_TRAS_EL_CAMBIO[via]
    # El intento no se devuelve: cuenta como uno fallido, igual que la contraseña errónea.
    assert _intentos(carrera_db) == intentos_erronea
    for secreto in (PASSWORD, NUEVA, "$argon2"):
        assert secreto not in caplog.text
        assert secreto not in response.get_data(as_text=True)


@pytest.mark.parametrize("via", VIAS)
def test_after_the_race_the_new_password_enters_and_the_old_one_does_not(
    client, carrera_db, app_engine, dev_headers, monkeypatch, via
):
    persona = _persona(carrera_db)
    accion = _preparar(via, client, app_engine, persona, dev_headers)
    _intercalar(monkeypatch, accion)
    assert _tenant_login(client, persona.email, PASSWORD).status_code == 401
    monkeypatch.undo()

    assert _tenant_login(client, persona.email, PASSWORD).status_code == 401
    nueva = _tenant_login(client, persona.email, NUEVA)
    assert nueva.status_code == 200
    assert client.get("/auth/me", headers=_bearer(nueva)).status_code == 200
    refresh = client.post(
        "/auth/refresh",
        headers={**CSRF, "Cookie": f"{REFRESH_COOKIE_SECURE_NAME}={_cookie(nueva)}"},
    )
    assert refresh.status_code == 200


# --- Lo que no se rechaza --------------------------------------------------------------------


@pytest.mark.parametrize("via", VIAS)
def test_a_login_that_starts_after_the_cut_is_not_rejected(
    client, carrera_db, app_engine, dev_headers, via
):
    persona = _persona(carrera_db)
    _preparar(via, client, app_engine, persona, dev_headers)()
    assert _corte(carrera_db, persona) is not None

    # Sin esperar al segundo siguiente: el instante de inicio tiene microsegundos.
    response = _tenant_login(client, persona.email, NUEVA)

    assert response.status_code == 200
    body = response.get_json()
    assert body["debe_cambiar_password"] is (via == "consola")
    assert _cookie(response) is not None
    assert client.get("/auth/me", headers=_bearer(response)).status_code == 200


def test_a_cut_of_another_user_during_the_verification_does_not_reject(
    client, carrera_db, app_engine, dev_headers, monkeypatch
):
    persona = _persona(carrera_db)
    otra = _persona(carrera_db)
    _intercalar(monkeypatch, _preparar("consola", client, app_engine, otra, dev_headers))

    response = _tenant_login(client, persona.email, PASSWORD)

    assert response.status_code == 200
    assert _corte(carrera_db, otra) is not None
    assert _corte(carrera_db, persona) is None
    assert client.get("/auth/me", headers=_bearer(response)).status_code == 200


def test_a_login_concurrent_with_a_cut_already_in_place_is_not_rejected(
    client, carrera_db, app_engine, dev_headers, monkeypatch
):
    # Corte de la persona ya confirmado; durante la verificación de su login con la nueva
    # cambia la contraseña de otra persona: el login legítimo entra.
    persona = _persona(carrera_db)
    _preparar("recuperacion", client, app_engine, persona, dev_headers)()
    otra = _persona(carrera_db)
    _intercalar(monkeypatch, _preparar("recuperacion", client, app_engine, otra, dev_headers))

    response = _tenant_login(client, persona.email, NUEVA)

    assert response.status_code == 200


# --- Reloj (D38 / O-1): la comparación es entre instantes de PostgreSQL -----------------------

DESFASES = (
    timedelta(seconds=-0.9),
    timedelta(seconds=0.9),
    timedelta(seconds=-30),
    timedelta(seconds=30),
)


@pytest.mark.parametrize("desfase", DESFASES, ids=lambda d: f"{d.total_seconds():+g}s")
def test_a_skewed_flask_clock_neither_lets_the_race_through_nor_rejects_a_later_login(
    client, carrera_db, app_engine, dev_headers, monkeypatch, desfase
):
    _reloj_de_flask(monkeypatch, desfase)
    persona = _persona(carrera_db)
    _intercalar(monkeypatch, _preparar("recuperacion", client, app_engine, persona, dev_headers))
    assert _tenant_login(client, persona.email, PASSWORD).status_code == 401

    response = _tenant_login(client, persona.email, NUEVA)
    assert response.status_code == 200
    assert client.get("/auth/me", headers=_bearer(response)).status_code == 200


# --- Ventana [t0, COMMIT]: la transacción del cambio empezó antes de la lectura del login ----


def _hash_guardado(db: AccesoDb, persona: Persona) -> str:
    (row,) = filas(db, "select password_hash from usuario where id = :u", {"u": persona.usuario_id})
    return row["password_hash"]


def _cambio_en_transaccion(
    via: str, db: AccesoDb, app_engine: Engine, persona: Persona, dev: Dev
) -> Callable[[Connection], None]:
    """La función real de cada vía, para ejecutarla en una transacción ya abierta."""
    nuevo_hash = HASHER.hash(NUEVA)
    if via == "consola":

        def consola(conn: Connection) -> None:
            conn.execute(
                text("select acceso.plataforma_restablecer_password_usuario(:d, :t, :u, :h)"),
                {"d": dev.id, "t": persona.tenant_id, "u": persona.usuario_id, "h": nuevo_hash},
            )

        return consola
    if via == "cambio_propio":
        actual = _hash_guardado(db, persona)

        def propio(conn: Connection) -> None:
            assert conn.scalar(
                text("select acceso.cambiar_password_propio(:u, :t, :a, :h)"),
                {"u": persona.usuario_id, "t": persona.tenant_id, "a": actual, "h": nuevo_hash},
            )

        return propio
    assert via == "recuperacion"
    token = secrets.token_urlsafe(32)
    with app_engine.begin() as conn:
        assert conn.scalar(
            text("select acceso.solicitar_recuperacion(:e, :c)"),
            {"e": persona.email, "c": token_key(token)},
        )

    def recuperar(conn: Connection) -> None:
        restablecido = conn.scalar(
            text("select acceso.restablecer_contrasena(:c, :h)"),
            {"c": token_key(token), "h": nuevo_hash},
        )
        assert restablecido == persona.usuario_id

    return recuperar


@pytest.mark.parametrize("via", VIAS)
def test_a_change_whose_transaction_began_before_the_read_emits_no_session(
    client, carrera_db, app_engine, plat_dev, monkeypatch, caplog, via
):
    # El corte (now() de la transacción del cambio, t0) es ANTERIOR a la lectura del hash del
    # login: compararlo con la lectura no basta; releer el hash sí.
    persona = _persona(carrera_db)
    previa = _tenant_login(client, persona.email)
    assert previa.status_code == 200
    erronea = _tenant_login(client, persona.email, ERRONEA)
    cambio = _cambio_en_transaccion(via, carrera_db, app_engine, persona, plat_dev)
    caplog.set_level(logging.DEBUG)

    with app_engine.connect() as conn:
        transaccion = conn.begin()
        t0 = conn.scalar(text("select now()"))

        def accion() -> None:
            cambio(conn)
            transaccion.commit()

        envoltura = _intercalar(monkeypatch, accion)
        response = _tenant_login(client, persona.email, PASSWORD)

    assert envoltura.disparado
    assert _corte(carrera_db, persona) == t0
    assert response.status_code == 401
    assert _sin_request_id(response) == _sin_request_id(erronea)
    assert "access_token" not in response.get_json()
    assert response.headers.getlist("Set-Cookie") == []
    # Ninguna familia nueva; la previa quedó revocada por el cambio.
    assert _familias(carrera_db, persona) == 1
    assert _vivos(carrera_db, persona) == 0
    # El rechazo se registra en INFO, solo con el usuario_id.
    rechazos = [r for r in caplog.records if "D48" in r.getMessage()]
    assert len(rechazos) == 1
    assert rechazos[0].levelno == logging.INFO
    assert str(persona.usuario_id) in rechazos[0].getMessage()
    for secreto in (persona.email, PASSWORD, NUEVA, "$argon2"):
        assert secreto not in caplog.text
    # La nueva entra después.
    monkeypatch.undo()
    assert _tenant_login(client, persona.email, NUEVA).status_code == 200


# --- Otras formas de que lo releído no sea lo verificado --------------------------------------


def _nuevo_email() -> str:
    return f"movido.{uuid.uuid4().hex[:10]}@ejemplo.test"


def test_a_hash_change_without_a_cut_is_also_rejected(client, carrera_db, monkeypatch):
    persona = _persona(carrera_db)

    def sin_corte() -> None:
        with carrera_db.migrator.begin() as conn:
            conn.execute(
                text("update usuario set password_hash = :h where id = :u"),
                {"h": HASHER.hash(NUEVA), "u": persona.usuario_id},
            )

    _intercalar(monkeypatch, sin_corte)
    response = _tenant_login(client, persona.email, PASSWORD)

    assert _corte(carrera_db, persona) is None
    assert response.status_code == 401
    assert _sin_request_id(response)["code"] == "credenciales_invalidas"
    assert _cookie(response) is None
    assert _familias(carrera_db, persona) == 0


def test_a_reread_without_rows_is_rejected(client, carrera_db, monkeypatch):
    persona = _persona(carrera_db)

    def otro_email() -> None:
        with carrera_db.migrator.begin() as conn:
            conn.execute(
                text("update usuario set email = :e where id = :u"),
                {"e": _nuevo_email(), "u": persona.usuario_id},
            )

    _intercalar(monkeypatch, otro_email)
    response = _tenant_login(client, persona.email, PASSWORD)

    assert response.status_code == 401
    assert _sin_request_id(response)["code"] == "credenciales_invalidas"
    assert _familias(carrera_db, persona) == 0


def test_a_reread_of_another_usuario_id_is_rejected_even_with_the_same_hash(
    client, carrera_db, monkeypatch
):
    # Otra cuenta (de otra empresa) pasa a tener el email y el hash exactos que se verificaron:
    # solo la comprobación del usuario_id lo rechaza.
    persona = _persona(carrera_db)
    otra = _persona(carrera_db)
    verificado = _hash_guardado(carrera_db, persona)

    def suplantar() -> None:
        with carrera_db.migrator.begin() as conn:
            conn.execute(
                text("update usuario set email = :e where id = :u"),
                {"e": _nuevo_email(), "u": persona.usuario_id},
            )
            conn.execute(
                text("update usuario set email = :e, password_hash = :h where id = :u"),
                {"e": persona.email, "h": verificado, "u": otra.usuario_id},
            )

    _intercalar(monkeypatch, suplantar)
    response = _tenant_login(client, persona.email, PASSWORD)

    assert response.status_code == 401
    assert _sin_request_id(response)["code"] == "credenciales_invalidas"
    assert _familias(carrera_db, persona) == 0
    assert _familias(carrera_db, otra) == 0


# --- La contraseña vigente sigue entrando -------------------------------------------------------


def test_the_current_password_enters_without_a_previous_cut(client, carrera_db):
    persona = _persona(carrera_db)
    assert _corte(carrera_db, persona) is None

    response = _tenant_login(client, persona.email, PASSWORD)

    assert response.status_code == 200
    assert _cookie(response) is not None
    assert _familias(carrera_db, persona) == 1
    assert client.get("/auth/me", headers=_bearer(response)).status_code == 200


def test_issue_session_checks_the_verified_hash(carrera_db, carrera_app):
    persona = _persona(carrera_db)
    guardado = _hash_guardado(carrera_db, persona)

    with carrera_app.app_context():
        distinto = service.issue_session(
            persona.usuario_id,
            persona.tenant_id,
            verificado_hash=HASHER.hash(PASSWORD),
            email=persona.email,
        )
        igual = service.issue_session(
            persona.usuario_id, persona.tenant_id, verificado_hash=guardado, email=persona.email
        )
        with pytest.raises(ValueError):
            service.issue_session(persona.usuario_id, persona.tenant_id, verificado_hash=guardado)
        with pytest.raises(ValueError):
            service.issue_session(persona.usuario_id, persona.tenant_id, email=persona.email)

    assert distinto is None
    assert igual is not None
    assert _familias(carrera_db, persona) == 1


# --- Una sola conexión: la relectura va en la de la emisión --------------------------------------


def test_issue_session_checks_out_a_single_connection(client, carrera_db, carrera_app, monkeypatch):
    persona = _persona(carrera_db)
    engine = carrera_app.extensions["assetcontrol.db"].engine
    real = service.issue_session
    conexiones: list[int] = []

    def contar(*args, **kwargs):
        sacadas: list[int] = []

        def al_sacar(*_):
            sacadas.append(1)

        event.listen(engine, "checkout", al_sacar)
        try:
            return real(*args, **kwargs)
        finally:
            event.remove(engine, "checkout", al_sacar)
            conexiones.append(len(sacadas))

    monkeypatch.setattr(service, "issue_session", contar)
    response = _tenant_login(client, persona.email, PASSWORD)

    assert response.status_code == 200
    assert conexiones == [1]


def _app_con_pool(db: AccesoDb, tamano: int) -> Flask:
    """La app con un pool de ``tamano`` conexiones y sin desborde."""
    flask_app = make_plat_app(db)
    anterior = flask_app.extensions["assetcontrol.db"]
    engine = create_engine(db.app_url, pool_size=tamano, max_overflow=0, pool_timeout=5)
    event.listen(engine, "connect", app_db._verify_role_on_connect)
    flask_app.extensions["assetcontrol.db"] = app_db._Database(
        engine=engine,
        session_factory=sessionmaker(
            bind=engine, class_=app_db._TenantSession, expire_on_commit=False
        ),
        plataforma_factory=sessionmaker(
            bind=engine, class_=app_db._PlataformaSession, expire_on_commit=False
        ),
    )
    anterior.engine.dispose()
    return flask_app


def test_concurrent_logins_do_not_exhaust_a_small_pool(carrera_db):
    personas = [_persona(carrera_db) for _ in range(6)]
    flask_app = _app_con_pool(carrera_db, 2)
    estados: dict[uuid.UUID, int] = {}
    salida = threading.Barrier(len(personas))

    def entrar(persona: Persona) -> None:
        cliente = flask_app.test_client(use_cookies=False)
        salida.wait()
        estados[persona.usuario_id] = _tenant_login(cliente, persona.email).status_code

    try:
        hilos = [threading.Thread(target=entrar, args=(p,)) for p in personas]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(timeout=60)
    finally:
        dispose(flask_app)

    assert estados == {p.usuario_id: 200 for p in personas}
    for persona in personas:
        assert _familias(carrera_db, persona) == 1


# --- Aislamiento de tenant ------------------------------------------------------------------------


def test_the_reread_is_of_the_same_usuario_id_under_the_tenant_session(
    client, carrera_db, monkeypatch
):
    persona = _persona(carrera_db)
    real = service.releer_login
    vistos: list[tuple[uuid.UUID, list]] = []

    def espiar(session, email):
        rows = real(session, email)
        vistos.append((session.scoped_tenant, rows))
        return rows

    monkeypatch.setattr(service, "releer_login", espiar)
    response = _tenant_login(client, persona.email, PASSWORD)

    assert response.status_code == 200
    ((tenant, rows),) = vistos
    assert tenant == persona.tenant_id
    assert [row.usuario_id for row in rows] == [persona.usuario_id]
    assert [row.tenant_id for row in rows] == [persona.tenant_id]


def test_a_race_on_one_account_neither_affects_nor_is_affected_by_another_tenant(
    client, carrera_db, app_engine, dev_headers, monkeypatch
):
    persona = _persona(carrera_db)
    otra = _persona(carrera_db)
    cambiar = _preparar("consola", client, app_engine, persona, dev_headers)
    de_la_otra: list = []

    def cambio_y_login_ajeno() -> None:
        cambiar()
        de_la_otra.append(_tenant_login(client, otra.email, PASSWORD))

    _intercalar(monkeypatch, cambio_y_login_ajeno)
    response = _tenant_login(client, persona.email, PASSWORD)
    monkeypatch.undo()

    assert response.status_code == 401
    (ajeno,) = de_la_otra
    assert ajeno.status_code == 200
    assert client.get("/auth/me", headers=_bearer(ajeno)).status_code == 200
    assert _familias(carrera_db, otra) == 1
    assert _vivos(carrera_db, otra) == 1
    assert _corte(carrera_db, otra) is None
    assert _familias(carrera_db, persona) == 0


def test_a_login_with_two_active_memberships_still_fails_closed(client, carrera_db):
    persona = _persona(carrera_db)
    otra = _persona(carrera_db)
    with carrera_db.migrator.begin() as conn:
        conn.execute(
            text("insert into membresia (tenant_id, usuario_id, rol) values (:t, :u, 'contador')"),
            {"t": otra.tenant_id, "u": persona.usuario_id},
        )

    response = _tenant_login(client, persona.email, PASSWORD)

    assert response.status_code == 401
    assert _familias(carrera_db, persona) == 0
