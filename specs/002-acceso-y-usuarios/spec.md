# Spec 002 — Acceso y usuarios

> **Estado:** Aprobada (G1–G3, 2026-11-12). **Condición:** T1 no empieza hasta que el humano aplique los cambios 1–5 a `docs/03` y P0 (`auth_owner` en el init); T10 no empieza hasta que aplique el cambio 6 (`limite_tasa`). Incorpora las decisiones humanas de la ronda G1 (Q1–Q18 salvo Q19; ver tabla) y los veredictos CAMBIOS del `security-reviewer` (primera revisión: B1, I1–I11, C1–C10; segunda: script bajo FORCE RLS, Q4=B completa, ventana de gracia, `membresia`, partición de tareas).
> **Depende de:** spec 001 (T1–T10), `docs/01-alcance-mvp.md`, `docs/02-arquitectura.md`, `docs/03-modelo-datos.md` (con los cambios propuestos de abajo, que aplica el humano antes de T1), `docs/07-casos-de-uso-y-modulos.md` (M1: CU-ACC-01..04), ADR-001 (RLS obligatoria), ADR-002.
> **Objetivo:** que un admin invite a un contador por enlace, ambos inicien sesión, el servidor verifique rol y tenant en cada petición, y quede probado que un tenant no ve a otro.
> **Convención:** `[PENDIENTE]` = decisión humana sin tomar. `[DECIDIDO]` = decisión humana.
> **Partición (Q18, DECIDIDO):** esta spec cubre el **backend** (T1–T10). OpenAPI + tipos TS (R17) y web mínima (R18) pasan a `specs/002b-acceso-web/` (aún sin aprobar; Q19 abierta). B2 y B5 de la deuda de T7 (spec 001) quedan diferidos.

---

## Decisiones humanas incorporadas

| Q | Decisión |
|---|---|
| Q1 | **A1 con C1–C10:** rol dueño `auth_owner` `NOLOGIN`, sin `BYPASSRLS` ni superusuario, no dueño de las tablas; funciones `SECURITY DEFINER` en un esquema propio `acceso`. **Consecuencia (R6):** el script del operador tampoco inserta directo; usa `acceso.crear_tenant(...)`, con el mismo patrón, `EXECUTE` solo para el rol migrador y sus políticas `TO auth_owner` en la lista cerrada. El `security-reviewer` revisa esas políticas en T2. |
| Q2 | Tabla `refresh_token` + cookie L1 `<tenant_id>.<secreto>` + rotación atómica; logout con la cookie de refresh. La ventana de gracia ~10 s y la revocación de familia por reuso se decidieron en Q15. |
| Q3 | **[DECIDIDO]** El primer admin entra por invitación (bootstrap), con expiración de 24 h. |
| Q5 | **[DECIDIDO]** El script usa un migrador sin superusuario con `EXECUTE` solo sobre `acceso.crear_tenant`; credenciales solo por entorno. |
| Q6 | **[DECIDIDO]** Con varias membresías activas el login falla cerrado. |
| Q7 | **[DECIDIDO]** Invitación 72 h (bootstrap 24 h), acceso 15 min, refresh 7 días con rotación. |
| Q8 | **[DECIDIDO]** Hash de contraseñas con `argon2-cffi` (no `werkzeug.security`) y `PyJWT` como dependencias nuevas de backend, con versiones exactas (`plan.md` §6). Sin `Flask-Limiter`. |
| Q10 | **[DECIDIDO]** Límites de tasa en una tabla de PostgreSQL (contador por IP y por cuenta); sin Flask-Limiter ni Redis. Tabla nueva de infraestructura sin `tenant_id`: esquema propuesto en `plan.md` §3.1 y sexto cambio a `docs/03` (abajo). **Umbrales (referencia, ajustables por configuración):** login 5 fallidos/15 min por cuenta y 20/15 min por IP; validar y aceptar invitación 10/15 min por IP; refresh 30/15 min por IP; `429` genérico; los emails inexistentes también cuentan, sin oráculo. **Purga:** comando operativo documentado `purgar-limite-tasa`, ejecutado por el operador con el rol migrador (único con `DELETE`, solo sobre `limite_tasa`); la aplicación no tiene `DELETE`. |
| Q12 | **[DECIDIDO]** `/health` intacto y `/ready` nuevo. |
| Q13 | **[DECIDIDO]** El token va en el fragmento del enlace (`/invitacion#<token>`). |
| Q14 | **[DECIDIDO]** Mismo sitio + `SameSite=Lax` + cabecera personalizada + comprobación de `Origin`/`Sec-Fetch-Site`. |
| Q15 | **[DECIDIDO]** Ventana de gracia ~10 s; el reuso fuera de ella revoca la familia. |
| Q16 | **[DECIDIDO]** Email existente al aceptar: respuesta idéntica a enlace inválido, `ON CONFLICT DO NOTHING` + excepción estática. |
| Q17 | **[DECIDIDO]** `creada_por` NULL solo por `crear_tenant`; política `RESTRICTIVE` en la aplicación. Exige cambio en `docs/03` (punto 3 abajo). |
| Q18-ii | **[DECIDIDO]** Alcance extra sobre `docs/07` M1 (M6) aceptado. |
| Q9 | **[DECIDIDO]** Contraseña de 10 a 128 caracteres; rechazo de una lista corta de contraseñas comunes (la fija T4); cuerpo máximo de 4 KB en los endpoints de auth. |
| Q11 | **[DECIDIDO]** `SECRET_KEY` de al menos 32 bytes. |
| Q4 | **B:** el admin (o el script) fija el email al invitar; columna `email` en `invitacion`. **Consecuencia (b):** el invitado no escribe el email; `POST /invitaciones/aceptar` recibe `{token, nombre, password}` y `acceso.aceptar_invitacion` toma el email de la invitación. |
| Q18 | Partición 002 (backend) / 002b (OpenAPI + tipos TS + web mínima); B2 y B5 de la spec 001 diferidos. |
| Q20 | **[DECIDIDO 2026-11-12, `/sdd-change`] Opción A:** la aplicación **sí** tiene `SELECT` sobre `refresh_token.token_hash`, porque la rotación (T7) es `UPDATE ... WHERE token_hash = :h` y PostgreSQL exige `SELECT` sobre las columnas del `WHERE`. Es aceptable porque lo guardado es `sha256(sha256(secreto))` (I1), que no autentica, y RLS acota por tenant. Siguen **sin** `SELECT` para la aplicación `usuario.password_hash` e `invitacion.token_hash`. **Descartadas:** B, función `SECURITY DEFINER` `acceso.rotar_refresh` (más superficie en `acceso` y en la lista cerrada C6 sin ganancia real); C, cookie con el `id` de la fila (cambia el formato L1 de Q2 y sigue exigiendo comparar el hash). |
| Q21 | **[DECIDIDO 2026-11-12, decisión humana; cierra I2 de la revisión de seguridad de T2] Opción A:** la invitación de bootstrap de `crear_tenant` queda ligada a un tenant creado en la **misma transacción**. `auth_owner` recibe `SELECT (id, creado_en)` sobre `tenant`, limitado por la política `FOR SELECT TO auth_owner USING (id = app.auth_tenant_nuevo AND creado_en = now())` a la fila que acaba de crear; la política `INSERT` de `invitacion` exige además `EXISTS (SELECT 1 FROM tenant t WHERE t.id = invitacion.tenant_id AND t.creado_en = now())`, y `creado_en` no está en el `GRANT INSERT` de `tenant` (lo fija el `DEFAULT now()`). Así, con el id de un tenant existente en la GUC, `auth_owner` no puede invitar un admin a ese tenant. **Descartada:** aceptar el riesgo (un `auth_owner` comprometido podía tomar el control de un tenant ajeno con una invitación admin). |

