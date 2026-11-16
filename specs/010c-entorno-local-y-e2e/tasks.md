# Tasks 010c — Entorno local, conexiones y pruebas e2e

> **Estado:** Aprobadas (2026-11-15).

| Tarea | Resultado | Verificación |
|---|---|---|
| T1 | Imports sin rojo en VS Code | `pyright` sin `reportMissingImports`; `tsc` 5.9 y 6.x limpios |
| T2 | `flask revisar-conexiones` | `pytest`, `ruff` |
| T3 | Pruebas e2e con Playwright | `npm run e2e` en verde; `lint`, `typecheck` |
| T4 | Guía de entorno local | revisión |
| T5 | Demostración en vivo | navegador de la app de Claude |

## Notas por tarea
- **T1 (hecha, 2026-11-15):** causa medida: sin configuración, Pyright (el motor de Pylance) da **225** `import` sin resolver en el backend (`sqlalchemy`, `alembic`, `psycopg`… porque no usa `backend/.venv`, y `acceso_db`/`conftest` de `tests/`); con `pyrightconfig.json`, **0**. En el frontend, el TypeScript 5.9 que trae VS Code marcaba errores que el 6.x no (iterar `NodeListOf`): `DOM.Iterable` en `tsconfig.app.json` los quita en ambas versiones. En tu PC quedó `.vscode/settings.json` (local) con el intérprete de uv, el `.env`, pytest y el TypeScript del proyecto. `.env` local completado (con tu autorización): las cuatro URL ya eran coherentes con usuarios y contraseñas; se cambió `localhost` → `127.0.0.1` (evita la espera por IPv6), se agregaron las variables opcionales y un bloque comentado para Supabase; copia previa en `.env.respaldo-2026-11-15`.
