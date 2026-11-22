"""Módulo Empresas de la consola (spec 017, T3b; R16–R22, R33–R35; A7, A8, A10–A12).

Sobre una base temporal migrada a ``head`` (tenants sintéticos A y B de ``acceso_db``) y con
la consola habilitada:

- Registro: ``GET /plataforma/modulos`` incluye ``empresas``.
- ``GET /plataforma/empresas``: solo identidad, logo sí/no y conteos (R21); búsqueda por
  nombre (``q``) y filtro de estado (``estado``).
- ``POST /plataforma/empresas``: Flask valida la ficha (reglas de la 013), el admin y la
  contraseña (política de la 002, confirmación en servidor) antes de llamar a la base
  (``422`` con ``campo``); alta atómica con ``empresa_creada`` en la misma transacción;
  ``409 empresa_existente`` / ``409 email_en_uso`` sin filas nuevas; la contraseña ni su
  hash salen en la respuesta, la auditoría ni los logs; ``no-store``.
- ``PATCH /plataforma/empresas/{id}``: desactivar y reactivar con auditoría; ``404`` si no
  existe.

Datos sintéticos (``@ejemplo.test``).
"""

import dataclasses
import logging
import uuid
from collections.abc import Iterator

import pytest
from acceso_db import ADMIN_A, TENANT_A, TENANT_B, AccesoDb, dispose, temporary_acceso_db
from flask import Flask
from plataforma_db import error_code, filas, login, make_plat_app, nuevo_dev, sembrar_dev
from sqlalchemy import text

from app.errors import ServiceUnavailableError
from app.plataforma import auditoria
from app.plataforma.modulos.empresas import service as empresas_service

ADMIN_PASSWORD = "Clave-Inicial-Sintetica-2026"
RUTA = "/plataforma/empresas"
TABLES = (
    "tenant",
    "usuario",
    "membresia",
    "empresa",
    "empresa_logo",
    "invitacion",
    "refresh_token",
    "plataforma_auditoria",
)
LISTA_CAMPOS = {
    "id",
    "nombre",
    "activa",
    "creado_en",
    "tiene_logo",
    "n_membresias_activas",
    "n_admins_activos",
}


@pytest.fixture(scope="module")
def emp_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("plat_empresas")


@pytest.fixture(scope="module")
def emp_app(emp_db) -> Iterator[Flask]:
    flask_app = make_plat_app(emp_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(emp_app):
    return emp_app.test_client(use_cookies=False)


@pytest.fixture(scope="module")
def dev(emp_db):
    return sembrar_dev(emp_db, nuevo_dev("empresas"))


@pytest.fixture(scope="module")
def headers(emp_app, dev) -> dict[str, str]:
    response = login(emp_app.test_client(use_cookies=False), dev.email)
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['access_token']}"}


def _email(prefijo: str = "admin") -> str:
    return f"{prefijo}.{uuid.uuid4().hex[:10]}@ejemplo.test"


def _cuerpo(**changes) -> dict:
    admin = {
        "nombre": "Admin Sintético",
        "email": _email(),
        "password": ADMIN_PASSWORD,
        "password_confirmacion": ADMIN_PASSWORD,
    }
    admin.update(changes.pop("admin", {}))
    body = {
        "id": str(uuid.uuid4()),
        "nombre": f"Clínica Sintética {uuid.uuid4().hex[:6]}",
        "direccion": "Calle 1 # 2-3, Cartago",
        "nit": "900123456-8",
        "telefono": "3001234567",
        "correo": "contacto@ejemplo.test",
        "admin": admin,
    }
    body.update(changes)
    return {k: v for k, v in body.items() if v is not ...}


def _counts(db: AccesoDb) -> dict[str, int]:
    with db.migrator.connect() as conn:
        return {t: conn.scalar(text(f"select count(*) from {t}")) for t in TABLES}  # noqa: S608


def _auditoria(db: AccesoDb, tenant_id) -> list[dict]:
    return filas(
        db,
        "select desarrollador_id, accion, resultado, tenant_id, objeto_id "
        "from plataforma_auditoria where tenant_id = :t order by creado_en, id",
        {"t": tenant_id},
    )


def _crear(client, headers, body):
    return client.post(RUTA, json=body, headers=headers)


# --- Registro del módulo (R12) ------------------------------------------------------------


