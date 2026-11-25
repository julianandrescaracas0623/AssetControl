"""Exportar la lista de activos a Excel (spec 015, T4; R1, R1a; A1; Q1–Q4).

- ``GET /activos/exportar`` es solo del admin (``403`` al contador, ``401`` sin sesión)
  y respeta ``q``, ``estado`` y ``ubicacion_id`` con el mismo resultado y el mismo orden
  que ``GET /activos`` (una sola consulta, sin paginar).
- Columnas de Q3 (A), sin fila de total; el dinero es un número desde el ``Decimal``
  exacto con formato COP; ningún texto se vuelve fórmula; cero filas → solo encabezado.
- Tope técnico de Q4 (B): más filas que ``MAX_FILAS_EXPORTACION`` → ``413``.
- Nombre de archivo fijo (sin datos de la clínica), ``no-store`` y ``nosniff``; nada de
  los datos en los registros. Otro tenant no aparece.

Spec 019 (T3): el archivo replica la plantilla A (``Activos_20261122_diseno.xlsx``) a
través de su huella versionada (``tests/plantillas/activos.json``): bloque de empresa
vigente del tenant con logo (Q9, Q10), cabecera en la fila 7, datos desde la 8, sin paneles
inmovilizados (2026-11-24), filtro, impresión y formatos; los datos, el orden de filas y las
columnas no cambian. Las pruebas de diseño comparan propiedad por propiedad con
``utils_xlsx_diseno.comparar``.

El archivo se lee con ``openpyxl`` (otra librería que la que lo escribe) y con la utilidad
de diseño (ZIP + XML). Empresa, logo y activos de las pruebas son FICTICIOS.
"""

import copy
import io
import logging
import re
import uuid
import zipfile
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest
import utils_xlsx_diseno as u
from acceso_db import (
    ADMIN_A,
    ADMIN_B,
    CONTADOR_A,
    TENANT_A,
    TENANT_B,
    AccesoDb,
    bearer,
    dispose,
    make_app,
    temporary_acceso_db,
)
from botocore.exceptions import ClientError, EndpointConnectionError
from flask import Flask
from openpyxl import load_workbook
from PIL import Image
from sqlalchemy import text
from utils_logo import comprobar_logo_con_borde

from app.activos import exportar, service
from app.conteo import exportar_estilo as est
from app.fotos.almacen import EXTENSION_KEY, CarpetaLocal

ADMIN = bearer(ADMIN_A, TENANT_A)
CONTADOR = bearer(CONTADOR_A, TENANT_A, rol="contador")
ADMIN_OTRO = bearer(ADMIN_B, TENANT_B)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
CENTAVO = Decimal("0.01")
ENCABEZADO = [
    "Código",
    "Nombre",
    "Categoría",
    "Ubicación",
    "Estado",
    "Serial",
    "Marca",
    "Modelo",
    "Subtipo",
    "Fecha de compra",
    "Precio de compra",
    "Registrado el",
]


@pytest.fixture(scope="module")
def exa_db(database_residue_guard) -> Iterator[AccesoDb]:
    yield from temporary_acceso_db("activos_exportar")


@pytest.fixture(scope="module")
def almacen_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("almacen_activos")


@pytest.fixture(scope="module")
def exa_app(exa_db, almacen_dir) -> Iterator[Flask]:
    flask_app = make_app(exa_db)
    flask_app.extensions[EXTENSION_KEY] = CarpetaLocal(almacen_dir)
    yield flask_app
    dispose(flask_app)


@pytest.fixture
def client(exa_app):
    return exa_app.test_client(use_cookies=False)


@pytest.fixture(autouse=True)
def tenant_limpio(exa_db) -> Iterator[None]:
    yield
    with exa_db.migrator.begin() as conn:
        for sql in (
            "update empresa set logo_id = null",
            "delete from empresa",
            "delete from empresa_logo",
            "delete from activo_evento",
            "delete from activo",
            "delete from ubicacion",
            "delete from categoria",
        ):
            conn.execute(text(sql))


class Catalogo:
    """Sede › Consultorios › Box 1 y Bodega; Biomédicos y Mobiliario (por la API)."""

    def __init__(self, client, headers=ADMIN):
        self.client, self.headers = client, headers
        sede = self._post("/ubicaciones", {"nombre": "Sede", "tipo": "sede"})["ubicacion"]["id"]
        self.sala = self._post(
            "/ubicaciones", {"nombre": "Consultorios", "tipo": "sala", "padre_id": sede}
        )["ubicacion"]["id"]
        self.box = self._post(
            "/ubicaciones", {"nombre": "Box 1", "tipo": "box", "padre_id": self.sala}
        )["ubicacion"]["id"]
        self.bodega = self._post(
            "/ubicaciones", {"nombre": "Bodega", "tipo": "sala", "padre_id": sede}
        )["ubicacion"]["id"]
        self.bio = self._post("/categorias", {"nombre": "Biomédicos"})["categoria"]["id"]
        self.mob = self._post("/categorias", {"nombre": "Mobiliario"})["categoria"]["id"]

    def _post(self, path, body):
        response = self.client.post(path, json=body, headers=self.headers)
        assert response.status_code in (200, 201), response.get_json()
        return response.get_json()

    def activo(self, nombre, precio="10.00", categoria=None, ubicacion=None, **extra) -> dict:
        body = {
            "id": str(uuid.uuid4()),
            "codigo": f"EXA-{uuid.uuid4().hex[:8]}".upper(),
            "nombre": nombre,
            "precio_compra": precio,
            "categoria_id": categoria or self.bio,
            "ubicacion_id": ubicacion or self.box,
            **extra,
        }
        return self._post("/activos", body)["activo"]

    def accion(self, activo, ruta, body):
        response = self.client.post(
            f"/activos/{activo['id']}/{ruta}",
            json=body,
            headers={**self.headers, "If-Match": f'"{activo["row_version"]}"'},
        )
        assert response.status_code == 200, response.get_json()
        return response.get_json()["activo"]


def exportar_(client, headers=ADMIN, **params):
    return client.get("/activos/exportar", query_string=params, headers=headers)


FILA_CABECERA = 7  # spec 019: bloque de empresa en las filas 1–5, cabecera en la 7
FILA_DATOS = 8


def filas(response) -> list[tuple]:
    """Filas de datos (bajo el encabezado de la fila 7) de la única hoja."""
    assert response.status_code == 200, response.get_json()
    hoja = load_workbook(io.BytesIO(response.data)).worksheets[0]
    todas = list(hoja.iter_rows(min_row=FILA_CABECERA, max_col=len(ENCABEZADO), values_only=True))
    assert list(todas[0]) == ENCABEZADO
    return todas[1:]


def lista_completa(client, **params) -> list[str]:
    """Códigos de ``GET /activos`` recorriendo todas las páginas, en su orden."""
    codigos, pagina = [], 1
    while True:
        response = client.get("/activos", query_string={**params, "pagina": pagina}, headers=ADMIN)
        assert response.status_code == 200, response.get_json()
        cuerpo = response.get_json()
        codigos += [a["codigo"] for a in cuerpo["activos"]]
        if pagina * cuerpo["por_pagina"] >= cuerpo["total"]:
            return codigos
        pagina += 1


