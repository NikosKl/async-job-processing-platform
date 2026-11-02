from dataclasses import dataclass
from uuid import UUID


@dataclass
class RepositoryAnalysisResult:
    owner: str
    repository: str
    stars: int
    forks: int
    open_issues: int


@dataclass(frozen=True)
class RepositoryAnalysisItemInput:
    item_id: UUID
    owner: str
    repository: str
