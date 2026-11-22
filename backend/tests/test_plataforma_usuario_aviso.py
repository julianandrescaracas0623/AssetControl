"""Aviso por correo al definir una contraseña temporal (spec 017, C1d, T18; R61–R65; A30,
A31; CU-15).

Sobre una base temporal migrada a ``head`` con la consola habilitada y el correo en modo
``carpeta`` con un transporte falso que guarda los mensajes. Cada prueba usa una empresa
propia sembrada por el migrador (un admin y un contador).

- Tras el ``204`` de C1b, la persona recibe **un** aviso con un enlace de la 014 que
  funciona: el canje deja ``debe_cambiar_password = false``, la temporal deja de servir y
  la contraseña elegida entra. Otra definición envía otro aviso e invalida el enlace
  anterior.
- Sin enlace (membresía desactivada, dos membresías activas): el aviso sale igual, sin
  enlace. Correo apagado, error al validar, empresa desactivada: ningún mensaje.
- Un fallo al pedir el enlace o al entregar no cambia el ``204`` ni deshace la temporal.
- Ni el mensaje, ni la respuesta, ni la auditoría, ni los logs llevan la temporal ni su
  hash; los logs no llevan el correo, el token ni el enlace; los contadores de la 014 no
  cambian.

Datos sintéticos (``@ejemplo.test``).
"""

import re
import threading
import uuid
from collections.abc import Iterator
from dataclasses import dataclass

import argon2
import pytest
from acceso_db import PASSWORD, SECRET_KEY, AccesoDb, dispose, temporary_acceso_db
from flask import Flask
from plataforma_db import (
    HIGH_LIMITS,
    ejecutar,
    filas,
    login,
    nuevo_dev,
    plat_bearer,
    sembrar_dev,
)
from sqlalchemy import text

from app import create_app
from app.auth.credentials import ARGON2_TEST_PARAMS
from app.auth.http import CSRF_HEADER, CSRF_HEADER_VALUE
from app.config import Config, PlataformaConfig
from app.correo import get_correo
from app.correo.config import CorreoConfig
from app.correo.plantillas import ASUNTO_AVISO
from app.plataforma.modulos.usuarios import aviso

HASHER = argon2.PasswordHasher.from_parameters(ARGON2_TEST_PARAMS)
URL_PUBLICA = "https://inventario.ejemplo.test"
REMITENTE = "AssetControl <no-responder@ejemplo.test>"
TEMPORAL = "Temporal-Aviso-Sintetica-2026"
OTRA_TEMPORAL = "Otra-Temporal-Aviso-2026"
ELEGIDA = "Elegida-Por-La-Persona-2026"
CSRF = {CSRF_HEADER: CSRF_HEADER_VALUE}
ENLACE = re.compile(re.escape(URL_PUBLICA) + r"/restablecer#([A-Za-z0-9_-]{32,128})")


class Registro:
    """Transporte falso: guarda los mensajes que entrega el hilo de ``Correo``."""

    def __init__(self) -> None:
        self.mensajes = []
        self._lock = threading.Lock()

    def entregar(self, mensaje) -> None:
        with self._lock:
            self.mensajes.append(mensaje)


class Falla:
    def entregar(self, mensaje) -> None:
        raise OSError("el servidor rechazó el mensaje")


def _app(db: AccesoDb, carpeta) -> Flask:
    return create_app(
        Config(
            database_url=db.app_url.render_as_string(hide_password=False),
            secret_key=SECRET_KEY,
            environment="test",
            rate_limits=HIGH_LIMITS,
            plataforma=PlataformaConfig.desde_texto("true", ""),
            correo=(
                CorreoConfig(
                    modo="carpeta", remitente=REMITENTE, url_publica=URL_PUBLICA, carpeta=carpeta
                )
                if carpeta is not None
                else None
            ),
        )
    )


@pytest.fixture(scope="module")
def av_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("plat_usr_aviso")


