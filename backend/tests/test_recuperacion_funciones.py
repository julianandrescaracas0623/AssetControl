"""Funciones ``acceso.*`` de recuperación de contraseña (spec 014, T2; migración 0016).

Comportamiento real de ``acceso.solicitar_recuperacion`` y
``acceso.restablecer_contrasena`` sobre una base temporal migrada a ``head``
(``plan.md`` §4; ``spec.md`` R2–R4, R9, R13, R15, A3, A4, A7, A10, A11; requisitos 1–11
del security-reviewer en ``tasks.md``, «Notas de cierre T1»):

- **Solicitar (R2, R13):** solo un usuario activo con **exactamente una** membresía
  activa recibe un enlace (``true``); inexistente, inactivo, sin membresía activa, con
  dos, no normalizable, vacío o comodín -> ``false`` sin error y sin filas. El cuerpo
  ejecuta las mismas sentencias en todos los casos (sin ``RETURN`` temprano).
- **Un enlace vivo (R4, A4, M1, M2):** la segunda solicitud invalida la primera; un
  pendiente vencido sin usar se invalida y no bloquea otro; dos solicitudes
  simultáneas del mismo usuario (dos conexiones) no dan ``23505`` y dejan uno vivo.
- **Restablecer (R9, A3, A7):** consume el enlace, guarda el hash recibido, revoca
  todos los refresh del usuario (todas sus membresías, de cualquier tenant) e invalida
  sus otros enlaces; vencido, usado, invalidado, inexistente o mal formado -> la misma
  excepción estática ``enlace_invalido`` sin eco; usuario o membresía que dejaron de
  ser elegibles -> ``enlace_invalido`` y nada cambia (enlace sin usar); un fallo
  intermedio revierte todo.
- **Aislamiento (A11):** la recuperación de un usuario no toca contraseña ni sesiones de
  otros (otro tenant incluido); un enlace no sirve para otra cuenta.
- **GUC (A19 de 002):** con GUC ``app.auth_*`` fijadas de antemano (residuales, de otra
  cuenta) o vacías, las funciones no hacen más de lo suyo, y al volver no queda
  contexto; ``auth_owner`` sin GUC no ve ni toca nada.
- **Privilegios:** la aplicación sigue sin acceso directo a la tabla; ``auth_owner``
  solo actualiza ``password_hash`` de ``usuario`` (sin ``DELETE``); las funciones
  corren como ``auth_owner`` bajo ``FORCE RLS``.

Las cuentas son sintéticas (``@ejemplo.test``) y se crean por prueba con ``COMMIT``
del migrador en la base temporal, que se borra al terminar.
"""

import hashlib
import re
import threading
import time
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
TABLE = "recuperacion_contrasena"

INSUFFICIENT_PRIVILEGE = "42501"
RAISE_EXCEPTION = "P0001"
INVALID_PARAMETER = "22023"
ENLACE_INVALIDO = "enlace_invalido"

TENANT_A = uuid.UUID("00000000-0000-4000-8000-00000000a016")
TENANT_B = uuid.UUID("00000000-0000-4000-8000-00000000b016")

SOLICITAR = "select acceso.solicitar_recuperacion(:e, :c)"
RESTABLECER = "select acceso.restablecer_contrasena(:c, :p)"
HASH_VIEJO = "hash-sintetico-viejo-no-valido"
HASH_NUEVO = "$argon2id$v=19$m=19456,t=2,p=1$c2ludGV0aWNv$aGFzaC1zaW50ZXRpY28tbnVldm8"

OWNER_GUCS = (
    "app.auth_email",
    "app.auth_usuario",
    "app.auth_inv_validar",
    "app.auth_inv_aceptar",
    "app.auth_usuario_nuevo",
    "app.auth_tenant_nuevo",
    "app.auth_rec_email",
    "app.auth_rec_usuario",
    "app.auth_rec_clave",
    "app.auth_reset_clave",
    "app.auth_reset_usuario",
)


def nueva_clave() -> str:
    """Lo que envía la aplicación: ``sha256(token)`` en hex minúsculo (I1)."""
    return hashlib.sha256(uuid.uuid4().hex.encode()).hexdigest()


def stored_hash(clave_hex: str) -> bytes:
    """Lo que guarda la base: ``sha256(clave)`` (doble hash)."""
    return hashlib.sha256(bytes.fromhex(clave_hex)).digest()


@dataclass(frozen=True)
class RecDb:
    app_role: str
    migrator: Engine
    app: Engine


@dataclass(frozen=True)
class Cuenta:
    id: uuid.UUID
    email: str
    membresias: dict[uuid.UUID, uuid.UUID]  # tenant -> membresia_id


def _fail(message: str) -> None:
    pytest.fail(message, pytrace=False)


def _alembic_config() -> AlembicConfig:
    config = AlembicConfig(str(ALEMBIC_INI))
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="module")
def db(database_residue_guard) -> Iterator[RecDb]:
    """Base temporal en ``head`` con dos tenants sintéticos; se borra al terminar."""
    migrator_url = read_database_url("TEST_MIGRATION_DATABASE_URL")
    app_url = read_database_url("TEST_DATABASE_URL")
    if migrator_url is None or app_url is None or not app_url.username:
        _fail(BLOCKED)
    name = f"assetcontrol_recfun_{uuid.uuid4().hex[:12]}"

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
            for tenant in (TENANT_A, TENANT_B):
                conn.execute(
                    text("insert into tenant (id, nombre) values (:id, :n)"),
                    {"id": tenant, "n": f"Clínica sintética {str(tenant)[-4:]}"},
                )
        yield RecDb(app_role=app_url.username, migrator=migrator, app=app)
    finally:
        for engine in engines:
            engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


# --- Utilidades -----------------------------------------------------------------


def cuenta(
    db: RecDb,
    membresias: tuple[tuple[uuid.UUID, bool], ...] = ((TENANT_A, True),),
    *,
    activo: bool = True,
) -> Cuenta:
    """Usuario sintético nuevo con sus membresías, confirmado por el migrador."""
    user, email = uuid.uuid4(), f"rec.{uuid.uuid4().hex[:10]}@ejemplo.test"
    ids: dict[uuid.UUID, uuid.UUID] = {}
    with db.migrator.begin() as conn:
        conn.execute(
            text(
                "insert into usuario (id, email, nombre, password_hash, activo) "
                "values (:id, :e, 'Persona sintética', :h, :a)"
            ),
            {"id": user, "e": email, "h": HASH_VIEJO, "a": activo},
        )
        for tenant, activa in membresias:
            ids[tenant] = conn.execute(
                text(
                    "insert into membresia (tenant_id, usuario_id, rol, activa) "
                    "values (:t, :u, 'admin', :a) returning id"
                ),
                {"t": tenant, "u": user, "a": activa},
            ).scalar_one()
    return Cuenta(user, email, ids)


def refresh(db: RecDb, c: Cuenta, tenant: uuid.UUID = TENANT_A, *, revocado: bool = False):
    """Un refresh vivo (o ya revocado) de una familia nueva; devuelve su ``id``."""
    with db.migrator.begin() as conn:
        return conn.execute(
            text(
                "insert into refresh_token (tenant_id, membresia_id, familia_id, token_hash, "
                "expira_en, revocado_en) values (:t, :m, :f, :h, now() + interval '7 days', "
                "case when :r then now() - interval '1 hour' end) returning id"
            ),
            {
                "t": tenant,
                "m": c.membresias[tenant],
                "f": uuid.uuid4(),
                "h": hashlib.sha256(uuid.uuid4().bytes).digest(),
                "r": revocado,
            },
        ).scalar_one()


def app_call(db: RecDb, sql: str, params: dict[str, object]):
    """Llama como la aplicación en su propia transacción confirmada; devuelve el escalar."""
    with db.app.begin() as conn:
        return conn.execute(text(sql), params).scalar_one()


def solicitar(db: RecDb, email: str, key: str | None = None) -> tuple[bool, str]:
    key = key or nueva_clave()
    return app_call(db, SOLICITAR, {"e": email, "c": key}), key


def app_fails(db: RecDb, sql: str, params: dict[str, object]) -> DBAPIError:
    """Llama como la aplicación; exige un error y revierte su transacción."""
    with db.app.connect() as conn:
        tx = conn.begin()
        try:
            with pytest.raises(DBAPIError) as excinfo:
                conn.execute(text(sql), params)
        finally:
            tx.rollback()
    return excinfo.value


def assert_enlace_invalido(error: DBAPIError, *secretos: str) -> None:
    message = str(error.orig)
    assert error.orig.sqlstate == RAISE_EXCEPTION, message
    assert error.orig.diag.message_primary == ENLACE_INVALIDO, message
    assert error.orig.diag.message_detail is None
    assert error.orig.diag.message_hint is None
    for secreto in secretos:
        if secreto:
            assert secreto not in message


