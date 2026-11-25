"""Módulo de estilo común de los Excel (spec 019, T2): bloque de encabezado y formatos.

Cada prueba genera un ``.xlsx`` con ``app.conteo.exportar_estilo`` y una empresa FICTICIA,
lo lee con la utilidad de diseño (ZIP + XML) y lo compara contra la huella versionada
(``tests/plantillas/*.json``), propiedad por propiedad (FT-1 a FT-3). Los valores esperados
salen de la huella; el módulo de la aplicación tiene sus propias constantes.

Alcance de T2: banda (fila 1), bloque de empresa con logo (filas 2–5) y campos ausentes
(Q9), cabecera de tabla, fila de datos, fila Total, catálogo de formatos, anchos, alturas,
pie, márgenes, página, pestaña, cuadrícula, congelado, área de impresión y filas a repetir,
logo proporcional dentro de la caja (Q10), propiedades del documento (fila 26). Lo que es de
T3–T5 (título y nota de lista, formato condicional por hoja, barras de datos, tarjetas del
Resumen, filtros y tabla) no se compara aquí, salvo sus formatos dentro del catálogo.
"""

from __future__ import annotations

import copy
import io
import json
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
import utils_xlsx_diseno as u
import xlsxwriter
from PIL import Image

from app.conteo import exportar_estilo as est

HUELLAS = {k: u.cargar_huella(k) for k in u.PLANTILLAS}

# Plantilla del módulo → (huella, hoja de la huella, nombre de la hoja generada).
HOJAS = {
    "activos": ("activos", "Activos", "Activos"),
    "todos": ("informe", "Todos los activos", "Todos los activos"),
    "por_ubicacion": ("informe", "Por ubicación", "Por ubicación"),
    "no_encontrados": ("informe", "No encontrados", "No encontrados"),
    "categoria": ("informe", u.MARCA_CATEGORIA, "Equipos de prueba"),
    "por_categoria": ("informe", "Por categoría", "Por categoría"),
    "resumen": ("informe", "Resumen", "Resumen"),
}
LISTAS = {"todos", "no_encontrados", "categoria"}  # Q12: 1 página de ancho × alto automático


class EmpresaFicticia:
    """Datos sintéticos: nada de la clínica (R8)."""

    def __init__(self, **kw: Any) -> None:
        self.nombre = kw.get("nombre", "Clínica Ficticia de Prueba S.A.S.")
        self.nit = kw.get("nit", "900000000-0")
        self.telefono = kw.get("telefono", "600 000 0000")
        self.correo = kw.get("correo", "contacto@ejemplo.test")
        self.direccion = kw.get("direccion", "Calle Falsa 00 # 00-00")
        self.logo = kw.get("logo")


FECHA = date(2026, 11, 22)
EMU = u.EMU_POR_PX


def _png(ancho: int = 600, alto: int = 240, dpi: int | None = None) -> bytes:
    b = io.BytesIO()
    opciones = {"dpi": (dpi, dpi)} if dpi else {}
    Image.new("RGB", (ancho, alto), (29, 78, 216)).save(b, format="PNG", **opciones)
    return b.getvalue()


def _esperada(clave: str) -> dict[str, Any]:
    """Copia de la hoja de la huella (las pruebas no deben alterar la compartida)."""
    huella, hoja, _ = HOJAS[clave]
    return copy.deepcopy(HUELLAS[huella]["hojas"][hoja])


def _fila(ref: str) -> int:
    return u.ref_a_rc(ref)[0]


def _ultima_fila_plantilla(clave: str) -> int:
    """Última fila (0-based) del área de impresión de la plantilla."""
    area = _esperada(clave)["impresion"]["area"].split("!")[1].replace("$", "")
    return _fila(area.split(":")[1]) - 1


