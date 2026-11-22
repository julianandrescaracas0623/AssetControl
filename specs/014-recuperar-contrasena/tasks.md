# Tasks 014 — Recuperar contraseña por correo

Nueve tareas, cada una ≤ 1 día, tests primero. Revisión: **toda tarea de auth, SQL o token pasa por `reviewer` y `security-reviewer`** (T1, T2, T3, T4, T5, T6, T7, T8). `domain-guardian`: ninguna, salvo T2 porque lee y revoca por membresía (revisar solo la regla «una membresía activa»). Condición previa de T1: CUMPLIDA (el humano aplicó a `docs/03` los cambios 1–2 de `spec.md`).

Estado: T1–T9 hechas; spec cerrada (2026-11-19). Comandos de backend desde `backend/` con `PGHOSTADDR=127.0.0.1 uv run --env-file ../.env`.

---

### [x] T1 — Migración 0015 y modelo (primera tarea ejecutable) — HECHA 480d5d7 (2026-11-19)
- **Resultado:** tabla `recuperacion_contrasena` con RLS forzada, índice único parcial, `CHECK`s, FK compuesta y sin `GRANT` a la aplicación; `CHECK` de `limite_tasa` ampliado con los tres ámbitos nuevos; modelo SQLAlchemy mínimo; lista de excepciones del catálogo intacta.
- **Archivos probables:** `backend/migrations/versions/0015_recuperacion_contrasena.py`, `backend/app/auth/models.py`, `backend/tests/test_recuperacion_tabla.py`.
- **Pruebas primero:** catálogo A2/A10 (RLS, `tenant_isolation`, sin `DELETE`, sin privilegios para aplicación/`anon`/`authenticated`/`service_role`), índice parcial (segundo pendiente del mismo usuario falla, usado o invalidado no), `CHECK`s, `upgrade`/`downgrade`/`upgrade`, ámbitos nuevos aceptados y desconocidos rechazados.
- **Verificación:** `uv run alembic upgrade head && uv run pytest tests/test_recuperacion_tabla.py tests/test_auth_tables_isolation.py -q` y `uv run ruff check .`
- **Dependencia:** ninguna (cambios 1–2 a `docs/03`). **Revisión:** reviewer + security-reviewer.

#### Notas de cierre T1 y requisitos de seguridad para T2

T1 en `develop` 480d5d7 (2026-11-19), aprobada por reviewer y security-reviewer. Pruebas: `ruff check` y `ruff format --check` limpios; `pytest -q tests/test_recuperacion_tabla.py tests/test_catalog_rls.py tests/test_migrations.py tests/test_auth_tables_isolation.py` → 374 verdes.

**Requisitos T2 (0016):**
1. Políticas de `auth_owner` por comando (INSERT, UPDATE, SELECT), siempre `TO auth_owner`, sin `FOR ALL`, sin `PUBLIC`, cero filas con GUC vacías o NULL.
2. GRANT por columna mínimo, sin DELETE ni TRUNCATE: INSERT solo de `tenant_id, usuario_id, token_hash, expira_en` (más `id`/`creado_en` si hace falta), UPDATE solo de `(usada_en, invalidada_en)`, SELECT solo lo imprescindible; actualizar `EXPECTED_OWNER_COLUMNS`/`EXPECTED_OWNER_POLICIES` en `test_catalog_rls.py` (hoy `{}`) y mantener sin privilegios a la app.
3. M1: la política de invalidación NO filtra por expiración (`usuario_id = GUC AND usada_en IS NULL AND invalidada_en IS NULL`) para que un enlace vencido sin usar no bloquee otro; el INSERT exige `expira_en > now()` y `<= now() + 30 min` con `usada_en`/`invalidada_en` NULL; el consumo exige `expira_en > now()` (reloj de la base).
4. M2: la carrera entre dos `solicitar_recuperacion` del mismo usuario (23505 del índice parcial) se serializa (candado de la fila `usuario` o advisory lock) o usa `ON CONFLICT DO NOTHING`; misma respuesta en ambos caminos y mismo trabajo (R13/A2), sin 500 ni oráculo de enumeración.
5. `solicitar_recuperacion` crea token solo con exactamente 1 membresía activa de un usuario activo; `restablecer_contrasena` lo re-comprueba al canjear (usuario y membresía activos, `tenant_id` del enlace = el de esa membresía); si falla, rollback y token sin usar.
6. Validar `p_clave` en SQL (hex de 64 caracteres `~ '^[0-9a-f]{64}$'`) y mapear cualquier fallo, incluido `decode`, a la misma excepción estática `enlace_invalido`, sin eco de parámetros ni SQL.
7. Patrón 002 §2.1: `SECURITY DEFINER`, `STRICT`, `SET search_path = pg_catalog, pg_temp`, todo calificado, SQL estático, `set_config(..., true)` local con una GUC distinta por función y tabla; `REVOKE ALL` a PUBLIC/anon/authenticated/service_role y `EXECUTE` solo a la app; `OWNER TO auth_owner` con `REVOKE CREATE` inmediato; probar con los privilegios por defecto de Supabase simulados (como `test_supabase_roles_cannot_execute_acceso_functions`).
8. Cruce de tenants solo para el usuario del token: la revocación de `refresh_token` abarca todas las membresías de ese usuario y de nadie más; prueba obligatoria de que la recuperación de un usuario en el tenant A no altera sesiones ni contraseña de usuarios del tenant B ni un token ajeno.
9. `auth_owner` solo puede UPDATE de la columna `password_hash`, sin poder leerla, sin DELETE.
10. Pruebas de aislamiento A11: la app sigue sin acceso directo tras 0016; con GUC vacías o residuales las funciones no hacen nada; token vencido, usado o invalidado no canjea; un segundo canje falla; un token de un usuario no se aplica a otro; el hueco del índice parcial se libera tras invalidar un pendiente vencido.
11. No registrar `clave`, token ni correo en logs ni errores (cuidar `log_statement`, I1); T3 usará `hmac_email` (de `limits.py`) para `recuperar_cuenta` y devolverá `429` al superar el límite.