def test_the_empresas_module_is_registered(client, headers):
    response = client.get("/plataforma/modulos", headers=headers)
    assert response.status_code == 200
    ids = [m["id"] for m in response.get_json()["modulos"]]
    assert "empresas" in ids
    (empresas,) = [m for m in response.get_json()["modulos"] if m["id"] == "empresas"]
    assert empresas["titulo"] == "Empresas"


# --- Lista (R21) --------------------------------------------------------------------------


def test_list_returns_only_identity_logo_and_counts(client, headers):
    response = client.get(RUTA, headers=headers)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    empresas = {e["id"]: e for e in response.get_json()["empresas"]}
    assert all(set(e) == LISTA_CAMPOS for e in empresas.values())
    a = empresas[str(TENANT_A)]
    assert (a["nombre"], a["activa"], a["tiene_logo"]) == ("Clínica sintética A8", True, False)
    assert (a["n_membresias_activas"], a["n_admins_activos"]) == (3, 2)
    assert empresas[str(TENANT_B)]["n_admins_activos"] == 1


def test_list_filters_by_name_and_state(client, headers, emp_db):
    nombre = f"Odontología Búsqueda {uuid.uuid4().hex[:6]}"
    creada = _crear(client, headers, _cuerpo(nombre=nombre))
    assert creada.status_code == 201
    empresa_id = creada.get_json()["empresa_id"]

    def ids(**params) -> set[str]:
        response = client.get(RUTA, query_string=params, headers=headers)
        assert response.status_code == 200, response.get_json()
        return {e["id"] for e in response.get_json()["empresas"]}

    assert ids(q=nombre.upper()) == {empresa_id}
    assert ids(q="  búsqueda ") >= {empresa_id}
    assert str(TENANT_A) not in ids(q="búsqueda")
    assert ids(q="") >= {empresa_id, str(TENANT_A), str(TENANT_B)}

    cambio = client.patch(f"{RUTA}/{empresa_id}", json={"activa": False}, headers=headers)
    assert cambio.status_code == 200
    assert empresa_id in ids(estado="desactivadas")
    assert str(TENANT_A) not in ids(estado="desactivadas")
    assert empresa_id not in ids(estado="activas")
    assert {empresa_id, str(TENANT_A)} <= ids(estado="todas")
    assert {empresa_id, str(TENANT_A)} <= ids()


@pytest.mark.parametrize("params", [{"estado": "otra"}, {"q": "x" * 121}])
def test_list_rejects_bad_filters(client, headers, params):
    response = client.get(RUTA, query_string=params, headers=headers)
    assert response.status_code == 400
    assert error_code(response) == "solicitud_invalida"


def test_list_requires_a_developer(client):
    response = client.get(RUTA)
    assert response.status_code == 401
    assert error_code(response) == "no_autenticado"


# --- Alta (R16–R20; A7, A8, A11) ----------------------------------------------------------


def test_create_makes_tenant_ficha_admin_and_membership_with_its_audit(
    client, headers, emp_db, dev
):
    before = _counts(emp_db)
    body = _cuerpo(admin={"email": "  Nuevo.Admin." + uuid.uuid4().hex[:6] + "@Ejemplo.TEST "})
    response = _crear(client, headers, body)
    assert response.status_code == 201, response.get_json()
    assert response.headers["Cache-Control"] == "no-store"
    created = response.get_json()
    assert set(created) == {"empresa_id", "admin_id"}
    assert created["empresa_id"] == body["id"]
    texto = response.get_data(as_text=True)
    assert ADMIN_PASSWORD not in texto and "argon2" not in texto

    after = _counts(emp_db)
    for table in ("tenant", "usuario", "membresia", "empresa", "plataforma_auditoria"):
        assert after[table] == before[table] + 1, table
    for table in ("empresa_logo", "invitacion", "refresh_token"):
        assert after[table] == before[table], table

    tenant_id = uuid.UUID(created["empresa_id"])
    admin_id = uuid.UUID(created["admin_id"])
    (tenant,) = filas(emp_db, "select nombre, activo from tenant where id = :t", {"t": tenant_id})
    assert tenant == {"nombre": body["nombre"], "activo": True}
    (empresa,) = filas(
        emp_db,
        "select nombre, direccion, nit, telefono, correo, logo_id from empresa "
        "where tenant_id = :t",
        {"t": tenant_id},
    )
    assert empresa == {
        "nombre": body["nombre"],
        "direccion": body["direccion"],
        "nit": "900.123.456-8",  # normalizado como en la 013
        "telefono": body["telefono"],
        "correo": body["correo"],
        "logo_id": None,
    }
    (usuario,) = filas(
        emp_db,
        "select email, nombre, password_hash, activo, debe_cambiar_password "
        "from usuario where id = :u",
        {"u": admin_id},
    )
    assert usuario["email"] == body["admin"]["email"].strip().lower()
    assert usuario["nombre"] == "Admin Sintético"
    assert usuario["password_hash"].startswith("$argon2id$")
    assert (usuario["activo"], usuario["debe_cambiar_password"]) == (True, True)
    assert filas(
        emp_db,
        "select tenant_id, rol, activa from membresia where usuario_id = :u",
        {"u": admin_id},
    ) == [{"tenant_id": tenant_id, "rol": "admin", "activa": True}]
    assert _auditoria(emp_db, tenant_id) == [
        {
            "desarrollador_id": dev.id,
            "accion": "empresa_creada",
            "resultado": "ok",
            "tenant_id": tenant_id,
            "objeto_id": tenant_id,
        }
    ]

    # A7 (hasta el login): el admin entra por el login de la 002 con esa contraseña.
    entrada = client.post(
        "/auth/login", json={"email": usuario["email"], "password": ADMIN_PASSWORD}
    )
    assert entrada.status_code == 200
    assert entrada.get_json()["tenant"]["id"] == str(tenant_id)


