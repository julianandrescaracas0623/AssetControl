"""Autorización por rol (spec 002, T8; R9, A12, A24, A25; plan.md §2.2, §4).

``require_auth`` y ``require_role`` sobre una base temporal migrada a ``head`` con
dos tenants sintéticos (A y B):

- El JWT solo propone ``sub`` y ``tenant``: bajo ``tenant_session`` de ese tenant
  se leen ``membresia`` (``rol``, ``activa``) y ``usuario.activo`` **en cada
  petición**. El ``rol`` del claim no autoriza; tampoco el cuerpo, la URL ni las
  cabeceras.
- Sin token o inválido (``alg: none``, otro algoritmo, sin ``exp``/``iss``, ``iss``
  ajeno, vencido, otra clave, ``tenant`` forjado) -> ``401`` ``no_autenticado``.
- Rol insuficiente -> ``403`` ``prohibido`` (plan.md §2.2).
- A24: un cambio de rol o una baja tras emitir el token se ve en la siguiente
  petición.
- N5 (deuda de T6): la petición abre **una** sola ``tenant_session``; el handler
  usa la misma en la que se leyó el rol (sin ventana entre la lectura del rol y
  la de los datos).
- Catálogo: todo endpoint es público por una lista cerrada o declara sus roles,
  y cada endpoint protegido figura aquí con su prueba de rol y aislamiento.
- O2 (deuda de T7): ``/auth/*`` e ``/invitaciones`` no responden cabeceras
  ``Access-Control-*`` (sin CORS: el preflight de la cabecera personalizada no
  se valida).
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from acceso_db import (
    ADMIN_A,
    ADMIN_B,
    CAMBIANTE_A,
    CONTADOR_A,
    CONTADOR_B,
    TENANT_A,
    TENANT_B,
    AccesoDb,
    base_claims,
    bearer,
    dispose,
    forged_token,
    invitaciones_de,
    make_app,
    migrator_execute,
    temporary_acceso_db,
)
from flask import Flask

from app.auth import decorators
from app.auth.decorators import require_auth, require_role

INVITAR = "/invitaciones"
ME = "/auth/me"


@pytest.fixture(scope="module")
def roles_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("roles")


@pytest.fixture(scope="module")
def roles_app(roles_db) -> Iterator[Flask]:
    flask_app = make_app(roles_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(roles_app):
    return roles_app.test_client(use_cookies=False)


@pytest.fixture
def toggle(roles_db):
    """Ejecuta un cambio con el migrador y lo deshace al terminar."""
    restore: list[tuple[str, dict]] = []

    def apply(sql: str, undo: str, params: dict) -> None:
        migrator_execute(roles_db, sql, params)
        restore.append((undo, params))

    yield apply
    for undo, params in reversed(restore):
        migrator_execute(roles_db, undo, params)


def invitar(client, headers: dict, body: dict | None = None, **kwargs):
    payload = {"email": f"nuevo.{uuid.uuid4().hex[:8]}@ejemplo.test", "rol": "contador"}
    if body is not None:
        payload = body
    return client.post(INVITAR, json=payload, headers=headers, **kwargs)


def error_code(response) -> str:
    return response.get_json()["error"]["code"]


# --- 401: sin token o token inválido (A25, R9) --------------------------------------


def _now() -> datetime:
    return datetime.now(UTC)


def _claims(**changes) -> dict:
    claims = base_claims(ADMIN_A, TENANT_A)
    for key, value in changes.items():
        if value is None:
            claims.pop(key, None)
        else:
            claims[key] = value
    return claims


INVALID_AUTHORIZATION = {
    "sin_cabecera": None,
    "vacia": "",
    "sin_bearer": "__TOKEN__",
    "basic": "Basic YWRtaW46YWRtaW4=",
    "bearer_vacio": "Bearer ",
    "basura": "Bearer no-es-un-jwt",
    "alg_none": "none",
    "hs512": "hs512",
    "otra_clave": "otra_clave",
    "sin_exp": "sin_exp",
    "sin_iss": "sin_iss",
    "iss_ajeno": "iss_ajeno",
    "vencido": "vencido",
    "sin_sub": "sin_sub",
    "sin_tenant": "sin_tenant",
    "sub_no_uuid": "sub_no_uuid",
    "tenant_no_uuid": "tenant_no_uuid",
}


def _authorization(case: str) -> str | None:
    value = INVALID_AUTHORIZATION[case]
    if value in (None, "", "Basic YWRtaW46YWRtaW4=", "Bearer ", "Bearer no-es-un-jwt"):
        return value
    if value == "__TOKEN__":
        return bearer(ADMIN_A, TENANT_A)["Authorization"].removeprefix("Bearer ")
    if value == "none":
        token = forged_token(_claims(), key=None, algorithm="none")
    elif value == "hs512":
        token = forged_token(_claims(), algorithm="HS512")
    elif value == "otra_clave":
        token = forged_token(_claims(), key=b"x" * 32)
    elif value == "sin_exp":
        token = forged_token(_claims(exp=None))
    elif value == "sin_iss":
        token = forged_token(_claims(iss=None))
    elif value == "iss_ajeno":
        token = forged_token(_claims(iss="otro-emisor"))
    elif value == "vencido":
        token = forged_token(_claims(exp=int((_now() - timedelta(minutes=1)).timestamp())))
    elif value == "sin_sub":
        token = forged_token(_claims(sub=None))
    elif value == "sin_tenant":
        token = forged_token(_claims(tenant=None))
    elif value == "sub_no_uuid":
        token = forged_token(_claims(sub="admin"))
    else:
        token = forged_token(_claims(tenant="tenant-a"))
    return f"Bearer {token}"


@pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")
@pytest.mark.parametrize("path", [INVITAR, ME])
@pytest.mark.parametrize("case", sorted(INVALID_AUTHORIZATION))
def test_missing_or_invalid_token_is_401(client, roles_db, path, case):
    authorization = _authorization(case)
    headers = {} if authorization is None else {"Authorization": authorization}
    before = invitaciones_de(roles_db, TENANT_A)

    if path == INVITAR:
        response = invitar(client, headers)
    else:
        response = client.get(path, headers=headers)

    assert response.status_code == 401
    assert error_code(response) == "no_autenticado"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert invitaciones_de(roles_db, TENANT_A) == before


def test_tenant_a_with_a_sub_that_only_belongs_to_b_is_401(client, roles_db):
    """JWT bien firmado con ``tenant`` A y ``sub`` de B: no hay membresía en A."""
    before = invitaciones_de(roles_db, TENANT_A)

    for path in (INVITAR, ME):
        headers = bearer(ADMIN_B, TENANT_A, rol="admin")
        response = (
            invitar(client, headers) if path == INVITAR else client.get(path, headers=headers)
        )
        assert response.status_code == 401, path
        assert error_code(response) == "no_autenticado"

    assert invitaciones_de(roles_db, TENANT_A) == before


def test_tenant_that_does_not_exist_is_401(client):
    headers = bearer(ADMIN_A, uuid.UUID("00000000-0000-4000-8000-00000000dead"), rol="admin")

    assert invitar(client, headers).status_code == 401
    assert client.get(ME, headers=headers).status_code == 401


@pytest.mark.parametrize(
    ("sql", "undo"),
    [
        (
            "update membresia set activa = false where tenant_id = :t and usuario_id = :u",
            "update membresia set activa = true where tenant_id = :t and usuario_id = :u",
        ),
        (
            "update usuario set activo = false where id = :u",
            "update usuario set activo = true where id = :u",
        ),
    ],
    ids=["membresia_inactiva", "usuario_inactivo"],
)
def test_deactivation_after_issuing_the_token_is_401_on_the_next_request(
    client, roles_db, toggle, sql, undo
):
    """A24: la baja se ve en la siguiente petición aunque el JWT siga vigente."""
    headers = bearer(CAMBIANTE_A, TENANT_A, rol="admin")
    assert client.get(ME, headers=headers).status_code == 200
    toggle(sql, undo, {"t": TENANT_A, "u": CAMBIANTE_A.usuario_id})
    before = invitaciones_de(roles_db, TENANT_A)

    assert invitar(client, headers).status_code == 401
    assert client.get(ME, headers=headers).status_code == 401
    assert invitaciones_de(roles_db, TENANT_A) == before


# --- 403: rol insuficiente (R9, A12) -------------------------------------------------


@pytest.mark.parametrize(
    ("cuenta", "tenant"), [(CONTADOR_A, TENANT_A), (CONTADOR_B, TENANT_B)], ids=["A", "B"]
)
def test_contador_gets_403_prohibido_on_admin_routes(client, roles_db, cuenta, tenant):
    before = invitaciones_de(roles_db, tenant)

    response = invitar(client, bearer(cuenta, tenant, rol="contador"))

    assert response.status_code == 403
    assert error_code(response) == "prohibido"
    assert response.get_json()["error"]["message"] == "No tienes permiso para esta acción."
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert invitaciones_de(roles_db, tenant) == before


def test_role_from_the_claim_does_not_authorize(client, roles_db):
    """Un ``contador`` con ``rol: admin`` en el claim (bien firmado) sigue siendo contador."""
    before = invitaciones_de(roles_db, TENANT_A)

    response = invitar(client, bearer(CONTADOR_A, TENANT_A, rol="admin"))

    assert response.status_code == 403
    assert invitaciones_de(roles_db, TENANT_A) == before


def test_admin_without_role_claim_is_still_admin(client):
    """El rol sale de ``membresia``: el claim ``rol`` puede faltar o mentir."""
    assert invitar(client, bearer(ADMIN_A, TENANT_A, rol=None)).status_code == 201
    assert invitar(client, bearer(ADMIN_A, TENANT_A, rol="contador")).status_code == 201


@pytest.mark.parametrize(
    "extra",
    [
        {"headers": {"X-Rol": "admin", "X-Role": "admin", "X-Tenant-ID": str(TENANT_A)}},
        {"query_string": {"rol": "admin", "role": "admin", "tenant_id": str(TENANT_A)}},
        {"body": {"rol": "admin", "role": "admin", "es_admin": True}},
    ],
    ids=["cabecera", "query", "cuerpo"],
)
def test_role_from_the_request_does_not_authorize(client, roles_db, extra):
    before = invitaciones_de(roles_db, TENANT_A)
    headers = {**bearer(CONTADOR_A, TENANT_A, rol="contador"), **extra.get("headers", {})}
    body = {"email": "ignorado.a8@ejemplo.test", "rol": "contador", **extra.get("body", {})}

    response = client.post(
        INVITAR, json=body, headers=headers, query_string=extra.get("query_string")
    )

    assert response.status_code == 403
    assert invitaciones_de(roles_db, TENANT_A) == before


def test_role_change_after_issuing_the_token_is_seen_on_the_next_request(client, toggle):
    """A24: admin -> contador da 403 en la siguiente petición; y al revés, 201."""
    admin_token = bearer(CAMBIANTE_A, TENANT_A, rol="admin")
    assert invitar(client, admin_token).status_code == 201

    toggle(
        "update membresia set rol = 'contador' where tenant_id = :t and usuario_id = :u",
        "update membresia set rol = 'admin' where tenant_id = :t and usuario_id = :u",
        {"t": TENANT_A, "u": CAMBIANTE_A.usuario_id},
    )
    response = invitar(client, admin_token)
    assert response.status_code == 403
    assert client.get(ME, headers=admin_token).get_json()["rol"] == "contador"


def test_promotion_after_issuing_the_token_is_seen_on_the_next_request(client, toggle):
    contador_token = bearer(CONTADOR_A, TENANT_A, rol="contador")
    assert invitar(client, contador_token).status_code == 403

    toggle(
        "update membresia set rol = 'admin' where tenant_id = :t and usuario_id = :u",
        "update membresia set rol = 'contador' where tenant_id = :t and usuario_id = :u",
        {"t": TENANT_A, "u": CONTADOR_A.usuario_id},
    )

    assert invitar(client, contador_token).status_code == 201


def test_auth_me_accepts_both_roles(client):
    for cuenta, rol in ((ADMIN_A, "admin"), (CONTADOR_A, "contador")):
        response = client.get(ME, headers=bearer(cuenta, TENANT_A))
        assert response.status_code == 200
        assert response.get_json()["rol"] == rol
        assert response.get_json()["tenant"]["id"] == str(TENANT_A)


def test_auth_me_ignores_tenant_from_query_and_headers(client):
    response = client.get(
        ME,
        headers={**bearer(ADMIN_A, TENANT_A), "X-Tenant-ID": str(TENANT_B)},
        query_string={"tenant_id": str(TENANT_B), "tenant": str(TENANT_B)},
    )

    assert response.status_code == 200
    assert response.get_json()["tenant"]["id"] == str(TENANT_A)


# --- N5: una sola tenant_session por petición ---------------------------------------


def test_the_handler_reuses_the_session_where_the_role_was_read(client, monkeypatch):
    opened = []
    original = decorators.tenant_session

    def spy(tenant_id):
        opened.append(tenant_id)
        return original(tenant_id)

    monkeypatch.setattr(decorators, "tenant_session", spy)

    assert invitar(client, bearer(ADMIN_A, TENANT_A)).status_code == 201
    assert client.get(ME, headers=bearer(CONTADOR_A, TENANT_A)).status_code == 200

    assert opened == [TENANT_A, TENANT_A]


def test_current_user_and_session_are_only_available_inside_a_protected_view(roles_app):
    with roles_app.test_request_context("/"):
        with pytest.raises(RuntimeError):
            decorators.current_user()
        with pytest.raises(RuntimeError):
            decorators.current_session()


# --- Declaración de roles y catálogo de endpoints (A12) ------------------------------


def test_require_role_rejects_unknown_or_missing_roles():
    with pytest.raises(ValueError):
        require_role()
    with pytest.raises(ValueError):
        require_role("superadmin")
    with pytest.raises(ValueError):
        require_role("Admin")


def test_decorators_declare_their_roles():
    @require_role("admin")
    def solo_admin():
        return ""

    @require_auth
    def cualquiera():
        return ""

    assert solo_admin.required_roles == frozenset({"admin"})
    assert cualquiera.required_roles == frozenset({"admin", "contador"})


# Endpoints sin token, cerrados. Añadir uno aquí exige justificarlo en la spec.
PUBLIC_ENDPOINTS = frozenset({"static", "meta.health", "auth.login", "auth.refresh", "auth.logout"})
# Todo endpoint protegido, con sus roles. Añadir uno exige su prueba de rol (401/403)
# y de aislamiento (A12) en este archivo o en el de su recurso.
PROTECTED_ENDPOINTS = {
    "auth.me": frozenset({"admin", "contador"}),  # test_auth_me_*, test_tenant_a_with_*
    "invitaciones.crear": frozenset({"admin"}),  # test_contador_*, test_invitaciones_crear
}


def test_every_endpoint_is_public_by_list_or_declares_its_roles(roles_app):
    found = {}
    undeclared = []
    for endpoint, view in roles_app.view_functions.items():
        if endpoint in PUBLIC_ENDPOINTS:
            assert not hasattr(view, "required_roles"), endpoint
            continue
        roles = getattr(view, "required_roles", None)
        if roles is None:
            undeclared.append(endpoint)
        else:
            found[endpoint] = roles

    assert undeclared == [], f"Endpoints sin require_auth/require_role: {undeclared}"
    assert found == PROTECTED_ENDPOINTS
    assert PUBLIC_ENDPOINTS <= set(roles_app.view_functions)


# --- O2: sin CORS en /auth/* ni /invitaciones ----------------------------------------


def _access_control(response) -> list[str]:
    return [name for name in response.headers.keys() if name.lower().startswith("access-control-")]


def _auth_rules(flask_app: Flask) -> list[str]:
    return sorted(
        {
            rule.rule
            for rule in flask_app.url_map.iter_rules()
            if rule.rule.startswith(("/auth", "/invitaciones"))
        }
    )


def test_there_are_auth_routes_to_check(roles_app):
    assert {"/auth/login", "/auth/refresh", "/auth/logout", ME, INVITAR} <= set(
        _auth_rules(roles_app)
    )


@pytest.mark.parametrize(
    "path", ["/auth/login", "/auth/refresh", "/auth/logout", "/auth/me", "/invitaciones"]
)
def test_no_cors_headers_nor_valid_preflight(client, path):
    origin = "https://sitio-ajeno.example"
    preflight = client.options(
        path,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-assetcontrol-csrf, authorization, content-type",
        },
    )
    actual = client.post(
        path,
        json={},
        headers={"Origin": origin, **bearer(ADMIN_A, TENANT_A)},
    )
    got = client.get(path, headers={"Origin": origin})

    for response in (preflight, actual, got):
        assert _access_control(response) == [], (path, response.status_code)


def test_all_auth_rules_are_covered_by_the_cors_test(roles_app):
    covered = {"/auth/login", "/auth/refresh", "/auth/logout", "/auth/me", "/invitaciones"}
    assert set(_auth_rules(roles_app)) == covered
