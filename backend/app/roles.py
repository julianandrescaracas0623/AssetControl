"""Roles de la base en un PostgreSQL administrado (spec 010b, T4; R5; C8 de la spec 002).

``docker/postgres/init/01-app-role.sh`` prepara los roles en local, donde el migrador es
superusuario. En Supabase el migrador (``postgres``) **no** es superusuario: no puede fijar
``log_min_error_statement`` ni revocar la membresía con ``ADMIN OPTION`` que PostgreSQL 16+
le da sobre cada rol que crea (concedida por el superusuario de arranque). Este módulo hace
lo mismo que el script, apto para ese caso:

- La contraseña del rol de la aplicación **nunca viaja en claro**: se envía su verificador
  SCRAM-SHA-256 calculado aquí (RFC 5802/7677), así ni un registro de sentencias del
  servidor la vería. Solo ASCII imprimible (sin SASLprep que pudiera no coincidir).
- Rol de la aplicación: ``LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE
  NOREPLICATION``; ``CONNECT`` a la base y ``USAGE`` en ``public``, sin ``CREATE``.
- ``auth_owner`` y ``plataforma_owner`` (spec 017): ``NOLOGIN`` y sin ningún atributo ni
  ``CREATE``.
- Membresías de los tres: se revocan todas las que el migrador puede revocar (por ejemplo
  la que ``createrole_self_grant`` le concede con ``INHERIT``/``SET``). La única que puede
  quedar es la del creador con ``ADMIN OPTION`` y **sin** ``INHERIT`` ni ``SET`` (no le da
  los privilegios del rol); cualquier otra detiene el comando.

Ningún mensaje incluye la contraseña, su verificador ni la URL.
"""

import base64
import hashlib
import hmac
import os
import re
from dataclasses import dataclass

import psycopg
from psycopg import sql

AUTH_OWNER = "auth_owner"
PLATAFORMA_OWNER = "plataforma_owner"
OWNERS = (AUTH_OWNER, PLATAFORMA_OWNER)
SCRAM_ITERACIONES = 4096
CONTRASENA_MIN = 24
IDENTIFICADOR = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
ASCII_IMPRIMIBLE = re.compile(r"^[\x21-\x7e]+$")


class ErrorRoles(RuntimeError):
    """Fallo legible para el operador; nunca con secretos."""


def verificador_scram(
    contrasena: str, *, sal: bytes | None = None, iteraciones: int = SCRAM_ITERACIONES
) -> str:
    """``SCRAM-SHA-256$<iter>:<sal>$<StoredKey>:<ServerKey>``, como lo guarda PostgreSQL."""
    sal = os.urandom(16) if sal is None else sal
    salada = hashlib.pbkdf2_hmac("sha256", contrasena.encode(), sal, iteraciones)
    client_key = hmac.new(salada, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salada, b"Server Key", hashlib.sha256).digest()
    b64 = lambda b: base64.b64encode(b).decode()  # noqa: E731
    return f"SCRAM-SHA-256${iteraciones}:{b64(sal)}${b64(stored_key)}:{b64(server_key)}"


def validar(app_user: str, contrasena: str, migrador: str) -> None:
    if not IDENTIFICADOR.fullmatch(app_user):
        raise ErrorRoles("APP_DB_USER debe ser un identificador simple: minúsculas, números y _.")
    if app_user in (migrador, *OWNERS):
        raise ErrorRoles(
            "APP_DB_USER no puede ser el rol migrador, auth_owner ni plataforma_owner."
        )
    if len(contrasena) < CONTRASENA_MIN or not ASCII_IMPRIMIBLE.fullmatch(contrasena):
        raise ErrorRoles(
            f"APP_DB_PASSWORD debe tener al menos {CONTRASENA_MIN} caracteres ASCII "
            "imprimibles, sin espacios."
        )


@dataclass(frozen=True)
class Resultado:
    creado: bool
    revocadas: int
    conservadas: int


def _existe(cur: psycopg.Cursor, rol: str) -> bool:
    cur.execute("select 1 from pg_roles where rolname = %s", (rol,))
    return cur.fetchone() is not None


