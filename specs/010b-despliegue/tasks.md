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
