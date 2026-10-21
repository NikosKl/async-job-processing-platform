import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.domain.enums import JobStatus, JobType
from app.models import Job, User
from app.repositories.job import (
    claim_job,
    get_job_by_id_and_user_id,
    list_jobs_by_user_id,
)
from app.schemas.jobs import CreateJobRequest, RepositoryBatchAnalysisInput
from app.services.job_service import submit_job


def test_get_job_by_id_and_user_id_returns_job_when_owned(db_session):
    user = User(
        email="user@example.com",
        hashed_password="hashed_password",
    )

    db_session.add(user)
    db_session.flush()

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=[
                "FastApi/FastApi",
                "SQLAlchemy/SQLAlchemy",
            ]
        ),
    )

    submitted_job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    job = get_job_by_id_and_user_id(db_session, submitted_job.id, user.id)

    assert job is not None
    assert job.id == submitted_job.id
    assert job.user_id == user.id


def test_get_job_by_id_and_user_id_returns_none_when_job_not_found(db_session):

    user = User(
        email="user@example.com",
        hashed_password="hashed_password",
    )

    db_session.add(user)
    db_session.flush()

    job_id = uuid.uuid4()

    job = get_job_by_id_and_user_id(db_session, job_id, user.id)

    assert job is None


def test_get_job_by_id_and_user_id_returns_none_when_job_belongs_to_another_user(
    db_session,
):

    user = User(
        email="user@example.com",
        hashed_password="hashed_password",
    )

    db_session.add(user)
    db_session.flush()

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=[
                "FastApi/FastApi",
                "SQLAlchemy/SQLAlchemy",
            ]
        ),
    )

    submitted_job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    new_user = User(
        email="new_user@example.com",
        hashed_password="hashed_password",
    )

    db_session.add(new_user)
    db_session.flush()

    job = get_job_by_id_and_user_id(db_session, submitted_job.id, new_user.id)

    assert job is None


def test_get_job_list_by_user_id_excludes_other_users_jobs(
    db_session, authenticated_user_factory
):

    user_a, _ = authenticated_user_factory("user_a@example.com", "password123")
    user_b, _ = authenticated_user_factory("user_b@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["owner/repository"]),
    )

    job_a = submit_job(
        db=db_session,
        user_id=user_a.id,
        request=request,
        idempotency_key="test-key-123",
    )

    submit_job(
        db=db_session,
        user_id=user_b.id,
        request=request,
        idempotency_key="test-key-456",
    )

    jobs = list_jobs_by_user_id(db_session, user_a.id)

    assert len(jobs) == 1
    assert jobs[0].id == job_a.id


def test_list_jobs_by_user_id_returns_newest_first(
    db_session, authenticated_user_factory
):

    user, _ = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["owner/repository"]),
    )

    first_job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    second_job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-456",
    )

    now = datetime.now(UTC)
    first_job.created_at = now - timedelta(minutes=10)
    second_job.created_at = now
    db_session.flush()

    jobs = list_jobs_by_user_id(db_session, user.id)

    assert len(jobs) == 2
    assert second_job.id == jobs[0].id
    assert first_job.id == jobs[1].id


def test_list_jobs_by_user_id_limit_and_offset_select_correct_jobs(
    db_session, authenticated_user_factory
):

    user, _ = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["owner/repository"]),
    )

    first_job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    second_job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-456",
    )

    third_job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-789",
    )

    now = datetime.now(UTC)
    first_job.created_at = now - timedelta(minutes=20)
    second_job.created_at = now - timedelta(minutes=10)
    third_job.created_at = now - timedelta(minutes=15)
    db_session.flush()

    jobs = list_jobs_by_user_id(db_session, user.id, limit=1, offset=1)
    assert len(jobs) == 1

    assert jobs[0].id == third_job.id


