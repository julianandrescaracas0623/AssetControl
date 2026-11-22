# Spec 014 — Recuperar contraseña por correo

> **Estado:** Cerrada (2026-11-19). Aprobada (G1–G3, 2026-11-19, decisión humana); T1–T9 en `develop` (ver `tasks.md`, «Deuda final» y «Pendiente del humano»). **Decisión humana (2026-11-19):** la contraseña olvidada se recupera **por correo con SMTP**. Resuelve la parte «recuperar contraseña» de P17 (`docs/05`) y se aparta de T5 («invitaciones por enlace sin proveedor de correo») **solo para esta función**: las invitaciones siguen igual (enlace compartido por WhatsApp).
> **Depende de:** spec 002 (login, refresh con familias, invitaciones con token de un solo uso y doble hash, Argon2id, `normalize_email`, `limite_tasa`, CSRF `X-AssetControl-CSRF`, política de contraseña 10–128 con comunes, funciones `acceso.*` con `auth_owner`), spec 002b (pantallas de acceso), spec 016 (kit y `MarcoAcceso`), `docs/01`–`docs/03`, ADR-001 (RLS), ADR-002 (sin colas).
> **Convención:** `[PENDIENTE]` = decisión humana sin tomar. `[DECIDIDO]` = decisión humana. `[RECOMENDADO]` = decisión técnica del planner, con su porqué en `plan.md` §10.

## Problema

Quien olvida su contraseña hoy no tiene salida: no existe «cambiar» ni «recuperar» (002 lo dejó fuera, P17) y la única vía sería que un admin lo invite de nuevo, pero el correo ya existe como `usuario` y la invitación fallaría (Q16). El administrador de una clínica pequeña podría quedar sin acceso a su propio inventario.

## Usuarios

| Usuario | Necesidad |
|---|---|
| `admin` / `contador` que olvidó su contraseña | Pedir un enlace a su correo y fijar una contraseña nueva sin ayuda de nadie |
| Atacante anónimo (a modelar) | No debe poder saber qué correos existen, adivinar enlaces, spamear buzones ajenos ni mantener sesiones tras el cambio |
| Operador | Configurar el SMTP por variables de entorno; en desarrollo leer los correos en una carpeta |

## Alcance

### Incluye

- Enlace «¿Olvidaste tu contraseña?» en `/login` y dos pantallas públicas: `/recuperar` (pide el correo) y `/restablecer` (fija la contraseña nueva, token en el fragmento `#`).
- Endpoints públicos `POST /auth/recuperar` y `POST /auth/restablecer`.
- Tabla `recuperacion_contrasena` (con `tenant_id`, RLS forzada) y dos funciones `SECURITY DEFINER` en el esquema `acceso` (mismo patrón A1 de 002).
- Ampliar `limite_tasa` con tres ámbitos nuevos (`recuperar_ip`, `recuperar_cuenta`, `restablecer_ip`).
- Módulo de correo con dos destinos: carpeta local de desarrollo (`.eml`) y SMTP con TLS obligatorio fuera de desarrollo, usando solo `smtplib`/`email`/`ssl` de la biblioteca estándar.
- Al restablecer: invalidar todas las familias de refresh del usuario y cualquier otro enlace de recuperación pendiente.
- Contrato `backend/openapi.yaml` y tipos (`npm run api:types`).
- Pruebas de backend y web; e2e opcional con el buzón en carpeta.

### No incluye

- Cambiar el flujo de invitaciones; cambiar la contraseña estando con sesión (pantalla de perfil); 2FA; «recordar dispositivo»; cambios de roles; desactivar usuarios (resto de P17).
- Elegir el proveedor de correo de producción: el despliegue está pospuesto por el humano; la spec deja la configuración SMTP lista por variables y documenta qué falta elegir (host, credenciales, remitente verificado con SPF/DKIM).
- Correo de aviso «tu contraseña cambió», correos con imágenes, plantillas por clínica, idiomas distintos del español. (El correo HTML con la marca del producto entró después: ver R6, decisión humana del 2026-11-22.)
- Dependencias nuevas (ni de backend ni de web). Colas, Celery o reintentos persistentes (constitución §1, ADR-002).
- Auto-login tras restablecer (ver R10).
- Invalidar el JWT de acceso ya emitido (vive hasta 15 min; es la deuda N4/A11 de 002, pendiente de decisión humana y no se amplía aquí).

