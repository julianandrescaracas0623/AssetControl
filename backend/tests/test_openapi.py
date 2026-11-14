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
from datetime import UTC, date, datetime
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
from app.activos import cambios as activos_cambios
from app.activos import service as activos_service
from app.auth import limits
from app.auth import routes as auth_routes
from app.auth.credentials import COMMON_PASSWORDS, PasswordPolicyError, check_password_policy
from app.auth.decorators import NOT_AUTHENTICATED
from app.auth.http import AUTH_MAX_BODY_BYTES, CSRF_HEADER, CSRF_HEADER_VALUE
from app.catalogo import service as catalogo_service
from app.config import RateLimits
from app.conteo import service as conteo_service
from app.conteo import verificaciones as conteo_verificaciones
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
    "items",
    "oneOf",
}
FORMATS = {"uuid", "date-time", "date", "email", "password"}


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
    if fmt == "date":
        try:
            return date.fromisoformat(value).isoformat() == value
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
    if "oneOf" in schema:
        coinciden = 0
        for option in schema["oneOf"]:
            try:
                validate(option, value, where)
            except AssertionError:
                continue
            coinciden += 1
        assert coinciden == 1, f"{where}: {value!r} cumple {coinciden} opciones de oneOf"
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
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            validate(schema["items"], item, f"{where}[{index}]")
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


def test_one_of_accepts_exactly_one_option():
    schema = {"oneOf": [{"type": "string"}, {"type": "null"}]}
    validate(schema, "x")
    validate(schema, None)
    with pytest.raises(AssertionError):
        validate(schema, 3)
    with pytest.raises(AssertionError):
        validate({"oneOf": [{"type": "string"}, {"type": "string"}]}, "x")


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
    if "items" in schema:
        _walk_schema(schema["items"], f"{where}[]")
    for index, option in enumerate(schema.get("oneOf", [])):
        _walk_schema(option, f"{where}.oneOf[{index}]")
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


def test_ubicaciones_responses(client):
    admin, contador = bearer(ADMIN_A, TENANT_A), bearer(CONTADOR_A, TENANT_A)
    grande = "x" * (AUTH_MAX_BODY_BYTES + 1)

    def crear(body, headers=admin):
        response = client.post("/ubicaciones", json=body, headers=headers)
        return check("post", "/ubicaciones", response)

    sede = crear({"nombre": f"Sede {uuid.uuid4().hex[:6]}", "tipo": "sede"})["ubicacion"]
    sala = crear({"nombre": "Sala", "tipo": "sala", "padre_id": sede["id"]})["ubicacion"]
    crear({"nombre": "", "tipo": "sede"})
    crear({"nombre": "Box", "tipo": "box", "padre_id": sede["id"]})
    crear({"nombre": "Sala", "tipo": "sala", "padre_id": sede["id"]})
    crear({"nombre": "X", "tipo": "sala", "padre_id": str(uuid.uuid4())})
    crear({"nombre": "X", "tipo": "sede"}, headers={})
    crear({"nombre": "X", "tipo": "sede"}, headers=contador)
    check("post", "/ubicaciones", client.post("/ubicaciones", data=grande, headers=admin))

    check("get", "/ubicaciones", client.get("/ubicaciones", headers=contador))
    check("get", "/ubicaciones", client.get("/ubicaciones"))

    def patch(ubicacion_id, body, headers=admin):
        response = client.patch(f"/ubicaciones/{ubicacion_id}", json=body, headers=headers)
        return check("patch", "/ubicaciones/{id}", response)

    patch(sala["id"], {"nombre": "Sala renombrada"})
    patch(sala["id"], {})
    patch(sede["id"], {"activa": False})
    patch(sala["id"], {"nombre": "X"}, headers={})
    patch(sala["id"], {"nombre": "X"}, headers=contador)
    patch(uuid.uuid4(), {"nombre": "X"})
    path = f"/ubicaciones/{sala['id']}"
    check("patch", "/ubicaciones/{id}", client.patch(path, data=grande, headers=admin))