def _texto_esperado(valor: Any, empresa: EmpresaFicticia, plantilla: est.Plantilla) -> Any:
    """El valor de la huella con los marcadores sustituidos por los datos ficticios.

    Un dato ausente se omite (Q9): en la línea «Informe · …» y en cada línea de un grupo
    (Empresa, Contacto, Dirección); un grupo sin datos queda vacío y sin su rótulo."""
    if not isinstance(valor, str):
        return valor
    if valor.startswith("Informe · "):  # línea junto al logo
        partes = ["Informe", empresa.nombre, f"{plantilla.rotulo_fecha.lower()} 22/11/2026"]
        return " · ".join(p for p in partes if p)
    lineas = {
        "{empresa.nombre}": empresa.nombre or None,
        "NIT {empresa.nit}": f"NIT {empresa.nit}" if empresa.nit else None,
        "Tel. {empresa.telefono}": f"Tel. {empresa.telefono}" if empresa.telefono else None,
        "{empresa.correo}": empresa.correo or None,
        "{empresa.direccion}": empresa.direccion or None,
    }
    grupos = {"Empresa": "{empresa.nombre}\nNIT {empresa.nit}"}
    grupos["Contacto"] = "{empresa.correo}\nTel. {empresa.telefono}"
    grupos["Dirección"] = "{empresa.direccion}"
    if valor in grupos:  # rótulo: solo si su grupo tiene algún dato
        return valor if _texto_esperado(grupos[valor], empresa, plantilla) else None
    if valor.split("\n")[0] in lineas:
        presentes = [lineas[linea] for linea in valor.split("\n")]
        return "\n".join(p for p in presentes if p) or None
    return valor.replace("{fecha}", "22/11/2026")


def _libro(construir) -> dict[str, Any]:
    salida = io.BytesIO()
    wb = xlsxwriter.Workbook(
        salida, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False}
    )
    construir(wb)
    wb.close()
    return u.extraer(salida.getvalue())


def _generar(clave: str, empresa: EmpresaFicticia, cuerpo=None) -> dict[str, Any]:
    plantilla = est.PLANTILLAS[clave]
    nombre = HOJAS[clave][2]

    def construir(wb):
        hoja = wb.add_worksheet(nombre)
        estilos = est.Estilos(wb)
        est.preparar_hoja(hoja, plantilla, _ultima_fila_plantilla(clave))
        est.dibujar_bloque(hoja, estilos, plantilla, empresa, FECHA)
        if cuerpo:
            cuerpo(hoja, estilos, plantilla)

    return _libro(construir)["hojas"][nombre]


def _bloque(celdas: dict[str, Any]) -> dict[str, Any]:
    return {ref: c for ref, c in celdas.items() if _fila(ref) <= 5}


CLAVES = list(HOJAS)


# ---------------------------------------------------------------------------
# Bloque común (filas 1–5): banda, título, empresa, fecha, contacto, dirección
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("clave", CLAVES)
def test_bloque_celdas_valores_y_estilos(clave):
    empresa = EmpresaFicticia(logo=_png())
    plantilla = est.PLANTILLAS[clave]
    gen = _bloque(_generar(clave, empresa)["celdas"])
    esperado = _bloque(_esperada(clave)["celdas"])
    for celda in esperado.values():
        celda["valor"] = _texto_esperado(celda["valor"], empresa, plantilla)
    assert sorted(gen) == sorted(esperado)
    assert u.comparar(esperado, gen, clave) == []


@pytest.mark.parametrize("clave", CLAVES)
def test_bloque_alturas_combinadas_pestana_y_vista(clave):
    gen = _generar(clave, EmpresaFicticia())
    esp = _esperada(clave)
    altos = {n: f for n, f in esp["filas"].items() if int(n) <= 5}
    assert u.comparar(altos, {n: f for n, f in gen["filas"].items() if int(n) <= 5}) == []
    assert gen["combinadas"] == [m for m in esp["combinadas"] if _fila(m.split(":")[0]) <= 5]
    assert u.comparar(esp["pestana"], gen["pestana"]) == []
    v, g = esp["vista"], gen["vista"]
    # Q11: la selección, la hoja activa y el desplazamiento de la plantilla no se reproducen.
    for k in ("cuadricula", "encabezados", "ceros", "derecha_a_izquierda", "zoom", "tipo"):
        assert g[k] == v[k], k
    assert u.comparar(v["panel"], g["panel"], "panel") == []
    assert g["celda_superior_izquierda"] is None


