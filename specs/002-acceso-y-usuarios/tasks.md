# Tasks 002 — Acceso y usuarios

> **Estado:** Aprobada (G1–G3, 2026-11-12). **Condición:** T1 no empieza hasta que el humano aplique los cambios 1–5 a `docs/03` y P0 (`auth_owner` en el init); T10 no empieza hasta que aplique el cambio 6 (`limite_tasa`). Máximo 10 tareas, cada una ≤ 1 día, una a la vez, **tests primero en cada tarea** (se escriben y se ven fallar antes del código). Backend únicamente; OpenAPI/tipos y web están en `specs/002b-acceso-web/`.
> Las tareas asumen las decisiones humanas de la ronda G1 (Q1–Q18, incluidas Q9, Q10 y Q11) y Q20 (`/sdd-change`) de `spec.md`; si el humano decide otra cosa, se ajusta con `/sdd-change` antes de implementar. Solo `argon2-cffi` y `PyJWT` (Q8) pueden instalarse, con versiones exactas (`plan.md` §6).
> "Depende de" lista tareas y preguntas que deben seguir respondiéndose antes de empezar (coincide con `plan.md` §8 y `spec.md`); las decididas no se repiten.
> **Prerrequisitos globales (los aplica el humano, antes de T1):**
> 1. Cambios 1–5 a `docs/03` de `spec.md` (incluido el formato `bytea` del hash). El cambio 6 (`limite_tasa`) se aplica antes de T10.
> 2. **P0:** ampliar `docker/postgres/init/01-app-role.sh` con el rol `auth_owner` (`NOLOGIN`, sin `rolsuper` ni `rolbypassrls`, `CREATE ROLE` condicional). El script solo corre con el volumen vacío (`docker compose down -v`) y la CI ya lo ejecuta. Criterio A0: `docker compose down -v && docker compose up -d db`, luego `psql -c "select rolname, rolcanlogin, rolsuper, rolbypassrls from pg_roles where rolname='auth_owner'"` devuelve una fila (`f`,`f`,`f`); ejecutar el script dos veces no falla; el job de la CI sigue verde.
> Comandos con `uv run`.

---

### T1 — Esquema base, RLS y prueba de catálogo

- **Resultado:** `alembic upgrade head` crea el esquema `acceso` y las tablas `tenant`, `usuario`, `membresia`, `invitacion` (con `email`, `token_hash` `bytea(32)`) y `refresh_token` con RLS forzada, `tenant_isolation` `TO` rol de aplicación, política `RESTRICTIVE` `FOR INSERT` de `creada_por IS NOT NULL` en `invitacion`, claves compuestas, CHECKs (`rol`, email normalizado), `GRANT` por columna (sin `usuario.password_hash` ni `invitacion.token_hash` para la aplicación; `refresh_token.token_hash` sí es legible por la aplicación como única excepción, Q20, y la prueba de catálogo lo fija así) y `REVOKE` a `anon`/`authenticated`/`service_role`; la prueba de catálogo (A2, parte de tablas) pasa. **Primer resultado ejecutable:** migración que sube, baja y sube.
- **Tests primero:** `test_catalog_rls.py` (tablas) y `test_migrations.py` fallan antes de la migración. La lista cerrada de excepciones de `test_catalog_rls.py` es `alembic_version`, `tenant`, `usuario` y `limite_tasa` (esta última se crea en T10; la excepción es por nombre y no exige que exista aún), cada una con su prueba propia.
- **Archivos probables:** `backend/migrations/versions/0002_acceso_y_usuarios.py`, `backend/app/auth/models.py`, `backend/tests/test_catalog_rls.py`, `backend/tests/test_migrations.py`.
- **Verificación:** `cd backend && uv run alembic upgrade head && uv run alembic downgrade base && uv run alembic upgrade head && uv run pytest tests/test_catalog_rls.py tests/test_migrations.py && uv run ruff check .`
- **Depende de:** spec aprobada; `docs/03` actualizado (cambios 1–5); P0 (A0).
- **Riesgo:** `GRANT` de columnas de más; política de lectura de `usuario` mal acotada; política permisiva que anule la `RESTRICTIVE`.

### T2 — Políticas del dueño y pruebas de aislamiento

