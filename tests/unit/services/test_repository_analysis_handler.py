import asyncio
from contextlib import aclosing
from unittest.mock import AsyncMock, call
from uuid import uuid4

import pytest

from app.domain.exceptions import (
    GitHubRateLimitError,
    GitHubUnavailableError,
    RepositoryAnalysisFailedError,
    RepositoryUnavailableError,
)
from app.domain.repository_analysis import (
    RepositoryAnalysisFailure,
    RepositoryAnalysisItemInput,
    RepositoryAnalysisResult,
    RepositoryAnalysisSuccess,
)
from app.services.repository_analysis_handler import (
    analyze_repositories,
    analyze_repositories_with_retries,
    analyze_repository_with_retries,
)


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


def test_analyze_repository_with_retries_immediate_success():
    item = RepositoryAnalysisItemInput(
        item_id=uuid4(),
        owner="fastapi",
        repository="fastapi",
    )

    expected_result = RepositoryAnalysisResult(
        owner="fastapi", repository="fastapi", stars=100, forks=20, open_issues=5
    )

    class FakeProvider:
        def __init__(self):
            self.calls = []

        async def get_repository(self, owner, repository):
            self.calls.append((owner, repository))
            return expected_result

    fake_provider = FakeProvider()
    sleep_mock = AsyncMock()

    async def run_test():
        result, attempt_count = await analyze_repository_with_retries(
            provider=fake_provider,
            repository=item,
            semaphore=asyncio.Semaphore(1),
            sleep=sleep_mock,
        )

        assert result == expected_result
        assert attempt_count == 1
        assert fake_provider.calls == [(item.owner, item.repository)]
        sleep_mock.assert_not_awaited()

    asyncio.run(run_test())


def test_analyze_repository_with_retries_succeeds_on_second_attempt():
    item = RepositoryAnalysisItemInput(
        item_id=uuid4(),
        owner="fastapi",
        repository="fastapi",
    )

    expected_result = RepositoryAnalysisResult(
        owner="fastapi", repository="fastapi", stars=100, forks=20, open_issues=5
    )

    class FakeProvider:
        def __init__(self):
            self.calls = []

        async def get_repository(self, owner, repository):
            self.calls.append((owner, repository))
            if len(self.calls) == 1:
                raise GitHubUnavailableError("GitHub is temporarily unavailable")
            return expected_result

    fake_provider = FakeProvider()
    sleep_mock = AsyncMock()

    async def run_test():
        result, attempt_count = await analyze_repository_with_retries(
            provider=fake_provider,
            repository=item,
            semaphore=asyncio.Semaphore(1),
            sleep=sleep_mock,
        )

        assert result == expected_result
        assert attempt_count == 2
        assert len(fake_provider.calls) == 2
        sleep_mock.assert_awaited_once_with(1)

    asyncio.run(run_test())


def test_analyze_repository_with_retries_succeeds_on_third_attempt():
    item = RepositoryAnalysisItemInput(
        item_id=uuid4(),
        owner="fastapi",
        repository="fastapi",
    )

    expected_result = RepositoryAnalysisResult(
        owner="fastapi", repository="fastapi", stars=100, forks=20, open_issues=5
    )

    class FakeProvider:
        def __init__(self):
            self.calls = []

        async def get_repository(self, owner, repository):
            self.calls.append((owner, repository))
            if len(self.calls) == 1 or len(self.calls) == 2:
                raise GitHubUnavailableError("GitHub is temporarily unavailable")
            return expected_result

    fake_provider = FakeProvider()
    sleep_mock = AsyncMock()

    async def run_test():
        result, attempt_count = await analyze_repository_with_retries(
            provider=fake_provider,
            repository=item,
            semaphore=asyncio.Semaphore(1),
            sleep=sleep_mock,
        )

        assert result == expected_result
        assert attempt_count == 3
        assert len(fake_provider.calls) == 3
        assert sleep_mock.await_args_list == [call(1), call(2)]

    asyncio.run(run_test())