@pytest.fixture(scope="module")
def av_app(av_db, tmp_path_factory) -> Iterator[Flask]:
    flask_app = _app(av_db, tmp_path_factory.mktemp("buzon"))
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def registro(av_app) -> Iterator[Registro]:
    correo = get_correo(av_app)
    original = correo.transporte
    correo.transporte = Registro()
    yield correo.transporte
    assert correo.esperar(5)
    correo.transporte = original


@pytest.fixture
def client(av_app):
    return av_app.test_client(use_cookies=False)


@pytest.fixture(scope="module")
def dev(av_db):
    return sembrar_dev(av_db, nuevo_dev("aviso-usuario"))


@pytest.fixture(scope="module")
def headers(av_app, dev) -> dict[str, str]:
    response = login(av_app.test_client(use_cookies=False), dev.email)
    assert response.status_code == 200
    return plat_bearer(response.get_json()["access_token"])


@pytest.fixture(autouse=True)
def fresh_rate_limits(av_db) -> Iterator[None]:
    ejecutar(av_db, "delete from limite_tasa")
    yield


@dataclass(frozen=True)
class Persona:
    usuario_id: uuid.UUID
    email: str


@dataclass(frozen=True)
class Empresa:
    tenant_id: uuid.UUID
    admin: Persona
    contador: Persona


def _empresa(db: AccesoDb, *, activa: bool = True) -> Empresa:
    def persona(rol: str) -> Persona:
        return Persona(uuid.uuid4(), f"{rol}.{uuid.uuid4().hex[:10]}@ejemplo.test")

    empresa = Empresa(uuid.uuid4(), persona("admin"), persona("contador"))
    with db.migrator.begin() as conn:
        conn.execute(
            text("insert into tenant (id, nombre) values (:t, :n)"),
            {"t": empresa.tenant_id, "n": f"Clínica Aviso {uuid.uuid4().hex[:6]}"},
        )
        for p, rol in ((empresa.admin, "admin"), (empresa.contador, "contador")):
            conn.execute(
                text(
                    "insert into usuario (id, email, nombre, password_hash) values (:u, :e, :n, :h)"
                ),
                {"u": p.usuario_id, "e": p.email, "n": "Persona Aviso", "h": HASHER.hash(PASSWORD)},
            )
            conn.execute(
                text("insert into membresia (tenant_id, usuario_id, rol) values (:t, :u, :r)"),
                {"t": empresa.tenant_id, "u": p.usuario_id, "r": rol},
            )
        if not activa:
            conn.execute(
                text("update tenant set activo = false, desactivado_en = now() where id = :t"),
                {"t": empresa.tenant_id},
            )
    return empresa


def _definir(client, headers, empresa: Empresa, persona: Persona, password=TEMPORAL, body=None):
    # ``buffered``: como un servidor WSGI real, se lee el cuerpo y se cierra la respuesta,
    # lo que ejecuta los ``call_on_close`` (ahí se programa el aviso).
    return client.post(
        f"/plataforma/empresas/{empresa.tenant_id}/usuarios/{persona.usuario_id}/contrasena",
        json=body
        if body is not None
        else {"password": password, "password_confirmacion": password},
        headers=headers,
        buffered=True,
    )


def _entregados(av_app, registro: Registro) -> list:
    assert get_correo(av_app).esperar(5)
    return list(registro.mensajes)


def _texto(mensaje) -> str:
    return mensaje.get_body(preferencelist=("plain",)).get_content()


def _token(mensaje) -> str | None:
    found = ENLACE.search(_texto(mensaje))
    return found.group(1) if found else None


def _restablecer(client, token: str, password: str = ELEGIDA):
    return client.post(
        "/auth/restablecer", json={"token": token, "password": password}, headers=CSRF
    )


def _tenant_login(client, email: str, password: str):
    return client.post("/auth/login", json={"email": email, "password": password})


def _usuario(db: AccesoDb, persona: Persona) -> dict:
    (row,) = filas(db, "select * from usuario where id = :u", {"u": persona.usuario_id})
    return row


