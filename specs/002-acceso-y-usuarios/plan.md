# Plan 002 — Acceso y usuarios

> **Estado:** Aprobada (G1–G3, 2026-11-12). **Condición:** T1 no empieza hasta que el humano aplique los cambios 1–5 a `docs/03` y P0 (`auth_owner` en el init); T10 no empieza hasta que aplique el cambio 6 (`limite_tasa`). Incorpora las decisiones humanas de la ronda G1 (Q1–Q18 salvo Q19) y los dos veredictos del `security-reviewer`. Backend en 10 tareas (T1–T10). Siguen abiertas Q19 (solo 002b) y C8 (antes del piloto); ver `spec.md` §Preguntas abiertas. Cubre el backend (T1–T10); OpenAPI y web están en `specs/002b-acceso-web/`.

## 1. Enfoque

Primero el esquema con RLS (la base manda), luego el esquema `acceso` con el rol dueño, sus políticas y funciones y sus pruebas de aislamiento, después credenciales, configuración segura y script del operador, los endpoints (login, refresh/logout, roles e invitar, aceptar) y al final los límites y la deuda operativa. Reglas de auth en `app/auth/` sin depender de Flask cuando sea posible.

## 2. Arquitectura

- `backend/app/auth/`: `routes.py` (`/auth`), `service.py`, `credentials.py` (hash, tokens, JWT), `decorators.py` (`require_auth`, `require_role`).
- `backend/app/invitaciones/`: `routes.py`, `service.py`.
- `backend/app/cli.py`: comando para crear tenant y primera invitación admin.
- `backend/app/db.py`: se reutiliza `tenant_session`. Las funciones de `acceso` se invocan con una función propia de `db.py` sin tenant (como `ping_database`), nunca por `text()` dentro de `tenant_session`.

### 2.1 Acceso previo al tenant (Q1 DECIDIDO: A1 con C1–C10)

**Rol y esquema**
- Rol `auth_owner`: `NOLOGIN`, sin `rolsuper` ni `rolbypassrls`, no dueño de tablas, no miembro del rol de aplicación ni al revés. Se crea en el script de init de la spec 001 (`docker/postgres/init/01-app-role.sh`), no en migraciones. **Prerrequisito P0, antes de T1:** lo amplía el humano (cambio de roles, junto con `docs/03`), no una tarea de esta spec. El script solo corre con el volumen vacío (`docker compose down -v` para reiniciar), debe ser idempotente (`CREATE ROLE` condicional) y la CI ya lo ejecuta (`ci-backend.yml`); criterio verificable A0 en `spec.md`. Las migraciones 0002, 0003 y 0004 fallan con mensaje claro si `auth_owner` no existe. **Membresía transitoria:** `ALTER FUNCTION ... OWNER TO auth_owner` exige que el migrador sea miembro de `auth_owner` y que `auth_owner` tenga `CREATE` en el esquema `acceso`. Por eso la migración 0004 hace `GRANT auth_owner TO <migrador> WITH INHERIT FALSE, SET TRUE` (la cláusula `WITH ... ` solo donde PG ≥ 16 la admite; PostgreSQL 17 en local, CI y Supabase) y `GRANT CREATE ON SCHEMA acceso TO auth_owner` **solo durante la migración**, y los revoca (`REVOKE CREATE ON SCHEMA acceso FROM auth_owner` y la membresía) inmediatamente después del `ALTER FUNCTION`. Aplica también en local y CI: con `POSTGRES_USER` superusuario como migrador basta (la membresía es implícita), pero el paso queda escrito y es idempotente. En Supabase, el rol administrador debe poder recibir esa membresía transitoria. Prueba (C5): tras `upgrade head`, `auth_owner` no tiene `CREATE` en `acceso` (`has_schema_privilege`) ni el migrador queda como miembro.
- Esquema `acceso`, propiedad del migrador, con `USAGE` solo para el rol de aplicación y `auth_owner`. Se cierra la Data API de Supabase para `acceso`; en `public` se revoca todo lo heredado a `anon`, `authenticated`, `service_role`.

**Funciones** (`SECURITY DEFINER`, `STRICT`, `SET search_path = pg_catalog, pg_temp`, todo calificado, sin `public`, SQL estático sin `EXECUTE`/`format`):