def enlaces(db: RecDb, c: Cuenta) -> list[dict]:
    with db.migrator.connect() as conn:
        rows = conn.execute(
            text(
                f"select tenant_id, token_hash, expira_en, usada_en, invalidada_en, creado_en, "  # noqa: S608
                f"expira_en - creado_en as vigencia from {TABLE} "
                "where usuario_id = :u order by creado_en, id"
            ),
            {"u": c.id},
        ).mappings()
        return [dict(r) for r in rows]


def vivos(db: RecDb, c: Cuenta) -> list[dict]:
    return [e for e in enlaces(db, c) if e["usada_en"] is None and e["invalidada_en"] is None]


def password_hash(db: RecDb, c: Cuenta) -> str:
    with db.migrator.connect() as conn:
        return conn.execute(
            text("select password_hash from usuario where id = :u"), {"u": c.id}
        ).scalar_one()


def refresh_revocados(db: RecDb, ids) -> dict[uuid.UUID, object]:
    with db.migrator.connect() as conn:
        rows = conn.execute(
            text("select id, revocado_en from refresh_token where id = any(:ids)"),
            {"ids": list(ids)},
        ).all()
    return {r[0]: r[1] for r in rows}


def migrator_execute(db: RecDb, sql: str, params: dict | None = None) -> None:
    with db.migrator.begin() as conn:
        conn.execute(text(sql), params or {})


def set_gucs(conn: Connection, gucs: dict[str, str]) -> None:
    for name, value in gucs.items():
        conn.execute(text("select set_config(:n, :v, true)"), {"n": name, "v": value})


def gucs(conn: Connection) -> dict[str, str | None]:
    return {
        name: conn.scalar(text("select current_setting(:n, true)"), {"n": name})
        for name in OWNER_GUCS
    }


def assert_no_owner_context(conn: Connection) -> None:
    assert {name: value for name, value in gucs(conn).items() if value} == {}


@contextmanager
def migrator_tx(db: RecDb) -> Iterator[Connection]:
    with db.migrator.connect() as conn:
        tx = conn.begin()
        try:
            yield conn
        finally:
            tx.rollback()


def _quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def function_source(db: RecDb, name: str) -> str:
    with db.migrator.connect() as conn:
        return conn.execute(
            text(
                "select p.prosrc from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
                "where n.nspname = 'acceso' and p.proname = :n"
            ),
            {"n": name},
        ).scalar_one()


# --- Solicitar: quién recibe un enlace (R2) ----------------------------------------


def test_solicitar_with_one_active_membership_creates_a_link(db):
    c = cuenta(db)
    created, key = solicitar(db, c.email)
    assert created is True
    (enlace,) = enlaces(db, c)
    assert enlace["tenant_id"] == TENANT_A
    assert bytes(enlace["token_hash"]) == stored_hash(key)
    assert enlace["usada_en"] is None and enlace["invalidada_en"] is None
    # 30 minutos exactos con el reloj de la base (now() de la transacción).
    assert enlace["vigencia"].total_seconds() == 30 * 60


def test_solicitar_ties_the_link_to_the_tenant_of_the_only_active_membership(db):
    # Membresía inactiva en A y activa en B: el enlace es de B.
    c = cuenta(db, ((TENANT_A, False), (TENANT_B, True)))
    assert solicitar(db, c.email)[0] is True
    assert [e["tenant_id"] for e in enlaces(db, c)] == [TENANT_B]


@pytest.mark.parametrize(
    "case",
    [
        "inexistente",
        "usuario_inactivo",
        "membresia_inactiva",
        "sin_membresia",
        "dos_membresias",
        "mayusculas",
        "espacios",
        "vacio",
        "comodin_porcentaje",
        "comodin_guion_bajo",
        "no_normalizable",
    ],
)
def test_solicitar_returns_false_without_error_and_creates_nothing(db, case):
    activa = cuenta(db)  # para los casos que deforman un correo real
    accounts = {
        "usuario_inactivo": cuenta(db, activo=False),
        "membresia_inactiva": cuenta(db, ((TENANT_A, False),)),
        "sin_membresia": cuenta(db, ()),
        "dos_membresias": cuenta(db, ((TENANT_A, True), (TENANT_B, True))),
    }
    emails = {
        "inexistente": f"nadie.{uuid.uuid4().hex[:8]}@ejemplo.test",
        "mayusculas": activa.email.upper(),
        "espacios": f"  {activa.email} ",
        "vacio": "",
        "comodin_porcentaje": "%",
        "comodin_guion_bajo": "rec._%@ejemplo.test",
        "no_normalizable": "no es un correo ​",
    }
    email = emails[case] if case in emails else accounts[case].email
    with db.migrator.connect() as conn:
        before = conn.scalar(text(f"select count(*) from {TABLE}"))  # noqa: S608
    created, _ = solicitar(db, email)
    assert created is False
    with db.migrator.connect() as conn:
        assert conn.scalar(text(f"select count(*) from {TABLE}")) == before  # noqa: S608


def test_solicitar_with_null_arguments_does_nothing(db):
    c = cuenta(db)
    assert app_call(db, SOLICITAR, {"e": None, "c": nueva_clave()}) is None
    assert app_call(db, SOLICITAR, {"e": c.email, "c": None}) is None
    assert enlaces(db, c) == []


@pytest.mark.parametrize(
    "value", ["", "%", "z" * 64, "A" * 64, "a" * 63, "a" * 65, "0x" + "a" * 62]
)
def test_solicitar_rejects_a_malformed_key_without_echo(db, value):
    c = cuenta(db)
    error = app_fails(db, SOLICITAR, {"e": c.email, "c": value})
    assert error.orig.sqlstate == INVALID_PARAMETER
    assert error.orig.diag.message_primary == "clave_invalida"
    assert c.email not in str(error.orig)
    if value:
        assert value not in str(error.orig)
    assert enlaces(db, c) == []


def test_solicitar_body_runs_the_same_statements_in_every_case(db):
    # R13/A2: sin RETURN temprano ni ramas alrededor de las sentencias: la única
    # condición es el formato de la clave (no depende del correo). El UPDATE y el INSERT
    # se ejecutan siempre, con cero filas si la cuenta no es elegible.
    source = function_source(db, "solicitar_recuperacion")
    assert len(re.findall(r"\bRETURN\b", source)) == 1
    assert len(re.findall(r"\bIF\b", source)) == 2  # IF ... END IF de la clave
    assert source.index("p_clave !~") < source.index("pg_advisory_xact_lock")
    assert "WHERE v_elegible" in source
    assert "UPDATE public.recuperacion_contrasena" in source
    assert "INSERT INTO public.recuperacion_contrasena" in source


# --- Un solo enlace vivo (R4, A4, M1, M2) --------------------------------------------


def test_a_second_request_invalidates_the_previous_link(db):
    c = cuenta(db)
    _, first = solicitar(db, c.email)
    created, second = solicitar(db, c.email)
    assert created is True
    rows = enlaces(db, c)
    assert [bytes(r["token_hash"]) for r in rows] == [stored_hash(first), stored_hash(second)]
    assert rows[0]["invalidada_en"] is not None and rows[0]["usada_en"] is None
    assert [bytes(r["token_hash"]) for r in vivos(db, c)] == [stored_hash(second)]


def test_an_expired_unused_link_is_invalidated_and_does_not_block_a_new_one(db):
    # M1: la invalidación no filtra por expiración.
    c = cuenta(db)
    vencida = nueva_clave()
    migrator_execute(
        db,
        f"insert into {TABLE} (tenant_id, usuario_id, token_hash, expira_en, creado_en) "  # noqa: S608
        "values (:t, :u, :h, now() - interval '31 minutes', now() - interval '1 hour')",
        {"t": TENANT_A, "u": c.id, "h": stored_hash(vencida)},
    )
    created, nueva = solicitar(db, c.email)
    assert created is True
    rows = enlaces(db, c)
    assert rows[0]["invalidada_en"] is not None
    assert [bytes(r["token_hash"]) for r in vivos(db, c)] == [stored_hash(nueva)]


def _wait_until_blocked(db: RecDb, application_name: str) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with db.migrator.connect() as conn:
            waiting = conn.scalar(
                text(
                    "select count(*) from pg_stat_activity "
                    "where application_name = :n and wait_event_type = 'Lock'"
                ),
                {"n": application_name},
            )
        if waiting:
            return
        time.sleep(0.05)
    pytest.fail("la segunda solicitud no llegó a esperar el candado", pytrace=False)


