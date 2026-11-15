from pathlib import Path

import pytest

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.services.workspace_service.vcs.errors import JjWorkingCopyStaleError
from sculptor.services.workspace_service.vcs.errors import VcsBinaryNotFoundError
from sculptor.services.workspace_service.vcs.errors import VcsCommandExitError
from sculptor.services.workspace_service.vcs.errors import VcsCommandTimeoutError
from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.services.workspace_service.vcs.jj_cli import JjSnapshotPolicy
from sculptor.services.workspace_service.vcs.jj_cli import parse_refused_snapshot_files
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import JjWorkspace
from sculptor.testing.jj_repos import make_workspace_stale
from sculptor.testing.jj_repos import run_jj

_REFUSED_SNAPSHOT_STDERR = """\
Warning: Some unrelated warning
Warning: Refused to snapshot some files:
  sub/a: b c.bin: 4.9KiB (5000 bytes); the maximum size allowed is 1.0KiB (1024 bytes)
  x"y.bin: 2.9KiB (3000 bytes); the maximum size allowed is 1.0KiB (1024 bytes)
Hint: This is to prevent large files from being added by accident. To fix this:
  * Add the file(s) to `.gitignore`
  * Run `jj config set --repo snapshot.max-new-file-size 5000`
    This will increase the maximum file size allowed for new files, in this repository only.
"""


def _write_script(path: Path, body: str) -> Path:
    path.write_text(f"#!/bin/bash\n{body}\n")
    path.chmod(0o755)
    return path


def _jj_cli_running(concurrency_group: ConcurrencyGroup, binary: Path) -> JjCli:
    return JjCli(concurrency_group, lambda tool: str(binary))


def _count_operations(jj_binary: JjBinary, repo_dir: Path) -> int:
    output = run_jj(jj_binary, ("--ignore-working-copy", "op", "log", "--no-graph", "-T", 'id ++ "\\n"'), cwd=repo_dir)
    return len(output.splitlines())


def test_run_puts_the_global_options_before_the_arguments_and_runs_in_the_repository(
    test_root_concurrency_group: ConcurrencyGroup, tmp_path: Path
) -> None:
    fake_jj = _write_script(tmp_path / "fake-jj", 'echo "$PWD"\nprintf "%s\\n" "$@"')
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    jj = _jj_cli_running(test_root_concurrency_group, fake_jj)

    result = jj.run(
        ["log", "-r", "@"],
        repo_dir,
        snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY,
        config_overrides={"snapshot.max-new-file-size": "100", "ui.editor": "false"},
    )

    cwd, *argv = result.stdout.splitlines()
    assert Path(cwd).resolve() == repo_dir.resolve()
    assert argv == [
        "--no-pager",
        "--color=never",
        "-R",
        str(repo_dir),
        "--ignore-working-copy",
        "--config",
        "snapshot.max-new-file-size=100",
        "--config",
        "ui.editor=false",
        "log",
        "-r",
        "@",
    ]


def test_run_with_snapshot_passes_no_ignore_working_copy_flag(
    test_root_concurrency_group: ConcurrencyGroup, tmp_path: Path
) -> None:
    fake_jj = _write_script(tmp_path / "fake-jj", 'printf "%s\\n" "$@"')
    jj = _jj_cli_running(test_root_concurrency_group, fake_jj)

    result = jj.run(["status"], tmp_path, snapshot=JjSnapshotPolicy.SNAPSHOT)

    assert result.stdout.splitlines() == ["--no-pager", "--color=never", "-R", str(tmp_path), "status"]


def test_run_outside_repository_passes_no_repository_option(
    test_root_concurrency_group: ConcurrencyGroup, tmp_path: Path
) -> None:
    fake_jj = _write_script(tmp_path / "fake-jj", 'echo "$PWD"\nprintf "%s\\n" "$@"')
    jj = _jj_cli_running(test_root_concurrency_group, fake_jj)

    result = jj.run_outside_repository(["git", "init", "--colocate", "dest"], tmp_path)

    cwd, *argv = result.stdout.splitlines()
    assert Path(cwd).resolve() == tmp_path.resolve()
    assert argv == ["--no-pager", "--color=never", "git", "init", "--colocate", "dest"]


def test_run_outside_repository_runs_the_resolved_jj(jj_cli: JjCli, jj_binary: JjBinary, tmp_path: Path) -> None:
    result = jj_cli.run_outside_repository(["--version"], tmp_path)

    assert result.stdout.startswith(f"jj {jj_binary.version}")


def test_a_read_ignoring_the_working_copy_adds_no_operation_and_does_not_see_unsnapshotted_files(
    jj_cli: JjCli, jj_binary: JjBinary, jj_workspace: JjWorkspace
) -> None:
    (jj_workspace.path / "unsnapshotted.txt").write_text("new\n")
    operations_before = _count_operations(jj_binary, jj_workspace.path)

    ignoring = jj_cli.run(["file", "list"], jj_workspace.path, snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY)
    operations_after_ignoring = _count_operations(jj_binary, jj_workspace.path)
    snapshotting = jj_cli.run(["file", "list"], jj_workspace.path, snapshot=JjSnapshotPolicy.SNAPSHOT)

    assert "unsnapshotted.txt" not in ignoring.stdout.splitlines()
    assert operations_after_ignoring == operations_before
    assert "unsnapshotted.txt" in snapshotting.stdout.splitlines()
    assert _count_operations(jj_binary, jj_workspace.path) == operations_before + 1


