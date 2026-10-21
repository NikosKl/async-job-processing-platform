import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.domain.enums import (
    JobAttemptStatus,
    JobStatus,
    JobType,
    OutboxEventType,
    RepositoryStatus,
)
from app.domain.exceptions import IdempotencyConflictError, JobNotFoundError
from app.models import Job, JobAttempt, OutboxMessage, RepositoryAnalysisItem
from app.repositories.job import (
    claim_job,
    get_job_by_id_and_user_id,
    get_job_by_idempotency_key,
)
from app.repositories.job_attempt import list_job_attempts_by_job_id
from app.repositories.repository_analysis_item import (
    list_repository_analysis_items_by_job_id,
)
from app.schemas.jobs.requests import CreateJobRequest
from app.services.job_request import hash_job_request


def create_job(
    db: Session,
    user_id: uuid.UUID,
    request: CreateJobRequest,
    idempotency_key: str,
    request_hash: str,
) -> Job:

    progress_total = len(request.input.repositories)
    now = datetime.now(UTC)

    job = Job(
        user_id=user_id,
        type=JobType(request.type.upper()),
        status=JobStatus.QUEUED,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        progress_total=progress_total,
        queued_at=now,
    )

    db.add(job)
    db.flush()

    for position, repository in enumerate(request.input.repositories):
        normalized_repository = repository.lower()
        owner, repository_name = normalized_repository.split("/")

        repository_item = RepositoryAnalysisItem(
            job_id=job.id,
            position=position,
            owner=owner,
            repository_name=repository_name,
            status=RepositoryStatus.PENDING,
        )

        db.add(repository_item)

    outbox_message = OutboxMessage(
        job_id=job.id,
        event_type=OutboxEventType.PROCESS_JOB,
        available_at=now,
    )

    db.add(outbox_message)
    return job


def submit_job(
    db: Session, user_id: uuid.UUID, request: CreateJobRequest, idempotency_key: str
) -> Job:

    request_hash = hash_job_request(request)

    try:
        job = get_job_by_idempotency_key(db, user_id, idempotency_key)
        if job is None:
            new_job = create_job(db, user_id, request, idempotency_key, request_hash)
            db.commit()
        elif job.request_hash == request_hash:
            return job
        else:
            raise IdempotencyConflictError()
    except IntegrityError as err:
        db.rollback()
        existing_job = get_job_by_idempotency_key(db, user_id, idempotency_key)

        if existing_job is None:
            raise

        if existing_job.request_hash == request_hash:
            return existing_job

        raise IdempotencyConflictError() from err
    except SQLAlchemyError:
        db.rollback()
        raise
    return new_job


def get_owned_job(db: Session, job_id: uuid.UUID, user_id: uuid.UUID) -> Job:
    job = get_job_by_id_and_user_id(db, job_id, user_id)
    if job is None:
        raise JobNotFoundError()
    return job


def get_owned_job_results(
    db: Session, job_id: uuid.UUID, user_id: uuid.UUID
) -> list[RepositoryAnalysisItem]:

    job = get_owned_job(db, job_id, user_id)

    items = list_repository_analysis_items_by_job_id(db, job.id)

    return items


def get_owned_job_attempts(
    db: Session,
    job_id: uuid.UUID,
    user_id: uuid.UUID,
) -> list[JobAttempt]:

    job = get_owned_job(db, job_id, user_id)

    attempts = list_job_attempts_by_job_id(db, job.id)

    return attempts


def claim_job_for_execution(
    db: Session,
    job_id: uuid.UUID,
    claim_time: datetime,
    lease_duration: timedelta,
) -> Job | None:

    if claim_time.tzinfo is None or claim_time.utcoffset() is None:
        raise ValueError("claim_time must be timezone-aware")

    if lease_duration.total_seconds() <= 0:
        raise ValueError("lease_duration must be positive")

    execution_token = uuid.uuid4()
    lease_expires_at = claim_time + lease_duration

    try:
        claimed_job = claim_job(
            db=db,
            job_id=job_id,
            claim_time=claim_time,
            execution_token=execution_token,
            lease_expires_at=lease_expires_at,
        )

        if claimed_job is None:
            db.rollback()
            return None

        job_attempt = JobAttempt(
            job_id=claimed_job.id,
            attempt_number=claimed_job.attempt_count,
            status=JobAttemptStatus.RUNNING,
            execution_token=claimed_job.execution_token,
            started_at=claim_time,
        )

        db.add(job_attempt)
        db.flush()
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    return claimed_job
