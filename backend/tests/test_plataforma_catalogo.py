"""Catálogo y comportamiento en base de ``0017_plataforma``, ``0018_funciones_plataforma``,
``0027_plataforma_usuarios``, ``0028_plataforma_actividad``, ``0029_plataforma_logo``,
``0030_plataforma_edicion_empresa``, ``0031_plataforma_editar_usuario`` y
``0032_plataforma_password_usuario``.

Spec 017, T1, T3a, T5 (las dos funciones de Usuarios y sus políticas sobre ``tenant``,
``membresia``, ``usuario`` y ``refresh_token``; su comportamiento está en
``test_plataforma_usuarios.py``) y T6 (la función de Actividad y sus políticas de lectura
sobre ``plataforma_auditoria``, ``tenant`` y ``desarrollador``; su comportamiento está en
``test_plataforma_actividad.py``) y T7 (la función del logo en el alta y sus políticas sobre
``tenant``, ``membresia``, ``empresa`` y ``empresa_logo``; su comportamiento está en
``test_plataforma_logo.py``) y C1/T12 (las dos funciones de la ficha, la del logo rehecha
con reemplazo y sus políticas sobre ``empresa`` y ``tenant``; su comportamiento está en
``test_plataforma_edicion.py`` y ``test_plataforma_logo.py``) y C1/T13 (la función de editar
nombre y rol, sus políticas sobre ``usuario`` y los privilegios por columna de
``usuario.nombre`` y ``membresia.rol``; su comportamiento está en
``test_plataforma_usuario_edicion.py``) y C1b/T16 (la función de la contraseña temporal, sus
políticas sobre ``membresia``, ``usuario`` y ``refresh_token`` y el ``UPDATE`` por columna de
``password_hash``, ``debe_cambiar_password`` y ``sesiones_validas_desde``, sin ``SELECT`` del
hash; su comportamiento está en ``test_plataforma_usuario_password.py``). Cubre A4 (funciones de
0017 y 0018 y las políticas de ``plataforma_owner`` sobre ``tenant``, ``usuario``,
``membresia`` y ``empresa``; el comportamiento de las funciones de 0018 está en
``test_plataforma_funciones.py``), A10 (auditoría de solo inserción; la aplicación solo
inserta sus acciones), A13 (parte: el rol de la aplicación no ejecuta las funciones del
operador), A15 (parte: tablas nuevas,
``tenant.activo`` y ``usuario.debe_cambiar_password`` en el catálogo de RLS) y R33–R34
(lista cerrada de acciones, sin datos personales).

Sobre una base temporal migrada a ``head`` (con los roles de Supabase y sus privilegios
por defecto, como ``test_catalog_rls.py``) comprueba leyendo los catálogos:

- Las tres tablas nuevas (excepciones cerradas a «toda tabla lleva ``tenant_id``»): columnas,
  claves, ``CHECK``, índices, RLS habilitada y forzada.
- Políticas: lista cerrada con texto exacto, las de la aplicación sobre las tablas nuevas y
  todas las ``TO plataforma_owner`` (una por comando, nunca ``FOR ALL``).
- ``GRANT`` exactos de la aplicación (nunca ``password_hash``) y de ``plataforma_owner``
  (por columna, sin ``DELETE``, nada en otras tablas); nada para los roles de Supabase.
- ``plataforma_owner`` inerte, sin membresías, con ``USAGE`` y sin ``CREATE`` en ``acceso``.
- Las cuatro funciones de 0017: firma, resultado, ``SECURITY DEFINER``, ``STRICT``,
  ``plpgsql``, dueña ``plataforma_owner``, ``search_path`` fijo, ``proacl`` exacto (la
  aplicación solo ``plataforma_buscar_login``; el migrador las tres del operador) y cuerpo
  exacto (huella ``sha256``), estático, calificado y sin leer GUC.

Y su comportamiento con el rol de la aplicación y el migrador: aislamiento por
``app.desarrollador_id``, auditoría sin ``UPDATE``/``DELETE``, funciones del operador
(crear, restablecer y cambiar estado, con revocación y auditoría con ``desarrollador_id``
nulo) y el login de plataforma. Datos sintéticos (``@ejemplo.test``).
"""

import hashlib
import re
import secrets
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import argon2
import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from conftest import BLOCKED, read_database_url, role_sees_all_rows
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Connection, Engine
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.pool import NullPool

from app.auth.credentials import ARGON2_TEST_PARAMS

BACKEND_DIR = Path(__file__).resolve().parent.parent
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
OWNER = "plataforma_owner"
AUTH_OWNER = "auth_owner"
SUPABASE_ROLES = ("anon", "authenticated", "service_role")
PLATFORM_TABLES = ("desarrollador", "plataforma_refresh_token", "plataforma_auditoria")
# Spec 017, T3a (0018): tablas existentes que abren las políticas de plataforma_owner.
# T5 (0027): también refresh_token (revocar las familias de una membresía desactivada).
# T7 (0029): también empresa_logo (solo el INSERT del logo inicial).
OWNER_BUSINESS_TABLES = (
    "tenant",
    "usuario",
    "membresia",
    "empresa",
    "refresh_token",
    "empresa_logo",
)
INSUFFICIENT_PRIVILEGE = "42501"

ACCIONES = [
    "login_ok",
    "empresa_creada",
    "empresa_desactivada",
    "empresa_reactivada",
    "empresa_logo_subido",
    "usuario_desactivado",
    "usuario_reactivado",
    "desarrollador_creado",
    "desarrollador_restablecido",
    "desarrollador_desactivado",
    "desarrollador_reactivado",
    # Spec 017, C1 (0030): editar la ficha, reemplazar el logo y editar un usuario.
    "empresa_editada",
    "empresa_logo_reemplazado",
    "usuario_editado",
    # Spec 017, C1b (0032): contraseña temporal de un usuario.
    "usuario_contrasena_restablecida",
]


# --- Texto esperado de pg_policies (espacios normalizados) ---------------------------


def _uuid_guc(guc: str) -> str:
    setting = f"current_setting('{guc}'::text, true)"
    pattern = "^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    return f"CASE WHEN ({setting} ~ '{pattern}'::text) THEN ({setting})::uuid ELSE NULL::uuid END"


def _text_guc(guc: str) -> str:
    return f"NULLIF(current_setting('{guc}'::text, true), ''::text)"


_DEV = "(NULLIF(current_setting('app.desarrollador_id'::text, true), ''::text))::uuid"
_ACTIVO = (
    "(EXISTS ( SELECT 1 FROM desarrollador d "  # noqa: S608
    f"WHERE ((d.id = {_DEV}) AND d.activo)))"
)
_OBJETIVO = _uuid_guc("app.plat_dev_objetivo")
_RESTABLECER = f"(email = {_text_guc('app.plat_dev_restablecer')})"
_ESTADO = f"(email = {_text_guc('app.plat_dev_estado')})"
# Spec 017, T3a (0018).
_ACCIONES_APP = (
    "login_ok",
    "empresa_creada",
    "empresa_desactivada",
    "empresa_reactivada",
    "empresa_logo_subido",
    "usuario_desactivado",
    "usuario_reactivado",
    # Spec 017, C1 (0030).
    "empresa_editada",
    "empresa_logo_reemplazado",
    "usuario_editado",
    # Spec 017, C1b (0032).
    "usuario_contrasena_restablecida",
)
_ACCIONES_APP_ARRAY = ", ".join(f"'{a}'::text" for a in _ACCIONES_APP)
_ACTOR_GUC = _uuid_guc("app.plat_actor")
_TENANT_NUEVO = _uuid_guc("app.plat_tenant_nuevo")
_USUARIO_NUEVO = _uuid_guc("app.plat_usuario_nuevo")
_TENANT_ESTADO = _uuid_guc("app.plat_tenant_estado")


def _dev_activo(guc: str) -> str:
    return (
        "(EXISTS ( SELECT 1 FROM desarrollador d "  # noqa: S608
        f"WHERE ((d.id = {guc}) AND d.activo)))"
    )


_ACTOR = _dev_activo(_ACTOR_GUC)
_LISTAR = _dev_activo(_uuid_guc("app.plat_listar"))
_RECIEN = (
    "(EXISTS ( SELECT 1 FROM tenant t "  # noqa: S608
    f"WHERE ((t.id = {_TENANT_NUEVO}) AND (t.creado_en = now()))))"
)
# Spec 017, T5 (0027): Usuarios.
_USUARIOS = _uuid_guc("app.plat_usuarios")
_MEM_TENANT = _uuid_guc("app.plat_membresia_tenant")
_MEM_USUARIO = _uuid_guc("app.plat_membresia_usuario")
_DE_LA_MEMBRESIA = (
    f"(tenant_id = {_MEM_TENANT}) AND (EXISTS ( SELECT 1 FROM membresia m "  # noqa: S608
    "WHERE ((m.id = refresh_token.membresia_id) AND (m.tenant_id = refresh_token.tenant_id) "
    f"AND (m.usuario_id = {_MEM_USUARIO}))))"
)
# Spec 017, T6 (0028): Actividad.
_ACTIVIDAD_GUC = _uuid_guc("app.plat_actividad")
_ACTIVIDAD = _dev_activo(_ACTIVIDAD_GUC)
# Spec 017, T7 (0029): logo en el alta.
_LOGO_TENANT = _uuid_guc("app.plat_logo_tenant")
_LOGO_ID = _uuid_guc("app.plat_logo_id")
# Spec 017, C1 (0030): ficha de la empresa.
_EMPRESA_TENANT = _uuid_guc("app.plat_empresa_tenant")
# Spec 017, C1/T13 (0031): el usuario que se edita (con las GUC de membresía de 0027).
_USUARIO_EDICION = _uuid_guc("app.plat_usuario_edicion")
_USUARIO_DEL_TENANT = (
    f"((id = {_USUARIO_EDICION}) AND (EXISTS ( SELECT 1 FROM membresia m "  # noqa: S608
    f"WHERE ((m.usuario_id = usuario.id) AND (m.tenant_id = {_MEM_TENANT})))) AND {_ACTOR})"
)
# Spec 017, C1b/T16 (0032): el usuario cuya contraseña se define (con la GUC de empresa de 0027).
_USUARIO_PASSWORD = _uuid_guc("app.plat_usuario_password")
_PASSWORD_DEL_TENANT = (
    f"((id = {_USUARIO_PASSWORD}) AND (EXISTS ( SELECT 1 FROM membresia m "  # noqa: S608
    f"WHERE ((m.usuario_id = usuario.id) AND (m.tenant_id = {_MEM_TENANT})))) AND {_ACTOR})"
)
_DEL_USUARIO_PASSWORD = (
    "(EXISTS ( SELECT 1 FROM membresia m WHERE ((m.id = refresh_token.membresia_id) "  # noqa: S608
    f"AND (m.tenant_id = refresh_token.tenant_id) AND (m.usuario_id = {_USUARIO_PASSWORD}))))"
)

