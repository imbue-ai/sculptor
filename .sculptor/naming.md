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

## Branch slug: when Sculptor asks you to rename the placeholder branch

Sculptor's reminder gives the exact `git branch -m` command and the prefix to keep;
this section only fixes the shape of the slug that replaces the random one.

- With a ticket: `scu-<number>-<short-description>`, for example `dev/scu-1746-inline-chat-rename`.
- Without one: a kebab-case slug of the workspace name, for example `dev/inline-chat-rename`.
- Lowercase ASCII letters, digits, and hyphens only; at most 5 words.
