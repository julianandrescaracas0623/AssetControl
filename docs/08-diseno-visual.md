# 08. Diseño visual del MVP

> Documento de diseño, no es spec ni código. Si choca con [01-alcance-mvp.md](01-alcance-mvp.md), [02-arquitectura.md](02-arquitectura.md), [03-modelo-datos.md](03-modelo-datos.md), [07-casos-de-uso-y-modulos.md](07-casos-de-uso-y-modulos.md) o un ADR, mandan ellos. Solo Tailwind CSS + shadcn/ui ([ADR-001](adr/ADR-001-stack.md)); sin otra librería de componentes. Toda dependencia npm nueva (las que arrastra un componente de shadcn/ui, una fuente, una librería de tablas o de íconos) se declara en la spec que la añada y la aprueba el humano antes (AGENTS.md: dependencias nuevas, preguntar antes). Lo no decidido va como `[PENDIENTE]`.

**Dirección (decidida por el humano, 2026-11-11)**: AssetControl es un sistema de gestión de activos y debe verse **profesional**. Estilo **SaaS moderno y sobrio**, inspirado (no copiado) en paneles como los de Stripe, Linear o Vercel: barra lateral, encabezado con buscador, tarjetas de indicadores, tablas limpias con filtros, mucho espacio en blanco y tipografía cuidada. Base neutra (grises tipo zinc/slate de shadcn), **un acento contenido** y estados semánticos discretos. La marca es la del producto, no la de la clínica. Los colores viven como variables de tema (Tailwind/shadcn) para cambiarlos sin tocar pantallas.

## 1. Principios visuales

1. **Profesional y sobrio**: la interfaz transmite control y precisión. Jerarquía por tipografía, espacio y peso, no por color ni decoración. Bordes finos antes que sombras; nada de degradados, ilustraciones ni íconos decorativos.
2. **El dato es el protagonista**: cifras alineadas (`tabular-nums`), tablas legibles, etiquetas cortas. El color solo significa algo: acento = acción o selección; verde/rojo/ámbar = estado.
3. **Un lenguaje, dos modos**: administración (escritorio, denso, app shell con barra lateral) y conteo (móvil, grande, una mano) comparten tipografía, color, radios, íconos y componentes. Cambia la densidad, no el estilo.
4. **Cero digitación innecesaria** (constitución 7): cada pantalla de captura ofrece primero escanear, elegir, autocompletar o copiar; el teclado es el último recurso. En escritorio, filtros y acciones por fila evitan reescribir datos.
5. **Una mano en conteo**: en `/contar/**` la acción principal vive fija en la zona del pulgar y los objetivos miden ≥ 44 px. Claridad bajo apuro: una acción principal por pantalla; el resultado se ve de inmediato.
6. **El servidor manda** (constitución 3): la UI nunca muestra una cifra como definitiva si no viene del servidor; "No se pudo confirmar" se ve distinto de "Guardado". Las tarjetas de indicadores y las gráficas muestran lo que devuelve el servidor, no lo recalculan.
7. **El precio es del admin** (P13): el diseño del contador no deja huecos, columnas vacías ni "•••" donde iría un precio; simplemente no existe.

## 2. Tokens

### 2.1 Color (claro)

Variables CSS de shadcn (`--background`, `--primary`, etc.) en un único archivo de tema; base neutra **zinc** `[PENDIENTE: zinc o slate]`. Valores propuestos; **no se afirma que cumplan contraste hasta medirlos**.

| Rol | Variable shadcn | Hex | Uso |
|---|---|---|---|
| Fondo | `--background` | `#FFFFFF` | Área de contenido |
| Fondo lateral | `--sidebar` (y `--sidebar-*`) | `#FAFAFA` | Barra lateral de admin |
| Superficie | `--card` / `--popover` | `#FFFFFF` | Tarjetas, sheets, diálogos, menús |
| Texto | `--foreground` | `#09090B` | Texto principal y cifras |
| Texto secundario | `--muted-foreground` | `#52525B` | Ayudas, metadatos, encabezados de tabla |
| Superficie suave | `--muted` / `--accent` | `#F4F4F5` | Hover de fila, ítem activo del menú, chips neutros |
| Botón principal | `--primary` | `#18181B` | Acción principal (una por pantalla) |
| Texto sobre principal | `--primary-foreground` | `#FAFAFA` | Etiqueta del botón principal |
| Acento de marca | `--brand` (propio) | `#2563EB` | Foco, enlaces, selección, barra de avance |
| Éxito | `--success` (propio) | `#15803D` | Encontrado, guardado |
| Error | `--destructive` | `#B91C1C` | Fallo, no encontrado, baja |
| Aviso | `--warning` (propio) | `#B45309` | Discrepancia, "No se pudo confirmar", dañado |
| Borde | `--border` | `#E4E4E7` | Separadores, contorno de tarjetas y tablas |
| Borde de control | `--input` | `#A1A1AA` | Contorno de campos y casillas |
| Anillo de foco | `--ring` | `#2563EB` | Foco visible (2 px + 2 px de separación) |

- **Botón principal** `[PENDIENTE]`: opción A (recomendada) neutro oscuro `#18181B`, como en el tema por defecto de shadcn, y el acento solo en foco, enlaces, selección y avance; opción B, el botón principal en el acento. A es más sobria y resiste mejor el sol directo.
- **Estados discretos**: en badges y avisos se usa fondo muy suave (≈ 5–10 % del color) con texto e ícono del color sólido; el color sólido de fondo se reserva para la banda "Verificado" y la acción destructiva confirmada. Nunca van solos: siempre ícono + texto.
- El borde de control `#A1A1AA` probablemente no alcanza 3:1 sobre blanco; si al medirlo no llega, se oscurece (p. ej. hacia `#71717A`). El borde decorativo `--border` no tiene que cumplir 3:1 porque no delimita controles.
- **Modo oscuro** `[PENDIENTE]`: el estilo SaaS suele incluirlo y las variables ya permiten añadir `.dark` sin tocar pantallas; no entra al MVP salvo decisión humana.
- **Meta de contraste**: WCAG AA, 4.5:1 en texto normal y 3:1 en texto grande y bordes de controles. Se mide con herramienta (inspector de contraste de Chrome DevTools o Lighthouse) cada par de la tabla y el resultado se anota en el PR. Hoy es una meta, no un hecho.

