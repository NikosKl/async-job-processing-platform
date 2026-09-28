import uuid
from datetime import UTC, datetime

from app.domain.enums import JobAttemptStatus
from app.models import JobAttempt
from app.repositories.job_attempt import list_job_attempts_by_job_id
from app.schemas.jobs import CreateJobRequest, RepositoryBatchAnalysisInput
from app.services.job_service import submit_job


def test_list_job_attempts_by_job_id_excludes_other_jobs_attempts(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory(
        email="user@example.com", password="password123"
    )

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=[
                "FastApi/FastApi",
                "SQLAlchemy/SQLAlchemy",
            ]
        ),
    )

    job_a = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    job_b = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-456",
    )

    attempt_a = JobAttempt(
        job_id=job_a.id,
        attempt_number=1,
        status=JobAttemptStatus.RUNNING,
        execution_token=uuid.uuid4(),
        started_at=datetime.now(UTC),
    )

    attempt_b = JobAttempt(
        job_id=job_b.id,
        attempt_number=1,
        status=JobAttemptStatus.RUNNING,
        execution_token=uuid.uuid4(),
        started_at=datetime.now(UTC),
    )

    db_session.add_all([attempt_a, attempt_b])
    db_session.flush()

    job_attempts = list_job_attempts_by_job_id(db_session, job_a.id)
    assert len(job_attempts) == 1
    assert job_attempts[0].id == attempt_a.id
    assert job_attempts[0].job_id == job_a.id


def test_list_job_attempts_by_job_id_orders_by_attempt_number(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory(
        email="user@example.com", password="password123"
    )

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=[
                "FastApi/FastApi",
            ]
        ),
    )

    job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    attempt_a = JobAttempt(
        job_id=job.id,
        attempt_number=3,
        status=JobAttemptStatus.RUNNING,
        execution_token=uuid.uuid4(),
        started_at=datetime.now(UTC),
    )

    attempt_b = JobAttempt(
        job_id=job.id,
        attempt_number=1,
        status=JobAttemptStatus.RUNNING,
        execution_token=uuid.uuid4(),
        started_at=datetime.now(UTC),
    )

    attempt_c = JobAttempt(
        job_id=job.id,
        attempt_number=2,
        status=JobAttemptStatus.RUNNING,
        execution_token=uuid.uuid4(),
        started_at=datetime.now(UTC),
    )

    db_session.add_all([attempt_a, attempt_b, attempt_c])
    db_session.flush()

    job_attempts = list_job_attempts_by_job_id(db_session, job.id)

    assert len(job_attempts) == 3
    assert [attempt.attempt_number for attempt in job_attempts] == [1, 2, 3]


def test_list_job_attempts_by_job_id_returns_empty_list_for_job_with_no_attempts(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory(
        email="user@example.com", password="password123"
    )

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=[
                "FastApi/FastApi",
            ]
        ),
    )

    job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    job_attempts = list_job_attempts_by_job_id(db_session, job.id)

    assert job_attempts == []


def test_list_job_attempts_by_job_id_returns_empty_list_for_unknown_job(db_session):
    job_id = uuid.uuid4()

    job_attempts = list_job_attempts_by_job_id(db_session, job_id)

    assert job_attempts == []
