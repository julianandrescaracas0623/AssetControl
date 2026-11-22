"""Recuperar y restablecer contraseña por HTTP (spec 014, T4; R1–R5, R8–R16; A1, A3, A5, A6,
A8, A9, A11, A12, A15; requisitos de seguridad de «Notas de cierre T2» y «T3 y requisitos
para T4» de ``tasks.md``).

Sobre una base temporal migrada a ``head`` con dos tenants sintéticos (A y B):

- ``POST /auth/recuperar`` ``{email}`` (público): siempre el mismo ``202`` (estado, cuerpo
  y cabeceras salvo ``X-Request-ID``) exista o no la cuenta, esté o no activa, tenga 0, 1
  o varias membresías activas o sea un correo no normalizable o no ASCII. Los contadores
  ``recuperar_ip`` y ``recuperar_cuenta`` se suman en la **misma** transacción que
  ``acceso.solicitar_recuperacion`` (M1 de T2: una escritura en todas las ramas) y el
  correo se programa solo tras el ``COMMIT`` y solo si la función creó el enlace, con el
  correo normalizado y el token recién generado. Sin correo configurado: el mismo ``202``
  sin tocar la base.
- ``POST /auth/restablecer`` ``{token, password}`` (público): forma y política antes de
  contar; ``restablecer_ip``; Argon2 siempre (también con enlace inválido); la función de
  la base es la primera sentencia de una transacción nueva ``READ COMMITTED`` (B2);
  ``204`` sin sesión ni cookie; enlace inválido por cualquier motivo -> el mismo ``400
  enlace_invalido``.

Datos sintéticos (``@ejemplo.test``).
"""

import json
import logging
import threading
import uuid
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import argon2
import pytest
from acceso_db import (
    ADMIN_A,
    ADMIN_B,
    CONTADOR_B,
    PASSWORD,
    SECRET_KEY,
    TENANT_A,
    TENANT_B,
    AccesoDb,
    Cuenta,
    dispose,
    temporary_acceso_db,
)
from flask import Flask, has_request_context
from sqlalchemy import event, text

from app import create_app
from app import db as app_db
from app.auth import recuperacion
from app.auth import routes as auth_routes
from app.auth.credentials import ARGON2_TEST_PARAMS, get_passwords, token_key, token_storage_hash
from app.auth.http import AUTH_MAX_BODY_BYTES, CSRF_HEADER, CSRF_HEADER_VALUE
from app.config import Config, RateLimits
from app.correo import get_correo
from app.correo.config import CorreoConfig

RECUPERAR = "/auth/recuperar"
RESTABLECER = "/auth/restablecer"
CSRF = {CSRF_HEADER: CSRF_HEADER_VALUE}
URL_PUBLICA = "https://inventario.ejemplo.test"
REMITENTE = "AssetControl <no-responder@ejemplo.test>"
NUEVA = "Clave-Nueva-Recuperada-14"
OTRA_NUEVA = "Otra-Clave-Recuperada-14"
IP = "192.0.2.14"
OTRA_IP = "198.51.100.14"
HIGH = RateLimits(
    login_account=1000,
    login_ip=1000,
    refresh_ip=1000,
    recover_ip=1000,
    recover_account=1000,
    reset_ip=1000,
)
RECOVERY_BODY = {"mensaje": recuperacion.RECOVERY_MESSAGE}
INVALID_LINK = {
    "code": "enlace_invalido",
    "message": recuperacion.INVALID_LINK_MESSAGE,
}
RATE_LIMITED = {
    "code": "demasiadas_solicitudes",
    "message": "Demasiados intentos. Espera unos minutos e intenta de nuevo.",
}


# --- Base, app y correo falso -----------------------------------------------------------


@pytest.fixture(scope="module")
def rec_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("recuperar")


class Registro:
    """Transporte falso: guarda los mensajes que el hilo de ``Correo`` entrega."""

    def __init__(self) -> None:
        self.mensajes = []
        self._lock = threading.Lock()

    def entregar(self, mensaje) -> None:
        with self._lock:
            self.mensajes.append(mensaje)


def correo_config(carpeta: Path) -> CorreoConfig:
    return CorreoConfig(
        modo="carpeta", remitente=REMITENTE, url_publica=URL_PUBLICA, carpeta=carpeta
    )


def build_app(db: AccesoDb, carpeta: Path | None, **overrides) -> Flask:
    config = Config(
        database_url=db.app_url.render_as_string(hide_password=False),
        secret_key=SECRET_KEY,
        environment="test",
        rate_limits=HIGH,
        correo=correo_config(carpeta) if carpeta is not None else None,
    )
    flask_app = create_app(replace(config, **overrides))
    if carpeta is not None:
        get_correo(flask_app).transporte = Registro()
    return flask_app


@pytest.fixture(scope="module")
def rec_app(rec_db, tmp_path_factory) -> Iterator[Flask]:
    flask_app = build_app(rec_db, tmp_path_factory.mktemp("buzon"))
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(rec_app):
    return rec_app.test_client(use_cookies=False)


