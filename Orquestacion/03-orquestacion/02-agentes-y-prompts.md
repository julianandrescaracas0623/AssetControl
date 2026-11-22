# Agentes y prompts

> **Ubicación real:** `.claude/agents/*.md` y `.cursor/agents/*.md`.
> **Regla:** el prompt define rol, límites y formato de salida. El conocimiento estable vive en skills. Los dos arneses comparten el mismo cuerpo; solo cambia el frontmatter.

---

## 1. Cadena de trabajo

```text
Humano
  │  tarea + prioridad
  ▼
coordinator
  │  lee contexto, descompone, delega
  ├──► planner ──► specs/NNN/{spec,plan,tasks}.md
  ├──► implementer ──► código + tests
  ├──► reviewer ──► veredicto
  ├──► domain-guardian ──► auditoría de dominio
  └──► security-reviewer ──► auditoría de tenant, auth y datos
  ▼
Humano decide merge
```

La profundidad objetivo es 1: el coordinator delega y los especialistas no vuelven a delegar. En Claude Code se fuerza con `disallowedTools: Agent`; en Cursor se indica en el prompt. En ambos arneses, los cinco especialistas (planner, implementer, reviewer, domain-guardian, security-reviewer) llevan en su cuerpo la viñeta "No delegas en otros agentes; devuelves tu resultado al coordinator."

---

## 2. Fichas

### `coordinator`

- **Puede:** leer todo, preguntar, delegar y resumir.
- **No puede:** editar archivos.
- **Salida:** objetivo, spec, agente, tarea exacta, criterio de terminado y riesgo principal.

### `planner`

- **Puede:** escribir `specs/**`, `docs/**` y `Orquestacion/**`.
- **No puede:** tocar `backend/` ni `web/`.
- **Salida:** `spec.md` (EARS), `plan.md` (arquitectura y riesgos), `tasks.md` (≤ 10 tareas de ≤ 1 día).

### `implementer`

- **Puede:** editar código y tests, correr pruebas. Tras la aprobación del reviewer (y de security-reviewer/domain-guardian cuando aplique): crear la rama, hacer commit, hacer push de ramas `feat/*` y `docs/*` y abrir el PR con `gh pr create --base <base>`.
- **No puede:** cambiar la spec, mergear (`git merge`, `gh pr merge`), tocar migraciones, auth o precios sin aprobación, hacer push a `main` o `develop`, hacer push forzado (`--force`, `-f`, `--force-with-lease`), reescribir historial (`rebase`, `reset --hard`, `commit --amend`, `filter-branch`) ni borrar ramas remotas.
- **Salida:** tarea, estado, archivos, pruebas con resultado real, pendiente y riesgo.

### `reviewer`

- **Puede:** leer, ejecutar pruebas, emitir veredicto.
- **No puede:** editar.
- **Salida:** `APROBADO | CAMBIOS | RECHAZADO`, con hallazgos por archivo y línea.

### `domain-guardian`

- **Puede:** auditar verificaciones inmutables e idempotentes, sesiones cerradas, totales congelados, serial no único, ubicación vigente y dinero exacto.
- **No puede:** editar.
- **Salida:** `SIN VIOLACIONES | CON VIOLACIONES`.

### `security-reviewer`

- **Puede:** auditar aislamiento por tenant, roles, tokens, invitaciones, subida de archivos y datos de la clínica.
- **No puede:** editar.
- **Salida:** `APROBADO | BLOQUEANTE`. Una posible fuga entre tenants es siempre bloqueante.

---

## 3. Prompts reutilizables

### Arrancar una sesión

```text
Actúa como coordinator. Lee AGENTS.md, docs/constitution.md y MEMORY.md.
Tarea: <texto exacto de tasks.md>.
Dime a qué agente delegas, el criterio de terminado y el riesgo principal. No edites.
```

### Pedir una spec

```text
/sdd <necesidad en una frase>
```

### Implementar una tarea

```text
/sdd-implement 001 T3
```

### Cerrar

```text
/sdd-validate 001
Después actualiza MEMORY.md (máx. 50 líneas).
```

---

## 4. Cuándo un agente falla repetidamente

Casi siempre es un problema de **contexto** o de **permiso**, no del modelo. Antes de reescribir el prompt, comprueba que el agente leyó la spec, que tiene la herramienta que necesita y que la tarea cabe en un día.
