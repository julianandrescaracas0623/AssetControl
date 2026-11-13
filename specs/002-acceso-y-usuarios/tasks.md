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
- **Deuda (T3):** `require_owner_attributes` de `0003_politicas_del_dueno` (ya integrada en `develop`) sigue sin rechazar `CREATEROLE`/`CREATEDB`/`REPLICATION` y da por bueno un rol inexistente; no se toca una migración aplicada. Lo cubre 0004, que corre en la misma cadena: rechaza esos atributos, trata el rol inexistente como fallo y falla si el rol de la aplicación es miembro (directo o indirecto) de `auth_owner`. Si se quiere en 0003, decisión humana.
- **Deuda (auditoría de seguridad de T3):**
  - H1 (baja, falla abierto): 0004:246-249, `to_regrole(current_user)` da NULL si el migrador tiene mayúsculas o caracteres especiales y C5 no detecta la membresía residual; usar `(select oid from pg_roles where rolname = current_user)` o `current_user::regrole`, con prueba (migrador con mayúsculas/guion miembro de `auth_owner` → la migración falla). Al inicio de T4 o antes del piloto.
  - H2 (baja, C8): `_app_role` no comprueba aplicación miembro del migrador, ni `CREATEROLE`/`REPLICATION` en la aplicación, ni terceros miembros de `auth_owner`; cubrir en C8 (excepción documentada de Supabase).
  - H3 (info, T4): el arranque verifica atributos y membresías de `auth_owner` (`ALTER ROLE` posterior a migrar).
  - H5 (info, T9): unificar código HTTP y cuerpo de "email ocupado" (`ON CONFLICT DO NOTHING`) y clave inválida, con tiempos comparables.
  - H6 (info, C8): la clave viaja como parámetro SQL; fijar logs sin parámetros (`log_statement`, `auto_explain`, `pg_stat_statements`).
- **Riesgo:** función expuesta a `anon`; contexto que sobrevive a un savepoint; si no cabe en un día, se divide con `/sdd-change` (catálogo C6 como tarea propia y se mueven límites/`/ready` a 002b), no se recorta cobertura.

### T4 — Credenciales, tokens, configuración segura y logs

