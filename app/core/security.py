from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from jwt import InvalidTokenError
from pwdlib import PasswordHash

from app.core.config import settings
from app.domain.exceptions import InvalidAccessTokenError

_password_hash = PasswordHash.recommended()
DUMMY_HASH = _password_hash.hash("dummypassword")


def verify_password(plain_password: str, hashed_password: str) -> bool:

    return _password_hash.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:

    return _password_hash.hash(password)


def create_access_token(user_id: UUID, expires_delta: timedelta | None = None) -> str:
    if expires_delta is not None:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(
            minutes=settings.access_token_expire_minutes
        )

    payload = {
        "sub": str(user_id),
        "exp": expire,
    }

    encoded_jwt = jwt.encode(
        payload, settings.jwt_secret, algorithm=settings.jwt_algorithm
    )
    return encoded_jwt


def decode_access_token(token: str) -> UUID:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "exp"]},
        )

        sub = UUID(payload["sub"])
    except (InvalidTokenError, ValueError) as err:
        raise InvalidAccessTokenError() from err

    return sub