## Cambios propuestos a docs/03 (los aplica el humano antes de T1)

Esta spec **no edita** `docs/03`. Texto exacto a incorporar:

1. **Nueva fila en la tabla de entidades:**
   `| `refresh_token` | `id`, `tenant_id`, `membresia_id`, `familia_id`, `token_hash`, `expira_en`, `usado_en`, `revocado_en`, `creado_en` | Refresh con rotación. Se guarda solo `sha256(clave)` (ver formato abajo). `familia_id` agrupa la cadena de rotación. Único `token_hash`. FK compuesta `(tenant_id, membresia_id)` → `membresia`. |`
   Q15 está decidida: añadir al final de la columna de notas "El reuso fuera de la ventana de gracia (~10 s) revoca la familia."
2. **`invitacion`:** añadir la columna `email` (obligatoria, normalizada: `lower(btrim(email))`) y cambiar la nota a: "Enlace de un solo uso. Se guarda `sha256(clave)` con `clave = sha256(token)`, nunca el token. El `email` lo fija quien invita; la aceptación lo toma de la invitación y el invitado no lo escribe."
   **Formato del hash (propuesta para `docs/03`):** `token_hash` es `bytea` de 32 bytes (`CHECK (octet_length(token_hash) = 32)`) en `invitacion` y `refresh_token`. La aplicación calcula `clave = sha256(token)` y la envía a la base en **hex minúsculo de 64 caracteres**; la función hace `sha256(decode(p_clave, 'hex'))` y compara con `token_hash`. Lo que se almacena es, por tanto, `sha256(clave)`, que no sirve como credencial.
3. **`invitacion.creada_por`:** `NULL` permitido; `NULL` significa "creada por el operador (script)". La FK `(tenant_id, creada_por)` → `membresia (tenant_id, usuario_id)` usa `MATCH SIMPLE`. Los endpoints de la aplicación solo insertan con `creada_por` no nulo.
4. **CHECKs y normalización:** `usuario.email` e `invitacion.email` con `CHECK (email = lower(btrim(email)))` e índice único sobre `usuario.email`; `membresia.rol` e `invitacion.rol` con `CHECK (rol IN ('admin','contador'))`.
5. **Nota general:** `usuario` y `tenant` no son legibles por el rol de aplicación fuera de la membresía del tenant fijado y no reciben `INSERT`/`UPDATE` de la aplicación; las altas se hacen por funciones del esquema `acceso` y por el script del operador.
6. **Nueva tabla de infraestructura `limite_tasa` (Q10, DECIDIDO; la aplica el humano antes de T10, no de T1):** tabla **sin `tenant_id`** porque cuenta intentos por IP y por cuenta **antes** de conocer el tenant y no guarda datos de negocio. Justificación, columnas, RLS y `GRANT` mínimos en `plan.md` §3.1 (texto a pegar). Se añade como excepción cerrada y con prueba propia al catálogo de A2, junto con `alembic_version`, `tenant` y `usuario`.

## Problema

