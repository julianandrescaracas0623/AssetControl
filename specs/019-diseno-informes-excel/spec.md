# Spec 019 — Diseño de los Excel según las plantillas del humano

> Estado: medición real incorporada (`medicion-plantillas.md`) y preguntas Q6–Q13 CERRADAS por decisión del humano 2026-11-22 (sección «Decisiones del humano»). AVISO DE PRIVACIDAD: `specs/019-diseno-informes-excel/medicion-plantillas.md` contiene datos reales de la clínica (dirección, correo, teléfono, NIT) y NO debe versionarse ni publicarse; queda excluido del commit y de cualquier publicación de la spec (la exclusión en `.gitignore` la hace el humano; el planner no lo edita). Lo mismo aplica a `informes/` y a cualquier `matriz.md` con valores reales. Q14 CERRADA por el humano 2026-11-22 («Corte» y «Cerrada» del Resumen como texto). Decisiones del humano ya tomadas: D-1 la plantilla manda en anchos, alturas, nombres de hoja y rótulos (datos y reglas de dominio no cambian); D-2 si algo no se puede reproducir con `xlsxwriter` se PARA y se pregunta, sin aproximaciones silenciosas, y cambiar a plantilla base + openpyxl ya no es opción sin decisión humana; D-3 se versiona una huella JSON de propiedades de diseño, sin datos reales, para que CI compare (`informes/` es local).

## Problema

Los Excel que genera AssetControl no se ven como los quiere el humano. El humano entregó dos plantillas de diseño locales en `informes/`:

- `informes/Activos_20261122_diseno.xlsx` (1 hoja: «Activos») → Excel del módulo de activos (generador `backend/app/activos/exportar.py`).
- `informes/Informe_boseto_limpio.xlsx` (6 hojas: «Todos los activos», «Por ubicación», «No encontrados», «Electrodomésticos», «Por categoría», «Resumen») → Excel del informe de sesión (generador `backend/app/conteo/exportar.py`, desde `cierre.informe`).

Los Excel generados deben replicar ese diseño, y las diferencias de estructura o contenido que la plantilla implica se deciden con el humano (sección «Diferencias de estructura»).

## Usuarios

- `admin`: único rol que descarga hoy ambos Excel (`@require_role("admin")` en `GET /activos/exportar` y `GET /sesiones/{id}/informe/excel`). Las dos plantillas llevan columnas de precio, así que el acceso no cambia.
- `contador`: no descarga ninguno de los dos Excel hoy (recibe 403) y sigue sin poder; esta spec no abre el Excel al contador. (La versión anterior de esta spec suponía lo contrario; se corrige.)

## Requisito de máxima prioridad: fidelidad total

> **FT-1.** TODO elemento medido de la plantilla se reproduce en el Excel generado. NADA se omite ni se salta en silencio. Si algo no se puede reproducir con `xlsxwriter==3.3.1`, la tarea se detiene y se pregunta al humano (D-2); no se aproxima.
>
> **FT-2.** Cada propiedad medida figura como fila de la matriz de `plan.md` («propiedad → valor de plantilla → dónde se implementa → prueba»). Una propiedad sin fila es un defecto de esta spec.
>
> **FT-3.** Las pruebas comparan el `.xlsx` generado contra la huella JSON versionada, propiedad por propiedad. Una propiedad sin prueba es una tarea no terminada.
>
> **FT-4.** El criterio de terminado de CADA tarea incluye FT-1 a FT-3 para su alcance.

Excepciones (única vía): una propiedad sin efecto visible ni funcional (metadatos del paquete: `calcId`, `baseColWidth`, `uid`, canal alfa del color, deduplicación de medios, elementos de cabecera/pie vacíos) solo queda fuera de la comparación por la decisión del humano 2026-11-22 sobre Q13; se lista en la matriz como «equivalente no idéntico».

Propiedades mínimas por hoja: fuentes; imágenes (tamaño, ancla, desplazamientos); anchos; alturas; combinaciones; alineación, ajuste de texto, sangría; bordes; rellenos; formatos numéricos y de fecha; congelados; orientación y papel; márgenes; encabezado y pie de impresión; área de impresión y filas a repetir; ajuste a página; zoom; cuadrícula; ocultas; agrupación; nombres y orden de hojas; color de pestañas; hoja activa y selección; validaciones; formato condicional; autofiltro; hipervínculos; protección; tema y fuente por defecto; textos de títulos, rótulos y cabeceras.

## Alcance

