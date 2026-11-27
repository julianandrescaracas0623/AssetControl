# Tasks 020 — Vista del contador en escritorio

Siete tareas, cada una ≤ 1 día, tests primero. Verificación común: `uv run ruff check .` (backend) y `npm run lint` + `npm run typecheck` (web). Backend: `cd backend && PGHOSTADDR=127.0.0.1 uv run --env-file ../.env pytest -q <archivo>`. Web: `cd web && npm test -- <patrón>`. La primera tarea produce algo ejecutable: un `PATCH` del contador que funciona. Estado: G1–G3 aprobadas por el humano (2026-11-25); T1–T3 implementadas.

## T1 — Backend: edición descriptiva por el contador (R7; req. 1–4)

- **Resultado:** el contador edita nombre, categoría, marca, modelo, subtipo, serial y fecha de compra con `If-Match`; 400 con `precio_compra`, `codigo`, ubicación, estado u otro campo; 200, 400 y 412 sin precio; `activo_evento` con autor y `categoria_cambiada`; admin sin cambios; OpenAPI y tipos actualizados.
- **Archivos probables:** `backend/app/activos/routes.py` (`editar`, `_con_version`, `_error`), `backend/app/activos/cambios.py` (`EDITABLES_CONTADOR`, `edicion(body, rol)`), `backend/tests/test_activos_cambios.py`, `backend/openapi.yaml`, `web/src/api/` (tipos).
- **Criterio de terminado:** pruebas rojas primero y luego verdes, incluidos recorrido recursivo del JSON sin claves de precio (200, 400, 412), 428/412, 403 del contador en mover/estado/baja/exportar, 404 entre tenants y sin regresión del admin.
- **Verificación:** `uv run pytest -q tests/test_activos_cambios.py` y `uv run ruff check .`.
- **Dependencia:** ninguna.
- **Agente y revisión:** implementer; reviewer + security-reviewer (rol y fuga de precio) + domain-guardian (precio, ADR-003, eventos).

## T2 — Backend: discrepancias en solo lectura (R8; req. 5–6)

- **Resultado:** `GET /sesiones/{id}/discrepancias` abierto al contador sin precios ni valores (sesión abierta y cerrada, con los filtros existentes); `aplicar` y `descartar` siguen 403 al contador; `GET /ubicaciones` y `GET /categorias` fijados en solo lectura para ambos roles por prueba.
- **Archivos probables:** `backend/app/conteo/routes.py`, `backend/tests/test_conteo_discrepancias.py` (o el archivo de pruebas de discrepancias existente), `backend/tests/` de catálogo, `backend/openapi.yaml`.
- **Criterio de terminado:** pruebas rojas primero; el contador recibe 200 sin claves de precio o valor (recorrido recursivo); `aplicar`/`descartar` 403; 404 entre tenants; contador 403 en crear/editar ubicaciones y categorías.
- **Verificación:** `uv run pytest -q tests/test_conteo_discrepancias.py` (ajustar al archivo real) y `uv run ruff check .`.
- **Dependencia:** ninguna técnica (se hace después de T1 por orden).
- **Agente y revisión:** implementer; reviewer + security-reviewer + domain-guardian.

## T3 — Web: marco compartido, menú por rol, `/app/**`, alias y guardas (R1–R4, R11; req. 7–9, 11)

- **Resultado:** `AppShell` y `APP_NAV` con `roles` por ítem; `rutaApp` sin `/admin` fijo; `/app/**` con grupo `RequiereAdmin` solo para Usuarios, Empresa, Ubicaciones, Categorías, Valor e Informe; `/admin/*` redirige a `/app/*` con query; en escritorio `/contar` redirige a `/app` salvo el espacio de conteo; Inicio del contador en `/app` (contenido P25 sin precios); buscador global y menú de cuenta en ambos roles; entrada «Contar» abre `/contar/escanear`.
- **Archivos probables:** `web/src/components/app/AdminShell.tsx` (renombrar a `AppShell`), `web/src/components/app/admin-nav.ts` (`APP_NAV`), `web/src/router.tsx`, `web/src/routes/admin/RequiereAdmin.tsx`, `web/src/routes/InicioPorRol.tsx`, `web/src/routes/contar/Inicio.tsx`, `web/src/routes/contar/Escritorio.tsx`, sus pruebas.
- **Criterio de terminado:** pruebas rojas primero; contador a 1440 px ve el marco con su menú (R4) y el admin el menú actual; `/admin/x?q=1` → `/app/x?q=1`; contador redirigido en pantallas exclusivas; `/contar/**` a 375 px intacto; búsqueda de `/admin` fijo sin restos.
- **Verificación:** `npm test -- router AdminShell admin-nav InicioPorRol Escritorio`, `npm run lint`, `npm run typecheck`.
- **Dependencia:** T1 y T2 solo para integración.
- **Agente y revisión:** implementer; reviewer + security-reviewer (guardas de rol).

