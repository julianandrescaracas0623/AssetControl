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
``aceptar_invitacion`` (T9), ``contar_y_solicitar_recuperacion`` y
``restablecer_contrasena`` (spec 014, T4), y ``plataforma_buscar_login`` (spec 017,
T2), nunca dentro de ``tenant_session``. Única excepción: ``cambiar_password_propio``
(spec 017, T4), que corre en la ``tenant_session`` de la petición y con su tenant para que
el cambio y la sesión nueva queden en una transacción.

Consola de plataforma (spec 017, T2; R37, A6; plan.md §2.1): ``plataforma_session``
es la sesión del desarrollador, paralela a ``tenant_session`` y sin mezclarse con ella.
Fija ``app.desarrollador_id`` (nunca ``app.tenant_id``) con ``set_config(..., true)`` y
solo admite los modelos de las tablas de plataforma (``PLATAFORMA_TABLES``): cualquier
otro modelo, de lectura o escritura, falla con ``PlataformaScopeError``. Como en
``tenant_session``, se rechazan ``text()`` y ``connection()``. La barrera sigue siendo
RLS: sin ``app.tenant_id`` ninguna tabla de negocio devuelve filas, y sin
``app.desarrollador_id`` ninguna tabla de plataforma. ``tenant_session`` nunca fija
``app.desarrollador_id``. Las funciones ``acceso.plataforma_*`` de Empresas (spec 017,
T3a) se llaman con ``plataforma_listar_tenants``, ``plataforma_crear_tenant`` y
``plataforma_cambiar_estado_tenant``, dentro de la ``plataforma_session`` y siempre con
su desarrollador.

