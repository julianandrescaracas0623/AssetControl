# Migraciones (Alembic)

- Se ejecutan con el **rol migrador** (dueño del esquema) leído de `MIGRATION_DATABASE_URL`. Nunca con `DATABASE_URL` (rol de la aplicación): `env.py` falla si falta la variable o si usa el mismo rol.
- El chequeo de "mismo rol" solo se hace si `DATABASE_URL` está definida (si alguna de las dos URL no se puede interpretar, falla); en un job de migración dedicado sin `DATABASE_URL` se omite.
- Comandos, desde `backend/`: `uv run alembic upgrade head`, `uv run alembic downgrade base` (en local: `uv run --env-file ../.env alembic ...`).
- `0001_baseline` está vacía: no crea tablas de negocio.

## Patrón obligatorio de toda tabla de negocio (spec 002 en adelante)

En el **mismo `upgrade`** que crea la tabla (lleva `tenant_id uuid NOT NULL`):

```sql
ALTER TABLE <tabla> ENABLE ROW LEVEL SECURITY;
ALTER TABLE <tabla> FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON <tabla>
  USING      (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
GRANT SELECT, INSERT, UPDATE ON <tabla> TO <rol_app>;  -- sin DELETE: nada se borra
```

- `NULLIF(..., '')` es obligatorio: sin tenant la política no devuelve filas ni deja escribir, en vez de fallar con `''::uuid`.
- `GRANT` mínimos: tablas de solo inserción (p. ej. `verificacion`) reciben solo `SELECT, INSERT`. Nunca `DELETE`.
- El nombre del rol de la aplicación no se escribe a mano en la migración: se lee del entorno (`APP_DB_USER`) o se decide en la spec 002.

El **`downgrade`** lo revierte en orden inverso:

```sql
REVOKE ALL ON <tabla> FROM <rol_app>;
DROP POLICY tenant_isolation ON <tabla>;
ALTER TABLE <tabla> NO FORCE ROW LEVEL SECURITY;
ALTER TABLE <tabla> DISABLE ROW LEVEL SECURITY;
DROP TABLE <tabla>;
```

Ver `specs/001-fundacion-tecnica/plan.md` §2 y §6, y la deuda para la spec 002 en §4 (FK compuestas con `tenant_id`, `UNIQUE` con `tenant_id`, vistas con `security_invoker`).