| Función | Entrada | Efecto | GUC propia |
|---|---|---|---|
| `acceso.buscar_login(p_email)` | email normalizado | solo lectura: `usuario_id`, `password_hash`, `activo` y la membresía activa (`tenant_id`, `rol`) | `app.auth_email`, luego `app.auth_usuario` para leer `membresia` |
| `acceso.validar_invitacion(p_clave)` | `sha256(token)` hex | solo lectura: indica si es vigente y no usada; sin tenant, rol ni creador | `app.auth_inv_validar` |
| `acceso.aceptar_invitacion(p_clave, p_nombre, p_password_hash)` | clave (hex), nombre, hash de contraseña; **sin email** (Q4=B) | atómica: `UPDATE invitacion` condicional (`RETURNING email, tenant_id, rol`), `INSERT usuario` con el email de la invitación `... ON CONFLICT DO NOTHING` (sin fila → excepción estática), fija `app.auth_usuario_nuevo`, `INSERT membresia`; devuelve `usuario_id`, `tenant_id`, `rol`. El `id` del usuario se genera dentro de la función (sin `INSERT ... RETURNING`, que exigiría una política `SELECT`) | `app.auth_inv_aceptar`, `app.auth_usuario_nuevo` (no existe `app.auth_email_nuevo`) |
| `acceso.crear_tenant(p_nombre, p_email, p_clave)` | nombre, email del primer admin (normalizado), clave (hex) | atómica: `INSERT tenant` e `INSERT invitacion` (`rol` `admin`, `creada_por` NULL, `expira_en = now() + interval '24 hours'`, Q3 DECIDIDO); devuelve `tenant_id`. **`EXECUTE` solo para el rol migrador**, no para la aplicación | `app.auth_tenant_nuevo` |

La función calcula `token_hash = sha256(decode(p_clave, 'hex'))` con la función de `pg_catalog` (sin extensión) y compara con la columna `bytea` (I1). Formato: `token_hash` `bytea(32)`; la clave viaja en hex minúsculo de 64 caracteres (validado por la función; otro formato → cero filas).

**Doble hash (I1).** La app calcula `clave = sha256(token)` y envía solo `clave`; la base guarda `sha256(clave)` (`bytea`). El hash almacenado no sirve como credencial. Igual para el secreto del refresh. La aplicación, al insertar `invitacion` o `refresh_token`, calcula en Python `sha256(clave)` en bytes.

**Políticas del dueño (I2, I3, I4).** Por comando, nunca `FOR ALL`, todas `TO auth_owner`, una GUC por función/tabla, cero filas con GUC vacía:

| Tabla | Comando | Política (esquema; SQL exacto lo fija T2 con el `security-reviewer`) |
|---|---|---|
| `invitacion` | SELECT | `token_hash` = clave de la función (lectura de `tenant_id`, `rol`, `email`, `expira_en`, `usada_en`) |
| `invitacion` | UPDATE | `USING (token_hash = clave AND usada_en IS NULL AND expira_en > now()) WITH CHECK (usada_en = now())` (consumo en esta transacción, no `IS NOT NULL`); `GRANT UPDATE (usada_en)` |
| `usuario` | SELECT | `email = clave` (login) |
| `usuario` | INSERT | `WITH CHECK (EXISTS (invitacion con token_hash = clave de la función, usada_en = now() y email = usuario.email))` (el email sale de la invitación; sin GUC de email) |
| `membresia` | SELECT | `usuario_id = clave` (login) |
| `membresia` | INSERT | `WITH CHECK (EXISTS (invitacion con tenant_id = membresia.tenant_id, token_hash = clave de la función, usada_en = now() (la de esta transacción) y rol = membresia.rol) AND usuario_id = app.auth_usuario_nuevo)`: rol y usuario ligados a la invitación recién consumida |
| `tenant` | INSERT | `WITH CHECK (id = app.auth_tenant_nuevo)`; `GRANT INSERT (id, nombre)` (sin `creado_en`, que fija el `DEFAULT now()`); solo lo usa `crear_tenant` (R6). Sin `UPDATE` ni `DELETE` |
| `tenant` | SELECT | Q21: `USING (id = app.auth_tenant_nuevo AND creado_en = now())`, con `GRANT SELECT (id, creado_en)`: `auth_owner` solo lee la fila creada en su misma transacción (la necesita el `EXISTS` de la política `INSERT` de `invitacion`) |
| `invitacion` | INSERT | `WITH CHECK (tenant_id = app.auth_tenant_nuevo AND rol = 'admin' AND creada_por IS NULL AND usada_en IS NULL AND expira_en <= now() + interval '24 hours' AND EXISTS (SELECT 1 FROM tenant t WHERE t.id = invitacion.tenant_id AND t.creado_en = now()))`; solo `crear_tenant` y solo para el tenant creado en la misma transacción (Q21) |

