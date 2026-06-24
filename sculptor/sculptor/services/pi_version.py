"""The single pinned pi version, in a dependency-free module.

Sculptor pins pi to one exact version so the RPC schema stays known.
``dependency_management_service`` builds ``PI_VERSION_RANGE`` from this constant,
but the string itself lives here — apart from that heavy module — so the test
harness's ``fake_pi`` stub can answer ``pi --version`` without importing the
database / web / httpx service layer it pulls in. Keep this module import-free.
"""

PI_PINNED_VERSION = "0.78.0"
