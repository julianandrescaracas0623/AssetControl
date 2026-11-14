# Tasks 001b — Sistema de diseño y app shell

> **Estado:** Aprobada (G1–G3, 2026-11-13) por el humano, con D1–D5 decididos según la recomendación. Máximo 10 tareas, cada una ≤ 1 día, una a la vez, **tests primero**. Solo se instalan las dependencias de `plan.md` §3, tras aprobar D1. Las capturas se toman en navegador real a 375 px y 1440 px (skill `browser-qa`) y se comparan con el lienzo aprobado.

---

### T1 — Tema "Grafito y Cobalto" y fuente

- **Resultado:** `index.css` con las variables de `plan.md` §2 y `@theme inline` para las propias; `components.json` con `baseColor` `zinc`; Geist y Geist Mono importadas desde `@fontsource-variable/*`; la pantalla `/health` ya usa el tema.
- **Tests primero:** `src/theme.test.ts`: (a) sin colores hex ni `rgb()` fuera de `index.css` (A1); (b) contraste WCAG de los pares de `plan.md` §2 (A2).
- **Archivos probables:** `web/src/index.css`, `web/components.json`, `web/src/main.tsx`, `web/package.json`, `web/package-lock.json`, `web/src/theme.test.ts`.
- **Verificación:** `cd web && npm test && npm run build` + red del navegador sin dominios externos (A3).
- **Depende de:** D1 aprobado.
- **Riesgo:** la CLI de shadcn reescribe `index.css`; se revisa el diff antes de seguir.
- **Implementada (2026-11-13), pendiente de revisión del `reviewer` y sin commit:**
  - `index.css`: tema completo en hex (variables de shadcn + `--brand*`, `--success*`, `--warning*`, `--destructive-soft/-border`) expuesto con `@theme inline`; sin bloque `.dark` (fuera del MVP); `prefers-reduced-motion`. `components.json`: `baseColor` `zinc`.
  - Fuente: `@fontsource-variable/geist` 5.3.0 y `@fontsource-variable/geist-mono` 5.3.0 (D1), importadas en `main.tsx`; `--font-sans` y `--font-mono` con pila del sistema de respaldo.
  - Prueba: `src/theme.node.test.ts` (no `theme.test.ts`: lee archivos con `node:fs`, así que la tipa `tsconfig.node.json` y `tsconfig.app.json` la excluye). Cubre A1 (sin colores literales fuera de `index.css`), fuente autoalojada (A3) y 18 pares de contraste (A2). Escrita antes del tema: 19 fallos en rojo, luego 25/25 en verde.
  - `package-lock.json`: solo +20 líneas (las dos fuentes). Se conservaron los campos `libc` del lock original, que npm 10 borra.
  - Verificación: `npm test` 25/25, `npm run lint`, `npm run typecheck` y `npm run build` en verde; `dist/` con las `.woff2` y sin referencias a dominios externos; en Chromium, `/health` a 375 y 1440 px carga solo `localhost`, usa "Geist Variable" y no tiene scroll horizontal.
  - Nota: se verificó con Node 22 (VM de la sesión, `--engine-strict=false`); el proyecto exige Node 24, que confirman la CI y el equipo del humano.
  - Pendiente A2: medir el contraste con Lighthouse/DevTools en la web real (T10).
  - **Revisión (2026-11-13): CAMBIOS → corregidos.** (I-1) foco base `outline-ring/50` (2,3 : 1) pasa a `outline-ring` opaco, con prueba; el foco de `button`/`badge` (`ring-ring/50`) se corrige en T2, que ya toca las variantes. (I-2) la prueba de A1 ahora también rechaza clases de la paleta de Tailwind (`bg-red-500`, `text-white`) y colores arbitrarios (`bg-[…]`). Menores: `--sidebar-accent` y la retirada de `--chart-*` documentados en `plan.md` §2. Los falsos positivos de `#123` en comentarios se aceptan (hoy no ocurren).

