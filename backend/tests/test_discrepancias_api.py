"""Discrepancias y pendientes (spec 007, T2–T4; R1–R9, Q1–Q4; plan.md §3).

- Lista: verificación vigente (R3) con encontrada ≠ esperada y su estado derivado
  (pendiente, desfasada, aplicada, descartada); ambos roles leen, sin precios ni valores
  (spec 020, R8).
- Aplicar y descartar en lote (solo admin): resultado por elemento; desfase sin confirmar no aplica;
  una sola resolución por verificación (también en carrera); sesión cerrada sí (Q1).
- Pendientes: activos ``activo``/``en_reparacion`` sin verificación; ambos roles, sin
  precio.
"""

import uuid
from collections.abc import Iterator

import pytest
from acceso_db import (
    ADMIN_A,
    ADMIN_B,
    CONTADOR_A,
    CONTADOR_B,
    TENANT_A,
    TENANT_B,
    AccesoDb,
    bearer,
    dispose,
    make_app,
    temporary_acceso_db,
)
from flask import Flask
from sqlalchemy import text

ADMIN = bearer(ADMIN_A, TENANT_A)
CONTADOR = bearer(CONTADOR_A, TENANT_A, rol="contador")
ADMIN_OTRO = bearer(ADMIN_B, TENANT_B)
CONTADOR_OTRO = bearer(CONTADOR_B, TENANT_B, rol="contador")


@pytest.fixture(scope="module")
def dis_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("discrepancias_api")


@pytest.fixture(scope="module")
def dis_app(dis_db) -> Iterator[Flask]:
    flask_app = make_app(dis_db)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(dis_app):
    return dis_app.test_client(use_cookies=False)


@pytest.fixture(scope="module")
def cat(dis_app) -> dict[str, str]:
    client = dis_app.test_client(use_cookies=False)

    def post(path, body):
        response = client.post(path, json=body, headers=ADMIN)
        assert response.status_code == 201, response.get_json()
        return response.get_json()

    sede = post("/ubicaciones", {"nombre": "Sede", "tipo": "sede"})["ubicacion"]["id"]
    sala = post("/ubicaciones", {"nombre": "Consultorios", "tipo": "sala", "padre_id": sede})
    sala_id = sala["ubicacion"]["id"]
    return {
        "sede": sede,
        "box": post("/ubicaciones", {"nombre": "Box 1", "tipo": "box", "padre_id": sala_id})[
            "ubicacion"
        ]["id"],
        "bodega": post("/ubicaciones", {"nombre": "Bodega", "tipo": "sala", "padre_id": sede})[
            "ubicacion"
        ]["id"],
        "adm": post("/ubicaciones", {"nombre": "Administración", "tipo": "sala", "padre_id": sede})[
            "ubicacion"
        ]["id"],
        "cat": post("/categorias", {"nombre": "Biomédicos"})["categoria"]["id"],
    }


@pytest.fixture
def sesion(client, dis_db) -> Iterator[str]:
    response = client.post(
        "/sesiones", json={"nombre": "Conteo nov 2026", "fecha_corte": "2026-11-30"}, headers=ADMIN
    )
    assert response.status_code == 201, response.get_json()
    sesion_id = response.get_json()["sesion"]["id"]
    yield sesion_id
    cerrar(dis_db, sesion_id)


def cerrar(db: AccesoDb, sesion_id: str) -> None:
    with db.migrator.begin() as conn:
        conn.execute(
            text(
                "update sesion_conteo set estado = 'cerrada', cerrada_en = now(), "
                "total_encontrado = 0, total_no_encontrado = 0, total_registrado = 0, "
                "cerrada_por = abierta_por where id = :s and estado = 'abierta'"
            ),
            {"s": sesion_id},
        )


def nuevo(client, cat, ubicacion="box", nombre="Autoclave") -> dict:
    body = {
        "id": str(uuid.uuid4()),
        "codigo": f"D-{uuid.uuid4().hex[:8].upper()}",
        "nombre": nombre,
        "precio_compra": "14200000.00",
        "categoria_id": cat["cat"],
        "ubicacion_id": cat[ubicacion],
    }
    response = client.post("/activos", json=body, headers=ADMIN)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["activo"]


def verificar(client, sesion_id, activo, ubicacion, headers=CONTADOR) -> str:
    body = {
        "id": str(uuid.uuid4()),
        "activo_id": activo["id"],
        "ubicacion_encontrada_id": ubicacion,
        "estado_fisico": "ok",
    }
    response = client.post(f"/sesiones/{sesion_id}/verificaciones", json=body, headers=headers)
    assert response.status_code == 201, response.get_json()
    return body["id"]


