import json
from contextlib import contextmanager
from pathlib import Path
from typing import Generator
from typing import Sequence
from typing import assert_never

from loguru import logger
from pydantic import Field
from pydantic import PrivateAttr
from pydantic import SkipValidation
from pydantic import ValidationError

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.agents.data_types.ids import TaskID
from imbue_core.itertools import remove_none
from imbue_core.nested_evolver import assign
from imbue_core.nested_evolver import chill
from imbue_core.nested_evolver import evolver
from imbue_core.pydantic_serialization import MutableModel
from imbue_core.pydantic_serialization import model_dump_json
from imbue_core.pydantic_serialization import model_load
from imbue_core.sculptor.state.messages import ChatInputUserMessage
from imbue_core.sculptor.state.messages import Message
from imbue_core.sculptor.state.messages import PersistentAgentMessage
from imbue_core.sculptor.state.messages import PersistentUserMessage
from imbue_core.serialization import SerializedException
from imbue_core.thread_utils import ObservableThread
from sculptor.interfaces.agents.v1.agent import Check
from sculptor.interfaces.agents.v1.agent import CheckControlUserMessage
from sculptor.interfaces.agents.v1.agent import CheckFinishedReason
from sculptor.interfaces.agents.v1.agent import CheckTrigger
from sculptor.interfaces.agents.v1.agent import ChecksDefinedRunnerMessage
from sculptor.interfaces.agents.v1.agent import EphemeralRequestCompleteAgentMessage
from sculptor.interfaces.agents.v1.agent import RestartCheckUserMessage
from sculptor.interfaces.agents.v1.agent import RunID
from sculptor.interfaces.agents.v1.agent import StopCheckUserMessage
from sculptor.interfaces.environments.v1.base import Environment
from sculptor.interfaces.environments.v1.base import ImageTypes
from sculptor.interfaces.environments.v1.errors import FileNotFoundEnvironmentError
from sculptor.primitives.executor import ObservableThreadPoolExecutor
from sculptor.services.task_service.data_types import ServiceCollectionForTask
from sculptor.tasks.handlers.run_agent.checks.check_loading import load_checks_from_environment
from sculptor.tasks.handlers.run_agent.checks.check_process import CheckProcess
from sculptor.tasks.handlers.run_agent.checks.constants import ALL_CHECKS_FILE_NAME
from sculptor.tasks.handlers.run_agent.checks.constants import CHECK_STATE_FILE_NAME
from sculptor.tasks.handlers.run_agent.checks.constants import CONVERSATION_FILE_NAME
from sculptor.tasks.handlers.run_agent.checks.errors import RestartCheckError
from sculptor.tasks.handlers.run_agent.checks.output_location import CheckRunOutputLocation
from sculptor.utils.secret import Secret


