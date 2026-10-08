import uuid
from datetime import datetime

from sqlalchemy import and_, or_, select, update
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


def claim_job(
    db: Session,
    job_id: uuid.UUID,
    claim_time: datetime,
    execution_token: uuid.UUID,
    lease_expires_at: datetime,
) -> Job | None:

    if claim_time.tzinfo is None or claim_time.utcoffset() is None:
        raise ValueError("claim_time must be timezone-aware")

    if lease_expires_at.tzinfo is None or lease_expires_at.utcoffset() is None:
        raise ValueError("lease_expires_at must be timezone-aware")

    if lease_expires_at <= claim_time:
        raise ValueError("lease_expires_at must be later than claim_time")

    stmt = (
        update(Job)
        .where(
            Job.id == job_id,
            or_(
                Job.status == JobStatus.QUEUED,
                and_(
                    Job.status == JobStatus.RETRYING,
                    Job.next_attempt_at <= claim_time,
                ),
            ),
        )
        .values(
            status=JobStatus.RUNNING,
            attempt_count=Job.attempt_count + 1,
            execution_token=execution_token,
            lease_expires_at=lease_expires_at,
            next_attempt_at=None,
        )
        .returning(Job)
    )

    return db.scalars(stmt).one_or_none()
