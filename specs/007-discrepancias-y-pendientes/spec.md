# Spec 007 — Discrepancias y pendientes

> **Estado:** Implementada (T1–T8, 2026-11-14). Aprobada (G1–G3, 2026-11-14) con Q1–Q4 en la opción recomendada. Depende de la 006 (sesiones y verificación, hecha). Módulos M5 (CU-VER-02, CU-VER-04) y M6 (CU-DIS-01, CU-DIS-02) de `docs/07`; cierra P14 y P16. Plan en `plan.md`, tareas en `tasks.md`.

## Problema

Con la 006 el personal ya cuenta y registra dónde vio cada activo, pero esa información no se usa: un activo encontrado en otra sala queda como una observación que nadie revisa, y el contador no sabe qué le falta por contar en su sala. Esta spec cierra ese ciclo: el admin revisa las diferencias de ubicación y decide (mover el activo a donde se vio o descartar la diferencia), y ambos roles ven, por ubicación, qué activos faltan por verificar antes del cierre (008).

## Usuarios

- **Admin:** revisa las discrepancias de una sesión, las aplica (una o varias) o las descarta; ve los pendientes por activo.
- **Contador:** ve en el teléfono los activos que faltan por contar en cada sala, sin precios, y abre cualquiera con un toque.

## Alcance

- **Incluye:** lista de discrepancias de una sesión con la verificación vigente R3 de cada activo (CU-DIS-01); aplicar (mueve el activo a la ubicación encontrada y escribe `ubicacion_cambiada` con la verificación, CU-DIS-02), una o varias a la vez (Q3); descartar (Q2); aviso de desfase cuando el activo ya se movió por otra vía; estados derivados (pendiente, desfasada, aplicada, descartada) sin tocar la sesión ni la verificación (inmutables); lista de pendientes por activo y por ubicación (CU-VER-04) para ambos roles; pantallas `/admin/discrepancias`, enlaces desde el detalle de la sesión y `/contar/pendientes` real.
- **No incluye:** cerrar la sesión ni el informe (008); marca "buscado y no hallado" (Q4: no existe; un pendiente es solo la falta de verificación, P16); discrepancias de categoría o de estado físico (solo ubicación, R6).

## Requisitos (EARS)

1. **R1 Ver discrepancias (CU-DIS-01).** El admin debe poder listar, para una sesión, los activos cuya verificación vigente (mayor `seq`, R3) tiene ubicación encontrada distinta de la esperada, con activo, esperada, encontrada, ubicación actual, quién y cuándo, y su estado: **pendiente** (el activo sigue en la esperada), **desfasada** (ya está en otra ubicación que no es la encontrada), **aplicada** o **descartada**. Una verificación posterior en la ubicación esperada hace desaparecer la discrepancia.
2. **R2 Aplicar (CU-DIS-02).** Cuando el admin aplique una discrepancia pendiente, el sistema debe mover el activo a la ubicación encontrada (sala o box activos, D1) y escribir `ubicacion_cambiada` con `{antes, despues}`, la sesión y la verificación, en una transacción. Nunca modifica la verificación ni la sesión.
3. **R3 Desfase.** Si el activo ya no está en la ubicación esperada, el sistema no debe aplicarla sin confirmación explícita (`desfasada`); con confirmación, la aplica desde la ubicación actual.
4. **R4 Una sola resolución.** Cada discrepancia se resuelve como mucho una vez (aplicada o descartada), también ante dos admins a la vez; la base lo garantiza.
5. **R5 Descartar (Q2).** El admin debe poder descartar una discrepancia (el activo no se mueve) y queda en el historial del activo con quién y cuándo.
6. **R6 Varias a la vez (Q3).** El admin debe poder aplicar o descartar varias seleccionadas en una sola acción; cada una se resuelve por separado y el resultado dice cuáles se aplicaron y cuáles no y por qué.
7. **R7 Sesión cerrada (Q1).** Las discrepancias de una sesión cerrada se pueden aplicar o descartar: el cambio recae en el activo, el informe congelado no cambia (ADR-003; lo encontrado usa `ubicacion_esperada_id`, P20).
8. **R8 Pendientes (CU-VER-04).** Ambos roles deben poder listar, por ubicación vigente, los activos `activo` o `en_reparacion` sin verificación en la sesión, con la marca "en reparación", paginados y sin precios.
9. **R9 Solo admin.** Ver, aplicar y descartar discrepancias es solo del admin (Q4); el contador recibe `403`.