### 2.2 Forma, sombra, espaciado

| Token | Valor | Nota |
|---|---|---|
| Radio base `--radius` | `0.5rem` (8 px) | Botones y campos `rounded-md`; tarjetas, sheets y diálogos `rounded-xl` |
| Bordes y sombras | Tarjetas y tablas con borde de 1 px, sin sombra o `shadow-xs`; `shadow-lg` solo en sheet, diálogo y menú | Sin sombras de color |
| Espaciado base | 4 px (escala Tailwind); bloques `gap-4` (16 px) en móvil, `gap-6` (24 px) en escritorio; márgenes de página 24–32 px en escritorio | Mucho blanco, nunca aire vacío sin propósito |
| Ancho de contenido admin | Fluido con máximo `[PENDIENTE: ~1280–1440 px]` | Tablas a ancho completo del área |
| Objetivo táctil | `min-h-11` (44 px) en `/contar/**`; botón principal `h-12`–`h-14` | Escritorio: `h-8`/`h-9` |
| Separación entre objetivos | ≥ 8 px | Evita toques erróneos |

### 2.3 Tipografía

- **Base**: pila del sistema, sin descargar nada: `ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`. Cifras con `tabular-nums`; códigos con `font-mono` del sistema.
- **Fuente de producto** `[PENDIENTE]`: el estilo SaaS gana mucho con una sola familia cuidada. Recomendación: **Inter** o **Geist**, variable y **autoalojada** (servida desde la propia web, no desde un CDN de terceros, para no filtrar visitas ni depender de red externa). Es una **dependencia nueva** (paquete npm de la fuente o archivos en el repo, con su licencia) que el humano debe aprobar; hasta entonces se usa la pila del sistema y nada se rompe al cambiarla, porque la familia vive en una variable de tema.

| Uso | Móvil (`/contar`) | Escritorio (`/admin`) |
|---|---|---|
| Cuerpo | 16 px mínimo (evita zoom automático en iOS) | 14 px |
| Etiqueta / metadato / encabezado de tabla | 14 px mínimo | 12–13 px, `font-medium`, `--muted-foreground` |
| Título de página | 18–20 px semibold | 24 px semibold, `tracking-tight` |
| Nombre de activo (ficha) | 22 px semibold | 18 px semibold |
| Código (sticker) | 18 px `font-mono` | 13–14 px `font-mono` |
| Cifra de indicador o informe | 28 px semibold, `tabular-nums` | 30 px semibold, `tabular-nums` |

Dinero: `$ 1.234.567,00` en `es-CO` (`Intl.NumberFormat`), siempre con la etiqueta "COP" en informes y exportaciones. El formateo es solo de presentación; las cifras vienen del servidor.

### 2.4 Íconos

Un solo juego de íconos de trazo fino en los dos modos, tamaño 16 px en escritorio y 20–24 px en conteo, siempre acompañando texto (salvo botones de ícono con `aria-label` y tooltip). La opción natural con shadcn/ui es **`lucide-react`**: varios componentes de shadcn la importan por sí mismos. Es una **dependencia a aprobar**; no se da por instalada.

## 3. Componentes

### 3.1 shadcn/ui (se añaden con `npx shadcn@latest add`, sin reescribirlos)

Copiar un componente de shadcn/ui no es "cero dependencias": muchos instalan paquetes npm o arrastran otros componentes. La lista exacta se confirma con la salida de `npx shadcn@latest add` en la tarea que lo añada, se declara en su spec y la aprueba el humano antes.

| Componente | Dónde | Dependencia propia (a confirmar al añadir) |
|---|---|---|
| `sidebar` | App shell de admin: barra lateral colapsable | Sí; arrastra otros componentes (p. ej. `sheet`, `tooltip`, `separator`) y posiblemente íconos |
| `breadcrumb` | Migas de pan del encabezado de admin | Posiblemente íconos |
| `button` | Todo. Variantes `default` (una por pantalla), `outline`, `ghost`, `destructive` | Sí, Radix |
| `input`, `label`, `textarea` | Alta, login, invitación, nota, búsqueda | `label`: Radix |
| `select` | Categoría, estado físico, filtros cortos | Sí, Radix |
| `command` + `popover` | Buscador global, ubicación jerárquica, autocompletado, "copiar de un parecido", filtros de opciones | `command`: `cmdk`; `popover`: Radix |
| `card` | Indicadores, ficha, bloques de informe | — |
| `table` | Base de las tablas de datos (ver 4.3) | — |
| `badge` | Estado del activo, de la sesión, rol | — |
| `dropdown-menu` | Menú de usuario, acciones por fila | Sí, Radix |
| `sheet` | Inferior en conteo; panel lateral de edición en admin | Sí, Radix |
| `dialog` / `alert-dialog` | Crear/editar en escritorio; acciones irreversibles | Sí, Radix |
| `tabs` | Informe: resumen / por categoría / por ubicación | Sí, Radix |
| `tooltip`, `separator`, `avatar` | Barra lateral colapsada, encabezado, menú de usuario | Sí, Radix |
| `sonner` (toast) | Éxito breve y errores no bloqueantes | `sonner` |
| `skeleton`, `alert` | Estados cargando; errores persistentes en pantalla | — |
| `chart` | Inicio de admin: valor por categoría, valor por ubicación y evolución entre conteos (CU-DSH-03, 04) | Sí: según la documentación de shadcn/ui se apoya en `recharts`. **Dependencia nueva**: a confirmar al añadir y a aprobar por el humano en la spec 010 |
| `form` + `checkbox` + `collapsible` | Formularios validados; selección de filas; opcionales colapsados | `form`: `react-hook-form`, `zod`, `@hookform/resolvers`; resto Radix |

**Bloques de referencia**: shadcn/ui publica bloques de ejemplo (paneles tipo dashboard, variantes de barra lateral, pantallas de inicio de sesión). Sirven como **punto de partida** para el app shell, el Inicio y el login; se eligen y adaptan en la spec de sistema de diseño (sección 11), sin fijar aquí nombres de bloques que no se hayan confirmado.