def lista(client, sesion_id, estado=None, headers=ADMIN):
    params = {"estado": estado} if estado else {}
    return client.get(f"/sesiones/{sesion_id}/discrepancias", query_string=params, headers=headers)


def accion(client, sesion_id, nombre, ids, headers=ADMIN, **extra):
    return client.post(
        f"/sesiones/{sesion_id}/discrepancias/{nombre}",
        json={"verificaciones": ids, **extra},
        headers=headers,
    )


def resultados(response) -> dict[str, str]:
    assert response.status_code == 200, response.get_json()
    return {r["verificacion_id"]: r["resultado"] for r in response.get_json()["resultados"]}


def mover(client, activo, ubicacion, version):
    response = client.post(
        f"/activos/{activo['id']}/mover",
        json={"ubicacion_id": ubicacion},
        headers={**ADMIN, "If-Match": str(version)},
    )
    assert response.status_code == 200, response.get_json()


def code(response) -> str:
    return response.get_json()["error"]["code"]


# --- T2: lista ---------------------------------------------------------------------------


def test_list_shows_only_the_current_verification_with_a_different_location(client, cat, sesion):
    igual, otra, corregida = nuevo(client, cat), nuevo(client, cat), nuevo(client, cat)
    verificar(client, sesion, igual, cat["box"])
    v_otra = verificar(client, sesion, otra, cat["bodega"])
    verificar(client, sesion, corregida, cat["bodega"])
    verificar(client, sesion, corregida, cat["box"])  # R3: la última está en la esperada

    response = lista(client, sesion)
    assert response.status_code == 200
    [item] = response.get_json()["discrepancias"]
    assert item["verificacion_id"] == v_otra
    assert item["activo"] == {
        "id": otra["id"],
        "codigo": otra["codigo"],
        "nombre": otra["nombre"],
        "estado": "activo",
    }
    assert item["ubicacion_esperada"] == {"id": cat["box"], "ruta": "Consultorios › Box 1"}
    assert item["ubicacion_encontrada"] == {"id": cat["bodega"], "ruta": "Bodega"}
    assert item["ubicacion_actual"] == item["ubicacion_esperada"]
    assert item["verificado_por"]["nombre"] == "Carlos"
    assert item["estado"] == "pendiente"
    assert item["resolucion"] is None
    assert "precio" not in str(response.get_json())


def test_states_desfasada_aplicada_and_descartada(client, cat, sesion):
    a, b, c = nuevo(client, cat), nuevo(client, cat), nuevo(client, cat)
    va = verificar(client, sesion, a, cat["bodega"])
    vb = verificar(client, sesion, b, cat["bodega"])
    vc = verificar(client, sesion, c, cat["bodega"])
    mover(client, a, cat["adm"], 1)  # se movió por otra vía
    assert resultados(accion(client, sesion, "aplicar", [vb])) == {vb: "aplicada"}
    assert resultados(accion(client, sesion, "descartar", [vc])) == {vc: "descartada"}

    por_resolver = {
        d["verificacion_id"]: d["estado"] for d in lista(client, sesion).get_json()["discrepancias"]
    }
    assert por_resolver == {va: "desfasada"}
    resueltas = lista(client, sesion, "resueltas").get_json()["discrepancias"]
    estados = {d["verificacion_id"]: d["estado"] for d in resueltas}
    assert estados == {vb: "aplicada", vc: "descartada"}
    aplicada = next(d for d in resueltas if d["verificacion_id"] == vb)
    assert aplicada["resolucion"]["por"]["nombre"] == "Ana"
    assert aplicada["ubicacion_actual"]["id"] == cat["bodega"]
    todas = lista(client, sesion, "todas").get_json()["discrepancias"]
    assert {d["verificacion_id"] for d in todas} == {va, vb, vc}


def test_list_is_for_both_roles_and_tenant_scoped(client, sesion):
    # Spec 020 (R8): el contador también lee la lista; un usuario de otro tenant, 404.
    assert lista(client, sesion, headers=CONTADOR).status_code == 200
    assert lista(client, sesion, headers=ADMIN_OTRO).status_code == 404
    assert lista(client, sesion, headers=CONTADOR_OTRO).status_code == 404
    assert lista(client, sesion, "otra", headers=CONTADOR).status_code == 400
    assert lista(client, str(uuid.uuid4())).status_code == 404
    assert lista(client, str(uuid.uuid4()), headers=CONTADOR).status_code == 404
    assert lista(client, "no-es-uuid", headers=CONTADOR).status_code == 404
    assert lista(client, sesion, "otra").status_code == 400
    assert lista(client, sesion, headers={}).status_code == 401


