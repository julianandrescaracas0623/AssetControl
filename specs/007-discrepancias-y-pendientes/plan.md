# Plan 007 — Discrepancias y pendientes

> **Estado:** Implementado (T1–T8, 2026-11-14). Aprobado (G1–G3, 2026-11-14) con Q1–Q4 en la opción recomendada (`spec.md`).

## 1. Enfoque

Sin tablas nuevas: una discrepancia es la verificación vigente (R3) de un activo con encontrada ≠ esperada, y su resolución es un evento del activo (`ubicacion_cambiada` o `discrepancia_descartada`) con el `verificacion_id`. La base garantiza una sola resolución por verificación. Luego la API (lista, aplicar y descartar en lote, pendientes), después la web.

## 2. Base de datos (migración `0010_discrepancias`, T1)

- `activo_evento.tipo` suma `discrepancia_descartada`.
- Índice único parcial `activo_evento (tenant_id, verificacion_id) WHERE verificacion_id IS NOT NULL AND tipo IN ('ubicacion_cambiada', 'discrepancia_descartada')` (R4). También sirve para buscar la resolución de una verificación.
- `docs/03`: tipo nuevo, `datos` de los eventos de discrepancia y la regla de una resolución.

## 3. API (T2–T4)

| Método y ruta | Rol | Notas |
|---|---|---|
| `GET /sesiones/{id}/discrepancias?estado=` | admin | `estado` ∈ `por_resolver` (pendiente y desfasada; por defecto), `resueltas`, `todas`. Cada elemento: verificación, activo, esperada, encontrada, actual, quién y cuándo verificó, estado, y quién y cuándo la resolvió |
| `POST /sesiones/{id}/discrepancias/aplicar` | admin | `{verificaciones: [id, …] (1–100), confirmar_desfase?: bool}` → `{resultados: [{verificacion_id, resultado, activo?}]}` |
| `POST /sesiones/{id}/discrepancias/descartar` | admin | `{verificaciones: [id, …] (1–100)}` → igual |
| `GET /sesiones/{id}/pendientes?ubicacion_id=&pagina=` | ambos | Activos `activo`/`en_reparacion` sin verificación en la sesión; 50 por página; orden por ruta y código; sin precio |

- **Estado derivado (T2):** con la verificación vigente por activo (`DISTINCT ON (activo_id) … ORDER BY seq DESC`) donde encontrada ≠ esperada: `aplicada` si hay `ubicacion_cambiada` con su `verificacion_id`; `descartada` si hay `discrepancia_descartada`; `pendiente` si el activo sigue en la esperada; `desfasada` si no (incluye el caso en que ya está en la encontrada por otra vía: se muestra como desfasada con "ya está donde se vio" y se puede descartar).
- **Aplicar (T3), por verificación y en su savepoint:** activo `FOR UPDATE`; resultados `aplicada`, `desfasada` (sin `confirmar_desfase`), `ya_resuelta`, `ya_no_es_discrepancia` (no es la vigente o encontrada = esperada), `dado_de_baja`, `ubicacion_invalida` (la encontrada ya no es sala o box activos), `no_encontrada`. Al aplicar: `ubicacion_id`, `row_version + 1`, evento `ubicacion_cambiada` con `datos {antes: {id, ruta}, despues: {id, ruta}, origen: 'discrepancia', sesion}` y `sesion_id`/`verificacion_id`. Una carrera con otro admin cae en el índice único → `ya_resuelta`.
- **Descartar:** evento `discrepancia_descartada` con `datos {esperada, encontrada, sesion}`; mismos resultados salvo `dado_de_baja` y `ubicacion_invalida`, que no aplican.
- La sesión puede estar abierta o cerrada (Q1). No se exige `If-Match`: la comprobación de la ubicación esperada bajo `FOR UPDATE` es la guarda contra cambios concurrentes, y el activo cambia de versión.
- **Errores nuevos:** ninguno de nivel petición (los resultados van por elemento); `400` si la lista está vacía, tiene más de 100 o ids repetidos.

## 4. Web (T5–T7)

- **T5 `/admin/discrepancias`:** selector de sesión (la abierta o la más reciente), pestañas "Por resolver" / "Resueltas", tabla (tarjetas en el teléfono) con casilla, activo, esperada → encontrada, actual, quién y cuándo; "Aplicar" y "Descartar" por fila y para las seleccionadas; el desfase pide confirmar en un diálogo; resumen del lote en un aviso.
- **T6 Enlaces e historial:** el detalle de la sesión muestra "N diferencias por revisar" (enlace) y la lista de pendientes; el historial muestra "Ubicación cambiada (por el conteo X)" y "Diferencia descartada".
- **T7 `/contar/pendientes`:** pestañas por ubicación (la sala de trabajo primero), lista de activos pendientes con "en reparación" y enlace a verificar; "Ver más"; el Inicio enlaza a esta pantalla. Sin banda de maqueta en ninguna pantalla del conteo.

## 5. Verificación (T8)

Navegador real (375 y 1440 px): pendientes del contador; verificación en otra sala; el admin aplica en lote, descarta, confirma un desfase y lo ve en el historial; red del contador sin precio. Revisión de seguridad y de dominio.

## 6. Dependencias nuevas

Ninguna.
