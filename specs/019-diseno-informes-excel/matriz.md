# Matriz de detalle 019 — generada desde la huella (T1)

> Generada por `backend/tests/utils_xlsx_diseno.py` desde `backend/tests/plantillas/*.json`. Solo marcadores: sin datos reales de la clínica. No editar a mano: regenerar. La matriz resumida (filas 1–27) está en `plan.md`; aquí está el detalle por celda, columna, fila e imagen, y la cobertura XML.

Leyenda: `N` = negrita (confirmado en T1: `<b val="1"/>` / `<b/>`), `K` = cursiva. Colores en ARGB tal como los guarda la plantilla (el canal alfa no se compara, Q13).

## Hallazgos de T1 (lo que la medición previa no leyó)

- Contenido de los `dxf` del informe (3, idénticos): fuente cursiva color `FF92400E`; relleno sólido `FFFDE68A` (fg = bg). Activos: 0 `dxf`.
- Barras de datos (Por ubicación y Por categoría, F8 y H8): sin `extLst` (sin extensión 2010), `cfvo` min y max sin `val`, color `FFBFDBFE`, prioridades 1 y 2.
- Cuadrícula al imprimir: no hay `printOptions` en ninguna hoja → no se imprime.
- Texto alternativo de las 7 imágenes: `descr="Picture"`; nombre `Image 1`.
- Propiedades del documento: `creator` = `openpyxl` en ambas; `lastModifiedBy`, `created` y `modified` con valores del equipo que guardó (marcadores); sin título, asunto ni palabras clave. No se copian: ver «Propiedades del documento (fila 26)».
- Fila 5 (borde inferior medio `FF1D4ED8`): Activos A5:L5; Todos A5:J5; Por ubicación A5:H5; No encontrados A5:F5; categoría A5:I5; Por categoría A5:H5; Resumen A5:J5 (= el ancho de la banda de la fila 1).
- `N` es negrita: confirmado (`<b val="1"/>` en el informe, `<b/>` en activos).
- Anchos: el valor guardado (`width`) de la plantilla es el que se compara; con xlsxwriter se obtiene exacto con `set_column_pixels(7 × ancho)`.
- Alturas con decimales (44.1, 15.95, 26.1, 21.95, 27.95, 20.1): `set_row` las redondea a píxel; `set_row_pixels(alto / 0.75)` las escribe exactas.

## Plantilla `activos` (`Activos_20261122_diseno.xlsx`)

- Hojas (orden): Activos
- Hoja activa: 0 (Q11: no se reproduce; primera hoja, A1)
- Nombres definidos: `_xlnm._FilterDatabase`[0] = `Activos!$A$7:$L$8`; `_xlnm.Print_Area`[0] = `Activos!$A$1:$L$8`; `_xlnm.Print_Titles`[0] = `Activos!$7:$7`
- `calcPr`: `{'calcId': '0'}` (EQ Q13)
- Tema: Office Theme; mayor Cambria, menor Calibri
- Fuente por defecto: `{'tamano': 11, 'color': {'theme': 1}, 'nombre': 'Calibri', 'familia': 2, 'esquema': 'minor', 'negrita': False, 'cursiva': False, 'tachado': False}`
- dxfs: `[]`
- Propiedades: `{'core': {'creator': 'openpyxl', 'lastModifiedBy': '{lastModifiedBy}', 'created': '{created}', 'modified': '{modified}'}, 'app': {'Application': 'Microsoft Excel', 'AppVersion': '16.0300'}}`

### Hoja `Activos`

- Pestaña `FF1D4ED8`; cuadrícula en pantalla oculta; zoom 100; congelado `{'x_split': None, 'y_split': 7, 'celda_superior_izquierda': 'A8', 'panel_activo': 'bottomLeft', 'estado': 'frozen'}`
- Selección `[{'panel': 'bottomLeft', 'celda_activa': 'J17', 'rango': 'J17'}]`, tabSelected True, topLeftCell `None` (Q11: no se reproduce)
- Formato de hoja `{'alto_fila_defecto': 15, 'ancho_col_defecto': 9.140625, 'ancho_base': 10, 'filas_ocultas_defecto': False, 'alto_propio_defecto': False}`
- Combinadas: ['C5:D5', 'E5:F5', 'G5:L5']
- Autofiltro `A7:L8`; tablas `[]`; validaciones ninguna; hipervínculos ninguno; protección None
- Impresión `{'area': 'Activos!$A$1:$L$8', 'titulos': 'Activos!$7:$7', 'filtro': 'Activos!$A$7:$L$8'}`
- Página `{'margenes': {'left': 0.4, 'right': 0.4, 'top': 0.6, 'bottom': 0.6, 'header': 0.5, 'footer': 0.5}, 'orientacion': 'landscape', 'papel': None, 'escala': None, 'ajustar_a_pagina': True, 'ajuste_ancho': 1, 'ajuste_alto': 0, 'primera_pagina': None, 'orden': None, 'blanco_y_negro': False, 'cuadricula_impresa': False, 'encabezados_impresos': False, 'centrado_horizontal': False, 'centrado_vertical': False, 'encabezado_pie': {'oddFooter': '&L&8 Generado con AssetControl&R&8 Página &P de &N'}, 'encabezado_pie_distinto_primera': False, 'encabezado_pie_pares_impares': False, 'saltos_fila': 0, 'saltos_columna': 0}`

| Columnas | Ancho guardado | Oculta | Estilo de columna |
|---|---|---|---|
| A | 14 | False | - |
| B | 30 | False | - |
| C | 20 | False | - |
| D | 22 | False | - |
| E | 14 | False | - |
| F | 18 | False | - |
| G–I | 16 | False | - |
| J | 18 | False | - |
| K–L | 20 | False | - |

| Fila | Alto (pt) | Propio | Estilo de fila |
|---|---|---|---|
| 1 | 6 | True | - |
| 2 | 44.1 | True | - |
| 3 | 18 | True | - |
| 4 | 16 | True | - |
| 5 | 30 | True | - |
| 7 | 30 | True | - |
| 8 | 20.1 | True | - |

| Celda | Valor | Estilo resuelto | Fila de matriz / decisión |
|---|---|---|---|
| A1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| B1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| C1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| D1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| E1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| F1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| G1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| H1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| I1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| J1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| K1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| L1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| C2 | Inventario de activos | Arial 19 N FF111827; alin general/center | 5–9, 25 |
| C3 | Informe · {empresa.nombre} · exportado {fecha} | Arial 10 FF4B5563; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| D3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| E3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| F3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| G3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| H3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| I3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| J3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| K3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| L3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| C4 | Empresa | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| D4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| E4 | Contacto | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| F4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| G4 | Dirección | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| H4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| I4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| J4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| K4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| L4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| A5 |  | Calibri 11 tema 1; borde B:medium FF1D4ED8; alin general/bottom | 5–9, 25 |
| B5 |  | Calibri 11 tema 1; borde B:medium FF1D4ED8; alin general/bottom | 5–9, 25 |
| C5 | {empresa.nombre}
NIT {empresa.nit} | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| D5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| E5 | {empresa.correo}
Tel. {empresa.telefono} | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| F5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| G5 | {empresa.direccion} | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| H5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| I5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| J5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| K5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| L5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| A7 | Código | Arial 10 N FFFFFFFF; relleno solid FF1F2937; borde L:thin FF9CA3AF, R:thin FF9CA3AF, T:thin FF9CA3AF, B:thin FF9CA3AF; alin center/center ajuste | 5–9, 25 |
| B7 | Nombre | Arial 10 N FFFFFFFF; relleno solid FF1F2937; borde L:thin FF9CA3AF, R:thin FF9CA3AF, T:thin FF9CA3AF, B:thin FF9CA3AF; alin center/center ajuste | 5–9, 25 |
| C7 | Categoría | Arial 10 N FFFFFFFF; relleno solid FF1F2937; borde L:thin FF9CA3AF, R:thin FF9CA3AF, T:thin FF9CA3AF, B:thin FF9CA3AF; alin center/center ajuste | 5–9, 25 |
| D7 | Ubicación | Arial 10 N FFFFFFFF; relleno solid FF1F2937; borde L:thin FF9CA3AF, R:thin FF9CA3AF, T:thin FF9CA3AF, B:thin FF9CA3AF; alin center/center ajuste | 5–9, 25 |
| E7 | Estado | Arial 10 N FFFFFFFF; relleno solid FF1F2937; borde L:thin FF9CA3AF, R:thin FF9CA3AF, T:thin FF9CA3AF, B:thin FF9CA3AF; alin center/center ajuste | 5–9, 25 |
| F7 | Serial | Arial 10 N FFFFFFFF; relleno solid FF1F2937; borde L:thin FF9CA3AF, R:thin FF9CA3AF, T:thin FF9CA3AF, B:thin FF9CA3AF; alin center/center ajuste | 5–9, 25 |
| G7 | Marca | Arial 10 N FFFFFFFF; relleno solid FF1F2937; borde L:thin FF9CA3AF, R:thin FF9CA3AF, T:thin FF9CA3AF, B:thin FF9CA3AF; alin center/center ajuste | 5–9, 25 |
| H7 | Modelo | Arial 10 N FFFFFFFF; relleno solid FF1F2937; borde L:thin FF9CA3AF, R:thin FF9CA3AF, T:thin FF9CA3AF, B:thin FF9CA3AF; alin center/center ajuste | 5–9, 25 |
| I7 | Subtipo | Arial 10 N FFFFFFFF; relleno solid FF1F2937; borde L:thin FF9CA3AF, R:thin FF9CA3AF, T:thin FF9CA3AF, B:thin FF9CA3AF; alin center/center ajuste | 5–9, 25 |
| J7 | Fecha de compra | Arial 10 N FFFFFFFF; relleno solid FF1F2937; borde L:thin FF9CA3AF, R:thin FF9CA3AF, T:thin FF9CA3AF, B:thin FF9CA3AF; alin center/center ajuste | 5–9, 25 |
| K7 | Precio de compra | Arial 10 N FFFFFFFF; relleno solid FF1F2937; borde L:thin FF9CA3AF, R:thin FF9CA3AF, T:thin FF9CA3AF, B:thin FF9CA3AF; alin center/center ajuste | 5–9, 25 |
| L7 | Registrado el | Arial 10 N FFFFFFFF; relleno solid FF1F2937; borde L:thin FF9CA3AF, R:thin FF9CA3AF, T:thin FF9CA3AF, B:thin FF9CA3AF; alin center/center ajuste | 5–9, 25 |
| A8 | {texto} | Arial 10 FF111827; borde L:thin FF9CA3AF, R:thin FF9CA3AF, T:thin FF9CA3AF, B:thin FF9CA3AF; alin center/center | 5–9, 25 |
| B8 | {texto} | Arial 10 FF111827; borde L:thin FF9CA3AF, R:thin FF9CA3AF, T:thin FF9CA3AF, B:thin FF9CA3AF; alin center/center | 5–9, 25 |
| C8 | {texto} | Arial 10 FF111827; borde L:thin FF9CA3AF, R:thin FF9CA3AF, T:thin FF9CA3AF, B:thin FF9CA3AF; alin center/center | 5–9, 25 |
| D8 | {texto} | Arial 10 FF111827; borde L:thin FF9CA3AF, R:thin FF9CA3AF, T:thin FF9CA3AF, B:thin FF9CA3AF; alin center/center | 5–9, 25 |
| E8 | {texto} | Arial 10 FF111827; borde L:thin FF9CA3AF, R:thin FF9CA3AF, T:thin FF9CA3AF, B:thin FF9CA3AF; alin center/center | 5–9, 25 |
| F8 |  | Arial 10 FF111827; borde L:thin FF9CA3AF, R:thin FF9CA3AF, T:thin FF9CA3AF, B:thin FF9CA3AF; alin center/center | 5–9, 25 |
| G8 | {texto} | Arial 10 FF111827; borde L:thin FF9CA3AF, R:thin FF9CA3AF, T:thin FF9CA3AF, B:thin FF9CA3AF; alin center/center | 5–9, 25 |
| H8 | {texto} | Arial 10 FF111827; borde L:thin FF9CA3AF, R:thin FF9CA3AF, T:thin FF9CA3AF, B:thin FF9CA3AF; alin center/center | 5–9, 25 |
| I8 |  | Arial 10 FF111827; borde L:thin FF9CA3AF, R:thin FF9CA3AF, T:thin FF9CA3AF, B:thin FF9CA3AF; alin center/center | 5–9, 25 |
| J8 | {fecha} | Arial 10 FF111827; borde L:thin FF9CA3AF, R:thin FF9CA3AF, T:thin FF9CA3AF, B:thin FF9CA3AF; alin center/center; formato `mm-dd-yy` | 5–9, 25 |
| K8 | {numero} | Arial 10 FF111827; borde L:thin FF9CA3AF, R:thin FF9CA3AF, T:thin FF9CA3AF, B:thin FF9CA3AF; alin center/center; formato `"$"\ #,##0.00` | 5–9, 25 |
| L8 | {fecha} | Arial 10 FF111827; borde L:thin FF9CA3AF, R:thin FF9CA3AF, T:thin FF9CA3AF, B:thin FF9CA3AF; alin center/center; formato `mm-dd-yy` | 5–9, 25 |

| Formato condicional | Detalle |
|---|---|

| Imagen | Detalle |
|---|---|
| 1 | `{'ancla': 'oneCellAnchor', 'edit_as': None, 'desde': {'col': 0, 'col_off': 76199, 'fila': 1, 'fila_off': 47625}, 'hasta': None, 'ext': {'cx': 2828926, 'cy': 1104900}, 'xfrm': {'x': 76199, 'y': 123825, 'cx': 2828926, 'cy': 1104900}, 'nombre': 'Image 1', 'descr': 'Picture', 'titulo': None, 'oculta': False, 'decorativa': False, 'bloqueos': {}, 'cstate': 'print', 'estirar': True, 'geometria': 'rect', 'linea': None, 'medio': 'xl/media/image1.png', 'imagen': {'formato': 'png', 'phys': None, 'ancho': 600, 'alto': 240}}` |

### Cobertura XML `activos`

