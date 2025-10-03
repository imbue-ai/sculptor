import traceback
from pathlib import Path
from threading import Event
from threading import Thread
from typing import Sequence

from loguru import logger
from pydantic import AnyUrl
from pydantic import Field
from pydantic import PrivateAttr
from pydantic import ValidationError

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.async_monkey_patches import log_exception
from imbue_core.constants import DISCORD_URL
from imbue_core.constants import ExceptionPriority
from imbue_core.processes.local_process import RunningProcess
from imbue_core.pydantic_serialization import MutableModel
from imbue_core.pydantic_serialization import model_dump_json
from imbue_core.pydantic_serialization import model_load_json
from imbue_core.sculptor.state.messages import Message
from imbue_core.suggestions import Suggestion
from imbue_core.suggestions import UseSuggestionAction
from imbue_core.suggestions import VisitLinkSuggestionAction
from imbue_core.thread_utils import ObservableThread
from sculptor.config.user_config import get_user_config_instance
from sculptor.interfaces.agents.v1.agent import Check
from sculptor.interfaces.agents.v1.agent import CheckFinishedReason
from sculptor.interfaces.agents.v1.agent import CheckFinishedRunnerMessage
from sculptor.interfaces.agents.v1.agent import CheckLaunchedRunnerMessage
from sculptor.interfaces.agents.v1.agent import CheckSource
from sculptor.interfaces.agents.v1.agent import NewSuggestionRunnerMessage
from sculptor.interfaces.environments.v1.base import Environment
from sculptor.interfaces.environments.v1.base import ImageTypes
from sculptor.interfaces.environments.v1.errors import EnvironmentFailure
from sculptor.services.anthropic_credentials_service.api import AnthropicApiKey
from sculptor.services.task_service.data_types import ServiceCollectionForTask
from sculptor.tasks.handlers.run_agent.checks.check_loading import load_checks_from_environment
from sculptor.tasks.handlers.run_agent.checks.constants import CHECK_CONFIG_PATH
from sculptor.tasks.handlers.run_agent.checks.constants import CHECK_STATE_FILE_NAME
from sculptor.tasks.handlers.run_agent.checks.constants import CONVERSATION_FILE_NAME
from sculptor.tasks.handlers.run_agent.checks.constants import SCULPTOR_SYSTEM_CHECK_NAME
from sculptor.tasks.handlers.run_agent.checks.errors import CheckStopped
from sculptor.tasks.handlers.run_agent.checks.errors import CheckTimeout
from sculptor.tasks.handlers.run_agent.checks.output_location import CheckRunOutputLocation
from sculptor.utils.secret import Secret