def test_export_has_the_same_rows_and_order_as_the_list_with_each_filter(client):
    c = Catalogo(client)
    reparada = c.activo("Silla en reparación", categoria=c.mob)
    c.accion(reparada, "estado", {"estado": "en_reparacion"})
    baja = c.activo("Silla dada de baja", ubicacion=c.bodega)
    c.accion(baja, "baja", {"motivo": "perdido"})
    for i in range(28):  # más de una página de la lista (25)
        c.activo(f"Archivador {i}", ubicacion=c.bodega if i % 2 else c.box)
    for params in (
        {},
        {"q": "silla"},
        {"q": reparada["codigo"].lower()},
        {"estado": "en_reparacion"},
        {"estado": "dado_de_baja"},
        {"estado": "activo"},
        {"ubicacion_id": c.bodega},
        {"ubicacion_id": c.bodega, "estado": "activo", "q": "archivador"},
    ):
        esperados = lista_completa(client, **params)
        assert [f[0] for f in filas(exportar_(client, **params))] == esperados, params
    # «Todos» incluye los dados de baja, igual que la lista (Q3 A).
    assert baja["codigo"] in [f[0] for f in filas(exportar_(client))]


def test_each_column_has_the_decided_value(client):
    c = Catalogo(client)
    activo = c.activo(
        "Autoclave",
        precio="1390000.50",
        serial="SN-1",
        marca="Tuttnauer",
        modelo="2540",
        subtipo="Clase B",
        fecha_compra="2024-01-31",
    )
    c.accion(activo, "estado", {"estado": "en_reparacion"})
    sin_opcionales = c.activo("Silla", precio="389900.00", categoria=c.mob, ubicacion=c.bodega)
    por_codigo = {f[0]: f for f in filas(exportar_(client))}

    fila = por_codigo[activo["codigo"]]
    assert fila[:9] == (
        activo["codigo"],
        "Autoclave",
        "Biomédicos",
        "Consultorios › Box 1",
        "En reparación",
        "SN-1",
        "Tuttnauer",
        "2540",
        "Clase B",
    )
    assert fila[9] == datetime(2024, 1, 31)
    assert Decimal(str(fila[10])).quantize(CENTAVO) == Decimal("1390000.50")
    registrado = datetime.fromisoformat(activo["creado_en"]).astimezone(exportar.HORA_COLOMBIA)
    assert fila[11] == datetime.combine(registrado.date(), datetime.min.time())

    otra = por_codigo[sin_opcionales["codigo"]]
    assert otra[2:5] == ("Mobiliario", "Bodega", "Activo")
    assert otra[5:10] == (None, None, None, None, None)
    assert Decimal(str(otra[10])).quantize(CENTAVO) == Decimal("389900.00")
    # Sin fila de total (Q3 A): solo los dos activos.
    assert len(por_codigo) == 2


def test_money_is_an_exact_number_with_cop_format_and_there_are_no_formulas(client):
    c = Catalogo(client)
    c.activo("Autoclave", precio="1390000.50")
    response = exportar_(client)
    hoja = load_workbook(io.BytesIO(response.data)).worksheets[0]
    precio = hoja.cell(row=FILA_DATOS, column=11)
    assert isinstance(precio.value, (int, float))
    # Spec 019: el formato de la columna de precio de la plantilla A (huella), no la constante.
    formato_precio = HUELLA["hojas"][HOJA]["celdas"]["K8"]["estilo"]["formato"]["codigo"]
    assert precio.number_format == formato_precio
    # Spec 019 (A7): fecha incorporada 14 de la plantilla (según la configuración regional).
    assert hoja.cell(row=FILA_DATOS, column=12).number_format == "mm-dd-yy"
    with zipfile.ZipFile(io.BytesIO(response.data)) as z:
        hojas = "".join(z.read(n).decode() for n in z.namelist() if n.startswith("xl/worksheets/"))
    assert "<f>" not in hojas
    # Escrito desde el Decimal exacto, no desde un float redondeado.
    assert "<v>1390000.50</v>" in hojas


@pytest.mark.parametrize("peligroso", ["=1+1", "+57 300", "-2+3", "@SUMA(A1)"])
def test_text_that_looks_like_a_formula_stays_text(client, peligroso):
    c = Catalogo(client)
    c.activo(peligroso, serial=peligroso, marca=peligroso, modelo=peligroso, subtipo=peligroso)
    response = exportar_(client)
    hoja = load_workbook(io.BytesIO(response.data)).worksheets[0]
    for col in (2, 6, 7, 8, 9):
        celda = hoja.cell(row=FILA_DATOS, column=col)
        assert celda.value == peligroso
        assert celda.data_type == "s", (col, celda.data_type)


def test_with_no_results_the_file_has_only_the_header(client):
    Catalogo(client)
    assert filas(exportar_(client)) == []
    response = exportar_(client, q="no-existe")
    assert filas(response) == []
    # Sin filas, el filtro y el área de impresión terminan en la cabecera (fila 7).
    hoja = u.extraer(response.data)["hojas"]["Activos"]
    assert hoja["autofiltro"] == "A7:L7"
    assert hoja["impresion"]["area"] == "Activos!$A$1:$L$7"
    assert not [r for r in hoja["celdas"] if u.ref_a_rc(r)[0] >= FILA_DATOS]


def test_sheet_has_a_filter_and_no_frozen_panes(client):
    c = Catalogo(client)
    c.activo("Autoclave")
    c.activo("Silla")
    hoja = load_workbook(io.BytesIO(exportar_(client).data)).worksheets[0]
    assert hoja.title == "Activos"
    # Filtra desde la cabecera (fila 7). Sin paneles inmovilizados (decisión del humano
    # 2026-11-24): la línea del corte no se puede ocultar en Excel.
    assert hoja.freeze_panes is None
    assert hoja.auto_filter.ref == "A7:L9"


def test_download_headers_and_a_fixed_file_name(client):
    c = Catalogo(client)
    c.activo("Clínica & Ejemplo")
    response = exportar_(client, q="clínica")
    assert response.status_code == 200
    assert response.mimetype == XLSX
    disposicion = response.headers["Content-Disposition"]
    hoy = datetime.now(exportar.HORA_COLOMBIA).date()
    nombre = f"activos-{hoy:%Y%m%d}.xlsx"
    assert disposicion == f"attachment; filename=\"{nombre}\"; filename*=UTF-8''{nombre}"
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_only_the_admin_exports_and_the_contador_gets_no_price(client):
    c = Catalogo(client)
    c.activo("Autoclave", precio="1390000.50")
    prohibido = exportar_(client, CONTADOR)
    assert prohibido.status_code == 403
    assert prohibido.mimetype == "application/json"
    assert "1390000" not in prohibido.get_data(as_text=True)
    assert prohibido.get_json()["error"]["code"] == "prohibido"
    assert exportar_(client, {}).status_code == 401