def test_analyze_repository_with_retries_exhausts_three_attempts():
    item = RepositoryAnalysisItemInput(
        item_id=uuid4(),
        owner="fastapi",
        repository="fastapi",
    )

    class FakeProvider:
        def __init__(self):
            self.calls = []

        async def get_repository(self, owner, repository):
            self.calls.append((owner, repository))
            raise GitHubUnavailableError("GitHub is temporarily unavailable")

    fake_provider = FakeProvider()
    sleep_mock = AsyncMock()

    async def run_test():
        with pytest.raises(RepositoryAnalysisFailedError) as exc_info:
            _, attempt_count = await analyze_repository_with_retries(
                provider=fake_provider,
                repository=item,
                semaphore=asyncio.Semaphore(1),
                sleep=sleep_mock,
            )

        assert len(fake_provider.calls) == 3
        assert sleep_mock.await_args_list == [call(1), call(2)]
        assert exc_info.value.attempt_count == 3
        assert isinstance(exc_info.value.__cause__, GitHubUnavailableError)

    asyncio.run(run_test())


def test_analyze_repository_with_retries_stops_on_permanent_error():
    item = RepositoryAnalysisItemInput(
        item_id=uuid4(),
        owner="fastapi",
        repository="fastapi",
    )

    class FakeProvider:
        def __init__(self):
            self.calls = []

        async def get_repository(self, owner, repository):
            self.calls.append((owner, repository))
            raise RepositoryUnavailableError("Repository not found")

    fake_provider = FakeProvider()
    sleep_mock = AsyncMock()

    async def run_test():
        with pytest.raises(RepositoryAnalysisFailedError) as exc_info:
            await analyze_repository_with_retries(
                provider=fake_provider,
                repository=item,
                semaphore=asyncio.Semaphore(1),
                sleep=sleep_mock,
            )

        assert exc_info.value.attempt_count == 1
        assert isinstance(exc_info.value.__cause__, RepositoryUnavailableError)
        assert len(fake_provider.calls) == 1
        sleep_mock.assert_not_awaited()

    asyncio.run(run_test())


def test_analyze_repository_with_retries_propagates_unclassified_error():
    item = RepositoryAnalysisItemInput(
        item_id=uuid4(),
        owner="fastapi",
        repository="fastapi",
    )

    class FakeProvider:
        def __init__(self):
            self.calls = []

        async def get_repository(self, owner, repository):
            self.calls.append((owner, repository))
            raise RuntimeError("Unexpected provider error")

    fake_provider = FakeProvider()
    sleep_mock = AsyncMock()

    async def run_test():
        with pytest.raises(RuntimeError, match="Unexpected provider error"):
            await analyze_repository_with_retries(
                provider=fake_provider,
                repository=item,
                semaphore=asyncio.Semaphore(1),
                sleep=sleep_mock,
            )

        assert len(fake_provider.calls) == 1
        sleep_mock.assert_not_awaited()

    asyncio.run(run_test())


def test_analyze_repository_with_retries_propagates_cancellation():
    item = RepositoryAnalysisItemInput(
        item_id=uuid4(),
        owner="fastapi",
        repository="fastapi",
    )

    class FakeProvider:
        def __init__(self):
            self.calls = []

        async def get_repository(self, owner, repository):
            self.calls.append((owner, repository))
            raise asyncio.CancelledError()

    fake_provider = FakeProvider()
    sleep_mock = AsyncMock()

    async def run_test():
        with pytest.raises(asyncio.CancelledError):
            await analyze_repository_with_retries(
                provider=fake_provider,
                repository=item,
                semaphore=asyncio.Semaphore(1),
                sleep=sleep_mock,
            )

        assert len(fake_provider.calls) == 1
        sleep_mock.assert_not_awaited()

    asyncio.run(run_test())


