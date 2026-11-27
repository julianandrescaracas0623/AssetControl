# Spec 018 — Despliegue en VPS con Coolify (pruebas y producción)

> Estado: en ejecución. El humano ejecutó T3–T8 (confirmado el 2026-11-27); G1–G3 aprobadas por el humano el 2026-11-27; el despliegue en VPS con Coolify está activo en pruebas y producción. Pendientes: T10 (código), el plazo de parada ≥ 25 s en Coolify, la repetición de A3 en los entornos reales y la parte del humano de T9 (respaldo). Redactada por el planner el 2026-11-21. Cierra la parte de plataforma de T10 de `docs/05` y los pendientes del riesgo R1 de la spec 017 y de la spec 014. Decisiones del humano de hoy: ver «Alcance».

## Problema

AssetControl no tiene dónde ejecutarse fuera de la PC de desarrollo. `docs/09-despliegue.md` deja la plataforma «pendiente (Q1)» y acumula pendientes de despliegue: cabeceras `no-referrer`/`no-store` en páginas con enlaces de un solo uso, `worker_exit` con `Correo.esperar`, tope del logo, cookie de refresh de plataforma bajo `/api`, `/plataforma` expuesta (R1) y NTP. Además el VPS elegido tiene hallazgos de seguridad abiertos (panel de Coolify en `http://IP:8000`, dashboard de Traefik en `:8080`, SSH por contraseña con root). Sin esto **no se puede ir al piloto** (R1 de la 017).

## Usuarios

- **Humano/operador (dueño del proyecto):** crea cuentas, DNS, secretos, configura Coolify y el VPS, migra y aprueba el paso a producción.
- **Implementer:** cabeceras, gunicorn y documentación, con pruebas.
- **Personas de la clínica (admin/contador):** usan la web en `app.<dominio>`; no ven nada de esto salvo disponibilidad y HTTPS.

## Alcance

### Incluye

- **Plataforma:** VPS Hostinger KVM 2 (2 vCPU, 8 GB, 100 GB, Ubuntu 24.04, Campinas, IPv4 <IP-del-VPS>) que ya tiene Coolify 4.7.6 con Traefik v3.7 en 80/443 y otra app (`renombrador-eps`). Se usa el Traefik de Coolify para TLS y enrutado; **no** se instala Caddy ni nginx propios.
- **Dos entornos en el mismo VPS:**
  - «pruebas»: rama `develop`, `pruebas.<dominio>`, datos solo ficticios.
  - «producción»: rama `main`, `app.<dominio>`, **despliegue manual** (sin auto-deploy).
  - `<dominio>` es un marcador: el nombre real se pide al humano después y no se escribe en el repo.
- **Dos proyectos Supabase Free separados**, región São Paulo (`sa-east-1`), cada uno con su `preparar-roles`, `SECRET_KEY`, llaves S3 y bucket privado `fotos`.
- **Imagen:** `Dockerfile.prod` desde la raíz del repo; `PORT=8000`; healthcheck `/api/ready`; `TRUSTED_PROXY_HOPS=1`; `ENVIRONMENT=production` en ambos entornos.
- **Seguridad del VPS:** panel de Coolify con dominio y HTTPS y cierre de `:8000` y `:8080` (Docker salta `ufw`, así que se cierra con la configuración de Coolify/Traefik y se comprueba desde fuera); SSH solo con llaves (`PasswordAuthentication no`, sin login de `root`), `fail2ban`, sincronización de hora (NTP) y reinicio pendiente del kernel.
- **Pendientes de R1 y de la 014 (código, con pruebas):**
  - `Referrer-Policy: no-referrer` y `Cache-Control: no-store` en `/restablecer`, `/invitacion`, `/cambiar-contrasena`, `/plataforma/**` y en el *fallback* de `index.html` de la SPA.
  - `worker_exit` en `backend/gunicorn.conf.py` que llama a `Correo.esperar` con un plazo menor que `graceful_timeout = 20`.