| Parte:ruta | Fila de matriz / decisión |
|---|---|
| `workbook:workbook` | estructura |
| `workbook:workbook/AlternateContent` | EQ L10: metadatos de la aplicación que guardó (Q13) |
| `workbook:workbook/AlternateContent/Choice` | EQ L10: metadatos de la aplicación que guardó (Q13) |
| `workbook:workbook/AlternateContent/Choice/absPath` | EQ L10: metadatos de la aplicación que guardó (Q13) |
| `workbook:workbook/AlternateContent/Choice/absPath@url` | EQ L10: metadatos de la aplicación que guardó (Q13) |
| `workbook:workbook/AlternateContent/Choice@Requires` | EQ L10: metadatos de la aplicación que guardó (Q13) |
| `workbook:workbook/bookViews` | 3 visibilidad |
| `workbook:workbook/bookViews/workbookView` | 3 visibilidad |
| `workbook:workbook/bookViews/workbookView@uid` | EQ L10: geometría de ventana del equipo que guardó (Q11/Q13) |
| `workbook:workbook/bookViews/workbookView@windowHeight` | EQ L10: geometría de ventana del equipo que guardó (Q11/Q13) |
| `workbook:workbook/bookViews/workbookView@windowWidth` | EQ L10: geometría de ventana del equipo que guardó (Q11/Q13) |
| `workbook:workbook/bookViews/workbookView@xWindow` | EQ L10: geometría de ventana del equipo que guardó (Q11/Q13) |
| `workbook:workbook/bookViews/workbookView@yWindow` | EQ L10: geometría de ventana del equipo que guardó (Q11/Q13) |
| `workbook:workbook/calcPr` | EQ Q13: calcPr (calcId, fullCalcOnLoad) |
| `workbook:workbook/calcPr@calcId` | EQ Q13: calcPr (calcId, fullCalcOnLoad) |
| `workbook:workbook/definedNames` | 18 área de impresión y filas a repetir; 24 filtro |
| `workbook:workbook/definedNames/definedName` | 18 área de impresión y filas a repetir; 24 filtro |
| `workbook:workbook/definedNames/definedName@hidden` | 18 área de impresión y filas a repetir; 24 filtro |
| `workbook:workbook/definedNames/definedName@localSheetId` | 18 área de impresión y filas a repetir; 24 filtro |
| `workbook:workbook/definedNames/definedName@name` | 18 área de impresión y filas a repetir; 24 filtro |
| `workbook:workbook/extLst` | EQ L10: metadatos de la aplicación que guardó (Q13) |
| `workbook:workbook/extLst/ext` | EQ L10: metadatos de la aplicación que guardó (Q13) |
| `workbook:workbook/extLst/ext/version` | EQ L10: metadatos de la aplicación que guardó (Q13) |
| `workbook:workbook/extLst/ext/version@setVersion` | EQ L10: metadatos de la aplicación que guardó (Q13) |
| `workbook:workbook/extLst/ext@uri` | EQ L10: metadatos de la aplicación que guardó (Q13) |
| `workbook:workbook/fileVersion` | EQ L10: metadatos de la aplicación que guardó (Q13) |
| `workbook:workbook/fileVersion@appName` | EQ L10: metadatos de la aplicación que guardó (Q13) |
| `workbook:workbook/fileVersion@lastEdited` | EQ L10: metadatos de la aplicación que guardó (Q13) |
| `workbook:workbook/fileVersion@lowestEdited` | EQ L10: metadatos de la aplicación que guardó (Q13) |
| `workbook:workbook/fileVersion@rupBuild` | EQ L10: metadatos de la aplicación que guardó (Q13) |
| `workbook:workbook/revisionPtr` | EQ L10: metadatos de la aplicación que guardó (Q13) |
| `workbook:workbook/revisionPtr@coauthVersionLast` | EQ L10: metadatos de la aplicación que guardó (Q13) |
| `workbook:workbook/revisionPtr@coauthVersionMax` | EQ L10: metadatos de la aplicación que guardó (Q13) |
| `workbook:workbook/revisionPtr@documentId` | EQ L10: metadatos de la aplicación que guardó (Q13) |
| `workbook:workbook/revisionPtr@revIDLastSave` | EQ L10: metadatos de la aplicación que guardó (Q13) |
| `workbook:workbook/revisionPtr@uidLastSave` | EQ L10: metadatos de la aplicación que guardó (Q13) |
| `workbook:workbook/sheets` | 1 nombres y orden de hojas |
| `workbook:workbook/sheets/sheet` | 1 nombres y orden de hojas |
| `workbook:workbook/sheets/sheet@id` | 1 nombres y orden de hojas |
| `workbook:workbook/sheets/sheet@name` | 1 nombres y orden de hojas |
| `workbook:workbook/sheets/sheet@sheetId` | 1 nombres y orden de hojas |
| `workbook:workbook/workbookPr` | EQ L10: workbookPr sin atributos de efecto |
| `workbook:workbook@Ignorable` | EQ L10: espacios de nombres ignorables (mc:Ignorable) |
| `styles:styleSheet` | estructura |
| `styles:styleSheet/borders` | 7 bordes |
| `styles:styleSheet/borders/border` | 7 bordes |
| `styles:styleSheet/borders/border/bottom` | 7 bordes |
| `styles:styleSheet/borders/border/bottom/color` | 7 bordes |
| `styles:styleSheet/borders/border/bottom/color@rgb` | 7 bordes |
| `styles:styleSheet/borders/border/bottom@style` | 7 bordes |
| `styles:styleSheet/borders/border/diagonal` | 7 bordes |
| `styles:styleSheet/borders/border/left` | 7 bordes |
| `styles:styleSheet/borders/border/left/color` | 7 bordes |
| `styles:styleSheet/borders/border/left/color@rgb` | 7 bordes |
| `styles:styleSheet/borders/border/left@style` | 7 bordes |
| `styles:styleSheet/borders/border/right` | 7 bordes |
| `styles:styleSheet/borders/border/right/color` | 7 bordes |
| `styles:styleSheet/borders/border/right/color@rgb` | 7 bordes |
| `styles:styleSheet/borders/border/right@style` | 7 bordes |
| `styles:styleSheet/borders/border/top` | 7 bordes |
| `styles:styleSheet/borders/border/top/color` | 7 bordes |
| `styles:styleSheet/borders/border/top/color@rgb` | 7 bordes |
| `styles:styleSheet/borders/border/top@style` | 7 bordes |
| `styles:styleSheet/borders@count` | 7 bordes |
| `styles:styleSheet/cellStyleXfs` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellStyleXfs/xf` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellStyleXfs/xf@borderId` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellStyleXfs/xf@fillId` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellStyleXfs/xf@fontId` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellStyleXfs/xf@numFmtId` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellStyleXfs@count` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellStyles` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellStyles/cellStyle` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellStyles/cellStyle@builtinId` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellStyles/cellStyle@name` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellStyles/cellStyle@xfId` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellStyles@count` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellXfs` | 5-9 estilo de celda (resuelto) |
| `styles:styleSheet/cellXfs/xf` | 5-9 estilo de celda (resuelto) |
| `styles:styleSheet/cellXfs/xf/alignment` | 8 alineación |
| `styles:styleSheet/cellXfs/xf/alignment@horizontal` | 8 alineación |
| `styles:styleSheet/cellXfs/xf/alignment@vertical` | 8 alineación |
| `styles:styleSheet/cellXfs/xf/alignment@wrapText` | 8 alineación |
| `styles:styleSheet/cellXfs/xf@applyAlignment` | EQ L10: banderas apply*/pivotButton/quotePrefix por defecto; el estilo se compara resuelto (Q13) |
| `styles:styleSheet/cellXfs/xf@applyBorder` | EQ L10: banderas apply*/pivotButton/quotePrefix por defecto; el estilo se compara resuelto (Q13) |
| `styles:styleSheet/cellXfs/xf@applyFill` | EQ L10: banderas apply*/pivotButton/quotePrefix por defecto; el estilo se compara resuelto (Q13) |
| `styles:styleSheet/cellXfs/xf@applyFont` | EQ L10: banderas apply*/pivotButton/quotePrefix por defecto; el estilo se compara resuelto (Q13) |
| `styles:styleSheet/cellXfs/xf@applyNumberFormat` | EQ L10: banderas apply*/pivotButton/quotePrefix por defecto; el estilo se compara resuelto (Q13) |
| `styles:styleSheet/cellXfs/xf@borderId` | 5-9 estilo de celda (resuelto) |
| `styles:styleSheet/cellXfs/xf@fillId` | 5-9 estilo de celda (resuelto) |
| `styles:styleSheet/cellXfs/xf@fontId` | 5-9 estilo de celda (resuelto) |
| `styles:styleSheet/cellXfs/xf@numFmtId` | 5-9 estilo de celda (resuelto) |
| `styles:styleSheet/cellXfs/xf@xfId` | EQ L10: banderas apply*/pivotButton/quotePrefix por defecto; el estilo se compara resuelto (Q13) |
| `styles:styleSheet/cellXfs@count` | 5-9 estilo de celda (resuelto) |
| `styles:styleSheet/dxfs` | 23a formato condicional (dxf) |
| `styles:styleSheet/dxfs@count` | 23a formato condicional (dxf) |
| `styles:styleSheet/extLst` | EQ L10: estilos de segmentación/escala de tiempo por defecto (Q13) |
| `styles:styleSheet/extLst/ext` | EQ L10: estilos de segmentación/escala de tiempo por defecto (Q13) |
| `styles:styleSheet/extLst/ext/slicerStyles` | EQ L10: estilos de segmentación/escala de tiempo por defecto (Q13) |
| `styles:styleSheet/extLst/ext/slicerStyles@defaultSlicerStyle` | EQ L10: estilos de segmentación/escala de tiempo por defecto (Q13) |
| `styles:styleSheet/extLst/ext/timelineStyles` | EQ L10: estilos de segmentación/escala de tiempo por defecto (Q13) |
| `styles:styleSheet/extLst/ext/timelineStyles@defaultTimelineStyle` | EQ L10: estilos de segmentación/escala de tiempo por defecto (Q13) |
| `styles:styleSheet/extLst/ext@uri` | EQ L10: estilos de segmentación/escala de tiempo por defecto (Q13) |
| `styles:styleSheet/fills` | 6 rellenos |
| `styles:styleSheet/fills/fill` | 6 rellenos |
| `styles:styleSheet/fills/fill/patternFill` | 6 rellenos |
| `styles:styleSheet/fills/fill/patternFill/bgColor` | 6 rellenos |
| `styles:styleSheet/fills/fill/patternFill/bgColor@rgb` | 6 rellenos |
| `styles:styleSheet/fills/fill/patternFill/fgColor` | 6 rellenos |
| `styles:styleSheet/fills/fill/patternFill/fgColor@rgb` | 6 rellenos |
| `styles:styleSheet/fills/fill/patternFill@patternType` | 6 rellenos |
| `styles:styleSheet/fills@count` | 6 rellenos |
| `styles:styleSheet/fonts` | 5 fuentes |
| `styles:styleSheet/fonts/font` | 5 fuentes |
| `styles:styleSheet/fonts/font/b` | 5 fuentes |
| `styles:styleSheet/fonts/font/color` | 5 fuentes |
| `styles:styleSheet/fonts/font/color@rgb` | 5 fuentes |
| `styles:styleSheet/fonts/font/color@theme` | 5 fuentes |
| `styles:styleSheet/fonts/font/family` | 5 fuentes |
| `styles:styleSheet/fonts/font/family@val` | 5 fuentes |
| `styles:styleSheet/fonts/font/name` | 5 fuentes |
| `styles:styleSheet/fonts/font/name@val` | 5 fuentes |
| `styles:styleSheet/fonts/font/scheme` | 5 fuentes |
| `styles:styleSheet/fonts/font/scheme@val` | 5 fuentes |
| `styles:styleSheet/fonts/font/sz` | 5 fuentes |
| `styles:styleSheet/fonts/font/sz@val` | 5 fuentes |
| `styles:styleSheet/fonts@count` | 5 fuentes |
| `styles:styleSheet/fonts@knownFonts` | EQ L10: x14ac:knownFonts (Q13) |
| `styles:styleSheet/numFmts` | 9 formatos numéricos |
| `styles:styleSheet/numFmts/numFmt` | 9 formatos numéricos |
| `styles:styleSheet/numFmts/numFmt@formatCode` | 9 formatos numéricos |
| `styles:styleSheet/numFmts/numFmt@numFmtId` | 9 formatos numéricos |
| `styles:styleSheet/numFmts@count` | 9 formatos numéricos |
| `styles:styleSheet/tableStyles` | 24 tablas (Q8) |
| `styles:styleSheet/tableStyles@count` | 24 tablas (Q8) |
| `styles:styleSheet/tableStyles@defaultPivotStyle` | 24 tablas (Q8) |
| `styles:styleSheet/tableStyles@defaultTableStyle` | 24 tablas (Q8) |
| `styles:styleSheet@Ignorable` | EQ L10: espacios de nombres ignorables (mc:Ignorable) |
| `sheet:worksheet` | estructura |
| `sheet:worksheet/autoFilter` | 24 autofiltro |
| `sheet:worksheet/autoFilter@ref` | 24 autofiltro |
| `sheet:worksheet/autoFilter@uid` | EQ Q13: uid |
| `sheet:worksheet/cols` | 10 anchos |
| `sheet:worksheet/cols/col` | 10 anchos |
| `sheet:worksheet/cols/col@customWidth` | 10 anchos |
| `sheet:worksheet/cols/col@max` | 10 anchos |
| `sheet:worksheet/cols/col@min` | 10 anchos |
| `sheet:worksheet/cols/col@width` | 10 anchos |
| `sheet:worksheet/dimension` | EQ L10: dimension (la calcula el escritor) |
| `sheet:worksheet/dimension@ref` | EQ L10: dimension (la calcula el escritor) |
| `sheet:worksheet/drawing` | 13 imágenes |
| `sheet:worksheet/drawing@id` | 13 imágenes |
| `sheet:worksheet/headerFooter` | 17 encabezado y pie |
| `sheet:worksheet/headerFooter/oddFooter` | 17 encabezado y pie |
| `sheet:worksheet/mergeCells` | 12 combinadas |
| `sheet:worksheet/mergeCells/mergeCell` | 12 combinadas |
| `sheet:worksheet/mergeCells/mergeCell@ref` | 12 combinadas |
| `sheet:worksheet/mergeCells@count` | 12 combinadas |
| `sheet:worksheet/pageMargins` | 16 márgenes |
| `sheet:worksheet/pageMargins@bottom` | 16 márgenes |
| `sheet:worksheet/pageMargins@footer` | 16 márgenes |
| `sheet:worksheet/pageMargins@header` | 16 márgenes |
| `sheet:worksheet/pageMargins@left` | 16 márgenes |
| `sheet:worksheet/pageMargins@right` | 16 márgenes |
| `sheet:worksheet/pageMargins@top` | 16 márgenes |
| `sheet:worksheet/pageSetup` | 15 orientación, papel y ajuste |
| `sheet:worksheet/pageSetup@fitToHeight` | 15 orientación, papel y ajuste |
| `sheet:worksheet/pageSetup@orientation` | 15 orientación, papel y ajuste |
| `sheet:worksheet/sheetData` | estructura |
| `sheet:worksheet/sheetData/row` | 11 alturas |
| `sheet:worksheet/sheetData/row/c` | 25 textos y valores |
| `sheet:worksheet/sheetData/row/c/v` | 25 textos y valores |
| `sheet:worksheet/sheetData/row/c@r` | detalle por celda (matriz.md) |
| `sheet:worksheet/sheetData/row/c@s` | 5-9 estilo de celda (resuelto) |
| `sheet:worksheet/sheetData/row/c@t` | 25 textos (tipo); inlineStr vs. sharedStrings = EQ L10 |
| `sheet:worksheet/sheetData/row@customHeight` | 11 alturas |
| `sheet:worksheet/sheetData/row@dyDescent` | EQ L10: pistas de renderizado de fila (Q13) |
| `sheet:worksheet/sheetData/row@ht` | 11 alturas |
| `sheet:worksheet/sheetData/row@r` | 11 alturas |
| `sheet:worksheet/sheetData/row@spans` | EQ L10: pistas de renderizado de fila (Q13) |
| `sheet:worksheet/sheetFormatPr` | estructura |
| `sheet:worksheet/sheetFormatPr@baseColWidth` | EQ Q13: baseColWidth (10 alturas/anchos por defecto efectivos) |
| `sheet:worksheet/sheetFormatPr@defaultColWidth` | EQ Q13: baseColWidth (10 alturas/anchos por defecto efectivos) |
| `sheet:worksheet/sheetFormatPr@defaultRowHeight` | 11 alturas (por defecto) |
| `sheet:worksheet/sheetFormatPr@dyDescent` | EQ Q13: dyDescent |
| `sheet:worksheet/sheetPr` | estructura |
| `sheet:worksheet/sheetPr/pageSetUpPr` | 15 ajuste a página |
| `sheet:worksheet/sheetPr/pageSetUpPr@fitToPage` | 15 ajuste a página |
| `sheet:worksheet/sheetPr/tabColor` | 2 color de pestaña |
| `sheet:worksheet/sheetPr/tabColor@rgb` | 2 color de pestaña |
| `sheet:worksheet/sheetViews` | estructura |
| `sheet:worksheet/sheetViews/sheetView` | estructura |
| `sheet:worksheet/sheetViews/sheetView/pane` | 14 congelados |
| `sheet:worksheet/sheetViews/sheetView/pane@activePane` | 14 congelados |
| `sheet:worksheet/sheetViews/sheetView/pane@state` | 14 congelados |
| `sheet:worksheet/sheetViews/sheetView/pane@topLeftCell` | 14 congelados |
| `sheet:worksheet/sheetViews/sheetView/pane@ySplit` | 14 congelados |
| `sheet:worksheet/sheetViews/sheetView/selection` | 3 selección (Q11) |
| `sheet:worksheet/sheetViews/sheetView/selection@activeCell` | 3 selección (Q11) |
| `sheet:worksheet/sheetViews/sheetView/selection@pane` | 3 selección (Q11) |
| `sheet:worksheet/sheetViews/sheetView/selection@sqref` | 3 selección (Q11) |
| `sheet:worksheet/sheetViews/sheetView@showGridLines` | 20 cuadrícula |
| `sheet:worksheet/sheetViews/sheetView@tabSelected` | 3 hoja activa y desplazamiento (Q11) |
| `sheet:worksheet/sheetViews/sheetView@workbookViewId` | estructura |
| `sheet:worksheet@Ignorable` | EQ L10: espacios de nombres ignorables (mc:Ignorable) |
| `sheet:worksheet@uid` | EQ Q13: uid |
| `drawing:wsDr` | estructura |
| `drawing:wsDr/oneCellAnchor` | 13 imágenes (ancla, Q13/L1) |
| `drawing:wsDr/oneCellAnchor/clientData` | 13 imágenes (por defecto) |
| `drawing:wsDr/oneCellAnchor/ext` | 13 imágenes (tamaño) |
| `drawing:wsDr/oneCellAnchor/ext@cx` | 13 imágenes (tamaño) |
| `drawing:wsDr/oneCellAnchor/ext@cy` | 13 imágenes (tamaño) |
| `drawing:wsDr/oneCellAnchor/from` | 13 imágenes (posición) |
| `drawing:wsDr/oneCellAnchor/from/col` | 13 imágenes (posición) |
| `drawing:wsDr/oneCellAnchor/from/colOff` | 13 imágenes (posición) |
| `drawing:wsDr/oneCellAnchor/from/row` | 13 imágenes (posición) |
| `drawing:wsDr/oneCellAnchor/from/rowOff` | 13 imágenes (posición) |
| `drawing:wsDr/oneCellAnchor/pic` | 13 imágenes |
| `drawing:wsDr/oneCellAnchor/pic/blipFill` | 13 imágenes (medio, estirado) |
| `drawing:wsDr/oneCellAnchor/pic/blipFill/blip` | 13 imágenes (medio, estirado) |
| `drawing:wsDr/oneCellAnchor/pic/blipFill/blip@cstate` | EQ L10: cstate (estado de compresión, sin efecto) |
| `drawing:wsDr/oneCellAnchor/pic/blipFill/blip@embed` | 13 imágenes (medio, estirado) |
| `drawing:wsDr/oneCellAnchor/pic/blipFill/stretch` | 13 imágenes (medio, estirado) |
| `drawing:wsDr/oneCellAnchor/pic/blipFill/stretch/fillRect` | 13 imágenes (medio, estirado) |
| `drawing:wsDr/oneCellAnchor/pic/nvPicPr` | 13 imágenes; L8 bloqueos (noChangeAspect = EQ aceptado) |
| `drawing:wsDr/oneCellAnchor/pic/nvPicPr/cNvPicPr` | 13 imágenes; L8 bloqueos (noChangeAspect = EQ aceptado) |
| `drawing:wsDr/oneCellAnchor/pic/nvPicPr/cNvPr` | 13 imágenes; L8 bloqueos (noChangeAspect = EQ aceptado) |
| `drawing:wsDr/oneCellAnchor/pic/nvPicPr/cNvPr/extLst` | EQ Q13: creationId (uid) |
| `drawing:wsDr/oneCellAnchor/pic/nvPicPr/cNvPr/extLst/ext` | EQ Q13: creationId (uid) |
| `drawing:wsDr/oneCellAnchor/pic/nvPicPr/cNvPr/extLst/ext/creationId` | EQ Q13: creationId (uid) |
| `drawing:wsDr/oneCellAnchor/pic/nvPicPr/cNvPr/extLst/ext/creationId@id` | EQ Q13: creationId (uid) |
| `drawing:wsDr/oneCellAnchor/pic/nvPicPr/cNvPr/extLst/ext@uri` | EQ Q13: creationId (uid) |
| `drawing:wsDr/oneCellAnchor/pic/nvPicPr/cNvPr@descr` | 13 imágenes; L8 texto alternativo; nombre `Picture N` = EQ aceptado (humano) |
| `drawing:wsDr/oneCellAnchor/pic/nvPicPr/cNvPr@id` | 13 imágenes; L8 texto alternativo; nombre `Picture N` = EQ aceptado (humano) |
| `drawing:wsDr/oneCellAnchor/pic/nvPicPr/cNvPr@name` | 13 imágenes; L8 texto alternativo; nombre `Picture N` = EQ aceptado (humano) |
| `drawing:wsDr/oneCellAnchor/pic/spPr` | 13 imágenes (posición absoluta, geometría) |
| `drawing:wsDr/oneCellAnchor/pic/spPr/prstGeom` | 13 imágenes (posición absoluta, geometría) |
| `drawing:wsDr/oneCellAnchor/pic/spPr/prstGeom/avLst` | 13 imágenes (posición absoluta, geometría) |
| `drawing:wsDr/oneCellAnchor/pic/spPr/prstGeom@prst` | 13 imágenes (posición absoluta, geometría) |
| `drawing:wsDr/oneCellAnchor/pic/spPr/xfrm` | 13 imágenes (posición absoluta, geometría) |
| `drawing:wsDr/oneCellAnchor/pic/spPr/xfrm/ext` | 13 imágenes (posición absoluta, geometría) |
| `drawing:wsDr/oneCellAnchor/pic/spPr/xfrm/ext@cx` | 13 imágenes (posición absoluta, geometría) |
| `drawing:wsDr/oneCellAnchor/pic/spPr/xfrm/ext@cy` | 13 imágenes (posición absoluta, geometría) |
| `drawing:wsDr/oneCellAnchor/pic/spPr/xfrm/off` | 13 imágenes (posición absoluta, geometría) |
| `drawing:wsDr/oneCellAnchor/pic/spPr/xfrm/off@x` | 13 imágenes (posición absoluta, geometría) |
| `drawing:wsDr/oneCellAnchor/pic/spPr/xfrm/off@y` | 13 imágenes (posición absoluta, geometría) |

## Plantilla `informe` (`Informe_boseto_limpio.xlsx`)

- Hojas (orden): Todos los activos, Por ubicación, No encontrados, {categoria}, Por categoría, Resumen
- Hoja activa: 2 (Q11: no se reproduce; primera hoja, A1)
- Nombres definidos: `_xlnm.Print_Titles`[0] = `'Todos los activos'!$9:$9`; `_xlnm.Print_Area`[0] = `'Todos los activos'!$A$1:$J$10`; `_xlnm.Print_Area`[1] = `'Por ubicación'!$A$1:$H$9`; `_xlnm.Print_Titles`[2] = `'No encontrados'!$9:$9`; `_xlnm.Print_Area`[2] = `'No encontrados'!$A$1:$F$9`; `_xlnm.Print_Titles`[3] = `'{categoria}'!$9:$9`; `_xlnm.Print_Area`[3] = `'{categoria}'!$A$1:$I$10`; `_xlnm.Print_Area`[4] = `'Por categoría'!$A$1:$H$9`; `_xlnm.Print_Area`[5] = `'Resumen'!$A$1:$J$13`
- `calcPr`: `{'calcId': '0', 'fullCalcOnLoad': '1'}` (EQ Q13)
- Tema: Office Theme; mayor Cambria, menor Calibri
- Fuente por defecto: `{'nombre': 'Calibri', 'familia': 2, 'color': {'theme': 1}, 'tamano': 11, 'esquema': 'minor', 'negrita': False, 'cursiva': False, 'tachado': False}`
- dxfs: `[{'fuente': {'cursiva': True, 'color': {'rgb': 'FF92400E'}, 'negrita': False, 'tachado': False}, 'relleno': {'patron': 'solid', 'color': {'rgb': 'FFFDE68A'}}}, {'fuente': {'cursiva': True, 'color': {'rgb': 'FF92400E'}, 'negrita': False, 'tachado': False}, 'relleno': {'patron': 'solid', 'color': {'rgb': 'FFFDE68A'}}}, {'fuente': {'cursiva': True, 'color': {'rgb': 'FF92400E'}, 'negrita': False, 'tachado': False}, 'relleno': {'patron': 'solid', 'color': {'rgb': 'FFFDE68A'}}}]`
- Propiedades: `{'core': {'creator': 'openpyxl', 'created': '{created}', 'modified': '{modified}', 'lastModifiedBy': '{lastModifiedBy}'}, 'app': {'Application': 'Microsoft Excel Compatible / Openpyxl 3.1.5', 'AppVersion': '3.1'}}`

### Hoja `Todos los activos`

- Pestaña `FF1D4ED8`; cuadrícula en pantalla oculta; zoom 100; congelado `{'x_split': None, 'y_split': 9, 'celda_superior_izquierda': 'A10', 'panel_activo': 'bottomLeft', 'estado': 'frozen'}`
- Selección `[{'panel': 'bottomLeft', 'celda_activa': 'C18', 'rango': 'C18'}]`, tabSelected False, topLeftCell `None` (Q11: no se reproduce)
- Formato de hoja `{'alto_fila_defecto': 15, 'ancho_col_defecto': 9.140625, 'ancho_base': 10, 'filas_ocultas_defecto': False, 'alto_propio_defecto': False}`
- Combinadas: ['A7:J7', 'C5:D5', 'E5:F5', 'G5:J5']
- Autofiltro `None`; tablas `[]`; validaciones ninguna; hipervínculos ninguno; protección None
- Impresión `{'area': "'Todos los activos'!$A$1:$J$10", 'titulos': "'Todos los activos'!$9:$9", 'filtro': None}`
- Página `{'margenes': {'left': 0.4, 'right': 0.4, 'top': 0.6, 'bottom': 0.6, 'header': 0.3, 'footer': 0.3}, 'orientacion': 'landscape', 'papel': None, 'escala': None, 'ajustar_a_pagina': True, 'ajuste_ancho': 1, 'ajuste_alto': 1, 'primera_pagina': None, 'orden': None, 'blanco_y_negro': False, 'cuadricula_impresa': False, 'encabezados_impresos': False, 'centrado_horizontal': False, 'centrado_vertical': False, 'encabezado_pie': {'oddFooter': '&L&8 Generado con AssetControl&R&8 Página &P de &N'}, 'encabezado_pie_distinto_primera': False, 'encabezado_pie_pares_impares': False, 'saltos_fila': 0, 'saltos_columna': 0}`

| Columnas | Ancho guardado | Oculta | Estilo de columna |
|---|---|---|---|
| A | 14 | False | Calibri 11 tema 1; alin general/bottom |
| B | 26 | False | Calibri 11 tema 1; alin general/bottom |
| C–D | 18 | False | Calibri 11 tema 1; alin general/bottom |
| E–F | 22 | False | Calibri 11 tema 1; alin general/bottom |
| G | 20 | False | Calibri 11 tema 1; alin general/bottom |
| H–I | 16 | False | Calibri 11 tema 1; alin general/bottom |
| J | 18 | False | Calibri 11 tema 1; alin general/bottom |

| Fila | Alto (pt) | Propio | Estilo de fila |
|---|---|---|---|
| 1 | 6 | True | - |
| 2 | 44.1 | True | - |
| 3 | 18 | True | - |
| 4 | 16 | True | - |
| 5 | 30 | True | - |
| 6 | 26.1 | True | - |
| 7 | 26.1 | True | - |
| 8 | 21.95 | True | - |
| 9 | 27.95 | True | - |
| 10 | 21.95 | True | - |

| Celda | Valor | Estilo resuelto | Fila de matriz / decisión |
|---|---|---|---|
| A1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| B1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| C1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| D1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| E1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| F1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| G1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| H1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| I1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| J1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| C2 | Informe de activos | Arial 19 N FF111827; alin general/center | 5–9, 25 |
| C3 | Informe · {empresa.nombre} · corte {fecha} | Arial 10 FF4B5563; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| D3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| E3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| F3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| G3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| H3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| I3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| J3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| C4 | Empresa | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| D4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| E4 | Contacto | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| F4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| G4 | Dirección | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| H4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| I4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| J4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| A5 |  | Calibri 11 tema 1; borde B:medium FF1D4ED8; alin general/bottom | 5–9, 25 |
| B5 |  | Calibri 11 tema 1; borde B:medium FF1D4ED8; alin general/bottom | 5–9, 25 |
| C5 | {empresa.nombre}
NIT {empresa.nit} | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| D5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| E5 | {empresa.correo}
Tel. {empresa.telefono} | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| F5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| G5 | {empresa.direccion} | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| H5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| I5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| J5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| A6 | Todos los activos del cierre | Arial 12 N FF111827; borde B:thin FF111827; alin left/center | 5–9, 25 |
| B6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin left/center | 5–9, 25 |
| C6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| D6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| E6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| F6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| G6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| H6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| I6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| J6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| A7 | {n} activo · encontrados {n} ({pct}) por {cop} · no encontrados {n} por {cop} · tabla «Activos», lista para filtrar o hacer una tabla dinámica. En cursiva y fondo ámbar: se encontró en otra ubicación. | Arial 9 FF6B7280; alin general/center ajuste | 5–9, 25 |
| A8 | Total | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| B8 | Todos los activos | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| C8 |  | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin left/center | 5–9, 25 |
| D8 |  | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin left/center | 5–9, 25 |
| E8 |  | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin left/center | 5–9, 25 |
| F8 |  | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin left/center | 5–9, 25 |
| G8 |  | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin left/center | 5–9, 25 |
| H8 |  | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin left/center | 5–9, 25 |
| I8 | {n} activo | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin left/center | 5–9, 25 |
| J8 | {numero} | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin right/center; formato `"$"\ #,##0.00` | 5–9, 25 |
| A9 | Código | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| B9 | Activo | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| C9 | Categoría | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| D9 | Marca | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| E9 | Serial | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| F9 | Ubicación esperada | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| G9 | Encontrado en | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| H9 | Estado físico | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| I9 | Resultado | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| J9 | Precio (COP) | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| A10 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| B10 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| C10 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| D10 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| E10 |  | Calibri 11 tema 1; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/bottom | 5–9, 25 |
| F10 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| G10 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| H10 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| I10 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| J10 | {numero} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `"$"\ #,##0.00` | 5–9, 25 |

