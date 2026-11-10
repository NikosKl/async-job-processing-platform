from dataclasses import dataclass
from datetime import datetime
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
