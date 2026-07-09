"""Human-like input driver for marketing demo recordings.

Drives the REAL Playwright mouse and keyboard so the page reacts exactly as it
would for a person (hover states, focus rings, ripples), while an injected
overlay (``cursor_overlay.js``) visualizes the cursor in the recording.

Movement model:
- Paths are cubic beziers with a slight perpendicular bow, so the cursor never
  travels in laser-straight lines.
- Timing follows a minimum-jerk profile (the standard model for human reaching
  motions): slow-in, fast-middle, slow-out.
- Click points get a small jitter inside the target so repeated takes don't
  look robotically identical.

Every action is appended to an event log with wall-clock timestamps
(``time.time()``, the same clock as the screencast frame metadata) plus the
target's bounding box in CSS pixels — enough for the post step to aim a
virtual camera at whatever the cursor was doing.
"""

from __future__ import annotations

import asyncio
import json
import math
import random
import time
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path

from playwright.async_api import Locator
from playwright.async_api import Page

_MOUSE_HZ = 60


def _minimum_jerk(u: float) -> float:
    return u * u * u * (10 - 15 * u + 6 * u * u)


@dataclass
class Director:
    page: Page
    rng: random.Random = field(default_factory=lambda: random.Random(1138))
    move_speed: float = 1.0  # >1 = snappier cursor, <1 = more languid

    _pos: tuple[float, float] = (200.0, 200.0)
    _events: list[dict] = field(default_factory=list)

    # -- event log ---------------------------------------------------------

    def _log(self, action: str, t0: float, **details) -> None:
        self._events.append({"action": action, "t0": t0, "t1": time.time(), **details})

    def mark(self, label: str) -> None:
        """Record a named instant (e.g. "agent_started") for use in post."""
        now = time.time()
        self._log("mark", now, label=label)

    async def save_events(self, path: Path, *, video_start_timestamp: float | None = None) -> None:
        """Write the event log; if the capture start time is known, add video-relative times."""
        viewport = self.page.viewport_size or {}
        events = []
        for event in self._events:
            event = dict(event)
            if video_start_timestamp is not None:
                event["video_t0"] = round(event["t0"] - video_start_timestamp, 3)
                event["video_t1"] = round(event["t1"] - video_start_timestamp, 3)
            events.append(event)
        payload = {
            "viewport": viewport,
            "video_start_timestamp": video_start_timestamp,
            "events": events,
        }
        path.write_text(json.dumps(payload, indent=2) + "\n")

    # -- pointer -----------------------------------------------------------

    async def place_cursor(self, x: float, y: float) -> None:
        """Teleport the cursor (no animation) — for the opening frame of a take."""
        self._pos = (x, y)
        await self.page.mouse.move(x, y)

    async def move_to(self, x: float, y: float, *, duration: float | None = None) -> None:
        t0 = time.time()
        x0, y0 = self._pos
        dx, dy = x - x0, y - y0
        distance = math.hypot(dx, dy)
        if distance < 1:
            return
        if duration is None:
            # Rough Fitts-flavored duration: short hops stay quick, long
            # sweeps take visibly longer, with mild take-to-take variation.
            duration = (0.28 + distance / 1800.0) * self.rng.uniform(0.92, 1.12)
            duration = min(max(duration, 0.30), 1.4)
        duration /= self.move_speed

        # Perpendicular bow gives the path a natural arc.
        perp_x, perp_y = -dy / distance, dx / distance
        bow = distance * self.rng.uniform(0.04, 0.10) * self.rng.choice((-1, 1))
        c1 = (x0 + dx * 0.30 + perp_x * bow, y0 + dy * 0.30 + perp_y * bow)
        c2 = (x0 + dx * 0.72 + perp_x * bow * 0.6, y0 + dy * 0.72 + perp_y * bow * 0.6)

        steps = max(2, int(duration * _MOUSE_HZ))
        for i in range(1, steps + 1):
            u = _minimum_jerk(i / steps)
            v = 1 - u
            px = v**3 * x0 + 3 * v**2 * u * c1[0] + 3 * v * u**2 * c2[0] + u**3 * x
            py = v**3 * y0 + 3 * v**2 * u * c1[1] + 3 * v * u**2 * c2[1] + u**3 * y
            await self.page.mouse.move(px, py)
            target_t = t0 + duration * (i / steps)
            delay = target_t - time.time()
            if delay > 0:
                await asyncio.sleep(delay)
        self._pos = (x, y)
        self._log("move", t0, x=x, y=y)

    async def _resolve_target(self, target: str | Locator) -> tuple[Locator, dict]:
        locator = self.page.locator(target).first if isinstance(target, str) else target.first
        await locator.wait_for(state="visible")
        box = await locator.bounding_box()
        assert box is not None, f"target has no bounding box: {target}"
        return locator, box

    def _click_point(self, box: dict) -> tuple[float, float]:
        # Aim near the center with a jitter proportional to the target size,
        # hard-clamped to its middle 60% so we never graze the edge.
        cx = box["x"] + box["width"] / 2
        cy = box["y"] + box["height"] / 2
        jx = self.rng.gauss(0, box["width"] / 10)
        jy = self.rng.gauss(0, box["height"] / 10)
        jx = max(-box["width"] * 0.3, min(box["width"] * 0.3, jx))
        jy = max(-box["height"] * 0.3, min(box["height"] * 0.3, jy))
        return cx + jx, cy + jy

    async def hover(self, target: str | Locator, *, label: str | None = None) -> None:
        t0 = time.time()
        _, box = await self._resolve_target(target)
        await self.move_to(*self._click_point(box))
        self._log("hover", t0, target=label or str(target), bbox=box)

    async def click(
        self,
        target: str | Locator,
        *,
        label: str | None = None,
        settle: float = 0.16,
    ) -> None:
        t0 = time.time()
        _, box = await self._resolve_target(target)
        point = self._click_point(box)
        await self.move_to(*point)
        # Settle before pressing, hold the button a human-length beat.
        await asyncio.sleep(settle * self.rng.uniform(0.8, 1.3))
        await self.page.mouse.down()
        await asyncio.sleep(self.rng.uniform(0.055, 0.11))
        await self.page.mouse.up()
        await asyncio.sleep(self.rng.uniform(0.12, 0.22))
        self._log("click", t0, target=label or str(target), bbox=box, x=point[0], y=point[1])

    # -- keyboard ----------------------------------------------------------

    async def type_text(self, text: str, *, speed: float = 1.0) -> None:
        """Type with per-character cadence: fast runs, brief thinking pauses."""
        t0 = time.time()
        for ch in text:
            await self.page.keyboard.type(ch)
            delay = self.rng.gauss(0.052, 0.018)
            if ch in ".,!?":
                delay += 0.10
            elif ch == " " and self.rng.random() < 0.08:
                delay += self.rng.uniform(0.15, 0.4)
            await asyncio.sleep(max(0.024, delay) / speed)
        self._log("type", t0, text=text)

    async def press(self, key: str) -> None:
        t0 = time.time()
        await self.page.keyboard.press(key)
        self._log("press", t0, key=key)

    # -- misc --------------------------------------------------------------

    async def pause(self, seconds: float, *, label: str = "") -> None:
        t0 = time.time()
        await asyncio.sleep(seconds)
        self._log("pause", t0, label=label)

    async def drift(self, *, anchor: tuple[float, float] | None = None, radius: float = 30.0) -> None:
        """A tiny idle wander so the cursor doesn't look frozen during waits.

        With an anchor, wander stays within ``radius`` of it — use this to park
        the cursor over neutral space, where a free random walk would sooner or
        later stray onto a hoverable control and pop a tooltip into the shot.
        """
        ax, ay = anchor if anchor is not None else self._pos
        await self.move_to(
            ax + self.rng.uniform(-radius, radius),
            ay + self.rng.uniform(-radius, radius),
            duration=self.rng.uniform(0.5, 0.9),
        )

    async def scroll(self, delta_y: float, *, duration: float = 0.7) -> None:
        """Eased wheel scroll (positive delta scrolls down)."""
        t0 = time.time()
        steps = max(3, int(duration * 30))
        done = 0.0
        for i in range(1, steps + 1):
            target = _minimum_jerk(i / steps) * delta_y
            step = target - done
            await self.page.mouse.wheel(0, step)
            done = target
            await asyncio.sleep(duration / steps)
        self._log("scroll", t0, delta_y=delta_y)

    async def wait_for(self, target: str | Locator, *, state: str = "visible", timeout: float = 30.0, label: str | None = None) -> None:
        """Non-visual wait on the app (logged, so post knows what happened when)."""
        t0 = time.time()
        locator = self.page.locator(target).first if isinstance(target, str) else target.first
        await locator.wait_for(state=state, timeout=timeout * 1000)
        self._log("wait", t0, target=label or str(target), state=state)