## Requisitos (EARS)

1. **R1 — Solicitar.** Cuando alguien envíe `POST /auth/recuperar` con `{email}` (cuerpo ≤ 4 KB, `email` cadena), el sistema debe responder **siempre** `202` con el mismo cuerpo y cabeceras, exista o no el correo, esté o no el usuario o su membresía activos, haya o no fallado el envío.
2. **R2 — Cuándo se envía.** Cuando el correo normalizado (`normalize_email`) pertenezca a un `usuario` con `activo = true` y **exactamente una** membresía activa, el sistema debe crear un token de recuperación y enviar el correo. En cualquier otro caso (correo inexistente o no normalizable, usuario inactivo, membresía desactivada, ninguna o más de una membresía activa) no crea token ni envía nada y responde igual (R1). *Aclaración de cierre (T8/T9):* tampoco reciben enlace los correos que no son una dirección simple ASCII *dot-atom* (con `%`, `!`, parte local entre comillas dobles, `..` o caracteres no ASCII): misma respuesta, sin enlace. La regla «una membresía activa» es la misma de Q6 (el login falla cerrado con varias).
3. **R3 — Token.** El token debe ser aleatorio de alta entropía (`secrets.token_urlsafe(32)`, 256 bits), con el mismo doble hash que 002 (I1): la app calcula `clave = sha256(token)`, la base guarda `sha256(clave)` en `bytea(32)`; nunca se guarda ni se registra el token. Vence a los **30 minutos** (`expira_en`, fijado por la base) y es de un solo uso.
4. **R4 — Un solo enlace vivo.** Cuando se cree un token nuevo para un usuario, el sistema debe invalidar el pendiente anterior (`invalidada_en`) en la misma transacción; un índice único parcial garantiza como máximo un enlace pendiente por usuario.
5. **R5 — Enlace.** El correo debe llevar `{URL_PUBLICA}/restablecer#<token>`. La base `URL_PUBLICA` sale de la configuración, **nunca** de la cabecera `Host` ni de datos de la petición. El token va en el fragmento (como Q13 de 002): no viaja al servidor ni queda en logs de acceso; la web lo lee una vez, lo guarda solo en memoria y reemplaza la URL sin él.
6. **R6 — Correo.** El correo debe ir en español, con asunto fijo, remitente configurable (`CORREO_REMITENTE`), el enlace, su vigencia (30 minutos) y la frase de que se ignore si no lo pidió. No incluye nombre de la clínica, de la persona, rol ni datos de inventario. El destinatario es el correo normalizado de la solicitud. **Formato (decisión humana, 2026-11-22):** `multipart/alternative` con el texto plano primero y una versión HTML con la marca del producto («Grafito y Cobalto», [docs/08](../../docs/08-diseno-visual.md)): botón «Elegir nueva contraseña» y el enlace visible como respaldo. El HTML solo usa estilos en línea y tablas, sin imágenes, fuentes, hojas de estilo ni recursos externos; el único destino de red es el enlace de R5. Sigue sin datos de la clínica ni de la persona.
7. **R7 — Destino del correo.** Cuando `CORREO_MODO=carpeta` (solo `ENVIRONMENT=development`), el sistema debe escribir un `.eml` por correo en `CORREO_CARPETA` (por defecto `backend/.buzon/`, ignorada por git). Cuando `CORREO_MODO=smtp`, debe enviar por SMTP con TLS obligatorio (`starttls` o `ssl`, contexto por defecto con verificación de certificado), con tiempo límite de 10 s por operación. Fuera de desarrollo `carpeta` no se admite y un SMTP sin TLS tampoco. Sin `CORREO_MODO` la app arranca con la recuperación **desactivada**: sigue respondiendo `202` (R1), no crea token ni envía y lo avisa una vez en el log al arrancar. *Aclaración de cierre (T4/T8):* con el correo desactivado la ruta responde el mismo `202` **sin tocar la base** (no cuenta límites ni crea o invalida enlaces), igual para todos los correos. *Implementado (T8):* además del tiempo límite por operación, cada entrega SMTP tiene un plazo total de 45 s y exige TLS 1.2 o superior.
8. **R8 — Envío sin bloquear ni revelar.** El envío debe ocurrir en un hilo simple (`threading.Thread`, acotado por un semáforo) lanzado **después** de confirmar la transacción, de modo que el tiempo de respuesta no dependa de que el correo exista ni del SMTP. Si el envío falla (tiempo, rechazo, TLS), el solicitante no se entera; se registra solo el tipo de error y el `request_id`, sin correo, token, host ni credenciales. No hay reintentos automáticos: el usuario puede pedir otro enlace (R4).
9. **R9 — Restablecer.** Cuando alguien envíe `POST /auth/restablecer` con `{token, password}`, el sistema debe, en una sola operación atómica de base de datos (`acceso.restablecer_contrasena`): consumir el token (vigente, no usado, no invalidado), comprobar que el usuario sigue activo y con exactamente una membresía activa, guardar el hash Argon2id nuevo, **revocar todas las familias de refresh del usuario**, e invalidar cualquier otro enlace pendiente del usuario. Si cualquier paso falla, todo se revierte y el token queda sin usar. Token vencido, usado, invalidado, inexistente o de una cuenta ya no elegible: mismo `400` `enlace_invalido`, indistinguible.
10. **R10 — Sin auto-login.** Tras restablecer, la respuesta es `204` sin sesión ni cookie. La web lleva a `/login` con el aviso «Tu contraseña se actualizó. Inicia sesión con la nueva.» `[RECOMENDADO]`: así tener acceso al buzón no entrega por sí solo una sesión, y la primera entrada pasa por el login y su límite de tasa. (002 sí emite sesión al aceptar una invitación; aquel caso crea la cuenta, este recupera una existente.)
11. **R11 — Contraseña.** La contraseña nueva debe cumplir la política de 002 (R12/Q9): 10 a 128 caracteres y rechazo de la lista de comunes, con los mismos códigos `contrasena_*`. El cuerpo máximo es 4 KB y la contraseña se valida **antes** de hashear.
12. **R12 — Límites de tasa.** El sistema debe limitar con `limite_tasa` (ventana de 15 min, contadas todas las peticiones, existan o no, sin oráculo): `recuperar_ip` 10, `recuperar_cuenta` 3 y `restablecer_ip` 10 (referencia, ajustables con `RATE_LIMIT_*`). Superado: `429` genérico igual que 002. Si no se puede contar: `503` sin tocar la cuenta, Argon2 ni el correo. El límite se aplica **antes** de buscar la cuenta, de Argon2 y de cualquier función `acceso.*`.
13. **R13 — Igualdad de respuesta y tiempo.** `/auth/recuperar` debe hacer la misma secuencia de trabajo en los casos existe, no existe y usuario o membresía desactivados (*aclaración de cierre:* sin envío configurado no se toca la base, ver R7, y la respuesta es igual para todos los correos, así que no hay oráculo): la función de base ejecuta las mismas sentencias (insertando 0 o 1 fila) y el envío va fuera de la petición. `/auth/restablecer` hashea siempre la contraseña antes de consultar el token (mismo costo para válido e inválido).
14. **R14 — Protección de origen.** Los dos endpoints deben exigir la cabecera `X-AssetControl-CSRF: 1` y comprobación de mismo sitio (`is_same_site_request`), con `403` antes de mirar el cuerpo, igual que refresh y logout. No usan cookies; la barrera evita que otro sitio use el navegador de una víctima para hacer mail-bombing.
15. **R15 — Aislamiento.** La tabla `recuperacion_contrasena` debe llevar `tenant_id`, RLS forzada y `tenant_isolation` `TO` el rol de aplicación; la aplicación **no recibe ningún privilegio directo** sobre ella (ni `SELECT`): todo pasa por las funciones `acceso.*`. Ninguna función devuelve token, hash ni datos de otras cuentas. Nada se borra (sin `DELETE`).
16. **R16 — Logs y cabeceras.** No se registran tokens, claves, hashes, contraseñas ni correos completos (solicitud, restablecimiento, hilo de envío ni errores SMTP). `/auth/*` mantiene `Cache-Control: no-store` y `Referrer-Policy: no-referrer` y el límite de 4 KB. La respuesta de `/auth/recuperar` no incluye ni el correo recibido.
17. **R17 — Web.** `/recuperar` y `/restablecer` deben usar `MarcoAcceso` y el kit (`Campo`, `Boton`, `Aviso`), móvil primero a 375 px, estados de carga/éxito/error, errores genéricos y accesibles (etiquetas, `aria-live` para avisos, foco al primer error). `/restablecer` muestra la política con `ayudaFija` y un botón mostrar/ocultar contraseña como la pantalla de invitación.
18. **R18 — Configuración.** Todas las credenciales y datos de correo vienen de variables de entorno (`CORREO_MODO`, `CORREO_REMITENTE`, `CORREO_CARPETA`, `SMTP_HOST`, `SMTP_PUERTO`, `SMTP_USUARIO`, `SMTP_CLAVE`, `SMTP_CIFRADO`, `URL_PUBLICA`); ninguna con valor en el repositorio. Configuración inválida (modo desconocido, SMTP incompleto, `URL_PUBLICA` sin `https` fuera de desarrollo, `carpeta` en producción) falla al arrancar con un mensaje que no imprime secretos.

