# Tasks 010 — Dashboard (Inicio)

> **Estado:** Aprobadas (G1–G3, 2026-11-15). Una tarea ≤ 1 día, pruebas primero, revisión y commit por tarea; el contrato de cada endpoint entra en su tarea. Plan en `plan.md`.

| Tarea | Resultado | Verificación | Depende de |
|---|---|---|---|
| T1 | `GET /inicio` (indicadores por rol); contrato; pruebas de cifras, vacíos, roles, tenant y respuesta del contador sin dinero | backend: `pytest`, `ruff`; web `api:types` | aprobación |
| T2 | `GET /inicio/actividad` (filtro de precio común con el historial); contrato; pruebas | igual que T1 | aprobación |
| T3 | `GET /inicio/evolucion` (máx. 12, % en unidades); contrato; igualdad punto a punto con el informe | igual que T1 | aprobación |
| T4 | Web: gráficas de barras accesibles (Q1) | web: `test`, `lint`, `typecheck`, `build` | aprobación |
| T5 | Web: indicadores y último informe reales en `/admin`, fallas aisladas | igual que T4 | T1 |
| T6 | Web: gráficas por categoría y ubicación y evolución en `/admin` | igual que T4 | T3, T4 |
| T7 | Web: actividad reciente (admin y contador) | igual que T4 | T2 |
| T8 | Web: Inicio del contador (Q3) | igual que T4 | T1, T7 |
| T9 | Navegador real, revisión de seguridad y de dominio | skill `browser-qa` | T5–T8 |

## Notas por tarea
