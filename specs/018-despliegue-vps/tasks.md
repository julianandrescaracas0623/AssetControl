# Tasks 018 — Despliegue en VPS con Coolify

Diez tareas, cada una ≤ 1 día. «Humano» = cuentas, DNS, secretos, SSH o panel de Coolify (el implementer no accede). «Implementer» = código y docs con tests primero. Revisiones: `reviewer` y `security-reviewer` en T1 y T2 (cabeceras, apagado); `reviewer` en T9. Las tareas del humano se cierran con evidencia pegada (sin secretos).

## T1 — Cabeceras `no-referrer` y `no-store` en páginas sensibles (implementer, ejecutable)

- **Resultado:** `/restablecer`, `/invitacion`, `/cambiar-contrasena`, `/plataforma/**` y el *fallback* de `index.html` responden `Referrer-Policy: no-referrer` y `Cache-Control: no-store`; `/assets/*` y `/api/**` sin cambios. Pruebas escritas primero.
- **Archivos probables:** `backend/app/wsgi.py`, `backend/tests/test_wsgi_cabeceras.py` (o el archivo de pruebas de `wsgi` existente).
- **Verificación:** `cd backend && uv run pytest tests/test_wsgi_cabeceras.py -q && uv run pytest -q && uv run ruff check .`
- **Dependencia:** ninguna.
- **Cubre:** R1–R3, A1.
- **Estado:** HECHA (2026-11-27), con revisión del reviewer y del security-reviewer; falta repetir A3 en los entornos reales (humano). Riesgo conocido: riesgo R12 de la spec (`Origin: null`), seguimiento en T10 (hecho en T10, 2026-11-27).

## T2 — `worker_exit` con `Correo.esperar` (implementer)

- **Resultado:** `backend/gunicorn.conf.py` define `worker_exit` que espera los envíos de correo con un plazo menor que `graceful_timeout`; no falla sin correo configurado. Prueba con doble de `Correo`.
- **Archivos probables:** `backend/gunicorn.conf.py`, `backend/tests/test_gunicorn_conf.py`.
- **Verificación:** `cd backend && uv run pytest tests/test_gunicorn_conf.py -q && uv run ruff check .`
- **Dependencia:** ninguna (en paralelo con T1 solo si el implementer lo decide; una tarea a la vez).
- **Cubre:** R4, A2.
- **Estado:** HECHA (2026-11-27), con revisión del reviewer y del security-reviewer; falta (humano) el plazo de parada ≥ 25 s en Coolify en los dos entornos y una prueba de apagado real con un correo en curso contra un SMTP de pruebas.

## T3 — Cuentas y proyectos Supabase, y DNS (humano)

- **Resultado:** dos proyectos Supabase Free en São Paulo (`pruebas`, `produccion`), cada uno con API de datos apagada, bucket privado `fotos`, conexión S3 y llaves S3, y contraseña de `postgres` en el gestor; `SECRET_KEY` y `APP_DB_PASSWORD` distintos por entorno (docs/09 §2–§3). Registros DNS `A` de `pruebas.<dominio>`, `app.<dominio>` y del subdominio del panel de Coolify hacia <IP-del-VPS>.
- **Archivos probables:** ninguno (cuentas y paneles).
- **Verificación:** `nslookup pruebas.<dominio>` devuelve <IP-del-VPS> (ídem `app` y panel); en cada proyecto, *Data API* apagada y bucket `fotos` privado; evidencia anotada.
- **Dependencia:** P1 (nombre del dominio) respondida.
- **Cubre:** R5 (parte), A9 (parte).
- **Estado:** HECHA por el humano (confirmado el 2026-11-27).

## T4 — Endurecer el VPS (humano)