class CheckProcess(MutableModel):
    # if validation failed, there will be a string in config_error with suggestions about how to fix
    check: Check = Field(frozen=True)
    # where to put the resulting check data
    output_location: CheckRunOutputLocation = Field(frozen=True)
    # the image from which the check will be run
    # there are 2 reasons this can be None:
    # 1. the snapshot failed to be created. In this case, we cannot really do very much if we're trying to run in a fork,
    #    so just fail the check immediately (though if we're running local checks they can simply run normally)
    # 2. the snapshot could not be loaded bc the format changed. In this case it doesn't matter, because `snapshot` is not required for gather_messages_from_previous_run
    #    but obviously it does mean that you won't be able to re-run those checks
    snapshot: ImageTypes | None = Field(frozen=True)

    # private variables, mutated while running
    _process: RunningProcess | None = PrivateAttr(default=None)
    _environment: Environment | None = PrivateAttr(default=None)
    _thread: Thread | None = PrivateAttr(default=None)
    _stop_event: Event = PrivateAttr(default_factory=lambda: Event())
    _stop_reason: CheckFinishedReason | None = PrivateAttr(default=None)

    # called for a check where the previous run was not finished, eg because Sculptor exited
    def gather_messages_from_previous_run(
        self, archival_reason: str, environment: Environment, default_reason: CheckFinishedReason
    ) -> list[Message]:
        # figure out what happened during the previous run
        finished_reason = _load_finished_reason_from_volume(self, environment, default_reason)
        exit_code = _load_exit_code_from_volume(self, environment)
        messages: list[Message] = []
        run_id = self.output_location.run_id
        messages.append(
            CheckFinishedRunnerMessage(
                user_message_id=self.output_location.user_message_id,
                check=self.check,
                run_id=run_id,
                exit_code=exit_code,
                finished_reason=finished_reason,
                archival_reason=archival_reason,
            )
        )
        # it's easier to process on the other side if we can be guaranteed that the check exists before suggestions are sent,
        # so we load suggestions after creating the CheckFinishedRunnerMessage
        suggestions = _load_suggestions_from_volume(self, environment)
        if len(suggestions) > 0:
            messages.append(
                NewSuggestionRunnerMessage(
                    suggestions=tuple(suggestions),
                    run_id=self.output_location.run_id,
                    check_name=self.output_location.check_name,
                    user_message_id=self.output_location.user_message_id,
                )
            )
        return messages

    def start(
        self,
        remote_environment: Environment,
        secrets: dict[str, str | Secret],
        services: ServiceCollectionForTask,
        project_id: ProjectID,
    ) -> None:
        self._environment = None if self.check.is_forked else remote_environment
        if not self._stop_event.is_set():
            self._thread = ObservableThread(
                target=self.run,
                args=(secrets, project_id, services),
                name=f"CheckProcess-{self.output_location.run_id}",
            )
            self._thread.start()

    def is_finished_running(self) -> bool:
        if self._thread is None:
            return False
        return not self._thread.is_alive()

    def run(self, secrets: dict[str, str | Secret], project_id: ProjectID, services: ServiceCollectionForTask) -> None:
        exit_code: int | None = None
        finished_reason: CheckFinishedReason | None = None
        error_suggestion: Suggestion | None = None
        is_in_unknown_state = False

        user_config = get_user_config_instance()
        if not user_config or not user_config.is_suggestion_beta_feature_on:
            logger.debug("Suggestions beta feature disabled, returning early.")
            return

        logger.debug("Suggestions beta feature enabled, proceeding as expected.")

        try:
            # in case the system is overloaded and we got stopped immediately, just exit immediately
            if self._stop_event.is_set():
                raise CheckStopped()

            # send a message to indicate that the check has been launched
            self._send_message(
                CheckLaunchedRunnerMessage(
                    message_id=AgentMessageID(),
                    check=self.check,
                    run_id=self.output_location.run_id,
                    snapshot=self.snapshot,
                    user_message_id=self.output_location.user_message_id,
                ),
                services,
            )

            # before we do anything else, report all of our initial suggestions along with the fact that we've started
            config_suggestions = _get_configuration_suggestions(self.check)
            if self.check.config_error:
                self._on_new_suggestions(config_suggestions, services)

            # deal with system checks first (they are just python code that runs in the server, not processes)
            if self.check.source == CheckSource.SYSTEM:
                # this default check is about seeing if anything goes wrong when we try to load the checks config
                if self.check.name == SCULPTOR_SYSTEM_CHECK_NAME:
                    _current_checks, suggestions_from_loading = load_checks_from_environment(
                        self._environment, services.settings.IS_IMBUE_VERIFY_CHECK_ENABLED
                    )
                    self._on_new_suggestions(suggestions_from_loading, services)
                # TODO: we could add extra checks here if anything else was misconfigured (ex: low disk space, etc)
                else:
                    raise NotImplementedError(f"Unknown system check: {self.check.name}")
                finished_reason = CheckFinishedReason.FINISHED
                # also need to save the definition of the check so that it gets loaded next time, just to be consistent
                self._save_check_json_file()
                return

            # TODO: it probably also makes sense to finish here if we have a non-empty archival reason

            # otherwise, we're guaranteed to have a command:
            assert self.check.command is not None

            if self._environment is None:
                if self.check.is_forked:
                    assert self.snapshot is not None, "Cannot run forked check without a snapshot"
                    self._environment = services.environment_service.create_environment(self.snapshot, project_id)

            # after starting the environment, check again to see if we need to stop...
            if self._stop_event.is_set():
                raise CheckStopped()

            # figure out the env vars
            run_output_folder = self.output_location.to_run_folder()
            inner_folder = self._environment.to_host_path(Path(run_output_folder))
            assert self.check.name == self.output_location.check_name, (
                f"Check name mismatch: {self.check.name} != {self.output_location.check_name}"
            )

            # inject token at the last second
            anthropic_credentials = services.anthropic_credentials_service.get_anthropic_credentials()
            if anthropic_credentials and isinstance(anthropic_credentials, AnthropicApiKey):
                secrets["ANTHROPIC_API_KEY"] = anthropic_credentials.anthropic_api_key

            standard_vars = dict(
                # canonically, checks should put their output here (they'll need to mkdir themselves)
                RUN_OUTPUT_FOLDER=f"{inner_folder}/output",
                RUN_ID=str(self.output_location.run_id),
                CHECK_NAME=self.output_location.check_name,
                USER_MESSAGE_ID=str(self.output_location.user_message_id),
                TASK_ID=str(self.output_location.task_id),
                AGENT_DATA=self._environment.to_host_path(Path(self.output_location.root_data_path)),
                CONVERSATION_FILE=self._environment.to_host_path(
                    Path(self.output_location.to_message_folder()) / CONVERSATION_FILE_NAME
                ),
            )
            env_vars = {**{k: Secret(v) for k, v in standard_vars.items()}, **secrets}

            # write before we even start the command so that we can tell if this was ever run when restoring
            self._save_check_json_file()

            normal_path = "${_IMBUE_USER_ORIGINAL_PATH:-/bin}"
            command_with_path = (
                f"export PATH={normal_path}:/imbue_addons/agent_path_extension_bin/ && {self.check.command}"
            )
            command_as_args = [
                "bash",
                "-c",
                "set -o pipefail; (((("
                + command_with_path
                # this is necessary to get stdout, stderr, and a combined log
                # https://unix.stackexchange.com/questions/6430/how-to-redirect-stderr-and-stdout-to-different-files-and-also-display-in-termina/6431#6431
                # note that you do not want to use process substitution here because the shell won't wait, which causes race conditions:
                # https://unix.stackexchange.com/questions/388519/bash-wait-for-process-in-process-substitution-even-if-command-is-invalid
                + f") | tee {inner_folder}/stdout ) 3>&1 1>&2 2>&3 | tee {inner_folder}/stderr | tee -a /{inner_folder}/combined_logs ) 3>&1 1>&2 2>&3) | tee -a /{inner_folder}/combined_logs",
            ]
            working_dir = self._environment.get_workspace_path()

            # before we go starting the process, check if the stop event is set
            if self._stop_event.is_set():
                raise CheckStopped()

            # actually launch the process
            self._process = self._environment.run_process_in_background(
                command_as_args, cwd=str(working_dir.absolute()), secrets=env_vars, timeout=self.check.timeout_seconds
            )
            # write the snapshot id to the run folder if we have one
            if self.check.is_forked:
                self._environment.write_file(
                    f"{run_output_folder}/snapshot_id", str(self.snapshot.image_id) + "\n", mode="w"
                )

            # write the command to the run folder (just to make it easier for the poor little LLM)
            self._environment.write_file(f"{run_output_folder}/command", self.check.command + "\n", mode="w")

            # now continually read the output and see if we get any suggestions
            output_queue = self._process.get_queue()
            is_reading_suggestions_from_stdout = False
            while not self._stop_event.is_set():
                # check if the process is still around
                exit_code = self._process.poll()

                # empty the output queue
                suggestions = []
                while output_queue.qsize() > 0:
                    line, is_stdout = output_queue.get(block=False)
                    if is_stdout:
                        if not is_reading_suggestions_from_stdout:
                            if line.strip() == "IMBUE_SUGGESTIONS_PROTOCOL_V0.0.1":
                                is_reading_suggestions_from_stdout = True
                                continue
                        if is_reading_suggestions_from_stdout:
                            try:
                                suggestion = model_load_json(Suggestion, line.strip())
                            except ValidationError:
                                pass
                            else:
                                suggestions.append(suggestion)

                # write the suggestions to a file as well for resumption, and notify the user
                if len(suggestions) > 0:
                    self._on_new_suggestions(suggestions, services)

                # if the process has finished, we can stop
                if exit_code is not None:
                    break

            # make sure the process is stopped
            exit_code = self._stop_process()

            # if it timed out, make a suggestion to either bump the timeout or optimize the check
            if self._process.get_timed_out():
                suggestion = Suggestion(
                    title=f"Fix {self.output_location.check_name} timeout",
                    description=f"{self.output_location.check_name} timed out after {self.check.timeout_seconds} seconds. You can either increase the timeout or optimize the check to run faster.",
                    severity_score=self.check.failure_severity,
                    confidence_score=1.0,
                    actions=(
                        UseSuggestionAction(
                            content=f"Please fix the {self.check.name} check (it timed out after {self.check.timeout_seconds} seconds).\n\nYou can see the stdout and stderr in {self.output_location.to_run_folder()}/stdout and {self.output_location.to_run_folder()}/stderr respectively\n\nIn order to run the command again, simply run:\n{self.check.command}",
                        ),
                    ),
                    original_issues=(),
                )
                self._on_new_suggestions([suggestion], services)
                raise CheckTimeout()

            # if the reason we exited was that we were asked to stop, raise the appropriate error
            if self._stop_event.is_set():
                raise CheckStopped()

            # if the command failed, make the suggestion that the user fix the check :)
            if exit_code != 0:
                last_lines = _load_last_lines_of_output(self._environment, self.output_location, 30)
                command_output_str = "".join(last_lines)
                # FIXME: make this link actually work
                full_output_link = f"/task/{self.output_location.task_id}/check_runs/{self.output_location.user_message_id}/{self.output_location.check_name}/{self.output_location.run_id}/output"
                suggestion = Suggestion(
                    title=f"Fix {self.output_location.check_name}",
                    description=f"{self.output_location.check_name} failed with exit code {exit_code}.\n\nThe last 30 lines of output were:\n\n```{command_output_str}\n```\n\nView the full output [here]({full_output_link})",
                    severity_score=self.check.failure_severity,
                    confidence_score=1.0,
                    actions=(
                        UseSuggestionAction(
                            # FIXME: make imbue_cli able to more easily re-run these commands exactly,
                            #  and change this description to be about running via imbue_cli
                            #  This is important because the data in this folder should be considered immutable
                            #  but we still want to be able to run in a way that has access to the correct env vars and secrets
                            #  (which should be a bit easier to get right via imbue_cli)
                            content=f"Please fix the {self.check.name} check (it exited with exit code={exit_code}).\n\nYou can see the stdout and stderr in {self.output_location.to_run_folder()}/stdout and {self.output_location.to_run_folder()}/stderr respectively\n\nIn order to run the command again, simply run:\n{self.check.command}",
                        ),
                    ),
                    original_issues=(),
                )
                self._on_new_suggestions([suggestion], services)

            # all done, hurray!
            finished_reason = CheckFinishedReason.FINISHED

        except CheckStopped:
            finished_reason = self._stop_reason
        except CheckTimeout:
            finished_reason = CheckFinishedReason.TIMEOUT
        # TODO: more specific EnvironmentFailure's may be better as suggestions (ex: to create a given folder, change permissions, etc)
        # handle cases where the environment has died, at least without throwing tons of errors, since it can happen
        except EnvironmentFailure as e:
            error_suggestion = Suggestion(
                title=f"Rerun {self.output_location.check_name} (container failure)",
                description=f"{self.output_location.check_name} seems to have failed because of a container failure: {e}\n\nYou could restart the check to see if it succeeds.",
                # TODO: I suppose this ought to be configurable as well
                severity_score=0.5,
                confidence_score=1.0,
                # TODO: I *suppose* you could have a "re-run" action here, sure...
                actions=(),
                original_issues=(),
            )
            # because we won't be able to write to the environment anyway...
            finished_reason = None
            # note that we do NOT re-raise this -- we have to assume that the environment is exiting
            logger.debug("Check process for {} exiting because of environment failure: {}", self.check.name, e)
        except BaseException as e:
            is_in_unknown_state = True
            error_suggestion = Suggestion(
                title=f"Report error to Imbue: failed to run {self.output_location.check_name} for unexpected reason",
                description=f"{self.output_location.check_name} failed because {e}:\n{traceback.format_exc()}\n\nYou should report this on Discord!",
                severity_score=1.0,
                confidence_score=1.0,
                actions=(VisitLinkSuggestionAction(link_text="Report", url=AnyUrl(DISCORD_URL)),),
                original_issues=(),
            )
            finished_reason = CheckFinishedReason.SCULPTOR_CRASHED
            raise
        # if we're done with the agent, try to indicate that. Of course there's no guarantee that this will work,
        # but we only set the finished reason if we think we can still write to the Environment
        finally:
            try:
                if self.check.is_forked and self._environment is not None:
                    self._environment.close()
            except EnvironmentFailure as e:
                logger.info("Failure while stopping check container: {}", e)
            except Exception as e:
                log_exception(e, "Failed to stop environment for unexpected reason")

            if finished_reason is not None:
                finished_reason_file = f"{self.output_location.to_run_folder()}/finished_reason"
                try:
                    # if error_suggestion is not None, record a suggestion (ex: to help the user see what failed in the environment)
                    if error_suggestion is not None:
                        self._on_new_suggestions([error_suggestion], services, is_environment_failure_ignored=True)

                    # save the finished reason to the run folder
                    self._environment.write_file(finished_reason_file, finished_reason + "\n", mode="w")
                except EnvironmentFailure as e:
                    # if this fails, not really that much the user can do about it.  I guess the status is "environment failed"
                    logger.debug(f"Failed to write finished reason ({finished_reason}) to {finished_reason_file}: {e}")

            try:
                # send the message
                self._send_message(
                    CheckFinishedRunnerMessage(
                        user_message_id=self.output_location.user_message_id,
                        check=self.check,
                        run_id=self.output_location.run_id,
                        exit_code=exit_code,
                        finished_reason=finished_reason
                        if finished_reason is not None
                        else CheckFinishedReason.ENVIRONMENT_CRASHED,
                        archival_reason="",
                    ),
                    services,
                )
            except BaseException as e:
                # if we're already known to be in a weird state, whatever, we can also log here but it doesn't matter
                # this is an acceptable use -- if we're in an unknown state, we already logged the real cause
                if is_in_unknown_state:
                    logger.exception(e)
                # otherwise raise so that this can be reported
                else:
                    raise

    def _save_check_json_file(self) -> None:
        # write the command out to the folder (will create the folder if it doesn't exist)
        # note that this is *mostly* for debugging, since the *current* value of the check will be in the parent folder
        # the one place that this does matter is for figuring out if we ran this particular check before when restoring
        run_output_folder = self.output_location.to_run_folder()
        check_data = model_dump_json(self.check)
        self._environment.write_file(f"{run_output_folder}/{CHECK_STATE_FILE_NAME}", check_data + "\n", mode="w")

    def stop(self, reason: CheckFinishedReason) -> int | None:
        self._stop_reason = reason
        self._stop_event.set()
        if self._process is None:
            return None

        # stop the process
        exit_code = self._stop_process()

        # make sure we've joined the thread as well
        if self._thread is not None:
            self._thread.join()

        return exit_code

    def abandon(self) -> None:
        self._stop_reason = CheckFinishedReason.TASK_EXIT
        self._stop_event.set()

    # wait until the check is done
    def join(self, timeout: float | None = None) -> None:
        assert self._thread is not None, "CheckProcess has not been started"
        self._thread.join(timeout)
        if self._thread.is_alive():
            raise TimeoutError("CheckProcess did not finish in time")

    def _stop_process(self) -> int:
        exit_code = self._process.poll()
        if exit_code is None:
            self._process.terminate()
        # always wait to make sure that the process exits
        exit_code = self._process.wait()

        # write the exit code to the correct location
        exit_code_file = f"{self.output_location.to_run_folder()}/exit_code"
        self._environment.write_file(exit_code_file, str(exit_code) + "\n", mode="w")

        return exit_code

    def _on_new_suggestions(
        self,
        suggestions: Sequence[Suggestion],
        services: ServiceCollectionForTask,
        is_environment_failure_ignored: bool = False,
    ) -> None:
        if len(suggestions) > 0:
            # save them to a file
            try:
                self._save_suggestions(suggestions)
            except EnvironmentFailure:
                if is_environment_failure_ignored:
                    pass
                else:
                    raise
            # if we got suggestions, send them to the user
            self._send_message(
                NewSuggestionRunnerMessage(
                    suggestions=tuple(suggestions),
                    run_id=self.output_location.run_id,
                    check_name=self.output_location.check_name,
                    user_message_id=self.output_location.user_message_id,
                ),
                services,
            )

    def _send_message(self, message: Message, services: ServiceCollectionForTask) -> None:
        with services.data_model_service.open_task_transaction() as transaction:
            services.task_service.create_message(message, self.output_location.task_id, transaction)

    def _save_suggestions(self, suggestions: Sequence[Suggestion]) -> None:
        if not suggestions:
            return
        suggestions_file = f"{self.output_location.to_run_folder()}/suggestions"
        content = "".join([(model_dump_json(x) + "\n") for x in suggestions])
        self._environment.write_file(suggestions_file, content + "\n", mode="a")


