# Spec 015 — Mejoras de uso real: activos, informe, conteo en escritorio y ficha

> **Estado:** implementada (T1–T10 en `develop`); cerrada el 2026-11-19 (sección «Cierre» al final de este archivo; deuda y pruebas manuales en «Deuda final» y «Pendiente del humano» de `tasks.md`). Implementada el 2026-11-18: T1–T10 en `develop` (tabla de commits abajo). Preguntas Q1–Q11 todas decididas por el humano (2026-11-18, cada una con su opción en la tabla de abajo); ya no hay `[PENDIENTE]` de producto.
>
> | Tarea | Commit | Tarea | Commit |
> |---|---|---|---|
> | T1 foto al guardar | ff5d3c7 | T6 categorías | 0a83894 |
> | T2 editar y reparación | 703fece | T7 ficha | 1a8037c |
> | T3 volver al informe | b48732d | T8 conteo escritorio | e7b2125 |
> | T4 exportar activos | 63008ea | T9 contar en la sesión | d19c34c |
> | T5 Excel del informe | 3477c9d | T10 registrar activo | c37a3b3 |
>
> Historial de estado:  Maquetas T7–T10 aprobadas por el humano (2026-11-18, con las recomendaciones; ver «Respuestas de diseño de las maquetas»), así que la condición de Q11 está cumplida. Origen: feedback de uso real del humano (7 puntos). Depende de 004, 005, 006, 008, 009, 012 y 013 (todas implementadas). Plan en `plan.md`, tareas en `tasks.md`. Las numeraciones 011 y 014 siguen reservadas.

## Problema

Con el sistema en uso aparecieron siete fricciones:

1. En **Activos**, «Exportar» solo muestra un aviso («llega con la spec 009») y la fila no se abre con doble clic.
2. Editar un activo abre un panel lateral (no un diálogo) y **al guardar se pierde la foto** en pantalla. «Enviar a reparación» actúa sin pedir confirmación.
3. El **Excel del informe** no convence (la 013 dejó la v3) y desde «Valor actual» no hay camino de vuelta al informe.
4. **Contar desde el computador** usa una interfaz de teléfono (columna de 480 px) y ofrece la cámara, que en un PC no tiene sentido; el formulario «Registrar activo» es mejorable.
5. **Categorías** es una lista plana sin búsqueda: no escala a muchas.
6. «Ir a contar» en escritorio es un atajo suelto del menú; debe vivir dentro de la sesión de conteo.
7. La **ficha del activo** es una lista de datos sin jerarquía.

Principio rector (constitución 7): cero digitación innecesaria; escritorio y móvil son dos formas de uso, no una columna estirada.

## Usuarios

- **Admin:** los siete puntos (lista, edición, exportaciones, categorías, ficha, sesión).
- **Contador:** puntos 4 y 6 (contar y registrar activos desde escritorio o teléfono); no exporta, no edita catálogo, no ve precios (P13).

## Alcance

- **Incluye:** exportar activos a archivo (admin); doble clic en fila; editar en diálogo centrado; arreglo de la foto que desaparece (causa en `plan.md` §2); confirmación Sí/No al enviar a reparación; mejora del Excel del informe sin tocar cifras; navegación Valor actual → informe; modo de conteo con diseño de escritorio (sin cámara por defecto, según Q7); entrada al conteo desde la sesión (Q8); formulario «Registrar activo» en dos columnas con menos digitación; categorías con búsqueda y paginación; ficha del activo rediseñada.
- **No incluye:** cambios de esquema ni migraciones; nuevas reglas de negocio, precios o roles; conteo offline; impresión de etiquetas; importación del Excel; gráficos nuevos en la web; exportar «Valor actual» (sigue fuera, 009); cambios al PDF; app nativa; jerarquía de categorías (el modelo no la tiene).

## Requisitos (EARS)

**Activos**

