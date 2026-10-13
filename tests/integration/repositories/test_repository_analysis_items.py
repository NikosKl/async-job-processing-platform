import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.domain.enums import JobStatus, RepositoryStatus
from app.models import Job, RepositoryAnalysisItem
from app.repositories.repository_analysis_item import (
    list_repository_analysis_items_by_job_id,
    persist_successful_item_result,
)
from app.repositories.user import create_user
from app.schemas.jobs import CreateJobRequest, RepositoryBatchAnalysisInput
from app.services.job_service import claim_job_for_execution, submit_job


def test_list_repository_analysis_items_by_job_id_excludes_other_jobs_items(
    db_session, authenticated_user_factory
):
    user_a, _ = authenticated_user_factory("user_a@example.com", "password123")

    user_b = create_user(
        db_session,
        email="user_b@example.com",
        hashed_password="password123",
    )

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["owner/repository"]),
    )

    job_a = submit_job(
        db_session,
        user_a.id,
        request=request,
        idempotency_key="test-key-123",
    )

    job_b = submit_job(
        db_session,
        user_b.id,
        request=request,
        idempotency_key="test-key-456",
    )

    items = list_repository_analysis_items_by_job_id(
        db_session,
        job_a.id,
    )

    assert len(items) == 1
    assert items[0].job_id == job_a.id
    assert items[0].job_id != job_b.id


