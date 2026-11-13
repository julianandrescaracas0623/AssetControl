# Spec 001 — Fundación técnica

> **Estado:** aprobada (2026-11-11).
> **Nota:** OpenAPI y los tipos TypeScript generados entran en la spec 002, no en esta. Las pruebas corren contra PostgreSQL local en Docker; producción apunta a Supabase (solo como PostgreSQL administrado; ver ADR-001).
> **Depende de:** `docs/constitution.md`, `docs/01-alcance-mvp.md`, `docs/02-arquitectura.md`, ADR-001 a 004.
> **Objetivo:** dejar un entorno reproducible donde escribir la primera línea de dominio no requiera discutir infraestructura.

---

## 1. Problema

Hoy el proyecto tiene documentación y decisiones, pero **no tiene código ni entorno ejecutable**. Sin una fundación común:

- Cada prueba futura depende de la máquina de quien la corre.
- No hay dónde poner la primera migración ni cómo verificar el aislamiento entre tenants.
- Los agentes no tienen un comando único de verificación.
- La web no tiene base para Tailwind ni shadcn/ui.

Esta spec construye solo el andamiaje. **No implementa autenticación, catálogo, conteo ni informes.**

---

## 2. Usuarios

| Usuario | Necesidad |
|---|---|
| Desarrollador | Levantar el proyecto con un comando y correr pruebas con otro |
| Agente implementer | Saber exactamente qué comando ejecutar y qué debe pasar |
| Agente reviewer | Verificar que la estructura respeta la arquitectura decidida |
| Futuro colaborador | Entender el repo en menos de 30 minutos |

---

## 3. Alcance

### Incluye

- Estructura del monorepo (`backend/`, `web/`).
- Backend Flask con *application factory*, configuración por entorno y blueprint `meta`.
- SQLAlchemy 2 + Alembic con PostgreSQL.
- Punto central de acceso a datos que exige un tenant (base del filtro central).
- Endpoint `/health` y manejo uniforme de errores.
- Arnés de pruebas con `pytest` contra PostgreSQL real, con rollback por prueba.
- Revisión inicial de Alembic, reversible.
- `docker-compose.yml` con la API y PostgreSQL.
- `.env.example` sin secretos.
- `web/` con React + Vite + TypeScript estricto, Tailwind CSS, shadcn/ui inicializado y una pantalla que muestra el estado de `/health`.
- ESLint, `typecheck` y Vitest en la web.
- CI en `.github/workflows` (ya escrito): lint, tipos, pruebas y build.
- Hooks de Git instalables con `sh scripts/setup-hooks.sh`.

### No incluye

- Registro, login ni roles funcionales.
- Tablas de negocio (activos, ubicaciones, sesiones, verificaciones).
- Escáner, conteo, informes o importación.
- Almacenamiento de fotos.
- Despliegue real.
- Offline o sincronización (ADR-002).

---

## 4. Requisitos (EARS)

### R1 — Estructura

**El sistema** debe organizarse en un monorepo con `backend/` y `web/`.

### R2 — Application factory

**El sistema** debe exponer `create_app(config)` en `backend/app/__init__.py`, de modo que cada prueba cree una instancia aislada.

### R3 — Configuración

**Cuando** falte una variable de entorno obligatoria, **el sistema** debe fallar al arrancar con un mensaje que nombre la variable, sin imprimir su valor.

Variables obligatorias: `DATABASE_URL`, `SECRET_KEY`, `ENVIRONMENT`.

### R4 — Acceso a datos con tenant

**El sistema** debe ofrecer un único punto de acceso a datos que reciba el `tenant_id` y lo aplique a toda consulta sobre una tabla de negocio, y que falle si se invoca sin tenant.

### R5 — Salud

**Cuando** se consulte `GET /health`, **el sistema** debe responder `200` con el estado de la aplicación y de la base de datos, y `503` si la base no responde, sin exponer secretos ni detalles internos.

### R6 — Errores

**Cuando** ocurra un error no controlado, **el sistema** debe responder un JSON uniforme con código estable, mensaje en español e identificador de correlación, sin traza en producción.

### R7 — Pruebas

**El sistema** debe permitir ejecutar `pytest` contra un PostgreSQL de pruebas y revertir los cambios de cada prueba al terminar.

### R8 — Migraciones

