import asyncio
from contextlib import aclosing
from uuid import uuid4

import pytest

from app.domain.repository_analysis import (
    RepositoryAnalysisItemInput,
    RepositoryAnalysisResult,
)
from app.services.repository_analysis_handler import analyze_repositories


def test_analyze_repositories_calls_provider_with_correct_identifiers():
    class FakeGitHubClient:
        def __init__(self):
            self.calls = []

        async def get_repository(
            self, owner: str, repository: str
        ) -> RepositoryAnalysisResult:
            self.calls.append((owner, repository))

            return RepositoryAnalysisResult(
                owner=owner,
                repository=repository,
                stars=100,
                forks=20,
                open_issues=5,
            )

    fake_client = FakeGitHubClient()

    items = [
        RepositoryAnalysisItemInput(
            item_id=uuid4(),
            owner="fastapi",
            repository="fastapi",
        ),
        RepositoryAnalysisItemInput(
            item_id=uuid4(),
            owner="django",
            repository="django",
        ),
    ]

    async def run_test():
        async for _, _ in analyze_repositories(fake_client, items):
            pass

    asyncio.run(run_test())

    assert len(fake_client.calls) == 2
    assert set(fake_client.calls) == {
        ("fastapi", "fastapi"),
        ("django", "django"),
    }


def test_analyze_repositories_preserves_item_ids():
    class FakeGitHubClient:
        def __init__(self):
            self.calls = []

        async def get_repository(
            self, owner: str, repository: str
        ) -> RepositoryAnalysisResult:
            self.calls.append((owner, repository))

            return RepositoryAnalysisResult(
                owner=owner,
                repository=repository,
                stars=100,
                forks=20,
                open_issues=5,
            )

    fake_client = FakeGitHubClient()

    items = [
        RepositoryAnalysisItemInput(
            item_id=uuid4(),
            owner="fastapi",
            repository="fastapi",
        ),
        RepositoryAnalysisItemInput(
            item_id=uuid4(),
            owner="django",
            repository="django",
        ),
    ]

    results = []

    async def run_test():
        async for item_id, result in analyze_repositories(fake_client, items):
            results.append((item_id, result))

    asyncio.run(run_test())

    assert len(results) == 2
    results_by_repo = {result.repository: item_id for item_id, result in results}

    assert results_by_repo == {
        "fastapi": items[0].item_id,
        "django": items[1].item_id,
    }


def test_analyze_repositories_yields_results_in_completion_order():

    async def run_test():
        started_fastapi = asyncio.Event()
        started_django = asyncio.Event()

        release_fastapi = asyncio.Event()
        release_django = asyncio.Event()

        first_result_received = asyncio.Event()

        class FakeGitHubClient:
            @staticmethod
            async def get_repository(
                owner: str, repository: str
            ) -> RepositoryAnalysisResult:

                if repository == "fastapi":
                    started_fastapi.set()
                    await release_fastapi.wait()

                elif repository == "django":
                    started_django.set()
                    await release_django.wait()

                return RepositoryAnalysisResult(
                    owner=owner,
                    repository=repository,
                    stars=100,
                    forks=20,
                    open_issues=5,
                )

        fake_client = FakeGitHubClient()

        items = [
            RepositoryAnalysisItemInput(
                item_id=uuid4(),
                owner="fastapi",
                repository="fastapi",
            ),
            RepositoryAnalysisItemInput(
                item_id=uuid4(),
                owner="django",
                repository="django",
            ),
        ]

        results = []

        async def collect_results():
            async for item_id, result in analyze_repositories(fake_client, items):
                results.append((item_id, result))

                if len(results) == 1:
                    first_result_received.set()

        consumer_task = asyncio.create_task(collect_results())

        await started_fastapi.wait()
        await started_django.wait()

        release_django.set()
        await first_result_received.wait()

        assert results[0][0] == items[1].item_id
        assert results[0][1].repository == "django"

        release_fastapi.set()
        await consumer_task

        assert results[1][0] == items[0].item_id
        assert results[1][1].repository == "fastapi"

    asyncio.run(asyncio.wait_for(run_test(), timeout=10))


