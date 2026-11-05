import asyncio
import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domain.enums import JobAttemptStatus, JobStatus, RepositoryStatus
from app.domain.repository_analysis import RepositoryAnalysisResult
from app.models import Job, JobAttempt, RepositoryAnalysisItem
from app.services.job_execution_service import (
    complete_claimed_job,
    execute_claimed_job,
    execute_claimed_job_async,
    save_item_result_and_update_progress,
)


def test_save_item_result_updates_progress_success(db_session, claimed_job_factory):
    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    _, _, claimed_job, items = claimed_job_factory(
        repositories=["FastApi/FastApi"],
        claim_time=claim_time,
        idempotency_key="test-key-123",
    )

    item = items[0]
    item_id = item.id
    job_id = claimed_job.id

    assert item.status == RepositoryStatus.PENDING

    analysis_result = RepositoryAnalysisResult(
        owner=item.owner,
        repository=item.repository_name,
        stars=10,
        forks=5,
        open_issues=2,
    )

    completed_at = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    result = save_item_result_and_update_progress(
        db=db_session,
        job_id=job_id,
        item_id=item_id,
        execution_token=claimed_job.execution_token,
        analysis_result=analysis_result,
        completed_at=completed_at,
    )

    assert result is True

    db_session.expire_all()

    stmt = select(Job).where(Job.id == job_id)
    job = db_session.scalars(stmt).one()

    stmt = select(RepositoryAnalysisItem).where(RepositoryAnalysisItem.id == item_id)
    item = db_session.scalars(stmt).one()

    assert job.progress_completed == 1

    assert item.status == RepositoryStatus.SUCCEEDED
    assert item.stars == analysis_result.stars
    assert item.forks == analysis_result.forks
    assert item.open_issues == analysis_result.open_issues
    assert item.completed_at == completed_at


def test_save_item_result_and_update_progress_repeated_result(
    db_session, claimed_job_factory
):
    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    _, _, claimed_job, items = claimed_job_factory(
        repositories=["FastApi/FastApi"],
        claim_time=claim_time,
        idempotency_key="test-key-123",
    )

    item = items[0]
    item_id = item.id
    job_id = claimed_job.id

    assert item.status == RepositoryStatus.PENDING

    analysis_result = RepositoryAnalysisResult(
        owner=item.owner,
        repository=item.repository_name,
        stars=10,
        forks=5,
        open_issues=2,
    )

    completed_at = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    result = save_item_result_and_update_progress(
        db=db_session,
        job_id=job_id,
        item_id=item_id,
        execution_token=claimed_job.execution_token,
        analysis_result=analysis_result,
        completed_at=completed_at,
    )

    assert result is True

    second_call = save_item_result_and_update_progress(
        db=db_session,
        job_id=job_id,
        item_id=item_id,
        execution_token=claimed_job.execution_token,
        analysis_result=analysis_result,
        completed_at=completed_at,
    )

    assert second_call is False

    db_session.expire_all()

    stmt = select(Job).where(Job.id == job_id)
    job = db_session.scalars(stmt).one()

    stmt = select(RepositoryAnalysisItem).where(RepositoryAnalysisItem.id == item_id)
    item = db_session.scalars(stmt).one()

    assert job.progress_completed == 1
    assert item.status == RepositoryStatus.SUCCEEDED
    assert item.stars == analysis_result.stars
    assert item.forks == analysis_result.forks
    assert item.open_issues == analysis_result.open_issues
    assert item.completed_at == completed_at


def test_save_item_result_and_update_progress_wrong_token(
    db_session, claimed_job_factory
):
    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    _, _, claimed_job, items = claimed_job_factory(
        repositories=["FastApi/FastApi"],
        claim_time=claim_time,
        idempotency_key="test-key-123",
    )

    item = items[0]
    item_id = item.id
    job_id = claimed_job.id

    assert item.status == RepositoryStatus.PENDING

    analysis_result = RepositoryAnalysisResult(
        owner=item.owner,
        repository=item.repository_name,
        stars=10,
        forks=5,
        open_issues=2,
    )

    completed_at = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    wrong_token = uuid.uuid4()

    result = save_item_result_and_update_progress(
        db=db_session,
        job_id=job_id,
        item_id=item_id,
        execution_token=wrong_token,
        analysis_result=analysis_result,
        completed_at=completed_at,
    )

    assert result is False

    db_session.expire_all()

    stmt = select(Job).where(Job.id == job_id)
    job = db_session.scalars(stmt).one()

    stmt = select(RepositoryAnalysisItem).where(RepositoryAnalysisItem.id == item_id)
    item = db_session.scalars(stmt).one()

    assert job.progress_completed == 0
    assert item.status == RepositoryStatus.PENDING
    assert item.stars is None
    assert item.forks is None
    assert item.open_issues is None
    assert item.completed_at is None


