# Plan 013 — Informe con los datos de la empresa y nuevo diseño de exportación

> **Estado:** Propuesto (G1 pendiente). Escrito con Q1 A y Q2 A.

## 1. Enfoque

Primero los datos (empresa, copia al cierre y detalle por activo), después el cierre que los llena desde la **misma** lista U, luego los dos archivos a partir del documento intermedio de la 009 (ampliado) y al final la web. Sin dependencias nuevas: XlsxWriter, reportlab y Pillow ya están.

## 2. Datos (T1, migración `0014_empresa_y_detalle`)

- `empresa` (una por tenant): `tenant_id` PK, `nombre`, `direccion`, `nit` null, `telefono` null, `correo` null, `logo_id` null, `actualizada_en`, `actualizada_por`. RLS por tenant; la app: `SELECT`, `INSERT` y `UPDATE` de sus columnas (solo el admin, en la aplicación).
- `empresa_logo`: `id` (del cliente), `tenant_id`, `clave`, `bytes`, `ancho`, `alto`, `subido_por`, `creado_en`; solo `INSERT`/`SELECT` (nunca se borra: R2).
- `sesion_empresa` (copia al cierre, una por sesión): `sesion_id` PK compuesta con el tenant, `nombre`, `direccion`, `nit`, `telefono`, `correo`, `logo_id` null; solo `INSERT`/`SELECT` y solo para sesiones cerradas (mismo disparador `conteo_cerrado_requerido` de la 0011).
- `sesion_detalle` (una fila por activo de U): `sesion_id`, `activo_id`, `codigo`, `nombre`, `marca` null, `serial` null, `categoria_id`, `categoria_nombre`, `ubicacion_id` (esperada) y `ubicacion_ruta`, `encontrada_ruta` null, `estado_fisico` null, `encontrado` bool, `en_reparacion` bool, `precio`; único `(tenant_id, sesion_id, activo_id)`; solo `INSERT`/`SELECT` y solo con la sesión cerrada.
- Revocar todo a los roles de Supabase (C8); `docs/03`.

## 3. API de empresa (T2, blueprint `empresa`, solo admin)

- `GET /empresa` → `{empresa: {nombre, direccion, nit, telefono, correo, logo: {id} | null, completa}}` (sin fila: nombre del tenant y `completa: false`).
- `PUT /empresa` (JSON ≤ 4 KB): valida R1; NIT normalizado a `900.123.456-7` (dígito de verificación por módulo 11 con los pesos de la DIAN; sin dígito se guarda sin él).
- `PUT /empresa/logo` (multipart, ≤ 2 MB): `procesar_logo` (tipo por contenido, ≤ 40 MP, PNG con transparencia, ≤ 600 px, sin metadatos) → almacenamiento (`<tenant>/<logo>.png`; la expresión de claves admite `.png` solo para logos) → `empresa_logo` y `empresa.logo_id`. `DELETE /empresa/logo` deja `logo_id` nulo (el archivo queda: R2). `GET /empresa/logo/{id}` (admin; también los logos congelados de su tenant).
- Contrato OpenAPI y matriz de roles.

## 4. Cierre e informe (T3)

- `FilaU` suma `marca`, `serial`, `encontrada_ruta` y `estado_fisico` (de la verificación vigente) en la **misma** consulta de `universo`.
- `cerrar` inserta en lote `sesion_detalle` (todas las filas de U) y `sesion_empresa` (la empresa vigente, o el nombre del tenant si no hay fila) en la misma transacción que el desglose.
- `cierre.informe` suma `empresa` (de `sesion_empresa`, o vigente con `vigente: true` para sesiones anteriores, Q1 A) y `detalle_disponible`. El detalle no va en el JSON del informe: lo lee el exportador (`cierre.detalle(sesion)`), ordenado por categoría, resultado y código.
- Pruebas: igualdad detalle ↔ desglose (por categoría y por ubicación, dinero y unidades); cambios posteriores no alteran nada; sesión sin activos.

## 5. Exportación (T4–T5)

- `exportar.Documento` suma `empresa` (con los bytes del logo leídos del almacenamiento, o nada) y `detalle` por categoría.
- **Excel (T4):** maqueta v3 en código: `_encabezado(ws)` común (logo con `insert_image` desde bytes, empresa, sesión, «Informe congelado»), hoja «Resumen», hojas por categoría (`_nombre_hoja`: quita `[]:*?/\`, recorta a 31, numera repetidos y evita «Resumen» y «No encontrados»), «No encontrados». `write_string` para todo texto; números desde `Decimal`.
- **PDF (T5):** estilo A: `ConPaginas` con pie y encabezado reducido; tabla de cabecera con logo (`ImageReader` desde bytes); tarjetas; tablas; nota; firmas con `KeepTogether`.
- Pruebas con `openpyxl` y `pypdf` (A3) y con la sesión anterior a la 013 (Q1 A).

## 6. Web (T6–T7)

- `lib/empresa.ts` (`useEmpresa`, `useGuardarEmpresa`, `useSubirLogo`, `useQuitarLogo`); ruta `/admin/empresa` («Ajustes → Empresa» en el menú): formulario con validación en vivo (NIT con dígito), logo con vista previa (blob con la sesión, como las fotos), «Cambiar» y «Quitar».
- Informe: aviso si `empresa.completa` es falso (enlace a Empresa); rótulo «Datos de la empresa vigentes» para sesiones anteriores.

## 7. Verificación (T8)

Navegador real (375 y 1440 px): completar la empresa con logo, cerrar una sesión, exportar los dos archivos y comprobarlos contra el JSON; cambiar la empresa y el logo después y exportar de nuevo: idénticos. e2e extendido. Revisión de seguridad (rol, tenant, subida del logo, textos en Excel/PDF) y de dominio (una sola fuente, congelado, igualdad).

## 8. Riesgos

Ver `spec.md`.
