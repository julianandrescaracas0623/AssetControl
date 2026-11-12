# Tasks 001 — Fundación técnica

> Máximo 10 tareas. Cada una ≤ 1 día. Una a la vez.
> Comando de verificación obligatorio antes de cerrar.
> **Estado de la spec:** aprobada (2026-11-11). Gestor de dependencias de Python: uv. En el backend, los comandos se ejecutan con `uv run` (p. ej. `uv run pytest`, `uv run ruff check .`, `uv run alembic ...`). OpenAPI y tipos generados entran en la spec 002.

---

### T1 — Estructura del monorepo

- **Depende de:** —
- **Archivos:** `backend/`, `web/`, `.gitignore`, `README.md`
- **Criterio:** existen `backend/` y `web/`; `.gitignore` excluye `.env`, `datos/`, `node_modules`, `dist`, `__pycache__`, `.venv`, `.pytest_cache` y el arnés local.
- **Verificación:** `git status --short` y `git check-ignore -v datos AGENTS.md .claude`
- **Riesgo:** ninguno.

---

### T2 — Backend: configuración y application factory

- **Depende de:** T1
- **Archivos:** `backend/app/__init__.py`, `backend/app/config.py`, `backend/pyproject.toml` (dependencias con uv), archivo de lock de uv, `backend/tests/test_app_factory.py`, `backend/tests/test_config.py`
- **Criterio:** `create_app()` se importa sin abrir conexiones; la falta de una variable obligatoria falla con el nombre de la variable y sin su valor; el entorno se crea con uv desde `pyproject.toml`.
- **Verificación:** `cd backend && uv run pytest tests/test_app_factory.py tests/test_config.py`
- **Riesgo:** inicializar el engine al importar rompe las pruebas.

---

### T3 — Backend: sesión de datos y aislamiento por tenant (RLS + filtro simple)

> Reescrita el 2026-11-11 (decisión humana tras 3 revisiones). Ver `spec.md` R4–R4d y `plan.md` §2 y §7.

- **Depende de:** T2. Adelanta de T7 el script de init del rol de la aplicación y su montaje en `docker-compose.yml`; no requiere T6 (la tabla de prueba no pasa por Alembic).
- **Archivos:** `backend/app/db.py`, `backend/tests/test_tenant_scope.py`, `backend/tests/conftest.py` (fixtures con conexión del rol de la aplicación y del rol migrador; enmascarar también las URL nuevas), `docker/postgres/init/01-app-role.sh` (ruta `[PROPUESTA]`), `docker-compose.yml` (solo montar el script y pasar `APP_DB_USER`/`APP_DB_PASSWORD`).
- **Criterio:**
  - Se crea el rol de la aplicación (`LOGIN`, `NOSUPERUSER`, `NOBYPASSRLS`, no dueño) con el script de init; `TEST_DATABASE_URL` se conecta con él.
  - `tenant_session(tenant_id)` valida el UUID, abre transacción y ejecuta `set_config('app.tenant_id', :tenant_id, true)` con parámetro enlazado; falla sin tenant.
  - Mixin `TenantScoped`; `with_loader_criteria` en `do_orm_execute`; asignación de `tenant_id` al insertar; rechazo de `text()` y `Session.connection()` dentro de `tenant_session`.
  - Se eliminan `_check_statement_elements` y la verificación por `SELECT` en `before_flush`.
  - La tabla de prueba con `tenant_id`, `ENABLE` + `FORCE ROW LEVEL SECURITY`, su política `USING`/`WITH CHECK` y sus `GRANT` se crean solo en las pruebas, con el rol migrador.
  - Con dos tenants, conectado como rol de la aplicación: el ORM solo ve su tenant; un `INSERT` con otro `tenant_id` es rechazado; sin tenant fijado no hay filas ni escritura (también en una conexión del pool que ya tuvo tenant); RLS bloquea al otro tenant por `get_bind()`, engine, SQL crudo por conexión del rol de la aplicación, API *bulk* heredada y `join()` explícito.
  - Prueba de atributos: `rolsuper` y `rolbypassrls` falsos para el rol de la aplicación; `relrowsecurity` y `relforcerowsecurity` verdaderos en la tabla de prueba.
