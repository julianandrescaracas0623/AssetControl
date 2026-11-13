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

  readonly TEST_DB="assetcontrol_test"

  run_psql() {
    local database="$1"
    shift
    psql -X -q -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$database" "$@"
  }

  # Rol de la aplicación y base de pruebas. Idempotente: se puede volver a ejecutar.
  run_psql "$POSTGRES_DB" -v test_db="$TEST_DB" <<'EOSQL'
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

SELECT format('CREATE DATABASE %I', :'test_db')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'test_db') \gexec
EOSQL

  for database in "$POSTGRES_DB" "$TEST_DB"; do
    run_psql "$database" -v db_name="$database" <<'EOSQL'
\getenv app_user APP_DB_USER
GRANT CONNECT ON DATABASE :"db_name" TO :"app_user";
GRANT USAGE ON SCHEMA public TO :"app_user";
EOSQL
  done

  echo "01-app-role.sh: rol de la aplicación y base ${TEST_DB} listos."
) || {
  echo "01-app-role.sh: la inicialización falló; el contenedor no debe arrancar." >&2
  exit 1
}
