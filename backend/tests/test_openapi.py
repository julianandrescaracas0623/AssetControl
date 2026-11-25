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
    CONTADOR_B,
    PASSWORD,
    TENANT_A,
    AccesoDb,
    bearer,
    dispose,
    make_app,
    temporary_acceso_db,
)
from flask import Flask
from plataforma_db import DEV_PASSWORD, nuevo_dev, plat_bearer, sembrar_dev
from sqlalchemy import text

import app.meta.routes as meta_routes
from app import errors
from app.activos import cambios as activos_cambios
from app.activos import service as activos_service
from app.auth import limits, recuperacion
from app.auth import routes as auth_routes
from app.auth import service as auth_service
from app.auth.credentials import (
    ARGON2_TEST_PARAMS,
    COMMON_PASSWORDS,
    PasswordPolicyError,
    check_password_policy,
    new_token,
)
from app.auth.decorators import NOT_AUTHENTICATED, PASSWORD_CHANGE_REQUIRED
from app.auth.http import AUTH_MAX_BODY_BYTES, CSRF_HEADER, CSRF_HEADER_VALUE
from app.catalogo import service as catalogo_service
from app.config import RateLimits
from app.conteo import cierre as conteo_cierre
from app.conteo import service as conteo_service
from app.conteo import verificaciones as conteo_verificaciones
from app.db import CounterRow, CounterUnavailableError
from app.empresa import service as empresa_service
from app.fotos import imagen as fotos_imagen
from app.fotos import service as fotos_service
from app.fotos.almacen import EXTENSION_KEY as ALMACEN_KEY
from app.fotos.almacen import CarpetaLocal
from app.invitaciones import routes as invitaciones_routes
from app.plataforma.config import PlataformaConfig
from app.plataforma.modulos.actividad import service as plataforma_actividad_service
from app.plataforma.modulos.empresas import service as plataforma_empresas_service
from app.plataforma.modulos.usuarios import service as plataforma_usuarios_service
from app.usuarios import routes as usuarios_routes

CONTRACT_FILE = Path(__file__).resolve().parent.parent / "openapi.yaml"
CSRF = {CSRF_HEADER: CSRF_HEADER_VALUE}
LINK_PREFIX = "/invitacion#"
NEW_PASSWORD = "Clave-Nueva-002b-segura"
OTHER_PASSWORD = "Clave-Recuperada-014-segura"

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
def contrato_app(contrato_db, tmp_path_factory) -> Iterator[Flask]:
    flask_app = make_app(
        contrato_db,
        RateLimits(login_account=1000, login_ip=1000, validate_ip=1000, accept_ip=1000),
        # Spec 017: la consola de plataforma habilitada para que sus rutas estén en el mapa.
        plataforma=PlataformaConfig(habilitada=True),
    )
    # Spec 012: fotos en una carpeta temporal.
    flask_app.extensions[ALMACEN_KEY] = CarpetaLocal(tmp_path_factory.mktemp("almacen"))
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
FORMATOS_EXPORTAR = ("excel", "pdf")


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
    if "application/json" not in content:
        # Respuesta binaria (spec 009): el tipo declarado y un cuerpo no vacío.
        (mime,) = content
        assert content[mime]["schema"] == {"type": "string", "format": "binary"}
        assert response.mimetype == mime, (method, path, response.mimetype)
        assert response.data, f"{method.upper()} {path} {status}: archivo vacío"
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


def test_usuarios_responses(client):
    body = check("get", "/usuarios", client.get("/usuarios", headers=bearer(ADMIN_A, TENANT_A)))
    assert body["usuarios"]
    check("get", "/usuarios", client.get("/usuarios", headers=bearer(CONTADOR_A, TENANT_A)))
    check("get", "/usuarios", client.get("/usuarios"))


def test_usuarios_cambiar_responses(client, monkeypatch):
    """Cada código de ``PUT /usuarios/{usuario_id}`` del contrato, sin cambiar nada."""
    csrf = {"X-AssetControl-CSRF": "1"}
    admin = {**bearer(ADMIN_A, TENANT_A), **csrf}
    ruta = f"/usuarios/{CONTADOR_A.usuario_id}"
    sin_cambios = {"rol": "contador", "activa": True}

    check("put", "/usuarios/{usuario_id}", client.put(ruta, json=sin_cambios, headers=admin))
    check(
        "put",
        "/usuarios/{usuario_id}",
        client.put(ruta, json={"rol": "admin"}, headers=admin),
    )
    check(
        "put",
        "/usuarios/{usuario_id}",
        client.put(ruta, json=sin_cambios, headers={**bearer(CONTADOR_A, TENANT_A), **csrf}),
    )
    check("put", "/usuarios/{usuario_id}", client.put(ruta, json=sin_cambios, headers=csrf))
    check(
        "put",
        "/usuarios/{usuario_id}",
        client.put(
            f"/usuarios/{ADMIN_A.usuario_id}",
            json={"rol": "contador", "activa": True},
            headers=admin,
        ),
    )
    check(
        "put",
        "/usuarios/{usuario_id}",
        client.put(f"/usuarios/{CONTADOR_B.usuario_id}", json=sin_cambios, headers=admin),
    )

    # 503: el candado de membresías de la empresa sigue ocupado (no se puede provocar aquí).
    from app import db as db_module
    from app.db import MembresiaRechazada

    def ocupado(*args, **kwargs):
        raise MembresiaRechazada("membresia_ocupada")

    monkeypatch.setattr(db_module, "cambiar_membresia", ocupado)
    check("put", "/usuarios/{usuario_id}", client.put(ruta, json=sin_cambios, headers=admin))


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


def test_cambiar_contrasena_responses(client, contrato_db, monkeypatch):
    """Spec 017 (T4): cambio de contraseña propio."""
    import argon2

    from app.errors import ServiceUnavailableError

    ruta = "/auth/cambiar-contrasena"
    usuario, email = uuid.uuid4(), nuevo_email()
    with contrato_db.migrator.begin() as conn:
        conn.execute(
            text(
                "insert into usuario (id, email, nombre, password_hash, debe_cambiar_password) "
                "values (:id, :e, 'Cambio contrato', :h, true)"
            ),
            {
                "id": usuario,
                "e": email,
                "h": argon2.PasswordHasher.from_parameters(ARGON2_TEST_PARAMS).hash(PASSWORD),
            },
        )
        conn.execute(
            text("insert into membresia (tenant_id, usuario_id, rol) values (:t, :u, 'admin')"),
            {"t": TENANT_A, "u": usuario},
        )
    entrada = check("post", "/auth/login", login(client, email=email))
    assert entrada["debe_cambiar_password"] is True
    auth = {"Authorization": f"Bearer {entrada['access_token']}"}
    me = check("get", "/auth/me", client.get("/auth/me", headers=auth))
    assert me["debe_cambiar_password"] is True

    def cuerpo(actual=PASSWORD, nueva=NEW_PASSWORD, confirmacion=None):
        return {"actual": actual, "nueva": nueva, "confirmacion": confirmacion or nueva}

    check("post", ruta, client.post(ruta, json={"actual": 1}, headers=auth))  # 400
    check("post", ruta, client.post(ruta, json=cuerpo()))  # 401 no_autenticado
    erronea = check(
        "post", ruta, client.post(ruta, json=cuerpo(actual="Otra-Clave-mala-17"), headers=auth)
    )
    assert erronea["error"]["code"] == "credenciales_invalidas"
    for body in (
        cuerpo(nueva=PASSWORD),
        cuerpo(confirmacion="Otra-Confirmacion-17"),
        cuerpo(nueva="corta"),
    ):
        check("post", ruta, client.post(ruta, json=body, headers=auth))  # 422
    big = "x" * (AUTH_MAX_BODY_BYTES + 1)
    check("post", ruta, client.post(ruta, data=big, content_type="application/json", headers=auth))

    class Saturado:
        def verify(self, stored, password):
            raise ServiceUnavailableError()

    monkeypatch.setattr(auth_service, "get_passwords", lambda: Saturado())
    check("post", ruta, client.post(ruta, json=cuerpo(), headers=auth))  # 503
    monkeypatch.undo()

    def exceeded(items, window_seconds):
        now = datetime.now(UTC)
        return [limits.Counter(ambito, key, now, limit + 1, limit) for ambito, key, limit in items]

    monkeypatch.setattr(limits, "increment_attempts", exceeded)
    check("post", ruta, client.post(ruta, json=cuerpo(), headers=auth))  # 429
    monkeypatch.undo()

    cambio = check("post", ruta, client.post(ruta, json=cuerpo(), headers=auth))  # 200
    assert cambio["debe_cambiar_password"] is False


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


