import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models import User
from app.schemas.users import RegisterUserRequest, UserResponse


def test_register_user_request_accepts_valid_data():
    request = RegisterUserRequest(
        email="user@example.com",
        password="password123",
    )

    assert request.email == "user@example.com"
    assert request.password == "password123"


def test_user_register_rejects_invalid_email():
    with pytest.raises(ValidationError):
        RegisterUserRequest(
            email="user",
            password="password123",
        )


def test_user_register_rejects_password_too_short():
    with pytest.raises(ValidationError):
        RegisterUserRequest(
            email="user@example.com",
            password="pass",
        )


def test_user_register_rejects_password_too_long():

    long_password = "a" * 129

    with pytest.raises(ValidationError):
        RegisterUserRequest(
            email="user@example.com",
            password=long_password,
        )


def test_user_response_validates_from_user_model():
    now = datetime.now(UTC)

    user = User(
        id=uuid.uuid4(),
        email="user@example.com",
        hashed_password="hashed_password",
        created_at=now,
        is_active=True,
    )

    response = UserResponse.model_validate(user)

    assert response.id == user.id
    assert response.email == user.email
    assert response.created_at == user.created_at
    assert response.is_active == user.is_active
    assert "hashed_password" not in response.model_dump()
