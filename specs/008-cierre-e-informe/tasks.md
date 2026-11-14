# Tasks 008 — Cierre de sesión, informe y valor actual

> **Estado:** Aprobadas (G1–G3, 2026-11-14). Una tarea ≤ 1 día, pruebas primero, revisión y commit por tarea; el contrato de cada endpoint entra en su tarea. Plan en `plan.md`.

| Tarea | Resultado | Verificación | Depende de |
|---|---|---|---|
| T1 | Migración `0011` (totales, disparador de inmutabilidad, `sesion_desglose`, `sesion_no_encontrado`), modelos, catálogo de RLS, pruebas en la base; `docs/03` | backend: `pytest`, `ruff` | aprobación |
| T2 | `universo` y `agregar` (única fuente), cerrar con candado exclusivo y repetición idempotente; pruebas de R4 y de cuadre (también al azar) y de concurrencia; contrato | backend + web `npm test` | T1 |
| T3 | Informe y valor actual; informe inmutable ante cambios posteriores; contrato | igual que T2 | T2 |
| T4 | Web: cerrar desde el detalle con aviso; sesiones cerradas enlazan al informe | web: `test`, `lint`, `typecheck`, `build` | T3 |
| T5 | Web: informe real | igual que T4 | T3 |
| T6 | Web: valor actual | igual que T4 | T3 |
| T7 | Navegador real, revisión de seguridad y de dominio | skill `browser-qa` | T4–T6 |

## Notas por tarea

(Se completan al cerrar cada tarea.)