@pytest.mark.parametrize(
    ("first_error", "expected_delay"),
    [
        pytest.param(
            GitHubUnavailableError("GitHub temporarily unavailable"),
            1,
            id="ordinary-backoff",
        ),
        pytest.param(
            GitHubRateLimitError(retry_after_seconds=60.0),
            60.0,
            id="rate-limit",
        ),
    ],
)
def test_analyze_repository_with_retries_releases_semaphore_during_backoff(
    first_error, expected_delay
):
    item = RepositoryAnalysisItemInput(
        item_id=uuid4(),
        owner="fastapi",
        repository="fastapi",
    )

    expected_result = RepositoryAnalysisResult(
        owner="fastapi",
        repository="fastapi",
        stars=100,
        forks=20,
        open_issues=5,
    )

    semaphore = asyncio.Semaphore(1)

    class FakeProvider:
        def __init__(self):
            self.calls = []

        async def get_repository(self, owner, repository):
            self.calls.append((owner, repository))

            if len(self.calls) == 1:
                raise first_error

            return expected_result

    fake_provider = FakeProvider()
    sleep_calls = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

        async with asyncio.timeout(1):
            async with semaphore:
                pass

    async def run_test():
        result, attempt_count = await analyze_repository_with_retries(
            provider=fake_provider,
            repository=item,
            semaphore=semaphore,
            sleep=fake_sleep,
        )

        assert result == expected_result
        assert attempt_count == 2

    asyncio.run(run_test())

    assert len(fake_provider.calls) == 2
    assert sleep_calls == [expected_delay]


def test_analyze_repositories_with_retries_immediate_success():
    item = RepositoryAnalysisItemInput(
        item_id=uuid4(),
        owner="fastapi",
        repository="fastapi",
    )

    expected_result = RepositoryAnalysisResult(
        owner="fastapi", repository="fastapi", stars=100, forks=20, open_issues=5
    )

    class FakeProvider:
        def __init__(self):
            self.calls = []

        async def get_repository(self, owner, repository):
            self.calls.append((owner, repository))
            return expected_result

    fake_provider = FakeProvider()
    sleep_mock = AsyncMock()

    async def run_test():
        outcomes = []

        async for item_id, outcome in analyze_repositories_with_retries(
            provider=fake_provider,
            items=[item],
            sleep=sleep_mock,
        ):
            outcomes.append((item_id, outcome))

        assert len(outcomes) == 1

        returned_id, returned_outcome = outcomes[0]
        assert returned_id == item.item_id
        assert isinstance(returned_outcome, RepositoryAnalysisSuccess)
        assert returned_outcome.result == expected_result
        assert returned_outcome.attempt_count == 1

    asyncio.run(run_test())

    assert fake_provider.calls == [("fastapi", "fastapi")]
    sleep_mock.assert_not_awaited()


def test_analyze_repositories_with_retries_succeeds_after_retry():
    item = RepositoryAnalysisItemInput(
        item_id=uuid4(),
        owner="fastapi",
        repository="fastapi",
    )

    expected_result = RepositoryAnalysisResult(
        owner="fastapi", repository="fastapi", stars=100, forks=20, open_issues=5
    )

    class FakeProvider:
        def __init__(self):
            self.calls = []

        async def get_repository(self, owner, repository):
            self.calls.append((owner, repository))
            if len(self.calls) == 1:
                raise GitHubUnavailableError("GitHub is temporarily unavailable")
            return expected_result

    fake_provider = FakeProvider()
    sleep_mock = AsyncMock()

    async def run_test():
        outcomes = []

        async for item_id, outcome in analyze_repositories_with_retries(
            provider=fake_provider,
            items=[item],
            sleep=sleep_mock,
        ):
            outcomes.append((item_id, outcome))

        assert len(outcomes) == 1
        returned_id, returned_outcome = outcomes[0]
        assert returned_id == item.item_id
        assert isinstance(returned_outcome, RepositoryAnalysisSuccess)
        assert returned_outcome.result == expected_result
        assert returned_outcome.attempt_count == 2

    asyncio.run(run_test())

    assert len(fake_provider.calls) == 2
    sleep_mock.assert_awaited_once_with(1)