**Deudas menores T1:**
- B1: sin prueba automática del camino de fallo del `downgrade` con migrador no superusuario.
- B2: el CHECK admite `expira_en < creado_en` (falla cerrado; el INSERT de T2 garantiza `expira_en > now()`).
- B3: el modelo declara `index=True` en `tenant_id` pero 0015 no crea ese índice (solo rendimiento).
- B4: el `downgrade` destruye la traza de recuperaciones: no usarlo en producción sin exportar antes.
- I1: la `clave` es canjeable: no debe llegar a logs de PostgreSQL ni `pg_stat_statements`.
- M3: `tenant_isolation` implícita ALL coherente con 0013 (decisión global del humano si se parte por comando).
- Prueba con `app.tenant_id = ''` residual no ejercitada.

### [x] T2 — Funciones `acceso.*` y políticas del dueño (migración 0016) — HECHA e6c84ee (2026-11-19)
- **Resultado:** `acceso.solicitar_recuperacion` y `acceso.restablecer_contrasena` con las políticas por comando de `plan.md` §4, `EXECUTE` solo para la aplicación y dueño `auth_owner`; listas cerradas del catálogo actualizadas.
- **Archivos probables:** `backend/migrations/versions/0016_funciones_recuperacion.py`, `backend/tests/test_recuperacion_funciones.py`, `backend/tests/test_auth_functions.py` (listas cerradas).
- **Pruebas primero:** A19 de 002 por función (vacío, nulo, comodines, sin contexto residual); una membresía activa sí, cero o dos no; usuario inactivo; solicitud nueva invalida la anterior; dos solicitudes concurrentes dejan un pendiente (A4); uso único, vencido por reloj de base, invalidado, inexistente (A3); fallo intermedio revierte todo (A7); revoca todas las familias solo del usuario del token y nunca las de otro tenant (A11); `auth_owner` sin `DELETE` ni `SELECT` de `password_hash`; `SET ROLE anon`/`authenticated` denegado (C7).
- **Verificación:** `uv run pytest tests/test_recuperacion_funciones.py tests/test_auth_functions.py -q`
- **Dependencia:** T1. **Revisión:** reviewer + security-reviewer (revisa el SQL concreto de las políticas) + domain-guardian (regla de una membresía).

#### Notas de cierre T2 y requisitos para T3–T4

T2 en `develop` e6c84ee (2026-11-19), aprobada por reviewer, security-reviewer (re-auditoría conforme) y domain-guardian. Pruebas: `ruff check` y `ruff format --check` limpios; `pytest -q tests/test_recuperacion_funciones.py tests/test_catalog_rls.py tests/test_migrations.py tests/test_recuperacion_tabla.py tests/test_auth_functions.py tests/test_auth_tables_isolation.py` → 601 verdes; suite completa → 2201 verdes + el fallo preexistente de TLS de entorno `test_revisar_conexiones.py::test_tls_is_read_from_the_client_side_connection`.

**Hallazgos resueltos:**
- H1: bucle de revocación de refresh con tope de 10 pasadas.
- B1: formato completo del hash Argon2id con `[$]`, longitud máx. 255.
- I1 (reviewer): validación del prefijo `$argon2id$`.
- I2 (reviewer): prueba de las funciones viejas de 0004.

