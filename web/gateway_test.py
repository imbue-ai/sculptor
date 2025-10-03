from unittest.mock import MagicMock

import pytest

from sculptor.config.settings import SculptorSettings
from sculptor.web.app import APP
from sculptor.web.gateway import get_httpx_client

FAKE_IMBUE_GATEWAY_BASE_URL = "https://imbue-gateway.ai/api/v1/"


@pytest.fixture
def mock_httpx_client():
    mock_client = MagicMock()
    mock_client.request = MagicMock()
    return mock_client


@pytest.fixture
def override_httpx_client(mock_httpx_client):
    APP.dependency_overrides[get_httpx_client] = lambda: mock_httpx_client
    yield mock_httpx_client
    APP.dependency_overrides.pop(get_httpx_client, None)


@pytest.fixture
def test_settings(test_settings: SculptorSettings) -> SculptorSettings:
    return test_settings.model_copy(update={"IMBUE_GATEWAY_BASE_URL": FAKE_IMBUE_GATEWAY_BASE_URL})


def test_gateway_proxy_forwards_requests(client, override_httpx_client, test_services):
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.is_server_error = False
    mock_response.headers = {"content-type": "application/json", "x-custom-response": "test"}
    mock_response.content = b'{"result": "success"}'
    override_httpx_client.request.return_value = mock_response
    response = client.post("/gateway/foo?bar=baz", headers={"X-Custom-Header": "test-value"}, json={"data": "test"})
    assert response.status_code == 201
    assert response.json() == {"result": "success"}
    assert response.headers.get("x-custom-response") == "test"
    call_args = override_httpx_client.request.call_args[1]
    assert call_args["headers"].get("x-custom-header") == "test-value"
    assert call_args["method"] == "POST"
    assert call_args["url"] == f"{FAKE_IMBUE_GATEWAY_BASE_URL}foo?bar=baz"
    assert call_args["content"] == b'{"data":"test"}'


def test_gateway_proxy_rewrites_internal_redirects(client, override_httpx_client, test_services):
    mock_response = MagicMock()
    mock_response.status_code = 302
    mock_response.headers = {"location": f"{FAKE_IMBUE_GATEWAY_BASE_URL}auth/callback?code=123&state=abc"}
    mock_response.is_server_error = False
    mock_response.content = b""
    override_httpx_client.request.return_value = mock_response
    response = client.get("/gateway/foo", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == f"{client.base_url}/gateway/auth/callback?code=123&state=abc"


def test_gateway_proxy_does_not_rewrite_external_redirects(client, override_httpx_client, test_services):
    mock_response = MagicMock()
    mock_response.status_code = 302
    mock_response.headers = {"location": "https://example.com/callback?code=123&state=abc"}
    mock_response.is_server_error = False
    mock_response.content = b""
    override_httpx_client.request.return_value = mock_response
    response = client.get("/gateway/foo", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "https://example.com/callback?code=123&state=abc"
