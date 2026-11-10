"""Content assertions for CLONE_MODE_PROMPT and the model tables."""

import re

from sculptor.agents.default.constants import BTW_MODEL
from sculptor.agents.default.constants import CLONE_MODE_PROMPT
from sculptor.agents.default.constants import DEFAULT_LLM_MODEL
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

    Both ids run Opus 5.5's native 1M window; the persisted members keep launching
    the exact ids they always have.
    """
    assert MODEL_SHORTNAME_MAP[LLMModel.CLAUDE_5_5_OPUS] == "claude-opus-5-5[1m]"
    assert MODEL_SHORTNAME_MAP[LLMModel.CLAUDE_5_5_OPUS_200K] == "claude-opus-5-5"


def test_sonnet_5_5_and_haiku_5_5_map_to_their_pinned_model_ids() -> None:
    """The bare ids already run with a 1M window, so neither model has a `[1m]` variant."""
    assert MODEL_SHORTNAME_MAP[LLMModel.CLAUDE_5_5_SONNET] == "claude-sonnet-5-5"
    assert MODEL_SHORTNAME_MAP[LLMModel.CLAUDE_5_5_HAIKU] == "claude-haiku-5-5"


def test_every_real_model_has_a_shortname() -> None:
    """Every model that reaches the CLI needs a `--model` id to pass to it.

    The fake models are driven by a stub harness that never shells out to Claude, so
    they are the only members allowed to be absent.
    """
    fakes = {LLMModel.FAKE_CLAUDE, LLMModel.FAKE_CLAUDE_2}
    missing = [model for model in LLMModel if model not in fakes and model not in MODEL_SHORTNAME_MAP]
    assert missing == []


def _newest_pinned_models(family: str) -> set[LLMModel]:
    """The members whose exact `--model` id carries the family's highest version."""
    versions: dict[LLMModel, tuple[int, ...]] = {}
    for model, model_id in MODEL_SHORTNAME_MAP.items():
        match = re.fullmatch(rf"claude-{family}-(\d+(?:-\d+)*)(?:\[1m\])?", model_id)
        if match is not None:
            versions[model] = tuple(int(part) for part in match.group(1).split("-"))
    newest = max(versions.values())
    return {model for model, version in versions.items() if version == newest}


def test_product_default_is_the_newest_pinned_opus() -> None:
    """Adding an Opus generation without repointing the product default fails here."""
    assert DEFAULT_LLM_MODEL in _newest_pinned_models("opus")


def test_btw_side_chat_runs_the_newest_pinned_haiku() -> None:
    """Adding a Haiku generation without repointing the `/btw` model fails here."""
    assert BTW_MODEL in _newest_pinned_models("haiku")
