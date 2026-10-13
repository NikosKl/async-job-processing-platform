from dataclasses import dataclass


@dataclass
class RepositoryAnalysisResult:
    owner: str
    repository: str
    stars: int
    forks: int
    open_issues: int


def run_fake_repository_analysis(
    owner: str, repository: str
) -> RepositoryAnalysisResult:

    return RepositoryAnalysisResult(
        owner=owner,
        repository=repository,
        stars=0,
        forks=0,
        open_issues=0,
    )
