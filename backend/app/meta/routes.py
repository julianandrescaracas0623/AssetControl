"""``GET /health`` (spec 001, R5).

Responde ``200`` si la base responde y ``503`` si no, siempre con
``{status, db, version}`` y sin detalles de la conexión. No requiere tenant ni
sesión: el ping va por ``ping_database()``, no por ``tenant_session``.
"""

from flask import Blueprint, jsonify
from flask.typing import ResponseReturnValue

from app.db import ping_database
from app.version import __version__

bp = Blueprint("meta", __name__)


@bp.get("/health")
def health() -> ResponseReturnValue:
    if ping_database():
        return jsonify(status="ok", db="ok", version=__version__), 200
    return jsonify(status="error", db="error", version=__version__), 503
