import json
import time
from pathlib import Path

import pytest

from imbue_core.agents.data_types.ids import AgentMessageID
from imbue_core.itertools import only
from imbue_core.pydantic_serialization import model_dump_json
from imbue_core.pydantic_serialization import model_load_json
from imbue_core.sculptor.state.messages import Message
from imbue_core.suggestions import Suggestion
from imbue_core.suggestions import UseSuggestionAction
from imbue_core.test_utils import wait_until
from sculptor.database.models import Task
from sculptor.database.models import TaskID
from sculptor.interfaces.agents.v1.agent import Check
from sculptor.interfaces.agents.v1.agent import CheckFinishedReason
from sculptor.interfaces.agents.v1.agent import CheckFinishedRunnerMessage
from sculptor.interfaces.agents.v1.agent import CheckLaunchedRunnerMessage
from sculptor.interfaces.agents.v1.agent import CheckSource
from sculptor.interfaces.agents.v1.agent import NewSuggestionRunnerMessage
from sculptor.interfaces.agents.v1.agent import RunID
from sculptor.services.environment_service.environments.local_environment import LocalEnvironment
from sculptor.services.task_service.data_types import ServiceCollectionForTask
from sculptor.tasks.handlers.run_agent.checks.check_process import CheckProcess
from sculptor.tasks.handlers.run_agent.checks.check_process import _load_suggestions_from_volume
from sculptor.tasks.handlers.run_agent.checks.constants import CHECK_STATE_FILE_NAME
from sculptor.tasks.handlers.run_agent.checks.constants import SCULPTOR_SYSTEM_CHECK_NAME
from sculptor.tasks.handlers.run_agent.checks.output_location import CheckRunOutputLocation
from sculptor.tasks.handlers.run_agent.conftest import get_all_messages_for_task
from sculptor.utils.secret import Secret


@pytest.fixture
def check_run_output_location(tmp_path: Path, local_task: Task) -> CheckRunOutputLocation:
    return CheckRunOutputLocation(
        root_data_path="/shared_volume",
        task_id=local_task.object_id,
        user_message_id=AgentMessageID(),
        run_id=RunID(),
        check_name="test_check",
    )


def get_messages_after_check_finished(task_id: TaskID, services: ServiceCollectionForTask) -> list[Message]:
    wait_until(
        lambda: any(
            x for x in get_all_messages_for_task(task_id, services) if isinstance(x, CheckFinishedRunnerMessage)
        )
    )
    return get_all_messages_for_task(task_id, services)


def get_messages_after_check_suggestion(task_id: TaskID, services: ServiceCollectionForTask) -> list[Message]:
    wait_until(
        lambda: any(
            x for x in get_all_messages_for_task(task_id, services) if isinstance(x, NewSuggestionRunnerMessage)
        )
    )
    return get_all_messages_for_task(task_id, services)


def test_check_run_output_location(check_run_output_location: CheckRunOutputLocation) -> None:
    location = check_run_output_location

    expected_path = (
        f"{location.root_data_path}/{location.task_id}/checks/{location.user_message_id}/test_check/{location.run_id}"
    )
    assert location.to_run_folder() == expected_path
    assert CheckRunOutputLocation.build_from_folder(expected_path) == location


def test_run_check(
    check_run_output_location: CheckRunOutputLocation,
    environment: LocalEnvironment,
    services: ServiceCollectionForTask,
    local_task: Task,
) -> None:
    """Test basic initialization of CheckProcess with minimal required fields."""
    check = Check(name=check_run_output_location.check_name, command="echo 'Hello, World!'")
    check_process = CheckProcess(check=check, output_location=check_run_output_location, snapshot=None)

    assert check_process.check == check
    assert check_process.output_location == check_run_output_location
    assert check_process.snapshot is None

    check_process._environment = environment
    check_process.run({}, local_task.project_id, services)

    # verify that the correct messages were created
    all_messages = get_messages_after_check_finished(check_run_output_location.task_id, services)
    check_launched_message, check_finished_message = all_messages
    assert isinstance(check_launched_message, CheckLaunchedRunnerMessage)
    assert check_launched_message.check == check
    assert check_launched_message.run_id == check_run_output_location.run_id
    assert check_launched_message.user_message_id == check_run_output_location.user_message_id
    assert isinstance(check_finished_message, CheckFinishedRunnerMessage)
    assert check_finished_message.check.name == check.name
    assert check_finished_message.run_id == check_run_output_location.run_id
    assert check_finished_message.user_message_id == check_run_output_location.user_message_id
    assert check_finished_message.exit_code == 0
    assert check_finished_message.finished_reason == CheckFinishedReason.FINISHED
    assert check_finished_message.archival_reason == ""