def test_save_item_result_and_update_progress_rejected_item(
    db_session, claimed_job_factory
):
    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    _, _, claimed_job, items = claimed_job_factory(
        repositories=["FastApi/FastApi"],
        claim_time=claim_time,
        idempotency_key="test-key-123",
    )

    item = items[0]
    item_id = item.id
    job_id = claimed_job.id

    assert item.status == RepositoryStatus.PENDING

    analysis_result = RepositoryAnalysisResult(
        owner=item.owner,
        repository=item.repository_name,
        stars=10,
        forks=5,
        open_issues=2,
    )

    completed_at = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    wrong_item_id = uuid.uuid4()

    result = save_item_result_and_update_progress(
        db=db_session,
        job_id=job_id,
        item_id=wrong_item_id,
        execution_token=claimed_job.execution_token,
        analysis_result=analysis_result,
        completed_at=completed_at,
    )

    assert result is False

    db_session.expire_all()

    stmt = select(Job).where(Job.id == job_id)
    job = db_session.scalars(stmt).one()

    stmt = select(RepositoryAnalysisItem).where(RepositoryAnalysisItem.id == item_id)
    item = db_session.scalars(stmt).one()

    assert job.progress_completed == 0

    assert item.status == RepositoryStatus.PENDING
    assert item.stars is None
    assert item.forks is None
    assert item.open_issues is None
    assert item.completed_at is None


def test_save_item_result_and_update_progress_rolls_back_on_progress_failure(
    db_session, claimed_job_factory
):
    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    _, _, claimed_job, items = claimed_job_factory(
        repositories=["FastApi/FastApi"],
        claim_time=claim_time,
        idempotency_key="test-key-123",
    )

    item = items[0]
    job_id = claimed_job.id
    item_id = item.id

    analysis_result = RepositoryAnalysisResult(
        owner=item.owner,
        repository=item.repository_name,
        stars=10,
        forks=5,
        open_issues=2,
    )

    completed_at = datetime(2026, 10, 2, 12, 5, tzinfo=UTC)

    with patch(
        "app.services.job_execution_service.increment_job_progress",
        side_effect=SQLAlchemyError("progress update failed"),
    ):
        with pytest.raises(SQLAlchemyError, match="progress update failed"):
            save_item_result_and_update_progress(
                db=db_session,
                job_id=job_id,
                item_id=item_id,
                execution_token=claimed_job.execution_token,
                analysis_result=analysis_result,
                completed_at=completed_at,
            )

    db_session.expire_all()

    stmt = select(Job).where(Job.id == job_id)
    job = db_session.scalars(stmt).one()

    stmt = select(RepositoryAnalysisItem).where(RepositoryAnalysisItem.id == item_id)
    item = db_session.scalars(stmt).one()

    assert job.progress_completed == 0

    assert item.status == RepositoryStatus.PENDING
    assert item.stars is None
    assert item.forks is None
    assert item.open_issues is None
    assert item.completed_at is None


def test_save_item_result_and_update_progress_rolls_back_on_commit_failure(
    db_session, claimed_job_factory
):
    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    _, _, claimed_job, items = claimed_job_factory(
        repositories=["FastApi/FastApi"],
        claim_time=claim_time,
        idempotency_key="test-key-123",
    )

    item = items[0]
    job_id = claimed_job.id
    item_id = item.id

    analysis_result = RepositoryAnalysisResult(
        owner=item.owner,
        repository=item.repository_name,
        stars=10,
        forks=5,
        open_issues=2,
    )

    completed_at = datetime(2026, 10, 2, 12, 5, tzinfo=UTC)

    with patch.object(
        Session,
        "commit",
        side_effect=SQLAlchemyError("commit failed"),
    ):
        with pytest.raises(SQLAlchemyError, match="commit failed"):
            save_item_result_and_update_progress(
                db=db_session,
                job_id=job_id,
                item_id=item_id,
                execution_token=claimed_job.execution_token,
                analysis_result=analysis_result,
                completed_at=completed_at,
            )

    db_session.expire_all()

    stmt = select(Job).where(Job.id == job_id)
    job = db_session.scalars(stmt).one()

    stmt = select(RepositoryAnalysisItem).where(RepositoryAnalysisItem.id == item_id)
    item = db_session.scalars(stmt).one()

    assert job.progress_completed == 0

    assert item.status == RepositoryStatus.PENDING
    assert item.stars is None
    assert item.forks is None
    assert item.open_issues is None
    assert item.completed_at is None


