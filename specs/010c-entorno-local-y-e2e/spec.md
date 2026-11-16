# Spec 010c — Entorno local, conexiones y pruebas e2e

> **Estado:** Aprobada por el humano (2026-11-15) en sus respuestas: imports en rojo en el editor; pruebas con Playwright **en el repo y además en vivo**; autoriza escribir el `.env` local (excepción a la regla de no tocarlo, solo para desarrollo); PR `develop → main` ahora. Plan en `plan.md`, tareas en `tasks.md`.

## Problema

1. VS Code marca en rojo los `import` del backend (no usa el entorno de uv ni ve los módulos de ayuda de `tests/`) y, con su TypeScript incluido, algunos del frontend.
2. No hay una forma simple de comprobar que cada conexión del `.env` (base local, base de pruebas, Supabase) funciona con el rol correcto.
3. Las pruebas en navegador viven fuera del repo (scripts de QA de Claude): el humano no las puede correr ni ver.
4. Falta una guía para quien no conoce el proyecto: configurar `.env`, levantar la base, conectarse con un cliente gráfico y a Supabase.

## Requisitos (EARS)

1. **R1 Editor.** Al abrir el repo en VS Code, los `import` de Python y TypeScript deben resolverse sin errores (intérprete `backend/.venv`, módulos de `backend/tests`, TypeScript del proyecto).
2. **R2 Revisar conexiones.** `flask revisar-conexiones` debe probar cada URL del entorno y mostrar, sin valores ni contraseñas: si conecta, con qué rol, si ese rol es el esperado (la app sin superusuario ni `BYPASSRLS`; el migrador distinto de la app), si la conexión usa TLS y en qué revisión de migraciones está la base.
3. **R3 Pruebas e2e.** `npm run e2e` (en `web/`) debe levantar su propia base `assetcontrol_e2e`, su API y su web, y recorrer en Chromium el flujo real: aceptar invitación, catálogo, invitar contador, verificar desde el teléfono, cerrar con aviso, informe, exportar, Inicio de ambos roles sin precios para el contador. Debe poder verse (`npm run e2e:ver`) y depurarse paso a paso (`npm run e2e:ui`). Nunca toca la base de desarrollo.
4. **R4 Guía.** `docs/10-entorno-local.md`: paso a paso para principiantes (instalar, `.env`, Docker, migrar, correr, conectarse con un cliente gráfico, conectarse a Supabase, conectar el MCP de Supabase, pruebas, e2e).

## Fuera

Cambiar el flujo de despliegue; datos reales de la clínica en pruebas.

## Dependencia nueva

`@playwright/test` (versión fijada) en `devDependencies` de `web/`.