def test_two_concurrent_requests_of_the_same_user_never_collide(db):
    # M2: la segunda espera el candado de la primera (dos conexiones reales); al
    # confirmar la primera, la segunda invalida su enlace e inserta el suyo. Sin 23505.
    c = cuenta(db)
    name = f"rec_m2_{uuid.uuid4().hex[:8]}"
    second_engine = create_engine(
        db.app.url, poolclass=NullPool, connect_args={"application_name": name}
    )
    results: dict[str, object] = {}

    def second_request() -> None:
        try:
            with second_engine.begin() as conn:
                results["second"] = conn.execute(
                    text(SOLICITAR), {"e": c.email, "c": nueva_clave()}
                ).scalar_one()
        except Exception as exc:  # noqa: BLE001 - se informa en la aserción
            results["error"] = exc

    try:
        with db.app.connect() as conn:
            tx = conn.begin()
            results["first"] = conn.execute(
                text(SOLICITAR), {"e": c.email, "c": nueva_clave()}
            ).scalar_one()
            worker = threading.Thread(target=second_request)
            worker.start()
            _wait_until_blocked(db, name)
            tx.commit()
        worker.join(timeout=15)
    finally:
        second_engine.dispose()
    assert "error" not in results, results.get("error")
    assert results == {"first": True, "second": True}
    rows = enlaces(db, c)
    assert len(rows) == 2
    assert len(vivos(db, c)) == 1
    assert rows[0]["invalidada_en"] is not None


def test_simultaneous_requests_from_many_connections_leave_one_live_link(db):
    c = cuenta(db)
    barrier = threading.Barrier(4)
    outcomes: list[object] = []

    def request() -> None:
        engine = create_engine(db.app.url, poolclass=NullPool)
        try:
            with engine.begin() as conn:
                barrier.wait(timeout=10)
                outcomes.append(
                    conn.execute(text(SOLICITAR), {"e": c.email, "c": nueva_clave()}).scalar_one()
                )
        except Exception as exc:  # noqa: BLE001 - se informa en la aserción
            outcomes.append(exc)
        finally:
            engine.dispose()

    workers = [threading.Thread(target=request) for _ in range(4)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=30)
    assert outcomes == [True] * 4
    assert len(enlaces(db, c)) == 4
    assert len(vivos(db, c)) == 1


# --- Restablecer (R9, A3, A5, A7) -----------------------------------------------------


def test_restablecer_consumes_the_link_updates_the_hash_and_revokes_every_session(db):
    c = cuenta(db, ((TENANT_A, True), (TENANT_B, False)))
    vivos_a = [refresh(db, c), refresh(db, c)]
    vivo_b = refresh(db, c, TENANT_B)  # membresía inactiva de otro tenant: también se revoca
    ya_revocado = refresh(db, c, revocado=True)
    with db.migrator.connect() as conn:
        antes = conn.scalar(
            text("select revocado_en from refresh_token where id = :i"), {"i": ya_revocado}
        )
    _, key = solicitar(db, c.email)

    assert app_call(db, RESTABLECER, {"c": key, "p": HASH_NUEVO}) == c.id

    assert password_hash(db, c) == HASH_NUEVO
    revocados = refresh_revocados(db, [*vivos_a, vivo_b, ya_revocado])
    assert all(revocados[i] is not None for i in (*vivos_a, vivo_b))
    assert revocados[ya_revocado] == antes  # no se reescribe una revocación anterior
    (enlace,) = enlaces(db, c)
    assert enlace["usada_en"] is not None and enlace["invalidada_en"] is None


def test_restablecer_invalidates_any_other_pending_link_of_the_user(db):
    # Con el índice parcial no puede haber dos pendientes del mismo usuario salvo por una
    # carrera; para ejercitar la sentencia y su política de forma determinista se quita el
    # índice dentro de una transacción que se revierte y se siembran dos pendientes.
    c = cuenta(db)
    otro = cuenta(db)
    key, other_key, foreign_key = nueva_clave(), nueva_clave(), nueva_clave()
    with migrator_tx(db) as conn:
        conn.exec_driver_sql(f"DROP INDEX {TABLE}_pendiente_key")
        for user, k in ((c, key), (c, other_key), (otro, foreign_key)):
            conn.execute(
                text(
                    f"insert into {TABLE} (tenant_id, usuario_id, token_hash, expira_en) "  # noqa: S608
                    "values (:t, :u, :h, now() + interval '30 minutes')"
                ),
                {"t": TENANT_A, "u": user.id, "h": stored_hash(k)},
            )
        conn.exec_driver_sql(f"SET LOCAL ROLE {_quoted(db.app_role)}")
        assert conn.scalar(text(RESTABLECER), {"c": key, "p": HASH_NUEVO}) == c.id
        conn.exec_driver_sql("RESET ROLE")
        rows = {
            bytes(r[0]): (r[1] is not None, r[2] is not None)
            for r in conn.execute(
                text(
                    f"select token_hash, usada_en, invalidada_en from {TABLE} "  # noqa: S608
                    "where usuario_id = any(:u)"
                ),
                {"u": [c.id, otro.id]},
            )
        }
    assert rows == {
        stored_hash(key): (True, False),  # consumido
        stored_hash(other_key): (False, True),  # el otro pendiente del usuario: invalidado
        stored_hash(foreign_key): (False, False),  # el de otra cuenta: intacto
    }


def test_restablecer_body_invalidates_the_other_pending_links(db):
    source = function_source(db, "restablecer_contrasena")
    assert "UPDATE public.recuperacion_contrasena AS r SET invalidada_en" in source


def test_a_link_can_be_used_only_once(db):
    c = cuenta(db)
    _, key = solicitar(db, c.email)
    assert app_call(db, RESTABLECER, {"c": key, "p": HASH_NUEVO}) == c.id
    migrator_execute(
        db, "update usuario set password_hash = :h where id = :u", {"h": HASH_VIEJO, "u": c.id}
    )
    # Hash con formato válido: el rechazo se debe al enlace ya usado, no al formato (I1).
    assert_enlace_invalido(app_fails(db, RESTABLECER, {"c": key, "p": HASH_NUEVO + "x"}), key)
    assert password_hash(db, c) == HASH_VIEJO


# --- Formato del hash recibido (I1 de la revisión de T2) ----------------------------------


@pytest.mark.parametrize(
    "value",
    [
        "",
        "hash-sin-prefijo",
        "argon2id$v=19$m=19456,t=2,p=1$c2Fs$aGFzaA",
        " $argon2id$v=19$m=19456,t=2,p=1$c2Fs$aGFzaA",
        "$ARGON2ID$v=19$m=19456,t=2,p=1$c2Fs$aGFzaA",
        "$argon2i$v=19$m=19456,t=2,p=1$c2Fs$aGFzaA",
        "$argon2d$v=19$m=19456,t=2,p=1$c2Fs$aGFzaA",
        "$2b$12$abcdefghijklmnopqrstuuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0",
        # B1 de la auditoría de T2: formato completo de argon2-cffi, no solo el prefijo.
        "$argon2id$",
        "$argon2id$v=19$",
        "$argon2id$v=19$m=19456,t=2,p=1$c2Fs",
        "$argon2id$v=19$m=19456,t=2,p=1$c2Fs$",
        "$argon2id$v=16$m=19456,t=2,p=1$c2Fs$aGFzaA",
        "$argon2id$v=19$m=19456,t=2$c2Fs$aGFzaA",
        "$argon2id$v=19$m=19456,t=2,p=1$c2Fs$aGFzaA==",
        "$argon2id$v=19$m=19456,t=2,p=1$c2Fs$aGFz-aA",
        "$argon2id$v=19$m=19456,t=2,p=1$c2Fs$aGFzaA\n",
        "$argon2id$v=19$m=19456,t=2,p=1$c2Fs$aGFzaA$extra",
        "$argon2id$v=19$m=19456,t=2,p=1$c2Fs$" + "A" * 256,
    ],
    ids=[
        "vacio",
        "sin_prefijo",
        "sin_dolar_inicial",
        "espacio_inicial",
        "mayusculas",
        "argon2i",
        "argon2d",
        "bcrypt",
        "solo_prefijo",
        "sin_parametros",
        "sin_hash",
        "hash_vacio",
        "otra_version",
        "parametros_incompletos",
        "con_relleno",
        "caracter_fuera_de_base64",
        "salto_final",
        "segmento_extra",
        "demasiado_largo",
    ],
)
def test_restablecer_rejects_a_hash_that_is_not_argon2id_and_changes_nothing(db, value):
    # Un hash vacío o de otro formato dejaría la cuenta sin poder entrar: la función lo
    # rechaza con la misma excepción estática, antes de consumir el enlace.
    c = cuenta(db)
    sessions = [refresh(db, c), refresh(db, c)]
    _, key = solicitar(db, c.email)
    before = enlaces(db, c)

    error = app_fails(db, RESTABLECER, {"c": key, "p": value})

    assert_enlace_invalido(error, key, value.strip())
    assert password_hash(db, c) == HASH_VIEJO
    assert refresh_revocados(db, sessions) == dict.fromkeys(sessions)
    assert enlaces(db, c) == before
    (enlace,) = vivos(db, c)
    assert enlace["usada_en"] is None
    # El mismo enlace, que sigue sin usar, funciona con un hash válido.
    assert app_call(db, RESTABLECER, {"c": key, "p": HASH_NUEVO}) == c.id
    assert password_hash(db, c) == HASH_NUEVO