def claves_de_dinero(valor) -> list[str]:
    """Recorre el JSON y devuelve toda clave que hable de precio o valor (spec 020, R8)."""
    if isinstance(valor, dict):
        propias = [k for k in valor if "precio" in k.lower() or "valor" in k.lower()]
        return propias + [c for v in valor.values() for c in claves_de_dinero(v)]
    if isinstance(valor, list):
        return [c for v in valor for c in claves_de_dinero(v)]
    return []


def test_claves_de_dinero_finds_nested_keys():
    assert claves_de_dinero([{"a": {"b": [{"precio_al_contar": 1}]}, "Valor_total": 2}]) == [
        "Valor_total",
        "precio_al_contar",
    ]
    assert claves_de_dinero({"activo": {"nombre": "x"}, "estado": "pendiente"}) == []


def test_contador_reads_every_filter_without_prices_open_and_closed(client, cat, sesion, dis_db):
    # Spec 020 (R8; req. 5): solo lectura, con los tres filtros, en sesión abierta y cerrada.
    pendiente, aplicada, descartada = nuevo(client, cat), nuevo(client, cat), nuevo(client, cat)
    v_pendiente = verificar(client, sesion, pendiente, cat["bodega"])
    v_aplicada = verificar(client, sesion, aplicada, cat["bodega"])
    v_descartada = verificar(client, sesion, descartada, cat["adm"])
    assert resultados(accion(client, sesion, "aplicar", [v_aplicada])) == {v_aplicada: "aplicada"}
    assert resultados(accion(client, sesion, "descartar", [v_descartada])) == {
        v_descartada: "descartada"
    }
    esperado = {
        None: {v_pendiente},
        "por_resolver": {v_pendiente},
        "resueltas": {v_aplicada, v_descartada},
        "todas": {v_pendiente, v_aplicada, v_descartada},
    }

    def leer_como_contador() -> None:
        for estado, ids in esperado.items():
            response = lista(client, sesion, estado, headers=CONTADOR)
            assert response.status_code == 200, response.get_json()
            cuerpo = response.get_json()
            assert {d["verificacion_id"] for d in cuerpo["discrepancias"]} == ids
            assert claves_de_dinero(cuerpo) == []
            texto = response.get_data(as_text=True)
            assert "precio" not in texto.lower()
            # El importe sembrado no aparece bajo ninguna otra clave.
            assert "14200000" not in texto
            # La misma vista que el admin: no hay una forma aparte para el contador.
            assert cuerpo == lista(client, sesion, estado).get_json()

    leer_como_contador()
    cerrar(dis_db, sesion)
    leer_como_contador()
    for nombre in ("aplicar", "descartar"):
        response = accion(client, sesion, nombre, [v_pendiente], headers=CONTADOR)
        assert response.status_code == 403
        assert code(response) == "prohibido"
    assert lista(client, sesion, headers=CONTADOR).get_json()["discrepancias"][0]["estado"] == (
        "pendiente"
    )


# --- T3: aplicar y descartar -------------------------------------------------------------


def test_apply_moves_the_asset_and_logs_the_verification(client, cat, sesion, dis_db):
    activo = nuevo(client, cat)
    v = verificar(client, sesion, activo, cat["bodega"])
    response = accion(client, sesion, "aplicar", [v])
    [r] = response.get_json()["resultados"]
    assert r["resultado"] == "aplicada"
    assert r["activo"]["ubicacion"] == {"id": cat["bodega"], "ruta": "Bodega"}

    ficha = client.get(f"/activos/{activo['id']}", headers=ADMIN).get_json()["activo"]
    assert ficha["ubicacion"]["id"] == cat["bodega"]
    assert ficha["row_version"] == 2
    with dis_db.migrator.connect() as conn:
        tipo, datos, sesion_id, verificacion_id = conn.execute(
            text(
                "select tipo, datos, sesion_id, verificacion_id from activo_evento "
                "where activo_id = :a and tipo = 'ubicacion_cambiada'"
            ),
            {"a": activo["id"]},
        ).one()
        # La verificación no cambia (inmutable).
        esperada = conn.scalar(
            text("select ubicacion_esperada_id from verificacion where id = :v"), {"v": v}
        )
    assert (str(sesion_id), str(verificacion_id)) == (sesion, v)
    assert datos == {
        "antes": {"id": cat["box"], "ruta": "Consultorios › Box 1"},
        "despues": {"id": cat["bodega"], "ruta": "Bodega"},
        "origen": "discrepancia",
        "sesion": "Conteo nov 2026",
    }
    assert str(esperada) == cat["box"]


