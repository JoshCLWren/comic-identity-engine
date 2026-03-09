"""Tests for identity resolver service."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from comic_identity_engine.services.identity_resolver import (
    IdentityResolver,
    ResolutionResult,
    MatchCandidate,
)
from comic_identity_engine.services.url_parser import ParsedUrl
from comic_identity_engine.errors import ResolutionError, ValidationError

# Fixed UUIDs for deterministic tests
FIXED_SERIES_RUN_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
FIXED_ISSUE_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")
FIXED_MAPPING_ISSUE_ID = uuid.UUID("00000000-0000-4000-8000-000000000003")
FIXED_SERIES2_ID = uuid.UUID("00000000-0000-4000-8000-000000000004")
FIXED_SERIES3_ID = uuid.UUID("00000000-0000-4000-8000-000000000005")
FIXED_ISSUE2_ID = uuid.UUID("00000000-0000-4000-8000-000000000006")
FIXED_RESULT_ID = uuid.UUID("00000000-0000-4000-8000-000000000007")


@pytest.fixture
def mock_session():
    """Create mock database session."""
    return AsyncMock()


@pytest.fixture
def sample_issue():
    """Create sample issue entity."""
    issue = MagicMock()
    issue.id = FIXED_ISSUE_ID
    issue.issue_number = "-1"
    issue.upc = "75960601772099911"
    issue.series_run_id = FIXED_SERIES_RUN_ID

    series = MagicMock()
    series.id = FIXED_SERIES_RUN_ID
    series.title = "X-Men"
    series.start_year = 1991

    issue.series_run = series
    return issue


@pytest.fixture
def sample_mapping():
    """Create sample external mapping."""
    mapping = MagicMock()
    mapping.issue_id = FIXED_MAPPING_ISSUE_ID
    mapping.source = "gcd"
    mapping.source_issue_id = "125295"
    mapping.source_series_id = "4254"
    return mapping


@pytest.mark.asyncio
class TestIdentityResolver:
    """Tests for IdentityResolver class."""

    @patch("comic_identity_engine.services.identity_resolver.ExternalMappingRepository")
    @patch("comic_identity_engine.services.identity_resolver.IssueRepository")
    async def test_resolve_by_existing_mapping(
        self,
        mock_issue_repo_cls,
        mock_mapping_repo_cls,
        mock_session,
        sample_issue,
        sample_mapping,
    ):
        """Test resolution via existing external mapping."""
        mock_mapping_repo = MagicMock()
        mock_mapping_repo.find_by_source = AsyncMock(return_value=sample_mapping)
        mock_mapping_repo_cls.return_value = mock_mapping_repo

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_id = AsyncMock(return_value=sample_issue)
        mock_issue_repo_cls.return_value = mock_issue_repo

        resolver = IdentityResolver(mock_session)
        parsed_url = ParsedUrl(platform="gcd", source_issue_id="125295")

        result = await resolver.resolve_issue(parsed_url)

        assert result.issue_id == sample_issue.id
        assert result.best_match is not None
        assert result.best_match.issue_confidence == 1.0
        assert "existing external mapping" in result.explanation.lower()

    @patch("comic_identity_engine.services.identity_resolver.ExternalMappingRepository")
    @patch("comic_identity_engine.services.identity_resolver.IssueRepository")
    async def test_resolve_by_upc(
        self, mock_issue_repo_cls, mock_mapping_repo_cls, mock_session, sample_issue
    ):
        """Test resolution via UPC exact match."""
        mock_mapping_repo = MagicMock()
        mock_mapping_repo.find_by_source = AsyncMock(return_value=None)
        mock_mapping_repo_cls.return_value = mock_mapping_repo

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_upc = AsyncMock(return_value=sample_issue)
        mock_issue_repo.find_with_variants = AsyncMock(return_value=sample_issue)
        mock_issue_repo_cls.return_value = mock_issue_repo

        resolver = IdentityResolver(mock_session)
        parsed_url = ParsedUrl(platform="gcd", source_issue_id="125295")

        result = await resolver.resolve_issue(parsed_url, upc="75960601772099911")

        assert result.issue_id == sample_issue.id
        assert result.best_match.issue_confidence == 1.0
        assert "upc exact match" in result.best_match.match_reason.lower()

    @patch("comic_identity_engine.services.identity_resolver.ExternalMappingRepository")
    @patch("comic_identity_engine.services.identity_resolver.IssueRepository")
    @patch("comic_identity_engine.services.identity_resolver.SeriesRunRepository")
    async def test_resolve_by_upc_not_found_falls_back_to_series_match(
        self,
        mock_series_repo_cls,
        mock_issue_repo_cls,
        mock_mapping_repo_cls,
        mock_session,
        sample_issue,
    ):
        """Test that when UPC is not found, it falls back to series matching."""
        mock_mapping_repo = MagicMock()
        mock_mapping_repo.find_by_source = AsyncMock(return_value=None)
        mock_mapping_repo_cls.return_value = mock_mapping_repo

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_upc = AsyncMock(return_value=None)
        mock_issue_repo.find_by_number = AsyncMock(return_value=sample_issue)
        mock_issue_repo.find_with_variants = AsyncMock(return_value=sample_issue)
        mock_issue_repo_cls.return_value = mock_issue_repo

        mock_series_repo = MagicMock()
        mock_series_repo.find_by_title = AsyncMock(return_value=sample_issue.series_run)
        mock_series_repo_cls.return_value = mock_series_repo

        resolver = IdentityResolver(mock_session)
        parsed_url = ParsedUrl(platform="gcd", source_issue_id="125295")

        result = await resolver.resolve_issue(
            parsed_url,
            upc="75960601772099911",
            series_title="X-Men",
            issue_number="-1",
            series_start_year=1991,
        )

        assert result.issue_id == sample_issue.id
        assert result.best_match.issue_confidence == 0.95

    @patch("comic_identity_engine.services.identity_resolver.ExternalMappingRepository")
    @patch("comic_identity_engine.services.identity_resolver.IssueRepository")
    @patch("comic_identity_engine.services.identity_resolver.SeriesRunRepository")
    async def test_resolve_by_series_issue_year(
        self,
        mock_series_repo_cls,
        mock_issue_repo_cls,
        mock_mapping_repo_cls,
        mock_session,
        sample_issue,
    ):
        """Test resolution via series + issue + year."""
        mock_mapping_repo = MagicMock()
        mock_mapping_repo.find_by_source = AsyncMock(return_value=None)
        mock_mapping_repo_cls.return_value = mock_mapping_repo

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_upc = AsyncMock(return_value=None)
        mock_issue_repo.find_by_number = AsyncMock(return_value=sample_issue)
        mock_issue_repo_cls.return_value = mock_issue_repo

        mock_series_repo = MagicMock()
        mock_series_repo.find_by_title = AsyncMock(return_value=sample_issue.series_run)
        mock_series_repo_cls.return_value = mock_series_repo

        resolver = IdentityResolver(mock_session)
        parsed_url = ParsedUrl(platform="gcd", source_issue_id="125295")

        result = await resolver.resolve_issue(
            parsed_url, series_title="X-Men", issue_number="-1", series_start_year=1991
        )

        assert result.issue_id == sample_issue.id
        assert result.best_match.issue_confidence == 0.95

    @patch("comic_identity_engine.services.identity_resolver.ExternalMappingRepository")
    @patch("comic_identity_engine.services.identity_resolver.IssueRepository")
    @patch("comic_identity_engine.services.identity_resolver.SeriesRunRepository")
    async def test_resolve_by_series_issue_year_falls_back_to_series_issue(
        self,
        mock_series_repo_cls,
        mock_issue_repo_cls,
        mock_mapping_repo_cls,
        mock_session,
        sample_issue,
    ):
        """Test that series+issue+year falls back to series+issue when year match fails."""
        mock_mapping_repo = MagicMock()
        mock_mapping_repo.find_by_source = AsyncMock(return_value=None)
        mock_mapping_repo_cls.return_value = mock_mapping_repo

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_upc = AsyncMock(return_value=None)
        mock_issue_repo.find_by_number = AsyncMock(return_value=sample_issue)
        mock_issue_repo_cls.return_value = mock_issue_repo

        def find_by_title_side_effect(title, year=None):
            if year == 1999:
                return None
            return sample_issue.series_run

        mock_series_repo = MagicMock()
        mock_series_repo.find_by_title = AsyncMock(
            side_effect=find_by_title_side_effect
        )
        mock_series_repo_cls.return_value = mock_series_repo

        resolver = IdentityResolver(mock_session)
        parsed_url = ParsedUrl(platform="gcd", source_issue_id="125295")

        result = await resolver.resolve_issue(
            parsed_url, series_title="X-Men", issue_number="-1", series_start_year=1999
        )

        assert result.issue_id == sample_issue.id
        assert result.best_match.issue_confidence == 0.85
        assert "series + issue" in result.best_match.match_reason.lower()

    @patch("comic_identity_engine.services.identity_resolver.ExternalMappingRepository")
    @patch("comic_identity_engine.services.identity_resolver.IssueRepository")
    @patch("comic_identity_engine.services.identity_resolver.SeriesRunRepository")
    async def test_resolve_by_series_issue_no_year(
        self,
        mock_series_repo_cls,
        mock_issue_repo_cls,
        mock_mapping_repo_cls,
        mock_session,
        sample_issue,
    ):
        """Test resolution via series + issue (no year)."""
        mock_mapping_repo = MagicMock()
        mock_mapping_repo.find_by_source = AsyncMock(return_value=None)
        mock_mapping_repo_cls.return_value = mock_mapping_repo

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_upc = AsyncMock(return_value=None)
        mock_issue_repo.find_by_number = AsyncMock(return_value=sample_issue)
        mock_issue_repo_cls.return_value = mock_issue_repo

        mock_series_repo = MagicMock()
        mock_series_repo.find_by_title = AsyncMock(return_value=sample_issue.series_run)
        mock_series_repo_cls.return_value = mock_series_repo

        resolver = IdentityResolver(mock_session)
        parsed_url = ParsedUrl(platform="gcd", source_issue_id="125295")

        result = await resolver.resolve_issue(
            parsed_url, series_title="X-Men", issue_number="-1"
        )

        assert result.issue_id == sample_issue.id
        assert result.best_match.issue_confidence == 0.85

    @patch("comic_identity_engine.services.identity_resolver.ExternalMappingRepository")
    @patch("comic_identity_engine.services.identity_resolver.IssueRepository")
    @patch("comic_identity_engine.services.identity_resolver.SeriesRunRepository")
    async def test_resolve_creates_new_issue(
        self,
        mock_series_repo_cls,
        mock_issue_repo_cls,
        mock_mapping_repo_cls,
        mock_session,
    ):
        """Test resolution creates new issue when no match."""
        from unittest.mock import AsyncMock, MagicMock

        mock_mapping_repo = MagicMock()
        mock_mapping_repo.find_by_source = AsyncMock(return_value=None)
        mock_mapping_repo_cls.return_value = mock_mapping_repo

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_upc = AsyncMock(return_value=None)
        mock_issue_repo.find_by_number = AsyncMock(return_value=None)
        mock_issue_repo_cls.return_value = mock_issue_repo

        mock_series_repo = MagicMock()
        mock_series_repo.find_by_title = AsyncMock(return_value=None)
        mock_series_repo.create = AsyncMock()
        mock_series_repo.create = AsyncMock()
        mock_series_repo_cls.return_value = mock_series_repo

        new_series = MagicMock()
        new_series.id = FIXED_SERIES2_ID

        mock_series_repo.create = AsyncMock(return_value=new_series)

        new_issue = MagicMock()
        new_issue.id = FIXED_SERIES2_ID
        new_issue.issue_number = "1"
        mock_issue_repo.create = AsyncMock(return_value=new_issue)

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[])
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        resolver = IdentityResolver(mock_session)
        parsed_url = ParsedUrl(platform="gcd", source_issue_id="999999")

        result = await resolver.resolve_issue(
            parsed_url,
            series_title="X-Men",
            series_start_year=1991,
            issue_number="1",
        )

        assert result.created_new is True
        assert result.issue_id == new_issue.id
        assert "created new issue" in result.explanation.lower()

    @patch("comic_identity_engine.services.identity_resolver.ExternalMappingRepository")
    @patch("comic_identity_engine.services.identity_resolver.IssueRepository")
    @patch("comic_identity_engine.services.identity_resolver.SeriesRunRepository")
    async def test_resolve_rejects_placeholder_creation_metadata(
        self,
        mock_series_repo_cls,
        mock_issue_repo_cls,
        mock_mapping_repo_cls,
        mock_session,
    ):
        """Placeholder metadata should not create a new canonical issue."""
        mock_mapping_repo = MagicMock()
        mock_mapping_repo.find_by_source = AsyncMock(return_value=None)
        mock_mapping_repo_cls.return_value = mock_mapping_repo

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_upc = AsyncMock(return_value=None)
        mock_issue_repo_cls.return_value = mock_issue_repo

        mock_series_repo = MagicMock()
        mock_series_repo.find_by_title = AsyncMock(return_value=None)
        mock_series_repo_cls.return_value = mock_series_repo

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[])
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        resolver = IdentityResolver(mock_session)
        parsed_url = ParsedUrl(platform="gcd", source_issue_id="999999")

        with pytest.raises(ValidationError, match="placeholder series metadata"):
            await resolver.resolve_issue(
                parsed_url,
                series_title="Unknown Series",
                issue_number="1",
            )


@pytest.mark.asyncio
class TestMatchCandidate:
    """Tests for MatchCandidate dataclass."""

    async def test_match_candidate_calculates_overall_confidence(self):
        """Test MatchCandidate calculates overall confidence."""
        candidate = MatchCandidate(
            issue_id=FIXED_ISSUE_ID,
            series_run_id=FIXED_SERIES_RUN_ID,
            issue_number="-1",
            series_title="X-Men",
            series_start_year=1991,
            match_reason="Test match",
            issue_confidence=0.95,
            variant_confidence=0.9,
        )

        assert candidate.overall_confidence == 0.855

    async def test_match_candidate_default_variant_confidence(self):
        """Test MatchCandidate defaults variant confidence to 1.0."""
        candidate = MatchCandidate(
            issue_id=FIXED_ISSUE2_ID,
            series_run_id=FIXED_SERIES2_ID,
            issue_number="-1",
            series_title="X-Men",
            series_start_year=1991,
            match_reason="Test match",
            issue_confidence=0.95,
        )

        assert candidate.variant_confidence == 1.0
        assert candidate.overall_confidence == 0.95


@pytest.mark.asyncio
class TestResolutionResult:
    """Tests for ResolutionResult dataclass."""

    async def test_resolution_result_defaults(self):
        """Test ResolutionResult default values."""
        result = ResolutionResult(issue_id=FIXED_RESULT_ID)

        assert result.matches == []
        assert result.best_match is None
        assert result.created_new is False
        assert result.explanation == ""


@pytest.mark.asyncio
class TestFuzzyMatching:
    """Tests for fuzzy title matching functionality."""

    @patch("comic_identity_engine.services.identity_resolver.ExternalMappingRepository")
    @patch("comic_identity_engine.services.identity_resolver.IssueRepository")
    @patch("comic_identity_engine.services.identity_resolver.SeriesRunRepository")
    async def test_fuzzy_match_without_issue_number_requires_manual_review(
        self,
        mock_series_repo_cls,
        mock_issue_repo_cls,
        mock_mapping_repo_cls,
        mock_session,
    ):
        """Series-only fuzzy matches should not create placeholder canonicals."""
        from unittest.mock import AsyncMock, MagicMock

        mock_mapping_repo = MagicMock()
        mock_mapping_repo.find_by_source = AsyncMock(return_value=None)
        mock_mapping_repo_cls.return_value = mock_mapping_repo

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_upc = AsyncMock(return_value=None)
        mock_issue_repo_cls.return_value = mock_issue_repo

        mock_series1 = MagicMock()
        mock_series1.id = FIXED_SERIES2_ID
        mock_series1.title = "X-Men"
        mock_series1.start_year = 1991

        mock_series2 = MagicMock()
        mock_series2.id = FIXED_SERIES2_ID
        mock_series2.title = "Xmen"
        mock_series2.start_year = 1992

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[mock_series1, mock_series2])
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_series_repo = MagicMock()
        mock_series_repo.find_by_title = AsyncMock(return_value=None)
        new_series = MagicMock()
        new_series.id = FIXED_SERIES2_ID
        mock_series_repo.create = AsyncMock(return_value=new_series)
        mock_series_repo_cls.return_value = mock_series_repo

        new_issue = MagicMock()
        new_issue.id = FIXED_SERIES2_ID
        new_issue.issue_number = "1"
        mock_issue_repo.create = AsyncMock(return_value=new_issue)

        resolver = IdentityResolver(mock_session)
        parsed_url = ParsedUrl(platform="gcd", source_issue_id="999999")

        with pytest.raises(ValidationError, match="start year"):
            await resolver.resolve_issue(parsed_url, series_title="X-Men")

    @patch("comic_identity_engine.services.identity_resolver.ExternalMappingRepository")
    @patch("comic_identity_engine.services.identity_resolver.IssueRepository")
    @patch("comic_identity_engine.services.identity_resolver.SeriesRunRepository")
    async def test_fuzzy_match_below_threshold_requires_manual_review(
        self,
        mock_series_repo_cls,
        mock_issue_repo_cls,
        mock_mapping_repo_cls,
        mock_session,
    ):
        """A fuzzy miss without issue metadata should fail closed."""
        from unittest.mock import AsyncMock, MagicMock

        mock_mapping_repo = MagicMock()
        mock_mapping_repo.find_by_source = AsyncMock(return_value=None)
        mock_mapping_repo_cls.return_value = mock_mapping_repo

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_upc = AsyncMock(return_value=None)
        mock_issue_repo_cls.return_value = mock_issue_repo

        mock_series_repo = MagicMock()
        mock_series_repo.find_by_title = AsyncMock(return_value=None)
        new_series = MagicMock()
        new_series.id = FIXED_SERIES2_ID
        mock_series_repo.create = AsyncMock(return_value=new_series)
        mock_series_repo_cls.return_value = mock_series_repo

        new_issue = MagicMock()
        new_issue.id = FIXED_SERIES2_ID
        new_issue.issue_number = "1"
        mock_issue_repo.create = AsyncMock(return_value=new_issue)

        mock_series = MagicMock()
        mock_series.id = FIXED_SERIES2_ID
        mock_series.title = "Batman"
        mock_series.start_year = 1940

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[mock_series])
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        resolver = IdentityResolver(mock_session)
        parsed_url = ParsedUrl(platform="gcd", source_issue_id="999999")

        with pytest.raises(ValidationError, match="start year"):
            await resolver.resolve_issue(parsed_url, series_title="Superman")

    @patch("comic_identity_engine.services.identity_resolver.ExternalMappingRepository")
    @patch("comic_identity_engine.services.identity_resolver.IssueRepository")
    @patch("comic_identity_engine.services.identity_resolver.SeriesRunRepository")
    async def test_fuzzy_match_with_issue_number_filters_candidates(
        self,
        mock_series_repo_cls,
        mock_issue_repo_cls,
        mock_mapping_repo_cls,
        mock_session,
    ):
        """Test fuzzy matching with issue number returns candidates with issue_id."""
        from unittest.mock import AsyncMock, MagicMock

        mock_mapping_repo = MagicMock()
        mock_mapping_repo.find_by_source = AsyncMock(return_value=None)
        mock_mapping_repo_cls.return_value = mock_mapping_repo

        sample_issue = MagicMock()
        sample_issue.id = FIXED_SERIES2_ID
        sample_issue.series_run_id = FIXED_SERIES2_ID
        sample_issue.issue_number = "-1"

        mock_series = MagicMock()
        mock_series.id = sample_issue.series_run_id
        mock_series.title = "X-Men"
        mock_series.start_year = 1991

        sample_issue.series_run = mock_series

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_upc = AsyncMock(return_value=None)
        mock_issue_repo.find_by_number = AsyncMock(return_value=sample_issue)
        mock_issue_repo_cls.return_value = mock_issue_repo

        mock_series_repo = MagicMock()
        mock_series_repo.find_by_title = AsyncMock(return_value=None)
        mock_series_repo_cls.return_value = mock_series_repo

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[mock_series])
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        resolver = IdentityResolver(mock_session)
        parsed_url = ParsedUrl(platform="gcd", source_issue_id="999999")

        result = await resolver.resolve_issue(
            parsed_url, series_title="X-Men", issue_number="-1"
        )

        assert len(result.matches) > 0
        assert result.best_match is not None
        assert result.best_match.issue_id is not None
        assert result.best_match.issue_id == sample_issue.id
        assert "fuzzy title match" in result.best_match.match_reason.lower()

    @patch("comic_identity_engine.services.identity_resolver.ExternalMappingRepository")
    @patch("comic_identity_engine.services.identity_resolver.IssueRepository")
    @patch("comic_identity_engine.services.identity_resolver.SeriesRunRepository")
    async def test_fuzzy_match_multiple_candidates_with_different_confidence(
        self,
        mock_series_repo_cls,
        mock_issue_repo_cls,
        mock_mapping_repo_cls,
        mock_session,
    ):
        """Test fuzzy matching with issue number returns multiple candidates sorted by confidence."""
        from unittest.mock import AsyncMock, MagicMock

        mock_mapping_repo = MagicMock()
        mock_mapping_repo.find_by_source = AsyncMock(return_value=None)
        mock_mapping_repo_cls.return_value = mock_mapping_repo

        sample_issue = MagicMock()
        sample_issue.id = FIXED_SERIES2_ID
        sample_issue.series_run_id = FIXED_SERIES2_ID
        sample_issue.issue_number = "-1"

        mock_series = MagicMock()
        mock_series.id = sample_issue.series_run_id
        mock_series.title = "X-Men"
        mock_series.start_year = 1991

        sample_issue.series_run = mock_series

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_upc = AsyncMock(return_value=None)
        mock_issue_repo.find_by_number = AsyncMock(return_value=sample_issue)
        mock_issue_repo_cls.return_value = mock_issue_repo

        mock_series_repo = MagicMock()
        mock_series_repo.find_by_title = AsyncMock(return_value=None)
        mock_series_repo_cls.return_value = mock_series_repo

        mock_series1 = MagicMock()
        mock_series1.id = FIXED_SERIES2_ID
        mock_series1.title = "X-Men"
        mock_series1.start_year = 1991

        mock_series2 = MagicMock()
        mock_series2.id = FIXED_SERIES2_ID
        mock_series2.title = "Xmen"
        mock_series2.start_year = 1992

        mock_series3 = MagicMock()
        mock_series3.id = FIXED_SERIES2_ID
        mock_series3.title = "X-MEN"
        mock_series3.start_year = 1993

        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(
            return_value=[mock_series1, mock_series2, mock_series3]
        )
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        resolver = IdentityResolver(mock_session)
        parsed_url = ParsedUrl(platform="gcd", source_issue_id="999999")

        result = await resolver.resolve_issue(
            parsed_url, series_title="X-Men", issue_number="-1"
        )

        assert len(result.matches) > 0
        assert result.best_match is not None
        assert result.best_match.issue_id is not None

        candidates_sorted = sorted(
            result.matches, key=lambda m: m.issue_confidence, reverse=True
        )
        assert result.matches == candidates_sorted[:5]
        for candidate in result.matches:
            assert "fuzzy title match" in candidate.match_reason.lower()
            assert candidate.issue_confidence >= 0.70 * 0.85

    @patch("comic_identity_engine.services.identity_resolver.ExternalMappingRepository")
    @patch("comic_identity_engine.services.identity_resolver.IssueRepository")
    @patch("comic_identity_engine.services.identity_resolver.SeriesRunRepository")
    async def test_rejects_upc_conflict_without_variant_suffix(
        self,
        mock_series_repo_cls,
        mock_issue_repo_cls,
        mock_mapping_repo_cls,
        mock_session,
        sample_issue,
    ):
        """Different UPCs without variant metadata should be rejected."""
        mock_mapping_repo = MagicMock()
        mock_mapping_repo.find_by_source = AsyncMock(return_value=None)
        mock_mapping_repo_cls.return_value = mock_mapping_repo

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_upc = AsyncMock(return_value=None)
        mock_issue_repo.find_by_number = AsyncMock(return_value=sample_issue)
        mock_issue_repo.find_with_variants = AsyncMock(return_value=sample_issue)
        mock_issue_repo_cls.return_value = mock_issue_repo

        mock_series_repo = MagicMock()
        mock_series_repo.find_by_title = AsyncMock(return_value=sample_issue.series_run)
        mock_series_repo_cls.return_value = mock_series_repo

        resolver = IdentityResolver(mock_session)
        parsed_url = ParsedUrl(platform="gcd", source_issue_id="125295")

        with pytest.raises(ValidationError, match="different UPC"):
            await resolver.resolve_issue(
                parsed_url,
                upc="different-upc",
                series_title="X-Men",
                series_start_year=1991,
                issue_number="-1",
            )

    @patch("comic_identity_engine.services.identity_resolver.ExternalMappingRepository")
    @patch("comic_identity_engine.services.identity_resolver.VariantRepository")
    @patch("comic_identity_engine.services.identity_resolver.IssueRepository")
    @patch("comic_identity_engine.services.identity_resolver.SeriesRunRepository")
    async def test_records_variant_on_upc_conflict_with_variant_suffix(
        self,
        mock_series_repo_cls,
        mock_issue_repo_cls,
        mock_variant_repo_cls,
        mock_mapping_repo_cls,
        mock_session,
        sample_issue,
    ):
        """Variant metadata should convert a UPC conflict into a tracked variant."""
        mock_mapping_repo = MagicMock()
        mock_mapping_repo.find_by_source = AsyncMock(return_value=None)
        mock_mapping_repo_cls.return_value = mock_mapping_repo

        mock_variant_repo = MagicMock()
        mock_variant_repo.find_by_issue_and_suffix = AsyncMock(return_value=None)
        mock_variant_repo.create = AsyncMock()
        mock_variant_repo_cls.return_value = mock_variant_repo

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_upc = AsyncMock(return_value=None)
        mock_issue_repo.find_by_number = AsyncMock(return_value=sample_issue)
        mock_issue_repo.find_with_variants = AsyncMock(return_value=sample_issue)
        mock_issue_repo_cls.return_value = mock_issue_repo

        mock_series_repo = MagicMock()
        mock_series_repo.find_by_title = AsyncMock(return_value=sample_issue.series_run)
        mock_series_repo_cls.return_value = mock_series_repo

        resolver = IdentityResolver(mock_session)
        parsed_url = ParsedUrl(platform="gcd", source_issue_id="125295")

        result = await resolver.resolve_issue(
            parsed_url,
            upc="different-upc",
            series_title="X-Men",
            series_start_year=1991,
            issue_number="-1",
            variant_suffix="B",
            variant_name="Variant Cover",
        )

        assert result.issue_id == sample_issue.id
        assert "variant B recorded" in result.explanation
        mock_variant_repo.create.assert_awaited_once()

    @patch("comic_identity_engine.services.identity_resolver.ExternalMappingRepository")
    async def test_resolve_issue_raises_resolution_error_on_exception(
        self,
        mock_mapping_repo_cls,
        mock_session,
    ):
        """Test resolve_issue raises ResolutionError when an exception occurs."""
        from unittest.mock import AsyncMock, MagicMock
        from sqlalchemy.exc import SQLAlchemyError

        mock_mapping_repo = MagicMock()
        mock_mapping_repo.find_by_source = AsyncMock(
            side_effect=SQLAlchemyError("Database error")
        )
        mock_mapping_repo_cls.return_value = mock_mapping_repo

        resolver = IdentityResolver(mock_session)
        parsed_url = ParsedUrl(platform="gcd", source_issue_id="999999")

        with pytest.raises(ResolutionError) as exc_info:
            await resolver.resolve_issue(parsed_url)

        assert "Failed to resolve issue" in str(exc_info.value)
        assert exc_info.value.source == "resolver"

    @patch("comic_identity_engine.services.identity_resolver.IssueRepository")
    async def test_match_by_upc_returns_none_when_not_found(
        self, mock_issue_repo_cls, mock_session
    ):
        """Test _match_by_upc returns None when UPC not found."""
        from unittest.mock import AsyncMock, MagicMock

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_upc = AsyncMock(return_value=None)
        mock_issue_repo_cls.return_value = mock_issue_repo

        resolver = IdentityResolver(mock_session)
        result = await resolver._match_by_upc("123456789")

        assert result is None

    @patch("comic_identity_engine.services.identity_resolver.SeriesRunRepository")
    async def test_match_by_series_issue_year_returns_none_when_series_not_found(
        self, mock_series_repo_cls, mock_session
    ):
        """Test _match_by_series_issue_year returns None when series not found."""
        from unittest.mock import AsyncMock, MagicMock

        mock_series_repo = MagicMock()
        mock_series_repo.find_by_title = AsyncMock(return_value=None)
        mock_series_repo_cls.return_value = mock_series_repo

        resolver = IdentityResolver(mock_session)
        result = await resolver._match_by_series_issue_year("Unknown Series", "1", 2000)

        assert result is None

    @patch("comic_identity_engine.services.identity_resolver.IssueRepository")
    @patch("comic_identity_engine.services.identity_resolver.SeriesRunRepository")
    async def test_match_by_series_issue_year_returns_none_when_issue_not_found(
        self, mock_series_repo_cls, mock_issue_repo_cls, mock_session
    ):
        """Test _match_by_series_issue_year returns None when issue not found."""
        from unittest.mock import AsyncMock, MagicMock

        mock_series = MagicMock()
        mock_series.id = FIXED_SERIES2_ID

        mock_series_repo = MagicMock()
        mock_series_repo.find_by_title = AsyncMock(return_value=mock_series)
        mock_series_repo_cls.return_value = mock_series_repo

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_number = AsyncMock(return_value=None)
        mock_issue_repo_cls.return_value = mock_issue_repo

        resolver = IdentityResolver(mock_session)
        result = await resolver._match_by_series_issue_year("X-Men", "999", 1991)

        assert result is None

    @patch("comic_identity_engine.services.identity_resolver.IssueRepository")
    @patch("comic_identity_engine.services.identity_resolver.SeriesRunRepository")
    async def test_match_by_series_issue_returns_none_when_issue_not_found(
        self, mock_series_repo_cls, mock_issue_repo_cls, mock_session
    ):
        """Test _match_by_series_issue returns None when issue not found."""
        from unittest.mock import AsyncMock, MagicMock

        mock_series = MagicMock()
        mock_series.id = FIXED_SERIES2_ID

        mock_series_repo = MagicMock()
        mock_series_repo.find_by_title = AsyncMock(return_value=mock_series)
        mock_series_repo_cls.return_value = mock_series_repo

        mock_issue_repo = MagicMock()
        mock_issue_repo.find_by_number = AsyncMock(return_value=None)
        mock_issue_repo_cls.return_value = mock_issue_repo

        resolver = IdentityResolver(mock_session)
        result = await resolver._match_by_series_issue("X-Men", "999")

        assert result is None
