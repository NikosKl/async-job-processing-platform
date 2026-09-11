import uuid
from datetime import UTC, datetime, timedelta

from app.domain.enums import JobAttemptStatus, JobStatus, JobType, RepositoryStatus
from app.models import Job, JobAttempt, RepositoryAnalysisItem
from app.schemas.jobs import (
    JobAttemptRead,
    JobDetail,
    JobSummary,
    RepositoryAnalysisItemRead,
)


def test_job_summary_validates_from_job():
    now = datetime.now(UTC)

    job = Job(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        type=JobType.REPOSITORY_BATCH_ANALYSIS,
        status=JobStatus.QUEUED,
        idempotency_key="test_key",
        request_hash="a" * 64,
        progress_total=2,
        progress_completed=0,
        created_at=now,
        queued_at=now,
    )

    response = JobSummary.model_validate(job)

    assert response.id == job.id
    assert response.type == JobType.REPOSITORY_BATCH_ANALYSIS
    assert response.status == JobStatus.QUEUED
    assert response.progress_total == 2
    assert response.progress_completed == 0
    assert response.queued_at == now


def test_job_detail_includes_additional_fields():
    now = datetime.now(UTC)
    next_attempt_at = now + timedelta(minutes=5)

    job = Job(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        type=JobType.REPOSITORY_BATCH_ANALYSIS,
        status=JobStatus.RETRYING,
        idempotency_key="test-key",
        request_hash="a" * 64,
        progress_total=2,
        progress_completed=1,
        attempt_count=1,
        max_attempts=3,
        next_attempt_at=next_attempt_at,
        result_summary={"succeeded": 1, "failed": 0},
        last_error_type="temporary_error",
        last_error_message="Temporary failure",
        created_at=now,
        queued_at=now,
    )

    response = JobDetail.model_validate(job)

    assert response.id == job.id
    assert response.attempt_count == 1
    assert response.max_attempts == 3
    assert response.next_attempt_at == next_attempt_at
    assert response.result_summary == {"succeeded": 1, "failed": 0}
    assert response.last_error_type == "temporary_error"
    assert response.last_error_message == "Temporary failure"


def test_repository_analysis_item_read_preserves_fields():
    item = RepositoryAnalysisItem(
        id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        position=2,
        owner="fastapi",
        repository_name="fastapi",
        status=RepositoryStatus.PENDING,
        attempt_count=0,
        stars=None,
        forks=None,
        open_issues=None,
        primary_language=None,
        archived=None,
        license=None,
        last_push_at=None,
        activity_classification=None,
        error_type=None,
        error_message=None,
        completed_at=None,
    )

    response = RepositoryAnalysisItemRead.model_validate(item)

    assert response.status == RepositoryStatus.PENDING
    assert response.position == 2
    assert response.license is None

    assert response.stars is None
    assert response.last_push_at is None
    assert response.activity_classification is None
    assert response.error_type is None
    assert response.error_message is None
    assert response.completed_at is None


def test_job_attempt_read_validates_status_and_nullable_fields():
    now = datetime.now(UTC)

    attempt = JobAttempt(
        id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        attempt_number=1,
        status=JobAttemptStatus.RUNNING,
        execution_token=uuid.uuid4(),
        worker_id="worker-1",
        started_at=now,
        finished_at=None,
        retryable=None,
        error_type=None,
        error_message=None,
    )

    response = JobAttemptRead.model_validate(attempt)

    assert response.status == JobAttemptStatus.RUNNING
    assert response.finished_at is None
    assert response.error_type is None
    assert response.error_message is None
