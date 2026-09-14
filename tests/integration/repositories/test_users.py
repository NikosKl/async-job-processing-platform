from app.models import User
from app.repositories.user import get_user_by_email


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
