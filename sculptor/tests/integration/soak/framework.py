"""Soak-test framework: operations, checks, recovery, runner.

A soak test repeatedly picks an :class:`Operation` from a weighted registry
and runs it against a single long-lived Sculptor instance.  Each operation
declares whether it is currently available (a DOM probe — the "reactive"
half) and what it does.

Three failure flavours are wired in:

* **Hard checks** (:func:`OperationContext.hard_check`) — raise
  :class:`AbortSoak` and end the run immediately.  Used for global
  invariants and for asserts inside operations that must never fail.
* **Soft checks** (:func:`OperationContext.soft_check`) — record a
  :class:`SoftFailure` in the JSONL log and annotate the Playwright trace,
  but do not raise.  The operation chooses how to react.
* **Recovery** — if an operation raises any non-:class:`AbortSoak`
  exception, the runner records it as a soft failure and tries each
  registered :class:`RecoveryAction` in order; if none succeeds, the soak
  is aborted.
"""

from __future__ import annotations

import json
import logging
import random
import time
import traceback
from abc import ABC
from abc import abstractmethod
from contextlib import contextmanager
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Callable
from typing import Iterator
from typing import Sequence

from playwright.sync_api import Page

logger = logging.getLogger(__name__)


class AbortSoak(Exception):
    """Raised when the soak must end immediately (hard invariant violated)."""


@dataclass
class SoftFailure:
    iteration: int
    operation: str
    check: str
    detail: str
    timestamp: float
    recovered_by: str | None = None


@dataclass
class SoakStats:
    iterations: int = 0
    operations_run: dict[str, int] = field(default_factory=dict)
    operations_skipped_unavailable: dict[str, int] = field(default_factory=dict)
    soft_failures: list[SoftFailure] = field(default_factory=list)
    recoveries: int = 0