- **Resultado:** SSH solo con llaves y sin login de `root`, `fail2ban`, NTP sincronizado, reinicio hecho; dominio HTTPS para el panel de Coolify y `:8000` y `:8080` cerrados desde fuera; `renombrador-eps` sigue respondiendo. Pasos del plan, sección «Plan del VPS».
- **Archivos probables:** ninguno (servidor y panel de Coolify).
- **Verificación:** desde otra red: `curl -m 5 http://<IP-del-VPS>:8000` y `:8080` fallan; `ssh -o PubkeyAuthentication=no <usuario>@<IP-del-VPS>` rechazado; `ssh root@<IP-del-VPS>` rechazado; en el VPS `timedatectl` y `systemctl status fail2ban`; el panel abre por `https://<panel>.<dominio>`; `renombrador-eps` responde (A5, A6).
- **Dependencia:** T3 (DNS del panel); P9 respondida.
- **Cubre:** R8, R15, A5, A6.
- **Estado:** HECHA por el humano (confirmado el 2026-11-27).

## T5 — Preparar y migrar «pruebas» (humano)

- **Resultado:** el proyecto Supabase de pruebas tiene roles, migraciones hasta `head` y una empresa ficticia con su enlace de invitación (docs/09 §4). `MIGRATION_DATABASE_URL` solo en la ventana de PowerShell, cerrada al terminar.
- **Archivos probables:** ninguno.
- **Verificación:** `uv run alembic current` muestra `0032_plataforma_password_usuario (head)`; `preparar-roles` sin errores; verificación de que el servidor y Coolify no contienen `MIGRATION_DATABASE_URL`.
- **Dependencia:** T3; T1 y T2 ya en `develop` (la 0026 va antes del código nuevo).
- **Cubre:** R12, R13, R14.
- **Estado:** HECHA por el humano (confirmado el 2026-11-27).

## T6 — Aplicación «pruebas» en Coolify (humano)

- **Resultado:** aplicación `Dockerfile.prod` desde `develop`, dominio `pruebas.<dominio>`, puerto 8000, healthcheck `/api/ready`, variables y secretos del plan; `PLATAFORMA_HABILITADA` según P2 (con restricción por red si se activa); `CORREO_MODO` sin definir mientras P3 esté abierta.
- **Archivos probables:** ninguno (panel de Coolify).
- **Verificación:** `curl -s https://pruebas.<dominio>/api/ready` devuelve `{"status":"ok"}`; `http://` redirige a `https://`; `curl -sI https://pruebas.<dominio>/restablecer` (e `/invitacion`, `/cambiar-contrasena`, `/plataforma/entrar`, `/login`, una ruta con mayúsculas como `/RESTABLECER` y una ruta inexistente) muestra las cabeceras de T1; el registro de arranque no avisa `TRUSTED_PROXY_HOPS=0`.
- **Dependencia:** T1, T2, T4, T5.
- **Cubre:** R5, R6, R7, A3, A4.
- **Estado:** HECHA por el humano (confirmado el 2026-11-27); la comprobación de las cabeceras de T1 (A3) se repite al cerrar T1.

## T7 — Comprobaciones reales en «pruebas» (humano)

- **Resultado:** cookie de plataforma, tope del logo, IP de cliente en el límite de tasa y aislamiento de tokens comprobados y anotados; medición de memoria con ambos entornos y `renombrador-eps`. Si falla algo, se documenta y se convierte en cambio (`/sdd-change`), no se parchea a mano.
- **Archivos probables:** notas en este `tasks.md` (sin secretos).
- **Verificación:** flujo de `docs/09` §5.2 completo con datos ficticios (necesita P2 = sí en pruebas); en las herramientas del navegador la cookie de refresh sale con `Path=/api/plataforma/auth` y recargar conserva la sesión; subir un logo de 2 MB funciona y uno mayor de 2 MB + 64 KB responde `413`; tres logins fallidos desde dos redes se cuentan por IP distinta; `docker stats` o el panel de Coolify con memoria libre razonable (R4).
- **Dependencia:** T6.
- **Cubre:** R9, R10, R11, A7, A9, R4 (medida).
- **Estado:** HECHA por el humano (confirmado el 2026-11-27).

## T8 — Producción (humano)