@pytest.mark.parametrize("clave", CLAVES)
def test_anchos_de_columna_y_ocultas(clave):
    gen = _generar(clave, EmpresaFicticia())
    esp = _esperada(clave)

    def sin_estilo(cols):
        return [{k: v for k, v in c.items() if k != "estilo"} for c in cols]

    assert u.comparar(sin_estilo(esp["columnas"]), sin_estilo(gen["columnas"])) == []
    # El estilo de columna de la plantilla resuelve al estilo por defecto (L7).
    defecto = HUELLAS[HOJAS[clave][0]]["libro"]["estilo_defecto"]
    assert all(c["estilo"] in (None, defecto) for c in esp["columnas"])
    assert all(c["estilo"] is None for c in gen["columnas"])


@pytest.mark.parametrize("clave", CLAVES)
def test_pagina_margenes_pie_e_impresion(clave):
    gen = _generar(clave, EmpresaFicticia())
    esp = _esperada(clave)
    pagina = dict(esp["pagina"])
    if clave in LISTAS:
        # Q12 (humano 2026-11-22): listas a 1 página de ancho × alto automático.
        assert pagina["ajuste_alto"] == 1
        pagina["ajuste_alto"] = 0
    assert u.comparar(pagina, gen["pagina"], f"{clave}.pagina") == []
    assert gen["pagina"]["papel"] is None  # L3: papel sin declarar
    assert gen["pagina"]["encabezado_pie"] == {"oddFooter": est.PIE}

    def rango(valor):
        return valor.split("!", 1)[1] if valor else None

    for k in ("area", "titulos"):
        assert rango(gen["impresion"][k]) == rango(esp["impresion"][k]), k


def test_area_de_impresion_se_extiende_hasta_la_ultima_fila():
    def construir(wb):
        hoja = wb.add_worksheet("Activos")
        est.preparar_hoja(hoja, est.PLANTILLAS["activos"], 499)

    imp = _libro(construir)["hojas"]["Activos"]["impresion"]
    assert imp["area"] == "Activos!$A$1:$L$500"
    assert imp["titulos"] == "Activos!$7:$7"


# ---------------------------------------------------------------------------
# Campos ausentes (Q9): se omite el texto (y el rótulo «Correo»); el estilo se conserva
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("clave", CLAVES)
def test_campos_ausentes_se_omiten_con_su_rotulo(clave):
    empresa = EmpresaFicticia(nit=None, telefono="", correo=None, direccion=None, logo=None)
    gen_hoja = _generar(clave, empresa)
    gen = _bloque(gen_hoja["celdas"])
    esp = _bloque(_esperada(clave)["celdas"])
    plantilla = est.PLANTILLAS[clave]
    assert sorted(gen) == sorted(esp)  # mismas celdas: el estilo (bordes) no se pierde
    for ref, celda in esp.items():
        assert u.comparar(celda["estilo"], gen[ref]["estilo"], ref) == []
        esperado = _texto_esperado(celda["valor"], empresa, plantilla)
        if esperado is None:
            assert gen[ref]["tipo"] == "vacia", (ref, gen[ref])
        else:
            assert (gen[ref]["tipo"], gen[ref]["valor"]) == ("s", esperado), ref
    textos = [c["valor"] for c in gen.values() if c["tipo"] == "s"]
    # Solo queda el nombre en «Empresa»; «Contacto» y «Dirección» quedan sin rótulo.
    assert empresa.nombre in textos and "Empresa" in textos
    assert "Contacto" not in textos and "Dirección" not in textos
    assert not any("NIT" in t or "Tel." in t for t in textos)
    assert gen_hoja["imagenes"] == []