def test_save_item_result_and_update_progress_accumulates_progress(
    db_session, claimed_job_factory
):
    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    _, _, claimed_job, items = claimed_job_factory(
        repositories=[
            "FastApi/FastApi",
            "SQLAlchemy/SQLAlchemy",
            "Pallets/Flask",
        ],
        claim_time=claim_time,
        idempotency_key="test-key-123",
    )

    job_id = claimed_job.id

    for item in items:
        item_id = item.id

        analysis_result = RepositoryAnalysisResult(
            owner=item.owner,
            repository=item.repository_name,
            stars=10,
            forks=5,
            open_issues=2,
        )

        completed_at = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

        result = save_item_result_and_update_progress(
            db=db_session,
            job_id=job_id,
            item_id=item_id,
            execution_token=claimed_job.execution_token,
            analysis_result=analysis_result,
            completed_at=completed_at,
        )

        assert result is True

    db_session.expire_all()

    stmt = select(Job).where(Job.id == job_id)
    job = db_session.scalars(stmt).one()

    stmt = select(RepositoryAnalysisItem).where(RepositoryAnalysisItem.job_id == job_id)
    items = db_session.scalars(stmt).all()

    assert job.progress_completed == 3
    assert len(items) == 3

    for item in items:
        assert item.status == RepositoryStatus.SUCCEEDED


def test_complete_claimed_job_all_successful_items(db_session, claimed_job_factory):
    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    _, _, claimed_job, items = claimed_job_factory(
        repositories=[
            "FastApi/FastApi",
            "SQLAlchemy/SQLAlchemy",
        ],
        claim_time=claim_time,
        idempotency_key="test-key-123",
    )

    job_id = claimed_job.id
    execution_token = claimed_job.execution_token

    assert execution_token is not None

    item_completed_at = datetime(2026, 10, 2, 12, 1, tzinfo=UTC)

    for item in items:
        assert item.status == RepositoryStatus.PENDING

        analysis_result = RepositoryAnalysisResult(
            owner=item.owner,
            repository=item.repository_name,
            stars=10,
            forks=5,
            open_issues=2,
        )

        result = save_item_result_and_update_progress(
            db=db_session,
            job_id=job_id,
            item_id=item.id,
            execution_token=execution_token,
            analysis_result=analysis_result,
            completed_at=item_completed_at,
        )

        assert result is True

    job_completed_at = datetime(2026, 10, 2, 12, 3, tzinfo=UTC)

    completed_job = complete_claimed_job(
        db=db_session,
        job_id=job_id,
        execution_token=execution_token,
        completed_at=job_completed_at,
    )

    assert completed_job is True

    db_session.expire_all()

    stmt = select(Job).where(Job.id == job_id)
    job = db_session.scalars(stmt).one()

    stmt = select(JobAttempt).where(JobAttempt.job_id == job_id)
    attempt = db_session.scalars(stmt).one()

    assert job.status == JobStatus.COMPLETED
    assert job.finished_at == job_completed_at
    assert job.progress_completed == 2
    assert job.result_summary == {
        "total": 2,
        "succeeded": 2,
        "failed": 0,
    }
    assert job.execution_token is None
    assert job.lease_expires_at is None

    assert attempt.status == JobAttemptStatus.SUCCEEDED
    assert attempt.finished_at == job_completed_at
    assert attempt.execution_token == execution_token


def test_complete_claimed_job_mixed_item_results(db_session, claimed_job_factory):
    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    _, _, claimed_job, items = claimed_job_factory(
        repositories=["FastApi/FastApi", "SQLAlchemy/SQLAlchemy", "Pallets/Flask"],
        claim_time=claim_time,
        idempotency_key="test-key-123",
    )

    job_id = claimed_job.id
    execution_token = claimed_job.execution_token

    assert execution_token is not None

    item_completed_at = datetime(2026, 10, 2, 12, 1, tzinfo=UTC)

    for index, item in enumerate(items):
        if index == 2:
            item.status = RepositoryStatus.FAILED
            item.completed_at = item_completed_at
            db_session.flush()
            db_session.commit()
        else:
            assert item.status == RepositoryStatus.PENDING

            analysis_result = RepositoryAnalysisResult(
                owner=item.owner,
                repository=item.repository_name,
                stars=10,
                forks=5,
                open_issues=2,
            )

            result = save_item_result_and_update_progress(
                db=db_session,
                job_id=job_id,
                item_id=item.id,
                execution_token=execution_token,
                analysis_result=analysis_result,
                completed_at=item_completed_at,
            )

            assert result is True

    job_completed_at = datetime(2026, 10, 2, 12, 3, tzinfo=UTC)

    completed_job = complete_claimed_job(
        db=db_session,
        job_id=job_id,
        execution_token=execution_token,
        completed_at=job_completed_at,
    )

    assert completed_job is True

    db_session.expire_all()

    stmt = select(Job).where(Job.id == job_id)
    job = db_session.scalars(stmt).one()

    stmt = select(JobAttempt).where(JobAttempt.job_id == job_id)
    attempt = db_session.scalars(stmt).one()

    assert job.status == JobStatus.COMPLETED
    assert job.progress_completed == 3

    assert job.result_summary == {
        "total": 3,
        "succeeded": 2,
        "failed": 1,
    }

    assert job.finished_at == job_completed_at
    assert job.execution_token is None
    assert job.lease_expires_at is None

    assert attempt.status == JobAttemptStatus.SUCCEEDED
    assert attempt.finished_at == job_completed_at


