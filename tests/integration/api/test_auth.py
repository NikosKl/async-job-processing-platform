from fastapi import status


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
