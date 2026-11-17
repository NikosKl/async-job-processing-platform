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