**Deuda y requisitos:**
- B3: acotar la política SELECT `dueno_recuperacion_restablecer` a enlaces pendientes rompe la invalidación de los otros enlaces con 42501: se deja como está (comentario en la migración).
- M1: los tiempos de `solicitar` no son literalmente iguales entre ramas. En T4: hacer en la MISMA transacción una escritura en todas las ramas (p. ej. el upsert del contador de `limite_tasa`, `limit_recover`) para que el COMMIT siempre haga flush; mover plantilla y SMTP al hilo posterior al COMMIT; el resultado booleano nunca influye en cuerpo, cabeceras ni temporización de la respuesta 202. Medirlo en T8 sobre el camino HTTP completo.
- M2 (riesgo aceptado): con SQL arbitrario en el rol de la app, dos llamadas (`solicitar_recuperacion` + `restablecer_contrasena`) bastan para tomar una cuenta de una membresía activa sin acceso al correo; es inherente a que la app elige la clave. Compensaciones: registro de auditoría del cambio de contraseña con `usuario_id` y `request_id` (nunca la clave) y promover el aviso «tu contraseña cambió». No ampliar el EXECUTE. Mejora opcional: un segundo dueño inerte sin `SELECT(password_hash)`.
- M3 (DECISIÓN HUMANA antes del piloto): un login iniciado antes del restablecimiento puede emitir su refresh después, y el JWT vive hasta 15 min (N4/A11). Se cierra con una versión de credencial (p. ej. `password_changed_at`), que exige migración y el plan §10 descartó.
- B2: T4 llama a `restablecer` como primera sentencia de una transacción nueva y corta, READ COMMITTED, sin `tenant_session`, y calcula Argon2 antes. Con REPEATABLE READ/SERIALIZABLE el segundo canje daría 40001.
- B4: un atacante puede invalidar el enlace pendiente de una víctima pidiendo uno nuevo hasta 3 veces por ventana (costo de R4).
- I1 de T1: la `clave` es canjeable: no debe llegar a logs de PostgreSQL ni `pg_stat_statements`; `log_statement=none` (spec de despliegue).
- `solicitar` con clave mal formada lanza `22023 clave_invalida`: T4 lo trata como 500 interno, nunca como respuesta distinta al cliente. Un NULL de `restablecer` se trata como inválido, nunca como éxito.
- Normalizar el correo con `normalize_email` antes de llamar (la comparación es exacta).
- Capturar `DBAPIError` y mapear como `_is_invitacion_invalida` (`app/db.py` ~l.366-389) sin registrar `str(exc)` ni `exc.orig`.
- D1 (decisión humana antes de abrir el segundo tenant): un usuario con ≥2 membresías activas no puede recuperar contraseña.
- D2: un usuario activo sin ninguna membresía activa tampoco puede recuperarse: confirmar que es lo deseado.
- m1: en T9 releer `docs/03` línea ~70 contra el cuerpo final (validación de formato del hash Argon2id, tope de 255, bucle de revocación y política que exige un enlace consumido en la misma transacción).
- m2: no hay `tenant.activo`; si se añaden tenants suspendidos, revisar ambas funciones.
- Falta una prueba de carrera de reactivación de membresía entre `solicitar` y `restablecer` (hoy cubierto solo por el test de re-comprobación).
- C8: `test_c8_supabase.py` se salta en local: correrlo en una base preparada como Supabase antes de desplegar.
- `test_recuperacion_funciones.py::_wait_until_blocked` depende de que el migrador vea `pg_stat_activity` de otros roles (superusuario local).
- Ruta del `downgrade` con migrador no superusuario sin prueba (B1 de T1).

### [x] T3 — Módulo de correo y configuración — HECHA c07a107 (2026-11-19)
- **Resultado:** `app/correo` (interfaz, buzón en carpeta, SMTP con TLS y timeout, plantilla en español, envío en hilo con semáforo) y `CorreoConfig` validada al arrancar; `backend/.buzon/` en `.gitignore`.
- **Archivos probables:** `backend/app/correo/{__init__,buzon,smtp,plantillas}.py`, `backend/app/config.py`, `backend/app/__init__.py`, `.gitignore`, `backend/tests/test_correo.py`.
- **Pruebas primero:** A14 (`.eml` UTF-8 con asunto, remitente, destinatario y enlace; nombre sin el correo; `carpeta` en producción y SMTP sin TLS fallan al arrancar; sin `CORREO_MODO` queda desactivado con un aviso); A13 con servidor SMTP falso (STARTTLS y SSL) y con rechazo, caída, tiempo agotado y certificado inválido: sin excepción hacia el llamador, log con solo tipo y `request_id`; `repr` de la configuración sin `SMTP_CLAVE`; `caplog` sin correo, token ni host.
- **Verificación:** `uv run pytest tests/test_correo.py -q` y `uv run ruff check .`
- **Dependencia:** ninguna (en paralelo con T1–T2). **Revisión:** reviewer + security-reviewer (credenciales, TLS, logs).

#### Notas de cierre T3 y requisitos para T4

T3 en `develop` c07a107 (2026-11-19), aprobada por reviewer (con correcciones aplicadas) y security-reviewer (conforme). Pruebas: `ruff check` y `ruff format --check` limpios; `pytest -q tests/test_correo.py` → 115 verdes y 1 omitida en Windows (permisos POSIX); suite completa → 2316 verdes, 9 omitidas y el fallo preexistente de TLS de entorno `test_revisar_conexiones.py::test_tls_is_read_from_the_client_side_connection`.

**Interfaz para T4:**
- `correo_activo(app)` indica si la recuperación está habilitada.
- `get_correo(app).enviar_recuperacion(destino_normalizado, token)` se llama tras el COMMIT; vuelve enseguida (envío en hilo con semáforo) y no lanza.
- `Correo.esperar(timeout)` solo para pruebas (esperar a que terminen los envíos en curso).
- El `request_id` se toma de la petición en curso.

**Variables de entorno (documentar en T9):**
- `CORREO_MODO`: `carpeta` | `smtp`; vacía = recuperación desactivada, con aviso al arrancar.
- `CORREO_REMITENTE`: obligatoria con `smtp`; en `carpeta` por defecto `AssetControl <no-responder@assetcontrol.invalid>`.
- `CORREO_CARPETA`: solo development/test; por defecto `backend/.buzon`.
- `SMTP_HOST`: obligatoria con `smtp`.
- `SMTP_PUERTO`: 1–65535; por defecto 587 con `starttls` y 465 con `ssl`.
- `SMTP_USUARIO` y `SMTP_CLAVE`: juntas o ninguna; nunca se imprimen.
- `SMTP_CIFRADO`: `starttls` | `ssl`; obligatoria fuera de development (en development, `starttls`); nunca texto plano.
- `URL_PUBLICA`: obligatoria si hay `CORREO_MODO`; https fuera de development; sin `?`, `#` ni usuario; host `[A-Za-z0-9.-]` o IPv6 entre corchetes; máx. 2048.