### 3.2 Propios (compuestos con los anteriores)

| Componente | Responsabilidad |
|---|---|
| `AdminShell` | Barra lateral + encabezado (migas, buscador, usuario) + área de contenido (ver 4.1) |
| `CountShell` | Encabezado compacto (sesión, sala, estado de red) + contenido + barra de acción fija abajo (ver 5) |
| `StatCard` | Indicador: rótulo, cifra del servidor, contexto ("de 200", "hace 5 min"), enlace al detalle |
| `DataTable` | Tabla de datos con búsqueda, filtros, orden, paginación y acciones por fila (ver 4.3) |
| `ScannerView` | Visor de cámara (ZXing sobre `getUserMedia`), marco de lectura, estados: pidiendo permiso, activo, poca luz, denegado, sin cámara. **Siempre** incluye "Escribir código" |
| `AssetCard` | Nombre, código, categoría, ubicación esperada, estado. Precio **solo si el rol es admin** y el dato viene del servidor |
| `NetworkStatus` | Chip de envío: enviando, guardado, "No se pudo confirmar" + `Reintentar`; "Sin conexión" si el navegador lo reporta. Conserva el UUID pendiente |
| `ThreeFiguresCard` | Tres cifras (encontrado, no encontrado, total registrado) con fecha de corte y sesión; rótulo "Informe congelado" |
| `LiveValueCard` | Valor en tiempo real, rotulado "Valor actual (no es el informe)"; nunca comparte tarjeta con `ThreeFiguresCard` (R7) |
| `LocationPicker` | Combobox jerárquico sede > sala > box con "última usada" arriba |
| `PendingList` | Activos sin verificar de la sesión, por ubicación |
| `BreakdownChart` | Gráfica de barras de valor por categoría o por ubicación (sobre `chart`); rótulo obligatorio de su fuente: "Valor actual (no es el informe)" o "Último informe cerrado · corte dd/mm/aaaa". Nunca mezcla las dos fuentes. Solo admin |
| `EvolutionChart` | Evolución entre conteos (sobre `chart`): valor registrado y % encontrado por sesión cerrada, con filtro por categoría; lee el desglose congelado del servidor. Solo admin |

### 3.3 Sheet, panel o diálogo

| Situación | Componente |
|---|---|
| Móvil, acción rápida tras escanear (verificar, ubicación, "otra ubicación") | **Sheet inferior** |
| Móvil, formulario corto (alta por escaneo) | Pantalla completa; botón principal fijo abajo |
| Escritorio, crear o editar corto (ubicación, invitación) | Diálogo |
| Escritorio, editar un activo desde la tabla | Sheet lateral derecho; la tabla sigue visible |
| Confirmación destructiva o irreversible (cerrar sesión, dar de baja) | `alert-dialog` en ambos modos, con el efecto explícito |
| Error que bloquea el flujo (sesión cerrada) | `alert` en pantalla, no toast |

## 4. Layout de administración (`/admin/**`, escritorio)

### 4.1 App shell

- **Barra lateral** (componente `sidebar`), colapsable a solo íconos (con tooltip) y recordando el estado. Arriba: "AssetControl" en texto (sin logotipo hasta T9). Grupos: **General** (Inicio), **Inventario** (Activos, Ubicaciones, Categorías), **Conteo** (Sesiones, Discrepancias `[PENDIENTE: entrada propia o solo dentro de la sesión]`), **Finanzas** (Valor actual), **Ajustes** (Usuarios). Abajo: "Ir a contar" (abre `/contar`) y la clínica activa (tenant) como texto.
- **Encabezado** (altura ~56 px, borde inferior): botón para colapsar la barra, **migas de pan** (`Sesiones / Conteo nov 2026 / Informe`), **buscador global** al centro o a la derecha, y **menú de usuario** (avatar con iniciales, nombre, rol, "Cerrar sesión").
- **Buscador global**: abre un `command` (también con `Ctrl/⌘ K`) que busca activos por código o nombre y salta a su ficha; alcance más allá de activos `[PENDIENTE]` (recomendación MVP: solo activos y navegación a pantallas). La búsqueda la resuelve el servidor, filtrada por tenant.
- **Área de contenido**: título de página + descripción corta a la izquierda, acciones de página a la derecha (una principal); debajo, tarjetas y tablas.
- **Menos de 1024 px**: la barra lateral pasa a sheet (comportamiento del componente). Admin en móvil no se optimiza en el MVP `[PENDIENTE]`; debe ser usable, no cómodo.
- El menú lateral solo se muestra al `admin`; el contador que abre `/admin/**` recibe 403 del servidor (ocultar el menú no es seguridad).

### 4.2 Inicio / Resumen (`/admin`)

**Entra al MVP** (decisión del humano, 2026-11-11): módulo M11, CU-DSH-01..04 de [07](07-casos-de-uso-y-modulos.md), spec 010.

- **Tarjetas de indicadores** (`StatCard`), en una o dos filas: **Activos hoy** (conteo en tiempo real de los activos `activo` o `en_reparacion`, sin los `dado_de_baja`, P15/R7; puede indicar aparte cuántos están en reparación; no es `total_registrado`, que es la cifra congelada del informe; nombre por defecto revisable, 2026-11-11), **Valor actual** (mismo criterio de estados que Activos hoy; rótulo "No es el informe", enlace a `/admin/valor`), **Avance del conteo abierto** (% verificado, barra de avance en acento y enlace a pendientes por ubicación; sin sesión abierta: "Sin sesión abierta" + [Abrir sesión]), **Discrepancias** sin resolver (enlace a la lista), **Dañados o en reparación** (rotula su fuente: estado vigente + estado físico de la sesión indicada, P26; enlace a la tabla de Activos filtrada).
- **Último informe cerrado**: `ThreeFiguresCard` con las tres cifras, fecha de corte y rótulo "Informe congelado"; enlace al informe. Va separada de la tarjeta de valor actual (R7).
- **Gráficas** (`BreakdownChart`): valor por categoría y valor por ubicación, cada una con su fuente rotulada ("Valor actual" o "Último informe cerrado"; fuente por defecto `[PENDIENTE]` P23).
- **Evolución entre conteos** (`EvolutionChart`): valor registrado y % encontrado por sesión cerrada, con selector de categoría; solo sesiones cerradas de tipo conteo, leídas del desglose congelado. Cuántas sesiones por defecto: `[PENDIENTE]` P22.
- **Actividad reciente**: tabla compacta de los últimos eventos (fecha, usuario, evento, activo) con enlace a "Ver todo" `[PENDIENTE: pantalla de actividad global o solo historial por activo]`.

