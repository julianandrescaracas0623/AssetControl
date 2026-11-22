# Plan 012 — Fotos de activos y atajo tipo app

> **Estado:** Aprobado (G1–G3, 2026-11-15) con Q1 B, Q2 B, Q3 A y Q4 A (`spec.md`).

## 1. Enfoque

La imagen nunca pasa por el navegador hacia el almacenamiento: la web la envía a Flask, Flask la valida, la vuelve a codificar sin metadatos y la guarda en un almacenamiento de objetos detrás de una interfaz pequeña (`Almacen`). La fila `foto` se escribe después de guardar el objeto. Primero almacenamiento y procesamiento (puro y probado), luego la migración, después los endpoints y al final la web. El manifest es independiente y va al final.

## 2. Almacenamiento (T1)

- `app/fotos/almacen.py`: protocolo `Almacen` con `guardar(clave, bytes, tipo)`, `leer(clave) -> bytes` y `borrar(clave)` (idempotente). Dos implementaciones:
  - `CarpetaLocal` (desarrollo y pruebas): raíz en `ALMACEN_CARPETA` (por defecto `backend/.almacen/`, en `.gitignore` y `.dockerignore`); valida que la clave no salga de la raíz.
  - `S3` (producción): `boto3` con `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, estilo de ruta (*path style*), sin ACL pública. Para Supabase: endpoint `https://<ref>.storage.supabase.co/storage/v1/s3` y llaves S3 del panel (Storage → S3 Connection), bucket privado `fotos`.
- Elección por configuración: `ALMACEN=carpeta|s3`. En desarrollo, vacío = `carpeta`. En producción/staging, `carpeta` no se admite (el contenedor es efímero) y `s3` exige sus cinco variables (falta → error al arrancar); sin `ALMACEN` la app arranca con las fotos desactivadas (`503 fotos_no_disponibles` y un aviso en el registro), así el despliegue no se cae por las fotos.
- Claves: `<tenant_id>/<foto_id>.jpg` y `<tenant_id>/<foto_id>_mini.jpg` (sin nombres del usuario).
- Pruebas: el mismo juego de pruebas contra `CarpetaLocal` y contra `S3` con `moto` (`mock_aws`).

## 3. Procesamiento (T2)

`app/fotos/imagen.py`, función pura `procesar(bytes) -> (completa, mini)`: tamaño ≤ 10 MB (`413`), detectar tipo por contenido (no por extensión ni `Content-Type`) entre JPEG/PNG/WebP (`415`), `Image.MAX_IMAGE_PIXELS` acotado (40 MP; excederlo → `422`), `ImageOps.exif_transpose`, convertir a RGB (fondo blanco si hay transparencia), redimensionar a lado ≤ 1600 y a 320, guardar JPEG calidad 82 **sin `exif`** ni otros metadatos. Pruebas con imágenes generadas en la prueba: con GPS y orientación 6 (la salida no tiene EXIF y queda girada), PNG con transparencia, WebP, archivo que dice ser JPEG y no lo es, bomba de descompresión, tamaño límite.

## 4. Datos (T3, migración `0013_fotos`)

- `foto`: `id uuid` (del cliente), `tenant_id`, `activo_id` → `activo`, `verificacion_id` null → `verificacion`, `clave text`, `bytes int`, `ancho int`, `alto int`, `subida_por` → `usuario`, `creada_en`, `retirada_en` null, `retirada_por` null. FK compuestas con `tenant_id` como el resto del esquema.
- Únicos parciales: una principal vigente por activo `(tenant_id, activo_id) WHERE verificacion_id IS NULL AND retirada_en IS NULL`; una por verificación `(tenant_id, verificacion_id) WHERE verificacion_id IS NOT NULL`.
- RLS `tenant_isolation` forzado; el rol de la app: `SELECT`, `INSERT` y `UPDATE (retirada_en, retirada_por)` solamente; un disparador impide cambiar una foto ya retirada o quitar la marca. Sin `DELETE`.
- `activo_evento.tipo` admite `foto_agregada`, `foto_cambiada` (`{antes, despues}` con ids) y `foto_retirada`; el evento `verificado` no cambia (la foto de la verificación se lee por `verificacion_id`).
- `docs/03` (tabla `foto` real, ya sin `estado pendiente/subida`: la fila se escribe después del objeto) y prueba de migración (cabeza 0013).

## 5. API (T4–T5, blueprint `fotos`)

