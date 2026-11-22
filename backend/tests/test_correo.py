"""Módulo de correo y su configuración (spec 014, T3; R5–R8, R16, R18; A13, A14).

No usa la base de datos. Datos sintéticos: correos ``@ejemplo.test`` y valores de
prueba que nunca son credenciales reales. Cada prueba comprueba también que el log no
lleva el token, el correo completo, el host ni la clave SMTP.
"""

import email
import email.policy
import logging
import re
import secrets
import smtplib
import socket
import ssl
import stat
import sys
import threading
import time
from email.message import EmailMessage
from pathlib import Path
from unittest import mock

import pytest

from app import create_app
from app.config import Config, load_config
from app.correo import (
    EXTENSION_KEY,
    MAX_CONCURRENCIA,
    Correo,
    correo_activo,
    crear,
    get_correo,
)
from app.correo.buzon import Buzon
from app.correo.config import (
    BUZON_POR_DEFECTO,
    SMTP_PLAZO_TOTAL_SEGUNDOS,
    SMTP_TIMEOUT_SEGUNDOS,
    CorreoConfig,
    CorreoNoValido,
    es_direccion_simple,
    load_correo,
)
from app.correo.plantillas import (
    ASUNTO,
    ASUNTO_AVISO,
    DestinoNoValido,
    TokenNoValido,
    componer_aviso_restablecimiento,
    componer_recuperacion,
    enlace_recuperacion,
)
from app.correo.smtp import ServidorSmtp, _Vigilante, nombre_ehlo

DESTINO = "persona.recupera@ejemplo.test"
CLAVE_SMTP = "clave-smtp-de-prueba-no-real"
USUARIO_SMTP = "usuario-smtp@ejemplo.test"
HOST_SMTP = "smtp.servidor-de-prueba.invalid"
REMITENTE = "AssetControl <no-responder@ejemplo.test>"
URL = "https://inventario.ejemplo.test"
OFFLINE_DB = "postgresql+psycopg://user:valor-secreto-db@db.invalid:5432/assetcontrol"
BASE_ENV = {
    "DATABASE_URL": OFFLINE_DB,
    "SECRET_KEY": "s" * 40,
    "ENVIRONMENT": "production",
}


def _token() -> str:
    return secrets.token_urlsafe(32)


def _smtp_env(**extra: str) -> dict[str, str]:
    env = {
        **BASE_ENV,
        "CORREO_MODO": "smtp",
        "CORREO_REMITENTE": REMITENTE,
        "SMTP_HOST": HOST_SMTP,
        "SMTP_PUERTO": "587",
        "SMTP_USUARIO": USUARIO_SMTP,
        "SMTP_CLAVE": CLAVE_SMTP,
        "SMTP_CIFRADO": "starttls",
        "URL_PUBLICA": URL,
    }
    env.update(extra)
    return env


def _smtp_config(**cambios) -> CorreoConfig:
    valores = {
        "modo": "smtp",
        "remitente": REMITENTE,
        "url_publica": URL,
        "smtp_host": HOST_SMTP,
        "smtp_puerto": 587,
        "smtp_usuario": USUARIO_SMTP,
        "smtp_clave": CLAVE_SMTP,
        "smtp_cifrado": "starttls",
    }
    valores.update(cambios)
    return CorreoConfig(**valores)


def _carpeta_config(carpeta: Path) -> CorreoConfig:
    return CorreoConfig(
        modo="carpeta", remitente=REMITENTE, url_publica="http://localhost:5173", carpeta=carpeta
    )


def _assert_sin_secretos(texto: str, token: str | None = None) -> None:
    for secreto in (DESTINO, CLAVE_SMTP, USUARIO_SMTP, HOST_SMTP):
        assert secreto not in texto
    assert "recupera@" not in texto
    if token is not None:
        assert token not in texto
        assert "restablecer#" not in texto


def _log_text(caplog) -> str:
    partes = []
    for record in caplog.records:
        partes.append(record.getMessage())
        if record.exc_info:
            partes.append(logging.Formatter().formatException(record.exc_info))
        if record.exc_text:
            partes.append(record.exc_text)
    return "\n".join(partes)


class _Registro:
    """Destino falso: guarda los mensajes; ``bloqueo`` lo hace lento a voluntad."""

    def __init__(self, bloqueo: threading.Event | None = None, falla: Exception | None = None):
        self.mensajes = []
        self.bloqueo = bloqueo
        self.falla = falla
        self.en_curso = 0
        self.maximo = 0
        self._lock = threading.Lock()

    def entregar(self, mensaje) -> None:
        with self._lock:
            self.en_curso += 1
            self.maximo = max(self.maximo, self.en_curso)
        try:
            if self.bloqueo is not None:
                self.bloqueo.wait(5)
            if self.falla is not None:
                raise self.falla
            self.mensajes.append(mensaje)
        finally:
            with self._lock:
                self.en_curso -= 1


# --- Plantilla (R5, R6) -----------------------------------------------------------------


def test_link_puts_the_token_in_the_fragment():
    token = _token()

    assert enlace_recuperacion(URL, token) == f"{URL}/restablecer#{token}"
    assert enlace_recuperacion(URL + "/", token) == f"{URL}/restablecer#{token}"


def test_message_is_plain_spanish_text_with_link_and_fixed_subject():
    token = _token()

    mensaje = componer_recuperacion(REMITENTE, DESTINO, URL, token)

    assert mensaje["Subject"] == ASUNTO == "Restablece tu contraseña de AssetControl"
    assert mensaje["To"] == DESTINO
    assert mensaje["From"] == REMITENTE
    assert mensaje["Auto-Submitted"] == "auto-generated"
    assert mensaje["Message-ID"]
    assert mensaje.get_content_type() == "multipart/alternative"
    partes = [parte.get_content_type() for parte in mensaje.iter_parts()]
    # El texto plano va primero: los clientes muestran la última alternativa que entienden.
    assert partes == ["text/plain", "text/html"]
    texto = mensaje.get_body(preferencelist=("plain",))
    assert texto.get_content_charset() == "utf-8"
    cuerpo = texto.get_content()
    assert f"{URL}/restablecer#{token}" in cuerpo
    assert "Vence en 30 minutos y solo sirve una vez" in cuerpo
    assert "Si no lo pediste, ignora este mensaje; tu contraseña no cambia" in cuerpo
    assert "?" not in enlace_recuperacion(URL, token)


def test_html_alternative_has_brand_button_and_fallback_link():
    token = _token()

    mensaje = componer_recuperacion(REMITENTE, DESTINO, URL, token)

    parte = mensaje.get_body(preferencelist=("html",))
    assert parte.get_content_type() == "text/html"
    assert parte.get_content_charset() == "utf-8"
    cuerpo = parte.get_content()
    enlace = f"{URL}/restablecer#{token}"
    assert '<html lang="es">' in cuerpo
    assert "Elegir nueva contraseña" in cuerpo
    # El botón y el enlace de respaldo apuntan al mismo enlace, y se muestra en texto.
    assert cuerpo.count(f'href="{enlace}"') == 2
    assert f">{enlace}</a>" in cuerpo
    assert "Vence en 30 minutos y solo sirve una vez" in cuerpo
    assert "Si no lo pediste, ignora este mensaje; tu contraseña no cambia" in cuerpo
    # Marca del producto (docs/08-diseno-visual.md): botón neutro oscuro, cobalto.
    assert "#18181B" in cuerpo
    assert "#2B50E0" in cuerpo


