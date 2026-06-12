"""Capture every compositor frame around workspace switches, for frame-by-frame
inspection of re-rendering problems (stale panel content, layout shift, slow
progressive load-in).

Launches Sculptor via ManualTestHarness, seeds two visually loud workspaces
(ALPHA / BRAVO) with deterministic FakeClaude content, then clicks between
them in the nav sidebar while recording the CDP `Page.startScreencast` stream.
Screencast frames are exactly the frames the compositor produced — unchanged
frames are simply never delivered — so every captured image is a distinct
visual state the user would have seen.

Output is a directory of numbered JPEG frames per switch plus an `index.html`
contact sheet that interleaves the frames with the renderer's `ws-switch.*`
performance marks (see frontend/src/common/perf/workspaceSwitchProfiler.ts).
Any frame showing ALPHA content after a click toward BRAVO is a stale frame,
visible at a glance.

Usage::

    uv run --project sculptor python -m sculptor.testing.frame_capture \\
        --out-dir /tmp/ws_switch_frames --switches a-to-b,b-to-a,a-to-b

Timings come from a Vite dev build (unminified, StrictMode), so treat
durations as relative; frame content and ordering are the primary signal.
"""

import argparse
import base64
import hashlib
import json
import tempfile
import time
from pathlib import Path

from loguru import logger
from playwright.sync_api import CDPSession
from playwright.sync_api import Page

from sculptor.testing.frame_capture_report import WS_SWITCH_MARK_PREFIX
from sculptor.testing.frame_capture_report import build_switch_timeline
from sculptor.testing.frame_capture_report import write_report
from sculptor.testing.manual_test_harness import ManualTestHarness

# Recorded by an init script on pointerdown over a workspace row, so the click
# moment is captured on the page's own clock with no protocol round-trip.
_CLICK_RECORDER_SCRIPT = """
window.__SWITCH_EVENTS__ = [];
addEventListener("pointerdown", (event) => {
    const row = event.target.closest('[data-testid="WORKSPACE_TAB"]');
    if (row) {
        window.__SWITCH_EVENTS__.push({
            epochMs: Date.now(),
            label: (row.textContent || "").trim(),
        });
    }
}, true);
"""

# Force-enable the in-app switch profiler so ws-switch.* marks exist even
# though this is not a traced build.
_PROFILER_ENABLE_SCRIPT = "window.__WS_SWITCH_PROFILER__ = true;"

_SEED_WAIT_TIMEOUT_MS = 90_000


def _build_seed_prompt(label: str) -> str:
    """A FakeClaude multi_step prompt producing loud, distinct workspace content.

    Several long chat messages (so the chat panel scrolls and clearly reads
    ALPHA/BRAVO), one committed file and one uncommitted file (so the diff and
    file panels have content), then a final `<LABEL>-DONE` message the capture
    script waits on.
    """
    body = " ".join(f"{label.lower()}-{index:02d}" for index in range(40))
    chat_text = f"{label} workspace chat content. {body}"
    committed_file = f"{label.lower()}_module.py"
    committed_content = "\n".join(f"def {label.lower()}_function_{index}(): ...." for index in range(60))
    uncommitted_file = f"{label.lower()}_scratch.md"
    # A few hundred lines so the uncommitted diff is comparable to a real
    # spec/doc diff — big enough that Pierre's mount + highlighting cost is
    # visible in the capture rather than fitting inside one frame.
    uncommitted_content = f"# {label} uncommitted change\n\n" + "\n".join(
        f"- {label.lower()} change line {index:03d} with some **markdown** content to highlight"
        for index in range(300)
    )
    steps = [
        {"command": "text", "args": {"text": chat_text}},
        {"command": "write_file", "args": {"file_path": committed_file, "content": committed_content}},
        # Add only this workspace's file: both seeded workspaces share one
        # IN_PLACE repo, so `git add -A` here would swallow the other
        # workspace's uncommitted seed file.
        {"command": "bash", "args": {"command": f"git add {committed_file} && git commit -m '{label} seed commit'"}},
        {"command": "write_file", "args": {"file_path": uncommitted_file, "content": uncommitted_content}},
        {"command": "text", "args": {"text": f"{label} second message. {body}"}},
        {"command": "text", "args": {"text": f"{label}-DONE"}},
    ]
    return "fake_claude:multi_step `" + json.dumps({"steps": steps}) + "`"