- `PUT /activos/{id}/foto` (multipart: `foto_id`, `archivo`): crea o cambia la principal. Mismo `foto_id` ya guardado para ese activo → `200` con la misma foto (idempotente); nuevo → `201`. Q1 B: los dos roles crean o cambian; la anterior queda retirada en la misma transacción y su archivo se borra después del commit (Q2 B; si el borrado falla, se registra sin la clave y queda un objeto huérfano que no se entrega). Activo dado de baja → `409`.
- `DELETE /activos/{id}/foto` (ambos roles, Q1 B): marca la principal como retirada y borra su archivo (Q2 B) → `204`; sin foto → `404`.
- `PUT /sesiones/{sid}/verificaciones/{vid}/foto` (multipart): una por verificación; sesión cerrada `409 sesion_cerrada`; contador que no hizo la verificación `403`; idempotente por `foto_id`.
- `GET /fotos/{id}?tamano=completa|mini`: bytes `image/jpeg`, `Cache-Control: private, max-age=86400` (la foto no cambia: cambiarla crea otra con otro id), `X-Content-Type-Options: nosniff`, `Content-Disposition: inline`. Una retirada ya no tiene archivo → `404`; otro tenant → `404`.
- La ficha (`GET /activos/{id}` y `por-codigo`) suma `foto: {id, creada_en} | null`; las verificaciones del activo (`GET /sesiones/{sid}/verificaciones?activo_id=`) y el historial suman `foto_id` donde exista. `MAX_CONTENT_LENGTH` = 11 MB. Límite de tasa de subidas por usuario (como el de la 002).
- Contrato OpenAPI (multipart y binario), matriz de roles y pruebas A1–A3.

## 6. Web (T6–T8)

- `lib/fotos.ts`: `reducir(file) -> Blob` (canvas: lado ≤ 1600, JPEG 0,8; si el navegador no puede decodificar, se envía tal cual y el servidor decide), `useSubirFoto` (reintento con el mismo `id`), `urlFoto(id, tamano)` con la sesión (las imágenes se piden con `fetch` y se muestran como `blob:` para enviar el token; la CSP ya permite `img-src blob:`).
- `components/app/CampoFoto.tsx`: botón «Tomar foto» (`<input type="file" accept="image/*" capture="environment">`: en el teléfono abre la cámara nativa sin pedir permisos de la página; en el PC abre el selector), vista previa, «Quitar», estados de subida y error con «Reintentar».
- Alta (admin y contador): `CampoFoto` opcional; tras el `201` del activo, sube la foto; la pantalla de «Activo creado» muestra si la foto quedó o falló.
- Ficha (admin) y verificar/historial (contador): foto o «Sin foto», «Cambiar foto» y «Quitar foto» (con confirmación: «se borra la imagen»). Verificar (ambos): miniatura de la principal; tras confirmar, «Agregar foto de esta verificación». Historial: miniaturas en los eventos de foto y en las verificaciones con foto; visor a pantalla completa accesible (`dialog`, cerrar con Esc).

## 7. Atajo tipo app (T9)

`web/public/manifest.webmanifest` (`name`, `short_name`, `start_url: /contar`, `scope: /`, `display: standalone`, `theme_color #2B50E0`, `background_color #FFFFFF`, `lang es-CO`), íconos PNG 192 y 512 (`any` y `maskable`) y `apple-touch-icon` 180 generados del logotipo existente (`components/app/Logo.tsx`), y las etiquetas en `index.html`. Se sirve desde `web/dist` en producción (la CSP `default-src 'self'` cubre `manifest-src`). Prueba: Chromium reconoce el manifest como instalable.

## 8. Configuración y documentación (T10)

`.env.example` y `.env` (bloque «Fotos»), `docker-compose.yml` (volumen de `backend/.almacen`), `docs/09` (bucket privado `fotos` y llaves S3 de Supabase como secretos de la plataforma), `docs/10` (cómo ver las fotos locales y cómo instalar el atajo en el teléfono), `docs/02`, `docs/05` (P18 decidida) y CI (las pruebas de S3 con `moto` corren en `ci-backend`).

## 9. Verificación (T11)

Navegador real (375 y 1440 px): alta con foto (archivo de prueba con GPS: la descargada desde `/fotos` no lo tiene), ficha, cambiar y quitar como admin y como contador (el archivo anterior ya no se entrega), verificar con foto, historial, falla forzada de la subida con «Reintentar», manifest instalable, axe 0, consola limpia; e2e extendido con una foto. Revisión de seguridad (subidas, tipo real, metadatos, tenant, entrega privada, credenciales) y de dominio (una principal, eventos, nada borra).

## 10. Riesgos

Ver `spec.md`.
