"""Ruta ``GET /plataforma/actividad`` (spec 017, T6; R32; plan.md §4).

Solo lectura: la auditoría de la más reciente a la más antigua, paginada por cursor, con
filtros opcionales por empresa, acción y fechas (``service``). Con ``require_desarrollador``
(token de plataforma y ``desarrollador.activo`` en cada petición); ``Authorization:
Bearer``, sin cookies ni CSRF. ``no-store`` y ``no-referrer`` los pone ``app.plataforma``.
No cuenta en ``plat_accion`` (es una lectura, como las listas de Empresas y Usuarios) ni
escribe auditoría. Ningún otro método: ``405``.
"""

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from app.errors import error_response
from app.plataforma.decoradores import current_plataforma_session, require_desarrollador
from app.plataforma.modulos.actividad import service

bp = Blueprint("plataforma_actividad", __name__, url_prefix="/plataforma")


@bp.get("/actividad")
@require_desarrollador
def listar() -> ResponseReturnValue:
    try:
        filtro = service.consulta(request.args)
        pagina = service.listar(current_plataforma_session(), filtro)
    except service.ErrorActividad as exc:
        return error_response(exc.status, exc.code, exc.message)
    return jsonify(pagina)
