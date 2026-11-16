from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.domain.repository_analysis import classify_repository_activity


def test_classify_repository_activity_recent_push_is_high():
    reference_time = datetime(2026, 11, 5, 16, 30, tzinfo=UTC)
    last_push_at = datetime(2026, 10, 31, 14, 30, tzinfo=UTC)

    result = classify_repository_activity(last_push_at, reference_time)

    assert result == "HIGH"


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        pytest.param(timedelta(days=30), "HIGH", id="exactly-30-days"),
        pytest.param(timedelta(days=30, seconds=1), "MEDIUM", id="over-30-days"),
    ],
)
def test_classify_repository_activity_30_day_boundary(age, expected):
    reference_time = datetime(2026, 11, 5, 16, 30, tzinfo=UTC)
    last_push_at = reference_time - age

    result = classify_repository_activity(last_push_at, reference_time)

    assert result == expected


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        pytest.param(timedelta(days=180), "MEDIUM", id="exactly-180-days"),
        pytest.param(timedelta(days=180, seconds=1), "LOW", id="over-180-days"),
    ],
)
def test_classify_repository_activity_180_day_boundary(age, expected):
    reference_time = datetime(2026, 11, 5, 16, 30, tzinfo=UTC)
    last_push_at = reference_time - age

    result = classify_repository_activity(last_push_at, reference_time)

    assert result == expected


def test_classify_repository_activity_missing_push_returns_none():
    reference_time = datetime(2026, 11, 5, 16, 30, tzinfo=UTC)
    last_push_at = None

    result = classify_repository_activity(last_push_at, reference_time)

    assert result is None


def test_classify_repository_activity_future_push_is_high():
    reference_time = datetime(2026, 11, 5, 16, 30, tzinfo=UTC)
    last_push_at = reference_time + timedelta(days=1)

    result = classify_repository_activity(last_push_at, reference_time)

    assert result == "HIGH"


def test_classify_repository_activity_equivalent_timezone_offsets():

    reference_time = datetime(2026, 11, 5, 16, 30, tzinfo=UTC)

    last_push_at_utc = datetime(2026, 11, 5, 16, 30, tzinfo=UTC)

    last_push_at_plus_2 = datetime(
        2026, 11, 5, 18, 30, tzinfo=timezone(timedelta(hours=2))
    )

    result_utc = classify_repository_activity(last_push_at_utc, reference_time)
    result_plus_2 = classify_repository_activity(last_push_at_plus_2, reference_time)

    assert result_utc == result_plus_2


@pytest.mark.parametrize(
    ("last_push_at", "reference_time"),
    [
        pytest.param(
            datetime(2026, 11, 5, 12, 0, tzinfo=UTC),
            datetime(2026, 11, 10, 12, 0),
            id="naive-reference-time",
        ),
        pytest.param(
            datetime(2026, 11, 5, 12, 0),
            datetime(2026, 11, 10, 12, 0, tzinfo=UTC),
            id="naive-last-push",
        ),
    ],
)
def test_classify_repository_activity_rejects_naive_timestamps(
    last_push_at, reference_time
):

    with pytest.raises(ValueError):
        classify_repository_activity(last_push_at, reference_time)
