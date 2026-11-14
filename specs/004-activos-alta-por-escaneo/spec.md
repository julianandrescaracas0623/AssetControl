# Spec 004 — Activos: alta por escaneo

> **Estado:** Propuesta, pendiente de aprobación humana (G1–G3). Fecha: 2026-11-14. Depende de la 003 (ubicaciones y categorías, hecha). Módulo M3 parcial: CU-CAT-01 a CU-CAT-04 de `docs/07`. Plan en `plan.md`, tareas en `tasks.md`.

## Problema

La clínica cuenta unos 300 activos y hoy los lleva en un Excel con nombres y ubicaciones en texto libre. Para contar con el teléfono, cada activo debe existir en el sistema con el código de su sticker. Esta spec permite registrarlos escaneando el sticker (o escribiendo el código si la cámara falla), con lo mínimo tecleado: nombre y precio. Lo demás se elige o se copia de un activo parecido.

## Usuarios

- **Contador y admin:** escanean un sticker. Si el activo existe, lo ven; si no, lo dan de alta o lo duplican de uno parecido (P11: sin revisión posterior).
- **Admin:** además ve precios y busca en la lista de activos.

## Alcance

- **Incluye:** tablas `activo` y `activo_evento` (migración `0007`), evento `creado`; resolver un código; alta idempotente con UUID del cliente; duplicar (copiar de un parecido); autocompletar nombre, marca, modelo y subtipo; búsqueda y lista de activos (solo lectura); ficha de solo lectura; escáner con la cámara (ZXing) y entrada manual; las dos reglas de ubicación decididas el 2026-11-14 (D1, D2); filtrado del precio por rol en el servidor.
- **No incluye:** editar, mover, cambiar estado o dar de baja (spec 005), historial completo en la ficha (005), sesiones y verificación (006), importar el Excel (012), fotos, imprimir stickers (el sistema no genera códigos).

## Requisitos (EARS)

1. **R1 Resolver.** Cuando alguien escanee o escriba un código, el sistema debe devolver el activo de ese código en el tenant o `404`; un código de otro tenant se trata como inexistente.
2. **R2 Código (Q1).** El `codigo` debe ser obligatorio, único por tenant, inmutable y con el formato de Q1; un duplicado se rechaza con `409 codigo_existente` e indica el activo que ya lo tiene, para abrirlo en vez de duplicar.
3. **R3 Alta.** Cuando un usuario dé de alta, el sistema debe exigir nombre (regla H-3), precio de compra (Q2), categoría y ubicación, y aceptar como opcionales serial, marca, modelo, subtipo y fecha de compra (Q5); crear el `activo` en estado `activo` y el evento `creado` con quién lo dio de alta, en una sola transacción.
4. **R4 Idempotencia (R2 de `docs/03`).** Cuando llegue de nuevo un alta con el mismo `id` del cliente, el sistema debe devolver el activo ya guardado sin duplicar ni fallar.
5. **R5 Precio por rol (P13).** Mientras el usuario sea contador, ninguna respuesta debe incluir precios (activo, búsqueda, sugerencias, duplicado); el filtrado es del servidor. El contador escribe el precio en un alta nueva y no lo vuelve a ver.
6. **R6 Duplicar (CU-CAT-03, Q3).** Cuando se duplique, el servidor debe copiar categoría, nombre, marca, modelo, subtipo, precio y ubicación del activo de origen; nunca código, serial ni historial.
7. **R7 Ubicación del activo (D1).** El sistema debe aceptar solo una sala o un box activos de su tenant como ubicación de un activo; una sede se rechaza (`400 ubicacion_invalida`).
8. **R8 Desactivar ubicación con activos (D2).** Cuando el admin desactive una ubicación con activos en estado `activo` o `en_reparacion`, el sistema debe rechazarlo con `409 tiene_activos` y el número de activos; los dados de baja no bloquean.
9. **R9 Escáner.** Cuando el usuario abra el escáner en un teléfono con HTTPS y permiso de cámara, la web debe leer el código de barras del sticker, consultar una sola vez por lectura (lecturas repetidas en menos de 1 s se ignoran) y, si la cámara está denegada o falla, ofrecer escribir el código.
10. **R10 Búsqueda.** Ambos roles deben poder buscar activos por código, nombre o serial (el serial solo busca, no deduplica), con paginación; el admin ve el precio en la lista.

