# Plan 018 — Despliegue en VPS con Coolify

## Arquitectura

```text
Navegador ──HTTPS──▶ Traefik v3.7 (Coolify, 80/443, TLS Let's Encrypt)
                       ├─ pruebas.<dominio> ─▶ contenedor AssetControl (develop)  :8000
                       ├─ app.<dominio>     ─▶ contenedor AssetControl (main)     :8000
                       ├─ <panel>.<dominio> ─▶ panel de Coolify (HTTPS)
                       └─ renombrador-eps (sin cambios)
contenedor: gunicorn (web en "/", API en "/api") ──TLS──▶ Supabase São Paulo (proyecto propio por entorno)
```

- Una aplicación de Coolify por entorno, tipo *Dockerfile*, repositorio GitHub, `Dockerfile.prod` en la raíz, puerto expuesto 8000, healthcheck `/api/ready`. Traefik es el único proxy; la app confía en un salto (`TRUSTED_PROXY_HOPS=1`).
- «pruebas»: rama `develop`. «producción»: rama `main`, sin auto-deploy, desplegada a mano tras migrar.
- Sin dependencias nuevas. Sin Compose propio de producción. `migrar.yml` y la CI siguen igual.
- Cabeceras: se resuelven en la app (`backend/app/wsgi.py`, `ConCabeceras`/`Estaticos`), no en Traefik, para que valgan en cualquier plataforma y se puedan probar en CI.
- Apagado: `worker_exit` en `backend/gunicorn.conf.py` llama `Correo.esperar(timeout)` con un plazo menor que 20 s (propuesta: 15 s; el valor definitivo lo fija el implementer con la API real de `Correo.esperar`).

## Tablas afectadas

Ninguna. No hay migraciones nuevas. El orden obligatorio es: migrar (PC del humano, `alembic upgrade head`, hoy `0029_plataforma_logo`) y luego desplegar.

## Endpoints

Sin endpoints nuevos ni cambios de contrato (`openapi.yaml` sin tocar). Cambian solo cabeceras de las páginas web `/restablecer`, `/invitacion`, `/cambiar-contrasena`, `/plataforma/**` y el *fallback* de `index.html`.

## Permisos y roles

- Sin cambios de roles de aplicación. `plataforma_owner` y `assetcontrol_app` se crean con `preparar-roles` en cada proyecto Supabase.
- Secretos por entorno en Coolify (variables marcadas como secretas): `DATABASE_URL`, `SECRET_KEY`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`. Nunca `MIGRATION_DATABASE_URL`.
- Variables no secretas: `ENVIRONMENT=production`, `PORT=8000`, `TRUSTED_PROXY_HOPS=1`, `ALMACEN=s3`, `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET=fotos`, `URL_PUBLICA` solo si se activa el correo. `PLATAFORMA_HABILITADA` sin definir salvo decisión P2.

## Plan del VPS (instrucciones para el humano, sin secretos)

1. **SSH:** crear usuario con `sudo`, instalar su llave pública, verificarla en una **segunda** sesión; luego en `/etc/ssh/sshd_config.d/`: `PasswordAuthentication no`, `PermitRootLogin no`; recargar `sshd`. Mantener abierta la primera sesión hasta confirmar.
2. **fail2ban** para `sshd`; **NTP:** `timedatectl` debe mostrar `System clock synchronized: yes` y `NTP service: active`.
3. **Actualizaciones y reinicio pendiente** (kernel): reiniciar en una ventana acordada y confirmar que Coolify, Traefik y `renombrador-eps` vuelven solos.
4. **Panel de Coolify:** asignar un dominio con HTTPS en *Settings → Instance's Domain*; cerrar `:8000` (puerto del panel) y `:8080` (dashboard de Traefik) desactivando su publicación en la configuración de Coolify/Traefik (no con `ufw` solamente: Docker lo salta). Verificar desde otra red (A5). Habilitar autenticación de dos pasos en Coolify si existe.
5. **Cortafuegos de Hostinger** (panel del VPS): permitir solo 22, 80 y 443 como capa adicional, si el panel lo ofrece. No se asume ni se promete costo.

## Estrategia de pruebas

- **Automática (implementer):** pruebas de cabeceras sobre `app.wsgi.application` (cliente de prueba WSGI) para cada ruta de R1/R2, sin regresión en `/assets/*`, `/api/**` ni en HSTS/CSP; prueba de `worker_exit` (con un `Correo` doble que registre `esperar(timeout)`, plazo < 20, sin correo configurado no falla). `uv run pytest` y `uv run ruff check .`.
- **Imagen:** `docker compose build api` / prueba de humo `imagen` de la CI siguen en verde.
- **Manual con evidencia (humano):** `curl -sI` (A3, A4), escaneo externo de puertos (A5), flujo `docs/09` §5.2 en «pruebas» (A7), `/plataforma` 404 en producción (A8), respaldo de ambos proyectos (A11). Las evidencias se anotan en `tasks.md` sin secretos.
- Verificar IP de cliente: con límite de tasa activo, tres logins fallidos desde dos redes distintas deben contarse por IP distinta (R11).

## Migraciones (procedimiento)

Por entorno, desde la PC del humano en una ventana nueva de PowerShell (docs/09 §4): `preparar-roles`, `alembic upgrade head`, `alembic current`, `create-tenant` con datos ficticios en pruebas. Producción: respaldo previo (§8), migrar, y solo entonces *Deploy* manual en Coolify. Revertir: retirar el código antes de cualquier `downgrade`.

## Riesgos

Ver `spec.md` (R1–R11). Los dos más graves: cerrar `:8000/:8080` sin perder acceso al panel (hacerlo después de tener el dominio HTTPS) y bloqueo de SSH.

## Alternativa descartada

- **Caddy o nginx propios delante del contenedor:** descartado por decisión del humano; ya existe Traefik con TLS gestionado por Coolify y un segundo proxy en 80/443 chocaría con el existente.
- **Cabeceras solo en Traefik:** descartado; no se puede probar en CI, depende de la plataforma y deja la app insegura si cambia el proxy.
- **Un solo Supabase con dos esquemas/tenants para pruebas y producción:** descartado; mezclaría datos reales con ficticios y compartiría roles y secretos.
- **Base de datos PostgreSQL en el VPS:** descartada; fuera del alcance (Supabase decidido en T10, 2026-11-11) y movería la responsabilidad de respaldos al VPS.
