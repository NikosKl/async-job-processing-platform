import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.domain.enums import JobStatus, JobType, OutboxEventType, RepositoryStatus
from app.models import Job, OutboxMessage, RepositoryAnalysisItem
from app.schemas.jobs import CreateJobRequest
from app.services.job_request import hash_job_request


def create_job(
    db: Session,
    user_id: uuid.UUID,
    request: CreateJobRequest,
    idempotency_key: str,
) -> Job:

    request_hash = hash_job_request(request)
    progress_total = len(request.input.repositories)
    now = datetime.now(UTC)

    try:
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

        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return job