- **Pendientes de R1 (comprobación en el entorno real):** cookie de refresh `Path=/plataforma/auth` llega como `/api/plataforma/auth` y la sesión de la consola sobrevive a recargar; tope de cuerpo del logo (2 MB + 64 KB) sin que el proxy lo corte; `/plataforma` apagada o restringida por red.
- **Migraciones:** desde la PC del humano (sección 4 de `docs/09`), **antes** de desplegar el código (0026 antes del ORM nuevo); `MIGRATION_DATABASE_URL` nunca en el VPS ni en Coolify. `migrar.yml` se mantiene sin cambios.
- **Respaldo:** `pg_dump` manual de `docs/09` §8 para ambos proyectos; se evalúa qué aporta el VPS (ver Preguntas abiertas) sin asumir costos.
- **Documentación:** actualizar `docs/09-despliegue.md` (secciones 3, 5.1, 5.2, 6, 7, 11) con los pasos reales y las comprobaciones hechas.

### No incluye

- Cambios de dominio, esquema, auth, roles, precios ni migraciones nuevas.
- Segundo factor (TOTP) para `/plataforma`: sigue siendo decisión previa al piloto (spec 017).
- Edición de `docs/adr/` (el ADR de plataforma lo escribe el humano si lo desea) ni de `docs/05` (el humano registra la decisión de T10).
- Caddy/nginx propios, Docker Compose de producción propio, orquestadores, colas, CI/CD de despliegue automático a producción, monitoreo con terceros, alta disponibilidad.
- Mover o tocar la app `renombrador-eps` (solo se verifica que no se afecte).
- Importar datos reales a «pruebas».
- Proveedor SMTP real y dominio verificado (SPF/DKIM): sin ellos la recuperación de contraseña queda **desactivada** (`CORREO_MODO` sin definir), ver P3.

## Requisitos (EARS)

1. Cuando una petición `GET` pide `/restablecer`, `/invitacion`, `/cambiar-contrasena`, `/plataforma` o `/plataforma/**` (existan o no como archivo), el sistema debe responder con `Referrer-Policy: no-referrer` y `Cache-Control: no-store`.
2. Cuando una petición `GET` cae en el *fallback* de la SPA (`index.html`) en cualquier ruta, el sistema debe responder con `Referrer-Policy: no-referrer` y `Cache-Control: no-store`; los archivos con huella (`/assets/*`) conservan su caché y `same-origin`.
3. Mientras la respuesta lleve las cabeceras de 1 y 2, el sistema debe conservar las demás (CSP, HSTS en producción, `X-Frame-Options`, `Permissions-Policy`) sin cambios y las respuestas de `/api/**` no deben cambiar.
4. Cuando gunicorn recibe la señal de apagado y un proceso termina, el sistema debe esperar los envíos de correo en curso con `Correo.esperar` durante un plazo menor que `graceful_timeout` (20 s) y no bloquear el apagado más allá de ese plazo ni fallar si no hay correo configurado.
5. Cuando se despliega en cualquiera de los dos entornos, el sistema debe arrancar con `ENVIRONMENT=production`, `ALMACEN=s3`, `TRUSTED_PROXY_HOPS=1`, `DATABASE_URL` de su propio proyecto Supabase y `SECRET_KEY` y llaves S3 propios; ningún secreto se comparte entre pruebas y producción.
6. Cuando se solicita `https://pruebas.<dominio>/api/ready` o `https://app.<dominio>/api/ready`, el sistema debe responder `200 {"status":"ok"}` por HTTPS con certificado válido de Traefik.
7. Cuando se solicita `http://` a cualquiera de los dominios, el sistema debe redirigir a `https://`.
8. Cuando se intenta alcanzar `http://<IP-del-VPS>:8000`, `http://<IP-del-VPS>:8080` o el puerto 22 con contraseña desde fuera, el sistema no debe permitirlo (conexión rechazada o autenticación por llaves solamente).
9. Cuando `PLATAFORMA_HABILITADA` no está definida, `/plataforma` y `/api/plataforma` deben responder `404`. Cuando se habilita en un entorno, solo debe ser alcanzable desde redes permitidas definidas en Traefik/Coolify o por `PLATAFORMA_REDES_PERMITIDAS` (respaldo).
10. Cuando el administrador de plataforma inicia sesión en `/plataforma/entrar` en el entorno real habilitado y recarga la consola, el sistema debe conservar la sesión (la cookie de refresh se envía a `/api/plataforma/auth/refresh`).
11. Cuando se sube un logo de 2 MB a `POST /api/plataforma/empresas/<id>/logo` por el dominio real, el sistema debe aceptarlo; uno mayor de 2 MB + 64 KB debe rechazarse con `413` sin que el proxy lo corte con otro error; cualquier otro cuerpo de `/plataforma` mayor de 4 KB responde `413`.
12. Cuando se despliega código con una migración nueva, la migración debe ejecutarse **antes** desde la PC del humano y el despliegue de producción debe iniciarse a mano solo después de eso, desde `main` con la CI en verde.
13. Cuando se revisa la configuración del VPS y de Coolify, `MIGRATION_DATABASE_URL`, la contraseña de `postgres` de Supabase y cualquier secreto no deben aparecer en el servidor, en el repo ni en los registros.
14. Cuando se despliega «pruebas», debe contener solo datos ficticios; no se restaura en él ningún respaldo de producción.
15. Mientras el VPS esté en servicio, la hora de Flask y de PostgreSQL debe estar sincronizada (NTP activo en el VPS; Supabase la sincroniza por su cuenta) con una desviación menor de 60 s.