| Formato condicional | Detalle |
|---|---|
| A10:J499 | `{'rango': 'A10:J499', 'tipo': 'expression', 'prioridad': 1, 'detener': False, 'operador': None, 'formulas': ['AND($F10<>"",$G10<>"",$F10<>$G10)'], 'dxf': {'fuente': {'cursiva': True, 'color': {'rgb': 'FF92400E'}, 'negrita': False, 'tachado': False}, 'relleno': {'patron': 'solid', 'color': {'rgb': 'FFFDE68A'}}}}` |

| Imagen | Detalle |
|---|---|
| 1 | `{'ancla': 'oneCellAnchor', 'edit_as': None, 'desde': {'col': 0, 'col_off': 80010, 'fila': 1, 'fila_off': 102870}, 'hasta': None, 'ext': {'cx': 2537460, 'cy': 1108710}, 'xfrm': {'x': 80010, 'y': 179070, 'cx': 2537460, 'cy': 1108710}, 'nombre': 'Image 1', 'descr': 'Picture', 'titulo': None, 'oculta': False, 'decorativa': False, 'bloqueos': {}, 'cstate': 'print', 'estirar': True, 'geometria': 'rect', 'linea': ['prstDash'], 'medio': 'xl/media/image1.png', 'imagen': {'formato': 'png', 'phys': None, 'ancho': 600, 'alto': 240}}` |

### Hoja `Por ubicación`

