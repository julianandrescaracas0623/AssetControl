# Tasks 010b — Despliegue

> **Estado:** Aprobadas (G1–G3, 2026-11-15); T5 sin plataforma (Q1 pendiente). Una tarea ≤ 1 día, pruebas primero, revisión y commit por tarea. Plan en `plan.md`.

| Tarea | Resultado | Verificación | Depende de |
|---|---|---|---|
| T1 | `app/wsgi.py`: API bajo `/api`, estáticos de la SPA, cookie con `Path=/api/auth`; cabeceras de seguridad | backend: `pytest`, `ruff` | aprobación |
| T2 | Configuración de producción (aviso de proxy, TLS en la URL) y gunicorn fijado con su configuración | igual que T1 | T1 |
| T3 | `Dockerfile.prod` y CI que construye la imagen y hace la prueba de humo | CI en GitHub (aquí no hay Docker) | T2 |
| T4 | `flask crear-rol-app` y prueba C8 con migrador no superusuario | igual que T1 | aprobación |
| T5 | `migrar.yml` (pruebas → migrar, a pedido y con aprobación); requisitos de cualquier plataforma en la guía | revisión; `actionlint` si está | T3 |
| T6 | `docs/09-despliegue.md`, `.env.example`; navegador real contra gunicorn + `web/dist`; revisión de seguridad y dominio | skill `browser-qa` | T1–T5 |

## Notas por tarea
- **T1 (hecha, 2026-11-15):** `app/wsgi.py`: `crear_wsgi(api, dist, produccion)` = `DispatcherMiddleware` (web en `/`, API Flask en `/api`) envuelto en `ConCabeceras`. `Estaticos`: `/assets/*` con caché inmutable y `404` si falta (nunca HTML para un script), archivos de la raíz con caché corta y `404` para extensiones estáticas inexistentes, cualquier otra ruta (también `/admin/activos/AC.01`) → `index.html` sin caché; solo `GET`/`HEAD`; `safe_join` contra rutas fuera de `dist`; falla clara si no hay `index.html`. Cabeceras en web y API: CSP (`'self'`, `blob:`/`data:` donde hace falta, `frame-ancestors 'none'`, sin `unsafe-eval`), `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`, `Permissions-Policy` con `camera=(self)`, COOP; HSTS solo en producción. La cookie de refresh toma el prefijo de `SCRIPT_NAME`: `Path=/api/auth` en producción, `/auth` en desarrollo. `application` se crea al pedirlo (gunicorn), no al importar. `test_wsgi.py` (8).
- **T2 (hecha, 2026-11-15):** TLS a la base fuera de desarrollo y pruebas (`app/db.py`, `_tls`): sin `sslmode` en la URL se exige `require`; `verify-ca`/`verify-full` se respetan; `disable`/`allow`/`prefer` detienen el arranque sin mostrar la URL. Aviso al arrancar con `ENVIRONMENT=production` y `TRUSTED_PROXY_HOPS=0` (deuda (e) de la 002). `gunicorn==27.0.1` y `backend/gunicorn.conf.py`: `app.wsgi:application` en `$PORT`, 2 procesos × 4 hilos `gthread` (semáforo de Argon2 de 4), `timeout 30`, sin recarga ni `preload` (el engine no se comparte entre procesos), reciclaje de procesos, registro de accesos sin consultas ni cuerpos y con el ID de petición. `test_produccion.py` (11); la prueba de la cookie por entorno aísla la regla de TLS (la base local no tiene TLS). Prueba de humo aquí con gunicorn + `web/dist`: `/`, `/api/health`, ruta de la SPA con punto, `404` de un asset inexistente y cabeceras.
