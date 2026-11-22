# Plan 015 — Mejoras de uso real: activos, informe, conteo en escritorio y ficha

**Estado: implementada (T1–T10 en `develop`), cerrada el 2026-11-19 (ff5d3c7, 703fece, b48732d, 63008ea, 3477c9d, 0a83894, 1a8037c, e7b2125, d19c34c, c37a3b3); deuda en «Deuda final» de `tasks.md`.**

Parte de `spec.md` (Q1–Q11 decididas por el humano el 2026-11-18, todas en la opción recomendada; Q4 con tope de 5.000 filas). Sin migraciones, sin tablas nuevas, sin dependencias nuevas. T7–T10 siguen condicionadas a la maqueta local aprobada por el humano (Q11).

## 1. Arquitectura

Monolito modular existente (ADR-002). Todo es capa de presentación salvo dos piezas de servidor:

| Pieza | Capa | Dónde |
|---|---|---|
| Exportar activos | Servidor + web | `backend/app/activos/` (nuevo módulo `exportar.py`, ruta en `routes.py`); botón en `web/src/routes/admin/Activos.tsx` |
| Foto que desaparece | Servidor + web | `backend/app/activos/routes.py` (`_con_version`, `_error`); `web/src/lib/cambiosActivo.ts` |
| Excel del informe | Servidor | `backend/app/conteo/exportar.py` (`a_excel`) |
| Resto (diálogo, confirmación, navegación, categorías, ficha, conteo, alta) | Web | `web/src/**` |

Principios: el servidor sigue siendo la autoridad (filtros, precio, rol); la web no arma archivos ni suma; una sola ruta `/contar/**` responsiva (sin segundo módulo de conteo).

## 2. Hallazgo: por qué desaparece la foto (punto 2)

Causa localizada por lectura del código (la prueba de T1 la confirma antes de arreglar):

- `GET /activos/por-codigo` y `GET /activos/{id}` devuelven el activo con `foto` (`_con_foto`).
- `PATCH /activos/{id}`, `mover`, `estado` y `baja` devuelven `_con_version`, que **no incluye `foto`**.
- `useCambio.onSuccess` llama a `guardarEnCache`, que **reemplaza** la entrada de la caché (`setQueryData` por código e id) por esa respuesta. La ficha lee `activo.foto` de esa entrada: queda `undefined`, `FotoActivo` muestra «Sin foto». Un refetch posterior la recuperaría, por eso parece intermitente.
- El `412 version_desactualizada` (`_error`) tiene el mismo defecto: `vista(...)` sin foto.
- El mismo bug afecta mover, cambiar estado, dar de baja y reactivar, no solo editar.

**Arreglo (en dos capas, decisión técnica):** (a) servidor: `_con_version` y `_error` pasan por la misma función que `_con_foto` (una sola fuente de la forma de la ficha, con `foto` y precio solo para admin); (b) web: `guardarEnCache` fusiona (`{ ...previo, ...nuevo }`) en vez de reemplazar, de modo que un campo ausente nunca borre lo conocido. Alternativa descartada: solo invalidar la consulta (parpadeo, una petición extra y deja la causa en el contrato).

## 3. Endpoints

| Endpoint | Cambio | Rol |
|---|---|---|
| `GET /activos/exportar?formato=excel&q=&estado=&ubicacion_id=` | **Nuevo** (Q1–Q4). Declarado antes de `/<uuid:id>`. Respuesta binaria con `Content-Disposition: attachment; filename="activos-AAAAMMDD.xlsx"` (sin datos de la clínica), `no-store`, `nosniff`. Errores JSON: `400` filtro inválido, `401`, `403`, `413` si Q4 = B. | solo `admin` |
| `PATCH /activos/{id}`, `POST .../mover`, `.../estado`, `.../baja` | La respuesta (y el `412`) añaden `foto` (misma forma que `GET`). Compatible hacia atrás. | `admin` (sin cambio) |
| `GET /sesiones/{id}/informe/excel` | Mismo endpoint y firma; cambia el contenido (Q6). | `admin` (sin cambio) |
| `GET /categorias` | Sin cambio (Q10 = A). Con Q10 = B se añade `activos: int`. | ambos |

`backend/openapi.yaml` se actualiza a mano (convención del proyecto) y `npm run api:types` regenera los tipos.

## 4. Evaluación de API para categorías (punto 5)

