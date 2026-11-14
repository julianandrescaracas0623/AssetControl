# Tasks 005 — Ciclo de vida e historial del activo

> **Estado:** Aprobadas (G1–G3, 2026-11-14). Una tarea ≤ 1 día, pruebas primero, revisión y commit por tarea; el contrato de cada endpoint entra en su tarea. Plan en `plan.md`.

| Tarea | Resultado | Verificación | Depende de |
|---|---|---|---|
| T1 | Migración `0008` (`UPDATE` por columna, tipo `datos_cambiados`, índice del historial), catálogo de RLS y permisos, pruebas en la base; `docs/03` | backend: `pytest`, `ruff` | aprobación |
| T2 | `PATCH /activos/{id}` con `If-Match` (`412`, `428`), diferencia por campo y eventos de precio, categoría y datos; `row_version` en la respuesta; contrato | backend + web `npm test` | T1 |
| T3 | Mover, estado, baja y reactivar (Q1, Q2); `409 activo_dado_de_baja`; contrato | igual que T2 | T2 |
| T4 | Historial por rol (sin precio para el contador), filtro `ubicacion_id` en la búsqueda, `ubicacion_id` en `tiene_activos`; contrato | igual que T2 | T3 |
| T5 | Web: editar en la ficha con `If-Match` y manejo del `412` conservando lo escrito | web: `test`, `lint`, `typecheck`, `build` | T4 |
| T6 | Web: mover, estado, baja y reactivar en la ficha; ficha de solo lectura del dado de baja | igual que T5 | T5 |
| T7 | Web: historial en la ficha del admin y en `/contar` para el contador | igual que T5 | T4 |
| T8 | Web: acciones reales en la lista, filtro por ubicación y enlace desde `tiene_activos` | igual que T5 | T6 |
| T9 | Navegador real, revisión de seguridad y de dominio | skill `browser-qa` | T5–T8 |

## Notas por tarea

- **T1 (hecha, 2026-11-14):** migración `0008_activo_cambios`: `GRANT UPDATE` por columna en `activo` (sin `codigo`, `id`, `tenant_id`, `creado_por`, `creado_en` ni `atributos`) y `datos_cambiados` en el `CHECK` de `activo_evento.tipo`; su `downgrade` falla sin borrar nada si ya hay eventos de ese tipo. El índice `(tenant_id, activo_id, seq)` de la 0007 ya sirve al historial: no se crea otro. Pruebas: catálogo de permisos exacto, cadena de migraciones con cabeza `0008`, subir/bajar/subir, y en la base: actualizar lo editable y subir la versión, versión vieja no actualiza, D1 al mover (sede, inactiva, otro tenant), los `CHECK` siguen al actualizar, la RLS no deja tocar otro tenant, columnas prohibidas `42501`. `docs/03` con permisos, solo lectura del dado de baja, el tipo nuevo y el contenido de `datos` por evento. Backend 1475 pruebas, ruff limpio.
- **T2 (hecha, 2026-11-14):** `app/activos/cambios.py`: `leer_version` (`If-Match` `"N"` o `N`; débil, vacío o no ASCII → `428 falta_version`), `bloquear` (`FOR UPDATE` y comparación bajo el bloqueo → `412 version_desactualizada` con el activo vigente), `edicion` (solo los campos del alta, normalizados igual; `codigo` → `400 codigo_inmutable`; otro campo → `400`) y `editar` (diferencia por campo; `precio_cambiado`, `categoria_cambiada` y `datos_cambiados` con antes/después y autor; sin cambios no toca versión ni eventos; dado de baja → `409 activo_dado_de_baja`). `PATCH /activos/{id}` solo admin con `ETag`. La respuesta del activo trae `row_version` (ambos roles). **Ajuste:** `referencia` y `color` salen del permiso de `UPDATE` de la 0008 (la API no los expone; mínimo privilegio). Contrato (`EditarActivoBody`, `VersionDesactualizada`, `If-Match`, 4 códigos nuevos) ejercitado. `test_activos_cambios.py` (36). Backend 1513, web 283 en verde.
