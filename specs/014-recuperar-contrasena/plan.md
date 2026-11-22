# Plan 014 — Recuperar contraseña por correo

Cumple `spec.md` (R1–R18, A1–A19). Reutiliza los patrones de 002 (A1 con `auth_owner`, doble hash, `limite_tasa`, `is_same_site_request`) y el kit de 016. Sin dependencias nuevas.

## 1. Enfoque

Dos funciones `SECURITY DEFINER` en `acceso` hacen todo lo que toca `usuario`, `membresia`, `refresh_token` y la tabla nueva, porque la solicitud ocurre **antes de conocer el tenant** y la aplicación no puede escribir `usuario` (002 R4e). La app Flask: valida forma, aplica el límite de tasa, hashea con Argon2 y llama a la función; el correo se envía en un hilo simple después del `COMMIT`.

```
POST /auth/recuperar {email}
  → forma + 4 KB → is_same_site_request → limit_recover(email)        (429/503)
  → acceso.solicitar_recuperacion(email_normalizado, clave)           (misma secuencia siempre)
  → COMMIT → si devolvió true: hilo → correo (carpeta | SMTP+TLS)
  → 202 {mensaje genérico}

POST /auth/restablecer {token, password}
  → forma + 4 KB → is_same_site_request → política de contraseña → limit_reset()
  → Argon2id(password) (siempre)
  → acceso.restablecer_contrasena(clave, hash)  (atómica)
  → 204 | 400 enlace_invalido
```

## 2. Módulos (rutas probables)

| Archivo | Contenido |
|---|---|
| `backend/app/auth/recuperacion.py` | servicio: token, `clave`, llamadas a las funciones, política de contraseña reutilizada de `credentials` |
| `backend/app/auth/routes.py` | dos rutas nuevas en el blueprint `/auth` (heredan `no-store`, `no-referrer` y 4 KB) |
| `backend/app/auth/limits.py` | `limit_recover(email)`, `limit_reset()`; ámbitos `RECOVER_IP`, `RECOVER_ACCOUNT`, `RESET_IP` |
| `backend/app/config.py` | `RateLimits` (3 campos + `RATE_LIMIT_RECOVER_IP/ACCOUNT`, `RATE_LIMIT_RESET_IP`), `CorreoConfig` desde las variables de R18 con validación al arrancar |
| `backend/app/correo/__init__.py` | `Correo` (interfaz), `enviar_en_hilo`, semáforo acotado |
| `backend/app/correo/buzon.py` | destino carpeta (`.eml`, nombre `<UTC>-<aleatorio>.eml`, sin el correo en el nombre) |
| `backend/app/correo/smtp.py` | `smtplib.SMTP`/`SMTP_SSL`, `ssl.create_default_context()`, `timeout=10` |
| `backend/app/correo/plantillas.py` | asunto y cuerpo fijos en texto plano |
| `backend/migrations/versions/0015_recuperacion_contrasena.py` | tabla, RLS, `CHECK` de `limite_tasa` |
| `backend/migrations/versions/0016_funciones_recuperacion.py` | funciones `acceso.*` y políticas del dueño |
| `backend/openapi.yaml`, `web/src/lib/api/schema.d.ts`, `web/src/lib/api/cliente.ts` | contrato, tipos y llamadas |
| `web/src/routes/RecuperarContrasena.tsx`, `NuevaContrasena.tsx`, `router.tsx`, `Login.tsx` | pantallas y enlace |

## 3. Tablas afectadas

### 3.1 `recuperacion_contrasena` (nueva, migración 0015)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | `gen_random_uuid()` |
| `tenant_id` | uuid NOT NULL | tenant de la **única** membresía activa del usuario al solicitar |
| `usuario_id` | uuid NOT NULL | |
| `token_hash` | bytea NOT NULL | `CHECK (octet_length(token_hash) = 32)`; `sha256(clave)`; `UNIQUE` |
| `expira_en` | timestamptz NOT NULL | `now() + interval '30 minutes'` fijado por la función; `CHECK (expira_en <= creado_en + interval '30 minutes')` |
| `usada_en`, `invalidada_en` | timestamptz NULL | `CHECK (usada_en IS NULL OR invalidada_en IS NULL)` |
| `creado_en` | timestamptz NOT NULL DEFAULT now() | |

