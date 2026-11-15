"""Documento intermedio de la exportación (spec 009, T1; R1–R3).

El Excel y el PDF salen de un mismo documento construido desde el dict de
``cierre.informe``: aquí no se suma nada. El formato COP y el porcentaje son los
mismos de la web (``web/src/lib/format.ts`` y ``porcentaje`` de ``lib/sesiones.ts``).
"""

from decimal import Decimal

import pytest

from app.conteo import exportar


@pytest.mark.parametrize(
    ("entrada", "salida"),
    [
        ("0", "$ 0,00"),
        ("0.5", "$ 0,50"),
        ("389900.00", "$ 389.900,00"),
        ("1234567.8", "$ 1.234.567,80"),
        ("276850300.00", "$ 276.850.300,00"),
        ("999999999999.99", "$ 999.999.999.999,99"),
        ("-1500", "-$ 1.500,00"),
    ],
)
def test_cop_format_matches_the_web(entrada, salida):
    assert exportar.formato_cop(Decimal(entrada)) == salida


def test_cop_format_rejects_more_than_two_decimals():
    with pytest.raises(ValueError):
        exportar.formato_cop(Decimal("1.005"))


@pytest.mark.parametrize(
    ("encontradas", "registradas", "salida"),
    [
        (0, 0, "0 %"),
        (1, 2, "50 %"),
        (1, 3, "33,3 %"),
        (2, 3, "66,7 %"),
        (3, 3, "100 %"),
        (1, 8, "12,5 %"),
    ],
)
def test_percentage_matches_the_web(encontradas, registradas, salida):
    assert exportar.porcentaje(encontradas, registradas) == salida


INFORME = {
    "sesion": {
        "id": "00000000-0000-4000-8000-0000000000e1",
        "nombre": "Conteo nov 2026",
        "tipo": "conteo",
        "estado": "cerrada",
        "fecha_corte": "2026-11-30",
        "abierta_por": {"id": "00000000-0000-4000-8000-00000000000a", "nombre": "Ana Torres"},
        "abierta_en": "2026-11-14T13:00:00+00:00",
        "cerrada_por": {"id": "00000000-0000-4000-8000-00000000000a", "nombre": "Ana Torres"},
        "cerrada_en": "2026-11-14T22:58:00+00:00",
    },
    "totales": {
        "encontrado": "1390000.50",
        "no_encontrado": "389900.00",
        "registrado": "1779900.50",
        "unidades_encontrado": 1,
        "unidades_no_encontrado": 1,
        "unidades_registrado": 2,
    },
    "desglose": {
        "categorias": [
            {
                "id": "00000000-0000-4000-8000-0000000000c1",
                "etiqueta": "Electrónica",
                "total_encontrado": "1390000.50",
                "total_no_encontrado": "0.00",
                "total_registrado": "1390000.50",
                "unidades_encontrado": 1,
                "unidades_no_encontrado": 0,
                "unidades_registrado": 1,
            },
            {
                "id": "00000000-0000-4000-8000-0000000000c2",
                "etiqueta": "Mobiliario",
                "total_encontrado": "0.00",
                "total_no_encontrado": "389900.00",
                "total_registrado": "389900.00",
                "unidades_encontrado": 0,
                "unidades_no_encontrado": 1,
                "unidades_registrado": 1,
            },
        ],
        "ubicaciones": [
            {
                "id": "00000000-0000-4000-8000-0000000000a2",
                "etiqueta": "Consultorio 1 › Box 2",
                "total_encontrado": "1390000.50",
                "total_no_encontrado": "389900.00",
                "total_registrado": "1779900.50",
                "unidades_encontrado": 1,
                "unidades_no_encontrado": 1,
                "unidades_registrado": 2,
            }
        ],
    },
    "no_encontrados": [
        {
            "activo_id": "00000000-0000-4000-8000-0000000000d2",
            "codigo": "000123",
            "nombre": "Silla ergonómica",
            "categoria": {"id": "00000000-0000-4000-8000-0000000000c2", "nombre": "Mobiliario"},
            "ubicacion": {
                "id": "00000000-0000-4000-8000-0000000000a2",
                "ruta": "Consultorio 1 › Box 2",
            },
            "precio": "389900.00",
            "en_reparacion": True,
        }
    ],
}


def test_document_reads_every_figure_from_the_report_without_summing():
    doc = exportar.documento(INFORME)
    assert doc.sesion == "Conteo nov 2026"
    assert doc.corte == "30/11/2026"
    assert doc.cerrada_por == "Ana Torres"
    # 22:58 UTC = 5:58 p. m. en Colombia (UTC−5, sin horario de verano).
    assert doc.cerrada_en == "14/11/2026, 5:58 p. m."
    assert doc.totales.encontrado == exportar.Cifra(Decimal("1390000.50"), 1)
    assert doc.totales.no_encontrado == exportar.Cifra(Decimal("389900.00"), 1)
    assert doc.totales.registrado == exportar.Cifra(Decimal("1779900.50"), 2)
    assert doc.totales.porcentaje == "50 %"
    assert [f.etiqueta for f in doc.por_categoria] == ["Electrónica", "Mobiliario"]
    assert doc.por_categoria[1].no_encontrado == exportar.Cifra(Decimal("389900.00"), 1)
    assert doc.por_categoria[1].porcentaje == "0 %"
    assert doc.por_ubicacion[0].etiqueta == "Consultorio 1 › Box 2"
    (silla,) = doc.no_encontrados
    assert (silla.codigo, silla.nombre, silla.categoria, silla.ubicacion) == (
        "000123",
        "Silla ergonómica",
        "Mobiliario",
        "Consultorio 1 › Box 2",
    )
    assert silla.precio == Decimal("389900.00")
    assert silla.en_reparacion is True
    assert all(
        isinstance(c.valor, Decimal) for c in (doc.totales.encontrado, doc.totales.no_encontrado)
    )


def test_document_of_an_empty_session_is_all_zeros():
    vacio = {
        **INFORME,
        "totales": {
            "encontrado": "0.00",
            "no_encontrado": "0.00",
            "registrado": "0.00",
            "unidades_encontrado": 0,
            "unidades_no_encontrado": 0,
            "unidades_registrado": 0,
        },
        "desglose": {"categorias": [], "ubicaciones": []},
        "no_encontrados": [],
    }
    doc = exportar.documento(vacio)
    assert doc.totales.registrado == exportar.Cifra(Decimal("0.00"), 0)
    assert doc.totales.porcentaje == "0 %"
    assert doc.por_categoria == doc.por_ubicacion == doc.no_encontrados == ()


@pytest.mark.parametrize(
    ("nombre", "corte", "archivo"),
    [
        ("Conteo nov 2026", "2026-11-30", "informe-conteo-nov-2026-corte-2026-11-30"),
        ("Conteo «Sede» / Año 2026", "2026-12-01", "informe-conteo-sede-ano-2026-corte-2026-12-01"),
        ("###", "2026-12-01", "informe-corte-2026-12-01"),
    ],
)
def test_file_name_is_ascii_and_safe(nombre, corte, archivo):
    assert exportar.nombre_base(nombre, corte) == archivo
