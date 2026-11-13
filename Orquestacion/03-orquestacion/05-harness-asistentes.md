# Arneses de asistentes

> **Qué es:** la configuración real que hace que los agentes trabajen con contexto, permisos y compuertas.
> **Dónde vive:** `.claude/`, `.cursor/`, `CLAUDE.md`, `AGENTS.md`, `docs/constitution.md`, `MEMORY.md` y `specs/`.

---

## 1. Un método, dos formatos

El método es el mismo para los dos asistentes. Lo que cambia es el formato nativo de cada uno:

| Asistente | Punto de entrada | Configuración | Reglas permanentes |
|---|---|---|---|
| Claude Code | `.claude/` | `.claude/settings.json` | `CLAUDE.md` (importa `AGENTS.md`) |
| Cursor | `.cursor/` | `.cursor/rules/*.mdc` | `AGENTS.md` (nativo) |

**No se copia a ciegas**: cada asistente recibe su formato, pero comparten los mismos roles, límites y compuertas.

Cursor también carga `.claude/agents/` y `.claude/skills/` por compatibilidad; si hay un nombre repetido, `.cursor/` gana. Por eso los dos espejos deben decir lo mismo.

---

## 2. Mapa de archivos

```text
AGENTS.md                          reglas compartidas por los dos asistentes
CLAUDE.md                          puerta de entrada de Claude Code
MEMORY.md                          estado entre sesiones
docs/constitution.md               principios innegociables
specs/                             specs SDD activas

.claude/
  agents/*.md                      6 roles (frontmatter tools/disallowedTools)
  commands/*.md                    11 comandos (/sdd-*, /feature, /review)
  skills/*/SKILL.md                5 skills (sdd + 4 de conocimiento)
  settings.json                    allow / ask / deny

.cursor/
  rules/*.mdc                      6 reglas (core, dominio, seguridad, UI, specs, docs)
  agents/*.md                      6 roles (frontmatter readonly)
  skills/*/SKILL.md                7 skills (3 flujos + 4 de conocimiento)

scripts/
  hooks/pre-commit                 bloquea publicar el arnés local
  hooks/commit-msg                 elimina atribución de IA del mensaje
  setup-hooks.sh                   instala los hooks en .git/hooks/
  check-attribution.sh             el mismo chequeo, para CI
```

---

## 3. Cómo se usa en una sesión

### Flujo completo

```text
1. Abrir el asistente en el proyecto.
2. /sdd <descripción de la feature>
3. El coordinator evalúa y, si aplica, delega en planner.
4. El planner escribe spec.md, plan.md y tasks.md.
5. El humano revisa y aprueba la spec (G1–G3).
6. /sdd-implement <spec> <tarea>
7. El implementer ejecuta una sola tarea con tests primero.
8. /sdd-validate <spec>
9. reviewer + domain-guardian + security-reviewer auditan.
10. Con la aprobación, el implementer hace commit y push de la rama feat/* o docs/*
    y abre el PR contra la base que indica el coordinator.
11. El humano mergea.
```

### Regla de git: commit + push de ramas

- **Puede (solo el implementer, tras aprobación del reviewer y, si aplica, de security-reviewer/domain-guardian):** crear la rama desde la base indicada, `git add` con rutas explícitas (nunca `git add -A` ni `git add .`), commit con mensaje convencional en español, `git push -u origin feat/*|docs/*` y `gh pr create --base <base>`.
- **Antes de cada push:** `git status --short` para confirmar que no se publican `.claude/`, `.cursor/`, `AGENTS.md`, `CLAUDE.md`, `MEMORY.md`, `.env` ni `datos/`.
- **Nunca:** push a `main` ni a `develop`; push forzado (`--force`, `-f`, `--force-with-lease`); `git merge` ni `gh pr merge`; `rebase`, `reset --hard`, `commit --amend`, `filter-branch`/`filter-repo` u otra reescritura de historial; borrar ramas remotas; `--no-verify`.
- **Autoría:** el commit sale con el `user.name`/`user.email` del humano, sin `Co-Authored-By` ni `Generated with` (principio 8, ADR-004). El merge sigue siendo del humano.

### Cambio pequeño

```text
/feature corregir el redondeo del total por categoría
```

Solo si toca ≤3 archivos y no cambia dominio, esquema, auth, roles ni precios.

### Revisión sin cambios

```text
/review          (Claude Code)
/review-change   (Cursor)
```

---

## 4. Permisos por rol