def test_complete_claimed_job_pending_item_prevents_completion(
    db_session, claimed_job_factory
):
    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    _, _, claimed_job, items = claimed_job_factory(
        repositories=[
            "FastApi/FastApi",
            "SQLAlchemy/SQLAlchemy",
        ],
        claim_time=claim_time,
        idempotency_key="test-key-123",
    )

    job_id = claimed_job.id
    execution_token = claimed_job.execution_token
    lease_expires_at = claimed_job.lease_expires_at

    assert execution_token is not None

    item_completed_at = datetime(2026, 10, 2, 12, 1, tzinfo=UTC)

    for index, item in enumerate(items):
        if index == 1:
            continue

        assert item.status == RepositoryStatus.PENDING

        analysis_result = RepositoryAnalysisResult(
            owner=item.owner,
            repository=item.repository_name,
            stars=10,
            forks=5,
            open_issues=2,
        )

        result = save_item_result_and_update_progress(
            db=db_session,
            job_id=job_id,
            item_id=item.id,
            execution_token=execution_token,
            analysis_result=analysis_result,
            completed_at=item_completed_at,
        )

        assert result is True

    job_completed_at = datetime(2026, 10, 2, 12, 3, tzinfo=UTC)

    completed_job = complete_claimed_job(
        db=db_session,
        job_id=job_id,
        execution_token=execution_token,
        completed_at=job_completed_at,
    )

    assert completed_job is False

    db_session.expire_all()

    stmt = select(Job).where(Job.id == job_id)
    job = db_session.scalars(stmt).one()

    stmt = select(JobAttempt).where(JobAttempt.job_id == job_id)
    attempt = db_session.scalars(stmt).one()

    assert job.status == JobStatus.RUNNING
    assert job.finished_at is None
    assert job.execution_token == execution_token
    assert job.lease_expires_at == lease_expires_at
    assert job.progress_completed == 1

    assert attempt.status == JobAttemptStatus.RUNNING
    assert attempt.finished_at is None


def test_complete_claimed_job_wrong_token_changes_nothing(
    db_session, claimed_job_factory
):
    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    _, _, claimed_job, items = claimed_job_factory(
        repositories=[
            "FastApi/FastApi",
            "SQLAlchemy/SQLAlchemy",
        ],
        claim_time=claim_time,
        idempotency_key="test-key-123",
    )

    job_id = claimed_job.id
    execution_token = claimed_job.execution_token
    lease_expires_at = claimed_job.lease_expires_at

    assert execution_token is not None

    item_completed_at = datetime(2026, 10, 2, 12, 1, tzinfo=UTC)

    for item in items:
        assert item.status == RepositoryStatus.PENDING

        analysis_result = RepositoryAnalysisResult(
            owner=item.owner,
            repository=item.repository_name,
            stars=10,
            forks=5,
            open_issues=2,
        )

        result = save_item_result_and_update_progress(
            db=db_session,
            job_id=job_id,
            item_id=item.id,
            execution_token=execution_token,
            analysis_result=analysis_result,
            completed_at=item_completed_at,
        )

        assert result is True

    job_completed_at = datetime(2026, 10, 2, 12, 3, tzinfo=UTC)
    wrong_execution_token = uuid.uuid4()

    completed_job = complete_claimed_job(
        db=db_session,
        job_id=job_id,
        execution_token=wrong_execution_token,
        completed_at=job_completed_at,
    )

    assert completed_job is False

    db_session.expire_all()

    stmt = select(Job).where(Job.id == job_id)
    job = db_session.scalars(stmt).one()

    stmt = select(JobAttempt).where(JobAttempt.job_id == job_id)
    attempt = db_session.scalars(stmt).one()

    assert job.status == JobStatus.RUNNING
    assert job.finished_at is None
    assert job.execution_token == execution_token
    assert job.lease_expires_at == lease_expires_at
    assert job.progress_completed == 2
    assert job.result_summary is None

    assert attempt.status == JobAttemptStatus.RUNNING
    assert attempt.finished_at is None
    assert attempt.execution_token == execution_token