def cuenta_nueva(client) -> str:
    """Correo de una cuenta nueva con una sola membresía activa (por invitación)."""
    email = nuevo_email()
    creada = client.post(
        "/invitaciones",
        json={"email": email, "rol": "contador"},
        headers=bearer(ADMIN_A, TENANT_A),
    )
    token = check("post", "/invitaciones", creada)["enlace"].removeprefix(LINK_PREFIX)
    body = {"token": token, "nombre": "Persona Sintética", "password": NEW_PASSWORD}
    check("post", "/invitaciones/aceptar", client.post("/invitaciones/aceptar", json=body))
    return email


def test_recuperar_responses(client, monkeypatch):
    ruta = "/auth/recuperar"
    # Sin correo configurado (la app de contrato no lo tiene): el mismo 202.
    body = check("post", ruta, client.post(ruta, json={"email": nuevo_email()}, headers=CSRF))
    assert body == {"mensaje": recuperacion.RECOVERY_MESSAGE}
    check("post", ruta, client.post(ruta, json={"email": nuevo_email()}))  # 403 sin cabecera
    check("post", ruta, client.post(ruta, json={"email": 1}, headers=CSRF))  # 400
    check(
        "post",
        ruta,
        client.post(ruta, data="x" * (AUTH_MAX_BODY_BYTES + 1), headers=CSRF),
    )  # 413

    # Con correo: cuenta y pide el enlace en la base (correo inexistente, sin enlace).
    monkeypatch.setattr(auth_routes, "correo_activo", lambda _app: True)
    check("post", ruta, client.post(ruta, json={"email": nuevo_email()}, headers=CSRF))

    def exceeded(items, window_seconds, permitido, destino, clave):
        now = datetime.now(UTC)
        return [CounterRow(intentos=10**6, ventana_inicio=now) for _ in items], None

    def unavailable(items, window_seconds, permitido, destino, clave):
        raise CounterUnavailableError("Sintetico", "XX000")

    monkeypatch.setattr(limits, "contar_y_solicitar_recuperacion", exceeded)
    check("post", ruta, client.post(ruta, json={"email": nuevo_email()}, headers=CSRF))  # 429
    monkeypatch.setattr(limits, "contar_y_solicitar_recuperacion", unavailable)
    check("post", ruta, client.post(ruta, json={"email": nuevo_email()}, headers=CSRF))  # 503


def test_restablecer_responses(client, monkeypatch):
    ruta = "/auth/restablecer"
    email = cuenta_nueva(client)
    token = new_token()
    monkeypatch.setattr(auth_routes, "correo_activo", lambda _app: True)
    monkeypatch.setattr(recuperacion, "new_token", lambda: token)
    pedido = client.post("/auth/recuperar", json={"email": email}, headers=CSRF)
    check("post", "/auth/recuperar", pedido)

    def restablecer(password=OTHER_PASSWORD, tok=token, headers=CSRF):
        return client.post(ruta, json={"token": tok, "password": password}, headers=headers)

    check("post", ruta, restablecer(headers={}))  # 403
    check("post", ruta, client.post(ruta, json={"token": 1}, headers=CSRF))  # 400
    for bad in ("\ud800", "corta", "x" * 200, next(iter(COMMON_PASSWORDS))):
        check("post", ruta, restablecer(password=bad))  # 400 contrasena_*
    check("post", ruta, client.post(ruta, data="x" * (AUTH_MAX_BODY_BYTES + 1), headers=CSRF))
    check("post", ruta, restablecer(tok="no-existe"))  # 400 enlace_invalido

    hecho = restablecer()
    assert check("post", ruta, hecho) is None  # 204
    assert "Set-Cookie" not in hecho.headers
    assert login(client, email=email, password=OTHER_PASSWORD).status_code == 200
    reusado = check("post", ruta, restablecer())  # el mismo enlace ya no sirve
    assert reusado["error"]["code"] == "enlace_invalido"


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


