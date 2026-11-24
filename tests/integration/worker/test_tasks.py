import asyncio
from datetime import UTC, datetime, timedelta
from functools import partial
from unittest.mock import patch

import httpx
from sqlalchemy import select

from app.domain.enums import JobAttemptStatus, JobStatus, RepositoryStatus
from app.models import Job, JobAttempt, RepositoryAnalysisItem
from app.providers.github import github_client_context
from app.repositories.user import create_user
from app.schemas.jobs import CreateJobRequest, RepositoryBatchAnalysisInput
from app.services.job_request import hash_job_request
from app.services.job_service import create_job
from app.services.repository_analysis_handler import analyze_repositories_with_retries
from app.worker.tasks import process_job


def test_process_job_completes_queued_job(test_session_factory):
    reference_time = datetime(2026, 11, 13, 14, 30, tzinfo=UTC)
    fastapi_push = reference_time - timedelta(days=5)
    sqlalchemy_push = reference_time - timedelta(days=181)

    def handler(http_request: httpx.Request) -> httpx.Response:
        if http_request.url.path == "/repos/fastapi/fastapi":
            owner, repo = "fastapi", "fastapi"
            stars, forks, open_issues = 100, 20, 5
            language = "python"
            archived = True
            pushed_at = fastapi_push.isoformat()

        elif http_request.url.path == "/repos/sqlalchemy/sqlalchemy":
            owner, repo = "sqlalchemy", "sqlalchemy"
            stars, forks, open_issues = 250, 50, 10
            language = "c"
            archived = False
            pushed_at = sqlalchemy_push.isoformat()

        else:
            raise AssertionError(f"Unexpected GitHub request: {http_request.url}")

        return httpx.Response(
            status_code=200,
            json={
                "owner": {"login": owner},
                "name": repo,
                "stargazers_count": stars,
                "forks_count": forks,
                "open_issues_count": open_issues,
                "language": language,
                "archived": archived,
                "pushed_at": pushed_at,
            },
            request=http_request,
        )

    transport = httpx.MockTransport(handler)

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=[
                "FastApi/FastApi",
                "SQLAlchemy/SQLAlchemy",
            ]
        ),
    )

    with test_session_factory() as db:
        user = create_user(
            db=db,
            email="user@example.com",
            hashed_password="hashed_password",
        )

        job = create_job(
            db=db,
            user_id=user.id,
            request=request,
            idempotency_key="test-key-123",
            request_hash=hash_job_request(request),
        )

        job_id = job.id
        db.commit()

    with test_session_factory() as db:
        job = db.get(Job, job_id)

        assert job is not None
        assert job.status == JobStatus.QUEUED
        assert job.attempt_count == 0

    with patch("app.worker.tasks.DBSession", new=test_session_factory):
        with patch(
            "app.worker.tasks.github_client_context",
            new=partial(github_client_context, transport=transport),
        ):
            with (
                patch("app.services.job_execution_service.datetime") as clock_mock,
                patch("app.worker.tasks.datetime") as task_clock_mock,
            ):
                clock_mock.now.return_value = reference_time
                task_clock_mock.now.return_value = reference_time

                process_job.run(str(job_id))

    with test_session_factory() as db:
        stmt = select(Job).where(Job.id == job_id)
        job = db.scalars(stmt).one()

        stmt = select(JobAttempt).where(JobAttempt.job_id == job_id)
        attempts = db.scalars(stmt).all()

        stmt = select(RepositoryAnalysisItem).where(
            RepositoryAnalysisItem.job_id == job_id
        )
        analysis_items = db.scalars(stmt).all()

        assert len(analysis_items) == 2

        expected_metrics = {
            "fastapi": (100, 20, 5, "python", True, fastapi_push, "HIGH"),
            "sqlalchemy": (250, 50, 10, "c", False, sqlalchemy_push, "LOW"),
        }

        for item in analysis_items:
            assert item.status == RepositoryStatus.SUCCEEDED

            (
                expected_stars,
                expected_forks,
                expected_issues,
                expected_language,
                expected_archived,
                expected_last_push_at,
                expected_classification,
            ) = expected_metrics[item.repository_name]

            assert item.stars == expected_stars
            assert item.forks == expected_forks
            assert item.open_issues == expected_issues
            assert item.completed_at is not None
            assert item.primary_language == expected_language
            assert item.archived == expected_archived
            assert item.last_push_at == expected_last_push_at
            assert item.activity_classification == expected_classification

        assert job.status == JobStatus.COMPLETED
        assert job.attempt_count == 1
        assert job.progress_completed == 2
        assert job.progress_total == 2
        assert job.result_summary == {
            "total": 2,
            "succeeded": 2,
            "failed": 0,
        }
        assert job.started_at is not None
        assert job.finished_at is not None
        assert job.started_at <= job.finished_at
        assert job.execution_token is None
        assert job.lease_expires_at is None

        assert len(attempts) == 1

        attempt = attempts[0]

        assert attempt.attempt_number == 1
        assert attempt.status == JobAttemptStatus.SUCCEEDED
        assert attempt.finished_at == job.finished_at


