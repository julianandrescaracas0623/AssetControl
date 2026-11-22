# Spec 016 — Rediseño visual de la web con biblioteca propia de componentes

> **Estado:** Propuesta (2026-11-18), escrita por el `planner`. Origen: petición del humano de rediseñar el aspecto de la web con componentes propios y reutilizables en lugar de pantallas con piezas sueltas (trabajo autónomo; las decisiones de gusto están tomadas en «Decisiones de diseño», sin preguntas abiertas). Depende de la 001b (sistema de diseño) y de la 015 (implementada; no se pisa). Plan en `plan.md`, tareas en `tasks.md`. Numeraciones 011 y 014 siguen reservadas.

## Problema

La web funciona, pero su aspecto es el de "piezas shadcn sueltas": cada pantalla compone `Button`, `Card`, `Badge`, `Table` y clases de Tailwind a su manera. Consecuencias:

1. Mismas cosas se ven distintas (espaciados, títulos, estados vacíos, tarjetas, filas de tabla, barras de acción) y cualquier ajuste visual exige tocar decenas de pantallas.
2. Los estados cargando, vacío y error están resueltos pantalla por pantalla (`EmptyState`, `ConEstado`, avisos ad hoc), con diferencias.
3. El diseño actual («Grafito y Cobalto», docs/08) es correcto pero plano: lienzo blanco sobre blanco, botón principal casi igual al texto, poca jerarquía entre página, tarjeta y control, y densidad igual en conteo y administración.

## Usuarios

- **Admin** (`/admin/**`, celular y escritorio) y **contador** (`/contar/**`, móvil primero a 375 px): ven una interfaz más clara y coherente. No hay usuarios ni permisos nuevos.
- **Desarrolladores**: arman pantallas con una biblioteca propia pequeña y cambian el aspecto desde los tokens.

## Alcance

**Incluye**

- Tokens de diseño centralizados (color, tipografía, radio, sombra, espaciado, densidad, objetivos táctiles) en `web/src/index.css`, único lugar con valores literales.
- Una biblioteca propia de componentes en `web/src/components/kit/`, construida **sobre** los componentes shadcn/ui de `components/ui/` (que no se reescriben) y Tailwind, con estados cargando/vacío/error/éxito integrados donde aplique.
- Migración incremental de todas las pantallas de `/login`, `/invitacion`, `/contar/**` y `/admin/**` a esa biblioteca, una familia por tarea.
- Galería `/dev/componentes` actualizada como documentación viva y revisión visual.
- Una prueba automática que impide que las pantallas vuelvan a componer piezas sueltas (ver R7).
- Lista de cambios respecto de `docs/08-diseno-visual.md` (sección «Cambios respecto de docs/08») para que el humano actualice ese documento.

**No incluye (no-objetivos duros)**

- Cero cambios de dominio, backend, esquema, migraciones, auth, roles, precios, contratos de API (`openapi.yaml`, tipos generados) ni textos de reglas de negocio. Mismas funcionalidades, mismos flujos, mismas rutas, mismos permisos.
- Cero dependencias nuevas (tampoco fuentes). Se usa lo que ya está en `package.json` (Geist y Geist Mono variables, `lucide-react`, `radix-ui`, `cmdk`, `sonner`, `class-variance-authority`, `tw-animate-css`). **Mejora futura NO incluida:** `@tanstack/react-table`, `recharts`, otra familia tipográfica, modo oscuro, ilustraciones.
- Ningún cambio de comportamiento ni de textos funcionales: los 546 tests web existentes siguen verdes. Solo se permite editar una prueba existente para cambiar un import o un selector de clase/estructura puramente visual, nunca una aserción de comportamiento, texto, rol o permiso; cada edición se anota en `tasks.md`.
- Sin logotipo nuevo ni marca (T9 de docs/08 sigue pendiente), sin animaciones decorativas, sin modo oscuro, sin conteo offline.
- Sin cambios a los informes exportados (Excel/PDF), que son del servidor.
- No se editan `docs/` ni `docs/adr/` desde esta spec; el humano actualiza docs/08 con la lista de cambios.

## Decisiones de diseño (tomadas, con su porqué)

