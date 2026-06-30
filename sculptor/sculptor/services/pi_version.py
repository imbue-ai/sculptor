"""The single pinned pi version, in a dependency-free module.

Sculptor pins pi to one exact version so the RPC schema stays known. ``managed_tools``
builds ``PI_PIN`` and ``PI_VERSION_RANGE`` from this constant, but the string itself lives
here — in its own import-free module — so the test harness's ``fake_pi`` stub can answer
``pi --version`` without pulling in that module's heavier dependency stack. Keep this
module import-free.
"""

PI_PINNED_VERSION = "0.80.2"
