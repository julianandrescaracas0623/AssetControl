# Spec 008 — Cierre de sesión, informe y valor actual

> **Estado:** Aprobada (G1–G3, 2026-11-14) con Q1–Q3 en la opción recomendada. Depende de la 007 (discrepancias y pendientes, hecha). Módulos M4 (CU-SES-03) y M7 (CU-INF-01, CU-INF-02) de `docs/07`; tablas `sesion_desglose` (R9) y `sesion_no_encontrado` (R9a). La exportación (CU-INF-03) es de la 009. Plan en `plan.md`, tareas en `tasks.md`.

## Problema

Contar ya funciona, pero el conteo no termina en nada: no se cierra y no hay informe. Es justo lo que falla en el Excel de hoy, donde el total no cuadra con la suma real (~$4,8 M de diferencia). Esta spec cierra la sesión con un cálculo único en el servidor que congela, en la misma transacción, las tres cifras (encontrado, no encontrado y total registrado), el desglose por categoría y por ubicación y la lista de no encontrados. El informe solo lee eso y cuadra con cero diferencias, aunque después cambien precios, categorías o ubicaciones. Aparte, rotulado como otra cosa, se ve el valor actual del inventario.

## Usuarios

- **Admin:** cierra la sesión (avisado de lo que falta), lee el informe congelado y consulta el valor actual.
- **Contador:** no cierra ni ve informes ni valor (P5, P13); al cerrarse, su verificación siguiente recibe "La sesión se cerró" (ya en la 006).

## Alcance

- **Incluye:** migración `0011` (totales y cierre en `sesion_conteo` con su regla de inmutabilidad en la base; tablas `sesion_desglose` y `sesion_no_encontrado`); una función de dominio que calcula el universo U una sola vez (R4, R8); cerrar (`POST /sesiones/{id}/cerrar`) con vista consistente y candado exclusivo de la sesión; informe (`GET /sesiones/{id}/informe`); valor actual (`GET /valor-actual`, R7); pantallas: cerrar desde el detalle de la sesión, informe real y "Valor actual".
- **No incluye:** exportar a PDF o Excel (009), Inicio con cifras y evolución (010), reabrir una sesión (nunca: R5), sesión de importación (012).

## Requisitos (EARS)

1. **R1 Universo (R4 de `docs/03`).** Al cerrar, el sistema debe calcular **una vez** la lista U = activos con verificación vigente (R3) en la sesión, en cualquier estado, ∪ activos `activo` o `en_reparacion` sin verificación. Encontrado: `precio_al_contar`, `categoria_al_contar` y `ubicacion_esperada_id` de su verificación. No encontrado: precio, categoría y ubicación vigentes. Los dados de baja sin verificación quedan fuera.
2. **R2 Congelar (R4, R9, R9a).** En la misma transacción, el sistema debe guardar las tres cifras en la sesión, una fila de desglose por categoría y una por ubicación (COP y unidades) y una fila por activo no encontrado (código, nombre, categoría, ubicación, precio y marca "en reparación"); todo sale de la lista U y ningún otro código recalcula.
3. **R3 Cuadre.** Para cada dimensión, la suma de sus filas debe ser igual a las tres cifras, con cero diferencias; cada activo de U cae en exactamente una fila por dimensión; la lista de no encontrados suma `total_no_encontrado` y coincide, por categoría y por ubicación, con el desglose.
4. **R4 Concurrencia.** El cierre debe tomar el candado exclusivo de la sesión (la verificación toma el compartido, 006) y leer U en una sola consulta: cada escritura concurrente (verificación, alta, cambio de precio, categoría, ubicación o estado, baja) queda entera dentro o entera fuera. Después del cierre, una verificación nueva recibe `409 sesion_cerrada`.
5. **R5 Inmutable (R5).** Una sesión cerrada no se modifica ni se reabre; la base lo impide. El desglose y la lista solo se insertan, una vez.
6. **R6 Cierre repetido (Q1).** Cerrar una sesión ya cerrada debe devolver su informe (`200`) sin volver a insertar nada.
7. **R7 Informe (CU-INF-01).** El admin debe poder leer, de una sesión cerrada, las tres cifras, fecha de corte, quién y cuándo cerró, el desglose por categoría y por ubicación con los nombres de ese momento (Q3) y la lista de no encontrados con la marca "en reparación", sin recalcular nada; de una abierta, `409 sesion_abierta`.
8. **R8 Valor actual (CU-INF-02, R7 de `docs/03`).** El admin debe poder ver el valor vigente del inventario (activos `activo` y `en_reparacion`; los dados de baja no) con unidades, cuánto está en reparación y desglose por categoría y ubicación, rotulado "Valor actual: no es un informe".
9. **R9 Solo admin.** Cerrar, informe y valor actual son solo del admin (P5, P13); el contador recibe `403`.
10. **R10 Cerrar en la web (Q2).** Antes de cerrar, la web debe mostrar cuántos activos quedarán como no encontrados y cuántas discrepancias siguen por resolver, y pedir confirmación; al cerrar, abre el informe.

