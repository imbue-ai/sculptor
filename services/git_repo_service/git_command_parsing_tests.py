import pytest

from sculptor.services.git_repo_service.api import GitRepoFileStatus
from sculptor.services.git_repo_service.default_implementation import NULL_DELIMITER_FOR_FOOLPROOF_PARSING
from sculptor.services.git_repo_service.default_implementation import _parse_git_status_file_counts


def _null_delimited_lines(lines: tuple[str, ...]) -> str:
    return "\x00".join(lines) + "\x00"


_EXPECTED_STATUS_BY_LINE: list[tuple[tuple[str, ...], str | None, GitRepoFileStatus]] = [
    (
        (
            " M .gitignore",
            " D conflict--AU.txt",
            " M conflict--aa.txt",
            " M conflict--ua.txt",
            " M conflict--uu.txt",
            " D test--AD.txt",
            " M test--AM.txt",
            " M test--MM.txt",
            " D test--_D.txt",
            " M test--_M.txt",
            " D test--copied.txt",
            "A  test--staged--A.txt",
            "M  test--staged--M.txt",
            "?? ?test--untracked1.txt",
            "?? count_git_status.py",
            "?? test untracked2.txt",
            "?? test$untracked3.txt",
            "?? test--to--delete.txt",
            "?? test_αβγ_unicode.txt",
        ),
        None,
        GitRepoFileStatus(unstaged=11, staged=2, deleted=4, untracked=6, ignored=0),
    ),
    (
        (
            "M .gitignore",
            "DD conflict--AU.txt",
            "AU conflict--aa.txt",
            " M conflict--ua.txt",
            " M conflict--uu.txt",
            "UD test--AD.txt",
            " M test--AM.txt",
            " M test--MM.txt",
            " D test--_D.txt",
            " M test--_M.txt",
            " D test--copied.txt",
            "A  test--staged--A.txt",
            "M  test--staged--M.txt",
            "?? ?test--untracked1.txt",
            "?? count_git_status.py",
            "?? test untracked2.txt",
            "?? test$untracked3.txt",
            "?? test--to--delete.txt",
            "?? test_αβγ_unicode.txt",
        ),
        None,
        GitRepoFileStatus(unstaged=10, staged=6, deleted=4, untracked=6, ignored=0),
    ),
    (
        (
            " M modified--worktree.txt",
            "M  modified--index.txt",
            "MM modified--both.txt",
            "A  added--index.txt",
            "AM added--index+mod.txt",
            "AD added--then-deleted.txt",
            " D deleted--worktree.txt",
            "D  deleted--index.txt",
            "DM deleted--index+mod.txt",
            # NOTE: currently we use --no-renames
            # _null_delimited_lines(("R  renamed--index--new.txt", "renamed--index.txt")),
            # _null_delimited_lines(("RM renamed--mod--new.txt", "renamed--mod.txt")),
            # _null_delimited_lines(("C  copied--index.txt", "copied--index--new.txt")),
            # _null_delimited_lines(("CM copied--mod--copy.txt", "copied--mod.txt")),
            "UU unmerged--both.txt",
            "UD unmerged--deleted--worktree.txt",
            "DU unmerged--deleted--index.txt",
            "AA unmerged--both-added.txt",
            "AU unmerged--added-by-us.txt",
            "UA unmerged--added-by-them.txt",
            "?? untracked--file.txt",
            "!! ignored--file.txt",
        ),
        None,
        GitRepoFileStatus(unstaged=14 - 2, staged=17 - 4, deleted=6, untracked=1, ignored=1),
    ),
    (
        (
            "M .gitignore",
            "AD added-then-deleted.txtAM added--index+mod.txt",
            "AD added--then-deleted.txt",
            "AA ignored_path/added-file",
            "?? ignored_path/untracked-file",
        ),
        ("ignored_path/",),
        GitRepoFileStatus(unstaged=3, staged=4, deleted=2, untracked=0, ignored=1),
    ),
    (
        ("?? .claude/settings.local.json",),
        (".claude/",),
        GitRepoFileStatus(unstaged=0, staged=0, deleted=0, untracked=0, ignored=1),
    ),
]


@pytest.mark.parametrize("input_lines, additional_ignores, expected_status", _EXPECTED_STATUS_BY_LINE)
def test_git_status_parsing_strings(
    input_lines: tuple[str, ...], additional_ignores: tuple[str, ...] | None, expected_status: GitRepoFileStatus
) -> None:
    input_str = _null_delimited_lines(input_lines)

    assert (
        _parse_git_status_file_counts(
            input_str, delimiter=NULL_DELIMITER_FOR_FOOLPROOF_PARSING, additional_ignores=additional_ignores
        )
        == expected_status
    )
