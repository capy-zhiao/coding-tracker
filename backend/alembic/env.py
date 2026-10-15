"""Alembic environment: points migrations at the app's database and models.

The URL comes from the Alembic config if a caller set one (migrate.py and the migration
tests do), otherwise from DATABASE_URL like the app itself. SQLite can't ALTER most
things in place, so on SQLite every migration runs in batch mode (copy the table, change
the copy, swap it in); Postgres alters directly.
"""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app import models  # noqa: F401  (registers every table on Base.metadata)
from app.config import settings
from app.database import Base

config = context.config

# Only set up logging from alembic.ini when run from the command line; migrate.py and the
# tests call Alembic inside their own process and keep their own logging.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

url = config.get_main_option("sqlalchemy.url") or settings.database_url
is_sqlite = url.startswith("sqlite")

options = dict(
    target_metadata=Base.metadata,
    render_as_batch=is_sqlite,
    compare_type=True,
)


def run_migrations_offline() -> None:
    """Print the SQL instead of running it (`alembic upgrade head --sql`)."""
    context.configure(url=url, literal_binds=True, **options)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection")
    if connectable is not None:            # a caller handed us an open connection
        context.configure(connection=connectable, **options)
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = engine_from_config(
        {"sqlalchemy.url": url}, prefix="sqlalchemy.", poolclass=pool.NullPool,
    )
    with engine.connect() as connection:
        context.configure(connection=connection, **options)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
