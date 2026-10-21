import uuid
from datetime import UTC
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.domain.enums import RepositoryStatus
from app.services.job_execution_service import (
    RepositoryAnalysisResult,
    execute_claimed_job,
    run_fake_repository_analysis,
)


def test_run_fake_repository_analysis_preserves_repository_identifiers():

    result = run_fake_repository_analysis("fastapi", "example-fastapi")

    assert result.owner == "fastapi"
    assert result.repository == "example-fastapi"


def test_run_fake_repository_analysis_returns_zero_placeholder_metrics():
    result = run_fake_repository_analysis("fastapi", "example-fastapi")

    assert result.stars == 0
    assert result.forks == 0
    assert result.open_issues == 0


def test_run_fake_repository_analysis_returns_equal_but_distinct_results():
    result_a = run_fake_repository_analysis("fastapi", "example-fastapi")
    result_b = run_fake_repository_analysis("fastapi", "example-fastapi")

    assert result_a == result_b
    assert result_a is not result_b


def test_execute_claimed_job_processes_pending_items_and_completes():
    db = MagicMock()

    item_a = SimpleNamespace(
        id=uuid.uuid4(),
        owner="fastapi",
        repository_name="fastapi",
    )

    item_b = SimpleNamespace(
        id=uuid.uuid4(),
        owner="sqlalchemy",
        repository_name="sqlalchemy",
    )

    db.scalars.return_value.all.return_value = [item_a, item_b]

    with patch(
        "app.services.job_execution_service.run_fake_repository_analysis"
    ) as analysis_mock:
        analysis_mock.return_value = RepositoryAnalysisResult(
            owner="test_owner",
            repository="test_repository",
            stars=0,
            forks=0,
            open_issues=0,
        )
        with patch(
            "app.services.job_execution_service.save_item_result_and_update_progress",
            return_value=True,
        ) as save_mock:
            with patch(
                "app.services.job_execution_service.complete_claimed_job",
                return_value=True,
            ) as complete_mock:
                job_id = uuid.uuid4()
                execution_token = uuid.uuid4()

                result = execute_claimed_job(
                    db=db,
                    job_id=job_id,
                    execution_token=execution_token,
                )

        assert result is True

        assert analysis_mock.call_count == 2
        assert save_mock.call_count == 2
        complete_mock.assert_called_once()

        completion_call = complete_mock.call_args
        assert completion_call.kwargs["job_id"] == job_id
        assert completion_call.kwargs["execution_token"] == execution_token

        assert analysis_mock.call_args_list[0].kwargs == {
            "owner": "fastapi",
            "repository": "fastapi",
        }

        assert analysis_mock.call_args_list[1].kwargs == {
            "owner": "sqlalchemy",
            "repository": "sqlalchemy",
        }

        assert save_mock.call_args_list[0].kwargs["execution_token"] == execution_token
        assert save_mock.call_args_list[1].kwargs["execution_token"] == execution_token


def test_execute_claimed_job_skips_terminal_items():
    db = MagicMock()

    item_a = SimpleNamespace(
        id=uuid.uuid4(),
        owner="fastapi",
        repository_name="fastapi",
        status=RepositoryStatus.PENDING,
    )

    item_b = SimpleNamespace(
        id=uuid.uuid4(),
        owner="sqlalchemy",
        repository_name="sqlalchemy",
        status=RepositoryStatus.SUCCEEDED,
        stars=100,
        forks=20,
        open_issues=5,
    )

    item_c = SimpleNamespace(
        id=uuid.uuid4(),
        owner="sqlalchemy",
        repository_name="sqlalchemy",
        status=RepositoryStatus.FAILED,
        stars=None,
        forks=None,
        open_issues=None,
    )

    db.scalars.return_value.all.return_value = [item_a]

    with patch(
        "app.services.job_execution_service.run_fake_repository_analysis"
    ) as analysis_mock:
        analysis_mock.return_value = RepositoryAnalysisResult(
            owner="test_owner",
            repository="test_repository",
            stars=0,
            forks=0,
            open_issues=0,
        )
        with patch(
            "app.services.job_execution_service.save_item_result_and_update_progress",
            return_value=True,
        ) as save_mock:
            with patch(
                "app.services.job_execution_service.complete_claimed_job",
                return_value=True,
            ) as complete_mock:
                job_id = uuid.uuid4()
                execution_token = uuid.uuid4()

                result = execute_claimed_job(
                    db=db,
                    job_id=job_id,
                    execution_token=execution_token,
                )

    assert result is True

    analysis_mock.assert_called_once_with(
        owner=item_a.owner,
        repository=item_a.repository_name,
    )

    save_mock.assert_called_once()
    save_call = save_mock.call_args
    assert save_call.kwargs["job_id"] == job_id
    assert save_call.kwargs["item_id"] == item_a.id
    assert save_call.kwargs["execution_token"] == execution_token

    complete_mock.assert_called_once()

    assert item_b.status == RepositoryStatus.SUCCEEDED
    assert item_b.stars == 100
    assert item_b.forks == 20
    assert item_b.open_issues == 5

    assert item_c.status == RepositoryStatus.FAILED
    assert item_c.stars is None
    assert item_c.forks is None
    assert item_c.open_issues is None


