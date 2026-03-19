"""Tests for catalog browser service."""

import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from comic_identity_engine.services.catalog_browser import (
    CatalogBrowser,
    CatalogMatchResult,
)


# Fixed UUIDs for deterministic tests
FIXED_SERIES_RUN_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
FIXED_ISSUE_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")
FIXED_SERIES2_ID = uuid.UUID("00000000-0000-4000-8000-000000000003")
FIXED_ISSUE2_ID = uuid.UUID("00000000-0000-4000-8000-000000000004")


@pytest.fixture
def mock_session():
    """Create mock database session."""
    return AsyncMock()


@pytest.fixture
def sample_series():
    """Create sample series run entity."""
    series = MagicMock()
    series.id = FIXED_SERIES_RUN_ID
    series.title = "X-Men"
    series.start_year = 1963
    series.publisher = "Marvel"
    return series


@pytest.fixture
def sample_issue():
    """Create sample issue entity."""
    issue = MagicMock()
    issue.id = FIXED_ISSUE_ID
    issue.issue_number = "1"
    issue.cover_date = datetime(1963, 9, 1)
    issue.series_run_id = FIXED_SERIES_RUN_ID
    return issue


@pytest.mark.asyncio
class TestCatalogBrowser:
    """Tests for CatalogBrowser class."""

    @patch("comic_identity_engine.services.catalog_browser.SeriesRunRepository")
    @patch("comic_identity_engine.services.catalog_browser.IssueRepository")
    async def test_find_comic_high_confidence_match(
        self,
        mock_issue_repo_cls,
        mock_series_repo_cls,
        mock_session,
        sample_series,
        sample_issue,
    ):
        """Test catalog browser with high confidence match."""
        # Setup mock repositories
        mock_series_repo = MagicMock()
        mock_series_repo.find_by_publisher_and_title = AsyncMock(
            return_value=[sample_series]
        )
        mock_series_repo_cls.return_value = mock_series_repo

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_series_run_id = AsyncMock(return_value=[sample_issue])
        mock_issue_repo_cls.return_value = mock_issue_repo

        browser = CatalogBrowser(mock_session)
        result = await browser.find_comic(
            publisher="Marvel",
            series_title="X-Men",
            issue_number="1",
            year=1963,
        )

        assert result.is_high_confidence
        assert result.confidence_score >= 90
        assert result.issue_id == FIXED_ISSUE_ID
        assert result.series_run_id == FIXED_SERIES_RUN_ID
        assert result.found_via == "catalog"
        assert result.year_confirmed is True
        assert result.publisher_score == 30
        assert result.series_score == 30
        assert result.issue_score == 30
        assert result.year_bonus == 10

    @patch("comic_identity_engine.services.catalog_browser.SeriesRunRepository")
    @patch("comic_identity_engine.services.catalog_browser.IssueRepository")
    async def test_find_comic_no_series_match(
        self,
        mock_issue_repo_cls,
        mock_series_repo_cls,
        mock_session,
    ):
        """Test catalog browser with no matching series."""
        # Setup mock repositories
        mock_series_repo = MagicMock()
        mock_series_repo.find_by_publisher_and_title = AsyncMock(return_value=[])
        mock_series_repo_cls.return_value = mock_series_repo

        mock_issue_repo = MagicMock()
        mock_issue_repo_cls.return_value = mock_issue_repo

        browser = CatalogBrowser(mock_session)
        result = await browser.find_comic(
            publisher="Nonexistent Publisher",
            series_title="Nonexistent Series",
            issue_number="999",
            year=9999,
        )

        assert not result.is_high_confidence
        assert result.confidence_score == 0
        assert result.issue_id is None
        assert result.found_via == "none"

    @patch("comic_identity_engine.services.catalog_browser.SeriesRunRepository")
    @patch("comic_identity_engine.services.catalog_browser.IssueRepository")
    async def test_find_comic_no_issue_match(
        self,
        mock_issue_repo_cls,
        mock_series_repo_cls,
        mock_session,
        sample_series,
    ):
        """Test catalog browser with matching series but no matching issue."""
        # Setup mock repositories
        mock_series_repo = MagicMock()
        mock_series_repo.find_by_publisher_and_title = AsyncMock(
            return_value=[sample_series]
        )
        mock_series_repo_cls.return_value = mock_series_repo

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_series_run_id = AsyncMock(return_value=[])
        mock_issue_repo_cls.return_value = mock_issue_repo

        browser = CatalogBrowser(mock_session)
        result = await browser.find_comic(
            publisher="Marvel",
            series_title="X-Men",
            issue_number="999",
            year=1963,
        )

        assert not result.is_high_confidence
        assert result.confidence_score == 0
        assert result.issue_id is None
        assert result.found_via == "none"

    @patch("comic_identity_engine.services.catalog_browser.SeriesRunRepository")
    @patch("comic_identity_engine.services.catalog_browser.IssueRepository")
    async def test_scoring_perfect_match(
        self,
        mock_issue_repo_cls,
        mock_series_repo_cls,
        mock_session,
        sample_series,
        sample_issue,
    ):
        """Test catalog browser scoring for perfect match."""
        # Setup mock repositories
        mock_series_repo = MagicMock()
        mock_series_repo.find_by_publisher_and_title = AsyncMock(
            return_value=[sample_series]
        )
        mock_series_repo_cls.return_value = mock_series_repo

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_series_run_id = AsyncMock(return_value=[sample_issue])
        mock_issue_repo_cls.return_value = mock_issue_repo

        browser = CatalogBrowser(mock_session)
        result = await browser.find_comic(
            publisher="Marvel",
            series_title="X-Men",
            issue_number="1",
            year=1963,
        )

        # Perfect match: 30 + 30 + 30 + 10 = 100
        assert result.confidence_score == 100
        assert result.publisher_score == 30
        assert result.series_score == 30
        assert result.issue_score == 30
        assert result.year_bonus == 10

    @patch("comic_identity_engine.services.catalog_browser.SeriesRunRepository")
    @patch("comic_identity_engine.services.catalog_browser.IssueRepository")
    async def test_scoring_without_year(
        self,
        mock_issue_repo_cls,
        mock_series_repo_cls,
        mock_session,
        sample_series,
        sample_issue,
    ):
        """Test catalog browser scoring without year confirmation."""
        # Setup mock repositories
        mock_series_repo = MagicMock()
        mock_series_repo.find_by_publisher_and_title = AsyncMock(
            return_value=[sample_series]
        )
        mock_series_repo_cls.return_value = mock_series_repo

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_series_run_id = AsyncMock(return_value=[sample_issue])
        mock_issue_repo_cls.return_value = mock_issue_repo

        browser = CatalogBrowser(mock_session)
        result = await browser.find_comic(
            publisher="Marvel",
            series_title="X-Men",
            issue_number="1",
            year=None,
        )

        # Without year: 30 + 40 + 30 = 90
        assert result.confidence_score == 90
        assert result.year_bonus == 0
        assert result.year_confirmed is False
        assert result.is_high_confidence  # Still high confidence

    @patch("comic_identity_engine.services.catalog_browser.SeriesRunRepository")
    @patch("comic_identity_engine.services.catalog_browser.IssueRepository")
    async def test_publisher_normalization(
        self,
        mock_issue_repo_cls,
        mock_series_repo_cls,
        mock_session,
        sample_series,
        sample_issue,
    ):
        """Test publisher name normalization."""
        # Setup mock repositories
        mock_series_repo = MagicMock()
        mock_series_repo.find_by_publisher_and_title = AsyncMock(
            return_value=[sample_series]
        )
        mock_series_repo_cls.return_value = mock_series_repo

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_series_run_id = AsyncMock(return_value=[sample_issue])
        mock_issue_repo_cls.return_value = mock_issue_repo

        browser = CatalogBrowser(mock_session)

        # Test various publisher aliases
        for publisher_alias in ["Marvel", "marvel", "Marvel Comics"]:
            result = await browser.find_comic(
                publisher=publisher_alias,
                series_title="X-Men",
                issue_number="1",
            )
            assert result.publisher_score == 30

    @patch("comic_identity_engine.services.catalog_browser.SeriesRunRepository")
    @patch("comic_identity_engine.services.catalog_browser.IssueRepository")
    async def test_series_title_normalization(
        self,
        mock_issue_repo_cls,
        mock_series_repo_cls,
        mock_session,
        sample_series,
        sample_issue,
    ):
        """Test series title normalization."""
        # Setup mock repositories
        mock_series_repo = MagicMock()
        mock_series_repo.find_by_publisher_and_title = AsyncMock(
            return_value=[sample_series]
        )
        mock_series_repo_cls.return_value = mock_series_repo

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_series_run_id = AsyncMock(return_value=[sample_issue])
        mock_issue_repo_cls.return_value = mock_issue_repo

        browser = CatalogBrowser(mock_session)

        # Test various series title formats
        for series_title in ["X-Men", "x-men", "THE X-MEN"]:
            result = await browser.find_comic(
                publisher="Marvel",
                series_title=series_title,
                issue_number="1",
            )
            assert result.series_score >= 25

    @patch("comic_identity_engine.services.catalog_browser.SeriesRunRepository")
    @patch("comic_identity_engine.services.catalog_browser.IssueRepository")
    async def test_issue_number_special_cases(
        self,
        mock_issue_repo_cls,
        mock_series_repo_cls,
        mock_session,
        sample_series,
    ):
        """Test issue number matching with special cases."""
        # Setup mock repositories
        mock_series_repo = MagicMock()
        mock_series_repo.find_by_publisher_and_title = AsyncMock(
            return_value=[sample_series]
        )
        mock_series_repo_cls.return_value = mock_series_repo

        # Test special issue number "-1"
        issue_neg1 = MagicMock()
        issue_neg1.id = uuid.uuid4()
        issue_neg1.issue_number = "-1"
        issue_neg1.cover_date = datetime(1991, 1, 1)
        issue_neg1.series_run_id = FIXED_SERIES_RUN_ID

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_series_run_id = AsyncMock(return_value=[issue_neg1])
        mock_issue_repo_cls.return_value = mock_issue_repo

        browser = CatalogBrowser(mock_session)
        result = await browser.find_comic(
            publisher="Marvel",
            series_title="X-Men",
            issue_number="-1",
        )

        assert result.issue_score >= 25  # Should match with normalized or exact

    def test_normalize_publisher(self):
        """Test publisher normalization method."""
        session = MagicMock()
        browser = CatalogBrowser(session)

        assert browser._normalize_publisher("Marvel") == "Marvel"
        assert browser._normalize_publisher("marvel") == "Marvel"
        assert browser._normalize_publisher("Marvel Comics") == "Marvel"
        assert browser._normalize_publisher("DC") == "DC Comics"
        assert browser._normalize_publisher("Image") == "Image Comics"

    def test_normalize_series_title(self):
        """Test series title normalization method."""
        session = MagicMock()
        browser = CatalogBrowser(session)

        assert browser._normalize_series_title("X-Men") == "xmen"
        assert browser._normalize_series_title("The X-Men") == "xmen"
        assert browser._normalize_series_title("  Batman  ") == "batman"

    def test_normalize_issue_number(self):
        """Test issue number normalization method."""
        session = MagicMock()
        browser = CatalogBrowser(session)

        assert browser._normalize_issue_number("1") == "1"
        assert browser._normalize_issue_number(" 1 ") == "1"
        assert browser._normalize_issue_number("½") == "½"
        assert browser._normalize_issue_number(" ½ ") == "½"

    def test_year_matches(self):
        """Test year matching with tolerance."""
        session = MagicMock()
        browser = CatalogBrowser(session)

        cover_date = datetime(1963, 9, 1)

        # Within 1 year tolerance
        assert browser._year_matches(1963, cover_date) is True
        assert browser._year_matches(1962, cover_date) is True
        assert browser._year_matches(1964, cover_date) is True

        # Outside tolerance
        assert browser._year_matches(1961, cover_date) is False
        assert browser._year_matches(1965, cover_date) is False

    def test_publishers_match(self):
        """Test publisher matching logic."""
        session = MagicMock()
        browser = CatalogBrowser(session)

        assert browser._publishers_match("Marvel", "Marvel") is True
        assert browser._publishers_match("Marvel", "marvel") is True
        assert browser._publishers_match("Marvel", "Marvel Comics") is True
        assert browser._publishers_match("Marvel", "DC") is False

    def test_series_titles_match_exact(self):
        """Test exact series title matching."""
        session = MagicMock()
        browser = CatalogBrowser(session)

        assert browser._series_titles_match_exact("X-Men", "X-Men") is True
        assert browser._series_titles_match_exact("X-Men", "x-men") is True
        assert browser._series_titles_match_exact("X-Men", "The X-Men") is True
        assert browser._series_titles_match_exact("X-Men", "Batman") is False

    def test_series_titles_match_normalized(self):
        """Test normalized series title matching."""
        session = MagicMock()
        browser = CatalogBrowser(session)

        assert browser._series_titles_match_normalized("X-Men Vol. 2", "X-Men") is True
        assert (
            browser._series_titles_match_normalized("Batman Vol. 1", "Batman") is True
        )

    def test_issue_numbers_match_exact(self):
        """Test exact issue number matching."""
        session = MagicMock()
        browser = CatalogBrowser(session)

        assert browser._issue_numbers_match_exact("1", "1") is True
        assert browser._issue_numbers_match_exact("1", " 1 ") is True
        assert browser._issue_numbers_match_exact("1", "2") is False

    def test_issue_numbers_match_normalized(self):
        """Test normalized issue number matching."""
        session = MagicMock()
        browser = CatalogBrowser(session)

        assert browser._issue_numbers_match_normalized("-1", "−1") is True
        assert browser._issue_numbers_match_normalized("-1", "negative 1") is True
        assert browser._issue_numbers_match_normalized("½", "0.5") is True
        assert browser._issue_numbers_match_normalized("½", "1/2") is True

    @patch("comic_identity_engine.services.catalog_browser.SeriesRunRepository")
    @patch("comic_identity_engine.services.catalog_browser.IssueRepository")
    async def test_multiple_issue_candidates_selects_best(
        self,
        mock_issue_repo_cls,
        mock_series_repo_cls,
        mock_session,
        sample_series,
    ):
        """Test that browser selects best match from multiple candidates."""
        # Setup mock repositories
        mock_series_repo = MagicMock()
        mock_series_repo.find_by_publisher_and_title = AsyncMock(
            return_value=[sample_series]
        )
        mock_series_repo_cls.return_value = mock_series_repo

        # Create multiple issue candidates
        issue1 = MagicMock()
        issue1.id = uuid.uuid4()
        issue1.issue_number = "1"
        issue1.cover_date = datetime(1963, 9, 1)
        issue1.series_run_id = FIXED_SERIES_RUN_ID

        issue2 = MagicMock()
        issue2.id = uuid.uuid4()
        issue2.issue_number = "1"
        issue2.cover_date = datetime(1975, 1, 1)
        issue2.series_run_id = FIXED_SERIES_RUN_ID

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_series_run_id = AsyncMock(return_value=[issue1, issue2])
        mock_issue_repo_cls.return_value = mock_issue_repo

        browser = CatalogBrowser(mock_session)
        result = await browser.find_comic(
            publisher="Marvel",
            series_title="X-Men",
            issue_number="1",
            year=1963,
        )

        # Should select issue1 because year matches
        assert result.issue_id == issue1.id
        assert result.year_confirmed is True

    def test_no_match_result(self):
        """Test no-match result creation."""
        session = MagicMock()
        browser = CatalogBrowser(session)

        result = browser._no_match_result(
            publisher="Test Publisher",
            series_title="Test Series",
            issue_number="999",
            year=9999,
        )

        assert result.issue_id is None
        assert result.series_run_id is None
        assert result.confidence_score == 0
        assert result.found_via == "none"
        assert result.match_explanation == "No match found in catalog"

    def test_score_publisher_match(self):
        """Test publisher match scoring."""
        session = MagicMock()
        browser = CatalogBrowser(session)

        assert browser._score_publisher_match("Marvel", "Marvel") == 30
        assert browser._score_publisher_match("Marvel", "DC") == 0

    def test_score_series_match(self):
        """Test series match scoring."""
        session = MagicMock()
        browser = CatalogBrowser(session)

        assert browser._score_series_match("X-Men", "X-Men") == 30
        assert browser._score_series_match("X-Men", "x-men") == 30
        assert browser._score_series_match("X-Men Vol. 2", "X-Men") == 25
        assert browser._score_series_match("X-Men", "Batman") == 0

    def test_score_issue_match(self):
        """Test issue match scoring."""
        session = MagicMock()
        browser = CatalogBrowser(session)

        assert browser._score_issue_match("1", "1") == 30
        assert browser._score_issue_match("1", " 1 ") == 30
        assert browser._score_issue_match("-1", "−1") == 25
        assert browser._score_issue_match("1", "2") == 0

    def test_catalog_match_result_to_dict(self):
        """Test CatalogMatchResult serialization to dict."""
        result = CatalogMatchResult(
            issue_id=FIXED_ISSUE_ID,
            series_run_id=FIXED_SERIES_RUN_ID,
            publisher="Marvel",
            series_title="X-Men",
            issue_number="1",
            year=1963,
            confidence_score=100,
            match_explanation="Perfect match",
            found_via="catalog",
            year_confirmed=True,
            publisher_score=30,
            series_score=40,
            issue_score=30,
            year_bonus=10,
        )

        result_dict = result.to_dict()

        assert result_dict["issue_id"] == str(FIXED_ISSUE_ID)
        assert result_dict["series_run_id"] == str(FIXED_SERIES_RUN_ID)
        assert result_dict["publisher"] == "Marvel"
        assert result_dict["confidence_score"] == 100
        assert result_dict["is_high_confidence"] is True

    def test_catalog_match_result_is_high_confidence(self):
        """Test is_high_confidence property."""
        result_high = CatalogMatchResult(
            issue_id=FIXED_ISSUE_ID,
            series_run_id=FIXED_SERIES_RUN_ID,
            publisher="Marvel",
            series_title="X-Men",
            issue_number="1",
            year=1963,
            confidence_score=90,
            match_explanation="High confidence",
            found_via="catalog",
        )

        result_low = CatalogMatchResult(
            issue_id=None,
            series_run_id=None,
            publisher="Marvel",
            series_title="X-Men",
            issue_number="1",
            year=1963,
            confidence_score=89,
            match_explanation="Low confidence",
            found_via="none",
        )

        assert result_high.is_high_confidence is True
        assert result_low.is_high_confidence is False