| # | Decisión | Porqué |
|---|---|---|
| D1 | **Lienzo en dos niveles**: fondo de página `--page` `#F6F6F7`; tarjetas, tablas, campos y diálogos en blanco `--card`. | Hoy todo es blanco sobre blanco; el contraste de nivel da jerarquía sin sombras ni degradados. Los controles siempre quedan sobre blanco, así `--input` (3,4:1) sigue cumpliendo 3:1. |
| D2 | **Botón principal en cobalto** `#2B50E0` (texto `#FFFFFF`, 6,3:1); hover `#2443C4`. El neutro oscuro pasa a botón «secundario fuerte» (`--ink`). | Una sola acción principal por pantalla debe reconocerse al instante, sobre todo bajo apuro en conteo; el cobalto ya es el acento de marca (foco, enlaces, avance), así que el sistema pasa de tres señales (oscuro, cobalto, foco) a una. Cambia la decisión A del 2026-11-13 (docs/08 §2.1). Cumple AA con margen. |
| D3 | **Radio**: `--radius` 0,625 rem (10 px). Controles `rounded-lg`, tarjetas y diálogos `rounded-xl`, insignias `rounded-full`. | Un poco más suave y actual que 8 px, sin llegar a "píldora"; tres niveles con función, no uno para todo. |
| D4 | **Sombra y borde**: tarjeta = borde 1 px + `shadow-xs`; elevación solo en diálogo, menú y sheet (`shadow-lg`); sin sombras de color ni degradados. | Principio 1 de docs/08 se conserva. |
| D5 | **Tipografía**: se mantiene Geist / Geist Mono (ya instaladas, autoalojadas). Escala nombrada en tokens: `titulo-pagina`, `titulo-seccion`, `cuerpo`, `etiqueta`, `cifra`, `codigo`. Cifras con `tabular-nums`. Títulos `tracking-tight`. Nada de mayúsculas sostenidas en etiquetas. | Sin dependencias nuevas; la escala nombrada es lo que evita las clases sueltas. |
| D6 | **Densidad por modo, vía variables**: `--control-h` y `--fila-h`. Conteo (`/contar/**`) y admin < `md`: controles 48 px, fila 56 px, botón principal 56 px. Admin ≥ `md`: controles 36 px, fila 44 px. Un único componente, dos densidades. | Hoy ≥ 44 px es el mínimo; 48 px da más holgura de pulgar y el escritorio gana densidad sin duplicar componentes. |
| D7 | **Estados semánticos** con fondo suave + borde + ícono + texto (nunca solo color): éxito, aviso, error, información (cobalto suave). Misma receta en `Insignia`, `Aviso` y `Estado`. | Constitución 7 y docs/08 §9; una sola fuente de la receta. |
| D8 | **Navegación admin**: barra lateral clara (`--sidebar` blanco), ítem activo con barra de acento cobalto a la izquierda y fondo `--brand-soft`; encabezado con borde inferior y migas. Conteo: encabezado compacto y barra de acción fija con área segura. | Orientación clara sin color de fondo pesado. |
| D9 | **Ancho de contenido admin** 1320 px (se conserva D2 de la 001b); conteo en móvil 100 %, en escritorio la composición de dos paneles de la 015. | No se pisa la 015. |
| D10 | **Modo oscuro**: fuera. Las variables siguen permitiéndolo. | Fuera de MVP (docs/08 §2.1). |
| D11 | **Ubicación de la biblioteca**: `web/src/components/kit/` (primitivos y compuestos genéricos del producto). `components/ui/` queda solo con shadcn generado; `components/app/` queda con componentes de dominio (`AssetCard`, `LocationPicker`, `Escaner`, `NetworkStatus`…) que componen `kit`. | Mantiene la convención de web-ui («shadcn no se reescribe») y separa lo genérico de lo de dominio. |
| D12 | **Capturas**: se guardan en `specs/016-rediseno-ui-componentes/capturas/` (local, sin versionar, como las maquetas de 013). | Convención vigente. |
| D13 | **Tamaños de imagen** (2026-11-19; viene de una indicación del humano: definir el tamaño del logo de la empresa y que el de la foto de activos sea prudente; los valores son **por defecto** fijados por el coordinator y el humano puede corregirlos). (a) Logo en Ajustes → Empresa (T9): caja fija 160 × 64 px, `object-contain`, fondo neutro, sin deformar. (b) Logo en cabeceras de informe y barra donde ya se muestre: alto fijo 32 px, ancho automático con máximo 120 px. (c) Foto de la ficha de activo en `/admin` (T8): máximo 320 × 240 px en escritorio; en teléfono (375 px) ancho completo con alto máximo 200 px; `object-cover`; clic la abre ampliada en un `Dialogo`. (d) Foto en la vista de activos de `/contar`, si existe: máximo 200 px de alto a 375 px, sin dominar la pantalla. Solo presentación en `web/src`: no cambia el límite de subida de la spec 013 (PNG ≤ 600 px sin metadatos) ni las reglas ni el procesamiento de imágenes del servidor. | Un tamaño fijo evita que una imagen muy grande o muy pequeña rompa el diseño o ocupe media pantalla; `object-contain` en el logo conserva la marca completa y `object-cover` en la foto mantiene una caja uniforme. |