def test_activos_responses(client, contrato_db, monkeypatch):
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

    # Spec 015, T4: exportar la lista (solo admin; tope de filas).
    exportar = "/activos/exportar"
    for params, headers in (
        ({"q": "contrato"}, admin),
        ({"estado": "otro"}, admin),
        ({}, contador),
        ({}, {}),
    ):
        check("get", exportar, client.get(exportar, query_string=params, headers=headers))
    monkeypatch.setattr(activos_service, "MAX_FILAS_EXPORTACION", 0)
    demasiado = check("get", exportar, client.get(exportar, headers=admin))
    assert demasiado["error"]["code"] == "exportacion_demasiado_grande"
    monkeypatch.undo()

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

    # Spec 007: discrepancias y pendientes.
    a2 = activo(f"VC-{sufijo}")
    otra_sala = post("/ubicaciones", {"nombre": "Otra", "tipo": "sala", "padre_id": sede})
    otra_id = otra_sala["ubicacion"]["id"]
    v_otra = verificar(
        {
            "id": str(uuid.uuid4()),
            "activo_id": a2,
            "ubicacion_encontrada_id": otra_id,
            "estado_fisico": "ok",
        }
    )["verificacion"]["id"]
    dis = f"{ruta}/discrepancias"
    for params, headers in (
        ({}, admin),
        ({"estado": "todas"}, admin),
        ({"estado": "x"}, admin),
        ({}, contador),
        ({}, {}),
    ):
        check(
            "get",
            "/sesiones/{id}/discrepancias",
            client.get(dis, query_string=params, headers=headers),
        )
    check(
        "get",
        "/sesiones/{id}/discrepancias",
        client.get(f"/sesiones/{uuid.uuid4()}/discrepancias", headers=admin),
    )
    for nombre, cuerpo_lote in (
        ("aplicar", {"verificaciones": [v_otra], "confirmar_desfase": False}),
        ("descartar", {"verificaciones": [v_otra]}),
    ):
        plantilla = f"/sesiones/{{id}}/discrepancias/{nombre}"
        url = f"{dis}/{nombre}"
        check("post", plantilla, client.post(url, json=cuerpo_lote, headers=admin))
        check("post", plantilla, client.post(url, json={"verificaciones": []}, headers=admin))
        check("post", plantilla, client.post(url, json=cuerpo_lote, headers=contador))
        check("post", plantilla, client.post(url, json=cuerpo_lote, headers={}))
        check(
            "post",
            plantilla,
            client.post(
                f"/sesiones/{uuid.uuid4()}/discrepancias/{nombre}", json=cuerpo_lote, headers=admin
            ),
        )
        check(
            "post",
            plantilla,
            client.post(url, data="x" * (AUTH_MAX_BODY_BYTES + 1), headers=admin),
        )
    check(
        "get",
        "/sesiones/{id}/discrepancias",
        client.get(dis, query_string={"estado": "todas"}, headers=admin),
    )
    pend = f"{ruta}/pendientes"
    for params, headers in (
        ({}, contador),
        ({"ubicacion_id": sala_id}, admin),
        ({"pagina": "0"}, admin),
        ({}, {}),
    ):
        check(
            "get",
            "/sesiones/{id}/pendientes",
            client.get(pend, query_string=params, headers=headers),
        )
    check(
        "get",
        "/sesiones/{id}/pendientes",
        client.get(f"/sesiones/{uuid.uuid4()}/pendientes", headers=admin),
    )

    # Spec 008: informe de una abierta, cerrar (y repetir), informe.
    informe = f"{ruta}/informe"
    check("get", "/sesiones/{id}/informe", client.get(informe, headers=admin))
    check("get", "/inicio", client.get("/inicio", headers=admin))  # Spec 010: con abierta.
    for formato in FORMATOS_EXPORTAR:  # Spec 009: abierta → 409.
        check(
            "get",
            f"/sesiones/{{id}}/informe/{formato}",
            client.get(f"{informe}/{formato}", headers=admin),
        )
    for headers in (contador, {}):
        check("post", "/sesiones/{id}/cerrar", client.post(f"{ruta}/cerrar", headers=headers))
        check("get", "/sesiones/{id}/informe", client.get(informe, headers=headers))
    check(
        "post",
        "/sesiones/{id}/cerrar",
        client.post(f"/sesiones/{uuid.uuid4()}/cerrar", headers=admin),
    )
    check(
        "get",
        "/sesiones/{id}/informe",
        client.get(f"/sesiones/{uuid.uuid4()}/informe", headers=admin),
    )
    check(
        "post",
        "/sesiones/{id}/cerrar",
        client.post(f"{ruta}/cerrar", data="x" * (AUTH_MAX_BODY_BYTES + 1), headers=admin),
    )
    cerrado = check("post", "/sesiones/{id}/cerrar", client.post(f"{ruta}/cerrar", headers=admin))
    assert cerrado["sesion"]["estado"] == "cerrada"
    assert cerrado["no_encontrados"]
    check("post", "/sesiones/{id}/cerrar", client.post(f"{ruta}/cerrar", headers=admin))
    check("get", "/sesiones/{id}/informe", client.get(informe, headers=admin))
    check("get", "/sesiones", client.get("/sesiones", headers=admin))
    for headers in (admin, contador, {}):
        check("get", "/valor-actual", client.get("/valor-actual", headers=headers))
    # Spec 010: Inicio (sin sesión abierta, con último informe).
    for headers in (admin, contador, {}):
        check("get", "/inicio", client.get("/inicio", headers=headers))
    for headers in (admin, contador, {}):
        check("get", "/inicio/actividad", client.get("/inicio/actividad", headers=headers))
    check("get", "/inicio/actividad", client.get("/inicio/actividad?antes_de=0", headers=admin))
    for headers in (admin, contador, {}):
        check("get", "/inicio/evolucion", client.get("/inicio/evolucion", headers=headers))

    # Spec 009: exportar (cerrada, abierta, roles, inexistente).
    for formato in FORMATOS_EXPORTAR:
        plantilla = f"/sesiones/{{id}}/informe/{formato}"
        for headers in (admin, contador, {}):
            check("get", plantilla, client.get(f"{ruta}/informe/{formato}", headers=headers))
        otra = uuid.uuid4()
        check("get", plantilla, client.get(f"/sesiones/{otra}/informe/{formato}", headers=admin))
    cerrada = verificar({**cuerpo_v, "id": str(uuid.uuid4())})
    assert cerrada["error"]["code"] == "sesion_cerrada"


def _jpeg() -> bytes:
    from io import BytesIO

    from PIL import Image

    buffer = BytesIO()
    Image.new("RGB", (40, 30), (10, 20, 30)).save(buffer, "JPEG")
    return buffer.getvalue()


def _multipart(foto_id=None, datos=None) -> dict:
    from io import BytesIO

    form: dict = {}
    if foto_id is not None:
        form["foto_id"] = str(foto_id)
    if datos is not None:
        form["archivo"] = (BytesIO(datos), "foto.jpg")
    return form