- **Resultado:** (a) hash **Argon2id** con `argon2-cffi` (Q8; versiones exactas de `argon2-cffi` y `PyJWT` fijadas con `==` en `pyproject.toml` y `uv.lock`; parámetros de Argon2id medidos y revisados por el `security-reviewer`, `plan.md` §6) y verificación de contraseña con **hash simulado de los mismos parámetros** calculado al arrancar, longitud máxima y política (Q9 DECIDIDO: 10–128 caracteres y rechazo de una lista corta de contraseñas comunes que fija esta tarea); comprobación de que la imagen del `api` instala la rueda binaria sin compilar; generación y doble hash (`sha256` → `sha256`, `bytea`) de tokens de invitación y refresh; JWT `HS256` fijo con `exp` e `iss` obligatorios, clave derivada de `SECRET_KEY`, rechazo de `alg` distinto y de `none`. (b) `SECRET_KEY` validada (B3 de T7; ≥ 32 bytes, Q11 DECIDIDO); verificación del rol de aplicación al arrancar (M2); `ENVIRONMENT` por defecto producción, cookie `__Secure-`/`Secure` salvo `development` explícito (B4 de T7) con `docker-compose.yml` y `.env.example` fijándolo; `Cache-Control: no-store` y `Referrer-Policy: no-referrer` en `/auth` e `/invitaciones`; límite de tamaño de cuerpo de 4 KB en los endpoints de auth (`413`, Q9); redacción de `DBAPIError` (tipo y `sqlstate`); `caplog` sin secretos.
- **Tests primero:** `test_credentials.py`, `test_config.py`, `test_log_redaction.py`.
- **Archivos probables:** `backend/app/auth/credentials.py`, `backend/app/config.py`, `backend/app/db.py`, `backend/app/errors.py`, `backend/pyproject.toml` y lock (solo dependencias aprobadas), `docker-compose.yml`, `.env.example`, `backend/tests/test_credentials.py`, `backend/tests/test_config.py`, `backend/tests/test_log_redaction.py`.
- **Verificación:** `cd backend && uv run pytest tests/test_credentials.py tests/test_config.py tests/test_log_redaction.py && uv run ruff check .`
- **Depende de:** T1; Q7, Q8, Q9 y Q11 decididos.
- **Nota:** de T4 solo se prueba el mecanismo de las cabeceras (`no-store`, `no-referrer`); las pruebas por ruta de `/auth` e `/invitaciones` se escriben en T6/T8/T9, cuando existan las rutas. Si T4 pasa de un día, se parte con `/sdd-change` (p. ej. configuración y logs aparte de credenciales).
- **Riesgo:** costo de hash lento en pruebas (costo bajo solo en tests); imprimir `SECRET_KEY`; romper el arranque local.
- **Cierre (T4):** hecha; H1 cerrado (0004 `_MIGRATOR_IS_MEMBER` por `rolname` exacto); 578 pruebas verdes; Argon2id m=19 MiB t=2 p=1 aceptado para el piloto por el `security-reviewer` (antes de producción: medir en el host de destino y subir a ~m=46 MiB t=1 o m=64 MiB t=3 p=1, 50–100 ms; solo seguro con rehash, hoy diferido: ver B3 en T6).
- **Siguiente: T4-endurecimiento** (inmediata, tests primero):
  - M1 (media): `ENVIRONMENT=test` en un proceso real desactiva el mínimo de `SECRET_KEY` y baja Argon2 (`config.py` `__post_init__` ~l.48-53, `credentials.py:185`, `ci-backend.yml:52`); relajaciones de `test` solo con `"pytest" in sys.modules` o flag explícito que ponen conftest y CI; lista cerrada de `ENVIRONMENT` (development, test, production, staging), fallar en otro valor; chequeo en CI/despliegue (C8) y warning al arrancar con `test`.
  - B1 (baja): contraseña con sustituto suelto revienta con `UnicodeEncodeError` (`credentials.py:130-147,162,174`); validar `encode("utf-8")` en `check_password_policy` y `verify`.
  - B2 (baja): la redacción de logs debe cubrir `SQLAlchemyError` y `psycopg.Error`, no solo `DBAPIError` (`errors.py` `_database_error_in_chain` ~l.70-111).
  - B6 (info): `pool_recycle` moderado (~30 min) en el engine para acotar la ventana de `ALTER ROLE ... BYPASSRLS`.
  - **Estado (2026-11-13, sin commit, pendiente de reviewer + security-reviewer):** M1 con `is_test_context()` = `"pytest" in sys.modules`, sin flag por entorno (quien fija `ENVIRONMENT` fijaría también el flag); `ENVIRONMENT` cerrado (`InvalidEnvironmentError`, sin repetir el valor); `test` fuera de pytest → `UnsafeTestEnvironmentError` al arrancar (probado en subproceso real); `TESTING` y Argon2 barato exigen además el contexto; aviso al arrancar con `test`. CI no cambia: `ENVIRONMENT=test` en `ci-backend.yml` solo lo usan pytest y Alembic (que no lee `Config`). `test_environment.py` falla si `docker-compose*.yml`/`Dockerfile*` fijan `ENVIRONMENT=test` (corre en CI); el chequeo de la imagen/compose de producción real queda en C8 (aún no existen). B1 (`contrasena_invalida`; `verify` → `False` sin Argon2, con y sin cuenta), B2 (`SQLAlchemyError` y `psycopg.Error`), B6 (`POOL_RECYCLE_SECONDS = 1800`). 626 verdes x2; 12 mutaciones detectadas. Pruebas ajustadas: `"prod"`, `"Development"` y `"desarrollo"` ya no son entornos válidos.
  - **Cierre (T4-endurecimiento):** hecha (2026-11-13); aprobada por `reviewer` y `security-reviewer`; 626 pruebas verdes.
  - **Deuda (C8):** imagen de producción con `uv sync --no-dev` (el Dockerfile de desarrollo instala pytest); ampliar la regex de `test_environment.py:206` (no cubre `${ENVIRONMENT:-test}`, `ENV ENVIRONMENT test`, `"ENVIRONMENT": "test"`) o inspeccionar `docker compose config` del compose de producción; documentar la ventana de `pool_recycle` (≤ 1800 s tras `ALTER ROLE ... BYPASSRLS`; la verificación del rol solo corre al abrir conexión, no en el pre-ping).
  - **Deuda (C8):** si algún proceso de producción llegara a importar pytest, `ENVIRONMENT=test` volvería a arrancar.
  - **Deuda O1 (info):** `_database_error_in_chain` no recorre `ExceptionGroup.exceptions` (`errors.py` ~l.80-95); hacerlo si se usan `TaskGroup` o grupos.
  - **Deuda O2 (info, T6+):** errores de base de datos fuera de los manejadores (p. ej. `teardown_request`) no pasan por `_handle_unexpected`; vigilar que no haya teardowns que toquen la base.
  - **Deuda para T6:** el handler de login trata el `False` rápido de `verify` (sustituto suelto o > 128) igual que cualquier otro `False`: mismo código, cuerpo y conteo de límite de tasa.
  - **Opcional:** la prueba de B6 usa atributos privados de SQLAlchemy (`engine.pool._recycle`, `_pre_ping`); puede romperse al actualizar.
