# 10 — Entorno local, paso a paso

> **Spec 010c.** Para dejar AssetControl funcionando en tu PC con Windows desde cero, conectarte a la base y correr las pruebas. Cada paso dice qué escribir y qué deberías ver. Si algo no sale igual, mira la sección 13.
>
> Todos los comandos son de **PowerShell**. Donde dice `<algo>`, reemplázalo completo (sin los `< >`).

## 0. Lo que vas a tener al final

- La base PostgreSQL en Docker, con dos usuarios: el **migrador** (dueño, crea tablas) y el de **la app** (solo lo que la app necesita).
- La API en `http://localhost:5000` y la web en `http://localhost:5173`.
- Un cliente gráfico (TablePlus o pgAdmin) conectado a la base.
- Las pruebas del backend, de la web y las de navegador (Playwright) en verde.

## 1. Programas que necesitas (una sola vez)

| Programa | Para qué | Cómo saber si ya lo tienes |
|---|---|---|
| Git | El código | `git --version` |
| Docker Desktop | La base de datos | Abre Docker Desktop: abajo a la izquierda dice *Engine running* |
| uv | Python y las dependencias del backend | `uv --version` |
| Node.js 24 | La web | `node --version` → `v24.x` |
| VS Code | Editar | Extensiones: **Python**, **Pylance**, **ESLint** |
| TablePlus o pgAdmin | Ver la base | Ya los tienes |

## 2. El archivo `.env` (las conexiones)

`.env` está en la raíz del proyecto (`C:\Users\VICTUS16\Proyectos\AssetControl\.env`). **Nunca se sube a GitHub** (el repo es público). Ábrelo con VS Code.

| Variable | Qué es | Valor en tu PC |
|---|---|---|
| `POSTGRES_USER` | Usuario **migrador** (dueño de la base) | p. ej. `assetcontrol_admin` |
| `POSTGRES_PASSWORD` | Su contraseña | una larga, sin espacios |
| `POSTGRES_DB` | Nombre de la base | `assetcontrol` |
| `APP_DB_USER` | Usuario **de la app** | `assetcontrol_app` (distinto del migrador) |
| `APP_DB_PASSWORD` | Su contraseña | otra larga, sin espacios |
| `DATABASE_URL` | Cómo entra la app | `postgresql+psycopg://<APP_DB_USER>:<APP_DB_PASSWORD>@127.0.0.1:5432/<POSTGRES_DB>` |
| `MIGRATION_DATABASE_URL` | Cómo entra el migrador | `postgresql+psycopg://<POSTGRES_USER>:<POSTGRES_PASSWORD>@127.0.0.1:5432/<POSTGRES_DB>` |
| `TEST_DATABASE_URL` | La app, en la base de pruebas | igual que `DATABASE_URL` pero terminando en `/assetcontrol_test` |
| `TEST_MIGRATION_DATABASE_URL` | El migrador, en la base de pruebas | igual que `MIGRATION_DATABASE_URL` pero terminando en `/assetcontrol_test` |
| `SECRET_KEY` | Firma las sesiones | 48 caracteres o más al azar |
| `ENVIRONMENT` | Modo | `development` |
| `TRUSTED_PROXY_HOPS` | Proxies delante | `0` en tu PC |
| `RATE_LIMIT_*`, `ARGON2_MAX_CONCURRENCY` | Opcionales | vacías |

Reglas que evitan el 90 % de los errores:

1. Usa `127.0.0.1`, no `localhost` (en Windows, `localhost` intenta primero IPv6 y tarda ~10 s).
2. Si una contraseña tiene `@ : / ? # %`, dentro de las URL va codificada (`@` → `%40`, `#` → `%23`). Más fácil: genera contraseñas sin esos símbolos:
   ```powershell
   cd C:\Users\VICTUS16\Proyectos\AssetControl\backend
   uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
3. Las contraseñas de `POSTGRES_PASSWORD` y `APP_DB_PASSWORD` se graban en la base **la primera vez** que Docker la crea. Si las cambias después en `.env`, la base no se entera (sección 13, «contraseña incorrecta»).

> Tu `.env` ya quedó revisado (2026-11-15): las cuatro URL coinciden con los usuarios y contraseñas, usan `127.0.0.1` y tienen las opcionales. Hay una copia de antes en `.env.respaldo-2026-11-15`.

## 3. Encender la base

```powershell
cd C:\Users\VICTUS16\Proyectos\AssetControl
docker compose up -d db
docker compose ps
```

Deberías ver `assetcontrol-db-1 ... healthy`. Si dice `starting`, espera 10 s y repite `docker compose ps`.

## 4. Instalar las dependencias

```powershell
cd C:\Users\VICTUS16\Proyectos\AssetControl\backend
uv sync
cd ..\web
npm ci
```

## 5. Migrar la base (crear o actualizar tablas)

```powershell
cd C:\Users\VICTUS16\Proyectos\AssetControl\backend
uv run --env-file ../.env alembic upgrade head
uv run --env-file ../.env alembic current
```

La última línea debe terminar en `0012_funciones_sin_supabase (head)`.

> **Siempre** `--env-file ../.env`: `uv run` no lee el `.env` solo. Sin eso sale «Faltan variables de entorno obligatorias».

## 6. Revisar que todas las conexiones estén bien

```powershell
uv run --env-file ../.env flask --app app revisar-conexiones
```

Debe salir así (los nombres pueden variar):

```text
Migraciones del repo: 0012_funciones_sin_supabase
  OK  DATABASE_URL: bien (rol assetcontrol_app, base assetcontrol, TLS no, migración (la lee el migrador))
  OK  MIGRATION_DATABASE_URL: bien (rol assetcontrol_admin, base assetcontrol, TLS no, migración 0012_funciones_sin_supabase)
  OK  TEST_DATABASE_URL: bien (...)
  OK  TEST_MIGRATION_DATABASE_URL: bien (...)
  ·  SUPABASE_DATABASE_URL: no configurada
