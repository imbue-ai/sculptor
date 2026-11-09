#!/usr/bin/env python3
"""Vendor the upstream jujutsu agent skill into Sculptor's ``sculptor-jj`` plugin.

Resolves a ref of https://github.com/danverbraganza/jujutsu-skill to a commit,
mirrors the upstream ``jujutsu/`` directory plus the root ``LICENSE`` at that
commit into ``sculptor/sculptor-jj/skills/jujutsu/``, rewrites
``sculptor/sculptor-jj/UPSTREAM.toml`` with the provenance and a sha256 per
vendored file, and prints the upstream URL for the change. An upstream whose
skill is no longer named ``jujutsu`` or whose license no longer starts with
``MIT License`` is refused, and the vendored directory is only replaced once
every file has been fetched and checked.

The vendored files are never edited here: changes belong upstream, and
``sculptor/sculptor/common/vendored_jj_skill_test.py`` fails when a file drifts
from its recorded digest.

Usage:
    just update-jj-skill              # upstream main
    just update-jj-skill <ref>        # any branch, tag or commit

Reads ``GH_TOKEN`` or ``GITHUB_TOKEN`` for the API calls when set; anonymous
works but is rate-limited per IP. Stdlib-only, like its ``scripts/`` siblings.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Protocol

_GITHUB_REPOSITORY = "danverbraganza/jujutsu-skill"
_REPOSITORY_URL = f"https://github.com/{_GITHUB_REPOSITORY}"
_UPSTREAM_SKILL_DIRECTORY = "jujutsu/"
_LICENSE_FILE_NAME = "LICENSE"
_SKILL_MARKDOWN_FILE_NAME = "SKILL.md"
_SKILL_NAME = "jujutsu"
_LICENSE_PREFIX = b"MIT License"
_LICENSE_NAME = "MIT"
_VENDORED_SKILL_DIRECTORY = Path("skills") / _SKILL_NAME
_PROVENANCE_FILE_NAME = "UPSTREAM.toml"
_COMMIT_ID_PATTERN = re.compile(r"[0-9a-f]{40}")
_REQUEST_TIMEOUT_SECONDS = 30


class UpstreamSkillError(RuntimeError):
    """Raised when upstream cannot be read or no longer looks like the vendored skill."""


class UpstreamRepository(Protocol):
    def resolve_commit(self, ref: str) -> str: ...

    def list_blob_paths(self, commit: str) -> list[str]: ...

    def read_blob(self, commit: str, path: str) -> bytes: ...


class GitHubUpstreamRepository:
    """Reads the upstream repository through the GitHub API and raw.githubusercontent.com."""

    def __init__(self, token: str | None) -> None:
        self._api_headers = {"Accept": "application/vnd.github+json"}
        if token:
            self._api_headers["Authorization"] = f"Bearer {token}"

    def resolve_commit(self, ref: str) -> str:
        url = f"https://api.github.com/repos/{_GITHUB_REPOSITORY}/commits/{urllib.parse.quote(ref, safe='/')}"
        # This media type makes the API answer with the bare commit id.
        return self._get(url, {**self._api_headers, "Accept": "application/vnd.github.sha"}).decode().strip()

    def list_blob_paths(self, commit: str) -> list[str]:
        url = f"https://api.github.com/repos/{_GITHUB_REPOSITORY}/git/trees/{commit}?recursive=1"
        payload = json.loads(self._get(url, self._api_headers))
        if payload["truncated"]:
            raise UpstreamSkillError(f"The GitHub API truncated the tree of {commit}")
        return [entry["path"] for entry in payload["tree"] if entry["type"] == "blob"]

    def read_blob(self, commit: str, path: str) -> bytes:
        return self._get(
            f"https://raw.githubusercontent.com/{_GITHUB_REPOSITORY}/{commit}/{urllib.parse.quote(path)}", {}
        )

    def _get(self, url: str, headers: Mapping[str, str]) -> bytes:
        # The GitHub API rejects requests that send no User-Agent.
        request = urllib.request.Request(url, headers={"User-Agent": "sculptor-update-jj-skill", **headers})
        try:
            with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError) as error:
            raise UpstreamSkillError(f"Could not fetch {url}: {error}") from error


@dataclass(frozen=True)
class VendoredSkillUpdate:
    previous_commit: str | None
    commit: str


def update_vendored_skill(
    upstream: UpstreamRepository, plugin_dir: Path, ref: str, today: date
) -> VendoredSkillUpdate:
    """Mirror the skill at upstream ``ref`` into ``plugin_dir`` and record its provenance.

    Re-vendoring the recorded commit keeps its original ``fetched_on``, so a run
    that finds nothing new leaves the tree unchanged.
    """
    commit = upstream.resolve_commit(ref)
    if _COMMIT_ID_PATTERN.fullmatch(commit) is None:
        raise UpstreamSkillError(f"{ref!r} resolved to {commit!r}, which is not a full commit id")
    skill_files = _fetch_skill_files(upstream, commit)
    _check_skill_files(skill_files)

    provenance_path = plugin_dir / _PROVENANCE_FILE_NAME
    previous = tomllib.loads(provenance_path.read_text()) if provenance_path.is_file() else None
    previous_commit = previous["commit"] if previous is not None else None
    fetched_on = previous["fetched_on"] if previous_commit == commit else today

    _replace_directory(plugin_dir / _VENDORED_SKILL_DIRECTORY, skill_files)
    _write_file_atomically(provenance_path, render_provenance(ref, commit, fetched_on, skill_files))
    return VendoredSkillUpdate(previous_commit=previous_commit, commit=commit)


def render_provenance(ref: str, commit: str, fetched_on: date, skill_files: Mapping[str, bytes]) -> str:
    """Render ``UPSTREAM.toml``; digests are keyed by path relative to the plugin directory."""
    lines = [
        "# Provenance of the vendored jujutsu skill. Written by `just update-jj-skill`; do not edit.",
        f"repository = {_toml_string(_REPOSITORY_URL)}",
        f"requested_ref = {_toml_string(ref)}",
        f"commit = {_toml_string(commit)}",
        f"fetched_on = {fetched_on.isoformat()}",
        f"license = {_toml_string(_LICENSE_NAME)}",
        "",
        "[sha256]",
    ]
    for relative_path in sorted(skill_files):
        key = (_VENDORED_SKILL_DIRECTORY / relative_path).as_posix()
        digest = hashlib.sha256(skill_files[relative_path]).hexdigest()
        lines.append(f"{_toml_string(key)} = {_toml_string(digest)}")
    return "\n".join(lines) + "\n"


def upstream_change_url(previous_commit: str | None, commit: str) -> str:
    """The upstream page showing what changed between the previous and the new vendored commit."""
    if previous_commit is None or previous_commit == commit:
        return f"{_REPOSITORY_URL}/commit/{commit}"
    return f"{_REPOSITORY_URL}/compare/{previous_commit}...{commit}"


def read_frontmatter_name(markdown: str) -> str | None:
    """Return the ``name`` field of a SKILL.md's YAML frontmatter, or None when there is none."""
    lines = markdown.splitlines()
    if not lines or lines[0] != "---":
        return None
    for line in lines[1:]:
        if line == "---":
            return None
        key, separator, value = line.partition(":")
        if separator and key == "name":
            return value.strip().strip("\"'")
    return None