## T4 — Web: Activos y FichaActivo por rol (R5, R7; req. 10, 12)

- **Resultado:** lista de activos con filtros (búsqueda, estado y ubicación; el de categoría queda como mejora futura para ambos roles, fuera de esta spec) y ficha para el contador sin precio, sin columna, sin exportar; «Editar» limitado a los siete campos; sin mover, estado ni baja; el 412 conserva lo escrito.
- **Archivos probables:** `web/src/routes/admin/Activos.tsx`, `web/src/routes/admin/FichaActivo.tsx`, `web/src/components/app/EditarActivo.tsx`, `web/src/lib/cambiosActivo.ts`, sus pruebas.
- **Criterio de terminado:** pruebas rojas primero; con rol contador no aparece «precio», columna ni «•••» en el DOM; la edición solo envía campos permitidos; admin sin regresión.
- **Verificación:** `npm test -- Activos FichaActivo EditarActivo`, lint, typecheck.
- **Dependencia:** T1, T3.
- **Agente y revisión:** implementer; reviewer + domain-guardian.
- **Pendiente heredado de la revisión de T3 (sin implementar):** acciones del admin que hoy ve el contador y que deben ocultarse por rol: en `Activos.tsx`, «Exportar» y el precio (columna y celdas, ~líneas 81, 117 y 171); en `FichaActivo.tsx`, «Mover», cambiar estado, «Dar de baja» y el bloque de precio (~313-327). Presentación: la API ya responde 403 o no envía el precio.

- **Cierre (2026-11-26):** `rol` obligatorio en `cuerpoDeEdicion`, `camposCambiados`, `useEdicionActivo` y `EditarActivo` (falla cerrado, sin defecto `'admin'`). Defensa en dos capas: `paraRol` (`web/src/lib/eventos.ts`) quita `precio_cambiado` y los datos de precio del historial (`HistorialActivo`) y de la actividad reciente a quien no es admin. Regresión con el doble `filtraPrecio: false` (lista, tarjeta, ficha con historial, edición y 412). `valorVisible('precio')` en `EditarActivo.tsx` se deja: el admin la usa en el aviso del 412. Aviso nuevo del 412 para el contador pendiente de aprobación en docs/08 (ver `cambios-docs.md`).

## T5 — Web: Registrar activo unificado para el contador (R6)

- **Resultado:** en escritorio el contador usa `admin/RegistrarActivo.tsx` con `rol='contador'` (precio al alta, autocompletado y duplicar sin mostrar el precio ajeno, foto); en teléfono sigue `contar/Alta.tsx`.
- **Archivos probables:** `web/src/routes/admin/RegistrarActivo.tsx`, `web/src/routes/contar/Alta.tsx`, `web/src/router.tsx`, `web/src/routes/contar/altaEscritorioKit.test.tsx`, `web/src/routes/AltaActivo.test.tsx`.
- **Criterio de terminado:** pruebas rojas primero; el contador da de alta y duplica en escritorio, no ve el precio después ni en el duplicado; el alta en teléfono no cambia.
- **Verificación:** `npm test -- RegistrarActivo AltaActivo altaEscritorio`, lint, typecheck.
- **Dependencia:** T3.
- **Agente y revisión:** implementer; reviewer + domain-guardian.
- **Pendiente heredado de la revisión de T3 (sin implementar):** el precio en `RegistrarActivo.tsx` (~208-215) para el contador según R6; redirección en escritorio de `/contar/nuevo` a la pantalla unificada del marco.

