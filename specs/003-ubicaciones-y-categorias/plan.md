# Plan 003 — Ubicaciones y categorías

> **Estado:** Aprobado (G1–G3, 2026-11-14) con Q1–Q4 en la opción recomendada (`spec.md`, Decisiones).

## 1. Enfoque

Primero la base (sin tablas no hay nada que aislar), luego la API con sus pruebas de rol y aislamiento, después el contrato y al final las pantallas. Patrón de la spec 002: RLS forzada por tenant, privilegios por columna, sin `DELETE`, pruebas de catálogo con listas cerradas. Sin dependencias nuevas.

## 2. Base de datos (migración `0006_ubicaciones_y_categorias`, T1)

**`ubicacion`:** `id uuid PK DEFAULT gen_random_uuid()`, `tenant_id uuid NOT NULL REFERENCES tenant`, `nombre text NOT NULL CHECK (char_length(nombre) BETWEEN 1 AND 120)`, `nombre_clave text NOT NULL`, `tipo text NOT NULL CHECK (tipo IN ('sede','sala','box'))`, `padre_id uuid NULL`, `activa boolean NOT NULL DEFAULT true`, `creado_en timestamptz NOT NULL DEFAULT now()`.

- `UNIQUE (tenant_id, id)` y FK compuesta `(tenant_id, padre_id) → ubicacion (tenant_id, id)` (`MATCH SIMPLE`): el padre es siempre del mismo tenant, lo haga quien lo haga.
- `CHECK ((tipo = 'sede') = (padre_id IS NULL))`. El tipo del padre (sala bajo sede, box bajo sala) lo exige la aplicación con el padre bloqueado (`FOR UPDATE`); una función de base sería más superficie en el catálogo cerrado sin ganancia (la FK ya impide cruzar tenants).
- Únicos parciales (los `NULL` no chocan en un `UNIQUE`): `(tenant_id, nombre_clave) WHERE padre_id IS NULL` y `(tenant_id, padre_id, nombre_clave) WHERE padre_id IS NOT NULL`.

**`categoria`:** `id`, `tenant_id`, `nombre` (mismo `CHECK`), `nombre_clave`, `creado_en`; `UNIQUE (tenant_id, id)` (para las FK compuestas de `activo` en la 004) y `UNIQUE (tenant_id, nombre_clave)`.

**Seguridad (igual que 0002):** `ENABLE` + `FORCE ROW LEVEL SECURITY`; `tenant_isolation` `TO` el rol de la aplicación con `USING` y `WITH CHECK` sobre `app.tenant_id`; `GRANT SELECT, INSERT (tenant_id, nombre, nombre_clave, tipo, padre_id)` y `UPDATE (nombre, nombre_clave, activa)` en `ubicacion`; `SELECT, INSERT (tenant_id, nombre, nombre_clave)` y `UPDATE (nombre, nombre_clave)` en `categoria`; sin `DELETE` ni `TRUNCATE`; `REVOKE ALL` a `anon`/`authenticated`/`service_role`. `test_catalog_rls.py` las añade a sus listas cerradas (tablas, políticas y `GRANT` por columna).

**`nombre_clave`:** la calcula la aplicación (no una colación de la base): `normalize_display_name` (H-3) → NFD → quitar marcas combinantes (`Mn`) → `casefold()` → espacios internos colapsados. "Consultorio  Uno", "consultorio uno" y "Consultorío Uno" chocan.

### Cambios a `docs/03` (autorizados con la aprobación; los aplica el implementer en T1)

1. `ubicacion`: añadir `nombre_clave` y `creado_en`; documentar la FK compuesta del padre, el `CHECK` de sede y los únicos parciales.
2. `categoria`: añadir `nombre_clave` y `creado_en`; documentar el `UNIQUE (tenant_id, nombre_clave)`.

## 3. API (T2–T3)

Todo bajo `require_role` (catálogo de `test_roles.py`: cada endpoint con su prueba de `401`/`403` y de aislamiento). Cuerpos JSON de 4 KB como máximo (se amplía `AUTH_PATH_PREFIXES` a un prefijo de "cuerpo pequeño" que incluya `/ubicaciones` y `/categorias`). Identificadores generados en el servidor.