def test_other_tenant_is_not_exported(client):
    propio = Catalogo(client).activo("Autoclave")
    ajeno = Catalogo(client, ADMIN_OTRO).activo("Autoclave del otro")
    assert [f[0] for f in filas(exportar_(client))] == [propio["codigo"]]
    assert [f[0] for f in filas(exportar_(client, ADMIN_OTRO))] == [ajeno["codigo"]]
    # Filtrar por una ubicación del otro tenant no la revela: no hay filas.
    assert filas(exportar_(client, ubicacion_id=ajeno["ubicacion"]["id"])) == []


@pytest.mark.parametrize(
    "params",
    [{"estado": "otro"}, {"q": "x" * 121}, {"ubicacion_id": "no-es-uuid"}],
)
def test_invalid_filters_are_400(client, params):
    response = exportar_(client, **params)
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "solicitud_invalida"


def test_more_rows_than_the_cap_is_413_with_a_clear_message(client, monkeypatch):
    assert service.MAX_FILAS_EXPORTACION == 5_000  # Q4 (B), decidido por el humano.
    c = Catalogo(client)
    for i in range(3):
        c.activo(f"Archivador {i}")
    monkeypatch.setattr(service, "MAX_FILAS_EXPORTACION", 3)
    assert len(filas(exportar_(client))) == 3  # justo en el tope: se exporta
    c.activo("Uno más")
    response = exportar_(client)
    assert response.status_code == 413
    error = response.get_json()["error"]
    assert error["code"] == "exportacion_demasiado_grande"
    assert error["message"] == (
        "Hay más de 3 activos para exportar. Filtra por búsqueda, estado o ubicación."
    )
    # Con un filtro que deja menos filas, vuelve a funcionar.
    assert len(filas(exportar_(client, q="uno más"))) == 1


def test_export_does_not_log_names_codes_or_prices(client, caplog):
    c = Catalogo(client)
    activo = c.activo("Autoclave secreto", precio="1390000.50", serial="SN-SECRETO")
    with caplog.at_level(logging.DEBUG):
        assert exportar_(client, q="autoclave").status_code == 200
    registros = " ".join(r.getMessage() for r in caplog.records)
    assert not re.search(rf"1390000|Autoclave|SN-SECRETO|{activo['codigo']}", registros)


def test_registered_date_is_a_real_date(client):
    c = Catalogo(client)
    c.activo("Autoclave")
    (fila,) = filas(exportar_(client))
    assert isinstance(fila[11], datetime)
    assert fila[11].date() == datetime.now(exportar.HORA_COLOMBIA).date()


@pytest.mark.parametrize("tope", [1, 2])
def test_exactly_the_cap_is_200_and_one_more_is_413(client, monkeypatch, tope):
    c = Catalogo(client)
    for i in range(tope):
        c.activo(f"Archivador {i}")
    monkeypatch.setattr(service, "MAX_FILAS_EXPORTACION", tope)
    assert len(filas(exportar_(client))) == tope
    c.activo("Archivador extra")
    response = exportar_(client)
    assert response.status_code == 413
    assert response.get_json()["error"]["code"] == "exportacion_demasiado_grande"


def test_413_body_has_no_data_of_the_activos(client, monkeypatch):
    c = Catalogo(client)
    activos = [
        c.activo("Autoclave secreto", precio="1390000.50", serial="SN-SECRETO", marca="Tuttnauer"),
        c.activo("Silla secreta", precio="389900.00", categoria=c.mob, ubicacion=c.bodega),
    ]
    monkeypatch.setattr(service, "MAX_FILAS_EXPORTACION", 1)
    response = exportar_(client)
    assert response.status_code == 413
    assert response.mimetype == "application/json"
    cuerpo = response.get_data(as_text=True)
    assert set(response.get_json()) == {"error"}
    prohibidos = ["1390000", "389900", "Autoclave", "Silla", "SN-SECRETO", "Tuttnauer"]
    prohibidos += ["Biomédicos", "Mobiliario", "Bodega", "Box 1", "Consultorios"]
    for a in activos:
        prohibidos += [a["codigo"], a["id"], a["ubicacion"]["id"]]
    for dato in prohibidos:
        assert dato not in cuerpo, dato


CON_BARRA = "Ruta c\\d"


@pytest.mark.parametrize(
    ("q", "esperado"),
    [
        ("%", "Algodón 100% puro"),
        ("_", "Tubo a_b"),
        ("\\", CON_BARRA),
        ("0%", "Algodón 100% puro"),
    ],
)
def test_like_wildcards_in_q_are_literal_and_match_the_list(client, q, esperado):
    c = Catalogo(client)
    for nombre in ("Algodón 100% puro", "Tubo a_b", CON_BARRA, "Otro activo", "Silla"):
        c.activo(nombre)
    exportados = filas(exportar_(client, q=q))
    assert [f[0] for f in exportados] == lista_completa(client, q=q)
    assert [f[1] for f in exportados] == [esperado]


def test_percent_alone_does_not_export_everything(client):
    c = Catalogo(client)
    for nombre in ("Autoclave", "Silla", "Mesa"):
        c.activo(nombre)
    assert filas(exportar_(client, q="%")) == []
    assert filas(exportar_(client, q="_")) == []
    assert len(filas(exportar_(client))) == 3


PELIGROSOS_CATALOGO = [
    "=cmd|' /C calc'!A0",
    "+57 Sede",
    "-2 Bodega",
    "@Sala 1",
    "\tTabulada",
    "Con\nsalto",
]


@pytest.mark.parametrize("peligroso", PELIGROSOS_CATALOGO)
def test_category_and_location_names_that_look_like_formulas_stay_text(client, exa_db, peligroso):
    c = Catalogo(client)
    activo = c.activo("Autoclave")
    # La API no deja crear tabuladores ni saltos (nombres.py): se escriben directo en la
    # base para cubrir datos ya existentes o importados.
    with exa_db.migrator.begin() as conn:
        conn.execute(
            text("update categoria set nombre = :n where id = :id"),
            {"n": peligroso, "id": c.bio},
        )
        conn.execute(
            text("update ubicacion set nombre = :n where id = :id"),
            {"n": peligroso, "id": c.box},
        )
    response = exportar_(client)
    assert response.status_code == 200
    hoja = load_workbook(io.BytesIO(response.data)).worksheets[0]
    assert hoja.cell(row=FILA_DATOS, column=1).value == activo["codigo"]
    categoria = hoja.cell(row=FILA_DATOS, column=3)
    ubicacion = hoja.cell(row=FILA_DATOS, column=4)
    assert categoria.value == peligroso
    assert ubicacion.value == f"Consultorios › {peligroso}"
    assert categoria.data_type == "s"
    assert ubicacion.data_type == "s"
    with zipfile.ZipFile(io.BytesIO(response.data)) as z:
        hojas = "".join(z.read(n).decode() for n in z.namelist() if n.startswith("xl/worksheets/"))
    assert "<f>" not in hojas


