from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import OutboxMessage
from app.repositories.outbox_message import (
    get_due_outbox_messages,
    mark_outbox_message_failed,
    mark_outbox_message_published,
)
from app.schemas.jobs import CreateJobRequest, RepositoryBatchAnalysisInput
from app.services.job_service import submit_job


def test_get_due_outbox_messages_returns_due_unpublished_messages(
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

    submitted_job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    stmt = select(OutboxMessage).where(OutboxMessage.job_id == submitted_job.id)
    outbox_message = db_session.scalars(stmt).one()

    cutoff = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    outbox_message.available_at = cutoff - timedelta(minutes=5)

    db_session.flush()

    outbox = get_due_outbox_messages(db=db_session, cutoff=cutoff, limit=1)

    assert len(outbox) == 1
    assert outbox[0].id == outbox_message.id


def test_get_due_outbox_messages_includes_message_at_exact_cutoff(
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

    submitted_job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    stmt = select(OutboxMessage).where(OutboxMessage.job_id == submitted_job.id)
    outbox_message = db_session.scalars(stmt).one()

    cutoff = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    outbox_message.available_at = cutoff

    db_session.flush()

    outbox = get_due_outbox_messages(db=db_session, cutoff=cutoff, limit=1)

    assert len(outbox) == 1
    assert outbox[0].id == outbox_message.id


def test_get_due_outbox_messages_excludes_future_messages(
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

    submitted_job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    stmt = select(OutboxMessage).where(OutboxMessage.job_id == submitted_job.id)
    outbox_message = db_session.scalars(stmt).one()

    cutoff = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    outbox_message.available_at = cutoff + timedelta(minutes=5)

    db_session.flush()

    outbox = get_due_outbox_messages(db=db_session, cutoff=cutoff, limit=1)

    assert outbox == []


def test_get_due_outbox_messages_excludes_published_messages(
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

    submitted_job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    stmt = select(OutboxMessage).where(OutboxMessage.job_id == submitted_job.id)
    outbox_message = db_session.scalars(stmt).one()

    cutoff = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    outbox_message.available_at = cutoff - timedelta(minutes=5)
    outbox_message.published_at = cutoff + timedelta(minutes=1)

    db_session.flush()

    outbox = get_due_outbox_messages(db=db_session, cutoff=cutoff, limit=1)

    assert outbox == []


def test_get_due_outbox_messages_orders_by_available_at_then_id(
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

    job_c = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-789",
    )

    stmt = select(OutboxMessage).where(
        OutboxMessage.job_id.in_([job_a.id, job_b.id, job_c.id])
    )
    outbox_messages = db_session.scalars(stmt).all()

    outbox_by_id = {message.job_id: message for message in outbox_messages}

    outbox_a = outbox_by_id[job_a.id]
    outbox_b = outbox_by_id[job_b.id]
    outbox_c = outbox_by_id[job_c.id]

    cutoff = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    outbox_a.available_at = cutoff - timedelta(minutes=10)
    outbox_b.available_at = cutoff - timedelta(minutes=5)
    outbox_c.available_at = cutoff - timedelta(minutes=5)

    db_session.flush()

    result = get_due_outbox_messages(db=db_session, cutoff=cutoff, limit=3)

    tied_messages = sorted(
        [outbox_b, outbox_c],
        key=lambda message: message.id,
    )

    expected_ids = [
        outbox_a.id,
        tied_messages[0].id,
        tied_messages[1].id,
    ]

    assert [message.id for message in result] == expected_ids


def test_get_due_outbox_messages_respects_batch_limit(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory(
        email="user@example.com",
        password="password123",
    )

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=["FastApi/FastApi"],
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

    job_c = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-789",
    )

    stmt = select(OutboxMessage).where(
        OutboxMessage.job_id.in_([job_a.id, job_b.id, job_c.id])
    )

    outbox_messages = db_session.scalars(stmt).all()

    outbox_by_job_id = {message.job_id: message for message in outbox_messages}

    outbox_a = outbox_by_job_id[job_a.id]
    outbox_b = outbox_by_job_id[job_b.id]
    outbox_c = outbox_by_job_id[job_c.id]

    cutoff = datetime(
        2026,
        10,
        2,
        12,
        0,
        tzinfo=UTC,
    )

    outbox_a.available_at = cutoff - timedelta(minutes=15)
    outbox_b.available_at = cutoff - timedelta(minutes=10)
    outbox_c.available_at = cutoff - timedelta(minutes=5)

    db_session.flush()

    result = get_due_outbox_messages(
        db=db_session,
        cutoff=cutoff,
        limit=2,
    )

    assert len(result) == 2
    assert result[0].id == outbox_a.id
    assert result[1].id == outbox_b.id


def test_get_due_outbox_messages_returns_empty_list_when_no_messages_are_due(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory(
        email="user@example.com",
        password="password123",
    )

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=["FastApi/FastApi"],
        ),
    )

    submitted_job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    stmt = select(OutboxMessage).where(OutboxMessage.job_id == submitted_job.id)
    outbox_message = db_session.scalars(stmt).one()

    cutoff = datetime(
        2026,
        10,
        2,
        12,
        0,
        tzinfo=UTC,
    )

    outbox_message.available_at = cutoff + timedelta(minutes=5)

    db_session.flush()

    result = get_due_outbox_messages(
        db=db_session,
        cutoff=cutoff,
        limit=10,
    )

    assert result == []


def test_get_due_outbox_messages_rejects_naive_cutoff(db_session):
    cutoff = datetime(2026, 10, 2, 12, 0)

    with pytest.raises(
        ValueError,
        match="cutoff must be timezone-aware",
    ):
        get_due_outbox_messages(
            db=db_session,
            cutoff=cutoff,
            limit=10,
        )


def test_mark_outbox_message_published_records_success(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory(
        email="user@example.com", password="password123"
    )

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=["FastApi/FastApi"],
        ),
    )

    job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    stmt = select(OutboxMessage).where(OutboxMessage.job_id == job.id)
    outbox_message = db_session.scalars(stmt).one()

    published_at = datetime(
        2026,
        10,
        2,
        12,
        0,
        tzinfo=UTC,
    )

    outbox_message.last_error = "test error"

    db_session.flush()

    mark_outbox_message_published(
        db=db_session,
        outbox_message=outbox_message,
        published_at=published_at,
    )

    assert outbox_message.published_at == published_at
    assert outbox_message.publish_attempts == 1
    assert outbox_message.last_error is None


def test_mark_outbox_message_failed_records_failure(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory(
        email="user@example.com", password="password123"
    )

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=["FastApi/FastApi"],
        ),
    )

    job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    stmt = select(OutboxMessage).where(OutboxMessage.job_id == job.id)
    outbox_message = db_session.scalars(stmt).one()

    long_error_message = "c" * 300

    mark_outbox_message_failed(
        db=db_session,
        outbox_message=outbox_message,
        error=long_error_message,
    )

    assert outbox_message.published_at is None
    assert outbox_message.publish_attempts == 1
    assert outbox_message.last_error == long_error_message[:255]


def test_failed_outbox_message_remains_selectable(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory(
        email="user@example.com", password="password123"
    )

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=["FastApi/FastApi"],
        ),
    )

    job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    stmt = select(OutboxMessage).where(OutboxMessage.job_id == job.id)
    outbox_message = db_session.scalars(stmt).one()

    cutoff = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    outbox_message.available_at = cutoff - timedelta(minutes=5)
    error = "test error"

    mark_outbox_message_failed(
        db=db_session, outbox_message=outbox_message, error=error
    )

    outbox = get_due_outbox_messages(db=db_session, cutoff=cutoff, limit=1)

    assert len(outbox) == 1
    assert outbox[0].id == outbox_message.id
    assert outbox[0].published_at is None
    assert outbox[0].publish_attempts == 1
    assert outbox[0].last_error == outbox_message.last_error


