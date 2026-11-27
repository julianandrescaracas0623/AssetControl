# Cambios de documentación que deriva la spec 020 (para el humano)

El `planner` no edita `docs/01`, `docs/08` ni `docs/adr/`. Al aprobar la spec, actualizar:

> **Aplicado (2026-11-26, encargo directo del humano, que aprobó estos textos):**
> - `docs/01`: Usuarios y acceso (línea 13) y Inicio (línea 21, `[PENDIENTE]` de P25 resuelto con P38). APLICADO.
> - `docs/08`: §3.2 (`AppShell`), §3.4 nueva (ajustes visuales de T7), §4 (marco `/app/**`), §4.1, §4.2.1, §6.1 (`/contar`), §6.2 (rutas `/app` con columna de rol), §7.3, §7.7 (Activos del contador y Registrar activo unificado, incl. cierre de T5 a–d), §8 (412 del contador, Sesiones y Discrepancias del contador, detalle con `?ubicacion=`), §9 (foco de pestañas), §10 (preguntas 8 y 14). APLICADO.
> - Fuera, a propósito: «el cursor empieza en Nombre» (y cualquier texto «El cursor empieza aquí»), pendiente de decisión del humano; el `[PENDIENTE]` de ubicaciones desactivadas en el filtro del contador (spec.md, preguntas abiertas). docs/05 (P11, P25), docs/03 y docs/07 no se tocaron en este encargo.
>
> **Aplicado (2026-11-27, encargo directo del humano):**
> - `docs/02`: Componentes, modos de la aplicación web (*Conteo* `/contar/**` y *Aplicación* `/app/**` con menú por rol, alias `/admin/**`, guarda y `403` de las pantallas exclusivas del admin, Inicio del contador, edición descriptiva con lista blanca por rol, lectura de sesiones, pendientes y discrepancias sin precios); Principios, concurrencia optimista (admin o contador, 412 sin precio al contador). APLICADO.
> - `docs/05`: nota «Modificada por P36 (2026-11-25)» en P11 y «Cambiada por P38 (2026-11-25)» en P25. APLICADO.
> - Siguen sin tocar: docs/03 y docs/07.
>
> **Aplicado (2026-11-27, encargo directo del humano):**
> - `docs/07`: CU-CAT-05 (actor admin y contador; el contador solo los 7 descriptivos, `If-Match` 428/412, 400 fuera de la lista, sin precio en 200/400/412; categoría solo afecta cálculos futuros), CU-DIS-01 (contador en solo lectura y sin precios; aplicar/descartar solo admin) y CU-HIS-02 (contador sin cifras de valor ni enlace al informe). Por consistencia interna, con R7/R8 de spec.md y P36/P37: §1 tabla de actores (fila `contador`, «Puede» y «No puede») y nota de P11; §2 filas M3 y M6. APLICADO.
> - Fuera: el `[PENDIENTE]` P25 del Inicio del contador en §1 y CU-DSH-01 (no figura en esta lista para docs/07). Sigue sin tocar: docs/03.

## docs/01-alcance-mvp.md

- **Línea 13 (Usuarios y acceso):** el contador, además de contar, consultar y dar de alta, ahora corrige datos descriptivos (`nombre`, categoría, `marca`, `modelo`, `subtipo`, `serial`, `fecha_compra`; nunca precio, código, ubicación ni estado) y consulta activos, sesiones y discrepancias en solo lectura, sin precios. El resto de la escritura del catálogo sigue siendo del admin. Referenciar P36 y P37.
- **Línea 21 (Inicio):** en escritorio el Inicio del contador está en `/app`, con el mismo contenido de P25 sin precios (P38).

## docs/05-preguntas-abiertas.md

- P36, P37 y P38 ya están agregadas. Notas de P11 y P25: APLICADO (2026-11-27).
- **P11:** añadir nota «Modificada por P36: el contador corrige datos descriptivos (2026-11-25)»; la lista de reservados al admin ya no incluye editar los datos descriptivos del catálogo.
- **P25:** añadir «Cambiada por P38: en escritorio, el Inicio del contador es `/app`; en teléfono sigue `/contar`».
- **P13 y P14:** siguen abiertas y no cambian.

## docs/08-diseno-visual.md