def test_complete_claimed_job_non_running_job_returns_false(
    db_session, claimed_job_factory
):
    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    _, _, claimed_job, _ = claimed_job_factory(
        repositories=[
            "FastApi/FastApi",
            "SQLAlchemy/SQLAlchemy",
        ],
        claim_time=claim_time,
        idempotency_key="test-key-123",
    )

    job_id = claimed_job.id
    execution_token = claimed_job.execution_token
    lease_expires_at = claimed_job.lease_expires_at

    assert execution_token is not None

    claimed_job.status = JobStatus.COMPLETED
    db_session.flush()
    db_session.commit()

    job_completed_at = datetime(2026, 10, 2, 12, 3, tzinfo=UTC)

    completed_job = complete_claimed_job(
        db=db_session,
        job_id=job_id,
        execution_token=execution_token,
        completed_at=job_completed_at,
    )

    assert completed_job is False

    db_session.expire_all()

    stmt = select(Job).where(Job.id == job_id)
    job = db_session.scalars(stmt).one()

    stmt = select(JobAttempt).where(JobAttempt.job_id == job_id)
    attempt = db_session.scalars(stmt).one()

    assert job.status == JobStatus.COMPLETED
    assert job.finished_at is None
    assert job.execution_token == execution_token
    assert job.lease_expires_at == lease_expires_at

    assert attempt.status == JobAttemptStatus.RUNNING
    assert attempt.finished_at is None
    assert attempt.execution_token == execution_token


def test_complete_claimed_job_missing_attempt_raises(db_session, claimed_job_factory):
    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    _, _, claimed_job, items = claimed_job_factory(
        repositories=[
            "FastApi/FastApi",
            "SQLAlchemy/SQLAlchemy",
        ],
        claim_time=claim_time,
        idempotency_key="test-key-123",
    )

    job_id = claimed_job.id
    execution_token = claimed_job.execution_token
    lease_expires_at = claimed_job.lease_expires_at

    assert execution_token is not None

    item_completed_at = datetime(2026, 10, 2, 12, 1, tzinfo=UTC)

    for item in items:
        assert item.status == RepositoryStatus.PENDING

        analysis_result = RepositoryAnalysisResult(
            owner=item.owner,
            repository=item.repository_name,
            stars=10,
            forks=5,
            open_issues=2,
        )

        result = save_item_result_and_update_progress(
            db=db_session,
            job_id=job_id,
            item_id=item.id,
            execution_token=execution_token,
            analysis_result=analysis_result,
            completed_at=item_completed_at,
        )

        assert result is True

    stmt = select(JobAttempt).where(JobAttempt.job_id == job_id)
    attempt = db_session.scalars(stmt).one()

    db_session.delete(attempt)
    db_session.commit()

    job_completed_at = datetime(2026, 10, 2, 12, 3, tzinfo=UTC)

    with pytest.raises(RuntimeError, match="Current JobAttempt is missing"):
        complete_claimed_job(
            db=db_session,
            job_id=job_id,
            execution_token=execution_token,
            completed_at=job_completed_at,
        )

    db_session.expire_all()

    stmt = select(Job).where(Job.id == job_id)
    job = db_session.scalars(stmt).one()

    assert job.status == JobStatus.RUNNING
    assert job.finished_at is None
    assert job.execution_token == execution_token
    assert job.lease_expires_at == lease_expires_at
    assert job.progress_completed == 2
    assert job.result_summary is None