**Requisitos de seguridad (security-reviewer) para T4/T6/T9:**
1. `202` uniforme en cuerpo, cabeceras y estado para correo inexistente, inactivo, con 0 o ≥2 membresías, no ASCII o inválido; nunca depende del resultado de `enviar_recuperacion` ni de la configuración; `DestinoNoValido` no produce respuesta distinta.
2. Envío solo tras el COMMIT y solo con el correo normalizado (`normalize_email`) y el token recién generado, sin devolverlo ni registrarlo en otra parte.
3. Misma escritura en todas las ramas (p. ej. upsert de `limite_tasa`) para igualar tiempos (M1 de T2); medir en T8 sobre el camino HTTP completo (el arranque del hilo, ~100 µs, solo ocurre en la rama «sí se envía»).
4. Si `correo_activo(app)` es False: responder igual para todos los correos (p. ej. `503 recuperacion_no_disponible`), sin tocar la base de datos y sin crear ni invalidar enlaces pendientes (no amplificar B4).
5. Logs: nunca correo, token, enlace ni `str(exc)`; solo `request_id` y tipo; cuidar el logging de SQL y `log_statement` (I1 de T1).
6. El enlace sale solo de `config.correo.url_publica`, nunca de `request.host`, `X-Forwarded-Host` ni `Origin` (prueba A15).
7. Límites por IP y por cuenta con `hmac_email` y `429`; si falla el contador, `503` sin enviar.
8. Token con hash en base, 30 min, un solo uso; tras restablecer, revocar todas las familias del usuario (A11).
9. Solo con una membresía activa (D1 y D2 pendientes de decisión humana); Argon2 siempre, sin atajo.
10. `restablecer` en transacción corta READ COMMITTED sin `tenant_session` (B2); mapear `DBAPIError` sin `str(exc)`.
11. Frontend T6/T7: `/restablecer` lee el token del fragmento y lo limpia de la URL con `history.replaceState` de inmediato; `Referrer-Policy: no-referrer`; el token no va en la URL de la API, en la caché ni en `console`.
12. Despliegue: el proveedor SMTP no debe reescribir enlaces ni usar seguimiento de clics (rompería o filtraría el fragmento); documentar `SMTP_CIFRADO`, `URL_PUBLICA` https y que `ENVIRONMENT` nunca sea `development` en producción; cerrar M-1 antes del piloto.

**Deuda y hardening para T8:**
- M-1: el timeout de 10 s es por operación, no total (un SMTP que gotea o un DNS colgado retiene un hilo; con cupo 4 se descartan correos): plazo total ~30–60 s con cierre de socket y contador/log de descartes.
- B-1: la regex del destinatario es más laxa que RFC dot-atom: rechazar `..`, puntos al inicio o al fin, parte local >64 y `%`/`!`.
- B-2: fijar `contexto.minimum_version = ssl.TLSVersion.TLSv1_2` explícito y probarlo.
- B-3: `mkdir(mode=0o700)` del buzón (`CORREO_CARPETA` puede apuntar a cualquier ruta en development; el buzón no se limpia).
- B-4: añadir `.buzon/` a `backend/.dockerignore` (falta; el Dockerfile de desarrollo hace `COPY . .`).
- B-5: `URL_PUBLICA` fuera de development admite loopback, IP privadas y `.invalid`: avisar o rechazar en production/staging.
- B-6: una clave SMTP no ASCII provoca `UnicodeEncodeError` en `login` (solo se registra el tipo; fallo funcional).
- B-7: las pruebas TLS usan `importorskip("cryptography")` (llega transitiva por `moto[s3]`, grupo dev): que CI falle si se saltan.
- Destinatarios no ASCII no se envían (SMTPUTF8/IDNA): un correo no ASCII responde 202 y no envía.
- Un envío en curso se pierde al apagar el worker (aceptado).
- `ENVIRONMENT=development` en producción permitiría buzón y http (misma raíz de confianza que `secure_cookies`: riesgo ya aceptado).

### [x] T4 — Servicio, límites de tasa y endpoints — HECHA 488a540 (2026-11-19)
- **Resultado:** `POST /auth/recuperar` y `POST /auth/restablecer` con límites (`limit_recover`, `limit_reset`, variables `RATE_LIMIT_*`), CSRF/mismo sitio, política de contraseña de 002, Argon2 siempre, envío tras el `COMMIT` y `URL_PUBLICA` para el enlace.
- **Archivos probables:** `backend/app/auth/recuperacion.py`, `backend/app/auth/routes.py`, `backend/app/auth/limits.py`, `backend/app/config.py`, `backend/tests/test_recuperacion_endpoints.py`.
- **Pruebas primero:** A1 (seis casos con respuesta idéntica), A3, A5 (login viejo falla, nuevo funciona, `/auth/refresh` → `401`, sin cookie ni sesión), A6, A8 (`429` por IP y cuenta, contador que sobrevive, `503` sin base para contar), A9 (`403` sin contar), A15 (`Host` y `X-Forwarded-Host` manipulados).
- **Verificación:** `uv run pytest tests/test_recuperacion_endpoints.py tests/test_auth_login.py tests/test_auth_refresh_logout.py -q` y `uv run ruff check .`
- **Dependencia:** T2, T3. **Revisión:** reviewer + security-reviewer.

#### Notas de cierre T4 y requisitos para T5–T9
Reviewer y security-reviewer: APROBADO. Archivos: `recuperacion.py`, `routes.py`, `limits.py`, `db.py`, `config.py`, `docker-compose.yml` y pruebas (`test_recuperacion_endpoints.py`, `test_roles.py`, `test_rate_limit_config.py`, `test_openapi.py`).

**T5:**
- Borrar `PENDING_CONTRACT` y su prueba en `test_openapi.py`.
- Documentar `/auth/recuperar` y `/auth/restablecer` en `openapi.yaml`.
- Añadir `enlace_invalido` a `backend_error_codes`.