### T2 — Componentes base de shadcn/ui

- **Resultado:** componentes de `plan.md` §3 añadidos con la CLI; variantes `success`, `warning`, `brand`, `neutral` y `dark` en `Badge`, y `info`, `warning`, `success` en `Alert`; ruta de desarrollo `/dev/componentes` con la galería del sistema (equivalente a la página "Sistema visual" del lienzo).
- **Tests primero:** render de cada variante con su rol accesible y su texto; botones de solo ícono con `aria-label`; ningún componente usa foco con transparencia (`ring-ring/NN`, `ring-destructive/NN`): anillo sólido de 2 px con 2 px de separación (`plan.md` §2, hallazgo de la revisión de T1).
- **Archivos probables:** `web/src/components/ui/*`, `web/src/routes/dev/Componentes.tsx`, pruebas junto a cada variante.
- **Verificación:** `cd web && npm test && npm run lint && npm run typecheck` + capturas de la galería.
- **Depende de:** T1.
- **Riesgo:** paquetes no previstos; se para y se pregunta.
- **Implementada (2026-11-13), revisada (APROBADO con menores):**
  - Pruebas primero (en rojo antes de la CLI): `components/ui/ui.node.test.ts` (24 componentes presentes, solo dependencias aprobadas y exactas, foco sólido), `components/ui/variants.test.tsx` y `routes/dev/Componentes.test.tsx`. Sin `@testing-library/jest-dom` (no aprobada). Total: 69/69 en verde; lint, typecheck y build en verde.
  - CLI ejecutada por el humano en su equipo (`ui.shadcn.com` está bloqueado en la sesión): `npx shadcn@4.23.0 add …`. Creó además `input-group` (lo pide `command`) y `hooks/use-mobile.ts` (lo pide `sidebar`).
  - La CLI añadió `next-themes` (no aprobado, lo pide `sonner` para modo oscuro): se quitó y `sonner.tsx` usa `theme="light"` (sin modo oscuro en el MVP). `cmdk` y `sonner` quedaron con versión exacta (1.1.1 y 2.0.8). El lock conserva el formato de npm 11.
  - Foco: en todos los componentes, `ring-3`/`ring-[3px]` + `ring-ring/50` pasan a `ring-2 ring-offset-2 ring-offset-background ring-ring` (cierra el hallazgo I-1 de T1); se quitan los `dark:` de foco. Comprobado en Chromium: anillo blanco de 2 px + cobalto de 2 px, también sobre el botón principal oscuro.
  - Tema: fondos de diálogo, `alert-dialog` y `sheet` de `bg-black/10` a `bg-foreground/40`; barra de `progress` en cobalto (`bg-brand`, docs/08: el acento marca el avance); variantes `success`, `warning`, `destructive`, `brand`, `neutral`, `dark` en `Badge` e `info`, `success`, `warning`, `destructive` en `Alert` (el color del ícono va en cada variante, no en la base).
  - `hooks/use-mobile.ts` reescrito con `useSyncExternalStore` (la versión de la CLI fallaba la regla `react-hooks/set-state-in-effect`).
  - Galería en `/dev/componentes` (secciones Botones, Campos, Insignias, Avisos, Superficies); `main.tsx` la elige por `pathname` de forma provisional hasta el enrutado de T3. Sin scroll horizontal a 375 y 1440 px.
  - Menores para tareas siguientes: jsdom no implementa `matchMedia` (las pruebas de la barra lateral en T4 deben simularlo); el botón `destructive` de shadcn es de fondo suave y la acción destructiva **confirmada** de `alert-dialog` debe ir en sólido (T8).

### T3 — Enrutado y pantallas de sistema

