"""Tests for application configuration."""

import os
from unittest.mock import patch

import pytest

os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost/test_db"

from comic_identity_engine.config import (
    AdapterSettings,
    AppSettings,
    ArqSettings,
    DatabaseSettings,
    RedisSettings,
    Settings,
    clear_settings_cache,
    get_adapter_settings,
    get_app_settings,
    get_arq_settings,
    get_database_settings,
    get_redis_settings,
    get_settings,
)


@pytest.fixture(autouse=True)
def clear_cache_before_each_test():
    """Clear settings cache before each test."""
    clear_settings_cache()
    yield
    clear_settings_cache()


class TestDatabaseSettings:
    """Tests for DatabaseSettings class."""

    def test_default_database_url(self):
        """Test DATABASE_URL is loaded from environment."""
        with patch.dict(
            os.environ, {"DATABASE_URL": "postgresql://user:pass@localhost/db"}
        ):
            settings = DatabaseSettings()
            assert settings.database_url == "postgresql://user:pass@localhost/db"

    def test_missing_database_url_raises_error(self):
        """Test missing DATABASE_URL raises validation error."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(Exception):
                DatabaseSettings()

    def test_async_url_with_asyncpg(self):
        """Test async_url property with postgresql+asyncpg:// URL."""
        with patch.dict(
            os.environ, {"DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db"}
        ):
            settings = DatabaseSettings()
            assert settings.async_url == "postgresql+asyncpg://user:pass@localhost/db"

    def test_async_url_with_psycopg(self):
        """Test async_url property converts postgresql+psycopg:// to asyncpg."""
        with patch.dict(
            os.environ, {"DATABASE_URL": "postgresql+psycopg://user:pass@localhost/db"}
        ):
            settings = DatabaseSettings()
            assert settings.async_url == "postgresql+asyncpg://user:pass@localhost/db"

    def test_async_url_with_postgresql(self):
        """Test async_url property converts postgresql:// to asyncpg."""
        with patch.dict(
            os.environ, {"DATABASE_URL": "postgresql://user:pass@localhost/db"}
        ):
            settings = DatabaseSettings()
            assert settings.async_url == "postgresql+asyncpg://user:pass@localhost/db"

    def test_async_url_with_postgres(self):
        """Test async_url property converts postgres:// to asyncpg."""
        with patch.dict(
            os.environ, {"DATABASE_URL": "postgres://user:pass@localhost/db"}
        ):
            settings = DatabaseSettings()
            assert settings.async_url == "postgresql+asyncpg://user:pass@localhost/db"

    def test_async_url_passthrough(self):
        """Test async_url property passes through other URLs."""
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///test.db"}):
            settings = DatabaseSettings()
            assert settings.async_url == "sqlite:///test.db"

    def test_test_database_url_optional(self):
        """Test TEST_DATABASE_URL is optional."""
        with patch.dict(
            os.environ, {"DATABASE_URL": "postgresql://localhost/db"}, clear=True
        ):
            settings = DatabaseSettings()
            assert settings.test_database_url is None

    def test_test_database_url_provided(self):
        """Test TEST_DATABASE_URL can be set."""
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://localhost/db",
                "TEST_DATABASE_URL": "postgresql://localhost/test_db",
            },
        ):
            settings = DatabaseSettings()
            assert settings.test_database_url == "postgresql://localhost/test_db"

    def test_pool_defaults(self):
        """Test database pool settings default to the current SQLAlchemy values."""
        with patch.dict(
            os.environ, {"DATABASE_URL": "postgresql://localhost/db"}, clear=True
        ):
            settings = DatabaseSettings()
            assert settings.pool_size == 10
            assert settings.max_overflow == 20
            assert settings.pool_timeout == 30
            assert settings.pool_capacity == 30

    def test_pool_settings_can_be_configured(self):
        """Test database pool settings are loaded from explicit env vars."""
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://localhost/db",
                "DB_POOL_SIZE": "12",
                "DB_MAX_OVERFLOW": "5",
                "DB_POOL_TIMEOUT": "45",
            },
            clear=True,
        ):
            settings = DatabaseSettings()
            assert settings.pool_size == 12
            assert settings.max_overflow == 5
            assert settings.pool_timeout == 45
            assert settings.pool_capacity == 17


