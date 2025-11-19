"""Configuration and environment variable validation for trading arena."""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class Config:
    """Configuration class that loads and validates environment variables."""

    def __init__(self):
        self.load_config()

    def load_config(self):
        """Load and validate all environment variables."""
        # JWT Configuration
        self.jwt_secret_key = os.getenv("JWT_SECRET_KEY")
        if not self.jwt_secret_key:
            logger.warning(
                "JWT_SECRET_KEY not set, using insecure default. "
                "Please set this environment variable in production!"
            )

        # Admin credentials
        self.admin_username = os.getenv("ADMIN_USERNAME")
        self.admin_password = os.getenv("ADMIN_PASSWORD")
        # Password mode: "plaintext" for development, "hashed" for production
        self.password_mode = os.getenv("PASSWORD_MODE", "plaintext" if not self.is_production else "hashed")

        # Database configuration
        self.database_url = os.getenv("DATABASE_URL")
        self.db_echo = os.getenv("DB_ECHO", "false").lower() == "true"
        self.db_pool_size = int(os.getenv("DB_POOL_SIZE", "10"))

        # Redis configuration - fail-fast if not set
        self.redis_url = os.getenv("REDIS_URL")
        self.redis_password = os.getenv("REDIS_PASSWORD")

        # Kafka configuration - fail-fast if not set
        self.kafka_bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS")
        self.kafka_topic_prefix = os.getenv("KAFKA_TOPIC_PREFIX", "trading_arena")

        # Environment detection - moved before Binance config
        self.environment = os.getenv("ENVIRONMENT", "development").lower()
        self.is_production = self.environment == "production"
        self.is_development = self.environment == "development"

        # Binance configuration
        self.binance_api_key = os.getenv("BINANCE_API_KEY")
        self.binance_secret_key = os.getenv("BINANCE_SECRET_KEY")

        # FAIL FAST - Default to production mode (testnet=false) for security
        # Must be explicitly set to 'true' if testnet is desired
        self.binance_testnet = os.getenv("BINANCE_TESTNET", "false").lower() == "true"

        if self.is_production and self.binance_testnet:
            logger.warning("PRODUCTION WARNING: BINANCE_TESTNET=true in production environment")

        # Validate configuration based on environment
        self._validate_config()

    def _validate_config(self):
        """Validate configuration and log warnings for potential issues."""
        if self.is_production:
            # Production requires secure defaults
            if not self.jwt_secret_key or len(self.jwt_secret_key) < 32:
                raise ValueError(
                    "JWT_SECRET_KEY must be set and at least 32 characters in production"
                )

            if not self.admin_username:
                raise ValueError("ADMIN_USERNAME must be set in production")

            if not self.admin_password:
                raise ValueError("ADMIN_PASSWORD must be set in production")

            if len(self.admin_password) < 12:
                logger.warning(
                    "ADMIN_PASSWORD should be at least 12 characters in production"
                )

            if not self.database_url:
                raise ValueError("DATABASE_URL must be set in production")

            if not self.redis_url:
                raise ValueError("REDIS_URL must be set in production")

            if not self.kafka_bootstrap_servers:
                raise ValueError("KAFKA_BOOTSTRAP_SERVERS must be set in production")

        else:
            # Development environment - fail-fast for security
            logger.info("Running in development mode")
            if not self.admin_username:
                logger.warning("ADMIN_USERNAME not set - authentication will fail")
            if not self.admin_password:
                logger.warning("ADMIN_PASSWORD not set - authentication will fail")
            if not self.jwt_secret_key:
                logger.warning("JWT_SECRET_KEY not set - tokens will be invalid")

    def get_admin_credentials(self) -> tuple[str, str]:
        """Get admin credentials, with fail-fast validation."""
        if not self.admin_username:
            raise ValueError(
                "ADMIN_USERNAME must be set. Run 'python scripts/validate_production.py' "
                "to check your configuration."
            )

        if not self.admin_password:
            raise ValueError(
                "ADMIN_PASSWORD must be set. Default passwords are not allowed for security."
            )

        if len(self.admin_password) < 8:
            raise ValueError("ADMIN_PASSWORD must be at least 8 characters long.")

        return self.admin_username, self.admin_password

# Global config instance
config = Config()