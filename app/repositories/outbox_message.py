from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import OutboxMessage


def get_due_outbox_messages(
    db: Session, cutoff: datetime, limit: int
) -> list[OutboxMessage]:

    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("cutoff must be timezone-aware")

    if limit <= 0:
        raise ValueError("limit must be positive")

    stmt = (
        select(OutboxMessage)
        .where(
            OutboxMessage.published_at.is_(None), OutboxMessage.available_at <= cutoff
        )
        .order_by(OutboxMessage.available_at, OutboxMessage.id)
        .limit(limit)
    )

    outbox_messages = db.scalars(stmt).all()

    return list(outbox_messages)


def mark_outbox_message_published(
    db: Session, outbox_message: OutboxMessage, published_at: datetime
) -> None:

    if published_at.tzinfo is None or published_at.utcoffset() is None:
        raise ValueError("published_at must be timezone-aware")

    outbox_message.published_at = published_at
    outbox_message.publish_attempts += 1
    outbox_message.last_error = None

    db.flush()


def mark_outbox_message_failed(
    db: Session, outbox_message: OutboxMessage, error: str
) -> None:

    outbox_message.publish_attempts += 1
    outbox_message.last_error = error[:255]

    db.flush()
