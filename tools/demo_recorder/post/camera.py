#!/usr/bin/env python3
"""Keyframed virtual camera (pan + zoom) for demo-recorder masters.

Takes a raw high-resolution master (e.g. 3200x2000@60 from recorder.py), a
hand-authored camera JSON, and renders a delivery mp4 — or a single PNG for
framing iteration — with smooth, eased camera motion: the "Ken Burns" pass
that turns a flat screen recording into a cinematic cut.

Usage:
    # render the edit
    python camera.py --input master.mp4 --camera shots.json --output out.mp4 \\
        [--size 1920x1080] [--fps 30] [--crf 18] [--preview] [--add-silent-audio]

    # iterate on framing: one frame at t=12.5s, fast
    python camera.py --input master.mp4 --camera shots.json --still 12.5 --output frame.png

Camera JSON:

    {"keyframes": [
      {"t": 0.0,  "zoom": 1.0, "cx": 0.5,  "cy": 0.5},
      {"t": 4.0,  "zoom": 1.0, "cx": 0.5,  "cy": 0.5},
      {"t": 6.5,  "zoom": 2.2, "cx": 0.32, "cy": 0.55, "ease": "smooth"}
    ]}

    t      Seconds on the master's timeline. Required, >= 0, strictly
           ascending across keyframes.
    zoom   1.0 is the widest possible framing: the largest rect with the
           OUTPUT's aspect ratio that fits inside the source (for a 16:10
           source and a 16:9 output that is the full source width with a
           sliver of height cropped). zoom 2.0 magnifies that framing 2x,
           i.e. shows half of its width. Must be >= 1.
    cx,cy  View center in normalized source coordinates (0..1 across the
           full source; 0.5,0.5 is dead center). The view rect is clamped to
           stay entirely inside the source, so centers near an edge saturate
           instead of revealing beyond-edge content; at zoom 1.0 the
           coordinate along the source's tighter axis is effectively pinned.
    ease   How the segment ENDING at this keyframe is interpolated:
             "smooth"  smoothstep u*u*(3-2u); gentle ramp in and out (default)
             "linear"  constant-rate motion
             "hold"    keep the previous keyframe's values until this t,
                       then jump — a hard cut to this keyframe's framing
           zoom/cx/cy interpolate together, with the same easing.

    A keyframe may omit zoom/cx/cy; omitted values inherit the previous
    keyframe's (the first keyframe defaults to zoom 1.0, centered), so a
    keyframe can change a single parameter. The camera holds before the
    first keyframe and after the last. Keys starting with "_" are ignored
    everywhere — use them for inline comments.

Rendering (one ffmpeg pass):

    fps=FPS -> yuv444 -> sendcmd -> crop@coarse -> scale@mid (lanczos)
        -> crop@fine -> scale@out (lanczos) -> yuv420 -> libx264 +faststart

    The camera is evaluated per output frame in Python and driven into the
    filtergraph via sendcmd: an integer pre-crop at source resolution (with
    margin for the resampler taps), a lanczos upscale that maps the exact
    float view rect onto a supersampled canvas (CANVAS_SCALE x the output
    size), a constant-size crop on that canvas, and a final lanczos
    downscale to the delivery size. Motion is thereby quantized to
    1/CANVAS_SCALE of an OUTPUT pixel, which keeps slow pans smooth;
    single-filter routes (zoompan, or an animated crop at source
    resolution) snap the window to whole input pixels and judder. The fine
    crop has exactly the output's aspect ratio at every frame, so circles
    stay circular for any source/output aspect combination. The yuv444
    intermediate avoids chroma misalignment on odd crop offsets when the
    master is 4:2:0.

ffmpeg is located via ffmpeg_utils.resolve_ffmpeg() (ffprobe is not needed).
If the system ffmpeg is unusable, run via
`uv run --project sculptor --with imageio-ffmpeg python ...` to make the
static fallback binary importable, or set DEMO_RECORDER_FFMPEG.
"""

from __future__ import annotations

import argparse
import json
import math
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

# ffmpeg_utils lives one directory up (tools/demo_recorder/).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ffmpeg_utils import probe_video  # noqa: E402
from ffmpeg_utils import resolve_ffmpeg  # noqa: E402

EASINGS = ("smooth", "linear", "hold")