**El sistema** debe versionar el esquema con Alembic y permitir `upgrade` y `downgrade` sin error sobre una base vacía.

### R9 — Entorno local

**Cuando** se ejecute `docker compose up`, **el sistema** debe levantar la API con recarga en caliente y PostgreSQL.

### R10 — Web base

**El sistema** debe compilar `web/` con React + Vite + TypeScript estricto, con Tailwind CSS y shadcn/ui inicializados, y mostrar el estado de `/health`.

### R11 — Calidad

**Cuando** se ejecute el CI, **el sistema** debe correr `ruff`, `pytest`, `npm run lint`, `npm run typecheck` y `npm test`, y fallar si alguno falla.

### R12 — Secretos y datos

**El sistema** no debe contener secretos ni datos de la clínica en el repositorio; `.env` y `datos/` deben estar ignorados y `.env.example` debe listar las variables sin valores reales.

### R13 — Arnés reproducible

**El sistema** debe instalar sus hooks de Git desde archivos versionados con `sh scripts/setup-hooks.sh`.

**Cuando** se abra un PR, **el CI** debe fallar si un commit del rango contiene atribución de un asistente o si el diff publica un archivo local del arnés.

---

## 5. Criterios de aceptación

| # | Criterio | Verificación |
|---|---|---|
| A1 | El repo tiene `backend/` y `web/` y cada una compila | `ls` + build |
| A2 | `create_app` se importa sin efectos secundarios | `uv run pytest tests/test_app_factory.py` |
| A3 | Falta de variable obligatoria falla con mensaje claro | prueba unitaria |
| A4 | El acceso a datos sin tenant falla; con tenant filtra | prueba con dos tenants |
| A5 | `/health` responde 200 con DB arriba y 503 con DB abajo | prueba de integración |
| A6 | Un error no controlado devuelve JSON uniforme sin traza | prueba unitaria |
| A7 | `pytest` corre en limpio y no deja datos | ejecución local, dos veces |
| A8 | `alembic upgrade head` y `downgrade base` funcionan | ejecución local |
| A9 | `docker compose up` levanta la API | ejecución local + `curl /health` |
| A10 | La web compila y muestra el estado de `/health` | `npm run build` + capturas a 375 px y 1440 px |
| A11 | `npm run lint`, `typecheck` y `npm test` pasan | ejecución local |
| A12 | El CI falla si una compuerta falla | PR de prueba |
| A13 | No hay secretos ni datos de la clínica en el repo | `git grep` + `git ls-files` |
| A14 | Un clon nuevo instala los hooks con un comando | `sh scripts/setup-hooks.sh` + commit de prueba |
| A15 | El CI rechaza atribución de IA y archivos locales del arnés | PR de prueba |

---

## 6. Reglas de dominio aplicables

Esta spec no implementa dominio, pero deja listas las bases:

- `tenant_id` será obligatorio en toda tabla de negocio.
- El filtro por tenant es único y central (R4); ningún endpoint filtra a mano.
- Dinero siempre con `Decimal` (la web no calculará totales).

---

## 7. Riesgos

| Riesgo | Mitigación |
|---|---|
| Sobrecargar la fundación con dominio | Prohibido crear tablas de negocio en esta spec |
| Entorno local no reproducible | Docker + `.env.example` + CI desde el primer día |
| Aislamiento por tenant "para después" | El punto central y su prueba con dos tenants se crean ahora |
| Pruebas con SQLite que no reflejan Postgres | `pytest` siempre contra PostgreSQL |
| Dependencias de shadcn/ui que cambian | Fijar versiones; añadir componentes con la CLI solo cuando se usan |
| Arnés local publicado por descuido | Hooks versionados, `pre-commit` y chequeo en CI |

---

## 8. Preguntas abiertas

- [ ] `[PENDIENTE]` ¿Nombre definitivo del repositorio? — dueño — antes de T10.
- [ ] `[PENDIENTE]` ¿Rama `main` protegida con PR obligatorio? — dueño — antes de T10.
- [x] Gestor de dependencias de Python: **uv** con `pyproject.toml` (decidido 2026-11-11).

---

## 9. Fuera de alcance explícito

- Cualquier tabla de negocio.
- Autenticación real.
- Escáner y conteo.
- Despliegue a producción.
- Offline.

Si una tarea de esta spec empieza a tocar esos temas, se detiene y se convierte en otra spec.
