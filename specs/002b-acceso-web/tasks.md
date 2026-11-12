# Tasks 002b — Acceso: contrato y web mínima (esquemático)

> **Estado:** Propuesta. Esquema para dimensionar; se detalla tras aprobar la spec. Una tarea ≤ 1 día, tests primero en cada una (T6 verifica en navegador). Depende de la T10 de la spec 002.

| Tarea | Resultado | Verificación | Depende de |
|---|---|---|---|
| T1 | Esquema OpenAPI publicado por el backend para `/auth`, `/invitaciones`, `/ready` (ejecutable: `GET` del esquema) | `cd backend && uv run pytest` | 002 T10; Q8 |
| T2 | Tipos TS generados + verificación en CI de que están al día | `cd web && npm run typecheck` | T1; Q8 |
| T3 | Cliente de API, enrutado y `/login` con redirección por rol; *proxy* de Vite | `cd web && npm test && npm run lint` | T2; Q8, Q19 |
| T4 | `/invitacion` (token del fragmento; solo nombre y contraseña, sin email; cuerpo `{token, nombre, password}`) | `cd web && npm test` | T3 |
| T5 | Pantalla de invitar (email y rol) y copiar enlace | `cd web && npm test` | T3 |
| T6 | Verificación en navegador a 375 px y 1440 px con capturas | skill `browser-qa` | T4, T5 |