La fundación (spec 001) dejó el patrón de aislamiento (RLS, rol de aplicación, `tenant_session`) pero no hay usuarios, tenants ni autenticación. Sin ellos no se puede construir ninguna pantalla de `/contar` ni `/admin`, ni probar roles o aislamiento sobre tablas reales. Además, **el login ocurre antes de conocer el tenant**, y `usuario` es global, mientras RLS exige un tenant fijado. Bajo `FORCE ROW LEVEL SECURITY` ni siquiera el dueño de una tabla (ni una función `SECURITY DEFINER` que corra como él) ve filas sin una política que lo cubra.

## Usuarios

| Usuario | Necesidad |
|---|---|
| Operador técnico | Crear un tenant y su primer admin por script/CLI (no hay pantalla de alta, `docs/03`) |
| `admin` | Invitar usuarios con un rol y un email, y compartir el enlace (WhatsApp, T5) |
| `contador` / invitado | Aceptar la invitación, definir su contraseña y entrar; llegar a `/contar` |
| Todos | Cerrar sesión |
| Reviewer / security-reviewer | Pruebas que demuestren aislamiento por RLS y 403 por rol |

## Alcance

### Incluye

- Tablas `tenant`, `usuario`, `membresia`, `invitacion` y `refresh_token`, cada una con RLS forzada, política y `GRANT` mínimos (por columna donde se indica) en su misma migración. `tenant` y `usuario` son globales: ver R4.
- Esquema `acceso` con rol dueño `auth_owner` y funciones `SECURITY DEFINER` (R4).
- Tabla de infraestructura `limite_tasa` (sin `tenant_id`) para los límites de tasa, creada en T10 (Q10, `plan.md` §3.1).
- Script/CLI del operador: crea un `tenant` y la primera invitación `admin` llamando a `acceso.crear_tenant` (R6).
- CU-ACC-01 login, CU-ACC-02 invitar, CU-ACC-03 aceptar invitación, CU-ACC-04 logout, más refresh y consulta del usuario actual.
- Roles `admin` | `contador` verificados en el servidor; el token lleva un solo tenant.
- Prueba de aislamiento entre dos tenants y 403 de `contador` en una ruta de admin.
- Deuda de la spec 001 que aplica a auth: `/ready`, límites de tasa, tokens fuera de logs, redacción de `DBAPIError`, `SECRET_KEY` validada (B3 de T7), verificación del rol de aplicación al arrancar (M2 de T6), cookie `Secure` por defecto (B4 de T7), guardián de residuos bajo RLS, pruebas RLS recomendadas.

### No incluye

- Desactivar usuarios o membresías (CU-ACC-05), recuperar o cambiar contraseña, vincular un usuario existente a otro tenant (P17).
- Listar usuarios o invitaciones; revocar invitaciones.
- Pantalla de alta de tenant; proveedor de correo (T5); Supabase Auth.
- App shell, sistema de diseño (`docs/08`); ubicaciones, activos, sesiones, precios.
- Despliegue y hosting del backend (T10 de `docs/05`).
- **Diferidos (Q18, DECIDIDO):** B2 (montaje `./backend:/app` de solo lectura) y B5 (imágenes por digest) de la spec 001.
- **Spec 002b:** OpenAPI y tipos TypeScript (R17), web mínima (R18).

### Alcance extra sobre `docs/07` M1 (M6) — [DECIDIDO] aceptado (Q18-ii)

`docs/07` M1 define CU-ACC-01..04. Esta spec añade: refresh y `GET /auth/me`; `GET /ready`; límites de tasa; `POST /invitaciones/validar`; verificación de rol de base y `SECRET_KEY` al arrancar; guardián de residuos bajo RLS; cabeceras de seguridad y límites de tamaño.

## Requisitos (EARS)

**R1 — Esquema.** El sistema debe crear `tenant`, `usuario`, `membresia`, `invitacion` y `refresh_token` con las columnas de `docs/03` (actualizado con los cambios propuestos arriba) y ninguna más. Dinero no interviene. `usuario.email` e `invitacion.email` se guardan normalizados (`lower(btrim())`) con `CHECK` y la aplicación normaliza antes de comparar; `rol` con `CHECK (rol IN ('admin','contador'))`.

**R2 — Patrón RLS.** Cuando se cree una tabla con `tenant_id` (`membresia`, `invitacion`, `refresh_token`), la misma migración debe incluir `ENABLE` + `FORCE ROW LEVEL SECURITY`, la política `tenant_isolation` **`TO` el rol de aplicación de forma explícita** (`USING` y `WITH CHECK`, con `NULLIF(current_setting('app.tenant_id', true), '')::uuid`), sin políticas `PUBLIC` ni `FOR ALL` auxiliares, y los `GRANT` mínimos al rol de aplicación, sin `DELETE` (constitución §6). Toda restricción adicional (p. ej. `creada_por IS NOT NULL` en `invitacion`) se expresa como política **`RESTRICTIVE`** `FOR INSERT TO <rol de aplicación>` (o separando `tenant_isolation` por comando), nunca como una política permisiva extra ni `FOR ALL`: las permisivas se combinan con OR y anularían la restricción. El `downgrade` los revierte en orden inverso.

**R3 — Claves e integridad.** Toda `UNIQUE` natural de tablas con tenant incluye `tenant_id`. Las tablas padre referenciadas llevan `UNIQUE (tenant_id, id)`; las referencias entre tablas con tenant son claves foráneas compuestas (p. ej. `invitacion (tenant_id, creada_por) → membresia (tenant_id, usuario_id)`, `refresh_token (tenant_id, membresia_id) → membresia (tenant_id, id)`). `creada_por` es nulo solo si lo inserta `acceso.crear_tenant` (script); con `MATCH SIMPLE` la clave no se evalúa en ese caso (Q17, DECIDIDO).