- **Verificación:** `docker compose up -d db` (si el volumen `pgdata` ya existía sin el rol, recrearlo con `docker compose down -v`, que borra solo datos locales de desarrollo) y luego `cd backend && uv run pytest tests/test_tenant_scope.py && uv run ruff check .`
- **Riesgo:** rol de la aplicación con `BYPASSRLS`, superusuario o dueño sin `FORCE` (anula RLS en silencio; lo detecta la prueba de atributos); `set_config` de sesión en lugar de local (fuga entre peticiones por el pool); `SET LOCAL` que sobrevive a un *savepoint* en la transacción externa de las pruebas; `''::uuid` sin `NULLIF` en la política.

---

### T4 — Backend: salud y errores

- **Depende de:** T2, T3
- **Archivos:** `backend/app/meta/__init__.py`, `backend/app/meta/routes.py`, `backend/app/errors.py`, `backend/app/version.py`, `backend/tests/test_health.py`, `backend/tests/test_errors.py`
- **Criterio:** `/health` responde 200 con `{status, db, version}` y 503 si la base falla; un error no controlado responde JSON uniforme con `request_id` y sin traza.
- **Verificación:** `cd backend && uv run pytest tests/test_health.py tests/test_errors.py`
- **Riesgo:** exponer detalles internos en el mensaje de error.
- **Deuda heredada de T3 (2026-11-11):** el manejador de errores nunca devuelve `str(exc)` de psycopg/SQLAlchemy (puede incluir SQL, host o base): mensaje genérico + `request_id`. `/health` hace el ping por una función de `app/db.py` sin tenant (p. ej. `ping_database()`), no con `tenant_session` (ahí `connection()` y `text()` están rechazados).
- **Implementada y aprobada (2026-11-11):** 100 pruebas pasan con base real; aprobada por reviewer y security-reviewer.
  - `backend/app/version.py` guarda la versión en código porque uv no instala el proyecto; una prueba en `test_health.py` verifica que coincide con `pyproject.toml`.
  - **Decisión humana (2026-11-11):** `connect_timeout` fijo de 5 s como constante `CONNECT_TIMEOUT_SECONDS` en `app/db.py`, global al engine; no configurable por ahora (solo si Supabase en producción lo exige).
  - Deuda de operación heredada de T4: ver `plan.md` §4 "Deuda de operación (heredada de T4)"; la parte de despliegue se cierra en T10.

---

### T5 — Arnés de pruebas

- **Depende de:** T2, T3, T4
- **Archivos:** `backend/tests/conftest.py`, `backend/tests/test_harness.py`, `backend/pyproject.toml`
- **Criterio:** cada prueba corre en una transacción con rollback sobre PostgreSQL; `pytest` se puede correr dos veces seguidas sin residuos; hay fixtures de app y de cliente HTTP.
- **Verificación:** `cd backend && uv run pytest && uv run pytest` (en local: `uv run --env-file ../.env pytest`).
- **Riesgo:** dejar datos de prueba entre corridas.
- **Deuda heredada de T3 (2026-11-11):** decidir y anotar en `conftest.py` si se mantiene "crear/borrar tablas por prueba" (como hace hoy T3) en lugar de "transacción con rollback por prueba" (`plan.md` §2), y el riesgo de `SET LOCAL` con *savepoints* (`plan.md` §4).
- **Decisión (2026-11-11, documentada en `conftest.py`):**
  - Por defecto, transacción con rollback por prueba: fixtures `db_connection`, `app` y `client`; la fábrica de sesiones se ata a una transacción externa con `join_transaction_mode="create_savepoint"` y al final se revierte.
  - Se mantiene crear/borrar tablas con `commit` real en `pg_app` de T3: esas pruebas verifican límites reales de transacción y del pool que una transacción externa ocultaría.
  - Mitigación de `SET LOCAL` con *savepoints*: al terminar cada transacción raíz de la sesión se vacía `app.tenant_id` en la conexión de la prueba; lo cubren `test_tenant_does_not_survive_*` en `test_harness.py` (fallan sin la mitigación).
  - Guardián de residuos de sesión (`database_residue_guard`): falla si quedan tablas `prueba_*` o cambian tablas, políticas o conteos fuera de ellas.
