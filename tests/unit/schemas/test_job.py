import pytest
from pydantic import ValidationError

from app.schemas.jobs import CreateJobRequest, RepositoryBatchAnalysisInput


def test_repository_batch_analysis_accepts_valid_repos():
    input_data = RepositoryBatchAnalysisInput(
        repositories=[
            "fastapi/fastapi",
            "sqlalchemy/sqlalchemy",
        ]
    )

    assert input_data.repositories == [
        "fastapi/fastapi",
        "sqlalchemy/sqlalchemy",
    ]


def test_repository_batch_analysis_rejects_invalid_repos():
    with pytest.raises(ValidationError):
        RepositoryBatchAnalysisInput(
            repositories=["https://github.com/fastapi/fastapi"]
        )


def test_repository_batch_analysis_input_rejects_duplicate_repos():
    with pytest.raises(ValidationError):
        RepositoryBatchAnalysisInput(
            repositories=[
                "fastapi/fastapi",
                "FastAPI/FastAPI",
            ]
        )


def test_repository_batch_analysis_input_rejects_more_than_100_repos():
    with pytest.raises(ValidationError):
        RepositoryBatchAnalysisInput(
            repositories=[f"owner/repo{i}" for i in range(101)]
        )


def test_repository_batch_analysis_input_rejects_empty_repo():
    with pytest.raises(ValidationError):
        RepositoryBatchAnalysisInput(repositories=[])


def test_repository_batch_analysis_input_rejects_invalid_repo_format():
    with pytest.raises(ValidationError):
        RepositoryBatchAnalysisInput(repositories=["fastapi/fastapi/repo"])


def test_create_job_request_accepts_valid_request():
    request = CreateJobRequest(
        type="repository_batch_analysis",
        input=RepositoryBatchAnalysisInput(
            repositories=["fastapi/fastapi", "sqlalchemy/sqlalchemy"]
        ),
    )

    assert request.type == "repository_batch_analysis"
    assert request.input == RepositoryBatchAnalysisInput(
        repositories=["fastapi/fastapi", "sqlalchemy/sqlalchemy"]
    )


def test_create_job_request_rejects_invalid_job_type():
    with pytest.raises(ValidationError):
        CreateJobRequest.model_validate(
            {
                "type": "invalid_job_type",
                "input": {
                    "repositories": ["fastapi/fastapi", "sqlalchemy/sqlalchemy"],
                },
            }
        )


def test_create_job_request_rejects_missing_input():
    with pytest.raises(ValidationError):
        CreateJobRequest.model_validate({"type": "repository_batch_analysis"})


def test_create_job_request_rejects_invalid_input():
    with pytest.raises(ValidationError):
        CreateJobRequest.model_validate(
            {
                "input": "repository_batch_analysis",
                "repositories": ["https://github.com/fastapi/fastapi"],
            }
        )
