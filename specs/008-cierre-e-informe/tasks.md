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

- **T1 (hecha, 2026-11-14):** migración `0011_cierre_e_informe` y modelos (`SesionDesglose`, `SesionNoEncontrado`, totales en `SesionConteo`). Totales con `CHECK` (cerrada ⇔ totales, `>= 0`, registrado = encontrado + no encontrado); disparador `sesion_conteo_inmutable` (solo `abierta → cerrada`, `P0003`); `UPDATE` de la aplicación solo de las columnas del cierre. `sesion_desglose` (dimensión coherente, sumas en COP y unidades, únicos parciales por categoría y por ubicación, etiqueta congelada) y `sesion_no_encontrado` (único por activo, nombres y precio congelados, marca `en_reparacion`), ambas solo `INSERT`/`SELECT`, con el disparador `conteo_cerrado_requerido` (`P0004`) y FK compuestas. Las pruebas que cerraban sesiones a mano ahora ponen totales (el `CHECK` los exige). `test_cierre_db.py` (24), catálogo de RLS y permisos (tablas, políticas, columnas, funciones), cadena con cabeza `0011` y su subir/bajar. `docs/03` actualizado. Backend 1673 en verde.