def test_analyze_repositories_with_retries_yields_permanent_failure():
    item = RepositoryAnalysisItemInput(
        item_id=uuid4(),
        owner="fastapi",
        repository="fastapi",
    )

    class FakeProvider:
        def __init__(self):
            self.calls = []

        async def get_repository(self, owner, repository):
            self.calls.append((owner, repository))
            raise RepositoryUnavailableError("Repository not found")

    fake_provider = FakeProvider()
    sleep_mock = AsyncMock()

    async def run_test():
        outcomes = []

        async for item_id, outcome in analyze_repositories_with_retries(
            provider=fake_provider,
            items=[item],
            sleep=sleep_mock,
        ):
            outcomes.append((item_id, outcome))

        assert len(outcomes) == 1
        returned_id, returned_outcome = outcomes[0]
        assert returned_id == item.item_id
        assert isinstance(returned_outcome, RepositoryAnalysisFailure)
        assert returned_outcome.error_type == "RepositoryUnavailableError"
        assert returned_outcome.error_message == "Repository not found"
        assert returned_outcome.attempt_count == 1

    asyncio.run(run_test())

    assert len(fake_provider.calls) == 1
    sleep_mock.assert_not_awaited()


def test_analyze_repositories_with_retries_yields_failure_after_three_attempts():
    item = RepositoryAnalysisItemInput(
        item_id=uuid4(),
        owner="fastapi",
        repository="fastapi",
    )

    class FakeProvider:
        def __init__(self):
            self.calls = []

        async def get_repository(self, owner, repository):
            self.calls.append((owner, repository))
            raise GitHubUnavailableError("GitHub is temporarily unavailable")

    fake_provider = FakeProvider()
    sleep_mock = AsyncMock()

    async def run_test():
        outcomes = []

        async for item_id, outcome in analyze_repositories_with_retries(
            provider=fake_provider,
            items=[item],
            sleep=sleep_mock,
        ):
            outcomes.append((item_id, outcome))

        assert len(outcomes) == 1
        returned_id, returned_outcome = outcomes[0]
        assert returned_id == item.item_id
        assert isinstance(returned_outcome, RepositoryAnalysisFailure)
        assert returned_outcome.error_type == "GitHubUnavailableError"
        assert returned_outcome.error_message == "GitHub is temporarily unavailable"
        assert returned_outcome.attempt_count == 3

    asyncio.run(run_test())

    assert len(fake_provider.calls) == 3
    assert sleep_mock.await_args_list == [call(1), call(2)]


def test_analyze_repositories_with_retries_yields_all_mixed_outcomes():
    items = [
        RepositoryAnalysisItemInput(uuid4(), "fastapi", "fastapi"),
        RepositoryAnalysisItemInput(uuid4(), "example", "missing"),
        RepositoryAnalysisItemInput(uuid4(), "pallets", "flask"),
    ]

    class FakeProvider:
        def __init__(self):
            self.calls = []

        async def get_repository(self, owner, repository):
            self.calls.append((owner, repository))

            if repository == "missing":
                raise RepositoryUnavailableError("Repository not found")

            if repository == "flask":
                flask_calls = self.calls.count((owner, repository))

                if flask_calls == 1:
                    raise GitHubUnavailableError("GitHub is temporarily unavailable")

            return RepositoryAnalysisResult(
                owner=owner,
                repository=repository,
                stars=100,
                forks=20,
                open_issues=5,
            )

    fake_provider = FakeProvider()
    sleep_mock = AsyncMock()

    async def run_test():
        outcomes = []

        async for item_id, outcome in analyze_repositories_with_retries(
            provider=fake_provider,
            items=items,
            sleep=sleep_mock,
        ):
            outcomes.append((item_id, outcome))

        assert len(outcomes) == 3

        results_by_id = dict(outcomes)

        fastapi_outcome = results_by_id[items[0].item_id]
        assert isinstance(fastapi_outcome, RepositoryAnalysisSuccess)
        assert fastapi_outcome.attempt_count == 1
        assert fastapi_outcome.result.repository == "fastapi"

        missing_outcome = results_by_id[items[1].item_id]
        assert isinstance(missing_outcome, RepositoryAnalysisFailure)
        assert missing_outcome.attempt_count == 1
        assert missing_outcome.error_type == "RepositoryUnavailableError"
        assert missing_outcome.error_message == "Repository not found"

        flask_outcome = results_by_id[items[2].item_id]
        assert isinstance(flask_outcome, RepositoryAnalysisSuccess)
        assert flask_outcome.attempt_count == 2
        assert flask_outcome.result.repository == "flask"

    asyncio.run(run_test())

    assert fake_provider.calls.count(("fastapi", "fastapi")) == 1
    assert fake_provider.calls.count(("example", "missing")) == 1
    assert fake_provider.calls.count(("pallets", "flask")) == 2

    sleep_mock.assert_awaited_once_with(1)