1. **R1 Exportar.** Cuando el admin pulse «Exportar» en Activos, el sistema debe descargar un archivo con los activos que coinciden con los filtros vigentes (búsqueda, estado, ubicación) —no solo la página visible—, con el formato y columnas que decidan Q2 y Q3, generado en el servidor.
2. **R1a Reglas de la exportación.** El precio debe salir solo para el admin (el endpoint es solo admin, `403` al contador); el dinero se escribe desde `Decimal`, en COP, como número con formato de moneda y dos decimales, nunca `float` en el cálculo; ningún texto se interpreta como fórmula; el nombre del archivo no lleva datos de la clínica; `Cache-Control: no-store` y `X-Content-Type-Options: nosniff`; sin datos en los registros del servidor. Con cero resultados el archivo se genera con solo el encabezado.
3. **R2 Doble clic.** Cuando el admin haga doble clic en una fila de la tabla de activos (escritorio), el sistema debe abrir la ficha de ese activo; con teclado, `Enter` en la fila enfocada hace lo mismo. El enlace del nombre y el menú de acciones siguen funcionando (el doble clic en un enlace, un botón o el menú no navega dos veces).

**Edición y ciclo de vida**

4. **R3 Diálogo centrado.** Cuando se abra «Editar», el sistema debe mostrarlo como diálogo centrado (no panel lateral), con los mismos campos y la misma lógica de conflicto 412; en escritorio, campos en dos columnas; en 375 px, una columna con objetivos de 44 px y desplazamiento interno.
5. **R4 La foto no desaparece.** Cuando se guarde una edición (y también mover, cambiar estado o dar de baja), la ficha, la lista y cualquier otra vista del activo deben seguir mostrando la foto principal vigente. Una prueba debe reproducir el fallo antes del arreglo.
6. **R5 Confirmar reparación.** Cuando el usuario pulse «Enviar a reparación», el sistema debe abrir un diálogo con «Sí, enviar a reparación» y «No»; solo «Sí» llama al servidor. «No», `Esc` o cerrar no cambian nada. «Volver a activo» no pide confirmación (se deshace igual de fácil).

**Informe y valor**

7. **R6 Excel del informe.** El Excel del informe debe mejorarse según lo que decida Q6. Toda cifra sigue saliendo de `cierre.informe` y de lo congelado al cierre, sin sumar ni leer `activo`, `verificacion` ni la empresa vigente (R1 y R7 de 009 y 013); idéntica al centavo a la del JSON.
8. **R7 Volver al informe.** Cuando el admin llegue a «Valor actual» desde el informe de una sesión, el sistema debe mostrar un enlace «Volver al informe de <sesión>» y la miga de pan correspondiente; si llega de otro lugar, «Volver» lleva a donde estaba (o al Inicio). El identificador de sesión viajará en la URL y se valida como UUID del tenant; si no existe, se ignora sin error.

**Contar en escritorio**

9. **R8 Modo de conteo de escritorio.** Cuando el ancho sea ≥ 1024 px con puntero fino, las pantallas de `/contar/**` deben usar un diseño de escritorio (ancho útil, dos paneles: búsqueda y cola a la izquierda, verificación a la derecha; atajos de teclado); en teléfono se conserva la experiencia de 375 px sin cambios de comportamiento.
10. **R9 Sin cámara en escritorio.** En el diseño de escritorio, el escáner de cámara no debe mostrarse por defecto; la captura es por búsqueda y por lector USB tipo teclado, según Q7. En teléfono la cámara sigue siendo lo primero.
11. **R10 Contar dentro de la sesión.** En escritorio, «Ir a contar» no debe existir como atajo suelto del menú; la entrada al conteo es desde la sesión abierta, según Q8. En teléfono se conserva el acceso actual.
12. **R11 Registrar activo.** El formulario «Registrar activo» (`/admin/activos/nuevo` y `/contar/nuevo`) debe presentarse en dos columnas en escritorio (datos a la izquierda; foto, «copiar de un parecido» y resumen a la derecha), con foco inicial, `Enter` para guardar y la opción «Guardar y registrar otro» según Q9. Sigue exigiendo solo código, nombre, precio, categoría y ubicación; el contador sigue sin ver precios de otros.

**Categorías y ficha**

