"""Application factory de AssetControl.

No abre conexiones al importar ni al crear la app: el engine de base de datos
se crea en ``create_app`` (``init_db``) y la primera conexión se abre al usarlo.
"""

from flask import Flask

from app.config import Config, load_config
from app.db import init_db
from app.errors import register_error_handlers
from app.meta.routes import bp as meta_bp
from app.version import __version__

__all__ = ["__version__", "create_app"]


def create_app(config: Config | None = None) -> Flask:
    """Crea una instancia aislada de la aplicación.

    Si no se pasa ``config``, se lee del entorno y falla con
    ``MissingConfigError`` si falta una variable obligatoria.
    """
    if config is None:
        config = load_config()

    app = Flask(__name__)
    app.config.update(config.to_flask())
    init_db(app)
    register_error_handlers(app)
    app.register_blueprint(meta_bp)
    return app
