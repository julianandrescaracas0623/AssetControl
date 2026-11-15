# Spec 010 — Dashboard (Inicio)

> **Estado:** Aprobada (G1–G3, 2026-11-15) con Q1–Q3 en la opción recomendada y P22, P24 y P26 por defecto. Depende de la 008 (cierre, informe y valor actual, hecha); la 009 no es requisito. Módulo M11 (CU-DSH-01..04) de `docs/07`; cierra P22–P26 de `docs/05`. Plan en `plan.md`, tareas en `tasks.md`.

## Problema

El Inicio de administración sigue siendo una maqueta con datos ficticios, y el del conteo no muestra ni el total de activos ni la actividad. Con el cierre, el informe y el valor actual ya reales, el Inicio puede reunir lo importante en una sola pantalla: cuántos activos hay hoy, cómo va el conteo, qué falta resolver, el último informe congelado, en qué categorías y ubicaciones está el valor y cómo evoluciona entre conteos. Todo leído del servidor, sin precios para el contador.

## Usuarios

- **Admin:** ve el Inicio completo en `/admin`.
- **Contador:** ve en `/contar` un Inicio sin ningún precio ni valor (P13, P25).

## Alcance

- Dentro: indicadores (CU-DSH-01), actividad reciente (CU-DSH-02), gráficas de valor por categoría y por ubicación (CU-DSH-03), evolución entre conteos (CU-DSH-04), Inicio del contador.
- Fuera: pantalla «Ver toda la actividad» (pendiente en `docs/08`), filtros por fechas, exportar el Inicio, comparativos más allá de la evolución, notificaciones.

## Requisitos (EARS)

1. **R1 Indicadores (CU-DSH-01).** Cuando el admin abra el Inicio, el servidor debe devolver: activos hoy (`activo` + `en_reparacion`, con cuántos en reparación; R7), valor actual (R7, rotulado «No es el informe»), avance de la sesión abierta (verificados, total, pendientes, %), discrepancias por resolver, dañados o en reparación (P26) y las tres cifras del último informe cerrado de `tipo=conteo` (rotulado «Informe congelado»). El valor actual y el último informe nunca comparten tarjeta.
2. **R2 Sin sesión o sin informe.** Sin sesión abierta, la tarjeta de avance debe decir «Sin sesión abierta» (y ofrecer «Abrir sesión» al admin); sin sesiones cerradas, la del último informe debe mostrar un estado vacío, no ceros.
3. **R3 Actividad reciente (CU-DSH-02).** Ambos roles deben ver los últimos eventos del tenant (altas, verificaciones, movimientos, cambios de estado, categoría y datos, bajas, discrepancias descartadas y, solo el admin, cambios de precio) por `seq` descendente, con fecha, autor, evento y activo, cada uno enlazado a su ficha o historial. Al contador el servidor le quita `precio_cambiado` y toda clave de precio (P13), igual que en el historial (005).
4. **R4 Gráficas (CU-DSH-03).** El admin debe ver el valor por categoría y por ubicación con las cifras del servidor; cada gráfica rotula su fuente y nunca mezcla dos (P23). El cliente solo dibuja.
5. **R5 Evolución (CU-DSH-04).** El admin debe ver, por cada sesión cerrada de `tipo=conteo` (P22), el total registrado y el % encontrado en unidades (P24), y poder verlo por categoría. Todo sale de `sesion_conteo` y `sesion_desglose`; cada punto coincide con el informe de su sesión. Sin cierres → «Aún no hay conteos cerrados»; una sola sesión → un punto; una categoría ausente en una sesión se muestra ausente, no como cero.
6. **R6 Contador (P13, P25).** El contador debe ver en `/contar` activos hoy (unidades), el avance del conteo abierto y la actividad reciente, sin ningún precio, valor, gráfica de valor ni evolución; los endpoints de valor, gráficas y evolución le responden `403`. Cada endpoint del Inicio tiene una prueba de que la respuesta al contador no trae dinero.
7. **R7 Fallas aisladas.** Si una parte del Inicio falla (indicadores, actividad, gráficas o evolución), solo esa parte muestra el error con «Reintentar»; el resto se ve.

## Criterios de aceptación

