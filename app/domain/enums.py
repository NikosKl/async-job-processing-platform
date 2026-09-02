from enum import StrEnum


class JobType(StrEnum):
    REPOSITORY_BATCH_ANALYSIS = "REPOSITORY_BATCH_ANALYSIS"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class RepositoryStatus(StrEnum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class JobAttemptStatus(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class OutboxEventType(StrEnum):
    PROCESS_JOB = "PROCESS_JOB"
