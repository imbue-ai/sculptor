import time
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.processes.local_process import RunningProcess
from imbue_core.subprocess_utils import ProcessError
from imbue_core.thread_utils import ObservableThread
from sculptor.interfaces.environments.v1.base import LocalEnvironmentConfig
from sculptor.primitives.ids import LocalEnvironmentID
from sculptor.services.environment_service.environments.local_environment import LocalEnvironment
from sculptor.utils.concurrency_group import AncestorConcurrentFailure
from sculptor.utils.concurrency_group import ChildConcurrencyGroupDidNotExitError
from sculptor.utils.concurrency_group import ConcurrencyExceptionGroup
from sculptor.utils.concurrency_group import ConcurrencyGroup
from sculptor.utils.concurrency_group import InvalidConcurrencyGroupStateError
from sculptor.utils.concurrency_group import StrandTimedOutError

TINY_SLEEP = 0.001
SMALL_SLEEP = 0.1
LARGE_SLEEP = 1.0


def _small_sleep_and_return_1() -> int:
    time.sleep(0.1)
    return 1


@pytest.fixture()
def local_environment(tmp_path: Path):
    sandbox_dir = str(tmp_path / "sandbox")
    environment_config = LocalEnvironmentConfig()
    local_env = LocalEnvironment(
        config=environment_config,
        environment_id=LocalEnvironmentID(sandbox_dir),
        project_id=ProjectID(),
    )
    workspace_path = local_env.get_workspace_path()
    workspace_host_path = local_env.to_host_path(workspace_path)
    workspace_host_path.mkdir(parents=True, exist_ok=True)
    return local_env


def test_concurrency_group_shortly_waits_for_threads_to_finish():
    with ConcurrencyGroup() as cg:
        thread1 = cg.start_thread(target=_small_sleep_and_return_1)
        thread2 = cg.start_thread(target=_small_sleep_and_return_1)
        assert thread1.is_alive()
        assert thread2.is_alive()
    assert not thread1.is_alive()
    assert not thread2.is_alive()


def test_concurrency_group_shortly_waits_for_environment_processes_to_finish(local_environment: LocalEnvironment):
    with ConcurrencyGroup(environment=local_environment) as cg:
        process1 = cg.run_environment_process_in_background(["sleep", str(SMALL_SLEEP)], {})
        process2 = cg.run_environment_process_in_background(["sleep", str(SMALL_SLEEP)], {})
        assert process1.poll() is None
        assert process2.poll() is None
    assert process1.poll() is not None
    assert process2.poll() is not None


def test_concurrency_group_supports_running_to_completion(local_environment: LocalEnvironment):
    with ConcurrencyGroup(environment=local_environment) as cg:
        process = cg.run_environment_process_to_completion(["sleep", str(SMALL_SLEEP)], {})
    assert process.poll() == 0


def test_concurrency_group_raises_timeout_when_not_finished_in_time():
    start_time = time.monotonic()
    thread: ObservableThread | None = None
    with pytest.raises(ConcurrencyExceptionGroup) as exception_info:
        with ConcurrencyGroup(exit_timeout_seconds=SMALL_SLEEP) as cg:
            thread = cg.start_thread(target=lambda: time.sleep(LARGE_SLEEP))
    assert len(exception_info.value.exceptions) == 1
    assert isinstance(exception_info.value.exceptions[0], StrandTimedOutError)
    assert thread is not None
    end_time = time.monotonic()
    # Check that we waited approximately the right time.
    assert abs((end_time - start_time) - SMALL_SLEEP) < SMALL_SLEEP / 2
    assert thread.is_alive()


def test_concurrency_group_does_not_raise_when_within_timeout():
    start_time = time.monotonic()
    with ConcurrencyGroup(exit_timeout_seconds=SMALL_SLEEP) as cg:
        thread = cg.start_thread(target=lambda: time.sleep(TINY_SLEEP))
    end_time = time.monotonic()
    assert end_time - start_time < 0.1
    assert not thread.is_alive()