- **Deuda para T6:** B3 `needs_rehash` tras login correcto: diferido; requiere `/sdd-change` y decisión humana (ver cierre de T6); `/auth/refresh` solo `POST` (cookie `SameSite=Lax`); B5 prueba por ruta de `no-store`, `no-referrer` y `413` bajo `/auth` e `/invitaciones`.
- **Deuda para T6–T9 (aislamiento):** token con `tenant` de otro tenant no accede; `rol` falsificado en el claim no eleva privilegios; membresía inactiva no accede con JWT válido; unificar código/cuerpo de "email ocupado" y clave inválida (H5, T9).
- **Info/opcionales (T4):** B4 exigir `str(uuid) == claim` en `sub`/`tenant`; B7 rechazar `SECRET_KEY` de un solo carácter repetido; B8 la prueba de tiempos con margen 0,5x–2x puede flaquear en CI cargada (más muestras o marcarla lenta); verificación manual pendiente de `docker compose build api` (se probó con `--no-build`); `ENVIRONMENT` obligatoria sin defecto (más estricto que la spec, que pedía producción por defecto); `prohibido` vs `sin_permiso` alineado en T8 (`prohibido` global en `errors.py`, también para el rechazo CSRF de refresh/logout); proxy delante de gunicorn por cuerpos chunked lentos.
- **Pendiente del humano (T4):** `.env.example` debe fijar `ENVIRONMENT=development` y avisar que `SECRET_KEY` necesita ≥ 32 bytes (`python -c "import secrets; print(secrets.token_urlsafe(48))"`); sus permisos impiden que lo editen los agentes.

### T5 — Script del operador: tenant y primera invitación admin

