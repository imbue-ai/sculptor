"""The single pinned jj version and its release digests, in a dependency-free module.

jj is pinned so every developer, CI job and offload sandbox runs the same jj, and the
pin is also the minimum version Sculptor supports. ``just install-jj`` reads both
constants, and ``.devcontainer/Dockerfile`` carries its own copy for the offload image
(``jj_version_test.py`` keeps them equal). jj publishes no checksum file, so the digests
are recorded here, keyed by the Rust target triple in the release asset names. Keep this
module import-free.
"""

JJ_PINNED_VERSION = "0.47.1"

JJ_PINNED_SHA256_BY_TARGET_TRIPLE = {
    "aarch64-apple-darwin": "50129b527f7cd6aef82aebd4bb2b670bb56766adc509ef3279c4327aa3592255",
    "x86_64-apple-darwin": "ce7ac70c3b7cf90f2273b4fa62d24576727c5fd55c60dc3820221c05320c7589",
    "aarch64-unknown-linux-musl": "0f300e1576de8dabe0a9dedf0b87ae44f8accea5cf54d9a342a51061c1fb1bcd",
    "x86_64-unknown-linux-musl": "d4b657f622ee50929c8916466dfa3d6a6c17a0a32b50e7b2c793707ec9ebcad7",
}