- **Deuda de T5 (resolver antes de la spec 002):** bajo `FORCE ROW LEVEL SECURITY` el conteo de filas del guardián, sin `app.tenant_id`, da 0 en las tablas de negocio, así que no detecta filas residuales en ellas. Decidir cómo contarlas (por tenant, rol de pruebas con `BYPASSRLS` o `pg_stat_user_tables`).

---

### T6 — Alembic y revisión inicial

- **Depende de:** T2
- **Archivos:** `backend/alembic.ini`, `backend/migrations/env.py`, `backend/migrations/versions/0001_baseline.py`
- **Criterio:** `upgrade head` y `downgrade base` funcionan sobre una base vacía; no crea tablas de negocio. `env.py` se conecta con `MIGRATION_DATABASE_URL` (rol migrador, nombre `[PROPUESTA]`), nunca con el rol de la aplicación. Queda documentado en `migrations/` (comentario o README corto) el **patrón obligatorio de toda tabla de negocio** para la spec 002: en el mismo `upgrade`, `ENABLE` + `FORCE ROW LEVEL SECURITY`, política `tenant_isolation` con `USING`/`WITH CHECK` sobre `NULLIF(current_setting('app.tenant_id', true), '')::uuid` y `GRANT` mínimos al rol de la aplicación; el `downgrade` los revierte (`plan.md` §2 y §6).
- **Verificación:** `cd backend && uv run alembic upgrade head && uv run alembic downgrade base && uv run alembic upgrade head`
- **Riesgo:** `env.py` usando por error la URL del rol de la aplicación (sin permisos de DDL) o la aplicación usando la del migrador (dueño: RLS no se le aplicaría sin `FORCE`).
- **Implementada y aprobada (2026-11-12):** 131 pruebas pasan con base real; aprobada por reviewer y security-reviewer (incluida la corrección M1).
  - La prueba de `upgrade`/`downgrade`/`upgrade` corre sobre una base temporal vacía creada y borrada por la propia prueba (requiere `CREATEDB` en el rol de `TEST_MIGRATION_DATABASE_URL`).
  - Guard de mismo rol: `load_migration_url` compara el usuario de `MIGRATION_DATABASE_URL` y `DATABASE_URL` con `make_url` (mismo parser que el engine, decodifica `%XX`); si alguna no se puede interpretar falla (fail-closed) sin mostrar la URL; dos URL sin usuario cuentan como mismo rol.
- **Deuda de T6 (security-reviewer, para la spec 002 / T7):**
  - M2: antes del piloto, verificación al arrancar de que el rol de la aplicación no tiene `rolsuper` ni `rolbypassrls`.
  - Patrón RLS en `migrations/`: `REVOKE` a `anon`/`authenticated`/`service_role` en Supabase; `USAGE` en secuencias; tablas globales sin `tenant_id`; el `downgrade` solo en dev/CI; prueba global de que toda tabla con `tenant_id` tenga RLS + `FORCE` + política.
  - El nombre del rol en SQL se cita con `identifier_preparer.quote`.
  - `file_template` de `alembic.ini` sin slug.
  - T7: `MIGRATION_DATABASE_URL` y `TEST_MIGRATION_DATABASE_URL` en `.env.example`.

---

### T7 — Entorno local con Docker

- **Depende de:** T2, T3, T6
- **Archivos:** `docker-compose.yml`, `backend/Dockerfile`, `.env.example`
- **Criterio:** `docker compose up` levanta la API con recarga y PostgreSQL con la imagen `postgres:17` (igual versión mayor que Supabase, 17.11 confirmada el 2026-11-11); la API se conecta con el rol de la aplicación creado por el script de init de T3; el `Dockerfile` instala las dependencias con uv desde `pyproject.toml` y su lock; `.env.example` lista las variables sin valores reales, incluidas las nuevas de `plan.md` §2 (`MIGRATION_DATABASE_URL`, `APP_DB_USER`, `APP_DB_PASSWORD`, `TEST_MIGRATION_DATABASE_URL`); `.env` está ignorado.
- **Verificación:** `docker compose up --build` + `curl http://localhost:5000/health`
- **Riesgo:** `localhost` dentro del contenedor no apunta al host.
- **Deuda heredada de T3 (2026-11-11):**
  - `docker-compose.yml` publica el puerto de PostgreSQL solo en `127.0.0.1` (`"127.0.0.1:5432:5432"`).
  - *Healthcheck* con `pg_isready` y verificación de que existe el rol `APP_DB_USER` con `rolsuper` y `rolbypassrls` falsos.
  - `.gitattributes` con `docker/**/*.sh text eol=lf` (sin esto un clon en Windows deja el script en CRLF y el init falla).
  - `.env.example` con `APP_DB_USER` (valor sugerido `assetcontrol_app` solo como comentario), `APP_DB_PASSWORD`, `MIGRATION_DATABASE_URL`, `TEST_DATABASE_URL` y `TEST_MIGRATION_DATABASE_URL`, sin valores.
  - README: `docker compose down -v` si el volumen no tiene el rol, y `APP_DB_USER` debe ser distinto de `POSTGRES_USER`.
