"""Versión de la API; debe coincidir con ``project.version`` de ``pyproject.toml``.

``tests/test_health.py`` falla si se desalinean. No se lee de los metadatos del
paquete porque uv no instala este proyecto (no tiene ``build-system``).
"""

__version__ = "0.1.0"
