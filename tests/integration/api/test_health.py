from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ready_success():
    mock_session = MagicMock(spec=Session)
    mock_session.scalar.return_value = 1

    def get_db_override():
        yield mock_session

    app.dependency_overrides[get_db] = get_db_override
    try:
        response = client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    finally:
        app.dependency_overrides.clear()


def test_health_ready_failure():
    mock_session = MagicMock(spec=Session)
    mock_session.scalar.side_effect = SQLAlchemyError("Database unavailable")

    def get_db_override():
        yield mock_session

    app.dependency_overrides[get_db] = get_db_override
    try:
        response = client.get("/health/ready")

        assert response.status_code == 503
        assert response.json() == {"detail": "Database unavailable"}
    finally:
        app.dependency_overrides.clear()
