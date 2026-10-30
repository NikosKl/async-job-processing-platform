import asyncio

import httpx
import pytest

from app.domain.exceptions import (
    GitHubUnavailableError,
    InvalidRepositoryResponseError,
    RepositoryUnavailableError,
)
from app.domain.repository_analysis import RepositoryAnalysisResult
from app.providers.github import GitHubClient, github_client_context

# HANDLERS


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


def invalid_json_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        status_code=200,
        content="{invalid json}",
    )


def non_object_json_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(status_code=200, json=["fastapi", "sqlalchemy"])


def extra_fields_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        status_code=200,
        json={
            "owner": {"login": "fastapi"},
            "name": "fastapi",
            "stargazers_count": 100,
            "forks_count": 20,
            "open_issues_count": 5,
            "description": "A Python web framework",
            "language": "Python",
            "html_url": "https://github.com/fastapi/fastapi",
        },
    )


# TESTS


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

            with pytest.raises(RepositoryUnavailableError) as exc_info:
                await github_client.get_repository("fastapi", "fastapi")

            assert isinstance(exc_info.value.__cause__, httpx.HTTPStatusError)
            assert exc_info.value.__cause__.response.status_code == 404

    asyncio.run(run_test())


@pytest.mark.parametrize(
    "error_type", [httpx.ReadTimeout, httpx.ConnectTimeout, httpx.ConnectError]
)
def test_github_client_translates_transport_errors(error_type):

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise error_type("Connection failed", request=request)

    transport = httpx.MockTransport(timeout_handler)

    async def run_test():
        async with httpx.AsyncClient(transport=transport) as client:
            github_client = GitHubClient(client)

            with pytest.raises(GitHubUnavailableError) as exc_info:
                await github_client.get_repository("fastapi", "fastapi")

            assert isinstance(exc_info.value.__cause__, error_type)

    asyncio.run(run_test())


def test_github_client_raises_on_missing_required_field():
    transport = httpx.MockTransport(missing_field_handler)

    async def run_test():
        async with httpx.AsyncClient(transport=transport) as client:
            github_client = GitHubClient(client)

            with pytest.raises(InvalidRepositoryResponseError):
                await github_client.get_repository("fastapi", "fastapi")

    asyncio.run(run_test())


@pytest.mark.parametrize(
    "metric",
    ["stargazers_count", "forks_count", "open_issues_count"],
)
@pytest.mark.parametrize("invalid_value", [None, "100", True, 1.5, -1])
def test_github_client_rejects_invalid_metrics(metric, invalid_value):

    def handler(request: httpx.Request) -> httpx.Response:
        data = {
            "owner": {"login": "fastapi"},
            "name": "fastapi",
            "stargazers_count": 100,
            "forks_count": 20,
            "open_issues_count": 5,
            metric: invalid_value,
        }

        return httpx.Response(status_code=200, json=data)

    transport = httpx.MockTransport(handler)

    async def run_test():
        async with httpx.AsyncClient(transport=transport) as client:
            github_client = GitHubClient(client)

            with pytest.raises(InvalidRepositoryResponseError):
                await github_client.get_repository("fastapi", "fastapi")

    asyncio.run(run_test())


@pytest.mark.parametrize("field", ["login", "name"])
@pytest.mark.parametrize("invalid_value", [None, "", "   ", 123, True])
def test_github_client_rejects_invalid_identifiers(field, invalid_value):
    def handler(request: httpx.Request) -> httpx.Response:
        data = {
            "owner": {"login": invalid_value if field == "login" else "fastapi"},
            "name": invalid_value if field == "name" else "fastapi",
            "stargazers_count": 100,
            "forks_count": 20,
            "open_issues_count": 5,
        }

        return httpx.Response(status_code=200, json=data)

    transport = httpx.MockTransport(handler)

    async def run_test():
        async with httpx.AsyncClient(transport=transport) as client:
            github_client = GitHubClient(client)

            with pytest.raises(InvalidRepositoryResponseError):
                await github_client.get_repository("fastapi", "fastapi")

    asyncio.run(run_test())


