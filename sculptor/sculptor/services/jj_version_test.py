import re
from pathlib import Path

from sculptor.services.jj_version import JJ_PINNED_SHA256_BY_TARGET_TRIPLE
from sculptor.services.jj_version import JJ_PINNED_VERSION

_DOCKERFILE_PATH = Path(__file__).parents[3] / ".devcontainer" / "Dockerfile"


def _read_dockerfile_arg(name: str) -> str:
    match = re.search(rf"^ARG {name}=(\S+)$", _DOCKERFILE_PATH.read_text(), flags=re.MULTILINE)
    assert match is not None, f"ARG {name} not found in {_DOCKERFILE_PATH}"
    return match.group(1)


def test_offload_image_installs_the_pinned_jj_version() -> None:
    assert _read_dockerfile_arg("JJ_VERSION") == JJ_PINNED_VERSION


def test_offload_image_verifies_the_pinned_linux_digests() -> None:
    assert _read_dockerfile_arg("JJ_SHA256_X86_64") == JJ_PINNED_SHA256_BY_TARGET_TRIPLE["x86_64-unknown-linux-musl"]
    assert _read_dockerfile_arg("JJ_SHA256_AARCH64") == JJ_PINNED_SHA256_BY_TARGET_TRIPLE["aarch64-unknown-linux-musl"]