# The fine-crop canvas is CANVAS_SCALE x the output size, so camera motion is
# quantized to 1/CANVAS_SCALE of an output pixel. 2x keeps sub-pixel steps
# invisible after the final lanczos downscale while the mid-stage upscale
# (the most expensive op in the graph) stays affordable.
CANVAS_SCALE_NUM = 2
CANVAS_SCALE_DEN = 1

# Extra source pixels around the coarse crop so the mid-scale's lanczos taps
# sample real content at the edges of the fine rect instead of clamped pixels.
COARSE_MARGIN = 8

# The mid scale is yuv444 -> yuv444, where the full-chroma/rounding refinements
# are no-ops, so it runs plain lanczos; the output scale performs the final
# 4:2:0 (or rgb) conversion and keeps the precision flags.
SWS_FLAGS_MID = "lanczos"
SWS_FLAGS_OUT = "lanczos+accurate_rnd+full_chroma_int+full_chroma_inp"

# swscale is single-threaded by default and dominates render time; cap the
# per-filter threads since scaling gains flatten out beyond this.
SWS_THREADS = 8

DEFAULT_SIZE = (1920, 1080)
DEFAULT_FPS = 30.0
DEFAULT_CRF = 18
PREVIEW_CRF = 23


class CameraError(ValueError):
    """A problem with the camera JSON or the CLI arguments."""


@dataclass(frozen=True)
class Keyframe:
    t: float
    zoom: float
    cx: float
    cy: float
    # Easing of the segment that ENDS at this keyframe (ignored on the first).
    ease: str


@dataclass(frozen=True)
class ViewRect:
    """The source-pixel rect the camera shows; always at the output aspect."""

    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class FrameGeometry:
    """Integer filter parameters realizing a ViewRect for one output frame."""

    coarse_w: int
    coarse_h: int
    coarse_x: int
    coarse_y: int
    mid_w: int
    mid_h: int
    fine_x: int
    fine_y: int


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


class Camera:
    """Evaluates zoom/cx/cy at any time from the keyframe list."""

    def __init__(self, keyframes: list[Keyframe]) -> None:
        self.keyframes = keyframes
        self._times = [kf.t for kf in keyframes]

    def state_at(self, t: float) -> tuple[float, float, float]:
        kfs = self.keyframes
        # Index of the segment's starting keyframe: rightmost with kf.t <= t.
        i = bisect_right(self._times, t) - 1
        if i < 0:
            first = kfs[0]
            return first.zoom, first.cx, first.cy
        if i >= len(kfs) - 1:
            last = kfs[-1]
            return last.zoom, last.cx, last.cy
        a, b = kfs[i], kfs[i + 1]
        u = (t - a.t) / (b.t - a.t)
        if b.ease == "hold":
            # Values jump only when t reaches b.t, at which point bisect
            # selects the next segment (or the final hold) and returns b's
            # values exactly.
            eased = 0.0
        elif b.ease == "linear":
            eased = u
        else:  # smooth
            eased = u * u * (3.0 - 2.0 * u)
        return (
            a.zoom + (b.zoom - a.zoom) * eased,
            a.cx + (b.cx - a.cx) * eased,
            a.cy + (b.cy - a.cy) * eased,
        )

    def max_zoom(self) -> float:
        # Interpolated values never overshoot the keyframe values (all
        # easings map into [0, 1]), so the max over keyframes is exact.
        return max(kf.zoom for kf in self.keyframes)


def _read_number(raw: dict, where: str, key: str, default: float, lo: float, hi: float, hint: str) -> float:
    value = raw.get(key, default)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise CameraError(f'{where}: "{key}" must be a number')
    if not lo <= value <= hi:
        raise CameraError(f'{where}: "{key}" must be in [{lo:g}, {hi:g}] ({hint}), got {value}')
    return float(value)