def test_execute_claimed_job_uses_original_token_and_utc_timestamps():
    db = MagicMock()

    item_a = SimpleNamespace(
        id=uuid.uuid4(),
        owner="fastapi",
        repository_name="fastapi",
    )

    item_b = SimpleNamespace(
        id=uuid.uuid4(),
        owner="sqlalchemy",
        repository_name="sqlalchemy",
    )

    db.scalars.return_value.all.return_value = [item_a, item_b]

    with patch(
        "app.services.job_execution_service.run_fake_repository_analysis"
    ) as analysis_mock:
        analysis_mock.return_value = RepositoryAnalysisResult(
            owner="test_owner",
            repository="test_repository",
            stars=0,
            forks=0,
            open_issues=0,
        )
        with patch(
            "app.services.job_execution_service.save_item_result_and_update_progress",
            return_value=True,
        ) as save_mock:
            with patch(
                "app.services.job_execution_service.complete_claimed_job",
                return_value=True,
            ):
                job_id = uuid.uuid4()
                execution_token = uuid.uuid4()

                result = execute_claimed_job(
                    db=db,
                    job_id=job_id,
                    execution_token=execution_token,
                )

    assert result is True

    assert save_mock.call_count == 2

    first_call = save_mock.call_args_list[0]
    second_call = save_mock.call_args_list[1]

    assert first_call.kwargs["execution_token"] == execution_token
    assert second_call.kwargs["execution_token"] == execution_token

    first_time = first_call.kwargs["completed_at"]
    second_time = second_call.kwargs["completed_at"]

    assert first_time.tzinfo is not None
    assert first_time.utcoffset() is not None
    assert first_time.tzinfo is UTC

    assert second_time.tzinfo is not None
    assert second_time.utcoffset() is not None
    assert second_time.tzinfo is UTC


def test_execute_claimed_job_stops_on_rejected_save():
    db = MagicMock()

    item_a = SimpleNamespace(
        id=uuid.uuid4(),
        owner="fastapi",
        repository_name="fastapi",
    )

    item_b = SimpleNamespace(
        id=uuid.uuid4(),
        owner="sqlalchemy",
        repository_name="sqlalchemy",
    )

    item_c = SimpleNamespace(
        id=uuid.uuid4(),
        owner="pallets",
        repository_name="flask",
    )

    db.scalars.return_value.all.return_value = [item_a, item_b, item_c]

    with patch(
        "app.services.job_execution_service.run_fake_repository_analysis"
    ) as analysis_mock:
        analysis_mock.return_value = RepositoryAnalysisResult(
            owner="test_owner",
            repository="test_repository",
            stars=0,
            forks=0,
            open_issues=0,
        )
        with patch(
            "app.services.job_execution_service.save_item_result_and_update_progress",
            side_effect=[True, False],
        ) as save_mock:
            with patch(
                "app.services.job_execution_service.complete_claimed_job",
            ) as complete_mock:
                job_id = uuid.uuid4()
                execution_token = uuid.uuid4()

                result = execute_claimed_job(
                    db=db,
                    job_id=job_id,
                    execution_token=execution_token,
                )

    assert result is False

    assert analysis_mock.call_count == 2
    assert save_mock.call_count == 2

    complete_mock.assert_not_called()


