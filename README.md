# Inventario de Activos

Sistema para llevar el inventario de activos (equipos y mobiliario) de una clínica odontológica, con conteos periódicos, historial y valor total para informes.

Primer cliente: Biotecnologia Dental (Cartago, Colombia). El diseño es multi-tenant desde el inicio.

## Estado

Fase: definición de arquitectura y alcance del MVP. Fundación técnica en curso (spec 001).

## Estructura

- `backend/` — API Flask.
- `web/` — cliente React responsive.

## Documentos

| Documento | Contenido |
|---|---|
| [docs/00-contexto-handoff.md](docs/00-contexto-handoff.md) | Contexto original y decisiones iniciales |
| [docs/01-alcance-mvp.md](docs/01-alcance-mvp.md) | Qué entra y qué no entra en el MVP |
| [docs/02-arquitectura.md](docs/02-arquitectura.md) | Componentes, flujos y despliegue |
| [docs/03-modelo-datos.md](docs/03-modelo-datos.md) | Entidades, relaciones e historial |
| [docs/04-metodologia.md](docs/04-metodologia.md) | Estructura del repo, ramas, ADR, definición de terminado, fases |
| [docs/05-preguntas-abiertas.md](docs/05-preguntas-abiertas.md) | Decisiones pendientes |
| [docs/06-importacion-excel.md](docs/06-importacion-excel.md) | Análisis del Excel actual y plan de importación |
| [docs/adr/](docs/adr/) | Decisiones de arquitectura registradas |
| [Orquestacion/](Orquestacion/README.md) | Método de trabajo: roles, agentes, compuertas, plan y arneses de Claude Code y Cursor |
| [specs/](specs/001-fundacion-tecnica/spec.md) | Specs SDD de cada entrega (la primera: fundación técnica) |

## Stack

- **Web:** React + TypeScript + Vite, Tailwind CSS y shadcn/ui, TanStack Query. Un solo cliente web responsive: conteo móvil primero y administración en celular y computador.
- **Backend:** Python con Flask, PostgreSQL, SQLAlchemy y Alembic.
- **Fotos:** almacenamiento de objetos compatible con S3.
- **CI/CD:** GitHub Actions.
- **Pruebas:** pytest en el backend; Vitest y Playwright en la web.

La justificación está en [ADR-001](docs/adr/ADR-001-stack.md) y [ADR-002](docs/adr/ADR-002-solo-online-cliente-web.md).

## Arranque rápido

Requisitos: Git, Docker y Node 24 (`^24.15.0`, fijado en `web/package.json`). Desde la raíz, en bash o Git Bash:

```sh
sh scripts/setup-hooks.sh                      # hooks de Git (una vez por clon)
cp .env.example .env                           # completa los valores (alfanuméricos)
docker compose up --build -d                   # PostgreSQL 17 + API en http://localhost:5000
curl http://localhost:5000/health              # 200 con "db": "ok"
cd web && npm ci && npm run dev                # web en http://localhost:5173
```

## Entorno local con Docker

1. Copia `.env.example` a `.env` y completa los valores (`.env` está ignorado por git).
2. `docker compose up --build` levanta PostgreSQL 17 (`db`, solo en `127.0.0.1:5432`) y la API con recarga (`api`, en `http://localhost:5000`).
3. Comprueba la API con `curl http://localhost:5000/health` (`200`, `"db": "ok"`).

Dentro de los contenedores la API se conecta a la base por el host `db`, no `localhost`, y con el rol de la aplicación (`APP_DB_USER`), nunca con el superusuario.

