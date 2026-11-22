# Plan 017 — Consola de plataforma

`spec.md` está cerrada (G1–G3 autorizadas por el humano el 2026-11-19; decisiones «Decidido (autónomo)» y Q-A1 «Decidido (humano)»). **Alcance completo, sin recorte:** base de plataforma, módulos Empresas, Usuarios y Actividad, logo en el alta (D13), cambio obligatorio de contraseña (Q-A1) y comandos de CLI de desarrolladores. No existe una «spec 018» para nada de esto.

## 1. Enfoque

Una segunda identidad (`desarrollador`) con su propio camino de autenticación, sesión de base de datos y funciones, **paralelo** al de tenant y sin mezclarse con él. No se toca `ROLES = {admin, contador}`. El acceso a varios tenants no usa políticas amplias ni `BYPASSRLS`: se hace por funciones `acceso.plataforma_*` (patrón A1 de la spec 002), cada una con lista cerrada de columnas y verificación interna de que quien llama es un desarrollador activo.

El cambio obligatorio de contraseña es la única parte que toca la app de la clínica: una marca en `usuario`, un bloqueo central en el decorador de autenticación y un endpoint más.

La web añade un shell y un registro de módulos; cada módulo es una carpeta con su ruta, su entrada de navegación y su API. Sin dependencias nuevas.

## 2. Arquitectura

### 2.1 Backend (`backend/app/plataforma/`)

| Archivo | Responsabilidad |
|---|---|
| `__init__.py` | `register_plataforma(app)`: lee `PLATAFORMA_HABILITADA`; si no es `true`, no registra nada (404). Registra el blueprint `/plataforma`, las cabeceras `no-store`/`no-referrer` y la restricción de red opcional. |
| `config.py` | `PLATAFORMA_HABILITADA`, `PLATAFORMA_REDES_PERMITIDAS` (CIDR; vacía = sin restricción), TTL de acceso (10 min) y refresh (8 h), tamaño de página de Actividad (50; máximo 100). Con la consola habilitada exige `SECRET_KEY` válida. |
| `credenciales.py` | JWT `HS256` con `sub` (desarrollador), `typ=plataforma`, `exp`, `iss`; **sin `tenant`**; clave derivada de `SECRET_KEY` con contexto propio (`plataforma-acceso`). Refresh opaco `<desarrollador_id>.<secreto>` con doble hash como en la 002. Reutiliza `app.auth.credentials` (Argon2id, `new_token`, `token_key`). |
| `decoradores.py` | `require_desarrollador`: valida el token, abre `plataforma_session(sub)`, lee `desarrollador.activo` en cada petición, expone `current_desarrollador()`; fija `required_roles = frozenset({"desarrollador"})`. |
| `auth_routes.py` | `POST /plataforma/auth/login`, `/refresh`, `/logout`, `GET /plataforma/auth/me`. CSRF y `Origin` como la 002. Audita `login_ok`. |
| `modulos/__init__.py` | Registro de módulos del servidor: `MODULOS = [Modulo(id, titulo, orden, blueprint)]`; `GET /plataforma/modulos` devuelve los habilitados (`empresas`, `usuarios`, `actividad`). |
| `modulos/empresas/{routes,service}.py` | Módulo Empresas: lista, alta, estado y logo. |
| `modulos/usuarios/{routes,service}.py` | Módulo Usuarios: lista por empresa y estado de membresía. |
| `modulos/actividad/{routes,service}.py` | Módulo Actividad: lectura paginada de la auditoría. |
| `auditoria.py` | `registrar(session, accion, tenant_id=None, objeto_id=None, resultado="ok")`; lista cerrada de acciones; sin texto libre. |

`backend/app/db.py` añade `plataforma_session(desarrollador_id)`: fija `app.desarrollador_id` (nunca `app.tenant_id`), con el mismo control del rol seguro (`verify_connection_role`) y sin `with_loader_criteria` de tenant. `tenant_session` nunca fija `app.desarrollador_id`. Las funciones `acceso.plataforma_*` se invocan con funciones propias de `db.py` (como `buscar_login`), nunca con `text()` suelto en las rutas.

`backend/app/cli.py` añade `crear-desarrollador`, `restablecer-desarrollador` y `desactivar-desarrollador` (§2.4).

**Lado tenant (T4):** `backend/app/auth/decorators.py` (bloqueo central), `backend/app/auth/routes.py` (`POST /auth/cambiar-contrasena`, campo `debe_cambiar_password` en login y `/auth/me`), `backend/app/auth/service.py`.

### 2.2 Web

```
web/src/routes/plataforma/
  PlataformaShell.tsx       layout, navegación generada del registro, cabecera, guard
  RequiereDesarrollador.tsx guard (redirige a /plataforma/entrar)
  Entrar.tsx                login
  sesion.tsx                contexto de sesión de plataforma (token solo en memoria)
  modulos.ts                registro: { id, titulo, icono, orden, ruta, cargar: () => import(...) }
  modulos/empresas/…        Empresas.tsx, NuevaEmpresa.tsx (asistente 2 pasos), api.ts, pruebas
  modulos/usuarios/…        Usuarios.tsx, api.ts, pruebas
  modulos/actividad/…       Actividad.tsx, api.ts, pruebas
web/src/routes/CambiarContrasena.tsx   pantalla de la clínica (cambio obligatorio y voluntario)
```

- `router.tsx` añade `/plataforma/entrar` y `/plataforma/**` con carga perezosa; las rutas hijas salen de `modulos.ts` (una entrada = una ruta + un ítem de menú). La web filtra por `GET /plataforma/modulos` (el servidor manda).
- Sesión de plataforma **separada** de la de tenant: token solo en memoria, cookie propia, cliente de TanStack Query propio vaciado al cerrar sesión.
- Shell: a 1440 px barra lateral con marca «Plataforma» e `Insignia` «Solo desarrolladores»; a 375 px la navegación va en `Menu`/`Dialogo` del kit. Componentes del kit: `EncabezadoPagina`, `TablaDatos`, `Dialogo`, `Confirmar`, `Campo`, `Boton`, `Insignia`, `Aviso`, `Estado`, `Panel`, `Notificaciones`, `Filtro`, `Fecha`. Nada de `components/ui` directo en código nuevo. Si hace falta un patrón nuevo, se compone con el kit y se informa al `coordinator` para docs/08.
- Alta de empresa, **formulario único (C1c; antes asistente de dos pasos)**: ficha, logo opcional (selector con vista previa) y primer admin con contraseña y confirmación (`autoComplete="new-password"`), estado de contraseñas descartado al enviar o cerrar; sin paso 2, sin «Paso N de 2» y sin barra de progreso; si el logo falla tras crear la empresa, aviso y reintento desde Editar empresa (§10.3). Aviso de respaldo «El admin deberá cambiar esta contraseña al entrar». Sin botón «Copiar».
- **Cambio obligatorio (clínica):** la sesión de tenant guarda `debe_cambiar_password` (de login y `/auth/me`); un guard del router lleva toda ruta a `/cambiar-contrasena` mientras sea `true`, y un `403 cambio_password_requerido` en cualquier petición hace lo mismo. Al guardar, se refresca `me` y se entra a la ruta por rol. La pantalla usa el kit (`Campo` de contraseña ×3, `Boton`), es de columna única y usable a 375 px.
- Usuarios: selector de empresa (o llegada desde la fila de Empresas), `TablaDatos` con estado y acción con `Confirmar`. Actividad: `TablaDatos`, `Filtro` por empresa y acción, `Fecha` para el rango, «Cargar más» por cursor.

### 2.3 Acceso multi-tenant: funciones