def test_applying_twice_or_discarding_after_is_ya_resuelta(client, cat, sesion):
    activo = nuevo(client, cat)
    v = verificar(client, sesion, activo, cat["bodega"])
    assert resultados(accion(client, sesion, "aplicar", [v])) == {v: "aplicada"}
    assert resultados(accion(client, sesion, "aplicar", [v])) == {v: "ya_resuelta"}
    assert resultados(accion(client, sesion, "descartar", [v])) == {v: "ya_resuelta"}


def test_desfase_needs_confirmation(client, cat, sesion):
    activo = nuevo(client, cat)
    v = verificar(client, sesion, activo, cat["bodega"])
    mover(client, activo, cat["adm"], 1)
    assert resultados(accion(client, sesion, "aplicar", [v])) == {v: "desfasada"}
    ficha = client.get(f"/activos/{activo['id']}", headers=ADMIN).get_json()["activo"]
    assert ficha["ubicacion"]["id"] == cat["adm"]
    response = accion(client, sesion, "aplicar", [v], confirmar_desfase=True)
    assert resultados(response) == {v: "aplicada"}
    ficha = client.get(f"/activos/{activo['id']}", headers=ADMIN).get_json()["activo"]
    assert ficha["ubicacion"]["id"] == cat["bodega"]


def test_already_where_it_was_found_suggests_discarding(client, cat, sesion):
    activo = nuevo(client, cat)
    v = verificar(client, sesion, activo, cat["bodega"])
    mover(client, activo, cat["bodega"], 1)
    response = accion(client, sesion, "aplicar", [v], confirmar_desfase=True)
    assert resultados(response) == {v: "ya_en_la_encontrada"}
    assert resultados(accion(client, sesion, "descartar", [v])) == {v: "descartada"}


def test_found_location_now_inactive_and_written_off_assets(client, cat, sesion):
    vieja = client.post(
        "/ubicaciones",
        json={"nombre": f"Vieja {uuid.uuid4().hex[:4]}", "tipo": "sala", "padre_id": cat["sede"]},
        headers=ADMIN,
    ).get_json()["ubicacion"]["id"]
    a, b = nuevo(client, cat), nuevo(client, cat)
    va = verificar(client, sesion, a, vieja)
    vb = verificar(client, sesion, b, cat["bodega"])
    assert (
        client.patch(f"/ubicaciones/{vieja}", json={"activa": False}, headers=ADMIN).status_code
        == 200
    )
    client.post(
        f"/activos/{b['id']}/baja", json={"motivo": "perdido"}, headers={**ADMIN, "If-Match": "1"}
    )
    assert resultados(accion(client, sesion, "aplicar", [va, vb])) == {
        va: "ubicacion_invalida",
        vb: "dado_de_baja",
    }
    assert resultados(accion(client, sesion, "descartar", [va, vb])) == {
        va: "descartada",
        vb: "descartada",
    }


def test_batch_reports_each_one(client, cat, sesion):
    a, b, igual = nuevo(client, cat), nuevo(client, cat), nuevo(client, cat)
    va = verificar(client, sesion, a, cat["bodega"])
    vb = verificar(client, sesion, b, cat["adm"])
    vi = verificar(client, sesion, igual, cat["box"])
    vieja = verificar(client, sesion, a, cat["adm"])  # va deja de ser la vigente
    ajena = str(uuid.uuid4())
    res = resultados(accion(client, sesion, "aplicar", [va, vb, vi, vieja, ajena]))
    assert res == {
        va: "ya_no_es_discrepancia",
        vb: "aplicada",
        vi: "ya_no_es_discrepancia",
        vieja: "aplicada",
        ajena: "no_encontrada",
    }


def test_closed_session_can_still_be_resolved(client, cat, sesion, dis_db):
    activo = nuevo(client, cat)
    v = verificar(client, sesion, activo, cat["bodega"])
    cerrar(dis_db, sesion)
    assert resultados(accion(client, sesion, "aplicar", [v])) == {v: "aplicada"}


