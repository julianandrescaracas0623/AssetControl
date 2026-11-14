# Spec 001b — Sistema de diseño y app shell

> **Estado:** Implementada (T1–T10, 2026-11-14), sobre la aprobación G1–G3 del 2026-11-13 con D1–D5. Detalle en `tasks.md`. Fecha: 2026-11-13. Extiende `specs/001-fundacion-tecnica/` (después de su T8, como pide `docs/08` §11). Va antes de `specs/002b-acceso-web/`, que usa el tema y el shell para sus pantallas.

## Problema

La web solo tiene la pantalla de `/health` de la fundación. El diseño visual ya está aprobado ("Grafito y Cobalto", `docs/08`, 2026-11-13, con su lienzo de referencia), pero vive en una maqueta hecha a mano. Sin el tema, los componentes y la estructura de navegación reales, cada spec de pantallas (002b, 003–010) inventaría su propio layout y el resultado se desviaría del diseño aprobado.

## Usuario

- `admin`: usa `/admin/**` en computador y en celular.
- `contador`: usa `/contar/**` en el celular, con una mano.

## Resultado esperado

Una web con el tema aprobado, los componentes de shadcn/ui configurados con ese tema, el `AdminShell` y el `CountShell` navegables y las pantallas clave como maquetas con **datos ficticios**, sin backend de negocio. Las specs siguientes solo conectan datos reales a piezas que ya existen.

## Alcance

- **Incluye:**
  - Tema "Grafito y Cobalto" como variables de shadcn/Tailwind en un solo archivo (`web/src/index.css`): neutros zinc, acento cobalto, estados (éxito, aviso, error) con sus variantes suaves, radios y sombras de `docs/08` §2.
  - Fuente Geist y Geist Mono **autoalojadas** (paquete npm, sin CDN).
  - Componentes de shadcn/ui añadidos con la CLI (lista en `plan.md` §3) y variantes semánticas de `Badge` y `Alert`.
  - Enrutado de la web: `/admin/**`, `/contar/**`, `/login` (marcador para 002b), pantalla "Sin permiso" y "No encontrado".
  - `AdminShell`: barra lateral con los grupos de `docs/08` §4.1 (incluida **Registrar activo**), colapsable a íconos y recordando el estado; menú tipo `sheet` por debajo de `md`; migas de pan; buscador global con `Ctrl/⌘ K` sobre datos ficticios; menú de usuario.
  - `CountShell`: encabezado compacto con sesión y sala, `NetworkStatus`, barra de acción fija abajo con área segura.
  - Componentes propios: `StatCard`, `ThreeFiguresCard`, `LiveValueCard`, `AssetCard`, `NetworkStatus`, `LocationPicker`, `PendingList`, `EmptyState`.
  - Maquetas con datos ficticios: Inicio de admin (sin gráficas), tabla de Activos, Registrar activo, Informe de sesión; y en conteo: Inicio del contador, escáner simulado, escribir código, verificar, verificado, no confirmado / sesión cerrada y alta por escaneo.
  - Verificación en navegador real a 375 px y 1440 px y contraste medido con herramienta.
- **No incluye:** backend ni llamadas a la API de negocio; login real y OpenAPI (002b); lectura real de códigos con ZXing (004); gráficas y `recharts` (010); `@tanstack/react-table` y TanStack Query (se deciden con la primera pantalla con datos); modo oscuro; logo definitivo (T9 de `docs/05`); exportar PDF/Excel (009).

## Requisitos (EARS)

1. **R1 (tema):** El sistema debe definir todos los colores, radios, sombras y familias tipográficas como variables de tema en un único archivo, de modo que ninguna pantalla use un color hex propio.
2. **R2 (contraste):** El sistema debe usar pares de texto y fondo con contraste WCAG AA (≥ 4,5 : 1 en texto normal, ≥ 3 : 1 en texto grande y bordes de control).
3. **R3 (fuente):** El sistema debe servir Geist y Geist Mono desde la propia web, sin peticiones a dominios de terceros.
4. **R4 (navegación admin):** Cuando el usuario abra una ruta `/admin/**` en un ancho desde `md`, la web debe mostrar la barra lateral con los grupos General, Inventario (Activos, Registrar activo, Ubicaciones, Categorías), Conteo, Finanzas y Ajustes, marcar la entrada activa y mostrar sus migas de pan.
5. **R5 (admin en celular):** Mientras el ancho sea menor que `md`, la web debe reemplazar la barra lateral por un menú tipo `sheet` abierto desde el encabezado, con las mismas entradas.
6. **R6 (barra colapsable):** Cuando el usuario colapse la barra lateral, la web debe mostrar solo íconos con tooltip y conservar el estado al recargar.
7. **R7 (buscador):** Cuando el usuario pulse `Ctrl+K` o `⌘K`, o toque el buscador, la web debe abrir el buscador global y permitir elegir un activo ficticio por código o nombre con el teclado.
8. **R8 (conteo):** Cuando el usuario abra una ruta `/contar/**`, la web debe mostrar el `CountShell` con la acción principal fija en la zona inferior, a ancho completo, con objetivos de 44 px o más y separación de 8 px o más.
9. **R9 (estado de envío):** El componente `NetworkStatus` debe distinguir visualmente y en texto, con ícono, los estados "En línea", "Enviando…", "Guardado", "No confirmado" y "Sin conexión", y anunciarlos con `aria-live="polite"`.
10. **R10 (dos cifras):** El sistema debe mostrar el valor actual (`LiveValueCard`, rótulo "Valor actual · no es el informe") y el informe congelado (`ThreeFiguresCard`, rótulo "Informe congelado") en componentes distintos que no se combinan en una misma tarjeta (R7 de `docs/03`).
11. **R11 (precio por rol en la UI):** Donde el rol simulado sea `contador`, `AssetCard` y las maquetas no deben mostrar precio, columna vacía ni marcador ("•••") en su lugar. Esto es presentación; la seguridad real es el filtrado del servidor (P13), fuera de esta spec.
12. **R12 (sin desbordes):** Cuando una pantalla se muestre a 375 px o a 1440 px, ningún modal, `sheet`, formulario, selector ni tabla debe salirse de su contenedor ni producir scroll horizontal de la página; los textos largos se cortan con "…" o bajan de línea, y las tablas anchas hacen scroll dentro de su caja.
13. **R13 (estados):** Cada maqueta debe ofrecer sus estados cargando, vacío con acción, error con reintentar y éxito, conmutables con datos ficticios.
14. **R14 (accesibilidad):** Todo control debe ser alcanzable con teclado, con anillo de foco visible; los botones de solo ícono deben tener `aria-label`; se respeta `prefers-reduced-motion`.

