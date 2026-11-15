# Spec 010b — Despliegue

> **Estado:** Aprobada (G1–G3, 2026-11-15) con Q2 = Free, Q3 = un solo contenedor y **Q1 (plataforma) pendiente**: el humano la revisa; esta spec deja todo independiente de la plataforma. Requisito del piloto (011): R1 de `MEMORY.md` y deuda (b) y (e) de la spec 002 («no exponer login, refresh, validar ni aceptar sin servidor WSGI real»). Cierra T10 de `docs/05` y C8 (validar con el PostgreSQL de Supabase). Plan en `plan.md`, tareas en `tasks.md`.

## Problema

AssetControl solo corre en desarrollo: Flask con su servidor de pruebas, Vite con su proxy y una base local. Para el piloto hace falta una dirección HTTPS estable (la cámara del teléfono la exige), un servidor WSGI real, la web y la API en el mismo sitio (la cookie de refresh y la defensa CSRF lo suponen), la base en Supabase con el rol de la aplicación sin `BYPASSRLS`, migraciones controladas y una forma repetible de desplegar y de volver atrás. Nada de eso existe todavía, y dónde se aloja el backend sigue abierto (T10).

## Usuarios

- **Humano (julian):** crea las cuentas, guarda los secretos, aprueba cada paso a `main` y ejecuta el despliegue con una guía escrita.
- **Admin y contador de la clínica:** usan la app en `https://…` desde el computador y el teléfono.

## Alcance

- Dentro: imagen de producción (web compilada + API con gunicorn), API montada bajo `/api` en el mismo origen, cabeceras de seguridad, configuración de producción y proxy, roles de base en Supabase, migraciones desde GitHub Actions, despliegue desde `main`, guía de despliegue y de vuelta atrás, verificación del contenedor de producción.
- Fuera: dominio propio (se puede añadir después sin cambiar código), fotos (M10 no está en el MVP), monitoreo pago, varios entornos (staging) — se decide tras el piloto, correo, CDN.

## Requisitos (EARS)

1. **R1 Mismo origen.** La web y la API deben servirse desde el mismo origen: la web en `/` (con `index.html` para las rutas de la SPA) y la API bajo `/api`, de modo que la cookie de refresh viaje con `Path=/api/auth` y la comprobación de mismo sitio (Q14) siga valiendo sin CORS.
2. **R2 Servidor WSGI.** En producción la app debe correr con gunicorn (trabajadores e hilos fijados, tiempos de espera, sin `--reload`), nunca con el servidor de Flask, como usuario sin privilegios.
3. **R3 Configuración segura.** Con `ENVIRONMENT=production` la app debe exigir HTTPS (cookies `Secure`, HSTS), `SECRET_KEY` fuerte y `TRUSTED_PROXY_HOPS` ≥ 1 detrás del proxy de la plataforma (si es 0 en producción, avisa al arrancar; deuda (e)). Ningún secreto en el repo, la imagen ni los registros.
4. **R4 Cabeceras.** Toda respuesta debe llevar `Content-Security-Policy` estricta (solo el propio origen; `blob:` para las descargas), `X-Content-Type-Options`, `Referrer-Policy`, `X-Frame-Options`/`frame-ancestors 'none'` y `Permissions-Policy` con `camera=(self)`; los archivos de la web con huella, caché larga e inmutable; `index.html`, sin caché.
5. **R5 Base en Supabase (C8).** La app debe conectarse con un rol propio sin `SUPERUSER` ni `BYPASSRLS`, distinto del que migra, con TLS; la API pública de Supabase y sus claves no se usan. Las pruebas de RLS y permisos deben pasar contra una base con los roles de Supabase.
6. **R6 Migraciones y despliegue.** GitHub Actions debe poder, a pedido del humano y con aprobación del entorno `production`, correr las pruebas y aplicar `alembic upgrade head` con el rol migrador; el paso de desplegar la imagen se conecta cuando se decida la plataforma (Q1). Si un paso falla, se detiene. Las migraciones existentes ya bajan (`downgrade`); la guía dice cuándo usarlo.
7. **R7 Salud.** La plataforma debe comprobar `/api/ready` (la base responde) antes de enviar tráfico a una versión nueva.
8. **R8 Guía.** Debe existir `docs/09-despliegue.md` con: cuentas, variables y dónde guardarlas, creación de roles, primer despliegue, crear el tenant y el primer admin, respaldo y restauración, rotación de secretos y cómo volver a la versión anterior.

## Criterios de aceptación