- **Resultado:** migración `0003_politicas_del_dueno`: políticas por comando `TO auth_owner` (I2/I3) con GUC propia por tabla y `GRANT` por columna del dueño (`invitacion` SELECT/UPDATE(`usada_en`)/INSERT, `usuario` SELECT/INSERT, `membresia` SELECT/INSERT ligada a la invitación recién consumida con `usada_en = now()`, rol y `usuario_id`, `tenant` INSERT y `SELECT (id, creado_en)` solo de la fila creada en la misma transacción, Q21) incluidas las de `crear_tenant` (R6); pruebas de aislamiento de `plan.md` §7.2 (1–7 y, a nivel SQL, las GUC `set_config(..., true)` que no sobreviven a `COMMIT`/`ROLLBACK`/`ROLLBACK TO SAVEPOINT`; la prueba 9 completa pasa a T3, donde existen las funciones). Ejecutan como `auth_owner` real con `SET LOCAL ROLE auth_owner` sobre la conexión del migrador, sin crear roles de prueba ni membresías en `auth_owner` (I1 de la revisión de seguridad de T2; A6 exige que la aplicación no pueda hacer `SET ROLE auth_owner`); el guardián falla si existe un rol `prueba_*` miembro de `auth_owner`; 0003 valida los atributos de `auth_owner` (I3); atributos de roles (A6, solo `pg_roles`); el guardián de residuos cuenta bajo FORCE RLS. **El `security-reviewer` revisa el SQL de estas políticas antes de aprobar la tarea** (incluidas `tenant`/`invitacion` de `crear_tenant`).
- **Tests primero:** `test_auth_tables_isolation.py` falla antes de la migración.
- **Archivos probables:** `backend/migrations/versions/0003_politicas_del_dueno.py`, `backend/tests/test_auth_tables_isolation.py`, `backend/tests/test_roles_attributes.py`, `backend/tests/conftest.py`, `backend/tests/test_harness.py`.
- **Verificación:** `cd backend && uv run pytest tests/test_auth_tables_isolation.py tests/test_roles_attributes.py tests/test_harness.py && uv run pytest` (dos veces, sin residuos) `&& uv run ruff check .`
- **Depende de:** T1; revisión del `security-reviewer`.
- **Riesgo:** cero filas por FORCE RLS; permisivas que se combinan por OR; `membresia` aceptando una invitación de otra transacción.

### T3 — Funciones `acceso.*`, `crear_tenant` y catálogo cerrado

