# Método aplicado a AssetControl

> **Origen:** el mismo método que usa el proyecto CuadreClaro (arnés + Spec-Driven Development + multiagente), adaptado a este dominio.
> **Propósito:** dejar explícito qué se toma del método, qué se adapta y qué se descarta, para que la orquestación no dependa de la memoria de nadie.

---

## 1. Las tres ideas del método

| Idea | Significado |
|---|---|
| Arnés | El agente no es el producto; el **arnés** (contexto, reglas, memoria, permisos) es lo que lo hace confiable |
| SDD | **Spec-Driven Development**: la intención se convierte en spec, plan y tareas verificables antes de escribir código |
| Multiagente | Separar coordinación, planeación, implementación y revisión produce mejor código que un solo agente que hace todo |

---

## 2. Artefactos del método en este proyecto

```text
AGENTS.md                     reglas permanentes (local)
CLAUDE.md                     entrada de Claude Code, importa AGENTS.md (local)
MEMORY.md                     estado entre sesiones (local)
docs/constitution.md          principios innegociables
specs/NNN-nombre/
  spec.md                     qué y por qué (EARS)
  plan.md                     cómo (arquitectura y decisiones)
  tasks.md                    tareas pequeñas y verificables
.claude/agents|commands|skills|settings.json     arnés de Claude Code (local)
.cursor/rules|agents|skills                      arnés de Cursor (local)
scripts/hooks, scripts/*.sh   hooks de Git y chequeo de autoría (versionados)
```

---

## 3. Cómo se traduce a este proyecto

| Regla del método | Aplicación en AssetControl |
|---|---|
| Pruebas automáticas | `uv run pytest` (backend) y `vitest` / Playwright (web) |
| Specs por slice vertical | Fundación, catálogo y alta, conteo, informe, piloto, importación opcional |
| Revisión de código | Revisión general + dominio (informes y verificaciones) + seguridad (tenant y roles), separadas |
| Demo visual | Verificación en navegador real a 375 px (skill `browser-qa`) |
| Agentes genéricos | Agentes con conocimiento del dominio de activos y conteos |

---

## 4. Las cinco reglas que se hacen obligatorias

1. **Contexto antes que código.** Ningún agente implementa sin leer `AGENTS.md`, `docs/constitution.md`, `MEMORY.md` y la spec activa.
2. **Una tarea, un cambio, un PR.** El implementer no toma dos tareas a la vez.
3. **Tests primero y verdes.** Sin tests no hay avance; el reviewer no aprueba "funciona en mi máquina".
4. **El que planea no implementa y el que implementa no se aprueba.** Roles separados por permisos, no por buena voluntad.
5. **Memoria al cerrar.** Si no se actualiza `MEMORY.md`, la sesión no terminó.

---

## 5. Qué se adapta

- **Idioma:** documentos, UI y mensajes en español; nombres técnicos en inglés; entidades de dominio con el nombre del modelo de datos.
- **Asistentes:** solo Claude Code y Cursor.
- **Agentes:** seis, sin `ai-evaluator` (este producto no tiene canal de IA).
- **Compuertas:** además de las generales, **S1 seguridad y tenant**, **S2 datos y migraciones** y **S3 totales y dinero**, que este dominio exige.
- **Definición de terminado:** incluye aislamiento por tenant, idempotencia y que los totales coincidan con la suma real, no solo tests.

---

## 6. Qué no se copia

- **Micro-tareas artificiales** solo para llenar un `tasks.md`.
- **Multiagentes por moda.** Se usan cuando aportan separación real de permisos y contexto.
- **Prompts gigantes.** El conocimiento estable va en skills; el prompt del agente define rol, límites y salida.
- **Automatización sin humano.** Ningún agente mergea a `main` ni cambia migraciones, auth o precios sin aprobación.

---

## 7. Lectura recomendada por rol

| Rol | Debe leer |
|---|---|
| Dueño de producto | Este documento, `01-estado-del-proyecto.md`, `05-decisiones/` |
| Coordinator | `AGENTS.md`, `docs/constitution.md`, `03-orquestacion/01-modelo-operativo.md` |
| Planner | `docs/constitution.md`, la spec activa, `04-plantillas/plantillas.md` |
| Implementer | `AGENTS.md`, la spec activa, `docs/03-modelo-datos.md` |
| Reviewer | `docs/constitution.md`, `03-orquestacion/03-flujos-y-compuertas.md`, la spec activa |
