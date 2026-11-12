"""Configuración compartida de pytest.

Ninguna salida de pytest debe mostrar la contraseña de la base. Los frames de
SQLAlchemy y psycopg reciben la contraseña como argumento (``cparams``,
``conninfo``), así que un fallo de conexión dentro de una prueba la mostraría en
el traceback, en ``--showlocals`` o en la salida capturada. Estos hooks la
reemplazan por ``***`` en cada reporte antes de que se imprima.

Las pruebas con PostgreSQL usan dos URL (spec 001, R4c):

- ``TEST_DATABASE_URL``: rol de la aplicación (sin ``SUPERUSER`` ni
  ``BYPASSRLS``, no dueño). Es con la que se conecta la app en las pruebas.
- ``TEST_MIGRATION_DATABASE_URL``: rol migrador, dueño del esquema. Solo crea y
  elimina tablas de prueba, sus políticas y sus ``GRANT``.

Arnés de pruebas (spec 001, R7 / A7, T5)
----------------------------------------

Decisión (2026-11-11, deuda de T3): conviven dos estrategias y cada prueba usa
la que no cambia lo que prueba.

1. **Transacción con rollback por prueba** (la regla por defecto, plan.md §2):
   fixtures ``app``, ``client`` y ``db_connection``. La app se conecta con el rol
   de la aplicación; su fábrica de sesiones se ata a una conexión con una
   transacción externa abierta (``join_transaction_mode="create_savepoint"``):
   cada ``tenant_session`` corre en un *savepoint* y su ``commit`` solo libera el
   *savepoint*. Al terminar la prueba se revierte la transacción externa: nada
   llega a confirmarse. Es lo que usarán las pruebas de endpoints de la spec 002+.

2. **Crear y borrar tablas por prueba, con ``commit`` real** (``pg_app`` de
   ``test_tenant_scope.py``, T3): se mantiene. Esas pruebas verifican justamente
   los límites reales de la transacción (``SET LOCAL`` que desaparece al
   confirmar o revertir, conexión del pool reutilizada, conexión nueva sin
   tenant, escritura visible desde otra conexión). Dentro de una transacción
   externa esos límites no existen y las pruebas pasarían por la razón
   equivocada. Su limpieza es el ``drop_all`` del migrador en el ``finally``.

Riesgo de ``SET LOCAL`` con *savepoints* (plan.md §4): ``set_config(..., true)``
dura hasta el fin de la transacción **externa**; ``RELEASE SAVEPOINT`` no lo
borra (``ROLLBACK TO SAVEPOINT`` sí). Sin mitigación, tras un ``tenant_session(A)``
la conexión de la prueba seguiría con el tenant A y una aserción de "sin tenant
no hay filas" pasaría o fallaría en falso. Mitigación: al terminar cada
transacción raíz de una sesión de la fixture ``app`` se vacía el tenant
(``set_config('app.tenant_id', '', true)``) en la conexión de la prueba
(``_clear_tenant_after_session``). Lo prueba ``test_harness.py``. Las pruebas que
necesiten el comportamiento real del pool o de ``commit`` usan la estrategia 2.

Sin residuos entre corridas: ``database_residue_guard`` (sesión) toma una foto
del esquema ``public`` (tablas, políticas y filas por tabla, como migrador)
antes de la primera prueba con base y falla al final de la corrida si quedó una
tabla ``prueba_*`` creada en ella o si cambió algo fuera de esas tablas. Así ``pytest`` se puede
correr dos veces seguidas con el mismo resultado.

Limitación conocida del guardián (deuda, resolver antes de la spec 002): las
tablas de negocio llevan ``FORCE ROW LEVEL SECURITY``, que también aplica al
migrador (dueño). Sin ``app.tenant_id`` la política no deja ver ninguna fila, así
que el conteo de filas por tabla da 0 y el guardián **no detecta filas
residuales en tablas de negocio**; hoy solo detecta tablas, políticas y filas en
tablas sin RLS. Opciones a decidir: contar por tenant, contar con un rol con
``BYPASSRLS`` solo para pruebas o leer ``pg_stat_user_tables``.

Uso local: ``uv run --env-file ../.env pytest`` desde ``backend``.
"""

import os
from collections.abc import Iterator
from urllib.parse import unquote, urlsplit

import pytest
from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import MetaData, create_engine, event, text
from sqlalchemy.engine import URL, Connection, make_url
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.pool import NullPool

from app import create_app
from app.config import Config
from app.db import _EXTENSION_KEY

_URL_VARS = (
    "TEST_DATABASE_URL",
    "TEST_MIGRATION_DATABASE_URL",
    "DATABASE_URL",
    "MIGRATION_DATABASE_URL",
)
_MASK = "***"