### Incluye
- Aspecto del Excel de activos y del Excel del informe de sesión (todas las hojas de la plantilla B).
- Hojas nuevas y reordenamiento que la plantilla implica, aprobados por el humano (Q6, Q7; decisión del humano 2026-11-22). No cambian cifras: «Por ubicación» y «Por categoría» muestran las mismas cifras congeladas que hoy están en «Resumen».
- Datos de la empresa del tenant (logo, NIT, teléfono, correo, dirección) y fecha de exportación en el Excel de activos (Q9).
- Huella JSON de las plantillas, utilidad de comparación y pruebas por propiedad.
- Pruebas actualizadas en `test_activos_exportar.py`, `test_exportar_api.py`, `test_exportar_documento.py` y `test_roles.py`.

### No incluye
- Cambiar totales, cálculo, datos ni reglas de dominio: totales congelados con `precio_al_contar`, una verificación por `(sesión, activo)`, dinero `Decimal`/COP, filtro por tenant, rol `admin` en los endpoints de exportación.
- Cambiar el PDF (`a_pdf`), la pantalla web, migraciones, auth, roles o dependencias (`xlsxwriter==3.3.1` y `openpyxl==3.1.5` ya están fijadas).
- Cambiar de método (plantilla base + openpyxl): prohibido sin decisión humana (D-2).

## Medición: resumen de lo medido

Detalle completo, hoja por hoja y celda por celda representativa, en `medicion-plantillas.md`; los valores quedan en la matriz de `plan.md`. Rasgos comunes a las 7 hojas: pestaña `FF1D4ED8`; cuadrícula oculta (pantalla); zoom 100 (sin atributo); horizontal; papel sin declarar; márgenes 0.4/0.4/0.6/0.6; pie `&L&8 Generado con AssetControl&R&8 Página &P de &N`; encabezado de impresión vacío; fila 1 de 6 pt con banda azul `FF1D4ED8`; filas 2–5 de 44.1/18/18/15.95 pt con logo, título, empresa, «Corte»/«Exportado», NIT, Tel., Correo y dirección; fuente Arial (10 datos, 9 cabeceras de informe y 10 de activos, 12 título de lista, 19 título); cabecera `FFFFFF` sobre `FF1F2937`; bordes finos `9CA3AF`; datos centrados sin ajuste de texto; formatos `"$"\ #,##0.00`, `#,##0`, `0.0\ %` y fecha incorporada 14 (`mm-dd-yy`); tema Office 2007–2010 (Cambria/Calibri).

Limitaciones de la propia medición (T1 las cierra): solo se midieron celdas representativas (no todas); `N` significa negrita (supuesto); no se leyó el contenido de los `dxf` (3 en el informe: estilo del formato condicional), el `extLst` de las barras de datos, la cuadrícula al imprimir, el texto alternativo de las imágenes ni el rango completo de bordes de la fila 5.

## Diferencias de estructura entre plantilla y generador vigente

Comparación contra `backend/app/conteo/exportar.py` y `backend/app/activos/exportar.py`. «Aspecto» = solo apariencia (la plantilla manda por D-1). «Contenido» = cambia qué información o qué estructura recibe el usuario, o toca una regla: se pregunta.

### Excel de activos (plantilla A)

| # | Elemento | Hoy | Plantilla | Tipo |
|---|---|---|---|---|
| A1 | Hojas | 1 («Activos») | 1 («Activos») | Igual |
| A2 | Columnas (texto y orden) | Código, Nombre, Categoría, Ubicación, Estado, Serial, Marca, Modelo, Subtipo, Fecha de compra, Precio de compra, Registrado el | Idénticas (12) | Igual |
| A3 | Bloque de encabezado | No existe; la cabecera está en la fila 1 | Filas 1–5: banda, logo, «Inventario de activos», empresa, «Exportado dd/mm/aaaa», NIT, Tel., «Correo», dirección; cabecera en fila 7, datos desde la 8 | Contenido: el archivo recibe datos de la empresa y la fecha de exportación que hoy no lleva (Q9) |
| A4 | Logo | No | Sí, 297 × 116 px, ancla oneCell | Contenido (Q9, Q10) y técnico (Q13) |
| A5 | Anchos de columna | 14, 36, 20, 30, 14, 18, 16, 16, 16, 15, 18, 14 | 14, 30, 20, 22, 14, 18, 16, 16, 16, 18, 20, 20 | Aspecto |
| A6 | Fuente | Calibri 10; código en Consolas; cabecera negrita con borde inferior | Arial 10; cabecera Arial 10 negrita blanca sobre `1F2937` con bordes finos; datos centrados con bordes | Aspecto |
| A7 | Fechas | Formato propio `dd/mm/yyyy` | Formato incorporado 14 (`mm-dd-yy`, se muestra según la configuración regional) | Aspecto |
| A8 | Celdas vacías (serial, marca, subtipo…) | Sin escribir | Con borde y formato | Aspecto |
| A9 | Congelado y filtro | Congela la fila 1; filtro en fila 1 | Congela hasta la fila 7; filtro `A7:L…` | Aspecto (misma función) |
| A10 | Impresión | Sin ajuste, papel no declarado | Horizontal, ancho 1 × alto automático, repite fila 7, área `A1:L…`, pie, márgenes con encabezado/pie 0.5 | Aspecto |
| A11 | Orden de datos y filas | Una fila por activo | Igual | Igual |