def test_create_without_optional_fields(client, headers, emp_db):
    body = _cuerpo(nit=..., telefono=None, correo="")
    response = _crear(client, headers, body)
    assert response.status_code == 201, response.get_json()
    (empresa,) = filas(
        emp_db,
        "select nit, telefono, correo from empresa where tenant_id = :t",
        {"t": body["id"]},
    )
    assert empresa == {"nit": None, "telefono": None, "correo": None}


def test_create_allows_the_company_email_to_be_the_admin_email(client, headers):
    email = _email("mismo")
    response = _crear(client, headers, _cuerpo(correo=email, admin={"email": email}))
    assert response.status_code == 201, response.get_json()


def test_repeating_the_same_id_is_empresa_existente_and_creates_nothing(client, headers, emp_db):
    body = _cuerpo()
    assert _crear(client, headers, body).status_code == 201
    before = _counts(emp_db)
    for repeated in (body, {**body, "admin": {**body["admin"], "email": _email("otro")}}):
        response = _crear(client, headers, repeated)
        assert response.status_code == 409
        assert error_code(response) == "empresa_existente"
    assert _counts(emp_db) == before
    assert len(_auditoria(emp_db, body["id"])) == 1


def test_an_email_in_use_is_email_en_uso_without_saying_where(client, headers, emp_db):
    before = _counts(emp_db)
    body = _cuerpo(admin={"email": ADMIN_A.email.upper()})
    response = _crear(client, headers, body)
    assert response.status_code == 409
    assert error_code(response) == "email_en_uso"
    texto = response.get_data(as_text=True)
    assert str(TENANT_A) not in texto and "A8" not in texto and ADMIN_A.email not in texto
    assert _counts(emp_db) == before