- FK compuesta `(tenant_id, usuario_id)` → `membresia (tenant_id, usuario_id)` (única según `docs/03`).
- **Índice único parcial** `(usuario_id) WHERE usada_en IS NULL AND invalidada_en IS NULL`: un enlace vivo por usuario (los NULL no chocan en un `UNIQUE` normal; por eso es parcial). No hay índice aparte por `usuario_id`: el parcial cubre la invalidación de pendientes (T1/T2).
- RLS: `ENABLE` + `FORCE`; `tenant_isolation` `TO` el rol de aplicación (`USING`/`WITH CHECK` con `NULLIF(current_setting('app.tenant_id', true), '')::uuid`), sin `PUBLIC` ni `FOR ALL`.
- **GRANT a la aplicación: ninguno** (ni `SELECT`). La política existe por catálogo (A2 de 002) y defensa en profundidad. `REVOKE ALL` a `PUBLIC`, `anon`, `authenticated`, `service_role`. Sin `DELETE` para nadie.
- Los tokens usados, invalidados o vencidos se **conservan** (constitución §6, nada se borra). El crecimiento queda acotado por los límites de tasa (3 por cuenta cada 15 min) y por el índice parcial; no hay comando de purga. No se amplía la excepción de `DELETE` de `limite_tasa`.

### 3.2 `limite_tasa` (migración 0015)

Se reemplaza el `CHECK` de `ambito` (drop + add, reversible en `downgrade`) añadiendo `recuperar_ip`, `recuperar_cuenta`, `restablecer_ip`. Sin cambio de columnas, RLS ni `GRANT`. El `downgrade` falla con mensaje claro si existen filas de los ámbitos nuevos (o las ignora con `DELETE` por el migrador, que sí lo tiene sobre esta tabla: decide T1 con el `security-reviewer`; recomendado borrar solo esos ámbitos con el migrador).

## 4. Funciones del esquema `acceso` (migración 0016)

Mismo patrón que 002 §2.1: `SECURITY DEFINER`, `STRICT`, `SET search_path = pg_catalog, pg_temp`, todo calificado, SQL estático, `set_config(..., true)` local, una GUC distinta por función y tabla, `REVOKE ALL ... FROM PUBLIC, anon, authenticated, service_role`, `GRANT EXECUTE` solo al rol de aplicación, `OWNER TO auth_owner` con la membresía transitoria y `REVOKE CREATE` inmediato (C3/C5). El SQL exacto lo fija T2 con el `security-reviewer`.

| Función | Entrada | Efecto | GUC propias |
|---|---|---|---|
| `acceso.solicitar_recuperacion(p_email, p_clave)` → `boolean` | email normalizado, `clave` hex | Lee `usuario` activo por email; cuenta sus membresías activas; si es exactamente 1: invalida el pendiente anterior (`UPDATE ... invalidada_en = now()`) e inserta el token nuevo (`expira_en = now() + 30 min`); devuelve `true` solo si insertó. Las sentencias se ejecutan **siempre** (con 0 filas si no aplica) para igualar el trabajo (R13) | `app.auth_rec_email`, `app.auth_rec_usuario`, `app.auth_rec_clave` |
| `acceso.restablecer_contrasena(p_clave, p_password_hash)` → `uuid` | `clave` hex, hash Argon2id | `UPDATE recuperacion_contrasena SET usada_en = now() WHERE token_hash = sha256(decode(p_clave,'hex')) AND usada_en IS NULL AND invalidada_en IS NULL AND expira_en > now() RETURNING usuario_id`; sin fila → excepción estática. Comprueba `usuario.activo` y exactamente una membresía activa (si no, excepción: revierte y el token queda sin usar). Luego `UPDATE usuario SET password_hash`, `UPDATE refresh_token SET revocado_en = now() WHERE revocado_en IS NULL` de **todas** las membresías del usuario e invalidación de otros pendientes. Devuelve el `usuario_id` | `app.auth_reset_clave`, `app.auth_reset_usuario` |

Políticas de `auth_owner` (por comando, nunca `FOR ALL`, `TO auth_owner`, cero filas con la GUC vacía; lista cerrada que se añade a A2/C6 de 002):

