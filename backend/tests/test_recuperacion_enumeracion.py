"""Enumeración por tiempo y camino HTTP completo de recuperar contraseña (spec 014, T8; A2, A13;
R13; M1 de T2, I1 de T4).

Sobre un servidor WSGI real (``werkzeug.serving.make_server`` en 127.0.0.1) y un cliente
``http.client``: lo que ve quien llama es la respuesta completa (cabeceras y cuerpo con su
``Content-Length``), no la vuelta de una función.

- **I1 (T4):** el correo se programa al cerrar la respuesta (``call_on_close``): con un
  ``enviar_recuperacion`` que se queda bloqueado, el cliente igual recibe el ``202``.
- **A2:** muestras intercaladas (N = 30 por rama tras un calentamiento) de cuenta elegible,
  cuenta no elegible (dos membresías activas), correo inexistente y, en una segunda app con
  el correo desactivado, cuenta elegible y correo inexistente. El transporte del correo
  tarda ``RETARDO_SMTP`` (SMTP lento): si entrara en la petición, la rama elegible tardaría
  eso de más. Se comparan **medianas** con un margen generoso (``indistinguibles``). La rama
  «desactivado» no se compara con las otras: no toca la base (requisito 4 de T3) y es la
  misma para todos los correos, así que no es un oráculo; se comparan sus dos casos entre sí.
- Por HTTP real: ``Retry-After`` del ``429`` de ``/auth/restablecer`` y el ``204`` que
  revoca las sesiones (``/auth/refresh`` → ``401``).

La prueba de tiempos depende del reloj y de la carga de la máquina: se puede omitir con
``ASSETCONTROL_OMITIR_PRUEBAS_DE_TIEMPO=1`` (p. ej. en un CI compartido muy ruidoso). Por
defecto corre. Datos sintéticos (``@ejemplo.test``).
"""

import http.client
import json
import os
import random
import statistics
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace

import pytest
from acceso_db import PASSWORD, TENANT_A, TENANT_B, dispose, temporary_acceso_db
from flask import Flask
from sqlalchemy import text
from test_recuperacion_endpoints import (
    HIGH,
    NUEVA,
    RECOVERY_BODY,
    RECUPERAR,
    RESTABLECER,
    Envios,
    build_app,
    crear_cuenta,
    enlaces_de,
)
from werkzeug.serving import WSGIRequestHandler, make_server

from app.auth.http import CSRF_HEADER, CSRF_HEADER_VALUE
from app.correo import get_correo

RETARDO_SMTP = 0.3
MUESTRAS = 30
CALENTAMIENTO = 3
# Margen de A2: dos medianas son indistinguibles si difieren menos de 25 ms o su razón es
# menor que 1,5. Un SMTP en la petición sumaría ``RETARDO_SMTP`` (300 ms) a una rama.
MARGEN_ABSOLUTO = 0.025
MARGEN_RELATIVO = 1.5
OMITIR_TIEMPOS = os.environ.get("ASSETCONTROL_OMITIR_PRUEBAS_DE_TIEMPO", "").strip() == "1"


class _Lento:
    """Transporte falso que tarda como un SMTP lento."""

    def __init__(self) -> None:
        self.mensajes = []
        self._lock = threading.Lock()

    def entregar(self, mensaje) -> None:
        time.sleep(RETARDO_SMTP)
        with self._lock:
            self.mensajes.append(mensaje)


class _Silencioso(WSGIRequestHandler):
    def log_request(self, *args, **kwargs) -> None:
        pass


@contextmanager
def servidor(flask_app: Flask) -> Iterator[int]:
    """Servidor WSGI real en un hilo; devuelve el puerto."""
    srv = make_server("127.0.0.1", 0, flask_app, threaded=True, request_handler=_Silencioso)
    hilo = threading.Thread(target=srv.serve_forever, daemon=True)
    hilo.start()
    try:
        yield srv.server_port
    finally:
        srv.shutdown()
        hilo.join(10)
        srv.server_close()


def post(puerto: int, ruta: str, cuerpo: dict, headers=None, timeout: float = 10):
    """``POST`` real; devuelve ``(estado, cabeceras, cuerpo, segundos)`` hasta leer el cuerpo."""
    conexion = http.client.HTTPConnection("127.0.0.1", puerto, timeout=timeout)
    datos = json.dumps(cuerpo).encode()
    cabeceras = {
        "Content-Type": "application/json",
        CSRF_HEADER: CSRF_HEADER_VALUE,
        **(headers or {}),
    }
    try:
        inicio = time.perf_counter()
        conexion.request("POST", ruta, body=datos, headers=cabeceras)
        respuesta = conexion.getresponse()
        contenido = respuesta.read()
        segundos = time.perf_counter() - inicio
        return respuesta.status, dict(respuesta.getheaders()), contenido, segundos
    finally:
        conexion.close()


def indistinguibles(a: float, b: float) -> bool:
    menor, mayor = sorted((a, b))
    return mayor - menor <= MARGEN_ABSOLUTO or mayor <= menor * MARGEN_RELATIVO


@pytest.fixture(scope="module")
def rec_db(database_residue_guard):
    yield from temporary_acceso_db("rec_tiempo")


@pytest.fixture(autouse=True)
def limpio(rec_db) -> None:
    with rec_db.migrator.begin() as conn:
        conn.execute(text("delete from limite_tasa"))


@pytest.fixture
def lenta(rec_db, tmp_path) -> Iterator[Flask]:
    flask_app = build_app(rec_db, tmp_path)
    get_correo(flask_app).transporte = _Lento()
    yield flask_app
    get_correo(flask_app).esperar(15)
    dispose(flask_app)


