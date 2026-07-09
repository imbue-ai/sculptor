"""Raw screen capture for marketing demo recordings.

Captures a Playwright page into individually timestamped frames plus an
encoded "master" video, keeping full device resolution so post-production can
pan and zoom without going soft.

Two capture modes:

- ``screenshot`` (default): a paced pump of CDP ``Page.captureScreenshot``
  calls with ``clip.scale`` set to the capture scale. This is the only way to
  get frames at ABOVE-CSS resolution (a 1600x1000 viewport at scale 2 yields
  3200x2000 frames); ``Page.startScreencast`` silently delivers CSS-pixel
  frames no matter the device scale factor. A single capture round-trip caps
  out well below real-time at that size, so ``inflight`` captures are kept in
  flight concurrently (measured on Apple Silicon: ~27fps with 1, ~45-60fps
  with 2-3). Completion order can swap under pipelining, so every frame is
  tagged with its capture-start wall-clock time and the timeline is sorted by
  that.
- ``screencast``: CDP ``Page.startScreencast``. Higher and more even fps, but
  CSS-resolution frames — fine when no zooming is planned.

Frame timestamps use the same wall clock as ``time.time()``, so director
events align with video time without sync markers. The frames on disk are the
true raw capture; ``build_master`` resamples them to a constant-frame-rate
H.264 via ffmpeg's concat demuxer.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import subprocess
import time
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from playwright.async_api import CDPSession
from playwright.async_api import Page

from ffmpeg_utils import resolve_ffmpeg

# Frame duration clamp for master assembly: gaps longer than this (page fully
# idle in screencast mode) are kept as a freeze on the previous frame;
# sub-4ms bursts are clamped so ffmpeg never sees a zero duration.
_MIN_FRAME_DURATION = 1 / 240


@dataclass
class CaptureStats:
    frame_count: int = 0
    first_timestamp: float | None = None
    last_timestamp: float | None = None

    @property
    def duration(self) -> float:
        if self.first_timestamp is None or self.last_timestamp is None:
            return 0.0
        return self.last_timestamp - self.first_timestamp

    @property
    def average_fps(self) -> float:
        if self.frame_count < 2 or self.duration <= 0:
            return 0.0
        return (self.frame_count - 1) / self.duration


@dataclass
class ScreencastRecorder:
    """Records one page. start() ... stop(), then build_master()/write_meta().

    ``page`` is None only for offline assembly (``_assemble_from_disk``), which
    never calls start().
    """

    page: Page | None
    out_dir: Path
    mode: str = "screenshot"  # "screenshot" (full-res) or "screencast" (CSS-res)
    # PNG is the default: for flat UI content it compresses about as well as
    # JPEG and is lossless. JPEG is the escape hatch for slower machines.
    frame_format: str = "png"
    jpeg_quality: int = 92
    capture_scale: float = 2.0  # output pixels per CSS pixel (screenshot mode)
    target_fps: float = 40.0  # pacing cap; actual rate may be lower (screenshot mode)
    inflight: int = 2  # concurrent captures in screenshot mode

    _cdp: CDPSession | None = None
    _queue: asyncio.Queue | None = None
    _writer_task: asyncio.Task | None = None
    _pump_tasks: list[asyncio.Task] = field(default_factory=list)
    _stopping: bool = False
    # (capture timestamp, frame filename) — sorted by timestamp at stop().
    _frame_index: list[tuple[float, str]] = field(default_factory=list)
    _arrival_count: int = 0
    _next_slot: float = 0.0
    _slot_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _stopped_at: float | None = None
    stats: CaptureStats = field(default_factory=CaptureStats)

    @property
    def frames_dir(self) -> Path:
        return self.out_dir / "frames"

    @property
    def _frame_suffix(self) -> str:
        return "jpg" if self.frame_format == "jpeg" else "png"

    async def start(self) -> None:
        assert self.page is not None, "recorder has no page (offline assembly instance)"
        assert self._cdp is None, "recorder already started"
        self.frames_dir.mkdir(parents=True, exist_ok=True)
        self._queue = asyncio.Queue()
        self._writer_task = asyncio.create_task(self._writer_loop())
        self._cdp = await self.page.context.new_cdp_session(self.page)

        if self.mode == "screenshot":
            self._next_slot = time.monotonic()
            self._pump_tasks = [
                asyncio.create_task(self._pump_loop()) for _ in range(max(1, self.inflight))
            ]
        elif self.mode == "screencast":
            viewport = self.page.viewport_size or {"width": 1600, "height": 1000}
            self._cdp.on("Page.screencastFrame", self._on_screencast_frame)
            params: dict = {
                "format": self.frame_format,
                "maxWidth": viewport["width"],
                "maxHeight": viewport["height"],
                "everyNthFrame": 1,
            }
            if self.frame_format == "jpeg":
                params["quality"] = self.jpeg_quality
            await self._cdp.send("Page.startScreencast", params)
        else:
            raise ValueError(f"unknown capture mode: {self.mode}")

    # -- screenshot-pump mode ------------------------------------------------

    async def _claim_slot(self) -> float:
        """Space capture starts evenly at target_fps across all pump workers."""
        async with self._slot_lock:
            slot = max(self._next_slot, time.monotonic())
            self._next_slot = slot + 1.0 / self.target_fps
        return slot

    async def _pump_loop(self) -> None:
        assert self._cdp is not None and self._queue is not None
        viewport = self.page.viewport_size or {"width": 1600, "height": 1000}
        params: dict = {
            "format": self.frame_format,
            "fromSurface": True,
            "optimizeForSpeed": True,
            "clip": {
                "x": 0,
                "y": 0,
                "width": viewport["width"],
                "height": viewport["height"],
                "scale": self.capture_scale,
            },
        }
        if self.frame_format == "jpeg":
            params["quality"] = self.jpeg_quality
        while not self._stopping:
            slot = await self._claim_slot()
            delay = slot - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            if self._stopping:
                return
            # The surface is sampled near the start of the call; the constant
            # encode/transport latency is shared by all frames, so relative
            # timing (and alignment with the director's event log) holds.
            captured_at = time.time()
            try:
                result = await self._cdp.send("Page.captureScreenshot", params)
            except Exception:
                if self._stopping:
                    return
                raise
            self._queue.put_nowait((captured_at, result["data"]))

    # -- screencast mode -------------------------------------------------------

    def _on_screencast_frame(self, params: dict) -> None:
        assert self._cdp is not None and self._queue is not None
        asyncio.get_running_loop().create_task(self._ack(params["sessionId"]))
        metadata = params.get("metadata") or {}
        timestamp = metadata.get("timestamp")
        if timestamp is not None:
            self._queue.put_nowait((float(timestamp), params["data"]))

    async def _ack(self, session_id: int) -> None:
        assert self._cdp is not None
        try:
            await self._cdp.send("Page.screencastFrameAck", {"sessionId": session_id})
        except Exception:
            # Acks racing a stopping session are harmless.
            pass

    # -- shared ---------------------------------------------------------------

    async def _writer_loop(self) -> None:
        assert self._queue is not None
        while True:
            item = await self._queue.get()
            if item is None:
                return
            timestamp, data_b64 = item
            self._arrival_count += 1
            filename = f"{self._arrival_count:06d}.{self._frame_suffix}"
            (self.frames_dir / filename).write_bytes(base64.b64decode(data_b64))
            self._frame_index.append((timestamp, filename))

    async def stop(self) -> None:
        assert self._cdp is not None and self._queue is not None and self._writer_task is not None
        self._stopping = True
        self._stopped_at = time.time()
        if self._pump_tasks:
            await asyncio.gather(*self._pump_tasks, return_exceptions=True)
        if self.mode == "screencast":
            try:
                await self._cdp.send("Page.stopScreencast")
            except Exception:
                pass
        self._queue.put_nowait(None)
        await self._writer_task

        # Pipelined captures can complete out of order; the timeline is the
        # sorted capture times, not arrival order.
        self._frame_index.sort()
        if self._frame_index:
            self.stats.frame_count = len(self._frame_index)
            self.stats.first_timestamp = self._frame_index[0][0]
            self.stats.last_timestamp = self._frame_index[-1][0]

        with (self.out_dir / "frames.jsonl").open("w") as f:
            for timestamp, filename in self._frame_index:
                f.write(json.dumps({"file": filename, "t": timestamp}) + "\n")

    @property
    def start_timestamp(self) -> float:
        """Epoch time of the first captured frame == t=0 of the master video."""
        if self.stats.first_timestamp is None:
            raise RuntimeError("no frames captured")
        return self.stats.first_timestamp

    def build_master(self, fps: int = 60, crf: int = 10) -> Path:
        """Encode the VFR frame sequence into a CFR H.264 master.

        crf 10 is visually lossless for UI content; the master is meant to be
        re-encoded by the camera/post step, never published directly.
        """
        if not self._frame_index:
            raise RuntimeError("no frames captured")

        concat_path = self.out_dir / "frames.ffconcat"
        lines = ["ffconcat version 1.0"]
        end_time = self._stopped_at or self._frame_index[-1][0]
        for (timestamp, filename), (next_timestamp, _) in zip(
            self._frame_index, self._frame_index[1:] + [(end_time, "")]
        ):
            duration = max(next_timestamp - timestamp, _MIN_FRAME_DURATION)
            lines.append(f"file 'frames/{filename}'")
            lines.append(f"duration {duration:.6f}")
        # The concat demuxer ignores the final entry's duration unless the
        # file is listed once more.
        lines.append(f"file 'frames/{self._frame_index[-1][1]}'")
        concat_path.write_text("\n".join(lines) + "\n")

        master_path = self.out_dir / "master.mp4"
        pix_fmt = "yuv444p" if self.frame_format == "png" else "yuv420p"
        cmd = [
            resolve_ffmpeg(),
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-vf",
            f"fps={fps},format={pix_fmt}",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            str(crf),
            "-movflags",
            "+faststart",
            str(master_path),
        ]
        subprocess.run(cmd, check=True, cwd=self.out_dir)
        return master_path

    def write_meta(self, extra: dict | None = None) -> Path:
        meta = {
            "mode": self.mode,
            "frame_format": self.frame_format,
            "capture_scale": self.capture_scale,
            "target_fps": self.target_fps,
            "inflight": self.inflight,
            "frame_count": self.stats.frame_count,
            "capture_duration_seconds": round(self.stats.duration, 3),
            "average_capture_fps": round(self.stats.average_fps, 2),
            "start_timestamp": self.stats.first_timestamp,
            **(extra or {}),
        }
        meta_path = self.out_dir / "meta.json"
        meta_path.write_text(json.dumps(meta, indent=2) + "\n")
        return meta_path


def _assemble_from_disk(take_dir: Path, fps: int, crf: int) -> None:
    """Rebuild master.mp4 from frames.jsonl — recovery for takes whose run
    crashed after capture but before assembly."""
    index_path = take_dir / "frames.jsonl"
    entries = [json.loads(line) for line in index_path.read_text().splitlines() if line.strip()]
    if not entries:
        raise SystemExit(f"no frames listed in {index_path}")
    recorder = ScreencastRecorder(page=None, out_dir=take_dir)
    recorder.frame_format = "jpeg" if entries[0]["file"].endswith(".jpg") else "png"
    recorder._frame_index = sorted((e["t"], e["file"]) for e in entries)
    recorder.stats.frame_count = len(entries)
    recorder.stats.first_timestamp = recorder._frame_index[0][0]
    recorder.stats.last_timestamp = recorder._frame_index[-1][0]
    master = recorder.build_master(fps=fps, crf=crf)
    print(f"assembled {master} from {len(entries)} frames (~{recorder.stats.average_fps:.1f} fps captured)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Assemble master.mp4 from an existing take directory")
    parser.add_argument("take_dir", type=Path)
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--crf", type=int, default=10)
    args = parser.parse_args()
    _assemble_from_disk(args.take_dir, fps=args.fps, crf=args.crf)