def test_sin_nombre_de_empresa_la_celda_queda_vacia():
    gen = _bloque(_generar("activos", EmpresaFicticia(nombre=None))["celdas"])
    assert gen["C3"]["valor"] == "Informe · exportado 22/11/2026"


# ---------------------------------------------------------------------------
# Logo (Q10, Q13, L8): dentro de la caja de la hoja, con su proporción y EMU exactos
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("clave", CLAVES)
@pytest.mark.parametrize(("ancho", "alto", "dpi"), [(600, 240, None), (200, 200, None)])
def test_logo_en_la_caja_de_la_hoja(clave, ancho, alto, dpi):
    (esp,) = _esperada(clave)["imagenes"]
    (img,) = _generar(clave, EmpresaFicticia(logo=_png(ancho, alto, dpi)))["imagenes"]
    caja = esp["ext"]
    # Equivalente aprobado (Q13): twoCellAnchor que se mueve pero no cambia de tamaño.
    assert (img["ancla"], img["edit_as"]) == ("twoCellAnchor", "oneCell")
    assert u.comparar(esp["desde"], img["desde"], "desde") == []
    assert (img["xfrm"]["x"], img["xfrm"]["y"]) == (esp["xfrm"]["x"], esp["xfrm"]["y"])
    cx, cy = img["xfrm"]["cx"], img["xfrm"]["cy"]
    # Una dimensión llena la caja exacta (EMU) y la otra cabe dentro.
    assert (cx == caja["cx"] and cy <= caja["cy"]) or (cy == caja["cy"] and cx <= caja["cx"])
    # Proporción del logo conservada (redondeo de 1 EMU en la dimensión derivada).
    assert abs(cx * alto - cy * ancho) <= max(ancho, alto)
    assert img["descr"] == esp["descr"] == est.TEXTO_ALTERNATIVO_LOGO
    for k in ("titulo", "oculta", "decorativa", "estirar", "geometria"):
        assert img[k] == esp[k], k
    assert (img["imagen"]["ancho"], img["imagen"]["alto"]) == (ancho, alto)


def test_logo_con_dpi_distinto_de_96_sigue_exacto():
    """xlsxwriter escala por 96/dpi: el ajuste lo tiene en cuenta (sin pHYs = 96)."""
    caja = est.PLANTILLAS["activos"].caja_logo
    (img,) = _generar("activos", EmpresaFicticia(logo=_png(600, 240, 192)))["imagenes"]
    assert img["imagen"]["phys"] is not None
    # 600 × 240 a 192 dpi = 300 × 120 px efectivos: manda el alto (116/120 < 297/300).
    assert img["xfrm"]["cy"] == caja.cy
    assert img["xfrm"]["cx"] == round(300 * EMU * caja.cy / (120 * EMU)) == 2762250


@pytest.mark.parametrize(
    ("ancho", "alto", "esperado"),
    [
        (1000, 100, (2828926, 282893)),  # ancho manda
        (100, 1000, (110490, 1104900)),  # alto manda
        (297, 116, (2828925, 1104900)),  # casi la caja: manda el alto, el ancho redondea
    ],
)
def test_ajustar_logo(ancho, alto, esperado):
    caja = est.PLANTILLAS["activos"].caja_logo
    assert (caja.cx, caja.cy) == (2828926, 1104900)
    ajuste = est.ajustar_logo(ancho, alto, 96, 96, caja)
    assert (ajuste.cx, ajuste.cy) == esperado
    # Lo que xlsxwriter escribirá: int(0.5 + px × escala × 9525).
    assert int(0.5 + ancho * ajuste.x_scale * 9525) == ajuste.cx
    assert int(0.5 + alto * ajuste.y_scale * 9525) == ajuste.cy


@pytest.mark.parametrize("logo", [None, b"", b"esto no es una imagen", _png()[:30]])
def test_logo_ausente_o_ilegible_genera_sin_imagen(logo):
    hoja = _generar("todos", EmpresaFicticia(logo=logo))
    assert hoja["imagenes"] == []
    assert hoja["formas"] == []  # sin logo no hay marco