def test_fotos_responses(client, contrato_app, contrato_db, monkeypatch):
    """Spec 012: foto principal, foto de una verificación y entrega de la imagen."""
    admin = bearer(ADMIN_A, TENANT_A)
    contador = bearer(CONTADOR_A, TENANT_A, rol="contador")
    mp = "multipart/form-data"

    def post(ruta, body):
        response = client.post(ruta, json=body, headers=admin)
        assert response.status_code == 201, response.get_json()
        return response.get_json()

    sede = post("/ubicaciones", {"nombre": f"SF {uuid.uuid4().hex[:6]}", "tipo": "sede"})
    sala = post(
        "/ubicaciones",
        {"nombre": "Sala F", "tipo": "sala", "padre_id": sede["ubicacion"]["id"]},
    )["ubicacion"]["id"]
    categoria = post("/categorias", {"nombre": f"Fotos {uuid.uuid4().hex[:6]}"})["categoria"]["id"]

    def activo() -> str:
        return post(
            "/activos",
            {
                "id": str(uuid.uuid4()),
                "codigo": f"FC-{uuid.uuid4().hex[:6].upper()}",
                "nombre": "Silla",
                "categoria_id": categoria,
                "ubicacion_id": sala,
                "precio_compra": "1.00",
            },
        )["activo"]["id"]

    a = activo()
    principal = "/activos/{id}/foto"

    def put(ruta, form, headers=admin):
        return client.put(ruta, data=form, headers=headers, content_type=mp)

    foto_id = uuid.uuid4()
    creada = check("put", principal, put(f"/activos/{a}/foto", _multipart(foto_id, _jpeg())))
    check("put", principal, put(f"/activos/{a}/foto", _multipart(foto_id, _jpeg())))  # 200
    check("put", principal, put(f"/activos/{a}/foto", _multipart(None, _jpeg())))  # 400
    check("put", principal, client.put(f"/activos/{a}/foto", data={}, content_type=mp))  # 401
    check("put", principal, put(f"/activos/{uuid.uuid4()}/foto", _multipart(uuid.uuid4(), _jpeg())))
    check("put", principal, put(f"/activos/{activo()}/foto", _multipart(foto_id, _jpeg())))  # 409
    check("put", principal, put(f"/activos/{a}/foto", _multipart(uuid.uuid4(), b"GIF89a")))  # 415
    check(
        "put",
        principal,
        put(f"/activos/{a}/foto", _multipart(uuid.uuid4(), _jpeg()[:200])),
    )  # 422
    check(
        "put",
        principal,
        put(f"/activos/{a}/foto", _multipart(uuid.uuid4(), b"0" * (11 * 1024 * 1024))),
    )  # 413

    ver = "/fotos/{id}"
    check("get", ver, client.get(f"/fotos/{creada['foto']['id']}?tamano=mini", headers=contador))
    check("get", ver, client.get(f"/fotos/{creada['foto']['id']}?tamano=x", headers=admin))
    check("get", ver, client.get(f"/fotos/{creada['foto']['id']}"))
    check("get", ver, client.get(f"/fotos/{uuid.uuid4()}", headers=admin))
    ficha = check("get", "/activos/{id}", client.get(f"/activos/{a}", headers=contador))
    assert ficha["activo"]["foto"]["id"] == creada["foto"]["id"]

    check("delete", principal, client.delete(f"/activos/{a}/foto", headers=contador))  # 204
    check("delete", principal, client.delete(f"/activos/{a}/foto", headers=admin))  # 404
    check("delete", principal, client.delete(f"/activos/{a}/foto"))  # 401
    historial = client.get(f"/activos/{a}/historial", headers=admin)
    check("get", "/activos/{id}/historial", historial)

    # Foto de una verificación.
    sesion = client.post(
        "/sesiones", json={"nombre": "Fotos", "fecha_corte": "2026-11-15"}, headers=admin
    )
    if sesion.status_code == 409:  # otra prueba dejó una abierta
        sid = client.get("/sesiones/abierta", headers=admin).get_json()["sesion"]["id"]
    else:
        sid = sesion.get_json()["sesion"]["id"]
    vid = str(uuid.uuid4())
    verificada = client.post(
        f"/sesiones/{sid}/verificaciones",
        json={
            "id": vid,
            "activo_id": a,
            "ubicacion_encontrada_id": sala,
            "estado_fisico": "danado",
        },
        headers=admin,
    )
    assert verificada.status_code in (200, 201), verificada.get_json()
    de_ver = "/sesiones/{sid}/verificaciones/{vid}/foto"
    ruta_v = f"/sesiones/{sid}/verificaciones/{vid}/foto"
    fv = uuid.uuid4()
    check("put", de_ver, put(ruta_v, _multipart(fv, _jpeg()), contador))  # 403
    check("put", de_ver, put(ruta_v, _multipart(fv, _jpeg())))  # 201
    check("put", de_ver, put(ruta_v, _multipart(fv, _jpeg())))  # 200
    check("put", de_ver, put(ruta_v, _multipart(uuid.uuid4(), _jpeg())))  # 409 foto_existente
    check("put", de_ver, put(ruta_v, _multipart(None, None)))  # 400
    check("put", de_ver, client.put(ruta_v, data={}, content_type=mp))  # 401
    otra = f"/sesiones/{sid}/verificaciones/{uuid.uuid4()}/foto"
    check("put", de_ver, put(otra, _multipart(uuid.uuid4(), _jpeg())))  # 404
    # Otra verificación sin foto para los errores de la imagen.
    vid2 = str(uuid.uuid4())
    otra_v = client.post(
        f"/sesiones/{sid}/verificaciones",
        json={
            "id": vid2,
            "activo_id": activo(),
            "ubicacion_encontrada_id": sala,
            "estado_fisico": "ok",
        },
        headers=admin,
    )
    assert otra_v.status_code in (200, 201), otra_v.get_json()
    ruta_v2 = f"/sesiones/{sid}/verificaciones/{vid2}/foto"
    check("put", de_ver, put(ruta_v2, _multipart(uuid.uuid4(), b"GIF89a")))  # 415
    check("put", de_ver, put(ruta_v2, _multipart(uuid.uuid4(), _jpeg()[:200])))  # 422
    check("put", de_ver, put(ruta_v2, _multipart(uuid.uuid4(), b"0" * (11 * 1024 * 1024))))

    # Fotos desactivadas: 503 en cada operación.
    monkeypatch.setitem(contrato_app.extensions, ALMACEN_KEY, None)
    check("put", principal, put(f"/activos/{a}/foto", _multipart(uuid.uuid4(), _jpeg())))
    check("delete", principal, client.delete(f"/activos/{a}/foto", headers=admin))
    check("put", de_ver, put(ruta_v, _multipart(uuid.uuid4(), _jpeg())))
    check("get", ver, client.get(f"/fotos/{creada['foto']['id']}", headers=admin))


def test_empresa_responses(client, contrato_app, monkeypatch):
    """Spec 013: datos de la empresa y logo (solo admin)."""
    from io import BytesIO

    from PIL import Image

    admin = bearer(ADMIN_A, TENANT_A)
    contador = bearer(CONTADOR_A, TENANT_A, rol="contador")
    mp = "multipart/form-data"
    datos = {"nombre": "Empresa contrato", "direccion": "Calle 1 # 2-3", "nit": "900123456-8"}

    def png() -> bytes:
        buffer = BytesIO()
        Image.new("RGBA", (60, 20), (1, 2, 3, 255)).save(buffer, "PNG")
        return buffer.getvalue()

    def logo(logo_id=None, archivo=None, headers=admin):
        form: dict = {}
        if logo_id is not None:
            form["logo_id"] = str(logo_id)
        if archivo is not None:
            form["archivo"] = (BytesIO(archivo), "logo.png")
        return client.put("/empresa/logo", data=form, headers=headers, content_type=mp)

    ruta, ruta_logo, ver = "/empresa", "/empresa/logo", "/empresa/logo/{id}"
    check("get", ruta, client.get(ruta, headers=admin))
    check("get", ruta, client.get(ruta))
    check("get", ruta, client.get(ruta, headers=contador))
    # Antes de guardar los datos, el logo no se puede subir.
    sin_datos = check("put", ruta_logo, logo(uuid.uuid4(), png()))
    assert sin_datos is None or sin_datos["error"]["code"] in ("empresa_sin_datos",)
    check("put", ruta, client.put(ruta, json=datos, headers=admin))
    invalido = check("put", ruta, client.put(ruta, json={**datos, "nit": "1-2"}, headers=admin))
    assert invalido["error"]["campo"] == "nit"
    check("put", ruta, client.put(ruta, json=datos))
    check("put", ruta, client.put(ruta, json=datos, headers=contador))
    grande = b'{"nombre": "' + b"x" * 5000 + b'"}'
    check(
        "put",
        ruta,
        client.put(ruta, data=grande, headers={**admin, "Content-Type": "application/json"}),
    )

    logo_id = uuid.uuid4()
    check("put", ruta_logo, logo(logo_id, png()))  # 201
    check("put", ruta_logo, logo(logo_id, png()))  # 200
    check("put", ruta_logo, logo(None, png()))  # 400
    check("put", ruta_logo, client.put(ruta_logo, data={}, content_type=mp))  # 401
    check("put", ruta_logo, logo(uuid.uuid4(), png(), headers=contador))  # 403
    check("put", ruta_logo, logo(uuid.uuid4(), b"GIF89a"))  # 415
    roto = BytesIO()
    Image.effect_noise((300, 300), 60).save(roto, "PNG")
    check("put", ruta_logo, logo(uuid.uuid4(), roto.getvalue()[:2000]))  # 422
    check("put", ruta_logo, logo(uuid.uuid4(), b"0" * (3 * 1024 * 1024)))  # 413

    check("get", ver, client.get(f"/empresa/logo/{logo_id}", headers=admin))
    check("get", ver, client.get(f"/empresa/logo/{logo_id}"))
    check("get", ver, client.get(f"/empresa/logo/{logo_id}", headers=contador))
    check("get", ver, client.get(f"/empresa/logo/{uuid.uuid4()}", headers=admin))

    check("delete", ruta_logo, client.delete(ruta_logo, headers=admin))  # 204
    check("delete", ruta_logo, client.delete(ruta_logo, headers=admin))  # 404
    check("delete", ruta_logo, client.delete(ruta_logo))  # 401
    check("delete", ruta_logo, client.delete(ruta_logo, headers=contador))  # 403

    monkeypatch.setitem(contrato_app.extensions, ALMACEN_KEY, None)
    check("put", ruta_logo, logo(uuid.uuid4(), png()))  # 503
    check("get", ver, client.get(f"/empresa/logo/{logo_id}", headers=admin))  # 503
    # Un logo_id ya usado (409) se prueba con el almacenamiento de vuelta.
    monkeypatch.undo()
    otro = uuid.uuid4()
    check("put", ruta_logo, logo(otro, png()))
    check("put", ruta_logo, logo(logo_id, png()))  # 409 logo_id_en_uso


