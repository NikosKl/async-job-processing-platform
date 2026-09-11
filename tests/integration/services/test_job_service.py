from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import select

from app.domain.enums import JobStatus, JobType, OutboxEventType, RepositoryStatus
from app.domain.exceptions import IdempotencyConflictError
from app.models import Job, OutboxMessage, RepositoryAnalysisItem, User
from app.schemas.jobs.requests import CreateJobRequest, RepositoryBatchAnalysisInput
from app.services.job_request import hash_job_request
from app.services.job_service import submit_job


def test_submit_job_persists_job_items_and_outbox_message(db_session):
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

    job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    assert job.id is not None
    assert job.user_id == user.id
    assert job.status == JobStatus.QUEUED
    assert job.type == JobType.REPOSITORY_BATCH_ANALYSIS
    assert job.idempotency_key == "test-key-123"
    assert job.progress_total == 2
    assert job.progress_completed == 0
    assert job.queued_at is not None
    assert job.request_hash == hash_job_request(request)

    stmt = (
        select(RepositoryAnalysisItem)
        .where(RepositoryAnalysisItem.job_id == job.id)
        .order_by(RepositoryAnalysisItem.position)
    )
    repository_items = db_session.scalars(stmt).all()

    assert len(repository_items) == 2

    assert repository_items[0].position == 0
    assert repository_items[0].owner == "fastapi"
    assert repository_items[0].repository_name == "fastapi"
    assert repository_items[0].status == RepositoryStatus.PENDING

    assert repository_items[1].position == 1
    assert repository_items[1].owner == "sqlalchemy"
    assert repository_items[1].repository_name == "sqlalchemy"
    assert repository_items[1].status == RepositoryStatus.PENDING

    stmt = select(OutboxMessage).where(OutboxMessage.job_id == job.id)
    outbox_messages = db_session.scalars(stmt).all()

    assert len(outbox_messages) == 1
    assert outbox_messages[0].event_type == OutboxEventType.PROCESS_JOB
    assert outbox_messages[0].available_at is not None
    assert outbox_messages[0].publish_attempts == 0
    assert outbox_messages[0].published_at is None


def test_submit_job_returns_existing_job_for_same_request(db_session):
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

    first_job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    assert first_job.id is not None

    second_job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    assert first_job.id == second_job.id

    stmt = select(Job).where(
        Job.user_id == user.id, Job.idempotency_key == "test-key-123"
    )
    job = db_session.scalars(stmt).one()

    stmt = select(RepositoryAnalysisItem).where(RepositoryAnalysisItem.job_id == job.id)
    repository_items = db_session.scalars(stmt).all()

    assert len(repository_items) == 2

    stmt = select(OutboxMessage).where(OutboxMessage.job_id == job.id)
    outbox_messages = db_session.scalars(stmt).all()

    assert len(outbox_messages) == 1


def test_submit_job_raises_conflict_for_same_key_different_request(db_session):
    user = User(
        email="user@example.com",
        hashed_password="hashed_password",
    )

    db_session.add(user)
    db_session.flush()

    first_request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=[
                "FastApi/FastApi",
                "SQLAlchemy/SQLAlchemy",
            ]
        ),
    )

    second_request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=[
                "FastApi/FastApi",
                "Pallets/Flask",
            ]
        ),
    )

    first_job = submit_job(
        db=db_session,
        user_id=user.id,
        request=first_request,
        idempotency_key="test-key-123",
    )

    assert first_job.id is not None

    with pytest.raises(IdempotencyConflictError):
        submit_job(
            db=db_session,
            user_id=user.id,
            request=second_request,
            idempotency_key="test-key-123",
        )

    stmt = select(Job).where(
        Job.user_id == user.id, Job.idempotency_key == "test-key-123"
    )
    job = db_session.scalars(stmt).one()

    assert job.id == first_job.id


def test_submit_job_handles_concurrent_duplicates(test_session_factory):

    with test_session_factory() as db_session:
        user = User(
            email="user_a@example.com",
            hashed_password="hashed_password",
        )

        db_session.add(user)
        db_session.commit()

        user_id = user.id

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=[
                "FastApi/FastApi",
                "SQLAlchemy/SQLAlchemy",
            ]
        ),
    )

    barrier = Barrier(2)

    def submit():
        with test_session_factory() as session:
            barrier.wait()

            submitted_job = submit_job(
                db=session,
                user_id=user_id,
                request=request,
                idempotency_key="test-key-123",
            )
            return submitted_job.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        future_a = executor.submit(submit)
        future_b = executor.submit(submit)

        job_id_a = future_a.result()
        job_id_b = future_b.result()

    assert job_id_a == job_id_b

    with test_session_factory() as verify_session:
        stmt = select(Job).where(
            Job.user_id == user.id, Job.idempotency_key == "test-key-123"
        )
        jobs = verify_session.scalars(stmt).all()

        job = jobs[0]

        assert len(jobs) == 1

        stmt = select(RepositoryAnalysisItem).where(
            RepositoryAnalysisItem.job_id == job.id
        )
        items = verify_session.scalars(stmt).all()

        assert len(items) == 2

        stmt = select(OutboxMessage).where(OutboxMessage.job_id == job.id)
        outbox_messages = verify_session.scalars(stmt).all()

        assert len(outbox_messages) == 1
