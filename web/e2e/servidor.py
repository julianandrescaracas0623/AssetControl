"""API de e2e (spec 010c, T3): prepara ``assetcontrol_e2e`` desde cero (``base.py``) y
sirve la app Flask contra esa base en el puerto 5011.

Playwright arranca sus servidores **antes** de cualquier ``globalSetup``: por eso la
base se prepara aquí, antes de servir, y Playwright espera a ``/health``.

Se ejecuta con el entorno de uv del backend: ``uv run --project ../backend python e2e/servidor.py``.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import base  # noqa: E402
from entorno import BACKEND, PUERTO_API, entorno_e2e  # noqa: E402

base.main()

os.environ.update(entorno_e2e())
sys.path.insert(0, str(BACKEND))

from app import create_app  # noqa: E402

if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=PUERTO_API, use_reloader=False, debug=False)