@mock.patch("imbue_core.thread_utils.log_exception")
@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_failed_threads_raise_when_probed(mock_log_exception: mock.MagicMock):
    i = 0
    with pytest.raises(ConcurrencyExceptionGroup) as exception_info:
        with ConcurrencyGroup() as cg:
            thread = cg.start_thread(target=lambda: 1 / 0)
            cg.raise_if_any_strands_or_ancestors_failed()
            i += 1
    assert len(exception_info.value.exceptions) == 1
    assert isinstance(exception_info.value.exceptions[0], ZeroDivisionError)
    # Check that we never got to the line after raise_if_any_strands_or_ancestors_failed.
    # (We cannot directly check that the exception was raised there because it's overshadowed by the one from the context manager exit.)
    assert i == 0


@mock.patch("imbue_core.thread_utils.log_exception")
@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_failed_threads_raise_when_exiting(mock_log_exception: mock.MagicMock):
    i = 0
    with pytest.raises(ConcurrencyExceptionGroup) as exception_info:
        with ConcurrencyGroup() as cg:
            thread = cg.start_thread(target=lambda: 1 / 0)
            i += 1
    assert len(exception_info.value.exceptions) == 1
    assert isinstance(exception_info.value.exceptions[0], ZeroDivisionError)
    assert i == 1


@mock.patch("imbue_core.thread_utils.log_exception")
@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_failed_threads_do_not_raise_when_suppressed(mock_log_exception: mock.MagicMock):
    with ConcurrencyGroup() as cg:
        thread = cg.start_thread(target=lambda: 1 / 0, suppressed_exceptions=(ZeroDivisionError,))
        cg.raise_if_any_strands_or_ancestors_failed()


def test_checked_failed_processes_raise_when_waited_for(local_environment: LocalEnvironment):
    i = 0
    with pytest.raises(ConcurrencyExceptionGroup) as exception_info:
        with ConcurrencyGroup(environment=local_environment) as cg:
            process = cg.run_environment_process_in_background(["bash", "-c", "exit 1"], {})
            process.wait()
            i += 1
        assert process.poll() == 1
    assert len(exception_info.value.exceptions) == 1
    assert isinstance(exception_info.value.exceptions[0], ProcessError)
    assert i == 0


def test_checked_failed_processes_raise_when_probed(local_environment: LocalEnvironment):
    i = 0
    with pytest.raises(ConcurrencyExceptionGroup) as exception_info:
        with ConcurrencyGroup(environment=local_environment) as cg:
            process = cg.run_environment_process_in_background(["bash", "-c", "exit 1"], {})
            # The command will be complete after the sleep even without an explicit wait.
            time.sleep(SMALL_SLEEP)
            cg.raise_if_any_strands_or_ancestors_failed()
            i += 1
        assert process.poll() == 1
    assert len(exception_info.value.exceptions) == 1
    assert isinstance(exception_info.value.exceptions[0], ProcessError)
    assert i == 0


def test_unchecked_failed_processes_do_not_raise(local_environment: LocalEnvironment):
    i = 0
    with ConcurrencyGroup(environment=local_environment) as cg:
        process = cg.run_environment_process_in_background(["bash", "-c", "exit 1"], {}, is_checked=False)
        process.wait()
        cg.raise_if_any_strands_or_ancestors_failed()
        i += 1
    assert process.poll() == 1
    assert i == 1


def test_probing_does_not_raise_when_no_failures_happened(local_environment: LocalEnvironment):
    with ConcurrencyGroup(environment=local_environment) as cg:
        process = cg.run_environment_process_in_background(["bash", "-c", "exit 0"], {})
        process.wait()
        thread = cg.start_thread(target=lambda: 1 + 1)
        thread.join()
        cg.raise_if_any_strands_or_ancestors_failed()


