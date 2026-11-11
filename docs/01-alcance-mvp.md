# 01. Alcance del MVP

## Objetivo

Reemplazar el libro de Excel por una aplicación web que permita hacer conteos de activos desde cualquier teléfono (o computador), guardar el historial de cada conteo y generar un informe con el valor total de los activos.

**El problema que se quiere eliminar es tener que digitar todo a mano en Excel.** Por eso el principio de diseño es *cero digitación innecesaria*: escanear en vez de escribir, elegir en vez de teclear, copiar un activo parecido en vez de empezar de cero.

## Dentro del alcance

- **Activos fijos:** equipos biomédicos, computadores, periféricos, electrodomésticos y mobiliario.
- **Ubicaciones:** registro de sedes, salas y boxes. Una ubicación pertenece a un solo tenant.
- **Usuarios y acceso:** cuentas, invitación por enlace de un solo uso y dos roles: administrador (crea ubicaciones y categorías, invita, edita el catálogo, importa, cierra sesiones, aplica discrepancias y genera informes) y contador (cuenta, consulta y da de alta activos escaneando un sticker nuevo). Ambos roles dan de alta activos, sin revisión posterior del admin (decisión del 2026-11-11, P11); el resto de la escritura del catálogo es solo del administrador. **Precios (P13, 2026-11-11):** el `precio_compra` es obligatorio al dar de alta; solo el administrador ve precios. El contador lo escribe al dar de alta y después no lo ve (ficha, historial, verificación, autocompletado ni API); el filtrado se hace en el servidor.
- **Alta de activo:** una fila por unidad física. Se compran stickers de código de barras y se pegan a cada activo; el `codigo` del activo es el impreso en el sticker (el sistema no lo genera ni imprime etiquetas). Es obligatorio, único por tenant e inmutable tras el alta; un duplicado se rechaza. La cámara del celular lee el código: si existe abre el activo, y si no existe en el tenant ofrece crearlo con ese código (pocos campos, copiando un activo parecido). No hay alta sin sticker; la entrada manual del código queda como respaldo si la cámara no lo lee. El serial del fabricante es opcional y no único.
- **Sesiones de conteo:** una sesión agrupa las verificaciones de un período. Cada verificación registra qué activo se encontró, en qué ubicación, con qué estado y quién lo hizo.
- **Historial:** las sesiones cerradas no se editan. Cada activo tiene una línea de tiempo con verificaciones, cambios de ubicación, de precio y de estado.
- **Alta con poca digitación:** autocompletado de nombre, marca y modelo con lo ya registrado; "duplicar activo" para equipos parecidos; alta de cada unidad por escaneo de su sticker (una fila por unidad); listas cerradas de categoría, ubicación y estado.
- **Carga inicial:** el Excel actual sirve de referencia de los datos reales ([06-importacion-excel.md](06-importacion-excel.md)). Una importación con pantalla de revisión es **opcional** y se hace después del conteo, si ahorra trabajo.
- **Informe de valor total:** suma de precios de compra por categoría y por ubicación, con fecha de corte y sesión de referencia. Las tres cifras, el desglose por categoría y por ubicación y la lista por activo de los no encontrados (con la marca "en reparación") se congelan al cerrar la sesión ([ADR-003](adr/ADR-003-verificacion-con-snapshot.md), R4, R9 y R9a de [03](03-modelo-datos.md)); el informe los lee, no los recalcula. La lista de no encontrados contiene precios y solo la ve el administrador. Exportable a PDF y Excel.
- **Inicio (dashboard) con evolución** (decisión del 2026-11-11): pantalla de inicio con indicadores (total de activos registrados y valor actual del inventario en COP, ambos en tiempo real sobre los activos en estado activo o en reparación, sin los dados de baja, P15; avance del conteo abierto con % verificado y pendientes por ubicación; discrepancias sin resolver; activos dañados o en reparación; último informe cerrado con sus tres cifras), actividad reciente (altas, verificaciones y cambios), gráficas de valor por categoría y por ubicación, y evolución entre conteos (valor registrado y % encontrado por sesión cerrada, también por categoría). **Roles y precios (P13):** el valor actual, las discrepancias, los dañados o en reparación y el último informe son solo del administrador; las gráficas de valor y el valor registrado de la evolución son precios y tampoco los ve el contador (qué más ve el contador en su Inicio: `[PENDIENTE]`, P25). El contador tiene una versión del Inicio sin ningún precio (ni en indicadores ni en la actividad reciente); el filtrado se hace en el servidor. La evolución usa solo sesiones cerradas de tipo conteo y lee el desglose congelado al cierre.
- **Uso desde el teléfono:** la interfaz de conteo está pensada primero para pantalla pequeña y se usa desde el navegador, sin instalar nada.

## Fuera del alcance

- Funcionamiento sin internet (conteo offline). Se reevalúa después del primer piloto; ver [ADR-002](adr/ADR-002-solo-online-cliente-web.md).
- App móvil nativa.
- Control de consumibles, entradas y salidas de stock.
- Depreciación contable y cálculo de valor en libros.
- Reconocimiento visual de objetos sin sticker.
- Generación o impresión de etiquetas por el sistema.
- Lectura automática de seriales por OCR (queda para una fase posterior).
- Compras, proveedores y facturación.
- Multisucursal con permisos avanzados.

## Criterios de éxito del MVP

1. Un usuario puede completar un conteo de una sala de la clínica desde el navegador de su teléfono, escaneando stickers de código de barras, y cada verificación queda guardada en el servidor al confirmarla. Si se corta la conexión, la app avisa y permite reintentar sin duplicar.
2. El informe de valor total coincide con la suma de los activos de la sesión, con cero diferencias.
3. Cada activo muestra su historial completo, con quién y cuándo lo verificó.
4. Dar de alta un activo nuevo, escaneando su sticker, toma menos de 30 segundos y requiere escribir como máximo el nombre y el precio (el resto se elige o se autocompleta).

Nota al criterio 2 (2026-11-11): "cero diferencias" incluye el desglose. Para cada dimensión (categoría y ubicación), la suma de las filas congeladas al cierre es igual a las tres cifras de la sesión. La evolución entre conteos del Inicio solo muestra sesiones cerradas y sus cifras coinciden con las de cada informe.

## Supuestos

- El precio registrado es el precio de compra. Se usa como base del informe para justificar la inversión ante los socios.
- Los stickers de código de barras se compran aparte y se pegan a cada activo; su formato, tamaño y numeración están `[PENDIENTE]` (P9). El sistema no los genera ni imprime.
- La lectura de códigos de barras con la cámara de los teléfonos reales se prueba antes de comprar el lote completo.
- Un activo tiene una sola ubicación vigente a la vez.
- La clínica tiene internet estable en todas las áreas donde se cuenta.