## Criterios de aceptación

- A1: migración `0011`: columnas de totales con `CHECK` (cerrada ⇔ totales; registrado = encontrado + no encontrado), disparador que impide modificar una sesión cerrada, `sesion_desglose` y `sesion_no_encontrado` con RLS, `GRANT` solo de `INSERT`/`SELECT`, únicos parciales y FK compuestas; catálogo de RLS ampliado.
- A2: pruebas de dominio y API: todos los casos de R4 (verificado y luego dado de baja = encontrado; en reparación sin verificar = no encontrado con marca; dado de baja sin verificar fuera; verificado dos veces cuenta la última; precio, categoría o ubicación cambiados después de verificar no mueven lo encontrado); cuadre con cero diferencias en un conjunto grande al azar; el informe no cambia tras editar, mover o dar de baja después del cierre; cierre repetido sin reinsertar; verificación y edición concurrentes con el cierre; contador `403`.
- A3: contrato OpenAPI de los endpoints nuevos con sus respuestas reales validadas.
- A4: navegador real (375 y 1440 px): cerrar con aviso de pendientes y discrepancias, informe con cifras, desglose y no encontrados; un precio corregido después no cambia el informe; valor actual separado; el contador ve "La sesión se cerró"; sin desbordes, consola limpia y axe sin hallazgos.

## Decisiones ya tomadas

R3, R4, R5, R8, R9, R9a y R7 de `docs/03`; ADR-003 con su actualización del 2026-11-11; P5 (solo el admin cierra), P13 (precios solo admin), P15 y E2 (en reparación cuenta; dado de baja no), P20 y P21 (criterio simétrico), E1 (lista congelada). Dinero en `NUMERIC(14,2)`/`Decimal`/texto, nunca `float`.

**Nota:** la skill `asset-domain` del arnés aún describe `cantidad` por lotes y no encontrado solo para `activo`; `docs/03` (R8 sin cantidad, P15) es la fuente vigente y manda (jerarquía de `CLAUDE.md`). Conviene actualizar la skill en `.claude/` y `.cursor/`.

## Riesgos

- Un cálculo distinto en el informe y en el cierre rompería el cuadre: el informe solo lee filas; las pruebas de cuadre lo vigilan.
- Cerrar por error: la web confirma y muestra lo que falta; no se reabre (R5), por eso el aviso es explícito.
- Muchos activos: la lista U sale de una sola consulta y se agrega en el servidor con `Decimal`; para ~300 activos es trivial.

## Decisiones de G1 (humano, 2026-11-14)

| Pregunta | Decisión |
|---|---|
| Q1 Cierre repetido | Devuelve el informe ya congelado (`200`), sin reinsertar (cierra el pendiente de R4 y CU-SES-03). |
| Q2 Antes de cerrar | Aviso con pendientes y discrepancias por resolver y confirmación; sin vista previa (cierra el pendiente de CU-INF-01). |
| Q3 Nombres | Se congelan el nombre de la categoría y la ruta de la ubicación al cierre (cierra el pendiente de `sesion_desglose`). |

## Opciones que se presentaron en G1

| Pregunta | Opciones | Recomendación |
|---|---|---|
| Q1 Cerrar una sesión ya cerrada | A: devuelve su informe (`200`), sin reinsertar. B: `409`. | **A.** Si la respuesta del cierre se pierde, reintentar muestra el informe en vez de un error; nunca duplica. |
| Q2 Antes de cerrar | A: aviso con pendientes y discrepancias por resolver y confirmación; sin "vista previa" del informe. B: además, vista previa no definitiva de las cifras. | **A.** Una vista previa con cifras que luego cambian confunde; el valor actual ya existe rotulado aparte. |
| Q3 Nombres en el informe | A: congelar el nombre de la categoría y la ruta de la ubicación al cerrar, junto con las cifras. B: mostrar el nombre vigente. | **A.** Si después se renombra una sala, el informe de ayer debe leerse igual que el día del cierre. |
