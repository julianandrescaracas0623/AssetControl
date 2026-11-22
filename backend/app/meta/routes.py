"""``GET /health`` (spec 001, R5) y ``GET /ready`` (spec 002, T10; R16, Q12, A15).

``/health`` responde ``200`` si la base responde y ``503`` si no, siempre con
``{status, db, version}`` y sin detalles de la conexión. No requiere tenant ni
sesión: el ping va por ``ping_database()``, no por ``tenant_session``.

``/ready`` responde ``200 {"status": "ok"}`` o ``503 {"status": "error"}``, sin
versión ni detalles. El resultado del ping (también el fallo) se guarda
``READY_CACHE_SECONDS`` por app y proceso: una ráfaga anónima no abre una conexión a
la base por petición. ``Cache-Control: no-store`` para que ningún intermediario lo
guarde más tiempo.
"""

import threading
import time

from flask import Blueprint, current_app, jsonify
from flask.typing import ResponseReturnValue

from app.db import ping_database
from app.version import __version__

bp = Blueprint("meta", __name__)

READY_CACHE_SECONDS = 5.0
_READY_CACHE_KEY = "assetcontrol.ready"
# Reloj monotónico (se sustituye en las pruebas).
_clock = time.monotonic


@bp.get("/health")
def health() -> ResponseReturnValue:
    if ping_database():
        return jsonify(status="ok", db="ok", version=__version__), 200
    return jsonify(status="error", db="error", version=__version__), 503


class _ReadyCache:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.checked_at: float | None = None
        self.ready = False


def _is_ready() -> bool:
    cache = current_app.extensions.setdefault(_READY_CACHE_KEY, _ReadyCache())
    with cache.lock:
        now = _clock()
        if cache.checked_at is None or now - cache.checked_at >= READY_CACHE_SECONDS:
            cache.ready = ping_database()
            cache.checked_at = now
        return cache.ready


@bp.get("/ready")
def ready() -> ResponseReturnValue:
    ok = _is_ready()
    response = jsonify(status="ok" if ok else "error")
    response.status_code = 200 if ok else 503
    response.headers["Cache-Control"] = "no-store"
    return response