# (tabla, nombre) -> (permissive, cmd, roles, USING, WITH CHECK); "app" = rol de la aplicación.
EXPECTED_POLICIES = {
    ("desarrollador", "desarrollador_propio"): (
        "PERMISSIVE",
        "SELECT",
        "app",
        f"(id = {_DEV})",
        None,
    ),
    ("plataforma_refresh_token", "plataforma_refresh_leer"): (
        "PERMISSIVE",
        "SELECT",
        "app",
        f"(desarrollador_id = {_DEV})",
        None,
    ),
    ("plataforma_refresh_token", "plataforma_refresh_crear"): (
        "PERMISSIVE",
        "INSERT",
        "app",
        None,
        f"(desarrollador_id = {_DEV})",
    ),
    ("plataforma_refresh_token", "plataforma_refresh_marcar"): (
        "PERMISSIVE",
        "UPDATE",
        "app",
        f"(desarrollador_id = {_DEV})",
        f"(desarrollador_id = {_DEV})",
    ),
    # Spec 017, T3a (0018): la aplicación solo inserta sus acciones (nunca las del operador);
    # login_ok sin tenant y sobre el propio desarrollador; las demás con tenant.
    ("plataforma_auditoria", "plataforma_auditoria_insertar"): (
        "PERMISSIVE",
        "INSERT",
        "app",
        None,
        f"((desarrollador_id = {_DEV}) AND {_ACTIVO} "
        f"AND (accion = ANY (ARRAY[{_ACCIONES_APP_ARRAY}])) "
        f"AND (((accion = 'login_ok'::text) AND (tenant_id IS NULL) AND (objeto_id = {_DEV})) "
        "OR ((accion <> 'login_ok'::text) AND (tenant_id IS NOT NULL))))",
    ),
    ("plataforma_auditoria", "plataforma_auditoria_leer"): (
        "PERMISSIVE",
        "SELECT",
        "app",
        _ACTIVO,
        None,
    ),
    # --- plataforma_owner: una GUC por función, cero filas con la GUC vacía ---
    ("desarrollador", "dueno_plat_desarrollador_login"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        f"(email = {_text_guc('app.plat_login_email')})",
        None,
    ),
    ("desarrollador", "dueno_plat_desarrollador_crear"): (
        "PERMISSIVE",
        "INSERT",
        OWNER,
        None,
        f"((id = {_uuid_guc('app.plat_dev_crear')}) AND activo)",
    ),
    ("desarrollador", "dueno_plat_desarrollador_restablecer_leer"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        _RESTABLECER,
        None,
    ),
    ("desarrollador", "dueno_plat_desarrollador_restablecer"): (
        "PERMISSIVE",
        "UPDATE",
        OWNER,
        _RESTABLECER,
        _RESTABLECER,
    ),
    ("desarrollador", "dueno_plat_desarrollador_estado_leer"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        _ESTADO,
        None,
    ),
    ("desarrollador", "dueno_plat_desarrollador_estado"): (
        "PERMISSIVE",
        "UPDATE",
        OWNER,
        _ESTADO,
        _ESTADO,
    ),
    ("plataforma_refresh_token", "dueno_plat_refresh_leer"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        f"(desarrollador_id = {_OBJETIVO})",
        None,
    ),
    ("plataforma_refresh_token", "dueno_plat_refresh_revocar"): (
        "PERMISSIVE",
        "UPDATE",
        OWNER,
        f"((desarrollador_id = {_OBJETIVO}) AND (revocado_en IS NULL))",
        f"((desarrollador_id = {_OBJETIVO}) AND (revocado_en = now()))",
    ),
    ("plataforma_auditoria", "dueno_plat_auditoria_operador"): (
        "PERMISSIVE",
        "INSERT",
        OWNER,
        None,
        "((desarrollador_id IS NULL) AND (tenant_id IS NULL) AND (resultado = 'ok'::text) "
        "AND (accion = ANY (ARRAY['desarrollador_creado'::text, "
        "'desarrollador_restablecido'::text, 'desarrollador_desactivado'::text, "
        f"'desarrollador_reactivado'::text])) AND (objeto_id = {_OBJETIVO}))",
    ),
    # --- Spec 017, T3a (0018): Empresas; todo exige un desarrollador activo ---
    ("desarrollador", "dueno_plat_desarrollador_actor"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        f"(id = {_ACTOR_GUC})",
        None,
    ),
    ("tenant", "dueno_plat_tenant_listar"): ("PERMISSIVE", "SELECT", OWNER, _LISTAR, None),
    ("empresa", "dueno_plat_empresa_listar"): ("PERMISSIVE", "SELECT", OWNER, _LISTAR, None),
    ("membresia", "dueno_plat_membresia_listar"): ("PERMISSIVE", "SELECT", OWNER, _LISTAR, None),
    ("tenant", "dueno_plat_tenant_crear"): (
        "PERMISSIVE",
        "INSERT",
        OWNER,
        None,
        f"((id = {_TENANT_NUEVO}) AND activo AND (desactivado_en IS NULL) "
        f"AND (desactivado_por IS NULL) AND {_ACTOR})",
    ),
    ("tenant", "dueno_plat_tenant_recien_creado"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        f"((id = {_TENANT_NUEVO}) AND (creado_en = now()))",
        None,
    ),
    ("usuario", "dueno_plat_usuario_crear"): (
        "PERMISSIVE",
        "INSERT",
        OWNER,
        None,
        f"((id = {_USUARIO_NUEVO}) AND activo AND debe_cambiar_password AND {_RECIEN} "
        f"AND {_ACTOR})",
    ),
    ("membresia", "dueno_plat_membresia_crear"): (
        "PERMISSIVE",
        "INSERT",
        OWNER,
        None,
        f"((tenant_id = {_TENANT_NUEVO}) AND (usuario_id = {_USUARIO_NUEVO}) "
        f"AND (rol = 'admin'::text) AND activa AND {_RECIEN} AND {_ACTOR})",
    ),
    ("empresa", "dueno_plat_empresa_crear"): (
        "PERMISSIVE",
        "INSERT",
        OWNER,
        None,
        f"((tenant_id = {_TENANT_NUEVO}) AND (actualizada_por = {_USUARIO_NUEVO}) "
        f"AND (logo_id IS NULL) AND {_RECIEN} AND {_ACTOR})",
    ),
    ("tenant", "dueno_plat_tenant_estado_leer"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        f"((id = {_TENANT_ESTADO}) AND {_ACTOR})",
        None,
    ),
    ("tenant", "dueno_plat_tenant_estado"): (
        "PERMISSIVE",
        "UPDATE",
        OWNER,
        f"((id = {_TENANT_ESTADO}) AND {_ACTOR})",
        f"((id = {_TENANT_ESTADO}) AND ((activo AND (desactivado_en IS NULL) "
        "AND (desactivado_por IS NULL)) OR ((NOT activo) AND (desactivado_en = now()) "
        f"AND (desactivado_por = {_ACTOR_GUC}))))",
    ),
    # --- Spec 017, T5 (0027): Usuarios; todo exige un desarrollador activo ---
    ("tenant", "dueno_plat_tenant_usuarios"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        f"((id = {_USUARIOS}) AND {_ACTOR})",
        None,
    ),
    ("membresia", "dueno_plat_membresia_usuarios"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        f"((tenant_id = {_USUARIOS}) AND {_ACTOR})",
        None,
    ),
    ("usuario", "dueno_plat_usuario_usuarios"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        "((EXISTS ( SELECT 1 FROM membresia m WHERE ((m.usuario_id = usuario.id) "  # noqa: S608
        f"AND (m.tenant_id = {_USUARIOS})))) AND {_ACTOR})",
        None,
    ),
    ("tenant", "dueno_plat_tenant_membresia"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        f"((id = {_MEM_TENANT}) AND {_ACTOR})",
        None,
    ),
    ("membresia", "dueno_plat_membresia_estado_leer"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        f"((tenant_id = {_MEM_TENANT}) AND {_ACTOR})",
        None,
    ),
    ("membresia", "dueno_plat_membresia_estado"): (
        "PERMISSIVE",
        "UPDATE",
        OWNER,
        f"((tenant_id = {_MEM_TENANT}) AND (usuario_id = {_MEM_USUARIO}) AND {_ACTOR})",
        f"((tenant_id = {_MEM_TENANT}) AND (usuario_id = {_MEM_USUARIO}))",
    ),
    ("refresh_token", "dueno_plat_refresh_membresia_leer"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        f"({_DE_LA_MEMBRESIA} AND {_ACTOR})",
        None,
    ),
    ("refresh_token", "dueno_plat_refresh_membresia_revocar"): (
        "PERMISSIVE",
        "UPDATE",
        OWNER,
        f"({_DE_LA_MEMBRESIA} AND (revocado_en IS NULL) AND {_ACTOR})",
        f"({_DE_LA_MEMBRESIA} AND (revocado_en = now()))",
    ),
    # --- Spec 017, T6 (0028): Actividad; solo lectura, para un desarrollador activo ---
    ("plataforma_auditoria", "dueno_plat_auditoria_actividad"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        _ACTIVIDAD,
        None,
    ),
    ("tenant", "dueno_plat_tenant_actividad"): ("PERMISSIVE", "SELECT", OWNER, _ACTIVIDAD, None),
    # Sin EXISTS sobre la propia tabla (recursión): la función ya comprobó el activo.
    ("desarrollador", "dueno_plat_desarrollador_actividad"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        f"( {_ACTIVIDAD_GUC} IS NOT NULL)",
        None,
    ),
    # --- Spec 017, T7 (0029): logo en el alta; todo exige un desarrollador activo ---
    ("tenant", "dueno_plat_tenant_logo"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        f"((id = {_LOGO_TENANT}) AND {_ACTOR})",
        None,
    ),
    ("membresia", "dueno_plat_membresia_logo"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        f"((tenant_id = {_LOGO_TENANT}) AND {_ACTOR})",
        None,
    ),
    ("empresa", "dueno_plat_empresa_logo_leer"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        f"((tenant_id = {_LOGO_TENANT}) AND {_ACTOR})",
        None,
    ),
    # C1 (0030): ya no exige logo_id IS NULL (reemplazo); solo deja el de esta subida.
    ("empresa", "dueno_plat_empresa_logo"): (
        "PERMISSIVE",
        "UPDATE",
        OWNER,
        f"((tenant_id = {_LOGO_TENANT}) AND {_ACTOR})",
        f"((tenant_id = {_LOGO_TENANT}) AND (logo_id = {_LOGO_ID}) AND (actualizada_en = now()))",
    ),
    # Clave del tenant y subido por una membresía admin del tenant.
    ("empresa_logo", "dueno_plat_empresa_logo_crear"): (
        "PERMISSIVE",
        "INSERT",
        OWNER,
        None,
        f"((id = {_LOGO_ID}) AND (tenant_id = {_LOGO_TENANT}) "  # noqa: S608
        "AND (clave = ((((tenant_id)::text || '/'::text) || (id)::text) || '.png'::text)) "
        "AND (EXISTS ( SELECT 1 FROM membresia m WHERE ((m.tenant_id = empresa_logo.tenant_id) "
        "AND (m.usuario_id = empresa_logo.subido_por) AND (m.rol = 'admin'::text)))) "
        f"AND {_ACTOR})",
    ),
    # --- Spec 017, C1 (0030): ficha de la empresa; todo exige un desarrollador activo ---
    ("empresa", "dueno_plat_empresa_ficha_leer"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        f"((tenant_id = {_EMPRESA_TENANT}) AND {_ACTOR})",
        None,
    ),
    ("empresa", "dueno_plat_empresa_ficha"): (
        "PERMISSIVE",
        "UPDATE",
        OWNER,
        f"((tenant_id = {_EMPRESA_TENANT}) AND {_ACTOR})",
        f"((tenant_id = {_EMPRESA_TENANT}) AND (actualizada_en = now()))",
    ),
    ("tenant", "dueno_plat_tenant_ficha_leer"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        f"((id = {_EMPRESA_TENANT}) AND {_ACTOR})",
        None,
    ),
    # tenant.nombre solo puede quedar igual al nombre de su ficha (Q-E1).
    ("tenant", "dueno_plat_tenant_ficha"): (
        "PERMISSIVE",
        "UPDATE",
        OWNER,
        f"((id = {_EMPRESA_TENANT}) AND {_ACTOR})",
        f"((id = {_EMPRESA_TENANT}) AND (EXISTS ( SELECT 1 FROM empresa e "  # noqa: S608
        "WHERE ((e.tenant_id = tenant.id) AND (e.nombre = tenant.nombre)))))",
    ),
    # --- Spec 017, C1/T13 (0031): editar nombre (y rol, con las políticas de 0027) ---
    ("usuario", "dueno_plat_usuario_edicion_leer"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        _USUARIO_DEL_TENANT,
        None,
    ),
    ("usuario", "dueno_plat_usuario_edicion"): (
        "PERMISSIVE",
        "UPDATE",
        OWNER,
        _USUARIO_DEL_TENANT,
        f"(id = {_USUARIO_EDICION})",
    ),
    # --- Spec 017, C1b/T16 (0032): contraseña temporal; todo exige un desarrollador activo ---
    # Las membresías del usuario objetivo, en cualquier empresa (candados y refresh, RC8).
    ("membresia", "dueno_plat_membresia_password"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        f"((usuario_id = {_USUARIO_PASSWORD}) AND {_ACTOR})",
        None,
    ),
    ("usuario", "dueno_plat_usuario_password_leer"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        _PASSWORD_DEL_TENANT,
        None,
    ),
    # No hay hash nuevo sin la marca ni sin el corte de sesiones.
    ("usuario", "dueno_plat_usuario_password"): (
        "PERMISSIVE",
        "UPDATE",
        OWNER,
        _PASSWORD_DEL_TENANT,
        f"((id = {_USUARIO_PASSWORD}) AND debe_cambiar_password "
        "AND (sesiones_validas_desde = now()))",
    ),
    ("refresh_token", "dueno_plat_refresh_password_leer"): (
        "PERMISSIVE",
        "SELECT",
        OWNER,
        f"({_DEL_USUARIO_PASSWORD} AND {_ACTOR})",
        None,
    ),
    ("refresh_token", "dueno_plat_refresh_password_revocar"): (
        "PERMISSIVE",
        "UPDATE",
        OWNER,
        f"({_DEL_USUARIO_PASSWORD} AND (revocado_en IS NULL) AND {_ACTOR})",
        f"({_DEL_USUARIO_PASSWORD} AND (revocado_en = now()))",
    ),
}

