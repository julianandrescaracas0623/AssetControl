"""Atributos de los roles de base (spec 002, T2; A6, plan.md §7.4).

Solo ``pg_roles`` (y ``pg_has_role`` para la membresía): el rol de la
aplicación y ``auth_owner`` no son superusuarios ni tienen ``BYPASSRLS``,
``CREATEROLE``, ``CREATEDB`` ni ``REPLICATION``, ``auth_owner`` no inicia sesión
y la aplicación no es miembro de ``auth_owner`` (no puede hacer ``SET ROLE
auth_owner``) ni al revés. La comprobación al arrancar con un rol inseguro es de T4.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Connection
from sqlalchemy.pool import NullPool

AUTH_OWNER = "auth_owner"

_ATTRIBUTES = text(
    "select rolsuper, rolbypassrls, rolcanlogin, rolcreaterole, rolcreatedb, rolreplication "
    "from pg_roles where rolname = :r"
)


@pytest.fixture
def migrator_conn(migration_database_url: URL) -> Iterator[Connection]:
    engine = create_engine(migration_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            yield conn
    finally:
        engine.dispose()


def test_app_role_does_not_skip_rls(migrator_conn, app_database_url):
    row = migrator_conn.execute(_ATTRIBUTES, {"r": app_database_url.username}).one()
    assert row == (False, False, True, False, False, False)


def test_auth_owner_does_not_skip_rls_and_cannot_log_in(migrator_conn):
    row = migrator_conn.execute(_ATTRIBUTES, {"r": AUTH_OWNER}).one()
    assert row == (False, False, False, False, False, False)


def test_app_role_sees_its_own_attributes_without_super_or_bypassrls(app_database_url):
    engine = create_engine(app_database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("select rolsuper, rolbypassrls from pg_roles where rolname = current_user")
            ).one()
    finally:
        engine.dispose()
    assert row == (False, False)


@pytest.mark.parametrize("privilege", ["MEMBER", "USAGE", "SET"])
def test_app_role_and_auth_owner_are_not_members_of_each_other(
    migrator_conn, app_database_url, privilege
):
    app_role = app_database_url.username
    for member, role in ((app_role, AUTH_OWNER), (AUTH_OWNER, app_role)):
        has = migrator_conn.scalar(
            text("select pg_has_role(:m, :r, :p)"), {"m": member, "r": role, "p": privilege}
        )
        assert has is False, (member, role, privilege)
