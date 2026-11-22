"""Registro de módulos de la consola de plataforma (spec 017, T2; R12–R13; plan.md §2.1).

``MODULOS`` es el registro único del servidor: cada entrada es un ``Modulo`` con su id,
título, orden y blueprint. Añadir un módulo futuro es añadir aquí su entrada (y su carpeta
con el blueprint); el shell no cambia. ``register_plataforma`` registra el blueprint de
cada módulo y ``GET /plataforma/modulos`` devuelve los habilitados ordenados. Las rutas de
un módulo deben colgar de ``/plataforma`` y protegerse con ``require_desarrollador``
(lo exige el catálogo de ``test_plataforma_aislamiento.py``).

``empresas`` desde T3b, ``usuarios`` desde T5 y ``actividad`` desde T6.
"""

from dataclasses import dataclass

from flask import Blueprint, jsonify
from flask.typing import ResponseReturnValue

from app.plataforma.decoradores import require_desarrollador
from app.plataforma.modulos.actividad.routes import bp as actividad_bp
from app.plataforma.modulos.empresas.routes import bp as empresas_bp
from app.plataforma.modulos.usuarios.routes import bp as usuarios_bp


@dataclass(frozen=True)
class Modulo:
    id: str
    titulo: str
    orden: int
    blueprint: Blueprint

    def to_json(self) -> dict[str, object]:
        return {"id": self.id, "titulo": self.titulo, "orden": self.orden}


MODULOS: tuple[Modulo, ...] = (
    Modulo(id="empresas", titulo="Empresas", orden=10, blueprint=empresas_bp),
    Modulo(id="usuarios", titulo="Usuarios", orden=20, blueprint=usuarios_bp),
    Modulo(id="actividad", titulo="Actividad", orden=30, blueprint=actividad_bp),
)

bp = Blueprint("plataforma_modulos", __name__, url_prefix="/plataforma")


def habilitados() -> list[Modulo]:
    # Se lee el registro en cada llamada: el módulo de prueba de T2 lo reemplaza.
    return sorted(MODULOS, key=lambda modulo: (modulo.orden, modulo.id))


@bp.get("/modulos")
@require_desarrollador
def listar() -> ResponseReturnValue:
    return jsonify(modulos=[modulo.to_json() for modulo in habilitados()])
