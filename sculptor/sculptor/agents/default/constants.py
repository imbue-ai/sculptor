from typing import Final

from sculptor.interfaces.agents.tool_names import AgentToolName
from sculptor.state.messages import LLMModel

DEFAULT_WAIT_TIMEOUT: Final[float] = 30.0
REMOVED_MESSAGE_IDS_STATE_FILE: Final[str] = "removed_message_ids"


FILE_CHANGE_TOOL_NAMES: Final[tuple[AgentToolName, ...]] = (
    AgentToolName.EDIT,
    AgentToolName.WRITE,
    AgentToolName.MULTI_EDIT,
)


MODEL_SHORTNAME_MAP: Final[dict[LLMModel, str]] = {
    LLMModel.CLAUDE_4_OPUS: "opus[1m]",
    LLMModel.CLAUDE_4_OPUS_200K: "opus",
    LLMModel.CLAUDE_5_5_OPUS: "claude-opus-5-5[1m]",
    LLMModel.CLAUDE_5_5_OPUS_200K: "claude-opus-5-5",
    LLMModel.CLAUDE_5_OPUS: "claude-opus-5[1m]",
    LLMModel.CLAUDE_5_OPUS_200K: "claude-opus-5",
    LLMModel.CLAUDE_4_8_OPUS: "claude-opus-4-8[1m]",
    LLMModel.CLAUDE_4_8_OPUS_200K: "claude-opus-4-8",
    LLMModel.CLAUDE_4_7_OPUS: "claude-opus-4-7[1m]",
    LLMModel.CLAUDE_4_7_OPUS_200K: "claude-opus-4-7",
    LLMModel.CLAUDE_4_6_OPUS: "claude-opus-4-6[1m]",
    LLMModel.CLAUDE_4_6_OPUS_200K: "claude-opus-4-6",
    LLMModel.CLAUDE_4_SONNET: "sonnet[1m]",
    LLMModel.CLAUDE_4_SONNET_200K: "sonnet",
    LLMModel.CLAUDE_4_HAIKU: "haiku",
    LLMModel.CLAUDE_FABLE_LATEST: "fable",
    LLMModel.CLAUDE_5_5_SONNET: "claude-sonnet-5-5",
    LLMModel.CLAUDE_5_SONNET: "claude-sonnet-5",
    LLMModel.CLAUDE_5_5_HAIKU: "claude-haiku-5-5",
    LLMModel.CLAUDE_FABLE_5: "claude-fable-5",
    LLMModel.CLAUDE_FABLE_5_1: "claude-fable-5-1",
    LLMModel.CLAUDE_FABLE_5_2: "claude-fable-5-2",
}

# Models a turn may launch in fast mode. Opus 4.8 is left out on purpose: its fast mode
# is deprecated upstream, and the API rejects it once removed. The frontend's
# `supportsFastMode` (modelCapabilities.ts) must offer the toggle on the same models.
FAST_MODE_MODELS: Final[frozenset[LLMModel]] = frozenset(
    {
        LLMModel.CLAUDE_4_OPUS,
        LLMModel.CLAUDE_4_OPUS_200K,
        LLMModel.CLAUDE_5_5_OPUS,
        LLMModel.CLAUDE_5_5_OPUS_200K,
        LLMModel.CLAUDE_5_OPUS,
        LLMModel.CLAUDE_5_OPUS_200K,
        LLMModel.CLAUDE_FABLE_5_2,
        LLMModel.CLAUDE_FABLE_LATEST,
        LLMModel.FAKE_CLAUDE,
    }
)

# The product default for a Claude agent when nothing else names a model. The
# frontend's DEFAULT_LLM_MODEL (modelConstants.ts) must name the same member.
DEFAULT_LLM_MODEL: Final[LLMModel] = LLMModel.CLAUDE_5_5_OPUS

# The model `/btw` side-chat turns run on.
BTW_MODEL: Final[LLMModel] = LLMModel.CLAUDE_5_5_HAIKU


ENTITY_MENTIONS_SYSTEM_PROMPT: Final[str] = """
<Entity mentions>
When a user message contains text of the form %[type:id|display_name], it refers
to a Sculptor entity:
- type is one of: repository, workspace, agent
- id is the opaque backend identifier for that entity
- display_name is the human-readable name

The id can be used directly with sculpt CLI commands. For example:
  sculpt workspace show <id>
  sculpt agent list --workspace <id>
  sculpt agent show <id>

Do not assume the display_name is a valid argument to sculpt commands — always
use the id.
</Entity mentions>
"""

