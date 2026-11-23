"""Datos de demostración por la API, para revisar la app en desarrollo o staging.

``flask sembrar-demo <email>`` (ver ``app.cli``) usa la cuenta de un **admin** existente,
entra por ``POST /auth/login`` con su contraseña y, dentro del mismo proceso
(``app.test_client()``, sin red), recorre la API como lo haría la web:

1. Ubicaciones: usa la primera sede activa (o crea «Sede principal») y crea las salas de
   ``SALAS`` que falten en ella. Un ``409`` (ya existe con ese nombre) no es error.
2. Categorías: crea las de ``CATEGORIAS`` que falten (``409`` no es error).
3. Activos: ``cantidad`` activos ``SEM-001``…, con id ``uuid5`` fijo por empresa y
   número, así que repetir no duplica (la API devuelve ``200`` con el mismo activo).
4. Con ``sesion=True``: abre una sesión de conteo, registra verificaciones (la mayoría
   en su sitio, algunas en otra ubicación y algunas dañadas, el resto sin contar) y la
   cierra. Cada corrida crea una sesión nueva. Si hay **otra** sesión abierta, no se toca
   y se omite este paso.

Todo pasa por las rutas de la app: códigos, historial, reglas de ubicación y auditoría
son los de siempre. Nunca escribe en la base por otro camino ni firma tokens. Solo datos
ficticios. El comando se niega a correr con ``ENVIRONMENT=production``.
"""

import random
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from flask import Flask

PREFIJO_CODIGO = "SEM-"
NOMBRE_SESION = "Conteo de prueba (siembra)"
NS = uuid.UUID("5e3d0c1a-0000-4000-8000-000000000019")
SALAS = ("Consultorio 1", "Consultorio 2", "Esterilización", "Rayos X", "Recepción")
CATEGORIAS = ("Equipo odontológico", "Instrumental", "Mobiliario", "Cómputo", "Esterilización")
# (nombre, categoría, marca, modelo, precio en COP): equipos típicos de una clínica dental.
CATALOGO: tuple[tuple[str, str, str, str, int], ...] = (
    ("Unidad odontológica", "Equipo odontológico", "Sirona", "Intego Pro", 38_500_000),
    ("Compresor libre de aceite", "Equipo odontológico", "Schulz", "MSV 12", 4_200_000),
    ("Autoclave clase B", "Esterilización", "W&H", "Lisa 22", 18_900_000),
    ("Lámpara de fotocurado", "Instrumental", "3M", "Elipar DeepCure", 2_350_000),
    ("Rayos X intraoral", "Equipo odontológico", "Carestream", "CS 2200", 16_700_000),
    ("Sensor radiográfico digital", "Equipo odontológico", "Carestream", "RVG 6200", 21_400_000),
    ("Micromotor eléctrico", "Instrumental", "NSK", "Surgic Pro", 9_800_000),
    ("Pieza de mano de alta velocidad", "Instrumental", "NSK", "Pana-Max", 1_150_000),
    ("Escalador ultrasónico", "Instrumental", "Woodpecker", "UDS-K", 1_900_000),
    ("Amalgamador", "Instrumental", "SDI", "Ultimate", 1_250_000),
    ("Selladora térmica", "Esterilización", "Euronda", "Euroseal", 2_800_000),
    ("Lavadora ultrasónica", "Esterilización", "Biobase", "UC-6", 1_600_000),
    ("Silla para odontólogo", "Mobiliario", "Ergonomic", "Saddle", 980_000),
    ("Mueble modular de consultorio", "Mobiliario", "Dentalmuebles", "M-120", 3_400_000),
    ("Escritorio de recepción", "Mobiliario", "Oficinas", "Rec-140", 1_750_000),
    ("Computador de escritorio", "Cómputo", "Lenovo", "ThinkCentre M70", 3_100_000),
    ("Portátil", "Cómputo", "Dell", "Latitude 5440", 4_600_000),
    ("Impresora multifuncional", "Cómputo", "Epson", "EcoTank L6270", 1_350_000),
    ("Monitor 24 pulgadas", "Cómputo", "Samsung", "S24C", 720_000),
    ("Aspirador quirúrgico", "Equipo odontológico", "Cattani", "Turbo-Smart", 7_900_000),
)
MAX_ACTIVOS = 500