- **Resultado:** `react-router` con `/admin/**`, `/contar/**`, `/login` (marcador), `/health`, "Sin permiso" y "No encontrado"; rol y estado simulados por parámetros de URL; banda "Datos ficticios".
- **Tests primero:** cada ruta renderiza su pantalla; ruta inexistente → "No encontrado"; `?rol=contador` en `/admin` → "Sin permiso".
- **Archivos probables:** `web/src/main.tsx`, `web/src/routes/*`, `web/src/lib/simulacion.ts`.
- **Verificación:** `cd web && npm test && npm run build`.
- **Depende de:** T2.
- **Riesgo:** confundir el rol simulado con autorización; se documenta en el código que la autorización es del servidor (002b).
- **Implementada (2026-11-13), revisada (APROBADO con menores):**
  - `react-router` 8.5.1 exacto (D1); trae como transitivas `cookie-es` 3.1.1 y `@remix-run/route-pattern` 0.22.x (en el lock, sin entrada en `package.json`). Lock con formato de npm 11 conservado (+43 líneas).
  - `src/router.tsx` (`routes`, usadas por `main.tsx` con `createBrowserRouter` y por las pruebas con `createMemoryRouter`): `/` → `/admin`, `/health` (pantalla de la fundación), `/login` (marcador de 002b), `/dev/componentes`, `/admin` (requiere rol simulado admin, si no "Sin permiso"), `/contar`, `*` → "No encontrado". Se retira el `pathname` provisional de T2.
  - `lib/simulacion.ts`: `?rol=admin|contador` y `?estado=exito|cargando|vacio|error`, con valores desconocidos ignorados; comentado como solo presentación.
  - Banda "Datos ficticios" (con el rol simulado) en todas las maquetas; pantallas de sistema con objetivos de 44 px por debajo de `md`.
  - Pruebas primero: `router.test.tsx` (9) y `lib/simulacion.test.ts` (3), en rojo antes de implementar; total 81/81, lint, typecheck y build en verde. En Chromium, las cinco rutas muestran su título a 375 y 1440 px sin scroll horizontal.
  - Menores: `/` → `/admin` es provisional hasta que 002b redirija por rol tras el login; el hosting de producción necesitará *fallback* de SPA a `index.html` (spec de despliegue); los botones de shadcn miden 32 px y los shells (T4, T6) deben asegurar 44 px en celular.

### T4 — `AdminShell`

- **Resultado:** barra lateral con grupos y entradas de `docs/08` §4.1 (incluida Registrar activo), colapsable a íconos con tooltip y estado recordado; `sheet` por debajo de `md`; encabezado con migas de pan, botón del buscador y menú de usuario; contenido con ancho máximo (D2).
- **Tests primero:** entrada activa con `aria-current="page"`; colapso persistido; `sheet` en ancho móvil (A4).
- **Archivos probables:** `web/src/components/app/AdminShell.tsx` y prueba.
- **Verificación:** `cd web && npm test` + capturas a 375 px y 1440 px, barra expandida, colapsada y menú móvil abierto.
- **Depende de:** T3.
- **Riesgo:** `sidebar` de shadcn con muchas piezas; si pasa de un día, el menú móvil se separa con `/sdd-change`.
- **Implementada (2026-11-13), revisada (APROBADO con menores):**
  - `components/app/AdminShell.tsx` sobre `sidebar` de shadcn: grupos y entradas de `docs/08` §4.1 desde una sola fuente (`components/app/admin-nav.ts`, también usada por las migas y las pantallas pendientes), incluida **Registrar activo** (`/admin/activos/nuevo`, D3); colapsable a íconos con tooltip; estado recordado con la cookie `sidebar_state` de shadcn (se lee al montar); menú tipo `sheet` por debajo de `md` con enlaces de 44 px; migas de pan (en celular solo la última); botón del buscador (se conecta en T5); menú de usuario ficticio con "Ir a contar" y "Cerrar sesión" (→ `/login`); contenido con ancho máximo de 1320 px (D2). Marca provisional en `components/app/Logo.tsx`.
  - Rutas de admin aún no construidas (`activos`, `activos/nuevo`, `ubicaciones`, `categorias`, `sesiones`, `discrepancias`, `valor`, `usuarios`) muestran "Pantalla en preparación" y qué spec o tarea las trae. `RequiereAdmin` pinta la banda y "Sin permiso" fuera del shell.
  - `sidebar.tsx` traducido (título y descripción del `sheet`, botón y borde); el borde (`SidebarRail`, sin foco de teclado) tiene otro nombre para no duplicar el del botón.
  - Pruebas primero: `components/app/AdminShell.test.tsx` (7: entradas y grupos, `aria-current`, migas, colapso persistido, menú de usuario, pantallas pendientes, `sheet` en celular). `src/test/setup.ts` + `src/test/matchMedia.ts` simulan `matchMedia` (jsdom no lo trae); sin `user-event` (no aprobada): `fireEvent`. Total 88/88; lint, typecheck y build en verde.
  - Navegador real: a 1440 px expandida y colapsada, y tras recargar sigue colapsada; a 375 px encabezado con menú, buscador y usuario de 44 px, y `sheet` con enlaces de 44 px; sin scroll horizontal en ninguno.
  - Menores: `Ctrl+B` (atajo de shadcn) alterna la barra; el texto del buscador se acortó a "Buscar por código o nombre" porque se cortaba a 1440 px.

