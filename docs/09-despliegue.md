# 09 — Despliegue

> **Spec 010b.** Guía para poner AssetControl en producción y mantenerlo. Decisiones de G1 (2026-11-15): base de datos en **Supabase Free**, web y API en **un solo contenedor**. **Plataforma (spec 018):** VPS con Coolify, con dos entornos (pruebas y producción); ver la sección 6. Las secciones 1–5 sirven para cualquier plataforma que ejecute un contenedor Docker con HTTPS delante.
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
| `MIGRATION_DATABASE_URL` | Secreto del entorno `production` en GitHub | `migrar.yml` (alternativa; el camino habitual es migrar desde la PC, secciones 4 y 7) |
| `SMTP_CLAVE` (y `SMTP_USUARIO`) del proveedor de correo | Variable secreta de la plataforma | La app (correo de recuperación, spec 014) |

Generar valores fuertes (PowerShell, una vez cada uno; no los pegues en chats ni en archivos del repo):

```powershell
cd C:\Users\VICTUS16\Proyectos\AssetControl\backend
uv run python -c "import secrets; print(secrets.token_urlsafe(48))"   # SECRET_KEY
uv run python -c "import secrets; print(secrets.token_urlsafe(32))"   # APP_DB_PASSWORD (solo ASCII, sin espacios)
```

## 3. Supabase (plan Free)

**Dos proyectos separados (spec 018):** uno para **pruebas** (solo datos ficticios) y otro para **producción**, ambos en la región **São Paulo** (`sa-east-1`), la más cercana al VPS. Cada uno tiene su propia contraseña de `postgres`, su `preparar-roles`, su `APP_DB_PASSWORD`, su `SECRET_KEY`, sus llaves S3 y su bucket `fotos`: ningún secreto se comparte entre entornos. Los pasos de abajo se hacen una vez en cada proyecto.