## Criterios de aceptación

- A1. Pruebas automáticas (backend) cubren R1–R3: cabeceras en las rutas listadas y en el *fallback*, sin regresión en `/assets/*` ni en `/api/**`. `uv run pytest` y `uv run ruff check .` en verde.
- A2. Prueba del `worker_exit` (R4): invoca `Correo.esperar` con plazo < 20 s, no falla sin correo y no excede el plazo.
- A3. `curl -sI https://pruebas.<dominio>/restablecer` muestra `Referrer-Policy: no-referrer` y `Cache-Control: no-store`; ídem con `/invitacion`, `/cambiar-contrasena`, `/plataforma/entrar` y una ruta inexistente.
- A4. `/api/ready` responde 200 por HTTPS en ambos dominios; `http` redirige a `https`.
- A5. Desde una red externa, `:8000` y `:8080` del VPS no responden; el panel de Coolify se abre solo por su dominio con HTTPS; `ssh` con contraseña o como `root` es rechazado; `fail2ban` activo; `timedatectl` muestra NTP sincronizado.
- A6. `renombrador-eps` sigue respondiendo igual después de cada cambio en Coolify/Traefik.
- A7. Prueba manual en «pruebas» (datos ficticios): flujo de `docs/09` §5.2 (desarrollador, empresa con logo real en S3, primer admin con cambio obligatorio, recarga de consola, desactivar y reactivar, Actividad) en verde; cookie con `Path=/api/plataforma/auth`; logo de 2 MB aceptado y de más de 2 MB + 64 KB rechazado con `413`.
- A8. Con `PLATAFORMA_HABILITADA` sin definir en «producción», `/plataforma` y `/api/plataforma` responden `404`.
- A9. Prueba humana de aislamiento: los dos proyectos Supabase tienen secretos distintos; un token de «pruebas» no abre sesión en «producción».
- A10. `docs/09` actualizado: sin textos «pendiente de la spec de despliegue» que ya estén resueltos; pasos de Coolify, orden migrar-antes-de-desplegar y respaldo.
- A11. Un `pg_dump` de cada proyecto se genera y se guarda fuera del repo según `docs/09` §8.

## Reglas de dominio

- No cambia ninguna regla de dominio (verificaciones, sesiones, precios, ubicaciones): es infraestructura.
- Aislamiento por tenant y roles siguen en servidor y base (RLS); el despliegue no los debilita: la app entra con el rol sin `BYPASSRLS`.
- Datos de la clínica: nunca en el repo, en los registros ni en «pruebas».
- Nada se borra: no hay `downgrade` que borre datos en producción sin respaldo previo (docs/09 §10).
- Los comandos de servidor se entregan como instrucciones al humano, sin secretos; el implementer no accede al VPS ni a Supabase.

## Riesgos

