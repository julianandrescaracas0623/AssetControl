"""``worker_exit`` de gunicorn espera los correos en curso (spec 018, T2; R4, A2).

Al apagarse un proceso, gunicorn llama a ``worker_exit``: debe esperar los envíos de
``Correo`` con un plazo menor que ``graceful_timeout`` y no fallar nunca (sin correo, sin
app cargada en el proceso o si ``esperar`` lanza). El registro no lleva datos personales.
"""

import importlib.util
import logging
import sys
import threading
import time
import types
from pathlib import Path
from types import ModuleType

import pytest

import app.wsgi as wsgi
from app.correo import EXTENSION_KEY, Correo

RUTA_CONF = Path(__file__).resolve().parents[1] / "gunicorn.conf.py"
MODULO_WSGI = "app.wsgi"
DESTINO = "persona@ejemplo.test"
TOKEN = "tokenSecretoDePrueba_0123456789abcdef"


def cargar_conf() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gunicorn_conf_prueba", RUTA_CONF)
    assert spec is not None and spec.loader is not None
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class CorreoDoble:
    """Doble de ``Correo``: anota el plazo con que se llamó a ``esperar``."""

    def __init__(self, *, resultado: bool = True, error: Exception | None = None) -> None:
        self.resultado = resultado
        self.error = error
        self.llamadas: list[float | None] = []

    def esperar(self, timeout: float | None = None) -> bool:
        self.llamadas.append(timeout)
        if self.error is not None:
            raise self.error
        return self.resultado


def modulo_wsgi(correo: object) -> ModuleType:
    falso = types.ModuleType(MODULO_WSGI)
    falso.correo_del_proceso = lambda: correo  # type: ignore[attr-defined]
    return falso


@pytest.fixture
def conf() -> ModuleType:
    return cargar_conf()


def test_cargar_la_configuracion_conserva_los_valores(conf: ModuleType) -> None:
    assert conf.wsgi_app == "app.wsgi:application"
    assert conf.workers == 2
    assert conf.threads == 4
    assert conf.worker_class == "gthread"
    assert conf.graceful_timeout == 20
    assert conf.preload_app is False
    assert conf.access_log_format == ('%(h)s "%(m)s %(U)s" %(s)s %(B)s %(M)sms %({x-request-id}o)s')
    assert callable(conf.worker_exit)


def test_el_plazo_es_menor_que_graceful_timeout(conf: ModuleType) -> None:
    assert 0 < conf.PLAZO_CORREO_AL_APAGAR < conf.graceful_timeout


def test_worker_exit_espera_el_correo_con_el_plazo(conf, monkeypatch) -> None:
    correo = CorreoDoble()
    monkeypatch.setitem(sys.modules, MODULO_WSGI, modulo_wsgi(correo))
    conf.worker_exit(None, None)
    assert correo.llamadas == [conf.PLAZO_CORREO_AL_APAGAR]


def test_sin_correo_configurado_no_falla(conf, monkeypatch, caplog) -> None:
    monkeypatch.setitem(sys.modules, MODULO_WSGI, modulo_wsgi(None))
    with caplog.at_level(logging.DEBUG):
        conf.worker_exit(None, None)
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_sin_app_cargada_en_el_proceso_no_falla(conf, monkeypatch) -> None:
    # El maestro (preload_app = False) también llama a worker_exit y no cargó la app.
    monkeypatch.delitem(sys.modules, MODULO_WSGI, raising=False)
    conf.worker_exit(None, None)
    assert MODULO_WSGI not in sys.modules  # no la importa por su cuenta


def test_correo_real_desactivado_no_falla(conf, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, MODULO_WSGI, modulo_wsgi(Correo(None)))
    conf.worker_exit(None, None)


