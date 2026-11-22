# Tasks 016 — Rediseño visual con biblioteca propia de componentes

Diez tareas, cada una ≤ 1 día, cada una un slice con tests primero. Comandos desde `web/`. Una tarea a la vez.

**Definición de «terminado» (aplica a todas):** (1) pruebas nuevas escritas primero y en verde (las de caracterización pasan antes contra la pantalla actual); (2) `npm test` completa en verde, ≥ 546 pruebas; (3) `npm run lint` y `npm run typecheck` limpios; (4) capturas a 375 y 1440 px de cada pantalla tocada en `specs/016-rediseno-ui-componentes/capturas/` (local, sin versionar), consola sin errores, sin scroll horizontal, axe sin infracciones AA; (5) la lista de excepciones de `kit.node.test.ts` se reduce con la familia migrada; (6) `git diff --stat` sin cambios en `backend/`, `docs/`, `web/src/lib/api/` ni `web/package.json`; (7) revisión del `reviewer`; (8) toda edición a una prueba existente se anota en la tarea (solo import o selector visual, nunca comportamiento).

## T1 — Tokens y base visual — [x] a4e5371 (2026-11-18)

- **Resultado:** `index.css` con los tokens de plan §3 (`--page`, `--ink`, `--primary` cobalto, `--radius` 0,625 rem, densidad, escala tipográfica) y `AdminShell`/`CountShell` fijando `data-densidad`; toda la app ya se ve con el nuevo fondo y botón principal sin tocar pantallas. Galería `/dev/componentes` muestra paleta, tipografía y densidades.
- **Archivos probables:** `web/src/index.css`, `web/src/theme.node.test.ts`, `web/src/components/ui/variants.test.tsx`, `web/src/routes/dev/Componentes.tsx`, `web/src/components/app/AdminShell.tsx`, `web/src/components/app/CountShell.tsx`.
- **Verificación:** `npm test -- theme variants Componentes AdminShell CountShell && npm run lint && npm run typecheck && npm run dev` (abrir `/dev/componentes` a 375 y 1440 px).
- **Dependencia:** ninguna. Es la primera tarea ejecutable.
- **Notas:** pruebas rojas primero (hex de 6 dígitos, contraste AA por cálculo de cada par del plan §3, sin literales fuera de `index.css`). `variants.test.tsx` puede cambiar solo en el selector de clase del botón principal; anotarlo.

### Deuda T1

- (a) T5: revisar el chip activo de `routes/contar/Pendientes.tsx:143` (ahora cobalto). — RESUELTA por T5 (fd89a11): pestañas subrayadas del kit.
- (b) T5/T6: verificar el contraste de la tecla `primary-foreground/10` en `FormularioAlta.tsx:63` y `Escritorio.tsx:1080`. — RESUELTA por T6 (94b72f6): componente `Tecla` con tono `sobrePrincipal` y contraste probado.
- (c) T4: estado activo de la barra lateral blanca y fondo de `/login`. — RESUELTA por T4 (f3f6085).
- (d) T2: inputs transparentes sobre `--page` (`Campo`). — RESUELTA por T2 (2746ca7).
- (e) T8: pie de `RegistrarActivo` con `bg-sidebar`. — RESUELTA por T8 (700ce1d).
- (f) T10: el parser de `theme.node.test.ts` es frágil ante `@media` anidado; confirmar que `data-densidad` llega al DOM de `SidebarProvider` y a los diálogos en portal.
- (g) axe real sin instalar.
- (h) El esqueleto `bg-foreground/6` no está en la prueba de contraste.

## T2 — Primitivos A: Boton, Campo, Insignia, Aviso, Estado — [x] 2746ca7 (2026-11-18)

- **Resultado:** `components/kit/` creado con `Boton`, `Campo`, `Insignia`, `Aviso` y `Estado` (cargando/vacío/error), con `index.ts`, pruebas y entrada en la galería. `EstadoActivoBadge`, `EmptyState`, `ConEstado` y `CampoFormulario` mantienen su API y delegan en el kit. Se crea `kit.node.test.ts` con la lista de excepciones inicial (todas las pantallas actuales que importan `ui/`).
- **Archivos probables:** `web/src/components/kit/{Boton,Campo,Insignia,Aviso,Estado,index}.tsx`, `kit.node.test.ts`, `web/src/components/app/{EstadoActivoBadge,EmptyState,ConEstado,CampoFormulario}.tsx`, `web/src/routes/dev/Componentes.tsx`.
- **Verificación:** `npm test -- kit EstadoActivoBadge ConEstado Campo datos && npm run lint && npm run typecheck`.
- **Dependencia:** T1.

### Deuda T2

