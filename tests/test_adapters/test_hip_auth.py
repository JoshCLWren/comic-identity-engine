"""Tests for AuthenticatedHIPAdapter.

Tests the authentication flow and cookie management for HipComics access.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from comic_identity_engine.adapters.hip_auth import (
    AuthenticatedHIPAdapter,
    create_authenticated_hip_adapter,
)
from comic_identity_engine.models import IssueCandidate


@pytest.fixture
def mock_cookies():
    """Mock authentication cookies."""
    return [
        {
            "name": "session",
            "value": "test_session_value",
            "domain": ".hipcomic.com",
            "path": "/",
            "expires": 9999999999,  # Far future
        },
        {
            "name": "auth_token",
            "value": "test_auth_token",
            "domain": ".hipcomic.com",
            "path": "/",
            "expires": 9999999999,
        },
    ]


@pytest.fixture
def expired_cookies():
    """Mock expired cookies."""
    return [
        {
            "name": "session",
            "value": "expired_session",
            "domain": ".hipcomic.com",
            "path": "/",
            "expires": 1000000000,  # Past timestamp
        }
    ]


class TestAuthenticatedHIPAdapter:
    """Test AuthenticatedHIPAdapter functionality."""

    def test_init_default_params(self):
        """Test adapter initialization with default parameters."""
        adapter = AuthenticatedHIPAdapter()
        assert adapter.SOURCE == "hip"
        assert adapter.username is None
        assert adapter.password is None
        assert adapter.headless is True
        assert adapter.cookie_file == Path("hip_cookies.json")

    def test_init_custom_params(self):
        """Test adapter initialization with custom parameters."""
        custom_cookie_file = Path("/tmp/custom_cookies.json")
        adapter = AuthenticatedHIPAdapter(
            username="test@example.com",
            password="testpass",
            cookie_file=custom_cookie_file,
            headless=False,
        )
        assert adapter.username == "test@example.com"
        assert adapter.password == "testpass"
        assert adapter.cookie_file == custom_cookie_file
        assert adapter.headless is False

    @pytest.mark.asyncio
    async def test_load_valid_cookies(self, mock_cookies, tmp_path):
        """Test loading valid cookies from file."""
        cookie_file = tmp_path / "test_cookies.json"
        with open(cookie_file, "w") as f:
            json.dump(mock_cookies, f)

        adapter = AuthenticatedHIPAdapter(cookie_file=cookie_file)
        cookies = await adapter._load_cookies()

        assert cookies is not None
        assert len(cookies) == 2
        assert cookies[0]["name"] == "session"
        assert cookies[1]["name"] == "auth_token"

    @pytest.mark.asyncio
    async def test_load_expired_cookies(self, expired_cookies, tmp_path):
        """Test loading expired cookies returns None."""
        cookie_file = tmp_path / "test_cookies.json"
        with open(cookie_file, "w") as f:
            json.dump(expired_cookies, f)

        adapter = AuthenticatedHIPAdapter(cookie_file=cookie_file)
        cookies = await adapter._load_cookies()

        assert cookies is None

    @pytest.mark.asyncio
    async def test_load_no_cookie_file(self, tmp_path):
        """Test loading when cookie file doesn't exist returns None."""
        cookie_file = tmp_path / "nonexistent_cookies.json"
        adapter = AuthenticatedHIPAdapter(cookie_file=cookie_file)
        cookies = await adapter._load_cookies()

        assert cookies is None

    @pytest.mark.asyncio
    async def test_save_cookies(self, mock_cookies, tmp_path):
        """Test saving cookies to file."""
        cookie_file = tmp_path / "test_save_cookies.json"
        adapter = AuthenticatedHIPAdapter(cookie_file=cookie_file)

        await adapter._save_cookies(mock_cookies)

        assert cookie_file.exists()
        with open(cookie_file, "r") as f:
            saved_cookies = json.load(f)
        assert len(saved_cookies) == 2
        assert saved_cookies[0]["name"] == "session"

    @pytest.mark.asyncio
    async def test_authenticate_with_cached_cookies(self, mock_cookies, tmp_path):
        """Test authentication uses cached cookies if available."""
        cookie_file = tmp_path / "test_auth_cookies.json"
        with open(cookie_file, "w") as f:
            json.dump(mock_cookies, f)

        adapter = AuthenticatedHIPAdapter(cookie_file=cookie_file)
        await adapter._authenticate()

        assert adapter._authenticated_cookies == mock_cookies
        assert len(adapter._authenticated_cookies) == 2

    @pytest.mark.asyncio
    async def test_context_manager_sets_cookie_header(self, mock_cookies, tmp_path):
        """Test async context manager sets Cookie header."""
        cookie_file = tmp_path / "test_cm_cookies.json"
        with open(cookie_file, "w") as f:
            json.dump(mock_cookies, f)

        async with AuthenticatedHIPAdapter(cookie_file=cookie_file) as adapter:
            # Check that Cookie header is set
            expected_cookie = "session=test_session_value; auth_token=test_auth_token"
            assert adapter.headers.get("Cookie") == expected_cookie

    @pytest.mark.asyncio
    async def test_fetch_issue_with_authentication(self, mock_cookies, tmp_path):
        """Test fetch_issue uses authenticated headers."""
        cookie_file = tmp_path / "test_fetch_cookies.json"
        with open(cookie_file, "w") as f:
            json.dump(mock_cookies, f)

        adapter = AuthenticatedHIPAdapter(cookie_file=cookie_file)

        # Mock the parent fetch_issue method
        with patch.object(
            adapter.__class__.__bases__[0],
            "fetch_issue",
            new=AsyncMock(return_value=MagicMock(spec=IssueCandidate)),
        ) as mock_fetch:
            async with adapter:
                await adapter.fetch_issue("test-issue", full_url="http://test.com")

                # Verify parent method was called with authenticated headers
                mock_fetch.assert_called_once()
                assert "Cookie" in adapter.headers

    @pytest.mark.asyncio
    async def test_login_without_credentials_raises_error(self):
        """Test that login fails gracefully without credentials."""
        adapter = AuthenticatedHIPAdapter(username=None, password=None)

        with pytest.raises(Exception) as exc_info:
            await adapter._login_with_playwright()

        assert "HIP_USERNAME" in str(exc_info.value) or "HIP_PASSWORD" in str(
            exc_info.value
        )