# ---------------------------------------------------------------------------
# Spec 019, T3: diseño de la plantilla A (huella ``tests/plantillas/activos.json``)
# ---------------------------------------------------------------------------
#
# Decisión de la celda vacía (pendiente del reviewer en T2): una celda de datos sin valor
# lleva el estilo de SU columna en la fila de datos de la plantilla (req. 5: «repetir el
# estilo de la fila de datos en cada fila»). La plantilla A lo determina: F8 e I8, vacías,
# tienen exactamente el estilo de las celdas de texto (A8, G8…); no existe en ella un estilo
# «vacía» distinto (``datos_vacia`` es del informe, T4). Así, fecha y precio vacíos llevan
# ``datos_fecha``/``datos_cop`` (sin valor se ven igual que ``datos``, con el mismo borde).

HUELLA = u.cargar_huella("activos")
HOJA = "Activos"
COLUMNAS = [u.col_letra(i) for i in range(1, 13)]

EMPRESA = {
    "nombre": "Clínica Ficticia de Prueba S.A.S.",
    "direccion": "Calle Falsa 00 # 00-00, Ciudad Ficticia",
    "nit": "900123456-8",
    "telefono": "600 000 0000",
    "correo": "contacto@ejemplo.test",
}
NIT_NORMALIZADO = "900.123.456-8"
EMPRESA_AJENA = {
    "nombre": "Empresa Ajena de Prueba Ltda.",
    "direccion": "Avenida Ajena 99, Otra Ciudad",
    "nit": "800197268",
    "telefono": "611 111 1111",
    "correo": "ajena@otro.test",
}
TEXTOS_AJENOS = [*EMPRESA_AJENA.values(), "800.197.268"]


def _png(ancho: int = 600, alto: int = 240, color=(29, 78, 216)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (ancho, alto), (*color, 255)).save(buffer, "PNG")
    return buffer.getvalue()


