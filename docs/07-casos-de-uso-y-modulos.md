# 07. Módulos y casos de uso del MVP

> Base para las specs 002 en adelante. No es una spec ni un plan: no define endpoints, esquemas ni tareas. Si choca con [01-alcance-mvp.md](01-alcance-mvp.md), [02-arquitectura.md](02-arquitectura.md), [03-modelo-datos.md](03-modelo-datos.md) o un ADR, mandan ellos. Lo no decidido va como `[PENDIENTE]` (sección 6).

Decisiones ya tomadas y no reabiertas: solo online (ADR-002); cámara del celular con ZXing; una fila por unidad; `codigo` = el del sticker de código de barras, obligatorio, único por tenant, inmutable y no generado por el sistema; sin alta sin sticker (entrada manual del código como respaldo); `serial` opcional y no único; informe con tres cifras congeladas al cerrar con `precio_al_contar` (ADR-003); desglose por categoría y por ubicación y lista por activo de los no encontrados (con la marca "en reparación") congelados en la misma transacción del cierre (R9 y R9a, decisiones del 2026-11-11), con criterio simétrico y universo de cierre definido en R4 (P15, P20, P21 y dados de baja, decisiones del 2026-11-11); Inicio (dashboard) con evolución entre conteos dentro del MVP (M11, decisión del 2026-11-11); importación del Excel no se construye ahora; roles `admin` y `contador`.

## 1. Actores y roles

| Actor | Descripción | Puede | No puede |
|---|---|---|---|
| `admin` | Responsable de la clínica | Todo lo del contador; **ver precios** (ficha, historial, verificación, autocompletado, informes y exportaciones; P13); invitar usuarios; crear/editar ubicaciones y categorías; dar de alta activos y escribir el catálogo existente (editar, mover, cambiar estado, dar de baja); abrir y cerrar sesiones (P5, ver 6); ver y aplicar discrepancias; generar informes y exportar; ver el Inicio completo con valor, gráficas y evolución (M11); importar (fuera de esta entrega) | Modificar una sesión cerrada ni una verificación |
| `contador` | Personal que cuenta desde el teléfono | Iniciar sesión; escanear; consultar activos y su historial; verificar activos en una sesión abierta; **dar de alta activos escaneando un sticker nuevo y duplicar** (P11, sin revisión posterior del admin); ver discrepancias de su conteo `[PENDIENTE: alcance exacto]`; **escribir el `precio_compra` solo al dar de alta (obligatorio)**; ver su versión del Inicio sin ningún precio (M11; alcance exacto `[PENDIENTE]` P25) | **Ver precios en cualquier pantalla o respuesta de la API una vez escrito** (ni ficha, ni historial, ni verificación, ni autocompletado; P13), cerrar sesión, invitar, crear/editar ubicaciones y categorías, importar, aplicar discrepancias, generar informes, editar el catálogo existente (editar, mover, cambiar estado, dar de baja). Nadie cambia el `codigo` |
| Sistema | El servidor | Asigna `seq` y `recibido_en`, congela totales, desglose y lista de no encontrados al cerrar (R4, R9, R9a), escribe `activo_evento`, valida rol y tenant en cada petición, filtra precios por rol en el Inicio | — |
| Operador técnico | Quien despliega | Crea el `tenant` y la primera invitación `admin` por script/CLI (03: sin pantalla de alta de tenant) | No es un rol de la aplicación |