- Pestaña `FF1D4ED8`; cuadrícula en pantalla oculta; zoom 100; congelado `None`
- Selección `[{'panel': None, 'celda_activa': 'A7', 'rango': 'A7:H9'}]`, tabSelected False, topLeftCell `None` (Q11: no se reproduce)
- Formato de hoja `{'alto_fila_defecto': 15, 'ancho_col_defecto': 9.140625, 'ancho_base': 10, 'filas_ocultas_defecto': False, 'alto_propio_defecto': False}`
- Combinadas: ['C5:D5', 'E5:F5', 'G5:H5']
- Autofiltro `None`; tablas `[]`; validaciones ninguna; hipervínculos ninguno; protección None
- Impresión `{'area': "'Por ubicación'!$A$1:$H$9", 'titulos': None, 'filtro': None}`
- Página `{'margenes': {'left': 0.4, 'right': 0.4, 'top': 0.6, 'bottom': 0.6, 'header': 0.3, 'footer': 0.3}, 'orientacion': 'landscape', 'papel': None, 'escala': None, 'ajustar_a_pagina': True, 'ajuste_ancho': 1, 'ajuste_alto': 1, 'primera_pagina': None, 'orden': None, 'blanco_y_negro': False, 'cuadricula_impresa': False, 'encabezados_impresos': False, 'centrado_horizontal': False, 'centrado_vertical': False, 'encabezado_pie': {'oddFooter': '&L&8 Generado con AssetControl&R&8 Página &P de &N'}, 'encabezado_pie_distinto_primera': False, 'encabezado_pie_pares_impares': False, 'saltos_fila': 0, 'saltos_columna': 0}`

| Columnas | Ancho guardado | Oculta | Estilo de columna |
|---|---|---|---|
| A | 14 | False | Calibri 11 tema 1; alin general/bottom |
| B | 26 | False | Calibri 11 tema 1; alin general/bottom |
| C–D | 18 | False | Calibri 11 tema 1; alin general/bottom |
| E–F | 22 | False | Calibri 11 tema 1; alin general/bottom |
| G | 20 | False | Calibri 11 tema 1; alin general/bottom |
| H–I | 16 | False | Calibri 11 tema 1; alin general/bottom |
| J | 18 | False | Calibri 11 tema 1; alin general/bottom |

| Fila | Alto (pt) | Propio | Estilo de fila |
|---|---|---|---|
| 1 | 6 | True | - |
| 2 | 44.1 | True | - |
| 3 | 18 | True | - |
| 4 | 16 | True | - |
| 5 | 30 | True | - |
| 6 | 26.1 | True | - |
| 7 | 27.95 | True | - |
| 8 | 21.95 | True | - |
| 9 | 21.95 | True | - |

| Celda | Valor | Estilo resuelto | Fila de matriz / decisión |
|---|---|---|---|
| A1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| B1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| C1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| D1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| E1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| F1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| G1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| H1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| I1 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| J1 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| C2 | Informe de activos | Arial 19 N FF111827; alin general/center | 5–9, 25 |
| C3 | Informe · {empresa.nombre} · corte {fecha} | Arial 10 FF4B5563; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| D3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| E3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| F3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| G3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| H3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| I3 |  | Calibri 11 tema 1; alin general/center | 5–9, 25 |
| J3 |  | Calibri 11 tema 1; alin general/center | 5–9, 25 |
| C4 | Empresa | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| D4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| E4 | Contacto | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| F4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| G4 | Dirección | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| H4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| I4 |  | Calibri 11 tema 1; alin general/center | 5–9, 25 |
| J4 |  | Calibri 11 tema 1; alin general/center | 5–9, 25 |
| A5 |  | Calibri 11 tema 1; borde B:medium FF1D4ED8; alin general/bottom | 5–9, 25 |
| B5 |  | Calibri 11 tema 1; borde B:medium FF1D4ED8; alin general/bottom | 5–9, 25 |
| C5 | {empresa.nombre}
NIT {empresa.nit} | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| D5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| E5 | {empresa.correo}
Tel. {empresa.telefono} | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| F5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| G5 | {empresa.direccion} | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| H5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| I5 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| J5 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| A6 | Por ubicación | Arial 12 N FF111827; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| B6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| C6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| D6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| E6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| F6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| G6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| H6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| I6 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| J6 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| A7 | Ubicación (al cierre) | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| B7 | Valor encontrado | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| C7 | Unid. encontradas | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| D7 | Valor no encontrado | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| E7 | Unid. no encontradas | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| F7 | Valor registrado | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| G7 | Unid. registradas | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| H7 | % encontrado | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| I7 |  | Arial 9 N FF6B7280; alin left/bottom ajuste | 5–9, 25 |
| J7 |  | Arial 9 N FF6B7280; alin left/bottom ajuste | 5–9, 25 |
| A8 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| B8 | {numero} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `"$"\ #,##0.00` | 5–9, 25 |
| C8 | {numero} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `#,##0` | 5–9, 25 |
| D8 | {numero} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `"$"\ #,##0.00` | 5–9, 25 |
| E8 | {numero} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `#,##0` | 5–9, 25 |
| F8 | {numero} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `"$"\ #,##0.00` | 5–9, 25 |
| G8 | {numero} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `#,##0` | 5–9, 25 |
| H8 | {numero} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `0.0\ %` | 5–9, 25 |
| A9 | Total | Arial 10 N FF111827; relleno solid FFDBEAFE; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| B9 | {numero} | Arial 10 N FF111827; relleno solid FFDBEAFE; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `"$"\ #,##0.00` | 5–9, 25 |
| C9 | {numero} | Arial 10 N FF111827; relleno solid FFDBEAFE; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `#,##0` | 5–9, 25 |
| D9 | {numero} | Arial 10 N FF111827; relleno solid FFDBEAFE; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `"$"\ #,##0.00` | 5–9, 25 |
| E9 | {numero} | Arial 10 N FF111827; relleno solid FFDBEAFE; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `#,##0` | 5–9, 25 |
| F9 | {numero} | Arial 10 N FF111827; relleno solid FFDBEAFE; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `"$"\ #,##0.00` | 5–9, 25 |
| G9 | {numero} | Arial 10 N FF111827; relleno solid FFDBEAFE; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `#,##0` | 5–9, 25 |
| H9 | {numero} | Arial 10 N FF111827; relleno solid FFDBEAFE; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `0.0\ %` | 5–9, 25 |
| I9 |  | Arial 10 N FF111827; alin left/center | 5–9, 25 |
| J9 |  | Arial 10 N FF111827; alin left/center | 5–9, 25 |

| Formato condicional | Detalle |
|---|---|
| F8 | `{'rango': 'F8', 'tipo': 'dataBar', 'prioridad': 1, 'detener': False, 'operador': None, 'formulas': [], 'dxf': None, 'barra': {'cfvo': [{'tipo': 'min', 'valor': None}, {'tipo': 'max', 'valor': None}], 'color': {'rgb': 'FFBFDBFE'}, 'mostrar_valor': True, 'largo_min': None, 'largo_max': None, 'ext': []}}` |
| H8 | `{'rango': 'H8', 'tipo': 'dataBar', 'prioridad': 2, 'detener': False, 'operador': None, 'formulas': [], 'dxf': None, 'barra': {'cfvo': [{'tipo': 'min', 'valor': None}, {'tipo': 'max', 'valor': None}], 'color': {'rgb': 'FFBFDBFE'}, 'mostrar_valor': True, 'largo_min': None, 'largo_max': None, 'ext': []}}` |

| Imagen | Detalle |
|---|---|
| 1 | `{'ancla': 'oneCellAnchor', 'edit_as': None, 'desde': {'col': 0, 'col_off': 171450, 'fila': 1, 'fila_off': 114300}, 'hasta': None, 'ext': {'cx': 2388870, 'cy': 1013460}, 'xfrm': {'x': 171450, 'y': 190500, 'cx': 2388870, 'cy': 1013460}, 'nombre': 'Image 1', 'descr': 'Picture', 'titulo': None, 'oculta': False, 'decorativa': False, 'bloqueos': {}, 'cstate': 'print', 'estirar': True, 'geometria': 'rect', 'linea': ['prstDash'], 'medio': 'xl/media/image2.png', 'imagen': {'formato': 'png', 'phys': None, 'ancho': 600, 'alto': 240}}` |

### Hoja `No encontrados`

- Pestaña `FF1D4ED8`; cuadrícula en pantalla oculta; zoom 100; congelado `{'x_split': None, 'y_split': 9, 'celda_superior_izquierda': 'A10', 'panel_activo': 'bottomLeft', 'estado': 'frozen'}`
- Selección `[{'panel': 'bottomLeft', 'celda_activa': 'E15', 'rango': 'E15'}]`, tabSelected True, topLeftCell `None` (Q11: no se reproduce)
- Formato de hoja `{'alto_fila_defecto': 15, 'ancho_col_defecto': 9.140625, 'ancho_base': 10, 'filas_ocultas_defecto': False, 'alto_propio_defecto': False}`
- Combinadas: ['A7:F7', 'C5:D5']
- Autofiltro `None`; tablas `[]`; validaciones ninguna; hipervínculos ninguno; protección None
- Impresión `{'area': "'No encontrados'!$A$1:$F$9", 'titulos': "'No encontrados'!$9:$9", 'filtro': None}`
- Página `{'margenes': {'left': 0.4, 'right': 0.4, 'top': 0.6, 'bottom': 0.6, 'header': 0.3, 'footer': 0.3}, 'orientacion': 'landscape', 'papel': None, 'escala': None, 'ajustar_a_pagina': True, 'ajuste_ancho': 1, 'ajuste_alto': 1, 'primera_pagina': None, 'orden': None, 'blanco_y_negro': False, 'cuadricula_impresa': False, 'encabezados_impresos': False, 'centrado_horizontal': False, 'centrado_vertical': False, 'encabezado_pie': {'oddFooter': '&L&8 Generado con AssetControl&R&8 Página &P de &N'}, 'encabezado_pie_distinto_primera': False, 'encabezado_pie_pares_impares': False, 'saltos_fila': 0, 'saltos_columna': 0}`

| Columnas | Ancho guardado | Oculta | Estilo de columna |
|---|---|---|---|
| A | 14 | False | Calibri 11 tema 1; alin general/bottom |
| B | 26 | False | Calibri 11 tema 1; alin general/bottom |
| C–D | 18 | False | Calibri 11 tema 1; alin general/bottom |
| E–F | 22 | False | Calibri 11 tema 1; alin general/bottom |
| G | 20 | True | Calibri 11 tema 1; alin general/bottom |
| H–I | 16 | True | Calibri 11 tema 1; alin general/bottom |
| J | 18 | True | Calibri 11 tema 1; alin general/bottom |
| K | 13 | True | Calibri 11 tema 1; alin general/bottom |

| Fila | Alto (pt) | Propio | Estilo de fila |
|---|---|---|---|
| 1 | 6 | True | - |
| 2 | 44.1 | True | - |
| 3 | 18 | True | - |
| 4 | 16 | True | - |
| 5 | 30 | True | - |
| 6 | 26.1 | True | - |
| 7 | 26.1 | True | - |
| 8 | 21.95 | True | - |
| 9 | 27.95 | True | - |
| 10 | 21.95 | True | - |
| 11 | 21.95 | True | - |

| Celda | Valor | Estilo resuelto | Fila de matriz / decisión |
|---|---|---|---|
| A1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| B1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| C1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| D1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| E1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| F1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| G1 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| H1 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| I1 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| J1 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| C2 | Informe de activos | Arial 19 N FF111827; alin general/center | 5–9, 25 |
| C3 | Informe · {empresa.nombre} · corte {fecha} | Arial 10 FF4B5563; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| D3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| E3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| F3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| G3 |  | Calibri 11 tema 1; alin general/center | 5–9, 25 |
| H3 |  | Calibri 11 tema 1; alin general/center | 5–9, 25 |
| I3 |  | Calibri 11 tema 1; alin general/center | 5–9, 25 |
| J3 |  | Calibri 11 tema 1; alin general/center | 5–9, 25 |
| C4 | Empresa | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| D4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| E4 | Contacto | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| F4 | Dirección | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| G4 |  | Calibri 11 tema 1; alin general/center | 5–9, 25 |
| H4 |  | Calibri 11 tema 1; alin general/center | 5–9, 25 |
| I4 |  | Calibri 11 tema 1; alin general/center | 5–9, 25 |
| J4 |  | Calibri 11 tema 1; alin general/center | 5–9, 25 |
| A5 |  | Calibri 11 tema 1; borde B:medium FF1D4ED8; alin general/bottom | 5–9, 25 |
| B5 |  | Calibri 11 tema 1; borde B:medium FF1D4ED8; alin general/bottom | 5–9, 25 |
| C5 | {empresa.nombre}
NIT {empresa.nit} | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| D5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| E5 | {empresa.correo}
Tel. {empresa.telefono} | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| F5 | {empresa.direccion} | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| G5 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| H5 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| I5 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| J5 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| A6 | No encontrados (lista congelada al cierre) | Arial 12 N FF111827; borde B:thin FF111827; alin general/center | 5–9, 25 |
| B6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| C6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| D6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| E6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| F6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| G6 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| H6 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| I6 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| J6 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| A7 | {n} activos no encontrados por {cop}. | Arial 9 FF6B7280; alin general/center ajuste | 5–9, 25 |
| A8 | Total | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| B8 | {n} activos no encontrados | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| C8 |  | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| D8 |  | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| E8 |  | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| F8 | {numero} | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `"$"\ #,##0.00` | 5–9, 25 |
| G8 |  | Arial 10 N FF111827; alin left/center | 5–9, 25 |
| H8 |  | Arial 10 N FF111827; alin left/center | 5–9, 25 |
| I8 |  | Arial 10 N FF111827; alin left/center | 5–9, 25 |
| J8 |  | Arial 10 N FF111827; alin left/center | 5–9, 25 |
| A9 | Código | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| B9 | Activo | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| C9 | Categoría | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| D9 | Ubicación esperada | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| E9 | Nota al cierre | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| F9 | Precio (COP) | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| G9 |  | Arial 9 N FF6B7280; alin left/bottom ajuste | 5–9, 25 |
| H9 |  | Arial 9 N FF6B7280; alin left/bottom ajuste | 5–9, 25 |
| I9 |  | Arial 9 N FF6B7280; alin left/bottom ajuste | 5–9, 25 |
| J9 |  | Arial 9 N FF6B7280; alin left/bottom ajuste | 5–9, 25 |

| Formato condicional | Detalle |
|---|---|

| Imagen | Detalle |
|---|---|
| 1 | `{'ancla': 'oneCellAnchor', 'edit_as': None, 'desde': {'col': 0, 'col_off': 112395, 'fila': 1, 'fila_off': 91440}, 'hasta': None, 'ext': {'cx': 2411730, 'cy': 1083944}, 'xfrm': {'x': 112395, 'y': 167640, 'cx': 2411730, 'cy': 1083944}, 'nombre': 'Image 1', 'descr': 'Picture', 'titulo': None, 'oculta': False, 'decorativa': False, 'bloqueos': {}, 'cstate': 'print', 'estirar': True, 'geometria': 'rect', 'linea': ['prstDash'], 'medio': 'xl/media/image3.png', 'imagen': {'formato': 'png', 'phys': None, 'ancho': 600, 'alto': 240}}` |

### Hoja `{categoria}`

- Pestaña `FF1D4ED8`; cuadrícula en pantalla oculta; zoom 100; congelado `{'x_split': None, 'y_split': 9, 'celda_superior_izquierda': 'A10', 'panel_activo': 'bottomLeft', 'estado': 'frozen'}`
- Selección `[{'panel': 'bottomLeft', 'celda_activa': 'E19', 'rango': 'E19'}]`, tabSelected False, topLeftCell `None` (Q11: no se reproduce)
- Formato de hoja `{'alto_fila_defecto': 15, 'ancho_col_defecto': 9.140625, 'ancho_base': 10, 'filas_ocultas_defecto': False, 'alto_propio_defecto': False}`
- Combinadas: ['A7:I7', 'C5:D5', 'E5:F5', 'G5:I5']
- Autofiltro `None`; tablas `[]`; validaciones ninguna; hipervínculos ninguno; protección None
- Impresión `{'area': "'{categoria}'!$A$1:$I$10", 'titulos': "'{categoria}'!$9:$9", 'filtro': None}`
- Página `{'margenes': {'left': 0.4, 'right': 0.4, 'top': 0.6, 'bottom': 0.6, 'header': 0.3, 'footer': 0.3}, 'orientacion': 'landscape', 'papel': None, 'escala': None, 'ajustar_a_pagina': True, 'ajuste_ancho': 1, 'ajuste_alto': 1, 'primera_pagina': None, 'orden': None, 'blanco_y_negro': False, 'cuadricula_impresa': False, 'encabezados_impresos': False, 'centrado_horizontal': False, 'centrado_vertical': False, 'encabezado_pie': {'oddFooter': '&L&8 Generado con AssetControl&R&8 Página &P de &N'}, 'encabezado_pie_distinto_primera': False, 'encabezado_pie_pares_impares': False, 'saltos_fila': 0, 'saltos_columna': 0}`