@pytest.mark.parametrize(
    ("changes", "campo", "code"),
    [
        ({"nombre": ""}, "nombre", "campo_invalido"),
        ({"nombre": "x" * 121}, "nombre", "campo_invalido"),
        ({"direccion": "  "}, "direccion", "campo_invalido"),
        ({"direccion": "x" * 201}, "direccion", "campo_invalido"),
        ({"nit": "900123456-7"}, "nit", "campo_invalido"),  # dígito de verificación errado
        ({"nit": "12-3"}, "nit", "campo_invalido"),
        ({"telefono": "123"}, "telefono", "campo_invalido"),
        ({"telefono": "1" * 31}, "telefono", "campo_invalido"),
        ({"correo": "no-es-correo"}, "correo", "campo_invalido"),
        ({"admin": {"nombre": " "}}, "admin.nombre", "campo_invalido"),
        ({"admin": {"nombre": "x" * 121}}, "admin.nombre", "campo_invalido"),
        ({"admin": {"email": "sin-arroba"}}, "admin.email", "campo_invalido"),
        ({"admin": {"email": "a@b@c.test"}}, "admin.email", "campo_invalido"),
        (
            {"admin": {"password": "Corta-1", "password_confirmacion": "Corta-1"}},
            "admin.password",
            "contrasena_corta",
        ),
        (
            {"admin": {"password": "bienvenido123", "password_confirmacion": "bienvenido123"}},
            "admin.password",
            "contrasena_comun",
        ),
        (
            {"admin": {"password_confirmacion": ADMIN_PASSWORD + "x"}},
            "admin.password_confirmacion",
            "contrasenas_distintas",
        ),
    ],
)
def test_invalid_data_is_422_with_its_field_and_creates_nothing(
    client, headers, emp_db, changes, campo, code
):
    before = _counts(emp_db)
    response = _crear(client, headers, _cuerpo(**changes))
    assert response.status_code == 422, response.get_json()
    error = response.get_json()["error"]
    assert (error["code"], error["campo"]) == (code, campo)
    assert error["message"]
    assert _counts(emp_db) == before


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {"id": "no-es-uuid"},
        {"id": str(uuid.uuid4()).upper()},
        {"admin": ...},
        {"admin": "texto"},
        {"admin": {"email": 1}},
        {"admin": {"password_confirmacion": ...}},
        {"admin": {"rol": "contador"}},
        {"tenant_id": str(uuid.uuid4())},
        {"nombre": ...},
        {"direccion": ...},
    ],
)
def test_malformed_bodies_are_400_and_create_nothing(client, headers, emp_db, body):
    if isinstance(body, dict):
        changes = dict(body)
        admin = changes.pop("admin", {})
        payload = _cuerpo(**changes)
        if admin is ...:
            payload.pop("admin")
        elif isinstance(admin, dict):
            payload["admin"].update(admin)
            payload["admin"] = {k: v for k, v in payload["admin"].items() if v is not ...}
        else:
            payload["admin"] = admin
    else:
        payload = body
    before = _counts(emp_db)
    response = client.post(RUTA, json=payload, headers=headers)
    assert response.status_code == 400, (payload, response.get_json())
    assert error_code(response) == "solicitud_invalida"
    assert _counts(emp_db) == before


def test_create_requires_a_developer(client, emp_db):
    before = _counts(emp_db)
    response = client.post(RUTA, json=_cuerpo())
    assert response.status_code == 401
    assert _counts(emp_db) == before


# --- Spec 017, T4: hallazgos aplazados de la revisión de T3b (O1, O2, forma y tamaño) -----


def test_an_overlong_admin_email_is_422_not_500(client, headers, emp_db):
    """O2: más de 254 caracteres (ya normalizado) es ``422 admin.email`` y nada creado."""
    before = _counts(emp_db)
    largo = "a" * 250 + "@ejemplo.test"
    response = _crear(client, headers, _cuerpo(admin={"email": largo}))
    assert response.status_code == 422, response.get_json()
    error = response.get_json()["error"]
    assert (error["code"], error["campo"]) == ("campo_invalido", "admin.email")
    assert _counts(emp_db) == before
    # El límite exacto sí se admite.
    justo = "b" * (254 - len("@ejemplo.test")) + "@ejemplo.test"
    assert _crear(client, headers, _cuerpo(admin={"email": justo})).status_code == 201


def test_a_json_body_sent_as_text_plain_is_400_and_creates_nothing(client, headers, emp_db):
    import json

    before = _counts(emp_db)
    response = client.post(
        RUTA, data=json.dumps(_cuerpo()), content_type="text/plain", headers=headers
    )
    assert response.status_code == 400
    assert error_code(response) == "solicitud_invalida"
    assert _counts(emp_db) == before


def test_bodies_over_4_kb_are_413_and_change_nothing(client, headers, emp_db):
    before = _counts(emp_db)
    grande = _cuerpo(direccion="x" * 5000)
    response = client.post(RUTA, json=grande, headers=headers)
    assert response.status_code == 413
    assert filas(emp_db, "select 1 from tenant where id = :t", {"t": grande["id"]}) == []
    patch = client.patch(
        f"{RUTA}/{TENANT_A}", json={"activa": False, "relleno": "x" * 5000}, headers=headers
    )
    assert patch.status_code == 413
    assert _counts(emp_db) == before
    (estado,) = filas(emp_db, "select activo from tenant where id = :t", {"t": TENANT_A})
    assert estado == {"activo": True}


