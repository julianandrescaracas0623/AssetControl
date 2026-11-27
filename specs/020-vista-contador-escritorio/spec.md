# Spec 020 — Vista del contador en escritorio

**Estado:** compuertas G1–G3 aprobadas por el humano (2026-11-25). Decisiones del humano (2026-11-25) registradas en P36, P37 y P38 de `docs/05-preguntas-abiertas.md`.

## Problema

En computador el contador usa la interfaz de teléfono (`/contar/**`): no ve la lista de activos, no corrige un dato mal tecleado, no consulta sesiones ni discrepancias, y el alta del escritorio vive solo en `/admin`, que le responde 403. El admin y el contador terminan con pantallas duplicadas. Se quiere una sola web responsive con un marco compartido, donde el contador tenga las capacidades de consulta y corrección descriptiva que el humano decidió, sin que nunca reciba un precio.

## Usuarios

- **Contador** (principal): trabaja en escritorio para registrar, consultar y corregir datos descriptivos; en teléfono sigue contando con la cámara.
- **Admin**: comparte el marco; sus capacidades no cambian (solo cambia la URL base de `/admin` a `/app`, con alias).

## Alcance

### Incluye

- R1. Marco único (barra lateral, cabecera, buscador global, menú de cuenta) generalizando `AdminShell` y `admin-nav.ts`, con `roles` por ítem filtrados con `useRol()`.
- R2. Rutas compartidas bajo `/app/**`; `/admin/**` queda como alias que redirige conservando subruta y query.
- R3. `RequiereAdmin` solo para pantallas exclusivas del admin: Usuarios, Empresa, Ubicaciones, Categorías, Valor e Informe.
- R4. Menú del contador: Inicio, Contar (abre `/contar/escanear`), Activos, Registrar activo, Sesiones, Discrepancias.
- R5. Activos (lista con filtros por búsqueda, estado y ubicación) y ficha, sin precio, sin columna de precio, sin exportar. (Decisión del humano, T4: el filtro por categoría sale de esta spec.)
- R6. Alta en escritorio idéntica a la del admin (`admin/RegistrarActivo.tsx` con `rol='contador'`); en teléfono sigue `contar/Alta.tsx`.
- R7. Edición descriptiva por el contador: solo `nombre`, `categoria_id`, `marca`, `modelo`, `subtipo`, `serial`, `fecha_compra`. Mantiene `If-Match` (412/428) y evento en `activo_evento` con su autor.
- R8. Discrepancias en solo lectura: `GET /sesiones/{id}/discrepancias` abierto al contador; `aplicar` y `descartar` siguen solo admin.
- R9. Sesiones en solo lectura, sin cifras de valor y sin enlace al informe.
- R10. Inicio del contador en escritorio en `/app` con el contenido de P25 sin precios (activos hoy en unidades, avance del conteo abierto, actividad reciente).
- R11. Teléfono sin cambios: `/contar/**` intacto. En computador `/contar` redirige a `/app`, salvo el espacio de conteo `/contar/escanear|escribir|activo/:codigo`.

### No incluye

- Migraciones, cambios de esquema o del modelo de datos (no se crea el campo «notas»).
- Cambios a `precio_al_contar`, al cierre, a los informes o a sus totales congelados.
- Revisión del admin sobre ediciones del contador (decidido: igual que el alta, P11).
- Que el contador mueva, cambie estado, dé de baja, exporte, aplique o descarte discrepancias, abra o cierre sesiones, vea informes o valor.
- Editar `precio_compra`, `codigo`, ubicación o estado desde el rol contador.
- App nativa, offline, dependencias nuevas.
- Resolver P13 (si el contador edita el precio al duplicar) ni P14 (aplicar sobre sesión cerrada).
- Filtro por categoría en la lista de activos: mejora futura para ambos roles (admin y contador), en otra spec (decisión del humano en T4).

## Requisitos (EARS)