def test_list_jobs_by_user_id_filters_by_status(db_session, authenticated_user_factory):

    user, _ = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["owner/repository"]),
    )

    first_job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-456",
    )

    first_job.status = JobStatus.COMPLETED
    db_session.flush()

    jobs = list_jobs_by_user_id(db_session, user.id, job_status=JobStatus.COMPLETED)

    assert len(jobs) == 1
    assert jobs[0].id == first_job.id


def test_list_jobs_by_user_id_filters_by_type(db_session, authenticated_user_factory):

    user, _ = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["owner/repository"]),
    )

    submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-456",
    )

    submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-789",
    )

    jobs = list_jobs_by_user_id(
        db_session, user.id, job_type=JobType.REPOSITORY_BATCH_ANALYSIS
    )

    assert len(jobs) == 3
    assert all(job.type == JobType.REPOSITORY_BATCH_ANALYSIS for job in jobs)


def test_claim_job_claims_queued_job(db_session, authenticated_user_factory):
    user, _ = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["owner/repository"]),
    )

    job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    execution_token = uuid.uuid4()
    lease_expires_at = claim_time + timedelta(minutes=10)

    claimed_job = claim_job(
        db=db_session,
        job_id=job.id,
        claim_time=claim_time,
        execution_token=execution_token,
        lease_expires_at=lease_expires_at,
    )

    assert claimed_job is not None
    assert claimed_job.status == JobStatus.RUNNING
    assert claimed_job.attempt_count == 1
    assert claimed_job.execution_token == execution_token
    assert claimed_job.lease_expires_at == lease_expires_at
    assert claimed_job.next_attempt_at is None


def test_claim_job_claims_due_retry_at_exact_boundary(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["owner/repository"]),
    )

    job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    execution_token = uuid.uuid4()
    lease_expires_at = claim_time + timedelta(minutes=10)

    job.status = JobStatus.RETRYING
    job.next_attempt_at = claim_time
    job.attempt_count = 1

    db_session.flush()

    claimed_job = claim_job(
        db=db_session,
        job_id=job.id,
        claim_time=claim_time,
        execution_token=execution_token,
        lease_expires_at=lease_expires_at,
    )

    assert claimed_job is not None
    assert claimed_job.status == JobStatus.RUNNING
    assert claimed_job.attempt_count == 2
    assert claimed_job.execution_token == execution_token
    assert claimed_job.lease_expires_at == lease_expires_at
    assert claimed_job.next_attempt_at is None


def test_claim_job_returns_none_for_future_retry(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["owner/repository"]),
    )

    job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    execution_token = uuid.uuid4()
    lease_expires_at = claim_time + timedelta(minutes=10)

    job.status = JobStatus.RETRYING
    job.next_attempt_at = claim_time + timedelta(minutes=5)
    job.attempt_count = 1

    db_session.flush()

    claimed_job = claim_job(
        db=db_session,
        job_id=job.id,
        claim_time=claim_time,
        execution_token=execution_token,
        lease_expires_at=lease_expires_at,
    )

    assert claimed_job is None
    assert job.status == JobStatus.RETRYING
    assert job.attempt_count == 1
    assert job.execution_token is None
    assert job.lease_expires_at is None
    assert job.next_attempt_at == claim_time + timedelta(minutes=5)


@pytest.mark.parametrize(
    "status",
    [
        JobStatus.RUNNING,
        JobStatus.COMPLETED,
        JobStatus.FAILED,
    ],
)
def test_claim_job_returns_none_for_ineligible_status(
    db_session, authenticated_user_factory, status
):
    user, _ = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["owner/repository"]),
    )

    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    execution_token = uuid.uuid4()
    lease_expires_at = claim_time + timedelta(minutes=10)

    job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    job.status = status
    db_session.flush()

    claimed_job = claim_job(
        db=db_session,
        job_id=job.id,
        claim_time=claim_time,
        execution_token=execution_token,
        lease_expires_at=lease_expires_at,
    )

    assert claimed_job is None
    assert job.status == status
    assert job.attempt_count == 0
    assert job.execution_token is None
    assert job.lease_expires_at is None