**T8:**
- I1 (security): canal de temporización por `hilo.start()` solo en la rama «se envía». Enviar vía `response.call_on_close` tras la respuesta y medir tiempos por HTTP con muestras.
- I2: prueba HTTP de dos canjes simultáneos del mismo token (un `204` y un `400`).
- Caso de aislamiento: token de B usado desde sesión de A.
- WARNING sin datos del enlace en rechazos (solo `request_id`).
- Aclaración R13: correo desactivado = `202` sin tocar la base.

**Menores:**
- `_resumen_error` en `db.py` duplica `_error_summary` de `limits.py`.
- Rama inalcanzable `failure or (...)` en `limits.py` (~línea 268).

**T9/despliegue:**
- Nivel INFO del logger de la app en producción (auditoría y «Correo entregado»).
- `log_statement=none`.
- `CORREO_*` y `URL_PUBLICA` en compose y `.env.example`.
- La web debe decir «si existe una cuenta, te enviamos un enlace» (con correo desactivado no se envía nada).

**Humano:** M3, D1/D2, B4.

### [x] T5 — Contrato y tipos — HECHA 84b81bc (2026-11-19)
- **Resultado:** `backend/openapi.yaml` con ambos endpoints (cuerpos, `202`, `204`, errores `enlace_invalido`, `contrasena_*`, `429`, `503`, cabecera CSRF) y tipos regenerados; funciones `solicitarRecuperacion` y `restablecerContrasena` en el cliente (con la cabecera `X-AssetControl-CSRF: 1`).
- **Archivos probables:** `backend/openapi.yaml`, `web/src/lib/api/schema.d.ts`, `web/src/lib/api/cliente.ts`, `web/src/lib/api/cliente.test.ts`.
- **Pruebas primero:** prueba del cliente (cabecera, cuerpo, mapeo de errores, el token nunca en la URL ni en `console`); prueba del contrato frente al esquema (`schema.node.test.ts`).
- **Verificación:** `cd web && npm run api:types && git diff --exit-code src/lib/api/schema.d.ts && npm test -- cliente && npm run typecheck`
- **Dependencia:** T4. **Revisión:** reviewer + security-reviewer (el cliente maneja el token).

#### Notas de cierre T5 y requisitos para T6/T7
Reviewer: APROBADO. Contrato de `/auth/recuperar` y `/auth/restablecer` en `openapi.yaml`; `enlace_invalido` en `ErrorCode`; `PENDING_CONTRACT` y su prueba eliminados; cliente `solicitarRecuperacion` y `restablecerContrasena`; `ErrorApi.reintentarEn` (de `Retry-After` del `429`); `202` en `ExitoDe`. Verificación: `npm test` 1006/1006 (80 archivos), lint y typecheck verdes.
- T6/T7: con correo desactivado el servidor igual responde `202`, así que la web dice «Si existe una cuenta con ese correo, te enviamos un enlace».
- T6/T7: usar `ErrorApi.reintentarEn` para el mensaje del `429`.
- T7: lee el token del fragmento y llama a `history.replaceState`; su auditoría de seguridad cubre el manejo del token en el navegador.

### [x] T6 — Web: «Recuperar contraseña» — HECHA c7a017d (2026-11-19)
- **Resultado:** enlace «¿Olvidaste tu contraseña?» en `/login` y pantalla `/recuperar` con `MarcoAcceso`, `Campo` de correo, `Boton`, estado de envío y mensaje genérico de éxito (igual para todo `202`), `Aviso` para `429`/`503`/red, foco y `aria-live`; ruta en `router.tsx`.
- **Archivos probables:** `web/src/routes/RecuperarContrasena.tsx`, `web/src/routes/Login.tsx`, `web/src/router.tsx`, `web/src/routes/recuperar.test.tsx`.
- **Pruebas primero:** vitest de estados (reposo, enviando, éxito genérico, `429`, sin conexión), enlace desde el login, accesibilidad por rol y etiqueta (sin `axe`, que no está instalado), la pantalla nunca muestra si el correo existe; navegador real a 375 px (`browser-qa`).
- **Verificación:** `cd web && npm test -- recuperar acceso && npm run lint && npm run typecheck`
- **Dependencia:** T5. **Revisión:** reviewer + security-reviewer (textos genéricos, sin oráculo).

#### Notas de cierre T6
Reviewer: APROBADO. Verificación: `npm test` 1022/1022 (81 archivos; `recuperar.test.tsx` 16 pruebas, incluidas `413` = mismo error y foco que `400`, y correo de `state` enviado recortado); lint, typecheck y build verdes.
- Textos definitivos: título del éxito «Revisa tu correo»; mensaje «Si existe una cuenta con ese correo, te enviamos un enlace que vale 30 minutos.» (igual para todo `202`, nunca repite el correo ni usa el texto del servidor).
- El correo escrito en el login viaja a `/recuperar` por el `state` del router (cero digitación); queda en `history.state` de la pestaña: aceptado.
- Capturas en `capturas/T6/` (locales, no se publican).
- Cambios para `docs/08` (los aplica el humano): ruta `/recuperar`; enlace «¿Olvidaste tu contraseña?» en el login; estado de éxito (`Aviso` tono éxito con foco, botones «Volver a iniciar sesión» y «Pedir otro enlace»); patrón de enlace secundario (texto apagado con flecha, alto mínimo 44 px, bajo un separador).
- Pendiente para T8: probar contra el backend real con el correo desactivado y activado; navegador real con lector de pantalla y gestor de contraseñas.