**Por qué `crear_tenant` y no INSERT directo del migrador (consecuencia de Q1).** El migrador no es superusuario ni `BYPASSRLS` y, bajo `FORCE RLS`, las `tenant_isolation` de `tenant` e `invitacion` son `TO <rol de aplicación>`: no hay política que cubra su INSERT. Se resuelve con el mismo patrón A1. Las políticas del dueño para `crear_tenant` están en la lista cerrada de A2/C6 y **el `security-reviewer` las revisa en T2** junto con las demás.

Las `tenant_isolation` de la aplicación son `TO <rol de aplicación>` explícito, sin políticas `PUBLIC` (I4). **`invitacion` y `creada_por`:** la restricción `creada_por IS NOT NULL` es una política **`RESTRICTIVE` `FOR INSERT TO <rol de aplicación>`** (`invitacion_creada_por_no_nula`), o bien `tenant_isolation` separada por comando; nunca una permisiva adicional ni `FOR ALL`, porque las permisivas se combinan con OR. Al ser `TO` el rol de aplicación, no afecta a `auth_owner`.

**Privilegios por columna (I5).** Aplicación: `usuario` `SELECT (id, email, nombre, activo)`; `invitacion` `SELECT` de todo salvo `token_hash` e `INSERT (id, tenant_id, rol, email, token_hash, expira_en, creada_por)` sin `usada_en`; `refresh_token` `SELECT` incluido `token_hash` (Q20). El dueño: solo las columnas que cada función necesita (incluye `token_hash` en `invitacion`, requerido por su `WHERE`; ajuste fino en T2). Ninguno con `DELETE`.

**`set_config` (I6):** `set_config(<guc>, <valor>, true)` al inicio de la función, local a la transacción; la función no deja contexto utilizable por la aplicación y el contexto no sobrevive a la transacción ni a un savepoint (prueba).

**Orden de la migración (C3):** `CREATE FUNCTION` → `REVOKE ALL ... FROM PUBLIC, anon, authenticated, service_role` → `GRANT EXECUTE ... TO <rol de aplicación>` (las tres funciones de login/invitación) o `TO <rol migrador>` (`crear_tenant`; el migrador es `current_user` al migrar, no se hardcodea) → `GRANT CREATE ON SCHEMA acceso TO auth_owner` y membresía transitoria (§2.1, Rol y esquema) → `ALTER FUNCTION ... OWNER TO auth_owner` → `REVOKE CREATE ON SCHEMA acceso FROM auth_owner` y fin de la membresía, de inmediato (C5: `CREATE` no queda abierto). El rol migrador de la CI es superusuario, así que la prueba de T5 usa un migrador de prueba y le otorga `EXECUTE` y `USAGE` sobre `acceso` explícitamente. Nombres de roles con `identifier_preparer.quote`.

**Validación (C8):** con el rol `postgres` real de Supabase (no superusuario) antes del piloto; no bloquea T1–T10. **Nota (revisión de seguridad de T2):** en Supabase el creador de `auth_owner` recibe la membresía con `INHERIT` por `createrole_self_grant`; esa membresía hereda los `GRANT` y las políticas `TO auth_owner`, así que C8 debe comprobarla y quitarla (o dejarla `INHERIT FALSE`). La migración 0003 ya falla si `auth_owner` es miembro de otro rol, pero no mide esta membresía inversa.

### 2.2 Flujos