- (a) `Componentes.test.tsx` solo ganó una prueba.
- (b) T10: comprobar altura computada y orden de CSS: `h-control`, `h-accion` y `size-control` ganan a `h-8`/`size-8` de shadcn por orden de CSS (tailwind-merge no los reconoce). e2e con `getComputedStyle().height` o configurar tailwind-merge.
- (c) T10: `ring-offset-background` es blanco sobre `--page`.
- (d) `Campo` selección: `value={valor}` queda no controlado si `valor` es undefined (usar `valor ?? ''` o documentarlo).
- (e) `Boton asChild` ignora `cargando`/`icono`/`soloIcono`: documentarlo en el comentario de la prop.
- (f) T10: retirar el selector de compatibilidad `bg-card` de `CampoFormulario` y el selector descendiente de `Estado.Vacio`. — Selector `bg-card` de `CampoFormulario` RESUELTO por T9 (2a5ff97): retirado, con guardia de que ninguna pantalla importa `CampoFormulario`; sigue el selector descendiente de `Estado.Vacio` (T10).
- (g) Cada pantalla con `CampoFormulario` (Alta T6, FichaActivo T8, Empresa T9) se revisa visualmente en su tarea.
- (h) La guardia `kit.node.test.ts` no detecta template literals en `import()` y solo cubre `routes/**`.
- (i) Sin axe.

## T3 — Primitivos B: Panel, EncabezadoPagina, ListaDatos, Cifra, Dialogo, Confirmar, BarraAccion, Pestanas, Filtro, TablaDatos — [x] 90da567 (2026-11-19)

- **Resultado:** resto del kit con estados integrados; `TablaDatos` con búsqueda, filtros, orden accesible, paginación, fila clicable/doble clic y vista de tarjetas por debajo de `md`; `StatCard` y `FigureCards` delegan en `Cifra` conservando los rótulos «Informe congelado» / «Valor actual (no es el informe)». Todo documentado en la galería con datos ficticios.
- **Archivos probables:** `web/src/components/kit/*.tsx` (10 archivos con sus pruebas), `web/src/components/app/{StatCard,FigureCards}.tsx`, `web/src/routes/dev/Componentes.tsx`.
- **Verificación:** `npm test -- kit StatCard datos Componentes && npm run lint && npm run typecheck` y galería a 375 y 1440 px.
- **Dependencia:** T2. Si no cabe en un día, `TablaDatos` pasa a su propia tarea vía `/sdd-change` (no se abre una T11 sin documentarla).

### Deuda T3

- (a) T8: `Confirmar` solo hace `preventDefault` si `confirmando` ya es true; la pantalla debe controlar `abierto` y cerrar al terminar (015: «¿Enviar a reparación?»). Falta prueba del primer clic con `abierto` controlado. — RESUELTA por T8 (700ce1d): `abierto` controlado y prueba del primer clic.
- (b) `ListaDatos` con `valor: false` deja un `<dd>` vacío: tratarlo como ausente y probarlo. — RESUELTA por T8 (700ce1d).
- (c) `Dialogo` lateral con `devolverFocoA` explícito y `onCloseAutoFocus` sin prueba. — RESUELTA por T8 (700ce1d).
- (d) T4: probar que `h-control` gana a `h-8` en `ui/input`. — RESUELTA por T4 (f3f6085) con `cascada.node.test.ts` (prueba el orden de reglas, no la altura computada: sigue abierta Deuda T2 (b) para T10).
- (e) El título de `Aviso` no recibe `text-cuerpo` (14 px en 375 en vez de 16): span interior.
- (f) T10: declarar `h-control`, `size-control` y `h-fila` en `createCn` o resolver cómo `components/ui` usa el `cn` del paquete sin extender.
- (g) `Filtro` sin buscador interno: revisar ubicaciones largas en T8.
- (h) `TablaDatos` en forma `desplazar` (primera columna fija) sin verificar en navegador: T7. — RESUELTA por T7 (5d58b3e): verificada en navegador en Informe y Valor a 375 px (queda Deuda T7 (a)).
- (i) Indentación de `DialogDescription`/`SheetDescription` en `Dialogo.tsx` (prettier).
- (j) T7: revisar con `domain-guardian` el cambio de `StatCard`/`FigureCards` a `Cifra` (en vivo vs congelada). — RESUELTA por T7 (5d58b3e): revisada y aprobada por el `domain-guardian`.
- (k) Sin axe.
- (l) docs/08: `StatCard`→`Cifra` con insignia «Tiempo real» y «No es el informe», barra de acción sticky, tarjetas de Activos en dos columnas en teléfono.

## T4 — Shells, acceso y pantallas de sistema — [x] f3f6085 (2026-11-19)