def test_claim_job_returns_none_for_missing_job(db_session):
    job_id = uuid.uuid4()

    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    execution_token = uuid.uuid4()
    lease_expires_at = claim_time + timedelta(minutes=10)

    claimed_job = claim_job(
        db=db_session,
        job_id=job_id,
        claim_time=claim_time,
        execution_token=execution_token,
        lease_expires_at=lease_expires_at,
    )

    assert claimed_job is None


def test_claim_job_second_claim_cannot_replace_ownership(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["owner/repository"]),
    )

    job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    execution_token_a = uuid.uuid4()
    lease_expires_at = claim_time + timedelta(minutes=10)

    claimed_job = claim_job(
        db=db_session,
        job_id=job.id,
        claim_time=claim_time,
        execution_token=execution_token_a,
        lease_expires_at=lease_expires_at,
    )

    assert claimed_job is not None

    execution_token_b = uuid.uuid4()

    claimed_job = claim_job(
        db=db_session,
        job_id=job.id,
        claim_time=claim_time,
        execution_token=execution_token_b,
        lease_expires_at=lease_expires_at,
    )

    assert claimed_job is None
    assert job.status == JobStatus.RUNNING
    assert job.attempt_count == 1
    assert job.execution_token == execution_token_a
    assert job.lease_expires_at == lease_expires_at


def test_claim_job_rollback_restores_original_state(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["owner/repository"]),
    )

    job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    execution_token = uuid.uuid4()
    lease_expires_at = claim_time + timedelta(minutes=10)

    original_status = job.status
    original_attempt_count = job.attempt_count
    original_execution_token = job.execution_token
    original_lease_expires_at = job.lease_expires_at
    original_next_attempt_at = job.next_attempt_at

    claimed_job = claim_job(
        db=db_session,
        job_id=job.id,
        claim_time=claim_time,
        execution_token=execution_token,
        lease_expires_at=lease_expires_at,
    )

    assert claimed_job is not None
    assert claimed_job.status == JobStatus.RUNNING
    assert claimed_job.attempt_count == 1
    assert claimed_job.execution_token == execution_token
    assert claimed_job.lease_expires_at == lease_expires_at

    db_session.rollback()

    stmt = select(Job).where(Job.id == job.id)
    job = db_session.scalars(stmt).one()

    assert job.status == original_status
    assert job.attempt_count == original_attempt_count
    assert job.execution_token == original_execution_token
    assert job.lease_expires_at == original_lease_expires_at
    assert job.next_attempt_at == original_next_attempt_at


def test_claim_job_rejects_naive_claim_time(db_session):
    job_id = uuid.uuid4()

    claim_time = datetime(2026, 10, 2, 12, 0)
    execution_token = uuid.uuid4()
    lease_expires_at = datetime(2026, 10, 2, 12, 10, tzinfo=UTC)

    with pytest.raises(ValueError):
        claim_job(
            db=db_session,
            job_id=job_id,
            claim_time=claim_time,
            execution_token=execution_token,
            lease_expires_at=lease_expires_at,
        )


def test_claim_job_rejects_naive_lease_expiry(db_session):
    job_id = uuid.uuid4()

    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    execution_token = uuid.uuid4()
    lease_expires_at = datetime(2026, 10, 2, 12, 0)

    with pytest.raises(ValueError):
        claim_job(
            db=db_session,
            job_id=job_id,
            claim_time=claim_time,
            execution_token=execution_token,
            lease_expires_at=lease_expires_at,
        )


@pytest.mark.parametrize(
    "lease_offset",
    [
        timedelta(minutes=-10),
        timedelta(0),
    ],
)
def test_claim_job_rejects_lease_expiry_not_later_than_claim_time(
    db_session,
    lease_offset,
):
    job_id = uuid.uuid4()

    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    execution_token = uuid.uuid4()
    lease_expires_at = claim_time + lease_offset

    with pytest.raises(ValueError):
        claim_job(
            db=db_session,
            job_id=job_id,
            claim_time=claim_time,
            execution_token=execution_token,
            lease_expires_at=lease_expires_at,
        )