**R4 — Tablas globales y acceso previo al tenant (Q1, A1 con C1–C10).**
- **R4a Esquema y rol.** Las funciones viven en el esquema `acceso`, **nunca en `public`**. El dueño es `auth_owner`: `NOLOGIN`, sin `rolsuper` ni `rolbypassrls`, no dueño de ninguna tabla, y la aplicación no puede asumirlo (`SET ROLE`). Ni el rol de aplicación ni `anon`, `authenticated` o `service_role` (Supabase) pueden hacerlo.
- **R4b Privilegios de funciones.** Orden de la migración (C3): `CREATE FUNCTION`, `REVOKE ALL ... FROM PUBLIC, anon, authenticated, service_role`, `GRANT EXECUTE` solo al rol de aplicación (`buscar_login`, `validar_invitacion`, `aceptar_invitacion`) o solo al rol migrador (`crear_tenant`, nunca al de aplicación), `ALTER FUNCTION ... OWNER TO auth_owner`. Se cierra la Data API de Supabase para el esquema `acceso` y se revoca lo heredado en `public` (`REVOKE` en cada tabla nueva a `anon`, `authenticated`, `service_role`; deuda T6).
- **R4c Cuerpo de las funciones (C2, I6).** `SET search_path = pg_catalog, pg_temp`; todos los objetos calificados con esquema y ninguno resuelto vía `public`; `STRICT`; SQL estático (sin `EXECUTE` ni `format`); `set_config(..., true)` local al inicio de la función; una GUC distinta por función y tabla (I2).
- **R4d Políticas del dueño (I2, I3, I4).** Políticas por comando (`SELECT`/`INSERT`/`UPDATE`; nunca `FOR ALL`), todas `TO auth_owner`, acotadas por la GUC de la función. Concretamente: `invitacion` `UPDATE USING (token_hash = clave AND usada_en IS NULL AND expira_en > now()) WITH CHECK (usada_en IS NOT NULL)` con `GRANT UPDATE (usada_en)`; `membresia` `INSERT WITH CHECK` ligado a la invitación recién consumida: existe una `invitacion` con ese `tenant_id`, el `token_hash` de la clave de la función, `usada_en = now()` (la de esta transacción), `rol` igual al de la membresía, y `usuario_id` igual al de la GUC `app.auth_usuario_nuevo` que la función fija tras crear el usuario; `usuario` `INSERT WITH CHECK` (existe una invitación consumida en esta transacción con esa clave y `email` igual al del usuario; el email sale de la invitación, sin GUC de email nuevo); `tenant` y `invitacion` reciben además `INSERT` del dueño **solo** para `crear_tenant` (R6). Las políticas `tenant_isolation` de la aplicación no cambian y no hay políticas `PUBLIC`.
- **R4e Privilegios por columna (I5).** Aplicación: `usuario` `SELECT (id, email, nombre, activo)` (sin `password_hash`); `invitacion` sin `token_hash` en `SELECT` e `INSERT` limitado a columnas sin `usada_en`; `refresh_token` con `SELECT` que **sí** incluye `token_hash` (única excepción, Q20); sin `INSERT`/`UPDATE` sobre `usuario`, `tenant` ni `membresia`.
- **R4f Tablas globales.** `tenant` y `usuario` no llevan `tenant_id` de negocio; RLS forzada con lectura solo por membresía en el tenant fijado. Ninguna tabla se omite sin estar en la lista cerrada de excepciones de la prueba de catálogo, con prueba propia.
- **R4g Supabase (C8).** El diseño se valida con el rol `postgres` real de Supabase (no superusuario) antes del piloto; es condición de salida de la fase, no de T1. **Nota (revisión de seguridad de T2):** en Supabase el rol creador (no superusuario, con `CREATEROLE`) recibe `auth_owner` con `INHERIT` por `createrole_self_grant`, y esa membresía hereda los `GRANT` y las políticas `TO auth_owner`; C8 debe comprobarlo y quitarla o dejarla `INHERIT FALSE`.

**R5 — Roles de base.** El rol de aplicación no tiene `DELETE` sobre ninguna tabla, `INSERT`/`UPDATE` solo donde se justifique en `plan.md` §3, no es dueño de las tablas, ni superusuario ni `BYPASSRLS` (R4c de la spec 001). `auth_owner` tampoco es superusuario ni `BYPASSRLS` y no recibe `DELETE`. "Sin `DELETE`" aplica al rol de la aplicación, a `auth_owner` y a `anon`/`authenticated`/`service_role`; única excepción: el migrador recibe `DELETE` solo sobre `limite_tasa` para la purga operativa de ventanas vencidas (`plan.md` §3.1).

