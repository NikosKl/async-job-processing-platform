from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.domain.exceptions import IdempotencyConflictError, JobNotFoundError
from app.models import User
from app.schemas.jobs import CreateJobRequest, JobDetail
from app.services.job_service import get_owned_job, submit_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobDetail)
def get_job_detail(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    job_id: UUID,
):
    try:
        job = get_owned_job(db, job_id, current_user.id)
    except JobNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        ) from None
    return job


@router.post("", response_model=JobDetail, status_code=status.HTTP_201_CREATED)
def job_creation(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    request: CreateJobRequest,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=255)],
):
    try:
        job = submit_job(db, current_user.id, request, idempotency_key)
    except IdempotencyConflictError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Idempotency key conflict"
        ) from None
    return job
