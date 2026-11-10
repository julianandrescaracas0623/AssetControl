# Inventario de Activos

Sistema para llevar el inventario de activos (equipos y mobiliario) de una clínica odontológica, con conteos periódicos, historial y valor total para informes.

Primer cliente: Biotecnologia Dental (Cartago, Colombia). El diseño es multi-tenant desde el inicio.

## Estado

Fase: definición de arquitectura y alcance del MVP. Todavía no hay código de aplicación.

## Documentos

| Documento | Contenido |
|---|---|
| [docs/01-alcance-mvp.md](docs/01-alcance-mvp.md) | Qué entra y qué no entra en el MVP |
| [docs/02-arquitectura.md](docs/02-arquitectura.md) | Componentes, flujo de datos y funcionamiento sin internet |
| [docs/03-modelo-datos.md](docs/03-modelo-datos.md) | Entidades, relaciones e historial |
| [docs/04-metodologia.md](docs/04-metodologia.md) | Cómo trabajamos: ramas, ADR, definición de terminado |
| [docs/05-preguntas-abiertas.md](docs/05-preguntas-abiertas.md) | Decisiones pendientes con la clínica |
| [docs/adr/](docs/adr/) | Decisiones de arquitectura registradas |

## Stack propuesto

- **Backend:** Python con Flask, PostgreSQL, SQLAlchemy y Alembic para migraciones.
- **App móvil:** React Native (Expo), SQLite local para funcionar sin internet, cámara para escanear códigos.
- **Pruebas:** pytest en el backend; Jest y pruebas de flujo en la app.

La justificación está en [ADR-001](docs/adr/ADR-001-stack.md).