Todas `SECURITY DEFINER`, `STRICT`, `SET search_path = pg_catalog, pg_temp`, nombres calificados, SQL estático, `REVOKE ALL … FROM PUBLIC, anon, authenticated, service_role`, `GRANT EXECUTE` solo al rol indicado. Dueño `plataforma_owner` (las de plataforma) o `auth_owner` (`cambiar_password_propio`, de tenant). Primera línea de cada `plataforma_*`: comprobar que `p_desarrollador` existe y está activo; si no, excepción estática sin datos.

| Función (migración) | Efecto | Devuelve (lista cerrada) | `EXECUTE` |
|---|---|---|---|
| `acceso.crear_desarrollador(p_email, p_nombre, p_password_hash)` (0017) | `INSERT desarrollador` y auditoría `desarrollador_creado` (`desarrollador_id` nulo). | `id` | solo migrador |
| `acceso.restablecer_desarrollador(p_email, p_password_hash)` (0017) | `UPDATE password_hash`, revoca todas las familias de `plataforma_refresh_token`, audita `desarrollador_restablecido`. Correo inexistente: excepción genérica. | nada | solo migrador |
| `acceso.cambiar_estado_desarrollador(p_email, p_activo)` (0017) | `UPDATE activo`, revoca familias al desactivar, audita `desarrollador_desactivado`/`desarrollador_reactivado`. | nada | solo migrador |
| `acceso.plataforma_buscar_login(p_email)` (0017) | Lectura para el login de plataforma. | `id`, `password_hash`, `activo` | aplicación |
| `acceso.plataforma_listar_tenants(p_dev)` (0018) | Lectura de `tenant`, de `empresa.logo_id IS NOT NULL` y conteos de `membresia`. | `id`, `nombre`, `activo`, `creado_en`, `tiene_logo`, `n_membresias_activas`, `n_admins_activos` | aplicación |
| `acceso.plataforma_crear_tenant(p_dev, p_id, p_ficha…, p_admin_id, p_admin_email, p_admin_nombre, p_password_hash)` (0018) | Una transacción: rechaza `email_en_uso` y `empresa_existente`; `INSERT tenant` (con `id` del cliente), `INSERT empresa` (ficha; sin logo), `INSERT usuario` con `debe_cambiar_password = true` y `INSERT membresia` admin activa. El hash lo calcula Flask; la función nunca lo devuelve. | `tenant_id`, `usuario_id` | aplicación |
| `acceso.plataforma_cambiar_estado_tenant(p_dev, p_tenant, p_activo)` (0018) | `UPDATE tenant.activo, desactivado_en, desactivado_por`; idempotente. | `activo` | aplicación |
| `acceso.cambiar_password_propio(p_usuario, p_hash_nuevo, p_familia_actual)` (0019) | Para el usuario autenticado: `UPDATE usuario.password_hash` y `debe_cambiar_password = false`; revoca las demás familias de refresh del usuario (conserva `p_familia_actual`). Se restringe con una GUC de la propia función y política acotada del dueño. | nada | aplicación |
| `acceso.plataforma_listar_usuarios(p_dev, p_tenant)` (0020) | Lectura de `membresia` y `usuario` de ese tenant. | `usuario_id`, `nombre`, `email`, `rol`, `activa`, `debe_cambiar_password`, `creado_en` | aplicación |
| `acceso.plataforma_cambiar_estado_membresia(p_dev, p_tenant, p_usuario, p_activa)` (0020) | `UPDATE membresia.activa`; rechaza `ultimo_admin`, `empresa_inactiva` y usuario ajeno (`404`); al desactivar revoca familias de refresh de esa membresía; idempotente. | `activa` | aplicación |
| `acceso.plataforma_listar_auditoria(p_dev, p_tenant, p_accion, p_desde, p_hasta, p_limite, p_cursor_fecha, p_cursor_id)` (0021) | Lectura de `plataforma_auditoria` con `LEFT JOIN` a `tenant` y `desarrollador` solo para nombres; orden `creado_en DESC, id DESC`; `p_limite` acotado dentro de la función. | `id`, `creado_en`, `accion`, `resultado`, `desarrollador_nombre`, `tenant_id`, `tenant_nombre`, `objeto_id` | aplicación |
| `acceso.plataforma_registrar_logo(p_dev, p_tenant, p_logo_id, p_clave, p_bytes, p_ancho, p_alto)` (0022) | Si la empresa no tiene logo: `INSERT empresa_logo` (subido por la única membresía admin activa más antigua) y `UPDATE empresa.logo_id`; `409 logo_existente` si ya hay; idempotente con el mismo `logo_id`; audita `empresa_logo_subido`. El archivo lo procesa y guarda Flask antes. | `logo_id`, `creado` | aplicación |

- Ninguna función de plataforma lee `activo`, `verificacion`, `sesion_*`, `ubicacion`, `categoria`, fotos ni informes; de `empresa` escribe la ficha inicial (`crear_tenant`), `logo_id` (`registrar_logo`) y, **desde C1 (§10)**, las cinco columnas de la ficha (`actualizar_empresa`); lee `logo_id IS NOT NULL` y, **desde C1**, esas cinco columnas (`leer_empresa`); nunca `actualizada_por`. La prueba A4 lo hace cumplir listando las tablas y columnas que cada política del dueño abre.
- **Políticas del dueño** (`TO plataforma_owner`, por comando, nunca `FOR ALL`, cero filas con GUC vacía): una GUC por función (`app.plat_crear_tenant`, etc.) como en la 002. Los `INSERT` de `tenant`, `empresa`, `usuario` y `membresia` se acotan al tenant creado en la misma transacción; `UPDATE tenant` solo `activo`, `desactivado_en`, `desactivado_por` *(C1: y `nombre`)*; `UPDATE membresia` solo `activa` *(C1: y `rol`)*; `UPDATE usuario` *(C1: `nombre`; C1b: `password_hash`, `debe_cambiar_password`, `sesiones_validas_desde`)*; `UPDATE empresa` solo `logo_id` (y `actualizada_*` requeridos por el esquema, fijado por T7 contra la `0014`) *(C1: la política de `logo_id` deja de exigir `logo_id IS NULL` y se añade la de la ficha; §10.2)*. Privilegios por columna; sin `DELETE`. Cada tarea verifica nombres y restricciones exactos contra las migraciones previas y fija el SQL con el `security-reviewer`.
- `acceso.crear_tenant` y el comando `create-tenant` **no cambian**; `plataforma_crear_tenant` tiene SQL propio para no ampliar el `EXECUTE` de una función del migrador.
- La contraseña se valida en Flask con la misma función de la 002/014 (`422` antes de llamar a la base); la confirmación también se compara en el servidor.

### 2.4 CLI del operador

`flask crear-desarrollador <email>`, `flask restablecer-desarrollador <email>`, `flask desactivar-desarrollador <email> [--reactivar]`:

- Crear pide **nombre** y **contraseña** con `click.prompt(hide_input=True, confirmation_prompt=True)`; restablecer pide solo la contraseña; ambos aceptan `--password-stdin` (nunca por argv ni entorno). Desactivar no pide contraseña.
- Validan la política (14–128, lista de comunes) y calculan Argon2id **en el comando**; a la base solo llega el hash.
- Se conectan con el rol migrador de `MIGRATION_DATABASE_URL` (mismas reglas que `create-tenant`: falla si es el mismo rol que `DATABASE_URL`) y llaman a la función `acceso.*` correspondiente.
- No imprimen ni registran la contraseña ni el hash; un error de base se informa con tipo y `sqlstate`; un correo inexistente da un mensaje genérico.

**Por qué CLI:** quien tiene `MIGRATION_DATABASE_URL` ya tiene control total de la base; no amplía quién puede administrar desarrolladores y evita el huevo y la gallina. **Por qué restablecer y desactivar:** sin ellos, una contraseña olvidada o una cuenta comprometida solo se resuelven con SQL a mano o apagando toda la consola. **Descartadas:** contraseña inicial en entorno o migración (secreto en el entorno o repo); enlace de activación (tabla y flujo extra para una o dos personas); pantalla pública de «primer uso» (hueco de toma de control).