## Criterios de aceptación

- A1: migración `0007` con `activo` y `activo_evento`, RLS forzada, `GRANT` por columna, sin `DELETE`; `activo_evento` solo `INSERT` y `SELECT` (inmutable); catálogo de RLS ampliado.
- A2: pruebas de API: alta, reintento con el mismo `id`, código duplicado, formato de código, precio inválido, sede rechazada, ubicación o categoría de otro tenant (`404`), duplicar, sugerencias, búsqueda y paginación; **ninguna respuesta al contador contiene precio** (prueba que recorre todas las respuestas del contador).
- A3: desactivar una ubicación con activos devuelve `409 tiene_activos`; con solo dados de baja se permite.
- A4: contrato OpenAPI de los endpoints nuevos con sus respuestas reales validadas.
- A5: en navegador real (375 y 1440 px): escanear un código simulado, alta en menos de 30 s tecleando solo nombre y precio, duplicar, reintento sin duplicar, sin desbordes, sin errores de consola y sin violaciones axe.
- A6 (humano, con teléfonos reales; cierra P4 y P9): leer los stickers reales con los teléfonos del personal y medir el tiempo de alta (P10). La sesión prepara la guía y el servidor de prueba con HTTPS.

## Decisiones ya tomadas (humano, 2026-11-14)

| Decisión | Contenido |
|---|---|
| **D1** Sede sin activos | Un activo vive en una sala o un box; lo que no tiene cuarto va en una sala como "Áreas comunes" o "General". |
| **D2** Desactivar con activos | Se bloquea (`409 tiene_activos`) hasta mover los activos; los dados de baja no cuentan y los en reparación sí. "Mover y desactivar en un paso" queda para cuando exista mover activos (005). |

## Riesgos

- El precio mal tecleado por un contador entra sin revisión (P11): lo corrige el admin en la 005 (`precio_cambiado`); el evento `creado` dice quién dio de alta.
- La cámara exige HTTPS y un navegador reciente (P4): en desarrollo, `localhost` vale en el computador, pero un teléfono necesita HTTPS en la red local.
- Los stickers aún no están comprados (P9): el formato del código (Q1) debe aceptar lo que se compre; la prueba con teléfonos reales lo confirma antes de comprar el lote.

## Preguntas abiertas (para G1)

- **Q1 Formato del código:** recomendado: de 1 a 40 caracteres, solo letras sin tilde, números y `-` `.` `/` `_`, sin espacios; se guarda en **mayúsculas** para que escribirlo a mano coincida con lo escaneado.
- **Q2 Precio:** recomendado: mayor o igual a 0 (una donación vale 0), con dos decimales como máximo y tope de `999.999.999.999,99` (`NUMERIC(14,2)`).
- **Q3 Contador al duplicar:** recomendado: hereda el precio del original sin verlo ni cambiarlo (lo que dice hoy `docs/07`); el admin sí lo ve y puede cambiarlo antes de guardar.
- **Q4 Dependencias:** `@zxing/browser` 0.2.1 y `@zxing/library` 0.23.0 (escáner, ya decidido en `docs/07`); `@vitejs/plugin-basic-ssl` 2.3.0 solo de desarrollo para probar con teléfonos en la red local.
- **Q5 Fecha de compra (P7):** recomendado: incluirla como opcional; proveedor queda fuera.
- **Q6 Lista y ficha:** recomendado: `/admin/activos` y la ficha pasan a datos reales en solo lectura (búsqueda incluida); sus acciones (editar, mover, dar de baja) siguen como maqueta hasta la 005.