- **`APP_DB_USER` debe ser distinto de `POSTGRES_USER`.** `POSTGRES_USER` es el rol migrador (dueño del esquema, ejecuta Alembic); `APP_DB_USER` es el rol de la aplicación, sin `SUPERUSER` ni `BYPASSRLS`, y el script de init falla si son el mismo.
- **El rol de la aplicación solo se crea con el volumen vacío.** El script `docker/postgres/init/01-app-role.sh` corre únicamente la primera vez que se inicializa el volumen `pgdata`. Si el volumen ya existía sin ese rol (o cambiaste `APP_DB_USER`), el servicio `db` no queda sano y la API no arranca. Recrea el volumen con `docker compose down -v` (borra los datos locales de la base) y vuelve a levantar; o ejecuta el mismo script a mano dentro del contenedor `db`.
- Si una contraseña lleva caracteres especiales (`@ : / ? # %`), codifícala en las URL de `.env`.
- **Usa contraseñas alfanuméricas en `.env` (solo desarrollo local).** Los comandos de migración y de pruebas cargan `.env` en el shell con `. ./.env`: caracteres como `& ; $ ( ) # \` o espacios lo rompen o se interpretan. Además, los valores quedan en los argumentos del proceso `docker compose` del host, visibles para otros usuarios de la máquina mientras corre.

### Migraciones dentro de Docker

El contenedor `api` solo recibe la URL del rol de la aplicación; la del rol migrador (`MIGRATION_DATABASE_URL`) no queda en su entorno. Para aplicar las migraciones, pásala solo a un contenedor efímero, desde la raíz del repositorio (bash/Git Bash) y sin escribir ni imprimir los valores:

```sh
set -a; . ./.env; set +a
docker compose run --rm \
  -e MIGRATION_DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}" \
  api uv run alembic upgrade head
```

### Crear un tenant y su primer admin (operador, spec 002)

`flask create-tenant <nombre> <email>` crea el tenant y la invitación `admin` de su primer usuario (vence en 24 h) llamando a `acceso.crear_tenant` con el rol migrador. Lo ejecuta el operador, nunca la API:

- Las credenciales del migrador llegan **solo** por la variable de entorno `MIGRATION_DATABASE_URL`; el comando no acepta URL, contraseña ni rol por argumentos y falla si esa URL usa el mismo rol que `DATABASE_URL`. El servicio `api` no la recibe, así que `docker compose exec api flask create-tenant ...` falla: se usa un contenedor efímero.
- En el ejemplo, `-e MIGRATION_DATABASE_URL` va **sin valor**: Docker la toma del shell, y la URL no queda en los argumentos del proceso `docker compose` (a diferencia del ejemplo de migraciones).
- El enlace `/invitacion#<token>` se muestra **una sola vez** por la salida estándar y no se guarda: la base solo guarda `sha256(sha256(token))`. Sale **relativo**: antepón `https://<dominio-de-la-web>` (nunca `http` en producción) y compártelo solo con esa persona. Si se pierde, se crea otra invitación.
- No redirijas la salida estándar a un archivo ni a logs de CI, ni la pegues en tickets: el token vale 24 h. Usa `docker compose run -T` solo si capturas la salida de forma segura.
- Solo crea el rol `admin`; nombre y email no son secretos (el email se guarda en minúsculas).
- La contraseña va **codificada** dentro de la URL (caracteres como `@` o `/` se escriben `%40`, `%2F`).

Desde la raíz del repositorio (bash/Git Bash), dentro de un subshell `( ... )` para que los secretos de `.env` no queden en tu shell:

```sh
(
  set -a; . ./.env; set +a
  export MIGRATION_DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}"
  docker compose run --rm -e MIGRATION_DATABASE_URL \
    api uv run flask --app app create-tenant "Clínica de ejemplo" admin@ejemplo.test
  unset MIGRATION_DATABASE_URL
)
```

En producción no escribas la URL literal en un `export` (queda en el historial del shell); léela sin eco:

```sh
read -rs MIGRATION_DATABASE_URL; export MIGRATION_DATABASE_URL
```

En producción el migrador no es superusuario ni tiene `BYPASSRLS` (Q5); la migración `0004` le concede `EXECUTE` sobre `acceso.crear_tenant`, que es lo único que necesita.

### Pruebas dentro del contenedor `api`