def test_html_alternative_loads_nothing_and_has_no_personal_data():
    token = _token()

    mensaje = componer_recuperacion(REMITENTE, DESTINO, URL, token)

    cuerpo = mensaje.get_body(preferencelist=("html",)).get_content().lower()
    for prohibido in ("<img", "<script", "<link", "<style", "src=", "url(", "@import"):
        assert prohibido not in cuerpo
    # El único destino de red es el enlace de recuperación (R5, R6).
    assert set(re.findall(r'href="([^"]*)"', cuerpo)) == {f"{URL}/restablecer#{token}".lower()}
    assert re.findall(r"https?://[^\s\"<]+", cuerpo) == [f"{URL}/restablecer#{token}".lower()] * 3
    assert DESTINO.lower() not in cuerpo
    assert "persona" not in cuerpo


def test_html_alternative_escapes_the_link():
    token = _token()
    url_rara = "https://ejemplo.test/a&b"

    mensaje = componer_recuperacion(REMITENTE, DESTINO, url_rara, token)

    cuerpo = mensaje.get_body(preferencelist=("html",)).get_content()
    assert f'href="https://ejemplo.test/a&amp;b/restablecer#{token}"' in cuerpo
    assert "a&b/" not in cuerpo


@pytest.mark.parametrize(
    "destino",
    [
        "persona@ejemplo.test\r\nBcc: otra@ejemplo.test",
        "persona@ejemplo.test\nBcc: otra@ejemplo.test",
        "persona@ejemplo.test\r",
        "persona@ejemplo.test, otra@ejemplo.test",
        "Nombre <persona@ejemplo.test>",
        "persona@ejemplo.test;otra@ejemplo.test",
        "sin-arroba",
        "dos@@ejemplo.test",
        "",
        " persona@ejemplo.test",
        "persona\x00@ejemplo.test",
        "a" * 250 + "@ejemplo.test",
        # B-1 de T3 (T8): dot-atom estricto en la parte local y en el dominio.
        "dos..puntos@ejemplo.test",
        ".inicio@ejemplo.test",
        "final.@ejemplo.test",
        "a" * 65 + "@ejemplo.test",
        "ruta%otro@ejemplo.test",
        "bang!otro@ejemplo.test",
        "persona@ejemplo..test",
        "persona@-ejemplo.test",
        "persona@ejemplo-.test",
    ],
)
def test_header_injection_and_odd_recipients_are_rejected(destino):
    with pytest.raises(DestinoNoValido) as info:
        componer_recuperacion(REMITENTE, destino, URL, _token())

    assert "ejemplo.test" not in str(info.value)


@pytest.mark.parametrize(
    "destino",
    [
        "persona@ejemplo.test",
        "nombre.apellido+etiqueta@sub.ejemplo.test",
        "a" * 64 + "@ejemplo.test",
        "o'neil_x-y=z#{1}~@ejemplo.test",
        "persona@localhost",
    ],
)
def test_simple_dot_atom_recipients_are_accepted(destino):
    assert es_direccion_simple(destino)
    assert componer_recuperacion(REMITENTE, destino, URL, _token())["To"] == destino


@pytest.mark.parametrize("token", ["", "a" * 20, "con espacio" * 5, "x\r\nBcc: y" * 5, "#" * 43])
def test_malformed_tokens_are_rejected_without_echo(token):
    with pytest.raises(ValueError) as info:
        componer_recuperacion(REMITENTE, DESTINO, URL, token)

    if token:
        assert token not in str(info.value)


# --- Plantilla del aviso de contraseña temporal (spec 017, C1d; R62, R63) ---------------

AVISO_CIERRE = "Si no esperabas este cambio, avísale al administrador de tu empresa."
AVISO_INICIO = (
    "El equipo de AssetControl definió una contraseña temporal para tu cuenta "
    "y cerró tus sesiones abiertas."
)


def test_notice_with_link_is_spanish_multipart_with_fixed_subject():
    token = _token()

    mensaje = componer_aviso_restablecimiento(REMITENTE, DESTINO, URL, token)

    assert (
        mensaje["Subject"] == ASUNTO_AVISO == "Se restableció el acceso a tu cuenta de AssetControl"
    )
    assert mensaje["To"] == DESTINO
    assert mensaje["From"] == REMITENTE
    assert mensaje["Auto-Submitted"] == "auto-generated"
    assert mensaje["Message-ID"].endswith("@ejemplo.test>")
    assert [p.get_content_type() for p in mensaje.iter_parts()] == ["text/plain", "text/html"]
    enlace = f"{URL}/restablecer#{token}"
    texto = mensaje.get_body(preferencelist=("plain",)).get_content()
    cuerpo = mensaje.get_body(preferencelist=("html",)).get_content()
    for parte in (texto, cuerpo):
        assert AVISO_INICIO in parte
        assert "Vence en 30 minutos y solo sirve una vez" in parte
        assert "también puedes entrar con ella" in parte
        assert AVISO_CIERRE in parte
    assert enlace in texto
    assert cuerpo.count(f'href="{enlace}"') == 2
    assert "Elegir mi contraseña" in cuerpo


def test_notice_without_link_has_no_link_and_points_to_who_gave_the_password():
    mensaje = componer_aviso_restablecimiento(REMITENTE, DESTINO, URL, None)

    texto = mensaje.get_body(preferencelist=("plain",)).get_content()
    cuerpo = mensaje.get_body(preferencelist=("html",)).get_content()
    for parte in (texto, cuerpo):
        assert AVISO_INICIO in parte
        assert "pide la contraseña temporal a quien te la definió" in parte
        assert AVISO_CIERRE in parte
        assert "/restablecer" not in parte
        assert "Vence en 30 minutos" not in parte
    assert "href=" not in cuerpo
    assert "http" not in texto


@pytest.mark.parametrize("token", [None, "con-enlace"])
def test_notice_loads_nothing_and_has_no_personal_or_company_data(token):
    token = _token() if token else None

    mensaje = componer_aviso_restablecimiento(REMITENTE, DESTINO, URL, token)

    for parte in mensaje.iter_parts():
        cuerpo = parte.get_content().lower()
        for prohibido in ("<img", "<script", "<link", "<style", "src=", "url(", "@import"):
            assert prohibido not in cuerpo
        assert DESTINO.lower() not in cuerpo
        assert "persona" not in cuerpo
        assert "clínica" not in cuerpo
    cuerpo = mensaje.get_body(preferencelist=("html",)).get_content().lower()
    esperados = set() if token is None else {f"{URL}/restablecer#{token}".lower()}
    assert set(re.findall(r'href="([^"]*)"', cuerpo)) == esperados


def test_notice_escapes_the_link_and_rejects_bad_recipients_and_tokens():
    token = _token()

    cuerpo = (
        componer_aviso_restablecimiento(REMITENTE, DESTINO, "https://ejemplo.test/a&b", token)
        .get_body(preferencelist=("html",))
        .get_content()
    )
    assert f'href="https://ejemplo.test/a&amp;b/restablecer#{token}"' in cuerpo
    with pytest.raises(DestinoNoValido):
        componer_aviso_restablecimiento(REMITENTE, "a@ejemplo.test\r\nBcc: b@x.test", URL, None)
    with pytest.raises(TokenNoValido):
        componer_aviso_restablecimiento(REMITENTE, DESTINO, URL, "corto")


