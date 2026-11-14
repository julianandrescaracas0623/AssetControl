# Plan 004 — Activos: alta por escaneo

> **Estado:** Propuesto, pendiente de aprobación humana (G1–G3). Las opciones "(recomendado)" son las de Q1–Q6 de `spec.md`; si el humano elige otra, se ajusta antes de T1.

## 1. Enfoque

Base, luego la API con sus pruebas de rol, precio y aislamiento (el contrato de cada endpoint en su tarea, como en la 003), después la web: primero alta y resolución sin cámara (entrada manual), luego el escáner y al final lista y ficha. Las reglas de dinero y código viven en funciones puras con pruebas propias.

## 2. Base de datos (migración `0007_activos`, T1)

**`activo`:** `id uuid PK` (lo manda el cliente), `tenant_id`, `codigo text NOT NULL` (`CHECK` de Q1: `codigo ~ '^[A-Z0-9._/-]{1,40}$'`), `nombre text NOT NULL` (1–120), `categoria_id uuid NOT NULL`, `ubicacion_id uuid NOT NULL`, `serial`, `marca`, `modelo`, `referencia`, `color`, `subtipo` (`text NULL`, cada uno hasta 120), `atributos jsonb NOT NULL DEFAULT '{}'`, `precio_compra numeric(14,2) NOT NULL CHECK (precio_compra >= 0)`, `fecha_compra date NULL`, `estado text NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo','en_reparacion','dado_de_baja'))`, `row_version integer NOT NULL DEFAULT 1`, `creado_por uuid NOT NULL`, `creado_en`, `actualizado_en`.

- `UNIQUE (tenant_id, codigo)`; `UNIQUE (tenant_id, id)`; FK compuestas `(tenant_id, categoria_id) → categoria`, `(tenant_id, ubicacion_id) → ubicacion`, `(tenant_id, creado_por) → membresia (tenant_id, usuario_id)`.
- Índices para buscar: `(tenant_id, serial)` y `(tenant_id, ubicacion_id, estado)` (la regla D2 los cuenta).
- **D1 en la base, no solo en la aplicación:** un disparador `BEFORE INSERT OR UPDATE OF ubicacion_id` rechaza una ubicación de tipo `sede` o inactiva (lee `ubicacion` con la FK ya garantizando el tenant). Es pequeño y cierra la regla aunque un error de la aplicación la saltara. Lo revisa el `security-reviewer` (función `SECURITY INVOKER`, `search_path` fijo).

**`activo_evento`:** `id uuid PK DEFAULT gen_random_uuid()`, `tenant_id`, `activo_id`, `tipo text CHECK` (la lista de `docs/03`), `datos jsonb NOT NULL`, `usuario_id uuid NOT NULL`, `sesion_id`, `verificacion_id` (`NULL` hasta la 006, sin FK aún), `ocurrido_en timestamptz DEFAULT now()`, `seq bigint GENERATED ALWAYS AS IDENTITY`. FK compuesta al activo. **Inmutable:** la aplicación solo tiene `SELECT` e `INSERT`.

**Seguridad:** RLS forzada con `tenant_isolation`; `GRANT INSERT` por columna (sin `estado`, `row_version`, fechas ni `seq`: los pone la base); `UPDATE` de `activo` aún **ninguno** (llega con la 005); sin `DELETE`. `precio_compra` es legible por el rol de la aplicación (el filtrado por rol es del servidor, P13).

**`docs/03`:** se actualiza en T1 con `UNIQUE (tenant_id, codigo)`, el `CHECK` de Q1, el disparador de D1 y que `activo_evento` es inmutable.

## 3. Dominio (funciones puras, T2)

- `normalizar_codigo(texto) -> str | None`: recorta, pasa a mayúsculas y valida Q1.
- `parsear_precio(texto | número) -> Decimal | None`: acepta `"1390000"`, `"1390000.50"` y `"1.390.000,50"` (formato colombiano); rechaza negativos, más de dos decimales, `NaN`, infinito y exponentes; nunca `float`.

## 4. API (T3–T5)

