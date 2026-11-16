import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.domain.repository_analysis import RepositoryAnalysisResult
from app.services.job_execution_service import execute_claimed_job_async


def test_async_execution_saves_out_of_order_results_to_correct_items():
    fastapi_id = uuid.uuid4()
    django_id = uuid.uuid4()

    fastapi_item = MagicMock()
    fastapi_item.id = fastapi_id
    fastapi_item.owner = "fastapi"
    fastapi_item.repository_name = "fastapi"

    django_item = MagicMock()
    django_item.id = django_id
    django_item.owner = "django"
    django_item.repository_name = "django"

    db = MagicMock()
    db.scalars.return_value.all.return_value = [fastapi_item, django_item]

    fastapi_result = RepositoryAnalysisResult(
        owner=fastapi_item.owner,
        repository=fastapi_item.repository_name,
        stars=100,
        forks=50,
        open_issues=7,
    )

    django_result = RepositoryAnalysisResult(
        owner=django_item.owner,
        repository=django_item.repository_name,
        stars=50,
        forks=20,
        open_issues=5,
    )

    async def fake_analyze_repositories(_provider, _items):
        yield django_id, django_result
        yield fastapi_id, fastapi_result

    class FakeGitHubClient:
        @staticmethod
        async def get_repository(
            owner: str, repository: str
        ) -> RepositoryAnalysisResult:
            raise AssertionError("Should not be called")

    with patch(
        "app.services.job_execution_service.analyze_repositories",
        new=fake_analyze_repositories,
    ):
        with patch(
            "app.services.job_execution_service.save_item_result_and_update_progress",
            return_value=True,
        ) as mock_save:
            with patch(
                "app.services.job_execution_service.complete_claimed_job",
                return_value=True,
            ) as mock_complete:
                job_id = uuid.uuid4()
                execution_token = uuid.uuid4()
                github_client = FakeGitHubClient()

                result = asyncio.run(
                    execute_claimed_job_async(
                        db, job_id, execution_token, github_client
                    )
                )

                assert result is True
                assert mock_save.call_count == 2

                assert mock_save.call_args_list[0].kwargs["item_id"] == django_id
                assert (
                    mock_save.call_args_list[0].kwargs["analysis_result"]
                    == django_result
                )

                assert mock_save.call_args_list[1].kwargs["item_id"] == fastapi_id
                assert (
                    mock_save.call_args_list[1].kwargs["analysis_result"]
                    == fastapi_result
                )

                mock_complete.assert_called_once()


def test_async_execution_saves_sequentially_with_correct_token_and_timestamps():
    fastapi_id = uuid.uuid4()
    django_id = uuid.uuid4()

    fastapi_item = MagicMock()
    fastapi_item.id = fastapi_id
    fastapi_item.owner = "fastapi"
    fastapi_item.repository_name = "fastapi"

    django_item = MagicMock()
    django_item.id = django_id
    django_item.owner = "django"
    django_item.repository_name = "django"

    db = MagicMock()
    db.scalars.return_value.all.return_value = [fastapi_item, django_item]

    fastapi_result = RepositoryAnalysisResult(
        owner=fastapi_item.owner,
        repository=fastapi_item.repository_name,
        stars=100,
        forks=50,
        open_issues=7,
    )

    django_result = RepositoryAnalysisResult(
        owner=django_item.owner,
        repository=django_item.repository_name,
        stars=50,
        forks=20,
        open_issues=5,
    )

    events = []

    async def fake_analyze_repositories(_provider, _items):
        events.append("django_yielded")
        yield django_id, django_result

        events.append("fastapi_yielded")
        yield fastapi_id, fastapi_result

    def record_save(**kwargs):
        if kwargs["item_id"] == django_id:
            events.append("django_saved")

        elif kwargs["item_id"] == fastapi_id:
            events.append("fastapi_saved")

        return True

    class FakeGitHubClient:
        @staticmethod
        async def get_repository(
            owner: str, repository: str
        ) -> RepositoryAnalysisResult:
            raise AssertionError("Should not be called")

    with patch(
        "app.services.job_execution_service.analyze_repositories",
        new=fake_analyze_repositories,
    ):
        with patch(
            "app.services.job_execution_service.save_item_result_and_update_progress",
            side_effect=record_save,
        ) as mock_save:
            with patch(
                "app.services.job_execution_service.complete_claimed_job",
                return_value=True,
            ):
                job_id = uuid.uuid4()
                execution_token = uuid.uuid4()
                github_client = FakeGitHubClient()

                result = asyncio.run(
                    execute_claimed_job_async(
                        db, job_id, execution_token, github_client
                    )
                )

                assert result is True
                assert mock_save.call_count == 2

                assert (
                    mock_save.call_args_list[0].kwargs["execution_token"]
                    == execution_token
                )
                assert (
                    mock_save.call_args_list[1].kwargs["execution_token"]
                    == execution_token
                )

                assert events == [
                    "django_yielded",
                    "django_saved",
                    "fastapi_yielded",
                    "fastapi_saved",
                ]

                first_timestamp = mock_save.call_args_list[0].kwargs["completed_at"]
                second_timestamp = mock_save.call_args_list[1].kwargs["completed_at"]

                assert isinstance(first_timestamp, datetime)
                assert isinstance(second_timestamp, datetime)

                assert first_timestamp.utcoffset() == timedelta(0)
                assert second_timestamp.utcoffset() == timedelta(0)