class SiembraError(Exception):
    """Falla de la siembra; el mensaje no lleva la contraseña ni el token."""


@dataclass
class Resultado:
    ubicaciones_creadas: list[str] = field(default_factory=list)
    categorias_creadas: list[str] = field(default_factory=list)
    activos_nuevos: int = 0
    activos_existentes: int = 0
    sesion_id: str | None = None
    sesion_omitida: str | None = None
    totales: dict[str, Any] | None = None


def _datos(respuesta: Any) -> Any:
    return respuesta.get_json(silent=True)


def _lista(cuerpo: Any, clave: str) -> list[dict]:
    if isinstance(cuerpo, dict):
        return cuerpo.get(clave) or cuerpo.get("items") or []
    return cuerpo or []


def sembrar(
    app: Flask,
    email: str,
    password: str,
    *,
    cantidad: int = 40,
    sesion: bool = True,
    hoy: date | None = None,
    avisar: Callable[[str], None] = lambda _texto: None,
) -> Resultado:
    """Siembra por la API con la cuenta de un admin. ``SiembraError`` si algo no cuadra."""
    if not 1 <= cantidad <= MAX_ACTIVOS:
        raise SiembraError(f"La cantidad de activos va de 1 a {MAX_ACTIVOS}.")
    hoy = hoy or date.today()
    client = app.test_client(use_cookies=False)
    entrada = client.post("/auth/login", json={"email": email, "password": password})
    if entrada.status_code != 200:
        raise SiembraError("No se pudo entrar con esa cuenta (correo o contraseña incorrectos).")
    cuerpo = _datos(entrada) or {}
    if cuerpo.get("debe_cambiar_password"):
        raise SiembraError("La cuenta debe cambiar su contraseña antes de usarse.")
    if cuerpo.get("rol") != "admin":
        raise SiembraError("La cuenta debe ser admin de la empresa.")
    cabeceras = {"Authorization": f"Bearer {cuerpo['access_token']}"}
    resultado = Resultado()

    def api(metodo: str, ruta: str, json: Any = None) -> Any:
        return client.open(ruta, method=metodo, json=json, headers=cabeceras)

    # Ids fijos por empresa: repetir en la misma empresa no duplica activos.
    semilla = str(cuerpo["tenant"]["id"])
    aleatorio = random.Random(f"siembra-{semilla}")  # noqa: S311 - datos ficticios repetibles

    # 1. Ubicaciones ------------------------------------------------------------------
    ubicaciones = _lista(_datos(api("GET", "/ubicaciones")), "ubicaciones")
    sede = next((u for u in ubicaciones if u["tipo"] == "sede" and u["activa"]), None)
    if sede is None:
        respuesta = api("POST", "/ubicaciones", {"nombre": "Sede principal", "tipo": "sede"})
        if respuesta.status_code != 201:
            raise SiembraError(f"No se pudo crear la sede ({respuesta.status_code}).")
        sede = _datos(respuesta)["ubicacion"]
        resultado.ubicaciones_creadas.append(sede["nombre"])
    for nombre in SALAS:
        respuesta = api(
            "POST", "/ubicaciones", {"nombre": nombre, "tipo": "sala", "padre_id": sede["id"]}
        )
        if respuesta.status_code == 201:
            resultado.ubicaciones_creadas.append(nombre)
        elif respuesta.status_code != 409:
            raise SiembraError(f"No se pudo crear la sala {nombre} ({respuesta.status_code}).")
    salas = [
        u
        for u in _lista(_datos(api("GET", "/ubicaciones")), "ubicaciones")
        if u["tipo"] in ("sala", "box") and u["activa"]
    ]
    if len(salas) < 2:
        raise SiembraError("Hacen falta al menos dos salas activas.")

    # 2. Categorías -------------------------------------------------------------------
    for nombre in CATEGORIAS:
        respuesta = api("POST", "/categorias", {"nombre": nombre})
        if respuesta.status_code == 201:
            resultado.categorias_creadas.append(nombre)
        elif respuesta.status_code != 409:
            raise SiembraError(f"No se pudo crear la categoría {nombre} ({respuesta.status_code}).")
    categorias = _lista(_datos(api("GET", "/categorias")), "categorias")
    por_nombre = {c["nombre"].casefold(): c for c in categorias}

    def categoria(nombre: str) -> dict:
        return por_nombre.get(nombre.casefold()) or aleatorio.choice(categorias)

    # 3. Activos ----------------------------------------------------------------------
    activos: list[tuple[str, str]] = []
    for i in range(cantidad):
        nombre, cat, marca, modelo, precio = CATALOGO[i % len(CATALOGO)]
        vuelta = i // len(CATALOGO)
        sala = salas[i % len(salas)]
        variacion = aleatorio.choice((0.9, 1.0, 1.05, 1.1))
        activo_id = str(uuid.uuid5(NS, f"{semilla}-activo-{i}"))
        cuerpo_activo = {
            "id": activo_id,
            "codigo": f"{PREFIJO_CODIGO}{i + 1:03d}",
            "nombre": nombre if vuelta == 0 else f"{nombre} {vuelta + 1}",
            "precio_compra": f"{round(precio * variacion / 1000) * 1000}.00",
            "categoria_id": categoria(cat)["id"],
            "ubicacion_id": sala["id"],
            "marca": marca,
            "modelo": modelo,
            "serial": f"SN{aleatorio.randint(10**7, 10**8 - 1)}",
            "fecha_compra": (hoy - timedelta(days=aleatorio.randint(60, 2500))).isoformat(),
        }
        respuesta = api("POST", "/activos", cuerpo_activo)
        if respuesta.status_code == 201:
            resultado.activos_nuevos += 1
        elif respuesta.status_code == 200:
            resultado.activos_existentes += 1
        else:
            avisar(f"Activo {cuerpo_activo['codigo']} omitido ({respuesta.status_code}).")
            continue
        activos.append((activo_id, sala["id"]))

    if not sesion:
        return resultado

    # 4. Sesión de conteo cerrada -----------------------------------------------------
    abierta = (_datos(api("GET", "/sesiones/abierta")) or {}).get("sesion")
    if abierta:
        resultado.sesion_omitida = "Ya hay una sesión de conteo abierta; no se tocó."
        return resultado
    respuesta = api("POST", "/sesiones", {"nombre": NOMBRE_SESION, "fecha_corte": hoy.isoformat()})
    if respuesta.status_code != 201:
        raise SiembraError(f"No se pudo abrir la sesión ({respuesta.status_code}).")
    sid = _datos(respuesta)["sesion"]["id"]
    orden = list(activos)
    aleatorio.shuffle(orden)
    n = len(orden)
    en_sitio, otra, danados = round(n * 0.65), round(n * 0.1), round(n * 0.075)
    for posicion, (activo_id, ubicacion_id) in enumerate(orden[: en_sitio + otra + danados]):
        destino = ubicacion_id
        estado = "ok"
        if en_sitio <= posicion < en_sitio + otra:
            destino = next(s["id"] for s in salas if s["id"] != ubicacion_id)
        elif posicion >= en_sitio + otra:
            estado = "danado"
        verificacion = {
            "id": str(uuid.uuid4()),
            "activo_id": activo_id,
            "ubicacion_encontrada_id": destino,
            "estado_fisico": estado,
        }
        respuesta = api("POST", f"/sesiones/{sid}/verificaciones", verificacion)
        if respuesta.status_code not in (200, 201):
            avisar(f"Verificación omitida ({respuesta.status_code}).")
    respuesta = api("POST", f"/sesiones/{sid}/cerrar", {})
    if respuesta.status_code != 200:
        raise SiembraError(f"No se pudo cerrar la sesión ({respuesta.status_code}).")
    resultado.sesion_id = sid
    resultado.totales = (_datos(respuesta) or {}).get("totales")
    return resultado
