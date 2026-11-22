"""Buzón en carpeta para desarrollo (spec 014, R7 y A14; plan §7 «Carpeta»).

Escribe un ``.eml`` por mensaje con nombre ``<UTC>-<aleatorio>.eml``: nunca deriva del
destinatario ni del token. Solo se admite en development (``validar_entorno``) y la
carpeta por defecto, ``backend/.buzon/``, está en ``.gitignore``. Los ``.eml`` llevan
enlaces válidos: solo correos ficticios.
"""

import os
import secrets
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path


class Buzon:
    """Destino «carpeta». Crea el archivo en exclusiva (nunca sobrescribe)."""

    def __init__(self, carpeta: Path) -> None:
        self.carpeta = Path(carpeta).resolve()

    def entregar(self, mensaje: EmailMessage) -> Path:
        # B-3 de T3 (T8): la carpeta que se crea queda solo para el dueño (los ``.eml``
        # llevan enlaces válidos). Una carpeta que ya existe no se toca.
        self.carpeta.parent.mkdir(parents=True, exist_ok=True)
        self.carpeta.mkdir(mode=0o700, exist_ok=True)
        marca = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        ruta = self.carpeta / f"{marca}-{secrets.token_hex(8)}.eml"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
        fd = os.open(ruta, flags, 0o600)
        with os.fdopen(fd, "wb") as archivo:
            archivo.write(mensaje.as_bytes())
        return ruta