def test_plataforma_responses(client, contrato_db):
    """Spec 017 (T2): login, refresh, logout, me y módulos de la consola."""
    dev = sembrar_dev(contrato_db, nuevo_dev("contrato"))
    login_path = "/plataforma/auth/login"

    def plat_login(password=DEV_PASSWORD):
        return client.post(login_path, json={"email": dev.email, "password": password})

    ok = plat_login()
    body = check("post", login_path, ok)
    token = body["access_token"]
    check("post", login_path, plat_login("Otra-Clave-incorrecta-17"))
    check("post", login_path, client.post(login_path, json={"email": 1}))
    big = "x" * (AUTH_MAX_BODY_BYTES + 1)
    check("post", login_path, client.post(login_path, data=big, content_type="text/plain"))

    cookie = refresh_cookie(ok)
    refresh_path = "/plataforma/auth/refresh"
    check("post", refresh_path, client.post(refresh_path, headers={**CSRF, "Cookie": cookie}))
    check("post", refresh_path, client.post(refresh_path, headers=CSRF))
    check("post", refresh_path, client.post(refresh_path, headers={"Cookie": cookie}))
    check(
        "post",
        refresh_path,
        client.post(refresh_path, data=big, content_type="text/plain", headers=CSRF),
    )

    me = "/plataforma/auth/me"
    check("get", me, client.get(me, headers=plat_bearer(token)))
    check("get", me, client.get(me))
    modulos = "/plataforma/modulos"
    check("get", modulos, client.get(modulos, headers=plat_bearer(token)))
    check("get", modulos, client.get(modulos, headers=bearer(ADMIN_A, TENANT_A)))

    logout_path = "/plataforma/auth/logout"
    check("post", logout_path, client.post(logout_path, headers=CSRF))
    check("post", logout_path, client.post(logout_path))
    check(
        "post",
        logout_path,
        client.post(logout_path, data=big, content_type="text/plain", headers=CSRF),
    )


def test_plataforma_empresas_responses(client, contrato_db, monkeypatch):
    """Spec 017 (T3b): lista, alta y estado de las empresas de la consola."""
    from app.errors import ServiceUnavailableError

    dev = sembrar_dev(contrato_db, nuevo_dev("contrato-empresas"))
    ok = client.post("/plataforma/auth/login", json={"email": dev.email, "password": DEV_PASSWORD})
    dev_auth = plat_bearer(ok.get_json()["access_token"])
    ruta, estado = "/plataforma/empresas", "/plataforma/empresas/{id}"
    big = "x" * (AUTH_MAX_BODY_BYTES + 1)

    def cuerpo(**admin) -> dict:
        return {
            "id": str(uuid.uuid4()),
            "nombre": "Empresa contrato 017",
            "direccion": "Calle 1 # 2-3",
            "nit": "900123456-8",
            "admin": {
                "nombre": "Admin contrato",
                "email": nuevo_email(),
                "password": NEW_PASSWORD,
                "password_confirmacion": NEW_PASSWORD,
                **admin,
            },
        }

    check("get", ruta, client.get(ruta, headers=dev_auth))
    check("get", ruta, client.get(ruta, query_string={"estado": "otra"}, headers=dev_auth))
    check("get", ruta, client.get(ruta, headers=bearer(ADMIN_A, TENANT_A)))

    body = cuerpo()
    creada = check("post", ruta, client.post(ruta, json=body, headers=dev_auth))  # 201
    check("post", ruta, client.post(ruta, json=body, headers=dev_auth))  # 409 empresa_existente
    en_uso = check(
        "post", ruta, client.post(ruta, json=cuerpo(email=ADMIN_A.email), headers=dev_auth)
    )
    assert en_uso["error"]["code"] == "email_en_uso"
    check("post", ruta, client.post(ruta, json={"id": "x"}, headers=dev_auth))  # 400
    invalido = check(
        "post",
        ruta,
        client.post(ruta, json=cuerpo(password_confirmacion="otra"), headers=dev_auth),
    )
    assert invalido["error"]["campo"] == "admin.password_confirmacion"
    check("post", ruta, client.post(ruta, json=body))  # 401
    check(
        "post",
        ruta,
        client.post(ruta, data=big, content_type="application/json", headers=dev_auth),
    )

    class Saturado:
        def hash(self, password):
            raise ServiceUnavailableError()

    monkeypatch.setattr(plataforma_empresas_service, "get_passwords", lambda: Saturado())
    check("post", ruta, client.post(ruta, json=cuerpo(), headers=dev_auth))  # 503
    monkeypatch.undo()

    empresa = f"/plataforma/empresas/{creada['empresa_id']}"
    check("patch", estado, client.patch(empresa, json={"activa": False}, headers=dev_auth))
    check("patch", estado, client.patch(empresa, json={"activa": True}, headers=dev_auth))
    check("patch", estado, client.patch(empresa, json={"activa": "no"}, headers=dev_auth))
    check("patch", estado, client.patch(empresa, json={"activa": False}))
    desconocida = f"/plataforma/empresas/{uuid.uuid4()}"
    check("patch", estado, client.patch(desconocida, json={"activa": False}, headers=dev_auth))
    check(
        "patch",
        estado,
        client.patch(empresa, data=big, content_type="application/json", headers=dev_auth),
    )

    # Spec 017, T4 (O1): plat_accion por desarrollador en POST y PATCH (429/503).
    def exceeded(items, window_seconds):
        now = datetime.now(UTC)
        return [limits.Counter(ambito, key, now, limit + 1, limit) for ambito, key, limit in items]

    def unavailable(items, window_seconds):
        raise RuntimeError("base caída (sintético)")

    for falla in (exceeded, unavailable):
        monkeypatch.setattr(limits, "increment_attempts", falla)
        check("post", ruta, client.post(ruta, json=cuerpo(), headers=dev_auth))
        check("patch", estado, client.patch(empresa, json={"activa": True}, headers=dev_auth))
        monkeypatch.undo()