def test_categorias_responses(client):
    admin, contador = bearer(ADMIN_A, TENANT_A), bearer(CONTADOR_A, TENANT_A)
    grande = "x" * (AUTH_MAX_BODY_BYTES + 1)

    def crear(body, headers=admin):
        return check("post", "/categorias", client.post("/categorias", json=body, headers=headers))

    nombre = f"Categoría {uuid.uuid4().hex[:6]}"
    categoria = crear({"nombre": nombre})["categoria"]
    crear({"nombre": nombre.upper()})
    crear({"nombre": ""})
    crear({"nombre": "X"}, headers={})
    crear({"nombre": "X"}, headers=contador)
    check("post", "/categorias", client.post("/categorias", data=grande, headers=admin))
    check("get", "/categorias", client.get("/categorias", headers=contador))
    check("get", "/categorias", client.get("/categorias"))

    def patch(categoria_id, body, headers=admin):
        response = client.patch(f"/categorias/{categoria_id}", json=body, headers=headers)
        return check("patch", "/categorias/{id}", response)

    otra = crear({"nombre": f"Otra {uuid.uuid4().hex[:6]}"})["categoria"]
    patch(categoria["id"], {"nombre": f"{nombre} renombrada"})
    patch(categoria["id"], {"nombre": otra["nombre"]})
    patch(categoria["id"], {})
    patch(categoria["id"], {"nombre": "X"}, headers={})
    patch(categoria["id"], {"nombre": "X"}, headers=contador)
    patch(uuid.uuid4(), {"nombre": "X"})
    path = f"/categorias/{categoria['id']}"
    check("patch", "/categorias/{id}", client.patch(path, data=grande, headers=admin))

    sugeridas = "/categorias/sugeridas"
    check("post", sugeridas, client.post(sugeridas, headers=admin))
    check("post", sugeridas, client.post(sugeridas))
    check("post", sugeridas, client.post(sugeridas, headers=contador))