def test_process_job_completes_mixed_outcomes(test_session_factory):
    reference_time = datetime(2026, 11, 13, 14, 30, tzinfo=UTC)
    fastapi_push = reference_time - timedelta(days=5)
    sqlalchemy_push = reference_time - timedelta(days=181)

    request_counts: dict[str, int] = {}

    def handler(http_request: httpx.Request) -> httpx.Response:
        path = http_request.url.path
        request_counts[path] = request_counts.get(path, 0) + 1

        if path == "/repos/fastapi/fastapi":
            owner, repo = "fastapi", "fastapi"
            stars, forks, open_issues = 100, 20, 5
            language = "python"
            archived = True
            pushed_at = fastapi_push.isoformat()

        elif path == "/repos/sqlalchemy/sqlalchemy":
            if request_counts[path] == 1:
                return httpx.Response(
                    status_code=503,
                    json={"message": "Service unavailable"},
                    request=http_request,
                )

            owner, repo = "sqlalchemy", "sqlalchemy"
            stars, forks, open_issues = 250, 50, 10
            language = "c"
            archived = False
            pushed_at = sqlalchemy_push.isoformat()

        elif path == "/repos/pallets/flask":
            return httpx.Response(
                status_code=404,
                json={"message": "Not Found"},
                request=http_request,
            )

        elif path == "/repos/django/django":
            return httpx.Response(
                status_code=503,
                json={"message": "Service unavailable"},
                request=http_request,
            )

        else:
            raise AssertionError(f"Unexpected GitHub request: {http_request.url}")

        return httpx.Response(
            status_code=200,
            json={
                "owner": {"login": owner},
                "name": repo,
                "stargazers_count": stars,
                "forks_count": forks,
                "open_issues_count": open_issues,
                "language": language,
                "archived": archived,
                "pushed_at": pushed_at,
            },
            request=http_request,
        )

    transport = httpx.MockTransport(handler)

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=[
                "FastApi/FastApi",
                "SQLAlchemy/SQLAlchemy",
                "Pallets/Flask",
                "Django/Django",
            ]
        ),
    )

    with test_session_factory() as db:
        user = create_user(
            db=db,
            email="user@example.com",
            hashed_password="hashed_password",
        )

        job = create_job(
            db=db,
            user_id=user.id,
            request=request,
            idempotency_key="test-key-123",
            request_hash=hash_job_request(request),
        )

        job_id = job.id
        db.commit()

    with test_session_factory() as db:
        job = db.get(Job, job_id)

        assert job is not None
        assert job.status == JobStatus.QUEUED
        assert job.attempt_count == 0

    sleep_durations: list[float] = []

    async def fake_sleep(duration: float) -> None:
        sleep_durations.append(duration)
        await asyncio.sleep(0)

    with patch("app.worker.tasks.DBSession", new=test_session_factory):
        with patch(
            "app.worker.tasks.github_client_context",
            new=partial(github_client_context, transport=transport),
        ):
            with (
                patch("app.services.job_execution_service.datetime") as clock_mock,
                patch("app.worker.tasks.datetime") as task_clock_mock,
            ):
                clock_mock.now.return_value = reference_time
                task_clock_mock.now.return_value = reference_time
                with patch(
                    "app.services.job_execution_service.analyze_repositories_with_retries",
                    new=partial(analyze_repositories_with_retries, sleep=fake_sleep),
                ):
                    process_job.run(str(job_id))

                assert request_counts["/repos/fastapi/fastapi"] == 1
                assert request_counts["/repos/sqlalchemy/sqlalchemy"] == 2
                assert request_counts["/repos/pallets/flask"] == 1
                assert request_counts["/repos/django/django"] == 3

                assert sorted(sleep_durations) == [1, 1, 2]

    with test_session_factory() as db:
        stmt = select(Job).where(Job.id == job_id)
        job = db.scalars(stmt).one()

        stmt = select(JobAttempt).where(JobAttempt.job_id == job_id)
        attempts = db.scalars(stmt).all()

        stmt = select(RepositoryAnalysisItem).where(
            RepositoryAnalysisItem.job_id == job_id
        )
        analysis_items = db.scalars(stmt).all()

        assert len(analysis_items) == 4

        expected_metrics = {
            "fastapi": (100, 20, 5, "python", True, fastapi_push, "HIGH", 1),
            "sqlalchemy": (250, 50, 10, "c", False, sqlalchemy_push, "LOW", 2),
        }

        for item in analysis_items:
            if item.repository_name in expected_metrics:
                assert item.status == RepositoryStatus.SUCCEEDED
                (
                    expected_stars,
                    expected_forks,
                    expected_issues,
                    expected_language,
                    expected_archived,
                    expected_last_push_at,
                    expected_classification,
                    expected_attempt_count,
                ) = expected_metrics[item.repository_name]

                assert item.stars == expected_stars
                assert item.forks == expected_forks
                assert item.open_issues == expected_issues
                assert item.completed_at is not None
                assert item.primary_language == expected_language
                assert item.archived == expected_archived
                assert item.last_push_at == expected_last_push_at
                assert item.activity_classification == expected_classification

                assert item.attempt_count == expected_attempt_count
                assert item.error_type is None
                assert item.error_message is None

            elif item.repository_name == "flask":
                assert item.stars is None
                assert item.forks is None
                assert item.open_issues is None
                assert item.status == RepositoryStatus.FAILED
                assert item.attempt_count == 1
                assert item.error_type == "RepositoryUnavailableError"
                assert item.error_message == "Repository not found or inaccessible"
                assert item.completed_at is not None

            elif item.repository_name == "django":
                assert item.stars is None
                assert item.forks is None
                assert item.open_issues is None
                assert item.status == RepositoryStatus.FAILED
                assert item.attempt_count == 3
                assert item.error_type == "GitHubUnavailableError"
                assert item.error_message == "GitHub is temporarily unavailable"

                assert item.completed_at is not None

        assert job.progress_completed == 4
        assert job.progress_total == 4
        assert job.result_summary == {
            "total": 4,
            "succeeded": 2,
            "failed": 2,
        }
        assert job.status == JobStatus.COMPLETED
        assert job.attempt_count == 1
        assert job.started_at is not None
        assert job.finished_at is not None
        assert job.started_at <= job.finished_at
        assert job.execution_token is None
        assert job.lease_expires_at is None

        assert len(attempts) == 1

        attempt = attempts[0]

        assert attempt.attempt_number == 1
        assert attempt.status == JobAttemptStatus.SUCCEEDED
        assert attempt.finished_at == job.finished_at

        assert attempt.started_at is not None
        assert attempt.finished_at is not None


