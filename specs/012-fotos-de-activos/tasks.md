# Tasks 012 — Fotos de activos y atajo tipo app

> **Estado:** Aprobadas (G1–G3, 2026-11-15). Una tarea ≤ 1 día, pruebas primero, revisión y commit por tarea. Plan en `plan.md`.

| Tarea | Resultado | Verificación | Depende de |
|---|---|---|---|
| T1 | `Almacen` (carpeta local y S3) con las mismas pruebas en los dos (S3 con `moto`); configuración y error al arrancar en producción sin S3 | backend: `pytest`, `ruff` | aprobación |
| T2 | `procesar()`: tipo real, límites, orientación, sin metadatos, completa + miniatura | igual que T1 | aprobación |
| T3 | Migración `0013_fotos` (tabla, RLS, privilegios, disparador, tipos de evento); `docs/03` | igual que T1 + prueba de migración | aprobación |
| T4 | `PUT`/`DELETE /activos/{id}/foto`, `GET /fotos/{id}`, `foto` en la ficha; contrato; roles (Q1 B: ambos) | igual que T1 + `api:types` | T1–T3 |
| T5 | `PUT /sesiones/{sid}/verificaciones/{vid}/foto`; `foto_id` en verificaciones e historial; contrato | igual que T4 | T4 |
| T6 | Web: `lib/fotos.ts` (reducir, subir con reintento, mostrar con sesión) y `CampoFoto` | web: `test`, `lint`, `typecheck`, `build` | T4 |
| T7 | Web: foto en el alta (admin y contador) y en la ficha y verificar (cambiar/quitar, ambos roles) | igual que T6 | T6 |
| T8 | Web: foto al verificar e historial con miniaturas y visor | igual que T6 | T5, T6 |
| T9 | Atajo tipo app: manifest, íconos y etiquetas | igual que T6 + Chromium instalable | aprobación |
| T10 | Configuración y documentación (`.env*`, compose, `docs/02`, `05`, `09`, `10`, CI) | revisión | T1–T9 |
| T11 | Navegador real, e2e, revisión de seguridad y de dominio | skill `browser-qa`, `npm run e2e` | T1–T10 |

## Notas por tarea
- **T1 (hecha, 2026-11-15):** `app/fotos/almacen.py`: `Almacen` (`guardar`, `leer`, `borrar` idempotente) con `CarpetaLocal` (escritura atómica por temporal y `os.replace`, ruta resuelta dentro de la raíz) y `S3` (`boto3`, estilo de ruta, reintentos estándar, tiempos de espera); claves solo `<uuid>/<uuid>[_mini].jpg` (expresión estricta: nada del usuario llega a una ruta). Configuración (`load_almacen` en `app/config.py`): vacío = carpeta (`backend/.almacen`, o `ALMACEN_CARPETA`) en desarrollo y pruebas y fotos desactivadas fuera (aviso al arrancar); `carpeta` rechazada fuera de desarrollo; `s3` exige `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` (nombra las que faltan); llaves fuera de `repr`. `create_app` deja el almacenamiento en `app.extensions`. `.almacen/` en `.gitignore` y `.dockerignore`. Dependencias: `boto3==1.44.3`, `pillow==13.0.0`; `moto[s3]==5.2.5` (pruebas). `test_almacen.py` (39): las mismas pruebas en carpeta y en S3 simulado, claves maliciosas, configuración por entorno, variables que faltan y llaves que nunca se muestran.
- **T2 (hecha, 2026-11-15):** `app/fotos/imagen.py`, `procesar(bytes) -> Procesada(completa, mini, ancho, alto)`: ≤ 10 MB (`413 imagen_demasiado_grande`), tipo por contenido entre JPEG, PNG y WebP (`415 tipo_no_admitido`; GIF, BMP, TIFF, PDF, SVG y texto fuera), bomba de descompresión rechazada antes de decodificar (> 40 MP o aviso de Pillow → `422 imagen_invalida`), imagen rota `422`; `exif_transpose`, RGB con fondo blanco si hay transparencia, JPEG calidad 82 sin EXIF, GPS ni perfil de color, lado ≤ 1600 y miniatura de 320 (no agranda). `test_imagen.py` (18).