### Excel del informe de sesión (plantilla B)

| # | Elemento | Hoy | Plantilla | Tipo |
|---|---|---|---|---|
| B1 | Orden de hojas | Resumen, Todos los activos, una por categoría, No encontrados | Todos los activos, Por ubicación, No encontrados, una por categoría («Electrodomésticos» es el ejemplo), Por categoría, Resumen | Contenido: reordena el libro (Q6, aprobado) |
| B2 | Hojas «Por ubicación» y «Por categoría» | No existen como hoja; son tablas dentro de «Resumen», con las mismas 8 columnas (`Ubicación/Categoría (al cierre)`, Valor/Unid. encontradas, no encontradas, registradas, % encontrado), barras de datos en F y H y fila de total | Hojas propias con las mismas columnas, barras de datos `BFDBFE` en F y H, fila Total con fondo `DBEAFE` | Contenido: cambia la ubicación de datos ya existentes; cifras iguales (Q6). Llevan precios; el rol `contador` no accede al Excel, no hay conflicto |
| B3 | «Resumen» | Antetítulo, nombre de la sesión, fila Fecha de corte / Cerrada / Moneda / Estado / Cerró, 4 tarjetas (con rótulo, valor y unidades), tablas por categoría y ubicación, nota de cifras congeladas (`NOTA`) y aviso `SIN_DETALLE` | Título en C2:D2, 4 tarjetas (Encontrado, No encontrado, Total registrado, % encontrado con «N unidad(es)» / «de las unidades registradas»), y debajo una lista «Todos los activos» con Total, cabecera y fila de datos | Contenido: desaparecen nombre de sesión, quién cerró y cuándo, moneda, estado «Informe congelado», `NOTA` y `SIN_DETALLE`; aparece una lista completa duplicada (Q7) |
| B4 | Encabezado de cada hoja | Empresa, contacto, nombre de sesión y estado («Informe congelado» / aviso `EMPRESA_VIGENTE`) en B1:B4; logo ≤ 110 × 40 px | Bloque de 5 filas con logo grande, «Informe de activos», empresa, «Corte dd/mm/aaaa», NIT, Tel., Correo, dirección | Contenido: el nombre de la sesión y el aviso `EMPRESA_VIGENTE` no tienen lugar (Q7) |
| B5 | Encabezado de impresión | Empresa y nombre de la sesión | Vacío | Contenido (el nombre de la sesión deja de imprimirse; Q7) |
| B6 | Columnas de «Todos los activos» | 10 (Código, Activo, Categoría, Marca, Serial, Ubicación esperada, Encontrado en, Estado físico, Resultado, Precio (COP)) | Idénticas | Igual |
| B7 | Columnas de la hoja por categoría | 9 (sin Categoría) | Idénticas | Igual |
| B8 | Columnas de «No encontrados» | 6 (Código, Activo, Categoría, Ubicación esperada, Nota al cierre, Precio (COP)) | Idénticas; columnas G–K ocultas | Igual (+ aspecto: columnas ocultas) |
| B9 | Textos de título y resumen de lista | «Todos los activos del cierre», «Categoría: X», «No encontrados (lista congelada al cierre)» y resúmenes «N activos · encontrados … · tabla «Activos» …» | Idénticos | Igual |
| B10 | Tabla «Activos» y filtros | «Todos los activos» es una tabla de Excel «Activos» con filtros; las demás listas con autofiltro | Sin tabla ni autofiltro en ninguna hoja de lista (el texto de la hoja igual dice «tabla «Activos», lista para filtrar o hacer una tabla dinámica») | Contenido: se pierde la función de filtrar/tabla dinámica (Q8) |
| B11 | Marcado de filas | Filas alternas con fondo; Resultado en verde/rojo; estado «En reparación»/«Dañado» en ámbar; «Encontrado en» ámbar cursiva por celda | Sin filas alternas; datos uniformes; formato condicional de fila completa (cursiva y fondo ámbar) cuando «Ubicación esperada» ≠ «Encontrado en» | Aspecto (la señal «encontrado en otra ubicación» se conserva; se pierden los colores verde/rojo/ámbar de Resultado y estado) |
| B12 | Congelado | Filas hasta la cabecera y 2 columnas | Solo filas (hasta la 9) en Todos, No encontrados y por categoría; ninguno en Por ubicación, Por categoría y Resumen | Aspecto |
| B13 | Impresión | Carta, ancho 1 × alto automático, repite cabecera | Papel sin declarar, 1 × 1 páginas en TODAS las hojas, área de impresión fija a las filas de la plantilla | Aspecto con efecto práctico: una lista de cientos de filas cabe en una sola página ilegible (Q12) |
| B14 | Fuente y color | Calibri/Consolas, paleta «Grafito y Cobalto» | Arial; paleta `1D4ED8`, `1F2937`, `111827`, `6B7280`, `9CA3AF`, `DBEAFE`, `BFDBFE` | Aspecto |
| B15 | Anchos y alturas | Calculados por contenido | Fijos de la plantilla (D-1) | Aspecto; texto largo se corta (sin ajuste) |
| B16 | Nombres de hoja reservados | `Resumen`, `Todos los activos`, `No encontrados`, `History` | Se suman `Por ubicación` y `Por categoría` | Regla técnica menor: evita que una categoría use esos nombres (se aplica el sufijo « (2)» ya vigente) |
| B17 | Fecha del bloque | Sesión y estado | «Corte dd/mm/aaaa» (fecha de corte) | Aspecto/rótulo (D-1) |

