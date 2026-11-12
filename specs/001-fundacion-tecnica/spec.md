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
- Punto central de acceso a datos que exige un tenant (base del filtro central), con aislamiento obligatorio por Row Level Security de PostgreSQL y un rol de base de datos de la aplicación distinto del rol que migra (ver R4).
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

`DATABASE_URL` usa el rol de la aplicación (R4c). La URL del rol migrador la lee solo Alembic y no es obligatoria para arrancar la API (nombre propuesto en `plan.md` §2).

### R4 — Acceso a datos con tenant

**El sistema** debe ofrecer un único punto de acceso a datos que reciba el `tenant_id` y lo aplique a toda consulta sobre una tabla de negocio, y que falle si se invoca sin tenant.

**R4a — Aislamiento en la base (obligatorio).** **Cuando** se abra el punto de acceso con un tenant, **el sistema** debe fijar ese tenant en la transacción de PostgreSQL (`SET LOCAL` vía `set_config`, parametrizado), y toda tabla de negocio debe tener Row Level Security habilitada y forzada (`ENABLE` + `FORCE ROW LEVEL SECURITY`) con una política que compare su `tenant_id` con el tenant fijado, tanto al leer (`USING`) como al escribir (`WITH CHECK`).

**R4b — Sin tenant, nada.** **Cuando** una conexión de la aplicación consulte o escriba una tabla de negocio sin tenant fijado, **la base** no debe devolver filas ni aceptar escrituras.

**R4c — Rol de la aplicación.** **El sistema** debe conectarse a PostgreSQL con un rol propio de la aplicación que no sea superusuario, no tenga `BYPASSRLS` y no sea dueño de las tablas de negocio (o, si lo fuera, con `FORCE ROW LEVEL SECURITY`); las migraciones deben correr con otro rol, dueño del esquema. Aplica en Docker local, en CI y en Supabase.

**R4d — Filtro en Python como complemento.** **El sistema** debe aplicar además el filtro estándar de SQLAlchemy (`with_loader_criteria` sobre las entidades con tenant) y asignar el `tenant_id` al insertar; este filtro no sustituye a RLS.

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
| A4 | El acceso a datos sin tenant falla; con tenant filtra; RLS bloquea a otro tenant incluso por vías que el filtro de Python no cubre (`get_bind`, engine, SQL crudo con el rol de app, API *bulk* heredada, `join` explícito) | prueba con dos tenants (`test_tenant_scope.py`) |
| A4a | El rol de la aplicación no es superusuario, no tiene `BYPASSRLS` y la tabla de prueba tiene RLS forzada | prueba que consulta `pg_roles` y `pg_class` |
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
- La base de datos hace cumplir el tenant con RLS (R4a–R4c); toda tabla de negocio futura nace con RLS forzada y su política.
- Dinero siempre con `Decimal` (la web no calculará totales).

---

## 7. Riesgos

| Riesgo | Mitigación |
|---|---|
| Sobrecargar la fundación con dominio | Prohibido crear tablas de negocio en esta spec |
| Entorno local no reproducible | Docker + `.env.example` + CI desde el primer día |
| Aislamiento por tenant "para después" | El punto central y su prueba con dos tenants se crean ahora |
| Barrera de aislamiento solo en Python con fugas (SQLAlchemy ofrece demasiadas vías) | RLS de PostgreSQL como barrera; Python solo como filtro estándar (R4a–R4d) |
| Rol de la aplicación con `BYPASSRLS` o superusuario anula RLS en silencio | Prueba A4a que lo verifica en cada corrida |
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

La tabla con `tenant_id` y su política que usa T3 se crea solo dentro de las pruebas; no es una tabla de negocio ni entra en las migraciones.

---

## 10. Registro de cambios

- 2026-11-11: aislamiento por RLS + filtro simple (decisión humana tras 3 revisiones de T3). R4 se amplía con R4a–R4d; A4 se amplía y se añade A4a; se descarta la barrera en Python que recorría el árbol de cada sentencia (ver `plan.md` §7). ADR-001 actualizado: RLS pasa de opcional a obligatoria.
- 2026-11-11: T3 aprobada (RLS). Nota: en la reescritura el código se escribió antes que las pruebas; el rojo se obtuvo restaurando el código anterior.