- A1: pruebas de API de cada endpoint: cifras exactas en un caso armado (activos hoy con reparación y bajas, avance, discrepancias, dañados con su sesión fuente, último informe = informe de esa sesión), sin sesión abierta y sin cierres, aislamiento por tenant, roles, y respuestas al contador sin `precio`, `valor`, `total_` ni COP.
- A2: evolución: cada punto es igual a `GET /sesiones/{id}/informe` de su sesión (total registrado y unidades); el % coincide; las sesiones abiertas e `importacion` no aparecen; una categoría ausente no tiene fila; el límite de P22.
- A3: actividad: orden por `seq`, autor del tenant, enlace al activo, filtro de precio para el contador.
- A4: contrato OpenAPI de los endpoints nuevos, ejercitado.
- A5: navegador real (375 y 1440 px): Inicio del admin y del contador con datos reales, sin banda de maqueta; gráficas con fuente rotulada; evolución con dos cierres; error aislado de una parte; axe 0, sin desbordes y consola limpia.

## Decisiones ya tomadas

R7, R8, R9 y ADR-003 (informe y valor nunca se mezclan; lo congelado se lee, no se recalcula), P13 (el servidor filtra los precios; ocultar en la UI no cuenta), P15/E2 (en reparación cuenta, dados de baja no). Decisiones por defecto revisables del 2026-11-11 que esta spec adopta: **P24** el % de la evolución lo calcula el servidor, en unidades, con un decimal; **P26** «dañados o en reparación» = activos `en_reparacion` + activos con `estado_fisico=danado` en su verificación vigente de la sesión abierta (o, sin sesión abierta, de la última cerrada), y la tarjeta nombra esa sesión. Recomendación no vinculante de **P22** que esta spec adopta salvo que G1 diga otra cosa: todas las sesiones cerradas de `tipo=conteo`, como máximo las 12 más recientes.

## Riesgos

- **Mezclar fuentes:** tipos y endpoints distintos para valor actual (vivo) y lo congelado; la web no suma; pruebas de igualdad con el informe.
- **Fuga de precios al contador:** cada endpoint con prueba de que su respuesta al contador no lleva dinero; los de valor, gráficas y evolución son solo admin.
- **Tamaño:** 9 tareas; si alguna crece se parte.

## Decisiones de G1 (humano, 2026-11-15)

| Pregunta | Decisión |
|---|---|
| Q1 Gráficas | Barras propias con CSS y tabla accesible; sin dependencia nueva (no se agrega `recharts`). |
| Q2 Fuente (P23) | «Valor actual», rotulado «No es el informe». |
| Q3 Contador (P25) | En `/contar`: activos hoy (unidades), avance del conteo abierto y actividad reciente, sin precios. |
| P22, P24, P26 | Aprobadas las decisiones por defecto: hasta los 12 conteos cerrados más recientes; % en unidades con un decimal calculado por el servidor; «dañados» = en reparación + `estado_fisico=danado` de la sesión abierta o de la última cerrada, con la sesión rotulada. |

## Opciones que se presentaron en G1

| Pregunta | Opciones | Recomendación |
|---|---|---|
| Q1 Cómo dibujar las gráficas | A: barras propias con CSS (sin dependencias), con su tabla accesible. B: `recharts` 3.10.1 vía el componente de gráficos de shadcn/ui (trae `@reduxjs/toolkit`, `immer`, `react-redux` y otras). | **A.** Son pocas series (≤ 12 conteos, decenas de categorías): barras horizontales y verticales bastan, se prueban en jsdom, cumplen accesibilidad con una tabla equivalente y no suman peso ni dependencias. B da tooltips y animaciones listas a cambio de peso y de pruebas más frágiles. |
| Q2 Fuente de las gráficas por categoría y ubicación (P23) | A: «Valor actual» (vivo), rotulado «No es el informe». B: «Último informe cerrado» (`sesion_desglose`). C: un selector entre las dos, una a la vez. | **A.** El último informe ya tiene su tarjeta y su pantalla, y la evolución usa lo congelado; así cada bloque tiene una sola fuente. |
| Q3 Inicio del contador (P25) | A: en `/contar`, activos hoy (unidades), avance del conteo abierto y actividad reciente sin precios. B: solo el avance (como hoy). C: además, unidades por categoría (sin valores). | **A.** Le da contexto del trabajo sin exponer dinero; C añade poco para quien cuenta. |