class TestCreateAuthenticatedHIPAdapter:
    """Test factory function for creating authenticated adapter."""

    @pytest.mark.asyncio
    async def test_factory_with_env_credentials(
        self, mock_cookies, tmp_path, monkeypatch
    ):
        """Test factory uses environment variables for credentials."""
        monkeypatch.setenv("HIP_USERNAME", "env@example.com")
        monkeypatch.setenv("HIP_PASSWORD", "env_password")

        cookie_file = tmp_path / "test_factory_cookies.json"
        with open(cookie_file, "w") as f:
            json.dump(mock_cookies, f)

        adapter = await create_authenticated_hip_adapter(cookie_file=cookie_file)

        assert adapter.username == "env@example.com"
        assert adapter.password == "env_password"
        assert adapter._authenticated_cookies == mock_cookies

    @pytest.mark.asyncio
    async def test_factory_with_explicit_credentials(self, mock_cookies, tmp_path):
        """Test factory uses explicit credentials over env vars."""
        cookie_file = tmp_path / "test_factory_explicit.json"
        with open(cookie_file, "w") as f:
            json.dump(mock_cookies, f)

        adapter = await create_authenticated_hip_adapter(
            username="explicit@example.com",
            password="explicit_password",
            cookie_file=cookie_file,
        )

        assert adapter.username == "explicit@example.com"
        assert adapter.password == "explicit_password"
        assert adapter._authenticated_cookies == mock_cookies