- **Implementación (2026-11-26, pendiente de revisión):** `RegistrarActivo` toma el rol de la sesión, lee `?codigo=` y la sala de trabajo; para el contador, ayuda del precio del alta del conteo, resumen sin precio, aviso «Se copia de …» al duplicar (solo ubicación y serial) y sin «Varias unidades iguales». `/contar/nuevo` en el computador redirige a `/app/activos/nuevo` con su query (`AltaConteo`, `routes/app/rutasApp.tsx`); el conteo de escritorio enlaza directo. Textos para docs/08 en `cambios-docs.md`. Deuda: la rama de escritorio de `contar/Alta.tsx` queda sin uso; `contar/Inicio.tsx` (`Registrar`) sigue enlazando a `/contar/nuevo` (redirige; T6).
- **Cierre (2026-11-26):** aprobada por reviewer y domain-guardian (security-reviewer no aplica: presentación y redirección interna). Menores aplicados: `?codigo=` pasa por `normalizarCodigo` (un código inválido no se precarga y el cursor queda en el código); «Volver al conteo» (a `/contar/escanear`) en el pie, en lugar de «Cancelar», y en «Activo creado» cuando se llega desde el conteo (`state { desde: 'conteo' }` del enlace «Crear activo con este código»); `paraRol` quita también las claves con «precio» de `datos.campos` para quien no es admin, con pruebas, y prueba de `useRol()` sin sesión → `'contador'`.
- **Deuda de T5:** (1) la rama de escritorio de `contar/Alta.tsx` queda sin uso: borrarla en una tarea posterior; (2) `RegistrarActivo` no lee `?ubicacion=` (ningún enlace actual lo usa); (3) redimensionar de teléfono a escritorio en `/contar/nuevo` con datos a medio escribir redirige y pierde lo tecleado (sin prueba); (4) el redirect `/contar/nuevo` → `/app/activos/nuevo` no lleva `state`, así que solo el enlace directo del conteo de escritorio muestra «Volver al conteo».

## T6 — Web: Inicio, Sesiones y Discrepancias de lectura (R8–R10)

- **Resultado:** Inicio del contador en `/app` sin precios; Sesiones sin enlace al informe ni cifras de valor; Discrepancias solo lectura sin botones aplicar ni descartar.
- **Archivos probables:** `web/src/routes/contar/Inicio.tsx`, `web/src/routes/admin/Sesiones.tsx`, `web/src/routes/admin/DetalleSesion.tsx`, `web/src/routes/admin/Discrepancias.tsx`, sus pruebas.
- **Criterio de terminado:** pruebas rojas primero; sin precio, valor, enlace al informe ni acciones para el contador; admin sin regresión.
- **Verificación:** `npm test -- Inicio Sesiones Discrepancias DetalleSesion`, lint, typecheck.
- **Dependencia:** T2, T3.
- **Agente y revisión:** implementer; reviewer + domain-guardian + security-reviewer.
- **Pendiente heredado de la revisión de T3 (sin implementar):** ocultar al contador abrir y cerrar sesión y los enlaces al informe en `Sesiones.tsx` (~41, 365) y en `DetalleSesion.tsx`, y «Aplicar»/«Descartar» en `Discrepancias.tsx`; redirección en escritorio de `/contar/pendientes` y del historial (`/contar/activo/:codigo/historial`) a su pantalla del marco; reforzar los dos tests de `gestionKit.test.tsx` que dependen del encabezado con `findByRole('heading', …)`.

