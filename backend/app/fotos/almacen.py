"""Almacenamiento de las imágenes (spec 012, T1; R8, Q3; plan.md §2).

Las imágenes no viven en la base (``docs/03``): Flask las guarda y las lee aquí. Dos
implementaciones con la misma interfaz:

- ``CarpetaLocal``: una carpeta del disco (desarrollo y pruebas; Q3 A).
- ``S3``: almacenamiento compatible con S3 (Supabase Storage en producción), con
  ``boto3`` y estilo de ruta. El bucket es privado: ninguna URL sale al navegador.

Las claves las arma el servidor (``<tenant>/<foto>.jpg`` y ``<tenant>/<foto>_mini.jpg``)
y se validan con una expresión estricta: nada del usuario llega a una ruta ni a una
clave. Los errores nunca muestran la clave ni las llaves.
"""

import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

_UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_CLAVE = re.compile(rf"{_UUID}/{_UUID}(_mini)?\.jpg")
TIPOS = ("carpeta", "s3")
S3_VARS = ("S3_ENDPOINT_URL", "S3_REGION", "S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY")
CARPETA_POR_DEFECTO = Path(__file__).resolve().parents[2] / ".almacen"
EXTENSION_KEY = "assetcontrol.almacen"


class ClaveInvalida(ValueError):
    """La clave no tiene la forma ``<uuid>/<uuid>[_mini].jpg``. No repite la clave."""

    def __init__(self) -> None:
        super().__init__("Clave de almacenamiento no válida.")


class ObjetoNoEncontrado(LookupError):
    """No hay imagen con esa clave. No repite la clave."""

    def __init__(self) -> None:
        super().__init__("La imagen no existe en el almacenamiento.")


class AlmacenNoValido(RuntimeError):
    """``ALMACEN`` no es válido para el entorno. No repite el valor recibido."""


@dataclass(frozen=True)
class AlmacenConfig:
    """Dónde se guardan las fotos. Las llaves de S3 nunca salen en ``repr``."""

    tipo: str
    carpeta: Path | None = None
    s3_endpoint_url: str | None = None
    s3_region: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: str | None = field(default=None, repr=False)
    s3_secret_access_key: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.tipo not in TIPOS:
            raise AlmacenNoValido("ALMACEN debe ser «carpeta» o «s3».")


def validar_clave(clave: str) -> str:
    if not isinstance(clave, str) or not _CLAVE.fullmatch(clave):
        raise ClaveInvalida()
    return clave


class Almacen(Protocol):
    def guardar(self, clave: str, datos: bytes, tipo: str) -> None: ...

    def leer(self, clave: str) -> bytes: ...

    def borrar(self, clave: str) -> None: ...


class CarpetaLocal:
    """Imágenes en una carpeta. Escribe en un temporal y lo renombra (sin archivos a medias)."""

    def __init__(self, raiz: Path) -> None:
        self.raiz = Path(raiz).resolve()

    def _ruta(self, clave: str) -> Path:
        ruta = (self.raiz / validar_clave(clave)).resolve()
        if self.raiz not in ruta.parents:
            raise ClaveInvalida()
        return ruta

    def guardar(self, clave: str, datos: bytes, tipo: str) -> None:
        ruta = self._ruta(clave)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        fd, temporal = tempfile.mkstemp(dir=ruta.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as archivo:
                archivo.write(datos)
            os.replace(temporal, ruta)
        except BaseException:
            Path(temporal).unlink(missing_ok=True)
            raise

    def leer(self, clave: str) -> bytes:
        ruta = self._ruta(clave)
        try:
            return ruta.read_bytes()
        except FileNotFoundError:
            raise ObjetoNoEncontrado() from None

    def borrar(self, clave: str) -> None:
        self._ruta(clave).unlink(missing_ok=True)


class S3:
    """Almacenamiento compatible con S3 (Supabase Storage). Bucket privado, sin ACL."""

    def __init__(self, config: AlmacenConfig) -> None:
        import boto3
        from botocore.config import Config as BotoConfig

        self.bucket = config.s3_bucket
        self._cliente: Any = boto3.client(
            "s3",
            endpoint_url=config.s3_endpoint_url,
            region_name=config.s3_region,
            aws_access_key_id=config.s3_access_key_id,
            aws_secret_access_key=config.s3_secret_access_key,
            config=BotoConfig(
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=5,
                read_timeout=20,
            ),
        )

    def guardar(self, clave: str, datos: bytes, tipo: str) -> None:
        self._cliente.put_object(
            Bucket=self.bucket, Key=validar_clave(clave), Body=datos, ContentType=tipo
        )

    def leer(self, clave: str) -> bytes:
        from botocore.exceptions import ClientError

        try:
            respuesta = self._cliente.get_object(Bucket=self.bucket, Key=validar_clave(clave))
        except ClientError as exc:
            codigo = exc.response.get("Error", {}).get("Code")
            if codigo in ("NoSuchKey", "404", "NotFound"):
                raise ObjetoNoEncontrado() from None
            raise
        return respuesta["Body"].read()

    def borrar(self, clave: str) -> None:
        # S3 responde bien aunque el objeto no exista: idempotente.
        self._cliente.delete_object(Bucket=self.bucket, Key=validar_clave(clave))


def crear(config: AlmacenConfig | None) -> Almacen | None:
    """El almacenamiento configurado, o ``None`` si las fotos están desactivadas."""
    if config is None:
        return None
    if config.tipo == "carpeta":
        return CarpetaLocal(config.carpeta or CARPETA_POR_DEFECTO)
    return S3(config)