`GET /categorias` devuelve la lista completa (sin paginar) y los nombres son cortos. Con el tamaño esperado (P6: ≤ ~2 000 activos; categorías del orden de decenas o pocas centenas) **no requiere cambio de API**: búsqueda normalizada (sin tildes ni mayúsculas) y paginación en el cliente (p. ej. 25 por página), con el estado en la URL (`?q=&pagina=`). Si el número real supera varios cientos, o si Q10 = B (conteo por categoría), sí habría cambio: parámetros `q`/`pagina` y el campo `activos` en el servidor. Agrupación por jerarquía queda fuera (el modelo no la define).

## 5. Tablas y migraciones

Ninguna. No se toca `docs/03` ni `docs/adr/`. Documentación a ajustar al decidir: `docs/01-alcance-mvp.md` (una línea: exportar la lista de activos, si Q1 = A), `docs/05-preguntas-abiertas.md` (Q1–Q11 como filas P28–P38 al cerrarse) y `docs/07` (CU de exportar activos) — por el humano o en la tarea de cierre.

## 6. Diseño por punto (resumen)

- **Exportar activos (T4).** Una función `buscar_todos(session, filtros)` comparte con `GET /activos` el mismo constructor de consulta (sin `LIMIT`); `activos/exportar.py` arma el `.xlsx` con `XlsxWriter 3.3.1` (ya fijado en 009; `strings_to_formulas=False`, `write_string` para todo texto, `write_number` desde `Decimal` con formato COP, filtro y encabezado fijo). Sin fila de total (Q3 A). Web: `Exportar` usa la misma descarga que el informe (`guardarArchivo` de `lib/informe.ts`), muestra «Exportando…», explica el error, y manda los filtros activos. Doble clic: `onDoubleClick` en `TableRow` (escritorio) → `navigate(ficha)`, ignora eventos que vienen de `a`, `button` o el menú; `Enter` con la fila enfocada (`tabIndex=0`, `role="row"` con nombre).
- **Editar como diálogo (T2).** `EditarActivo` pasa de `Sheet` a `Dialog` (`sm:max-w-2xl`, `max-h` con desplazamiento del cuerpo, pie fijo), campos en `md:grid-cols-2`. La lógica `useEdicionActivo` (412, descartar) no cambia. Confirmar reparación: `AlertDialog` en `useAlternarReparacion` solo para el destino `en_reparacion`, con texto «Sigue contando en el inventario» y botones «Sí, enviar a reparación» / «No».
- **Excel del informe (T5).** `a_excel` solo reordena y da formato a `Documento` (ya construido desde `cierre.informe`/congelado); se implementa la opción de Q6. Las pruebas de igualdad de 009/013 se mantienen y se añaden las del formato (porcentaje, hoja plana, anchos, impresión).
- **Valor → informe (T3).** El enlace del informe a «Ver valor actual» agrega `?sesion=<uuid>`; `Valor` lo lee, valida UUID y consulta el nombre de la sesión (ya en caché del listado); muestra «Volver al informe de X» y ajusta `migasDeRuta`. Sin parámetro, «Volver» usa `navigate(-1)` con respaldo a `/admin`.
- **Categorías (T6).** Barra de búsqueda con `Input` (`type=search`), `useDeferredValue`, normalización compartida con `lib/catalogo.ts` (la misma que usa el selector), paginación «‹ Anterior / Siguiente ›» como en Activos, contador de resultados. Fila con altura 44 px en móvil.
- **Ficha (T7).** Encabezado compacto (nombre, `codigo` en mono, estado, categoría, acciones principales + menú «Más»), foto grande en columna izquierda (`FotoActivo`), datos agrupados en tarjetas (Identificación, Ubicación, Compra con precio solo admin), historial a la derecha en escritorio. Una sola columna a 375 px con las acciones en pie fijo o al principio (decide la maqueta, Q11).
- **Conteo en escritorio (T8–T10).**
  - Hook `useEsEscritorio()` (`matchMedia('(min-width:1024px) and (pointer:fine)')`), probado con el mock de `src/test/matchMedia.ts`.
  - `CountShell` gana variante de escritorio: encabezado con sesión y estado de red, contenido a ancho útil, panel izquierdo (búsqueda + cola/pendientes) y derecho (verificación); en móvil conserva exactamente el shell actual.
  - `Escanear`: en escritorio, campo de captura siempre enfocado que acepta ráfaga de teclas + `Enter` (lector USB) y búsqueda por nombre/código; cámara oculta (Q7 A) o tras «Usar la cámara de este equipo» (Q7 B, recomendado). `Escaner` no se monta (no se pide permiso) mientras no se pida.
  - Entrada al conteo (Q8 A): se quita «Ir a contar» de `AdminShell` (pie de la barra lateral y menú de usuario) en `md+`; botón «Contar» en `DetalleSesion` (sesión abierta) y en la tarjeta de «Sesiones». En móvil el acceso actual no cambia. «Volver a la sesión» en el encabezado de conteo del admin.
  - Registrar activo (T10): `RegistrarActivo` y `Alta` comparten un formulario de dos columnas en escritorio; «Guardar y registrar otro» conserva lo que decida Q9; foco inicial en el código, `Enter` guarda, `CopiarDeParecido` en la columna derecha. La lógica (`altaActivo.ts`, UUID del cliente, idempotencia) no cambia.