def test_actions_are_limited_per_developer_before_argon2(emp_db, monkeypatch):
    """O1: ``plat_accion`` cuenta POST y PATCH por desarrollador; la N+1 es ``429``."""
    from plataforma_db import HIGH_LIMITS

    limites = dataclasses.replace(HIGH_LIMITS, plat_accion=3)
    flask_app = make_plat_app(emp_db, rate_limits=limites)
    try:
        client = flask_app.test_client(use_cookies=False)
        uno = sembrar_dev(emp_db, nuevo_dev("limite-uno"))
        otro = sembrar_dev(emp_db, nuevo_dev("limite-otro"))
        h_uno = {"Authorization": f"Bearer {login(client, uno.email).get_json()['access_token']}"}
        h_otro = {"Authorization": f"Bearer {login(client, otro.email).get_json()['access_token']}"}

        creada = _crear(client, h_uno, _cuerpo())  # 1
        assert creada.status_code == 201
        empresa = creada.get_json()["empresa_id"]
        assert (
            client.patch(f"{RUTA}/{empresa}", json={"activa": False}, headers=h_uno).status_code
            == 200
        )  # 2
        assert (
            client.patch(f"{RUTA}/{empresa}", json={"activa": "x"}, headers=h_uno).status_code
            == 400
        )  # 3

        hashes = []
        real = empresas_service.get_passwords
        monkeypatch.setattr(empresas_service, "get_passwords", lambda: hashes.append(1) or real())
        before = _counts(emp_db)
        bloqueada = _crear(client, h_uno, _cuerpo())  # 4 > 3
        assert bloqueada.status_code == 429
        assert error_code(bloqueada) == "demasiadas_solicitudes"
        assert hashes == []
        bloqueado = client.patch(f"{RUTA}/{empresa}", json={"activa": True}, headers=h_uno)
        assert bloqueado.status_code == 429
        assert _counts(emp_db) == before
        # Otro desarrollador tiene su propio contador; la lista (GET) no cuenta.
        assert client.get(RUTA, headers=h_uno).status_code == 200
        assert (
            client.patch(f"{RUTA}/{empresa}", json={"activa": True}, headers=h_otro).status_code
            == 200
        )
        ambitos = {
            row["ambito"] for row in filas(emp_db, "select distinct ambito from limite_tasa")
        }
        assert "plat_accion" in ambitos
    finally:
        dispose(flask_app)


def test_a_failure_after_creating_rolls_everything_back(client, headers, emp_db, monkeypatch):
    # La auditoría va en la misma transacción: si falla, no queda la empresa (A7, A10).
    def broken(*args, **kwargs):
        raise RuntimeError("auditoría caída (sintético)")

    monkeypatch.setattr(auditoria, "registrar", broken)
    before = _counts(emp_db)
    body = _cuerpo()
    response = _crear(client, headers, body)
    assert response.status_code == 500
    assert _counts(emp_db) == before
    assert filas(emp_db, "select 1 from tenant where id = :t", {"t": body["id"]}) == []


def test_saturated_argon2_is_503_and_creates_nothing(client, headers, emp_db, monkeypatch):
    class Saturado:
        def hash(self, password):
            raise ServiceUnavailableError()

    monkeypatch.setattr(empresas_service, "get_passwords", lambda: Saturado())
    before = _counts(emp_db)
    response = _crear(client, headers, _cuerpo())
    assert response.status_code == 503
    assert "Retry-After" in response.headers
    assert _counts(emp_db) == before


def test_no_log_has_the_password_hash_emails_or_names(client, headers, emp_db, caplog):
    body = _cuerpo()
    secretos = [
        ADMIN_PASSWORD,
        body["admin"]["email"],
        body["admin"]["nombre"],
        body["nombre"],
        body["direccion"],
        body["correo"],
        ADMIN_A.email,
    ]
    with caplog.at_level(logging.DEBUG):
        assert _crear(client, headers, body).status_code == 201
        assert _crear(client, headers, body).status_code == 409
        en_uso = _cuerpo(admin={"email": ADMIN_A.email})
        assert _crear(client, headers, en_uso).status_code == 409
        distinta = _cuerpo(admin={"password_confirmacion": ADMIN_PASSWORD + "-otra"})
        assert _crear(client, headers, distinta).status_code == 422
        corta = _cuerpo(admin={"password": "Corta-1", "password_confirmacion": "Corta-1"})
        assert _crear(client, headers, corta).status_code == 422
    (usuario,) = filas(
        emp_db, "select password_hash from usuario where email = :e", {"e": body["admin"]["email"]}
    )
    secretos += [usuario["password_hash"], ADMIN_PASSWORD + "-otra", "Corta-1"]
    logged = "\n".join(
        [record.getMessage() for record in caplog.records]
        + [str(record.args) for record in caplog.records]
    )
    for secreto in secretos:
        assert secreto not in logged