## Biblioteca de componentes (contrato de la spec)

Nombres en español, consistentes con `components/app`. Cada componente: props tipadas, `className` solo para casos puntuales, accesible por teclado, con prueba y entrada en la galería. Los que muestran datos cubren cargando, vacío, error (con reintento) y éxito.

| Componente | Reemplaza / envuelve | Responsabilidad |
|---|---|---|
| `Boton` | `ui/button` | Variantes `principal` (cobalto), `secundario` (contorno), `fuerte` (neutro oscuro), `fantasma`, `peligro`; `cargando` (deshabilita, `aria-busy`, texto "…ando"), `icono`; alturas por densidad; ancho completo en barra de acción. |
| `Campo` | `app/CampoFormulario`, `ui/label|input|textarea|select` | Etiqueta visible + control + ayuda + error enlazado con `aria-describedby`/`aria-invalid`; 16 px mínimo en móvil. Variantes: texto, número, dinero (COP, solo presentación), área, selección. |
| `Panel` | `ui/card` | Superficie blanca con título/acciones opcionales y pie; también variante «sección plegable». |
| `EncabezadoPagina` | títulos sueltos | Título, descripción, acciones (una principal), migas opcionales. |
| `ListaDatos` | filas rótulo/valor de ficha y verificación | Rótulo/valor con alineación, `tabular-nums`, código en mono; el precio solo se pasa si existe (el contador no recibe hueco, P13). |
| `Insignia` | `ui/badge`, `EstadoActivoBadge` | Estado semántico con ícono + texto (D7). |
| `Aviso` | `ui/alert`, avisos ad hoc | Información, éxito, aviso, error; con acción opcional; `role` adecuado (`alert`/`status`). |
| `Estado` | `EmptyState`, `ConEstado`, esqueletos | `Estado.Cargando`, `Estado.Vacio` (con acción), `Estado.Error` (con «Reintentar»); un envoltorio `ConEstado` mantiene su API actual. |
| `Cifra` | `app/StatCard`, `FigureCards` | Rótulo, cifra del servidor (nunca recalculada), contexto, enlace; la variante «congelada» y «en vivo» conservan los rótulos obligatorios de R7. |
| `TablaDatos` | `ui/table` en pantallas | Barra de herramientas (búsqueda, filtros, limpiar, acción principal), encabezados, orden accesible (`aria-sort`), fila clicable/doble clic, menú de fila, paginación «1–25 de N», y por debajo de `md` lista de tarjetas o scroll con primera columna fija; estados integrados. Sin `@tanstack/react-table`: orden, filtro y paginación siguen donde ya están (cliente o servidor, sin cambio de contrato). |
| `Dialogo` / `Confirmar` | `ui/dialog`, `ui/alert-dialog`, `ui/sheet` | Diálogo centrado, sheet inferior en móvil, confirmación destructiva con efecto explícito; foco atrapado y devuelto. |
| `BarraAccion` | barras fijas de `/contar` | Acción principal a ancho completo, secundaria opcional, área segura, no tapa el contenido. |
| `Navegacion` | piezas de `AdminShell`/`CountShell` | Ítem de menú (activo, colapsado con tooltip), migas, cabecera de conteo. |
| `Pestanas`, `Filtro` | `ui/tabs`, filtros de tabla | Pestañas del informe; botón de filtro con conteo de seleccionados. |

Los componentes de dominio se conservan (misma API pública para no tocar sus consumidores y pruebas) y se reescriben por dentro con `kit`.

## Requisitos (EARS)

