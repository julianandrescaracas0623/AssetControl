# Tasks 004 — Activos: alta por escaneo

> **Estado:** Aprobadas (G1–G3, 2026-11-14). Una tarea ≤ 1 día, pruebas primero, revisión y commit por tarea; el contrato de cada endpoint entra en su tarea. Plan en `plan.md`.

| Tarea | Resultado | Verificación | Depende de |
|---|---|---|---|
| T1 | Migración `0007` (`activo`, `activo_evento`, disparador D1, RLS, `GRANT`), modelos, catálogo de RLS y pruebas en la base; `docs/03` | backend: `pytest`, `ruff` | aprobación |
| T2 | Dominio puro: `normalizar_codigo` y `parsear_precio` con pruebas exhaustivas | backend | T1 |
| T3 | `POST /activos` (alta e idempotencia), `GET /activos/codigo/{codigo}`, `GET /activos/{id}`, precio por rol, D2 en ubicaciones; contrato | backend + web `npm test` | T2 |
| T4 | Duplicar (`copiar_de`) con Q3; contrato | igual que T3 | T3 |
| T5 | Búsqueda paginada y sugerencias; prueba "ninguna respuesta al contador trae precio"; contrato | igual que T3 | T3 |
| T6 | Web: resolver y alta reales sin cámara (contar y admin), reintento con el mismo `id`, copiar de un parecido | web: `test`, `lint`, `typecheck`, `build` | T4, T5 |
| T7 | Web: autocompletar nombre, marca, modelo y subtipo | igual que T6 | T6 |
| T8 | Web: escáner ZXing con estados y antirrebote | igual que T6 | T6 |
| T9 | Web: `/admin/activos` y ficha con datos reales (solo lectura) | igual que T6 | T5 |
| T10 | HTTPS de desarrollo para teléfonos y guía | igual que T6 | T8 |
| T11 | Navegador real, revisión de seguridad y dominio, guía de la prueba con teléfonos (A6) | skill `browser-qa` | T6–T10 |

## Notas por tarea

- **T1 (hecha, 2026-11-14):** migración `0007_activos` (`activo` con `CHECK` de código y precio, únicos, FK compuestas a categoría, ubicación y membresía, índices de búsqueda; `activo_evento` inmutable con `seq` por identidad; disparador `activo_ubicacion_valida` para D1; RLS y `GRANT` por columna, sin `UPDATE` ni `DELETE`). Modelos `app/activos/models.py`. Catálogo de RLS ampliado (la lista de funciones de `public` pasa de vacía a solo la del disparador), `test_migrations.py` con la nueva cabeza y su subir/bajar, `test_activos_db.py` (formato y unicidad del código, precio, D1, referencias de otro tenant, sin escrituras prohibidas, atributos de la función). `docs/03` actualizado. Backend 1369 pruebas, ruff limpio.
- **T2 (hecha, 2026-11-14):** `app/activos/dominio.py` con `normalizar_codigo` (solo ASCII antes de pasar a mayúsculas: "ß" o "ı" no se convierten en otras letras) y `parsear_precio` (solo texto canónico, `Decimal` con dos decimales, tope `999999999999.99`). 40 pruebas en `test_activos_dominio.py`. Ajuste del plan §3: el formato colombiano lo convierte la web.
