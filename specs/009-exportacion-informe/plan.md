# Plan 009 — Exportar el informe a Excel y PDF

> **Estado:** Aprobado (G1–G3, 2026-11-15) con Q1–Q3 en la opción recomendada (`spec.md`).

## 1. Enfoque

Un módulo de dominio arma un **documento** intermedio (dataclasses con `Decimal` y textos ya formateados en COP) a partir del dict de `cierre.informe`: es la única entrada de los dos generadores. Primero el documento y el Excel con sus pruebas de igualdad; después el PDF; al final la web. Sin migraciones.

## 2. Dependencias (Q1)

Versiones fijadas en `backend/pyproject.toml` y `uv.lock`:
- Producción: `xlsxwriter==3.3.1` (sin dependencias), `reportlab==5.1.0` (trae `pillow` y `charset-normalizer`).
- Desarrollo (solo pruebas): `openpyxl==3.1.5` (lector independiente del `.xlsx`), `pypdf==7.1.0` (extrae el texto del PDF).
- La imagen `api` se reconstruye (`docker compose build api`).

## 3. Backend (T1–T3)

- **`app/conteo/exportar.py`**
  - `documento(informe) -> Documento`: metadatos (sesión, corte, cerró, cuándo), las tres cifras, % encontrado, filas del desglose por dimensión con su total y la lista de no encontrados con su total. Todo viene del dict; aquí no se suma (el % es la proporción de unidades, como en la web).
  - `formato_cop(Decimal) -> "$ 1.390.000,50"` (igual que `formatCOP` de la web; prueba de tabla compartida con los mismos casos que `format.test.ts`).
  - `a_excel(doc) -> bytes` (XlsxWriter, en memoria, `constant_memory` no hace falta): hoja «Informe» (encabezado, tres cifras, % y nota de congelado), hojas «Por categoría», «Por ubicación» y «No encontrados». Dinero como número con formato `"$" #,##0.00` (Q2 A), unidades enteras; texto siempre con `write_string` (nunca fórmulas), anchos de columna y fila de encabezado fija.
  - `a_pdf(doc) -> bytes` (reportlab `platypus`, Carta horizontal según Q3): título, metadatos, tabla de tres cifras, las dos tablas de desglose y la lista de no encontrados con encabezado repetido por página, pie con «Informe congelado al cierre · página N de M». Fuentes estándar (Helvetica); caracteres fuera de Latin-1 → «?».
  - `nombre_archivo(sesion, extension)`: `informe-<slug-del-nombre>-corte-<AAAA-MM-DD>.<ext>`, ASCII, con `filename*` UTF-8 en `Content-Disposition`.
- **Rutas** en `app/conteo/routes.py`: `GET /sesiones/<id>/informe/excel` y `/informe/pdf` (admin) → `cierre.informe(...)` → `exportar` → `Response(bytes, mimetype=...)` con las cabeceras de R6. Errores JSON de siempre (`409 sesion_abierta`, `404`, `403`).
- **Contrato:** dos rutas con `200` de tipo `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` y `application/pdf` (`type: string, format: binary`) y los errores JSON; el validador de `test_openapi.py` acepta respuestas binarias comprobando tipo y que el cuerpo no esté vacío.
- **Pruebas** (`test_exportar.py`): igualdad Excel↔JSON leyendo con `openpyxl` cada celda de dinero (como `Decimal(str(valor))` redondeado a centavos) y unidades; igualdad PDF↔JSON extrayendo el texto con `pypdf` y buscando cada cifra formateada; sesión en ceros; nombre con `=`, `+`, `-`, `@` al inicio queda texto; cabeceras; informe idéntico tras cambios posteriores; roles y tenant; registros sin cifras.

## 4. Web (T4)

- `lib/api/cliente.ts`: `descargar(ruta, token)` que pide el binario con el mismo manejo de errores (`ErrorApi`) y devuelve `{ blob, nombre }` (nombre desde `Content-Disposition`).
- `lib/informe.ts`: `useExportarInforme(id)` (mutación) que descarga y dispara el guardado con un enlace temporal (`URL.createObjectURL`, se libera al terminar).
- `routes/admin/Informe.tsx`: botones «Exportar Excel» y «Exportar PDF» con estado de carga y `toast` de error; en celular quedan en el encabezado sin desbordar.
- Pruebas: llama a la ruta correcta, usa el nombre del servidor, muestra el error, deshabilita mientras descarga.

## 5. Verificación (T5)

Navegador real (skill `browser-qa`): cerrar una sesión con datos variados, descargar los dos archivos a 1440 y 375 px, leerlos (Excel con `openpyxl`, PDF con `pypdf`) y comparar con las cifras de la pantalla; revisar las capturas del PDF renderizado. Revisión de seguridad (rol, tenant, cabeceras, fórmulas, registros) y de dominio (una sola fuente, sin `float` en el cálculo).

## 6. Riesgos y mitigación

Ver `spec.md`. Si G1 elige otra librería, cambian solo `a_excel`/`a_pdf` y las dependencias; el documento intermedio y las pruebas de igualdad se mantienen.