@pytest.mark.parametrize("clave", CLAVES)
@pytest.mark.parametrize(("ancho", "alto"), [(600, 240), (200, 200), (1000, 100)])
def test_el_logo_lleva_un_marco_gris_ajustado_a_la_imagen(clave, ancho, alto):
    """Decisión del humano 2026-11-24: marco gris fino a 3 px de la imagen, sin relleno ni
    texto, debajo del logo; no cambia el tamaño ni la posición del logo y no pasa a C."""
    hoja = _generar(clave, EmpresaFicticia(logo=_png(ancho, alto)))
    (img,) = hoja["imagenes"]
    (marco,) = hoja["formas"]
    m = est.MARGEN_MARCO_PX * EMU
    i, f = img["xfrm"], marco["xfrm"]
    assert abs(f["x"] - (i["x"] - m)) <= 1 and abs(f["y"] - (i["y"] - m)) <= 1
    assert abs(f["cx"] - (i["cx"] + 2 * m)) <= 1 and abs(f["cy"] - (i["cy"] + 2 * m)) <= 1
    assert marco["linea"] == {"ancho": round(est.ANCHO_LINEA_MARCO * 12700), "color": "D1D5DB"}
    assert (marco["geometria"], marco["sin_relleno"], marco["texto"]) == ("rect", True, "")
    assert marco["decorativa"] is True
    assert marco["edit_as"] == img["edit_as"] == "oneCell"  # se mueve con el logo
    hasta = marco["hasta"]
    assert hasta["col"] < 2 or (hasta["col"], hasta["col_off"]) == (2, 0), hasta


# ---------------------------------------------------------------------------
# Cabecera de tabla, fila de datos y fila Total (filas de la plantilla)
# ---------------------------------------------------------------------------


def _valor_de_prueba(celda: dict[str, Any]) -> Any:
    """Un valor sintético del mismo tipo que la celda de la huella."""
    if celda["tipo"] == "vacia":
        return None
    if celda["tipo"] == "fecha":
        return FECHA
    if celda["tipo"] == "n":
        return Decimal("1234.56")
    valor = celda["valor"]
    return "dato de prueba" if valor == "{texto}" else valor.replace("{n}", "3")


def _filas_de_tabla(plantilla: est.Plantilla) -> list[tuple[int, str]]:
    filas = []
    if plantilla.estilos_cabecera:
        filas.append((plantilla.fila_cabecera, "cabecera"))
    if plantilla.estilos_datos:
        filas.append((plantilla.fila_datos, "datos"))
    if plantilla.estilos_total:
        total = plantilla.fila_total
        filas.append((plantilla.fila_datos + 1 if total is None else total, "total"))
    return filas


CON_TABLA = [c for c in CLAVES if est.PLANTILLAS[c].estilos_cabecera]


@pytest.mark.parametrize("clave", CON_TABLA)
def test_cabecera_datos_y_total(clave):
    plantilla = est.PLANTILLAS[clave]
    esp = _esperada(clave)
    filas = _filas_de_tabla(plantilla)
    if clave == "no_encontrados":
        # Sin fila de datos medida: sus estilos son los de las otras listas (decisión del
        # humano, T4); se prueban en ``test_no_encontrados_usa_los_estilos_…`` y en T4.
        filas = [f for f in filas if f[1] != "datos"]
    assert filas, clave

    def cuerpo(hoja, estilos, p):
        for fila, tipo in filas:
            nombres = {
                "cabecera": p.estilos_cabecera,
                "datos": p.estilos_datos,
                "total": p.estilos_total,
            }[tipo]
            celdas = []
            for col, nombre in enumerate(nombres):
                ref = f"{u.col_letra(col + 1)}{fila + 1}"
                valor = _valor_de_prueba(esp["celdas"][ref]) if ref in esp["celdas"] else None
                if tipo == "datos" and valor is None:
                    nombre = p.estilo_vacia
                celdas.append((valor, nombre))
            alto = {"datos": p.alto_datos, "total": p.alto_total}.get(tipo)
            est.escribir_fila(hoja, estilos, fila, celdas, alto)

    gen = _generar(clave, EmpresaFicticia(), cuerpo)
    for fila, tipo in filas:
        numero = str(fila + 1)
        esperadas = {r: c for r, c in esp["celdas"].items() if _fila(r) == fila + 1}
        generadas = {r: c for r, c in gen["celdas"].items() if _fila(r) == fila + 1}
        assert sorted(generadas) == sorted(esperadas), (tipo, numero)
        for ref, celda in esperadas.items():
            g = generadas[ref]
            assert g["tipo"] == celda["tipo"], ref
            assert u.comparar(celda["estilo"], g["estilo"], f"{clave}!{ref}") == []
            if celda["tipo"] == "s" and "{" not in celda["valor"]:
                assert g["valor"] == celda["valor"], ref  # rótulos fijos literales
        assert u.comparar(esp["filas"][numero], gen["filas"][numero], f"fila {numero}") == []


