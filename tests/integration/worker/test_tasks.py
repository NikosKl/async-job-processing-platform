from unittest.mock import patch

from sqlalchemy import select

from app.domain.enums import JobAttemptStatus, JobStatus, RepositoryStatus
from app.models import Job, JobAttempt, RepositoryAnalysisItem
from app.repositories.user import create_user
from app.schemas.jobs import CreateJobRequest, RepositoryBatchAnalysisInput
from app.services.job_request import hash_job_request
from app.services.job_service import create_job
from app.worker.tasks import process_job


def test_process_job_completes_queued_job(test_session_factory):
    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=[
                "FastApi/FastApi",
                "SQLAlchemy/SQLAlchemy",
            ]
        ),
    )

    with test_session_factory() as db:
        user = create_user(
            db=db,
            email="user@example.com",
            hashed_password="hashed_password",
        )

        job = create_job(
            db=db,
            user_id=user.id,
            request=request,
            idempotency_key="test-key-123",
            request_hash=hash_job_request(request),
        )

        job_id = job.id
        db.commit()

    with test_session_factory() as db:
        job = db.get(Job, job_id)

        assert job is not None
        assert job.status == JobStatus.QUEUED
        assert job.attempt_count == 0

    with patch("app.worker.tasks.DBSession", new=test_session_factory):
        process_job.run(str(job_id))

    with test_session_factory() as db:
        stmt = select(Job).where(Job.id == job_id)
        job = db.scalars(stmt).one()

        stmt = select(JobAttempt).where(JobAttempt.job_id == job_id)
        attempts = db.scalars(stmt).all()

        stmt = select(RepositoryAnalysisItem).where(
            RepositoryAnalysisItem.job_id == job_id
        )
        analysis_items = db.scalars(stmt).all()

        assert len(analysis_items) == 2

        for item in analysis_items:
            assert item.status == RepositoryStatus.SUCCEEDED
            assert item.stars == 0
            assert item.forks == 0
            assert item.open_issues == 0
            assert item.completed_at is not None

        assert job.status == JobStatus.COMPLETED
        assert job.attempt_count == 1
        assert job.progress_completed == 2
        assert job.progress_total == 2
        assert job.result_summary == {
            "total": 2,
            "succeeded": 2,
            "failed": 0,
        }
        assert job.started_at is not None
        assert job.finished_at is not None
        assert job.started_at <= job.finished_at
        assert job.execution_token is None
        assert job.lease_expires_at is None

        assert len(attempts) == 1

        attempt = attempts[0]

        assert attempt.attempt_number == 1
        assert attempt.status == JobAttemptStatus.SUCCEEDED
        assert attempt.finished_at == job.finished_at


def test_process_job_does_not_reexecute_completed_job(test_session_factory):
    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=[
                "FastApi/FastApi",
                "SQLAlchemy/SQLAlchemy",
            ]
        ),
    )

    with test_session_factory() as db:
        user = create_user(
            db=db,
            email="user@example.com",
            hashed_password="hashed_password",
        )

        job = create_job(
            db=db,
            user_id=user.id,
            request=request,
            idempotency_key="test-key-123",
            request_hash=hash_job_request(request),
        )

        job_id = job.id
        db.commit()

    with patch("app.worker.tasks.DBSession", new=test_session_factory):
        process_job.run(str(job_id))

    with test_session_factory() as db:
        stmt = select(Job).where(Job.id == job_id)
        job = db.scalars(stmt).one()

        stmt = select(JobAttempt).where(JobAttempt.job_id == job_id)
        attempts = db.scalars(stmt).all()

        stmt = select(RepositoryAnalysisItem).where(
            RepositoryAnalysisItem.job_id == job_id
        )
        items = db.scalars(stmt).all()

        assert job.status == JobStatus.COMPLETED
        assert job.attempt_count == 1
        assert len(attempts) == 1
        assert len(items) == 2

        original_progress = job.progress_completed
        original_summary = job.result_summary
        original_finished_at = job.finished_at
        original_attempt_id = attempts[0].id

        original_items = [
            (
                item.id,
                item.status,
                item.stars,
                item.forks,
                item.open_issues,
                item.completed_at,
            )
            for item in items
        ]

    with patch("app.worker.tasks.DBSession", new=test_session_factory):
        process_job.run(str(job_id))

    with test_session_factory() as db:
        stmt = select(Job).where(Job.id == job_id)
        job = db.scalars(stmt).one()

        stmt = select(JobAttempt).where(JobAttempt.job_id == job_id)
        attempts = db.scalars(stmt).all()

        stmt = select(RepositoryAnalysisItem).where(
            RepositoryAnalysisItem.job_id == job_id
        )
        items = db.scalars(stmt).all()

        assert job.status == JobStatus.COMPLETED
        assert job.attempt_count == 1
        assert job.progress_completed == original_progress
        assert job.result_summary == original_summary
        assert job.finished_at == original_finished_at

        assert len(attempts) == 1
        assert attempts[0].id == original_attempt_id

        assert [
            (
                item.id,
                item.status,
                item.stars,
                item.forks,
                item.open_issues,
                item.completed_at,
            )
            for item in items
        ] == original_items
