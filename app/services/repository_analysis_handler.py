import asyncio
from collections.abc import AsyncGenerator
from typing import Protocol
from uuid import UUID

from app.domain.repository_analysis import (
    RepositoryAnalysisItemInput,
    RepositoryAnalysisResult,
)


class RepositoryProvider(Protocol):
    async def get_repository(
        self, owner: str, repository: str
    ) -> RepositoryAnalysisResult:
        pass


async def analyze_repositories(
    github_client: RepositoryProvider, items: list[RepositoryAnalysisItemInput]
) -> AsyncGenerator[tuple[UUID, RepositoryAnalysisResult]]:

    semaphore = asyncio.Semaphore(10)

    async def analyze_item(
        repo_input: RepositoryAnalysisItemInput,
    ) -> tuple[UUID, RepositoryAnalysisResult]:
        async with semaphore:
            repo_result = await github_client.get_repository(
                repo_input.owner, repo_input.repository
            )

        return repo_input.item_id, repo_result

    tasks = []

    try:
        for item in items:
            tasks.append(asyncio.create_task(analyze_item(item)))

        for completed_task in asyncio.as_completed(tasks):
            item_id, result = await completed_task
            yield item_id, result
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