class CheckProcessController(MutableModel):
    """
    This class wraps all state and logic for managing CheckProcess instances, ie, the class that runs each check.

    Consumers should simply use it as a context manager and call the appropriate signal methods,
    and the controller will handle the rest.

    See the README for a description of the overall architecture and data layout.
    """

    task_id: TaskID = Field(frozen=True)
    project_id: ProjectID = Field(frozen=True)
    environment: Environment = Field(frozen=True)
    services: SkipValidation[ServiceCollectionForTask] = Field(frozen=True)
    root_data_path: Path = Field(frozen=True)

    _check_process_by_run_id: dict[RunID, CheckProcess] = PrivateAttr(default_factory=dict)
    _restore_check_controller_state_thread: ObservableThread | None = PrivateAttr(default=None)

    @contextmanager
    def start(
        self, snapshot_by_user_input_message_id: dict[AgentMessageID, ImageTypes], parent_task_id: TaskID | None
    ) -> Generator["CheckProcessController", None, None]:
        """
        Should be called when the task starts.

        Right now this just launches a thread to actually load the previous state for all checks.
        """
        if not self.services.settings.IS_CHECKS_ENABLED:
            yield self
            return

        self._start(snapshot_by_user_input_message_id, parent_task_id)
        try:
            yield self
        finally:
            self._stop()

    def on_persistent_user_message(self, message: ChatInputUserMessage) -> None:
        """
        Should be called when a new chat message is sent by the user.

        Right now this just cancels locally-running checks, since the agent may be mutating state
        in the container, and we don't want checks to be running at the same time bc they may spuriously fail
        """
        if not self.services.settings.IS_CHECKS_ENABLED:
            return

        # we cancel any checks that are running in the container when sending a new user input message bc
        # otherwise the agent may be mutating state under the check, which will lead to inconsistent results
        self._cancel_local_checks_in_container()

    def on_filesystem_change(
        self,
        is_agent_turn_finished: bool,
        is_next_message_in_progress: bool,
        current_user_message_id: AgentMessageID | None,
        snapshot: ImageTypes | None,
        secrets: dict[str, str | Secret],
        persistent_message_history: Sequence[PersistentUserMessage | PersistentAgentMessage],
    ) -> None:
        """
        Should be called when the filesystem changes, ie, after the agent has responded (causing a snapshot) or
        after local sync changes have been applied.

        Right now, we only bother re-running checks after a snapshot.  One could imagine running checks after all
        changes, but we don't do that right now.

        Note that there doesn't need to be a snapshot, see `CheckProcess` for more details.
        """
        if not self.services.settings.IS_CHECKS_ENABLED:
            return

        # first make sure we're done emitting messages for previous checks before we start new ones
        self._restore_check_controller_state_thread.join()
        # make sure that we've loaded the current checks
        # this causes some side effects as well, which allow us to re-run these checks later
        output_location_by_check = self._set_checks_and_conversation_history_for_this_turn(
            current_user_message_id, persistent_message_history
        )

        # start any checks that happen on every filesystem change (eg, seeing if the checks.toml file is up-to-date)
        self._launch_checks_for_event(
            CheckTrigger.FILE_CHANGE, snapshot, output_location_by_check, is_next_message_in_progress, secrets
        )

        # if the agent turn just ended, we can kick off any required checks
        if is_agent_turn_finished:
            # then actually go start the new checks
            self._launch_checks_for_event(
                CheckTrigger.AGENT_MESSAGE, snapshot, output_location_by_check, is_next_message_in_progress, secrets
            )

    def handle_message(
        self,
        message: Message,
        current_user_chat_message_id: AgentMessageID | None,
        secrets: dict[str, str | Secret],
        snapshot_by_user_input_message_id: dict[AgentMessageID, ImageTypes],
    ) -> bool:
        """
        Handle messages that are specifically intended for the check controller, ie, `CheckControlUserMessage`s

        Returns True if the message was handled, False otherwise.
        """
        if not self.services.settings.IS_CHECKS_ENABLED:
            return False

        if isinstance(message, CheckControlUserMessage):
            # first make sure we're done emitting messages for previous checks before we start new ones
            self._restore_check_controller_state_thread.join()
            # then actually go handle the user message
            failure = None
            match message:
                case StopCheckUserMessage() as stop_message:
                    self._stop_by_run_id(stop_message.run_id)
                case RestartCheckUserMessage() as restart_message:
                    failure = self._restart_check_process(
                        current_user_chat_message_id, restart_message, secrets, snapshot_by_user_input_message_id
                    )
                case _ as unreachable:
                    assert_never(unreachable)
            with self.services.data_model_service.open_task_transaction() as transaction:
                response_message = EphemeralRequestCompleteAgentMessage(
                    message_id=AgentMessageID(), request_id=message.message_id, error=failure
                )
                self.services.task_service.create_message(response_message, self.task_id, transaction)
            return True
        return False

    def _start(
        self, snapshot_by_user_input_message_id: dict[AgentMessageID, ImageTypes], parent_task_id: TaskID | None
    ) -> None:
        # make any leftover check state consistent and understand what checks were run at each conversation turn
        # is run in a thread so that we keep this out of the critical section
        self._restore_check_controller_state_thread = ObservableThread(
            target=self._restore_check_controller_state,
            args=(snapshot_by_user_input_message_id, parent_task_id),
            name="_restore_checks",
        )
        self._restore_check_controller_state_thread.start()

    def _stop(self) -> None:
        """
        Should be called when the task stops.

        Right now this just stops any running check threads. The processes will be cleaned up by the Environment.
        """
        for check_process in self._check_process_by_run_id.values():
            check_process.abandon()
        if self._restore_check_controller_state_thread is not None:
            # note: currently we just join this, even though it could take a little while.
            self._restore_check_controller_state_thread.join()

    def _restore_check_controller_state(
        self, snapshot_by_user_input_message_id: dict[AgentMessageID, ImageTypes], parent_task_id: TaskID | None
    ) -> None:
        """
        Called in a thread. Is responsible for loading any previous check state from disk,
        and emitting the appropriate messages so that the task is aware of
        what checks were run and what their results were.

        Is also responsible for properly migrating state when forking from a previous task.
        This is done by copying all the check state from the parent task into the current task,
        """

        if parent_task_id is None:
            missing_check_reason = CheckFinishedReason.SCULPTOR_CRASHED
        else:
            missing_check_reason = CheckFinishedReason.FORKED
            # TODO: technically we could optimize this by only copying the checks that are still running,
            #  and simply symlinking everything else (since this is supposed to be write-only)
            #  However, for simplicity right now, we're just going to copy everything.
            source_task_folder = self.environment.to_host_path(self.root_data_path / str(parent_task_id))
            dest_task_folder = self.environment.to_host_path(self.root_data_path / str(self.task_id))
            copy_process = self.environment.run_process_in_background(
                ["cp", "-r", str(source_task_folder), str(dest_task_folder)], {}
            )
            assert copy_process.wait() == 0, f"Failed to copy check state from {parent_task_id} to {self.task_id}"

        # TODO: this could be further optimized to load both of these types of data in parallel,
        #  but idk that it's worth the complexity right now, since I doubt we'll be blocked on this...

        run_paths = _load_check_run_paths(self.task_id, self.root_data_path, self.environment)

        # process each run folder via a ThreadPoolExecutor instead, since that will lower latency
        with ObservableThreadPoolExecutor(thread_name_prefix="load_check_run_data") as executor:
            previous_runs = remove_none(
                executor.map(
                    lambda run_path: self._gather_messages_for_previous_run(
                        run_path, snapshot_by_user_input_message_id, missing_check_reason
                    ),
                    run_paths,
                )
            )

        check_definition_paths_by_message_id = _load_check_definition_paths_by_message_id(
            self.task_id, self.root_data_path, self.environment
        )

        # read definitions for all checks in parallel
        with ObservableThreadPoolExecutor(thread_name_prefix="load_check_configs") as executor:
            checks_and_user_message_ids = list(
                zip(
                    check_definition_paths_by_message_id.keys(),
                    executor.map(
                        lambda file: _load_all_checks(file, self.environment),
                        check_definition_paths_by_message_id.values(),
                    ),
                )
            )

        # we need to properly order the check runs by time (otherwise multiple runs may be misordered)
        sorted_runs = sorted(previous_runs)

        # save all messages
        with self.services.data_model_service.open_task_transaction() as transaction:
            for user_message_id, checks in checks_and_user_message_ids:
                checks_defined_message = ChecksDefinedRunnerMessage(
                    user_message_id=user_message_id, check_by_name=checks
                )
                self.services.task_service.create_message(checks_defined_message, self.task_id, transaction)
            for run_time, old_run_id, messages in sorted_runs:
                for message in messages:
                    self.services.task_service.create_message(message, self.task_id, transaction)

    def _set_checks_and_conversation_history_for_this_turn(
        self,
        user_message_id: AgentMessageID,
        persistent_message_history: Sequence[PersistentUserMessage | PersistentAgentMessage],
    ) -> dict[Check, CheckRunOutputLocation]:
        """
        Reload the defined checks from the environment,
        and emit a message to communicate their current state as of this user message ID.

        Also writes the check definitions to disk so that they can be used later,
        and writes the current conversation state so that it is accessible to checks as well.

        Should be called whenever the repo changes in the environment, so the user can see the latest checks.
        """
        # note -- it is ok that we ignore the suggestions from loading here -- they're handled by the SCULPTOR_SYSTEM_CHECK_NAME check
        checks, _suggestions_from_loading = load_checks_from_environment(
            self.environment, self.services.settings.IS_IMBUE_VERIFY_CHECK_ENABLED
        )

        output_location_by_check = {}
        for check_name, check in checks.items():
            output_location = CheckRunOutputLocation(
                run_id=RunID(),
                task_id=self.task_id,
                user_message_id=user_message_id,
                check_name=check.name,
                root_data_path=str(self.root_data_path.absolute()),
            )
            message_folder = output_location.to_message_folder()
            output_location_by_check[check] = output_location

        if len(checks) == 0:
            # if there were no real checks, run an empty check just to get the message folder
            output_location = CheckRunOutputLocation(
                run_id=RunID(),
                task_id=self.task_id,
                user_message_id=user_message_id,
                check_name="",
                root_data_path=str(self.root_data_path.absolute()),
            )
            message_folder = output_location.to_message_folder()

        # also write the messages (for later use)
        serialized_conversation_messages = [model_dump_json(x) for x in persistent_message_history]
        self.environment.write_file(
            f"{message_folder}/{CONVERSATION_FILE_NAME}", "\n".join(serialized_conversation_messages) + "\n"
        )

        if len(checks) > 0:
            check_data = {}
            for check in checks.values():
                check_data[check.name] = check.model_dump(mode="json")
            self.environment.write_file(f"{message_folder}/{ALL_CHECKS_FILE_NAME}", json.dumps(check_data) + "\n")

        # emit a user message that contains all current checks for this user_message_id
        with self.services.data_model_service.open_task_transaction() as transaction:
            message = ChecksDefinedRunnerMessage(user_message_id=user_message_id, check_by_name=checks)
            self.services.task_service.create_message(message, self.task_id, transaction)

        return output_location_by_check

    def _launch_checks_for_event(
        self,
        event: CheckTrigger,
        snapshot: ImageTypes | None,
        output_location_by_check: dict[Check, CheckRunOutputLocation],
        is_next_message_in_progress: bool,
        secrets: dict[str, str | Secret],
    ) -> None:
        """
        Handles actually creating and starting the CheckProcess instances for a given "event", ie, a CheckTrigger

        Right now we only support CheckTrigger.AGENT_MESSAGE, ie, starting checks after the agent has responded
        and created a new snapshot, but we'll probably want to add USER_MESSAGE as an option as well (eg, to allow
        checks to run right after the user has sent a message, in case we want to flag issues with their input)
        """
        # for each check, start the appropriate process / container / etc. It will create and send the correct message
        for check, output_location in output_location_by_check.items():
            # only start the check if this is the right event type
            if check.trigger != event:
                continue

            # don't bother starting checks when there's a pending message and the check is not forked
            # (since it would end up running on container state that was mutated by the agent)
            is_safe_to_execute_alongside_agent = check.is_forked or check.is_local_concurrency_allowed
            if is_next_message_in_progress and not is_safe_to_execute_alongside_agent:
                continue

            # actually start the check
            check_process = CheckProcess(
                snapshot=snapshot,
                # update the run_id so that it is unique for this run
                output_location=output_location.evolve(output_location.ref().run_id, RunID()),
                check=check,
            )
            check_process.start(self.environment, secrets, self.services, self.project_id)
            self._check_process_by_run_id[check_process.output_location.run_id] = check_process

    def _restart_check_process(
        self,
        current_user_message_id: AgentMessageID | None,
        restart_message: RestartCheckUserMessage,
        secrets: dict[str, str | Secret],
        snapshot_by_user_input_message_id: dict[AgentMessageID, ImageTypes],
    ) -> SerializedException | None:
        """
        Handles restarting a check process from a previous run.

        Just stop any running instances of the check for the given user message ID and check name,
        and then start a new one from the current check definition and snapshot
        """

        run_ids = self._get_active_run_ids(restart_message.check_name, restart_message.user_message_id)
        # there's usually just one, but just in case something went wrong:
        for run_id in run_ids:
            self._stop_by_run_id(run_id)
        # this is a little tricky -- we need to get the *latest* snapshot for a given user message ID
        # and that's what ought to be used for running this check
        # this is because local_sync should be updating that snapshot id
        snapshot = snapshot_by_user_input_message_id.get(restart_message.user_message_id, None)
        try:
            self._start_check_process_from_current_definition(
                restart_message, current_user_message_id, snapshot, secrets
            )
        except RestartCheckError as e:
            return SerializedException.build(e)
        return None

    def _start_check_process_from_current_definition(
        self,
        restart_message: RestartCheckUserMessage,
        current_user_message_id: AgentMessageID,
        # the snapshot at which we should run the check
        # we should generally have the snapshot unless:
        # 1. we just upgraded from the old code, before this data was properly tracked
        # 2. the snapshotting operation failed, was impossible to attempt in the first place, or was deleted
        # in either case, we can simply say "sorry, this check cannot be restarted"
        snapshot: ImageTypes | None,
        secrets: dict[str, str | Secret],
    ) -> None:
        """
        Loads the current definition of a given check, and starts a new CheckProcess for it.

        Ensures that the check is using the latest configuration.
        """
        check_name = restart_message.check_name
        output_location = CheckRunOutputLocation(
            run_id=RunID(),
            task_id=self.task_id,
            user_message_id=current_user_message_id,
            check_name=check_name,
            root_data_path=str(self.root_data_path.absolute()),
        )
        result = _load_check_process_from_location(
            output_location, self.task_id, self.environment, {current_user_message_id: snapshot}
        )
        if result is None:
            raise RestartCheckError(f"Cannot restart check {check_name}: no previous check found")

        # we were able to load the previous check -- now make sure it is valid to restart
        archival_reason, check_process, run_time = result
        if restart_message.user_message_id != current_user_message_id and not check_process.check.is_forked:
            raise RestartCheckError(
                f"Cannot run a (non-forked) check unless it is from the most recent state: {check_process.output_location.check_name}"
            )
        if snapshot is None:
            reason = "no snapshot" if check_process.check.is_forked else "outdated state"
            raise RestartCheckError(f"Cannot restart check {check_name}: {reason}")
        if archival_reason:
            raise RestartCheckError(f"Cannot restart check {check_name}: {archival_reason}")

        mutable_check_process = evolver(check_process)
        # update the check process with the new snapshot
        assign(mutable_check_process.snapshot, lambda: snapshot)
        # and give it a new run ID
        new_output_location = check_process.output_location.evolve(check_process.output_location.ref().run_id, RunID())
        assign(mutable_check_process.output_location, lambda: new_output_location)
        updated_check_process = chill(mutable_check_process)

        check_process.start(self.environment, secrets, self.services, self.project_id)
        self._check_process_by_run_id[updated_check_process.output_location.run_id] = updated_check_process

    def _cancel_local_checks_in_container(self) -> None:
        run_ids_to_remove = []
        for run_id, check_process in self._check_process_by_run_id.items():
            if not check_process.check.is_forked and not check_process.check.is_local_concurrency_allowed:
                check_process.stop(CheckFinishedReason.INTERRUPTED)
                run_ids_to_remove.append(run_id)
        for run_id in run_ids_to_remove:
            # FIXME: we'll need to have some locks around access to this dict (if we actually want to delete the old stuff)
            #  and if we do, we'll probably want to delete it from other functions as well, eg, when responding to events, check the old ones
            #  otherwise these will simply accumulate forever
            del self._check_process_by_run_id[run_id]

    def _get_active_run_ids(self, check_name: str, user_message_id: AgentMessageID) -> list[RunID]:
        """returns all run IDs for the given check name and user message ID that have not finished yet"""
        run_ids = []
        for run_id, process in self._check_process_by_run_id.items():
            if (
                process.output_location.check_name == check_name
                and process.output_location.user_message_id == user_message_id
            ):
                if not process.is_finished_running():
                    run_ids.append(run_id)
        return run_ids

    def _stop_by_run_id(self, run_id: RunID) -> None:
        """stops a particular check process"""
        if run_id in self._check_process_by_run_id:
            check_process = self._check_process_by_run_id[run_id]
            check_process.stop(CheckFinishedReason.STOPPED)
            del self._check_process_by_run_id[run_id]
            return

    def _gather_messages_for_previous_run(
        self,
        run_path: str,
        snapshot_by_user_input_message_id: dict[AgentMessageID, ImageTypes],
        default_reason: CheckFinishedReason,
    ) -> tuple[float, RunID, list[Message]] | None:
        """Is meant to be run in a thread in order to load all previous check data"""
        result = _load_check_process_from_file(
            run_path, self.task_id, self.environment, snapshot_by_user_input_message_id
        )
        if result is None:
            return None
        archival_reason, check_process, run_time = result
        messages = check_process.gather_messages_from_previous_run(archival_reason, self.environment, default_reason)
        # the run_time and run_id are just there for stably sorting such that we always get things in the same order
        return (run_time, check_process.output_location.run_id, messages)