### 4.2.1 Inicio del contador (sin precios)

El contador no entra a `/admin/**` (403); su Inicio vive en el modo conteo (`/contar`, ruta exacta `[PENDIENTE]` P25), a 375 px. Recomendación (P25): tarjeta de **Activos hoy** (total en tiempo real), **Avance del conteo abierto** (% verificado y pendientes por ubicación) y **Actividad reciente** sin precios (sin eventos `precio_cambiado` ni montos). Valor actual, discrepancias, dañados, último informe, gráficas y evolución **no existen** para él: no se ocultan con un hueco ni con "•••", y el servidor no envía esos datos (P13).

```
┌─────────────────────────┐
│ AssetControl           ●│
├─────────────────────────┤
│ ┌──────────┐┌──────────┐│
│ │Activos   ││Conteo nov││
│ │200       ││60 %      ││
│ └──────────┘└──────────┘│
│ Pendientes por ubicación│
│ Sala 2          8  ›    │
│ Bodega         12  ›    │
│ Actividad reciente      │
│ 10:42 Verificado Autocl.│
│ 10:40 Activo creado Sil.│
├─────────────────────────┤
│ ▓[      Escanear     ]▓ │
└─────────────────────────┘
```

### 4.3 Tablas de datos

Patrón para Activos, Ubicaciones (vista lista), Sesiones, Discrepancias, Usuarios:

- **Barra de herramientas**: búsqueda por texto, filtros como botones `outline` con conteo de seleccionados (p. ej. Categoría, Ubicación, Estado), "Limpiar filtros"; a la derecha la acción principal ("Nuevo activo" no aplica: el alta es por escaneo; en Activos la principal es "Exportar" `[PENDIENTE]`).
- **Tabla**: encabezados en 12–13 px `--muted-foreground`, filas de ~44 px, hover suave, cifras alineadas a la derecha con `tabular-nums`, códigos en `font-mono`, estados como `badge`. Orden al hacer clic en el encabezado.
- **Acciones por fila**: menú `⋯` (`dropdown-menu`) con Ver, Editar, Mover, Historial, Dar de baja (destructiva, al final y con `alert-dialog`).
- **Paginación** al pie: "1–25 de 200", tamaño de página y anterior/siguiente. Paginación, orden y filtro en cliente o en servidor `[PENDIENTE]`; con el volumen del primer cliente cabe en cliente, pero el contrato de la API se fija en la spec de cada módulo.
- **Estados**: esqueleto de filas, vacío con acción y error con reintento (sección 8).
- El patrón "data table" de shadcn/ui se apoya en **`@tanstack/react-table`**: es una **dependencia a aprobar**, no se da por instalada. Alternativa sin ella: `table` simple con orden y filtro propios (aceptable para pocas columnas).

## 5. Layout de conteo (`/contar/**`, móvil, 375 px)

Mismo lenguaje visual que admin (tipografía, color, radios, íconos, badges), con densidad de una mano:

- **Encabezado compacto** (~48 px, borde inferior): retroceso a la izquierda; al centro sesión y sala ("Conteo nov 2026 · Sala 2"); a la derecha `NetworkStatus` (chip "En línea", "Enviando…", "No confirmado"). Sin menús en la esquina superior.
- **Contenido**: tarjeta con borde, sin sombra; datos en filas rótulo/valor; badges de estado iguales a los de admin.
- **Barra de acción fija abajo**: fondo `--background`, borde superior, respeta el área segura del teléfono; contiene la acción principal a ancho completo y, si hace falta, una secundaria `outline` encima.
- Sheets inferiores para elegir y confirmar; nada de diálogos centrados en móvil salvo `alert-dialog`.

## 6. Inventario de pantallas

Rutas **propuestas** (`[PENDIENTE]` de fijar en las specs 002–010). "Precios" indica si la pantalla cambia según el rol.

### 6.1 Conteo (`/contar/**`, móvil primero; ambos roles)

| Ruta | Pantalla | CU | Precios |
|---|---|---|---|
| `/login`, `/invitacion/:token` | Iniciar sesión; aceptar invitación | ACC-01, 03 | — |
| `/contar` | Inicio del contador (4.2.1): sesión abierta, avance, pendientes por ubicación, actividad reciente, botón "Escanear" | SES-02, DSH-01, 02 | **Sin ningún precio para el contador** |
| `/contar/escanear` | Escáner + "Escribir código" + cámara denegada | CAT-01, VER-05 | — |
| `/contar/activo/:codigo` | Ficha / verificar con un toque; ubicación distinta; daño | VER-01..03 | **Admin ve precio de referencia; contador no** |
| `/contar/nuevo?codigo=` | Alta por escaneo (nombre, precio, categoría, ubicación; copiar de un parecido) | CAT-02, 03 | **El contador escribe el precio y después no lo ve** |
| `/contar/pendientes` | Activos sin verificar de la sesión | VER-04, SES-02 | — |
| `/contar/activo/:codigo/historial` | Línea de tiempo del activo | HIS-01 | **Contador no ve eventos ni valores de precio** |
| (estado en todas) | "No se pudo confirmar / Reintentar"; "La sesión se cerró" | VER-06, SES-04 | — |

### 6.2 Administración (`/admin/**`, escritorio; solo `admin`)

