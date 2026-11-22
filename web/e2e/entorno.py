"""Entorno de las pruebas e2e (spec 010c, T3): lee ``../.env`` sin mostrar valores.

Las pruebas usan su propia base, ``assetcontrol_e2e``, en el mismo PostgreSQL local de
desarrollo (Docker): nunca la base de desarrollo. Las variables ya presentes en el
entorno mandan sobre las del archivo (así la CI las pasa directamente).
"""

import os
from pathlib import Path

from sqlalchemy.engine import make_url

RAIZ = Path(__file__).resolve().parents[2]
BACKEND = RAIZ / "backend"
ESTADO = Path(__file__).resolve().parent / ".estado"
BASE_E2E = "assetcontrol_e2e"
PUERTO_API = 5011


def cargar() -> dict[str, str]:
    """``../.env`` + ``os.environ`` (gana el entorno)."""
    valores: dict[str, str] = {}
    archivo = RAIZ / ".env"
    if archivo.exists():
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            clave, valor = linea.split("=", 1)
            valores[clave.strip()] = valor.strip().strip('"').strip("'")
    valores.update(os.environ)
    for requerida in ("DATABASE_URL", "MIGRATION_DATABASE_URL", "APP_DB_USER"):
        if not valores.get(requerida):
            raise SystemExit(f"e2e: falta {requerida} en .env (docs/10-entorno-local.md).")
    return valores


def a_base_e2e(url: str) -> str:
    """La misma URL apuntando a ``assetcontrol_e2e`` (como texto, con la contraseña)."""
    return make_url(url).set(database=BASE_E2E).render_as_string(hide_password=False)


def entorno_e2e() -> dict[str, str]:
    """Variables para la API y las migraciones de e2e: siempre desarrollo y base de e2e."""
    valores = cargar()
    return {
        **valores,
        "DATABASE_URL": a_base_e2e(valores["DATABASE_URL"]),
        "MIGRATION_DATABASE_URL": a_base_e2e(valores["MIGRATION_DATABASE_URL"]),
        "ENVIRONMENT": "development",
        "SECRET_KEY": valores.get("SECRET_KEY") or "e2e-clave-local-de-al-menos-32-bytes-xx",
        "TRUSTED_PROXY_HOPS": "0",
        # Spec 017, T9: la consola de plataforma encendida solo en e2e (plataforma.spec.ts).
        "PLATAFORMA_HABILITADA": "true",
        "PLATAFORMA_REDES_PERMITIDAS": "",
    }