## Criterios de aceptación

| # | Criterio | Verificación |
|---|---|---|
| A1 | Correo existente, inexistente, no normalizable, usuario inactivo, membresía inactiva y usuario con dos membresías activas: `202` con cuerpo y cabeceras idénticos; solo el existente y elegible crea una fila y un correo | `pytest` |
| A2 | La diferencia de tiempo entre correo existente e inexistente no es distinguible (el envío corre en un hilo; las dos rutas hacen las mismas sentencias) | `pytest` (relación de medianas, con tolerancia como A10 de 002) |
| A3 | El token del correo restablece una vez; el segundo uso, el vencido (reloj de base adelantado o `expira_en` forzado), el invalidado por uno nuevo y el inexistente dan el mismo `400 enlace_invalido` | `pytest` |
| A4 | Un enlace nuevo invalida el anterior; solo existe un pendiente por usuario (índice parcial); dos peticiones concurrentes dejan exactamente uno vivo | `pytest` (dos conexiones) |
| A5 | Tras restablecer: el login con la contraseña vieja falla y con la nueva funciona; todas las familias de refresh del usuario quedan revocadas (`/auth/refresh` → `401`); otros enlaces pendientes quedan invalidados; no se emite sesión ni cookie | `pytest` |
| A6 | Contraseña corta, larga (>128), común o cuerpo > 4 KB: rechazada sin consumir el token ni hashear (cuerpo grande: `413`) | `pytest` |
| A7 | Si falla cualquier paso de `restablecer_contrasena`, nada cambia (hash viejo, refresh vivos, token sin usar) | `pytest` |
| A8 | Superar `recuperar_cuenta` (3), `recuperar_ip` (10) o `restablecer_ip` (10) da `429` genérico, también para correos inexistentes; el contador sobrevive al fallo de la petición; sin base para contar, `503` | `pytest` |
| A9 | Sin la cabecera `X-AssetControl-CSRF` o con `Sec-Fetch-Site: cross-site`: `403` y no se cuenta ni se crea nada | `pytest` |
| A10 | Catálogo cerrado (A2 de 002): la tabla nueva tiene `tenant_id`, RLS forzada, `tenant_isolation`, ningún `DELETE` ni `GRANT` directo a la aplicación, `anon`, `authenticated` ni `service_role`; las funciones nuevas están en la lista cerrada (`prosecdef`, dueño `auth_owner`, `search_path` fijo, `EXECUTE` solo para la aplicación); las políticas del dueño forman una lista cerrada | `pytest` |
| A11 | Aislamiento: con el tenant A fijado, la aplicación no ve ni toca filas de B ni de A en la tabla (sin `GRANT`); `acceso.restablecer_contrasena` con un token de B nunca revoca refresh de A | `pytest` |
| A12 | `caplog` y salida estándar sin token, clave, hash, contraseña ni correo completo en solicitud, restablecimiento, fallo de SMTP y hilo de envío | `pytest` |
| A13 | Con SMTP caído (conexión rechazada, tiempo agotado, certificado inválido) la respuesta sigue siendo el mismo `202`, a tiempo, y el log tiene solo tipo y `request_id` | `pytest` (servidor falso y socket cerrado) |
| A14 | Modo carpeta: se escribe un `.eml` UTF-8 con asunto, remitente, destinatario y enlace `…/restablecer#<token>`; el nombre de archivo no contiene el correo; `carpeta` en producción y SMTP sin TLS fallan al arrancar | `pytest` |
| A15 | El enlace usa `URL_PUBLICA` aunque la petición traiga `Host` o `X-Forwarded-Host` manipulados | `pytest` |
| A16 | `/recuperar` y `/restablecer` a 375 px: etiquetas, foco, estados y mensajes genéricos; `/restablecer` quita el token de la URL; enlace sin token o rechazado muestra «Enlace vencido o ya usado» con salida a pedir uno nuevo; tras éxito va a `/login` con aviso | `vitest` + navegador real (`browser-qa`) |
| A17 | `backend/openapi.yaml` describe ambos endpoints y `npm run api:types` deja `schema.d.ts` sin diferencias | CI / local |
| A18 | `git grep` sin secretos; `.env.example` lista las variables nuevas sin valores; `backend/.buzon/` ignorada por git | `git grep` |
| A19 | Las demás pantallas y el flujo de invitaciones no cambian (suites existentes verdes) | `pytest` + `npm test` |