TS = "timestamp with time zone"
EXPECTED_COLUMNS = {
    "desarrollador": {
        "id": ("uuid", True),
        "email": ("text", True),
        "nombre": ("text", True),
        "password_hash": ("text", True),
        "activo": ("boolean", True),
        "creado_en": (TS, True),
    },
    "plataforma_refresh_token": {
        "id": ("uuid", True),
        "desarrollador_id": ("uuid", True),
        "familia_id": ("uuid", True),
        "token_hash": ("bytea", True),
        "expira_en": (TS, True),
        "usado_en": (TS, False),
        "revocado_en": (TS, False),
        "creado_en": (TS, True),
    },
    "plataforma_auditoria": {
        "id": ("uuid", True),
        "desarrollador_id": ("uuid", False),
        "accion": ("text", True),
        "resultado": ("text", True),
        "tenant_id": ("uuid", False),
        "objeto_id": ("uuid", False),
        "creado_en": (TS, True),
    },
}
_ACCIONES_CHECK = ", ".join(f"'{a}'::text" for a in ACCIONES)
EXPECTED_CONSTRAINTS = {
    "desarrollador": {
        "PRIMARY KEY (id)",
        "UNIQUE (email)",
        "CHECK ((email = lower(btrim(email))))",
        "CHECK (((char_length(nombre) >= 1) AND (char_length(nombre) <= 120)))",
    },
    "plataforma_refresh_token": {
        "PRIMARY KEY (id)",
        "FOREIGN KEY (desarrollador_id) REFERENCES desarrollador(id)",
        "UNIQUE (token_hash)",
        "CHECK ((octet_length(token_hash) = 32))",
    },
    "plataforma_auditoria": {
        "PRIMARY KEY (id)",
        "FOREIGN KEY (desarrollador_id) REFERENCES desarrollador(id)",
        "FOREIGN KEY (tenant_id) REFERENCES tenant(id)",
        f"CHECK ((accion = ANY (ARRAY[{_ACCIONES_CHECK}])))",
        "CHECK ((resultado = ANY (ARRAY['ok'::text, 'rechazado'::text])))",
    },
}

EXPECTED_APP_COLUMNS = {
    "desarrollador": {"SELECT": {"id", "email", "nombre", "activo"}},
    "plataforma_refresh_token": {
        "SELECT": set(EXPECTED_COLUMNS["plataforma_refresh_token"]),
        "INSERT": set(EXPECTED_COLUMNS["plataforma_refresh_token"]),
        "UPDATE": {"usado_en", "revocado_en"},
    },
    "plataforma_auditoria": {
        "SELECT": set(EXPECTED_COLUMNS["plataforma_auditoria"]),
        "INSERT": {"desarrollador_id", "accion", "resultado", "tenant_id", "objeto_id"},
    },
}
EXPECTED_APP_TABLE_PRIVILEGES = {
    "desarrollador": set(),
    "plataforma_refresh_token": {"SELECT", "INSERT"},
    "plataforma_auditoria": {"SELECT"},
}
# plataforma_owner: tabla -> privilegio -> columnas; nada fuera de estas tablas.
EXPECTED_OWNER_COLUMNS = {
    # Spec 017, T6 (0028): también el nombre (Actividad), nunca más del hash que el login.
    "desarrollador": {
        "SELECT": {"id", "email", "nombre", "password_hash", "activo"},
        "INSERT": {"id", "email", "nombre", "password_hash"},
        "UPDATE": {"password_hash", "activo"},
    },
    "plataforma_refresh_token": {
        "SELECT": {"desarrollador_id", "revocado_en"},
        "UPDATE": {"revocado_en"},
    },
    # Spec 017, T6 (0028): lee la auditoría (sin datos personales, R34); nunca la cambia.
    "plataforma_auditoria": {
        "SELECT": set(EXPECTED_COLUMNS["plataforma_auditoria"]),
        "INSERT": {"accion", "resultado", "objeto_id"},
    },
    # Spec 017, T3a (0018): identidad y estado del tenant; alta de la ficha inicial y del
    # primer admin; de empresa solo lee tenant_id y logo_id (A19); nunca DELETE.
    "tenant": {
        "SELECT": {"id", "nombre", "activo", "creado_en"},
        "INSERT": {"id", "nombre"},
        # C1 (0030): también el nombre, solo para seguir a la ficha (Q-E1).
        "UPDATE": {"nombre", "activo", "desactivado_en", "desactivado_por"},
    },
    # Spec 017, T5 (0027): lee nombre, correo y la marca del usuario (nunca su hash ni
    # sesiones_validas_desde), cambia solo membresia.activa y revoca refresh (nunca token_hash).
    # C1/T13 (0031): también UPDATE (nombre) de usuario y (rol) de membresia; nunca email,
    # password_hash, las marcas del usuario, activo, tenant_id ni usuario_id.
    # C1b/T16 (0032): también UPDATE de password_hash, debe_cambiar_password y
    # sesiones_validas_desde (la contraseña temporal); nunca SELECT de password_hash (R56).
    "usuario": {
        "SELECT": {"id", "email", "nombre", "debe_cambiar_password"},
        "INSERT": {"id", "email", "nombre", "password_hash", "debe_cambiar_password"},
        "UPDATE": {"nombre", "password_hash", "debe_cambiar_password", "sesiones_validas_desde"},
    },
    "membresia": {
        "SELECT": {"id", "tenant_id", "usuario_id", "rol", "activa"},
        "INSERT": {"tenant_id", "usuario_id", "rol"},
        "UPDATE": {"activa", "rol"},
    },
    "refresh_token": {
        "SELECT": {"tenant_id", "membresia_id", "revocado_en"},
        "UPDATE": {"revocado_en"},
    },
    "empresa": {
        # C1 (0030): también las cinco columnas de la ficha (A19); nunca actualizada_por.
        "SELECT": {"tenant_id", "logo_id", "nombre", "direccion", "nit", "telefono", "correo"},
        "INSERT": {
            "tenant_id",
            "nombre",
            "direccion",
            "nit",
            "telefono",
            "correo",
            "actualizada_por",
        },
        # Spec 017, T7 (0029): fijar el logo; C1 (0030): editar las cinco de la ficha.
        "UPDATE": {
            "logo_id",
            "actualizada_en",
            "nombre",
            "direccion",
            "nit",
            "telefono",
            "correo",
        },
    },
    # Spec 017, T7 (0029): solo el INSERT del logo inicial; nunca lee logos.
    "empresa_logo": {
        "INSERT": {"id", "tenant_id", "clave", "bytes", "ancho", "alto", "subido_por"},
    },
}

