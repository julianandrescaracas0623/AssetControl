# Modelo operativo

> **Principio:** pocas personas, varios roles, un solo flujo. El arnés reemplaza la coordinación que no existe.

---

## 1. Roles humanos

| Rol | Quién | Decide | No hace |
|---|---|---|---|
| Dueño de producto | Responsable del proyecto | Prioridad, alcance, merge a `main`, aceptación de ADR | Implementar sin spec |
| Desarrollador | Responsable del proyecto | Diseño técnico dentro de la spec | Saltarse compuertas |
| Cliente (clínica) | Administración de la clínica | Responde las preguntas de dominio (P1, P2…), valida el piloto | Acceso a datos de otros tenants |

Quien cumple varios roles **no los ejerce al mismo tiempo**. Cada sesión declara en qué rol está.

---

## 2. Roles de IA

| Agente | Puede | No puede |
|---|---|---|
| `coordinator` | Planear, delegar, preguntar, resumir | Editar archivos, ejecutar comandos destructivos |
| `planner` | Escribir `specs/**`, `docs/**` y `Orquestacion/**` | Tocar código |
| `implementer` | Editar código, correr tests | Cambiar la spec, mergear |
| `reviewer` | Leer, ejecutar pruebas, emitir veredicto | Editar |
| `domain-guardian` | Auditar verificaciones, sesiones, informes, precios | Editar |
| `security-reviewer` | Auditar tenant, auth, roles, archivos y datos | Editar |

La separación es de **permisos**, no de instrucciones. Un agente que puede editar y aprobar su propio trabajo no es un revisor.

---

## 3. Cadencia

### Semanal (60 min)

1. Revisar el estado de la fase y las preguntas abiertas de [`docs/05`](../../docs/05-preguntas-abiertas.md).
2. Elegir **una** prioridad de la semana.
3. Descomponer en tareas de ≤ 1 día.
4. Confirmar que la spec activa cubre la prioridad; si no, se escribe spec primero.

### Diaria (15 min)

1. Leer `MEMORY.md`.
2. Elegir una tarea de `tasks.md`.
3. Ejecutar el ciclo: implementar → probar → revisar.
4. Actualizar el estado de la tarea.

### Al cerrar una tarea

1. Tests verdes.
2. Diff revisado.
3. `MEMORY.md` actualizado.
4. Spec actualizada si cambió una decisión.
5. PR pequeño, con descripción y evidencia.

### Mensual (90 min)

1. Podar `MEMORY.md`.
2. Revisar si las fases del plan siguen siendo válidas.
3. Cerrar o archivar decisiones obsoletas.
4. Revisar prompts y skills contra la realidad del código.

---

## 4. Límites de trabajo en curso (WIP)

| Tipo | Límite |
|---|---|
| Features en curso | 1 |
| Specs en borrador | 2 |
| PRs abiertos | 2 |

Si se supera, se para y se cierra antes de abrir.

---

## 5. Artefactos y dueño

| Artefacto | Dueño | Frecuencia |
|---|---|---|
| `AGENTS.md` | Dueño de producto | Cambio raro |
| `docs/constitution.md` | Dueño de producto | Cambio raro |
| `MEMORY.md` | Coordinator | Cada sesión |
| `specs/NNN/{spec,plan,tasks}.md` | Planner | Por feature |
| `Orquestacion/` | Dueño de producto | Mensual |
| ADR | Dueño de producto | Por decisión |
| Runbook | Implementer | Por operación crítica |

---

## 6. Comunicación

- **Decisiones:** en el documento, no en el chat.
- **Preguntas:** una a la vez, con opciones y recomendación.
- **Bloqueos:** se declaran el mismo día.
- **Malas noticias:** primero, con datos y propuesta.
- **No:** "ya casi", "debería funcionar", "en mi máquina".

---

## 7. Cómo se usa una sesión de IA

```text
1. Abrir con el rol: "Actúa como coordinator".
2. Pegar la tarea exacta de tasks.md.
3. El coordinator lee contexto y delega.
4. El implementer cambia lo mínimo.
5. El reviewer verifica contra la spec.
6. El humano decide: merge, rechazo o nueva tarea.
7. Se actualiza MEMORY.md.
```

Lo que no se hace: pedir "mejora todo el proyecto", aceptar un diff sin leerlo, dejar que el agente elija el alcance, mezclar dos tareas en una sesión.

---

## 8. Definición de "trabajo terminado" a nivel operativo

- [ ] Cumple el criterio de aceptación de la spec.
- [ ] Tiene prueba automatizada o verificación manual documentada.
- [ ] Pasa la compuerta de dominio y, si aplica, la de seguridad.
- [ ] No rompe el aislamiento por tenant ni la idempotencia.
- [ ] Los totales de informe coinciden con la suma real.
- [ ] La documentación refleja el cambio.
- [ ] `MEMORY.md` está actualizado.
- [ ] El humano aprobó.

"Funciona" no es un criterio. "Verificado" sí.
