class IdempotencyConflictError(Exception):
    pass


class JobNotFoundError(Exception):
    pass


class EmailAlreadyRegisteredError(Exception):
    pass