def test_successful_outbox_message_is_excluded(db_session, authenticated_user_factory):
    user, _ = authenticated_user_factory(
        email="user@example.com", password="password123"
    )

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=["FastApi/FastApi"],
        ),
    )

    job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    stmt = select(OutboxMessage).where(OutboxMessage.job_id == job.id)
    outbox_message = db_session.scalars(stmt).one()

    cutoff = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    outbox_message.available_at = cutoff - timedelta(minutes=5)

    published_at = datetime(
        2026,
        10,
        2,
        12,
        0,
        tzinfo=UTC,
    )

    mark_outbox_message_published(
        db=db_session,
        outbox_message=outbox_message,
        published_at=published_at,
    )

    result = get_due_outbox_messages(
        db=db_session,
        cutoff=cutoff,
        limit=1,
    )

    assert result == []


def test_outbox_publication_rollback_restores_state(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory(
        email="user@example.com", password="password123"
    )

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=["FastApi/FastApi"],
        ),
    )

    job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    job_id = job.id

    stmt = select(OutboxMessage).where(OutboxMessage.job_id == job_id)
    outbox_message = db_session.scalars(stmt).one()

    assert outbox_message.published_at is None
    assert outbox_message.publish_attempts == 0
    assert outbox_message.last_error is None

    published_at = datetime(
        2026,
        10,
        2,
        12,
        0,
        tzinfo=UTC,
    )

    mark_outbox_message_published(
        db=db_session,
        outbox_message=outbox_message,
        published_at=published_at,
    )

    assert outbox_message.published_at == published_at
    assert outbox_message.publish_attempts == 1
    assert outbox_message.last_error is None

    db_session.rollback()

    outbox_message = db_session.scalars(stmt).one()

    assert outbox_message.published_at is None
    assert outbox_message.publish_attempts == 0
    assert outbox_message.last_error is None