def test_plataforma_usuarios_responses(client, contrato_db, monkeypatch):
    """Spec 017 (T5): lista y estado de las membresías de una empresa."""
    dev = sembrar_dev(contrato_db, nuevo_dev("contrato-usuarios"))
    ok = client.post("/plataforma/auth/login", json={"email": dev.email, "password": DEV_PASSWORD})
    dev_auth = plat_bearer(ok.get_json()["access_token"])
    big = "x" * (AUTH_MAX_BODY_BYTES + 1)
    alta = {
        "id": str(uuid.uuid4()),
        "nombre": "Empresa contrato usuarios 017",
        "direccion": "Calle 1 # 2-3",
        "admin": {
            "nombre": "Admin contrato",
            "email": nuevo_email(),
            "password": NEW_PASSWORD,
            "password_confirmacion": NEW_PASSWORD,
        },
    }
    creada = client.post("/plataforma/empresas", json=alta, headers=dev_auth).get_json()
    empresa_id, admin_id = creada["empresa_id"], creada["admin_id"]
    lista, estado = (
        "/plataforma/empresas/{id}/usuarios",
        "/plataforma/empresas/{id}/usuarios/{usuario_id}",
    )
    usuarios = f"/plataforma/empresas/{empresa_id}/usuarios"
    admin = f"{usuarios}/{admin_id}"

    body = check("get", lista, client.get(usuarios, headers=dev_auth))  # 200
    assert [u["id"] for u in body["usuarios"]] == [admin_id]
    check("get", lista, client.get(usuarios))  # 401
    check(
        "get", lista, client.get(f"/plataforma/empresas/{uuid.uuid4()}/usuarios", headers=dev_auth)
    )

    ultimo = check("patch", estado, client.patch(admin, json={"activa": False}, headers=dev_auth))
    assert ultimo["error"]["code"] == "ultimo_admin"
    check("patch", estado, client.patch(admin, json={"activa": True}, headers=dev_auth))  # 200
    check("patch", estado, client.patch(admin, json={"activa": "no"}, headers=dev_auth))  # 400
    check("patch", estado, client.patch(admin, json={"activa": True}))  # 401
    ajeno = f"{usuarios}/{ADMIN_A.usuario_id}"
    check("patch", estado, client.patch(ajeno, json={"activa": False}, headers=dev_auth))  # 404
    check(
        "patch",
        estado,
        client.patch(admin, data=big, content_type="application/json", headers=dev_auth),
    )  # 413
    empresa = f"/plataforma/empresas/{empresa_id}"
    assert client.patch(empresa, json={"activa": False}, headers=dev_auth).status_code == 200
    inactiva = check("patch", estado, client.patch(admin, json={"activa": True}, headers=dev_auth))
    assert inactiva["error"]["code"] == "empresa_inactiva"
    assert client.patch(empresa, json={"activa": True}, headers=dev_auth).status_code == 200

    def exceeded(items, window_seconds):
        now = datetime.now(UTC)
        return [limits.Counter(ambito, key, now, limit + 1, limit) for ambito, key, limit in items]

    def unavailable(items, window_seconds):
        raise RuntimeError("base caída (sintético)")

    for falla in (exceeded, unavailable):
        monkeypatch.setattr(limits, "increment_attempts", falla)
        check("patch", estado, client.patch(admin, json={"activa": True}, headers=dev_auth))
        monkeypatch.undo()


def test_plataforma_editar_usuario_responses(client, contrato_db, monkeypatch):
    """Spec 017, C1 (T13): editar nombre y rol de un usuario desde la consola."""
    dev = sembrar_dev(contrato_db, nuevo_dev("contrato-editar-usuario"))
    ok = client.post("/plataforma/auth/login", json={"email": dev.email, "password": DEV_PASSWORD})
    dev_auth = plat_bearer(ok.get_json()["access_token"])
    big = "x" * (AUTH_MAX_BODY_BYTES + 1)
    alta = {
        "id": str(uuid.uuid4()),
        "nombre": "Empresa contrato editar usuario 017",
        "direccion": "Calle 1 # 2-3",
        "admin": {
            "nombre": "Admin contrato",
            "email": nuevo_email(),
            "password": NEW_PASSWORD,
            "password_confirmacion": NEW_PASSWORD,
        },
    }
    creada = client.post("/plataforma/empresas", json=alta, headers=dev_auth).get_json()
    empresa_id, admin_id = creada["empresa_id"], creada["admin_id"]
    ruta = "/plataforma/empresas/{id}/usuarios/{usuario_id}"
    admin = f"/plataforma/empresas/{empresa_id}/usuarios/{admin_id}"
    cuerpo = {"nombre": "Admin contrato editado", "rol": "admin"}

    editado = check("put", ruta, client.put(admin, json=cuerpo, headers=dev_auth))  # 200
    assert editado == {"id": admin_id, "nombre": cuerpo["nombre"], "rol": "admin"}
    check("put", ruta, client.put(admin, json=cuerpo, headers=dev_auth))  # 200 sin cambios
    ultimo = check(
        "put", ruta, client.put(admin, json={**cuerpo, "rol": "contador"}, headers=dev_auth)
    )
    assert ultimo["error"]["code"] == "ultimo_admin"  # 409
    check(
        "put", ruta, client.put(admin, json={**cuerpo, "email": "x@ejemplo.test"}, headers=dev_auth)
    )  # 400
    invalido = check(
        "put", ruta, client.put(admin, json={**cuerpo, "rol": "dueño"}, headers=dev_auth)
    )
    assert invalido["error"]["campo"] == "rol"  # 422
    check("put", ruta, client.put(admin, json=cuerpo))  # 401
    check("put", ruta, client.put(admin, json=cuerpo, headers=bearer(ADMIN_A, TENANT_A)))  # 401
    ajeno = f"/plataforma/empresas/{empresa_id}/usuarios/{ADMIN_A.usuario_id}"
    check("put", ruta, client.put(ajeno, json=cuerpo, headers=dev_auth))  # 404
    check(
        "put",
        ruta,
        client.put(admin, data=big, content_type="application/json", headers=dev_auth),
    )  # 413
    empresa = f"/plataforma/empresas/{empresa_id}"
    assert client.patch(empresa, json={"activa": False}, headers=dev_auth).status_code == 200
    inactiva = check("put", ruta, client.put(admin, json=cuerpo, headers=dev_auth))
    assert inactiva["error"]["code"] == "empresa_inactiva"  # 409
    assert client.patch(empresa, json={"activa": True}, headers=dev_auth).status_code == 200

    def exceeded(items, window_seconds):
        now = datetime.now(UTC)
        return [limits.Counter(ambito, key, now, limit + 1, limit) for ambito, key, limit in items]

    def unavailable(items, window_seconds):
        raise RuntimeError("base caída (sintético)")

    for falla in (exceeded, unavailable):
        monkeypatch.setattr(limits, "increment_attempts", falla)
        check("put", ruta, client.put(admin, json=cuerpo, headers=dev_auth))  # 429 / 503
        monkeypatch.undo()