def load_camera(path: Path) -> tuple[Camera, list[str]]:
    """Parse and validate the camera JSON; returns (camera, warnings)."""
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        raise CameraError(f"camera file not found: {path}")
    except json.JSONDecodeError as exc:
        raise CameraError(f"{path} is not valid JSON: {exc}")

    warnings: list[str] = []
    if not isinstance(data, dict) or "keyframes" not in data:
        raise CameraError(f'{path}: expected a top-level object with a "keyframes" array')
    for key in data:
        if key != "keyframes" and not key.startswith("_"):
            warnings.append(f'{path}: ignoring unknown top-level key "{key}"')
    raw_keyframes = data["keyframes"]
    if not isinstance(raw_keyframes, list) or not raw_keyframes:
        raise CameraError(f'{path}: "keyframes" must be a non-empty array')

    known = {"t", "zoom", "cx", "cy", "ease"}
    keyframes: list[Keyframe] = []
    prev_zoom, prev_cx, prev_cy = 1.0, 0.5, 0.5
    for index, raw in enumerate(raw_keyframes):
        where = f"{path}: keyframes[{index}]"
        if not isinstance(raw, dict):
            raise CameraError(f"{where}: expected an object, got {type(raw).__name__}")
        for key in raw:
            if key not in known and not key.startswith("_"):
                warnings.append(f'{where}: ignoring unknown key "{key}" (typo?)')

        t = raw.get("t")
        if not isinstance(t, (int, float)) or isinstance(t, bool):
            raise CameraError(f'{where}: "t" (seconds) is required and must be a number')
        if t < 0:
            raise CameraError(f'{where}: "t" must be >= 0, got {t}')
        if keyframes and t <= keyframes[-1].t:
            raise CameraError(f'{where}: "t" values must be strictly ascending (t={t} follows t={keyframes[-1].t})')

        zoom = _read_number(raw, where, "zoom", prev_zoom, 1.0, 1000.0, "1.0 is the widest framing; zoom in only")
        cx = _read_number(raw, where, "cx", prev_cx, 0.0, 1.0, "normalized source coordinates")
        cy = _read_number(raw, where, "cy", prev_cy, 0.0, 1.0, "normalized source coordinates")

        ease = raw.get("ease", "smooth")
        if ease not in EASINGS:
            raise CameraError(f'{where}: "ease" must be one of {", ".join(EASINGS)}; got {ease!r}')
        if index == 0 and "ease" in raw:
            warnings.append(f'{where}: "ease" on the first keyframe has no effect (it shapes the segment ending at a keyframe)')

        keyframes.append(Keyframe(t=float(t), zoom=zoom, cx=cx, cy=cy, ease=ease))
        prev_zoom, prev_cx, prev_cy = zoom, cx, cy

    return Camera(keyframes), warnings


def zoom1_rect(src_w: int, src_h: int, out_w: int, out_h: int) -> tuple[float, float]:
    """Size of the largest output-aspect rect that fits inside the source."""
    aspect = out_w / out_h
    rect_w = min(float(src_w), src_h * aspect)
    return rect_w, rect_w / aspect


def view_rect_at(
    camera: Camera, t: float, src_w: int, src_h: int, rect0: tuple[float, float]
) -> ViewRect:
    zoom, cx, cy = camera.state_at(t)
    w = rect0[0] / zoom
    h = rect0[1] / zoom
    # Clamp the center so the rect stays entirely inside the source.
    px = _clamp(cx * src_w, w / 2.0, src_w - w / 2.0)
    py = _clamp(cy * src_h, h / 2.0, src_h - h / 2.0)
    return ViewRect(px - w / 2.0, py - h / 2.0, w, h)


def frame_geometry(
    rect: ViewRect, src_w: int, src_h: int, canvas_w: int, canvas_h: int
) -> FrameGeometry:
    coarse_x = max(int(rect.x) - COARSE_MARGIN, 0)
    coarse_y = max(int(rect.y) - COARSE_MARGIN, 0)
    coarse_w = min(int(rect.x + rect.w) + 1 + COARSE_MARGIN, src_w) - coarse_x
    coarse_h = min(int(rect.y + rect.h) + 1 + COARSE_MARGIN, src_h) - coarse_y
    # One uniform scale factor maps the view rect onto the canvas exactly;
    # because rect and canvas share the output aspect, the same factor holds
    # for both axes and the crop introduces no distortion.
    k = canvas_w / rect.w
    mid_w = round(coarse_w * k)
    mid_h = round(coarse_h * k)
    fine_x = min(max(round((rect.x - coarse_x) * k), 0), mid_w - canvas_w)
    fine_y = min(max(round((rect.y - coarse_y) * k), 0), mid_h - canvas_h)
    return FrameGeometry(coarse_w, coarse_h, coarse_x, coarse_y, mid_w, mid_h, fine_x, fine_y)