Reglas que la plantilla NO toca (se verifican con pruebas): totales congelados, hoja por categoría solo con detalle disponible, `contador` sin acceso, tenant. Nota: la regla «hojas por ubicación sin precio» de versiones previas de esta spec se refería al Excel original de la clínica (`docs/06-importacion-excel.md`), no al generador; el generador no tiene hojas por ubicación hoy.

## Requisitos (EARS)

1. Cuando se miden las plantillas, el sistema de pruebas debe volcar cada propiedad de FT de TODAS sus hojas en una huella JSON versionable (`backend/tests/plantillas/*.json`) que solo contenga propiedades de diseño y rótulos fijos; los datos de empresa (nombre, NIT, teléfono, correo, dirección, cifras y fechas) se sustituyen por marcadores.
2. Cuando un `admin` descarga el Excel de activos, el sistema debe generar un `.xlsx` cuya hoja coincida con la huella de `Activos_20261122_diseno.xlsx` propiedad por propiedad, con los mismos datos y el mismo orden de filas y columnas que hoy.
3. Cuando un `admin` descarga el Excel del informe de una sesión, el sistema debe generar un `.xlsx` cuyas hojas coincidan con la huella de `Informe_boseto_limpio.xlsx` propiedad por propiedad, en este orden: «Todos los activos», «Por ubicación», «No encontrados», una hoja por categoría, «Por categoría», «Resumen» (Q6), con tabla de Excel «Activos» y filtros con el estilo de la plantilla (Q8).
3a. Cuando se genera el Resumen, el sistema debe escribir lo de la plantilla (título, 4 tarjetas) y, debajo, filas finales con el nombre de la sesión, quién cerró y cuándo, la moneda, el estado «Informe congelado», la `NOTA` de cifras congeladas y los avisos `SIN_DETALLE` (si aplica) y `EMPRESA_VIGENTE` (si aplica); la lista «Todos los activos» duplicada de la plantilla en el Resumen NO se genera (Q7: residuo; ver matriz).
3b. Cuando se generan «Por ubicación» y «Por categoría», el sistema debe escribir las mismas cifras congeladas de `cierre.informe` (valores `Decimal` calculados al cierre con `precio_al_contar`; el Excel solo los presenta, nunca los suma ni convierte a `float`).
3c. Cuando un `admin` descarga el Excel de activos, el sistema debe escribir logo, NIT, teléfono, correo, dirección y fecha de exportación desde los datos vigentes de la empresa del tenant (sin migración), omitiendo los campos que no existan (Q9).
3d. Cuando se inserta el logo, el sistema debe ajustarlo dentro de la caja de cada hoja conservando su proporción (Q10).
3e. Cuando se abre el libro, el sistema debe dejar la primera hoja activa con la celda A1 y sin desplazamiento (Q11, residuo no reproducido).
3f. Cuando se configura la impresión, el sistema debe usar ajuste 1×1 en las hojas cortas («Por ubicación», «Por categoría», «Resumen») y 1 página de ancho × alto automático en las listas («Todos los activos», por categoría, «No encontrados») (Q12).
4. Cuando un `contador` solicita cualquiera de los dos Excel, el sistema debe seguir respondiendo 403 como hoy.
5. Cuando un dato es variable (filas, nombres de ubicación o categoría), el sistema debe repetir el estilo de la fila de datos de la plantilla en cada fila, y extender el rango dependiente de las filas (área de impresión, formato condicional, barras de datos) hasta la última fila escrita; los nombres de hoja siguen la regla `nombres_de_hoja` (≤ 31 caracteres UTF-16, sin caracteres prohibidos, únicos) con los dos nombres reservados nuevos.
6. Cuando el informe está cerrado, el sistema debe seguir leyendo de `cierre.informe`; el cambio de diseño no recalcula nada.
7. Cuando una propiedad de la plantilla no se puede reproducir con `xlsxwriter`, la tarea debe detenerse y registrar la pregunta al humano (D-2); no se aproxima en silencio.
8. Cuando el logo de la empresa no existe o no se puede leer, el sistema debe generar el archivo sin imagen, como hoy.

