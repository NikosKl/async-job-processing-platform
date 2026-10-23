import asyncio

import httpx
import pytest

from app.domain.repository_analysis import RepositoryAnalysisResult
from app.providers.github import GitHubClient


def successful_repo_handler(request: httpx.Request) -> httpx.Response:
    assert request.method == "GET"
    assert request.url.scheme == "https"
    assert request.url.host == "api.github.com"
    assert request.url.path == "/repos/fastapi/fastapi"

    return httpx.Response(
        status_code=200,
        json={
            "owner": {"login": "fastapi"},
            "name": "fastapi",
            "stargazers_count": 100,
            "forks_count": 20,
            "open_issues_count": 5,
        },
    )


def zero_metrics_handler(request: httpx.Request) -> httpx.Response:
    assert request.method == "GET"
    assert request.url.scheme == "https"
    assert request.url.host == "api.github.com"
    assert request.url.path == "/repos/fastapi/fastapi"

    return httpx.Response(
        status_code=200,
        json={
            "owner": {"login": "fastapi"},
            "name": "fastapi",
            "stargazers_count": 0,
            "forks_count": 0,
            "open_issues_count": 0,
        },
    )


def not_found_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        status_code=404,
        json={
            "message": "Not Found",
        },
    )


def timeout_handler(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("Read timeout", request=request)


def missing_field_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        status_code=200,
        json={
            "owner": {"login": "fastapi"},
            "name": "fastapi",
            "forks_count": 20,
            "open_issues_count": 5,
        },
    )


def test_github_client_sends_correct_request():
    transport = httpx.MockTransport(successful_repo_handler)

    async def run_test():
        async with httpx.AsyncClient(transport=transport) as client:
            github_client = GitHubClient(client)

            await github_client.get_repository("fastapi", "fastapi")

    asyncio.run(run_test())


def test_github_client_maps_repository_response():
    transport = httpx.MockTransport(successful_repo_handler)

    async def run_test():
        async with httpx.AsyncClient(transport=transport) as client:
            github_client = GitHubClient(client)

            result = await github_client.get_repository("fastapi", "fastapi")

        assert isinstance(result, RepositoryAnalysisResult)
        assert result.owner == "fastapi"
        assert result.repository == "fastapi"
        assert result.stars == 100
        assert result.forks == 20
        assert result.open_issues == 5

    asyncio.run(run_test())


def test_github_client_preserves_zero_metrics():
    transport = httpx.MockTransport(zero_metrics_handler)

    async def run_test():
        async with httpx.AsyncClient(transport=transport) as client:
            github_client = GitHubClient(client)

            result = await github_client.get_repository("fastapi", "fastapi")

        assert isinstance(result, RepositoryAnalysisResult)
        assert result.owner == "fastapi"
        assert result.repository == "fastapi"
        assert result.stars == 0
        assert result.forks == 0
        assert result.open_issues == 0

    asyncio.run(run_test())


def test_github_client_raises_on_404_response():
    transport = httpx.MockTransport(not_found_handler)

    async def run_test():
        async with httpx.AsyncClient(transport=transport) as client:
            github_client = GitHubClient(client)

            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                await github_client.get_repository("fastapi", "fastapi")

            assert exc_info.value.response.status_code == 404

    asyncio.run(run_test())


def test_github_client_propagates_timeout():
    transport = httpx.MockTransport(timeout_handler)

    async def run_test():
        async with httpx.AsyncClient(transport=transport) as client:
            github_client = GitHubClient(client)

            with pytest.raises(httpx.ReadTimeout):
                await github_client.get_repository("fastapi", "fastapi")

    asyncio.run(run_test())


def test_github_client_raises_on_missing_required_field():
    transport = httpx.MockTransport(missing_field_handler)

    async def run_test():
        async with httpx.AsyncClient(transport=transport) as client:
            github_client = GitHubClient(client)

            with pytest.raises(KeyError, match="stargazers_count"):
                await github_client.get_repository("fastapi", "fastapi")

    asyncio.run(run_test())
