---
name: frame-capture
description: |
  Capture every compositor frame around workspace tab switches and produce an
  HTML contact sheet for frame-by-frame inspection. Use when diagnosing or
  verifying workspace-switch rendering problems: stale panel content from the
  previous workspace, layout shift, or slow progressive load-in.
---

# Workspace-switch frame capture

Records the CDP screencast (every frame the compositor actually produced)
while clicking between two seeded workspaces, then writes numbered JPEG frames
and a self-contained `index.html` contact sheet. The renderer's `ws-switch.*`
performance marks (from `frontend/src/common/perf/workspaceSwitchProfiler.ts`)
appear as labeled dividers between frames, so the stale-content window is
bracketed visually.

## Run a capture

```bash
uv run --project sculptor python -m sculptor.testing.frame_capture \
  --out-dir /tmp/ws_switch_frames \
  --switches a-to-b,b-to-a,a-to-b
```

Takes a few minutes: it launches a backend + Vite dev server via
`ManualTestHarness`, seeds two workspaces (ALPHA / BRAVO) with deterministic
FakeClaude content (distinct chat text, committed + uncommitted files), then
performs the switch sequence. The first `a-to-b` is a cold switch; repeats are
warm. The script prints `FRAME_CAPTURE_REPORT=<path to index.html>` at the end.

Options: `--settle-ms` (capture window after the click, default 4000),
`--lead-ms` (pre-click lead-in, default 300), `--jpeg-quality`, `--viewport`,
`--headed` (headed Chromium for fidelity checks).

## Read the results

Open `index.html` (or read the per-switch `timeline.json` files). Each switch
section shows a filmstrip of distinct frames captioned with their offset from
the click (`×N` badges mark collapsed identical frames; pre-click frames are
dimmed). What to look for:

- **Stale content**: any frame showing ALPHA chat/files after a click toward
  BRAVO (or vice versa). These appear between the click and the
  `layout-restored` / `first-paint-after-restore` dividers.
- **Layout shift**: section sizes/visibility jumping between consecutive frames.
- **Progressive load-in**: how many distinct frames (and how much time) until
  the final stable frame; which panels fill in last relative to the
  `chat-loaded` / `diff-loaded` / `files-loaded` dividers.

For an agent: read a handful of frames around the click with the Read tool
(they are plain JPEGs) rather than every frame; `timeline.json` has the
offsets to pick interesting ones.

## Caveats

- Runs against the Vite dev build (unminified, StrictMode): treat durations as
  relative. Frame content and ordering are the trustworthy signal. For
  production-grade timing, use the `/perf-compare` skill or tracing.
- Headless compositor frame pacing differs from headed Chrome; use `--headed`
  when absolute frame counts matter.
- Both seeded workspaces share one IN_PLACE repo, so the uncommitted seed
  files appear in both workspaces' Changes panels — the chat content is the
  unambiguous per-workspace signal.
