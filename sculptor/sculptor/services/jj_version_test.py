import re
from pathlib import Path

import pytest

from sculptor.services.jj_version import JJ_MINIMUM_GIT_VERSION
from sculptor.services.jj_version import JJ_PINNED_SHA256_BY_TARGET_TRIPLE
from sculptor.services.jj_version import JJ_PINNED_VERSION
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import JjFixtureCommandError
from sculptor.testing.jj_repos import run_jj

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


def test_the_pinned_jj_names_the_oldest_git_it_accepts_when_a_git_too_old_to_fetch_with_refuses(
    jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo, tmp_path: Path
) -> None:
    # What git 2.39 prints for `git fetch --porcelain`, the git command jj runs to fetch.
    old_git = tmp_path / "git"
    old_git.write_text('#!/bin/sh\necho "error: unknown option \\`porcelain\'" >&2\nexit 129\n')
    old_git.chmod(0o755)

    with pytest.raises(JjFixtureCommandError) as refusal:
        run_jj(jj_binary, ("--config", f"git.executable-path={old_git}", "git", "fetch"), cwd=jj_colocated_repo.path)

    assert f"Jujutsu requires git >= {JJ_MINIMUM_GIT_VERSION})" in str(refusal.value)