| Ruta | Pantalla | CU | Precios |
|---|---|---|---|
| `/admin` | Inicio / Resumen (4.2): indicadores, último informe, gráficas, evolución, actividad | DSH-01..04 (reúne SES-02, INF-01, INF-02, DIS-01, HIS-01) | Solo admin |
| `/admin/activos` | Tabla de datos; ficha con editar, mover, estado, baja | CAT-04..08 | Admin ve todo |
| `/admin/ubicaciones` | Árbol sede > sala > box; crear, editar, desactivar | UBI-01..03 | — |
| `/admin/categorias` | Lista cerrada de categorías | CAT-09 | — |
| `/admin/sesiones` | Lista; abrir; detalle con avance y cierre | SES-01..03 | — |
| `/admin/sesiones/:id/discrepancias` | Esperada vs. encontrada; aplicar | DIS-01, 02 | — |
| `/admin/sesiones/:id/informe` | Tres cifras, por categoría y ubicación, lista de no encontrados con marca "en reparación", exportar PDF/Excel | INF-01, 03 | Solo admin |
| `/admin/valor` | Valor en tiempo real (separado del informe) | INF-02 | Solo admin |
| `/admin/usuarios` | Usuarios e invitaciones (enlace de un solo uso, se muestra una vez) | ACC-02, 05 | — |
| `/admin/activos/:id/historial` | Línea de tiempo completa con antes/después | HIS-01 | Admin ve todo |

El admin también puede usar `/contar/**` (con precio de referencia donde corresponda).

## 7. Wireframes (texto)

Convención: `[ Botón ]` = objetivo ≥ 44 px; `( )` = campo; `▓` = acción principal; `●` = chip de estado de red. Cifras y nombres ficticios.

### 7.1 (a) Escáner, entrada manual y cámara denegada (375 px)

```
Cámara activa                     Cámara denegada
┌─────────────────────────┐      ┌─────────────────────────┐
│ ←  Conteo nov · Sala 2 ●│      │ ←  Conteo nov · Sala 2 ●│
├─────────────────────────┤      ├─────────────────────────┤
│ ┌─────────────────────┐ │      │ ┌─────────────────────┐ │
│ │   ┌─────────────┐   │ │      │ │ ⚠ Sin acceso a la   │ │
│ │   │ ▌▌▐▌▐▐▌▌▐▌  │   │ │      │ │   cámara. Actívala  │ │
│ │   └─────────────┘   │ │      │ │   en el navegador.  │ │
│ │  Apunta al sticker  │ │      │ └─────────────────────┘ │
│ └─────────────────────┘ │      │ [ Reintentar cámara ]   │
│ Verificados hoy  12     │      │ Código del sticker      │
│ Poca luz   [ Linterna ] │      │ (_____________________) │
├─────────────────────────┤      ├─────────────────────────┤
│ [   Escribir código   ] │      │ ▓[       Buscar      ]▓ │
└─────────────────────────┘      └─────────────────────────┘
```

- Con cámara la acción es **apuntar** (lee sola); "Escribir código" queda en la barra inferior como secundaria `outline`, siempre visible.
- Denegada: el campo pasa a principal y se enfoca solo; `inputmode` `[PENDIENTE: según P9]`.
- Lectura repetida del mismo código en < 1 s = una sola consulta (CU-CAT-01). "Linterna" solo si el navegador la expone.
- Se teclea: nada con cámara; solo el código si falla.

### 7.2 (b) Sticker encontrado: verificar con un toque (375 px)

```
Contador (sin precio)             Admin (con precio de referencia)
┌─────────────────────────┐      ┌─────────────────────────┐
│ ←  Conteo nov · Sala 2 ●│      │ ←  Conteo nov · Sala 2 ●│
├─────────────────────────┤      ├─────────────────────────┤
│ Autoclave 18 L          │      │ Autoclave 18 L          │
│ 000123 · [Biomédicos]   │      │ 000123 · [Biomédicos]   │
│ ┌─────────────────────┐ │      │ ┌─────────────────────┐ │
│ │ Esperada  Sala 2>Box1│ │      │ │ Esperada  Sala 2>Box1│ │
│ │ Encontrada Sala 2  ✓ │ │      │ │ Encontrada Sala 2  ✓ │ │
│ │ Estado    [Ok]       │ │      │ │ Estado    [Ok]       │ │
│ └─────────────────────┘ │      │ │ Precio ref. $4.200.000│ │
│ [ Cambiar ubicación ]   │      │ └─────────────────────┘ │
│ [ Marcar dañado ]       │      │ [ Cambiar ubicación ]   │
├─────────────────────────┤      ├─────────────────────────┤
│ ▓[     Confirmar     ]▓ │      │ ▓[     Confirmar     ]▓ │
└─────────────────────────┘      └─────────────────────────┘
```

- Acción principal: **Confirmar**, fija abajo, ancho completo. Ubicación = la de la sala de trabajo; estado = `ok` por defecto.
- Confirmar genera el UUID en el cliente; el botón pasa a "Guardando…" y no admite doble toque; el chip `●` muestra "Enviando…".
- Éxito: banda verde "Verificado" + vuelta al escáner en ≤ 1 s. Vibración/sonido `[PENDIENTE]`.
- Ubicación distinta: sheet inferior con `LocationPicker`; se guarda como observación (CU-VER-02): "Se registra como diferencia; no mueve el activo".
- Ya verificado: aviso "Ya verificado a las 10:42. Si confirmas de nuevo, se guarda otra verificación y cuenta la más reciente" (solo `INSERT`; cuenta la de mayor `seq`).

### 7.3 (c) Sticker NO encontrado: alta por escaneo (375 px)

```
┌─────────────────────────┐
│ ←  Nuevo activo        ●│
├─────────────────────────┤
│ Código  000457 (fijo)   │
│ ( Copiar de un parecido ⌄)│  ← command de búsqueda
│ Nombre                  │
│ (Silla ergonómica…    ) │  ← autocompleta
│ Precio (COP)            │
│ ($ __________________ ) │  ← numérico
│ Categoría [Mobiliario ⌄]│
│ Ubicación [Sala 2     ⌄]│  ← última usada
│ ▸ Más datos (serial,    │
│   marca, modelo, fecha) │
├─────────────────────────┤
│ ▓[   Guardar activo  ]▓ │
└─────────────────────────┘
```

- Prellenados: código (inmutable), categoría y ubicación (última usada o de la sesión).
- "Copiar de un parecido" rellena categoría, nombre, marca, modelo, subtipo, ubicación y precio. Para el contador el precio se copia en el servidor y el campo **no** aparece relleno (CU-CAT-03; editar al duplicar `[PENDIENTE]`).
- Código por entrada manual: confirmar el código antes de guardar. Validación junto al campo y en el servidor.
- Éxito: "Activo creado" + "Verificarlo ahora" (si hay sesión) / "Escanear otro". Meta: < 30 s (C4).

