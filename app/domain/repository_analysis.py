from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID


@dataclass
class RepositoryAnalysisResult:
    owner: str
    repository: str
    stars: int
    forks: int
    open_issues: int
    language: str | None = None
    archived: bool | None = None
    last_push_at: datetime | None = None


@dataclass(frozen=True)
class RepositoryAnalysisItemInput:
    item_id: UUID
    owner: str
    repository: str


def classify_repository_activity(
    last_push_at: datetime | None, reference_time: datetime
) -> str | None:
    """
    Classify repository activity based on time since the last push.

    HIGH: Up to and including 30 days.
    MEDIUM: More than 30 days, through 180 days.
    LOW: More than 180 days.
    None: No last push timestamp.
    Future timestamps are treated as zero age.
    """

    if reference_time.tzinfo is None or reference_time.utcoffset() is None:
        raise ValueError

    if last_push_at is None:
        return None
    if last_push_at.tzinfo is None or last_push_at.utcoffset() is None:
        raise ValueError

    age = reference_time.astimezone(UTC) - last_push_at.astimezone(UTC)

    if age < timedelta(0):
        age = timedelta(0)

    if age <= timedelta(days=30):
        return "HIGH"
    elif age <= timedelta(days=180):
        return "MEDIUM"
    else:
        return "LOW"
