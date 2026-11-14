"""Acceso a datos con tenant (spec 001, R4–R4d).

La barrera de aislamiento es la base de datos: toda tabla de negocio tiene Row
Level Security habilitada y forzada, con una política que compara su
``tenant_id`` con ``current_setting('app.tenant_id')``, y la aplicación se
conecta con un rol sin ``SUPERUSER`` ni ``BYPASSRLS`` que no es dueño de las
tablas. Sin tenant fijado en la transacción, la base no devuelve filas ni
acepta escrituras.

Lo que hace Python es un complemento, no la barrera:

- ``tenant_session(tenant_id)`` valida el UUID antes de conectar (si no hay
  tenant válido falla con ``MissingTenantError``), abre una transacción y fija
  el tenant con ``set_config('app.tenant_id', :tenant_id, true)`` (equivale a
  ``SET LOCAL``: desaparece al terminar la transacción, así que no se filtra a
  otra petición por el pool).
- Filtro estándar de SQLAlchemy: ``with_loader_criteria`` sobre ``TenantScoped``
  en ``do_orm_execute``.
- En ``before_flush`` los objetos ``TenantScoped`` nuevos reciben el tenant de la
  sesión; si traen otro, o si se intenta mover una fila a otro tenant, se
  rechaza con ``TenantMismatchError``.
- Higiene: dentro de ``tenant_session`` se rechazan ``text()`` y
  ``Session.connection()`` con ``UnscopedStatementError``. No cierra todas las
  vías (``get_bind()``, el engine, API *bulk*, ``join()`` explícito): de esas se
  encarga RLS.

Cada conexión nueva del engine comprueba que su ``current_user`` no es
``SUPERUSER`` ni tiene ``BYPASSRLS`` (``InsecureDatabaseRoleError``; spec 002,
T4, R15). Las conexiones se reciclan cada ``POOL_RECYCLE_SECONDS`` (B6).

Logs de SQLAlchemy (M1 de T6-endurecimiento): con ``sqlalchemy.engine`` en DEBUG
el engine escribe filas completas (``Row (...)``), con hashes Argon2 y emails;
``hide_parameters`` solo oculta parámetros. ``init_db`` fija ``sqlalchemy.engine``
y ``sqlalchemy.pool`` en ``WARNING`` antes de ``create_engine``, crea el engine con
``echo=False`` y ``echo_pool=False`` literales (ninguna variable de entorno los
activa) y deja en el logger emisor un filtro que descarta los registros DEBUG
(``Row``/``Col``) aunque luego alguien suba el nivel o active ``echo``.

Las funciones ``acceso.*`` (antes de conocer el tenant) se llaman con funciones
propias de este módulo sin tenant y en su propia transacción, como
``buscar_login`` (spec 002, T6; plan.md §2), ``validar_invitacion`` y
``aceptar_invitacion`` (T9), nunca dentro de ``tenant_session``.

El engine se crea en ``init_db`` (llamado por ``create_app``), nunca al importar.
``create_engine`` no abre conexiones; la primera se abre al usar la sesión.
Ningún mensaje de este módulo incluye la URL de la base ni credenciales.
"""

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from flask import Flask, current_app, has_app_context
from sqlalchemy import Uuid, create_engine, event, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import (
    Mapped,
    ORMExecuteState,
    Session,
    SessionTransaction,
    mapped_column,
    sessionmaker,
    with_loader_criteria,
)
from sqlalchemy.sql.elements import TextClause

_EXTENSION_KEY = "assetcontrol.db"
_SET_TENANT = text("select set_config('app.tenant_id', :tenant_id, true)")
_PING = text("select 1")
# Sin tope, psycopg espera ~130 s si la base no responde y /health no llega a dar 503.
CONNECT_TIMEOUT_SECONDS = 5
# B6 de T4: una conexión del pool vive como mucho 30 min; la siguiente vuelve a pasar
# verify_connection_role, lo que acota la ventana tras un ALTER ROLE ... BYPASSRLS.
POOL_RECYCLE_SECONDS = 30 * 60
# M1 de T6-endurecimiento: niveles mínimos de los loggers de SQLAlchemy.
_QUIET_SQLALCHEMY_LOGGERS = ("sqlalchemy.engine", "sqlalchemy.pool")
# Logger que emite las filas (sin ``logging_name``, que no se usa).
_ENGINE_EMITTER_LOGGER = "sqlalchemy.engine.Engine"


