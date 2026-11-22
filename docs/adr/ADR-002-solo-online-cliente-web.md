# ADR-002: MVP solo online, con un cliente web

- **Estado:** Propuesta
- **Fecha:** 2026-11-09

## Contexto

El diseño inicial era local-first: app móvil con SQLite, cola de eventos y sincronización por lotes. Es la parte más costosa y riesgosa del proyecto (idempotencia, reconciliación, eventos tardíos, versiones). La clínica tiene internet estable y el objetivo es validar el producto cuanto antes.

## Decisión

- El MVP es **solo online**. No hay base local, cola de eventos ni endpoint de sincronización.
- El cliente es **una aplicación web responsiva** (ver [ADR-001](ADR-001-stack.md)); el conteo se hace desde el navegador del teléfono.
- Se conserva lo barato y útil del diseño anterior:
  - Verificaciones inmutables con **UUID generado en el cliente** (idempotencia ante doble toque y reintentos).
  - Fotos subidas por separado de la verificación, para que una foto lenta no bloquee el conteo.
  - Reubicación como observación (`ubicacion_encontrada_id`); el admin aplica las discrepancias al cerrar.
- Si una petición falla por red, la interfaz lo muestra y permite **reintentar**. No hay cola persistente.
- Una verificación contra una sesión cerrada responde `409 sesion_cerrada`.

## Alternativas consideradas

- **Local-first con app Expo:** el diseño original. Más tiempo, más pruebas y distribución de la app, sin necesidad demostrada.
- **PWA con cola de reintentos:** término medio. No se hace ahora; queda como evolución natural sobre el mismo cliente web si el piloto muestra zonas sin cobertura.

## Consecuencias

- Menos código y menos casos límite: sale la sincronización, la resolución de conflictos y el segundo cliente.
- El conteo depende de la conexión. Mitigación: avisos claros y reintento idempotente.
- Criterio de reevaluación: si en el piloto más de un conteo se interrumpe por falta de red, se escribe un ADR de PWA offline.
- La importación, el catálogo, las discrepancias y los informes viven en la misma web (modo administración).
