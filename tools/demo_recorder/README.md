# Demo recorder

Playwright-based pipeline for recording marketing footage of Sculptor without a
human at the mouse: a headless, scripted "screen recording" with a smooth
synthetic cursor and click effects, plus a post step for cinematic pan/zoom
camera moves. Twitter-ready output.

All commands run from the repo root. The `--with imageio-ffmpeg` flag makes a
static ffmpeg available so nothing depends on the state of the system ffmpeg
(see "ffmpeg resolution" below).

## Workflow

### 1. Record a take

```bash
uv run --project sculptor --with imageio-ffmpeg \
  python tools/demo_recorder/scenario_first_look.py \
  [--name my-take] [--prompt "..."] [--watch-seconds 28] [--project-path /repo]
```

This boots a throwaway Sculptor instance (backend + Vite dev server + a fresh
test repo; real Claude via your local keys), dismisses onboarding off-camera,
then records: home page → new workspace form → name + task typed in → create →
the agent starts working → Changes panel. Roughly 55 seconds per take.

Output lands in `~/sculptor-marketing/takes/<name>/`:

| file | what it is |
|---|---|
| `frames/` + `frames.jsonl` | the true raw capture: full-resolution (viewport × 2) lossless PNG frames with exact per-frame timestamps |
| `master.mp4` | those frames encoded 3200×2000, CFR 60fps, visually lossless — the editing source |
| `events.json` | every director action (clicks, typing, waits, marks) with `video_t0`/`video_t1` on the master's timeline and element bounding boxes in CSS px |
| `meta.json` | capture stats (achieved fps, viewport, prompt) |

Takes are archival: keep `frames/` if you may ever want to re-master; only
`master.mp4` is needed for editing.

If a run crashes after capture but before assembly, rebuild the master with:

```bash
uv run --project sculptor --with imageio-ffmpeg \
  python tools/demo_recorder/recorder.py ~/sculptor-marketing/takes/<name>
```

### 2. Author the camera

Write a `shots.json` next to the master (see `post/example_camera.json` and the
`post/camera.py` docstring for the full format):

```json
{"keyframes": [
  {"t": 0.0,  "zoom": 1.0,  "cx": 0.5,   "cy": 0.5,  "_beat": "open wide"},
  {"t": 4.4,  "zoom": 1.55, "cx": 0.503, "cy": 0.34, "_beat": "push into the form"}
]}
```

Don't scrub video for beat times — read them from `events.json` (`video_t0` of
each click/type event), and derive `cx`/`cy` from the logged bounding boxes
(`cx = (bbox.x + bbox.width/2) / viewport.width`).

Iterate on framing with single stills (~1s each):

```bash
uv run --project sculptor --with imageio-ffmpeg \
  python tools/demo_recorder/post/camera.py \
  --input master.mp4 --camera shots.json --still 12.5 --output check.png
```

### 3. Render the edit

```bash
uv run --project sculptor --with imageio-ffmpeg \
  python tools/demo_recorder/post/camera.py \
  --input master.mp4 --camera shots.json --output final.mp4 \
  --size 1920x1080 --fps 30
```

Output is H.264 high / yuv420p / `+faststart` — Twitter-compatible as-is
(`--add-silent-audio` muxes a silent AAC track if a platform demands one;
`--preview` renders fast and rough). Renders at roughly 2× realtime.

## Pieces

- `recorder.py` — raw capture. Pumps CDP `Page.captureScreenshot` with
  `clip.scale=2`, keeping 2-3 captures in flight (~45fps at 3200×2000; a
  single capture caps at ~27fps). This is the only route to above-CSS-pixel
  frames: `Page.startScreencast` (and Playwright's built-in `record_video_dir`)
  silently ignores the device scale factor. Frame timestamps share the
  `time.time()` wall clock with the event log, so no sync markers are needed.
  Knobs: `capture_scale`, `target_fps`, `inflight`, `frame_format`
  (png/jpeg), plus a `screencast` mode for CSS-resolution/high-fps captures.
- `director.py` — human-like input driving the REAL Playwright mouse and
  keyboard (hover states react like they would for a person): bezier paths
  with minimum-jerk timing, per-character typing cadence, click jitter,
  anchored idle drift (free-wandering drift eventually hovers a control and
  pops a tooltip into the shot). Logs `events.json`.
- `cursor_overlay.js` — injected into the recorded page; draws a macOS-style
  cursor (arrow/hand/I-beam by hovered element) with press + ripple click
  effects. Headless recordings have no OS cursor without this.
- `scenario_first_look.py` — the staged take described above. Notable traps it
  handles: the onboarding installation step appears even with a pre-filled
  test config (clicked through before capture starts), and the new-workspace
  prompt textarea pre-fills a getting-started prompt on first run
  (select-all before typing).
- `post/camera.py` — keyframed virtual camera rendered in one ffmpeg pass via
  `sendcmd` with sub-pixel motion (deliberately not `zoompan`, which snaps the
  window to whole input pixels and judders on slow moves).
- `ffmpeg_utils.py` — ffmpeg resolution + ffprobe-free probing.

## ffmpeg resolution

`ffmpeg_utils.resolve_ffmpeg()` picks, in order: `$DEMO_RECORDER_FFMPEG`, a
system ffmpeg that actually runs and has libx264, then the static binary from
the `imageio-ffmpeg` wheel (hence `--with imageio-ffmpeg`). Candidates are
validated by running them — a present-but-broken brew ffmpeg (e.g. dangling
x265 dylib after a partial upgrade) is skipped automatically. No ffprobe is
required anywhere.

## Current limitations

- Records the web UI in a browser: no Electron window chrome. A fake macOS
  window frame + backdrop could be composited in post.
- Dev-build version label is visible bottom-left; the default staged repo is a
  toy Flask app (`--project-path` accepts a real one).
- No retiming — typing plays at recorded speed. Speed ramps would live in
  `post/camera.py`.
- Agent output is real Claude, so content varies per take. FakeClaude could
  script fully deterministic takes.