def test_list_repository_analysis_items_by_job_id_returns_items_in_position_order(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=["FastApi/FastApi", "SQLAlchemy/SQLAlchemy", "Pallets/Flask"]
        ),
    )

    job = submit_job(
        db_session,
        user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    items = list_repository_analysis_items_by_job_id(
        db_session,
        job.id,
    )

    assert len(items) == 3
    assert [item.position for item in items] == [0, 1, 2]


def test_list_repository_analysis_items_by_job_id_returns_empty_list_for_unknown_job(
    db_session,
):
    job_id = uuid.uuid4()

    items = list_repository_analysis_items_by_job_id(
        db_session,
        job_id,
    )

    assert items == []


def test_persist_successful_item_result_current_owner_can_update_pending_item(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=["FastApi/FastApi", "SQLAlchemy/SQLAlchemy", "Pallets/Flask"]
        ),
    )

    job = submit_job(
        db_session,
        user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    lease_duration = timedelta(minutes=10)

    claimed_job = claim_job_for_execution(
        db=db_session,
        job_id=job.id,
        claim_time=claim_time,
        lease_duration=lease_duration,
    )

    assert claimed_job is not None
    assert claimed_job.execution_token is not None

    stmt = select(RepositoryAnalysisItem).where(RepositoryAnalysisItem.job_id == job.id)
    item = db_session.scalar(stmt)

    assert item is not None
    assert item.status == RepositoryStatus.PENDING

    completed_at = datetime.now(UTC)

    result = persist_successful_item_result(
        db=db_session,
        job_id=job.id,
        item_id=item.id,
        execution_token=claimed_job.execution_token,
        stars=100,
        forks=20,
        open_issues=5,
        completed_at=completed_at,
    )

    assert result is True
    assert item.status == RepositoryStatus.SUCCEEDED
    assert item.stars == 100
    assert item.forks == 20
    assert item.open_issues == 5
    assert item.attempt_count == 1
    assert item.completed_at == completed_at
    assert item.error_type is None
    assert item.error_message is None


def test_persist_successful_item_result_wrong_execution_token_leaves_item_unchanged(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=["FastApi/FastApi", "SQLAlchemy/SQLAlchemy", "Pallets/Flask"]
        ),
    )

    job = submit_job(
        db_session,
        user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    lease_duration = timedelta(minutes=10)

    claimed_job = claim_job_for_execution(
        db=db_session,
        job_id=job.id,
        claim_time=claim_time,
        lease_duration=lease_duration,
    )

    assert claimed_job is not None
    assert claimed_job.status == JobStatus.RUNNING

    stmt = select(RepositoryAnalysisItem).where(RepositoryAnalysisItem.job_id == job.id)
    item = db_session.scalar(stmt)

    assert item is not None

    wrong_token = uuid.uuid4()

    completed_at = datetime.now(UTC)

    result = persist_successful_item_result(
        db=db_session,
        job_id=job.id,
        item_id=item.id,
        execution_token=wrong_token,
        stars=100,
        forks=20,
        open_issues=5,
        completed_at=completed_at,
    )

    assert result is False
    assert item.status == RepositoryStatus.PENDING
    assert item.stars is None
    assert item.forks is None
    assert item.open_issues is None
    assert item.attempt_count == 0
    assert item.completed_at is None


def test_persist_successful_item_result_non_running_job_leaves_item_unchanged(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=["FastApi/FastApi", "SQLAlchemy/SQLAlchemy", "Pallets/Flask"]
        ),
    )

    job = submit_job(
        db_session,
        user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    lease_duration = timedelta(minutes=10)

    claimed_job = claim_job_for_execution(
        db=db_session,
        job_id=job.id,
        claim_time=claim_time,
        lease_duration=lease_duration,
    )

    stmt = select(RepositoryAnalysisItem).where(RepositoryAnalysisItem.job_id == job.id)
    item = db_session.scalar(stmt)

    assert item is not None
    assert item.status == RepositoryStatus.PENDING
    assert claimed_job is not None
    assert claimed_job.execution_token is not None

    execution_token = claimed_job.execution_token

    claimed_job.status = JobStatus.COMPLETED
    db_session.flush()

    completed_at = datetime.now(UTC)

    result = persist_successful_item_result(
        db=db_session,
        job_id=job.id,
        item_id=item.id,
        execution_token=execution_token,
        stars=100,
        forks=20,
        open_issues=5,
        completed_at=completed_at,
    )

    assert result is False
    assert item.status == RepositoryStatus.PENDING
    assert item.attempt_count == 0
    assert item.stars is None
    assert item.forks is None
    assert item.open_issues is None
    assert item.completed_at is None


def test_persist_successful_item_result_item_from_another_job_is_unchanged(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory("user@example.com", "password123")

    request_a = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["FastApi/FastApi"]),
    )

    request_b = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["SQLAlchemy/SQLAlchemy"]),
    )

    job_a = submit_job(
        db_session,
        user.id,
        request=request_a,
        idempotency_key="test-key-a",
    )

    job_b = submit_job(
        db_session,
        user.id,
        request=request_b,
        idempotency_key="test-key-b",
    )

    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    lease_duration = timedelta(minutes=10)

    claimed_job_a = claim_job_for_execution(
        db=db_session,
        job_id=job_a.id,
        claim_time=claim_time,
        lease_duration=lease_duration,
    )

    assert claimed_job_a is not None
    assert claimed_job_a.execution_token is not None

    stmt = select(RepositoryAnalysisItem).where(
        RepositoryAnalysisItem.job_id == job_b.id
    )
    item_b = db_session.scalar(stmt)

    assert item_b is not None
    assert item_b.status == RepositoryStatus.PENDING

    completed_at = datetime.now(UTC)

    result = persist_successful_item_result(
        db=db_session,
        job_id=job_a.id,
        item_id=item_b.id,
        execution_token=claimed_job_a.execution_token,
        stars=100,
        forks=20,
        open_issues=5,
        completed_at=completed_at,
    )

    assert result is False
    assert item_b.status == RepositoryStatus.PENDING
    assert item_b.attempt_count == 0
    assert item_b.stars is None
    assert item_b.forks is None
    assert item_b.open_issues is None
    assert item_b.completed_at is None


