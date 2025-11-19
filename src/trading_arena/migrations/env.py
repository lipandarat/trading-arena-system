"""
Alembic environment configuration for Trading Arena.

This file configures the Alembic database migration tool for the
Trading Arena application's SQLAlchemy models.
"""

import asyncio
import os
import sys
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from trading_arena.models.base import Base
from trading_arena.db import Database

# Import all models to ensure they're registered with Base.metadata
from trading_arena.models.agent import Agent
from trading_arena.models.competition import Competition, CompetitionEntry
from trading_arena.models.trading import Trade, Position
from trading_arena.models.scoring import Score, Ranking, Performance

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_database_url():
    """Get database URL from environment or config."""
    # Try environment variable first
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    # Fallback to config or default
    return config.get_main_option("sqlalchemy.url",
        "postgresql+asyncpg://arena_user:arena_pass@postgres:5432/trading_arena")


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with the given database connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        # Include schemas if needed
        include_schemas=True,
        # Render item for PostgreSQL-specific features
        render_item=render_postgresql_item,
    )

    with context.begin_transaction():
        context.run_migrations()


def render_postgresql_item(type_, autogen_context):
    """Custom rendering for PostgreSQL-specific types."""
    if type_.compile(autogen_context.dialect) == "UUID":
        return "UUID"
    if type_.compile(autogen_context.dialect) == "JSONB":
        return "JSONB"
    return False


async def run_async_migrations() -> None:
    """Run migrations in async mode."""
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()