# Spec 003 — Ubicaciones y categorías

> **Estado:** Implementada (T1–T8, 2026-11-14), aprobada (G1–G3, 2026-11-14) con Q1–Q4 en la opción recomendada. Fecha: 2026-11-14. Depende de la spec 002 (acceso, hecha) y de la 002b (web con sesión, hecha). Módulo M2 completo y CU-CAT-09 de `docs/07`. Plan en `plan.md`, tareas en `tasks.md`.

## Problema

Para registrar y contar activos hace falta saber **dónde** está cada uno y **qué** es. Hoy la base no tiene `ubicacion` ni `categoria` y las pantallas usan listas ficticias. El Excel de la clínica mezcla nombres ("Mobiliaria", "Mobiliario", "Inmobiliaria") y ubica por texto libre; el sistema necesita listas cerradas por clínica, elegidas con un toque (cero digitación al contar).

## Usuarios

- **Admin:** crea y ordena la jerarquía sede > sala > box, renombra y desactiva ubicaciones, y mantiene la lista de categorías.
- **Contador:** solo elige una ubicación activa en un selector (inicio del conteo y, en specs siguientes, alta y verificación).

## Alcance

- **Incluye:** tablas `ubicacion` y `categoria` (migración `0006`) con RLS por tenant; API para listar, crear, renombrar y activar/desactivar ubicaciones y para listar, crear y renombrar categorías, más cargar las categorías sugeridas; contrato OpenAPI y tipos; pantallas `/admin/ubicaciones` y `/admin/categorias`; el selector "Estás contando en" del inicio de conteo con datos reales; pruebas de aislamiento y de rol.
- **No incluye:** activos (spec 004; por eso aún no hay regla sobre desactivar una ubicación con activos), mover ubicaciones entre padres, borrar (nada se borra físicamente), subtipos de categoría (P8 los menciona como texto libre del activo: spec 004), importar del Excel, conectar las demás maquetas (alta, verificar, informe) a estos datos.

## Requisitos (EARS)

1. **R1 Aislamiento.** Cuando cualquier rol lea o escriba ubicaciones o categorías, el sistema debe limitarse al tenant del token (RLS forzada con `tenant_isolation` y filtro en la capa de datos); un `id` de otro tenant responde `404 no_encontrado`, igual que uno inexistente.
2. **R2 Jerarquía (Q1).** Cuando el admin cree una ubicación, el sistema debe exigir: `sede` sin padre; `sala` con padre `sede`; `box` con padre `sala`; el padre activo y del mismo tenant. Así no hay ciclos por construcción. El padre no se cambia después.
3. **R3 Nombres (Q3).** Cuando el admin cree o renombre una ubicación o categoría, el nombre debe cumplir la regla de nombres visibles (H-3: NFC, 1–120 caracteres, sin invisibles ni control, con letras o números) y ser único sin distinguir mayúsculas ni tildes: entre hermanas en ubicaciones y en todo el tenant en categorías. Duplicado → `409 nombre_duplicado`.
4. **R4 Desactivar (Q2).** Cuando el admin desactive una ubicación, el sistema debe rechazarlo con `409 tiene_hijas_activas` si tiene hijas activas; reactivar exige el padre activo (`409 padre_inactivo`). Una ubicación inactiva no aparece en el selector ni admite hijas nuevas. La regla con activos vigentes la fija la spec 004.
5. **R5 Lectura.** Mientras haya sesión, ambos roles deben poder listar ubicaciones (el contador solo las activas) y categorías; solo el admin crea, renombra o desactiva (`403 prohibido` al contador, comprobado en el servidor).
6. **R6 Categorías iniciales (Q4).** Cuando el admin pida cargar las sugeridas, el sistema debe crear las que falten de la lista de P8 (Mobiliario, Electrónica, CPU, Periféricos, Electrodomésticos, Biomédicos) sin duplicar las existentes; repetir la petición no cambia nada. Las categorías no se borran ni desactivan en esta spec (no hay activos que las usen todavía).
7. **R7 Selector.** Cuando el contador abra el inicio de conteo, el selector "Estás contando en" debe mostrar las salas y boxes activos reales agrupados por sede, con su ruta ("Consultorios › Box 2"), como el diseño aprobado de `docs/08`, a 375 px y 1440 px, sin digitar y con búsqueda por nombre. Si una ubicación de nivel sede puede recibir activos lo decide la spec 004.

## Criterios de aceptación

- A1: migración `0006` con `ubicacion` y `categoria`, RLS habilitada y forzada, `tenant_isolation` `TO` el rol de la aplicación, sin `DELETE` para nadie salvo el dueño; la prueba de catálogo de RLS las incluye en sus listas cerradas.
- A2: pruebas de API: jerarquía (R2) con cada combinación inválida, duplicados (R3), desactivar y reactivar (R4), `404` para el `id` de otro tenant, `403` para el contador en toda escritura, idempotencia de las sugeridas (R6).
- A3: el contrato OpenAPI cubre los endpoints nuevos y las pruebas de `test_openapi.py` validan sus respuestas reales; la web regenera tipos.
- A4: `/admin/ubicaciones`, `/admin/categorias` y el selector del inicio de conteo funcionan contra el backend real a 375 px y 1440 px, sin desbordes, sin errores de consola y sin violaciones axe WCAG 2.1 AA (skill `browser-qa`).

## Reglas de dominio y riesgos

- Una ubicación vigente por activo y desglose por el nodo exacto (R4/P20 de `docs/03`): por eso un `box` y una `sala` son ubicaciones válidas por igual para un activo.
- Riesgo: renombrar cambia el rótulo de informes ya cerrados (que guardan el `id`, `docs/03` §desglose); se acepta y queda la nota `[PENDIENTE]` de la spec 008.
- Riesgo: comparar nombres "sin tildes" en Python y en PostgreSQL puede diferir; se resuelve con una clave de comparación calculada en la aplicación y guardada (`nombre_clave`) con índice único, no con colación de la base.

## Decisiones (2026-11-14, humanas)

| Pregunta | Decisión |
|---|---|
| Q1 Jerarquía | Estricta: sede sin padre, sala bajo sede, box bajo sala. |
| Q2 Desactivar con hijas activas | Rechazar (`409 tiene_hijas_activas`). |
| Q3 Nombres | Únicos sin distinguir mayúsculas ni tildes: entre hermanas (ubicaciones) y en el tenant (categorías). |
| Q4 Categorías iniciales (P8) | Botón "Cargar las 6 sugeridas", idempotente; sin tocar `acceso.crear_tenant`. |
| `docs/03` | El implementer aplica en T1 los cambios de `plan.md` §2 (autorizado con la aprobación). |

## Preguntas abiertas

Ninguna para esta spec. Para la 004: si una sede puede recibir activos y qué pasa al desactivar una ubicación con activos vigentes.
