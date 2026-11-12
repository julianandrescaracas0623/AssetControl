# Plan 001 — Fundación técnica

> **Cambio 2026-11-11:** aislamiento por RLS + filtro simple (decisión humana tras 3 revisiones de T3). Ver `spec.md` §10.

## 1. Enfoque

Construir primero el backend (configuración, acceso a datos con tenant, salud y errores, pruebas) porque define el patrón de aislamiento; después el entorno Docker y la web base. El CI y los hooks cierran la fundación. Nada de dominio.

El aislamiento entre tenants lo hace cumplir **PostgreSQL con Row Level Security (RLS)**; Python solo aplica el filtro estándar de SQLAlchemy como complemento y como higiene.

## 2. Cambios por capa

### Base de datos

- PostgreSQL 17. Alembic con una revisión inicial vacía y reversible.
- Sin tablas de negocio.
- **Dos roles** (nombres propuestos, `[PROPUESTA]` hasta aprobación):
  - **Migrador / dueño** (`POSTGRES_USER` en local; en Supabase, el rol administrador del proyecto): dueño del esquema y de las tablas; ejecuta Alembic.
  - **Aplicación** (propuesto: `assetcontrol_app`): `LOGIN`, `NOSUPERUSER`, `NOBYPASSRLS`, `NOCREATEROLE`, `NOCREATEDB`, no dueño de las tablas. Solo recibe `USAGE` sobre el esquema y los `GRANT` por tabla que dé cada migración.
- **Patrón de toda tabla de negocio** (plantilla para la spec 002; en esta spec solo se usa en la tabla de prueba de T3):

  ```sql
  ALTER TABLE <tabla> ENABLE ROW LEVEL SECURITY;
  ALTER TABLE <tabla> FORCE ROW LEVEL SECURITY;
  CREATE POLICY tenant_isolation ON <tabla>
    USING      (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
  GRANT SELECT, INSERT, UPDATE ON <tabla> TO <rol_app>;  -- [PROPUESTA] sin DELETE: nada se borra (constitución §6)
  ```

  `NULLIF(..., '')` es necesario: tras terminar una transacción con `SET LOCAL`, la variable queda en `''` dentro de esa conexión, y `''::uuid` fallaría con error en lugar de "no devolver filas". Con `NULLIF`, sin tenant la comparación es `NULL` y la política no devuelve filas ni deja escribir (R4b). Las tablas de solo inserción (p. ej. `verificacion`) reciben solo `SELECT, INSERT`; eso lo decide cada spec.

### Backend

- `backend/app/__init__.py`: `create_app(config)`.
- `backend/app/config.py`: lectura de `DATABASE_URL`, `SECRET_KEY`, `ENVIRONMENT`; error con el nombre de la variable. `DATABASE_URL` es la del rol de la aplicación.
- `backend/app/db.py`: engine y sesión de SQLAlchemy 2, y:
  - **`TenantScoped`**: mixin con la columna `tenant_id` (uuid, NOT NULL) que heredan las entidades de negocio.
  - **`tenant_session(tenant_id)`**: único acceso a datos con tenant. Valida que `tenant_id` sea un UUID (si no, falla antes de tocar la base), abre una transacción y ejecuta `SELECT set_config('app.tenant_id', :tenant_id, true)` con parámetro enlazado (el tercer argumento `true` equivale a `SET LOCAL`; nunca se interpola texto en el SQL). Al salir, `commit` o `rollback` cierra la transacción y la variable desaparece con ella.
  - **Filtro estándar**: `with_loader_criteria(TenantScoped, lambda cls: cls.tenant_id == <tenant>, include_aliases=True)` en el evento `do_orm_execute` de la sesión, y asignación de `tenant_id` a los objetos `TenantScoped` nuevos en `before_flush` (si traen otro tenant, error).
  - **Higiene**: dentro de `tenant_session` se rechaza explícitamente `text()` y `Session.connection()`; no es la barrera, solo evita el SQL crudo por costumbre.
  - **Se elimina** el recorrido del árbol de sentencias (`_check_statement_elements`) y la verificación por `SELECT` en `before_flush` (ver §7).