def test_plataforma_contrasena_usuario_responses(client, contrato_db, monkeypatch):
    """Spec 017, C1b (T16): contraseña temporal de un usuario desde la consola."""
    dev = sembrar_dev(contrato_db, nuevo_dev("contrato-contrasena-usuario"))
    ok = client.post("/plataforma/auth/login", json={"email": dev.email, "password": DEV_PASSWORD})
    dev_auth = plat_bearer(ok.get_json()["access_token"])
    big = "x" * (AUTH_MAX_BODY_BYTES + 1)
    alta = {
        "id": str(uuid.uuid4()),
        "nombre": "Empresa contrato contraseña 017",
        "direccion": "Calle 1 # 2-3",
        "admin": {
            "nombre": "Admin contrato",
            "email": nuevo_email(),
            "password": NEW_PASSWORD,
            "password_confirmacion": NEW_PASSWORD,
        },
    }
    creada = client.post("/plataforma/empresas", json=alta, headers=dev_auth).get_json()
    empresa_id, admin_id = creada["empresa_id"], creada["admin_id"]
    ruta = "/plataforma/empresas/{id}/usuarios/{usuario_id}/contrasena"
    url = f"/plataforma/empresas/{empresa_id}/usuarios/{admin_id}/contrasena"
    temporal = "Temporal-Contrato-2026"
    cuerpo = {"password": temporal, "password_confirmacion": temporal}

    check("post", ruta, client.post(url, json=cuerpo, headers=dev_auth))  # 204
    check("post", ruta, client.post(url, json={**cuerpo, "rol": "admin"}, headers=dev_auth))  # 400
    distintas = check(
        "post",
        ruta,
        client.post(
            url, json={**cuerpo, "password_confirmacion": "Otra-2026-xyz"}, headers=dev_auth
        ),
    )
    assert distintas["error"]["campo"] == "password_confirmacion"  # 422
    corta = check(
        "post",
        ruta,
        client.post(
            url, json={"password": "corta", "password_confirmacion": "corta"}, headers=dev_auth
        ),
    )
    assert corta["error"]["code"] == "contrasena_corta"  # 422
    check("post", ruta, client.post(url, json=cuerpo))  # 401
    check("post", ruta, client.post(url, json=cuerpo, headers=bearer(ADMIN_A, TENANT_A)))  # 401
    ajeno = f"/plataforma/empresas/{empresa_id}/usuarios/{ADMIN_A.usuario_id}/contrasena"
    check("post", ruta, client.post(ajeno, json=cuerpo, headers=dev_auth))  # 404
    check(
        "post",
        ruta,
        client.post(url, data=big, content_type="application/json", headers=dev_auth),
    )  # 413
    empresa = f"/plataforma/empresas/{empresa_id}"
    assert client.patch(empresa, json={"activa": False}, headers=dev_auth).status_code == 200
    inactiva = check("post", ruta, client.post(url, json=cuerpo, headers=dev_auth))
    assert inactiva["error"]["code"] == "empresa_inactiva"  # 409
    assert client.patch(empresa, json={"activa": True}, headers=dev_auth).status_code == 200

    def exceeded(items, window_seconds):
        now = datetime.now(UTC)
        return [limits.Counter(ambito, key, now, limit + 1, limit) for ambito, key, limit in items]

    def unavailable(items, window_seconds):
        raise RuntimeError("base caída (sintético)")

    for falla in (exceeded, unavailable):
        monkeypatch.setattr(limits, "increment_attempts", falla)
        check("post", ruta, client.post(url, json=cuerpo, headers=dev_auth))  # 429 / 503
        monkeypatch.undo()


def test_plataforma_logo_responses(client, contrato_app, contrato_db, monkeypatch):
    """Spec 017 (T7): logo inicial de una empresa desde la consola."""
    from io import BytesIO

    from PIL import Image

    dev = sembrar_dev(contrato_db, nuevo_dev("contrato-logo"))
    ok = client.post("/plataforma/auth/login", json={"email": dev.email, "password": DEV_PASSWORD})
    dev_auth = plat_bearer(ok.get_json()["access_token"])
    alta = {
        "id": str(uuid.uuid4()),
        "nombre": "Empresa contrato logo 017",
        "direccion": "Calle 1 # 2-3",
        "admin": {
            "nombre": "Admin contrato",
            "email": nuevo_email(),
            "password": NEW_PASSWORD,
            "password_confirmacion": NEW_PASSWORD,
        },
    }
    creada = client.post("/plataforma/empresas", json=alta, headers=dev_auth).get_json()
    ruta = "/plataforma/empresas/{id}/logo"
    url = f"/plataforma/empresas/{creada['empresa_id']}/logo"
    mp = "multipart/form-data"

    def png() -> bytes:
        buffer = BytesIO()
        Image.new("RGBA", (60, 20), (1, 2, 3, 255)).save(buffer, "PNG")
        return buffer.getvalue()

    def subir(logo_id=None, archivo=None, headers=dev_auth, destino=url):
        form: dict = {}
        if logo_id is not None:
            form["logo_id"] = str(logo_id)
        if archivo is not None:
            form["archivo"] = (BytesIO(archivo), "logo.png")
        return client.post(destino, data=form, headers=headers, content_type=mp)

    # Sin almacén: 503 logos_no_disponibles (la empresa sigue sin logo).
    monkeypatch.setitem(contrato_app.extensions, ALMACEN_KEY, None)
    sin_almacen = check("post", ruta, subir(uuid.uuid4(), png()))
    assert sin_almacen["error"]["code"] == "logos_no_disponibles"
    monkeypatch.undo()

    check("post", ruta, subir(None, png()))  # 400
    check("post", ruta, subir(uuid.uuid4(), png(), headers={}))  # 401
    check("post", ruta, subir(uuid.uuid4(), png(), headers=bearer(ADMIN_A, TENANT_A)))  # 401
    check("post", ruta, subir(uuid.uuid4(), b"GIF89a"))  # 415
    roto = BytesIO()
    Image.effect_noise((300, 300), 60).save(roto, "PNG")
    check("post", ruta, subir(uuid.uuid4(), roto.getvalue()[:2000]))  # 422
    check("post", ruta, subir(uuid.uuid4(), b"0" * (3 * 1024 * 1024)))  # 413
    otra = f"/plataforma/empresas/{uuid.uuid4()}/logo"
    check("post", ruta, subir(uuid.uuid4(), png(), destino=otra))  # 404
    # Un tenant sin ficha empresa (como los que crea la CLI).
    sin_ficha = uuid.uuid4()
    with contrato_db.migrator.begin() as conn:
        conn.execute(
            text("insert into tenant (id, nombre) values (:t, 'Sin ficha 017')"), {"t": sin_ficha}
        )
    sin_datos = check(
        "post", ruta, subir(uuid.uuid4(), png(), destino=f"/plataforma/empresas/{sin_ficha}/logo")
    )
    assert sin_datos["error"]["code"] == "empresa_sin_datos"

    logo_id = uuid.uuid4()
    check("post", ruta, subir(logo_id, png()))  # 201
    check("post", ruta, subir(logo_id, png()))  # 200
    # C1 (R44): con logo vigente, otro logo_id lo reemplaza (201).
    reemplazo = uuid.uuid4()
    assert check("post", ruta, subir(reemplazo, png())) == {"logo": {"id": str(reemplazo)}}
    en_uso = check("post", ruta, subir(logo_id, png()))  # 409: el anterior ya se usó
    assert en_uso["error"]["code"] == "logo_id_en_uso"

    def exceeded(items, window_seconds):
        now = datetime.now(UTC)
        return [limits.Counter(ambito, key, now, limit + 1, limit) for ambito, key, limit in items]

    def unavailable(items, window_seconds):
        raise RuntimeError("base caída (sintético)")

    for falla in (exceeded, unavailable):
        monkeypatch.setattr(limits, "increment_attempts", falla)
        check("post", ruta, subir(uuid.uuid4(), png()))  # 429 / 503
        monkeypatch.undo()