def test_execute_claimed_job_propagates_analysis_error_without_completion():
    db = MagicMock()

    item_a = SimpleNamespace(
        id=uuid.uuid4(),
        owner="fastapi",
        repository_name="fastapi",
    )

    item_b = SimpleNamespace(
        id=uuid.uuid4(),
        owner="sqlalchemy",
        repository_name="sqlalchemy",
    )

    db.scalars.return_value.all.return_value = [item_a, item_b]

    with patch(
        "app.services.job_execution_service.run_fake_repository_analysis",
        side_effect=RuntimeError("analysis failed"),
    ) as analysis_mock:
        with patch(
            "app.services.job_execution_service.save_item_result_and_update_progress",
            return_value=True,
        ) as save_mock:
            with patch(
                "app.services.job_execution_service.complete_claimed_job",
                return_value=True,
            ) as complete_mock:
                job_id = uuid.uuid4()
                execution_token = uuid.uuid4()

                with pytest.raises(RuntimeError, match="analysis failed"):
                    execute_claimed_job(
                        db=db,
                        job_id=job_id,
                        execution_token=execution_token,
                    )

    analysis_mock.assert_called_once()
    save_mock.assert_not_called()
    complete_mock.assert_not_called()


def test_execute_claimed_job_propagates_persistence_error_without_completion():
    db = MagicMock()

    item_a = SimpleNamespace(
        id=uuid.uuid4(),
        owner="fastapi",
        repository_name="fastapi",
    )

    item_b = SimpleNamespace(
        id=uuid.uuid4(),
        owner="sqlalchemy",
        repository_name="sqlalchemy",
    )

    db.scalars.return_value.all.return_value = [item_a, item_b]

    with patch(
        "app.services.job_execution_service.run_fake_repository_analysis",
    ) as analysis_mock:
        analysis_mock.return_value = RepositoryAnalysisResult(
            owner="test_owner",
            repository="test_repository",
            stars=0,
            forks=0,
            open_issues=0,
        )
        with patch(
            "app.services.job_execution_service.save_item_result_and_update_progress",
            side_effect=SQLAlchemyError("save failed"),
        ) as save_mock:
            with patch(
                "app.services.job_execution_service.complete_claimed_job",
            ) as complete_mock:
                job_id = uuid.uuid4()
                execution_token = uuid.uuid4()

                with pytest.raises(SQLAlchemyError, match="save failed"):
                    execute_claimed_job(
                        db=db,
                        job_id=job_id,
                        execution_token=execution_token,
                    )

    analysis_mock.assert_called_once()
    save_mock.assert_called_once()
    complete_mock.assert_not_called()


def test_execute_claimed_job_returns_false_when_completion_rejected():
    db = MagicMock()

    item = SimpleNamespace(
        id=uuid.uuid4(),
        owner="fastapi",
        repository_name="fastapi",
    )

    db.scalars.return_value.all.return_value = [item]

    with patch(
        "app.services.job_execution_service.run_fake_repository_analysis"
    ) as analysis_mock:
        analysis_mock.return_value = RepositoryAnalysisResult(
            owner="test_owner",
            repository="test_repository",
            stars=0,
            forks=0,
            open_issues=0,
        )
        with patch(
            "app.services.job_execution_service.save_item_result_and_update_progress",
            return_value=True,
        ) as save_mock:
            with patch(
                "app.services.job_execution_service.complete_claimed_job",
                return_value=False,
            ) as complete_mock:
                job_id = uuid.uuid4()
                execution_token = uuid.uuid4()

                result = execute_claimed_job(
                    db=db,
                    job_id=job_id,
                    execution_token=execution_token,
                )

    assert result is False
    analysis_mock.assert_called_once()
    save_mock.assert_called_once()
    complete_mock.assert_called_once()
