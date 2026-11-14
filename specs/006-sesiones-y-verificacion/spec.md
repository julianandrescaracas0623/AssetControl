# Spec 006 — Sesiones de conteo y verificación

> **Estado:** Aprobada (G1–G3, 2026-11-14) con Q1–Q4 en la opción recomendada. Depende de la 005 (ciclo de vida e historial, hecha). Módulos M4 (CU-SES-01, 02, 04) y M5 (CU-VER-01, 03, 05, 06) de `docs/07`. Plan en `plan.md`, tareas en `tasks.md`.

## Problema

El catálogo ya existe y se mantiene, pero contar sigue siendo una maqueta: el teléfono "verifica" sin guardar nada. Esta spec hace el conteo real: el admin abre una sesión, el personal escanea cada sticker y confirma con un toque, el servidor guarda la verificación con una foto del precio, la categoría y la ubicación de ese momento (ADR-003), y un corte de red nunca duplica ni pierde en silencio. Es la base del informe (008) y de las discrepancias (007).

## Usuarios

- **Admin:** abre la sesión con nombre y fecha de corte; ve el avance por ubicación; también puede verificar.
- **Contador:** elige la sala donde está contando, escanea y confirma; ve su avance sin precios.

## Alcance

- **Incluye:** tablas `sesion_conteo` y `verificacion` (migración `0009`); abrir una sesión (Q1); ver la sesión abierta y su avance por ubicación (CU-SES-02); verificar idempotente con UUID del cliente (R2), con estado físico (Q2), nota opcional y ubicación encontrada (Q4); rechazo `409 sesion_cerrada` (R5) y `409 activo_dado_de_baja` (R5a); verificar otra vez el mismo activo (R3: la de mayor `seq` gana); evento `verificado` en el historial; pantallas reales de `/admin/sesiones`, Inicio del conteo, Verificar y su resultado (confirmado, no confirmado con reintento, sesión cerrada).
- **No incluye:** cerrar la sesión, totales, desglose e informe (008); lista de discrepancias y aplicarlas, lista de pendientes por activo (007); actividad reciente y cifras del Inicio (010); fotos (P18); sesión de importación (012).

## Requisitos (EARS)

1. **R1 Abrir (CU-SES-01, Q1).** Cuando el admin abra una sesión con nombre (regla H-3) y fecha de corte, el sistema debe crearla `abierta`, de tipo `conteo`, con quién y cuándo la abrió; si ya hay una abierta en el tenant, `409 sesion_abierta_existente`. El contador recibe `403`.
2. **R2 Sesión abierta.** Ambos roles deben poder consultar la sesión abierta (o saber que no hay ninguna) y el listado de sesiones.
3. **R3 Avance (CU-SES-02).** El sistema debe dar, por ubicación vigente del activo, cuántos activos `activo` o `en_reparacion` hay, cuántos tienen verificación en la sesión y cuántos faltan, y el total. Es información de trabajo, sin precios, y no es el informe.
4. **R4 Verificar (CU-VER-01, 03).** Cuando alguien confirme un activo en la sesión abierta, el sistema debe guardar una `verificacion` con su `id` del cliente, el activo, la ubicación encontrada (sala o box activos, Q4), el estado físico (Q2), la nota opcional, quién y la hora del cliente (informativa), y copiar del activo en ese momento `precio_al_contar`, `categoria_al_contar` y `ubicacion_esperada_id` (ADR-003); escribir el evento `verificado` en la misma transacción.
5. **R5 Idempotencia (R2 de `docs/03`, CU-VER-06, Q3).** Cuando llegue otra vez una verificación con el mismo `id`, el sistema debe devolver la ya guardada sin duplicar, aunque la sesión se haya cerrado después; un `id` usado para otro activo o sesión es `400`.
6. **R6 Sesión cerrada (R5, CU-SES-04).** Mientras la sesión no esté abierta, el sistema debe rechazar una verificación nueva con `409 sesion_cerrada` sin guardar nada.
7. **R7 Dado de baja (R5a).** El sistema debe rechazar verificar un activo `dado_de_baja` con `409 activo_dado_de_baja`.
8. **R8 Verificar de nuevo (R3 de `docs/03`).** Cuando el activo ya tenga verificación en la sesión, el sistema debe avisarlo (quién, cuándo, dónde) antes de confirmar y permitir una nueva; las dos se conservan.
9. **R9 Precio por rol (P13).** Ninguna respuesta al contador debe incluir `precio_al_contar` ni otro precio; el admin ve el precio de referencia, no editable.
10. **R10 Conteo en el teléfono.** El contador elige la sala o el box donde está contando (se recuerda en la pestaña); escanear un activo existente con sesión abierta muestra la verificación con ubicación encontrada preseleccionada y estado `ok`; un toque confirma y la cámara queda lista para el siguiente. Sin respuesta del servidor: "No se pudo confirmar" con reintento del mismo `id` (sin cola ni offline, ADR-002). Sin sesión abierta, escanear solo consulta.