13. **R12 Categorías a escala.** Cuando existan muchas categorías, la pantalla debe ofrecer búsqueda (sin tildes ni mayúsculas) y paginación; mantener crear y renombrar. Evaluación de API en `plan.md` §4 (no requiere cambio).
14. **R13 Ficha del activo.** La ficha debe organizarse en: encabezado (nombre, código, estado, categoría y acciones), foto grande, datos agrupados (identificación, ubicación y compra) y historial, con dos columnas en escritorio y una en 375 px. Mismo contenido y permisos que hoy; sin nuevos datos.

## Criterios de aceptación

- **A1** (R1, R1a): pruebas de API: el archivo trae las mismas filas que `GET /activos` con los mismos filtros (cuenta y orden); contador `403`; sin sesión `401`; otro tenant no aparece; un nombre que empieza por `=`, `+`, `-` o `@` queda como texto; precio con decimales exacto; cero resultados; cabeceras; sin precio en la hoja si Q3 lo decide para algún caso. Contrato OpenAPI actualizado.
- **A2** (R2): prueba web: doble clic navega a la ficha; clic en el menú no; `Enter` abre.
- **A3** (R3, R4): prueba web que reproduce el fallo: ficha con foto, guardar edición, la foto sigue; ídem mover, estado y baja; prueba de API: la respuesta de cada escritura trae `foto` (y el `412` también). Diálogo centrado con `role="dialog"`, foco atrapado y `Esc`.
- **A4** (R5): «No» no envía; «Sí» envía una sola vez; mensaje coherente con D3 («sigue contando en el inventario»).
- **A5** (R6): Excel leído con `openpyxl`: lo decidido en Q6; cifras iguales al JSON; sin fórmulas; el archivo no cambia si después se edita un precio o una ubicación (A2 de 009 y 013 siguen verdes).
- **A6** (R7): prueba web: el enlace aparece solo con `?sesion=` válida y lleva al informe; sin parámetro no aparece.
- **A7** (R8–R10): pruebas web con `matchMedia` de escritorio y teléfono: sin cámara ni `getUserMedia` en escritorio; lector tipo teclado (ráfaga + `Enter`) abre el activo; el teléfono no cambia; «Ir a contar» ausente del menú en escritorio y presente en teléfono; la sesión abierta ofrece «Contar».
- **A8** (R11): `AltaActivo.test.tsx` extendido: dos columnas, «Guardar y registrar otro», sin precio para el contador, idempotencia (UUID del cliente) intacta.
- **A9** (R12, R13): categorías: búsqueda y paginación con 200 categorías; ficha: jerarquía y orden de lectura, axe 0.
- **A10** (todas las de UI): navegador real a **375 y 1440 px** (skill `browser-qa`), axe 0, consola limpia, capturas; e2e (`npm run e2e`) extendido con exportar activos y editar con foto.

## Reglas de dominio

- Una fila por unidad física; el `codigo` no se toca; el `serial` no es único y no deduplica.
- Solo el admin ve precios (P13) y exporta; el servidor filtra, no la web.
- Dinero COP, `NUMERIC(14,2)`/`Decimal`, nunca `float`; informes congelados leen lo congelado (ADR-003, R8).
- `en_reparacion` cuenta siempre en el inventario (D3, P15): el diálogo de confirmación debe decirlo.
- Escrituras de catálogo con `If-Match`/`row_version` (005): el arreglo de la foto no cambia la concurrencia.
- Roles en el servidor; esconder botones no es seguridad.

## Riesgos

- **Exportar con la lista filtrada:** que la exportación y la lista usen filtros distintos. Mitigación: una sola función de búsqueda sin paginación; prueba de igualdad.
- **Inyección de fórmulas / fuga de precio** en la exportación: pruebas de A1; revisión de seguridad.
- **Rediseño del Excel sin criterio:** sin Q6 resuelto sería gusto personal; se pide decisión antes de implementar T5.
- **Dos interfaces de conteo que divergen:** se evita con una sola ruta `/contar/**` responsiva (no un segundo módulo), compartiendo lógica (`useVerificacion`, `altaActivo`).
- **Lector USB sin foco:** el campo de captura debe recuperar el foco; documentado y probado.
- **Alcance creciente:** diseño de escritorio de conteo (T8–T10) es lo más grande; si Q7/Q8 piden más, se divide en otra spec.
- **P4 (docs/05) dice «sin pistola lectora en el MVP»:** usar un lector USB como teclado es compatible (no hay integración) pero roza esa nota; se pide confirmar (Q7).

