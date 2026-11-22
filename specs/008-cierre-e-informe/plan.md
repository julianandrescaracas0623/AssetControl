# Plan 008 — Cierre de sesión, informe y valor actual

> **Estado:** Aprobado (G1–G3, 2026-11-14) con Q1–Q3 en la opción recomendada (`spec.md`).

## 1. Enfoque

Primero la base, con la inmutabilidad de la sesión cerrada en un disparador. Después la función de dominio única (`universo`) con pruebas de cuadre, el cierre y el informe con su contrato, y al final la web. Sin dependencias nuevas.

## 2. Base de datos (migración `0011_cierre_e_informe`, T1)

**`sesion_conteo`:** `total_encontrado`, `total_no_encontrado`, `total_registrado` `numeric(14,2) NULL`, con:
- `CHECK ((estado = 'cerrada') = (total_registrado IS NOT NULL))`, totales `>= 0` y `total_registrado = total_encontrado + total_no_encontrado`.
- Disparador `sesion_conteo_inmutable` (`BEFORE UPDATE`, `SECURITY INVOKER`, `search_path` fijo): si `OLD.estado <> 'abierta'` → error; la única transición permitida es `abierta → cerrada`.
- `GRANT UPDATE (estado, cerrada_por, cerrada_en, total_encontrado, total_no_encontrado, total_registrado)` a la aplicación. Con eso puede tomar la fila con `FOR UPDATE`.

**`sesion_desglose`** (R9): `id uuid DEFAULT gen_random_uuid()`, `tenant_id`, `sesion_id`, `dimension` (`categoria`|`ubicacion`), `categoria_id`, `ubicacion_id`, `etiqueta text` (nombre de la categoría o ruta de la ubicación al cierre, Q3), los tres totales `numeric(14,2) >= 0` y las tres unidades `integer >= 0` (registrado = encontrado + no encontrado en ambos), `creado_en`. `CHECK` de dimensión; únicos parciales `(sesion_id, categoria_id) WHERE dimension='categoria'` y `(sesion_id, ubicacion_id) WHERE dimension='ubicacion'`; FK compuestas a sesión, categoría y ubicación.

**`sesion_no_encontrado`** (R9a): `id`, `tenant_id`, `sesion_id`, `activo_id`, `codigo`, `nombre`, `categoria_id`, `categoria_nombre`, `ubicacion_id`, `ubicacion_ruta` (Q3), `precio numeric(14,2) >= 0`, `en_reparacion boolean`, `creado_en`; único `(sesion_id, activo_id)`; FK compuestas.

**Ambas:** RLS forzada, solo `INSERT` y `SELECT`, y un disparador que exige que la sesión ya esté `cerrada` al insertar: el cierre primero cierra la sesión y después inserta, en la misma transacción.

## 3. Dominio y API (T2–T3)

- **`app/conteo/cierre.py` · `universo(session, sesion_id)`** — **la única función que calcula U** (R8): una consulta con `UNION ALL` de (a) la verificación vigente de cada activo (`row_number()` por `seq`) con su foto y (b) los activos `activo`/`en_reparacion` sin verificación con sus valores vigentes, más el nombre de la categoría y la ruta de la ubicación. Devuelve filas `(activo, condición, precio, categoría, ubicación, etiquetas, en_reparacion, código, nombre)`. `agregar(filas)` produce, con `Decimal`, las tres cifras y el desglose por dimensión.
- **`POST /sesiones/{id}/cerrar`** (admin): en una transacción: candado consultivo **exclusivo** de la sesión (espera a las verificaciones en curso) → `SELECT … FOR UPDATE` de la sesión → si ya está cerrada devuelve su informe (`200`, Q1) → `universo` → `UPDATE` a `cerrada` con los totales → `INSERT` del desglose y de los no encontrados → devuelve el informe (`200`). Para el contador, `403`.
- **`GET /sesiones/{id}/informe`** (admin): lee la sesión y las dos tablas; abierta → `409 sesion_abierta`.
- **`GET /valor-actual`** (admin): consulta en vivo de `activo` (`activo` + `en_reparacion`), con totales, unidades, cuánto está en reparación y desglose por categoría y ubicación con los nombres vigentes. **Nunca** lee el desglose de una sesión ni se mezcla con él.
- **Errores nuevos:** `sesion_abierta` (409).
- **Pruebas de cuadre:** un caso armado a mano con cada regla de R4 y un conjunto al azar (semilla fija, unos 120 activos con precios con centavos, verificaciones repetidas, bajas, reparaciones, movimientos y discrepancias aplicadas): por dimensión, filas = cifras; cada activo de U una vez por dimensión; lista = no encontrado; las sumas en Python con `Decimal` coinciden con `SUM` en SQL.

## 4. Web (T4–T6)

- **T4 Cerrar:** en el detalle de una sesión abierta, "Cerrar sesión" abre una confirmación con lo que quedará como no encontrado (pendientes) y las discrepancias por resolver (se pueden resolver después, Q1 de la 007); al confirmar, abre el informe. Una sesión cerrada muestra "Ver informe" en vez del avance en vivo; la lista de sesiones enlaza las cerradas a su informe.
- **T5 Informe:** `/admin/sesiones/:id/informe` real (reemplaza la maqueta): tres cifras, corte, quién y cuándo cerró; desglose por categoría y por ubicación (COP y unidades, con el % encontrado por unidades) y la lista de no encontrados con "en reparación". Todo leído del servidor; la web no suma.
- **T6 Valor actual:** `/admin/valor` real, rotulado "No es un informe", con total, unidades, en reparación y desglose.

## 5. Verificación (T7)

Navegador real: verificar en el teléfono, cerrar con aviso, ver el informe y comprobar que cuadra; corregir un precio y mover un activo después y ver que el informe no cambia mientras el valor actual sí; el contador recibe "La sesión se cerró"; 375 y 1440 px, consola y axe. Revisión de seguridad (disparadores, permisos, precio solo admin) y de dominio (R4, R8, R9, R9a, ADR-003).

## 6. Dependencias nuevas

Ninguna.