| Columnas | Ancho guardado | Oculta | Estilo de columna |
|---|---|---|---|
| A | 14 | False | Calibri 11 tema 1; alin general/bottom |
| B | 26 | False | Calibri 11 tema 1; alin general/bottom |
| C–D | 18 | False | Calibri 11 tema 1; alin general/bottom |
| E–F | 22 | False | Calibri 11 tema 1; alin general/bottom |
| G | 20 | False | Calibri 11 tema 1; alin general/bottom |
| H–I | 16 | False | Calibri 11 tema 1; alin general/bottom |
| J | 18 | False | Calibri 11 tema 1; alin general/bottom |

| Fila | Alto (pt) | Propio | Estilo de fila |
|---|---|---|---|
| 1 | 6 | True | - |
| 2 | 44.1 | True | - |
| 3 | 18 | True | - |
| 4 | 16 | True | - |
| 5 | 30 | True | - |
| 6 | 26.1 | True | Calibri 11 tema 1; alin general/center |
| 7 | 26.1 | True | - |
| 8 | 21.95 | True | - |
| 9 | 27.95 | True | - |
| 10 | 21.95 | True | - |

| Celda | Valor | Estilo resuelto | Fila de matriz / decisión |
|---|---|---|---|
| A1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| B1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| C1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| D1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| E1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| F1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| G1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| H1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| I1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| J1 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| C2 | Informe de activos | Arial 19 N FF111827; alin general/center | 5–9, 25 |
| C3 | Informe · {empresa.nombre} · corte {fecha} | Arial 10 FF4B5563; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| D3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| E3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| F3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| G3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| H3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| I3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| J3 |  | Calibri 11 tema 1; alin general/center | 5–9, 25 |
| C4 | Empresa | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| D4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| E4 | Contacto | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| F4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| G4 | Dirección | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| H4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| I4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| J4 |  | Calibri 11 tema 1; alin general/center | 5–9, 25 |
| A5 |  | Calibri 11 tema 1; borde B:medium FF1D4ED8; alin general/bottom | 5–9, 25 |
| B5 |  | Calibri 11 tema 1; borde B:medium FF1D4ED8; alin general/bottom | 5–9, 25 |
| C5 | {empresa.nombre}
NIT {empresa.nit} | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| D5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| E5 | {empresa.correo}
Tel. {empresa.telefono} | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| F5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| G5 | {empresa.direccion} | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| H5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| I5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| J5 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| A6 | Categoría: {categoria} | Arial 12 N FF111827; borde B:thin FF111827; alin general/center | 5–9, 25 |
| B6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/center | 5–9, 25 |
| C6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/center | 5–9, 25 |
| D6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/center | 5–9, 25 |
| E6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/center | 5–9, 25 |
| F6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/center | 5–9, 25 |
| G6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/center | 5–9, 25 |
| H6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/center | 5–9, 25 |
| I6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/center | 5–9, 25 |
| J6 |  | Calibri 11 tema 1; alin general/center | 5–9, 25 |
| A7 | {n} activo · encontrados {n} ({pct}) por {cop} · no encontrados {n} por {cop} · En cursiva y fondo ámbar: se encontró en otra ubicación. | Arial 9 FF6B7280; alin general/center ajuste | 5–9, 25 |
| A8 | Total | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| B8 | {texto} | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| C8 |  | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| D8 |  | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| E8 |  | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| F8 |  | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| G8 |  | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| H8 | {n} activo | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| I8 | {numero} | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `"$"\ #,##0.00` | 5–9, 25 |
| J8 |  | Arial 10 N FF111827; alin left/center | 5–9, 25 |
| A9 | Código | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| B9 | Activo | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| C9 | Marca | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| D9 | Serial | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| E9 | Ubicación esperada | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| F9 | Encontrado en | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| G9 | Estado físico | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| H9 | Resultado | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| I9 | Precio (COP) | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| A10 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| B10 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| C10 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| D10 |  | Calibri 11 tema 1; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/bottom | 5–9, 25 |
| E10 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| F10 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| G10 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| H10 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| I10 | {numero} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `"$"\ #,##0.00` | 5–9, 25 |

| Formato condicional | Detalle |
|---|---|
| A10:I499 | `{'rango': 'A10:I499', 'tipo': 'expression', 'prioridad': 1, 'detener': False, 'operador': None, 'formulas': ['AND($E10<>"",$F10<>"",$E10<>$F10)'], 'dxf': {'fuente': {'cursiva': True, 'color': {'rgb': 'FF92400E'}, 'negrita': False, 'tachado': False}, 'relleno': {'patron': 'solid', 'color': {'rgb': 'FFFDE68A'}}}}` |

| Imagen | Detalle |
|---|---|
| 1 | `{'ancla': 'oneCellAnchor', 'edit_as': None, 'desde': {'col': 0, 'col_off': 152400, 'fila': 1, 'fila_off': 62865}, 'hasta': None, 'ext': {'cx': 2396490, 'cy': 1082040}, 'xfrm': {'x': 152400, 'y': 139065, 'cx': 2396490, 'cy': 1082040}, 'nombre': 'Image 1', 'descr': 'Picture', 'titulo': None, 'oculta': False, 'decorativa': False, 'bloqueos': {}, 'cstate': 'print', 'estirar': True, 'geometria': 'rect', 'linea': ['prstDash'], 'medio': 'xl/media/image4.png', 'imagen': {'formato': 'png', 'phys': None, 'ancho': 600, 'alto': 240}}` |

### Hoja `Por categoría`

- Pestaña `FF1D4ED8`; cuadrícula en pantalla oculta; zoom 100; congelado `None`
- Selección `[{'panel': None, 'celda_activa': 'D22', 'rango': 'D22'}]`, tabSelected False, topLeftCell `None` (Q11: no se reproduce)
- Formato de hoja `{'alto_fila_defecto': 15, 'ancho_col_defecto': 9.140625, 'ancho_base': 10, 'filas_ocultas_defecto': False, 'alto_propio_defecto': False}`
- Combinadas: ['C5:D5', 'E5:F5', 'G5:H5']
- Autofiltro `None`; tablas `[]`; validaciones ninguna; hipervínculos ninguno; protección None
- Impresión `{'area': "'Por categoría'!$A$1:$H$9", 'titulos': None, 'filtro': None}`
- Página `{'margenes': {'left': 0.4, 'right': 0.4, 'top': 0.6, 'bottom': 0.6, 'header': 0.3, 'footer': 0.3}, 'orientacion': 'landscape', 'papel': None, 'escala': None, 'ajustar_a_pagina': True, 'ajuste_ancho': 1, 'ajuste_alto': 1, 'primera_pagina': None, 'orden': None, 'blanco_y_negro': False, 'cuadricula_impresa': False, 'encabezados_impresos': False, 'centrado_horizontal': False, 'centrado_vertical': False, 'encabezado_pie': {'oddFooter': '&L&8 Generado con AssetControl&R&8 Página &P de &N'}, 'encabezado_pie_distinto_primera': False, 'encabezado_pie_pares_impares': False, 'saltos_fila': 0, 'saltos_columna': 0}`

| Columnas | Ancho guardado | Oculta | Estilo de columna |
|---|---|---|---|
| A | 14 | False | Calibri 11 tema 1; alin general/bottom |
| B | 26 | False | Calibri 11 tema 1; alin general/bottom |
| C–D | 18 | False | Calibri 11 tema 1; alin general/bottom |
| E–F | 22 | False | Calibri 11 tema 1; alin general/bottom |
| G | 20 | False | Calibri 11 tema 1; alin general/bottom |
| H–I | 16 | False | Calibri 11 tema 1; alin general/bottom |
| J | 18 | False | Calibri 11 tema 1; alin general/bottom |

| Fila | Alto (pt) | Propio | Estilo de fila |
|---|---|---|---|
| 1 | 6 | True | - |
| 2 | 44.1 | True | - |
| 3 | 18 | True | - |
| 4 | 16 | True | - |
| 5 | 30 | True | - |
| 6 | 26.1 | True | - |
| 7 | 27.95 | True | - |
| 8 | 21.95 | True | - |
| 9 | 21.95 | True | - |

| Celda | Valor | Estilo resuelto | Fila de matriz / decisión |
|---|---|---|---|
| A1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| B1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| C1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| D1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| E1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| F1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| G1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| H1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| I1 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| J1 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| C2 | Informe de activos | Arial 19 N FF111827; alin general/center | 5–9, 25 |
| C3 | Informe · {empresa.nombre} · corte {fecha} | Arial 10 FF4B5563; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| D3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| E3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| F3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| G3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| H3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| I3 |  | Calibri 11 tema 1; alin general/center | 5–9, 25 |
| J3 |  | Calibri 11 tema 1; alin general/center | 5–9, 25 |
| C4 | Empresa | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| D4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| E4 | Contacto | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| F4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| G4 | Dirección | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| H4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| I4 |  | Calibri 11 tema 1; alin general/center | 5–9, 25 |
| J4 |  | Calibri 11 tema 1; alin general/center | 5–9, 25 |
| A5 |  | Calibri 11 tema 1; borde B:medium FF1D4ED8; alin general/bottom | 5–9, 25 |
| B5 |  | Calibri 11 tema 1; borde B:medium FF1D4ED8; alin general/bottom | 5–9, 25 |
| C5 | {empresa.nombre}
NIT {empresa.nit} | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| D5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| E5 | {empresa.correo}
Tel. {empresa.telefono} | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| F5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| G5 | {empresa.direccion} | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| H5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| I5 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| J5 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| A6 | Por categoría | Arial 12 N FF111827; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| B6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| C6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| D6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| E6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| F6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| G6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| H6 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | 5–9, 25 |
| I6 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| J6 |  | Calibri 11 tema 1; alin general/bottom | 5–9, 25 |
| A7 | Categoría (al cierre) | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| B7 | Valor encontrado | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| C7 | Unid. encontradas | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| D7 | Valor no encontrado | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| E7 | Unid. no encontradas | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| F7 | Valor registrado | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| G7 | Unid. registradas | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| H7 | % encontrado | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | 5–9, 25 |
| I7 |  | Arial 9 N FF6B7280; alin left/bottom ajuste | 5–9, 25 |
| J7 |  | Arial 9 N FF6B7280; alin left/bottom ajuste | 5–9, 25 |
| A8 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| B8 | {numero} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `"$"\ #,##0.00` | 5–9, 25 |
| C8 | {numero} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `#,##0` | 5–9, 25 |
| D8 | {numero} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `"$"\ #,##0.00` | 5–9, 25 |
| E8 | {numero} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `#,##0` | 5–9, 25 |
| F8 | {numero} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `"$"\ #,##0.00` | 5–9, 25 |
| G8 | {numero} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `#,##0` | 5–9, 25 |
| H8 | {numero} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `0.0\ %` | 5–9, 25 |
| A9 | Total | Arial 10 N FF111827; relleno solid FFDBEAFE; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | 5–9, 25 |
| B9 | {numero} | Arial 10 N FF111827; relleno solid FFDBEAFE; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `"$"\ #,##0.00` | 5–9, 25 |
| C9 | {numero} | Arial 10 N FF111827; relleno solid FFDBEAFE; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `#,##0` | 5–9, 25 |
| D9 | {numero} | Arial 10 N FF111827; relleno solid FFDBEAFE; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `"$"\ #,##0.00` | 5–9, 25 |
| E9 | {numero} | Arial 10 N FF111827; relleno solid FFDBEAFE; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `#,##0` | 5–9, 25 |
| F9 | {numero} | Arial 10 N FF111827; relleno solid FFDBEAFE; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `"$"\ #,##0.00` | 5–9, 25 |
| G9 | {numero} | Arial 10 N FF111827; relleno solid FFDBEAFE; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `#,##0` | 5–9, 25 |
| H9 | {numero} | Arial 10 N FF111827; relleno solid FFDBEAFE; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `0.0\ %` | 5–9, 25 |
| I9 |  | Arial 10 N FF111827; alin left/center | 5–9, 25 |
| J9 |  | Arial 10 N FF111827; alin left/center | 5–9, 25 |

| Formato condicional | Detalle |
|---|---|
| F8 | `{'rango': 'F8', 'tipo': 'dataBar', 'prioridad': 1, 'detener': False, 'operador': None, 'formulas': [], 'dxf': None, 'barra': {'cfvo': [{'tipo': 'min', 'valor': None}, {'tipo': 'max', 'valor': None}], 'color': {'rgb': 'FFBFDBFE'}, 'mostrar_valor': True, 'largo_min': None, 'largo_max': None, 'ext': []}}` |
| H8 | `{'rango': 'H8', 'tipo': 'dataBar', 'prioridad': 2, 'detener': False, 'operador': None, 'formulas': [], 'dxf': None, 'barra': {'cfvo': [{'tipo': 'min', 'valor': None}, {'tipo': 'max', 'valor': None}], 'color': {'rgb': 'FFBFDBFE'}, 'mostrar_valor': True, 'largo_min': None, 'largo_max': None, 'ext': []}}` |

| Imagen | Detalle |
|---|---|
| 1 | `{'ancla': 'oneCellAnchor', 'edit_as': None, 'desde': {'col': 0, 'col_off': 129540, 'fila': 1, 'fila_off': 57150}, 'hasta': None, 'ext': {'cx': 2343150, 'cy': 1082040}, 'xfrm': {'x': 129540, 'y': 133350, 'cx': 2343150, 'cy': 1082040}, 'nombre': 'Image 1', 'descr': 'Picture', 'titulo': None, 'oculta': False, 'decorativa': False, 'bloqueos': {}, 'cstate': 'print', 'estirar': True, 'geometria': 'rect', 'linea': ['prstDash'], 'medio': 'xl/media/image5.png', 'imagen': {'formato': 'png', 'phys': None, 'ancho': 600, 'alto': 240}}` |

### Hoja `Resumen`

- Pestaña `FF1D4ED8`; cuadrícula en pantalla oculta; zoom 100; congelado `None`
- Selección `[{'panel': None, 'celda_activa': 'B17', 'rango': 'B17'}]`, tabSelected False, topLeftCell `A7` (Q11: no se reproduce)
- Formato de hoja `{'alto_fila_defecto': 15, 'ancho_col_defecto': 9.140625, 'ancho_base': 10, 'filas_ocultas_defecto': False, 'alto_propio_defecto': False}`
- Combinadas: ['A10:J10', 'C2:D2', 'C5:D5', 'E5:F5', 'G5:J5'] (A10:J10 es de la lista omitida por Q7)
- Autofiltro `None`; tablas `[]`; validaciones ninguna; hipervínculos ninguno; protección None
- Impresión `{'area': "'Resumen'!$A$1:$J$13", 'titulos': None, 'filtro': None}`
- Página `{'margenes': {'left': 0.4, 'right': 0.4, 'top': 0.6, 'bottom': 0.6, 'header': 0.3, 'footer': 0.3}, 'orientacion': 'landscape', 'papel': None, 'escala': None, 'ajustar_a_pagina': True, 'ajuste_ancho': 1, 'ajuste_alto': 1, 'primera_pagina': None, 'orden': None, 'blanco_y_negro': False, 'cuadricula_impresa': False, 'encabezados_impresos': False, 'centrado_horizontal': False, 'centrado_vertical': False, 'encabezado_pie': {'oddFooter': '&L&8 Generado con AssetControl&R&8 Página &P de &N'}, 'encabezado_pie_distinto_primera': False, 'encabezado_pie_pares_impares': False, 'saltos_fila': 0, 'saltos_columna': 0}`

| Columnas | Ancho guardado | Oculta | Estilo de columna |
|---|---|---|---|
| A | 24 | False | Calibri 11 tema 1; alin general/bottom |
| B | 26 | False | Calibri 11 tema 1; alin general/bottom |
| C–D | 18 | False | Calibri 11 tema 1; alin general/bottom |
| E–F | 22 | False | Calibri 11 tema 1; alin general/bottom |
| G | 20 | False | Calibri 11 tema 1; alin general/bottom |
| H–I | 16 | False | Calibri 11 tema 1; alin general/bottom |
| J | 18 | False | Calibri 11 tema 1; alin general/bottom |