def test_mail_is_scheduled_after_the_response_reaches_the_client(lenta, rec_db, monkeypatch):
    """I1 de T4: un envío que no vuelve no retiene la respuesta (``call_on_close``)."""
    cuenta = crear_cuenta(rec_db)
    correo = get_correo(lenta)
    llamado = threading.Event()
    liberar = threading.Event()
    confirmado: list[bool] = []

    def bloqueado(destino, token, request_id=None):
        confirmado.append(bool(enlaces_de(rec_db, cuenta)))
        llamado.set()
        liberar.wait(10)

    monkeypatch.setattr(correo, "enviar_recuperacion", bloqueado)
    with servidor(lenta) as puerto:
        try:
            estado, _, contenido, _ = post(puerto, RECUPERAR, {"email": cuenta.email}, timeout=5)
            # La respuesta llegó entera mientras el envío sigue bloqueado.
            assert not liberar.is_set()
            assert estado == 202
            assert json.loads(contenido) == RECOVERY_BODY
            assert llamado.wait(5), "el correo no se programó tras la respuesta"
            assert confirmado == [True], "el correo se programó antes del COMMIT"
        finally:
            liberar.set()


@pytest.mark.skipif(
    OMITIR_TIEMPOS, reason="ASSETCONTROL_OMITIR_PRUEBAS_DE_TIEMPO=1 (reloj en máquina ruidosa)"
)
def test_response_time_does_not_reveal_whether_the_account_exists(lenta, rec_db, tmp_path):
    elegible = crear_cuenta(rec_db)
    no_elegible = crear_cuenta(
        rec_db, membresias=((TENANT_A, "contador", True), (TENANT_B, "contador", True))
    )
    apagada = build_app(rec_db, None)
    ramas = {
        "elegible": ("activa", elegible.email),
        "no_elegible": ("activa", no_elegible.email),
        "inexistente": ("activa", "nadie.registrado.tiempo@ejemplo.test"),
        "desactivado_elegible": ("apagada", elegible.email),
        "desactivado_inexistente": ("apagada", "nadie.registrado.tiempo@ejemplo.test"),
    }
    tiempos: dict[str, list[float]] = {rama: [] for rama in ramas}
    azar = random.Random(14)  # noqa: S311 - orden de las muestras, no criptografía
    try:
        with servidor(lenta) as puerto_activa, servidor(apagada) as puerto_apagada:
            puertos = {"activa": puerto_activa, "apagada": puerto_apagada}
            for ronda in range(CALENTAMIENTO + MUESTRAS):
                orden = list(ramas)
                azar.shuffle(orden)
                for rama in orden:
                    app_de, email = ramas[rama]
                    estado, _, contenido, segundos = post(
                        puertos[app_de], RECUPERAR, {"email": email}
                    )
                    assert estado == 202, rama
                    assert json.loads(contenido) == RECOVERY_BODY, rama
                    if ronda >= CALENTAMIENTO:
                        tiempos[rama].append(segundos)
    finally:
        dispose(apagada)

    medianas = {rama: statistics.median(valores) for rama, valores in tiempos.items()}
    detalle = ", ".join(f"{rama}={1000 * m:.1f} ms" for rama, m in medianas.items())
    assert all(len(valores) == MUESTRAS for valores in tiempos.values())
    # El SMTP lento nunca entra en la petición.
    assert medianas["elegible"] < RETARDO_SMTP, detalle
    for rama in ("no_elegible", "inexistente"):
        assert indistinguibles(medianas["elegible"], medianas[rama]), detalle
    assert indistinguibles(medianas["desactivado_elegible"], medianas["desactivado_inexistente"]), (
        detalle
    )
    # Solo la rama elegible creó enlaces; la desactivada no tocó la base.
    assert len(enlaces_de(rec_db, elegible)) == CALENTAMIENTO + MUESTRAS
    assert enlaces_de(rec_db, no_elegible) == []


def test_reset_over_real_http_revokes_sessions_and_429_carries_retry_after(rec_db, tmp_path):
    flask_app = build_app(rec_db, tmp_path, rate_limits=replace(HIGH, reset_ip=2))
    correo = get_correo(flask_app)
    envios = Envios(rec_db, correo.enviar_recuperacion)
    correo.enviar_recuperacion = envios
    cuenta = crear_cuenta(rec_db)
    try:
        with servidor(flask_app) as puerto:
            estado, cabeceras, _, _ = post(
                puerto, "/auth/login", {"email": cuenta.email, "password": PASSWORD}
            )
            assert estado == 200
            cookie = cabeceras["Set-Cookie"].split(";", 1)[0]
            assert post(puerto, RECUPERAR, {"email": cuenta.email})[0] == 202
            # El envío se programa al cerrar la respuesta, en el hilo del servidor: puede
            # llegar un instante después de que el cliente leyó el 202.
            limite = time.monotonic() + 5
            while not envios.llamadas and time.monotonic() < limite:
                time.sleep(0.01)
            [(_, token, _)] = envios.llamadas

            estado, cabeceras, contenido, _ = post(
                puerto, RESTABLECER, {"token": token, "password": NUEVA}
            )
            assert (estado, contenido) == (204, b"")
            assert "Set-Cookie" not in cabeceras
            assert post(puerto, "/auth/refresh", {}, headers={"Cookie": cookie})[0] == 401

            # Segundo intento cabe (2); el tercero supera el límite por IP.
            assert post(puerto, RESTABLECER, {"token": token, "password": NUEVA})[0] == 400
            estado, cabeceras, contenido, _ = post(
                puerto, RESTABLECER, {"token": token, "password": NUEVA}
            )
            assert estado == 429
            assert cabeceras["Retry-After"] == "900"
            assert json.loads(contenido)["error"]["code"] == "demasiadas_solicitudes"
    finally:
        correo.esperar(5)
        dispose(flask_app)