- **Petición protegida:** validar JWT (HS256 fijo, `exp`, `iss`) → `tenant_session(tenant_id del claim)` → leer de `membresia` `rol` y `activa` del usuario **en cada petición** (no del claim) → comprobar rol del endpoint (I9).
- **Login:** `buscar_login(email)`; hash verificado en Python, con hash simulado del mismo costo si el email no existe; longitud máxima de contraseña antes de hashear. Una sola membresía activa; si hay más, falla cerrado (Q6, DECIDIDO). Luego `tenant_session` y se guarda el refresh.
- **Refresh (Q2, L1):** cookie `__Secure-refresh=<tenant_id>.<secreto>`. El servidor fija el tenant de la cookie y calcula `sha256(sha256(secreto))`. Rotación: **un `UPDATE refresh_token SET usado_en = now() WHERE token_hash = :h AND usado_en IS NULL AND revocado_en IS NULL AND expira_en > now() RETURNING ...`**; si devuelve fila, inserta el siguiente de la misma `familia_id`. Si no devuelve fila (Q15, DECIDIDO): si el refresh se usó hace menos de la ventana de gracia (~10 s) se responde `401` sin revocar; si es reuso fuera de ventana se hace `UPDATE ... SET revocado_en = now()` sobre toda la `familia_id`. Cabecera personalizada obligatoria y comprobación de `Origin`/`Sec-Fetch-Site` (Q14, DECIDIDO).
- **Logout (I8):** usa la cookie de refresh (no depende de un acceso vigente); revoca la familia y limpia la cookie.
- **Validar invitación:** token en cuerpo → `clave = sha256(token)` → `validar_invitacion(clave)`.
- **Aceptar:** cuerpo `{token, nombre, password}` (sin email); hash de contraseña antes de la función; `aceptar_invitacion` atómica, con el email tomado de la invitación; email ya existente, vencido, usado o inexistente → `invitacion_invalida` (Q16, DECIDIDO). Sesión después del `COMMIT` (A22).
- **Tokens:** acceso JWT `HS256`, claims `sub`, `tenant`, `exp`, `iss` (el `rol` del claim es informativo para la web, no se usa para autorizar); clave derivada de `SECRET_KEY` con contexto propio; TTL acceso 15 min y refresh 7 días; invitación 72 h (bootstrap 24 h) (Q7, DECIDIDO). Refresh e invitación opacos, `secrets.token_urlsafe`.
- **Cookie:** `__Secure-` (implica `Secure`), `HttpOnly`, `SameSite=Lax`, `Path=/auth`. Solo con `ENVIRONMENT=development` explícito se omite `Secure` (y entonces el prefijo `__Secure-` no se usa en desarrollo; el nombre lo decide T4/T6).
- **Errores:** JSON uniforme de la spec 001; códigos `credenciales_invalidas`, `no_autenticado` (401), `prohibido` (403), `invitacion_invalida`, `demasiadas_solicitudes` (429), `cuerpo_demasiado_grande` (413).
- **Cabeceras y límites (T4):** `Cache-Control: no-store` y `Referrer-Policy: no-referrer` en `/auth/*` e `/invitaciones/*` (T4 implementa y prueba el mecanismo; la prueba por ruta de cada endpoint va en T6/T8/T9 cuando existan); límite de tamaño de cuerpo (`MAX_CONTENT_LENGTH`) y de longitud de contraseña; contraseña de 10 a 128 caracteres con rechazo de una lista corta de comunes que fija T4 (Q9 DECIDIDO); cuerpo máximo de 4 KB en los endpoints de auth.
- **Logs:** `DBAPIError` con tipo y `sqlstate`; sin tokens, hashes ni contraseñas; el enlace del script solo va a stdout.
- **Arranque:** valida `SECRET_KEY` (≥ 32 bytes, Q11 DECIDIDO) y `rolsuper`/`rolbypassrls` del `current_user`.

### 2.3 Script del operador

`flask create-tenant <nombre> <email>`: genera el token, calcula `clave = sha256(token)` y llama a **`acceso.crear_tenant(nombre, email, clave)`** (§2.1), que en **una transacción** crea `tenant` e `invitacion` (rol `admin`, `creada_por` NULL, expira 24 h, Q3 DECIDIDO). El script no hace INSERT directo ni fija `app.tenant_id`: el migrador no tiene política bajo `FORCE RLS`. Solo rol admin; las credenciales del migrador solo vienen de variable de entorno (nunca de argv ni archivo versionado); el enlace solo a stdout; no corre en el contenedor `api`. **Prueba (T5):** crea un rol migrador de prueba sin superusuario ni `BYPASSRLS` (con `USAGE` en `acceso` y `EXECUTE` en `crear_tenant`), lo usa para ejecutar el script y verifica que (a) funciona, (b) ese rol no puede INSERT directo en `tenant`/`invitacion`, (c) el rol de aplicación no puede ejecutar `crear_tenant`. No usa `POSTGRES_USER`.

## 3. Tablas afectadas, RLS y GRANT

