"""Centralized application configuration using Pydantic Settings.

This module consolidates all environment variables used throughout the application.
Configuration is validated at startup and provides type-safe access to settings.

SOURCE: Derived from comic-pile/app/config.py
MODIFICATIONS:
- Removed: AuthSettings, SessionSettings, RatingSettings (comic-pile specific)
- Added: RedisSettings, ArqSettings for job queue and caching
- Adapted: For Comic Identity Engine domain
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """Database configuration settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        populate_by_name=True,
    )

    database_url: str = Field(
        ...,
        description="PostgreSQL database connection URL",
        json_schema_extra={"env": "DATABASE_URL"},
    )
    test_database_url: str | None = Field(
        default=None,
        description="Database URL for testing (overrides DATABASE_URL in tests)",
        json_schema_extra={"env": "TEST_DATABASE_URL"},
    )
    pool_size: int = Field(
        default=20,
        alias="DB_POOL_SIZE",
        ge=1,
        description="SQLAlchemy connection pool size",
    )
    max_overflow: int = Field(
        default=40,
        alias="DB_MAX_OVERFLOW",
        ge=0,
        description="Additional temporary SQLAlchemy connections allowed beyond pool_size",
    )
    pool_timeout: int = Field(
        default=30,
        alias="DB_POOL_TIMEOUT",
        gt=0,
        description="Seconds to wait for a SQLAlchemy pooled connection before timing out",
    )

    @property
    def async_url(self) -> str:
        """Get the asynchronous database URL with asyncpg driver."""
        url = self.database_url
        if url.startswith("postgresql+asyncpg://"):
            return url
        elif url.startswith("postgresql+psycopg://"):
            return url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url

    @property
    def pool_capacity(self) -> int:
        """Get the maximum number of concurrent checked-out DB connections."""
        return self.pool_size + self.max_overflow


class RedisSettings(BaseSettings):
    """Redis configuration settings for caching and job queue."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL (DB 0 for arq job queue, DB 1 for cache)",
        json_schema_extra={"env": "REDIS_URL"},
    )
    redis_cache_db: int = Field(
        default=1,
        description="Redis database number for application cache",
        json_schema_extra={"env": "REDIS_CACHE_DB"},
    )
    redis_pool_size: int = Field(
        default=100,
        description="Redis connection pool size",
        json_schema_extra={"env": "REDIS_POOL_SIZE"},
    )
    redis_socket_timeout: float = Field(
        default=2.0,
        description="Redis socket timeout in seconds",
        json_schema_extra={"env": "REDIS_SOCKET_TIMEOUT"},
    )

    @property
    def cache_url(self) -> str:
        """Get Redis URL for cache database."""
        url = self.redis_url
        if url.endswith("/0"):
            url = url[:-1] + str(self.redis_cache_db)
        elif "/" in url and url.split("/")[-1].isdigit():
            url = url.rsplit("/", 1)[0] + "/" + str(self.redis_cache_db)
        else:
            url = url + "/" + str(self.redis_cache_db)
        return url


class ArqSettings(BaseSettings):
    """arq job queue configuration settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    arq_queue_url: str | None = Field(
        default=None,
        description="arq job queue Redis URL (defaults to redis_url DB 0)",
        json_schema_extra={"env": "ARQ_QUEUE_URL"},
    )
    arq_queue_name: str = Field(
        default="arq:queue",
        description="arq queue name used for enqueueing and worker consumption",
        json_schema_extra={"env": "ARQ_QUEUE_NAME"},
    )
    arq_queue_size: int = Field(
        default=10000,
        description="Maximum number of tasks in queue (0 = unlimited)",
        json_schema_extra={"env": "ARQ_QUEUE_SIZE"},
    )
    arq_max_jobs: int = Field(
        default=100,
        description="Maximum number of concurrent jobs processed per poll cycle",
        json_schema_extra={"env": "ARQ_MAX_JOBS"},
    )
    arq_poll_interval: float = Field(
        default=0.1,
        description="Queue polling interval in seconds (100ms = high throughput)",
        json_schema_extra={"env": "ARQ_POLL_INTERVAL"},
    )
    arq_job_timeout: int = Field(
        default=3000,
        description="Default job timeout in seconds (10x: 3000s = 50 minutes)",
        json_schema_extra={"env": "ARQ_JOB_TIMEOUT"},
    )
    arq_keep_result: int = Field(
        default=3600,
        description="How long to keep job results in seconds (0 = don't keep)",
        json_schema_extra={"env": "ARQ_KEEP_RESULT"},
    )

    @property
    def queue_url(self) -> str:
        """Get arq queue URL (defaults to REDIS_URL environment variable or main Redis URL)."""
        if self.arq_queue_url:
            return self.arq_queue_url
        # Use the redis_url from RedisSettings to ensure consistency
        return get_redis_settings().redis_url