def test_process_job_does_not_reexecute_completed_job(test_session_factory):
    http_requests = []

    def handler(http_request: httpx.Request) -> httpx.Response:
        http_requests.append(http_request.url.path)

        if http_request.url.path == "/repos/fastapi/fastapi":
            owner, repo = "fastapi", "fastapi"
            stars, forks, open_issues = 100, 20, 5
            language = "python"
            archived = True
            pushed_at = "2026-11-05T14:30:00Z"
        elif http_request.url.path == "/repos/sqlalchemy/sqlalchemy":
            owner, repo = "sqlalchemy", "sqlalchemy"
            stars, forks, open_issues = 250, 50, 10
            language = "c"
            archived = False
            pushed_at = "2026-11-03T14:30:00Z"

        else:
            raise AssertionError(f"Unexpected GitHub request: {http_request.url}")

        return httpx.Response(
            status_code=200,
            json={
                "owner": {"login": owner},
                "name": repo,
                "stargazers_count": stars,
                "forks_count": forks,
                "open_issues_count": open_issues,
                "language": language,
                "archived": archived,
                "pushed_at": pushed_at,
            },
            request=http_request,
        )

    transport = httpx.MockTransport(handler)

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=[
                "FastApi/FastApi",
                "SQLAlchemy/SQLAlchemy",
            ]
        ),
    )

    with test_session_factory() as db:
        user = create_user(
            db=db,
            email="user@example.com",
            hashed_password="hashed_password",
        )

        job = create_job(
            db=db,
            user_id=user.id,
            request=request,
            idempotency_key="test-key-123",
            request_hash=hash_job_request(request),
        )

        job_id = job.id
        db.commit()

    with patch("app.worker.tasks.DBSession", new=test_session_factory):
        with patch(
            "app.worker.tasks.github_client_context",
            new=partial(github_client_context, transport=transport),
        ):
            process_job.run(str(job_id))

            assert len(http_requests) == 2

    with test_session_factory() as db:
        stmt = select(Job).where(Job.id == job_id)
        job = db.scalars(stmt).one()

        stmt = select(JobAttempt).where(JobAttempt.job_id == job_id)
        attempts = db.scalars(stmt).all()

        stmt = select(RepositoryAnalysisItem).where(
            RepositoryAnalysisItem.job_id == job_id
        )
        items = db.scalars(stmt).all()

        assert job.status == JobStatus.COMPLETED
        assert job.attempt_count == 1
        assert len(attempts) == 1
        assert len(items) == 2

        original_progress = job.progress_completed
        original_summary = job.result_summary
        original_finished_at = job.finished_at
        original_attempt_id = attempts[0].id

        original_items = [
            (
                item.id,
                item.status,
                item.stars,
                item.forks,
                item.open_issues,
                item.completed_at,
                item.primary_language,
                item.archived,
                item.last_push_at,
            )
            for item in items
        ]

    with patch("app.worker.tasks.DBSession", new=test_session_factory):
        with patch(
            "app.worker.tasks.github_client_context",
            new=partial(github_client_context, transport=transport),
        ):
            process_job.run(str(job_id))

            assert len(http_requests) == 2

    with test_session_factory() as db:
        stmt = select(Job).where(Job.id == job_id)
        job = db.scalars(stmt).one()

        stmt = select(JobAttempt).where(JobAttempt.job_id == job_id)
        attempts = db.scalars(stmt).all()

        stmt = select(RepositoryAnalysisItem).where(
            RepositoryAnalysisItem.job_id == job_id
        )
        items = db.scalars(stmt).all()

        assert job.status == JobStatus.COMPLETED
        assert job.attempt_count == 1
        assert job.progress_completed == original_progress
        assert job.result_summary == original_summary
        assert job.finished_at == original_finished_at

        assert len(attempts) == 1
        assert attempts[0].id == original_attempt_id

        assert [
            (
                item.id,
                item.status,
                item.stars,
                item.forks,
                item.open_issues,
                item.completed_at,
                item.primary_language,
                item.archived,
                item.last_push_at,
            )
            for item in items
        ] == original_items
