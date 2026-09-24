import uuid

from fastapi import status

from app.repositories.user import create_user
from app.schemas.jobs import CreateJobRequest, RepositoryBatchAnalysisInput
from app.services.job_request import hash_job_request
from app.services.job_service import create_job


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
