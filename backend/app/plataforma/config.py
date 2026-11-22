"""Configuración de la consola de plataforma (spec 017, T2; R1; plan.md §2.1, §2.7).

- ``PLATAFORMA_HABILITADA``: solo ``true`` (sin distinguir mayúsculas ni espacios en los
  extremos) la habilita. Cualquier otro valor, o ninguno, la deja apagada: no se registra
  ninguna ruta ``/plataforma`` (``404``) ni se crea nada al arrancar.
- ``PLATAFORMA_REDES_PERMITIDAS``: lista de redes CIDR (o direcciones sueltas) separadas
  por comas. Vacía = sin restricción. Fuera de la lista, ``/plataforma`` responde ``404``.
  Es una defensa adicional: la restricción real va en el proxy o el firewall.

Los TTL son constantes (``credenciales``). Ningún mensaje repite el valor recibido.
"""

import ipaddress
from collections.abc import Mapping
from dataclasses import dataclass

HABILITADA_VAR = "PLATAFORMA_HABILITADA"
REDES_VAR = "PLATAFORMA_REDES_PERMITIDAS"

Red = ipaddress.IPv4Network | ipaddress.IPv6Network


class RedesNoValidasError(RuntimeError):
    """``PLATAFORMA_REDES_PERMITIDAS`` no es una lista de redes válida. No repite el valor."""

    def __init__(self) -> None:
        super().__init__(
            f"{REDES_VAR} no es válida: debe ser una lista de redes CIDR separadas por comas "
            "(por ejemplo 10.0.0.0/8, 192.168.1.10)."
        )


def _redes(texto: str) -> tuple[Red, ...]:
    texto = texto.strip()
    if not texto:
        return ()
    partes = [parte.strip() for parte in texto.split(",")]
    if any(not parte for parte in partes):
        raise RedesNoValidasError()
    redes: list[Red] = []
    error = False
    for parte in partes:
        try:
            # strict=True: «10.0.0.1/8» (bits de host puestos) es un error, no una red.
            redes.append(ipaddress.ip_network(parte, strict=True))
        except ValueError:
            error = True
    if error:
        # Fuera del except: sin causa que arrastre el valor.
        raise RedesNoValidasError()
    return tuple(redes)


@dataclass(frozen=True)
class PlataformaConfig:
    habilitada: bool = False
    redes_permitidas: tuple[Red, ...] = ()

    @classmethod
    def desde_texto(cls, habilitada: str | None, redes: str | None) -> "PlataformaConfig":
        return cls(
            habilitada=(habilitada or "").strip().lower() == "true",
            redes_permitidas=_redes(redes or ""),
        )

    def permite(self, direccion: str | None) -> bool:
        """``True`` si no hay lista o ``direccion`` cae en alguna red de la lista."""
        if not self.redes_permitidas:
            return True
        if direccion is None:
            return False
        try:
            ip = ipaddress.ip_address(direccion.strip())
        except ValueError:
            return False
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        return any(ip.version == red.version and ip in red for red in self.redes_permitidas)


def load_plataforma(source: Mapping[str, str]) -> PlataformaConfig:
    return PlataformaConfig.desde_texto(source.get(HABILITADA_VAR), source.get(REDES_VAR))
