# Plan 010c — Entorno local, conexiones y pruebas e2e

> **Estado:** Aprobado (2026-11-15).

- **T1 Editor:** `pyrightconfig.json` en la raíz (venv `backend/.venv`, raíz de ejecución `backend`, `extraPaths` `backend/tests`); `DOM.Iterable` en `tsconfig.app.json` (el TypeScript que trae VS Code lo necesita; el 6.x lo acepta). `.vscode/settings.json` local (ignorado por git) con intérprete, `.env`, pytest y `typescript.tsdk`.
- **T2 `flask revisar-conexiones`** (`app/conexiones.py`): para `DATABASE_URL`, `MIGRATION_DATABASE_URL`, `TEST_DATABASE_URL`, `TEST_MIGRATION_DATABASE_URL` y, si existen, `SUPABASE_DATABASE_URL`/`SUPABASE_MIGRATION_DATABASE_URL`: conecta (5 s), lee `current_user`, `rolsuper`, `rolbypassrls`, `ssl` de `pg_stat_ssl`, `alembic_version`; compara con la revisión cabeza del repo; tabla con ✓/✗ y motivo; código de salida 1 si algo falla. Nunca imprime URL, host ni contraseña.
- **T3 e2e** (`web/e2e/`): `@playwright/test`; `playwright.config.ts` con `globalSetup` que prepara la base (`e2e/base.py`: lee `../.env`, crea `assetcontrol_e2e` desde cero, migra y crea el tenant; guarda solo el token de invitación en `e2e/.estado/`, ignorado) y dos `webServer`: la API de e2e (`e2e/servidor.py`, la app Flask apuntando a `assetcontrol_e2e`, puerto 5011) y Vite (puerto 5174, proxy a 5011). Pruebas: `flujo.spec.ts` (admin y contador de punta a punta) y `contador.spec.ts` (sin precios). Scripts `e2e`, `e2e:ver`, `e2e:ui`. Vitest excluye `e2e/`.
- **T4 Guía** `docs/10-entorno-local.md` y enlace desde el README.
- **T5 Verificación:** `e2e` en verde aquí; demostración en vivo en el navegador de la app de Claude cuando el humano tenga la app local corriendo.