### 2.5 Efecto de `tenant.activo` en el acceso del tenant

- `service.load_current_user` (cada petición protegida) añade la condición `tenant.activo`: empresa inactiva → `401 no_autenticado`.
- `acceso.buscar_login` no devuelve membresías de un tenant inactivo (login falla con el `401` genérico). El mecanismo (política `SELECT` acotada de `auth_owner` sobre `tenant.activo` con una GUC de la propia función) lo fija T3a con el `security-reviewer`: es el único cambio a una función existente de la 002 en esta parte.
- El refresh rotativo debe fallar con tenant inactivo; T3b lo comprueba (A9) y lo añade si hace falta.
- Sin caché: `tenant.activo` se lee en cada petición. Lo mismo para `membresia.activa` (R30): T5 confirma que `load_current_user`, login y refresh ya la respetan (spec 002) y lo cubre con prueba.

### 2.6 Cambio obligatorio de contraseña (R25–R28)

- **Marca:** `usuario.debe_cambiar_password boolean NOT NULL DEFAULT false` (migración 0017). Solo `plataforma_crear_tenant` la pone en `true`. Los usuarios existentes, invitados y restablecidos tienen `false`.
- **Bloqueo central:** `load_current_user` ya lee `usuario` en cada petición; el decorador común (`require_role`/equivalente de `app/auth/decorators.py`) comprueba la marca después de autenticar y responde `403 cambio_password_requerido` salvo en una **lista blanca explícita por nombre de endpoint** (`auth.me`, `auth.logout`, `auth.refresh`, `auth.cambiar_contrasena`; `login` y `restablecer` son públicos). Un endpoint nuevo queda bloqueado por defecto. Fuera del decorador no hay otra comprobación.
- **Endpoint:** `POST /auth/cambiar-contrasena` `{actual, nueva, confirmacion}`: verifica la actual (Argon2id, hash simulado si no coincide, `limite_tasa` en el ámbito de login del tenant), política de la 002, nueva distinta de la actual, confirmación; llama `acceso.cambiar_password_propio`. `401 credenciales_invalidas` / `422`. Las contraseñas no se registran.
- **014:** la función de restablecer de la migración 0016 también deja `debe_cambiar_password = false` (R28); T4 lo añade con prueba.
- **Login:** la respuesta de login y `/auth/me` incluyen `debe_cambiar_password`. El JWT no lo lleva (se lee de la base en cada petición, sin caché).
- **Por qué marca en `usuario`, no en `membresia`:** la contraseña es del usuario; hay una sola membresía activa por usuario (H-2) y recuperar o cambiar la contraseña ya opera sobre `usuario`.

### 2.7 Seguridad transversal

- **CSRF:** `X-AssetControl-CSRF: 1` y `Origin`/`Sec-Fetch-Site` en `refresh` y `logout`; el resto usa `Authorization: Bearer`.
- **Cookie:** `__Secure-plat-refresh`, `HttpOnly`, `SameSite=Lax`, `Path` del prefijo de auth de plataforma (con el prefijo `/api` que defina la spec de despliegue); con `ENVIRONMENT=development` explícito se omite `Secure` y el prefijo, como la del tenant.
- **Límites:** ámbitos `plat_login_ip` y `plat_login_cuenta` (la migración 0017 amplía el `CHECK` de `limite_tasa.ambito`); 5 por cuenta y 10 por IP en 15 min, configurables.
- **Cabeceras:** `Cache-Control: no-store` y `Referrer-Policy: no-referrer` en toda `/plataforma/*`; la web de `/plataforma/**` lleva `noindex`.
- **Red:** `PLATAFORMA_REDES_PERMITIDAS` compara `request.remote_addr` (tras `ProxyFix`); fuera de la lista, `404`. Defensa adicional: la restricción real va en el proxy o firewall (docs/09, T11).
- **Logo:** `multipart/form-data` con el mismo procesamiento de `app.fotos.imagen.procesar_logo` y el mismo almacén que la 013 (clave `clave_logo(tenant_id, logo_id)`); si la transacción falla, se borra el archivo (patrón `after_rollback` de la 013).
- **Logs:** sin contraseñas, tokens, hashes ni correos; solo ids, acción y resultado.

## 3. Tablas afectadas

Nuevas (excepciones cerradas a «toda tabla de negocio lleva `tenant_id`»; cada una con prueba propia en el catálogo de RLS):

| Tabla | Columnas | RLS y privilegios (rol de aplicación) |
|---|---|---|
| `desarrollador` | `id`, `email` (único, `CHECK email = lower(btrim(email))`), `nombre`, `password_hash`, `activo`, `creado_en` | `ENABLE`+`FORCE`; política `SELECT` con `id = app.desarrollador_id`; `GRANT SELECT (id, email, nombre, activo)` (sin `password_hash`); sin `INSERT`/`UPDATE`/`DELETE`: las altas y cambios van por CLI y funciones del migrador. |
| `plataforma_refresh_token` | `id`, `desarrollador_id` FK, `familia_id`, `token_hash` bytea(32) único, `expira_en`, `usado_en`, `revocado_en`, `creado_en` | `FORCE`; políticas por comando con `desarrollador_id = app.desarrollador_id`; `SELECT`, `INSERT`, `UPDATE (usado_en, revocado_en)`; sin `DELETE`. |
| `plataforma_auditoria` | `id`, `desarrollador_id` FK **null** (null = operador/CLI), `accion` (`CHECK` con la lista cerrada de R33), `resultado` (`ok`\|`rechazado`), `tenant_id` FK null, `objeto_id` uuid null, `creado_en` default `now()` | `FORCE`; `INSERT` con `desarrollador_id = app.desarrollador_id`; `SELECT` para un desarrollador activo (`EXISTS` sobre `desarrollador`); sin `UPDATE` ni `DELETE`. Índices `(creado_en DESC, id DESC)`, `(tenant_id, creado_en DESC)` y `(accion, creado_en DESC)`. Sin correos, nombres, IP ni texto libre. |

Modificadas:

| Tabla | Cambio |
|---|---|
| `tenant` | `activo boolean NOT NULL DEFAULT true`, `desactivado_en timestamptz NULL`, `desactivado_por uuid NULL` (FK a `desarrollador`); `CHECK (activo = (desactivado_en IS NULL))`; al reactivar, ambos campos vuelven a null y el historial queda en la auditoría. Sin `DELETE`. |
| `usuario` | `debe_cambiar_password boolean NOT NULL DEFAULT false`. Escribible solo por `acceso.plataforma_crear_tenant`, `acceso.cambiar_password_propio`, la función de restablecer de la 014 y, desde C1b, `acceso.plataforma_restablecer_password_usuario` (§11; la deja en `true`). |
| `limite_tasa` | Ampliar el `CHECK` de `ambito` con `plat_login_ip` y `plat_login_cuenta`. |
| `membresia` | Sin cambio de esquema; `activa` se escribe también desde `plataforma_cambiar_estado_membresia`. |
| `empresa`, `empresa_logo` | Sin cambio de esquema; el alta o reemplazo de logo escribe `empresa_logo` y `empresa.logo_id` desde `plataforma_registrar_logo`; **(C1)** la ficha se lee y escribe desde `plataforma_leer_empresa` y `plataforma_actualizar_empresa` (§10). |
| `usuario`, `membresia` (C1) | Sin cambio de esquema; `plataforma_cambiar_usuario` escribe `usuario.nombre` y `membresia.rol` (§10). |
| `plataforma_auditoria` (C1) | Se amplía el `CHECK` de `accion` y la política de inserción de la aplicación con `empresa_editada`, `empresa_logo_reemplazado` y `usuario_editado` (migración `0030`). |
| `tenant` (C1, Q-E1 = a, decidida por el humano) | `UPDATE (nombre)` acotado por GUC (la misma `app.plat_empresa_tenant`); sin cambio de esquema. |
| `usuario` (C1b) | Sin cambio de esquema; `plataforma_restablecer_password_usuario` escribe `password_hash`, `debe_cambiar_password` y `sesiones_validas_desde` (§11). |
| `plataforma_auditoria` (C1b) | `0032` amplía otra vez el `CHECK` de `accion` y la política de inserción con `usuario_contrasena_restablecida`. |

