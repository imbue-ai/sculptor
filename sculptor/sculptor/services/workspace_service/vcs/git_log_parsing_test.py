from sculptor.services.workspace_service.vcs.git_log_parsing import expand_numstat_rename_path
from sculptor.services.workspace_service.vcs.git_log_parsing import parse_file_data_by_commit
from sculptor.services.workspace_service.vcs.git_log_parsing import parse_name_status_lines
from sculptor.services.workspace_service.vcs.git_log_parsing import parse_numstat_lines


def test_expand_numstat_rename_path_resolves_every_compact_form() -> None:
    assert expand_numstat_rename_path("{src => lib}/a.py") == "lib/a.py"
    assert expand_numstat_rename_path("pkg/{old => new}/file.py") == "pkg/new/file.py"
    assert expand_numstat_rename_path("{ => lib}/file.py") == "lib/file.py"
    assert expand_numstat_rename_path("{src => }/file.py") == "file.py"
    assert expand_numstat_rename_path("old.py => new.py") == "new.py"
    assert expand_numstat_rename_path("src/file.py") == "src/file.py"


def test_parse_numstat_lines_counts_binary_files_as_zero_and_expands_renames() -> None:
    lines = ["3\t1\tsrc/a.py", "-\t-\timage.png", "0\t0\t{old => new}/b.py", "2\t2\told.py\tnew.py", "junk"]

    assert parse_numstat_lines(lines) == {
        "src/a.py": (3, 1),
        "image.png": (0, 0),
        "new/b.py": (0, 0),
        "new.py": (2, 2),
    }


def test_parse_name_status_lines_keeps_renames_and_reads_other_statuses_as_modified() -> None:
    lines = ["M\tsrc/a.py", "A\tadded.py", "R087\told.py\tnew.py", "D\tgone.py", "T100\ttype.py"]

    assert parse_name_status_lines(lines) == {
        "src/a.py": ("M", None),
        "added.py": ("A", None),
        "new.py": ("R", "old.py"),
        "gone.py": ("D", None),
        "type.py": ("M", None),
    }


def test_parse_file_data_by_commit_groups_lines_under_each_commit() -> None:
    output = "COMMIT_SEP:aaa\n\nM\ta.py\nA\tb.py\nCOMMIT_SEP:bbb\n\nD\tc.py\nCOMMIT_SEP:ccc\n"

    assert parse_file_data_by_commit(output, list) == {"aaa": ["M\ta.py", "A\tb.py"], "bbb": ["D\tc.py"], "ccc": []}
