"""Error handling utilities for comic-identity-engine tasks."""

import uuid
from typing import Any, Callable

from sqlalchemy.exc import SQLAlchemyError

from comic_identity_engine.adapters import (
    NotFoundError,
    SourceError,
    ValidationError as AdapterValidationError,
)
from comic_identity_engine.errors import (
    NetworkError,
    ParseError,
    ResolutionError,
    ValidationError,
)


ERROR_TYPE_MAPPING: dict[type, tuple[str, str]] = {
    ParseError: ("parse_error", "URL parsing failed"),
    NotFoundError: ("not_found_error", "Issue not found on platform"),
    NetworkError: ("network_error", "Network error communicating with platform"),
    SourceError: ("platform_error", "Platform communication error"),
    AdapterValidationError: ("adapter_validation_error", "Invalid data from platform"),
    ValidationError: ("validation_error", "Validation error during resolution"),
    ResolutionError: ("resolution_error", "Identity resolution failed"),
    SQLAlchemyError: ("database_error", "Database error during operation"),
    ValueError: ("validation_error", "Invalid input"),
    FileNotFoundError: ("file_not_found_error", "File not found"),
}


async def handle_task_error(
    session: Any,
    operation_uuid: uuid.UUID | None,
    operation_id: str,
    error: Exception,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Handle task errors with consistent logging and operation marking.

    Args:
        session: Database session
        operation_uuid: UUID of the operation (may be None if not yet parsed)
        operation_id: String operation ID for logging
        error: The exception that occurred
        context: Optional additional context for error result

    Returns:
        Error dictionary with error message and error_type
    """
    from comic_identity_engine.jobs.tasks import _mark_failed_safe
    import structlog

    logger = structlog.get_logger(__name__)

    error_type, error_prefix = ERROR_TYPE_MAPPING.get(
        type(error),
        ("unexpected_error", "Unexpected error during operation"),
    )
    error_msg = f"{error_prefix}: {error}"

    logger.error(
        f"Task failed - {error_type}",
        operation_id=operation_id,
        error=error_msg,
        error_type=type(error).__name__,
    )

    if operation_uuid:
        result = {"error_type": error_type}
        if context:
            result.update(context)
        await _mark_failed_safe(session, operation_uuid, error_msg, result=result)

    return {"error": error_msg, "error_type": error_type}