def test_analyze_repositories_with_retries_preserves_completion_order():
    items = [
        RepositoryAnalysisItemInput(uuid4(), "fastapi", "fastapi"),
        RepositoryAnalysisItemInput(uuid4(), "django", "django"),
        RepositoryAnalysisItemInput(uuid4(), "pallets", "flask"),
    ]

    async def run_test():
        started = {item.repository: asyncio.Event() for item in items}
        release = {item.repository: asyncio.Event() for item in items}

        class FakeProvider:
            async def get_repository(self, owner, repository):
                started[repository].set()
                await release[repository].wait()

                return RepositoryAnalysisResult(
                    owner=owner,
                    repository=repository,
                    stars=100,
                    forks=20,
                    open_issues=5,
                )

        sleep_mock = AsyncMock()

        generator = analyze_repositories_with_retries(
            provider=FakeProvider(),
            items=items,
            sleep=sleep_mock,
        )

        first_task = asyncio.create_task(anext(generator))

        await asyncio.wait_for(
            asyncio.gather(*(event.wait() for event in started.values())),
            timeout=2,
        )

        release["flask"].set()
        first = await asyncio.wait_for(first_task, timeout=2)

        release["django"].set()
        second = await asyncio.wait_for(anext(generator), timeout=2)

        release["fastapi"].set()
        third = await asyncio.wait_for(anext(generator), timeout=2)

        outcomes = [first, second, third]

        assert [item_id for item_id, _ in outcomes] == [
            items[2].item_id,
            items[1].item_id,
            items[0].item_id,
        ]

        for _, outcome in outcomes:
            assert isinstance(outcome, RepositoryAnalysisSuccess)
            assert outcome.attempt_count == 1

        sleep_mock.assert_not_awaited()

        with pytest.raises(StopAsyncIteration):
            await anext(generator)

    asyncio.run(run_test())


def test_analyze_repositories_with_retries_cancels_tasks_on_unexpected_error():
    async def run_test():
        blocked_started = asyncio.Event()
        blocked_cancelled = asyncio.Event()
        never_release = asyncio.Event()

        class FakeProvider:
            @staticmethod
            async def get_repository(owner, repository):
                if repository == "error":
                    await blocked_started.wait()
                    raise RuntimeError("provider failed")

                blocked_started.set()

                try:
                    await never_release.wait()
                except asyncio.CancelledError:
                    blocked_cancelled.set()
                    raise

                return RepositoryAnalysisResult(
                    owner=owner,
                    repository=repository,
                    stars=100,
                    forks=20,
                    open_issues=5,
                )

        items = [
            RepositoryAnalysisItemInput(uuid4(), "owner", "error"),
            RepositoryAnalysisItemInput(uuid4(), "owner", "blocked"),
        ]

        sleep_mock = AsyncMock()

        with pytest.raises(RuntimeError, match="provider failed"):
            async for _ in analyze_repositories_with_retries(
                provider=FakeProvider(),
                items=items,
                sleep=sleep_mock,
            ):
                pass

        assert blocked_cancelled.is_set()
        sleep_mock.assert_not_awaited()

    asyncio.run(asyncio.wait_for(run_test(), timeout=10))


