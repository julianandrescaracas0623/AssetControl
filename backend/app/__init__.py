"""Application factory de AssetControl.

No abre conexiones al importar ni al crear la app: el engine de base de datos
se crea en ``create_app`` (``init_db``) y la primera conexión se abre al usarlo.
"""

from flask import Flask

from app.auth.credentials import init_credentials
from app.auth.http import register_auth_http_policy
from app.auth.routes import bp as auth_bp
from app.cli import register_cli
from app.config import CONFIG_EXTENSION_KEY, Config, load_config
from app.db import init_db
from app.errors import register_error_handlers
from app.invitaciones.routes import bp as invitaciones_bp
from app.meta.routes import bp as meta_bp
from app.version import __version__

__all__ = ["__version__", "create_app"]


def create_app(config: Config | None = None) -> Flask:
    """Crea una instancia aislada de la aplicación.

    Si no se pasa ``config``, se lee del entorno y falla con
    ``MissingConfigError`` si falta una variable obligatoria o con
    ``WeakSecretKeyError`` si ``SECRET_KEY`` es corta fuera de pruebas,
    ``InvalidEnvironmentError`` fuera de la lista cerrada y
    ``UnsafeTestEnvironmentError`` con ``ENVIRONMENT=test`` fuera de pytest.
    Calcula aquí el hash simulado de contraseñas (una vez por app).
    """
    if config is None:
        config = load_config()

    # Sin carpeta estática: la API no sirve archivos y la ruta ``static`` quedaría fuera
    # del catálogo de roles (H7 de T8).
    app = Flask(__name__, static_folder=None)
    app.config.update(config.to_flask())
    app.extensions[CONFIG_EXTENSION_KEY] = config
    if config.is_test:
        app.logger.warning(
            "ENVIRONMENT=test: SECRET_KEY corta admitida y Argon2 de bajo costo; solo para pruebas."
        )
    init_db(app)
    init_credentials(app)
    register_error_handlers(app)
    register_auth_http_policy(app)
    app.register_blueprint(meta_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(invitaciones_bp)
    register_cli(app)
    return app
