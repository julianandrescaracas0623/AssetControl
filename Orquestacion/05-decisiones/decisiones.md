# Decisiones

> **Estado:** resumen de las decisiones de arquitectura de [`docs/adr/`](../../docs/adr/). El texto vinculante está en los ADR; este archivo es el registro de por qué se decidió.
> Todas están en estado `Propuesta` hasta que el dueño las acepte. Si una cambia, se escribe un ADR nuevo que la reemplaza; no se edita el anterior.

---

## D-001 — Stack → [ADR-001](../../docs/adr/ADR-001-stack.md)

- **Decisión:** Flask + SQLAlchemy + Alembic, PostgreSQL y una web React con Tailwind CSS y shadcn/ui. Fotos en almacenamiento compatible con S3.
- **Consecuencia:** un solo cliente que mantener; HTTPS obligatorio por la cámara; sin tiendas de aplicaciones.

## D-002 — Solo online → [ADR-002](../../docs/adr/ADR-002-solo-online-cliente-web.md)

- **Decisión:** el MVP no tiene base local, cola de eventos ni sincronización. El conteo se hace desde el navegador con UUID del cliente y reintento manual.
- **Consecuencia:** se pierde contar sin red; se reabre con un ADR de PWA si el piloto lo exige.

## D-003 — Verificación con copia de precio → [ADR-003](../../docs/adr/ADR-003-verificacion-con-snapshot.md)

- **Decisión:** cada verificación guarda `precio_al_contar` y `categoria_al_contar`; los totales de la sesión se congelan al cerrar.
- **Consecuencia:** un informe cerrado siempre da el mismo número; hay duplicación deliberada de dos campos.

## D-004 — Arnés local y autoría humana → [ADR-004](../../docs/adr/ADR-004-arnes-local-y-autoria-humana.md)

- **Decisión:** el autor es siempre el humano; el arnés (`.claude/`, `.cursor/`, `AGENTS.md`, `CLAUDE.md`, `MEMORY.md`) es local y los hooks y el CI lo hacen cumplir.
- **Consecuencia:** un clon nuevo no trae el arnés; se instalan los hooks con `sh scripts/setup-hooks.sh`.

---

## Pendientes de decisión

Las preguntas abiertas y su recomendación por defecto están en [`docs/05-preguntas-abiertas.md`](../../docs/05-preguntas-abiertas.md): P1 unidad vs lote, P2 qué suma el informe, P10 importar o partir de cero, T9 nombre del repositorio y T10 hosting.