def test_async_execution_stops_and_cleans_up_on_rejected_save():
    fastapi_id = uuid.uuid4()
    django_id = uuid.uuid4()

    fastapi_item = MagicMock()
    fastapi_item.id = fastapi_id
    fastapi_item.owner = "fastapi"
    fastapi_item.repository_name = "fastapi"

    django_item = MagicMock()
    django_item.id = django_id
    django_item.owner = "django"
    django_item.repository_name = "django"

    db = MagicMock()
    db.scalars.return_value.all.return_value = [fastapi_item, django_item]

    fastapi_result = RepositoryAnalysisResult(
        owner="fastapi",
        repository="fastapi",
        stars=100,
        forks=50,
        open_issues=7,
    )

    django_result = RepositoryAnalysisResult(
        owner="django",
        repository="django",
        stars=50,
        forks=20,
        open_issues=5,
    )

    events = []

    async def fake_analyze_repositories(_provider, _items):
        try:
            events.append("fastapi_yielded")
            yield fastapi_id, fastapi_result

            events.append("django_yielded")
            yield django_id, django_result

        finally:
            events.append("analysis_closed")

    class FakeGitHubClient:
        @staticmethod
        async def get_repository(
            owner: str, repository: str
        ) -> RepositoryAnalysisResult:
            raise AssertionError("Should not be called")

    job_id = uuid.uuid4()
    execution_token = uuid.uuid4()
    github_client = FakeGitHubClient()

    with patch(
        "app.services.job_execution_service.analyze_repositories",
        new=fake_analyze_repositories,
    ):
        with patch(
            "app.services.job_execution_service.save_item_result_and_update_progress",
            return_value=False,
        ) as mock_save:
            with patch(
                "app.services.job_execution_service.complete_claimed_job",
                return_value=True,
            ) as mock_complete:

                async def run_test():
                    test_result = await execute_claimed_job_async(
                        db,
                        job_id,
                        execution_token,
                        github_client,
                    )

                    assert events == [
                        "fastapi_yielded",
                        "analysis_closed",
                    ]

                    return test_result

                result = asyncio.run(run_test())

                assert result is False
                mock_save.assert_called_once()
                assert mock_save.call_args.kwargs["item_id"] == fastapi_id
                mock_complete.assert_not_called()


def test_async_execution_propagates_analysis_error_and_cleans_up():
    fastapi_id = uuid.uuid4()

    fastapi_item = MagicMock()
    fastapi_item.id = fastapi_id
    fastapi_item.owner = "fastapi"
    fastapi_item.repository_name = "fastapi"

    db = MagicMock()
    db.scalars.return_value.all.return_value = [fastapi_item]

    fastapi_result = RepositoryAnalysisResult(
        owner="fastapi",
        repository="fastapi",
        stars=100,
        forks=50,
        open_issues=7,
    )

    events = []

    async def fake_analyze_repositories(_provider, _items):
        try:
            yield fastapi_id, fastapi_result
            raise RuntimeError("analysis failed")
        finally:
            events.append("analysis_closed")

    class FakeGitHubClient:
        @staticmethod
        async def get_repository(
            owner: str, repository: str
        ) -> RepositoryAnalysisResult:
            raise AssertionError("Should not be called")

    job_id = uuid.uuid4()
    execution_token = uuid.uuid4()
    github_client = FakeGitHubClient()

    with patch(
        "app.services.job_execution_service.analyze_repositories",
        new=fake_analyze_repositories,
    ):
        with patch(
            "app.services.job_execution_service.save_item_result_and_update_progress",
            return_value=True,
        ) as mock_save:
            with patch(
                "app.services.job_execution_service.complete_claimed_job",
                return_value=True,
            ) as mock_complete:
                with pytest.raises(RuntimeError, match="analysis failed"):
                    asyncio.run(
                        execute_claimed_job_async(
                            db,
                            job_id,
                            execution_token,
                            github_client,
                        )
                    )

                mock_save.assert_called_once()
                assert events == ["analysis_closed"]
                mock_complete.assert_not_called()


