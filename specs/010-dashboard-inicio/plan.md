# Plan 010 — Dashboard (Inicio)

> **Estado:** Aprobado (G1–G3, 2026-11-15) con Q1–Q3 en la opción recomendada (`spec.md`).

## 1. Enfoque

Tres endpoints nuevos de solo lectura (indicadores, actividad, evolución); las gráficas reutilizan `GET /valor-actual` (008). Cada parte del Inicio es una consulta aparte en la web: si una falla, solo esa parte muestra el error (R7). Primero el backend con sus pruebas de igualdad y de «sin dinero para el contador»; después la web parte por parte. Sin migraciones.

## 2. Backend (T1–T3, blueprint `inicio`)

- **`GET /inicio`** (ambos roles; `app/inicio/indicadores.py`). Siempre: `activos_hoy {unidades, en_reparacion}` (R7) y `sesion_abierta {id, nombre, fecha_corte, avance {total, verificados, pendientes, porcentaje}} | null` (mismo cálculo que el detalle de la sesión, `service.avance`). Solo admin (claves ausentes para el contador, no `null`): `valor_actual {total, unidades, calculado_en}` (de `valor.valor_actual`), `discrepancias_por_resolver` (de `discrepancias.listar` por resolver de la sesión abierta y de las cerradas con pendientes, como la pantalla de la 007), `danados {en_reparacion, danados, sesion {id, nombre} | null}` (P26) y `ultimo_informe {sesion, totales} | null` (lee `sesion_conteo` de la última cerrada `tipo=conteo` con `cierre.informe`, solo totales).
- **`GET /inicio/actividad?antes_de=<seq>`** (ambos roles; `app/inicio/actividad.py`): 20 eventos del tenant por `seq` descendente con `{seq, tipo, ocurrido_en, autor, activo {id, codigo, nombre}, datos}`; al contador se le omiten `precio_cambiado` en la consulta y se le quitan las claves de precio con el mismo `_sin_precio` del historial (005), que pasa a un módulo común.
- **`GET /inicio/evolucion`** (solo admin; `app/inicio/evolucion.py`): las sesiones cerradas `tipo=conteo` más recientes (máx. 12, P22) en orden cronológico, cada una con `{sesion {id, nombre, fecha_corte, cerrada_en}, total_registrado, unidades_registrado, unidades_encontrado, porcentaje_encontrado}`; `porcentaje_encontrado` como texto con un decimal (`"66.7"`, P24) calculado con `Decimal`; y `por_categoria`: por cada categoría (por `categoria_id`, con la etiqueta más reciente) sus puntos `{sesion_id, total_registrado, unidades_registrado}` solo donde existe fila en `sesion_desglose` (ausente ≠ cero).
- **Gráficas:** `GET /valor-actual` ya da `por_categoria` y `por_ubicacion` (Q2 A).
- **Contrato** de los tres endpoints y matriz de roles. **Pruebas** por endpoint: cifras exactas, vacíos, tenant, roles y un barrido de la respuesta al contador que falla si aparece `precio`, `valor`, `total_` o un número con formato de dinero.

## 3. Web (T4–T8)

- `lib/inicio.ts`: `useIndicadores`, `useActividad` (paginada con `antes_de`), `useEvolucion`; tipos del contrato.
- **Gráficas (Q1 A):** `components/app/Barras.tsx` — barras horizontales (valor por categoría/ubicación) y verticales (evolución) con CSS; cada gráfica es una `figure` con `figcaption` que nombra su fuente y una tabla equivalente (visible al pedirla y legible por lectores de pantalla). El ancho de cada barra es la proporción de la cifra del servidor respecto de la mayor (dibujar, no sumar).
- **`/admin` (Inicio):** tarjetas de indicadores (activos hoy, valor actual, avance o «Sin sesión abierta» con «Abrir sesión», discrepancias, dañados con su sesión fuente), último informe (`ThreeFiguresCard`, enlace al informe) o estado vacío, gráficas por categoría y por ubicación («Valor actual · no es el informe»), evolución (total registrado y % por conteo, y vista por categoría) y actividad reciente con «Ver más». Cada bloque con su carga, vacío y error con «Reintentar». Fuera la banda de maqueta y `useSimulacion` de esta pantalla.
- **`/contar` (Q3 A):** activos hoy (unidades) y actividad reciente sin precios junto al avance actual.

## 4. Verificación (T9)

Navegador real con dos sesiones cerradas y una abierta: cifras del Inicio contra el informe y el valor actual, evolución con dos puntos que coinciden con sus informes, contador sin dinero en ninguna respuesta, error aislado forzado en una parte, 375 y 1440 px, axe 0. Revisión de seguridad (roles, tenant, filtro de precios) y de dominio (fuentes rotuladas, sin mezcla, sin sumas en la web).

## 5. Riesgos

Ver `spec.md`.
