# Spec 002b — Acceso: contrato OpenAPI y web mínima

> **Estado:** Aprobada (G1–G3, 2026-11-14) con las respuestas humanas Q8 y Q19 (tabla de decisiones). Fecha: 2026-11-12, detallada el 2026-11-14. Hermana de `specs/002-acceso-y-usuarios/` (partición Q18). Depende de la spec 002 (T1–T10, hecha) y de la 001b (sistema de diseño, hecha). Plan en `plan.md`, tareas en `tasks.md`.

## Problema

Con el backend de acceso listo (spec 002) falta que el usuario pueda usarlo: pantallas de login, aceptar invitación e invitar, y un contrato tipado entre API y web para que los cambios del backend rompan la compilación o las pruebas en vez de producción.

## Alcance

- **Incluye:** R17 contrato OpenAPI escrito a mano de los endpoints existentes, con pruebas que lo atan al backend real, y tipos TypeScript generados de él con verificación de que están al día; R18 pantallas `/login`, `/invitacion` (lee el token del fragmento y lo envía en el cuerpo) e invitar (email y rol) en `/admin/usuarios`, a 375 px y 1440 px con shadcn/ui; sesión real en la web (token de acceso en memoria, refresh por cookie, cerrar sesión); redirección tras login a `/contar` (`contador`) o `/admin` (`admin`); *proxy* de Vite en desarrollo (Q19).
- **No incluye:** recuperar contraseña, listar o dar de baja usuarios, cambios de comportamiento del backend de la spec 002, despliegue (el *reverse proxy* de producción lo decide su spec), datos reales en las maquetas de la 001b.

## Requisitos (EARS)

1. Cuando el backend cambie una ruta o la forma de una respuesta de acceso, el sistema debe fallar las pruebas del backend si el contrato OpenAPI no lo refleja, y fallar las pruebas o el `typecheck` de la web si los tipos generados no coinciden con el contrato.
2. Cuando el usuario abra `/login`, `/invitacion` o la pantalla de invitar, la web debe funcionar a 375 px y 1440 px, sin digitar más que email y contraseña al iniciar sesión, o solo nombre y contraseña al aceptar la invitación (el email lo fijó el admin y no se vuelve a pedir; el cuerpo de `POST /invitaciones/aceptar` es `{token, nombre, password}`).
3. Cuando el usuario inicie sesión o acepte una invitación, la web debe redirigir según el rol que devuelve el servidor; esconder botones no sustituye la verificación del servidor.
4. Cuando la web use el token de invitación, debe leerlo del fragmento de la URL, enviarlo solo en el cuerpo y no conservarlo en el historial ni en el almacenamiento persistente.
5. Mientras haya sesión, la web debe guardar el token de acceso solo en memoria; cuando una llamada protegida responda `401`, debe renovar la sesión una vez con la cookie de refresh y, si la renovación falla, llevar al usuario a `/login`.
6. Cuando un usuario sin sesión abra `/admin/**` o `/contar/**`, la web debe llevarlo a `/login`; cuando un `contador` abra `/admin/**`, debe mostrar "Sin permiso" (el servidor responde `403` igualmente).

## Criterios de aceptación

- A16: contrato `backend/openapi.yaml`; las pruebas del backend fallan si una ruta de Flask falta en el contrato (o sobra) o si una respuesta real no cumple su esquema; la web falla `npm test` si `schema.d.ts` no es el que genera el contrato, y `npm run typecheck` si el código usa una forma que el contrato no tiene (CI + local).
- A17: login, aceptar invitación e invitar se ven y funcionan a 375 px y 1440 px contra el backend real, con capturas en navegador real, sin desbordes, sin errores de consola y sin violaciones WCAG AA de axe (skill `browser-qa`).
- A18: el token de invitación no queda en `location`, en el historial ni en `localStorage`/`sessionStorage`; el token de acceso no queda en almacenamiento persistente (pruebas).
- A19: sin sesión `/admin` y `/contar` llevan a `/login`; un `contador` en `/admin` ve "Sin permiso"; tras login cada rol llega a su inicio; cerrar sesión llama a `POST /auth/logout` y vuelve a `/login` (pruebas).

## Reglas de dominio y riesgos

Las de la spec 002 (Q13 enlace por fragmento, Q14 cabecera `X-AssetControl-CSRF` y mismo sitio, Q16 error idéntico de invitación, P13 precios solo admin). Riesgos:

- Token de invitación en historial o logs del navegador: se lee una vez, se guarda en memoria y se limpia el fragmento con una navegación `replace`.
- Token de acceso robado por XSS si se persiste: vive solo en memoria (caché de TanStack Query).
- La cookie de refresh tiene `Path=/auth`; tras el *proxy* (`/api/auth/...`) el navegador no la enviaría: el *proxy* reescribe la ruta de la cookie a `/api/auth`. El *reverse proxy* de producción debe hacer lo mismo (nota para la spec de despliegue).
- El contrato a mano se desvía del código: lo impiden las pruebas de A16, que recorren las rutas de Flask y validan respuestas reales.

## Decisiones

| Pregunta | Decisión (2026-11-14) |
|---|---|
| Q8 (contrato) | YAML escrito a mano (`backend/openapi.yaml`) + pruebas que lo atan al backend; sin generador en Flask. `openapi-typescript` genera los tipos. |
| Q8 (datos web) | `@tanstack/react-query` para sesión y llamadas. `react-router` ya está (001b). |
| Q19 | *Proxy* de Vite en desarrollo (`/api` → API), ya presente desde la spec 001; se añade la reescritura de la ruta de la cookie. |
| Q13 | **[DECIDIDO]** en la spec 002: fragmento `/invitacion#<token>`. |
| Simulación de rol de la 001b (técnica, `plan.md` §5) | La sesión real reemplaza `?rol=`; `?estado=` sigue para revisar los estados de las maquetas. |

## Preguntas abiertas

Ninguna para esta spec.