- `backend/app/meta/routes.py`: `GET /health`.
- `backend/app/errors.py`: manejador de errores con JSON uniforme y `request_id`.
- `backend/tests/conftest.py`: PostgreSQL de pruebas, transacción con rollback por prueba; fixtures con dos conexiones: rol de la aplicación (lo que se prueba) y rol migrador (solo para crear la tabla de prueba y su política).
- `pyproject.toml` con `ruff` y `pytest`; dependencias gestionadas con uv (decidido 2026-11-11). Los comandos se invocan como `uv run pytest` y `uv run ruff check .`; el bloqueo de versiones (archivo de lock) lo genera uv. **Sin dependencias nuevas** por este cambio: RLS es de PostgreSQL y `with_loader_criteria` es de SQLAlchemy.

### Web

- `web/`: Vite + React + TypeScript estricto.
- Tailwind CSS y `npx shadcn@latest init`; un componente (`button`, `card`) añadido con la CLI.
- Pantalla que consulta `/health` con TanStack Query y muestra cargando, error y éxito.
- Vitest para la pantalla; scripts `lint`, `typecheck`, `test`, `build`.

### Entorno y CI

- `docker-compose.yml` (api + postgres), `backend/Dockerfile` (instala dependencias con uv), `.env.example`.
- Las pruebas usan el PostgreSQL local de Docker; producción apuntará al PostgreSQL de Supabase (`DATABASE_URL`), sin Supabase Auth ni su API automática. La versión mayor local coincide con la de Supabase: el contenedor local usa la imagen `postgres:17` (Supabase ejecuta PostgreSQL 17.11, confirmado el 2026-11-11; pendiente resuelto).
- **Roles en local (opción elegida, la más simple):** un script de inicialización de PostgreSQL versionado (ruta propuesta: `docker/postgres/init/01-app-role.sh`) montado en `/docker-entrypoint-initdb.d/` desde `docker-compose.yml`. Usa `psql` con variables de entorno (sin contraseñas en el repo) para crear el rol de la aplicación con los atributos de §2 y darle `CONNECT` y `USAGE`. El migrador es `POSTGRES_USER`, dueño de la base.
  - Se descarta crearlo en una revisión de Alembic: obligaría a dar `CREATEROLE` al migrador en Supabase y a manejar contraseñas dentro de migraciones.
  - El script solo corre con el volumen vacío; con un volumen existente se recrea (`docker compose down -v`) o se ejecuta el mismo script a mano. Se documenta en el README (T10).
  - En CI (T10) el mismo script se ejecuta con `bash` (usa bashismos; con `sh` falla) contra el contenedor de servicio de PostgreSQL antes de `pytest`. `TEST_DATABASE_URL` nunca es el superusuario del servicio.
- **Roles en Supabase:** el operador crea el rol de la aplicación una vez, con el mismo SQL, desde el rol administrador; Alembic corre con el rol administrador. Fuera de esta spec (no hay despliegue), pero se deja escrito en el README.
- **Deuda heredada de T3 (2026-11-11) — tarea humana antes del piloto (Supabase):**
  - Crear el rol de la aplicación `NOSUPERUSER NOBYPASSRLS`, sin membresías en `postgres`, `service_role` ni `authenticated`, y que no sea dueño de las tablas.
  - Verificar sus atributos como en A4a (`pg_roles`: `rolsuper` y `rolbypassrls` falsos).
  - Revisar los `ALTER DEFAULT PRIVILEGES` de Supabase hacia `anon`/`authenticated` y confirmar que la API automática de Supabase no accede al esquema `public`.
- **Variables nuevas para `.env.example`** (sin valores; nombres `[PROPUESTA]`):
  - `MIGRATION_DATABASE_URL` — URL del rol migrador; la lee solo Alembic (`migrations/env.py`). No es obligatoria para la API.
  - `APP_DB_USER`, `APP_DB_PASSWORD` — los usa el script de init para crear el rol de la aplicación.
  - `TEST_MIGRATION_DATABASE_URL` — URL del rol migrador sobre la base de pruebas (crear la tabla de prueba y su política). `TEST_DATABASE_URL` (ya en uso) pasa a ser la del rol de la aplicación.
  - Se mantienen `DATABASE_URL` (rol de la aplicación), `SECRET_KEY`, `ENVIRONMENT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`.
  - El enmascarado de contraseñas de `conftest.py` debe cubrir también las URL nuevas.
