"""Tests for database models and repositories."""

import uuid
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import exc as sqlalchemy_exc

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from comic_identity_engine.database.models import (
    ExternalMapping,
    Issue,
    Operation,
    SeriesRun,
    Variant,
)
from comic_identity_engine.database.repositories import (
    ExternalMappingRepository,
    IssueRepository,
    OperationRepository,
    SeriesRunRepository,
    VariantRepository,
)
from comic_identity_engine.errors import (
    DuplicateEntityError,
    EntityNotFoundError,
    RepositoryError,
)


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create a mock database session."""
    return AsyncMock(spec=AsyncSession)


class TestSeriesRunRepository:
    """Tests for SeriesRunRepository."""

    def test_init(self, mock_session: AsyncMock) -> None:
        """Test repository initialization."""
        repo = SeriesRunRepository(mock_session)
        assert repo.session is mock_session

    @pytest.mark.asyncio
    async def test_find_by_id(self, mock_session: AsyncMock) -> None:
        """Test finding series run by ID."""
        repo = SeriesRunRepository(mock_session)
        test_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = SeriesRun(
            id=test_id,
            title="X-Men",
            start_year=1991,
            publisher="Marvel Comics",
        )

        mock_session.execute.return_value = mock_result

        result = await repo.find_by_id(test_id)

        assert result is not None
        assert result.id == test_id
        assert result.title == "X-Men"
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_by_title(self, mock_session: AsyncMock) -> None:
        """Test finding series run by title."""
        repo = SeriesRunRepository(mock_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = SeriesRun(
            id=uuid.uuid4(),
            title="X-Men",
            start_year=1991,
            publisher="Marvel Comics",
        )

        mock_session.execute.return_value = mock_result

        result = await repo.find_by_title("X-Men", 1991)

        assert result is not None
        assert result.title == "X-Men"
        assert result.start_year == 1991

    @pytest.mark.asyncio
    async def test_create(self, mock_session: AsyncMock) -> None:
        """Test creating a series run."""
        repo = SeriesRunRepository(mock_session)

        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        series_run = await repo.create(
            title="X-Men",
            start_year=1991,
            publisher="Marvel Comics",
        )

        assert series_run.title == "X-Men"
        assert series_run.start_year == 1991
        assert series_run.publisher == "Marvel Comics"
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()


class TestIssueRepository:
    """Tests for IssueRepository."""

    def test_init(self, mock_session: AsyncMock) -> None:
        """Test repository initialization."""
        repo = IssueRepository(mock_session)
        assert repo.session is mock_session

    @pytest.mark.asyncio
    async def test_find_by_id(self, mock_session: AsyncMock) -> None:
        """Test finding issue by ID."""
        repo = IssueRepository(mock_session)
        test_id = uuid.uuid4()

        mock_result = MagicMock()
        series_run = SeriesRun(
            id=uuid.uuid4(),
            title="X-Men",
            start_year=1991,
        )
        mock_result.scalar_one_or_none.return_value = Issue(
            id=test_id,
            series_run_id=series_run.id,
            issue_number="-1",
        )

        mock_session.execute.return_value = mock_result

        result = await repo.find_by_id(test_id)

        assert result is not None
        assert result.id == test_id
        assert result.issue_number == "-1"

    @pytest.mark.asyncio
    async def test_find_by_number(self, mock_session: AsyncMock) -> None:
        """Test finding issue by series run and issue number."""
        repo = IssueRepository(mock_session)
        series_run_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = Issue(
            id=uuid.uuid4(),
            series_run_id=series_run_id,
            issue_number="-1",
        )

        mock_session.execute.return_value = mock_result

        result = await repo.find_by_number(series_run_id, "-1")

        assert result is not None
        assert result.issue_number == "-1"

    @pytest.mark.asyncio
    async def test_find_by_upc(self, mock_session: AsyncMock) -> None:
        """Test finding issue by UPC."""
        repo = IssueRepository(mock_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = Issue(
            id=uuid.uuid4(),
            series_run_id=uuid.uuid4(),
            issue_number="-1",
            upc="75960601772099911",
        )

        mock_session.execute.return_value = mock_result

        result = await repo.find_by_upc("75960601772099911")

        assert result is not None
        assert result.upc == "75960601772099911"

    @pytest.mark.asyncio
    async def test_create(self, mock_session: AsyncMock) -> None:
        """Test creating an issue."""
        repo = IssueRepository(mock_session)
        series_run_id = uuid.uuid4()

        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        issue = await repo.create(
            series_run_id=series_run_id,
            issue_number="-1",
            upc="75960601772099911",
        )

        assert issue.issue_number == "-1"
        assert issue.upc == "75960601772099911"
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()


class TestVariantRepository:
    """Tests for VariantRepository."""

    def test_init(self, mock_session: AsyncMock) -> None:
        """Test repository initialization."""
        repo = VariantRepository(mock_session)
        assert repo.session is mock_session

    @pytest.mark.asyncio
    async def test_find_by_id(self, mock_session: AsyncMock) -> None:
        """Test finding variant by ID."""
        repo = VariantRepository(mock_session)
        test_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = Variant(
            id=test_id,
            issue_id=uuid.uuid4(),
            variant_suffix="B",
            variant_name="Variant Edition",
        )

        mock_session.execute.return_value = mock_result

        result = await repo.find_by_id(test_id)

        assert result is not None
        assert result.id == test_id
        assert result.variant_suffix == "B"

    @pytest.mark.asyncio
    async def test_create(self, mock_session: AsyncMock) -> None:
        """Test creating a variant."""
        repo = VariantRepository(mock_session)
        issue_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        variant = await repo.create(
            issue_id=issue_id,
            variant_suffix="B",
            variant_name="Variant Edition",
        )

        assert variant.variant_suffix == "B"
        assert variant.variant_name == "Variant Edition"
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()


class TestExternalMappingRepository:
    """Tests for ExternalMappingRepository."""

    def test_init(self, mock_session: AsyncMock) -> None:
        """Test repository initialization."""
        repo = ExternalMappingRepository(mock_session)
        assert repo.session is mock_session

    @pytest.mark.asyncio
    async def test_find_by_source(self, mock_session: AsyncMock) -> None:
        """Test finding external mapping by source and source issue ID."""
        repo = ExternalMappingRepository(mock_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = ExternalMapping(
            id=uuid.uuid4(),
            issue_id=uuid.uuid4(),
            source="gcd",
            source_issue_id="125295",
        )

        mock_session.execute.return_value = mock_result

        result = await repo.find_by_source("gcd", "125295")

        assert result is not None
        assert result.source == "gcd"
        assert result.source_issue_id == "125295"

    @pytest.mark.asyncio
    async def test_create_mapping(self, mock_session: AsyncMock) -> None:
        """Test creating an external mapping."""
        repo = ExternalMappingRepository(mock_session)
        issue_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        mapping = await repo.create_mapping(
            issue_id=issue_id,
            source="gcd",
            source_issue_id="125295",
            source_series_id="4254",
        )

        assert mapping.source == "gcd"
        assert mapping.source_issue_id == "125295"
        assert mapping.source_series_id == "4254"
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_by_issue(self, mock_session: AsyncMock) -> None:
        """Test finding all external mappings for an issue."""
        repo = ExternalMappingRepository(mock_session)
        issue_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            ExternalMapping(
                id=uuid.uuid4(),
                issue_id=issue_id,
                source="gcd",
                source_issue_id="125295",
            ),
            ExternalMapping(
                id=uuid.uuid4(),
                issue_id=issue_id,
                source="locg",
                source_issue_id="1169529",
            ),
        ]

        mock_session.execute.return_value = mock_result

        result = await repo.find_by_issue(issue_id)

        assert len(result) == 2
        assert result[0].source == "gcd"
        assert result[1].source == "locg"


class TestOperationRepository:
    """Tests for OperationRepository."""

    def test_init(self, mock_session: AsyncMock) -> None:
        """Test repository initialization."""
        repo = OperationRepository(mock_session)
        assert repo.session is mock_session

    @pytest.mark.asyncio
    async def test_create_operation(self, mock_session: AsyncMock) -> None:
        """Test creating an operation."""
        repo = OperationRepository(mock_session)

        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        operation = await repo.create_operation(
            operation_type="import",
            input_hash="abc123",
        )

        assert operation.operation_type == "import"
        assert operation.status == "pending"
        assert operation.input_hash == "abc123"
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_status(self, mock_session: AsyncMock) -> None:
        """Test updating operation status."""
        repo = OperationRepository(mock_session)

        operation = Operation(
            id=uuid.uuid4(),
            operation_type="import",
            status="pending",
        )

        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        result = await repo.update_status(
            operation,
            status="completed",
            result={"success": True},
        )

        assert result.status == "completed"
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_operation(self, mock_session: AsyncMock) -> None:
        """Test finding operation by ID."""
        repo = OperationRepository(mock_session)
        test_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = Operation(
            id=test_id,
            operation_type="import",
            status="pending",
        )

        mock_session.execute.return_value = mock_result

        result = await repo.get_operation(test_id)

        assert result is not None
        assert result.id == test_id

    @pytest.mark.asyncio
    async def test_find_by_status(self, mock_session: AsyncMock) -> None:
        """Test finding operations by status."""
        repo = OperationRepository(mock_session)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            Operation(
                id=uuid.uuid4(),
                operation_type="import",
                status="pending",
            ),
            Operation(
                id=uuid.uuid4(),
                operation_type="export",
                status="pending",
            ),
        ]

        mock_session.execute.return_value = mock_result

        result = await repo.find_by_status("pending")

        assert len(result) == 2
        assert all(op.status == "pending" for op in result)

    @pytest.mark.asyncio
    async def test_find_by_input_hash(self, mock_session: AsyncMock) -> None:
        """Test finding operation by input hash."""
        repo = OperationRepository(mock_session)

        mock_result = MagicMock()
        operation = Operation(
            id=uuid.uuid4(),
            operation_type="import",
            status="completed",
            input_hash="abc123",
        )
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = operation
        mock_result.scalars.return_value = mock_scalars

        mock_session.execute.return_value = mock_result

        result = await repo.find_by_input_hash("abc123")

        assert result is not None
        assert result.input_hash == "abc123"

    @pytest.mark.asyncio
    async def test_find_by_input_hash_returns_newest_duplicate(
        self, mock_session: AsyncMock
    ) -> None:
        """Duplicate input hashes should not crash repository lookup."""
        repo = OperationRepository(mock_session)

        newest = Operation(
            id=uuid.uuid4(),
            operation_type="resolve",
            status="pending",
            input_hash="abc123",
        )
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = newest
        mock_result.scalars.return_value = mock_scalars
        mock_session.execute.return_value = mock_result

        result = await repo.find_by_input_hash("abc123")

        assert result is newest


class TestModelStringRepresentations:
    """Tests for model __str__ and __repr__ methods."""

    def test_series_run_str(self) -> None:
        """Test SeriesRun __str__ method."""
        series = SeriesRun(
            id=uuid.uuid4(),
            title="X-Men",
            start_year=1991,
            publisher="Marvel Comics",
        )
        assert str(series) == "X-Men (1991)"

    def test_series_run_repr(self) -> None:
        """Test SeriesRun __repr__ method."""
        test_id = uuid.uuid4()
        series = SeriesRun(
            id=test_id,
            title="X-Men",
            start_year=1991,
        )
        repr_str = repr(series)
        assert "SeriesRun" in repr_str
        assert "X-Men" in repr_str
        assert "1991" in repr_str

    def test_issue_str(self) -> None:
        """Test Issue __str__ method."""
        series = SeriesRun(
            id=uuid.uuid4(),
            title="X-Men",
            start_year=1991,
        )
        issue = Issue(
            id=uuid.uuid4(),
            series_run_id=series.id,
            series_run=series,
            issue_number="-1",
        )
        assert str(issue) == "X-Men #-1"

    def test_issue_repr(self) -> None:
        """Test Issue __repr__ method."""
        test_id = uuid.uuid4()
        series_run_id = uuid.uuid4()
        issue = Issue(
            id=test_id,
            series_run_id=series_run_id,
            issue_number="-1",
        )
        repr_str = repr(issue)
        assert "Issue" in repr_str
        assert "-1" in repr_str

    def test_variant_str(self) -> None:
        """Test Variant __str__ method."""
        series = SeriesRun(
            id=uuid.uuid4(),
            title="X-Men",
            start_year=1991,
        )
        issue = Issue(
            id=uuid.uuid4(),
            series_run_id=series.id,
            series_run=series,
            issue_number="-1",
        )
        variant = Variant(
            id=uuid.uuid4(),
            issue_id=issue.id,
            issue=issue,
            variant_suffix="B",
        )
        assert str(variant) == "X-Men #-1.B"

    def test_external_mapping_str(self) -> None:
        """Test ExternalMapping __str__ method."""
        mapping = ExternalMapping(
            id=uuid.uuid4(),
            issue_id=uuid.uuid4(),
            source="gcd",
            source_issue_id="125295",
        )
        assert str(mapping) == "gcd:125295"

    def test_operation_str(self) -> None:
        """Test Operation __str__ method."""
        operation = Operation(
            id=uuid.uuid4(),
            operation_type="import",
            status="pending",
        )
        assert str(operation) == "import:pending"


class TestModelRelationships:
    """Tests for model relationships."""

    def test_series_run_issues_relationship(self) -> None:
        """Test SeriesRun to Issue relationship."""
        series = SeriesRun(
            id=uuid.uuid4(),
            title="X-Men",
            start_year=1991,
        )
        issue = Issue(
            id=uuid.uuid4(),
            series_run_id=series.id,
            series_run=series,
            issue_number="-1",
        )

        assert issue.series_run is series
        assert issue in series.issues

    def test_issue_variants_relationship(self) -> None:
        """Test Issue to Variant relationship."""
        issue = Issue(
            id=uuid.uuid4(),
            series_run_id=uuid.uuid4(),
            issue_number="-1",
        )
        variant = Variant(
            id=uuid.uuid4(),
            issue_id=issue.id,
            issue=issue,
            variant_suffix="B",
        )

        assert variant.issue is issue
        assert variant in issue.variants

    def test_issue_external_mappings_relationship(self) -> None:
        """Test Issue to ExternalMapping relationship."""
        issue = Issue(
            id=uuid.uuid4(),
            series_run_id=uuid.uuid4(),
            issue_number="-1",
        )
        mapping = ExternalMapping(
            id=uuid.uuid4(),
            issue_id=issue.id,
            issue=issue,
            source="gcd",
            source_issue_id="125295",
        )

        assert mapping.issue is issue
        assert mapping in issue.external_mappings


class TestModelDefaults:
    """Tests for model default values."""

    def test_series_run_defaults(self) -> None:
        """Test SeriesRun default values."""
        series = SeriesRun(
            id=uuid.uuid4(),
            title="X-Men",
            start_year=1991,
        )
        assert series.publisher is None

    def test_issue_defaults(self) -> None:
        """Test Issue default values."""
        issue = Issue(
            id=uuid.uuid4(),
            series_run_id=uuid.uuid4(),
            issue_number="-1",
        )
        assert issue.cover_date is None
        assert issue.upc is None

    def test_variant_defaults(self) -> None:
        """Test Variant default values."""
        variant = Variant(
            id=uuid.uuid4(),
            issue_id=uuid.uuid4(),
            variant_suffix="B",
        )
        assert variant.variant_name is None

    def test_external_mapping_defaults(self) -> None:
        """Test ExternalMapping default values."""
        mapping = ExternalMapping(
            id=uuid.uuid4(),
            issue_id=uuid.uuid4(),
            source="gcd",
            source_issue_id="125295",
        )
        assert mapping.source_series_id is None

    def test_operation_defaults(self) -> None:
        """Test Operation default values."""
        operation = Operation(
            id=uuid.uuid4(),
            operation_type="import",
            status="pending",
        )
        assert operation.input_hash is None
        assert operation.result is None
        assert operation.error_message is None


class TestSeriesRunRepositoryErrorPaths:
    """Tests for SeriesRunRepository error paths."""

    @pytest.mark.asyncio
    async def test_create_database_error(self, mock_session: AsyncMock) -> None:
        """Test creating series run with database error."""
        repo = SeriesRunRepository(mock_session)
        mock_session.flush = AsyncMock(
            side_effect=sqlalchemy_exc.SQLAlchemyError("Database connection failed")
        )

        with pytest.raises(RepositoryError) as exc_info:
            await repo.create(title="X-Men", start_year=1991)

        assert "Failed to create series run" in str(exc_info.value)
        assert exc_info.value.original_error is not None

    @pytest.mark.asyncio
    async def test_update_success(self, mock_session: AsyncMock) -> None:
        """Test updating series run successfully."""
        repo = SeriesRunRepository(mock_session)
        test_id = uuid.uuid4()
        series_run = SeriesRun(
            id=test_id,
            title="X-Men",
            start_year=1991,
            publisher="Marvel Comics",
        )

        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        result = await repo.update(series_run)

        assert result.id == test_id
        mock_session.add.assert_called_once_with(series_run)
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_database_error(self, mock_session: AsyncMock) -> None:
        """Test updating series run with database error."""
        repo = SeriesRunRepository(mock_session)
        test_id = uuid.uuid4()
        series_run = SeriesRun(
            id=test_id,
            title="X-Men",
            start_year=1991,
        )

        mock_session.flush = AsyncMock(
            side_effect=sqlalchemy_exc.SQLAlchemyError("Database connection failed")
        )

        with pytest.raises(RepositoryError) as exc_info:
            await repo.update(series_run)

        assert "Failed to update series run" in str(exc_info.value)
        assert exc_info.value.original_error is not None

    @pytest.mark.asyncio
    async def test_delete_success(self, mock_session: AsyncMock) -> None:
        """Test deleting series run successfully."""
        repo = SeriesRunRepository(mock_session)
        test_id = uuid.uuid4()
        series_run = SeriesRun(
            id=test_id,
            title="X-Men",
            start_year=1991,
        )

        mock_session.delete = AsyncMock()
        mock_session.flush = AsyncMock()

        await repo.delete(series_run)

        mock_session.delete.assert_called_once_with(series_run)
        mock_session.flush.assert_called_once()


class TestIssueRepositoryErrorPaths:
    """Tests for IssueRepository error paths."""

    @pytest.mark.asyncio
    async def test_create_database_error(self, mock_session: AsyncMock) -> None:
        """Test creating issue with database error."""
        repo = IssueRepository(mock_session)
        series_run_id = uuid.uuid4()

        mock_session.flush = AsyncMock(
            side_effect=sqlalchemy_exc.SQLAlchemyError("Database connection failed")
        )

        with pytest.raises(RepositoryError) as exc_info:
            await repo.create(
                series_run_id=series_run_id,
                issue_number="-1",
            )

        assert "Failed to create issue" in str(exc_info.value)
        assert exc_info.value.original_error is not None

    @pytest.mark.asyncio
    async def test_update_success(self, mock_session: AsyncMock) -> None:
        """Test updating issue successfully."""
        repo = IssueRepository(mock_session)
        test_id = uuid.uuid4()
        series_run = SeriesRun(
            id=uuid.uuid4(),
            title="X-Men",
            start_year=1991,
        )
        issue = Issue(
            id=test_id,
            series_run_id=series_run.id,
            series_run=series_run,
            issue_number="-1",
            upc="75960601772099911",
        )

        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        result = await repo.update(issue)

        assert result.id == test_id
        mock_session.add.assert_called_once_with(issue)
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_database_error(self, mock_session: AsyncMock) -> None:
        """Test updating issue with database error."""
        repo = IssueRepository(mock_session)
        test_id = uuid.uuid4()
        issue = Issue(
            id=test_id,
            series_run_id=uuid.uuid4(),
            issue_number="-1",
        )

        mock_session.flush = AsyncMock(
            side_effect=sqlalchemy_exc.SQLAlchemyError("Database connection failed")
        )

        with pytest.raises(RepositoryError) as exc_info:
            await repo.update(issue)

        assert "Failed to update issue" in str(exc_info.value)
        assert exc_info.value.original_error is not None

    @pytest.mark.asyncio
    async def test_delete_success(self, mock_session: AsyncMock) -> None:
        """Test deleting issue successfully."""
        repo = IssueRepository(mock_session)
        test_id = uuid.uuid4()
        issue = Issue(
            id=test_id,
            series_run_id=uuid.uuid4(),
            issue_number="-1",
        )

        mock_session.delete = AsyncMock()
        mock_session.flush = AsyncMock()

        await repo.delete(issue)

        mock_session.delete.assert_called_once_with(issue)
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_with_variants_success(self, mock_session: AsyncMock) -> None:
        """Test finding issue with variants preloaded."""
        repo = IssueRepository(mock_session)
        test_id = uuid.uuid4()

        mock_result = MagicMock()
        series_run = SeriesRun(
            id=uuid.uuid4(),
            title="X-Men",
            start_year=1991,
        )
        variant = Variant(
            id=uuid.uuid4(),
            issue_id=test_id,
            variant_suffix="B",
        )
        issue = Issue(
            id=test_id,
            series_run_id=series_run.id,
            series_run=series_run,
            issue_number="-1",
            variants=[variant],
        )

        mock_result.scalar_one_or_none.return_value = issue
        mock_session.execute.return_value = mock_result

        result = await repo.find_with_variants(test_id)

        assert result is not None
        assert result.id == test_id
        assert len(result.variants) == 1
        assert result.variants[0].variant_suffix == "B"

    @pytest.mark.asyncio
    async def test_find_with_variants_not_found(self, mock_session: AsyncMock) -> None:
        """Test finding issue with variants when issue doesn't exist."""
        repo = IssueRepository(mock_session)
        test_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repo.find_with_variants(test_id)

        assert result is None


