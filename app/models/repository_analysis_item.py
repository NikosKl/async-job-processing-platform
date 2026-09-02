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
from app.domain.enums import RepositoryStatus

if TYPE_CHECKING:
    from app.models.job import Job


class RepositoryAnalysisItem(Base):
    __tablename__ = "repository_analysis_items"
    __table_args__ = (
        UniqueConstraint("job_id", "position", name="unique_job_id_position"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id"), index=True, nullable=False
    )

    position: Mapped[int] = mapped_column(Integer, nullable=False)

    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    repository_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[RepositoryStatus] = mapped_column(
        EnumType(RepositoryStatus, name="repository_status"), nullable=False, index=True
    )

    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    stars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    forks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    open_issues: Mapped[int | None] = mapped_column(Integer, nullable=True)
    primary_language: Mapped[str | None] = mapped_column(String(255), nullable=True)
    archived: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    license: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_push_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    activity_classification: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    error_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(255), nullable=True)

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    job: Mapped[Job] = relationship(back_populates="repository_analysis_items")