SEARCH_PATH = ["search_path=pg_catalog, pg_temp"]
# Además del search_path: la de Usuarios acota la espera de sus candados (0027).
FUNCTION_CONFIG = {
    "plataforma_cambiar_estado_membresia": [*SEARCH_PATH, "lock_timeout=5s"],
    # Spec 017, T7 (0029): la fila de empresa puede estar bloqueada por el admin.
    "plataforma_registrar_logo": [*SEARCH_PATH, "lock_timeout=5s"],
    # Spec 017, C1 (0030): la misma fila, al editar la ficha.
    "plataforma_actualizar_empresa": [*SEARCH_PATH, "lock_timeout=5s"],
    # Spec 017, C1/T13 (0031): el mismo candado que desactivar una membresía.
    "plataforma_cambiar_usuario": [*SEARCH_PATH, "lock_timeout=5s"],
    # Spec 017, C1b/T16 (0032): los mismos candados, de cada empresa del usuario.
    "plataforma_restablecer_password_usuario": [*SEARCH_PATH, "lock_timeout=5s"],
}
# nombre -> (argumentos, resultado, GUC que fija, huella sha256 de prosrc, rol con EXECUTE).
EXPECTED_FUNCTIONS = {
    "crear_desarrollador": (
        "p_email text, p_nombre text, p_password_hash text",
        "uuid",
        {"app.plat_dev_crear", "app.plat_dev_objetivo"},
        "c5980fa2693fb58f7b42daf556848f75870f0bb7ca2eab7ac80f51c72cbd915b",
        "migrator",
    ),
    "restablecer_desarrollador": (
        "p_email text, p_password_hash text",
        "void",
        {"app.plat_dev_restablecer", "app.plat_dev_objetivo"},
        "eb2b6ac721d6fc19df3804b01cb1cdc0c7db6e7ba01efa8d6bdc596576ea484d",
        "migrator",
    ),
    "cambiar_estado_desarrollador": (
        "p_email text, p_activo boolean",
        "void",
        {"app.plat_dev_estado", "app.plat_dev_objetivo"},
        "335bfd19dbf3cceb2fd3b618291572cab597483bdb11a96260a96a546db6e2f0",
        "migrator",
    ),
    # Lectura para el login de plataforma (T2): el hash solo para verificar Argon2id en
    # Flask (plan.md §2.3); ninguna otra función de plataforma devuelve un hash.
    "plataforma_buscar_login": (
        "p_email text",
        "TABLE(id uuid, password_hash text, activo boolean)",
        {"app.plat_login_email"},
        "8dd5760702aff6b8b536b0c7b70ad1e609e7d294b5e45d71c51d99ce18124156",
        "app",
    ),
    # Spec 017, T3a (0018): Empresas. Primera comprobación: desarrollador activo (A5).
    "plataforma_listar_tenants": (
        "p_desarrollador uuid",
        "TABLE(id uuid, nombre text, activo boolean, creado_en timestamp with time zone, "
        "tiene_logo boolean, n_membresias_activas bigint, n_admins_activos bigint)",
        {"app.plat_actor", "app.plat_listar"},
        "dc0b0b59c085882317c8c1aedad01a4b3685b90425889a097deda83fca484acd",
        "app",
    ),
    "plataforma_crear_tenant": (
        "p_desarrollador uuid, p_tenant uuid, p_nombre text, p_direccion text, p_nit text, "
        "p_telefono text, p_correo text, p_admin_email text, p_admin_nombre text, "
        "p_password_hash text",
        "TABLE(tenant_id uuid, usuario_id uuid)",
        {"app.plat_actor", "app.plat_tenant_nuevo", "app.plat_usuario_nuevo"},
        "349b292dfa98b4805446e24cf08a912889c4c519083d605c9bf1d0501f7ee455",
        "app",
    ),
    "plataforma_cambiar_estado_tenant": (
        "p_desarrollador uuid, p_tenant uuid, p_activo boolean",
        "boolean",
        {"app.plat_actor", "app.plat_tenant_estado"},
        "a7a49e68ce69f0673ed0ae3c9021b0094d5432fa959e92c9deb225cc1f71d50a",
        "app",
    ),
    # Spec 017, T5 (0027): Usuarios. Sin hash, token ni fecha de alta (no hay columna).
    "plataforma_listar_usuarios": (
        "p_desarrollador uuid, p_tenant uuid",
        "TABLE(usuario_id uuid, nombre text, email text, rol text, activa boolean, "
        "debe_cambiar_password boolean)",
        {"app.plat_actor", "app.plat_usuarios"},
        "5233edc03c6c49b075f5032f15d71be27bbbf71e2ccb9430d712c005f2236f0c",
        "app",
    ),
    # Una fila (estado resultante, si hubo cambio real): solo se audita un cambio real.
    "plataforma_cambiar_estado_membresia": (
        "p_desarrollador uuid, p_tenant uuid, p_usuario uuid, p_activa boolean",
        "TABLE(estado boolean, cambiado boolean)",
        {"app.plat_actor", "app.plat_membresia_tenant", "app.plat_membresia_usuario"},
        "ed0f3c4c7fd3d50b801f21262f51451cc51a6e48acfa31f2a218c2b35e57b836",
        "app",
    ),
    # Spec 017, T6 (0028): Actividad (R32). Solo lectura; los nombres se leen al consultar.
    "plataforma_listar_auditoria": (
        "p_desarrollador uuid, p_tenant uuid, p_accion text, "
        "p_desde timestamp with time zone, p_hasta timestamp with time zone, "
        "p_limite integer, p_cursor_fecha timestamp with time zone, p_cursor_id uuid",
        "TABLE(id uuid, creado_en timestamp with time zone, accion text, resultado text, "
        "desarrollador_nombre text, tenant_id uuid, tenant_nombre text, objeto_id uuid)",
        {"app.plat_actor", "app.plat_actividad"},
        "f9de8c8d1b04c6005052f3b2b7c1ee8563bdf20254272fbebcd2472972336954",
        "app",
    ),
    # Spec 017, T7 (0029): logo en el alta (R23). El archivo lo guarda Flask después.
    # C1 (0030): rehecha; reemplaza el vigente y lo dice (reemplazado).
    "plataforma_registrar_logo": (
        "p_desarrollador uuid, p_tenant uuid, p_logo uuid, p_clave text, p_bytes integer, "
        "p_ancho integer, p_alto integer",
        "TABLE(logo_id uuid, creado boolean, reemplazado boolean)",
        {"app.plat_actor", "app.plat_logo_tenant", "app.plat_logo_id"},
        "d23b450f018dff443586712b4eef295aa1050a3528d922f9d33cfe8b45acebcb",
        "app",
    ),
    # Spec 017, C1 (0030): ficha de la empresa (R41, R42). Ni actualizada_por ni el logo.
    "plataforma_leer_empresa": (
        "p_desarrollador uuid, p_tenant uuid",
        "TABLE(nombre text, direccion text, nit text, telefono text, correo text, "
        "tiene_logo boolean)",
        {"app.plat_actor", "app.plat_empresa_tenant"},
        "fb17d7648304dbc6f77bd6a653c6e401fbaab52d2f8f9fa0261f890dfdc63656",
        "app",
    ),
    "plataforma_actualizar_empresa": (
        "p_desarrollador uuid, p_tenant uuid, p_nombre text, p_direccion text, p_nit text, "
        "p_telefono text, p_correo text",
        "boolean",
        {"app.plat_actor", "app.plat_empresa_tenant"},
        "017a55ac121d5bf9290110b4c0daf8220fa7b86a78341dbbb46a9c9621da22f9",
        "app",
    ),
    # Spec 017, C1/T13 (0031): editar nombre y rol (R47–R51). Ni correo ni hash.
    "plataforma_cambiar_usuario": (
        "p_desarrollador uuid, p_tenant uuid, p_usuario uuid, p_nombre text, p_rol text",
        "TABLE(nombre text, rol text, cambiado boolean, rol_cambiado boolean)",
        {
            "app.plat_actor",
            "app.plat_membresia_tenant",
            "app.plat_membresia_usuario",
            "app.plat_usuario_edicion",
        },
        "af827565d0589f6c6f3bc133ad5f69bbb8e05506652379a6463472f3048b4dd7",
        "app",
    ),
    # Spec 017, C1b/T16 (0032): contraseña temporal (R53–R56). void: ni hash ni contraseña;
    # nunca la GUC de edición de 0031 ni la de membresía-usuario de 0027.
    "plataforma_restablecer_password_usuario": (
        "p_desarrollador uuid, p_tenant uuid, p_usuario uuid, p_password_hash text",
        "void",
        {"app.plat_actor", "app.plat_membresia_tenant", "app.plat_usuario_password"},
        "9431cdfcb1dad4e299d2497a07b16ac2efda6e690f3c13f5dce1594df556cf19",
        "app",
    ),
}
# Funciones que ejecuta el rol de la aplicación (las demás, solo el migrador).
APP_FUNCTIONS = {name for name, spec in EXPECTED_FUNCTIONS.items() if spec[4] == "app"}
OWNER_GUCS_0017 = (
    "app.plat_login_email",
    "app.plat_dev_crear",
    "app.plat_dev_restablecer",
    "app.plat_dev_estado",
    "app.plat_dev_objetivo",
)
OWNER_GUCS_0018 = (
    *OWNER_GUCS_0017,
    "app.plat_actor",
    "app.plat_listar",
    "app.plat_tenant_nuevo",
    "app.plat_usuario_nuevo",
    "app.plat_tenant_estado",
)
# Spec 017, T5 (0027).
USUARIOS_FUNCTIONS = ("plataforma_listar_usuarios", "plataforma_cambiar_estado_membresia")
OWNER_GUCS = (
    *OWNER_GUCS_0018,
    "app.plat_usuarios",
    "app.plat_membresia_tenant",
    "app.plat_membresia_usuario",
)
# Spec 017, T6 (0028).
ACTIVIDAD_FUNCTIONS = ("plataforma_listar_auditoria",)
OWNER_GUCS_0028 = (*OWNER_GUCS, "app.plat_actividad")
# Spec 017, T7 (0029).
LOGO_FUNCTIONS = ("plataforma_registrar_logo",)
OWNER_GUCS_0029 = (*OWNER_GUCS_0028, "app.plat_logo_tenant", "app.plat_logo_id")
# Spec 017, C1 (0030): la de la ficha; la del logo rehecha también la vacía.
EDICION_FUNCTIONS = (
    "plataforma_leer_empresa",
    "plataforma_actualizar_empresa",
    "plataforma_registrar_logo",
)
OWNER_GUCS_0030 = (*OWNER_GUCS_0029, "app.plat_empresa_tenant")
# Spec 017, C1/T13 (0031).
USUARIO_EDICION_FUNCTIONS = ("plataforma_cambiar_usuario",)
OWNER_GUCS_0031 = (*OWNER_GUCS_0030, "app.plat_usuario_edicion")
# Spec 017, C1b/T16 (0032).
PASSWORD_FUNCTIONS = ("plataforma_restablecer_password_usuario",)
OWNER_GUCS_0032 = (*OWNER_GUCS_0031, "app.plat_usuario_password")
# GUC que vacía cada función: la lista completa de plataforma_owner al crearla. Las de 0017
# no conocen las de 0018; no es un hueco: sus cuerpos estáticos no leen tenant, usuario,
# membresia ni empresa, y las políticas nuevas exigen además app.plat_actor de un
# desarrollador activo (precedente: 0004 tampoco vacía las GUC de 0016). Igual con las de
# 0018 y las tres de 0027: cada función de 0027 vacía las suyas al salir y, si falla, el
# SAVEPOINT o la transacción abortada revierten su set_config; y lo que abren (el tenant
# pedido, sus membresías, sus usuarios y los refresh de una membresía) no da a las
# funciones de 0018 nada que no lean ya.
FUNCTION_CLEARS = {
    name: OWNER_GUCS_0032
    if name in PASSWORD_FUNCTIONS
    else OWNER_GUCS_0031
    if name in USUARIO_EDICION_FUNCTIONS
    else OWNER_GUCS_0030
    if name in EDICION_FUNCTIONS
    else OWNER_GUCS_0029
    if name in LOGO_FUNCTIONS
    else OWNER_GUCS_0028
    if name in ACTIVIDAD_FUNCTIONS
    else OWNER_GUCS
    if name in USUARIOS_FUNCTIONS
    else OWNER_GUCS_0018
    if name.startswith("plataforma_") and name != "plataforma_buscar_login"
    else OWNER_GUCS_0017
    for name in EXPECTED_FUNCTIONS
}
# Tablas que puede nombrar el cuerpo de cada función (A4: nada de negocio).
FUNCTION_TABLES = {
    "crear_desarrollador": {"desarrollador", "plataforma_auditoria"},
    "restablecer_desarrollador": {
        "desarrollador",
        "plataforma_refresh_token",
        "plataforma_auditoria",
    },
    "cambiar_estado_desarrollador": {
        "desarrollador",
        "plataforma_refresh_token",
        "plataforma_auditoria",
    },
    "plataforma_buscar_login": {"desarrollador"},
    "plataforma_listar_tenants": {"desarrollador", "tenant", "empresa", "membresia"},
    "plataforma_crear_tenant": {"desarrollador", "tenant", "usuario", "membresia", "empresa"},
    "plataforma_cambiar_estado_tenant": {"desarrollador", "tenant"},
    "plataforma_listar_usuarios": {"desarrollador", "tenant", "membresia", "usuario"},
    "plataforma_cambiar_estado_membresia": {
        "desarrollador",
        "tenant",
        "membresia",
        "refresh_token",
    },
    "plataforma_listar_auditoria": {"desarrollador", "plataforma_auditoria", "tenant"},
    "plataforma_registrar_logo": {
        "desarrollador",
        "tenant",
        "empresa",
        "membresia",
        "empresa_logo",
    },
    "plataforma_leer_empresa": {"desarrollador", "tenant", "empresa"},
    "plataforma_actualizar_empresa": {"desarrollador", "tenant", "empresa"},
    "plataforma_cambiar_usuario": {
        "desarrollador",
        "tenant",
        "membresia",
        "usuario",
        "refresh_token",
    },
    "plataforma_restablecer_password_usuario": {
        "desarrollador",
        "tenant",
        "membresia",
        "usuario",
        "refresh_token",
    },
}
FUNCTION_CALLS = {
    "crear_desarrollador": "select acceso.crear_desarrollador('x@ejemplo.test', 'X', 'h')",
    "restablecer_desarrollador": "select acceso.restablecer_desarrollador('x@ejemplo.test', 'h')",
    "cambiar_estado_desarrollador": (
        "select acceso.cambiar_estado_desarrollador('x@ejemplo.test', false)"
    ),
    "plataforma_buscar_login": "select * from acceso.plataforma_buscar_login('x@ejemplo.test')",
    "plataforma_listar_tenants": (
        "select * from acceso.plataforma_listar_tenants('00000000-0000-4000-8000-00000000f001')"
    ),
    "plataforma_crear_tenant": (
        "select * from acceso.plataforma_crear_tenant('00000000-0000-4000-8000-00000000f001', "
        "'00000000-0000-4000-8000-00000000f002', 'X', 'Y', '', '', '', "
        "'x@ejemplo.test', 'X', 'h')"
    ),
    "plataforma_cambiar_estado_tenant": (
        "select acceso.plataforma_cambiar_estado_tenant('00000000-0000-4000-8000-00000000f001', "
        "'00000000-0000-4000-8000-00000000f002', false)"
    ),
    "plataforma_listar_usuarios": (
        "select * from acceso.plataforma_listar_usuarios('00000000-0000-4000-8000-00000000f001', "
        "'00000000-0000-4000-8000-00000000f002')"
    ),
    "plataforma_cambiar_estado_membresia": (
        "select acceso.plataforma_cambiar_estado_membresia("
        "'00000000-0000-4000-8000-00000000f001', '00000000-0000-4000-8000-00000000f002', "
        "'00000000-0000-4000-8000-00000000f003', false)"
    ),
    "plataforma_listar_auditoria": (
        "select * from acceso.plataforma_listar_auditoria("
        "'00000000-0000-4000-8000-00000000f001', '00000000-0000-0000-0000-000000000000', '', "
        "'-infinity', 'infinity', 50, 'infinity', 'ffffffff-ffff-ffff-ffff-ffffffffffff')"
    ),
    "plataforma_registrar_logo": (
        "select * from acceso.plataforma_registrar_logo("
        "'00000000-0000-4000-8000-00000000f001', '00000000-0000-4000-8000-00000000f002', "
        "'00000000-0000-4000-8000-00000000f003', 'x', 1, 1, 1)"
    ),
    "plataforma_leer_empresa": (
        "select * from acceso.plataforma_leer_empresa("
        "'00000000-0000-4000-8000-00000000f001', '00000000-0000-4000-8000-00000000f002')"
    ),
    "plataforma_actualizar_empresa": (
        "select acceso.plataforma_actualizar_empresa("
        "'00000000-0000-4000-8000-00000000f001', '00000000-0000-4000-8000-00000000f002', "
        "'X', 'Y', '', '', '')"
    ),
    "plataforma_cambiar_usuario": (
        "select * from acceso.plataforma_cambiar_usuario("
        "'00000000-0000-4000-8000-00000000f001', '00000000-0000-4000-8000-00000000f002', "
        "'00000000-0000-4000-8000-00000000f003', 'X', 'contador')"
    ),
    "plataforma_restablecer_password_usuario": (
        "select acceso.plataforma_restablecer_password_usuario("
        "'00000000-0000-4000-8000-00000000f001', '00000000-0000-4000-8000-00000000f002', "
        "'00000000-0000-4000-8000-00000000f003', 'h')"
    ),
}
TABLE_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
COLUMN_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "REFERENCES")

