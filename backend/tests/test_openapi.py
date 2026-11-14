"""Contrato OpenAPI escrito a mano (spec 002b, T1; R17/R1, A16; plan.md §2).

``backend/openapi.yaml`` es la fuente de los tipos de la web. Estas pruebas lo atan
al backend real para que no se desvíe:

1. Es OpenAPI 3.1 y todo ``$ref`` resuelve.
2. Las rutas ``(método, ruta)`` de Flask son exactamente las de ``paths``.
3. Cada operación se ejercita sobre una base temporal migrada a ``head`` y cada
   respuesta real se valida contra el esquema declarado para su estado (un estado no
   declarado falla), con sus cabeceras obligatorias y los códigos de error que la
   respuesta lista en ``x-codigos``. Todo estado declarado se ejercita (salvo los de
   ``NOT_EXERCISED``, justificados).
4. El ``enum`` de ``Error.code`` es el conjunto de códigos que define el backend.

El validador cubre solo el subconjunto que usa el contrato; una palabra clave
desconocida falla, para que nadie amplíe el contrato sin ampliar la prueba.
"""

import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from acceso_db import (
    ADMIN_A,
    CONTADOR_A,
    PASSWORD,
    TENANT_A,
    AccesoDb,
    bearer,
    dispose,
    make_app,
    temporary_acceso_db,
)
from flask import Flask
from sqlalchemy import text

import app.meta.routes as meta_routes
from app import errors
from app.auth import limits
from app.auth import routes as auth_routes
from app.auth.credentials import COMMON_PASSWORDS, PasswordPolicyError, check_password_policy
from app.auth.decorators import NOT_AUTHENTICATED
from app.auth.http import AUTH_MAX_BODY_BYTES, CSRF_HEADER, CSRF_HEADER_VALUE
from app.config import RateLimits
from app.invitaciones import routes as invitaciones_routes

CONTRACT_FILE = Path(__file__).resolve().parent.parent / "openapi.yaml"
CSRF = {CSRF_HEADER: CSRF_HEADER_VALUE}
LINK_PREFIX = "/invitacion#"
NEW_PASSWORD = "Clave-Nueva-002b-segura"

# Estados declarados que estas pruebas no provocan, con su motivo.
NOT_EXERCISED = {
    # A22 (spec 002, T9): la cuenta se creó pero emitir la sesión falló; lo cubre
    # test_invitaciones_aceptar.py con un fallo inyectado en la base.
    ("post", "/invitaciones/aceptar", "500"),
}

HTTP_METHODS = {"get", "put", "post", "delete", "patch"}


def load_contract() -> dict:
    return yaml.safe_load(CONTRACT_FILE.read_text(encoding="utf-8"))


CONTRACT = load_contract()


# --- Validador del subconjunto del contrato ------------------------------------------


SCHEMA_KEYWORDS = {
    "$ref",
    "type",
    "properties",
    "required",
    "additionalProperties",
    "enum",
    "const",
    "format",
    "minLength",
    "maxLength",
    "description",
    "example",
    "examples",
    "title",
    "minimum",
}
FORMATS = {"uuid", "date-time", "email", "password"}


def resolve(ref: str) -> dict:
    assert ref.startswith("#/"), ref
    node: object = CONTRACT
    for part in ref.removeprefix("#/").split("/"):
        assert isinstance(node, dict) and part in node, f"$ref sin destino: {ref}"
        node = node[part]
    assert isinstance(node, dict), ref
    return node


def _type_ok(expected: str, value: object) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "null":
        return value is None
    raise AssertionError(f"type no soportado por el validador: {expected}")


def _format_ok(fmt: str, value: str) -> bool:
    if fmt == "uuid":
        try:
            return str(uuid.UUID(value)) == value
        except ValueError:
            return False
    if fmt == "date-time":
        try:
            return datetime.fromisoformat(value).tzinfo is not None
        except ValueError:
            return False
    if fmt == "email":
        return re.fullmatch(r"[^@\s]+@[^@\s]+", value) is not None
    return True  # password: solo indica al cliente que oculte el valor