def test_async_execution_propagates_persistence_error_and_cleans_up():
    fastapi_id = uuid.uuid4()

    fastapi_item = MagicMock()
    fastapi_item.id = fastapi_id
    fastapi_item.owner = "fastapi"
    fastapi_item.repository_name = "fastapi"

    db = MagicMock()
    db.scalars.return_value.all.return_value = [fastapi_item]

    fastapi_result = RepositoryAnalysisResult(
        owner="fastapi",
        repository="fastapi",
        stars=100,
        forks=50,
        open_issues=7,
    )

    events = []

    async def fake_analyze_repositories(_provider, _items):
        try:
            yield fastapi_id, fastapi_result
        finally:
            events.append("analysis_closed")

    class FakeGitHubClient:
        @staticmethod
        async def get_repository(
            owner: str, repository: str
        ) -> RepositoryAnalysisResult:
            raise AssertionError("Should not be called")

    job_id = uuid.uuid4()
    execution_token = uuid.uuid4()
    github_client = FakeGitHubClient()

    with patch(
        "app.services.job_execution_service.analyze_repositories",
        new=fake_analyze_repositories,
    ):
        with patch(
            "app.services.job_execution_service.save_item_result_and_update_progress",
            side_effect=RuntimeError("persistence failed"),
        ) as mock_save:
            with patch(
                "app.services.job_execution_service.complete_claimed_job",
                return_value=True,
            ) as mock_complete:

                async def run_test():
                    with pytest.raises(RuntimeError, match="persistence failed"):
                        await execute_claimed_job_async(
                            db,
                            job_id,
                            execution_token,
                            github_client,
                        )

                    assert events == ["analysis_closed"]

                asyncio.run(run_test())

                mock_save.assert_called_once()
                assert mock_save.call_args.kwargs["item_id"] == fastapi_id
                mock_complete.assert_not_called()


def test_async_execution_returns_false_when_completion_rejected():
    fastapi_id = uuid.uuid4()

    fastapi_item = MagicMock()
    fastapi_item.id = fastapi_id
    fastapi_item.owner = "fastapi"
    fastapi_item.repository_name = "fastapi"

    db = MagicMock()
    db.scalars.return_value.all.return_value = [fastapi_item]

    fastapi_result = RepositoryAnalysisResult(
        owner="fastapi",
        repository="fastapi",
        stars=100,
        forks=50,
        open_issues=7,
    )

    async def fake_analyze_repositories(_provider, _items):
        yield fastapi_id, fastapi_result

    class FakeGitHubClient:
        @staticmethod
        async def get_repository(
            owner: str, repository: str
        ) -> RepositoryAnalysisResult:
            raise AssertionError("Should not be called")

    job_id = uuid.uuid4()
    execution_token = uuid.uuid4()
    github_client = FakeGitHubClient()

    with patch(
        "app.services.job_execution_service.analyze_repositories",
        new=fake_analyze_repositories,
    ):
        with patch(
            "app.services.job_execution_service.save_item_result_and_update_progress",
            return_value=True,
        ) as mock_save:
            with patch(
                "app.services.job_execution_service.complete_claimed_job",
                return_value=False,
            ) as mock_complete:
                result = asyncio.run(
                    execute_claimed_job_async(
                        db,
                        job_id,
                        execution_token,
                        github_client,
                    )
                )

                assert result is False
                mock_save.assert_called_once()
                mock_complete.assert_called_once()

                assert mock_complete.call_args.kwargs["job_id"] == job_id
                assert (
                    mock_complete.call_args.kwargs["execution_token"] == execution_token
                )


def test_async_execution_completes_job_with_no_pending_items():
    job_id = uuid.uuid4()
    execution_token = uuid.uuid4()

    db = MagicMock()
    db.scalars.return_value.all.return_value = []

    class FakeGitHubClient:
        @staticmethod
        async def get_repository(
            owner: str, repository: str
        ) -> RepositoryAnalysisResult:
            raise AssertionError("Provider should not be called")

    with patch(
        "app.services.job_execution_service.save_item_result_and_update_progress",
        return_value=True,
    ) as mock_save:
        with patch(
            "app.services.job_execution_service.complete_claimed_job",
            return_value=True,
        ) as mock_complete:
            result = asyncio.run(
                execute_claimed_job_async(
                    db,
                    job_id,
                    execution_token,
                    FakeGitHubClient(),
                )
            )

            assert result is True

            mock_save.assert_not_called()
            mock_complete.assert_called_once()

            assert mock_complete.call_args.kwargs["job_id"] == job_id
            assert mock_complete.call_args.kwargs["execution_token"] == execution_token