| Método y ruta | Rol | Cuerpo | Respuesta |
|---|---|---|---|
| `GET /ubicaciones` | ambos | — | `200 {ubicaciones: [{id, nombre, tipo, padre_id, activa}]}`; el contador solo recibe activas; orden sede, sala, box y nombre |
| `POST /ubicaciones` | admin | `{nombre, tipo, padre_id?}` | `201 {ubicacion}` |
| `PATCH /ubicaciones/{id}` | admin | `{nombre?, activa?}` (al menos uno) | `200 {ubicacion}` |
| `GET /categorias` | ambos | — | `200 {categorias: [{id, nombre}]}` por nombre |
| `POST /categorias` | admin | `{nombre}` | `201 {categoria}` |
| `PATCH /categorias/{id}` | admin | `{nombre}` | `200 {categoria}` |
| `POST /categorias/sugeridas` | admin | — | `200 {categorias, creadas}` (idempotente) |

**Errores nuevos** (se suman a `ErrorCode` y a la prueba de códigos): `jerarquia_invalida` (400: sede con padre, sala sin padre sede, box sin padre sala), `nombre_duplicado` (409), `tiene_hijas_activas` (409), `padre_inactivo` (409). Padre o `id` de otro tenant o inexistente: `404 no_encontrado` (RLS lo oculta). Nombre fuera de H-3 o cuerpo mal formado: `400 solicitud_invalida`.

**Concurrencia:** crear una hija y desactivar el padre toman el padre con `SELECT ... FOR UPDATE` en la misma transacción: no queda una hija activa bajo un padre inactivo. Un duplicado por carrera lo detiene el índice único (`23505` → `409 nombre_duplicado`).

## 4. Contrato y tipos (T4)

`backend/openapi.yaml` con los 7 endpoints, esquemas `Ubicacion`, `Categoria` y cuerpos; `test_openapi.py` ejercita cada estado declarado. `npm run api:types`; `api.*` nuevos en `cliente.ts` y consultas de TanStack Query (`['ubicaciones']`, `['categorias']`) con invalidación tras cada escritura.

## 5. Web (T5–T7)

- **`/admin/ubicaciones` (T5):** árbol por sede con salas y boxes sangrados; "Nueva sede" arriba y "Agregar sala"/"Agregar box" en cada fila (diálogo con nombre; tipo y padre ya fijados por dónde se pulsa: cero decisiones de jerarquía para el admin); renombrar en diálogo; desactivar/reactivar con confirmación y el error del servidor si tiene hijas activas; filtro "Mostrar inactivas". A 375 px: lista en tarjetas con menú de acciones de 44 px.
- **`/admin/categorias` (T6):** lista, "Nueva categoría" y renombrar; vacía: estado vacío con "Cargar las 6 sugeridas" (R6).
- **Inicio de conteo (T7):** `LocationPicker` recibe las ubicaciones por prop (deja de importar los datos ficticios) y el inicio las pide a la API; las maquetas que aún no conectan (alta, verificar) le pasan los ficticios. "Última usada" queda en memoria de la sesión de la pestaña (sin `localStorage`).
- Navegación: `Pendiente` deja de usarse para Ubicaciones y Categorías.

## 6. Verificación (T8)

Navegador real contra el backend (base de QA aparte): crear sede, sala y box; duplicado; desactivar con hijas (error) y en orden; categorías sugeridas dos veces; el contador ve solo activas en el selector y recibe "Sin permiso" en `/admin/ubicaciones`. 375 y 1440 px: 0 desbordes, 0 errores de consola, 0 violaciones axe. Revisión de `security-reviewer` (RLS, `GRANT`, `404` entre tenants) y de `domain-guardian` (jerarquía y nodo exacto para el desglose).

## 7. Riesgos

- Renombrar cambia el rótulo de informes cerrados (guardan el `id`): aceptado, decisión pendiente en la 008.
- La clave sin tildes depende de la base Unicode de Python (igual que H-6): la comparación vive solo en la aplicación y la base solo hace cumplir la unicidad de la clave ya calculada.
