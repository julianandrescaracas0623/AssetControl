"""Empresas de la consola: lista, alta y estado (spec 017, T3b; R16–R22, R33–R35).

**Validación en Flask, antes de la base.** La ficha usa la misma ``validar`` de la spec 013
(nombre 1–120, dirección 1–200, NIT con dígito de verificación de la DIAN, teléfono 7–30,
correo); el primer admin, el normalizador de nombres visibles (``app.nombres``, tope de
``usuario.nombre``) y el de correos de las invitaciones (``lower(btrim)`` con forma
mínima); la contraseña, ``check_password_policy`` de la 002 (la misma del alta por
invitación y de la recuperación de la 014) y la confirmación se compara aquí. Un cuerpo
mal formado es ``400 solicitud_invalida``; un dato inválido, ``422`` con ``campo``. El
hash Argon2id se calcula aquí y solo viaja a ``acceso.plataforma_crear_tenant``.

**Transacción.** Todo corre en la ``plataforma_session`` de ``require_desarrollador``. Cada
función ``acceso.plataforma_*`` va en un ``SAVEPOINT``: si rechaza (``empresa_existente``,
``email_en_uso``, ``empresa_no_encontrada``...) se revierte solo ese punto y la sesión
sigue sana; la ruta responde el error y la transacción termina sin cambios. Si la función
pasa, la auditoría (``empresa_creada``, ``empresa_desactivada``, ``empresa_reactivada``) se
escribe en la **misma** transacción (``flush`` antes de responder): si falla, no queda la
acción. Los rechazos no se auditan (R33 solo registra acciones; A10: una acción que falla
no deja fila de éxito).

**Logo en el alta (T7; R23, R24).** ``subir_logo`` aplica las reglas de la 013 con
``app.fotos.imagen.procesar_logo`` (PNG, JPEG o WebP ≤ 2 MB; PNG ≤ 600 px con
transparencia y sin metadatos) **antes** de la base; luego
``acceso.plataforma_registrar_logo`` (en su ``SAVEPOINT``) y, solo si creó la fila, guarda
el PNG en el almacén con la clave del tenant (``empresa.service.clave_logo``), registra
el borrado del archivo si la transacción no se confirma (``after_rollback``, como la 013)
y escribe ``empresa_logo_subido`` en la misma transacción. Repetir con el logo vigente
no toca el almacén ni audita (``200``). Sin almacén, ``503 logos_no_disponibles``; un
candado que no llega a tiempo o un interbloqueo, el ``503 servicio_no_disponible``
genérico. Nunca se registran los bytes, el nombre del archivo ni la clave.

**Editar la ficha y reemplazar el logo (C1, T12; R41–R45).** ``leer_ficha`` devuelve
exactamente las cinco columnas de la ficha y ``tiene_logo`` (``acceso.plataforma_leer_empresa``).
``actualizar_ficha`` exige los cinco campos (``PUT``: ``nit``, ``telefono`` y ``correo``
pueden ser ``null``; cualquier otra clave, ``400``), los valida con la misma ``validar`` de la
013 (``422`` con ``campo``) y llama a ``acceso.plataforma_actualizar_empresa`` (fila de
``empresa`` bloqueada; si cambia el nombre, también ``tenant.nombre``, Q-E1); solo si hubo
un cambio real escribe ``empresa_editada`` (sin valores; ``objeto_id`` nulo). ``subir_logo``
ya no rechaza a una empresa con logo: lo reemplaza y audita ``empresa_logo_reemplazado``
(``empresa_logo_subido`` si no tenía); el logo anterior (fila y archivo) se conserva.

Nada de este módulo registra contraseñas, hashes, correos ni nombres; la auditoría solo
lleva ids, acción y resultado.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import event
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.auth.credentials import PasswordPolicyError, check_password_policy, get_passwords
from app.db import (
    FichaEmpresa,
    FichaLeida,
    LogoRegistrado,
    PlataformaFuncionError,
    TenantResumen,
    plataforma_actualizar_empresa,
    plataforma_cambiar_estado_tenant,
    plataforma_crear_tenant,
    plataforma_leer_empresa,
    plataforma_listar_tenants,
    plataforma_registrar_logo,
)
from app.empresa import service as empresa_service
from app.errors import ServiceUnavailableError
from app.fotos import imagen
from app.fotos.almacen import Almacen
from app.invitaciones.service import normalize_invitation_email
from app.nombres import normalize_display_name
from app.plataforma import auditoria

FICHA = empresa_service.CAMPOS  # nombre, direccion, nit, telefono, correo
CAMPOS_ALTA = frozenset({"id", *FICHA, "admin"})
CAMPOS_ADMIN = frozenset({"nombre", "email", "password", "password_confirmacion"})
ESTADOS = ("activas", "desactivadas", "todas")
BUSQUEDA_MAX = 120
# O2 de T3b: tope del correo del primer admin ya normalizado (RFC 5321): sin él, uno más
# largo llegaba a la base y respondía 500.
EMAIL_MAX = 254
# T7: el tope del logo es el de la 013 (2 MB); se lee un byte más para responder 413.
LOGO_MAX_BYTES = empresa_service.LOGO_MAX_BYTES


class ErrorEmpresas(Exception):
    status = 400
    code = "solicitud_invalida"
    message = "La solicitud no es válida."
    campo: str | None = None

    def __init__(self) -> None:
        super().__init__(self.code)


class CampoInvalido(ErrorEmpresas):
    status = 422
    code = "campo_invalido"
    MENSAJES = {
        **empresa_service.CampoInvalido.MENSAJES,
        "admin.nombre": "Escribe el nombre del primer admin (máximo 120 caracteres).",
        "admin.email": "El correo del primer admin no es válido.",
    }

    def __init__(self, campo: str) -> None:
        super().__init__()
        self.campo = campo
        self.message = self.MENSAJES[campo]


class ContrasenaInvalida(ErrorEmpresas):
    """La contraseña del admin no cumple la política de la 002; el código es el de ella."""

    status = 422
    campo = "admin.password"

    def __init__(self, error: PasswordPolicyError) -> None:
        super().__init__()
        self.code = error.code
        self.message = str(error)


class ContrasenasDistintas(ErrorEmpresas):
    status = 422
    code = "contrasenas_distintas"
    message = "Las contraseñas no coinciden."
    campo = "admin.password_confirmacion"


class EmpresaExistente(ErrorEmpresas):
    status = 409
    code = "empresa_existente"
    message = "Esta empresa ya se creó. La contraseña del admin no se puede recuperar."


class EmailEnUso(ErrorEmpresas):
    status = 409
    code = "email_en_uso"
    message = "Ese correo ya está en uso. Usa otro correo para el primer admin."


class EmpresaNoEncontrada(ErrorEmpresas):
    status = 404
    code = "no_encontrado"
    message = "La empresa no existe."


class DesarrolladorNoAutorizado(ErrorEmpresas):
    """El desarrollador dejó de estar activo durante la petición: el mismo ``401``."""

    status = 401
    code = "no_autenticado"
    message = "Debes iniciar sesión."


# --- Logo en el alta (T7) ---


class EmpresaSinDatos(ErrorEmpresas):
    """El tenant no tiene ficha ``empresa`` (p. ej. creado por la CLI): como la 013."""

    status = 409
    code = "empresa_sin_datos"
    message = "La empresa no tiene sus datos guardados; su admin debe guardarlos primero."


class LogoIdEnUso(ErrorEmpresas):
    status = 409
    code = "logo_id_en_uso"
    message = "Ese identificador de logo ya se usó."


class EmpresaSinAdmin(ErrorEmpresas):
    status = 409
    code = "empresa_sin_admin"
    message = "La empresa no tiene un admin a quien asignar el logo."


class LogosNoDisponibles(ErrorEmpresas):
    status = 503
    code = "logos_no_disponibles"
    message = "El almacenamiento de imágenes no está disponible en este momento."


class ImagenRechazada(ErrorEmpresas):
    """Archivo que no cumple las reglas de la 013: su mismo estado, código y mensaje."""

    def __init__(self, error: imagen.ErrorImagen) -> None:
        super().__init__()
        self.status = error.status
        self.code = error.code
        self.message = error.message


# Códigos propios del módulo (los de la política de contraseña son los de la 002 y los de
# la imagen, los de la 012/013).
ERRORES = (
    ErrorEmpresas,
    CampoInvalido,
    ContrasenasDistintas,
    EmpresaExistente,
    EmailEnUso,
    EmpresaNoEncontrada,
    EmpresaSinDatos,
    LogoIdEnUso,
    EmpresaSinAdmin,
    LogosNoDisponibles,
)

_RECHAZOS = {
    "empresa_existente": EmpresaExistente,
    "email_en_uso": EmailEnUso,
    "empresa_no_encontrada": EmpresaNoEncontrada,
    "desarrollador_no_autorizado": DesarrolladorNoAutorizado,
    # T7 (0029); C1 (0030) ya no emite logo_existente: reemplaza.
    "empresa_sin_datos": EmpresaSinDatos,
    "logo_id_en_uso": LogoIdEnUso,
    "empresa_sin_admin": EmpresaSinAdmin,
    # Fila de empresa bloqueada más allá del lock_timeout: 503 genérico con Retry-After.
    "empresa_ocupada": ServiceUnavailableError,
}

# Errores transitorios de la base (candado, interbloqueo, serialización): ``503`` genérico.
_SQLSTATE_TRANSITORIOS = frozenset({"55P03", "40P01", "40001"})


@dataclass(frozen=True)
class EmpresaCreada:
    empresa_id: uuid.UUID
    admin_id: uuid.UUID

    def to_json(self) -> dict[str, str]:
        return {"empresa_id": str(self.empresa_id), "admin_id": str(self.admin_id)}


@dataclass(frozen=True)
class AltaValidada:
    """Alta lista para la base. Solo el id sale en ``repr``: nunca datos ni la contraseña."""

    tenant_id: uuid.UUID
    ficha: FichaEmpresa = field(repr=False)
    admin_email: str = field(repr=False)
    admin_nombre: str = field(repr=False)
    password: str = field(repr=False)


def _llamar(session: Session, funcion, *args: Any, **kwargs: Any):
    """La función ``acceso.plataforma_*`` en un ``SAVEPOINT``; su rechazo, como error HTTP."""
    rechazo = None
    try:
        with session.begin_nested():
            return funcion(session, *args, **kwargs)
    except PlataformaFuncionError as exc:
        rechazo = _RECHAZOS.get(exc.codigo)
        if rechazo is None:
            raise
    raise rechazo()


# --- Lista (R21) --------------------------------------------------------------------------


def filtros(args: Any) -> tuple[str, str]:
    """``(q, estado)`` de la consulta: ``q`` sin espacios en los extremos y en minúsculas."""
    q = args.get("q", "")
    estado = args.get("estado", "todas")
    if len(q) > BUSQUEDA_MAX or estado not in ESTADOS:
        raise ErrorEmpresas()
    return q.strip().casefold(), estado


def _empresa_json(tenant: TenantResumen) -> dict[str, object]:
    return {
        "id": str(tenant.id),
        "nombre": tenant.nombre,
        "activa": tenant.activo,
        "creado_en": tenant.creado_en.isoformat(),
        "tiene_logo": tenant.tiene_logo,
        "n_membresias_activas": tenant.n_membresias_activas,
        "n_admins_activos": tenant.n_admins_activos,
    }


def listar(session: Session, q: str, estado: str) -> list[dict[str, object]]:
    tenants = _llamar(session, plataforma_listar_tenants)
    return [
        _empresa_json(tenant)
        for tenant in tenants
        if (estado == "todas" or tenant.activo == (estado == "activas"))
        and q in tenant.nombre.casefold()
    ]


# --- Alta (R16–R20) -----------------------------------------------------------------------


def _uuid(value: Any) -> uuid.UUID:
    if not isinstance(value, str):
        raise ErrorEmpresas()
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        raise ErrorEmpresas() from None
    if str(parsed) != value:
        raise ErrorEmpresas()
    return parsed


# UUID canónico (minúsculas, con guiones) de un campo del cliente; si no, ``400``.
parse_uuid = _uuid


def _ficha(body: dict[str, Any]) -> FichaEmpresa:
    try:
        datos = empresa_service.validar({k: v for k, v in body.items() if k in FICHA})
    except empresa_service.CampoInvalido as exc:
        campo = exc.campo
    except empresa_service.ErrorEmpresa:
        raise ErrorEmpresas() from None
    else:
        return FichaEmpresa(
            nombre=datos["nombre"],
            direccion=datos["direccion"],
            nit=datos["nit"],
            telefono=datos["telefono"],
            correo=datos["correo"],
        )
    # Fuera del except: sin causa que arrastre el valor rechazado.
    raise CampoInvalido(campo)


def validar_alta(body: Any) -> AltaValidada:
    """Forma (``400``) y contenido (``422``) del alta; nada aquí toca la base."""
    if not isinstance(body, dict) or not set(body) <= CAMPOS_ALTA:
        raise ErrorEmpresas()
    if "id" not in body or "admin" not in body:
        raise ErrorEmpresas()
    tenant_id = _uuid(body["id"])
    admin = body["admin"]
    if not isinstance(admin, dict) or set(admin) != CAMPOS_ADMIN:
        raise ErrorEmpresas()
    if not all(isinstance(admin[k], str) for k in CAMPOS_ADMIN):
        raise ErrorEmpresas()

    ficha = _ficha(body)
    nombre = normalize_display_name(admin["nombre"])
    if nombre is None:
        raise CampoInvalido("admin.nombre")
    email = normalize_invitation_email(admin["email"])
    if email is None or len(email) > EMAIL_MAX:
        raise CampoInvalido("admin.email")
    password = admin["password"]
    policy_error = None
    try:
        check_password_policy(password)
    except PasswordPolicyError as exc:
        policy_error = exc
    if policy_error is not None:
        raise ContrasenaInvalida(policy_error)
    if admin["password_confirmacion"] != password:
        raise ContrasenasDistintas()
    return AltaValidada(
        tenant_id=tenant_id,
        ficha=ficha,
        admin_email=email,
        admin_nombre=nombre,
        password=password,
    )


def crear(session: Session, alta: AltaValidada) -> EmpresaCreada:
    """Hash Argon2id, ``plataforma_crear_tenant`` y ``empresa_creada``, en una transacción."""
    password_hash = get_passwords().hash(alta.password)
    creado = _llamar(
        session,
        plataforma_crear_tenant,
        tenant_id=alta.tenant_id,
        ficha=alta.ficha,
        admin_email=alta.admin_email,
        admin_nombre=alta.admin_nombre,
        password_hash=password_hash,
    )
    auditoria.registrar(
        session, "empresa_creada", tenant_id=creado.tenant_id, objeto_id=creado.tenant_id
    )
    session.flush()
    return EmpresaCreada(empresa_id=creado.tenant_id, admin_id=creado.usuario_id)


# --- Estado (R22) -------------------------------------------------------------------------


def validar_estado(body: Any) -> bool:
    if not isinstance(body, dict) or set(body) != {"activa"}:
        raise ErrorEmpresas()
    activa = body["activa"]
    if not isinstance(activa, bool):
        raise ErrorEmpresas()
    return activa


def cambiar_estado(session: Session, tenant_id: uuid.UUID, activa: bool) -> bool:
    """Desactiva o reactiva (idempotente) y lo audita en la misma transacción."""
    activo = _llamar(session, plataforma_cambiar_estado_tenant, tenant_id, activa)
    accion = "empresa_reactivada" if activo else "empresa_desactivada"
    auditoria.registrar(session, accion, tenant_id=tenant_id, objeto_id=tenant_id)
    session.flush()
    return activo


# --- Logo en el alta (R23, R24) -----------------------------------------------------------


def _transitorio(exc: DBAPIError) -> bool:
    return getattr(exc.orig, "sqlstate", None) in _SQLSTATE_TRANSITORIOS


def _llamar_bloqueante(session: Session, funcion, *args: Any, **kwargs: Any):
    """Una función que bloquea la fila de ``empresa``, en un ``SAVEPOINT``; sus rechazos y
    los errores transitorios de la base (candado, interbloqueo, serialización), como HTTP."""
    rechazo = None
    try:
        with session.begin_nested():
            return funcion(session, *args, **kwargs)
    except PlataformaFuncionError as exc:
        rechazo = _RECHAZOS.get(exc.codigo)
        if rechazo is None:
            raise
    except DBAPIError as exc:
        if not _transitorio(exc):
            raise
        rechazo = ServiceUnavailableError
    # Fuera del except: sin causa ni contexto con el mensaje de la base.
    raise rechazo()


def _flush_o_503(session: Session) -> None:
    """``flush`` de la auditoría; un error transitorio de la base es el ``503`` genérico
    (la ``plataforma_session`` revierte todo al salir)."""
    transitorio = False
    try:
        session.flush()
    except DBAPIError as exc:
        if not _transitorio(exc):
            raise
        transitorio = True
    if transitorio:
        raise ServiceUnavailableError()


def _borrar(almacen: Almacen, clave: str) -> None:
    try:
        almacen.borrar(clave)
    except Exception:  # noqa: BLE001, S110 - mejor esfuerzo: queda un objeto huérfano
        pass


def subir_logo(
    session: Session,
    almacen: Almacen | None,
    *,
    tenant_id: uuid.UUID,
    logo_id: uuid.UUID,
    datos: bytes,
) -> LogoRegistrado:
    """Logo de una empresa (R23) o reemplazo del vigente (R44); idempotente con el vigente."""
    if almacen is None:
        raise LogosNoDisponibles()
    error = None
    try:
        logo = imagen.procesar_logo(datos)
    except imagen.ErrorImagen as exc:
        error = exc
    if error is not None:
        raise ImagenRechazada(error)
    clave = empresa_service.clave_logo(tenant_id, logo_id)
    registrado = _llamar_bloqueante(
        session,
        plataforma_registrar_logo,
        tenant_id=tenant_id,
        logo_id=logo_id,
        clave=clave,
        bytes_=len(logo.png),
        ancho=logo.ancho,
        alto=logo.alto,
    )
    if not registrado.creado:
        return registrado
    # Si la transacción no se confirma, no debe quedar un archivo sin fila. El anterior
    # (si lo había) no se toca: los informes congelados lo usan (013 R2).
    event.listen(session, "after_rollback", lambda _s: _borrar(almacen, clave), once=True)
    almacen.guardar(clave, logo.png, empresa_service.TIPO_LOGO)
    accion = "empresa_logo_reemplazado" if registrado.reemplazado else "empresa_logo_subido"
    auditoria.registrar(session, accion, tenant_id=tenant_id, objeto_id=logo_id)
    # Si falla, la plataforma_session revierte también el logo (y after_rollback borra el
    # archivo nuevo).
    _flush_o_503(session)
    return registrado


# --- Ficha de la empresa (C1; R41–R43, R45) -----------------------------------------------


def _ficha_json(ficha: FichaLeida) -> dict[str, object]:
    return {
        "nombre": ficha.nombre,
        "direccion": ficha.direccion,
        "nit": ficha.nit,
        "telefono": ficha.telefono,
        "correo": ficha.correo,
        "tiene_logo": ficha.tiene_logo,
    }


def leer_ficha(session: Session, tenant_id: uuid.UUID) -> dict[str, object]:
    """Exactamente las cinco columnas de la ficha y si hay logo (R41)."""
    return _ficha_json(_llamar(session, plataforma_leer_empresa, tenant_id))


def validar_ficha(body: Any) -> FichaEmpresa:
    """``PUT`` con los cinco campos y nada más (``400``); su contenido, como la 013 (``422``)."""
    if not isinstance(body, dict) or set(body) != set(FICHA):
        raise ErrorEmpresas()
    return _ficha(body)


def actualizar_ficha(
    session: Session, tenant_id: uuid.UUID, ficha: FichaEmpresa
) -> dict[str, object]:
    """Edita la ficha (y ``tenant.nombre`` si cambia el nombre); audita solo un cambio real."""
    cambiado = _llamar_bloqueante(session, plataforma_actualizar_empresa, tenant_id, ficha)
    if cambiado:
        # Sin valores (R45): solo la acción y la empresa.
        auditoria.registrar(session, "empresa_editada", tenant_id=tenant_id)
        _flush_o_503(session)
    return leer_ficha(session, tenant_id)
