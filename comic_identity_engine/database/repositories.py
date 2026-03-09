"""Repository pattern for database access.

SOURCE: Data access layer abstraction
USAGE:
- SeriesRunRepository: Series CRUD operations
- IssueRepository: Issue CRUD operations
- ExternalMappingRepository: External ID mapping operations
- OperationRepository: Async operation tracking operations

USED BY:
- Service layer for business logic
- API endpoints for data access
- Import/export operations
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Delete, Select, delete, exc as sqlalchemy_exc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from comic_identity_engine.database.models import (
    ExternalMapping,
    Issue,
    Operation,
    SeriesRun,
    Variant,
)
from comic_identity_engine.errors import (
    DuplicateEntityError,
    RepositoryError,
)


logger = logging.getLogger(__name__)

SERIES_RUN_IDENTITY_CONSTRAINT = "uq_series_runs_title_start_year"
ISSUE_IDENTITY_CONSTRAINT = "uq_issues_series_run_id_issue_number"


def _is_unique_constraint_violation(
    error: sqlalchemy_exc.IntegrityError,
    constraint_name: str,
    table_name: str,
    columns: tuple[str, ...],
) -> bool:
    """Return True when an IntegrityError matches a specific unique constraint."""
    diag = getattr(getattr(error, "orig", None), "diag", None)
    if getattr(diag, "constraint_name", None) == constraint_name:
        return True

    message = str(getattr(error, "orig", error)).lower()
    if constraint_name.lower() in message:
        return True

    sqlite_columns = [f"{table_name}.{column}".lower() for column in columns]
    return all(column in message for column in sqlite_columns)


class SeriesRunRepository:
    """Repository for SeriesRun entity operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: Async database session
        """
        self.session = session

    async def find_by_id(
        self,
        series_run_id: uuid.UUID,
    ) -> Optional[SeriesRun]:
        """Find series run by ID.

        Args:
            series_run_id: UUID of the series run

        Returns:
            SeriesRun entity or None if not found
        """
        stmt: Select[SeriesRun] = select(SeriesRun).where(SeriesRun.id == series_run_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_title(
        self,
        title: str,
        start_year: Optional[int] = None,
    ) -> Optional[SeriesRun]:
        """Find series run by title and optionally start year.

        Args:
            title: Series title
            start_year: Optional start year for disambiguation

        Returns:
            SeriesRun entity or None if not found
        """
        stmt: Select[SeriesRun] = select(SeriesRun).where(SeriesRun.title == title)
        if start_year is not None:
            stmt = stmt.where(SeriesRun.start_year == start_year)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        title: str,
        start_year: int,
        publisher: Optional[str] = None,
    ) -> SeriesRun:
        """Create a new series run.

        Args:
            title: Series title
            start_year: Year the series started
            publisher: Optional publisher name

        Returns:
            Created SeriesRun entity

        Raises:
            DuplicateEntityError: If a series run with the same title and year exists
            RepositoryError: If another database operation fails
        """
        series_run = SeriesRun(
            title=title,
            start_year=start_year,
            publisher=publisher,
        )
        self.session.add(series_run)
        try:
            await self.session.flush()
            await self.session.refresh(series_run)
            logger.info(f"Created series run: {series_run}")
        except sqlalchemy_exc.IntegrityError as e:
            await self.session.rollback()
            if _is_unique_constraint_violation(
                e,
                SERIES_RUN_IDENTITY_CONSTRAINT,
                "series_runs",
                ("title", "start_year"),
            ):
                existing = await self.find_by_title(title, start_year)
                if existing:
                    logger.warning(
                        "Integrity error creating duplicate series run: title=%s, start_year=%s",
                        title,
                        start_year,
                    )
                    raise DuplicateEntityError(
                        f"Series run with title={title} and start_year={start_year} already exists",
                        entity_type="SeriesRun",
                        existing_id=str(existing.id),
                        original_error=e,
                    ) from e
                raise DuplicateEntityError(
                    f"Series run with title={title} and start_year={start_year} already exists",
                    entity_type="SeriesRun",
                    original_error=e,
                ) from e

            logger.error(f"Error creating series run: {e}")
            raise RepositoryError(
                f"Failed to create series run: {title} ({start_year})",
                original_error=e,
            ) from e
        except sqlalchemy_exc.SQLAlchemyError as e:
            logger.error(f"Error creating series run: {e}")
            raise RepositoryError(
                f"Failed to create series run: {title} ({start_year})",
                original_error=e,
            ) from e

        return series_run

    async def update(
        self,
        series_run: SeriesRun,
    ) -> SeriesRun:
        """Update an existing series run.

        Args:
            series_run: SeriesRun entity with updated fields

        Returns:
            Updated SeriesRun entity

        Raises:
            RepositoryError: If database operation fails
        """
        self.session.add(series_run)
        try:
            await self.session.flush()
            await self.session.refresh(series_run)
            logger.info(f"Updated series run: {series_run}")
        except sqlalchemy_exc.SQLAlchemyError as e:
            logger.error(f"Error updating series run: {e}")
            raise RepositoryError(
                f"Failed to update series run: {series_run.id}",
                original_error=e,
            ) from e

        return series_run

    async def delete(
        self,
        series_run: SeriesRun,
    ) -> None:
        """Delete a series run.

        Args:
            series_run: SeriesRun entity to delete
        """
        await self.session.delete(series_run)
        await self.session.flush()


class IssueRepository:
    """Repository for Issue entity operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: Async database session
        """
        self.session = session

    async def find_by_id(
        self,
        issue_id: uuid.UUID,
    ) -> Optional[Issue]:
        """Find issue by ID.

        Args:
            issue_id: UUID of the issue

        Returns:
            Issue entity or None if not found
        """
        stmt: Select[Issue] = select(Issue).where(Issue.id == issue_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_number(
        self,
        series_run_id: uuid.UUID,
        issue_number: str,
    ) -> Optional[Issue]:
        """Find issue by series run and issue number.

        Args:
            series_run_id: UUID of the series run
            issue_number: Issue number string

        Returns:
            Issue entity or None if not found
        """
        stmt: Select[Issue] = select(Issue).where(
            Issue.series_run_id == series_run_id,
            Issue.issue_number == issue_number,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_upc(
        self,
        upc: str,
    ) -> Optional[Issue]:
        """Find issue by UPC.

        Args:
            upc: Universal Product Code

        Returns:
            Issue entity or None if not found
        """
        stmt: Select[Issue] = select(Issue).where(Issue.upc == upc)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        series_run_id: uuid.UUID,
        issue_number: str,
        cover_date: Optional[datetime] = None,
        upc: Optional[str] = None,
    ) -> Issue:
        """Create a new issue.

        Args:
            series_run_id: UUID of the parent series run
            issue_number: Issue number string
            cover_date: Optional cover publication date
            upc: Optional Universal Product Code

        Returns:
            Created Issue entity

        Raises:
            DuplicateEntityError: If an issue with the same series and number exists
            RepositoryError: If another database operation fails
        """
        issue = Issue(
            series_run_id=series_run_id,
            issue_number=issue_number,
            cover_date=cover_date,
            upc=upc,
        )
        self.session.add(issue)
        try:
            await self.session.flush()
            await self.session.refresh(issue)
            logger.info(
                f"Created issue: series_run_id={series_run_id}, issue_number={issue_number}"
            )
        except sqlalchemy_exc.IntegrityError as e:
            await self.session.rollback()
            if _is_unique_constraint_violation(
                e,
                ISSUE_IDENTITY_CONSTRAINT,
                "issues",
                ("series_run_id", "issue_number"),
            ):
                existing = await self.find_by_number(series_run_id, issue_number)
                if existing:
                    logger.warning(
                        "Integrity error creating duplicate issue: series_run_id=%s, issue_number=%s",
                        series_run_id,
                        issue_number,
                    )
                    raise DuplicateEntityError(
                        "Issue with "
                        f"series_run_id={series_run_id} and issue_number={issue_number} already exists",
                        entity_type="Issue",
                        existing_id=str(existing.id),
                        original_error=e,
                    ) from e
                raise DuplicateEntityError(
                    "Issue with "
                    f"series_run_id={series_run_id} and issue_number={issue_number} already exists",
                    entity_type="Issue",
                    original_error=e,
                ) from e

            logger.error(f"Error creating issue: {e}")
            raise RepositoryError(
                f"Failed to create issue: {issue_number}",
                original_error=e,
            ) from e
        except sqlalchemy_exc.SQLAlchemyError as e:
            logger.error(f"Error creating issue: {e}")
            raise RepositoryError(
                f"Failed to create issue: {issue_number}",
                original_error=e,
            ) from e

        return issue

    async def update(
        self,
        issue: Issue,
    ) -> Issue:
        """Update an existing issue.

        Args:
            issue: Issue entity with updated fields

        Returns:
            Updated Issue entity

        Raises:
            RepositoryError: If database operation fails
        """
        self.session.add(issue)
        try:
            await self.session.flush()
            await self.session.refresh(issue)
            logger.info(f"Updated issue: {issue}")
        except sqlalchemy_exc.SQLAlchemyError as e:
            logger.error(f"Error updating issue: {e}")
            raise RepositoryError(
                f"Failed to update issue: {issue.id}",
                original_error=e,
            ) from e

        return issue

    async def delete(
        self,
        issue: Issue,
    ) -> None:
        """Delete an issue.

        Args:
            issue: Issue entity to delete
        """
        await self.session.delete(issue)
        await self.session.flush()

    async def find_with_variants(
        self,
        issue_id: uuid.UUID,
    ) -> Optional[Issue]:
        """Find issue with variants preloaded.

        Args:
            issue_id: UUID of the issue

        Returns:
            Issue entity with variants or None if not found
        """
        stmt: Select[Issue] = (
            select(Issue)
            .options(selectinload(Issue.variants))
            .where(Issue.id == issue_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class VariantRepository:
    """Repository for Variant entity operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: Async database session
        """
        self.session = session

    async def find_by_id(
        self,
        variant_id: uuid.UUID,
    ) -> Optional[Variant]:
        """Find variant by ID.

        Args:
            variant_id: UUID of the variant

        Returns:
            Variant entity or None if not found
        """
        stmt: Select[Variant] = select(Variant).where(Variant.id == variant_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_issue_and_suffix(
        self,
        issue_id: uuid.UUID,
        variant_suffix: str,
    ) -> Optional[Variant]:
        """Find variant by issue and suffix.

        Args:
            issue_id: UUID of the parent issue
            variant_suffix: Variant suffix code

        Returns:
            Variant entity or None if not found
        """
        stmt: Select[Variant] = select(Variant).where(
            Variant.issue_id == issue_id,
            Variant.variant_suffix == variant_suffix,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        issue_id: uuid.UUID,
        variant_suffix: str,
        variant_name: Optional[str] = None,
    ) -> Variant:
        """Create a new variant.

        Args:
            issue_id: UUID of the parent issue
            variant_suffix: Variant suffix code
            variant_name: Optional human-readable variant name

        Returns:
            Created Variant entity

        Raises:
            DuplicateEntityError: If a variant with the same issue_id and suffix exists
        """
        existing = await self.find_by_issue_and_suffix(issue_id, variant_suffix)
        if existing is not None:
            logger.warning(
                f"Duplicate variant attempt: issue_id={issue_id}, suffix={variant_suffix}"
            )
            raise DuplicateEntityError(
                f"Variant with issue_id={issue_id} and suffix={variant_suffix} already exists",
                entity_type="Variant",
                existing_id=str(existing.id),
            )

        variant = Variant(
            issue_id=issue_id,
            variant_suffix=variant_suffix,
            variant_name=variant_name,
        )
        self.session.add(variant)
        try:
            await self.session.flush()
            await self.session.refresh(variant)
            logger.info(f"Created variant: {variant}")
        except sqlalchemy_exc.IntegrityError as e:
            logger.error(f"Integrity error creating variant: {e}")
            raise DuplicateEntityError(
                f"Variant with issue_id={issue_id} and suffix={variant_suffix} already exists",
                entity_type="Variant",
                original_error=e,
            ) from e

        return variant


class ExternalMappingRepository:
    """Repository for ExternalMapping entity operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: Async database session
        """
        self.session = session

    async def find_by_source(
        self,
        source: str,
        source_issue_id: str,
    ) -> Optional[ExternalMapping]:
        """Find external mapping by source and source issue ID.

        Args:
            source: Source platform code (e.g., "gcd", "locg")
            source_issue_id: Issue ID on the source platform

        Returns:
            ExternalMapping entity or None if not found
        """
        stmt: Select[ExternalMapping] = select(ExternalMapping).where(
            ExternalMapping.source == source,
            ExternalMapping.source_issue_id == source_issue_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_all_by_source(
        self,
        source: str,
        limit: int = 1000,
    ) -> list[ExternalMapping]:
        """Find all external mappings for a source platform.

        Args:
            source: Source platform code
            limit: Maximum number of results

        Returns:
            List of ExternalMapping entities
        """
        stmt: Select[ExternalMapping] = (
            select(ExternalMapping).where(ExternalMapping.source == source).limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_mapping(
        self,
        issue_id: uuid.UUID,
        source: str,
        source_issue_id: str,
        source_series_id: Optional[str] = None,
    ) -> ExternalMapping:
        """Create a new external mapping.

        Args:
            issue_id: UUID of the canonical issue
            source: Source platform code
            source_issue_id: Issue ID on the source platform
            source_series_id: Optional series ID on the source platform

        Returns:
            Created ExternalMapping entity

        Raises:
            DuplicateEntityError: If a mapping with the same source and source_issue_id exists
        """
        existing = await self.find_by_source(source, source_issue_id)
        if existing is not None:
            logger.warning(
                f"Duplicate external mapping attempt: source={source}, source_issue_id={source_issue_id}"
            )
            raise DuplicateEntityError(
                f"External mapping with source={source} and source_issue_id={source_issue_id} already exists",
                entity_type="ExternalMapping",
                existing_id=str(existing.id),
            )

        mapping = ExternalMapping(
            issue_id=issue_id,
            source=source,
            source_issue_id=source_issue_id,
            source_series_id=source_series_id,
        )
        self.session.add(mapping)
        try:
            await self.session.flush()
            await self.session.refresh(mapping)
            logger.info(f"Created external mapping: {mapping}")
        except sqlalchemy_exc.IntegrityError as e:
            logger.error(f"Integrity error creating external mapping: {e}")
            raise DuplicateEntityError(
                f"External mapping with source={source} and source_issue_id={source_issue_id} already exists",
                entity_type="ExternalMapping",
                original_error=e,
            ) from e

        return mapping

    async def find_by_issue(
        self,
        issue_id: uuid.UUID,
    ) -> list[ExternalMapping]:
        """Find all external mappings for an issue.

        Args:
            issue_id: UUID of the issue

        Returns:
            List of ExternalMapping entities
        """
        stmt: Select[ExternalMapping] = select(ExternalMapping).where(
            ExternalMapping.issue_id == issue_id
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_source_issue_id(
        self,
        source_issue_id: str,
    ) -> int:
        """Delete all external mappings for a given source_issue_id.

        Args:
            source_issue_id: Issue ID on the source platform

        Returns:
            Number of mappings deleted
        """
        stmt: Delete[ExternalMapping] = delete(ExternalMapping).where(
            ExternalMapping.source_issue_id == source_issue_id
        )
        result = await self.session.execute(stmt)
        return result.rowcount


class OperationRepository:
    """Repository for Operation entity operations (AIP-151)."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: Async database session
        """
        self.session = session

    async def create_operation(
        self,
        operation_type: str,
        input_hash: Optional[str] = None,
        result: Optional[dict] = None,
    ) -> Operation:
        """Create a new operation.

        Args:
            operation_type: Type of operation (import, export, reconcile)
            input_hash: Optional hash of input data for deduplication

        Returns:
            Created Operation entity

        Raises:
            RepositoryError: If database operation fails
        """
        operation = Operation(
            operation_type=operation_type,
            status="pending",
            input_hash=input_hash,
            result=result,
        )
        self.session.add(operation)
        try:
            await self.session.flush()
            await self.session.refresh(operation)
            logger.info(f"Created operation: {operation}")
        except sqlalchemy_exc.SQLAlchemyError as e:
            logger.error(f"Error creating operation: {e}")
            raise RepositoryError(
                f"Failed to create operation: {operation_type}",
                original_error=e,
            ) from e

        return operation

    async def update_status(
        self,
        operation: Operation,
        status: str,
        result: Optional[dict] = None,
        error_message: Optional[str] = None,
        clear_error_message: bool = False,
    ) -> Operation:
        """Update operation status and result.

        Args:
            operation: Operation entity to update
            status: New status (pending, running, completed, failed)
            result: Optional result data as dictionary
            error_message: Optional error message if failed

        Returns:
            Updated Operation entity

        Raises:
            RepositoryError: If database operation fails
        """
        operation.status = status
        if result is not None:
            operation.result = result
        if clear_error_message:
            operation.error_message = None
        elif error_message is not None:
            operation.error_message = error_message
        self.session.add(operation)
        try:
            await self.session.flush()
            await self.session.refresh(operation)
            logger.info(f"Updated operation status: {operation}")
        except sqlalchemy_exc.SQLAlchemyError as e:
            logger.error(f"Error updating operation status: {e}")
            raise RepositoryError(
                f"Failed to update operation: {operation.id}",
                original_error=e,
            ) from e

        return operation

    async def get_operation(
        self,
        operation_id: uuid.UUID,
    ) -> Optional[Operation]:
        """Find operation by ID.

        Args:
            operation_id: UUID of the operation

        Returns:
            Operation entity or None if not found
        """
        stmt: Select[Operation] = select(Operation).where(Operation.id == operation_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_status(
        self,
        status: str,
        limit: int = 100,
    ) -> list[Operation]:
        """Find operations by status.

        Args:
            status: Operation status to filter by
            limit: Maximum number of results

        Returns:
            List of Operation entities
        """
        stmt: Select[Operation] = (
            select(Operation)
            .where(Operation.status == status)
            .order_by(Operation.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_input_hash(
        self,
        input_hash: str,
    ) -> Optional[Operation]:
        """Find operation by input hash.

        Args:
            input_hash: Hash of input data

        Returns:
            Operation entity or None if not found
        """
        stmt: Select[Operation] = (
            select(Operation)
            .where(Operation.input_hash == input_hash)
            .order_by(Operation.created_at.desc(), Operation.id.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