- **§4.1 (App shell):** marco único para ambos roles con menú filtrado por rol; menú del contador (Inicio, Contar, Activos, Registrar activo, Sesiones, Discrepancias). Reemplazar la línea 150 («el menú lateral solo se muestra al `admin`; el contador que abre `/admin/**` recibe 403»): el contador ve el marco con su menú en `/app/**`; las pantallas exclusivas del admin (Usuarios, Empresa, Ubicaciones, Categorías, Valor, Informe) siguen dando 403 en servidor. `/admin/**` es alias redirigido a `/app/**`. Resolver `[PENDIENTE]` de Discrepancias (entrada propia en el menú).
- **§4.2.1 (Inicio del contador):** en escritorio vive en `/app` dentro del marco compartido, en dos columnas (ver spec 015 R8); en teléfono sigue en `/contar` a 375 px. Mismo contenido, sin precios.
- **§6.1 / §6.2 (inventario de pantallas):** marcar Activos, Ficha, Registrar activo, Sesiones y Discrepancias como compartidas por rol; Discrepancias del contador sin acciones.
- **Pregunta 14:** resuelta (el contador ve sus discrepancias y sesiones; no edita el precio; Inicio en P25/P38). La parte de «editar el precio al duplicar sin verlo» sigue abierta (P13).
- **Texto nuevo (T4, para aprobar):** cuando el 412 del contador se debe solo a un dato que no edita (p. ej. el precio), el aviso dice «Cambió un dato que no editas aquí. Tus datos siguen aquí.» sin nombrar el campo. Añadirlo a los textos del conflicto de edición.
- **Filtro por categoría (T4):** la lista de activos no lo tiene en esta spec; queda como mejora futura para ambos roles.
- **Registrar activo unificado (T5, para aprobar):** en el computador «Registrar activo» (`/app/activos/nuevo`) es la misma pantalla para los dos roles y `/contar/nuevo` redirige ahí con su query (`?codigo=` del sticker no encontrado llega cargado y el cursor empieza en Nombre); en el teléfono sigue el alta del conteo. Para el contador: la ayuda del precio dice «Después de guardar, solo lo verán los administradores.» (el texto que ya usaba el alta del conteo; el admin conserva «Solo lo ven los administradores.»); el resumen no tiene fila de precio y lleva la nota «El precio no se muestra aquí; después de guardar, solo lo ven los administradores.»; al copiar de un parecido se muestra el aviso «Se copia de …» del alta del conteo y solo se eligen ubicación y serial; no ve el interruptor «Varias unidades iguales» (conservaría su precio a la vista tras guardar). Para los dos roles, la ubicación empieza en la sala donde se está contando, si hay una («Viene de la sala donde estás contando.»), como hacía el alta del conteo en el computador. Confirmar en §7.3 / §6 de docs/08.
- **Cierre de T5 (para aprobar):**
  - (a) La sala de trabajo es la ubicación por defecto también para el **admin** en `/app/activos/nuevo` cuando eligió sala en esa pestaña (antes solo lo hacía el alta del conteo).
  - (b) En el computador se pierde el **código fijo** del alta del conteo: el código llega cargado pero es editable, con la confirmación «Revisé que coincide con el sticker: no se puede cambiar después».
  - (c) «Varias unidades iguales» queda **oculto para el contador** (conservaría su precio a la vista tras guardar).
  - (d) Si se llega desde el conteo («Crear activo con este código»), el pie muestra «Volver al conteo» en lugar de «Cancelar» y «Activo creado» lo ofrece junto a «Registrar otro» y «Ver el activo».
- **Sesiones y Discrepancias del contador (T6, para aprobar):**
  - Sesiones sin abierta: «Cuando el administrador abra una, el botón «Contar» aparece aquí y en su detalle. Mientras tanto puedes consultar y registrar activos.»; sin sesiones: «Cuando el administrador abra la primera sesión, aparecerá aquí.»; sesión cerrada: «El … por …. Ya no se puede seguir contando en ella.» (sin «Ver informe»). El nombre de una cerrada abre su detalle, no el informe.
  - Detalle de la sesión con `?ubicacion=` (ambos roles): «Pendientes por verificar en {ubicación}» y el enlace «Ver todas las ubicaciones». En el computador `/contar/pendientes` lleva ahí y el historial del conteo lleva a la ficha del activo.
  - Discrepancias del contador: descripción «… El administrador decide si se mueven o se quedan donde están.»; pestañas Por resolver, Resueltas y **Todas** (vacío: «No hay diferencias en esta sesión»); columnas «Está ahora en» y «Resolvió»; sin casillas ni acciones. El admin no cambia (dos pestañas).
  - Nota (cierre de T6): la pestaña «Todas» existe solo para el contador; es una asimetría consciente con el admin, que conserva «Por resolver» y «Resueltas» (el servidor ya acepta `todas`). `?ubicacion=` en el detalle de sesión aplica a ambos roles.
- **Ajustes visuales de T7 (designer, 2026-11-26; sin textos nuevos):**
  - Pestañas del kit (`Pestanas`): el foco es un contorno cobalto de 2 px **por dentro** de la pestaña (antes un anillo por fuera que el carril desplazable recortaba). Afecta a todas las pestañas (Activos, Discrepancias, Informe). Anotarlo en §3 (foco) / componente Pestañas.
  - Avisos (`Aviso`): un botón que es enlace dentro de la acción («Ver el activo», «Volver al conteo») ya no sale subrayado; se ve como botón secundario.
  - Detalle de sesión con `?ubicacion=`: «Ver todas las ubicaciones» se ve como enlace (cobalto oscuro y subrayado, 44 px de alto en el teléfono) en lugar de texto en negrita; el título «Pendientes por verificar en …» reparte las líneas (sin palabra huérfana a 375 px).
  - Resumen del alta: sin código, el «—» va en la fuente normal como las demás filas (antes en monoespaciada, más corto).

## docs/03-modelo-datos.md y docs/07

- docs/03: sin cambios de esquema. Mencionar, si se quiere, que `activo_evento` registra al contador como autor de ediciones.
- docs/07: CU-CAT-05 (editar activo) cambia de rol a admin y contador; CU-DIS-01 y CU-HIS-02, lectura para el contador. APLICADO (2026-11-27).
