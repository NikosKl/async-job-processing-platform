import uuid
from datetime import UTC, datetime, timedelta

from app.domain.enums import JobStatus, JobType
from app.models import User
from app.repositories.job import get_job_by_id_and_user_id, list_jobs_by_user_id
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