# Formato completo que produce argon2-cffi (B1): versión 19, parámetros, sal y hash en
# base64 sin relleno; el mismo que fija la función (sin barras invertidas).
REAL_HASH_FORMAT = re.compile(
    r"[$]argon2id[$]v=19[$]m=[0-9]+,t=[0-9]+,p=[0-9]+[$][A-Za-z0-9+/]+[$][A-Za-z0-9+/]+"
)


@pytest.mark.parametrize("params", ["ARGON2_TEST_PARAMS", "ARGON2_PARAMS"])
def test_restablecer_accepts_the_hash_the_application_produces(db, params):
    # El formato comprobado es el que genera de verdad la aplicación (argon2-cffi,
    # Type.ID), con los parámetros de prueba y con los de producción.
    from app.auth import credentials

    real = credentials.Passwords(getattr(credentials, params), wait_seconds=0).hash(
        "frase-sintetica-de-prueba"
    )
    assert REAL_HASH_FORMAT.fullmatch(real), real
    assert len(real) <= 255
    c = cuenta(db)
    _, key = solicitar(db, c.email)
    assert app_call(db, RESTABLECER, {"c": key, "p": real}) == c.id
    assert password_hash(db, c) == real


@pytest.mark.parametrize("length, accepted", [(255, True), (256, False)])
def test_the_hash_length_limit_is_255(db, length, accepted):
    prefix = "$argon2id$v=19$m=19456,t=2,p=1$c2ludGV0aWNv$"
    value = prefix + "A" * (length - len(prefix))
    assert len(value) == length
    c = cuenta(db)
    _, key = solicitar(db, c.email)
    if accepted:
        assert app_call(db, RESTABLECER, {"c": key, "p": value}) == c.id
        assert password_hash(db, c) == value
    else:
        assert_enlace_invalido(app_fails(db, RESTABLECER, {"c": key, "p": value}), key)
        assert password_hash(db, c) == HASH_VIEJO
        assert len(vivos(db, c)) == 1


def test_restablecer_works_with_standard_conforming_strings_off(db):
    # B1: el formato no usa barras invertidas, así que no depende de esta GUC de sesión
    # (que el rol de la aplicación puede cambiar). Conexión nueva: PL/pgSQL compila el
    # cuerpo con la configuración de la sesión que lo ejecuta por primera vez.
    c = cuenta(db)
    session = refresh(db, c)
    _, key = solicitar(db, c.email)
    engine = create_engine(db.app.url, poolclass=NullPool)
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("SET standard_conforming_strings = off")
            assert conn.scalar(text("show standard_conforming_strings")) == "off"
            assert conn.execute(text(RESTABLECER), {"c": key, "p": HASH_NUEVO}).scalar_one() == c.id
    finally:
        engine.dispose()
    assert password_hash(db, c) == HASH_NUEVO
    assert refresh_revocados(db, [session])[session] is not None


def test_the_hash_format_is_checked_before_touching_any_table(db):
    # R13/A2: la comprobación va con la de la clave, antes de la primera sentencia sobre
    # tablas, y no depende de que el usuario exista.
    source = function_source(db, "restablecer_contrasena")
    for check in (
        source.index("p_password_hash !~"),
        source.index("pg_catalog.length(p_password_hash) > 255"),
    ):
        assert check < source.index("UPDATE public.recuperacion_contrasena")
        assert check < source.index("public.usuario")
        assert check < source.index("set_config('app.auth_reset_clave'")
    # B1: sin barras invertidas en el cuerpo (no depende de standard_conforming_strings).
    assert "\\" not in source


@pytest.mark.parametrize("case", ["vencido", "invalidado", "inexistente"])
def test_a_link_that_is_not_live_gives_the_same_static_error(db, case):
    c = cuenta(db)
    session = refresh(db, c)
    if case == "vencido":
        key = nueva_clave()
        migrator_execute(
            db,
            f"insert into {TABLE} (tenant_id, usuario_id, token_hash, expira_en, creado_en) "  # noqa: S608
            "values (:t, :u, :h, now() - interval '1 second', now() - interval '20 minutes')",
            {"t": TENANT_A, "u": c.id, "h": stored_hash(key)},
        )
    elif case == "invalidado":
        _, key = solicitar(db, c.email)
        solicitar(db, c.email)
    else:
        key = nueva_clave()
    before = enlaces(db, c)
    error = app_fails(db, RESTABLECER, {"c": key, "p": HASH_NUEVO})
    assert_enlace_invalido(error, key, c.email, HASH_NUEVO)
    assert password_hash(db, c) == HASH_VIEJO
    assert refresh_revocados(db, [session]) == {session: None}
    assert enlaces(db, c) == before


@pytest.mark.parametrize(
    "value",
    [
        "",
        "%",
        "_" * 64,
        "z" * 64,
        "A" * 64,
        "a" * 63,
        "a" * 65,
        "g" * 64,
        "a" * 64 + "\n",
        " " * 64,
    ],
)
def test_a_malformed_key_gives_the_same_static_error_without_echo(db, value):
    error = app_fails(db, RESTABLECER, {"c": value, "p": HASH_NUEVO})
    assert_enlace_invalido(error, value.strip(), HASH_NUEVO)


def test_the_expiry_is_checked_with_the_database_clock(db):
    # Vigente al sembrar (1 segundo); se consume tras vencer según now() de la base.
    c = cuenta(db)
    key = nueva_clave()
    migrator_execute(
        db,
        f"insert into {TABLE} (tenant_id, usuario_id, token_hash, expira_en) "  # noqa: S608
        "values (:t, :u, :h, now() + interval '1 second')",
        {"t": TENANT_A, "u": c.id, "h": stored_hash(key)},
    )
    with db.migrator.connect() as conn:
        conn.execute(text("select pg_sleep(1.2)"))
    assert_enlace_invalido(app_fails(db, RESTABLECER, {"c": key, "p": HASH_NUEVO}), key)


def test_restablecer_with_null_arguments_does_nothing(db):
    c = cuenta(db)
    _, key = solicitar(db, c.email)
    assert app_call(db, RESTABLECER, {"c": key, "p": None}) is None
    assert app_call(db, RESTABLECER, {"c": None, "p": HASH_NUEVO}) is None
    assert password_hash(db, c) == HASH_VIEJO
    assert len(vivos(db, c)) == 1


@pytest.mark.parametrize(
    "change",
    [
        "update usuario set activo = false where id = :u",
        "update membresia set activa = false where usuario_id = :u",
        # Segunda membresía activa: deja de ser exactamente una.
        "insert into membresia (tenant_id, usuario_id, rol) values (:b, :u, 'contador')",
        # La única membresía activa pasa a otro tenant: no es la del enlace.
        "update membresia set activa = (tenant_id = :b) where usuario_id = :u; "
        "insert into membresia (tenant_id, usuario_id, rol) values (:b, :u, 'contador')",
    ],
    ids=["usuario_inactivo", "membresia_inactiva", "dos_membresias", "otro_tenant"],
)
def test_restablecer_rechecks_the_account_and_leaves_the_link_unused(db, change):
    c = cuenta(db)
    session = refresh(db, c)
    _, key = solicitar(db, c.email)
    with db.migrator.begin() as conn:
        for statement in change.split("; "):
            conn.execute(text(statement), {"u": c.id, "b": TENANT_B})
    assert_enlace_invalido(app_fails(db, RESTABLECER, {"c": key, "p": HASH_NUEVO}), key)
    assert password_hash(db, c) == HASH_VIEJO
    assert refresh_revocados(db, [session]) == {session: None}
    (enlace,) = enlaces(db, c)
    assert enlace["usada_en"] is None and enlace["invalidada_en"] is None