## Reglas de dominio

- **El token es de la persona, no de una clínica, pero se guarda con su tenant.** `usuario.password_hash` es global; el enlace se liga a la única membresía activa del usuario para que la tabla cumpla la regla multi-tenant (`tenant_id`, FK compuesta a `membresia`). Con más de una membresía activa no se envía (R2), igual que el login falla cerrado (Q6).
- **Sin oráculo de cuentas** en respuesta, tiempo, logs ni límites (R1, R12, R13, R16).
- **Un solo uso, 30 minutos, un enlace vivo por usuario**; solo se guarda `sha256(sha256(token))`.
- **Cambiar la contraseña cierra todas las sesiones** (revocación de todas las familias de refresh del usuario).
- **Nada se borra:** los tokens usados, invalidados o vencidos se conservan marcados.
- Ninguna dependencia nueva; correo con la biblioteca estándar.

## Riesgos

| Riesgo | Mitigación |
|---|---|
| Enumeración de correos por respuesta, tiempo o límites | R1, R12, R13; el trabajo igual en todos los casos; envío fuera de la petición; contadores que cuentan todo |
| Toma de cuenta por buzón comprometido o enlace filtrado | 30 min, un uso, un enlace vivo, doble hash, token en fragmento, sin auto-login, revocación de todas las sesiones |
| Host header injection en el enlace | `URL_PUBLICA` desde configuración (R5, A15) |
| Mail-bombing a un tercero | `recuperar_cuenta` 3 por 15 min, `recuperar_ip`, cabecera CSRF y mismo sitio, un enlace vivo por usuario |
| Bloqueo del correo de una víctima (alguien agota su cupo de 3) | Aceptado: solo retrasa 15 min; el login no se ve afectado |
| Hilo de envío perdido si el worker se reinicia | El usuario pide otro enlace (R4); sin colas por ADR-002 |
| Hilos sin control bajo carga | Semáforo acotado + límites de tasa; si no hay cupo se descarta y se registra el tipo |
| SMTP sin TLS filtra el enlace en tránsito | TLS obligatorio fuera de desarrollo, certificado verificado (R7) |
| Archivos `.eml` de desarrollo con enlaces válidos | Solo `development`, carpeta fuera de git, correos ficticios; nunca datos reales |
| JWT de acceso emitido sigue vivo ≤ 15 min tras restablecer | Deuda N4/A11 de 002 (pendiente de decisión humana); el rol y `activa` se leen de la base en cada petición; el refresh sí queda revocado |
| H-2 (email global antes de un segundo tenant) cambiaría el modelo de `usuario` | La función resuelve por `usuario` con una sola membresía activa; si se decide email por tenant, esta spec se revisa (`/sdd-change`) antes de ese segundo tenant |
| Proveedor SMTP de producción sin elegir | No bloquea: configuración lista por variables; falta host, credenciales y remitente verificado (SPF/DKIM) cuando se decida el despliegue |
| Ampliar el `CHECK` de `limite_tasa` falla en un `downgrade` con filas de los ámbitos nuevos | Prueba de `upgrade`/`downgrade`/`upgrade` y manejo explícito de esas filas en T1 |