| Fila | Alto (pt) | Propio | Estilo de fila |
|---|---|---|---|
| 1 | 6 | True | - |
| 2 | 44.1 | True | - |
| 3 | 18 | True | - |
| 4 | 16 | True | - |
| 5 | 30 | True | - |
| 6 | 15.95 | True | - |
| 7 | 30 | True | - |
| 8 | 15.95 | True | - |
| 9 | 26.1 | True | - |
| 10 | 26.1 | True | - |
| 11 | 21.95 | True | - |
| 12 | 27.95 | True | - |
| 13 | 21.95 | True | - |

| Celda | Valor | Estilo resuelto | Fila de matriz / decisión |
|---|---|---|---|
| A1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| B1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| C1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| D1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| E1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| F1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| G1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| H1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| I1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| J1 |  | Calibri 11 tema 1; relleno solid FF1D4ED8; alin general/bottom | 5–9, 25 |
| C2 | Informe de activos | Arial 19 N FF111827; alin center/center | 5–9, 25 |
| C3 | Informe · {empresa.nombre} · corte {fecha} | Arial 10 FF4B5563; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| D3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| E3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| F3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| G3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| H3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| I3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| J3 |  | Calibri 11 tema 1; borde B:thin FFE5E7EB; alin general/center | 5–9, 25 |
| C4 | Empresa | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| D4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| E4 | Contacto | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| F4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| G4 | Dirección | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| H4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| I4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| J4 |  | Arial 8 FF6B7280; alin general/bottom | 5–9, 25 |
| A5 |  | Calibri 11 tema 1; borde B:medium FF1D4ED8; alin general/bottom | 5–9, 25 |
| B5 |  | Calibri 11 tema 1; borde B:medium FF1D4ED8; alin general/bottom | 5–9, 25 |
| C5 | {empresa.nombre}
NIT {empresa.nit} | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| D5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| E5 | {empresa.correo}
Tel. {empresa.telefono} | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| F5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| G5 | {empresa.direccion} | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| H5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| I5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| J5 |  | Arial 9 FF111827; borde B:medium FF1D4ED8; alin general/top ajuste | 5–9, 25 |
| A6 | Encontrado | Arial 9 N FF1D4ED8; alin center/center | 5–9, 25 |
| B6 |  | Calibri 11 tema 1; alin center/bottom | 5–9, 25 |
| C6 | No encontrado | Arial 9 N FF1D4ED8; alin center/center | 5–9, 25 |
| D6 |  | Calibri 11 tema 1; alin center/bottom | 5–9, 25 |
| E6 | Total registrado | Arial 9 N FF1D4ED8; alin center/center | 5–9, 25 |
| F6 |  | Calibri 11 tema 1; alin center/bottom | 5–9, 25 |
| G6 | % encontrado | Arial 9 FF6B7280; alin center/center | 5–9, 25 |
| H6 |  | Calibri 11 tema 1; alin center/bottom | 5–9, 25 |
| I6 |  | Calibri 11 tema 1; alin center/bottom | 5–9, 25 |
| J6 |  | Calibri 11 tema 1; alin center/bottom | 5–9, 25 |
| A7 | {numero} | Arial 18 N FF111827; alin center/center; formato `"$"\ #,##0.00` | 5–9, 25 |
| B7 |  | Calibri 11 tema 1; alin center/bottom | 5–9, 25 |
| C7 | {numero} | Arial 18 N FF111827; alin center/center; formato `"$"\ #,##0.00` | 5–9, 25 |
| D7 |  | Calibri 11 tema 1; alin center/bottom | 5–9, 25 |
| E7 | {numero} | Arial 18 N FF111827; alin center/center; formato `"$"\ #,##0.00` | 5–9, 25 |
| F7 |  | Calibri 11 tema 1; alin center/bottom | 5–9, 25 |
| G7 | {numero} | Arial 18 N FF111827; alin center/center; formato `0.0\ %` | 5–9, 25 |
| H7 |  | Calibri 11 tema 1; alin center/bottom | 5–9, 25 |
| I7 |  | Calibri 11 tema 1; alin center/bottom | 5–9, 25 |
| J7 |  | Calibri 11 tema 1; alin center/bottom | 5–9, 25 |
| A8 | {n} unidad | Arial 9 FF6B7280; alin center/center | 5–9, 25 |
| B8 |  | Calibri 11 tema 1; alin center/bottom | 5–9, 25 |
| C8 | {n} unidades | Arial 9 FF6B7280; alin center/center | 5–9, 25 |
| D8 |  | Calibri 11 tema 1; alin center/bottom | 5–9, 25 |
| E8 | {n} unidad | Arial 9 FF6B7280; alin center/center | 5–9, 25 |
| F8 |  | Calibri 11 tema 1; alin center/bottom | 5–9, 25 |
| G8 | de las unidades registradas | Arial 9 FF6B7280; alin center/center | 5–9, 25 |
| H8 |  | Calibri 11 tema 1; alin center/bottom | 5–9, 25 |
| I8 |  | Calibri 11 tema 1; alin center/bottom | 5–9, 25 |
| J8 |  | Calibri 11 tema 1; alin center/bottom | 5–9, 25 |
| A9 | Todos los activos | Arial 12 N FF111827; borde B:thin FF111827; alin general/bottom | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| B9 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| C9 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| D9 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| E9 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| F9 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| G9 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| H9 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| I9 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| J9 |  | Calibri 11 tema 1; borde B:thin FF111827; alin general/bottom | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| A10 | {n} activo · encontrados {n} ({pct}) por {cop} · no encontrados {n} por {cop} · tabla «Activos», lista para filtrar o hacer una tabla dinámica. En cursiva y fondo ámbar: se encontró en otra ubicación. | Arial 9 FF6B7280; alin general/center ajuste | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| A11 | Total | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| B11 | Todos los activos | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| C11 |  | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| D11 |  | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| E11 |  | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| F11 |  | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| G11 |  | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| H11 |  | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| I11 | {n} activo | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| J11 | {numero} | Arial 10 N FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `"$"\ #,##0.00` | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| A12 | Código | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| B12 | Activo | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| C12 | Categoría | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| D12 | Marca | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| E12 | Serial | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| F12 | Ubicación esperada | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| G12 | Encontrado en | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| H12 | Estado físico | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| I12 | Resultado | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| J12 | Precio (COP) | Arial 9 N FFFFFFFF; relleno solid FF1F2937; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center ajuste | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| A13 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| B13 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| C13 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| D13 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| E13 |  | Calibri 11 tema 1; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| F13 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| G13 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| H13 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| I13 | {texto} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |
| J13 | {numero} | Arial 10 FF111827; borde L:thin 009CA3AF, R:thin 009CA3AF, T:thin 009CA3AF, B:thin 009CA3AF; alin center/center; formato `"$"\ #,##0.00` | NO REPRODUCIDO (Q7: lista duplicada del Resumen) |

| Formato condicional | Detalle |
|---|---|
| A13:J13 (Q7: no se reproduce) | `{'rango': 'A13:J13', 'tipo': 'expression', 'prioridad': 1, 'detener': False, 'operador': None, 'formulas': ['AND($F13<>"",$G13<>"",$F13<>$G13)'], 'dxf': {'fuente': {'cursiva': True, 'color': {'rgb': 'FF92400E'}, 'negrita': False, 'tachado': False}, 'relleno': {'patron': 'solid', 'color': {'rgb': 'FFFDE68A'}}}}` |

| Imagen | Detalle |
|---|---|
| 1 | `{'ancla': 'oneCellAnchor', 'edit_as': None, 'desde': {'col': 0, 'col_off': 205740, 'fila': 1, 'fila_off': 68580}, 'hasta': None, 'ext': {'cx': 2606040, 'cy': 1074420}, 'xfrm': {'x': 205740, 'y': 144780, 'cx': 2606040, 'cy': 1074420}, 'nombre': 'Image 1', 'descr': 'Picture', 'titulo': None, 'oculta': False, 'decorativa': False, 'bloqueos': {}, 'cstate': 'print', 'estirar': True, 'geometria': 'rect', 'linea': ['prstDash'], 'medio': 'xl/media/image6.png', 'imagen': {'formato': 'png', 'phys': None, 'ancho': 600, 'alto': 240}}` |

### Cobertura XML `informe`