def test_mark_outbox_message_published_rejects_naive_timestamp(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory(
        email="user@example.com", password="password123"
    )

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=["FastApi/FastApi"],
        ),
    )

    job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    stmt = select(OutboxMessage).where(OutboxMessage.job_id == job.id)
    outbox_message = db_session.scalars(stmt).one()

    published_at = datetime(2026, 10, 2, 12, 0)

    with pytest.raises(ValueError, match="published_at must be timezone-aware"):
        mark_outbox_message_published(
            db=db_session,
            outbox_message=outbox_message,
            published_at=published_at,
        )

    assert outbox_message.published_at is None
    assert outbox_message.publish_attempts == 0


def test_outbox_failure_state_is_restored_after_rollback(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory(
        email="user@example.com",
        password="password123",
    )

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=["FastApi/FastApi"],
        ),
    )

    job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    job_id = job.id

    stmt = select(OutboxMessage).where(OutboxMessage.job_id == job_id)
    outbox_message = db_session.scalars(stmt).one()

    initial_published_at = outbox_message.published_at
    initial_publish_attempts = outbox_message.publish_attempts
    initial_last_error = outbox_message.last_error

    error = "redis unavailable"

    mark_outbox_message_failed(
        db=db_session,
        outbox_message=outbox_message,
        error=error,
    )

    assert outbox_message.published_at is None
    assert outbox_message.publish_attempts == 1
    assert outbox_message.last_error == error

    db_session.rollback()

    outbox_message = db_session.scalars(stmt).one()

    assert outbox_message.published_at == initial_published_at
    assert outbox_message.publish_attempts == initial_publish_attempts
    assert outbox_message.last_error == initial_last_error


def test_outbox_publication_attempts_accumulate_across_failures_and_success(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory(
        email="user@example.com",
        password="password123",
    )

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=["FastApi/FastApi"],
        ),
    )

    job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    stmt = select(OutboxMessage).where(OutboxMessage.job_id == job.id)
    outbox_message = db_session.scalars(stmt).one()

    mark_outbox_message_failed(
        db=db_session,
        outbox_message=outbox_message,
        error="redis unavailable",
    )

    mark_outbox_message_failed(
        db=db_session,
        outbox_message=outbox_message,
        error="redis still unavailable",
    )

    published_at = datetime(
        2026,
        10,
        5,
        12,
        0,
        tzinfo=UTC,
    )

    mark_outbox_message_published(
        db=db_session,
        outbox_message=outbox_message,
        published_at=published_at,
    )

    assert outbox_message.publish_attempts == 3
    assert outbox_message.published_at == published_at
    assert outbox_message.last_error is None
