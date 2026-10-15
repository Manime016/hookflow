from logging.config import fileConfig

from alembic import context
from sqlalchemy import URL, engine_from_config, pool

from app.database import Base, database_url
import app.models  # noqa: F401 - register every mapped table

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
rendered_url = (
    database_url.render_as_string(hide_password=False)
    if isinstance(database_url, URL)
    else database_url
)
config.set_main_option("sqlalchemy.url", rendered_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=rendered_url, target_metadata=target_metadata,
        literal_binds=True, dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