| Método y ruta | Rol | Notas |
|---|---|---|
| `GET /activos/codigo/{codigo}` | ambos | R1; el código se normaliza antes de buscar |
| `POST /activos` | ambos | `{id, codigo, nombre, precio_compra, categoria_id, ubicacion_id, serial?, marca?, modelo?, subtipo?, fecha_compra?}`; `201` nuevo, `200` si el `id` ya existe con el mismo código (R4); `409 codigo_existente {activo}` si el código es de otro activo |
| `POST /activos` con `copiar_de` | ambos | Duplicar (R6): `{id, codigo, copiar_de, serial?, ubicacion_id?}`; el contador no puede mandar precio (Q3); el admin puede mandarlo para cambiarlo |
| `GET /activos/{id}` | ambos | Ficha de solo lectura |
| `GET /activos?q=&pagina=` | ambos | Búsqueda por código, nombre o serial; 25 por página; orden por `creado_en` descendente |
| `GET /activos/sugerencias?campo=&q=` | ambos | `campo` ∈ `nombre`, `marca`, `modelo`, `subtipo`; hasta 8 valores distintos |

- **Precio (R5):** una sola función arma la respuesta de un activo según el rol; para el contador el campo `precio_compra` no existe (no es `null`). La prueba A2 recorre todas las respuestas del contador buscando cualquier clave o valor de precio.
- **Ubicación (D1, D2):** el alta toma la ubicación con `FOR SHARE` y el `PATCH /ubicaciones` de desactivar cuenta los activos con la ubicación ya bloqueada (`FOR UPDATE`): no queda un activo nuevo en una ubicación recién desactivada.
- **Errores nuevos:** `codigo_invalido` (400), `precio_invalido` (400), `ubicacion_invalida` (400), `codigo_existente` (409, con el activo), `tiene_activos` (409, con la cantidad). Categoría, ubicación u origen de otro tenant: `404`.
- **Evento `creado`:** `datos` con el estado inicial (incluido el precio, que solo leerá el admin en la 005); `usuario_id` del token.

## 5. Web (T6–T10)

- **T6 Alta sin cámara:** `/contar/escribir` resuelve el código real (existe → tarjeta del activo, sin precio para el contador; no existe → alta). `/contar/nuevo` y `/admin/activos/nuevo` guardan de verdad: UUID generado al abrir el formulario (`crypto.randomUUID`) y reutilizado en cada reintento; categoría y ubicación de la API; "Copiar de un parecido" con búsqueda real; error de red con "Reintentar" que reenvía el mismo `id`; `codigo_existente` abre el existente.
- **T7 Autocompletar:** nombre, marca, modelo y subtipo con sugerencias (debounce 250 ms, sin precio).
- **T8 Escáner:** componente `Escaner` con `@zxing/browser` (cámara trasera, formatos 1D comunes: Code 128, Code 39, EAN-13, EAN-8, UPC-A, ITF), estados: pidiendo permiso, leyendo, denegada (→ escribir), sin cámara; antirrebote de 1 s; vibración corta al leer si el teléfono la tiene. `/contar/escanear` lo usa. Prueba con un lector simulado (sin cámara en las pruebas).
- **T9 Lista y ficha:** `/admin/activos` con búsqueda y paginación reales (las pestañas por estado filtran; las acciones de editar y dar de baja quedan deshabilitadas con "llega en la spec 005"); ficha de solo lectura.
- **T10 HTTPS para teléfonos:** `@vitejs/plugin-basic-ssl` activado solo con `VITE_HTTPS=1` y guía corta en `web/README.md` para abrir la web desde el teléfono en la misma red.

## 6. Verificación (T11)

Navegador real contra el backend: escanear (simulado con un video o con la entrada manual), alta en menos de 30 s, duplicar, reintento sin duplicar, contador sin precio en ninguna respuesta de red, `tiene_activos` al desactivar. 375 y 1440 px, consola y axe. Revisión de seguridad (disparador, `GRANT`, precio por rol) y de dominio (código, dinero, una fila por unidad). Guía para la prueba humana con teléfonos reales (A6).

## 7. Dependencias nuevas (Q4)

| Paquete | Versión | Dónde |
|---|---|---|
| `@zxing/browser` | 0.2.1 | web, `dependencies` |
| `@zxing/library` | 0.23.0 | web, `dependencies` (par de `@zxing/browser`) |
| `@vitejs/plugin-basic-ssl` | 2.3.0 | web, `devDependencies` |

Versiones verificadas con `npm view` el 2026-11-14.
