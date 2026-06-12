"""Content assertions for CLONE_MODE_PROMPT — locks in R5/R9 invariants."""

from sculptor.agents.default.constants import CLONE_MODE_PROMPT


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
