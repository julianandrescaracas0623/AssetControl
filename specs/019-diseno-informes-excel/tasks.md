# Tareas 019 — Diseño de los Excel según las plantillas

Regla común (FT-1 a FT-4 de `spec.md`): el criterio de terminado de CADA tarea incluye fidelidad total en su alcance: ninguna propiedad medida omitida, cada una con fila en la matriz y prueba verde propiedad por propiedad contra la huella. Si algo no se puede reproducir con `xlsxwriter`, la tarea se detiene y se pregunta al humano (D-2). Una tarea a la vez; tests primero; sin migraciones, auth, roles ni dependencias nuevas. Q6–Q13 están cerradas por decisión del humano 2026-11-22 (ver `spec.md`). Todo lo omitido por decisión (Q7 lista duplicada del Resumen, Q11 hoja activa/selección/desplazamiento, Q13 metadatos invisibles) se registra en `matriz.md` con la decisión que lo respalda. Privacidad: `medicion-plantillas.md` e `informes/` contienen datos reales y no se versionan; en cada commit, `git add` con rutas explícitas y `git status --short` para confirmar que no entran. Dinero: `Decimal`, nunca `float`; «Por ubicación» y «Por categoría» escriben las cifras congeladas de `cierre.informe`.

## T1 — Huella, utilidad de comparación y sondas de `xlsxwriter` — HECHA (2026-11-22)
- Estado: completa. L1: `twoCellAnchor editAs="oneCell"` (Q13). L2–L7 y L9 se reproducen. L8 y las diferencias de paquete fuera de Q13: equivalentes aceptados por decisión del humano 2026-11-22 (ver `spec.md`, «Decisiones del humano tras las sondas de T1», y `matriz.md`); las sondas fijan cada diferencia, sin `xfail`. Fila 26: título del libro y `creator` «AssetControl»; `xlsxwriter` no permite omitir `lastModifiedBy` (siempre lo escribe igual que `author`); decisión del coordinator 2026-11-22: `creator` = `lastModifiedBy` = «AssetControl» (única opción coherente), CONFIRMADA salvo que el humano pida ambos vacíos.
- Resultado: ejecutable. Un extractor lee ambas plantillas de `informes/` (todas las hojas y todas las celdas con estilo) y genera `backend/tests/plantillas/activos.json` e `informe.json` (sin datos reales; marcadores para empresa, cifras y fechas) y `specs/019-diseno-informes-excel/matriz.md` (detalle por celda). Completa lo no medido: contenido de los `dxf`, `extLst` de las barras de datos, cuadrícula al imprimir, texto alternativo, propiedades del documento, rango de bordes de la fila 5, y confirma que `N` es negrita. Incluye la utilidad de comparación y la prueba de cobertura XML. Incluye una prueba de sondeo por cada punto L1–L10 de `spec.md` con un `.xlsx` mínimo generado por `xlsxwriter`. La sonda L1 decide el ancla: si `xlsxwriter` logra `oneCellAnchor`, se usa; si no, se acepta `twoCellAnchor editAs="oneCell"` con las mismas dimensiones visibles (Q13) y los metadatos invisibles no se comparan. Si cualquier OTRA sonda (L2–L9) falla, la tarea se detiene y devuelve la pregunta al `coordinator` (sin aproximaciones; cambiar de método exige decisión humana). `matriz.md` se genera con marcadores, sin valores reales.
- Archivos probables: `backend/tests/utils_xlsx_diseno.py`, `backend/tests/plantillas/activos.json`, `backend/tests/plantillas/informe.json`, `backend/tests/test_xlsx_diseno_utilidad.py`, `backend/tests/test_xlsx_sondas.py`, `specs/019-diseno-informes-excel/matriz.md`.
- Verificación: `cd backend && uv run pytest tests/test_xlsx_diseno_utilidad.py tests/test_xlsx_sondas.py -q` y `uv run ruff check .`; revisión de que los JSON no contienen NIT, teléfono, correo ni dirección reales (`Grep` de control).
- Dependencia: ninguna. Solo resta aquí confirmar L1 (qué ancla se usa).

