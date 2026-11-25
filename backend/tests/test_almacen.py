"""Almacenamiento de fotos (spec 012, T1; R8, Q3; plan.md §2).

Las mismas pruebas corren contra la carpeta local y contra S3 (simulado con ``moto``):
guardar y leer, sobrescribir, inexistente, borrar idempotente y claves que intentan salir
de su lugar. Además, la configuración: qué almacenamiento se elige por entorno, qué
falta y que nunca se muestren las llaves.
"""

import uuid
from collections.abc import Iterator
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from app.config import MissingConfigError, load_config
from app.fotos import almacen
from app.fotos.almacen import AlmacenConfig, ClaveInvalida, ObjetoNoEncontrado

BUCKET = "fotos-prueba"
BASE_ENV = {"DATABASE_URL": "postgresql://a:b@h/d", "SECRET_KEY": "x" * 40}
S3_ENV = {
    "ALMACEN": "s3",
    "S3_ENDPOINT_URL": "https://ejemplo.storage.supabase.co/storage/v1/s3",
    "S3_REGION": "us-west-2",
    "S3_BUCKET": "fotos",
    "S3_ACCESS_KEY_ID": "llave-id-de-prueba",
    "S3_SECRET_ACCESS_KEY": "secreto-de-prueba-123",
}


def _clave() -> str:
    return f"{uuid.uuid4()}/{uuid.uuid4()}.jpg"


@pytest.fixture(params=["carpeta", "s3"])
def store(request, tmp_path: Path) -> Iterator[almacen.Almacen]:
    if request.param == "carpeta":
        yield almacen.CarpetaLocal(tmp_path / "almacen")
        return
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket=BUCKET)
        yield almacen.S3(
            AlmacenConfig(
                tipo="s3",
                s3_endpoint_url=None,
                s3_region="us-east-1",
                s3_bucket=BUCKET,
                s3_access_key_id="testing",
                s3_secret_access_key="testing",  # noqa: S106 - credencial de moto
            )
        )


def test_save_and_read_back(store):
    clave = _clave()
    store.guardar(clave, b"\xff\xd8bytes", "image/jpeg")
    assert store.leer(clave) == b"\xff\xd8bytes"


def test_saving_again_replaces_the_content(store):
    clave = _clave()
    store.guardar(clave, b"uno", "image/jpeg")
    store.guardar(clave, b"dos", "image/jpeg")
    assert store.leer(clave) == b"dos"


def test_reading_a_missing_key_raises(store):
    with pytest.raises(ObjetoNoEncontrado):
        store.leer(_clave())


def test_delete_removes_and_is_idempotent(store):
    clave = _clave()
    store.guardar(clave, b"x", "image/jpeg")
    store.borrar(clave)
    with pytest.raises(ObjetoNoEncontrado):
        store.leer(clave)
    store.borrar(clave)  # otra vez: sin error


@pytest.mark.parametrize(
    "clave",
    [
        "../fuera.jpg",
        "/abs/x.jpg",
        "a/../../x.jpg",
        "a\\b.jpg",
        "",
        "a/b.png",
        "a/ b.jpg",
        "a//b.jpg",
    ],
)
def test_keys_that_could_escape_are_rejected(store, clave):
    with pytest.raises(ClaveInvalida):
        store.guardar(clave, b"x", "image/jpeg")
    with pytest.raises(ClaveInvalida):
        store.leer(clave)
    with pytest.raises(ClaveInvalida):
        store.borrar(clave)


def test_local_folder_writes_inside_its_root_only(tmp_path):
    raiz = tmp_path / "raiz"
    store = almacen.CarpetaLocal(raiz)
    clave = _clave()
    store.guardar(clave, b"x", "image/jpeg")
    archivos = [p for p in raiz.rglob("*") if p.is_file()]
    assert archivos == [raiz / clave]
    assert not list(tmp_path.glob("*.tmp"))


# --- configuración


def test_development_defaults_to_the_local_folder():
    config = load_config({**BASE_ENV, "ENVIRONMENT": "development"})
    assert config.almacen is not None
    assert config.almacen.tipo == "carpeta"
    assert config.almacen.carpeta.name == ".almacen"


def test_local_folder_can_be_moved():
    config = load_config(
        {**BASE_ENV, "ENVIRONMENT": "development", "ALMACEN_CARPETA": "/srv/otra-carpeta"}
    )
    assert config.almacen.carpeta == Path("/srv/otra-carpeta")


def test_production_without_storage_starts_with_photos_off():
    config = load_config({**BASE_ENV, "ENVIRONMENT": "production", "TRUSTED_PROXY_HOPS": "1"})
    assert config.almacen is None


def test_production_refuses_the_local_folder():
    with pytest.raises(almacen.AlmacenNoValido) as exc:
        load_config(
            {
                **BASE_ENV,
                "ENVIRONMENT": "production",
                "TRUSTED_PROXY_HOPS": "1",
                "ALMACEN": "carpeta",
            }
        )
    assert "s3" in str(exc.value)


def test_unknown_storage_is_refused_without_echoing_it():
    with pytest.raises(almacen.AlmacenNoValido) as exc:
        load_config({**BASE_ENV, "ENVIRONMENT": "development", "ALMACEN": "ftp-raro"})
    assert "ftp-raro" not in str(exc.value)


def test_s3_reads_its_five_variables():
    config = load_config(
        {**BASE_ENV, "ENVIRONMENT": "production", "TRUSTED_PROXY_HOPS": "1", **S3_ENV}
    )
    a = config.almacen
    assert (a.tipo, a.s3_region, a.s3_bucket) == ("s3", "us-west-2", "fotos")
    assert a.s3_endpoint_url == S3_ENV["S3_ENDPOINT_URL"]


@pytest.mark.parametrize("falta", [k for k in S3_ENV if k != "ALMACEN"])
def test_s3_names_the_missing_variable(falta):
    env = {**BASE_ENV, "ENVIRONMENT": "production", "TRUSTED_PROXY_HOPS": "1", **S3_ENV}
    del env[falta]
    with pytest.raises(MissingConfigError) as exc:
        load_config(env)
    assert exc.value.missing == [falta]
    for secreto in (S3_ENV["S3_ACCESS_KEY_ID"], S3_ENV["S3_SECRET_ACCESS_KEY"]):
        assert secreto not in str(exc.value)


def test_storage_config_never_shows_the_keys():
    config = load_config(
        {**BASE_ENV, "ENVIRONMENT": "production", "TRUSTED_PROXY_HOPS": "1", **S3_ENV}
    )
    for texto in (repr(config), repr(config.almacen), str(config.almacen)):
        assert S3_ENV["S3_SECRET_ACCESS_KEY"] not in texto
        assert S3_ENV["S3_ACCESS_KEY_ID"] not in texto


def test_factory_builds_the_configured_store(tmp_path):
    local = almacen.crear(AlmacenConfig(tipo="carpeta", carpeta=tmp_path))
    assert isinstance(local, almacen.CarpetaLocal)
    assert almacen.crear(None) is None