## Criterios de aceptación

1. La matriz de `plan.md` tiene una fila por propiedad medida con valor, lugar de implementación y prueba; sin celdas vacías.
2. Existe una prueba por fila; todas comparan generado vs. huella y pasan.
3. Los datos, totales, cifras y columnas no cambian respecto a la versión vigente; las pruebas de contenido existentes siguen verdes sin relajarse (solo se actualizan aserciones de estilo y de estructura aprobadas).
4. `uv run pytest` del backend verde; `uv run ruff check .` limpio.
5. La huella JSON versionada no contiene datos reales (revisión explícita antes del commit).
6. Revisión manual: el humano abre cada archivo generado junto a su plantilla en Excel real (LibreOffice/Excel no están en CI), con el checklist de T6.
7. Sin migraciones ni dependencias nuevas.
8. Las hojas «Por ubicación» y «Por categoría» reproducen exactamente las cifras de `cierre.informe` (prueba con valores `Decimal` que no son representables en `float`, p. ej. centavos); ningún cálculo del generador usa `float`; el valor escrito a la celda es el congelado con `precio_al_contar`.
9. Ninguna propiedad medida queda sin fila en la matriz; lo omitido por decisión (Q7 lista duplicada del Resumen, Q11 hoja activa/selección/desplazamiento, Q13 metadatos invisibles y `oneCellAnchor` si aplica) figura con su decisión del humano 2026-11-22.
10. `contador` recibe 403 en ambos Excel (sin cambios).

## Reglas de dominio

- Totales congelados al cerrar con `precio_al_contar`; una verificación por `(sesión, activo)`; el hecho de que una hoja o tabla cambie de lugar no recalcula nada.
- Dinero en COP con `Decimal`/`NUMERIC(14,2)`; el formato de la plantilla es solo presentación; nunca `float` en cálculos.
- Roles verificados en servidor (`admin` en ambos Excel); aislamiento por tenant.
- El `serial` no se usa para deduplicar.
- Los datos reales de la clínica no se versionan ni se loguean: la huella y las pruebas usan datos sintéticos y marcadores.

## Riesgos

- R1: `xlsxwriter` escribe archivos nuevos; la plantilla usa ancla `oneCellAnchor` en las imágenes, y `xlsxwriter` emite `twoCellAnchor` (ver Q13). Se confirma con prueba en T1.
- R2: `informes/` es local; las pruebas en CI dependen solo de la huella (D-3). Una prueba opcional (se omite si el archivo no existe) compara huella vs. plantilla original.
- R3: Fuentes no instaladas y autoajuste varían entre equipos; se fija el valor medido.
- R4 (cerrado por D-1): anchos y alturas de la plantilla prevalecen sobre el cálculo por contenido; con datos largos el texto se corta (celdas sin ajuste de texto). Se revisa en la verificación manual.
- R5: la medición cubre celdas representativas; T1 amplía la huella a todas las celdas con estilo, y la prueba de cobertura falla si aparece un elemento XML sin fila.
- R6: en «Resumen» los valores de las tarjetas son Arial 18 negrita en columnas de 24, 18, 22 y 20 caracteres sin combinar: cifras como `$ 167.226.590,70` podrían mostrarse como `####`. Se verifica en Excel real; si ocurre, se pregunta (no se amplía la columna por cuenta propia).
- R7: la plantilla tiene incoherencias de estilo por hoja (p. ej. «Correo» y el correo en Calibri 11 en unas hojas y Arial 9/10 gris en otras; gris `6B7280` en el informe y `4B5563` en activos; canal alfa `00` en el color de borde del informe y `FF` en activos). Por D-1 se reproducen tal cual, por hoja.
- R8: privacidad. `specs/019-diseno-informes-excel/medicion-plantillas.md` contiene datos reales de la clínica (dirección, correo, teléfono, NIT); NO se versiona ni se publica (excluido; el humano lo añade a `.gitignore`, hoy `.gitignore` no lo cubre y el archivo está sin seguimiento junto a la spec). `matriz.md` (T1) se genera sin valores reales (marcadores) o también se excluye. Antes de cada commit: `git status --short` y revisión de que no se agregue.
- R9: la dimensión del conjunto: hasta 7 imágenes (una por hoja) del mismo logo; `xlsxwriter` las deduplica en un solo medio (invisible; Q13).

