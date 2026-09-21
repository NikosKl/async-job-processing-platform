import jwt
from fastapi import status

from app.core.config import settings
from app.core.security import hash_password
from app.repositories.user import create_user


def test_register_success_returns_201(client):
    payload = {
        "email": "user@example.com",
        "password": "password123",
    }

    response = client.post("/auth/register", json=payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["email"] == payload["email"]
    assert "id" in data
    assert "password" not in data
    assert "hashed_password" not in data


def test_register_user_with_different_email_casing_returns_409(client):
    payload = {
        "email": "user@example.com",
        "password": "password123",
    }

    first_response = client.post("/auth/register", json=payload)
    assert first_response.status_code == status.HTTP_201_CREATED

    second_payload = {
        "email": "USER@EXAMPLE.COM",
        "password": "new_password123",
    }

    second_response = client.post("/auth/register", json=second_payload)
    assert second_response.status_code == status.HTTP_409_CONFLICT
    assert second_response.json() == {"detail": "Email already registered"}


def test_register_user_with_invalid_input_returns_422(client):
    payload = {
        "email": "user@example",
        "password": "password123",
    }

    response = client.post("/auth/register", json=payload)
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_login_returns_access_token_for_valid_credentials(client, db_session):
    email = "user@example.com"
    password = "password123"

    user = create_user(db_session, email=email, hashed_password=hash_password(password))

    response = client.post(
        "/auth/login", data={"username": email, "password": password}
    )

    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

    decoded_data = jwt.decode(
        data["access_token"], settings.jwt_secret, settings.jwt_algorithm
    )
    assert decoded_data["sub"] == str(user.id)


def test_login_accepts_uppercase_email(client, db_session):
    email = "user@example.com"
    password = "password123"

    create_user(db_session, email=email, hashed_password=hash_password(password))

    response = client.post(
        "/auth/login", data={"username": "USER@EXAMPLE.COM", "password": password}
    )

    assert response.status_code == status.HTTP_200_OK


def test_login_returns_401_for_wrong_password(client, db_session):
    email = "user@example.com"
    password = "password123"

    create_user(db_session, email=email, hashed_password=hash_password(password))

    response = client.post(
        "/auth/login", data={"username": email, "password": "wrong_password"}
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    assert response.headers["WWW-Authenticate"] == "Bearer"
    data = response.json()
    assert data["detail"] == "Incorrect username or password"


def test_login_returns_401_for_unknown_email(client, db_session):
    email = "user@example.com"
    password = "password123"

    create_user(db_session, email=email, hashed_password=hash_password(password))

    response = client.post(
        "/auth/login",
        data={"username": "wrong_email@example.com", "password": password},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED

    assert response.headers["WWW-Authenticate"] == "Bearer"
    data = response.json()
    assert data["detail"] == "Incorrect username or password"
