# Plan 002b — Acceso: contrato OpenAPI y web mínima

> **Estado:** Implementado (T1–T6, 2026-11-14), aprobado (G1–G3, 2026-11-14) con Q8 = YAML a mano + pruebas y TanStack Query, Q19 = *proxy* de Vite. Tareas en `tasks.md`.

## 1. Enfoque

Primero el contrato (sin él la web no tiene tipos), luego los tipos y el cliente, después la sesión y el login, y al final las dos pantallas que la usan. El backend **no cambia de comportamiento**: T1 solo añade el contrato y sus pruebas. No hay migraciones, ni cambios de roles, ni endpoints nuevos (el contrato vive en el repositorio; no se publica una ruta `GET /openapi.*`, que sumaría un endpoint público al catálogo de `test_roles.py`).

## 2. Contrato (`backend/openapi.yaml`, T1)

OpenAPI 3.1 escrito a mano. Cubre todas las rutas de Flask: `GET /health`, `GET /ready`, `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout`, `GET /auth/me`, `POST /invitaciones`, `POST /invitaciones/validar`, `POST /invitaciones/aceptar`.

- Esquemas en `components.schemas`: `Error` (`{error: {code, message, request_id}}`, `code` con la lista cerrada de códigos), `Sesion` (cuerpo de login, refresh y aceptar), `UsuarioActual` (`/auth/me`), `Invitacion`, `InvitacionCreada`, `Health`, `Ready` y los cuerpos de petición.
- `additionalProperties: false` en las respuestas: un campo nuevo sin documentar rompe las pruebas.
- Seguridad: `bearerAuth` en `/auth/me` y `POST /invitaciones`; la cookie de refresh y la cabecera `X-AssetControl-CSRF` se documentan como parámetros de `/auth/refresh` y `/auth/logout`.
- Cada operación lista sus respuestas de error con su código (`401 no_autenticado`, `403 prohibido`, `429 demasiadas_solicitudes`, ...).

**Pruebas (`backend/tests/test_openapi.py`):**

1. El YAML es OpenAPI 3.1 y cada `$ref` resuelve.
2. Rutas: el conjunto `(método, ruta)` de `app.url_map` (sin `HEAD`/`OPTIONS`) es igual al de `paths`.
3. Respuestas reales: sobre una base temporal (`acceso_db.temporary_acceso_db`) se ejercita cada operación en sus casos de éxito y de error principales, y cada cuerpo se valida contra el esquema declarado para ese estado. Un validador pequeño en la prueba cubre el subconjunto que usa el contrato (`type`, `required`, `properties`, `additionalProperties`, `enum`, `format: uuid|date-time|email`, `$ref`); un estado no declarado falla.
4. Códigos: el `enum` de `Error.code` es igual al conjunto de códigos que define el backend (`_HTTP_ERRORS`, constantes de rutas y `PasswordPolicyError`).

**Dependencia nueva (solo desarrollo):** `pyyaml==6.0.3` en el grupo `dev` de `pyproject.toml` (leer el YAML en las pruebas). Solo pruebas: la app no lo importa (la imagen de desarrollo instala el grupo `dev`, como pytest y ruff).

## 3. Tipos y cliente (T2)

- `openapi-typescript` **7.13.0** (devDependency, exacta). Declara `peerDependencies: typescript ^5.x` y el repo usa 6.0.3: se añade `"overrides": {"openapi-typescript": {"typescript": "$typescript"}}` en `package.json` (probado el 2026-11-14: genera bien con TS 6; `npm audit` sin hallazgos nuevos).
- Script `npm run api:types` → `openapi-typescript ../backend/openapi.yaml -o src/lib/api/schema.d.ts`. El archivo generado se versiona.
- Prueba `src/lib/api/schema.node.test.ts`: genera en memoria con la API de `openapi-typescript` y exige que sea idéntico al archivo versionado (falla en `npm test`, que ya corre en CI).
- Cliente `src/lib/api/cliente.ts`: `fetch` tipado con `paths` (sin `openapi-fetch`), base `/api`, `credentials: 'same-origin'`, cabecera `Authorization` si hay token y `X-AssetControl-CSRF: 1` en refresh y logout. Error tipado `ErrorApi {status, code, message, requestId}`; un cuerpo que no es el de error da `code: 'error_interno'` o `'sin_conexion'` (red caída).

## 4. Sesión y login (T3)

