from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    UUID,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy import Enum as EnumType
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domain.enums import JobAttemptStatus

if TYPE_CHECKING:
    from app.models.job import Job


class JobAttempt(Base):
    __tablename__ = "job_attempts"
    __table_args__ = (
        UniqueConstraint(
            "job_id", "attempt_number", name="unique_job_id_attempt_number"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id"), index=True, nullable=False
    )

    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[JobAttemptStatus] = mapped_column(
        EnumType(JobAttemptStatus, name="job_attempt_status"),
        nullable=False,
        index=True,
    )

    execution_token: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    worker_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    retryable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(255), nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    job: Mapped[Job] = relationship(back_populates="job_attempts")