1. **R1 Tokens únicos.** Cuando se necesite un color, radio, sombra, tamaño de letra o altura de control, el sistema debe tomarlo de los tokens de `index.css`; no debe haber valores literales de color ni clases de paleta de Tailwind fuera de ese archivo (la prueba `theme.node.test.ts` sigue vigente y se amplía).
2. **R2 Biblioteca.** Cuando una pantalla necesite un botón, campo, panel, tabla, insignia, aviso, estado, diálogo o barra de acción, el sistema debe usar el componente correspondiente de `components/kit/`, no un componente de `components/ui/` directamente.
3. **R3 Estados.** Cuando un componente de datos esté cargando, sin datos o en error, el sistema debe mostrar el estado correspondiente con el mismo aspecto en todas las pantallas; el error ofrece «Reintentar» y el vacío una acción clara, con los textos que ya existen.
4. **R4 Conteo móvil.** Cuando se use `/contar/**` a 375 px, el sistema debe mostrar objetivos ≥ 48 px con ≥ 8 px entre ellos, una acción principal por pantalla fija en la zona del pulgar, sin scroll horizontal, y sin añadir pasos ni digitación.
5. **R5 Administración.** Cuando se use `/admin/**` desde `md`, el sistema debe mostrar la densidad de escritorio (D6); por debajo de `md`, la de móvil, con tablas convertidas según docs/08 §4.4.
6. **R6 Accesibilidad.** Cuando se opere con teclado o lector de pantalla, el sistema debe mostrar foco visible (anillo 2 px + 2 px de separación) en todo control, contraste AA (4,5:1 texto, 3:1 bordes de control y ícono), color nunca como único canal, y `prefers-reduced-motion` respetado; axe-core sin infracciones AA en cada pantalla migrada.
7. **R7 Sin piezas sueltas.** Cuando se añada código en `web/src/routes/**`, el sistema debe fallar `npm test` si una pantalla importa de `components/ui/` fuera de la lista de excepciones; la lista de excepciones empieza con las pantallas aún no migradas y debe quedar **vacía** al cerrar la T10.
8. **R8 Presentación pura.** Cuando se migre una pantalla, el sistema debe conservar textos, rutas, roles, orden de foco funcional, llamadas a la API, claves de caché e idempotencia (UUID del cliente); la verificación de cada tarea incluye la suite web completa sin cambios de comportamiento.
9. **R9 Dinero y datos.** Cuando se muestre dinero o una cifra, el sistema debe formatearla solo para presentación (`es-CO`, COP), con `tabular-nums`, tal como llega del servidor; el contador no ve hueco ni «•••» donde iría un precio (P13).
10. **R10 Cero digitación.** Cuando se rediseñe una pantalla de captura, el sistema debe mantener (o mejorar) escanear, elegir, autocompletar y duplicar como primeras opciones; ningún campo nuevo.
11. **R11 Tamaños de imagen.** Cuando se muestre el logo de la empresa o la foto de un activo, el sistema debe respetar los tamaños fijos de D13 sin deformar la imagen y sin provocar scroll horizontal, sea la imagen muy grande o muy pequeña.

## Criterios de aceptación

- **A1** (R1): `theme.node.test.ts` ampliado verde: sin colores literales ni clases de paleta fuera de `index.css`; todas las variables de tema son hex de 6 dígitos; los pares de contraste de la tabla de tokens (plan §3) se verifican por cálculo en una prueba de nodo (AA).
- **A2** (R2, R7): prueba de nodo `kit.node.test.ts`: ninguna ruta importa `components/ui/*` salvo la lista de excepciones; al cierre la lista está vacía.
- **A3** (R3): prueba por componente con datos: cargando, vacío con acción, error con «Reintentar» que llama al callback.
- **A4** (R4, R5, R6): por pantalla migrada, captura a 375 y 1440 px, sin scroll horizontal (`scrollWidth ≤ ancho`), axe 0 infracciones AA, consola sin errores, objetivos táctiles medidos en `/contar/**`.
- **A5** (R8): suite web completa verde en cada tarea (546 al inicio; solo puede crecer), `npm run lint` y `npm run typecheck` limpios; backend intacto (sin diff en `backend/`).
- **A6** (R9): pruebas existentes de cifras y de roles (contador sin precios) verdes; ningún componente nuevo recibe `float` ni recalcula totales.
- **A7**: la galería `/dev/componentes` muestra cada componente del kit en todos sus estados y variantes a 375 y 1440 px.
- **A9** (R11, D13): prueba por componente de las dimensiones y del ajuste (`object-contain` en logo, `object-cover` en foto) y captura a 375 y 1440 px mostrando la caja, con imagen muy grande y muy pequeña, sin deformación ni scroll horizontal.
- **A8**: al cerrar, `git diff` de `backend/`, `docs/`, `web/src/lib/api/` y `web/package.json` está vacío.

## Reglas de dominio (que el rediseño no puede romper)

