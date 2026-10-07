from datetime import UTC, datetime

from app.db.session import DBSession
from app.services.outbox_publisher import publish_outbox_batch
from app.worker.celery_app import celery_app

OUTBOX_BATCH_SIZE = 100


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
