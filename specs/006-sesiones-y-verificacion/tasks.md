# Tasks 006 — Sesiones de conteo y verificación

> **Estado:** Aprobadas (G1–G3, 2026-11-14). Una tarea ≤ 1 día, pruebas primero, revisión y commit por tarea; el contrato de cada endpoint entra en su tarea. Plan en `plan.md`.

| Tarea | Resultado | Verificación | Depende de |
|---|---|---|---|
| T1 | Migración `0009` (`sesion_conteo`, `verificacion`, FK de `activo_evento`), modelos, catálogo de RLS y pruebas en la base; `docs/03` | backend: `pytest`, `ruff` | aprobación |
| T2 | Sesiones: abrir, listar, abierta y detalle con avance por ubicación; contrato | backend + web `npm test` | T1 |
| T3 | Verificar: idempotencia (Q3), `sesion_cerrada`, dado de baja, ubicación encontrada, copia de precio, categoría y ubicación, evento `verificado`; última verificación del activo; contrato | igual que T2 | T2 |
| T4 | Precio por rol en todas las respuestas de sesiones y verificaciones (prueba que recorre las del contador); `verificado` en el historial | igual que T2 | T3 |
| T5 | Web: `/admin/sesiones` (lista, abrir, detalle con avance) | web: `test`, `lint`, `typecheck`, `build` | T4 |
| T6 | Web: Inicio del conteo real, sala de trabajo recordada, cabecera real | igual que T5 | T4 |
| T7 | Web: Verificar real con sus estados (confirmado, no confirmado y reintento, sesión cerrada, dado de baja, ya verificado) | igual que T5 | T6 |
| T8 | Web: sin banda de maqueta en el conteo real, rutas de maqueta retiradas, historial con `verificado` | igual que T5 | T7 |
| T9 | Navegador real, revisión de seguridad y de dominio | skill `browser-qa` | T5–T8 |

## Notas por tarea

(Se completan al cerrar cada tarea.)