- **Resultado:** `AdminShell` (barra lateral blanca, ítem activo con barra de acento, encabezado con migas, buscador, menú de cuenta) y `CountShell` (encabezado compacto, `BarraAccion` con área segura) rediseñados con el kit; `Login`, `Invitacion`, `MarcoAcceso`, `SinPermiso`, `SinConexion`, `NoEncontrado` y `PantallaCarga` migradas. Buscador global (`Ctrl/⌘ K`), colapso y menú móvil intactos.
- **Archivos probables:** `web/src/components/app/{AdminShell,CountShell,MenuCuenta,GlobalSearch,MarcoAcceso,Logo}.tsx`, `web/src/routes/{Login,Invitacion,SinPermiso,SinConexion,NoEncontrado,PantallaCarga}.tsx`.
- **Verificación:** `npm test -- AdminShell CountShell GlobalSearch acceso Invitacion && npm run lint && npm run typecheck`; QA de login y shells a 375 y 1440 px.
- **Dependencia:** T3.

### Deuda T4

- (a) `CountShell.test.tsx` cambió `size-11`→`size-control` sin perder aserciones (anotado).
- (b) `Invitacion.tsx:79-85`: al mostrarse `errorClave` desaparece la política «Entre 10 y 128 caracteres. Evita contraseñas comunes.»; fusionar ayuda y error (T10 o antes).
- (c) `cascada.node.test.ts` es frágil: rutas fijas a `node_modules` (tw-animate-css, shadcn) y regex sobre `ui/input`.
- (d) No se creó el componente `Navegacion` del contrato (la receta de D8 vive en `ITEM_NAV` de `AdminShell`): llevarlo al kit en T10 o vía `/sdd-change`.
- (e) Sin enlace «Saltar al contenido».
- (f) Menú móvil de admin: «Ir a contar» y la tarjeta de la clínica quedan pegados al pie, sin separación.
- (g) T5: los consumidores de `acciones` en `/contar` aún ponen `min-h-14` a mano. — RESUELTA por T5 (fd89a11): `BarraAccion` fija la altura; `min-h-14` queda solo en `Alta.tsx` (T6). — `min-h-14` de `Alta.tsx` RESUELTO por T6 (94b72f6).
- (h) Sin prueba de teclado/lector en el botón del ojo ni en el menú móvil.
- (i) Sin axe.
- (j) docs/08: barra lateral blanca con ítem activo `brand-soft` + barra de acento, marco común de acceso y sistema, texto «Comprobando la sesión», avisos admin abajo-derecha y conteo arriba-centro, encabezado de conteo blanco con objetivos de 48 px, textos de carga «Entrando…».

## T5 — `/contar`: Inicio, escáner, verificar, pendientes, historial — [x] fd89a11 (2026-11-19)

- **Resultado:** las cinco pantallas del flujo de conteo en móvil con kit, objetivos de 48 px, `BarraAccion` fija, `NetworkStatus` e `Insignia` unificados; «No se pudo confirmar» (ámbar, Reintentar) y «Verificado» siguen siendo claramente distintos; el contador no ve hueco de precio. Caso de `409 sesion_cerrada` sin «Reintentar» intacto.
- **Archivos probables:** `web/src/routes/contar/{Inicio,Escanear,Escribir,Verificar,Pendientes,Historial}.tsx`, `web/src/components/app/{NetworkStatus,Escaner,AssetCard,PendingList,LineaDeTiempo}.tsx` y sus pruebas.
- **Verificación:** `npm test -- contar Verificar Selector Historial Escaner NetworkStatus FotoVerificacion maquetas && npm run lint && npm run typecheck && npm run e2e`.
- **Dependencia:** T4. Revisión extra: `domain-guardian` (verificación, estados de red).

### Deuda T5

