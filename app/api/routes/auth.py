from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.exceptions import EmailAlreadyRegisteredError
from app.schemas.users import RegisterUserRequest, UserResponse
from app.services.auth_service import register_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
def user_registration(
    user: RegisterUserRequest, db: Annotated[Session, Depends(get_db)]
):
    try:
        created_user = register_user(db, user)
        return created_user
    except EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already registered"
        ) from None
