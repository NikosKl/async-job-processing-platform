import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.domain.enums import JobStatus, JobType, OutboxEventType, RepositoryStatus
from app.domain.exceptions import IdempotencyConflictError
from app.models import Job, OutboxMessage, RepositoryAnalysisItem
from app.repositories.job import get_job_by_idempotency_key
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