@pytest.mark.parametrize("missing_field", ["owner", "login", "name"])
def test_github_client_rejects_missing_identifiers(missing_field):
    def handler(request: httpx.Request) -> httpx.Response:
        data = {
            "owner": {"login": "fastapi"},
            "name": "fastapi",
            "stargazers_count": 100,
            "forks_count": 20,
            "open_issues_count": 5,
        }

        if missing_field == "owner":
            del data["owner"]
        elif missing_field == "login":
            del data["owner"]["login"]
        else:
            del data["name"]

        return httpx.Response(status_code=200, json=data)

    transport = httpx.MockTransport(handler)

    async def run_test():
        async with httpx.AsyncClient(transport=transport) as client:
            github_client = GitHubClient(client)

            with pytest.raises(InvalidRepositoryResponseError):
                await github_client.get_repository("fastapi", "fastapi")

    asyncio.run(run_test())


def test_github_client_rejects_invalid_json():
    transport = httpx.MockTransport(invalid_json_handler)

    async def run_test():
        async with httpx.AsyncClient(transport=transport) as client:
            github_client = GitHubClient(client)

            with pytest.raises(InvalidRepositoryResponseError):
                await github_client.get_repository("fastapi", "fastapi")

    asyncio.run(run_test())


def test_github_client_rejects_non_object_json():
    transport = httpx.MockTransport(non_object_json_handler)

    async def run_test():
        async with httpx.AsyncClient(transport=transport) as client:
            github_client = GitHubClient(client)

            with pytest.raises(InvalidRepositoryResponseError):
                await github_client.get_repository("fastapi", "fastapi")

    asyncio.run(run_test())


def test_github_client_ignores_extra_fields():
    transport = httpx.MockTransport(extra_fields_handler)

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


@pytest.mark.parametrize("status_code", [500, 502, 503])
def test_github_client_raises_on_server_error(status_code):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=status_code, request=request)

    transport = httpx.MockTransport(handler)

    async def run_test():
        async with httpx.AsyncClient(transport=transport) as client:
            github_client = GitHubClient(client)

            with pytest.raises(GitHubUnavailableError) as exc_info:
                await github_client.get_repository("fastapi", "fastapi")

            assert isinstance(exc_info.value.__cause__, httpx.HTTPStatusError)
            assert exc_info.value.__cause__.response.status_code == status_code

    asyncio.run(run_test())


@pytest.mark.parametrize("status_code", [401, 403])
def test_github_client_preserves_other_http_errors(status_code):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=status_code, request=request)

    transport = httpx.MockTransport(handler)

    async def run_test():
        async with httpx.AsyncClient(transport=transport) as client:
            github_client = GitHubClient(client)

            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                await github_client.get_repository("fastapi", "fastapi")

            assert exc_info.value.response.status_code == status_code

    asyncio.run(run_test())


def test_github_client_sends_required_headers():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Accept"] == "application/vnd.github+json"
        assert request.headers["User-Agent"] == "async-job-processing-platform"
        assert request.headers["X-GitHub-Api-Version"] == "2026-03-10"

        json = {
            "owner": {"login": "fastapi"},
            "name": "fastapi",
            "stargazers_count": 100,
            "forks_count": 20,
            "open_issues_count": 5,
        }

        return httpx.Response(status_code=200, json=json, request=request)

    transport = httpx.MockTransport(handler)

    async def run_test():
        async with httpx.AsyncClient(transport=transport) as client:
            github_client = GitHubClient(client)

            await github_client.get_repository("fastapi", "fastapi")

    asyncio.run(run_test())


def test_github_client_sends_bearer_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer fake-token-123"

        json = {
            "owner": {"login": "fastapi"},
            "name": "fastapi",
            "stargazers_count": 100,
            "forks_count": 20,
            "open_issues_count": 5,
        }

        return httpx.Response(status_code=200, json=json, request=request)

    transport = httpx.MockTransport(handler)

    async def run_test():
        async with httpx.AsyncClient(transport=transport) as client:
            github_client = GitHubClient(client, token="fake-token-123")

            await github_client.get_repository("fastapi", "fastapi")

    asyncio.run(run_test())


def test_github_client_does_not_send_authorization_without_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "Authorization" not in request.headers

        json = {
            "owner": {"login": "fastapi"},
            "name": "fastapi",
            "stargazers_count": 100,
            "forks_count": 20,
            "open_issues_count": 5,
        }

        return httpx.Response(status_code=200, json=json, request=request)

    transport = httpx.MockTransport(handler)

    async def run_test():
        async with httpx.AsyncClient(transport=transport) as client:
            github_client = GitHubClient(client)

            await github_client.get_repository("fastapi", "fastapi")

    asyncio.run(run_test())