### T5 — Buscador global

- **Resultado:** `GlobalSearch` con `command`: `Ctrl/⌘ K`, búsqueda por código o nombre sobre `datos-ficticios`, salto a la ficha ficticia; estados "Buscando…", "Sin resultados para «…»".
- **Tests primero:** atajo, filtrado, navegación con flechas y `Enter` (A5).
- **Archivos probables:** `web/src/components/app/GlobalSearch.tsx`, `web/src/mocks/datos-ficticios.ts` y pruebas.
- **Verificación:** `cd web && npm test` + capturas del buscador abierto a 375 px y 1440 px.
- **Depende de:** T4.
- **Riesgo:** atajo que choca con el del navegador; se usa `preventDefault` solo dentro de la app.
- **Implementada (2026-11-13), revisada (APROBADO):**
  - `components/app/GlobalSearch.tsx` (`CommandDialog` + `cmdk`): grupo "Activos" (código o nombre sobre `mocks/datos-ficticios.ts`) y grupo "Ir a" (pantallas de `admin-nav.ts`); "Sin resultados para «…»"; elementos de 44 px en celular. Se abre con `Ctrl+K`/`⌘K` (con `preventDefault`), con el botón del encabezado y con el ícono en celular.
  - `mocks/datos-ficticios.ts`: "Clínica Demo" con activos, ubicaciones, resumen del Inicio, último informe (desglose por categoría y ubicación que suma las tres cifras) y actividad; dinero como texto decimal. Lo usan T5–T9.
  - Ruta `/admin/activos/:codigo` con ficha mínima (la completa llega con la spec 005) y "No encontramos ese código".
  - `command.tsx`: campo de búsqueda con `bg-muted` (el `bg-input/30` quedaba gris oscuro con el borde de control más fuerte del tema) y 16 px en celular (evita el zoom de iOS).
  - `test/setup.ts`: simula `scrollIntoView` y `ResizeObserver` (cmdk y Radix; jsdom no los trae).
  - Pruebas primero: `components/app/GlobalSearch.test.tsx` (6, en rojo antes); total 94/94; lint, typecheck y build en verde. Navegador real a 375 y 1440 px: diálogo dentro de la pantalla, sin scroll horizontal ni errores de consola.

### T6 — `CountShell` y `NetworkStatus`

- **Resultado:** encabezado compacto (retroceso, sesión y sala, chip de estado), contenido y barra de acción fija con área segura; `NetworkStatus` con sus cinco estados; columna centrada en computador (D5).
- **Tests primero:** `NetworkStatus` por estado (texto, ícono, `aria-live`) y tamaño mínimo de los botones de la barra (A6).
- **Archivos probables:** `web/src/components/app/CountShell.tsx`, `web/src/components/app/NetworkStatus.tsx` y pruebas.
- **Verificación:** `cd web && npm test` + capturas a 375 px; objetivos medidos ≥ 44 px.
- **Depende de:** T3.
- **Riesgo:** área segura de iOS; se usa `env(safe-area-inset-bottom)`.