def quote_filter_value(value: str) -> str:
    """Quote a string for use as a filter option value in a filtergraph."""
    return "'" + value.replace("'", r"'\''") + "'"


def sws_threads_option() -> str:
    """The scale filter's threads option, or "" where this ffmpeg lacks it."""
    result = subprocess.run(
        [resolve_ffmpeg(), "-hide_banner", "-h", "filter=scale"],
        capture_output=True,
        text=True,
    )
    if "threads" in result.stdout:
        return f":threads={SWS_THREADS}"
    return ""


def plan_render(
    camera: Camera,
    src_w: int,
    src_h: int,
    duration: float,
    out_w: int,
    out_h: int,
    fps: float,
) -> tuple[list[str], FrameGeometry, float]:
    """Per-frame sendcmd lines, the first frame's geometry, and the peak
    magnification of source pixels (>1 means upscaling past native)."""
    rect0 = zoom1_rect(src_w, src_h, out_w, out_h)
    canvas_w = out_w * CANVAS_SCALE_NUM // CANVAS_SCALE_DEN
    canvas_h = out_h * CANVAS_SCALE_NUM // CANVAS_SCALE_DEN

    # A couple of spare command lines past the planned end are harmless
    # (frames that never materialize simply leave commands unfired).
    frame_count = max(1, math.ceil(duration * fps)) + 2
    lines: list[str] = []
    first: FrameGeometry | None = None
    max_magnification = 0.0
    for n in range(frame_count):
        t = n / fps
        rect = view_rect_at(camera, t, src_w, src_h, rect0)
        geo = frame_geometry(rect, src_w, src_h, canvas_w, canvas_h)
        if first is None:
            first = geo
        max_magnification = max(max_magnification, out_w / rect.w)
        # Timestamps sit a quarter frame early so float formatting can never
        # push a command past the frame it targets. The constant fine-crop
        # size is resent every frame: a size command forces the crop filter
        # to reconfigure after its input size changed upstream.
        ts = 0.0 if n == 0 else (n - 0.25) / fps
        commands = ", ".join(
            [
                f"crop@coarse w {geo.coarse_w}",
                f"crop@coarse h {geo.coarse_h}",
                f"crop@coarse x {geo.coarse_x}",
                f"crop@coarse y {geo.coarse_y}",
                f"scale@mid w {geo.mid_w}",
                f"scale@mid h {geo.mid_h}",
                f"crop@fine w {canvas_w}",
                f"crop@fine h {canvas_h}",
                f"crop@fine x {geo.fine_x}",
                f"crop@fine y {geo.fine_y}",
            ]
        )
        lines.append(f"{ts:.6f} {commands};")
    assert first is not None
    return lines, first, max_magnification


def build_render_graph(
    first: FrameGeometry,
    cmd_path: Path,
    out_w: int,
    out_h: int,
    fps: float,
) -> str:
    canvas_w = out_w * CANVAS_SCALE_NUM // CANVAS_SCALE_DEN
    canvas_h = out_h * CANVAS_SCALE_NUM // CANVAS_SCALE_DEN
    threads = sws_threads_option()
    # setpts normalizes a nonzero container start time so camera t=0 is the
    # first frame. The final scale also performs the yuv444->yuv420
    # conversion (the trailing format filter only pins negotiation), so the
    # chroma downsample uses the high-quality flags.
    chain = [
        f"[0:v]setpts=PTS-STARTPTS,fps={fps:g},format=yuv444p",
        f"sendcmd=f={quote_filter_value(str(cmd_path))}",
        f"crop@coarse={first.coarse_w}:{first.coarse_h}:{first.coarse_x}:{first.coarse_y}",
        f"scale@mid={first.mid_w}:{first.mid_h}:flags={SWS_FLAGS_MID}{threads}",
        f"crop@fine={canvas_w}:{canvas_h}:{first.fine_x}:{first.fine_y}",
        f"scale@out={out_w}:{out_h}:flags={SWS_FLAGS_OUT}{threads}",
        "setsar=1,format=yuv420p[vout]",
    ]
    return ",".join(chain)


