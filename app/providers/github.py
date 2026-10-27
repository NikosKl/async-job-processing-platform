import json
from typing import Annotated

import httpx
from pydantic import BaseModel, Field, StringConstraints, ValidationError

from app.domain.exceptions import (
    GitHubUnavailableError,
    InvalidRepositoryResponseError,
    RepositoryUnavailableError,
)
from app.domain.repository_analysis import RepositoryAnalysisResult

Identifier = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=1,
        strip_whitespace=True,
    ),
]


class GitHubOwnerResponse(BaseModel):
    login: Identifier


class GitHubRepositoryResponse(BaseModel):
    owner: GitHubOwnerResponse
    name: Identifier
    stargazers_count: int = Field(strict=True, ge=0)
    forks_count: int = Field(strict=True, ge=0)
    open_issues_count: int = Field(strict=True, ge=0)


class GitHubClient:
    def __init__(self, client: httpx.AsyncClient, token: str | None = None) -> None:
        self._client = client
        self._token = token

    async def get_repository(
        self, owner: str, repository: str
    ) -> RepositoryAnalysisResult:

        url = f"https://api.github.com/repos/{owner}/{repository}"

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2026-03-10",
            "User-Agent": "async-job-processing-platform",
        }

        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        try:
            response = await self._client.get(
                url=url,
                headers=headers,
                timeout=10.0,
                follow_redirects=False,
            )
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            raise GitHubUnavailableError() from exc

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise RepositoryUnavailableError() from exc
            if exc.response.is_server_error:
                raise GitHubUnavailableError() from exc
            raise

        try:
            data = response.json()
            validated_data = GitHubRepositoryResponse.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise InvalidRepositoryResponseError(
                "Invalid GitHub repository response"
            ) from exc

        return RepositoryAnalysisResult(
            owner=validated_data.owner.login,
            repository=validated_data.name,
            stars=validated_data.stargazers_count,
            forks=validated_data.forks_count,
            open_issues=validated_data.open_issues_count,
        )