class MissingTenantError(ValueError):
    """Se pidió acceso a datos sin un tenant válido."""


class TenantMismatchError(RuntimeError):
    """Se intentó escribir una fila de otro tenant."""


class UnscopedStatementError(RuntimeError):
    """Vía de acceso no permitida dentro de una sesión con tenant."""


class DatabaseNotInitializedError(RuntimeError):
    """No hay base de datos configurada en la aplicación actual."""


class InsecureDatabaseRoleError(RuntimeError):
    """El rol de ``DATABASE_URL`` se salta RLS (R15, A6; M2 de T6 de la spec 001)."""

    def __init__(self) -> None:
        super().__init__(
            "El rol de DATABASE_URL es SUPERUSER o tiene BYPASSRLS y se saltaría la RLS: "
            "la aplicación debe usar el rol de la aplicación (NOSUPERUSER NOBYPASSRLS)."
        )


# Sin fila para current_user (no debería pasar) cuenta como inseguro: falla cerrado.
_ROLE_SKIPS_RLS = (
    "select coalesce((select rolsuper or rolbypassrls from pg_catalog.pg_roles "
    "where rolname = current_user), true)"
)


def verify_connection_role(dbapi_connection: Any, *, rollback: bool = True) -> None:
    """Falla con ``InsecureDatabaseRoleError`` si el ``current_user`` se salta RLS.

    Se ejecuta en cada conexión nueva del engine (evento ``connect``): el
    arranque no abre conexiones (spec 001), así que la primera conexión hace de
    verificación de arranque y un ``ALTER ROLE`` posterior se detecta en la
    siguiente conexión. Deshace la transacción implícita que abre la consulta.
    """
    with dbapi_connection.cursor() as cursor:
        cursor.execute(_ROLE_SKIPS_RLS)
        row = cursor.fetchone()
    if rollback:
        dbapi_connection.rollback()
    if row is None or bool(row[0]):
        raise InsecureDatabaseRoleError()


def _verify_role_on_connect(dbapi_connection: Any, connection_record: Any) -> None:
    verify_connection_role(dbapi_connection)


class TenantScoped:
    """Mixin de toda tabla de negocio: aporta ``tenant_id`` y activa el filtro."""

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)