def _fetch_skill_files(upstream: UpstreamRepository, commit: str) -> dict[str, bytes]:
    """The files to vendor at ``commit``, keyed by their path inside the skill directory."""
    skill_files = {
        path.removeprefix(_UPSTREAM_SKILL_DIRECTORY): upstream.read_blob(commit, path)
        for path in upstream.list_blob_paths(commit)
        if path.startswith(_UPSTREAM_SKILL_DIRECTORY)
    }
    if _LICENSE_FILE_NAME in skill_files:
        raise UpstreamSkillError(
            f"Upstream {_UPSTREAM_SKILL_DIRECTORY}{_LICENSE_FILE_NAME} collides with the vendored root license"
        )
    skill_files[_LICENSE_FILE_NAME] = upstream.read_blob(commit, _LICENSE_FILE_NAME)
    return skill_files


def _check_skill_files(skill_files: Mapping[str, bytes]) -> None:
    skill_markdown = skill_files.get(_SKILL_MARKDOWN_FILE_NAME)
    if skill_markdown is None:
        raise UpstreamSkillError(f"Upstream has no {_UPSTREAM_SKILL_DIRECTORY}{_SKILL_MARKDOWN_FILE_NAME}")
    name = read_frontmatter_name(skill_markdown.decode("utf-8"))
    if name != _SKILL_NAME:
        raise UpstreamSkillError(f"Upstream skill is named {name!r}, expected {_SKILL_NAME!r}")
    if not skill_files[_LICENSE_FILE_NAME].startswith(_LICENSE_PREFIX):
        raise UpstreamSkillError(f"Upstream {_LICENSE_FILE_NAME} no longer starts with {_LICENSE_PREFIX.decode()!r}")


def _replace_directory(target: Path, files: Mapping[str, bytes]) -> None:
    """Swap ``target`` for a directory holding exactly ``files``, staged beside it first."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{target.name}-", dir=target.parent) as scratch:
        staged = Path(scratch) / "new"
        for relative_path, content in files.items():
            path = staged / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        if target.exists():
            target.rename(Path(scratch) / "old")
        staged.rename(target)


def _write_file_atomically(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(content)
    os.replace(temporary, path)


def _toml_string(value: str) -> str:
    # A JSON string literal is a valid TOML basic string for these ASCII values.
    return json.dumps(value)


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description="Vendor the upstream jujutsu skill into the sculptor-jj plugin.")
    parser.add_argument("ref", nargs="?", default="main", help="upstream branch, tag or commit (default: main)")
    parser.add_argument(
        "--plugin-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "sculptor" / "sculptor-jj",
        help="the sculptor-jj plugin directory (defaults to this checkout's)",
    )
    arguments = parser.parse_args(argv)
    upstream = GitHubUpstreamRepository(os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
    try:
        update = update_vendored_skill(upstream, arguments.plugin_dir, arguments.ref, date.today())
    except UpstreamSkillError as error:
        print(f"update-jj-skill: {error}", file=sys.stderr)
        return 1
    if update.previous_commit == update.commit:
        print(f"The vendored jujutsu skill is already at {update.commit} ({arguments.ref}).")
    else:
        print(f"Vendored the jujutsu skill at {update.commit} ({arguments.ref}).")
    print(f"Upstream: {upstream_change_url(update.previous_commit, update.commit)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
