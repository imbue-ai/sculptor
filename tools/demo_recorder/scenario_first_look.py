"""Record a marketing take: create a workspace and watch the agent get to work.

Boots a throwaway Sculptor instance (backend + Vite, fresh test repo, real
Claude via local API keys), then drives it in a headless Chromium with a
human-like cursor while capturing full-resolution raw frames.

Run from the repo root:

    uv run --project sculptor python tools/demo_recorder/scenario_first_look.py \
        [--out-root ~/sculptor-marketing/takes] [--name my-take] \
        [--viewport 1600x1000] [--prompt "..."] [--watch-seconds 30]

Outputs one take directory containing the raw frames, an encoded master
(viewport x2 resolution, CFR 60), events.json (director actions on the video
timeline), and meta.json. Feed the master + a camera keyframes file to
``post/camera.py`` to produce the final pan/zoom edit.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).parent))
from director import Director  # noqa: E402
from recorder import ScreencastRecorder  # noqa: E402

from sculptor.testing.manual_test_harness import ManualTestHarness  # noqa: E402

DEFAULT_PROMPT = "Add a /health endpoint to the Flask app and cover it with a simple test"

# data-testid values from sculptor.constants.ElementIDs.
NEW_WORKSPACE_BUTTON = "[data-testid=SIDEBAR_NEW_WORKSPACE_BUTTON]"
NAME_INPUT = "[data-testid=WORKSPACE_NAME_INPUT]"
PROMPT_TEXTAREA = "[data-testid=NEW_WORKSPACE_PROMPT_TEXTAREA]"
CREATE_BUTTON = "[data-testid=NEW_WORKSPACE_CREATE_BUTTON]"
CHAT_INPUT = "[data-testid=CHAT_INPUT]"
# Appears when the agent becomes active on a workspace (there is no
# THINKING_INDICATOR test-id in the current UI).
STATUS_PILL = "[data-testid=STATUS_PILL]"
CHANGES_TAB = "[data-testid=PANEL_TAB-changes]"


async def _goto_with_retries(page, url: str, timeout_seconds: float = 60) -> None:
    """The Vite dev server compiles on first request; retry until it responds."""
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while True:
        try:
            await page.goto(url)
            return
        except Exception:
            if asyncio.get_event_loop().time() > deadline:
                raise
            await asyncio.sleep(1)


async def _dismiss_onboarding(page, timeout_seconds: float = 90) -> None:
    """Click through the onboarding wizard until the home sidebar appears.

    The pre-filled test config skips the telemetry/account steps, but the
    installation-check step keys off the local machine, so it still shows.
    This runs before capture starts — the take should open on the home page.
    """
    email_input = page.locator("[data-testid=ONBOARDING_EMAIL_INPUT]")
    advance_buttons = [
        page.locator("[data-testid=ONBOARDING_EMAIL_SUBMIT]"),
        page.locator("[data-testid=ONBOARDING_COMPLETE_BUTTON]"),
        page.locator("[data-testid=ADD_REPO_SUBMIT_BUTTON]"),
    ]
    home_ready = page.locator(NEW_WORKSPACE_BUTTON)
    deadline = asyncio.get_event_loop().time() + timeout_seconds
    while asyncio.get_event_loop().time() < deadline:
        if await home_ready.is_visible():
            return
        if await email_input.is_visible():
            await email_input.fill("demo@imbue.com")
        for button in advance_buttons:
            if await button.is_visible() and await button.is_enabled():
                await button.click()
                break
        await asyncio.sleep(1)
    raise TimeoutError("onboarding did not complete; home sidebar never appeared")


async def _watch(director: Director, seconds: float, rest: tuple[float, float]) -> None:
    """Idle beat: park the cursor at a neutral rest point and drift around it."""
    await director.move_to(*rest)
    deadline = asyncio.get_event_loop().time() + seconds
    while asyncio.get_event_loop().time() < deadline:
        await director.pause(3.5, label="watching")
        await director.drift(anchor=rest)


async def run_take(
    vite_url: str,
    out_dir: Path,
    *,
    viewport: dict[str, int],
    prompt: str,
    watch_seconds: float,
) -> None:
    overlay_path = Path(__file__).parent / "cursor_overlay.js"
    overlay_js = overlay_path.read_text() if overlay_path.exists() else None
    if overlay_js is None:
        print("WARNING: cursor_overlay.js not found — recording without a visible cursor")

    async with async_playwright() as p:
        # Mirror ManualTestHarness's browser flags: WebGL off so xterm.js uses
        # its canvas renderer, which actually paints in headless Chromium.
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-webgl", "--disable-webgl2", "--force-color-profile=srgb"],
        )
        context = await browser.new_context(viewport=viewport, device_scale_factor=2)
        page = await context.new_page()
        page.set_default_timeout(30_000)
        if overlay_js is not None:
            await page.add_init_script(overlay_js)

        recorder = ScreencastRecorder(page=page, out_dir=out_dir)
        director = Director(page=page)

        # Everything up to a settled home page happens off-camera.
        await _goto_with_retries(page, vite_url)
        await _dismiss_onboarding(page)
        await asyncio.sleep(2.0)

        await recorder.start()
        try:
            # Opening beat: land on home, cursor at rest, let the frame breathe.
            await director.place_cursor(viewport["width"] * 0.56, viewport["height"] * 0.72)
            await director.pause(1.6, label="opening")

            # Create a workspace: open the form, name it, type the task, submit.
            await director.click(NEW_WORKSPACE_BUTTON, label="new_workspace_button")
            await director.wait_for(PROMPT_TEXTAREA, label="new_workspace_form")
            await director.click(NAME_INPUT, label="name_input")
            await director.type_text("Health check endpoint")
            await director.click(PROMPT_TEXTAREA, label="prompt_textarea")
            await director.pause(0.4, label="before_typing")
            # First-run installs pre-fill a getting-started prompt here;
            # select-all so typing replaces it instead of splicing into it.
            await director.press("ControlOrMeta+a")
            await director.type_text(prompt)
            await director.pause(0.8, label="after_typing")
            await director.click(CREATE_BUTTON, label="create_workspace")

            # Workspace page: the agent spins up and starts working.
            await director.wait_for(CHAT_INPUT, timeout=90, label="workspace_open")
            director.mark("workspace_open")
            await director.wait_for(STATUS_PILL, timeout=90, label="agent_started")
            director.mark("agent_started")

            # Watch the agent stream for a while, then peek at the diff so the
            # take shows changes accumulating, then watch a little more. Rest
            # points sit over non-interactive space so no tooltips pop up.
            await _watch(director, watch_seconds / 2, (viewport["width"] * 0.57, viewport["height"] * 0.64))
            await director.click(CHANGES_TAB, label="open_changes_panel")
            director.mark("changes_panel_open")
            await _watch(director, watch_seconds / 2, (viewport["width"] * 0.30, viewport["height"] * 0.55))

            director.mark("closing")
            await director.pause(2.0, label="closing")
        finally:
            await recorder.stop()
            await director.save_events(
                out_dir / "events.json",
                video_start_timestamp=recorder.stats.first_timestamp,
            )
            await browser.close()

    master = recorder.build_master()
    recorder.write_meta(
        extra={
            "viewport": viewport,
            "device_scale_factor": 2,
            "prompt": prompt,
            "scenario": "first_look",
        }
    )
    print(f"\nTake recorded: {out_dir}")
    print(f"  master:  {master}")
    frame_stats = f"{recorder.stats.frame_count} frames, ~{recorder.stats.average_fps:.1f} fps captured"
    print(f"  frames:  {recorder.frames_dir} ({frame_stats})")
    print(f"  events:  {out_dir / 'events.json'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-root", type=Path, default=Path.home() / "sculptor-marketing" / "takes")
    parser.add_argument("--name", default=None, help="take name (default: timestamped)")
    parser.add_argument("--viewport", default="1600x1000")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--watch-seconds", type=float, default=30.0,
                        help="how long to film the agent working after it starts")
    parser.add_argument("--project-path", type=Path, default=None,
                        help="use a real repository instead of the generated test repo")
    args = parser.parse_args()

    width, height = (int(v) for v in args.viewport.split("x"))
    name = args.name or datetime.datetime.now().strftime("take-%Y%m%d-%H%M%S")
    out_dir = args.out_root.expanduser() / name
    out_dir.mkdir(parents=True, exist_ok=True)

    # Keep test-only "Fake Claude" models out of the model picker — this is
    # marketing footage of the real product.
    os.environ["SCULPTOR_MANUAL_TEST_HIDE_FAKE_MODELS"] = "1"

    harness = ManualTestHarness(project_path=args.project_path)
    harness.start_servers()
    try:
        asyncio.run(
            run_take(
                harness.vite_url,
                out_dir,
                viewport={"width": width, "height": height},
                prompt=args.prompt,
                watch_seconds=args.watch_seconds,
            )
        )
    finally:
        harness.stop()


if __name__ == "__main__":
    main()
