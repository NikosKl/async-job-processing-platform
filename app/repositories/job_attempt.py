from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import JobAttempt


def list_job_attempts_by_job_id(db: Session, job_id: UUID) -> list[JobAttempt]:
    stmt = (
        select(JobAttempt)
        .where(JobAttempt.job_id == job_id)
        .order_by(JobAttempt.attempt_number.asc())
    )

    job_attempts = db.scalars(stmt).all()
    return list(job_attempts)
