import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password


def test_hash_password_returns_hash_different_from_plaintext():

    password = "password123"
    hashed_password = hash_password(password)

    assert hashed_password != password
    assert isinstance(hashed_password, str)


def test_verify_password_returns_true_for_correct_password():

    password = "password123"
    hashed_password = hash_password(password)

    assert verify_password(password, hashed_password) is True


def test_verify_password_returns_false_for_incorrect_password():

    password = "password123"
    hashed_password = hash_password(password)

    wrong_password = "random_password"

    assert verify_password(wrong_password, hashed_password) is False


def test_hash_password_produces_different_hashes_for_same_password():

    password = "password123"

    hashed_password_one = hash_password(password)
    hashed_password_two = hash_password(password)

    assert hashed_password_one != hashed_password_two
    assert verify_password(password, hashed_password_two) is True


def test_create_access_token_contains_user_id_as_subject():
    user_id = uuid.uuid4()

    token = create_access_token(user_id)

    decoded = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )

    assert decoded["sub"] == str(user_id)


def test_create_access_token_has_future_expiration():
    user_id = uuid.uuid4()

    token = create_access_token(user_id)

    decoded = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )

    assert decoded["exp"] > datetime.now(UTC).timestamp()


def test_create_access_token_uses_default_expiration():
    user_id = uuid.uuid4()

    token = create_access_token(user_id)

    decoded = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )

    now = datetime.now(UTC).timestamp()

    assert decoded["exp"] > now + timedelta(minutes=29).total_seconds()
    assert decoded["exp"] < now + timedelta(minutes=30).total_seconds()


def test_create_access_token_honors_expiration_override():
    user_id = uuid.uuid4()

    token = create_access_token(user_id, expires_delta=timedelta(minutes=2))

    decoded = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
    )

    now = datetime.now(UTC).timestamp()

    assert decoded["exp"] > now + timedelta(minutes=1, seconds=55).total_seconds()
    assert decoded["exp"] < now + timedelta(minutes=2).total_seconds()
