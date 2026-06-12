"""Tests for the behaviour of errors in our system."""

from unittest.mock import Mock

from sculptor.foundation.async_monkey_patches import log_exception
from sculptor.foundation.errors import ImbueRuntimeException
from sculptor.foundation.fixtures import mock_loguru_log
from sculptor.foundation.serialization import SerializedException

_ = mock_loguru_log


def test_imbue_runtime_exceptions__logged_only_once(mock_loguru_log: Mock) -> None:
    try:
        raise ImbueRuntimeException("This is our exception")
    except ImbueRuntimeException as e:
        log_exception(e, "Ensuring  this is logged once")
        log_exception(e, "Should not be logged twice")

    assert len(mock_loguru_log.get_errors()) == 1, "This should not have logged again"


def test_imbue_runtime_exceptions__retain_logged_status(mock_loguru_log: Mock) -> None:
    try:
        raise ImbueRuntimeException("This is our exception")
    except ImbueRuntimeException as e:
        log_exception(e, "Ensuring  this is logged once")
        assert e._was_logged_by_log_exception
        sre = SerializedException.build(e)

    reconstructed_exception = sre.construct_instance()
    assert isinstance(reconstructed_exception, ImbueRuntimeException)
    assert reconstructed_exception._was_logged_by_log_exception
    log_exception(reconstructed_exception, "This should not actually log")

    assert len(mock_loguru_log.get_errors()) == 1, "This should not have logged again"