def test_check_can_be_stopped_immediately(
    check_run_output_location: CheckRunOutputLocation,
    environment: LocalEnvironment,
    services: ServiceCollectionForTask,
    local_task: Task,
) -> None:
    # Use a sleep command that will take long enough for us to stop it
    check = Check(name=check_run_output_location.check_name, command="sleep 10")
    check_process = CheckProcess(check=check, output_location=check_run_output_location, snapshot=None)
    check_process.start(environment, {}, services, local_task.project_id)

    # Wait a brief moment to ensure the check has started
    time.sleep(1.0)

    # Stop the check
    exit_code = check_process.stop(CheckFinishedReason.STOPPED)
    check_process.join(timeout=5)  # Wait for thread to complete, with timeout

    # Verify that the check was stopped properly
    all_messages = get_messages_after_check_finished(check_run_output_location.task_id, services)
    check_launched_message, check_finished_message = all_messages

    # Should have at least the launch message and finished message
    assert len(all_messages) >= 2

    # Verify the launch message
    assert isinstance(check_launched_message, CheckLaunchedRunnerMessage)
    assert check_launched_message.check == check
    assert check_launched_message.run_id == check_run_output_location.run_id

    # Verify the finished message indicates it was stopped
    assert isinstance(check_finished_message, CheckFinishedRunnerMessage)
    assert check_finished_message.check.name == check.name
    assert check_finished_message.run_id == check_run_output_location.run_id
    assert check_finished_message.finished_reason == CheckFinishedReason.STOPPED
    assert check_finished_message.exit_code == exit_code
    # 0 in case you get really unlucky and the sleep finishes before we stop it
    assert exit_code in [-15, 0]


def test_check_produces_suggestions_via_stdout(
    check_run_output_location: CheckRunOutputLocation,
    environment: LocalEnvironment,
    services: ServiceCollectionForTask,
    local_task: Task,
) -> None:
    # Create a suggestion object
    suggestion = Suggestion(
        title="Test Suggestion",
        description="This is a test suggestion from the check",
        severity_score=0.5,
        confidence_score=0.8,
        actions=(UseSuggestionAction(content="Make it good"),),
        original_issues=(),
    )

    # Create a command that outputs the suggestion protocol and a suggestion
    suggestion_json = model_dump_json(suggestion)
    command = f'''echo "IMBUE_SUGGESTIONS_PROTOCOL_V0.0.1" && echo '{suggestion_json}' && echo "Test complete"'''

    check = Check(name=check_run_output_location.check_name, command=command)
    check_process = CheckProcess(check=check, output_location=check_run_output_location, snapshot=None)
    check_process._environment = environment

    # Run the check
    check_process.run({}, local_task.project_id, services)

    # Verify the messages
    all_messages = get_messages_after_check_finished(check_run_output_location.task_id, services)
    check_finished_message = all_messages[-1]

    # Find the suggestion message
    suggestion_messages = [msg for msg in all_messages if isinstance(msg, NewSuggestionRunnerMessage)]
    assert len(suggestion_messages) == 1

    suggestion_message = suggestion_messages[0]
    assert len(suggestion_message.suggestions) == 1

    received_suggestion = suggestion_message.suggestions[0]
    assert received_suggestion.title == "Test Suggestion"
    assert received_suggestion.description == "This is a test suggestion from the check"
    assert received_suggestion.severity_score == 0.5
    assert received_suggestion.confidence_score == 0.8

    # Verify the check completed successfully
    assert check_finished_message.exit_code == 0
    assert check_finished_message.finished_reason == CheckFinishedReason.FINISHED


