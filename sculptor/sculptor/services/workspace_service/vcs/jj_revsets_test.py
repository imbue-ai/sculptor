import json
from pathlib import Path

import pytest

from sculptor.services.workspace_service.vcs.errors import InvalidRevisionError
from sculptor.services.workspace_service.vcs.jj_data_types import JjBookmarkSymbol
from sculptor.services.workspace_service.vcs.jj_revsets import any_remote_bookmark_revset
from sculptor.services.workspace_service.vcs.jj_revsets import bookmark_name_of_symbol
from sculptor.services.workspace_service.vcs.jj_revsets import exact_string_pattern
from sculptor.services.workspace_service.vcs.jj_revsets import format_bookmark_symbol
from sculptor.services.workspace_service.vcs.jj_revsets import local_bookmark_revset
from sculptor.services.workspace_service.vcs.jj_revsets import parse_bookmark_symbol
from sculptor.services.workspace_service.vcs.jj_revsets import quote_string_literal
from sculptor.services.workspace_service.vcs.jj_revsets import remote_bookmark_revset
from sculptor.services.workspace_service.vcs.jj_revsets import revset_for_base
from sculptor.services.workspace_service.vcs.jj_revsets import root_file_fileset
from sculptor.services.workspace_service.vcs.jj_revsets import working_copy_revset
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import JjWorkspace
from sculptor.testing.jj_repos import run_jj

_AWKWARD_NAME = 'we "ird" na/me \\ end'


def _log_commit_ids(jj_binary: JjBinary, repo_dir: Path, revset: str) -> list[str]:
    output = run_jj(
        jj_binary,
        ("--ignore-working-copy", "log", "--no-graph", "-r", revset, "-T", 'commit_id ++ "\\n"'),
        cwd=repo_dir,
    )
    return output.split()


def _main_commit_id(jj_binary: JjBinary, repo: JjColocatedRepo) -> str:
    (commit_id,) = _log_commit_ids(jj_binary, repo.path, "main")
    return commit_id


def test_quote_string_literal_escapes_backslashes_and_double_quotes() -> None:
    assert quote_string_literal('a "b" \\ c/d') == '"a \\"b\\" \\\\ c/d"'


def test_exact_string_pattern_wraps_a_quoted_literal() -> None:
    assert exact_string_pattern("feature/x") == 'exact:"feature/x"'


def test_bookmark_revsets_use_exact_patterns() -> None:
    assert local_bookmark_revset("main") == 'bookmarks(exact:"main")'
    assert remote_bookmark_revset("main", "origin") == 'remote_bookmarks(exact:"main", exact:"origin")'
    assert any_remote_bookmark_revset("main") == 'remote_bookmarks(exact:"main")'


def test_working_copy_revset_and_root_file_fileset_quote_their_operand() -> None:
    assert working_copy_revset("ws 1") == '"ws 1"@'
    assert root_file_fileset("dir/a b.txt") == 'root-file:"dir/a b.txt"'


