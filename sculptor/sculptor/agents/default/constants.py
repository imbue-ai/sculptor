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
    LLMModel.CLAUDE_4_7_OPUS: "claude-opus-4-7[1m]",
    LLMModel.CLAUDE_4_7_OPUS_200K: "claude-opus-4-7",
    LLMModel.CLAUDE_4_6_OPUS: "claude-opus-4-6[1m]",
    LLMModel.CLAUDE_4_6_OPUS_200K: "claude-opus-4-6",
    LLMModel.CLAUDE_4_SONNET: "sonnet[1m]",
    LLMModel.CLAUDE_4_SONNET_200K: "sonnet",
    LLMModel.CLAUDE_4_HAIKU: "haiku",
    LLMModel.CLAUDE_FABLE_5: "claude-fable-5",
}


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

Because the `.git` is shared, the remotes you see (e.g. `origin`) are the user's real remotes. There is no `local` remote; sync-back is automatic via the shared object store.

You can push changes normally with `git push`, but NEVER do so without explicit permission from the user.
</Environment mode>
"""