class TestRedisSettings:
    """Tests for RedisSettings class."""

    def test_default_values(self):
        """Test default Redis settings values."""
        with patch.dict(os.environ, {}, clear=True):
            settings = RedisSettings()
            assert settings.redis_url == "redis://localhost:6379/0"
            assert settings.redis_cache_db == 1
            assert settings.redis_pool_size == 100
            assert settings.redis_socket_timeout == 2.0

    def test_custom_values(self):
        """Test custom Redis settings."""
        with patch.dict(
            os.environ,
            {
                "REDIS_URL": "redis://redis:6379/0",
                "REDIS_CACHE_DB": "2",
                "REDIS_POOL_SIZE": "50",
                "REDIS_SOCKET_TIMEOUT": "5.0",
            },
        ):
            settings = RedisSettings()
            assert settings.redis_url == "redis://redis:6379/0"
            assert settings.redis_cache_db == 2
            assert settings.redis_pool_size == 50
            assert settings.redis_socket_timeout == 5.0

    def test_cache_url_with_db_zero(self):
        """Test cache_url property with /0 database."""
        with patch.dict(
            os.environ, {"REDIS_URL": "redis://localhost:6379/0", "REDIS_CACHE_DB": "1"}
        ):
            settings = RedisSettings()
            assert settings.cache_url == "redis://localhost:6379/1"

    def test_cache_url_with_numeric_db(self):
        """Test cache_url property with numeric database."""
        with patch.dict(
            os.environ, {"REDIS_URL": "redis://localhost:6379/5", "REDIS_CACHE_DB": "2"}
        ):
            settings = RedisSettings()
            assert settings.cache_url == "redis://localhost:6379/2"

    def test_cache_url_without_db(self):
        """Test cache_url property without database in URL."""
        with patch.dict(
            os.environ, {"REDIS_URL": "redis://localhost:6379", "REDIS_CACHE_DB": "1"}
        ):
            settings = RedisSettings()
            assert settings.cache_url == "redis://localhost:6379/1"

    def test_cache_url_preserves_host(self):
        """Test cache_url property preserves host."""
        with patch.dict(
            os.environ,
            {"REDIS_URL": "redis://redis.example.com:6380/0", "REDIS_CACHE_DB": "3"},
        ):
            settings = RedisSettings()
            assert settings.cache_url == "redis://redis.example.com:6380/3"


class TestArqSettings:
    """Tests for ArqSettings class."""

    def test_default_values(self):
        """Test default arq settings values."""
        with patch.dict(os.environ, {}, clear=True):
            settings = ArqSettings()
            assert settings.arq_queue_url is None
            assert settings.arq_queue_name == "arq:queue"
            assert settings.arq_max_jobs == 100
            assert settings.arq_job_timeout == 300
            assert settings.arq_keep_result == 3600

    def test_custom_values(self):
        """Test custom arq settings."""
        with patch.dict(
            os.environ,
            {
                "ARQ_QUEUE_URL": "redis://localhost:6379/1",
                "ARQ_QUEUE_NAME": "cie:test:queue",
                "ARQ_MAX_JOBS": "20",
                "ARQ_JOB_TIMEOUT": "600",
                "ARQ_KEEP_RESULT": "7200",
            },
        ):
            settings = ArqSettings()
            assert settings.arq_queue_url == "redis://localhost:6379/1"
            assert settings.arq_queue_name == "cie:test:queue"
            assert settings.arq_max_jobs == 20
            assert settings.arq_job_timeout == 600
            assert settings.arq_keep_result == 7200

    def test_queue_url_with_custom_url(self):
        """Test queue_url property with custom URL."""
        with patch.dict(os.environ, {"ARQ_QUEUE_URL": "redis://localhost:6379/2"}):
            settings = ArqSettings()
            assert settings.queue_url == "redis://localhost:6379/2"

    def test_queue_url_defaults_to_redis(self):
        """Test queue_url property defaults to standard Redis URL."""
        with patch.dict(os.environ, {}, clear=True):
            settings = ArqSettings()
            assert settings.queue_url == "redis://localhost:6379/0"