**R6 — Script del operador (consecuencia de Q1).** El migrador no es superusuario ni `BYPASSRLS` y, bajo `FORCE ROW LEVEL SECURITY`, ninguna política cubre su `INSERT` en `tenant` e `invitacion` (las `tenant_isolation` son `TO` el rol de aplicación). Por eso el script **no inserta directo**: cuando el operador lo ejecute con el nombre del tenant y el email del primer admin, debe llamar a `acceso.crear_tenant(p_nombre, p_email, p_clave)`, función `SECURITY DEFINER` con dueña `auth_owner` (patrón A1 de R4), que crea el `tenant` y una `invitacion` de rol `admin` **en una sola transacción** (`creada_por` NULL, expiración 24 h) y devuelve el `tenant_id`. El script genera el token, calcula `clave = sha256(token)` (hex) y solo envía la clave; muestra el enlace una sola vez por la salida estándar, sin guardarlo ni registrarlo. Reglas: `EXECUTE` solo para el rol migrador (no para el de aplicación ni `anon`/`authenticated`/`service_role`); políticas por comando `TO auth_owner` acotadas por GUC propia: `tenant` `INSERT WITH CHECK (id = app.auth_tenant_nuevo)` e `invitacion` `INSERT WITH CHECK (tenant_id = app.auth_tenant_nuevo AND rol = 'admin' AND creada_por IS NULL AND usada_en IS NULL AND expira_en <= now() + interval '24 hours')`, con `GRANT INSERT` mínimo al dueño; esas políticas entran en la lista cerrada de A2/C6 y las revisa el `security-reviewer` en T2. El script solo crea rol `admin`, usa credenciales del migrador **solo por variable de entorno** (nunca argumento de línea de comandos ni archivo versionado) y su prueba (T5) corre con un migrador **sin superusuario ni `BYPASSRLS`** que la propia prueba crea, no con `POSTGRES_USER` (I11). Expiración de la invitación bootstrap: 24 h (Q3, DECIDIDO). Rol del migrador sin superusuario (Q5, DECIDIDO).

**R7 — Login (CU-ACC-01).** Cuando un usuario envíe email y contraseña válidos con membresía activa, el sistema debe emitir un token de acceso de corta duración con un solo tenant y rol, y un refresh token en cookie `__Secure-` `HttpOnly`, `Secure`, `SameSite=Lax`, `Path` acotado a `/auth`. Si las credenciales son inválidas, el usuario está inactivo o la membresía está inactiva, responde con mensaje genérico. El hash de la contraseña se verifica siempre (hash simulado del mismo costo si el email no existe). Se limita la longitud de la contraseña y el tamaño del cuerpo antes de hashear. Si hubiera más de una membresía activa, falla cerrado (Q6, DECIDIDO). TTL: acceso 15 min, refresh 7 días (Q7, DECIDIDO).

**R8 — Refresh y logout (CU-ACC-04, Q2 DECIDIDO).** Cuando llegue una petición de refresh con la cookie `<tenant_id>.<secreto>`, el servidor fija ese tenant con `tenant_session` y busca el hash bajo RLS normal. La rotación es **un único `UPDATE` atómico** (`usado_en` solo si es nulo, no revocado, no vencido) que emite el siguiente refresh de la misma `familia_id`. Q15 (DECIDIDO): un refresh ya usado dentro de una ventana de gracia (~10 s) responde `401` sin revocar la familia; fuera de ella, el reuso revoca toda la familia (`revocado_en`). Cuando se haga logout, se invalida **el refresh de la cookie** (familia completa) y se limpia la cookie; no depende del token de acceso. El rol de aplicación solo tiene `UPDATE (usado_en, revocado_en)` sobre `refresh_token`. Refresh vencido, usado o revocado → `401`.

**R9 — Autorización por rol.** Cuando llegue una petición a un endpoint protegido, el servidor debe validar el token, abrir `tenant_session` y **leer rol y `activa` de `membresia` en cada petición** (no del claim; el claim solo propone el tenant y el usuario). Un endpoint solo de admin llamado por un `contador` responde `403`; sin token o inválido, `401`. El rol nunca se toma del cuerpo ni de parámetros. Esconder botones no es seguridad.

**R10 — Invitar (CU-ACC-02).** Cuando un `admin` cree una invitación con un rol y un email, el sistema debe generar un token aleatorio de alta entropía; la app calcula `clave = sha256(token)` y la base guarda `sha256(clave)` (`bytea`, ver formato en los cambios a `docs/03`), de modo que el valor almacenado no sirve como credencial (I1); fijar `expira_en` y mostrar el enlace una sola vez. El tenant es el del admin autenticado y `creada_por` es el `usuario_id` del admin (una política `RESTRICTIVE` `FOR INSERT` del rol de aplicación exige `creada_por IS NOT NULL`, I11; R2). Expiración: 72 h para invitaciones normales y 24 h para el bootstrap (Q3, Q7, DECIDIDO).

**R11 — Aceptar invitación (CU-ACC-03).** Cuando el invitado envíe un token vigente y no usado con nombre y contraseña (`POST /invitaciones/aceptar` recibe `{token, nombre, password}`, **sin email**: lo fijó el admin y no se vuelve a pedir), el sistema debe ejecutar **una sola operación atómica en la base** (`acceso.aceptar_invitacion(p_clave, p_nombre, p_password_hash)`) que: marque `usada_en` con `UPDATE` condicional devolviendo el `email`, `tenant_id` y `rol` de la invitación, cree el `usuario` con **ese email**, y cree la `membresia` con el rol de la invitación. No existe la GUC `app.auth_email_nuevo`. `acceso.validar_invitacion` sigue devolviendo solo vigente o no (sin email, tenant ni rol). Si cualquier paso falla, se revierte completo y la invitación **sigue sin usar**. La emisión de sesión ocurre **después** del `COMMIT`; si falla, la cuenta existe, la respuesta es `500` genérico y el invitado entra con el login normal. Enlace vencido, usado o inexistente responden el mismo error. Con dos aceptaciones concurrentes, solo una gana. Email ya existente (Q16): `INSERT ... ON CONFLICT DO NOTHING` y excepción estática, respuesta indistinguible de `invitacion_invalida` (Q16, DECIDIDO). El token viaja siempre en el cuerpo.

