"""Autorización de la consola de plataforma (spec 017, T2; R4, R5; plan.md §2.1).

``require_desarrollador`` protege una vista de ``/plataforma``:

1. Valida el ``Authorization: Bearer <jwt>`` de plataforma (clave y ``typ`` propios, sin
   ``tenant``). Sin token, inválido o de tenant -> ``401`` ``no_autenticado``.
2. Abre **una** ``plataforma_session`` con el ``sub`` del token y en ella lee
   ``desarrollador.activo`` y que la familia de refresh del token no esté revocada, en
   cada petición. Si no -> ``401``.
3. La vista corre dentro de esa misma transacción (como ``require_role`` de la 002):
   ``current_plataforma_session()`` y ``current_desarrollador()``. Ni la sesión ni el
   desarrollador sobreviven a la vista.

La vista decorada expone ``required_roles = frozenset({"desarrollador"})``: el catálogo de
``test_plataforma_aislamiento.py`` exige que todo endpoint no público de ``/plataforma``
lo declare. ``desarrollador`` no está en ``ROLES`` del tenant: ningún ``require_role`` lo
acepta.
"""

from collections.abc import Callable
from functools import wraps
from typing import Any

from flask import g, request
from sqlalchemy.orm import Session

from app.db import plataforma_session
from app.errors import error_response
from app.plataforma import servicio

ROL_DESARROLLADOR = "desarrollador"
NOT_AUTHENTICATED = ("no_autenticado", "Debes iniciar sesión.")

_DEV_KEY = "plataforma_current_desarrollador"
_SESSION_KEY = "plataforma_session"


def require_desarrollador(view: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(view)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        claims = servicio.platform_claims(request.headers.get("Authorization"))
        if claims is None:
            return error_response(401, *NOT_AUTHENTICATED)
        with plataforma_session(claims.sub) as session:
            desarrollador = servicio.load_current_desarrollador(session, claims)
            if desarrollador is None:
                return error_response(401, *NOT_AUTHENTICATED)
            setattr(g, _DEV_KEY, desarrollador)
            setattr(g, _SESSION_KEY, session)
            try:
                return view(*args, **kwargs)
            finally:
                g.pop(_SESSION_KEY, None)
                g.pop(_DEV_KEY, None)

    wrapped.required_roles = frozenset({ROL_DESARROLLADOR})  # type: ignore[attr-defined]
    return wrapped


def current_desarrollador() -> servicio.CurrentDesarrollador:
    """Desarrollador autenticado de la vista protegida en curso."""
    desarrollador = g.get(_DEV_KEY)
    if desarrollador is None:
        raise RuntimeError("current_desarrollador() solo existe dentro de una vista protegida.")
    return desarrollador


def current_plataforma_session() -> Session:
    """``plataforma_session`` en la que se leyó el desarrollador; solo dentro de la vista."""
    session = g.get(_SESSION_KEY)
    if session is None:
        raise RuntimeError(
            "current_plataforma_session() solo existe dentro de una vista protegida."
        )
    return session