- OpenAPI y tipos generados: spec 002, fuera de esta.
- Workflows de `.github/` ya escritos; se ajustan los comandos si cambia algo.

## 3. Orden de implementación

T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8 → T9 → T10. La web (T8, T9) no empieza antes de cerrar T5.

T3 adelanta de T7 el script de init del rol de la aplicación y su montaje en `docker-compose.yml` (sin él no hay rol con el que probar RLS). T7 lo consume y completa el resto del entorno.

## 4. Riesgos técnicos

| Riesgo | Mitigación |
|---|---|
| Inicializar el engine al importar rompe las pruebas | Crear el engine dentro de `create_app` |
| `tenant_session` fácil de saltarse | RLS en la base: aunque el código use `get_bind`, el engine o SQL crudo, la conexión del rol de la aplicación no ve otro tenant. Prueba con dos tenants por cada vía |
| Rol de la aplicación con `BYPASSRLS`, superusuario o dueño sin `FORCE` anula RLS en silencio | Prueba que consulta `pg_roles` (`rolsuper`, `rolbypassrls` = falso) y `pg_class` (`relrowsecurity`, `relforcerowsecurity` = verdadero) y falla si no se cumple; corre en local y en CI |
| `current_setting('app.tenant_id', true)` sin tenant: devuelve `NULL` o `''` según la historia de la conexión | Política con `NULLIF(..., '')::uuid`; prueba "sin tenant no hay filas ni escritura" en una conexión que ya usó otro tenant |
| Pool de conexiones y variable de tenant que sobrevive a una petición | Solo `set_config(..., true)` (equivale a `SET LOCAL`) dentro de la transacción abierta por `tenant_session`; nunca `SET` de sesión. Prueba: misma conexión del pool, siguiente transacción sin tenant → cero filas. Compatible con el *pooler* de Supabase en modo transacción |
| `SET LOCAL` dentro de la transacción externa de las pruebas (rollback por prueba) persiste más allá de un *savepoint* | Las pruebas de aislamiento que dependen de "sin tenant" usan su propia transacción o verifican la limpieza; se documenta en `conftest.py` |
| `tenant_id` no UUID interpolado en SQL | Validación como `uuid.UUID` antes de abrir la transacción y parámetro enlazado en `set_config` |
| Script de init que no corre con un volumen existente | README: `docker compose down -v` o ejecutar el script a mano; CI siempre parte de cero |
| Pruebas lentas con Postgres | Contenedor reutilizable y rollback por transacción |
| shadcn/ui cambia el scaffolding | Fijar versión de la CLI y documentar el comando |

### Deuda de operación (heredada de T4, 2026-11-11)

Decisión humana: `connect_timeout` fijo de 5 s (`CONNECT_TIMEOUT_SECONDS` en `app/db.py`), global al engine y no configurable; se hará configurable solo si Supabase en producción lo exige.

1. **`/health` anónimo y DoS:** rate limit en el proxy; separar liveness (sin base) de readiness (con base); cachear el ping 2-5 s; engine/pool propio y pequeño con `pool_timeout` corto; `statement_timeout` en `connect_args`; workers `gthread` o suficientes.
2. **Logs:** el log con `exc_info` puede arrastrar el `DETAIL` de PostgreSQL con valores de fila (seriales, correos, teléfonos) y host/ruta. Acotar acceso y retención de logs; en la spec 002+ redactar `DBAPIError` registrando tipo y `orig.sqlstate` en lugar de `str(orig)`; logging JSON estructurado.
3. **Debug:** en `create_app`, si `environment == "production"`, forzar `DEBUG=False` y `PROPAGATE_EXCEPTIONS=False`, con prueba. Comando de producción: `gunicorn`, nunca `flask run`.
4. **Menores:**
   - `ping_database` solo captura `SQLAlchemyError` (una excepción ajena daría 500 en vez de 503) y el 503 no deja log.
   - El handler de 5xx HTTP (`abort(502)`) no registra con `request_id`.
   - Conservar `Allow`/`WWW-Authenticate` en 405/401 al llegar auth (T6+).
   - Valorar `Cache-Control: no-store`.
   - Prueba con `caplog`, engine real y host inexistente, que verifique que el log no contiene contraseña ni URL.

