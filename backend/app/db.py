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

El engine se crea en ``init_db`` (llamado por ``create_app``), nunca al importar.
``create_engine`` no abre conexiones; la primera se abre al usar la sesión.
Ningún mensaje de este módulo incluye la URL de la base ni credenciales.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from flask import Flask, current_app, has_app_context
from sqlalchemy import Uuid, create_engine, event, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError
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


@dataclass(frozen=True)
class _Database:
    engine: Engine
    session_factory: sessionmaker[_TenantSession]


def init_db(app: Flask) -> None:
    """Crea el engine y la fábrica de sesiones de ``app`` sin conectar."""
    engine = create_engine(
        app.config["DATABASE_URL"],
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
