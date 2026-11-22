# Plan 019 — Diseño de los Excel según las plantillas

## Arquitectura

- Solo capa de presentación del generador Excel; sin cambios de datos ni de cálculo. Decisiones del humano 2026-11-22 (Q6–Q13 cerradas): hojas nuevas y orden de la plantilla (Q6), filas finales de contexto en el Resumen y lista duplicada omitida (Q7), tabla «Activos» y filtros conservados (Q8), datos de empresa en el Excel de activos (Q9), logo proporcional (Q10), hoja activa A1 (Q11), ajuste 1×1 en hojas cortas y 1×auto en listas (Q12), `twoCellAnchor editAs="oneCell"` aceptado salvo que L1 permita `oneCellAnchor` (Q13). Ninguna toca migraciones.
- Dinero: «Por ubicación» y «Por categoría» escriben los `Decimal` congelados de `cierre.informe` tal cual (conversión solo en el borde de `xlsxwriter` como ya hace el generador vigente; sin sumas ni cálculos nuevos en `float`); se prueba con centavos no representables en `float`.
- Privacidad: `specs/019-diseno-informes-excel/medicion-plantillas.md` y `informes/` contienen datos reales y no se versionan; huellas y `matriz.md` solo con marcadores.
- `backend/app/activos/exportar.py` (`a_excel`) y `backend/app/conteo/exportar.py` (`a_excel(doc)`), ambos con `xlsxwriter==3.3.1`, aplican la plantilla correspondiente.
- Estilos en módulos de constantes, con los valores medidos (nunca calculados ni números mágicos): `backend/app/conteo/exportar_estilo.py` (común a ambos generadores: banda, bloque de encabezado, logo, cabecera de tabla, total, datos, formatos, página) y, si hace falta, `backend/app/activos/exportar_estilo.py` para lo propio de la plantilla A (grises `4B5563`, cabecera Arial 10).
- Utilidad de prueba `backend/tests/utils_xlsx_diseno.py`: extrae propiedades de un `.xlsx` (openpyxl 3.1.5 para hoja y estilos; lectura directa del ZIP/XML para `drawing`, imágenes, tema, `workbook.xml`, `styles.xml`, formato condicional con su `dxf`, barras de datos con su `extLst`, validaciones) y las compara con la huella.
- Huella (D-3): `backend/tests/plantillas/activos.json` e `informe.json`; solo propiedades de diseño y rótulos fijos. Datos de empresa, cifras, fechas y textos con cifras se guardan como marcadores (`{empresa.nombre}`, `{n_activos}`, `{cop}`…). Una prueba opcional (se omite si `informes/` no existe) compara huella vs. plantilla original para detectar deriva.
- Imagen: se prueba primero en T1 (L1). Si `xlsxwriter` logra `oneCellAnchor`, se usa; si no, se acepta `twoCellAnchor editAs="oneCell"` con las mismas dimensiones visibles (decisión Q13). Cualquier otra propiedad no reproducible detiene T1 y se pregunta (D-2).
- Logo: se escala por factor único para caber en la caja de la hoja (Q10), conservando proporción, anclado en el desplazamiento de la plantilla.
- Resumen: lo de la plantilla (C2:D2, 4 tarjetas en filas 6–8) y, desde la fila 10, filas de contexto: sesión, cerró y cuándo, moneda, estado «Informe congelado», `NOTA`, `SIN_DETALLE`, `EMPRESA_VIGENTE`; sin la lista de las filas 9–13 de la plantilla.
- Impresión: Ubic., PorCat y Res. con `fit_to_pages(1, 1)`; Todos, Cat, NoEnc y A con `fit_to_pages(1, 0)` (Q12).
- Reservas de nombres de hoja: `nombres_de_hoja` suma `Por ubicación` y `Por categoría` a los reservados (spec B16).
- El `Documento` y `cierre.informe` no cambian; el generador del informe recibe los mismos datos que hoy. Para el Excel de activos, si se aprueba Q9, la ruta lee la empresa vigente y su logo con el servicio existente (`empresa_service`), sin migración.

## Tablas afectadas, endpoints, permisos, migraciones

