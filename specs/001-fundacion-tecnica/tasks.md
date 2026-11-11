# Tasks 001 — Fundación técnica

> Máximo 10 tareas. Cada una ≤ 1 día. Una a la vez.
> Comando de verificación obligatorio antes de cerrar.
> **Estado de la spec:** aprobada (2026-11-11). Gestor de dependencias de Python: uv. En el backend, los comandos se ejecutan con `uv run` (p. ej. `uv run pytest`, `uv run ruff check .`, `uv run alembic ...`). OpenAPI y tipos generados entran en la spec 002.

---

### T1 — Estructura del monorepo

- **Depende de:** —
- **Archivos:** `backend/`, `web/`, `.gitignore`, `README.md`
- **Criterio:** existen `backend/` y `web/`; `.gitignore` excluye `.env`, `datos/`, `node_modules`, `dist`, `__pycache__`, `.venv`, `.pytest_cache` y el arnés local.
- **Verificación:** `git status --short` y `git check-ignore -v datos AGENTS.md .claude`
- **Riesgo:** ninguno.

---

### T2 — Backend: configuración y application factory

- **Depende de:** T1
- **Archivos:** `backend/app/__init__.py`, `backend/app/config.py`, `backend/pyproject.toml` (dependencias con uv), archivo de lock de uv, `backend/tests/test_app_factory.py`, `backend/tests/test_config.py`
- **Criterio:** `create_app()` se importa sin abrir conexiones; la falta de una variable obligatoria falla con el nombre de la variable y sin su valor; el entorno se crea con uv desde `pyproject.toml`.
- **Verificación:** `cd backend && uv run pytest tests/test_app_factory.py tests/test_config.py`
- **Riesgo:** inicializar el engine al importar rompe las pruebas.

---

### T3 — Backend: sesión de datos y punto central de tenant

- **Depende de:** T2
- **Archivos:** `backend/app/db.py`, `backend/tests/test_tenant_scope.py`
- **Criterio:** `tenant_session(tenant_id)` aplica el tenant a toda consulta de una tabla de negocio de prueba, falla sin tenant y no deja ver filas de otro tenant (prueba con dos tenants).
- **Verificación:** `cd backend && uv run pytest tests/test_tenant_scope.py`
- **Riesgo:** exponer la sesión sin filtro al resto del código.

---

### T4 — Backend: salud y errores

- **Depende de:** T2, T3
- **Archivos:** `backend/app/meta/routes.py`, `backend/app/errors.py`, `backend/tests/test_health.py`, `backend/tests/test_errors.py`
- **Criterio:** `/health` responde 200 con `{status, db, version}` y 503 si la base falla; un error no controlado responde JSON uniforme con `request_id` y sin traza.
- **Verificación:** `cd backend && uv run pytest tests/test_health.py tests/test_errors.py`
- **Riesgo:** exponer detalles internos en el mensaje de error.

---

### T5 — Arnés de pruebas

- **Depende de:** T2, T3, T4
- **Archivos:** `backend/tests/conftest.py`, `backend/pyproject.toml`
- **Criterio:** cada prueba corre en una transacción con rollback sobre PostgreSQL; `pytest` se puede correr dos veces seguidas sin residuos; hay fixtures de app y de cliente HTTP.
- **Verificación:** `cd backend && uv run pytest && uv run pytest`
- **Riesgo:** dejar datos de prueba entre corridas.

---

### T6 — Alembic y revisión inicial

- **Depende de:** T2
- **Archivos:** `backend/alembic.ini`, `backend/migrations/env.py`, `backend/migrations/versions/0001_baseline.py`
- **Criterio:** `upgrade head` y `downgrade base` funcionan sobre una base vacía; no crea tablas de negocio.
- **Verificación:** `cd backend && uv run alembic upgrade head && uv run alembic downgrade base && uv run alembic upgrade head`
- **Riesgo:** `env.py` leyendo una URL distinta a la de la app.

---

### T7 — Entorno local con Docker

- **Depende de:** T2, T3, T6
- **Archivos:** `docker-compose.yml`, `backend/Dockerfile`, `.env.example`
- **Criterio:** `docker compose up` levanta la API con recarga y PostgreSQL; el `Dockerfile` instala las dependencias con uv desde `pyproject.toml` y su lock; `.env.example` lista las variables sin valores reales; `.env` está ignorado.
- **Verificación:** `docker compose up --build` + `curl http://localhost:5000/health`
- **Riesgo:** `localhost` dentro del contenedor no apunta al host.

---

### T8 — Web: Vite, TypeScript, Tailwind y shadcn/ui

- **Depende de:** T5
- **Archivos:** `web/package.json`, `web/tsconfig.json`, `web/vite.config.ts`, `web/src/main.tsx`, `web/src/App.tsx`, `web/components.json`, `web/src/components/ui/`
- **Criterio:** compila en TypeScript estricto; Tailwind activo; shadcn/ui inicializado con al menos un componente añadido por la CLI; la pantalla muestra el estado de `/health` (cargando, error, éxito) y se ve bien a 375 px.
- **Verificación:** `cd web && npm run build` + captura a 375 px
- **Riesgo:** acoplar la pantalla base a un diseño que aún no existe.

---

### T9 — Web: calidad

- **Depende de:** T8
- **Archivos:** `web/eslint.config.js`, `web/vitest.config.ts`, `web/src/App.test.tsx`
- **Criterio:** `npm run lint`, `npm run typecheck` y `npm test` pasan; la prueba cubre los tres estados de la pantalla de salud.
- **Verificación:** `cd web && npm run lint && npm run typecheck && npm test`
- **Riesgo:** pruebas que dependen de la red real.

---

### T10 — CI, hooks y arranque documentado

- **Depende de:** T2–T9
- **Archivos:** `.github/workflows/*.yml`, `README.md`, `scripts/`
- **Criterio:** el CI corre `ruff`, `pytest`, migraciones, `lint`, `typecheck`, `test` y `build`; corre `check-attribution.sh` sobre el rango del PR; un clon nuevo instala los hooks con `sh scripts/setup-hooks.sh`; el README explica el arranque en menos de 10 líneas; `MEMORY.md` refleja el estado.
- **Verificación:** PR de prueba con un fallo intencional → CI rojo; corregido → CI verde; commit de prueba con `Co-Authored-By: Claude` → CI rojo.
- **Riesgo:** CI que no corre por la configuración de ramas.

---

## Resumen

| Tarea | Depende de | Verificación |
|---|---|---|
| T1 | — | estructura + `git check-ignore` |
| T2 | T1 | `uv run pytest test_app_factory test_config` |
| T3 | T2 | `uv run pytest test_tenant_scope` |
| T4 | T2, T3 | `uv run pytest test_health test_errors` |
| T5 | T2–T4 | `uv run pytest` dos veces |
| T6 | T2 | `uv run alembic upgrade/downgrade/upgrade` |
| T7 | T2, T3, T6 | `docker compose up` + `/health` |
| T8 | T5 | `npm run build` + captura 375 px |
| T9 | T8 | `lint` + `typecheck` + `test` |
| T10 | T2–T9 | CI rojo/verde + hooks instalados |

## Reglas de ejecución

- Una tarea por sesión.
- No se abre T8 antes de cerrar T5: la fundación del backend manda.
- Si una tarea crece más de un día, se divide y se actualiza este archivo con `/sdd-change`.
- T6 no crea tablas de negocio. Si aparece esa necesidad, es otra spec.
