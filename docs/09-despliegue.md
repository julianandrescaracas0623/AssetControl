# 09 — Despliegue

> **Spec 010b.** Guía para poner AssetControl en producción y mantenerlo. Decisiones de G1 (2026-11-15): base de datos en **Supabase Free**, web y API en **un solo contenedor**, **plataforma pendiente** (Q1). Todo lo de abajo sirve para cualquier plataforma que ejecute un contenedor Docker con HTTPS delante; la sección 6 se completa cuando se elija.
>
> Claude no crea cuentas, no ve ni guarda secretos y no hace `push` a `main`. Los pasos con secretos los hace el humano.

## 1. Cómo queda en producción

```text
Teléfono / computador ──HTTPS──▶ Plataforma (TLS, proxy) ──▶ Contenedor (Dockerfile.prod)
                                                            gunicorn: web en "/", API en "/api"
                                                                   │  TLS (sslmode=require)
                                                                   ▼
                                                       Supabase: PostgreSQL (pooler, modo sesión)
```

- **Un contenedor** (`Dockerfile.prod`): la web compilada y la API con gunicorn (`backend/gunicorn.conf.py`, 2 procesos × 4 hilos). Mismo origen: la cookie de sesión viaja con `Path=/api/auth` y no hace falta CORS.
- **Salud:** `GET /api/ready` (200 si la base responde). La imagen trae `HEALTHCHECK`.
- **Cabeceras:** CSP estricta, HSTS (solo `ENVIRONMENT=production`), `X-Frame-Options: DENY`, `Permissions-Policy` con `camera=(self)`.
- **Base:** Supabase solo como PostgreSQL administrado. **No** se usan Supabase Auth, su API de datos ni sus claves (`anon`, `service_role`). RLS obligatoria; la app entra con su propio rol sin `BYPASSRLS`.

## 2. Cuentas y secretos

| Qué | Dónde se guarda | Quién lo usa |
|---|---|---|
| Contraseña del rol `postgres` de Supabase | Gestor de contraseñas del humano | Preparar roles y migrar |
| `APP_DB_PASSWORD` (rol de la aplicación) | Gestor de contraseñas; dentro de `DATABASE_URL` en la plataforma | La app |
| `SECRET_KEY` | Variable secreta de la plataforma | La app (firma los JWT) |
| `MIGRATION_DATABASE_URL` | Secreto del entorno `production` en GitHub | `migrar.yml` |
| `SMTP_CLAVE` (y `SMTP_USUARIO`) del proveedor de correo | Variable secreta de la plataforma | La app (correo de recuperación, spec 014) |

Generar valores fuertes (PowerShell, una vez cada uno; no los pegues en chats ni en archivos del repo):

```powershell
cd C:\Users\VICTUS16\Proyectos\AssetControl\backend
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"   # SECRET_KEY
uv run python -c "import secrets; print(secrets.token_urlsafe(32))"   # APP_DB_PASSWORD (solo ASCII, sin espacios)
```

## 3. Supabase (plan Free)