## Preguntas abiertas

Ninguna sigue abierta: Q1–Q11 quedaron decididas por el humano el 2026-11-18 («aplicar todas las recomendaciones»; Q4 con tope de 5.000 filas fijado por el humano). La tabla se conserva como registro de la decisión. Condición vigente: T7–T10 siguen condicionadas a Q11 = A (maqueta local aprobada por el humano en `specs/015-mejoras-ux-escritorio/maquetas/` antes de implementar).

| # | Pregunta | Opciones | Recomendación | Bloquea |
|---|---|---|---|---|
| **Q1** `[DECIDIDA: A]` (humano, 2026-11-18) | ¿La exportación de la lista de activos entra al alcance? `docs/01` solo prevé exportar el informe (PDF y Excel); la 009 dejó fuera «exportar el valor actual». | **A:** sí, solo admin; se añade una línea a `docs/01`. **B:** no; se quita el botón. | **A** (el botón ya está en la maqueta aprobada y contabilidad lo pide). | T4 |
| **Q2** `[DECIDIDA: A]` (humano, 2026-11-18) | Formato de la exportación de activos. | **A:** Excel (.xlsx) con filtro y encabezado fijo. **B:** CSV (UTF-8 con BOM, `;` o `,`: dato de Excel en es-CO). **C:** ambos con selector. | **A**: reutiliza `xlsxwriter` (sin dependencia nueva) y el patrón de 009; CSV obliga a decidir separador y neutralizar `=+-@`. | T4 |
| **Q3** `[DECIDIDA: A]` (humano, 2026-11-18) | Columnas y contenido. Propuesta: código, nombre, categoría, ubicación (ruta), estado, serial, marca, modelo, subtipo, fecha de compra, precio de compra, registrado el. ¿Incluye dados de baja si el filtro es «Todos»? ¿Fila de total? | **A:** las columnas propuestas, respeta el filtro de estado (como la lista), **sin** fila de total. **B:** igual con fila de total del precio. **C:** otras columnas (indícalas). | **A**: un total fuera de `cierre` duplicaría la suma de «Valor actual» y puede confundirse con un informe; el valor en vivo ya tiene su pantalla. | T4 |
| **Q4** `[DECIDIDA: B, tope 5.000 filas]` (humano, 2026-11-18) | Tope de filas de la exportación. | **A:** sin tope (≈2 000 activos esperados, P6). **B:** tope técnico con error claro `413 exportacion_demasiado_grande` (valor a definir). | **B** con un tope holgado respecto de P6; el número lo fija el humano. | T4 |
| **Q5** `[DECIDIDA: A]` (humano, 2026-11-18) | ¿Confirmar solo el envío a reparación o también «Dar de baja» (ya tiene diálogo) y «Volver a activo»? | **A:** solo «Enviar a reparación» (lo pedido). **B:** también «Volver a activo». | **A**. | T2 |
| **Q6** `[DECIDIDA: A]` (humano, 2026-11-18) | Qué debe cambiar del Excel del informe (la v3 de la 013 ya tiene hoja Resumen, una hoja por categoría, filtros, encabezado fijo, anchos, impresión horizontal y logo). ¿Qué te desagrada concretamente? | **A (pulido):** Resumen tipo «tablero» (tres cifras en tarjetas, % encontrado con formato porcentaje, barras de datos en el desglose), colores de la marca con estilo sobrio, fila de totales resaltada y fija, formato condicional solo visual para «En reparación» y diferencias, nombres de columna claros, anchos ajustados al contenido, hoja «Todos los activos» plana (apta para tabla dinámica) además de las de categoría. **B (A + gráficos nativos):** añade dos gráficos de XlsxWriter (valor por categoría y por ubicación) en el Resumen, con datos del desglose congelado. **C:** otro (descríbelo o adjunta un ejemplo). | **A**. B si lo quieren para socios; ambos sin dependencias nuevas. Ninguna opción introduce fórmulas ni recalcula. | T5 |
| **Q7** `[DECIDIDA: B]` (humano, 2026-11-18) | Escáner de cámara en computador. No está definido (P4 solo habla de cámara de celular). | **A:** ocultar la cámara en escritorio; solo búsqueda y lector USB (teclado). **B:** ocultar por defecto con enlace «Usar la cámara de este equipo». **C:** mantenerla siempre. | **B**: resuelve el 95 % sin cerrar la puerta a portátiles con cámara y tablets; el lector USB como teclado no necesita integración. Criterio de «escritorio»: ancho ≥ 1024 px y `pointer: fine`. | T8 |
| **Q8** `[DECIDIDA: A]` (humano, 2026-11-18) | Dónde vive «Contar» en escritorio. | **A:** una sola ruta `/contar/**` responsiva; el admin entra desde el botón «Contar esta sesión» del detalle de la sesión abierta (y la tarjeta de «Sesiones»), sin atajo en la barra lateral ni en el menú de usuario; el contador entra por su Inicio (`/contar`). **B:** un espacio de conteo dentro del `AdminShell` (`/admin/sesiones/:id/contar`) distinto del de teléfono. **C:** dejar el atajo y solo mejorar el diseño. | **A**: una interfaz, una lógica, sin duplicar pantallas; satisface «dentro de la sesión» porque sin sesión abierta no hay conteo (006). B duplica el flujo. | T9 |
| **Q9** `[DECIDIDA: A]` (humano, 2026-11-18) | «Registrar activo»: ¿qué conserva «Guardar y registrar otro»? | **A:** categoría, ubicación, marca, modelo y subtipo (los datos «de sala»); borra código, serial, precio y foto. **B:** además conserva el precio (lotes homogéneos). **C:** no hay «registrar otro». | **A**: el precio no se arrastra para evitar altas con precio equivocado. | T10 |
| **Q10** `[DECIDIDA: A]` (humano, 2026-11-18) | Categorías: ¿se muestra cuántos activos tiene cada una? | **A:** no en esta spec (búsqueda y paginación en el cliente, sin cambio de API). **B:** sí; añade el campo `activos` (conteo, sin precio) a `GET /categorias` (cambio de API pequeño). | **A**; B queda como mejora si usan mucho renombrar. | T6 |
| **Q11** `[DECIDIDA: A]` (humano, 2026-11-18) | Proceso de diseño de las pantallas nuevas (ficha, conteo de escritorio, Registrar activo). | **A:** maqueta en navegador (como la 013, en `specs/015-mejoras-ux-escritorio/maquetas/`, solo local) que el humano aprueba antes de implementar T7–T10. **B:** implementar directo y revisar en QA. | **A**: costo bajo y evita rehacer (aprendizaje de la memoria: «no mostrar pantallas sin verlas»). | T7–T10 |

