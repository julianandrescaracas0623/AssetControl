# Plan 005 — Ciclo de vida e historial del activo

> **Estado:** Aprobado (G1–G3, 2026-11-14) con Q1–Q3 en la opción recomendada (`spec.md`).

## 1. Enfoque

Base primero (permiso de `UPDATE` por columna y el tipo de evento nuevo), luego la API: una sola función de dominio escribe el cambio, sube la versión y deja los eventos, y cada endpoint la usa. El contrato de cada endpoint entra en su tarea. Después la web: acciones en la ficha, historial para los dos roles y la lista con filtro por ubicación. Sin dependencias nuevas.

## 2. Base de datos (migración `0008_activo_cambios`, T1)

- `GRANT UPDATE (nombre, categoria_id, ubicacion_id, serial, marca, modelo, subtipo, precio_compra, fecha_compra, estado, row_version, actualizado_en) ON activo` al rol de la aplicación. Sin `codigo`, `tenant_id`, `id`, `creado_por`, `creado_en`, `atributos`, `referencia` ni `color` (la API no los expone). La RLS forzada ya limita el `UPDATE` al tenant (política `FOR ALL` con `WITH CHECK`).
- El `CHECK` de `activo_evento.tipo` suma `datos_cambiados` (Q3). `activo_evento` sigue con solo `SELECT` e `INSERT`.
- El disparador de D1 (`BEFORE INSERT OR UPDATE OF ubicacion_id`) ya cubre mover: no cambia.
- Índice `(tenant_id, activo_id, seq)` en `activo_evento` para el historial (si el de la 0007 no lo cubre).
- `docs/03`: la lista de tipos con `datos_cambiados`, el contenido de `datos` de cada evento de esta spec y los permisos de `UPDATE`.

## 3. Dominio y concurrencia (T2)

- `cambiar(session, activo_id, version, cambios, usuario_id)` en `app/activos/service.py`: `SELECT ... FOR UPDATE` del activo; si `row_version ≠ version` → `412` con el activo vigente; calcula la diferencia campo a campo (normalizando igual que el alta: H-3, precio canónico, código no editable); si no hay diferencias devuelve el activo sin tocar nada; si hay, un solo `UPDATE` con `row_version = row_version + 1` y `actualizado_en = now()`, y los eventos en la misma transacción.
- Eventos y su `datos`:
  - `precio_cambiado`: `{antes, despues}` (texto canónico).
  - `categoria_cambiada`: `{antes: {id, nombre}, despues: {id, nombre}}`.
  - `datos_cambiados`: `{campos: {<campo>: {antes, despues}}}` para nombre, serial, marca, modelo, subtipo y fecha de compra.
  - `ubicacion_cambiada`: `{antes: {id, ruta}, despues: {id, ruta}}` (la ruta se copia para que el historial no cambie si después se renombra la sala).
  - `estado_cambiado`: `{antes, despues, motivo?, nota?}` (motivo solo al reactivar, Q1: `encontrado`, `baja_por_error`, `otro`; nota obligatoria con `otro`).
  - `dado_de_baja`: `{motivo, nota?}` (Q2).
- Motivos de baja (Q2): `danado_sin_reparacion`, `perdido`, `vendido_o_donado`, `obsoleto`, `otro`; `nota` 1–200 caracteres (H-3), obligatoria con `otro`.

## 4. API (T2–T4)

| Método y ruta | Rol | Notas |
|---|---|---|
| `PATCH /activos/{id}` | admin | `If-Match: "<row_version>"`; cuerpo con los campos de R1 (todos opcionales; `null` borra un opcional). `codigo` → `400 codigo_inmutable`. Responde `200` con el activo y `ETag` |
| `POST /activos/{id}/mover` | admin | `{ubicacion_id}` con `If-Match`; D1 → `400 ubicacion_invalida` |
| `POST /activos/{id}/estado` | admin | `{estado: "activo" \| "en_reparacion", motivo?}` con `If-Match`; desde `dado_de_baja` solo `activo` con motivo (reactivar, Q1) |
| `POST /activos/{id}/baja` | admin | `{motivo, nota?}` con `If-Match` |
| `GET /activos/{id}/historial?antes_de=<seq>` | ambos | 50 eventos por página, `seq` descendente, con autor (nombre) y `siguiente` para la próxima página |
| `GET /activos?ubicacion_id=` | ambos | Filtro nuevo de la búsqueda (R10) |

- **Errores nuevos:** `falta_version` (428), `version_desactualizada` (412, con `{error, activo}` vigente), `codigo_inmutable` (400), `activo_dado_de_baja` (409), `motivo_invalido` (400). El `409 tiene_activos` suma `ubicacion_id` para el enlace (R10).
- **Respuesta del activo:** suma `row_version` (el `ETag` y la web lo usan); el precio sigue solo para el admin.
- **Historial por rol (P13):** una sola función arma cada evento según el rol; al contador se le omiten los `precio_cambiado` y se le quita `precio_compra` de `creado` e `importado`. Prueba que recorre el historial y todas las respuestas del contador buscando cualquier clave o valor de precio.
- **`If-Match`:** acepta `"3"` y `3`; cualquier otra forma → `428`. Se compara contra la fila bloqueada, no contra una lectura previa.

## 5. Web (T5–T8)

- **T5 Editar:** en la ficha del admin, "Editar" abre el formulario con los campos de R1 (reutiliza los del alta: `InputSugerido`, categoría, precio en formato colombiano). Envía con `If-Match`. Ante `412`: aviso "Alguien cambió este activo", recarga el vigente, marca los campos que cambiaron y conserva lo escrito para reaplicarlo con un toque.
- **T6 Mover, estado, baja, reactivar:** "Mover" con `LocationPicker` (solo salas y boxes activos); "Enviar a reparación" / "Volver a activo"; "Dar de baja" con diálogo de confirmación, motivo en lista y nota; "Reactivar" en un dado de baja con motivo. Un dado de baja muestra la ficha en solo lectura con su motivo.
- **T7 Historial:** línea de tiempo en la ficha del admin (con precios) y en `/contar/activo/:codigo/historial` para el contador (reemplaza la maqueta de `Historial.tsx`), "Ver más" por páginas; cada evento con autor, fecha y antes/después en lenguaje claro.
- **T8 Lista:** el menú de cada fila llama a las acciones reales; filtro por ubicación (`?ubicacion=` en la URL); el aviso de `tiene_activos` en Ubicaciones enlaza a la lista filtrada.

## 6. Verificación (T9)

Navegador real contra el backend (375 y 1440 px, consola y axe): editar con un conflicto real (dos pestañas sobre la misma versión), mover, en reparación y de vuelta, dar de baja y reactivar, historial del admin y del contador (red sin precio para el contador), desactivar una ubicación con activos → lista filtrada → mover → desactivar. Revisión de seguridad (permisos de `UPDATE`, rol, precio en el historial) y de dominio (eventos, versión, valor con dado de baja y en reparación).

## 7. Dependencias nuevas

Ninguna.
