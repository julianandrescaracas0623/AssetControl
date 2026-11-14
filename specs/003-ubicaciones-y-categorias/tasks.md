# Tasks 003 — Ubicaciones y categorías

> **Estado:** Aprobadas (G1–G3, 2026-11-14). Una tarea ≤ 1 día, pruebas primero, revisión y commit por tarea. Plan en `plan.md`.

| Tarea | Resultado | Verificación | Depende de |
|---|---|---|---|
| T1 | Migración `0006` (tablas, FK compuesta, `CHECK`, únicos parciales, RLS, `GRANT` por columna) + `test_catalog_rls.py` ampliado + pruebas de aislamiento en la base; `docs/03` actualizado | `cd backend && uv run pytest && uv run ruff check .` | aprobación |
| T2 | Modelos, servicio y API de ubicaciones (crear, listar, renombrar, activar/desactivar), `nombre_clave`, bloqueo del padre, errores nuevos; catálogo de `test_roles.py` | igual que T1 | T1 |
| T3 | API de categorías (crear, listar, renombrar, sugeridas idempotentes) | igual que T1 | T1 |
| T4 | Contrato OpenAPI de los 7 endpoints, `test_openapi.py`, tipos y `api.*` en la web | backend + `cd web && npm test && npm run typecheck` | T2, T3 |
| T5 | `/admin/ubicaciones` (árbol, crear, renombrar, desactivar) | `cd web && npm test && npm run lint && npm run typecheck && npm run build` | T4 |
| T6 | `/admin/categorias` (lista, crear, renombrar, sugeridas) | igual que T5 | T4 |
| T7 | `LocationPicker` con datos por prop y selector real en el inicio de conteo | igual que T5 | T4 |
| T8 | Navegador real a 375 y 1440 px, revisión de seguridad y de dominio | skill `browser-qa` | T5, T6, T7 |

## Notas por tarea

_(se completan al cerrar cada tarea)_