| Tabla | Comando | Política (esquema) |
|---|---|---|
| `usuario` | SELECT | `email = app.auth_rec_email AND activo` (columnas `id, email, activo`); para restablecer: `id = app.auth_reset_usuario` |
| `usuario` | UPDATE | `USING (id = app.auth_reset_usuario) WITH CHECK (id = app.auth_reset_usuario)`; `GRANT UPDATE (password_hash)` |
| `membresia` | SELECT | `usuario_id = app.auth_rec_usuario` o `= app.auth_reset_usuario` (`id, tenant_id, activa`) |
| `recuperacion_contrasena` | INSERT | `WITH CHECK (usuario_id = app.auth_rec_usuario AND token_hash = <clave de la GUC> AND usada_en IS NULL AND invalidada_en IS NULL AND expira_en > now() AND expira_en <= now() + interval '30 minutes')` |
| `recuperacion_contrasena` | UPDATE (`usada_en`, `invalidada_en`) | consumir: `USING (token_hash = clave AND usada_en IS NULL AND invalidada_en IS NULL AND expira_en > now()) WITH CHECK (usada_en = now())`; invalidar: `USING (usuario_id = GUC AND usada_en IS NULL AND invalidada_en IS NULL) WITH CHECK (invalidada_en = now() AND usada_en IS NULL)` |
| `recuperacion_contrasena` | SELECT | `token_hash = clave` o `usuario_id = GUC` (lo exigen el `WHERE` y el `RETURNING`) |
| `refresh_token` | UPDATE (`revocado_en`) | `USING (membresia_id IN membresías del usuario GUC AND revocado_en IS NULL) WITH CHECK (revocado_en = now())`; cruza tenants solo para ese usuario |
| `refresh_token` | SELECT | lo mínimo para el `UPDATE`; ajuste fino en T2 |

`auth_owner` no recibe `DELETE`. `restablecer_contrasena` no lee ni devuelve `password_hash` (solo `UPDATE` de la columna); ver la garantía real en §4.1.

### 4.1 Lo que añadió o cambió la implementación de T2 (0016, aprobada)

El SQL exacto quedó fijado en `backend/migrations/versions/0016_funciones_recuperacion.py`; esta lista prevalece sobre el esquema de arriba donde difieran. Ninguna cambia una decisión de producto ni contradice `spec.md`.

- **Consumo atado a un enlace.** Las políticas `UPDATE` de `usuario` (`password_hash`) y de `refresh_token` (`revocado_en`) exigen además un enlace del usuario **consumido en la misma transacción** (`usada_en = now()` con la clave de la GUC `app.auth_reset_clave`): fijar `app.auth_reset_usuario` no basta para cambiar una contraseña ni revocar sesiones.
- **INSERT.** El `WITH CHECK` exige exactamente una membresía activa del usuario, la del `tenant_id` del enlace (existe la del tenant y no existe otra activa en otro tenant), además de 30 min como máximo, sin marcas y clave de la GUC.
- **Consumo.** El `WITH CHECK` de la política de consumir es `usada_en = now() AND invalidada_en IS NULL`.
- **Serialización en `solicitar`.** `pg_advisory_xact_lock(hashtextextended('recuperacion_contrasena:' || p_email, 0))` por correo en lugar de `FOR UPDATE` de la fila `usuario` (la app no tiene ese privilegio sobre `usuario`); más `ON CONFLICT DO NOTHING` como defensa. La invalidación del pendiente no filtra por expiración, para que un vencido sin usar no bloquee uno nuevo.
- **Errores.** `solicitar` con clave mal formada lanza `22023 clave_invalida` (no depende del correo, R13). Ninguna función usa `EXCEPTION WHEN OTHERS`. Ambas son `STRICT`: un argumento `NULL` devuelve `NULL` sin ejecutar el cuerpo. `restablecer` lanza siempre la misma excepción estática `P0001 enlace_invalido` (sin eco) ante clave mal formada, hash inválido, enlace inexistente, usado, invalidado o vencido, usuario inactivo o sin exactamente una membresía activa del tenant del enlace; la excepción revierte también el consumo.
- **Validación del hash recibido** en `restablecer`, antes de tocar tablas: formato completo `^[$]argon2id[$]v=19[$]m=[0-9]+,t=[0-9]+,p=[0-9]+[$][A-Za-z0-9+/]+[$][A-Za-z0-9+/]+$` y longitud máxima 255. Sin barras invertidas, para no depender de `standard_conforming_strings` (GUC de sesión). Evita dejar la cuenta sin poder entrar con un hash vacío, `argon2i`, bcrypt o recortado.
- **Revocación de refresh en bucle**, hasta 10 pasadas mientras afecte filas (H1, como `_revoke_family` de 002): en READ COMMITTED una rotación en vuelo cuyo sucesor se confirma durante la espera queda revocada en la pasada siguiente.
- **Sin índice aparte por `usuario_id`** (ver §3.1): lo cubre el parcial.
- **Garantía de «no lee `password_hash`».** `auth_owner` ya tenía `SELECT (password_hash)` sobre `usuario` desde 0003 (lo usa `buscar_login`), así que el privilegio del rol **no** lo impide. La garantía es el cuerpo estático de las funciones, fijado por su huella `sha256` en el catálogo C6 (`test_catalog_rls.py`). 0016 no añade ningún `SELECT` a `usuario`.
- **Lista cerrada de 13 políticas** (en `POLICIES` de la migración) y `GRANT` por columna mínimos; cualquier política o función nueva rompe el catálogo C6 y se revisa con el `security-reviewer`.