1. Crea el proyecto en [supabase.com](https://supabase.com) en la región **São Paulo** (`sa-east-1`). Guarda la contraseña de la base (rol `postgres`).
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

uv run flask --app app preparar-roles      # crea assetcontrol_app, auth_owner y plataforma_owner (C8; spec 017)
uv run alembic upgrade head                 # migra hasta la última (0032 con los cambios C1 y C1b de la spec 017)
uv run alembic current
uv run flask --app app create-tenant "<Nombre de la clínica>" "<correo del primer admin>"
```

- `preparar-roles` envía la contraseña como **verificador SCRAM** (nunca en claro), deja el rol de la aplicación sin `SUPERUSER`, `BYPASSRLS`, `CREATEROLE` ni `CREATEDB`, y revoca las membresías que Supabase le da a `postgres` sobre los roles que crea; solo conserva la de administración (sin heredar privilegios). Es seguro repetirlo (por ejemplo, para cambiar la contraseña).
- En el pooler, el usuario lleva el sufijo del proyecto (`<rol>.<ref>`); úsalo igual en `DATABASE_URL`.
- `create-tenant` imprime una sola vez un enlace `/invitacion#…`: antepón `https://<tu-dominio>` y envíaselo solo al primer admin (vence en 24 h).
- Al terminar, cierra la ventana de PowerShell.

## 5. Variables de la app en la plataforma

Hay **dos entornos** en el mismo VPS (spec 018), cada uno como una aplicación aparte en Coolify con sus propias variables y secretos:

| Entorno | Rama | Dominio | Despliegue | Datos |
|---|---|---|---|---|
| pruebas | `develop` | `pruebas.<dominio>` | desde `develop`, automático en cada push a `develop` (P10, decidido el 2026-11-27) | solo ficticios |
| producción | `main` | `app.<dominio>` | **manual**, después de migrar (sección 7) | los de la clínica (desde el piloto) |

Los dos usan `ENVIRONMENT=production`, `ALMACEN=s3`, `TRUSTED_PROXY_HOPS=1` y la `DATABASE_URL` de su propio proyecto Supabase.

| Variable | Valor |
|---|---|
| `DATABASE_URL` | La del rol de la aplicación (pooler, modo sesión, `sslmode=require`). |
| `SECRET_KEY` | La generada (≥ 32 bytes). |
| `ENVIRONMENT` | `production` (exige TLS a la base, cookies `Secure` y HSTS). |
| `TRUSTED_PROXY_HOPS` | **Obligatoria en `production`** (SEC-01): sin ella la app no arranca y nombra la variable. **Valor: `1`** si la app está detrás de exactamente un proxy de confianza (en el VPS, el Traefik de Coolify). `0` solo si los clientes llegan directos al contenedor. Admite de 0 a 5. Un valor mayor que el número real de proxies deja que el cliente falsee su IP en el límite de tasa. |
| `FORWARDED_ALLOW_IPS` | Opcional; **no la definas** en Coolify. La lee `backend/gunicorn.conf.py` (por defecto `127.0.0.1`). Es la lista de IP o redes CIDR desde las que gunicorn acepta las cabeceras de esquema (`X-Forwarded-Proto`, `X-Forwarded-Ssl`, `X-Forwarded-Protocol`, que fijan `wsgi.url_scheme`) y las cabeceras `SCRIPT_NAME` y `PATH_INFO` (`forwarder_headers` de gunicorn). No decide la IP del cliente: esa sale de `X-Forwarded-For` con `TRUSTED_PROXY_HOPS` (ProxyFix). Detrás del Traefik de Coolify la petición llega desde la IP de Traefik en la red de Docker, no desde `127.0.0.1`, así que gunicorn ignora esas cabeceras y la app ve `http`. Eso no afecta a nada: las cookies `Secure` y HSTS dependen de `ENVIRONMENT`, la comprobación de mismo sitio compara solo el nombre del host, el enlace del correo sale de `URL_PUBLICA` y la app no arma URL absolutas ni redirecciones a partir de la petición. Un valor que incluya a Traefik dejaría además que una cabecera `SCRIPT_NAME` reenviada por el proxy cambie la ruta que ve la app. **Nunca `*`.** Si un cambio futuro necesita que la app vea `https`, se define con la IP o la red de Traefik en la red de Docker del VPS, después de comprobarla en el servidor. Decisión del humano (2026-11-27): sin definir en pruebas y producción. |
| `PORT` | Lo pone la plataforma; si no, `8000` (en Coolify se usa `8000`). |
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
| `PLATAFORMA_HABILITADA` | Spec 017. Solo el valor `true` (sin distinguir mayúsculas ni espacios) habilita la consola `/plataforma`. **Apagada por defecto**: con cualquier otro valor o sin la variable no se registra ninguna ruta `/plataforma` (responde `404`) ni se crea nada al arrancar. Ver 5.2. |
| `PLATAFORMA_REDES_PERMITIDAS` | **Obligatoria si `PLATAFORMA_HABILITADA=true` en `production`** (SEC-03): sin ella la app no arranca. Redes CIDR o direcciones sueltas separadas por comas (`10.0.0.0/8, 192.168.1.10`). Vacía = sin restricción (solo fuera de producción). Fuera de la lista, `/plataforma` responde `404`. Un valor mal formado impide arrancar (el mensaje no repite el valor). Es una defensa adicional: la restricción real va en el proxy o el firewall. |
| `RATE_LIMIT_PLAT_LOGIN_ACCOUNT`, `RATE_LIMIT_PLAT_LOGIN_IP` | Opcionales (por defecto 5 y 10 por ventana de 15 min). Login de plataforma por cuenta y por IP. |
| `RATE_LIMIT_PLAT_ACCION`, `RATE_LIMIT_PLAT_REFRESH_IP` | Opcionales (por defecto 60 y 30). Acciones de la consola por desarrollador (`POST`/`PATCH` de Empresas y Usuarios, subida o reemplazo del logo y, desde el cambio C1, los `PUT` de la ficha de la empresa y de nombre y rol de un usuario; los `GET` no cuentan) y refresh de plataforma por IP. Entre 1 y 10000. |

`MIGRATION_DATABASE_URL` **no** va en la plataforma: la app nunca usa el rol migrador.

**Fotos (SEC-02).** Límites por proceso: 25 MP por imagen (las de más se rechazan con `422`), 2 decodificaciones a la vez por proceso (si no hay cupo en 5 s, `503 procesado_ocupado`) y 60 subidas por usuario cada 10 minutos (`429 demasiadas_subidas`). Gunicorn tiene 2 trabajadores (`backend/gunicorn.conf.py`) y cada uno cuenta por separado: el tope real de subidas es hasta el doble. Un contador compartido en la base necesitaría un ámbito nuevo en `limite_tasa` (una migración), fuera de este cambio.

### 5.1 Correo de recuperación de contraseña (spec 014)

**Qué falta elegir** (cuando se decida el despliegue): el proveedor SMTP, sus credenciales y un remitente de un dominio propio verificado con SPF y DKIM (sin eso el correo llega a no deseado o no llega). La configuración ya está lista por variables (sección 5).

**Requisitos del proveedor:**

- TLS obligatorio: `starttls` (normalmente puerto 587) o `ssl` (465). La app exige **TLS 1.2 o superior** y verifica el certificado y el nombre del servidor; uno inválido o de otro nombre hace fallar el envío.
- **Sin reescritura de enlaces ni seguimiento de clics** (*click tracking*, *link branding*): desactívalos en el panel del proveedor. El enlace es `https://<tu-dominio>/restablecer#<token>`; un redirector propio del proveedor lo rompería o le haría ver el token del fragmento.
- Cada entrega tiene **10 s por operación** y un **plazo total de 45 s** (conexión, TLS, autenticación y envío); si se pasa, se corta. No hay reintentos: la persona pide otro enlace.
- Envíos simultáneos: 4 por proceso. Sin cupo, el correo se descarta y se registra `Correo de recuperación descartado: sin cupo de envío (request_id=…, descartados=N)`. **Pon una alerta** en la plataforma sobre ese texto: si aparece, el SMTP está lento o caído.

**Cabeceras.** `/restablecer#<token>` e `/invitacion#<token>` llevan un enlace de un solo uso en el fragmento. La API ya responde `Referrer-Policy: no-referrer` en `/api/auth/*`, y la web fija el meta `referrer` en `no-referrer` mientras `/restablecer` está abierta, pero el contenedor respondía `Referrer-Policy: same-origin` a toda la web (`backend/app/wsgi.py`). **Aplicado (SEC-05):** el contenedor responde `Referrer-Policy: no-referrer` en `/restablecer`, `/invitacion` y `/plataforma` (y sus subrutas); el resto de la web sigue con `same-origin`. **Aplicado (spec 018, T1):** `Referrer-Policy: no-referrer` y `Cache-Control: no-store` en `/restablecer`, `/invitacion`, `/cambiar-contrasena` y `/plataforma/**` (aunque exista un archivo con ese nombre) y en el *fallback* de `index.html` (cualquier otra ruta de la SPA); `/assets/*`, los archivos de la raíz y `/api/**` siguen con `same-origin` y su caché. Ver 5.2.

**Registro (auditoría).** El registro de la app debe quedar en nivel **INFO** en producción (gunicorn ya usa `loglevel = "info"`): ahí quedan `Contraseña restablecida por enlace de recuperación (request_id=…, usuario_id=…)` y `Correo de recuperación entregado (request_id=…)`. Nunca se registran correo, token, enlace, host ni contraseña; los rechazos y fallos solo llevan `request_id` y el tipo de error. En la base, `log_statement` debe quedar en `none` en producción (compruébalo con `SHOW log_statement;` como `postgres` y no lo subas para depurar); es el criterio único de este documento (ver también «Registro de sentencias de PostgreSQL» en la consola de plataforma). Con `all`, PostgreSQL escribiría en su registro la clave canjeable del enlace que viaja como parámetro de `acceso.*`. `mod` hoy no registraría esas llamadas (son `SELECT acceso.fn(...)`, no sentencias que modifiquen datos), pero también se prohíbe: la regla segura es `none`, sin excepciones que dependan de cómo se escribe cada llamada.

**Apagado.** Un correo en curso se pierde si el proceso se apaga (riesgo aceptado: la persona pide otro). **Aplicado (spec 018, T2):** `worker_exit` en `backend/gunicorn.conf.py` espera los envíos en curso con `Correo.esperar` hasta `PLAZO_CORREO_AL_APAGAR = 15 s` (menor que `graceful_timeout = 20`); si vence, registra en nivel WARNING `Apagado: venció el plazo de 15.0 s y se perdieron correos en curso.` (texto exacto del código, útil para poner una alerta).

- **Requisito del entorno:** el plazo de parada del contenedor en Coolify (*stop grace period*) debe ser de **25 s o más** en pruebas y en producción. Con el valor por defecto de Docker (10 s), el SIGKILL llega antes y corta la espera. Comprobación: `docker inspect` del contenedor de la API muestra `StopTimeout` ≥ 25.
- **Límites aceptados:** primero se terminan las peticiones en curso y después corre `worker_exit`, dentro de la misma ventana de `graceful_timeout`. Una entrega SMTP puede tardar hasta 45 s (`SMTP_PLAZO_TOTAL_SEGUNDOS`), así que la espera no la cubre del todo. Un correo perdido deja un token sin usar que vence solo (sin fuga). El aviso de contraseña temporal (spec 017) también puede perderse en esa ventana. El reciclado de procesos por `max_requests` no pasa por Docker, y ahí la espera sí se cumple.

**Prueba manual antes del piloto** (con el proveedor real y un correo de prueba, nunca uno de la clínica):

1. Arranca con `ENVIRONMENT=production` y `CORREO_MODO=carpeta`: la app debe negarse a arrancar. Repite con `URL_PUBLICA=http://…`: también.
2. Con `CORREO_MODO=smtp`, prueba `starttls` y luego `ssl`: en `/login` → «¿Olvidaste tu contraseña?» → tu correo. Debe llegar un correo de texto en español con el enlace `https://<tu-dominio>/restablecer#…`, sin redirector del proveedor.
3. Abre el enlace **desde el cliente de correo** (web y teléfono): la barra de direcciones queda en `/restablecer` sin el fragmento. Guarda una contraseña nueva: llegas a `/login` con «Tu contraseña se actualizó. Inicia sesión con la nueva.»; las sesiones abiertas en otros equipos se cierran al renovar (el acceso ya emitido dura hasta 15 min).
4. Abre el mismo enlace otra vez: «Enlace vencido o ya usado».
5. Revisa el registro: `Correo de recuperación entregado` y `Contraseña restablecida…` con su `request_id`, sin el correo ni el enlace.

### 5.2 Consola de plataforma `/plataforma` (spec 017)

Consola gráfica solo para desarrolladores de AssetControl (Empresas, Usuarios y Actividad). Vive en el mismo contenedor y dominio que la app de la clínica y está **apagada por defecto**.

**Comandos del operador** (rol migrador, `MIGRATION_DATABASE_URL`; desde `backend/`, con `uv run flask --app app <comando>`). No hay pantalla de alta de desarrolladores:

| Comando | Qué hace |
|---|---|
| `crear-desarrollador <correo> [--password-stdin]` | Pide el nombre y la contraseña (sin eco y con confirmación; 14–128 caracteres) o lee la contraseña de la entrada estándar. Argon2id calculado en el comando. Audita `desarrollador_creado` sin desarrollador (operador). |
| `restablecer-desarrollador <correo> [--password-stdin]` | Fija una contraseña nueva y cierra todas las sesiones del desarrollador. |
| `desactivar-desarrollador <correo> [--reactivar]` | Desactiva (cierra sus sesiones; un token vigente recibe `401` en su siguiente petición) o reactiva la cuenta. No pide contraseña. |

**Exposición (riesgo R1 de la spec 017).** `/plataforma` queda en el mismo dominio que la clínica y una cuenta de desarrollador comprometida controla todas las empresas (crear admins con contraseña conocida, definir una contraseña temporal a cualquier usuario —incluido el único admin— y entrar con ella, desactivar usuarios; no lee datos de negocio). Cada contraseña temporal queda en Actividad como «Contraseña temporal definida» y la persona pierde todas sus sesiones; no hay aviso por correo. **No habilites `PLATAFORMA_HABILITADA` en un entorno expuesto** sin restringir `/plataforma` y `/api/plataforma` por red en el proxy o el firewall (`PLATAFORMA_REDES_PERMITIDAS` solo es respaldo), y usa contraseñas largas y únicas. No hay segundo factor (TOTP): es trabajo de diseño aparte (SEC-03) y sigue pendiente **antes del piloto**; el arranque en producción ya exige la lista de redes. **No ir al piloto sin cerrar la spec 018 (T1, T2 y respaldo).** **Estado (spec 018, T8, comprobado por el humano el 2026-11-27):** en producción `PLATAFORMA_HABILITADA` no está definida y `/plataforma` responde `404`.

**Notas de despliegue acumuladas:**

- **Relojes (NTP obligatorio):** Flask y PostgreSQL deben tener la hora sincronizada. El corte `usuario.sesiones_validas_desde` usa `now()` de la base y el access token usa la hora de Flask: con la base adelantada más de 60 s, todo acceso emitido tras un cambio de contraseña se rechaza hasta que el reloj de Flask alcance el corte.
- **Orden con la migración `0026`:** migrar `0026` **antes** de desplegar el código (el ORM lee `usuario.sesiones_validas_desde` en cada petición). Para revertir, retirar el código **antes** del `alembic downgrade`.
- **Cookie de refresh de plataforma:** viaja con `Path=/plataforma/auth` en la aplicación. En el contenedor único, la API montada bajo `/api` la deja en `/api/plataforma/auth`, y el servidor de desarrollo de Vite ya lo reescribe (`cookiePathRewrite`); un proxy de producción que quite el prefijo `/api` debe reescribir `/plataforma/auth` a `/api/plataforma/auth` igual que hace con `/auth`. Si no, el navegador no manda la cookie al refresh y recargar la consola pierde la sesión. **Resuelto (spec 018, T7, comprobado por el humano en «pruebas» el 2026-11-27):** detrás del Traefik de Coolify la cookie sale con `Path=/api/plataforma/auth` y recargar la consola conserva la sesión.
- **Cabeceras de las páginas de la consola:** las respuestas de la API de plataforma ya llevan `Cache-Control: no-store` y `Referrer-Policy: no-referrer`. Las páginas web `/plataforma/**` ya reciben `Referrer-Policy: no-referrer` del contenedor (SEC-05). **Aplicado (spec 018, T1):** `Referrer-Policy: no-referrer` y `Cache-Control: no-store` en `/restablecer`, `/invitacion`, `/cambiar-contrasena` y `/plataforma/**` (aunque exista un archivo con ese nombre) y en el *fallback* de `index.html` (cualquier otra ruta); `/assets/*`, los archivos de la raíz y `/api/**` siguen con `same-origin` y su caché. Se pone en el contenedor, no en el proxy. Las páginas llevan `noindex, nofollow`.
  - *Corregido (spec 018, T10; riesgo R12):* los `fetch` de `web/src/lib/api/cliente.ts` envían `referrerPolicy: 'strict-origin'`, así que el `Origin` es el real y el `Referer` lleva solo el origen, sin ruta, consulta ni fragmento. El servidor sigue sin aceptar `Origin: null`. `/health` (GET, `web/src/lib/health.ts`) no la necesita. Una prueba de guarda (`cliente.test.ts`) impide `fetch` fuera de `cliente.ts` y `health.ts`. Verificado en pruebas (jsdom), **no** en un navegador viejo real. Antes de T10: con `no-referrer` en el documento de la SPA, los POST del mismo origen enviaban `Origin: null`; si además faltaba `Sec-Fetch-Site` (Safari/iOS 16.0–16.3, Firefox anterior a la 90), la comprobación de mismo sitio respondía 403 en refresh, logout, recuperar y restablecer (también en la consola). Fallaba cerrado, sin abrir CSRF; en esos navegadores el logout no revocaba el refresh token en el servidor.
- **Tope de cuerpo:** `/plataforma` rechaza cuerpos de más de 4 KB (`413`), salvo `POST /plataforma/empresas/<id>/logo`, que admite 2 MB + 64 KB (el logo de la spec 013 y su formulario). Si el proxy impone un tope menor, súbelo solo para esa ruta. **Resuelto (spec 018, T7, comprobado por el humano en «pruebas» el 2026-11-27):** por el dominio real, un logo de 2 MB se acepta y uno de más de 2 MB + 64 KB responde `413` de la app, sin que el Traefik de Coolify lo corte antes. La subida chunked del logo requiere un servidor WSGI que marque `wsgi.input_terminated` (gunicorn lo hace). Si se cambia de servidor y no la marca, la subida sin Content-Length responde 400.
- **Almacén para logos:** el logo del alta y su reemplazo desde «Editar empresa» (cambio C1) usan el mismo almacén que las fotos y el logo de la clínica (`ALMACEN=s3`, bucket `fotos`, clave `<tenant>/<logo>.png`). Reemplazar no borra el archivo anterior (los informes cerrados lo siguen usando). Sin almacén, la subida responde `503 logos_no_disponibles`: la empresa se crea igual, la consola avisa «Empresa creada; el logo no se pudo subir» y se reintenta desde «Editar empresa» (o el admin lo sube en su pantalla Empresa). Si falla el borrado del archivo tras un `rollback` (mejor esfuerzo, como en la 013) puede quedar un archivo huérfano sin fila.
- **Registro de sentencias de PostgreSQL (cambio C1b):** la contraseña temporal se convierte en hash Argon2id en Flask y el hash viaja a la base como **parámetro** de `acceso.plataforma_restablecer_password_usuario` (igual que en el alta, el cambio de contraseña y la recuperación). Criterio único: `log_statement = none` en producción (ni `ddl`, ni `mod`, ni `all`). `mod` no registraría estas llamadas, porque son `SELECT acceso.fn(...)`, pero se prohíbe igual por regla segura. Si usas `log_min_duration_statement` o `auto_explain`, fija además `log_parameter_max_length = 0` (y `log_parameter_max_length_on_error = 0`) para que no se registren los parámetros, y no actives `auto_explain` con parámetros. Si no, el hash quedaría en los registros de la base. Nota: esto vale porque hoy psycopg 3 enlaza los parámetros en el servidor (protocolo extendido). Si algún día se usa `ClientCursor` (u otro enlace en el cliente), los valores irían dentro del texto de la sentencia y `log_parameter_max_length` ya no los protegería: cualquier registro de sentencias los mostraría.
- **Rol `plataforma_owner`:** lo crea `preparar-roles` (`NOLOGIN`, sin atributos). `preparar-roles` y las migraciones se ejecutaron en los dos proyectos de Supabase (T5 y T8).

**Prueba manual antes del piloto** (con datos de prueba, nunca de la clínica): crea un desarrollador con `crear-desarrollador`, entra a `/plataforma/entrar`, crea una empresa con logo (con el almacén real) y entra como su admin: debe llevar a `/cambiar-contrasena` y, tras cambiarla, a `/admin`. Recarga la consola con la sesión abierta (comprueba la cookie), desactiva y reactiva la empresa y revisa Actividad. Del cambio C1: edita la ficha y reemplaza el logo (el admin lo ve en `/admin/empresa` y un informe ya cerrado conserva el anterior), cambia el rol de un usuario de prueba (su sesión abierta se cierra y al volver a entrar tiene los permisos nuevos) y comprueba en Actividad «Empresa editada», «Logo reemplazado» y «Usuario editado». Del cambio C1b: con un usuario de prueba con sesión abierta, define una contraseña temporal desde Usuarios; su sesión cae al recargar, la contraseña anterior da «incorrectos», con la temporal llega a «Cambia tu contraseña», la cambia y entra; la fila mostró «Cambio de contraseña pendiente» y Actividad registra «Contraseña temporal definida».

## 6. Plataforma: VPS con Coolify

Spec 018 ([`specs/018-despliegue-vps/`](../specs/018-despliegue-vps/spec.md)). AssetControl corre en un VPS propio (Ubuntu 24.04) que ya tiene **Coolify** con su **Traefik** en los puertos 80 y 443 y otra aplicación ajena a AssetControl.

```text
Navegador ──HTTPS──▶ <IP-del-VPS>:443  Traefik de Coolify (TLS y enrutado por dominio)
                                         ├─ pruebas.<dominio> ─▶ contenedor «pruebas» (develop) ─▶ Supabase pruebas
                                         ├─ app.<dominio>     ─▶ contenedor «producción» (main) ─▶ Supabase producción
                                         ├─ <panel>.<dominio> ─▶ panel de Coolify
                                         └─ (la otra app del VPS, sin cambios)
```

**Arquitectura:**

- **TLS y enrutado:** los hace el Traefik de Coolify (certificados gestionados por Coolify). **No** se instala Caddy ni nginx propios: un segundo proxy en 80/443 chocaría con el existente.
- **Imagen:** `Dockerfile.prod` desde la raíz del repo, el mismo contenedor de la sección 1 (web en `/`, API en `/api`).
- **Puerto y salud:** `PORT=8000`; healthcheck en `/api/ready`.
- **Proxy de confianza:** `TRUSTED_PROXY_HOPS=1` (solo Traefik delante); la app toma la IP real del cliente para los límites de tasa (comprobado en «pruebas», T7).
- **Entorno:** `ENVIRONMENT=production` en los dos entornos (TLS a la base, cookies `Secure`, HSTS).
- **Dos entornos** (tabla de la sección 5): «pruebas» desde `develop` (despliegue automático en cada push a `develop`; P10, decidido el 2026-11-27) y solo datos ficticios; «producción» desde `main` con despliegue **manual**. Cada uno con su proyecto Supabase y sus secretos.
- `/plataforma` apagada en producción (`PLATAFORMA_HABILITADA` sin definir; sección 5.2).

**Endurecimiento del VPS (una vez, lo hace el humano):**

1. **SSH:** usuario con `sudo` y llave pública; probar la llave en una **segunda** sesión antes de cerrar la primera; luego `PasswordAuthentication no` y `PermitRootLogin no`. La consola web del proveedor del VPS sirve de respaldo si se pierde el acceso.
2. **fail2ban** para `sshd`.
3. **Hora:** NTP activo (`timedatectl` debe mostrar `System clock synchronized: yes`); Flask y PostgreSQL no pueden diferir más de 60 s (sección 5.2, «Relojes»).
4. **Actualizaciones** y reinicio si el kernel lo pide; comprobar que Coolify, Traefik y la otra app vuelven solos.
5. **Panel de Coolify** solo por `https://<panel>.<dominio>`; el puerto del panel (`:8000`) y el dashboard de Traefik (`:8080`) cerrados desde fuera. Docker salta `ufw`, así que se cierran sin publicarlos en Coolify/Traefik y se comprueba desde otra red (`curl -m 5 http://<IP-del-VPS>:8000` y `:8080` deben fallar).
6. Si el proveedor del VPS ofrece cortafuegos en su panel, permitir solo 22, 80 y 443 como capa adicional.

**Crear cada aplicación en Coolify (lo hace el humano):**

1. DNS: registros `A` de `pruebas.<dominio>`, `app.<dominio>` y `<panel>.<dominio>` hacia `<IP-del-VPS>`.
2. Prepara y migra su proyecto Supabase desde la PC (sección 4) **antes** del primer despliegue.
3. Nueva aplicación desde el repositorio, *build pack* Dockerfile con `Dockerfile.prod`, rama `develop` (pruebas) o `main` (producción), dominio `https://pruebas.<dominio>` o `https://app.<dominio>`, puerto `8000` y healthcheck `/api/ready`.
4. Plazo de parada (*stop grace period*) de **25 s o más** (sección 5.1, «Apagado»); comprobar con `docker inspect` que `StopTimeout` ≥ 25.
5. Variables de la sección 5, con los secretos marcados como secretos en Coolify. Nunca `MIGRATION_DATABASE_URL`.
6. «Pruebas» se despliega automáticamente en cada push a `develop` (P10, decidido el 2026-11-27); en «producción» el despliegue automático queda desactivado (se despliega a mano, sección 7).
7. Comprobar: `https://pruebas.<dominio>/api/ready` o `https://app.<dominio>/api/ready` responde `{"status":"ok"}`, `http://` redirige a `https://`, el registro de arranque no avisa `TRUSTED_PROXY_HOPS=0` y la otra app del VPS sigue respondiendo.

**Recursos:** el VPS comparte memoria entre los dos entornos, la otra app y Coolify; gunicorn usa 2 procesos × 4 hilos y Argon2 (19 MiB) por hilo. Si la memoria aprieta, el humano decide con la medida si baja `workers` en «pruebas».

## 7. Migrar y desplegar

### 7.1 Antes de subir a `develop` un cambio con migración

Como «pruebas» se despliega automáticamente en cada push a `develop` (P10, decidido el 2026-11-27), una migración nueva se aplica en el proyecto de «pruebas» desde la PC **antes** de subir a `develop` el cambio que la necesita; si no, el código nuevo arranca contra un esquema viejo. Migra primero el proyecto de «pruebas» desde la PC: en una ventana nueva de PowerShell, con la `MIGRATION_DATABASE_URL` del proyecto de pruebas solo en esa ventana, `uv run alembic upgrade head` y `uv run alembic current` (sección 4); cierra la ventana al terminar. Así la base de «pruebas» ya tiene el esquema nuevo cuando se despliega el código de `develop` (spec 018, R10 y R12).

### 7.2 Cada vez que algo llega a `main`

1. El humano pasa `develop` → `main` (nunca Claude).
2. La CI corre en `main`: `backend`, `c8` (base como Supabase) e `imagen` (contenedor de producción con prueba de humo).
3. **Respaldo** de producción (sección 8) si el cambio trae una migración.
4. **Migrar desde la PC antes del despliegue manual** (spec 018): en una ventana nueva de PowerShell, con la `MIGRATION_DATABASE_URL` del proyecto de producción solo en esa ventana, `uv run alembic upgrade head` y `uv run alembic current` (sección 4); cierra la ventana al terminar. `MIGRATION_DATABASE_URL` **nunca** va en el VPS ni en Coolify.
   - `migrar.yml` sigue en el repositorio sin cambios, pero el camino vigente con el VPS es migrar desde la PC.
   - Alternativa: `migrar.yml` desde GitHub (configuración del entorno `production`):
     - Configuración una sola vez: Settings → Environments → `production` con *Required reviewers* (tú); secreto `MIGRATION_DATABASE_URL`; variable `APP_DB_USER = assetcontrol_app`.
5. **Desplegar** a mano en Coolify la aplicación de producción (sección 6), solo después de migrar y con la CI de `main` en verde.
6. **Comprobar:** `https://app.<dominio>/api/ready` responde `{"status": "ok"}`; entra como admin; en un teléfono abre *Escanear* y confirma que la cámara funciona.

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
- **Contraseña de `postgres`:** cámbiala en cada proyecto de Supabase y actualiza el secreto `MIGRATION_DATABASE_URL` del entorno `production` en GitHub (`migrar.yml`) y tu gestor de contraseñas. Nunca en el VPS ni en Coolify.

## 10. Volver atrás

- **Código:** vuelve a desplegar la versión anterior de la imagen o del commit en la plataforma.
- **Base:** primero intenta corregir hacia adelante (una migración nueva). `alembic downgrade <revisión>` solo si la migración no borra datos (las de tablas nuevas sí los borran al bajar: `0011` elimina los informes congelados). Haz un respaldo justo antes.

## 11. Qué no hacer

- No habilitar `PLATAFORMA_HABILITADA` en un entorno expuesto sin restringir `/plataforma` por red (sección 5.2).
- No usar las claves `anon` ni `service_role` de Supabase, ni Supabase Auth ni Storage público.
- No poner `MIGRATION_DATABASE_URL` en la plataforma ni en `.env` del servidor.
- No desplegar con `ENVIRONMENT=development` ni con `sslmode=disable`, `allow` o `prefer` (la app se niega a arrancar). Con `development` la app aceptaría además el buzón en carpeta y una `URL_PUBLICA` con `http`.
- No activar en el proveedor de correo la reescritura de enlaces ni el seguimiento de clics, ni subir `log_statement` de la base de `none` (tampoco a `ddl` ni `mod`).
- No publicar `.claude/`, `.cursor/`, `AGENTS.md`, `CLAUDE.md` ni `MEMORY.md` (la imagen no los copia).

**En el VPS (spec 018):**

- No poner `MIGRATION_DATABASE_URL` ni la contraseña de `postgres` en el VPS ni en Coolify: se migra desde la PC (sección 7).
- No instalar Caddy ni nginx propios: TLS y enrutado son del Traefik de Coolify.
- No tocar la otra aplicación del VPS ni la configuración global de Traefik más de lo necesario; tras cada cambio, comprobar que sigue respondiendo.
- No poner datos reales en «pruebas» ni restaurar en él un respaldo de producción.
- No activar el despliegue automático en producción: se despliega a mano, después de migrar.
- No publicar el panel de Coolify (`:8000`) ni el dashboard de Traefik (`:8080`) hacia fuera, ni volver a permitir SSH con contraseña o como `root`.
- No escribir en el repositorio el dominio real, la IP del VPS, usuarios ni contraseñas: se usan los marcadores `<dominio>`, `<IP-del-VPS>` y `<panel>.<dominio>`.
- No usar `StripPrefix /api` en Traefik ni la variable `SCRIPT_NAME` en gunicorn: el contenedor monta la API en `/api` (`backend/app/wsgi.py`) y decide las cabeceras de T1 por la ruta completa (`PATH_INFO`); quitar o mover el prefijo rompe la API o deja páginas sensibles sin `no-store`.
- No agregar en Coolify un middleware de caché: las páginas sensibles deben llegar con `Cache-Control: no-store` tal como las responde el contenedor.
- Si se activa el access log de Traefik: desde T10 registra el `Referer` con solo el origen (no sensible); la consulta de `/api/...` puede quedar registrada, igual que antes.