- (a) Pruebas existentes editadas solo con adiciones: `CountShell.test.tsx`, `BarraAccion.test.tsx`, `Campo.test.tsx`; `kit.node.test.ts` quitó 6 excepciones (`contar/Escanear`, `Escribir`, `Historial`, `Inicio`, `Pendientes`, `Verificar`); quedan `Alta` y `Escritorio` para T6.
- (b) `Pendientes.tsx:39` usa `min-h-16` a mano y el comentario dice 56 px: usar `min-h-fila` o corregir el comentario.
- (c) `conteoKit.test.tsx` busca `[data-slot=alert-title]` (detalle de `ui/alert`): buscar por rol o texto dentro de `[data-kit=aviso]`.
- (d) T10: el título del encabezado se corta («Conteo nov 20…») con «No confirmado» a 375 px.
- (e) `ui/progress` no pasa `value` a la raíz y sigue en `Escritorio.tsx` y admin Sesiones: sin `aria-valuenow` (T6/T9/T10). — En `Escritorio.tsx` RESUELTA por T6 (94b72f6) con `Progreso`; admin Sesiones sigue (T9/T10). — Inicio admin RESUELTO por T7 (5d58b3e) con `Progreso` (`aria-valuenow`). — Admin Sesiones RESUELTO por T9 (2a5ff97) con `Progreso` (`aria-valuenow`).
- (f) `Progreso` es un componente nuevo fuera del contrato (sobre `radix-ui`, ya dependencia).
- (g) T6: `EstadoFoto` (en `CampoFoto`) usa el `Button` de shadcn; enlaces de `ActividadReciente` de 24 px (T7); «Agregar foto» de `FotoActivo` de 28 px (T8). — `EstadoFoto` RESUELTO por T6 (94b72f6); enlaces de `ActividadReciente` RESUELTOS por T7 (5d58b3e) (la fila entera es el objetivo táctil); «Agregar foto» de 28 px RESUELTO por T8 (700ce1d).
- (h) T6: verificar el contraste de `primary-foreground/10` (Deuda T1 b). — RESUELTA por T6 (94b72f6).
- (i) PRUEBA MANUAL pendiente del humano en `Escritorio.tsx`: `OtraUbicacion` pasó de `Sheet` a `Dialogo` del kit: tras elegir sala el foco debe volver al panel «Verificación» y Enter debe confirmar; la ráfaga del lector USB (50 ms) con el diálogo abierto o recién cerrado; que los atajos globales no se disparen con el diálogo abierto.
- (j) Comprobar con un contador real que no ve precio en `/contar/activo/:codigo`.
- (k) Sin axe.
- (l) docs/08: barra de acción del conteo (`BarraAccion` en `<footer>`, principal 56 px, secundaria 48 px), estado de red como `Insignia`, Inicio con `Progreso` y «Activos hoy» como `Cifra`, Pendientes con pestañas subrayadas, mensajes de pantalla completa con panel tonal, campo del código de 56 px y 24 px de letra, hoja «¿Dónde lo encontraste?» con opciones de 48 px, componente nuevo `Progreso`.

## T6 — `/contar`: alta de activo y modo escritorio — [x] 94b72f6 (2026-11-19)

- **Resultado:** `Alta`, `FormularioAlta`, `CampoFoto`, `CopiarDeParecido`, `InputSugerido`, `LocationPicker` y `contar/Escritorio` (dos paneles de la 015) con el kit; el contador sigue sin ver precios de otros; idempotencia por UUID, foco inicial, `Enter`, lector USB de ráfaga y «Guardar y registrar otro» intactos.
- **Archivos probables:** `web/src/routes/contar/{Alta,Escritorio}.tsx`, `web/src/components/app/{FormularioAlta,CampoFoto,CopiarDeParecido,InputSugerido,LocationPicker}.tsx`, pruebas `AltaActivo`, `Escritorio`, `CampoFoto`.
- **Verificación:** `npm test -- AltaActivo Escritorio CampoFoto Selector && npm run lint && npm run typecheck && npm run e2e`; capturas a 375 y 1440 px.
- **Dependencia:** T5.

### Deuda T6

- (a) B1 (domain-guardian, baja, ACEPTADO por el coordinator): abrir «Está en otra ubicación» con el botón, Esc sin elegir, Enter confirma en la sala vigente porque el foco vuelve al panel «Verificación» (`Escritorio.tsx:1132`, `Dialogo.tsx:69-73`); es idempotente y la sala es visible; revisar si se prefiere devolver el foco al botón cuando se abrió con clic (decisión de UX, T10).
- (b) PRUEBA MANUAL del humano: lector USB real en ráfaga con el diálogo abierto o recién cerrado, atajos globales con el diálogo abierto, B1; contador real sin precio en alta, copia y Escritorio; «Reintentar» tras «No se pudo confirmar» no duplica en el servidor; valor guardado del precio con el nuevo `Campo tipo="dinero"` (verificar en vivo).
- (c) T10: anillo de foco grueso del Panel «Verificación» en `Escritorio.tsx` (~284): suavizar.
- (d) T10: `CopiarDeParecido`, `LocationPicker` e `InputSugerido` conservan `Button`/`Input` de shadcn por dentro (la guardia solo vigila `routes/**`).
- (e) T10: retirar la prop `acciones` de `CountShell` (sin uso) y el selector `bg-card` de `CampoFormulario` (lo usan `RegistrarActivo`, `EditarActivo` y `Empresa`, T8/T9). — Las pantallas de T8 ya no lo usan (700ce1d); siguen `Empresa.tsx` y `Sesiones.tsx`. — Selector `bg-card` RESUELTO por T9 (2a5ff97): retirado de `CampoFormulario`, con guardia de que ninguna pantalla lo importa; sigue la prop `acciones` de `CountShell` (T10).
- (f) T8: `RegistrarActivo` comparte `FormularioAlta` y ya cambió de aspecto. — RESUELTA por T8 (700ce1d).
- (g) El campo de captura de Escritorio pierde el ícono de escáner (campo grande del kit).
- (h) El aviso «Activo anterior sin confirmar» ganó título nuevo (solo texto).
- (i) Confirmar en navegador real que la `BarraAccion` sticky no tapa el último campo del alta a 375 px.
- (j) La caché `web/node_modules/.vite` se reescribió con el servidor de QA: el vite del 5173 puede reoptimizar.
- (k) Sin axe.
- (l) docs/08: componente `Tecla` con tono `sobrePrincipal`; conteo de escritorio a 48 px con cabecera de 72 px y sala en línea; cola con pestañas subrayadas; alta móvil con paneles por bloque y «Más datos» plegable; alta de escritorio con `EncabezadoPagina` y pie del panel en `bg-muted/40`.