def test_persist_successful_item_result_terminal_item_is_unchanged(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=["FastApi/FastApi", "SQLAlchemy/SQLAlchemy", "Pallets/Flask"]
        ),
    )

    job = submit_job(
        db_session,
        user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    lease_duration = timedelta(minutes=10)

    claimed_job = claim_job_for_execution(
        db=db_session,
        job_id=job.id,
        claim_time=claim_time,
        lease_duration=lease_duration,
    )

    assert claimed_job is not None
    assert claimed_job.execution_token is not None

    stmt = select(RepositoryAnalysisItem).where(RepositoryAnalysisItem.job_id == job.id)
    item = db_session.scalar(stmt)

    item.status = RepositoryStatus.SUCCEEDED
    item.attempt_count = 1
    db_session.flush()

    completed_at = datetime.now(UTC)

    result = persist_successful_item_result(
        db=db_session,
        job_id=job.id,
        item_id=item.id,
        execution_token=claimed_job.execution_token,
        stars=100,
        forks=20,
        open_issues=5,
        completed_at=completed_at,
    )

    assert result is False
    assert item.status == RepositoryStatus.SUCCEEDED
    assert item.attempt_count == 1


def test_persist_successful_item_result_missing_job_returns_false(
    db_session,
):
    completed_at = datetime.now(UTC)

    result = persist_successful_item_result(
        db=db_session,
        job_id=uuid.uuid4(),
        item_id=uuid.uuid4(),
        execution_token=uuid.uuid4(),
        stars=100,
        forks=20,
        open_issues=5,
        completed_at=completed_at,
    )

    assert result is False


def test_persist_successful_item_result_missing_item_returns_false(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=["FastApi/FastApi", "SQLAlchemy/SQLAlchemy", "Pallets/Flask"]
        ),
    )

    job = submit_job(
        db_session,
        user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    lease_duration = timedelta(minutes=10)

    claimed_job = claim_job_for_execution(
        db=db_session,
        job_id=job.id,
        claim_time=claim_time,
        lease_duration=lease_duration,
    )

    assert claimed_job is not None
    assert claimed_job.execution_token is not None

    completed_at = datetime.now(UTC)

    result = persist_successful_item_result(
        db=db_session,
        job_id=job.id,
        item_id=uuid.uuid4(),
        execution_token=claimed_job.execution_token,
        stars=100,
        forks=20,
        open_issues=5,
        completed_at=completed_at,
    )

    assert result is False


def test_persist_successful_item_result_rollback_restores_original_item_state(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=["FastApi/FastApi", "SQLAlchemy/SQLAlchemy", "Pallets/Flask"]
        ),
    )

    job = submit_job(
        db_session,
        user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    lease_duration = timedelta(minutes=10)

    claimed_job = claim_job_for_execution(
        db=db_session,
        job_id=job.id,
        claim_time=claim_time,
        lease_duration=lease_duration,
    )

    assert claimed_job is not None
    assert claimed_job.execution_token is not None

    stmt = select(RepositoryAnalysisItem).where(RepositoryAnalysisItem.job_id == job.id)
    item = db_session.scalar(stmt)

    assert item is not None
    assert item.status == RepositoryStatus.PENDING

    completed_at = datetime.now(UTC)

    result = persist_successful_item_result(
        db=db_session,
        job_id=job.id,
        item_id=item.id,
        execution_token=claimed_job.execution_token,
        stars=100,
        forks=20,
        open_issues=5,
        completed_at=completed_at,
    )

    assert result is True

    db_session.flush()

    assert item.status == RepositoryStatus.SUCCEEDED
    assert item.attempt_count == 1

    db_session.rollback()

    item = db_session.scalar(stmt)

    assert item.status == RepositoryStatus.PENDING
    assert item.attempt_count == 0
    assert item.stars is None
    assert item.forks is None
    assert item.open_issues is None
    assert item.completed_at is None


def test_persist_successful_item_result_rejects_naive_completed_at(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=["FastApi/FastApi", "SQLAlchemy/SQLAlchemy", "Pallets/Flask"]
        ),
    )

    job = submit_job(
        db_session,
        user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    lease_duration = timedelta(minutes=10)

    claimed_job = claim_job_for_execution(
        db=db_session,
        job_id=job.id,
        claim_time=claim_time,
        lease_duration=lease_duration,
    )

    assert claimed_job is not None
    assert claimed_job.execution_token is not None

    stmt = select(RepositoryAnalysisItem).where(RepositoryAnalysisItem.job_id == job.id)
    item = db_session.scalar(stmt)

    assert item is not None
    assert item.status == RepositoryStatus.PENDING

    completed_at = datetime(2026, 10, 2, 12, 0)

    with pytest.raises(ValueError, match="completed_at must be timezone-aware"):
        persist_successful_item_result(
            db=db_session,
            job_id=job.id,
            item_id=item.id,
            execution_token=claimed_job.execution_token,
            stars=100,
            forks=20,
            open_issues=5,
            completed_at=completed_at,
        )

    assert item.status == RepositoryStatus.PENDING
    assert item.attempt_count == 0
    assert item.stars is None
    assert item.forks is None
    assert item.open_issues is None
    assert item.completed_at is None


def test_persist_successful_item_result_second_call_before_commit_is_rejected(
    db_session, authenticated_user_factory
):
    user, _ = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["FastApi/FastApi"]),
    )

    job = submit_job(
        db_session,
        user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    lease_duration = timedelta(minutes=10)

    claimed_job = claim_job_for_execution(
        db=db_session,
        job_id=job.id,
        claim_time=claim_time,
        lease_duration=lease_duration,
    )

    assert claimed_job is not None
    assert claimed_job.execution_token is not None

    stmt = select(RepositoryAnalysisItem).where(RepositoryAnalysisItem.job_id == job.id)
    item = db_session.scalar(stmt)

    assert item is not None
    assert item.status == RepositoryStatus.PENDING

    completed_at = datetime.now(UTC)

    first_result = persist_successful_item_result(
        db=db_session,
        job_id=job.id,
        item_id=item.id,
        execution_token=claimed_job.execution_token,
        stars=100,
        forks=20,
        open_issues=5,
        completed_at=completed_at,
    )

    second_result = persist_successful_item_result(
        db=db_session,
        job_id=job.id,
        item_id=item.id,
        execution_token=claimed_job.execution_token,
        stars=999,
        forks=999,
        open_issues=999,
        completed_at=completed_at,
    )

    assert first_result is True
    assert second_result is False

    assert item.status == RepositoryStatus.SUCCEEDED
    assert item.attempt_count == 1
    assert item.stars == 100
    assert item.forks == 20
    assert item.open_issues == 5


def test_persist_successful_item_result_rejects_stale_execution_token(
    test_session_factory,
):
    with test_session_factory() as setup_session:
        user = create_user(
            setup_session,
            email="user@example.com",
            hashed_password="hashed_password",
        )
        setup_session.commit()

        request = CreateJobRequest(
            type="repository_batch_analysis",
            input=RepositoryBatchAnalysisInput(repositories=["FastApi/FastApi"]),
        )

        job = submit_job(
            setup_session,
            user.id,
            request=request,
            idempotency_key="test-key-123",
        )

        claimed_job = claim_job_for_execution(
            db=setup_session,
            job_id=job.id,
            claim_time=datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
            lease_duration=timedelta(minutes=10),
        )

        assert claimed_job is not None
        assert claimed_job.execution_token is not None

        job_id = job.id
        token_a = claimed_job.execution_token

        item = setup_session.scalar(
            select(RepositoryAnalysisItem).where(
                RepositoryAnalysisItem.job_id == job_id
            )
        )

        assert item is not None

        item_id = item.id

        setup_session.commit()

    with test_session_factory() as session_a:
        stale_job = session_a.get(Job, job_id)

        assert stale_job is not None
        assert stale_job.execution_token == token_a

        with test_session_factory() as session_b:
            job_b = session_b.get(Job, job_id)

            assert job_b is not None

            job_b.execution_token = uuid.uuid4()
            session_b.commit()

        assert stale_job.execution_token == token_a

        result = persist_successful_item_result(
            db=session_a,
            job_id=job_id,
            item_id=item_id,
            execution_token=token_a,
            stars=100,
            forks=20,
            open_issues=5,
            completed_at=datetime.now(UTC),
        )

        assert result is False

        item = session_a.get(RepositoryAnalysisItem, item_id)

        assert item is not None
        assert item.status == RepositoryStatus.PENDING
        assert item.attempt_count == 0
        assert item.stars is None
        assert item.forks is None
        assert item.open_issues is None
        assert item.completed_at is None
