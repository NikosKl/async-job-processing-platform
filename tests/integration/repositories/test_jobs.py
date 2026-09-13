import uuid

from app.models import User
from app.repositories.job import get_job_by_id_and_user_id
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
