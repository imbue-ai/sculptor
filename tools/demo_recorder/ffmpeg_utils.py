"""Locate a working ffmpeg for the demo-recorder pipeline.

A system ffmpeg can be present but broken (e.g. a homebrew ffmpeg whose x265
dylib moved out from under it after a partial upgrade), so candidates are
validated by actually running them, and we require the libx264 encoder because
every output in this pipeline is H.264. The static binary shipped in the
``imageio-ffmpeg`` wheel is the no-setup fallback: run scripts with
``uv run --project sculptor --with imageio-ffmpeg ...`` to make it available.

ffprobe is deliberately not required — ``probe_video`` parses ``ffmpeg -i``
stderr instead, since the static wheel ships only the ffmpeg binary.
"""

from __future__ import annotations

import functools
import importlib
import os
import re
import shutil
import subprocess

# Optional static-ffmpeg fallback; present when scripts run under
# ``uv run --with imageio-ffmpeg``.
try:
    imageio_ffmpeg = importlib.import_module("imageio_ffmpeg")
except ImportError:
    imageio_ffmpeg = None


class FfmpegNotFoundError(RuntimeError):
    pass


def _is_working_ffmpeg(path: str) -> bool:
    try:
        result = subprocess.run(
            [path, "-hide_banner", "-h", "encoder=libx264"],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and "libx264" in result.stdout


@functools.cache
def resolve_ffmpeg() -> str:
    """Return the path of a runnable ffmpeg that can encode H.264."""
    env_override = os.environ.get("DEMO_RECORDER_FFMPEG")
    if env_override:
        if not _is_working_ffmpeg(env_override):
            raise FfmpegNotFoundError(f"DEMO_RECORDER_FFMPEG={env_override} is not a working ffmpeg with libx264")
        return env_override

    system = shutil.which("ffmpeg")
    if system and _is_working_ffmpeg(system):
        return system

    if imageio_ffmpeg is not None:
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if _is_working_ffmpeg(exe):
            return exe

    raise FfmpegNotFoundError(
        "No working ffmpeg with libx264 found. Either fix the system ffmpeg (e.g. `brew reinstall ffmpeg`), "
        + "or run via `uv run --project sculptor --with imageio-ffmpeg ...`, "
        + "or set DEMO_RECORDER_FFMPEG to a working binary."
    )


_STREAM_RE = re.compile(r"Stream #\d+:\d+.*?Video:.*?\b(\d{2,5})x(\d{2,5})\b.*?([\d.]+)\s*fps")
_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def probe_video(path: str) -> dict:
    """Return {width, height, fps, duration} by parsing ``ffmpeg -i`` stderr.

    Works without ffprobe. Only intended for the well-formed single-video-stream
    files this pipeline produces.
    """
    result = subprocess.run(
        [resolve_ffmpeg(), "-hide_banner", "-i", path],
        capture_output=True,
        text=True,
    )
    # ffmpeg exits non-zero for "-i with no output", the stream info is still printed.
    stderr = result.stderr
    stream = _STREAM_RE.search(stderr)
    duration = _DURATION_RE.search(stderr)
    if not stream:
        raise ValueError(f"could not parse video stream info for {path}:\n{stderr[-2000:]}")
    info = {
        "width": int(stream.group(1)),
        "height": int(stream.group(2)),
        "fps": float(stream.group(3)),
    }
    if duration:
        hours, minutes, seconds = duration.groups()
        info["duration"] = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return info
