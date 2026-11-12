# Inventario de Activos

Sistema para llevar el inventario de activos (equipos y mobiliario) de una clínica odontológica, con conteos periódicos, historial y valor total para informes.

Primer cliente: Biotecnologia Dental (Cartago, Colombia). El diseño es multi-tenant desde el inicio.

## Estado

Fase: definición de arquitectura y alcance del MVP. Fundación técnica en curso (spec 001).

## Estructura

- `backend/` — API Flask.
- `web/` — cliente React responsive.

## Documentos

| Documento | Contenido |
|---|---|
| [docs/00-contexto-handoff.md](docs/00-contexto-handoff.md) | Contexto original y decisiones iniciales |
| [docs/01-alcance-mvp.md](docs/01-alcance-mvp.md) | Qué entra y qué no entra en el MVP |
| [docs/02-arquitectura.md](docs/02-arquitectura.md) | Componentes, flujos y despliegue |
| [docs/03-modelo-datos.md](docs/03-modelo-datos.md) | Entidades, relaciones e historial |
| [docs/04-metodologia.md](docs/04-metodologia.md) | Estructura del repo, ramas, ADR, definición de terminado, fases |
| [docs/05-preguntas-abiertas.md](docs/05-preguntas-abiertas.md) | Decisiones pendientes |
| [docs/06-importacion-excel.md](docs/06-importacion-excel.md) | Análisis del Excel actual y plan de importación |
| [docs/adr/](docs/adr/) | Decisiones de arquitectura registradas |
| [Orquestacion/](Orquestacion/README.md) | Método de trabajo: roles, agentes, compuertas, plan y arneses de Claude Code y Cursor |
| [specs/](specs/001-fundacion-tecnica/spec.md) | Specs SDD de cada entrega (la primera: fundación técnica) |

## Stack

- **Web:** React + TypeScript + Vite, Tailwind CSS y shadcn/ui, TanStack Query. Un solo cliente web responsive: conteo móvil primero y administración en celular y computador.
- **Backend:** Python con Flask, PostgreSQL, SQLAlchemy y Alembic.
- **Fotos:** almacenamiento de objetos compatible con S3.
- **CI/CD:** GitHub Actions.
- **Pruebas:** pytest en el backend; Vitest y Playwright en la web.

La justificación está en [ADR-001](docs/adr/ADR-001-stack.md) y [ADR-002](docs/adr/ADR-002-solo-online-cliente-web.md).

## Entorno local con Docker

1. Copia `.env.example` a `.env` y completa los valores (`.env` está ignorado por git).
2. `docker compose up --build` levanta PostgreSQL 17 (`db`, solo en `127.0.0.1:5432`) y la API con recarga (`api`, en `http://localhost:5000`).
3. Comprueba la API con `curl http://localhost:5000/health` (`200`, `"db": "ok"`).

Dentro de los contenedores la API se conecta a la base por el host `db`, no `localhost`, y con el rol de la aplicación (`APP_DB_USER`), nunca con el superusuario.

- **`APP_DB_USER` debe ser distinto de `POSTGRES_USER`.** `POSTGRES_USER` es el rol migrador (dueño del esquema, ejecuta Alembic); `APP_DB_USER` es el rol de la aplicación, sin `SUPERUSER` ni `BYPASSRLS`, y el script de init falla si son el mismo.
- **El rol de la aplicación solo se crea con el volumen vacío.** El script `docker/postgres/init/01-app-role.sh` corre únicamente la primera vez que se inicializa el volumen `pgdata`. Si el volumen ya existía sin ese rol (o cambiaste `APP_DB_USER`), el servicio `db` no queda sano y la API no arranca. Recrea el volumen con `docker compose down -v` (borra los datos locales de la base) y vuelve a levantar; o ejecuta el mismo script a mano dentro del contenedor `db`.
- Si una contraseña lleva caracteres especiales (`@ : / ? # %`), codifícala en las URL de `.env`.

## Trabajo con asistentes de IA

El método está en [Orquestacion/](Orquestacion/README.md). La configuración de Claude Code y Cursor (`.claude/`, `.cursor/`, `AGENTS.md`, `CLAUDE.md`, `MEMORY.md`) es **local** y no se publica ([ADR-004](docs/adr/ADR-004-arnes-local-y-autoria-humana.md)). Tras clonar, instala los hooks de Git:

```sh
sh scripts/setup-hooks.sh
```
