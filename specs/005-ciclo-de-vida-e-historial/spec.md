# Spec 005 — Ciclo de vida e historial del activo

> **Estado:** Aprobada (G1–G3, 2026-11-14) con Q1–Q3 en la opción recomendada. Depende de la 004 (activos: alta por escaneo, hecha). Módulo M3 (resto): CU-CAT-05 a CU-CAT-08; M8: CU-HIS-01 (eventos de catálogo) de `docs/07`. Plan en `plan.md`, tareas en `tasks.md`.

## Problema

Con la 004 los activos se registran, pero quedan fijos: un precio mal tecleado por un contador (P11) no se corrige, un equipo que cambia de consultorio no se mueve, uno que va a mantenimiento no se marca y uno que se pierde o se desecha no sale del valor total. Tampoco se ve qué le pasó a un activo ni quién lo cambió. Sin esto el conteo (006) compararía contra un catálogo que no refleja la clínica.

## Usuarios

- **Admin:** edita, mueve, cambia el estado y da de baja desde la ficha o la lista; ve el historial completo con precios.
- **Contador:** ve el historial de un activo desde el teléfono, sin precios ni eventos de precio (P13). No escribe en el catálogo existente.

## Alcance

- **Incluye:** editar con concurrencia optimista (`If-Match` con `row_version`, `412` si cambió); mover (una ubicación vigente, misma regla D1); cambiar estado `activo` ↔ `en_reparacion`; dar de baja con motivo (Q2); reactivar un dado de baja (Q1); un evento por cada cambio en la misma transacción; historial (línea de tiempo por `seq`) para ambos roles con el filtrado de precio en el servidor; filtro por ubicación en la lista de activos y enlace desde el aviso `tiene_activos` (D2) para encontrar los activos que hay que mover.
- **No incluye:** mover o dar de baja varios activos a la vez (lote), "mover y desactivar la ubicación en un paso", sesiones y verificación (006), discrepancias y su `ubicacion_cambiada` desde un conteo (007), eventos del tenant en el Inicio (CU-DSH, spec del dashboard), fotos, importar (012).

## Requisitos (EARS)

1. **R1 Editar (CU-CAT-05).** Cuando el admin guarde cambios de un activo, el sistema debe aceptar nombre (H-3), categoría, precio de compra (Q2 de la 004), serial, marca, modelo, subtipo y fecha de compra (los mismos campos que el alta); nunca `codigo` (`400 codigo_inmutable`). Un campo opcional vacío se borra.
2. **R2 Concurrencia.** Toda escritura sobre un activo existente (editar, mover, estado, baja, reactivar) debe traer `If-Match` con su `row_version`: sin él `428 falta_version`; si no coincide, `412 version_desactualizada` con el activo vigente, sin guardar nada. Cada escritura con cambios incrementa `row_version` una vez.
3. **R3 Eventos.** Cada cambio debe escribir su evento en la misma transacción, con autor y `{antes, despues}`: `precio_cambiado`, `categoria_cambiada`, `datos_cambiados` (los demás campos, Q3), `ubicacion_cambiada`, `estado_cambiado`, `dado_de_baja`. Guardar sin cambios no escribe evento ni cambia la versión.
4. **R4 Mover (CU-CAT-06).** Cuando el admin mueva un activo, el sistema debe aceptar solo una sala o un box activos de su tenant (D1, `400 ubicacion_invalida`).
5. **R5 Estado (CU-CAT-07).** El admin debe poder pasar un activo de `activo` a `en_reparacion` y de vuelta; un `en_reparacion` sigue contando en el valor y en el universo del cierre (P15, E2).
6. **R6 Baja (CU-CAT-08, Q2).** Cuando el admin dé de baja, el sistema debe exigir un motivo, poner `estado = dado_de_baja` y escribir `dado_de_baja` con el motivo. Desde ese momento el activo sale del valor en tiempo real y de "Activos hoy" (R7 de `docs/03`) y no se podrá verificar (R5a, en la 006).
7. **R7 Dado de baja (Q1).** Mientras un activo esté dado de baja, el sistema debe rechazar editarlo, moverlo o cambiar su estado (`409 activo_dado_de_baja`); solo se permite reactivarlo con motivo, que vuelve a `activo` y escribe `estado_cambiado`.
8. **R8 Historial (CU-HIS-01).** Ambos roles deben poder ver la línea de tiempo de un activo ordenada por `seq` (la más reciente primero, por páginas), con autor, fecha y antes/después. Al contador el servidor le omite los eventos `precio_cambiado` y quita todo precio de los demás (`creado`, `importado`).
9. **R9 Solo admin.** Editar, mover, cambiar estado, dar de baja y reactivar son solo del admin; el contador recibe `403`.
10. **R10 Encontrar para mover (D2).** La lista de activos debe filtrar por ubicación, y el aviso `tiene_activos` al desactivar una ubicación debe llevar a esa lista filtrada.