- **Resultado:** `flask create-tenant <nombre> <email>` genera el token, calcula la clave y llama a `acceso.crear_tenant` (una transacción; rol `admin`, `creada_por` NULL, 24 h); enlace una vez a stdout, sin guardar ni registrar; solo rol admin; credenciales del migrador solo por entorno; no corre en el contenedor `api`. **La prueba corre con un migrador de prueba sin superusuario ni `BYPASSRLS`** (creado por la prueba, con `USAGE` en `acceso` y `EXECUTE` en `crear_tenant`), no con `POSTGRES_USER`; comprueba que ese rol no puede INSERT directo y que la aplicación no puede ejecutar `crear_tenant`.
- **Tests primero:** `test_cli_tenant.py` falla antes del comando.
- **Archivos probables:** `backend/app/cli.py`, `backend/tests/test_cli_tenant.py`, `backend/tests/conftest.py`, `README.md`, `.env.example`.
- **Verificación:** `cd backend && uv run pytest tests/test_cli_tenant.py` y ejecución manual, comprobando que `invitacion` solo tiene `sha256(clave)`.
- **Depende de:** T3, T4 (Q3, Q5, Q17 decididos).
- **Riesgo:** enlace en logs o historial; credenciales en argv; prueba que pase solo por ser superusuario.
- **Estado (2026-11-13, sin commit, pendiente de reviewer + security-reviewer):** `backend/app/cli.py` (`create-tenant`, registrado en `create_app`; exige además `DATABASE_URL`, `SECRET_KEY` y `ENVIRONMENT` porque `flask --app app` crea la app) con `load_migration_url` (solo entorno, rechaza el mismo rol que `DATABASE_URL`), `new_token`/`token_key` de T4, una transacción y enlace relativo `/invitacion#<token>` a stdout tras el `COMMIT`; errores de base solo con tipo y `sqlstate`. `test_cli_tenant.py` (24 pruebas, base temporal y migrador `prueba_migrador_*` `NOSUPERUSER NOBYPASSRLS` con solo `USAGE`/`EXECUTE`, incluido un proceso real `flask` con `ENVIRONMENT=development`). `.env.example` no cambia (`MIGRATION_DATABASE_URL` ya figura). README: sección del operador con `-e MIGRATION_DATABASE_URL` sin valor (fuera de argv). 650 verdes x2.
- **Abierto (humano):** (1) URL base de la web para el enlace (no está en la spec; hoy se imprime la ruta relativa, igual en T8); (2) si el comando debe negarse a correr con un migrador superusuario o `BYPASSRLS` (Q5) aunque en local y CI el migrador es `POSTGRES_USER`; (3) confirmar que un contenedor efímero `docker compose run api` cuenta como "no corre en el contenedor `api`". Revisados por `reviewer` y `security-reviewer`: aceptables.
- **Cierre (T5):** hecha (2026-11-13); aprobada por `reviewer` y `security-reviewer`; 650 pruebas verdes. README: subshell para `.env`, contraseña codificada en la URL, `read -rs` en producción, enlace con `https://<dominio-de-la-web>`, sin redirigir stdout (token 24 h).
- **Deuda (hallazgo 5, decisión humana):** aviso por stderr no bloqueante si el migrador es `rolsuper` o `rolbypassrls` (`pg_roles` por `current_user`); opcional negarse si `ENVIRONMENT` no es `development`.
- **Deuda (hallazgo 7):** tope de longitud (nombre ~200, email 254) y rechazo de caracteres de control en el nombre (`cli.py:66-71`).
- **Documentado (hallazgo 6):** dos ejecuciones crean dos tenants independientes (`tenant.nombre` no es único); si `click.echo` falla tras el `COMMIT` (BrokenPipe) queda un tenant sin enlace: se crea otra invitación.
- **Pruebas pendientes:** atomicidad (email que viole el CHECK → no queda tenant); dos ejecuciones con mismo email/nombre; prueba del aviso del hallazgo 5 si se implementa.
- **Opcional (con T8/web):** `WEB_BASE_URL` para imprimir el enlace completo, exigiendo `https` fuera de `development`.
- **Deuda (C8 / T4-I1):** `sha256(token)` es credencial equivalente al token y viaja como parámetro ligado a `crear_tenant`; fijar en el servidor `log_statement=none`, sin `pg_stat_statements` ni `auto_explain` con parámetros (`docker/postgres/init/01-app-role.sh:74-75` es solo un `SET` de sesión).
- **Verificación manual pendiente:** `docker compose build api` y probar el ejemplo del README en el contenedor efímero.
- **Fragilidad menor:** `test_command_rejects_credentials_or_role_in_argv` depende del texto "No such option" de click.

### T6 — Login y usuario actual

