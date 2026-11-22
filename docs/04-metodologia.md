# 04. Metodología de trabajo

## Estructura del repositorio

```
/
├── backend/            API Flask (se crea al empezar la implementación)
│   ├── app/
│   │   ├── api/        blueprints y esquemas de entrada/salida
│   │   ├── domain/     reglas de negocio (sin Flask ni SQLAlchemy)
│   │   ├── models/     modelos SQLAlchemy
│   │   └── services/   casos de uso: conteo, cierre, informe (e importación si se hace)
│   ├── migrations/     Alembic
│   └── tests/
├── web/                App React: Vite, Tailwind, shadcn/ui (se crea al empezar)
│   └── src/{pages,features,components,api,lib}
├── docs/               arquitectura, modelo, ADR
├── specs/              specs SDD por entrega (spec, plan, tasks)
├── Orquestacion/       método de trabajo con personas y agentes de IA
├── scripts/            hooks de Git y chequeo de autoría
├── .github/            CI (GitHub Actions) y plantilla de PR
└── (local, no se publica) .claude/ .cursor/ AGENTS.md CLAUDE.md MEMORY.md
```

Monorepo: un cambio que toca API y web (por ejemplo, un campo nuevo en una verificación) va en un solo PR.

## Ramas y revisión

- `main` siempre desplegable. Protegida: solo se entra por PR.
- Ramas cortas desde `main`: `feat/…`, `fix/…`, `docs/…`, `chore/…`. Sin Git Flow.
- Un PR = un cambio con un propósito. Preferir PR de menos de ~400 líneas.
- Merge por *squash*. El título del PR sigue el formato `tipo(área): resultado` (ej. `feat(sessions): cerrar sesión con totales congelados`).
- El autor de commits y PRs es siempre el humano; sin `Co-Authored-By` de asistentes ([ADR-004](adr/ADR-004-arnes-local-y-autoria-humana.md)).
- Todo PR pasa CI antes de fusionarse. Si hay otra persona en el equipo, requiere una aprobación.

## Decisiones de arquitectura (ADR)

- Se escribe un ADR cuando la decisión es difícil de revertir o afecta a más de un componente.
- Archivo `docs/adr/ADR-NNN-titulo.md`, con estado `Propuesta`, `Aceptada` o `Reemplazada`.
- Un ADR aceptado no se edita; si cambia, se escribe uno nuevo que lo reemplaza.
- Usar la plantilla en [docs/adr/README.md](adr/README.md).

## Definición de terminado

Un cambio está terminado cuando:

1. Cumple el criterio de aceptación escrito en el issue o PR.
2. Tiene pruebas que fallarían sin el cambio (regla de negocio ⇒ prueba de dominio).
3. CI en verde: lint, tipos y pruebas.
4. Las migraciones son reversibles y se probaron sobre una base con datos.
5. Si cambia el contrato de la API, se actualiza la documentación en el mismo PR.
6. Si toma una decisión de arquitectura, hay ADR.
7. No hay datos reales de la clínica ni secretos en el repositorio.

## Pruebas

- **Dominio:** pruebas unitarias puras (cierre de sesión, regla R3, totales). Son las más importantes: el producto vende un número correcto.
- **API:** pytest contra PostgreSQL real (contenedor), no SQLite. Incluye una prueba de aislamiento entre tenants por endpoint.
- **Idempotencia:** reenviar la misma verificación y verificar contra una sesión cerrada (`409`).
- **Web:** Vitest para lógica de cliente; Playwright para el flujo de conteo (escaneo simulado, confirmación, reintento tras un corte de red).
- **Importación (si se hace):** un extracto anonimizado del Excel es el caso de prueba. Debe reproducir la suma de las hojas de categoría, no la de la hoja TOTAL.

## MVP: criterios medibles

Los cuatro criterios de [01-alcance-mvp.md](01-alcance-mvp.md) son la definición de éxito. Cada uno tendrá una prueba automatizada o un guion de prueba manual firmado antes de entregar.

## Fases

| Fase | Resultado | Depende de |
|---|---|---|
| 0. Definición | Docs 01–06, ADR iniciales, CI en verde | — |
| 1. Esqueleto | Backend + migraciones del modelo, auth y roles, web con login | Fase 0 |
| 2. Catálogo | Ubicaciones, categorías, alta de activos con poca digitación | Fase 1 |
| 3. Conteo | Sesiones, escaneo, verificaciones, discrepancias | Fase 2 |
| 4. Informe y Dashboard | Cierre con totales y desglose por categoría y por ubicación congelados (R4, R9), PDF y Excel, Dashboard (Inicio) con evolución entre conteos | Fase 3 |
| 5. Piloto | Un conteo real en la clínica | Fases 3–4 |
| 6. Importación (opcional) | Excel → revisión → activos | Fase 2 |