1. Cuando un `contador` envía `PATCH /activos/{id}` con `If-Match` válido y solo campos descriptivos permitidos, el sistema debe aplicar el cambio, registrar el evento en `activo_evento` con su autor y responder 200 sin ningún campo de precio.
2. Cuando un `contador` envía `PATCH /activos/{id}` con `precio_compra`, `codigo`, `ubicacion_id` (o `ubicacion*`), `estado` (o `estado*`) u otro campo fuera de la lista, el sistema debe responder 400 sin modificar nada y sin precio en el cuerpo.
3. Cuando falta `If-Match`, el sistema debe responder 428; cuando la versión no coincide, 412. Para el contador, el cuerpo del 412 y del 400 no debe incluir precio. Para el admin no cambia.
4. Cuando un `contador` corrige la categoría de un activo, el sistema debe registrar `categoria_cambiada` y afectar solo cálculos futuros; las sesiones cerradas y sus informes no cambian (ADR-003).
5. Cuando un `contador` pide `GET /sesiones/{id}/discrepancias`, el sistema debe devolver la lista (sesión abierta o cerrada) sin precios ni valores; `POST .../aplicar` y `.../descartar` deben responder 403 al contador.
6. Cuando un `contador` pide `GET /ubicaciones` o `GET /categorias`, el sistema debe responder en solo lectura (ya abiertos a ambos roles); la creación y edición siguen solo admin.
7. Cuando un usuario autenticado abre `/admin/<ruta>?<query>`, la web debe redirigir a `/app/<ruta>?<query>`.
8. Cuando un `contador` abre en la web una pantalla exclusiva del admin (R3), la web debe redirigirlo a `/app` o a Sin permiso; el servidor sigue siendo la autoridad (403).
9. Cuando un `contador` entra en computador, la web debe mostrarle el marco con su menú (R4) y su Inicio en `/app`; en teléfono, su flujo `/contar/**` actual.
10. Cuando se muestra cualquier pantalla al contador, la web no debe renderizar precio, columna de precio, hueco ni «•••»; el servidor no debe enviarlos.
11. Cuando un `contador` entra a `/contar/escanear`, `/contar/escribir` o `/contar/activo/:codigo` en computador, la web debe mostrar el espacio de conteo sin redirigir.
12. Si el `412` ocurre al editar, la web debe conservar lo escrito por el usuario y ofrecer reintentar con la versión nueva.

## Criterios de aceptación

- Contador con `PATCH` válido: 200, evento con su autor, cero claves de precio en el JSON; con `precio_compra`/`codigo`/ubicación/estado: 400 y el activo no cambia.
- `412` y `428` conservados; cuerpo del 412 sin precio para contador (prueba que recorre el JSON buscando claves de precio) y con precio para admin como hoy.
- Admin: `PATCH`, `mover`, `estado`, `baja` sin cambios; contador en `mover`, `estado`, `baja` y `exportar`: 403.
- Contador: `GET discrepancias` 200 sin precios en las tres variantes de filtro; `aplicar`/`descartar` 403; un contador de otro tenant: 404.
- Cada endpoint tocado trae prueba de aislamiento por tenant y de rol. `backend/openapi.yaml` actualizado y tipos regenerados.
- Web (contador, 1440 px): marco con su menú, Inicio en `/app`, Activos, Registrar activo (`RegistrarActivo`), Sesiones y Discrepancias; ninguna con precio en el DOM.
- `/admin/...?x=1` redirige a `/app/...?x=1`; contador en Usuarios, Empresa, Ubicaciones, Categorías, Valor o Informe: sin acceso.
- Teléfono (375 px): `/contar/**` sin regresión; en escritorio `/contar` redirige a `/app` salvo el espacio de conteo.
- Suites backend y web verdes; ruff, lint y typecheck limpios; QA en navegador a 375 y 1440 px con consola limpia.

## Reglas de dominio

- El contador nunca recibe precio: 200, 400, 412, historial, listas, autocompletado y sugerencias. El alta sigue exigiendo `precio_compra` (P13) y el contador no lo ve después.
- Dinero en COP, `NUMERIC(14,2)`/`Decimal`, nunca `float`.
- Verificaciones inmutables y sesión cerrada inmutable (`409 sesion_cerrada`); totales congelados con `precio_al_contar` (ADR-003).
- Nada se borra; cada edición deja evento en `activo_evento` con autor.
- El `serial` no es único ni sirve para deduplicar; corregirlo no valida unicidad.
- Roles en servidor; ocultar el menú no es seguridad.
- El `codigo` sigue inmutable.

## Riesgos

- Fuga de precio por `_con_version` y `_error` (hoy `con_precio=True`) y por el 412 y el 400. Mitigación: depender de `_es_admin()` y prueba que recorre el JSON.
- `/admin` fijo en rutas, migas, enlaces, `rutaInforme`, `entradaDeRuta` y `buscarEnNav`. Mitigación: helper único de rutas y alias.
- Un cambio de categoría hecho por el contador mueve el «valor actual por categoría» del Inicio del admin (comportamiento vigente de R7, no del informe).
- Regresión del conteo en teléfono por la redirección de `/contar` en escritorio. Mitigación: pruebas del criterio de «escritorio» y QA a 375 px.
- El contador puede cambiar `serial` y categoría sin revisión (decisión del humano); el rastro es `activo_evento`.

## Preguntas abiertas

- Ninguna de producto bloquea la spec: P36, P37 y P38 están decididas por el humano.
- Contradicciones documentales por actualizar (no son preguntas): P11, P25, docs/01 línea 13, docs/08 §4.1 (línea 150) y §4.2.1, pregunta 14. Detalle en `cambios-docs.md`.
- P13 (precio al duplicar por el contador) y P14 (discrepancias sobre sesión cerrada) siguen abiertas y esta spec no las toca: el alta del contador no cambia y `aplicar` sigue solo admin.
- [PENDIENTE, menor, no bloquea el backend] `GET /ubicaciones` devuelve solo ubicaciones activas a quien no es admin (`solo_activas`). El filtro por ubicación del contador no ofrecerá ubicaciones desactivadas aunque tengan activos (P19 abierta). Recomendación: aceptarlo en la 020. El humano confirma.