def test_do_not_allow_starting_new_strands_if_the_previous_failed(local_environment: LocalEnvironment):
    process1: RunningProcess | None = None
    process2: RunningProcess | None = None
    with pytest.raises(ConcurrencyExceptionGroup) as exception_info:
        with ConcurrencyGroup(environment=local_environment) as cg:
            process1 = cg.run_environment_process_in_background(["bash", "-c", "exit 1"], {})
            process1.wait()
            process2 = cg.run_environment_process_in_background(["sleep", str(SMALL_SLEEP)], {})
    assert isinstance(exception_info.value.exceptions[0], ProcessError)
    assert process1 is not None
    assert process1.poll() == 1
    assert process2 is None


def test_all_failure_modes_get_combined(local_environment: LocalEnvironment):
    with pytest.raises(ConcurrencyExceptionGroup) as exception_info:
        with ConcurrencyGroup(environment=local_environment, exit_timeout_seconds=SMALL_SLEEP) as cg:
            process1 = cg.run_environment_process_in_background(
                ["sleep", str(LARGE_SLEEP)],
                {},
            )
            process2 = cg.run_environment_process_in_background(["bash", "-c", "exit 1"], {})
            # Avoid explicitly calling wait() on process2 to test that the probing in the exit works.
            time.sleep(SMALL_SLEEP)
            i = 1 / 0
    assert len(exception_info.value.exceptions) == 3
    assert any(isinstance(e, ProcessError) for e in exception_info.value.exceptions)
    assert any(isinstance(e, ZeroDivisionError) for e in exception_info.value.exceptions)
    assert any(isinstance(e, StrandTimedOutError) for e in exception_info.value.exceptions)


def test_nesting_in_the_same_thread_just_works():
    with ConcurrencyGroup() as cg_outer:
        with ConcurrencyGroup() as cg_inner:
            pass


def _create_nested_concurrency_group(concurrency_group: ConcurrencyGroup, closure: dict):
    with concurrency_group.make_concurrency_group() as cg:
        cg.start_thread(target=lambda: closure.update({"i": _small_sleep_and_return_1()}))


def test_nesting_across_threads_works_and_properly_waits():
    closure = {"i": 0}
    with ConcurrencyGroup() as cg_outer:
        cg_outer.start_thread(target=_create_nested_concurrency_group, args=(cg_outer, closure))
        # Allow the nested group time to start (but not to finish) before exiting the outer group.
        time.sleep(TINY_SLEEP)
    assert closure["i"] == 1


def _create_nested_concurrency_group_that_expects_parent_failure(concurrency_group: ConcurrencyGroup, closure: dict):
    with pytest.raises(ConcurrencyExceptionGroup) as exception_info:
        with concurrency_group.make_concurrency_group() as cg:
            cg.start_thread(target=lambda: closure.update({"i": _small_sleep_and_return_1()}))
    assert len(exception_info.value.exceptions) == 1
    assert isinstance(exception_info.value.exceptions[0], AncestorConcurrentFailure)


def test_nesting_across_raises_timeout_when_child_group_does_not_finish_in_time():
    closure = {"i": 0}
    with pytest.raises(ConcurrencyExceptionGroup) as exception_info:
        with ConcurrencyGroup(exit_timeout_seconds=TINY_SLEEP) as cg_outer:
            cg_outer.start_thread(
                target=_create_nested_concurrency_group_that_expects_parent_failure, args=(cg_outer, closure)
            )
            time.sleep(TINY_SLEEP)
    assert any(
        isinstance(exception, ChildConcurrencyGroupDidNotExitError) for exception in exception_info.value.exceptions
    )
    assert closure["i"] == 0


def _create_nested_failing_concurrency_group(concurrency_group: ConcurrencyGroup):
    with concurrency_group.make_concurrency_group() as cg:
        cg.start_thread(target=lambda: 1 / 0)