def _contadores_recuperacion(db: AccesoDb) -> int:
    with db.migrator.connect() as conn:
        return conn.scalar(text("select count(*) from limite_tasa where ambito like 'recuperar%'"))


# --- A30: el aviso y su enlace ----------------------------------------------------------


def test_reset_sends_one_notice_whose_link_lets_the_person_choose(
    client, headers, av_app, av_db, registro
):
    empresa = _empresa(av_db)

    response = _definir(client, headers, empresa, empresa.admin)

    assert response.status_code == 204
    (mensaje,) = _entregados(av_app, registro)
    assert mensaje["To"] == empresa.admin.email
    assert mensaje["Subject"] == ASUNTO_AVISO
    assert [p.get_content_type() for p in mensaje.iter_parts()] == ["text/plain", "text/html"]
    token = _token(mensaje)
    assert token is not None
    assert _usuario(av_db, empresa.admin)["debe_cambiar_password"] is True

    assert _restablecer(client, token).status_code == 204

    assert _usuario(av_db, empresa.admin)["debe_cambiar_password"] is False
    assert _tenant_login(client, empresa.admin.email, TEMPORAL).status_code == 401
    entrada = _tenant_login(client, empresa.admin.email, ELEGIDA)
    assert entrada.status_code == 200
    assert entrada.get_json()["debe_cambiar_password"] is False


def test_temporary_password_still_works_when_the_link_is_not_used(
    client, headers, av_app, av_db, registro
):
    empresa = _empresa(av_db)

    assert _definir(client, headers, empresa, empresa.contador).status_code == 204
    _entregados(av_app, registro)

    entrada = _tenant_login(client, empresa.contador.email, TEMPORAL)
    assert entrada.status_code == 200
    assert entrada.get_json()["debe_cambiar_password"] is True


def test_second_reset_sends_another_notice_and_voids_the_first_link(
    client, headers, av_app, av_db, registro
):
    empresa = _empresa(av_db)

    assert _definir(client, headers, empresa, empresa.admin).status_code == 204
    assert _definir(client, headers, empresa, empresa.admin, OTRA_TEMPORAL).status_code == 204

    primero, segundo = _entregados(av_app, registro)
    rechazo = _restablecer(client, _token(primero))
    assert rechazo.status_code == 400
    assert rechazo.get_json()["error"]["code"] == "enlace_invalido"
    assert _restablecer(client, _token(segundo)).status_code == 204


def test_inactive_membership_gets_the_notice_without_a_link(
    client, headers, av_app, av_db, registro
):
    empresa = _empresa(av_db)
    ejecutar(
        av_db,
        "update membresia set activa = false where usuario_id = :u",
        {"u": empresa.contador.usuario_id},
    )

    assert _definir(client, headers, empresa, empresa.contador).status_code == 204

    (mensaje,) = _entregados(av_app, registro)
    assert mensaje["To"] == empresa.contador.email
    assert _token(mensaje) is None
    assert "pide la contraseña temporal a quien te la definió" in _texto(mensaje)


def test_user_with_two_active_memberships_gets_the_notice_without_a_link(
    client, headers, av_app, av_db, registro
):
    empresa = _empresa(av_db)
    otra = _empresa(av_db)
    ejecutar(
        av_db,
        "insert into membresia (tenant_id, usuario_id, rol) values (:t, :u, 'contador')",
        {"t": otra.tenant_id, "u": empresa.admin.usuario_id},
    )

    assert _definir(client, headers, empresa, empresa.admin).status_code == 204

    (mensaje,) = _entregados(av_app, registro)
    assert _token(mensaje) is None


