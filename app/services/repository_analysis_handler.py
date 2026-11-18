import asyncio
from asyncio import Semaphore
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Protocol
from uuid import UUID

from app.domain.exceptions import RepositoryAnalysisFailedError
from app.domain.repository_analysis import (
    RepositoryAnalysisItemInput,
    RepositoryAnalysisResult,
)
from app.domain.repository_errors import classify_repository_error


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


async def analyze_repository_with_retries(
    provider: RepositoryProvider,
    repository: RepositoryAnalysisItemInput,
    semaphore: Semaphore,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> tuple[RepositoryAnalysisResult, int]:
    attempt_count = 0

    for _ in range(3):
        attempt_count += 1

        try:
            async with semaphore:
                result = await provider.get_repository(
                    repository.owner, repository.repository
                )

            return result, attempt_count

        except Exception as error:
            classification = classify_repository_error(error)

            if classification is None:
                raise
            if classification == "PERMANENT":
                raise RepositoryAnalysisFailedError(attempt_count) from error
            if classification == "RETRYABLE":
                if attempt_count == 3:
                    raise RepositoryAnalysisFailedError(attempt_count) from error
                await sleep(attempt_count)
    raise RuntimeError("Retry loop ended without a result or failure")