1. Crea el proyecto en [supabase.com](https://supabase.com) con una región cercana a la plataforma que se elija (sin plataforma aún: **este de EE. UU.**, cerca de Colombia). Guarda la contraseña de la base (rol `postgres`).
2. **Apaga la API de datos** (en el panel del proyecto, la sección *Data API*; si tu panel la ubica en otro lugar, búscala por ese nombre). AssetControl no la usa; así nadie puede llegar a las tablas por ese camino aunque una clave se filtre. Las migraciones igual revocan todo a `anon`, `authenticated` y `service_role` (C8, migración `0012`).
3. Copia la cadena del **pooler en modo sesión** (Connect → *Session pooler*, puerto 5432). La conexión directa puede ser solo IPv6 y el modo transacción no conserva las variables de sesión que usa el RLS. Pásala al formato de SQLAlchemy y exige TLS:

   ```text
   postgresql+psycopg://postgres.<ref>:<contraseña>@<host-del-pooler>:5432/postgres?sslmode=require
   ```

   Si la contraseña lleva `@ : / ? # %`, codifícala (por ejemplo `@` → `%40`).

4. **Fotos (spec 012).** En *Storage*, crea un bucket **privado** llamado `fotos` (sin acceso público ni políticas para `anon` o `authenticated`: solo Flask entra, con llaves S3). En *Storage → Settings → S3 Connection* activa la conexión S3, copia el **endpoint** (`https://<ref>.storage.supabase.co/storage/v1/s3`) y la **región**, y crea un par de **llaves de acceso S3** (se muestran una sola vez: guárdalas en tu gestor de contraseñas). El plan Free trae 1 GB: unas 3.000 fotos (cada una ~300 KB con su miniatura; las cambiadas o quitadas se borran). El uso se ve en *Storage → Usage*. El mismo bucket guarda los **logos de la empresa** (spec 013, PNG de pocos KB): no se borran porque los informes cerrados los usan.

**Riesgos aceptados del plan Free (G1):**

- **Pausa por inactividad:** tras 7 días sin uso el proyecto se pausa y la app responde error de base. **Antes de cada conteo**, entra al panel de Supabase y reactívalo; comprueba `https://<tu-dominio>/api/ready`.
- **Sin copias garantizadas:** el respaldo manual de la sección 8 es **obligatorio** antes y después de cada conteo.

## 4. Preparar la base (una vez, desde tu PC)

En una ventana de PowerShell nueva (las variables viven solo en esa ventana):

```powershell
cd C:\Users\VICTUS16\Proyectos\AssetControl\backend
$env:MIGRATION_DATABASE_URL = "postgresql+psycopg://postgres.<ref>:<contraseña>@<pooler>:5432/postgres?sslmode=require"
$env:APP_DB_USER = "assetcontrol_app"
$env:APP_DB_PASSWORD = "<la que generaste>"
$env:DATABASE_URL = "postgresql+psycopg://assetcontrol_app.<ref>:<APP_DB_PASSWORD>@<pooler>:5432/postgres?sslmode=require"
$env:SECRET_KEY = "<la que generaste>"
$env:ENVIRONMENT = "production"

uv run flask --app app preparar-roles      # crea assetcontrol_app y auth_owner (C8)
uv run alembic upgrade head                 # migra hasta la última (0012)
uv run alembic current
uv run flask --app app create-tenant "<Nombre de la clínica>" "<correo del primer admin>"
```

- `preparar-roles` envía la contraseña como **verificador SCRAM** (nunca en claro), deja el rol de la aplicación sin `SUPERUSER`, `BYPASSRLS`, `CREATEROLE` ni `CREATEDB`, y revoca las membresías que Supabase le da a `postgres` sobre los roles que crea; solo conserva la de administración (sin heredar privilegios). Es seguro repetirlo (por ejemplo, para cambiar la contraseña).
- En el pooler, el usuario lleva el sufijo del proyecto (`<rol>.<ref>`); úsalo igual en `DATABASE_URL`.
- `create-tenant` imprime una sola vez un enlace `/invitacion#…`: antepón `https://<tu-dominio>` y envíaselo solo al primer admin (vence en 24 h).
- Al terminar, cierra la ventana de PowerShell.

## 5. Variables de la app en la plataforma

| Variable | Valor |
|---|---|
| `DATABASE_URL` | La del rol de la aplicación (pooler, modo sesión, `sslmode=require`). |
| `SECRET_KEY` | La generada (≥ 32 bytes). |
| `ENVIRONMENT` | `production` (exige TLS a la base, cookies `Secure` y HSTS). |
| `TRUSTED_PROXY_HOPS` | Proxies delante del contenedor; normalmente `1`. Con `0` la app avisa al arrancar y el límite de tasa trataría a todos como una sola IP. |
| `PORT` | Lo pone la plataforma; si no, `8000`. |
| `RATE_LIMIT_*`, `ARGON2_MAX_CONCURRENCY` | Opcionales (`.env.example`). |
| `ALMACEN` | `s3` (spec 012). Sin esta variable la app arranca con las **fotos desactivadas** (responden `503`) y lo avisa en el registro; `carpeta` no se admite en producción (el contenedor no guarda archivos). |
| `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET` | Los de la sección 3, paso 4 (`S3_BUCKET=fotos`). |
| `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | Las llaves S3 de Supabase, como **secretos** de la plataforma. Si falta alguna con `ALMACEN=s3`, la app no arranca y dice cuál. |

| `CORREO_MODO` | `smtp` (spec 014). Sin esta variable la app arranca con la **recuperación de contraseña desactivada** y lo avisa una vez en el registro: `/auth/recuperar` responde el mismo `202` sin tocar la base ni enviar nada. `carpeta` no se admite en producción (la app se niega a arrancar). |
| `CORREO_REMITENTE` | Obligatoria con `smtp`: `Nombre <correo@dominio>` o `correo@dominio`, de un dominio verificado en el proveedor (SPF y DKIM). |
| `SMTP_HOST` | Obligatoria con `smtp`: el servidor del proveedor. |
| `SMTP_CIFRADO` | Obligatoria fuera de development: `starttls` o `ssl`. Nunca hay texto plano. |
| `SMTP_PUERTO` | Opcional: por defecto `587` con `starttls` y `465` con `ssl`. |
| `SMTP_USUARIO`, `SMTP_CLAVE` | Las credenciales del proveedor, como **secretos**; van juntas o ninguna (si falta una, la app no arranca y dice cuál, sin mostrar valores). |
| `URL_PUBLICA` | Obligatoria con `CORREO_MODO`: `https://<tu-dominio>`, sin `/` final, sin `?`, `#` ni usuario. Es la base del enlace del correo; nunca se toma de la petición. Fuera de development debe ser `https`. |

`MIGRATION_DATABASE_URL` **no** va en la plataforma: la app nunca usa el rol migrador.

### 5.1 Correo de recuperación de contraseña (spec 014)

**Qué falta elegir** (cuando se decida el despliegue): el proveedor SMTP, sus credenciales y un remitente de un dominio propio verificado con SPF y DKIM (sin eso el correo llega a no deseado o no llega). La configuración ya está lista por variables (sección 5).

**Requisitos del proveedor:**

- TLS obligatorio: `starttls` (normalmente puerto 587) o `ssl` (465). La app exige **TLS 1.2 o superior** y verifica el certificado y el nombre del servidor; uno inválido o de otro nombre hace fallar el envío.
- **Sin reescritura de enlaces ni seguimiento de clics** (*click tracking*, *link branding*): desactívalos en el panel del proveedor. El enlace es `https://<tu-dominio>/restablecer#<token>`; un redirector propio del proveedor lo rompería o le haría ver el token del fragmento.
- Cada entrega tiene **10 s por operación** y un **plazo total de 45 s** (conexión, TLS, autenticación y envío); si se pasa, se corta. No hay reintentos: la persona pide otro enlace.
- Envíos simultáneos: 4 por proceso. Sin cupo, el correo se descarta y se registra `Correo de recuperación descartado: sin cupo de envío (request_id=…, descartados=N)`. **Pon una alerta** en la plataforma sobre ese texto: si aparece, el SMTP está lento o caído.

**Cabeceras.** `/restablecer#<token>` e `/invitacion#<token>` llevan un enlace de un solo uso en el fragmento. La API ya responde `Referrer-Policy: no-referrer` en `/api/auth/*`, y la web fija el meta `referrer` en `no-referrer` mientras `/restablecer` está abierta, pero el contenedor responde hoy `Referrer-Policy: same-origin` a toda la web (`backend/app/wsgi.py`). **Pendiente de la spec de despliegue:** responder `Referrer-Policy: no-referrer` en `/restablecer`, en `/invitacion` y en el *fallback* de la SPA (`index.html`), o en toda la web.

**Registro (auditoría).** El registro de la app debe quedar en nivel **INFO** en producción (gunicorn ya usa `loglevel = "info"`): ahí quedan `Contraseña restablecida por enlace de recuperación (request_id=…, usuario_id=…)` y `Correo de recuperación entregado (request_id=…)`. Nunca se registran correo, token, enlace, host ni contraseña; los rechazos y fallos solo llevan `request_id` y el tipo de error. En la base, `log_statement` debe quedar en `none` (compruébalo con `SHOW log_statement;` como `postgres` y no lo subas para depurar): con `all` o `mod`, PostgreSQL escribiría en su registro la clave canjeable del enlace que viaja como parámetro de `acceso.*`.

**Apagado.** Un correo en curso se pierde si el proceso se apaga (riesgo aceptado: la persona pide otro). **Pendiente de la spec de despliegue:** un `worker_exit` en `backend/gunicorn.conf.py` que llame a `Correo.esperar(timeout)` (con un plazo menor que `graceful_timeout = 20`) para dejar terminar los envíos en curso.

**Prueba manual antes del piloto** (con el proveedor real y un correo de prueba, nunca uno de la clínica):

1. Arranca con `ENVIRONMENT=production` y `CORREO_MODO=carpeta`: la app debe negarse a arrancar. Repite con `URL_PUBLICA=http://…`: también.
2. Con `CORREO_MODO=smtp`, prueba `starttls` y luego `ssl`: en `/login` → «¿Olvidaste tu contraseña?» → tu correo. Debe llegar un correo de texto en español con el enlace `https://<tu-dominio>/restablecer#…`, sin redirector del proveedor.
3. Abre el enlace **desde el cliente de correo** (web y teléfono): la barra de direcciones queda en `/restablecer` sin el fragmento. Guarda una contraseña nueva: llegas a `/login` con «Tu contraseña se actualizó. Inicia sesión con la nueva.»; las sesiones abiertas en otros equipos se cierran al renovar (el acceso ya emitido dura hasta 15 min).
4. Abre el mismo enlace otra vez: «Enlace vencido o ya usado».
5. Revisa el registro: `Correo de recuperación entregado` y `Contraseña restablecida…` con su `request_id`, sin el correo ni el enlace.

## 6. Plataforma (pendiente, Q1)

Lo que cualquier plataforma necesita de AssetControl:

- Construir la imagen con `Dockerfile.prod` desde la raíz del repo (o desde una imagen ya construida por GitHub Actions).
- Exponer el puerto `$PORT`, comprobar salud en `/api/ready` y poner **HTTPS** delante (la cámara del teléfono no funciona sin él).
- Las variables de la sección 5.
- Desplegar solo desde `main` y solo después de `migrar.yml`.

Cuando se elija la plataforma se añaden aquí sus pasos y, si conviene, un paso de despliegue al final de `migrar.yml`.

## 7. Cada vez que algo llega a `main`

1. El humano pasa `develop` → `main` (nunca Claude).
2. La CI corre en `main`: `backend`, `c8` (base como Supabase) e `imagen` (contenedor de producción con prueba de humo).
3. **Migrar:** GitHub → Actions → *Migrar producción* → *Run workflow* desde `main`, escribe `migrar` y aprueba el entorno `production`. El flujo verifica que la CI de ese commit esté en verde antes de tocar la base.
   - Configuración una sola vez: Settings → Environments → `production` con *Required reviewers* (tú); secreto `MIGRATION_DATABASE_URL`; variable `APP_DB_USER = assetcontrol_app`.
4. **Desplegar** en la plataforma (sección 6).
5. **Comprobar:** `https://<dominio>/api/ready` responde `{"status": "ok"}`; entra como admin; en un teléfono abre *Escanear* y confirma que la cámara funciona.

## 8. Respaldo y restauración

**Antes y después de cada conteo** (y antes de una migración que borre datos):

```powershell
cd C:\Users\VICTUS16\Proyectos\AssetControl\backend
$env:PGPASSWORD = "<contraseña de postgres>"
pg_dump --format=custom --no-owner --no-privileges `
  "host=<pooler> port=5432 dbname=postgres user=postgres.<ref> sslmode=require" `
  --file "C:\Respaldos\AssetControl\assetcontrol-$(Get-Date -Format yyyy-MM-dd-HHmm).dump"
Remove-Item Env:PGPASSWORD
```

- Guarda los respaldos **fuera del repositorio** (`datos/` y `*.sql` están prohibidos en git) y en un lugar cifrado; son datos de la clínica.
- Necesitas las herramientas cliente de PostgreSQL (`pg_dump`, `pg_restore`) de la misma versión mayor que Supabase o superior.
- **Restaurar:** en un proyecto nuevo, prepara la base (sección 4, sin `create-tenant`) y restaura los datos con `pg_restore --data-only --no-owner --no-privileges` usando el rol migrador. El migrador de Supabase no es superusuario y las tablas tienen disparadores e inmutabilidad, así que **el procedimiento exacto se valida en un ensayo antes del piloto** (pendiente, en un proyecto aparte) y se anota aquí.

**Fotos:** el respaldo de la base no incluye las imágenes. Para guardarlas, descarga el bucket `fotos` desde el panel de Supabase (o con cualquier cliente S3 y las mismas llaves) junto con el respaldo de la base.

## 9. Rotación de secretos

- **`SECRET_KEY`:** cámbiala en la plataforma y vuelve a desplegar. Todas las sesiones se cierran y cada persona vuelve a entrar.
- **Contraseña de la app:** genera una nueva, ejecuta `uv run flask --app app preparar-roles` con la nueva `APP_DB_PASSWORD` (sección 4), actualiza `DATABASE_URL` en la plataforma y vuelve a desplegar.
- **Contraseña de `postgres`:** cámbiala en Supabase y actualiza el secreto `MIGRATION_DATABASE_URL` en GitHub.

## 10. Volver atrás

- **Código:** vuelve a desplegar la versión anterior de la imagen o del commit en la plataforma.
- **Base:** primero intenta corregir hacia adelante (una migración nueva). `alembic downgrade <revisión>` solo si la migración no borra datos (las de tablas nuevas sí los borran al bajar: `0011` elimina los informes congelados). Haz un respaldo justo antes.

## 11. Qué no hacer

- No usar las claves `anon` ni `service_role` de Supabase, ni Supabase Auth ni Storage público.
- No poner `MIGRATION_DATABASE_URL` en la plataforma ni en `.env` del servidor.
- No desplegar con `ENVIRONMENT=development` ni con `sslmode=disable`, `allow` o `prefer` (la app se niega a arrancar). Con `development` la app aceptaría además el buzón en carpeta y una `URL_PUBLICA` con `http`.
- No activar en el proveedor de correo la reescritura de enlaces ni el seguimiento de clics, ni subir `log_statement` de la base.
- No publicar `.claude/`, `.cursor/`, `AGENTS.md`, `CLAUDE.md` ni `MEMORY.md` (la imagen no los copia).
