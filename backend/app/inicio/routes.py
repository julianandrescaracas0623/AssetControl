"""Rutas del Inicio (spec 010): solo lectura; el filtro por rol vive en el servidor (P13)."""

from flask import Blueprint, jsonify
from flask.typing import ResponseReturnValue

from app.auth.decorators import current_session, current_user, require_auth
from app.inicio import indicadores

bp = Blueprint("inicio", __name__, url_prefix="/inicio")


@bp.get("")
@require_auth
def ver_indicadores() -> ResponseReturnValue:
    return jsonify(indicadores.indicadores(current_session(), current_user().rol))
