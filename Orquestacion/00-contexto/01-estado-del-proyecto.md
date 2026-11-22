# Estado del proyecto

> **Fecha:** 2026-11-09
> **Fuente:** [`docs/`](../../docs/) y el Excel original de la clínica (local, en `datos/`).
> **Propósito:** dejar claro qué existe, qué no y qué restricciones hay antes de planear.

---

## 1. Qué existe hoy

### Documentación

- Alcance del MVP, arquitectura, modelo de datos, metodología y preguntas abiertas ([`docs/01` a `05`](../../docs/)).
- Análisis del Excel actual y plan de importación opcional ([`docs/06`](../../docs/06-importacion-excel.md)).
- Constitución y cuatro ADR en estado `Propuesta` ([`docs/adr/`](../../docs/adr/)).
- Primera spec: `specs/001-fundacion-tecnica/`, pendiente de aprobación.

### Código

- No hay implementación de backend, web ni base de datos.
- Sin repositorio remoto, CI ejecutándose ni entornos desplegados. Los workflows de `.github/` están escritos y se activan al publicar.

### Conclusión

El proyecto está en **Fase 0: definición**. La ventaja es que el problema está medido sobre datos reales; el riesgo es construir sincronización, app nativa o importación antes de validar lo esencial: contar rápido y cerrar un informe correcto.

---

## 2. El Excel de origen (contexto del problema)

El libro tiene 23 hojas: 16 por ubicación, 6 por categoría y una hoja `TOTAL`.

| Hallazgo | Detalle |
|---|---|
| Dos vistas, no una copia | Ubicación: 245 filas / 301 unidades, **sin precio**. Categoría: 191 filas / 219 unidades, con precio |
| Total que no cuadra | Hoja `TOTAL`: $167.226.590,70. Suma real: $172.013.797,08. Diferencia: $4.787.206,38, toda en CPU (16 unidades en `TOTAL` contra 17 en la hoja) |
| Seriales repetidos | 13 en las hojas de ubicación. Son válidos: hay unidades en esas áreas. **El serial no es clave única** |
| Texto libre | Categorías, estados y lugares con variantes (`Equipo Biomedico`, `EquipoBioquimico`, `Funsiona`, `BOX 4/3`) |
| Lotes | Filas con cantidad >1 (sillas, botes de basura) |
| Fechas distintas | Hojas con 16/08/2023, 25/08/2023 y 12/12/2023 |

El Excel no es un requisito de migración: ilustra lo que se quiere eliminar, que es **tener que digitar todo a mano**. Detalle en [`docs/06-importacion-excel.md`](../../docs/06-importacion-excel.md).

---

## 3. Restricciones

| Restricción | Consecuencia |
|---|---|
| Equipo reducido | Un solo cliente web, un monolito, sin colas ni microservicios |
| Un solo cliente real (una clínica) | Multi-tenant barato (`tenant_id` + filtro central); sin pantallas de alta de tenants |
| Internet estable en la clínica | MVP solo online; offline se reevalúa con evidencia del piloto |
| Datos sensibles de la clínica | `datos/` y Excel nunca se versionan; fixtures anonimizadas |
| Decisiones pendientes | Se resuelven en [`docs/05`](../../docs/05-preguntas-abiertas.md); lo no decidido se marca `[PENDIENTE]` |

---

## 4. Lo que ya se decidió y por qué

| Decisión | Motivo | ADR |
|---|---|---|
| Web única con React, Tailwind y shadcn/ui | Un cliente, sin tiendas de apps, despliegue inmediato | ADR-001 |
| Solo online | Local-first es la parte más cara y riesgosa; la clínica tiene red estable | ADR-002 |
| Verificación con precio copiado y totales congelados | El informe debe ser reproducible aunque el precio cambie | ADR-003 |
| Arnés local y autoría humana | Las instrucciones y el estado de las sesiones no son producto | ADR-004 |

---

## 5. Brecha

Lo que falta para empezar a construir: responder P1/P2/P10, aceptar los ADR, aprobar la spec 001 y publicar el repositorio. Nada de esto requiere código.
