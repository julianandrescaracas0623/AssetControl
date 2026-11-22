"""``GET /ready`` (spec 002, T10; R16, Q12, A15).

Responde ``200 {"status": "ok"}`` si la base responde y ``503 {"status": "error"}``
si no, sin detalles (ni versión, ni base, ni el error). El resultado se guarda unos
segundos por proceso (``READY_CACHE_SECONDS``): una ráfaga anónima no se traduce en
una conexión a la base por petición. ``/health`` no cambia (test_health.py).
"""

import pytest

import app.meta.routes as routes_module
from app import create_app
from app.config import Config

DOWN_PASSWORD = "clave-que-no-debe-salir"
DOWN_DB = f"postgresql+psycopg://usuario:{DOWN_PASSWORD}@db.invalid:5432/assetcontrol"


def make_app(database_url: str):
    return create_app(
        Config(database_url=database_url, secret_key="clave-de-prueba", environment="test")
    )


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(routes_module, "_clock", fake)
    return fake


class Pings(list):
    """Resultados que devolverá el ping, en orden; ``calls`` registra cada llamada."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[bool] = []

    def __call__(self) -> bool:
        value = self.pop(0)
        self.calls.append(value)
        return value


@pytest.fixture
def pings(monkeypatch) -> Pings:
    fake = Pings()
    monkeypatch.setattr(routes_module, "ping_database", fake)
    return fake


def test_ready_returns_200_without_details_when_the_database_responds(app_database_url):
    flask_app = make_app(app_database_url.render_as_string(hide_password=False))
    response = flask_app.test_client().get("/ready")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}
    assert response.headers["Cache-Control"] == "no-store"


def test_ready_returns_503_without_details_when_the_database_is_down():
    response = make_app(DOWN_DB).test_client().get("/ready")

    assert response.status_code == 503
    assert response.get_json() == {"status": "error"}
    raw = response.get_data(as_text=True)
    assert DOWN_PASSWORD not in raw
    assert "db.invalid" not in raw


def test_ready_is_cached_for_a_few_seconds(clock, pings):
    flask_app = make_app(DOWN_DB)
    client = flask_app.test_client()
    pings += [True, False]

    assert client.get("/ready").status_code == 200
    clock.now += routes_module.READY_CACHE_SECONDS - 0.1
    assert client.get("/ready").status_code == 200
    assert pings.calls == [True]

    clock.now += 0.2
    assert client.get("/ready").status_code == 503
    assert pings.calls == [True, False]


def test_a_failure_is_cached_too(clock, pings):
    client = make_app(DOWN_DB).test_client()
    pings += [False, True]

    assert client.get("/ready").status_code == 503
    assert client.get("/ready").status_code == 503
    assert pings.calls == [False]

    clock.now += routes_module.READY_CACHE_SECONDS + 0.1
    assert client.get("/ready").status_code == 200


def test_the_cache_is_per_app(clock, pings):
    pings += [True, False]
    assert make_app(DOWN_DB).test_client().get("/ready").status_code == 200
    assert make_app(DOWN_DB).test_client().get("/ready").status_code == 503


def test_cache_window_is_a_few_seconds():
    assert 1 <= routes_module.READY_CACHE_SECONDS <= 10


def test_ready_only_answers_get():
    response = make_app(DOWN_DB).test_client().post("/ready")
    assert response.status_code == 405