## Preguntas abiertas

Ninguna de producto, dominio ni precios. Las decisiones técnicas están tomadas en `plan.md` §10 con su porqué.

**Bloqueos:** ninguno. **Condición previa (la misma mecánica que 002): CUMPLIDA** (2026-11-19): los cambios 1–2 de «Cambios en docs» ya están aplicados en `docs/03`.

### Cambios en docs (esta spec NO los edita)

Los cambios 1–4 ya están aplicados (1–2 en `docs/03`, 3 en `docs/05`, 4 en `docs/07`). Quedan para la T9 el 5 (`docs/08`), el 6 (`docs/09` y `docs/10`) y el 7 (`.env.example`).

1. **`docs/03` — nueva fila en la tabla de entidades:** `recuperacion_contrasena` | `id`, `tenant_id`, `usuario_id`, `token_hash`, `expira_en`, `usada_en`, `invalidada_en`, `creado_en` | Enlace de recuperación de un solo uso, 30 minutos. Se guarda `sha256(clave)` con `clave = sha256(token)` (mismo formato `bytea(32)` que `invitacion`). FK compuesta `(tenant_id, usuario_id)` → `membresia`. Índice único parcial `(usuario_id) WHERE usada_en IS NULL AND invalidada_en IS NULL` (un enlace vivo por usuario). Sin `GRANT` directo a la aplicación: se opera por `acceso.solicitar_recuperacion` y `acceso.restablecer_contrasena`.
2. **`docs/03` — `limite_tasa`:** ampliar el `CHECK` de `ambito` con `'recuperar_ip'`, `'recuperar_cuenta'`, `'restablecer_ip'` y los umbrales de referencia (10, 3 y 10 por 15 min).
3. **`docs/05`:** P17 «Decidida (2026-11-19, spec 014)» en la parte de recuperar contraseña (por correo, enlace 30 min, un solo uso); siguen abiertos desactivar usuarios y vincular un usuario existente a otro tenant. T5: añadir «Las invitaciones siguen sin correo; la **recuperación de contraseña sí usa correo** (spec 014)».
4. **`docs/07`:** fila «Desactivar usuarios y restablecer contraseña» (línea ~244): «Restablecer contraseña: por correo con enlace de 30 min (spec 014). Desactivar usuarios: sigue pendiente (P17)». Añadir CU-ACC-06 «Recuperar contraseña» con el flujo de R1–R10.
5. **`docs/08`:** pantallas `/recuperar` y `/restablecer` en la tabla de rutas (junto a `/login`), textos de estados (genérico «Si el correo está registrado, te enviamos un enlace…», «Enlace vencido o ya usado. Pide uno nuevo.», «Tu contraseña se actualizó. Inicia sesión con la nueva.»).
6. **`docs/09` y `docs/10`:** las nueve variables de R18 (en `docs/10`: valores de desarrollo `CORREO_MODO=carpeta`, `URL_PUBLICA=http://localhost:5173`, buzón en `backend/.buzon/`; en `docs/09` §5: `CORREO_MODO=smtp` y variables SMTP, `URL_PUBLICA` con `https`) y la lista de lo que falta elegir (proveedor, remitente verificado, SPF/DKIM). En `docs/10`, cómo leer los `.eml` y que hay que borrarlos al terminar.
7. **`.env.example`:** nombres sin valores (lo hace T9; no se edita `.env`).