def test_a_failure_in_an_intermediate_step_reverts_everything(db):
    # A7: un disparador (en una transacción que se revierte) hace fallar la revocación
    # de los refresh: el consumo y el cambio de contraseña también se revierten.
    c = cuenta(db)
    session = refresh(db, c)
    _, key = solicitar(db, c.email)
    with migrator_tx(db) as conn:
        conn.exec_driver_sql(
            "CREATE FUNCTION pg_temp.falla() RETURNS trigger LANGUAGE plpgsql AS "
            "$$BEGIN RAISE EXCEPTION 'fallo_inyectado'; END$$"
        )
        conn.exec_driver_sql(
            "CREATE TRIGGER falla BEFORE UPDATE ON refresh_token "
            "FOR EACH ROW EXECUTE FUNCTION pg_temp.falla()"
        )
        conn.exec_driver_sql(f"SET LOCAL ROLE {_quoted(db.app_role)}")
        nested = conn.begin_nested()
        with pytest.raises(DBAPIError) as excinfo:
            conn.execute(text(RESTABLECER), {"c": key, "p": HASH_NUEVO})
        nested.rollback()
        assert "fallo_inyectado" in str(excinfo.value.orig)
        conn.exec_driver_sql("RESET ROLE")
        assert (
            conn.scalar(text("select password_hash from usuario where id = :u"), {"u": c.id})
            == HASH_VIEJO
        )
        assert (
            conn.scalar(
                text(f"select usada_en from {TABLE} where usuario_id = :u"),  # noqa: S608
                {"u": c.id},
            )
            is None
        )
        assert (
            conn.scalar(text("select revocado_en from refresh_token where id = :i"), {"i": session})
            is None
        )


# --- Aislamiento (A11, requisito 8) ---------------------------------------------------


def test_recovering_one_user_never_touches_other_users_or_tenants(db):
    a = cuenta(db)
    vecino_a = cuenta(db)
    b = cuenta(db, ((TENANT_B, True),))
    sessions = {"a": refresh(db, a), "vecino": refresh(db, vecino_a), "b": refresh(db, b, TENANT_B)}
    _, key_b = solicitar(db, b.email)
    _, key_vecino = solicitar(db, vecino_a.email)
    _, key_a = solicitar(db, a.email)

    assert app_call(db, RESTABLECER, {"c": key_a, "p": HASH_NUEVO}) == a.id

    assert password_hash(db, a) == HASH_NUEVO
    assert password_hash(db, vecino_a) == HASH_VIEJO
    assert password_hash(db, b) == HASH_VIEJO
    revocados = refresh_revocados(db, sessions.values())
    assert revocados[sessions["a"]] is not None
    assert revocados[sessions["vecino"]] is None
    assert revocados[sessions["b"]] is None
    # Los enlaces ajenos siguen vivos y solo sirven para su propia cuenta.
    assert len(vivos(db, vecino_a)) == 1 and len(vivos(db, b)) == 1
    assert app_call(db, RESTABLECER, {"c": key_b, "p": HASH_NUEVO + "b"}) == b.id
    assert password_hash(db, a) == HASH_NUEVO
    assert password_hash(db, b) == HASH_NUEVO + "b"


# --- GUC: residuales, vacías y sin contexto al volver (A19 de 002) ---------------------


def _victim_gucs(victim: Cuenta, key: str) -> dict[str, str]:
    return {
        "app.auth_email": victim.email,
        "app.auth_usuario": str(victim.id),
        "app.auth_rec_email": victim.email,
        "app.auth_rec_usuario": str(victim.id),
        "app.auth_rec_clave": key,
        "app.auth_reset_clave": key,
        "app.auth_reset_usuario": str(victim.id),
    }


def test_residual_gucs_of_another_account_do_not_widen_solicitar(db):
    victim = cuenta(db)
    _, victim_key = solicitar(db, victim.email)
    with db.app.begin() as conn:
        set_gucs(conn, _victim_gucs(victim, victim_key))
        created = conn.execute(
            text(SOLICITAR), {"e": f"nadie.{uuid.uuid4().hex[:6]}@ejemplo.test", "c": nueva_clave()}
        ).scalar_one()
        assert created is False
        assert_no_owner_context(conn)
    assert [bytes(e["token_hash"]) for e in vivos(db, victim)] == [stored_hash(victim_key)]


def test_residual_gucs_of_another_account_do_not_widen_restablecer(db):
    victim = cuenta(db)
    session = refresh(db, victim)
    _, victim_key = solicitar(db, victim.email)
    with db.app.connect() as conn:
        tx = conn.begin()
        try:
            set_gucs(conn, _victim_gucs(victim, victim_key))
            nested = conn.begin_nested()
            with pytest.raises(DBAPIError) as excinfo:
                conn.execute(text(RESTABLECER), {"c": nueva_clave(), "p": HASH_NUEVO})
            nested.rollback()
        finally:
            tx.rollback()
    assert_enlace_invalido(excinfo.value, victim_key)
    assert password_hash(db, victim) == HASH_VIEJO
    assert refresh_revocados(db, [session]) == {session: None}
    assert len(vivos(db, victim)) == 1


# I2 de la revisión de T2: las GUC nuevas de una «víctima», fijadas por quien llama, no
# amplían las funciones de 0004 (que no las vacían): las políticas nuevas son TO
# auth_owner y se suman a las de 0003 mientras esas funciones corren como auth_owner.
NEW_GUCS = tuple(g for g in OWNER_GUCS if g.startswith(("app.auth_rec_", "app.auth_reset_")))
OLD_GUCS = tuple(g for g in OWNER_GUCS if g not in NEW_GUCS)


def _new_victim_gucs(victim: Cuenta, key: str) -> dict[str, str]:
    gucs_ = {k: v for k, v in _victim_gucs(victim, key).items() if k in NEW_GUCS}
    assert set(gucs_) == set(NEW_GUCS)
    return gucs_


def _snapshot(conn: Connection) -> dict[str, object]:
    """Estado de las tablas de acceso con claves estables (sin ids generados)."""
    queries = {
        "usuario": "select email, nombre, password_hash, activo from usuario",
        "membresia": "select u.email, m.tenant_id::text, m.rol, m.activa from membresia m "
        "join usuario u on u.id = m.usuario_id",
        "tenant": "select nombre from tenant",
        "invitacion": "select encode(token_hash, 'hex'), email, rol, usada_en is not null "
        "from invitacion",
        "refresh_token": "select id::text, revocado_en is not null from refresh_token",
        TABLE: f"select encode(token_hash, 'hex'), usada_en is not null, "  # noqa: S608
        f"invalidada_en is not null from {TABLE}",
    }
    return {
        name: sorted(map(tuple, conn.execute(text(sql)).all())) for name, sql in queries.items()
    }


def _invitacion(conn: Connection, email: str, key: str) -> None:
    conn.execute(
        text(
            "insert into invitacion (tenant_id, email, rol, token_hash, expira_en) "
            "values (:t, :e, 'contador', :h, now() + interval '24 hours')"
        ),
        {"t": TENANT_A, "e": email, "h": stored_hash(key)},
    )


def _old_inputs(victim: Cuenta) -> dict[str, str]:
    """Entradas fijas del caso: las dos pasadas (con y sin GUC) usan las mismas."""
    tag = uuid.uuid4().hex[:8]
    return {
        "victim": victim.email,
        "nuevo": f"inv.{tag}@ejemplo.test",
        "validar": f"val.{tag}@ejemplo.test",
        "tenant": f"adm.{tag}@ejemplo.test",
        "k_validar": nueva_clave(),
        "k_aceptar": nueva_clave(),
        "k_victima": nueva_clave(),
        "k_tenant": nueva_clave(),
        "k_inexistente": nueva_clave(),
    }