def test_a_bookmark_whose_name_has_quotes_spaces_and_slashes_round_trips_through_jj(
    jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    run_jj(
        jj_binary,
        ("--ignore-working-copy", "bookmark", "create", quote_string_literal(_AWKWARD_NAME), "-r", "main"),
        cwd=jj_colocated_repo.path,
    )

    # The `name` keyword prints jj's quoted display form; `json(self)` carries the raw name.
    listed_names = [
        json.loads(line)["name"]
        for line in run_jj(
            jj_binary,
            ("--ignore-working-copy", "bookmark", "list", "-T", 'json(self) ++ "\\n"'),
            cwd=jj_colocated_repo.path,
        ).splitlines()
    ]
    resolved = _log_commit_ids(jj_binary, jj_colocated_repo.path, local_bookmark_revset(_AWKWARD_NAME))

    assert _AWKWARD_NAME in listed_names
    assert resolved == [_main_commit_id(jj_binary, jj_colocated_repo)]


def test_a_name_holding_revset_syntax_matches_nothing_instead_of_being_evaluated(
    jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    assert _log_commit_ids(jj_binary, jj_colocated_repo.path, local_bookmark_revset("main | all()")) == []


def test_remote_bookmark_revset_resolves_the_remote_bookmark(
    jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    resolved = _log_commit_ids(jj_binary, jj_colocated_repo.path, remote_bookmark_revset("main", "origin"))

    assert resolved == [_main_commit_id(jj_binary, jj_colocated_repo)]


def test_working_copy_revset_resolves_a_workspace_working_copy_from_the_main_repository(
    jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo, jj_workspace: JjWorkspace
) -> None:
    from_main_repo = _log_commit_ids(jj_binary, jj_colocated_repo.path, working_copy_revset(jj_workspace.name))
    from_workspace = _log_commit_ids(jj_binary, jj_workspace.path, "@")

    assert from_main_repo == from_workspace


def test_root_file_fileset_names_a_file_relative_to_the_workspace_root(
    jj_binary: JjBinary, jj_workspace: JjWorkspace
) -> None:
    relative_path = 'dir with space/fi"le.txt'
    (jj_workspace.path / relative_path).parent.mkdir()
    (jj_workspace.path / relative_path).write_text("awkward content\n")
    run_jj(jj_binary, ("util", "snapshot"), cwd=jj_workspace.path)

    content = run_jj(
        jj_binary,
        ("--ignore-working-copy", "file", "show", "-r", "@", root_file_fileset(relative_path)),
        cwd=jj_workspace.path / "dir with space",
    )

    assert content == "awkward content\n"


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("main", JjBookmarkSymbol(name="main", remote=None)),
        ("main@origin", JjBookmarkSymbol(name="main", remote="origin")),
        ("feature/x@upstream", JjBookmarkSymbol(name="feature/x", remote="upstream")),
        ("origin/main", JjBookmarkSymbol(name="origin/main", remote=None)),
    ],
)
def test_parse_bookmark_symbol_reads_local_and_remote_symbols(symbol: str, expected: JjBookmarkSymbol) -> None:
    assert parse_bookmark_symbol(symbol) == expected


@pytest.mark.parametrize("symbol", ["", "@origin", "main@", "a@b@c"])
def test_parse_bookmark_symbol_rejects_a_malformed_symbol(symbol: str) -> None:
    with pytest.raises(InvalidRevisionError):
        parse_bookmark_symbol(symbol)


def test_format_bookmark_symbol_writes_jj_syntax_and_round_trips() -> None:
    remote = JjBookmarkSymbol(name="main", remote="origin")
    local = JjBookmarkSymbol(name="main", remote=None)

    assert format_bookmark_symbol(remote) == "main@origin"
    assert format_bookmark_symbol(local) == "main"
    assert parse_bookmark_symbol(format_bookmark_symbol(remote)) == remote


def test_revset_for_base_turns_bookmark_symbols_into_exact_revsets() -> None:
    assert revset_for_base("main") == local_bookmark_revset("main")
    assert revset_for_base("main@origin") == remote_bookmark_revset("main", "origin")


def test_revset_for_base_uses_a_full_commit_id_verbatim(
    jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    commit_id = _main_commit_id(jj_binary, jj_colocated_repo)

    revset = revset_for_base(commit_id)

    assert revset == commit_id
    assert _log_commit_ids(jj_binary, jj_colocated_repo.path, revset) == [commit_id]


def test_revset_for_base_treats_a_git_style_remote_ref_as_a_local_name_that_does_not_resolve(
    jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo
) -> None:
    revset = revset_for_base("origin/main")

    assert revset == local_bookmark_revset("origin/main")
    assert _log_commit_ids(jj_binary, jj_colocated_repo.path, revset) == []


@pytest.mark.parametrize("request_string", ["", "main@", "a@b@c"])
def test_revset_for_base_rejects_anything_that_is_neither_a_symbol_nor_a_commit_id(request_string: str) -> None:
    with pytest.raises(InvalidRevisionError):
        revset_for_base(request_string)


def test_bookmark_name_of_symbol_drops_the_remote_and_names_nothing_for_no_or_a_malformed_symbol() -> None:
    assert bookmark_name_of_symbol("release/1.0@origin") == "release/1.0"
    assert bookmark_name_of_symbol("main") == "main"
    assert bookmark_name_of_symbol("a@b@c") is None
    assert bookmark_name_of_symbol(None) is None
