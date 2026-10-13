import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import JobStatus, RepositoryStatus
from app.models import Job, RepositoryAnalysisItem


def list_repository_analysis_items_by_job_id(
    db: Session,
    job_id: uuid.UUID,
) -> list[RepositoryAnalysisItem]:

    stmt = (
        select(RepositoryAnalysisItem)
        .where(RepositoryAnalysisItem.job_id == job_id)
        .order_by(RepositoryAnalysisItem.position)
    )

    job_items = db.scalars(stmt).all()
    return list(job_items)


def persist_successful_item_result(
    db: Session,
    job_id: uuid.UUID,
    item_id: uuid.UUID,
    execution_token: uuid.UUID,
    stars: int,
    forks: int,
    open_issues: int,
    completed_at: datetime,
) -> bool:

    if completed_at.tzinfo is None or completed_at.utcoffset() is None:
        raise ValueError("completed_at must be timezone-aware")

    stmt = (
        select(Job)
        .where(Job.id == job_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    job = db.scalar(stmt)

    if job is None:
        return False
    if job.status != JobStatus.RUNNING or job.execution_token != execution_token:
        return False

    stmt = select(RepositoryAnalysisItem).where(
        RepositoryAnalysisItem.id == item_id,
        RepositoryAnalysisItem.job_id == job_id,
        RepositoryAnalysisItem.status == RepositoryStatus.PENDING,
    )
    item = db.scalar(stmt)

    if item is None:
        return False

    item.stars = stars
    item.forks = forks
    item.open_issues = open_issues
    item.status = RepositoryStatus.SUCCEEDED
    item.completed_at = completed_at
    item.attempt_count += 1
    item.error_type = None
    item.error_message = None

    db.flush()

    return True