| Tabla | tenant_id | RLS y política (aplicación) | GRANT a la aplicación | Claves |
|---|---|---|---|---|
| `tenant` | es su `id` | forzada; `SELECT` si `id` = tenant fijado; `INSERT` solo del dueño (`crear_tenant`) | `SELECT` | PK `id` |
| `usuario` | no | forzada; `SELECT` si tiene membresía en el tenant fijado | `SELECT (id, email, nombre, activo)`; sin `password_hash`, `INSERT` ni `UPDATE` | `email` único, normalizado, CHECK `lower(btrim())` |
| `membresia` | sí | `tenant_isolation` `TO` aplicación | `SELECT` | `UNIQUE (tenant_id, usuario_id)`, `UNIQUE (tenant_id, id)`; CHECK `rol` |
| `invitacion` | sí | `tenant_isolation` `TO` aplicación + política `RESTRICTIVE` `FOR INSERT TO` aplicación (`creada_por IS NOT NULL`) | `SELECT` (sin `token_hash`), `INSERT` columnas sin `usada_en` | FK compuesta `(tenant_id, creada_por)`; `email` normalizado; CHECK `rol`; `token_hash` `bytea(32)` con índice único |
| `refresh_token` | sí | `tenant_isolation` `TO` aplicación | `SELECT` (incluye `token_hash`, Q20), `INSERT`, `UPDATE (usado_en, revocado_en)` | FK compuesta `(tenant_id, membresia_id)`; `token_hash` `bytea(32)` con índice único; índice `familia_id` |

- Ninguna tabla con `DELETE`. `REVOKE` a `anon`/`authenticated`/`service_role` en cada tabla (deuda T6).
- Lista de excepciones de la prueba de catálogo: `alembic_version`, `tenant`, `usuario`, `limite_tasa` (cada una con prueba propia). La prueba de T1 ya incluye `limite_tasa` en la lista aunque la tabla aún no exista (se crea en T10): la excepción es por nombre, no exige que esté presente, y T10 añade su prueba propia.

### 3.1 `limite_tasa` (Q10 DECIDIDO) — esquema propuesto para `docs/03` (cambio 6, lo aplica el humano antes de T10)

Tabla de **infraestructura**, no de negocio: sin `tenant_id` porque el login, la validación y la aceptación se limitan antes de conocer el tenant. Guarda solo contadores; no contiene datos de la clínica.

| Columna | Tipo | Nota |
|---|---|---|
| `ambito` | `text` NOT NULL, `CHECK (ambito IN ('login_ip','login_cuenta','refresh_ip','validar_ip','aceptar_ip'))` | qué se limita (lista cerrada; ajustable en T10) |
| `clave_hash` | `bytea` NOT NULL, `CHECK (octet_length(clave_hash) = 32)` | `sha256` de la IP o del email normalizado, con la clave derivada de `SECRET_KEY`; nunca IP ni email en claro |
| `ventana_inicio` | `timestamptz` NOT NULL | inicio de la ventana fija |
| `intentos` | `integer` NOT NULL DEFAULT 0, `CHECK (intentos >= 0)` | contador |

PK `(ambito, clave_hash, ventana_inicio)`. Incremento atómico con `INSERT ... ON CONFLICT (...) DO UPDATE SET intentos = limite_tasa.intentos + 1 RETURNING intentos`, en una **transacción propia** (autocommit) para que el fallo de la petición no revierta el contador. Ventana de 15 min; umbrales (Q10 DECIDIDO; referencia, ajustables por configuración): login 5 fallidos por cuenta y 20 por IP; validar y aceptar invitación 10 por IP; refresh 30 por IP; `429` genérico; los emails inexistentes también cuentan, sin oráculo.

- **RLS y `GRANT` mínimos:** `ENABLE` + `FORCE ROW LEVEL SECURITY`; una política por comando `TO <rol de aplicación>` (`SELECT`, `INSERT`, `UPDATE`), sin `PUBLIC` ni `FOR ALL`; `GRANT SELECT, INSERT, UPDATE (intentos)` al rol de aplicación (el `SELECT` de tabla completa es necesario para el `RETURNING`; la tabla solo guarda hashes y contadores); **sin `DELETE`** (constitución §6) y `REVOKE` a `anon`/`authenticated`/`service_role`. Como la tabla no tiene datos de negocio ni de tenant, la política no filtra por tenant: su defensa es el privilegio mínimo y el hash de la clave. Las ventanas vencidas se ignoran; la purga (único `DELETE`, con `GRANT DELETE` solo al migrador) es el comando operativo documentado `purgar-limite-tasa`, ejecutado por el operador (responsable) con el rol migrador (DECIDIDO); T10 lo deja escrito en el `README.md` previsto.
- **Excepción a la constitución §4** (toda tabla de negocio lleva `tenant_id`): se justifica porque no es una tabla de negocio. Queda en la lista cerrada de A2 con prueba propia (sin `DELETE`, solo `intentos` actualizable, sin columnas en claro).
- Migración `0005_limite_tasa` (T10).

