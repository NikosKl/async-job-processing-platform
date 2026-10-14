import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

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
