# Naming conventions

How to name the workspace, the agent, and the branch when Sculptor's auto-rename
reminder fires.

## Workspace name: the task or goal

- 3 to 6 words, sentence case, no trailing period. Say what the task is, not how
  far along it is: `Fix stuck pending question after restart`.
- Lead with the Linear ticket ID when there is one: `SCU-1746 Inline chat tab rename`.
- Name the user-visible outcome or the subsystem, never the file being edited.
- No branch names, dates, or people's names.

## Agent name: the action being taken

- 3 to 6 words, imperative verb first: `Write failing tests`, `Mock the settings UI`.
- Several agents can share a workspace, so name the slice this agent owns rather
  than repeating the workspace name.

## Branch name: rename the placeholder (worktree and clone workspaces only)

Workspaces start on a branch like `dev/gorgeous-emu`: the user's prefix plus a random
`adjective-animal` slug. Once the workspace has a real name, rename the branch to match.

- Only rename while the branch still carries the random slug. If it already has a
  meaningful name (someone typed it in the Add Workspace form), keep it.
- Keep the `<user>/` prefix exactly as it is. Replace the slug with a kebab-case slug
  of the workspace name: lowercase ASCII letters, digits, and hyphens, at most 5 words.
- With a ticket: `<user>/scu-<number>-<slug>`, for example `dev/scu-1746-inline-chat-rename`.
  Without one: `<user>/<slug>`, for example `dev/inline-chat-rename`.
- Rename with `git branch -m <new-name>` from the repo root, once, before pushing or
  opening a PR. If the command fails (for example the name is taken), keep the current
  branch and move on. Never use `-M`.
- Never rename the branch in an in-place workspace: there the checkout and branch are
  the user's own. The system prompt's "Environment mode" section says which mode this is.
