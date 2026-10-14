import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domain.enums import RepositoryStatus
from app.models import Job, RepositoryAnalysisItem
from app.services.job_execution_service import (
    RepositoryAnalysisResult,
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