- **Resultado:** `POST /auth/login` y `GET /auth/me`; respuesta genérica, hash simulado, rechazo de inactivos, falla cerrado con varias membresías (Q6); JWT con tenant; refresh emitido (cookie `HttpOnly`/`Secure`/`SameSite=Lax`, `<tenant_id>.<secreto>`, `familia_id` nueva); rol y `activa` leídos de `membresia`.
- **Tests primero:** `test_auth_login.py` (A10, A21).
- **Archivos probables:** `backend/app/auth/routes.py`, `backend/app/auth/service.py`, `backend/app/__init__.py`, `backend/tests/test_auth_login.py`.
- **Verificación:** `cd backend && uv run pytest tests/test_auth_login.py`
- **Depende de:** T3, T4 (Q6, Q7 decididos: acceso 15 min, refresh 7 días).
- **Riesgo:** enumeración por mensaje o tiempo; `buscar_login` dentro de `tenant_session`.
- **Cierre (T6):** hecha (2026-11-13); aprobada por `reviewer` y `security-reviewer`; 728 pruebas verdes.
- **Contrato JSON (decidido por el implementer, no fijado por la spec; lo hereda 002b/OpenAPI):** `POST /auth/login` → 200 `{access_token, token_type: "Bearer", expires_in: 900, usuario: {id, email, nombre}, tenant: {id, nombre}, rol}` + cookie de refresh; 400 `solicitud_invalida` (cuerpo no objeto, campos no texto, JSON inválido, `Content-Type` distinto de JSON); 401 `credenciales_invalidas` ("Correo o contraseña incorrectos.") uniforme. `GET /auth/me` → `{usuario, tenant, rol}`; 401 `no_autenticado`.
- **B3 `needs_rehash`: diferido, bloqueado por R4e** (la app no puede `UPDATE usuario` y no hay función `acceso.*` que reescriba `password_hash`); requiere `/sdd-change` y decisión humana. Opciones del `security-reviewer`: (A, recomendada para el piloto) fijar los parámetros definitivos de Argon2 midiéndolos en el host de destino **antes** de crear cuentas de producción y no prometer rehash; (B, con la spec de cambio/restablecimiento de contraseña) `acceso.actualizar_password_hash(p_usuario_id, p_hash_actual, p_hash_nuevo)` plpgsql `STRICT SECURITY DEFINER`, `GRANT UPDATE (password_hash)` solo a `auth_owner`, compare-and-set; mientras convivan parámetros, el dummy sigue el costo de los hashes vigentes (oráculo transitorio documentado). Riesgo: subir parámetros sin rehash deja las cuentas existentes más rápidas que el dummy y rompe A10.
- **R1 (alta si se expone):** sin límite de tasa hasta T10; **no exponer `/auth/login` ni ir al piloto antes de T10** (intentos ilimitados y DoS de CPU/memoria, 19 MiB por verificación). En T10: clave por cuenta con la salida de `normalize_email`; emails no normalizables (NUL, sustituto, vacío) comparten un cubo fijo; IP solo del proxy conocido; contador en transacción propia, antes de Argon2 o tras el fallo.
- **T6-endurecimiento (M1, media; hecha 2026-11-13, aprobada por `reviewer`, 730 pruebas verdes):** con `sqlalchemy.engine` en DEBUG el log vuelca filas con el hash Argon2 y el resultado de `buscar_login` (`hide_parameters` no oculta filas). Fijar `logging.getLogger("sqlalchemy.engine").setLevel(WARNING)` en `init_db` (`db.py:165`) y prueba con el logger en DEBUG antes de `create_app` que exija que `$argon2` y el email no aparezcan.
  - **Estado (2026-11-13, aprobada por `reviewer`; solo toca logging, sin segunda auditoría de seguridad):** M1 hecha: `init_db` fija `sqlalchemy.engine`/`sqlalchemy.pool` en WARNING antes de `create_engine`, `echo=False`/`echo_pool=False` literales y filtro que descarta los DEBUG (`Row`/`Col`) de `sqlalchemy.engine.Engine`; 2 pruebas en `test_auth_login.py` (DEBUG antes y después de `create_app`, `echo="debug"`); 730 verdes x2; 6 mutaciones detectadas.
  - **Deuda opcional (M1):** (a) prueba que haga grep de `logging_name` en `backend/app/`: si alguien lo pasa a `create_engine`, el filtro de `sqlalchemy.engine.Engine` dejaría de cubrirlo.
    (b) El efecto del arreglo es global al proceso: para depurar SQL hay que subir el nivel después de `create_app`.
    (c) Los loggers de otros módulos de SQLAlchemy (p. ej. `sqlalchemy.orm`) no quedan cubiertos; hoy no se usa ORM de forma que importe.