BLOCKED = (
    "bloqueado: faltan TEST_DATABASE_URL (rol de la aplicación) y "
    "TEST_MIGRATION_DATABASE_URL (rol migrador), o la base assetcontrol_test no responde"
)
SAME_ROLE = (
    "bloqueado: TEST_MIGRATION_DATABASE_URL usa el mismo rol que TEST_DATABASE_URL; "
    "debe usar el rol migrador (POSTGRES_USER), no el de la aplicación"
)


def _database_passwords() -> list[str]:
    """Contraseñas de las URL de base del entorno, tal cual y decodificadas."""
    found: set[str] = set()
    for name in _URL_VARS:
        raw = os.environ.get(name, "").strip()
        if not raw:
            continue
        try:
            password = urlsplit(raw).password
        except ValueError:
            continue
        if password:
            found.update({password, unquote(password)})
    # Primero las más largas: una contraseña no queda a medias tapada por otra.
    return sorted(found, key=len, reverse=True)


def _scrub(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        text = text.replace(secret, _MASK)
    return text


def _redact_report(report: pytest.CollectReport | pytest.TestReport) -> None:
    secrets = _database_passwords()
    if not secrets:
        return
    longrepr = report.longrepr
    if isinstance(longrepr, tuple):
        path, lineno, message = longrepr
        report.longrepr = (path, lineno, _scrub(message, secrets))
    elif longrepr is not None:
        text = str(longrepr)
        if any(secret in text for secret in secrets):
            report.longrepr = _scrub(text, secrets)
    report.sections = [(title, _scrub(body, secrets)) for title, body in report.sections]


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    _redact_report(report)
    return report


@pytest.hookimpl(wrapper=True)
def pytest_make_collect_report(collector):
    report = yield
    _redact_report(report)
    return report


def read_database_url(name: str) -> URL | None:
    """La variable ``name`` como ``URL``: su ``str`` y ``repr`` ocultan la contraseña.

    Así ningún frame de pytest (argumentos o variables locales) la muestra en texto plano.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    return make_url(raw)


@pytest.fixture
def app_database_url(database_residue_guard) -> URL:
    """URL del rol de la aplicación sobre la base de pruebas."""
    url = read_database_url("TEST_DATABASE_URL")
    if url is None:
        pytest.fail(BLOCKED, pytrace=False)
    return url


@pytest.fixture
def migration_database_url(database_residue_guard) -> URL:
    """URL del rol migrador sobre la base de pruebas."""
    url = read_database_url("TEST_MIGRATION_DATABASE_URL")
    if url is None:
        pytest.fail(BLOCKED, pytrace=False)
    app_url = read_database_url("TEST_DATABASE_URL")
    if app_url is not None and app_url.username == url.username:
        # Con el mismo rol no hay quién cree las tablas ni nada que probar sobre RLS.
        pytest.fail(SAME_ROLE, pytrace=False)
    return url


# --- Arnés de pruebas (T5) -------------------------------------------------

_CLEAR_TENANT = text("select set_config('app.tenant_id', '', true)")
POLICY_EXPR = "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid"
RESIDUE_PREFIX = "prueba_"
# Sin base alcanzable el guardián no debe demorar la corrida.
_GUARD_CONNECT_TIMEOUT = 3

_SNAPSHOT_TABLES = text(
    "select c.relname, c.relkind from pg_class c "
    "join pg_namespace n on n.oid = c.relnamespace "
    "where n.nspname = 'public' and c.relkind in ('r', 'p', 'v', 'm', 'S', 'f') "
    "order by c.relname"
)
_SNAPSHOT_POLICIES = text(
    "select tablename, policyname from pg_policies where schemaname = 'public' "
    "order by tablename, policyname"
)


_GUARD_URL_KEY = pytest.StashKey[URL | None]()
_APP_KEY = "assetcontrol.tests.app"


def pytest_configure(config):
    # La URL del migrador se lee al arrancar: una prueba que use ``monkeypatch.setenv``
    # sobre ella no cambia la base que revisa el guardián.
    config.stash[_GUARD_URL_KEY] = read_database_url("TEST_MIGRATION_DATABASE_URL")


def create_rls_tables(conn: Connection, metadata: MetaData, app_role: str) -> None:
    """Crea las tablas de ``metadata`` con la plantilla de toda tabla de negocio.

    ``ENABLE`` + ``FORCE ROW LEVEL SECURITY``, política ``tenant_isolation`` y
    ``GRANT SELECT, INSERT, UPDATE`` al rol de la aplicación (plan.md §2). Se
    ejecuta con una conexión del rol migrador; solo para tablas de prueba.
    """
    metadata.drop_all(conn)
    metadata.create_all(conn)
    preparer = conn.dialect.identifier_preparer
    role = preparer.quote(app_role)
    for table in metadata.sorted_tables:
        name = preparer.format_table(table)
        for sql in (
            f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY",
            f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY",
            f"CREATE POLICY tenant_isolation ON {name} "
            f"USING ({POLICY_EXPR}) WITH CHECK ({POLICY_EXPR})",
            f"GRANT SELECT, INSERT, UPDATE ON {name} TO {role}",
        ):
            conn.execute(text(sql))


def _schema_snapshot(url: URL) -> dict[str, object] | None:
    """Tablas, políticas y filas por tabla de ``public``; ``None`` si no hay base."""
    engine = create_engine(
        url, poolclass=NullPool, connect_args={"connect_timeout": _GUARD_CONNECT_TIMEOUT}
    )
    try:
        with engine.connect() as conn:
            tables = [tuple(row) for row in conn.execute(_SNAPSHOT_TABLES)]
            policies = [tuple(row) for row in conn.execute(_SNAPSHOT_POLICIES)]
            preparer = conn.dialect.identifier_preparer
            rows = {
                name: conn.scalar(text(f"select count(*) from {preparer.quote(name)}"))  # noqa: S608
                for name, kind in tables
                if kind in ("r", "p")
            }
    except SQLAlchemyError:
        # Sin base no hay qué revisar; las pruebas con base ya fallan como "bloqueado".
        return None
    finally:
        engine.dispose()
    return {"tables": tables, "policies": policies, "rows": rows}


def _without_test_tables(snapshot: dict[str, object]) -> dict[str, object]:
    def keep(name: str) -> bool:
        return not name.startswith(RESIDUE_PREFIX)

    return {
        "tables": [t for t in snapshot["tables"] if keep(t[0])],
        "policies": [p for p in snapshot["policies"] if keep(p[0])],
        "rows": {k: v for k, v in snapshot["rows"].items() if keep(k)},
    }


def residue_problems(before: dict[str, object], after: dict[str, object]) -> list[str]:
    """Diferencias que cuentan como residuo de una corrida de pruebas."""
    # Solo cuenta lo que dejó esta corrida: una tabla ``prueba_*`` que ya existía al
    # empezar es de otro proceso en curso (p. ej. el pytest que lanza una sonda).
    existing = {name for name, _ in before["tables"]}
    problems = [
        f"tabla de prueba sin borrar: {name}"
        for name, _ in after["tables"]
        if name.startswith(RESIDUE_PREFIX) and name not in existing
    ]
    clean_before, clean_after = _without_test_tables(before), _without_test_tables(after)
    for key in ("tables", "policies", "rows"):
        if clean_before[key] != clean_after[key]:
            problems.append(f"cambió {key}: antes {clean_before[key]}, después {clean_after[key]}")
    return problems


@pytest.fixture(scope="session")
def database_residue_guard(request) -> Iterator[None]:
    """Falla al final de la corrida si las pruebas dejaron algo en la base."""
    url = request.config.stash.get(_GUARD_URL_KEY, None)
    before = _schema_snapshot(url) if url is not None else None
    yield
    if before is None:
        return
    after = _schema_snapshot(url)
    if after is None:
        return
    problems = residue_problems(before, after)
    if problems:
        pytest.fail("residuos de pruebas en la base: " + "; ".join(problems), pytrace=False)


def _clear_tenant_after_session(connection: Connection):
    """Mitigación del riesgo de ``SET LOCAL`` con *savepoints* (ver docstring del módulo)."""

    def clear(session, transaction) -> None:
        if transaction.parent is not None:
            return
        if connection.closed or connection.invalidated or not connection.in_transaction():
            return
        connection.execute(_CLEAR_TENANT)

    return clear


@pytest.fixture
def db_connection(app_database_url) -> Iterator[Connection]:
    """Conexión del rol de la aplicación con una transacción externa que se revierte."""
    app = create_app(
        Config(database_url=app_database_url, secret_key="clave-de-prueba", environment="test")
    )
    database = app.extensions[_EXTENSION_KEY]
    failure = None
    try:
        connection = database.engine.connect()
    except OperationalError as exc:
        # Solo el nombre del error: el traceback de psycopg trae la contraseña en sus frames.
        failure = f"{BLOCKED} (rol de la aplicación: {type(exc.orig).__name__})"
    if failure is not None:
        database.engine.dispose()
        pytest.fail(failure, pytrace=False)

    outer = connection.begin()
    database.session_factory.configure(bind=connection, join_transaction_mode="create_savepoint")
    clear = _clear_tenant_after_session(connection)
    event.listen(database.session_factory, "after_transaction_end", clear)
    connection.info[_APP_KEY] = app
    try:
        yield connection
    finally:
        event.remove(database.session_factory, "after_transaction_end", clear)
        if outer.is_active:
            outer.rollback()
        connection.close()
        database.engine.dispose()


@pytest.fixture
def app(db_connection) -> Iterator[Flask]:
    """App con el rol de la aplicación; todo lo que escribe se revierte al terminar."""
    flask_app = db_connection.info[_APP_KEY]
    with flask_app.app_context():
        yield flask_app


@pytest.fixture
def client(app) -> FlaskClient:
    """Cliente HTTP de la app de ``app``."""
    return app.test_client()
