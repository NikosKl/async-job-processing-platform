from app.domain.exceptions import (
    GitHubUnavailableError,
    InvalidRepositoryResponseError,
    RepositoryUnavailableError,
)
from app.domain.repository_errors import classify_repository_error


def test_github_unavailable_error_is_retryable():
    error = GitHubUnavailableError("GitHub is temporarily unavailable")

    result = classify_repository_error(error)

    assert result == "RETRYABLE"


def test_repository_unavailable_error_is_permanent():
    error = RepositoryUnavailableError("Repository not found")

    result = classify_repository_error(error)

    assert result == "PERMANENT"


def test_invalid_repository_response_error_is_permanent():
    error = InvalidRepositoryResponseError("GitHub returned invalid repository data")

    result = classify_repository_error(error)

    assert result == "PERMANENT"


def test_exception_subclasses_retain_parent_classification():
    class CustomGithubUnavailableError(GitHubUnavailableError):
        pass

    result = classify_repository_error(CustomGithubUnavailableError())

    assert result == "RETRYABLE"


def test_unexpected_exception_returns_none():
    error = RuntimeError("Unexpected exception")

    result = classify_repository_error(error)

    assert result is None
