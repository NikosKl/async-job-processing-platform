import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.domain.exceptions import InvalidAccessTokenError


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


def test_decode_access_token_returns_user_id_for_valid_token():
    user_id = uuid.uuid4()

    token = create_access_token(user_id)
    decoded_user_id = decode_access_token(token)

    assert decoded_user_id == user_id


def test_decode_access_token_rejects_expired_token():
    user_id = uuid.uuid4()

    token = create_access_token(user_id, expires_delta=timedelta(minutes=-1))
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token)


def test_decode_access_token_rejects_wrongly_signed_token():
    sub = uuid.uuid4()
    exp = datetime.now(UTC) + timedelta(minutes=30)

    token = {
        "sub": str(sub),
        "exp": exp,
    }

    wrong_secret = "this-is-a-wrong-secret-that-is-long-enough"

    signed_token = jwt.encode(token, wrong_secret, algorithm=settings.jwt_algorithm)

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(signed_token)


def test_decode_access_token_rejects_malformed_token():
    malformed_token = "not.a.jwt"

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(malformed_token)


def test_decode_access_token_rejects_missing_sub():
    payload = {
        "exp": datetime.now(UTC) + timedelta(minutes=30),
    }

    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token)


def test_decode_access_token_rejects_missing_exp():
    payload = {
        "sub": str(uuid.uuid4()),
    }

    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token)


def test_decode_access_token_rejects_non_uuid_sub():
    payload = {
        "sub": "wrong_type_sub",
        "exp": datetime.now(UTC) + timedelta(minutes=30),
    }

    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token)
