from sculptor.web.access_log_filter import should_suppress_access_log


def test_should_suppress_only_healthy_polling_routes() -> None:
    message = '127.0.0.1:63270 - "GET /api/v1/health HTTP/1.1" 200'
    assert should_suppress_access_log(message) is True


def test_should_not_suppress_failures_even_on_polled_routes() -> None:
    message = '127.0.0.1:63270 - "GET /api/v1/health HTTP/1.1" 500'
    assert should_suppress_access_log(message) is False


def test_should_not_suppress_other_routes() -> None:
    message = '127.0.0.1:63270 - "GET /api/v1/tasks HTTP/1.1" 200'
    assert should_suppress_access_log(message) is False
