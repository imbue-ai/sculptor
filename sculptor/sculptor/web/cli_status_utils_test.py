from sculptor.web.cli_status_utils import CliStatusError
from sculptor.web.cli_status_utils import classify_cli_error

# --- classify_cli_error: not_authenticated ---


def test_classify_cli_error_auth_keyword_returns_not_authenticated() -> None:
    assert classify_cli_error("error: auth required") == "not_authenticated"


def test_classify_cli_error_not_logged_into_returns_not_authenticated() -> None:
    assert classify_cli_error("You are not logged into any GitHub hosts") == "not_authenticated"


def test_classify_cli_error_not_logged_returns_not_authenticated() -> None:
    assert classify_cli_error("error: not logged in. Run `gh auth login`") == "not_authenticated"


def test_classify_cli_error_log_in_returns_not_authenticated() -> None:
    assert classify_cli_error("Please log in to continue") == "not_authenticated"


def test_classify_cli_error_authentication_keyword_returns_not_authenticated() -> None:
    assert classify_cli_error("authentication failed for github.com") == "not_authenticated"


def test_classify_cli_error_token_keyword_returns_not_authenticated() -> None:
    assert classify_cli_error("invalid token: token has been revoked") == "not_authenticated"


def test_classify_cli_error_401_returns_not_authenticated() -> None:
    assert classify_cli_error("HTTP 401 Unauthorized") == "not_authenticated"


# --- classify_cli_error: no_access ---


def test_classify_cli_error_403_returns_no_access() -> None:
    assert classify_cli_error("HTTP 403 Forbidden") == "no_access"


def test_classify_cli_error_forbidden_returns_no_access() -> None:
    assert classify_cli_error("Resource not accessible (forbidden)") == "no_access"


def test_classify_cli_error_access_denied_returns_no_access() -> None:
    assert classify_cli_error("access denied for this project") == "no_access"


def test_classify_cli_error_permission_returns_no_access() -> None:
    assert classify_cli_error("permission denied accessing this repo") == "no_access"


# --- classify_cli_error: network_error ---


def test_classify_cli_error_could_not_resolve_returns_network_error() -> None:
    """DNS resolution failure should be network_error, not no_access."""
    assert classify_cli_error("could not resolve host: github.com") == "network_error"


def test_classify_cli_error_no_such_host_returns_network_error() -> None:
    assert classify_cli_error("dial tcp: lookup github.com: no such host") == "network_error"


def test_classify_cli_error_dns_keyword_returns_network_error() -> None:
    assert classify_cli_error("DNS lookup failed for api.github.com") == "network_error"


# --- classify_cli_error: rate_limited ---


def test_classify_cli_error_primary_rate_limit_returns_rate_limited() -> None:
    """GitHub's primary GraphQL limit comes back as HTTP 403 'API rate limit exceeded'."""
    assert classify_cli_error("HTTP 403: API rate limit exceeded for user ID 12345") == "rate_limited"


def test_classify_cli_error_graphql_rate_limit_returns_rate_limited() -> None:
    assert classify_cli_error("GraphQL: API rate limit exceeded (repository.pullRequests)") == "rate_limited"


def test_classify_cli_error_secondary_rate_limit_returns_rate_limited() -> None:
    assert classify_cli_error("You have exceeded a secondary rate limit. Please wait a few minutes.") == "rate_limited"


def test_classify_cli_error_ratelimit_header_returns_rate_limited() -> None:
    assert classify_cli_error("x-ratelimit-remaining: 0") == "rate_limited"


def test_classify_cli_error_rate_limit_takes_priority_over_403() -> None:
    """A rate-limit 403 must classify as rate_limited, not no_access."""
    assert classify_cli_error("HTTP 403 Forbidden: API rate limit exceeded") == "rate_limited"


# --- classify_cli_error: transient ---


def test_classify_cli_error_http_5xx_returns_transient() -> None:
    assert classify_cli_error("HTTP 502 Bad Gateway") == "transient"


def test_classify_cli_error_http_500_returns_transient() -> None:
    assert classify_cli_error("HTTP/1.1 500 Internal Server Error") == "transient"


def test_classify_cli_error_status_503_returns_transient() -> None:
    assert classify_cli_error("status: 503 Service Unavailable") == "transient"


def test_classify_cli_error_timeout_returns_transient() -> None:
    assert classify_cli_error("connection timeout after 30s") == "transient"


def test_classify_cli_error_connection_refused_returns_transient() -> None:
    assert classify_cli_error("dial tcp 10.0.0.1:443: connection refused") == "transient"


def test_classify_cli_error_bare_number_512_does_not_match_5xx() -> None:
    """A bare 3-digit number starting with 5 should NOT be treated as an HTTP 5xx."""
    assert classify_cli_error("found 512 pull requests") == "transient"


def test_classify_cli_error_unknown_error_defaults_to_transient() -> None:
    assert classify_cli_error("something completely unexpected happened") == "transient"


def test_classify_cli_error_empty_stderr_defaults_to_transient() -> None:
    assert classify_cli_error("") == "transient"


# --- classify_cli_error: usage errors ---


def test_classify_cli_error_unknown_json_field_returns_transient() -> None:
    """gh rejects an unknown --json field and prints a field list containing
    "author"; that must not read as not_authenticated (the bug this fixes)."""
    stderr = 'Unknown JSON field: "reviewThreads"\nAvailable fields:\n  author\n  authorAssociation\n  state\n'
    assert classify_cli_error(stderr) == "transient"


def test_classify_cli_error_unknown_json_field_is_not_not_authenticated() -> None:
    """The 'author'/'authorAssociation' help text must never classify as auth."""
    stderr = 'Unknown JSON field: "bogus"\nAvailable fields:\n  author\n  authorAssociation\n'
    assert classify_cli_error(stderr) != "not_authenticated"


def test_classify_cli_error_unknown_flag_returns_transient() -> None:
    assert classify_cli_error("unknown flag: --jsom") == "transient"


def test_classify_cli_error_author_substring_alone_does_not_match_auth() -> None:
    """A bare "author" token (no real auth keyword) must not match the auth check."""
    assert classify_cli_error("returned field author for the pull request") != "not_authenticated"


# --- classify_cli_error: priority ---


def test_classify_cli_error_auth_takes_priority_over_403() -> None:
    """When stderr contains both auth and 403 keywords, auth wins (checked first)."""
    assert classify_cli_error("401 authentication failed, 403 forbidden") == "not_authenticated"


# --- CliStatusError ---


def test_cli_status_error_preserves_category() -> None:
    error = CliStatusError("not_authenticated", "not logged into any hosts")
    assert error.category == "not_authenticated"


def test_cli_status_error_stderr_is_message() -> None:
    """str(error) should return the stderr, so it can be passed as error_message."""
    error = CliStatusError("no_access", "HTTP 403 Forbidden")
    assert str(error) == "HTTP 403 Forbidden"
