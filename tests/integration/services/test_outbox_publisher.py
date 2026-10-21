from datetime import UTC, datetime, timedelta
from unittest.mock import call, patch

import pytest
from kombu.exceptions import OperationalError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.models import OutboxMessage
from app.schemas.jobs import CreateJobRequest, RepositoryBatchAnalysisInput
from app.services.job_service import submit_job
from app.services.outbox_publisher import publish_outbox_batch


def test_publish_outbox_batch_publishes_due_messages_with_correct_job_ids(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory("user@example.com", "password123")

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

    stmt = select(OutboxMessage).where(OutboxMessage.job_id.in_([job_a.id, job_b.id]))

    messages = db_session.scalars(stmt).all()

    messages_by_job_id = {message.job_id: message for message in messages}

    outbox_a = messages_by_job_id[job_a.id]
    outbox_b = messages_by_job_id[job_b.id]

    cutoff = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    outbox_a.available_at = cutoff - timedelta(minutes=10)
    outbox_b.available_at = cutoff - timedelta(minutes=5)

    db_session.flush()

    with patch("app.services.outbox_publisher.publish_process_job") as publish_mock:
        publish_outbox_batch(
            db=db_session,
            cutoff=cutoff,
            limit=10,
        )

    assert publish_mock.call_args_list == [
        call(job_a.id),
        call(job_b.id),
    ]


def test_publish_outbox_batch_success_persists_publication_state(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory("user@example.com", "password123")

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

    stmt = select(OutboxMessage).where(OutboxMessage.job_id == job.id)
    outbox_message = db_session.scalars(stmt).one()

    cutoff = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    outbox_message.available_at = cutoff - timedelta(minutes=5)
    outbox_message.publish_attempts = 1
    outbox_message.last_error = "broker error"

    db_session.flush()

    with patch("app.services.outbox_publisher.publish_process_job") as publish_mock:
        publish_outbox_batch(
            db=db_session,
            cutoff=cutoff,
            limit=10,
        )

    publish_mock.assert_called_once_with(job.id)

    db_session.expire_all()
    outbox_message = db_session.scalars(stmt).one()

    assert outbox_message.published_at is not None
    assert outbox_message.publish_attempts == 2
    assert outbox_message.last_error is None


def test_publish_outbox_batch_failure_persists_error_and_leaves_message_unpublished(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory("user@example.com", "password123")

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

    stmt = select(OutboxMessage).where(OutboxMessage.job_id == job.id)
    outbox_message = db_session.scalars(stmt).one()

    cutoff = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    outbox_message.available_at = cutoff - timedelta(minutes=5)

    db_session.flush()

    with patch(
        "app.services.outbox_publisher.publish_process_job",
        side_effect=OperationalError("broker unavailable"),
    ):
        publish_outbox_batch(
            db=db_session,
            cutoff=cutoff,
            limit=10,
        )

    db_session.expire_all()
    outbox_message = db_session.scalars(stmt).one()

    assert outbox_message.published_at is None
    assert outbox_message.publish_attempts == 1
    assert outbox_message.last_error == "broker unavailable"


def test_publish_outbox_batch_failure_does_not_stop_later_message(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory(
        "user@example.com",
        "password123",
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

    stmt = select(OutboxMessage).where(OutboxMessage.job_id.in_([job_a.id, job_b.id]))
    messages = db_session.scalars(stmt).all()

    messages_by_job_id = {message.job_id: message for message in messages}

    outbox_a = messages_by_job_id[job_a.id]
    outbox_b = messages_by_job_id[job_b.id]

    cutoff = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    outbox_a.available_at = cutoff - timedelta(minutes=10)
    outbox_b.available_at = cutoff - timedelta(minutes=5)

    db_session.flush()

    with patch(
        "app.services.outbox_publisher.publish_process_job",
        side_effect=[
            OperationalError("broker unavailable"),
            None,
        ],
    ) as publish_mock:
        publish_outbox_batch(
            db=db_session,
            cutoff=cutoff,
            limit=10,
        )

    assert publish_mock.call_args_list == [
        call(job_a.id),
        call(job_b.id),
    ]

    db_session.expire_all()

    messages = db_session.scalars(stmt).all()
    messages_by_job_id = {message.job_id: message for message in messages}

    outbox_a = messages_by_job_id[job_a.id]
    outbox_b = messages_by_job_id[job_b.id]

    assert outbox_a.published_at is None
    assert outbox_a.publish_attempts == 1
    assert outbox_a.last_error == "broker unavailable"

    assert outbox_b.published_at is not None
    assert outbox_b.publish_attempts == 1
    assert outbox_b.last_error is None


def test_publish_outbox_batch_skips_future_and_already_published_messages(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory(
        "user@example.com",
        "password123",
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

    job_c = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-789",
    )

    stmt = select(OutboxMessage).where(
        OutboxMessage.job_id.in_([job_a.id, job_b.id, job_c.id])
    )

    messages = db_session.scalars(stmt).all()

    messages_by_job_id = {message.job_id: message for message in messages}

    outbox_a = messages_by_job_id[job_a.id]
    outbox_b = messages_by_job_id[job_b.id]
    outbox_c = messages_by_job_id[job_c.id]

    cutoff = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    outbox_a.available_at = cutoff - timedelta(minutes=5)

    outbox_b.available_at = cutoff + timedelta(minutes=5)

    outbox_c.available_at = cutoff - timedelta(minutes=10)
    outbox_c.published_at = cutoff - timedelta(minutes=2)
    outbox_c.publish_attempts = 1

    db_session.flush()

    with patch("app.services.outbox_publisher.publish_process_job") as publish_mock:
        publish_outbox_batch(
            db=db_session,
            cutoff=cutoff,
            limit=10,
        )

    publish_mock.assert_called_once_with(job_a.id)

    db_session.expire_all()

    messages = db_session.scalars(stmt).all()

    messages_by_job_id = {message.job_id: message for message in messages}

    outbox_a = messages_by_job_id[job_a.id]
    outbox_b = messages_by_job_id[job_b.id]
    outbox_c = messages_by_job_id[job_c.id]

    assert outbox_a.published_at is not None
    assert outbox_a.publish_attempts == 1

    assert outbox_b.published_at is None
    assert outbox_b.publish_attempts == 0

    assert outbox_c.published_at == cutoff - timedelta(minutes=2)
    assert outbox_c.publish_attempts == 1


def test_publish_outbox_batch_respects_limit(db_session, authenticated_user_factory):
    user, _ = authenticated_user_factory(
        "user@example.com",
        "password123",
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

    job_c = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-789",
    )

    stmt = select(OutboxMessage).where(
        OutboxMessage.job_id.in_([job_a.id, job_b.id, job_c.id])
    )

    messages = db_session.scalars(stmt).all()

    messages_by_job_id = {message.job_id: message for message in messages}

    outbox_a = messages_by_job_id[job_a.id]
    outbox_b = messages_by_job_id[job_b.id]
    outbox_c = messages_by_job_id[job_c.id]

    cutoff = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    outbox_a.available_at = cutoff - timedelta(minutes=15)
    outbox_b.available_at = cutoff - timedelta(minutes=10)
    outbox_c.available_at = cutoff - timedelta(minutes=5)

    db_session.flush()

    with patch("app.services.outbox_publisher.publish_process_job") as publish_mock:
        publish_outbox_batch(
            db=db_session,
            cutoff=cutoff,
            limit=2,
        )

    assert publish_mock.call_args_list == [
        call(job_a.id),
        call(job_b.id),
    ]

    db_session.expire_all()

    messages = db_session.scalars(stmt).all()

    messages_by_job_id = {message.job_id: message for message in messages}

    outbox_a = messages_by_job_id[job_a.id]
    outbox_b = messages_by_job_id[job_b.id]
    outbox_c = messages_by_job_id[job_c.id]

    assert outbox_a.published_at is not None
    assert outbox_a.publish_attempts == 1

    assert outbox_b.published_at is not None
    assert outbox_b.publish_attempts == 1

    assert outbox_c.published_at is None
    assert outbox_c.publish_attempts == 0


def test_publish_outbox_batch_with_no_due_messages_does_not_publish(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory(
        "user@example.com",
        "password123",
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

    job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    stmt = select(OutboxMessage).where(OutboxMessage.job_id == job.id)
    outbox_message = db_session.scalars(stmt).one()

    cutoff = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    outbox_message.available_at = cutoff + timedelta(minutes=5)

    db_session.flush()

    with patch("app.services.outbox_publisher.publish_process_job") as publish_mock:
        publish_outbox_batch(
            db=db_session,
            cutoff=cutoff,
            limit=10,
        )

    publish_mock.assert_not_called()

    db_session.expire_all()
    outbox_message = db_session.scalars(stmt).one()

    assert outbox_message.published_at is None
    assert outbox_message.publish_attempts == 0
    assert outbox_message.last_error is None


def test_publish_outbox_batch_database_failure_rolls_back_and_propagates(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory(
        "user@example.com",
        "password123",
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

    db_session.flush()

    with (
        patch("app.services.outbox_publisher.publish_process_job") as publish_mock,
        patch.object(
            db_session,
            "commit",
            side_effect=SQLAlchemyError("database unavailable"),
        ),
    ):
        with pytest.raises(
            SQLAlchemyError,
            match="database unavailable",
        ):
            publish_outbox_batch(
                db=db_session,
                cutoff=cutoff,
                limit=10,
            )

    publish_mock.assert_called_once_with(job.id)

    db_session.expire_all()
    outbox_message = db_session.scalars(stmt).one()

    assert outbox_message.published_at is None
    assert outbox_message.publish_attempts == 0
    assert outbox_message.last_error is None