- Tablas: ninguna. Migraciones: ninguna.
- Endpoints: sin cambios de ruta ni contrato (`GET /activos/exportar`, `GET /sesiones/{id}/informe/excel`).
- Permisos: sin cambios; ambos endpoints siguen `@require_role("admin")`. `test_roles.py` confirma 403 para `contador` y aislamiento por tenant.
- Dependencias: ninguna nueva.

## Matriz de trazabilidad (propiedad → valor de plantilla → dónde se implementa → prueba)

Valores medidos (`medicion-plantillas.md`). Plantilla A = `Activos_20261122_diseno.xlsx`; plantilla B = `Informe_boseto_limpio.xlsx`. Siglas: Todos = «Todos los activos»; Ubic. = «Por ubicación»; NoEnc = «No encontrados»; Cat = hoja por categoría (ejemplo «Electrodomésticos»); PorCat = «Por categoría»; Res = «Resumen». `N` = negrita (supuesto de la medición, T1 lo confirma). Por celda, el detalle exhaustivo lo genera T1 en `matriz.md` desde la huella.

| # | Propiedad | Valor de plantilla | Dónde se implementa | Prueba |
|---|---|---|---|---|
| 1 | Nombre y orden de hojas | A: `Activos`. B: Todos, Ubic., NoEnc., Cat…, PorCat., Res. (Q6 aprobado, decisión del humano 2026-11-22; hoy: Res., Todos, Cat…, NoEnc.) | `a_excel` (A y B) | `test_hojas_nombre_orden` |
| 2 | Color de pestaña | `FF1D4ED8` en las 7 hojas | `set_tab_color` | `test_color_pestana` |
| 3 | Visibilidad, hoja activa, selección | Todas visibles. `tabSelected`: A hoja 1; B «No encontrados». Selecciones: A J17; Todos C18; Ubic. A7:H9; NoEnc E15; Cat E19; PorCat D22; Res B17 con `topLeftCell` A7. NO REPRODUCIDO POR DECISIÓN (Q11, humano 2026-11-22): residuo de edición; el libro abre en la primera hoja, A1, sin desplazamiento | `activate`, `set_selection`, `set_top_left_cell` | `test_visibilidad_activa` |
| 4 | Fuente y tema por defecto del libro | Tema Office: mayor Cambria, menor Calibri; dk2 `1F497D`, lt2 `EEECE1`, accent1 `4F81BD`, accent2 `C0504D`, accent3 `9BBB59`, accent4 `8064A2`, accent5 `4BACC6`, accent6 `F79646`, hlink `0000FF`, folHlink `800080`. Celda sin estilo: Calibri 11 color tema 1 | formato base de `xlsxwriter` | `test_fuente_defecto` (L2) |
| 5a | Fuente: título del informe/activos | Arial 19 N `111827`, v centro (C2). En Res.: C2:D2 combinada, h centro | módulo de estilo | `test_fuentes` |
| 5b | Fuente: empresa | Arial 10 N `1D4ED8` (C3) | idem | `test_fuentes` |
| 5c | Fuente: fecha («Exportado»/«Corte»), teléfono, correo, dirección | Arial 10 (fecha) y Arial 9 (resto), color `6B7280` en B y `4B5563` en A; NIT Arial 9 N `111827` (C4) | idem | `test_fuentes` |
| 5d | Fuente: «Correo» (etiqueta) y correo en algunas hojas | Varía por hoja (Calibri 11 tema 1 en Todos F3/F4, Res. F3/F4 y Ubic. F3; Arial 11 tema 1 en Cat F3; Arial 10 `4B5563` en A G3). Se reproduce tal cual (R7) | idem | `test_fuentes` (L6) |
| 5e | Fuente: título de lista | Arial 12 N `111827` (A6) | idem | `test_fuentes` |
| 5f | Fuente: nota de lista | Arial 9 `6B7280`, ajuste de texto (A7) | idem | `test_fuentes` |
| 5g | Fuente: cabecera de tabla | B: Arial 9 N `FFFFFF`; A: Arial 10 N `FFFFFF` | idem | `test_fuentes` |
| 5h | Fuente: datos y total | Arial 10 `111827`; total Arial 10 N `111827` | idem | `test_fuentes` |
| 5i | Fuente: tarjetas de Res. | Rótulo Arial 9 N `1D4ED8` (A6, C6, E6; G6 Arial 9 `6B7280` sin N); valor Arial 18 N `111827`; subtexto Arial 9 `6B7280` | idem | `test_fuentes` |
| 6 | Relleno | Banda fila 1: sólido `FF1D4ED8` (A1:L1 en A; A1:J1 Todos y Res.; A1:H1 Ubic. y PorCat; A1:F1 NoEnc; A1:I1 Cat). Cabecera: sólido `FF1F2937`. Total de Ubic./PorCat: sólido `FFDBEAFE`. Resto sin relleno | idem | `test_rellenos` |
| 7 | Bordes | Cabecera, datos y total: fino `9CA3AF` en 4 lados (en B el color se guarda `009CA3AF`, en A `FF9CA3AF`: R7/Q13). C5 (dirección): inferior medio `FF1D4ED8` (rango completo de la fila 5: T1). A6 de listas: inferior fino `FF111827`. Banda, título y tarjetas sin borde | idem | `test_bordes` |
| 8 | Alineación | Cabecera: centro/centro con ajuste; datos y total: centro/centro sin ajuste (J8 de Todos: derecha); nota A7: v centro con ajuste; A6 de Todos/Cat/NoEnc: izquierda/centro; A6 de Ubic./PorCat y Res.: general/base; tarjetas centradas; sin sangría ni rotación (0) | idem | `test_alineacion` |
| 9 | Formatos numéricos y de fecha | `"$"\ #,##0.00` (dinero), `#,##0` (unidades), `0.0\ %` (porcentaje), fecha incorporada 14 (`mm-dd-yy`, A: J y L), `General` (texto) | idem | `test_formatos_numericos` |
| 10a | Anchos A (12 col.) | 14, 30, 20, 22, 14, 18, 16, 16, 16, 18, 20, 20 | `set_column` | `test_anchos_columna` |
| 10b | Anchos B (A–J) | Todos, Ubic., NoEnc., Cat, PorCat: 14, 26, 18, 18, 22, 22, 20, 16, 16, 18. Res.: 24, 26, 18, 18, 22, 22, 20, 16, 16, 18. NoEnc: columnas G–K ocultas (20, 16, 16, 18, 13) | idem | `test_anchos_columna` (L7) |
| 11a | Alturas A (pt) | f1 6; f2 44.1; f3 18; f4 18; f5 15.95; f6 por defecto; f7 30; f8 y siguientes 20.1 | `set_row` | `test_alturas_fila` |
| 11b | Alturas B (pt) | f1–f5 como A. Todos y Cat: f6 26.1, f7 26.1, f8 21.95, f9 27.95, datos 21.95. Ubic. y PorCat: f6 26.1, f7 27.95, f8 21.95, f9 21.95. NoEnc: f6 26.1, f7 26.1, f8 21.95, f9 27.95. Res.: f6 15.95, f7 30, f8 15.95 (f9–f13 de la lista omitida por Q7: no reproducidas por decisión; las filas de contexto usan la altura por defecto) | idem | `test_alturas_fila` |
| 12 | Celdas combinadas | A: ninguna. B: Todos A7:J7; NoEnc A7:F7; Cat A7:I7; Res. C2:D2 (A10:J10 pertenece a la lista omitida por Q7: no reproducido por decisión); Ubic. y PorCat ninguna | `merge_range` | `test_combinaciones` |
| 13a | Imagen A | oneCellAnchor desde col 0 +8.0 px, fila 1 +5.0 px; ext 2828926 × 1104900 EMU (297.0 × 116.0 px); PNG 600 × 240, sin pHYs; nombre «Image 1»; con texto alternativo | `insert_image` | `test_imagenes` (L1, L8) |
| 13b | Imágenes B (misma PNG en cada hoja) | Todos: +8.4/+10.8 px, 2537460 × 1108710 (266.4 × 116.4). Ubic.: +18.0/+12.0, 2388870 × 1013460 (250.8 × 106.4). NoEnc: +11.8/+9.6, 2411730 × 1083944 (253.2 × 113.8). Cat: +16.0/+6.6, 2396490 × 1082040 (251.6 × 113.6). PorCat: +13.6/+6.0, 2343150 × 1082040 (246.0 × 113.6). Res.: +21.6/+7.2, 2606040 × 1074420 (273.6 × 112.8). Todas oneCellAnchor desde columna 0, fila 1 (generado: `oneCellAnchor` si L1 lo permite; si no, `twoCellAnchor editAs="oneCell"` con las mismas dimensiones visibles, «equivalente no idéntico» por Q13). Logo real: ajustado dentro de la caja conservando proporción (Q10) | idem | `test_imagenes` |
| 14 | Congelados | A: fila 7 (`ySplit` 7, `A8`). B: Todos, NoEnc y Cat: `ySplit` 9 (`A10`); Ubic., PorCat y Res.: ninguno. Sin columnas congeladas | `freeze_panes` | `test_congelados` |
| 15 | Orientación, papel, ajuste | Horizontal; papel sin declarar; sin escala. A: ancho 1 × alto automático (0). B (Q12, decisión del humano 2026-11-22): 1 × 1 en Ubic., PorCat y Res.; 1 página de ancho × alto automático en Todos, Cat y NoEnc (la plantilla trae 1 × 1 en las 6: desviación aprobada). Sin centrado horizontal | `set_landscape`, `fit_to_pages` (no `set_paper`) | `test_pagina` (L3) |
| 16 | Márgenes (pulg.) | izq 0.4, der 0.4, sup 0.6, inf 0.6; encabezado/pie 0.5 en A y 0.3 en B | `set_margins` | `test_margenes` |
| 17 | Encabezado y pie de impresión | Encabezado vacío. Pie: `&L&8 Generado con AssetControl&R&8 Página &P de &N` (con espacio tras `&8`) | `set_header`, `set_footer` | `test_encabezado_pie` |
| 18 | Área de impresión y filas a repetir | A: `A1:L…` (plantilla `A1:L8`); repetir fila 7. B: Todos `A1:J…` (plantilla `A1:J10`), repetir fila 9; Ubic. `A1:H…`; NoEnc `A1:F…`, repetir fila 9; Cat `A1:I…`, repetir fila 9; PorCat `A1:H…`; Res. `A1:J…`; sin columnas repetidas. «…» = última fila escrita | `print_area`, `repeat_rows` | `test_area_impresion` |
| 19 | Zoom | 100 (sin atributo) en todas | no se llama a `set_zoom` | `test_zoom` |
| 20 | Cuadrícula | Pantalla oculta en las 7 hojas; impresión: por medir (T1) | `hide_gridlines` | `test_cuadricula` |
| 21 | Agrupación y ocultas | Sin agrupación; ocultas solo las columnas G–K de NoEnc | `set_column` | `test_agrupacion_ocultas` |
| 22 | Validaciones de datos | Ninguna | — | `test_validaciones` (verifica que no hay) |
| 23a | Formato condicional por fórmula | Todos `A10:J499`: `AND($F10<>"",$G10<>"",$F10<>$G10)`, `dxf` 0. Cat `A10:I499`: `AND($E10<>"",$F10<>"",$E10<>$F10)`. Res. `A13:J13`: `AND($F13<>"",$G13<>"",$F13<>$G13)` (pertenece a la lista omitida por Q7: no reproducido por decisión). El contenido del `dxf` (cursiva y fondo ámbar según la nota) se mide en T1. El rango se extiende si hay más filas. Decisiones del humano 2026-11-22 (T4): se ACEPTA como equivalente el `dxf` deduplicado por `xlsxwriter` (un solo `dxf` para las reglas idénticas; cada regla resuelve al mismo estilo); «En reparación» y «Dañado» van sin relleno ámbar fijo, como la plantilla, sin regla condicional extra | `conditional_format` | `test_formato_condicional` (L4) |
| 23b | Barras de datos | Ubic. y PorCat: F y H de las filas de datos; mínimo y máximo automáticos; color `FFBFDBFE`; extensión por medir | `conditional_format` data_bar | `test_formato_condicional` (L5) |
| 24 | Autofiltro, hipervínculos, protección | A: autofiltro `A7:L…` (nombre oculto `_FilterDatabase` = `Activos!$A$7:$L…`). B: la plantilla no tiene tabla ni autofiltro; por Q8 (humano 2026-11-22) se CONSERVA la tabla de Excel «Activos» en «Todos los activos» y los filtros en las listas, con el estilo de la plantilla (desviación aprobada; el estilo de tabla no debe alterar fuente, relleno ni bordes medidos). Sin hipervínculos ni protección | `autofilter` | `test_filtro_enlaces_proteccion` |
| 25a | Textos: A | «Inventario de activos»; empresa; «Exportado dd/mm/aaaa» (E3); NIT `NIT {nit}` (C4); `Tel. {tel}` (E4); «Correo» (G3) y el correo (G4); dirección (C5). Cabecera en fila 7: Código, Nombre, Categoría, Ubicación, Estado, Serial, Marca, Modelo, Subtipo, Fecha de compra, Precio de compra, Registrado el | generador | `test_textos_rotulos` |
| 25b | Textos: B, bloque común | «Informe de activos» (C2; en Res. combinada C2:D2); empresa (C3); «Corte dd/mm/aaaa» (E3); «Correo» (F3, salvo Ubic. y NoEnc según hoja: T1); NIT (C4); `Tel. …` (E4; en NoEnc D4); correo (F4; en NoEnc E4); dirección (C5) | generador | `test_textos_rotulos` |
| 25c | Textos: títulos de lista | Todos «Todos los activos del cierre»; Ubic. «Por ubicación»; NoEnc «No encontrados (lista congelada al cierre)»; Cat «Categoría: {etiqueta}»; PorCat «Por categoría»; Res. «Todos los activos» (A9): NO REPRODUCIDO POR DECISIÓN (Q7, humano 2026-11-22: lista duplicada = residuo; filas 9–13 de la plantilla en Res. se sustituyen por las filas de contexto) | generador | `test_textos_rotulos` |
| 25d | Textos: notas de lista | Todos: `{N} activo(s) · encontrados {n} ({pct}) por {cop} · no encontrados {n} por {cop} · tabla «Activos», lista para filtrar o hacer una tabla dinámica. En cursiva y fondo ámbar: se encontró en otra ubicación.` Cat: igual sin la frase de la tabla. NoEnc: `{N} activos no encontrados por {cop}.` (coincide con el generador actual) | generador | `test_textos_rotulos` |
| 25e | Textos: cabeceras | Todos: Código, Activo, Categoría, Marca, Serial, Ubicación esperada, Encontrado en, Estado físico, Resultado, Precio (COP). Cat: sin Categoría. NoEnc: Código, Activo, Categoría, Ubicación esperada, Nota al cierre, Precio (COP). Ubic./PorCat: «Ubicación (al cierre)» o «Categoría (al cierre)», Valor encontrado, Unid. encontradas, Valor no encontrado, Unid. no encontradas, Valor registrado, Unid. registradas, % encontrado | generador | `test_textos_rotulos` |
| 25f | Textos: Res. | Tarjetas en A, C, E, G: rótulos Encontrado, No encontrado, Total registrado, % encontrado (fila 6); valores (fila 7: dinero, dinero, dinero, `0.0 %`); subtexto (fila 8): `{n} unidad(es)` y «de las unidades registradas» | generador | `test_textos_rotulos` |
| 25g | Textos: filas finales del Resumen (adición, Q7) | Desde la fila 10: «Sesión» {nombre}; «Cerró» {usuario}, «Cerrada» {fecha/hora}; «Moneda» COP; «Estado» «Informe congelado»; `NOTA` de cifras congeladas; `SIN_DETALLE` y `EMPRESA_VIGENTE` solo si aplican. Textos tal como hoy en el generador; estilo: fuente Arial 9/10 de la paleta de la plantilla (sin inventar valores nuevos: T1 fija el estilo con los de las notas de lista) | generador | `test_textos_rotulos`, `test_resumen_contexto` |
| 25h | Textos y datos: Excel de activos (Q9) | Logo, NIT, teléfono, correo, dirección desde la empresa vigente del tenant; fecha de exportación; los campos ausentes se omiten (con su rótulo) | `exportar.py` de activos, lectura con `empresa_service` | `test_activos_exportar` (empresa completa, sin logo, sin NIT/teléfono/correo) |
| 26 | Propiedades del documento | Sin medir (T1 lo mide); hoy `title` = «Activos» (A) | `set_properties` | `test_propiedades_documento` |
| 27 | Cobertura XML | Cada elemento/atributo de `sheetN.xml`, `styles.xml`, `drawingN.xml`, `workbook.xml` (incluidos `sheetFormatPr`, `calcPr` `fullCalcOnLoad=1` en B y `calcId=0` en A, nombres definidos) aparece en una fila o está declarado «equivalente no idéntico» por decisión Q13 (humano 2026-11-22): `calcId`, `baseColWidth`, canal alfa del borde, medios duplicados, `oneCellAnchor` vs `twoCellAnchor editAs="oneCell"` | utilidad de prueba | `test_cobertura_matriz` |