- **Deuda:** N1 (baja, T9/T10) `normalize_email` de Python no coincide con `lower(btrim())` de Postgres (NBSP, casos raros de Unicode): un único normalizador para login, invitación (T8/T9) y `limite_tasa` (T10), preferible en SQL. N4 (T7) el JWT de acceso no se revoca con el logout (hasta 15 min, Q7/A11): documentarlo. N5 (T8) `authenticate` abre una `tenant_session` y el endpoint otra: `require_auth` guarda la sesión en `g` o se documenta la ventana. N6 (T7/T9) un login nuevo no revoca familias anteriores: decidir. N2/N3 aceptados.
- **Pruebas de aislamiento recomendadas:** T7: cookie `<tenant_B>.<secreto de A>`, la rotación relee `activa`/`usuario.activo`, el reuso revoca solo la familia, logout con cookie ajena no revoca, 401 indistinguible, rotación atómica concurrente. T8: contador 403, admin de A no ve ni invita en B aunque el cuerpo mande `tenant_id`, token con tenant forjado 401, `creada_por` del token. T9: invitación de A no crea membresía en B, clave inválida = usada = vencida, aceptación paralela con un solo ganador, email de otro tenant indistinguible. Transversal: `caplog` con el logger del engine en DEBUG (M1) y coincidencia `normalize_email`/`limite_tasa` (N1).
- **Menores:** el 400 `solicitud_invalida` y el nombre `REFRESH_TOKEN_TTL` (7 días) no están en la spec. La mutación 2 (membresía inexistente en `/auth/me`) **no** es equivalente: sin `membresia is None or` da 500 y la detectan 4 pruebas; la equivalente es quitar `account.activo` en `service.py:116` (defensa en profundidad: se deja).

### T7 — Refresh y logout

- **Resultado:** `POST /auth/refresh` con rotación en un `UPDATE` atómico, cabecera personalizada y comprobación `Origin`/`Sec-Fetch-Site` (Q14, decidido); ventana de gracia ~10 s y revocación de familia ante reuso (Q15, decidido; A23); `POST /auth/logout` por cookie de refresh que revoca la familia y limpia la cookie (A11).
- **Tests primero:** `test_auth_refresh_logout.py`.
- **Archivos probables:** `backend/app/auth/routes.py`, `backend/app/auth/service.py`, `backend/tests/test_auth_refresh_logout.py`.
- **Verificación:** `cd backend && uv run pytest tests/test_auth_refresh_logout.py`
- **Depende de:** T6 (Q7, Q14, Q15 decididos).
- **Riesgo:** refresh que sobrevive al logout; condiciones de carrera en la rotación.
- **Cierre (T7):** hecha (2026-11-13); aprobada por `reviewer` y `security-reviewer`; 784 pruebas verdes. M1 (carrera logout/reuso contra una rotación en vuelo) corregido repitiendo el `UPDATE` de revocación hasta 0 filas (tope 10 pasadas), con 2 pruebas.
- **Decisiones ratificadas por el humano (2026-11-13; la spec no las fijaba):** (a) cabecera `X-AssetControl-CSRF: 1` (la web de la 002b debe enviarla). (b) `is_same_site_request()`: cabecera obligatoria; con `Sec-Fetch-Site`, solo `same-origin`/`same-site`; sin él, hostname de `Origin` igual al de `request.host_url` sin comparar puerto; `Origin: null` rechazado; sin ninguna de las dos basta la cabecera; fallo 403 `prohibido` (alineado en T8; ya no es `sin_permiso`). (c) Una cuenta desactivada consume el refresh sin revocar la familia. (d) Refresh vencido y no usado → 401 sin revocar; usado fuera de ventana revoca aunque esté vencido.
- **Contrato:** refresh 200 = mismo cuerpo que login + cookie rotada; refresh 401 `no_autenticado` **sin** `Set-Cookie` (a propósito: la pestaña perdedora no borra la cookie ganadora); logout 204 siempre, con cookie borrada.
- **Deuda y riesgos:**
  - N4: el JWT de acceso sigue vivo hasta 15 min tras el logout (Q7). Propuesta del `security-reviewer`: añadirlo a la tabla de riesgos de la spec y reformular A11 como "el refresh y la cookie dejan de servir"; pendiente de aplicar en `spec.md` (decisión humana).
  - N6: un login nuevo no revoca familias previas; ninguna Q lo decide. Recomendación: mantenerlo (multidispositivo) y que todo cambio de contraseña futuro revoque todas las familias; pendiente de ratificación humana.
  - O1: la familia no tiene tope absoluto de vida (cada rotación da +7 días; una cookie robada y rotada a diario no vence; solo la detección de reuso la frena; Q7 no pide tope); decisión humana.
  - O2: `Sec-Fetch-Site: same-site` acepta subdominios hermanos; la cabecera personalizada obliga a preflight y la API no responde `Access-Control-*`. En T8, prueba que fije que `/auth/*` no tiene cabeceras CORS; no añadir flask-cors.
  - O3: el respaldo por `Origin` ignora esquema y puerto (deliberado, por el proxy de Vite).
  - O4: un proxy que no preserve `Host` (o `changeOrigin` en Vite) hace fallar cerrado el respaldo por `Origin` en navegadores sin `Sec-Fetch-Site` (spec de despliegue).
  - O5: `if membresia is None` y `loaded[0].id != membresia.id` son código defensivo inalcanzable (la FK compuesta lo garantiza).
  - O6: al desactivar una membresía hay que revocar sus refresh (tarea de gestión de miembros).
  - O7: el cliente web no debe llamar a logout tras un 401 de refresh ni reintentar refresh a ciegas pasados 10 s (revocaría la familia viva).
  - M1 (opcional): `_revoke_family` termina en silencio si agota las 10 pasadas (irreal); recomendado `for ... else: raise RuntimeError` (2 líneas, falla cerrado). La espera fija de 1 s de las pruebas de M1 podría robustecerse esperando `wait_event_type='Lock'` en `pg_stat_activity`.
