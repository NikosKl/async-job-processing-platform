import hashlib
import json

from app.schemas.jobs import CreateJobRequest


def normalize_job_request(request: CreateJobRequest) -> dict:
    return {
        "type": request.type,
        "input": {
            "repositories": [
                repository.lower() for repository in request.input.repositories
            ]
        },
    }


def hash_job_request(request: CreateJobRequest) -> str:

    normalized_request = normalize_job_request(request)

    json_request = json.dumps(
        normalized_request,
        sort_keys=True,
        separators=(",", ":"),
    )

    request_hash = hashlib.sha256(json_request.encode("utf-8")).hexdigest()
    return request_hash