Roles: `plataforma_owner` `NOLOGIN` (sin `rolsuper`/`rolbypassrls`, no dueño de tablas, sin membresía cruzada con el rol de aplicación), creado en `docker/postgres/init/01-app-role.sh` (idempotente) y por `app.roles`/`preparar-roles` (Supabase), con los mismos controles de membresía transitoria que `auth_owner` (§2.1 de la 002).

## 4. Endpoints y permisos

Bajo `/plataforma`: «desarrollador» = token de plataforma válido y `desarrollador.activo`. Errores con el JSON uniforme de la spec 001.

| Método y ruta | Rol | Notas |
|---|---|---|
| `POST /plataforma/auth/login` | público, con límite | `{email, password}`; `401` genérico |
| `POST /plataforma/auth/refresh` | cookie de refresh | CSRF + `Origin`; rotación |
| `POST /plataforma/auth/logout` | cookie de refresh | revoca familia |
| `GET /plataforma/auth/me` | desarrollador | id, nombre, correo |
| `GET /plataforma/modulos` | desarrollador | registro del servidor |
| `GET /plataforma/empresas` | desarrollador | solo identidad, `tiene_logo` y conteos |
| `POST /plataforma/empresas` | desarrollador | `{id, ficha…, admin: {nombre, email, password, password_confirmacion}}` → `201 {empresa_id, admin_id}`; `409 email_en_uso`/`empresa_existente`; `422` |
| `PATCH /plataforma/empresas/{id}` | desarrollador | `{activa}`; `404` si no existe |
| `POST /plataforma/empresas/{id}/logo` | desarrollador | multipart `logo_id` + archivo; `201` (alta o **C1: reemplazo**)/`200` (mismo `logo_id`); ~~`409 logo_existente`~~ (retirado en C1); `404`; `415`/`422` y `503 logos_no_disponibles` como la 013 |
| `GET /plataforma/empresas/{id}/ficha` (C1) | desarrollador | `{nombre, direccion, nit, telefono, correo, tiene_logo}`; `404` |
| `PUT /plataforma/empresas/{id}/ficha` (C1) | desarrollador | los cinco campos; `200 {…ficha}`; `422`; `404`; `409 empresa_sin_datos`; `503`; cuenta en `plat_accion` |
| `PUT /plataforma/empresas/{id}/usuarios/{usuario_id}` (C1) | desarrollador | `{nombre, rol}`; `200 {id, nombre, rol}`; `422`; `400` si hay otra clave; `409 ultimo_admin`/`empresa_inactiva`; `404`; `503`; cuenta en `plat_accion` |
| `POST /plataforma/empresas/{id}/usuarios/{usuario_id}/contrasena` (C1b) | desarrollador | `{password, password_confirmacion}`; `204` sin cuerpo; `422`; `400` si hay otra clave; `404` (empresa o usuario); `409 empresa_inactiva`; `503` (candado); `429`; cuenta en `plat_accion`; `no-store` |
| `GET /plataforma/empresas/{id}/usuarios` | desarrollador | campos de R29; `404` |
| `PATCH /plataforma/empresas/{id}/usuarios/{usuario_id}` | desarrollador | `{activa}`; `409 ultimo_admin`/`empresa_inactiva`; `404` |
| `GET /plataforma/actividad` | desarrollador | filtros `empresa_id`, `accion`, `desde`, `hasta`, `cursor`, `limite`; solo lectura |

Tenant (en `/auth`, spec 002): `POST /auth/cambiar-contrasena` (cualquier usuario autenticado, incluso con la marca) y el campo `debe_cambiar_password` en login y `GET /auth/me`; el `403 cambio_password_requerido` aplica a todo endpoint de tenant fuera de la lista blanca (§2.6).

Sin ruta pública salvo el login de plataforma. Cada endpoint trae su prueba `401` (sin token, con token de tenant, con token expirado) y de aislamiento (A2, A6). Los contratos se añaden a `backend/openapi.yaml` a mano y los tipos con `npm run api:types`.

## 5. Migraciones

Encadenadas desde `0016`; nada se borra de las tablas existentes; todas reversibles.

- `0017_plataforma` (T1): tablas `desarrollador`, `plataforma_refresh_token`, `plataforma_auditoria` (con la lista cerrada completa de acciones); columnas de `tenant`; `usuario.debe_cambiar_password`; `CHECK` de `limite_tasa`; RLS, privilegios y `REVOKE` a roles de Supabase; falla con mensaje claro si falta `plataforma_owner`. Funciones `acceso.crear_desarrollador`, `restablecer_desarrollador`, `cambiar_estado_desarrollador` (migrador) y `plataforma_buscar_login`.
- `0018_funciones_plataforma` (T3a): `plataforma_listar_tenants`, `plataforma_crear_tenant`, `plataforma_cambiar_estado_tenant`, políticas del dueño, `ALTER FUNCTION … OWNER TO plataforma_owner` con membresía transitoria y `REVOKE CREATE` posterior (C3/C5 de la 002), y el ajuste de `acceso.buscar_login` (§2.5).
- `0019_cambio_password` (T4): `acceso.cambiar_password_propio` y el ajuste de la función de restablecer de la 0016 (R28).
- `0020_plataforma_usuarios` (T5): `plataforma_listar_usuarios`, `plataforma_cambiar_estado_membresia` y sus políticas.
- `0021_plataforma_actividad` (T6): `plataforma_listar_auditoria`.
- `0022_plataforma_logo` (T7): `plataforma_registrar_logo` y sus políticas sobre `empresa_logo` y `empresa.logo_id`.
- **Numeración real** (ver «Cierre» de la spec): se implementaron `0017`, `0018`, `0023`–`0029`. **C1 añade `0030_plataforma_edicion_empresa` (T12) y `0031_plataforma_editar_usuario` (T13)**, encadenadas en ese orden desde `0029_plataforma_logo`; reversibles; un solo head. **C1b añade `0032_plataforma_password_usuario` (T16)**, encadenada a `0031`.

## 6. Dependencias

Ninguna nueva (Argon2id, Flask, SQLAlchemy, psycopg, click, Pillow, React, TanStack Query y el kit ya están). Si algo parece necesario, se para y se pregunta.

## 7. Estrategia de pruebas

Tests primero en cada tarea.