**R12 — Contraseñas.** Solo se guarda el hash **Argon2id** con `argon2-cffi` (Q8, DECIDIDO; no `werkzeug.security`); nunca la contraseña en claro ni en logs o respuestas. Parámetros de Argon2id y hash simulado del mismo costo: `plan.md` §6 y T4. Política (Q9, DECIDIDO): mínimo 10 y máximo 128 caracteres; rechazo de una lista corta de contraseñas comunes (la fija T4); cuerpo máximo de 4 KB en los endpoints de auth.

**R13 — Límites de tasa.** Si se exceden los intentos de login, refresh, validación o aceptación por IP o cuenta, responde `429` sin revelar si la cuenta existe. Almacenamiento (Q10, DECIDIDO): tabla `limite_tasa` de PostgreSQL (contador por IP y por cuenta), sin Flask-Limiter ni Redis; el contador se escribe en una transacción propia para que el fallo del login no lo revierta. Umbrales (Q10, DECIDIDO; referencia, ajustables por configuración, ventana de 15 min): login 5 fallidos por cuenta y 20 por IP; validar y aceptar invitación 10 por IP; refresh 30 por IP; `429` genérico; los emails inexistentes también cuentan, sin oráculo.

**R14 — Secretos en logs y cabeceras.** No se registran tokens de invitación (ruta, query, cuerpo), de acceso, refresh, contraseñas ni `token_hash`. Errores de base con tipo y `sqlstate`, no `str(orig)`. Las respuestas de `/auth` y `/invitaciones` llevan `Cache-Control: no-store` y `Referrer-Policy: no-referrer`. Prueba con `caplog` incluyendo `validar` y `aceptar`.

**R15 — Configuración.** Si `SECRET_KEY` es débil (longitud mínima, Q11 DECIDIDO: 32 bytes), el sistema falla al arrancar fuera de pruebas, sin imprimir su valor. Al arrancar verifica que el rol de `DATABASE_URL` no tiene `rolsuper` ni `rolbypassrls`. `ENVIRONMENT` por defecto es producción: cookie `Secure` salvo `ENVIRONMENT=development` explícito; `docker-compose.yml` y `.env.example` lo fijan. **JWT:** algoritmo fijo `HS256` (rechaza `none` y cualquier otro), `exp` e `iss` obligatorios, clave de firma derivada de `SECRET_KEY` con un contexto propio (no se reutiliza cruda en otros usos).

**R16 — Readiness.** `GET /ready` verifica la base con respuesta cacheada unos segundos y sin detalles. `/health` no cambia (Q12, DECIDIDO).

**R17 — Contrato (spec 002b).** Ver `specs/002b-acceso-web/spec.md`.

**R18 — Web (spec 002b).** Ver `specs/002b-acceso-web/spec.md`.

## Criterios de aceptación