def build_still_filter(rect: ViewRect, src_w: int, src_h: int, out_w: int, out_h: int) -> str:
    # A single frame has no motion to keep smooth, so a plain integer crop at
    # source resolution is enough (at most half a pixel of framing skew) and
    # renders near-instantly. The rounded crop is re-clamped to the source so
    # x and w rounding up together cannot spill past an edge. The scale
    # performs the rgb conversion for the image encoder with the same
    # high-quality flags as a full render.
    crop_w = min(max(round(rect.w), 2), src_w)
    crop_h = min(max(round(rect.h), 2), src_h)
    crop_x = min(max(round(rect.x), 0), src_w - crop_w)
    crop_y = min(max(round(rect.y), 0), src_h - crop_h)
    chain = [
        f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y}",
        f"scale={out_w}:{out_h}:flags={SWS_FLAGS_OUT}",
        "format=rgb24,setsar=1",
    ]
    return ",".join(chain)


def run_ffmpeg(cmd: list[str]) -> None:
    print("+ " + shlex.join(cmd), flush=True)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        raise SystemExit(f"error: ffmpeg exited with status {result.returncode}")


def parse_size(text: str) -> tuple[int, int]:
    parts = text.lower().split("x")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise CameraError(f"--size must look like 1920x1080, got {text!r}")
    w, h = int(parts[0]), int(parts[1])
    if w < 16 or h < 16:
        raise CameraError(f"--size {text}: too small to encode")
    if w % 2 or h % 2:
        raise CameraError(f"--size {text}: width and height must be even (4:2:0 H.264)")
    return w, h


def render_video(args: argparse.Namespace, camera: Camera, info: dict) -> None:
    out_w, out_h = parse_size(args.size)
    if "duration" not in info:
        raise CameraError(f"{args.input}: could not determine duration; remux the file first")
    duration = info["duration"]

    fps = args.fps if args.fps is not None else DEFAULT_FPS
    if args.preview:
        fps = max(1.0, fps / 2.0)
    crf = args.crf if args.crf is not None else (PREVIEW_CRF if args.preview else DEFAULT_CRF)
    preset = "veryfast" if args.preview else "slow"

    lines, first, max_magnification = plan_render(
        camera, info["width"], info["height"], duration, out_w, out_h, fps
    )
    if max_magnification > 1.02:
        warning = (
            f"warning: the camera magnifies source pixels up to {max_magnification:.2f}x"
            + " past native resolution; those segments will look softer"
        )
        print(warning, file=sys.stderr)

    temp_dir = Path(tempfile.mkdtemp(prefix="camera_render_"))
    cmd_path = temp_dir / "camera.cmd"
    graph_path = temp_dir / "graph.txt"
    cmd_path.write_text("\n".join(lines) + "\n")
    graph_path.write_text(build_render_graph(first, cmd_path, out_w, out_h, fps))

    ffmpeg = resolve_ffmpeg()
    cmd = [ffmpeg, "-hide_banner", "-v", "error", "-stats", "-y", "-i", str(args.input)]
    if args.add_silent_audio:
        cmd += ["-f", "lavfi", "-t", f"{duration:.3f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"]
    cmd += ["-filter_complex_script", str(graph_path), "-map", "[vout]"]
    if args.add_silent_audio:
        cmd += ["-map", "1:a", "-c:a", "aac", "-b:a", "128k", "-shortest"]
    cmd += [
        "-c:v", "libx264",
        "-profile:v", "high",
        "-preset", preset,
        "-crf", str(crf),
        "-movflags", "+faststart",
        str(args.output),
    ]

    source_desc = f"{args.input}: {info['width']}x{info['height']} @ {info['fps']:g} fps, {duration:.2f}s"
    target_desc = f"{out_w}x{out_h} @ {fps:g} fps, crf {crf}, preset {preset}"
    audio_desc = ", silent audio" if args.add_silent_audio else ""
    print(f"{source_desc} -> {target_desc}{audio_desc}")
    started = time.monotonic()
    try:
        run_ffmpeg(cmd)
    except SystemExit:
        print(f"note: keeping filter files for inspection in {temp_dir}", file=sys.stderr)
        raise
    elapsed = time.monotonic() - started
    shutil.rmtree(temp_dir, ignore_errors=True)

    frames = math.ceil(duration * fps)
    size_mb = Path(args.output).stat().st_size / 1e6
    speed = f"{frames / elapsed:.0f} fps, {duration / elapsed:.1f}x realtime"
    print(f"wrote {args.output} ({size_mb:.1f} MB): ~{frames} frames in {elapsed:.1f}s ({speed})")


