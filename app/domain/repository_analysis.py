from dataclasses import dataclass


@dataclass
class RepositoryAnalysisResult:
    owner: str
    repository: str
    stars: int
    forks: int
    open_issues: int