def test_analyze_repositories_limits_concurrent_requests():
    async def run_test():
        ten_started = asyncio.Event()
        release = asyncio.Event()

        active = 0
        peak_active = 0
        started = 0

        class FakeGitHubClient:
            @staticmethod
            async def get_repository(
                owner: str, repository: str
            ) -> RepositoryAnalysisResult:
                nonlocal active, peak_active, started

                active += 1
                started += 1
                peak_active = max(peak_active, active)

                if started == 10:
                    ten_started.set()

                try:
                    await release.wait()
                finally:
                    active -= 1

                return RepositoryAnalysisResult(owner, repository, 100, 20, 5)

        items = [
            RepositoryAnalysisItemInput(uuid4(), "owner", f"repo-{index}")
            for index in range(15)
        ]

        async def collect_results():
            return [
                result
                async for result in analyze_repositories(FakeGitHubClient(), items)
            ]

        consumer = asyncio.create_task(collect_results())

        await ten_started.wait()

        assert active == 10
        assert started == 10

        release.set()
        results = await consumer

        assert len(results) == 15
        assert peak_active == 10
        assert active == 0

    asyncio.run(asyncio.wait_for(run_test(), timeout=10))


def test_analyze_repositories_handles_empty_input():
    class FakeGitHubClient:
        @staticmethod
        async def get_repository(
            owner: str, repository: str
        ) -> RepositoryAnalysisResult:
            pytest.fail("Provider should not be called")

    async def run_test():
        results = [item async for item in analyze_repositories(FakeGitHubClient(), [])]

        assert results == []

    asyncio.run(run_test())


def test_analyze_repositories_cancels_remaining_tasks_on_error():
    async def run_test():
        blocked_started = asyncio.Event()
        blocked_cancelled = asyncio.Event()
        never_release = asyncio.Event()

        class FakeGitHubClient:
            @staticmethod
            async def get_repository(
                owner: str, repository: str
            ) -> RepositoryAnalysisResult:
                if repository == "error":
                    await blocked_started.wait()
                    raise RuntimeError("provider failed")

                blocked_started.set()

                try:
                    await never_release.wait()
                except asyncio.CancelledError:
                    blocked_cancelled.set()
                    raise

                return RepositoryAnalysisResult(owner, repository, 100, 20, 5)

        items = [
            RepositoryAnalysisItemInput(uuid4(), "owner", "error"),
            RepositoryAnalysisItemInput(uuid4(), "owner", "blocked"),
        ]

        with pytest.raises(RuntimeError, match="provider failed"):
            async for _ in analyze_repositories(FakeGitHubClient(), items):
                pass

        assert blocked_cancelled.is_set()

    asyncio.run(asyncio.wait_for(run_test(), timeout=10))


def test_analyze_repositories_cleans_up_on_early_close():
    async def run_test():
        blocked_started = asyncio.Event()
        blocked_cancelled = asyncio.Event()
        never_release = asyncio.Event()

        class FakeGitHubClient:
            @staticmethod
            async def get_repository(
                owner: str, repository: str
            ) -> RepositoryAnalysisResult:
                if repository == "blocked":
                    blocked_started.set()

                    try:
                        await never_release.wait()
                    except asyncio.CancelledError:
                        blocked_cancelled.set()
                        raise
                else:
                    await blocked_started.wait()

                return RepositoryAnalysisResult(owner, repository, 100, 20, 5)

        items = [
            RepositoryAnalysisItemInput(uuid4(), "owner", "fastapi"),
            RepositoryAnalysisItemInput(uuid4(), "owner", "blocked"),
        ]

        async with aclosing(analyze_repositories(FakeGitHubClient(), items)) as results:
            async for _, result in results:
                assert result.repository == "fastapi"
                break

        assert blocked_cancelled.is_set()

    asyncio.run(asyncio.wait_for(run_test(), timeout=10))
