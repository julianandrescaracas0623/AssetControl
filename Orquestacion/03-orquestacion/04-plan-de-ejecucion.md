# Plan de ejecución

> **Horizonte:** MVP hasta el piloto en la clínica. Sin fechas todavía: se estiman después de responder P1, P4 y P6 en [`docs/05`](../../docs/05-preguntas-abiertas.md).

---

## 1. Regla de secuencia

```text
Fundación → Acceso → Catálogo y alta → Conteo → Informe → Dashboard → Piloto
                               └──────────────────────────────────→ Importación (opcional)
```

La numeración de specs es la de [`docs/07`, sección 4](../../docs/07-casos-de-uso-y-modulos.md#4-orden-propuesto-de-specs) (001–012); si cambia allí, se cambia aquí.

No se paraleliza lo que depende de lo anterior. La importación del Excel solo se hace si, tras probar el alta con poca digitación, resulta más barata que dar de alta todo por escaneo.

---

## 2. Fases y specs

| Fase | Spec prevista | Entregable | Verificación |
|---|---|---|---|
| 0. Definición | — | Docs 01–06, ADR, constitución, orquestación | Enlaces válidos, ADR indexados |
| 1. Fundación | `001-fundacion-tecnica` | Repo reproducible, API con `/health`, web base con Tailwind y shadcn/ui, CI y hooks | `uv run pytest`, `npm test`, CI verde |
| 1. Acceso | `002` Acceso y usuarios | Login, invitación, roles `admin`/`contador`, aislamiento por tenant | Un contador recibe 403 en ruta de admin; prueba de aislamiento entre dos tenants |
| 2. Catálogo y alta | `003` Ubicaciones y categorías | Sede > sala > box; lista cerrada de categorías | El contador ve el selector a 375 px y 1440 px |
| 2. Catálogo y alta | `004` Activos: alta por escaneo | Escáner, alta con autocompletar y duplicar, entrada manual | Alta por escaneo < 30 s; `codigo` duplicado rechazado; reintento sin duplicar |
| 2. Catálogo y alta | `005` Ciclo de vida e historial | Editar (`412`), mover, estado, baja lógica, línea de tiempo | Cada cambio deja evento |
| 3. Conteo | `006` Sesiones y verificación | Abrir sesión, verificar idempotente, `409 sesion_cerrada` | Flujo de conteo (móvil primero) a 375 px y 1440 px; reintento sin duplicar |
| 3. Conteo | `007` Discrepancias | Lista de discrepancias y pendientes; aplicar | Aplicar deja `ubicacion_cambiada` |
| 4. Informe | `008` Cierre e informe de sesión | Cierre con totales y desglose por categoría y ubicación congelados (R4, R9), valor en tiempo real separado | Total = suma de las partes y suma de filas por dimensión = tres cifras, cero diferencias |
| 4. Informe | `009` Exportación PDF y Excel | Archivos con las cifras del informe | Igualdad con la pantalla |
| 4. Dashboard | `010` Dashboard (Inicio) | Indicadores, actividad, gráficas por categoría y ubicación, evolución entre conteos | Cada punto de la evolución = informe de su sesión; respuesta al contador sin precios |
| 5. Piloto | `011` Piloto | Un conteo real en la clínica | Guion de piloto firmado; criterios 1–4 de `docs/01` |
| 6. Importación (opcional) | `012` Importación del Excel | Excel → revisión → activos | Total importado = suma de hojas de categoría |

Cada fila se abre como spec solo cuando la anterior pasó G5.

---

## 3. Preguntas que bloquean cada fase

| Fase | Pregunta | Recomendación por defecto |
|---|---|---|
| 2 | P1 unidad vs lote | **Decidida (2026-11-11):** una fila por unidad física con el `codigo` del sticker; sin lotes (R8) |
| 2 | P8 categorías y estados | 6 categorías cerradas; estado `ok` / `dañado` |
| 3 | P4 teléfonos y navegadores | Probar el escáner en los teléfonos reales antes de la fase 3 |
| 4 | P2 qué suma el informe | **Decidida:** tres cifras (encontrado, no encontrado, total registrado) |
| 4 | P15, P20, P21 universo y desglose del cierre | **Decididas (2026-11-11):** universo U y criterio simétrico de R4 en `docs/03` |
| 4 | P22–P26 Dashboard | Ver `docs/05`, sección D |
| 6 | P10 importar o partir de cero | Decidir tras la fase 2 |

---

## 4. Criterios de salida del MVP

Los cuatro de [`docs/01-alcance-mvp.md`](../../docs/01-alcance-mvp.md):

1. Un conteo de una sala completo desde el teléfono; cada verificación queda guardada y un reintento no duplica.
2. El informe de valor total coincide con la suma de los activos de la sesión, con cero diferencias.
3. Cada activo muestra su historial completo.
4. Dar de alta un activo por escaneo toma menos de 30 s y exige escribir solo nombre y precio.

---

## 5. Criterio para reabrir el offline

Si en el piloto más de un conteo se interrumpe por falta de red, se escribe un ADR de PWA con cola de reintentos (sobre el mismo cliente web). Antes, no.

---

## 6. Siguientes pasos inmediatos

1. Responder P1, P2 y P10.
2. Aceptar los ADR 001–004.
3. Aprobar `specs/001-fundacion-tecnica/spec.md`.
4. Instalar los hooks (`sh scripts/setup-hooks.sh`) y publicar el repositorio.
5. `/sdd-implement 001 T1`.
