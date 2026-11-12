import pytest

from app.config import REQUIRED_VARS, Config, MissingConfigError, load_config

VALID_ENV = {
    "DATABASE_URL": "postgresql+psycopg://user:valor-secreto-db@db.invalid:5432/assetcontrol",
    "SECRET_KEY": "valor-secreto-clave-123",
    "ENVIRONMENT": "test",
}


def test_required_vars_are_the_three_of_the_spec():
    assert set(REQUIRED_VARS) == {"DATABASE_URL", "SECRET_KEY", "ENVIRONMENT"}


def test_load_config_reads_all_variables():
    config = load_config(VALID_ENV)

    assert isinstance(config, Config)
    assert config.database_url == VALID_ENV["DATABASE_URL"]
    assert config.secret_key == VALID_ENV["SECRET_KEY"]
    assert config.environment == "test"


def test_load_config_reads_os_environ_by_default(monkeypatch):
    for name, value in VALID_ENV.items():
        monkeypatch.setenv(name, value)

    config = load_config()

    assert config.environment == "test"


@pytest.mark.parametrize("missing", ["DATABASE_URL", "SECRET_KEY", "ENVIRONMENT"])
def test_missing_variable_names_it_without_leaking_values(missing):
    env = {k: v for k, v in VALID_ENV.items() if k != missing}

    with pytest.raises(MissingConfigError) as excinfo:
        load_config(env)

    message = str(excinfo.value)
    assert missing in message
    for present_value in env.values():
        assert present_value not in message
    assert "valor-secreto" not in message


@pytest.mark.parametrize("missing", ["DATABASE_URL", "SECRET_KEY", "ENVIRONMENT"])
def test_empty_variable_counts_as_missing(missing):
    env = {**VALID_ENV, missing: "   "}

    with pytest.raises(MissingConfigError) as excinfo:
        load_config(env)

    assert missing in str(excinfo.value)


def test_all_missing_variables_are_named():
    with pytest.raises(MissingConfigError) as excinfo:
        load_config({})

    message = str(excinfo.value)
    for name in REQUIRED_VARS:
        assert name in message


def test_config_repr_does_not_leak_secrets():
    config = load_config(VALID_ENV)

    assert VALID_ENV["SECRET_KEY"] not in repr(config)
    assert VALID_ENV["DATABASE_URL"] not in repr(config)
