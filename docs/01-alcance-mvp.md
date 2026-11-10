# 01. Alcance del MVP

## Objetivo

Reemplazar el libro de Excel por una app que permita hacer conteos de activos desde cualquier teléfono, guardar el historial de cada conteo y generar un informe con el valor total de los activos.

## Dentro del alcance

- **Activos fijos:** equipos biomédicos, computadores, periféricos, electrodomésticos y mobiliario.
- **Ubicaciones:** registro de sedes, salas y boxes. Una ubicación pertenece a un solo tenant.
- **Usuarios y acceso:** cuentas, invitación por correo y dos roles: administrador (crea ubicaciones, activos e informes) y contador (cuenta y consulta).
- **Alta de activo:** con código escaneado (QR o código de barras) o sin etiqueta. Con etiqueta, la cámara lee el código y abre el activo. Sin etiqueta, el alta rápida pide foto y pocos campos.
- **Sesiones de conteo:** una sesión agrupa las verificaciones de un período. Cada verificación registra qué activo se encontró, en qué ubicación, con qué estado y quién lo hizo.
- **Historial:** las sesiones cerradas no se editan. Cada activo tiene una línea de tiempo con verificaciones, cambios de ubicación, de precio y de estado.
- **Importación desde Excel:** carga inicial de las hojas por ubicación y por categoría, con pantalla de revisión para duplicados y datos dudosos.
- **Informe de valor total:** suma de precios de compra por categoría y por ubicación, con fecha de corte y sesión de referencia. Exportable a PDF y Excel.
- **Funcionamiento sin internet:** el conteo se guarda en el teléfono y se sincroniza al recuperar conexión.

## Fuera del alcance

- Control de consumibles, entradas y salidas de stock.
- Depreciación contable y cálculo de valor en libros.
- Reconocimiento visual de objetos sin etiqueta.
- Lectura automática de seriales por OCR (queda para una fase posterior).
- Compras, proveedores y facturación.
- Multisucursal con permisos avanzados.

## Criterios de éxito del MVP

1. Un usuario puede completar un conteo de una sala de la clínica desde su teléfono, sin internet, y el conteo aparece en el servidor al reconectarse.
2. El informe de valor total coincide con la suma de los activos de la sesión, con cero diferencias.
3. Cada activo muestra su historial completo, con quién y cuándo lo verificó.
4. El Excel actual se puede importar y revisar en menos de una hora de trabajo.

## Supuestos

- El precio registrado es el precio de compra. Se usa como base del informe para justificar la inversión ante los socios.
- Las etiquetas se compran aparte y se pegan a cada activo antes del primer conteo con escaneo.
- Un activo tiene una sola ubicación vigente a la vez.