class TestAppSettings:
    """Tests for AppSettings class."""

    def test_default_values(self):
        """Test default app settings values."""
        with patch.dict(os.environ, {}, clear=True):
            settings = AppSettings()
            assert settings.environment == "development"
            assert settings.cors_origins is None
            assert settings.enable_debug_routes is False
            assert settings.log_level == "INFO"

    def test_custom_values(self):
        """Test custom app settings."""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "CORS_ORIGINS": "https://example.com,https://api.example.com",
                "ENABLE_DEBUG_ROUTES": "true",
                "LOG_LEVEL": "DEBUG",
            },
        ):
            settings = AppSettings()
            assert settings.environment == "production"
            assert (
                settings.cors_origins == "https://example.com,https://api.example.com"
            )
            assert settings.enable_debug_routes is True
            assert settings.log_level == "DEBUG"

    def test_cors_origins_list_empty_production(self):
        """Test cors_origins_list returns empty list in production when not set."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "CORS_ORIGINS": ""}):
            settings = AppSettings()
            assert settings.cors_origins_list == []

    def test_cors_origins_list_wildcard_development(self):
        """Test cors_origins_list returns wildcard in development."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development", "CORS_ORIGINS": ""}):
            settings = AppSettings()
            assert settings.cors_origins_list == ["*"]

    def test_cors_origins_list_wildcard_test(self):
        """Test cors_origins_list returns wildcard in test environment."""
        with patch.dict(os.environ, {"ENVIRONMENT": "test", "CORS_ORIGINS": ""}):
            settings = AppSettings()
            assert settings.cors_origins_list == ["*"]

    def test_cors_origins_list_multiple(self):
        """Test cors_origins_list parses comma-separated origins."""
        with patch.dict(
            os.environ, {"CORS_ORIGINS": "https://a.com, https://b.com, https://c.com"}
        ):
            settings = AppSettings()
            assert settings.cors_origins_list == [
                "https://a.com",
                "https://b.com",
                "https://c.com",
            ]

    def test_cors_origins_list_whitespace_trimmed(self):
        """Test cors_origins_list trims whitespace."""
        with patch.dict(
            os.environ,
            {"CORS_ORIGINS": "  https://example.com  ,  https://api.example.com  "},
        ):
            settings = AppSettings()
            assert settings.cors_origins_list == [
                "https://example.com",
                "https://api.example.com",
            ]

    def test_validate_production_cors_success(self):
        """Test validate_production_cors passes with CORS origins set."""
        with patch.dict(
            os.environ,
            {"ENVIRONMENT": "production", "CORS_ORIGINS": "https://example.com"},
        ):
            settings = AppSettings()
            settings.validate_production_cors()

    def test_validate_production_cors_fails_empty(self):
        """Test validate_production_cors fails with empty CORS origins."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "CORS_ORIGINS": ""}):
            settings = AppSettings()
            with pytest.raises(
                RuntimeError, match="CORS_ORIGINS must be set in production mode"
            ):
                settings.validate_production_cors()

    def test_validate_production_cors_fails_none(self):
        """Test validate_production_cors fails with None CORS origins."""
        with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
            settings = AppSettings()
            with pytest.raises(
                RuntimeError, match="CORS_ORIGINS must be set in production mode"
            ):
                settings.validate_production_cors()

    def test_validate_production_cors_skips_development(self):
        """Test validate_production_cors skips validation in development."""
        with patch.dict(os.environ, {"ENVIRONMENT": "development", "CORS_ORIGINS": ""}):
            settings = AppSettings()
            settings.validate_production_cors()


class TestAdapterSettings:
    """Tests for AdapterSettings class."""

    def test_default_values(self):
        """Test default adapter settings values."""
        with patch.dict(os.environ, {}, clear=True):
            settings = AdapterSettings()
            assert settings.gcd_api_key is None
            assert settings.gcd_api_base_url == "https://comicvine.gamespot.com/api"
            assert settings.adapter_timeout == 30
            assert settings.adapter_max_concurrent == 5
            assert (
                settings.adapter_user_agent
                == "ComicIdentityEngine/1.0 (+https://github.com/anomalyco/comic-identity-engine)"
            )

    def test_custom_values(self):
        """Test custom adapter settings."""
        with patch.dict(
            os.environ,
            {
                "GCD_API_KEY": "test-key-123",
                "GCD_API_BASE_URL": "https://custom-api.com",
                "ADAPTER_TIMEOUT": "60",
                "ADAPTER_MAX_CONCURRENT": "10",
                "ADAPTER_USER_AGENT": "CustomAgent/1.0",
            },
        ):
            settings = AdapterSettings()
            assert settings.gcd_api_key == "test-key-123"
            assert settings.gcd_api_base_url == "https://custom-api.com"
            assert settings.adapter_timeout == 60
            assert settings.adapter_max_concurrent == 10
            assert settings.adapter_user_agent == "CustomAgent/1.0"


class TestSettings:
    """Tests for main Settings class."""

    def test_settings_properties(self):
        """Test Settings class properties delegate to cached functions."""
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://localhost/db",
                "ENVIRONMENT": "test",
            },
        ):
            settings = Settings()
            assert isinstance(settings.database, DatabaseSettings)
            assert isinstance(settings.redis, RedisSettings)
            assert isinstance(settings.arq, ArqSettings)
            assert isinstance(settings.app, AppSettings)
            assert isinstance(settings.adapter, AdapterSettings)


class TestLruCacheFunctions:
    """Tests for @lru_cache functions."""

    def test_get_database_settings_cached(self):
        """Test get_database_settings returns cached instance."""
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/db"}):
            settings1 = get_database_settings()
            settings2 = get_database_settings()
            assert settings1 is settings2

    def test_get_redis_settings_cached(self):
        """Test get_redis_settings returns cached instance."""
        settings1 = get_redis_settings()
        settings2 = get_redis_settings()
        assert settings1 is settings2

    def test_get_arq_settings_cached(self):
        """Test get_arq_settings returns cached instance."""
        settings1 = get_arq_settings()
        settings2 = get_arq_settings()
        assert settings1 is settings2

    def test_get_app_settings_cached(self):
        """Test get_app_settings returns cached instance."""
        settings1 = get_app_settings()
        settings2 = get_app_settings()
        assert settings1 is settings2

    def test_get_adapter_settings_cached(self):
        """Test get_adapter_settings returns cached instance."""
        settings1 = get_adapter_settings()
        settings2 = get_adapter_settings()
        assert settings1 is settings2

    def test_get_settings_cached(self):
        """Test get_settings returns cached instance."""
        with patch.dict(
            os.environ,
            {
                "DATABASE_URL": "postgresql://localhost/db",
            },
        ):
            settings1 = get_settings()
            settings2 = get_settings()
            assert settings1 is settings2

    def test_clear_settings_cache(self):
        """Test clear_settings_cache clears all cached settings."""
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/db"}):
            settings1 = get_database_settings()
            clear_settings_cache()
            settings2 = get_database_settings()
            assert settings1 is not settings2

    def test_different_settings_not_same_instance(self):
        """Test different settings types return different instances."""
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://localhost/db"}):
            db_settings = get_database_settings()
            redis_settings = get_redis_settings()
            assert db_settings is not redis_settings
