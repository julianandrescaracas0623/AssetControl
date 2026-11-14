# Tasks 007 — Discrepancias y pendientes

> **Estado:** Aprobadas (G1–G3, 2026-11-14). Una tarea ≤ 1 día, pruebas primero, revisión y commit por tarea; el contrato de cada endpoint entra en su tarea. Plan en `plan.md`.

| Tarea | Resultado | Verificación | Depende de |
|---|---|---|---|
| T1 | Migración `0010` (tipo `discrepancia_descartada`, índice único de resolución), pruebas en la base; `docs/03` | backend: `pytest`, `ruff` | aprobación |
| T2 | Lista de discrepancias con estado derivado (R3); contrato | backend + web `npm test` | T1 |
| T3 | Aplicar y descartar en lote, desfase, carreras; contrato | igual que T2 | T2 |
| T4 | Pendientes por activo y ubicación (sin precio); contrato | igual que T2 | T1 |
| T5 | Web: `/admin/discrepancias` | web: `test`, `lint`, `typecheck`, `build` | T3 |
| T6 | Web: enlaces desde la sesión, pendientes en el detalle, eventos de discrepancia en el historial | igual que T5 | T5 |
| T7 | Web: `/contar/pendientes` real; conteo sin banda de maqueta | igual que T5 | T4 |
| T8 | Navegador real, revisión de seguridad y de dominio | skill `browser-qa` | T5–T7 |

## Notas por tarea

- **T1 (hecha, 2026-11-14):** migración `0010_discrepancias`: `discrepancia_descartada` en el `CHECK` de `activo_evento.tipo` e índice único parcial `activo_evento_una_resolucion (tenant_id, verificacion_id)` sobre `ubicacion_cambiada` y `discrepancia_descartada` con verificación; sin cambios de permisos. Pruebas: una sola resolución por verificación en las cuatro combinaciones, movimientos sin verificación sin límite, cadena con cabeza `0010` y su subir/bajar. `TipoEvento` del contrato y `docs/03` actualizados.