def _load_finished_reason_from_volume(
    check_process: CheckProcess, environment: Environment, default_reason: CheckFinishedReason
) -> CheckFinishedReason:
    finished_reason_file = f"{check_process.output_location.to_run_folder()}/finished_reason"
    try:
        finished_reason_data = environment.read_file(finished_reason_file, mode="r")
        return CheckFinishedReason(finished_reason_data.strip())
    except ValueError as e:
        # it shouldn't be possible for this to happen, so, curious if it ever does
        log_exception(
            e,
            f"Failed to load finished reason from {finished_reason_file}: {e}",
            priority=ExceptionPriority.LOW_PRIORITY,
        )
        return CheckFinishedReason.SCULPTOR_CRASHED
    except FileNotFoundError:
        return default_reason


def _load_exit_code_from_volume(check_process: CheckProcess, environment: Environment) -> int | None:
    exit_code_file = f"{check_process.output_location.to_run_folder()}/exit_code"
    try:
        exit_code_data = environment.read_file(exit_code_file, mode="r")
        return int(exit_code_data.strip())
    except (FileNotFoundError, ValueError):
        return None


def _load_last_lines_of_output(
    environment: Environment, output_location: CheckRunOutputLocation, max_lines: int
) -> list[str]:
    combined_logs_file = f"{output_location.to_run_folder()}/combined_logs"
    try:
        combined_logs_data = environment.read_file(combined_logs_file, mode="r")
        all_lines = combined_logs_data.splitlines(keepends=True)
        return all_lines[-max_lines:]
    except FileNotFoundError:
        return []


def _load_suggestions_from_volume(check_process: CheckProcess, environment: Environment) -> list[Suggestion]:
    suggestions_file = f"{check_process.output_location.to_run_folder()}/suggestions"
    try:
        suggestions_data = environment.read_file(suggestions_file, mode="r")
    except FileNotFoundError:
        return []
    suggestions: list[Suggestion] = []
    for line in suggestions_data.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            suggestion = model_load_json(Suggestion, line)
        except ValidationError:
            continue
        suggestions.append(suggestion)
    return suggestions


def _get_configuration_suggestions(check: Check) -> list[Suggestion]:
    """
    If there were errors while parsing the check, returns a list of suggestions about how to fix them.

    If there were no errors, returns an empty list.
    """
    if not check.config_error:
        return []

    return [
        Suggestion(
            title=f"Fix {check.name} configuration",
            description=check.config_error,
            severity_score=1.0,
            confidence_score=1.0,
            actions=(
                UseSuggestionAction(
                    content=f"Please fix the configuration of the {check.name} check in {CHECK_CONFIG_PATH}.  The parsing error was:\n{check.config_error}",
                ),
            ),
            original_issues=(),
        )
    ]
