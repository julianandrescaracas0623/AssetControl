"""Pruebas de las funciones ``acceso.*`` (spec 002, T3; plan.md §2.1, §7.2 #8–#10, §7.3).

Comportamiento real sobre una base temporal migrada a ``head`` con dos tenants
sintéticos (A y B):

- **A19 (§7.3):** ``buscar_login`` solo devuelve la cuenta del email exacto;
  vacío, nulo, comodines o sin normalizar -> nada; ``validar_invitacion`` solo
  dice vigente o no; ``aceptar_invitacion`` con clave inexistente, usada,
  vencida o mal formada no crea nada y con el email ya existente revierte
  (invitación sin usar); ``crear_tenant`` crea tenant e invitación ``admin`` en
  una transacción, revierte entera si falla y solo la ejecuta el migrador;
  las funciones corren como ``auth_owner`` real bajo ``FORCE RLS`` (sin su
  política devuelven cero).
- **GUC propias (revisión de seguridad de T3):** cada función fija sus GUC con
  valores que ella calcula y vacía las demás; una GUC ``app.auth_*`` fijada de
  antemano por quien llama (con datos de otro tenant) no cambia el resultado.
- **Prueba 9 (§7.2):** tras cada función no queda contexto: las ``app.auth_*``
  quedan vacías al volver, no sobreviven a la transacción ni a un savepoint y
  una consulta directa sin tenant devuelve cero.
- **Prueba 10 (§7.2):** ``ON CONFLICT DO NOTHING`` bajo ``auth_owner`` real no
  exige política ``SELECT`` en ``usuario``; ``now()`` es el de la transacción:
  una invitación consumida con ``COMMIT`` en otra transacción no satisface
  ``usada_en = now()`` (dentro de la misma transacción sí, también tras un
  savepoint: por eso esa no sirve como prueba de "consumida antes").
- **Criterio 4:** una sesión de la aplicación que usa la clave de B no ve de B
  más que la salida definida de la función.

Los ``COMMIT`` reales quedan en la base temporal, que se borra al terminar.
Datos sintéticos: nunca datos de la clínica.
"""

import hashlib
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from conftest import BLOCKED, read_database_url, role_sees_all_rows
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.pool import NullPool

BACKEND_DIR = Path(__file__).resolve().parent.parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
AUTH_OWNER = "auth_owner"

INSUFFICIENT_PRIVILEGE = "42501"
RAISE_EXCEPTION = "P0001"
INVALID_PARAMETER = "22023"
RLS_VIOLATION = "row-level security"
INVITACION_INVALIDA = "invitacion_invalida"

TABLES = ("tenant", "usuario", "membresia", "invitacion", "refresh_token")

TENANT_A = uuid.UUID("00000000-0000-4000-8000-00000000a003")
TENANT_B = uuid.UUID("00000000-0000-4000-8000-00000000b003")
USER_A = uuid.UUID("00000000-0000-4000-8000-0000000a0031")
USER_B = uuid.UUID("00000000-0000-4000-8000-0000000b0031")
USER_SIN_MEMBRESIA = uuid.UUID("00000000-0000-4000-8000-0000000c0031")
EMAIL_A = "admin.a3@ejemplo.test"
EMAIL_B = "admin.b3@ejemplo.test"
EMAIL_SIN_MEMBRESIA = "inactiva.a3@ejemplo.test"
NOMBRE_A = "Clínica sintética A3"
NOMBRE_B = "Clínica sintética B3"
HASH_A = "hash-sintetico-a-no-valido"

OWNER_GUCS = (
    "app.auth_email",
    "app.auth_usuario",
    "app.auth_inv_validar",
    "app.auth_inv_aceptar",
    "app.auth_usuario_nuevo",
    "app.auth_tenant_nuevo",
)

BUSCAR = "select * from acceso.buscar_login(:e)"
VALIDAR = "select acceso.validar_invitacion(:c)"
ACEPTAR = "select * from acceso.aceptar_invitacion(:c, :n, :p)"
CREAR = "select acceso.crear_tenant(:n, :e, :c)"


def clave(token: str) -> str:
    """Lo que envía la aplicación: ``sha256(token)`` en hex minúsculo (I1)."""
    return hashlib.sha256(token.encode()).hexdigest()


def stored_hash(clave_hex: str) -> bytes:
    """Lo que guarda la base: ``sha256(clave)`` en bytes (doble hash, I1)."""
    return hashlib.sha256(bytes.fromhex(clave_hex)).digest()


def nueva_clave() -> str:
    return clave(uuid.uuid4().hex)


def nuevo_email(prefix: str = "inv") -> str:
    return f"{prefix}.{uuid.uuid4().hex[:10]}@ejemplo.test"


@dataclass(frozen=True)
class AccesoDb:
    app_role: str
    migrator_role: str
    migrator: Engine
    app: Engine


def _fail(message: str) -> None:
    pytest.fail(message, pytrace=False)


def _alembic_config() -> AlembicConfig:
    config = AlembicConfig(str(ALEMBIC_INI))
    config.attributes["configure_logger"] = False
    return config


def _seed(conn: Connection) -> None:
    for tenant, nombre in ((TENANT_A, NOMBRE_A), (TENANT_B, NOMBRE_B)):
        conn.execute(
            text("insert into tenant (id, nombre) values (:id, :n)"), {"id": tenant, "n": nombre}
        )
    for user, email, password_hash in (
        (USER_A, EMAIL_A, HASH_A),
        (USER_B, EMAIL_B, "hash-sintetico-b-no-valido"),
        (USER_SIN_MEMBRESIA, EMAIL_SIN_MEMBRESIA, "hash-sintetico-c-no-valido"),
    ):
        conn.execute(
            text(
                "insert into usuario (id, email, nombre, password_hash) "
                "values (:id, :e, 'Persona sintética', :h)"
            ),
            {"id": user, "e": email, "h": password_hash},
        )
    for tenant, user, activa in (
        (TENANT_A, USER_A, True),
        (TENANT_B, USER_B, True),
        (TENANT_A, USER_SIN_MEMBRESIA, False),
    ):
        conn.execute(
            text(
                "insert into membresia (tenant_id, usuario_id, rol, activa) "
                "values (:t, :u, 'admin', :a)"
            ),
            {"t": tenant, "u": user, "a": activa},
        )