- **Implementada (2026-11-12), pendiente de revisión:** `docker compose up --build` deja `db` sano (healthcheck con `pg_isready` y rol de la aplicación sin `rolsuper` ni `rolbypassrls`) y `GET /health` responde `200` con `db: ok`; la API usa el host `db` y el rol de la aplicación; recarga verificada; 131 pruebas pasan dentro del contenedor `api`.
  - Cambios del reviewer (2026-11-12): `.env.example` añadido; README con el comando de pruebas dentro del contenedor `api` (`TEST_DATABASE_URL` y `TEST_MIGRATION_DATABASE_URL` sobre `assetcontrol_test`).
  - Security-reviewer (2026-11-12): aprobada con M1 y B1, corregidos con autorización humana.
    - M1 resuelto: `MIGRATION_DATABASE_URL` sale del servicio `api`; el README documenta migrar con `docker compose run --rm -e MIGRATION_DATABASE_URL=... api uv run alembic upgrade head` (contenedor efímero).
    - B1 resuelto: el README avisa que las contraseñas de `.env` deben ser alfanuméricas (el comando carga `.env` en el shell y los valores quedan en los argumentos del proceso del host; solo desarrollo local).
- **Deuda de T7 (security-reviewer):**
  - B2: el montaje `./backend:/app` es de lectura/escritura; valorar `:ro` (cuidar la caché de pytest/ruff).
  - B3: validar longitud y debilidad de `SECRET_KEY` en la spec de auth.
  - B4: `ENVIRONMENT` cae en `development` por defecto; el compose es solo para desarrollo, nunca para producción.
  - B5: fijar las imágenes (`postgres:17`, base de Python) por digest.
  - M2 de T6: antes del piloto, verificación al arrancar de `rolsuper`/`rolbypassrls` del `current_user` de `DATABASE_URL`; el *healthcheck* solo cubre `APP_DB_USER`.
  - Prueba (CI/T10) que verifique que `docker compose config` del servicio `api` no contiene `MIGRATION_DATABASE_URL`.

---

### T8 — Web: Vite, TypeScript, Tailwind y shadcn/ui

- **Depende de:** T5
- **Archivos:** `web/package.json`, `web/tsconfig.json`, `web/vite.config.ts`, `web/src/main.tsx`, `web/src/App.tsx`, `web/components.json`, `web/src/components/ui/`
- **Criterio:** compila en TypeScript estricto; Tailwind activo; shadcn/ui inicializado con al menos un componente añadido por la CLI; la pantalla muestra el estado de `/health` (cargando, error, éxito) y se ve bien a 375 px y a 1440 px.
- **Verificación:** `cd web && npm run build` + capturas a 375 px y 1440 px
- **Riesgo:** acoplar la pantalla base a un diseño que aún no existe.
- **Implementada (2026-11-12), aprobada por reviewer:** `npm ci`, `npm run build` y `npm run typecheck` en verde; capturas a 375 y 1440 px de cargando, error (API caída), base caída (503) y éxito. CLI fijada en `shadcn@4.23.0` (preset `nova`, base `radix`).
  - Dependencias aprobadas por el humano con **versiones fijadas** (exactas, sin `^` ni `~`, iguales a `package-lock.json`):
    - `dependencies`: `react` 19.3.1, `react-dom` 19.3.1, `tailwindcss` 4.3.5, `@tailwindcss/vite` 4.3.5, `radix-ui` 1.8.1, `class-variance-authority` 0.7.1, `cn` 0.5.2, `tw-animate-css` 1.4.0, `lucide-react` 1.72.0 (añadido por la CLI, sin uso aún).
    - `devDependencies`: `typescript` 7.0.2 (en T9 quedó en **6.0.3** por la decisión D; ver T9), `vite` 8.3.8, `@vitejs/plugin-react` 6.3.0, `@types/node` 24.19.2, `@types/react` 19.3.0, `@types/react-dom` 19.3.0, `shadcn` 4.23.0 (movido a dev: solo aporta `shadcn/tailwind.css` en build y la CLI; build y typecheck siguen en verde).
  - `cn` (usado en `src/lib/utils.ts`) procede del paquete que instala la CLI (repositorio shadcn-ui/cn); **humano a confirmar** el editor del paquete en npm.
  - TanStack Query se difiere a la primera pantalla con datos (decisión humana); `/health` usa `fetch` + `useEffect` en `src/lib/health.ts`.
  - La CLI añade la fuente Geist; se quitó hasta aprobar la fuente de la marca.
  - `npm ci` reporta 6 vulnerabilidades (2 bajas, 4 moderadas) en dependencias transitivas; revisar con `npm audit` antes del piloto.

