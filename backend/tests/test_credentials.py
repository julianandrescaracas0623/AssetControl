"""Credenciales y tokens (spec 002, T4; R12, R15, A10, A25; plan.md §2.2 y §6).

- Contraseñas: Argon2id con ``argon2-cffi``; política Q9 (10–128 caracteres y
  lista corta de comunes); verificación con hash simulado de los mismos
  parámetros cuando la cuenta no existe; una contraseña sobre el máximo se
  rechaza sin hashear.
- Tokens opacos (invitación y refresh): ``clave = sha256(token)`` en hex (lo
  que recibe la base) y doble hash ``sha256(sha256(token))`` en ``bytea`` (lo
  que guarda), igual que ``acceso.*`` (0004).
- JWT de acceso: ``HS256`` fijo, ``exp`` e ``iss`` obligatorios, clave derivada
  de ``SECRET_KEY`` con contexto propio; rechaza ``none`` y otros algoritmos.

Datos sintéticos; las contraseñas de prueba son literales ficticios.
"""

import base64
import hashlib
import hmac
import json
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta

import argon2
import jwt
import pytest

from app import create_app
from app.auth import credentials
from app.auth.credentials import (
    ACCESS_TOKEN_TTL,
    ARGON2_PARAMS,
    ARGON2_TEST_PARAMS,
    COMMON_PASSWORDS,
    JWT_ALGORITHM,
    JWT_ISSUER,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    InvalidAccessTokenError,
    PasswordPolicyError,
    Passwords,
    check_password_policy,
    decode_access_token,
    derive_key,
    encode_access_token,
    get_passwords,
    new_token,
    token_key,
    token_storage_hash,
)
from app.config import Config

SECRET = "clave-sintetica-de-prueba-con-mas-de-32-bytes"
OTHER_SECRET = "otra-clave-sintetica-de-prueba-de-mas-de-32-bytes"
USER = uuid.UUID("00000000-0000-4000-8000-0000000a0041")
TENANT = uuid.UUID("00000000-0000-4000-8000-00000000a004")
GOOD_PASSWORD = "caballo-bateria-grapa"


@pytest.fixture(scope="module")
def passwords() -> Passwords:
    return Passwords(ARGON2_TEST_PARAMS)


# --- Parámetros de Argon2id ----------------------------------------------------


def test_production_params_are_argon2id_with_a_published_minimum():
    # OWASP (Password Storage Cheat Sheet): Argon2id, m >= 19 MiB, t >= 2, p = 1.
    assert ARGON2_PARAMS.type is argon2.Type.ID
    assert ARGON2_PARAMS.memory_cost >= 19 * 1024
    assert ARGON2_PARAMS.time_cost >= 2
    assert ARGON2_PARAMS.parallelism >= 1
    assert ARGON2_PARAMS.hash_len >= 32
    assert ARGON2_PARAMS.salt_len >= 16


def test_test_params_are_argon2id_and_cheaper():
    assert ARGON2_TEST_PARAMS.type is argon2.Type.ID
    assert ARGON2_TEST_PARAMS.memory_cost < ARGON2_PARAMS.memory_cost


def test_hash_is_argon2id_with_the_configured_params(passwords):
    stored = passwords.hash(GOOD_PASSWORD)

    assert stored.startswith("$argon2id$")
    assert argon2.extract_parameters(stored) == ARGON2_TEST_PARAMS
    assert GOOD_PASSWORD not in stored


def test_production_hasher_uses_production_params():
    stored = Passwords(ARGON2_PARAMS).hash(GOOD_PASSWORD)

    assert argon2.extract_parameters(stored) == ARGON2_PARAMS


def test_two_hashes_of_the_same_password_differ(passwords):
    assert passwords.hash(GOOD_PASSWORD) != passwords.hash(GOOD_PASSWORD)


# --- Verificación y hash simulado (A10) ---------------------------------------


def test_verify_accepts_the_right_password_and_rejects_others(passwords):
    stored = passwords.hash(GOOD_PASSWORD)

    assert passwords.verify(stored, GOOD_PASSWORD) is True
    assert passwords.verify(stored, GOOD_PASSWORD + "x") is False
    assert passwords.verify(stored, "") is False


def test_verify_without_account_runs_the_dummy_hash_and_returns_false(passwords, monkeypatch):
    calls: list[str] = []
    real_verify = argon2.PasswordHasher.verify

    def spy(self, hash_, password):
        calls.append(hash_)
        return real_verify(self, hash_, password)

    monkeypatch.setattr(argon2.PasswordHasher, "verify", spy)

    assert passwords.verify(None, GOOD_PASSWORD) is False
    assert len(calls) == 1
    # El hash simulado tiene exactamente los mismos parámetros (mismo costo).
    assert argon2.extract_parameters(calls[0]) == ARGON2_TEST_PARAMS