### T7 — Componentes propios de datos

- **Resultado:** `StatCard`, `ThreeFiguresCard`, `LiveValueCard` (tipos distintos, R10), `AssetCard` (precio solo con rol `admin`, R11), `LocationPicker` (jerárquico, "Última usada" arriba), `PendingList`, `EmptyState`; dinero con `lib/format.ts`.
- **Tests primero:** A7 (tipos y DOM sin precio para `contador`), formato `$ 1.234.567,00`, `LocationPicker` con teclado, textos largos truncados sin desbordar (R12).
- **Archivos probables:** `web/src/components/app/*`, `web/src/lib/format.ts` y pruebas.
- **Verificación:** `cd web && npm test && npm run typecheck` + galería en `/dev/componentes`.
- **Depende de:** T2.
- **Riesgo:** calcular totales en el cliente; las tarjetas solo reciben cifras ya hechas.

### T8 — Maquetas de administración

- **Resultado:** con datos ficticios y sus cuatro estados: Inicio (indicadores, último informe, actividad; sin gráficas, que llegan en 010), tabla de Activos (búsqueda, filtros, menú por fila con `alert-dialog` en Dar de baja), Registrar activo (D3: código del sticker, copiar de un parecido, nombre, precio, categoría y ubicación obligatorios, opcionales colapsados, varias unidades), Informe (tres cifras y pestañas por categoría, por ubicación y no encontrados).
- **Tests primero:** estados por maqueta (A9); Registrar no permite guardar sin código, nombre, precio, categoría ni ubicación (validación de formulario; la del servidor llega en 004).
- **Archivos probables:** `web/src/routes/admin/*` y pruebas.
- **Verificación:** `cd web && npm test` + capturas a 375 px y 1440 px, con modales y `sheet` abiertos, y `scrollWidth` (A8).
- **Depende de:** T4, T5, T7.
- **Riesgo:** pasar de un día; Informe se separa con `/sdd-change` si hace falta.

### T9 — Maquetas de conteo

- **Resultado:** a 375 px y con datos ficticios: Inicio del contador (sin precios), escáner simulado (sin ZXing), escribir código y cámara denegada, verificar (con variante admin con precio de referencia), `sheet` de otra ubicación, verificado, no confirmado / sesión cerrada (409) y alta por escaneo en una columna.
- **Tests primero:** flujo escanear → verificar → verificado por rutas; "No confirmado" ofrece Reintentar y "Sesión cerrada" no; alta exige los cuatro campos obligatorios.
- **Archivos probables:** `web/src/routes/contar/*` y pruebas.
- **Verificación:** `cd web && npm test` + capturas a 375 px (y 1440 px con la columna centrada), `scrollWidth` (A8).
- **Depende de:** T6, T7.
- **Riesgo:** sobrediseñar el escáner antes de 004; solo visor simulado y "Escribir código".

### T10 — Verificación final y documentación

- **Resultado:** recorrido completo en navegador real a 375 px y 1440 px de todas las rutas, con modales y `sheet` abiertos; contraste y accesibilidad con Lighthouse; resultados y capturas anotados aquí; `docs/08` actualizado (pendientes de diseño cerrados por esta spec) y `MEMORY.md`.
- **Tests primero:** no aplica (tarea de verificación); `npm test` completo en verde.
- **Archivos probables:** `specs/001b-sistema-de-diseno/tasks.md`, `docs/08-diseno-visual.md`, `MEMORY.md`.
- **Verificación:** `cd web && npm run lint && npm run typecheck && npm test && npm run build` + A2, A3, A8, A9 documentados.
- **Depende de:** T1–T9; revisión del `reviewer`.
- **Riesgo:** hallazgos de desborde tardíos; se corrigen en la tarea que los originó antes de cerrar.
