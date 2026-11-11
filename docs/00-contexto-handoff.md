> **Documento histórico.** Es el contexto original del proyecto. Dos decisiones de abajo fueron reemplazadas: el enfoque *local-first* y la app Expo/SQLite pasaron a un cliente web solo online (ver [ADR-001](adr/ADR-001-stack.md) y [ADR-002](adr/ADR-002-solo-online-cliente-web.md)). Lo vigente está en el resto de `docs/`.

# Traspaso a Claude Code: sistema de inventario de activos

Pega este documento al inicio de la sesión en Claude Code. Es el contexto de todo lo definido hasta ahora.

## Qué estamos construyendo

Un sistema para llevar el inventario de activos (equipos y mobiliario) de clínicas. Se hacen conteos periódicos desde cualquier teléfono con la app, se guarda el historial de cada conteo y se genera un informe con el valor total de los activos para presentarlo a los socios. Primer cliente: una clínica odontológica en Cartago, Colombia. El diseño es multi-tenant desde el inicio.

## Decisiones ya tomadas

- **Alcance:** solo activos fijos (equipos y mobiliario). No hay control de consumibles ni stock.
- **Precio:** es el precio de compra. El informe de valor total se basa en eso.
- **Historial:** cada conteo es una sesión. Las sesiones cerradas no se editan. Cada activo tiene una línea de tiempo con verificaciones, cambios de ubicación, de precio y de estado.
- **Quién cuenta:** cualquier persona registrada en la app, desde cualquier teléfono con la app.
- **Identificación:** stickers de código de barras que se compran y se pegan a cada activo; el `codigo` del activo es el impreso en el sticker.
- **Nota (2026-11-11):** el modelo vigente es una fila por unidad física, con `codigo` del sticker (obligatorio, único por tenant, inmutable; el sistema no lo genera ni imprime etiquetas) y alta por escaneo, sin alta sin sticker; no hay `cantidad` ni lotes (ver P1 en [05-preguntas-abiertas.md](05-preguntas-abiertas.md)). El Excel sigue siendo contexto y la importación es opcional.
- **Sin internet:** local-first. El conteo se guarda en el teléfono y se sincroniza después. La clínica tiene internet estable, pero el diseño debe funcionar sin red.
- **Importación:** el Excel actual se importa con pantalla de revisión para duplicados y datos dudosos.
- **Stack:** Flask (backend), PostgreSQL (base de datos) y React Native con Expo (app móvil, con SQLite local).
- **Metodología:** documentos de arquitectura en el repositorio, decisiones registradas como ADR, y un MVP con criterios de éxito medibles.

## Puntos abiertos (no decididos todavía)

- Nombre de la app y del repositorio.
- Fecha del último conteo real del cliente. Los encabezados del Excel no coinciden entre hojas (16/08/2023, 25/08/2023 y 12/12/2023).
- Si el precio necesita fecha de compra y proveedor además del precio.
- Dónde se guardan las fotos en el MVP (disco local con respaldo o servicio de objetos).
- Cómo se maneja la reubicación de un activo cuando el conteo se hace sin internet.
- Si el valor total se calcula por sesión, por fecha de corte o en tiempo real.

## Hallazgos del Excel actual (para validar el modelo)

- El libro tiene 23 hojas: 16 por ubicación, 6 por categoría y una hoja TOTAL.
- Cada activo aparece dos veces, en su hoja de ubicación y en su hoja de categoría.
- La hoja TOTAL muestra $167.226.590,70, pero la suma real de los activos es cercana a $172.013.797,08. La diferencia viene de un subtotal de CPU que omite tres filas.
- Hay seriales repetidos entre ubicaciones (por ejemplo, la cámara 3C01317PAG00139 aparece en tres hojas).
- Algunas fórmulas multiplican por cantidad dos veces, y hay precios con fórmulas escritas a mano.
- Los nombres de categoría varían (Mobiliaria, Mobiliario, Inmobiliaria).

## Qué necesitamos en la fase de diseño

1. Modelo de datos completo: tenants, usuarios, membresías, ubicaciones, activos, sesiones de conteo, verificaciones, eventos de historial, fotos.
2. Diseño de la sincronización: formato de eventos, endpoint de lotes, reconciliación y manejo de conflictos.
3. Contratos de la API (endpoints, autenticación y roles).
4. Flujos de pantalla de la app para conteo, alta por escaneo, búsqueda y revisión de importación.
5. Plan de importación del Excel.
6. Informe de valor total: qué incluye y cómo se exporta.
7. Estructura del repositorio y reglas de trabajo (ramas, revisión, definición de terminado).
8. ADR iniciales: stack y sincronización local-first.

## Repositorio

Existe un commit inicial local (`36be4b3`) con README, alcance y arquitectura. Todavía no está publicado en GitHub porque falta crear el repositorio remoto y decidir su nombre.