## Puntos a confirmar en T1 con prueba (limitaciones posibles de `xlsxwriter`)

Cada uno se prueba con un `.xlsx` de sondeo antes de implementar; si alguno falla, T1 se detiene y se pregunta (D-2). Ninguno está decidido a favor ni en contra.

| # | Propiedad de la plantilla | Riesgo con `xlsxwriter` 3.3.1 |
|---|---|---|
| L1 | Imagen con ancla `oneCellAnchor`, `ext` exacto en EMU (p. ej. 2828926 × 1104900; tamaños distintos por hoja, no enteros en px: 266.4 × 116.4, 250.8 × 106.4…) y desplazamiento en px con decimales (8, 5; 8.4, 10.8; 18, 12…) | Probable: `xlsxwriter` emite `twoCellAnchor` con `editAs`; el tamaño y el desplazamiento se redondean a px enteros. Ver Q13 |
| L2 | Tema por defecto (`theme1.xml`: Cambria/Calibri, colores Office 2007–2010) | Probable que coincida (es el tema por defecto de `xlsxwriter`); se compara |
| L3 | Papel no declarado (`paperSize` ausente) | Se logra no llamando a `set_paper`; se comprueba que no se escriba |
| L4 | Formato condicional por hoja: fórmula `AND($F10<>"",$G10<>"",$F10<>$G10)` con `dxf` (cursiva + fondo ámbar, a medir) sobre `A10:J499`, `A10:I499` con `$E`/`$F` en la hoja por categoría y `A13:J13` en Resumen | Se pueden escribir con `conditional_format` tipo `formula`; el rango literal hasta 499 se extiende si hay más filas (req. 5); contenido del `dxf` por medir |
| L5 | Barras de datos `BFDBFE`, mínimo y máximo automáticos, sin extensión 2010 | `xlsxwriter` agrega la extensión 2010 y puede dibujar degradado; se prueba `bar_solid`/`data_bar_2010` |
| L6 | Color de fuente de tema (`color tema1`) con fuente Arial (p. ej. «Correo») | `xlsxwriter` solo fija colores RGB en formatos propios; el negro de tema se logra con el color por defecto, no con Arial + tema |
| L7 | Columnas ocultas con ancho (G–K de «No encontrados») y estilo de columna `style=18` | Se logra con `set_column(..., {'hidden': True})` y formato de columna |
| L8 | Texto alternativo y nombre de imagen («Image 1») | Se logra con `description` y el nombre de archivo; texto a medir |
| L9 | `topLeftCell`, `activeCell`, `tabSelected` | `set_top_left_cell`, `set_selection`, `activate`; ver Q11 |
| L10 | Metadatos invisibles del paquete (`calcId`, `baseColWidth`, `dyDescent`, `uid`, elementos de encabezado vacíos, canal alfa `00`, un medio por imagen) | No reproducibles; ver Q13 |

## Preguntas abiertas

Cerradas por decisión del humano:

- **Q1 (medición): CERRADA.** Plantillas medidas; ver `medicion-plantillas.md`. Las consecuencias de contenido pasan a Q6–Q10.
- **Q2 (qué hacer con lo no reproducible): CERRADA por D-2.** Se detiene y se pregunta; no hay aproximación silenciosa ni cambio de método sin decisión humana.
- **Q3 (huella versionada): CERRADA por D-3.** `backend/tests/plantillas/*.json`, sin datos reales; `informes/` sigue local.
- **Q4 (anchos y alturas): CERRADA por D-1.** Prevalecen los de la plantilla (celdas sin ajuste de texto; el texto largo se corta; ver R4).
- **Q5 (nombres de hoja y rótulos): CERRADA por D-1.** Se adoptan los de la plantilla (en su mayoría ya coinciden con los actuales).

## Decisiones del humano (2026-11-22) — Q6 a Q14 CERRADAS

Respondidas explícitamente por el humano en sesión el 2026-11-22. Cada una conserva debajo el planteamiento original como registro. Sin `[PENDIENTE]` restantes.

