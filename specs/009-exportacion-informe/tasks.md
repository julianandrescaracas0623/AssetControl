# Tasks 009 — Exportar el informe a Excel y PDF

> **Estado:** Aprobadas (G1–G3, 2026-11-15). Una tarea ≤ 1 día, pruebas primero, revisión y commit por tarea; el contrato de cada endpoint entra en su tarea. Plan en `plan.md`.

| Tarea | Resultado | Verificación | Depende de |
|---|---|---|---|
| T1 | Dependencias fijadas; `documento` y `formato_cop` con pruebas (misma tabla de casos que la web) | backend: `pytest`, `ruff` | aprobación |
| T2 | Excel: `a_excel`, ruta, contrato (respuesta binaria), cabeceras; igualdad con el JSON, ceros, fórmulas, roles, tenant | backend + web `npm run api:types` | T1 |
| T3 | PDF: `a_pdf`, ruta, contrato; igualdad con el JSON, ceros, roles | igual que T2 | T1 |
| T4 | Web: botones de exportar en el informe con descarga, carga y error | web: `test`, `lint`, `typecheck`, `build` | T2, T3 |
| T5 | Navegador real, archivos leídos y comparados con la pantalla; revisión de seguridad y de dominio | skill `browser-qa` | T4 |

## Notas por tarea
- **T1 (hecha, 2026-11-15):** dependencias fijadas (`xlsxwriter==3.3.1`, `reportlab==5.1.0`; en desarrollo `openpyxl==3.1.5`, `pypdf==7.1.0`) en `pyproject.toml` y `uv.lock`. `app/conteo/exportar.py`: `documento(informe)` arma `Documento` (metadatos, fila de totales, desglose por categoría y ubicación, no encontrados) desde el dict de `cierre.informe` sin sumar; `formato_cop` y `porcentaje` iguales a la web (misma tabla de casos que `format.test.ts`); fechas `dd/mm/aaaa` y hora de cierre en Colombia (UTC−5 fijo, sin depender de `tzdata` en Windows); `nombre_base` ASCII seguro. `test_exportar_documento.py` (19).
