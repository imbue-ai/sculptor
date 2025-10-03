"""
Format: we assume that `checks.toml` is a well-formed toml file where each entry is the name of a check,
which is defined either as:
1. a bunch of attributes that correspond to the fields on the `Check` class.
2. a simple string that is the command to run (everything else uses the default values)
"""

import toml
from pydantic import AnyUrl
from pydantic import ValidationError
from toml import TomlDecodeError

from imbue_core.async_monkey_patches import log_exception
from imbue_core.constants import ExceptionPriority
from imbue_core.suggestions import Suggestion
from imbue_core.suggestions import UseSuggestionAction
from imbue_core.suggestions import VisitLinkSuggestionAction
from sculptor.interfaces.agents.v1.agent import Check
from sculptor.interfaces.agents.v1.agent import CheckSource
from sculptor.interfaces.agents.v1.agent import CheckTrigger
from sculptor.interfaces.agents.v1.agent import DEFAULT_CHECK_TIMEOUT_SECONDS
from sculptor.interfaces.environments.v1.base import Environment
from sculptor.tasks.handlers.run_agent.checks.constants import CHECK_CONFIG_PATH
from sculptor.tasks.handlers.run_agent.checks.constants import IMBUE_VERIFY_CHECK_NAME
from sculptor.tasks.handlers.run_agent.checks.constants import SCULPTOR_CHECKS_DOCS_URL
from sculptor.tasks.handlers.run_agent.checks.constants import SCULPTOR_SYSTEM_CHECK_NAME
from sculptor.tasks.handlers.run_agent.checks.errors import ConfigValidationError
from sculptor.tasks.handlers.run_agent.checks.errors import ExpectedCheckConfigParsingError


def load_checks_from_environment(
    environment: Environment, is_imbue_verify_check_enabled: bool = True
) -> tuple[dict[str, Check], tuple[Suggestion, ...]]:
    """
    load checks from their canonical location.

    note that we only support reading a versioned file in the repo -- no unversioned files, no files on the user machine
    otherwise it gets very difficult to know how to propagate changes to the other tasks

    if there are errors when loading an individual check, it will be included within the config_error field of the check
    """
    system_suggestions = []
    user_checks = {}
    try:
        checks_data = environment.read_file(str(environment.get_workspace_path() / CHECK_CONFIG_PATH))
        user_checks = load_checks(checks_data.strip())
    except FileNotFoundError:
        if not is_imbue_verify_check_enabled:
            system_suggestions.append(
                Suggestion(
                    title=f"Define your own custom checks",
                    description=f"You can define your own custom checks in {CHECK_CONFIG_PATH}\n\nLearn more here: {SCULPTOR_CHECKS_DOCS_URL}",
                    severity_score=0.0,
                    confidence_score=1.0,
                    actions=(VisitLinkSuggestionAction(link_text="Learn", url=AnyUrl(SCULPTOR_CHECKS_DOCS_URL)),),
                    original_issues=(),
                )
            )

        pass

    except Exception as e:
        if not isinstance(e, (ExpectedCheckConfigParsingError, TomlDecodeError)):
            log_exception(e, "Failed to parse checks.toml", priority=ExceptionPriority.LOW_PRIORITY)
        system_suggestions.append(
            Suggestion(
                title=f"Fix check configuration in {CHECK_CONFIG_PATH}",
                description=f"Failed to load checks from {CHECK_CONFIG_PATH} because {e}",
                severity_score=1.0,
                confidence_score=1.0,
                actions=(
                    UseSuggestionAction(
                        content=f"Please fix the check configuration in {CHECK_CONFIG_PATH}\n\nIt failed because:\n{e}"
                    ),
                ),
                original_issues=(),
            )
        )

    # TODO: this default configuration could be editable by the user (as part of global configuration)
    default_checks = {x.name: x for x in _get_default_checks(is_imbue_verify_check_enabled)}

    return {**default_checks, **user_checks}, tuple(system_suggestions)


def load_checks(file_contents: str) -> dict[str, Check]:
    if not file_contents:
        return {}

    checks: dict[str, Check] = {}

    # the data is for a toml file where keys either map directly to a string, or to a dictionary that defined the check
    data = toml.loads(file_contents)
    for check_name, check_value in data.items():
        try:
            # this is a simple check that just runs the command
            if isinstance(check_value, str):
                checks[check_name] = Check(name=check_name, command=check_value)
            # this is a more complex check that has additional parameters
            elif isinstance(check_value, dict):
                # parse the more complex types (enums) separately
                if "source" in check_value:
                    if check_value.get("source", "").upper() != CheckSource.USER.value:
                        raise ConfigValidationError(
                            f"Invalid check source ({check_value.get('source')}), must be ommitted or set to USER"
                        )
                trigger = CheckTrigger.AGENT_MESSAGE
                if "trigger" in check_value:
                    try:
                        trigger = CheckTrigger(check_value["trigger"])
                    except ValueError:
                        raise ConfigValidationError(f"Invalid check trigger ({check_value['trigger']})")
                if "name" in check_value and check_value["name"] != check_name:
                    raise ConfigValidationError(
                        f"Check name in config ({check_value['name']}) does not match key '{check_name}' -- either omit or make them match"
                    )
                # then let pydantic handle the rest of the validation
                checks[check_name] = Check(
                    name=check_name,
                    command=check_value.get("command", ""),
                    timeout_seconds=check_value.get("timeout", DEFAULT_CHECK_TIMEOUT_SECONDS),
                    description=check_value.get("description", ""),
                    is_forked=check_value.get("is_forked", False),
                    is_local_concurrency_allowed=check_value.get("is_local_concurrency_allowed", False),
                    trigger=trigger,
                    is_enabled=check_value.get("is_enabled", True),
                    is_visible=check_value.get("is_visible", True),
                )
            else:
                raise ExpectedCheckConfigParsingError(
                    f"Invalid check data (is a {type(check_value)}, not a dict or str) for key '{check_name}': {check_value}"
                )
        except (ValidationError, ConfigValidationError) as e:
            checks[check_name] = Check(name=check_name, command=check_value.get("command", ""), config_error=str(e))

    return checks


def _get_default_checks(is_imbue_verify_check_enabled: bool = True) -> list[Check]:
    """
    Returns a list of default checks that are always available.
    These checks are not user-editable.
    """
    checks = [
        Check(
            name=SCULPTOR_SYSTEM_CHECK_NAME,
            command=None,
            description="Checks basic system configuration for Sculptor itself.",
            timeout_seconds=DEFAULT_CHECK_TIMEOUT_SECONDS,
            trigger=CheckTrigger.FILE_CHANGE,
            is_enabled=True,
            is_visible=True,
            source=CheckSource.SYSTEM,
        ),
    ]

    if is_imbue_verify_check_enabled:
        # TODO (andrew.laack): We don't want this running during tests. Currently, all tests that have checks enabled should be skipped, but when those are enabled, we should ensure imbue_cli has caching set up.
        checks.append(
            Check(
                name=IMBUE_VERIFY_CHECK_NAME,
                command="imbue-cli.sh check --project-path /code --use-internal-config --output-format suggestions",
                description="Runs imbue_verify with goal from last commit message via MCP",
                timeout_seconds=DEFAULT_CHECK_TIMEOUT_SECONDS,
                trigger=CheckTrigger.AGENT_MESSAGE,
                is_enabled=True,
                is_visible=True,
                source=CheckSource.USER,
                is_local_concurrency_allowed=True,
            )
        )

    return checks