| Parte:ruta | Fila de matriz / decisión |
|---|---|
| `workbook:workbook` | estructura |
| `workbook:workbook/bookViews` | 3 visibilidad |
| `workbook:workbook/bookViews/workbookView` | 3 visibilidad |
| `workbook:workbook/bookViews/workbookView@activeTab` | 3 hoja activa (Q11) |
| `workbook:workbook/bookViews/workbookView@autoFilterDateGrouping` | 3 visibilidad (valores por defecto) |
| `workbook:workbook/bookViews/workbookView@firstSheet` | 3 visibilidad (valores por defecto) |
| `workbook:workbook/bookViews/workbookView@minimized` | 3 visibilidad (valores por defecto) |
| `workbook:workbook/bookViews/workbookView@showHorizontalScroll` | 3 visibilidad (valores por defecto) |
| `workbook:workbook/bookViews/workbookView@showSheetTabs` | 3 visibilidad (valores por defecto) |
| `workbook:workbook/bookViews/workbookView@showVerticalScroll` | 3 visibilidad (valores por defecto) |
| `workbook:workbook/bookViews/workbookView@tabRatio` | EQ L10: geometría de ventana del equipo que guardó (Q11/Q13) |
| `workbook:workbook/bookViews/workbookView@visibility` | 3 visibilidad (valores por defecto) |
| `workbook:workbook/bookViews/workbookView@windowHeight` | EQ L10: geometría de ventana del equipo que guardó (Q11/Q13) |
| `workbook:workbook/bookViews/workbookView@windowWidth` | EQ L10: geometría de ventana del equipo que guardó (Q11/Q13) |
| `workbook:workbook/bookViews/workbookView@xWindow` | EQ L10: geometría de ventana del equipo que guardó (Q11/Q13) |
| `workbook:workbook/bookViews/workbookView@yWindow` | EQ L10: geometría de ventana del equipo que guardó (Q11/Q13) |
| `workbook:workbook/calcPr` | EQ Q13: calcPr (calcId, fullCalcOnLoad) |
| `workbook:workbook/calcPr@calcId` | EQ Q13: calcPr (calcId, fullCalcOnLoad) |
| `workbook:workbook/calcPr@fullCalcOnLoad` | EQ Q13: calcPr (calcId, fullCalcOnLoad) |
| `workbook:workbook/definedNames` | 18 área de impresión y filas a repetir; 24 filtro |
| `workbook:workbook/definedNames/definedName` | 18 área de impresión y filas a repetir; 24 filtro |
| `workbook:workbook/definedNames/definedName@localSheetId` | 18 área de impresión y filas a repetir; 24 filtro |
| `workbook:workbook/definedNames/definedName@name` | 18 área de impresión y filas a repetir; 24 filtro |
| `workbook:workbook/sheets` | 1 nombres y orden de hojas |
| `workbook:workbook/sheets/sheet` | 1 nombres y orden de hojas |
| `workbook:workbook/sheets/sheet@id` | 1 nombres y orden de hojas |
| `workbook:workbook/sheets/sheet@name` | 1 nombres y orden de hojas |
| `workbook:workbook/sheets/sheet@sheetId` | 1 nombres y orden de hojas |
| `workbook:workbook/sheets/sheet@state` | 3 visibilidad |
| `workbook:workbook/workbookPr` | EQ L10: workbookPr sin atributos de efecto |
| `styles:styleSheet` | estructura |
| `styles:styleSheet/borders` | 7 bordes |
| `styles:styleSheet/borders/border` | 7 bordes |
| `styles:styleSheet/borders/border/bottom` | 7 bordes |
| `styles:styleSheet/borders/border/bottom/color` | 7 bordes |
| `styles:styleSheet/borders/border/bottom/color@rgb` | 7 bordes |
| `styles:styleSheet/borders/border/bottom@style` | 7 bordes |
| `styles:styleSheet/borders/border/diagonal` | 7 bordes |
| `styles:styleSheet/borders/border/left` | 7 bordes |
| `styles:styleSheet/borders/border/left/color` | 7 bordes |
| `styles:styleSheet/borders/border/left/color@rgb` | 7 bordes |
| `styles:styleSheet/borders/border/left@style` | 7 bordes |
| `styles:styleSheet/borders/border/right` | 7 bordes |
| `styles:styleSheet/borders/border/right/color` | 7 bordes |
| `styles:styleSheet/borders/border/right/color@rgb` | 7 bordes |
| `styles:styleSheet/borders/border/right@style` | 7 bordes |
| `styles:styleSheet/borders/border/top` | 7 bordes |
| `styles:styleSheet/borders/border/top/color` | 7 bordes |
| `styles:styleSheet/borders/border/top/color@rgb` | 7 bordes |
| `styles:styleSheet/borders/border/top@style` | 7 bordes |
| `styles:styleSheet/borders@count` | 7 bordes |
| `styles:styleSheet/cellStyleXfs` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellStyleXfs/xf` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellStyleXfs/xf@borderId` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellStyleXfs/xf@fillId` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellStyleXfs/xf@fontId` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellStyleXfs/xf@numFmtId` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellStyleXfs@count` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellStyles` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellStyles/cellStyle` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellStyles/cellStyle@builtinId` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellStyles/cellStyle@name` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellStyles/cellStyle@xfId` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellStyles@count` | 4 fuente y estilo por defecto |
| `styles:styleSheet/cellXfs` | 5-9 estilo de celda (resuelto) |
| `styles:styleSheet/cellXfs/xf` | 5-9 estilo de celda (resuelto) |
| `styles:styleSheet/cellXfs/xf/alignment` | 8 alineación |
| `styles:styleSheet/cellXfs/xf/alignment@horizontal` | 8 alineación |
| `styles:styleSheet/cellXfs/xf/alignment@vertical` | 8 alineación |
| `styles:styleSheet/cellXfs/xf/alignment@wrapText` | 8 alineación |
| `styles:styleSheet/cellXfs/xf@applyAlignment` | EQ L10: banderas apply*/pivotButton/quotePrefix por defecto; el estilo se compara resuelto (Q13) |
| `styles:styleSheet/cellXfs/xf@borderId` | 5-9 estilo de celda (resuelto) |
| `styles:styleSheet/cellXfs/xf@fillId` | 5-9 estilo de celda (resuelto) |
| `styles:styleSheet/cellXfs/xf@fontId` | 5-9 estilo de celda (resuelto) |
| `styles:styleSheet/cellXfs/xf@numFmtId` | 5-9 estilo de celda (resuelto) |
| `styles:styleSheet/cellXfs/xf@pivotButton` | EQ L10: banderas apply*/pivotButton/quotePrefix por defecto; el estilo se compara resuelto (Q13) |
| `styles:styleSheet/cellXfs/xf@quotePrefix` | EQ L10: banderas apply*/pivotButton/quotePrefix por defecto; el estilo se compara resuelto (Q13) |
| `styles:styleSheet/cellXfs/xf@xfId` | EQ L10: banderas apply*/pivotButton/quotePrefix por defecto; el estilo se compara resuelto (Q13) |
| `styles:styleSheet/cellXfs@count` | 5-9 estilo de celda (resuelto) |
| `styles:styleSheet/colors` | EQ L10: paleta indexada por defecto (no se usa en ningún color de la plantilla) |
| `styles:styleSheet/colors/indexedColors` | EQ L10: paleta indexada por defecto (no se usa en ningún color de la plantilla) |
| `styles:styleSheet/colors/indexedColors/rgbColor` | EQ L10: paleta indexada por defecto (no se usa en ningún color de la plantilla) |
| `styles:styleSheet/colors/indexedColors/rgbColor@rgb` | EQ L10: paleta indexada por defecto (no se usa en ningún color de la plantilla) |
| `styles:styleSheet/dxfs` | 23a formato condicional (dxf) |
| `styles:styleSheet/dxfs/dxf` | 23a formato condicional (dxf) |
| `styles:styleSheet/dxfs/dxf/fill` | 23a formato condicional (dxf) |
| `styles:styleSheet/dxfs/dxf/fill/patternFill` | 23a formato condicional (dxf) |
| `styles:styleSheet/dxfs/dxf/fill/patternFill/bgColor` | 23a formato condicional (dxf) |
| `styles:styleSheet/dxfs/dxf/fill/patternFill/bgColor@rgb` | 23a formato condicional (dxf) |
| `styles:styleSheet/dxfs/dxf/fill/patternFill/fgColor` | 23a formato condicional (dxf) |
| `styles:styleSheet/dxfs/dxf/fill/patternFill/fgColor@rgb` | 23a formato condicional (dxf) |
| `styles:styleSheet/dxfs/dxf/fill/patternFill@patternType` | 23a formato condicional (dxf) |
| `styles:styleSheet/dxfs/dxf/font` | 23a formato condicional (dxf) |
| `styles:styleSheet/dxfs/dxf/font/color` | 23a formato condicional (dxf) |
| `styles:styleSheet/dxfs/dxf/font/color@rgb` | 23a formato condicional (dxf) |
| `styles:styleSheet/dxfs/dxf/font/i` | 23a formato condicional (dxf) |
| `styles:styleSheet/dxfs/dxf/font/i@val` | 23a formato condicional (dxf) |
| `styles:styleSheet/dxfs@count` | 23a formato condicional (dxf) |
| `styles:styleSheet/fills` | 6 rellenos |
| `styles:styleSheet/fills/fill` | 6 rellenos |
| `styles:styleSheet/fills/fill/patternFill` | 6 rellenos |
| `styles:styleSheet/fills/fill/patternFill/bgColor` | 6 rellenos |
| `styles:styleSheet/fills/fill/patternFill/bgColor@rgb` | 6 rellenos |
| `styles:styleSheet/fills/fill/patternFill/fgColor` | 6 rellenos |
| `styles:styleSheet/fills/fill/patternFill/fgColor@rgb` | 6 rellenos |
| `styles:styleSheet/fills/fill/patternFill@patternType` | 6 rellenos |
| `styles:styleSheet/fills@count` | 6 rellenos |
| `styles:styleSheet/fonts` | 5 fuentes |
| `styles:styleSheet/fonts/font` | 5 fuentes |
| `styles:styleSheet/fonts/font/b` | 5 fuentes |
| `styles:styleSheet/fonts/font/b@val` | 5 fuentes |
| `styles:styleSheet/fonts/font/color` | 5 fuentes |
| `styles:styleSheet/fonts/font/color@rgb` | 5 fuentes |
| `styles:styleSheet/fonts/font/color@theme` | 5 fuentes |
| `styles:styleSheet/fonts/font/family` | 5 fuentes |
| `styles:styleSheet/fonts/font/family@val` | 5 fuentes |
| `styles:styleSheet/fonts/font/name` | 5 fuentes |
| `styles:styleSheet/fonts/font/name@val` | 5 fuentes |
| `styles:styleSheet/fonts/font/scheme` | 5 fuentes |
| `styles:styleSheet/fonts/font/scheme@val` | 5 fuentes |
| `styles:styleSheet/fonts/font/sz` | 5 fuentes |
| `styles:styleSheet/fonts/font/sz@val` | 5 fuentes |
| `styles:styleSheet/fonts@count` | 5 fuentes |
| `styles:styleSheet/numFmts` | 9 formatos numéricos |
| `styles:styleSheet/numFmts/numFmt` | 9 formatos numéricos |
| `styles:styleSheet/numFmts/numFmt@formatCode` | 9 formatos numéricos |
| `styles:styleSheet/numFmts/numFmt@numFmtId` | 9 formatos numéricos |
| `styles:styleSheet/numFmts@count` | 9 formatos numéricos |
| `styles:styleSheet/tableStyles` | 24 tablas (Q8) |
| `styles:styleSheet/tableStyles@count` | 24 tablas (Q8) |
| `styles:styleSheet/tableStyles@defaultPivotStyle` | 24 tablas (Q8) |
| `styles:styleSheet/tableStyles@defaultTableStyle` | 24 tablas (Q8) |
| `sheet:worksheet` | estructura |
| `sheet:worksheet/cols` | 10 anchos |
| `sheet:worksheet/cols/col` | 10 anchos |
| `sheet:worksheet/cols/col@customWidth` | 10 anchos |
| `sheet:worksheet/cols/col@hidden` | 21 ocultas |
| `sheet:worksheet/cols/col@max` | 10 anchos |
| `sheet:worksheet/cols/col@min` | 10 anchos |
| `sheet:worksheet/cols/col@style` | L7 estilo de columna (resuelto) |
| `sheet:worksheet/cols/col@width` | 10 anchos |
| `sheet:worksheet/conditionalFormatting` | 23 formato condicional |
| `sheet:worksheet/conditionalFormatting/cfRule` | 23 formato condicional |
| `sheet:worksheet/conditionalFormatting/cfRule/dataBar` | 23 formato condicional |
| `sheet:worksheet/conditionalFormatting/cfRule/dataBar/cfvo` | 23 formato condicional |
| `sheet:worksheet/conditionalFormatting/cfRule/dataBar/cfvo@type` | 23 formato condicional |
| `sheet:worksheet/conditionalFormatting/cfRule/dataBar/color` | 23 formato condicional |
| `sheet:worksheet/conditionalFormatting/cfRule/dataBar/color@rgb` | 23 formato condicional |
| `sheet:worksheet/conditionalFormatting/cfRule/formula` | 23 formato condicional |
| `sheet:worksheet/conditionalFormatting/cfRule@dxfId` | 23 formato condicional |
| `sheet:worksheet/conditionalFormatting/cfRule@priority` | 23 formato condicional |
| `sheet:worksheet/conditionalFormatting/cfRule@type` | 23 formato condicional |
| `sheet:worksheet/conditionalFormatting@sqref` | 23 formato condicional |
| `sheet:worksheet/dimension` | EQ L10: dimension (la calcula el escritor) |
| `sheet:worksheet/dimension@ref` | EQ L10: dimension (la calcula el escritor) |
| `sheet:worksheet/drawing` | 13 imágenes |
| `sheet:worksheet/drawing@id` | 13 imágenes |
| `sheet:worksheet/headerFooter` | 17 encabezado y pie |
| `sheet:worksheet/headerFooter/evenFooter` | 17 encabezado/pie (vacíos: EQ Q13) |
| `sheet:worksheet/headerFooter/evenHeader` | 17 encabezado/pie (vacíos: EQ Q13) |
| `sheet:worksheet/headerFooter/firstFooter` | 17 encabezado/pie (vacíos: EQ Q13) |
| `sheet:worksheet/headerFooter/firstHeader` | 17 encabezado/pie (vacíos: EQ Q13) |
| `sheet:worksheet/headerFooter/oddFooter` | 17 encabezado y pie |
| `sheet:worksheet/headerFooter/oddHeader` | 17 encabezado/pie (vacíos: EQ Q13) |
| `sheet:worksheet/mergeCells` | 12 combinadas |
| `sheet:worksheet/mergeCells/mergeCell` | 12 combinadas |
| `sheet:worksheet/mergeCells/mergeCell@ref` | 12 combinadas |
| `sheet:worksheet/mergeCells@count` | 12 combinadas |
| `sheet:worksheet/pageMargins` | 16 márgenes |
| `sheet:worksheet/pageMargins@bottom` | 16 márgenes |
| `sheet:worksheet/pageMargins@footer` | 16 márgenes |
| `sheet:worksheet/pageMargins@header` | 16 márgenes |
| `sheet:worksheet/pageMargins@left` | 16 márgenes |
| `sheet:worksheet/pageMargins@right` | 16 márgenes |
| `sheet:worksheet/pageMargins@top` | 16 márgenes |
| `sheet:worksheet/pageSetup` | 15 orientación, papel y ajuste |
| `sheet:worksheet/pageSetup@fitToHeight` | 15 orientación, papel y ajuste |
| `sheet:worksheet/pageSetup@fitToWidth` | 15 orientación, papel y ajuste |
| `sheet:worksheet/pageSetup@orientation` | 15 orientación, papel y ajuste |
| `sheet:worksheet/sheetData` | estructura |
| `sheet:worksheet/sheetData/row` | 11 alturas |
| `sheet:worksheet/sheetData/row/c` | 25 textos y valores |
| `sheet:worksheet/sheetData/row/c/is` | 25 textos y valores |
| `sheet:worksheet/sheetData/row/c/is/t` | 25 textos y valores |
| `sheet:worksheet/sheetData/row/c/v` | 25 textos y valores |
| `sheet:worksheet/sheetData/row/c@r` | detalle por celda (matriz.md) |
| `sheet:worksheet/sheetData/row/c@s` | 5-9 estilo de celda (resuelto) |
| `sheet:worksheet/sheetData/row/c@t` | 25 textos (tipo); inlineStr vs. sharedStrings = EQ L10 |
| `sheet:worksheet/sheetData/row@customFormat` | 11 estilo de fila (solo cuenta con customFormat=1) |
| `sheet:worksheet/sheetData/row@customHeight` | 11 alturas |
| `sheet:worksheet/sheetData/row@ht` | 11 alturas |
| `sheet:worksheet/sheetData/row@r` | 11 alturas |
| `sheet:worksheet/sheetData/row@s` | 11 estilo de fila (solo cuenta con customFormat=1) |
| `sheet:worksheet/sheetData/row@thickBot` | EQ L10: pistas de renderizado de fila (Q13) |
| `sheet:worksheet/sheetFormatPr` | estructura |
| `sheet:worksheet/sheetFormatPr@baseColWidth` | EQ Q13: baseColWidth (10 alturas/anchos por defecto efectivos) |
| `sheet:worksheet/sheetFormatPr@defaultColWidth` | EQ Q13: baseColWidth (10 alturas/anchos por defecto efectivos) |
| `sheet:worksheet/sheetFormatPr@defaultRowHeight` | 11 alturas (por defecto) |
| `sheet:worksheet/sheetPr` | estructura |
| `sheet:worksheet/sheetPr/outlinePr` | 21 agrupación (valores por defecto) |
| `sheet:worksheet/sheetPr/outlinePr@summaryBelow` | 21 agrupación (valores por defecto) |
| `sheet:worksheet/sheetPr/outlinePr@summaryRight` | 21 agrupación (valores por defecto) |
| `sheet:worksheet/sheetPr/pageSetUpPr` | 15 ajuste a página |
| `sheet:worksheet/sheetPr/pageSetUpPr@fitToPage` | 15 ajuste a página |
| `sheet:worksheet/sheetPr/tabColor` | 2 color de pestaña |
| `sheet:worksheet/sheetPr/tabColor@rgb` | 2 color de pestaña |
| `sheet:worksheet/sheetViews` | estructura |
| `sheet:worksheet/sheetViews/sheetView` | estructura |
| `sheet:worksheet/sheetViews/sheetView/pane` | 14 congelados |
| `sheet:worksheet/sheetViews/sheetView/pane@activePane` | 14 congelados |
| `sheet:worksheet/sheetViews/sheetView/pane@state` | 14 congelados |
| `sheet:worksheet/sheetViews/sheetView/pane@topLeftCell` | 14 congelados |
| `sheet:worksheet/sheetViews/sheetView/pane@ySplit` | 14 congelados |
| `sheet:worksheet/sheetViews/sheetView/selection` | 3 selección (Q11) |
| `sheet:worksheet/sheetViews/sheetView/selection@activeCell` | 3 selección (Q11) |
| `sheet:worksheet/sheetViews/sheetView/selection@pane` | 3 selección (Q11) |
| `sheet:worksheet/sheetViews/sheetView/selection@sqref` | 3 selección (Q11) |
| `sheet:worksheet/sheetViews/sheetView@showGridLines` | 20 cuadrícula |
| `sheet:worksheet/sheetViews/sheetView@tabSelected` | 3 hoja activa y desplazamiento (Q11) |
| `sheet:worksheet/sheetViews/sheetView@topLeftCell` | 3 hoja activa y desplazamiento (Q11) |
| `sheet:worksheet/sheetViews/sheetView@workbookViewId` | estructura |
| `drawing:wsDr` | estructura |
| `drawing:wsDr/oneCellAnchor` | 13 imágenes (ancla, Q13/L1) |
| `drawing:wsDr/oneCellAnchor/clientData` | 13 imágenes (por defecto) |
| `drawing:wsDr/oneCellAnchor/ext` | 13 imágenes (tamaño) |
| `drawing:wsDr/oneCellAnchor/ext@cx` | 13 imágenes (tamaño) |
| `drawing:wsDr/oneCellAnchor/ext@cy` | 13 imágenes (tamaño) |
| `drawing:wsDr/oneCellAnchor/from` | 13 imágenes (posición) |
| `drawing:wsDr/oneCellAnchor/from/col` | 13 imágenes (posición) |
| `drawing:wsDr/oneCellAnchor/from/colOff` | 13 imágenes (posición) |
| `drawing:wsDr/oneCellAnchor/from/row` | 13 imágenes (posición) |
| `drawing:wsDr/oneCellAnchor/from/rowOff` | 13 imágenes (posición) |
| `drawing:wsDr/oneCellAnchor/pic` | 13 imágenes |
| `drawing:wsDr/oneCellAnchor/pic/blipFill` | 13 imágenes (medio, estirado) |
| `drawing:wsDr/oneCellAnchor/pic/blipFill/blip` | 13 imágenes (medio, estirado) |
| `drawing:wsDr/oneCellAnchor/pic/blipFill/blip@cstate` | EQ L10: cstate (estado de compresión, sin efecto) |
| `drawing:wsDr/oneCellAnchor/pic/blipFill/blip@embed` | 13 imágenes (medio, estirado) |
| `drawing:wsDr/oneCellAnchor/pic/blipFill/stretch` | 13 imágenes (medio, estirado) |
| `drawing:wsDr/oneCellAnchor/pic/blipFill/stretch/fillRect` | 13 imágenes (medio, estirado) |
| `drawing:wsDr/oneCellAnchor/pic/nvPicPr` | 13 imágenes; L8 bloqueos (noChangeAspect = EQ aceptado) |
| `drawing:wsDr/oneCellAnchor/pic/nvPicPr/cNvPicPr` | 13 imágenes; L8 bloqueos (noChangeAspect = EQ aceptado) |
| `drawing:wsDr/oneCellAnchor/pic/nvPicPr/cNvPr` | 13 imágenes; L8 bloqueos (noChangeAspect = EQ aceptado) |
| `drawing:wsDr/oneCellAnchor/pic/nvPicPr/cNvPr@descr` | 13 imágenes; L8 texto alternativo; nombre `Picture N` = EQ aceptado (humano) |
| `drawing:wsDr/oneCellAnchor/pic/nvPicPr/cNvPr@id` | 13 imágenes; L8 texto alternativo; nombre `Picture N` = EQ aceptado (humano) |
| `drawing:wsDr/oneCellAnchor/pic/nvPicPr/cNvPr@name` | 13 imágenes; L8 texto alternativo; nombre `Picture N` = EQ aceptado (humano) |
| `drawing:wsDr/oneCellAnchor/pic/spPr` | 13 imágenes (posición absoluta, geometría) |
| `drawing:wsDr/oneCellAnchor/pic/spPr/ln` | EQ L10: a:ln sin relleno ni estilo (no dibuja línea) |
| `drawing:wsDr/oneCellAnchor/pic/spPr/ln/prstDash` | EQ L10: a:ln sin relleno ni estilo (no dibuja línea) |
| `drawing:wsDr/oneCellAnchor/pic/spPr/ln/prstDash@val` | EQ L10: a:ln sin relleno ni estilo (no dibuja línea) |
| `drawing:wsDr/oneCellAnchor/pic/spPr/prstGeom` | 13 imágenes (posición absoluta, geometría) |
| `drawing:wsDr/oneCellAnchor/pic/spPr/prstGeom/avLst` | 13 imágenes (posición absoluta, geometría) |
| `drawing:wsDr/oneCellAnchor/pic/spPr/prstGeom@prst` | 13 imágenes (posición absoluta, geometría) |
| `drawing:wsDr/oneCellAnchor/pic/spPr/xfrm` | 13 imágenes (posición absoluta, geometría) |
| `drawing:wsDr/oneCellAnchor/pic/spPr/xfrm/ext` | 13 imágenes (posición absoluta, geometría) |
| `drawing:wsDr/oneCellAnchor/pic/spPr/xfrm/ext@cx` | 13 imágenes (posición absoluta, geometría) |
| `drawing:wsDr/oneCellAnchor/pic/spPr/xfrm/ext@cy` | 13 imágenes (posición absoluta, geometría) |
| `drawing:wsDr/oneCellAnchor/pic/spPr/xfrm/off` | 13 imágenes (posición absoluta, geometría) |
| `drawing:wsDr/oneCellAnchor/pic/spPr/xfrm/off@x` | 13 imágenes (posición absoluta, geometría) |
| `drawing:wsDr/oneCellAnchor/pic/spPr/xfrm/off@y` | 13 imágenes (posición absoluta, geometría) |