def test_complete_claimed_job_inconsistent_attempt_raises(
    db_session, claimed_job_factory
):
    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    _, _, claimed_job, items = claimed_job_factory(
        repositories=[
            "FastApi/FastApi",
            "SQLAlchemy/SQLAlchemy",
        ],
        claim_time=claim_time,
        idempotency_key="test-key-123",
    )

    job_id = claimed_job.id
    execution_token = claimed_job.execution_token
    lease_expires_at = claimed_job.lease_expires_at

    assert execution_token is not None

    item_completed_at = datetime(2026, 10, 2, 12, 1, tzinfo=UTC)

    for item in items:
        analysis_result = RepositoryAnalysisResult(
            owner=item.owner,
            repository=item.repository_name,
            stars=10,
            forks=5,
            open_issues=2,
        )

        result = save_item_result_and_update_progress(
            db=db_session,
            job_id=job_id,
            item_id=item.id,
            execution_token=execution_token,
            analysis_result=analysis_result,
            completed_at=item_completed_at,
        )

        assert result is True

    stmt = select(JobAttempt).where(JobAttempt.job_id == job_id)
    attempt = db_session.scalars(stmt).one()

    attempt.status = JobAttemptStatus.FAILED
    db_session.flush()
    db_session.commit()

    job_completed_at = datetime(2026, 10, 2, 12, 3, tzinfo=UTC)

    with pytest.raises(RuntimeError, match="Current JobAttempt is not running"):
        complete_claimed_job(
            db=db_session,
            job_id=job_id,
            execution_token=execution_token,
            completed_at=job_completed_at,
        )

    db_session.expire_all()

    stmt = select(Job).where(Job.id == job_id)
    job = db_session.scalars(stmt).one()

    stmt = select(JobAttempt).where(JobAttempt.job_id == job_id)
    attempt = db_session.scalars(stmt).one()

    assert job.status == JobStatus.RUNNING
    assert job.finished_at is None
    assert job.execution_token == execution_token
    assert job.lease_expires_at == lease_expires_at
    assert job.progress_completed == 2
    assert job.result_summary is None

    assert attempt.status == JobAttemptStatus.FAILED


def test_complete_claimed_job_rolls_back_on_commit_failure(
    db_session, claimed_job_factory
):
    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    _, _, claimed_job, items = claimed_job_factory(
        repositories=[
            "FastApi/FastApi",
            "SQLAlchemy/SQLAlchemy",
        ],
        claim_time=claim_time,
        idempotency_key="test-key-123",
    )

    job_id = claimed_job.id
    execution_token = claimed_job.execution_token
    lease_expires_at = claimed_job.lease_expires_at

    assert execution_token is not None

    item_completed_at = datetime(2026, 10, 2, 12, 1, tzinfo=UTC)

    for item in items:
        analysis_result = RepositoryAnalysisResult(
            owner=item.owner,
            repository=item.repository_name,
            stars=10,
            forks=5,
            open_issues=2,
        )

        result = save_item_result_and_update_progress(
            db=db_session,
            job_id=job_id,
            item_id=item.id,
            execution_token=execution_token,
            analysis_result=analysis_result,
            completed_at=item_completed_at,
        )

        assert result is True

    job_completed_at = datetime(2026, 10, 2, 12, 3, tzinfo=UTC)

    with patch.object(
        Session,
        "commit",
        side_effect=SQLAlchemyError("commit failed"),
    ):
        with pytest.raises(SQLAlchemyError, match="commit failed"):
            complete_claimed_job(
                db=db_session,
                job_id=job_id,
                execution_token=execution_token,
                completed_at=job_completed_at,
            )

    db_session.expire_all()

    stmt = select(Job).where(Job.id == job_id)
    job = db_session.scalars(stmt).one()

    stmt = select(JobAttempt).where(
        JobAttempt.job_id == job_id, JobAttempt.attempt_number == job.attempt_count
    )
    attempt = db_session.scalars(stmt).one()

    assert job.status == JobStatus.RUNNING
    assert job.finished_at is None
    assert job.execution_token == execution_token
    assert job.lease_expires_at == lease_expires_at
    assert job.progress_completed == 2
    assert job.result_summary is None

    assert attempt.status == JobAttemptStatus.RUNNING
    assert attempt.finished_at is None
    assert attempt.execution_token == execution_token


def test_complete_claimed_job_rejects_naive_completion_time(db_session):
    job_id = uuid.uuid4()
    execution_token = uuid.uuid4()
    completed_at = datetime(2026, 10, 2, 12, 0)

    with pytest.raises(
        ValueError,
        match="completed_at must be timezone-aware",
    ):
        complete_claimed_job(
            db=db_session,
            job_id=job_id,
            execution_token=execution_token,
            completed_at=completed_at,
        )


