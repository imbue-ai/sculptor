import pytest

from sculptor.services.task_service.concurrent_implementation import DebounceCache


def test_size_compliance() -> None:
    cache = DebounceCache(interval_seconds=5, max_items=10)

    for item in range(60):
        cache.add(item, item)

    assert len(cache.cache) == 10


@pytest.fixture
def specimen():
    return DebounceCache(interval_seconds=5, max_items=10)


def test_debounce__one_event_passes(specimen: DebounceCache) -> None:
    assert specimen.debounce(Exception, 0)


def test_debounce__duplicate_event_debounced(specimen: DebounceCache) -> None:
    specimen.debounce(Exception, 0)
    assert not specimen.debounce(Exception, 4.99999)


def test_debounce__duplicate_event_out_of_interval(specimen: DebounceCache) -> None:
    specimen.debounce(Exception, 0)
    assert specimen.debounce(Exception, 5.000002)


def test_debounce_duplicate_three_events(specimen: DebounceCache) -> None:
    specimen.debounce(Exception, 0)
    assert not specimen.debounce(Exception, 4.99999)
    # The previous event should not reset the timer on Exception.
    assert specimen.debounce(Exception, 5.000002)


def test_debounce_two_different_events(specimen: DebounceCache, old_exception=Exception) -> None:
    specimen.debounce(old_exception, 0)

    class Exception(old_exception):
        """Creating a derived class here with the same name"""

    # This should NOT debounce, because Exception is not Exception
    assert specimen.debounce(Exception, 4.99999)
