"""Tests for the terminal agent's periodic diff refresher."""

from pathlib import Path

from sculptor.tasks.handlers.run_terminal_agent.diff_refresh import PeriodicDiffRefresher


def _make_refresher(repo: Path, fired: list[int], interval_seconds: float = 0.0) -> PeriodicDiffRefresher:
    return PeriodicDiffRefresher(
        working_directory=repo,
        on_change=lambda: fired.append(1),
        interval_seconds=interval_seconds,
    )


def test_first_tick_establishes_baseline_without_firing(initial_commit_repo: tuple[Path, str]) -> None:
    repo, _ = initial_commit_repo
    fired: list[int] = []
    refresher = _make_refresher(repo, fired)

    refresher.tick()

    assert fired == []


def test_tick_fires_once_per_change(initial_commit_repo: tuple[Path, str]) -> None:
    repo, _ = initial_commit_repo
    fired: list[int] = []
    refresher = _make_refresher(repo, fired)
    refresher.tick()  # baseline

    (repo / "new_file.txt").write_text("hello")
    refresher.tick()
    assert len(fired) == 1

    # No further change — no further fire.
    refresher.tick()
    assert len(fired) == 1


def test_tick_rate_limits_by_interval(initial_commit_repo: tuple[Path, str]) -> None:
    repo, _ = initial_commit_repo
    fired: list[int] = []
    refresher = _make_refresher(repo, fired, interval_seconds=3600.0)
    refresher.tick()  # baseline

    (repo / "new_file.txt").write_text("hello")
    refresher.tick()  # within the interval — fingerprint not even computed

    assert fired == []


def test_tick_swallows_git_failure(tmp_path: Path) -> None:
    fired: list[int] = []
    refresher = _make_refresher(tmp_path / "does-not-exist", fired)

    refresher.tick()
    refresher.tick()

    assert fired == []


def test_force_fires_unconditionally_and_rebases(initial_commit_repo: tuple[Path, str]) -> None:
    repo, _ = initial_commit_repo
    fired: list[int] = []
    refresher = _make_refresher(repo, fired)
    refresher.tick()  # baseline

    refresher.force()
    assert len(fired) == 1

    # force() rebased the fingerprint, so an unchanged tree does not re-fire.
    refresher.tick()
    assert len(fired) == 1