### 7.4 (d) "No se pudo confirmar / Reintentar" (375 px)

```
┌─────────────────────────┐
│ ←  Conteo nov · Sala 2 ●│  ← chip "No confirmado" (ámbar)
├─────────────────────────┤
│ ┌─────────────────────┐ │
│ │ ⚠ No se pudo        │ │  ← fondo ámbar suave, borde ámbar
│ │   confirmar         │ │
│ │ Autoclave 18 L      │ │
│ │ No sabemos si quedó │ │
│ │ guardado. Reintentar│ │
│ │ no lo duplica.      │ │
│ └─────────────────────┘ │
├─────────────────────────┤
│ [ Descartar y seguir ]  │
│ ▓[     Reintentar    ]▓ │
└─────────────────────────┘
```

- **Reintentar** reenvía con el mismo UUID; el servidor nunca duplica. La verificación no cuenta en el avance hasta confirmarse.
- "Descartar y seguir" pide confirmación: no se guardó (sin cola offline, ADR-002); cerrar la pestaña la pierde.
- `409 sesion_cerrada`: se reemplaza por `alert` rojo "La sesión se cerró; esta verificación no se guardó", **sin** Reintentar (CU-SES-04).

### 7.5 (e) Informe de sesión (≥ 1024 px, solo admin)

```
┌────────────┬─────────────────────────────────────────────────────────┐
│AssetControl│ ☰  Sesiones / Conteo nov 2026 / Informe   (Buscar ⌘K) (A)│
│            ├─────────────────────────────────────────────────────────┤
│ Inicio     │ Informe de sesión         [Exportar Excel] ▓[Exportar PDF]│
│ Activos    │ [Informe congelado] Corte 11/11/2026 · Cerrada 17:40     │
│ Ubicaciones│ ┌───────────────┐ ┌───────────────┐ ┌────────────────┐ │
│ Categorías │ │ Encontrado    │ │ No encontrado │ │Total registrado│ │
│ Sesiones ◂ │ │$90.000.000,00 │ │$10.000.000,00 │ │$100.000.000,00 │ │
│ Valor      │ │180 unidades   │ │20 unidades    │ │200 unidades    │ │
│ Usuarios   │ └───────────────┘ └───────────────┘ └────────────────┘ │
│            │ [Resumen] [Por categoría] [Por ubicación] [No encontr.] │
│ Ir a contar│ Categoría      Encontrado  No encontrado  Total reg.    │
│            │ Mobiliario          $ …            $ …          $ …    │
└────────────┴─────────────────────────────────────────────────────────┘
```

- Acción principal: **Exportar** (PDF y Excel con las mismas cifras que la pantalla, en COP).
- Las tres cifras y las pestañas por categoría y por ubicación son del servidor, congeladas al cerrar (R4, R9); la pantalla no recalcula.
- Pestaña **No encontrados**: tabla de la lista congelada al cierre (código, nombre, categoría, ubicación, precio), leída de `sesion_no_encontrado` (R9a); los que estaban en reparación al cierre llevan la insignia "En reparación" para no confundirlos con un faltante. La marca y la lista vienen del servidor y no se reconstruyen con el estado actual. Solo admin: la lista trae precios y el servidor no la entrega al contador (P13). La exportación incluye la misma lista. Total = encontrado + no encontrado se verifica en pruebas, no en la UI.
- "Ver valor actual" lleva a `/admin/valor`, otra pantalla con otro rótulo (R7). Sesión abierta: estado vacío; vista previa "no definitiva" `[PENDIENTE]`.

### 7.6 (f) Inicio / Resumen de admin (1440 px)

```
┌────────────┬─────────────────────────────────────────────────────────┐
│AssetControl│ ☰  Inicio                          (Buscar activo ⌘K) (A)│
│            ├─────────────────────────────────────────────────────────┤
│ Inicio   ◂ │ Resumen                                ▓[Abrir sesión]  │
│ Activos    │ ┌─────────┐┌────────────┐┌──────────┐┌────────┐┌────────┐│
│ Ubicaciones│ │Activos  ││Valor actual││Conteo nov││Discrep.││Dañados ││
│ Categorías │ │200      ││$100.000.000││120 de 200││3       ││4       ││
│ Sesiones   │ │hoy      ││No es inform││███▒▒ 60 %││sin res.││o en rep││
│ Valor      │ └─────────┘└────────────┘└──────────┘└────────┘└────────┘│
│ Usuarios   │ ┌ Último informe cerrado · Informe congelado · corte 12/05 ┐│
│            │ │ Encontrado $90.000.000 · No enc. $10.000.000 · Total $100.000.000 │
│            │ └──────────────────────────────────────────────────────────┘│
│            │ Valor por categoría        Evolución entre conteos [Todas ⌄]│
│            │ Valor actual (no es inf.)  Valor registrado y % encontrado │
│            │ Biomédicos ██████████ 48 M  100M ┤      ●───●            │
│            │ Mobiliario ████▌      21 M       ┤ ●───●       ── valor   │
│            │ CPU        ███▌       18 M  100% ┤ ○───○───○───○ ·· %     │
│            │ Electrón.  ██▌        13 M       └─may25─nov25─may26─nov26│
│            │ (Valor por ubicación: misma forma, debajo)                │
│            │ Actividad reciente                         Ver todo →  │
│            │ Fecha        Usuario    Evento            Activo        │
│            │ 11/11 10:42  Contador 1 Verificado        Autoclave 18 L│
│            │ 11/11 10:40  Contador 1 Activo creado     Silla ergon.  │
│ Ir a contar│ 11/11 09:15  Admin      Sesión abierta    —             │
└────────────┴─────────────────────────────────────────────────────────┘
```