def test_notice_sends_through_the_same_bounded_thread_without_leaking(tmp_path, caplog):
    registro = []

    class Registro:
        def entregar(self, mensaje):
            registro.append(mensaje)

    correo = Correo(
        CorreoConfig(modo="carpeta", remitente=REMITENTE, url_publica=URL, carpeta=tmp_path),
        transporte=Registro(),
    )
    token = _token()
    with caplog.at_level(logging.DEBUG):
        correo.enviar_aviso_restablecimiento(DESTINO, token, request_id="rid-aviso")
        correo.enviar_aviso_restablecimiento(DESTINO, None, request_id="rid-aviso-2")
        assert correo.esperar(5)

    assert [m["Subject"] for m in registro] == [ASUNTO_AVISO, ASUNTO_AVISO]
    assert "Correo de aviso entregado (request_id=rid-aviso)" in caplog.text
    assert DESTINO not in caplog.text
    assert token not in caplog.text


def test_notice_failure_logs_only_type_and_request_id(tmp_path, caplog):
    class Falla:
        def entregar(self, mensaje):
            raise OSError(f"fallo con {DESTINO}")

    correo = Correo(
        CorreoConfig(modo="carpeta", remitente=REMITENTE, url_publica=URL, carpeta=tmp_path),
        transporte=Falla(),
    )
    with caplog.at_level(logging.DEBUG):
        correo.enviar_aviso_restablecimiento(DESTINO, _token(), request_id="rid-falla")
        assert correo.esperar(5)

    assert "Correo de aviso no enviado (request_id=rid-falla, tipo=OSError)" in caplog.text
    assert DESTINO not in caplog.text


def test_disabled_mail_ignores_the_notice(tmp_path):
    correo = Correo(None)

    assert correo.enviar_aviso_restablecimiento(DESTINO, _token(), request_id="rid") is None
    assert correo.esperar(1)


# --- Configuración (R7, R18) ------------------------------------------------------------


def test_without_mode_recovery_is_disabled():
    assert load_correo({}, "production") is None
    assert load_correo({"CORREO_MODO": "  "}, "development") is None
    assert load_config(BASE_ENV).correo is None


def test_smtp_config_is_read_from_environment():
    config = load_config(_smtp_env()).correo

    assert config == _smtp_config()
    assert config.smtp_puerto == 587


@pytest.mark.parametrize(
    ("cifrado", "puerto"),
    [("starttls", 587), ("ssl", 465), ("STARTTLS", 587), (" ssl ", 465)],
)
def test_default_port_follows_encryption(cifrado, puerto):
    env = _smtp_env(SMTP_CIFRADO=cifrado)
    del env["SMTP_PUERTO"]

    assert load_config(env).correo.smtp_puerto == puerto


def test_folder_mode_in_development_uses_default_mailbox():
    env = {
        **BASE_ENV,
        "ENVIRONMENT": "development",
        "CORREO_MODO": "carpeta",
        "URL_PUBLICA": "http://localhost:5173",
    }

    config = load_config(env).correo

    assert config.modo == "carpeta"
    assert config.carpeta == BUZON_POR_DEFECTO
    assert BUZON_POR_DEFECTO.name == ".buzon"
    assert BUZON_POR_DEFECTO.parent.name == "backend"
    assert config.remitente


def test_folder_mode_reads_custom_folder(tmp_path):
    env = {
        **BASE_ENV,
        "ENVIRONMENT": "development",
        "CORREO_MODO": "carpeta",
        "CORREO_CARPETA": str(tmp_path),
        "URL_PUBLICA": "http://localhost:5173/",
    }

    config = load_config(env).correo

    assert config.carpeta == tmp_path
    assert config.url_publica == "http://localhost:5173"


def test_development_smtp_without_encryption_defaults_to_starttls_never_plain():
    env = _smtp_env(ENVIRONMENT="development")
    del env["SMTP_CIFRADO"]
    del env["SMTP_PUERTO"]

    config = load_config(env).correo

    assert config.smtp_cifrado == "starttls"
    assert config.smtp_puerto == 587


_ERRORES = [
    ({"CORREO_MODO": "imap"}, "CORREO_MODO"),
    ({"CORREO_MODO": "carpeta"}, "CORREO_MODO"),
    ({"URL_PUBLICA": ""}, "URL_PUBLICA"),
    ({"URL_PUBLICA": "http://inventario.ejemplo.test"}, "URL_PUBLICA"),
    ({"URL_PUBLICA": "ftp://inventario.ejemplo.test"}, "URL_PUBLICA"),
    ({"URL_PUBLICA": "https://"}, "URL_PUBLICA"),
    ({"URL_PUBLICA": "https://u:p@inventario.ejemplo.test"}, "URL_PUBLICA"),
    ({"URL_PUBLICA": "https://inventario.ejemplo.test/?a=1"}, "URL_PUBLICA"),
    ({"URL_PUBLICA": "https://inventario.ejemplo.test/#x"}, "URL_PUBLICA"),
    ({"URL_PUBLICA": "https://inventario.ejemplo.test/a b"}, "URL_PUBLICA"),
    ({"URL_PUBLICA": "https://inventario.ejemplo.test\r\nX: y"}, "URL_PUBLICA"),
    # Host: solo letras, dígitos, «.» y «-», o IPv6 entre corchetes bien formada.
    ({"URL_PUBLICA": "https://[::1"}, "URL_PUBLICA"),
    ({"URL_PUBLICA": "https://[::1]x"}, "URL_PUBLICA"),
    ({"URL_PUBLICA": "https://[no-es-ipv6]"}, "URL_PUBLICA"),
    ({"URL_PUBLICA": "https://[fe80::1%25eth0]"}, "URL_PUBLICA"),
    ({"URL_PUBLICA": "https://evil.com\\good.com"}, "URL_PUBLICA"),
    ({"URL_PUBLICA": "https://a b.com"}, "URL_PUBLICA"),
    ({"URL_PUBLICA": "https://user@inventario.ejemplo.test"}, "URL_PUBLICA"),
    ({"URL_PUBLICA": "https://:443"}, "URL_PUBLICA"),
    ({"URL_PUBLICA": "https:///ruta"}, "URL_PUBLICA"),
    ({"URL_PUBLICA": "https://inv_entario.ejemplo.test"}, "URL_PUBLICA"),
    ({"URL_PUBLICA": "https://inv%41ntario.ejemplo.test"}, "URL_PUBLICA"),
    ({"URL_PUBLICA": "https://-inventario.ejemplo.test"}, "URL_PUBLICA"),
    ({"URL_PUBLICA": "https://inventario.ejemplo.test:80:90"}, "URL_PUBLICA"),
    ({"SMTP_PUERTO": "quinientos"}, "SMTP_PUERTO"),
    ({"SMTP_PUERTO": "0"}, "SMTP_PUERTO"),
    ({"SMTP_PUERTO": "70000"}, "SMTP_PUERTO"),
    ({"SMTP_CIFRADO": "ninguno"}, "SMTP_CIFRADO"),
    ({"SMTP_CIFRADO": ""}, "SMTP_CIFRADO"),
    ({"SMTP_HOST": ""}, "SMTP_HOST"),
    ({"CORREO_REMITENTE": ""}, "CORREO_REMITENTE"),
    ({"CORREO_REMITENTE": "sin-arroba"}, "CORREO_REMITENTE"),
    ({"CORREO_REMITENTE": "a@ejemplo.test\r\nBcc: b@ejemplo.test"}, "CORREO_REMITENTE"),
    ({"SMTP_CLAVE": ""}, "SMTP_CLAVE"),
    ({"SMTP_USUARIO": ""}, "SMTP_USUARIO"),
]