def test_execute_claimed_job_persists_results_and_completes_job(
    db_session, claimed_job_factory
):
    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    _, _, claimed_job, items = claimed_job_factory(
        repositories=["FastApi/FastApi", "SQLAlchemy/SQLAlchemy"],
        claim_time=claim_time,
        idempotency_key="test-key-123",
    )

    job_id = claimed_job.id
    execution_token = claimed_job.execution_token

    assert execution_token is not None

    result = execute_claimed_job(
        db=db_session,
        job_id=job_id,
        execution_token=execution_token,
    )

    assert result is True

    db_session.expire_all()

    stmt = select(Job).where(Job.id == job_id)
    job = db_session.scalars(stmt).one()

    stmt = select(JobAttempt).where(
        JobAttempt.job_id == job_id, JobAttempt.attempt_number == job.attempt_count
    )
    attempt = db_session.scalars(stmt).one()

    stmt = select(RepositoryAnalysisItem).where(RepositoryAnalysisItem.job_id == job_id)
    analysis_items = db_session.scalars(stmt).all()

    assert len(analysis_items) == 2

    for item in analysis_items:
        assert item.status == RepositoryStatus.SUCCEEDED
        assert item.stars == 0
        assert item.forks == 0
        assert item.open_issues == 0
        assert item.completed_at is not None

    assert job.status == JobStatus.COMPLETED
    assert job.progress_completed == 2
    assert job.progress_total == 2
    assert job.result_summary == {
        "total": 2,
        "succeeded": 2,
        "failed": 0,
    }
    assert job.finished_at is not None
    assert job.execution_token is None
    assert job.lease_expires_at is None

    assert attempt.status == JobAttemptStatus.SUCCEEDED
    assert attempt.finished_at == job.finished_at
    assert attempt.execution_token == execution_token


def test_execute_claimed_job_skips_existing_terminal_items(
    db_session, claimed_job_factory
):
    claim_time = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)

    _, _, claimed_job, items = claimed_job_factory(
        repositories=[
            "FastApi/FastApi",
            "SQLAlchemy/SQLAlchemy",
            "Pallets/Flask",
        ],
        claim_time=claim_time,
        idempotency_key="test-key-123",
    )

    job_id = claimed_job.id
    execution_token = claimed_job.execution_token

    assert execution_token is not None

    items = sorted(items, key=lambda item: item.position)

    pending_item = items[0]
    succeeded_item = items[1]
    failed_item = items[2]

    succeeded_completed_at = datetime(2026, 10, 2, 12, 1, tzinfo=UTC)
    failed_completed_at = datetime(2026, 10, 2, 12, 2, tzinfo=UTC)

    succeeded_item.status = RepositoryStatus.SUCCEEDED
    succeeded_item.stars = 100
    succeeded_item.forks = 20
    succeeded_item.open_issues = 5
    succeeded_item.completed_at = succeeded_completed_at
    succeeded_item.attempt_count = 2

    failed_item.status = RepositoryStatus.FAILED
    failed_item.completed_at = failed_completed_at
    failed_item.attempt_count = 3
    failed_item.error_type = "AnalysisError"
    failed_item.error_message = "existing failure"

    succeeded_item_id = succeeded_item.id
    failed_item_id = failed_item.id

    db_session.flush()
    db_session.commit()

    analysis_result = RepositoryAnalysisResult(
        owner=pending_item.owner,
        repository=pending_item.repository_name,
        stars=0,
        forks=0,
        open_issues=0,
    )

    with patch(
        "app.services.job_execution_service.run_fake_repository_analysis",
        return_value=analysis_result,
    ) as analysis_mock:
        result = execute_claimed_job(
            db=db_session,
            job_id=job_id,
            execution_token=execution_token,
        )

    assert result is True

    analysis_mock.assert_called_once_with(
        owner=pending_item.owner,
        repository=pending_item.repository_name,
    )

    db_session.expire_all()

    succeeded_item = db_session.scalars(
        select(RepositoryAnalysisItem).where(
            RepositoryAnalysisItem.id == succeeded_item_id
        )
    ).one()

    failed_item = db_session.scalars(
        select(RepositoryAnalysisItem).where(
            RepositoryAnalysisItem.id == failed_item_id
        )
    ).one()

    assert succeeded_item.status == RepositoryStatus.SUCCEEDED
    assert succeeded_item.stars == 100
    assert succeeded_item.forks == 20
    assert succeeded_item.open_issues == 5
    assert succeeded_item.completed_at == succeeded_completed_at
    assert succeeded_item.attempt_count == 2

    assert failed_item.status == RepositoryStatus.FAILED
    assert failed_item.completed_at == failed_completed_at
    assert failed_item.attempt_count == 3
    assert failed_item.error_type == "AnalysisError"
    assert failed_item.error_message == "existing failure"