| # | Criterio | Verificación |
|---|---|---|
| A0 | **Prerrequisito P0 (antes de T1):** tras `docker compose down -v && docker compose up -d db` (el script de init solo corre con volumen vacío) y en la CI (que ejecuta `docker/postgres/init/01-app-role.sh`), `auth_owner` existe `NOLOGIN`, sin `rolsuper` ni `rolbypassrls`; ejecutar el script dos veces no falla (idempotente) | `psql -c "select rolname, rolcanlogin, rolsuper, rolbypassrls from pg_roles where rolname='auth_owner'"` + CI |
| A1 | `alembic upgrade head`, `downgrade base`, `upgrade head` funcionan con las 5 tablas, el esquema `acceso`, las funciones (incluida `crear_tenant`) y las políticas del dueño (el rol `auth_owner` lo crea el script de init, P0) | CI / local |
| A2 | **Catálogo cerrado (C6):** toda tabla de `public` fuera de la lista de excepciones (`alembic_version`, `tenant`, `usuario`, `limite_tasa`) tiene `tenant_id`, `relrowsecurity`, `relforcerowsecurity`, `tenant_isolation` `TO` rol de aplicación y ningún `DELETE`; las funciones de `acceso` (`buscar_login`, `validar_invitacion`, `aceptar_invitacion`, `crear_tenant`) coinciden **exactamente** con una lista cerrada (`prosecdef` verdadero, dueño `auth_owner`, `proconfig` con `search_path` fijo, `proacl` solo con el rol de aplicación, o solo con el migrador en `crear_tenant`); las políticas `TO auth_owner` (incluidas las de `crear_tenant` sobre `tenant` e `invitacion`) y las `RESTRICTIVE` de la aplicación forman listas cerradas; ningún rol distinto tiene `DELETE`, **salvo** el migrador sobre `limite_tasa` (purga operativa, `plan.md` §3.1), que la prueba distingue y exige que exista solo ahí (la aplicación, `anon`, `authenticated` y `service_role` nunca tienen `DELETE`); no hay funciones propias en `public`; `tenant`, `usuario` y `limite_tasa` (cuando exista, T10) tienen su propia prueba; la lista de excepciones ya incluye `limite_tasa` desde T1 | `pytest` |
| A3 | **Con tenant A fijado, nunca se ven ni se tocan filas de B** en `membresia`, `invitacion`, `refresh_token`: `SELECT` cero filas y `UPDATE` cero filas por ORM, `get_bind`, SQL crudo y `join`; `DELETE` falla con `insufficient_privilege`; `usuario` y `tenant` de B no visibles | `pytest` |
| A4 | **Sin tenant fijado no se lee ni se escribe**, también en una conexión del pool que ya usó otro tenant | `pytest` |
| A5 | `WITH CHECK` impide insertar `invitacion`/`refresh_token` con `tenant_id` de otro tenant y que un `UPDATE` cambie `tenant_id` | `pytest` |
| A6 | Atributos de roles (`rolsuper`, `rolbypassrls` falsos) y tablas; el arranque falla si el rol es inseguro; **la aplicación no puede `SET ROLE auth_owner` y llamar a las funciones con `SET ROLE anon`/`authenticated` da `permission denied` (C7)** | `pytest` |
| A7 | El script, vía `acceso.crear_tenant`, crea tenant + invitación admin en una transacción; el enlace sale una vez por stdout; no aparece en logs ni en base (solo `sha256(clave)`); solo rol admin y `expira_en` ≤ 24 h; **la prueba corre con un migrador de prueba sin superusuario ni `BYPASSRLS`** (rol creado por la prueba) y confirma que ese rol **no** puede `INSERT` directo en `tenant`/`invitacion`, que el rol de aplicación no puede ejecutar `crear_tenant` y que `crear_tenant` no crea rol `contador` ni `creada_por` no nulo | `pytest` + manual |
| A8 | Un admin invita a un contador (con email); el contador acepta, entra y recibe `403` en un endpoint de admin | integración |
| A9 | Enlace vencido, usado o inexistente da el mismo error; dos aceptaciones concurrentes: una gana; el usuario creado usa el email de la invitación (el cuerpo no lleva email) | `pytest` (dos conexiones) |
| A10 | Credenciales inválidas, usuario inactivo y membresía inactiva: misma respuesta; tiempo no distingue (hash simulado del mismo costo) | `pytest` |
| A11 | Refresh válido emite acceso; tras logout (por cookie de refresh) deja de servir (`401`) | `pytest` |
| A12 | Cada endpoint protegido: prueba de rol (401/403) y de aislamiento | `pytest` |
| A13 | `429` por IP y cuenta sin revelar existencia; el contador sobrevive al fallo de la petición y es compartido entre workers (tabla `limite_tasa`); la aplicación no puede `DELETE` y solo puede `UPDATE` la columna `intentos`; tiene `SELECT` de la tabla (necesario para el `RETURNING`), que solo contiene hashes y contadores, sin datos en claro | `pytest` |
| A14 | `caplog` sin token de invitación, acceso, refresh, contraseña ni hashes | `pytest` |
| A15 | `/ready` responde 200/503 sin detalles | `pytest` |
| A18 | Sin secretos en el repo; `.env.example` lista variables nuevas sin valores (se verifica en T10, cierre de la spec) | `git grep` |
| A19 | Funciones de Q1 sin fuga: cada función devuelve solo lo que su parámetro exacto identifica; cero filas con parámetro vacío, nulo o comodines; sin contexto residual; la aplicación no lee `usuario` fuera de ellas; el hash almacenado no sirve como clave (I1) | `pytest` |
| A20 | Email de la invitación ya existente al aceptar: respuesta indistinguible de enlace inválido, transacción revertida, invitación sin consumir; sin diferencia de tiempo apreciable | `pytest` |
| A21 | Con `ENVIRONMENT` sin definir, cookie `Secure`; sin `Secure` solo con `development` explícito | `pytest` |
| A22 | Si falla la emisión de sesión tras aceptar, la cuenta existe y el login funciona | `pytest` |
| A23 | **Refresh (Q2/I7):** rotación atómica; (Q15) dos refresh concurrentes: uno rota, el otro dentro de la ventana de gracia no revoca, y el reuso fuera de ventana revoca la familia; el rol de aplicación no puede `UPDATE` otras columnas | `pytest` |
| A24 | **Rol desde la base (I9):** si el admin pasa a `contador` o la membresía a inactiva tras emitir el token, la siguiente petición lo refleja (403/401) sin esperar la expiración | `pytest` |
| A25 | **JWT:** token con `alg: none`, otro algoritmo, sin `exp` o `iss`, o `iss` ajeno → `401`; cabeceras `no-store` y `no-referrer` presentes; cuerpo mayor al límite → `413`; contraseña sobre el máximo → rechazada sin hashear | `pytest` |
| A26 | **Pruebas de aislamiento ampliadas (9, `plan.md` §7.2):** ver el plan | `pytest` |

A16 y A17 pasan a la spec 002b.

## Reglas de dominio