Alta por escaneo de un activo (P11, decidida el 2026-11-11, ver [05, sección D](05-preguntas-abiertas.md#d-preguntas-surgidas-de-los-casos-de-uso)): `contador` y `admin` pueden dar de alta activos escaneando un sticker nuevo (CU-CAT-02) y duplicar (CU-CAT-03), sin revisión posterior del admin. Criterio del humano: "una persona registrada o con permisos podrá registrar activos". El resto de la escritura del catálogo sigue siendo solo del admin. Riesgo asociado: ver sección 7.

Visibilidad del precio (P13, decidida el 2026-11-11, ver [05, sección D](05-preguntas-abiertas.md#d-preguntas-surgidas-de-los-casos-de-uso)): el `precio_compra` es obligatorio en el alta (nombre y precio son lo único que se teclea, C4). Solo el `admin` ve precios. El `contador` lo escribe al dar de alta y después no lo ve: ni en la ficha, ni en el historial, ni en la verificación, ni en el autocompletado, ni en ninguna respuesta de la API. Los informes y exportaciones ya son solo admin. **Requisito para las specs que toquen activos, verificaciones, historial y autocompletado (004, 005, 006, 007) y para el `security-reviewer`:** el filtrado de campos por rol se hace en el servidor (el campo no se serializa para el contador, incluidos `precio_compra`, `precio_al_contar` y `{antes, despues}` de `precio_cambiado`); ocultarlo en la UI no cuenta como seguridad. Cada endpoint afectado trae una prueba de que la respuesta al contador no contiene precios.

## 2. Mapa de módulos

| # | Módulo | Responsabilidad | Fase | Rol | Entidades | Depende de | MVP |
|---|---|---|---|---|---|---|---|
| M1 | Acceso y usuarios | Login, refresh, logout, aceptar invitación, invitar, roles, aislamiento por tenant | 1 | ambos; invitar: admin | `tenant`, `usuario`, `membresia`, `invitacion` | Fundación (spec 001) | Sí |
| M2 | Ubicaciones | Sedes, salas y boxes; jerarquía por `padre_id`; activar/desactivar | 2 | admin escribe; ambos leen | `ubicacion` | M1 | Sí |
| M3 | Catálogo de activos | Categorías (lista cerrada), alta por escaneo/manual, duplicar, autocompletado, editar, mover, estado, baja lógica | 2 | alta y duplicar: admin y contador; resto: admin | `categoria`, `activo`, `activo_evento` | M1, M2 | Sí |
| M4 | Sesiones de conteo | Abrir, listar, estado, cerrar (la lógica de totales vive en M7) | 3 | admin abre/cierra; ambos ven | `sesion_conteo` | M1, M2, M3 | Sí |
| M5 | Verificación y escaneo | Componente de escáner, resolución de `codigo`, verificar con UUID de cliente, idempotencia, reintento, 409 | 3 | ambos | `verificacion` (lee `activo`) | M3, M4 | Sí |
| M6 | Discrepancias | Listar verificaciones con ubicación encontrada distinta; aplicar (genera `ubicacion_cambiada`) | 3 | admin aplica | `verificacion`, `activo`, `activo_evento` | M5 | Sí |
| M7 | Informes y exportación | Cierre con totales, desglose y lista de no encontrados congelados (R4, R9, R9a), informe de sesión de 3 cifras, valor en tiempo real (R7), PDF y Excel | 4 | admin | `sesion_conteo`, `sesion_desglose`, `sesion_no_encontrado`, `verificacion`, `activo` | M4, M5 | Sí |
| M8 | Historial / línea de tiempo | Vista de `activo_evento` y verificaciones de un activo | 2–3 | ambos leen | `activo_evento`, `verificacion` | M3, M5 | Sí |
| M9 | Importación del Excel | Excel → pantalla de revisión → activos | 6 | admin | `importacion`, `importacion_fila`, `sesion_conteo` (`tipo=importacion`) | M3 | **No** (fuera de esta entrega; P10) |
| M10 | Fotos | Foto de activo/verificación en almacenamiento S3-compatible | — | — | `foto` | M3, M5 | **No** `[PENDIENTE]` (no figura en el alcance; ver 5) |
| M11 | Dashboard (Inicio) | Indicadores, actividad reciente, gráficas de valor por categoría y ubicación, evolución entre conteos. Solo lectura; no calcula totales de informe, los lee | 4 | admin: completo; contador: versión sin ningún precio (P13, filtrado en servidor) | Lee `activo`, `sesion_conteo`, `sesion_desglose`, `sesion_no_encontrado`, `verificacion`, `activo_evento` | M4, M7 (también M6 para discrepancias y M8 para actividad) | Sí (decisión del 2026-11-11) |

Notas: M8 nace con el evento `creado` en M3 y se completa con las verificaciones en M5. El componente de escaneo (ZXing) se construye una vez y lo usan M3 (alta por escaneo) y M5 (verificar).

## 3. Casos de uso

Convención: **Contribuye a** = criterio de éxito de [01](01-alcance-mvp.md) (C1 conteo desde el teléfono y reintento sin duplicar; C2 informe = suma de la sesión, cero diferencias; C3 historial completo; C4 alta en <30 s con nombre y precio como máximo). "—" = habilita sin cubrir un criterio directo. Todo caso aplica R1 (tenant) y valida rol en servidor.

### M1. Acceso y usuarios

**CU-ACC-01 Iniciar sesión.** Actor: admin/contador. Pre: cuenta activa con membresía activa.
1. Ingresa email y contraseña. 2. Servidor valida y emite token de acceso con un solo tenant y refresh en cookie `HttpOnly`. 3. La app redirige a `/contar` o `/admin` según rol.
Alternos: credenciales inválidas → mensaje genérico (sin revelar si el email existe); membresía inactiva → rechazo; refresh vencido → vuelve al login.
Reglas: 02 Autenticación; R1. Contribuye a: —.

**CU-ACC-02 Invitar usuario.** Actor: admin. Pre: sesión de admin.
1. Elige rol (`admin`|`contador`). 2. El sistema crea la invitación y muestra el enlace una sola vez. 3. El admin lo comparte (WhatsApp, T5).
Alternos: contador intenta invitar → 403. Reglas: se guarda solo `token_hash`; expiración. Contribuye a: —.

**CU-ACC-03 Aceptar invitación.** Actor: invitado. Pre: enlace vigente y no usado.
1. Abre el enlace. 2. Define nombre y contraseña (o la vincula si el `usuario` ya existe `[PENDIENTE]`). 3. Se crea `membresia` con el rol de la invitación, se marca `usada_en` y se inicia sesión.
Alternos: enlace vencido o ya usado → error sin crear cuenta; reuso concurrente → solo uno gana. Reglas: un solo uso. Contribuye a: —.

**CU-ACC-04 Cerrar sesión de usuario (logout).** Actor: ambos. Invalida el refresh y limpia la cookie. Contribuye a: —.

**CU-ACC-05 Desactivar usuario / membresía.** Actor: admin. `[PENDIENTE]` si entra al MVP (ver 5).

### M2. Ubicaciones

**CU-UBI-01 Crear ubicación.** Actor: admin. Pre: sesión de admin.
1. Escribe nombre, elige tipo (`sede`|`sala`|`box`) y padre (lista). 2. Se guarda `activa=true`.
Alternos: padre de otro tenant → 404; ciclo en la jerarquía → rechazo; contador → 403.
Reglas: R1; jerarquía simple. Contribuye a: C1 (prerrequisito de contar).

**CU-UBI-02 Editar / desactivar ubicación.** Actor: admin. Cambia nombre o `activa`. No se borra (baja lógica). Alternos: desactivar con activos vigentes → `[PENDIENTE]` (bloquear, o exigir moverlos). Contribuye a: —.

**CU-UBI-03 Listar ubicaciones (selector).** Actor: ambos. Lista cerrada para elegir en alta, mover y verificar; cero digitación. Contribuye a: C4.

### M3. Catálogo de activos

**CU-CAT-01 Escanear un sticker (resolver código).** Actor: contador/admin. Pre: sesión iniciada; HTTPS y permiso de cámara.
1. Abre la cámara; ZXing lee el código. 2. La app consulta por `codigo` en el tenant. 3a. Existe → abre el activo (ficha o, dentro de una sesión, la verificación: CU-VER-01). 3b. No existe → ofrece "Crear activo con este código" (CU-CAT-02; lo ofrecen ambos roles).
Alternos: cámara denegada o ilegible → CU-VER-05 (entrada manual); lectura repetida del mismo código en <1 s → una sola consulta; código de otro tenant → se trata como inexistente (R1).
Reglas: R8; 02 Flujo de conteo. Contribuye a: C1, C4.

**CU-CAT-02 Alta de activo por escaneo.** Actor: admin y contador (P11). Pre: `codigo` leído o ingresado que no existe en el tenant.
1. El `codigo` llega prellenado e inmutable. 2. Escribe `nombre` (autocompleta con lo ya registrado, sin precio para el contador) y `precio_compra` (obligatorio; ambos roles lo escriben). 3. Elige categoría y ubicación (listas cerradas; ubicación por defecto = la última usada o la de la sesión). 4. Opcionales colapsados: `serial`, marca, modelo, `subtipo`, `fecha_compra` (P7). 5. Guarda con UUID de cliente; el servidor crea `activo` y evento `creado`.
Alternos: `codigo` ya existe (carrera) → se abre el existente, no se duplica; reintento con el mismo `id` → devuelve el ya guardado (R2); sin precio o con precio inválido (no numérico, negativo) → el servidor rechaza el alta, no se guarda nada; fallo de red → aviso y reintentar.
Reglas: `precio_compra` obligatorio (P13); sin revisión posterior del admin (P11); el evento `creado` registra quién lo dio de alta (al contador no se le muestra el precio del evento); R2, R8, `codigo` único por tenant e inmutable, `serial` no deduplica, dinero `Decimal`. Contribuye a: C4.

**CU-CAT-03 Duplicar activo.** Actor: admin y contador (igual que CU-CAT-02). Pre: activo existente seleccionado y un `codigo` nuevo escaneado (o ingresado).
1. Desde la ficha elige "Duplicar" (o en el alta, "Copiar de un parecido" por búsqueda). 2. Se copian categoría, nombre, marca, modelo, subtipo, `precio_compra` y ubicación; **no** se copian `codigo`, `serial` ni historial. Para el contador el precio se copia en el servidor y no se le muestra. 3. Escanea el sticker de la unidad nueva y guarda.
Alternos: el `codigo` nuevo ya existe → se rechaza con el activo existente. `[PENDIENTE: ¿puede el contador editar el precio al duplicar? Hasta que el humano decida, no puede: hereda el del activo copiado sin verlo]`.
Reglas: R8; una fila por unidad; el copiado del precio lo hace el servidor (P13). Contribuye a: C4 (clave para reducir digitación).

**CU-CAT-04 Autocompletar y buscar.** Actor: ambos. Sugiere nombre, marca, modelo y `subtipo` desde lo registrado; búsqueda por `codigo`, nombre o `serial` (el serial solo busca, no deduplica). No devuelve precio al contador (P13); el filtrado es del servidor. Contribuye a: C4.

**CU-CAT-05 Editar activo (con conflicto de versión).** Actor: admin. Pre: ficha abierta con su `row_version`.
1. Cambia campos editables (nombre, categoría, precio, marca, etc.; **no** `codigo`). 2. La app envía con `If-Match: row_version`. 3. El servidor guarda, incrementa la versión y escribe eventos (`precio_cambiado`, `categoria_cambiada` con `{antes, despues}`).
Alternos: versión desactualizada → `412`; la app avisa y recarga conservando lo escrito para reaplicar; intento de cambiar `codigo` → rechazo; contador → 403.
Reglas: concurrencia optimista (02); `codigo` inmutable; cambios de precio no alteran sesiones cerradas ni `precio_al_contar` (ADR-003). Contribuye a: C3.

**CU-CAT-06 Mover activo.** Actor: admin. Cambia la ubicación vigente (una sola) y escribe `ubicacion_cambiada`. Es la acción directa; la vía por conteo es CU-DIS-02. Reglas: una ubicación vigente. Contribuye a: C3.

**CU-CAT-07 Cambiar estado (`activo` ↔ `en_reparacion`).** Actor: admin. Escribe `estado_cambiado`. Un activo `en_reparacion` cuenta siempre en el universo del cierre y en el total registrado; si no se verificó en la sesión, va a no encontrado con la marca "en reparación" visible en el informe, congelada al cierre en `sesion_no_encontrado` (P15 y E1, decididas el 2026-11-11; R4, R9a). También cuenta en el valor en tiempo real y en "Activos hoy" (E2, R7). Contribuye a: C3.

**CU-CAT-08 Dar de baja (baja lógica).** Actor: admin. Pre: activo no dado de baja.
1. Pide baja y confirma con motivo `[PENDIENTE: ¿motivo obligatorio?]`. 2. `estado=dado_de_baja`; evento `dado_de_baja`. 3. Ya no se puede verificar (R5a); sin verificación en una sesión queda fuera de su universo de cierre (R4) y no entra a "no encontrado"; tampoco entra al valor en tiempo real.
Alternos: sesión abierta con verificaciones previas del activo → se conservan y, en esa sesión, el activo cuenta como encontrado en el informe congelado (decisión del 2026-11-11); reactivar `[PENDIENTE]`. Reglas: nada se borra físicamente (constitución 6); `codigo` queda reservado. Contribuye a: C2, C3.

**CU-CAT-09 Gestionar categorías.** Actor: admin. Lista cerrada por tenant. Valores iniciales y quién los edita: `[PENDIENTE]` (P8; recomendación de 6 categorías no es vinculante). Contribuye a: C4.

### M4. Sesiones de conteo

**CU-SES-01 Abrir sesión de conteo.** Actor: admin (P5 análogo; quién abre `[PENDIENTE]`). Pre: existen ubicaciones y activos.
1. Indica `nombre` y `fecha_corte`. 2. Se crea `sesion_conteo` `tipo=conteo`, `estado=abierta`, `abierta_por/en`.
Alternos: ya hay una sesión abierta → `[PENDIENTE]` (¿una o varias simultáneas?). Reglas: tipo `conteo`; la `importacion` no cuenta. Contribuye a: C1.

**CU-SES-02 Ver sesión y avance.** Actor: ambos. Muestra estado y contadores de verificados / pendientes por ubicación; los pendientes son los activos `activo` o `en_reparacion` sin verificación R3 (los que caerían en no encontrado, R4). Es información de trabajo, no el informe. Contribuye a: C1.

**CU-SES-03 Cerrar sesión.** Actor: solo admin (P5). Pre: sesión `abierta`.
1. Pide cerrar; la app muestra pendientes (activos sin verificación) y discrepancias sin resolver. 2. Confirma. 3. El servidor, en una transacción, bloquea la fila de `sesion_conteo`, fija `cerrada_por/en`, elige una verificación por `(sesión, activo)` (mayor `seq`, R3) y, con una sola función de dominio (R8), calcula **una vez** la lista de activos del universo de cierre U (R4) con su condición, precio, categoría y ubicación. De esa lista inserta el desglose congelado en `sesion_desglose` (una fila por categoría y una por ubicación, con encontrado, no encontrado y total registrado en COP y en unidades; R9), inserta en `sesion_no_encontrado` una fila por cada activo no encontrado (`codigo`, `nombre`, categoría, ubicación y precio vigentes al cierre y marca `en_reparacion`; R9a, E1) y guarda `total_encontrado`, `total_no_encontrado` y `total_registrado` como la suma de esas filas; luego pasa a `cerrada`. Todo en la misma transacción: si falla una parte, no se cierra nada.
Alternos: contador → 403; ya cerrada → idempotente, devuelve el informe `[PENDIENTE: o 409]` (en ningún caso se vuelven a insertar el desglose ni la lista de no encontrados); escritura concurrente durante el cierre (verificación, alta, cambio de precio, categoría, ubicación o estado, baja) → queda entera dentro de la vista consistente del cierre o entera fuera, nunca a medias; una verificación posterior recibe `409 sesion_cerrada`. El cierre lee con una vista consistente (por ejemplo `REPEATABLE READ` o una sola consulta); el mecanismo exacto lo fija la spec 008.
Reglas: R3, R4, R5, R5a, R8, R9, R9a, ADR-003 (actualización 2026-11-11); totales, desglose y lista de no encontrados los calcula el servidor, nunca el cliente. Universo U y criterio simétrico (P15, P20, P21, decididas el 2026-11-11): encontrado → `precio_al_contar`, `categoria_al_contar` y `ubicacion_esperada_id` de su verificación R3, aunque luego se haya dado de baja; no encontrado → precio, categoría y ubicación vigentes del activo al cierre, incluidos los `en_reparacion` con marca visible "en reparación"; los `dado_de_baja` sin verificación quedan fuera. La fila de ubicación usa exactamente esa ubicación, sin agregar por sede ni sala. Prueba obligatoria: para cada dimensión, la suma de sus filas = las tres cifras de la sesión, con cero diferencias, y cada activo de U aparece en exactamente una fila por dimensión. Pruebas obligatorias de la lista (R9a): suma de `precio` = `total_no_encontrado`; número de filas = unidades no encontradas; por categoría y por ubicación coincide con las filas de `sesion_desglose`. Contribuye a: C2.

**CU-SES-04 Escribir en una sesión cerrada (rechazo 409).** Actor: contador/admin. Pre: la sesión se cerró mientras alguien contaba.
1. Se envía una verificación (o cualquier escritura asociada). 2. El servidor responde `409 sesion_cerrada` y no guarda nada. 3. La app muestra un mensaje claro ("La sesión se cerró; esta verificación no se guardó") y no ofrece reintentar.
Alternos: verificación ya guardada antes del cierre con el mismo UUID → devuelve el registro existente (R2) `[PENDIENTE: confirmar precedencia de R2 sobre R5 en el reintento tardío]`.
Reglas: R5, T6, constitución 5. Contribuye a: C1, C2.

### M5. Verificación y escaneo

**CU-VER-01 Verificar un activo escaneando (encontrado).** Actor: contador/admin. Pre: sesión `abierta`; activo existente y no dado de baja.
1. Escanea el sticker (CU-CAT-01). 2. La app muestra nombre y ubicación esperada; no muestra precio al contador (P13). El `admin` puede ver el precio de referencia, no editable. 3. La ubicación encontrada viene preseleccionada con la de la sala de trabajo; el estado físico, en `ok`. 4. Un toque en "Confirmar" envía `POST` con UUID generado en el cliente. 5. El servidor guarda con `precio_al_contar`, `categoria_al_contar`, `ubicacion_esperada_id`, `seq` y `recibido_en`. 6. Feedback inmediato y cámara lista para el siguiente.
Alternos: mismo activo ya verificado en la sesión → se avisa y se permite una nueva verificación (la de mayor `seq` gana, R3); activo `dado_de_baja` → el servidor rechaza la verificación y no guarda nada; la app lo muestra como dado de baja (R5a, decisión del 2026-11-11). Si el activo se verificó antes de darse de baja en la misma sesión, esa verificación se conserva y cuenta como encontrado (R4).
Reglas: R2, R3, R5a, ADR-003, `ocurrido_en` informativo; `precio_al_contar` lo copia el servidor y no se devuelve al contador (P13). Contribuye a: C1, C3.

**CU-VER-02 Verificar en otra ubicación.** Actor: igual. Igual que CU-VER-01 pero la ubicación encontrada difiere de la esperada.
1. La app lo detecta y pide confirmar la ubicación real (selector). 2. Se guarda como **observación**: el activo no cambia de ubicación. 3. Aparece en discrepancias (M6).
Reglas: R6. Contribuye a: C1, C3.

**CU-VER-03 Verificar con daño.** Actor: igual. Marca `estado_fisico=danado` (lista corta `[PENDIENTE]`, P8) y opcional `nota`. No cambia el `estado` del activo; si hay que pasarlo a `en_reparacion` lo hace el admin (CU-CAT-07). Contribuye a: C1, C3.

**CU-VER-04 Activo no encontrado.** Actor: contador/admin. No existe un registro "no encontrado": un activo `activo` o `en_reparacion` sin verificación al cierre cuenta como no encontrado (R4); el `en_reparacion` lleva la marca "en reparación" en el informe (P15). Al cerrar, la lista por activo de los no encontrados y su marca quedan congeladas en `sesion_no_encontrado` (R9a, E1); antes del cierre, la app muestra la lista de pendientes para revisión antes de cerrar. Nota o marca explícita de "buscado y no hallado": `[PENDIENTE]` (el modelo solo admite `ok`|`danado`). Contribuye a: C2.

**CU-VER-05 Entrada manual del código.** Actor: contador/admin. Pre: cámara denegada, sin luz o sticker ilegible.
1. Elige "Escribir código". 2. Digita el código impreso del sticker (o busca por nombre/serial, CU-CAT-04). 3. Sigue el mismo camino que un escaneo (existe → CU-VER-01; no existe → ofrece alta).
Alternos: código inexistente por error de tecleo → el alta debe pedir confirmación explícita del `codigo` (por ser inmutable). Reglas: R8 (no hay alta sin sticker). Contribuye a: C1.

**CU-VER-06 Reintento idempotente tras corte de red.** Actor: contador/admin. Pre: confirmó una verificación y la petición no tuvo respuesta.
1. La app muestra "No se pudo confirmar" y deja la verificación pendiente, visible y no confirmada. 2. El usuario toca "Reintentar" con **el mismo UUID**. 3. El servidor devuelve la verificación ya guardada, o la guarda si no había llegado; nunca duplica.
Alternos: sesión cerrada entretanto → CU-SES-04. Sin cola persistente ni offline (ADR-002): si se cierra la pestaña antes de confirmar, se pierde y se vuelve a escanear. Reglas: R2, T3. Contribuye a: C1.

### M6. Discrepancias

**CU-DIS-01 Ver discrepancias.** Actor: admin (contador `[PENDIENTE]`). Lista verificaciones de la sesión con ubicación encontrada ≠ esperada, usando la verificación R3 vigente de cada activo. Muestra activo, esperada, encontrada, quién y cuándo. Reglas: R6. Contribuye a: C3.

**CU-DIS-02 Aplicar discrepancia.** Actor: admin. Pre: discrepancia visible; la ubicación vigente del activo sigue siendo la esperada.
1. Elige "Aplicar" (individual o en lote `[PENDIENTE]`). 2. El servidor cambia la ubicación vigente y escribe `ubicacion_cambiada` con `{antes, despues}` y `verificacion_id`. 3. La discrepancia queda marcada como resuelta.
Alternos: el activo ya se movió por otra vía → aviso de desfase y no se aplica sin confirmar; aplicar sobre sesión cerrada: `[PENDIENTE]` (R5 prohíbe modificar la sesión; el cambio recae en `activo`, no en la sesión, pero hay que decidir si se permite y cómo se marca "resuelta" sin tocar la sesión). Ignorar una discrepancia: `[PENDIENTE]`.
Reglas: R6; la verificación es inmutable y no se altera. Contribuye a: C3.

### M7. Informes y exportación

**CU-INF-01 Informe de sesión (3 cifras).** Actor: admin. Pre: sesión `cerrada`.
1. Abre el informe. 2. Ve `total_encontrado`, `total_no_encontrado` y `total_registrado`, fecha de corte, sesión de referencia, y desglose por categoría y por ubicación. 3. Las tres cifras salen de `sesion_conteo` y el desglose sale de las filas de `sesion_desglose`, ambos guardados al cierre; el informe los lee y no recalcula nada con precios, categorías ni ubicaciones actuales. Ve también la **lista de no encontrados** por activo (código, nombre, categoría, ubicación y precio), con la marca visible "en reparación" en los que estaban `en_reparacion` al cierre; la lista y la marca se leen de `sesion_no_encontrado` (R9a, P15, E1) y no se reconstruyen desde `activo`. La lista contiene precios: solo el admin la ve, filtrado en el servidor (P13). Los subtotales por sede o sala, si se muestran, son una vista que suma filas de ubicación.
Alternos: sesión abierta → no hay informe `[PENDIENTE]` (¿vista previa marcada "no definitiva"?). Reglas: R3, R4, R9, R9a, P2, P13, ADR-003; dinero `Decimal`/COP. Contribuye a: C2.

**CU-INF-02 Valor total en tiempo real.** Actor: admin. Consulta sobre `activo` vigente con estado `activo` o `en_reparacion` (no los `dado_de_baja`; P15, decisión E2 del 2026-11-11; mismo criterio que el universo del cierre), con desglose por categoría y ubicación. Se rotula distinto del informe de sesión y nunca lo reemplaza ni se mezcla con él. Reglas: R7, T7. Contribuye a: C2 (separación de cifras).

**CU-INF-03 Exportar a PDF y Excel.** Actor: admin. Pre: informe disponible.
1. Elige formato. 2. El servidor genera el archivo con las mismas cifras y metadatos del informe (fecha de corte, sesión, quién cerró); el desglose sale de `sesion_desglose` (R9) y la lista de no encontrados, con su marca "en reparación", de `sesion_no_encontrado` (R9a), igual que en pantalla. 3. Descarga.
Alternos: sin datos → archivo con ceros, no error. Reglas: una sola fuente de cálculo (R8); las cifras exportadas deben ser idénticas a las de pantalla. Contribuye a: C2. Librerías de PDF/Excel: dependencia nueva, a justificar en su plan.

### M8. Historial

**CU-HIS-01 Ver historial de un activo.** Actor: ambos. Pre: activo abierto (por escaneo o búsqueda).
1. Abre "Historial". 2. Ve la línea de tiempo ordenada por `seq` (no por reloj del cliente): `creado`, `verificado` (quién, cuándo, sesión, ubicación encontrada, estado físico), `ubicacion_cambiada`, `precio_cambiado`, `estado_cambiado`, `categoria_cambiada`, `dado_de_baja`. 3. Cada cambio muestra antes/después y autor.
Visibilidad (P13): al `contador` se le ocultan los eventos `precio_cambiado` y cualquier precio dentro de otros eventos (p. ej. `creado`, `importado`); el `admin` ve todo. El filtrado lo hace el servidor.
Alternos: activo de otro tenant → 404. Reglas: eventos solo `INSERT`, escritos por el servidor. Contribuye a: C3.

**CU-HIS-02 Ver sesiones pasadas.** Actor: ambos `[PENDIENTE: contador]`. Lista de sesiones cerradas, solo lectura. Contribuye a: C3.

### M11. Dashboard (Inicio)

Decisión del humano (2026-11-11): el Inicio completo, con evolución entre conteos, entra al MVP. Es solo lectura: reúne datos de otros módulos, no escribe y no calcula totales de informe (los lee). Cada cifra la entrega el servidor (constitución 3). El `admin` ve la versión completa en `/admin`; el `contador` ve una versión **sin ningún precio**: el servidor no serializa precios, valores en COP ni datos de gráficas de valor para el contador, y cada endpoint del Inicio trae una prueba de que la respuesta al contador no contiene precios (P13). Ocultarlos en la UI no cuenta como seguridad.

**CU-DSH-01 Indicadores.** Actor: admin (completo) y contador (sin precios). Pre: sesión iniciada.
1. Abre el Inicio. 2. El servidor devuelve, según el rol:

| Indicador | Fuente | Admin | Contador |
|---|---|---|---|
| Activos hoy | Conteo en tiempo real sobre `activo` vigente con estado `activo` o `en_reparacion`, no los `dado_de_baja` (P15, E2 del 2026-11-11; R7); no es `total_registrado` de un informe (cifra congelada). Puede mostrar aparte cuántos están en reparación. Nombre "Activos hoy": decisión por defecto revisable (2026-11-11) | Sí | Sí |
| Valor actual del inventario (COP) | R7, consulta en tiempo real con el mismo criterio de estados que "Activos hoy" (`activo` o `en_reparacion`; E2); rotulado "Valor actual (no es el informe)" | Sí | **No** |
| Avance del conteo abierto: % verificado y pendientes por ubicación | Igual que CU-SES-02 (verificaciones R3 de la sesión abierta) | Sí | Sí |
| Discrepancias sin resolver | Igual que CU-DIS-01; qué es "resuelta": P14 | Sí | **No** |
| Activos dañados o en reparación | Estado `en_reparacion` vigente del activo y `estado_fisico=danado` de verificaciones; qué verificación cuenta: `[PENDIENTE]` P26. La tarjeta rotula su fuente: "estado vigente + estado físico de la sesión <nombre>" (decisión por defecto revisable, 2026-11-11) | Sí | **No** |
| Último informe cerrado: tres cifras | Lee `sesion_conteo` de la última sesión cerrada `tipo=conteo`; rotulado "Informe congelado" | Sí | **No** |

Alternos: sin sesión abierta → la tarjeta de avance dice "Sin sesión abierta" (y el admin ve "Abrir sesión"); sin sesiones cerradas → la tarjeta de último informe muestra un estado vacío, no ceros inventados; un indicador falla → solo esa tarjeta muestra error.
Reglas: R1, R3, R7, P13; el valor actual y el último informe nunca comparten tarjeta (R7). Qué más ve el contador: `[PENDIENTE]` P25. Contribuye a: C2 (separación de cifras).

**CU-DSH-02 Actividad reciente.** Actor: admin y contador.
1. El Inicio muestra los últimos eventos del tenant: altas (`creado`), verificaciones (`verificado`) y cambios (`ubicacion_cambiada`, `estado_cambiado`, `categoria_cambiada`, `precio_cambiado`, `dado_de_baja`), con fecha, usuario, evento y activo, ordenados por `seq`. 2. Cada fila enlaza al historial del activo (CU-HIS-01).
Visibilidad (P13): al contador se le omiten los eventos `precio_cambiado` y cualquier precio dentro de otros eventos, igual que en CU-HIS-01; el filtrado es del servidor. Pantalla de "Ver todo": `[PENDIENTE]` (08, decisiones de diseño).
Reglas: R1; eventos solo lectura. Contribuye a: C3.

**CU-DSH-03 Gráficas de valor por categoría y por ubicación.** Actor: admin.
1. El Inicio muestra una gráfica de valor por categoría y otra por ubicación, en COP, con las cifras que entrega el servidor. 2. Cada gráfica declara su fuente en el rótulo: **"Valor actual"** (R7, consulta en tiempo real sobre `activo` vigente con estado `activo` o `en_reparacion`, E2) **o** **"Último informe cerrado"** (lee `sesion_desglose` de esa sesión, con su fecha de corte). Una gráfica nunca mezcla las dos fuentes. Fuente por defecto: `[PENDIENTE]` P23.
Alternos: sin activos → estado vacío; contador → el servidor no entrega estos datos y la gráfica no existe en su Inicio.
Reglas: R7, R9, P13; el cliente solo dibuja, no suma. Componente: gráficos de shadcn/ui, que según su documentación se apoya en `recharts` (dependencia nueva, a aprobar en la spec 010). Contribuye a: C2.

**CU-DSH-04 Evolución entre conteos.** Actor: admin.
1. El Inicio muestra, por cada sesión cerrada de `tipo=conteo`, el valor registrado (`total_registrado`) y el % encontrado. 2. Puede verse también por categoría. 3. Todas las cifras se leen de `sesion_conteo` y `sesion_desglose`; no se recalcula nada con precios, categorías ni ubicaciones actuales, y cada punto coincide con el informe de su sesión (CU-INF-01).
Alternos: sin sesiones cerradas → "Aún no hay conteos cerrados"; una sola sesión → un punto, sin tendencia; la sesión abierta no aparece; la sesión `importacion` no aparece. Cuántos conteos se muestran por defecto: `[PENDIENTE]` P22. El % encontrado lo calcula el servidor, en unidades por defecto (si fuera en valor, con `Decimal`); decisión por defecto revisable (2026-11-11), base definitiva y precisión de presentación `[PENDIENTE]` P24 (recomendación: un decimal). Una categoría que no existía en una sesión no tiene fila para esa sesión: se muestra como ausente, no como cero inventado.
Reglas: R4, R9, ADR-003 (actualización 2026-11-11), P13. Contribuye a: C2.

## 4. Orden propuesto de specs

La 001 ya existe (fundación). Cada spec es un slice vertical (API + web + pruebas) con ≤10 tareas y deja algo demostrable. El tamaño de 004, 006, 007 y 010 es el principal riesgo: si al planificar pasan de 10 tareas, se parten, no se comprimen. La numeración desde la 010 se ajustó el 2026-11-11 al entrar el Dashboard (ninguna de esas specs existía todavía).

| Spec | Nombre | Módulos / CU | Fase | Depende de | Entrega verificable |
|---|---|---|---|---|---|
| 001 | Fundación técnica | — | 0–1 | — | `docker compose up`, `/health`, CI verde (escrita) |
| 002 | Acceso y usuarios | M1: CU-ACC-01..04; tablas `tenant`, `usuario`, `membresia`, `invitacion`; script de tenant + primer admin | 1 | 001 | Un admin invita a un contador por enlace; ambos entran; un contador recibe 403 en una ruta de admin; prueba de aislamiento entre dos tenants |
| 003 | Ubicaciones y categorías | M2 completo; CU-CAT-09 (lista y semilla) | 2 | 002 | El admin crea sede > sala > box en `/admin`; el contador las ve en un selector a 375 px y 1440 px |
| 004 | Activos: alta por escaneo | M3 parcial: CU-CAT-01..04; componente de escáner; `activo` + `activo_evento` (`creado`); entrada manual | 2 | 003 | Escanear un sticker real o simulado crea un activo en <30 s con nombre y precio; duplicado de `codigo` rechazado; reintento con mismo `id` no duplica. Mide P10 y cierra la prueba de P9/P4 con teléfonos reales |
| 005 | Ciclo de vida e historial del activo | CU-CAT-05..08; M8: CU-HIS-01 (eventos de catálogo) | 2 | 004 | Editar con `412` ante conflicto; mover, cambiar estado y baja lógica dejan evento; la ficha muestra la línea de tiempo |
| 006 | Sesiones y verificación | M4: CU-SES-01, 02, 04; M5: CU-VER-01, 03, 05, 06 | 3 | 005 | Abrir sesión y verificar activos escaneando desde el teléfono; reintento idempotente; `409 sesion_cerrada` probado; el historial muestra `verificado` |
| 007 | Discrepancias | M5: CU-VER-02, CU-VER-04; M6: CU-DIS-01, 02 | 3 | 006 | Una verificación en otra ubicación aparece en la lista; el admin la aplica y queda `ubicacion_cambiada`; la lista de pendientes ("no encontrado") está visible |
| 008 | Cierre e informe de sesión | M4: CU-SES-03; M7: CU-INF-01, 02; tablas `sesion_desglose` (R9) y `sesion_no_encontrado` (R9a) | 4 | 007 | Cerrar congela los tres totales, el desglose por categoría y ubicación y la lista de no encontrados con su marca "en reparación" en la misma transacción; la lista cuadra con `total_no_encontrado` y con el desglose; el informe coincide con la suma de verificaciones R3 con cero diferencias, aunque el precio, la categoría o la ubicación cambien después; la suma de las filas de cada dimensión = las tres cifras; valor en tiempo real separado |
| 009 | Exportación PDF y Excel | M7: CU-INF-03 | 4 | 008 | Los archivos exportados traen las mismas cifras que la pantalla (prueba de igualdad) |
| 010 | Dashboard (Inicio) | M11: CU-DSH-01..04 | 4 | 008 (009 no es requisito) | El admin ve indicadores, actividad, gráficas por categoría y ubicación con su fuente rotulada y la evolución leída de `sesion_desglose`; cada punto de la evolución coincide con el informe de su sesión; prueba de que la respuesta al contador no trae precios. Declara para aprobación la dependencia de gráficos (`recharts`, vía el componente de shadcn/ui) |
| 011 | Piloto | Guion y preparación; ajustes de UX derivados | 5 | 001–010 | Un conteo real de una sala con guion firmado contra C1–C4 |
| 012 | Importación del Excel | M9 | 6 | 004 | **Opcional**; solo si P10 se decide a favor tras medir 004. Extracto anonimizado que reproduce la suma de las hojas de categoría |

Las specs 002 y 003 son pequeñas y podrían fusionarse si el planner confirma que caben en 10 tareas; se separan por defecto para no mezclar auth con catálogo. Las 006–008 deben mantener separados el conteo y el informe (R7).

## 5. Casos de uso candidatos a quedar fuera del MVP

| Caso | Por qué queda fuera |
|---|---|
| Importar el Excel (M9) | Decidido (P10): no se construye ahora; opcional tras medir el alta |
| Conteo offline / cola persistente | Fuera de alcance; ADR-002 |
| Generar o imprimir stickers | Fuera de alcance; el `codigo` lo trae el sticker |
| Alta de activo sin sticker | Prohibido por R8 |
| Fotos de activos y verificaciones (M10) | No figura en el alcance, aunque `foto` está en el modelo y en la arquitectura; decidir si entra o se difiere `[PENDIENTE]` |
| Reconocimiento por imagen, OCR de seriales | Fuera de alcance |
| Consumibles, stock, depreciación, compras, proveedores | Fuera de alcance |
| Multisucursal con permisos avanzados | Fuera de alcance |
| Desactivar usuarios y restablecer contraseña | No hay decisión; sin proveedor de correo (T5). Mínimo viable: el admin desactiva la membresía; contraseña olvidada vía nueva invitación `[PENDIENTE]` |
| Pantalla de alta de tenant | El tenant se crea por script/CLI (03) |
| Edición masiva de activos; reportes comparativos entre sesiones más allá de la evolución del Inicio (CU-DSH-04) | No pedidos; se evalúan tras el piloto. La evolución entre conteos sí entra (decisión del 2026-11-11) |
| Pistola lectora | Sin pistola lectora en el MVP (P4) |

## 6. Preguntas abiertas / [PENDIENTE]

| # | Tema | Impacto | Recomendación por defecto (no vinculante) |
|---|---|---|---|
| P11–P19 | Preguntas surgidas de estos casos de uso; P11, P13 y P15 decididas (2026-11-11; P15 completa: cierre y tiempo real, E2), el resto abiertas. La marca "en reparación" se congela en `sesion_no_encontrado` (E1, R9a) | 002–008 | Texto, estado y recomendación en [05, sección D](05-preguntas-abiertas.md#d-preguntas-surgidas-de-los-casos-de-uso) |
| P20–P26 | Desglose congelado (ubicación y categoría) y Dashboard (conteos en la evolución, fuente de las gráficas, base del % encontrado, Inicio del contador, "dañados"); P20 y P21 decididas (2026-11-11, criterio simétrico, R4); P22–P26 abiertas | 008, 010 | Ver [05, sección D](05-preguntas-abiertas.md#d-preguntas-surgidas-de-los-casos-de-uso) |
| P5 | ¿Quién cierra la sesión? (P5 abierta) | 008 | Solo admin |
| P9 | Formato, tamaño y numeración de stickers; prefijo del código; impresora/proveedor | 004, 011 | Probar con teléfonos reales antes de comprar el lote (Code 128 como candidato). El sistema acepta cualquier texto como `codigo` mientras no se decida lo contrario |
| P4 | Teléfonos y navegadores del personal | 004, 011 | Probar en los teléfonos reales |
| P7 | `fecha_compra` (¿se captura?, ¿obligatoria?) | 004 | Opcional |
| P8 | Categorías iniciales y lista de `estado_fisico` | 003, 006 | 6 categorías; `ok`/`danado` |
| P3, P6, P10 | Fecha del último conteo, volumen esperado, importación | 012 | Ver [05](05-preguntas-abiertas.md) |
| T9, T10 | Nombre del repo, hosting | 011 | Ver [05](05-preguntas-abiertas.md) |

P11–P26 viven en [05-preguntas-abiertas.md, sección D](05-preguntas-abiertas.md#d-preguntas-surgidas-de-los-casos-de-uso), con su numeración original.

## 7. Riesgos

| Riesgo | Mitigación disponible | Otras opciones |
|---|---|---|
| Alta por el contador con precio y sin revisión (P11): un dato mal digitado entra al informe de valor total | El admin puede corregir el precio (CU-CAT-05): genera `precio_cambiado` con antes/después y no altera sesiones cerradas ni `precio_al_contar` (ADR-003). El historial (`creado`) muestra quién dio de alta | `[PENDIENTE]` filtro de "altas recientes" para el admin. No decidido |

Con P13 el riesgo se mantiene y se agrava: el contador no puede verificar su propio precio después, porque no lo ve. La mitigación es la corrección del admin con evento `precio_cambiado` antes/después.