- **Catálogo (A3, A4, A15):** `url_map` recorrido; funciones cerradas (se amplía en cada migración); tablas con RLS forzada; columnas devueltas; privilegios de la aplicación, del migrador y de `plataforma_owner`; `auth_owner` y `plataforma_owner` sin `CREATE` en `acceso` tras `upgrade head` (C5).
- **Aislamiento (A2, A5, A6, A9, A17):** matriz token×endpoint en ambos sentidos (admin y contador no entran a `/plataforma`); `plataforma_session` no lee tablas de negocio; `tenant_session` no lee tablas de plataforma; funciones con desarrollador inexistente o inactivo; conteos antes/después de desactivar; tenants A y B para confirmar que desactivar A (o un usuario de A) no toca B.
- **Auth (A13):** login, refresh con rotación y reuso, logout, CSRF, límite de tasa, hash simulado, política de contraseña, token cruzado (clave y `typ` distintos), flag apagado → `404`.
- **CLI (A13, A20):** rol migrador de prueba sin superusuario; sin contraseña en argv/entorno; salida sin secretos; restablecer revoca refresh; desactivar corta el token vigente.
- **Empresas y logo (A7, A8, A10–A12, A19):** atomicidad (fallo a mitad → cero filas), `409`/`422` sin filas nuevas, una fila de auditoría por acción en la misma transacción, `UPDATE`/`DELETE` sobre auditoría fallan, `caplog` sin secretos, el admin creado inicia sesión por el login de la 002, logo con archivo huérfano limpiado.
- **Cambio obligatorio (A16):** recorrido de `url_map` con un usuario marcado (todo `403` salvo la lista blanca); cambio exitoso, actual errónea, nueva igual, confirmación distinta; revocación de las demás familias; usuarios no marcados no cambian; regresión de 002 y 014; `caplog`.
- **Usuarios y Actividad (A17, A18):** `ultimo_admin`, `empresa_inactiva`, usuario ajeno, revocación de refresh; paginación por cursor, filtros, orden, campos exactos.
- **Web (A14):** Vitest del shell, registro (módulo de prueba), guard, login, Empresas (alta en formulario único, fallo parcial del logo, aviso, desactivar con `Confirmar`, estados), Usuarios, Actividad, pantalla de cambio de contraseña; capturas en navegador real a 375 y 1440 px (skill `browser-qa`); e2e Playwright (crear empresa → login del admin → cambio obligatorio → `/admin`). No declarar axe si no está instalado.

## 8. Riesgos técnicos

Los de la spec (R1 a R13) más:

- **Cambiar `buscar_login`, `load_current_user`, el decorador común y la función de restablecer de la 014** toca la ruta de login y de toda petición del tenant: regresión completa de las specs 002 y 014 en T3b y T4.
- **T3 y T4 son las tareas más densas.** T3 ya viene partida en T3a (SQL y catálogo) y T3b (endpoints y efecto de `tenant.activo`). En T4, si la pantalla web no cabe en el día, se mueve a su propia tarea sin cambiar alcance.
- **Roles en Supabase:** `plataforma_owner` exige repetir la validación C8 con el rol real antes del piloto (pendiente del humano).
- **Coordinación con despliegue:** la cookie `Path` con `/api` y la restricción por red dependen de esa spec.
- **Logo:** la subida desde la consola reutiliza el almacén; si en un entorno de prueba no hay almacén, `503 logos_no_disponibles`; en el alta (C1c) se avisa «Empresa creada; el logo no se pudo subir» y el reintento es desde Editar empresa.

## 9. Alternativas descartadas

- **Rol de aplicación aparte con `BYPASSRLS` para el desarrollador:** rompe la barrera de la constitución §4.
- **Tercer rol `desarrollador` en una membresía de un tenant «plataforma»:** mezcla identidades, ensancha `ROLES` y permite poder de plataforma por error de configuración.
- **Políticas RLS amplias cuando `app.desarrollador_id` está fijado:** una GUC mal fijada abriría todas las tablas; las funciones acotadas devuelven solo columnas listadas.
- **Servicio o contenedor separado:** contradice ADR-002; la separación se logra con flag, red y subdominio opcional.
- **Reutilizar `acceso.crear_tenant`:** su `EXECUTE` es del migrador; abrirlo ampliaría una función de operador.
- **Invitación para el primer admin:** descartada por el humano; el desarrollador crea el admin con contraseña y el admin debe cambiarla en el primer ingreso.
- **Solo aviso en lugar de cambio obligatorio:** descartado por el humano (Q-A1: SÍ); un aviso no impide usar la contraseña conocida por el desarrollador.
- **Marca de cambio en el JWT:** descartada; se lee de la base en cada petición para que cambiar la contraseña surta efecto al instante y sin tokens a revocar.
- **Subir el logo desde la web de la clínica con un token suplantado por el desarrollador:** descartado; el desarrollador nunca opera con identidad de tenant (R36–R37).
- **Guardar secretos SMTP en base de datos desde la consola:** riesgo alto; fuera de alcance.

## 10. Cambio C1 (2026-11-21): editar empresa, logo en el alta y editar usuario

Cambio aprobado por el humano; sin dependencias nuevas. Mismo patrón que T5 y T7 (funciones `acceso.plataforma_*`, `SECURITY DEFINER`, `STRICT`, `search_path = pg_catalog, pg_temp`, dueño `plataforma_owner`, `EXECUTE` solo la aplicación, desarrollador activo en la primera línea, GUC `app.plat_*` vaciadas al entrar y salir, `SET lock_timeout = '5s'`, políticas por comando y por GUC, privilegios por columna). Por ser `STRICT`, los opcionales vacíos viajan como `''` (como en T6), nunca `NULL`; la validación de formato y de dígito de verificación sigue en Flask (`app.empresa.service.validar`, la misma de la 013) y las restricciones de la `0014` siguen siendo el respaldo en la base.

### 10.1 Funciones nuevas o rehechas

| Función (migración) | Efecto | Devuelve (lista cerrada) |
|---|---|---|
| `acceso.plataforma_leer_empresa(p_desarrollador, p_tenant)` (0030) | Lectura de la ficha de ese tenant; `404` si el tenant no existe; `409 empresa_sin_datos` si no hay fila `empresa`. | `nombre`, `direccion`, `nit`, `telefono`, `correo`, `tiene_logo` |
| `acceso.plataforma_actualizar_empresa(p_desarrollador, p_tenant, p_nombre, p_direccion, p_nit, p_telefono, p_correo)` (0030) | Con la fila `empresa` bloqueada, `UPDATE` de las cinco columnas y `actualizada_en = now()` **solo si algún valor cambia** (`IS DISTINCT FROM`); sin cambios no escribe. `actualizada_por` no se toca (la persona que actúa no es un `usuario`; el actor queda en la auditoría; el implementer lo confirma contra la `0014` y, si la columna fuera `NOT NULL` sin valor, se detiene y lo informa). **Q-E1 = (a) (decidida por el humano):** si el nombre cambia, actualiza también `tenant.nombre` (`UPDATE` de esa columna acotado por la misma GUC, en la misma función y transacción; `cambiado` es verdadero si cambió cualquiera de las dos). No toca `activo` ni `desactivado_*`. | `cambiado boolean` |
| `acceso.plataforma_registrar_logo(...)` rehecha (0030) | Igual que la de T7 (misma firma de entrada) pero **sin `409 logo_existente`**: si la empresa tiene otro logo lo reemplaza; mismo `logo_id` vigente → no escribe. El `UPDATE empresa SET logo_id` ya no exige `logo_id IS NULL`; la fila bloqueada serializa contra el admin. El resto del orden de rechazos de T7 no cambia. Como cambia el tipo devuelto, se hace `DROP FUNCTION` + `CREATE` y se reaplican dueño (membresía transitoria y `REVOKE CREATE` posterior, C3/C5), `REVOKE` y `GRANT EXECUTE`. | `logo_id`, `creado boolean`, `reemplazado boolean` |
| `acceso.plataforma_cambiar_usuario(p_desarrollador, p_tenant, p_usuario, p_nombre, p_rol)` (0031) | Mismo orden de rechazos y mismo candado consultivo por tenant (`hashtextextended('plataforma_membresia:' \|\| tenant)`) que `plataforma_cambiar_estado_membresia` (0027): `404` empresa → `404` usuario ajeno → `409 empresa_inactiva` → `409 ultimo_admin` (solo si la membresía es `admin` activa, es la última `admin` activa y `p_rol = 'contador'`) → `UPDATE usuario.nombre` y `UPDATE membresia.rol` solo de lo que cambia; si cambió el rol, revoca las familias de refresh de esa membresía con el mismo bucle acotado y fallo cerrado de 0027. `lock_timeout` 5 s → `55P03` → `503`. | `nombre`, `rol`, `cambiado boolean`, `rol_cambiado boolean` |

