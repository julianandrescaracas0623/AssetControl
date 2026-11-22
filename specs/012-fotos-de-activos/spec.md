# Spec 012 — Fotos de activos y atajo tipo app

> **Estado:** Implementada (T1–T11, 2026-11-16). Aprobada (G1–G3, 2026-11-15): Q1 **B**, Q2 **B**, Q3 y Q4 **A** (ver «Decisiones de G1»). Decisiones previas del humano (2026-11-15): **una foto principal por activo** (reemplazable), **foto opcional también al contar** y **atajo tipo app** en el teléfono. Cierra P18 («Fotos en el MVP: diferir») de `docs/05`. Depende de 004 (alta), 005 (ficha e historial) y 006 (verificación). Plan en `plan.md`, tareas en `tasks.md`.

## Problema

Al registrar un activo solo quedan texto y precio. En el inventario anual, una foto despeja dudas que el nombre no resuelve («Silla de prueba» ¿cuál?), sirve de evidencia del estado (un daño) y ayuda a quien cuenta a reconocer el activo. Además, el contador entra a `/contar` desde el navegador del teléfono; no tiene un ícono que abra la app directamente.

## Usuarios

- **Admin y contador** (los dos dan de alta, P11): toman una foto opcional al registrar un activo y, al contar, una foto opcional de la verificación.
- **Admin y contador** (Q1 B): agregan, cambian y quitan la foto principal; el admin desde la ficha y el contador desde la pantalla de verificar y el historial del activo.

## Alcance

- Dentro: foto principal del activo (alta y ficha), foto opcional de una verificación, entrega privada de las imágenes por Flask, almacenamiento de objetos (local en desarrollo, Supabase Storage en producción), eventos en el historial y atajo instalable (manifest con ícono, abre en `/contar`).
- Fuera: galería de varias fotos, edición o recorte, reconocimiento de imagen, fotos en los informes exportados, funcionamiento sin conexión (ADR-002), fotos en la importación de Excel.

## Requisitos (EARS)

1. **R1 Alta con foto.** Mientras registra un activo (admin en `/admin/activos/nuevo`, contador en `/contar/nuevo`), el usuario podrá tomar o elegir una foto (opcional), verla y quitarla antes de guardar. Guardar el activo no depende de la foto.
2. **R2 Subida aparte (ADR-002).** Cuando el activo quede creado, la web subirá la foto en una petición aparte con un `id` generado en el cliente. Si la subida falla, el activo queda registrado y la web dice «La foto no se subió» con «Reintentar»; reintentar con el mismo `id` no duplica (idempotente).
3. **R3 Reducir en el teléfono.** Antes de subir, la web reducirá la imagen (lado mayor 1600 px, JPEG ~0,8) para no gastar datos; el servidor no confía en eso (R5).
4. **R4 Una principal por activo.** Cada activo tiene como máximo una foto principal vigente. Cambiarla o quitarla **borra el archivo anterior** del almacenamiento (Q2 B; la fila queda marcada como retirada, sin imagen) y escribe un evento en el historial (`foto_agregada`, `foto_cambiada`, `foto_retirada`). Los dos roles pueden cambiar o quitar (Q1 B).
5. **R5 Procesar en el servidor.** El servidor aceptará solo JPEG, PNG o WebP de hasta 10 MB (`415`/`413` si no), lo decodificará con límite de píxeles (bomba de descompresión → `422`), aplicará la orientación EXIF y **guardará una copia nueva sin metadatos** (sin GPS ni modelo del teléfono) en JPEG de lado ≤ 1600 px, más una miniatura de 320 px. Nunca guarda el archivo tal como llegó.
6. **R6 Foto al contar.** Al verificar, el usuario podrá agregar una foto opcional (p. ej., un daño); se sube después de confirmar la verificación (no la frena) y queda ligada a esa verificación (una por verificación). Solo mientras la sesión esté abierta, por quien verificó o un admin.
7. **R7 Ver.** La ficha del activo (admin), la pantalla de verificar y el historial (ambos roles) muestran la miniatura; al tocarla, la imagen completa. El historial muestra la foto de cada verificación que la tenga.
8. **R8 Entrega privada.** Las imágenes solo se entregan por `GET /fotos/{id}` de Flask, con sesión y del mismo tenant (otro tenant o inexistente → `404`), `Cache-Control: private`, `nosniff` y tipo `image/jpeg`. El almacenamiento es privado: ninguna URL pública ni firmada sale al navegador, y las credenciales del almacenamiento solo las tiene Flask.
9. **R9 Datos.** Tabla `foto` (`docs/03`) con RLS forzado por tenant; el rol de la app solo inserta, lee y marca como retirada (no borra filas); el archivo de una foto retirada sí se borra del almacenamiento (Q2 B). Los registros del servidor no llevan claves de almacenamiento ni nombres de archivo del usuario.
10. **R10 Atajo tipo app.** La web publicará un manifest (`AssetControl`, ícono propio, `display: standalone`, `start_url: /contar`, color de marca) y los íconos para Android e iPhone, de modo que «Agregar a la pantalla principal» cree un ícono que abra la app sin barra del navegador. No agrega modo sin conexión ni service worker.