---

### T9 — Web: calidad

- **Depende de:** T8
- **Archivos:** `web/eslint.config.js`, `web/vitest.config.ts`, `web/src/App.test.tsx`
- **Criterio:** `npm run lint`, `npm run typecheck` y `npm test` pasan; la prueba cubre los tres estados de la pantalla de salud.
- **Verificación:** `cd web && npm run lint && npm run typecheck && npm test`
- **Riesgo:** pruebas que dependen de la red real.
- **Riesgo:** compatibilidad de ESLint (`typescript-eslint`) y Vitest con TypeScript 7.0.2 (fijado en T8; quedó en 6.0.3 por la decisión D); verificar los rangos de `peerDependencies` antes de instalar y, si no hay soporte, decidir con el humano en lugar de bajar TS por cuenta propia.
- **Bloqueada (2026-11-12), pendiente de decisión humana:** `typescript-eslint` (8.72.2 `latest` y 8.72.3-alpha.8 `canary`) exige `typescript >=4.8.4 <6.1.0`. Además, el paquete `typescript` 7.0.2 (compilador nativo) solo exporta `version` y `versionMajorMinor`, sin la API de compilador (`createSourceFile`, `createProgram`) que usa el parser. No es solo el rango: no funciona. Vitest 5.1.0, jsdom, Testing Library y los plugins de React no dependen de TypeScript y son compatibles. No se instaló nada ni se bajó TS. Opciones:
  - A: añadir `@typescript/typescript6` 6.0.2 (Microsoft, binario `tsc6`) para las herramientas, junto a TS 7 para `typecheck`/`build`, y resolver `typescript` hacia él solo para `typescript-eslint` (alias u `overrides` de npm; verificar que funcione).
  - B: cambiar ESLint por un linter que no dependa de TS (`oxlint` 1.93.0, con reglas de react-hooks, o `@biomejs/biome` 2.6.7), con `eslint.config.js` sustituido por su configuración.
  - C: ESLint sin TypeScript (solo `.js`) más el typecheck de TS 7 para `.ts`/`.tsx`. Cubre poco: descartable.
  - D: bajar el proyecto a TS 6.0.3 (lo prohíbe la instrucción actual; requiere decisión humana).
- **Decisión humana (2026-11-12): opción D.** `typescript` fijado en **6.0.3 exacto** para usar `typescript-eslint` estándar. No hizo falta cambiar `tsconfig` por TS 6; solo se añadió `vitest.config.ts` al `include` de `tsconfig.node.json`. Build y typecheck de T8 siguen en verde con TS 6.0.3.
  - **Recordatorio:** volver a TypeScript 7 cuando `typescript-eslint` lo soporte (rango `peerDependencies` que incluya 7 y API de compilador disponible); revisar en cada actualización de `typescript-eslint`.
  - `devDependencies` añadidas, versiones exactas: `eslint` 10.14.0, `@eslint/js` 10.0.1, `typescript-eslint` 8.72.2, `eslint-plugin-react-hooks` 7.1.1, `eslint-plugin-react-refresh` 0.5.7, `globals` 17.14.0, `vitest` 5.1.0, `jsdom` 31.0.0, `@testing-library/react` 16.3.3, `@testing-library/dom` 10.4.2.
  - Scripts: `lint` (`eslint . --max-warnings 0`), `test` (`vitest run`); `typecheck` ya existía. `src/App.test.tsx` cubre cargando, éxito (200), base caída (503) y error de red con `fetch` simulado (sin red real).
  - `npm audit`: 0 en producción; 15 (2 bajas, 13 moderadas) solo en dev, por `minimatch`/`deepmerge` transitivas de ESLint, `typescript-eslint` y `shadcn`. Revisar antes del piloto junto con la deuda de T8.