@pytest.mark.parametrize(
    "body",
    [
        {"verificaciones": []},
        {"verificaciones": ["x"]},
        {"verificaciones": "uno"},
        {"verificaciones": [str(uuid.uuid4())] * 2},
        {"verificaciones": [str(uuid.uuid4()) for _ in range(101)]},
        {"verificaciones": [str(uuid.uuid4())], "confirmar_desfase": "si"},
        {"verificaciones": [str(uuid.uuid4())], "otro": 1},
    ],
)
def test_invalid_batches_are_400(client, sesion, body):
    response = client.post(f"/sesiones/{sesion}/discrepancias/aplicar", json=body, headers=ADMIN)
    assert response.status_code == 400
    assert code(response) == "solicitud_invalida"


def test_actions_are_admin_only(client, cat, sesion):
    activo = nuevo(client, cat)
    v = verificar(client, sesion, activo, cat["bodega"])
    for nombre in ("aplicar", "descartar"):
        assert accion(client, sesion, nombre, [v], headers=CONTADOR).status_code == 403
        assert accion(client, sesion, nombre, [v], headers=ADMIN_OTRO).status_code == 404
    assert lista(client, sesion).get_json()["discrepancias"][0]["estado"] == "pendiente"


def test_two_admins_applying_at_once_leave_one_resolution(client, cat, sesion, dis_db):
    import threading

    activo = nuevo(client, cat)
    v = verificar(client, sesion, activo, cat["bodega"])
    salida: list[str] = []
    barrera = threading.Barrier(2)

    def aplicar():
        barrera.wait()
        salida.extend(resultados(accion(client, sesion, "aplicar", [v])).values())

    hilos = [threading.Thread(target=aplicar) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=10)
    assert sorted(salida) == ["aplicada", "ya_resuelta"]
    with dis_db.migrator.connect() as conn:
        assert (
            conn.scalar(
                text(
                    "select count(*) from activo_evento "
                    "where verificacion_id = :v and tipo = 'ubicacion_cambiada'"
                ),
                {"v": v},
            )
            == 1
        )


# --- T4: pendientes ----------------------------------------------------------------------


def test_pending_by_location_without_prices(client, cat, sesion):
    hecho = nuevo(client, cat, "bodega", "Hecho")
    falta = nuevo(client, cat, "bodega", "Falta")
    reparacion = nuevo(client, cat, "bodega", "En taller")
    baja = nuevo(client, cat, "bodega", "Baja")
    client.post(
        f"/activos/{reparacion['id']}/estado",
        json={"estado": "en_reparacion"},
        headers={**ADMIN, "If-Match": "1"},
    )
    client.post(
        f"/activos/{baja['id']}/baja",
        json={"motivo": "perdido"},
        headers={**ADMIN, "If-Match": "1"},
    )
    verificar(client, sesion, hecho, cat["bodega"])

    for headers in (ADMIN, CONTADOR):
        response = client.get(
            f"/sesiones/{sesion}/pendientes",
            query_string={"ubicacion_id": cat["bodega"]},
            headers=headers,
        )
        assert response.status_code == 200
        cuerpo = response.get_json()
        nombres = {a["nombre"]: a for a in cuerpo["activos"]}
        assert {falta["nombre"], reparacion["nombre"]} <= set(nombres)
        assert hecho["nombre"] not in nombres and baja["nombre"] not in nombres
        assert nombres["En taller"]["estado"] == "en_reparacion"
        assert nombres["Falta"]["ubicacion"] == {"id": cat["bodega"], "ruta": "Bodega"}
        assert cuerpo["por_pagina"] == 50
        assert "precio" not in str(cuerpo) and "14200000" not in str(cuerpo)


def test_pending_pages_and_validation(client, cat, sesion):
    for i in range(3):
        nuevo(client, cat, "adm", f"Silla {i}")
    todos = client.get(f"/sesiones/{sesion}/pendientes", headers=CONTADOR).get_json()
    assert todos["total"] >= 3
    assert todos["pagina"] == 1
    assert (
        client.get(
            f"/sesiones/{sesion}/pendientes", query_string={"pagina": "0"}, headers=ADMIN
        ).status_code
        == 400
    )
    assert (
        client.get(
            f"/sesiones/{sesion}/pendientes", query_string={"ubicacion_id": "x"}, headers=ADMIN
        ).status_code
        == 400
    )
    assert client.get(f"/sesiones/{uuid.uuid4()}/pendientes", headers=ADMIN).status_code == 404
    assert client.get(f"/sesiones/{sesion}/pendientes", headers={}).status_code == 401
