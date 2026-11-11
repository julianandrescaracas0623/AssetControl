# 06. Análisis del Excel actual e importación opcional

El Excel es el **contexto del problema**: hoy todo se digita a mano, en dos vistas (por ubicación y por categoría) que hay que mantener sincronizadas a mano. Este documento lo analiza para validar el modelo de datos y, si se decide importarlo (pregunta P10), define cómo hacerlo. **La importación no es un requisito del MVP.**

> **Nota (2026-11-11):** las menciones a `CANTIDAD` y a lotes describen el Excel, no el modelo nuevo. Allí ya no hay `cantidad` ni lotes: una fila por unidad física con `codigo` del sticker de código de barras, obligatorio y único por tenant (P1, P9). Una eventual importación necesitaría un código de sticker por cada unidad; cómo se asigna es `[PENDIENTE]` y depende de P9. Una eventual importación expandiría cada fila con cantidad >1 en una fila por unidad. No se construye ahora (P10).

## Estructura real del libro

El libro tiene 23 hojas: 16 por ubicación, 6 por categoría y una hoja `TOTAL`. Cifras medidas sobre el archivo original:

| Tipo de hoja | Columnas | Filas de datos | Unidades | Precio |
|---|---|---|---|---|
| Ubicación (16) | NOMBRE, CATEGORIA, CANTIDAD, MARCA, SERIAL, MODELO, REFERENCIA, LUGAR, COLOR, ESTADO | 245 | 301 | **No** |
| Categoría (6) | NUMERO, NOMBRE, CATEGORIA, CANTIDAD, MARCA, PRECIO, TOTAL, SERIAL, (LOTE o MODELO/SERIE/REGISTRO SANITARIO), LUGAR, COLOR, ESTADO | 191 | 219 | **Sí** |

Conclusiones:

1. **Son dos vistas del inventario, no una copia exacta.** Las hojas de ubicación dicen *dónde* está cada cosa; las de categoría dicen *cuánto costó*. Las cifras no coinciden (301 vs 219 unidades), así que hay filas de ubicación sin precio conocido y puede haber filas de categoría sin ubicación confiable.
2. **Las columnas de las hojas de categoría no son iguales entre sí.** La detección de columnas se hace por el texto del encabezado, nunca por posición.
3. **Los seriales repetidos entre ubicaciones son válidos.** Hay 13 en las hojas de ubicación (por ejemplo, un mismo serial de cámara en Sala de Espera 2 y Gerencia): según la clínica, se repiten porque hay unidades en esas áreas. Por eso el serial **no es clave única** y nunca se usa para fusionar filas. Un serial repetido genera, como máximo, un aviso informativo.
4. **Valores que no son serial:** `No Especifica`, `No Requiere`, `No Require`, `N/A`, `No Aplica`, `Pendiente`, vacío. Se tratan como "sin serial".

## La diferencia en el total

| Concepto | Valor |
|---|---|
| Suma de la columna TOTAL de las 6 hojas de categoría | $172.013.797,08 |
| Hoja `TOTAL` del libro | $167.226.590,70 |
| Diferencia | $4.787.206,38 |

La diferencia está toda en CPU: la hoja `TOTAL` dice 16 unidades por $16.685.410, y la hoja de CPU suma 17 unidades por $21.472.616,38. Mobiliario, Electrónica, Periféricos, Electrodomésticos y Biomédicos coinciden con la hoja `TOTAL`.

**Criterio de aceptación de la importación:** el total importado debe ser igual a la suma de las hojas de categoría ($172.013.797,08), más lo que el admin complete en la revisión. Nunca igual a la hoja `TOTAL`.

## Suciedad de datos conocida

- Categorías por fila con variantes: `Equipo Biomedico`, `EquipoBioquimico`, `Mobiliaria`, `Computador`, `Video`, `Fuente`…
- Estados: `Funciona`, `Funsiona`, `Funcional`, `Buen Estado`, `No Funciona`.
- Seriales numéricos leídos como decimales (`3463344552.0`) y una fecha en la columna LOTE.
- Lugares compuestos o con variantes: `BOX 4/3`, `Box 5`, `BOX5`, `Insumoa`, `Rack`/`RACK`.
- Numeración repetida en la hoja CPU (dos filas con el número 16).
- Cantidades >1 en filas de mobiliario (lotes).

## Plan de importación

1. **Subida** del `.xlsx` desde el panel web (solo `admin`). El servidor lo lee con `openpyxl` en modo `data_only` (valores calculados, sin ejecutar fórmulas).
2. **Lectura por hoja**, con detección de encabezado y de columnas por texto. Cada fila se guarda cruda en `importacion_fila` (hoja, número de fila, datos).
3. **Normalización:** diccionario de categorías y estados, mayúsculas/espacios, números de serial como texto, parser de montos en formato colombiano.
4. **Emparejamiento** de filas de ubicación con filas de categoría por `(nombre normalizado, serial real si existe, lugar)`. Cada fila resulta en una de:
   - `emparejada`: tiene ubicación y precio.
   - `sin_precio`: solo en hojas de ubicación.
   - `sin_ubicacion_confiable`: solo en hojas de categoría.
   - `ambigua`: varias candidatas.
5. **Pantalla de revisión** (web): filtros por resultado, edición en línea de precio/categoría/ubicación, decisión por fila (`importar`, `omitir`, `fusionar`). Un contador muestra el total que se importaría.
6. **Confirmación** (acción única, transaccional): crea activos, la sesión baseline `tipo = importacion` y un evento `importado` por activo. Ningún activo se crea sin precio confirmado.

   `[PENDIENTE]` Si una importación futura (M9) necesitara marcar filas dudosas, se diseña en su propia spec con su tabla `importacion_fila`; `activo` no lleva ningún campo de revisión (se eliminó `requiere_revision`, ver [03](03-modelo-datos.md)).
7. **Entregable previo a la implementación:** un script que mida la tasa real de emparejamiento sobre este archivo. La decisión de qué hoja es la base se toma con ese número, no antes.

## Datos sensibles

El `.xlsx` original contiene datos de la clínica. No se versiona: la carpeta `datos/` y los archivos `*.xlsx`/`*.xls` están en `.gitignore`. Para pruebas se usa un archivo reducido y anonimizado en `backend/tests/fixtures/`.
