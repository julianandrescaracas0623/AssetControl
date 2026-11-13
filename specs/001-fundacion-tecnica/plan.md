# Plan 001 — Fundación técnica

## 1. Enfoque

Construir primero el backend (configuración, acceso a datos con tenant, salud y errores, pruebas) porque define el patrón de aislamiento; después el entorno Docker y la web base. El CI y los hooks cierran la fundación. Nada de dominio.

## 2. Cambios por capa

### Base de datos

- PostgreSQL 16. Alembic con una revisión inicial vacía y reversible.
- Sin tablas de negocio.

### Backend

- `backend/app/__init__.py`: `create_app(config)`.
- `backend/app/config.py`: lectura de `DATABASE_URL`, `SECRET_KEY`, `ENVIRONMENT`; error con el nombre de la variable.
- `backend/app/db.py`: engine y sesión de SQLAlchemy 2; `tenant_session(tenant_id)` como único acceso a datos con tenant.
- `backend/app/meta/routes.py`: `GET /health`.
- `backend/app/errors.py`: manejador de errores con JSON uniforme y `request_id`.
- `backend/tests/conftest.py`: PostgreSQL de pruebas, transacción con rollback por prueba.
- `pyproject.toml` con `ruff` y `pytest`; dependencias gestionadas con uv (decidido 2026-11-11). Los comandos se invocan como `uv run pytest` y `uv run ruff check .`; el bloqueo de versiones (archivo de lock) lo genera uv.

### Web

- `web/`: Vite + React + TypeScript estricto.
- Tailwind CSS y `npx shadcn@latest init`; un componente (`button`, `card`) añadido con la CLI.
- Pantalla que consulta `/health` con TanStack Query y muestra cargando, error y éxito.
- Vitest para la pantalla; scripts `lint`, `typecheck`, `test`, `build`.

### Entorno y CI

- `docker-compose.yml` (api + postgres), `backend/Dockerfile` (instala dependencias con uv), `.env.example`.
- Las pruebas usan el PostgreSQL local de Docker; producción apuntará al PostgreSQL de Supabase (`DATABASE_URL`), sin Supabase Auth ni su API automática. La versión mayor local debe coincidir con la de Supabase `[PENDIENTE: confirmar versión]` (hoy el plan dice PostgreSQL 16).
- OpenAPI y tipos generados: spec 002, fuera de esta.
- Workflows de `.github/` ya escritos; se ajustan los comandos si cambia algo.

## 3. Orden de implementación

T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 → T9 → T10. La web (T8, T9) no empieza antes de cerrar T5.

## 4. Riesgos técnicos

| Riesgo | Mitigación |
|---|---|
| Inicializar el engine al importar rompe las pruebas | Crear el engine dentro de `create_app` |
| `tenant_session` fácil de saltarse | Prueba con dos tenants; el resto del código no recibe la sesión cruda |
| Pruebas lentas con Postgres | Contenedor reutilizable y rollback por transacción |
| shadcn/ui cambia el scaffolding | Fijar versión de la CLI y documentar el comando |

## 5. Estrategia de pruebas

- Backend: `uv run pytest` contra PostgreSQL (app factory, config, tenant con dos tenants, salud, errores).
- Web: Vitest para la pantalla de salud; verificación manual a 375 px y 1440 px con capturas.
- Aislamiento: la prueba de R4 se convierte en la plantilla de las pruebas por endpoint.

## 6. Migraciones y reversa

Revisión inicial vacía. Reversa: `uv run alembic downgrade base`. CI ejecuta `upgrade → downgrade → upgrade`.

## 7. Alternativa descartada

Crear ya las tablas `tenant`, `usuario` y `membresia`. Se descarta: pertenecen a la spec 002 (auth y roles) y adelantarlas acopla la fundación al dominio.