- **Auditoría:** Flask escribe `empresa_editada`, `empresa_logo_reemplazado` (si `reemplazado`; `empresa_logo_subido` si `creado` sin reemplazo) y `usuario_editado` en la misma transacción, solo si `cambiado`/`creado`/`reemplazado` es verdadero (como T5; a diferencia del `PATCH` de Empresas, D12), con `tenant_id` y `objeto_id` (logo nuevo, usuario o `NULL` para la ficha), nunca valores. `auditoria.py`, el `CHECK` `plataforma_auditoria_accion_valida` y la política `plataforma_auditoria_insertar` de la aplicación se amplían en `0030` con las tres acciones (la política de 0018 ya exige `tenant_id IS NOT NULL` para acciones que no son `login_ok`).
- **Catálogo A4:** `plataforma_leer_empresa`, `plataforma_actualizar_empresa` (0030) y `plataforma_cambiar_usuario` (0031) entran a la lista cerrada con columnas devueltas exactas; la de logo cambia sus columnas. La prueba de políticas del dueño lista de nuevo qué tablas y columnas abre cada una.

### 10.2 Políticas y privilegios del dueño (nuevos o cambiados)

- `empresa`: `SELECT (nombre, direccion, nit, telefono, correo)` y política `FOR SELECT` acotada a `app.plat_empresa_tenant` con desarrollador de `app.plat_actor` activo; `UPDATE (nombre, direccion, nit, telefono, correo)` con política `FOR UPDATE` acotada a la misma GUC (`WITH CHECK` mantiene `tenant_id` y exige `actualizada_en = now()`); la política `UPDATE` de `logo_id` de T7 pierde `logo_id IS NULL` y mantiene `logo_id = app.plat_logo_id`. Sigue sin `SELECT` de `actualizada_por` ni de `logo_id` salvo lo que ya abre T7.
- `usuario`: `UPDATE (nombre)` con política acotada a la GUC del usuario objetivo y a una membresía de ese tenant; `membresia`: `SELECT (rol, activa, tenant_id)` si 0027 no lo abre ya y `UPDATE (rol)` acotado por GUC (tenant, usuario). El implementer verifica contra `0002`–`0027` los nombres y restricciones exactos (índices parciales, `CHECK membresia_rol_valido`) y fija el SQL con el `security-reviewer`. Sin `DELETE`; sin `UPDATE` de `email`, `password_hash` ni `activo`.
- `tenant`: `UPDATE (nombre)` con política `FOR UPDATE` acotada a `app.plat_empresa_tenant` (Q-E1 = a); sin `UPDATE` de `activo` ni de `desactivado_*` desde estas funciones.
- GUC nuevas en C1: una en T12 (`app.plat_empresa_tenant`; la de `tenant.nombre` la reutiliza) y una en T13 (`app.plat_usuario_edicion`); y una en C1b (`app.plat_usuario_password`, §11); todas las funciones `plataforma_*` las vacían al entrar y salir (se actualiza el recuento de T7: 16 → 19 con C1 → 20 con C1b).

### 10.3 Web

- **Alta (C1c, formulario único):** `NuevaEmpresa.tsx` es **un solo formulario**: sin paso 2, sin «Paso 1 de 2» y sin barra de progreso (se retira el componente de pasos y su `Progreso`). Incluye el campo «Logo (opcional)» con `reducirLogo` y vista previa (componente compartido con Editar empresa dentro de `modulos/empresas/`). Al enviar: `POST` de creación (JSON) y, tras el `201`, si hay archivo, `apiPlataforma.subirLogo` con el `logo_id` generado al elegir el archivo (segunda llamada transparente, un solo botón y un solo estado de envío); éxito → «Empresa lista». **Fallo del logo** (`413/415/422`, `503`, `429`): la empresa ya existe, se muestra «Empresa creada; el logo no se pudo subir» con el motivo y la indicación de reintentar desde «Editar empresa»; la web recuerda que la empresa ya se creó y **nunca vuelve a llamar al `POST` de creación** (la acción pasa a «Ir a la lista»/«Editar empresa»). La contraseña sigue sin pasar por estado tras el `201` ni por el `multipart`.
- **Editar empresa:** acción «Editar» por fila en `Empresas.tsx`; `EditarEmpresa.tsx` (`Dialogo` del kit) carga `GET …/ficha` (`useQuery` con clave propia, vaciada al cerrar), usa los mismos `Campo` y mensajes del alta, deshabilita «Guardar cambios» sin cambios, y reutiliza el bloque de logo con «Tiene logo / Sin logo» y «Reemplazar logo» o «Subir logo». Sin vista previa del logo vigente (no se añade un endpoint de lectura del archivo para el desarrollador; la vista previa es del archivo recién elegido). Tras guardar se invalidan la lista de empresas y la ficha.
- **Editar usuario:** acción «Editar» por fila en `Usuarios.tsx`; `EditarUsuario.tsx` (`Dialogo`) con correo deshabilitado, `Campo` de nombre y selección de rol; cambio de rol con `Confirmar` (R52); mensajes de `409 ultimo_admin`/`empresa_inactiva`/`404`/`503`; acciones deshabilitadas en empresa desactivada, como D23. Tras guardar se invalidan la lista de usuarios y la de Empresas (conteo de admins).
- `web/src/lib/api/plataforma.ts`: `fichaEmpresa`, `guardarFichaEmpresa`, `editarUsuario`; `subirLogo` ya existe; tipos con `npm run api:types` tras editar `backend/openapi.yaml` (rutas nuevas, `409 logo_existente` retirado del logo, tres acciones nuevas en el enum, `Retry-After` del `503`). Actividad: tres etiquetas en español y las tres acciones en su `Filtro`.

### 10.4 Decisiones de diseño de C1

- **Sin `If-Match`/`412` en la edición de empresa.** La 013 (`PUT /empresa`, logo del admin) no lo usa: bloquea la fila con `SELECT … FOR UPDATE` y la última escritura gana. Se replica, con el `lock_timeout` de 5 s de T5 y T7. *Alternativa descartada:* `ETag` sobre `actualizada_en` con `428`/`412` (requeriría que el formulario del admin de la 013 lo manejara también para que sirviera de algo, y la consola es de uso poco frecuente).
- **No hay limpieza del logo anterior.** El pedido hablaba de «limpieza del archivo anterior», pero 013 R2 y la constitución §6 mandan conservarlo (los informes congelados lo sirven). La única limpieza es la del **archivo nuevo** si la transacción falla (`after_rollback` de T7). *Alternativa descartada:* borrar el anterior cuando ningún informe lo usa (requiere recorrer `sesion_empresa`, que la consola no puede leer).
- **`PUT` con los campos completos y no `PATCH` parcial** para la ficha y el usuario: el formulario siempre tiene todos los valores, evita ambigüedad entre «campo ausente» y «borrar», y encaja con `STRICT` (sentinelas). Ruta nueva `…/ficha` y no reutilizar `PATCH /empresas/{id}` (`{activa}`), para no mezclar estado y datos.
- **Un único endpoint de logo** (alta y reemplazo): el cliente ya manda `logo_id` y el servidor decide por el estado de la base.
- **El alta con logo son dos llamadas, aunque el formulario sea uno (C1c)** (JSON y `multipart`): una sola ruta `multipart` pondría la contraseña del admin junto a un archivo, ampliaría el tope de cuerpo de `/plataforma/empresas` de 4 KB a 2 MB y rompería la idempotencia por `id` de R20. *Alternativa descartada.*
- **Empresas creadas por el comando `create-tenant` y nunca completadas** no tienen fila `empresa`: la edición responde `409 empresa_sin_datos` (igual que el logo). No se hace `INSERT` de la ficha desde la edición para no abrir otra política de inserción; su admin la completa por la 013.
- **RC10 (privilegios por columna del dueño):** `UPDATE (nombre)` sobre `tenant`, `logo_id` y la ficha sobre `empresa` ensanchan todas las políticas del mismo comando; la contención es la huella de los cuerpos de las funciones y la aserción de catálogo `test_only_actualizar_empresa_renames_a_tenant`, no la RLS. Aceptado sin disparador (`reviewer` y `security-reviewer` de T12). **T13 y T16 deben pasar esa aserción** y no añadir columnas a los `UPDATE` por columna sin actualizarla.
- **Alta con logo, formulario único (C1c):** la web crea y luego sube; el fallo del logo no deshace la empresa y nunca se recrea (alternativa descartada: mantener el paso 2 con reintento en el asistente, por decisión del humano).
- **Riesgo de escalada por rol:** ver RC2 de la spec; el cambio de rol se limita a una membresía existente (no crea cuentas ni toca correo o contraseña por esta ruta; la contraseña temporal es una ruta aparte, §11).

