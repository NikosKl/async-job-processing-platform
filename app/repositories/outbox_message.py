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