@pytest.fixture(scope="module")
def acceso(database_residue_guard) -> Iterator[AccesoDb]:
    """Base temporal en ``head`` con datos sintéticos; se borra al terminar."""
    migrator_url = read_database_url("TEST_MIGRATION_DATABASE_URL")
    app_url = read_database_url("TEST_DATABASE_URL")
    if migrator_url is None or app_url is None or not app_url.username:
        _fail(BLOCKED)
    name = f"assetcontrol_funciones_{uuid.uuid4().hex[:12]}"

    admin = create_engine(migrator_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    failure = None
    try:
        with admin.connect() as conn:
            if not role_sees_all_rows(conn):
                failure = (
                    "bloqueado: el rol migrador debe ser superusuario o BYPASSRLS para "
                    "sembrar los datos sintéticos bajo FORCE RLS"
                )
            else:
                conn.execute(text(f'CREATE DATABASE "{name}"'))
    except SQLAlchemyError as exc:
        failure = f"bloqueado: el rol migrador no pudo preparar la base ({type(exc).__name__})"

    engines: list[Engine] = []
    try:
        if failure is not None:
            _fail(failure)
        migrator_db = migrator_url.set(database=name)
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("MIGRATION_DATABASE_URL", migrator_db.render_as_string(hide_password=False))
            mp.delenv("DATABASE_URL", raising=False)
            mp.setenv("APP_DB_USER", app_url.username)
            command.upgrade(_alembic_config(), "head")

        migrator = create_engine(migrator_db, poolclass=NullPool)
        app = create_engine(app_url.set(database=name), poolclass=NullPool)
        engines += [migrator, app]
        with migrator.begin() as conn:
            _seed(conn)
        yield AccesoDb(
            app_role=app_url.username,
            migrator_role=migrator_url.username,
            migrator=migrator,
            app=app,
        )
    finally:
        for engine in engines:
            engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


# --- Utilidades -----------------------------------------------------------------


def invite(
    db: AccesoDb,
    tenant: uuid.UUID = TENANT_A,
    email: str | None = None,
    *,
    rol: str = "contador",
    expira: str = "now() + interval '3 days'",
    usada: str = "NULL",
    creada_por: uuid.UUID | None = None,
) -> tuple[str, str]:
    """Invitación confirmada (``COMMIT``) por el migrador; devuelve ``(clave, email)``."""
    key, email = nueva_clave(), email or nuevo_email()
    creador = creada_por or (USER_A if tenant == TENANT_A else USER_B)
    with db.migrator.begin() as conn:
        conn.execute(
            text(
                "insert into invitacion (tenant_id, email, rol, token_hash, creada_por, "  # noqa: S608
                f"expira_en, usada_en) values (:t, :e, :r, :h, :c, {expira}, {usada})"
            ),
            {"t": tenant, "e": email, "r": rol, "h": stored_hash(key), "c": creador},
        )
    return key, email


def set_gucs(conn: Connection, gucs: dict[str, str]) -> None:
    for name, value in gucs.items():
        conn.execute(text("select set_config(:n, :v, true)"), {"n": name, "v": value})


def gucs(conn: Connection) -> dict[str, str | None]:
    return {
        name: conn.scalar(text("select current_setting(:n, true)"), {"n": name})
        for name in OWNER_GUCS
    }


def assert_no_owner_context(conn: Connection) -> None:
    """Ninguna ``app.auth_*`` con valor (nula o vacía)."""
    assert {name: value for name, value in gucs(conn).items() if value} == {}


@contextmanager
def app_tx(db: AccesoDb, tenant: object | None = None) -> Iterator[Connection]:
    """Transacción del rol de la aplicación, con ``app.tenant_id`` opcional; se revierte."""
    with db.app.connect() as conn:
        tx = conn.begin()
        try:
            if tenant is not None:
                set_gucs(conn, {"app.tenant_id": str(tenant)})
            yield conn
        finally:
            tx.rollback()


@contextmanager
def migrator_tx(db: AccesoDb) -> Iterator[Connection]:
    """Transacción del migrador (superusuario en local y CI); se revierte."""
    with db.migrator.connect() as conn:
        tx = conn.begin()
        try:
            yield conn
        finally:
            tx.rollback()


def app_call(db: AccesoDb, sql: str, params: dict[str, object]):
    """Llama como la aplicación en su propia transacción confirmada; devuelve las filas."""
    with db.app.begin() as conn:
        return conn.execute(text(sql), params).all()


def assert_fails(conn: Connection, sql: str, params=None, *, code: str, fragment: str) -> str:
    """Falla con ``code`` y ``fragment``; revierte solo su savepoint; devuelve el mensaje."""
    nested = conn.begin_nested()
    with pytest.raises(DBAPIError) as excinfo:
        conn.execute(text(sql), params or {})
    nested.rollback()
    message = str(excinfo.value.orig)
    assert getattr(excinfo.value.orig, "sqlstate", None) == code, message
    assert fragment in message, message
    return message


def assert_denied(conn: Connection, sql: str, params=None) -> None:
    assert_fails(conn, sql, params, code=INSUFFICIENT_PRIVILEGE, fragment="permission denied")


def counts(db: AccesoDb) -> dict[str, int]:
    """Filas por tabla, contadas por el migrador (superusuario: ve todos los tenants)."""
    with db.migrator.connect() as conn:
        return {table: conn.scalar(text(f"select count(*) from {table}")) for table in TABLES}  # noqa: S608


def invitacion_usada_en(db: AccesoDb, key: str):
    with db.migrator.connect() as conn:
        return conn.execute(
            text("select usada_en from invitacion where token_hash = :h"), {"h": stored_hash(key)}
        ).scalar_one()


def foreign_gucs(**overrides: str) -> dict[str, str]:
    """GUC ``app.auth_*`` fijadas de antemano con datos del tenant B (criterio 1)."""
    values = {
        "app.auth_email": EMAIL_B,
        "app.auth_usuario": str(USER_B),
        "app.auth_inv_validar": nueva_clave(),
        "app.auth_inv_aceptar": nueva_clave(),
        "app.auth_usuario_nuevo": str(USER_B),
        "app.auth_tenant_nuevo": str(TENANT_B),
    }
    values.update(overrides)
    return values


# --- A19 (a, b): buscar_login ----------------------------------------------------


def test_buscar_login_returns_exactly_the_account_of_the_exact_email(acceso):
    rows = app_call(acceso, BUSCAR, {"e": EMAIL_A})
    assert [tuple(row) for row in rows] == [(USER_A, HASH_A, True, TENANT_A, "admin")]
    assert list(rows[0]._mapping) == ["usuario_id", "password_hash", "activo", "tenant_id", "rol"]


@pytest.mark.parametrize(
    "email",
    [
        None,
        "",
        " ",
        "%",
        "_",
        "%@ejemplo.test",
        "admin.a3@ejemplo.tes_",
        EMAIL_A.upper(),
        f" {EMAIL_A}",
    ],
)
def test_buscar_login_returns_nothing_for_empty_null_wildcard_or_other_email(acceso, email):
    assert app_call(acceso, BUSCAR, {"e": email}) == []


def test_buscar_login_does_not_return_inactive_memberships(acceso):
    rows = app_call(acceso, BUSCAR, {"e": EMAIL_SIN_MEMBRESIA})
    assert [tuple(row)[:3] for row in rows] == [
        (USER_SIN_MEMBRESIA, "hash-sintetico-c-no-valido", True)
    ]
    assert [tuple(row)[3:] for row in rows] == [(None, None)]


def test_buscar_login_ignores_owner_gucs_set_beforehand(acceso):
    with app_tx(acceso) as conn:
        set_gucs(conn, foreign_gucs())
        rows = conn.execute(text(BUSCAR), {"e": EMAIL_A}).all()
        assert [tuple(row) for row in rows] == [(USER_A, HASH_A, True, TENANT_A, "admin")]
        assert_no_owner_context(conn)


def test_buscar_login_does_not_depend_on_the_app_tenant(acceso):
    with app_tx(acceso, TENANT_B) as conn:
        rows = conn.execute(text(BUSCAR), {"e": EMAIL_A}).all()
    assert [tuple(row) for row in rows] == [(USER_A, HASH_A, True, TENANT_A, "admin")]


# --- A19 (c): validar_invitacion -------------------------------------------------


def test_validar_invitacion_returns_only_a_boolean(acceso):
    key, _ = invite(acceso)
    with app_tx(acceso) as conn:
        assert (
            conn.scalar(text("select pg_typeof(acceso.validar_invitacion(:c))::text"), {"c": key})
            == "boolean"
        )


def test_validar_invitacion_says_only_whether_it_is_valid(acceso):
    vigente_a, _ = invite(acceso, TENANT_A)
    vigente_b, _ = invite(acceso, TENANT_B)
    usada, _ = invite(acceso, usada="now() - interval '1 hour'")
    vencida, _ = invite(acceso, expira="now() - interval '1 minute'")
    cases = {
        vigente_a: True,
        vigente_b: True,  # desde la aplicación sin tenant: solo "vigente", nada más de B
        usada: False,
        vencida: False,
        nueva_clave(): False,
        vigente_a.upper(): False,
        vigente_a[:-1]: False,
        vigente_a + "0": False,
        "": False,
        "%": False,
        stored_hash(vigente_a).hex(): False,  # el hash guardado no sirve como clave (I1)
    }
    for key, expected in cases.items():
        assert app_call(acceso, VALIDAR, {"c": key}) == [(expected,)], key
    assert app_call(acceso, VALIDAR, {"c": None}) == [(None,)]
    # Validar no consume.
    assert invitacion_usada_en(acceso, vigente_a) is None


def test_validar_invitacion_ignores_owner_gucs_set_beforehand(acceso):
    vigente, _ = invite(acceso, TENANT_A)
    otra_b, _ = invite(acceso, TENANT_B)
    with app_tx(acceso) as conn:
        set_gucs(conn, foreign_gucs(**{"app.auth_inv_validar": otra_b}))
        assert conn.scalar(text(VALIDAR), {"c": vigente}) is True
        assert_no_owner_context(conn)
        set_gucs(conn, foreign_gucs(**{"app.auth_inv_validar": otra_b}))
        assert conn.scalar(text(VALIDAR), {"c": nueva_clave()}) is False


# --- A19 (d): aceptar_invitacion -------------------------------------------------


def test_aceptar_invitacion_creates_usuario_and_membresia_from_the_invitation(acceso):
    key, email = invite(acceso, TENANT_A, rol="contador")
    rows = app_call(acceso, ACEPTAR, {"c": key, "n": "Contadora sintética", "p": "hash-nuevo"})

    assert len(rows) == 1
    assert list(rows[0]._mapping) == ["usuario_id", "tenant_id", "rol"]
    usuario_id, tenant_id, rol = rows[0]
    assert (tenant_id, rol) == (TENANT_A, "contador")
    with acceso.migrator.connect() as conn:
        usuario = conn.execute(
            text("select email, nombre, password_hash, activo from usuario where id = :u"),
            {"u": usuario_id},
        ).one()
        membresias = conn.execute(
            text("select tenant_id, rol, activa from membresia where usuario_id = :u"),
            {"u": usuario_id},
        ).all()
    assert tuple(usuario) == (email, "Contadora sintética", "hash-nuevo", True)
    assert [tuple(m) for m in membresias] == [(TENANT_A, "contador", True)]
    assert invitacion_usada_en(acceso, key) is not None


def test_aceptar_invitacion_twice_creates_nothing_the_second_time(acceso):
    key, _ = invite(acceso)
    assert len(app_call(acceso, ACEPTAR, {"c": key, "n": "Uno", "p": "hash-1"})) == 1
    before = counts(acceso)
    assert app_call(acceso, ACEPTAR, {"c": key, "n": "Dos", "p": "hash-2"}) == []
    assert counts(acceso) == before


@pytest.mark.parametrize("case", ["inexistente", "usada", "vencida", "mayusculas", "corta", "hash"])
def test_aceptar_invitacion_with_an_invalid_key_creates_nothing(acceso, case):
    key, _ = invite(acceso)
    usada, _ = invite(acceso, usada="now() - interval '1 hour'")
    vencida, _ = invite(acceso, expira="now() - interval '1 minute'")
    value = {
        "inexistente": nueva_clave(),
        "usada": usada,
        "vencida": vencida,
        "mayusculas": key.upper(),
        "corta": key[:-1],
        "hash": stored_hash(key).hex(),
    }[case]
    before = counts(acceso)
    assert app_call(acceso, ACEPTAR, {"c": value, "n": "Nadie", "p": "hash-x"}) == []
    assert counts(acceso) == before
    assert invitacion_usada_en(acceso, key) is None
    assert invitacion_usada_en(acceso, vencida) is None


def test_aceptar_invitacion_with_an_existing_email_reverts_and_leaves_it_unused(acceso):
    # Q16: ON CONFLICT DO NOTHING + excepción estática; el email ya es de USER_B.
    key, _ = invite(acceso, TENANT_A, EMAIL_B)
    before = counts(acceso)
    with acceso.app.connect() as conn:
        with pytest.raises(DBAPIError) as excinfo:
            conn.execute(text(ACEPTAR), {"c": key, "n": "Intrusa", "p": "hash-intrusa"})
        conn.rollback()
    message = str(excinfo.value.orig)
    assert excinfo.value.orig.sqlstate == RAISE_EXCEPTION, message
    assert message.splitlines()[0] == INVITACION_INVALIDA
    for secret in (key, EMAIL_B, "Intrusa", "hash-intrusa", str(USER_B)):
        assert secret not in message
    # Revertida: la invitación sigue sin usar y no se creó nada.
    assert invitacion_usada_en(acceso, key) is None
    assert counts(acceso) == before
    # Y sigue sirviendo... para nada: el email sigue ocupado, otra vez el mismo error.
    with app_tx(acceso) as conn:
        assert_fails(
            conn,
            ACEPTAR,
            {"c": key, "n": "Intrusa", "p": "hash"},
            code=RAISE_EXCEPTION,
            fragment=INVITACION_INVALIDA,
        )


def test_aceptar_invitacion_ignores_owner_gucs_set_beforehand(acceso):
    # Criterios 1 y 2: con las GUC de B fijadas de antemano (incluido el usuario nuevo y
    # la clave de una invitación vigente de B) se crea el usuario nuevo en A, nada más.
    key_a, email_a = invite(acceso, TENANT_A)
    key_b, _ = invite(acceso, TENANT_B, rol="admin")
    before = counts(acceso)
    with acceso.app.begin() as conn:
        set_gucs(conn, foreign_gucs(**{"app.auth_inv_aceptar": key_b}))
        rows = conn.execute(text(ACEPTAR), {"c": key_a, "n": "Nueva A", "p": "hash-a"}).all()
        assert_no_owner_context(conn)
    assert len(rows) == 1
    usuario_id, tenant_id, rol = rows[0]
    assert usuario_id not in (USER_A, USER_B, USER_SIN_MEMBRESIA)
    assert (tenant_id, rol) == (TENANT_A, "contador")
    with acceso.migrator.connect() as conn:
        assert (
            conn.scalar(text("select email from usuario where id = :u"), {"u": usuario_id})
            == email_a
        )
        memberships = conn.execute(
            text("select tenant_id, usuario_id, rol from membresia where usuario_id in (:u, :b)"),
            {"u": usuario_id, "b": USER_B},
        ).all()
    assert sorted(tuple(m) for m in memberships) == sorted(
        [(TENANT_A, usuario_id, "contador"), (TENANT_B, USER_B, "admin")]
    )
    after = counts(acceso)
    assert after["usuario"] == before["usuario"] + 1
    assert after["membresia"] == before["membresia"] + 1
    assert invitacion_usada_en(acceso, key_b) is None


def test_aceptar_invitacion_with_an_invalid_key_and_a_valid_guc_consumes_nothing(acceso):
    key_b, _ = invite(acceso, TENANT_B)
    before = counts(acceso)
    with acceso.app.begin() as conn:
        set_gucs(conn, foreign_gucs(**{"app.auth_inv_aceptar": key_b}))
        assert conn.execute(text(ACEPTAR), {"c": nueva_clave(), "n": "X", "p": "h"}).all() == []
    assert invitacion_usada_en(acceso, key_b) is None
    assert counts(acceso) == before


# Disparadores de prueba (solo en la transacción, que se revierte): anotan en GUC
# ``prueba.*`` el id que se insertó en usuario, el usuario_id de la membresía y el valor
# de app.auth_usuario_nuevo en el momento de insertar la membresía. Corren como quien
# inserta (auth_owner, dentro de la función) y no leen tablas.
_RECORDING_TRIGGERS = (
    """
    CREATE FUNCTION public.prueba_t3_anota_usuario() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        PERFORM pg_catalog.set_config('prueba.usuario_insertado', NEW.id::text, true);
        RETURN NEW;
    END $$
    """,
    """
    CREATE FUNCTION public.prueba_t3_anota_membresia() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        PERFORM pg_catalog.set_config('prueba.membresia_usuario', NEW.usuario_id::text, true);
        PERFORM pg_catalog.set_config(
            'prueba.guc_al_insertar',
            pg_catalog.current_setting('app.auth_usuario_nuevo', true),
            true
        );
        RETURN NEW;
    END $$
    """,
    "CREATE TRIGGER prueba_t3_anota_usuario AFTER INSERT ON usuario "
    "FOR EACH ROW EXECUTE FUNCTION public.prueba_t3_anota_usuario()",
    "CREATE TRIGGER prueba_t3_anota_membresia BEFORE INSERT ON membresia "
    "FOR EACH ROW EXECUTE FUNCTION public.prueba_t3_anota_membresia()",
)


def _recorded(conn: Connection) -> dict[str, str | None]:
    return {
        name: conn.scalar(text("select current_setting(:n, true)"), {"n": f"prueba.{name}"})
        for name in ("usuario_insertado", "membresia_usuario", "guc_al_insertar")
    }


@pytest.mark.parametrize("preset", [False, True])
def test_aceptar_invitacion_membership_is_for_the_usuario_inserted_in_the_same_call(acceso, preset):
    # Revisión de seguridad de T2: app.auth_usuario_nuevo solo toma el id del INSERT
    # usuario de esa misma llamada, aunque quien llama la haya fijado antes a otro usuario.
    key, email = invite(acceso, TENANT_A, rol="contador")
    quote = acceso.app.dialect.identifier_preparer.quote
    with migrator_tx(acceso) as conn:
        for statement in _RECORDING_TRIGGERS:
            conn.exec_driver_sql(statement)
        conn.exec_driver_sql(f"SET LOCAL ROLE {quote(acceso.app_role)}")
        if preset:
            set_gucs(conn, foreign_gucs(**{"app.auth_usuario_nuevo": str(USER_SIN_MEMBRESIA)}))
        rows = conn.execute(text(ACEPTAR), {"c": key, "n": "Mismo id", "p": "h"}).all()
        assert_no_owner_context(conn)
        conn.exec_driver_sql("RESET ROLE")

        assert len(rows) == 1
        usuario_id = rows[0].usuario_id
        assert usuario_id not in (USER_A, USER_B, USER_SIN_MEMBRESIA)
        assert _recorded(conn) == {
            "usuario_insertado": str(usuario_id),
            "membresia_usuario": str(usuario_id),
            "guc_al_insertar": str(usuario_id),
        }
        assert (
            conn.scalar(text("select email from usuario where id = :u"), {"u": usuario_id}) == email
        )
        memberships = conn.execute(
            text("select usuario_id, tenant_id, rol from membresia where usuario_id in (:u, :s)"),
            {"u": usuario_id, "s": USER_SIN_MEMBRESIA},
        ).all()
        assert sorted(map(tuple, memberships)) == sorted(
            [(usuario_id, TENANT_A, "contador"), (USER_SIN_MEMBRESIA, TENANT_A, "admin")]
        )


def test_aceptar_invitacion_body_sets_usuario_nuevo_only_from_its_own_insert(acceso):
    # Y en el cuerpo: una sola asignación de v_usuario (gen_random_uuid), que es el id del
    # INSERT usuario y el único valor con que se fija app.auth_usuario_nuevo.
    with acceso.migrator.connect() as conn:
        source = conn.scalar(
            text(
                "select p.prosrc from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                "where n.nspname = 'acceso' and p.proname = 'aceptar_invitacion'"
            )
        )
    # Fuera de las listas que se vacían, app.auth_usuario_nuevo solo aparece en su set_config.
    assert source.count("set_config('app.auth_usuario_nuevo'") == 1
    assert (
        source.count("pg_catalog.set_config('app.auth_usuario_nuevo', v_usuario::text, true)") == 1
    )
    assert source.count("v_usuario :=") == 1
    assert "v_usuario := pg_catalog.gen_random_uuid();" in source
    assert "VALUES (v_usuario, v_email, p_nombre, p_password_hash)" in source
    assert "INTO v_usuario" not in source
    # El set_config del usuario nuevo va después del INSERT usuario y de su comprobación.
    insert = source.index("INSERT INTO public.usuario")
    check = source.index("IF v_filas <> 1 THEN")
    assert insert < check < source.index("'app.auth_usuario_nuevo', v_usuario")


# --- Dos llamadas en la misma transacción: la primera no abre la segunda -------------


def test_two_acceptances_with_different_keys_in_one_transaction_stay_separate(acceso):
    key_a, email_a = invite(acceso, TENANT_A, rol="contador")
    key_b, email_b = invite(acceso, TENANT_B, rol="admin")
    before = counts(acceso)
    with acceso.app.begin() as conn:
        first = conn.execute(text(ACEPTAR), {"c": key_a, "n": "Primera", "p": "h1"}).one()
        second = conn.execute(text(ACEPTAR), {"c": key_b, "n": "Segunda", "p": "h2"}).one()
        # La clave de la primera, ya consumida en esta transacción, no vuelve a servir.
        assert conn.execute(text(ACEPTAR), {"c": key_a, "n": "Otra", "p": "h3"}).all() == []
        # Ni una clave inexistente aprovecha lo que dejó la anterior.
        assert conn.execute(text(ACEPTAR), {"c": nueva_clave(), "n": "X", "p": "h4"}).all() == []
        assert_no_owner_context(conn)
    assert first.usuario_id != second.usuario_id
    assert (first.tenant_id, first.rol) == (TENANT_A, "contador")
    assert (second.tenant_id, second.rol) == (TENANT_B, "admin")
    with acceso.migrator.connect() as conn:
        rows = conn.execute(
            text(
                "select u.id, u.email, m.tenant_id, m.rol from usuario u "
                "join membresia m on m.usuario_id = u.id where u.id in (:a, :b)"
            ),
            {"a": first.usuario_id, "b": second.usuario_id},
        ).all()
    assert sorted(map(tuple, rows)) == sorted(
        [
            (first.usuario_id, email_a, TENANT_A, "contador"),
            (second.usuario_id, email_b, TENANT_B, "admin"),
        ]
    )
    after = counts(acceso)
    assert after["usuario"] == before["usuario"] + 2
    assert after["membresia"] == before["membresia"] + 2


@pytest.mark.parametrize("function", ["buscar_login", "validar_invitacion", "aceptar_invitacion"])
def test_a_previous_call_in_the_transaction_opens_nothing_for_auth_owner(acceso, function):
    # Tras la primera llamada, en la misma transacción, auth_owner no puede leer, consumir
    # ni insertar nada con la clave de otra invitación vigente: no quedó contexto.
    sql, params = _app_calls(acceso)[function]
    key_b, email_b = invite(acceso, TENANT_B)
    quote = acceso.app.dialect.identifier_preparer.quote
    with migrator_tx(acceso) as conn:
        conn.exec_driver_sql(f"SET LOCAL ROLE {quote(acceso.app_role)}")
        conn.execute(text(sql), params).all()
        conn.exec_driver_sql("RESET ROLE")
        conn.exec_driver_sql(f"SET LOCAL ROLE {AUTH_OWNER}")
        # Las tablas que auth_owner puede leer (0003); refresh_token no le está concedida.
        for table, column in (
            ("usuario", "id"),
            ("membresia", "usuario_id"),
            ("invitacion", "token_hash"),
            ("tenant", "id"),
        ):
            assert conn.scalar(text(f"select count({column}) from {table}")) == 0, table  # noqa: S608
        assert conn.execute(text(CONSUME), {"h": stored_hash(key_b)}).rowcount == 0
        assert_fails(
            conn,
            INSERT_USUARIO,
            {"id": uuid.uuid4(), "e": email_b},
            code=INSUFFICIENT_PRIVILEGE,
            fragment=RLS_VIOLATION,
        )
        assert_fails(
            conn,
            "insert into membresia (tenant_id, usuario_id, rol) values (:t, :u, 'contador')",
            {"t": TENANT_B, "u": USER_SIN_MEMBRESIA},
            code=INSUFFICIENT_PRIVILEGE,
            fragment=RLS_VIOLATION,
        )
    assert invitacion_usada_en(acceso, key_b) is None


def test_two_concurrent_acceptances_only_one_wins(acceso):
    key, _ = invite(acceso)
    results: dict[str, object] = {}
    with acceso.app.connect() as first:
        tx = first.begin()
        assert len(first.execute(text(ACEPTAR), {"c": key, "n": "Primera", "p": "h1"}).all()) == 1

        def second() -> None:
            try:
                results["rows"] = app_call(acceso, ACEPTAR, {"c": key, "n": "Segunda", "p": "h2"})
            except Exception as exc:
                results["error"] = type(exc).__name__

        worker = threading.Thread(target=second)
        worker.start()
        worker.join(timeout=0.5)
        assert worker.is_alive(), "la segunda aceptación debía esperar el bloqueo de la fila"
        tx.commit()
        worker.join(timeout=10)
    assert not worker.is_alive()
    assert results == {"rows": []}


# --- Criterio 4: con la clave de B la aplicación no ve nada más de B ---------------


def test_app_using_a_key_of_b_sees_nothing_else_of_b(acceso):
    key_b, email_b = invite(acceso, TENANT_B)
    with app_tx(acceso, TENANT_A) as conn:
        assert conn.scalar(text(VALIDAR), {"c": key_b}) is True
        rows = conn.execute(text(ACEPTAR), {"c": key_b, "n": "Nueva B", "p": "h"}).all()
        # La salida definida: id del usuario nuevo, tenant y rol de la invitación.
        assert [(r.tenant_id, r.rol) for r in rows] == [(TENANT_B, "contador")]
        assert_no_owner_context(conn)
        assert conn.scalar(text("select current_setting('app.tenant_id', true)")) == str(TENANT_A)
        assert conn.execute(text("select id, nombre from tenant")).all() == [(TENANT_A, NOMBRE_A)]
        for table in ("membresia", "invitacion", "refresh_token"):
            assert (
                conn.scalar(
                    text(f"select count(*) from {table} where tenant_id <> :a"),  # noqa: S608
                    {"a": TENANT_A},
                )
                == 0
            ), table
        visible = set(conn.scalars(text("select email from usuario")))
        assert email_b not in visible and EMAIL_B not in visible
        assert (
            conn.scalar(text("select count(id) from usuario where id = :u"), {"u": rows[0][0]}) == 0
        )
    # Nada quedó: la transacción se revirtió.
    assert invitacion_usada_en(acceso, key_b) is None


# --- A19 (d'): crear_tenant -------------------------------------------------------


def test_crear_tenant_creates_the_tenant_and_a_24h_admin_invitation(acceso):
    key, email = nueva_clave(), nuevo_email("primer.admin")
    nombre = f"Clínica nueva {uuid.uuid4().hex[:6]}"
    with acceso.migrator.begin() as conn:
        tenant_id = conn.scalar(text(CREAR), {"n": nombre, "e": email, "c": key})
        assert_no_owner_context(conn)
    assert isinstance(tenant_id, uuid.UUID)
    assert tenant_id not in (TENANT_A, TENANT_B)
    with acceso.migrator.connect() as conn:
        assert (
            conn.scalar(text("select nombre from tenant where id = :t"), {"t": tenant_id}) == nombre
        )
        inv = conn.execute(
            text(
                "select email, rol, creada_por, usada_en, token_hash, "
                "expira_en - now() between interval '23 hours 50 minutes' and interval '24 hours' "
                "from invitacion where tenant_id = :t"
            ),
            {"t": tenant_id},
        ).all()
    assert [tuple(row) for row in inv] == [(email, "admin", None, None, stored_hash(key), True)]
    # Y el primer admin la puede aceptar con la aplicación.
    rows = app_call(acceso, ACEPTAR, {"c": key, "n": "Primer admin", "p": "hash-admin"})
    assert [(r.tenant_id, r.rol) for r in rows] == [(tenant_id, "admin")]


def _tenants_named(db: AccesoDb, nombre: str) -> int:
    with db.migrator.connect() as conn:
        return conn.scalar(text("select count(*) from tenant where nombre = :n"), {"n": nombre})


@pytest.mark.parametrize("case", ["clave_repetida", "email_sin_normalizar", "email_vacio"])
def test_crear_tenant_reverts_the_tenant_if_the_invitation_fails(acceso, case):
    existing, _ = invite(acceso)
    nombre = f"Clínica que no queda {uuid.uuid4().hex[:6]}"
    key, email = {
        "clave_repetida": (existing, nuevo_email()),
        "email_sin_normalizar": (nueva_clave(), " Mayus@Ejemplo.test"),
        "email_vacio": (nueva_clave(), " "),
    }[case]
    before = counts(acceso)
    with acceso.migrator.connect() as conn:
        with pytest.raises(DBAPIError) as excinfo:
            conn.execute(text(CREAR), {"n": nombre, "e": email, "c": key})
        conn.rollback()
    assert key not in str(excinfo.value.orig)
    assert _tenants_named(acceso, nombre) == 0
    assert counts(acceso) == before


@pytest.mark.parametrize("value", ["", "%", "z" * 64, "A" * 64, "a" * 63])
def test_crear_tenant_rejects_a_malformed_key_and_creates_nothing(acceso, value):
    nombre = f"Clínica mal formada {uuid.uuid4().hex[:6]}"
    before = counts(acceso)
    with migrator_tx(acceso) as conn:
        message = assert_fails(
            conn,
            CREAR,
            {"n": nombre, "e": nuevo_email(), "c": value},
            code=INVALID_PARAMETER,
            fragment="clave_invalida",
        )
    assert message.splitlines()[0] == "clave_invalida"
    assert _tenants_named(acceso, nombre) == 0
    assert counts(acceso) == before


def test_crear_tenant_ignores_owner_gucs_set_beforehand(acceso):
    # Criterios 1 y 3: con app.auth_tenant_nuevo = A fijada de antemano, el tenant y la
    # invitación son los del tenant que la función inserta, nunca A.
    key, email = nueva_clave(), nuevo_email()
    with acceso.migrator.connect() as conn:
        invitaciones_a = conn.scalar(
            text("select count(*) from invitacion where tenant_id = :a"), {"a": TENANT_A}
        )
    with acceso.migrator.begin() as conn:
        set_gucs(conn, foreign_gucs(**{"app.auth_tenant_nuevo": str(TENANT_A)}))
        tenant_id = conn.scalar(text(CREAR), {"n": "Clínica GUC", "e": email, "c": key})
        assert_no_owner_context(conn)
    assert tenant_id != TENANT_A
    with acceso.migrator.connect() as conn:
        assert (
            conn.scalar(
                text("select tenant_id from invitacion where token_hash = :h"),
                {"h": stored_hash(key)},
            )
            == tenant_id
        )
        assert (
            conn.scalar(
                text("select count(*) from invitacion where tenant_id = :a"), {"a": TENANT_A}
            )
            == invitaciones_a
        )


def test_app_cannot_execute_crear_tenant(acceso):
    with app_tx(acceso, TENANT_A) as conn:
        assert_denied(conn, CREAR, {"n": "X", "e": nuevo_email(), "c": nueva_clave()})
        assert (
            conn.scalar(
                text(
                    "select has_function_privilege("
                    "'acceso.crear_tenant(text, text, text)', 'EXECUTE')"
                )
            )
            is False
        )


# --- A19 (e): corren como auth_owner real bajo FORCE RLS ---------------------------


@pytest.mark.parametrize(
    "policy, table, sql, with_policy, without_policy",
    [
        ("dueno_usuario_login", "usuario", "select count(*) from acceso.buscar_login(:e)", 1, 0),
        (
            "dueno_membresia_login",
            "membresia",
            "select count(tenant_id) from acceso.buscar_login(:e)",
            1,
            0,
        ),
        (
            "dueno_invitacion_validar",
            "invitacion",
            "select acceso.validar_invitacion(:c)",
            True,
            False,
        ),
    ],
)
def test_functions_run_as_auth_owner_under_force_rls(
    acceso, policy, table, sql, with_policy, without_policy
):
    # El migrador es superusuario y se salta RLS: si la función corriera como quien
    # llama, quitar la política no cambiaría nada.
    key, _ = invite(acceso)
    params = {"e": EMAIL_A, "c": key}
    with migrator_tx(acceso) as conn:
        assert conn.scalar(text(sql), params) == with_policy
        conn.exec_driver_sql(f"DROP POLICY {policy} ON {table}")
        assert conn.scalar(text(sql), params) == without_policy


def test_aceptar_runs_as_auth_owner_under_force_rls(acceso):
    key, _ = invite(acceso)
    with migrator_tx(acceso) as conn:
        conn.exec_driver_sql("DROP POLICY dueno_invitacion_consumir ON invitacion")
        assert conn.execute(text(ACEPTAR), {"c": key, "n": "X", "p": "h"}).all() == []


def test_crear_tenant_runs_as_auth_owner_under_force_rls(acceso):
    with migrator_tx(acceso) as conn:
        conn.exec_driver_sql("DROP POLICY dueno_tenant_crear ON tenant")
        assert_fails(
            conn,
            CREAR,
            {"n": "X", "e": nuevo_email(), "c": nueva_clave()},
            code=INSUFFICIENT_PRIVILEGE,
            fragment=RLS_VIOLATION,
        )


# --- Prueba 9 (§7.2): ningún contexto sobrevive a la función ----------------------


def _app_calls(db: AccesoDb) -> dict[str, tuple[str, dict[str, object]]]:
    key, _ = invite(db)
    return {
        "buscar_login": (BUSCAR, {"e": EMAIL_A}),
        "validar_invitacion": (VALIDAR, {"c": key}),
        "aceptar_invitacion": (ACEPTAR, {"c": key, "n": "Contexto", "p": "h"}),
    }


def _assert_app_sees_nothing_without_tenant(conn: Connection) -> None:
    for table in TABLES:
        column = "id" if table in ("usuario", "invitacion") else "*"
        assert conn.scalar(text(f"select count({column}) from {table}")) == 0, table  # noqa: S608


@pytest.mark.parametrize("function", ["buscar_login", "validar_invitacion", "aceptar_invitacion"])
@pytest.mark.parametrize("end", ["commit", "rollback", "rollback_to_savepoint"])
def test_function_context_does_not_survive(acceso, function, end):
    sql, params = _app_calls(acceso)[function]
    with acceso.app.connect() as conn:
        tx = conn.begin()
        if end == "rollback_to_savepoint":
            set_gucs(conn, {"app.auth_email": "antes@ejemplo.test"})
            nested = conn.begin_nested()
        conn.execute(text(sql), params).all()
        # Al volver de la función ya no queda contexto del dueño.
        assert_no_owner_context(conn)
        _assert_app_sees_nothing_without_tenant(conn)
        if end == "rollback_to_savepoint":
            nested.rollback()
            # ROLLBACK TO SAVEPOINT devuelve el valor de antes de la función.
            assert gucs(conn)["app.auth_email"] == "antes@ejemplo.test"
            tx.rollback()
        elif end == "commit":
            tx.commit()
        else:
            tx.rollback()
        with conn.begin():
            assert_no_owner_context(conn)
            _assert_app_sees_nothing_without_tenant(conn)


@pytest.mark.parametrize("end", ["commit", "rollback"])
def test_crear_tenant_leaves_no_context_usable_by_auth_owner(acceso, end):
    with acceso.migrator.connect() as conn:
        tx = conn.begin()
        conn.scalar(text(CREAR), {"n": "Clínica contexto", "e": nuevo_email(), "c": nueva_clave()})
        assert_no_owner_context(conn)
        # Sin la GUC, auth_owner ya no ve ni la fila que la función acaba de crear.
        conn.exec_driver_sql(f"SET LOCAL ROLE {AUTH_OWNER}")
        assert conn.scalar(text("select count(id) from tenant")) == 0
        conn.exec_driver_sql("RESET ROLE")
        if end == "commit":
            tx.commit()
        else:
            tx.rollback()
        with conn.begin():
            assert_no_owner_context(conn)


# --- Prueba 10 (§7.2): ON CONFLICT y now() -----------------------------------------


def _as_owner(conn: Connection, **gucs_: str) -> None:
    conn.exec_driver_sql(f"SET LOCAL ROLE {AUTH_OWNER}")
    set_gucs(conn, gucs_)


CONSUME = (
    "update invitacion set usada_en = now() where token_hash = :h "
    "and usada_en is null and expira_en > now()"
)
INSERT_USUARIO = (
    "insert into usuario (id, email, nombre, password_hash) "
    "values (:id, :e, 'Persona sintética', 'h') on conflict do nothing"
)


def test_on_conflict_do_nothing_needs_no_select_policy_on_usuario(acceso):
    # El email de la invitación ya existe (EMAIL_A). Se quita además la única política
    # SELECT de auth_owner en usuario: ON CONFLICT DO NOTHING no la necesita.
    key, _ = invite(acceso, TENANT_A, EMAIL_A)
    key_libre, email_libre = invite(acceso, TENANT_A)
    with migrator_tx(acceso) as conn:
        conn.exec_driver_sql("DROP POLICY dueno_usuario_login ON usuario")
        _as_owner(conn, **{"app.auth_inv_aceptar": key})
        assert conn.execute(text(CONSUME), {"h": stored_hash(key)}).rowcount == 1
        conflict = conn.execute(text(INSERT_USUARIO), {"id": uuid.uuid4(), "e": EMAIL_A})
        assert conflict.rowcount == 0
        set_gucs(conn, {"app.auth_inv_aceptar": key_libre})
        assert conn.execute(text(CONSUME), {"h": stored_hash(key_libre)}).rowcount == 1
        inserted = conn.execute(text(INSERT_USUARIO), {"id": uuid.uuid4(), "e": email_libre})
        assert inserted.rowcount == 1
        # Y auth_owner no puede leer usuario sin su política.
        assert conn.scalar(text("select count(id) from usuario")) == 0


def test_invitation_consumed_in_a_committed_transaction_does_not_satisfy_now(acceso):
    key, email = invite(acceso, TENANT_A)
    with acceso.migrator.begin() as conn:  # COMMIT real
        _as_owner(conn, **{"app.auth_inv_aceptar": key})
        assert conn.execute(text(CONSUME), {"h": stored_hash(key)}).rowcount == 1
    with migrator_tx(acceso) as conn:
        _as_owner(conn, **{"app.auth_inv_aceptar": key, "app.auth_usuario_nuevo": str(USER_B)})
        conn.begin_nested()  # incluso tras un SAVEPOINT en la transacción nueva
        assert_fails(
            conn,
            INSERT_USUARIO,
            {"id": uuid.uuid4(), "e": email},
            code=INSUFFICIENT_PRIVILEGE,
            fragment=RLS_VIOLATION,
        )
        assert_fails(
            conn,
            "insert into membresia (tenant_id, usuario_id, rol) values (:t, :u, 'contador')",
            {"t": TENANT_A, "u": USER_B},
            code=INSUFFICIENT_PRIVILEGE,
            fragment=RLS_VIOLATION,
        )


def test_consumed_before_a_savepoint_in_the_same_transaction_still_matches_now(acceso):
    # La trampa de now(): dentro de una misma transacción, aunque haya un SAVEPOINT de
    # por medio, la invitación consumida sigue cumpliendo usada_en = now(). Por eso
    # "consumida antes" se prueba con COMMIT real (prueba anterior), no así.
    key, email = invite(acceso, TENANT_A)
    with migrator_tx(acceso) as conn:
        _as_owner(conn, **{"app.auth_inv_aceptar": key})
        assert conn.execute(text(CONSUME), {"h": stored_hash(key)}).rowcount == 1
        conn.begin_nested()
        assert conn.execute(text(INSERT_USUARIO), {"id": uuid.uuid4(), "e": email}).rowcount == 1


def test_function_rejects_an_invitation_consumed_in_a_committed_transaction(acceso):
    key, _ = invite(acceso, TENANT_A)
    with acceso.migrator.begin() as conn:
        _as_owner(conn, **{"app.auth_inv_aceptar": key})
        assert conn.execute(text(CONSUME), {"h": stored_hash(key)}).rowcount == 1
    before = counts(acceso)
    assert app_call(acceso, ACEPTAR, {"c": key, "n": "Tarde", "p": "h"}) == []
    assert counts(acceso) == before