def test_dummy_hash_never_authenticates_even_with_its_own_secret(passwords):
    # El secreto del hash simulado es aleatorio y no se conserva: nada lo verifica.
    for candidate in ("", GOOD_PASSWORD, "None", "null"):
        assert passwords.verify(None, candidate) is False


def test_dummy_hash_is_computed_once_at_startup(monkeypatch):
    calls: list[str] = []
    real_hash = argon2.PasswordHasher.hash

    def spy(self, password, *, salt=None):
        calls.append("hash")
        return real_hash(self, password, salt=salt)

    monkeypatch.setattr(argon2.PasswordHasher, "hash", spy)
    passwords = Passwords(ARGON2_TEST_PARAMS)
    assert calls == ["hash"]

    passwords.verify(None, GOOD_PASSWORD)
    passwords.verify(None, GOOD_PASSWORD)
    assert calls == ["hash"]


def test_verify_takes_comparable_time_with_and_without_account():
    # Parámetros de producción: el login sin cuenta cuesta lo mismo que con cuenta.
    production = Passwords(ARGON2_PARAMS)
    stored = production.hash(GOOD_PASSWORD)

    def elapsed(target) -> float:
        best = float("inf")
        for _ in range(3):
            start = time.perf_counter()
            production.verify(target, "contrasena-equivocada")
            best = min(best, time.perf_counter() - start)
        return best

    with_account, without_account = elapsed(stored), elapsed(None)
    assert without_account > with_account * 0.5
    assert without_account < with_account * 2


def test_verify_rejects_a_password_over_the_maximum_without_hashing(passwords, monkeypatch):
    stored = passwords.hash(GOOD_PASSWORD)

    def forbidden(*args, **kwargs):
        raise AssertionError("no debe hashear una contraseña sobre el máximo")

    monkeypatch.setattr(argon2.PasswordHasher, "verify", forbidden)
    too_long = "a" * (PASSWORD_MAX_LENGTH + 1)

    assert passwords.verify(stored, too_long) is False
    assert passwords.verify(None, too_long) is False


@pytest.mark.parametrize("value", [None, 123, b"bytes-de-prueba"])
def test_verify_rejects_non_text_passwords(passwords, value):
    assert passwords.verify(passwords.hash(GOOD_PASSWORD), value) is False


def test_verify_with_a_corrupt_stored_hash_returns_false(passwords):
    assert passwords.verify("no-es-un-hash", GOOD_PASSWORD) is False
    assert passwords.verify("", GOOD_PASSWORD) is False


# --- Política de contraseña (Q9) -----------------------------------------------


def test_length_limits_are_the_decided_ones():
    assert (PASSWORD_MIN_LENGTH, PASSWORD_MAX_LENGTH) == (10, 128)


@pytest.mark.parametrize("length", [10, 11, 64, 128])
def test_policy_accepts_lengths_in_range(length):
    check_password_policy(("caballo-bateria-" * 10)[:length])


@pytest.mark.parametrize(
    ("password", "code"),
    [
        ("", "contrasena_corta"),
        ("a1-b2-c3-", "contrasena_corta"),  # 9 caracteres
        ("x" * 129, "contrasena_larga"),
    ],
)
def test_policy_rejects_lengths_out_of_range(password, code):
    with pytest.raises(PasswordPolicyError) as excinfo:
        check_password_policy(password)
    assert excinfo.value.code == code
    assert password not in str(excinfo.value) or password == ""


def test_policy_counts_characters_not_bytes():
    # 10 caracteres con tilde (más de 10 bytes) son válidos; 129 con tilde no.
    check_password_policy("ñandú-áéíó")
    with pytest.raises(PasswordPolicyError):
        check_password_policy("ñ" * 129)


def test_common_list_is_short_and_only_has_passwords_the_length_rule_lets_through():
    assert 10 <= len(COMMON_PASSWORDS) <= 100
    for common in COMMON_PASSWORDS:
        assert PASSWORD_MIN_LENGTH <= len(common) <= PASSWORD_MAX_LENGTH
        assert common == common.casefold()


@pytest.mark.parametrize("password", ["1234567890", "Contraseña123", "PASSWORD123", "qwertyuiop"])
def test_policy_rejects_common_passwords_ignoring_case(password):
    with pytest.raises(PasswordPolicyError) as excinfo:
        check_password_policy(password)
    assert excinfo.value.code == "contrasena_comun"


def test_policy_rejects_non_text():
    with pytest.raises(PasswordPolicyError):
        check_password_policy(None)  # type: ignore[arg-type]