- **Para T10:** el límite de refresh (30/IP en 15 min) toparía con una clínica de ~30 usuarios activos tras un NAT (cada uno refresca cada 15 min): contar solo los 401 o subir el umbral; el logout comparte contador; un `X-Forwarded-For` falso no evade el límite; 429 idéntico para cuentas existentes e inexistentes.
- **Pruebas de aislamiento recomendadas:**
  - T8: `require_auth` con JWT de tenant A y `sub` con membresía solo en B → 401; contador 403 en rutas de admin; rol/tenant del cuerpo, URL o cabecera ignorados; sin cabeceras `Access-Control-*` en `/auth/*`.
  - T9: invitación de A usada con la cookie de B no activa nada en B; un solo ganador en aceptación paralela; expirada = mismo error genérico; usuario con membresía en otro tenant falla cerrado (Q6); aceptar no emite refresh hasta el login.
  - T10: los contadores de refresh y logout no mezclan IPs ni cuentas; el rol de la app no puede borrar de `limite_tasa`.

### T8 — Autorización por rol e invitar

- **Resultado:** `require_auth` y `require_role` (rol y `activa` desde `membresia` por petición, A24); `POST /invitaciones` (solo `admin`, `{email, rol}`) con `creada_por` NOT NULL, tenant del token y enlace una vez (Q13); `contador` → `403`, sin token `401`; JWT inválido (A25); aislamiento por endpoint (A12).
- **Tests primero:** `test_roles.py`, `test_invitaciones_crear.py`.
- **Archivos probables:** `backend/app/auth/decorators.py`, `backend/app/invitaciones/routes.py`, `backend/app/invitaciones/service.py`, `backend/tests/test_roles.py`, `backend/tests/test_invitaciones_crear.py`.
- **Verificación:** `cd backend && uv run pytest tests/test_roles.py tests/test_invitaciones_crear.py`
- **Depende de:** T6 (Q7 y Q13 decididos: enlace `/invitacion#<token>`, invitación 72 h).
- **Riesgo:** rol tomado del token o de la petición; token en logs.
- **Cierre (T8):** hecha (2026-11-13); aprobada por `reviewer` y `security-reviewer`; 885 pruebas verdes. Solo `POST /invitaciones`: listar usuarios/invitaciones y revocar quedan fuera (`spec.md`:81, `plan.md`:118). N5 de T6 resuelto: una sola `tenant_session` por petición vía `require_role`/`require_auth`. Código 403 alineado: `prohibido` global (`errors.py`), también para el rechazo CSRF de refresh/logout (T7 (b), T4 "Info").
- **Contrato (decidido por el implementer; la spec solo fija el enlace `/invitacion#<token>`, Q13; la 002b lo ratifica):** `POST /invitaciones {email, rol}` → `201 {"invitacion": {id, email, rol, expira_en ISO 8601}, "enlace": "/invitacion#<token>"}`; `rol` exactamente `admin`|`contador`; campos extra (`tenant_id`, `creada_por`, `expira_en`, `usada_en`, `token_hash`, `id`) ignorados; `400 solicitud_invalida`, `401 no_autenticado`, `403 prohibido` (antes de leer el cuerpo), `413 cuerpo_demasiado_grande`, `405`; varias pendientes por email permitidas; `expira_en` = `now()` + 72 h (Q7); un admin puede invitar a admin. En `models.py`, `Invitacion.usada_en` con `server_default=FetchedValue()` solo evita que el ORM la incluya en el INSERT (la app no tiene INSERT sobre esa columna; sin cambio de esquema).
- **Hallazgos del `security-reviewer` (T8):**
  - H1 (media; decisión humana antes de T9/gestión de miembros): las invitaciones vigentes sobreviven a la baja o degradación de quien las creó (`aceptar_invitacion` no mira `creada_por` ni su membresía; 0004:178-181); un admin comprometido deja invitaciones admin de hasta 72 h y no hay endpoint para listar/revocar. Opciones: (A) documentar que sobreviven (72 h); (B) que `aceptar_invitacion` rechace si el creador ya no tiene membresía activa (requiere `/sdd-change` y función SQL); (C) endpoints de revocación en una spec futura.
  - H2 (baja-media; T10): `POST /invitaciones` sin límite de tasa ni tope de pendientes; T10 solo cubre login, refresh, validar y aceptar → añadir tope por tenant/creador o de pendientes.
  - H3 (baja; unificar con N1 en T9): 27 code points (U+1C89, U+A7CB/CC/DA/DC, bloque U+10D50…) pasan `normalize_email` de Python pero violan el CHECK `lower(btrim())` de Postgres 17 → 500 en vez de 400; añadir prueba que espere 400 y normalizar en SQL o limitar el rango.
  - H4 (info): `current_user()` queda en `g` tras la vista (solo se limpia `_SESSION_KEY`): sacar `_USER_KEY` de `g` en el `finally` y probar que `current_user()` lanza tras la vista (la mutación que quita `g.pop` sobrevive).
  - H5 (info): el rol se lee sin bloqueo al inicio de la transacción (coherente con A24).
  - H6 (info): sin tope de longitud del email ni rechazo de caracteres de control (igual que T5, hallazgo 7).
  - H7 (info): `Flask(__name__)` registra la ruta `static` (hoy sin `app/static`); mantenerla en la lista pública del catálogo o desactivarla con `static_folder=None`.
  - H8 (info): Dockerfile de desarrollo con `flask run --reload` (C8).
- **Menores del `reviewer` (T8):** la transacción queda abierta mientras la vista corre (hoy un INSERT; vigilar en T9 y specs siguientes); sin prueba directa de que un fallo de commit dé 500 sin entregar el enlace (el `security-reviewer` lo comprobó con una prueba propia); aviso git LF→CRLF.
- **Pruebas recomendadas por el `security-reviewer`:**
  - T9: invitación de A aceptada con credenciales o cookie de B no activa nada en B; un solo ganador en aceptación paralela; vencida, usada, inexistente o email duplicado dan el mismo error y la misma forma; invitación de un creador dado de baja o degradado (según la opción de H1); usuario con membresía en otro tenant falla cerrado (Q6); validar y aceptar no tocan `tenant_session` ni emiten refresh; las rutas nuevas de `/invitaciones/*` se añaden a `PUBLIC_ENDPOINTS` y a la prueba de CORS; prueba de catálogo conductual (anónimo → 401, contador → 403 en cada ruta protegida).
  - T10: contadores de login/refresh/validar/aceptar no mezclan IP ni cuenta; la app no puede DELETE en `limite_tasa`; `caplog` con DEBUG en validar/aceptar sin tokens; `purgar-limite-tasa` solo con el rol migrador.

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
