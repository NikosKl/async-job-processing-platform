from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.db.session import DBSession
from app.services.job_execution_service import execute_claimed_job
from app.services.job_service import claim_job_for_execution
from app.services.outbox_publisher import publish_outbox_batch
from app.worker.celery_app import celery_app

OUTBOX_BATCH_SIZE = 100
LEASE_DURATION = timedelta(minutes=10)


@celery_app.task(name="run_outbox_publisher_batch")
def run_outbox_publisher_batch():

    db = DBSession()

    cutoff = datetime.now(UTC)

    try:
        publish_outbox_batch(
            db=db,
            cutoff=cutoff,
            limit=OUTBOX_BATCH_SIZE,
        )
    finally:
        db.close()


@celery_app.task(name="process_job")
def process_job(job_id: str) -> None:

    parsed_job_id = UUID(job_id)
    db = DBSession()

    claim_time = datetime.now(UTC)

    try:
        claim = claim_job_for_execution(
            db=db,
            job_id=parsed_job_id,
            claim_time=claim_time,
            lease_duration=LEASE_DURATION,
        )

        if claim is None:
            return

        execution_token = claim.execution_token

        if execution_token is None:
            raise RuntimeError("claimed job is missing execution token")

        execute_claimed_job(
            db=db,
            job_id=parsed_job_id,
            execution_token=execution_token,
        )
    finally:
        db.close()