class Envios:
    """Espía de ``Correo.enviar_recuperacion``: registra cada llamada y la deja pasar.

    En el momento de la llamada comprueba, desde otra conexión (el migrador), si el enlace
    del token ya está confirmado en la base: así se prueba que el envío ocurre tras el
    ``COMMIT``. También anota si aún había contexto de petición (I1 de T4, T8: el envío se
    programa con ``call_on_close``, cuando la respuesta ya salió y el contexto se cerró) y
    el ``request_id`` que recibió.
    """

    def __init__(self, db: AccesoDb, original) -> None:
        self.db = db
        self.original = original
        self.llamadas: list[tuple[str, str, bool]] = []
        self.en_peticion: list[bool] = []
        self.request_ids: list[str | None] = []

    def __call__(self, destino: str, token: str, request_id: str | None = None) -> None:
        confirmado = enlace(self.db, token) is not None
        self.llamadas.append((destino, token, confirmado))
        self.en_peticion.append(has_request_context())
        self.request_ids.append(request_id)
        return self.original(destino, token, request_id=request_id)


@pytest.fixture
def envios(rec_app, rec_db, monkeypatch) -> Envios:
    correo = get_correo(rec_app)
    spy = Envios(rec_db, correo.enviar_recuperacion)
    monkeypatch.setattr(correo, "enviar_recuperacion", spy)
    return spy


@pytest.fixture(autouse=True)
def limpio(rec_db, rec_app) -> Iterator[None]:
    """Cada prueba parte sin contadores ni mensajes (la base del módulo es compartida)."""
    with rec_db.migrator.begin() as conn:
        conn.execute(text("delete from limite_tasa"))
    registro = get_correo(rec_app).transporte
    if isinstance(registro, Registro):
        registro.mensajes.clear()
    yield
    get_correo(rec_app).esperar(5)


_HASHER = argon2.PasswordHasher.from_parameters(ARGON2_TEST_PARAMS)