Disposición por hoja (bloque común + cuerpo) para guiar la implementación:

| Hoja | Filas de título y cuerpo | Datos desde |
|---|---|---|
| Activos (A) | f6 vacía; f7 cabecera; f8 datos | f8 |
| Todos | f6 título, f7 nota (combinada), f8 Total, f9 cabecera, f10 datos | f10 |
| Ubic. y PorCat | f6 título, f7 cabecera, f8 datos, fila final Total | f8 |
| NoEnc | f6 título, f7 nota (combinada), f8 Total, f9 cabecera, f10 datos (la plantilla no trae fila de datos con estilo; decisión del humano 2026-11-22: los mismos estilos de datos de las otras listas —texto, COP y vacía de Todos—, sin filas alternas; sin formato condicional porque la hoja no tiene «Encontrado en»; detalle en `matriz.md`, «Hojas de lista del informe (T4)») | f10 |
| Cat | igual que Todos, sin columna Categoría | f10 |
| Res. | f6 rótulos, f7 valores, f8 subtexto; desde f10 filas de contexto (Q7: sesión, cierre, moneda, estado, `NOTA`, avisos); sin lista (f9–f13 de la plantilla omitidas por Q7) | — |

Fila Total de las listas: «Total», etiqueta en B, conteo («N activos») en la penúltima columna y el valor congelado en la última; las celdas intermedias con borde y sin texto (igual que `banda_total` hoy). Ubic./PorCat: Total con fondo `DBEAFE`, mismas columnas que los datos.

