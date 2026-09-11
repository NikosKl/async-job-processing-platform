import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.enums import JobAttemptStatus, JobStatus, JobType, RepositoryStatus


class JobSummary(BaseModel):
    id: uuid.UUID
    type: JobType
    status: JobStatus
    progress_total: int
    progress_completed: int
    created_at: datetime
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class JobDetail(JobSummary):
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime | None
    result_summary: dict | None
    last_error_type: str | None
    last_error_message: str | None


class RepositoryAnalysisItemRead(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    position: int
    owner: str
    repository_name: str
    status: RepositoryStatus
    attempt_count: int

    stars: int | None
    forks: int | None
    open_issues: int | None
    primary_language: str | None
    archived: bool | None
    license: str | None
    last_push_at: datetime | None
    activity_classification: str | None

    error_type: str | None
    error_message: str | None

    completed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class JobAttemptRead(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    attempt_number: int
    status: JobAttemptStatus
    retryable: bool | None
    error_type: str | None
    error_message: str | None
    started_at: datetime
    finished_at: datetime | None

    model_config = ConfigDict(from_attributes=True)
