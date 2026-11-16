# Tasks 013 — Informe con los datos de la empresa y nuevo diseño de exportación

> **Estado:** Aprobadas (G1–G3, 2026-11-16). Una tarea ≤ 1 día, pruebas primero, revisión y commit por tarea. Plan en `plan.md`.

| Tarea | Resultado | Verificación | Depende de |
|---|---|---|---|
| T1 | Migración `0014_empresa_y_detalle` (empresa, logos, copia al cierre, detalle por activo; RLS y privilegios); `docs/03` | backend: `pytest`, `ruff` + prueba de migración y catálogo RLS | aprobación |
| T2 | API de empresa y logo (validación de NIT, logo sin metadatos); contrato; roles | igual que T1 + `api:types` | T1 |
| T3 | Cierre guarda detalle y copia de la empresa desde U; informe con `empresa`; igualdad detalle ↔ desglose | igual que T1 | T1 |
| T4 | Excel v3 (Resumen, hojas por categoría, No encontrados) | igual que T1 (`openpyxl`) | T3 |
| T5 | PDF estilo A con logo (sin firmas) y «Página X de Y» | igual que T1 (`pypdf`) | T3 |
| T6 | Web: Ajustes → Empresa (formulario y logo) | web: `test`, `lint`, `typecheck`, `build` | T2 |
| T7 | Web: aviso en el informe y rótulo de sesiones anteriores | igual que T6 | T3, T6 |
| T8 | Navegador real, e2e, revisión de seguridad y de dominio; `docs/08` y `docs/05` | skill `browser-qa`, `npm run e2e` | T1–T7 |

## Notas por tarea
