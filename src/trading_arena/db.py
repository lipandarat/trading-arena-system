"""
Database connection and session management for the Trading Arena.

Provides async database connection, session management, and
database initialization utilities.
"""

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import event
from contextlib import asynccontextmanager
import os
import logging
import time
import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional
from .models.base import Base
from .config import config

logger = logging.getLogger(__name__)


class Database:
    """
    Async database connection manager.

    Provides connection pooling, session management, and
    database utilities for the trading arena application.
    """

    def __init__(self, database_url: str, echo: bool = False, pool_size: int = 10):
        """
        Initialize database connection.

        Args:
            database_url: PostgreSQL connection string
            echo: Whether to log SQL queries
            pool_size: Connection pool size
        """
        self.database_url = database_url
        self.engine = None
        self.async_session = None
        self.echo = echo
        self.pool_size = pool_size

    async def initialize(self, max_retries: int = 3, retry_delay: float = 2.0):
        """
        Initialize the database engine and session maker with retry logic.

        Args:
            max_retries: Maximum number of connection retry attempts
            retry_delay: Delay between retry attempts in seconds
        """
        for attempt in range(max_retries):
            try:
                logger.info(f"Attempting database connection (attempt {attempt + 1}/{max_retries})")

                self.engine = create_async_engine(
                    self.database_url,
                    echo=self.echo,
                    pool_pre_ping=True,
                    pool_recycle=3600,  # Recycle connections after 1 hour
                    pool_size=self.pool_size,
                    max_overflow=20,  # Allow 20 additional connections
                    # Connection timeout settings
                    connect_args={
                        "command_timeout": 60,
                        "server_settings": {
                            "application_name": "trading_arena",
                            "jit": "off"  # Disable JIT for better consistency
                        }
                    }
                )

                self.async_session = async_sessionmaker(
                    self.engine,
                    class_=AsyncSession,
                    expire_on_commit=False,
                    autoflush=True
                )

                # Validate connection with a simple query
                await self._validate_connection()

                # Set up event listeners
                self._setup_event_listeners()

                logger.info("Database connection initialized successfully")
                return

            except Exception as e:
                logger.error(f"Database connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    logger.info(f"Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    logger.error("All database connection attempts failed")
                    raise

    async def _validate_connection(self):
        """Validate database connection with a simple query."""
        if not self.engine:
            raise RuntimeError("Database engine not initialized")

        async with self.engine.begin() as conn:
            result = await conn.execute("SELECT 1 as test")
            test_value = result.scalar()
            if test_value != 1:
                raise RuntimeError("Database connection validation failed")
        logger.debug("Database connection validation passed")

    def _setup_event_listeners(self):
        """Set up SQLAlchemy event listeners for monitoring."""

        @event.listens_for(self.engine.sync_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            """Set connection pragmas."""
            pass  # PostgreSQL-specific pragmas can be added here

        @event.listens_for(self.engine.sync_engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            """Log slow queries."""
            context._query_start_time = time.time()

        @event.listens_for(self.engine.sync_engine, "after_cursor_execute")
        def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            """Log query execution time."""
            total = time.time() - context._query_start_time
            if total > 1.0:  # Log queries taking more than 1 second
                logger.warning(f"Slow query ({total:.2f}s): {statement[:100]}...")

    async def create_tables(self, drop_first: bool = False):
        """
        Create all database tables.

        Args:
            drop_first: Whether to drop existing tables first
        """
        if not self.engine:
            await self.initialize()

        try:
            async with self.engine.begin() as conn:
                if drop_first:
                    logger.info("Dropping existing tables...")
                    await conn.run_sync(Base.metadata.drop_all)

                logger.info("Creating database tables...")
                await conn.run_sync(Base.metadata.create_all)
                logger.info("Database tables created successfully")

        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
            raise

    async def drop_tables(self):
        """Drop all database tables."""
        if not self.engine:
            await self.initialize()

        try:
            async with self.engine.begin() as conn:
                logger.info("Dropping all tables...")
                await conn.run_sync(Base.metadata.drop_all)
                logger.info("All tables dropped successfully")

        except Exception as e:
            logger.error(f"Failed to drop tables: {e}")
            raise

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a database session with automatic commit/rollback.

        Yields:
            AsyncSession: Database session
        """
        if not self.async_session:
            await self.initialize()

        async with self.async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Database session error: {e}")
                raise
            finally:
                await session.close()

    async def get_connection_info(self) -> dict:
        """
        Get database connection information.

        Returns:
            dict: Connection info and status
        """
        if not self.engine:
            return {"status": "not_initialized"}

        try:
            async with self.get_session() as session:
                # Test connection
                await session.execute("SELECT 1")

                pool = self.engine.pool
                return {
                    "status": "connected",
                    "url": str(self.engine.url).replace(self.engine.url.password or "", "***"),
                    "pool_size": self.pool_size,
                    "checked_in": pool.checkedin(),
                    "checked_out": pool.checkedout(),
                    "overflow": pool.overflow(),
                }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }

    async def close(self):
        """Close all database connections."""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database connections closed")

    async def health_check(self) -> dict:
        """
        Perform comprehensive database health check.

        Returns:
            dict: Detailed health check results
        """
        health_info = {
            "status": "unhealthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checks": {}
        }

        try:
            # Basic connectivity check
            async with self.get_session() as session:
                start_time = time.time()
                await session.execute("SELECT 1")
                response_time = time.time() - start_time
                health_info["checks"]["connectivity"] = {
                    "status": "pass",
                    "response_time_ms": round(response_time * 1000, 2)
                }

            # Connection pool check
            if self.engine and self.engine.pool:
                pool = self.engine.pool
                health_info["checks"]["connection_pool"] = {
                    "status": "pass",
                    "size": self.pool_size,
                    "checked_in": pool.checkedin(),
                    "checked_out": pool.checkedout(),
                    "overflow": pool.overflow()
                }

            # Database version check
            async with self.get_session() as session:
                result = await session.execute("SELECT version()")
                version = result.scalar()
                health_info["checks"]["database_version"] = {
                    "status": "pass",
                    "version": version
                }

            # Table existence check
            async with self.get_session() as session:
                result = await session.execute("""
                    SELECT COUNT(*) as table_count
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                """)
                table_count = result.scalar()
                health_info["checks"]["tables"] = {
                    "status": "pass",
                    "count": table_count
                }

            health_info["status"] = "healthy"

        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            health_info["error"] = str(e)

        return health_info


# Global database instance
db: Optional[Database] = None


async def get_database() -> Database:
    """
    Get the global database instance using configuration module.

    Returns:
        Database: Global database instance
    """
    global db
    if db is None:
        database_url = config.database_url or "postgresql+asyncpg://arena_user:arena_pass@postgres:5432/trading_arena"
        echo = config.db_echo
        pool_size = config.db_pool_size

        db = Database(database_url, echo=echo, pool_size=pool_size)
        await db.initialize()

    return db


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function to get database session.

    Yields:
        AsyncSession: Database session
    """
    database = await get_database()
    async with database.get_session() as session:
        yield session


# Database utilities
async def init_database(drop_first: bool = False):
    """
    Initialize the database with all tables.

    Args:
        drop_first: Whether to drop existing tables first
    """
    database = await get_database()
    await database.create_tables(drop_first=drop_first)


async def check_database_health() -> dict:
    """
    Check database health status with comprehensive monitoring.

    Returns:
        dict: Detailed health status information
    """
    try:
        database = await get_database()
        health_result = await database.health_check()
        conn_info = await database.get_connection_info()

        return {
            "status": "healthy" if health_result["status"] == "healthy" else "unhealthy",
            "database": health_result,
            "connection": conn_info,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


async def validate_database_startup() -> bool:
    """
    Validate database connection during application startup.
    This function should be called before the application starts serving requests.

    Returns:
        bool: True if database is ready for production use
    """
    logger.info("Validating database connectivity for startup...")

    try:
        database = await get_database()
        health_result = await database.health_check()

        if health_result["status"] != "healthy":
            logger.error(f"Database health check failed: {health_result}")
            return False

        # Check critical tables exist
        async with database.get_session() as session:
            result = await session.execute("""
                SELECT COUNT(*) as count FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name IN (
                    'agents', 'trades', 'positions', 'competitions'
                )
            """)
            critical_tables = result.scalar()

            if critical_tables < 4:
                logger.error(f"Critical tables missing. Found: {critical_tables}/4")
                return False

        logger.info("Database validation completed successfully")
        return True

    except Exception as e:
        logger.error(f"Database startup validation failed: {e}")
        return False