def test_activos_responses(client, contrato_db):
    admin, contador = bearer(ADMIN_A, TENANT_A), bearer(CONTADOR_A, TENANT_A)
    sufijo = uuid.uuid4().hex[:6]

    def post(path, body):
        response = client.post(path, json=body, headers=admin)
        assert response.status_code == 201, response.get_json()
        return response.get_json()

    sede = post("/ubicaciones", {"nombre": f"Sede {sufijo}", "tipo": "sede"})["ubicacion"]["id"]
    sala = post("/ubicaciones", {"nombre": "Sala", "tipo": "sala", "padre_id": sede})["ubicacion"]
    categoria = post("/categorias", {"nombre": f"Cat {sufijo}"})["categoria"]["id"]
    body = {
        "id": str(uuid.uuid4()),
        "codigo": f"OA-{sufijo}",
        "nombre": "Activo del contrato",
        "precio_compra": "100.00",
        "categoria_id": categoria,
        "ubicacion_id": sala["id"],
        "fecha_compra": "2024-01-31",
    }

    def alta(payload, headers=admin):
        return check("post", "/activos", client.post("/activos", json=payload, headers=headers))

    alta(body)
    alta(body)
    duplicado = {"id": str(uuid.uuid4()), "codigo": f"OD-{sufijo}", "copiar_de": body["id"]}
    alta(duplicado, headers=contador)
    alta({**body, "id": str(uuid.uuid4()), "codigo": f"oa-{sufijo}"})
    alta({**body, "id": str(uuid.uuid4()), "codigo": "con espacio"})
    alta(
        {
            **body,
            "id": str(uuid.uuid4()),
            "codigo": f"OB-{sufijo}",
            "categoria_id": str(uuid.uuid4()),
        }
    )
    alta(body, headers={})
    check(
        "post",
        "/activos",
        client.post("/activos", data="x" * (AUTH_MAX_BODY_BYTES + 1), headers=admin),
    )

    def por_codigo(codigo, headers=admin):
        response = client.get(
            "/activos/por-codigo", query_string={"codigo": codigo}, headers=headers
        )
        return check("get", "/activos/por-codigo", response)

    por_codigo(body["codigo"], headers=contador)
    por_codigo("NO-EXISTE")
    por_codigo("con espacio")
    por_codigo("X", headers={})

    for headers in (admin, contador, {}):
        check("get", "/activos/{id}", client.get(f"/activos/{body['id']}", headers=headers))
    check("get", "/activos/{id}", client.get(f"/activos/{uuid.uuid4()}", headers=admin))

    for params, headers in (
        ({"q": "contrato"}, admin),
        ({"pagina": "2"}, contador),
        ({"estado": "otro"}, admin),
        ({}, {}),
    ):
        check("get", "/activos", client.get("/activos", query_string=params, headers=headers))
    sugerencias = "/activos/sugerencias"
    for params, headers in (
        ({"campo": "nombre", "q": "act"}, contador),
        ({"campo": "precio_compra"}, admin),
        ({"campo": "nombre"}, {}),
    ):
        check("get", sugerencias, client.get(sugerencias, query_string=params, headers=headers))

    # Spec 005, T2: editar (solo admin, con If-Match).
    ruta = f"/activos/{body['id']}"

    def editar(payload, headers=admin, version="1", **kwargs):
        extra = {"If-Match": f'"{version}"'} if version is not None else {}
        response = client.patch(ruta, json=payload, headers={**headers, **extra}, **kwargs)
        return check("patch", "/activos/{id}", response)

    assert (
        editar({"nombre": "Activo editado", "precio_compra": "120.00"})["activo"]["row_version"]
        == 2
    )
    assert editar({"nombre": "Viejo"})["error"]["code"] == "version_desactualizada"
    assert editar({"nombre": "X"}, version=None)["error"]["code"] == "falta_version"
    assert editar({"codigo": "OTRO"}, version="2")["error"]["code"] == "codigo_inmutable"
    editar({"nombre": "X"}, headers=contador, version="2")
    editar({"nombre": "X"}, headers={}, version="2")
    check(
        "patch",
        "/activos/{id}",
        client.patch(
            f"/activos/{uuid.uuid4()}", json={"nombre": "X"}, headers={**admin, "If-Match": "1"}
        ),
    )
    check(
        "patch",
        "/activos/{id}",
        client.patch(
            ruta, data="x" * (AUTH_MAX_BODY_BYTES + 1), headers={**admin, "If-Match": "2"}
        ),
    )

    # Spec 005, T3: mover, estado, baja y reactivar.
    def accion(nombre, payload, headers=admin, version="2", activo=body["id"]):
        extra = {"If-Match": f'"{version}"'} if version is not None else {}
        response = client.post(
            f"/activos/{activo}/{nombre}", json=payload, headers={**headers, **extra}
        )
        return check("post", f"/activos/{{id}}/{nombre}", response)

    otra = post("/ubicaciones", {"nombre": "Otra", "tipo": "sala", "padre_id": sede})["ubicacion"]
    assert accion("mover", {"ubicacion_id": otra["id"]})["activo"]["row_version"] == 3
    assert accion("mover", {"ubicacion_id": sede}, version="3")["error"]["code"] == (
        "ubicacion_invalida"
    )
    assert accion("estado", {"estado": "en_reparacion"}, version="3")["activo"]["estado"] == (
        "en_reparacion"
    )
    assert accion("estado", {"estado": "otro"}, version="4")["error"]["code"] == (
        "solicitud_invalida"
    )
    assert accion("baja", {"motivo": "otro"}, version="4")["error"]["code"] == "motivo_invalido"
    for nombre, payload in (
        ("mover", {"ubicacion_id": sala["id"]}),
        ("estado", {"estado": "activo"}),
        ("baja", {"motivo": "perdido"}),
    ):
        accion(nombre, payload, version="1")
        accion(nombre, payload, version=None)
        accion(nombre, payload, headers=contador)
        accion(nombre, payload, headers={})
        accion(nombre, payload, activo=uuid.uuid4())
        check(
            "post",
            f"/activos/{{id}}/{nombre}",
            client.post(
                f"/activos/{body['id']}/{nombre}",
                data="x" * (AUTH_MAX_BODY_BYTES + 1),
                headers={**admin, "If-Match": "4"},
            ),
        )
    assert accion("baja", {"motivo": "perdido"}, version="4")["activo"]["estado"] == "dado_de_baja"
    for nombre, payload in (
        ("mover", {"ubicacion_id": sala["id"]}),
        ("estado", {"estado": "en_reparacion"}),
        ("baja", {"motivo": "perdido"}),
    ):
        assert accion(nombre, payload, version="5")["error"]["code"] == "activo_dado_de_baja"
    assert editar({"nombre": "X"}, version="5")["error"]["code"] == "activo_dado_de_baja"
    reactivado = accion("estado", {"estado": "activo", "motivo": "encontrado"}, version="5")
    assert reactivado["activo"]["estado"] == "activo"
    accion("mover", {"ubicacion_id": sala["id"]}, version="6")

    # Spec 005, T4: historial y filtro por ubicación.
    historial = f"/activos/{body['id']}/historial"
    for params, headers in (({}, admin), ({}, contador), ({"antes_de": "x"}, admin), ({}, {})):
        check(
            "get",
            "/activos/{id}/historial",
            client.get(historial, query_string=params, headers=headers),
        )
    check(
        "get",
        "/activos/{id}/historial",
        client.get(f"/activos/{uuid.uuid4()}/historial", headers=admin),
    )
    filtrada = client.get("/activos", query_string={"ubicacion_id": sala["id"]}, headers=admin)
    assert check("get", "/activos", filtrada)["total"] >= 1

    # D2 en el contrato de ubicaciones.
    patch = client.patch(f"/ubicaciones/{sala['id']}", json={"activa": False}, headers=admin)
    assert check("patch", "/ubicaciones/{id}", patch)["error"]["code"] == "tiene_activos"


