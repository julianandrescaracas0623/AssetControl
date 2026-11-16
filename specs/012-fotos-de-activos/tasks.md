# Tasks 012 — Fotos de activos y atajo tipo app

> **Estado:** Aprobadas (G1–G3, 2026-11-15). Una tarea ≤ 1 día, pruebas primero, revisión y commit por tarea. Plan en `plan.md`.

| Tarea | Resultado | Verificación | Depende de |
|---|---|---|---|
| T1 | `Almacen` (carpeta local y S3) con las mismas pruebas en los dos (S3 con `moto`); configuración y error al arrancar en producción sin S3 | backend: `pytest`, `ruff` | aprobación |
| T2 | `procesar()`: tipo real, límites, orientación, sin metadatos, completa + miniatura | igual que T1 | aprobación |
| T3 | Migración `0013_fotos` (tabla, RLS, privilegios, disparador, tipos de evento); `docs/03` | igual que T1 + prueba de migración | aprobación |
| T4 | `PUT`/`DELETE /activos/{id}/foto`, `GET /fotos/{id}`, `foto` en la ficha; contrato; roles (Q1 B: ambos) | igual que T1 + `api:types` | T1–T3 |
| T5 | `PUT /sesiones/{sid}/verificaciones/{vid}/foto`; `foto_id` en verificaciones e historial; contrato | igual que T4 | T4 |
| T6 | Web: `lib/fotos.ts` (reducir, subir con reintento, mostrar con sesión) y `CampoFoto` | web: `test`, `lint`, `typecheck`, `build` | T4 |
| T7 | Web: foto en el alta (admin y contador) y en la ficha y verificar (cambiar/quitar, ambos roles) | igual que T6 | T6 |
| T8 | Web: foto al verificar e historial con miniaturas y visor | igual que T6 | T5, T6 |
| T9 | Atajo tipo app: manifest, íconos y etiquetas | igual que T6 + Chromium instalable | aprobación |
| T10 | Configuración y documentación (`.env*`, compose, `docs/02`, `05`, `09`, `10`, CI) | revisión | T1–T9 |
| T11 | Navegador real, e2e, revisión de seguridad y de dominio | skill `browser-qa`, `npm run e2e` | T1–T10 |

## Notas por tarea