## Criterios de aceptación

- A1: migración `0008` con `UPDATE` por columna en `activo` (sin `codigo`, `tenant_id`, `creado_por`, `creado_en`) y el tipo de evento nuevo; el catálogo de RLS y de permisos lo comprueba; `activo_evento` sigue inmutable.
- A2: pruebas de API: cada cambio deja exactamente su evento con antes/después y autor; `412` con dos ediciones sobre la misma versión (la segunda no guarda nada); `428` sin `If-Match`; `codigo` rechazado; sede o ubicación inactiva rechazada al mover; dado de baja bloquea todo salvo reactivar; contador `403` en cada escritura; **el historial y todas las respuestas al contador no contienen precio**.
- A3: la lista con pestañas refleja la baja y el estado al instante; una prueba de dominio deja fijada la regla para el valor en tiempo real (R7 de `docs/03`): dado de baja fuera, en reparación dentro.
- A4: contrato OpenAPI de los endpoints nuevos y cambiados, con sus respuestas reales validadas.
- A5: navegador real (375 y 1440 px): editar con un conflicto simulado (la app avisa y conserva lo escrito para reaplicar), mover, en reparación y de vuelta, dar de baja y reactivar desde la ficha; historial del admin con precios y del contador sin precios; desactivar una ubicación con activos lleva a la lista filtrada; sin desbordes, sin errores de consola y sin violaciones axe.

## Decisiones ya tomadas

- `codigo` inmutable (R8 de `docs/03`); ediciones online con `If-Match` y `412` (CU-CAT-05); una sola ubicación vigente (CU-CAT-06); D1 (sede sin activos) también al mover; P13 (precio solo admin, filtrado en el servidor) también en el historial; P15/E2 (en reparación cuenta, dado de baja no). Un cambio de precio no altera sesiones cerradas ni `precio_al_contar` (ADR-003); hoy aún no hay sesiones.

## Riesgos

- Un admin corrige el precio mientras alguien cuenta: con la 006 la verificación congela `precio_al_contar`, así que no se mezcla; la 008 fija la vista consistente del cierre.
- Dos admins editan a la vez: el `412` evita que uno pise al otro sin saberlo.
- Una baja por error saca el activo del valor total: se mitiga con confirmación, motivo y reactivar (Q1).

## Decisiones de G1 (humano, 2026-11-14)

| Pregunta | Decisión |
|---|---|
| Q1 Deshacer una baja | Sí: el admin reactiva con motivo (vuelve a `activo`, evento `estado_cambiado`); mientras está de baja es de solo lectura. Motivos al reactivar: encontrado, baja por error u otro (con nota). |
| Q2 Motivo de baja | Lista corta (dañado sin reparación, perdido, vendido o donado, obsoleto, otro) y nota opcional, obligatoria con "otro". |
| Q3 Evento de los demás campos | Evento nuevo `datos_cambiados` con antes/después por campo. |

## Opciones que se presentaron en G1

| Pregunta | Opciones | Recomendación |
|---|---|---|
| Q1 ¿Se puede deshacer una baja? | A: sí, el admin reactiva con motivo (vuelve a `activo`, evento `estado_cambiado`); mientras está de baja es de solo lectura. B: no, la baja es definitiva. | **A.** En una clínica un equipo dado de baja por "perdido" aparece en el siguiente conteo; sin reactivar, su sticker queda inutilizable. Las sesiones cerradas no cambian (ADR-003). |
| Q2 ¿Motivo de baja? | A: lista corta (dañado sin reparación, perdido, vendido o donado, obsoleto, otro) y nota opcional, obligatoria si es "otro". B: texto libre obligatorio. C: sin motivo. | **A.** Cero digitación en lo común y permite contar bajas por motivo en informes futuros. |
| Q3 ¿Evento para nombre, marca, serial y demás? | A: evento nuevo `datos_cambiados` con antes/después por campo (cambia la lista de tipos de `docs/03`). B: sin evento para esos campos. | **A.** El historial debe decir quién cambió qué (CU-HIS-01: "cada cambio muestra antes/después y autor"). |