### Respuestas de diseño de las maquetas (DECIDIDAS por el humano, 2026-11-18)

Maquetas T7–T10 aprobadas por el humano el 2026-11-18 con las recomendaciones; con esto se cumple la condición de Q11 = A para T7–T10. Solo registran decisiones; los requisitos R1–R13 no cambian.

- **T7 (ficha):** variante A.
- **T8 (conteo en escritorio):** si se escanea otro sticker con un activo abierto sin confirmar, se abre el nuevo y se avisa que el anterior quedó sin confirmar; nada se confirma solo.
- **T9 (contar dentro de la sesión):** «Ir a contar» se quita solo con el criterio de escritorio (≥ 1024 px y puntero fino, el mismo de Q7); «Contar» en la sesión también se ve en teléfono.
- **T10 (Registrar activo):** variante A. «Guardar y registrar otro» también borra el nombre (además de lo que borra Q9 = A). «Varias unidades iguales» se mantiene apagado por defecto. Teclado: `Enter` del lector USB en el campo código pasa a Nombre sin guardar; `Enter` guarda en los demás campos; `Ctrl+Enter` es «Guardar y registrar otro».

## Decisiones ya tomadas (no se reabren)

P11 (ambos roles dan de alta), P13 (precios solo admin), P15/D3 (reparación cuenta), ADR-002 (solo online, sin offline), 009 (librerías Excel/PDF, dinero como número, sin fórmulas), 013 (Excel v3 con empresa congelada), 012 (fotos: una principal, ambos roles), diseño «Grafito y Cobalto» (docs/08), `/contar/**` móvil primero y `/admin/**` responsivo (T8 de docs/05).

