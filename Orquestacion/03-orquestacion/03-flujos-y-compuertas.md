# Flujos y compuertas

> **Regla:** una compuerta no es burocracia; es el punto donde se evita que un error barato se vuelva caro.

---

## 1. Flujo principal (SDD)

```text
[G0] Idea / necesidad
      │
      ▼
  /sdd-constitution   (si cambia un principio)
      │
      ▼
  /sdd-spec           spec.md  ──► [G1] Spec revisada
      │
      ▼
  /sdd-clarify        preguntas resueltas
      │
      ▼
  /sdd-plan           plan.md  ──► [G2] Plan aprobado
      │
      ▼
  /sdd-tasks          tasks.md ──► [G3] Tareas ≤ 1 día
      │
      ▼
  /sdd-implement      código + tests ──► [G4] Tests verdes
      │
      ▼
  /sdd-validate       revisión + evidencia ──► [G5] Merge aprobado
      │
      ▼
  MEMORY.md + docs
```

---

## 2. Flujo corto (feature pequeña)

Para cambios que no cambian una decisión ni el esquema:

```text
/feature <descripción>
  → implementer (una tarea)
  → reviewer
  → tests
  → humano aprueba
  → MEMORY.md
```

**Límite:** si el cambio toca más de 3 archivos, una migración, auth, roles o precios, deja de ser "pequeña" y va a `/sdd`.

---

## 3. Compuertas

### G0 — Entrada

- [ ] La necesidad está descrita en una frase.
- [ ] Existe un usuario afectado (admin o contador).
- [ ] No contradice el alcance ni un ADR.
- [ ] Hay un criterio de éxito.

### G1 — Spec

- [ ] Requisitos en EARS.
- [ ] Criterios de aceptación verificables.
- [ ] Fuera de alcance explícito.
- [ ] Reglas de dominio referenciadas, no redefinidas.
- [ ] Preguntas abiertas marcadas o resueltas.

### G2 — Plan

- [ ] Arquitectura compatible con `docs/02-arquitectura.md`.
- [ ] Sin dependencias nuevas sin justificación.
- [ ] Riesgos identificados.
- [ ] Estrategia de pruebas clara.
- [ ] Migraciones y reversa descritas si aplica.

### G3 — Tareas

- [ ] ≤ 10 tareas, cada una ≤ 1 día.
- [ ] Cada tarea tiene comando de verificación.
- [ ] Ordenadas por dependencia.
- [ ] La primera tarea produce algo ejecutable.

### G4 — Implementación

- [ ] Tests escritos y verdes.
- [ ] Sin cambios fuera de la tarea.
- [ ] Sin secretos ni datos de la clínica.
- [ ] Roles y tenant verificados si aplica.

### G5 — Validación

- [ ] Reviewer aprueba.
- [ ] Domain guardian sin violaciones (si aplica).
- [ ] Security reviewer sin hallazgos bloqueantes (si aplica).
- [ ] Evidencia de prueba (comando + salida o capturas a 375 px y 1440 px).
- [ ] Documentación y `MEMORY.md` actualizados.

Merge solo con G5 completa y aprobación humana.

---

## 4. Compuertas especiales

### S1 — Seguridad y tenant

Obligatoria si el cambio toca SQL, consultas o la capa de datos; autenticación, tokens o invitaciones; roles; subida de archivos o importación; exportaciones; logs que puedan contener datos de la clínica.

Sin S1 no hay merge, aunque los tests pasen.

### S2 — Datos y migraciones

Obligatoria si el cambio agrega o modifica tablas, columnas o índices; cambia una regla de cálculo histórico; o afecta datos existentes.

Requiere migración reversible (`upgrade` y `downgrade` probados) y prueba sobre una base con datos.

### S3 — Totales y dinero

Obligatoria si el cambio toca el cierre de sesión, los totales de informe, `precio_al_contar`, la exportación a PDF/Excel o cualquier suma de dinero.

Requiere: prueba de dominio que compare el total con la suma de las partes, uso de `Decimal` y verificación de que el informe de sesión no lee el precio vigente.

---

## 5. DoR — Definition of Ready

Una tarea entra a implementación solo si:

- [ ] Está en `tasks.md` con identificador.
- [ ] Tiene criterio de aceptación.
- [ ] Tiene comando de verificación.
- [ ] No depende de una decisión sin resolver (P1, P2, P10…).
- [ ] El contexto necesario está enlazado.

---

## 6. DoD — Definition of Done

Una tarea se cierra solo si:

- [ ] Criterio de aceptación cumplido.
- [ ] Tests verdes (o verificación manual documentada si no es automatizable).
- [ ] Revisión aprobada.
- [ ] Sin deuda crítica introducida.
- [ ] Documentación actualizada.
- [ ] `MEMORY.md` actualizado.
- [ ] Aprobación humana.

---

## 7. Checklist de PR

```text
[ ] Título: tipo(área): resultado
[ ] Describe el qué y el por qué
[ ] Enlaza la tarea de tasks.md
[ ] Incluye evidencia de pruebas
[ ] Marca cambios de esquema, auth, roles o precios
[ ] Un solo tema
[ ] Sin secretos ni datos de la clínica
[ ] Sin atribución de asistentes en los commits
```

---

## 8. Manejo de fallos

| Situación | Acción |
|---|---|
| Test rojo | No se avanza; se corrige o se revierte |
| Fuga entre tenants | Se detiene el merge; incidente; revisión completa |
| Verificación duplicada | Se revierte; se agrega prueba de regresión de idempotencia |
| Total de informe que no coincide | Se bloquea la entrega; prueba de regresión del cálculo |
| Migración fallida | Se restaura copia; se documenta |
| Dato real de la clínica en el repo | Se elimina del historial y se rota lo que corresponda |
| Scope creep | Se corta; nueva tarea o nueva spec |
| Agente bloqueado | Se declara el bloqueo; no se inventa |

---

## 9. Evidencia mínima por tipo de cambio

| Tipo | Evidencia |
|---|---|
| Backend | `uv run pytest` con salida y cobertura del caso |
| Aislamiento | Prueba que usa dos tenants y demuestra que el segundo no ve nada del primero |
| Web | `npm test` + capturas a 375 px y 1440 px |
| Migración | Alembic `upgrade` y `downgrade` aplicados |
| Informe | Prueba que compara el total con la suma de las partes |
| Documentación | Diff revisado y enlaces válidos |
