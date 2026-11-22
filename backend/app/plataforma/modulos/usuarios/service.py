"""Usuarios de una empresa en la consola: lista, estado de la membresía (spec 017, T5) y
edición de nombre y rol (C1, T13).

``spec.md`` R29–R31, R33–R35; A17. Todo corre en la ``plataforma_session`` de
``require_desarrollador``. Cada función ``acceso.plataforma_*`` va en un ``SAVEPOINT``: si
rechaza (``empresa_no_encontrada``, ``usuario_no_encontrado``, ``empresa_inactiva``,
``ultimo_admin``...) se revierte solo ese punto y la ruta responde el error sin cambios.
Si pasa y hubo un cambio real, la auditoría (``usuario_desactivado`` /
``usuario_reactivado``, con el tenant y el id del usuario; nada más) se escribe en la
**misma** transacción (``flush`` antes de responder). Ni los rechazos ni un ``PATCH``
idempotente (repetir el estado actual) se auditan. Si la función no obtiene su candado a
tiempo (``membresia_ocupada``, ``lock_timeout`` de 0027), o la base aborta la transacción
por interbloqueo (``40P01``) o fallo de serialización (``40001``), se responde el ``503
servicio_no_disponible`` genérico, sin cambios ni el mensaje de la base.

Editar (R47–R51): el cuerpo es exactamente ``{nombre, rol}`` (otra clave, incluidos
``email``, ``password`` o ``activa``, es ``400``); el nombre pasa por el normalizador de
``usuario.nombre`` (``app.nombres``, el del alta, R19) y el rol es ``admin`` o
``contador`` (``422`` con ``campo``), antes de tocar la base. La función cambia solo lo que
difiere y, si cambió el rol, revoca las familias de refresh de esa membresía;
``usuario_editado`` (tenant e id del usuario; ningún valor) se audita en la misma
transacción solo si algo cambió.

Contraseña temporal (C1b, R53–R58): el cuerpo es exactamente ``{password,
password_confirmacion}`` (``400`` con otra clave o sin texto); la política es la del alta
(``check_password_policy``, R19) y la confirmación se compara en el servidor (``422`` con
``campo``), antes de tocar la base. El hash Argon2id se calcula aquí, con
``get_passwords()`` (la misma del alta), antes de llamar a la función de base, que toma los
candados. ``usuario_contrasena_restablecida`` (tenant e id del usuario; ningún valor) se
audita en la misma transacción en cada llamada válida (no es idempotente). Ni la contraseña,
ni su confirmación, ni el hash salen en una respuesta, un log o una excepción.

La lista solo lleva lo que permite R29: id del usuario, nombre, correo, rol, si la
membresía está activa y si el cambio de contraseña sigue pendiente. Nada de este módulo
registra nombres ni correos.
"""

import uuid
from typing import Any

from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.auth.credentials import PasswordPolicyError, check_password_policy, get_passwords
from app.auth.decorators import ROLES
from app.db import (
    CambioMembresia,
    PlataformaFuncionError,
    UsuarioEditado,
    UsuarioResumen,
    plataforma_cambiar_estado_membresia,
    plataforma_cambiar_usuario,
    plataforma_listar_usuarios,
    plataforma_restablecer_password_usuario,
)
from app.errors import ServiceUnavailableError
from app.nombres import normalize_display_name
from app.plataforma import auditoria


class ErrorUsuarios(Exception):
    status = 400
    code = "solicitud_invalida"
    message = "La solicitud no es válida."
    campo: str | None = None

    def __init__(self) -> None:
        super().__init__(self.code)


class EmpresaNoEncontrada(ErrorUsuarios):
    status = 404
    code = "no_encontrado"
    message = "La empresa no existe."


class UsuarioNoEncontrado(ErrorUsuarios):
    """El usuario no es de esa empresa (o no existe): el mismo ``404`` genérico."""

    status = 404
    code = "no_encontrado"
    message = "Ese usuario no pertenece a esta empresa."


class EmpresaInactiva(ErrorUsuarios):
    status = 409
    code = "empresa_inactiva"
    message = "La empresa está desactivada. Reactívala antes de cambiar sus usuarios."


class UltimoAdmin(ErrorUsuarios):
    status = 409
    code = "ultimo_admin"
    message = "No se puede desactivar al último admin activo de la empresa."


class UltimoAdminRol(UltimoAdmin):
    """Degradar al último admin activo (C1, R48): el mismo código, otro mensaje."""

    message = "No se puede quitar el rol admin al último admin activo de la empresa."