## Criterios de aceptación

- **A1 (R1):** una prueba recorre `web/src` y falla si encuentra colores hex o `rgb()` fuera de `index.css` (lista de excepciones vacía).
- **A2 (R2):** una prueba calcula el contraste WCAG de los pares de la tabla de `plan.md` §2 a partir de las variables de `index.css` y falla si alguno no cumple; además, el contraste se mide con Lighthouse o DevTools en la web real y el resultado se anota en `tasks.md`.
- **A3 (R3):** `npm run build` incluye los archivos de fuente en `dist/`; en el navegador, la pestaña de red no muestra peticiones a dominios externos.
- **A4 (R4–R6):** pruebas de componentes: entrada activa marcada con `aria-current="page"`, colapso persistido, `sheet` por debajo de `md`; capturas a 375 px y 1440 px.
- **A5 (R7):** prueba de componente: `Ctrl+K` abre el buscador, flechas y `Enter` eligen un activo y la web navega a su ficha ficticia.
- **A6 (R8, R9):** pruebas de `NetworkStatus` (texto, ícono y `aria-live` por estado) y capturas de conteo a 375 px con objetivos medidos ≥ 44 px.
- **A7 (R10, R11):** pruebas: `ThreeFiguresCard` y `LiveValueCard` no aceptan las cifras del otro (tipos distintos); con rol `contador`, el DOM de `AssetCard` y de las maquetas no contiene el texto del precio ni el símbolo `$` en esa ficha.
- **A8 (R12):** en navegador real, a 375 px y 1440 px, `document.documentElement.scrollWidth <= window.innerWidth` en cada maqueta y con cada modal o `sheet` abierto; capturas en `tasks.md`.
- **A9 (R13, R14):** cada maqueta muestra sus cuatro estados; recorrido completo con teclado en `AdminShell` y en Verificar sin trampas de foco.
- **A10:** `npm run lint`, `npm run typecheck`, `npm test` y `npm run build` en verde en local y en CI.

## Reglas de dominio

No se redefinen; las maquetas las muestran tal como están en `docs/03` y `docs/07`: R7 (valor actual separado del informe), R8 (no hay alta sin código de sticker), P13 (precio solo para el admin), R6 (otra ubicación es una observación, no un movimiento). Los datos ficticios no usan datos de la clínica (constitución: datos de la clínica fuera del repo): clínica "Clínica Demo", personas y cifras inventadas.

## Riesgos

- **Desvío respecto al lienzo** → las capturas de A8 se comparan con el lienzo aprobado antes de dar por buena cada pantalla.
- **Dependencias que arrastra la CLI de shadcn** → la lista exacta se toma de la salida de `npx shadcn add`; si aparece algo fuera de `plan.md` §3, se para y se pregunta.
- **Maquetas que se confundan con funcionalidad** → banda visible "Datos ficticios" en las maquetas y rutas bajo `/admin` y `/contar` sin llamadas de red de negocio.
- **Tamaño** → si una tarea pasa de un día, se parte con `/sdd-change`, no se recorta verificación.

## Decisiones (G1–G3, humano, 2026-11-13)

- **D1 [DECIDIDO]:** aprobadas con versión exacta `@fontsource-variable/geist` 5.3.0, `@fontsource-variable/geist-mono` 5.3.0, `react-router` 8.5.1, `cmdk` 1.1.1 y `sonner` 2.0.8. `react-router` cubre también el enrutado de 002b (su Q8).
- **D2 [DECIDIDO]:** ancho máximo del contenido de admin, 1320 px.
- **D3 [DECIDIDO]:** Registrar activo en `/admin/activos/nuevo`.
- **D4 [DECIDIDO]:** crear o editar en admin por debajo de `md` con `sheet` inferior o pantalla completa, como en conteo.
- **D5 [DECIDIDO]:** `/contar/**` en computador, columna centrada de 480 px.