### 10.5 Pruebas de C1

Tests primero. Backend: catálogo y migraciones (up/down/up con datos, un head, columnas exactas, GUC vacías en el pool, privilegios por columna del dueño); `test_plataforma_empresas.py`/nuevo `test_plataforma_edicion.py` (A21, A23: validaciones por campo con los casos de la 013, sin cambios → sin auditoría, `caplog` y auditoría sin valores, sesión cerrada intacta, tenant B intacto, `404`, `409 empresa_sin_datos`, `503` por candado); `test_plataforma_logo.py` adaptado (las pruebas de `409 logo_existente` pasan a reemplazo; archivo y fila anteriores intactos; informe congelado con el logo anterior sigue sirviendo; limpieza del nuevo ante `rollback`; mutación de T7 repetida); `test_plataforma_usuarios.py` ampliado (A24, A25: `ultimo_admin`, carrera de dos degradaciones, revocación solo si cambia el rol, rol efectivo inmediato, membresía desactivada editable, otra clave → `400`); matriz de roles y de tokens cruzados sobre las rutas nuevas (A2, A3). Web: Vitest de `NuevaEmpresa` (formulario único con logo opcional; **fallo parcial**: empresa creada, logo falla, aviso «Empresa creada; el logo no se pudo subir» y sin segundo `POST` de creación), `EditarEmpresa`, `EditarUsuario`, Actividad (etiquetas); e2e ampliado; capturas a 375 y 1440 px (`browser-qa`); no declarar axe. Q-E1 = (a) añade a `test_plataforma_edicion.py`: el nombre nuevo llega a `tenant.nombre` y a la lista de Empresas, no cambia si el nombre es igual, `activo` y `desactivado_*` intactos, tenant B intacto, auditoría sin valores.

## 11. Ampliación C1b (2026-11-21): contraseña temporal de un usuario

Pedido del humano; **revierte Q-A4** (decisión autónoma de «sin restablecer contraseña desde la consola»). Sin dependencias nuevas. Las preguntas Q-P1 a Q-P3 están **decididas por el humano (2026-11-21)** y T16 está desbloqueada: **Q-P1 SÍ** (cualquier usuario, incluido el único admin); **Q-P2 NO** (sin correo de aviso: no hay plantilla ni envío en T16); **Q-P3 SÍ** (membresía desactivada y usuarios con membresías en otras empresas, sin `409`; se revocan todas sus sesiones). La función no añade condiciones por ello.

### 11.1 Función y migración `0032_plataforma_password_usuario`

| Función (migración) | Efecto | Devuelve | `EXECUTE` |
|---|---|---|---|
| `acceso.plataforma_restablecer_password_usuario(p_desarrollador, p_tenant, p_usuario, p_password_hash)` (0032) | Mismo patrón y candado consultivo por tenant que `plataforma_cambiar_estado_membresia` (0027) y `plataforma_cambiar_usuario` (0031), `lock_timeout` 5 s → `55P03` → `503`. Orden de rechazos: `404` empresa → `404` usuario ajeno → `409 empresa_inactiva`. Valida el **formato** del hash Argon2id (como las de 0016/0019) y, en una transacción: `UPDATE usuario SET password_hash, debe_cambiar_password = true, sesiones_validas_desde = now()` de ese usuario; revoca todas las familias de refresh **del usuario** (no solo de la membresía) con el bucle acotado y fallo cerrado de 0027. Flask escribe la auditoría. | nada (`void`) | aplicación |

- Dueño `plataforma_owner`, `SECURITY DEFINER`, `STRICT`, `search_path = pg_catalog, pg_temp`, GUC `app.plat_usuario_password` vaciada al entrar y salir, dueño con membresía transitoria y `REVOKE CREATE` posterior, `REVOKE` a `PUBLIC`/Supabase y `GRANT EXECUTE` solo a la aplicación (como las demás).
- **Política y privilegios del dueño:** `usuario`: `UPDATE (password_hash, debe_cambiar_password, sesiones_validas_desde)` con política `FOR UPDATE` acotada a la GUC del usuario objetivo y a una membresía de ese tenant (el implementer verifica contra `0002`–`0031` los nombres exactos); **sin `SELECT` de `password_hash`** para `plataforma_owner`; la tabla de refresh de tenant: `UPDATE (revocado_en)` acotado, si 0027 no lo abre ya. El `STRICT` impide `NULL`; un hash vacío o mal formado falla antes de escribir.
- `0032` amplía también el `CHECK` `plataforma_auditoria_accion_valida` y la política `plataforma_auditoria_insertar` con `usuario_contrasena_restablecida` (misma técnica que 0030); reversible (el `downgrade` retira la función y las políticas, y restaura el `CHECK` anterior tras comprobar que no hay filas con la acción nueva o fallar con mensaje claro).
- **Catálogo A4:** la función entra a la lista cerrada (`void`, sin columnas devueltas); la prueba de políticas del dueño lista que `usuario` abre exactamente esas tres columnas y que `password_hash` nunca se puede leer.

### 11.2 Servidor (Flask)

- Ruta `POST /plataforma/empresas/{id}/usuarios/{usuario_id}/contrasena` en `app/plataforma/modulos/usuarios/routes.py`; cuerpo estricto `{password, password_confirmacion}` (`400` con otra clave); la política de contraseña es **la misma función** que el alta (`plataforma_crear_tenant`, R19) y el hash Argon2id se calcula con la misma función de `app/auth/credentials.py` **antes** de abrir la transacción de la función; el cálculo no ocurre dentro de una conexión con candado tomado (el candado lo toma la función, que es corta).
- Auditoría `usuario_contrasena_restablecida` en la misma transacción (`tenant_id`, `objeto_id` = usuario, sin valores); `auditoria.py` con la acción nueva; `plat_accion` y `no-store`; respuesta `204` sin cuerpo; `openapi.yaml` con la ruta, sus errores (`Retry-After` en `503`) y la acción nueva en el enum; `npm run api:types`.
- **Efecto en el tenant sin cambios de código en `auth`:** `load_current_user` ya lee `sesiones_validas_desde` y `debe_cambiar_password` en cada petición (0026, T4); el login ya devuelve la marca; el bloqueo `403 cambio_password_requerido` ya es central. La prueba A28 lo comprueba de punta a punta.

### 11.3 Web

- `Usuarios.tsx`: acción «Restablecer contraseña» por fila (deshabilitada en empresa desactivada o aún desconocida, como D23); `RestablecerContrasena.tsx` (`Dialogo` del kit) con dos `Campo` de contraseña (`new-password`, sin estado persistente: se leen del formulario al enviar y se vacían al responder, como `NuevaEmpresa`), `Confirmar` que nombra a la persona y la empresa, `Aviso` con el efecto, mensajes por código de error; tras el éxito se invalida la lista de usuarios (la fila pasa a «Cambio de contraseña pendiente»). Sin «Copiar» y sin guardar la contraseña en la caché de TanStack Query (la mutación no devuelve datos y no usa `variables` persistentes: `gcTime` 0 y `reset` al cerrar).
- `web/src/lib/api/plataforma.ts`: `restablecerContrasenaUsuario`. Actividad: etiqueta en español de la acción nueva y entrada en su `Filtro`.
- **Alta:** el aviso de `NuevaEmpresa` pasa de «No se vuelve a mostrar ni se puede recuperar desde la consola.» a «No se vuelve a mostrar. Si se pierde, define otra desde Usuarios.» (`cambios-docs08.md` y su prueba).

