#!/usr/bin/env bash
# Crea el rol de la aplicación y la base de pruebas (spec 001, R4c; plan.md §2).
#
# Lo ejecuta la imagen oficial de PostgreSQL desde /docker-entrypoint-initdb.d/
# solo cuando el volumen de datos está vacío. Con un volumen existente se recrea
# el volumen o se ejecuta este mismo script a mano dentro del contenedor.
#
# - Rol de la aplicación (APP_DB_USER): LOGIN, NOSUPERUSER, NOBYPASSRLS,
#   NOCREATEDB, NOCREATEROLE. No es dueño de nada: solo recibe CONNECT y USAGE
#   sobre el esquema public; los GRANT por tabla los da cada migración.
# - Rol migrador: POSTGRES_USER, dueño de las bases y del esquema.
# - Rol auth_owner (spec 002, P0/A0; R4a): futuro dueño de las funciones
#   SECURITY DEFINER del esquema acceso (las crean las migraciones, no este
#   script). NOLOGIN, NOSUPERUSER, NOBYPASSRLS, NOCREATEDB, NOCREATEROLE,
#   NOREPLICATION, sin contraseña, sin CREATE en public ni en las bases, no dueño
#   de nada y sin membresías con ningún rol en ningún sentido (ni con el rol de la
#   aplicación ni con otros); el script revoca las que encuentre y falla si queda alguna.
# - El usuario y la contraseña llegan a psql por el entorno (\getenv, psql 17) y
#   se usan como :"app_user" y :'app_password': no van en la línea de comandos
#   (ps no los muestra), no se interpolan en el texto SQL ni se imprimen (sin set -x).
#
# Todo corre en un subshell: si la imagen lo carga con "source" (sin permiso de
# ejecución), las opciones de shell no alteran el entrypoint. Si el subshell
# falla, "|| exit 1" al final corta la inicialización tanto con "source" (sale
# el entrypoint) como con ejecución directa: el contenedor no queda sano.

(
  set -euo pipefail

  require_var() {
    if [ -z "${!1:-}" ]; then
      echo "01-app-role.sh: falta la variable de entorno $1" >&2
      exit 1
    fi
  }

  require_var APP_DB_USER
  require_var APP_DB_PASSWORD
  require_var POSTGRES_USER
  require_var POSTGRES_DB
  # psql las lee del entorno con \getenv: deben estar exportadas.
  export APP_DB_USER APP_DB_PASSWORD

  # El rol de la aplicación no puede ser el migrador: sería dueño y superusuario.
  if [ "$APP_DB_USER" = "$POSTGRES_USER" ]; then
    echo "01-app-role.sh: APP_DB_USER no puede ser el mismo rol que POSTGRES_USER" >&2
    exit 1
  fi

  readonly AUTH_OWNER="auth_owner"

  # auth_owner no puede ser el rol de la aplicación ni el migrador: perdería NOLOGIN.
  if [ "$APP_DB_USER" = "$AUTH_OWNER" ] || [ "$POSTGRES_USER" = "$AUTH_OWNER" ]; then
    echo "01-app-role.sh: APP_DB_USER y POSTGRES_USER no pueden llamarse ${AUTH_OWNER}" >&2
    exit 1
  fi

  readonly TEST_DB="assetcontrol_test"

  # "|| exit 1" explícito: bash ignora set -e dentro de un subshell que está a la
  # izquierda de "||" (como este), así que un psql fallido no cortaría el script.
  run_psql() {
    local database="$1"
    shift
    psql -X -q -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$database" "$@" || exit 1
  }

  # Rol de la aplicación y base de pruebas. Idempotente: se puede volver a ejecutar.
  run_psql "$POSTGRES_DB" -v test_db="$TEST_DB" -v auth_owner="$AUTH_OWNER" <<'EOSQL'
-- Si una sentencia falla, ni el servidor ni psql muestran su texto (llevaría la contraseña).
\set VERBOSITY terse
\getenv app_user APP_DB_USER
\getenv app_password APP_DB_PASSWORD
SET log_min_error_statement = panic;
SET log_statement = 'none';

SELECT NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user') AS create_role \gset
\if :create_role
CREATE ROLE :"app_user" LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE
  PASSWORD :'app_password';
\else
ALTER ROLE :"app_user" LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE
  PASSWORD :'app_password';
\endif

-- auth_owner (spec 002, P0). Idempotente: si ya existe se reafirman los atributos.
SELECT NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'auth_owner') AS create_auth_owner \gset
\if :create_auth_owner
CREATE ROLE :"auth_owner" NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE
  NOREPLICATION PASSWORD NULL;
