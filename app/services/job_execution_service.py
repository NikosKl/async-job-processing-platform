import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domain.enums import JobAttemptStatus, JobStatus, RepositoryStatus
from app.models import Job, JobAttempt, RepositoryAnalysisItem
from app.repositories.job import increment_job_progress
from app.repositories.repository_analysis_item import persist_successful_item_result


@dataclass
class RepositoryAnalysisResult:
    owner: str
    repository: str
    stars: int
    forks: int
    open_issues: int


def run_fake_repository_analysis(
    owner: str, repository: str
) -> RepositoryAnalysisResult:

    return RepositoryAnalysisResult(
        owner=owner,
        repository=repository,
        stars=0,
        forks=0,
        open_issues=0,
    )


def save_item_result_and_update_progress(
    db: Session,
    job_id: uuid.UUID,
    item_id: uuid.UUID,
    execution_token: uuid.UUID,
    analysis_result: RepositoryAnalysisResult,
    completed_at: datetime,
) -> bool:

    if completed_at.tzinfo is None or completed_at.utcoffset() is None:
        raise ValueError("completed_at must be timezone-aware")

    try:
        result = persist_successful_item_result(
            db=db,
            job_id=job_id,
            item_id=item_id,
            execution_token=execution_token,
            stars=analysis_result.stars,
            forks=analysis_result.forks,
            open_issues=analysis_result.open_issues,
            completed_at=completed_at,
        )

        if not result:
            db.rollback()
            return False

        increment_job_progress(db=db, job_id=job_id)
        db.commit()
        return True
    except SQLAlchemyError:
        db.rollback()
        raise


def complete_claimed_job(
    db: Session,
    job_id: uuid.UUID,
    execution_token: uuid.UUID,
    completed_at: datetime,
) -> bool:

    if completed_at.tzinfo is None or completed_at.utcoffset() is None:
        raise ValueError("completed_at must be timezone-aware")

    try:
        stmt = (
            select(Job)
            .where(Job.id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        job = db.scalars(stmt).one_or_none()

        if job is None:
            db.rollback()
            return False
        if job.status != JobStatus.RUNNING:
            db.rollback()
            return False
        if job.execution_token != execution_token:
            db.rollback()
            return False

        stmt = (
            select(RepositoryAnalysisItem)
            .where(RepositoryAnalysisItem.job_id == job_id)
            .execution_options(populate_existing=True)
        )
        items = db.scalars(stmt).all()

        if not items:
            db.rollback()
            return False

        succeeded = 0
        failed = 0

        for item in items:
            if item.status == RepositoryStatus.PENDING:
                db.rollback()
                return False

            if item.status == RepositoryStatus.SUCCEEDED:
                succeeded += 1
            elif item.status == RepositoryStatus.FAILED:
                failed += 1

        total = len(items)

        stmt = (
            select(JobAttempt)
            .where(
                JobAttempt.job_id == job_id,
                JobAttempt.attempt_number == job.attempt_count,
            )
            .execution_options(populate_existing=True)
        )

        attempt = db.scalars(stmt).one_or_none()

        if attempt is None:
            db.rollback()
            raise RuntimeError("Current JobAttempt is missing")

        if attempt.status != JobAttemptStatus.RUNNING:
            db.rollback()
            raise RuntimeError("Current JobAttempt is not running")

        if attempt.execution_token != execution_token:
            db.rollback()
            raise RuntimeError(
                "Current JobAttempt has inconsistent execution ownership"
            )

        job.status = JobStatus.COMPLETED
        job.finished_at = completed_at
        job.progress_completed = total
        job.result_summary = {"total": total, "succeeded": succeeded, "failed": failed}
        job.execution_token = None
        job.lease_expires_at = None

        attempt.status = JobAttemptStatus.SUCCEEDED
        attempt.finished_at = completed_at

        db.flush()
        db.commit()
        return True

    except SQLAlchemyError:
        db.rollback()
        raise
