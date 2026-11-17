# Tasks 013 — Informe con los datos de la empresa y nuevo diseño de exportación

> **Estado:** Aprobadas (G1–G3, 2026-11-16). Una tarea ≤ 1 día, pruebas primero, revisión y commit por tarea. Plan en `plan.md`.

| Tarea | Resultado | Verificación | Depende de |
|---|---|---|---|
| T1 | Migración `0014_empresa_y_detalle` (empresa, logos, copia al cierre, detalle por activo; RLS y privilegios); `docs/03` | backend: `pytest`, `ruff` + prueba de migración y catálogo RLS | aprobación |
| T2 | API de empresa y logo (validación de NIT, logo sin metadatos); contrato; roles | igual que T1 + `api:types` | T1 |
| T3 | Cierre guarda detalle y copia de la empresa desde U; informe con `empresa`; igualdad detalle ↔ desglose | igual que T1 | T1 |
| T4 | Excel v3 (Resumen, hojas por categoría, No encontrados) | igual que T1 (`openpyxl`) | T3 |
| T5 | PDF estilo A con logo (sin firmas) y «Página X de Y» | igual que T1 (`pypdf`) | T3 |
| T6 | Web: Ajustes → Empresa (formulario y logo) | web: `test`, `lint`, `typecheck`, `build` | T2 |
| T7 | Web: aviso en el informe y rótulo de sesiones anteriores | igual que T6 | T3, T6 |
| T8 | Navegador real, e2e, revisión de seguridad y de dominio; `docs/08` y `docs/05` | skill `browser-qa`, `npm run e2e` | T1–T7 |

## Notas por tarea
- **T1 (hecha, 2026-11-16):** migración `0014_empresa_y_detalle`: `empresa` (una por tenant, NIT con formato, dirección obligatoria, logo vigente con FK), `empresa_logo` (solo `INSERT`/`SELECT`: nunca se borra), `sesion_empresa` (copia al cierre, `vigente` para sesiones anteriores) y `sesion_detalle` (una fila por activo de U; único por sesión y activo; encontrado ⇔ estado físico y ubicación encontrada); las dos del cierre con el disparador `conteo_cerrado_requerido`; RLS forzada, privilegios mínimos por columna, nada a Supabase. Modelos `app/empresa/models.py` y `SesionEmpresa`/`SesionDetalle` en `app/conteo/models.py`; `docs/03`. Pruebas: `test_empresa_db.py` (3: NIT, una por tenant, otro tenant, logos sin cambios ni borrado, solo sesiones cerradas, coherencia, sin `UPDATE`/`DELETE`), cadena de migraciones y up/down/up de la 0014, catálogo cerrado de RLS y privilegios.
- **T2 (hecha, 2026-11-17):** blueprint `empresa` (solo admin): `GET /empresa` (sin fila: nombre del tenant, el resto `null`, `completa: false`), `PUT /empresa` (JSON ≤ 4 KB; nombre con el normalizador de nombres, dirección ≤ 200, NIT opcional con dígito de la DIAN y guardado como `890.903.938-8`, teléfono 7–30 y correo con formato; vacío o `null` borra un opcional; campos desconocidos `400`; el error de un campo lo nombra en `error.campo`), `PUT /empresa/logo` (multipart `logo_id` + `archivo`, cuerpo ≤ 2 MB + formulario; `imagen.procesar_logo`: mismos controles que las fotos, PNG RGBA ≤ 600 px sin textos, EXIF ni perfil; `409 empresa_sin_datos` sin la empresa guardada, `409 logo_id_en_uso`; reintento con el mismo id `200`), `DELETE /empresa/logo` (la empresa queda sin logo; archivo y fila se conservan, R2) y `GET /empresa/logo/{id}` (vigente o anterior, `image/png`, privado). La expresión de claves del almacenamiento admite `.png` para logos. Contrato (esquemas `Empresa`, `GuardarEmpresaBody`, `SubirLogoBody`, `LogoRespuesta`, `Error.error.campo`, códigos nuevos) y matriz de roles; `api:types`. `test_empresa_api.py` (42) y `test_empresa_responses`.
