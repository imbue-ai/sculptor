#!/usr/bin/env python3
"""Derive the per-PR "fast" offload perf config from the full one.

The perf lane runs the full scenario matrix on main/nightly but a fast subset on
every PR — the fast subset deselects the ``perf_heavy`` marker (scenarios with
expensive setup: 50+ chat turns, many files). Rather than maintain two
near-identical TOMLs that silently drift, this derives the fast config from the
single source of truth (``offload-perf.toml``) by injecting ``not perf_heavy``
into the group's pytest marker filter. Run by the ``test-offload-perf-fast``
just recipe; the output (``offload-perf-fast.toml``) is generated, not committed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SRC = Path("offload-perf.toml")
DST = Path("offload-perf-fast.toml")


def derive_fast(text: str) -> str:
    """Return ``text`` with ``not perf_heavy and`` injected into the -m filter.

    Raises if the filter line isn't found exactly once, so a config refactor
    fails loudly here rather than silently running the full matrix on PRs.
    """
    new, n = re.subn(r"""(filters = "-m ')""", r"\1not perf_heavy and ", text, count=1)
    if n != 1:
        raise ValueError(f"expected exactly one `filters = \"-m '...` line in {SRC}, patched {n}")
    return new


def main() -> int:
    try:
        DST.write_text(derive_fast(SRC.read_text(encoding="utf-8")), encoding="utf-8")
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {DST} (fast subset: deselects perf_heavy)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