### [x] T7 — Web: «Nueva contraseña» — HECHA 1588f2e (2026-11-19)
- **Resultado:** `/restablecer` que lee el token del fragmento una vez, lo guarda solo en memoria y limpia la URL; campo de contraseña con `ayudaFija` (política 10–128, sin comunes) y mostrar/ocultar; errores `contrasena_*` junto al campo; `enlace_invalido` o falta de token → «Enlace vencido o ya usado» con botón a `/recuperar`; éxito → `/login` con el aviso «Tu contraseña se actualizó. Inicia sesión con la nueva.» sin sesión.
- **Archivos probables:** `web/src/routes/NuevaContrasena.tsx`, `web/src/routes/Login.tsx` (aviso por estado de navegación), `web/src/router.tsx`, `web/src/routes/restablecer.test.tsx`.
- **Pruebas primero:** token fuera de la URL y del historial tras montar; ausente → enlace no válido; política; errores del servidor; doble envío bloqueado; redirección con aviso; ningún `localStorage`/`sessionStorage` con el token; navegador real a 375 px.
- **Verificación:** `cd web && npm test -- restablecer acceso invitacion && npm run lint && npm run typecheck`
- **Dependencia:** T5 (en paralelo con T6; el aviso de `Login.tsx` se coordina con T6). **Revisión:** reviewer + security-reviewer.

#### Notas de cierre T7
Reviewer y security-reviewer: APROBADOS. Verificación: `npm test` 1050/1050 (82 archivos); lint, typecheck y build verdes.
- Token solo en memoria; se quita de la URL con `history.replaceState` y `navigate(..., { replace: true })`; sin `useMutation` (el token no entra en la caché).
- Meta `referrer` temporal mientras la pantalla está abierta; sin meta previo deja `no-referrer` al salir (nunca rebaja la política); con meta previo restaura su valor. StrictMode no lo duplica.
- Despliegue: añadir la cabecera `Referrer-Policy: no-referrer` en `/restablecer` y `/invitacion` y en el fallback SPA.
- Textos definitivos: «Crea una contraseña nueva», «Guardar contraseña», «Enlace vencido o ya usado», aviso en `/login` «Tu contraseña se actualizó. Inicia sesión con la nueva.».
- Tras el `204` la sesión local se olvida solo en el cliente (`useOlvidarSesionLocal`); sin auto-login.
- `CampoContrasena` (`web/src/components/app/CampoContrasena.tsx`) compartido con `Invitacion`.
- El correo que viaja a `/recuperar` se limpia de `history.state` tras leerlo.
- Capturas en `capturas/T7/` (locales, no se publican).
- Cambios para `docs/08` (los aplica el humano): ruta `/restablecer`; estado «enlace no válido»; aviso de éxito en `/login`; componente `CampoContrasena`.
- Pendiente T8/T9/despliegue: `Retry-After` de punta a punta en `/auth/restablecer`; el `204` revoca todas las sesiones (probar por HTTP); e2e; SMTP sin reescritura de enlaces ni tracking y `URL_PUBLICA` con https; gestor de contraseñas sin campo usuario (usabilidad); pruebas manuales en Chrome real (replaceState quita el fragmento; meta referrer efectivo; enlace desde un correo real).

### [x] T8 — Endurecimiento y pruebas de seguridad — HECHA d549188 (2026-11-19)
- **Resultado:** pruebas que cierran A2, A12 y A13 de punta a punta: igualdad de tiempo con SMTP lento, `caplog`/`capsys` sin secretos en solicitud, restablecimiento y fallo SMTP, concurrencia de dos restablecimientos con el mismo token (gana uno), reuso tras el cambio, `Referrer-Policy`/`no-store`/4 KB en ambas rutas, y e2e opcional con el buzón de la base `assetcontrol_e2e`. Corrige lo que aparezca.
- **Archivos probables:** `backend/tests/test_recuperacion_enumeracion.py`, `backend/tests/test_recuperacion_logs.py`, `backend/tests/test_recuperacion_concurrencia.py`, `web/e2e/recuperar.spec.ts` (opcional).
- **Verificación:** `uv run pytest -q -k recuperacion` y, si se hace el e2e, `cd web && npm run e2e -- recuperar`.
- **Dependencia:** T4, T6, T7. **Revisión:** reviewer + security-reviewer.

#### Notas de cierre T8
Reviewer y security-reviewer: APROBADOS. Verificación: `uv run pytest -q` 2434 pasan, 9 omitidas, 1 fallo TLS preexistente (`test_revisar_conexiones::test_tls_is_read_from_the_client_side_connection`, ajeno a la 014); `ruff check` y `ruff format --check` verdes.
- I1 resuelto con `call_on_close`: el envío arranca después de cerrar la respuesta.
- Pruebas de tiempos = guarda contra regresión, no prueba de ausencia de canal lateral; se omiten con `ASSETCONTROL_OMITIR_PRUEBAS_DE_TIEMPO`.
- M-1: plazo total de 45 s por entrega (vigilante que corta el socket); residual: DNS y saludo TLS de `ssl` antes de existir `sock` (los acota el timeout por operación). El vigilante comparte un candado con `__exit__` y una bandera `terminado`: un `_cortar` tardío no toca el socket ni marca vencido (hallazgo del security-reviewer).
- TLS 1.2 mínimo; certificado de otro nombre rechazado en `starttls` y `ssl`; buzón con carpeta 0700.
- Destinatario dot-atom: correos con `%`, `!` o comillas no reciben enlace (decisión humana pendiente si hace falta ampliarlo).
- Deuda: `conexion._host` es atributo privado de `smtplib`; falla cerrada y las pruebas TLS reales detectarían un cambio.
- Aislamiento B→A: tras el canje de B, el enlace pendiente de A sigue vigente y se puede canjear.
- Pendiente T9/despliegue/humano: apagado ordenado con `Correo.esperar()` (`worker_exit` de gunicorn) y alerta sobre `descartados`; verificar que `ENVIRONMENT=production` rechaza `CORREO_MODO=carpeta` en arranque real; SMTP real STARTTLS/SSL contra el proveedor; B-5 `URL_PUBLICA` loopback/privada/`.invalid` en producción; B-6 `SMTP_CLAVE` no ASCII; B-7 CI que falle si las pruebas TLS se saltan; `cli.py` tiene su propio `_database_error_summary`; fijar versión de Python en el Dockerfile.

