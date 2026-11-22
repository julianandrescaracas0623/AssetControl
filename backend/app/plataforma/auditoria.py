"""Auditoría de la consola de plataforma (spec 017, T2; R33–R34; plan.md §2.1).

``registrar`` inserta una fila en ``plataforma_auditoria`` **en la sesión de la acción**
(misma transacción: si la acción se revierte, la fila también). El autor es el
desarrollador de la ``plataforma_session`` (RLS exige que coincida con
``app.desarrollador_id`` y que esté activo). Lista cerrada de acciones; sin texto libre,
correos, nombres, IP, contraseñas, tokens ni hashes: solo ids, acción y resultado.
"""

import uuid

from sqlalchemy.orm import Session

from app.db import session_desarrollador
from app.plataforma.models import PlataformaAuditoria

# Lista cerrada de R33 (la misma del CHECK de la migración 0017, ampliado en 0030 con las
# tres acciones del cambio C1: editar la ficha, reemplazar el logo y editar un usuario; y
# en 0032 con la de C1b: definir una contraseña temporal).
ACCIONES: frozenset[str] = frozenset(
    {
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
        "empresa_editada",
        "empresa_logo_reemplazado",
        "usuario_editado",
        # C1b (0032): contraseña temporal de un usuario (sin valores, R57).
        "usuario_contrasena_restablecida",
    }
)
RESULTADOS: frozenset[str] = frozenset({"ok", "rechazado"})


def registrar(
    session: Session,
    accion: str,
    *,
    tenant_id: uuid.UUID | None = None,
    objeto_id: uuid.UUID | None = None,
    resultado: str = "ok",
) -> None:
    """Añade la fila de auditoría a ``session`` (se escribe con su ``flush``/``commit``)."""
    if accion not in ACCIONES:
        raise ValueError("Acción de auditoría fuera de la lista cerrada.")
    if resultado not in RESULTADOS:
        raise ValueError("Resultado de auditoría no válido.")
    session.add(
        PlataformaAuditoria(
            desarrollador_id=session_desarrollador(session),
            accion=accion,
            resultado=resultado,
            tenant_id=tenant_id,
            objeto_id=objeto_id,
        )
    )