## 5. Endpoints y permisos

| Endpoint | Rol / ámbito | Cuerpo | Respuesta |
|---|---|---|---|
| `POST /auth/recuperar` | público, sin sesión; `X-AssetControl-CSRF: 1` + mismo sitio | `{email: string}` | `202 {mensaje}` siempre; `400 solicitud_invalida` solo por forma; `403` cabecera; `413`; `429 demasiadas_solicitudes`; `503` si no se puede contar |
| `POST /auth/restablecer` | público; mismo requisito | `{token: string, password: string}` | `204`; `400 enlace_invalido`; `400 contrasena_*` (códigos de 002); `400 solicitud_invalida`; `403`; `413`; `429`; `503` |

Heredan de `/auth`: `Cache-Control: no-store`, `Referrer-Policy: no-referrer`, tope de 4 KB. Sin `Set-Cookie` en ninguno. «Rol» no aplica (no hay sesión): la prueba de A12 de 002 se sustituye por la prueba de enumeración/igualdad (A1, A2) y de aislamiento (A11).

## 6. Límites de tasa

Ventana de 15 min (`RATE_LIMIT_WINDOW_SECONDS`). `limit_recover(email)`: `recuperar_ip` (10) y `recuperar_cuenta` (3, HMAC del email normalizado, el mismo cubo fijo para lo no normalizable). `limit_reset()`: `restablecer_ip` (10). Cuentan todas las peticiones, sin `give_back` (como validar y aceptar). Se llaman después de validar forma y antes de Argon2, de la función `acceso.*` y del correo. `429` y `503` con el mismo cuerpo que 002.

## 7. Correo

- **Configuración (R18), solo variables de entorno:** `CORREO_MODO` (`carpeta` | `smtp`; ausente = recuperación desactivada con aviso al arrancar, como `ALMACEN` en 012), `CORREO_REMITENTE`, `CORREO_CARPETA`, `SMTP_HOST`, `SMTP_PUERTO` (465 con `ssl`, 587 con `starttls`), `SMTP_USUARIO`, `SMTP_CLAVE`, `SMTP_CIFRADO` (`starttls` | `ssl`; sin valor y fuera de desarrollo = error), `URL_PUBLICA`. `SMTP_CLAVE` nunca se imprime ni aparece en `repr`.
- **Mensaje:** `email.message.EmailMessage`, `text/plain; charset=utf-8`, `From` configurable, `To` el correo normalizado, `Subject: Restablece tu contraseña de AssetControl`, `Message-ID` con `make_msgid`, `Auto-Submitted: auto-generated`. Cuerpo: enlace, «Vence en 30 minutos y solo sirve una vez», «Si no lo pediste, ignora este mensaje; tu contraseña no cambia».
- **Hilo:** `threading.Thread(daemon=True)` lanzado tras el `COMMIT`, con `BoundedSemaphore(4)`; si no hay cupo se descarta y se registra el tipo. Timeout de 10 s por operación SMTP. Sin reintentos. En pruebas, un destino falso registra los mensajes y expone `esperar()` para sincronizar sin dormir.
- **Registro de fallos:** `type(exc).__name__`, `request_id`; nunca el correo, el host, el token ni el mensaje de la excepción.
- **Carpeta:** solo con `ENVIRONMENT=development`; `backend/.buzon/` entra en `.gitignore`. Los `.eml` contienen un enlace válido: solo correos ficticios.

