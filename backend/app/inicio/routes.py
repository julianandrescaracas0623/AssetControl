"""Rutas del Inicio (spec 010): solo lectura; el filtro por rol vive en el servidor (P13)."""

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from app.activos import historial
from app.activos.service import ErrorActivo
from app.auth.decorators import current_session, current_user, require_auth
from app.errors import error_response
from app.inicio import indicadores

ACTIVIDAD_POR_PAGINA = 20

bp = Blueprint("inicio", __name__, url_prefix="/inicio")


@bp.get("")
@require_auth
def ver_indicadores() -> ResponseReturnValue:
    return jsonify(indicadores.indicadores(current_session(), current_user().rol))


@bp.get("/actividad")
@require_auth
def ver_actividad() -> ResponseReturnValue:
    """Últimos eventos del tenant (CU-DSH-02); al contador, sin precios (P13)."""
    try:
        pagina = historial.leer_tenant(
            current_session(),
            antes_de=request.args.get("antes_de"),
            con_precio=current_user().rol == "admin",
            por_pagina=ACTIVIDAD_POR_PAGINA,
        )
    except ErrorActivo as exc:
        return error_response(exc.status, exc.code, exc.message)
    return jsonify(eventos=pagina.eventos, siguiente=pagina.siguiente)