@pytest.mark.parametrize(
    "body",
    [
        {"password": "corta", "password_confirmacion": "corta"},
        {"password": TEMPORAL, "password_confirmacion": OTRA_TEMPORAL},
        {"password": TEMPORAL},
    ],
)
def test_rejected_request_sends_nothing(client, headers, av_app, av_db, registro, body):
    empresa = _empresa(av_db)

    response = _definir(client, headers, empresa, empresa.admin, body=body)

    assert response.status_code in (400, 422)
    assert _entregados(av_app, registro) == []


def test_inactive_company_sends_nothing(client, headers, av_app, av_db, registro):
    empresa = _empresa(av_db, activa=False)

    response = _definir(client, headers, empresa, empresa.admin)

    assert response.status_code == 409
    assert _entregados(av_app, registro) == []


def test_without_mail_nothing_is_sent_and_the_reset_still_works(av_db, headers):
    flask_app = _app(av_db, None)
    try:
        client = flask_app.test_client(use_cookies=False)
        empresa = _empresa(av_db)

        response = _definir(client, headers, empresa, empresa.admin)

        assert response.status_code == 204
        assert _usuario(av_db, empresa.admin)["debe_cambiar_password"] is True
        assert (
            filas(
                av_db,
                "select 1 from recuperacion_contrasena where usuario_id = :u",
                {"u": empresa.admin.usuario_id},
            )
            == []
        )
    finally:
        dispose(flask_app)


def test_link_request_failure_keeps_the_204_and_sends_the_notice_without_link(
    client, headers, av_app, av_db, registro, monkeypatch, caplog
):
    empresa = _empresa(av_db)

    def falla(email, clave):
        raise RuntimeError(f"no se pudo con {email}")

    monkeypatch.setattr(aviso, "pedir_enlace_recuperacion", falla)

    response = _definir(client, headers, empresa, empresa.admin)

    assert response.status_code == 204
    assert _usuario(av_db, empresa.admin)["debe_cambiar_password"] is True
    (mensaje,) = _entregados(av_app, registro)
    assert _token(mensaje) is None
    assert "tipo=RuntimeError" in caplog.text
    assert empresa.admin.email not in caplog.text


def test_delivery_failure_keeps_the_204_and_the_temporary_password(
    client, headers, av_app, av_db, caplog
):
    empresa = _empresa(av_db)
    correo = get_correo(av_app)
    original = correo.transporte
    correo.transporte = Falla()
    try:
        response = _definir(client, headers, empresa, empresa.admin)
        assert correo.esperar(5)
    finally:
        correo.transporte = original

    assert response.status_code == 204
    assert _tenant_login(client, empresa.admin.email, TEMPORAL).status_code == 200
    assert "Correo de aviso no enviado" in caplog.text
    assert "tipo=OSError" in caplog.text


# --- A31: nada sensible en ninguna parte ------------------------------------------------


def test_nothing_sensitive_leaks_and_recovery_counters_do_not_move(
    client, headers, av_app, av_db, registro, caplog
):
    empresa = _empresa(av_db)
    antes = _contadores_recuperacion(av_db)

    response = _definir(client, headers, empresa, empresa.admin)

    assert response.status_code == 204
    assert response.get_data() == b""
    (mensaje,) = _entregados(av_app, registro)
    token = _token(mensaje)
    password_hash = _usuario(av_db, empresa.admin)["password_hash"]
    crudo = mensaje.as_string()
    for parte in mensaje.iter_parts():
        contenido = parte.get_content()
        assert TEMPORAL not in contenido
        assert password_hash not in contenido
        assert "Clínica Aviso" not in contenido
    assert TEMPORAL not in crudo
    auditoria = filas(
        av_db,
        "select * from plataforma_auditoria where tenant_id = :t",
        {"t": empresa.tenant_id},
    )
    assert [fila["accion"] for fila in auditoria] == ["usuario_contrasena_restablecida"]
    volcado = repr(auditoria)
    for prohibido in (TEMPORAL, password_hash, empresa.admin.email, token):
        assert prohibido not in volcado
        assert prohibido not in caplog.text
    assert "/restablecer#" not in caplog.text
    assert _contadores_recuperacion(av_db) == antes
