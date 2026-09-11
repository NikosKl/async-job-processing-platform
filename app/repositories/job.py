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
    job = db.scalars(stmt).one_or_none()
    return job
