# Spec 013 — Informe con los datos de la empresa y nuevo diseño de exportación

> **Estado:** Aprobada (G1–G3, 2026-11-16): Q1 **A**; Q2: **sin firmas** (decisión del humano, ver «Decisiones de G1»). Decisiones previas del humano (2026-11-15/16): los datos de la empresa salen **congelados al cierre**; PDF **estilo A «Corporativo»** (sin firmas, G1); Excel **v3** (Resumen, una hoja por categoría con el detalle de cada activo, No encontrados); campos de empresa: nombre, dirección, NIT opcional, teléfono y correo opcionales, logo opcional. Maquetas aprobadas en `maquetas/`. Depende de 008 (cierre), 009 (exportación) y 012 (almacenamiento). Plan en `plan.md`, tareas en `tasks.md`.

## Problema

El Excel y el PDF de la 009 salen sin identidad: no dicen de qué empresa son, no tienen logo, y el Excel solo trae totales: para revisar el inventario hay que ver **cada activo**, agrupado por categoría. Además, hoy el cierre congela los totales y la lista de no encontrados, pero no el detalle de lo encontrado; sin congelarlo, un Excel exportado meses después cambiaría si alguien renombra o mueve un activo.

## Usuarios

- **Admin:** completa los datos de su empresa (Ajustes → Empresa) y exporta informes con esos datos.
- **Contador:** no ve ni edita los datos de la empresa ni exporta (P5, P13).

## Alcance

- Dentro: datos de la empresa por tenant (nombre, dirección, NIT, teléfono, correo, logo), copia congelada de esos datos al cerrar una sesión, detalle congelado por activo al cerrar (encontrados y no encontrados), Excel y PDF rediseñados según las maquetas aprobadas.
- Fuera: plantillas configurables, colores por empresa, firma digital, envío por correo, marca de la clínica dentro de la app (la app sigue con la marca del producto, `docs/08`).

## Requisitos (EARS)

