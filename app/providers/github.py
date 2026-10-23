import httpx

from app.domain.repository_analysis import RepositoryAnalysisResult


class GitHubClient:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def get_repository(
        self, owner: str, repository: str
    ) -> RepositoryAnalysisResult:

        response = await self._client.get(
            f"https://api.github.com/repos/{owner}/{repository}",
            timeout=10.0,
            follow_redirects=False,
        )

        response.raise_for_status()

        data = response.json()

        return RepositoryAnalysisResult(
            owner=data["owner"]["login"],
            repository=data["name"],
            stars=data["stargazers_count"],
            forks=data["forks_count"],
            open_issues=data["open_issues_count"],
        )
