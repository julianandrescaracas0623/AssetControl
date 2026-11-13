"""Guardas de código de T3 (spec 001, R4).

El tenant de la transacción se fija en un único punto: ``backend/app/db.py``.
Ningún otro módulo de la aplicación puede nombrar ``app.tenant_id`` ni llamar a
``set_config``; si lo hiciera, abriría una segunda vía para elegir el tenant.
"""

import re
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
ALLOWED = "db.py"
FORBIDDEN = re.compile(r"app\.tenant_id|set_config", re.IGNORECASE)


def find_tenant_setters(root: Path, allowed: str = ALLOWED) -> list[str]:
    """``ruta:línea`` de cada mención prohibida fuera de ``root/allowed``."""
    allowed_path = (root / allowed).resolve()
    hits: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if path.resolve() == allowed_path:
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, start=1):
            if FORBIDDEN.search(line):
                hits.append(f"{path.relative_to(root.parent).as_posix()}:{number}")
    return hits


def test_guard_detects_tenant_setter_outside_db(tmp_path):
    app_dir = tmp_path / "app"
    (app_dir / "rutas").mkdir(parents=True)
    (app_dir / "db.py").write_text("SET = \"set_config('app.tenant_id', x, true)\"\n")
    (app_dir / "rutas" / "activos.py").write_text(
        "import os\n\nsql = \"select SET_CONFIG('app.tenant_id', :t, false)\"\n"
    )
    (app_dir / "otro.py").write_text("x = 1\nclave = 'app.tenant_id'\n")

    assert find_tenant_setters(app_dir) == ["app/otro.py:2", "app/rutas/activos.py:3"]


def test_only_db_module_sets_the_tenant():
    hits = find_tenant_setters(APP_DIR)

    assert hits == [], (
        "Solo backend/app/db.py puede fijar el tenant (app.tenant_id / set_config). "
        "Encontrado en: " + ", ".join(hits)
    )
