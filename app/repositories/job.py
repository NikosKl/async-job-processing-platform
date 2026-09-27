import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import JobStatus, JobType
from app.models import Job


def get_job_by_idempotency_key(
    db: Session, user_id: uuid.UUID, idempotency_key: str
) -> Job | None:

    stmt = select(Job).where(
        Job.user_id == user_id, Job.idempotency_key == idempotency_key
    )
    return db.scalars(stmt).one_or_none()


def get_job_by_id_and_user_id(
    db: Session, job_id: uuid.UUID, user_id: uuid.UUID
) -> Job | None:

    stmt = select(Job).where(Job.id == job_id, Job.user_id == user_id)
    return db.scalars(stmt).one_or_none()


def list_jobs_by_user_id(
    db: Session,
    user_id: uuid.UUID,
    limit: int | None = None,
    offset: int | None = None,
    job_status: JobStatus | None = None,
    job_type: JobType | None = None,
) -> list[Job]:

    stmt = select(Job).where(Job.user_id == user_id)

    if job_status is not None:
        stmt = stmt.where(Job.status == job_status)
    if job_type is not None:
        stmt = stmt.where(Job.type == job_type)

    stmt = stmt.order_by(Job.created_at.desc(), Job.id.desc())

    if limit is not None:
        stmt = stmt.limit(limit)
    if offset is not None:
        stmt = stmt.offset(offset)

    jobs = db.scalars(stmt).all()
    return list(jobs)