- **Resultado:** proyecto Supabase de producción preparado y migrado (con respaldo previo), aplicación de Coolify en `main` con despliegue **manual** en `app.<dominio>`, variables y secretos propios; `/plataforma` apagada; primer `create-tenant` real solo cuando el humano decida el piloto.
- **Archivos probables:** ninguno.
- **Verificación:** `https://app.<dominio>/api/ready` 200; cabeceras de T1 en `https://app.<dominio>/restablecer`; `https://app.<dominio>/plataforma` y `/api/plataforma/auth/login` responden `404`; un token de «pruebas» no abre sesión en producción (A8, A9); el servidor y Coolify no tienen `MIGRATION_DATABASE_URL` (solo existe como secreto del entorno `production` de GitHub, para `migrar.yml`).
- **Dependencia:** T7 sin hallazgos abiertos; `main` con la CI en verde (la integración a `main` la hace el humano).
- **Cubre:** R5, R6, R7, R9, R12, R13, A4, A8, A9.
- **Estado:** HECHA por el humano (confirmado el 2026-11-27); la comprobación de las cabeceras de T1 (A3) se repite al cerrar T1.

## T9 — Respaldo, documentación y cierre (implementer + humano)

- **Resultado:** (humano) un `pg_dump` de cada proyecto guardado fuera del repo (docs/09 §8) y, según P7, ensayo de restauración en pruebas con datos ficticios; (implementer) `docs/09-despliegue.md` actualizado: sección 6 con los pasos de Coolify y el VPS, secciones 3 y 5 con región São Paulo y los dos entornos, 5.1 y 5.2 sin los pendientes ya resueltos (cabeceras, `worker_exit`, cookie, tope), sección 7 con «migrar desde la PC antes del despliegue manual», sección 11 con lo que no se hace en el VPS; si P6 resulta afirmativa por parte del humano, se anota la opción sin costos. `MEMORY.md` actualizado.
- **Archivos probables:** `docs/09-despliegue.md`, `MEMORY.md`, `specs/018-despliegue-vps/tasks.md`.
- **Verificación:** `git diff --stat docs/09-despliegue.md` solo toca ese archivo en `docs/`; búsqueda `Grep "Pendiente de la spec de despliegue" docs/` sin resultados; `pg_dump` genera archivos con tamaño > 0 (humano); revisión del `reviewer`.
- **Dependencia:** T8 (y T7 para las comprobaciones reales).
- **Cubre:** A10, A11, P7.
- **Estado:** documentación hecha (2026-11-27); falta del humano: pg_dump de cada proyecto y ensayo de restauración.

## T10 — `referrerPolicy: 'strict-origin'` en el cliente de la API web (implementer)

> No confundir con la pregunta T10 de `docs/05` (elección de plataforma, P8).

- **Resultado:** los `fetch` de `web/src/lib/api/cliente.ts` envían `referrerPolicy: 'strict-origin'`, de modo que los POST del mismo origen llevan un `Origin` real aunque el documento tenga `Referrer-Policy: no-referrer`; refresh, logout, recuperar y restablecer (y los de la consola) dejan de responder 403 en navegadores sin `Sec-Fetch-Site` (riesgo R12). El servidor no cambia ni acepta `Origin: null`. Pruebas escritas primero.
- **Archivos probables:** `web/src/lib/api/cliente.ts` y su prueba.
- **Verificación:** `cd web && npm test && npm run lint && npm run typecheck`
- **Revisiones:** `reviewer` y `security-reviewer`.
- **Dependencia:** T1.
- **Cubre:** riesgo R12 de la sección «Riesgos» de la spec (no el requisito R12).
- **Estado:** HECHA (2026-11-27), con revisión del reviewer y del security-reviewer; falta (humano) comprobar en un navegador real, en pruebas, con DevTools, que el POST a `/api/auth/refresh` desde `/restablecer#…` y desde `/app/…` lleva `Origin` real y `Referer` solo con el origen, y que el logout devuelve 204.

## Pendiente del humano (fuera de las tareas)

- Registrar la decisión de T10 en `docs/05` y, si quiere, un ADR de plataforma (P8).
- TOTP para `/plataforma` antes de habilitarla en producción (P4) y proveedor SMTP con dominio verificado (P3): specs aparte.
- Contraseñas largas y únicas para el panel de Coolify y las cuentas de desarrollador.
- Plazo de parada del contenedor ≥ 25 s en Coolify (pruebas y producción); comprobar con `docker inspect` (StopTimeout).