# Mode-specific system prompt content
IN_PLACE_MODE_PROMPT: Final[str] = """
<Environment mode>
You are working directly in the user's repository (in-place mode).
Changes you make appear immediately in their IDE and filesystem.
You have full access to git remotes and can push/pull normally, but NEVER push without explicit permission from the user.
</Environment mode>
"""

CLONE_MODE_PROMPT: Final[str] = """
<Environment mode>
You are working in an isolated clone of the user's repository (clone mode).

The clone's git remotes are a copy of the user's source repo's remotes
(same names, same URLs). If the user's repo has no remotes, the clone
has a single remote named `origin` pointing at their on-disk repo.

Changes you make stay in the clone. To get changes back to the user's
local repo, the user can:
- push to a remote shared with their local repo (e.g. origin), then
  pull locally, or
- push directly to their on-disk repo. Run `sculpt workspace show`
  to find the `repo_path` for this workspace, then e.g.
    git push <repo_path> HEAD:refs/heads/<new-branch-name>
  Caveat: git refuses to push into the user's currently-checked-out
  branch by default, so push to a *different* branch name and tell the
  user to check it out locally.

Never push without explicit permission from the user.
</Environment mode>
"""

WORKTREE_MODE_PROMPT: Final[str] = """
<Environment mode>
You are working in a git worktree of the user's local repository (worktree mode).

The checkout is a real git worktree, so the `.git` directory is shared with the user's repository on disk. Commits you make on this branch are immediately visible in the user's working copy — there is no separate sync step.

Because the `.git` is shared, the remotes you see (e.g. `origin`) are the user's real remotes, and there is no `local` remote. Your commits and branch are written straight into the user's `.git`, so they show up in the user's repo automatically.

You can push changes normally with `git push`, but NEVER do so without explicit permission from the user.
</Environment mode>
"""

# Formatted with `snapshot_max_new_file_size_mib`, the user's configured jj snapshot limit.
JJ_WORKSPACE_MODE_PROMPT: Final[str] = """
<Environment mode>
You are working in a jj (Jujutsu) workspace of the user's local repository (jj workspace mode).

This directory has a `.jj` directory and no `.git`, so every `git` command fails here. Use `jj` for all version control.

- The working copy is the commit `@`. Every jj command first snapshots your file changes into it; there is no staging area.
- The repository is shared with the user's own checkout and with other workspaces. Never rewrite revisions outside your own stack, and never run `jj undo`, `jj op restore` or `jj workspace forget`.
- Always pass `-m` to commands that set a description (`jj describe`, `jj commit`, `jj new`); no editor is available.
- Name your work with a bookmark, and move it onto your newest described change before pushing, for example `jj bookmark set <bookmark> -r @-`.
- NEVER push without explicit permission from the user. Push with `jj git push -b <bookmark>`. The push reaches the remote at once, but the bookmark shows up in the user's git branches only after they next run a jj command in their own checkout.
- `gh` finds the repository through `GH_REPO`, since there is no `.git` to read, but it cannot tell which bookmark is yours: pass `--head <bookmark>`, for example to `gh pr create`.
- jj does not snapshot a new file larger than {snapshot_max_new_file_size_mib} MiB: it warns and leaves the file untracked. Tell the user about such a file rather than changing jj's configuration.
- If a command fails with "The working copy is stale", run `jj workspace update-stale`, check the result with `jj st`, and tell the user what happened.
</Environment mode>
"""

# The vendored jj skill as Claude names it: the `jujutsu` skill of the `sculptor-jj` plugin.
JJ_SKILL_NAME: Final[str] = "sculptor-jj:jujutsu"

# Appended to a Claude agent's system prompt in a jj workspace, so the rule outlives
# the first-message reminder through compaction and `/clear`.
CLAUDE_JJ_SKILL_REQUIRED_PROMPT: Final[str] = f"""
The `{JJ_SKILL_NAME}` skill is required for version control in this workspace. If its instructions are not in your context, invoke it with the Skill tool (skill="{JJ_SKILL_NAME}") before you run any version-control command.
"""

# Formatted with `requested_bookmark`: which bookmark Sculptor creates for a jj workspace's work, and when.
JJ_REQUESTED_BOOKMARK_PROMPT: Final[str] = (
    """Sculptor names this workspace's work with the jj bookmark `{requested_bookmark}`. Until a bookmark is on your stack, Sculptor creates `{requested_bookmark}` on your newest described change each time one of your turns ends, if the name is free. So describe your work with `jj describe -m` or `jj commit -m`, and do not create a bookmark under another name. Keep the bookmark on your newest described change as you go, for example `jj bookmark set {requested_bookmark} -r @-`."""
)