def test_execute_claimed_job_async_persists_results_and_completes_job(
    db_session, claimed_job_factory
):
    claim_time = datetime.now(UTC)

    _, _, claimed_job, _ = claimed_job_factory(
        repositories=["FastApi/FastApi", "SQLAlchemy/SQLAlchemy"],
        claim_time=claim_time,
        idempotency_key="async-execution-test",
    )

    job_id = claimed_job.id
    execution_token = claimed_job.execution_token

    assert execution_token is not None

    class FakeGitHubClient:
        @staticmethod
        async def get_repository(
            owner: str, repository: str
        ) -> RepositoryAnalysisResult:
            if repository == "fastapi":
                stars, forks, open_issues = 100, 50, 7
            elif repository == "sqlalchemy":
                stars, forks, open_issues = 200, 80, 12
            else:
                raise AssertionError(f"Unexpected repository: {repository}")

            return RepositoryAnalysisResult(
                owner=owner,
                repository=repository,
                stars=stars,
                forks=forks,
                open_issues=open_issues,
            )

    result = asyncio.run(
        execute_claimed_job_async(
            db=db_session,
            job_id=job_id,
            execution_token=execution_token,
            github_client=FakeGitHubClient(),
        )
    )

    assert result is True

    db_session.expire_all()

    job = db_session.scalars(select(Job).where(Job.id == job_id)).one()

    assert job.status == JobStatus.COMPLETED
    assert job.progress_total == 2
    assert job.progress_completed == 2
    assert job.result_summary == {
        "total": 2,
        "succeeded": 2,
        "failed": 0,
    }
    assert job.finished_at is not None
    assert job.execution_token is None
    assert job.lease_expires_at is None

    items = db_session.scalars(
        select(RepositoryAnalysisItem).where(RepositoryAnalysisItem.job_id == job_id)
    ).all()

    assert len(items) == 2

    expected_metrics = {
        "fastapi": (100, 50, 7),
        "sqlalchemy": (200, 80, 12),
    }

    for item in items:
        assert item.status == RepositoryStatus.SUCCEEDED
        assert item.completed_at is not None

        assert (
            item.stars,
            item.forks,
            item.open_issues,
        ) == expected_metrics[item.repository_name]

    attempt = db_session.scalars(
        select(JobAttempt).where(
            JobAttempt.job_id == job_id,
            JobAttempt.attempt_number == job.attempt_count,
        )
    ).one()

    assert attempt.status == JobAttemptStatus.SUCCEEDED
    assert attempt.finished_at is not None
    assert attempt.execution_token == execution_token


def test_execute_claimed_job_async_preserves_terminal_items(
    db_session, claimed_job_factory
):
    _, _, job, items = claimed_job_factory(
        repositories=["owner/pending", "owner/succeeded", "owner/failed"],
        claim_time=datetime.now(UTC),
        idempotency_key="async-terminal-items",
    )

    job_id = job.id
    token = job.execution_token
    assert token is not None

    items_by_name = {item.repository_name: item for item in items}
    succeeded = items_by_name["succeeded"]
    failed = items_by_name["failed"]

    completed_at = datetime.now(UTC)

    succeeded.status = RepositoryStatus.SUCCEEDED
    succeeded.stars = 100
    succeeded.forks = 20
    succeeded.open_issues = 5
    succeeded.attempt_count = 2
    succeeded.completed_at = completed_at

    failed.status = RepositoryStatus.FAILED
    failed.attempt_count = 3
    failed.completed_at = completed_at
    failed.error_type = "AnalysisError"
    failed.error_message = "existing failure"

    db_session.commit()

    def snapshot(item):
        return (
            item.status,
            item.stars,
            item.forks,
            item.open_issues,
            item.error_type,
            item.error_message,
            item.completed_at,
            item.attempt_count,
        )

    original_terminal_items = {item.id: snapshot(item) for item in [succeeded, failed]}

    class FakeProvider:
        def __init__(self):
            self.calls = []

        async def get_repository(
            self, owner: str, repository: str
        ) -> RepositoryAnalysisResult:
            self.calls.append((owner, repository))
            return RepositoryAnalysisResult(owner, repository, 10, 5, 2)

    provider = FakeProvider()

    result = asyncio.run(
        execute_claimed_job_async(
            db=db_session,
            job_id=job_id,
            execution_token=token,
            github_client=provider,
        )
    )

    assert result is True
    assert provider.calls == [("owner", "pending")]

    db_session.expire_all()

    persisted_items = db_session.scalars(
        select(RepositoryAnalysisItem).where(RepositoryAnalysisItem.job_id == job_id)
    ).all()

    for item in persisted_items:
        if item.id in original_terminal_items:
            assert snapshot(item) == original_terminal_items[item.id]

    persisted_job = db_session.get(Job, job_id)
    assert persisted_job is not None
    assert persisted_job.status == JobStatus.COMPLETED
    assert persisted_job.progress_completed == 3
    assert persisted_job.result_summary == {
        "total": 3,
        "succeeded": 2,
        "failed": 1,
    }