def crear_cuenta(
    db: AccesoDb,
    *,
    membresias=((TENANT_A, "contador", True),),
    activo: bool = True,
    email: str | None = None,
) -> Cuenta:
    cuenta = Cuenta(
        uuid.uuid4(), email or f"persona.{uuid.uuid4().hex[:10]}@ejemplo.test", "Sintética"
    )
    with db.migrator.begin() as conn:
        conn.execute(
            text(
                "insert into usuario (id, email, nombre, password_hash, activo) "
                "values (:id, :e, :n, :h, :a)"
            ),
            {
                "id": cuenta.usuario_id,
                "e": cuenta.email,
                "n": cuenta.nombre,
                "h": _HASHER.hash(PASSWORD),
                "a": activo,
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
    return cuenta


def enlace(db: AccesoDb, token: str) -> dict | None:
    with db.migrator.connect() as conn:
        row = (
            conn.execute(
                text("select * from recuperacion_contrasena where token_hash = :h"),
                {"h": token_storage_hash(token)},
            )
            .mappings()
            .one_or_none()
        )
    return None if row is None else dict(row)


def enlaces_de(db: AccesoDb, cuenta: Cuenta) -> list[dict]:
    with db.migrator.connect() as conn:
        rows = conn.execute(
            text("select * from recuperacion_contrasena where usuario_id = :u order by creado_en"),
            {"u": cuenta.usuario_id},
        ).mappings()
        return [dict(row) for row in rows]


def todos_los_enlaces(db: AccesoDb) -> int:
    with db.migrator.connect() as conn:
        return conn.scalar(text("select count(*) from recuperacion_contrasena"))


def password_hash_de(db: AccesoDb, cuenta: Cuenta) -> str:
    with db.migrator.connect() as conn:
        return conn.scalar(
            text("select password_hash from usuario where id = :u"), {"u": cuenta.usuario_id}
        )


def contadores(db: AccesoDb) -> dict[str, int]:
    with db.migrator.connect() as conn:
        rows = conn.execute(text("select ambito, sum(intentos) from limite_tasa group by ambito"))
        return {ambito: int(total) for ambito, total in rows}


def recuperar(client, email, ip=IP, headers=None, **kwargs):
    # ``buffered``: como un servidor WSGI real, se lee el cuerpo y se cierra la respuesta,
    # lo que ejecuta los ``call_on_close`` (ahí se programa el correo, I1 de T4).
    kwargs.setdefault("buffered", True)
    return client.post(
        RECUPERAR,
        json={"email": email},
        headers={**CSRF, **(headers or {})},
        environ_base={"REMOTE_ADDR": ip},
        **kwargs,
    )


def restablecer(client, token, password=NUEVA, ip=IP, headers=None):
    return client.post(
        RESTABLECER,
        json={"token": token, "password": password},
        headers={**CSRF, **(headers or {})},
        environ_base={"REMOTE_ADDR": ip},
    )


def login(client, email, password):
    return client.post(
        "/auth/login", json={"email": email, "password": password}, environ_base={"REMOTE_ADDR": IP}
    )


def refresh_cookie(response) -> str:
    return response.headers["Set-Cookie"].split(";", 1)[0]


def refrescar(client, cookie: str):
    return client.post("/auth/refresh", headers={**CSRF, "Cookie": cookie})


def comparable(response) -> tuple:
    """Todo lo observable de la respuesta salvo el ``request_id``."""
    headers = sorted(
        (k.lower(), v) for k, v in response.headers.items() if k.lower() != "x-request-id"
    )
    body = response.get_json(silent=True)
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        body = {"error": {k: v for k, v in body["error"].items() if k != "request_id"}}
    return response.status_code, body, headers


def token_por_correo(client, envios: Envios, cuenta: Cuenta) -> str:
    """Pide un enlace para ``cuenta`` y devuelve el token que salió hacia el correo."""
    antes = len(envios.llamadas)
    assert recuperar(client, cuenta.email).status_code == 202
    assert len(envios.llamadas) == antes + 1
    return envios.llamadas[-1][1]


def error_of(response) -> dict:
    body = response.get_json()
    assert set(body) == {"error"}
    return {k: v for k, v in body["error"].items() if k != "request_id"}


class HasherSpy:
    """Cuenta las llamadas a Argon2 del ``Passwords`` de la app."""

    def __init__(self, hasher) -> None:
        self._hasher = hasher
        self.calls = 0

    def hash(self, password, **kwargs):
        self.calls += 1
        return self._hasher.hash(password, **kwargs)

    def verify(self, target, password):
        self.calls += 1
        return self._hasher.verify(target, password)

    def __getattr__(self, name):
        return getattr(self._hasher, name)


@pytest.fixture
def hasher_spy(rec_app, monkeypatch) -> HasherSpy:
    with rec_app.app_context():
        passwords = get_passwords()
    spy = HasherSpy(passwords._hasher)
    monkeypatch.setattr(passwords, "_hasher", spy)
    return spy


def log_text(caplog) -> str:
    partes = []
    for record in caplog.records:
        partes.append(record.getMessage())
        if record.exc_info:
            partes.append(logging.Formatter().formatException(record.exc_info))
        if record.exc_text:
            partes.append(record.exc_text)
    return "\n".join(partes)


# --- Catálogo y forma -------------------------------------------------------------------


def test_both_endpoints_are_public_posts_under_auth(rec_app):
    rules = {rule.rule: rule for rule in rec_app.url_map.iter_rules()}
    for path, endpoint in ((RECUPERAR, "auth.recuperar"), (RESTABLECER, "auth.restablecer")):
        assert rules[path].methods - {"HEAD", "OPTIONS"} == {"POST"}
        assert rules[path].endpoint == endpoint
        assert not hasattr(rec_app.view_functions[endpoint], "required_roles")


@pytest.mark.parametrize("path", [RECUPERAR, RESTABLECER])
def test_without_csrf_header_is_403_before_reading_or_counting(client, rec_db, path):
    for headers in ({}, {CSRF_HEADER: "0"}):
        response = client.post(path, json={"email": ADMIN_A.email}, headers=headers)
        assert response.status_code == 403
        assert error_of(response)["code"] == "prohibido"
    # Antes de mirar el cuerpo: uno mal formado también es 403.
    assert client.post(path, data="no-json", content_type="text/plain").status_code == 403
    assert contadores(rec_db) == {}


@pytest.mark.parametrize("path", [RECUPERAR, RESTABLECER])
@pytest.mark.parametrize(
    "headers",
    [
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "none"},
        {"Origin": "https://sitio-ajeno.example"},
        {"Origin": "null"},
    ],
)
def test_cross_site_is_403_and_nothing_is_counted(client, rec_db, envios, path, headers):
    body = {"email": ADMIN_A.email, "token": "x" * 43, "password": NUEVA}
    response = client.post(path, json=body, headers={**CSRF, **headers})
    assert response.status_code == 403
    assert contadores(rec_db) == {}
    assert envios.llamadas == []


@pytest.mark.parametrize("path", [RECUPERAR, RESTABLECER])
def test_body_over_4kb_is_413(client, rec_db, path):
    response = client.post(
        path, data="x" * (AUTH_MAX_BODY_BYTES + 1), content_type="application/json", headers=CSRF
    )
    assert response.status_code == 413
    assert error_of(response)["code"] == "cuerpo_demasiado_grande"
    assert contadores(rec_db) == {}


@pytest.mark.parametrize(
    ("path", "kwargs"),
    [
        (RECUPERAR, {"data": "email=a@b.c", "content_type": "text/plain"}),
        (RECUPERAR, {"json": ["a@b.c"]}),
        (RECUPERAR, {"json": {}}),
        (RECUPERAR, {"json": {"email": 5}}),
        (RECUPERAR, {"json": {"email": None}}),
        (RESTABLECER, {"data": "token=x", "content_type": "text/plain"}),
        (RESTABLECER, {"json": {"token": "x" * 43}}),
        (RESTABLECER, {"json": {"password": NUEVA}}),
        (RESTABLECER, {"json": {"token": 1, "password": NUEVA}}),
        (RESTABLECER, {"json": {"token": "x" * 43, "password": ["x"]}}),
        # Sin «clave» ni «email»: el cuerpo es {token, password} (plan §5).
        (RESTABLECER, {"json": {"clave": "a" * 64, "password": NUEVA}}),
    ],
)
def test_malformed_body_is_400_before_counting(client, rec_db, envios, hasher_spy, path, kwargs):
    response = client.post(path, headers=CSRF, **kwargs)
    assert response.status_code == 400
    assert error_of(response) == {
        "code": "solicitud_invalida",
        "message": "La solicitud no es válida.",
    }
    assert contadores(rec_db) == {}
    assert envios.llamadas == []
    assert hasher_spy.calls == 0


@pytest.mark.parametrize("path", [RECUPERAR, RESTABLECER])
def test_auth_headers_and_no_cookies(client, envios, path):
    body = {"email": ADMIN_A.email, "token": "x" * 43, "password": NUEVA}
    response = client.post(path, json=body, headers=CSRF)
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert "Set-Cookie" not in response.headers


# --- Recuperar: respuesta uniforme (A1, R1, R2; requisito 1) ----------------------------


def test_recover_is_the_same_202_for_every_kind_of_email(client, rec_db, envios):
    elegible = crear_cuenta(rec_db)
    inactivo = crear_cuenta(rec_db, activo=False)
    membresia_inactiva = crear_cuenta(rec_db, membresias=((TENANT_A, "contador", False),))
    dos_membresias = crear_cuenta(
        rec_db, membresias=((TENANT_A, "contador", True), (TENANT_B, "contador", True))
    )
    sin_membresia = crear_cuenta(rec_db, membresias=())
    no_ascii = crear_cuenta(rec_db, email=f"ñandú.{uuid.uuid4().hex[:6]}@ejemplo.test")
    casos = [
        elegible.email,
        "nadie.registrado@ejemplo.test",
        inactivo.email,
        membresia_inactiva.email,
        dos_membresias.email,
        sin_membresia.email,
        no_ascii.email,
        "",
        "   ",
        "con\x00nul@ejemplo.test",
        "no-es-un-correo",
        "a@b@c",
        "x" * 3000,
        "Ⅻ@ejemplo.test",
    ]
    antes = todos_los_enlaces(rec_db)

    respuestas = [recuperar(client, email) for email in casos]

    esperado = comparable(respuestas[0])
    assert esperado[0] == 202
    assert esperado[1] == RECOVERY_BODY
    for email, response in zip(casos, respuestas, strict=True):
        assert comparable(response) == esperado, email
        assert email not in response.get_data(as_text=True) or email in ("", "   ")
    # Solo el elegible crea un enlace y programa un correo.
    assert todos_los_enlaces(rec_db) == antes + 1
    assert len(enlaces_de(rec_db, elegible)) == 1
    for cuenta in (inactivo, membresia_inactiva, dos_membresias, sin_membresia, no_ascii):
        assert enlaces_de(rec_db, cuenta) == []
    assert [destino for destino, _, _ in envios.llamadas] == [elegible.email]


def test_recover_does_not_depend_on_the_mail_module_failing(client, rec_db, rec_app, monkeypatch):
    elegible = crear_cuenta(rec_db)
    referencia = comparable(recuperar(client, "nadie.mas@ejemplo.test"))

    def falla(destino, token, **kwargs):
        raise RuntimeError(f"fallo sintético {destino} {token}")

    monkeypatch.setattr(get_correo(rec_app), "enviar_recuperacion", falla)
    response = recuperar(client, elegible.email)

    assert comparable(response) == referencia


def test_mail_is_sent_after_commit_with_normalized_email_and_fresh_token(client, rec_db, envios):
    cuenta = crear_cuenta(rec_db)

    response = recuperar(client, f"  {cuenta.email.upper()}  ")

    assert response.status_code == 202
    [(destino, token, confirmado)] = envios.llamadas
    assert destino == cuenta.email
    assert confirmado, "el correo se programó antes del COMMIT"
    # I1 de T4: se programa al cerrar la respuesta, sin contexto de petición, con el
    # ``request_id`` de la petición capturado antes.
    assert envios.en_peticion == [False]
    assert envios.request_ids == [response.headers["X-Request-ID"]]
    fila = enlace(rec_db, token)
    assert fila is not None and fila["usuario_id"] == cuenta.usuario_id
    assert fila["usada_en"] is None and fila["invalidada_en"] is None
    assert token not in response.get_data(as_text=True)
    assert all(token not in value for _, value in response.headers.items())

    # Otra solicitud genera otro token e invalida el anterior (R4).
    recuperar(client, cuenta.email)
    segundo = envios.llamadas[-1][1]
    assert segundo != token
    assert enlace(rec_db, token)["invalidada_en"] is not None


def test_link_uses_public_url_despite_forged_host_headers(client, rec_db, rec_app):
    """A15 (requisito 6): la base del enlace sale solo de la configuración."""
    cuenta = crear_cuenta(rec_db)
    response = recuperar(
        client,
        cuenta.email,
        headers={
            "Host": "atacante.example",
            "X-Forwarded-Host": "reenviado.atacante.example",
            "X-Forwarded-Proto": "http",
            "Origin": "https://origen.atacante.example",
            "Sec-Fetch-Site": "same-origin",
        },
    )
    assert response.status_code == 202
    correo = get_correo(rec_app)
    assert correo.esperar(5)
    [mensaje] = correo.transporte.mensajes
    contenido = mensaje.get_body(preferencelist=("plain",)).get_content()
    assert mensaje["To"] == cuenta.email
    assert f"{URL_PUBLICA}/restablecer#" in contenido
    assert "atacante" not in contenido
    assert "atacante" not in str(mensaje)


def test_commit_failure_sends_nothing(client, rec_db, rec_app, envios, caplog):
    cuenta = crear_cuenta(rec_db)
    engine = rec_app.extensions["assetcontrol.db"].engine

    def falla_commit(conn):
        raise RuntimeError("commit sintético fallido")

    event.listen(engine, "commit", falla_commit)
    try:
        with caplog.at_level(logging.DEBUG):
            response = recuperar(client, cuenta.email)
    finally:
        event.remove(engine, "commit", falla_commit)
        # Fallar desde el evento deja la conexión en transacción y SQLAlchemy no la limpia
        # al devolverla (artefacto de la simulación: un COMMIT fallido real de psycopg la
        # deja inactiva). Se descarta el pool para no contaminar las pruebas siguientes.
        engine.dispose()

    assert response.status_code == 500
    assert error_of(response)["code"] == "error_interno"
    assert envios.llamadas == []
    assert enlaces_de(rec_db, cuenta) == []
    assert cuenta.email not in log_text(caplog)


def test_counter_and_request_share_one_transaction(client, rec_db, rec_app, envios):
    """M1 de T2: el upsert de ``limite_tasa`` va en la misma transacción que
    ``solicitar_recuperacion``; hay escritura en todas las ramas."""
    engine = rec_app.extensions["assetcontrol.db"].engine
    eventos: list[str] = []

    def begin(conn):
        eventos.append("BEGIN")

    def commit(conn):
        eventos.append("COMMIT")

    def ejecuta(conn, cursor, statement, parameters, context, executemany):
        if "limite_tasa" in statement:
            eventos.append("contador")
        elif "solicitar_recuperacion" in statement:
            eventos.append("solicitar")

    escuchas = (("begin", begin), ("commit", commit), ("before_cursor_execute", ejecuta))
    for nombre, fn in escuchas:
        event.listen(engine, nombre, fn)
    try:
        for email in (crear_cuenta(rec_db).email, "nadie.aqui@ejemplo.test", "no-normalizable"):
            eventos.clear()
            assert recuperar(client, email).status_code == 202
            assert eventos == ["BEGIN", "contador", "contador", "solicitar", "COMMIT"], email
    finally:
        for nombre, fn in escuchas:
            event.remove(engine, nombre, fn)


def test_invalid_key_from_the_database_is_a_generic_500(client, rec_db, envios, monkeypatch):
    """``22023 clave_invalida`` de ``solicitar`` es un error interno, nunca otra respuesta."""
    cuenta = crear_cuenta(rec_db)
    monkeypatch.setattr(recuperacion, "token_key", lambda token: "NO-ES-HEX")

    for email in (cuenta.email, "nadie.otro@ejemplo.test"):
        response = recuperar(client, email)
        assert response.status_code == 500
        assert error_of(response)["code"] == "error_interno"
    assert envios.llamadas == []
    assert enlaces_de(rec_db, cuenta) == []


# --- Recuperación desactivada (requisito 4) --------------------------------------------


def test_disabled_recovery_answers_the_same_without_touching_the_database(client, rec_db, envios):
    cuenta = crear_cuenta(rec_db)
    token = token_por_correo(client, envios, cuenta)
    referencia = comparable(recuperar(client, "nadie.desactivado@ejemplo.test"))
    apagada = build_app(rec_db, None)
    engine = apagada.extensions["assetcontrol.db"].engine
    sentencias: list[str] = []

    def ejecuta(conn, cursor, statement, parameters, context, executemany):
        sentencias.append(statement)

    event.listen(engine, "before_cursor_execute", ejecuta)
    try:
        apagada_client = apagada.test_client(use_cookies=False)
        respuestas = [
            recuperar(apagada_client, email)
            for email in (cuenta.email, "nadie.desactivado@ejemplo.test", "", "no-es-correo")
        ]
    finally:
        event.remove(engine, "before_cursor_execute", ejecuta)
        dispose(apagada)

    for response in respuestas:
        assert comparable(response) == referencia
    assert sentencias == []
    # El enlace pendiente sigue vivo: no se crea ni invalida nada (no amplifica B4).
    fila = enlace(rec_db, token)
    assert fila["invalidada_en"] is None and fila["usada_en"] is None
    assert len(enlaces_de(rec_db, cuenta)) == 1


# --- Límites de tasa (A8; requisito 7) --------------------------------------------------


@pytest.fixture
def limited_app(rec_db, tmp_path) -> Iterator[Flask]:
    flask_app = build_app(
        rec_db,
        tmp_path,
        rate_limits=replace(HIGH, recover_ip=3, recover_account=2, reset_ip=2),
    )
    yield flask_app
    get_correo(flask_app).esperar(5)
    dispose(flask_app)


def test_recover_ip_limit_is_429_also_for_unknown_emails(limited_app, rec_db):
    client = limited_app.test_client(use_cookies=False)
    for n in range(3):
        assert recuperar(client, f"nadie.{n}@ejemplo.test").status_code == 202
    response = recuperar(client, "nadie.3@ejemplo.test")
    assert response.status_code == 429
    assert error_of(response) == RATE_LIMITED
    assert response.headers["Retry-After"] == "900"
    assert recuperar(client, "nadie.4@ejemplo.test", ip=OTRA_IP).status_code == 202


def test_recover_account_limit_counts_the_same_whether_the_email_exists(limited_app, rec_db):
    client = limited_app.test_client(use_cookies=False)
    cuenta = crear_cuenta(rec_db)
    resultados = {}
    for email in (cuenta.email, "nadie.limite@ejemplo.test"):
        estados = [recuperar(client, email, ip=f"203.0.113.{n}").status_code for n in range(1, 4)]
        resultados[email] = estados
        # Igual con mayúsculas y espacios: es la misma cuenta normalizada.
        assert recuperar(client, f" {email.upper()} ", ip="203.0.113.9").status_code == 429
    assert resultados[cuenta.email] == resultados["nadie.limite@ejemplo.test"] == [202, 202, 429]
    # Solo se crearon los dos enlaces permitidos; el segundo invalidó al primero.
    assert len(enlaces_de(rec_db, cuenta)) == 2


def test_reset_ip_limit_is_429_before_argon2(limited_app, rec_db):
    client = limited_app.test_client(use_cookies=False)
    for _ in range(2):
        assert restablecer(client, "x" * 43).status_code == 400
    response = restablecer(client, "x" * 43)
    assert response.status_code == 429
    assert error_of(response) == RATE_LIMITED
    # T8 (pendiente de T7): ``Retry-After`` constante (la ventana) de punta a punta.
    assert response.headers["Retry-After"] == "900"
    assert contadores(rec_db) == {"restablecer_ip": 3}


def test_recover_counter_survives_a_failed_request(client, rec_db, envios, monkeypatch):
    monkeypatch.setattr(
        app_db, "_SOLICITAR_RECUPERACION", text("select acceso.funcion_que_no_existe(:email)")
    )
    response = recuperar(client, "nadie.fallo@ejemplo.test")
    assert response.status_code == 500
    assert contadores(rec_db) == {"recuperar_ip": 1, "recuperar_cuenta": 1}
    assert envios.llamadas == []


@pytest.mark.parametrize("path", [RECUPERAR, RESTABLECER])
def test_counter_failure_is_503_without_request_argon2_or_mail(
    client, rec_db, envios, hasher_spy, monkeypatch, caplog, path
):
    cuenta = crear_cuenta(rec_db)
    monkeypatch.setattr(app_db, "_CONTAR_INTENTO", text("select * from tabla_que_no_existe"))
    body = {"email": cuenta.email, "token": "x" * 43, "password": NUEVA}

    with caplog.at_level(logging.DEBUG):
        response = client.post(path, json=body, headers=CSRF)

    assert response.status_code == 503
    assert error_of(response)["code"] == "servicio_no_disponible"
    assert response.headers["Retry-After"] == "10"
    assert envios.llamadas == []
    assert hasher_spy.calls == 0
    assert enlaces_de(rec_db, cuenta) == []
    assert cuenta.email not in log_text(caplog)
    assert "tabla_que_no_existe" not in log_text(caplog)


# --- Restablecer (A3, A5, A6, A7; R9–R11) -----------------------------------------------


def test_reset_changes_password_revokes_all_sessions_and_issues_none(client, rec_db, envios):
    cuenta = crear_cuenta(rec_db)
    sesiones = [login(client, cuenta.email, PASSWORD) for _ in range(2)]
    assert all(s.status_code == 200 for s in sesiones)
    cookies = [refresh_cookie(s) for s in sesiones]
    viejo = token_por_correo(client, envios, cuenta)
    token = token_por_correo(client, envios, cuenta)

    response = restablecer(client, token)

    assert response.status_code == 204
    assert response.get_data() == b""
    assert "Set-Cookie" not in response.headers
    assert login(client, cuenta.email, PASSWORD).status_code == 401
    assert login(client, cuenta.email, NUEVA).status_code == 200
    for cookie in cookies:
        assert refrescar(client, cookie).status_code == 401
    # Ningún enlace pendiente queda vivo; el usado queda marcado (nada se borra).
    filas = enlaces_de(rec_db, cuenta)
    assert len(filas) == 2
    assert all(f["usada_en"] is not None or f["invalidada_en"] is not None for f in filas)
    assert enlace(rec_db, token)["usada_en"] is not None
    assert comparable(restablecer(client, viejo)) == comparable(restablecer(client, token))


def test_every_invalid_link_is_the_same_400_and_still_costs_argon2(
    client, rec_db, envios, hasher_spy
):
    cuenta = crear_cuenta(rec_db)
    usado = token_por_correo(client, envios, cuenta)
    assert restablecer(client, usado).status_code == 204
    invalidado = token_por_correo(client, envios, cuenta)
    vencido = token_por_correo(client, envios, cuenta)
    assert enlace(rec_db, invalidado)["invalidada_en"] is not None
    with rec_db.migrator.begin() as conn:
        conn.execute(
            text(
                "update recuperacion_contrasena set creado_en = now() - interval '40 minutes', "
                "expira_en = now() - interval '11 minutes' where token_hash = :h"
            ),
            {"h": token_storage_hash(vencido)},
        )
    inactivo = crear_cuenta(rec_db)
    de_inactivo = token_por_correo(client, envios, inactivo)
    with rec_db.migrator.begin() as conn:
        conn.execute(
            text("update usuario set activo = false where id = :u"), {"u": inactivo.usuario_id}
        )
    hash_antes = password_hash_de(rec_db, cuenta)
    tokens = {
        "usado": usado,
        "invalidado": invalidado,
        "vencido": vencido,
        "cuenta inactiva": de_inactivo,
        "inexistente": "A" * 43,
        "vacío": "",
        "corto": "x",
        "largo": "y" * 3000,
        "sustituto": "\ud800abc",
        "clave en lugar de token": token_key(vencido),
    }
    hasher_spy.calls = 0

    respuestas = {motivo: restablecer(client, token) for motivo, token in tokens.items()}

    esperado = comparable(respuestas["inexistente"])
    assert esperado[0] == 400
    assert error_of(respuestas["inexistente"]) == INVALID_LINK
    for motivo, response in respuestas.items():
        assert comparable(response) == esperado, motivo
    assert hasher_spy.calls == len(tokens)
    assert password_hash_de(rec_db, cuenta) == hash_antes
    # El rechazo no consumió el de la cuenta inactiva (la función revierte).
    assert enlace(rec_db, de_inactivo)["usada_en"] is None


@pytest.mark.parametrize(
    ("password", "code"),
    [
        ("corta", "contrasena_corta"),
        ("x" * 129, "contrasena_larga"),
        ("contraseña123", "contrasena_comun"),
        ("Contrasena123", "contrasena_comun"),
        ("\ud800" + "a" * 12, "contrasena_invalida"),
    ],
)
def test_password_policy_rejects_without_hashing_counting_or_consuming(
    client, rec_db, envios, hasher_spy, password, code
):
    cuenta = crear_cuenta(rec_db)
    token = token_por_correo(client, envios, cuenta)
    contados = contadores(rec_db)
    hasher_spy.calls = 0

    response = restablecer(client, token, password=password)

    assert response.status_code == 400
    assert error_of(response)["code"] == code
    assert hasher_spy.calls == 0
    assert contadores(rec_db) == contados
    assert enlace(rec_db, token)["usada_en"] is None
    assert restablecer(client, token).status_code == 204


def test_reset_is_the_first_statement_of_a_new_read_committed_transaction(
    client, rec_db, rec_app, envios
):
    """B2 de T2: Argon2 antes, transacción nueva y corta, sin ``tenant_session``."""
    cuenta = crear_cuenta(rec_db)
    token = token_por_correo(client, envios, cuenta)
    engine = rec_app.extensions["assetcontrol.db"].engine
    en_transaccion: list[str] = []
    vistos: list[tuple[list[str], object]] = []

    def begin(conn):
        en_transaccion.clear()

    def ejecuta(conn, cursor, statement, parameters, context, executemany):
        if "restablecer_contrasena" in statement:
            vistos.append(
                (list(en_transaccion), conn.get_execution_options().get("isolation_level"))
            )
        en_transaccion.append(statement)

    event.listen(engine, "begin", begin)
    event.listen(engine, "before_cursor_execute", ejecuta)
    try:
        assert restablecer(client, token).status_code == 204
    finally:
        event.remove(engine, "begin", begin)
        event.remove(engine, "before_cursor_execute", ejecuta)

    assert vistos == [([], "READ COMMITTED")]


def test_null_from_the_function_is_an_invalid_link_never_success(
    client, rec_db, envios, monkeypatch
):
    cuenta = crear_cuenta(rec_db)
    token = token_por_correo(client, envios, cuenta)
    monkeypatch.setattr(
        app_db,
        "_RESTABLECER_CONTRASENA",
        text(
            "select cast(null as uuid) from (select cast(:clave as text), "
            "cast(:password_hash as text)) as p"
        ),
    )
    response = restablecer(client, token)
    assert response.status_code == 400
    assert error_of(response) == INVALID_LINK


def test_other_database_errors_are_500_without_echoing_the_key(
    client, rec_db, envios, monkeypatch, caplog
):
    """Mapeo de ``DBAPIError`` sin ``str(exc)``: el mensaje de PostgreSQL repite el valor."""
    cuenta = crear_cuenta(rec_db)
    token = token_por_correo(client, envios, cuenta)
    monkeypatch.setattr(
        app_db,
        "_RESTABLECER_CONTRASENA",
        text("select cast(:clave as integer) + length(:password_hash)"),
    )
    with caplog.at_level(logging.DEBUG):
        response = restablecer(client, token)

    assert response.status_code == 500
    assert error_of(response)["code"] == "error_interno"
    texto = log_text(caplog) + response.get_data(as_text=True)
    assert token_key(token) not in texto
    assert token not in texto
    assert "$argon2id$" not in texto
    assert enlace(rec_db, token)["usada_en"] is None


def test_saturated_argon2_is_503_and_consumes_nothing(rec_db, tmp_path, envios, client):
    cuenta = crear_cuenta(rec_db)
    token = token_por_correo(client, envios, cuenta)
    ocupada = build_app(rec_db, tmp_path, argon2_max_concurrency=1)
    try:
        with ocupada.app_context():
            passwords = get_passwords()
        passwords._wait_seconds = 0
        assert passwords._slots.acquire(blocking=False)
        try:
            response = restablecer(ocupada.test_client(use_cookies=False), token)
        finally:
            passwords._slots.release()
    finally:
        dispose(ocupada)
    assert response.status_code == 503
    assert error_of(response)["code"] == "servicio_no_disponible"
    assert enlace(rec_db, token)["usada_en"] is None


# --- Aislamiento entre tenants (A11) ----------------------------------------------------


def test_reset_in_tenant_a_never_touches_tenant_b(client, rec_db, envios):
    cuenta_a = crear_cuenta(rec_db, membresias=((TENANT_A, "admin", True),))
    cuenta_b = crear_cuenta(rec_db, membresias=((TENANT_B, "admin", True),))
    sesion_a = refresh_cookie(login(client, cuenta_a.email, PASSWORD))
    sesion_b = refresh_cookie(login(client, cuenta_b.email, PASSWORD))
    sesion_admin_b = refresh_cookie(login(client, ADMIN_B.email, PASSWORD))
    pendiente_b = token_por_correo(client, envios, cuenta_b)
    hashes_b = {c.email: password_hash_de(rec_db, c) for c in (cuenta_b, ADMIN_B, CONTADOR_B)}
    token_a = token_por_correo(client, envios, cuenta_a)

    assert restablecer(client, token_a).status_code == 204

    assert refrescar(client, sesion_a).status_code == 401
    for cookie in (sesion_b, sesion_admin_b):
        assert refrescar(client, cookie).status_code == 200
    assert {c.email: password_hash_de(rec_db, c) for c in (cuenta_b, ADMIN_B, CONTADOR_B)} == (
        hashes_b
    )
    assert enlace(rec_db, pendiente_b)["invalidada_en"] is None
    assert enlace(rec_db, pendiente_b)["usada_en"] is None
    assert enlace(rec_db, pendiente_b)["tenant_id"] == TENANT_B
    assert login(client, cuenta_b.email, PASSWORD).status_code == 200
    # El token de A ya no sirve para nadie más.
    assert restablecer(client, token_a, password=OTRA_NUEVA).status_code == 400


# --- Logs y auditoría (A12; requisito 5; M2 de T2) --------------------------------------


def test_no_email_token_key_link_hash_or_password_in_logs_or_responses(
    client, rec_db, rec_app, envios, caplog
):
    cuenta = crear_cuenta(rec_db)
    with caplog.at_level(logging.DEBUG):
        r1 = recuperar(client, cuenta.email)
        assert get_correo(rec_app).esperar(5)
        token = envios.llamadas[-1][1]
        r2 = restablecer(client, token, password="corta")
        r3 = restablecer(client, token)
        r4 = restablecer(client, token)
        r5 = recuperar(client, "nadie.logs@ejemplo.test")

    nuevo_hash = password_hash_de(rec_db, cuenta)
    texto = log_text(caplog) + "".join(
        r.get_data(as_text=True) + json.dumps(dict(r.headers)) for r in (r1, r2, r3, r4, r5)
    )
    for secreto in (
        cuenta.email,
        cuenta.email.split("@")[0],
        "nadie.logs",
        token,
        token_key(token),
        token_storage_hash(token).hex(),
        "/restablecer#",
        NUEVA,
        nuevo_hash,
        "$argon2id$",
    ):
        assert secreto not in texto, secreto


def test_password_change_is_audited_with_user_and_request_id_only(client, rec_db, envios, caplog):
    cuenta = crear_cuenta(rec_db)
    token = token_por_correo(client, envios, cuenta)
    with caplog.at_level(logging.INFO):
        response = restablecer(client, token)
    assert response.status_code == 204
    request_id = response.headers["X-Request-ID"]
    auditoria = [r for r in caplog.records if "restablecida" in r.getMessage()]
    assert len(auditoria) == 1
    mensaje = auditoria[0].getMessage()
    assert auditoria[0].levelno == logging.INFO
    assert str(cuenta.usuario_id) in mensaje
    assert request_id in mensaje
    assert cuenta.email not in mensaje and token not in mensaje


def test_rejected_reset_writes_no_audit_record(client, rec_db, envios, caplog):
    with caplog.at_level(logging.INFO):
        assert restablecer(client, "B" * 43).status_code == 400
    assert not [r for r in caplog.records if "restablecida" in r.getMessage()]


def test_rejected_link_is_a_warning_with_only_the_request_id(client, rec_db, envios, caplog):
    """T8 (notas de T4): cada rechazo de enlace deja un ``WARNING`` sin datos del enlace."""
    cuenta = crear_cuenta(rec_db)
    token = token_por_correo(client, envios, cuenta)
    assert restablecer(client, token).status_code == 204
    caplog.clear()

    with caplog.at_level(logging.DEBUG):
        respuestas = [restablecer(client, t) for t in (token, "C" * 43, "")]

    avisos = [r for r in caplog.records if "Enlace de recuperación rechazado" in r.getMessage()]
    assert [r.levelno for r in avisos] == [logging.WARNING] * 3
    for registro, response in zip(avisos, respuestas, strict=True):
        assert response.status_code == 400
        assert registro.getMessage() == (
            f"Enlace de recuperación rechazado (request_id={response.headers['X-Request-ID']})"
        )
        assert registro.exc_info is None
    texto = log_text(caplog)
    for secreto in (token, token_key(token), token_storage_hash(token).hex(), "C" * 43):
        assert secreto not in texto
    assert cuenta.email not in texto and str(cuenta.usuario_id) not in texto


def test_routes_module_exposes_the_new_codes():
    assert recuperacion.INVALID_LINK[0] == "enlace_invalido"
    assert auth_routes.BAD_REQUEST[0] == "solicitud_invalida"
