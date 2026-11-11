"""Tests for the update_jj_skill dev tool, colocated with the script.

Not part of `just test-unit`; run on demand with
`uv run python -m pytest scripts/update_jj_skill_test.py`. Upstream is an
in-memory fake, so these run offline; the guard test in
`sculptor/sculptor/common/vendored_jj_skill_test.py` checks the real vendored copy.
"""

import hashlib
import tomllib
from datetime import date
from pathlib import Path

import pytest

import update_jj_skill

_FIRST_COMMIT = "1" * 40
_SECOND_COMMIT = "2" * 40
_SKILL_MARKDOWN = b'---\nname: jujutsu\ndescription: "Use jj."\n---\n\n# Jujutsu\n'
_MIT_LICENSE = b"MIT License\n\nCopyright (c) 2026 jujutsu-skill contributors\n"


class _FakeUpstream:
    """Serves fixed refs and per-commit trees in place of GitHub."""

    def __init__(self, refs: dict[str, str], trees: dict[str, dict[str, bytes]]) -> None:
        self.refs = refs
        self.trees = trees

    def resolve_commit(self, ref: str) -> str:
        return self.refs[ref]

    def list_blob_paths(self, commit: str) -> list[str]:
        return list(self.trees[commit])

    def read_blob(self, commit: str, path: str) -> bytes:
        return self.trees[commit][path]


def _upstream_tree(skill_markdown: bytes = _SKILL_MARKDOWN, license_text: bytes = _MIT_LICENSE) -> dict[str, bytes]:
    return {
        "README.md": b"# jujutsu-skill\n",
        "LICENSE": license_text,
        "jujutsu/SKILL.md": skill_markdown,
        "evals/README.md": b"not vendored\n",
    }


def _snapshot(directory: Path) -> dict[str, bytes]:
    return {str(path.relative_to(directory)): path.read_bytes() for path in directory.rglob("*") if path.is_file()}


def _read_upstream_toml(plugin_dir: Path) -> dict:
    return tomllib.loads((plugin_dir / "UPSTREAM.toml").read_text())


def test_vendors_the_skill_directory_and_root_license_byte_identical(tmp_path: Path) -> None:
    upstream = _FakeUpstream({"main": _FIRST_COMMIT}, {_FIRST_COMMIT: _upstream_tree()})

    update_jj_skill.update_vendored_skill(upstream, tmp_path, "main", date(2026, 11, 10))

    assert _snapshot(tmp_path / "skills" / "jujutsu") == {"SKILL.md": _SKILL_MARKDOWN, "LICENSE": _MIT_LICENSE}


def test_records_provenance_and_per_file_digests(tmp_path: Path) -> None:
    upstream = _FakeUpstream({"main": _FIRST_COMMIT}, {_FIRST_COMMIT: _upstream_tree()})

    update_jj_skill.update_vendored_skill(upstream, tmp_path, "main", date(2026, 11, 10))

    assert _read_upstream_toml(tmp_path) == {
        "repository": "https://github.com/danverbraganza/jujutsu-skill",
        "requested_ref": "main",
        "commit": _FIRST_COMMIT,
        "fetched_on": date(2026, 11, 10),
        "license": "MIT",
        "sha256": {
            "skills/jujutsu/LICENSE": hashlib.sha256(_MIT_LICENSE).hexdigest(),
            "skills/jujutsu/SKILL.md": hashlib.sha256(_SKILL_MARKDOWN).hexdigest(),
        },
    }


def test_mirrors_nested_files_under_the_upstream_skill_directory(tmp_path: Path) -> None:
    tree = {**_upstream_tree(), "jujutsu/references/revsets.md": b"revsets\n"}
    upstream = _FakeUpstream({"main": _FIRST_COMMIT}, {_FIRST_COMMIT: tree})

    update_jj_skill.update_vendored_skill(upstream, tmp_path, "main", date(2026, 11, 10))

    assert (tmp_path / "skills" / "jujutsu" / "references" / "revsets.md").read_bytes() == b"revsets\n"
    assert "skills/jujutsu/references/revsets.md" in _read_upstream_toml(tmp_path)["sha256"]


def test_rerunning_at_the_same_commit_changes_nothing_even_on_a_later_day(tmp_path: Path) -> None:
    upstream = _FakeUpstream({"main": _FIRST_COMMIT}, {_FIRST_COMMIT: _upstream_tree()})
    update_jj_skill.update_vendored_skill(upstream, tmp_path, "main", date(2026, 11, 10))
    first_run = _snapshot(tmp_path)

    update = update_jj_skill.update_vendored_skill(upstream, tmp_path, "main", date(2026, 12, 1))

    assert update == update_jj_skill.VendoredSkillUpdate(previous_commit=_FIRST_COMMIT, commit=_FIRST_COMMIT)
    assert _snapshot(tmp_path) == first_run


