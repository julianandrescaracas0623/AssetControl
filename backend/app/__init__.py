"""Application factory de AssetControl.

No abre conexiones al importar ni al crear la app: el engine de base de datos
se crea en ``create_app`` a partir de la tarea T3.
"""

from flask import Flask

from app.config import Config, load_config


def create_app(config: Config | None = None) -> Flask:
    """Crea una instancia aislada de la aplicación.

    Si no se pasa ``config``, se lee del entorno y falla con
    ``MissingConfigError`` si falta una variable obligatoria.
    """
    if config is None:
        config = load_config()

    app = Flask(__name__)
    app.config.update(config.to_flask())
    return app