## 8. Migraciones

- **0015** `recuperacion_contrasena` + ampliación del `CHECK` de `limite_tasa`; `downgrade` en orden inverso (T1 prueba `upgrade`, `downgrade`, `upgrade`).
- **0016** funciones y políticas; `downgrade` quita las funciones, las políticas y los `GRANT`.
- Condición previa **cumplida**: los cambios 1–4 de `spec.md` a `docs/` están aplicados en `develop` (34edca9); T1 (480d5d7) y T2 (0016) siguen a esa base.

## 9. Estrategia de pruebas (tests primero)

- **Backend (`pytest`, base `assetcontrol_test`):**
  `test_recuperacion_tabla.py` (catálogo A2/A10, RLS, sin `GRANT`, índice parcial, `downgrade`);
  `test_recuperacion_funciones.py` (A19 de 002: parámetros vacíos, nulos, comodines, contexto residual; A4, A7, A11, uso único, vencimiento por reloj de base);
  `test_recuperacion_endpoints.py` (A1, A3, A5, A6, A8, A9, A15);
  `test_recuperacion_enumeracion.py` (A2: relación de medianas con SMTP lento; igualdad byte a byte de respuestas);
  `test_correo.py` (A13, A14: carpeta, SMTP falso con TLS, servidor caído, timeout, config inválida);
  `test_recuperacion_logs.py` (A12 con `caplog` y `capsys`).
- **Web (`vitest`):** `recuperar.test.tsx` y `restablecer.test.tsx` (estados, errores genéricos, foco, fragmento sin token en la URL, redirección con aviso, enlace de login); la suite de acceso existente sigue verde.
- **e2e opcional (Playwright):** pedir el enlace, leer el `.eml` de la carpeta de la base `assetcontrol_e2e`, abrirlo, fijar la contraseña y entrar. No es obligatorio para cerrar la spec.
- **Navegador real a 375 px** con el skill `browser-qa` para las dos pantallas.
- **Comandos:** `cd backend && PGHOSTADDR=127.0.0.1 uv run --env-file ../.env pytest -q` y `uv run ruff check .`; `cd web && npm test && npm run lint && npm run typecheck`.

## 10. Decisiones técnicas (opción recomendada y porqué)

| Tema | Decisión | Por qué |
|---|---|---|
| Tenant de un correo global (H-2) | Token ligado a la **única** membresía activa; con 0 o ≥ 2 no se envía (respuesta igual) | Mantiene `tenant_id` y RLS en la tabla sin crear otra excepción global; coincide con Q6 (el login falla cerrado con varias). Si H-2 cambia el modelo, se revisa con `/sdd-change` |
| Dónde viven las operaciones | Funciones `acceso.*` `SECURITY DEFINER` | La solicitud es previa al tenant y la aplicación no escribe `usuario` (002 R4e); es el patrón aprobado, revisable por lista cerrada |
| Forma del token | Opaco, `token_urlsafe(32)`, doble hash, sin tenant dentro | Idéntico a invitaciones; la base filtra por la política del dueño |
| Dónde va el token | Fragmento `#` | No llega al servidor ni a logs de acceso ni a `Referer` (Q13 de 002) |
| Base del enlace | `URL_PUBLICA` de configuración | Evita Host header injection |
| Sin auto-login | `204` y volver a `/login` | El buzón no entrega sesión por sí solo; la primera entrada pasa por el límite del login; todas las sesiones previas se cierran |
| Sin endpoint «validar» | La validez se conoce al enviar | Menos superficie, otro límite y otro oráculo; el costo es que quien tarda más de 30 min lo sabe al enviar y se le ofrece pedir otro |
| Envío | Hilo simple tras el `COMMIT`, semáforo, timeout 10 s, sin reintentos | Igualdad de tiempo (R13) y sin colas (ADR-002); en la misma petición el SMTP delataría al correo existente. Alternativa descartada abajo |
| Tokens usados/vencidos | Se conservan marcados; sin `DELETE` ni comando de purga | Constitución §6; crecimiento acotado por la tasa; evita ampliar excepciones de `DELETE` |
| Límite por cuenta superado | `429`, no `202` silencioso | Cuenta todo igual exista o no (sin oráculo) y no engaña al usuario legítimo |
| JWT vivo tras restablecer | No se invalida (≤ 15 min); sí el refresh | Es N4/A11 de 002; añadir `password_changed_at` es otra decisión y otra migración |
| Aviso «tu contraseña cambió» | Fuera de alcance | Valioso pero separable; usa el mismo módulo de correo después |