- `@tanstack/react-query` **5.107.1** (dependencia, exacta).
- Raíz de rutas `Raiz.tsx`: `QueryClientProvider` (cliente por montaje) y `Outlet`; envuelve todas las rutas, así las pruebas que montan `routes` usan el código real.
- Sesión = dato de la consulta `['sesion']` (solo memoria): al arrancar `POST /api/auth/refresh` (`retry: false`, `staleTime: Infinity`); `200` → sesión, `401` → anónima, otro error → pantalla "No se pudo conectar" con reintentar. TanStack Query deduplica la petición (StrictMode monta dos veces).
- `useSesion()` expone `{estado, sesion, iniciar, cerrar}`. `iniciar` (login) y aceptar invitación escriben la consulta; `cerrar` llama a `POST /auth/logout`, vacía la caché y navega a `/login`.
- 401 en una llamada protegida: el cliente renueva una vez (promesa compartida si hay varias en vuelo) y repite; si la renovación falla, la sesión pasa a anónima y la guarda lleva a `/login`.
- Guardas: `RequiereSesion` (`/admin`, `/contar`): cargando → pantalla de carga; anónima → `/login` con `state.desde`; `RequiereAdmin` usa el rol de la sesión (contador → `SinPermiso`). `/` y `/login` con sesión redirigen por rol. `desde` viaja en el estado del router (no en la URL: sin redirección abierta) y solo se usa si el rol puede abrir esa ruta.
- `/login`: email (`autocomplete="username"`) y contraseña (`current-password`), botón "Entrar", error del servidor en un `Alert` (mismo mensaje para cualquier fallo de credenciales), botón deshabilitado mientras envía. Tarjeta centrada de 400 px máx., una columna; a 375 px sin desbordes.
- `AdminShell` y `CountShell` muestran nombre, email y rol de la sesión y la opción "Cerrar sesión".
- *Proxy* de Vite: `cookiePathRewrite: {'/auth': '/api/auth'}` en la entrada `/api`.

## 5. Fin de la simulación de rol (T3)

La 001b eligía el rol con `?rol=`. Con sesión real eso sería un segundo origen del rol: se retira `?rol=` y `useEnlace`; `AssetCard`, `Verificar` y `Alta` leen el rol de la sesión (P13 sigue en el servidor). `?estado=` queda para revisar los estados de las maquetas, que siguen con datos ficticios y el aviso `DatosFicticios`. Las pruebas de maquetas montan las rutas con una sesión simulada en `fetch` (`src/test/sesion.ts`). `docs/08` se actualiza en una línea.

## 6. Aceptar invitación (T4)

`/invitacion` (pública):

1. Lee `location.hash` una vez (estado en memoria) y navega con `replace` a `/invitacion` sin fragmento.
2. `POST /invitaciones/validar {token}` → `vigente: false` muestra "El enlace no es válido o venció" con indicación de pedir otro al administrador; sin fragmento, lo mismo.
3. `vigente: true` → formulario nombre (`autocomplete="name"`) y contraseña (`new-password`, botón mostrar/ocultar, ayuda "Entre 10 y 128 caracteres"). Sin confirmar contraseña (R2: no se digita más).
4. `POST /invitaciones/aceptar` → `201` escribe la sesión y redirige por rol. `contrasena_*` → error en el campo con el mensaje del servidor; `invitacion_invalida` → pantalla de enlace no válido; `429`/`503` → `Alert`.

## 7. Invitar (T5)

`/admin/usuarios` deja de ser `Pendiente`: encabezado "Usuarios", tarjeta "Invitar a una persona" con email y rol (`Select`: Contador por defecto, Admin), botón "Crear invitación". Éxito: el enlace completo (`location.origin + enlace`) en un campo de solo lectura con "Copiar", el email, el rol y la fecha de vencimiento (72 h), y el aviso de que el enlace se muestra una sola vez y debe enviarse por un canal privado. Errores `400`/`403`/`429` en `Alert`. La lista de usuarios queda para una spec posterior (texto informativo, sin datos ficticios).

## 8. Verificación (T6)

Backend real (PostgreSQL + Flask) y Vite con el *proxy*; Playwright con Chromium a 375 px y 1440 px: login de admin y de contador, invitar, abrir el enlace, aceptar y llegar al inicio del rol, cerrar sesión. Capturas, cero desbordes, cero errores de consola, axe WCAG AA sin violaciones, `localStorage`/`sessionStorage` vacíos y sin token en la URL.

## 9. Dependencias nuevas

| Paquete | Versión | Dónde | Para qué |
|---|---|---|---|
| `pyyaml` | 6.0.3 | backend, grupo `dev` | Leer el contrato en las pruebas |
| `openapi-typescript` | 7.13.0 | web, `devDependencies` | Generar `schema.d.ts` |
| `@tanstack/react-query` | 5.107.1 | web, `dependencies` | Sesión y llamadas a la API |

Versiones verificadas el 2026-11-14 (`npm view`, PyPI). Si una herramienta pide otro paquete, la tarea se detiene y se pregunta.

## 10. Riesgos

- `openapi-typescript` fuera de su rango de TypeScript: la prueba de T2 lo detecta; si una versión futura rompe, se fija o se cambia por spec.
- La reescritura de cookie es solo de desarrollo: producción necesita la misma regla (spec de despliegue).
- Las maquetas dependen ahora de una sesión: para verlas en local hace falta `docker compose up` y una cuenta (script del operador de la spec 002).