### [x] T9 — Documentos de entorno y cierre — HECHA a660a10 (2026-11-19), salvo `.env.example` (ver notas)
- **Resultado:** `.gitignore` verificado; `docs/10` y `docs/09` con las variables, cómo leer los `.eml` y qué falta elegir del SMTP de producción; cambio 6 (`docs/09` y `docs/10`) de «Cambios en docs» aplicado tal como está en `spec.md` (nunca `docs/adr/`); `MEMORY.md` y esta spec actualizados. Los cambios 1–4 ya están aplicados; T9 solo los verifica vigentes. **No aplicados:** el cambio 7 (`.env.example`), por el bloqueo de permiso `Read(.env.*)` (bloque propuesto abajo), y el cambio 5 (`docs/08`), que es del humano (`cambios-docs08.md`); ambos quedan en «Pendiente del humano». Correcciones de la revisión (docs/09 tabla de la §5, docs/10 mensaje de la API frente al de la pantalla, docs/07 y docs/10 correos no dot-atom) y variables de correo en `docker-compose.yml`: commits posteriores a a660a10.
- **Archivos probables:** `.env.example`, `docs/09-despliegue.md`, `docs/10-entorno-local.md`, `docs/08-diseno-visual.md`, `specs/014-recuperar-contrasena/*`, `MEMORY.md`.
- **Verificación:** `git grep -n -i -E "SMTP_CLAVE=.+|password=.+" -- ':!*.md'` sin hallazgos de valores; `git status --short`; suites completas `uv run pytest -q` y `npm test`.
- **Dependencia:** T8. **Revisión:** reviewer (security-reviewer solo si tocó `.env.example` o configuración con valores).

#### Notas de cierre T9
Commit a660a10 en `develop`: `docs/09` (variables `CORREO_*`/`SMTP_*`/`URL_PUBLICA`, §5.1 con proveedor por elegir, TLS ≥ 1.2, 10 s por operación y 45 s en total, sin reescritura de enlaces ni seguimiento de clics, alerta sobre `descartados`, INFO, `log_statement=none`, `Referrer-Policy`, apagado ordenado y prueba manual con SMTP real), `docs/10` (valores de desarrollo, buzón `backend/.buzon/`, cómo leer y borrar los `.eml`, correo desactivado = `202` sin tocar la base, correos con `%`, `!` o comillas sin enlace), `docs/03` (cuerpos finales de 0016: validación de clave y hash Argon2id ≤ 255, candado consultivo, tope de 10 pasadas, política de enlace consumido en la misma transacción, `auth_owner` ya tenía `SELECT (password_hash)` desde 0003) y `docs/07` (CU-ACC-06 con los textos definitivos y los dos casos aclarados). `docs/05` (P17, T5) verificado sin cambios. `cambios-docs08.md` (local) con el cambio 5 para el humano. `spec.md`: estado «Cerrada» y aclaraciones en R2, R7 y R13. Verificación: `git grep -n -i -E "SMTP_CLAVE=.+|password=.+" -- ':!*.md'` solo encuentra código y pruebas (ningún valor); `npm test` 1050/1050 (82 archivos); `uv run pytest -q` 2434 pasan, 9 omitidas y el fallo TLS preexistente `test_revisar_conexiones.py::test_tls_is_read_from_the_client_side_connection`.
- **Bloqueo:** `.env.example` no se pudo leer ni editar: la regla `Read(.env.*)` de `.claude/settings.json` lo niega al agente. Queda para el humano con este bloque (todas vacías; añadir al final de `.env.example`):

```dotenv
# --- Recuperación de contraseña (spec 014) ---
# Sin CORREO_MODO la recuperación queda desactivada (la API responde 202 sin enviar nada).
# Valores: carpeta (solo con ENVIRONMENT=development; escribe .eml en backend/.buzon/) o smtp.
CORREO_MODO=
# Base del enlace del correo, sin / final (en desarrollo: http://localhost:5173; fuera, https).
URL_PUBLICA=
# Remitente: "Nombre <correo@dominio>" o correo@dominio (obligatorio con smtp).
CORREO_REMITENTE=
# Carpeta del buzón con CORREO_MODO=carpeta; vacía = backend/.buzon/ (en Docker, déjala vacía).
CORREO_CARPETA=
# Servidor SMTP del proveedor (obligatorio con smtp).
SMTP_HOST=
# starttls o ssl (obligatorio fuera de development; nunca texto plano).
SMTP_CIFRADO=
# Opcional: por defecto 587 con starttls y 465 con ssl.
SMTP_PUERTO=
# Credenciales del proveedor: van juntas o ninguna. Nunca las escribas aquí; solo en .env.
SMTP_USUARIO=
SMTP_CLAVE=
# Límites de tasa opcionales de la recuperación (vacíos = valores por defecto de la app).
RATE_LIMIT_RECOVER_IP=
RATE_LIMIT_RECOVER_ACCOUNT=
RATE_LIMIT_RESET_IP=
```
- **Hallazgo (resuelto después):** `docker-compose.yml` no pasaba `CORREO_*`, `SMTP_*` ni `URL_PUBLICA` al contenedor `api`; ya los pasa con el patrón `${VAR:-}` (commit «feat(dev): pasar variables de correo al servicio api del compose») y `docs/10` lo explica.