def test_hash_applies_the_policy_before_hashing(passwords, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("no debe hashear una contraseña que no cumple la política")

    monkeypatch.setattr(argon2.PasswordHasher, "hash", forbidden)
    for bad in ("corta", "x" * 129, "1234567890"):
        with pytest.raises(PasswordPolicyError):
            passwords.hash(bad)


# --- Sustitutos sueltos (B1 de T4): nunca un 500 por UnicodeEncodeError ----------------

LONE_SURROGATES = ["\ud800", "caballo-bateria-\ud800", "\udfff" + "x" * 20, "a\udc80" * 6]


@pytest.mark.parametrize("password", LONE_SURROGATES)
def test_policy_rejects_lone_surrogates_without_echoing_them(password):
    with pytest.raises(PasswordPolicyError) as excinfo:
        check_password_policy(password)

    assert excinfo.value.code == "contrasena_invalida"
    message = str(excinfo.value)
    assert "contraseña" in message.lower()
    for char in ("\ud800", "\udfff", "\udc80", "ud800", "udfff", "udc80"):
        assert char not in message
    # Sin causa ni contexto: el UnicodeEncodeError trae el carácter y su posición.
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__context__ is None


def test_hash_rejects_lone_surrogates_with_the_policy_error(passwords):
    with pytest.raises(PasswordPolicyError) as excinfo:
        passwords.hash("caballo-bateria-\ud800")
    assert excinfo.value.code == "contrasena_invalida"


@pytest.mark.parametrize("password", LONE_SURROGATES)
def test_verify_returns_false_for_lone_surrogates_with_and_without_account(
    passwords, monkeypatch, password
):
    stored = passwords.hash(GOOD_PASSWORD)
    calls: list[str] = []
    original = argon2.PasswordHasher.verify

    def spy(self, *args, **kwargs):
        calls.append("verify")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(argon2.PasswordHasher, "verify", spy)

    assert passwords.verify(stored, password) is False
    assert passwords.verify(None, password) is False
    # Mismo camino con y sin cuenta: ninguno llega a Argon2 (no distingue cuentas).
    assert calls == []


def test_lone_surrogates_are_not_logged(passwords, caplog):
    caplog.set_level(logging.DEBUG)
    password = "caballo-bateria-\ud800"

    passwords.verify(passwords.hash(GOOD_PASSWORD), password)
    passwords.verify(None, password)
    with pytest.raises(PasswordPolicyError):
        passwords.hash(password)

    assert "\ud800" not in caplog.text
    assert "ud800" not in caplog.text


def test_policy_messages_are_in_spanish_and_do_not_echo_the_password():
    with pytest.raises(PasswordPolicyError) as excinfo:
        check_password_policy("1234567890")
    assert "contraseña" in str(excinfo.value).lower()
    assert "1234567890" not in str(excinfo.value)


# --- Tokens opacos y doble hash --------------------------------------------------


def test_new_tokens_are_long_random_and_url_safe():
    tokens = {new_token() for _ in range(50)}

    assert len(tokens) == 50
    for token in tokens:
        assert len(token) >= 43  # 32 bytes en base64url
        assert set(token) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def test_token_key_is_the_sha256_hex_that_acceso_functions_expect():
    token = "token-sintetico"
    key = token_key(token)

    assert key == hashlib.sha256(token.encode()).hexdigest()
    assert len(key) == 64 and key == key.lower()


def test_token_storage_hash_is_the_double_sha256_bytes_stored_by_the_database():
    token = "token-sintetico"
    stored = token_storage_hash(token)

    assert isinstance(stored, bytes) and len(stored) == 32
    assert stored == hashlib.sha256(hashlib.sha256(token.encode()).digest()).digest()
    # El hash guardado no es la clave que se envía (I1): filtrado no autentica.
    assert stored.hex() != token_key(token)


# --- Derivación de claves ----------------------------------------------------------


def test_derived_keys_depend_on_the_context_and_never_equal_the_secret():
    jwt_key = derive_key(SECRET, "jwt-acceso")
    other = derive_key(SECRET, "limite-tasa")

    assert jwt_key != other
    assert jwt_key != SECRET.encode()
    assert len(jwt_key) == 32
    assert derive_key(SECRET, "jwt-acceso") == jwt_key
    assert derive_key(OTHER_SECRET, "jwt-acceso") != jwt_key


# --- JWT de acceso (A25) -------------------------------------------------------------


def _b64(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _forge(header: dict, claims: dict, key: bytes | None) -> str:
    signing_input = f"{_b64(header)}.{_b64(claims)}"
    if key is None:
        return f"{signing_input}."
    signature = hmac.new(key, signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def _claims(**overrides) -> dict:
    now = datetime.now(UTC)
    claims = {
        "sub": str(USER),
        "tenant": str(TENANT),
        "iss": JWT_ISSUER,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
    }
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not None}


def test_access_token_round_trip():
    token = encode_access_token(SECRET, sub=USER, tenant=TENANT, rol="admin")
    claims = decode_access_token(SECRET, token)

    assert claims.sub == USER
    assert claims.tenant == TENANT
    assert jwt.get_unverified_header(token)["alg"] == JWT_ALGORITHM == "HS256"


def test_access_token_carries_exp_15_minutes_and_iss():
    now = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
    token = encode_access_token(SECRET, sub=USER, tenant=TENANT, rol="contador", now=now)
    raw = jwt.decode(token, options={"verify_signature": False})

    assert ACCESS_TOKEN_TTL == timedelta(minutes=15)
    assert raw["exp"] == int((now + ACCESS_TOKEN_TTL).timestamp())
    assert raw["iss"] == JWT_ISSUER
    assert raw["rol"] == "contador"  # informativo; no se usa para autorizar (I9)


def test_access_token_is_not_signed_with_the_raw_secret_key():
    token = encode_access_token(SECRET, sub=USER, tenant=TENANT, rol="admin")

    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(token, SECRET, algorithms=["HS256"], issuer=JWT_ISSUER)


def test_token_signed_with_another_secret_is_rejected():
    token = encode_access_token(OTHER_SECRET, sub=USER, tenant=TENANT, rol="admin")

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(SECRET, token)


def test_alg_none_is_rejected():
    token = _forge({"alg": "none", "typ": "JWT"}, _claims(), None)

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(SECRET, token)


# Se firma con la clave correcta a propósito: lo que se rechaza es el algoritmo.
@pytest.mark.filterwarnings("ignore::jwt.warnings.InsecureKeyLengthWarning")
@pytest.mark.parametrize("alg", ["HS384", "HS512"])
def test_other_algorithms_are_rejected(alg):
    key = derive_key(SECRET, credentials.JWT_KEY_CONTEXT)
    token = jwt.encode(_claims(), key, algorithm=alg)

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(SECRET, token)


def test_header_alg_hs256_with_a_forged_signature_is_rejected():
    key = derive_key(SECRET, credentials.JWT_KEY_CONTEXT)
    token = _forge({"alg": "HS256", "typ": "JWT"}, _claims(), key)
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")

    assert decode_access_token(SECRET, token).sub == USER
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(SECRET, tampered)


@pytest.mark.parametrize(
    "claims",
    [
        _claims(exp=None),
        _claims(iss=None),
        _claims(iss="otro-emisor"),
        _claims(sub=None),
        _claims(tenant=None),
        _claims(sub="no-es-un-uuid"),
        _claims(tenant="no-es-un-uuid"),
        _claims(exp=int((datetime.now(UTC) - timedelta(seconds=1)).timestamp())),
    ],
    ids=[
        "sin-exp",
        "sin-iss",
        "iss-ajeno",
        "sin-sub",
        "sin-tenant",
        "sub-malo",
        "tenant-malo",
        "vencido",
    ],
)
def test_invalid_claims_are_rejected(claims):
    key = derive_key(SECRET, credentials.JWT_KEY_CONTEXT)
    token = _forge({"alg": "HS256", "typ": "JWT"}, claims, key)

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(SECRET, token)


@pytest.mark.parametrize("token", ["", "a.b", "no-es-un-jwt", "a.b.c.d"])
def test_garbage_tokens_are_rejected(token):
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(SECRET, token)


def test_invalid_token_error_does_not_echo_the_token():
    token = encode_access_token(OTHER_SECRET, sub=USER, tenant=TENANT, rol="admin")
    with pytest.raises(InvalidAccessTokenError) as excinfo:
        decode_access_token(SECRET, token)

    assert token not in str(excinfo.value)
    assert excinfo.value.__cause__ is None
    assert excinfo.value.__context__ is None


# --- Integración con la aplicación ----------------------------------------------------


def _config(environment: str) -> Config:
    return Config(
        database_url="postgresql+psycopg://u:p@db.invalid:5432/x",
        secret_key=SECRET,
        environment=environment,
    )


def test_app_computes_the_dummy_hash_at_startup_with_test_params_only_in_test():
    test_app = create_app(_config("test"))
    production_app = create_app(_config("production"))

    with test_app.app_context():
        assert get_passwords().params == ARGON2_TEST_PARAMS
    with production_app.app_context():
        assert get_passwords().params == ARGON2_PARAMS


def test_credentials_do_not_log_secrets(passwords, caplog):
    caplog.set_level(logging.DEBUG)
    stored = passwords.hash(GOOD_PASSWORD)
    passwords.verify(stored, GOOD_PASSWORD)
    passwords.verify(None, "contrasena-equivocada")
    token = new_token()
    token_key(token)
    access = encode_access_token(SECRET, sub=USER, tenant=TENANT, rol="admin")
    decode_access_token(SECRET, access)
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(OTHER_SECRET, access)

    for secret in (GOOD_PASSWORD, stored, token, access, SECRET, "contrasena-equivocada"):
        assert secret not in caplog.text