## T7 — `/admin`: Inicio, Valor e Informe — [x] 5d58b3e (2026-11-19)

- **Resultado:** tablero con `Cifra`, `Panel` y `Barras` rediseñadas (rótulo de fuente obligatorio y «Ver como tabla» intactos), `Informe` con `Pestanas` y `TablaDatos` (scroll con primera columna fija en móvil), `Valor` con enlace «Volver al informe». «Informe congelado» y «Valor actual» nunca comparten tarjeta.
- **Archivos probables:** `web/src/routes/admin/{Inicio,Valor,Informe}.tsx`, `web/src/components/app/{FigureCards,Barras,ActividadReciente}.tsx` y pruebas.
- **Verificación:** `npm test -- Inicio Valor Informe Barras FigureCards && npm run lint && npm run typecheck`.
- **Dependencia:** T3 y T4 (no depende de T5/T6; puede ir antes si hace falta). Revisión extra: `domain-guardian` (cifras, R7).

### Deuda T7

- (a) Valor a 375 px desplaza 10 px dentro de la tabla (38 px por ubicación con nombres reales): ampliar `CeldaPie` del kit para que el pie herede la clase de columna o acepte `clase` por celda (tarea del kit, T10).
- (b) `StatCard` sin consumidores: borrar en T10. `ErrorDeParte` y `Seccion` exportadas desde `Inicio.tsx` sin otros usos.
- (c) Cambios de aspecto declarados: `Barras.tsx` `break-words md:truncate` (la etiqueta envuelve en móvil); «Ver valor actual» de ghost a secundario; encabezados de `TablaDatos` opacos `bg-muted`; `Esqueleto` y `TablaDatos.pie` nuevos en el kit; la celda de pie con colSpan > 1 ya no es fija en móvil (lo heredan T8/T9).
- (d) Las pruebas nuevas de pie y `Esqueleto` no se corrieron en rojo antes en la primera ronda; se reforzaron en la segunda (rojo→verde de colSpan 2/3/5 y `Esqueleto` contra implementación vacía).
- (e) PRUEBA MANUAL del humano con datos reales: con una sesión cerrada a 375 px, el total de precio de no encontrados queda visible al desplazar y la suma de cada pestaña del informe coincide con las tres cifras congeladas (cero diferencias); el valor en vivo no cambia al cerrar una sesión y el último informe no se mueve al cambiar un precio.
- (f) Los `Number()` de `Inicio.tsx:54` y `Barras.tsx:43` son solo de proporción de barra: mantener ese límite (nunca para texto visible de dinero).
- (g) Sin axe.
- (h) docs/08: gráficas de barras con superficie de `Panel` y barra `bg-ink`; tablas de informe y valor con fila de total en el pie opaca y desplazamiento con primera columna fija en teléfono; avisos de empresa e informe previo en tono información con «Ir a Empresa» secundario; Exportar PDF principal (cobalto) y Excel secundario; actividad reciente con la fila entera como objetivo táctil; componentes nuevos `Esqueleto` y `TablaDatos.pie`.

## T8 — `/admin`: Activos, ficha, edición y registrar activo — [x] 700ce1d (2026-11-19)

