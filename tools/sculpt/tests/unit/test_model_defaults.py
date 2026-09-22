"""What model `sculpt` picks when the user names none.

The Claude CLI's own `opus` alias moves to a new generation as the managed CLI is
bumped, so resolving the no-flag default through it would silently change which
model new agents run on. The default is an explicit member instead; `--model opus`
keeps resolving through the alias, because asking for `opus` by name is asking for
whatever the CLI currently calls the latest Opus.
"""

from sculpt.auth import DEFAULT_CLAUDE_MODEL
from sculpt.auth import MODEL_MAPPING
from sculpt.auth import build_client
from sculpt.commands._harness_helpers import resolve_prompt_models

from sculptor.state.messages import LLMModel

_UNUSED_CLIENT = build_client("http://localhost:1")


def test_the_default_is_a_pinned_generation_not_the_rolling_alias() -> None:
    assert DEFAULT_CLAUDE_MODEL == LLMModel.CLAUDE_5_5_OPUS
    assert DEFAULT_CLAUDE_MODEL != MODEL_MAPPING["opus"]


def test_a_prompt_with_no_model_flag_gets_the_pinned_default() -> None:
    claude_model, backend_model = resolve_prompt_models(None, None, _UNUSED_CLIENT, False)
    assert claude_model == LLMModel.CLAUDE_5_5_OPUS
    assert backend_model is None


def test_asking_for_opus_by_name_still_resolves_through_the_rolling_alias() -> None:
    claude_model, _ = resolve_prompt_models(None, "opus", _UNUSED_CLIENT, False)
    assert claude_model == MODEL_MAPPING["opus"]


def test_the_default_is_the_1m_context_variant() -> None:
    """The GUI defaults to a 1M-context Opus; `sculpt` must not quietly differ."""
    assert not DEFAULT_CLAUDE_MODEL.value.endswith("-200K")