## 4. Endpoints y permisos

| Método y ruta | Rol | Notas |
|---|---|---|
| `POST /auth/login` | público, con límite | `{email, password}`; genérico en fallo |
| `POST /auth/refresh` | cookie de refresh | cabecera personalizada + `Origin`/`Sec-Fetch-Site`; rotación |
| `POST /auth/logout` | cookie de refresh | revoca familia, limpia cookie |
| `GET /auth/me` | `admin`, `contador` | usuario, tenant, rol leído de `membresia` |
| `POST /invitaciones` | `admin` | `{email, rol}`; enlace una sola vez; contador → 403 |
| `POST /invitaciones/validar` | público, con límite | `{token}` |
| `POST /invitaciones/aceptar` | público, con límite | `{token, nombre, password}` (sin email: lo fijó el admin) |
| `GET /ready` | público | ping cacheado |
| `GET /health` | público | sin cambios |

El token nunca va en ruta ni query. Cada endpoint declara su rol y trae pruebas 401/403 y de aislamiento.

## 5. Migraciones

- `0002_acceso_y_usuarios` (T1): esquema `acceso` (vacío), las cinco tablas, CHECKs, índices, claves, RLS + FORCE, `tenant_isolation`, política `RESTRICTIVE` de `creada_por`, lectura por membresía, `GRANT` por columna y `REVOKE` a roles de Supabase.
- `0003_politicas_del_dueno` (T2): políticas por comando `TO auth_owner` y `GRANT` por columna del dueño (incluidas las de `crear_tenant`).
- `0004_funciones_de_acceso` (T3): las cuatro funciones de §2.1 en el orden de C3.
- `0005_limite_tasa` (T10): tabla `limite_tasa` de §3.1 con RLS forzada, política y `GRANT` mínimos; `downgrade` la elimina.
- Ninguna migración crea roles (`auth_owner` lo crea el script de init, P0).
- **Prerrequisitos (humano, antes de T1):** cambios 1–5 a `docs/03` de `spec.md` y P0 (script de init con `auth_owner`; A0). **Antes de T10:** cambio 6 (`limite_tasa`).
- CI y Docker local con PostgreSQL 17; paridad con Supabase antes del piloto (C8).

## 6. Dependencias nuevas de backend (Q8 DECIDIDO: aprobadas)

| Dependencia | Uso | Justificación | Alternativa descartada |
|---|---|---|---|
| `argon2-cffi` | hash Argon2id de contraseñas | algoritmo adaptativo y resistente a GPU; decisión humana | `werkzeug.security` (reemplazada) |
| `PyJWT` | firmar/verificar acceso (HS256 fijo) | estándar, pequeña | `itsdangerous` |

Sin `Flask-Limiter` ni Redis: los límites usan la tabla `limite_tasa` (§3.1, Q10).

**Versiones exactas:** se fijan con `==` en `pyproject.toml` y en `uv.lock` en T4 (no se inventan aquí); no se instalan otras.

**Argon2id (T4):** los parámetros (`time_cost`, `memory_cost`, `parallelism`, longitud de hash y sal) se fijan en T4 midiendo en el hardware objetivo, partiendo de un perfil publicado (RFC 9106 / OWASP) y con revisión del `security-reviewer`; `[PENDIENTE]` hasta T4. En pruebas se usa un costo bajo solo vía configuración de test. **Hash simulado:** se calcula una vez al arrancar con **los mismos parámetros** y se verifica cuando el email no existe, para que el tiempo de login no distinga cuentas (A10).

**Despliegue:** `argon2-cffi` depende de `argon2-cffi-bindings` (extensión en C); el despliegue necesita la **rueda binaria** (imagen del `api` sin compilador), con `uv.lock` fijado. T4 comprueba que la imagen instala sin compilar.

Las dependencias de 002b están en su propia spec.

## 7. Estrategia de pruebas

Tests primero; `uv run pytest` contra PostgreSQL real, con el rol de aplicación y dos tenants sintéticos.