@pytest.mark.parametrize("clave", CLAVES)
def test_alturas_fijas_del_cuerpo(clave):
    """Alturas de las filas fijas bajo el bloque (sin la lista omitida del Resumen, Q7)."""
    plantilla = est.PLANTILLAS[clave]
    esp = _esperada(clave)
    gen = _generar(clave, EmpresaFicticia())
    for fila, alto in plantilla.altos.items():
        numero = str(fila + 1)
        assert u.comparar(esp["filas"][numero], gen["filas"][numero], numero) == []
        assert gen["filas"][numero]["alto"] == alto
    tabla = {f for f, _ in _filas_de_tabla(plantilla)}
    resto = {
        int(n) - 1 for n in esp["filas"] if int(n) > 5 and not (clave == "resumen" and int(n) >= 9)
    }
    # Toda fila con altura de la plantilla es fija o de tabla (datos repetidos: alto_datos).
    sin_cubrir = resto - set(plantilla.altos) - tabla
    for fila in sin_cubrir:
        assert esp["filas"][str(fila + 1)]["alto"] == plantilla.alto_datos, fila


def test_no_encontrados_usa_los_estilos_de_datos_de_las_otras_listas():
    """La plantilla «No encontrados» no trae fila de datos con estilo. Decisión del humano
    2026-11-22 (T4): sus filas llevan los estilos de datos de las otras listas (texto y COP de
    «Todos los activos»; la celda vacía, ``datos_vacia``), sin filas alternas."""
    esp = _esperada("no_encontrados")
    assert not [r for r in esp["celdas"] if _fila(r) >= 10]
    plantilla = est.PLANTILLAS["no_encontrados"]
    assert plantilla.estilos_datos == ("datos",) * 5 + ("datos_cop",)
    assert plantilla.estilo_vacia == est.PLANTILLAS["todos"].estilo_vacia == "datos_vacia"
    todos = est.PLANTILLAS["todos"].estilos_datos
    assert plantilla.estilos_datos == todos[:5] + todos[-1:]
    # Alto de datos: el de las filas 10–11 de la plantilla (con altura y sin celdas).
    assert {esp["filas"][n]["alto"] for n in ("10", "11")} == {plantilla.alto_datos}


# ---------------------------------------------------------------------------
# Catálogo de formatos: cada estilo medido tiene su formato, y ninguno sobra
# ---------------------------------------------------------------------------


def _clave_estilo(estilo: dict[str, Any]) -> str:
    return json.dumps(u._normalizar(estilo), sort_keys=True)


def _estilos_medidos() -> dict[str, str]:
    medidos: dict[str, str] = {}
    for huella, h in HUELLAS.items():
        for nombre, hoja in h["hojas"].items():
            for ref, c in hoja["celdas"].items():
                medidos.setdefault(_clave_estilo(c["estilo"]), f"{huella}/{nombre}!{ref}")
            for n, f in hoja["filas"].items():
                if f["estilo"]:
                    medidos.setdefault(_clave_estilo(f["estilo"]), f"{nombre}!fila {n}")
    return medidos


