# Constitución — AssetControl

Principios innegociables. Toda spec, plan y tarea debe cumplirlos.

1. **Simplicidad primero**: monolito modular Flask + una web React; sin microservicios, colas ni sincronización offline en el MVP (ADR-002). Toda pieza nueva se justifica por una necesidad concreta.
2. **La spec manda**: nada se implementa si no está en el alcance vigente (`docs/01-alcance-mvp.md`) o en la spec activa (`specs/`). Si falta una decisión, se para y se pregunta.
3. **El servidor es la autoridad**: totales de informe, cierre de sesión, permisos y `seq` se calculan y validan en el servidor. El cliente propone; nunca impone.
4. **Multi-tenant y roles en servidor**: toda tabla de negocio lleva `tenant_id`; el filtro vive en un único punto de la capa de datos; cada endpoint declara y verifica su rol (`admin` | `contador`) y trae su prueba de aislamiento.
5. **Registros inmutables e informes congelados**: las verificaciones solo se insertan, con UUID del cliente (idempotentes); una sesión cerrada no se modifica; los totales se guardan al cerrar con `precio_al_contar` (ADR-003).
6. **Dinero exacto y datos sagrados**: `NUMERIC`/`Decimal`, nunca `float`; nada se borra (baja lógica con evento); los datos reales de la clínica no se versionan ni se loguean.
7. **Cero digitación innecesaria**: el problema que se resuelve es escribir todo en Excel; cada pantalla de captura prefiere escanear, elegir, autocompletar o duplicar antes que teclear. Tests verdes antes de avanzar.
8. **Autoría humana y arnés local**: ningún asistente (Claude, Cursor, Copilot u otro) figura como autor ni coautor en commits, PRs o releases. Los arneses y su configuración (`.claude/`, `.cursor/`, `AGENTS.md`, `CLAUDE.md`, `MEMORY.md`) viven solo en la máquina del desarrollador y no se suben al repositorio (ADR-004).