```

Cada `MAL` dice el motivo en español (contraseña, base apagada, migraciones atrasadas…). El comando **nunca** muestra contraseñas ni direcciones.

## 7. Crear tu clínica de prueba (una vez)

```powershell
uv run --env-file ../.env flask --app app create-tenant "Clínica de prueba" "tu-correo@ejemplo.com"
```

Copia la línea que empieza por `/invitacion#…`. La usarás en el paso 8 (vence en 24 h; si vence, repite este paso).

## 8. Encender la app

```powershell
cd C:\Users\VICTUS16\Proyectos\AssetControl
docker compose up -d --build api
cd web
npm run dev
```

Abre `http://localhost:5173/invitacion#<lo que copiaste>` → crea tu cuenta → llegas al **Resumen**. Para dejar de usarla: `Ctrl + C` en la ventana de `npm run dev` y `docker compose stop`.

> **Probar la cámara en el teléfono:** la cámara solo funciona con HTTPS. En vez de `npm run dev`, usa `$env:VITE_HTTPS = "1"; npm run dev`, abre en el teléfono (misma red Wi-Fi) la dirección `https://<IP de tu PC>:5173` que muestra Vite y acepta el aviso del certificado de desarrollo.

## 9. Conectarte a la base con un cliente gráfico

### TablePlus

1. *Create a new connection* → **PostgreSQL**.
2. Rellena:
   - **Name:** `AssetControl local`
   - **Host:** `127.0.0.1` · **Port:** `5432`
   - **User:** el valor de `POSTGRES_USER` · **Password:** el de `POSTGRES_PASSWORD`
   - **Database:** el de `POSTGRES_DB`
   - **SSL mode:** *Disable* (solo en local)
3. *Test* → *Connect*.

### pgAdmin

*Register → Server*: pestaña **General** → Name `AssetControl local`; pestaña **Connection** → Host `127.0.0.1`, Port `5432`, Maintenance database = `POSTGRES_DB`, Username = `POSTGRES_USER`, Password = `POSTGRES_PASSWORD` → *Save*.

### Qué vas a ver

- Con el **migrador** (`POSTGRES_USER`) ves todas las tablas y todas las filas: en tu PC es superusuario. **Úsalo para mirar, no para editar**: un `UPDATE` o `DELETE` a mano se salta las reglas de la app (por ejemplo, los informes congelados).
- Con el **usuario de la app** (`APP_DB_USER`) verás las tablas **vacías**. Es lo correcto: el RLS solo deja ver las filas de una clínica cuando la app fija cuál es. Esa es la protección entre clínicas.
- Tablas principales: `tenant` (clínicas), `usuario`, `membresia`, `ubicacion`, `categoria`, `activo`, `activo_evento` (historial), `sesion_conteo`, `verificacion`, `sesion_desglose` y `sesion_no_encontrado` (informes congelados).

## 10. VS Code sin `import` en rojo

1. Abre la **carpeta raíz** del proyecto (`AssetControl`), no `backend` ni `web` por separado.
2. `Ctrl + Shift + P` → **Python: Select Interpreter** → elige `backend\.venv\Scripts\python.exe`.
3. Abre cualquier `.tsx` → `Ctrl + Shift + P` → **TypeScript: Select TypeScript Version** → **Use Workspace Version**.
4. `Ctrl + Shift + P` → **Developer: Reload Window**.

Ya están `pyrightconfig.json` (en el repo) y `.vscode/settings.json` (solo en tu PC) con esa configuración. Si un `import` sigue en rojo, corre `uv sync` y `npm ci` (sección 4) y recarga.

