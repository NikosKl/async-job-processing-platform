from app.schemas.jobs import CreateJobRequest, RepositoryBatchAnalysisInput
from app.services.job_request import hash_job_request, normalize_job_request


def test_job_request_lowercase_repos():
    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=[
                "FastApi/FastApi",
                "SQLAlchemy/SQLAlchemy",
            ]
        ),
    )

    result = normalize_job_request(request)

    assert result == {
        "type": "repository_batch_analysis",
        "input": {"repositories": ["fastapi/fastapi", "sqlalchemy/sqlalchemy"]},
    }


def test_job_request_preserves_order():
    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=[
                "SQLAlchemy/SQLAlchemy",
                "FastApi/FastApi",
            ]
        ),
    )

    result = normalize_job_request(request)

    assert result["input"]["repositories"] == [
        "sqlalchemy/sqlalchemy",
        "fastapi/fastapi",
    ]


def test_job_request_does_not_mutate_original_request():
    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=[
                "SQLAlchemy/SQLAlchemy",
            ]
        ),
    )

    result = normalize_job_request(request)

    assert result["input"]["repositories"] == [
        "sqlalchemy/sqlalchemy",
    ]

    assert request.input.repositories == [
        "SQLAlchemy/SQLAlchemy",
    ]


def test_job_same_request_produces_same_hash():
    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=[
                "SQLAlchemy/SQLAlchemy",
                "FastApi/FastApi",
            ]
        ),
    )

    first_hash = hash_job_request(request)
    second_hash = hash_job_request(request)

    assert first_hash == second_hash


def test_same_repos_with_different_casing_produce_same_hash():
    first_request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=[
                "SQLAlchemy/SQLAlchemy",
                "FastApi/FastApi",
            ]
        ),
    )

    second_request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=[
                "SQLALCHEMY/SQLALCHEMY",
                "fastAPI/fastAPI",
            ]
        ),
    )

    first_hash = hash_job_request(first_request)
    second_hash = hash_job_request(second_request)

    assert first_hash == second_hash


def test_same_repos_with_different_order_produce_different_hash():
    first_request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=[
                "SQLAlchemy/SQLAlchemy",
                "FastApi/FastApi",
            ]
        ),
    )

    second_request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=[
                "FastApi/FastApi",
                "SQLAlchemy/SQLAlchemy",
            ]
        ),
    )

    first_hash = hash_job_request(first_request)
    second_hash = hash_job_request(second_request)

    assert first_hash != second_hash


def test_different_repos_with_different_order_produce_different_hash():
    first_request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=[
                "Pallets/Flask",
                "FastApi/FastApi",
            ]
        ),
    )

    second_request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=[
                "FastApi/FastApi",
                "SQLAlchemy/SQLAlchemy",
            ]
        ),
    )

    first_hash = hash_job_request(first_request)
    second_hash = hash_job_request(second_request)

    assert first_hash != second_hash


def test_hash_job_request_returns_sha256_hash():
    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=[
                "SQLAlchemy/SQLAlchemy",
                "FastApi/FastApi",
            ]
        ),
    )

    hash_request = hash_job_request(request)

    assert isinstance(hash_request, str)
    assert len(hash_request) == 64
    assert all(characters in "0123456789abcdef" for characters in hash_request)