- **Resultado:** `Activos` con `TablaDatos` (filtros, exportar, doble clic/`Enter`, menú de fila, tarjetas en móvil), ficha con `ListaDatos`, `Panel` y foto grande, `EditarActivo` y confirmación de reparación con `Dialogo`/`Confirmar` (foco devuelto como en la 015), `RegistrarActivo` en dos columnas. Conflicto 412 y precio solo admin intactos.
- **Archivos probables:** `web/src/routes/admin/{Activos,FichaActivo,RegistrarActivo}.tsx`, `web/src/components/app/{EditarActivo,AccionesActivo,FotoActivo}.tsx`, pruebas `Activos`, `FichaActivo`, `FotosActivo`, `AltaActivo`.
- **Tamaño de la foto (D13, R11, A9):** la foto de la ficha ocupa como máximo 320 × 240 px en escritorio y, a 375 px, ancho completo con alto máximo 200 px, con `object-cover`; al hacer clic se abre ampliada en un `Dialogo` (foco devuelto). La prueba fija las clases/atributos de dimensiones y `object-cover`, y comprueba que una imagen muy grande o muy pequeña no deforma ni genera scroll horizontal. Si la vista de activos de `/contar` muestra foto, se aplica el máximo de 200 px de alto a 375 px (tarea que la toque; si no existe, no se añade).
- **Terminado cuando:** además de lo anterior, captura a 375 y 1440 px mostrando la caja de la foto y sin scroll horizontal (`scrollWidth ≤ ancho`).
- **Verificación:** `npm test -- Activos FichaActivo FotosActivo AltaActivo && npm run lint && npm run typecheck`.
- **Dependencia:** T3 y T4. Revisión extra: `domain-guardian` (precios, estados).
- **Cerrada:** 700ce1d (2026-11-19), aprobada por `reviewer` y `domain-guardian`; 911 pruebas en 76 archivos, lint y typecheck limpios. Resuelve además el foco devuelto en Mover, Dar de baja y Reactivar (pendiente de la 015).

### Deuda T8

- (a) `EditarActivo.tsx`: `Edicion` queda montada con el diálogo cerrado; si se cierra con un guardado en vuelo y se abre otra acción (Mover/Baja) antes de la respuesta, el `onSuccess` ejecuta `cerrar()` y cierra esa otra acción (baja, solo interacción). Blindar `cerrar()` para que solo actúe si el diálogo sigue abierto y añadir pruebas de «reabrir empieza de cero» y del guardado en vuelo con el diálogo cerrado.
- (b) T10: en el conflicto 412 hay dos botones principales («Guardar mis cambios» en el `Aviso` y «Guardar cambios» en el pie): hacer secundario el del `Aviso`.
- (c) T10: a 375 px la cuarta pestaña «Dados de baja» queda cortada sin indicio de desplazamiento (`Activos.tsx:28-33`, `Pestanas.tsx:59`): degradado o texto más corto.
- (d) `ListaDatos.tsx:7`: comentario duplicado y confuso.
- (e) T10: el Historial usa `Panel` con su h2 dentro del cuerpo para no tocar el selector de `Historial.test.tsx`: migrar al encabezado del Panel.
- (f) Hueco en el panel de foto de un dado de baja sin foto; una foto diminuta se ve pixelada con `object-cover` (esperado).
- (g) `FormularioAlta.tsx` importa `Switch` de `components/ui` (la guardia no escanea `components/app`).
- (h) Las pruebas de la foto fijan clases, no medidas (jsdom): el tamaño D13 y el «sin scroll horizontal» dependen de las capturas y de `informe-qa.json` de T8.
- (i) `Menu`, `MarcoImagen`, `medidasImagen.ts` (`MEDIDAS_IMAGEN`) y `Panel.pieFijo` son del kit fuera del contrato original; `MarcoImagen` con variantes `foto`, `logo` y `logoCabecera` ya listas para T9 (logo 160×64 en Ajustes → Empresa, 32 px en cabeceras). — `Menu` usado en Ubicaciones y logo D13 (`MarcoImagen` `logo`) en Empresa por T9 (2a5ff97); `logoCabecera` sin uso real (Deuda T9 (e)).
- (j) PRUEBA MANUAL del humano con datos reales: edición con dos sesiones de admin y un 412 real; contador real en ficha, `/contar/activo/:codigo` e historial sin precio ni rótulo; admin con precio válido muestra «$» y no «—»; Exportar con más de 5.000 filas; quitar/cambiar foto y que el servidor borre la anterior.
- (k) Sin axe.
- (l) docs/08: kit nuevo `MarcoImagen` (D13) y `Menu`; `Panel.pieFijo`; paginación «‹ Anterior»/«Siguiente ›» en vez de chevrons; ficha con foto en caja de 320×240 y acciones al lado, datos en `Panel` con `ListaDatos`; Activos con pestañas subrayadas encima de la `TablaDatos`; pasos numerados en `brand-soft` en Registrar activo; Cancelar de diálogos de ghost a secundario y Dar de baja con la variante de peligro.

## T9 — `/admin`: sesiones, discrepancias, ubicaciones, categorías, usuarios, empresa — [x] 2a5ff97 (2026-11-19)

