"""Logs y salida estándar de recuperar y restablecer contraseña (spec 014, T8; A12, A13).

De punta a punta por HTTP: solicitud elegible e inexistente, fallo del SMTP en el hilo de
envío (la excepción lleva a propósito el correo, el host y el token en su mensaje),
restablecimiento correcto, rechazado y por política. Ni ``caplog`` ni ``capsys`` (``stdout``
y ``stderr``) contienen el correo, el token, la clave, su hash, el enlace, la contraseña,
su hash Argon2 ni el host SMTP. Con el SMTP caído la respuesta es el mismo ``202``.
Datos sintéticos (``@ejemplo.test``).
"""

import json
import logging
import threading
from collections.abc import Iterator

import pytest
from acceso_db import dispose, temporary_acceso_db
from flask import Flask
from sqlalchemy import text
from test_recuperacion_endpoints import (
    NUEVA,
    Envios,
    build_app,
    comparable,
    crear_cuenta,
    log_text,
    password_hash_de,
    recuperar,
    restablecer,
)

from app.auth.credentials import token_key, token_storage_hash
from app.correo import get_correo

HOST_SMTP = "smtp.servidor-de-prueba.invalid"


class _SmtpCaido:
    """Transporte que falla como un SMTP real, con datos sensibles en el mensaje."""

    def __init__(self) -> None:
        self.intentos = 0
        self._lock = threading.Lock()

    def entregar(self, mensaje) -> None:
        with self._lock:
            self.intentos += 1
        raise ConnectionRefusedError(
            f"{HOST_SMTP} rechazó {mensaje['To']}: {mensaje.get_content()}"
        )


@pytest.fixture(scope="module")
def rec_db(database_residue_guard):
    yield from temporary_acceso_db("rec_logs")


@pytest.fixture
def caida(rec_db, tmp_path) -> Iterator[Flask]:
    with rec_db.migrator.begin() as conn:
        conn.execute(text("delete from limite_tasa"))
    flask_app = build_app(rec_db, tmp_path)
    get_correo(flask_app).transporte = _SmtpCaido()
    yield flask_app
    get_correo(flask_app).esperar(5)
    dispose(flask_app)


def test_no_secrets_in_logs_or_stdio_across_the_whole_flow(caida, rec_db, caplog, capsys):
    cuenta = crear_cuenta(rec_db)
    correo = get_correo(caida)
    envios = Envios(rec_db, correo.enviar_recuperacion)
    correo.enviar_recuperacion = envios
    client = caida.test_client(use_cookies=False)

    with caplog.at_level(logging.DEBUG):
        respuestas = [recuperar(client, cuenta.email)]
        assert correo.esperar(5)
        [(_, token, _)] = envios.llamadas
        respuestas += [
            recuperar(client, "nadie.registrado.logs@ejemplo.test"),
            restablecer(client, token, password="corta"),
            restablecer(client, token),
            restablecer(client, token),
            restablecer(client, "D" * 43),
        ]
    salida = capsys.readouterr()

    # A13: el SMTP caído no cambia la respuesta; el fallo se registra con tipo y request_id.
    assert correo.transporte.intentos == 1
    assert comparable(respuestas[0]) == comparable(respuestas[1])
    assert [r.status_code for r in respuestas[2:]] == [400, 204, 400, 400]
    fallos = [r for r in caplog.records if "no enviado" in r.getMessage()]
    assert len(fallos) == 1
    assert "tipo=ConnectionRefusedError" in fallos[0].getMessage()
    assert respuestas[0].headers["X-Request-ID"] in fallos[0].getMessage()
    assert fallos[0].exc_info is None

    nuevo_hash = password_hash_de(rec_db, cuenta)
    texto = "\n".join(
        [
            log_text(caplog),
            salida.out,
            salida.err,
            *(r.get_data(as_text=True) + json.dumps(dict(r.headers)) for r in respuestas),
        ]
    )
    for secreto in (
        cuenta.email,
        cuenta.email.split("@")[0],
        "nadie.registrado.logs",
        token,
        token_key(token),
        token_storage_hash(token).hex(),
        "/restablecer#",
        NUEVA,
        nuevo_hash,
        "$argon2id$",
        HOST_SMTP,
        "D" * 43,
    ):
        assert secreto not in texto, secreto
