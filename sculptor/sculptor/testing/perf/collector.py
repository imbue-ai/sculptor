"""Performance measurement primitives for scenario tests.

A ``MeasurementRecorder`` wraps a Playwright ``Page`` and exposes a
``window()`` context manager that brackets a user-visible action.  Inside
the window we collect:

- HTTP requests issued from the page (foreground vs. background, bucketed
  by route pattern), via ``page.on("request")``.
- React fiber commits, via the DevTools hook injected by
  :mod:`sculptor.testing.perf.init_scripts`.
- DOM mutations, via a ``MutationObserver`` registered by the same script.
- Wall-clock duration from window-start to stabilization-end.

Within a window, ``checkpoint(name, wait_for=...)`` snapshots the same
metrics at intermediate points (e.g. "user-message bubble visible") so
multi-stage actions can be attributed to the slow stage.

Measurements are appended as JSONL to a file selected via the
``SCULPTOR_PERF_OUTPUT_PATH`` environment variable (default:
``perf-results/perf-measurements.jsonl`` — see ``resolve_output_path``).
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any

from playwright.sync_api import Page
from playwright.sync_api import Request

from sculptor.testing.perf.init_scripts import PERF_GATE_LOCALSTORAGE_KEY
from sculptor.testing.perf.init_scripts import PERF_INIT_SCRIPT

# Routes whose calls are polling / debounced sync / push-driven and not part
# of a foreground user action. Tagged separately so they show up in the
# breakdown without polluting the foreground delta. Each entry is a substring
# match against the URL path (after host/scheme stripping).
_BACKGROUND_ROUTE_FRAGMENTS: tuple[str, ...] = (
    "/api/v1/health",
    "/api/v1/skills",
    "/api/v1/projects/active",
    "/api/v1/projects/most-recently-used",
    "/repo_info",
    "/current_branch",
    "/artifacts/USAGE",
    "/mark-read",
    "/api/v1/config",
)

# Replace per-entity IDs in URL paths with stable placeholders so requests
# to different workspaces/agents/projects bucket together.
_ID_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"/workspaces/[^/?#]+"), "/workspaces/:id"),
    (re.compile(r"/projects/[^/?#]+"), "/projects/:id"),
    (re.compile(r"/agents/[^/?#]+"), "/agents/:id"),
    (re.compile(r"/tasks/[^/?#]+"), "/tasks/:id"),
)


def _bucket_url(url: str) -> str:
    """Strip query/host and collapse entity IDs so URLs aggregate cleanly."""
    path = url.split("?", 1)[0]
    path = re.sub(r"^https?://[^/]+", "", path)
    for pattern, repl in _ID_PATTERNS:
        path = pattern.sub(repl, path)
    return path


def _is_background(path: str) -> bool:
    return any(fragment in path for fragment in _BACKGROUND_ROUTE_FRAGMENTS)


@dataclass
class Checkpoint:
    """Snapshot of cumulative counters at a named point inside a window."""

    name: str
    ms_since_start: float
    fg_requests: int
    bg_requests: int
    commits: int
    dom_mutations: int


@dataclass
class Measurement:
    """One scenario × variant result, written to JSONL on window close."""

    scenario: str
    variant: str
    duration_ms: float
    fg_requests: int
    bg_requests: int
    fg_by_route: dict[str, int]
    bg_by_route: dict[str, int]
    commits: int
    # Commits-by-component counts fibers React actually did work on this
    # commit (Placement | Update flags). Static infrastructure like Radix
    # Slot drops out; the entries that remain are real re-renders.
    commits_by_component: dict[str, int]
    dom_mutations: int
    dom_mutations_by_type: dict[str, int]
    # Mutations bucketed by the nearest enclosing ``data-testid`` ancestor.
    # ``__untagged__`` collects mutations that have no tagged ancestor —
    # mostly deep inside Radix/styled-components subtrees. Coverage is
    # whatever fraction of the DOM we've tagged for test ids.
    dom_mutations_by_testid: dict[str, int]
    checkpoints: list[Checkpoint] = field(default_factory=list)
    test_nodeid: str = ""


class _Window:
    """Active measurement window. Created by ``MeasurementRecorder.window``."""

    def __init__(
        self,
        page: Page,
        scenario: str,
        variant: str,
        stabilization_ms: int,
    ) -> None:
        self._page = page
        self._scenario = scenario
        self._variant = variant
        self._stabilization_ms = stabilization_ms
        self._fg_by_route: dict[str, int] = {}
        self._bg_by_route: dict[str, int] = {}
        self._fg_total = 0
        self._bg_total = 0
        self._t0 = 0.0
        self._checkpoints: list[Checkpoint] = []

    def _on_request(self, request: Request) -> None:
        if "/api/" not in request.url:
            return
        bucket = _bucket_url(request.url)
        key = f"{request.method} {bucket}"
        if _is_background(bucket):
            self._bg_by_route[key] = self._bg_by_route.get(key, 0) + 1
            self._bg_total += 1
        else:
            self._fg_by_route[key] = self._fg_by_route.get(key, 0) + 1
            self._fg_total += 1

    def _start(self) -> None:
        # Attach the Python-side listener before JS-side reset so any
        # request fired between the two ends up counted on both sides.
        self._page.on("request", self._on_request)
        self._page.evaluate("window.__SCULPTOR_PERF__.reset()")
        self._t0 = time.monotonic()

    def _snapshot_js(self) -> dict[str, Any]:
        # Returns whatever ``window.__SCULPTOR_PERF__.snapshot()`` emits:
        # ``{commits, commitsByComponent, domMutations, domMutationsByType}``.
        # Typed as Any because the values are mixed (int + nested dicts) and
        # the JS side is the source of truth, not Python's type system.
        return self._page.evaluate("window.__SCULPTOR_PERF__.snapshot()")

    def checkpoint(self, name: str, wait_for: Callable[[], None]) -> None:
        """Wait for an intermediate signal, snapshot cumulative counters."""
        wait_for()
        elapsed_ms = (time.monotonic() - self._t0) * 1000.0
        snap = self._snapshot_js()
        self._checkpoints.append(
            Checkpoint(
                name=name,
                ms_since_start=elapsed_ms,
                fg_requests=self._fg_total,
                bg_requests=self._bg_total,
                commits=int(snap["commits"]),
                dom_mutations=int(snap["domMutations"]),
            )
        )

    def _finish(self) -> Measurement:
        # Stabilization window: wait so any post-end-signal activity
        # (debounced sync, late commits, secondary fetches) lands inside
        # the recorded numbers rather than leaking into the next test.
        time.sleep(self._stabilization_ms / 1000.0)
        self._page.evaluate("window.__SCULPTOR_PERF__.stop()")
        self._page.remove_listener("request", self._on_request)
        duration_ms = (time.monotonic() - self._t0) * 1000.0
        snap = self._snapshot_js()
        return Measurement(
            scenario=self._scenario,
            variant=self._variant,
            duration_ms=duration_ms,
            fg_requests=self._fg_total,
            bg_requests=self._bg_total,
            fg_by_route=dict(self._fg_by_route),
            bg_by_route=dict(self._bg_by_route),
            commits=int(snap["commits"]),
            commits_by_component=dict(snap["commitsByComponent"]),
            dom_mutations=int(snap["domMutations"]),
            dom_mutations_by_type=dict(snap["domMutationsByType"]),
            dom_mutations_by_testid=dict(snap["domMutationsByTestid"]),
            checkpoints=list(self._checkpoints),
        )


class MeasurementRecorder:
    """Per-test recorder: installs the init script, opens measurement windows,
    flushes JSONL on test teardown.
    """

    def __init__(self, page: Page, output_path: Path | None, test_nodeid: str) -> None:
        self._page = page
        self._output_path = output_path
        self._test_nodeid = test_nodeid
        self._measurements: list[Measurement] = []
        self._enabled = False

    def enable(self) -> None:
        """Register the perf init script and flip the localStorage gate.

        Idempotent: callable many times in the same context. Callers must
        reload the SPA after the first ``enable()`` so React picks up the
        injected DevTools hook on its next mount.
        """
        if not self._enabled:
            self._page.add_init_script(PERF_INIT_SCRIPT)
            self._enabled = True
        self._page.evaluate(f"localStorage.setItem({json.dumps(PERF_GATE_LOCALSTORAGE_KEY)}, 'true')")

    def disable(self) -> None:
        """Clear the localStorage gate so subsequent navigations skip the script."""
        self._page.evaluate(f"localStorage.removeItem({json.dumps(PERF_GATE_LOCALSTORAGE_KEY)})")

    def assert_hook_wired(self) -> None:
        """Fail loudly if the React DevTools hook didn't pick up a renderer.

        Catches the most common silent failure: the init script raced
        React (or wasn't yet active because the SPA loaded before
        ``enable()``). Without this check the test would record zero
        commits and look healthy.
        """
        hook_check_js = """
            (() => {
                const hook = window.__REACT_DEVTOOLS_GLOBAL_HOOK__;
                return (hook && hook.renderers) ? hook.renderers.size : 0;
            })()
        """
        n = self._page.evaluate(hook_check_js)
        if not n:
            raise RuntimeError(
                "perf init script did not register a React renderer."
                + " The SPA likely loaded before MeasurementRecorder.enable() —"
                + " reload the page after calling enable() so the init script runs"
                + " before React boots."
            )

    @contextmanager
    def window(
        self,
        *,
        scenario: str,
        variant: str,
        stabilization_ms: int = 250,
    ) -> Generator[_Window, None, None]:
        w = _Window(self._page, scenario, variant, stabilization_ms)
        w._start()
        try:
            yield w
        finally:
            m = w._finish()
            m.test_nodeid = self._test_nodeid
            self._measurements.append(m)

    def flush(self) -> None:
        if not self._output_path or not self._measurements:
            return
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        with self._output_path.open("a", encoding="utf-8") as f:
            for m in self._measurements:
                f.write(json.dumps(asdict(m), separators=(",", ":")) + "\n")


def resolve_output_path() -> Path | None:
    """Return the JSONL output path, or None if perf collection is disabled.

    Reads ``SCULPTOR_PERF_OUTPUT_PATH``; if unset, defaults to
    ``perf-results/perf-measurements.jsonl`` under the current working dir.
    Set the env var to an empty string to disable output entirely.

    Deliberately NOT under ``test-results/``: pytest-playwright wipes that
    directory at session start, so measurements accumulated there survive
    only the most recent pytest invocation — repeat-run workflows (e.g.
    re-running one scenario 3x for variance) silently lose all but the
    last run's data.
    """
    raw = os.environ.get("SCULPTOR_PERF_OUTPUT_PATH")
    if raw is None:
        return Path.cwd() / "perf-results" / "perf-measurements.jsonl"
    if raw == "":
        return None
    return Path(raw)