def test_a_new_commit_replaces_the_directory_and_reports_the_previous_commit(tmp_path: Path) -> None:
    first_tree = {**_upstream_tree(), "jujutsu/references/removed.md": b"gone upstream\n"}
    second_tree = _upstream_tree(skill_markdown=_SKILL_MARKDOWN + b"\nMore guidance.\n")
    upstream = _FakeUpstream({"main": _FIRST_COMMIT}, {_FIRST_COMMIT: first_tree, _SECOND_COMMIT: second_tree})
    update_jj_skill.update_vendored_skill(upstream, tmp_path, "main", date(2026, 11, 10))
    upstream.refs["main"] = _SECOND_COMMIT

    update = update_jj_skill.update_vendored_skill(upstream, tmp_path, "main", date(2026, 12, 1))

    assert update == update_jj_skill.VendoredSkillUpdate(previous_commit=_FIRST_COMMIT, commit=_SECOND_COMMIT)
    assert _snapshot(tmp_path / "skills" / "jujutsu") == {
        "SKILL.md": _SKILL_MARKDOWN + b"\nMore guidance.\n",
        "LICENSE": _MIT_LICENSE,
    }
    recorded = _read_upstream_toml(tmp_path)
    assert recorded["commit"] == _SECOND_COMMIT
    assert recorded["fetched_on"] == date(2026, 12, 1)
    assert set(recorded["sha256"]) == {"skills/jujutsu/LICENSE", "skills/jujutsu/SKILL.md"}
    assert sorted(path.name for path in (tmp_path / "skills").iterdir()) == ["jujutsu"]


@pytest.mark.parametrize(
    "tree",
    [
        pytest.param(_upstream_tree(skill_markdown=b"---\nname: jj\n---\n"), id="renamed-skill"),
        pytest.param(_upstream_tree(license_text=b"Apache License\n"), id="relicensed"),
        pytest.param({"LICENSE": _MIT_LICENSE, "jujutsu/README.md": b"no skill\n"}, id="missing-skill-markdown"),
        pytest.param({**_upstream_tree(), "jujutsu/LICENSE": b"clashes\n"}, id="license-collision"),
    ],
)
def test_refuses_an_unexpected_upstream_and_leaves_the_vendored_copy_alone(
    tmp_path: Path, tree: dict[str, bytes]
) -> None:
    upstream = _FakeUpstream({"main": _FIRST_COMMIT}, {_FIRST_COMMIT: _upstream_tree(), _SECOND_COMMIT: tree})
    update_jj_skill.update_vendored_skill(upstream, tmp_path, "main", date(2026, 11, 10))
    before = _snapshot(tmp_path)
    upstream.refs["main"] = _SECOND_COMMIT

    with pytest.raises(update_jj_skill.UpstreamSkillError):
        update_jj_skill.update_vendored_skill(upstream, tmp_path, "main", date(2026, 12, 1))

    assert _snapshot(tmp_path) == before
    assert sorted(path.name for path in (tmp_path / "skills").iterdir()) == ["jujutsu"]


def test_refuses_a_ref_that_does_not_resolve_to_a_full_commit_id(tmp_path: Path) -> None:
    upstream = _FakeUpstream({"main": "not-a-sha"}, {})

    with pytest.raises(update_jj_skill.UpstreamSkillError):
        update_jj_skill.update_vendored_skill(upstream, tmp_path, "main", date(2026, 11, 10))


def test_upstream_change_url_compares_the_previous_commit_with_the_new_one() -> None:
    assert update_jj_skill.upstream_change_url(_FIRST_COMMIT, _SECOND_COMMIT) == (
        f"https://github.com/danverbraganza/jujutsu-skill/compare/{_FIRST_COMMIT}...{_SECOND_COMMIT}"
    )


def test_upstream_change_url_links_the_commit_when_there_is_nothing_to_compare() -> None:
    expected = f"https://github.com/danverbraganza/jujutsu-skill/commit/{_FIRST_COMMIT}"
    assert update_jj_skill.upstream_change_url(None, _FIRST_COMMIT) == expected
    assert update_jj_skill.upstream_change_url(_FIRST_COMMIT, _FIRST_COMMIT) == expected