- **R1. Docker salta `ufw`:** cerrar puertos con `ufw` no basta para `:8000` y `:8080`. Mitigación: cerrarlos en la configuración de Coolify/Traefik (no publicar el puerto) y verificar desde una red externa (A5).
- **R2. Lockout de SSH** al desactivar contraseñas. Mitigación: probar la llave en una sesión **segunda** antes de cerrar la primera; usar la consola web de Hostinger como respaldo.
- **R3. Coolify cambia Traefik o el proxy** y deja `renombrador-eps` o AssetControl sin ruta. Mitigación: A6 tras cada cambio; no tocar la configuración global de Traefik más de lo necesario.
- **R4. Recursos compartidos (8 GB):** dos entornos + `renombrador-eps` + Coolify. Gunicorn usa 2 procesos × 4 hilos y Argon2 (19 MiB) por hilo. Mitigación: medir uso con ambos entornos activos; si aprieta, bajar `workers` en «pruebas» **[PENDIENTE: no se define aquí; es decisión del humano con la medida]**.
- **R5. Supabase Free se pausa tras 7 días sin uso** y no tiene copias garantizadas (riesgo aceptado en G1). «Pruebas» y «producción» se pausan por separado. Mitigación: respaldo manual y comprobación `/api/ready` antes de cada conteo.
- **R6. Cabeceras:** `Cache-Control: no-store` en el *fallback* de `index.html` evita caché del HTML, pero reduce la velocidad de carga de la SPA; los `/assets/*` con huella no se tocan. Se acepta.
- **R7. Tope del logo:** Traefik no impone un tope de cuerpo por defecto; el tope real lo aplica la app (413). Si Coolify o un middleware agrega uno menor, el logo falla. Mitigación: A7 lo comprueba; si hace falta, un middleware `buffering` con `maxRequestBodyBytes` solo para la ruta del logo (sección de Preguntas).
- **R8. `/plataforma` en el mismo dominio que la clínica:** una cuenta de desarrollador comprometida controla todas las empresas (R1 de la 017). Mitigación: apagada por defecto; restringida por red al habilitarla; sin TOTP todavía.
- **R9. Hora distinta entre Flask y PostgreSQL** rompe el acceso emitido tras un cambio de contraseña (más de 60 s). Mitigación: NTP en el VPS (R15 de esta spec).
- **R10. Auto-deploy de «pruebas» desde `develop`** puede desplegar una migración que aún no se aplicó. Mitigación: el humano migra «pruebas» primero (requisito R12); el despliegue de pruebas es el único con auto-deploy y falla de forma visible (`/api/ready`).
- **R11. `forwarded_allow_ips` de gunicorn** es `127.0.0.1` por defecto y el proxy llega desde la red Docker de Coolify. La IP del cliente la decide la app con `TRUSTED_PROXY_HOPS=1` (ProxyFix), no gunicorn; hay que comprobar en real que el límite de tasa ve la IP del cliente y no la de Traefik (T7).
- **R12. `Origin: null` con `no-referrer` (descubierto en la revisión de seguridad de T1):** con `Referrer-Policy: no-referrer` en todo el documento de la SPA, los POST del mismo origen envían `Origin: null`. `is_same_site_request` (`backend/app/auth/http.py`) los rechaza si además falta `Sec-Fetch-Site`, lo que pasa en Safari/iOS 16.0–16.3 y en Firefox anterior a la 90. Afecta a `/auth/refresh`, logout, recuperar y restablecer (`backend/app/auth/routes.py`) y al refresh y logout de la consola (`backend/app/plataforma/auth_routes.py`), que responden 403. Falla cerrado, sin abrir ninguna vía de CSRF; efecto lateral: en esos navegadores el logout no revoca el refresh token en el servidor. Riesgo bajo: en 2026 esas versiones casi no existen. El servidor no acepta `Origin: null`; los tokens de `/restablecer` e `/invitacion` viajan en el fragmento `#`, que nunca va en el `Referer`. **Decisión del humano (2026-11-27):** documentarlo ahora y corregirlo después con un cambio pequeño en la web: `referrerPolicy: 'strict-origin'` en los `fetch` de `web/src/lib/api/cliente.ts`, con revisión del `reviewer` y del `security-reviewer` (T10 de `tasks.md`).
- **R13. Plazo de parada de Docker frente a `graceful_timeout` (descubierto en la revisión de T2):** Docker y Coolify mandan SIGKILL 10 s después del SIGTERM, y ni `docker-compose.yml` ni `Dockerfile.prod` declaran `stop_grace_period`; con eso, `graceful_timeout = 20` y la espera de correo de 15 s (`PLAZO_CORREO_AL_APAGAR`) no llegan a cumplirse en el VPS. **Decisión del humano (2026-11-27):** el código queda igual y se amplía en Coolify, en pruebas y en producción, el plazo de parada a 25 s o más (`stop_grace_period` o el ajuste equivalente del servicio); se comprueba con `docker inspect` (`StopTimeout` ≥ 25). Si Coolify no lo permite, se vuelve a decidir. Límites aceptados en `docs/09` §5.1, «Apagado».