def test_sesiones_responses(client, contrato_db):
    admin, contador = bearer(ADMIN_A, TENANT_A), bearer(CONTADOR_A, TENANT_A)
    with contrato_db.migrator.begin() as conn:
        conn.execute(text("delete from sesion_conteo where estado = 'abierta'"))
    check("get", "/sesiones/abierta", client.get("/sesiones/abierta", headers=contador))
    cuerpo = {"nombre": "Conteo del contrato", "fecha_corte": "2026-11-30"}
    sesion = check("post", "/sesiones", client.post("/sesiones", json=cuerpo, headers=admin))
    check("post", "/sesiones", client.post("/sesiones", json=cuerpo, headers=admin))
    check("post", "/sesiones", client.post("/sesiones", json={"nombre": ""}, headers=admin))
    check("post", "/sesiones", client.post("/sesiones", json=cuerpo, headers=contador))
    check("post", "/sesiones", client.post("/sesiones", json=cuerpo, headers={}))
    check(
        "post",
        "/sesiones",
        client.post("/sesiones", data="x" * (AUTH_MAX_BODY_BYTES + 1), headers=admin),
    )
    check("get", "/sesiones/abierta", client.get("/sesiones/abierta", headers=contador))
    check("get", "/sesiones/abierta", client.get("/sesiones/abierta", headers={}))
    for headers in (admin, {}):
        check("get", "/sesiones", client.get("/sesiones", headers=headers))
    ruta = f"/sesiones/{sesion['sesion']['id']}"
    for headers in (contador, {}):
        check("get", "/sesiones/{id}", client.get(ruta, headers=headers))
    check("get", "/sesiones/{id}", client.get(f"/sesiones/{uuid.uuid4()}", headers=admin))
    # Verificar (T3).
    sufijo = uuid.uuid4().hex[:6]

    def post(path, body):
        response = client.post(path, json=body, headers=admin)
        assert response.status_code == 201, response.get_json()
        return response.get_json()

    sede = post("/ubicaciones", {"nombre": f"Sede V {sufijo}", "tipo": "sede"})["ubicacion"]["id"]
    sala = post("/ubicaciones", {"nombre": "Sala", "tipo": "sala", "padre_id": sede})
    sala_id = sala["ubicacion"]["id"]
    categoria = post("/categorias", {"nombre": f"Cat V {sufijo}"})["categoria"]["id"]

    def activo(codigo):
        body = {
            "id": str(uuid.uuid4()),
            "codigo": codigo,
            "nombre": "Activo verificado",
            "precio_compra": "10.00",
            "categoria_id": categoria,
            "ubicacion_id": sala_id,
        }
        return post("/activos", body)["activo"]["id"]

    a1, baja = activo(f"VA-{sufijo}"), activo(f"VB-{sufijo}")
    client.post(
        f"/activos/{baja}/baja", json={"motivo": "perdido"}, headers={**admin, "If-Match": "1"}
    )
    ver = f"{ruta}/verificaciones"

    def verificar(body, headers=contador):
        return check(
            "post", "/sesiones/{id}/verificaciones", client.post(ver, json=body, headers=headers)
        )

    def ultima(params, headers=contador):
        response = client.get(ver, query_string=params, headers=headers)
        return check("get", "/sesiones/{id}/verificaciones", response)

    ultima({"activo_id": a1})
    cuerpo_v = {
        "id": str(uuid.uuid4()),
        "activo_id": a1,
        "ubicacion_encontrada_id": sala_id,
        "estado_fisico": "ok",
    }
    verificar(cuerpo_v)
    verificar(cuerpo_v)
    verificar({**cuerpo_v, "id": str(uuid.uuid4()), "nota": "Revisado"}, headers=admin)
    ultima({"activo_id": a1}, headers=admin)
    ultima({"activo_id": a1}, headers={})
    ultima({})
    check(
        "get",
        "/sesiones/{id}/verificaciones",
        client.get(
            f"/sesiones/{uuid.uuid4()}/verificaciones",
            query_string={"activo_id": a1},
            headers=admin,
        ),
    )
    verificar({**cuerpo_v, "id": str(uuid.uuid4()), "estado_fisico": "regular"})
    verificar({**cuerpo_v, "id": str(uuid.uuid4()), "ubicacion_encontrada_id": sede})
    verificar({**cuerpo_v, "id": str(uuid.uuid4()), "activo_id": str(uuid.uuid4())})
    verificar({**cuerpo_v, "id": str(uuid.uuid4()), "activo_id": baja})
    verificar(cuerpo_v, headers={})
    check(
        "post",
        "/sesiones/{id}/verificaciones",
        client.post(ver, data="x" * (AUTH_MAX_BODY_BYTES + 1), headers=admin),
    )

    # Una sesión cerrada (el cierre llega con la 008) también cumple el contrato.
    with contrato_db.migrator.begin() as conn:
        conn.execute(
            text(
                "update sesion_conteo set estado = 'cerrada', cerrada_en = now(), "
                "cerrada_por = abierta_por where id = :s"
            ),
            {"s": sesion["sesion"]["id"]},
        )
    check("get", "/sesiones", client.get("/sesiones", headers=admin))
    cerrada = verificar({**cuerpo_v, "id": str(uuid.uuid4())})
    assert cerrada["error"]["code"] == "sesion_cerrada"


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
    codes |= {error.code for error in catalogo_service.ERRORES}
    codes |= {error.code for error in (*activos_service.ERRORES, activos_service.CodigoExistente)}
    codes |= {error.code for error in activos_cambios.ERRORES}
    codes |= {error.code for error in conteo_service.ERRORES}
    codes |= {error.code for error in conteo_verificaciones.ERRORES}
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