- A1: pruebas: rutas de la SPA devuelven `index.html`; `/api/*` llega a la API; un archivo inexistente de `/assets` es `404`; cookie con `Path=/api/auth`; cabeceras de R4 en web y API; aviso de `TRUSTED_PROXY_HOPS=0` en producción.
- A2: el contenedor de producción se construye en CI y arranca con gunicorn; prueba de humo (`/api/ready`, `index.html`, login) contra él.
- A3: las pruebas de RLS y permisos pasan contra una base con roles como los de Supabase (migrador no superusuario, rol de app sin `BYPASSRLS`).
- A4: navegador real contra el contenedor de producción (no Vite): login, escaneo manual, cierre e informe, exportar; CSP sin violaciones en consola; axe 0.
- A5: guía completa revisada; el humano puede desplegar siguiéndola sin pasos implícitos.

## Decisiones ya tomadas

ADR-001 (Flask único backend, RLS obligatoria, rol de app sin `BYPASSRLS`), ADR-002 (solo en línea), T10 parcial (base y fotos en Supabase, sin Supabase Auth ni su API), HTTPS obligatorio por la cámara, uv para dependencias, despliegue desde GitHub Actions (`docs/02`), flujo git (`main` solo lo pasa el humano).

## Riesgos

- **Pausa de la base por inactividad** (Supabase Free pausa tras 7 días sin uso): el conteo es anual; la app quedaría caída entre conteos. Ver Q2.
- **Conexión desde la plataforma a Supabase:** la conexión directa de Supabase puede ser solo IPv6; se usa su *pooler* en modo sesión (IPv4), compatible con las variables de sesión que usa el RLS.
- **Arranque en frío** en plataformas que apagan el servicio: el primer escaneo del día tarda.
- **Secretos:** los gestiona el humano en la plataforma y en GitHub; Claude no los lee ni los escribe.

## Decisiones de G1 (humano, 2026-11-15)

| Pregunta | Decisión |
|---|---|
| Q1 Plataforma (T10) | **Pendiente**: el humano la revisa. La spec no elige plataforma: la imagen, las migraciones y la guía sirven para cualquiera que ejecute un contenedor con HTTPS delante; el paso «desplegar» de GitHub Actions y la sección de la plataforma en la guía se completan cuando se decida (cambio de alcance pequeño). |
| Q2 Plan de Supabase | **Free.** Riesgo aceptado: el proyecto se pausa tras 7 días sin uso y hay que reactivarlo a mano antes de cada conteo; no hay copias garantizadas, así que la guía pide un respaldo manual (`pg_dump`) antes y después de cada conteo y lo deja como paso obligatorio del cierre. Revisable si el piloto lo muestra. |
| Q3 Web | Un solo contenedor: gunicorn sirve la web en `/` y la API bajo `/api`. |
| Dependencia | `gunicorn==27.0.1` aprobada. |

## Opciones que se presentaron en G1

| Pregunta | Opciones | Recomendación |
|---|---|---|
| Q1 Dónde se aloja la API y la web (T10) | A: **Render**, servicio web con Docker (HTTPS y dominio `*.onrender.com` incluidos, despliegue por *deploy hook*; desde US$7/mes por 512 MB, julio 2026; sin región en Sudamérica). B: **VPS** (p. ej. Hetzner CX23, desde ~€4–6/mes) con Docker Compose y Caddy para HTTPS; parches del sistema, firewall y respaldos a cargo de ustedes. C: **Google Cloud Run** (capa gratuita mensual; São Paulo es región de precio Tier 2); se apaga sin tráfico (arranque en frío) y la configuración de GCP es más larga. | **A.** Para una clínica y una persona de TI, que la plataforma se encargue de TLS, parches y reinicios vale más que el ahorro de un VPS; el costo es predecible. Supabase y Render se crean en regiones del este de EE. UU., cerca entre sí y de Colombia. |
| Q2 Plan de Supabase | A: **Pro** (US$25/mes): sin pausa por inactividad y con copias diarias. B: **Free**: pausa tras 7 días sin uso y hay que reactivarlo a mano; sin copias garantizadas. | **A.** Un conteo al año deja semanas sin uso: con Free la app aparece caída justo cuando se necesita, y los datos de la clínica quedan sin copia. |
| Q3 Cómo se sirve la web | A: **Un solo contenedor**: gunicorn sirve la web compilada en `/` y monta la API bajo `/api` (mismo origen, sin CORS ni reescrituras). B: la web como sitio estático aparte (CDN) con reescritura de `/api` hacia la API. C: Caddy + gunicorn en el mismo contenedor. | **A.** Una sola pieza que desplegar y probar; el mismo origen mantiene la cookie y la defensa CSRF tal cual. B y C suman piezas sin beneficio para ~300 activos. |