def test_config_error_suggestions(
    check_run_output_location: CheckRunOutputLocation,
    environment: LocalEnvironment,
    services: ServiceCollectionForTask,
    local_task: Task,
) -> None:
    """Test that checks with config errors send appropriate suggestions."""
    config_error = "Invalid timeout value: must be a positive number"

    check = Check(
        name=check_run_output_location.check_name,
        command="echo 'This should still run'",
        config_error=config_error,
    )
    check_process = CheckProcess(check=check, output_location=check_run_output_location, snapshot=None)
    check_process._environment = environment

    check_process.run({}, local_task.project_id, services)

    # Verify messages
    all_messages = get_messages_after_check_suggestion(check_run_output_location.task_id, services)

    # Find suggestion messages
    suggestion_messages = [msg for msg in all_messages if isinstance(msg, NewSuggestionRunnerMessage)]
    assert len(suggestion_messages) >= 1

    # Find the config error suggestion
    config_suggestions_found = False
    for msg in suggestion_messages:
        for suggestion in msg.suggestions:
            if "Fix test_check configuration" in suggestion.title:
                config_suggestions_found = True
                assert config_error in suggestion.description
                assert suggestion.severity_score == 1.0
                assert suggestion.confidence_score == 1.0
                break

    assert config_suggestions_found, "Config error suggestion not found"


def test_system_check_suggestions(
    check_run_output_location: CheckRunOutputLocation,
    environment: LocalEnvironment,
    services: ServiceCollectionForTask,
    local_task: Task,
) -> None:
    """Test that system checks send their suggestions properly."""

    # Create a system check with explicit suggestions
    check = Check(
        name=SCULPTOR_SYSTEM_CHECK_NAME,
        command=None,
        description="System check for testing",
        source=CheckSource.SYSTEM,
    )

    # Update output location to use system check name
    output_location = check_run_output_location.model_copy(update={"check_name": SCULPTOR_SYSTEM_CHECK_NAME})

    check_process = CheckProcess(check=check, output_location=output_location, snapshot=None)
    check_process._environment = environment

    check_process.run({}, local_task.project_id, services)

    # Verify messages
    all_messages = get_messages_after_check_suggestion(output_location.task_id, services)

    # Find suggestion messages
    suggestion_messages = [msg for msg in all_messages if isinstance(msg, NewSuggestionRunnerMessage)]
    assert len(suggestion_messages) == 1

    # Verify system suggestions were sent
    received_suggestions = suggestion_messages[0].suggestions
    assert len(received_suggestions) == 1
    assert received_suggestions[0].title == "Define your own custom checks"


def test_command_with_non_zero_exit_code(
    check_run_output_location: CheckRunOutputLocation,
    environment: LocalEnvironment,
    services: ServiceCollectionForTask,
    local_task: Task,
) -> None:
    """Test that commands with non-zero exit codes create failure suggestions."""
    # Use exit code 42 for testing
    check = Check(name=check_run_output_location.check_name, command="exit 42")
    check_process = CheckProcess(check=check, output_location=check_run_output_location, snapshot=None)
    check_process._environment = environment

    check_process.run({}, local_task.project_id, services)

    # Verify messages
    all_messages = get_messages_after_check_finished(check_run_output_location.task_id, services)

    # Find suggestion messages
    suggestion_messages = [msg for msg in all_messages if isinstance(msg, NewSuggestionRunnerMessage)]
    assert len(suggestion_messages) >= 1

    # Find the failure suggestion
    failure_suggestion_found = False
    for msg in suggestion_messages:
        for suggestion in msg.suggestions:
            if f"Fix {check_run_output_location.check_name}" in suggestion.title:
                failure_suggestion_found = True
                assert "exit code 42" in suggestion.description
                # Default failure_severity is used
                assert suggestion.confidence_score == 1.0
                # Should have a UseSuggestionAction with instructions
                assert len(suggestion.actions) == 1
                assert isinstance(suggestion.actions[0], UseSuggestionAction)
                assert "exit code=42" in suggestion.actions[0].content
                break

    assert failure_suggestion_found, "Failure suggestion not found"

    # Check finished message has correct exit code
    check_finished_message = all_messages[-1]
    assert isinstance(check_finished_message, CheckFinishedRunnerMessage)
    assert check_finished_message.exit_code == 42
    assert check_finished_message.finished_reason == CheckFinishedReason.FINISHED