## 11. Riesgos aceptados y requisitos para T3–T4

Salen de las auditorías de T2. Los marcados «decisión humana» no se resuelven en el código.

- **M1 — tiempos de `solicitar` (R13).** T4 debe ejecutar la escritura en **todas** las ramas (existe, no existe, 0 o ≥ 2 membresías) y llamar a `solicitar` siempre con una clave nueva; el correo se envía solo tras el `COMMIT` y en hilo. La igualdad de tiempos se mide en T8 (relación de medianas con tolerancia).
- **M2 — radio de una SQL injection.** Con dos llamadas (`solicitar` y `restablecer`) a `acceso.*`, una inyección SQL con el rol de la aplicación bastaría para tomar una cuenta. Se acepta; compensaciones: auditoría del evento y aviso «tu contraseña cambió» (hoy fuera de alcance, §10), y **no ampliar** `EXECUTE` a más roles ni funciones.
- **M3 — versión de credencial.** El JWT vivo sigue 15 min tras restablecer (§10, N4/A11 de 002). Añadir `password_changed_at` o versión de credencial es otra migración: **decisión humana antes del piloto**.
- **B2 — transacción corta.** La función corre en READ COMMITTED y la llamada la hace la ruta **después** de Argon2 (hash calculado antes), con la transacción lo más corta posible, para no sostener candados durante el costo del hash.
- **B4 — invalidar el pendiente de una víctima.** Quien conozca un correo puede pedir un enlace nuevo e invalidar el pendiente de otra persona; el costo se acepta por R4 (un enlace vivo por usuario) y lo acota el límite por cuenta (3 por 15 min).
- **I1 — clave en logs de PostgreSQL.** La clave canjeable viaja como parámetro de las funciones: no debe llegar a logs de PostgreSQL (`log_statement`, `log_min_duration_statement`, errores con parámetros). T4 y el despliegue lo verifican; la excepción de `restablecer` no lleva eco.
- **D1 — usuario con ≥ 2 membresías activas** no puede recuperar por este flujo (respuesta igual, no se envía). **Decisión humana** (ligada a H-2 de 002).
- **D2 — usuario con 0 membresías activas** tampoco puede recuperar. **Decisión humana.**

## 12. Riesgos técnicos

Ver `spec.md` (Riesgos). Adicionales: la ampliación del `CHECK` de `limite_tasa` requiere `DROP CONSTRAINT` con nombre estable (T1 lo lee del catálogo); la prueba de tiempo es sensible al hardware (se usa relación de medianas con tolerancia, como A10 de 002); `restablecer_contrasena` cruza tenants para revocar refresh solo del usuario del token, lo que el `security-reviewer` revisa con atención en T2.

## 13. Alternativa descartada

- **Enviar el correo en la misma petición con timeout:** más simple y sin hilos, pero la respuesta tarda distinto si el correo existe (SMTP ≈ cientos de ms) y delata cuentas; igualar con `sleep` es frágil y bloquea un worker de gunicorn. Se acepta el hilo con sus límites.
- **Tabla global sin `tenant_id` (como `usuario`):** evitaría el caso de varias membresías, pero añade una excepción más a la regla multi-tenant y al catálogo cerrado sin necesidad.
- **Token con el `tenant_id` dentro** (como la cookie de refresh): permitiría leer con RLS normal, pero igualmente hace falta una función para actualizar `usuario`; se prefiere el patrón de invitaciones.
- **Auto-login tras restablecer** y **endpoint de validación previa**: ver §10.