def test_plataforma_ficha_responses(client, contrato_db, monkeypatch):
    """Spec 017, C1 (T12): leer y editar la ficha de una empresa desde la consola."""
    dev = sembrar_dev(contrato_db, nuevo_dev("contrato-ficha"))
    ok = client.post("/plataforma/auth/login", json={"email": dev.email, "password": DEV_PASSWORD})
    dev_auth = plat_bearer(ok.get_json()["access_token"])
    big = "x" * (AUTH_MAX_BODY_BYTES + 1)
    alta = {
        "id": str(uuid.uuid4()),
        "nombre": "Empresa contrato ficha 017",
        "direccion": "Calle 1 # 2-3",
        "admin": {
            "nombre": "Admin contrato",
            "email": nuevo_email(),
            "password": NEW_PASSWORD,
            "password_confirmacion": NEW_PASSWORD,
        },
    }
    creada = client.post("/plataforma/empresas", json=alta, headers=dev_auth).get_json()
    ruta = "/plataforma/empresas/{id}/ficha"
    url = f"/plataforma/empresas/{creada['empresa_id']}/ficha"
    otra = f"/plataforma/empresas/{uuid.uuid4()}/ficha"
    sin_ficha = uuid.uuid4()
    with contrato_db.migrator.begin() as conn:
        conn.execute(
            text("insert into tenant (id, nombre) values (:t, 'Sin ficha ficha 017')"),
            {"t": sin_ficha},
        )
    sin_datos_url = f"/plataforma/empresas/{sin_ficha}/ficha"
    ficha = {
        "nombre": "Empresa contrato ficha editada",
        "direccion": "Carrera 9 # 8-7",
        "nit": "900123456-8",
        "telefono": None,
        "correo": "contacto@ejemplo.test",
    }

    leida = check("get", ruta, client.get(url, headers=dev_auth))  # 200
    assert leida["nombre"] == alta["nombre"] and leida["tiene_logo"] is False
    check("get", ruta, client.get(url))  # 401
    check("get", ruta, client.get(url, headers=bearer(ADMIN_A, TENANT_A)))  # 401
    check("get", ruta, client.get(otra, headers=dev_auth))  # 404
    sin_datos = check("get", ruta, client.get(sin_datos_url, headers=dev_auth))  # 409
    assert sin_datos["error"]["code"] == "empresa_sin_datos"

    editada = check("put", ruta, client.put(url, json=ficha, headers=dev_auth))  # 200
    assert editada["nombre"] == ficha["nombre"] and editada["nit"] == "900.123.456-8"
    check("put", ruta, client.put(url, json=ficha, headers=dev_auth))  # 200 sin cambios
    check("put", ruta, client.put(url, json={**ficha, "extra": 1}, headers=dev_auth))  # 400
    check("put", ruta, client.put(url, json=ficha))  # 401
    check("put", ruta, client.put(otra, json=ficha, headers=dev_auth))  # 404
    sin_datos = check("put", ruta, client.put(sin_datos_url, json=ficha, headers=dev_auth))
    assert sin_datos["error"]["code"] == "empresa_sin_datos"  # 409
    invalido = check(
        "put", ruta, client.put(url, json={**ficha, "nit": "1-2"}, headers=dev_auth)
    )  # 422
    assert invalido["error"]["campo"] == "nit"
    check(
        "put",
        ruta,
        client.put(url, data=big, content_type="application/json", headers=dev_auth),
    )  # 413

    def exceeded(items, window_seconds):
        now = datetime.now(UTC)
        return [limits.Counter(ambito, key, now, limit + 1, limit) for ambito, key, limit in items]

    def unavailable(items, window_seconds):
        raise RuntimeError("base caída (sintético)")

    for falla in (exceeded, unavailable):
        monkeypatch.setattr(limits, "increment_attempts", falla)
        check("put", ruta, client.put(url, json=ficha, headers=dev_auth))  # 429 / 503
        monkeypatch.undo()


def test_plataforma_actividad_responses(client, contrato_db):
    """Spec 017 (T6): lista paginada de la auditoría de la consola."""
    dev = sembrar_dev(contrato_db, nuevo_dev("contrato-actividad"))
    ok = client.post("/plataforma/auth/login", json={"email": dev.email, "password": DEV_PASSWORD})
    dev_auth = plat_bearer(ok.get_json()["access_token"])
    ruta = "/plataforma/actividad"

    body = check("get", ruta, client.get(ruta, query_string={"limite": "1"}, headers=dev_auth))
    assert body["actividad"]
    if body["siguiente"] is not None:
        check(
            "get",
            ruta,
            client.get(ruta, query_string={"cursor": body["siguiente"]}, headers=dev_auth),
        )
    filtrada = check(
        "get",
        ruta,
        client.get(
            ruta,
            query_string={
                "empresa_id": str(TENANT_A),
                "accion": "empresa_creada",
                "desde": "2026-01-01",
                "hasta": "2026-12-31",
            },
            headers=dev_auth,
        ),
    )
    assert isinstance(filtrada["actividad"], list)
    check("get", ruta, client.get(ruta, query_string={"limite": "101"}, headers=dev_auth))  # 400
    check("get", ruta, client.get(ruta))  # 401
    check("get", ruta, client.get(ruta, headers=bearer(ADMIN_A, TENANT_A)))  # 401


LIMITED = [
    ("post", "/auth/login", {"email": ADMIN_A.email, "password": PASSWORD}, {}),
    ("post", "/auth/refresh", None, CSRF),
    ("post", "/invitaciones/validar", {"token": "x"}, {}),
    ("post", "/invitaciones/aceptar", {"token": "x", "nombre": "N", "password": NEW_PASSWORD}, {}),
    ("post", "/auth/restablecer", {"token": "x", "password": NEW_PASSWORD}, CSRF),
    # Spec 017 (T2): login y refresh de la consola de plataforma.
    ("post", "/plataforma/auth/login", {"email": "dev@ejemplo.test", "password": "x"}, {}),
    ("post", "/plataforma/auth/refresh", None, CSRF),
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
        PASSWORD_CHANGE_REQUIRED[0],
        auth_routes.PASSWORD_REPEATED[0],
        auth_routes.PASSWORDS_DIFFER[0],
        auth_routes.INVALID_CREDENTIALS[0],
        auth_routes.BAD_REQUEST[0],
        invitaciones_routes.INVALID_INVITATION[0],
        recuperacion.INVALID_LINK[0],
    }
    codes |= {error.code for error in catalogo_service.ERRORES}
    codes |= {
        error.code
        for error in (
            *activos_service.ERRORES,
            activos_service.CodigoExistente,
            activos_service.ExportacionDemasiadoGrande,
        )
    }
    codes |= {error.code for error in activos_cambios.ERRORES}
    codes |= {error.code for error in conteo_service.ERRORES}
    codes |= {error.code for error in conteo_verificaciones.ERRORES}
    codes |= {error.code for error in conteo_cierre.ERRORES}
    codes |= {error.code for error in fotos_service.ERRORES}
    codes |= {error.code for error in empresa_service.ERRORES}
    codes |= {error.code for error in plataforma_empresas_service.ERRORES}
    codes |= {error.code for error in plataforma_usuarios_service.ERRORES}
    codes |= {error.code for error in plataforma_actividad_service.ERRORES}
    codes |= {
        error.code
        for error in (
            fotos_imagen.ImagenDemasiadoGrande,
            fotos_imagen.TipoNoAdmitido,
            fotos_imagen.ImagenInvalida,
        )
    }
    # Rechazos de PUT /usuarios/{usuario_id} (0033): mapa código de la base -> respuesta.
    codes |= {code for _, code, _ in usuarios_routes.RECHAZOS.values()}
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
