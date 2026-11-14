# Plan 006 — Sesiones de conteo y verificación

> **Estado:** Aprobado (G1–G3, 2026-11-14) con Q1–Q4 en la opción recomendada (`spec.md`).

## 1. Enfoque

Base, luego la API (sesiones, después verificar, con su contrato en cada tarea), después la web: administración de sesiones, Inicio del conteo y verificar. Sin dependencias nuevas.

## 2. Base de datos (migración `0009_sesiones_y_verificacion`, T1)

**`sesion_conteo`:** `id uuid PK DEFAULT gen_random_uuid()`, `tenant_id`, `nombre` (1–120), `tipo text CHECK IN ('conteo','importacion') DEFAULT 'conteo'`, `estado text CHECK IN ('abierta','cerrada') DEFAULT 'abierta'`, `fecha_corte date NOT NULL`, `abierta_por uuid NOT NULL` (FK compuesta a `membresia`), `abierta_en timestamptz DEFAULT now()`, `cerrada_por uuid NULL`, `cerrada_en timestamptz NULL`, `CHECK ((estado = 'cerrada') = (cerrada_en IS NOT NULL))`. `UNIQUE (tenant_id, id)`. **Q1:** índice único parcial `(tenant_id) WHERE estado = 'abierta' AND tipo = 'conteo'`. Los totales y el desglose los agrega la 008 con el cierre.

**`verificacion`:** `id uuid PK` (del cliente), `tenant_id`, `sesion_id`, `activo_id`, `ubicacion_esperada_id`, `ubicacion_encontrada_id`, `estado_fisico text CHECK IN ('ok','danado')`, `precio_al_contar numeric(14,2) NOT NULL CHECK >= 0`, `categoria_al_contar uuid NOT NULL`, `nota text NULL` (1–120), `verificado_por uuid NOT NULL`, `ocurrido_en timestamptz NULL` (reloj del cliente), `recibido_en timestamptz DEFAULT now()`, `seq bigint GENERATED ALWAYS AS IDENTITY`. FK compuestas a sesión, activo, ubicación (las dos), categoría y membresía. `UNIQUE (tenant_id, id)`. Índice `(tenant_id, sesion_id, activo_id, seq)` (R3).

**`activo_evento`:** FK compuestas de `sesion_id` y `verificacion_id` (estaban sin FK desde la 0007).

**Seguridad:** RLS forzada; `sesion_conteo` con `INSERT` de `tenant_id, nombre, fecha_corte, abierta_por` y sin `UPDATE` (cerrar llega con la 008); `verificacion` con `INSERT` de las columnas del cliente y de la copia, sin `seq` ni `recibido_en`, y sin `UPDATE` ni `DELETE` nunca.

## 3. API (T2–T4)

| Método y ruta | Rol | Notas |
|---|---|---|
| `POST /sesiones` | admin | `{nombre, fecha_corte}`; `201`; `409 sesion_abierta_existente` |
| `GET /sesiones` | ambos | Todas, la abierta primero y luego por `abierta_en` descendente |
| `GET /sesiones/abierta` | ambos | `{sesion: … | null}` |
| `GET /sesiones/{id}` | ambos | Sesión con su avance: `{total, verificados, pendientes, por_ubicacion: [{ubicacion: {id, ruta}, total, verificados, pendientes}]}` |
| `POST /sesiones/{id}/verificaciones` | ambos | `{id, activo_id, ubicacion_encontrada_id, estado_fisico, nota?, ocurrido_en?}`; `201` nueva, `200` reintento (Q3) |
| `GET /sesiones/{id}/verificaciones?activo_id=` | ambos | La última verificación R3 del activo en la sesión o `null` (para el aviso de R8) |

- **Verificar, en una transacción:** idempotencia primero (`id` existente con el mismo activo y sesión → `200`, Q3); candado consultivo **compartido** de la sesión y luego su lectura (`404` si no es del tenant; `409 sesion_cerrada` si no está abierta) — ajuste de T3: `FOR SHARE` exige `UPDATE` sobre la tabla y la aplicación no lo tiene hasta la 008; el cierre tomará el mismo candado **exclusivo**; activo con `FOR SHARE` (`404`; `409 activo_dado_de_baja`); ubicación encontrada sala o box activa (`400 ubicacion_invalida`); copia de precio, categoría y ubicación del activo bloqueado; `verificacion` y evento `verificado` (`datos`: ubicación esperada y encontrada con ruta, estado físico, nota; sin precio). Carrera con el mismo `id` → el índice único y relectura, como en la 004.
- **Avance:** una consulta: activos `activo`/`en_reparacion` agrupados por su ubicación vigente, y cuántos de ellos tienen al menos una verificación en la sesión.
- **Respuesta de una verificación:** `id, sesion_id, activo {id, codigo, nombre}, ubicacion_esperada {id, ruta}, ubicacion_encontrada {id, ruta}, estado_fisico, nota, verificado_por {id, nombre}, ocurrido_en, recibido_en, seq` y, solo para el admin, `precio_al_contar`.
- **Errores nuevos:** `sesion_abierta_existente` (409), `sesion_cerrada` (409). Se reutilizan `ubicacion_invalida`, `activo_dado_de_baja`, `no_encontrado`.
- **Historial:** `verificado` se muestra como "Verificado en {encontrada}" (con "en otra ubicación" si difiere), estado físico y nota.

## 4. Web (T5–T8)

- **T5 `/admin/sesiones`:** lista (abierta destacada, cerradas debajo con "Informe en la 008"), "Abrir sesión" (nombre sugerido "Conteo {mes año}", fecha de corte hoy), detalle con avance por ubicación. El botón "Cerrar" no aparece hasta la 008.
- **T6 Inicio del conteo:** sesión abierta real con avance y pendientes por ubicación (cifras); sin sesión, estado vacío con "Consultar activos". "Estás contando en" se recuerda en la pestaña (`sessionStorage`, con respaldo en memoria). Sin la sección de actividad reciente (llega con la 010). La cabecera de todas las pantallas de conteo muestra la sesión y la sala reales.
- **T7 Verificar:** la ficha resuelta + aviso de "ya verificado" + estado físico + nota + "Está en otra ubicación" con las ubicaciones reales; "Confirmar" envía con un `id` creado al abrir la pantalla y reutilizado al reintentar. Estados: confirmado (pantalla verde con el avance de la sala y "Escanear siguiente"), no confirmado (reintentar con el mismo `id` o descartar), sesión cerrada (sin reintento), dado de baja (sin confirmar). Sin sesión abierta o sin sala elegida, muestra el activo y pide abrir sesión o elegir sala.
- **T8 Limpieza:** la banda "Datos ficticios" deja de salir en `/contar` (solo queda en Pendientes, que llega con la 007); se retiran las rutas de maqueta `verificado/:codigo` y `no-confirmado/:codigo` (sus estados viven en Verificar).

## 5. Verificación (T9)

Navegador real contra el backend (375 y 1440 px, consola y axe): el admin abre; el contador elige sala, escanea con la cámara simulada y confirma; avance; corte de red y reintento sin duplicar; "ya verificado"; sesión cerrada mientras cuenta (se cierra con el migrador, porque cerrar llega con la 008); dado de baja; red del contador sin precio. Revisión de seguridad y de dominio.

## 6. Dependencias nuevas

Ninguna.