class _TenantSession(Session):
    """Sesión con tenant. Solo se obtiene a través de ``tenant_session``.

    El tenant se fija al construirla y no tiene setter. ``connection()`` se
    rechaza por higiene; el flush y ``execute`` del ORM usan
    ``_connection_for_bind`` y no pasan por él.
    """

    def __init__(self, *args: Any, tenant_id: uuid.UUID, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.__tenant = _normalize_tenant(tenant_id)

    @property
    def scoped_tenant(self) -> uuid.UUID:
        return self.__tenant

    def connection(self, *args: Any, **kwargs: Any):
        raise UnscopedStatementError(
            "session.connection() no está disponible en una sesión con tenant."
        )


class _DropRowRecords(logging.Filter):
    """Descarta los registros DEBUG del engine: son las filas (``Row``) y columnas (``Col``).

    Un filtro de logger solo se aplica a lo que ese logger emite, por eso va en
    ``sqlalchemy.engine.Engine``; también cubre ``echo=True``/``"debug"``, que
    salta el nivel pero no los filtros.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno > logging.DEBUG


def _quiet_sqlalchemy_logs() -> None:
    """Sube a ``WARNING`` los loggers de SQLAlchemy y deja el filtro de filas (idempotente)."""
    for name in _QUIET_SQLALCHEMY_LOGGERS:
        logger = logging.getLogger(name)
        if logger.level < logging.WARNING:
            logger.setLevel(logging.WARNING)
    emitter = logging.getLogger(_ENGINE_EMITTER_LOGGER)
    if not any(isinstance(f, _DropRowRecords) for f in emitter.filters):
        emitter.addFilter(_DropRowRecords())


@dataclass(frozen=True)
class _Database:
    engine: Engine
    session_factory: sessionmaker[_TenantSession]


def init_db(app: Flask) -> None:
    """Crea el engine y la fábrica de sesiones de ``app`` sin conectar."""
    # Antes de create_engine: el engine y el pool fijan su logger al construirse.
    _quiet_sqlalchemy_logs()
    engine = create_engine(
        app.config["DATABASE_URL"],
        echo=False,
        echo_pool=False,
        pool_pre_ping=True,
        pool_recycle=POOL_RECYCLE_SECONDS,
        hide_parameters=True,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS},
    )
    event.listen(engine, "connect", _verify_role_on_connect)
    factory = sessionmaker(bind=engine, class_=_TenantSession, expire_on_commit=False)
    app.extensions[_EXTENSION_KEY] = _Database(engine=engine, session_factory=factory)


def _normalize_tenant(tenant_id: object) -> uuid.UUID:
    """Devuelve siempre un ``uuid.UUID`` exacto, nunca una subclase.

    Una subclase podría redefinir ``__str__`` y alterar el valor que llega a
    ``set_config``; se reconstruye desde su entero.
    """
    if isinstance(tenant_id, uuid.UUID):
        return uuid.UUID(int=tenant_id.int)
    if tenant_id is None or (isinstance(tenant_id, str) and not tenant_id.strip()):
        raise MissingTenantError("El acceso a datos requiere un tenant_id.")
    try:
        return uuid.UUID(str(tenant_id).strip())
    except ValueError:
        raise MissingTenantError("El tenant_id no es un UUID válido.") from None


def _get_database() -> _Database:
    if not has_app_context():
        raise DatabaseNotInitializedError("No hay una aplicación activa para acceder a datos.")
    database = current_app.extensions.get(_EXTENSION_KEY)
    if database is None:
        raise DatabaseNotInitializedError("La base de datos no está inicializada.")
    return database


@contextmanager
def tenant_session(tenant_id: uuid.UUID | str) -> Iterator[Session]:
    """Abre una sesión con el tenant fijado en la transacción de PostgreSQL.

    Confirma al salir sin errores y revierte si el bloque lanza una excepción.
    Falla con ``MissingTenantError`` antes de conectar si no hay tenant válido.
    """
    tenant = _normalize_tenant(tenant_id)
    database = _get_database()
    with database.session_factory(tenant_id=tenant) as session:
        with session.begin():
            yield session


def ping_database() -> bool:
    """Comprueba que la base responde, sin tenant (lo usa ``/health``).

    Usa una conexión del engine con ``select 1``: no lee tablas de negocio, así
    que no necesita tenant ni pasa por ``tenant_session`` (que rechaza ``text()``).
    Devuelve ``False`` ante cualquier error de base sin propagar su mensaje.
    """
    database = _get_database()
    try:
        with database.engine.connect() as connection:
            connection.execute(_PING)
    except SQLAlchemyError:
        return False
    except InsecureDatabaseRoleError as exc:
        # Base alcanzable pero rol inseguro: /health no la da por buena y queda en el log.
        current_app.logger.error("%s", exc)
        return False
    return True


@dataclass(frozen=True)
class LoginRow:
    """Una fila de ``acceso.buscar_login`` (una por membresía activa, o una sin tenant)."""

    usuario_id: uuid.UUID
    password_hash: str
    activo: bool
    tenant_id: uuid.UUID | None
    rol: str | None


_BUSCAR_LOGIN = text(
    "select usuario_id, password_hash, activo, tenant_id, rol from acceso.buscar_login(:email)"
)


def buscar_login(email: str) -> list[LoginRow]:
    """Llama a ``acceso.buscar_login`` sin tenant, en su propia transacción (plan.md §2).

    Antes del login no hay tenant: nunca se llama dentro de ``tenant_session``
    (que además rechaza ``text()``). La función es de solo lectura; el ``email``
    debe venir normalizado. Sin cuenta devuelve ``[]``.
    """
    database = _get_database()
    with database.engine.begin() as connection:
        rows = connection.execute(_BUSCAR_LOGIN, {"email": email}).all()
    return [
        LoginRow(
            usuario_id=row.usuario_id,
            password_hash=row.password_hash,
            activo=row.activo,
            tenant_id=row.tenant_id,
            rol=row.rol,
        )
        for row in rows
    ]


_VALIDAR_INVITACION = text("select acceso.validar_invitacion(:clave)")
_ACEPTAR_INVITACION = text(
    "select usuario_id, tenant_id, rol "
    "from acceso.aceptar_invitacion(:clave, :nombre, :password_hash)"
)
# Excepción estática de aceptar_invitacion (Q16): email ya existente; revierte el consumo.
_INVITACION_INVALIDA = ("P0001", "invitacion_invalida")


@dataclass(frozen=True)
class AcceptedInvitation:
    """Lo que devuelve ``acceso.aceptar_invitacion``: la cuenta creada y su membresía."""

    usuario_id: uuid.UUID
    tenant_id: uuid.UUID
    rol: str


def validar_invitacion(clave: str) -> bool:
    """``acceso.validar_invitacion`` sin tenant, en su propia transacción (T9).

    Solo dice si la invitación de ``clave`` (``sha256(token)`` en hex) está vigente;
    no consume ni devuelve email, tenant o rol.
    """
    database = _get_database()
    with database.engine.begin() as connection:
        return connection.scalar(_VALIDAR_INVITACION, {"clave": clave}) is True


def _is_invitacion_invalida(exc: DBAPIError) -> bool:
    orig = exc.orig
    message = getattr(getattr(orig, "diag", None), "message_primary", None)
    return (getattr(orig, "sqlstate", None), message) == _INVITACION_INVALIDA


def aceptar_invitacion(clave: str, nombre: str, password_hash: str) -> AcceptedInvitation | None:
    """``acceso.aceptar_invitacion`` sin tenant, en su propia transacción (T9, R11).

    Una sola operación atómica de la base: consume la invitación y crea usuario y
    membresía con el email, el tenant y el rol de la invitación. ``None`` (nada
    creado, la invitación sigue como estaba) si la clave no existe, está usada,
    vencida o mal formada (cero filas), o si el email ya tiene cuenta (excepción
    estática, Q16). Cualquier otro error de base se propaga (``500``). Nunca se llama
    dentro de ``tenant_session``.
    """
    database = _get_database()
    params = {"clave": clave, "nombre": nombre, "password_hash": password_hash}
    rejected = False
    row = None
    try:
        with database.engine.begin() as connection:
            row = connection.execute(_ACEPTAR_INVITACION, params).one_or_none()
    except DBAPIError as exc:
        if not _is_invitacion_invalida(exc):
            raise
        rejected = True
    if rejected or row is None:
        return None
    return AcceptedInvitation(usuario_id=row.usuario_id, tenant_id=row.tenant_id, rol=row.rol)


# --- limite_tasa (T10; R13, Q10, A13; docs/03 cambio 6) ---------------------------------

# Ventana fija: el inicio es ``now()`` truncado a múltiplos de la duración (en segundos
# desde la época). El incremento es atómico: un solo ``INSERT ... ON CONFLICT DO UPDATE``.
_CONTAR_INTENTO = text(
    "insert into limite_tasa (ambito, clave_hash, ventana_inicio, intentos) "
    "values (:ambito, :clave, pg_catalog.to_timestamp(pg_catalog.floor("
    "extract(epoch from now()) / cast(:ventana as integer)) * cast(:ventana as integer)), 1) "
    "on conflict (ambito, clave_hash, ventana_inicio) "
    "do update set intentos = limite_tasa.intentos + 1 "
    "returning intentos, ventana_inicio"
)
_DEVOLVER_INTENTO = text(
    "update limite_tasa set intentos = intentos - 1 "
    "where ambito = :ambito and clave_hash = :clave and ventana_inicio = :ventana "
    "and intentos > 0"
)


@dataclass(frozen=True)
class CounterRow:
    """Un contador de ``limite_tasa`` tras sumarle un intento."""

    intentos: int
    ventana_inicio: Any


def contar_intentos(items: list[tuple[str, bytes]], window_seconds: int) -> list[CounterRow]:
    """Suma un intento a cada ``(ambito, clave_hash)`` en una transacción propia y confirmada.

    Sin tenant (como ``buscar_login``) y fuera de cualquier otra transacción: el
    ``COMMIT`` ocurre antes de volver, así que el fallo posterior de la petición no
    revierte el contador. Los contadores se actualizan en orden de ``(ambito, clave)``
    para que dos peticiones con los mismos contadores no se bloqueen entre sí; el
    resultado sale en el orden de ``items``. Cualquier error se propaga.
    """
    database = _get_database()
    order = sorted(range(len(items)), key=lambda i: items[i])
    results: dict[int, CounterRow] = {}
    with database.engine.begin() as connection:
        for index in order:
            ambito, clave = items[index]
            row = connection.execute(
                _CONTAR_INTENTO, {"ambito": ambito, "clave": clave, "ventana": window_seconds}
            ).one()
            results[index] = CounterRow(intentos=row.intentos, ventana_inicio=row.ventana_inicio)
    return [results[index] for index in range(len(items))]


def devolver_intentos(items: list[tuple[str, bytes, Any]]) -> None:
    """Resta el intento sumado por una petición que terminó bien (login y refresh, Q10).

    ``(ambito, clave_hash, ventana_inicio)`` de ``contar_intentos``; nunca baja de 0.
    Transacción propia; cualquier error se propaga.
    """
    database = _get_database()
    with database.engine.begin() as connection:
        for ambito, clave, ventana in sorted(items):
            connection.execute(
                _DEVOLVER_INTENTO, {"ambito": ambito, "clave": clave, "ventana": ventana}
            )


def _session_tenant(session: Session) -> uuid.UUID:
    if not isinstance(session, _TenantSession):
        raise MissingTenantError("El acceso a datos requiere un tenant_id.")
    return session.scoped_tenant


@event.listens_for(_TenantSession, "after_begin")
def _set_transaction_tenant(
    session: Session, transaction: SessionTransaction, connection: Connection
) -> None:
    """Fija el tenant en cada transacción que la sesión abre en la base.

    Parámetro enlazado y tercer argumento ``true`` (local a la transacción).
    """
    connection.execute(_SET_TENANT, {"tenant_id": str(_session_tenant(session))})


@event.listens_for(_TenantSession, "do_orm_execute")
def _apply_tenant_filter(state: ORMExecuteState) -> None:
    tenant = _session_tenant(state.session)

    if isinstance(state.statement, TextClause):
        raise UnscopedStatementError("No se permite SQL crudo en una sesión con tenant.")
    if state.is_select or state.is_update or state.is_delete:
        state.statement = state.statement.options(
            with_loader_criteria(
                TenantScoped,
                lambda cls: cls.tenant_id == tenant,
                include_aliases=True,
            )
        )


@event.listens_for(_TenantSession, "before_flush")
def _enforce_tenant_on_write(session: Session, flush_context, instances) -> None:
    tenant = _session_tenant(session)

    for obj in session.new:
        if not isinstance(obj, TenantScoped):
            continue
        if obj.tenant_id is None:
            obj.tenant_id = tenant
        elif _normalize_tenant(obj.tenant_id) != tenant:
            raise TenantMismatchError("No se puede crear una fila de otro tenant.")

    for obj in session.dirty:
        if isinstance(obj, TenantScoped) and _normalize_tenant(obj.tenant_id) != tenant:
            raise TenantMismatchError("No se puede mover una fila a otro tenant.")
