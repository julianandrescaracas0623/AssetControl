"""Datos de la empresa y su logo (spec 013, T2; R1, R2, R9; plan.md §3).

- ``vista``: los datos guardados o, si no hay fila, el nombre del tenant y
  ``completa: false``.
- ``guardar``: valida y normaliza (R1): nombre y dirección obligatorios; NIT opcional con
  el dígito de verificación de la DIAN si lo trae; teléfono y correo opcionales.
- Logo (R2): ``imagen.procesar_logo`` (PNG ≤ 600 px, transparencia, sin metadatos) →
  almacenamiento → ``empresa_logo`` y ``empresa.logo_id``. Cambiarlo o quitarlo **no**
  borra el anterior: los informes congelados lo siguen usando.

Nunca se registran los datos de la empresa ni las claves del almacenamiento.
"""

import re
import unicodedata
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.models import Tenant
from app.empresa.models import Empresa, EmpresaLogo
from app.fotos import imagen
from app.fotos.almacen import Almacen, ObjetoNoEncontrado
from app.nombres import normalize_display_name

LOGO_MAX_BYTES = imagen.LOGO_MAX_BYTES
TIPO_LOGO = "image/png"
CAMPOS = ("nombre", "direccion", "nit", "telefono", "correo")
OBLIGATORIOS = ("nombre", "direccion")
# Pesos de la DIAN para el dígito de verificación, desde el dígito de la derecha.
PESOS_DV = (3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71)
_NIT = re.compile(r"(?P<base>[0-9][0-9. ]*[0-9])(?:\s*-\s*(?P<dv>[0-9]+))?")
_TELEFONO = re.compile(r"[0-9+() .\-]{7,30}")
_CORREO = re.compile(r"[^@\s]+@[^@\s.]+(\.[^@\s.]+)+")
_RECHAZADOS = frozenset({"Cc", "Cs", "Cf", "Zl", "Zp", "Co", "Cn"})


class ErrorEmpresa(Exception):
    status = 400
    code = "solicitud_invalida"
    message = "La solicitud no es válida."
    campo: str | None = None


class CampoInvalido(ErrorEmpresa):
    MENSAJES = {
        "nombre": "Escribe el nombre de la empresa (máximo 120 caracteres).",
        "direccion": "Escribe la dirección (máximo 200 caracteres).",
        "nit": "El NIT no es válido: revisa los números y el dígito de verificación.",
        "telefono": (
            "El teléfono debe tener entre 7 y 30 caracteres: números, espacios, +, ( ) o -."
        ),
        "correo": "El correo no es válido.",
    }

    def __init__(self, campo: str) -> None:
        super().__init__(campo)
        self.campo = campo
        self.message = self.MENSAJES[campo]


class EmpresaSinDatos(ErrorEmpresa):
    status = 409
    code = "empresa_sin_datos"
    message = "Guarda primero el nombre y la dirección de la empresa."


class SinLogo(ErrorEmpresa):
    status = 404
    code = "sin_logo"
    message = "No hay logo."


class LogoIdEnUso(ErrorEmpresa):
    status = 409
    code = "logo_id_en_uso"
    message = "Ese identificador de logo ya se usó."


class LogosNoDisponibles(ErrorEmpresa):
    status = 503
    code = "fotos_no_disponibles"
    message = "El almacenamiento de imágenes no está disponible en este momento."


ERRORES = (ErrorEmpresa, EmpresaSinDatos, SinLogo, LogoIdEnUso, LogosNoDisponibles)


@dataclass(frozen=True)
class SubidaLogo:
    logo: EmpresaLogo
    creado: bool


def clave_logo(tenant_id: uuid.UUID, logo_id: uuid.UUID) -> str:
    return f"{tenant_id}/{logo_id}.png"


# --- validación


def digito_verificacion(base: str) -> int:
    suma = sum(int(d) * PESOS_DV[i] for i, d in enumerate(reversed(base)))
    resto = suma % 11
    return resto if resto < 2 else 11 - resto


def _con_puntos(base: str) -> str:
    grupos = []
    while base:
        grupos.insert(0, base[-3:])
        base = base[:-3]
    return ".".join(grupos)


def normalizar_nit(valor: str) -> str:
    """``900123456-8`` → ``900.123.456-8``; sin guion se guarda sin dígito."""
    coincide = _NIT.fullmatch(valor.strip())
    if coincide is None:
        raise CampoInvalido("nit")
    base = re.sub(r"[. ]", "", coincide["base"])
    dv = coincide["dv"]
    if not 5 <= len(base) <= 15 or (dv is not None and len(dv) != 1):
        raise CampoInvalido("nit")
    if dv is not None and int(dv) != digito_verificacion(base):
        raise CampoInvalido("nit")
    return _con_puntos(base) + (f"-{dv}" if dv is not None else "")


def _texto(campo: str, valor: Any, maximo: int) -> str | None:
    if valor is None:
        return None
    if not isinstance(valor, str):
        raise CampoInvalido(campo)
    if any(unicodedata.category(c) == "Cs" for c in valor):
        raise CampoInvalido(campo)
    texto = " ".join(unicodedata.normalize("NFC", valor).split())
    if not texto:
        return None
    if len(texto) > maximo or any(unicodedata.category(c) in _RECHAZADOS for c in texto):
        raise CampoInvalido(campo)
    return texto