HASHER = argon2.PasswordHasher.from_parameters(ARGON2_TEST_PARAMS)


@dataclass(frozen=True)
class PlataformaDb:
    url: URL
    app_role: str
    migrator: str
    superuser: Engine  # migrador superusuario: ve todas las filas bajo FORCE RLS
    app: Engine


def _fail(message: str) -> None:
    pytest.fail(message, pytrace=False)


def _alembic_config() -> AlembicConfig:
    config = AlembicConfig(str(ALEMBIC_INI))
    config.attributes["configure_logger"] = False
    return config


@pytest.fixture(scope="module")
def db(database_residue_guard) -> Iterator[PlataformaDb]:
    """Base temporal en ``head`` con los roles de Supabase; se borra al terminar."""
    migrator_url = read_database_url("TEST_MIGRATION_DATABASE_URL")
    app_url = read_database_url("TEST_DATABASE_URL")
    if migrator_url is None or app_url is None or not app_url.username:
        _fail(BLOCKED)
    name = f"assetcontrol_plataforma_{uuid.uuid4().hex[:12]}"
    admin = create_engine(migrator_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    created_roles: list[str] = []
    failure = None
    try:
        with admin.connect() as conn:
            if not role_sees_all_rows(conn):
                failure = "bloqueado: el rol migrador debe ser superusuario para verificar"
            else:
                conn.execute(text(f'CREATE DATABASE "{name}"'))
                for role in SUPABASE_ROLES:
                    exists = conn.scalar(
                        text("select exists (select 1 from pg_roles where rolname = :r)"),
                        {"r": role},
                    )
                    if not exists:
                        conn.execute(text(f'CREATE ROLE "{role}" NOLOGIN'))
                        created_roles.append(role)
    except SQLAlchemyError as exc:
        failure = f"bloqueado: el rol migrador no pudo preparar la base ({type(exc).__name__})"
    if failure is not None:
        admin.dispose()
        _fail(failure)

    url = migrator_url.set(database=name)
    engines: list[Engine] = []
    try:
        setup = create_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
        try:
            with setup.connect() as conn:
                for role in SUPABASE_ROLES:
                    conn.execute(
                        text(
                            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                            f'GRANT ALL ON TABLES TO "{role}"'
                        )
                    )
                    conn.execute(
                        text(f'ALTER DEFAULT PRIVILEGES GRANT EXECUTE ON FUNCTIONS TO "{role}"')
                    )
        finally:
            setup.dispose()
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("MIGRATION_DATABASE_URL", url.render_as_string(hide_password=False))
            mp.delenv("DATABASE_URL", raising=False)
            mp.setenv("APP_DB_USER", app_url.username)
            command.upgrade(_alembic_config(), "head")
        superuser = create_engine(url, poolclass=NullPool)
        app = create_engine(app_url.set(database=name), poolclass=NullPool)
        engines += [superuser, app]
        yield PlataformaDb(
            url=url,
            app_role=app_url.username,
            migrator=migrator_url.username,
            superuser=superuser,
            app=app,
        )
    finally:
        for engine in engines:
            engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            for role in created_roles:
                conn.execute(text(f'DROP ROLE IF EXISTS "{role}"'))
        admin.dispose()


@pytest.fixture
def conn(db) -> Iterator[Connection]:
    with db.superuser.connect() as connection:
        yield connection


# --- Utilidades de catálogo --------------------------------------------------------


def _normalize(expression: str | None) -> str | None:
    return None if expression is None else " ".join(expression.split())


def _policies(conn: Connection) -> dict[tuple[str, str], tuple]:
    rows = conn.execute(
        text(
            "select tablename, policyname, permissive, cmd, roles::text, qual, with_check "
            "from pg_policies where schemaname = 'public' "
            "and (tablename = any(:t) or roles::text = :owner)"
        ),
        {"t": list(PLATFORM_TABLES), "owner": "{" + OWNER + "}"},
    )
    return {
        (r[0], r[1]): (r[2], r[3], r[4].strip("{}"), _normalize(r[5]), _normalize(r[6]))
        for r in rows
    }


def _columns(conn: Connection, table: str) -> dict[str, tuple[str, bool]]:
    rows = conn.execute(
        text(
            "select column_name, data_type, is_nullable from information_schema.columns "
            "where table_schema = 'public' and table_name = :t"
        ),
        {"t": table},
    )
    return {r[0]: (r[1], r[2] == "NO") for r in rows}


def _public_tables(conn: Connection) -> set[str]:
    return set(
        conn.scalars(
            text(
                "select c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace "
                "where n.nspname = 'public' and c.relkind in ('r', 'p')"
            )
        )
    )


def _acl_table_privileges(conn: Connection, role: str, table: str) -> set[str]:
    return set(
        conn.scalars(
            text(
                "select a.privilege_type from pg_class c "
                "join pg_namespace n on n.oid = c.relnamespace "
                "cross join lateral aclexplode(c.relacl) a "
                "where n.nspname = 'public' and c.relname = :t "
                "and a.grantee = (select oid from pg_roles where rolname = :r)"
            ),
            {"t": table, "r": role},
        )
    )


def _column_privileges(conn: Connection, role: str, table: str) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for privilege in COLUMN_PRIVILEGES:
        cols = {
            column
            for column in _columns(conn, table)
            if conn.scalar(
                text("select has_column_privilege(:r, :t, :c, :p)"),
                {"r": role, "t": f"public.{table}", "c": column, "p": privilege},
            )
        }
        if cols:
            result[privilege] = cols
    return result


def _functions(conn: Connection) -> dict[str, dict[str, object]]:
    rows = conn.execute(
        text(
            "select p.proname, pg_get_function_identity_arguments(p.oid), "
            "pg_get_function_result(p.oid), p.prosecdef, p.proisstrict, l.lanname, "
            "p.provolatile, pg_get_userbyid(p.proowner), p.proconfig, p.prosrc, p.prokind "
            "from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
            "join pg_language l on l.oid = p.prolang "
            "where n.nspname = 'acceso' and pg_get_userbyid(p.proowner) <> :auth"
        ),
        {"auth": AUTH_OWNER},
    ).all()
    keys = ("args", "result", "secdef", "strict", "lang", "volatile", "owner", "config", "src")
    return {row[0]: dict(zip(keys + ("kind",), row[1:], strict=True)) for row in rows}


def _function_acl(conn: Connection, name: str) -> set[tuple[str, str, str, bool]]:
    rows = conn.execute(
        text(
            "select case when a.grantee = 0 then 'PUBLIC' else pg_get_userbyid(a.grantee) end, "
            "pg_get_userbyid(a.grantor), a.privilege_type, a.is_grantable "
            "from pg_proc p join pg_namespace n on n.oid = p.pronamespace "
            "cross join lateral aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a "
            "where n.nspname = 'acceso' and p.proname = :n"
        ),
        {"n": name},
    ).all()
    return {tuple(row) for row in rows}


def _expect_error(connection: Connection, sql: str, params: dict, sqlstate: str) -> str:
    nested = connection.begin_nested()
    with pytest.raises(DBAPIError) as excinfo:
        connection.execute(text(sql), params)
    nested.rollback()
    assert getattr(excinfo.value.orig, "sqlstate", None) == sqlstate, str(excinfo.value.orig)
    return str(excinfo.value.orig)


def _as_developer(connection: Connection, desarrollador_id: uuid.UUID | str) -> None:
    connection.execute(
        text("select set_config('app.desarrollador_id', :d, true)"), {"d": str(desarrollador_id)}
    )


def _email(prefix: str = "dev") -> str:
    return f"{prefix}.{uuid.uuid4().hex[:10]}@ejemplo.test"


def _new_developer(db: PlataformaDb, *, activo: bool = True) -> tuple[uuid.UUID, str]:
    """Desarrollador sembrado por el superusuario (sin pasar por las funciones)."""
    desarrollador_id, email = uuid.uuid4(), _email()
    with db.superuser.begin() as connection:
        connection.execute(
            text(
                "insert into desarrollador (id, email, nombre, password_hash, activo) "
                "values (:id, :e, 'Dev sintético', :h, :a)"
            ),
            {"id": desarrollador_id, "e": email, "h": HASHER.hash("x" * 16), "a": activo},
        )
    return desarrollador_id, email


def _new_refresh(db: PlataformaDb, desarrollador_id: uuid.UUID) -> uuid.UUID:
    token_id = uuid.uuid4()
    with db.superuser.begin() as connection:
        connection.execute(
            text(
                "insert into plataforma_refresh_token "
                "(id, desarrollador_id, familia_id, token_hash, expira_en) "
                "values (:id, :d, :f, :h, :e)"
            ),
            {
                "id": token_id,
                "d": desarrollador_id,
                "f": uuid.uuid4(),
                "h": secrets.token_bytes(32),
                "e": datetime.now(UTC) + timedelta(hours=8),
            },
        )
    return token_id


def _audit_rows(db: PlataformaDb, objeto_id: uuid.UUID) -> list[dict]:
    with db.superuser.connect() as connection:
        return [
            dict(r)
            for r in connection.execute(
                text(
                    "select desarrollador_id, accion, resultado, tenant_id, objeto_id "
                    "from plataforma_auditoria where objeto_id = :o order by creado_en, accion"
                ),
                {"o": objeto_id},
            ).mappings()
        ]


def _counts(db: PlataformaDb) -> dict[str, int]:
    with db.superuser.connect() as connection:
        return {
            table: connection.scalar(text(f"select count(*) from {table}"))  # noqa: S608
            for table in PLATFORM_TABLES
        }


def _revoked(db: PlataformaDb, token_id: uuid.UUID) -> bool:
    with db.superuser.connect() as connection:
        return (
            connection.scalar(
                text("select revocado_en from plataforma_refresh_token where id = :i"),
                {"i": token_id},
            )
            is not None
        )


# --- Tablas, columnas y claves --------------------------------------------------------


@pytest.mark.parametrize("table", PLATFORM_TABLES)
def test_platform_tables_columns_and_constraints(conn, table):
    assert _columns(conn, table) == EXPECTED_COLUMNS[table]
    constraints = set(
        conn.scalars(
            text(
                "select pg_get_constraintdef(oid) from pg_constraint "
                "where conrelid = to_regclass(:t) and contype in ('c', 'u', 'f', 'p')"
            ),
            {"t": f"public.{table}"},
        )
    )
    assert constraints == EXPECTED_CONSTRAINTS[table]


@pytest.mark.parametrize("table", PLATFORM_TABLES)
def test_platform_tables_have_rls_enabled_and_forced(conn, table):
    flags = conn.execute(
        text(
            "select c.relrowsecurity, c.relforcerowsecurity from pg_class c "
            "where c.oid = to_regclass(:t)"
        ),
        {"t": f"public.{table}"},
    ).one()
    assert tuple(flags) == (True, True)


def test_platform_tables_are_owned_by_the_migrator(conn, db):
    for table in PLATFORM_TABLES:
        owner = conn.scalar(
            text("select pg_get_userbyid(relowner) from pg_class where oid = to_regclass(:t)"),
            {"t": f"public.{table}"},
        )
        assert owner == db.migrator, table


def test_auditoria_actions_are_the_closed_list_of_r33(conn):
    check = conn.scalar(
        text(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conname = 'plataforma_auditoria_accion_valida'"
        )
    )
    assert re.findall(r"'(\w+)'::text", check) == ACCIONES


def test_auditoria_has_no_personal_data_columns(conn):
    # R34: sin correos, nombres, IP, texto libre ni hashes.
    assert set(_columns(conn, "plataforma_auditoria")) == {
        "id",
        "desarrollador_id",
        "accion",
        "resultado",
        "tenant_id",
        "objeto_id",
        "creado_en",
    }


def test_auditoria_and_refresh_indexes(conn):
    def indexes(table: str) -> set[str]:
        return {
            re.sub(r"^.* USING btree ", "", definition)
            for definition in conn.scalars(
                text(
                    "select indexdef from pg_indexes where schemaname = 'public' and tablename = :t"
                ),
                {"t": table},
            )
        }

    assert indexes("plataforma_auditoria") == {
        "(id)",
        "(creado_en DESC, id DESC)",
        "(tenant_id, creado_en DESC)",
        "(accion, creado_en DESC)",
    }
    assert indexes("plataforma_refresh_token") == {
        "(id)",
        "(token_hash)",
        "(familia_id)",
        "(desarrollador_id)",
    }


def test_tenant_activo_columns_and_checks(conn):
    columns = _columns(conn, "tenant")
    assert {k: columns[k] for k in ("activo", "desactivado_en", "desactivado_por")} == {
        "activo": ("boolean", True),
        "desactivado_en": (TS, False),
        "desactivado_por": ("uuid", False),
    }
    default = conn.scalar(
        text(
            "select column_default from information_schema.columns "
            "where table_name = 'tenant' and column_name = 'activo'"
        )
    )
    assert default == "true"
    constraints = set(
        conn.scalars(
            text(
                "select pg_get_constraintdef(oid) from pg_constraint "
                "where conrelid = 'tenant'::regclass"
            )
        )
    )
    assert constraints == {
        "PRIMARY KEY (id)",
        "CHECK ((activo = (desactivado_en IS NULL)))",
        "CHECK (((NOT activo) OR (desactivado_por IS NULL)))",
        "FOREIGN KEY (desactivado_por) REFERENCES desarrollador(id)",
    }


def test_tenant_activo_check_keeps_state_and_date_together(db):
    with db.superuser.connect() as connection:
        tx = connection.begin()
        try:
            tenant_id = uuid.uuid4()
            connection.execute(
                text("insert into tenant (id, nombre) values (:i, 'Clínica sintética')"),
                {"i": tenant_id},
            )
            assert (
                connection.scalar(text("select activo from tenant where id = :i"), {"i": tenant_id})
                is True
            )
            for sql in (
                "update tenant set activo = false where id = :i",
                "update tenant set desactivado_en = now() where id = :i",
            ):
                _expect_error(connection, sql, {"i": tenant_id}, "23514")
            connection.execute(
                text("update tenant set activo = false, desactivado_en = now() where id = :i"),
                {"i": tenant_id},
            )
        finally:
            tx.rollback()


def test_usuario_debe_cambiar_password_defaults_to_false(conn):
    assert _columns(conn, "usuario")["debe_cambiar_password"] == ("boolean", True)
    default = conn.scalar(
        text(
            "select column_default from information_schema.columns "
            "where table_name = 'usuario' and column_name = 'debe_cambiar_password'"
        )
    )
    assert default == "false"


def test_limite_tasa_accepts_the_platform_login_scopes(conn):
    check = conn.scalar(
        text(
            "select pg_get_constraintdef(oid) from pg_constraint "
            "where conname = 'limite_tasa_ambito_check'"
        )
    )
    scopes = re.findall(r"'(\w+)'::text", check)
    # Spec 017, T4 (0025): después, las acciones y el refresh de plataforma (O1).
    assert scopes[-4:] == ["plat_login_ip", "plat_login_cuenta", "plat_accion", "plat_refresh_ip"]
    assert len(scopes) == 12


# --- Políticas ------------------------------------------------------------------------


def test_platform_policies_are_a_closed_list_with_exact_text(conn, db):
    expected = {
        key: (permissive, cmd, db.app_role if roles == "app" else roles, qual, check)
        for key, (permissive, cmd, roles, qual, check) in EXPECTED_POLICIES.items()
    }
    assert _policies(conn) == expected


def test_owner_policies_are_never_for_all_nor_public(conn):
    for key, (_, cmd, roles, _, _) in _policies(conn).items():
        assert cmd != "ALL", key
        assert roles != "public", key


def test_platform_owner_policies_only_touch_platform_and_listed_tables(conn):
    # Spec 017, T3a (0018): además, tenant, usuario, membresia y empresa (nada de negocio:
    # ni activos, verificaciones, sesiones, ubicaciones, categorías, fotos ni informes).
    tables = {table for (table, _), value in _policies(conn).items() if value[2] == OWNER}
    assert tables == set(PLATFORM_TABLES) | set(OWNER_BUSINESS_TABLES)


# --- GRANT --------------------------------------------------------------------------


@pytest.mark.parametrize("table", PLATFORM_TABLES)
def test_app_privileges_on_platform_tables_are_exact(conn, db, table):
    assert _column_privileges(conn, db.app_role, table) == EXPECTED_APP_COLUMNS[table]
    assert _acl_table_privileges(conn, db.app_role, table) == EXPECTED_APP_TABLE_PRIVILEGES[table]


def test_app_never_reads_the_developer_password_hash(conn, db):
    assert not conn.scalar(
        text("select has_column_privilege(:r, 'public.desarrollador', 'password_hash', 'SELECT')"),
        {"r": db.app_role},
    )


def test_platform_owner_privileges_are_exactly_its_column_grants(conn):
    for table in _public_tables(conn):
        assert _acl_table_privileges(conn, OWNER, table) == set(), table
        expected = EXPECTED_OWNER_COLUMNS.get(table, {})
        assert _column_privileges(conn, OWNER, table) == expected, table


def test_nobody_but_the_owner_can_delete_platform_rows(conn, db):
    for role in (db.app_role, OWNER, AUTH_OWNER, *SUPABASE_ROLES):
        for table in PLATFORM_TABLES:
            for privilege in ("DELETE", "TRUNCATE"):
                assert not conn.scalar(
                    text("select has_table_privilege(:r, :t, :p)"),
                    {"r": role, "t": f"public.{table}", "p": privilege},
                ), (role, table, privilege)


def test_supabase_roles_receive_nothing_on_platform_tables(conn):
    for role in SUPABASE_ROLES:
        for table in PLATFORM_TABLES:
            assert _acl_table_privileges(conn, role, table) == set(), (role, table)
            assert _column_privileges(conn, role, table) == {}, (role, table)


# --- plataforma_owner ------------------------------------------------------------------


def test_platform_owner_is_inert_and_has_no_memberships(conn, db):
    row = conn.execute(
        text(
            "select rolsuper, rolbypassrls, rolcanlogin, rolcreaterole, rolcreatedb, "
            "rolreplication from pg_roles where rolname = :r"
        ),
        {"r": OWNER},
    ).one()
    assert tuple(row) == (False, False, False, False, False, False)
    members = conn.scalar(
        text(
            "select count(*) from pg_auth_members m "
            "join pg_roles r on r.oid in (m.roleid, m.member) "
            "where r.rolname = :r"
        ),
        {"r": OWNER},
    )
    assert members == 0
    for member, role in ((db.app_role, OWNER), (OWNER, db.app_role), (OWNER, AUTH_OWNER)):
        assert not conn.scalar(
            text("select pg_has_role(:m, :r, 'MEMBER')"), {"m": member, "r": role}
        ), (member, role)


def test_platform_owner_has_usage_but_no_create_on_acceso(conn):
    assert conn.scalar(text("select has_schema_privilege(:r, 'acceso', 'USAGE')"), {"r": OWNER})
    assert not conn.scalar(
        text("select has_schema_privilege(:r, 'acceso', 'CREATE')"), {"r": OWNER}
    )
    assert not conn.scalar(
        text("select has_schema_privilege(:r, 'public', 'CREATE')"), {"r": OWNER}
    )
    assert not conn.scalar(
        text("select has_database_privilege(:r, current_database(), 'CREATE')"), {"r": OWNER}
    )


# --- Funciones (A4) ----------------------------------------------------------------------


def test_platform_functions_are_a_closed_list(conn):
    assert set(_functions(conn)) == set(EXPECTED_FUNCTIONS)


@pytest.mark.parametrize("name", sorted(EXPECTED_FUNCTIONS))
def test_platform_function_signature_and_attributes(conn, name):
    function = _functions(conn)[name]
    args, result, _, _, _ = EXPECTED_FUNCTIONS[name]
    assert (function["args"], function["result"]) == (args, result)
    assert function["kind"] == "f"
    assert function["secdef"] is True
    assert function["strict"] is True
    assert function["lang"] == "plpgsql"
    assert function["volatile"] == "v"
    assert function["owner"] == OWNER
    assert function["config"] == FUNCTION_CONFIG.get(name, SEARCH_PATH)


@pytest.mark.parametrize("name", sorted(EXPECTED_FUNCTIONS))
def test_platform_function_acl_is_exact(conn, db, name):
    grantee = {"app": db.app_role, "migrator": db.migrator}[EXPECTED_FUNCTIONS[name][4]]
    assert _function_acl(conn, name) == {
        (OWNER, OWNER, "EXECUTE", False),
        (grantee, OWNER, "EXECUTE", False),
    }


@pytest.mark.parametrize("name", sorted(EXPECTED_FUNCTIONS))
def test_platform_function_body_is_exactly_the_reviewed_one(conn, name):
    source = _functions(conn)[name]["src"]
    assert hashlib.sha256(source.encode()).hexdigest() == EXPECTED_FUNCTIONS[name][3]


_RELATION_REFERENCE = re.compile(r"\b(?:FROM|JOIN|UPDATE|INTO)\s+([A-Za-z_][\w]*)(\.)?", re.I)


@pytest.mark.parametrize("name", sorted(EXPECTED_FUNCTIONS))
def test_platform_function_body_is_static_qualified_and_reads_no_guc(conn, name):
    source = _functions(conn)[name]["src"]
    lowered = source.lower()
    assert "current_setting" not in lowered
    assert re.search(r"\bexecute\b", lowered) is None
    assert "format(" not in lowered
    for match in _RELATION_REFERENCE.finditer(source):
        word, qualified = match.group(1), match.group(2)
        if qualified:
            assert word in ("public", "pg_catalog"), match.group(0)
        else:
            assert word.startswith("v_"), match.group(0)
    for guc in EXPECTED_FUNCTIONS[name][2]:
        assert f"pg_catalog.set_config('{guc}'," in source, guc
    assert source.count("pg_catalog.set_config(g, '', true)") >= 2
    for guc in FUNCTION_CLEARS[name]:
        assert f"'{guc}'" in source, guc  # la lista que vacía es la completa


@pytest.mark.parametrize("name", sorted(EXPECTED_FUNCTIONS))
def test_platform_function_body_names_only_its_tables(conn, name):
    source = _functions(conn)[name]["src"]
    tables = set(re.findall(r"\bpublic\.([a-z_]+)", source))
    assert tables == FUNCTION_TABLES[name]


# Conservadora: cualquier «nombre» en la sentencia (también «SET (nombre, ...) =» o un WHERE).
_RENAMES_TENANT = re.compile(r"\bUPDATE\s+public\.tenant\b[^;]*?\bSET\b[^;]*?\bnombre\b", re.I)


def test_only_actualizar_empresa_renames_a_tenant(conn):
    """Spec 017, C1 (T12): ``plataforma_owner`` tiene UPDATE (nombre) en ``tenant`` y la
    política de ``app.plat_tenant_estado`` (0018) no restringe columnas (límite conocido,
    RC10). Que solo ``plataforma_actualizar_empresa`` escriba ``nombre`` lo garantiza el
    cuerpo de cada función: una función nueva (T13/T16) que lo haga rompe esta prueba."""
    functions = _functions(conn)
    renombran = {name for name, f in functions.items() if _RENAMES_TENANT.search(str(f["src"]))}
    assert renombran == {"plataforma_actualizar_empresa"}
    estado = str(functions["plataforma_cambiar_estado_tenant"]["src"])
    assert "UPDATE public.tenant" in estado  # sí escribe el tenant, pero no su nombre
    assert _RENAMES_TENANT.search(estado) is None


# Spec 017, C1/T13 y C1b/T16 (RC10): los privilegios por columna del dueño sobre usuario
# (UPDATE de nombre desde 0031; de password_hash, debe_cambiar_password y
# sesiones_validas_desde desde 0032) y sobre membresia (rol) ensanchan todas sus políticas
# UPDATE de la misma tabla: con las GUC de 0031, la RLS dejaría escribir también el hash y
# las marcas; con la de 0032, el nombre (solo junto con la marca y el corte, por su WITH
# CHECK); la de 0027 sobre membresia dejaría cambiar el rol. Lo contiene que cada función
# escriba exactamente sus columnas: esta aserción fija, por función, qué columnas de
# usuario pone en el SET de su UPDATE (una función nueva que actualice usuario, o una
# columna más, rompe la prueba).
_CHANGES_ROLE = re.compile(r"\bUPDATE\s+public\.membresia\b[^;]*?\bSET\b[^;]*?\brol\b", re.I)
_UPDATE_USER = re.compile(
    r"\bUPDATE\s+public\.usuario\s+AS\s+u\s+SET\s+(?P<set>.*?)\s+WHERE\b", re.I | re.S
)
_SET_COLUMN = re.compile(r"(?:^|,)\s*([a-z_]+)\s*=", re.I)
USER_COLUMNS_WRITTEN = {
    "plataforma_cambiar_usuario": {"nombre"},
    "plataforma_restablecer_password_usuario": {
        "password_hash",
        "debe_cambiar_password",
        "sesiones_validas_desde",
    },
}


def _user_columns_written(source: str) -> set[str]:
    return {
        column
        for match in _UPDATE_USER.finditer(source)
        for column in _SET_COLUMN.findall(match.group("set"))
    }


def test_only_cambiar_usuario_renames_a_user_or_changes_a_role(conn):
    functions = _functions(conn)
    # Ninguna función del dueño de plataforma actualiza usuario salvo estas dos, y cada una
    # solo sus columnas (cualquier «UPDATE public.usuario» cuenta, también sin alias).
    writers = {
        name: _user_columns_written(str(f["src"]))
        for name, f in functions.items()
        if re.search(r"\bUPDATE\s+public\.usuario\b", str(f["src"]), re.I)
    }
    assert writers == USER_COLUMNS_WRITTEN
    for name in USER_COLUMNS_WRITTEN:
        cuerpo = str(functions[name]["src"])
        assert len(re.findall(r"\bUPDATE\s+public\.usuario\b", cuerpo, re.I)) == len(
            _UPDATE_USER.findall(cuerpo)
        ), name
    # El rol solo lo cambia la edición de T13.
    roles = {n for n, f in functions.items() if _CHANGES_ROLE.search(str(f["src"]))}
    assert roles == {"plataforma_cambiar_usuario"}
    # La edición (T13) no menciona nada de la contraseña ni del correo; la contraseña
    # temporal (T16) no menciona el nombre, el correo, el estado ni el rol, y nunca lee el
    # hash (lo recibe y lo escribe; no hay «password_hash» fuera de su SET y su validación).
    edicion = str(functions["plataforma_cambiar_usuario"]["src"])
    for columna in ("email", "password_hash", "debe_cambiar_password", "sesiones_validas_desde"):
        assert re.search(rf"\b{columna}\b", edicion) is None, columna
    assert "SET activa" not in edicion
    password = str(functions["plataforma_restablecer_password_usuario"]["src"])
    for prohibido in (r"\bemail\b", r"\bnombre\b", r"\bactivo\s*=", r"\bactiva\b", r"\brol\b"):
        assert re.search(prohibido, password) is None, prohibido
    assert re.search(r"\bu\.password_hash\b", password) is None
    assert re.search(r"SELECT[^;]*\bpassword_hash\b", password, re.I) is None
    estado = str(functions["plataforma_cambiar_estado_membresia"]["src"])
    assert _CHANGES_ROLE.search(estado) is None


def test_only_restablecer_password_writes_a_password_or_cuts_the_sessions(conn):
    # Spec 017, C1b/T16 (RC9): de las funciones de plataforma_owner, solo la de la
    # contraseña temporal escribe usuario.password_hash (la de alta lo inserta) y fija
    # sesiones_validas_desde; ninguna función del dueño lo lee.
    functions = _functions(conn)
    for columna in ("password_hash", "sesiones_validas_desde", "debe_cambiar_password"):
        escriben = {
            name for name, f in functions.items() if columna in _user_columns_written(str(f["src"]))
        }
        assert escriben == {"plataforma_restablecer_password_usuario"}, columna


@pytest.mark.parametrize(
    "name",
    sorted(n for n in EXPECTED_FUNCTIONS if n.startswith("plataforma_") and "login" not in n),
)
def test_empresas_functions_check_the_developer_first(conn, name):
    # A5/R36: lo primero tras vaciar las GUC es comprobar que quien llama está activo.
    source = _functions(conn)[name]["src"]
    check = source.index("'desarrollador_no_autorizado'")
    for statement in ("INSERT", "UPDATE", "RETURN QUERY", "public.tenant", "public.empresa"):
        if statement in source:
            assert source.index(statement) > check, statement


def test_only_the_login_function_returns_a_hash(conn):
    for name, function in _functions(conn).items():
        result = str(function["result"])
        if name == "plataforma_buscar_login":
            assert "password_hash" in result
        else:
            assert "hash" not in result, name


def test_app_executes_only_the_login_and_empresas_functions(conn, db):
    assert APP_FUNCTIONS == {
        "plataforma_buscar_login",
        "plataforma_listar_tenants",
        "plataforma_crear_tenant",
        "plataforma_cambiar_estado_tenant",
        "plataforma_listar_usuarios",
        "plataforma_cambiar_estado_membresia",
        "plataforma_listar_auditoria",
        "plataforma_registrar_logo",
        "plataforma_leer_empresa",
        "plataforma_actualizar_empresa",
        "plataforma_cambiar_usuario",
        "plataforma_restablecer_password_usuario",
    }
    for name, (args, *_rest) in EXPECTED_FUNCTIONS.items():
        signature = f"acceso.{name}({', '.join(a.split(' ', 1)[1] for a in args.split(', '))})"
        allowed = conn.scalar(
            text("select has_function_privilege(:r, :f, 'EXECUTE')"),
            {"r": db.app_role, "f": signature},
        )
        assert allowed is (name in APP_FUNCTIONS), name


@pytest.mark.parametrize("role", SUPABASE_ROLES)
@pytest.mark.parametrize("name", sorted(EXPECTED_FUNCTIONS))
def test_supabase_roles_cannot_execute_platform_functions(db, role, name):
    with db.superuser.connect() as connection:
        for with_usage in (False, True):
            tx = connection.begin()
            try:
                if with_usage:
                    connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA acceso TO "{role}"')
                connection.exec_driver_sql(f'SET LOCAL ROLE "{role}"')
                with pytest.raises(DBAPIError) as excinfo:
                    connection.execute(text(FUNCTION_CALLS[name]))
            finally:
                tx.rollback()
            assert excinfo.value.orig.sqlstate == INSUFFICIENT_PRIVILEGE


# --- Rol de la aplicación sobre las tablas nuevas (A6, A10) ------------------------------


def test_without_developer_the_app_sees_no_platform_rows(db):
    desarrollador_id, _ = _new_developer(db)
    _new_refresh(db, desarrollador_id)
    with db.app.connect() as connection:
        tx = connection.begin()
        try:
            # Sin GUC y con un tenant fijado (tenant_session): cero filas (R37).
            for tenant in (None, str(uuid.uuid4())):
                if tenant is not None:
                    connection.execute(
                        text("select set_config('app.tenant_id', :t, true)"), {"t": tenant}
                    )
                assert connection.scalar(text("select count(id) from desarrollador")) == 0
                assert connection.scalar(text("select count(*) from plataforma_refresh_token")) == 0
                assert connection.scalar(text("select count(*) from plataforma_auditoria")) == 0
        finally:
            tx.rollback()


def test_with_a_developer_the_app_sees_only_its_own_rows(db):
    propio, _ = _new_developer(db)
    ajeno, _ = _new_developer(db)
    _new_refresh(db, propio)
    _new_refresh(db, ajeno)
    with db.app.connect() as connection:
        tx = connection.begin()
        try:
            _as_developer(connection, propio)
            ids = connection.scalars(text("select id from desarrollador")).all()
            assert ids == [propio]
            owners = set(
                connection.scalars(text("select desarrollador_id from plataforma_refresh_token"))
            )
            assert owners == {propio}
            _expect_error(
                connection,
                "select password_hash from desarrollador",
                {},
                INSUFFICIENT_PRIVILEGE,
            )
        finally:
            tx.rollback()


def test_with_a_developer_the_app_reads_no_business_rows(db):
    desarrollador_id, _ = _new_developer(db)
    with db.superuser.begin() as connection:
        connection.execute(
            text("insert into tenant (id, nombre) values (:i, 'Clínica sintética P')"),
            {"i": uuid.uuid4()},
        )
    with db.app.connect() as connection:
        tx = connection.begin()
        try:
            _as_developer(connection, desarrollador_id)
            for table in ("tenant", "membresia", "activo", "ubicacion", "categoria", "empresa"):
                count = connection.scalar(text(f"select count(*) from {table}"))  # noqa: S608
                assert count == 0, table
        finally:
            tx.rollback()


def test_app_cannot_write_developers_directly(db):
    desarrollador_id, _ = _new_developer(db)
    with db.app.connect() as connection:
        tx = connection.begin()
        try:
            _as_developer(connection, desarrollador_id)
            for sql in (
                "insert into desarrollador (email, nombre, password_hash) "
                "values ('x@ejemplo.test', 'X', 'h')",
                "update desarrollador set activo = true",
                "update desarrollador set password_hash = 'h'",
                "delete from desarrollador",
            ):
                _expect_error(connection, sql, {}, INSUFFICIENT_PRIVILEGE)
        finally:
            tx.rollback()


def test_app_refresh_tokens_are_bound_to_its_developer(db):
    propio, _ = _new_developer(db)
    ajeno, _ = _new_developer(db)
    params = {
        "f": uuid.uuid4(),
        "h": secrets.token_bytes(32),
        "e": datetime.now(UTC) + timedelta(hours=8),
    }
    sql = (
        "insert into plataforma_refresh_token "
        "(desarrollador_id, familia_id, token_hash, expira_en) "
        "values (:d, :f, :h, :e)"
    )
    with db.app.connect() as connection:
        tx = connection.begin()
        try:
            _as_developer(connection, propio)
            connection.execute(text(sql), {**params, "d": propio})
            _expect_error(
                connection, sql, {**params, "d": ajeno, "h": secrets.token_bytes(32)}, "42501"
            )
            _expect_error(connection, "delete from plataforma_refresh_token", {}, "42501")
        finally:
            tx.rollback()


def test_audit_is_insert_and_select_only_for_an_active_developer(db):
    activo, _ = _new_developer(db)
    inactivo, _ = _new_developer(db, activo=False)
    # Spec 017, T3a (0018): login_ok lleva como objeto al propio desarrollador.
    sql = (
        "insert into plataforma_auditoria (desarrollador_id, accion, resultado, objeto_id) "
        "values (:d, 'login_ok', 'ok', :d)"
    )
    with db.app.connect() as connection:
        tx = connection.begin()
        try:
            _as_developer(connection, activo)
            connection.execute(text(sql), {"d": activo})
            assert connection.scalar(text("select count(*) from plataforma_auditoria")) >= 1
            # Otro desarrollador ni nulo (operador): RLS lo rechaza.
            _expect_error(connection, sql, {"d": inactivo}, "42501")
            _expect_error(connection, sql, {"d": None}, "42501")
            # A10: sin UPDATE ni DELETE para la aplicación.
            _expect_error(
                connection, "update plataforma_auditoria set resultado = 'rechazado'", {}, "42501"
            )
            _expect_error(connection, "delete from plataforma_auditoria", {}, "42501")
            # Un desarrollador inactivo no inserta ni lee.
            _as_developer(connection, inactivo)
            assert connection.scalar(text("select count(*) from plataforma_auditoria")) == 0
            _expect_error(connection, sql, {"d": inactivo}, "42501")
        finally:
            tx.rollback()


def test_tenant_session_reads_no_platform_rows(db):
    desarrollador_id, _ = _new_developer(db)
    with db.app.connect() as connection:
        tx = connection.begin()
        try:
            connection.execute(
                text("select set_config('app.tenant_id', :t, true)"), {"t": str(uuid.uuid4())}
            )
            assert (
                connection.scalar(
                    text("select count(*) from desarrollador where id = :i"),
                    {"i": desarrollador_id},
                )
                == 0
            )
        finally:
            tx.rollback()


# --- plataforma_buscar_login --------------------------------------------------------------


def test_login_lookup_returns_only_the_listed_columns_and_clears_its_gucs(db):
    desarrollador_id, email = _new_developer(db)
    with db.app.connect() as connection:
        tx = connection.begin()
        try:
            result = connection.execute(
                text("select * from acceso.plataforma_buscar_login(:e)"), {"e": email}
            )
            rows = result.all()
            assert list(result.keys()) == ["id", "password_hash", "activo"]
            assert len(rows) == 1
            assert rows[0].id == desarrollador_id and rows[0].activo is True
            assert rows[0].password_hash.startswith("$argon2id$")
            for guc in OWNER_GUCS:
                value = connection.scalar(text("select current_setting(:g, true)"), {"g": guc})
                assert value in (None, ""), guc
            missing = connection.execute(
                text("select * from acceso.plataforma_buscar_login(:e)"), {"e": _email("nadie")}
            ).all()
            assert missing == []
        finally:
            tx.rollback()


def test_login_lookup_returns_inactive_developers_with_their_flag(db):
    desarrollador_id, email = _new_developer(db, activo=False)
    with db.app.connect() as connection:
        rows = connection.execute(
            text("select id, activo from acceso.plataforma_buscar_login(:e)"), {"e": email}
        ).all()
    assert [tuple(r) for r in rows] == [(desarrollador_id, False)]


def test_app_cannot_execute_the_operator_functions(db):
    with db.app.connect() as connection:
        tx = connection.begin()
        try:
            for name in ("crear_desarrollador", "restablecer_desarrollador"):
                message = _expect_error(
                    connection, FUNCTION_CALLS[name], {}, INSUFFICIENT_PRIVILEGE
                )
                assert "permission denied for function" in message
            _expect_error(
                connection,
                FUNCTION_CALLS["cambiar_estado_desarrollador"],
                {},
                INSUFFICIENT_PRIVILEGE,
            )
        finally:
            tx.rollback()


# --- Funciones del operador (con el migrador) ------------------------------------------------


def _call(db: PlataformaDb, sql: str, params: dict):
    with db.superuser.begin() as connection:
        return connection.scalar(text(sql), params)


def test_crear_desarrollador_inserts_and_audits_as_operator(db):
    email, password_hash = _email(), HASHER.hash("clave-sintetica-larga")
    before = _counts(db)

    desarrollador_id = _call(
        db,
        "select acceso.crear_desarrollador(:e, :n, :h)",
        {"e": email, "n": "Dev Sintético", "h": password_hash},
    )

    with db.superuser.connect() as connection:
        row = connection.execute(
            text("select email, nombre, password_hash, activo from desarrollador where id = :i"),
            {"i": desarrollador_id},
        ).one()
    assert tuple(row) == (email, "Dev Sintético", password_hash, True)
    assert _audit_rows(db, desarrollador_id) == [
        {
            "desarrollador_id": None,
            "accion": "desarrollador_creado",
            "resultado": "ok",
            "tenant_id": None,
            "objeto_id": desarrollador_id,
        }
    ]
    after = _counts(db)
    assert after["desarrollador"] == before["desarrollador"] + 1
    assert after["plataforma_auditoria"] == before["plataforma_auditoria"] + 1


def test_crear_desarrollador_with_a_repeated_email_creates_nothing(db):
    _, email = _new_developer(db)
    before = _counts(db)
    with db.superuser.connect() as connection:
        tx = connection.begin()
        try:
            message = _expect_error(
                connection,
                "select acceso.crear_desarrollador(:e, 'Otro', :h)",
                {"e": email, "h": HASHER.hash("x" * 16)},
                "23505",
            )
        finally:
            tx.rollback()
    assert "desarrollador_existente" in message
    assert email not in message
    assert _counts(db) == before


@pytest.mark.parametrize(
    "password_hash",
    [
        "",
        "x",
        "$argon2i$v=19$m=8,t=1,p=1$c2FsdHNhbHQ$aGFzaGhhc2g",
        "$2b$12$abcdefghijklmnopqrstuuabcdefghijklmnopqrstuvwxyzabcde",
        "$argon2id$v=19$m=8,t=1,p=1$c2FsdHNhbHQ$" + "a" * 300,
    ],
)
def test_crear_desarrollador_rejects_hashes_that_are_not_argon2id(db, password_hash):
    before = _counts(db)
    with db.superuser.connect() as connection:
        tx = connection.begin()
        try:
            _expect_error(
                connection,
                "select acceso.crear_desarrollador(:e, 'X', :h)",
                {"e": _email(), "h": password_hash},
                "22023",
            )
        finally:
            tx.rollback()
    assert _counts(db) == before


def test_crear_desarrollador_rejects_an_unnormalized_email(db):
    before = _counts(db)
    with db.superuser.connect() as connection:
        tx = connection.begin()
        try:
            _expect_error(
                connection,
                "select acceso.crear_desarrollador(:e, 'X', :h)",
                {"e": " Mayus@Ejemplo.test", "h": HASHER.hash("x" * 16)},
                "23514",
            )
        finally:
            tx.rollback()
    assert _counts(db) == before


def test_restablecer_desarrollador_changes_the_hash_and_revokes_every_family(db):
    desarrollador_id, email = _new_developer(db)
    otro, _ = _new_developer(db)
    tokens = [_new_refresh(db, desarrollador_id) for _ in range(3)]
    ajeno = _new_refresh(db, otro)
    nuevo = HASHER.hash("otra-clave-sintetica")

    _call(db, "select acceso.restablecer_desarrollador(:e, :h)", {"e": email, "h": nuevo})

    with db.superuser.connect() as connection:
        stored = connection.scalar(
            text("select password_hash from desarrollador where id = :i"), {"i": desarrollador_id}
        )
    assert stored == nuevo
    assert all(_revoked(db, token) for token in tokens)
    assert not _revoked(db, ajeno)
    assert [r["accion"] for r in _audit_rows(db, desarrollador_id)] == [
        "desarrollador_restablecido"
    ]
    assert _audit_rows(db, desarrollador_id)[0]["desarrollador_id"] is None


def test_restablecer_desarrollador_with_an_unknown_email_fails_generically(db):
    before = _counts(db)
    email = _email("nadie")
    with db.superuser.connect() as connection:
        tx = connection.begin()
        try:
            message = _expect_error(
                connection,
                "select acceso.restablecer_desarrollador(:e, :h)",
                {"e": email, "h": HASHER.hash("x" * 16)},
                "P0002",
            )
        finally:
            tx.rollback()
    assert email not in message
    assert _counts(db) == before


def test_cambiar_estado_desarrollador_deactivates_revokes_and_reactivates(db):
    desarrollador_id, email = _new_developer(db)
    token = _new_refresh(db, desarrollador_id)
    sql = "select acceso.cambiar_estado_desarrollador(:e, :a)"

    _call(db, sql, {"e": email, "a": False})
    with db.superuser.connect() as connection:
        activo = connection.scalar(
            text("select activo from desarrollador where id = :i"), {"i": desarrollador_id}
        )
    assert activo is False
    assert _revoked(db, token)

    posterior = _new_refresh(db, desarrollador_id)
    _call(db, sql, {"e": email, "a": True})
    with db.superuser.connect() as connection:
        activo = connection.scalar(
            text("select activo from desarrollador where id = :i"), {"i": desarrollador_id}
        )
    assert activo is True
    assert not _revoked(db, posterior)  # reactivar no revoca
    rows = _audit_rows(db, desarrollador_id)
    assert {r["accion"] for r in rows} == {"desarrollador_desactivado", "desarrollador_reactivado"}
    assert all(r["desarrollador_id"] is None and r["tenant_id"] is None for r in rows)


def test_cambiar_estado_with_an_unknown_email_fails_generically(db):
    before = _counts(db)
    with db.superuser.connect() as connection:
        tx = connection.begin()
        try:
            _expect_error(
                connection,
                "select acceso.cambiar_estado_desarrollador(:e, false)",
                {"e": _email("nadie")},
                "P0002",
            )
        finally:
            tx.rollback()
    assert _counts(db) == before


def test_operator_functions_leave_no_gucs_behind(db):
    _, email = _new_developer(db)
    with db.superuser.connect() as connection:
        tx = connection.begin()
        try:
            connection.execute(
                text("select acceso.cambiar_estado_desarrollador(:e, true)"), {"e": email}
            )
            for guc in OWNER_GUCS:
                value = connection.scalar(text("select current_setting(:g, true)"), {"g": guc})
                assert value in (None, ""), guc
        finally:
            tx.rollback()