| Rol | Claude Code | Cursor |
|---|---|---|
| `coordinator` | tools: `Agent, Read, Grep, Glob, AskUserQuestion`; sin `Write`/`Edit`; es el agente por defecto | `readonly: true` |
| `planner` | `Read, Grep, Glob, Write, Edit`; sin `Bash` ni `Agent` | `readonly: false` |
| `implementer` | `Read, Grep, Glob, Bash, Write, Edit`; sin `Agent` | `readonly: false` |
| `reviewer` | `Read, Grep, Glob, Bash`; sin `Write`/`Edit` | `readonly: true` |
| `domain-guardian` | `Read, Grep, Glob, Bash`; sin `Write`/`Edit` | `readonly: true` |
| `security-reviewer` | `Read, Grep, Glob, Bash`; sin `Write`/`Edit` | `readonly: true` |

Nota: en Claude Code, la ausencia de `Write`/`Edit` en `reviewer`, `domain-guardian` y `security-reviewer` es una restricción parcial, porque conservan `Bash` para correr pruebas (ver §5). En Cursor, `readonly: true` sí cubre los comandos que cambian estado.

Además:

- **Claude Code:** `deny` > `ask` > `allow` en `.claude/settings.json`. `git commit -m`, `git switch`, `git fetch`, `git push [-u] origin feat/*|docs/*` y `gh pr create` están permitidos; cualquier otro `git push`, `git checkout`, `git reset --hard`, `git clean`, `rm`, `alembic` y las instalaciones de dependencias piden confirmación; el push a `main`/`develop`, el push forzado o de borrado, `git merge`, `gh pr merge`, `rebase`, `filter-branch`/`filter-repo`, `commit --amend` y `--no-verify` están denegados. `.env`, claves y `datos/` están denegados.
- **Cursor:** `readonly: true` restringe ediciones y comandos que cambian estado. No hay agente por defecto: `00-core.mdc` obliga a la sesión principal a actuar como `coordinator` y delegar.

---

## 5. Por qué el coordinator no edita

Si el que coordina puede editar, termina implementando y deja de planear. En el coordinator la restricción es técnica, no honoraria: no tiene `Bash`, `Write` ni `Edit`, así que no puede escribir por ningún camino.

Con el reviewer, el domain-guardian y el security-reviewer pasa algo parecido, pero la restricción en Claude Code es **parcial**: si pueden arreglar lo que revisan, revisan con sesgo. A los tres se les quita `Write`/`Edit`, pero se mantiene `Bash` porque necesitan correr pruebas, y por shell podrían escribir en teoría. La garantía final es el prompt, la regla de permisos `ask` de `.claude/settings.json` y la revisión humana. En Cursor, `readonly: true` sí cubre también los comandos que cambian estado.

---

## 6. Skills y cuándo se cargan

| Skill | Se carga cuando | Paths |
|---|---|---|
| `sdd` | Se va a escribir o ejecutar una spec | — |
| `asset-domain` | Se toca conteo, precios, ubicaciones o totales | `backend/**/*.py`, `web/src/**`, `backend/migrations/**` |
| `tenant-security` | Se toca SQL, auth, roles, subidas, exportación o logs | `backend/**/*.py`, `backend/migrations/**` |
| `web-ui` | Se crean o modifican pantallas (Tailwind, shadcn/ui) | `web/**` |
| `browser-qa` | Se verifica UI en navegador a 375 px | `web/**` |

Las skills no se cargan todas: se cargan cuando hacen falta. Eso mantiene el contexto pequeño.

---

## 7. Comandos por asistente

| Flujo | Claude Code | Cursor |
|---|---|---|
| Flujo completo | `/sdd` (skill) | `/sdd` (skill) |
| Constitución, spec, clarificar, plan, tareas, implementar, validar, cambio, estado | `/sdd-constitution`, `/sdd-spec`, `/sdd-clarify`, `/sdd-plan`, `/sdd-tasks`, `/sdd-implement`, `/sdd-validate`, `/sdd-change`, `/sdd-status` | Pasos dentro de `/sdd` |
| Cambio pequeño | `/feature` | `/feature` (skill) |
| Revisión | `/review` | `/review-change` (skill) |

Claude Code fusiona los comandos personalizados con las skills: un archivo en `.claude/commands/` y una skill en `.claude/skills/` crean el mismo `/nombre`. Cursor está migrando los comandos a skills, por eso solo tiene tres flujos invocables; la revisión se llama `/review-change` porque Cursor ya trae un `/review` integrado.

---

## 8. Formato de cada pieza

### Claude Code

- Agentes: `name`, `description`, `tools`, `disallowedTools`, `color`. `tools` es una allowlist.
- Skills y comandos: `description`, `argument-hint`, `paths`, `context: fork`, `agent`, `background`.
- `CLAUDE.md` importa `@AGENTS.md`, `@docs/constitution.md` y `@MEMORY.md`; no duplica su contenido.