def test_catalogo_de_formatos_cubre_exactamente_lo_medido():
    nombres = list(est.ESTILOS)

    def construir(wb):
        hoja = wb.add_worksheet("Catalogo")
        estilos = est.Estilos(wb)
        for i, nombre in enumerate(nombres):
            hoja.write_blank(i, 0, None, estilos(nombre))

    celdas = _libro(construir)["hojas"]["Catalogo"]["celdas"]
    generados = {
        nombre: _clave_estilo(celdas[f"A{i + 1}"]["estilo"]) for i, nombre in enumerate(nombres)
    }
    medidos = _estilos_medidos()
    sobrantes = [n for n, k in generados.items() if k not in medidos]
    faltantes = [ref for k, ref in medidos.items() if k not in set(generados.values())]
    assert sobrantes == [], "formatos sin estilo medido (inventados)"
    assert faltantes == [], "estilos medidos sin formato en el catálogo"
    assert len(set(generados.values())) == len(nombres), "dos nombres para el mismo estilo"


def test_formatos_numericos_incorporados_y_propios():
    assert est.FORMATO_UNIDADES == 3 and est.FORMATO_FECHA == 14  # incorporados (enteros)
    assert est.FORMATO_COP == '"$"\\ #,##0.00'
    assert est.FORMATO_PORCENTAJE == "0.0\\ %"


def test_dxf_y_barra_de_datos_de_la_plantilla():
    dxf = HUELLAS["informe"]["libro"]["dxfs"][0]

    def construir(wb):
        hoja = wb.add_worksheet("Cf")
        hoja.conditional_format(
            "A1:A2",
            {
                "type": "formula",
                "criteria": "=TRUE",
                "format": wb.add_format(est.DXF_OTRA_UBICACION),
            },
        )

    (cf,) = _libro(construir)["hojas"]["Cf"]["formato_condicional"]
    assert u.comparar(dxf, cf["dxf"]) == []
    barra = HUELLAS["informe"]["hojas"]["Por ubicación"]["formato_condicional"][0]["barra"]
    assert u.comparar(barra["color"], {"rgb": "FF" + est.BARRA.lstrip("#")}) == []


# ---------------------------------------------------------------------------
# Escritura de celdas: dinero sin float; texto nunca fórmula
# ---------------------------------------------------------------------------


def test_escribir_celda_rechaza_float():
    def construir(wb):
        hoja = wb.add_worksheet("X")
        with pytest.raises(TypeError):
            est.escribir_fila(hoja, est.Estilos(wb), 0, [(1.5, "datos_cop")])

    _libro(construir)


def test_escribir_celda_decimal_exacto_y_texto_como_texto():
    def construir(wb):
        hoja = wb.add_worksheet("X")
        est.escribir_fila(
            hoja,
            est.Estilos(wb),
            0,
            [(Decimal("167226590.70"), "datos_cop"), ("=1+1", "datos"), (7, "datos_unidades")],
        )

    celdas = _libro(construir)["hojas"]["X"]["celdas"]
    assert celdas["A1"]["valor"] == 167226590.7
    assert (celdas["B1"]["tipo"], celdas["B1"]["valor"]) == ("s", "=1+1")
    assert celdas["C1"]["valor"] == 7


# ---------------------------------------------------------------------------
# Propiedades del documento (fila 26)
# ---------------------------------------------------------------------------


def test_propiedades_del_documento():
    def construir(wb):
        wb.set_properties(est.propiedades("Activos"))
        wb.add_worksheet("A")

    core = _libro(construir)["libro"]["propiedades"]["core"]
    assert core["title"] == "Activos"
    assert core["creator"] == core["lastModifiedBy"] == est.AUTOR == "AssetControl"
    assert set(core) == {"title", "creator", "lastModifiedBy", "created", "modified"}