@pytest.mark.parametrize(("cambios", "variable"), _ERRORES)
def test_invalid_config_fails_naming_the_variable_without_secrets(cambios, variable):
    with pytest.raises(CorreoNoValido) as info:
        load_config(_smtp_env(**cambios))

    mensaje = str(info.value)
    assert variable in mensaje
    _assert_sin_secretos(mensaje)
    for valor in cambios.values():
        # «carpeta» es un literal del mensaje (modo admitido), no un eco del valor.
        if valor.strip() and valor != "carpeta":
            assert valor not in mensaje


@pytest.mark.parametrize(
    "url",
    [
        "https://inventario.ejemplo.test",
        "https://inventario.ejemplo.test:8443/app",
        "https://[::1]:8443",
        "https://[2001:db8::1]",
        "https://127.0.0.1",
    ],
)
def test_well_formed_public_urls_are_accepted(url):
    assert load_config(_smtp_env(URL_PUBLICA=url)).correo.url_publica == url


@pytest.mark.parametrize("ambiente", ["production", "staging"])
def test_folder_mode_outside_development_is_rejected(ambiente, tmp_path):
    env = {
        **BASE_ENV,
        "ENVIRONMENT": ambiente,
        "CORREO_MODO": "carpeta",
        "CORREO_CARPETA": str(tmp_path),
        "URL_PUBLICA": URL,
    }

    with pytest.raises(CorreoNoValido, match="CORREO_MODO"):
        load_config(env)
    with pytest.raises(CorreoNoValido, match="CORREO_MODO"):
        Config(
            database_url=OFFLINE_DB,
            secret_key="s" * 40,
            environment=ambiente,
            correo=_carpeta_config(tmp_path),
        )


def test_http_public_url_outside_development_is_rejected_by_config_too():
    with pytest.raises(CorreoNoValido, match="URL_PUBLICA"):
        Config(
            database_url=OFFLINE_DB,
            secret_key="s" * 40,
            environment="production",
            correo=_smtp_config(url_publica="http://inventario.ejemplo.test"),
        )


@pytest.mark.parametrize(
    "cambios",
    [
        {"modo": "imap"},
        {"smtp_cifrado": None},
        {"smtp_cifrado": "plano"},
        {"smtp_puerto": 0},
        {"smtp_host": None},
        {"url_publica": "https://inventario.ejemplo.test/#x"},
    ],
)
def test_config_object_validates_itself(cambios):
    with pytest.raises(CorreoNoValido):
        _smtp_config(**cambios)


def test_repr_and_str_hide_credentials_and_host():
    config = load_config(_smtp_env())

    for texto in (repr(config), str(config), repr(config.correo), str(config.correo)):
        assert CLAVE_SMTP not in texto
        assert USUARIO_SMTP not in texto
        assert HOST_SMTP not in texto


# --- Arranque (R7) ----------------------------------------------------------------------


def test_app_without_mode_starts_disabled_and_warns_once(caplog):
    config = Config(database_url=OFFLINE_DB, secret_key="s" * 40, environment="development")

    with caplog.at_level(logging.WARNING):
        app = create_app(config)

    assert correo_activo(app) is False
    avisos = [r for r in caplog.records if "CORREO_MODO" in r.getMessage()]
    assert len(avisos) == 1
    assert "desactivada" in avisos[0].getMessage()


def test_disabled_mail_accepts_calls_and_does_nothing(tmp_path, caplog):
    correo = crear(None)

    with caplog.at_level(logging.DEBUG):
        assert correo.enviar_recuperacion(DESTINO, _token()) is None
        assert correo.esperar(1) is True

    assert correo.activo is False
    assert list(tmp_path.iterdir()) == []


def test_app_with_folder_mode_exposes_active_mail(tmp_path):
    config = Config(
        database_url=OFFLINE_DB,
        secret_key="s" * 40,
        environment="development",
        correo=_carpeta_config(tmp_path),
    )

    app = create_app(config)

    assert correo_activo(app) is True
    assert get_correo(app) is app.extensions[EXTENSION_KEY]
    assert isinstance(get_correo(app).transporte, Buzon)


def test_app_with_smtp_mode_uses_smtp_transport():
    config = Config(
        database_url=OFFLINE_DB,
        secret_key="s" * 40,
        environment="production",
        correo=_smtp_config(),
    )

    app = create_app(config)

    assert isinstance(get_correo(app).transporte, ServidorSmtp)


# --- Buzón en carpeta (A14) -------------------------------------------------------------


def test_folder_mode_writes_utf8_eml_with_link_and_safe_name(tmp_path, caplog):
    correo = crear(_carpeta_config(tmp_path))
    token = _token()

    with caplog.at_level(logging.DEBUG):
        correo.enviar_recuperacion(DESTINO, token)
        assert correo.esperar(5)

    archivos = list(tmp_path.iterdir())
    assert len(archivos) == 1
    archivo = archivos[0]
    assert archivo.suffix == ".eml"
    assert token not in archivo.name
    assert "persona" not in archivo.name
    assert "ejemplo" not in archivo.name
    mensaje = email.message_from_bytes(archivo.read_bytes(), policy=email.policy.default)
    assert mensaje["Subject"] == ASUNTO
    assert mensaje["To"] == DESTINO
    assert mensaje["From"] == REMITENTE
    texto = mensaje.get_body(preferencelist=("plain",))
    assert texto.get_content_charset() == "utf-8"
    assert f"http://localhost:5173/restablecer#{token}" in texto.get_content()
    assert mensaje.get_body(preferencelist=("html",)) is not None
    _assert_sin_secretos(_log_text(caplog), token)


def test_mailbox_creates_folder_and_never_overwrites(tmp_path):
    carpeta = tmp_path / "anidada" / ".buzon"
    buzon = Buzon(carpeta)
    mensaje = componer_recuperacion(REMITENTE, DESTINO, URL, _token())

    primero = buzon.entregar(mensaje)
    segundo = buzon.entregar(mensaje)

    assert primero != segundo
    assert primero.parent == carpeta.resolve()
    assert len(list(carpeta.iterdir())) == 2


@pytest.mark.skipif(sys.platform == "win32", reason="Windows no aplica permisos POSIX")
def test_mailbox_file_is_private_to_the_owner(tmp_path):
    ruta = Buzon(tmp_path).entregar(componer_recuperacion(REMITENTE, DESTINO, URL, _token()))

    assert stat.S_IMODE(ruta.stat().st_mode) == 0o600


def test_mailbox_folder_is_created_private_to_the_owner(tmp_path):
    """B-3 de T3 (T8): la carpeta del buzón se crea con ``0o700`` (en Windows se pide igual)."""
    carpeta = tmp_path / "nueva" / ".buzon"
    original = Path.mkdir
    llamadas = []

    def espiar(self, *args, **kwargs):
        llamadas.append((Path(self), kwargs.get("mode", args[0] if args else None)))
        return original(self, *args, **kwargs)

    with mock.patch.object(Path, "mkdir", espiar):
        Buzon(carpeta).entregar(componer_recuperacion(REMITENTE, DESTINO, URL, _token()))

    assert (carpeta.resolve(), 0o700) in llamadas
    if sys.platform != "win32":
        assert stat.S_IMODE(carpeta.stat().st_mode) == 0o700


