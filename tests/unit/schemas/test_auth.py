import pytest
from pydantic import ValidationError

from app.schemas.auth import TokenResponse


def test_token_response_defaults_token_type_to_bearer():
    response = TokenResponse(access_token="test-token")

    assert response.token_type == "bearer"


def test_token_response_rejects_invalid_token_type():
    with pytest.raises(ValidationError):
        TokenResponse.model_validate(
            {
                "access_token": "test-token",
                "token_type": "Basic",
            }
        )