## Equivalentes no idénticos (Q13, humano 2026-11-22)

- `alfa_color`: Canal alfa del color ARGB (`00`/`FF`): Excel no lo usa en celdas (Q13).
- `calcPr`: `calcId` y `fullCalcOnLoad` de `calcPr` (Q13: calcId).
- `ancho_base`: `baseColWidth`/`defaultColWidth` del paquete; se compara el ancho por defecto efectivo (Q13: baseColWidth).
- `medios`: Un medio por imagen vs. un medio deduplicado (Q13: medios duplicados).
- `encabezado_vacio`: Elementos de encabezado/pie vacíos (Q13).
- `ancla`: `oneCellAnchor` vs. `twoCellAnchor editAs="oneCell"` con las mismas dimensiones visibles (Q13; L1 confirma que xlsxwriter no escribe oneCellAnchor).

## Equivalentes aceptados fuera de Q13 (decisión del humano 2026-11-22)

- `l8_nombre_imagen`: L8: la imagen se llama `Picture N` (xlsxwriter fija `name="Picture N"` sin opción); la plantilla dice `Image 1`. Mismo tamaño y posición exactos.
- `l8_bloqueo_proporcion`: L8: xlsxwriter siempre escribe `<a:picLocks noChangeAspect="1"/>` (casilla «Bloquear relación de aspecto» marcada); la plantilla no la trae. Mismo tamaño y posición exactos.
- `cfvo_val_min_max`: xlsxwriter escribe `val="0"` en los `cfvo` min/max de las barras de datos (la plantilla no lo trae); para min/max Excel ignora `val` (L5).
- `dxf_patternType`: xlsxwriter escribe el relleno del dxf sin `patternType` y solo con `bgColor`; la plantilla trae `solid` con fg = bg. Excel escribe el dxf igual que xlsxwriter y lo pinta sólido con `bgColor` (L4).
- `fila_s_sin_customFormat`: La plantilla del informe pone `s="18"` en cada fila sin `customFormat`; Excel ignora ese atributo (L10).
- `pistas_fila`: `spans` y `thickBot` de fila; `x14ac:dyDescent` ya entra en Q13 (L10).
- `cstate_y_ln`: `cstate="print"` del blip y `<a:ln><a:prstDash/></a:ln>` sin relleno (no dibuja línea) en las imágenes (L10).
- `cadenas`: `inlineStr` (informe) / `sharedStrings` (activos) vs. `sharedStrings` (xlsxwriter): mismo texto (L10).
- `fullCalcOnLoad_activos`: Activos no trae `fullCalcOnLoad`; xlsxwriter siempre lo escribe en modo automático (solo `set_calc_mode('manual')` lo quita, y agrega `calcMode=manual`). Es parte de `calcPr` (Q13 nombra `calcId`) (L10).
- `ventana_y_aplicacion`: Geometría de `workbookView`, `fileVersion`, `AlternateContent` (ruta local del equipo que guardó), `revisionPtr`, `extLst` del libro y de estilos, `colors` indexados por defecto, banderas `apply*`/`pivotButton`/`quotePrefix`, índices de estilo y de `numFmt` (L10).

## Propiedades del documento (fila 26, decisión del humano 2026-11-22)

- `title`: Según el libro: «Activos» en el Excel de activos; en el informe, el título que ya escribe el generador («Informe · {sesion}»).
- `creator`: Neutro: `AssetControl`.
- `lastModifiedBy`: Sin dato de equipo ni personal. xlsxwriter 3.3.1 SIEMPRE escribe `<cp:lastModifiedBy>` con el mismo valor que `author` (o vacío si no hay autor): no se puede omitir el elemento ni darle otro valor que el de `creator`. Decisión del coordinator 2026-11-22: `creator` = `lastModifiedBy` = `AssetControl` (única opción coherente), CONFIRMADA salvo que el humano pida ambos vacíos.
- `otros`: Sin asunto, palabras clave ni administrador; `Company` vacío (xlsxwriter escribe el elemento sin texto); `created`/`modified` con la hora de generación (xlsxwriter siempre los escribe); `Application` = `Microsoft Excel` (fijo en xlsxwriter, no es dato del equipo).

## Hojas de lista del informe (T4)

- `no_encontrados_datos`: Decisión del humano 2026-11-22: la plantilla no trae fila de datos con estilo en «No encontrados» (filas 10–11 solo con alto 21.95). Sus filas de datos llevan los mismos estilos de datos que las otras hojas de lista: texto `datos` (Todos A10), COP `datos_cop` (Todos J10) y celda vacía `datos_vacia` (Todos E10), sin filas alternas, alto 21.95. Formato condicional de fila completa: la regla de la spec (B11, fila 23a) compara «Ubicación esperada» con «Encontrado en»; esta hoja no tiene «Encontrado en» (todo lo listado no se encontró) y la plantilla no trae regla: sin formato condicional. Prueba: `test_no_encontrados_replica_la_huella_con_los_estilos_de_datos_de_las_listas`.
- `celda_vacia_informe`: Celda de datos sin valor en las listas del informe (marca, serial, «Encontrado en», «Estado físico», «Nota al cierre»): `datos_vacia`, el estilo que la plantilla da a su única celda de datos vacía (Todos E10, categoría D10: Calibri 11, bordes finos, centro/abajo), distinto del de texto (A10). Las listas del informe no tienen columnas de fecha y el precio nunca es nulo (`precio_al_contar` congelado): no hay fecha ni COP vacíos. Prueba: `test_celdas_vacias_de_cada_columna_llevan_el_estilo_vacia_de_la_plantilla`.
- `columnas_ocultas_no_encontrados`: «No encontrados»: G–K ocultas con los anchos de la plantilla (20, 16, 16, 18, 13; L7). Prueba: `test_no_encontrados_oculta_las_columnas_g_a_k_como_la_plantilla`.
- `formato_condicional_listas`: Todos `A10:J499` y cada categoría `A10:I499` con la fórmula y el dxf medidos; con más filas, hasta la última escrita (req. 5). Prueba: `test_con_mas_filas_el_formato_condicional_y_el_area_se_extienden`.
- `dxf_deduplicado`: Decisión del humano 2026-11-22: ACEPTADO como equivalente. xlsxwriter deduplica los `dxf` idénticos: el libro guarda uno solo para las reglas de Todos y de cada categoría (la plantilla guarda uno por regla, los tres iguales). Se compara el `dxf` resuelto de cada regla, como el estilo resuelto de cada celda (índices de estilo: `ventana_y_aplicacion`); cada regla resuelve al mismo estilo.
- `estados_sin_relleno`: Decisión del humano 2026-11-22: «En reparación» y «Dañado» («Estado físico» en las listas y «Nota al cierre» en «No encontrados») van sin relleno ámbar fijo, como la plantilla: llevan el estilo de datos de su columna y no se agrega regla de formato condicional extra. El único ámbar es el de la regla de discrepancia (fila 23a).
- `tabla_y_filtros`: Q8: «Todos los activos» lleva la tabla «Activos» (A9:J…) sin nombre de estilo (`tableStyleInfo` sin `name`: no altera fuente, relleno ni bordes); la hoja por categoría y «No encontrados» (si tiene filas), autofiltro desde la fila 9. Sobrantes aceptados por Q8: `tableParts`, la parte `table`, `autoFilter`.
- `encabezado_impresion_listas`: Vacío, como la plantilla (B5, Q7); pie de la plantilla.
- `bloque_informe`: Empresa CONGELADA al cierre (`cierre.informe`) y «Corte dd/mm/aaaa» con la fecha de corte de la sesión (B17).
- `logo_informe`: Logo congelado ilegible o almacén con error (`OSError`, `ClientError`, `BotoCoreError`): sin imagen y `200` (req. 8), con un WARNING con el tipo del error y, en S3, su código; sin clave, ruta, endpoint, bucket ni datos. Vale también para el PDF. `ClaveInvalida` (clave del logo congelado inválida) NO se degrada: es un error de integridad y se propaga. Prueba: `test_informe_logo_con_clave_invalida_no_se_traga_el_error`.

## Libro del informe (T5)

- `orden_libro`: Q6 (humano 2026-11-22): Todos los activos, Por ubicación, No encontrados, una hoja por categoría, Por categoría, Resumen. Sin detalle (sesión anterior a la 013): Por ubicación, No encontrados, Por categoría, Resumen. Prueba: `test_el_libro_sigue_el_orden_de_la_plantilla_y_abre_en_la_primera_hoja`.
- `hoja_activa`: Q11 (humano 2026-11-22): el libro abre en la primera hoja (`activeTab` ausente = 0; solo ella con `tabSelected`), en A1 y sin `topLeftCell`; la hoja activa («No encontrados»), las celdas activas y el desplazamiento del Resumen (A7) de la plantilla son residuo de edición y no se generan.
- `desglose_cifras`: Criterio 8: «Por ubicación» y «Por categoría» escriben una fila por etiqueta del desglose congelado de `cierre.informe` y la fila Total con sus `totales` (nunca la suma de las filas), desde el `Decimal` exacto (`precio_al_contar`). Prueba: `test_desglose_escribe_el_decimal_congelado_sin_sumar_ni_pasar_por_float`.
- `desglose_disposicion`: Título en A6 (I6 y J6 con el estilo por defecto), cabecera en la fila 7 (I7 y J7 vacías con su estilo), datos desde la 8 con el estilo de la fila 8 de la plantilla y Total justo debajo con el de la fila 9 (fondo `DBEAFE`, I y J vacías con su estilo). Barras de datos `BFDBFE` en F y H de las filas de datos, sin extensión 2010, extendidas hasta la última fila (req. 5); sin filas, sin barras.
- `resumen_tarjetas`: Filas 6–8 de la plantilla: rótulos en A6, C6, E6 (Arial 9 N `1D4ED8`) y G6 (Arial 9 `6B7280`, sin negrita, como la plantilla); valores congelados en A7, C7, E7 (COP) y G7 (`0.0 %`); unidades y «de las unidades registradas» en la fila 8; las demás celdas de A–J con el estilo por defecto centrado de la plantilla.
- `resumen_contexto`: Q7 (humano 2026-11-22) y plan, fila 25g: desde la fila 10, «Sesión» y su nombre; «Cerró» y quién, «Cerrada» y cuándo; «Moneda» COP; «Estado» «Informe congelado»; la `NOTA`; `SIN_DETALLE` y `EMPRESA_VIGENTE` solo si aplican. Rótulo en A y valor en B (D para «Cerrada»). Estilo: el de la nota de lista de la plantilla (Arial 9 `6B7280`, centro vertical, ajuste de texto), sin combinar y con la altura por defecto (plan, filas 11b y 12). «Cerrada» va como texto (hora de Colombia, igual que el PDF): la plantilla no tiene un formato de fecha y hora. Prueba: `test_resumen_replica_la_huella_con_tarjetas_y_filas_de_contexto`. Decisión del humano 2026-11-22: ACEPTADAS (estilo `nota`, sin combinar, altura por defecto; «Cerrada» y «Corte» como texto con hora de Colombia); se revisan visualmente en Excel real en T6.
- `contexto_solo_resumen`: Decisión del humano 2026-11-22: Sesión, Cerró, Cerrada, Moneda, Estado y los avisos `EMPRESA_VIGENTE` van solo en el Resumen; no se repiten en cada hoja (las demás hojas llevan solo el bloque de la plantilla).
- `resumen_lista_omitida`: Q7 (humano 2026-11-22): la lista «Todos los activos» duplicada del Resumen (filas 9–13, combinada A10:J10 y regla A13:J13) no se genera; la fila 9 queda vacía.
- `impresion_hojas_cortas`: Q12 (humano 2026-11-22): Por ubicación, Por categoría y Resumen a 1 × 1 página (como la plantilla); área de impresión hasta la última fila.
- `encabezado_impresion_resumen`: El Resumen pierde el encabezado de impresión con la empresa y la sesión (B5, Q7): ninguna hoja del libro tiene encabezado; el pie es el de la plantilla.
- `propiedades_informe`: Fila 26: título «Informe · {sesion}» y `creator` = `lastModifiedBy` = `AssetControl`; se quita el comentario «Informe congelado» que escribía el generador (sin asunto, palabras clave ni comentarios).
- `corte_congelado`: «Corte dd/mm/aaaa» (E3) en todas las hojas, Resumen incluido: la fecha de corte de la sesión de `cierre.informe` (B17), no la de hoy ni la del cierre. Prueba: `test_corte_es_la_fecha_de_corte_congelada_no_la_de_hoy`.
- `decimal_16_cifras`: xlsxwriter escribe los números con `{:.16G}`: un `Decimal` de más de 16 cifras significativas se rechaza (`ValueError`) en vez de redondearse en silencio; `NUMERIC(14,2)` nunca llega a ese tope. Prueba: `test_un_decimal_de_mas_de_16_cifras_se_rechaza_en_vez_de_redondearse`.
- `ancho_base_comparado`: `defaultColWidth`/`baseColWidth` se comparan como el equivalente `ancho_base` (Q13) en todas las hojas: la plantilla declara 9.140625 y 10; el generado no los escribe (mismo ancho por defecto efectivo).
- `valores_por_omision`: Cobertura en las dos direcciones (fila 27): la plantilla escribe atributos con su valor por omisión que xlsxwriter no escribe: `<b val="1"/>` y `<i val="1"/>` (xlsxwriter: `<b/>` y `<i/>`; `val` vale `true` por omisión en ECMA-376), `fitToWidth="1"`, `sheet@state="visible"`, `outlinePr` por defecto y `col@style` que resuelve al estilo por defecto. La propiedad se compara resuelta (negrita, cursiva del dxf, ajuste de ancho, visibilidad, agrupación, estilo de columna) y coincide. Decisión del humano 2026-11-22: ACEPTADOS como equivalentes.
- `regla_discrepancia_vacia`: Cambio semántico menor (T4, documentado en T5): la regla de fila completa sigue la fórmula de la plantilla `AND($F10<>"",$G10<>"",$F10<>$G10)`; con «Ubicación esperada» vacía la fila ya no se marca (antes el generador marcaba la celda «Encontrado en» si difería). La ubicación esperada sale del cierre y no suele faltar.

## Encabezado junto al logo (decisión del humano 2026-11-24)

- `encabezado_junto_al_logo`: Decisión del humano 2026-11-24: el bloque de las dos exportaciones (activos e informe) pone el título junto al logo y debajo la línea «Informe · empresa · exportado|corte fecha» (C3) con una línea fina gris. En la fila 4, los rótulos «Empresa», «Contacto» y «Dirección»; en la fila 5, bajo cada uno, sus datos (nombre y NIT; correo y teléfono; dirección) en celdas combinadas con ajuste de texto, hasta el fin de la banda. Un dato ausente se omite y un grupo sin datos va sin rótulo. Se quitan los rótulos «Exportado» y «Correo» de la plantilla. Alturas: fila 4 = 16 y fila 5 = 30. El logo conserva su caja y su tamaño (`CajaLogo`, en EMU) y lleva un marco gris fino (`D1D5DB`, 0,75 pt, sin relleno) a 3 px de la imagen; el marco depende del logo, así que no va en la huella y lo cubre su propia prueba. Las huellas `activos.json` e `informe.json` llevan las filas 1–5 de este diseño, con sus marcadores.