def con_empresa(client, datos=EMPRESA, logo: bytes | None = None, headers=ADMIN) -> str | None:
    """Guarda la empresa del tenant (y su logo) por la API; devuelve el ``logo_id``."""
    respuesta = client.put("/empresa", json=datos, headers=headers)
    assert respuesta.status_code == 200, respuesta.get_json()
    if logo is None:
        return None
    logo_id = str(uuid.uuid4())
    subida = client.put(
        "/empresa/logo",
        data={"logo_id": logo_id, "archivo": (io.BytesIO(logo), "logo.png")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert subida.status_code == 201, subida.get_json()
    return logo_id


def hoy() -> date:
    return datetime.now(exportar.HORA_COLOMBIA).date()


def diseno(response) -> dict[str, Any]:
    assert response.status_code == 200, response.get_json()
    return u.extraer(response.data)


def hoja_de(response) -> dict[str, Any]:
    return diseno(response)["hojas"][HOJA]


def esperada() -> dict[str, Any]:
    return copy.deepcopy(HUELLA["hojas"][HOJA])


def _fila(ref: str) -> int:
    return u.ref_a_rc(ref)[0]


def fecha_exportada(hoja: dict[str, Any], antes: date, despues: date) -> date:
    """La fecha de la línea junto al logo (C3, «Informe · empresa · exportado dd/mm/aaaa»):
    la de hoy en Colombia (Q9)."""
    texto = hoja["celdas"]["C3"]["valor"]
    fecha = datetime.strptime(texto.rsplit(" ", 1)[-1], "%d/%m/%Y").date()
    assert fecha in (antes, despues), texto
    return fecha


LINEA_EMPRESA = re.compile(r"^Informe · (.*) · exportado \d{2}/\d{2}/\d{4}$")


def empresa_en_linea(hoja: dict[str, Any]) -> str:
    """El nombre de la empresa dentro de la línea junto al logo (C3): «Informe · empresa ·
    exportado dd/mm/aaaa». Exige el formato completo y que la celda sea texto."""
    celda = hoja["celdas"]["C3"]
    assert celda["tipo"] == "s", celda
    coincide = LINEA_EMPRESA.match(celda["valor"])
    assert coincide, celda["valor"]
    return coincide.group(1)


def textos_bloque(fecha: date, nombre, nit=None, telefono=None, correo=None, direccion=None):
    """Lo que debe decir cada marcador del bloque (filas 1–5); ``None`` = celda vacía.

    Empresa, Contacto y Dirección (2026-11-24): cada grupo une sus datos presentes en
    líneas; un grupo sin datos queda vacío y sin su rótulo (Q9)."""

    def lineas(*partes):
        return "\n".join(p for p in partes if p) or None

    empresa = lineas(nombre, f"NIT {nit}" if nit else None)
    contacto = lineas(correo, f"Tel. {telefono}" if telefono else None)
    direccion = direccion or None
    return {
        "Informe · {empresa.nombre} · exportado {fecha}": (
            f"Informe · {nombre} · exportado {fecha:%d/%m/%Y}"
        ),
        "Empresa": "Empresa" if empresa else None,
        "Contacto": "Contacto" if contacto else None,
        "Dirección": "Dirección" if direccion else None,
        "{empresa.nombre}\nNIT {empresa.nit}": empresa,
        "{empresa.correo}\nTel. {empresa.telefono}": contacto,
        "{empresa.direccion}": direccion,
    }


def comprobar_bloque(hoja: dict[str, Any], textos: dict[str, Any]) -> None:
    """Filas 1–5: mismas celdas y estilos que la plantilla (la línea azul de la fila 5 sigue
    entera aunque falten datos), con los textos esperados o la celda vacía."""
    esp = {r: c for r, c in esperada()["celdas"].items() if _fila(r) <= 5}
    gen = {r: c for r, c in hoja["celdas"].items() if _fila(r) <= 5}
    assert sorted(gen) == sorted(esp)
    for ref, celda in esp.items():
        assert u.comparar(celda["estilo"], gen[ref]["estilo"], ref) == []
        valor = textos.get(celda["valor"], celda["valor"])
        if valor is None:
            assert gen[ref]["tipo"] == "vacia", (ref, gen[ref]["valor"])
        else:
            assert (gen[ref]["tipo"], gen[ref]["valor"]) == ("s", valor), ref


def _rango_hasta(valor: str, ultima: int) -> str:
    """``Activos!$A$1:$L$8`` → el mismo rango hasta la fila ``ultima`` (req. 5)."""
    return re.sub(r"\d+$", str(ultima), valor)


def comprobar_imagen(imagen: dict[str, Any], ancho: int, alto: int) -> None:
    """El logo, en la caja de la plantilla con su proporción (Q10) y los equivalentes
    aceptados (Q13: ancla; L8: nombre «Picture N» y bloqueo de proporción; cstate)."""
    (esp,) = esperada()["imagenes"]
    # Caja de la plantilla (Q10) y proporción del logo; con su borde redondeado en la misma
    # imagen y centrado en altura (decisiones del humano 2026-11-24 y 2026-11-25).
    comprobar_logo_con_borde(
        imagen, est.PLANTILLAS["activos"].caja_logo, _png(ancho, alto), ancho, alto
    )
    for k in ("descr", "titulo", "oculta", "decorativa", "estirar", "geometria", "linea"):
        assert imagen[k] == esp[k], k
    assert imagen["nombre"] == "Picture 1"  # L8, equivalente aceptado (plantilla: «Image 1»)
    assert imagen["bloqueos"] == {"noChangeAspect": "1"}  # L8, equivalente aceptado
    assert imagen["cstate"] is None  # cstate_y_ln, equivalente aceptado (plantilla: «print»)
    assert imagen["ext"] is None and imagen["hasta"] is not None  # Q13: twoCellAnchor
    assert imagen["medio"] == esp["medio"]
    assert {k: v for k, v in imagen["imagen"].items() if k not in ("ancho", "alto")} == {
        k: v for k, v in esp["imagen"].items() if k not in ("ancho", "alto")
    }  # PNG sin pHYs, como la plantilla
    # La imagen guardada es la compuesta (logo y borde), no el logo tal cual.
    compuesto = est.componer_logo(_png(ancho, alto))
    assert (imagen["imagen"]["ancho"], imagen["imagen"]["alto"]) == compuesto[1:]


LIBRO_IGUAL = (
    "hojas",
    "estados",
    "hoja_activa",
    "primera_hoja_visible",
    "pestanas_visibles",
    "proteccion",
    "fecha_1904",
    "tema",
    "fuente_defecto",
    "estilo_defecto",
    "estilos_tabla",
    "dxfs",
)
HOJA_IGUAL = (
    "pestana",
    "esquema",
    "columnas",
    "combinadas",
    "formato_condicional",
    "formato_condicional_ext",
    "validaciones",
    "hipervinculos",
    "proteccion",
    "tablas",
    "pagina",
    "indice",
    "estado",
)


def test_el_libro_replica_la_huella_de_la_plantilla_a(client):
    """FT-1 a FT-3: libro y hoja, propiedad por propiedad, contra ``activos.json``."""
    con_empresa(client, logo=_png())
    c = Catalogo(client)
    # Como la fila de datos de la plantilla: sin serial ni subtipo (F8 e I8 vacías).
    autoclave = c.activo(
        "Autoclave", precio="1390000.50", marca="Marca X", modelo="M-1", fecha_compra="2024-01-31"
    )
    silla = c.activo(
        "Silla",
        precio="389900.00",
        categoria=c.mob,
        ubicacion=c.bodega,
        marca="Marca Y",
        modelo="M-2",
        fecha_compra="2023-05-02",
    )
    antes = hoy()
    response = exportar_(client)
    despues = hoy()
    gen = diseno(response)
    libro, esp_libro = gen["libro"], HUELLA["libro"]
    ultima = FILA_CABECERA + 2

    # Libro: hojas, tema y fuente por defecto, estilos de tabla, dxf, nombres definidos.
    for k in LIBRO_IGUAL:
        assert u.comparar(esp_libro[k], libro[k], k) == []
    assert u.sha256_tema(response.data) == esp_libro["tema_sha256"]
    nombres = [
        d
        if d["nombre"] == "_xlnm.Print_Titles"
        else {**d, "valor": _rango_hasta(d["valor"], ultima)}
        for d in esp_libro["nombres_definidos"]
    ]

    def orden(lista):
        return sorted(lista, key=lambda d: d["nombre"])

    assert u.comparar(orden(nombres), orden(libro["nombres_definidos"])) == []
    # Fila 26 (decisión del humano): título del libro y autor neutro, nada del equipo.
    core = libro["propiedades"]["core"]
    assert core["title"] == HOJA
    assert core["creator"] == core["lastModifiedBy"] == "AssetControl"
    assert set(core) == {"title", "creator", "lastModifiedBy", "created", "modified"}
    assert libro["medios"] == ["xl/media/image1.png"]  # Q13: un medio

    # Hoja: todo lo que no depende del número de filas, idéntico a la plantilla.
    hoja, esp = gen["hojas"][HOJA], esperada()
    for k in HOJA_IGUAL:
        assert u.comparar(esp[k], hoja[k], k) == []
    for k in ("alto_fila_defecto", "filas_ocultas_defecto", "alto_propio_defecto"):
        assert hoja["formato_hoja"][k] == esp["formato_hoja"][k], k
    # Vista: sin paneles inmovilizados (2026-11-24) y sin cuadrícula; Q11: primera hoja, sin
    # desplazamiento ni la celda activa de edición de la plantilla (J17).
    vista_esp = {k: v for k, v in esp["vista"].items() if k != "seleccion"}
    vista_gen = {k: v for k, v in hoja["vista"].items() if k != "seleccion"}
    assert u.comparar(vista_esp, vista_gen, "vista") == []
    assert hoja["vista"]["panel"] is None
    assert hoja["vista"]["seleccion"] == []  # Excel abre en A1

    # Rangos que se extienden hasta la última fila escrita (req. 5).
    assert hoja["autofiltro"] == f"A7:L{ultima}"
    assert hoja["impresion"] == {
        "area": f"Activos!$A$1:$L${ultima}",
        "titulos": esp["impresion"]["titulos"],
        "filtro": f"Activos!$A$7:$L${ultima}",
    }

    # Alturas: filas 1–5 y 7 de la plantilla; cada fila de datos, la de la fila 8.
    filas_esp = {n: f for n, f in esp["filas"].items() if int(n) < FILA_DATOS}
    filas_esp.update({str(n): esp["filas"]["8"] for n in range(FILA_DATOS, ultima + 1)})
    assert u.comparar(filas_esp, hoja["filas"], "filas") == []

    # Celdas: bloque, cabecera y cada fila de datos con el estilo de su columna en la fila 8.
    fecha = fecha_exportada(hoja, antes, despues)
    comprobar_bloque(
        hoja,
        textos_bloque(
            fecha,
            EMPRESA["nombre"],
            NIT_NORMALIZADO,
            EMPRESA["telefono"],
            EMPRESA["correo"],
            EMPRESA["direccion"],
        ),
    )
    refs_esp = {r for r in esp["celdas"] if _fila(r) < FILA_DATOS}
    refs_esp |= {f"{col}{n}" for col in COLUMNAS for n in range(FILA_DATOS, ultima + 1)}
    assert sorted(hoja["celdas"]) == sorted(refs_esp)
    for col in COLUMNAS:
        cab = esp["celdas"][f"{col}7"]
        assert u.comparar(cab["estilo"], hoja["celdas"][f"{col}7"]["estilo"], f"{col}7") == []
        assert hoja["celdas"][f"{col}7"]["valor"] == cab["valor"]
        for n in range(FILA_DATOS, ultima + 1):
            ref, plantilla = f"{col}{n}", esp["celdas"][f"{col}8"]
            assert u.comparar(plantilla["estilo"], hoja["celdas"][ref]["estilo"], ref) == []
            assert hoja["celdas"][ref]["tipo"] == plantilla["tipo"], ref
    por_codigo = {hoja["celdas"][f"A{n}"]["valor"]: n for n in range(FILA_DATOS, ultima + 1)}
    for activo, textos in (
        (autoclave, ["Autoclave", "Biomédicos", "Consultorios › Box 1", "Activo"]),
        (silla, ["Silla", "Mobiliario", "Bodega", "Activo"]),
    ):
        n = por_codigo[activo["codigo"]]
        assert [hoja["celdas"][f"{col}{n}"]["valor"] for col in "BCDE"] == textos
        assert hoja["celdas"][f"G{n}"]["valor"] == activo["marca"]
        assert hoja["celdas"][f"H{n}"]["valor"] == activo["modelo"]

    # Logo (Q10, Q13, L8).
    (imagen,) = hoja["imagenes"]
    comprobar_imagen(imagen, 600, 240)

    # Cobertura XML (fila 27): nada de la plantilla falta y nada sobra, salvo lo decidido.
    comprobar_cobertura_xml(response.data)


# Lo que el generado escribe y la plantilla no, y por qué (Q13 / equivalentes aceptados).
SOBRANTES_ACEPTADOS = (
    (r"wsDr/twoCellAnchor.*", "Q13: ancla twoCellAnchor editAs=oneCell (y picLocks, L8)"),
    (r"workbook/calcPr@fullCalcOnLoad", "fullCalcOnLoad_activos (equivalente aceptado)"),
    (r"workbook/workbookPr@.*", "EQ L10: workbookPr sin atributos de efecto"),
)


def comprobar_cobertura_xml(contenido: bytes) -> None:
    generado, plantilla = u.inventario_xml(contenido), HUELLA["inventario_xml"]
    assert sorted(generado) == sorted(plantilla)
    for parte in plantilla:
        for ruta in sorted(set(plantilla[parte]) - set(generado[parte])):
            destino = u.destino_cobertura(f"{parte}:{ruta}") or ""
            gemela = ruta.replace("oneCellAnchor", "twoCellAnchor")
            aceptada = (
                destino.startswith("EQ")
                or "(Q11)" in destino  # selección de edición de la plantilla (J17)
                or (ruta.startswith("wsDr/oneCellAnchor") and gemela in generado[parte])
                # oneCellAnchor/ext: en twoCellAnchor el tamaño va en xfrm y en «to» (Q13).
                or ruta.startswith("wsDr/oneCellAnchor/ext")
            )
            assert aceptada, f"falta en el generado: {parte}:{ruta} ({destino})"
        for ruta in sorted(set(generado[parte]) - set(plantilla[parte])):
            assert any(re.fullmatch(p, ruta) for p, _ in SOBRANTES_ACEPTADOS), (
                f"sobra en el generado: {parte}:{ruta}"
            )


def test_las_celdas_vacias_de_cada_columna_llevan_su_estilo_con_borde(client):
    """Serial, marca, modelo, subtipo y fecha nulos: la celda existe vacía con el estilo de
    su columna en la plantilla (texto: el de F8/I8; fecha: el de J8)."""
    Catalogo(client).activo("Silla", precio="389900.00")
    hoja, esp = hoja_de(exportar_(client)), esperada()
    for col in "FGHIJ":
        ref = f"{col}{FILA_DATOS}"
        celda = hoja["celdas"][ref]
        assert (celda["tipo"], celda["valor"]) == ("vacia", None), ref
        assert u.comparar(esp["celdas"][ref]["estilo"], celda["estilo"], ref) == []
    # La plantilla no distingue un estilo «vacía» en texto: F8 (vacía) = A8 (con texto).
    assert u.comparar(esp["celdas"]["F8"]["estilo"], esp["celdas"]["A8"]["estilo"]) == []
    assert esp["celdas"]["J8"]["estilo"]["formato"]["incorporado"] == 14


class SinCatalogo:
    """Sesión sin catálogo: el generador no encuentra categoría ni ubicación."""

    def get(self, *_args):
        return None


def _activo(**cambios) -> SimpleNamespace:
    fila = {
        "codigo": "FIC-0001",
        "nombre": "Activo ficticio",
        "categoria_id": uuid.uuid4(),
        "ubicacion_id": uuid.uuid4(),
        "estado": "activo",
        "serial": None,
        "marca": None,
        "modelo": None,
        "subtipo": None,
        "fecha_compra": None,
        "precio_compra": Decimal("10.00"),
        "creado_en": datetime(2026, 1, 2, 15, 0, tzinfo=exportar.HORA_COLOMBIA),
    }
    return SimpleNamespace(**{**fila, **cambios})


EMPRESA_DIRECTA = SimpleNamespace(
    nombre="Clínica Ficticia", nit=None, telefono=None, correo=None, direccion=None, logo=None
)


def _directo(*activos) -> bytes:
    return exportar.a_excel(SinCatalogo(), list(activos), EMPRESA_DIRECTA, date(2026, 11, 22))


def test_precio_nulo_y_textos_vacios_quedan_como_celdas_vacias_con_su_estilo():
    """El precio es obligatorio en la base; si llegara nulo, la celda queda vacía con el
    formato COP de su columna (nunca 0 ni un número inventado). Texto vacío = vacía."""
    hoja = u.extraer(_directo(_activo(precio_compra=None, serial="", marca="  ")))["hojas"][HOJA]
    esp = esperada()
    for col in "FGHIJK":
        ref = f"{col}{FILA_DATOS}"
        assert hoja["celdas"][ref]["tipo"] == "vacia", ref
        assert u.comparar(esp["celdas"][ref]["estilo"], hoja["celdas"][ref]["estilo"], ref) == []
    # Sin categoría ni ubicación (no debería pasar): celdas vacías, con borde.
    for col in "CD":
        ref = f"{col}{FILA_DATOS}"
        assert hoja["celdas"][ref]["tipo"] == "vacia"
        assert u.comparar(esp["celdas"][ref]["estilo"], hoja["celdas"][ref]["estilo"], ref) == []


def test_el_precio_nunca_es_float():
    """Dinero exacto: el estilo común rechaza ``float`` (el modelo entrega ``Decimal``)."""
    with pytest.raises(TypeError):
        _directo(_activo(precio_compra=1390000.5))


def test_precio_decimal_se_escribe_exacto_desde_el_decimal():
    contenido = _directo(_activo(precio_compra=Decimal("167226590.70")))
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        hoja = z.read("xl/worksheets/sheet1.xml").decode()
    assert "<v>167226590.70</v>" in hoja


def test_sin_datos_de_empresa_va_el_nombre_del_tenant_y_la_fecha(client, exa_db):
    """Sin empresa guardada: el nombre del tenant (como ``GET /empresa``), la fecha de
    exportación y nada más; sin logo; la línea azul de la fila 5 sigue entera."""
    with exa_db.migrator.begin() as conn:
        tenant = conn.execute(
            text("select nombre from tenant where id = :t"), {"t": TENANT_A}
        ).scalar_one()
    antes = hoy()
    hoja = hoja_de(exportar_(client))
    fecha = fecha_exportada(hoja, antes, hoy())
    comprobar_bloque(hoja, textos_bloque(fecha, tenant))
    assert hoja["imagenes"] == []


@pytest.mark.parametrize(
    "ausentes", [("nit",), ("telefono",), ("correo",), ("nit", "telefono", "correo")]
)
def test_campos_opcionales_ausentes_se_omiten_con_su_rotulo(client, ausentes):
    datos = {k: v for k, v in EMPRESA.items() if k not in ausentes}
    con_empresa(client, datos)
    antes = hoy()
    hoja = hoja_de(exportar_(client))
    fecha = fecha_exportada(hoja, antes, hoy())
    comprobar_bloque(
        hoja,
        textos_bloque(
            fecha,
            datos["nombre"],
            NIT_NORMALIZADO if "nit" in datos else None,
            datos.get("telefono"),
            datos.get("correo"),
            datos["direccion"],
        ),
    )
    textos = [c["valor"] for c in hoja["celdas"].values() if c["tipo"] == "s"]
    if "nit" in ausentes:
        assert not any("NIT" in t for t in textos)
    if "telefono" in ausentes:
        assert not any("Tel." in t for t in textos)
    if {"correo", "telefono"} <= set(ausentes):
        assert "Contacto" not in textos


@pytest.mark.parametrize(("ancho", "alto"), [(600, 240), (200, 200), (600, 100)])
def test_el_logo_de_la_empresa_cabe_en_la_caja_con_su_proporcion(client, ancho, alto):
    con_empresa(client, logo=_png(ancho, alto))
    (imagen,) = hoja_de(exportar_(client))["imagenes"]
    comprobar_imagen(imagen, ancho, alto)


def _archivo_logo(almacen_dir, logo_id: str):
    return almacen_dir / str(TENANT_A) / f"{logo_id}.png"


def test_logo_que_no_esta_en_el_almacen_sale_sin_imagen(client, almacen_dir):
    logo_id = con_empresa(client, logo=_png())
    _archivo_logo(almacen_dir, logo_id).unlink()
    hoja = hoja_de(exportar_(client))
    assert hoja["imagenes"] == []
    assert empresa_en_linea(hoja) == EMPRESA["nombre"]


def test_logo_ilegible_sale_sin_imagen(client, almacen_dir):
    logo_id = con_empresa(client, logo=_png())
    _archivo_logo(almacen_dir, logo_id).write_bytes(b"esto no es una imagen")
    hoja = hoja_de(exportar_(client))
    assert hoja["imagenes"] == []
    assert empresa_en_linea(hoja) == EMPRESA["nombre"]


def test_sin_almacen_configurado_sale_sin_imagen(client, exa_app, monkeypatch):
    con_empresa(client, logo=_png())
    monkeypatch.setitem(exa_app.extensions, EXTENSION_KEY, None)
    hoja = hoja_de(exportar_(client))
    assert hoja["imagenes"] == []
    assert empresa_en_linea(hoja) == EMPRESA["nombre"]


class AlmacenQueFalla:
    """Almacén falso: ``leer`` lanza el error dado (S3 caído, sin permiso, disco roto)."""

    def __init__(self, error: BaseException) -> None:
        self.error = error
        self.lecturas = 0

    def guardar(self, *_args) -> None:
        raise AssertionError("no se escribe en el almacén al exportar")

    def leer(self, _clave: str) -> bytes:
        self.lecturas += 1
        raise self.error

    def borrar(self, *_args) -> None:
        raise AssertionError("no se borra del almacén al exportar")


ERRORES_DEL_ALMACEN = [
    pytest.param(OSError("disco no disponible"), id="oserror"),
    pytest.param(
        ClientError({"Error": {"Code": "AccessDenied", "Message": "denegado"}}, "GetObject"),
        id="clienterror",
    ),
    pytest.param(EndpointConnectionError(endpoint_url="https://almacen.invalido"), id="botocore"),
]


@pytest.mark.parametrize("error", ERRORES_DEL_ALMACEN)
def test_si_el_almacen_falla_el_excel_sale_completo_sin_imagen(
    client, exa_app, monkeypatch, caplog, error
):
    """Req. 8: el logo es decorativo; un fallo del almacén no tumba la exportación (ni
    ``500``): el Excel sale completo, sin imagen, y el registro no trae la clave."""
    logo_id = con_empresa(client, logo=_png())
    propio = Catalogo(client).activo("Autoclave", precio="1390000.50")
    almacen = AlmacenQueFalla(error)
    monkeypatch.setitem(exa_app.extensions, EXTENSION_KEY, almacen)
    with caplog.at_level(logging.DEBUG):
        response = exportar_(client)
    assert response.status_code == 200
    assert almacen.lecturas == 1
    hoja = hoja_de(response)
    assert hoja["imagenes"] == []
    assert empresa_en_linea(hoja) == EMPRESA["nombre"]
    assert [f[0] for f in filas(response)] == [propio["codigo"]]
    registros = " ".join(r.getMessage() for r in caplog.records)
    for dato in [logo_id, str(TENANT_A), "almacen.invalido", *EMPRESA.values()]:
        assert dato not in registros, dato


def test_fallo_de_s3_se_registra_como_warning_con_el_codigo_y_sin_datos(
    client, exa_app, monkeypatch, caplog
):
    """La degradación a «sin logo» deja un WARNING con el tipo y el código de S3 (un enum,
    sin datos); nunca la clave, el tenant, el endpoint, el bucket ni datos de la empresa."""
    logo_id = con_empresa(client, logo=_png())
    error = ClientError({"Error": {"Code": "AccessDenied", "Message": "denegado"}}, "GetObject")
    monkeypatch.setitem(exa_app.extensions, EXTENSION_KEY, AlmacenQueFalla(error))
    with caplog.at_level(logging.DEBUG, logger="app.activos.routes"):
        response = exportar_(client)
    assert response.status_code == 200
    avisos = [r for r in caplog.records if r.name == "app.activos.routes"]
    assert len(avisos) == 1
    assert avisos[0].levelno == logging.WARNING
    mensaje = avisos[0].getMessage()
    assert "ClientError" in mensaje
    assert "AccessDenied" in mensaje
    registros = " ".join(r.getMessage() for r in caplog.records)
    for dato in [logo_id, str(TENANT_A), "denegado", "GetObject", *EMPRESA.values()]:
        assert dato not in registros, dato


def test_correo_hostil_queda_como_texto_sin_formula_ni_hipervinculo(client):
    """Un correo que parece fórmula (lo admite la validación de empresa) sale como texto:
    celda ``s``, sin ``<f>`` ni ``<hyperlink>`` en la hoja."""
    hostil = "=1+1@a.co"
    con_empresa(client, {**EMPRESA, "correo": hostil})
    response = exportar_(client)
    celdas = hoja_de(response)["celdas"]
    # El correo es la primera línea del grupo «Contacto» (fila 5).
    con_correo = [c for c in celdas.values() if (c["valor"] or "").split("\n")[0] == hostil]
    assert len(con_correo) == 1
    assert con_correo[0]["tipo"] == "s"
    with zipfile.ZipFile(io.BytesIO(response.data)) as z:
        hojas = "".join(z.read(n).decode() for n in z.namelist() if n.startswith("xl/worksheets/"))
    assert "<f>" not in hojas
    assert "<f " not in hojas
    assert "<hyperlink" not in hojas


def test_el_contador_sigue_con_403_aunque_el_almacen_falle(client, exa_app, monkeypatch):
    con_empresa(client, logo=_png())
    almacen = AlmacenQueFalla(OSError("disco no disponible"))
    monkeypatch.setitem(exa_app.extensions, EXTENSION_KEY, almacen)
    prohibido = exportar_(client, CONTADOR)
    assert prohibido.status_code == 403
    assert almacen.lecturas == 0


def test_con_mas_filas_que_el_tope_no_se_lee_el_logo(client, exa_app, monkeypatch):
    """El ``413`` sale antes de leer la empresa: el almacén no se toca."""
    con_empresa(client, logo=_png())
    c = Catalogo(client)
    c.activo("Archivador 1")
    c.activo("Archivador 2")
    almacen = AlmacenQueFalla(AssertionError("no se debe leer el logo en un 413"))
    monkeypatch.setitem(exa_app.extensions, EXTENSION_KEY, almacen)
    monkeypatch.setattr(service, "MAX_FILAS_EXPORTACION", 1)
    response = exportar_(client)
    assert response.status_code == 413
    assert response.get_json()["error"]["code"] == "exportacion_demasiado_grande"
    assert almacen.lecturas == 0


def _todo_el_xml(contenido: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        return "".join(z.read(n).decode() for n in z.namelist() if n.endswith((".xml", ".rels")))


def test_la_empresa_y_el_logo_de_otro_tenant_no_aparecen(client):
    con_empresa(client, EMPRESA_AJENA, logo=_png(120, 100, (200, 30, 30)), headers=ADMIN_OTRO)
    Catalogo(client, ADMIN_OTRO).activo("Autoclave ajeno")
    propio = Catalogo(client).activo("Autoclave propio")

    # Tenant A sin empresa guardada: ni los datos ni el logo del otro tenant.
    response = exportar_(client)
    xml = _todo_el_xml(response.data)
    for dato in TEXTOS_AJENOS:
        assert dato not in xml, dato
    assert hoja_de(response)["imagenes"] == []
    assert [f[0] for f in filas(response)] == [propio["codigo"]]

    # Con su propia empresa y logo: los suyos, nunca los del otro.
    con_empresa(client, logo=_png(600, 240))
    response = exportar_(client)
    xml = _todo_el_xml(response.data)
    for dato in TEXTOS_AJENOS:
        assert dato not in xml, dato
    (imagen,) = hoja_de(response)["imagenes"]
    tamano = (imagen["imagen"]["ancho"], imagen["imagen"]["alto"])
    assert tamano == est.componer_logo(_png(600, 240))[1:]  # su logo, con su borde

    # Y el otro tenant ve lo suyo, sin lo de A.
    otro = exportar_(client, ADMIN_OTRO)
    hoja_otro = hoja_de(otro)
    assert empresa_en_linea(hoja_otro) == EMPRESA_AJENA["nombre"]
    (imagen_otro,) = hoja_otro["imagenes"]
    tamano_otro = (imagen_otro["imagen"]["ancho"], imagen_otro["imagen"]["alto"])
    assert tamano_otro == est.componer_logo(_png(120, 100))[1:] != tamano
    xml_otro = _todo_el_xml(otro.data)
    for dato in [*EMPRESA.values(), NIT_NORMALIZADO, propio["codigo"]]:
        assert dato not in xml_otro, dato


def test_el_contador_recibe_403_sin_datos_de_la_empresa(client):
    con_empresa(client, logo=_png())
    Catalogo(client).activo("Autoclave", precio="1390000.50")
    prohibido = exportar_(client, CONTADOR)
    assert prohibido.status_code == 403
    assert prohibido.mimetype == "application/json"
    assert prohibido.get_json()["error"]["code"] == "prohibido"
    cuerpo = prohibido.get_data(as_text=True)
    for dato in [*EMPRESA.values(), NIT_NORMALIZADO, "1390000"]:
        assert dato not in cuerpo, dato


@pytest.mark.parametrize(
    "hostil", ['=HYPERLINK("http://evil","x")', '&A&P&"Arial,Bold"&K FF0000&Z', "@SUMA(A1)"]
)
def test_los_datos_de_la_empresa_que_parecen_formulas_quedan_como_texto(client, hostil):
    con_empresa(client, {"nombre": hostil, "direccion": hostil, "correo": "a@b.test"})
    response = exportar_(client)
    hoja = hoja_de(response)
    assert empresa_en_linea(hoja) == hostil
    assert (hoja["celdas"]["C5"]["tipo"], hoja["celdas"]["C5"]["valor"]) == ("s", hostil)
    xml = _todo_el_xml(response.data)
    assert "<f>" not in xml and "<f " not in xml
    assert "<hyperlink" not in xml and "relationships/hyperlink" not in xml
    # El texto de la empresa no entra en el encabezado ni en el pie de impresión.
    assert hoja["pagina"]["encabezado_pie"] == {"oddFooter": est.PIE}


def test_dos_exportaciones_seguidas_tienen_el_mismo_formato(client):
    """Estabilidad: mismo contenido y mismo formato (solo cambian las horas del paquete)."""
    con_empresa(client, logo=_png())
    c = Catalogo(client)
    c.activo("Autoclave", precio="1390000.50", serial="SN-1", fecha_compra="2024-01-31")
    c.activo("Silla", precio="389900.00", categoria=c.mob)
    primera, segunda = exportar_(client), exportar_(client)
    a, b = diseno(primera), diseno(segunda)
    for d in (a, b):
        for k in ("created", "modified"):
            d["libro"]["propiedades"]["core"].pop(k)
    if a["hojas"][HOJA]["celdas"]["C3"] != b["hojas"][HOJA]["celdas"]["C3"]:
        pytest.skip("las dos exportaciones cruzaron la medianoche")
    assert u.comparar(a, b) == []
    with (
        zipfile.ZipFile(io.BytesIO(primera.data)) as z1,
        zipfile.ZipFile(io.BytesIO(segunda.data)) as z2,
    ):
        assert z1.namelist() == z2.namelist()
        for n in z1.namelist():
            if n != "docProps/core.xml":
                assert z1.read(n) == z2.read(n), n


def test_la_exportacion_no_registra_datos_de_la_empresa(client, caplog):
    con_empresa(client, logo=_png())
    Catalogo(client).activo("Autoclave")
    with caplog.at_level(logging.DEBUG):
        assert exportar_(client).status_code == 200
    registros = " ".join(r.getMessage() for r in caplog.records)
    for dato in [*EMPRESA.values(), NIT_NORMALIZADO]:
        assert dato not in registros, dato
