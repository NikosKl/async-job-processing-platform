from typing import Literal

from app.domain.exceptions import (
    GitHubRateLimitError,
    GitHubUnavailableError,
    InvalidRepositoryResponseError,
    RepositoryUnavailableError,
)


def classify_repository_error(
    exception: Exception,
) -> Literal["RETRYABLE", "PERMANENT"] | None:

    if isinstance(exception, (GitHubUnavailableError, GitHubRateLimitError)):
        return "RETRYABLE"
    if isinstance(exception, RepositoryUnavailableError):
        return "PERMANENT"
    if isinstance(exception, InvalidRepositoryResponseError):
        return "PERMANENT"
    return None