def _load_check_run_paths(task_id: TaskID, root_data_path: Path, environment: Environment) -> list[str]:
    find_command = [
        "find",
        str(environment.to_host_path(root_data_path / str(task_id))),
        "-name",
        CHECK_STATE_FILE_NAME,
        "-type",
        "f",
    ]
    process = environment.run_process_in_background(find_command, secrets={})
    exit_code = process.wait()
    assert exit_code in (0, 1)
    lines = process.read_stdout()
    run_paths = []
    for line in lines.splitlines():
        line = line.strip()
        if line:
            path = Path(line)
            assert path.name == CHECK_STATE_FILE_NAME
            run_paths.append(str(environment.to_environment_path(path.parent)))
    return run_paths


def _load_check_definition_paths_by_message_id(
    task_id: TaskID, root_data_path: Path, environment: Environment
) -> dict[AgentMessageID, str]:
    find_command = [
        "find",
        str(environment.to_host_path(root_data_path / str(task_id))),
        "-name",
        ALL_CHECKS_FILE_NAME,
        "-type",
        "f",
    ]
    process = environment.run_process_in_background(find_command, secrets={})
    exit_code = process.wait()
    assert exit_code in (0, 1)
    lines = process.read_stdout()
    result: dict[AgentMessageID, str] = {}
    for line in lines.splitlines():
        line = line.strip()
        if line:
            path = Path(line)
            folder = path.parent
            assert path.name == ALL_CHECKS_FILE_NAME
            fixed_path = environment.to_environment_path(folder)
            message_id_component = folder.name
            message_id = AgentMessageID(message_id_component)
            result[message_id] = str(fixed_path / ALL_CHECKS_FILE_NAME)
    return result


