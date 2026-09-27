import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RepositoryAnalysisItem


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
