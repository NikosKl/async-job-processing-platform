import pytest

from app.core.security import verify_password
from app.domain.exceptions import EmailAlreadyRegisteredError
from app.repositories.user import get_user_by_email
from app.schemas.users import RegisterUserRequest
from app.services.auth_service import register_user


def test_register_user_creates_user_with_normalized_email(db_session):
    user = RegisterUserRequest(email="USer@example.COM", password="password123")

    registered_user = register_user(db_session, user)

    assert registered_user.id is not None
    assert registered_user.email == "user@example.com"
    assert registered_user.hashed_password != "password123"
    assert verify_password(user.password, registered_user.hashed_password)

    retrieved_user = get_user_by_email(db_session, registered_user.email)

    assert retrieved_user is not None


def test_register_user_raises_email_already_registered_when_email_exists(db_session):
    user = RegisterUserRequest(email="user@example.com", password="password123")

    registered_user = register_user(db_session, user)
    assert registered_user.id is not None

    new_user = RegisterUserRequest(email="USER@EXAMPLE.COM", password="password123")

    with pytest.raises(EmailAlreadyRegisteredError):
        register_user(db_session, new_user)

    check_user = get_user_by_email(db_session, registered_user.email)

    assert check_user is not None
    assert check_user.id == registered_user.id