- **Implementada (2026-11-12), aprobada por reviewer.** `npm ci`, `lint`, `typecheck`, `test` y `build` en verde.
  - Ratificadas por el humano (2026-11-12): `eslint` 10.14.0, `@eslint/js` 10.0.1 y `globals` 17.14.0.
  - Deuda aceptada por el humano: los 15 avisos de `npm audit` en `devDependencies` se revisan antes del piloto (pasa a T10).

---

### T10 — CI, hooks y arranque documentado

- **Depende de:** T2–T9
- **Archivos:** `.github/workflows/*.yml`, `README.md`, `scripts/`
- **Criterio:** el CI crea el rol de la aplicación con el script de init de T3 antes de `pytest` y corre `ruff`, `pytest`, migraciones (con el rol migrador), `lint`, `typecheck`, `test` y `build`; el README explica cómo recrear el volumen si el rol no existe y cómo crear el rol en Supabase; corre `check-attribution.sh` sobre el rango del PR; un clon nuevo instala los hooks con `sh scripts/setup-hooks.sh`; el README explica el arranque en menos de 10 líneas; `MEMORY.md` refleja el estado.
- **Verificación:** PR de prueba con un fallo intencional → CI rojo; corregido → CI verde; commit de prueba con `Co-Authored-By: Claude` → CI rojo.
- **Riesgo:** CI que no corre por la configuración de ramas.
- **Deuda heredada de T3 (2026-11-11):** el script de init usa bashismos: se ejecuta con `bash`, no con `sh`. En CI se crea el rol de la aplicación con ese mismo script antes de `pytest`, y `TEST_DATABASE_URL` nunca puede ser el superusuario del servicio de PostgreSQL.
- **Deuda heredada de T4 (2026-11-11):** el comando de producción es `gunicorn` (workers `gthread` o suficientes), nunca `flask run`; el README documenta rate limit de `/health` en el proxy y acceso/retención acotados de logs. Detalle en `plan.md` §4 "Deuda de operación (heredada de T4)".
- **Deuda heredada de T9 (2026-11-12):** fijar la versión de Node: CI con `actions/setup-node` en 24.x y `engines` en `web/package.json` o `.nvmrc` (jsdom 31 exige `^22.22.2 || ^24.15.0 || >=26`). Revisar `npm audit` (15 avisos solo en dev) antes del piloto.

---

## Resumen

| Tarea | Depende de | Verificación |
|---|---|---|
| T1 | — | estructura + `git check-ignore` |
| T2 | T1 | `uv run pytest test_app_factory test_config` |
| T3 | T2 (adelanta el rol de app de T7) | `docker compose up -d db` + `uv run pytest test_tenant_scope` |
| T4 | T2, T3 | `uv run pytest test_health test_errors` |
| T5 | T2–T4 | `uv run pytest` dos veces |
| T6 | T2 | `uv run alembic upgrade/downgrade/upgrade` |
| T7 | T2, T3, T6 | `docker compose up` + `/health` |
| T8 | T5 | `npm run build` + capturas 375 y 1440 px |
| T9 | T8 | `lint` + `typecheck` + `test` |
| T10 | T2–T9 | CI rojo/verde + hooks instalados |

## Reglas de ejecución

- Una tarea por sesión.
- No se abre T8 antes de cerrar T5: la fundación del backend manda.
- Si una tarea crece más de un día, se divide y se actualiza este archivo con `/sdd-change`.
- T6 no crea tablas de negocio. Si aparece esa necesidad, es otra spec.
- La tabla de prueba de T3 y su política viven solo en las pruebas; no se migran.
- Toda tabla de negocio futura nace con RLS forzada, política y `GRANT` mínimos en su misma migración (patrón de T6).