### 7.1 Catálogo cerrado (A2, C6)
Falla si: una tabla de `public` fuera de la lista de excepciones carece de `tenant_id`, RLS, FORCE o `tenant_isolation` `TO` aplicación; hay `DELETE` para cualquier rol; el conjunto de funciones de `acceso` no coincide exactamente con la lista cerrada (`prosecdef`, dueño `auth_owner`, `proconfig` = `search_path` fijo, `proacl` solo aplicación); el conjunto de políticas `TO auth_owner` no coincide con la lista cerrada; existen funciones propias en `public`; la aplicación tiene `SELECT` sobre `usuario.password_hash` o `invitacion.token_hash`. La prueba fija explícitamente `refresh_token.token_hash` como **única** excepción permitida de columna de hash legible por la aplicación (Q20: la rotación de T7 la necesita en el `WHERE`) y falla si aparece cualquier otra.

### 7.2 Las 9 pruebas de aislamiento ampliadas (A26) más la 10 de T3
> El `security-reviewer` recomendó 9 pruebas; se enumeran aquí según su veredicto y se ajustarán si su lista difiere.

1. Sin tenant fijado, `SELECT`/`INSERT`/`UPDATE` en las cinco tablas no leen ni escriben (conexión nueva y reutilizada).
2. Con tenant A, cero filas de B por ORM, `get_bind`, SQL crudo y `join`; `DELETE` → `insufficient_privilege`.
3. `WITH CHECK`: `tenant_id` ajeno falla en `invitacion` y `refresh_token`; `UPDATE` de `tenant_id` falla.
4. `membresia` `INSERT` por `auth_owner` sin invitación recién consumida falla; con ella, solo con `usada_en = now()`, ese tenant, esa clave, el `rol` de la invitación y el `usuario_id` de la GUC; una invitación consumida en otra transacción, otro rol u otro usuario falla.
5. `usuario` `INSERT` por `auth_owner` con `email` distinto al de la invitación consumida falla.
6. `auth_owner` solo lee `tenant (id, creado_en)` de la fila creada en su misma transacción (Q21; cero filas para un tenant de otra transacción aunque su id esté en la GUC, y sin `nombre`) y ninguna fila con GUC vacía/nula/comodín (`%`, `_`); su `INSERT` en `tenant`/`invitacion` solo pasa con la GUC `app.auth_tenant_nuevo` y con `rol = 'admin'`, `creada_por` NULL, expiración ≤ 24 h y un tenant creado en la misma transacción; el `WITH CHECK` del consumo de la invitación es `usada_en = now()` (no `IS NOT NULL`). La aplicación no puede insertar `invitacion` con `creada_por` NULL aunque exista otra política permisiva (la `RESTRICTIVE` la frena).
7. La aplicación no puede leer `usuario.password_hash` ni `invitacion.token_hash`; sí puede leer `refresh_token.token_hash` (única excepción, Q20), acotado por RLS a su tenant; el hash almacenado (doble) no autentica (I1).
8. `SET ROLE auth_owner` falla para la aplicación; llamar a `acceso.*` con `SET ROLE anon`/`authenticated`/`service_role` → `permission denied` (C7).
9. Tras cada función, el contexto local no sobrevive (transacción ni savepoint) y una consulta directa sin tenant devuelve cero. **Se ejecuta en T3**, cuando existen las funciones. En T2 solo se prueba, a nivel SQL, que las GUC de las políticas (`app.auth_*`) fijadas con `set_config(..., true)` no sobreviven al `COMMIT`/`ROLLBACK` ni a un `ROLLBACK TO SAVEPOINT`, y que con GUC vacía las políticas devuelven cero filas.
10. (T3) `ON CONFLICT DO NOTHING` bajo `auth_owner` real no exige política `SELECT` en `usuario`; y `now()` es el de la transacción: una invitación consumida en una transacción anterior (o antes de un `SAVEPOINT` en otra) no satisface `usada_en = now()` de las políticas de `usuario` y `membresia`.