El engine se crea en ``init_db`` (llamado por ``create_app``), nunca al importar.
``create_engine`` no abre conexiones; la primera se abre al usar la sesión.
Ningún mensaje de este módulo incluye la URL de la base ni credenciales.
"""

import logging
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from flask import Flask, current_app, has_app_context
from sqlalchemy import Uuid, create_engine, event, func, select, text
from sqlalchemy.engine import Connection, Engine, make_url
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
_SET_DESARROLLADOR = text("select set_config('app.desarrollador_id', :desarrollador_id, true)")
# Únicas tablas que admite ``plataforma_session`` (spec 017, plan.md §3).
PLATAFORMA_TABLES: frozenset[str] = frozenset(
    {"desarrollador", "plataforma_refresh_token", "plataforma_auditoria"}
)
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


class MissingDesarrolladorError(ValueError):
    """Se pidió una sesión de plataforma sin un ``desarrollador_id`` válido."""


class PlataformaScopeError(RuntimeError):
    """Una sesión de plataforma intentó usar un modelo fuera de las tablas de plataforma."""


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


class _PlataformaSession(Session):
    """Sesión del desarrollador. Solo se obtiene a través de ``plataforma_session``.

    El desarrollador se fija al construirla y no tiene setter. Nunca lleva tenant.
    """

    def __init__(self, *args: Any, desarrollador_id: uuid.UUID, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.__desarrollador = _normalize_desarrollador(desarrollador_id)

    @property
    def scoped_desarrollador(self) -> uuid.UUID:
        return self.__desarrollador

    def connection(self, *args: Any, **kwargs: Any):
        raise UnscopedStatementError(
            "session.connection() no está disponible en una sesión de plataforma."
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
    plataforma_factory: sessionmaker[_PlataformaSession]


TLS_ESTRICTOS = frozenset({"require", "verify-ca", "verify-full"})
SIN_TLS_OBLIGATORIO = frozenset({"development", "test"})


def _tls(database_url: str, environment: str) -> dict[str, object]:
    """Spec 010b (R3, R5): fuera de desarrollo y pruebas la base va siempre por TLS.

    Sin ``sslmode`` en la URL se exige ``require``; uno igual o más estricto se respeta;
    uno más débil (``disable``, ``allow``, ``prefer``) detiene el arranque. El mensaje no
    incluye la URL.
    """
    if environment in SIN_TLS_OBLIGATORIO:
        return {}
    modo = make_url(database_url).query.get("sslmode")
    if modo is None:
        return {"sslmode": "require"}
    if modo not in TLS_ESTRICTOS:
        raise RuntimeError(
            "La conexión a la base debe usar TLS fuera de desarrollo: sslmode debe ser "
            "require, verify-ca o verify-full."
        )
    return {}


def init_db(app: Flask) -> None:
    """Crea el engine y la fábrica de sesiones de ``app`` sin conectar."""
    # Antes de create_engine: el engine y el pool fijan su logger al construirse.
    _quiet_sqlalchemy_logs()
    connect_args: dict[str, object] = {"connect_timeout": CONNECT_TIMEOUT_SECONDS}
    connect_args.update(_tls(app.config["DATABASE_URL"], app.config["ENVIRONMENT"]))
    engine = create_engine(
        app.config["DATABASE_URL"],
        echo=False,
        echo_pool=False,
        pool_pre_ping=True,
        pool_recycle=POOL_RECYCLE_SECONDS,
        hide_parameters=True,
        connect_args=connect_args,
    )
    event.listen(engine, "connect", _verify_role_on_connect)
    factory = sessionmaker(bind=engine, class_=_TenantSession, expire_on_commit=False)
    plataforma = sessionmaker(bind=engine, class_=_PlataformaSession, expire_on_commit=False)
    app.extensions[_EXTENSION_KEY] = _Database(
        engine=engine, session_factory=factory, plataforma_factory=plataforma
    )


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


def _normalize_desarrollador(desarrollador_id: object) -> uuid.UUID:
    """Como ``_normalize_tenant``, para el ``desarrollador_id`` de una sesión de plataforma."""
    try:
        return _normalize_tenant(desarrollador_id)
    except MissingTenantError:
        raise MissingDesarrolladorError(
            "La sesión de plataforma requiere un desarrollador_id válido."
        ) from None


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


@contextmanager
def plataforma_session(desarrollador_id: uuid.UUID | str) -> Iterator[Session]:
    """Sesión del desarrollador con ``app.desarrollador_id`` fijado en la transacción.

    Confirma al salir sin errores y revierte si el bloque lanza. Falla con
    ``MissingDesarrolladorError`` antes de conectar si el id no es un UUID. No fija
    ``app.tenant_id`` (R37).
    """
    desarrollador = _normalize_desarrollador(desarrollador_id)
    database = _get_database()
    with database.plataforma_factory(desarrollador_id=desarrollador) as session:
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
    password_hash: str = field(repr=False)
    activo: bool
    tenant_id: uuid.UUID | None
    rol: str | None


_BUSCAR_LOGIN = text(
    "select usuario_id, password_hash, activo, tenant_id, rol from acceso.buscar_login(:email)"
)


def _login_rows(rows) -> list[LoginRow]:
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


def buscar_login(email: str) -> list[LoginRow]:
    """Llama a ``acceso.buscar_login`` sin tenant, en su propia transacción (plan.md §2).

    Antes del login no hay tenant: nunca se llama dentro de ``tenant_session``
    (que además rechaza ``text()``). La función es de solo lectura; el ``email``
    debe venir normalizado. Sin cuenta devuelve ``[]``.
    """
    database = _get_database()
    with database.engine.begin() as connection:
        rows = connection.execute(_BUSCAR_LOGIN, {"email": email}).all()
    return _login_rows(rows)


def releer_login(session: Session, email: str) -> list[LoginRow]:
    """``acceso.buscar_login`` en la conexión y la transacción de ``session`` (spec 017, T17).

    Segunda excepción explícita a la regla del módulo, junto a ``cambiar_password_propio``:
    ``issue_session`` relee el hash del login **en la misma** ``tenant_session`` donde
    inserta el refresh (sin otra conexión del pool), después del candado compartido. La
    función es de solo lectura y ``SECURITY DEFINER``: no depende del tenant de la sesión,
    así que quien llama debe comprobar que el ``usuario_id`` es el suyo. Nunca registra el
    hash ni el email.
    """
    _session_tenant(session)
    rows = Session.connection(session).execute(_BUSCAR_LOGIN, {"email": email}).all()
    return _login_rows(rows)


@dataclass(frozen=True)
class PlataformaLoginRow:
    """La fila de ``acceso.plataforma_buscar_login``. El hash nunca sale en ``repr``."""

    id: uuid.UUID
    password_hash: str = field(repr=False)
    activo: bool


_PLATAFORMA_BUSCAR_LOGIN = text(
    "select id, password_hash, activo from acceso.plataforma_buscar_login(:email)"
)


def plataforma_buscar_login(email: str) -> PlataformaLoginRow | None:
    """``acceso.plataforma_buscar_login`` sin tenant ni desarrollador, en su transacción.

    El login de plataforma (spec 017, T2) la llama antes de conocer al desarrollador;
    nunca dentro de una sesión. El ``email`` debe venir normalizado. El hash solo se usa
    para verificar la contraseña en el servidor: no se devuelve, registra ni audita.
    """
    database = _get_database()
    with database.engine.begin() as connection:
        row = connection.execute(_PLATAFORMA_BUSCAR_LOGIN, {"email": email}).one_or_none()
    if row is None:
        return None
    return PlataformaLoginRow(id=row.id, password_hash=row.password_hash, activo=row.activo)


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
    with database.engine.begin() as connection:
        return _sumar_intentos(connection, items, window_seconds)


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


def _sumar_intentos(
    connection: Connection, items: list[tuple[str, bytes]], window_seconds: int
) -> list[CounterRow]:
    """Suma un intento a cada contador en ``connection`` (orden estable, sin confirmar)."""
    order = sorted(range(len(items)), key=lambda i: items[i])
    results: dict[int, CounterRow] = {}
    for index in order:
        ambito, clave = items[index]
        row = connection.execute(
            _CONTAR_INTENTO, {"ambito": ambito, "clave": clave, "ventana": window_seconds}
        ).one()
        results[index] = CounterRow(intentos=row.intentos, ventana_inicio=row.ventana_inicio)
    return [results[index] for index in range(len(items))]


# --- Recuperación de contraseña (spec 014, T4; plan §4, §4.1) ---------------------------

_SOLICITAR_RECUPERACION = text("select acceso.solicitar_recuperacion(:email, :clave)")
_RESTABLECER_CONTRASENA = text("select acceso.restablecer_contrasena(:clave, :password_hash)")
# Excepción estática de restablecer_contrasena (sin eco): clave o hash mal formados, enlace
# inexistente, usado, invalidado o vencido, o cuenta ya no elegible. Revierte el consumo.
_ENLACE_INVALIDO = ("P0001", "enlace_invalido")
_RESTABLECER_ISOLATION = "READ COMMITTED"


class CounterUnavailableError(Exception):
    """No se pudo sumar el intento al límite de tasa (falla cerrado, ``503``).

    Solo lleva el tipo del error y su ``sqlstate``: nunca el mensaje, el SQL ni los
    parámetros.
    """

    def __init__(self, tipo: str, sqlstate: str) -> None:
        self.tipo = tipo
        self.sqlstate = sqlstate
        super().__init__("Límite de tasa no disponible.")


def error_summary(exc: BaseException) -> tuple[str, str]:
    """``(tipo, sqlstate)`` de un error de base, sin mensaje, SQL ni parámetros.

    Única versión para ``app.db`` y ``app.auth.limits`` (T8); ``sqlstate`` es
    ``"desconocido"`` si el error no trae uno.
    """
    orig = getattr(exc, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None) or getattr(exc, "sqlstate", None)
    return type(exc).__name__, sqlstate if isinstance(sqlstate, str) else "desconocido"


def contar_y_solicitar_recuperacion(
    items: list[tuple[str, bytes]],
    window_seconds: int,
    permitido: Callable[[list[CounterRow]], bool],
    email: str,
    clave: str,
) -> tuple[list[CounterRow], bool | None]:
    """Contadores y ``acceso.solicitar_recuperacion`` en **una** transacción sin tenant.

    M1 de la auditoría de T2: el ``upsert`` de ``limite_tasa`` es una escritura que ocurre
    en todas las ramas (exista o no la cuenta), así que el ``COMMIT`` hace el mismo
    trabajo aunque la función no inserte nada.

    1. Suma un intento a cada ``(ambito, clave_hash)``; si falla, ``CounterUnavailableError``
       sin llamar a la función.
    2. Si ``permitido(contadores)`` es falso, confirma solo los contadores y devuelve
       ``(contadores, None)``.
    3. Si no, llama a la función dentro de un *savepoint*: si falla, se revierte solo la
       función, los contadores se confirman igual (el intento sobrevive al fallo de la
       petición) y el error se propaga (``500``).
    4. ``COMMIT`` y ``(contadores, creado)``; ``creado`` es ``True`` solo si la función
       insertó el enlace. Si el ``COMMIT`` falla, el error se propaga: quien llama no
       llega a programar el correo.

    ``email`` ya normalizado (o vacío) y ``clave = sha256(token)`` en hex. Nunca se llama
    dentro de ``tenant_session``.
    """
    database = _get_database()
    fallo_conteo: tuple[str, str] | None = None
    with database.engine.connect() as connection:
        transaction = connection.begin()
        try:
            try:
                rows = _sumar_intentos(connection, items, window_seconds)
            except Exception as exc:
                fallo_conteo = error_summary(exc)
                raise
            if not permitido(rows):
                transaction.commit()
                return rows, None
            savepoint = connection.begin_nested()
            try:
                creado = connection.scalar(
                    _SOLICITAR_RECUPERACION, {"email": email, "clave": clave}
                )
            except BaseException:
                savepoint.rollback()
                transaction.commit()
                raise
            savepoint.commit()
            transaction.commit()
        except BaseException:
            if transaction.is_active:
                transaction.rollback()
            if fallo_conteo is None:
                raise
    if fallo_conteo is not None:
        # Fuera del except: sin causa ni contexto que arrastren SQL o parámetros.
        raise CounterUnavailableError(*fallo_conteo)
    return rows, creado is True


def _is_enlace_invalido(exc: DBAPIError) -> bool:
    orig = exc.orig
    message = getattr(getattr(orig, "diag", None), "message_primary", None)
    return (getattr(orig, "sqlstate", None), message) == _ENLACE_INVALIDO


def restablecer_contrasena(clave: str, password_hash: str) -> uuid.UUID | None:
    """``acceso.restablecer_contrasena`` como primera sentencia de una transacción nueva.

    B2 de la auditoría de T2: conexión propia, ``READ COMMITTED`` explícito (con
    ``REPEATABLE READ`` el segundo canje simultáneo daría ``40001``), sin
    ``tenant_session`` y con el hash Argon2 ya calculado: la transacción solo dura la
    función. Devuelve el ``usuario_id`` o ``None`` si la función lanza su excepción
    estática ``enlace_invalido`` o devuelve ``NULL`` (nunca se trata como éxito).
    Cualquier otro error de base se propaga sin leer su mensaje (``500``).
    """
    database = _get_database()
    params = {"clave": clave, "password_hash": password_hash}
    rechazado = False
    usuario = None
    try:
        with database.engine.connect() as connection:
            connection.execution_options(isolation_level=_RESTABLECER_ISOLATION)
            with connection.begin():
                usuario = connection.scalar(_RESTABLECER_CONTRASENA, params)
    except DBAPIError as exc:
        if not _is_enlace_invalido(exc):
            raise
        rechazado = True
    if rechazado or not isinstance(usuario, uuid.UUID):
        return None
    return usuario


def pedir_enlace_recuperacion(email: str, clave: str) -> bool:
    """``acceso.solicitar_recuperacion`` en una transacción propia y corta, **sin** los
    contadores de la 014 (spec 017, C1d, R61; plan §12.1).

    Solo para el aviso de una contraseña temporal recién definida desde la consola: esa
    acción ya está autenticada, auditada y limitada por ``plat_accion``. ``email`` ya
    normalizado y ``clave = sha256(token)`` en hex. La elegibilidad es la de 0016 (usuario
    activo con exactamente una membresía activa). Devuelve ``True`` solo si la función
    creó el enlace. Nunca se llama dentro de ``tenant_session`` ni de la
    ``plataforma_session``; los errores de base se propagan sin leer su mensaje.
    """
    database = _get_database()
    with database.engine.connect() as connection, connection.begin():
        creado = connection.scalar(_SOLICITAR_RECUPERACION, {"email": email, "clave": clave})
    return creado is True


# --- Cambio de contraseña propio (spec 017, T4; R27; plan.md §2.6) ----------------------

_CAMBIAR_PASSWORD_PROPIO = text(
    "select acceso.cambiar_password_propio(:usuario, :tenant, :hash_actual, :hash_nuevo)"
)
# Excepción estática de cambiar_password_propio (sin eco): la cuenta ya no es elegible o la
# contraseña cambió desde que Flask la verificó. No cambia nada.
_CAMBIO_INVALIDO = ("P0001", "cambio_invalido")


def _is_cambio_invalido(exc: DBAPIError) -> bool:
    orig = exc.orig
    message = getattr(getattr(orig, "diag", None), "message_primary", None)
    return (getattr(orig, "sqlstate", None), message) == _CAMBIO_INVALIDO


def cambiar_password_propio(
    session: Session, usuario_id: uuid.UUID, hash_actual: str, hash_nuevo: str
) -> bool:
    """``acceso.cambiar_password_propio`` dentro de la ``tenant_session`` de la petición.

    Función ``acceso.*`` que corre dentro de ``tenant_session`` (excepción explícita a la
    regla del módulo; la otra es ``releer_login``, spec 017 T17): así el cambio de hash, la
    marca en ``false``, la revocación de los refresh y la familia nueva que inserta quien
    llama quedan en **una** transacción
    (R27). El tenant es siempre el de la sesión, nunca uno que elija quien llama. La
    función va en un ``SAVEPOINT``: si rechaza (``cambio_invalido``) se revierte solo ese
    punto, la sesión sigue sana y se devuelve ``False``. Cualquier otro error se propaga
    sin leer su mensaje. Nunca recibe ni devuelve la contraseña en claro.
    """
    params = {
        "usuario": str(_normalize_tenant(usuario_id)),
        "tenant": str(_session_tenant(session)),
        "hash_actual": hash_actual,
        "hash_nuevo": hash_nuevo,
    }
    rechazado = False
    resultado = None
    try:
        with session.begin_nested():
            resultado = Session.connection(session).scalar(_CAMBIAR_PASSWORD_PROPIO, params)
    except DBAPIError as exc:
        if not _is_cambio_invalido(exc):
            raise
        rechazado = True
    return not rechazado and resultado is True


# --- Cambio de rol y de activación desde la consola de la empresa (0033) -----------------

_CAMBIAR_MEMBRESIA = text(
    "select rol_resultado, activa_resultado, cambiado "
    "from acceso.cambiar_membresia(:tenant, :actor, :usuario, :rol, :activa)"
)
# (SQLSTATE, mensaje) de acceso.cambiar_membresia -> código estable de la aplicación.
_MEMBRESIA_ERRORES = {
    ("42501", "no_autorizado"): "no_autorizado",
    ("P0001", "cambio_propio_no_permitido"): "cambio_propio_no_permitido",
    ("P0001", "ultimo_admin"): "ultimo_admin",
    ("P0002", "usuario_no_encontrado"): "usuario_no_encontrado",
    ("55P03", "membresia_ocupada"): "membresia_ocupada",
}


class MembresiaRechazada(Exception):
    """Rechazo esperado de ``acceso.cambiar_membresia``: solo lleva su código.

    Sin mensaje, SQL ni parámetros de la base. ``tenant_session`` revierte la transacción
    al salir con esta excepción: no queda nada a medias.
    """

    def __init__(self, codigo: str) -> None:
        self.codigo = codigo
        super().__init__(codigo)


@dataclass(frozen=True)
class ResultadoCambioMembresia:
    """Lo que devuelve ``acceso.cambiar_membresia``: estado resultante y si hubo escritura."""

    rol: str
    activa: bool
    cambiado: bool


def cambiar_membresia(
    session: Session,
    usuario_id: uuid.UUID,
    *,
    actor_id: uuid.UUID,
    rol: str,
    activa: bool,
) -> ResultadoCambioMembresia:
    """``acceso.cambiar_membresia`` dentro de la ``tenant_session`` de la petición.

    El tenant es siempre el de la sesión, nunca uno que elija quien llama. Quien cambia
    (``actor_id``) lo comprueba la función, que es la que decide. Un rechazo se levanta como
    ``MembresiaRechazada``; cualquier otro error de la base se propaga sin leer su mensaje.
    """
    params = {
        "tenant": str(_session_tenant(session)),
        "actor": str(actor_id),
        "usuario": str(usuario_id),
        "rol": rol,
        "activa": activa,
    }
    connection = Session.connection(session)
    codigo = None
    try:
        fila = connection.execute(_CAMBIAR_MEMBRESIA, params).one()
    except DBAPIError as exc:
        orig = exc.orig
        message = getattr(getattr(orig, "diag", None), "message_primary", None)
        codigo = _MEMBRESIA_ERRORES.get((getattr(orig, "sqlstate", None), message))
        if codigo is None:
            raise
    # Fuera del except: sin causa ni contexto que arrastren SQL o parámetros.
    if codigo is not None:
        raise MembresiaRechazada(codigo)
    return ResultadoCambioMembresia(
        rol=fila.rol_resultado, activa=fila.activa_resultado, cambiado=fila.cambiado
    )


# Candado no obtenido dentro del lock_timeout o interbloqueo al esperarlo.
_CANDADO_NO_OBTENIDO = frozenset({"55P03", "40P01"})


def candado_compartido_acotado(session: Session, clave: str, lock_timeout: str) -> bool:
    """``pg_advisory_xact_lock_shared(hashtextextended(clave, 0))`` esperando a lo sumo
    ``lock_timeout``; ``False`` si no se obtuvo (``55P03``/``40P01``).

    Spec 017, T5. El ``lock_timeout`` se fija con ``set_config(..., true)`` (local a la
    transacción) y, tomado el candado, se restaura el valor previo en la misma transacción:
    no acota las consultas siguientes. Si no se obtiene, la transacción queda abortada y
    quien llama debe revertirla (el ``ROLLBACK`` descarta también el valor local). No lee
    ni propaga el mensaje de la base.
    """
    previo = session.scalar(select(func.current_setting("lock_timeout")))
    session.execute(select(func.set_config("lock_timeout", lock_timeout, True)))
    try:
        session.execute(select(func.pg_advisory_xact_lock_shared(func.hashtextextended(clave, 0))))
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) not in _CANDADO_NO_OBTENIDO:
            raise
        return False
    session.execute(select(func.set_config("lock_timeout", previo, True)))
    return True


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


# --- Sesión de plataforma (spec 017, T2) ------------------------------------------------------


def session_desarrollador(session: Session) -> uuid.UUID:
    if not isinstance(session, _PlataformaSession):
        raise MissingDesarrolladorError("La sesión de plataforma requiere un desarrollador_id.")
    return session.scoped_desarrollador


def _is_platform_class(cls: type) -> bool:
    table = getattr(cls, "__table__", None)
    return getattr(table, "name", None) in PLATAFORMA_TABLES


@event.listens_for(_PlataformaSession, "after_begin")
def _set_transaction_desarrollador(
    session: Session, transaction: SessionTransaction, connection: Connection
) -> None:
    """Fija el desarrollador (y solo él) en cada transacción que la sesión abre."""
    connection.execute(
        _SET_DESARROLLADOR, {"desarrollador_id": str(session_desarrollador(session))}
    )


@event.listens_for(_PlataformaSession, "do_orm_execute")
def _restrict_platform_statement(state: ORMExecuteState) -> None:
    """Defensa en profundidad: la barrera real es RLS en la base.

    Sin ``app.tenant_id`` ninguna tabla de negocio devuelve ni acepta filas, aunque este
    filtro del ORM se saltara; aquí solo se corta antes el uso de un modelo indebido.
    """
    if isinstance(state.statement, TextClause):
        raise UnscopedStatementError("No se permite SQL crudo en una sesión de plataforma.")
    for mapper in state.all_mappers:
        if not _is_platform_class(mapper.class_):
            raise PlataformaScopeError(
                "Una sesión de plataforma solo admite las tablas de plataforma."
            )


@event.listens_for(_PlataformaSession, "before_flush")
def _restrict_platform_write(session: Session, flush_context, instances) -> None:
    for obj in (*session.new, *session.dirty, *session.deleted):
        if not _is_platform_class(type(obj)):
            raise PlataformaScopeError(
                "Una sesión de plataforma solo escribe en las tablas de plataforma."
            )


# --- Funciones de Empresas de la consola (spec 017, T3a; plan.md §2.3) ------------------------
#
# Se llaman dentro de ``plataforma_session`` (misma transacción que la auditoría de T3b) y
# siempre con el desarrollador de la sesión: nunca con uno que elija quien llama. El
# ``text()`` va por la conexión de la sesión, no por ``session.execute`` (que lo rechaza).

_PLATAFORMA_LISTAR_TENANTS = text(
    "select id, nombre, activo, creado_en, tiene_logo, n_membresias_activas, n_admins_activos "
    "from acceso.plataforma_listar_tenants(:desarrollador)"
)
_PLATAFORMA_CREAR_TENANT = text(
    "select tenant_id, usuario_id from acceso.plataforma_crear_tenant("
    ":desarrollador, :tenant, :nombre, :direccion, :nit, :telefono, :correo, "
    ":admin_email, :admin_nombre, :password_hash)"
)
_PLATAFORMA_CAMBIAR_ESTADO_TENANT = text(
    "select acceso.plataforma_cambiar_estado_tenant(:desarrollador, :tenant, :activo)"
)
# Excepciones estáticas de las funciones (sqlstate, mensaje) -> código de error.
_PLATAFORMA_ERRORES = {
    ("42501", "desarrollador_no_autorizado"): "desarrollador_no_autorizado",
    ("22023", "hash_invalido"): "hash_invalido",
    ("23505", "empresa_existente"): "empresa_existente",
    ("23505", "email_en_uso"): "email_en_uso",
    ("P0002", "empresa_no_encontrada"): "empresa_no_encontrada",
    # Spec 017, T5 (0027): Usuarios.
    ("P0002", "usuario_no_encontrado"): "usuario_no_encontrado",
    ("P0001", "empresa_inactiva"): "empresa_inactiva",
    ("P0001", "ultimo_admin"): "ultimo_admin",
    # Candado del tenant o de una fila no obtenido dentro del lock_timeout de la función.
    ("55P03", "membresia_ocupada"): "membresia_ocupada",
    # Spec 017, T7 (0029): logo en el alta.
    ("22023", "clave_invalida"): "clave_invalida",
    ("P0001", "empresa_sin_datos"): "empresa_sin_datos",
    ("P0001", "empresa_sin_admin"): "empresa_sin_admin",
    ("23505", "logo_id_en_uso"): "logo_id_en_uso",
    ("55P03", "empresa_ocupada"): "empresa_ocupada",
}


class PlataformaFuncionError(Exception):
    """Rechazo esperado de una función ``acceso.plataforma_*``: solo lleva su código.

    Sin mensaje de la base, SQL ni parámetros. La transacción de la sesión queda abortada:
    ``plataforma_session`` la revierte al salir (no queda nada creado).
    """

    def __init__(self, codigo: str) -> None:
        self.codigo = codigo
        super().__init__(codigo)


@dataclass(frozen=True)
class TenantResumen:
    """Una fila de ``acceso.plataforma_listar_tenants``: identidad y conteos (R21)."""

    id: uuid.UUID
    nombre: str
    activo: bool
    creado_en: Any
    tiene_logo: bool
    n_membresias_activas: int
    n_admins_activos: int


@dataclass(frozen=True)
class FichaEmpresa:
    """Datos de la ficha ``empresa`` ya validados en Flask (reglas de la 013)."""

    nombre: str
    direccion: str
    nit: str | None = None
    telefono: str | None = None
    correo: str | None = None


@dataclass(frozen=True)
class TenantCreado:
    tenant_id: uuid.UUID
    usuario_id: uuid.UUID


def _plataforma_connection(session: Session) -> tuple[Connection, str]:
    """Conexión de la transacción de ``session`` y su desarrollador (en texto)."""
    desarrollador = session_desarrollador(session)
    return Session.connection(session), str(desarrollador)


def _plataforma_codigo(exc: DBAPIError) -> str | None:
    orig = exc.orig
    message = getattr(getattr(orig, "diag", None), "message_primary", None)
    return _PLATAFORMA_ERRORES.get((getattr(orig, "sqlstate", None), message))


def _plataforma_call(session: Session, statement: TextClause, params: dict[str, Any]):
    connection, desarrollador = _plataforma_connection(session)
    codigo = None
    try:
        return connection.execute(statement, {"desarrollador": desarrollador, **params})
    except DBAPIError as exc:
        codigo = _plataforma_codigo(exc)
        if codigo is None:
            raise
    # Fuera del except: sin causa ni contexto que arrastren SQL o parámetros.
    raise PlataformaFuncionError(codigo)


def plataforma_listar_tenants(session: Session) -> list[TenantResumen]:
    """``acceso.plataforma_listar_tenants`` con el desarrollador de ``session``."""
    rows = _plataforma_call(session, _PLATAFORMA_LISTAR_TENANTS, {}).all()
    return [
        TenantResumen(
            id=row.id,
            nombre=row.nombre,
            activo=row.activo,
            creado_en=row.creado_en,
            tiene_logo=row.tiene_logo,
            n_membresias_activas=row.n_membresias_activas,
            n_admins_activos=row.n_admins_activos,
        )
        for row in rows
    ]


def plataforma_crear_tenant(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    ficha: FichaEmpresa,
    admin_email: str,
    admin_nombre: str,
    password_hash: str,
) -> TenantCreado:
    """``acceso.plataforma_crear_tenant`` en la transacción de ``session`` (R16).

    ``admin_email`` normalizado y ``password_hash`` ya calculado con Argon2id. Los
    opcionales de la ficha viajan como ``''`` (la función es ``STRICT``) y se guardan
    como ``NULL``. Rechazos esperados: ``PlataformaFuncionError`` con
    ``empresa_existente``, ``email_en_uso``, ``hash_invalido`` o
    ``desarrollador_no_autorizado``.
    """
    params = {
        "tenant": str(_normalize_tenant(tenant_id)),
        "nombre": ficha.nombre,
        "direccion": ficha.direccion,
        "nit": ficha.nit or "",
        "telefono": ficha.telefono or "",
        "correo": ficha.correo or "",
        "admin_email": admin_email,
        "admin_nombre": admin_nombre,
        "password_hash": password_hash,
    }
    row = _plataforma_call(session, _PLATAFORMA_CREAR_TENANT, params).one()
    return TenantCreado(tenant_id=row.tenant_id, usuario_id=row.usuario_id)


def plataforma_cambiar_estado_tenant(session: Session, tenant_id: uuid.UUID, activo: bool) -> bool:
    """``acceso.plataforma_cambiar_estado_tenant`` (R22); idempotente.

    Devuelve el estado resultante. ``PlataformaFuncionError`` con
    ``empresa_no_encontrada`` o ``desarrollador_no_autorizado``.
    """
    params = {"tenant": str(_normalize_tenant(tenant_id)), "activo": bool(activo)}
    return _plataforma_call(session, _PLATAFORMA_CAMBIAR_ESTADO_TENANT, params).scalar_one()


# --- Funciones de Usuarios de la consola (spec 017, T5; 0027) ---------------------------------

_PLATAFORMA_LISTAR_USUARIOS = text(
    "select usuario_id, nombre, email, rol, activa, debe_cambiar_password "
    "from acceso.plataforma_listar_usuarios(:desarrollador, :tenant)"
)
_PLATAFORMA_CAMBIAR_ESTADO_MEMBRESIA = text(
    "select estado, cambiado from acceso.plataforma_cambiar_estado_membresia("
    ":desarrollador, :tenant, :usuario, :activa)"
)


@dataclass(frozen=True)
class UsuarioResumen:
    """Una fila de ``acceso.plataforma_listar_usuarios`` (R29). ``repr`` sin nombre ni correo."""

    usuario_id: uuid.UUID
    nombre: str = field(repr=False)
    email: str = field(repr=False)
    rol: str
    activa: bool
    debe_cambiar_password: bool


def plataforma_listar_usuarios(session: Session, tenant_id: uuid.UUID) -> list[UsuarioResumen]:
    """``acceso.plataforma_listar_usuarios`` con el desarrollador de ``session`` (R29).

    ``PlataformaFuncionError`` con ``empresa_no_encontrada`` o
    ``desarrollador_no_autorizado``.
    """
    params = {"tenant": str(_normalize_tenant(tenant_id))}
    rows = _plataforma_call(session, _PLATAFORMA_LISTAR_USUARIOS, params).all()
    return [
        UsuarioResumen(
            usuario_id=row.usuario_id,
            nombre=row.nombre,
            email=row.email,
            rol=row.rol,
            activa=row.activa,
            debe_cambiar_password=row.debe_cambiar_password,
        )
        for row in rows
    ]


@dataclass(frozen=True)
class CambioMembresia:
    """Resultado de ``acceso.plataforma_cambiar_estado_membresia``: el estado resultante
    y si hubo un cambio real (``False`` al repetir el estado actual)."""

    activa: bool
    cambiado: bool


def plataforma_cambiar_estado_membresia(
    session: Session, tenant_id: uuid.UUID, usuario_id: uuid.UUID, activa: bool
) -> CambioMembresia:
    """``acceso.plataforma_cambiar_estado_membresia`` (R30, R31); idempotente.

    ``PlataformaFuncionError`` con ``empresa_no_encontrada``, ``usuario_no_encontrado``,
    ``empresa_inactiva``, ``ultimo_admin``, ``membresia_ocupada`` (candado no obtenido a
    tiempo) o ``desarrollador_no_autorizado``.
    """
    if not isinstance(usuario_id, uuid.UUID):
        raise TypeError("usuario_id debe ser un UUID.")
    params = {
        "tenant": str(_normalize_tenant(tenant_id)),
        "usuario": str(usuario_id),
        "activa": bool(activa),
    }
    row = _plataforma_call(session, _PLATAFORMA_CAMBIAR_ESTADO_MEMBRESIA, params).one()
    if type(row.estado) is not bool or type(row.cambiado) is not bool:
        raise RuntimeError("Resultado inesperado de plataforma_cambiar_estado_membresia.")
    return CambioMembresia(activa=row.estado, cambiado=row.cambiado)


# --- Editar nombre y rol de un usuario (spec 017, C1/T13; 0031) -------------------------------

_PLATAFORMA_CAMBIAR_USUARIO = text(
    "select nombre, rol, cambiado, rol_cambiado from acceso.plataforma_cambiar_usuario("
    ":desarrollador, :tenant, :usuario, :nombre, :rol)"
)


@dataclass(frozen=True)
class UsuarioEditado:
    """Resultado de ``acceso.plataforma_cambiar_usuario``: el nombre y el rol resultantes,
    si hubo algún cambio real y si cambió el rol (entonces se revocaron las familias de
    refresh de esa membresía). ``repr`` sin el nombre."""

    nombre: str = field(repr=False)
    rol: str
    cambiado: bool
    rol_cambiado: bool


def plataforma_cambiar_usuario(
    session: Session, tenant_id: uuid.UUID, usuario_id: uuid.UUID, nombre: str, rol: str
) -> UsuarioEditado:
    """``acceso.plataforma_cambiar_usuario`` (R47–R51); idempotente.

    ``nombre`` ya normalizado y ``rol`` ya validado en Flask. ``PlataformaFuncionError`` con
    ``empresa_no_encontrada``, ``usuario_no_encontrado``, ``empresa_inactiva``,
    ``ultimo_admin``, ``membresia_ocupada`` (candado no obtenido a tiempo) o
    ``desarrollador_no_autorizado``.
    """
    if not isinstance(usuario_id, uuid.UUID):
        raise TypeError("usuario_id debe ser un UUID.")
    if not isinstance(nombre, str) or not isinstance(rol, str):
        raise TypeError("nombre y rol deben ser texto.")
    params = {
        "tenant": str(_normalize_tenant(tenant_id)),
        "usuario": str(usuario_id),
        "nombre": nombre,
        "rol": rol,
    }
    row = _plataforma_call(session, _PLATAFORMA_CAMBIAR_USUARIO, params).one()
    if (
        type(row.cambiado) is not bool
        or type(row.rol_cambiado) is not bool
        or (row.rol_cambiado and not row.cambiado)
        or row.nombre != nombre
        or row.rol != rol
    ):
        raise RuntimeError("Resultado inesperado de plataforma_cambiar_usuario.")
    return UsuarioEditado(
        nombre=row.nombre, rol=row.rol, cambiado=row.cambiado, rol_cambiado=row.rol_cambiado
    )


# --- Contraseña temporal de un usuario (spec 017, C1b/T16; 0032) ------------------------------

_PLATAFORMA_RESTABLECER_PASSWORD_USUARIO = text(
    "select acceso.plataforma_restablecer_password_usuario("
    ":desarrollador, :tenant, :usuario, :password_hash)"
)


def plataforma_restablecer_password_usuario(
    session: Session, tenant_id: uuid.UUID, usuario_id: uuid.UUID, password_hash: str
) -> None:
    """``acceso.plataforma_restablecer_password_usuario`` (R53–R56); no idempotente.

    ``password_hash`` ya calculado con Argon2id en Flask (nunca viaja la contraseña). La
    función no devuelve nada (``void``): ni hash ni contraseña. ``PlataformaFuncionError``
    con ``empresa_no_encontrada``, ``usuario_no_encontrado``, ``empresa_inactiva``,
    ``hash_invalido``, ``membresia_ocupada`` (candado no obtenido a tiempo) o
    ``desarrollador_no_autorizado``.
    """
    if not isinstance(usuario_id, uuid.UUID):
        raise TypeError("usuario_id debe ser un UUID.")
    if not isinstance(password_hash, str):
        raise TypeError("password_hash debe ser texto.")
    params = {
        "tenant": str(_normalize_tenant(tenant_id)),
        "usuario": str(usuario_id),
        "password_hash": password_hash,
    }
    _plataforma_call(session, _PLATAFORMA_RESTABLECER_PASSWORD_USUARIO, params).one()


# --- Función de Actividad de la consola (spec 017, T6; 0028) ----------------------------------
#
# La función es ``STRICT``: «sin filtro» viaja con centinelas, nunca ``NULL`` (ver 0028). Los
# instantes viajan como texto ISO 8601 con zona (o ``±infinity``) y la base los convierte.

_PLATAFORMA_LISTAR_AUDITORIA = text(
    "select id, creado_en, accion, resultado, desarrollador_nombre, tenant_id, tenant_nombre, "
    "objeto_id from acceso.plataforma_listar_auditoria(:desarrollador, cast(:tenant as uuid), "
    ":accion, cast(:desde as timestamptz), cast(:hasta as timestamptz), :limite, "
    "cast(:cursor_fecha as timestamptz), cast(:cursor_id as uuid))"
)
_SIN_TENANT = "00000000-0000-0000-0000-000000000000"
_PRIMER_CURSOR_ID = "ffffffff-ffff-ffff-ffff-ffffffffffff"


@dataclass(frozen=True)
class FiltroAuditoria:
    """Filtros ya validados en Flask. ``hasta`` es exclusivo; ``cursor`` = ``(fecha, id)``
    del último registro visto (la página sigue estrictamente después)."""

    tenant_id: uuid.UUID | None = None
    accion: str | None = None
    desde: datetime | None = None
    hasta: datetime | None = None
    cursor: tuple[datetime, uuid.UUID] | None = None
    limite: int = 50


@dataclass(frozen=True)
class RegistroAuditoria:
    """Una fila de ``acceso.plataforma_listar_auditoria`` (R32). ``repr`` sin nombres."""

    id: uuid.UUID
    creado_en: datetime
    accion: str
    resultado: str
    desarrollador_nombre: str | None = field(repr=False)
    tenant_id: uuid.UUID | None
    tenant_nombre: str | None = field(repr=False)
    objeto_id: uuid.UUID | None


def _instante(value: datetime | None, sentinel: str) -> str:
    if value is None:
        return sentinel
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise TypeError("Se esperaba un datetime con zona horaria.")
    return value.isoformat()


def plataforma_listar_auditoria(
    session: Session, filtro: FiltroAuditoria
) -> list[RegistroAuditoria]:
    """``acceso.plataforma_listar_auditoria`` con el desarrollador de ``session`` (R32).

    Solo lectura. ``PlataformaFuncionError`` con ``desarrollador_no_autorizado``.
    """
    if filtro.cursor is None:
        cursor_fecha, cursor_id = "infinity", _PRIMER_CURSOR_ID
    else:
        fecha, ultimo = filtro.cursor
        if not isinstance(ultimo, uuid.UUID):
            raise TypeError("El cursor debe llevar un UUID.")
        cursor_fecha, cursor_id = _instante(fecha, "infinity"), str(ultimo)
    if type(filtro.limite) is not int:
        raise TypeError("limite debe ser un entero.")
    params = {
        "tenant": _SIN_TENANT
        if filtro.tenant_id is None
        else str(_normalize_tenant(filtro.tenant_id)),
        "accion": filtro.accion or "",
        "desde": _instante(filtro.desde, "-infinity"),
        "hasta": _instante(filtro.hasta, "infinity"),
        "limite": filtro.limite,
        "cursor_fecha": cursor_fecha,
        "cursor_id": cursor_id,
    }
    rows = _plataforma_call(session, _PLATAFORMA_LISTAR_AUDITORIA, params).all()
    return [
        RegistroAuditoria(
            id=row.id,
            creado_en=row.creado_en,
            accion=row.accion,
            resultado=row.resultado,
            desarrollador_nombre=row.desarrollador_nombre,
            tenant_id=row.tenant_id,
            tenant_nombre=row.tenant_nombre,
            objeto_id=row.objeto_id,
        )
        for row in rows
    ]


# --- Función del logo de la consola (spec 017, T7 en 0029; C1/T12 en 0030: reemplazo) --------

_PLATAFORMA_REGISTRAR_LOGO = text(
    "select logo_id, creado, reemplazado from acceso.plataforma_registrar_logo("
    ":desarrollador, :tenant, :logo, :clave, :bytes, :ancho, :alto)"
)


@dataclass(frozen=True)
class LogoRegistrado:
    """Resultado de ``acceso.plataforma_registrar_logo``: ``creado`` es ``False`` si la
    empresa ya tenía este mismo logo (idempotente; no se escribió nada); ``reemplazado``,
    si el logo nuevo sustituyó a otro vigente (el anterior se conserva, 013 R2)."""

    logo_id: uuid.UUID
    creado: bool
    reemplazado: bool = False


def plataforma_registrar_logo(
    session: Session,
    *,
    tenant_id: uuid.UUID,
    logo_id: uuid.UUID,
    clave: str,
    bytes_: int,
    ancho: int,
    alto: int,
) -> LogoRegistrado:
    """``acceso.plataforma_registrar_logo`` en la transacción de ``session`` (R23, R44).

    El PNG ya procesado (reglas de la 013) lo guarda quien llama **después**, solo si
    ``creado``. ``PlataformaFuncionError`` con ``clave_invalida``,
    ``empresa_no_encontrada``, ``empresa_sin_datos``, ``empresa_sin_admin``,
    ``logo_id_en_uso``, ``empresa_ocupada`` (fila bloqueada más allá del
    ``lock_timeout``) o ``desarrollador_no_autorizado``.
    """
    if not isinstance(logo_id, uuid.UUID):
        raise TypeError("logo_id debe ser un UUID.")
    for valor in (bytes_, ancho, alto):
        if type(valor) is not int:
            raise TypeError("bytes, ancho y alto deben ser enteros.")
    params = {
        "tenant": str(_normalize_tenant(tenant_id)),
        "logo": str(logo_id),
        "clave": clave,
        "bytes": bytes_,
        "ancho": ancho,
        "alto": alto,
    }
    row = _plataforma_call(session, _PLATAFORMA_REGISTRAR_LOGO, params).one()
    if (
        type(row.creado) is not bool
        or type(row.reemplazado) is not bool
        or row.logo_id != logo_id
        or (row.reemplazado and not row.creado)
    ):
        raise RuntimeError("Resultado inesperado de plataforma_registrar_logo.")
    return LogoRegistrado(logo_id=row.logo_id, creado=row.creado, reemplazado=row.reemplazado)


# --- Ficha de la empresa desde la consola (spec 017, C1/T12; 0030) ----------------------------

_PLATAFORMA_LEER_EMPRESA = text(
    "select nombre, direccion, nit, telefono, correo, tiene_logo "
    "from acceso.plataforma_leer_empresa(:desarrollador, :tenant)"
)
_PLATAFORMA_ACTUALIZAR_EMPRESA = text(
    "select acceso.plataforma_actualizar_empresa("
    ":desarrollador, :tenant, :nombre, :direccion, :nit, :telefono, :correo)"
)


@dataclass(frozen=True)
class FichaLeida:
    """Una fila de ``acceso.plataforma_leer_empresa`` (R41). ``repr`` sin los datos."""

    nombre: str = field(repr=False)
    direccion: str | None = field(repr=False)
    nit: str | None = field(repr=False)
    telefono: str | None = field(repr=False)
    correo: str | None = field(repr=False)
    tiene_logo: bool


def plataforma_leer_empresa(session: Session, tenant_id: uuid.UUID) -> FichaLeida:
    """``acceso.plataforma_leer_empresa`` con el desarrollador de ``session`` (R41).

    Solo lectura. ``PlataformaFuncionError`` con ``empresa_no_encontrada``,
    ``empresa_sin_datos`` o ``desarrollador_no_autorizado``.
    """
    params = {"tenant": str(_normalize_tenant(tenant_id))}
    row = _plataforma_call(session, _PLATAFORMA_LEER_EMPRESA, params).one()
    if type(row.tiene_logo) is not bool:
        raise RuntimeError("Resultado inesperado de plataforma_leer_empresa.")
    return FichaLeida(
        nombre=row.nombre,
        direccion=row.direccion,
        nit=row.nit,
        telefono=row.telefono,
        correo=row.correo,
        tiene_logo=row.tiene_logo,
    )


def plataforma_actualizar_empresa(
    session: Session, tenant_id: uuid.UUID, ficha: FichaEmpresa
) -> bool:
    """``acceso.plataforma_actualizar_empresa`` en la transacción de ``session`` (R42, R43).

    ``ficha`` ya validada y normalizada en Flask (reglas de la 013); los opcionales viajan
    como ``''`` (la función es ``STRICT``) y se guardan como ``NULL``. Devuelve si cambió
    algo (``False``: no escribió nada). Si cambió el nombre, también cambia
    ``tenant.nombre`` (Q-E1). ``PlataformaFuncionError`` con ``empresa_no_encontrada``,
    ``empresa_sin_datos``, ``empresa_ocupada`` (fila bloqueada más allá del
    ``lock_timeout``) o ``desarrollador_no_autorizado``.
    """
    params = {
        "tenant": str(_normalize_tenant(tenant_id)),
        "nombre": ficha.nombre,
        "direccion": ficha.direccion,
        "nit": ficha.nit or "",
        "telefono": ficha.telefono or "",
        "correo": ficha.correo or "",
    }
    cambiado = _plataforma_call(session, _PLATAFORMA_ACTUALIZAR_EMPRESA, params).scalar_one()
    if type(cambiado) is not bool:
        raise RuntimeError("Resultado inesperado de plataforma_actualizar_empresa.")
    return cambiado