@mock.patch("imbue_core.thread_utils.log_exception")
@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_error_from_nested_group_in_another_thread_gets_properly_propagated(mock_log_exception: mock.MagicMock):
    with pytest.raises(ConcurrencyExceptionGroup) as exception_info:
        with ConcurrencyGroup() as cg_outer:
            cg_outer.start_thread(target=_create_nested_failing_concurrency_group, args=(cg_outer,))
            time.sleep(TINY_SLEEP)
    assert len(exception_info.value.exceptions) == 1
    assert isinstance(exception_info.value.exceptions[0], ConcurrencyExceptionGroup)
    assert len(exception_info.value.exceptions[0].exceptions) == 1
    assert isinstance(exception_info.value.exceptions[0].exceptions[0], ZeroDivisionError)


def _create_two_nested_concurrency_groups_that_expect_parent_failure(
    concurrency_group: ConcurrencyGroup, closure: dict
):
    with pytest.raises(ConcurrencyExceptionGroup) as exception_info:
        with concurrency_group.make_concurrency_group() as cg_middle:
            try:
                with cg_middle.make_concurrency_group() as cg_inner:
                    thread = cg_inner.start_thread(target=lambda: closure.update({"i": _small_sleep_and_return_1()}))
                    thread.join()
            except ConcurrencyExceptionGroup as exception_info:
                # On exit, the concurrency group should notice that the root concurrency group failed:
                #   - Because of a timeout of the spawned (top-level) thread.
                #   - And because the nested groups didn't manage to exit cleanly in time.
                assert len(exception_info.exceptions) == 1
                ancestor_failure = exception_info.exceptions[0]
                assert isinstance(ancestor_failure, AncestorConcurrentFailure)
                assert isinstance(ancestor_failure.ancestor_exception, ConcurrencyExceptionGroup)
                assert len(ancestor_failure.ancestor_exception.exceptions) == 2
                assert any(isinstance(e, StrandTimedOutError) for e in ancestor_failure.ancestor_exception.exceptions)
                assert any(
                    isinstance(e, ChildConcurrencyGroupDidNotExitError)
                    for e in ancestor_failure.ancestor_exception.exceptions
                )
                # We check that the above asserts passed by checking the value of closure["i"] in the outer test.
                closure["i"] += 1


@mock.patch("imbue_core.thread_utils.log_exception")
@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")
def test_parent_failures_propagate_recursively(mock_log_exception: mock.MagicMock):
    closure: dict[str, Any] = {"i": 0}
    outer_thread: ObservableThread | None = None
    with pytest.raises(ConcurrencyExceptionGroup) as exception_info:
        with ConcurrencyGroup(exit_timeout_seconds=0.0001) as cg_outer:
            outer_thread = cg_outer.start_thread(
                target=_create_two_nested_concurrency_groups_that_expect_parent_failure, args=(cg_outer, closure)
            )
            time.sleep(0.001)
    assert outer_thread is not None
    outer_thread.join()
    # Make sure the inner thread actually ran to completion and then exited with exception because of the parent failure.
    assert closure["i"] == 2


def test_exhausted_concurrency_group_cannot_be_entered_again():
    cg = ConcurrencyGroup()
    with cg:
        cg.start_thread(target=lambda: 1)
    with pytest.raises(InvalidConcurrencyGroupStateError):
        with cg:
            pass


def test_exhausted_concurrency_group_cannot_start_threads():
    cg = ConcurrencyGroup()
    with cg:
        cg.start_thread(target=lambda: 1)
    with pytest.raises(InvalidConcurrencyGroupStateError):
        cg.start_thread(target=lambda: 1)


def test_exhausted_concurrency_group_cannot_make_nested_groups():
    cg = ConcurrencyGroup()
    with cg:
        cg.start_thread(target=lambda: 1)
    with pytest.raises(InvalidConcurrencyGroupStateError):
        cg_nested = cg.make_concurrency_group()
