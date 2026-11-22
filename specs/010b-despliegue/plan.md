# Plan 010b — Despliegue

> **Estado:** Aprobado (G1–G3, 2026-11-15) con Q1 pendiente, Q2 = Supabase Free y Q3 = un solo contenedor (`spec.md`). §5 queda independiente de la plataforma.

## 1. Enfoque

Primero la app lista para producción (mismo origen, gunicorn, cabeceras, configuración), probada aquí sin Docker; después la imagen de producción construida y probada en CI, los roles de Supabase (C8) y el flujo de GitHub Actions; al final la guía y la verificación en navegador contra el contenedor de producción. Claude no crea cuentas, no ve secretos y no hace `push` a `main`: deja todo listo y la guía para el humano.

## 2. App de producción (T1–T2)

- **`app/wsgi.py`** (`create_wsgi_app`): `DispatcherMiddleware` con la API Flask bajo `/api` y una app WSGI mínima de estáticos para `web/dist` (`index.html` para rutas sin extensión fuera de `/api`; `/assets/*` con `Cache-Control: public, max-age=31536000, immutable`; `index.html` con `no-cache`; `404` para archivos que no existen). Sin dependencias nuevas (Werkzeug ya está).
- **Cookie de refresh:** su `path` sale de `request.script_root + "/auth"` (bajo `/api` → `/api/auth`); en desarrollo, sin prefijo, sigue `/auth` (el proxy de Vite la reescribe como hoy).
- **Cabeceras de seguridad** (`app/seguridad.py`, para API y estáticos): CSP `default-src 'self'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'` (se ajusta tras medir la web real en T6), `Referrer-Policy: same-origin`, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Permissions-Policy: camera=(self), microphone=(), geolocation=()`, y HSTS solo con `ENVIRONMENT=production`.
- **Configuración:** aviso al arrancar con `ENVIRONMENT=production` y `TRUSTED_PROXY_HOPS=0`; `DATABASE_URL` de producción exige `sslmode=require` (o más estricto).
- **gunicorn** (`backend/gunicorn.conf.py`): `bind 0.0.0.0:$PORT`, 2 trabajadores × 4 hilos (semáforo de Argon2 de 4, spec 002), `timeout 30`, `graceful_timeout 20`, registros a stdout sin cuerpos, `forwarded_allow_ips` según la plataforma. Dependencia nueva: **`gunicorn`** con versión fijada (la anticipa la deuda (b) de la 002).

## 3. Imagen y CI (T3)

- **`Dockerfile.prod`** (en la raíz): etapa Node (`npm ci && npm run build` de `web/`) → etapa Python (uv `--frozen --no-dev`, sin compilador) que copia `backend/` y `web/dist`; usuario sin privilegios; `HEALTHCHECK` contra `/api/ready`; `CMD gunicorn`.
- **CI (`ci-imagen.yml`)**: construye la imagen en cada PR a `develop`/`main`, la arranca con un PostgreSQL de servicio y hace la prueba de humo (A2).

## 4. Base en Supabase (T4, C8)

- **`backend/app/cli.py` → `flask crear-rol-app`**: crea (o actualiza la contraseña de) el rol de la aplicación con `NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE LOGIN`, le da `CONNECT`/`USAGE` y deja que las migraciones pongan los `GRANT` de siempre. Lo ejecuta el humano con el rol `postgres` de Supabase; la contraseña la lee de una variable, nunca de un argumento.
- **Prueba C8:** una variante de la base de pruebas donde el migrador **no** es superusuario (como `postgres` en Supabase) corre `alembic upgrade head` y las pruebas de RLS y permisos (A3).
- **Conexión:** pooler de Supabase en modo sesión, `sslmode=require`; la guía explica por qué no el modo transacción.

## 5. Migraciones desde GitHub Actions (T5)

- **`migrar.yml`** (`workflow_dispatch`, entorno `production` con aprobación del humano): pruebas del backend → `alembic upgrade head` con `MIGRATION_DATABASE_URL` (secreto del entorno) → `alembic current` en el resumen. No despliega.
- **Desplegar:** pendiente de Q1. Queda anotado en la guía qué necesita cualquier plataforma (imagen `Dockerfile.prod`, puerto `$PORT`, salud `/api/ready`, variables, HTTPS delante, `TRUSTED_PROXY_HOPS`) y el paso de despliegue se añade cuando se elija.

## 6. Guía y verificación (T6)

- **`docs/09-despliegue.md`** (R8) y `.env.example` con las variables de producción.
- **Navegador real** contra el contenedor de producción levantado aquí con gunicorn + `web/dist` (sin Vite): login, escaneo manual, cierre, informe, exportar, Inicio; cabeceras y CSP sin violaciones; axe 0. Revisión de seguridad (secretos, cabeceras, roles, cookie) y de dominio (nada cambia en los cálculos).
