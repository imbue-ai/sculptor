"""The single pinned jj version and its release digests, in a dependency-free module.

jj is pinned so every developer, CI job and offload sandbox runs the same jj, and the
pin is also the minimum version Sculptor supports. ``just install-jj`` reads both
constants, and ``.devcontainer/Dockerfile`` carries its own copy for the offload image
(``jj_version_test.py`` keeps them equal). jj publishes no checksum file, so the digests
are recorded here, keyed by the Rust target triple in the release asset names. Keep this
module import-free.
"""

JJ_PINNED_VERSION = "0.46.0"

JJ_PINNED_SHA256_BY_TARGET_TRIPLE = {
    "aarch64-apple-darwin": "43daa37ce0f9716cdf6fb65a29cbcae74a3160aef048cf3cb3d166d41cb4ab58",
    "x86_64-apple-darwin": "10d941de276c7c5074ef5d395312813b4575f4ce92cb9c0b05738efb90bd3b60",
    "aarch64-unknown-linux-musl": "80e28f7501c11e50e0ca06cd6a1fa1d982cff9cc59bfe4411a9d36aa501d867e",
    "x86_64-unknown-linux-musl": "fce0271158e665ceb82dc66c5eb95b1728649094e9133074f3b5baece345fc08",
}
