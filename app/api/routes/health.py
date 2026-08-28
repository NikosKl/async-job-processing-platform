from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette import status

from app.db.session import get_db

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/live")
def live_check():
    return {"status": "ok"}


@router.get("/ready")
def readiness_check(db: Annotated[Session, Depends(get_db)]):
    try:
        db.scalar(select(1))
        return {"status": "ok"}
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from exc
