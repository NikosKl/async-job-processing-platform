from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    UUID,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as EnumType
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.domain.enums import JobStatus, JobType

if TYPE_CHECKING:
    from app.models.job_attempt import JobAttempt
    from app.models.outbox_message import OutboxMessage
    from app.models.repository_analysis_item import RepositoryAnalysisItem
    from app.models.user import User


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "idempotency_key", name="unique_job_user_id_idempotency_key"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )

    type: Mapped[JobType] = mapped_column(
        EnumType(JobType, name="job_type"), nullable=False
    )
    status: Mapped[JobStatus] = mapped_column(
        EnumType(JobStatus, name="job_status"), nullable=False, index=True
    )

    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    options: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    progress_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    execution_token: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    last_error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship(back_populates="jobs")

    job_attempts: Mapped[list[JobAttempt]] = relationship(back_populates="job")

    outbox_messages: Mapped[list[OutboxMessage]] = relationship(back_populates="job")

    repository_analysis_items: Mapped[list[RepositoryAnalysisItem]] = relationship(
        back_populates="job"
    )