def _old_call(conn: Connection, app_role: str, case: str, otra: Cuenta, i: dict[str, str]):
    """Prepara y llama a una función de 0004; devuelve el resultado normalizado."""
    _invitacion(conn, i["validar"], i["k_validar"])
    _invitacion(conn, i["nuevo"], i["k_aceptar"])
    _invitacion(conn, i["victim"], i["k_victima"])
    victim_email = i["victim"]
    keys = {
        "validar_viva": i["k_validar"],
        "aceptar_nueva": i["k_aceptar"],
        "aceptar_correo_victima": i["k_victima"],
    }
    calls = {
        "buscar_login_otra": ("select * from acceso.buscar_login(:e)", {"e": otra.email}),
        "buscar_login_victima": ("select * from acceso.buscar_login(:e)", {"e": victim_email}),
        "buscar_login_inexistente": (
            "select * from acceso.buscar_login(:e)",
            {"e": "nadie.i2@ejemplo.test"},
        ),
        "validar_viva": ("select acceso.validar_invitacion(:c)", {"c": keys["validar_viva"]}),
        "validar_inexistente": (
            "select acceso.validar_invitacion(:c)",
            {"c": i["k_inexistente"]},
        ),
        "aceptar_nueva": (
            "select tenant_id, rol from acceso.aceptar_invitacion(:c, 'Persona I2', :p)",
            {"c": keys["aceptar_nueva"], "p": HASH_NUEVO},
        ),
        "aceptar_correo_victima": (
            "select tenant_id, rol from acceso.aceptar_invitacion(:c, 'Persona I2', :p)",
            {"c": keys["aceptar_correo_victima"], "p": HASH_NUEVO},
        ),
        "aceptar_inexistente": (
            "select tenant_id, rol from acceso.aceptar_invitacion(:c, 'Persona I2', :p)",
            {"c": i["k_inexistente"], "p": HASH_NUEVO},
        ),
        "crear_tenant": (
            "select acceso.crear_tenant('Clínica sintética I2', :e, :c) is not null",
            {"e": i["tenant"], "c": i["k_tenant"]},
        ),
    }
    sql, params = calls[case]
    if case != "crear_tenant":  # crear_tenant: EXECUTE solo del migrador (C6)
        conn.exec_driver_sql(f"SET LOCAL ROLE {_quoted(app_role)}")
    nested = conn.begin_nested()
    try:
        rows = sorted(map(tuple, conn.execute(text(sql), params).all()))
        result: object = ("ok", rows)
    except DBAPIError as exc:
        result = ("error", exc.orig.sqlstate, exc.orig.diag.message_primary)
        nested.rollback()
    else:
        nested.commit()
    return result


OLD_CASES = [
    "buscar_login_otra",
    "buscar_login_victima",
    "buscar_login_inexistente",
    "validar_viva",
    "validar_inexistente",
    "aceptar_nueva",
    "aceptar_correo_victima",
    "aceptar_inexistente",
    "crear_tenant",
]


@pytest.mark.parametrize("case", OLD_CASES)
def test_new_gucs_of_a_victim_do_not_widen_the_old_functions(db, case):
    victim = cuenta(db)
    otra = cuenta(db)
    session = refresh(db, victim)
    _, victim_key = solicitar(db, victim.email)
    victim_gucs = _new_victim_gucs(victim, victim_key)
    inputs = _old_inputs(victim)

    outcomes = {}
    for with_gucs in (False, True):
        with migrator_tx(db) as conn:
            if with_gucs:
                set_gucs(conn, victim_gucs)
            result = _old_call(conn, db.app_role, case, otra, inputs)
            after = gucs(conn)
            conn.exec_driver_sql("RESET ROLE")
            outcomes[with_gucs] = (result, _snapshot(conn))
        # Sin contexto residual del dueño: las GUC de 0004 vacías; las nuevas, tal cual
        # las dejó quien llama (0004 no las lee ni las cambia).
        assert {g: after[g] for g in OLD_GUCS if after[g]} == {}
        # Spec 017, T3a (0018): buscar_login se reescribió y ahora vacía también las GUC de
        # 0016 (más estricto: no deja contexto del dueño de ninguna migración).
        clears_all = case.startswith("buscar_login")
        expected_new = victim_gucs if with_gucs and not clears_all else {}
        assert {g: after[g] for g in NEW_GUCS if after[g]} == expected_new

    assert outcomes[True] == outcomes[False]
    # Control: cada caso recorre de verdad su camino (no es una igualdad vacía).
    result = outcomes[False][0]
    expected = {
        "buscar_login_otra": lambda r: r[0] == "ok" and len(r[1]) == 1,
        "buscar_login_victima": lambda r: r[0] == "ok" and len(r[1]) == 1,
        "buscar_login_inexistente": lambda r: r == ("ok", []),
        "validar_viva": lambda r: r == ("ok", [(True,)]),
        "validar_inexistente": lambda r: r == ("ok", [(False,)]),
        "aceptar_nueva": lambda r: r == ("ok", [(TENANT_A, "contador")]),
        "aceptar_correo_victima": lambda r: r == ("error", RAISE_EXCEPTION, "invitacion_invalida"),
        "aceptar_inexistente": lambda r: r == ("ok", []),
        "crear_tenant": lambda r: r == ("ok", [(True,)]),
    }[case]
    assert expected(result), result
    # Y nada de la víctima cambió fuera de esas transacciones revertidas.
    assert password_hash(db, victim) == HASH_VIEJO
    assert refresh_revocados(db, [session]) == {session: None}
    assert [bytes(e["token_hash"]) for e in vivos(db, victim)] == [stored_hash(victim_key)]


@pytest.mark.parametrize("function", ["solicitar", "restablecer"])
def test_no_owner_context_survives_the_call(db, function):
    c = cuenta(db)
    _, key = solicitar(db, c.email)
    sql, params = {
        "solicitar": (SOLICITAR, {"e": c.email, "c": nueva_clave()}),
        "restablecer": (RESTABLECER, {"c": key, "p": HASH_NUEVO}),
    }[function]
    with db.app.connect() as conn:
        tx = conn.begin()
        conn.execute(text(sql), params).scalar_one()
        assert_no_owner_context(conn)
        tx.rollback()


@pytest.mark.parametrize("value", [None, "", "%", "_", "*", "A" * 64, "no-es-uuid"])
def test_auth_owner_without_a_valid_guc_sees_and_touches_nothing(db, value):
    c = cuenta(db)
    solicitar(db, c.email)
    with migrator_tx(db) as conn:
        conn.exec_driver_sql(f"SET LOCAL ROLE {AUTH_OWNER}")
        if value is not None:
            set_gucs(conn, {name: value for name in OWNER_GUCS})
        assert conn.scalar(text(f"select count(usuario_id) from {TABLE}")) == 0  # noqa: S608
        assert conn.scalar(text("select count(id) from usuario")) == 0
        assert conn.scalar(text("select count(id) from membresia")) == 0
        assert conn.scalar(text("select count(membresia_id) from refresh_token")) == 0
        touched = conn.execute(
            text("update usuario set password_hash = 'x' where id = :u"), {"u": c.id}
        )
        assert touched.rowcount == 0
        touched = conn.execute(
            text("update refresh_token set revocado_en = now() where revocado_en is null")
        )
        assert touched.rowcount == 0
        touched = conn.execute(
            text(f"update {TABLE} set invalidada_en = now() where usuario_id = :u"),  # noqa: S608
            {"u": c.id},
        )
        assert touched.rowcount == 0


# --- Privilegios ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "statement",
    [
        f"select count(*) from {TABLE}",  # noqa: S608
        f"insert into {TABLE} (tenant_id, usuario_id, token_hash, expira_en) "  # noqa: S608
        "values (:t, :u, :h, now() + interval '5 minutes')",
        f"update {TABLE} set usada_en = now() where usuario_id = :u",  # noqa: S608
        f"delete from {TABLE} where usuario_id = :u",  # noqa: S608
    ],
)
@pytest.mark.parametrize("tenant", [None, TENANT_A])
def test_the_app_still_has_no_direct_access_to_the_table(db, statement, tenant):
    c = cuenta(db)
    with db.app.connect() as conn:
        tx = conn.begin()
        try:
            if tenant is not None:
                set_gucs(conn, {"app.tenant_id": str(tenant)})
            with pytest.raises(DBAPIError) as excinfo:
                conn.execute(
                    text(statement), {"t": TENANT_A, "u": c.id, "h": stored_hash(nueva_clave())}
                )
        finally:
            tx.rollback()
    assert excinfo.value.orig.sqlstate == INSUFFICIENT_PRIVILEGE


@pytest.mark.parametrize(
    "statement",
    [
        "update usuario set nombre = 'x' where id = :u",
        "update usuario set activo = false where id = :u",
        "update usuario set email = 'x@ejemplo.test' where id = :u",
        "delete from usuario where id = :u",
        "delete from membresia where usuario_id = :u",
        "delete from refresh_token where membresia_id = :m",
        "update refresh_token set usado_en = now() where membresia_id = :m",
        f"delete from {TABLE} where usuario_id = :u",  # noqa: S608
        f"update {TABLE} set expira_en = now() where usuario_id = :u",  # noqa: S608
        f"update {TABLE} set token_hash = :h where usuario_id = :u",  # noqa: S608
    ],
)
def test_auth_owner_can_only_update_the_password_hash(db, statement):
    # Aun con la GUC de restablecer fijada para la cuenta, auth_owner solo actualiza
    # usuario.password_hash (sin DELETE ni otras columnas).
    c = cuenta(db)
    with migrator_tx(db) as conn:
        conn.exec_driver_sql(f"SET LOCAL ROLE {AUTH_OWNER}")
        set_gucs(conn, {"app.auth_reset_usuario": str(c.id)})
        nested = conn.begin_nested()
        with pytest.raises(DBAPIError) as excinfo:
            conn.execute(
                text(statement),
                {"u": c.id, "m": c.membresias[TENANT_A], "h": stored_hash(nueva_clave())},
            )
        nested.rollback()
    assert excinfo.value.orig.sqlstate == INSUFFICIENT_PRIVILEGE