- **Resultado:** resto de pantallas de gestión con `EncabezadoPagina`, `TablaDatos`, `Panel`, `Dialogo` y `Estado`; cierre de sesión con `Confirmar` que explicita el efecto; discrepancias con desfase confirmado; categorías con búsqueda y paginación de la 015; invitaciones con el enlace que «no se vuelve a mostrar»; `Pendiente` migrada. La lista de excepciones de `kit.node.test.ts` queda vacía salvo lo que T10 deba revisar.
- **Archivos probables:** `web/src/routes/admin/{Sesiones,DetalleSesion,Discrepancias,Ubicaciones,Categorias,Usuarios,Empresa,Pendiente}.tsx` y pruebas.
- **Tamaño del logo (D13, R11, A9):** en Ajustes → Empresa el logo se muestra en una caja fija de 160 × 64 px con `object-contain` y fondo neutro; en cabeceras de informe y barra, donde ya se muestre, con alto fijo de 32 px y ancho automático con máximo 120 px. El límite de subida de la 013 (PNG ≤ 600 px sin metadatos) no cambia. La prueba fija dimensiones y `object-contain` y comprueba que un logo muy grande o muy pequeño no se deforma ni rompe el diseño (sin scroll horizontal).
- **Terminado cuando:** además de lo anterior, captura a 375 y 1440 px mostrando la caja del logo en Ajustes → Empresa y en la cabecera donde aparezca.
- **Verificación:** `npm test -- Sesiones Discrepancias Ubicaciones Categorias Usuarios Empresa && npm run lint && npm run typecheck`.
- **Dependencia:** T8 (reutiliza `TablaDatos` ya probada en una pantalla real). Si pasa de un día, se parte en dos con `/sdd-change`.
- **Cerrada:** 2a5ff97 (2026-11-19), aprobada por `reviewer`, `domain-guardian` y `security-reviewer`; 975 pruebas en 79 archivos, lint y typecheck limpios.

### Deuda T9

- (a) Edición de pruebas existentes: `Categorias.test.tsx:237` `size-11`→`size-control`; en `kit-compat.test.tsx` la prueba «quedan sobre blanco» pasó a comprobar que el selector YA NO existe (aserción invertida; cobertura en `Campo.test`/`gestionKit.test`); retirada la prueba de caracterización del error de carga de Empresa (reintentos de TanStack) y reemplazada por una de textos: añadir una prueba simple con `fetch` 500 en `/api/empresa` que muestre «Reintentar» (`Empresa.tsx:227`).
- (b) `TablaDatos.tsx:467-481`: `pulsado` queda armado si el clic no cambia `desde`/`hayAnterior`/`haySiguiente`: revisar en Activos con paginación por cursor.
- (c) `Ubicaciones.tsx:254`: el título «¿Desactivar «»?» durante la animación de cierre (estético).
- (d) El cierre de sesión usa `Dialogo` (`role=dialog`) y no `Confirmar`/`alertdialog`, y el clic fuera puede cerrarlo si no está en curso: valorar `alertdialog` (T10). El `Confirmar` del desfase no pasa `confirmando` (igual que antes).
- (e) El logo no aparece en ninguna cabecera de la web, solo en Ajustes → Empresa y en Excel/PDF del servidor: no hay captura de «logo en cabecera»; `MarcoImagen` variante `logoCabecera` queda sin uso real (T10 decide si la deja); un logo pequeño se amplía y se ve pixelado con `object-contain` + `size-full` (esperado).
- (f) `CampoFormulario.tsx`, `app/EmptyState` y `ConEstado` (`EncabezadoPagina`) siguen existiendo sin pantallas: T10 decide si se borran; `StatCard` sin consumidores.
- (g) `Usuarios.tsx:117-119`: el enlace de invitación vive en el `MutationCache` hasta `reset()` o 5 min de `gcTime` (preexistente): poner `gcTime: 0` en esa `useMutation` (fuera de presentación: tarea aparte, con spec).
- (h) `Casilla`, `Interruptor`, `TablaDatos.nombrarFilas`, `encabezadoOculto` y el foco devuelto en paginación son del kit fuera del contrato original; el foco devuelto en paginación ahora también aplica a Activos (sin prueba propia).
- (i) Las mediciones por elemento de 18–20 px en interruptor y casilla miden el control interno: el objetivo real es el `label` de 48 px (36 px en escritorio), no medido directamente.
- (j) PRUEBA MANUAL del humano con datos reales: cerrar una sesión real y abrir su informe (el segundo cierre devuelve 200 sin cambiar nada); lote de discrepancias con una fila desfasada («Ya se movió» y «Aplicar de todos modos» envía `confirmar_desfase`); «Seleccionar todas» indeterminado en teléfono y escritorio; «Quitar logo» (solo retira el logo vigente; el archivo se conserva) y luego informe nuevo sin logo e informe viejo con logo; subir un logo real grande y uno pequeño y ver Excel/PDF; invitación: el enlace se ve una sola vez y tras «Invitar a otra persona» no queda en el DOM; un contador que entra por URL a `/admin/sesiones`, `/admin/usuarios` y `/admin/empresa` es rechazado; lector de pantalla con «Seleccionar todas» en estado mixto.
- (k) Sin axe.
- (l) docs/08: kit nuevo `Casilla` e `Interruptor`; `TablaDatos` con `nombrarFilas`, `encabezadoOculto` y foco devuelto; Sesiones con tarjeta «En curso» con `Progreso`, cerradas en `TablaDatos`, cierre en `Dialogo` con botón de peligro; Discrepancias con pestañas subrayadas y acciones del lote a la derecha («Aplicar» principal), «Seleccionar todas» visible también en teléfono y desfase con `Confirmar`; Ubicaciones con tarjetas por sede y menú ⋯ del kit; Usuarios y Empresa en dos `Panel`, logo en `MarcoImagen` `logo` (160×64 object-contain); estados vacíos con la acción secundaria cuando el encabezado ya tiene la principal.

