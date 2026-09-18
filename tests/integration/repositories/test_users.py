from sqlalchemy import select

from app.models import User
from app.repositories.user import create_user, get_user_by_email


def test_get_user_by_email_success(db_session):
    user = User(
        email="user@example.com",
        hashed_password="hashed_password",
    )

    db_session.add(user)
    db_session.flush()

    returned_user = get_user_by_email(db_session, user.email)

    assert returned_user is not None
    assert returned_user.id == user.id
    assert returned_user.email == user.email


def test_get_user_by_email_returns_none_when_not_found(db_session):
    email = "user@example.com"

    returned_user = get_user_by_email(db_session, email)

    assert returned_user is None


def test_create_user_returns_user_with_all_values(db_session):
    email = "user@example.com"
    hashed_password = "fake_hashed_password"

    user = create_user(db_session, email, hashed_password)

    assert user.id is not None
    assert user.email == email
    assert user.hashed_password == hashed_password
    assert user.is_active is True
    assert user.created_at is not None

    stmt = select(User).where(User.email == email, User.id == user.id)
    retrieved_user = db_session.scalars(stmt).one_or_none()

    assert retrieved_user is not None