def test_mailbox_folder_is_excluded_from_the_docker_build_context():
    """B-4 de T3 (T8): el Dockerfile de desarrollo hace ``COPY . .``."""
    dockerignore = Path(__file__).resolve().parents[1] / ".dockerignore"
    lineas = {linea.strip() for linea in dockerignore.read_text(encoding="utf-8").splitlines()}

    assert ".buzon/" in lineas


# --- SMTP (R7, A13) ---------------------------------------------------------------------


def _smtp_mock():
    servidor = mock.MagicMock()
    servidor.__enter__.return_value = servidor
    servidor.__exit__.return_value = False
    return servidor


def test_starttls_uses_verified_tls_timeout_and_configured_credentials():
    servidor = _smtp_mock()
    mensaje = componer_recuperacion(REMITENTE, DESTINO, URL, _token())

    with (
        mock.patch.object(smtplib, "SMTP", return_value=servidor) as clase,
        mock.patch.object(smtplib, "SMTP_SSL") as clase_ssl,
    ):
        ServidorSmtp(_smtp_config()).entregar(mensaje)

    clase.assert_called_once()
    clase_ssl.assert_not_called()
    kwargs = clase.call_args.kwargs
    # Se construye sin conectar (M-1: el vigilante del plazo total ya ve el socket) y luego
    # se conecta al host y puerto configurados.
    assert not clase.call_args.args and "host" not in kwargs
    servidor.connect.assert_called_once_with(HOST_SMTP, 587)
    assert kwargs["timeout"] == SMTP_TIMEOUT_SEGUNDOS == 10
    servidor.starttls.assert_called_once()
    contexto = servidor.starttls.call_args.kwargs["context"]
    assert isinstance(contexto, ssl.SSLContext)
    assert contexto.verify_mode == ssl.CERT_REQUIRED
    assert contexto.check_hostname is True
    # B-2 de T3 (T8): TLS 1.2 como mínimo, explícito.
    assert contexto.minimum_version == ssl.TLSVersion.TLSv1_2
    servidor.login.assert_called_once_with(USUARIO_SMTP, CLAVE_SMTP)
    servidor.send_message.assert_called_once_with(mensaje)
    nombres = [c[0] for c in servidor.method_calls]
    assert nombres.index("starttls") < nombres.index("login") < nombres.index("send_message")


def test_ssl_mode_uses_implicit_tls_with_verified_context():
    servidor = _smtp_mock()
    mensaje = componer_recuperacion(REMITENTE, DESTINO, URL, _token())

    with (
        mock.patch.object(smtplib, "SMTP") as clase,
        mock.patch.object(smtplib, "SMTP_SSL", return_value=servidor) as clase_ssl,
    ):
        ServidorSmtp(_smtp_config(smtp_cifrado="ssl", smtp_puerto=465)).entregar(mensaje)

    clase.assert_not_called()
    kwargs = clase_ssl.call_args.kwargs
    assert not clase_ssl.call_args.args and "host" not in kwargs
    servidor.connect.assert_called_once_with(HOST_SMTP, 465)
    assert kwargs["timeout"] == 10
    assert kwargs["context"].verify_mode == ssl.CERT_REQUIRED
    assert kwargs["context"].check_hostname is True
    assert kwargs["context"].minimum_version == ssl.TLSVersion.TLSv1_2
    servidor.starttls.assert_not_called()
    servidor.login.assert_called_once_with(USUARIO_SMTP, CLAVE_SMTP)
    servidor.send_message.assert_called_once_with(mensaje)


@pytest.mark.parametrize("cifrado", ["starttls", "ssl"])
def test_ehlo_name_is_the_sender_domain_never_the_machine_name(cifrado):
    servidor = _smtp_mock()
    mensaje = componer_recuperacion(REMITENTE, DESTINO, URL, _token())

    with (
        mock.patch.object(smtplib, "SMTP", return_value=servidor) as clase,
        mock.patch.object(smtplib, "SMTP_SSL", return_value=servidor) as clase_ssl,
        mock.patch.object(socket, "getfqdn", side_effect=AssertionError("sin getfqdn")),
    ):
        ServidorSmtp(_smtp_config(smtp_cifrado=cifrado)).entregar(mensaje)

    usada = clase_ssl if cifrado == "ssl" else clase
    assert usada.call_args.kwargs["local_hostname"] == "ejemplo.test"


@pytest.mark.parametrize(
    ("remitente", "nombre"),
    [
        (REMITENTE, "ejemplo.test"),
        ("no-responder@Correo.Ejemplo.test", "Correo.Ejemplo.test"),
        ("sin-dominio", "localhost"),
        ("", "localhost"),
    ],
)
def test_ehlo_name_falls_back_to_localhost(remitente, nombre):
    assert nombre_ehlo(remitente) == nombre


def test_without_credentials_does_not_login():
    servidor = _smtp_mock()
    mensaje = componer_recuperacion(REMITENTE, DESTINO, URL, _token())

    with mock.patch.object(smtplib, "SMTP", return_value=servidor):
        ServidorSmtp(_smtp_config(smtp_usuario=None, smtp_clave=None)).entregar(mensaje)

    servidor.login.assert_not_called()
    servidor.send_message.assert_called_once()


def test_server_without_starttls_never_falls_back_to_plain_text():
    servidor = _smtp_mock()
    servidor.starttls.side_effect = smtplib.SMTPNotSupportedError("sin STARTTLS")
    mensaje = componer_recuperacion(REMITENTE, DESTINO, URL, _token())

    with mock.patch.object(smtplib, "SMTP", return_value=servidor):
        with pytest.raises(smtplib.SMTPNotSupportedError):
            ServidorSmtp(_smtp_config()).entregar(mensaje)

    servidor.login.assert_not_called()
    servidor.send_message.assert_not_called()


_FALLOS_SMTP = [
    ConnectionRefusedError(f"conexión rechazada {HOST_SMTP}"),
    TimeoutError(f"tiempo agotado {HOST_SMTP}"),
    smtplib.SMTPNotSupportedError("STARTTLS extension not supported by server."),
    ssl.SSLCertVerificationError(f"certificado inválido para {HOST_SMTP}"),
    smtplib.SMTPAuthenticationError(535, f"auth {USUARIO_SMTP} {CLAVE_SMTP}".encode()),
    smtplib.SMTPRecipientsRefused({DESTINO: (550, b"no existe")}),
    smtplib.SMTPServerDisconnected("desconectado"),
]


@pytest.mark.parametrize("fallo", _FALLOS_SMTP, ids=lambda e: type(e).__name__)
def test_smtp_failure_never_propagates_nor_retries_nor_leaks(fallo, caplog):
    servidor = _smtp_mock()
    servidor.send_message.side_effect = fallo
    correo = Correo(_smtp_config())
    token = _token()

    with (
        caplog.at_level(logging.DEBUG),
        mock.patch.object(smtplib, "SMTP", return_value=servidor) as clase,
    ):
        assert correo.enviar_recuperacion(DESTINO, token) is None
        assert correo.esperar(5)

    assert clase.call_count == 1
    assert servidor.send_message.call_count == 1
    texto = _log_text(caplog)
    _assert_sin_secretos(texto, token)
    assert type(fallo).__name__ in texto
    fallos = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert len(fallos) == 1
    assert fallos[0].exc_info is None


