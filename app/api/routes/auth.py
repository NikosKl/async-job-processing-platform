from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.db.session import get_db
from app.domain.exceptions import EmailAlreadyRegisteredError, InvalidCredentialsError
from app.schemas.auth import TokenResponse
from app.schemas.users import RegisterUserRequest, UserResponse
from app.services.auth_service import authenticate_user, register_user

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


@router.post("/login", response_model=TokenResponse)
def user_login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[Session, Depends(get_db)],
):
    try:
        authenticated_user = authenticate_user(
            db, email=form_data.username, password=form_data.password
        )
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    access_token = create_access_token(authenticated_user.id)
    return TokenResponse(access_token=access_token)