## Criterios de aceptación

- A1: migración `0010`: tipo de evento `discrepancia_descartada` e índice único parcial que impide dos resoluciones de la misma verificación (`ubicacion_cambiada` o `discrepancia_descartada` con el mismo `verificacion_id`); `docs/03` actualizado.
- A2: pruebas de API: lista con los cuatro estados; la R3 manda (verificar de nuevo en la esperada la quita); aplicar mueve y deja el evento con la verificación; desfase sin confirmar no aplica y con confirmar sí; ubicación encontrada ya inactiva `ubicacion_invalida`; dado de baja no se aplica; dos aplicaciones a la vez dejan una; descartar; lote con resultados por elemento; sesión cerrada también; pendientes por ubicación con la marca en reparación; contador `403` en discrepancias y **sin precios** en pendientes.
- A3: contrato OpenAPI de los endpoints nuevos con sus respuestas reales validadas.
- A4: navegador real (375 y 1440 px): el contador ve sus pendientes y abre uno; verifica uno en otra sala; el admin lo ve en discrepancias, aplica varias, descarta una y confirma un desfase; el historial muestra el movimiento por discrepancia; sin desbordes, consola limpia, axe sin hallazgos.

## Decisiones ya tomadas

R3 (la verificación de mayor `seq` es la vigente), R6 (una ubicación distinta es observación hasta que el admin la aplique), P20 (el informe usa la ubicación esperada para lo encontrado: aplicar no cambia el informe), D1 (sala o box activos), la verificación y la sesión son inmutables, P13 (sin precios al contador).

## Riesgos

- Aplicar en lote muchas a la vez: cada una en su propio savepoint, con tope de 100 por petición.
- El admin aplica una discrepancia vieja de una sesión cerrada cuando el activo ya se movió: el desfase lo detecta y pide confirmar.

## Decisiones de G1 (humano, 2026-11-14)

| Pregunta | Decisión |
|---|---|
| Q1 Sesión cerrada | Se aplica y descarta en sesiones abiertas y cerradas; el cambio va al activo y el informe no cambia (cierra P14 en ese punto). |
| Q2 Descartar | Sí, con evento `discrepancia_descartada` en el historial del activo. |
| Q3 Varias a la vez | Sí: una o varias seleccionadas, cada una resuelta aparte con su resultado. |
| Q4 Quién ve y marca | Solo el admin ve discrepancias; el contador ve sus pendientes. Sin marca "buscado y no hallado" (cierra P16). |

## Opciones que se presentaron en G1

| Pregunta | Opciones | Recomendación |
|---|---|---|
| Q1 ¿Aplicar en una sesión cerrada? (P14) | A: sí, abiertas y cerradas; el cambio va al activo y el informe no cambia. B: solo mientras está abierta. | **A.** Lo normal es revisar después de cerrar; el informe ya está congelado con la ubicación esperada (P20). |
| Q2 ¿Descartar? (P14) | A: sí, con evento `discrepancia_descartada` en el historial del activo (sale de la lista). B: no; queda pendiente hasta aplicarla. | **A.** Hay diferencias que no son reales (el equipo estaba de paso); sin descartar, la lista nunca se vacía. |
| Q3 ¿Varias a la vez? (P14) | A: una o varias seleccionadas; cada una se resuelve aparte y se informa el resultado. B: solo de a una. | **A.** Tras un conteo grande son decenas; de a una es lento. |
| Q4 ¿Quién ve discrepancias y "buscado y no hallado"? (P16) | A: solo el admin ve discrepancias; el contador ve sus pendientes. Sin marca "buscado y no hallado": un pendiente es la falta de verificación. B: el contador también ve discrepancias; agregar la marca. | **A.** Decidir dónde está un activo es del admin; la marca no cambia el informe y agrega un toque por activo. |
