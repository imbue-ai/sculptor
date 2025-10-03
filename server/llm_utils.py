import json
import re
import time
from typing import Any
from typing import TypeVar
from typing import assert_never

import anthropic
from anthropic.types import CacheControlEphemeralParam
from anthropic.types import Message
from anthropic.types import TextBlock
from anthropic.types import TextBlockParam
from loguru import logger
from pydantic import BaseModel
from pydantic import ValidationError

from sculptor.services.anthropic_credentials_service.api import AnthropicApiKey
from sculptor.services.anthropic_credentials_service.api import AnthropicCredentials
from sculptor.services.anthropic_credentials_service.api import ClaudeOauthCredentials
from sculptor.utils.secret import Secret

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "claude-3-7-sonnet-20250219"

DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.0  # seconds


class LLMError(Exception):
    """Base exception for LLM utilities."""


class LLMValidationError(LLMError):
    """Exception raised when structured output validation fails after retries."""


class LLMAPIError(LLMError):
    """Exception raised when the LLM API call fails."""


def get_estimated_token_count(
    system: str,
    message: str,
    api_key: Secret,
    model: str | None = "sonnet",
):
    tokens = 11680  # 11680 comes from an api call with the system reminder and tool use
    if model == "sonnet":
        model = "claude-4-sonnet-20250514"
    else:
        model = "claude-opus-4-20250514"
    client = anthropic.Anthropic(api_key=api_key.unwrap())
    response = client.messages.count_tokens(
        model=model,
        system=system,
        messages=[{"role": "user", "content": message}],
    )
    js = json.loads(response.model_dump_json())
    return tokens + js["input_tokens"]


def get_anthropic_client(credentials: AnthropicCredentials) -> anthropic.Anthropic:
    """Get an Anthropic client using the credentials from the service."""
    match credentials:
        case AnthropicApiKey(anthropic_api_key=anthropic_api_key):
            return anthropic.Anthropic(api_key=anthropic_api_key.unwrap())
        case ClaudeOauthCredentials(access_token=access_token):
            return anthropic.Anthropic(
                auth_token=access_token.unwrap(), default_headers={"anthropic-beta": "oauth-2025-04-20"}
            )
        case _ as unreachable:
            assert_never(unreachable)


def get_llm_response(
    prompt: str,
    anthropic_credentials: AnthropicCredentials,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4000,
    temperature: float = 0.7,
    system_prompt: str | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> str:
    """
    Get a response from an LLM with a simple string prompt.

    Args:
        anthropic_credentials: Anthropic credentials
        prompt: The user prompt to send to the LLM
        model: The model name to use (defaults to Claude 3.7 Sonnet)
        max_tokens: Maximum tokens in the response
        temperature: Sampling temperature (0.0 to 1.0)
        system_prompt: Optional system prompt to set context
        max_retries: Maximum number of retries on API errors
    Returns:
        The LLM's response as a string

    Raises:
        LLMAPIError: If the API call fails after retries
        LLMError: For other configuration issues
    """
    client = get_anthropic_client(anthropic_credentials)

    messages = [{"role": "user", "content": prompt}]

    call_params: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": messages,
    }

    call_params["system"] = prepend_claude_code_system_prompt(system_prompt)

    last_exception = None
    for attempt in range(max_retries + 1):
        try:
            logger.debug("Making LLM call (attempt {}/{})", attempt + 1, max_retries + 1)
            response: Message = client.messages.create(**call_params)

            if response.content and len(response.content) > 0:
                content_block = response.content[0]
                match content_block:
                    case TextBlock(text=text):
                        return text
                    case _:
                        raise LLMAPIError(f"Unexpected content type in response: {type(content_block)}")
            else:
                raise LLMAPIError("Empty response from LLM")

        except anthropic.APIError as e:
            last_exception = e
            logger.debug("LLM API error on attempt {}: {}", attempt + 1, e)
            if attempt < max_retries:
                time.sleep(DEFAULT_RETRY_DELAY * (2**attempt))  # Exponential backoff
            continue
        except Exception as e:
            raise LLMAPIError(f"Unexpected error during LLM call: {e}") from e

    raise LLMAPIError(f"LLM API call failed after {max_retries + 1} attempts. Last error: {last_exception}")