def test_auth_owner_reset_cannot_change_membresia_activa(db):
    # auth_owner puede actualizar membresia.rol y activa (0033, para el cambio de rol y
    # activación del admin), pero la política exige la GUC de tenant y de usuario de esa
    # función: con solo la GUC de restablecer no alcanza ninguna fila.
    c = cuenta(db)
    with migrator_tx(db) as conn:
        conn.exec_driver_sql(f"SET LOCAL ROLE {AUTH_OWNER}")
        set_gucs(conn, {"app.auth_reset_usuario": str(c.id)})
        nested = conn.begin_nested()
        touched = conn.execute(
            text("update membresia set activa = false where usuario_id = :u"), {"u": c.id}
        )
        assert touched.rowcount == 0
        nested.rollback()
    with migrator_tx(db) as conn:
        activa = conn.scalar(
            text("select activa from membresia where usuario_id = :u"), {"u": c.id}
        )
    assert activa is True


def test_the_password_update_needs_a_link_consumed_in_the_same_transaction(db):
    # Con la GUC de restablecer fijada a mano pero sin un enlace consumido en esta
    # transacción, auth_owner no cambia la contraseña ni revoca sesiones.
    c = cuenta(db)
    session = refresh(db, c)
    _, key = solicitar(db, c.email)
    with migrator_tx(db) as conn:
        conn.exec_driver_sql(f"SET LOCAL ROLE {AUTH_OWNER}")
        set_gucs(conn, {"app.auth_reset_usuario": str(c.id), "app.auth_reset_clave": key})
        touched = conn.execute(
            text("update usuario set password_hash = 'x' where id = :u"), {"u": c.id}
        )
        assert touched.rowcount == 0
        touched = conn.execute(
            text("update refresh_token set revocado_en = now() where membresia_id = :m"),
            {"m": c.membresias[TENANT_A]},
        )
        assert touched.rowcount == 0
        # Control positivo: tras consumir el enlace en esta transacción, sí.
        consumed = conn.execute(
            text(f"update {TABLE} set usada_en = now() where token_hash = :h"),  # noqa: S608
            {"h": stored_hash(key)},
        )
        assert consumed.rowcount == 1
        touched = conn.execute(
            text("update usuario set password_hash = 'x' where id = :u"), {"u": c.id}
        )
        assert touched.rowcount == 1
        touched = conn.execute(
            text("update refresh_token set revocado_en = now() where membresia_id = :m"),
            {"m": c.membresias[TENANT_A]},
        )
        assert touched.rowcount == 1
    assert refresh_revocados(db, [session]) == {session: None}


def test_the_functions_never_read_the_password_hash(db):
    # Requisito 9: restablecer solo escribe password_hash (destino del SET); ninguna de
    # las dos lo lee ni lo devuelve.
    assert "password_hash" not in function_source(db, "solicitar_recuperacion")
    source = function_source(db, "restablecer_contrasena")
    # SET password_hash = p_password_hash y las comprobaciones de formato y longitud del
    # parámetro (I1, B1).
    assert source.count("password_hash") == 4
    assert "SET password_hash = p_password_hash" in source
    assert source.count("p_password_hash !~") == 1
    assert source.count("pg_catalog.length(p_password_hash) > 255") == 1
    assert re.search(r"\bu\.password_hash\b|SELECT[^;]*\bpassword_hash\b", source) is None


def test_the_functions_log_nothing(db):
    # Requisito 11: ni NOTICE/LOG/WARNING ni mensajes con datos; solo excepciones estáticas.
    for name in ("solicitar_recuperacion", "restablecer_contrasena"):
        source = function_source(db, name)
        assert re.search(r"RAISE\s+(NOTICE|LOG|WARNING|INFO|DEBUG)", source, re.I) is None
        for match in re.finditer(r"MESSAGE\s*=\s*([^;]+);", source):
            assert match.group(1).strip() in ("'enlace_invalido'", "'clave_invalida'")
        assert "DETAIL" not in source and "HINT" not in source


@pytest.mark.parametrize(
    "policy, table",
    [
        ("dueno_recuperacion_crear", TABLE),
        ("dueno_usuario_recuperar", "usuario"),
        ("dueno_membresia_recuperar", "membresia"),
    ],
)
def test_solicitar_runs_as_auth_owner_under_force_rls(db, policy, table):
    # El migrador es superusuario: si la función corriera como quien llama, quitar la
    # política no cambiaría nada.
    c = cuenta(db)
    with migrator_tx(db) as conn:
        assert conn.scalar(text(SOLICITAR), {"e": c.email, "c": nueva_clave()}) is True
        conn.exec_driver_sql(f"DROP POLICY {policy} ON {table}")
        nested = conn.begin_nested()
        try:
            result = conn.scalar(text(SOLICITAR), {"e": c.email, "c": nueva_clave()})
        except DBAPIError as exc:
            result = exc.orig.sqlstate
        nested.rollback()
    assert result in (False, INSUFFICIENT_PRIVILEGE)


@pytest.mark.parametrize(
    "policy, table",
    [
        ("dueno_recuperacion_consumir", TABLE),
        ("dueno_usuario_cambiar_clave", "usuario"),
        ("dueno_membresia_restablecer", "membresia"),
    ],
)
def test_restablecer_runs_as_auth_owner_under_force_rls(db, policy, table):
    c = cuenta(db)
    _, key = solicitar(db, c.email)
    with migrator_tx(db) as conn:
        conn.exec_driver_sql(f"DROP POLICY {policy} ON {table}")
        nested = conn.begin_nested()
        with pytest.raises(DBAPIError) as excinfo:
            conn.execute(text(RESTABLECER), {"c": key, "p": HASH_NUEVO})
        nested.rollback()
    assert excinfo.value.orig.diag.message_primary == ENLACE_INVALIDO
    assert password_hash(db, c) == HASH_VIEJO


# --- Concurrencia (auditoría de T2: H1 y pruebas pedidas antes de T4) -------------------


@contextmanager
def background_call(db: RecDb, sql: str, params: dict[str, object]) -> Iterator[dict]:
    """Ejecuta ``sql`` como la aplicación en un hilo con su propia conexión y ``COMMIT``.

    Al entrar espera a que la llamada quede bloqueada por un candado (``pg_stat_activity``);
    al salir espera a que termine. El resultado queda en ``outcome["result"]`` o
    ``outcome["error"]``.
    """
    name = f"rec_bg_{uuid.uuid4().hex[:8]}"
    engine = create_engine(db.app.url, poolclass=NullPool, connect_args={"application_name": name})
    outcome: dict[str, object] = {}

    def run() -> None:
        try:
            with engine.begin() as conn:
                outcome["result"] = conn.execute(text(sql), params).scalar_one()
        except Exception as exc:  # noqa: BLE001 - se informa en la aserción
            outcome["error"] = exc

    worker = threading.Thread(target=run)
    worker.start()
    try:
        _wait_until_blocked(db, name)
        yield outcome
    finally:
        worker.join(timeout=30)
        engine.dispose()
    assert not worker.is_alive(), "la llamada en segundo plano no terminó"


def test_restablecer_revokes_the_successor_of_a_rotation_in_flight(db):
    # H1: una rotación de refresh en vuelo (UPDATE usado_en del viejo + INSERT del sucesor,
    # sin confirmar) mientras se restablece. En READ COMMITTED el UPDATE de revocación
    # espera el candado del viejo, lo revoca al confirmarse la rotación y no ve el
    # sucesor (su instantánea es anterior): sin repetir la pasada, el sucesor queda vivo.
    c = cuenta(db)
    old = refresh(db, c)
    _, key = solicitar(db, c.email)
    with db.app.connect() as rotation:
        tx = rotation.begin()
        set_gucs(rotation, {"app.tenant_id": str(TENANT_A)})
        rotated = rotation.execute(
            text(
                "update refresh_token set usado_en = now() "
                "where id = :i and usado_en is null and revocado_en is null"
            ),
            {"i": old},
        )
        assert rotated.rowcount == 1
        successor = rotation.execute(
            text(
                "insert into refresh_token (tenant_id, membresia_id, familia_id, token_hash, "
                "expira_en) select tenant_id, membresia_id, familia_id, :h, "
                "now() + interval '7 days' from refresh_token where id = :i returning id"
            ),
            {"i": old, "h": hashlib.sha256(uuid.uuid4().bytes).digest()},
        ).scalar_one()
        with background_call(db, RESTABLECER, {"c": key, "p": HASH_NUEVO}) as outcome:
            tx.commit()
    assert "error" not in outcome, outcome.get("error")
    assert outcome["result"] == c.id
    assert password_hash(db, c) == HASH_NUEVO
    revocados = refresh_revocados(db, [old, successor])
    assert revocados[old] is not None
    assert revocados[successor] is not None, "el sucesor de la rotación en vuelo quedó vivo"