def validar(cuerpo: Any) -> dict[str, str | None]:
    if not isinstance(cuerpo, dict) or set(cuerpo) - set(CAMPOS):
        raise ErrorEmpresa()
    if any(campo not in cuerpo for campo in OBLIGATORIOS):
        raise ErrorEmpresa()
    nombre = normalize_display_name(cuerpo["nombre"]) if isinstance(cuerpo["nombre"], str) else None
    if nombre is None:
        raise CampoInvalido("nombre")
    direccion = _texto("direccion", cuerpo["direccion"], 200)
    if direccion is None:
        raise CampoInvalido("direccion")
    nit = _texto("nit", cuerpo.get("nit"), 40)
    telefono = _texto("telefono", cuerpo.get("telefono"), 30)
    correo = _texto("correo", cuerpo.get("correo"), 254)
    if telefono is not None and not _TELEFONO.fullmatch(telefono):
        raise CampoInvalido("telefono")
    if correo is not None and not _CORREO.fullmatch(correo):
        raise CampoInvalido("correo")
    return {
        "nombre": nombre,
        "direccion": direccion,
        "nit": normalizar_nit(nit) if nit is not None else None,
        "telefono": telefono,
        "correo": correo,
    }


# --- lectura y escritura


def obtener(session: Session) -> Empresa | None:
    return session.scalars(select(Empresa)).one_or_none()


def vista(session: Session, tenant_id: uuid.UUID) -> dict[str, Any]:
    empresa = obtener(session)
    if empresa is None:
        nombre = session.scalar(select(Tenant.nombre).where(Tenant.id == tenant_id))
        return {
            "nombre": nombre,
            "direccion": None,
            "nit": None,
            "telefono": None,
            "correo": None,
            "logo": None,
            "completa": False,
        }
    return {
        "nombre": empresa.nombre,
        "direccion": empresa.direccion,
        "nit": empresa.nit,
        "telefono": empresa.telefono,
        "correo": empresa.correo,
        "logo": {"id": str(empresa.logo_id)} if empresa.logo_id else None,
        "completa": True,
    }


def _bloquear(session: Session) -> Empresa | None:
    return session.scalars(
        select(Empresa).with_for_update().execution_options(populate_existing=True)
    ).one_or_none()


def guardar(session: Session, cuerpo: Any, *, tenant_id: uuid.UUID, usuario_id: uuid.UUID) -> None:
    datos = validar(cuerpo)
    empresa = _bloquear(session)
    if empresa is None:
        session.add(Empresa(tenant_id=tenant_id, actualizada_por=usuario_id, **datos))
    else:
        for campo, valor in datos.items():
            setattr(empresa, campo, valor)
        empresa.actualizada_en = func.now()  # type: ignore[assignment]
        empresa.actualizada_por = usuario_id
    session.flush()


def _requerir(almacen: Almacen | None) -> Almacen:
    if almacen is None:
        raise LogosNoDisponibles()
    return almacen


def subir_logo(
    session: Session,
    almacen: Almacen | None,
    *,
    tenant_id: uuid.UUID,
    logo_id: uuid.UUID,
    datos: bytes,
    usuario_id: uuid.UUID,
) -> SubidaLogo:
    almacen = _requerir(almacen)
    empresa = _bloquear(session)
    if empresa is None:
        raise EmpresaSinDatos()
    previo = session.get(EmpresaLogo, logo_id)
    if previo is not None:
        if empresa.logo_id == logo_id:
            return SubidaLogo(previo, creado=False)
        raise LogoIdEnUso()
    logo = imagen.procesar_logo(datos)
    clave = clave_logo(tenant_id, logo_id)
    almacen.guardar(clave, logo.png, TIPO_LOGO)
    # Si la transacción no se confirma, no debe quedar un logo sin fila.
    event.listen(session, "after_rollback", lambda _s: _borrar(almacen, clave), once=True)
    fila = EmpresaLogo(
        id=logo_id,
        clave=clave,
        bytes=len(logo.png),
        ancho=logo.ancho,
        alto=logo.alto,
        subido_por=usuario_id,
    )
    try:
        with session.begin_nested():
            session.add(fila)
            session.flush()
    except IntegrityError:
        # Un ``id`` usado en otro tenant (la RLS no lo deja ver) choca con la clave primaria.
        raise LogoIdEnUso() from None
    empresa.logo_id = logo_id
    empresa.actualizada_en = func.now()  # type: ignore[assignment]
    empresa.actualizada_por = usuario_id
    session.flush()
    return SubidaLogo(fila, creado=True)


def _borrar(almacen: Almacen, clave: str) -> None:
    try:
        almacen.borrar(clave)
    except Exception:  # noqa: BLE001, S110 - mejor esfuerzo: queda un objeto huérfano
        pass


def quitar_logo(session: Session, *, usuario_id: uuid.UUID) -> None:
    """Deja la empresa sin logo; el archivo y la fila quedan (R2)."""
    empresa = _bloquear(session)
    if empresa is None or empresa.logo_id is None:
        raise SinLogo()
    empresa.logo_id = None
    empresa.actualizada_en = func.now()  # type: ignore[assignment]
    empresa.actualizada_por = usuario_id
    session.flush()


def leer_logo(session: Session, almacen: Almacen | None, logo_id: uuid.UUID) -> bytes:
    """PNG de un logo del tenant (vigente o de un informe congelado)."""
    almacen = _requerir(almacen)
    logo = session.get(EmpresaLogo, logo_id)
    if logo is None:
        raise SinLogo()
    try:
        return almacen.leer(logo.clave)
    except ObjetoNoEncontrado:
        raise SinLogo() from None
