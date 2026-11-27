# Cambios a docs/08 por la spec 016 (rediseño UI con kit propio)

Lista consolidada para que el humano actualice `docs/08-diseno-visual.md`. Archivo local, no se versiona; el agente no edita `docs/`. Reúne la sección «Cambios respecto de docs/08» de `spec.md`, los apartados «docs/08» de la deuda de T1–T9 en `tasks.md` y lo nuevo de T10. Orden: por sección de docs/08.

## §2.1 Color (claro)

1. Botón principal: `--primary` pasa de `#18181B` a cobalto `#2B50E0` (`--primary-foreground` `#FFFFFF`); se retira la «opción A» del botón principal y se registra la D2 de la spec 016. `--brand` y `--ring` se mantienen.
2. Nuevo `--page` `#F6F6F7` (fondo de página) y `--ink` `#18181B` (botón fuerte, barras de gráficas `bg-ink`); `--background`/`--card` siguen blancos.
3. `--sidebar` pasa de `#FAFAFA` a `#FFFFFF` (blanco), con ítem activo `--brand-soft` y barra de acento cobalto.
4. Avisos de empresa e informe previo en tono información.

## §2.2 Forma, sombra, espaciado

5. `--radius` de 0,5 rem a 0,625 rem; controles `rounded-lg`, tarjetas/diálogos `rounded-xl`; tarjeta con `shadow-xs`.
6. Densidad: objetivo táctil de 44 a 48 px en conteo y en admin < `md`; admin ≥ `md`: control 36 px, fila 44 px; botón principal de conteo 56 px (secundario 48 px).
7. Foco de botones como contorno de 2 px (T10).
8. Foco suave del panel «Verificación» del conteo de escritorio (en lugar del anillo grueso) (T10).

## §2.3 Tipografía

9. Escala tipográfica nombrada en tokens (tabla del plan §3 de la spec 016); fuente sin cambio (Geist / Geist Mono).

## §3.2 Componentes propios

10. La lista de componentes propios se sustituye por el kit de `web/src/components/kit/`: `Boton`, `Campo`, `Panel`, `EncabezadoPagina`, `ListaDatos`, `Insignia`, `Aviso`, `Estado`, `Cifra`, `TablaDatos`, `Dialogo`/`Confirmar`, `BarraAccion`, `Pestanas`, `Filtro`. `Navegacion` del contrato no se creó (la receta vive en `AdminShell`).
11. Componentes nuevos del kit fuera del contrato original: `Progreso`, `Tecla` (tono `sobrePrincipal`), `Esqueleto`, `MarcoImagen` (variantes `foto`, `logo`, `logoCabecera`), `Menu`, `Casilla`, `Interruptor`, `SaltarContenido`; `Panel.pieFijo`; `TablaDatos.pie`.
12. `StatCard`/`ThreeFiguresCard`/`LiveValueCard` pasan a variantes de `Cifra`, con insignias «Tiempo real» y «No es el informe»; `StatCard`, `EmptyState`, `ConEstado` y `CampoFormulario` quedan borrados.
13. `Campo` con `ayudaFija`: la ayuda (p. ej. la política de contraseña) se mantiene visible junto al error (T10).
14. Pestañas subrayadas (Pendientes, cola del escritorio, Activos, Discrepancias), con degradado que indica desplazamiento cuando no caben (T10).
15. Paginación «‹ Anterior» / «Siguiente ›» en vez de chevrons.

## §3.3 Sheet, panel o diálogo

16. Cancelar de los diálogos pasa de ghost a secundario; Dar de baja con la variante de peligro.
17. Cierre de sesión en `Dialogo` con botón de peligro que explicita el efecto; desfase de discrepancias con `Confirmar`.
18. Conflicto 412 al editar: una sola acción principal (la del pie); «Guardar mis cambios» del aviso queda secundario (T10).

## §4.1 App shell