def test_the_audit_never_has_personal_data(client, headers, emp_db):
    body = _cuerpo()
    assert _crear(client, headers, body).status_code == 201
    (fila,) = filas(
        emp_db, "select * from plataforma_auditoria where tenant_id = :t", {"t": body["id"]}
    )
    valores = " ".join(str(v) for v in fila.values())
    for dato in (body["nombre"], body["admin"]["email"], body["admin"]["nombre"], ADMIN_PASSWORD):
        assert dato not in valores


# --- Estado (R22) -------------------------------------------------------------------------


def _nueva(client, headers) -> uuid.UUID:
    body = _cuerpo()
    assert _crear(client, headers, body).status_code == 201
    return uuid.UUID(body["id"])


def test_deactivate_and_reactivate_with_their_audit(client, headers, emp_db, dev):
    tenant_id = _nueva(client, headers)
    ruta = f"{RUTA}/{tenant_id}"
    response = client.patch(ruta, json={"activa": False}, headers=headers)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.get_json() == {"id": str(tenant_id), "activa": False}
    (estado,) = filas(
        emp_db,
        "select activo, desactivado_en, desactivado_por from tenant where id = :t",
        {"t": tenant_id},
    )
    assert (estado["activo"], estado["desactivado_por"]) == (False, dev.id)
    assert estado["desactivado_en"] is not None

    # Repetir no falla ni cambia el estado.
    repetida = client.patch(ruta, json={"activa": False}, headers=headers)
    assert repetida.get_json() == {"id": str(tenant_id), "activa": False}
    (otra_vez,) = filas(
        emp_db,
        "select activo, desactivado_en, desactivado_por from tenant where id = :t",
        {"t": tenant_id},
    )
    assert otra_vez == estado

    reactivada = client.patch(ruta, json={"activa": True}, headers=headers)
    assert reactivada.get_json() == {"id": str(tenant_id), "activa": True}
    (final,) = filas(
        emp_db,
        "select activo, desactivado_en, desactivado_por from tenant where id = :t",
        {"t": tenant_id},
    )
    assert final == {"activo": True, "desactivado_en": None, "desactivado_por": None}
    acciones = [
        (r["accion"], r["objeto_id"], r["desarrollador_id"]) for r in _auditoria(emp_db, tenant_id)
    ]
    assert acciones == [
        ("empresa_creada", tenant_id, dev.id),
        ("empresa_desactivada", tenant_id, dev.id),
        ("empresa_desactivada", tenant_id, dev.id),
        ("empresa_reactivada", tenant_id, dev.id),
    ]


def test_patch_of_an_unknown_company_is_404_without_audit(client, headers, emp_db):
    before = _counts(emp_db)
    response = client.patch(f"{RUTA}/{uuid.uuid4()}", json={"activa": False}, headers=headers)
    assert response.status_code == 404
    assert error_code(response) == "no_encontrado"
    assert _counts(emp_db) == before


@pytest.mark.parametrize(
    "body", [None, {}, {"activa": "false"}, {"activa": 0}, {"activa": False, "nombre": "x"}]
)
def test_patch_with_a_bad_body_is_400(client, headers, emp_db, body):
    before = _counts(emp_db)
    response = client.patch(f"{RUTA}/{TENANT_B}", json=body, headers=headers)
    assert response.status_code == 400
    assert error_code(response) == "solicitud_invalida"
    assert _counts(emp_db) == before


def test_patch_requires_a_developer(client, emp_db):
    response = client.patch(f"{RUTA}/{TENANT_B}", json={"activa": False})
    assert response.status_code == 401
    (estado,) = filas(emp_db, "select activo from tenant where id = :t", {"t": TENANT_B})
    assert estado == {"activo": True}


def test_a_developer_deactivated_mid_session_cannot_act(client, emp_app, emp_db):
    otro = sembrar_dev(emp_db, nuevo_dev("empresas-baja"))
    response = login(emp_app.test_client(use_cookies=False), otro.email)
    token = {"Authorization": f"Bearer {response.get_json()['access_token']}"}
    with emp_db.migrator.begin() as conn:
        conn.execute(
            text("select acceso.cambiar_estado_desarrollador(:e, false)"), {"e": otro.email}
        )
    before = _counts(emp_db)
    for method, path, body in (
        ("get", RUTA, None),
        ("post", RUTA, _cuerpo()),
        ("patch", f"{RUTA}/{TENANT_B}", {"activa": False}),
    ):
        answer = client.open(path, method=method, json=body, headers=token)
        assert answer.status_code == 401, (method, path)
        assert error_code(answer) == "no_autenticado"
    assert _counts(emp_db) == before
