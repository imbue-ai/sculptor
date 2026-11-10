"""Tests for the terminal agent's periodic diff refresher."""

from collections.abc import Sequence

from sculptor.tasks.handlers.run_terminal_agent.diff_refresh import PeriodicDiffRefresher


def _make_refresher(
    fingerprints: Sequence[str | None], fired: list[int], interval_seconds: float = 0.0
) -> PeriodicDiffRefresher:
    """A refresher whose successive fingerprint checks return `fingerprints` in order."""
    remaining_fingerprints = iter(fingerprints)
    return PeriodicDiffRefresher(
        compute_fingerprint=lambda: next(remaining_fingerprints),
        on_change=lambda: fired.append(1),
        interval_seconds=interval_seconds,
    )


def test_first_tick_establishes_baseline_without_firing() -> None:
    fired: list[int] = []
    refresher = _make_refresher(["clean"], fired)

    refresher.tick()

    assert fired == []


def test_tick_fires_once_per_change() -> None:
    fired: list[int] = []
    refresher = _make_refresher(["clean", "edited", "edited"], fired)
    refresher.tick()  # baseline

    refresher.tick()
    assert len(fired) == 1

    # No further change — no further fire.
    refresher.tick()
    assert len(fired) == 1


def test_tick_rate_limits_by_interval() -> None:
    fired: list[int] = []
    refresher = _make_refresher(["clean", "edited"], fired, interval_seconds=3600.0)
    refresher.tick()  # baseline

    refresher.tick()  # within the interval — fingerprint not even computed

    assert fired == []


def test_failed_fingerprint_checks_never_fire() -> None:
    fired: list[int] = []
    refresher = _make_refresher([None, None], fired)

    refresher.tick()
    refresher.tick()

    assert fired == []


def test_failed_fingerprint_check_keeps_the_baseline() -> None:
    fired: list[int] = []
    refresher = _make_refresher(["clean", None, "edited"], fired)
    refresher.tick()  # baseline
    refresher.tick()  # failed check

    refresher.tick()

    assert fired == [1]