- R1 de `docs/03`: toda tabla de negocio con `tenant_id`; el filtro es central y RLS lo hace cumplir.
- El token de acceso lleva **un solo tenant**; `membresia` única por `(tenant_id, usuario_id)`.
- `usuario.email` único y normalizado. Ninguna respuesta debe revelar si un email existe (R7, R11); la aplicación nunca inserta en `usuario` directamente.
- La invitación es de un solo uso; se guarda solo `sha256(clave)` con `clave = sha256(token)`; el token viaja solo en el cuerpo y el invitado no escribe el email.
- Nada se borra: sin `DELETE` en ninguna tabla para la aplicación (única excepción: purga operativa de `limite_tasa` por el migrador, R5).
- Roles `admin` y `contador`, verificados en el servidor contra la base en cada petición.
- Aún no hay precios; P13 se aplicará en las specs que los expongan.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Login y aceptación necesitan leer sin tenant, en tensión con RLS forzada | A1: `auth_owner` con políticas por comando acotadas por GUC (R4); pruebas A2, A19; validación con `postgres` real de Supabase antes del piloto (R4g) |
| Función `SECURITY DEFINER` expuesta por la Data API de Supabase (anon/authenticated) | Esquema `acceso`, `REVOKE ... FROM PUBLIC, anon, authenticated, service_role`, prueba C7 |
| Hash almacenado utilizable como credencial si la base se filtra | Doble hash (I1) |
| `usuario` global filtra datos entre tenants | RLS por membresía, `SELECT` por columna, sin `INSERT`/`UPDATE`; A3 |
| Enumeración de cuentas (mensajes, tiempos, unicidad) | Respuesta genérica, hash simulado del mismo costo, `ON CONFLICT DO NOTHING` + excepción estática; A10, A20 |
| Fuerza bruta y abuso | R13; contador en tabla `limite_tasa`, compartido entre workers (Q10); `X-Forwarded-For` falsificable: confiar solo en el proxy conocido (T10) |
| Token en logs, historial o `Referer` | R14, fragmento (Q13), `Referrer-Policy: no-referrer` |
| Refresh robado | Rotación con familia y detección de reuso (R8, Q15) |
| CSRF sobre refresh/logout | `SameSite=Lax`, cabecera personalizada y comprobación de `Origin`/`Sec-Fetch-Site` (Q14) |
| Rueda binaria de `argon2-cffi` ausente en el despliegue (compilar en la imagen o fallar) | `uv.lock` fijado; T4 verifica que la imagen del `api` instala sin compilador; el despliegue necesita la rueda binaria |
| `limite_tasa` sin `tenant_id` rompe el patrón de la constitución §4 | Tabla de infraestructura sin datos de negocio, excepción cerrada con prueba propia, RLS/GRANT mínimos y cambio explícito a `docs/03` que aplica el humano |
| Esquema fuera de `docs/03` | El humano aplica los cambios propuestos antes de T1 |
| Rol obsoleto en el token tras degradar a un usuario | Rol y `activa` leídos de `membresia` en cada petición (R9) |
| Script del operador sin política bajo `FORCE RLS` (o con `BYPASSRLS`/superusuario implícito) | `acceso.crear_tenant` (patrón A1), `EXECUTE` solo migrador, políticas `TO auth_owner` en la lista cerrada y revisadas por el `security-reviewer` en T2; prueba con migrador sin superusuario ni `BYPASSRLS`; credenciales solo por entorno; enlace solo a stdout |
| Política permisiva extra anula `creada_por IS NOT NULL` (OR entre permisivas) | Política `RESTRICTIVE` `FOR INSERT` (R2); prueba en A2/A26 |
| Script de init con `auth_owner` no corre en un volumen existente | P0 antes de T1; criterio A0 (`down -v`, idempotente, CI); las migraciones fallan con mensaje claro si `auth_owner` no existe |
| Dependencias de auth nuevas | `plan.md` §6; ninguna sin aprobación |

## Preguntas abiertas

Spec aprobada (G1–G3, 2026-11-12). **Decididas:** Q1–Q18 (incluidos Q9, Q10 completa y Q11), Q20 (`/sdd-change`) y Q21 (cierre de I2 de T2). **Siguen abiertas:** Q19 (solo 002b) y C8 (antes del piloto). **Condiciones previas del humano:** T1 no empieza hasta aplicar los cambios 1–5 a `docs/03` y P0 (`auth_owner` en el init); T10 no empieza hasta aplicar el cambio 6 (`limite_tasa`). T4 fija las versiones exactas de `argon2-cffi` y `PyJWT` (Q8) y la lista corta de contraseñas comunes. "Bloquea" coincide con `tasks.md` y `plan.md` §8.

| Pregunta | Estado | Bloquea |
|---|---|---|
| **Cambios a `docs/03`** (los cinco primeros, con el formato `bytea` del hash) y **P0** (ampliar `docker/postgres/init/01-app-role.sh` con `auth_owner`; A0) | Los aplica el humano antes de T1 | T1 |
| **Cambio 6 a `docs/03`** (`limite_tasa`, `plan.md` §3.1) | Los aplica el humano antes de T10 | T10 |
| **Q1 — detalle** de las políticas y GUC exactas (I2/I3), incluidas las de `crear_tenant` y `membresia` | Diseño decidido; el `security-reviewer` revisa el SQL concreto en T2 | T2, T3 |
| **Q3, Q5, Q6, Q7, Q9, Q10, Q11, Q12–Q18, Q20, Q21** | **[DECIDIDO]** (tabla de decisiones) | — |
| **Q8** Dependencias `argon2-cffi` y `PyJWT` | **[DECIDIDO]**; falta fijar versiones exactas y parámetros de Argon2id en T4 | T4 |
| **Q19** (solo 002b) Origen en desarrollo: proxy de Vite | `[PENDIENTE]` | 002b |
| **P17** (`docs/05`) Desactivar, recuperar, vincular | Abierta; fuera de 002 | — |
| **T5 / T10** de `docs/05` (invitación sin correo; hosting) | Abiertas en `docs/05` | — |
| **C8** Validar con `postgres` real de Supabase | Antes del piloto, no bloquea T1–T10 | Piloto |
