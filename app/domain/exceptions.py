import math


class IdempotencyConflictError(Exception):
    pass


class JobNotFoundError(Exception):
    pass


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class InvalidAccessTokenError(Exception):
    pass


class InvalidRepositoryResponseError(Exception):
    pass


class RepositoryUnavailableError(Exception):
    pass


class GitHubUnavailableError(Exception):
    pass


class RepositoryAnalysisFailedError(Exception):
    def __init__(self, attempt_count: int) -> None:
        super().__init__(f"Repository analysis failed with {attempt_count} attempts")

        self.attempt_count = attempt_count


class GitHubRateLimitError(Exception):
    def __init__(self, retry_after_seconds: float) -> None:

        if not math.isfinite(retry_after_seconds) or retry_after_seconds < 0:
            raise ValueError("retry_after_seconds must be finite and nonnegative")

        super().__init__(f"GitHub rate limit exceeded: {retry_after_seconds} seconds")

        self.retry_after_seconds = retry_after_seconds
