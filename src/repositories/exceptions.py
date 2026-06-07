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


class RecordNotFoundError(RepositoryError):
    """Raised when a requested record does not exist.

    This exception is raised by repository methods that expect to find
    exactly one record matching the given criteria. It is distinct from
    methods that return ``None`` on no match (e.g., ``get_by_id`` vs.
    ``find_by_id``).

    Attributes:
        identifier: The primary key or natural key that was queried.
        table_name: The name of the table where the record was not found.

    Example:
        raise RecordNotFoundError(
            identifier=42,
            table_name="dim_movie",
        )
    """

    def __init__(self: "RecordNotFoundError", identifier: object, table_name: str) -> None:
        """Initialise the exception.

        Args:
            identifier: The key value that was queried (int, str, UUID, etc.).
            table_name: The table name where the lookup occurred.
        """
        self.identifier = identifier
        self.table_name = table_name
        super().__init__(f"Record not found in {table_name}: {identifier}")


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