- **Q6: CERRADA, decisión del humano 2026-11-22: opción A.** Se adopta el orden y las hojas de la plantilla (Todos los activos, Por ubicación, No encontrados, una hoja por categoría, Por categoría, Resumen). «Por ubicación» y «Por categoría» pasan a hojas propias con las mismas cifras congeladas.
- **Q7: CERRADA, decisión del humano 2026-11-22: opción B.** Plantilla más filas finales en el Resumen con nombre de sesión, quién cerró y cuándo, moneda, estado «Informe congelado», la `NOTA` de cifras congeladas y los avisos `SIN_DETALLE` / `EMPRESA_VIGENTE`. La lista «Todos los activos» duplicada dentro del Resumen se omite como residuo (se registra en la matriz como «no reproducido por decisión»).
- **Q8: CERRADA, decisión del humano 2026-11-22: opción B.** Se conserva la tabla de Excel «Activos» y los filtros, con el estilo de la plantilla.
- **Q9: CERRADA, decisión del humano 2026-11-22: opción A.** El Excel de activos lleva logo, NIT, teléfono, correo, dirección y fecha de exportación desde los datos vigentes de la empresa del tenant, sin migración; los campos que falten se omiten.
- **Q10: CERRADA, decisión del humano 2026-11-22: opción A.** Logo ajustado dentro de la caja de cada hoja conservando proporción.
- **Q11: CERRADA, decisión del humano 2026-11-22: opción A.** Hoja activa, selección y desplazamiento = residuo de edición: primera hoja, A1; se registra en la matriz.
- **Q12: CERRADA, decisión del humano 2026-11-22: opción B.** Ajuste 1×1 en hojas cortas; 1 página de ancho × alto automático en las listas.
- **Q13: CERRADA, decisión del humano 2026-11-22.** Se acepta `twoCellAnchor editAs="oneCell"` con las mismas dimensiones visibles, y no se comparan metadatos invisibles (`calcId`, `baseColWidth`, canal alfa del borde, medios duplicados), listados en la matriz como «equivalente no idéntico». Si la sonda L1 de T1 demuestra que `xlsxwriter` sí puede `oneCellAnchor`, se usa. Cualquier otra propiedad que `xlsxwriter` no reproduzca: T1 se detiene y pregunta (sin aproximaciones silenciosas; cambiar de método exige decisión humana).

- **Q14: CERRADA, decisión del humano 2026-11-22.** «Corte» y «Cerrada» del Resumen se mantienen como TEXTO, no como fecha real de Excel. «Corte» es `Corte dd/mm/aaaa` y «Cerrada» es la fecha y hora de cierre en hora de Colombia, en texto. Motivo: coincide con la plantilla y es el comportamiento ya implementado y cubierto por la matriz y las pruebas.

### Decisiones del humano tras las sondas de T1 (2026-11-22)

- **L8:** se acepta como equivalente que la imagen se llame «Picture N» (no «Image 1») y lleve «Bloquear relación de aspecto», con el mismo tamaño y posición exactos.
- **Equivalentes aceptados fuera de Q13** (revisados grupo por grupo): `val="0"` en los `cfvo` de las barras de datos y `patternType` ausente en el `dxf` (L4/L5); `inlineStr`/`sharedStrings` y `fullCalcOnLoad` en activos; `s="18"` sin `customFormat`, `spans` y `thickBot` en filas; `cstate="print"` y `<a:ln>` vacío en imágenes; metadatos del paquete (geometría de ventana, `fileVersion`, `extLst` vacíos, banderas `apply*`). Se suman a los de Q13. Lista completa en `matriz.md`; cada uno fijado por una sonda.
- **Fila 26 (propiedades del documento):** título según el libro («Activos»; en el informe, el que ya escribe el generador), `creator` neutro «AssetControl», sin `lastModifiedBy` ni datos de equipo o personales. Hallazgo: `xlsxwriter` 3.3.1 siempre escribe `lastModifiedBy` con el valor de `creator`; decisión del coordinator 2026-11-22: `creator` = `lastModifiedBy` = «AssetControl» (única opción coherente), CONFIRMADA salvo que el humano pida ambos vacíos (ver `matriz.md`).

Registro del planteamiento original (histórico):