## Estrategia de pruebas

- Primero la prueba (rojo): comparación generado vs. huella, propiedad por propiedad, con mensajes «hoja, celda, propiedad, esperado, obtenido».
- Datos sintéticos con empresa de marcadores; nunca datos reales.
- Las pruebas de contenido existentes (`test_activos_exportar.py`, `test_exportar_documento.py`) no se relajan; solo se actualizan aserciones de estilo y la estructura aprobada en Q6–Q8.
- `test_exportar_api.py`: encabezados HTTP y nombre de archivo sin cambios.
- `test_roles.py`: `contador` recibe 403 en ambos Excel; `admin` 200; aislamiento por tenant.
- Variabilidad: 0 filas, muchas filas (rango del formato condicional, área de impresión y barras de datos se extienden), nombre de ubicación/categoría largo (≤ 31 UTF-16, reservados nuevos), informe sin no encontrados, informe sin detalle (sesión antigua), empresa sin logo o sin NIT/teléfono/correo.
- Sonda L1–L10 en T1; la falla de una detiene la tarea (D-2).
- Verificación manual: abrir cada archivo junto a su plantilla en Excel real, con checklist (T6): logo, banda, cabecera, anchos, congelado, barras de datos, formato condicional, impresión 1 × 1, columnas ocultas, `####` en las tarjetas (R6), fechas según configuración regional.

## Riesgos

Ver `spec.md` (R1–R9). R8 (privacidad de `medicion-plantillas.md`) vigente: no versionar. Adicional: el volumen de filas cambia la altura de repetición de estilos; se prueba con datos sintéticos.

## Alternativa descartada

Usar la plantilla `.xlsx` como base y rellenarla con openpyxl: reproduciría el ancla `oneCellAnchor`, los EMU y los metadatos de forma automática, pero abandona el generador `xlsxwriter` vigente, arriesga arrastrar datos o metadatos reales de la plantilla y es un cambio de método. Por D-2 ya no es una opción para el implementador; solo el humano puede reabrirla (en Q13 eligió aceptar `twoCellAnchor editAs="oneCell"` con `xlsxwriter`, 2026-11-22).