19. Barra lateral blanca con ítem activo `brand-soft` y barra de acento cobalto.
20. Enlace «Saltar al contenido» en los dos shells (admin y conteo) (T10).
21. Avisos de admin abajo a la derecha; de conteo arriba al centro.
22. Logo en cabecera: 32 px de alto, máx. 120 px de ancho (D13 b); hoy no se muestra en ninguna cabecera de la web (variante `logoCabecera` sin uso).

## §4.2 Inicio / Resumen

23. «Activos hoy» y cifras como `Cifra`; Inicio con `Progreso`; gráficas de barras con superficie de `Panel` y barra `bg-ink`; actividad reciente con la fila entera como objetivo táctil.

## §4.3 Tablas de datos

24. `TablaDatos` con búsqueda, filtros, orden accesible, paginación, fila clicable/doble clic, `nombrarFilas`, `encabezadoOculto`, foco devuelto y vista de tarjetas por debajo de `md` (tarjetas de Activos en dos columnas en teléfono).
25. Celdas de tabla con 8 px de relleno lateral por debajo de `md`; el pie hereda la clase de columna (T10).
26. Tablas de informe y valor con fila de total en el pie opaca y desplazamiento con primera columna fija en teléfono.
27. Activos con pestañas subrayadas encima de la `TablaDatos`.

## §4.4 Responsive y pantallas de admin

28. Barra de acción sticky (`BarraAccion`).
29. Informe: Exportar PDF principal (cobalto) y Excel secundario; «Ir a Empresa» secundario.
30. Ficha de activo: foto en caja de 320×240 con acciones al lado, datos en `Panel` con `ListaDatos`.
31. Registrar activo: pasos numerados en `brand-soft`.
32. Sesiones: tarjeta «En curso» con `Progreso`, cerradas en `TablaDatos`.
33. Discrepancias: acciones del lote a la derecha («Aplicar» principal); «Seleccionar todas» visible también en teléfono.
34. Ubicaciones con tarjetas por sede y menú ⋯ del kit; Usuarios y Empresa en dos `Panel`.
35. Estados vacíos con la acción secundaria cuando el encabezado ya tiene la principal.

## §5 Layout de conteo (`/contar/**`)

36. Encabezado de conteo blanco, objetivos de 48 px, en dos líneas (título y estado de red) (T10).
37. Barra de acción del conteo (`BarraAccion` en `<footer>`, principal 56 px, secundaria 48 px); estado de red como `Insignia`.
38. Campo del código de 56 px y 24 px de letra; hoja «¿Dónde lo encontraste?» con opciones de 48 px.
39. Mensajes de pantalla completa con panel tonal.
40. Conteo de escritorio a 48 px con cabecera de 72 px y sala en línea; cola con pestañas subrayadas.
41. Alta móvil con paneles por bloque y «Más datos» plegable; alta de escritorio con `EncabezadoPagina` y pie del panel en `bg-muted/40`.

## §6 Inventario de pantallas (fotos y logo, D13)

42. Logo de empresa en Ajustes → Empresa: caja fija 160×64 px, `object-contain`, fondo neutro.
43. Foto de ficha de activo: máx. 320×240 px en escritorio; en teléfono ancho completo con 200 px de alto máximo; `object-cover`; clic la amplía en `Dialogo`. Foto en `/contar`: máx. 200 px de alto a 375 px.
44. Solo presentación: no cambia el límite de subida (PNG ≤ 600 px sin metadatos) ni el procesamiento del servidor.

## §8 Estados y mensajes

45. Marco común de acceso y sistema; textos «Comprobando la sesión» y «Entrando…».
46. Invitaciones: el enlace «no se vuelve a mostrar».

## §10 Decisiones pendientes

47. Fuente (3) y dependencias (5): sin cambio; `@tanstack/react-table` y `recharts` siguen sin aprobar.

## Sin cambio

48. Flujos, wireframes, estados y mensajes de §7–§9 no listados arriba y rutas de §6 no cambian.