## Criterios de aceptación

- A1: API: subir, reintentar con el mismo `id` (sin duplicar), cambiar y retirar (con su evento), tipos y tamaños rechazados, bomba de descompresión, foto de otro tenant `404`, permisos de Q1 por rol, foto de verificación (sesión cerrada `409`, otro usuario `403`); la imagen guardada **no tiene EXIF** (GPS incluido) y respeta la orientación.
- A2: RLS: el rol de la app no ve fotos de otro tenant ni puede borrar filas; contrato OpenAPI con respuestas binarias ejercitado.
- A3: almacenamiento: las mismas pruebas pasan con el almacenamiento local y con un S3 simulado (Q3).
- A4: web: alta con y sin foto, falla de la subida con «Reintentar», ficha con cambiar/retirar según rol, foto al verificar, historial con miniaturas.
- A5: navegador real a 375 y 1440 px: tomar la foto con un archivo de prueba, verla en la ficha y en el historial; manifest válido (instalable en Chromium), axe 0, consola limpia; e2e extendido.

## Decisiones ya tomadas

ADR-001 y T4 (fotos en Supabase Storage, solo infraestructura; el acceso lo hace Flask), ADR-002 (solo en línea; fotos subidas aparte), P11 (los dos roles dan de alta), P13 (el contador no ve precios: nada cambia), `docs/03` (`foto` con UUID del cliente; los bytes fuera de la base). Decisiones del humano (2026-11-15): una principal por activo; foto también al contar; atajo tipo app.

## Riesgos

- **Espacio en Supabase (1 GB gratis):** ~300 KB por foto + miniatura ≈ 3.000 fotos (las retiradas se borran, Q2 B). Se documenta cómo ver el uso.
- **iPhone (HEIC):** con `accept="image/*"`, Safari entrega JPEG al subir; si llega HEIC, el navegador no lo puede reducir y el servidor responde `415` con un mensaje claro.
- **Memoria al procesar:** límite de 10 MB y de píxeles; se procesa una imagen por petición.
- **MinIO ya no publica imágenes de Docker** (archivado en 2025): por eso Q3 no propone un contenedor S3 en desarrollo.
- **Objeto huérfano:** si se guarda la imagen y falla el registro en la base, queda un objeto sin fila; no se ve ni se entrega. Se anota para una limpieza futura.

## Decisiones de G1 (humano, 2026-11-15)

| Pregunta | Decisión |
|---|---|
| Q1 Quién cambia o quita | **B:** admin y contador agregan, cambian y quitan la foto principal. |
| Q2 Al cambiar o quitar | **B:** se borra el archivo anterior. La fila `foto` queda como retirada (quién y cuándo) y el historial conserva el evento; solo la imagen desaparece. Decisión explícita del humano sobre la regla «no borrar datos de negocio»: el registro del cambio se conserva, la imagen reemplazada no. |
| Q3 Almacenamiento | **A:** carpeta local en desarrollo y pruebas; S3 (Supabase Storage) en producción; S3 probado con `moto`. |
| Q4 Dependencias | **A:** `boto3==1.44.3`, `pillow==13.0.0`; `moto[s3]==5.2.5` solo en pruebas. |

## Opciones que se presentaron en G1

| Pregunta | Opciones | Recomendación |
|---|---|---|
| Q1 Quién cambia o retira la principal | A: los dos agregan si el activo no tiene; solo el admin cambia o retira. B: los dos agregan, cambian y retiran. C: solo el admin. | **A.** El contador aporta fotos al registrar, pero cambiar la evidencia de un activo es una decisión del admin (como editar o dar de baja, 005). |
| Q2 Al cambiar o retirar | A: conservar la anterior como retirada (no se muestra; queda en el historial y en el almacenamiento). B: borrar el archivo anterior. | **A.** No se borran datos de negocio (constitución) y la foto anterior es evidencia; el costo es poco espacio. |
| Q3 Almacenamiento en tu PC y en pruebas | A: carpeta local (`backend/.almacen/`, ignorada) en desarrollo; S3 (Supabase) en producción; las pruebas de S3 con `moto` (solo pruebas). B: contenedor S3 en Docker (Garage o RustFS) para tener S3 también en desarrollo. | **A.** Sin contenedor extra en Windows; el código S3 se prueba igual con `moto` en la CI y una prueba opcional contra Supabase. B suma un servicio que configurar. |
| Q4 Dependencias | A: `boto3==1.44.3` (S3) y `pillow==13.0.0` (imágenes) en producción; `moto[s3]==5.2.5` solo en pruebas. B: cliente S3 propio sin `boto3`. | **A.** `boto3` es el cliente S3 de referencia (Supabase lo documenta); escribir la firma S3 a mano es riesgo sin beneficio. Pillow es el estándar y sabe quitar metadatos. |