def _load_check_process_from_file(
    run_path: str,
    task_id: TaskID,
    environment: Environment,
    snapshot_by_user_input_message_id: dict[AgentMessageID, ImageTypes],
) -> tuple[str, CheckProcess, float] | None:
    try:
        output_location = CheckRunOutputLocation.build_from_folder(run_path)
    except ValidationError as e:
        # can't really do anything if it's not even json, probably corrupted during a write or something
        logger.warning("{}: check data path {} is invalid because {}", task_id, run_path, e)
        return None
    else:
        return _load_check_process_from_location(
            output_location, task_id, environment, snapshot_by_user_input_message_id
        )


def _load_check_process_from_location(
    output_location: CheckRunOutputLocation,
    task_id: TaskID,
    environment: Environment,
    snapshot_by_user_input_message_id: dict[AgentMessageID, ImageTypes],
) -> tuple[str, CheckProcess, float] | None:
    # load the check data
    all_checks_path = f"{output_location.to_message_folder()}/{ALL_CHECKS_FILE_NAME}"
    all_checks = _load_all_checks(all_checks_path, environment)
    try:
        run_time = environment.get_file_mtime(all_checks_path)
    except FileNotFoundEnvironmentError as e:
        logger.warning("{}: could not find check data at {}, skipping: {}", task_id, all_checks_path, e)
        return None
    # properly handle the case where the Check format has shifted
    check = all_checks.get(output_location.check_name, None)
    if check is None:
        # can't really do anything if it's not even json, probably corrupted during a write or something
        logger.warning(
            "{}: check data at {} did not have {}, skipping", task_id, output_location.check_name, all_checks_path
        )
        return None
    snapshot = snapshot_by_user_input_message_id.get(output_location.user_message_id, None)
    check_process = CheckProcess(
        output_location=output_location,
        snapshot=snapshot,
        check=check,
    )
    return check_process.check.outdated_reason, check_process, run_time


def _load_all_checks(file_path: str, environment: Environment) -> dict[str, Check]:
    try:
        file_data = environment.read_file(file_path)
    except FileNotFoundError:
        # if the file doesn't exist, we can just return an empty dict
        return {}
    results = {}
    for key, value in json.loads(file_data.strip()).items():
        check, archival_reason = _load_potentially_outdated_check(value)
        if check is not None:
            results[key] = check
    return results


def _load_potentially_outdated_check(check_data: dict) -> tuple[Check | None, str]:
    try:
        check = model_load(Check, check_data)
        return check, ""
    except ValidationError as e:
        try:
            archival_reason = f"check data format is old: {e}"
            check = Check.model_construct(
                name=check_data["name"],
                command=check_data["command"],
                outdated_reason=archival_reason,
            )
            return check, archival_reason
        except json.JSONDecodeError:
            return None, ""
