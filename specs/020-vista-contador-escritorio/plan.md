# Plan 020 — Vista del contador en escritorio

## Arquitectura

Sin migraciones ni dependencias nuevas. Dos cambios de permiso en backend y un marco web compartido.

### Backend (hallazgos verificados)

- `backend/app/activos/routes.py`: `editar` (`PATCH /activos/{id}`) es `@require_role("admin")`. `require_role(*roles)` acepta varios roles, así que pasa a `@require_role("admin", "contador")`. `mover`, `cambiar_estado`, `dar_de_baja` y `exportar_lista` siguen `admin`.
- `_con_version` (`con_precio=True` fijo) y `_error` (rama del 412, `con_precio=True`) pasan a `con_precio=_es_admin()`. Hoy el comentario dice que es válido porque solo el admin llega; deja de serlo. `CodigoExistente` ya trae un dict sin precio. `_con_foto`, `buscar`, `ver_historial` ya usan `_es_admin()`.
- `backend/app/activos/cambios.py`: `EDITABLES` incluye `precio_compra`. Se agrega `EDITABLES_CONTADOR = (nombre, categoria_id, marca, modelo, subtipo, serial, fecha_compra)` (los `TEXTOS` sin precio) y `edicion(body, rol)` rechaza con `ErrorActivo` 400 todo campo fuera de la lista del rol, antes de bloquear la fila. `editar` emite `precio_cambiado` solo si llega precio, que el contador nunca envía. `categoria_cambiada` y el autor ya se registran.
- `backend/app/conteo/routes.py` (~línea 113): `listar_discrepancias` pasa de `@require_role("admin")` a `@require_auth`. `aplicar_discrepancias` y `descartar_discrepancias` siguen `admin`. `discrepancias.listar` devuelve activo (id, codigo, nombre, estado), ubicaciones (ruta), autor y fechas; T2 lo comprueba con una prueba que recorre el JSON.
- `GET /ubicaciones` y `GET /categorias` (`backend/app/catalogo/routes.py`) ya son `@require_auth` (lectura abierta a ambos roles; la escritura es `admin`). Ubicaciones devuelve solo activas a quien no es admin. No requieren cambio; T2 agrega pruebas de rol para dejarlo fijado.
- `GET /sesiones`, `/sesiones/abierta`, `/sesiones/{id}`, `/pendientes` ya son `@require_auth` y `service.vista` no trae precios. `ver_informe` y exportaciones siguen `admin`.

### Web

- `components/app/AdminShell.tsx` se generaliza a `AppShell`; `admin-nav.ts` pasa a `APP_NAV` con `roles` por ítem, filtrado con `useRol()` (`lib/sesion.ts`). Se deja un export de compatibilidad solo si hace falta para no romper pruebas existentes.
- Helper único `rutaApp(...)` para quitar `/admin` fijo en `migasDeRuta`, `rutaInforme`, `entradaDeRuta`, `buscarEnNav` y enlaces internos.
- `router.tsx`: `/app` con hijos compartidos (Inicio, Activos, Registrar activo, Sesiones, Discrepancias, ficha) y un grupo hijo bajo `RequiereAdmin` (Usuarios, Empresa, Ubicaciones, Categorías, Valor, Informe). `/admin/*` → `<Navigate>` a `/app/*` conservando subruta y query. `RequiereAdmin` queda solo para ese grupo.
- Inicio por rol: `InicioPorRol.tsx` decide; en escritorio el contador va a `/app` (contenido de `contar/Inicio.tsx`, P25, sin precios) y el admin conserva `admin/Inicio.tsx`. En teléfono `/contar` sigue como hoy.
- `/contar` en computador redirige a `/app`, salvo `/contar/escanear|escribir|activo/:codigo`. Se reutiliza el criterio de «escritorio» ya existente (`contar/Escritorio.tsx`); no se inventa otro.
- `Activos`, `FichaActivo`, `RegistrarActivo`, `Sesiones`, `Discrepancias` y `EditarActivo` reciben el rol (`useRol()`): sin precio ni columna, edición limitada a la lista de R7, sin mover/estado/baja/exportar, Sesiones sin enlace al informe, Discrepancias sin acciones. El 412 conserva lo escrito (`useEdicionActivo`).
- OpenAPI: `backend/openapi.yaml` documenta `PATCH /activos/{id}` (roles, 400, 412 sin precio para contador) y `GET /sesiones/{id}/discrepancias` (roles); `npm run api:types`.

## Tablas afectadas

Ninguna se modifica. Se lee/escribe `activo` (campos descriptivos) y se inserta en `activo_evento` (autor, `categoria_cambiada`, otros eventos de edición). `tenant_id` y RLS sin cambios.

## Endpoints y permisos

| Endpoint | Antes | Después |
|---|---|---|
| `PATCH /activos/{id}` | admin | admin (todo) y contador (solo R7; 400 si no) |
| `GET /sesiones/{id}/discrepancias` | admin | admin y contador (solo lectura) |
| `POST .../discrepancias/aplicar`, `.../descartar` | admin | admin (sin cambio) |
| `POST mover/estado/baja`, `GET exportar`, informes | admin | admin (sin cambio) |
| `GET /ubicaciones`, `GET /categorias` | ambos | ambos (sin cambio; solo prueba) |

## Migraciones

Ninguna.

## Estrategia de pruebas

- Backend, rojo primero: contador edita cada campo permitido; 400 por `precio_compra`, `codigo`, `ubicacion_id`, `estado` y campos desconocidos sin cambiar nada; 428/412; ningún JSON del contador (200, 400, 412) contiene claves de precio (recorrido recursivo); eventos con autor y `categoria_cambiada`; admin sin regresión; contador 403 en mover/estado/baja/exportar/aplicar/descartar; aislamiento por tenant (404 entre tenants) en cada endpoint tocado; sesión cerrada con discrepancias legibles.
- Web: Vitest por rol (sin «precio» ni columna en el DOM para contador), menú por rol, redirección `/admin` → `/app` con query, guarda de pantallas exclusivas, 412 que conserva lo escrito, `/contar` en escritorio y en teléfono.
- E2E Playwright existente del conteo en teléfono como regresión (`npm run e2e`) si el entorno lo permite.
- QA en navegador real a 375 y 1440 px con la skill `browser-qa`; axe solo si está instalado.

## Riesgos

- Fuga de precio por rutas de error y 412 (mitigado en T1 con prueba recursiva).
- `/admin` fijo disperso (mitigado con `rutaApp` y búsqueda exhaustiva en T3).
- Cambio de categoría que desplaza el valor actual por categoría (comportamiento vigente).
- Regresión del conteo móvil (mitigado con pruebas y QA a 375 px).
- Pantallas del admin reutilizadas para contador: riesgo de que una consulta (p. ej. `useActivos`, sugerencias, historial) pida `con_precio` implícito; el servidor es la barrera.

## Alternativa descartada

Una segunda cáscara solo para el contador: duplica navegación, buscador y menú de cuenta. Tampoco se da al contador el `PATCH` completo filtrando el precio en la respuesta: arriesga que cambie el precio; el servidor lo rechaza con 400.