Las pruebas usan una base aparte, `assetcontrol_test`, en el mismo servidor `db`. Si no existe, créala con el rol migrador (las credenciales salen del entorno del contenedor):

```sh
docker compose exec db sh -c 'createdb -U "$POSTGRES_USER" assetcontrol_test'
```

Con los servicios levantados, desde la raíz del repositorio (bash/Git Bash). Las variables se leen de `.env`; no escribas los valores en el comando ni los imprimas:

```sh
set -a; . ./.env; set +a
docker compose exec \
  -e TEST_DATABASE_URL="postgresql+psycopg://${APP_DB_USER}:${APP_DB_PASSWORD}@db:5432/assetcontrol_test" \
  -e TEST_MIGRATION_DATABASE_URL="postgresql+psycopg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/assetcontrol_test" \
  api uv run pytest
```

`TEST_DATABASE_URL` usa el rol de la aplicación y `TEST_MIGRATION_DATABASE_URL` el rol migrador (necesita `CREATEDB` para la prueba de migraciones).

### Si el rol de la aplicación no existe

Síntoma: `db` no queda sano (`docker compose ps`) y la API no arranca. Pasa cuando el volumen `pgdata` se creó antes del script de init o cambiaste `APP_DB_USER`. Dos salidas:

```sh
docker compose down -v && docker compose up --build -d                      # borra SOLO los datos locales de desarrollo
docker compose exec db bash /docker-entrypoint-initdb.d/01-app-role.sh      # o: crea el rol sin borrar el volumen
```

El script usa bashismos: ejecútalo siempre con `bash`, nunca con `sh`. Es idempotente.

### Reparar un volumen existente (rol `auth_owner`, spec 002)

Un volumen `pgdata` creado antes de la spec 002 no tiene el rol `auth_owner`, y uno manipulado puede tenerlo con `LOGIN`, contraseña, membresías o `CREATE`. No hace falta `down -v` (que borra los datos locales): con `db` en marcha, vuelve a ejecutar el script de init, que crea o reafirma `auth_owner`, revoca todas sus membresías y su `CREATE` en `public` y en las bases, y falla si queda alguna membresía:

```sh
docker compose exec db bash /docker-entrypoint-initdb.d/01-app-role.sh
```

Debe terminar con `01-app-role.sh: roles de la aplicación y auth_owner, y base assetcontrol_test listos.` y código de salida 0; los datos existentes se conservan. En Git Bash (Windows) antepón `MSYS_NO_PATHCONV=1`: sin eso, Git Bash convierte la ruta del contenedor en `C:/Program Files/Git/docker-entrypoint-initdb.d/...` y falla con `No such file or directory`. En PowerShell el comando funciona tal cual.

## CI (GitHub Actions)

Los workflows de `.github/workflows/` corren en cada PR hacia `main`, `develop` y las ramas encadenadas `feat/**` y `docs/**`, y en cada push a `main` y `develop`:

- **Backend:** `ruff`, rol de la aplicación creado con `bash docker/postgres/init/01-app-role.sh`, comprobación de que `TEST_DATABASE_URL` no es superusuario ni tiene `BYPASSRLS`, migraciones con el rol migrador (subir, bajar, subir) y `pytest` sobre PostgreSQL 17.
- **Web (Node 24.x):** `npm ci`, `lint`, `typecheck`, `test` y `build`.
- **Repositorio:** enlaces de la documentación, índice de ADR, ausencia de datos de la clínica y del arnés local, `scripts/check-attribution.sh` sobre los commits del PR y que el servicio `api` del compose no reciba la URL del rol migrador.

Las credenciales del CI son valores efímeros de un PostgreSQL desechable; no hay secretos reales en los workflows.

## Producción (antes del piloto)

No hay despliegue en esta fase; esto queda escrito para cuando lo haya.

### Rol de la aplicación en Supabase

Supabase solo aporta el PostgreSQL administrado. El operador crea el rol de la aplicación **una vez**, con el rol administrador del proyecto (que también ejecuta Alembic), desde `psql`. La contraseña se escribe en el aviso de `\password`, no en el SQL ni en el historial:

```sql
CREATE ROLE assetcontrol_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
\password assetcontrol_app
GRANT CONNECT ON DATABASE postgres TO assetcontrol_app;
GRANT USAGE ON SCHEMA public TO assetcontrol_app;
-- Debe devolver f | f y ninguna membresía:
SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'assetcontrol_app';
SELECT roleid::regrole FROM pg_auth_members WHERE member = 'assetcontrol_app'::regrole;
```

- El rol no puede ser miembro de `postgres`, `service_role`, `authenticated` ni `anon`, ni dueño de las tablas (con dueño o `BYPASSRLS`, RLS no se aplica).
- Aquí solo se dan `CONNECT` y `USAGE`: los permisos por tabla del rol de la aplicación (`SELECT, INSERT, UPDATE`, nunca `DELETE`) los da cada migración de Alembic junto con su RLS ([backend/migrations/README.md](backend/migrations/README.md)), no el operador a mano.
- `DATABASE_URL` de la API usa este rol; `MIGRATION_DATABASE_URL` (solo Alembic) usa el administrador. Los valores viven en el gestor de secretos del alojamiento, nunca en el repositorio.

### Cerrar la API automática de Supabase

Flask es el único backend: los roles `anon` y `authenticated` de Supabase no deben poder leer ni escribir el esquema `public`. Con el rol administrador, una vez y de nuevo tras cada migración que cree tablas:

```sql
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM anon, authenticated;
-- Debe devolver 0 filas:
SELECT grantee, table_name, privilege_type
FROM information_schema.role_table_grants
WHERE table_schema = 'public' AND grantee IN ('anon', 'authenticated');
```

Además, desactiva la Data API en el panel del proyecto (*Project Settings → Data API*) o, como mínimo, quita `public` de los esquemas expuestos.

### Servidor de la API

- El comando de producción es **`gunicorn`**, nunca `flask run` (el `CMD` de `backend/Dockerfile` es solo para desarrollo). Escucha solo en local, detrás del proxy inverso, con workers `gthread` o suficientes para que un `/health` lento no bloquee la API, por ejemplo: `gunicorn --worker-class gthread --workers 2 --threads 4 --bind 127.0.0.1:5000 "app:create_app()"`. Si el proxy corre en otra máquina o contenedor, fija `--forwarded-allow-ips` con su IP exacta (nunca `*`) para que las cabeceras `X-Forwarded-*` solo se acepten de él. `gunicorn` aún no es dependencia del proyecto: se añade, con aprobación, en la spec de despliegue.
- `ENVIRONMENT=production`, sin `FLASK_DEBUG` ni `--reload`; el compose de este repositorio es solo para desarrollo.
- **`/health` es anónimo y hace ping a la base:** limita su tasa en el proxy inverso (p. ej. unas pocas peticiones por segundo por IP) para que no sirva para saturar la base.
- **Logs:** pueden arrastrar detalles de PostgreSQL (valores de fila, host). Restringe el acceso a quien opera el servicio y fija una retención acotada (p. ej. 14–30 días) en el alojamiento; nunca los copies a canales abiertos.
- **Qué no se registra nunca:** la cabecera `Authorization`, cookies, tokens de invitación, URLs de conexión (`DATABASE_URL`, `MIGRATION_DATABASE_URL`), correos, teléfonos ni seriales de activos de la clínica. Sin `echo=True` en SQLAlchemy y con `log_statement = none` en PostgreSQL.

## Trabajo con asistentes de IA

El método está en [Orquestacion/](Orquestacion/README.md). La configuración de Claude Code y Cursor (`.claude/`, `.cursor/`, `AGENTS.md`, `CLAUDE.md`, `MEMORY.md`) es **local** y no se publica ([ADR-004](docs/adr/ADR-004-arnes-local-y-autoria-humana.md)). Tras clonar, instala los hooks de Git:

```sh
sh scripts/setup-hooks.sh
```