- **Resultado:** migración `0004_funciones_de_acceso`: `buscar_login`, `validar_invitacion`, `aceptar_invitacion(p_clave, p_nombre, p_password_hash)` (email tomado de la invitación; sin GUC `app.auth_email_nuevo`) y `crear_tenant(p_nombre, p_email, p_clave)` en el orden C3 (`REVOKE` a PUBLIC/anon/authenticated/service_role; `EXECUTE` solo aplicación, y solo migrador en `crear_tenant`; `GRANT CREATE ON SCHEMA acceso TO auth_owner` y migrador miembro transitorio de `auth_owner` `WITH INHERIT FALSE, SET TRUE` (PG ≥ 16), también en local y CI, donde basta `POSTGRES_USER` superusuario, pero queda escrito; `ALTER FUNCTION ... OWNER TO auth_owner`; `REVOKE CREATE` y fin de la membresía inmediatamente después; la migración falla con mensaje claro si `auth_owner` no existe), con prueba de que `CREATE` sobre `acceso` no queda abierto para `auth_owner` (C5), `search_path` fijo, `STRICT`, doble hash en `bytea`; pruebas de funciones (`plan.md` §7.3, A19, A20 a nivel de base), C7 (`SET ROLE` aplicación/anon/authenticated/service_role), la **prueba 9 de §7.2** (tras cada función el contexto local no sobrevive a transacción ni savepoint), las pruebas "`ON CONFLICT DO NOTHING` bajo `auth_owner` real no exige política `SELECT` en `usuario`" y "`now()` con `SAVEPOINT` / invitación consumida en una transacción anterior no satisface `usada_en = now()`" (§7.2 #10), y **catálogo cerrado C6** (A2: listas exactas de funciones, políticas `TO auth_owner` y `RESTRICTIVE`).
- **Notas para las pruebas (cierre de la revisión de seguridad de T2):** `aceptar_invitacion` fija `app.auth_usuario_nuevo` solo con el `id` del `INSERT usuario` recién hecho en la función, y revierte (excepción estática, Q16) si el email ya existe; nunca con un id recibido ni leído. `now()` es constante dentro de una transacción: en una transacción externa de prueba, una invitación consumida antes en la misma transacción sigue cumpliendo `usada_en = now()`: no se da por buena como prueba de "consumida antes"; ese caso se prueba consumiéndola con un `COMMIT` real en otra transacción.
- **Tests primero:** `test_auth_functions.py` y la parte de funciones/políticas de `test_catalog_rls.py` fallan antes de la migración.
- **Archivos probables:** `backend/migrations/versions/0004_funciones_de_acceso.py`, `backend/tests/test_auth_functions.py`, `backend/tests/test_catalog_rls.py`.
- **Verificación:** `cd backend && uv run pytest tests/test_auth_functions.py tests/test_catalog_rls.py && uv run pytest && uv run ruff check .`
- **Depende de:** T2 (Q3, 24 h, y Q16 ya decididos).
- **Riesgo:** función expuesta a `anon`; contexto que sobrevive a un savepoint; si no cabe en un día, se divide con `/sdd-change` (catálogo C6 como tarea propia y se mueven límites/`/ready` a 002b), no se recorta cobertura.

### T4 — Credenciales, tokens, configuración segura y logs

- **Resultado:** (a) hash **Argon2id** con `argon2-cffi` (Q8; versiones exactas de `argon2-cffi` y `PyJWT` fijadas con `==` en `pyproject.toml` y `uv.lock`; parámetros de Argon2id medidos y revisados por el `security-reviewer`, `plan.md` §6) y verificación de contraseña con **hash simulado de los mismos parámetros** calculado al arrancar, longitud máxima y política (Q9 DECIDIDO: 10–128 caracteres y rechazo de una lista corta de contraseñas comunes que fija esta tarea); comprobación de que la imagen del `api` instala la rueda binaria sin compilar; generación y doble hash (`sha256` → `sha256`, `bytea`) de tokens de invitación y refresh; JWT `HS256` fijo con `exp` e `iss` obligatorios, clave derivada de `SECRET_KEY`, rechazo de `alg` distinto y de `none`. (b) `SECRET_KEY` validada (B3 de T7; ≥ 32 bytes, Q11 DECIDIDO); verificación del rol de aplicación al arrancar (M2); `ENVIRONMENT` por defecto producción, cookie `__Secure-`/`Secure` salvo `development` explícito (B4 de T7) con `docker-compose.yml` y `.env.example` fijándolo; `Cache-Control: no-store` y `Referrer-Policy: no-referrer` en `/auth` e `/invitaciones`; límite de tamaño de cuerpo de 4 KB en los endpoints de auth (`413`, Q9); redacción de `DBAPIError` (tipo y `sqlstate`); `caplog` sin secretos.
- **Tests primero:** `test_credentials.py`, `test_config.py`, `test_log_redaction.py`.
- **Archivos probables:** `backend/app/auth/credentials.py`, `backend/app/config.py`, `backend/app/db.py`, `backend/app/errors.py`, `backend/pyproject.toml` y lock (solo dependencias aprobadas), `docker-compose.yml`, `.env.example`, `backend/tests/test_credentials.py`, `backend/tests/test_config.py`, `backend/tests/test_log_redaction.py`.
- **Verificación:** `cd backend && uv run pytest tests/test_credentials.py tests/test_config.py tests/test_log_redaction.py && uv run ruff check .`
- **Depende de:** T1; Q7, Q8, Q9 y Q11 decididos.
- **Nota:** de T4 solo se prueba el mecanismo de las cabeceras (`no-store`, `no-referrer`); las pruebas por ruta de `/auth` e `/invitaciones` se escriben en T6/T8/T9, cuando existan las rutas. Si T4 pasa de un día, se parte con `/sdd-change` (p. ej. configuración y logs aparte de credenciales).
- **Riesgo:** costo de hash lento en pruebas (costo bajo solo en tests); imprimir `SECRET_KEY`; romper el arranque local.

### T5 — Script del operador: tenant y primera invitación admin

- **Resultado:** `flask create-tenant <nombre> <email>` genera el token, calcula la clave y llama a `acceso.crear_tenant` (una transacción; rol `admin`, `creada_por` NULL, 24 h); enlace una vez a stdout, sin guardar ni registrar; solo rol admin; credenciales del migrador solo por entorno; no corre en el contenedor `api`. **La prueba corre con un migrador de prueba sin superusuario ni `BYPASSRLS`** (creado por la prueba, con `USAGE` en `acceso` y `EXECUTE` en `crear_tenant`), no con `POSTGRES_USER`; comprueba que ese rol no puede INSERT directo y que la aplicación no puede ejecutar `crear_tenant`.
- **Tests primero:** `test_cli_tenant.py` falla antes del comando.
- **Archivos probables:** `backend/app/cli.py`, `backend/tests/test_cli_tenant.py`, `backend/tests/conftest.py`, `README.md`, `.env.example`.
- **Verificación:** `cd backend && uv run pytest tests/test_cli_tenant.py` y ejecución manual, comprobando que `invitacion` solo tiene `sha256(clave)`.
- **Depende de:** T3, T4 (Q3, Q5, Q17 decididos).
- **Riesgo:** enlace en logs o historial; credenciales en argv; prueba que pase solo por ser superusuario.

### T6 — Login y usuario actual

- **Resultado:** `POST /auth/login` y `GET /auth/me`; respuesta genérica, hash simulado, rechazo de inactivos, falla cerrado con varias membresías (Q6); JWT con tenant; refresh emitido (cookie `HttpOnly`/`Secure`/`SameSite=Lax`, `<tenant_id>.<secreto>`, `familia_id` nueva); rol y `activa` leídos de `membresia`.
- **Tests primero:** `test_auth_login.py` (A10, A21).
- **Archivos probables:** `backend/app/auth/routes.py`, `backend/app/auth/service.py`, `backend/app/__init__.py`, `backend/tests/test_auth_login.py`.
- **Verificación:** `cd backend && uv run pytest tests/test_auth_login.py`
- **Depende de:** T3, T4 (Q6, Q7 decididos: acceso 15 min, refresh 7 días).
- **Riesgo:** enumeración por mensaje o tiempo; `buscar_login` dentro de `tenant_session`.

### T7 — Refresh y logout

- **Resultado:** `POST /auth/refresh` con rotación en un `UPDATE` atómico, cabecera personalizada y comprobación `Origin`/`Sec-Fetch-Site` (Q14, decidido); ventana de gracia ~10 s y revocación de familia ante reuso (Q15, decidido; A23); `POST /auth/logout` por cookie de refresh que revoca la familia y limpia la cookie (A11).
- **Tests primero:** `test_auth_refresh_logout.py`.
- **Archivos probables:** `backend/app/auth/routes.py`, `backend/app/auth/service.py`, `backend/tests/test_auth_refresh_logout.py`.
- **Verificación:** `cd backend && uv run pytest tests/test_auth_refresh_logout.py`
- **Depende de:** T6 (Q7, Q14, Q15 decididos).
- **Riesgo:** refresh que sobrevive al logout; condiciones de carrera en la rotación.

### T8 — Autorización por rol e invitar

- **Resultado:** `require_auth` y `require_role` (rol y `activa` desde `membresia` por petición, A24); `POST /invitaciones` (solo `admin`, `{email, rol}`) con `creada_por` NOT NULL, tenant del token y enlace una vez (Q13); `contador` → `403`, sin token `401`; JWT inválido (A25); aislamiento por endpoint (A12).
- **Tests primero:** `test_roles.py`, `test_invitaciones_crear.py`.
- **Archivos probables:** `backend/app/auth/decorators.py`, `backend/app/invitaciones/routes.py`, `backend/app/invitaciones/service.py`, `backend/tests/test_roles.py`, `backend/tests/test_invitaciones_crear.py`.
- **Verificación:** `cd backend && uv run pytest tests/test_roles.py tests/test_invitaciones_crear.py`
- **Depende de:** T6 (Q7 y Q13 decididos: enlace `/invitacion#<token>`, invitación 72 h).
- **Riesgo:** rol tomado del token o de la petición; token en logs.

### T9 — Validar y aceptar invitación

- **Resultado:** `POST /invitaciones/validar` (`{token}`, solo vigente o no) y `POST /invitaciones/aceptar` (`{token, nombre, password}`, **sin email**; token en cuerpo); `aceptar_invitacion` atómica con el email de la invitación, `ON CONFLICT DO NOTHING` y excepción estática (Q16, decidido; A20); sesión tras el commit (A22); mismo error para vencido, usado, inexistente o email ya existente; concurrencia (A9).
- **Tests primero:** `test_invitaciones_aceptar.py`, `test_invitaciones_concurrencia.py`.
- **Archivos probables:** `backend/app/invitaciones/routes.py`, `backend/app/invitaciones/service.py`, `backend/tests/test_invitaciones_aceptar.py`, `backend/tests/test_invitaciones_concurrencia.py`.
- **Verificación:** `cd backend && uv run pytest tests/test_invitaciones_aceptar.py tests/test_invitaciones_concurrencia.py`
- **Depende de:** T3, T6, T8 (política de contraseña de T4; Q9 y Q16 decididos).
- **Riesgo:** carrera en el uso único; revelar email existente por mensaje o tiempo.

### T10 — Límites de tasa, `/ready` y secretos en logs

- **Resultado:** migración `0005_limite_tasa` (tabla de infraestructura sin `tenant_id`, `plan.md` §3.1, con RLS forzada, política y `GRANT` mínimos, sin `DELETE`) y prueba propia en el catálogo (la excepción ya figura desde T1); `429` por IP y cuenta en login, refresh, validar y aceptar con contador en esa tabla, en transacción propia, sin Flask-Limiter ni Redis (Q10 DECIDIDO; ventana de 15 min, umbrales de referencia ajustables por configuración: login 5/cuenta y 20/IP, validar y aceptar 10/IP, refresh 30/IP; `429` genérico; los emails inexistentes también cuentan, sin oráculo); comando operativo documentado `purgar-limite-tasa`, ejecutado por el **operador** (responsable) con el rol migrador, único con `DELETE` y solo sobre `limite_tasa`, sin `DELETE` para la app, y documentado en el `README.md` previsto; `GET /ready` cacheado (Q12); sin dependencias nuevas; prueba `caplog` de que ningún log contiene tokens, hashes ni contraseñas, incluidos `validar` y `aceptar`; cierre de A18: `git grep` de secretos y revisión de que `.env.example` lista las variables nuevas sin valores.
- **Tests primero:** `test_rate_limits.py`, `test_ready.py`, `test_no_secrets_in_logs.py`.
- **Archivos probables:** `backend/migrations/versions/0005_limite_tasa.py`, `backend/tests/test_catalog_rls.py`, `backend/app/auth/limits.py`, `backend/app/meta/routes.py`, `backend/tests/test_rate_limits.py`, `backend/tests/test_ready.py`, `backend/tests/test_no_secrets_in_logs.py`, `README.md`.
- **Verificación:** `cd backend && uv run alembic upgrade head && uv run alembic downgrade base && uv run alembic upgrade head && uv run pytest tests/test_rate_limits.py tests/test_ready.py tests/test_no_secrets_in_logs.py tests/test_catalog_rls.py && uv run pytest && uv run ruff check . && git grep -nEi "(secret|password|token)[a-z_]*\s*=\s*['\"][^'\"]+['\"]" -- . ':!*/tests/*'` (sin coincidencias reales; criterio A18)
- **Depende de:** T6–T9; cambio 6 a `docs/03` (`limite_tasa`) aplicado por el humano (T10 no empieza sin él); Q10 y Q12 decididos.
- **Riesgo:** `X-Forwarded-For` falsificable; el contador revertido por el fallo de la petición; tabla sin `tenant_id` mal acotada (privilegio mínimo y prueba propia).

---

## Fuera de esta spec

Spec `002b-acceso-web` (aún sin aprobar; Q19 abierta): OpenAPI + tipos TS y web mínima; depende de T10. B2 y B5 de la spec 001 diferidos. C8 (validación con `postgres` real de Supabase) antes del piloto.

## Resumen

| Tarea | Depende de | Verificación |
|---|---|---|
| T1 | `docs/03` (1–5) actualizado; P0 (A0) | `alembic up/down/up` + catálogo de tablas |
| T2 | T1; `security-reviewer` | `pytest` aislamiento y atributos, dos veces |
| T3 | T2 | `pytest` funciones + catálogo cerrado |
| T4 | T1 | `pytest test_credentials test_config test_log_redaction` |
| T5 | T3, T4 | `pytest test_cli_tenant` + manual |
| T6 | T3, T4 | `pytest test_auth_login` |
| T7 | T6 | `pytest test_auth_refresh_logout` |
| T8 | T6 | `pytest test_roles test_invitaciones_crear` |
| T9 | T3, T6, T8 | `pytest test_invitaciones_*` |
| T10 | T6–T9; `docs/03` cambio 6 | `alembic up/down/up` + `pytest test_rate_limits test_ready test_no_secrets_in_logs test_catalog_rls` |

## Reglas de ejecución

- Una tarea por sesión; tests antes que el código; sin tests verdes no se avanza.
- Nada de las preguntas abiertas se decide dentro de una tarea: se detiene y se pregunta.
- No se cambia `docs/03` ni `docs/adr/` desde esta spec; lo aplica el humano.
- Toda tabla nueva nace con RLS forzada, política y `GRANT` mínimos en su misma migración.
- No se instala dependencia fuera de la lista aprobada de `plan.md` §6 (`argon2-cffi`, `PyJWT`).
