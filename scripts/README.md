# Scripts del repositorio

Utilidades versionadas que no dependen de la máquina de cada quien.

## `setup-hooks.sh`

Instala los hooks de Git desde `scripts/hooks/` en `.git/hooks/`.

```sh
sh scripts/setup-hooks.sh
```

Se corre una vez por clon. No borra hooks ajenos: sobrescribe solo `pre-commit` y `commit-msg`.

## `check-attribution.sh`

Falla si un commit del rango trae atribución de un asistente (Claude, Cursor, OpenCode, Copilot, Codex).

```sh
sh scripts/check-attribution.sh origin/main..HEAD
```

Sin argumento revisa el último commit. El CI lo corre sobre el rango del PR.

## `hooks/`

- `pre-commit`: bloquea publicar los archivos locales del arnés (`.claude/`, `.cursor/`, `.opencode/`, `AGENTS.md`, `CLAUDE.md`, `MEMORY.md`, `opencode.jsonc`).
- `commit-msg`: elimina la atribución de IA del mensaje antes de crear el commit.

Los hooks locales de `.git/hooks/` no viajan con el repositorio. Estas copias sí.