def render_still(args: argparse.Namespace, camera: Camera, info: dict) -> None:
    out_w, out_h = parse_size(args.size)
    t = args.still
    if t < 0:
        raise CameraError(f"--still {t}: time must be >= 0")
    duration = info.get("duration")
    if duration is not None and t >= duration:
        raise CameraError(f"--still {t}: beyond the input's duration ({duration:.2f}s)")
    for flag, name in ((args.preview, "--preview"), (args.add_silent_audio, "--add-silent-audio"),
                       (args.fps is not None, "--fps"), (args.crf is not None, "--crf")):
        if flag:
            print(f"warning: {name} has no effect with --still", file=sys.stderr)

    rect0 = zoom1_rect(info["width"], info["height"], out_w, out_h)
    rect = view_rect_at(camera, t, info["width"], info["height"], rect0)
    zoom, cx, cy = camera.state_at(t)
    rect_desc = f"source rect {rect.w:.1f}x{rect.h:.1f}+{rect.x:.1f}+{rect.y:.1f}"
    print(f"still at t={t:g}s: zoom {zoom:.3f} centered ({cx:.3f}, {cy:.3f}) -> {rect_desc}")

    ffmpeg = resolve_ffmpeg()
    # -ss before -i: demuxer-level seek to the preceding keyframe, then
    # accurate decode up to t. This is the fast path for framing iteration.
    cmd = [
        ffmpeg, "-hide_banner", "-v", "error", "-y",
        "-ss", f"{t:.6f}", "-i", str(args.input),
        "-frames:v", "1", "-update", "1",
        "-vf", build_still_filter(rect, info["width"], info["height"], out_w, out_h),
        str(args.output),
    ]
    run_ffmpeg(cmd)
    print(f"wrote {args.output}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply a keyframed pan/zoom camera to a demo master. See the module docstring for the camera JSON format.",
    )
    parser.add_argument("--input", required=True, type=Path, help="master video (any aspect/fps)")
    parser.add_argument("--camera", required=True, type=Path, help="camera keyframes JSON")
    parser.add_argument("--output", required=True, type=Path, help="output mp4 (or image with --still)")
    parser.add_argument("--size", default=f"{DEFAULT_SIZE[0]}x{DEFAULT_SIZE[1]}",
                        help="output WxH (default %(default)s; both even)")
    parser.add_argument("--fps", type=float, default=None,
                        help=f"output frame rate (default {DEFAULT_FPS:g}; halved by --preview)")
    parser.add_argument("--crf", type=int, default=None,
                        help=f"libx264 CRF (default {DEFAULT_CRF}, or {PREVIEW_CRF} with --preview)")
    parser.add_argument("--preview", action="store_true",
                        help="fast draft encode: veryfast preset, half fps, crf %d" % PREVIEW_CRF)
    parser.add_argument("--add-silent-audio", action="store_true",
                        help="mux a silent stereo AAC track (some platforms want an audio stream)")
    parser.add_argument("--still", type=float, default=None, metavar="T",
                        help="render a single image at time T seconds instead of a video")
    args = parser.parse_args(argv)

    try:
        if args.crf is not None and not 0 <= args.crf <= 51:
            raise CameraError(f"--crf {args.crf}: valid range is 0..51")
        if args.fps is not None and args.fps <= 0:
            raise CameraError(f"--fps {args.fps}: must be positive")
        if not args.input.exists():
            raise CameraError(f"input not found: {args.input}")
        camera, warnings = load_camera(args.camera)
        info = probe_video(str(args.input))
        duration = info.get("duration")
        if duration is not None and camera.keyframes[-1].t > duration + 0.5:
            last_t = camera.keyframes[-1].t
            warnings.append(
                f"last keyframe at t={last_t:g}s is beyond the input's duration ({duration:.2f}s); "
                + "the camera will simply hold at the end"
            )
        for warning in warnings:
            print(f"warning: {warning}", file=sys.stderr)
        if args.still is not None:
            render_still(args, camera, info)
        else:
            render_video(args, camera, info)
    except CameraError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
