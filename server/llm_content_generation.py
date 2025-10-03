import re
from typing import Sequence

from imbue_core.pydantic_utils import model_update
from imbue_core.sculptor.telemetry import PosthogEventPayload
from imbue_core.sculptor.telemetry import with_consent
from imbue_core.sculptor.telemetry_constants import ConsentLevel
from sculptor.server.llm_utils import LLMError
from sculptor.server.llm_utils import get_structured_llm_response
from sculptor.services.anthropic_credentials_service.api import AnthropicCredentials


class TaskTitleAndBranch(PosthogEventPayload):
    """Structured output for LLM-generated task title and branch name."""

    title: str = with_consent(
        ConsentLevel.LLM_LOGS,
        description="A concise, descriptive title (5-8 words) that captures the essence of the task",
    )
    branch_name: str = with_consent(
        ConsentLevel.LLM_LOGS,
        description="A short, kebab-case branch name suitable for git (e.g., 'add-user-auth', 'fix-login-bug')",
    )


# TODO: don't hardcode "sculptor/" prefix, allow it to be configured
def generate_title_and_branch_from_initial_prompt(
    initial_prompt: str,
    existing_branches: Sequence[str],
    anthropic_credentials: AnthropicCredentials,
    max_retries: int = 3,
) -> TaskTitleAndBranch:
    """
    Generate a concise title and branch name for a task based on the user's prompt.

    Args:
        initial_prompt: The user's task description
        existing_branches: List of existing branch names to avoid duplicates
        max_retries: Maximum number of retries if generated branch name already exists

    Returns:
        TaskTitleAndBranch with unique branch name
    """
    assert max_retries >= 1

    # Extract existing sculptor branches for comparison
    sculptor_branches = [b for b in existing_branches if b.startswith("sculptor/")]

    system_prompt = """You are a helpful assistant that creates concise, professional titles and branch names for development tasks.

Guidelines for titles:
- Keep titles between 5-8 words
- Be specific and descriptive
- Use action verbs when appropriate
- Focus on the main objective, not implementation details
- Examples: "Add user authentication system", "Fix memory leak in parser", "Refactor database connection logic"

Guidelines for branch names:
- Use kebab-case (lowercase with hyphens)
- Keep under 30 characters when possible
- Be descriptive but concise
- Use prefixes like 'add-', 'fix-', 'update-', 'remove-' when appropriate
- Examples: "add-user-auth", "fix-memory-leak", "refactor-db-connection"
- IMPORTANT: The branch name must be unique and not already exist
"""

    existing_branch_info = ""
    if sculptor_branches:
        branch_suffixes = [b[9:] for b in sculptor_branches]  # Remove "sculptor/" prefix
        existing_branch_info = f"\n\nEXISTING BRANCHES TO AVOID:\n" + "\n".join(
            f"- {suffix}" for suffix in branch_suffixes[:20]
        )

    enhanced_prompt = f"""
Based on this user request, generate a concise title and branch name:

"{initial_prompt}"

Create:
1. A title that's 5-8 words long, specific enough to understand the task at a glance
2. A branch name in kebab-case that's short and descriptive

Consider the type of task (feature, bugfix, refactor, etc.) and make the title and branch name reflect that appropriately.{existing_branch_info}

IMPORTANT: The branch name MUST be unique and not match any of the existing branches listed above.
"""

    for attempt in range(max_retries):
        result = get_structured_llm_response(
            prompt=enhanced_prompt,
            output_type=TaskTitleAndBranch,
            anthropic_credentials=anthropic_credentials,
            system_prompt=system_prompt,
            temperature=0.3 + (0.1 * attempt),  # Increase temperature on retries for more variation
            max_tokens=200,
        )

        result = model_update(result, {"branch_name": _clean_branch_name(result.branch_name)})

        # Check if the full branch name would be unique
        full_branch_name = f"sculptor/{result.branch_name}"
        if full_branch_name not in existing_branches:
            return result

        # If not unique and we have retries left, update the prompt
        if attempt < max_retries - 1:
            enhanced_prompt += (
                f"\n\nNOTE: The branch name '{result.branch_name}' already exists. Please generate a different one."
            )

    # If we've exhausted retries, append a number to make it unique
    base_branch = result.branch_name
    counter = 2
    while f"sculptor/{result.branch_name}" in existing_branches:
        result = model_update(result, {"branch_name": f"{base_branch}-{counter}"})
        counter += 1

    # pyre-ignore[61]: Pyre thinks result could be undefined, but it's assigned to in a loop that runs at least once.
    return result


def _clean_branch_name(branch_name: str) -> str:
    """
    Clean and validate the generated branch name to ensure it's git-compatible.

    Args:
        branch_name: The raw branch name from LLM

    Returns:
        A cleaned, git-compatible branch name
    """
    if branch_name.startswith("sculptor/"):
        branch_name = branch_name[9:]

    branch_name = branch_name.lower()

    # Replace spaces and underscores with hyphens
    branch_name = re.sub(r"[\s_]+", "-", branch_name)

    # Remove any characters that aren't alphanumeric, hyphens, or dots
    branch_name = re.sub(r"[^a-z0-9\-.]", "", branch_name)

    # Remove leading/trailing hyphens or dots
    branch_name = branch_name.strip("-.")

    # Ensure it's not empty and has a reasonable length
    if not branch_name:
        branch_name = "task"

    # Truncate if too long
    if len(branch_name) > 50:
        branch_name = branch_name[:50].rstrip("-.")

    return branch_name


def generate_title_only_from_initial_prompt(
    prompt: str, existing_branches: Sequence[str], anthropic_credentials: AnthropicCredentials
) -> str:
    """
    Generate just a title for a task (fallback method).
    """
    try:
        result = generate_title_and_branch_from_initial_prompt(prompt, existing_branches, anthropic_credentials)
        return result.title
    except LLMError:
        return _create_fallback_title(prompt)


def _create_fallback_title(prompt: str) -> str:
    """
    Create a fallback title when LLM generation fails.
    """
    # Take first sentence or up to 60 characters
    title = prompt.split(".")[0].split("\n")[0].strip()

    if len(title) > 60:
        title = title[:57] + "..."

    # Capitalize first letter
    if title:
        title = title[0].upper() + title[1:]
    else:
        title = "New Task"

    return title
