from subprocess import TimeoutExpired

from loguru import logger
from pydantic import Field

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.pydantic_serialization import SerializableModel

# How long to wait for the claude CLI to produce a title before giving up.
_CLAUDE_CLI_TIMEOUT_SECONDS = 30
# How much of the CLI output to include in log messages, to avoid huge log lines.
_MAX_LOGGED_OUTPUT_CHARS = 500
# Maximum number of words to keep when falling back to a title derived from the prompt.
_MAX_FALLBACK_TITLE_WORD_COUNT = 8


class TaskTitle(SerializableModel):
    """Structured output for LLM-generated task title."""

    title: str = Field(
        description="A concise, descriptive title (5-8 words) that captures the essence of the task",
    )


def generate_title_from_prompt(
    initial_prompt: str,
    concurrency_group: ConcurrencyGroup,
) -> TaskTitle:
    """
    Generate a concise title for a task based on the user's prompt.

    Uses Claude CLI to generate a descriptive title from the user's prompt.

    Args:
        initial_prompt: The user's task description
        concurrency_group: ConcurrencyGroup for running the process

    Returns:
        TaskTitle with an LLM-generated title, or a fallback if generation fails
    """
    system_prompt = """You are a helpful assistant that creates concise, professional titles for development tasks.

Guidelines for titles:
- Keep titles between 5-8 words
- Be specific and descriptive
- Use action verbs when appropriate
- Focus on the main objective, not implementation details
- Examples: "Add user authentication system", "Fix memory leak in parser", "Refactor database connection logic"
"""

    prompt = f"""Based on this user request, generate a concise title:

"{initial_prompt}"

Create a title that's 5-8 words long, specific enough to understand the task at a glance.

Consider the type of task (feature, bugfix, refactor, etc.) and make the title reflect that appropriately.

Respond with ONLY the title, nothing else.
"""

    try:
        logger.debug("Invoking claude CLI to generate title")
        process = concurrency_group.run_process_in_background(
            command=["claude", "-p", prompt, "--system-prompt", system_prompt],
            timeout=_CLAUDE_CLI_TIMEOUT_SECONDS,
        )
        returncode = process.wait(timeout=_CLAUDE_CLI_TIMEOUT_SECONDS)
        stdout = process.read_stdout()
        stderr = process.read_stderr()
        logger.debug(
            "Claude CLI completed: returncode={}, stdout={!r}, stderr={!r}",
            returncode,
            stdout[:_MAX_LOGGED_OUTPUT_CHARS] if stdout else None,
            stderr[:_MAX_LOGGED_OUTPUT_CHARS] if stderr else None,
        )
        if returncode == 0 and stdout.strip():
            title = stdout.strip()
            logger.debug("Generated title from claude: {!r}", title)
            return TaskTitle(title=title)
        else:
            logger.warning(
                "Claude CLI failed or returned empty output: returncode={}, stdout={!r}, stderr={!r}",
                returncode,
                stdout,
                stderr,
            )
    except (TimeoutExpired, FileNotFoundError) as e:
        logger.warning("Failed to generate title with claude: {}", e)
    except Exception as e:
        logger.warning("Unexpected error invoking claude: {}", e)

    # Fallback: use first few words of the prompt
    logger.debug("Using fallback title generation")
    words = initial_prompt.split()
    if len(words) <= _MAX_FALLBACK_TITLE_WORD_COUNT:
        title = initial_prompt
    else:
        title = " ".join(words[:_MAX_FALLBACK_TITLE_WORD_COUNT]) + "..."

    return TaskTitle(title=title)