class AppSettings(BaseSettings):
    """General application settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "production", "test"] = Field(
        default="development",
        description="Application environment",
        json_schema_extra={"env": "ENVIRONMENT"},
    )
    cors_origins: str | None = Field(
        default=None,
        description="Comma-separated list of allowed CORS origins",
        json_schema_extra={"env": "CORS_ORIGINS"},
    )
    enable_debug_routes: bool = Field(
        default=False,
        description="Enable debug routes (should be False in production)",
        json_schema_extra={"env": "ENABLE_DEBUG_ROUTES"},
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
        json_schema_extra={"env": "LOG_LEVEL"},
    )

    @property
    def cors_origins_list(self) -> list[str]:
        """Get CORS origins as a list."""
        if not self.cors_origins or not self.cors_origins.strip():
            if self.environment == "production":
                return []
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",")]

    def validate_production_cors(self) -> None:
        """Validate that CORS is properly configured in production."""
        if self.environment == "production":
            if not self.cors_origins or not self.cors_origins.strip():
                raise RuntimeError("CORS_ORIGINS must be set in production mode")


class AdapterSettings(BaseSettings):
    """Platform adapter configuration settings."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gcd_api_key: str | None = Field(
        default=None,
        description="Grand Comics Database API key (if required)",
        json_schema_extra={"env": "GCD_API_KEY"},
    )
    gcd_api_base_url: str = Field(
        default="https://comicvine.gamespot.com/api",
        description="Grand Comics Database API base URL",
        json_schema_extra={"env": "GCD_API_BASE_URL"},
    )
    adapter_timeout: int = Field(
        default=30,
        description="Default timeout for platform adapter HTTP requests (seconds)",
        json_schema_extra={"env": "ADAPTER_TIMEOUT"},
    )
    adapter_max_concurrent: int = Field(
        default=5,
        description="Maximum concurrent requests per adapter",
        json_schema_extra={"env": "ADAPTER_MAX_CONCURRENT"},
    )
    adapter_user_agent: str = Field(
        default="ComicIdentityEngine/1.0 (+https://github.com/anomalyco/comic-identity-engine)",
        description="User agent for platform adapter requests",
        json_schema_extra={"env": "ADAPTER_USER_AGENT"},
    )
    platform_search_timeout: int | None = Field(
        default=None,
        description=(
            "Optional hard wall-clock timeout for each platform search in seconds. "
            "If unset, platform searches are not force-cut early."
        ),
        json_schema_extra={"env": "PLATFORM_SEARCH_TIMEOUT"},
    )


class Settings(BaseSettings):
    """Main settings class that aggregates all configuration groups."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def database(self) -> DatabaseSettings:
        """Get database settings."""
        return get_database_settings()

    @property
    def redis(self) -> RedisSettings:
        """Get Redis settings."""
        return get_redis_settings()

    @property
    def arq(self) -> ArqSettings:
        """Get arq settings."""
        return get_arq_settings()

    @property
    def app(self) -> AppSettings:
        """Get app settings."""
        return get_app_settings()

    @property
    def adapter(self) -> AdapterSettings:
        """Get adapter settings."""
        return get_adapter_settings()


@lru_cache
def get_database_settings() -> DatabaseSettings:
    """Get cached database settings instance."""
    return DatabaseSettings()


@lru_cache
def get_redis_settings() -> RedisSettings:
    """Get cached Redis settings instance."""
    return RedisSettings()


@lru_cache
def get_arq_settings() -> ArqSettings:
    """Get cached arq settings instance."""
    return ArqSettings()


@lru_cache
def get_app_settings() -> AppSettings:
    """Get cached app settings instance."""
    return AppSettings()


@lru_cache
def get_adapter_settings() -> AdapterSettings:
    """Get cached adapter settings instance."""
    return AdapterSettings()


@lru_cache
def get_settings() -> Settings:
    """Get cached main settings instance."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear all cached settings (useful for testing)."""
    get_database_settings.cache_clear()
    get_redis_settings.cache_clear()
    get_arq_settings.cache_clear()
    get_app_settings.cache_clear()
    get_adapter_settings.cache_clear()
    get_settings.cache_clear()
