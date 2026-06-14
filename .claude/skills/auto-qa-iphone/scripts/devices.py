"""Simulator device presets for the iPhone QA loop.

`idb ui tap`/`swipe` take coordinates in **logical points**, not pixels.
Screenshots come out at the device's native scale (2x or 3x), so to turn a
target you spotted in a screenshot into a tap, express it as a fraction of the
image and multiply by the point dimensions here (this is what
`iphone_sim.py tap --frac FX FY` does).

The Add-to-Home-Screen (AHS) reference coordinates are empirical: SpringBoard
and the share sheet are NOT in the accessibility tree, so they cannot be
located by selector. The values below were derived for MobileSafari on iOS
18.x at the device's point size and MUST be re-verified with a screenshot
after every tap when the iOS version or layout changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass(frozen=True)
class DevicePreset:
    key: str
    # Exact device-type name accepted by `xcrun simctl create`.
    sim_name: str
    # (width, height) in logical points.
    points: Tuple[int, int]
    # True if the device has a notch / Dynamic Island + home indicator, so
    # env(safe-area-inset-*) are non-zero. Non-notched devices are a useful
    # "insets ~= 0" control.
    notched: bool
    # Reference tap/swipe coordinates (in points) for the Add-to-Home-Screen
    # flow. Empty when not yet measured for this device.
    ahs: Dict[str, Tuple[int, int]] = field(default_factory=dict)


PRESETS: Dict[str, DevicePreset] = {
    "iphone-16-pro": DevicePreset(
        key="iphone-16-pro",
        sim_name="iPhone 16 Pro",
        points=(402, 874),
        notched=True,
        ahs={
            # Bottom toolbar Share button.
            "share_button": (201, 818),
            # Swipe the share sheet up to reveal the action list.
            "sheet_swipe_from": (201, 620),
            "sheet_swipe_to": (201, 320),
            # "Add to Home Screen" row in the action list.
            "add_to_home_screen": (202, 607),
            # "Add" (top-right of the confirmation dialog).
            "add_confirm": (382, 96),
            # First free home-screen slot — tapping it launches the standalone
            # web clip. Position depends on how many icons already exist.
            "launch_icon": (148, 232),
        },
    ),
    "iphone-16-pro-max": DevicePreset(
        key="iphone-16-pro-max",
        sim_name="iPhone 16 Pro Max",
        points=(440, 956),
        notched=True,
        # AHS coords differ at this size — drive manually with `tap --frac`.
        ahs={},
    ),
    "iphone-se": DevicePreset(
        key="iphone-se",
        sim_name="iPhone SE (3rd generation)",
        points=(375, 667),
        notched=False,  # safe-area insets ~= 0 — control device.
        ahs={},
    ),
}

DEFAULT_PRESET = "iphone-16-pro"


def get_preset(key: str) -> DevicePreset:
    try:
        return PRESETS[key]
    except KeyError:
        valid = ", ".join(sorted(PRESETS))
        raise SystemExit(f"Unknown device preset {key!r}. Choose one of: {valid}")
