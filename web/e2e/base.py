"""Prepara la base de e2e desde cero (spec 010c, T3).

1. Borra y crea ``assetcontrol_e2e`` con el rol migrador de ``.env``.
2. Migra con Alembic hasta la cabeza.
3. Crea el tenant «Clínica E2E» y guarda **solo** el token de la invitación del primer
   admin en ``e2e/.estado/tenant.json`` (ignorado por git).
4. Spec 017, T9: crea un desarrollador de la consola con la CLI de T1
   (``flask crear-desarrollador --password-stdin``) y una contraseña aleatoria de esta
   corrida, guardada solo en ``e2e/.estado/plataforma.json`` (ignorado por git).

Se ejecuta con el entorno de uv del backend: ``uv run --project ../backend python e2e/base.py``.
Nunca muestra URL ni contraseñas.
"""

import json
import os
import re
import secrets
import subprocess
import sys

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

sys.path.insert(0, os.path.dirname(__file__))
from entorno import BACKEND, BASE_E2E, ESTADO, cargar, entorno_e2e  # noqa: E402


def main() -> None:
    valores = cargar()
    migrador = make_url(valores["MIGRATION_DATABASE_URL"]).set(drivername="postgresql")
    with psycopg.connect(migrador.render_as_string(hide_password=False), autocommit=True, connect_timeout=5) as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(BASE_E2E)))
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(BASE_E2E)))
        conn.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                sql.Identifier(BASE_E2E), sql.Identifier(valores["APP_DB_USER"])
            )
        )
    entorno = entorno_e2e()
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=entorno, check=True, capture_output=True)
    salida = subprocess.run(
        [sys.executable, "-m", "flask", "--app", "app", "create-tenant", "Clínica E2E", "admin@e2e.ejemplo.test"],
        cwd=BACKEND,
        env=entorno,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    token = re.search(r"#(\S+)", salida)
    if token is None:
        raise SystemExit("e2e: create-tenant no devolvió el enlace de invitación.")
    ESTADO.mkdir(exist_ok=True)
    (ESTADO / "tenant.json").write_text(json.dumps({"token": token.group(1)}), encoding="utf-8")
    crear_desarrollador(entorno)
    print(f"e2e: base {BASE_E2E} lista y migrada.")


DESARROLLADOR = "dev@e2e.ejemplo.test"


def crear_desarrollador(entorno: dict[str, str]) -> None:
    """Desarrollador de e2e por la CLI (nombre y contraseña por la entrada estándar)."""
    clave = f"E2e-Plataforma-{secrets.token_urlsafe(12)}"
    subprocess.run(
        [sys.executable, "-m", "flask", "--app", "app", "crear-desarrollador", DESARROLLADOR, "--password-stdin"],
        cwd=BACKEND,
        env=entorno,
        input=f"Dev E2E\n{clave}\n",
        check=True,
        capture_output=True,
        text=True,
    )
    (ESTADO / "plataforma.json").write_text(json.dumps({"email": DESARROLLADOR, "password": clave}), encoding="utf-8")


if __name__ == "__main__":
    main()
