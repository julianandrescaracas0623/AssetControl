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
- **T2 (hecha, 2026-11-15):** `app/conexiones.py` + `flask revisar-conexiones`: por cada URL presente (`DATABASE_URL`, `MIGRATION_DATABASE_URL`, `TEST_*`, `SUPABASE_*`) conecta con 5 s de espera y dice OK/MAL con motivo en español (contraseña incorrecta, base o rol inexistente, sin respuesta, rol de la app con superusuario o `BYPASSRLS`, mismo rol que su pareja, base sin migrar o atrasada frente a la cabeza del repo, Supabase sin TLS); muestra rol, base, TLS y revisión, nunca URL, host ni contraseña; sale con 1 si algo está mal. El rol de la app no lee `alembic_version` (no le hace falta): la revisión la da el migrador; la base de pruebas no se exige migrada. `test_revisar_conexiones.py` (4).