### 11.4 Decisiones de diseño de C1b

- **Contraseña temporal con marca, no cambio libre.** Reutiliza el mecanismo del alta (`debe_cambiar_password`, R25–R27): quien la define no puede usar la aplicación con ella sin cambiarla. *No impide la toma de cuenta* (RC7): se mitiga con auditoría, revocación de todas las sesiones y cierre de sesión visible para la persona; **sin correo** (Q-P2: NO, decidido por el humano). *Alternativa descartada:* enlace de restablecimiento generado por la consola (token que el desarrollador entregaría; más superficie y reutiliza la 014 con un envío manual).
- **Hash en Flask, no en SQL**; la función solo valida el formato (como el alta y las de la 014): no hay `pgcrypto` ni contraseñas en claro en la base ni en `pg_stat_statements`.
- **Revocación de todo el usuario** (no solo la membresía): la contraseña es global (`usuario.password_hash`); `sesiones_validas_desde` corta además los access tokens vigentes (el JWT de 15 min no se puede revocar de otro modo; D38/O-1).
- **No idempotente:** a diferencia de `PUT` de usuario, repetir define otra contraseña y audita de nuevo; no hay «sin cambios» posible sin conocer el hash anterior.
- **Ruta propia, no el `PUT` de usuario:** el `PUT` mantiene `400` ante una clave `password` (R47) para no mezclar datos de perfil con credenciales (cuerpo, `422`, auditoría y logs distintos).
- **Sin límite por usuario objetivo** además de `plat_accion` (por desarrollador): el freno es la auditoría visible; si el humano lo pide, es un ámbito más de `limite_tasa`.

### 11.5 Pruebas de C1b

Tests primero. Backend: `test_plataforma_usuarios.py` ampliado (A27, A28: `204`, hash cambia, marca y corte de sesión, login anterior `401`, temporal entra y recibe `403 cambio_password_requerido` en todo el `url_map` salvo la lista de R26, `422`/`400`/`404`/`409`/`503`, segunda definición, carrera con desactivar y con dos definiciones, 014 sobre una temporal pendiente, usuario con dos membresías, una desactivada y otra en otra empresa: permitido por Q-P3 y se revocan todas sus sesiones; el único admin: permitido por Q-P1; la aserción `test_only_actualizar_empresa_renames_a_tenant` sigue pasando, RC10); `caplog` y auditoría sin la contraseña, la confirmación ni el hash (se buscan los valores enviados en todas las columnas, en los logs y en la respuesta); catálogo A4/A5/A6 (`void`, sin `SELECT` de `password_hash`, GUC vacía en el pool, `tenant_session` no ejecuta); migraciones up/down/up con datos y un head; `test_openapi.py`; matriz de roles y tokens cruzados (A2, A3). Web: Vitest del diálogo y de `Usuarios` (A29), del aviso del alta y de Actividad; e2e ampliado; capturas a 375 y 1440 px (`browser-qa`); no declarar axe.

## 12. Cambio C1d (2026-11-22): aviso por correo al definir una contraseña temporal

Pedido del humano; **supera a Q-P2** (y a la alternativa descartada de 11.4 «enlace generado por la consola», que ahora no se entrega a mano: va al buzón de la persona). Sin dependencias nuevas y **sin migración**: `acceso.solicitar_recuperacion` (0016) ya crea el enlace con la elegibilidad de la 014, la aplicación ya tiene `EXECUTE`, y el canje (`acceso.restablecer_contrasena`, rehecha en 0024/0026) ya pone `debe_cambiar_password = false` (R59).

### 12.1 Servidor (Flask)

- **Correo de la persona:** dentro de la vista de C1b, en la misma `plataforma_session`, se toma de `plataforma_listar_usuarios` (R29 ya devuelve el correo; sin función nueva) y se normaliza con `recuperacion.destino_de`. Solo se lee si `correo_activo(app)`.
- **Después del `COMMIT`:** `require_desarrollador` confirma la transacción al salir de la vista; la ruta registra un `after_this_request` que actúa **solo** si la respuesta es `204` (si el `COMMIT` falla, la respuesta es `5xx` y no se pide nada). Ahí, con un token nuevo (`new_token`), llama a un envoltorio nuevo de `app/db.py`, `pedir_enlace_recuperacion(email, clave) -> bool`: conexión propia, transacción corta, `select acceso.solicitar_recuperacion(:email, :clave)`, **sin** `_sumar_intentos` (no toca `recuperar_ip` ni `recuperar_cuenta`). Un error de base se captura y se registra solo con su tipo y el `request_id`; el aviso sale entonces sin enlace.
- **Envío:** `response.call_on_close` programa `Correo.enviar_aviso_restablecimiento(destino, token | None, request_id)`, con el mismo hilo, semáforo, contador de descartes y logs sin datos que `enviar_recuperacion`. `Correo._enviar` pasa a recibir la función que compone el mensaje (refactor sin cambio de comportamiento para la 014).
- **Plantilla:** `componer_aviso_restablecimiento(remitente, destino, url_publica, token | None)` en `app/correo/plantillas.py`, con el mismo armazón HTML que la de recuperación (se extrae el marco común; el correo de la 014 no cambia byte a byte, lo fija su prueba actual), asunto y textos de R62/R63.
- `openapi.yaml`: solo la descripción del `POST …/contrasena` (aviso por correo; la respuesta no cambia).

### 12.2 Web

- `RestablecerContrasena.tsx`: la `Confirmar` añade «Le enviaremos un aviso a su correo.» (R65) y su prueba.

### 12.3 Decisiones de diseño de C1d

- **Sin migración ni función de plataforma nueva:** pedir el enlace con la función de la 014 mantiene una sola regla de elegibilidad y un solo canje. Se descartó una `acceso.plataforma_*` que creara el enlace (más superficie, otra GUC y otra huella de catálogo para lo mismo).
- **Sin los contadores de la 014:** esos contadores frenan el abuso anónimo de `/auth/recuperar`; aquí la acción ya está autenticada, auditada y limitada por `plat_accion`, y contar la IP del desarrollador lo bloquearía en su propio uso.
- **Elegibilidad de la 014 tal cual:** con una membresía desactivada o varias activas no hay enlace (el canje tampoco funcionaría); el aviso sale igual, sin enlace (R63), porque su valor principal es la señal ante una toma de cuenta (RC7).
- **Sin auditoría aparte:** el aviso es consecuencia de `usuario_contrasena_restablecida`; su entrega no es verificable (ADR-002, sin reintentos).

### 12.4 Pruebas de C1d

Tests primero. Backend: `tests/test_plataforma_usuario_aviso.py` con el correo en modo `carpeta` (A30: un mensaje, enlace que canjea y deja la marca en `false`, segunda definición invalida el enlace anterior, membresía desactivada y dos membresías sin enlace, correo apagado sin mensaje, fallo al pedir el enlace y fallo del transporte con el mismo `204`; A31: contraseña, hash, correo, token y enlace ausentes de respuesta, auditoría y `caplog`; contadores de recuperación intactos); `tests/test_correo.py` ampliado (aviso con y sin enlace; el de recuperación sin cambios). Web: prueba de componente de la frase de R65. Sin cambios de catálogo (A4) ni de migraciones: `test_plataforma_catalogo.py` y `test_migrations.py` deben seguir verdes sin tocarlos.