def test_si_esperar_lanza_no_se_propaga_ni_registra_el_mensaje(conf, monkeypatch, caplog) -> None:
    correo = CorreoDoble(error=RuntimeError(f"fallo con {DESTINO} y {TOKEN}"))
    monkeypatch.setitem(sys.modules, MODULO_WSGI, modulo_wsgi(correo))
    with caplog.at_level(logging.INFO):
        conf.worker_exit(None, None)
    avisos = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert avisos
    texto = caplog.text
    assert DESTINO not in texto and TOKEN not in texto
    assert all(r.exc_info is None for r in caplog.records)


def test_si_vence_el_plazo_registra_un_aviso_sin_datos(conf, monkeypatch, caplog) -> None:
    correo = CorreoDoble(resultado=False)
    monkeypatch.setitem(sys.modules, MODULO_WSGI, modulo_wsgi(correo))
    with caplog.at_level(logging.INFO):
        conf.worker_exit(None, None)
    avisos = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(avisos) == 1
    assert "correo" in avisos[0].getMessage().lower()
    assert DESTINO not in caplog.text and TOKEN not in caplog.text


def test_si_terminan_a_tiempo_no_hay_aviso(conf, monkeypatch, caplog) -> None:
    monkeypatch.setitem(sys.modules, MODULO_WSGI, modulo_wsgi(CorreoDoble()))
    with caplog.at_level(logging.INFO):
        conf.worker_exit(None, None)
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_si_correo_del_proceso_lanza_no_se_propaga(conf, monkeypatch) -> None:
    falso = types.ModuleType(MODULO_WSGI)

    def roto() -> None:
        raise RuntimeError("roto")

    falso.correo_del_proceso = roto  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, MODULO_WSGI, falso)
    conf.worker_exit(None, None)


def test_modulo_wsgi_sin_la_funcion_no_falla(conf, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, MODULO_WSGI, types.ModuleType(MODULO_WSGI))
    conf.worker_exit(None, None)


# --- app.wsgi.correo_del_proceso: el Correo de la app creada en ESTE proceso.


def test_correo_del_proceso_sin_app_creada_es_none(monkeypatch) -> None:
    monkeypatch.setattr(wsgi, "_api", None)
    assert wsgi.correo_del_proceso() is None


def test_correo_del_proceso_devuelve_el_de_la_app(monkeypatch) -> None:
    correo = Correo(None)
    api = types.SimpleNamespace(extensions={EXTENSION_KEY: correo})
    monkeypatch.setattr(wsgi, "_api", api)
    assert wsgi.correo_del_proceso() is correo


def test_correo_del_proceso_sin_extension_es_none(monkeypatch) -> None:
    monkeypatch.setattr(wsgi, "_api", types.SimpleNamespace(extensions={}))
    assert wsgi.correo_del_proceso() is None


def test_con_correo_real_bloqueado_no_excede_el_plazo(conf, monkeypatch, caplog) -> None:
    # A2: un envío colgado no retiene el apagado más que el plazo (aquí reducido).
    liberar = threading.Event()

    class TransporteColgado:
        def entregar(self, mensaje: object) -> None:
            liberar.wait(5)

    config = types.SimpleNamespace(
        modo="smtp", remitente="no-responder@ejemplo.test", url_publica="https://ejemplo.test"
    )
    correo = Correo(config, transporte=TransporteColgado())  # type: ignore[arg-type]
    correo.enviar_recuperacion(DESTINO, TOKEN, request_id="r-1")
    monkeypatch.setattr(conf, "PLAZO_CORREO_AL_APAGAR", 0.2)
    monkeypatch.setitem(sys.modules, MODULO_WSGI, modulo_wsgi(correo))
    try:
        inicio = time.monotonic()
        with caplog.at_level(logging.INFO):
            conf.worker_exit(None, None)
        transcurrido = time.monotonic() - inicio
        # Holgura por la resolución del reloj en Windows; el límite superior se conserva.
        assert 0.15 <= transcurrido < 2
    finally:
        liberar.set()
        assert correo.esperar(5)
    avisos = [r for r in caplog.records if r.name == "gunicorn.error"]
    assert len(avisos) == 1 and "venció el plazo" in avisos[0].getMessage()
    assert DESTINO not in caplog.text and TOKEN not in caplog.text