def test_analyze_repositories_with_retries_cancels_tasks_on_early_close():
    async def run_test():
        blocked_started = asyncio.Event()
        blocked_cancelled = asyncio.Event()
        never_release = asyncio.Event()

        class FakeProvider:
            @staticmethod
            async def get_repository(owner, repository):
                if repository == "blocked":
                    blocked_started.set()

                    try:
                        await never_release.wait()
                    except asyncio.CancelledError:
                        blocked_cancelled.set()
                        raise

                await blocked_started.wait()

                return RepositoryAnalysisResult(
                    owner=owner,
                    repository=repository,
                    stars=100,
                    forks=20,
                    open_issues=5,
                )

        items = [
            RepositoryAnalysisItemInput(uuid4(), "owner", "success"),
            RepositoryAnalysisItemInput(uuid4(), "owner", "blocked"),
        ]

        sleep_mock = AsyncMock()

        generator = analyze_repositories_with_retries(
            provider=FakeProvider(),
            items=items,
            sleep=sleep_mock,
        )

        first_item_id, first_outcome = await anext(generator)

        assert first_item_id == items[0].item_id
        assert isinstance(first_outcome, RepositoryAnalysisSuccess)
        assert first_outcome.attempt_count == 1

        await generator.aclose()

        assert blocked_cancelled.is_set()
        sleep_mock.assert_not_awaited()

    asyncio.run(asyncio.wait_for(run_test(), timeout=10))


def test_analyze_repositories_with_retries_respects_concurrency_limit():
    items = [
        RepositoryAnalysisItemInput(uuid4(), "owner", f"repo-{i}") for i in range(15)
    ]

    async def run_test():
        first_ten_started = asyncio.Event()
        release_calls = asyncio.Event()

        retry_repositories = {f"repo-{i}" for i in range(5)}

        class FakeProvider:
            def __init__(self):
                self.active_calls = 0
                self.max_active_calls = 0
                self.calls_by_repo = {}

            async def get_repository(self, owner, repository):
                self.active_calls += 1
                self.max_active_calls = max(self.max_active_calls, self.active_calls)

                self.calls_by_repo[repository] = (
                    self.calls_by_repo.get(repository, 0) + 1
                )

                attempt = self.calls_by_repo[repository]

                if self.active_calls == 10:
                    first_ten_started.set()

                try:
                    await release_calls.wait()

                    if repository in retry_repositories and attempt == 1:
                        raise GitHubUnavailableError(
                            "GitHub is temporarily unavailable"
                        )

                    return RepositoryAnalysisResult(
                        owner=owner,
                        repository=repository,
                        stars=100,
                        forks=20,
                        open_issues=5,
                    )
                finally:
                    self.active_calls -= 1

        fake_provider = FakeProvider()
        sleep_calls = []

        async def fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)
            await asyncio.sleep(0)

        outcomes = []

        async def consume():
            async for item_id, outcome in analyze_repositories_with_retries(
                provider=fake_provider,
                items=items,
                sleep=fake_sleep,
            ):
                outcomes.append((item_id, outcome))

        consumer = asyncio.create_task(consume())

        try:
            await asyncio.wait_for(first_ten_started.wait(), timeout=5)

            assert fake_provider.active_calls == 10
            assert fake_provider.max_active_calls == 10

            release_calls.set()

            await asyncio.wait_for(consumer, timeout=5)
        finally:
            release_calls.set()

            if not consumer.done():
                consumer.cancel()

            await asyncio.gather(consumer, return_exceptions=True)

        assert fake_provider.max_active_calls <= 10
        assert fake_provider.active_calls == 0

        assert len(outcomes) == 15
        assert {item_id for item_id, _ in outcomes} == {item.item_id for item in items}

        for item_id, outcome in outcomes:
            assert isinstance(outcome, RepositoryAnalysisSuccess)

            item = next(item for item in items if item.item_id == item_id)

            if item.repository in retry_repositories:
                assert outcome.attempt_count == 2
                assert fake_provider.calls_by_repo[item.repository] == 2
            else:
                assert outcome.attempt_count == 1
                assert fake_provider.calls_by_repo[item.repository] == 1

        assert sleep_calls == [1] * 5

    asyncio.run(asyncio.wait_for(run_test(), timeout=10))


