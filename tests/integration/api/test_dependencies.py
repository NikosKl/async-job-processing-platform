import uuid
from typing import Annotated

from fastapi import Depends
from starlette.status import HTTP_200_OK, HTTP_401_UNAUTHORIZED

from app.api.dependencies import get_current_user
from app.core.security import create_access_token, hash_password
from app.main import app as fastapi_app
from app.models import User
from app.repositories.user import create_user


@fastapi_app.get("/test/current-user")
def current_user_endpoint(
    current_user: Annotated[User, Depends(get_current_user)],
):
    return {"id": str(current_user.id)}


def test_get_current_user_returns_user_for_valid_token(db_session, client):
    email = "user@example.com"
    password = "password123"

    user = create_user(db_session, email=email, hashed_password=hash_password(password))

    token = create_access_token(user.id)

    response = client.get(
        "/test/current-user", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == HTTP_200_OK
    assert response.json() == {"id": str(user.id)}


def test_get_current_user_returns_401_for_invalid_token(client):
    invalid_token = "not.a.jwt"

    response = client.get(
        "/test/current-user", headers={"Authorization": f"Bearer {invalid_token}"}
    )
    assert response.status_code == HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "Invalid Token"}
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_get_current_user_returns_401_for_missing_user(client):
    user_id = uuid.uuid4()

    token = create_access_token(user_id)

    response = client.get(
        "/test/current-user", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "Invalid Token"}
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_get_current_user_returns_401_for_inactive_user(db_session, client):
    email = "user@example.com"
    password = "password123"

    user = create_user(db_session, email=email, hashed_password=hash_password(password))

    user.is_active = False
    db_session.flush()

    token = create_access_token(user.id)

    response = client.get(
        "/test/current-user", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == HTTP_401_UNAUTHORIZED
    assert response.json() == {"detail": "Invalid Token"}
    assert response.headers["WWW-Authenticate"] == "Bearer"