- Acción principal: **Abrir sesión** solo si no hay una abierta; si la hay, la principal es "Ver sesión".
- Cada tarjeta enlaza a su detalle; las cifras vienen del servidor con la hora de consulta. La tarjeta "Valor actual" no se confunde con el informe (R7): va en su propia tarjeta, y el último informe en otra con el rótulo "Informe congelado".
- **Valor por categoría** (y **por ubicación**, misma forma): barras horizontales ordenadas de mayor a menor, cifras en COP abreviadas en la barra y completas en el tooltip; el rótulo de la fuente es obligatorio ("Valor actual" o "Último informe cerrado", P23). Nunca mezcla fuentes.
- **Evolución entre conteos**: un punto por sesión cerrada de tipo conteo (eje: fecha de corte); serie de valor registrado y serie de % encontrado (lo calcula el servidor, en unidades por defecto; precisión `[PENDIENTE]` P24, recomendación un decimal), con selector de categoría. Lee el desglose congelado; cada punto lleva al informe de su sesión. Sin sesiones cerradas: "Aún no hay conteos cerrados".
- Las gráficas no son el único canal: cada una tiene un enlace "Ver como tabla" o tooltip con la cifra exacta (accesibilidad, sección 9). Fechas y montos del ejemplo son ficticios.

### 7.7 (g) Tabla de Activos de admin (1440 px)

```
┌────────────┬─────────────────────────────────────────────────────────┐
│AssetControl│ ☰  Inventario / Activos            (Buscar activo ⌘K) (A)│
│            ├─────────────────────────────────────────────────────────┤
│ Inicio     │ Activos                                  ▓[Exportar]    │
│ Activos  ◂ │ (Buscar código o nombre) [Categoría ⌄][Ubicación ⌄]     │
│ Ubicaciones│ [Estado ⌄]  Limpiar                                     │
│ Categorías │ Código↕ Nombre↕        Categoría  Ubicación  Estado   Precio ref.│
│ Sesiones   │ 000123  Autoclave 18 L Biomédicos Sala2>Box1 [Activo]  4.200.000 ⋯│
│ Valor      │ 000124  Silla ergonóm. Mobiliario Sala 2     [Activo]    350.000 ⋯│
│ Usuarios   │ 000131  Compresor      Biomédicos Bodega   [En repar.] 2.900.000 ⋯│
│            │ …                                                       │
│ Ir a contar│ 1–25 de 200        Filas [25 ⌄]   [‹ Anterior][Siguiente ›]│
└────────────┴─────────────────────────────────────────────────────────┘
```

- `⋯` abre Ver, Editar (sheet lateral), Mover, Historial y Dar de baja (con `alert-dialog`). Precio alineado a la derecha, `tabular-nums`, en COP.
- No hay "Nuevo activo": el alta es por escaneo (CU-CAT-02); el vacío ofrece [Ir a escanear]. Edición concurrente: `412` con aviso (sección 8).

## 8. Estados y mensajes

Tono: breve, directo, sin tecnicismos ni culpa al usuario. Tuteo.

| Pantalla | Cargando | Vacío (con acción) | Error (con reintento) | Éxito visible |
|---|---|---|---|---|
| Escáner | "Abriendo cámara…" | — | "No pudimos leer el código. Acércate o escríbelo." [Escribir código] · "Sin acceso a la cámara" [Reintentar cámara] | Ficha del activo; vibración/sonido `[PENDIENTE]` |
| Ficha / verificar | Esqueleto de tarjeta | "No encontramos ese código." [Crear activo] [Escribir otro] | "No se pudo confirmar" [Reintentar] · "La sesión se cerró; esta verificación no se guardó" | "Verificado" (banda verde, 1 s) |
| Alta por escaneo | "Guardando…" | — | "No se pudo guardar. Revisa la conexión." [Reintentar] · "Escribe el precio" · "Ese código ya existe" [Abrir activo] | "Activo creado" [Escanear otro] |
| Pendientes | Esqueleto de lista | "No quedan activos por verificar" | "No se pudo cargar" [Reintentar] | — |
| Inicio de conteo | Esqueleto | "No hay una sesión abierta. Pídele al administrador que abra una." | "No se pudo cargar" [Reintentar] | — |
| Inicio admin | Esqueleto de tarjetas, gráficas y filas | "Aún no hay activos ni sesiones." [Ir a escanear] · Evolución: "Aún no hay conteos cerrados" · Último informe: "Todavía no hay un informe cerrado" | "No se pudo cargar" [Reintentar] (por tarjeta o gráfica, sin tumbar la página) | — |
| Historial | Esqueleto de línea de tiempo | "Este activo aún no tiene movimientos" | "No se pudo cargar" [Reintentar] | — |
| Activos (admin) | Esqueleto de filas | "Aún no hay activos. Escanea un sticker para crear el primero." [Ir a escanear] · Con filtros: "Nada coincide." [Limpiar filtros] | "No se pudo cargar" [Reintentar] · `412`: "Alguien cambió este activo. Recargamos; revisa tus cambios" | "Cambios guardados" (toast) |
| Ubicaciones | Esqueleto de árbol | "Crea la primera sede." [Crear ubicación] | "No se pudo guardar" [Reintentar] | "Ubicación creada" |
| Sesiones | Esqueleto de filas | "No hay sesiones. Abre la primera." [Abrir sesión] | "No se pudo cargar" [Reintentar] | "Sesión abierta" |
| Cerrar sesión | "Cerrando…" | — | "No se pudo cerrar" [Reintentar] | "Sesión cerrada. Informe listo." [Ver informe] |
| Discrepancias | Esqueleto de filas | "Sin diferencias de ubicación" | "No se pudo aplicar" [Reintentar] · "El activo ya se movió. ¿Aplicar de todos modos?" | "Ubicación actualizada" |
| Informe | Esqueleto de tarjetas | "El informe se genera al cerrar la sesión." [Ir a la sesión] | "No se pudo cargar el informe" [Reintentar] | "Archivo descargado" |
| Valor en tiempo real | Esqueleto | "Sin activos registrados" | "No se pudo cargar" [Reintentar] | "Valor actual al [hora]. No es el informe de una sesión." |
| Usuarios / invitaciones | Esqueleto | "Aún no has invitado a nadie." [Invitar] | "No se pudo crear la invitación" [Reintentar] | "Enlace creado. Cópialo ahora: no se vuelve a mostrar." |
| Buscador global | "Buscando…" | "Sin resultados para «…»" | "No se pudo buscar" [Reintentar] | Salta a la ficha |
| Login / invitación | "Entrando…" | — | "Correo o contraseña incorrectos" (genérico) · "Enlace vencido o ya usado. Pide uno nuevo." | Redirección según rol |
| Sin permiso | — | — | "No tienes permiso para ver esto." [Volver] | — |