## T10 — Pulido, limpieza y cierre — [x] a2ca22d (2026-11-19)

- **Resultado:** componentes de `app/` sin uso y envoltorios de compatibilidad eliminados; `EXCEPCIONES` de `kit.node.test.ts` vacía; galería final con todo el kit; recorrido completo a 375 y 1440 px de todas las rutas (≈ 24 rutas × 2 anchos) con axe no ejecutado (no instalado); contraste por cálculo y revisión en navegador; consola limpia y sin scroll horizontal; e2e verde; `tasks.md` con la deuda y la lista de cambios respecto de docs/08 confirmada para que el humano la aplique.
- **Archivos probables:** `web/src/components/app/*` (borrados/ajustes), `web/src/components/kit/kit.node.test.ts`, `web/src/routes/dev/Componentes.tsx`, `specs/016-rediseno-ui-componentes/tasks.md`.
- **Verificación:** `npm test && npm run lint && npm run typecheck && npm run build && npm run e2e` y `git diff --stat origin/develop -- backend docs web/package.json web/src/lib/api` vacío.
- **Dependencia:** T6, T7, T8 y T9. Revisión: `reviewer` global y `domain-guardian`.
- **Cerrada:** aprobada por reviewer; 1000 pruebas en 80 archivos; lint, typecheck, build y e2e verdes; domain-guardian y security-reviewer no requeridos (solo presentación).
- **Cambios respecto de docs/08:** consolidados en `specs/016-rediseno-ui-componentes/cambios-docs08.md` (local) para que el humano actualice `docs/08-diseno-visual.md`.

### Deuda T10 / deuda final de la spec

- (a) Cierre de sesión como `alertdialog` no hecho: sigue en `Dialogo` (`role=dialog`); `e2e/flujo.spec.ts:87` busca `role=dialog` y está fuera de `web/src`.
- (b) Componente `Navegacion` del contrato no creado (solo `SaltarContenido`); la receta sigue en `ITEM_NAV` de `AdminShell`.
- (c) axe sin instalar: A4 se cumple por cálculo de contraste y revisión en navegador, no por axe.
- (d) A2 se cumple para rutas: `CopiarDeParecido`, `LocationPicker`, `InputSugerido`, el `Switch` de `FormularioAlta` y `App.tsx` (`/health`) siguen con `components/ui` por dentro (el humano acepta o pide spec).
- (e) Enlaces pequeños en admin < md (18–24 px: «Ver sesiones», «elígela», nombres en tablas, títulos de tarjeta en Sesiones/Detalle/Discrepancias) y de 24 px en `/contar` inicio (la fila entera es el objetivo).
- (f) Sala truncada con «No confirmado» a 375 px.
- (g) `invitacion-error-clave-1440.png` es de una pasada anterior y dos capturas de invitación a 1440 fallaron por 429 (límite de tasa): regenerar tras esperar.
- (h) «Guardar mis cambios» del aviso 412 es secundario (ya no hay acción principal en el aviso; edición visual declarada).
- (i) Posible pérdida menor: la aserción `data-obligatorio` con `aria-hidden` del `Campo` se borró con `CampoFormulario` (no está en `Campo.test`): añadirla.
- (j) `Ubicaciones.tsx:177`: setState durante el render con guarda de igualdad (patrón válido).
- (k) `gcTime: 0` de la mutación de invitación: fuera de presentación, tarea aparte con spec.
- (l) B1 (foco tras Esc en «¿Dónde lo encontraste?») aceptado.
- (m) Pasada manual con teclado y lector USB real sobre el foco del panel «Verificación» (`Escritorio.tsx:289-293`).