## Preguntas abiertas

- **[PENDIENTE] P1. Nombre real del dominio** (y si el DNS se administra en Hostinger u otro proveedor). No bloquea la redacción; bloquea T4/T6 (ejecución).
- **[PENDIENTE] P2. ¿Se habilita `/plataforma` en «pruebas»?** Propuesta: sí en pruebas (para ensayar con datos ficticios), restringida por red a la IP del humano; en «producción» apagada hasta decidir TOTP (P4). Requiere decisión del humano.
- **[PENDIENTE] P3. Proveedor SMTP, remitente y dominio verificado (SPF/DKIM)** para la recuperación de contraseña (spec 014). Hasta decidirlo, `CORREO_MODO` queda sin definir y la recuperación desactivada en ambos entornos. Es un costo y una decisión de producto/proveedor: no se asume.
- **[PENDIENTE] P4. TOTP para `/plataforma`** antes del piloto (de la spec 017). Esta spec no lo implementa; sin él, la consola no se habilita en producción.
- **[PENDIENTE] P5. Tope del logo en el proxy:** ¿basta con el tope de la app (413) o se quiere una defensa adicional en Traefik (middleware `buffering`)? Propuesta: basta la app si A7 pasa.
- **[PENDIENTE] P6. Respaldo:** ¿los *snapshots*/copias del VPS de Hostinger, si el plan los incluye o tienen costo, aportan algo? No protegen los datos (viven en Supabase, no en el VPS), solo la configuración de Coolify. **No se asume costo ni disponibilidad**; el humano revisa su panel. Mientras, el respaldo es el `pg_dump` manual de la sección 8.
- **[PENDIENTE] P7. Ensayo de restauración** de un respaldo en un proyecto aparte (pendiente desde la 010b). ¿Se hace dentro de esta spec usando el proyecto de «pruebas», o queda fuera? Propuesta: dentro, con datos ficticios.
- **[PENDIENTE] P8. Registro de la decisión de T10** en `docs/05` y, si el humano lo desea, un ADR de plataforma (`docs/adr/` es del humano; el planner no los edita).
- **[PENDIENTE] P9. Acceso al panel de Coolify:** ¿restringido por IP o solo por contraseña + dominio HTTPS? La decisión es del humano.
- **P10. ¿Se activan en Coolify los despliegues automáticos de «pruebas» al empujar a `develop`** (webhook de GitHub) o también manuales? Respondida por el humano el 2026-11-27: automático en cada push a `develop`; producción manual.

## Cumplimiento de la regla de autonomía (para el coordinator)

- (a) Se deriva de `docs/09`, `docs/01–03` y de las specs 014 y 017: sí. La elección de plataforma es decisión del humano de hoy, aún no escrita en `docs/05` (P8).
- (b) No contradice ADR ni constitución: sí (ADR-001/002: monolito, un contenedor, sin colas).
- (c) Sin preguntas abiertas de producto, dominio o precios: El coordinator no podía aprobarla (P1–P10 abiertas; bloqueaban P2, P3, P4, P6 y P9); la aprobó el humano el 2026-11-27. Siguen abiertas P1–P9.
- Los pasos con cuentas, DNS, secretos, SSH y panel de Coolify son siempre del humano.