## Deuda final

| # | Deuda | Origen | Qué hacer |
|---|---|---|---|
| 1 | `.env.example` sin las variables `CORREO_*`, `SMTP_*`, `URL_PUBLICA` ni `RATE_LIMIT_RECOVER_IP`/`RECOVER_ACCOUNT`/`RESET_IP` | T9 (bloqueo de permisos) | El humano las añade sin valores |
| 2 | ~~`docker-compose.yml` no pasa `CORREO_*` ni `URL_PUBLICA` a `api`~~ | T4/T9 | Resuelto tras T9 (compose con `${VAR:-}`) |
| 3 | `Referrer-Policy: no-referrer` en `/restablecer`, `/invitacion` y el *fallback* de la SPA (hoy `same-origin` en `wsgi.py`) | T7 | Spec de despliegue |
| 4 | Apagado ordenado: `worker_exit` de gunicorn con `Correo.esperar()` | T8 | Spec de despliegue |
| 5 | Alerta sobre `descartados` en el registro | T8 | Spec de despliegue |
| 6 | B-5: `URL_PUBLICA` con loopback, IP privada o `.invalid` se admite fuera de development | T3 | Avisar o rechazar en production |
| 7 | B-6: `SMTP_CLAVE` no ASCII da `UnicodeEncodeError` en `login` | T3 | Validar al arrancar |
| 8 | B-7: las pruebas TLS se saltan sin `cryptography` | T3 | Que CI falle si se saltan |
| 9 | `cli.py` tiene su propio `_database_error_summary` (y `_resumen_error` de `db.py` duplica `_error_summary` de `limits.py`) | T4/T8 | Unificar |
| 10 | Rama inalcanzable `failure or (...)` en `limits.py` | T4 | Limpiar |
| 11 | Versión de Python sin fijar en el Dockerfile | T8 | Fijarla |
| 12 | `conexion._host` es atributo privado de `smtplib` (falla cerrada) | T8 | Vigilar al subir Python |
| 13 | M1 de T2: tiempos de `solicitar` no literalmente iguales; las pruebas de tiempo son guarda de regresión | T2/T8 | Aceptado |
| 14 | B1 de T1: `downgrade` con migrador no superusuario sin prueba; B4 de T1: el `downgrade` destruye la traza | T1 | No usar `downgrade` en producción sin exportar |
| 15 | B3 de T1: `index=True` en `tenant_id` del modelo sin índice en 0015 | T1 | Rendimiento, menor |
| 16 | Prueba de carrera de reactivación de membresía entre `solicitar` y `restablecer` | T2 | Añadir prueba |
| 17 | C8: `test_c8_supabase.py` se salta en local | T2 | Correrlo en base como Supabase antes de desplegar |
| 18 | `_wait_until_blocked` depende de ver `pg_stat_activity` de otros roles | T2 | Aceptado en local |
| 19 | m2: no existe `tenant.activo`; si se añaden tenants suspendidos, revisar ambas funciones | T2 | Al decidirlo |
| 20 | Destinatarios no ASCII y con `%`, `!` o comillas no reciben enlace | T3/T8 | Decisión humana si hace falta ampliarlo |

## Pendiente del humano

- **M3 (antes del piloto):** un login iniciado antes del restablecimiento puede emitir su refresh después y el JWT de acceso vive hasta 15 min tras restablecer (N4/A11); se cierra con una versión de credencial (migración).
- **D1/D2 (antes del segundo tenant):** un usuario con ≥ 2 membresías activas, o activo con 0, no puede recuperar su contraseña: confirmar que es lo deseado (ligado a H-2).
- **B4:** un atacante puede invalidar el enlace pendiente de una víctima pidiendo uno nuevo (hasta 3 por ventana): riesgo aceptado o mitigación.
- **B-5, B-6, B-7** (filas 6–8 de la deuda).
- `cli.py` `_database_error_summary`; fijar la versión de Python en el Dockerfile; `conexion._host` (filas 9, 11 y 12).
- Añadir a `.env.example` las variables de la recuperación (fila 1; bloque propuesto en las notas de cierre de T9). El compose ya las pasa (fila 2 resuelta).
- Aplicar `cambios-docs08.md` a `docs/08`.
- Elegir proveedor SMTP, remitente verificado (SPF/DKIM) y desactivar reescritura de enlaces y seguimiento de clics (`docs/09` §5.1).
- **Pruebas manuales:** Chrome real (que `replaceState` quite el fragmento y que el meta `referrer` sea efectivo); lector de pantalla en `/recuperar`, `/restablecer` y el aviso de `/login`; gestor de contraseñas (sin campo usuario en `/restablecer`); SMTP real con `starttls` y `ssl`; abrir el enlace desde un cliente de correo real (web y teléfono); arranque real con `ENVIRONMENT=production` y `CORREO_MODO=carpeta` (debe negarse); e2e opcional con el buzón (`web/e2e/recuperar.spec.ts`, no hecho).