- **Q6 (estructura y orden del libro del informe).** La plantilla ordena: Todos los activos, Por ubicación, No encontrados, una hoja por categoría, Por categoría, Resumen; y saca las tablas «Por categoría» y «Por ubicación» del Resumen a hojas propias (B1, B2). Opciones: (A) adoptar el orden y las hojas de la plantilla, sin cambiar cifras; (B) conservar la estructura actual y aplicar solo el aspecto. Recomendación: A, por D-1 (la plantilla manda en nombres de hoja).
- **Q7 (contenido del Resumen y de los encabezados).** La plantilla no tiene lugar para: nombre de la sesión, quién cerró y cuándo, moneda, estado «Informe congelado», nota de cifras congeladas (`NOTA`), aviso `SIN_DETALLE` (sesiones antiguas sin detalle) ni el aviso `EMPRESA_VIGENTE` (datos de empresa no congelados); y trae en «Resumen» una lista «Todos los activos» duplicada (B3–B5). Opciones: (A) solo lo de la plantilla (se pierden esos textos); (B) plantilla más filas finales adicionales con esos textos, sin alterar lo medido. Sub-pregunta: la lista duplicada en «Resumen» (¿residuo de la plantilla o intencional?). Recomendación: B; conservar los avisos de honestidad del informe congelado y el nombre de la sesión (la plantilla ya no lo imprime en el encabezado de página); lista duplicada = residuo, se omite.
- **Q8 (tabla de Excel y filtros).** Hoy «Todos los activos» es una tabla «Activos» con filtros, y las demás listas llevan autofiltro; la plantilla no tiene tabla ni autofiltro en el informe (en activos sí hay autofiltro) y su texto igual menciona la «tabla «Activos»» (B10). Opciones: (A) sin tabla ni filtros en el informe (plantilla estricta; se ajusta el texto, que hoy lo promete); (B) conservar tabla y filtros con el estilo de la plantilla. Recomendación: B, para no perder la función que el texto de la propia plantilla anuncia.
- **Q9 (datos de empresa en el Excel de activos).** El Excel de activos hoy no lleva datos de la empresa; la plantilla pide logo, nombre, NIT, teléfono, correo, dirección y fecha de exportación (A3, A4). Opciones: (A) usar los datos vigentes de la empresa del tenant (lectura existente, sin migración) y omitir (con su rótulo, p. ej. «Correo») los campos que no existan; (B) dejar el bloque con solo la fecha. Recomendación: A.
- **Q10 (logo de tamaño variable).** La plantilla fija una caja por hoja (de 246 × 113.6 a 297 × 116 px) para un PNG de 600 × 240; el logo real de cada empresa puede tener otra proporción. Opciones: (A) ajustar el logo dentro de la caja de la hoja conservando su proporción, anclado en el desplazamiento de la plantilla; (B) estirar al tamaño exacto (deforma logos de otra proporción). Recomendación: A.
- **Q11 (hoja activa, selección y desplazamiento).** La plantilla guarda estado de edición: hoja seleccionada (en el informe «No encontrados», en activos la única), celdas activas arbitrarias (J17, C18, E15, E19, D22, B17) y la vista de «Resumen» desplazada a la fila 7. Opciones: (A) tratarlo como residuo de edición: abrir en la primera hoja, celda A1, sin desplazamiento, registrado en la matriz como «no reproducido por decisión»; (B) reproducirlo literalmente. Recomendación: A.
- **Q12 (ajuste a página).** La plantilla del informe usa 1 × 1 página en todas las hojas y área de impresión fija (B13); con cientos de filas la hoja se imprime en una página ilegible (el Excel de activos sí usa ancho 1 × alto automático). Opciones: (A) reproducir literalmente 1 × 1 (área hasta la última fila); (B) 1 × 1 en las hojas cortas (Por ubicación, Por categoría, Resumen) y 1 × automático en las listas (Todos, por categoría, No encontrados). Recomendación: B.
- **Q13 (lo que `xlsxwriter` no reproduce).** (a) La imagen: `xlsxwriter` no emite `oneCellAnchor` con `ext` en EMU exactos, sino `twoCellAnchor` con `editAs` y tamaños y desplazamientos enteros en px (L1). (b) Metadatos invisibles del paquete (L10). Opciones para (a): (A) aceptar `twoCellAnchor editAs="oneCell"` con las mismas dimensiones en px redondeadas, con aviso en la matriz; (B) cambiar de método (plantilla base + openpyxl), que exige decisión de arquitectura del humano. Opciones para (b): aceptar que no se comparen (equivalentes no idénticos), o exigirlos (implicaría B). Recomendación: A para (a) y aceptar (b), a confirmar tras la prueba L1 de T1. Si la prueba de T1 muestra que `xlsxwriter` sí lo logra, la pregunta se cierra sola.
- Sin conflicto con `docs/05-preguntas-abiertas.md` (P2 y R9/R9a siguen vigentes). Q6–Q13 son decisiones de producto de esta spec, no están en ese archivo.

Q1–Q13 están cerradas: no quedan `[PENDIENTE]` de producto, dominio ni precios. Verificación contra la regla de autonomía de `AGENTS.md`: (a) se deriva de `docs/01` (informe «exportable a PDF y Excel» y exportar la lista de activos en Excel; `docs/01` no fija la composición de hojas del libro), `docs/02` y `docs/03` (sin cambios de esquema); (b) no contradice ningún ADR ni la constitución (ADR-003: totales congelados, solo se presentan); (c) sin preguntas abiertas de producto, dominio o precios en `docs/05`. Observación para el humano: el cambio de composición del libro (Q6) y el nuevo contenido del Excel de activos (Q9) no contradicen `docs/01`, pero `docs/01` no los menciona; ya están decididos por el humano y no requieren edición de `docs/`.