## 7. Permisos

| Acción | admin | contador |
|---|---|---|
| Exportar activos | sí | `403` |
| Excel del informe | sí | `403` (sin cambio) |
| Editar, mover, estado, baja | sí | `403` (sin cambio) |
| Contar y registrar activos (escritorio y teléfono) | sí | sí |
| Ver precios | sí | no (el servidor los omite) |

## 8. Estrategia de pruebas

Tests primero, una tarea a la vez.

- **Backend (`backend/tests/`):** `test_activos_exportar.py` (nuevo: igualdad con la lista, filtros, roles, aislamiento de tenant, inyección de fórmulas, `Decimal`, cero filas, cabeceras, tope si Q4 = B); `test_activos_cambios.py` (la respuesta y el `412` traen `foto`); `test_exportacion_informe.py` / existentes de 009 y 013 (formato nuevo + igualdad al centavo + inmutabilidad). Comando: `cd backend && PGHOSTADDR=127.0.0.1 uv run --env-file ../.env pytest -q <archivo>`; ruff: `uv run ruff check .`.
- **Web (Vitest + Testing Library):** extender `Activos.test.tsx`, `FichaActivo.test.tsx`, `FotosActivo.test.tsx` (reproduce el fallo de la foto), `Categorias.test.tsx`, `Valor.test.tsx`, `Informe.test.tsx`, `AltaActivo.test.tsx`, `Verificar.test.tsx`/`Selector.test.tsx` (modo escritorio), `acceso.test.tsx` (menú). Comandos: `cd web && npm test`, `npm run lint`, `npm run typecheck`.
- **Navegador (skill `browser-qa`):** cada tarea de UI a **375 y 1440 px**, axe 0, consola limpia, capturas; más `npm run e2e` (010c) extendido: exportar activos, editar con foto, entrar a contar desde la sesión.
- **Maquetas (Q11 A):** T7–T10 empiezan por una maqueta local aprobada por el humano en `specs/015-mejoras-ux-escritorio/maquetas/` (no se versiona fuera de `specs/`, como la 013).

## 9. Revisiones (regla de autonomía)

| Tarea | reviewer | domain-guardian | security-reviewer |
|---|---|---|---|
| T1 foto | sí | no | sí (cambia la forma de la respuesta con precio por rol) |
| T2 diálogo y confirmación | sí | no | no |
| T3 volver al informe | sí | no | no (valida UUID en la URL; el servidor filtra por tenant) |
| T4 exportar activos | sí | **sí** (precio, dinero, universo, dados de baja) | **sí** (exportación, rol, fórmulas, tenant, cabeceras, tope) |
| T5 Excel del informe | sí | **sí** (informe/cierre, cifras congeladas, sin sumar) | **sí** (exportación; texto como texto) |
| T6 categorías | sí | no | no |
| T7 ficha | sí | no | no (misma API) |
| T8 conteo escritorio y escáner | sí | no | sí (permiso de cámara, entrada de lector, rutas `/contar`) |
| T9 contar dentro de la sesión | sí | sí (sesión abierta única, 006) | sí (guardas de rol y rutas) |
| T10 registrar activo | sí | sí (alta con precio, P11/P13, idempotencia) | sí (el contador no ve precios; duplicado) |

## 10. Riesgos

Ver `spec.md`. Adicional: el hook `useEsEscritorio` debe tolerar cambios de tamaño de ventana sin perder lo digitado (el estado vive por encima del diseño).

## 11. Alternativa descartada

**Un segundo módulo de conteo para escritorio dentro del `AdminShell`** (Q8 B): duplicaría pantallas, pruebas y reglas (verificar, sesión cerrada, idempotencia) y dejaría al contador sin versión de escritorio. Se prefiere una ruta responsiva con layout propio por ancho. También se descartó paginar categorías en el servidor (sin necesidad hoy) y generar el Excel de activos en el navegador (contradice el principio «el servidor es la autoridad» y filtrar el precio por rol sería frágil).
