# Orquestación de AssetControl

> **Versión:** 1.0 · 2026-11-09
> **Estado:** propuesta operativa para decisión del dueño
> **Fuente de verdad:** [`docs/`](../docs/) (alcance, arquitectura, modelo de datos, constitución y ADR)

---

## 1. Qué es esta carpeta

Convierte el diseño de AssetControl en una **operación ejecutable** por una persona y varios agentes de IA:

- Qué vamos a construir y en qué orden.
- Quién decide qué, con qué artefactos y con qué compuertas de calidad.
- Cómo se configuran Claude Code y Cursor para trabajar con contexto, permisos y límites.

No es documentación de producto (eso vive en `docs/`). Es el **sistema operativo del proyecto**.

---

## 2. Jerarquía de verdad

Si hay conflicto, manda en este orden:

1. [`docs/01-alcance-mvp.md`](../docs/01-alcance-mvp.md), [`docs/02-arquitectura.md`](../docs/02-arquitectura.md) y [`docs/03-modelo-datos.md`](../docs/03-modelo-datos.md).
2. [`docs/adr/`](../docs/adr/) — decisiones.
3. `specs/NNN-*/` — spec activa de la entrega.
4. [`05-decisiones/decisiones.md`](05-decisiones/decisiones.md) — resumen; el texto vinculante está en los ADR.
5. `MEMORY.md` — estado de la sesión (local).

**Regla:** si una decisión de producto, dominio o arquitectura cambia, primero se actualiza el documento y después se implementa.

---

## 3. Resumen ejecutivo

1. **El problema** es escribir todo a mano en un Excel de 23 hojas, con cada activo repetido en dos vistas (por ubicación y por categoría), totales que no cuadran ($4.787.206,38 de diferencia) y conteos que no dejan historial.
2. **La solución** es una web responsiva: el contador escanea el sticker de código de barras con la cámara del teléfono y confirma; el administrador gestiona catálogo, cierra sesiones y genera el informe de valor total.
3. **Simplicidad:** un cliente web, una API Flask, un PostgreSQL. Sin app nativa y sin local-first en el MVP.
4. **El número correcto es el producto:** las verificaciones son inmutables, las sesiones cerradas no cambian y los totales se congelan con el precio al momento de contar.
5. **Multi-tenant desde el inicio**, con un solo cliente (una clínica odontológica en Cartago) para validar.

---

## 4. Índice

| Documento | Para qué | Cuándo leerlo |
|---|---|---|
| [`00-contexto/01-estado-del-proyecto.md`](00-contexto/01-estado-del-proyecto.md) | Qué existe hoy, el Excel de origen y las restricciones | Antes de planear |
| [`00-contexto/02-metodo-curso-ia.md`](00-contexto/02-metodo-curso-ia.md) | El método (arnés + SDD + multiagente) y cómo se aplica aquí | Antes de usar los agentes |
| [`03-orquestacion/01-modelo-operativo.md`](03-orquestacion/01-modelo-operativo.md) | Roles, cadencia, artefactos y WIP | Al arrancar |
| [`03-orquestacion/02-agentes-y-prompts.md`](03-orquestacion/02-agentes-y-prompts.md) | Los seis agentes, sus límites y salidas | Al delegar |
| [`03-orquestacion/03-flujos-y-compuertas.md`](03-orquestacion/03-flujos-y-compuertas.md) | Flujos, compuertas, DoR/DoD y checklists | Antes de cada entrega |
| [`03-orquestacion/04-plan-de-ejecucion.md`](03-orquestacion/04-plan-de-ejecucion.md) | Fases, specs previstas y siguientes pasos | Cada lunes |
| [`03-orquestacion/05-harness-asistentes.md`](03-orquestacion/05-harness-asistentes.md) | `.claude/` y `.cursor/`: agentes, comandos, skills, permisos, hooks | Al abrir una sesión |
| [`04-plantillas/plantillas.md`](04-plantillas/plantillas.md) | PRD, ADR, runbook, PR, incidente, onboarding, piloto | Al crear artefactos |
| [`05-decisiones/decisiones.md`](05-decisiones/decisiones.md) | Decisiones tomadas y su ADR | Al cambiar el rumbo |

El producto se documenta en [`docs/`](../docs/): alcance, arquitectura, modelo de datos, metodología, preguntas abiertas y análisis del Excel.

---

## 5. Decisión central

**Que escribir menos sea la norma.**

```text
Contador escanea el sticker
        ↓
La web muestra el activo; confirma ubicación y estado
        ↓
Verificación inmutable, con precio copiado al momento de contar
        ↓
El admin cierra la sesión → totales congelados → informe PDF / Excel
```

El servidor calcula y decide; el cliente propone.

---

## 6. Lo que debemos poder demostrar

1. **Los números cuadran.** El informe de una sesión suma exactamente sus activos, con cero diferencias.
2. **No se duplica nada.** Cada verificación tiene UUID de cliente; reintentar no duplica.
3. **Hay historial.** Cada activo muestra quién lo verificó, cuándo y qué cambió.
4. **Se teclea poco.** Dar de alta un activo por escaneo toma menos de 30 segundos.
5. **Los datos están aislados.** Una clínica nunca ve los datos de otra.

---

## 7. Estado actual y siguientes 5 acciones

**Estado:** Fase 0. Documentos 01–06 y ADR 001–004 escritos (en estado `Propuesta`), orquestación y arneses listos, primera spec (`specs/001-fundacion-tecnica/`) escrita y pendiente de aprobación. No hay código de aplicación.

**Siguientes 5 acciones:**

1. Responder las preguntas abiertas que condicionan el modelo: P1 (unidad vs lote), P2 (qué suma el informe) y P10 (importar o partir de cero) en [`docs/05-preguntas-abiertas.md`](../docs/05-preguntas-abiertas.md).
2. Aceptar los ADR 001–004.
3. Aprobar `specs/001-fundacion-tecnica/spec.md`.
4. Elegir nombre, crear el repositorio remoto y publicar (los workflows de `.github/` se activan solos).
5. Ejecutar T1–T10, una tarea por sesión.

---

## 8. Convenciones

- Idioma: español. Nombres técnicos en inglés; entidades de dominio con el nombre del modelo de datos.
- Fechas: `YYYY-MM-DD`.
- Decisiones: `ADR-NNN`.
- Issues: `[área] verbo + resultado` (ej. `[backend] registrar verificación idempotente`).
- Ramas: `feat/`, `fix/`, `docs/`, `chore/`, `spike/`.
- Commits: `tipo(área): resultado` (ej. `feat(sessions): cerrar sesión con totales congelados`).
- Un PR = un slice vertical verificable.
- Ningún agente mergea a `main`. El humano aprueba.
- Ningún asistente (Claude, Cursor, Copilot) figura como autor ni coautor. El autor es el humano.
- El arnés de asistentes es local y no se publica (ADR-004).

---

## 9. Regla de oro

> Si no está en el alcance o en la spec, no se implementa.
> Si no tiene prueba, no se considera terminado.
> Si no pasa la compuerta de seguridad y tenant, no se despliega.
> Si un total no coincide con la suma de sus partes, no se entrega.