def validate(schema: dict, value: object, where: str = "$") -> None:
    unknown = set(schema) - SCHEMA_KEYWORDS
    assert not unknown, f"{where}: palabras clave sin soporte en la prueba: {unknown}"
    if "$ref" in schema:
        validate(resolve(schema["$ref"]), value, where)
        return
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        assert any(_type_ok(t, value) for t in types), f"{where}: {value!r} no es {types}"
    if "const" in schema:
        assert value == schema["const"], f"{where}: {value!r} != {schema['const']!r}"
    if "enum" in schema:
        assert value in schema["enum"], f"{where}: {value!r} fuera de {schema['enum']}"
    if isinstance(value, str):
        if "format" in schema:
            assert schema["format"] in FORMATS, f"{where}: formato {schema['format']}"
            assert _format_ok(schema["format"], value), (
                f"{where}: {value!r} no es {schema['format']}"
            )
        if "minLength" in schema:
            assert len(value) >= schema["minLength"], where
        if "maxLength" in schema:
            assert len(value) <= schema["maxLength"], where
    if isinstance(value, int) and "minimum" in schema:
        assert value >= schema["minimum"], where
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            assert name in value, f"{where}: falta {name!r}"
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(properties)
            assert not extra, f"{where}: campos sin documentar {extra}"
        for name, sub in properties.items():
            if name in value:
                validate(sub, value[name], f"{where}.{name}")


# --- 1. Forma del documento ------------------------------------------------------------


def _refs(node: object) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref":
                yield value
            else:
                yield from _refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _refs(item)


def test_contract_is_openapi_31_and_every_ref_resolves():
    assert CONTRACT["openapi"] == "3.1.0"
    assert CONTRACT["info"]["title"] == "AssetControl API"
    refs = list(_refs(CONTRACT))
    assert refs, "el contrato debe reutilizar esquemas"
    for ref in refs:
        resolve(ref)


def test_every_declared_schema_uses_only_supported_keywords():
    for name, schema in CONTRACT["components"]["schemas"].items():
        _walk_schema(schema, f"components.schemas.{name}")


def _walk_schema(schema: dict, where: str) -> None:
    unknown = set(schema) - SCHEMA_KEYWORDS
    assert not unknown, f"{where}: {unknown}"
    for name, sub in schema.get("properties", {}).items():
        _walk_schema(sub, f"{where}.{name}")
    if schema.get("type") == "object" and "properties" in schema:
        assert schema.get("additionalProperties") is False, f"{where}: objeto abierto"


# --- Base temporal y app ---------------------------------------------------------------


@pytest.fixture(scope="module")
def contrato_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("contrato")


@pytest.fixture(scope="module")
def contrato_app(contrato_db) -> Iterator[Flask]:
    flask_app = make_app(
        contrato_db,
        RateLimits(login_account=1000, login_ip=1000, validate_ip=1000, accept_ip=1000),
    )
    yield flask_app
    dispose(flask_app)


@pytest.fixture(autouse=True)
def fresh_rate_limits(contrato_db) -> Iterator[None]:
    with contrato_db.migrator.begin() as conn:
        conn.execute(text("delete from limite_tasa"))
    yield


@pytest.fixture
def client(contrato_app):
    return contrato_app.test_client(use_cookies=False)


# --- 2. Rutas ----------------------------------------------------------------------------


def _flask_operations(flask_app: Flask) -> set[tuple[str, str]]:
    found = set()
    for rule in flask_app.url_map.iter_rules():
        path = re.sub(r"<(?:[^:<>]+:)?([^<>]+)>", r"{\1}", rule.rule)
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            found.add((method.lower(), path))
    return found


def _contract_operations() -> set[tuple[str, str]]:
    return {
        (method, path)
        for path, item in CONTRACT["paths"].items()
        for method in item
        if method in HTTP_METHODS
    }


def test_flask_routes_and_contract_paths_are_the_same(contrato_app):
    assert _flask_operations(contrato_app) == _contract_operations()


# --- 3. Respuestas reales ---------------------------------------------------------------


EXERCISED: set[tuple[str, str, str]] = set()


def check(method: str, path: str, response) -> dict | None:
    """Valida ``response`` contra el contrato y la marca como ejercitada."""
    operation = CONTRACT["paths"][path][method]
    status = str(response.status_code)
    declared = operation["responses"]
    assert status in declared, f"{method.upper()} {path}: {status} no está en el contrato"
    spec = declared[status]
    if "$ref" in spec:
        spec = resolve(spec["$ref"])
    EXERCISED.add((method, path, status))

    for name, header in spec.get("headers", {}).items():
        if header.get("required"):
            assert name in response.headers, f"{method.upper()} {path} {status}: falta {name}"

    content = spec.get("content")
    if content is None:
        assert response.data == b"", f"{method.upper()} {path} {status}: cuerpo no declarado"
        return None
    assert response.mimetype == "application/json"
    body = response.get_json()
    validate(content["application/json"]["schema"], body)
    if "x-codigos" in spec:
        assert body["error"]["code"] in spec["x-codigos"], (method, path, status, body)
    return body


