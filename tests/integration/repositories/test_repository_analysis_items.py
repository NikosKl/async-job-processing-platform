import uuid

from app.repositories.repository_analysis_item import (
    list_repository_analysis_items_by_job_id,
)
from app.repositories.user import create_user
from app.schemas.jobs import CreateJobRequest, RepositoryBatchAnalysisInput
from app.services.job_service import submit_job


def test_list_repository_analysis_items_by_job_id_excludes_other_jobs_items(
    db_session, authenticated_user_factory
):
    user_a, _ = authenticated_user_factory("user_a@example.com", "password123")

    user_b = create_user(
        db_session,
        email="user_b@example.com",
        hashed_password="password123",
    )

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["owner/repository"]),
    )

    job_a = submit_job(
        db_session,
        user_a.id,
        request=request,
        idempotency_key="test-key-123",
    )

    job_b = submit_job(
        db_session,
        user_b.id,
        request=request,
        idempotency_key="test-key-456",
    )

    items = list_repository_analysis_items_by_job_id(
        db_session,
        job_a.id,
    )

    assert len(items) == 1
    assert items[0].job_id == job_a.id
    assert items[0].job_id != job_b.id


def test_list_repository_analysis_items_by_job_id_returns_items_in_position_order(
    db_session, authenticated_user_factory
):

    user, _ = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=["FastApi/FastApi", "SQLAlchemy/SQLAlchemy", "Pallets/Flask"]
        ),
    )

    job = submit_job(
        db_session,
        user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    items = list_repository_analysis_items_by_job_id(
        db_session,
        job.id,
    )

    assert len(items) == 3
    assert [item.position for item in items] == [0, 1, 2]


def test_list_repository_analysis_items_by_job_id_returns_empty_list_for_unknown_job(
    db_session,
):

    job_id = uuid.uuid4()

    items = list_repository_analysis_items_by_job_id(
        db_session,
        job_id,
    )

    assert items == []