## T2 — Módulo de estilo común y bloque de encabezado
- Resultado: constantes y funciones de dibujo comunes a ambos generadores: banda (fila 1), bloque de empresa con logo y marcadores de campos ausentes, cabecera de tabla, fila de datos, fila Total, formatos, pie, márgenes y página, con valores de la matriz (no calculados). Logo ajustado dentro de la caja de la hoja conservando proporción (Q10). Prueba por propiedad del bloque común contra la huella, con empresa sintética.
- Archivos probables: `backend/app/conteo/exportar_estilo.py`, `backend/app/activos/exportar_estilo.py` (si aplica), `backend/tests/test_exportar_estilo.py`.
- Verificación: `cd backend && uv run pytest tests/test_exportar_estilo.py -q` y `uv run ruff check .`
- Dependencia: T1.

## T3 — Excel del módulo de activos
- Resultado: `a_excel` de activos replica la plantilla A (bloque de encabezado con logo, NIT, teléfono, correo, dirección y fecha de exportación de la empresa vigente del tenant, omitiendo los campos ausentes (Q9), cabecera en fila 7, congelado, autofiltro, impresión, formatos y anchos); datos, orden de filas y columnas sin cambios; celdas vacías con borde.
- Archivos probables: `backend/app/activos/exportar.py`, `backend/app/activos/routes.py` (lectura de empresa y logo), `backend/tests/test_activos_exportar.py`, `backend/tests/test_exportar_api.py`, `backend/tests/test_roles.py`.
- Verificación: `cd backend && uv run pytest tests/test_activos_exportar.py tests/test_exportar_api.py tests/test_roles.py -q` y `uv run ruff check .`
- Dependencia: T2.

## T4 — Informe: hojas de lista («Todos los activos», por categoría, «No encontrados»)
- Resultado: las tres familias de hojas replican la plantilla B (bloque común, título y nota combinada, fila Total sobre la cabecera, cabecera, datos sin filas alternas, formato condicional de fila completa, columnas ocultas en «No encontrados», congelado, impresión 1 página de ancho × alto automático (Q12), tabla de Excel «Activos» y filtros conservados con el estilo de la plantilla (Q8)); contenido, totales y orden sin cambios; `nombres_de_hoja` con los dos reservados nuevos.
- Archivos probables: `backend/app/conteo/exportar.py`, `backend/tests/test_exportar_documento.py`, `backend/tests/test_exportar_api.py`.
- Verificación: `cd backend && uv run pytest tests/test_exportar_documento.py tests/test_exportar_api.py -q` y `uv run ruff check .`
- Dependencia: T2.

## T5 — Informe: «Por ubicación», «Por categoría», «Resumen» y orden del libro
- Resultado: hojas «Por ubicación» y «Por categoría» (mismas cifras congeladas de `cierre.informe` en `Decimal`, barras de datos, fila Total con fondo `DBEAFE`, ajuste 1×1; prueba con centavos no representables en `float`), «Resumen» con las 4 tarjetas y filas finales (nombre de sesión, quién cerró y cuándo, moneda, estado «Informe congelado», `NOTA`, `SIN_DETALLE`, `EMPRESA_VIGENTE`) sin la lista duplicada (Q7), ajuste 1×1; libro en el orden de la plantilla (Q6); hoja activa la primera, A1 (Q11); sesión antigua sin detalle sigue generando un libro válido.
- Archivos probables: `backend/app/conteo/exportar.py`, `backend/tests/test_exportar_documento.py`, `backend/tests/test_roles.py`.
- Verificación: `cd backend && uv run pytest tests/test_exportar_documento.py tests/test_roles.py -q` y `uv run ruff check .`
- Dependencia: T4.

## T6 — Validación
- Resultado: suite completa verde; `reviewer` y `domain-guardian` aprueban (totales congelados, `precio_al_contar`, `contador` con 403, tenant, `Decimal`, sin datos reales en huellas ni logs); `security-reviewer` revisa la lectura de empresa/logo en la ruta de activos; comprobación de que `medicion-plantillas.md` e `informes/` no están en el árbol a commitear; comprobación de que la matriz no tiene filas sin prueba ni elementos XML sin fila; checklist de revisión manual en Excel real (plantilla vs. generado, incluidos `####` en tarjetas y fechas por configuración regional) documentado para el humano.
- Archivos probables: `specs/019-diseno-informes-excel/matriz.md` (estado final), `MEMORY.md`.
- Verificación: `cd backend && uv run pytest -q` y `uv run ruff check .`
- Recordatorio del reviewer (T1): antes de cerrar, regenerar la huella y la matriz con las plantillas locales de `informes/` (`cd backend && uv run python tests/utils_xlsx_diseno.py`) y confirmar que no hay deriva, porque la prueba de deriva se omite en CI (allí no están las plantillas).
- Dependencia: T3, T4 y T5.