def nuevo_email() -> str:
    return f"contrato.{uuid.uuid4().hex[:10]}@ejemplo.test"


def login(client, email=ADMIN_A.email, password=PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def refresh_cookie(response) -> str:
    header = response.headers["Set-Cookie"]
    return header.split(";", 1)[0]


def invitar(client, rol="contador") -> str:
    response = client.post(
        "/invitaciones",
        json={"email": nuevo_email(), "rol": rol},
        headers=bearer(ADMIN_A, TENANT_A),
    )
    check("post", "/invitaciones", response)
    return response.get_json()["enlace"].removeprefix(LINK_PREFIX)


def test_meta_responses(client, monkeypatch):
    check("get", "/health", client.get("/health"))
    check("get", "/ready", client.get("/ready"))
    monkeypatch.setattr(meta_routes, "ping_database", lambda: False)
    monkeypatch.setattr(meta_routes, "_is_ready", lambda: False)
    check("get", "/health", client.get("/health"))
    check("get", "/ready", client.get("/ready"))


def test_login_responses(client):
    ok = login(client)
    body = check("post", "/auth/login", ok)
    assert body["rol"] == "admin"
    check("post", "/auth/login", login(client, password="Otra-Clave-incorrecta"))
    check("post", "/auth/login", client.post("/auth/login", json={"email": 1}))
    check(
        "post",
        "/auth/login",
        client.post("/auth/login", data="x" * (AUTH_MAX_BODY_BYTES + 1), content_type="text/plain"),
    )


def test_me_responses(client):
    body = check("get", "/auth/me", client.get("/auth/me", headers=bearer(CONTADOR_A, TENANT_A)))
    assert body["rol"] == "contador"
    check("get", "/auth/me", client.get("/auth/me"))


def test_refresh_and_logout_responses(client):
    cookie = refresh_cookie(login(client))
    renewed = client.post("/auth/refresh", headers={**CSRF, "Cookie": cookie})
    check("post", "/auth/refresh", renewed)
    check("post", "/auth/refresh", client.post("/auth/refresh", headers=CSRF))
    check("post", "/auth/refresh", client.post("/auth/refresh", headers={"Cookie": cookie}))
    check(
        "post",
        "/auth/refresh",
        client.post("/auth/refresh", headers=CSRF, data="x" * (AUTH_MAX_BODY_BYTES + 1)),
    )

    check(
        "post",
        "/auth/logout",
        client.post("/auth/logout", headers={**CSRF, "Cookie": refresh_cookie(renewed)}),
    )
    check("post", "/auth/logout", client.post("/auth/logout"))
    check(
        "post",
        "/auth/logout",
        client.post("/auth/logout", headers=CSRF, data="x" * (AUTH_MAX_BODY_BYTES + 1)),
    )


def test_crear_invitacion_responses(client):
    body = client.post(
        "/invitaciones",
        json={"email": nuevo_email(), "rol": "admin"},
        headers=bearer(ADMIN_A, TENANT_A),
    )
    created = check("post", "/invitaciones", body)
    assert created["enlace"].startswith(LINK_PREFIX)
    admin = bearer(ADMIN_A, TENANT_A)
    check("post", "/invitaciones", client.post("/invitaciones", json={"rol": "x"}, headers=admin))
    check("post", "/invitaciones", client.post("/invitaciones", json={}))
    check(
        "post",
        "/invitaciones",
        client.post("/invitaciones", json={}, headers=bearer(CONTADOR_A, TENANT_A)),
    )
    check(
        "post",
        "/invitaciones",
        client.post("/invitaciones", data="x" * (AUTH_MAX_BODY_BYTES + 1), headers=admin),
    )


def test_validar_y_aceptar_responses(client):
    token = invitar(client)
    body = check(
        "post", "/invitaciones/validar", client.post("/invitaciones/validar", json={"token": token})
    )
    assert body == {"vigente": True}
    check("post", "/invitaciones/validar", client.post("/invitaciones/validar", json={"token": 1}))
    check(
        "post",
        "/invitaciones/validar",
        client.post("/invitaciones/validar", data="x" * (AUTH_MAX_BODY_BYTES + 1)),
    )

    def aceptar(password=NEW_PASSWORD, tok=token, **extra):
        body = {"token": tok, "nombre": "Persona Sintética", "password": password, **extra}
        return client.post("/invitaciones/aceptar", json=body)

    for bad in ("corta", "x" * 200, next(iter(COMMON_PASSWORDS))):
        check("post", "/invitaciones/aceptar", aceptar(password=bad))
    check("post", "/invitaciones/aceptar", aceptar(tok="no-existe"))
    check("post", "/invitaciones/aceptar", client.post("/invitaciones/aceptar", json={"token": 1}))
    check(
        "post",
        "/invitaciones/aceptar",
        client.post("/invitaciones/aceptar", data="x" * (AUTH_MAX_BODY_BYTES + 1)),
    )
    accepted = check("post", "/invitaciones/aceptar", aceptar())
    assert accepted["rol"] == "contador"


LIMITED = [
    ("post", "/auth/login", {"email": ADMIN_A.email, "password": PASSWORD}, {}),
    ("post", "/auth/refresh", None, CSRF),
    ("post", "/invitaciones/validar", {"token": "x"}, {}),
    ("post", "/invitaciones/aceptar", {"token": "x", "nombre": "N", "password": NEW_PASSWORD}, {}),
]


@pytest.mark.parametrize(("method", "path", "body", "headers"), LIMITED)
def test_rate_limited_responses(client, monkeypatch, method, path, body, headers):
    def exceeded(items, window_seconds):
        now = datetime.now(UTC)
        return [limits.Counter(ambito, key, now, limit + 1, limit) for ambito, key, limit in items]

    def unavailable(items, window_seconds):
        raise RuntimeError("base caída (sintético)")

    monkeypatch.setattr(limits, "increment_attempts", exceeded)
    check(method, path, client.open(path, method=method, json=body, headers=headers))
    monkeypatch.setattr(limits, "increment_attempts", unavailable)
    check(method, path, client.open(path, method=method, json=body, headers=headers))


def test_every_declared_response_is_exercised(request):
    """Va al final del módulo: usa lo que marcaron las pruebas anteriores."""
    module = request.node.module.__name__
    selected = {item.name for item in request.session.items if item.module.__name__ == module}
    exercising = {name for name in dir(request.node.module) if name.endswith("_responses")}
    if not {name for name in exercising if name.startswith("test_")} <= {
        name.split("[", 1)[0] for name in selected
    }:
        pytest.skip("solo tiene sentido con todo el módulo seleccionado")
    declared = {
        (method, path, status)
        for path, item in CONTRACT["paths"].items()
        for method, operation in item.items()
        if method in HTTP_METHODS
        for status in operation["responses"]
    }
    assert NOT_EXERCISED <= declared
    assert declared - NOT_EXERCISED - EXERCISED == set()


# --- 4. Códigos de error -----------------------------------------------------------------


def _policy_codes() -> set[str]:
    codes = set()
    for password in ("\ud800", "corta", "x" * 200, next(iter(COMMON_PASSWORDS))):
        with pytest.raises(PasswordPolicyError) as raised:
            check_password_policy(password)
        codes.add(raised.value.code)
    return codes


def backend_error_codes() -> set[str]:
    codes = {code for code, _ in errors._HTTP_ERRORS.values()}
    codes |= {
        "error_http",  # estado HTTP sin código propio (errors._handle_http_exception)
        errors.INTERNAL_ERROR_CODE,
        errors.SERVICE_UNAVAILABLE[0],
        errors.TOO_MANY_REQUESTS[0],
        NOT_AUTHENTICATED[0],
        auth_routes.INVALID_CREDENTIALS[0],
        auth_routes.BAD_REQUEST[0],
        invitaciones_routes.INVALID_INVITATION[0],
    }
    return codes | _policy_codes()


def test_error_code_enum_is_the_backend_set():
    enum = CONTRACT["components"]["schemas"]["ErrorCode"]["enum"]
    assert len(enum) == len(set(enum))
    assert set(enum) == backend_error_codes()


def test_error_codes_listed_per_response_exist():
    enum = set(CONTRACT["components"]["schemas"]["ErrorCode"]["enum"])
    for path, item in CONTRACT["paths"].items():
        for method, operation in item.items():
            if method not in HTTP_METHODS:
                continue
            for status, spec in operation["responses"].items():
                if "$ref" in spec:
                    spec = resolve(spec["$ref"])
                assert set(spec.get("x-codigos", [])) <= enum, (method, path, status)