## Criterios de aceptación

- A1: migración `0009` con `sesion_conteo` y `verificacion`: RLS forzada, `GRANT` por columna, `verificacion` solo `INSERT` y `SELECT` (inmutable), una sola sesión `conteo` abierta por tenant (índice único parcial), FK compuestas, y las FK de `activo_evento.sesion_id` y `verificacion_id`; catálogo de RLS ampliado.
- A2: pruebas de API: abrir (y la segunda `409`), verificar (`201`), reintento con el mismo `id` (`200`, una sola fila) también tras cerrar, `409 sesion_cerrada`, `409 activo_dado_de_baja`, ubicación encontrada inválida, activo o sesión de otro tenant `404`, dos verificaciones del mismo activo (avance cuenta una), avance por ubicación, copia de precio, categoría y ubicación esperada aunque el activo cambie después, evento `verificado`; **ninguna respuesta al contador contiene precio**.
- A3: contrato OpenAPI de los endpoints nuevos con sus respuestas reales validadas.
- A4: navegador real (375 y 1440 px): el admin abre una sesión; el contador elige sala, escanea, confirma, ve el avance; corte de red simulado → "No se pudo confirmar" → reintentar no duplica; sesión cerrada mientras cuenta → mensaje sin reintento; dado de baja → no se verifica; sin desbordes, consola limpia y axe sin hallazgos.

## Decisiones ya tomadas

R2, R3, R5, R5a y ADR-003 de `docs/03`; P13 (precio solo admin, en el servidor); P15 (en reparación se verifica y cuenta); la ubicación encontrada distinta es una **observación**: no mueve el activo (R6 de `docs/03`); solo online, sin cola (ADR-002).

## Riesgos

- Cerrar mientras alguien verifica: la verificación toma un candado consultivo compartido de la sesión; el cierre (008) tomará el mismo candado exclusivo, así que cada verificación queda entera antes o después del cierre (ajuste de T3; probado con dos conexiones).
- Un admin cambia el precio mientras se cuenta: lo ya verificado guarda su `precio_al_contar`; el informe no se mueve (ADR-003).
- La sala de trabajo mal elegida genera discrepancias falsas: la sala se ve siempre en la cabecera y se cambia en un toque.

## Decisiones de G1 (humano, 2026-11-14)

| Pregunta | Decisión |
|---|---|
| Q1 Abrir | Solo el admin; una sesión de conteo abierta por clínica (cierra P12). |
| Q2 Estado físico | `ok` y `dañado`, más nota opcional de hasta 120 caracteres (cierra P8 en lo que toca a estados). |
| Q3 Reintento tardío | La verificación guardada antes del cierre se devuelve (`200`) al reintentar con el mismo `id`; R2 tiene precedencia sobre R5 solo en ese caso. |
| Q4 Ubicación encontrada | Obligatoria: la sala o box de trabajo, preseleccionada; "Está en otra ubicación" la cambia para esa verificación (observación). |

## Opciones que se presentaron en G1

| Pregunta | Opciones | Recomendación |
|---|---|---|
| Q1 ¿Quién abre y cuántas a la vez? (P12) | A: solo el admin; una sesión de conteo abierta por clínica. B: varias abiertas a la vez. | **A.** Un solo conteo vigente evita que un escaneo caiga en la sesión equivocada; el admin ya es quien cierra (P5). |
| Q2 Estado físico (P8) | A: `ok` y `dañado`, más una nota opcional de hasta 120 caracteres. B: lista más larga. | **A.** Un toque; el detalle va en la nota. Pasar a reparación sigue siendo del admin (CU-VER-03). |
| Q3 Reintento tardío (CU-SES-04) | A: si la verificación ya se había guardado antes del cierre, el reintento con el mismo `id` la devuelve (`200`). B: `409 sesion_cerrada` siempre. | **A.** Se guardó antes del cierre y cuenta en el informe; responder 409 haría creer que se perdió. |
| Q4 Ubicación encontrada | A: obligatoria: la sala o box de trabajo que el contador elige al empezar, preseleccionada en cada verificación; "Está en otra ubicación" la cambia para esa verificación y se guarda como observación (la lista de discrepancias llega en la 007). B: opcional; si falta, se asume la esperada. | **A.** Saber dónde se vio cada activo es lo que hace útil el conteo, y la preselección mantiene el "un toque". |
