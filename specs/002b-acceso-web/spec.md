# Spec 002b — Acceso: contrato OpenAPI y web mínima

> **Estado:** Propuesta, pendiente de aprobación humana. Fecha: 2026-11-12. Hermana de `specs/002-acceso-y-usuarios/` (partición Q18). **Depende de la T10 de la spec 002.**

## Problema

Con el backend de acceso listo (spec 002) falta que el usuario pueda usarlo: pantallas de login, aceptar invitación e invitar, y un contrato tipado entre API y web para que los cambios del backend rompan la compilación en vez de producción.

## Alcance

- **Incluye:** R17 contrato OpenAPI de los endpoints de la spec 002 y tipos TypeScript generados, con verificación en CI de que están al día; R18 pantallas `/login`, `/invitacion` (lee el token del fragmento y lo envía en el cuerpo) y de invitar (email y rol), a 375 px y 1440 px con shadcn/ui; redirección tras login a `/contar` (`contador`) o `/admin` (`admin`); *proxy* de Vite en desarrollo (Q19).
- **No incluye:** app shell y sistema de diseño (`docs/08`), recuperar contraseña, listar usuarios, cambios de backend de la spec 002.

## Requisitos (EARS)

1. Cuando el backend cambie un endpoint de acceso, el sistema debe fallar el `typecheck` de la web si los tipos generados no coinciden con el esquema OpenAPI publicado.
2. Cuando el usuario abra `/login`, `/invitacion` o la pantalla de invitar, la web debe funcionar a 375 px y 1440 px, sin digitar más que email y contraseña al iniciar sesión, o solo nombre y contraseña al aceptar la invitación (el email lo fijó el admin y no se vuelve a pedir; el cuerpo de `POST /invitaciones/aceptar` es `{token, nombre, password}`).
3. Cuando el usuario inicie sesión, la web debe redirigir según el rol que devuelve el servidor; esconder botones no sustituye la verificación del servidor.
4. Cuando la web use el token de invitación, debe leerlo del fragmento de la URL, enviarlo solo en el cuerpo y no conservarlo en el historial ni en el almacenamiento persistente.

## Criterios de aceptación

- A16: OpenAPI publicado; `tsc` falla si los tipos generados no coinciden; la web compila (CI + `npm run typecheck`).
- A17: login, aceptar invitación e invitar se ven y funcionan a 375 px y 1440 px, con capturas en navegador real (skill `browser-qa`).

## Reglas de dominio y riesgos

Las de la spec 002. Riesgo: token en historial o logs del navegador; mitigación: fragmento limpiado tras leerlo.

## Preguntas abiertas

- **Q8 (web):** generador OpenAPI (`flask-smorest` o `apispec`), `openapi-typescript`, `react-router-dom`, `@tanstack/react-query`; ninguna se instala sin aprobación.
- **Q19:** origen en desarrollo; recomendado *proxy* de Vite.
- Q13 (forma del enlace) se decide en la spec 002.
- Número y nombre definitivos de la spec, y tareas definitivas, tras aceptar la partición.