def get_structured_llm_response(
    prompt: str,
    output_type: type[T],
    anthropic_credentials: AnthropicCredentials,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 4000,
    temperature: float = 0.7,
    system_prompt: str | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    validation_retries: int = 3,
) -> T:
    """
    Get a structured response from an LLM that conforms to a Pydantic model.

    Args:
        prompt: The user prompt to send to the LLM
        output_type: Pydantic model class that defines the expected structure
        anthropic_credentials: Anthropic credentials
        model: The model name to use (defaults to Claude 3.7 Sonnet)
        max_tokens: Maximum tokens in the response
        temperature: Sampling temperature (0.0 to 1.0)
        system_prompt: Optional system prompt to set context
        max_retries: Maximum number of retries on API errors
        validation_retries: Maximum number of retries when JSON parsing/validation fails

    Returns:
        An instance of output_type with the LLM's structured response

    Raises:
        LLMValidationError: If validation fails after retries
        LLMAPIError: If the API call fails after retries
        LLMError: For other configuration issues
    """
    schema = output_type.model_json_schema()

    enhanced_prompt = f"""
<Formatting Instructions>
    Please respond with valid JSON that matches this exact schema:

    <Schema>
        {json.dumps(schema, indent=2)}
    </Schema>

    Important:
    - Return ONLY the JSON object, no additional text or formatting
    - Ensure all required fields are included
    - Follow the exact data types specified in the schema
    - Do not include any markdown formatting or code blocks
</Formatting Instructions>

<Prompt>
    {prompt}
</Prompt>
"""

    # Retry validation logic
    last_validation_error = None
    for validation_attempt in range(validation_retries + 1):
        try:
            # Get raw response from LLM
            response_text = get_llm_response(
                prompt=enhanced_prompt,
                anthropic_credentials=anthropic_credentials,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                system_prompt=system_prompt,
                max_retries=max_retries,
            )

            # Clean the response (remove potential markdown formatting)
            cleaned_response = re.sub(r"^```(?:json)?\s*", "", response_text.strip(), flags=re.MULTILINE)
            cleaned_response = re.sub(r"```\s*$", "", cleaned_response, flags=re.MULTILINE).strip()

            try:
                parsed_data = json.loads(cleaned_response)
            except json.JSONDecodeError as e:
                raise ValidationError([f"Invalid JSON: {e}"], output_type)

            return output_type.model_validate(parsed_data)

        except ValidationError as e:
            last_validation_error = e
            logger.debug("Validation failed on attempt {}/{}: {}", validation_attempt + 1, validation_retries + 1, e)
            if validation_attempt < validation_retries:
                # Adjust temperature slightly to get different output
                temperature = min(1.0, temperature + 0.1)
                continue

    raise LLMValidationError(
        f"Failed to get valid structured response after {validation_retries + 1} attempts. "
        + f"Last validation error: {last_validation_error}"
    )


# TODO: These are duplicated from imbue_core.agents.llm_apis.anthropic_api.
# Remove those when we can depend on imbue_core normally again.
_CLAUDE_CODE_SYSTEM_PROMPT = TextBlockParam(
    type="text",
    text="You are Claude Code, Anthropic's official CLI for Claude.",
    cache_control=CacheControlEphemeralParam(type="ephemeral"),
)


def prepend_claude_code_system_prompt(system_prompt: str | list[TextBlockParam] | None) -> list[TextBlockParam]:
    if not system_prompt:
        return [_CLAUDE_CODE_SYSTEM_PROMPT]
    elif isinstance(system_prompt, str):
        return [_CLAUDE_CODE_SYSTEM_PROMPT, TextBlockParam(type="text", text=system_prompt)]
    else:
        return [_CLAUDE_CODE_SYSTEM_PROMPT] + system_prompt