\else
ALTER ROLE :"auth_owner" NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE
  NOREPLICATION PASSWORD NULL;
\endif

-- auth_owner sin membresías con ningún rol, en ningún sentido (R4a): ni con el rol
-- de la aplicación (no podría hacer SET ROLE auth_owner) ni con otros roles
-- (anon, authenticated o service_role si existen, roles predefinidos pg_*, etc.).
-- Cada concesión se revoca con su propio grantor (GRANTED BY, de
-- pg_auth_members.grantor): sin él, REVOKE solo quita la que hizo el rol actual y
-- deja las demás con un WARNING. CASCADE quita también las concesiones que dependen
-- de ella (dadas con ADMIN OPTION). El catálogo se relee en cada vuelta para no
-- revocar dos veces lo que ya cayó en cascada (sin avisos). Solo revoca lo que exista.
SET assetcontrol.auth_owner = :'auth_owner';
DO $$
DECLARE
  auth_owner_name text := current_setting('assetcontrol.auth_owner');
  membership record;
BEGIN
  FOR attempt IN 1..1000 LOOP
    SELECT granted.rolname AS granted_role, member.rolname AS member_role,
           grantor.rolname AS grantor_role
      INTO membership
      FROM pg_auth_members m
      JOIN pg_roles granted ON granted.oid = m.roleid
      JOIN pg_roles member ON member.oid = m.member
      JOIN pg_roles grantor ON grantor.oid = m.grantor
     WHERE auth_owner_name IN (granted.rolname, member.rolname)
     ORDER BY m.oid
     LIMIT 1;
    EXIT WHEN NOT FOUND;
    EXECUTE format('REVOKE %I FROM %I GRANTED BY %I CASCADE',
                   membership.granted_role, membership.member_role, membership.grantor_role);
  END LOOP;
END
$$;

SELECT format('CREATE DATABASE %I', :'test_db')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'test_db') \gexec
EOSQL

  for database in "$POSTGRES_DB" "$TEST_DB"; do
    run_psql "$database" -v db_name="$database" -v auth_owner="$AUTH_OWNER" <<'EOSQL'
\getenv app_user APP_DB_USER
GRANT CONNECT ON DATABASE :"db_name" TO :"app_user";
GRANT USAGE ON SCHEMA public TO :"app_user";
-- auth_owner no crea esquemas ni objetos en public (el CREATE transitorio en acceso
-- lo da y lo quita la migración 0004, plan.md §2.1).
REVOKE CREATE ON DATABASE :"db_name" FROM :"auth_owner";
REVOKE CREATE ON SCHEMA public FROM :"auth_owner";
EOSQL
  done

  # Aserción final: si auth_owner conserva alguna membresía (como rol concedido o
  # como miembro), RAISE EXCEPTION aborta psql (ON_ERROR_STOP) y el script falla.
  # Nota para C8 (Supabase): allí el migrador no es superusuario y, al crear el rol,
  # PostgreSQL 16+ le concede auth_owner con ADMIN OPTION (más SET/INHERIT según
  # createrole_self_grant); esa membresía del creador no la puede revocar él mismo,
  # así que esta aserción no aplica tal cual fuera de este contenedor.
  run_psql "$POSTGRES_DB" -v auth_owner="$AUTH_OWNER" <<'EOSQL'
\set VERBOSITY terse
SET assetcontrol.auth_owner = :'auth_owner';
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
      FROM pg_auth_members m
      JOIN pg_roles r ON r.oid IN (m.roleid, m.member)
     WHERE r.rolname = current_setting('assetcontrol.auth_owner')
  ) THEN
    RAISE EXCEPTION '01-app-role.sh: auth_owner conserva membresías de roles';
  END IF;
END
$$;
EOSQL

  echo "01-app-role.sh: roles de la aplicación y ${AUTH_OWNER}, y base ${TEST_DB} listos."
) || {
  echo "01-app-role.sh: la inicialización falló; el contenedor no debe arrancar." >&2
  exit 1
}