def test_rate_limit_error_retries_with_requested_delay():
    item = RepositoryAnalysisItemInput(
        item_id=uuid4(),
        owner="fastapi",
        repository="fastapi",
    )

    expected_result = RepositoryAnalysisResult(
        owner="fastapi",
        repository="fastapi",
        stars=100,
        forks=20,
        open_issues=5,
    )

    class FakeProvider:
        def __init__(self):
            self.calls = []

        async def get_repository(self, owner, repository):
            self.calls.append((owner, repository))

            if len(self.calls) == 1:
                raise GitHubRateLimitError(retry_after_seconds=30.0)

            return expected_result

    fake_provider = FakeProvider()
    sleep_mock = AsyncMock()

    async def run_test():
        result, attempt_count = await analyze_repository_with_retries(
            provider=fake_provider,
            repository=item,
            semaphore=asyncio.Semaphore(10),
            sleep=sleep_mock,
        )

        assert result == expected_result
        assert attempt_count == 2

    asyncio.run(run_test())

    assert fake_provider.calls == [
        ("fastapi", "fastapi"),
        ("fastapi", "fastapi"),
    ]

    sleep_mock.assert_awaited_once_with(30.0)


def test_analyze_repository_with_retries_exhausts_rate_limit_attempts():
    item = RepositoryAnalysisItemInput(
        item_id=uuid4(),
        owner="fastapi",
        repository="fastapi",
    )

    errors = [
        GitHubRateLimitError(retry_after_seconds=10.0),
        GitHubRateLimitError(retry_after_seconds=20.0),
        GitHubRateLimitError(retry_after_seconds=30.0),
    ]

    class FakeProvider:
        def __init__(self):
            self.calls = []

        async def get_repository(
            self, owner: str, repository: str
        ) -> RepositoryAnalysisResult:
            self.calls.append((owner, repository))
            raise errors[len(self.calls) - 1]

    provider = FakeProvider()
    sleep_mock = AsyncMock()

    async def run_test():
        with pytest.raises(RepositoryAnalysisFailedError) as exc_info:
            await analyze_repository_with_retries(
                provider=provider,
                repository=item,
                semaphore=asyncio.Semaphore(1),
                sleep=sleep_mock,
            )

        assert provider.calls == [("fastapi", "fastapi")] * 3
        assert sleep_mock.await_args_list == [call(10.0), call(20.0)]
        assert exc_info.value.attempt_count == 3
        assert exc_info.value.__cause__ is errors[2]

    asyncio.run(run_test())


def test_analyze_repository_with_retries_accepts_zero_rate_limit_delay():
    item = RepositoryAnalysisItemInput(
        item_id=uuid4(),
        owner="fastapi",
        repository="fastapi",
    )

    expected_result = RepositoryAnalysisResult(
        owner="fastapi",
        repository="fastapi",
        stars=100,
        forks=20,
        open_issues=5,
    )

    class FakeProvider:
        def __init__(self):
            self.calls = []

        async def get_repository(self, owner, repository):
            self.calls.append((owner, repository))

            if len(self.calls) == 1:
                raise GitHubRateLimitError(retry_after_seconds=0.0)

            return expected_result

    provider = FakeProvider()
    sleep_mock = AsyncMock()

    async def run_test():
        result, attempt_count = await analyze_repository_with_retries(
            provider=provider,
            repository=item,
            semaphore=asyncio.Semaphore(1),
            sleep=sleep_mock,
        )

        assert result == expected_result
        assert attempt_count == 2

    asyncio.run(run_test())

    assert provider.calls == [("fastapi", "fastapi")] * 2
    sleep_mock.assert_awaited_once_with(0.0)
