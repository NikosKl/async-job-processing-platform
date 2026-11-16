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
