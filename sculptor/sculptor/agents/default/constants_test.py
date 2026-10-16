"""Content assertions for CLONE_MODE_PROMPT and the model shortname map."""

from sculptor.agents.default.constants import CLONE_MODE_PROMPT
from sculptor.agents.default.constants import MODEL_SHORTNAME_MAP
from sculptor.state.messages import LLMModel


def test_clone_mode_prompt_does_not_mention_local_remote() -> None:
    """The prompt must not describe a `local` remote (which no longer exists).

    Phrases like "local repo" and "pull locally" are legitimate English and
    must still be allowed; this test only guards against the remote-name
    references that the old prompt used.
    """
    assert "`local`" not in CLONE_MODE_PROMPT
    assert "- local:" not in CLONE_MODE_PROMPT


def test_clone_mode_prompt_does_not_mention_merge_workflow() -> None:
    """The prompt must not claim a Sculptor merge workflow exists."""
    assert "merge workflow" not in CLONE_MODE_PROMPT.lower()


def test_clone_mode_prompt_mentions_sculpt_workspace_show_and_repo_path() -> None:
    """The prompt must tell Claude how to discover the source repo path at runtime."""
    assert "sculpt workspace show" in CLONE_MODE_PROMPT
    assert "repo_path" in CLONE_MODE_PROMPT


def test_opus_5_5_maps_to_its_pinned_model_ids() -> None:
    """The Opus 5.5 members map to the `--model` ids the Claude CLI accepts.

    The bracketed `[1m]` suffix is what selects the 1M-context window; the bare id
    is the 200K variant.
    """
    assert MODEL_SHORTNAME_MAP[LLMModel.CLAUDE_5_5_OPUS] == "claude-opus-5-5[1m]"
    assert MODEL_SHORTNAME_MAP[LLMModel.CLAUDE_5_5_OPUS_200K] == "claude-opus-5-5"


def test_every_real_model_has_a_shortname() -> None:
    """Every model that reaches the CLI needs a `--model` id to pass to it.

    The fake models are driven by a stub harness that never shells out to Claude, so
    they are the only members allowed to be absent.
    """
    fakes = {LLMModel.FAKE_CLAUDE, LLMModel.FAKE_CLAUDE_2}
    missing = [model for model in LLMModel if model not in fakes and model not in MODEL_SHORTNAME_MAP]
    assert missing == []