class TestVariantRepositoryErrorPaths:
    """Tests for VariantRepository error paths."""

    @pytest.mark.asyncio
    async def test_create_duplicate_variant(self, mock_session: AsyncMock) -> None:
        """Test creating variant that already exists."""
        repo = VariantRepository(mock_session)
        issue_id = uuid.uuid4()
        existing_variant = Variant(
            id=uuid.uuid4(),
            issue_id=issue_id,
            variant_suffix="B",
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_variant
        mock_session.execute.return_value = mock_result

        with pytest.raises(DuplicateEntityError) as exc_info:
            await repo.create(
                issue_id=issue_id,
                variant_suffix="B",
            )

        assert "Variant with issue_id" in str(exc_info.value)
        assert exc_info.value.entity_type == "Variant"
        assert exc_info.value.existing_id == str(existing_variant.id)

    @pytest.mark.asyncio
    async def test_create_integrity_error(self, mock_session: AsyncMock) -> None:
        """Test creating variant with integrity error."""
        repo = VariantRepository(mock_session)
        issue_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        mock_session.flush = AsyncMock(
            side_effect=sqlalchemy_exc.IntegrityError(
                "INSERT INTO variants", {}, Exception()
            )
        )

        with pytest.raises(DuplicateEntityError) as exc_info:
            await repo.create(
                issue_id=issue_id,
                variant_suffix="B",
            )

        assert "Variant with issue_id" in str(exc_info.value)
        assert exc_info.value.entity_type == "Variant"
        assert exc_info.value.original_error is not None


class TestExternalMappingRepositoryErrorPaths:
    """Tests for ExternalMappingRepository error paths."""

    @pytest.mark.asyncio
    async def test_find_all_by_source(self, mock_session: AsyncMock) -> None:
        """Test finding all mappings by source."""
        repo = ExternalMappingRepository(mock_session)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            ExternalMapping(
                id=uuid.uuid4(),
                issue_id=uuid.uuid4(),
                source="gcd",
                source_issue_id="125295",
            ),
            ExternalMapping(
                id=uuid.uuid4(),
                issue_id=uuid.uuid4(),
                source="gcd",
                source_issue_id="125296",
            ),
        ]

        mock_session.execute.return_value = mock_result

        result = await repo.find_all_by_source("gcd")

        assert len(result) == 2
        assert all(m.source == "gcd" for m in result)

    @pytest.mark.asyncio
    async def test_find_all_by_source_with_limit(self, mock_session: AsyncMock) -> None:
        """Test finding all mappings by source with limit."""
        repo = ExternalMappingRepository(mock_session)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            ExternalMapping(
                id=uuid.uuid4(),
                issue_id=uuid.uuid4(),
                source="gcd",
                source_issue_id="125295",
            ),
        ]

        mock_session.execute.return_value = mock_result

        result = await repo.find_all_by_source("gcd", limit=1)

        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_create_mapping_duplicate(self, mock_session: AsyncMock) -> None:
        """Test creating mapping that already exists."""
        repo = ExternalMappingRepository(mock_session)
        issue_id = uuid.uuid4()
        existing_mapping = ExternalMapping(
            id=uuid.uuid4(),
            issue_id=issue_id,
            source="gcd",
            source_issue_id="125295",
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_mapping
        mock_session.execute.return_value = mock_result

        with pytest.raises(DuplicateEntityError) as exc_info:
            await repo.create_mapping(
                issue_id=issue_id,
                source="gcd",
                source_issue_id="125295",
            )

        assert "External mapping with source=gcd" in str(exc_info.value)
        assert exc_info.value.entity_type == "ExternalMapping"
        assert exc_info.value.existing_id == str(existing_mapping.id)

    @pytest.mark.asyncio
    async def test_create_mapping_integrity_error(
        self, mock_session: AsyncMock
    ) -> None:
        """Test creating mapping with integrity error."""
        repo = ExternalMappingRepository(mock_session)
        issue_id = uuid.uuid4()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        mock_session.flush = AsyncMock(
            side_effect=sqlalchemy_exc.IntegrityError(
                "INSERT INTO external_mappings", {}, Exception()
            )
        )

        with pytest.raises(DuplicateEntityError) as exc_info:
            await repo.create_mapping(
                issue_id=issue_id,
                source="gcd",
                source_issue_id="125295",
            )

        assert "External mapping with source=gcd" in str(exc_info.value)
        assert exc_info.value.entity_type == "ExternalMapping"
        assert exc_info.value.original_error is not None


class TestOperationRepositoryErrorPaths:
    """Tests for OperationRepository error paths."""

    @pytest.mark.asyncio
    async def test_create_operation_database_error(
        self, mock_session: AsyncMock
    ) -> None:
        """Test creating operation with database error."""
        repo = OperationRepository(mock_session)

        mock_session.flush = AsyncMock(
            side_effect=sqlalchemy_exc.SQLAlchemyError("Database connection failed")
        )

        with pytest.raises(RepositoryError) as exc_info:
            await repo.create_operation(operation_type="import")

        assert "Failed to create operation" in str(exc_info.value)
        assert exc_info.value.original_error is not None

    @pytest.mark.asyncio
    async def test_update_status_with_error_message(
        self, mock_session: AsyncMock
    ) -> None:
        """Test updating operation status with error message."""
        repo = OperationRepository(mock_session)
        operation = Operation(
            id=uuid.uuid4(),
            operation_type="import",
            status="pending",
        )

        mock_session.flush = AsyncMock()
        mock_session.refresh = AsyncMock()

        result = await repo.update_status(
            operation,
            status="failed",
            error_message="Connection timeout",
        )

        assert result.status == "failed"
        assert result.error_message == "Connection timeout"
        mock_session.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_status_database_error(self, mock_session: AsyncMock) -> None:
        """Test updating operation status with database error."""
        repo = OperationRepository(mock_session)
        operation = Operation(
            id=uuid.uuid4(),
            operation_type="import",
            status="pending",
        )

        mock_session.flush = AsyncMock(
            side_effect=sqlalchemy_exc.SQLAlchemyError("Database connection failed")
        )

        with pytest.raises(RepositoryError) as exc_info:
            await repo.update_status(operation, status="completed")

        assert "Failed to update operation" in str(exc_info.value)
        assert exc_info.value.original_error is not None


class TestRepositoryErrors:
    """Tests for custom repository error classes."""

    def test_repository_error_basic(self) -> None:
        """Test basic RepositoryError."""
        error = RepositoryError("Database operation failed")
        assert "Database operation failed" in str(error)
        assert error.source == "repository"

    def test_repository_error_with_original_error(self) -> None:
        """Test RepositoryError with original error."""
        original = Exception("Connection lost")
        error = RepositoryError("Database operation failed", original_error=original)
        assert error.original_error is original
        assert "Database operation failed" in str(error)

    def test_duplicate_entity_error_basic(self) -> None:
        """Test basic DuplicateEntityError."""
        error = DuplicateEntityError("Entity already exists")
        assert "Entity already exists" in str(error)

    def test_duplicate_entity_error_with_details(self) -> None:
        """Test DuplicateEntityError with entity type and ID."""
        error = DuplicateEntityError(
            "Variant already exists",
            entity_type="Variant",
            existing_id="123e4567-e89b-12d3-a456-426614174000",
        )
        assert "Variant" in str(error)
        assert "123e4567-e89b-12d3-a456-426614174000" in str(error)
        assert error.entity_type == "Variant"
        assert error.existing_id == "123e4567-e89b-12d3-a456-426614174000"

    def test_duplicate_entity_error_with_original_error(self) -> None:
        """Test DuplicateEntityError with original error."""
        original = Exception("Integrity constraint violation")
        error = DuplicateEntityError(
            "Mapping already exists",
            entity_type="ExternalMapping",
            original_error=original,
        )
        assert error.original_error is original
        assert error.entity_type == "ExternalMapping"

    def test_entity_not_found_error_basic(self) -> None:
        """Test basic EntityNotFoundError."""
        error = EntityNotFoundError("Entity not found")
        assert "Entity not found" in str(error)
        assert error.source == "repository"

    def test_entity_not_found_error_with_details(self) -> None:
        """Test EntityNotFoundError with entity type and ID."""
        error = EntityNotFoundError(
            "Issue not found",
            entity_type="Issue",
            entity_id="123e4567-e89b-12d3-a456-426614174000",
        )
        assert "Issue" in str(error)
        assert "123e4567-e89b-12d3-a456-426614174000" in str(error)
        assert error.entity_type == "Issue"
        assert error.entity_id == "123e4567-e89b-12d3-a456-426614174000"

    def test_entity_not_found_error_with_original_error(self) -> None:
        """Test EntityNotFoundError with original error."""
        original = Exception("No row found")
        error = EntityNotFoundError(
            "Series not found",
            entity_type="SeriesRun",
            original_error=original,
        )
        assert error.original_error is original
        assert error.entity_type == "SeriesRun"

    def test_error_inheritance(self) -> None:
        """Test that repository errors inherit from AdapterError."""
        repo_error = RepositoryError("Test")
        dup_error = DuplicateEntityError("Test")
        not_found_error = EntityNotFoundError("Test")

        from comic_identity_engine.errors import AdapterError

        assert isinstance(repo_error, AdapterError)
        assert isinstance(dup_error, AdapterError)
        assert isinstance(not_found_error, AdapterError)
        assert isinstance(dup_error, RepositoryError)
        assert isinstance(not_found_error, RepositoryError)


class TestIssueStr:
    """Tests for Issue.__str__ method."""

    def test_issue_str_without_series_run(self) -> None:
        """Test Issue.__str__ when series_run is None."""
        issue = Issue(issue_number="1")
        assert str(issue) == "Issue #1"

    def test_issue_str_with_series_run(self) -> None:
        """Test Issue.__str__ when series_run is set."""
        series = SeriesRun(title="X-Men")
        issue = Issue(issue_number="1", series_run=series)
        assert str(issue) == "X-Men #1"


class TestBackwardCompatibility:
    """Tests for backward compatibility imports."""

    def test_database_backward_compatibility_file_exists(self) -> None:
        """Test that the backward compatibility database.py file exists."""
        # This tests that the backward compatibility shim exists
        import os

        root_dir = os.path.dirname(os.path.dirname(__file__))
        compat_file = os.path.join(root_dir, "comic_identity_engine", "database.py")
        assert os.path.exists(compat_file), (
            f"Backward compat file not found: {compat_file}"
        )

        # Check the file contains expected import
        with open(compat_file) as f:
            content = f.read()
            assert "from comic_identity_engine.database.connection import" in content

    def test_database_backward_compatibility_import(self) -> None:
        """Test that the backward compatibility import works."""
        # This import triggers coverage of the backward compatibility module
        from comic_identity_engine import database

        # Verify it exports the expected symbols
        assert hasattr(database, "get_db")
        assert hasattr(database, "AsyncSessionLocal")
        assert hasattr(database, "Base")