def test_timeout_handling(
    check_run_output_location: CheckRunOutputLocation,
    environment: LocalEnvironment,
    services: ServiceCollectionForTask,
    local_task: Task,
) -> None:
    """Test that checks properly handle timeout scenarios."""
    # Create a check with a very short timeout
    check = Check(
        name=check_run_output_location.check_name,
        command="sleep 30",  # Long-running command
        timeout_seconds=1,  # Very short timeout
    )
    check_process = CheckProcess(check=check, output_location=check_run_output_location, snapshot=None)
    check_process._environment = environment

    check_process.run({}, local_task.project_id, services)

    # Verify messages
    all_messages = get_messages_after_check_finished(check_run_output_location.task_id, services)

    # Should have launch and finished messages, along with a suggestion about timeout
    assert len(all_messages) == 3, f"Got {len(all_messages)} messages instead of 3: {all_messages}"

    suggestion = only([only(msg.suggestions) for msg in all_messages if isinstance(msg, NewSuggestionRunnerMessage)])
    assert suggestion.title == f"Fix {check_run_output_location.check_name} timeout"

    # Check finished message indicates timeout
    check_finished_message = all_messages[-1]
    assert isinstance(check_finished_message, CheckFinishedRunnerMessage)
    assert check_finished_message.finished_reason == CheckFinishedReason.TIMEOUT


def test_file_outputs_are_created_correctly(
    check_run_output_location: CheckRunOutputLocation,
    environment: LocalEnvironment,
    services: ServiceCollectionForTask,
    local_task: Task,
) -> None:
    """Test that all expected output files are created with correct content."""
    # Create suggestions to test suggestion file append
    suggestion1 = Suggestion(
        title="First Suggestion",
        description="First test suggestion",
        severity_score=0.5,
        confidence_score=0.8,
        actions=(),
        original_issues=(),
    )
    suggestion2 = Suggestion(
        title="Second Suggestion",
        description="Second test suggestion",
        severity_score=0.7,
        confidence_score=0.9,
        actions=(),
        original_issues=(),
    )

    # Create command that outputs to stdout/stderr and produces suggestions
    suggestion1_json = model_dump_json(suggestion1)
    suggestion2_json = model_dump_json(suggestion2)
    command = f"""echo "stdout line 1" && \
echo "stderr line 1" >&2 && \
echo "IMBUE_SUGGESTIONS_PROTOCOL_V0.0.1" && \
echo '{suggestion1_json}' && \
echo "stdout line 2" && \
echo "stderr line 2" >&2 && \
echo '{suggestion2_json}' && \
exit 0"""

    check = Check(name=check_run_output_location.check_name, command=command)
    check_process = CheckProcess(check=check, output_location=check_run_output_location, snapshot=None)
    check_process._environment = environment

    check_process.run({}, local_task.project_id, services)

    run_folder = check_run_output_location.to_run_folder()

    # Test stdout file
    stdout_content = environment.read_file(f"{run_folder}/stdout")
    assert "stdout line 1" in stdout_content
    assert "stdout line 2" in stdout_content
    assert "IMBUE_SUGGESTIONS_PROTOCOL_V0.0.1" in stdout_content
    assert suggestion1_json in stdout_content
    assert suggestion2_json in stdout_content

    # Test stderr file
    stderr_content = environment.read_file(f"{run_folder}/stderr")
    assert "stderr line 1" in stderr_content
    assert "stderr line 2" in stderr_content

    # Test combined_logs file
    combined_content = environment.read_file(f"{run_folder}/combined_logs")
    assert "stdout line 1" in combined_content
    assert "stdout line 2" in combined_content
    assert "stderr line 1" in combined_content
    assert "stderr line 2" in combined_content

    # Test exit_code file
    exit_code_content = environment.read_file(f"{run_folder}/exit_code")
    assert exit_code_content.strip() == "0"

    # Test finished_reason file
    finished_reason_content = environment.read_file(f"{run_folder}/finished_reason")
    assert finished_reason_content.strip() == CheckFinishedReason.FINISHED.value

    # Test command file
    command_content = environment.read_file(f"{run_folder}/command")
    assert command_content.strip() == command

    # Test suggestions file (should have both suggestions appended)
    suggestions_content = environment.read_file(f"{run_folder}/suggestions")
    suggestions_lines = [line.strip() for line in suggestions_content.strip().split("\n") if line.strip()]
    assert len(suggestions_lines) == 2

    # Parse and verify suggestions
    parsed_suggestion1 = model_load_json(Suggestion, suggestions_lines[0])
    parsed_suggestion2 = model_load_json(Suggestion, suggestions_lines[1])
    assert parsed_suggestion1.title == "First Suggestion"
    assert parsed_suggestion2.title == "Second Suggestion"

    # Test check.json state file
    check_state_content = environment.read_file(f"{run_folder}/{CHECK_STATE_FILE_NAME}")
    check_state = model_load_json(Check, check_state_content)
    assert check_state.name == check.name
    assert check_state.command == check.command


