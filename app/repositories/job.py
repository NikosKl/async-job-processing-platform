import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

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
