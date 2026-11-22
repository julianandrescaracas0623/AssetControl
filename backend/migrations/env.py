"""Entorno de Alembic (spec 001, T6; R4c).

Se conecta solo con ``MIGRATION_DATABASE_URL`` (rol migrador, dueño del
esquema), nunca con ``DATABASE_URL`` (rol de la aplicación). Si falta, falla con
el nombre de la variable y sin su valor. La URL no se guarda en la
configuración de Alembic ni se imprime: se convierte a ``URL``, cuyo ``str``
oculta la contraseña.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from app.config import load_migration_url

config = context.config

# Las pruebas lo desactivan para no tocar el logging de pytest.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# Sin modelos todavía: la spec 002 apuntará aquí su MetaData para --autogenerate.
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=make_url(load_migration_url()),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(make_url(load_migration_url()), poolclass=NullPool)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