def _create_task(page: Page, prompt: str, name: str) -> dict:
    """Create a task (and its implicit workspace) via the backend API."""
    result = page.evaluate(
        """async ({ prompt, name }) => {
            const projectsRes = await fetch('/api/v1/projects');
            const projects = await projectsRes.json();
            const projectId = projects[0]?.objectId;
            if (!projectId) throw new Error('no project found');
            const taskRes = await fetch(`/api/v1/projects/${projectId}/tasks`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt, name, interface: 'API', model: 'FAKE_CLAUDE' }),
            });
            if (!taskRes.ok) throw new Error(`task creation failed: ${taskRes.status} ${await taskRes.text()}`);
            const task = await taskRes.json();
            return { workspaceId: task.workspaceId, taskId: task.id };
        }""",
        {"prompt": prompt, "name": name},
    )
    logger.info("Seeded task {} → workspace {}", result["taskId"], result["workspaceId"])
    return result


class ScreencastRecorder:
    """Records CDP screencast frames as (epoch_seconds, jpeg_bytes) tuples."""

    def __init__(self, page: Page, jpeg_quality: int, max_width: int, max_height: int) -> None:
        self._cdp: CDPSession = page.context.new_cdp_session(page)
        self._jpeg_quality = jpeg_quality
        self._max_width = max_width
        self._max_height = max_height
        self.frames: list[tuple[float, bytes]] = []
        self._cdp.on("Page.screencastFrame", self._on_frame)

    def _on_frame(self, params: dict) -> None:
        # Ack first — Chromium stops delivering frames while one is unacked.
        self._cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
        self.frames.append((params["metadata"]["timestamp"], base64.b64decode(params["data"])))

    def start(self) -> None:
        self.frames = []
        self._cdp.send(
            "Page.startScreencast",
            {
                "format": "jpeg",
                "quality": self._jpeg_quality,
                "maxWidth": self._max_width,
                "maxHeight": self._max_height,
                "everyNthFrame": 1,
            },
        )

    def stop(self) -> None:
        self._cdp.send("Page.stopScreencast")

    def detach(self) -> None:
        self._cdp.detach()


def _dedupe_frames(frames: list[tuple[float, bytes]]) -> list[dict]:
    """Collapse runs of byte-identical frames, keeping the first timestamp."""
    deduped: list[dict] = []
    previous_digest: str | None = None
    for epoch_seconds, data in frames:
        digest = hashlib.md5(data).hexdigest()
        if digest == previous_digest:
            deduped[-1]["repeat_count"] += 1
            continue
        previous_digest = digest
        deduped.append({"epoch_ms": epoch_seconds * 1000.0, "data": data, "repeat_count": 1})
    return deduped


def _write_frames(switch_dir: Path, deduped: list[dict], click_epoch_ms: float) -> list[dict]:
    frames_dir = switch_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    written: list[dict] = []
    for index, frame in enumerate(deduped, start=1):
        offset_ms = frame["epoch_ms"] - click_epoch_ms
        sign = "+" if offset_ms >= 0 else "-"
        file_name = f"{index:04d}_t{sign}{abs(offset_ms):05.0f}ms.jpg"
        (frames_dir / file_name).write_bytes(frame["data"])
        written.append({"file_name": file_name, "epoch_ms": frame["epoch_ms"], "repeat_count": frame["repeat_count"]})
    return written


def _collect_switch_marks(page: Page, since_epoch_ms: float) -> list[dict]:
    """Read ws-switch.* performance marks created after `since_epoch_ms`."""
    raw = page.evaluate(
        """(prefix) => performance.getEntriesByType('mark')
            .filter((entry) => entry.name.startsWith(prefix))
            .map((entry) => ({ name: entry.name, epochMs: performance.timeOrigin + entry.startTime }))""",
        WS_SWITCH_MARK_PREFIX,
    )
    return [{"name": mark["name"], "epoch_ms": mark["epochMs"]} for mark in raw if mark["epochMs"] >= since_epoch_ms]