def test_environment_variables_and_secrets(
    check_run_output_location: CheckRunOutputLocation,
    environment: LocalEnvironment,
    services: ServiceCollectionForTask,
    local_task: Task,
) -> None:
    """Test that standard environment variables and secrets are properly set."""
    # Command that echoes all the expected environment variables
    command = " && ".join(
        [
            'echo "RUN_OUTPUT_FOLDER=$RUN_OUTPUT_FOLDER"',
            'echo "RUN_ID=$RUN_ID"',
            'echo "CHECK_NAME=$CHECK_NAME"',
            'echo "USER_MESSAGE_ID=$USER_MESSAGE_ID"',
            'echo "TASK_ID=$TASK_ID"',
            'echo "AGENT_DATA=$AGENT_DATA"',
            'echo "MY_SECRET=$MY_SECRET"',
            'echo "MY_OTHER_SECRET=$MY_OTHER_SECRET"',
            'echo "RUN_ID_OVERRIDE=$RUN_ID_OVERRIDE"',
        ]
    )

    check = Check(name=check_run_output_location.check_name, command=command)
    check_process = CheckProcess(check=check, output_location=check_run_output_location, snapshot=None)
    check_process._environment = environment

    # Define secrets to test propagation and override
    secrets = {
        "MY_SECRET": Secret("secret_value_123"),
        "MY_OTHER_SECRET": Secret("another_secret"),
        # Try to override a standard variable (should be overridden by standard)
        "RUN_ID": Secret("fake_run_id"),
    }

    check_process.run(secrets, local_task.project_id, services)

    run_folder = check_run_output_location.to_run_folder()
    stdout_content = environment.read_file(f"{run_folder}/stdout")

    # Verify standard environment variables
    first_line = stdout_content.splitlines()[0]
    assert "RUN_OUTPUT_FOLDER" in first_line and f"{run_folder}/output" in first_line
    assert f"CHECK_NAME={check_run_output_location.check_name}" in stdout_content
    assert f"USER_MESSAGE_ID={check_run_output_location.user_message_id}" in stdout_content
    assert f"TASK_ID={check_run_output_location.task_id}" in stdout_content
    assert all(
        check_run_output_location.root_data_path in line
        for line in stdout_content.splitlines()
        if "AGENT_DATA" in line
    )

    # Verify secrets are propagated
    assert "MY_SECRET=secret_value_123" in stdout_content
    assert "MY_OTHER_SECRET=another_secret" in stdout_content
    # including dumb overrides
    assert "RUN_ID=fake_run_id" in stdout_content


