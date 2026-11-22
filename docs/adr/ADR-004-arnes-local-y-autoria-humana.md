# ADR-004: Arnés local y autoría humana

- **Estado:** Propuesta
- **Fecha:** 2026-11-09

## Contexto

El proyecto se desarrolla con asistentes de IA (Claude Code, Cursor). Su configuración (`.claude/`, `.cursor/`, `AGENTS.md`, `CLAUDE.md`, `MEMORY.md`) contiene instrucciones y estado de trabajo que no forman parte del producto. Además, las herramientas pueden añadir por su cuenta trailers de coautoría (`Co-Authored-By`) en commits y PRs.

## Decisión

- El autor de todo commit, PR y release es el humano. Ningún asistente figura como autor ni coautor.
- El arnés es **local**: `.gitignore` lo excluye y el hook `pre-commit` bloquea su publicación aunque se use `git add -f`.
- La documentación del método (`Orquestacion/`), las specs y la constitución **sí** se versionan.
- Los hooks viven versionados en `scripts/hooks/` y se instalan con `sh scripts/setup-hooks.sh`.
- El CI falla si un commit del PR trae atribución de un asistente o si el diff publica un archivo local del arnés (`scripts/check-attribution.sh`).

## Alternativas consideradas

- **Versionar el arnés:** facilita compartirlo con otra persona, pero publica instrucciones internas y el estado de las sesiones. Si se necesita compartirlo, se hace por un canal privado.
- **Solo regla en el prompt:** no basta; algunas herramientas inyectan el trailer después del prompt. El hook se ejecuta tras esa inyección y antes de que exista el commit.

## Consecuencias

- Un clon nuevo no trae el arnés: se recibe por un canal privado y se instalan los hooks.
- `git commit --no-verify` salta los hooks; por eso el CI repite la verificación.
- Un agente en la nube no ve los archivos locales ni los hooks: si se usa, se revisa el mensaje antes de mergear.