### 7.3 Funciones (A19)
(a) `buscar_login` solo devuelve la cuenta del email exacto; (b) vacío, nulo, `%`, `_` → cero filas; (c) `validar_invitacion` con la clave de B solo dice vigente o no; (d) `aceptar_invitacion` con clave inexistente/usada/vencida → nada creado; con el email de la invitación ya existente → revierte, `usada_en` nulo; el usuario creado lleva el email de la invitación; (d') `crear_tenant` crea tenant + invitación admin en una transacción y revierte entera si falla; solo la ejecuta el migrador; (e) ejecuta como `auth_owner` real bajo `FORCE RLS` (sin política devolvería cero, con ella exactamente una).

### 7.4 Atributos (A6)
`pg_roles` sin `rolsuper` ni `rolbypassrls` (aplicación y `auth_owner`); arranque falla con rol inseguro.

### 7.5 Refresh y sesión (A11, A23, A24)
Rotación atómica concurrente; (Q15) ventana de gracia y reuso fuera de ella revoca la familia; `UPDATE` de otras columnas denegado; logout por cookie; rol y `activa` leídos de `membresia` en cada petición.

### 7.6 Otras
Concurrencia (A9), atomicidad (A20, A22), auth (A10, A13, A14, A21), JWT/cabeceras/tamaños (A25), roles (A8, A12), script del operador con migrador real (A7). Secretos en el repo (A18): `git grep` de patrones de secretos y revisión de `.env.example` en T10. Guardián de residuos bajo FORCE RLS (deuda de T5): `pg_stat_user_tables` o rol de solo lectura de pruebas `[decisión del implementer, documentada en conftest.py; si requiere rol nuevo, se aprueba]`. Datos sintéticos; nunca datos de la clínica.

## 8. Riesgos técnicos y preguntas por tarea

| Riesgo | Mitigación |
|---|---|
| Función mal acotada o que devuelve cero filas por `FORCE RLS` | Políticas por comando `TO auth_owner` con GUC, mínima, `search_path` fijo, `EXECUTE` solo aplicación; §7.1–7.3 |
| Exposición vía Data API de Supabase | Esquema `acceso` + `REVOKE` a anon/authenticated/service_role + prueba C7 |
| Hash filtrado utilizable | Doble hash |
| Oráculo de existencia por `UNIQUE` | La aplicación no inserta en `usuario`; `ON CONFLICT DO NOTHING` y excepción estática |
| Rol obsoleto en el token | Rol desde `membresia` en cada petición |
| Script con `BYPASSRLS` implícito | Prueba con migrador real, entorno, stdout |
| Cookie `Secure` rompe el desarrollo local | `development` explícito en compose y `.env.example` |
| Contador en memoria con varios workers | Tabla `limite_tasa` (Q10) |

"Debe estar respondido antes" (solo lo que sigue abierto; el resto está decidido):

| Tarea | Pendiente antes de empezar |
|---|---|
| T1 | `docs/03` actualizado por el humano (cambios 1–5), P0 (init con `auth_owner`) |
| T2 | T1; revisión del SQL de políticas por el `security-reviewer` |
| T3 | T2 |
| T4 | T1; versiones exactas y parámetros de Argon2id y lista corta de contraseñas comunes (se fijan en la tarea) |
| T5 | T3, T4 |
| T6 | T3, T4 |
| T7 | T6 |
| T8 | T6 |
| T9 | T3, T6, T8 |
| T10 | Cambio 6 a `docs/03` (`limite_tasa`) por el humano |

Decididas: Q1–Q18 (incluidas Q9, Q10 completa y Q11) y Q20 (`SELECT` de `refresh_token.token_hash` para la aplicación). Q19 solo afecta a 002b.

## 9. Alternativa descartada

- **Supabase Auth**: contradice la decisión T10.
- **Usuario con `tenant_id`**: choca con `docs/03` y P17.
- **Aplicación sin `FORCE RLS` en tablas globales**: dejaría `usuario` legible.
- **`BYPASSRLS` o superusuario como dueño** (Q1 A2/A3/C descartados): anula ADR-001 y no es asumible en Supabase.
- **Funciones en `public`**: expuestas por la Data API; se usa el esquema `acceso`.
- **Política `FOR ALL` o `USING (true)` para el dueño**: sin defensa en profundidad.
- **Guardar `sha256(token)` directo**: el hash filtrado serviría como credencial; se usa doble hash.
- **`INSERT` directo del rol de aplicación en `usuario`**: oráculo de existencia; se usa `aceptar_invitacion`.
- **Script con INSERT directo del migrador** (con política `TO` migrador, `BYPASSRLS` o superusuario): amplía el poder del migrador o lo anula; se usa `acceso.crear_tenant` con el patrón A1.
- **El invitado escribe el email** (Q4-A): descartado por Q4=B; el email lo fija el admin.
- **Política permisiva adicional para `creada_por IS NOT NULL`**: se combina con OR y no restringe; se usa `RESTRICTIVE`.
- **Refresh sin estado** (Q2-C) y **`token_version`** (Q2-B): no permiten detección de reuso por familia.
- **Contador de intentos solo en memoria con varios workers**: no se comparte.
- **`Flask-Limiter`, Redis o proxy** (Q10): descartados por decisión humana; se usa la tabla `limite_tasa`.
- **`werkzeug.security` para el hash** (Q8): reemplazado por `argon2-cffi`.