class NombreInvalido(ErrorUsuarios):
    status = 422
    code = "campo_invalido"
    campo = "nombre"
    message = "Escribe el nombre (máximo 120 caracteres)."


class RolInvalido(ErrorUsuarios):
    status = 422
    code = "campo_invalido"
    campo = "rol"
    message = "Elige un rol: admin o contador."


class ContrasenaInvalida(ErrorUsuarios):
    """La contraseña temporal no cumple la política de la 002 (C1b, R53): su código y mensaje."""

    status = 422
    campo = "password"

    def __init__(self, error: PasswordPolicyError) -> None:
        super().__init__()
        self.code = error.code
        self.message = str(error)


class ContrasenasDistintas(ErrorUsuarios):
    status = 422
    code = "contrasenas_distintas"
    message = "Las contraseñas no coinciden."
    campo = "password_confirmacion"


class DesarrolladorNoAutorizado(ErrorUsuarios):
    """El desarrollador dejó de estar activo durante la petición: el mismo ``401``."""

    status = 401
    code = "no_autenticado"
    message = "Debes iniciar sesión."


# Códigos propios del módulo.
ERRORES = (
    ErrorUsuarios,
    EmpresaNoEncontrada,
    UsuarioNoEncontrado,
    EmpresaInactiva,
    UltimoAdmin,
    NombreInvalido,
    RolInvalido,
    ContrasenasDistintas,
)

_RECHAZOS = {
    "empresa_no_encontrada": EmpresaNoEncontrada,
    "usuario_no_encontrado": UsuarioNoEncontrado,
    "empresa_inactiva": EmpresaInactiva,
    "ultimo_admin": UltimoAdmin,
    "desarrollador_no_autorizado": DesarrolladorNoAutorizado,
    # Candado no obtenido dentro del lock_timeout: 503 genérico con Retry-After.
    "membresia_ocupada": ServiceUnavailableError,
}
# Editar (C1): los mismos rechazos; ultimo_admin dice que es por quitar el rol.
_RECHAZOS_EDICION = {**_RECHAZOS, "ultimo_admin": UltimoAdminRol}


# Errores transitorios de la base (candado, interbloqueo, serialización): ``503`` genérico.
_SQLSTATE_TRANSITORIOS = frozenset({"55P03", "40P01", "40001"})


def _transitorio(exc: DBAPIError) -> bool:
    return getattr(exc.orig, "sqlstate", None) in _SQLSTATE_TRANSITORIOS


def _llamar(session: Session, funcion, *args: Any, rechazos: dict = _RECHAZOS):
    """La función ``acceso.plataforma_*`` en un ``SAVEPOINT``; su rechazo, como error HTTP."""
    rechazo = None
    try:
        with session.begin_nested():
            return funcion(session, *args)
    except PlataformaFuncionError as exc:
        rechazo = rechazos.get(exc.codigo)
        if rechazo is None:
            raise
    except DBAPIError as exc:
        if not _transitorio(exc):
            raise
        rechazo = ServiceUnavailableError
    # Fuera del except: sin causa ni contexto con el mensaje de la base.
    raise rechazo()


# --- Lista (R29) --------------------------------------------------------------------------


def _usuario_json(usuario: UsuarioResumen) -> dict[str, object]:
    return {
        "id": str(usuario.usuario_id),
        "nombre": usuario.nombre,
        "email": usuario.email,
        "rol": usuario.rol,
        "activa": usuario.activa,
        "debe_cambiar_password": usuario.debe_cambiar_password,
    }


def listar(session: Session, tenant_id: uuid.UUID) -> list[dict[str, object]]:
    return [_usuario_json(u) for u in _llamar(session, plataforma_listar_usuarios, tenant_id)]


# --- Estado (R30, R31) --------------------------------------------------------------------


def validar_estado(body: Any) -> bool:
    """El cuerpo es exactamente ``{"activa": bool}`` (sin otros campos)."""
    if not isinstance(body, dict) or set(body) != {"activa"}:
        raise ErrorUsuarios()
    activa = body["activa"]
    if not isinstance(activa, bool):
        raise ErrorUsuarios()
    return activa