def test_a_checked_failure_raises_vcs_command_exit_error_and_an_unchecked_one_returns(
    jj_cli: JjCli, jj_colocated_repo: JjColocatedRepo
) -> None:
    arguments = ["log", "-r", "no_such_bookmark"]

    with pytest.raises(VcsCommandExitError) as error_info:
        jj_cli.run(arguments, jj_colocated_repo.path, snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY)
    unchecked = jj_cli.run(
        arguments, jj_colocated_repo.path, snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY, is_checked=False
    )

    assert "no_such_bookmark" in error_info.value.stderr
    assert unchecked.returncode != 0


def test_a_stale_working_copy_raises_even_when_unchecked_and_reads_ignoring_it_still_work(
    jj_cli: JjCli, jj_binary: JjBinary, jj_colocated_repo: JjColocatedRepo, jj_workspace: JjWorkspace
) -> None:
    make_workspace_stale(jj_binary, jj_colocated_repo.path, jj_workspace.path)

    with pytest.raises(JjWorkingCopyStaleError) as error_info:
        jj_cli.run(["status"], jj_workspace.path, snapshot=JjSnapshotPolicy.SNAPSHOT, is_checked=False)
    ignoring = jj_cli.run(
        ["log", "--no-graph", "-r", "@", "-T", "commit_id"],
        jj_workspace.path,
        snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY,
    )

    assert isinstance(error_info.value, VcsCommandExitError)
    assert ignoring.stdout.strip() != ""


def test_parse_refused_snapshot_files_reads_jj_warning_into_path_and_message() -> None:
    assert parse_refused_snapshot_files(_REFUSED_SNAPSHOT_STDERR) == {
        "sub/a: b c.bin": "4.9KiB (5000 bytes); the maximum size allowed is 1.0KiB (1024 bytes)",
        'x"y.bin': "2.9KiB (3000 bytes); the maximum size allowed is 1.0KiB (1024 bytes)",
    }


def test_parse_refused_snapshot_files_is_empty_without_the_warning() -> None:
    assert parse_refused_snapshot_files("Warning: Some unrelated warning\n  indented: line\n") == {}


def test_a_real_refused_file_is_reported_relative_to_the_workspace_root(
    jj_cli: JjCli, jj_workspace: JjWorkspace
) -> None:
    (jj_workspace.path / "big dir").mkdir()
    (jj_workspace.path / "big dir" / "large.bin").write_bytes(b"\0" * 1000)

    result = jj_cli.run(
        ["file", "list"],
        jj_workspace.path,
        snapshot=JjSnapshotPolicy.SNAPSHOT,
        config_overrides={"snapshot.max-new-file-size": "100"},
    )

    refused_files = parse_refused_snapshot_files(result.stderr)
    assert list(refused_files) == ["big dir/large.bin"]
    assert "1000 bytes" in refused_files["big dir/large.bin"]
    assert "big dir/large.bin" not in result.stdout.splitlines()


def test_a_resolver_that_returns_none_raises_vcs_binary_not_found(
    test_root_concurrency_group: ConcurrencyGroup, tmp_path: Path
) -> None:
    jj = JjCli(test_root_concurrency_group, lambda tool: None)

    with pytest.raises(VcsBinaryNotFoundError):
        jj.run(["status"], tmp_path, snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY)


def test_a_command_past_its_timeout_raises_vcs_command_timeout_error(
    test_root_concurrency_group: ConcurrencyGroup, tmp_path: Path
) -> None:
    hanging_jj = _write_script(tmp_path / "hanging-jj", "exec sleep 30")
    jj = _jj_cli_running(test_root_concurrency_group, hanging_jj)

    with pytest.raises(VcsCommandTimeoutError):
        jj.run(["status"], tmp_path, snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY, timeout=0.2)


def test_a_failed_read_is_not_retried(test_root_concurrency_group: ConcurrencyGroup, tmp_path: Path) -> None:
    attempts_file = tmp_path / "attempts"
    failing_jj = _write_script(tmp_path / "failing-jj", f'echo attempt >> "{attempts_file}"\nexit 1')
    jj = _jj_cli_running(test_root_concurrency_group, failing_jj)

    with pytest.raises(VcsCommandExitError):
        jj.run(["log"], tmp_path, snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY)

    assert len(attempts_file.read_text().splitlines()) == 1


def test_env_overrides_reach_jj_and_a_call_extra_env_wins_over_them(
    test_root_concurrency_group: ConcurrencyGroup, tmp_path: Path
) -> None:
    fake_jj = _write_script(tmp_path / "fake-jj", 'echo "$SCTEST_FROM_OVERRIDES $SCTEST_SHARED"')
    jj = JjCli(
        test_root_concurrency_group,
        lambda tool: str(fake_jj),
        lambda: {"SCTEST_FROM_OVERRIDES": "override", "SCTEST_SHARED": "override"},
    )

    result = jj.run(
        ["status"], tmp_path, snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY, extra_env={"SCTEST_SHARED": "call"}
    )

    assert result.stdout.strip() == "override call"
