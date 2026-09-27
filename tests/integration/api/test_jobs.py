import uuid
from datetime import UTC, datetime, timedelta

from fastapi import status

from app.domain.enums import JobStatus
from app.repositories.user import create_user
from app.schemas.jobs import CreateJobRequest, RepositoryBatchAnalysisInput
from app.services.job_request import hash_job_request
from app.services.job_service import create_job, submit_job


def test_get_job_detail_returns_job_for_owner(
    client, db_session, authenticated_user_factory
):

    user, headers = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["owner/repository"]),
    )

    request_hash = hash_job_request(request)

    job = create_job(
        db_session,
        user.id,
        request,
        "test_idempotency_key",
        request_hash,
    )

    response = client.get(f"/jobs/{job.id}", headers=headers)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["id"] == str(job.id)


def test_get_job_detail_returns_404_for_unknown_job(client, authenticated_user_factory):

    user, headers = authenticated_user_factory("user@example.com", "password123")

    job_id = uuid.uuid4()

    response = client.get(f"/jobs/{job_id}", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": "Job not found"}


def test_get_job_detail_returns_404_for_other_users_job(
    client, db_session, authenticated_user_factory
):

    _, headers = authenticated_user_factory("user@example.com", "password123")

    second_user = create_user(
        db_session, email="second_user@example.com", hashed_password="password123"
    )

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["owner/repository"]),
    )

    request_hash = hash_job_request(request)

    job = create_job(
        db_session,
        second_user.id,
        request,
        "test_idempotency_key",
        request_hash,
    )

    response = client.get(f"/jobs/{job.id}", headers=headers)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": "Job not found"}


def test_get_job_detail_returns_401_without_authentication(client):
    job_id = uuid.uuid4()

    response = client.get(f"/jobs/{job_id}")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_create_job_returns_201_for_valid_request(client, authenticated_user_factory):

    _, headers = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["owner/repository"]),
    )

    headers["Idempotency-Key"] = "test-idempotency-key"

    response = client.post("/jobs", json=request.model_dump(), headers=headers)

    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()

    assert data["type"] == "REPOSITORY_BATCH_ANALYSIS"
    assert data["status"] == "QUEUED"
    assert data["progress_total"] == 1


def test_create_job_returns_401_without_authentication(client):

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["owner/repository"]),
    )

    headers = {
        "Idempotency-Key": "test-idempotency-key",
    }

    response = client.post("/jobs", json=request.model_dump(), headers=headers)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_create_job_returns_422_without_idempotency_key(
    client, authenticated_user_factory
):

    _, headers = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["owner/repository"]),
    )

    response = client.post("/jobs", json=request.model_dump(), headers=headers)

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_create_job_repeating_same_key_and_request_returns_same_job(
    client, authenticated_user_factory
):

    _, headers = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["owner/repository"]),
    )

    headers["Idempotency-Key"] = "test-idempotency-key"

    first_response = client.post("/jobs", json=request.model_dump(), headers=headers)

    assert first_response.status_code == status.HTTP_201_CREATED
    first_job_id = first_response.json()["id"]

    second_response = client.post("/jobs", json=request.model_dump(), headers=headers)

    assert second_response.status_code == status.HTTP_201_CREATED
    second_job_id = second_response.json()["id"]

    assert second_job_id == first_job_id


def test_create_job_repeating_same_key_with_different_request_returns_409(
    client, authenticated_user_factory
):

    _, headers = authenticated_user_factory("user@example.com", "password123")

    first_request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["owner/repository"]),
    )

    headers["Idempotency-Key"] = "test-idempotency-key"

    first_response = client.post(
        "/jobs", json=first_request.model_dump(), headers=headers
    )
    assert first_response.status_code == status.HTTP_201_CREATED

    second_request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["new_owner/new_repository"]),
    )

    second_response = client.post(
        "/jobs", json=second_request.model_dump(), headers=headers
    )
    assert second_response.status_code == status.HTTP_409_CONFLICT
    assert second_response.json() == {"detail": "Idempotency key conflict"}


def test_get_jobs_returns_only_authenticated_users_jobs(
    client, authenticated_user_factory, db_session
):

    user_a, headers = authenticated_user_factory("user_a@example.com", "password123")

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
        db=db_session,
        user_id=user_a.id,
        request=request,
        idempotency_key="test-key-123",
    )

    submit_job(
        db=db_session,
        user_id=user_b.id,
        request=request,
        idempotency_key="test-key-456",
    )

    response = client.get("/jobs", headers=headers)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(job_a.id)


def test_get_jobs_returns_newest_first(client, authenticated_user_factory, db_session):

    user, headers = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["owner/repository"]),
    )

    first_job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    second_job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-456",
    )

    now = datetime.now(UTC)
    first_job.created_at = now - timedelta(minutes=10)
    second_job.created_at = now - timedelta(minutes=5)
    db_session.flush()

    response = client.get("/jobs", headers=headers)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data[0]["id"] == str(second_job.id)
    assert data[1]["id"] == str(first_job.id)


def test_get_jobs_limit_and_offset_work(client, authenticated_user_factory, db_session):

    user, headers = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["owner/repository"]),
    )

    first_job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    second_job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-456",
    )

    third_job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-789",
    )

    now = datetime.now(UTC)
    first_job.created_at = now - timedelta(minutes=15)
    second_job.created_at = now - timedelta(minutes=10)
    third_job.created_at = now - timedelta(minutes=5)
    db_session.flush()

    response = client.get("/jobs?limit=1&offset=1", headers=headers)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == str(second_job.id)


def test_get_jobs_filters_by_status(client, authenticated_user_factory, db_session):
    user, headers = authenticated_user_factory("user@example.com", "password123")

    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(repositories=["owner/repository"]),
    )

    submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-123",
    )

    second_job = submit_job(
        db=db_session,
        user_id=user.id,
        request=request,
        idempotency_key="test-key-456",
    )

    second_job.status = JobStatus.COMPLETED
    db_session.flush()

    response = client.get("/jobs?status=COMPLETED", headers=headers)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == str(second_job.id)


def test_get_jobs_returns_401_without_authentication(client):

    response = client.get("/jobs")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_get_jobs_returns_422_for_invalid_limit_above_100(
    client, authenticated_user_factory
):
    _, headers = authenticated_user_factory("user@example.com", "password123")

    response = client.get("/jobs?limit=101", headers=headers)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_get_jobs_returns_422_for_invalid_limit_below_1(
    client, authenticated_user_factory
):
    _, headers = authenticated_user_factory("user@example.com", "password123")

    response = client.get("/jobs?limit=0", headers=headers)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_get_jobs_returns_422_for_invalid_offset(
    client, authenticated_user_factory
):
    _, headers = authenticated_user_factory("user@example.com", "password123")

    response = client.get("/jobs?offset=-1", headers=headers)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
