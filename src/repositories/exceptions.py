"""Repository-layer exception hierarchy.

All exceptions raised by repository implementations inherit from
``RepositoryError``. This keeps the persistence layer isolated from
domain-level exceptions and allows service-layer code to catch repository
failures uniformly.
"""


class RepositoryError(Exception):
    """Base class for all repository-layer exceptions.

    Service-layer code may catch this exception to handle any persistence
    failure uniformly, or catch specific subclasses when finer-grained
    error handling is required.

    Example:
        try:
            dto = await repo.get_by_id(42)
        except RepositoryError as exc:
            logger.error("Persistence failure", extra={"error": str(exc)})
    """


class IntegrityViolationError(RepositoryError):
    """Raised when a persistence operation violates a database constraint.

    This includes unique constraint violations, foreign key violations,
    check constraint violations, and not-null violations. The exception
    wraps the underlying database-level error with additional context.

    Attributes:
        constraint_name: The name of the violated constraint, if available.
        detail: Human-readable description of the violation.

    Example:
        raise IntegrityViolationError(
            constraint_name="uq_dim_movie_imdb_id",
            detail="Duplicate IMDB ID: tt1234567",
        )
    """

    def __init__(
        self: "IntegrityViolationError",
        constraint_name: str | None,
        detail: str,
    ) -> None:
        """Initialise the exception.

        Args:
            constraint_name: The violated constraint name, or ``None`` when
                not reported by the database driver.
            detail: Descriptive message explaining the violation.
        """
        self.constraint_name = constraint_name
        self.detail = detail
        message = f"Integrity violation: {detail}"
        if constraint_name:
            message = f"{message} (constraint: {constraint_name})"
        super().__init__(message)
