from app.services.job_execution_service import run_fake_repository_analysis


def test_run_fake_repository_analysis_preserves_repository_identifiers():

    result = run_fake_repository_analysis("fastapi", "example-fastapi")

    assert result.owner == "fastapi"
    assert result.repository == "example-fastapi"


def test_run_fake_repository_analysis_returns_zero_placeholder_metrics():
    result = run_fake_repository_analysis("fastapi", "example-fastapi")

    assert result.stars == 0
    assert result.forks == 0
    assert result.open_issues == 0


def test_run_fake_repository_analysis_returns_equal_but_distinct_results():
    result_a = run_fake_repository_analysis("fastapi", "example-fastapi")
    result_b = run_fake_repository_analysis("fastapi", "example-fastapi")

    assert result_a == result_b
    assert result_a is not result_b