## 9. Accesibilidad y móvil

- **Foco**: anillo visible (`--ring`, 2 px) en todo control; orden de tabulación = orden visual; tras confirmar una verificación el foco vuelve al visor o a "Escanear otro". En admin, la barra lateral y el buscador son operables con teclado.
- **Toque**: ≥ 44 × 44 px en `/contar/**`, ≥ 8 px entre objetivos; acción principal a ancho completo. Sin gestos como única vía.
- **Una mano**: acciones principales y sheets en el tercio inferior; navegación superior solo de retroceso.
- **Poca luz**: "Linterna" si el navegador lo permite; "Poca luz" tras ~3 s sin lectura `[PENDIENTE: umbral]`; siempre queda "Escribir código".
- **Sol directo**: texto principal en `--foreground` casi negro, 16 px o más, sin gris claro para datos críticos; la acción principal es un botón sólido, no de contorno.
- **Color no es el único canal**: ícono + texto en éxito, error y aviso.
- **Lectores de pantalla**: resultados de verificación en `aria-live="polite"`; errores con `aria-describedby`; botones de ícono con `aria-label`; tablas con encabezados reales y orden anunciado (`aria-sort`).
- **Formularios**: `inputmode`, `autocomplete` y `enterkeyhint` adecuados; 16 px mínimo en campos móviles; etiquetas visibles.
- **Movimiento**: transiciones cortas (colapsar barra, abrir sheet); respetar `prefers-reduced-motion`.
- **Verificación**: Playwright para el flujo de conteo; capturas en navegador real a 375 px y 1440 px (skill `browser-qa`); teléfonos reales de P4; contraste medido con herramienta.

## 10. Qué NO se diseña ahora y decisiones pendientes

| Tema | Motivo |
|---|---|
| Conteo offline, cola persistente, Service Worker | Fuera de alcance (ADR-002) |
| Impresión o generación de etiquetas | Fuera de alcance; el `codigo` lo trae el sticker |
| Pantalla de importación del Excel | No se construye ahora (P10) |
| Fotos de activos y verificaciones | `[PENDIENTE]` (P18; recomendación: diferir) |
| App nativa, notificaciones push | Fuera de alcance (ADR-001) |
| Pantalla de alta de tenant | Se crea por script (03) |

### Decisiones `[PENDIENTE]` de diseño

1. Base neutra (zinc o slate) y hex definitivos de neutros, acento y estados, tras medir contraste (sección 2.1).
2. Botón principal: neutro oscuro (recomendado) o en el acento.
3. Fuente de producto: Inter o Geist autoalojada, o quedarse con la pila del sistema (dependencia nueva).
4. Modo oscuro: dentro o fuera del MVP.
5. Dependencias: `lucide-react` (íconos), `@tanstack/react-table` (tablas) y `recharts` (gráficos del Inicio, vía el componente `chart` de shadcn/ui; spec 010), además de las que arrastre cada componente de shadcn/ui.
6. Alcance del buscador global (recomendación: activos y navegación).
7. Paginación, orden y filtro en cliente o en servidor.
8. "Actividad reciente": ¿pantalla de actividad global o solo historial por activo? Discrepancias: ¿entrada propia en la barra lateral?
9. Acción principal de la tabla de Activos ("Exportar" u otra) y ancho máximo del contenido.
10. Admin en pantallas < 1024 px: usable sin optimizar (recomendado) u optimizado.
11. Vibración y sonido al verificar, y si el usuario puede apagarlos.
12. Rutas definitivas (sección 6) y `inputmode` del campo de código (P9).
13. Nombre y logo del producto (T9); hasta entonces, texto "AssetControl".
14. Contador: ¿ve discrepancias de su conteo? (CU-DIS-01), ¿sesiones pasadas? (CU-HIS-02), ¿puede editar el precio al duplicar sin verlo? (CU-CAT-03), ¿qué ve en su Inicio? (P25).
15. Vista previa "no definitiva" del informe con sesión abierta; "buscado y no hallado" frente a "sin verificar" (P16); umbral de "Poca luz".
16. Nombre y número de la spec de sistema de diseño y app shell (sección 11).
17. Inicio de admin: fuente por defecto de las gráficas por categoría y ubicación (P23), cuántos conteos muestra la evolución (P22) y base del % encontrado (P24).

## 11. Siguientes pasos

1. **No más prototipos hechos a mano.** El diseño se valida sobre la web real, con los componentes reales.
2. **Spec corta de "sistema de diseño y app shell"** `[PENDIENTE: nombre y número, decisión humana]`, **después de T8** de [specs/001-fundacion-tecnica](../specs/001-fundacion-tecnica/tasks.md). Monta el shell real (`AdminShell` y `CountShell`) con componentes de shadcn/ui, el tema de la sección 2 y **datos ficticios**, sin backend de negocio: Inicio, tabla de Activos, informe y las pantallas (a)–(d) de conteo como maquetas navegables. Declara para aprobación todas sus dependencias (las que arrastre `npx shadcn@latest add`, `lucide-react`, `@tanstack/react-table`, la fuente si se aprueba y `recharts` solo si la maqueta del Inicio incluye gráficas; si no, las gráficas llegan con la spec 010). T8 sigue limitada a su criterio (esqueleto, tema base y un componente); cualquier ajuste a T8 pasa por el planner y el humano.
3. **Revisión antes de mostrar**: cada pantalla se revisa con capturas en navegador real a **375 px** y a **1440 px** (skill `browser-qa`), con contraste medido y estados (cargando, vacío, error, éxito) recorridos, **antes** de presentarla al humano.
4. **Aprobación humana con las capturas**: el humano aprueba o pide cambios sobre las capturas; con eso se fijan los hex, la fuente y los `[PENDIENTE]` que afecten a las specs 004 y 006 (escáner y verificación). Las pantallas reales con datos llegan en las specs 002–010.
