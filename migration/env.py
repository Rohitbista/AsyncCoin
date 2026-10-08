import os
import asyncio
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from asynccoin.config.settings import settings
from asynccoin.database import models  # noqa: F401  (registers tables on Base.metadata)
from asynccoin.database.base import Base

# this is the Alembic Config object
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 1. Fetch URL from GitHub Actions secret/Environment variable first
database_url = os.getenv("ASYNCCOIN_DATABASE_URL")

# 2. Fall back to your app settings if the environment variable isn't set
if not database_url:
    database_url = settings.database_url

# 3. Ensure the URL uses the async driver if it's missing (e.g. for postgres)
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

# 4. Set the URL into the Alembic config, escaping '%' for the ConfigParser
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

# target_metadata definition and your run_migrations_offline / online functions follow below...
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