## 11. Pruebas

```powershell
# Backend (usa la base de pruebas; crea y borra bases temporales)
cd C:\Users\VICTUS16\Proyectos\AssetControl\backend
uv run --env-file ../.env pytest -q
uv run ruff check .

# Web
cd ..\web
npm test
npm run lint
npm run typecheck
```

## 12. Pruebas en el navegador (Playwright)

La primera vez, instala el navegador de pruebas:

```powershell
cd C:\Users\VICTUS16\Proyectos\AssetControl\web
npx playwright install chromium
```

Con la base encendida (sección 3):

| Comando | Qué hace |
|---|---|
| `npm run e2e` | Corre todo sin ventana (~15 s) |
| `npm run e2e:ver` | Igual, pero ves el navegador moverse |
| `npm run e2e:ui` | Modo interactivo: eliges la prueba y la ves paso a paso, con la línea de tiempo |
| `npm run e2e:informe` | Abre el informe de la última corrida (con capturas y video si algo falló) |

Las pruebas crean y usan su **propia base** (`assetcontrol_e2e`), su propia API (puerto 5011) y su propia web (puerto 5174): **no tocan** tus datos de desarrollo. Necesitan libres esos dos puertos.

## 13. Supabase

### 13.1 Crear el proyecto y obtener las conexiones

1. Entra a [supabase.com](https://supabase.com) → *New project* → nombre `assetcontrol` → región del este de EE. UU. → guarda la **contraseña de la base** en tu gestor de contraseñas.
2. En el proyecto: botón **Connect** → **Session pooler** (no *Direct* ni *Transaction*). Copia la cadena; se parece a `postgresql://postgres.<ref>:[YOUR-PASSWORD]@aws-0-us-east-1.pooler.supabase.com:5432/postgres`.
3. Conviértela al formato de AssetControl: cambia `postgresql://` por `postgresql+psycopg://`, pon tu contraseña y agrega `?sslmode=require` al final.
4. En `.env`, quita el `#` de las dos líneas `SUPABASE_…` y pon:
   - `SUPABASE_MIGRATION_DATABASE_URL` = la cadena con el usuario `postgres.<ref>`.
   - `SUPABASE_DATABASE_URL` = la misma con el usuario `assetcontrol_app.<ref>` y la contraseña de la app de producción (existe después de `preparar-roles`, `docs/09-despliegue.md` §4).
5. Comprueba: `uv run --env-file ../.env flask --app app revisar-conexiones` → las líneas `SUPABASE_…` deben decir `OK` y `TLS sí`.

> Las variables `SUPABASE_…` solo las usa `revisar-conexiones`. La app local **siempre** usa `DATABASE_URL` (tu Docker): así nunca escribes en producción por error.

### 13.2 Ver Supabase en TablePlus

Igual que la sección 9, con: Host = el del pooler (`aws-0-…pooler.supabase.com`), Port `5432`, User `postgres.<ref>`, Password = la de Supabase, Database `postgres`, **SSL mode: Require**. Ponle un color rojo a la conexión en TablePlus: es **producción**.

### 13.3 Conectar Supabase a Claude (MCP)

En el chat te dejé la tarjeta del conector **Supabase**. Pulsa *Connect*, inicia sesión en Supabase y autoriza **solo la organización del proyecto**. Si el conector ofrece modo de **solo lectura**, actívalo: así Claude puede revisar tablas, políticas y registros sin poder cambiar nada. Cuando esté conectado, avísame en el chat.

## 14. Problemas comunes

| Mensaje | Causa | Solución |
|---|---|---|
| `Faltan variables de entorno obligatorias: …` | Faltó `--env-file ../.env` | Repite el comando con `--env-file ../.env` |
| `usuario o contraseña incorrectos` | La contraseña de `.env` no es la que tiene la base | Si la base de Docker no tiene datos importantes: `docker compose down -v` y `docker compose up -d db` (**borra la base local**) y vuelve a la sección 5 |
| `no se pudo conectar (¿Docker apagado…?)` | Docker Desktop o el contenedor apagados | Abre Docker Desktop y `docker compose up -d db` |
| `port is already allocated` (5432) | Otro PostgreSQL usa el puerto | Detén el otro servicio, o cambia el puerto en `docker-compose.yml` y en las URL |
| `migraciones atrasadas` | Hay migraciones nuevas | Sección 5 |
| `imports` en rojo | Intérprete o TypeScript de VS Code | Sección 10 |
| `npm run e2e`: `Executable doesn't exist` | Falta el Chromium de Playwright | `npx playwright install chromium` |
| `npm run e2e`: puerto 5011 o 5174 ocupado | Quedó un servidor de una corrida anterior | Cierra esa ventana o reinicia la terminal |
