# Tasks 002b — Acceso: contrato y web mínima

> **Estado:** Aprobadas (G1–G3, 2026-11-14). Una tarea ≤ 1 día, pruebas primero, revisión y commit por tarea. Plan en `plan.md`.

| Tarea | Resultado | Verificación | Depende de |
|---|---|---|---|
| T1 | `backend/openapi.yaml` a mano y `tests/test_openapi.py` (rutas, respuestas reales, códigos de error); `pyyaml` en `dev` | `cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check .` | — |
| T2 | `openapi-typescript` + `api:types` + `schema.d.ts` versionado + prueba de frescura + cliente tipado con `ErrorApi` | `cd web && npm test && npm run lint && npm run typecheck` | T1 |
| T3 | `@tanstack/react-query`, raíz con sesión, guardas, `/login`, cerrar sesión en los shells, fin de `?rol=`, cookie en el *proxy* | `cd web && npm test && npm run lint && npm run typecheck && npm run build` | T2 |
| T4 | `/invitacion`: token del fragmento, validar, nombre y contraseña, aceptar y redirigir | igual que T3 | T3 |
| T5 | `/admin/usuarios`: invitar (email y rol), enlace para copiar | igual que T3 | T3 |
| T6 | Navegador real contra el backend a 375 px y 1440 px: capturas, consola, axe, almacenamiento | skill `browser-qa` | T4, T5 |

## Notas por tarea

- **T1 (hecha, 2026-11-14):** `backend/openapi.yaml` (OpenAPI 3.1, 9 operaciones, respuestas reutilizables y `x-codigos` por respuesta) y `tests/test_openapi.py` (16 pruebas): rutas de Flask = `paths`; respuestas reales de cada operación validadas con cabeceras obligatorias (`Set-Cookie`, `Retry-After`); todo estado declarado ejercitado salvo `500` de aceptar (A22, ya probado en `test_invitaciones_aceptar.py`); `429`/`503` con `increment_attempts` sustituido; enum de `ErrorCode` = códigos del backend (17). Probado que quitar un campo, un código o una respuesta rompe las pruebas. `pyyaml==6.0.3` en `dev`; `uv.lock` regenerado con uv 0.13.7 (la versión de la CI). Backend: 1202 pruebas en verde, ruff limpio.