### Cursor

- Reglas: `.mdc` con `description`, `globs` y `alwaysApply`. Un `.md` suelto en `.cursor/rules` se ignora.
- Agentes: `name`, `description`, `model: inherit`, `readonly`.
- Skills: `name` debe coincidir con la carpeta; `description`, `paths` y `disable-model-invocation`.

---

## 9. Sincronización de los dos arneses

- El **cuerpo** del agente o de la skill es el mismo en los dos. Solo cambia el frontmatter.
- Si cambias un rol, un límite o una regla, actualiza `.claude/` y `.cursor/` en el mismo cambio.
- No agregues una regla en un asistente que contradiga a otro. Si hay conflicto, manda `AGENTS.md`.
- El planner no edita `docs/adr/` sin decisión humana (ya está en su prompt, igual en los dos arneses).
- Valida antes de terminar:
  - `.claude/settings.json` debe parsear como JSON.
  - El frontmatter YAML de agentes, skills y comandos debe parsear.
  - Las reglas de Cursor deben usar `.mdc` y tener `description` o `globs`.

---

## 10. MCP

| Asistente | Dónde se configura | Estado |
|---|---|---|
| Claude Code | `.mcp.json` o `claude mcp add` | Previsto, ninguno activo |
| Cursor | `.cursor/mcp.json` | Previsto, ninguno activo |

Servidores previstos, todos opcionales:

| MCP | Para qué | Cuándo activarlo |
|---|---|---|
| Chrome DevTools | Verificar UI real, consola, red, móvil 375 px y cámara | Desde la fase 2 |
| Context7 | Documentación actualizada de Flask, React, Tailwind y shadcn/ui | Cuando haya dudas de API |

**Regla:** ningún MCP se agrega "porque suena bien". Se agrega cuando una tarea concreta lo necesita. Los secretos van en variables de entorno, nunca en el repo.

---

## 11. Qué NO hace este arnés

- No reemplaza la revisión humana.
- No garantiza código correcto por sí solo.
- No decide prioridades.
- No autoriza merges.
- No inventa reglas de negocio.

---

## 12. Mantenimiento

| Frecuencia | Acción |
|---|---|
| Cada sesión | Actualizar `MEMORY.md` |
| Cada feature | Actualizar la spec si cambió una decisión |
| Mensual | Revisar prompts y skills contra la realidad del código |
| Trimestral | Revisar `AGENTS.md`, la constitución y este documento |

---

## 13. Archivos locales y autoría

### 13.1 El arnés no se publica

Estos archivos viven solo en la máquina del desarrollador:

```text
.claude/
.cursor/
AGENTS.md
CLAUDE.md
MEMORY.md
```

Tres capas los protegen:

| Capa | Qué hace |
|---|---|
| `.gitignore` | Los excluye de `git status` y de `git add` normal |
| `.git/hooks/pre-commit` | Bloquea el commit si alguno quedó staged, incluso con `git add -f` |
| CI (`ci-repo.yml`) | Falla si el diff de un PR publica alguno |

Comprobar:

```sh
git check-ignore -v .claude/settings.json .cursor/rules/00-core.mdc AGENTS.md
```

### 13.2 Ningún asistente como autor ni coautor

El autor es el humano. Ningún commit, PR o release lleva `Co-authored-by` de Claude, Cursor o Copilot, ni trailers de sesión, ni pies tipo `Generated with ...`.

| Asistente | Control |
|---|---|
| Claude Code | `.claude/settings.json` → `attribution` vacío para commit y PR |
| Cursor (IDE) | Settings → Git & PRs → Attribution: commit y PR apagados |
| Cursor (CLI) | `~/.cursor/cli-config.json` → `attribution.attributeCommitsToAgent` y `attributePRsToAgent` en `false` |
| Todos | `.git/hooks/commit-msg` elimina las líneas de atribución antes de crear el commit |

El hook es la garantía final: algunas herramientas inyectan el trailer a nivel de herramienta, así que una regla en el prompt no basta. `git commit --no-verify` lo salta; por eso la regla también vive en los prompts, en el CI y en la revisión humana.

### 13.3 Los hooks se versionan aparte y se instalan con un comando

`.git/hooks/` no se versiona, pero la copia fuente sí: vive en `scripts/hooks/` y se instala con:

```sh
sh scripts/setup-hooks.sh
```

Se corre una vez por clon. `scripts/check-attribution.sh` hace la misma verificación en CI sobre el rango del PR. Ver ADR-004.

### 13.4 Límite de esta protección

Esto protege el repositorio local y lo que se publique desde esta máquina. Un agente en la nube no ve los archivos locales ni los hooks: si se usa, hay que revisar el mensaje antes de mergear.