def _membresias(cur: psycopg.Cursor, roles: tuple[str, ...]) -> list[tuple]:
    cur.execute(
        """
        select g.rolname, m.rolname, gr.rolname, a.admin_option, a.inherit_option, a.set_option
          from pg_auth_members a
          join pg_roles g on g.oid = a.roleid
          join pg_roles m on m.oid = a.member
          join pg_roles gr on gr.oid = a.grantor
         where g.rolname = any(%s) or m.rolname = any(%s)
         order by a.oid
        """,
        (list(roles), list(roles)),
    )
    return cur.fetchall()


def preparar(conninfo: str, app_user: str, contrasena: str) -> Resultado:
    """Crea o reafirma el rol de la aplicación y los dueños en una transacción."""
    with (
        psycopg.connect(conninfo, connect_timeout=5, autocommit=False) as conn,
        conn.cursor() as cur,
    ):
        cur.execute("select current_user, current_database()")
        migrador, base = cur.fetchone()  # type: ignore[misc]
        validar(app_user, contrasena, migrador)
        app = sql.Identifier(app_user)
        clave = sql.Literal(verificador_scram(contrasena))
        # Al crear se fijan todos los atributos. Al alterar, un migrador no superusuario
        # no puede ni nombrar SUPERUSER, REPLICATION o BYPASSRLS (PostgreSQL 16+): se
        # omiten y la comprobación final exige que estén apagados.
        crear = sql.SQL("NOSUPERUSER NOBYPASSRLS NOREPLICATION NOCREATEDB NOCREATEROLE")
        alterar = sql.SQL("NOCREATEDB NOCREATEROLE")
        creado = not _existe(cur, app_user)
        cur.execute(
            sql.SQL("{} {} LOGIN {} PASSWORD {}").format(
                sql.SQL("CREATE ROLE" if creado else "ALTER ROLE"),
                app,
                crear if creado else alterar,
                clave,
            )
        )
        for nombre in OWNERS:
            nuevo_owner = not _existe(cur, nombre)
            cur.execute(
                sql.SQL("{} {} NOLOGIN {} PASSWORD NULL").format(
                    sql.SQL("CREATE ROLE" if nuevo_owner else "ALTER ROLE"),
                    sql.Identifier(nombre),
                    crear if nuevo_owner else alterar,
                )
            )
        gestionados = (app_user, *OWNERS)

        revocadas = 0
        for _ in range(100):  # cada REVOKE ... CASCADE puede quitar otras: se relee
            pendiente = next(
                (m for m in _membresias(cur, gestionados) if m[2] == migrador),
                None,
            )
            if pendiente is None:
                break
            concedido, miembro, otorgante = pendiente[:3]
            cur.execute(
                sql.SQL("REVOKE {} FROM {} GRANTED BY {} CASCADE").format(
                    sql.Identifier(concedido), sql.Identifier(miembro), sql.Identifier(otorgante)
                )
            )
            revocadas += 1
        restantes = _membresias(cur, gestionados)
        for concedido, miembro, _otorgante, admin, inherit, set_ in restantes:
            # Solo la del creador sobre el rol que creó, para administrarlo y nada más.
            if not (
                miembro == migrador
                and concedido in gestionados
                and admin
                and not inherit
                and not set_
            ):
                raise ErrorRoles(
                    f"Queda una membresía que no se puede revocar desde {migrador}: "
                    f"{miembro} en {concedido}. Revísala con el superusuario del proveedor."
                )

        cur.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(base), app))
        cur.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(app))
        for rol in (app_user, *OWNERS):
            cur.execute(
                sql.SQL("REVOKE CREATE ON SCHEMA public FROM {}").format(sql.Identifier(rol))
            )
        for nombre in OWNERS:
            cur.execute(
                sql.SQL("REVOKE CREATE ON DATABASE {} FROM {}").format(
                    sql.Identifier(base), sql.Identifier(nombre)
                )
            )

        cur.execute(
            "select rolname, rolsuper or rolbypassrls or rolcreaterole or rolcreatedb "
            "or rolreplication, rolcanlogin from pg_roles where rolname = any(%s)",
            (list(gestionados),),
        )
        for rol, con_atributos, login in cur.fetchall():
            if con_atributos or login != (rol == app_user):
                raise ErrorRoles(f"El rol {rol} quedó con un atributo que no debe tener.")
        conn.commit()
        return Resultado(creado=creado, revocadas=revocadas, conservadas=len(restantes))