def test_connection_refused_against_real_closed_port(caplog):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        puerto = sock.getsockname()[1]
    correo = Correo(_smtp_config(smtp_host="127.0.0.1", smtp_puerto=puerto))
    token = _token()

    with caplog.at_level(logging.DEBUG):
        correo.enviar_recuperacion(DESTINO, token)
        assert correo.esperar(15)

    texto = _log_text(caplog)
    assert "ConnectionRefusedError" in texto or "OSError" in texto
    _assert_sin_secretos(texto, token)
    assert str(puerto) not in texto


def test_silent_server_times_out_without_retry(caplog):
    with socket.socket() as servidor:
        servidor.bind(("127.0.0.1", 0))
        servidor.listen(5)
        puerto = servidor.getsockname()[1]
        transporte = ServidorSmtp(
            _smtp_config(smtp_host="127.0.0.1", smtp_puerto=puerto), timeout=0.3
        )
        correo = Correo(_smtp_config(), transporte=transporte)
        token = _token()

        with caplog.at_level(logging.DEBUG):
            inicio = time.monotonic()
            correo.enviar_recuperacion(DESTINO, token)
            # Margen amplio frente a la espera simulada (0,3 s): evita intermitencias.
            assert time.monotonic() - inicio < 1
            assert correo.esperar(10)
            assert time.monotonic() - inicio >= 0.3

        # Una sola conexión: sin reintentos.
        servidor.settimeout(0.2)
        conexiones = 0
        while True:
            try:
                aceptada, _ = servidor.accept()
            except TimeoutError:
                break
            aceptada.close()
            conexiones += 1
        assert conexiones == 1

    texto = _log_text(caplog)
    # ``smtplib`` convierte el tiempo agotado del saludo en ``SMTPServerDisconnected``.
    assert "tipo=SMTPServerDisconnected" in texto or "tipo=TimeoutError" in texto
    _assert_sin_secretos(texto, token)


def test_total_deadline_is_45_seconds():
    assert SMTP_PLAZO_TOTAL_SEGUNDOS == 45


def test_dribbling_server_is_cut_by_the_total_deadline(caplog):
    """M-1 de T3 (T8): un servidor que gotea (nunca agota el timeout por operación) se corta
    al vencer el plazo total, con el socket cerrado y sin reintentos."""
    parar = threading.Event()
    with socket.socket() as oyente:
        oyente.bind(("127.0.0.1", 0))
        oyente.listen(1)
        puerto = oyente.getsockname()[1]

        def gotear():
            conexion, _ = oyente.accept()
            with conexion:
                # Saludo multilínea que nunca termina: una línea cada 50 ms.
                while not parar.is_set():
                    try:
                        conexion.sendall(b"220-sigo aqui\r\n")
                    except OSError:
                        return
                    time.sleep(0.05)

        hilo = threading.Thread(target=gotear, daemon=True)
        hilo.start()
        transporte = ServidorSmtp(
            _smtp_config(smtp_host="127.0.0.1", smtp_puerto=puerto), timeout=2, plazo_total=0.5
        )
        correo = Correo(_smtp_config(), transporte=transporte)
        token = _token()
        try:
            with caplog.at_level(logging.DEBUG):
                inicio = time.monotonic()
                correo.enviar_recuperacion(DESTINO, token)
                assert correo.esperar(10)
                duracion = time.monotonic() - inicio
        finally:
            parar.set()
            hilo.join(5)

    assert 0.5 <= duracion < 2.5
    texto = _log_text(caplog)
    assert "tipo=TimeoutError" in texto
    _assert_sin_secretos(texto, token)
    assert str(puerto) not in texto


def test_late_watchdog_cut_after_exit_touches_nothing():
    """Hallazgo de seguridad de T8: un ``_cortar`` que llega después de ``__exit__`` (el
    temporizador ya disparó y su hilo va tarde) no toca el socket, que podría ser ya un
    descriptor reutilizado, ni marca la entrega como vencida."""
    izquierda, derecha = socket.socketpair()
    with izquierda, derecha:
        conexion = mock.Mock(spec=smtplib.SMTP)
        conexion.sock = izquierda
        with _Vigilante(conexion, plazo=60) as vigilante:
            pass
        with mock.patch.object(socket.socket, "shutdown") as cortar:
            vigilante._cortar()
        cortar.assert_not_called()
        assert vigilante.vencido is False
        vigilante.comprobar()
        # El socket sigue sano en los dos sentidos.
        izquierda.sendall(b"ok")
        assert derecha.recv(2) == b"ok"


def test_exit_waits_for_a_watchdog_cut_in_progress():
    """``__exit__`` no vuelve mientras un ``_cortar`` está a mitad: comparten el candado."""
    conexion = mock.Mock(spec=smtplib.SMTP)
    dentro = threading.Event()
    soltar = threading.Event()
    salio = threading.Event()
    vigilante = _Vigilante(conexion, plazo=60)
    vigilante.__enter__()

    def sock_lento():
        dentro.set()
        soltar.wait(5)
        return None

    type(conexion).sock = mock.PropertyMock(side_effect=sock_lento)
    cortador = threading.Thread(target=vigilante._cortar, daemon=True)
    cortador.start()
    assert dentro.wait(5)

    def salir():
        vigilante.__exit__(None, None, None)
        salio.set()

    saliendo = threading.Thread(target=salir, daemon=True)
    saliendo.start()
    assert not salio.wait(0.2)
    soltar.set()
    cortador.join(5)
    assert salio.wait(5)
    saliendo.join(5)


# --- TLS real contra un servidor SMTP falso (R7, A13) -----------------------------------
#
# Sockets reales en 127.0.0.1 y un certificado autofirmado generado en tiempo de prueba
# (``cryptography`` ya está instalada como dependencia de ``moto``, grupo dev). Ningún
# certificado ni clave se versiona: viven en ``tmp_path`` de la sesión de pruebas.

_COMANDOS_TRAS_TLS = ("AUTH", "MAIL", "RCPT", "DATA")