def test_gather_messages_from_previous_run(
    check_run_output_location: CheckRunOutputLocation,
    environment: LocalEnvironment,
    services: ServiceCollectionForTask,
) -> None:
    """Test loading messages from a previous run that didn't complete."""

    # Set up a check
    check = Check(name=check_run_output_location.check_name, command="echo 'test'")
    check_process = CheckProcess(check=check, output_location=check_run_output_location, snapshot=None)

    # Simulate a previous run by creating the necessary files
    run_folder = check_run_output_location.to_run_folder()
    environment.write_file(f"{run_folder}/finished_reason", CheckFinishedReason.SCULPTOR_CRASHED.value, mode="w")
    environment.write_file(f"{run_folder}/exit_code", "137", mode="w")

    # Create some suggestions from the previous run
    suggestion1 = Suggestion(
        title="Previous Run Suggestion 1",
        description="Suggestion from incomplete run",
        severity_score=0.6,
        confidence_score=0.8,
        actions=(),
        original_issues=(),
    )
    suggestion2 = Suggestion(
        title="Previous Run Suggestion 2",
        description="Another suggestion from incomplete run",
        severity_score=0.4,
        confidence_score=0.7,
        actions=(),
        original_issues=(),
    )

    # Write suggestions file
    suggestions_content = model_dump_json(suggestion1) + "\n" + model_dump_json(suggestion2) + "\n"
    environment.write_file(f"{run_folder}/suggestions", suggestions_content, mode="w")

    # Gather messages from the previous run
    archival_reason = "Sculptor was restarted"
    messages = check_process.gather_messages_from_previous_run(
        archival_reason, environment, CheckFinishedReason.SCULPTOR_CRASHED
    )

    # Should have finished message and suggestions message
    assert len(messages) == 2

    # Check finished message
    finished_message = messages[0]
    assert isinstance(finished_message, CheckFinishedRunnerMessage)
    assert finished_message.check.name == check_run_output_location.check_name
    assert finished_message.run_id == check_run_output_location.run_id
    assert finished_message.exit_code == 137
    assert finished_message.finished_reason == CheckFinishedReason.SCULPTOR_CRASHED
    assert finished_message.archival_reason == archival_reason

    # Check suggestions message
    suggestions_message = messages[1]
    assert isinstance(suggestions_message, NewSuggestionRunnerMessage)
    assert len(suggestions_message.suggestions) == 2
    assert suggestions_message.suggestions[0].title == "Previous Run Suggestion 1"
    assert suggestions_message.suggestions[1].title == "Previous Run Suggestion 2"
    assert suggestions_message.run_id == check_run_output_location.run_id


def test_loading_suggestions_from_corrupted_previous_run(
    check_run_output_location: CheckRunOutputLocation,
    environment: LocalEnvironment,
    services: ServiceCollectionForTask,
) -> None:
    """Test resuming a check that had suggestions from a previous partial run."""

    # Create suggestions to simulate a previous run
    suggestion1 = Suggestion(
        title="Loaded Suggestion 1",
        description="First loaded suggestion",
        severity_score=0.3,
        confidence_score=0.6,
        actions=(UseSuggestionAction(content="Fix this"),),
        original_issues=(),
    )
    suggestion2 = Suggestion(
        title="Loaded Suggestion 2",
        description="Second loaded suggestion",
        severity_score=0.8,
        confidence_score=0.9,
        actions=(),
        original_issues=(),
    )

    # Create a check process
    check = Check(name=check_run_output_location.check_name, command="echo 'resumed'")
    check_process = CheckProcess(check=check, output_location=check_run_output_location, snapshot=None)

    # Write suggestions to the expected location
    run_folder = check_run_output_location.to_run_folder()
    # simulate corruption by removing an attribute
    suggestion2_json_dict = suggestion2.model_dump(mode="json")
    del suggestion2_json_dict["severity_score"]
    suggestions_content = model_dump_json(suggestion1) + "\n" + json.dumps(suggestion2_json_dict) + "\n"
    environment.write_file(f"{run_folder}/suggestions", suggestions_content, mode="w")

    # Load suggestions
    loaded_suggestions = _load_suggestions_from_volume(check_process, environment)

    assert len(loaded_suggestions) == 1
    assert loaded_suggestions[0].title == "Loaded Suggestion 1"
    assert loaded_suggestions[0].description == "First loaded suggestion"
    assert loaded_suggestions[0].severity_score == 0.3
    assert loaded_suggestions[0].confidence_score == 0.6
    assert len(loaded_suggestions[0].actions) == 1
    assert isinstance(loaded_suggestions[0].actions[0], UseSuggestionAction)