def test_github_client_does_not_send_authorization_with_empty_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "Authorization" not in request.headers

        json = {
            "owner": {"login": "fastapi"},
            "name": "fastapi",
            "stargazers_count": 100,
            "forks_count": 20,
            "open_issues_count": 5,
        }

        return httpx.Response(status_code=200, json=json, request=request)

    transport = httpx.MockTransport(handler)

    async def run_test():
        async with httpx.AsyncClient(transport=transport) as client:
            github_client = GitHubClient(client, token="")

            await github_client.get_repository("fastapi", "fastapi")

    asyncio.run(run_test())


def test_github_client_does_not_modify_client_headers():
    def handler(request: httpx.Request) -> httpx.Response:

        json = {
            "owner": {"login": "fastapi"},
            "name": "fastapi",
            "stargazers_count": 100,
            "forks_count": 20,
            "open_issues_count": 5,
        }

        return httpx.Response(status_code=200, json=json, request=request)

    transport = httpx.MockTransport(handler)

    async def run_test():
        async with httpx.AsyncClient(transport=transport) as client:
            original_headers = client.headers.copy()

            github_client = GitHubClient(client, token="fake-token-123")

            await github_client.get_repository("fastapi", "fastapi")

            assert client.headers == original_headers

    asyncio.run(run_test())


def test_github_client_context_uses_supplied_token():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer fake-token-123"

        json = {
            "owner": {"login": "fastapi"},
            "name": "fastapi",
            "stargazers_count": 100,
            "forks_count": 20,
            "open_issues_count": 5,
        }

        return httpx.Response(status_code=200, json=json, request=request)

    transport = httpx.MockTransport(handler)

    async def run_test():
        async with github_client_context(
            token="fake-token-123",
            transport=transport,
        ) as github:
            await github.get_repository("fastapi", "fastapi")

    asyncio.run(run_test())


def test_github_client_context_reuses_http_client():

    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)

        assert request.headers["Authorization"] == "Bearer fake-token-123"

        json = {
            "owner": {"login": "fastapi"},
            "name": "fastapi",
            "stargazers_count": 100,
            "forks_count": 20,
            "open_issues_count": 5,
        }

        return httpx.Response(status_code=200, json=json, request=request)

    transport = httpx.MockTransport(handler)

    async def run_test():
        async with github_client_context(
            token="fake-token-123",
            transport=transport,
        ) as github:
            original_client = github._client

            await github.get_repository("fastapi", "fastapi")
            await github.get_repository("sqlalchemy", "sqlalchemy")

        assert github._client is original_client
        assert len(requests) == 2

    asyncio.run(run_test())


def test_github_client_context_closes_http_client_on_exit():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer fake-token-123"

        json = {
            "owner": {"login": "fastapi"},
            "name": "fastapi",
            "stargazers_count": 100,
            "forks_count": 20,
            "open_issues_count": 5,
        }

        return httpx.Response(status_code=200, json=json, request=request)

    transport = httpx.MockTransport(handler)

    async def run_test():
        async with github_client_context(
            token="fake-token-123",
            transport=transport,
        ) as github:
            client = github._client
            assert not client.is_closed

            await github.get_repository("fastapi", "fastapi")

        assert client.is_closed

    asyncio.run(run_test())


def test_github_client_context_closes_http_client_on_exception():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer fake-token-123"

        json = {
            "owner": {"login": "fastapi"},
            "name": "fastapi",
            "stargazers_count": 100,
            "forks_count": 20,
            "open_issues_count": 5,
        }

        return httpx.Response(status_code=200, json=json, request=request)

    transport = httpx.MockTransport(handler)

    async def run_test():
        with pytest.raises(RuntimeError):
            async with github_client_context(
                token="fake-token-123",
                transport=transport,
            ) as github:
                client = github._client
                assert not client.is_closed

                raise RuntimeError("test failure")

        assert client.is_closed

    asyncio.run(run_test())


def test_github_client_context_creates_separate_http_clients():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer fake-token-123"

        json = {
            "owner": {"login": "fastapi"},
            "name": "fastapi",
            "stargazers_count": 100,
            "forks_count": 20,
            "open_issues_count": 5,
        }

        return httpx.Response(status_code=200, json=json, request=request)

    transport = httpx.MockTransport(handler)

    async def run_test():
        async with github_client_context(
            token="fake-token-123",
            transport=transport,
        ) as github:
            client_a = github._client

        async with github_client_context(
            token="fake-token-123",
            transport=transport,
        ) as github:
            client_b = github._client

        assert client_a is not client_b

    asyncio.run(run_test())
