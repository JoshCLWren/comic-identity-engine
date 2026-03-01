"""Tests for core cache modules (Redis, Memory, HTTP cache)."""

import json
import pickle
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from comic_identity_engine.core.cache.http_cache import http_cached
from comic_identity_engine.core.cache.memory_cache import MemoryCache, TieredCache
from comic_identity_engine.core.cache.redis_singleton import RedisSingleton, redis_cache


class TestRedisSingleton:
    """Tests for RedisSingleton class."""

    @pytest.fixture(autouse=True)
    async def reset_singleton(self):
        """Reset singleton state before each test."""
        from comic_identity_engine.core.cache.redis_singleton import RedisSingleton

        singleton = RedisSingleton()
        singleton._client = None
        singleton._initialized = False
        yield
        singleton._client = None
        singleton._initialized = False

    def test_singleton_pattern(self):
        """Test RedisSingleton implements singleton pattern."""
        instance1 = RedisSingleton()
        instance2 = RedisSingleton()
        assert instance1 is instance2

    def test_global_redis_cache_singleton(self):
        """Test global redis_cache is singleton."""
        from comic_identity_engine.core.cache.redis_singleton import RedisSingleton

        assert isinstance(redis_cache, RedisSingleton)

    def test_client_property_not_initialized(self):
        """Test client property raises error when not initialized."""
        singleton = RedisSingleton()
        with pytest.raises(RuntimeError, match="Redis not initialized"):
            _ = singleton.client

    @pytest.mark.asyncio
    async def test_initialize_success(self):
        """Test successful Redis initialization."""
        singleton = RedisSingleton()
        mock_client = AsyncMock()
        mock_redis_class = MagicMock(return_value=mock_client)

        with patch(
            "comic_identity_engine.core.cache.redis_singleton.redis.from_url",
            mock_redis_class,
        ):
            await singleton.initialize("redis://localhost:6379/0")
            assert singleton._initialized is True
            assert singleton._client is mock_client

    @pytest.mark.asyncio
    async def test_initialize_already_initialized(self):
        """Test initialize does not re-initialize if already initialized."""
        singleton = RedisSingleton()
        singleton._client = AsyncMock()
        singleton._initialized = True

        with patch(
            "comic_identity_engine.core.cache.redis_singleton.logger"
        ) as mock_logger:
            await singleton.initialize("redis://localhost:6379/0")
            mock_logger.warning.assert_called_with("Redis already initialized")

    @pytest.mark.asyncio
    async def test_initialize_failure(self):
        """Test initialize raises RuntimeError on connection failure."""
        singleton = RedisSingleton()
        mock_redis_class = MagicMock(side_effect=ConnectionError("Connection refused"))

        with patch(
            "comic_identity_engine.core.cache.redis_singleton.redis.from_url",
            mock_redis_class,
        ):
            with pytest.raises(RuntimeError, match="Failed to connect to Redis"):
                await singleton.initialize("redis://localhost:6379/0")
            assert singleton._initialized is False
            assert singleton._client is None

    @pytest.mark.asyncio
    async def test_get_json_value(self):
        """Test get retrieves JSON value."""
        singleton = RedisSingleton()
        mock_client = AsyncMock()
        mock_client.get.return_value = json.dumps({"key": "value"}).encode()
        singleton._client = mock_client
        singleton._initialized = True

        result = await singleton.get("test_key")
        assert result == {"key": "value"}
        mock_client.get.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_get_pickle_value(self):
        """Test get retrieves pickle value when JSON fails."""
        singleton = RedisSingleton()
        mock_client = AsyncMock()
        test_data = {"key": "value", "nested": {"data": [1, 2, 3]}}
        mock_client.get.return_value = pickle.dumps(test_data)
        singleton._client = mock_client
        singleton._initialized = True

        result = await singleton.get("test_key")
        assert result == test_data

    @pytest.mark.asyncio
    async def test_get_not_found(self):
        """Test get returns None when key not found."""
        singleton = RedisSingleton()
        mock_client = AsyncMock()
        mock_client.get.return_value = None
        singleton._client = mock_client
        singleton._initialized = True

        result = await singleton.get("nonexistent_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_failure(self):
        """Test get raises RuntimeError on failure."""
        singleton = RedisSingleton()
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("Redis error")
        singleton._client = mock_client
        singleton._initialized = True

        with pytest.raises(RuntimeError, match="Failed to get key"):
            await singleton.get("test_key")

    @pytest.mark.asyncio
    async def test_set_json_value(self):
        """Test set stores JSON value."""
        singleton = RedisSingleton()
        mock_client = AsyncMock()
        singleton._client = mock_client
        singleton._initialized = True

        await singleton.set("test_key", {"data": "value"}, ttl=3600)
        mock_client.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_pickle_value(self):
        """Test set stores pickle value when JSON fails."""
        singleton = RedisSingleton()
        mock_client = AsyncMock()
        singleton._client = mock_client
        singleton._initialized = True

        obj = {"data": complex(1, 2)}
        await singleton.set("test_key", obj, ttl=None)
        mock_client.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_without_ttl(self):
        """Test set stores value without TTL."""
        singleton = RedisSingleton()
        mock_client = AsyncMock()
        singleton._client = mock_client
        singleton._initialized = True

        await singleton.set("test_key", "value", ttl=None)
        mock_client.set.assert_called_once_with("test_key", '"value"', ex=None)

    @pytest.mark.asyncio
    async def test_set_failure(self):
        """Test set raises RuntimeError on failure."""
        singleton = RedisSingleton()
        mock_client = AsyncMock()
        mock_client.set.side_effect = Exception("Redis error")
        singleton._client = mock_client
        singleton._initialized = True

        with pytest.raises(RuntimeError, match="Failed to set key"):
            await singleton.set("test_key", "value")

    @pytest.mark.asyncio
    async def test_delete(self):
        """Test delete removes key."""
        singleton = RedisSingleton()
        mock_client = AsyncMock()
        singleton._client = mock_client
        singleton._initialized = True

        await singleton.delete("test_key")
        mock_client.delete.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_delete_failure(self):
        """Test delete raises RuntimeError on failure."""
        singleton = RedisSingleton()
        mock_client = AsyncMock()
        mock_client.delete.side_effect = Exception("Redis error")
        singleton._client = mock_client
        singleton._initialized = True

        with pytest.raises(RuntimeError, match="Failed to delete key"):
            await singleton.delete("test_key")

    @pytest.mark.asyncio
    async def test_clear(self):
        """Test clear flushes database."""
        singleton = RedisSingleton()
        mock_client = AsyncMock()
        singleton._client = mock_client
        singleton._initialized = True

        await singleton.clear()
        mock_client.flushdb.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_failure(self):
        """Test clear raises RuntimeError on failure."""
        singleton = RedisSingleton()
        mock_client = AsyncMock()
        mock_client.flushdb.side_effect = Exception("Redis error")
        singleton._client = mock_client
        singleton._initialized = True

        with pytest.raises(RuntimeError, match="Failed to clear Redis"):
            await singleton.clear()

    @pytest.mark.asyncio
    async def test_close(self):
        """Test close closes connection."""
        singleton = RedisSingleton()
        mock_client = AsyncMock()
        singleton._client = mock_client
        singleton._initialized = True

        await singleton.close()
        mock_client.close.assert_called_once()
        assert singleton._client is None
        assert singleton._initialized is False

    @pytest.mark.asyncio
    async def test_close_when_not_initialized(self):
        """Test close when not initialized does nothing."""
        singleton = RedisSingleton()
        singleton._client = None
        singleton._initialized = False

        await singleton.close()
        assert singleton._client is None


class TestMemoryCache:
    """Tests for MemoryCache class."""

    @pytest.mark.asyncio
    async def test_set_and_get(self):
        """Test basic set and get operations."""
        cache = MemoryCache(max_keys=100)
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self):
        """Test get returns None for nonexistent key."""
        cache = MemoryCache()
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_with_ttl(self):
        """Test set with TTL expires after TTL."""
        cache = MemoryCache()
        import time

        await cache.set("key", "value", ttl=1)
        result = await cache.get("key")
        assert result == "value"

        time.sleep(1.1)
        result = await cache.get("key")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_without_ttl(self):
        """Test set without TTL persists indefinitely."""
        cache = MemoryCache()
        await cache.set("key", "value")
        import time

        time.sleep(0.1)
        result = await cache.get("key")
        assert result == "value"

    @pytest.mark.asyncio
    async def test_delete(self):
        """Test delete removes key."""
        cache = MemoryCache()
        await cache.set("key", "value")
        await cache.delete("key")
        result = await cache.get("key")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_key(self):
        """Test delete of nonexistent key does nothing."""
        cache = MemoryCache()
        await cache.delete("nonexistent")

    @pytest.mark.asyncio
    async def test_clear(self):
        """Test clear removes all keys."""
        cache = MemoryCache()
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.clear()
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None

    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        """Test LRU eviction when max_keys reached."""
        cache = MemoryCache(max_keys=3)
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")
        await cache.set("key4", "value4")

        assert await cache.get("key1") is None
        assert await cache.get("key2") is not None
        assert await cache.get("key3") is not None
        assert await cache.get("key4") is not None

    @pytest.mark.asyncio
    async def test_access_time_updates_lru(self):
        """Test accessing key updates LRU order."""
        cache = MemoryCache(max_keys=3)
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")

        await cache.get("key1")
        await cache.set("key4", "value4")

        assert await cache.get("key1") is not None
        assert await cache.get("key2") is None

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test get_stats returns cache statistics."""
        cache = MemoryCache(max_keys=10)
        await cache.set("key1", "value1")
        await cache.set("key2", "value2", ttl=1)

        import time

        time.sleep(1.1)

        stats = cache.get_stats()
        assert stats["total_entries"] == 2
        assert stats["expired_entries"] == 1
        assert stats["active_entries"] == 1

    @pytest.mark.asyncio
    async def test_per_key_locking(self):
        """Test per-key locking prevents race conditions."""
        cache = MemoryCache()
        import asyncio

        async def writer():
            for i in range(100):
                await cache.set("key", i)

        await asyncio.gather(writer(), writer())
        result = await cache.get("key")
        assert isinstance(result, int)

    @pytest.mark.asyncio
    async def test_ensure_capacity_evicts_lru(self):
        """Test _ensure_capacity evicts LRU keys."""
        cache = MemoryCache(max_keys=2)
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")

        import time

        time.sleep(0.01)
        await cache.set("key3", "value3")

        assert await cache.get("key1") is None

    @pytest.mark.asyncio
    async def test_cleanup_unused_locks(self):
        """Test unused locks are cleaned up."""
        cache = MemoryCache()
        await cache.set("key", "value")
        await cache.delete("key")

        import asyncio

        await asyncio.sleep(0.1)
        cache.get_stats()  # Trigger cleanup
        assert "key" not in cache._key_locks or len(cache._key_locks) == 0


class TestTieredCache:
    """Tests for TieredCache class."""

    @pytest.mark.asyncio
    async def test_get_from_l1_cache(self):
        """Test get retrieves from L1 (fastest) cache."""
        l1 = MemoryCache()
        l2 = MemoryCache()
        cache = TieredCache([l1, l2])

        await l1.set("key", "value1")
        await l2.set("key", "value2")

        result = await cache.get("key")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_from_l2_promotes_to_l1(self):
        """Test get from L2 promotes to L1."""
        l1 = MemoryCache()
        l2 = MemoryCache()
        cache = TieredCache([l1, l2])

        await l2.set("key", "value2")
        result = await cache.get("key")

        assert result == "value2"
        assert await l1.get("key") == "value2"

    @pytest.mark.asyncio
    async def test_get_not_found(self):
        """Test get returns None when not in any cache."""
        l1 = MemoryCache()
        l2 = MemoryCache()
        cache = TieredCache([l1, l2])

        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_writes_to_all_providers(self):
        """Test set writes to all cache providers."""
        l1 = MemoryCache()
        l2 = MemoryCache()
        cache = TieredCache([l1, l2])

        await cache.set("key", "value")
        assert await l1.get("key") == "value"
        assert await l2.get("key") == "value"

    @pytest.mark.asyncio
    async def test_delete_from_all_providers(self):
        """Test delete removes from all providers."""
        l1 = MemoryCache()
        l2 = MemoryCache()
        cache = TieredCache([l1, l2])

        await cache.set("key", "value")
        await cache.delete("key")

        assert await l1.get("key") is None
        assert await l2.get("key") is None

    @pytest.mark.asyncio
    async def test_clear_all_providers(self):
        """Test clear empties all providers."""
        l1 = MemoryCache()
        l2 = MemoryCache()
        cache = TieredCache([l1, l2])

        await l1.set("key1", "value1")
        await l2.set("key2", "value2")
        await cache.clear()

        assert await l1.get("key1") is None
        assert await l2.get("key2") is None


class TestHttpCachedDecorator:
    """Tests for http_cached decorator."""

    @pytest.mark.asyncio
    async def test_decorator_cache_miss(self):
        """Test decorator cache MISS executes function."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.set = AsyncMock()

        with patch(
            "comic_identity_engine.core.cache.http_cache.redis_cache", mock_redis
        ):

            @http_cached(ttl=300)
            async def fetch_data(url: str):
                return {"data": f"from {url}"}

            result = await fetch_data("https://example.com")
            assert result == {"data": "from https://example.com"}
            mock_redis.get.assert_called_once()
            mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_decorator_cache_hit(self):
        """Test decorator cache HIT returns cached value."""
        cached_value = {"data": "cached"}
        mock_redis = AsyncMock()
        mock_redis.get.return_value = cached_value
        mock_redis.set = AsyncMock()

        with patch(
            "comic_identity_engine.core.cache.http_cache.redis_cache", mock_redis
        ):
            call_count = 0

            @http_cached(ttl=300)
            async def fetch_data(url: str):
                nonlocal call_count
                call_count += 1
                return {"data": f"fresh {call_count}"}

            result = await fetch_data("https://example.com")
            assert result == cached_value
            assert call_count == 0
            mock_redis.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_decorator_ttl_override(self):
        """Test decorator TTL override via parameter."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.set = AsyncMock()

        with patch(
            "comic_identity_engine.core.cache.http_cache.redis_cache", mock_redis
        ):

            @http_cached(ttl=300)
            async def fetch_data(url: str, ttl: int | None = None):
                return {"data": "value"}

            await fetch_data("https://example.com", ttl=7200)
            mock_redis.set.assert_called_once_with(
                "https://example.com", {"data": "value"}, ttl=7200
            )

    @pytest.mark.asyncio
    async def test_decorator_graceful_degradation_get(self):
        """Test decorator gracefully handles Redis unavailable on get."""
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = RuntimeError("Redis unavailable")
        mock_redis.set = AsyncMock()

        with patch(
            "comic_identity_engine.core.cache.http_cache.redis_cache", mock_redis
        ):

            @http_cached(ttl=300)
            async def fetch_data(url: str):
                return {"data": "fresh"}

            result = await fetch_data("https://example.com")
            assert result == {"data": "fresh"}

    @pytest.mark.asyncio
    async def test_decorator_graceful_degradation_set(self):
        """Test decorator gracefully handles Redis unavailable on set."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.set.side_effect = RuntimeError("Redis unavailable")

        with patch(
            "comic_identity_engine.core.cache.http_cache.redis_cache", mock_redis
        ):

            @http_cached(ttl=300)
            async def fetch_data(url: str):
                return {"data": "fresh"}

            result = await fetch_data("https://example.com")
            assert result == {"data": "fresh"}

    @pytest.mark.asyncio
    async def test_decorator_unexpected_error_get(self):
        """Test decorator handles unexpected errors on get."""
        mock_redis = AsyncMock()
        mock_redis.get.side_effect = ValueError("Unexpected error")
        mock_redis.set = AsyncMock()

        with patch(
            "comic_identity_engine.core.cache.http_cache.redis_cache", mock_redis
        ):

            @http_cached(ttl=300)
            async def fetch_data(url: str):
                return {"data": "value"}

            result = await fetch_data("https://example.com")
            assert result == {"data": "value"}
            mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_decorator_unexpected_error_set(self):
        """Test decorator handles unexpected errors on set."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.set.side_effect = ValueError("Unexpected error")

        with patch(
            "comic_identity_engine.core.cache.http_cache.redis_cache", mock_redis
        ):

            @http_cached(ttl=300)
            async def fetch_data(url: str):
                return {"data": "value"}

            result = await fetch_data("https://example.com")
            assert result == {"data": "value"}

    @pytest.mark.asyncio
    async def test_decorator_function_without_url_param(self):
        """Test decorator raises error for function without url parameter."""
        with pytest.raises(RuntimeError, match="must have a 'url' parameter"):

            @http_cached(ttl=300)
            async def fetch_data(key: str):
                return {"data": "value"}

    @pytest.mark.asyncio
    async def test_decorator_missing_url_argument(self):
        """Test decorator raises error when url argument is missing."""
        mock_redis = AsyncMock()

        with patch(
            "comic_identity_engine.core.cache.http_cache.redis_cache", mock_redis
        ):

            @http_cached(ttl=300)
            async def fetch_data(url: str):
                return {"data": "value"}

            with pytest.raises(TypeError):
                await fetch_data()

    @pytest.mark.asyncio
    async def test_decorator_with_multiple_args(self):
        """Test decorator works with multiple function arguments."""
        mock_redis = AsyncMock()
        mock_redis.get.return_value = None
        mock_redis.set = AsyncMock()

        with patch(
            "comic_identity_engine.core.cache.http_cache.redis_cache", mock_redis
        ):

            @http_cached(ttl=300)
            async def fetch_data(url: str, headers: dict | None = None):
                return {"url": url, "headers": headers}

            result = await fetch_data(
                "https://example.com", {"Authorization": "Bearer token"}
            )
            assert result == {
                "url": "https://example.com",
                "headers": {"Authorization": "Bearer token"},
            }

    @pytest.mark.asyncio
    async def test_decorator_preserves_function_signature(self):
        """Test decorator preserves function signature."""
        import inspect

        @http_cached(ttl=300)
        async def fetch_data(url: str, ttl: int | None = None):
            return {"data": "value"}

        sig = inspect.signature(fetch_data)
        params = sig.parameters
        assert "url" in params
        assert "ttl" in params

    @pytest.mark.asyncio
    async def test_decorator_with_none_url(self):
        """Test decorator raises error when url parameter is explicitly None."""
        mock_redis = AsyncMock()

        with patch(
            "comic_identity_engine.core.cache.http_cache.redis_cache", mock_redis
        ):

            @http_cached(ttl=300)
            async def fetch_data(url: str | None = None):
                return {"data": "value"}

            with pytest.raises(RuntimeError, match="missing required 'url' parameter"):
                await fetch_data(url=None)