def test_restablecer_body_repeats_the_revocation_with_a_bounded_loop(db):
    # H1: mismo patrón que _revoke_family (spec 002): pasadas hasta NOT FOUND, tope 10.
    source = function_source(db, "restablecer_contrasena")
    loop = source.index("FOR v_pasada IN 1..10 LOOP")
    revoke = source.index("UPDATE public.refresh_token")
    assert loop < revoke < source.index("EXIT WHEN NOT FOUND") < source.index("END LOOP")


def test_two_simultaneous_resets_with_the_same_key_only_one_wins(db):
    c = cuenta(db)
    _, key = solicitar(db, c.email)
    other_hash = HASH_NUEVO + "otro"
    with db.app.connect() as first:
        tx = first.begin()
        assert first.execute(text(RESTABLECER), {"c": key, "p": HASH_NUEVO}).scalar_one() == c.id
        with background_call(db, RESTABLECER, {"c": key, "p": other_hash}) as outcome:
            tx.commit()
    assert "result" not in outcome, outcome
    assert_enlace_invalido(outcome["error"], key, other_hash)
    assert password_hash(db, c) == HASH_NUEVO
    (enlace,) = enlaces(db, c)
    assert enlace["usada_en"] is not None and enlace["invalidada_en"] is None


def test_solicitar_while_restablecer_is_in_flight_resurrects_nothing(db):
    # Restablecer primero (sin confirmar): la solicitud espera el candado del enlace;
    # al confirmar, la contraseña queda cambiada, el enlace usado sigue usado y queda
    # un único pendiente, el de la solicitud nueva.
    c = cuenta(db)
    _, key = solicitar(db, c.email)
    nueva = nueva_clave()
    with db.app.connect() as reset:
        tx = reset.begin()
        assert reset.execute(text(RESTABLECER), {"c": key, "p": HASH_NUEVO}).scalar_one() == c.id
        with background_call(db, SOLICITAR, {"e": c.email, "c": nueva}) as outcome:
            tx.commit()
    assert "error" not in outcome, outcome.get("error")
    assert outcome["result"] is True
    assert password_hash(db, c) == HASH_NUEVO
    rows = {bytes(r["token_hash"]): r for r in enlaces(db, c)}
    usado = rows[stored_hash(key)]
    assert usado["usada_en"] is not None and usado["invalidada_en"] is None
    assert [bytes(r["token_hash"]) for r in vivos(db, c)] == [stored_hash(nueva)]


def test_restablecer_while_solicitar_is_in_flight_gets_enlace_invalido(db):
    # Orden inverso: la solicitud invalida el enlace anterior (sin confirmar); el
    # restablecimiento con ese enlace espera y, al confirmar la solicitud, falla.
    c = cuenta(db)
    _, key = solicitar(db, c.email)
    nueva = nueva_clave()
    with db.app.connect() as request:
        tx = request.begin()
        assert request.execute(text(SOLICITAR), {"e": c.email, "c": nueva}).scalar_one() is True
        with background_call(db, RESTABLECER, {"c": key, "p": HASH_NUEVO}) as outcome:
            tx.commit()
    assert "result" not in outcome, outcome
    assert_enlace_invalido(outcome["error"], key)
    assert password_hash(db, c) == HASH_VIEJO
    rows = {bytes(r["token_hash"]): r for r in enlaces(db, c)}
    assert rows[stored_hash(key)]["usada_en"] is None
    assert rows[stored_hash(key)]["invalidada_en"] is not None
    assert [bytes(r["token_hash"]) for r in vivos(db, c)] == [stored_hash(nueva)]


# --- Políticas del dueño en directo (auditoría de T2) -----------------------------------


@pytest.mark.parametrize(
    "case",
    [
        "control",
        "expira_31_minutos",
        "ya_vencido",
        "usada_marcada",
        "invalidada_marcada",
        "dos_membresias_activas",
        "tenant_ajeno",
        "token_hash_distinto",
        "usuario_distinto",
    ],
)
def test_the_create_policy_rejects_every_out_of_contract_row(db, case):
    # dueno_recuperacion_crear como auth_owner con las GUC fijadas: solo el caso de
    # control pasa. Para probar la política (y no el GRANT por columna), las columnas de
    # marca se conceden en la transacción que se revierte.
    membresias = {
        "dos_membresias_activas": ((TENANT_A, True), (TENANT_B, True)),
        "tenant_ajeno": ((TENANT_A, False), (TENANT_B, True)),
    }.get(case, ((TENANT_A, True),))
    c = cuenta(db, membresias)
    otro = cuenta(db)
    key = nueva_clave()
    row = {
        "t": TENANT_A,
        "u": otro.id if case == "usuario_distinto" else c.id,
        "h": stored_hash(nueva_clave() if case == "token_hash_distinto" else key),
        "e": {"expira_31_minutos": "31 minutes", "ya_vencido": "-1 second"}.get(case, "30 minutes"),
        "usada": case == "usada_marcada",
        "invalidada": case == "invalidada_marcada",
    }
    with migrator_tx(db) as conn:
        conn.exec_driver_sql(f"GRANT INSERT (usada_en, invalidada_en) ON {TABLE} TO {AUTH_OWNER}")
        conn.exec_driver_sql(f"SET LOCAL ROLE {AUTH_OWNER}")
        set_gucs(conn, {"app.auth_rec_usuario": str(c.id), "app.auth_rec_clave": key})
        nested = conn.begin_nested()
        try:
            result: object = conn.execute(
                text(
                    f"insert into {TABLE} (tenant_id, usuario_id, token_hash, expira_en, "  # noqa: S608
                    "usada_en, invalidada_en) values (:t, :u, :h, now() + cast(:e as interval), "
                    "case when :usada then now() end, case when :invalidada then now() end)"
                ),
                row,
            ).rowcount
        except DBAPIError as exc:
            result = exc.orig.sqlstate
        nested.rollback()
    assert result == (1 if case == "control" else INSUFFICIENT_PRIVILEGE)


def test_the_revoke_policy_only_touches_the_user_with_a_consumed_link(db):
    # dueno_refresh_revocar como auth_owner: con el enlace de A consumido en esta
    # transacción, un UPDATE sin filtro revoca los refresh de A en sus dos tenants y
    # ninguno de B (ni en el tenant de A ni en otro).
    a = cuenta(db, ((TENANT_A, True), (TENANT_B, False)))
    b = cuenta(db, ((TENANT_A, True), (TENANT_B, False)))
    tokens_a = {refresh(db, a, TENANT_A), refresh(db, a, TENANT_B)}
    tokens_b = {refresh(db, b, TENANT_A), refresh(db, b, TENANT_B)}
    _, key_a = solicitar(db, a.email)
    _, key_b = solicitar(db, b.email)

    def revoke_as_owner(conn: Connection, usuario: Cuenta, key: str) -> set[uuid.UUID]:
        conn.exec_driver_sql(f"SET LOCAL ROLE {AUTH_OWNER}")
        set_gucs(conn, {"app.auth_reset_usuario": str(usuario.id), "app.auth_reset_clave": key})
        consumed = conn.execute(
            text(f"update {TABLE} set usada_en = now() where token_hash = :h"),  # noqa: S608
            {"h": stored_hash(key)},
        )
        assert consumed.rowcount == 1
        conn.execute(text("update refresh_token set revocado_en = now() where revocado_en is null"))
        conn.exec_driver_sql("RESET ROLE")
        rows = conn.execute(
            text("select id from refresh_token where id = any(:ids) and revocado_en is not null"),
            {"ids": list(tokens_a | tokens_b)},
        )
        return {r[0] for r in rows}

    with migrator_tx(db) as conn:
        assert revoke_as_owner(conn, a, key_a) == tokens_a
    # La GUC de usuario apuntando a B con el enlace de A consumido no revoca nada.
    with migrator_tx(db) as conn:
        assert revoke_as_owner(conn, b, key_a) == set()
    # Control: con el enlace de B, solo los de B.
    with migrator_tx(db) as conn:
        assert revoke_as_owner(conn, b, key_b) == tokens_b
    assert refresh_revocados(db, tokens_a | tokens_b) == dict.fromkeys(tokens_a | tokens_b)