1. **R1 Empresa.** El admin podrá ver y editar los datos de su empresa: nombre (obligatorio, 1–120), dirección (obligatoria, 1–200), NIT (opcional; si trae dígito de verificación, debe ser correcto), teléfono (opcional, 7–30) y correo (opcional, formato válido). Si no los ha completado, el nombre por defecto es el del tenant.
2. **R2 Logo.** El admin podrá subir (PNG, JPEG o WebP, ≤ 2 MB), ver, cambiar y quitar el logo. El servidor lo vuelve a codificar en PNG sin metadatos, conserva la transparencia y lo reduce a ≤ 600 px. Los logos anteriores **no se borran**: los usan los informes congelados.
3. **R3 Congelar la empresa al cierre.** Al cerrar una sesión, el sistema copiará los datos de la empresa vigentes (incluida la referencia al logo) a la sesión; el informe y sus exportaciones usarán siempre esa copia, aunque la empresa cambie después.
4. **R4 Congelar el detalle al cierre.** Al cerrar, el sistema guardará **una fila por activo de U** (la misma lista de `cierre.universo`, R8): código, nombre, marca, serial, categoría, ubicación esperada, ubicación donde se encontró, estado físico, resultado (encontrado/no encontrado), «en reparación» y precio, con los mismos criterios de la 008 (encontrado: datos de su verificación vigente; no encontrado: los del cierre). La suma del detalle por categoría y por ubicación debe ser **igual** al desglose congelado.
5. **R5 Excel (v3).** Hojas en este orden: «Resumen» (empresa, sesión, tres cifras, por categoría y por ubicación), **una hoja por categoría** con sus activos (columnas de la maqueta v3, filtros, encabezado fijo, total), y «No encontrados». Encabezado con logo y datos congelados en cada hoja; impresión horizontal en carta con «Página X de Y». Los nombres de hoja se limpian (sin `[]:*?/\`, ≤ 31 caracteres) y se numeran si se repiten. Sin fórmulas; dinero como número con formato COP (009).
6. **R6 PDF (estilo A).** Encabezado con logo, datos de la empresa y título; fila de corte, cierre, responsable, moneda y «Informe congelado»; tarjetas de las tres cifras; tablas por categoría y por ubicación; no encontrados; nota de cómo se calculó; **sin sección de firmas** (G1); pie con empresa, sesión y «Página X de Y»; encabezado reducido desde la página 2.
7. **R7 Igualdad (009, R3).** Toda cifra exportada sigue siendo idéntica al centavo a la del informe en JSON; los archivos se arman solo desde lo congelado (sin leer `activo` ni la empresa vigente).
8. **R8 Sesiones anteriores.** Para sesiones cerradas antes de esta spec (sin detalle ni copia de la empresa), según Q1.
9. **R9 Seguridad.** Solo el admin lee y escribe la empresa y su logo (contador `403`); el logo se entrega solo por Flask (como las fotos, 012); los textos de la empresa se escriben como texto en Excel (nunca fórmula) y escapados en el PDF.
10. **R10 Web.** Pantalla «Empresa» en Ajustes (formulario y logo con vista previa). En el informe, si la empresa no está completa, un aviso con enlace: «Completa los datos de tu empresa: saldrán en los próximos informes que cierres».

## Criterios de aceptación

- A1: API de empresa (leer, editar, validar NIT con dígito, correo, logo con tipos, tamaño, transparencia y sin metadatos, contador `403`, otro tenant aislado).
- A2: cierre: la copia de la empresa y el detalle quedan guardados; cambiar después la empresa, el logo, un nombre, un precio o una ubicación **no cambia** el informe ni los archivos; sumas del detalle = desglose.
- A3: Excel leído con `openpyxl`: hojas y orden, una por categoría con sus activos y total igual al desglose, nombres de hoja limpios y únicos, logo presente, textos como texto; PDF leído con `pypdf`: datos de la empresa, cifras, sin firmas y «Página X de Y».
- A4: web: pantalla Empresa (validaciones, logo), aviso en el informe; navegador real a 375 y 1440 px, axe 0; e2e extendido (completar empresa, cerrar, exportar).

## Decisiones ya tomadas

R8 (una sola fuente), ADR-003, 008 (nombres congelados), 009 (Q1–Q3: librerías, dinero como número, carta horizontal), 012 (almacenamiento y entrega privada). Del humano: datos congelados al cierre; estilo A; Excel v3; campos de la empresa.

## Riesgos

- **Más filas al cerrar:** una por activo (~300): un `INSERT` en lote dentro de la transacción del cierre.
- **Fuente estándar del PDF (WinAnsi):** tildes y ñ bien; caracteres fuera de Latin-1 se reemplazan por «?» (como en la 009).
- **Logos que se acumulan:** se guarda uno por cada cambio (pocos KB); nunca se borran mientras una sesión los use.
- **`docs/08` decía «la marca es la del producto, no la de la clínica»:** se precisa: en la app, sí; en los informes exportados, la de la empresa.

## Decisiones de G1 (humano, 2026-11-16)

| Pregunta | Decisión |
|---|---|
| Q1 Sesiones anteriores | **A:** diseño nuevo sin hojas por categoría (nota) y datos vigentes de la empresa, rotulados. |
| Q2 Firmas | **Sin firmantes:** el PDF no lleva sección de firmas (el estilo A se toma sin ella). |

## Opciones que se presentaron en G1

| Pregunta | Opciones | Recomendación |
|---|---|---|
| Q1 Sesiones cerradas antes de la 013 | A: se exportan con el diseño nuevo, sin hojas por categoría (una nota explica que esa sesión se cerró antes de guardar el detalle) y con los datos **vigentes** de la empresa, rotulados así. B: reconstruir el detalle desde las verificaciones y los activos de hoy. | **A.** B mostraría nombres y ubicaciones de hoy como si fueran del cierre (rompe «congelado»). En tu entorno solo afecta a la sesión de prueba. |
| Q2 Firmas del PDF | A: tres líneas en blanco «Elaboró / Revisó / Aprobó» con «Nombre y cargo / C.C.». B: además, nombres y cargos configurables en Ajustes → Empresa (salen impresos bajo cada línea). | **A.** Es lo de la maqueta aprobada; B suma campos y quién firma puede cambiar entre conteos. |