- Verificación inmutable e idempotente por UUID del cliente; «No se pudo confirmar» se ve distinto de «Guardado»; `409 sesion_cerrada` sigue sin «Reintentar».
- «Informe congelado» y «Valor actual (no es el informe)» nunca comparten tarjeta ni rótulo (R7 de docs/03-07).
- El precio es del admin; el servidor decide qué se muestra; esconder un botón no es seguridad.
- Dinero en COP desde el servidor; ningún cálculo de totales en el cliente.
- Sin datos reales de la clínica en galerías, capturas versionadas ni pruebas (datos ficticios).

## Riesgos

1. **Regresión funcional silenciosa** al reescribir pantallas. Mitigación: tests primero, suite completa por tarea, migración de una familia por tarea, componentes de dominio con API estable.
2. **Pruebas que dependen de clases o estructura** (`variants.test.tsx`, `theme.node.test.ts`, pruebas de foco de la 015). Mitigación: tocarlas solo en T1/T2, anotadas; lo funcional (roles, nombres accesibles, foco) no se cambia.
3. **Choque con trabajo en curso** de la 015 (ficha, conteo de escritorio, alta). Mitigación: la 015 está implementada (T1–T10 en `develop`); el rediseño reescribe por dentro conservando sus contratos (`?sesion=`, doble clic, foco devuelto, lector USB).
4. **Cambio de la decisión A de docs/08 (botón principal)**. Mitigación: D2 registrada; el humano actualiza docs/08; revertir es cambiar un token.
5. **Contraste** de nuevas superficies. Mitigación: prueba de contraste por cálculo (A1) y axe real.
6. **Diferencia local/CI en pruebas lentas** (suite web larga). Mitigación: las configuraciones de estabilidad vigentes (`eb6b68e`) no se tocan.
7. **Tamaño**: son muchas pantallas. Mitigación: 10 tareas ≤ 1 día; si una crece, se divide en la propia spec (`/sdd-change`).

## Cambios respecto de docs/08 (para que el humano actualice ese documento)

1. §2.1: añadir `--page` `#F6F6F7` (fondo de página) y `--ink` `#18181B` (botón fuerte); `--background`/`--card` siguen blancos. `--primary` pasa de `#18181B` a `#2B50E0` (`--primary-foreground` `#FFFFFF`); `--brand` y `--ring` se mantienen. Retirar la «opción A» del botón principal y registrar la D2.
2. §2.1: `--sidebar` pasa de `#FAFAFA` a `#FFFFFF` con ítem activo `--brand-soft` y barra de acento.
3. §2.2: `--radius` de 0,5 rem a 0,625 rem; controles `rounded-lg`, tarjetas/diálogos `rounded-xl`; tarjeta con `shadow-xs`. Objetivo táctil de 44 a **48 px** en conteo y admin < `md` (el mínimo de accesibilidad de 44 px se cumple con margen); botón principal de conteo 56 px; admin ≥ `md`: control 36 px, fila 44 px.
4. §2.3: escala tipográfica nombrada en tokens (tabla del plan §3); fuente sin cambio (Geist / Geist Mono, ya aprobadas e instaladas).
5. §3.2: la lista de componentes propios se sustituye por el kit de esta spec (`Boton`, `Campo`, `Panel`, `EncabezadoPagina`, `ListaDatos`, `Insignia`, `Aviso`, `Estado`, `Cifra`, `TablaDatos`, `Dialogo`/`Confirmar`, `BarraAccion`, `Navegacion`, `Pestanas`, `Filtro`) en `components/kit/`; `StatCard`/`ThreeFiguresCard`/`LiveValueCard` pasan a variantes de `Cifra`.
6. §4.1: ítem activo del menú lateral con barra de acento cobalto.
7. §10, decisión pendiente 3 (fuente) y 5 (dependencias): sin cambio; `@tanstack/react-table` y `recharts` siguen sin aprobar y fuera de esta spec.
8. §3 y §6 (fotos y logo): fijar los tamaños de D13 (logo de empresa 160 × 64 px `object-contain`; logo en cabeceras 32 px de alto, máx. 120 px de ancho; foto de ficha máx. 320 × 240 px, 200 px de alto en teléfono, `object-cover`, ampliable en `Dialogo`). Por indicación del humano; valores por defecto.
9. Todo lo demás (flujos, wireframes, estados y mensajes de §7–§9, rutas de §6) no cambia.

## Preguntas abiertas

Ninguna. Las decisiones de gusto están en D1–D13 con su opción recomendada y su porqué. No hay `[PENDIENTE]` de producto, dominio ni precios en esta spec, y nada contradice un ADR, la constitución ni docs/01–03.
