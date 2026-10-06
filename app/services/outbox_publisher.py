from datetime import UTC, datetime

from kombu.exceptions import OperationalError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.repositories.outbox_message import (
    get_due_outbox_messages,
    mark_outbox_message_failed,
    mark_outbox_message_published,
)
from app.worker.publication import publish_process_job


def publish_outbox_batch(db: Session, cutoff: datetime, limit: int) -> None:
    try:
        outbox_messages = get_due_outbox_messages(db, cutoff, limit)

        for message in outbox_messages:
            try:
                publish_process_job(message.job_id)
            except OperationalError as exc:
                mark_outbox_message_failed(
                    db=db, outbox_message=message, error=str(exc)
                )
                continue

            published_at = datetime.now(UTC)

            mark_outbox_message_published(
                db=db, outbox_message=message, published_at=published_at
            )

        db.commit()

    except SQLAlchemyError:
        db.rollback()
        raise