## Cierre (2026-11-19)

**Estado: implementada (T1–T10 en `develop`).** Commits: T1 ff5d3c7, T2 703fece, T3 b48732d, T4 63008ea, T5 3477c9d, T6 0a83894, T7 1a8037c, T8 e7b2125, T9 d19c34c, T10 c37a3b3. La spec 016 (rediseño con kit propio, hasta a2ca22d) volvió a pintar estas pantallas sin cambiar su comportamiento.

**Preguntas:** Q1–Q11 decididas por el humano el 2026-11-18 (tabla de «Preguntas abiertas»; en esta spec ninguna quedó con `[PENDIENTE]`). No hay preguntas abiertas de producto, dominio ni precios.

**Cambios de alcance realizados** (todos decididos, ninguno nuevo):

- `docs/01` recibió una línea para la exportación de la lista de activos (Q1 = A).
- Q4 = B con tope fijado por el humano en 5.000 filas (`413 exportacion_demasiado_grande`).
- Q7 = B: en escritorio la cámara es opcional tras «Usar la cámara de este equipo» (no se elimina).
- T10 añadió «Guardar y registrar otro» que borra también el nombre (respuestas de diseño de las maquetas; la fecha de compra también se borra, decisión de implementación aceptada en la revisión).
- Sin migraciones, tablas, dependencias ni roles nuevos.

**Evidencia de los criterios de aceptación** (detalle y cifras en `tasks.md`):

| Criterio | Evidencia |
|---|---|
| A1 exportar | T4: `test_activos_exportar.py` (18: igualdad con la lista en 8 combinaciones de filtros, fórmulas como texto, 401/403, tenant, tope, cabeceras, logs) y contrato en `test_openapi.py` |
| A2 doble clic | T4: 6 + 2 pruebas en `Activos.test.tsx` y e2e (doble clic abre la ficha) |
| A3 foto y diálogo | T1: 6 pruebas de backend y 5 web que reproducían el fallo; T2: diálogo centrado, foco devuelto |
| A4 reparación | T2: «No» no envía, «Sí» una vez; foco inicial en «No» |
| A5 Excel | T5: `test_exportar_api.py` y `test_exportar_documento.py` (cuadre con el informe, sin `<formula>`); revisado por reviewer, domain-guardian y security-reviewer |
| A6 volver | T3: 8 pruebas en `Valor.test.tsx` y 1 en `Informe.test.tsx` |
| A7 escritorio | T8 (`Escritorio.test.tsx`, 45) y T9 (`Sesiones.test.tsx` +6, `AdminShell.test.tsx` +3) |
| A8 alta | T10: `AltaActivo.test.tsx` (28 pruebas); idempotencia intacta |
| A9 categorías y ficha | T6 (120 y 200 categorías) y T7 (15 pruebas); **axe 0 no demostrado** (axe no instalado) |
| A10 navegador real | QA en navegador a 375 y 1440 px en T2–T4 y T6–T10 con consola limpia; e2e extendido con exportar activos y doble clic (T4); **no consta e2e del alta ni de «editar con foto»**; **axe sin pasar** |

Último recuento conocido: 546 pruebas web verdes al cerrar T10 (lint y typecheck limpios); la 016 lo dejó en 1000 pruebas. Backend: 1959 verdes salvo TLS de entorno (T4).

**Brechas respecto de los criterios (no ocultas):** A10 (axe 0; e2e del alta y de editar con foto) y A9 (axe) no se cumplieron del todo; quedan en «Deuda final» de `tasks.md`.

**Compatibilidad con la normativa del proyecto:** nada contradice `docs/01–03`, un ADR ni la constitución. La nota P4 de `docs/05` («sin pistola lectora») roza el lector USB tipo teclado; se confirmó en Q7 y no hay integración.
