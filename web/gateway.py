"""
Gateway proxy functionality for forwarding requests to imbue-gateway.

Only to be used for simple non-streaming requests.

"""

from urllib.parse import urljoin
from urllib.parse import urlparse
from urllib.parse import urlunparse

import httpx
from anyio import from_thread
from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from fastapi import Response
from loguru import logger

from sculptor.config.settings import SculptorSettings
from sculptor.web.middleware import DecoratedAPIRouter
from sculptor.web.middleware import add_logging_context
from sculptor.web.middleware import get_settings

router = DecoratedAPIRouter(decorator=add_logging_context)


def maybe_rewrite_location_header(
    request: Request, response: httpx.Response, imbue_gateway_base_url: str
) -> dict[str, str]:
    """
    Rewrite the Location header for redirects within the imbue-gateway domain to go through Sculptor again.

    """
    response_headers = dict(response.headers)
    if "location" not in response_headers or response.status_code not in [301, 302, 303, 307, 308]:
        return response_headers

    location = response_headers["location"]
    parsed = urlparse(location)
    gateway_parsed = urlparse(imbue_gateway_base_url)

    # Check if the redirect is to the same gateway host
    if parsed.netloc == gateway_parsed.netloc and parsed.path.startswith(gateway_parsed.path):
        relative_path = parsed.path[len(gateway_parsed.path) :].lstrip("/")
        # Reconstruct the URL to go through Sculptor's proxy.
        sculptor_scheme = request.url.scheme
        sculptor_netloc = request.url.netloc
        sculptor_path = f"/gateway/{relative_path}"
        # Keep query string and fragment if present.
        rewritten = urlunparse(
            (sculptor_scheme, sculptor_netloc, sculptor_path, parsed.params, parsed.query, parsed.fragment)
        )
        logger.debug(f"Rewriting redirect from {location} to {rewritten}")
        response_headers["location"] = rewritten
    return response_headers


def get_httpx_client() -> httpx.Client:
    return httpx.Client()


@router.api_route("/gateway/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
def gateway_proxy(
    request: Request,
    path: str,
    settings: SculptorSettings = Depends(get_settings),
    httpx_client: httpx.Client = Depends(get_httpx_client),
) -> Response:
    """
    Proxy requests to the imbue-gateway endpoints.

    We do this to:
        - avoid having to configure imbue-gateway twice (once for the sculptor backend and once for the frontend)
        - not making the setup more complicated for the frontend

    """
    target_url = urljoin(settings.IMBUE_GATEWAY_BASE_URL, path)
    if request.url.query:
        target_url += f"?{request.url.query}"
    headers = dict(request.headers)
    # Remove host header as it should be set by httpx
    headers.pop("host", None)
    body = None
    if request.method in ["POST", "PUT", "PATCH"]:
        # There's no synchronous way to read the body in FastAPI/Starlette.
        body = from_thread.run(request.body)
    try:
        response = httpx_client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
            follow_redirects=False,
            timeout=httpx.Timeout(16.0),
        )
        if response.is_server_error:
            raise HTTPException(status_code=502, detail="Bad gateway")
        response_headers = maybe_rewrite_location_header(request, response, settings.IMBUE_GATEWAY_BASE_URL)
        response_headers.pop("connection", None)
        response_headers.pop("keep-alive", None)
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=response_headers,
        )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Gateway timeout")