### Deuda para specs siguientes (heredada de T3, 2026-11-11)

Para la spec 002 (primeras tablas de negocio, auth y roles):

- **FK compuestas:** `(tenant_id, x_id) → padre(tenant_id, id)`, con `UNIQUE (tenant_id, id)` en el padre.
- **UNIQUE naturales con tenant:** toda `UNIQUE` natural incluye `tenant_id`. Las FK/PK/UNIQUE globales sirven de oráculo de existencia entre tenants, y la integridad referencial ignora RLS.
- **Vistas:** con `security_invoker = true`; `SECURITY DEFINER` prohibido sin revisión.
- **Prueba de catálogo:** toda tabla de `public` fuera de una lista explícita de excepciones tiene `tenant_id`, RLS forzada, política `tenant_isolation` y no tiene `GRANT DELETE` (incluidas las tablas de asociación).
- **`verificacion`:** solo `SELECT, INSERT` para el rol de la aplicación.
- **`insert()` masivo del ORM:** no recibe `tenant_id` de `before_flush` (falla por `NOT NULL`; `WITH CHECK` lo cubre). Hay que pasarlo explícito.
- **Login con RLS:** decidir el mecanismo para buscar el usuario antes de conocer el tenant (política por usuario, función `SECURITY DEFINER` acotada o usuario sin tenant). `[PENDIENTE]` para la spec 002.

## 5. Estrategia de pruebas

- Backend: `uv run pytest` contra PostgreSQL (app factory, config, tenant con dos tenants, salud, errores).
- Aislamiento (`test_tenant_scope.py`), siempre conectado con el **rol de la aplicación**:
  - Con tenant A, el ORM solo ve filas de A; un `INSERT` con `tenant_id` de B es rechazado por `WITH CHECK`.
  - Sin tenant fijado: cero filas y escritura rechazada.
  - RLS bloquea a B también por las vías que el filtro de Python no cubre: `session.get_bind()`, el engine directo, `text()` por una conexión cruda del rol de la aplicación, API *bulk* heredada (`query().update()`/`delete()`) y `join()` explícito.
  - Atributos del rol y de la tabla (`pg_roles`, `pg_class`), como en §4.
  - La tabla de prueba y su política se crean con el rol migrador solo dentro de las pruebas; no entran en Alembic.
- Web: Vitest para la pantalla de salud; verificación manual a 375 px y 1440 px con capturas.
- La prueba de aislamiento es la plantilla de las pruebas por endpoint de las specs 002+.

## 6. Migraciones y reversa

Revisión inicial vacía. Reversa: `uv run alembic downgrade base`. CI ejecuta `upgrade → downgrade → upgrade`. Alembic se conecta con `MIGRATION_DATABASE_URL` (rol migrador), no con `DATABASE_URL`.

Desde la spec 002, cada revisión que cree una tabla de negocio incluye en el mismo `upgrade`: `ENABLE` + `FORCE ROW LEVEL SECURITY`, la política `tenant_isolation` y los `GRANT` al rol de la aplicación (§2); el `downgrade` los quita en orden inverso.

## 7. Alternativa descartada

- Crear ya las tablas `tenant`, `usuario` y `membresia`. Se descarta: pertenecen a la spec 002 (auth y roles) y adelantarlas acopla la fundación al dominio.
- **Barrera de aislamiento en Python que recorre el árbol de cada sentencia SQLAlchemy** (`_check_statement_elements`) más verificación por `SELECT` en `before_flush`. Se descarta (decisión humana, 2026-11-11): en 3 rondas de revisión siguieron apareciendo fugas (API *bulk* heredada, `join()` explícito, `aliased` sobre subconsulta Core, relaciones); depende de internos privados de SQLAlchemy 2.1; bloquea *joins* legítimos que necesitan las specs 002+; y `session.get_bind()` y el engine no se pueden cerrar desde Python. Una lista negra en Python no converge: el tenant lo hace cumplir la base con RLS.