def _generar_certificado(carpeta: Path, nombre: str, con_ip: bool) -> tuple[Path, Path, str]:
    """Certificado autofirmado EC P-256 válido 1 día; devuelve (cert, clave, PEM)."""
    import datetime
    import ipaddress

    x509 = pytest.importorskip("cryptography.x509")
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    clave = ec.generate_private_key(ec.SECP256R1())
    sujeto = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "smtp-falso.invalid")])
    nombres: list[x509.GeneralName] = [x509.DNSName("smtp-falso.invalid")]
    if con_ip:
        nombres.append(x509.IPAddress(ipaddress.ip_address("127.0.0.1")))
    ahora = datetime.datetime.now(datetime.UTC)
    certificado = (
        x509.CertificateBuilder()
        .subject_name(sujeto)
        .issuer_name(sujeto)
        .public_key(clave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(ahora - datetime.timedelta(minutes=5))
        .not_valid_after(ahora + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName(nombres), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(clave, hashes.SHA256())
    )
    pem = certificado.public_bytes(serialization.Encoding.PEM).decode("ascii")
    ruta_cert = carpeta / f"{nombre}.pem"
    ruta_clave = carpeta / f"{nombre}.key"
    ruta_cert.write_text(pem, encoding="ascii")
    ruta_clave.write_bytes(
        clave.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return ruta_cert, ruta_clave, pem


@pytest.fixture(scope="module")
def certificados(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("tls-smtp-falso")
    return {
        "ip": _generar_certificado(carpeta, "ip", con_ip=True),
        "otro_nombre": _generar_certificado(carpeta, "otro-nombre", con_ip=False),
    }


def _contexto_servidor(certificado) -> ssl.SSLContext:
    ruta_cert, ruta_clave, _ = certificado
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    contexto.load_cert_chain(ruta_cert, ruta_clave)
    return contexto


class _SmtpFalso:
    """Servidor SMTP mínimo en un hilo: una conexión, registra los verbos recibidos.

    ``starttls``: anuncia STARTTLS antes del TLS. ``implicito``: TLS desde el saludo
    (SSL implícito). Sin ``contexto`` no hay TLS posible (texto plano).
    """

    def __init__(self, contexto=None, starttls=True, implicito=False):
        self.contexto = contexto
        self.starttls = starttls and contexto is not None
        self.implicito = implicito
        self.comandos: list[str] = []
        self.ehlo: list[str] = []
        self.verbos_en_tls: list[str] = []
        self.datos = b""
        self.error: str | None = None
        self._tls = False
        self._oyente = socket.socket()
        self._oyente.bind(("127.0.0.1", 0))
        self._oyente.listen(1)
        self._oyente.settimeout(10)
        self.puerto = self._oyente.getsockname()[1]
        self._hilo = threading.Thread(target=self._atender, daemon=True)
        self._hilo.start()

    def cerrar(self) -> None:
        self._hilo.join(10)
        self._oyente.close()

    def _atender(self) -> None:
        try:
            conexion, _ = self._oyente.accept()
        except OSError as exc:
            self.error = type(exc).__name__
            return
        conexion.settimeout(10)
        self._conexion = conexion
        try:
            if self.implicito:
                self._conexion = self.contexto.wrap_socket(conexion, server_side=True)
                self._tls = True
            self._dialogo()
        except Exception as exc:  # se registra para la aserción
            self.error = type(exc).__name__
        finally:
            self._conexion.close()

    def _enviar(self, texto: str) -> None:
        self._conexion.sendall(texto.encode("ascii"))

    def _dialogo(self) -> None:
        lector = self._conexion.makefile("rb")
        self._enviar("220 smtp-falso ESMTP\r\n")
        while True:
            linea = lector.readline()
            if not linea:
                return
            texto = linea.decode("ascii", "replace").rstrip("\r\n")
            verbo, _, argumento = texto.partition(" ")
            verbo = verbo.upper()
            self.comandos.append(verbo)
            if self._tls:
                self.verbos_en_tls.append(verbo)
            if verbo in ("EHLO", "HELO"):
                self.ehlo.append(argumento)
                extensiones = ["smtp-falso"]
                if self.starttls and not self._tls:
                    extensiones.append("STARTTLS")
                extensiones.append("AUTH PLAIN")
                lineas = [f"250-{e}\r\n" for e in extensiones[:-1]]
                self._enviar("".join(lineas) + f"250 {extensiones[-1]}\r\n")
            elif verbo == "STARTTLS" and self.starttls and not self._tls:
                self._enviar("220 listo para TLS\r\n")
                lector.close()
                self._conexion = self.contexto.wrap_socket(self._conexion, server_side=True)
                self._tls = True
                lector = self._conexion.makefile("rb")
            elif verbo == "AUTH":
                self._enviar("235 autenticado\r\n")
            elif verbo in ("MAIL", "RCPT", "RSET", "NOOP"):
                self._enviar("250 ok\r\n")
            elif verbo == "DATA":
                self._enviar("354 adelante\r\n")
                partes = []
                while (parte := lector.readline()) and parte != b".\r\n":
                    partes.append(parte)
                self.datos = b"".join(partes)
                self._enviar("250 recibido\r\n")
            elif verbo == "QUIT":
                self._enviar("221 adios\r\n")
                return
            else:
                self._enviar("502 no implementado\r\n")


def _confiar_en(pem: str):
    """Parchea solo en la prueba el contexto por defecto para confiar además en ``pem``.

    La verificación sigue activa (``CERT_REQUIRED`` y nombre): solo se amplía la lista
    de autoridades de confianza.
    """
    original = ssl.create_default_context

    def contexto(*args, **kwargs):
        resultado = original(*args, **kwargs)
        resultado.load_verify_locations(cadata=pem)
        return resultado

    return mock.patch.object(ssl, "create_default_context", contexto)


def _entregar_a(puerto: int, cifrado: str) -> EmailMessage:
    mensaje = componer_recuperacion(REMITENTE, DESTINO, URL, _token())
    config = _smtp_config(smtp_host="127.0.0.1", smtp_puerto=puerto, smtp_cifrado=cifrado)
    ServidorSmtp(config, timeout=5).entregar(mensaje)
    return mensaje


def test_real_starttls_rejects_an_untrusted_certificate(certificados):
    servidor = _SmtpFalso(_contexto_servidor(certificados["ip"]))
    try:
        with pytest.raises(ssl.SSLCertVerificationError):
            _entregar_a(servidor.puerto, "starttls")
    finally:
        servidor.cerrar()

    assert servidor.comandos[:2] == ["EHLO", "STARTTLS"]
    assert not set(servidor.comandos) & set(_COMANDOS_TRAS_TLS)
    assert servidor.datos == b""


def test_real_starttls_rejects_a_trusted_certificate_for_another_name(certificados):
    _, _, pem = certificados["otro_nombre"]
    servidor = _SmtpFalso(_contexto_servidor(certificados["otro_nombre"]))
    try:
        with _confiar_en(pem), pytest.raises(ssl.SSLCertVerificationError):
            _entregar_a(servidor.puerto, "starttls")
    finally:
        servidor.cerrar()

    assert not set(servidor.comandos) & set(_COMANDOS_TRAS_TLS)


def test_real_starttls_delivers_with_a_trusted_certificate(certificados):
    _, _, pem = certificados["ip"]
    servidor = _SmtpFalso(_contexto_servidor(certificados["ip"]))
    try:
        with _confiar_en(pem):
            _entregar_a(servidor.puerto, "starttls")
    finally:
        servidor.cerrar()

    assert servidor.error is None
    assert servidor.comandos == [
        "EHLO",
        "STARTTLS",
        "EHLO",
        "AUTH",
        "MAIL",
        "RCPT",
        "DATA",
        "QUIT",
    ]
    # Credenciales, remitente y mensaje viajan solo dentro del TLS.
    assert servidor.verbos_en_tls == ["EHLO", "AUTH", "MAIL", "RCPT", "DATA", "QUIT"]
    assert servidor.ehlo == ["ejemplo.test", "ejemplo.test"]
    assert b"Subject:" in servidor.datos


def test_real_plain_server_without_starttls_never_falls_back(certificados):
    servidor = _SmtpFalso(contexto=None)
    try:
        with pytest.raises(smtplib.SMTPNotSupportedError):
            _entregar_a(servidor.puerto, "starttls")
    finally:
        servidor.cerrar()

    assert "STARTTLS" not in servidor.comandos
    assert not set(servidor.comandos) & set(_COMANDOS_TRAS_TLS)
    assert servidor.datos == b""


def test_real_implicit_ssl_delivers_with_a_trusted_certificate(certificados):
    _, _, pem = certificados["ip"]
    servidor = _SmtpFalso(_contexto_servidor(certificados["ip"]), implicito=True)
    try:
        with _confiar_en(pem):
            _entregar_a(servidor.puerto, "ssl")
    finally:
        servidor.cerrar()

    assert servidor.error is None
    assert servidor.verbos_en_tls == ["EHLO", "AUTH", "MAIL", "RCPT", "DATA", "QUIT"]
    assert servidor.ehlo == ["ejemplo.test"]


def test_real_implicit_ssl_rejects_an_untrusted_certificate(certificados):
    servidor = _SmtpFalso(_contexto_servidor(certificados["ip"]), implicito=True)
    try:
        with pytest.raises(ssl.SSLCertVerificationError):
            _entregar_a(servidor.puerto, "ssl")
    finally:
        servidor.cerrar()

    assert servidor.comandos == []
    assert servidor.datos == b""


def test_real_implicit_ssl_rejects_a_trusted_certificate_for_another_name(certificados):
    _, _, pem = certificados["otro_nombre"]
    servidor = _SmtpFalso(_contexto_servidor(certificados["otro_nombre"]), implicito=True)
    try:
        with _confiar_en(pem), pytest.raises(ssl.SSLCertVerificationError):
            _entregar_a(servidor.puerto, "ssl")
    finally:
        servidor.cerrar()

    assert servidor.comandos == []
    assert servidor.datos == b""


# --- Hilo y semáforo (R8) ---------------------------------------------------------------


def test_header_injection_in_thread_sends_nothing_and_logs_only_the_type(caplog):
    registro = _Registro()
    correo = Correo(_smtp_config(), transporte=registro)
    destino = f"{DESTINO}\r\nBcc: otra@ejemplo.test"
    token = _token()

    with caplog.at_level(logging.DEBUG):
        correo.enviar_recuperacion(destino, token)
        assert correo.esperar(5)

    assert registro.mensajes == []
    texto = _log_text(caplog)
    assert "DestinoNoValido" in texto
    _assert_sin_secretos(texto, token)
    assert "otra@" not in texto


def test_call_returns_before_a_slow_delivery_finishes():
    bloqueo = threading.Event()
    registro = _Registro(bloqueo=bloqueo)
    correo = Correo(_smtp_config(), transporte=registro)

    inicio = time.monotonic()
    correo.enviar_recuperacion(DESTINO, _token())
    duracion = time.monotonic() - inicio

    assert duracion < 0.5
    assert registro.mensajes == []
    assert correo.esperar(0.05) is False
    bloqueo.set()
    assert correo.esperar(5) is True
    assert len(registro.mensajes) == 1


def test_semaphore_caps_concurrency_and_discards_overflow(caplog):
    bloqueo = threading.Event()
    registro = _Registro(bloqueo=bloqueo)
    correo = Correo(_smtp_config(), transporte=registro)
    tokens = [_token() for _ in range(MAX_CONCURRENCIA + 2)]

    with caplog.at_level(logging.DEBUG):
        for token in tokens:
            correo.enviar_recuperacion(DESTINO, token)
        descartes = [r for r in caplog.records if "sin cupo" in r.getMessage()]
        assert len(descartes) == 2
        bloqueo.set()
        assert correo.esperar(5)

    assert MAX_CONCURRENCIA == 4
    # M-1 (T8): contador de descartes, también en el log.
    assert correo.descartados == 2
    assert "descartados=2" in descartes[-1].getMessage()
    assert registro.maximo <= MAX_CONCURRENCIA
    assert len(registro.mensajes) == MAX_CONCURRENCIA
    texto = _log_text(caplog)
    for token in tokens:
        _assert_sin_secretos(texto, token)

    # El cupo se libera: un envío posterior vuelve a salir.
    correo.enviar_recuperacion(DESTINO, _token())
    assert correo.esperar(5)
    assert len(registro.mensajes) == MAX_CONCURRENCIA + 1


def test_slot_is_released_after_a_failure():
    registro = _Registro(falla=RuntimeError("falla"))
    correo = Correo(_smtp_config(), transporte=registro, max_concurrencia=1)

    for _ in range(3):
        correo.enviar_recuperacion(DESTINO, _token())
        assert correo.esperar(5)

    registro.falla = None
    correo.enviar_recuperacion(DESTINO, _token())
    assert correo.esperar(5)
    assert len(registro.mensajes) == 1


def test_thread_start_failure_releases_slot_and_does_not_propagate(caplog):
    registro = _Registro()
    correo = Correo(_smtp_config(), transporte=registro, max_concurrencia=1)

    with (
        caplog.at_level(logging.DEBUG),
        mock.patch.object(threading.Thread, "start", side_effect=RuntimeError("sin hilos")),
    ):
        assert correo.enviar_recuperacion(DESTINO, _token()) is None

    assert "RuntimeError" in _log_text(caplog)
    correo.enviar_recuperacion(DESTINO, _token())
    assert correo.esperar(5)
    assert len(registro.mensajes) == 1


def test_explicit_request_id_is_used_outside_a_request(caplog):
    """I1 de T4 (T8): la ruta programa el envío al cerrar la respuesta, sin contexto de
    petición, y pasa el ``request_id`` capturado antes."""
    correo = Correo(_smtp_config(), transporte=_Registro(falla=OSError("x")))

    with caplog.at_level(logging.DEBUG):
        correo.enviar_recuperacion(DESTINO, _token(), request_id="rid-sintetico-14")
        assert correo.esperar(5)

    assert "request_id=rid-sintetico-14" in _log_text(caplog)


def test_threads_are_daemon_and_log_the_request_id(caplog):
    registro = _Registro(falla=OSError("x"))
    correo = Correo(_smtp_config(), transporte=registro)
    app = create_app(Config(database_url=OFFLINE_DB, secret_key="s" * 40, environment="test"))
    hilos = []
    original = threading.Thread.start

    def espiar(self):
        hilos.append(self)
        return original(self)

    with (
        caplog.at_level(logging.DEBUG),
        mock.patch.object(threading.Thread, "start", espiar),
        app.test_request_context("/"),
    ):
        from app.errors import current_request_id

        request_id = current_request_id()
        correo.enviar_recuperacion(DESTINO, _token())
        assert correo.esperar(5)

    assert hilos and all(h.daemon for h in hilos)
    assert request_id in _log_text(caplog)


# --- docker-compose.yml (hallazgo de la T9) ------------------------------------------

VARIABLES_CORREO = (
    "CORREO_MODO",
    "CORREO_REMITENTE",
    "CORREO_CARPETA",
    "URL_PUBLICA",
    "SMTP_HOST",
    "SMTP_CIFRADO",
    "SMTP_PUERTO",
    "SMTP_USUARIO",
    "SMTP_CLAVE",
)


@pytest.mark.parametrize("name", VARIABLES_CORREO)
def test_compose_passes_each_correo_variable_to_the_api(name):
    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text("utf-8")
    api = compose.split("\n  api:", 1)[1].split("\n    volumes:", 1)[0]
    environment = api.split("\n    environment:", 1)[1]

    # Opcional y sin valor literal: vacía en .env -> recuperación desactivada o valor
    # por defecto de app/correo/config.py. Nunca una credencial escrita en el compose.
    assert re.search(rf"^      {name}: \$\{{{name}:-\}}\s*$", environment, re.MULTILINE)


def test_all_correo_variables_empty_disable_recovery():
    # Es lo que recibe la API del compose cuando .env no las define (``${VAR:-}``).
    assert load_correo(dict.fromkeys(VARIABLES_CORREO, ""), "development") is None