def _wait_for_workspace_url(page: Page, workspace_id: str, timeout_seconds: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if workspace_id in page.evaluate("window.location.hash"):
            return
        time.sleep(0.1)
    raise TimeoutError(f"URL never reached workspace {workspace_id} (hash={page.evaluate('window.location.hash')})")


def _configure_panels_changes_vs_files(
    page: Page, seeded: dict[str, dict], row_index_by_label: dict[str, int]
) -> None:
    """Set up the user-reported jarring scenario: each workspace has a
    DIFFERENT active panel in the left section, and one has an open file diff.

    ALPHA: Changes panel active with alpha_scratch.md's diff open.
    BRAVO: Files panel active.
    Switching between them then swaps the whole section body, the diff
    master-detail split, and the diff content itself.
    """
    rows = page.get_by_test_id("WORKSPACE_TAB")

    rows.nth(row_index_by_label["ALPHA"]).click()
    _wait_for_workspace_url(page, seeded["ALPHA"]["workspaceId"])
    page.get_by_test_id("panel-tab-changes").click()
    time.sleep(0.5)
    page.locator('[data-testid="CHANGES_PANEL"]').get_by_text("alpha_scratch.md").first.click()
    time.sleep(2.0)  # let the diff render fully (file lines fetch + highlight)

    rows.nth(row_index_by_label["BRAVO"]).click()
    _wait_for_workspace_url(page, seeded["BRAVO"]["workspaceId"])
    page.get_by_test_id("panel-tab-files").click()
    time.sleep(1.5)
    logger.info("Panel setup complete: ALPHA=Changes+diff, BRAVO=Files")


def _capture_switch(
    page: Page,
    recorder: ScreencastRecorder,
    out_dir: Path,
    switch_name: str,
    target_row_index: int,
    target_workspace_id: str,
    lead_ms: int,
    settle_ms: int,
) -> dict:
    """Record one click-driven workspace switch and write its frames."""
    page.evaluate("window.__SWITCH_EVENTS__ = []")
    timings_before = page.evaluate("(window.__WS_SWITCH_TIMINGS__ || []).length")
    capture_start_epoch_ms = time.time() * 1000.0

    recorder.start()
    time.sleep(lead_ms / 1000.0)
    page.get_by_test_id("WORKSPACE_TAB").nth(target_row_index).click()
    _wait_for_workspace_url(page, target_workspace_id)
    time.sleep(settle_ms / 1000.0)
    recorder.stop()

    click_events = page.evaluate("window.__SWITCH_EVENTS__")
    if len(click_events) != 1:
        raise RuntimeError(f"expected exactly one recorded click for {switch_name}, got {click_events}")
    click_epoch_ms = click_events[0]["epochMs"]

    timing_record = page.evaluate(
        "(count) => (window.__WS_SWITCH_TIMINGS__ || []).length > count ? window.__WS_SWITCH_TIMINGS__.at(-1) : null",
        timings_before,
    )
    marks = _collect_switch_marks(page, since_epoch_ms=capture_start_epoch_ms)

    switch_dir = out_dir / switch_name
    deduped = _dedupe_frames(recorder.frames)
    frames = _write_frames(switch_dir, deduped, click_epoch_ms)
    logger.info(
        "{}: {} distinct frames ({} raw), {} marks", switch_name, len(frames), len(recorder.frames), len(marks)
    )
    return build_switch_timeline(switch_name, click_epoch_ms, frames, marks, timing_record)


def _complete_onboarding_if_needed(page: Page) -> None:
    """Click through the installation step (dependency checks) on first launch.

    The harness starts with a fresh data folder, so the onboarding wizard's
    installation screen gates the app until its Continue button is pressed.
    """
    continue_button = page.get_by_role("button", name="Continue")
    try:
        continue_button.wait_for(state="visible", timeout=90_000)
    except Exception:
        logger.info("No onboarding Continue button — assuming onboarding is already complete")
        return
    # The button stays disabled until the backend's background dependency
    # install (Claude CLI) finishes — wait for it to become enabled.
    deadline = time.monotonic() + 180
    while not continue_button.is_enabled():
        if time.monotonic() > deadline:
            raise TimeoutError("onboarding Continue button never became enabled")
        time.sleep(1)
    continue_button.click()
    continue_button.wait_for(state="hidden", timeout=30_000)
    logger.info("Onboarding completed")


def _navigate_to_seeded_workspace(page: Page, workspace_id: str, task_id: str, timeout_seconds: float = 30.0) -> None:
    """Navigate to a freshly API-created workspace, retrying until it sticks.

    The frontend learns about the new workspace via the websocket stream;
    until that update lands, WorkspacePage's validation effect treats the id
    as a deleted workspace and bounces to the new-workspace page. Re-assert
    the hash until the route survives.
    """
    target_hash = f"#/ws/{workspace_id}/agent/{task_id}"
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        page.evaluate("(hash) => { window.location.hash = hash; }", target_hash)
        time.sleep(1.0)
        if workspace_id in page.evaluate("window.location.hash"):
            return
    raise TimeoutError(f"navigation to workspace {workspace_id} kept bouncing (hash never stuck)")


def _seed_workspaces(page: Page) -> dict[str, dict]:
    """Create the ALPHA and BRAVO workspaces sequentially and wait for both.

    Sequential creation keeps the two FakeClaude runs from interleaving their
    git operations in the shared IN_PLACE repo.
    """
    seeded: dict[str, dict] = {}
    for expected_row_count, label in enumerate(("ALPHA", "BRAVO"), start=1):
        seeded[label] = _create_task(page, _build_seed_prompt(label), name=f"{label} agent")
        target = seeded[label]
        # Wait for the websocket update to surface the workspace in the nav
        # sidebar before navigating, so the route isn't treated as stale.
        page.get_by_test_id("WORKSPACE_TAB").nth(expected_row_count - 1).wait_for(timeout=_SEED_WAIT_TIMEOUT_MS)
        _navigate_to_seeded_workspace(page, target["workspaceId"], target["taskId"])
        page.get_by_text(f"{label}-DONE").first.wait_for(timeout=_SEED_WAIT_TIMEOUT_MS)
        logger.info("{} workspace seeded and rendered", label)
    return seeded


def _resolve_sidebar_rows(page: Page, seeded: dict[str, dict]) -> dict[str, int]:
    """Map each seeded workspace to its nav-sidebar row index by clicking through."""
    rows = page.get_by_test_id("WORKSPACE_TAB")
    row_count = rows.count()
    row_index_by_label: dict[str, int] = {}
    for row_index in range(row_count):
        rows.nth(row_index).click()
        time.sleep(1.0)
        current_hash = page.evaluate("window.location.hash")
        for label, target in seeded.items():
            if target["workspaceId"] in current_hash:
                row_index_by_label[label] = row_index
    missing = {label for label in seeded if label not in row_index_by_label}
    if missing:
        raise RuntimeError(f"could not find sidebar rows for {missing} among {row_count} rows")
    logger.info("Sidebar rows resolved: {}", row_index_by_label)
    return row_index_by_label


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", type=Path, default=None, help="Output directory (default: a fresh temp dir)")
    parser.add_argument("--settle-ms", type=int, default=4000, help="Capture window after each click")
    parser.add_argument("--lead-ms", type=int, default=300, help="Capture lead-in before each click")
    parser.add_argument(
        "--switches",
        default="a-to-b,b-to-a,a-to-b",
        help="Comma-separated switch sequence (first a-to-b is cold, repeats are warm)",
    )
    parser.add_argument("--jpeg-quality", type=int, default=80)
    parser.add_argument("--viewport", default="1400x900", help="WIDTHxHEIGHT")
    parser.add_argument("--headed", action="store_true", help="Run a headed browser (fidelity checks)")
    parser.add_argument(
        "--panel-setup",
        choices=["none", "changes-vs-files"],
        default="none",
        help="Optional per-workspace panel configuration before capturing "
        "(changes-vs-files: ALPHA on the Changes panel with an open diff, BRAVO on Files)",
    )
    args = parser.parse_args()

    width, height = (int(part) for part in args.viewport.split("x"))
    out_dir = args.out_dir or Path(tempfile.mkdtemp(prefix="sculptor_frame_capture_"))
    out_dir.mkdir(parents=True, exist_ok=True)

    switch_specs = [spec.strip() for spec in args.switches.split(",") if spec.strip()]
    label_by_letter = {"a": "ALPHA", "b": "BRAVO"}

    harness = ManualTestHarness(
        screenshots_dir=out_dir / "harness",
        viewport={"width": width, "height": height},
        init_scripts=[_CLICK_RECORDER_SCRIPT, _PROFILER_ENABLE_SCRIPT],
        is_headless=not args.headed,
    )
    harness.start()
    try:
        page = harness.page
        _complete_onboarding_if_needed(page)
        seeded = _seed_workspaces(page)
        row_index_by_label = _resolve_sidebar_rows(page, seeded)
        if args.panel_setup == "changes-vs-files":
            _configure_panels_changes_vs_files(page, seeded, row_index_by_label)

        recorder = ScreencastRecorder(page, jpeg_quality=args.jpeg_quality, max_width=width, max_height=height)
        timelines: list[dict] = []
        for sequence_number, spec in enumerate(switch_specs, start=1):
            from_letter, _, to_letter = spec.partition("-to-")
            from_label, to_label = label_by_letter[from_letter], label_by_letter[to_letter]
            switch_name = f"switch_{sequence_number:02d}_{spec}"

            # Make sure we start on the "from" workspace, outside the recording.
            page.get_by_test_id("WORKSPACE_TAB").nth(row_index_by_label[from_label]).click()
            _wait_for_workspace_url(page, seeded[from_label]["workspaceId"])
            time.sleep(1.5)

            timelines.append(
                _capture_switch(
                    page=page,
                    recorder=recorder,
                    out_dir=out_dir,
                    switch_name=switch_name,
                    target_row_index=row_index_by_label[to_label],
                    target_workspace_id=seeded[to_label]["workspaceId"],
                    lead_ms=args.lead_ms,
                    settle_ms=args.settle_ms,
                )
            )
        recorder.detach()

        meta = {
            "viewport": args.viewport,
            "settle_ms": args.settle_ms,
            "lead_ms": args.lead_ms,
            "switches": switch_specs,
            "jpeg_quality": args.jpeg_quality,
            "headed": args.headed,
            "workspaces": seeded,
        }
        index_path = write_report(out_dir, timelines, meta)
        logger.info("Frame capture complete — open {}", index_path)
        print(f"\nFRAME_CAPTURE_REPORT={index_path}")
    finally:
        harness.stop()


if __name__ == "__main__":
    main()
