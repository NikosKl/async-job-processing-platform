import re
from typing import Literal

from pydantic import BaseModel, field_validator

REPOSITORY_PATTERN = r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"


class RepositoryBatchAnalysisInput(BaseModel):
    repositories: list[str]

    @field_validator("repositories")
    @classmethod
    def repository_validator(cls, value: list[str]) -> list[str]:

        if len(value) < 1 or len(value) > 100:
            raise ValueError("Repositories must be between 1 and 100")

        for repository in value:
            if re.fullmatch(REPOSITORY_PATTERN, repository) is None:
                raise ValueError("Repository must use owner/repo format")

        normalized_repositories = [repository.lower() for repository in value]

        if len(normalized_repositories) != len(set(normalized_repositories)):
            raise ValueError("Duplicate repositories are not allowed")

        return value


class CreateJobRequest(BaseModel):
    type: Literal["repository_batch_analysis"]
    input: RepositoryBatchAnalysisInput
