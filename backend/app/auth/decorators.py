"""Autorización por rol (spec 002, T8; R9, A12, A24; plan.md §2.2).

``require_role("admin")`` (o ``require_auth`` para cualquier rol) protege una
vista:

1. Valida el ``Authorization: Bearer <jwt>`` (``HS256`` fijo, ``exp``, ``iss``,
   ``sub``, ``tenant``). Sin token o inválido -> ``401`` ``no_autenticado``.
2. Abre **una** ``tenant_session`` con el ``tenant`` del claim y en ella lee
   ``membresia`` (``rol``, ``activa``) y ``usuario.activo`` en cada petición. El
   ``rol`` del claim es solo informativo y nunca se usa; el cuerpo, la URL y las
   cabeceras no proponen tenant ni rol. Sin membresía activa en ese tenant ->
   ``401``.
3. Rol fuera de los declarados -> ``403`` ``prohibido`` (``abort(403)``).
4. La vista corre **dentro de esa misma transacción** (N5 de T6): sin ventana
   entre la lectura del rol y la de los datos. Toma la sesión con
   ``current_session()`` y el usuario con ``current_user()``. La transacción se
   confirma al volver la vista; si confirmar falla la respuesta no sale (``500``)
   y, si la vista lanza, se revierte.

La vista decorada expone ``required_roles`` (``frozenset``): la prueba de
catálogo de ``test_roles.py`` exige que todo endpoint no público lo declare.
"""

from collections.abc import Callable
from functools import wraps
from typing import Any

from flask import abort, g, request
from sqlalchemy.orm import Session

from app.auth import service
from app.db import tenant_session
from app.errors import error_response

ROLES: frozenset[str] = frozenset({"admin", "contador"})
NOT_AUTHENTICATED = ("no_autenticado", "Debes iniciar sesión.")

_USER_KEY = "auth_current_user"
_SESSION_KEY = "auth_tenant_session"


def require_role(*roles: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Exige una membresía activa con uno de ``roles`` en el tenant del token."""
    allowed = frozenset(roles)
    if not allowed or not allowed <= ROLES:
        raise ValueError("require_role necesita uno o más roles de la lista cerrada.")

    def decorator(view: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(view)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            claims = service.access_claims(request.headers.get("Authorization"))
            if claims is None:
                return error_response(401, *NOT_AUTHENTICATED)
            with tenant_session(claims.tenant) as session:
                user = service.load_current_user(session, claims.sub, claims.tenant)
                if user is None:
                    return error_response(401, *NOT_AUTHENTICATED)
                if user.rol not in allowed:
                    abort(403)
                setattr(g, _USER_KEY, user)
                setattr(g, _SESSION_KEY, session)
                try:
                    return view(*args, **kwargs)
                finally:
                    # Ni la sesión ni el usuario sobreviven a la vista (H4 de T8): no los
                    # ven los after_request ni otro código de la misma petición.
                    g.pop(_SESSION_KEY, None)
                    g.pop(_USER_KEY, None)

        wrapped.required_roles = allowed  # type: ignore[attr-defined]
        return wrapped

    return decorator


require_auth = require_role(*sorted(ROLES))


def current_user() -> service.CurrentUser:
    """Usuario autenticado de la vista protegida en curso."""
    user = g.get(_USER_KEY)
    if user is None:
        raise RuntimeError("current_user() solo existe dentro de una vista protegida.")
    return user


def current_session() -> Session:
    """``tenant_session`` en la que se leyó el rol (N5); solo dentro de la vista."""
    session = g.get(_SESSION_KEY)
    if session is None:
        raise RuntimeError("current_session() solo existe dentro de una vista protegida.")
    return session