- **Implementación (2026-11-26, pendiente de revisión):** `Sesiones.tsx` y su detalle con `useRol()` (falla cerrado: sin sesión, solo lectura): el contador no ve «Abrir sesión» (ni el diálogo montado), «Cerrar sesión», «Informe» ni «Ver informe»; el nombre de una cerrada lleva a su detalle en lugar del informe; textos propios sin abrir/cerrar. El detalle acepta `?ubicacion=` y filtra los pendientes («Pendientes por verificar en …» y «Ver todas las ubicaciones»), para los dos roles. `Discrepancias.tsx`: el contador tiene pestañas Por resolver, Resueltas y Todas, sin casillas, lote, Aplicar, Descartar ni Confirmar de desfase; columnas extra «Está ahora en» y «Resolvió» (y sus líneas en la tarjeta del teléfono). El admin conserva sus dos pestañas. En el computador `/contar/pendientes` redirige al detalle de la sesión abierta con su query (sin sesión abierta o con error, a Sesiones) y `/contar/activo/:codigo/historial` a `/app/activos/:codigo`; el Inicio del contador en `/app` enlaza directo a esas pantallas. En el teléfono, `/contar/**` intacto. Doble de pruebas: `GET discrepancias` abierto a ambos roles (como el servidor tras T2), `resoluciones` expuesto, y con `filtraPrecio: false` manda valor en Inicio, detalle y discrepancias. Pruebas en `routes/admin/sesionesContador.test.tsx`. Textos para docs/08 en `cambios-docs.md`.
- **Estado (2026-11-26):** HECHA y aprobada (reviewer, domain-guardian y security-reviewer, sin bloqueantes).
- **Deuda menor de T6:** (1) sin prueba web del caso «sin sesión» (`useRol()` sin datos, solo lectura); (2) sin prueba del error y reintento al cargar discrepancias y pendientes del contador; (3) sin prueba de `?ubicacion=` desconocida (no debe llamar a `/pendientes` con ese id); (4) sin prueba backend explícita de 404 cross-tenant de `GET discrepancias` y `GET pendientes` como contador (confirmar si T2 la cubre; búsqueda rápida en `backend/tests` no la encontró nombrada).

## T7 — Designer: pasada visual a 375 y 1440 px

- **Resultado:** revisión visual del marco compartido, el menú del contador y las pantallas de T4–T6 en ambos anchos, con capturas, consola limpia y axe solo si está instalado; ajustes dentro de `web/`; cambios de diseño informados para `docs/08`.
- **Archivos probables:** `web/src/components/app/`, `web/src/routes/`, `specs/020-vista-contador-escritorio/capturas/`.
- **Criterio de terminado:** contador y admin sin desborde a 375 px, jerarquía correcta a 1440 px, sin precio visible para el contador, `npm test`, lint y typecheck verdes.
- **Verificación:** skill `browser-qa` a 375 y 1440 px; `npm test`.
- **Dependencia:** T3–T6.
- **Agente y revisión:** designer; reviewer.
- **Estado (2026-11-26):** HECHA, aprobada por el reviewer (sin bloqueantes) y subida a develop en c4a502e. Foco de pestañas, enlaces en avisos y ajustes visuales (`Pestanas`, `Aviso`, `FormularioAlta`, `Sesiones`). Web: 101 archivos / 1466 pruebas, lint y typecheck limpios.
- **Deuda de T7:** (1) ~~sin prueba backend de aislamiento entre empresas para `GET /sesiones/{id}/pendientes`~~ **resuelta (2026-11-26)**: `test_pending_is_tenant_scoped` en `backend/tests/test_discrepancias_api.py` (otro tenant, ambos roles: 404 `no_encontrado` sin datos de A; sesión propia de B con `ubicacion_id` de A: 200 lista vacía; contador de A con `ubicacion_id` no UUID: 400); solo pruebas, sin cambios de producción; (2) la ayuda «El cursor empieza aquí» del alta es inexacta cuando el código viene del conteo (decide el humano); (3) el «▼» que pinta Chrome en el campo Nombre; (4) error `flushSync` de Radix/cmdk en consola; (5) axe sin instalar.
- **Deuda e2e (desde 602f1e7/2d2a643) — resuelta (2026-11-26):** `web/e2e/flujo.spec.ts` y `web/e2e/plataforma.spec.ts` buscaban «Correo de la persona» sin abrir el diálogo de invitación. Ahora pulsan «Invitar» y rellenan, envían y leen el «Enlace de invitación» dentro del diálogo «Invitar a una persona». Solo pruebas, sin cambios de producción. `npm run e2e`: 5/5; lint y typecheck limpios.