class _JsonlWriter:
    """Append-only JSONL sink. Flushes after every write so a crash still
    leaves a readable log on disk."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Truncate any prior run so the log corresponds to this soak only.
        self._fh = self._path.open("w", encoding="utf-8")

    def write(self, event: dict) -> None:
        event.setdefault("ts", time.time())
        self._fh.write(json.dumps(event, default=str) + "\n")
        self._fh.flush()

    def close(self) -> None:
        self._fh.close()


class OperationContext:
    """Per-tick context handed to every operation.

    Carries the Playwright ``page``, a seeded RNG, and the failure-recording
    primitives.  Operations should reach for the page directly when they
    need to drive the UI and use ``hard_check`` / ``soft_check`` for the
    bits that should be recorded.
    """

    def __init__(
        self,
        page: Page,
        rng: random.Random,
        stats: SoakStats,
        jsonl: _JsonlWriter,
        screenshot_dir: Path | None,
    ) -> None:
        self.page = page
        self.rng = rng
        self.stats = stats
        self._jsonl = jsonl
        self._screenshot_dir = screenshot_dir
        self.current_operation: str = "<idle>"
        self.iteration: int = 0

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def hard_check(self, name: str, fn: Callable[[], None]) -> None:
        """Run ``fn``; on any exception, log and abort the soak."""
        try:
            fn()
        except Exception as exc:
            self._jsonl.write(
                {
                    "kind": "hard_fail",
                    "iteration": self.iteration,
                    "operation": self.current_operation,
                    "check": name,
                    "error": repr(exc),
                    "traceback": traceback.format_exc(),
                }
            )
            raise AbortSoak(f"hard_check failed: {self.current_operation}/{name}: {exc!r}") from exc

    def soft_check(self, name: str, fn: Callable[[], None]) -> bool:
        """Run ``fn``; on failure, record a SoftFailure and return False."""
        try:
            fn()
            return True
        except Exception as exc:
            failure = SoftFailure(
                iteration=self.iteration,
                operation=self.current_operation,
                check=name,
                detail=repr(exc),
                timestamp=time.time(),
            )
            self.stats.soft_failures.append(failure)
            self._jsonl.write({"kind": "soft_fail", **asdict(failure)})
            self._annotate_trace(f"SOFT_FAIL: {self.current_operation}/{name}")
            self._maybe_screenshot(f"soft-{self.iteration:05d}-{self.current_operation}-{name}")
            logger.info(
                "Soak soft-fail iter=%d op=%s check=%s detail=%s",
                self.iteration,
                self.current_operation,
                name,
                exc,
            )
            return False

    def record_event(self, kind: str, **data: object) -> None:
        """Append a free-form event to the JSONL log (for operation telemetry)."""
        self._jsonl.write({"kind": kind, "iteration": self.iteration, **data})

    # ------------------------------------------------------------------
    # Trace / screenshot helpers
    # ------------------------------------------------------------------

    @contextmanager
    def annotated(self, group_name: str) -> Iterator[None]:
        """Wrap a block in a named tracing group for trace-viewer inspection."""
        self._annotate_trace_start(group_name)
        try:
            yield
        finally:
            self._annotate_trace_end()

    def _annotate_trace(self, label: str) -> None:
        self._annotate_trace_start(label)
        self._annotate_trace_end()

    def _annotate_trace_start(self, label: str) -> None:
        try:
            self.page.context.tracing.group(label)
        except Exception:
            # Tracing may not be enabled (e.g. tracing=off) — never fail
            # the soak because we couldn't annotate the trace.
            pass

    def _annotate_trace_end(self) -> None:
        try:
            self.page.context.tracing.group_end()
        except Exception:
            pass

    def _maybe_screenshot(self, label: str) -> None:
        if self._screenshot_dir is None:
            return
        try:
            self._screenshot_dir.mkdir(parents=True, exist_ok=True)
            path = self._screenshot_dir / f"{label}.png"
            self.page.screenshot(path=str(path), full_page=False)
            self._jsonl.write({"kind": "screenshot", "path": str(path), "label": label})
        except Exception as exc:
            logger.debug("Soak screenshot failed for %s: %s", label, exc)


class Operation(ABC):
    """An atomic UI step the soak loop can pick on each tick.

    Designed so a future *compound* operation is simply an :class:`Operation`
    whose :meth:`execute` calls a sequence of other operations.  No extra
    framework needed today.
    """

    #: Name shown in logs and trace annotations.
    name: str = ""
    #: Relative weight for the random picker. Higher = more often.
    weight: float = 1.0

    def is_available(self, ctx: OperationContext) -> bool:  # noqa: ARG002
        """Cheap DOM probe — return True iff this op can run *right now*.

        Default ``True``; override for operations that need particular UI
        state (e.g. an existing workspace, an open chat panel).
        """
        return True

    @abstractmethod
    def execute(self, ctx: OperationContext) -> None:
        """Drive the UI. May call ``hard_check`` / ``soft_check``."""


class RecoveryAction(ABC):
    """Named recovery step tried after an operation raises.

    Returns True if the app is back in a known-good state.  The runner tries
    actions in registration order until one succeeds, otherwise aborts.
    """

    name: str = ""

    @abstractmethod
    def apply(self, ctx: OperationContext) -> bool: ...


class SoakRunner:
    """Drives the soak loop for a configured duration."""

    def __init__(
        self,
        page: Page,
        operations: Sequence[Operation],
        recoveries: Sequence[RecoveryAction],
        global_invariants: Sequence[Callable[[OperationContext], None]],
        duration_seconds: float,
        seed: int,
        log_path: Path,
        screenshot_dir: Path | None = None,
    ) -> None:
        if not operations:
            raise ValueError("SoakRunner needs at least one operation.")
        self._page = page
        self._operations = list(operations)
        self._recoveries = list(recoveries)
        self._global_invariants = list(global_invariants)
        self._duration = duration_seconds
        self._seed = seed
        self._log_path = log_path
        self._screenshot_dir = screenshot_dir

    def run(self) -> SoakStats:
        rng = random.Random(self._seed)
        stats = SoakStats()
        jsonl = _JsonlWriter(self._log_path)
        ctx = OperationContext(self._page, rng, stats, jsonl, self._screenshot_dir)
        start = time.monotonic()
        jsonl.write(
            {
                "kind": "soak_start",
                "seed": self._seed,
                "duration_seconds": self._duration,
                "operations": [op.name for op in self._operations],
                "recoveries": [r.name for r in self._recoveries],
            }
        )
        try:
            while time.monotonic() - start < self._duration:
                ctx.iteration = stats.iterations
                op = self._pick(ctx)
                if op is None:
                    # The registry is expected to contain at least one always-
                    # available operation (e.g. IdleWaitOp). If we hit this,
                    # the soak is misconfigured — abort loudly rather than
                    # silently spin.
                    raise AbortSoak(
                        "No operation is currently available — the registry should include at least one always-available op (e.g. IdleWaitOp)."  # noqa: E501
                    )
                self._run_one(ctx, op)
                self._check_global_invariants(ctx)
                stats.iterations += 1
        except AbortSoak as exc:
            jsonl.write({"kind": "abort", "reason": str(exc)})
            raise
        finally:
            jsonl.write(
                {
                    "kind": "soak_end",
                    "iterations": stats.iterations,
                    "operations_run": stats.operations_run,
                    "operations_skipped_unavailable": stats.operations_skipped_unavailable,
                    "soft_failure_count": len(stats.soft_failures),
                    "recoveries": stats.recoveries,
                    "elapsed_seconds": time.monotonic() - start,
                }
            )
            jsonl.close()
        return stats

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _pick(self, ctx: OperationContext) -> Operation | None:
        available: list[Operation] = []
        weights: list[float] = []
        for op in self._operations:
            try:
                if op.is_available(ctx):
                    available.append(op)
                    weights.append(op.weight)
                else:
                    ctx.stats.operations_skipped_unavailable[op.name] = (
                        ctx.stats.operations_skipped_unavailable.get(op.name, 0) + 1
                    )
            except Exception as exc:
                # A buggy is_available shouldn't crash the soak.
                logger.debug("is_available raised for %s: %s", op.name, exc)
        if not available:
            return None
        return ctx.rng.choices(available, weights=weights, k=1)[0]

    def _run_one(self, ctx: OperationContext, op: Operation) -> None:
        ctx.current_operation = op.name
        ctx.stats.operations_run[op.name] = ctx.stats.operations_run.get(op.name, 0) + 1
        ctx._jsonl.write({"kind": "op_start", "iteration": ctx.iteration, "operation": op.name})
        try:
            with ctx.annotated(f"SOAK[{ctx.iteration:05d}] {op.name}"):
                op.execute(ctx)
        except AbortSoak:
            raise
        except Exception as exc:
            # Treat as a soft failure and try to recover.
            failure = SoftFailure(
                iteration=ctx.iteration,
                operation=op.name,
                check="<execute>",
                detail=repr(exc),
                timestamp=time.time(),
            )
            ctx.stats.soft_failures.append(failure)
            ctx._jsonl.write(
                {
                    "kind": "op_exception",
                    **asdict(failure),
                    "traceback": traceback.format_exc(),
                }
            )
            ctx._annotate_trace(f"OP_RAISED: {op.name}: {exc!r}")
            ctx._maybe_screenshot(f"op-raised-{ctx.iteration:05d}-{op.name}")
            self._attempt_recovery(ctx, failure)
        finally:
            ctx._jsonl.write({"kind": "op_end", "iteration": ctx.iteration, "operation": op.name})
            ctx.current_operation = "<idle>"

    def _attempt_recovery(self, ctx: OperationContext, failure: SoftFailure) -> None:
        if self._page.is_closed():
            raise AbortSoak(f"Page closed after {failure.operation}; cannot recover.")
        for recovery in self._recoveries:
            try:
                with ctx.annotated(f"RECOVERY: {recovery.name}"):
                    if recovery.apply(ctx):
                        ctx.stats.recoveries += 1
                        failure.recovered_by = recovery.name
                        ctx._jsonl.write(
                            {
                                "kind": "recovered",
                                "iteration": ctx.iteration,
                                "operation": failure.operation,
                                "recovery": recovery.name,
                            }
                        )
                        return
            except Exception as exc:
                ctx._jsonl.write(
                    {
                        "kind": "recovery_failed",
                        "iteration": ctx.iteration,
                        "recovery": recovery.name,
                        "error": repr(exc),
                    }
                )
        raise AbortSoak(f"No recovery succeeded after {failure.operation} failed: {failure.detail}")

    def _check_global_invariants(self, ctx: OperationContext) -> None:
        ctx.current_operation = "<global_invariants>"
        try:
            for invariant in self._global_invariants:
                invariant(ctx)
        finally:
            ctx.current_operation = "<idle>"