def cambiar_estado(
    session: Session, tenant_id: uuid.UUID, usuario_id: uuid.UUID, activa: bool
) -> bool:
    """Desactiva o reactiva la membresía (idempotente); audita solo un cambio real, en la
    misma transacción. Devuelve el estado resultante."""
    cambio = _llamar(session, plataforma_cambiar_estado_membresia, tenant_id, usuario_id, activa)
    if not isinstance(cambio, CambioMembresia):
        raise TypeError("Resultado inesperado al cambiar el estado de la membresía.")
    if cambio.cambiado is True:
        accion = "usuario_reactivado" if cambio.activa is True else "usuario_desactivado"
        auditoria.registrar(session, accion, tenant_id=tenant_id, objeto_id=usuario_id)
        _flush_o_503(session)
    return cambio.activa


def _flush_o_503(session: Session) -> None:
    """``flush`` de la auditoría; un error transitorio de la base es el ``503`` genérico
    (la ``plataforma_session`` revierte también el cambio de la membresía o del usuario)."""
    transitorio = False
    try:
        session.flush()
    except DBAPIError as exc:
        if not _transitorio(exc):
            raise
        transitorio = True
    if transitorio:
        raise ServiceUnavailableError()


# --- Editar nombre y rol (C1; R47–R51) ------------------------------------------------------

CAMPOS_EDICION = frozenset({"nombre", "rol"})


def validar_edicion(body: Any) -> tuple[str, str]:
    """Exactamente ``{nombre, rol}`` (``400``); nombre normalizado y rol de la lista (``422``)."""
    if not isinstance(body, dict) or set(body) != CAMPOS_EDICION:
        raise ErrorUsuarios()
    nombre = normalize_display_name(body["nombre"])
    if nombre is None:
        raise NombreInvalido()
    rol = body["rol"]
    if not isinstance(rol, str) or rol not in ROLES:
        raise RolInvalido()
    return nombre, rol


def editar(
    session: Session, tenant_id: uuid.UUID, usuario_id: uuid.UUID, nombre: str, rol: str
) -> dict[str, object]:
    """Cambia nombre y rol (solo lo que difiere; idempotente); audita solo un cambio real,
    en la misma transacción. Devuelve ``{id, nombre, rol}`` resultantes."""
    editado = _llamar(
        session,
        plataforma_cambiar_usuario,
        tenant_id,
        usuario_id,
        nombre,
        rol,
        rechazos=_RECHAZOS_EDICION,
    )
    if not isinstance(editado, UsuarioEditado):
        raise TypeError("Resultado inesperado al editar el usuario.")
    if editado.cambiado is True:
        # Sin valores (R34, R50): ni el nombre ni el rol, ni qué cambió.
        auditoria.registrar(session, "usuario_editado", tenant_id=tenant_id, objeto_id=usuario_id)
        _flush_o_503(session)
    return {"id": str(usuario_id), "nombre": editado.nombre, "rol": editado.rol}


# --- Contraseña temporal (C1b; R53–R58) -----------------------------------------------------

CAMPOS_CONTRASENA = frozenset({"password", "password_confirmacion"})


def validar_contrasena(body: Any) -> str:
    """Exactamente ``{password, password_confirmacion}`` de texto (``400``); la política de
    la 002, la misma del alta (R19), y la confirmación (``422`` con ``campo``). Nada aquí
    toca la base ni registra los valores."""
    if not isinstance(body, dict) or set(body) != CAMPOS_CONTRASENA:
        raise ErrorUsuarios()
    password, confirmacion = body["password"], body["password_confirmacion"]
    if not isinstance(password, str) or not isinstance(confirmacion, str):
        raise ErrorUsuarios()
    policy_error = None
    try:
        check_password_policy(password)
    except PasswordPolicyError as exc:
        policy_error = exc
    if policy_error is not None:
        # Fuera del except: sin causa que arrastre el valor rechazado.
        raise ContrasenaInvalida(policy_error)
    if confirmacion != password:
        raise ContrasenasDistintas()
    return password


def restablecer_contrasena(
    session: Session, tenant_id: uuid.UUID, usuario_id: uuid.UUID, password: str
) -> None:
    """Define una contraseña temporal (no idempotente): hash Argon2id en Flask con la misma
    función del alta, la función de base (marca, corte de sesiones y revocación de todas las
    familias del usuario) y ``usuario_contrasena_restablecida`` en la misma transacción."""
    password_hash = get_passwords().hash(password)
    _llamar(session, plataforma_restablecer_password_usuario, tenant_id, usuario_id, password_hash)
    # Sin valores (R57): ni la contraseña ni el hash, ni el correo ni el nombre.
    auditoria.registrar(
        session, "usuario_contrasena_restablecida", tenant_id=tenant_id, objeto_id=usuario_id
    )
    _flush_o_503(session)
