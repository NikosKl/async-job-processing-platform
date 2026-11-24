import pytest

from app.domain.exceptions import GitHubRateLimitError


def test_github_rate_limit_error_preserves_message_and_delay():
    rate_limit = GitHubRateLimitError(retry_after_seconds=30.0)

    assert rate_limit.retry_after_seconds == 30.0
    assert str(rate_limit) == "GitHub rate limit exceeded: 30.0 seconds"


@pytest.mark.parametrize(
    "invalid_delay",
    [
        pytest.param(-1.0, id="negative"),
        pytest.param(float("inf"), id="positive-infinity"),
        pytest.param(float("-inf"), id="negative-infinity"),
        pytest.param(float("nan"), id="Nan"),
    ],
)
def test_github_rate_limit_error_rejects_invalid_delay(invalid_delay):
    with pytest.raises(ValueError):
        GitHubRateLimitError(retry_after_seconds=invalid_delay)


def test_github_rate_limit_error_accepts_zero_delay():
    rate_limit = GitHubRateLimitError(retry_after_seconds=0.0)
    assert rate_limit.retry_after_seconds == 0.0
